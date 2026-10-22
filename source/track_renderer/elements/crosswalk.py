"""Draw zebra stripes and retain the waiting areas on either side of a road.

The stripe field is centered between the inner road markings. Waiting areas use
left and right relative to the crosswalk's travel direction, and keep their
physical poses even when their dashed projections are disabled.
"""

import math

from ..description.types import Data, Instance, Point, Section
from ..diagnostics import RenderFailure
from ..geometry.directions import lateral_sign
from ..geometry.primitives import positive, stroke_intervals
from ..rendering.context import Context
from ..rendering.records import Pose


def compile_crosswalk(ctx: Context, path: str) -> None:
    """@brief Draw the paint, then add waiting-area bodies and optional outlines."""
    section = ctx.section(path)
    instance = ctx.model.by_path[path]
    value = ctx.sources[path]
    parameters, rendering = value["parameters"], value["rendering"]
    if section.value["type"] != "straight":
        raise RenderFailure("Crosswalks require straight sections")

    _draw_stripes(ctx, path, section, instance, rendering)
    _add_waiting_areas(ctx, path, section, instance, parameters, rendering)


def _draw_stripes(
    ctx: Context, path: str, section: Section, instance: Instance, rendering: Data
) -> None:
    """Fit whole stripes across the road and share the leftover margin equally."""
    stripe = positive(rendering["stripe_width"])
    gap = positive(rendering["stripe_gap"])
    count = math.floor((2 * section.inner + gap) / (stripe + gap))
    if count <= 0 or count > 100000:
        raise RenderFailure("Crosswalk has an unusable stripe count")

    occupied = count * stripe + (count - 1) * gap
    color = section.value["road"]["rendering"]["marking_color"]
    for index in range(count):
        lateral = -occupied / 2 + index * (stripe + gap)
        ctx.region(
            path,
            f"stripe/{index}",
            [
                section.point(station, offset)
                for station, offset in (
                    (instance.start, lateral),
                    (instance.end, lateral),
                    (instance.end, lateral + stripe),
                    (instance.start, lateral + stripe),
                )
            ],
            color,
        )


def _add_waiting_areas(
    ctx: Context,
    path: str,
    section: Section,
    instance: Instance,
    parameters: Data,
    rendering: Data,
) -> None:
    """Place each waiting-area body before considering its optional drawing."""
    length = parameters["waiting_area_longitudinal_extent"]
    depth = parameters["waiting_area_lateral_extent"]
    middle = (instance.start + instance.end) / 2
    for side in parameters["waiting_area_sides"]:
        sign = lateral_sign(side, parameters["direction"])
        center = section.point(middle, sign * (section.boundary + depth / 2))
        part = ctx.part(
            path,
            "waiting_area/" + side,
            Pose(*center, yaw=math.degrees(section.yaw(middle))),
            {"length": length, "width": depth},
            {"side": side},
        )
        if not ctx.options.project("crosswalk_waiting_area"):
            continue

        start, end = middle - length / 2, middle + length / 2
        points = [
            section.point(station, sign * lateral)
            for station, lateral in (
                (start, section.boundary),
                (start, section.boundary + depth),
                (end, section.boundary + depth),
                (end, section.boundary),
            )
        ]
        _draw_waiting_outline(ctx, path, side, points, part, rendering)


def _draw_waiting_outline(
    ctx: Context, path: str, side: str, points: list[Point], part: str, rendering: Data
) -> None:
    """Dash three edges, leaving the road-facing side open for pedestrians."""
    for edge, (start, end) in enumerate(zip(points, points[1:], strict=False)):
        distance = math.dist(start, end)
        stroke = rendering["waiting_area_dash_length"]
        gap = rendering["waiting_area_dash_gap"]
        for index, (low, high) in enumerate(stroke_intervals(0, distance, stroke, gap, phase=gap)):
            vertices = [
                (
                    start[0] + (end[0] - start[0]) * station / distance,
                    start[1] + (end[1] - start[1]) * station / distance,
                )
                for station in (low, high)
            ]
            ctx.path(
                path,
                f"waiting/{side}/{edge}/{index}",
                vertices,
                rendering["waiting_area_color"],
                rendering["waiting_area_outline_width"],
                part=part,
                purpose="projection",
            )
