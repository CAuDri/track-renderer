"""Draw the center and outer guidance lines through a mandatory turn.

These lines intentionally remain visible inside missing-marking zones. When a
turn meets a tapered T-junction edge, its outer arc is fitted to that actual edge.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from shapely.geometry import LineString
from shapely.ops import substring

from ...diagnostics import RenderFailure
from ...geometry.primitives import add, cross, scale, stroke_intervals
from ...markings.planning import control_intervals, dashed_intervals
from ...rendering.records import Pose
from .approaches import centerline_components, effective_style
from .geometry import Arm, Junction, sample_corner_arc, sample_transition

if TYPE_CHECKING:
    from ...description.types import Point
    from ...rendering.context import Context


def draw_mandatory_centerline(ctx: Context, junction: Junction, ports: list[str]) -> None:
    """@brief Continue the incoming road's centerline through the required turn."""
    section = junction.section
    first, second = (junction.arms[p] for p in ports)
    style = effective_style(ctx, junction, first)
    opposite_style = effective_style(ctx, junction, second)
    if style[0] != opposite_style[0]:
        raise RenderFailure("Mandatory-turn approaches have incompatible centerline styles")
    leg = ctx.model.junction_leg(section, *ports)
    rendering = first.road["rendering"]

    for component, (offset, dashed) in enumerate(centerline_components(first, *style[:2])):
        line = leg.line.offset_curve(-offset, quad_segs=32) if offset else leg.line
        if not isinstance(line, LineString) or line.is_empty:
            raise RenderFailure("Mandatory-turn offset is not a continuous line")
        intervals = (
            dashed_intervals(ctx, section, 0, leg.length, leg.length, rendering)
            if dashed
            else control_intervals(ctx, section, 0, leg.length)
        )
        for index, (a, b) in enumerate(intervals):
            segment = substring(line, a / leg.length, b / leg.length, normalized=True)
            ctx.path(
                section.path,
                f"centerline/turn/{component}/{index}",
                segment.coords,
                rendering["marking_color"],
                first.marking,
                layer=20,
                sources=style[2] | opposite_style[2],
            )


def _mandatory_transition(
    ctx: Context, junction: Junction, first: Arm, second: Arm, radius: float
) -> list[Point] | None:
    """Join turn guidance tangentially to the closed-side taper, when present."""
    boundary = next(
        (
            b
            for b in junction.boundaries
            if b.transition is not None and (b.second == first.port or b.first == second.port)
        ),
        None,
    )
    if boundary is None:
        return None
    if junction.arms[boundary.first].boundary == junction.arms[boundary.second].boundary:
        return None

    transition = boundary.transition
    closed_first = boundary.second == first.port
    branch = second if closed_first else first
    side = 1 if closed_first else -1
    d = junction.section.value["parameters"]["port_distance"]
    low, high = (0.5, 1.0) if closed_first else (0.0, 0.5)

    def center_at(t: float) -> Point:
        return add(transition.point(t), scale(transition.normal(t), -radius))

    def residual(t: float) -> float:
        center = add(center_at(t), (-d, 0))
        return sum(a * b for a, b in zip(center, branch.n, strict=True)) - side * (
            branch.boundary - radius
        )

    left, right = residual(low), residual(high)
    if left * right > 0:
        raise RenderFailure("Mandatory-turn guide cannot meet the taper; increase port_distance")

    # Moving along the taper gives candidate circle centers one radius away.
    # Find the center whose distance to the branch edge is also that radius;
    # the resulting circle is tangent to both without a kink in the guide line.
    for _ in range(60):
        middle = (low + high) / 2
        value = residual(middle)
        if value == 0:
            low = high = middle
            break
        if left * value <= 0:
            high = middle
        else:
            low, left = middle, value

    t = (low + high) / 2
    center, curve_point = center_at(t), transition.point(t)
    branch_point = add(center, scale(branch.n, side * radius))
    relative = add(branch_point, (-d, 0))
    station = sum(a * b for a, b in zip(relative, branch.u, strict=True))
    if station >= d:
        raise RenderFailure("Intersection port_distance is too short for its outer turn line")
    branch_port = add(add((d, 0), scale(branch.u, d)), scale(branch.n, side * branch.boundary))
    start, end = (curve_point, branch_point) if closed_first else (branch_point, curve_point)
    start_angle = math.atan2(start[1] - center[1], start[0] - center[0])
    end_angle = math.atan2(end[1] - center[1], end[0] - center[0])
    sweep = -((start_angle - end_angle) % math.tau)
    if not -math.pi < sweep < 0:
        raise RenderFailure("Mandatory-turn guide has no usable tangent arc at the taper")

    arc = sample_corner_arc(center, start, sweep, radius, ctx.tolerance)
    if closed_first:
        approach = sample_transition(transition, ctx.tolerance, start=1, end=t)
        return [*approach, *arc, branch_port]
    approach = sample_transition(transition, ctx.tolerance, start=t, end=0)
    return [branch_port, *arc, *approach]


def draw_mandatory_boundary(ctx: Context, junction: Junction, ports: list[str]) -> None:
    """@brief Continue the turn's outside boundary across the other approaches.

    Construct both tangencies explicitly: different approach widths cannot be
    represented by a constant offset of the turn's centerline.
    """
    section = junction.section
    first, second = (junction.arms[p] for p in ports)
    delta = (second.angle - first.angle) % math.tau
    reverse = delta > math.pi
    if reverse:
        first, second, delta = second, first, math.tau - delta

    d = section.value["parameters"]["port_distance"]
    radius = section.value["parameters"]["corner_radius"] + first.boundary + second.boundary
    a = add((d, 0), scale(first.n, -first.boundary))
    b = add((d, 0), scale(second.n, second.boundary))
    points = _mandatory_transition(ctx, junction, first, second, radius)
    if points is not None:
        length = LineString(points).length
    else:
        difference = add(b, scale(a, -1))
        denominator = cross(first.u, second.u)
        advance = radius / math.tan(delta / 2)
        first_station = cross(difference, second.u) / denominator + advance
        second_station = cross(difference, first.u) / denominator + advance
        if max(first_station, second_station) >= d:
            raise RenderFailure("Intersection port_distance is too short for its outer turn line")

        tangent = add(a, scale(first.u, first_station))
        arc = sample_corner_arc(
            add(tangent, scale(first.n, radius)), tangent, -(math.pi - delta), radius, ctx.tolerance
        )
        points = [add(a, scale(first.u, d)), *arc, add(b, scale(second.u, d))]
        length = 2 * d - first_station - second_station + radius * (math.pi - delta)

    pose = Pose(*section.pose[:2], yaw=math.degrees(section.pose[2]))
    line = LineString([pose.point(*point) for point in points])
    center = ctx.model.junction_leg(section, *ports)
    if line.distance(center.line) <= max(first.marking, second.marking):
        raise RenderFailure("Mandatory-turn center and outer line overlap")

    phase, direction = ctx.phases[section.identifier]

    # Anchor the outer pattern at a canonical end of the centerline. Its longer
    # arc must not shift the pattern when the same pair of ports is reordered.
    if reverse:
        phase, direction = phase + direction * center.length, -direction
    rendering = first.road["rendering"]
    for index, (start, end) in enumerate(
        stroke_intervals(
            0,
            length,
            rendering["centerline_dashed_stroke_length"],
            rendering["centerline_dashed_gap_length"],
            phase,
            direction,
            rendering["centerline_minimum_terminal_stroke_ratio"],
        )
    ):
        segment = substring(line, start / length, end / length, normalized=True)
        ctx.path(
            section.path,
            f"turn_boundary/{index}",
            segment.coords,
            rendering["marking_color"],
            first.marking,
            layer=20,
        )
