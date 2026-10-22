"""Draw outer junction boundaries and apply each arm's missing-marking zones.

Corners connect neighboring sides; the closed side of a T-junction may instead
use a smooth taper. Tapers with changing paint width are drawn as filled bands.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from shapely.geometry import LineString

from ...markings.visibility import junction_missing
from ...rendering.records import Pose
from .geometry import Boundary, Junction, sample_transition

if TYPE_CHECKING:
    from ...rendering.context import Context


def draw_boundary(ctx: Context, junction: Junction, boundary: Boundary) -> None:
    """@brief Draw the unmasked sides and their shared corner connector."""
    section = junction.section
    first = junction_missing(ctx, section, boundary.first, 1)
    second = junction_missing(ctx, section, boundary.second, -1)
    if boundary.transition is not None:
        _transition_boundary(ctx, junction, boundary, first, second)
        return

    pieces = []
    if not first and not second:
        pieces.append([boundary.start, *boundary.connector_points, boundary.end])
    else:
        # The shared arc belongs to both adjacent sides. Its deletion must not
        # remove the straight segment of an unvisited neighboring arm.
        if not first:
            pieces.append([boundary.start, boundary.connector_points[0]])
        if not second:
            pieces.append([boundary.connector_points[-1], boundary.end])

    pose = Pose(*section.pose[:2], yaw=math.degrees(section.pose[2]))
    for index, points in enumerate(pieces):
        if LineString(points).length <= 1e-12:
            continue
        role = f"boundary/{boundary.first}/{boundary.second}"
        if index:
            role += f"/{index}"
        ctx.path(
            section.path,
            role,
            [pose.point(*point) for point in points],
            section.value["road"]["rendering"]["marking_color"],
            boundary.width,
            join="miter" if section.value["parameters"]["corner_radius"] == 0 else "round",
            layer=20,
            sources=first | second,
        )


def _transition_boundary(
    ctx: Context,
    junction: Junction,
    boundary: Boundary,
    first: frozenset[str],
    second: frozenset[str],
) -> None:
    """Retain each arm's half of the taper when its neighbor is masked."""
    if first and second:
        return

    start, end = (0.5 if first else 0.0), (0.5 if second else 1.0)
    transition = boundary.transition
    section = junction.section
    pose = Pose(*section.pose[:2], yaw=math.degrees(section.pose[2]))
    role = f"boundary/{boundary.first}/{boundary.second}"
    color = section.value["road"]["rendering"]["marking_color"]
    if transition.start_width == transition.end_width:
        points = sample_transition(transition, ctx.tolerance, start=start, end=end)
        ctx.path(
            section.path,
            role,
            [pose.point(*point) for point in points],
            color,
            boundary.width,
            layer=20,
            sources=first | second,
        )
    else:
        # A filled band also follows both attached roads when their paint widths differ.
        outside = sample_transition(transition, ctx.tolerance, side=1, start=start, end=end)
        inside = sample_transition(transition, ctx.tolerance, side=-1, start=start, end=end)
        ctx.region(
            section.path,
            role,
            [pose.point(*point) for point in [*outside, *reversed(inside)]],
            color,
            layer=20,
            sources=first | second,
        )
