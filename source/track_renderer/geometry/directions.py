"""Convert travel-relative sides into section-local lateral directions."""

from typing import Literal


def lateral_sign(side: Literal["left", "right"], direction: Literal["forward", "backward"]) -> int:
    """@return +1 for section-left and -1 for section-right, accounting for travel."""
    sign = {"left": 1, "right": -1}[side]
    return sign if direction == "forward" else -sign
