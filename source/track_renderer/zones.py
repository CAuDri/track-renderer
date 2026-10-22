"""Give zones an invisible road footprint that editors can select.

These regions follow the resolved route and belong to the source zone, including
zones that remove all visible paint. They are selection aids, not physical road
surfaces, and do not enlarge the visible drawing's bounds.
"""

from shapely.geometry import Polygon

from .diagnostics import RenderFailure
from .geometry.placement import zone_route
from .geometry.primitives import sample
from .rendering.context import Context


def compile_zone(ctx: Context, path: str) -> None:
    """@brief Add a selection region for each visit along the zone's route.

    Separate regions preserve repeated intersection visits. At a junction, clip
    the traveled corridor to the road so unrelated crossing arms stay unselected.
    """
    owner = ctx.model.by_path[path]
    for index, leg in enumerate(zone_route(ctx, owner)):
        section = ctx.model.sections[leg.section]
        if section.component != ctx.model.root_component or section.component < 0:
            raise RenderFailure("Zone has no position relative to the root")
        if leg.length <= 1e-12:
            continue

        if not section.intersection and abs(leg.end - leg.start) >= section.curve.length - 1e-12:
            # Reuse annulus construction for complete circular sections; joining
            # its inner and outer rings at a seam would make an invalid polygon.
            shape = ctx.model.road_shape(section, ctx.tolerance)
        elif section.intersection:
            width = max(
                ctx.model.arm(section, port)["half"] for port in (leg.incoming, leg.outgoing)
            )
            shape = leg.line.buffer(width, cap_style="flat").intersection(
                ctx.model.road_shape(section, ctx.tolerance)
            )
        else:
            shape = Polygon(
                sample(section, leg.start, leg.end, section.half, ctx.tolerance)
                + sample(section, leg.end, leg.start, -section.half, ctx.tolerance)
            )

        pieces = [shape] if isinstance(shape, Polygon) else list(shape.geoms)
        for piece, polygon in enumerate(pieces):
            if isinstance(polygon, Polygon) and not polygon.is_empty:
                ctx.region(
                    path,
                    f"selection/{index}/{piece}",
                    polygon,
                    "#000000",
                    purpose="selection",
                    layer=10,
                    placement_section=section.path,
                )
