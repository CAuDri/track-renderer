"""Place landmark panels beside the road and attach their QR artwork.

A landmark can have a panel on either or both sides. Physical panel placement
is resolved first, so both panels remain available if artwork is hidden or its
generation fails during forced rendering.
"""

from dataclasses import replace

from shapely.geometry import Point

from ..assets.landmark_artwork import landmark_asset
from ..diagnostics import RenderFailure
from ..geometry.placement import explicit_placement
from ..rendering.context import Context


def compile_landmark(ctx: Context, path: str) -> None:
    """@brief Resolve the road cross-section, then add each panel and its drawing."""
    value = ctx.sources[path]
    parameters, rendering = value["parameters"], value["rendering"]
    anchor, section = explicit_placement(
        ctx, path, value, height=parameters["lower_edge_height"] + rendering["sign_height"] / 2
    )
    if section is None:
        try:
            section = ctx.section(path)
        except RenderFailure:
            # An absolute root-level pose can use a unique containing road. Multiple
            # candidates or an off-road anchor require explicit section binding.
            candidates = [
                s
                for s in ctx.model.sections.values()
                if s.component == ctx.model.root_component
                and s.surface is not None
                and s.surface.covers(Point(anchor.x, anchor.y))
                and not s.intersection
            ]
            if len(candidates) != 1:
                raise RenderFailure(
                    "Landmark pose has no unique road cross-section; use at.section"
                ) from None
            section = candidates[0]

    panels = []
    for side in parameters["sign_sides"]:
        sign = 1 if side == "left" else -1
        point = anchor.point(
            0, sign * (section.half + parameters["lateral_offset"] + rendering["sign_width"] / 2)
        )
        pose = replace(
            anchor,
            x=point[0],
            y=point[1],
            yaw=anchor.yaw + (180 if parameters["faces"][side] == "backward" else 0),
        )
        part = ctx.part(
            path,
            "panel/" + side,
            pose,
            {"width": rendering["sign_width"], "height": rendering["sign_height"]},
            {"side": side, "faces": parameters["faces"][side], "asset": rendering["asset"]},
        )
        panels.append((side, pose, part))

    if ctx.options.project("landmark"):
        # Retain both physical poses even if artwork generation fails in force mode.
        asset = landmark_asset(ctx, value)
        for side, pose, part in panels:
            ctx.symbol(
                path,
                "symbol/" + side,
                pose,
                asset,
                rendering["sign_height"],
                rendering["sign_width"],
                part=part,
            )
