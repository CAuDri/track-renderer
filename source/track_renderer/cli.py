"""Connect command-line arguments to the public rendering and export functions.

Drawing output goes to a file or stdout; diagnostics go to stderr. The exit
status distinguishes an incomplete track from an input or output failure, so
editor tasks and shell scripts can react without parsing error messages.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import NoReturn

from .api import render
from .diagnostics import Diagnostic, RenderError
from .exporters import export_jpg, export_svg
from .io import write_file
from .options import PROJECTION_TYPES, RenderOptions
from .svg import SvgDocument


def _color(text: str, kind: str) -> str:
    """@brief Style terminal diagnostics while keeping redirected output plain."""
    code = {"warning": "33", "error": "31", "code": "36"}.get(kind)
    if (
        code
        and sys.stderr.isatty()
        and not os.environ.get("NO_COLOR")
        and os.environ.get("TERM") != "dumb"
    ):
        return f"\033[{code}m{text}\033[0m"
    return text


def _print_message(severity: str, message: str) -> None:
    """@brief Print a diagnostic with its severity highlighted."""
    print(f"{_color(severity + ':', severity)} {message}", file=sys.stderr)


def _print_findings(findings: Iterable[Diagnostic]) -> None:
    for finding in findings:
        _print_message(
            finding.severity,
            f"{_color(finding.code, 'code')} {finding.path}: {finding.message}",
        )


class _ArgumentParser(argparse.ArgumentParser):
    """Keep argument-error prefixes consistent with renderer diagnostics."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: {_color('error:', 'error')} {message}\n")


def _make_parser() -> _ArgumentParser:
    """Collect input, drawing and export options in one place."""
    parser = _ArgumentParser(description="Render a CAuDri track into SVG or JPEG")
    parser.add_argument("track", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("--format", choices=["svg", "jpg"])
    parser.add_argument(
        "--force", action="store_true", help="emit usable parts despite diagnostics"
    )
    parser.add_argument(
        "--no-projections",
        action="store_true",
        help="retain physical parts and poses without optional 2D depictions",
    )
    parser.add_argument(
        "--pose-only",
        action="append",
        default=[],
        choices=sorted(PROJECTION_TYPES),
        help="omit the 2D projection of this object type; repeatable",
    )
    parser.add_argument("--curve-tolerance", type=float)
    parser.add_argument("--margin", type=float, default=0.5)
    parser.add_argument("--scale", type=float, default=1)
    parser.add_argument(
        "--svg-responsive",
        action="store_true",
        help="omit physical SVG dimensions so previews fit their viewport",
    )
    parser.add_argument(
        "--dpi",
        type=float,
        default=20,
        help="JPEG pixels per inch at 1:1 Map scale; default 20",
    )
    parser.add_argument("--width", type=int)
    parser.add_argument("--report", type=Path)
    parser.add_argument(
        "--section",
        action="append",
        default=[],
        metavar="SECTION",
        help="show only this section and its owned objects; repeatable",
    )
    return parser


def _output_format(args: argparse.Namespace, parser: _ArgumentParser) -> str:
    """Check distinct file paths and infer the format when it was not supplied."""
    paths = [p.resolve() for p in (args.track, args.output, args.report) if p is not None]
    if len(paths) != len(set(paths)):
        parser.error("Input, output and report paths must differ")

    format_name = args.format
    if format_name is None:
        suffix = args.output.suffix.lower() if args.output else ".svg"
        format_name = {".svg": "svg", ".jpg": "jpg", ".jpeg": "jpg"}.get(suffix)
        if format_name is None:
            parser.error("Use --format for an output without a recognized extension")
    return format_name


def _export_drawing(
    drawing: SvgDocument, args: argparse.Namespace, format_name: str
) -> str | bytes:
    if format_name == "svg":
        return export_svg(
            drawing, margin=args.margin, scale=args.scale, responsive=args.svg_responsive
        )
    return export_jpg(drawing, dpi=args.dpi, width=args.width, margin=args.margin)


def _write_output(output: str | bytes, destination: Path | None) -> None:
    if destination is not None:
        write_file(destination, output)
    elif isinstance(output, bytes):
        sys.stdout.buffer.write(output)
    else:
        sys.stdout.write(output)


def _write_report(path: Path, report: dict[str, object]) -> None:
    write_file(path, json.dumps(report, indent=2) + "\n")


def main(argv: list[str] | None = None) -> int:
    """@brief Render a track; return 0 for success, 1 for findings, 2 for input/output errors."""
    parser = _make_parser()
    args = parser.parse_args(argv)
    format_name = _output_format(args, parser)

    try:
        drawing = render(
            args.track,
            force=args.force,
            options=RenderOptions(
                pose_only=frozenset(args.pose_only),
                curve_tolerance=args.curve_tolerance,
                projections=not args.no_projections,
            ),
        )
        if args.section:
            drawing = drawing.select_sections(args.section)
        output = _export_drawing(drawing, args, format_name)
        _write_output(output, args.output)

        if args.report:
            _write_report(
                args.report,
                {
                    "complete": drawing.complete,
                    "validation": drawing.validation,
                    "diagnostics": [d.to_dict() for d in drawing.diagnostics],
                },
            )
        _print_findings(drawing.diagnostics)
        return 0 if drawing.complete and drawing.validation.get("valid") is True else 1

    except RenderError as exc:
        _print_message("error", str(exc))
        _print_findings(exc.diagnostics)

        if args.report:
            try:
                _write_report(
                    args.report,
                    {"complete": False, "diagnostics": [d.to_dict() for d in exc.diagnostics]},
                )
            except OSError as report_error:
                _print_message("error", f"Cannot write report: {report_error}")
                return 2

        return 2 if any(d.code.startswith("input.") for d in exc.diagnostics) else 1
    except (ValueError, OSError) as exc:
        _print_message("error", str(exc))
        return 2
