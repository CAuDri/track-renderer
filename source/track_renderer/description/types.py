"""Describe the upstream objects the renderer reads from Track Description.

These Protocols give type checkers and developers a small map of that dependency.
They describe existing objects, without wrapping them or importing the dynamically
loaded upstream scripts. This is an internal integration contract, not another
track format or a replacement for the validators. Keep it in step with the pinned
submodule when the renderer starts using more of its model.

Distances are meters and upstream yaws are radians. The SVG annotation model uses
degrees, so compilers convert angles when they create scene poses.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol, TypedDict

from shapely.geometry import LineString, Polygon

Point = tuple[float, float]
Data = dict[str, Any]


class SourceDocument(Protocol):
    """Parsed input and the authored locations used to explain diagnostics."""

    data: Data
    uri: str
    locations: dict[str, Data]


class UpstreamDiagnostic(Protocol):
    """One expansion or validation finding before conversion to a scene diagnostic."""

    code: str
    message: str
    path: str
    severity: str
    source: Data | None
    schema_ref: str | None
    details: Data


class ExpansionResult(Protocol):
    """Expanded values and their history, including defaults and generated objects."""

    track: Data
    source: SourceDocument
    provenance: dict[str, Data]
    diagnostics: list[UpstreamDiagnostic]

    @property
    def complete(self) -> bool: ...


class SchemaNode(Protocol):
    """A schema or catalog fragment, together with the URI used for references."""

    value: Data
    uri: str


class SchemaBundle(Protocol):
    """The loaded schema resources used to expand and validate one track."""

    documents: dict[str, SourceDocument]

    def catalog(self, path: str) -> SchemaNode: ...


class Curve(Protocol):
    """A section's local reference curve, parameterized by distance along it."""

    length: float
    k0: float

    def point(self, distance: float) -> Point: ...
    def yaw(self, distance: float) -> float: ...

    def stations(
        self, tolerance: float, offset: float = 0, start: float = 0, end: float | None = None
    ) -> Iterable[float]: ...


class Section(Protocol):
    """A resolved road section; points, ports and headings are in Map coordinates."""

    identifier: str
    value: Data
    curve: Curve
    pose: tuple[float, float, float]
    component: int
    surface: Polygon | None
    ports: dict[str, tuple[float, float, float]]

    @property
    def path(self) -> str: ...

    @property
    def intersection(self) -> bool: ...

    @property
    def width(self) -> float:
        """One lane's nominal width, excluding the outer marking."""
        ...

    @property
    def marking(self) -> float:
        """Width of one painted road marking."""
        ...

    @property
    def boundary(self) -> float:
        """Reference-line distance to the center of the outer marking."""
        ...

    @property
    def half(self) -> float:
        """Reference-line distance to the outer painted road edge."""
        ...

    @property
    def inner(self) -> float:
        """Reference-line distance to the inner edge of the outer marking."""
        ...

    def point(self, s: float, offset: float = 0) -> Point: ...
    def yaw(self, s: float) -> float: ...
    def port(self, name: str) -> tuple[float, float, float]: ...
    def project(self, point: Point) -> float: ...


class RoadArm(TypedDict):
    """Resolved intersection-arm directions and its adjacent road dimensions."""

    u: Point
    n: Point
    half: float
    inner: float
    boundary: float
    road: Section
    angle: float


class RouteLeg(Protocol):
    """One visit along a section, including the chosen ports at an intersection.

    Start and end are section stations; their order records travel direction.
    A route can visit the same section more than once.
    """

    section: str
    start: float
    end: float
    length: float
    line: LineString
    incoming: str | None
    outgoing: str | None


class Instance(Protocol):
    """An element, feature or zone with resolved ownership and geometric placement.

    Ownership and placement are separate: a generated sign can belong to an
    element on one section while its advance places it on the neighboring road.
    """

    path: str
    value: Data
    section: str | None
    owner: Instance | None
    slot: str
    kind: str
    start: float | None
    end: float | None
    position: Point | None
    yaw: float
    station: float | None
    placed_section: str | None
    route: list[RouteLeg] | None


class BoundaryTransition(Protocol):
    """An opposite-arm taper and its painted edges in the junction frame."""

    start_width: float
    end_width: float

    def point(self, t: float, *, side: int = 0) -> Point: ...
    def normal(self, t: float) -> Point: ...

    def sample(
        self, tolerance: float, *, side: int = 0, start: float = 0, end: float = 1
    ) -> list[Point]: ...


class GeometryModel(Protocol):
    """Validated road connectivity, placements and shared geometric constructions."""

    sections: dict[str, Section]
    instances: list[Instance]
    by_path: dict[str, Instance]
    links: dict[tuple[str, str], tuple[str, str, int]]
    root_component: int
    approximation: float
    tolerance: float

    def arm(self, section: Section, port: str) -> RoadArm: ...
    def boundary_transition(
        self, section: Section, first_port: str, second_port: str
    ) -> BoundaryTransition: ...
    def road_shape(self, section: Section, tolerance: float | None = None) -> Polygon: ...
    def linear_leg(self, section: Section, start: float, end: float) -> RouteLeg: ...
    def junction_leg(self, section: Section, incoming: str, outgoing: str) -> RouteLeg: ...
    def resolve_span(self, span: Data, direction: str = "forward") -> list[RouteLeg]: ...
    def locate(
        self, section: Section, station: float
    ) -> tuple[Section, float | None, Point, float]: ...
    def sign_panel_size(self, value: Data) -> tuple[float, float]: ...


class GeometryResult(Protocol):
    """Validation findings and any model that can be used for scene compilation."""

    model: GeometryModel | None
    diagnostics: list[UpstreamDiagnostic]

    def report(self) -> Data: ...
