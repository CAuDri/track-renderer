"""Measure the native SVG shapes emitted by the track renderer.

The renderer uses explicit polylines, straight-edged filled paths and embedded
images. Reading those elements keeps bounds tied to the actual drawing, even
after a caller hides or moves a group through the XML tree.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterator
from xml.etree import ElementTree as ET

from ..diagnostics import SvgError
from .metadata import SVG, XLINK
from .strokes import stroke_extrema

Point = tuple[float, float]
Bounds = tuple[float, float, float, float]
Matrix = tuple[float, float, float, float, float, float]
IDENTITY: Matrix = (1, 0, 0, 1, 0, 0)
_NUMBER = r"[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?"
_TOKEN = re.compile(_NUMBER)
_TRANSFORM = re.compile(r"([A-Za-z]+)\s*\(([^()]*)\)")
_PAINT_DEFAULTS = {
    "visibility": "visible",
    "fill": "#000000",
    "fill-opacity": "1",
    "stroke": "none",
    "stroke-opacity": "1",
    "stroke-width": "1",
    "stroke-linecap": "butt",
    "stroke-linejoin": "miter",
}


def numbers(value: str) -> list[float]:
    """Read a finite SVG number list without accepting unparsed trailing text."""
    if _TOKEN.sub("", value).strip(" ,\t\r\n"):
        raise SvgError(f"Invalid SVG number list: {value[:100]}")
    result = [float(token) for token in _TOKEN.findall(value)]
    if not all(math.isfinite(number) for number in result):
        raise SvgError("SVG coordinates must be finite")
    return result


def number(value: str) -> float:
    result = numbers(value)
    if len(result) != 1:
        raise SvgError("Expected one SVG number")
    return result[0]


def multiply(left: Matrix, right: Matrix) -> Matrix:
    a, b, c, d, e, f = left
    g, h, i, j, k, offset_y = right
    result = (
        a * g + c * h,
        b * g + d * h,
        a * i + c * j,
        b * i + d * j,
        a * k + c * offset_y + e,
        b * k + d * offset_y + f,
    )
    if not all(math.isfinite(value) for value in result):
        raise SvgError("SVG transform exceeds finite coordinates")
    return result


def transform(value: str) -> Matrix:
    """Resolve the ordinary affine transforms supported by our SVG profile."""
    if _TRANSFORM.sub("", value).strip(" ,\t\r\n"):
        raise SvgError("Invalid SVG transform")
    result = IDENTITY
    for match in _TRANSFORM.finditer(value):
        kind, args = match[1], numbers(match[2])
        if kind == "matrix" and len(args) == 6:
            current = tuple(args)
        elif kind == "translate" and len(args) in (1, 2):
            current = (1, 0, 0, 1, args[0], args[1] if len(args) == 2 else 0)
        elif kind == "scale" and len(args) in (1, 2):
            current = (args[0], 0, 0, args[-1], 0, 0)
        elif kind == "rotate" and len(args) in (1, 3):
            angle = math.radians(args[0])
            cosine, sine = math.cos(angle), math.sin(angle)
            current = (cosine, sine, -sine, cosine, 0, 0)
            if len(args) == 3:
                x, y = args[1:]
                current = multiply(multiply((1, 0, 0, 1, x, y), current), (1, 0, 0, 1, -x, -y))
        elif kind in ("skewX", "skewY") and len(args) == 1:
            tangent = math.tan(math.radians(args[0]))
            current = (1, 0, tangent, 1, 0, 0) if kind == "skewX" else (1, tangent, 0, 1, 0, 0)
        else:
            raise SvgError(f"Unsupported SVG transform: {kind}")
        result = multiply(result, current)
    return result


def apply(matrix: Matrix, point: Point) -> Point:
    a, b, c, d, e, f = matrix
    x, y = point
    result = a * x + c * y + e, b * x + d * y + f
    if not all(math.isfinite(value) for value in result):
        raise SvgError("SVG drawing exceeds finite coordinates")
    return result


def map_transform(orientation: float) -> str:
    """Rotate the Map into its display orientation, then flip y for SVG.

    Coordinates and physical poses remain local to the Map. This shared outer
    transform turns positive angles counter-clockwise in the displayed image.
    """
    return "scale(1,-1)" + (f" rotate({orientation})" if orientation else "")


def _subpaths(element: ET.Element) -> list[tuple[list[Point], bool]]:
    """Read native vertices while retaining each subpath and its closing join."""
    if element.tag == f"{{{SVG}}}polyline":
        values = numbers(element.get("points", ""))
        if len(values) % 2 or len(values) < 4:
            raise SvgError("SVG drawing has too few vertices or an unmatched coordinate")
        return [(list(zip(values[::2], values[1::2], strict=True)), False)]

    commands = re.split(r"([MLZ])", element.get("d", ""))
    if commands[0].strip() or len(commands) == 1:
        raise SvgError("Expected an absolute M/L/Z SVG path")
    result: list[tuple[list[Point], bool]] = []
    current: list[Point] | None = None
    start: Point | None = None
    vertex_count = 0
    for command, coordinates in zip(commands[1::2], commands[2::2], strict=True):
        values = numbers(coordinates)
        if command == "Z":
            if values or start is None:
                raise SvgError("Invalid closed SVG path")
            if current is not None:
                result.append((current, True))
                current = None
            continue

        if not values or len(values) % 2 or (command == "L" and start is None):
            raise SvgError("Invalid SVG path vertices")
        points = list(zip(values[::2], values[1::2], strict=True))
        vertex_count += len(points)
        if command == "M":
            if current is not None:
                result.append((current, False))
            current = points
            start = points[0]
        else:
            # After Z, SVG resumes a following line at the closed subpath's
            # initial point. It is a new open subpath, with its own end caps.
            if current is None:
                current = [start]
            current.extend(points)
    if current is not None:
        result.append((current, False))
    if vertex_count < 3:
        raise SvgError("SVG drawing has too few vertices or an unmatched coordinate")
    return result


def vertices(element: ET.Element) -> list[Point]:
    """Read generated polylines or absolute M/L/Z paths, including hole rings."""
    return [point for points, _ in _subpaths(element) for point in points]


def href(element: ET.Element) -> str:
    return element.get("href", element.get(f"{{{XLINK}}}href", ""))


def _paint(element: ET.Element, inherited: dict[str, str]) -> dict[str, str]:
    """Resolve presentation values that children inherit and may override."""
    return {
        key: element.get(key, value) if element.get(key) != "inherit" else value
        for key, value in inherited.items()
    }


def _shape_points(element: ET.Element, paint: dict[str, str]) -> Iterator[Point]:
    name = element.tag.rsplit("}", 1)[-1]
    if name in {"polyline", "path"}:
        subpaths = _subpaths(element)
        if paint["fill"] not in {"none", "transparent"} and number(paint["fill-opacity"]) > 0:
            for points, _ in subpaths:
                yield from points
        stroke_width = number(paint["stroke-width"])
        if (
            paint["stroke"] not in {"none", "transparent"}
            and number(paint["stroke-opacity"]) > 0
            and stroke_width > 0
        ):
            for points, closed in subpaths:
                yield from stroke_extrema(
                    {
                        "points": points,
                        "closed": closed,
                        "width": stroke_width,
                        "cap": paint["stroke-linecap"],
                        "join": paint["stroke-linejoin"],
                    }
                )
    elif name in {"image", "rect"}:
        x, y = number(element.get("x", "0")), number(element.get("y", "0"))
        width, height = number(element.get("width", "0")), number(element.get("height", "0"))
        for corner_x in (x, x + width):
            for corner_y in (y, y + height):
                yield corner_x, corner_y


def drawing_bounds(root: ET.Element, *, svg_coordinates: bool = False) -> Bounds | None:
    """Measure painted bounds in Map meters, excluding selection aids.

    @param svg_coordinates Include the outer Map transform for viewport fitting.
        These bounds use displayed SVG coordinates, with y pointing down.
        The default keeps bounds local to the Map for geometry consumers.
    """
    world = root.find(f"{{{SVG}}}g[@id='map']")
    if world is None:
        raise SvgError("SVG has no Map drawing group")
    references = {node.get("id"): node for node in root.iter() if node.get("id")}
    bounds = None

    def visit(
        element: ET.Element,
        matrix: Matrix,
        active: frozenset[str],
        inherited: dict[str, str],
    ) -> None:
        nonlocal bounds
        if (
            element.get("data-purpose") == "selection"
            or element.get("display") == "none"
            or number(element.get("opacity", "1")) == 0
        ):
            return

        local = multiply(matrix, transform(element.get("transform", "")))
        paint = _paint(element, inherited)
        if element.tag == f"{{{SVG}}}use":
            identifier = href(element).removeprefix("#")
            if identifier in active or identifier not in references:
                raise SvgError("Cyclic or missing SVG use reference")
            local = multiply(
                local, (1, 0, 0, 1, number(element.get("x", "0")), number(element.get("y", "0")))
            )
            visit(references[identifier], local, active | {identifier}, paint)
            return

        # Unlike display:none and group opacity, visibility can be restored by
        # a child. Skip hidden paint here, but still visit its descendants.
        if paint["visibility"] not in {"hidden", "collapse"}:
            for point in _shape_points(element, paint):
                x, y = apply(local, point)
                if bounds is None:
                    bounds = x, y, x, y
                else:
                    bounds = (
                        min(bounds[0], x),
                        min(bounds[1], y),
                        max(bounds[2], x),
                        max(bounds[3], y),
                    )
        for child in element:
            visit(child, local, active, paint)

    # Export measures the actual rotated shapes, not a rotated bounding box.
    # Public Map bounds omit the display rotation and SVG's y-axis flip.
    if (
        root.get("display") != "none"
        and number(root.get("opacity", "1")) != 0
        and world.get("display") != "none"
        and number(world.get("opacity", "1")) != 0
    ):
        paint = _paint(world, _paint(root, _PAINT_DEFAULTS))
        matrix = transform(world.get("transform", "")) if svg_coordinates else IDENTITY
        for child in world:
            visit(child, matrix, frozenset(), paint)
    return bounds
