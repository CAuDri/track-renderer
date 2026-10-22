"""Resolve placements used by more than one kind of track object.

These helpers turn authored poses, route endpoints and implicit starting lines
into Map positions. They also handle placements that continue onto another road.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from ..diagnostics import RenderFailure
from ..rendering.records import Pose
from .primitives import add, positive, scale, unit

if TYPE_CHECKING:
    from ..description.types import Data, Instance, RouteLeg, Section
    from ..rendering.context import Context


def starting_line_support(ctx: Context, path: str) -> tuple[Section, float, float]:
    """@return The supporting road and the two painted-edge distances along it.

    An implicit line starts at the root port. If that port is an exit, the line
    belongs on its connected successor; paint and centerline gaps use this same
    placement so their edges agree.
    """
    section, value = ctx.section(path), ctx.sources[path]
    start = value["parameters"].get("distance")
    direction = 1

    if start is None:
        root = ctx.track["root"]
        start = section.curve.length if root["port"] == "exit" else 0
        if root["port"] == "exit":
            link = ctx.model.links.get((section.identifier, "exit"))
            if link is None:
                raise RenderFailure("Root starting line needs a connected successor")
            section = ctx.model.sections[link[0]]
            direction = 1 if link[1] == "entry" else -1
            start = 0 if direction == 1 else section.curve.length

    if section.intersection:
        raise RenderFailure("Starting-line support must be a linear section")
    end = start + direction * positive(value["rendering"]["width"])
    if min(start, end) < 0 or max(start, end) > section.curve.length:
        raise RenderFailure("Starting line exceeds its support section")
    return section, start, end


def explicit_pose(ctx: Context, path: str, source: Data, *, height: float = 0) -> Pose:
    """@return A Map pose from explicit coordinates or a section-relative placement."""
    return explicit_placement(ctx, path, source, height=height)[0]


def explicit_placement(
    ctx: Context, path: str, source: Data, *, height: float = 0
) -> tuple[Pose, Section | None]:
    """Resolve a pose and the section reached by a relative placement.

    Carrying a distance through connected roads can change the supporting road
    and its cross-section without changing the object's semantic owner. Absolute
    Map poses have no resolved section; callers can retain their own binding or
    infer one from the position when their geometry requires it.
    """
    if "pose" in source:
        return Pose(**source["pose"]), None

    at = source["at"]
    sid = at.get("section")
    section = ctx.model.sections[sid] if sid else ctx.section(path)
    if section.component != ctx.model.root_component or section.component < 0:
        raise RenderFailure("Placement section is disconnected from the Map root")
    if section.intersection:
        frame = Pose(*section.pose[:2], yaw=math.degrees(section.pose[2]))
        point = frame.point(at["x"], at["y"])
        yaw = section.pose[2]
    else:
        try:
            section, _, point, yaw = ctx.model.locate(section, at["distance"])
        except ValueError as exc:
            raise RenderFailure(str(exc)) from exc
        point = add(point, scale(unit(yaw + math.pi / 2), at.get("offset", 0)))
    pose = Pose(*point, height + at.get("upward_offset", 0), math.degrees(yaw) + at.get("yaw", 0))
    return pose, section


def zone_route(ctx: Context, owner: Instance) -> list[RouteLeg]:
    """@return The zone's route, resolving its range if upstream left it unexpanded."""
    if owner.route:
        return owner.route
    parameters = owner.value["parameters"]
    if "span" in parameters:
        try:
            return ctx.model.resolve_span(parameters["span"], parameters["direction"])
        except ValueError as exc:
            raise RenderFailure(str(exc)) from exc
    section = ctx.model.sections[owner.section]
    start, end = parameters["range"]["start"], parameters["range"]["end"]
    if parameters["direction"] == "backward":
        start, end = end, start
    try:
        return [ctx.model.linear_leg(section, start, end)]
    except ValueError as exc:
        raise RenderFailure(str(exc)) from exc


def zone_endpoint(
    ctx: Context, owner: Instance, begin: bool, *, advance: float = 0, roadside: float | None = None
) -> Pose:
    """@return A pose facing along the zone's travel direction at either endpoint.

    @param advance Move this many meters back along the approach.
    @param roadside Optional clearance beyond the outer painted road edge.
    """
    route = zone_route(ctx, owner)
    if not route:
        raise RenderFailure("Zone endpoint has no resolved path")
    leg = route[0] if begin else route[-1]
    section = ctx.model.sections[leg.section]
    if section.intersection:
        if advance:
            raise RenderFailure("An advanced sign at a junction endpoint needs explicit placement")
        port = leg.incoming if begin else leg.outgoing
        x, y, outward = section.port(port)
        yaw = outward + (math.pi if begin else 0)
        arm = ctx.model.arm(section, port)
        offset = -(arm["half"] + roadside) if roadside is not None else -arm["inner"] / 2
        return Pose(*add((x, y), scale(unit(yaw + math.pi / 2), offset)), yaw=math.degrees(yaw))

    direction = 1 if leg.end > leg.start else -1
    station = leg.start if begin else leg.end
    station -= direction * advance
    try:
        placed, _, point, yaw = ctx.model.locate(section, station)
    except ValueError as exc:
        raise RenderFailure(str(exc)) from exc
    yaw += math.pi if direction == -1 else 0
    offset = (
        -(placed.half + roadside)
        if roadside is not None
        else -(placed.marking / 2 + placed.width / 2)
    )
    point = add(point, scale(unit(yaw + math.pi / 2), offset))
    return Pose(*point, yaw=math.degrees(yaw))
