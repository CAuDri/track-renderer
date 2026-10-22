"""Place and draw stop lines, give-way lines, arrows and speed-limit markings.

Generated junction controls follow the prepared approach geometry. Other markings
use an explicit pose or a zone endpoint. Line paint is built directly; arrows and
numbers use artwork embedded in the scene at the requested physical size.
"""

from ..description.types import Data, Instance
from ..diagnostics import RenderFailure
from ..geometry.placement import explicit_pose, zone_endpoint
from ..geometry.primitives import positive, rectangle, stroke_intervals
from ..rendering.context import Context
from ..rendering.records import Pose
from ..sections.intersection.controls import approach_pose, control_marking
from ..sections.intersection.geometry import Junction


def compile_surface_marking(ctx: Context, path: str) -> None:
    """@brief Resolve placement, then draw either control-line paint or artwork."""
    value = ctx.sources[path]
    parameters, rendering = value["parameters"], value["rendering"]
    instance = ctx.model.by_path[path]
    marking = parameters["marking"]
    implicit = "pose" not in value and "at" not in value
    owner = instance.owner
    junction = None
    if implicit and owner and owner.kind == "section" and owner.section in ctx.junctions:
        junction = ctx.junctions[owner.section]
        port = instance.slot.split("_", 1)[0]
        if marking in {"stop_line", "give_way_line"}:
            control_marking(ctx, path, junction, port)
            return

    pose = _marking_pose(ctx, path, value, instance, junction)
    if marking in {"stop_line", "give_way_line"}:
        _draw_placed_control(ctx, path, pose, value, marking)
    else:
        _draw_artwork(ctx, path, pose, value, rendering, marking)


def _marking_pose(
    ctx: Context, path: str, value: Data, instance: Instance, junction: Junction | None
) -> Pose:
    """Place artwork on an approach, at a zone endpoint or at its authored pose."""
    owner = instance.owner
    implicit = "pose" not in value and "at" not in value
    if junction is not None:
        port = instance.slot.split("_", 1)[0]
        arm = junction.arms[port]
        offset = (arm.marking / 2 + arm.inner) / 2
        arrow_length = value.get("size", {}).get("length", value["rendering"]["length"])
        return approach_pose(
            ctx,
            junction,
            port,
            junction.section.value["parameters"]["mandatory_marking_distance"] + arrow_length / 2,
            offset,
        )

    if implicit and owner and owner.kind in {"speed_limit", "no_passing", "expressway"}:
        return zone_endpoint(ctx, owner, instance.slot.startswith("begin"))
    return explicit_pose(ctx, path, value)


def _draw_placed_control(ctx: Context, path: str, pose: Pose, value: Data, marking: str) -> None:
    """Draw a transverse control line whose position is already resolved."""
    # Absolute global markings have no road owner. Missing dimensions and paint
    # color use the same track-wide defaults that sections inherit.
    has_section = ctx.drawing.objects[path].section_id or value.get("at", {}).get("section")
    road = ctx.section(path).value["road"] if has_section else ctx.track["road"]
    rendering = value["rendering"]
    size = value.get("size", {})
    length = positive(size.get("length", rendering["width"]), "control-line length")
    width = positive(size.get("width", road["lane_width"]), "control-line width")
    color = road["rendering"]["marking_color"]
    if marking == "stop_line":
        ctx.region(path, "line", rectangle(pose, length, width), color)
        return

    for index, (start, end) in enumerate(
        stroke_intervals(
            -width / 2,
            width / 2,
            rendering["stroke_length"],
            rendering["gap_length"],
            phase=rendering["gap_length"] + width / 2,
        )
    ):
        ctx.region(
            path,
            f"dash/{index}",
            [
                pose.point(x, y)
                for x, y in (
                    (-length / 2, start),
                    (length / 2, start),
                    (length / 2, end),
                    (-length / 2, end),
                )
            ],
            color,
        )


def _draw_artwork(
    ctx: Context, path: str, pose: Pose, value: Data, rendering: Data, marking: str
) -> None:
    """Keep the marking's physical dimensions and attach its SVG drawing."""
    if marking == "mandatory_direction":
        length, width = rendering["length"], rendering["width"]
    elif marking == "speed_limit_begin":
        length, width = rendering["digit_height"], rendering["total_width"]
    elif marking == "speed_limit_end":
        length, width = rendering["total_height"], rendering["total_width"]
    else:
        raise RenderFailure(f"Unknown surface-marking variant: {marking}")

    size = value.get("size", {})
    length, width = size.get("length", length), size.get("width", width)
    part = ctx.part(
        path, "marking", pose, {"length": length, "width": width}, {"asset": rendering["asset"]}
    )
    ctx.symbol(
        path,
        "artwork",
        pose,
        rendering["asset"],
        length,
        width,
        part=part,
        purpose="physical",
        layer=35,
    )
