"""Keep track semantics in SVG metadata without duplicating its drawing.

SVG owns the geometry. This small application payload only describes source
objects, physical parts and validation results, linked to the drawing by IDs.
Ordinary SVG viewers can ignore it and still display the complete track.
"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any
from xml.etree import ElementTree as ET

from ..diagnostics import SvgError

SVG = "http://www.w3.org/2000/svg"
METADATA = "urn:caudri:track-renderer:metadata:1"
XLINK = "http://www.w3.org/1999/xlink"
ET.register_namespace("", SVG)
ET.register_namespace("caudri", METADATA)
ET.register_namespace("xlink", XLINK)

COORDINATES = {
    "frame": "map",
    "length_unit": "m",
    "angle_unit": "deg",
    "axes": {"x": "root_forward", "y": "left", "z": "up"},
    "positive_yaw": "counter_clockwise",
}


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise SvgError(f"Duplicate metadata key: {key}")
        result[key] = value
    return result


def read_metadata(root: ET.Element) -> dict[str, Any]:
    """@return An independent semantic payload from a renderer-produced SVG."""
    records = root.findall(f"{{{SVG}}}metadata/{{{METADATA}}}track")
    if len(records) != 1:
        raise SvgError("Expected one CAuDri track metadata record")
    record = records[0]
    if record.get("encoding") != "application/json" or len(record):
        raise SvgError("Unsupported CAuDri metadata encoding")
    try:
        value = json.loads(record.text or "", object_pairs_hook=_unique_keys)
    except (ValueError, RecursionError) as exc:
        raise SvgError(f"Cannot decode track metadata: {exc}") from exc
    if not isinstance(value, dict):
        raise SvgError("Track metadata must be an object")
    return value


def write_metadata(root: ET.Element, data: dict[str, Any]) -> None:
    """@brief Replace the semantic payload, leaving native SVG geometry intact."""
    payload = deepcopy(data)
    payload.setdefault("coordinates", deepcopy(COORDINATES))
    try:
        content = json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False)
    except (ValueError, TypeError, RecursionError) as exc:
        raise SvgError(f"Metadata must contain finite JSON-compatible values: {exc}") from exc

    container = root.find(f"{{{SVG}}}metadata")
    if container is None:
        container = ET.Element(f"{{{SVG}}}metadata")
        root.insert(0, container)
    for existing in list(container):
        if existing.tag == f"{{{METADATA}}}track":
            container.remove(existing)
    record = ET.SubElement(container, f"{{{METADATA}}}track", {"encoding": "application/json"})
    record.text = content
