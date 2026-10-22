"""Draw solid or checkered starting lines on their resolved road support.

An implicit line at the root's exit can belong geometrically to the next section.
The placement helper resolves that support and direction; cell edges are then
sampled along it so the paint follows straight roads, arcs and clothoids alike.
"""

import math

from ..diagnostics import RenderFailure
from ..geometry.placement import starting_line_support
from ..geometry.primitives import positive, sample
from ..rendering.context import Context


def compile_starting_line(ctx: Context, path: str) -> None:
    """@brief Add the full stripe or the painted cells of a checker pattern."""
    section, start, end = starting_line_support(ctx, path)
    value = ctx.sources[path]
    parameters, rendering = value["parameters"], value["rendering"]
    width, direction = rendering["width"], 1 if end > start else -1
    color = section.value["road"]["rendering"]["marking_color"]

    def cell(role: str, a: float, b: float, left: float, right: float) -> None:
        begin, end = start + direction * a, start + direction * b
        outline = sample(section, begin, end, left, ctx.tolerance)
        outline += sample(section, end, begin, right, ctx.tolerance)
        ctx.region(path, role, outline, color)

    if parameters["pattern"] == "solid":
        cell("solid", 0, width, -section.inner, section.inner)
        return
    if parameters["pattern"] != "checkered":
        raise RenderFailure(f"Unknown starting-line pattern: {parameters['pattern']}")

    size = positive(rendering["checker_size"])
    rows, columns = math.ceil(width / size), math.ceil(2 * section.inner / size)
    if rows * columns > 100000:
        raise RenderFailure("Starting-line checker count exceeds 100000")

    for row in range(rows):
        for column in range(columns):
            if (row + column) % 2:
                continue
            cell(
                f"checker/{row}/{column}",
                row * size,
                min(width, (row + 1) * size),
                -section.inner + column * size,
                min(section.inner, -section.inner + (column + 1) * size),
            )
