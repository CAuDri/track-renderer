"""Turn the expanded object tree into the scene's ownership and source index.

Ownership follows nested source collections, not the roads used for placement.
Each scene object also receives the expansion history for its source subtree,
so an editor can relate generated or defaulted values to the authored track.
"""

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from .pointers import pointer
from .records import TrackObject


@dataclass
class SemanticIndex:
    """Objects and their source mappings for one compilation."""

    objects: dict[str, TrackObject]
    sources: dict[str, dict[str, Any]]


def _index_provenance(provenance: dict[str, Any]) -> dict[str, list[tuple[str, Any]]]:
    """Group source entries by pointer prefix in their original insertion order.

    A parent object includes its descendants' history. Building those groups once
    avoids scanning every source entry again for every object. Keep references
    here; each object copies its own history when it is added to the scene.
    """
    by_prefix: dict[str, list[tuple[str, Any]]] = {}
    for path, entry in provenance.items():
        prefix = path
        while prefix:
            by_prefix.setdefault(prefix, []).append((path, entry))
            prefix = prefix.rpartition("/")[0]
    return by_prefix


def index_objects(
    track: dict[str, Any],
    source_provenance: dict[str, Any],
    issue: Callable[[str, str], None],
) -> SemanticIndex:
    """@brief Collect source objects, their owners and their expansion history."""
    objects: dict[str, TrackObject] = {}
    sources: dict[str, dict[str, Any]] = {}
    provenance_by_path = _index_provenance(source_provenance)

    def visit(
        value: Any,
        path: str,
        category: str,
        parent: str | None = None,
        section: str | None = None,
        kind: str | None = None,
    ) -> None:
        if not isinstance(value, dict):
            if value is not False or category == "sections":
                issue(path, "Source object is not a mapping")
            return

        sources[path] = value
        properties = {
            k: deepcopy(v)
            for k, v in value.items()
            if k not in {"elements", "features", "zones", "type"}
        }
        if kind == "parking_lot":
            properties.pop("spots", None)
        if value.get("type") == "parking_area":
            for lot in ("parallel_parking", "perpendicular_parking"):
                if isinstance(properties.get("parameters"), dict):
                    properties["parameters"].pop(lot, None)
        provenance = {key: deepcopy(entry) for key, entry in provenance_by_path.get(path, ())}

        type_name = kind or value.get("type", "unknown")
        if not isinstance(type_name, str):
            properties["invalid_type"] = type_name
            type_name = "unknown"
        objects[path] = TrackObject(
            path, type_name, category, parent, section, path, properties, provenance
        )

        for collection in ("features", "zones", "elements"):
            children = value.get(collection, {})
            if isinstance(children, dict):
                for key, child in sorted(children.items()):
                    visit(child, pointer(path + "/" + collection, key), collection, path, section)
            else:
                issue(path + "/" + collection, "Expected an object mapping")

        if value.get("type") == "parking_area":
            parameters = value.get("parameters", {})
            if not isinstance(parameters, dict):
                issue(path + "/parameters", "Expected parking parameters to be a mapping")
                return
            for lot_name in ("parallel_parking", "perpendicular_parking"):
                lot = parameters.get(lot_name)
                if not isinstance(lot, dict):
                    continue
                lot_path = path + "/parameters/" + lot_name
                visit(lot, lot_path, "elements", path, section, "parking_lot")
                spots = lot.get("spots", {})
                if not isinstance(spots, dict):
                    issue(lot_path + "/spots", "Expected parking spots to be a mapping")
                    continue
                for key, spot in sorted(spots.items()):
                    visit(
                        spot,
                        pointer(lot_path + "/spots", key),
                        "elements",
                        lot_path,
                        section,
                        "parking_spot",
                    )

    sections = track.get("sections", {})
    for key, value in sorted(sections.items()) if isinstance(sections, dict) else ():
        path = pointer("/sections", key)
        visit(value, path, "sections", section=path)
    for category in ("features", "zones", "actors"):
        collection = track.get(category, {})
        if not isinstance(collection, dict):
            issue("/" + category, "Expected an object mapping")
            continue
        for key, value in sorted(collection.items()):
            # A global object's at.section is a placement reference, not an owner.
            visit(value, pointer("/" + category, key), category)

    return SemanticIndex(objects, sources)
