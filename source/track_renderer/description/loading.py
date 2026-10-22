"""Load a track and prepare the geometry that the drawing code will use.

The Track Description tools supply defaults, validate the input and resolve
placements. This module connects those tools to the renderer's API and
diagnostics. A prepared track represents one revision and can be rendered with
different drawing options without repeating that work.
"""

from __future__ import annotations

import importlib
import sys
from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any

from ..diagnostics import Diagnostic, RenderError
from .bundle_cache import bundle_for_track

if TYPE_CHECKING:
    from .types import (
        ExpansionResult,
        GeometryModel,
        GeometryResult,
        SchemaBundle,
        SourceDocument,
        UpstreamDiagnostic,
    )


def description_directory() -> Path:
    """@return The Track Description resources for this installation or checkout."""
    package = Path(__file__).resolve().parents[1]
    installed = package / "resources" / "track-description"
    if installed.is_dir():
        return installed

    checkout = package.parents[1] / "submodules" / "track-description"
    if not (checkout / "scripts" / "expand_track.py").is_file():
        raise RenderError("Track Description resources are missing; initialize the submodule")
    return checkout


@lru_cache(maxsize=1)
def upstream() -> tuple[ModuleType, ModuleType]:
    """@return Expansion and geometry modules in a private import namespace.

    Upstream scripts use relative imports when loaded as a package. Isolating
    their namespace avoids modifying sys.path or claiming a global `scripts` name.
    """
    name = "track_renderer._track_description"
    package = ModuleType(name)
    package.__path__ = [str(description_directory() / "scripts")]
    sys.modules.setdefault(name, package)
    return (
        importlib.import_module(name + ".expand_track"),
        importlib.import_module(name + ".validate_geometry"),
    )


@dataclass(frozen=True)
class PreparedTrack:
    """@brief Keep a track's resolved input and validation results for reuse.

    Treat the upstream result objects as read-only. Prepare again after editing
    the description or changing the schema bundle.
    """

    expansion: ExpansionResult
    bundle: SchemaBundle
    geometry: GeometryResult | None
    diagnostics: tuple[Diagnostic, ...]
    validation: dict[str, Any]
    model: GeometryModel | None

    @property
    def track_id(self) -> str:
        """@return The prepared track's identifier."""
        return self.expansion.track["id"]

    @property
    def source_uri(self) -> str:
        """@return The source URI used to resolve this revision's references."""
        return self.expansion.source.uri

    @property
    def expanded_track(self) -> dict[str, Any]:
        """@return An independent copy of the expanded Track Description."""
        return deepcopy(self.expansion.track)

    @property
    def valid(self) -> bool:
        """@return Whether all prerequisite checks completed successfully."""
        return self.validation.get("valid") is True


def prepare_track(
    track: str | Path | dict[str, Any] | PreparedTrack,
    *,
    source_uri: str | None = None,
) -> PreparedTrack:
    """@brief Apply defaults and check the track before it is drawn.

    @param track File/URI, in-memory description, or an already prepared revision.
    @param source_uri Source document URI for relative references in dictionaries.
    @return Reusable result, including failed or incomplete validation.
    @throws RenderError If the document or its schema resources cannot be loaded.
    """
    if isinstance(track, PreparedTrack):
        return track

    expansion_module, geometry_module = upstream()
    try:
        document = _load_document(track, source_uri, expansion_module)
        bundle = bundle_for_track(document, expansion_module)
        expanded = expansion_module.expand_track(document, bundle=bundle)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        diagnostic = Diagnostic("input.unavailable", str(exc))
        raise RenderError(str(exc), (diagnostic,)) from exc

    geometry = None
    failure = None
    try:
        geometry = geometry_module.validate_geometry(expanded, bundle=bundle)
        report = geometry.report()
        findings = geometry.diagnostics
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        # An input can load successfully but still lack data needed to build its
        # geometry. Keep that failure available to the editor's forced preview.
        failure = Diagnostic("validation.unavailable", str(exc))
        report = {"stage": "geometry", "valid": None, "checks": [], "diagnostics": []}
        findings = expanded.diagnostics

    diagnostics = _validation_diagnostics(findings, report, failure)
    model = geometry.model if geometry is not None else None
    if model is None:
        model, recovered_findings = _partial_model(expanded, bundle, geometry_module)
        diagnostics.extend(recovered_findings)

    return PreparedTrack(expanded, bundle, geometry, tuple(diagnostics), report, model)


def _load_document(
    track: str | Path | dict[str, Any], source_uri: str | None, module: ModuleType
) -> SourceDocument:
    """Read a file, or wrap a private copy of an in-memory track with its base URI."""
    if not isinstance(track, dict):
        return module.load_track(track)

    if source_uri is None:
        reference = track.get("$schema", "")
        if not isinstance(reference, str) or not (
            ":" in reference or Path(reference).is_absolute()
        ):
            raise ValueError("A dictionary with relative $schema needs source_uri")
        source_uri = description_directory().as_uri() + "/input.json"

    return module.Document(deepcopy(track), source_uri)


def _diagnostic(finding: UpstreamDiagnostic, *, include_schema_ref: bool = False) -> Diagnostic:
    """Translate an upstream finding without changing its source information."""
    details = finding.details
    if include_schema_ref:
        details = {**details, **({"schema_ref": finding.schema_ref} if finding.schema_ref else {})}

    return Diagnostic(
        code=finding.code,
        message=finding.message,
        path=finding.path,
        severity=finding.severity,
        source=finding.source,
        details=details,
    )


def _validation_diagnostics(
    findings: list[UpstreamDiagnostic], report: dict[str, Any], failure: Diagnostic | None
) -> list[Diagnostic]:
    """Include blocked checks so an incomplete validation always has an explanation."""
    diagnostics = [_diagnostic(finding, include_schema_ref=True) for finding in findings]
    if failure is not None:
        diagnostics.append(failure)

    for check in report["checks"]:
        blocked = check.get("details", {}).get("blocked_paths", {})
        for path, reason in blocked.items():
            diagnostics.append(
                Diagnostic("validation.blocked", reason, path, details={"check": check["code"]})
            )

    if report["valid"] is not True and not any(d.severity == "error" for d in diagnostics):
        diagnostics.append(
            Diagnostic("validation.incomplete", "Prerequisite validation is incomplete")
        )
    return diagnostics


def _partial_model(
    expanded: ExpansionResult, bundle: SchemaBundle, module: ModuleType
) -> tuple[GeometryModel | None, list[Diagnostic]]:
    """Build whatever geometry remains usable after the normal preparation failed."""
    result = module.GeometryResult(expansion=expanded)
    reporter = module.Reporter(result, expanded, module.CHECKS)
    diagnostics = []
    try:
        model = module.GeometryModel(expanded, bundle, reporter)
    except (ValueError, KeyError, TypeError) as exc:
        return None, [Diagnostic("render.model_unavailable", str(exc))]

    # Later steps may still succeed for unaffected sections. Record each failed
    # step and continue, while leaving the original validation result unchanged.
    for step in (
        "build_sections",
        "assemble",
        "build_surfaces",
        "index_objects",
        "intervals",
        "resolve_zones",
        "place_features",
    ):
        try:
            getattr(model, step)()
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            diagnostics.append(Diagnostic("render.partial_model", str(exc), details={"step": step}))

    reporter.finish()
    diagnostics.extend(_diagnostic(finding) for finding in result.diagnostics)
    return model, diagnostics
