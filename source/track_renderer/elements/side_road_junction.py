"""Draw the dashed road edge where a side road meets a section.

The element owns this replacement paint. Its side follows the element's travel
direction, and missing-marking zones can hide pieces just as they do on the
ordinary section boundary.
"""

from ..geometry.directions import lateral_sign
from ..geometry.primitives import sample, stroke_intervals
from ..markings.visibility import visible_marking_intervals
from ..rendering.context import Context


def compile_side_road(ctx: Context, path: str) -> None:
    """@brief Replace the chosen outer-boundary interval with visible dash pieces."""
    section = ctx.section(path)
    instance, value = ctx.model.by_path[path], ctx.sources[path]
    parameters, rendering = value["parameters"], value["rendering"]
    sign = lateral_sign(parameters["side"], parameters["direction"])
    role = "left_boundary" if sign == 1 else "right_boundary"

    for i, (start, end) in enumerate(
        stroke_intervals(
            instance.start,
            instance.end,
            rendering["stroke_length"],
            rendering["gap_length"],
            phase=rendering["gap_length"] - instance.start,
        )
    ):
        intervals = visible_marking_intervals(ctx, section, role, start, end)
        for fragment, (low, high) in enumerate(intervals):
            ctx.path(
                path,
                f"boundary/{i}" + (f"/{fragment}" if len(intervals) > 1 else ""),
                sample(section, low, high, sign * section.boundary, ctx.tolerance),
                section.value["road"]["rendering"]["marking_color"],
                section.marking,
                layer=20,
            )
