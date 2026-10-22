"""Coordinate the separate paint compilers for a prepared intersection.

Outer boundaries are drawn first, followed by ordinary approaches and any
mandatory-turn guidance. Geometry preparation also runs earlier for dash planning.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .approaches import draw_approach
from .boundaries import draw_boundary
from .geometry import prepare_junction
from .mandatory_turn import draw_mandatory_boundary, draw_mandatory_centerline

if TYPE_CHECKING:
    from ...description.types import Section
    from ...rendering.context import Context


def compile_intersection(ctx: Context, section: Section) -> None:
    """@brief Draw the junction using its shared corner and control-edge geometry."""
    junction = ctx.junctions.get(section.identifier) or prepare_junction(ctx, section)
    for boundary in junction.boundaries:
        draw_boundary(ctx, junction, boundary)

    mandatory = section.value["parameters"].get("mandatory_turn", [])
    for arm in junction.arms.values():
        if arm.port not in mandatory:
            ctx.attempt(section.path, lambda arm=arm: draw_approach(ctx, junction, arm))

    if mandatory:
        # Turn guidance, including its centerline, is exempt from missing-marking zones.
        ctx.attempt(section.path, lambda: draw_mandatory_centerline(ctx, junction, mandatory))
        ctx.attempt(section.path, lambda: draw_mandatory_boundary(ctx, junction, mandatory))
