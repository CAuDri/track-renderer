"""Reuse local schema bundles instead of parsing the same YAML on every render.

Loading a bundle is a noticeable part of track preparation. We keep a small set
of parsed bundles and check their file contents before reuse. Each preparation
receives its own copy, so later reference loading cannot change another track's
bundle. Remote bundles are loaded afresh.
"""

from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from threading import Lock
from types import ModuleType
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin, urlsplit
from urllib.request import url2pathname

if TYPE_CHECKING:
    from .types import SchemaBundle, SourceDocument

_MAX_BUNDLES = 8
_bundles: OrderedDict[tuple[type, str], Any] = OrderedDict()
_lock = Lock()


def _digest(uri: str) -> bytes | None:
    """@return A local file's content hash, or None when it cannot be cached."""
    parts = urlsplit(uri)
    if (
        parts.scheme != "file"
        or parts.netloc not in ("", "localhost")
        or parts.query
        or parts.fragment
    ):
        return None

    try:
        return sha256(Path(url2pathname(parts.path)).read_bytes()).digest()
    except OSError:
        return None


@lru_cache(maxsize=_MAX_BUNDLES)
def _tracked_bundle_type(base: type) -> type:
    """@return An upstream bundle subclass that records its actual file reads."""

    class TrackedBundle(base):
        def __init__(self, schema_uri):
            self._cache_sources: dict[str, bytes] = {}
            self._cacheable = True
            super().__init__(schema_uri)

        def _load(self, uri):
            if uri in self.documents:
                return

            # Hash on both sides of parsing. If an editor saves the schema during
            # the read, that mixed revision must not become a cached snapshot.
            before = _digest(uri)
            super()._load(uri)
            after = _digest(uri)
            if before is None or before != after:
                self._cacheable = False
            else:
                self._cache_sources[uri] = after

    return TrackedBundle


def _unchanged(bundle: Any) -> bool:
    """@return Whether every initial resource still has its original contents."""
    return bundle._cacheable and all(
        _digest(uri) == digest for uri, digest in bundle._cache_sources.items()
    )


def _clone(bundle: Any) -> SchemaBundle:
    """@return A separate bundle with references bound to its own schema objects."""
    memo: dict[int, Any] = {}
    result = deepcopy(bundle, memo)

    # Upstream indexes schema dictionaries by identity. deepcopy retains integer
    # keys, so the index must follow the copied dictionaries explicitly.
    result.origins = {id(memo[key]): origin for key, origin in bundle.origins.items()}
    return result


def bundle_for_track(document: SourceDocument, module: ModuleType) -> SchemaBundle:
    """@return A fresh bundle using a bounded cache of unchanged local schemas.

    Snapshots contain only the initial entry schema, catalog and regulations.
    Lazy references belong to each returned copy and are loaded afresh. Remote
    resources and files changed during loading never enter the shared cache.
    """
    base = module.SchemaBundle
    reference = document.data.get("$schema")
    if not isinstance(reference, str) or not reference:
        return base.for_track(document)  # Preserve upstream input diagnostics.

    key = (base, module.as_uri(urljoin(document.uri, reference)))
    with _lock:
        cached = _bundles.get(key)

    if cached is not None:
        unchanged = _unchanged(cached)
        with _lock:
            if _bundles.get(key) is cached:
                if unchanged:
                    _bundles.move_to_end(key)
                else:
                    del _bundles[key]
        if unchanged:
            return _clone(cached)

    bundle = _tracked_bundle_type(base).for_track(document)

    # Check again after the entire initial load: an earlier file may have
    # changed while a later resource was being parsed.
    if not _unchanged(bundle):
        return bundle

    with _lock:
        _bundles[key] = bundle
        _bundles.move_to_end(key)
        while len(_bundles) > _MAX_BUNDLES:
            _bundles.popitem(last=False)

    # Never expose the snapshot: lazy retrieval and caller mutation must stay
    # local to one preparation. Copies can run outside the cache bookkeeping lock.
    return _clone(bundle)
