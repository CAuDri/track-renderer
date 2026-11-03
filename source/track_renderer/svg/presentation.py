"""Remove track annotations from an export copy, leaving only visible SVG content.

Paint order, transforms and embedded artwork remain intact. Source metadata,
invisible selection regions and unnecessary wrapper groups are not needed by
viewers and take up most of the space in small illustrations.
"""

from xml.etree import ElementTree as ET

from .geometry import href
from .metadata import SVG


def strip_metadata(root: ET.Element) -> None:
    """@brief Reduce a validated export tree to standalone presentation SVG."""
    for parent in list(root.iter()):
        for child in list(parent):
            if child.tag == f"{{{SVG}}}metadata" or child.get("data-purpose") == "selection":
                parent.remove(child)

    # Only artwork referenced by a surviving use element needs an ID or payload.
    referenced = {
        href(node)[1:] for node in root.iter(f"{{{SVG}}}use") if href(node).startswith("#")
    }
    definitions = root.find(f"{{{SVG}}}defs")
    if definitions is not None:
        definitions[:] = [node for node in definitions if node.get("id") in referenced]

    for node in root.iter():
        for name in list(node.attrib):
            if name.startswith("data-") or (name == "id" and node.attrib[name] not in referenced):
                del node.attrib[name]

    # Work upwards so emptied layers and attribute-free geometry wrappers can
    # disappear without changing inheritance, transformations or painter order.
    for parent in reversed(list(root.iter())):
        children = []
        for node in parent:
            if node.tag == f"{{{SVG}}}g" and not node.attrib:
                children.extend(node)
            elif node.tag == f"{{{SVG}}}defs" and not len(node):
                continue
            else:
                children.append(node)
        parent[:] = children
