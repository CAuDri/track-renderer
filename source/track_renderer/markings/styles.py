"""Turn a centerline style into one or two painted strokes.

Roads and junction approaches use opposite lateral directions. Callers supply
the sign of their right side explicitly; this also keeps component order stable.
"""

from __future__ import annotations

from typing import Literal

from ..diagnostics import RenderFailure


def centerline_components(
    style: str,
    marking_width: float,
    spacing: float,
    *,
    right_sign: Literal[-1, 1],
    dashed_side: Literal["left", "right"] | None = None,
) -> list[tuple[float, bool]]:
    """@return Lateral offsets and dash choices, with the right stroke first.

    @param right_sign -1 on a forward road; +1 in an outward-facing junction arm.
    @param dashed_side Which travel-relative side is dashed for a mixed line.
    """
    if style in {"dashed", "solid"}:
        return [(0.0, style == "dashed")]

    if style not in {"double_solid", "mixed"}:
        raise RenderFailure(f"Unsupported centerline style: {style}")

    offset = right_sign * (marking_width + spacing) / 2
    return [
        (offset, style == "mixed" and dashed_side == "right"),
        (-offset, style == "mixed" and dashed_side == "left"),
    ]
