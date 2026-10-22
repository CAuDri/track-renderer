"""Build an SVG drawing while compilers resolve a track's contents.

Geometry goes straight into ordinary SVG nodes. Only ownership, placements and
other application data stay in temporary Python records until they are written
into the document's metadata. The finished document has no parallel geometry
list to keep in sync with its drawing.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import asdict
from typing import Any, cast
from xml.etree import ElementTree as ET

from ..diagnostics import Diagnostic
from ..svg import SvgDocument, write_metadata
from ..svg.geometry import map_transform
from .records import PhysicalPart, TrackObject
from .types import GeometryData, GeometryKind, PathData, RegionData, SymbolData

SVG = "http://www.w3.org/2000/svg"


def drawing_id(identifier: str) -> str:
    """Return an XML-safe ID that stays stable when unrelated objects are added."""
    return "geometry-" + hashlib.sha256(identifier.encode()).hexdigest()


class DrawingBuilder:
    """Collect semantic records and emit native SVG during one rendering call."""

    def __init__(self, track_id: str, schema_uri: str, map_orientation: float) -> None:
        self.track_id = track_id
        self.schema_uri = schema_uri
        self.map_orientation = map_orientation
        self.complete = True
        self.background = "#1A1A1A"
        self.objects: dict[str, TrackObject] = {}
        self.parts: dict[str, PhysicalPart] = {}
        self.assets: dict[str, dict[str, Any]] = {}
        self.diagnostics: list[Diagnostic] = []
        self.validation: dict[str, Any] = {}
        self._asset_dependencies: set[str] = set()

        self.root = ET.Element(f"{{{SVG}}}svg", {"data-track-id": track_id})
        ET.SubElement(self.root, f"{{{SVG}}}title").text = track_id
        self.defs = ET.SubElement(self.root, f"{{{SVG}}}defs")
        ET.SubElement(self.root, f"{{{SVG}}}rect", {"id": "background", "fill": self.background})
        self.world = ET.SubElement(
            self.root, f"{{{SVG}}}g", {"id": "map", "transform": map_transform(map_orientation)}
        )
        self.layers: dict[int, ET.Element] = {}

    def add_geometry(
        self,
        identifier: str,
        owner: str,
        role: str,
        kind: GeometryKind,
        data: GeometryData,
        *,
        layer: int,
        part: str | None,
        purpose: str,
        sources: tuple[str, ...],
        placement_section: str | None = None,
    ) -> None:
        """Draw a compiler result immediately and attach its source identity."""
        obj = self.objects[owner]
        attributes = {
            "id": drawing_id(identifier),
            "data-geometry-id": identifier,
            "data-object-id": owner,
            "data-role": role,
            "data-purpose": purpose,
        }
        if obj.section_id:
            attributes["data-section-id"] = obj.section_id
        if obj.parent_id:
            attributes["data-parent-id"] = obj.parent_id
        if part:
            attributes["data-part-id"] = part
        if sources:
            attributes["data-source-ids"] = json.dumps(sources)
        if placement_section:
            attributes["data-placement-section-id"] = placement_section
        if purpose == "selection":
            attributes.update({"opacity": "0", "pointer-events": "all"})

        if layer not in self.layers:
            self.layers[layer] = ET.SubElement(
                self.world,
                f"{{{SVG}}}g",
                {"id": f"layer-{layer}", "data-layer": str(layer)},
            )
        group = ET.Element(f"{{{SVG}}}g", attributes)

        if kind == "path":
            self._path(group, cast(PathData, data))
        elif kind == "region":
            self._region(group, cast(RegionData, data))
        else:
            self._symbol(group, cast(SymbolData, data))

        # Attach only after drawing succeeds, so a forced partial export never
        # contains an empty or half-built graphical object.
        self.layers[layer].append(group)

    @staticmethod
    def _path(group: ET.Element, data: PathData) -> None:
        ET.SubElement(
            group,
            f"{{{SVG}}}polyline",
            {
                "points": " ".join(f"{x} {y}" for x, y in data["points"]),
                "fill": "none",
                "stroke": data["color"],
                "stroke-width": str(data["width"]),
                "stroke-linecap": data.get("cap", "butt"),
                "stroke-linejoin": data.get("join", "round"),
            },
        )

    @staticmethod
    def _region(group: ET.Element, data: RegionData) -> None:
        rings = [data["exterior"], *data.get("holes", [])]
        commands = ["M" + " L".join(f"{x} {y}" for x, y in ring) + " Z" for ring in rings]
        ET.SubElement(
            group,
            f"{{{SVG}}}path",
            {"d": " ".join(commands), "fill": data["color"], "fill-rule": "evenodd"},
        )

    def _symbol(self, group: ET.Element, data: SymbolData) -> None:
        pose = data["pose"]
        asset = data["asset"]
        # The artwork viewport is deliberately larger than one unit. Browser
        # rasterization of percentage-sized embedded SVGs otherwise loses detail.
        ET.SubElement(
            group,
            f"{{{SVG}}}use",
            {
                "href": "#asset-" + asset,
                "transform": (
                    f"translate({pose['x']} {pose['y']}) rotate({pose['yaw'] - 90}) "
                    f"scale({data['width'] / 1000} {-data['length'] / 1000})"
                ),
            },
        )

    def finish(self) -> SvgDocument:
        """Embed artwork and annotations, then hand the completed XML to callers."""
        self.world[:] = [self.layers[layer] for layer in sorted(self.layers)]
        for layer in self.layers.values():
            layer[:] = sorted(layer, key=lambda node: node.get("data-geometry-id", ""))

        assets = {}
        for identifier, asset in sorted(self.assets.items()):
            content = base64.b64encode(asset["content"].encode()).decode()
            ET.SubElement(
                self.defs,
                f"{{{SVG}}}image",
                {
                    "id": "asset-" + identifier,
                    "x": "-500",
                    "y": "-500",
                    "width": "1000",
                    "height": "1000",
                    "preserveAspectRatio": "none",
                    "href": "data:image/svg+xml;base64," + content,
                },
            )
            assets[identifier] = {key: value for key, value in asset.items() if key != "content"}

        metadata = {
            "track_id": self.track_id,
            "schema_uri": self.schema_uri,
            "map_orientation": self.map_orientation,
            "coordinates": {
                "frame": "map",
                "length_unit": "m",
                "angle_unit": "deg",
                "axes": {"x": "root_forward", "y": "left", "z": "up"},
                "positive_yaw": "counter_clockwise",
            },
            "complete": self.complete,
            "validation": self.validation,
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
            "objects": {key: asdict(value) for key, value in sorted(self.objects.items())},
            "parts": {key: asdict(value) for key, value in sorted(self.parts.items())},
            "assets": assets,
            "dependencies": sorted(
                uri for uri in self._asset_dependencies if not uri.startswith("urn:")
            ),
            "background": self.background,
        }
        self.root.set("data-complete", str(self.complete).lower())
        write_metadata(self.root, metadata)
        return SvgDocument(self.root)
