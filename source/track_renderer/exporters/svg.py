"""Serialize a rendered SVG document with the requested page dimensions."""

from ..svg import SvgDocument


def export_svg(
    drawing: SvgDocument,
    *,
    margin: float = 0.5,
    scale: float = 1,
    responsive: bool = False,
    metadata: bool = True,
) -> str:
    """@brief Return standalone SVG with embedded artwork and track annotations.

    @param margin Background margin in meters.
    @param scale Physical drawing scale denominator; unused for responsive SVGs.
    @param responsive Omit physical dimensions and fit the viewer using the viewBox.
    @param metadata False omits track annotations and invisible selection geometry.
    """
    return drawing.to_svg(margin=margin, scale=scale, responsive=responsive, metadata=metadata)
