"""Load SVG artwork and keep one copy of each distinct image in the scene.

Public loading and embedding functions validate artwork before it is accepted.
Assets are identified by their content hash, while source URIs remain available
for dependency tracking and for recognizing a repeated request in this scene.
"""

from __future__ import annotations

import hashlib
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote, urlsplit
from urllib.request import urlopen

from ..diagnostics import RenderFailure

if TYPE_CHECKING:
    from ..rendering.builder import DrawingBuilder
from .validation import SVG_LIMIT, validate_svg


def embed_asset(scene: DrawingBuilder, reference: str) -> str:
    """@brief Read an SVG once and embed it by content hash.

    Failed reads remain dependencies of a forced partial scene, so an application
    can invalidate that scene when the artwork becomes available.
    @throws RenderFailure For unsupported, oversized or active/external artwork.
    @throws OSError For unavailable artwork.
    """
    scene._asset_dependencies.add(reference)
    for identifier, asset in scene.assets.items():
        if reference in asset["sources"]:
            return identifier

    # read_asset has already checked the SVG. Store it directly so a fresh read
    # does not immediately repeat the XML and CSS validation.
    return _store_validated_svg(scene, read_asset(reference), reference)


def read_asset(reference: str) -> str:
    """@return Validated passive SVG content from the selected asset URI."""
    try:
        return _read_asset(reference)
    except (RenderFailure, OSError):
        raise
    except Exception as exc:
        # External readers and parsers may expose implementation-specific errors.
        # Keep them at the artwork boundary so forced rendering can continue.
        raise RenderFailure(f"Cannot import SVG artwork {reference}: {exc}") from exc


def _read_asset(reference: str) -> str:
    """Read bounded artwork and validate it before returning its text."""
    parsed = urlsplit(reference)
    if parsed.fragment:
        raise RenderFailure(f"Asset fragments are not supported: {reference}")

    if parsed.scheme in {"http", "https"}:
        with urlopen(reference, timeout=15) as response:
            data = response.read(SVG_LIMIT + 1)
    elif parsed.scheme in {"", "file"} and parsed.netloc in {"", "localhost"}:
        if parsed.query:
            raise RenderFailure(f"File asset URI cannot contain a query: {reference}")
        with Path(unquote(parsed.path)).open("rb") as stream:
            data = stream.read(SVG_LIMIT + 1)
    else:
        raise RenderFailure(f"Unsupported asset URI: {reference}")
    if len(data) > SVG_LIMIT:
        raise RenderFailure("SVG artwork exceeds 8 MiB")

    try:
        content = data.decode("utf-8")
    except UnicodeError as exc:
        raise RenderFailure("SVG artwork must use UTF-8 encoding") from exc

    validate_svg(content)
    return content


def embed_svg(
    scene: DrawingBuilder,
    content: str,
    reference: str,
    *,
    generation: dict[str, Any] | None = None,
) -> str:
    """@return The content hash of validated supplied or generated SVG artwork."""
    validate_svg(content)
    return _store_validated_svg(scene, content, reference, generation=generation)


def _store_validated_svg(
    scene: DrawingBuilder,
    content: str,
    reference: str,
    *,
    generation: dict[str, Any] | None = None,
) -> str:
    """Store content that has just passed validation and merge its source URI."""
    identifier = hashlib.sha256(content.encode()).hexdigest()
    if identifier not in scene.assets:
        scene.assets[identifier] = {
            "mime_type": "image/svg+xml",
            "content": content,
            "sources": [reference],
        }
        if generation is not None:
            scene.assets[identifier]["generation"] = deepcopy(generation)
    elif reference not in scene.assets[identifier]["sources"]:
        scene.assets[identifier]["sources"].append(reference)
    return identifier
