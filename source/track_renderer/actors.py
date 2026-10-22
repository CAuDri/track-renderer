"""Turn actor descriptions into physical bodies and optional 2D drawings.

This module resolves starting positions only. Pedestrians without an explicit
spawn start in their crosswalk's waiting area. Movement is handled elsewhere.
"""

import math
from dataclasses import replace

from .diagnostics import RenderFailure
from .geometry.directions import lateral_sign
from .geometry.placement import explicit_pose
from .geometry.primitives import rectangle
from .rendering.context import Context
from .rendering.pointers import pointer
from .rendering.records import Pose


def compile_actor(ctx: Context, path: str) -> None:
    """@brief Add an actor at its starting position.

    The body keeps its position and size even when projections are turned off.
    Only the optional footprint or pedestrian symbol is skipped.
    """
    value = ctx.sources[path]
    kind = value["type"]
    pose = actor_pose(ctx, path)
    size = value.get("size", {})
    part = ctx.part(path, "body", pose, size)

    if not ctx.options.project(kind):
        return

    if kind == "dynamic_obstacle":
        ctx.region(
            path,
            "footprint",
            rectangle(pose, size["length"], size["width"]),
            "#FFFFFF",
            part=part,
            layer=50,
            purpose="projection",
        )
    elif kind == "pedestrian":
        rendering = value["rendering"]
        ctx.symbol(
            path,
            "symbol",
            replace(pose, pitch=0, roll=0),
            rendering["asset"],
            rendering["box_height"],
            rendering["box_width"],
            part=part,
        )
    else:
        raise RenderFailure(f"Unknown actor type: {kind}")


def actor_pose(ctx: Context, path: str) -> Pose:
    """@return The authored spawn pose, or a pedestrian's crosswalk waiting pose."""
    value = ctx.sources[path]
    spawn = value.get("spawn")
    if spawn:
        pose = explicit_pose(ctx, path, spawn, height=value.get("size", {}).get("height", 0) / 2)
        if "at" in spawn and spawn.get("direction") == "backward":
            pose = replace(pose, yaw=pose.yaw + 180)
        return pose

    if value["type"] != "pedestrian":
        raise RenderFailure("Actor needs an explicit spawn")

    section_id, element_id = value["parameters"]["crosswalk"].split(".")
    crossing_path = pointer(pointer("/sections", section_id) + "/elements", element_id)
    crossing = ctx.model.by_path[crossing_path]
    section = ctx.section(crossing_path)
    direction = value["simulation"]["behavior"]["parameters"]["direction"]
    side = "left" if direction == "left_to_right" else "right"
    parameters = crossing.value["parameters"]
    if side not in parameters["waiting_area_sides"]:
        raise RenderFailure(
            "Pedestrian spawn requires an enabled waiting area on its approach side"
        )

    # The waiting side follows the crosswalk's travel direction. Face across the
    # road toward the opposite waiting area rather than along the section tangent.
    sign = lateral_sign(side, parameters["direction"])
    station = (crossing.start + crossing.end) / 2
    offset = sign * (section.boundary + parameters["waiting_area_lateral_extent"] / 2)
    point = section.point(station, offset)
    return Pose(
        *point,
        value.get("size", {}).get("height", 0) / 2,
        math.degrees(section.yaw(station) - sign * math.pi / 2),
    )
