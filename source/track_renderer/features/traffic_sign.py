"""Place traffic-sign panels and add their optional artwork.

Explicit placements use the authored pose; most generated placements come from
the validated model. Grade warning signs additionally walk back along the road
to honor their advance distance, stopping before an intersection is crossed.
"""

from __future__ import annotations

import math
from dataclasses import replace

from ..description.types import Instance
from ..diagnostics import RenderFailure
from ..geometry.placement import explicit_pose, zone_route
from ..geometry.primitives import add, scale, unit
from ..rendering.context import Context
from ..rendering.records import Pose


def compile_traffic_sign(ctx: Context, path: str) -> None:
    """@brief Add a sign's panel and, when enabled, its plan-view drawing."""
    value = ctx.sources[path]
    parameters, rendering = value["parameters"], value["rendering"]
    variants = ctx.prepared.bundle.catalog("features/$defs/traffic_sign").value["x-caudri"][
        "variants"
    ]
    variant = variants[parameters["sign"]]
    width, height = ctx.model.sign_panel_size(value)
    pose = sign_pose(ctx, path, width, height)
    if pose is None:
        return

    part = ctx.part(
        path,
        "panel",
        pose,
        {"width": width, "height": height},
        {"asset": rendering["asset"], "shape": variant["shape"], "faces": parameters["faces"]},
    )

    if ctx.options.project("traffic_sign"):
        ctx.symbol(path, "symbol", pose, rendering["asset"], height, width, part=part)


def sign_pose(ctx: Context, path: str, panel_width: float, panel_height: float) -> Pose | None:
    """@return The panel center, or None when a grade warning would cross a junction."""
    value = ctx.sources[path]
    parameters = value["parameters"]
    z = parameters["lower_edge_height"] + panel_height / 2
    if "pose" in value or "at" in value:
        pose = explicit_pose(ctx, path, value, height=z)
        return replace(pose, yaw=pose.yaw + (180 if parameters["faces"] == "backward" else 0))

    instance = ctx.model.by_path[path]
    if instance.owner and instance.owner.kind == "grade":
        center_offset = parameters["lateral_offset"] + panel_width / 2
        owner = instance.owner
        grade_parameters = owner.value["parameters"]
        if grade_parameters["grade_percent"] == 0:
            raise RenderFailure("A zero-grade zone has no uphill/downhill approach")
        positive = instance.slot == "positive_warning_sign"
        begin = positive == (grade_parameters["grade_percent"] > 0)
        pose = _grade_approach(ctx, path, owner, begin, center_offset)
        if pose is None:
            return None
        return replace(pose, z=z, yaw=pose.yaw + (180 if parameters["faces"] == "backward" else 0))

    if instance.position is None:
        raise RenderFailure("Generated sign has no resolved placement")
    if instance.placed_section:
        section = ctx.model.sections[instance.placed_section]
        if section.component != ctx.model.root_component or section.component < 0:
            raise RenderFailure("Sign belongs to an unanchored component")
    return Pose(*instance.position, z, math.degrees(instance.yaw))


def _grade_approach(
    ctx: Context, path: str, owner: Instance, begin: bool, roadside: float
) -> Pose | None:
    """Walk outward from a grade endpoint, omitting a sign before crossing a junction.

    Check each traversed section: a final linear-section pose alone cannot tell
    whether the advance has already passed through an intersection.
    """
    route = zone_route(ctx, owner)
    if not route:
        raise RenderFailure("Grade endpoint has no resolved path")

    leg = route[0] if begin else route[-1]
    section = ctx.model.sections[leg.section]
    advance = owner.value["parameters"]["warning_sign_advance"]
    if not math.isfinite(advance) or advance < 0:
        raise RenderFailure("Grade warning-sign advance must be finite and nonnegative")

    remaining = advance
    if section.intersection:
        # A zone can end at a junction port. Its sign approaches that port from
        # the attached road; leaving this endpoint does not traverse the junction.
        port = leg.incoming if begin else leg.outgoing
    else:
        station = leg.start if begin else leg.end
        outward = -1 if leg.end > leg.start else 1
        if not begin:
            outward = -outward

    for _ in range(10000):
        if section.component != ctx.model.root_component or section.component < 0:
            raise RenderFailure("Grade sign belongs to an unanchored component")
        if not section.intersection:
            available = station if outward < 0 else section.curve.length - station
            if remaining <= available:
                station += outward * remaining
                yaw = section.yaw(station) + (math.pi if outward > 0 else 0)
                point = add(
                    section.point(station),
                    scale(unit(yaw - math.pi / 2), section.half + roadside),
                )
                return Pose(*point, yaw=math.degrees(yaw))
            remaining -= available
            port = "entry" if outward < 0 else "exit"

        link = ctx.model.links.get((section.identifier, port))
        if link is None:
            raise RenderFailure(f"Grade sign extends past open port {section.identifier}.{port}")
        section = ctx.model.sections[link[0]]
        if section.intersection:
            ctx.issue(
                path,
                f"Automatic grade sign omitted: its {advance:g} m advance reaches or crosses "
                f"intersection {section.identifier!r}.",
                "render.sign_omitted_at_junction",
                severity="warning",
                details={
                    "zone_id": owner.path,
                    "intersection_id": section.path,
                    "warning_sign_advance": advance,
                },
            )
            return None
        outward = 1 if link[1] == "entry" else -1
        station = 0 if outward > 0 else section.curve.length
    raise RenderFailure("Grade sign advance exceeds 10000 section transitions")
