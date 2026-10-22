"""Keep the working state for one render and emit checked SVG drawing elements.

Compilers share this context to resolve source objects, report findings and build
the SVG. Prepared input stays read-only; the XML drawing belongs to the
new document, so a later render cannot change an earlier result.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Iterable
from copy import copy, deepcopy
from dataclasses import asdict
from typing import TYPE_CHECKING, Any, Literal

from shapely.errors import GEOSException
from shapely.geometry import Polygon

from ..description import PreparedTrack
from ..diagnostics import Diagnostic, RenderFailure
from ..geometry.primitives import positive
from ..options import RenderOptions
from .builder import DrawingBuilder
from .indexing import index_objects
from .instance_index import InstanceIndex
from .pointers import pointer
from .records import PhysicalPart, Pose
from .types import GeometryData, GeometryKind, GeometryPurpose, Point

if TYPE_CHECKING:
    from ..description.types import Section
    from ..markings.planning import DashChain, MarkingRun
    from ..sections.intersection.geometry import Junction


class Context:
    """@brief Share source lookup, drawing helpers and diagnostics for one render."""

    def __init__(self, prepared: PreparedTrack, options: RenderOptions) -> None:
        self.prepared, self.options = prepared, options
        self.track = prepared.expansion.track
        self.model = copy(prepared.model)
        self.tolerance = options.curve_tolerance or (
            self.model.approximation if self.model is not None else 0.0001
        )
        if self.model is not None:
            # Junction sampling uses the model tolerance. Copy only the wrapper;
            # sections and validated placements remain shared, read-only input.
            self.model.approximation = self.tolerance

        self.drawing = DrawingBuilder(
            self.track["id"],
            self.track["$schema"],
            self.track.get("root", {}).get("map_orientation", 0),
        )
        self.drawing.diagnostics = deepcopy(list(prepared.diagnostics))
        self.drawing.validation = deepcopy(prepared.validation)
        self.drawing._asset_dependencies.update(
            document.uri for document in prepared.bundle.documents.values()
        )
        if prepared.expansion.source:
            self.drawing._asset_dependencies.add(prepared.expansion.source.uri)

        self.sources: dict[str, dict[str, Any]] = {}
        self.phases: dict[MarkingRun, tuple[float, int]] = {}
        self.dash_chains: dict[MarkingRun, DashChain] = {}
        self.junctions: dict[str, Junction] = {}
        self._ids: set[str] = set()

        index = index_objects(self.track, prepared.expansion.provenance, self.issue)
        self.drawing.objects, self.sources = index.objects, index.sources
        self.instances = InstanceIndex(self.model.instances if self.model is not None else ())
        self.sections_by_path = (
            {section.path: section for section in self.model.sections.values()}
            if self.model is not None
            else {}
        )

    def issue(
        self,
        path: str,
        message: str,
        code: str = "render.unresolved",
        *,
        severity: Literal["error", "warning"] = "error",
        details: dict[str, Any] | None = None,
    ) -> None:
        """@brief Record a source-linked finding; only errors make rendering incomplete."""
        if severity == "error":
            self.drawing.complete = False

        source = None
        if self.prepared.expansion.source:
            from ..description import upstream

            expansion, _ = upstream()
            source = expansion.source_location(
                self.prepared.expansion.source, path, self.prepared.expansion.provenance
            )
        self.drawing.diagnostics.append(
            Diagnostic(code, message, path, severity, deepcopy(source), deepcopy(details or {}))
        )

    def attempt(self, path: str, operation: Callable[[], Any]) -> None:
        """@brief Record a drawing failure and let the remaining objects render.

        Invalid forced input may lack fields that validation normally guarantees.
        The same failure on valid input should reach the developer for debugging.
        """
        try:
            operation()
        except (RenderFailure, OSError, GEOSException) as exc:
            self.issue(path, str(exc))
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            if self.prepared.valid:
                raise
            self.issue(path, str(exc), code="render.invalid_source")

    def section(self, path: str) -> Section:
        """@return The section used for placement, anchored to the track's root.

        An explicit at.section takes precedence over semantic ownership. A global
        feature can therefore use a road's coordinates without becoming its child.
        """
        obj = self.drawing.objects[path]
        value = self.sources[path]
        section_path = obj.section_id
        explicit = value.get("at", {}).get("section")
        if explicit:
            section_path = pointer("/sections", explicit)
        if self.model is None or section_path is None:
            raise RenderFailure("No resolved owning section")
        section = self.sections_by_path.get(section_path)
        if (
            section is None
            or section.component != self.model.root_component
            or section.component < 0
        ):
            raise RenderFailure("Section has no position relative to the root")
        return section

    def add_geometry(
        self,
        owner: str,
        role: str,
        kind: GeometryKind,
        data: GeometryData,
        *,
        layer: int = 30,
        part: str | None = None,
        purpose: GeometryPurpose = "physical",
        sources: Iterable[str] = (),
        placement_section: str | None = None,
    ) -> None:
        """@brief Add drawing data under a stable owner-and-role identifier.

        The SVG stores the geometry directly in native drawing elements. Contributing source IDs
        explain, for example, which zones changed a marking; they do not change
        the object's owner. The optional part links a drawing to a physical body.
        """
        if owner not in self.drawing.objects:
            raise RenderFailure(f"Unknown geometry owner: {owner}")
        identifier = owner + "#" + role
        if identifier in self._ids:
            raise RenderFailure(f"Duplicate geometry identifier: {identifier}")
        if "color" in data and not re.fullmatch(r"#[0-9A-Fa-f]{6}", str(data["color"])):
            raise RenderFailure("Drawing color must be a hexadecimal RGB value")

        self._ids.add(identifier)
        self.drawing.add_geometry(
            identifier,
            owner,
            role,
            kind,
            data,
            layer=layer,
            part=part,
            purpose=purpose,
            sources=tuple(sorted(sources)),
            placement_section=placement_section,
        )

    def path(
        self,
        owner: str,
        role: str,
        points: Iterable[Point],
        color: str,
        width: float,
        *,
        join: Literal["round", "miter", "bevel"] = "round",
        layer: int = 30,
        part: str | None = None,
        purpose: GeometryPurpose = "physical",
        sources: Iterable[str] = (),
    ) -> None:
        """@brief Add a stroked line in Map coordinates, with width in meters."""
        positive(width, "stroke width")
        points = [tuple(map(float, p)) for p in points]
        if len(points) < 2 or not all(math.isfinite(v) for p in points for v in p):
            raise RenderFailure("A path needs at least two finite points")
        self.add_geometry(
            owner,
            role,
            "path",
            {"points": points, "color": color, "width": width, "cap": "butt", "join": join},
            layer=layer,
            part=part,
            purpose=purpose,
            sources=sources,
        )

    def region(
        self,
        owner: str,
        role: str,
        polygon: Polygon | Iterable[Point],
        color: str,
        *,
        layer: int = 30,
        part: str | None = None,
        purpose: GeometryPurpose = "physical",
        sources: Iterable[str] = (),
        placement_section: str | None = None,
    ) -> None:
        """@brief Add a filled polygon, preserving any holes in a Shapely input."""
        if not isinstance(polygon, Polygon):
            polygon = Polygon(polygon)
        if not polygon.is_valid or polygon.is_empty or polygon.area <= 0:
            raise RenderFailure("Drawing polygon is empty or invalid")
        self.add_geometry(
            owner,
            role,
            "region",
            {
                "exterior": list(polygon.exterior.coords)[:-1],
                "holes": [list(r.coords)[:-1] for r in polygon.interiors],
                "color": color,
            },
            layer=layer,
            part=part,
            purpose=purpose,
            sources=sources,
            placement_section=placement_section,
        )

    def part(
        self,
        owner: str,
        role: str,
        pose: Pose,
        size: dict[str, float] | None = None,
        properties: dict[str, Any] | None = None,
    ) -> str:
        """@brief Keep a physical placement even when its drawing is turned off.

        Dimensions and properties are copied into the scene. No missing physical
        dimension is guessed from artwork or from the size of a selection region.
        @return The stable part ID used to link optional drawings to this body.
        """
        identifier = owner + "#" + role
        if identifier in self.drawing.parts:
            raise RenderFailure(f"Duplicate spatial part: {identifier}")
        if not all(math.isfinite(v) for v in asdict(pose).values()):
            raise RenderFailure("Pose must be finite")
        for key, value in (size or {}).items():
            positive(value, "physical " + key)

        self.drawing.parts[identifier] = PhysicalPart(
            identifier, owner, role, pose, deepcopy(size or {}), deepcopy(properties or {})
        )
        return identifier

    def symbol(
        self,
        owner: str,
        role: str,
        pose: Pose,
        asset: str,
        length: float,
        width: float,
        *,
        part: str | None = None,
        purpose: GeometryPurpose = "projection",
        layer: int = 60,
    ) -> None:
        """@brief Place embedded SVG artwork at its physical size and orientation.

        An asset can be an existing scene asset ID or a URI to load. In Map
        coordinates, length follows the pose's forward axis and width spans it.
        """
        from ..assets import embed_asset

        positive(length)
        positive(width)
        asset_id = asset if asset in self.drawing.assets else embed_asset(self.drawing, asset)
        self.add_geometry(
            owner,
            role,
            "symbol",
            {"pose": asdict(pose), "asset": asset_id, "length": length, "width": width},
            layer=layer,
            part=part,
            purpose=purpose,
        )
