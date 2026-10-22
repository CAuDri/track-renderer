"""Place static obstacles, artifacts and custom markers in the scene.

Bodies retain their authored dimensions even when their projections are hidden.
Artwork is used when supplied; otherwise a sized object gets a simple footprint.
"""

import math

from ..assets import embed_asset
from ..assets.dimensions import intrinsic_dimensions
from ..diagnostics import RenderFailure
from ..geometry.placement import explicit_pose
from ..geometry.primitives import rectangle
from ..rendering.context import Context
from ..rendering.records import Pose


def compile_object(ctx: Context, path: str) -> None:
    """@brief Add the object's body, then its optional footprint or artwork."""
    value = ctx.sources[path]
    kind = value["type"]
    pose = (
        obstacle_pose(ctx, path)
        if kind == "static_obstacle"
        else explicit_pose(ctx, path, value, height=value.get("size", {}).get("height", 0) / 2)
    )
    size = value.get("size", {})
    part = ctx.part(path, "body", pose, size)

    if not ctx.options.project(kind):
        return

    asset = value.get("rendering", {}).get("asset")
    if asset:
        length, width = size.get("length"), size.get("width")
        if length is None or width is None:
            if kind != "custom_marker" or size:
                raise RenderFailure("Artwork requires explicit size.length and size.width")
            asset = embed_asset(ctx.drawing, asset)
            length, width = intrinsic_dimensions(ctx.drawing.assets[asset]["content"])
        ctx.symbol(path, "artwork", pose, asset, length, width, part=part)
    elif size:
        ctx.region(
            path,
            "footprint",
            rectangle(pose, size["length"], size["width"]),
            "#FFFFFF" if kind == "static_obstacle" else "#AA55CC",
            part=part,
            layer=50,
            purpose="projection",
        )


def obstacle_pose(ctx: Context, path: str) -> Pose:
    """@return The obstacle center, including placement inherited from a parking spot."""
    value = ctx.sources[path]
    height = value.get("size", {}).get("height", 0) / 2
    if "pose" in value or "at" in value:
        return explicit_pose(ctx, path, value, height=height)

    instance = ctx.model.by_path[path]
    if instance.position is None:
        raise RenderFailure("Obstacle has no resolved position")
    ctx.section(path)
    return Pose(*instance.position, height, math.degrees(instance.yaw))
