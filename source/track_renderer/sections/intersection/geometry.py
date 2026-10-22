"""Prepared intersection arms, corners and control edges.

The constructions follow the CAuDri concept renderer. Everything is prepared in
junction-local coordinates before any paint is drawn: the center lies one
port_distance along the entry axis, and each arm points outward from it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ...diagnostics import RenderFailure
from ...geometry.primitives import add, cross, scale, unit

if TYPE_CHECKING:
    from ...description.types import BoundaryTransition, Data, Point, Section
    from ...rendering.context import Context


@dataclass(frozen=True)
class Arm:
    """@brief One outward-facing arm with the attached road's cross-section."""

    port: str
    angle: float
    u: tuple[float, float]
    n: tuple[float, float]
    boundary: float
    inner: float
    marking: float
    road: Data


@dataclass(frozen=True)
class Control:
    """@brief The control marking's front edge in outward arm coordinates."""

    station: float
    lateral: float
    circle: tuple[float, float, float] | None = None
    # Sharp controls end at the inner painted boundary rather than at the
    # lateral anchor used by rounded corners.
    lateral_limit: float | None = None


@dataclass
class Junction:
    """@brief Shared corner results for section paint and generated features."""

    section: Section
    arms: dict[str, Arm]
    controls: dict[str, Control]
    boundaries: list[Boundary]


@dataclass(frozen=True)
class Boundary:
    """@brief Adjacent arm sides joined by a corner or an opposite-arm taper."""

    first: str
    second: str
    start: tuple[float, float]
    connector_points: list[Point]
    end: tuple[float, float]
    width: float
    transition: BoundaryTransition | None = None


def sample_corner_arc(
    center: Point, start: Point, sweep: float, radius: float, tolerance: float
) -> list[Point]:
    """@return Circular corner points within the requested chord-error tolerance."""
    step = 2 * math.acos(max(-1, 1 - tolerance / radius))
    count = max(1, math.ceil(abs(sweep) / max(step, 1e-10)))
    if count > 50000:
        raise RenderFailure("Intersection corner requires more than 50000 samples")
    angle = math.atan2(start[1] - center[1], start[0] - center[0])
    return [add(center, scale(unit(angle + sweep * i / count), radius)) for i in range(count + 1)]


def sample_transition(transition: BoundaryTransition, tolerance: float, **kwargs) -> list[Point]:
    """Convert upstream sampling limits into a source-linked rendering failure."""
    try:
        return transition.sample(tolerance, **kwargs)
    except ValueError as exc:
        raise RenderFailure(str(exc)) from exc


def _arm(ctx: Context, section: Section, port: str) -> Arm:
    info = ctx.model.arm(section, port)
    road = info["road"].value["road"]
    return Arm(
        port,
        info["angle"],
        info["u"],
        info["n"],
        info["boundary"],
        info["inner"],
        info["road"].marking,
        road,
    )


def _previous_arm(arms: list[Arm], index: int) -> Arm:
    """Find the neighboring arm used to anchor a straight control edge."""
    current, previous, following = arms[index], arms[index - 1], arms[(index + 1) % len(arms)]
    right_angle = (following.angle - current.angle) % math.tau
    if (
        right_angle <= math.pi / 2 + 1e-10
        or (current.angle - previous.angle) % math.tau < math.pi - 1e-10
    ):
        return previous
    # An obtuse T-junction uses the theoretical missing cross-arm as its anchor.
    canonical = ("straight", "left", "entry", "right")
    name = canonical[(canonical.index(current.port) - 1) % len(canonical)]
    for arm in arms:
        if arm.port == name:
            return arm
    opposite = {"entry": "straight", "straight": "entry", "left": "right", "right": "left"}
    matching = next(a for a in arms if a.port == opposite[name])
    return Arm(
        name,
        (matching.angle + math.pi) % math.tau,
        scale(matching.u, -1),
        scale(matching.n, -1),
        matching.boundary,
        matching.inner,
        matching.marking,
        matching.road,
    )


def _boundary_between(
    ctx: Context, section: Section, first: Arm, second: Arm
) -> tuple[Boundary, Point | None]:
    """Join adjacent painted sides and retain the first corner's tangent point."""
    parameters = section.value["parameters"]
    port_distance, radius = parameters["port_distance"], parameters["corner_radius"]
    center = (port_distance, 0)
    delta = (second.angle - first.angle) % math.tau
    first_offset = add(center, scale(first.n, first.boundary))
    second_offset = add(center, scale(second.n, -second.boundary))
    transition, tangent = None, None

    if abs(delta - math.pi) < 1e-10:
        transition = ctx.model.boundary_transition(section, first.port, second.port)
        connector = sample_transition(transition, ctx.tolerance)
    else:
        if not 0 < delta < math.pi:
            raise RenderFailure("Intersection has an unresolved gap between its arms")
        advance = cross(add(second_offset, scale(first_offset, -1)), second.u) / cross(
            first.u, second.u
        )
        vertex = add(first_offset, scale(first.u, advance))
        run = radius / math.tan(delta / 2)
        tangent = add(vertex, scale(first.u, run))
        other = add(vertex, scale(second.u, run))
        connector = (
            sample_corner_arc(
                add(tangent, scale(first.n, radius)),
                tangent,
                -(math.pi - delta),
                radius,
                ctx.tolerance,
            )
            if radius
            else [tangent, other]
        )

    boundary = Boundary(
        first.port,
        second.port,
        add(first_offset, scale(first.u, port_distance)),
        connector,
        add(second_offset, scale(second.u, port_distance)),
        max(first.marking, second.marking),
        transition,
    )
    return boundary, tangent


def _control_for_arm(
    section: Section, arms: list[Arm], index: int, tangent: Point | None
) -> Control:
    """Anchor control paint to a corner, or to the opposite straight painted edge."""
    first, second = arms[index], arms[(index + 1) % len(arms)]
    parameters = section.value["parameters"]
    port_distance, radius = parameters["port_distance"], parameters["corner_radius"]
    center = (port_distance, 0)
    delta = (second.angle - first.angle) % math.tau

    if delta <= math.pi / 2 + 1e-10:
        circle = add(tangent, scale(first.n, radius))
        relative = add(circle, scale(center, -1))
        station = sum(x * y for x, y in zip(relative, first.u, strict=True))
        lateral = sum(x * y for x, y in zip(relative, first.n, strict=True))
        visible_radius = radius + max(first.marking, second.marking) / 2
        if radius == 0:
            # Zero means a sharp painted corner. Its control cap follows the
            # straight inner edge; there is no small substitute circle.
            return Control(
                station - visible_radius,
                first.inner,
                lateral_limit=first.boundary - max(first.marking, second.marking) / 2,
            )
        return Control(station - visible_radius, lateral, (station, lateral, visible_radius))

    previous = _previous_arm(arms, index)
    width = max(first.marking, previous.marking)
    first_offset = add(center, scale(first.n, -(first.boundary - width / 2)))
    previous_offset = add(center, scale(previous.n, previous.boundary - width / 2))
    station = cross(add(previous_offset, scale(first_offset, -1)), previous.u) / cross(
        first.u, previous.u
    )
    return Control(station, first.inner)


def prepare_junction(ctx: Context, section: Section) -> Junction:
    """@brief Prepare boundary connectors and control edges for drawing and dash planning."""
    arms = sorted((_arm(ctx, section, port) for port in section.ports), key=lambda arm: arm.angle)
    controls, boundaries = {}, []

    for index, first in enumerate(arms):
        second = arms[(index + 1) % len(arms)]
        boundary, tangent = _boundary_between(ctx, section, first, second)
        boundaries.append(boundary)
        controls[first.port] = _control_for_arm(section, arms, index, tangent)

    junction = Junction(section, {arm.port: arm for arm in arms}, controls, boundaries)
    ctx.junctions[section.identifier] = junction
    return junction


def control_approach_edge(ctx: Context, junction: Junction, port: str) -> float:
    """Return the painted edge nearest the approach, or the unpainted control limit."""
    section = junction.section
    layout = section.value["parameters"]["layout"]
    slot = {"stop": "stop_line", "give_way": "give_way_line"}.get(layout)
    value = ctx.sources.get(f"{section.path}/features/{port}_{slot}") if slot else None
    station = junction.controls[port].station
    if value and "at" not in value and "pose" not in value:
        station += value["rendering"]["width"]
    return station


def approach_extent(ctx: Context, junction: Junction, port: str) -> float:
    """@return Distance from the port to its nearest control-paint edge."""
    extent = junction.section.value["parameters"]["port_distance"] - control_approach_edge(
        ctx, junction, port
    )
    if extent < 0:
        raise RenderFailure(f"Control edge extends past the {port} junction port")
    return extent
