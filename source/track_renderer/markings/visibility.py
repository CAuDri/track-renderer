"""Remove paint covered by missing-marking zones.

Road marking names use the section's own left and right. At intersections they
follow each directed route visit, so the entry and exit arms use opposite signs.
Mandatory-turn guidance deliberately stays outside this masking policy.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..description.types import Section
    from ..rendering.context import Context


def subtract_intervals(
    start: float, end: float, gaps: Iterable[tuple[float, float]]
) -> list[tuple[float, float]]:
    """@return Ordered visible intervals after subtracting possibly overlapping gaps."""
    result = []
    for low, high in sorted(gaps):
        if low >= end:
            break
        if high <= start:
            continue
        if low > start:
            result.append((start, low))
        start = max(start, high)
    if start < end:
        result.append((start, end))
    return result


def missing_intervals(ctx: Context, section: Section, role: str) -> list[tuple[float, float]]:
    """@return Missing intervals; ordinary-section roles stay section-local."""
    return [
        tuple(sorted((leg.start, leg.end)))
        for obj, leg in ctx.instances.visits(section.identifier, "missing_marking")
        if role in obj.value["parameters"]["markings"]
    ]


def visible_marking_intervals(
    ctx: Context, section: Section, role: str, start: float, end: float
) -> list[tuple[float, float]]:
    """@return Unmasked portions of an ordinary section's named marking."""
    return subtract_intervals(start, end, missing_intervals(ctx, section, role))


def junction_missing(ctx: Context, section: Section, port: str, side: int = 0) -> frozenset[str]:
    """@return Zones hiding an approach centerline or outward-frame boundary side.

    A zero side selects the centerline; +1/-1 select positive/negative outward
    lateral offsets. At junctions, left/right follow each zone's directed visit.
    Mandatory-turn guidance deliberately does not call this policy.
    """
    sources = set()
    for obj, leg in ctx.instances.visits(section.identifier, "missing_marking"):
        if port not in (leg.incoming, leg.outgoing):
            continue
        markings = obj.value["parameters"]["markings"]
        if side == 0:
            role = "centerline"
        else:
            travel_left = -1 if port == leg.incoming else 1
            role = "left_boundary" if side == travel_left else "right_boundary"
        if role in markings:
            sources.add(obj.path)
    return frozenset(sources)
