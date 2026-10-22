"""Register the compilers for road elements such as crossings and parking areas.

Each element has its own module. Section compilation uses this registry to draw
the expanded elements while preserving their source ownership.
"""

from .barred_area import compile_barred
from .crosswalk import compile_crosswalk
from .parking_area import compile_parking
from .side_road_junction import compile_side_road
from .start_box import compile_start_box
from .starting_line import compile_starting_line

COMPILERS = {
    "crosswalk": compile_crosswalk,
    "side_road_junction": compile_side_road,
    "parking_area": compile_parking,
    "barred_area": compile_barred,
    "start_box": compile_start_box,
    "starting_line": compile_starting_line,
}
