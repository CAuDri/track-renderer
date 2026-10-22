"""Choose which optional drawings to include and how finely to sample curves.

These settings apply to a rendering call. Hiding an object's projection keeps
its physical position and dimensions in the scene; it only removes the drawing.
The authored description and its validation results remain unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass

from .diagnostics import RenderFailure
from .geometry.primitives import positive

PROJECTION_TYPES = frozenset(
    {
        "traffic_sign",
        "landmark",
        "static_obstacle",
        "dynamic_obstacle",
        "pedestrian",
        "crosswalk_waiting_area",
    }
)


@dataclass(frozen=True)
class RenderOptions:
    """@brief Drawing settings; they do not modify the authored description.

    @param pose_only Object types whose optional 2D projections are omitted.
    @param curve_tolerance Maximum chord error in meters; None uses the catalog.
    @param projections Enable optional drawings, including crosswalk waiting areas.
    """

    pose_only: frozenset[str] = frozenset()
    curve_tolerance: float | None = None
    projections: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "pose_only", frozenset(self.pose_only))
        unknown = set(self.pose_only) - PROJECTION_TYPES
        if unknown:
            raise RenderFailure(f"Unknown projection types: {sorted(unknown)}")

        if self.curve_tolerance is not None:
            positive(self.curve_tolerance, "curve tolerance")

    def project(self, kind: str) -> bool:
        """@return Whether objects of this type should include their optional drawing."""
        return self.projections and kind not in self.pose_only
