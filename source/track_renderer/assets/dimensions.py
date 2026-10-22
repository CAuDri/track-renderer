"""Read an artwork's intrinsic display dimensions without inventing body sizes.

An SVG viewport with absolute width and height supplies a natural display size.
A viewBox alone, percentages and font-relative units do not establish its scale
in the Map frame and therefore need explicit dimensions in the description.
"""

import math
import re
from xml.etree import ElementTree as ET

from ..diagnostics import RenderFailure

# Match a number with optional decimal and exponent, followed by an optional unit.
_LENGTH = re.compile(
    r"\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(mm|cm|in|pt|pc|px|q)?\s*",
    re.I,
)
_METERS = {
    "mm": 0.001,
    "cm": 0.01,
    "in": 0.0254,
    "pt": 0.0254 / 72,
    "pc": 0.0254 / 6,
    "px": 0.0254 / 96,
    "q": 0.00025,
}


def intrinsic_dimensions(content: str) -> tuple[float, float]:
    """Return forward length and lateral width in meters from validated SVG.

    SVG height follows a symbol's forward axis and SVG width its lateral axis.
    Unitless lengths, like explicit CSS pixels, use 96 pixels per inch. These
    dimensions describe only the projection, not an object's physical body.
    """
    root = ET.fromstring(content)
    dimensions = []
    for name in ("height", "width"):
        match = _LENGTH.fullmatch(root.get(name, ""))
        if match is None:
            raise RenderFailure(
                "Artwork needs size.length and size.width, or absolute SVG width and height; "
                "a viewBox or relative dimensions alone do not define a display size"
            )
        value = float(match[1]) * _METERS[(match[2] or "px").lower()]
        if not math.isfinite(value) or value <= 0:
            raise RenderFailure("SVG artwork width and height must be finite and positive")
        dimensions.append(value)
    return dimensions[0], dimensions[1]
