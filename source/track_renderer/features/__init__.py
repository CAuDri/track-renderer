"""Choose the compiler for each supported Track Description feature type.

The explicit registry is the starting point for adding a feature. Individual
modules handle its placement, physical parts and drawing under the same owner.
"""

from ..diagnostics import RenderFailure
from ..rendering.context import Context
from .landmark import compile_landmark
from .objects import compile_object
from .surface_marking import compile_surface_marking
from .traffic_sign import compile_traffic_sign

COMPILERS = {
    "traffic_sign": compile_traffic_sign,
    "surface_marking": compile_surface_marking,
    "landmark": compile_landmark,
    "static_obstacle": compile_object,
    "artifact": compile_object,
    "custom_marker": compile_object,
}


def compile_feature(ctx: Context, path: str) -> None:
    """@brief Send a feature to its compiler, or report an unsupported type."""
    kind = ctx.sources[path]["type"]
    compiler = COMPILERS.get(kind)
    if compiler is None:
        raise RenderFailure(f"Unknown feature type: {kind}")
    compiler(ctx, path)
