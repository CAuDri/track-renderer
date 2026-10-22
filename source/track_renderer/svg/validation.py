"""Check saved track SVGs before editors or rasterizers consume them.

This is the renderer's supported SVG profile, not a general SVG validator.
Native drawing elements stay passive and self-contained, and their semantic
IDs must agree with the track annotations carried in the same document.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import re
from typing import Any
from xml.etree import ElementTree as ET

from ..assets.validation import SVG_LIMIT, validate_svg
from ..diagnostics import SvgError
from .annotations import validate_annotations
from .geometry import href, map_transform, number, numbers, transform, vertices
from .metadata import METADATA, SVG, XLINK, read_metadata

DOCUMENT_LIMIT = 64 * 1024 * 1024
ELEMENT_LIMIT = 250_000
DEPTH_LIMIT = 64
_ELEMENTS = {
    "svg",
    "title",
    "desc",
    "metadata",
    "defs",
    "g",
    "rect",
    "polyline",
    "path",
    "image",
    "use",
}
_ATTRIBUTES = {
    "id",
    "version",
    "viewBox",
    "width",
    "height",
    "x",
    "y",
    "transform",
    "fill",
    "stroke",
    "stroke-width",
    "stroke-linecap",
    "stroke-linejoin",
    "fill-rule",
    "opacity",
    "fill-opacity",
    "stroke-opacity",
    "pointer-events",
    "display",
    "visibility",
    "points",
    "d",
    "preserveAspectRatio",
    "href",
    "role",
    "aria-label",
    "encoding",
    f"{{{XLINK}}}href",
}
_DATA_URI = "data:image/svg+xml;base64,"


def _structure(root: ET.Element) -> None:
    """Keep every painted node inside an identified geometry and drawing layer."""
    expected = {"metadata": 1, "defs": 1, "rect": 1, "g": 1}
    for name, count in expected.items():
        if len(root.findall(f"{{{SVG}}}{name}")) != count:
            raise SvgError(f"Expected exactly {count} root {name} element")
    for element in root:
        name = element.tag.rsplit("}", 1)[-1]
        if name not in {*expected, "title", "desc"}:
            raise SvgError("Unsupported drawing outside the Map group")
        if name == "metadata":
            if len(element) != 1 or element[0].tag != f"{{{METADATA}}}track":
                raise SvgError("Expected only the CAuDri track annotation in metadata")
            if element[0].attrib != {"encoding": "application/json"} or len(element[0]):
                raise SvgError("Unsupported CAuDri metadata element")
        elif name == "defs":
            if any(child.tag != f"{{{SVG}}}image" or len(child) for child in element):
                raise SvgError("Definitions may contain only embedded SVG images")
        elif name == "rect":
            if element.get("id") != "background" or len(element):
                raise SvgError("Expected the document background rectangle")
        elif name == "g":
            if element.get("id") != "map":
                raise SvgError("Expected the Map drawing group")
            for layer in element:
                if layer.tag != f"{{{SVG}}}g" or not re.fullmatch(
                    r"-?\d+", layer.get("data-layer", "")
                ):
                    raise SvgError("Map children must be numbered drawing layers")
                for group in layer:
                    if (
                        group.tag != f"{{{SVG}}}g"
                        or not group.get("data-geometry-id")
                        or not group.get("id")
                    ):
                        raise SvgError("Layer children must be identified geometry groups")
                    if len(group) != 1 or group[0].tag not in {
                        f"{{{SVG}}}{kind}" for kind in ("polyline", "path", "use")
                    }:
                        raise SvgError("Geometry groups must contain one native drawing element")
                    if len(group[0]):
                        raise SvgError("Native drawing elements must not contain child elements")
        elif len(element):
            raise SvgError("Document title and description must contain plain text")


def parse_document(content: str | bytes) -> ET.Element:
    """@brief Parse bounded UTF-8 XML without entities or stylesheet instructions."""
    if isinstance(content, bytes):
        if len(content) > DOCUMENT_LIMIT:
            raise SvgError("SVG document exceeds 64 MiB")
        try:
            content = content.decode("utf-8-sig")
        except UnicodeError as exc:
            raise SvgError("SVG document must use UTF-8") from exc
    try:
        size = len(content.encode("utf-8"))
    except UnicodeError as exc:
        raise SvgError("SVG document must contain valid Unicode text") from exc
    if size > DOCUMENT_LIMIT:
        raise SvgError("SVG document exceeds 64 MiB")
    if re.search(r"<!\s*(?:ENTITY|DOCTYPE)|<\?\s*xml-stylesheet\b", content, re.I):
        raise SvgError("SVG entities, DTDs and stylesheet instructions are not supported")
    try:
        return ET.fromstring(content)
    except (ET.ParseError, RecursionError) as exc:
        raise SvgError(f"Cannot parse SVG: {exc}") from exc


def _artwork(element: ET.Element, checked: set[str]) -> str:
    source = href(element)
    if not source.startswith(_DATA_URI):
        raise SvgError("Images must contain embedded SVG data")
    encoded = source[len(_DATA_URI) :]
    if len(encoded) > (SVG_LIMIT + 2) // 3 * 4:
        raise SvgError("Embedded SVG artwork exceeds 8 MiB")
    try:
        content = base64.b64decode(encoded, validate=True)
        identifier = hashlib.sha256(content).hexdigest()
        if identifier not in checked:
            validate_svg(content.decode("utf-8"))
            checked.add(identifier)
    except (ValueError, UnicodeError, binascii.Error) as exc:
        raise SvgError(f"Invalid embedded SVG artwork: {exc}") from exc
    return identifier


def _attributes(element: ET.Element) -> None:
    # SVG2 and older consumers can disagree about which spelling wins. Never
    # allow the second attribute to hide a different resource from the checks.
    if "href" in element.attrib and f"{{{XLINK}}}href" in element.attrib:
        if element.attrib["href"] != element.attrib[f"{{{XLINK}}}href"]:
            raise SvgError("Conflicting href and xlink:href references are not supported")
    for key, value in element.attrib.items():
        if key not in _ATTRIBUTES and not key.startswith("data-"):
            raise SvgError(f"Unsupported SVG attribute: {key}")
        if (
            key in {"fill", "stroke"}
            and value not in {"none", "transparent"}
            and not re.fullmatch(r"#[0-9a-fA-F]{6}", value)
        ):
            raise SvgError("Drawing colors must be RGB hex colors, transparent or none")
        if key in {"opacity", "fill-opacity", "stroke-opacity"} and not 0 <= number(value) <= 1:
            raise SvgError("SVG opacity must be between zero and one")
    if "transform" in element.attrib:
        transform(element.attrib["transform"])
    if "stroke-width" in element.attrib and number(element.attrib["stroke-width"]) < 0:
        raise SvgError("Stroke width must be nonnegative")
    if element.get("stroke-linecap", "butt") not in {"butt", "square", "round"}:
        raise SvgError("Unsupported SVG line cap")
    if element.get("stroke-linejoin", "miter") not in {"miter", "bevel", "round"}:
        raise SvgError("Unsupported SVG line join")


def _geometry_links(element: ET.Element, data: dict[str, Any], seen: set[str]) -> None:
    identifier = element.get("data-geometry-id")
    if not identifier:
        return
    if identifier in seen:
        raise SvgError("Duplicate logical geometry ID")
    seen.add(identifier)
    objects, parts = data["objects"], data["parts"]
    owner = element.get("data-object-id")
    if owner not in objects:
        raise SvgError(f"Geometry references an unknown object: {owner}")
    obj = objects[owner]
    for attribute, field in (("data-section-id", "section_id"), ("data-parent-id", "parent_id")):
        if element.get(attribute) != obj.get(field):
            raise SvgError(f"Geometry {attribute} disagrees with its object")
    placement = element.get("data-placement-section-id")
    if placement and placement not in objects:
        raise SvgError("Geometry placement section is unknown")
    part_id = element.get("data-part-id")
    if part_id and (part_id not in parts or parts[part_id]["object_id"] != owner):
        raise SvgError("Geometry references a missing part or another object's part")
    if element.get("data-purpose") not in {"physical", "projection", "selection"}:
        raise SvgError("Geometry has an unknown purpose")
    if not element.get("data-role"):
        raise SvgError("Geometry has no semantic role")
    try:
        sources = json.loads(element.get("data-source-ids", "[]"))
    except ValueError as exc:
        raise SvgError("Geometry source IDs must be a JSON array") from exc
    if not isinstance(sources, list) or any(
        not isinstance(item, str) or item not in objects for item in sources
    ):
        raise SvgError("Geometry source IDs contain unknown objects")


def validate_document(root: ET.Element) -> dict[str, Any]:
    """@return Validated metadata after checking native drawing and cross-links."""
    if root.tag != f"{{{SVG}}}svg":
        raise SvgError("Expected an SVG document root")
    _structure(root)
    data = read_metadata(root)
    validate_annotations(data)
    if root.get("data-track-id") != data["track_id"]:
        raise SvgError("SVG track ID disagrees with its metadata")
    if root.get("data-complete") != str(data["complete"]).lower():
        raise SvgError("SVG completion flag disagrees with its metadata")
    identifiers: dict[str, ET.Element] = {}
    logical_ids: set[str] = set()
    artwork: set[str] = set()
    assets: set[str] = set()
    pending = [(root, 0)]
    count = 0
    while pending:
        element, depth = pending.pop()
        count += 1
        if count > ELEMENT_LIMIT or depth > DEPTH_LIMIT:
            raise SvgError("SVG exceeds the supported element count or nesting depth")
        if element.tag == f"{{{METADATA}}}track":
            continue
        if element.tag not in {f"{{{SVG}}}{name}" for name in _ELEMENTS}:
            raise SvgError(f"Unsupported SVG element: {element.tag}")
        _attributes(element)
        identifier = element.get("id")
        if identifier:
            if identifier in identifiers or re.search(r"\s", identifier):
                raise SvgError("SVG IDs must be unique and contain no whitespace")
            identifiers[identifier] = element
        _geometry_links(element, data, logical_ids)
        if element.tag in {f"{{{SVG}}}polyline", f"{{{SVG}}}path"}:
            vertices(element)
        if element.tag in {f"{{{SVG}}}image", f"{{{SVG}}}rect"}:
            for field in ("width", "height"):
                if number(element.get(field, "0")) <= 0:
                    raise SvgError("SVG images and rectangles need positive dimensions")
        if element.tag in {f"{{{SVG}}}image", f"{{{SVG}}}rect", f"{{{SVG}}}use"}:
            for field in ("x", "y"):
                number(element.get(field, "0"))
        if element.tag == f"{{{SVG}}}image":
            asset = _artwork(element, artwork)
            if element.get("id") != "asset-" + asset or asset not in data["assets"]:
                raise SvgError("Embedded artwork does not match its asset metadata")
            assets.add(asset)
        pending.extend((child, depth + 1) for child in element)

    if assets != set(data["assets"]):
        raise SvgError("Asset metadata has no matching embedded SVG artwork")
    for element in root.iter():
        if element.tag == f"{{{SVG}}}use":
            source = href(element)
            target = identifiers.get(source[1:]) if source.startswith("#") else None
            if target is None or target.tag != f"{{{SVG}}}image":
                raise SvgError("SVG use must reference embedded artwork in this document")
        elif href(element) and element.tag != f"{{{SVG}}}image":
            raise SvgError("Resource references are supported only on use and image")

    worlds = root.findall(f"{{{SVG}}}g[@id='map']")
    expected = transform(map_transform(data["map_orientation"]))
    if len(worlds) != 1 or not all(
        math.isclose(actual, target, rel_tol=1e-9, abs_tol=1e-12)
        for actual, target in zip(transform(worlds[0].get("transform", "")), expected, strict=True)
    ):
        raise SvgError("Expected one Map group matching map_orientation and the SVG y-axis flip")
    if "viewBox" in root.attrib:
        viewbox = numbers(root.attrib["viewBox"])
        if len(viewbox) != 4 or min(viewbox[2:]) <= 0:
            raise SvgError("SVG viewBox must have four finite values and positive dimensions")
    return data
