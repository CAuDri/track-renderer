"""Provide SVG loading and embedding with the same passive-artwork checks."""

from .loading import embed_asset, embed_svg, read_asset
from .validation import validate_svg

__all__ = ["embed_asset", "embed_svg", "read_asset", "validate_svg"]
