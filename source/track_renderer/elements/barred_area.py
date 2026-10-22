"""Draw a barred-area outline and clip diagonal paint bands inside it.

Construction happens in the straight road's station/offset coordinates before
points are mapped into the scene. The configured hatch gap is free distance
along the road, so it must be converted to spacing normal to the diagonal bands.
"""

import math

from shapely.geometry import Polygon

from ..diagnostics import RenderFailure
from ..geometry.primitives import positive
from ..rendering.context import Context


def compile_barred(ctx: Context, path: str) -> None:
    """@brief Draw the outline and fill its interior with evenly spaced hatch bands."""
    section, value = ctx.section(path), ctx.sources[path]
    if section.value["type"] != "straight":
        raise RenderFailure("Barred areas require straight sections")

    parameters, rendering = value["parameters"], value["rendering"]
    start, end = parameters["range"]["start"], parameters["range"]["end"]
    sign = -1 if parameters["direction"] == "forward" else 1
    depth = positive(parameters["lateral_extent"])
    angle = math.radians(parameters["outline_side_angle"])
    if not 0 < angle < math.pi / 2:
        raise RenderFailure("Barred-area side angle must be between zero and 90 degrees")
    run = depth / math.tan(angle)
    if 2 * run >= end - start:
        raise RenderFailure("Barred area is too short for its sloped ends")

    outer, inner = sign * section.inner, sign * (section.inner - depth)
    polygon = Polygon([(start, outer), (start + run, inner), (end - run, inner), (end, outer)])
    color = section.value["road"]["rendering"]["marking_color"]
    points = [section.point(s, y) for s, y in polygon.exterior.coords]
    ctx.path(path, "outline", points, color, rendering["outline_width"])
    interior = polygon.buffer(-rendering["outline_width"] / 2, join_style="mitre")
    if interior.is_empty:
        raise RenderFailure("Barred-area outline leaves no hatch interior")

    angle = math.radians(rendering["hatch_angle"])
    direction = (math.cos(angle), -sign * math.sin(angle))
    normal = (-direction[1], direction[0])
    width = positive(rendering["hatch_width"])
    gap = positive(rendering["hatch_longitudinal_gap"])
    # A gap measured along the road projects onto the band normal by |normal.x|.
    # Add the paint width there so the requested free gap stays between bands.
    step = width + gap * abs(normal[0])
    projections = [s * normal[0] + y * normal[1] for s, y in polygon.exterior.coords]
    low, high = min(projections) + step, max(projections)
    reach = 2 * (abs(start) + abs(end) + section.half + depth + 1)
    count = math.ceil((high - low) / step)
    if count > 100000:
        raise RenderFailure("Barred-area hatch count exceeds 100000")

    for i in range(max(0, count)):
        center = low + i * step
        band = Polygon(
            [
                (normal[0] * v + direction[0] * u, normal[1] * v + direction[1] * u)
                for u, v in (
                    (-reach, center - width / 2),
                    (reach, center - width / 2),
                    (reach, center + width / 2),
                    (-reach, center + width / 2),
                )
            ]
        )

        clipped = band.intersection(interior)
        if clipped.is_empty or clipped.area <= 1e-14:
            continue
        ctx.region(
            path, f"hatch/{i}", [section.point(s, y) for s, y in clipped.exterior.coords], color
        )
