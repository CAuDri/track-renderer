"""Extract section drawings while preserving global SVG paint order.

Ownership decides which objects belong to a section. A source reference or
physical overlap does not silently make an unrelated object part of it. Small
reference-only records keep retained annotations meaningful after extraction.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from copy import deepcopy
from typing import Any
from xml.etree import ElementTree as ET

from ..diagnostics import SvgError
from .geometry import href
from .metadata import SVG, read_metadata, write_metadata


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings(item)


def select_sections(
    root: ET.Element, identifiers: Iterable[str], *, fit_viewbox: bool
) -> ET.Element:
    """Return independent XML containing the requested sections and their children."""
    result = deepcopy(root)
    data = read_metadata(result)
    objects = data["objects"]
    sections = {key for key, value in objects.items() if value["category"] == "sections"}
    requested = set()
    if isinstance(identifiers, str):
        identifiers = [identifiers]
    for identifier in identifiers:
        if not isinstance(identifier, str):
            raise TypeError("Section IDs must be strings")
        pointer = (
            identifier
            if identifier in sections
            else "/sections/" + identifier.replace("~", "~0").replace("/", "~1")
        )
        if pointer not in sections:
            raise SvgError(f"Unknown section: {identifier}")
        if objects[pointer].get("reference_only"):
            raise SvgError(
                f"Section is present only as a reference; select it from the original document: {identifier}"
            )
        requested.add(pointer)

    owned = set(requested)
    while True:
        children = {key for key, obj in objects.items() if obj["parent_id"] in owned}
        if children <= owned:
            break
        owned.update(children)

    references = set(owned)
    world = result.find(f"{{{SVG}}}g[@id='map']")
    assert world is not None
    for layer in list(world):
        for group in list(layer):
            if group.get("data-object-id") not in owned:
                layer.remove(group)
                continue
            references.update(json.loads(group.get("data-source-ids", "[]")))
            if group.get("data-placement-section-id"):
                references.add(group.get("data-placement-section-id"))
        if not len(layer):
            world.remove(layer)

    # Ancestors explain ownership; related source records explain generated
    # drawings such as missing-marking intervals. Keep records, not their paint.
    while True:
        previous = set(references)
        for identifier in previous:
            obj = objects[identifier]
            references.update(
                value for value in (obj.get("parent_id"), obj.get("section_id")) if value
            )
            references.update(value for value in _strings(obj) if value in objects)
        if references == previous:
            break

    data["objects"] = {
        key: {**obj, **({"reference_only": True} if key not in owned else {})}
        for key, obj in objects.items()
        if key in references
    }
    data["parts"] = {key: part for key, part in data["parts"].items() if part["object_id"] in owned}
    required_assets = {
        href(node).removeprefix("#asset-") for node in world.iter() if node.tag == f"{{{SVG}}}use"
    }
    required_assets.update(value for value in _strings(data["parts"]) if value in data["assets"])
    required_assets.update(value for value in _strings(data["objects"]) if value in data["assets"])
    data["assets"] = {key: value for key, value in data["assets"].items() if key in required_assets}
    for definitions in result.findall(f"{{{SVG}}}defs"):
        for element in list(definitions):
            if element.get("id", "").removeprefix("asset-") not in required_assets:
                definitions.remove(element)

    data["selection"] = {"section_ids": sorted(requested), "validation_scope": "source_track"}
    write_metadata(result, data)
    if fit_viewbox:
        result.attrib.pop("data-fixed-viewbox", None)
        result.attrib.pop("viewBox", None)
    else:
        result.set("data-fixed-viewbox", "true")
    return result
