"""Turn a prepared track into the scene used by every exporter.

Rendering first plans markings across section boundaries, then adds the sections
and their contents. Each call creates its own scene, so drawing options can
change without modifying a prepared track or an earlier result.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .actors import compile_actor
from .description import PreparedTrack, prepare_track
from .diagnostics import RenderError
from .elements import COMPILERS
from .features import compile_feature
from .markings.planning import build_phases
from .options import RenderOptions
from .rendering.context import Context
from .sections.compilation import compile_section
from .svg import SvgDocument
from .zones import compile_zone


def render(
    track: str | Path | dict[str, Any] | PreparedTrack,
    *,
    source_uri: str | None = None,
    force: bool = False,
    options: RenderOptions | None = None,
) -> SvgDocument:
    """@brief Prepare the track if needed and build its self-contained SVG document.

    @param track Authored/expanded description, file/URI, or a prepared revision.
    @param source_uri Base document URI for dictionary inputs with relative refs.
    @param force Return usable parts despite validation or rendering failures.
    @param options Drawing settings, including projection suppression by type.
    @return SVG with native drawing elements, semantic annotations and embedded artwork.
    @throws RenderError If validation is not positive or rendering is incomplete,
        unless force=True. Unreadable inputs cannot be rendered even with force.
    """
    prepared = prepare_track(track, source_uri=source_uri)
    if not prepared.valid and not force:
        raise RenderError("Track validation failed or could not finish", prepared.diagnostics)

    ctx = Context(prepared, options or RenderOptions())
    if ctx.model is None:
        ctx.issue("", "No geometric model could be assembled")
    else:
        # Plan shared dash coordinates before individual sections draw their
        # pieces. This also prepares the junction controls used by generated signs.
        ctx.attempt("/sections", lambda: build_phases(ctx))
        for path, obj in ctx.drawing.objects.items():
            if obj.category == "sections":
                ctx.attempt(path, lambda path=path: compile_section(ctx, path))

        for path, obj in ctx.drawing.objects.items():
            if obj.category == "elements" and obj.type not in {"parking_lot", "parking_spot"}:
                compiler = COMPILERS.get(obj.type)
                if compiler is None:
                    ctx.issue(path, f"Unknown element type: {obj.type}")
                else:
                    ctx.attempt(path, lambda path=path, compiler=compiler: compiler(ctx, path))

        for path, obj in ctx.drawing.objects.items():
            if obj.category == "features":
                ctx.attempt(path, lambda path=path: compile_feature(ctx, path))
            elif obj.category == "actors":
                ctx.attempt(path, lambda path=path: compile_actor(ctx, path))
            elif obj.category == "zones":
                ctx.attempt(path, lambda path=path: compile_zone(ctx, path))

    if not ctx.drawing.complete and not force:
        raise RenderError("Scene geometry is incomplete", tuple(ctx.drawing.diagnostics))
    return ctx.drawing.finish()
