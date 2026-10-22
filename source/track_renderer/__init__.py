"""Prepare CAuDri tracks and render portable SVG documents with semantic metadata.

The public API keeps rendering, section selection and raster export together.
Drawing geometry lives in the SVG tree, so other SVG tools can use the result
without implementing a separate scene format.
"""

from .api import render
from .cache import dependency_uris, renderer_fingerprint
from .description import PreparedTrack, prepare_track
from .diagnostics import Diagnostic, RenderError, SvgError
from .exporters import export_jpg, export_svg
from .io import write_file
from .options import RenderOptions
from .svg import SvgDocument, load_svg

__all__ = [
    "Diagnostic",
    "PreparedTrack",
    "RenderError",
    "RenderOptions",
    "SvgDocument",
    "SvgError",
    "dependency_uris",
    "export_jpg",
    "export_svg",
    "load_svg",
    "prepare_track",
    "render",
    "renderer_fingerprint",
    "write_file",
]
