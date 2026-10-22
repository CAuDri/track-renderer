"""Small geometric building blocks shared by the drawing compilers.

Distances are in meters and angles are in radians unless a Pose supplies its
own frame. Sampling and dash helpers keep the original curve and pattern sizes.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from typing import TYPE_CHECKING

from ..diagnostics import RenderFailure
from ..rendering.records import Point, Pose

if TYPE_CHECKING:
    from ..description.types import Section


def positive(value: float, name: str = "dimension") -> float:
    """@return A usable positive dimension, or raise a rendering failure."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RenderFailure(f"{name} must be numeric")
    if not math.isfinite(value) or value <= 0:
        raise RenderFailure(f"{name} must be finite and positive")
    return float(value)


def rectangle(pose: Pose, length: float, width: float) -> list[Point]:
    """@return The four corners of a rectangle centered on the given pose."""
    positive(length)
    positive(width)
    return [
        pose.point(x, y)
        for x, y in (
            (-length / 2, -width / 2),
            (length / 2, -width / 2),
            (length / 2, width / 2),
            (-length / 2, width / 2),
        )
    ]


def stroke_intervals(
    start: float,
    end: float,
    stroke: float,
    gap: float,
    phase: float = 0,
    direction: float = 1,
    minimum: float = 0,
) -> Iterator[tuple[float, float]]:
    """@brief Fit a repeating gap-then-stroke pattern into the requested interval.

    The pattern keeps its original stroke and gap lengths. Only strokes at the
    ends are shortened, and very small terminal pieces can be left out.

    @param phase Pattern coordinate at section distance zero.
    @param direction Sign of increasing pattern coordinate along the section.
    @param minimum Minimum retained terminal fraction of one full stroke.
    """
    positive(stroke, "stroke length")
    positive(gap, "gap length")
    if direction not in (-1, 1):
        raise RenderFailure("Pattern direction must be +1 or -1")

    period = stroke + gap
    low, high = sorted((phase + direction * start, phase + direction * end))
    first, last = math.floor((low - gap) / period), math.floor((high - gap) / period)
    if last - first > 100000:
        raise RenderFailure("Dash pattern exceeds 100000 strokes")

    for index in range(first, last + 1):
        a, b = max(low, index * period + gap), min(high, (index + 1) * period)
        if b - a <= max(1e-12, minimum * stroke - 1e-12):
            continue
        yield tuple(sorted(((a - phase) / direction, (b - phase) / direction)))


def sample(
    section: Section, start: float, end: float, offset: float, tolerance: float
) -> list[Point]:
    """@return Curve points whose straight segments stay within the given tolerance."""
    return [section.point(s, offset) for s in section.curve.stations(tolerance, offset, start, end)]


def cross(a: Point, b: Point) -> float:
    """@return Signed two-dimensional cross product."""
    return a[0] * b[1] - a[1] * b[0]


def add(a: Point, b: Point) -> Point:
    return a[0] + b[0], a[1] + b[1]


def scale(a: Point, factor: float) -> Point:
    return a[0] * factor, a[1] * factor


def unit(angle: float) -> Point:
    return math.cos(angle), math.sin(angle)
