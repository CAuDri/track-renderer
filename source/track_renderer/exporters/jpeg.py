"""Turn a native SVG drawing into an opaque JPEG with a physical resolution.

CairoSVG and Pillow are loaded only when JPEG output is requested, so other
exports do not require the optional image dependencies. Pixel sizing follows
the SVG viewport, converting Map meters to inches before applying DPI. JPEG
metadata stores the nearest whole-number print density supported by JFIF.
"""

import math
from io import BytesIO
from xml.etree import ElementTree as ET

from ..geometry.primitives import positive
from ..svg import SvgDocument
from .svg import export_svg

_METERS_PER_INCH = 0.0254
_MAX_PIXELS = 100_000_000
# Cairo's image surfaces limit each axis even when the total pixel count fits.
_MAX_DIMENSION = 32767
_SIZE_HINT = "Reduce DPI or specify a smaller width (--width)."


def _pixel_dimensions(
    width_m: float, height_m: float, dpi: float, width: int | None
) -> tuple[int, int]:
    """Resolve a bounded raster size before allocating any image memory."""
    if width is None:
        projected_width = width_m * dpi / _METERS_PER_INCH
        if not math.isfinite(projected_width) or projected_width > _MAX_PIXELS:
            raise ValueError(f"Requested image exceeds 100 million pixels. {_SIZE_HINT}")
        width = round(projected_width)

    if isinstance(width, bool) or not isinstance(width, int) or width < 1:
        raise ValueError("Image width must be a positive integer")
    if width > _MAX_DIMENSION:
        raise ValueError(f"Image width exceeds {_MAX_DIMENSION} pixels. {_SIZE_HINT}")

    projected_height = width * (height_m / width_m)
    if not math.isfinite(projected_height) or projected_height > _MAX_PIXELS:
        raise ValueError(f"Requested image exceeds 100 million pixels. {_SIZE_HINT}")
    height = round(projected_height)
    if height < 1:
        raise ValueError("Image height would be less than one pixel; increase the resolution")
    if height > _MAX_DIMENSION:
        raise ValueError(f"Image height exceeds {_MAX_DIMENSION} pixels. {_SIZE_HINT}")
    if width * height > _MAX_PIXELS:
        raise ValueError(f"Requested image exceeds 100 million pixels. {_SIZE_HINT}")

    return width, height


def export_jpg(
    drawing: SvgDocument,
    *,
    dpi: float = 20,
    width: int | None = None,
    margin: float = 0.5,
    quality: int = 95,
) -> bytes:
    """@brief Rasterize an SVG drawing into an opaque JPEG image.

    @param dpi Pixels per inch at Map scale 1:1; defaults to 20.
        The rounded value must fit JPEG's integer density range, 1 through 65535.
    @param width Optional pixel width, taking precedence over DPI-based sizing.
        DPI still supplies the JPEG's nominal print resolution.
    @param quality JPEG quality from 1 to 100.
    @return Encoded JPEG bytes. Requires the package's image extra.
    """
    try:
        import cairosvg
        from cairocffi import CairoError
        from PIL import Image
    except ImportError as exc:
        raise ValueError("JPEG export requires track-renderer[image]") from exc

    try:
        dpi = positive(dpi, "DPI")
    except OverflowError as exc:
        raise ValueError("DPI is outside the supported JPEG density range") from exc
    density = round(dpi)
    if not 1 <= density <= 65535:
        raise ValueError("DPI must round to a JPEG density between 1 and 65535")
    if not isinstance(quality, int) or not 1 <= quality <= 100:
        raise ValueError("JPEG quality must be an integer between 1 and 100")

    svg = export_svg(drawing, margin=margin)
    if drawing.bounds() is None:
        raise ValueError("SVG has no drawable geometry")
    # A selected document may deliberately retain its original viewport. Size
    # the raster from that viewport, rather than the smaller visible bounds.
    viewbox = [float(value) for value in ET.fromstring(svg).get("viewBox").split()]
    pixel_width, height = _pixel_dimensions(viewbox[2], viewbox[3], dpi, width)

    try:
        raster = cairosvg.svg2png(
            bytestring=svg.encode(), output_width=pixel_width, output_height=height
        )
    except CairoError as exc:
        raise ValueError(f"JPEG rasterization failed: {exc}. {_SIZE_HINT}") from exc
    output = BytesIO()
    with Image.open(BytesIO(raster)) as image:
        background = Image.new("RGB", image.size, drawing.metadata["background"])
        if image.mode == "RGBA":
            background.paste(image, mask=image.getchannel("A"))
        else:
            background.paste(image.convert("RGB"))
        background.save(output, format="JPEG", quality=quality, dpi=(density, density))
    return output.getvalue()
