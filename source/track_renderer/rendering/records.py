"""Keep typed ownership and physical placements while a track is compiled.

These records are temporary compiler data. Their semantic fields are embedded
in SVG metadata; drawing geometry is emitted directly as native SVG elements.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

Point = tuple[float, float]


@dataclass(frozen=True)
class Pose:
    """@brief Place a center in the Map frame, in meters and counter-clockwise degrees."""

    x: float
    y: float
    z: float = 0.0
    yaw: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0

    def point(self, x: float, y: float) -> Point:
        """@return A local planar point transformed into the Map frame."""
        angle = math.radians(self.yaw)
        return (
            self.x + math.cos(angle) * x - math.sin(angle) * y,
            self.y + math.sin(angle) * x + math.cos(angle) * y,
        )


@dataclass(frozen=True)
class TrackObject:
    """@brief Identify a source object and its owner, even when it has no drawing."""

    id: str
    type: str
    category: str
    parent_id: str | None
    section_id: str | None
    source_pointer: str
    properties: dict[str, Any]
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PhysicalPart:
    """@brief Describe a physical component at its resolved position.

    Parts remain in SVG metadata when their optional 2D projections are disabled.
    Size uses the source convention where defined. Panel dimensions use explicit
    width/height instead of inventing a thickness for planar artwork.
    """

    id: str
    object_id: str
    role: str
    pose: Pose
    size: dict[str, float] = field(default_factory=dict)
    properties: dict[str, Any] = field(default_factory=dict)
