"""Work with native SVG track drawings and their source-linked annotations."""

from .document import SvgDocument, load_svg
from .metadata import SVG, write_metadata

__all__ = ["SvgDocument", "load_svg", "SVG", "write_metadata"]
