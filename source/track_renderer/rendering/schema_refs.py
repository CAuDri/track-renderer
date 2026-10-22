"""Shorten schema references in exported provenance and validation records.

The SVG's schema_uri is the shared base. Keep other resource URIs and the
prepared input untouched; only schema_ref fields use this convention.
"""

import posixpath
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit


def _relative_ref(reference: str, schema_uri: str) -> str:
    """Use a relative URI only when resolving it recovers the exact original."""
    base = urlsplit(schema_uri)
    target = urlsplit(reference)

    if (
        not base.scheme
        or (base.scheme, base.netloc) != (target.scheme, target.netloc)
        or not base.path.startswith("/")
        or not target.path.startswith("/")
    ):
        return reference

    path = posixpath.relpath(target.path, posixpath.dirname(base.path))

    # A colon in the first segment would otherwise be read as a URI scheme.
    if ":" in path.split("/", 1)[0]:
        path = "./" + path

    relative = urlunsplit(("", "", path, target.query, target.fragment))

    # This also protects unusual URI schemes, escaped paths and trailing slashes.
    return relative if urljoin(schema_uri, relative) == reference else reference


def relative_schema_refs(value: Any, schema_uri: str) -> Any:
    """@return Copied records with schema_ref strings relative to schema_uri.

    Call this only for provenance and validation records, not user properties:
    an authored property named schema_ref has no special meaning to the renderer.
    Existing relative references and references to other URI origins stay intact.
    """
    if isinstance(value, dict):
        return {
            key: (
                _relative_ref(item, schema_uri)
                if key == "schema_ref" and isinstance(item, str)
                else relative_schema_refs(item, schema_uri)
            )
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [relative_schema_refs(item, schema_uri) for item in value]

    return value
