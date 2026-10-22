"""Type the temporary arguments passed from compilers to SVG drawing helpers.

These dictionaries are consumed immediately when an SVG node is added. They
are not a serialized scene or a public interchange format.
"""

from typing import Literal, NotRequired, TypedDict

Point = tuple[float, float] | list[float]
GeometryKind = Literal["region", "path", "symbol"]
GeometryPurpose = Literal["physical", "projection", "selection"]


class PoseData(TypedDict):
    """Map-frame pose, in meters and counter-clockwise degrees."""

    x: float
    y: float
    yaw: float
    z: NotRequired[float]
    pitch: NotRequired[float]
    roll: NotRequired[float]


class RegionData(TypedDict):
    """Filled exterior and optional holes, without a repeated closing vertex."""

    exterior: list[Point]
    holes: NotRequired[list[list[Point]]]
    color: str


class PathData(TypedDict):
    """Explicit vertices and a physical stroke width in meters."""

    points: list[Point]
    width: float
    color: str
    cap: NotRequired[Literal["butt", "round", "square"]]
    join: NotRequired[Literal["round", "miter", "bevel"]]


class SymbolData(TypedDict):
    """Embedded SVG asset and its oriented physical footprint."""

    pose: PoseData
    asset: str
    length: float
    width: float


GeometryData = RegionData | PathData | SymbolData
