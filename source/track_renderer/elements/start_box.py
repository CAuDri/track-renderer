"""Join a straight starting bay to the outside of a left root arc.

The bay follows the arc's exit tangent. Its inner edge meets the curved road
boundary, or the bay's rear edge cuts that curve when the bay is shorter. Find
that join first, then draw the boundary and the extra road surface around it.
"""

import math

from ..description.types import Point, Section
from ..diagnostics import RenderFailure
from ..geometry.primitives import positive, sample
from ..rendering.context import Context
from ..rendering.records import Pose


def compile_start_box(ctx: Context, path: str) -> None:
    """@brief Add the start bay's boundary paint and extra road surface."""
    section, value = ctx.section(path), ctx.sources[path]
    if section.value["type"] != "arc" or section.curve.k0 <= 0:
        raise RenderFailure("Start-box construction needs a left root arc")

    end = section.curve.length
    pose = Pose(*section.point(end), yaw=math.degrees(section.yaw(end)))
    boundary = section.width + section.marking
    length = positive(value["parameters"]["length"])
    join, back_inner, inner_end = _start_box_join(section, pose, boundary, length)
    back_outer = pose.point(-length, -boundary)

    color = section.value["road"]["rendering"]["marking_color"]
    if inner_end is not None:
        ctx.path(path, "inner_boundary", [back_inner, inner_end], color, section.marking)
    ctx.path(path, "rear_boundary", [back_inner, back_outer], color, section.marking)
    ctx.path(path, "outer_boundary", [back_outer, pose.point(0, -boundary)], color, section.marking)

    surface = [back_inner] + sample(section, join, end, -boundary, ctx.tolerance) + [back_outer]
    ctx.region(
        path, "surface", surface, section.value["road"]["rendering"]["surface_color"], layer=0
    )


def _start_box_join(
    section: Section, pose: Pose, boundary: float, length: float
) -> tuple[float, Point, Point | None]:
    """Find the curve station and the bay's rear inner corner in Map coordinates.

    The optional third point ends the straight inner boundary. A short bay meets
    the curve at its rear instead and has no separate inner boundary to draw.
    """
    end = section.curve.length
    yaw = section.yaw(end)
    inner = -section.marking / 2

    def local(station: float) -> Point:
        # In the exit-tangent frame the bay is axis-aligned: its rear is x=-length
        # and its inner edge is y=inner. This turns each join into a 1D search.
        point = section.point(station, -boundary)
        x, y = point[0] - pose.x, point[1] - pose.y
        return x * math.cos(yaw) + y * math.sin(yaw), -x * math.sin(yaw) + y * math.cos(yaw)

    # Walk backward to bracket the closest crossing with the inner edge. A long
    # arc can cross the same line more than once, so the choice of crossing matters.
    previous = end
    bracket = None
    for index in range(1, 513):
        current = end * (1 - index / 512)
        if local(current)[1] >= inner and local(previous)[1] < inner:
            bracket = current, previous
            break
        previous = current
    if bracket is None:
        raise RenderFailure("Start bay does not meet the root's outer boundary")

    low, high = bracket
    for _ in range(60):
        middle = (low + high) / 2
        if local(middle)[1] >= inner:
            low = middle
        else:
            high = middle
    join = (low + high) / 2
    join_point = local(join)
    if join_point[0] > -length:
        return join, pose.point(-length, inner), pose.point(*join_point)

    # The inner-edge crossing lies behind this bay. Clip the curved boundary at
    # the rear line x=-length instead; its intersection becomes the rear corner.
    low, high = join, end
    for _ in range(60):
        middle = (low + high) / 2
        if local(middle)[0] < -length:
            low = middle
        else:
            high = middle
    join = (low + high) / 2
    return join, section.point(join, -boundary), None
