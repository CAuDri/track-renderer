"""Describe problems in a track, a rendering operation or an SVG document.

Diagnostics retain source paths and structured details for editors and command-
line reports. Public errors carry these diagnostics or a document location;
RenderFailure is the internal exception for expected drawing failures.
"""

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Diagnostic:
    """@brief Explain a finding and identify the affected part of the expanded track."""

    code: str
    message: str
    path: str = ""
    severity: str = "error"
    source: dict[str, Any] | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """@return JSON-compatible diagnostic data."""
        return asdict(self)


class RenderError(ValueError):
    """@brief Input or rendering failed; diagnostics describe the affected sources."""

    def __init__(self, message: str, diagnostics: tuple[Diagnostic, ...] = ()):
        super().__init__(message)
        self.diagnostics = diagnostics


class SvgError(ValueError):
    """@brief Identify invalid SVG or semantic annotations by their document location."""

    def __init__(self, message: str, *, path: str = ""):
        self.path = path
        super().__init__(f"{path or '/'}: {message}")


class RenderFailure(ValueError):
    """Expected compilation failure, converted into a source-linked diagnostic.

    Internal compilers use this for unusable placements, dimensions or artwork.
    Programming errors remain visible instead of becoming partial render output.
    """
