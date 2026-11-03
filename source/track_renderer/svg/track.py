"""Reassemble an expanded Track Description from the SVG's source records.

The track header and object properties partition the expanded input. Geometry,
physical parts and provenance are derived data and do not enter the description.
Reconstruction reads no schemas or assets and does not infer source parameters
from edited SVG paths.
"""

from copy import deepcopy
from typing import Any

from ..diagnostics import SvgError
from .annotations import validate_annotations


def _location(obj: dict[str, Any], objects: dict[str, Any]) -> tuple[list[str], bool]:
    """Find the slot relative to its parent and recognize untyped parking records."""
    path = obj["source_pointer"]
    parent_id = obj["parent_id"]
    category = obj["category"]

    if parent_id is None:
        suffix = path
        expected_section = path if category == "sections" else None
    else:
        if not path.startswith(parent_id + "/"):
            raise SvgError("Source pointer is outside its parent object", path=path)
        suffix = path[len(parent_id) :]
        expected_section = objects[parent_id]["section_id"]

    keys = [key.replace("~1", "/").replace("~0", "~") for key in suffix[1:].split("/")]
    if len(keys) != 2 or obj["section_id"] != expected_section:
        raise SvgError("Source pointer and ownership disagree", path=path)

    synthetic = False
    if parent_id is None:
        valid = category in {"sections", "features", "zones", "actors"} and keys[0] == category
    else:
        parent_type = objects[parent_id]["type"]
        if parent_type == "parking_area" and keys[0] == "parameters":
            synthetic = True
            valid = (
                category == "elements"
                and obj["type"] == "parking_lot"
                and keys[1] in {"parallel_parking", "perpendicular_parking"}
            )
        elif parent_type == "parking_lot" and keys[0] == "spots":
            synthetic = True
            valid = category == "elements" and obj["type"] == "parking_spot"
        else:
            valid = category in {"features", "zones", "elements"} and keys[0] == category

    if not valid:
        raise SvgError("Source pointer does not identify a supported object slot", path=path)
    return keys, synthetic


def to_track(metadata: dict[str, Any]) -> dict[str, Any]:
    """@return An independent expanded track assembled from an unfiltered drawing.

    This checks the source tree, not Track Description validity. A forced render
    may still return invalid source data; prepare_track() can validate it again.
    """
    validate_annotations(metadata)
    objects = metadata["objects"]
    if "selection" in metadata or any(obj.get("reference_only") for obj in objects.values()):
        raise SvgError("Track reconstruction requires a full, unfiltered SVG", path="/selection")

    track = deepcopy(metadata["track"])
    restored: dict[str, dict[str, Any]] = {}

    # Parents precede their children regardless of the JSON object's key order.
    for path in sorted(objects, key=lambda key: (key.count("/"), key)):
        obj = objects[path]
        keys, synthetic = _location(obj, objects)
        parent_id = obj["parent_id"]
        parent = track if parent_id is None else restored.get(parent_id)
        collection = parent.get(keys[0]) if parent is not None else None
        if not isinstance(collection, dict):
            raise SvgError("Source collection is missing or is not a mapping", path=path)
        if keys[1] in collection:
            raise SvgError("Object conflicts with a value in its parent's properties", path=path)

        value = deepcopy(obj["properties"])
        if "type" in value:
            raise SvgError("Object type must be stored in the record's type field", path=path)
        if not synthetic:
            value["type"] = obj["type"]

        collection[keys[1]] = value
        restored[path] = value

    return track
