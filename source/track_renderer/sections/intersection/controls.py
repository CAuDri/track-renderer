"""Draw generated stop and give-way lines against the real junction boundary.

Outlines and dash cuts are built in an outward-facing arm frame, where the first
coordinate runs along the arm. Only the finished paint is moved into Map space.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from shapely.geometry import Polygon, box
from shapely.geometry.base import BaseGeometry

from ...diagnostics import RenderFailure
from ...geometry.primitives import add, scale, stroke_intervals
from ...rendering.records import Pose
from .geometry import (
    Arm,
    Control,
    Junction,
    control_approach_edge,
    sample_corner_arc,
    sample_transition,
)

if TYPE_CHECKING:
    from ...rendering.context import Context


def _control_polygons(shape: BaseGeometry) -> Iterator[Polygon]:
    """Yield positive-area components, omitting clipping contacts without area."""
    if isinstance(shape, Polygon):
        if not shape.is_empty and shape.area > 1e-14:
            yield shape
    elif hasattr(shape, "geoms"):
        for part in shape.geoms:
            yield from _control_polygons(part)


@dataclass(frozen=True)
class _PaintOutline:
    """Control paint in the arm frame, before individual give-way strokes are cut."""

    shape: Polygon
    start: float
    end: float
    tangent_lateral: float | None = None


def _control_outline(control: Control, arm: Arm, width: float, tolerance: float) -> _PaintOutline:
    """Follow the corner's approach edge, continuing along its tangent if needed."""
    start = -arm.marking / 2
    end = control.lateral
    limit = control.lateral_limit if control.lateral_limit is not None else end + arm.marking / 2
    if control.circle is None:
        return _PaintOutline(
            box(control.station, start, control.station + width, limit), start, limit
        )

    station, lateral, radius = control.circle
    finish = control.station + width
    extends_past_corner = finish > station
    arc_end = min(finish, station)
    delta = arc_end - station
    back = (arc_end, lateral - math.sqrt(max(0, radius * radius - delta * delta)))
    front = (control.station, end)
    first_angle = math.atan2(front[1] - lateral, front[0] - station)
    last_angle = math.atan2(back[1] - lateral, back[0] - station)
    arc = sample_corner_arc(
        (station, lateral), front, (last_angle - first_angle) % math.tau, radius, tolerance
    )

    # Use only the approach-side quarter-circle. Continuing around a small
    # corner would fold the cap back into the paint and split give-way strokes.
    tangent_lateral = None
    if extends_past_corner:
        arc[0], arc[-1] = front, back
        tangent_lateral = lateral - radius
    points = [(control.station, start), *arc]
    if extends_past_corner:
        points.append((finish, tangent_lateral))
    shape = Polygon([*points, (finish, start)])
    return _PaintOutline(shape, start, limit, tangent_lateral)


def _clip_to_taper(
    ctx: Context, junction: Junction, port: str, width: float, outline: _PaintOutline
) -> _PaintOutline:
    """Use the actual painted taper edge when opposite arms have different widths."""
    transition = next(
        (b.transition for b in junction.boundaries if b.first == port and b.transition is not None),
        None,
    )
    if transition is None:
        return outline

    arm, control = junction.arms[port], junction.controls[port]
    port_distance = junction.section.value["parameters"]["port_distance"]
    edge = []
    for x, y in sample_transition(transition, ctx.tolerance):
        relative = (x - port_distance, y)
        edge.append(
            (
                sum(a * b for a, b in zip(relative, arm.u, strict=True)),
                sum(a * b for a, b in zip(relative, arm.n, strict=True)),
            )
        )

    envelope = Polygon([*edge, (-port_distance, outline.start), (port_distance, outline.start)])
    shape = envelope.intersection(
        box(control.station, outline.start, control.station + width, max(y for _, y in edge))
    )
    if shape.is_empty or not isinstance(shape, Polygon) or shape.area <= 0:
        raise RenderFailure("Control line does not meet its junction boundary")
    return replace(outline, shape=shape, end=shape.bounds[3])


def _draw_control_strokes(
    ctx: Context,
    path: str,
    junction: Junction,
    port: str,
    width: float,
    outline: _PaintOutline,
    intervals: Iterable[tuple[float, float]],
) -> None:
    """Cut solid or dashed strips from the outline, then place them in the Map."""
    section, arm = junction.section, junction.arms[port]
    control = junction.controls[port]
    pose = Pose(*section.pose[:2], yaw=math.degrees(section.pose[2]))
    port_distance = section.value["parameters"]["port_distance"]

    for index, (start, end) in enumerate(intervals):
        if outline.tangent_lateral is not None:
            # Snap a dash edge that almost meets the tangent. Without this,
            # roundoff can turn a zero-width extension into a rotated spike.
            tangent = outline.tangent_lateral
            start, end = (tangent if abs(edge - tangent) < 1e-12 else edge for edge in (start, end))
        clipped = outline.shape.intersection(
            box(control.station - 1, start, control.station + width + 1, end)
        )
        for part_index, polygon in enumerate(_control_polygons(clipped)):
            points = [
                pose.point(
                    *add((port_distance, 0), add(scale(arm.u, station), scale(arm.n, lateral)))
                )
                for station, lateral in polygon.exterior.coords
            ]
            role = f"control/{index}" + (f"/{part_index}" if part_index else "")
            ctx.region(path, role, points, arm.road["rendering"]["marking_color"])


def control_marking(ctx: Context, path: str, junction: Junction, port: str) -> None:
    """@brief Add a stop or give-way line that meets the adjoining corner or taper."""
    value = ctx.sources[path]
    parameters, rendering = value["parameters"], value["rendering"]
    width = rendering["width"]

    outline = _control_outline(junction.controls[port], junction.arms[port], width, ctx.tolerance)
    outline = _clip_to_taper(ctx, junction, port, width, outline)
    intervals = [(outline.start, outline.end)]
    if parameters["marking"] == "give_way_line":
        intervals = stroke_intervals(
            outline.start,
            outline.end,
            rendering["stroke_length"],
            rendering["gap_length"],
            phase=rendering["gap_length"] - outline.start,
        )

    _draw_control_strokes(ctx, path, junction, port, width, outline, intervals)


def approach_pose(
    ctx: Context, junction: Junction, port: str, advance: float, lateral: float
) -> Pose:
    """@return An inbound pose measured from the nearest control-paint edge."""
    arm, section = junction.arms[port], junction.section
    port_distance = section.value["parameters"]["port_distance"]
    center = add(
        (port_distance, 0),
        add(
            scale(arm.u, control_approach_edge(ctx, junction, port) + advance),
            scale(arm.n, lateral),
        ),
    )
    frame = Pose(*section.pose[:2], yaw=math.degrees(section.pose[2]))
    return Pose(*frame.point(*center), yaw=math.degrees(section.pose[2] + arm.angle + math.pi))
