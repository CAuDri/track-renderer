"""Help applications decide when a previously rendered drawing needs rebuilding.

The renderer fingerprint covers code and core dependency versions. The resource
list identifies the input, schemas and artwork whose contents the application
must check separately. This is separate from the automatic schema bundle cache.
"""

import hashlib
import sys
from importlib.metadata import version
from pathlib import Path

from .description import PreparedTrack, description_directory
from .svg import SvgDocument


def renderer_fingerprint() -> str:
    """@return A fingerprint of rendering/validation code and dependency versions.

    Document and artwork contents are separate dependencies returned by
    dependency_uris(). No expansion or rendering is needed to compute this key.
    """
    digest = hashlib.sha256(repr(sys.version_info[:3]).encode())
    for distribution in (
        "track-renderer",
        "PyYAML",
        "jsonschema",
        "referencing",
        "shapely",
        "segno",
        "tinycss2",
    ):
        digest.update(f"{distribution}={version(distribution)}".encode())

    for root in (Path(__file__).parent, description_directory() / "scripts"):
        for path in sorted(root.rglob("*.py")):
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())

    return digest.hexdigest()


def dependency_uris(prepared: PreparedTrack, drawing: SvgDocument) -> tuple[str, ...]:
    """@return Input, loaded schema/catalog documents and referenced artwork URIs.

    Consumers must check contents, not only timestamps. Non-file URIs require
    revalidation by the consumer; generated URNs are not external dependencies.
    Attempted artwork reads remain dependencies even when rendering is partial.
    They are preserved in the SVG metadata when a document is saved and loaded.
    """
    uris = {prepared.expansion.source.uri}
    uris.update(uri for uri in drawing.dependencies if not uri.startswith("urn:"))
    uris.update(document.uri for document in prepared.bundle.documents.values())

    for asset in drawing.assets.values():
        uris.update(uri for uri in asset.get("sources", ()) if not uri.startswith("urn:"))
        template = asset.get("generation", {}).get("template_uri")
        if template:
            uris.add(template)

    return tuple(sorted(uris))
