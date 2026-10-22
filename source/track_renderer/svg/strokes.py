"""Find the parts of a stroked path that can extend its drawing bounds.

Most strokes fit inside a half-width pad around their vertices; 
square caps and miter tips need extra points so an export does not cut them off at the edge of its viewport.
"""

from collections.abc import Iterator
from math import hypot
from typing import Any

Point = tuple[float, float]

# The renderer does not override SVG's default miter limit. Beyond this ratio of
# miter length to half stroke width, SVG draws a bevel instead of a sharp tip.
SVG_MITER_LIMIT = 4.0


def stroke_extrema(data: dict[str, Any]) -> Iterator[Point]:
    """@brief Yield conservative bounds points for a complete painted path.

    The ordinary half-width padding also covers round caps and bevel/round
    joins. We add only the square-cap corners and visible miter tips that the
    padding can miss. A closed subpath joins its last edge back to its first
    instead of receiving end caps. Measure separate subpaths independently.
    """
    half_width = data["width"] / 2
    points = data["points"]
    closed = data.get("closed", False)
    for x, y in points:
        yield x - half_width, y - half_width
        yield x - half_width, y + half_width
        yield x + half_width, y - half_width
        yield x + half_width, y + half_width

    if data.get("cap", "butt") != "square" and data.get("join", "round") != "miter":
        return

    # Repeated vertices have no direction. Look through them when finding the
    # adjoining tangents, just as SVG does for a zero-length segment.
    vertices = []
    for point in points:
        if not vertices or tuple(point) != tuple(vertices[-1]):
            vertices.append(point)
    if closed and len(vertices) > 1 and vertices[-1] == vertices[0]:
        vertices.pop()
    if len(vertices) < 2:
        return

    tangents = []
    successors = vertices[1:] + (vertices[:1] if closed else [])
    for first, second in zip(vertices, successors, strict=False):
        dx, dy = second[0] - first[0], second[1] - first[1]
        length = hypot(dx, dy)
        tangents.append((dx / length, dy / length))

    if not closed and data.get("cap", "butt") == "square":
        for point, tangent, direction in (
            (vertices[0], tangents[0], -1),
            (vertices[-1], tangents[-1], 1),
        ):
            dx, dy = tangent
            for side in (-1, 1):
                yield (
                    point[0] + half_width * (direction * dx - side * dy),
                    point[1] + half_width * (direction * dy + side * dx),
                )

    if data.get("join", "round") != "miter":
        return

    joins = (
        zip(vertices, tangents[-1:] + tangents[:-1], tangents, strict=True)
        if closed
        else zip(vertices[1:-1], tangents, tangents[1:], strict=False)
    )
    for point, incoming, outgoing in joins:
        cross = incoming[0] * outgoing[1] - incoming[1] * outgoing[0]
        normal_x = -incoming[1] - outgoing[1]
        normal_y = incoming[0] + outgoing[0]
        normal_length = hypot(normal_x, normal_y)
        if not cross or normal_length < 2 / SVG_MITER_LIMIT:
            continue

        # The sum of the two normals points along the corner bisector. Its
        # length gives the miter ratio; the turn direction selects the outer
        # side. The inner intersection does not produce a painted spike.
        side = -1 if cross > 0 else 1
        distance = side * half_width * 2 / (normal_length * normal_length)
        yield point[0] + normal_x * distance, point[1] + normal_y * distance
