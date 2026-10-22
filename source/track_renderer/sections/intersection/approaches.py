"""Draw centerlines from a junction port up to its stop or give-way edge.

Zone styles are resolved for each directed route visit. Coordinates point out
of the junction, so an arriving vehicle's right side has a positive offset.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from ...diagnostics import RenderFailure
from ...geometry.primitives import add, scale
from ...markings.planning import control_intervals, dashed_intervals
from ...markings.styles import centerline_components as style_components
from ...rendering.records import Pose
from .geometry import Arm, Junction, approach_extent

if TYPE_CHECKING:
    from ...rendering.context import Context


def effective_style(
    ctx: Context, junction: Junction, arm: Arm
) -> tuple[str, bool | None, set[str]]:
    """@return One compatible style and the zones affecting this particular arm."""
    styles = set()
    sources = set()
    for obj, leg in ctx.instances.visits(junction.section.identifier, "centerline", "no_passing"):
        if arm.port not in {leg.incoming, leg.outgoing}:
            continue
        parameters = obj.value["parameters"]
        style = parameters["style"] if obj.kind == "centerline" else parameters["centerline"]
        incoming = leg.incoming == arm.port
        right_dashed = incoming if obj.kind == "centerline" else not incoming
        styles.add((style, right_dashed if style == "mixed" else None))
        sources.add(obj.path)

    if len(styles) > 1:
        raise RenderFailure(f"Conflicting centerline zones at {arm.port}")
    style, right_dashed = next(iter(styles), (arm.road["centerline"], None))
    if style == "mixed" and right_dashed is None:
        raise RenderFailure("Mixed intersection centerline needs a directed zone")
    return style, right_dashed, sources


def centerline_components(
    arm: Arm, style: str, right_dashed: bool | None
) -> list[tuple[float, bool]]:
    """Use the shared style policy in the junction's outward-facing frame."""
    if style not in {"dashed", "solid", "double_solid", "mixed"}:
        raise RenderFailure(f"Unsupported intersection centerline: {style}")
    double_line = style in {"double_solid", "mixed"}
    spacing = arm.road["rendering"]["centerline_double_line_spacing"] if double_line else 0
    return style_components(
        style,
        arm.marking if double_line else 0,
        spacing,
        right_sign=1,
        dashed_side="right" if right_dashed else "left",
    )


def draw_approach(ctx: Context, junction: Junction, arm: Arm) -> None:
    """@brief Draw this arm's share of its road's continuous centerline pattern."""
    section = junction.section
    port_distance = section.value["parameters"]["port_distance"]
    rendering = arm.road["rendering"]
    end = approach_extent(ctx, junction, arm.port)
    pose = Pose(*section.pose[:2], yaw=math.degrees(section.pose[2]))
    run = section.identifier, arm.port
    if run not in ctx.phases:
        raise RenderFailure(f"No usable marking plan for the {arm.port} junction approach")

    style, right_dashed, sources = effective_style(ctx, junction, arm)
    for component, (offset, dashed) in enumerate(centerline_components(arm, style, right_dashed)):
        intervals = (
            dashed_intervals(ctx, section, 0, end, end, rendering, run=run)
            if dashed
            else control_intervals(ctx, section, 0, end, run=run)
        )
        for index, (a, b) in enumerate(intervals):
            points = [
                pose.point(
                    *add(
                        (port_distance, 0),
                        add(scale(arm.u, port_distance - t), scale(arm.n, offset)),
                    )
                )
                for t in (a, b)
            ]
            ctx.path(
                section.path,
                f"centerline/{arm.port}/{component}/{index}",
                points,
                rendering["marking_color"],
                arm.marking,
                layer=20,
                sources=sources,
            )
