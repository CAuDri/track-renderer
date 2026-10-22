"""Draw parking bays and the individually owned spots inside them.

The bay outline follows the road and slopes outward at its ends. Each spot keeps
its own source identity for editor selection; a no-parking spot adds a cross,
while an occupied spot's generated obstacle is drawn by the feature compiler.
"""

import math

from ..diagnostics import RenderFailure
from ..rendering.context import Context
from ..rendering.pointers import pointer


def compile_parking(ctx: Context, path: str) -> None:
    """@brief Add each bay's road surface, outline and parking-spot markings."""
    section, value = ctx.section(path), ctx.sources[path]
    if section.value["type"] != "straight":
        raise RenderFailure("Parking areas require straight sections")

    parameters, rendering = value["parameters"], value["rendering"]
    boundary = section.boundary
    color = section.value["road"]["rendering"]["marking_color"]
    angle = math.radians(parameters["boundary_side_angle"])
    if not 0 < angle < math.pi / 2:
        raise RenderFailure("Parking side angle must be between zero and 90 degrees")

    for lot_name, sign in (("parallel_parking", -1), ("perpendicular_parking", 1)):
        if not isinstance(parameters.get(lot_name), dict):
            continue

        lot_path = path + "/parameters/" + lot_name
        lot = ctx.model.by_path[lot_path]
        depth = lot.value["extent_lateral"]
        if parameters["direction"] == "backward":
            sign *= -1
        run = depth / math.tan(angle)
        if 2 * run >= lot.end - lot.start:
            raise RenderFailure("Parking bay is too short for its outline side angle")

        local = (
            (lot.start, boundary),
            (lot.start + run, boundary + depth),
            (lot.end - run, boundary + depth),
            (lot.end, boundary),
        )
        points = [section.point(s, sign * y) for s, y in local]
        ctx.region(
            lot_path,
            "surface",
            points,
            section.value["road"]["rendering"]["surface_color"],
            layer=0,
        )
        ctx.path(lot_path, "outline", points, color, rendering["boundary_outline_width"])

        for spot_id in sorted(lot.value["spots"]):
            spot_path = pointer(lot_path + "/spots", spot_id)
            spot = ctx.model.by_path[spot_path]
            outer = boundary + spot.value["extent_lateral"]
            vertices = [
                section.point(s, sign * y)
                for s, y in (
                    (spot.start, boundary),
                    (spot.end, boundary),
                    (spot.end, outer),
                    (spot.start, outer),
                )
            ]
            width = (
                rendering["parallel_outer_marking_width"]
                if lot_name == "parallel_parking"
                else rendering["perpendicular_separator_width"]
            )

            # Occupancy is semantic; its generated obstacle supplies the drawing.
            ctx.path(spot_path, "outline", vertices + [vertices[0]], color, width)
            if spot.value["state"] == "no_parking":
                for i in (0, 1):
                    ctx.path(spot_path, f"cross/{i}", [vertices[i], vertices[i + 2]], color, width)
