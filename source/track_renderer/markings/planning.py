"""Plan continuous dashes before individual sections draw their pieces of paint.

Each connected chain uses one shared coordinate: ``phase + direction * station``
maps a section-local distance onto that chain. This lets a dash continue across
section boundaries and makes nearby control markings cut the same stroke.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..diagnostics import RenderFailure
from ..geometry.placement import starting_line_support
from ..geometry.primitives import stroke_intervals
from ..sections.intersection.geometry import approach_extent, prepare_junction
from .visibility import junction_missing, missing_intervals, subtract_intervals

if TYPE_CHECKING:
    from ..description.types import Data, Section
    from ..rendering.context import Context

MarkingRun = str | tuple[str, str]
RunEndpoint = tuple[MarkingRun, int]


@dataclass
class DashChain:
    """@brief A continuous paint domain, ending at open ports or junction controls."""

    start: float
    end: float
    closed: bool
    gaps: list[tuple[float, float]] = field(default_factory=list)


@dataclass(frozen=True)
class Run:
    """@brief A section or junction approach, with at most two connectable endpoints."""

    length: float
    section: str
    ports: tuple[str | None, str | None]


def build_phases(ctx: Context) -> None:
    """@brief Build shared dash coordinates, then collect every gap in the paint.

    An ordinary junction contributes independent terminal approach runs. Their
    physical control edges end each chain; section ports only partition ownership.
    """
    runs = _collect_runs(ctx)
    endpoints, links = _connect_runs(ctx, runs)
    _assign_chain_coordinates(ctx, runs, endpoints, links)
    _build_gaps(ctx, runs)


def _collect_runs(ctx: Context) -> dict[MarkingRun, Run]:
    """Collect ordinary roads, mandatory turns and terminal junction approaches."""
    runs: dict[MarkingRun, Run] = {}
    for sid, section in ctx.model.sections.items():
        if not section.intersection:
            runs[sid] = Run(section.curve.length, sid, ("entry", "exit"))
            continue
        ctx.attempt(section.path, lambda section=section: prepare_junction(ctx, section))
        junction = ctx.junctions.get(sid)
        if junction is None:
            continue
        turn = section.value["parameters"].get("mandatory_turn", [])
        if turn:
            try:
                leg = ctx.model.junction_leg(section, *turn)
                runs[sid] = Run(leg.length, sid, tuple(turn))
            except ValueError as exc:
                ctx.issue(section.path, str(exc))
            except (KeyError, TypeError) as exc:
                if ctx.prepared.valid:
                    raise
                ctx.issue(section.path, str(exc))
        for port in section.ports:
            if port not in turn:
                try:
                    extent = approach_extent(ctx, junction, port)
                except RenderFailure as exc:
                    ctx.issue(section.path, str(exc))
                    continue
                runs[sid, port] = Run(extent, sid, (port, None))
    return runs


def _connect_runs(
    ctx: Context, runs: dict[MarkingRun, Run]
) -> tuple[dict[tuple[str, str], RunEndpoint], dict[RunEndpoint, RunEndpoint]]:
    """Translate section-port connections into pairs of marking-run endpoints."""
    endpoints = {
        (run.section, port): (key, index)
        for key, run in runs.items()
        for index, port in enumerate(run.ports)
        if port is not None
    }
    links = {}
    for endpoint, (key, index) in endpoints.items():
        link = ctx.model.links.get(endpoint)
        if link and tuple(link[:2]) in endpoints:
            links[key, index] = endpoints[tuple(link[:2])]
    return endpoints, links


def _assign_chain_coordinates(
    ctx: Context,
    runs: dict[MarkingRun, Run],
    endpoints: dict[tuple[str, str], RunEndpoint],
    links: dict[RunEndpoint, RunEndpoint],
) -> None:
    """Anchor the root chain first, then give every remaining chain a stable origin."""
    root = ctx.track["root"]
    root_endpoint = endpoints.get((root["section"], root["port"]))
    seeds = [root_endpoint[0]] if root_endpoint else []
    seeds += sorted(
        set(runs) - set(seeds), key=lambda key: (key, "") if isinstance(key, str) else key
    )
    for seed in seeds:
        if seed in ctx.phases:
            continue
        origin = root_endpoint[1] if root_endpoint and seed == root_endpoint[0] else 0
        members = _propagate_coordinates(ctx, runs, links, seed, origin)
        closed = _close_loop(ctx, runs, links, seed, origin)
        coordinates = [
            ctx.phases[key][0] + ctx.phases[key][1] * station
            for key in members
            for station in (0, runs[key].length)
        ]
        chain = DashChain(min(coordinates), max(coordinates), closed)
        ctx.dash_chains.update({key: chain for key in members})


def _propagate_coordinates(
    ctx: Context,
    runs: dict[MarkingRun, Run],
    links: dict[RunEndpoint, RunEndpoint],
    seed: MarkingRun,
    origin: int,
) -> list[MarkingRun]:
    """Walk connected runs, keeping the shared coordinate equal at each join."""
    ctx.phases[seed] = (-origin * runs[seed].length, 1)
    queue, members = deque([seed]), []

    while queue:
        key = queue.popleft()
        members.append(key)
        phase, direction = ctx.phases[key]
        for index in (0, 1):
            link = links.get((key, index))
            if link is None or link[0] in ctx.phases:
                continue

            other, other_index = link
            # Joining two entries or two exits reverses the local direction.
            other_direction = direction if index != other_index else -direction
            value = phase + direction * index * runs[key].length
            ctx.phases[other] = (
                value - other_direction * other_index * runs[other].length,
                other_direction,
            )
            queue.append(other)

    return members


def _close_loop(
    ctx: Context,
    runs: dict[MarkingRun, Run],
    links: dict[RunEndpoint, RunEndpoint],
    seed: MarkingRun,
    origin: int,
) -> bool:
    """Unroll a closed component once, with its deliberate seam at the root port."""
    current, entry = seed, 0
    if origin:
        link = links.get((seed, origin))
        if link is None:
            return False
        current, entry = link
    start = current, entry
    phases, distance = {}, 0.0
    while current not in phases:
        direction = 1 if entry == 0 else -1
        length = runs[current].length
        phases[current] = (distance - direction * entry * length, direction)
        distance += length
        link = links.get((current, 1 - entry))
        if link is None:
            return False
        current, entry = link
    if (current, entry) != start:
        return False
    ctx.phases.update(phases)
    return True


def _add_gap(ctx: Context, key: MarkingRun, start: float, end: float) -> None:
    """Place a local gap on its chain, wrapping it across a closed loop's seam."""
    phase, direction = ctx.phases[key]
    chain = ctx.dash_chains[key]
    low, high = sorted((phase + direction * start, phase + direction * end))
    if chain.closed:
        span, width = chain.end - chain.start, high - low
        if width >= span:
            low, high = chain.start, chain.end
        else:
            low = chain.start + (low - chain.start) % span
            high = low + width
            if high > chain.end:
                chain.gaps.append((chain.start, chain.start + high - chain.end))
    chain.gaps.append((max(chain.start, low), min(chain.end, high)))


def _build_gaps(ctx: Context, runs: dict[MarkingRun, Run]) -> None:
    """Collect paint, clearances and missing intervals before any owner draws."""
    for key, run in runs.items():
        section = ctx.model.sections[run.section]
        if isinstance(key, tuple):
            port = key[1]
            arm = ctx.junctions[run.section].arms[port]
            gap = arm.road["rendering"]["centerline_control_gap"]
            _add_gap(ctx, key, run.length - gap, run.length)
            if junction_missing(ctx, section, port):
                _add_gap(ctx, key, 0, run.length)
        elif not section.intersection:
            for start, end in missing_intervals(ctx, section, "centerline"):
                _add_gap(ctx, key, start, end)

    for obj in ctx.instances.kinds("crosswalk", "starting_line"):
        try:
            if obj.kind == "starting_line":
                section, start, end = starting_line_support(ctx, obj.path)
            else:
                section = ctx.model.sections[obj.section]
                start, end = obj.start, obj.end
            gap = section.value["road"]["rendering"]["centerline_control_gap"]
            _add_gap(ctx, section.identifier, min(start, end) - gap, max(start, end) + gap)
        except RenderFailure:
            # Its compiler diagnoses unusable placement during forced rendering.
            continue
        except (KeyError, TypeError, ValueError):
            if ctx.prepared.valid:
                raise

    for chain in {id(chain): chain for chain in ctx.dash_chains.values()}.values():
        merged = []
        for start, end in sorted(chain.gaps):
            if end <= start:
                continue
            if merged and start <= merged[-1][1] + 1e-12:
                merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
            else:
                merged.append((start, end))
        chain.gaps = merged


def control_intervals(
    ctx: Context,
    section: Section,
    start: float,
    end: float,
    *,
    run: MarkingRun | None = None,
) -> list[tuple[float, float]]:
    """@return Visible local intervals outside controls and missing centerlines."""
    key = section.identifier if run is None else run
    phase, direction = ctx.phases[key]
    low, high = sorted((phase + direction * start, phase + direction * end))
    intervals = subtract_intervals(low, high, ctx.dash_chains[key].gaps)
    return sorted(
        tuple(sorted(((a - phase) / direction, (b - phase) / direction))) for a, b in intervals
    )


def dashed_intervals(
    ctx: Context,
    section: Section,
    start: float,
    end: float,
    length: float,
    rendering: Data,
    *,
    run: MarkingRun | None = None,
    style_span: tuple[float, float] | None = None,
) -> Iterator[tuple[float, float]]:
    """@return Dash pieces whose full visible stroke meets the minimum length.

    A section may own just a small piece of an otherwise complete dash. Check
    the stroke in shared chain coordinates before deciding whether to keep it.
    """
    key = section.identifier if run is None else run
    phase, direction = ctx.phases[key]
    stroke = rendering["centerline_dashed_stroke_length"]
    gap = rendering["centerline_dashed_gap_length"]
    minimum = rendering["centerline_minimum_terminal_stroke_ratio"]
    chain = ctx.dash_chains[key]
    low, high = chain.start, chain.end

    # Only actual style boundaries cut a stroke. Other marking masks and source
    # ownership can split one continuous style into several drawing intervals.
    style_start, style_end = style_span if style_span is not None else (start, end)
    for position, is_lower in ((style_start, direction > 0), (style_end, direction < 0)):
        if 1e-10 < position < length - 1e-10:
            if is_lower:
                low = max(low, phase + direction * position)
            else:
                high = min(high, phase + direction * position)

    for visible_start, visible_end in control_intervals(ctx, section, start, end, run=key):
        for a, b in stroke_intervals(visible_start, visible_end, stroke, gap, phase, direction):
            middle = phase + direction * (a + b) / 2
            beginning = math.floor((middle - gap) / (stroke + gap)) * (stroke + gap) + gap
            left, right = max(low, beginning), min(high, beginning + stroke)
            for control_start, control_end in chain.gaps:
                if control_end <= middle:
                    left = max(left, control_end)
                elif control_start >= middle:
                    right = min(right, control_start)
                    break
            if right - left >= minimum * stroke - 1e-12:
                yield a, b
