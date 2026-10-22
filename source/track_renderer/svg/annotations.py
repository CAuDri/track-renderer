"""Validate track annotations and reject non-JSON values, recursive containers and invalid references.

The checks protect ownership and physical pose data used by editors. Geometry
is deliberately absent here; native SVG elements are checked separately.
"""

from __future__ import annotations

import math
import re
from typing import Any

from ..diagnostics import SvgError
from .metadata import COORDINATES


def child(path: str, key: str | int) -> str:
    """@return A child JSON Pointer suitable for a validation error."""
    return path + "/" + str(key).replace("~", "~0").replace("/", "~1")


def _fail(path: str, message: str):
    raise SvgError(message, path=path)


def _mapping(value, path, required=(), optional=()):
    if not isinstance(value, dict):
        _fail(path, "Expected an object")
    for key in required:
        if key not in value:
            _fail(child(path, key), "Required field is missing")
    if required or optional:
        for key in value.keys() - set(required) - set(optional):
            _fail(child(path, key), "Unknown field")
    return value


def _sequence(value, path):
    if not isinstance(value, (list, tuple)):
        _fail(path, "Expected an array")
    return value


def _string(value, path, *, nonempty=True):
    if not isinstance(value, str) or (nonempty and not value):
        _fail(path, "Expected a nonempty string" if nonempty else "Expected a string")


def _number(value, path, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(path, "Expected a finite number")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite or (positive and value <= 0):
        _fail(path, "Expected a positive finite number" if positive else "Expected a finite number")


def _choice(value, values, path):
    if not isinstance(value, str) or value not in values:
        _fail(path, "Expected one of: " + ", ".join(sorted(values)))


def _color(value, path):
    if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        _fail(path, "Expected a hexadecimal RGB color")


def _json(value, path, ancestors=frozenset()):
    """Reject non-JSON metadata, non-finite numbers and recursive containers."""
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, (int, float)):
        _number(value, path)
        return
    if not isinstance(value, (dict, list, tuple)):
        _fail(path, "Expected JSON-compatible data")
    if id(value) in ancestors:
        _fail(path, "Recursive containers are not supported")
    ancestors = ancestors | {id(value)}
    for key, item in value.items() if isinstance(value, dict) else enumerate(value):
        if isinstance(value, dict) and not isinstance(key, str):
            _fail(path, "Object keys must be strings")
        _json(item, child(path, key), ancestors)


def _pose(value, path, *, symbol=False):
    required = ("x", "y", "yaw") if symbol else ("x", "y")
    _mapping(value, path, required, ("z", "yaw", "pitch", "roll"))
    for key, coordinate in value.items():
        _number(coordinate, child(path, key))


def _reference(value, entries, path, *, nullable=False):
    if value is None and nullable:
        return
    _string(value, path)
    if value not in entries:
        _fail(path, f"Unknown reference: {value}")


def _objects(objects):
    fields = ("id", "type", "category", "parent_id", "section_id", "source_pointer", "properties")
    for key, obj in objects.items():
        path = child("/objects", key)
        _mapping(obj, path, fields, ("provenance", "reference_only"))
        for field in ("id", "type", "category", "source_pointer"):
            _string(obj[field], child(path, field))
        if key != obj["id"] or obj["source_pointer"] != key:
            _fail(path, "Object IDs must match their source JSON Pointers")
        if not key.startswith("/") or re.search(r"~(?![01])", key):
            _fail(child(path, "id"), "Expected a source JSON Pointer")
        _mapping(obj["properties"], child(path, "properties"))
        _mapping(obj.get("provenance", {}), child(path, "provenance"))

        _reference(obj["parent_id"], objects, child(path, "parent_id"), nullable=True)
        _reference(obj["section_id"], objects, child(path, "section_id"), nullable=True)
    # Resolve parent chains only after every referenced object has been checked.
    for key in objects:
        section = objects[key]["section_id"]
        if section is not None and objects[section]["category"] != "sections":
            _fail(child(child("/objects", key), "section_id"), "Expected a section object")
        seen, parent = {key}, objects[key]["parent_id"]
        while parent is not None:
            if parent in seen:
                _fail(child(child("/objects", key), "parent_id"), "Cyclic ownership")
            seen.add(parent)
            parent = objects[parent]["parent_id"]


def _parts(parts, objects):
    for key, part in parts.items():
        path = child("/parts", key)
        _mapping(part, path, ("id", "object_id", "role", "pose"), ("size", "properties"))
        _string(part["id"], child(path, "id"))
        if part["id"] != key:
            _fail(child(path, "id"), "Spatial part ID must match its key")
        _reference(part["object_id"], objects, child(path, "object_id"))
        _string(part["role"], child(path, "role"))
        _pose(part["pose"], child(path, "pose"))
        for dimension, size in _mapping(part.get("size", {}), child(path, "size")).items():
            _number(size, child(child(path, "size"), dimension), positive=True)
        _mapping(part.get("properties", {}), child(path, "properties"))


def validate_annotations(data: dict[str, Any]) -> None:
    """@brief Require coherent semantic records and finite, serializable values."""
    fields = (
        "track_id",
        "schema_uri",
        "map_orientation",
        "coordinates",
        "complete",
        "validation",
        "diagnostics",
        "background",
        "objects",
        "parts",
        "assets",
        "dependencies",
    )
    _mapping(data, "/metadata", fields, ("selection",))
    try:
        _json(data, "/metadata")
    except RecursionError as exc:
        raise SvgError("Track annotations are nested too deeply") from exc

    for field in ("track_id", "schema_uri"):
        _string(data[field], "/" + field)
    if data["coordinates"] != COORDINATES:
        _fail("/coordinates", "Expected the Map coordinate convention in meters and degrees")
    _number(data["map_orientation"], "/map_orientation")
    if type(data["complete"]) is not bool:
        _fail("/complete", "Expected a boolean")
    _color(data["background"], "/background")

    validation = _mapping(data["validation"], "/validation")
    if validation.get("valid") is not None and type(validation["valid"]) is not bool:
        _fail("/validation/valid", "Expected a boolean or null")

    for index, item in enumerate(_sequence(data["diagnostics"], "/diagnostics")):
        path = child("/diagnostics", index)
        _mapping(item, path, ("code", "message"), ("path", "severity", "source", "details"))
        for field in ("code", "message", "path"):
            if field in item:
                _string(item[field], child(path, field), nonempty=field == "code")
        _choice(
            item.get("severity", "error"), {"error", "warning", "info"}, child(path, "severity")
        )
        for field in ("source", "details"):
            if item.get(field) is not None:
                _mapping(item[field], child(path, field))

    for field in ("objects", "parts", "assets"):
        _mapping(data[field], "/" + field)
    _objects(data["objects"])
    _parts(data["parts"], data["objects"])
    for identifier, obj in data["objects"].items():
        if "reference_only" in obj and type(obj["reference_only"]) is not bool:
            _fail(child("/objects", identifier), "reference_only must be a boolean")

    for identifier, asset in data["assets"].items():
        path = child("/assets", identifier)
        _mapping(asset, path, ("mime_type", "sources"), ("generation",))
        if not re.fullmatch(r"[0-9a-f]{64}", identifier):
            _fail(path, "Asset identifiers must be SHA-256 content hashes")
        if asset["mime_type"] != "image/svg+xml":
            _fail(path, "Only embedded SVG artwork is supported")
        for index, source in enumerate(_sequence(asset["sources"], child(path, "sources"))):
            _string(source, child(child(path, "sources"), index))
        if "generation" in asset:
            _mapping(asset["generation"], child(path, "generation"))
    for index, uri in enumerate(_sequence(data["dependencies"], "/dependencies")):
        _string(uri, child("/dependencies", index))
