"""Draw road markings after splitting the road at every relevant zone boundary.

The resulting intervals have one effective centerline style and a set of hidden
markings. Side-road openings are then left to their element's own paint compiler.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from itertools import groupby
from typing import TYPE_CHECKING, Literal

from ..geometry.directions import lateral_sign
from ..geometry.primitives import sample
from .planning import dashed_intervals
from .styles import centerline_components
from .visibility import subtract_intervals

if TYPE_CHECKING:
    from ..description.types import Section
    from ..rendering.context import Context


@dataclass(frozen=True)
class MarkingState:
    """@brief Effective style over one non-overlapping section interval."""

    start: float
    end: float
    centerline: str
    dashed_side: Literal["left", "right"] | None
    missing: frozenset[str]
    zone_sources: frozenset[str]
    centerline_span: tuple[float, float]


def states(ctx: Context, section: Section) -> list[MarkingState]:
    """@return Intervals with a single style and the zones that contributed to it.

    Overlapping zones may agree, but conflicting centerline styles are diagnosed
    instead of letting the order of the source objects choose the winner.
    """
    length = section.curve.length
    effects = []
    cuts = {0.0, length}
    for obj, leg in ctx.instances.visits(
        section.identifier, "centerline", "missing_marking", "no_passing"
    ):
        start, end = sorted((leg.start, leg.end))
        start, end = max(0.0, start), min(length, end)
        if end > start:
            effects.append((start, end, obj, leg.end > leg.start))
            cuts.update((start, end))

    gaps = []
    phase, direction = ctx.phases[section.identifier]
    for low, high in ctx.dash_chains[section.identifier].gaps:
        start, end = sorted(((low - phase) / direction, (high - phase) / direction))
        start, end = max(0.0, start), min(length, end)
        if end > start:
            gaps.append((start, end))
            cuts.update((start, end))

    result = []
    values = sorted(cuts)
    for start, end in zip(values, values[1:], strict=False):
        middle = (start + end) / 2
        centerlines, missing, owners = set(), set(), set()
        for a, b, obj, forward in effects:
            if not a <= middle < b:
                continue
            parameters = obj.value["parameters"]
            owners.add(obj.path)
            if obj.kind == "missing_marking":
                # Marking roles are section-local even for backward zones.
                missing.update(parameters["markings"])
            else:
                style = (
                    parameters["style"] if obj.kind == "centerline" else parameters["centerline"]
                )
                side = None
                if style == "mixed":
                    dashed_right = forward if obj.kind == "centerline" else not forward
                    side = "right" if dashed_right else "left"
                centerlines.add((style, side))

        if len(centerlines) > 1:
            ctx.issue(
                section.path,
                f"Conflicting centerline zones over [{start:g}, {end:g}]",
                "render.zone_conflict",
            )
            missing.add("centerline")
            style, side = section.value["road"]["centerline"], None
        else:
            style, side = next(iter(centerlines), (section.value["road"]["centerline"], None))

        if any(a <= middle < b for a, b in gaps):
            missing.add("centerline")
        if style == "mixed" and side is None:
            ctx.issue(section.path, "A mixed centerline needs a zone specifying its direction")
            missing.add("centerline")
        result.append(
            MarkingState(
                start, end, style, side, frozenset(missing), frozenset(owners), (start, end)
            )
        )

    # Boundary masks and provenance can split drawing ownership without cutting
    # the centerline. Measure terminal strokes over its complete effective style.
    joined = []
    for _, group in groupby(
        result,
        key=lambda state: (state.centerline, state.dashed_side, "centerline" in state.missing),
    ):
        members = list(group)
        span = members[0].start, members[-1].end
        joined.extend(replace(state, centerline_span=span) for state in members)
    return joined


def centerline(ctx: Context, section: Section, state: MarkingState, index: int) -> None:
    """@brief Draw one interval using its resolved style and continuous dash plan."""
    if "centerline" in state.missing:
        return
    road, start, end = section.value["road"], state.start, state.end
    rendering = road["rendering"]
    double_line = state.centerline in {"double_solid", "mixed"}
    components = centerline_components(
        state.centerline,
        road["marking_width"] if double_line else 0,
        rendering["centerline_double_line_spacing"] if double_line else 0,
        right_sign=-1,
        dashed_side=state.dashed_side,
    )

    for component, (offset, dashed) in enumerate(components):
        intervals = (
            dashed_intervals(
                ctx,
                section,
                start,
                end,
                section.curve.length,
                rendering,
                style_span=state.centerline_span,
            )
            if dashed
            else [(start, end)]
        )
        for stroke, (a, b) in enumerate(intervals):
            ctx.path(
                section.path,
                f"centerline/{index}/{component}/{stroke}",
                sample(section, a, b, offset, ctx.tolerance),
                rendering["marking_color"],
                road["marking_width"],
                layer=20,
                sources=state.zone_sources,
            )


def boundary(ctx: Context, section: Section, state: MarkingState, index: int, side: str) -> None:
    """@brief Leave the side-road intervals to their semantic element's compiler."""
    role = side + "_boundary"
    if role in state.missing:
        return
    sign = lateral_sign(side, "forward")
    openings = []
    for obj in ctx.instances.owned(section.identifier, "side_road_junction"):
        parameters = obj.value["parameters"]
        if lateral_sign(parameters["side"], parameters["direction"]) != sign or obj.start is None:
            continue
        openings.append((obj.start, obj.end))

    intervals = subtract_intervals(state.start, state.end, openings)
    for piece, (start, end) in enumerate(intervals):
        ctx.path(
            section.path,
            f"{role}/{index}/{piece}",
            sample(section, start, end, sign * (section.width + section.marking), ctx.tolerance),
            section.value["road"]["rendering"]["marking_color"],
            section.marking,
            layer=20,
        )
