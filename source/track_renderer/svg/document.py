"""Expose a rendered track as an ordinary SVG document with useful helpers.

The XML tree is the drawing itself. Metadata access returns independent values,
while root gives editors explicit access to native SVG groups and attributes.
Selection and saving work without the original description or asset files.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from copy import deepcopy
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from ..diagnostics import Diagnostic, SvgError
from ..io import write_file
from .geometry import Bounds, drawing_bounds, numbers
from .metadata import SVG, read_metadata
from .selection import select_sections
from .validation import DOCUMENT_LIMIT, parse_document, validate_document


def _viewport(root: ET.Element, *, margin: float, scale: float, responsive: bool) -> None:
    if not math.isfinite(margin) or margin < 0 or not math.isfinite(scale) or scale <= 0:
        raise ValueError("Margin must be nonnegative and scale must be positive and finite")

    if root.get("data-fixed-viewbox") == "true" and "viewBox" in root.attrib:
        left, top, width, height = numbers(root.attrib["viewBox"])
    else:
        bounds = drawing_bounds(root, svg_coordinates=True)
        if bounds is None:
            left, top, width, height = -0.5, -0.5, 1.0, 1.0
        else:
            left, top, right, bottom = bounds
            width, height = right - left + 2 * margin, bottom - top + 2 * margin
            left, top = left - margin, top - margin
            # A degenerate but finite edited shape still needs a valid viewport.
            width, height = max(width, 1e-12), max(height, 1e-12)
        root.set("viewBox", f"{left} {top} {width} {height}")

    if not all(
        math.isfinite(value)
        for value in (left, top, width, height, width * 1000 / scale, height * 1000 / scale)
    ):
        raise ValueError("Drawing dimensions exceed the finite SVG coordinate range")
    if responsive:
        root.attrib.pop("width", None)
        root.attrib.pop("height", None)
    else:
        root.set("width", f"{width * 1000 / scale:g}mm")
        root.set("height", f"{height * 1000 / scale:g}mm")

    background = root.find(f"{{{SVG}}}rect[@id='background']")
    if background is not None:
        background.attrib.update(x=str(left), y=str(top), width=str(width), height=str(height))


class SvgDocument:
    """@brief A native SVG drawing and its CAuDri semantic annotations.

    Direct root edits change the drawing, not the authored track or physical
    poses in metadata. Saving validates our supported SVG profile. It does not
    attempt to interpret arbitrary SVG files from other drawing applications.
    """

    def __init__(self, root: ET.Element):
        self.root = root
        background = root.find(f"{{{SVG}}}rect[@id='background']")
        if background is not None and "viewBox" not in root.attrib:
            background.attrib.setdefault("width", "1")
            background.attrib.setdefault("height", "1")
        validate_document(root)
        if "viewBox" not in root.attrib:
            _viewport(root, margin=0.5, scale=1, responsive=False)

    @property
    def metadata(self) -> dict[str, Any]:
        """@return An independent copy of every semantic annotation."""
        return read_metadata(self.root)

    @property
    def track_id(self) -> str:
        return self.metadata["track_id"]

    @property
    def schema_uri(self) -> str:
        return self.metadata["schema_uri"]

    @property
    def map_orientation(self) -> float:
        return self.metadata["map_orientation"]

    @property
    def complete(self) -> bool:
        return self.metadata["complete"]

    @property
    def validation(self) -> dict[str, Any]:
        return self.metadata["validation"]

    @property
    def diagnostics(self) -> list[Diagnostic]:
        return [Diagnostic(**item) for item in self.metadata["diagnostics"]]

    @property
    def objects(self) -> dict[str, dict[str, Any]]:
        return self.metadata["objects"]

    @property
    def parts(self) -> dict[str, dict[str, Any]]:
        return self.metadata["parts"]

    @property
    def assets(self) -> dict[str, dict[str, Any]]:
        return self.metadata["assets"]

    @property
    def dependencies(self) -> tuple[str, ...]:
        return tuple(self.metadata["dependencies"])

    def bounds(self) -> Bounds | None:
        """@return Painted Map bounds; invisible selection aids do not contribute."""
        return drawing_bounds(self.root)

    def validate(self) -> None:
        """@brief Check the SVG profile, embedded artwork and semantic cross-links."""
        validate_document(self.root)

    def to_svg(self, *, margin: float = 0.5, scale: float = 1, responsive: bool = False) -> str:
        """@return A standalone SVG, leaving this document's XML tree unchanged.

        @param margin Viewport padding in meters; unused for a fixed selection viewport.
        @param scale Physical scale denominator, such as 10 for a 1:10 drawing.
        @param responsive Omit physical dimensions so a viewer can fit the viewBox.
        """
        self.validate()
        root = deepcopy(self.root)
        _viewport(root, margin=margin, scale=scale, responsive=responsive)
        content = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            + ET.tostring(root, encoding="unicode")
            + "\n"
        )
        if len(content.encode("utf-8")) > DOCUMENT_LIMIT:
            raise SvgError("SVG document exceeds 64 MiB")
        return content

    def write(
        self, path: str | Path, *, margin: float = 0.5, scale: float = 1, responsive: bool = False
    ) -> None:
        """@brief Atomically save this document as a self-contained SVG file."""
        write_file(path, self.to_svg(margin=margin, scale=scale, responsive=responsive))

    def select_sections(self, ids: Iterable[str], *, fit_viewbox: bool = True) -> SvgDocument:
        """@return An independent document containing sections and owned descendants.

        IDs can be full source pointers or short section names. An empty selection
        is valid. Retained reference-only records do not bring their drawings along.
        With fit_viewbox=False, keep the original viewport through saving/loading.
        """
        self.validate()
        return SvgDocument(select_sections(self.root, ids, fit_viewbox=fit_viewbox))


def load_svg(source: str | bytes | Path) -> SvgDocument:
    """@brief Load one of our SVG exports from a path, XML text or UTF-8 bytes.

    No original track, schema bundle or external artwork is opened. General SVG
    editing/import is outside this loader's scope; it checks the renderer profile.
    """
    if isinstance(source, Path) or (
        isinstance(source, str) and not source.lstrip("\ufeff \t\r\n").startswith("<")
    ):
        with Path(source).open("rb") as stream:
            content = stream.read(DOCUMENT_LIMIT + 1)
    else:
        content = source
    if not isinstance(content, (str, bytes)):
        raise TypeError("Expected an SVG path, XML string or bytes")
    root = parse_document(content)
    if "viewBox" not in root.attrib:
        raise SvgError("Saved SVG documents must include a viewBox")
    return SvgDocument(root)
