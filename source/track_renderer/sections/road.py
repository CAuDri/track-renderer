"""Draw the same lane-marking rules on straight, arc and clothoid roads.

Zone boundaries split the road into intervals. Sampling the section's reference
curve then gives each interval its own centerline and outer-boundary geometry.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..markings.drawing import boundary, centerline, states

if TYPE_CHECKING:
    from ..description.types import Section
    from ..rendering.context import Context


def compile_road(ctx: Context, section: Section) -> None:
    """@brief Draw the effective centerline and both road edges for each interval."""
    for index, state in enumerate(states(ctx, section)):
        centerline(ctx, section, state, index)
        for side in ("left", "right"):
            boundary(ctx, section, state, index, side)
