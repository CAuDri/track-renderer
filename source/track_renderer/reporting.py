"""Build standalone render reports with enough context to resolve schema links.

Successful drawings carry relative schema references and their shared base URI.
Failures before a drawing exists retain the diagnostics' original absolute
references; their schema and validation fields are unavailable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .diagnostics import RenderError

if TYPE_CHECKING:
    from .svg import SvgDocument


def build_report(result: SvgDocument | RenderError) -> dict[str, Any]:
    """@return An independent report for either a completed render or a failure."""
    if isinstance(result, RenderError):
        return {
            "schema_uri": None,
            "complete": False,
            "validation": None,
            "diagnostics": [finding.to_dict() for finding in result.diagnostics],
        }

    # Read the JSON once; document accessors otherwise each decode the payload.
    metadata = result.metadata
    return {key: metadata[key] for key in ("schema_uri", "complete", "validation", "diagnostics")}
