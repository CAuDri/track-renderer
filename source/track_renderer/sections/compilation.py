"""Add each section's reference pose and road surface, then draw its markings.

The compiler registry is the entry point for supported section types. Shared
scene objects are created here so road and intersection compilers focus on paint.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from ..diagnostics import RenderFailure
from ..rendering.records import Pose
from .intersection.compilation import compile_intersection
from .road import compile_road

if TYPE_CHECKING:
    from ..rendering.context import Context

SECTION_COMPILERS = {
    "straight": compile_road,
    "arc": compile_road,
    "clothoid": compile_road,
    "intersection": compile_intersection,
}


def compile_section(ctx: Context, path: str) -> None:
    """@brief Add a positioned section and dispatch its type-specific paint."""
    section = ctx.section(path)
    if section.surface is None:
        raise RenderFailure("Section has no usable road surface")

    ctx.part(
        path,
        "reference",
        Pose(*section.pose[:2], yaw=math.degrees(section.pose[2])),
        properties={
            "anchor": "entry_port",
            "ports": {
                name: {
                    "x": section.port(name)[0],
                    "y": section.port(name)[1],
                    "outward_yaw": math.degrees(section.port(name)[2]),
                }
                for name in section.ports
            },
        },
    )
    ctx.region(
        path,
        "road_surface",
        ctx.model.road_shape(section, ctx.tolerance),
        section.value["road"]["rendering"]["surface_color"],
        layer=0,
    )

    compiler = SECTION_COMPILERS.get(section.value["type"])
    if compiler is None:
        raise RenderFailure(f"Unsupported section type: {section.value['type']}")
    compiler(ctx, section)
