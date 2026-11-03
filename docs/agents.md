# Agent reference: CAuDri Track Renderer

> [!IMPORTANT]
> This is just an additional and mostly redundant documentation for the track renderer. It is written by an agent for an agent.
> Read it if you want, but it primarily serves as an entry point for AI agents that want to use the library.

This file is a self-contained working map of the library: how to use it, where
behavior is implemented, and which contracts to preserve while changing it.
Human-facing entry points are the [README](../README.md),
[Python API](python_api.md) and [SVG format guide](svg_format.md). Source code and the pinned
Track Description resources determine the actual behavior.

## Repository and working constraints

- Repository text, code, comments and documentation are English. Conversation with
  the maintainer may be German.
- Development and verification are local. Do not add GitHub Actions or commit
  tests. `tests/` is ignored and excluded from source distributions. New temporary
  regression scripts, generated previews, audit output and builds belong under
  `/tmp`.
- Do not commit or publish without a request. Preserve unrelated edits, authored
  example tracks, backup files and generated files owned by the user.
- The license is MIT, Copyright (c) 2026 CAuDri e.V. Preserve `LICENSE` and the
  Track Description license.
- `submodules/track-description/` is a pinned Git submodule. Its schemas, catalog
  and validators are a separate project. Do not change them incidentally while
  modifying rendering. Resolve ambiguous placement, default and measurement
  semantics with the maintainer before changing their meaning.
- Keep module introductions and descriptive, natural-English docstrings. Doxygen
  tags are useful for parameters, results and exceptions. Explain intent,
  geometry and ownership where these are difficult to infer; avoid comments that
  repeat names or obvious statements. Separate logical steps with blank lines.

## Product and input/output boundary

The distribution is `track-renderer`, the import package is
`track_renderer`, and the command is `track-render`. Python 3.11 or newer
is required. Sources live under `source/track_renderer/` and include
`py.typed`.

Input is a CAuDri Track Description, authored or expanded, in YAML/JSON. The
description's `$schema` selects a schema bundle; expansion resolves catalog
defaults, implicit objects, source references and provenance. The renderer
produces a planar SVG drawing with embedded artwork and semantic metadata. JPEG
is rasterized from that SVG. The library calculates actor spawn poses; it does
not execute actor movement or construct a 3D world.

SVG elements are the drawing geometry. CAuDri metadata supplies ownership,
physical parts, source identity, validation and dependency information. SVG's
groups and drawing order are standard; concepts such as a road section or a
sign's physical pose are application semantics. There is no parallel exported
geometry collection. An ordinary SVG viewer needs only the SVG to display it.

The Track Description remains the editable road model. Moving an SVG group does
not update source metadata, connected sections or marking plans. Editing the
serialized source metadata changes what `to_track()` returns, but does not
recalculate geometry or physical parts. Edit and render the description to
recompute those relationships. Selection and presentation changes can reuse the
existing SVG without geometry compilation.

Full annotated drawings also preserve the expanded source model: `track` stores
global values and collection slots, and `objects` stores each semantic object
once. `drawing.to_track()` reassembles a new expanded dictionary without resource
access. Re-rendering that dictionary requires the referenced schema and artwork.
SVG export with `metadata=False` produces a compact presentation file; it cannot
be loaded by the semantic SVG loader or used for track reconstruction.

## Installation and resource layout

Initialize the pinned resources before installing from a checkout:

```sh
git submodule update --init --recursive
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[image,dev]"
```

The core install is `python -m pip install .`; `[image]` adds CairoSVG and Pillow,
and `[dev]` adds pytest and Ruff. CairoSVG's Python dependencies include the
`cairocffi` bridge, but this dependency chain does not bundle the native Cairo
shared library. Install that runtime separately through the operating system's
package manager; see [CairoSVG installation](https://cairosvg.org/documentation/#installation)
for platform requirements. Builds from source may also need development headers
and a compiler. SVG rendering, loading, selection and track reconstruction do
not import these optional image libraries or require native Cairo.

| Dependency | Use |
| --- | --- |
| PyYAML | Track Description YAML loading. |
| jsonschema, referencing | Upstream schema validation and reference resolution. |
| Shapely | Road surfaces, corridors, intersections and geometric operations. |
| segno | Landmark QR generation. |
| tinycss2 | Passive SVG artwork CSS checks. |
| CairoSVG, Pillow (`image`) | SVG rasterization and opaque JPEG encoding. |

Hatchling is the build backend. All package and resource inclusion rules live in
`pyproject.toml`; there are no custom build hooks. Wheels contain the Python
package from `source/track_renderer/`, including `py.typed`. Wheel `force-include`
entries copy the pinned schema files, license, scripts and assets into
`track_renderer/resources/track-description/`.

Each schema file and the upstream license has an explicit source path; scripts
and assets use directory mappings. The source-distribution target force-includes
the same resources at their checkout paths, so its archives can build wheels
independently. A missing force-included path stops wheel, source-distribution and
editable builds with Hatchling's standard error. These rules do not check file
contents, individual script names, asset categories or catalog references.
Initialize the submodule before building from a checkout. Complete source
archives need no Git executable or Git metadata to build.

`description_directory()`
uses these installed resources first, then the checkout submodule. Upstream
scripts are imported once under the private namespace
`track_renderer._track_description`; the loader does not modify `sys.path`
or claim a global `scripts` package.

The source-distribution rules select the library and required upstream resources,
`docs/*.md`, `docs/img/*.{png,svg}`, `docs/scripts/*.py` and root-level
`examples/*.{yaml,py}`. Nested example directories are not covered by those
example patterns. Project metadata supplies the README and license. Tests and
local builds are outside these selections; `**/*.preview.svg` is explicitly
excluded. Other generated images can match the documentation inclusion rules;
inspect the archive when changing those rules or adding assets.

### Reference resolution

Track Description expansion resolves references before rendering. These bases
are distinct:

| Reference | Resolution base |
| --- | --- |
| Relative input `$schema` | The source document URI, supplied by the file loader or the API's `source_uri`. |
| Relative `rendering.asset_path` | The selected bundle's catalog URI. Expansion records the resulting absolute asset base. |
| Relative object `rendering.asset` | The resolved asset base, after substituting supported parameter placeholders. |
| Metadata `schema_ref` | The expanded `track.$schema` URI; independent of the SVG file's location. |

Absolute asset URIs do not depend on the asset base. For application-owned local
artwork, use an absolute URI for `rendering.asset_path` or for each asset, for
example `Path("artwork").resolve().as_uri()`. Expansion normalizes the asset base
with a trailing slash. `source_uri` does not make artwork paths relative to the
track file. Bundled resources supply defaults; they do not redirect every
authored reference to the installed resource directory.

### VS Code preview

The Git checkout includes `.vscode/tasks.json`, `settings.json` and
`extensions.json`. Preview tasks invoke the repository's `.venv/bin/python`
(`.venv/Scripts/python.exe` on Windows) with `PYTHONPATH` set to `source/`.
The default build task renders the active track into its sibling
`preview/<fileBasenameNoExtension>.preview.svg`, then opens that file through
`code --reuse-window` (`code.cmd` on Windows), so the editor CLI must be on PATH.
The recommended extensions are `vitaliymaz.vscode-svg-previewer`,
`gruntfuggly.triggertaskonsave` and `seunlanlege.action-buttons`; they provide the
preview editor, render-on-save trigger and Track Preview status-bar button.
The save trigger is configured for YAML/YML/JSON files and does not depend on an
open preview. It runs a full render; the library itself has no file watcher.

### Documentation assets and regeneration

`docs/img/track_renderer_header.png` is the README title illustration, with a YAML
excerpt, an arrow and the actual rendering of `examples/example_track.yaml`.
The complete example is a closed oval with a crosswalk and a checkered starting
line. Run `.venv/bin/python docs/scripts/render_header.py` with the image extra
installed to regenerate the PNG and its vector counterpart
`docs/img/track_renderer_header.svg`. The script reads the excerpt from the YAML
and uses the public renderer for the drawing. The composed SVG is a documentation
illustration; use the renderer to export an annotated track document.

`docs/svg_format.md` describes the output format: document structure, geometry
annotations, expansion provenance, physical parts, coordinates and section
selection. Keep it concise and descriptive, with downstream applications in mind
but without tool-building tutorials. `examples/track.yaml` is
its compact reference input: connected sections, a junction, a crosswalk with
generated signs, a centerline zone and a spawned actor. Its `map_orientation` is
0 degrees: the Map x-axis points right in the display. Primitive coordinates and
metadata poses use the Map frame.

The guide's three annotated examples come from this same input:

- `docs/img/track.svg`: complete rendering with all projections enabled.
- `docs/img/track_no_projections.svg`: `RenderOptions(projections=False)`;
  identical `objects` and `parts`, without optional projection geometry or artwork
  used only by those projections.
- `docs/img/track_west_approach.svg`: the complete rendering filtered through
  `select_sections(["west_approach"])`; includes the crosswalk and generated signs,
  excludes the global actor, and retains original Map coordinates.

`examples/curved_track.yaml` is a separate 65-degree arc with a 3 m radius
and a partial centerline zone. `docs/img/curved_track.svg` is its complete
annotated rendering, used to measure the road surface and curved zone selection geometry.

Eight generated figures are embedded in `docs/svg_format.md`. Each contains
one track excerpt with a transparent outer canvas, a few colored markers and
short labels. Most copied Map groups use only
the y flip for an unrotated detail view. The main reference exports use the same
zero-degree orientation as the source track. Keep explanatory text in the guide; avoid text
cards, title banners and white backgrounds in the figures.

Annotation colors are centralized by meaning in `docs/scripts/render_svg_figures.py`:

| Subject | Color |
| --- | --- |
| Sections and section bounds | Blue `#3478C7` |
| Elements such as crosswalks | Teal `#388E91` |
| Physical parts and their depictions: signs, waiting areas and actor bodies | Pink `#BC3D7B` |
| Zones, their selection regions, bounds and influence on geometry | Gold `#C38618` |
| Road markings and generic paint-layer callouts | Violet `#8B78B4` |
| Surface callouts, reference lines, angles and presentation-status labels | Gray `#78828C` |
| Map x / y axes | Red `#E45756` / green `#16B970` |

The subject determines the color even in paint-layer and selection illustrations.
A zone's influence on a centerline is gold; a callout about the marking itself is
violet. The overview's generic paint-layer callout points to the upper-lane
surface in layer 0. Shape, opacity and line style distinguish filled regions, dashed bounds,
pose handles and faded context. Renderer geometry keeps its native colors,
including the red waiting-area projections. The overview uses 22 px titles,
16 px attribute labels and smaller handles; the detail figures use 27 px labels.

- `docs/img/svg_format_overview.svg`: opening overview of the reference track,
  showing section ownership, a crosswalk source object, a sign's physical part,
  zone contributors and a paint layer. The global actor is omitted; geometry
  and poses retain their Map coordinates and are shown without display rotation.
- `docs/img/svg_object_links.svg`: section, crosswalk stripes and a generated
  sign marked within the same road excerpt.
- `docs/img/svg_projection_poses.svg`: projections disabled, with the retained
  sign-panel pose marked from metadata. Colored outlines, crosshairs and labels
  belong to the guide, not the exported track.
- `docs/img/svg_layers.svg`: surface, road-marking, waiting-area projection and
  artwork paint layers. The red waiting-area outline is a projection in layer 30.
- `docs/img/svg_zone_contributors.svg`: section-owned centerlines influenced by
  a zone, with its normally invisible selection boundary outlined.
- `docs/img/svg_curved_bounds.svg`: actual arc surface and zone selection region
  with their axis-aligned bounds. Bounds are computed from native SVG vertices
  for the illustration; the export has no extra semantic bounding-box fields.
- `docs/img/svg_section_selection.svg`: selected section geometry and owned
  signs stay bright; excluded surroundings and the global actor fade as context.
  The copied actor geometry and its annotation are translated to Map x=2.8 for
  this illustration, with the label on the left. Source poses remain unchanged.
- `docs/img/svg_map_orientation.svg`: a 35-degree counter-clockwise rotation of
  the west approach with matching Map axes and an angle marker. Axis arrows and
  labels use the Track Description colors: x `#E45756`, y `#16B970`.

The orientation illustration overrides the copied group's angle to 35 degrees
without changing the source track or its zero-degree reference exports.

`docs/scripts/render_reference.py` regenerates the four examples through the
public render/load/write API. `docs/scripts/render_svg_figures.py` composes the
eight figures from those exports, retaining native geometry and shared artwork
references. Both locate inputs relative to their own files and can run
independently of the current directory. From the repository root:

```sh
.venv/bin/python docs/scripts/render_reference.py
.venv/bin/python docs/scripts/render_svg_figures.py
```

The generator replaces the current repository's absolute file-URI prefix with
`file:///workspace/track-renderer`, giving the reference reproducible resource
locations across developer checkouts. Those locations describe provenance and
dependencies; the rendered SVG already embeds its artwork and needs no files at
that synthetic path to display or reload. The generator indents both the XML and
its JSON metadata for inspection, validates the formatted SVG, and writes it
atomically. The composed figures are documentation illustrations, not annotated
track documents accepted by `load_svg()`. Keep the YAML, generated examples,
figures and guide aligned when changing output. Preserve authored YAML changes
when regenerating the SVGs.

## Public Python API

Import public names from `track_renderer`. Its complete export list is
`Diagnostic`, `PreparedTrack`, `RenderError`, `RenderOptions`, `SvgDocument`,
`SvgError`, `dependency_uris`, `export_jpg`, `export_svg`, `load_svg`,
`prepare_track`, `render`, `renderer_fingerprint` and `write_file`.
Internal module paths, compiler records and upstream objects are implementation
interfaces.

| Operation | Contract |
| --- | --- |
| `prepare_track(track, *, source_uri=None)` | Accepts a file/URI string, `Path`, dictionary or `PreparedTrack`. Returns expanded input, validation and usable geometry. An existing prepared object is returned unchanged. |
| `render(track, *, source_uri=None, force=False, options=None)` | Accepts the same input forms; returns a new independent `SvgDocument`. Strict rendering requires positive validation and complete drawing. |
| `RenderOptions(pose_only=frozenset(), curve_tolerance=None, projections=True)` | Frozen options. `pose_only` is normalized to a frozenset. Chord tolerance must be positive and finite; `None` uses the bundle's approximation setting. |
| `load_svg(source)` | Accepts a file path, XML string or UTF-8 bytes. Loads the renderer's annotated SVG profile without opening the original track, schemas or artwork. |
| `export_svg(drawing, *, margin=.5, scale=1, responsive=False, metadata=True)` | Returns standalone SVG text. Equivalent to `drawing.to_svg(...)`. |
| `export_jpg(drawing, *, dpi=20, width=None, margin=.5, quality=95)` | Returns opaque JPEG bytes. Positive pixel width overrides DPI-based sizing; aspect ratio follows the exported viewBox. DPI also sets nominal print density. Quality is an integer 1–100. |
| `write_file(path, content)` | Atomically replaces a destination with UTF-8 text or bytes using a temporary file in the same directory. Parent directories must already exist. |
| `dependency_uris(prepared, drawing)` | Returns sorted input/schema/artwork dependency URIs, including attempted artwork reads. |
| `renderer_fingerprint()` | Hashes renderer/upstream code, Python version and core dependency versions without preparing a track. |

`PreparedTrack` is a frozen wrapper with `track_id`, `source_uri`, `valid`,
`validation`, `diagnostics`, and `expanded_track`. The expanded dictionary is a
deep copy. Treat all other nested state as read-only, including `validation`,
diagnostic details and the upstream `expansion`, `bundle`, `geometry` and `model`
objects. The wrapper being frozen does not make those objects immutable. Prepare
again after source or bundle changes; passing an existing prepared object does
not check files for changes.

A dictionary is copied before expansion and must contain its own `$schema` value;
the file loader does not invent this field. A relative `$schema` requires
`source_uri`, normally `Path("track.yaml").resolve().as_uri()`. That URI supplies
a resolution base and diagnostic identity: the source file need not exist and
is not read when input is a dictionary. The referenced schema must still be
accessible. Without `source_uri`, an absolute schema reference allows the loader
to establish a synthetic source URI in the renderer's Track Description resource
directory. It does not use the custom schema's parent directory as the source
base. Artwork uses the separate asset-base rules above.

Example, run from the repository root:

```python
from pathlib import Path
from tempfile import gettempdir

from track_renderer import (
    RenderOptions,
    dependency_uris,
    export_jpg,
    load_svg,
    prepare_track,
    render,
    write_file,
)

source = Path("examples/intersection_showcase.yaml").resolve()
output = Path(gettempdir()) / "caudri-agent-example"
output.mkdir(exist_ok=True)

prepared = prepare_track(source)
drawing = render(prepared)
drawing.write(output / "track.svg", responsive=True)

reopened = load_svg(output / "track.svg")
expanded = reopened.to_track()
assert expanded == prepared.expanded_track

# Export a compact illustration while retaining the original semantic drawing.
drawing.write(output / "track_plain.svg", metadata=False)

selection = drawing.select_sections(["crossing"])
selection.write(output / "crossing.svg", responsive=True)
assert load_svg(output / "crossing.svg").track_id == drawing.track_id
# Selection keeps full-source context but cannot be reconstructed with to_track().

physical = render(prepared, options=RenderOptions(projections=False))
assert physical.parts == drawing.parts
print(drawing.bounds(), dependency_uris(prepared, drawing))

# Requires the image extra and native Cairo.
write_file(output / "crossing.jpg", export_jpg(selection, width=1200))
```

### Document access and mutation

| Member | Behavior |
| --- | --- |
| `root` | The actual `xml.etree.ElementTree.Element` drawing root, mutable by the caller. |
| `metadata` | A newly decoded copy of the complete semantic payload. |
| `track_id`, `schema_uri`, `map_orientation`, `complete` | Scalar metadata accessors. |
| `validation` | Independent report dictionary; `valid` is separate from rendering completeness. |
| `diagnostics` | A new list of `Diagnostic` instances. |
| `objects`, `parts`, `assets` | Independent dictionaries keyed by their semantic/asset IDs; values are dictionaries, not compiler dataclasses. |
| `dependencies` | Tuple of dependency URIs stored in the document. |
| `bounds()` | Conservative visible bounds `(left, bottom, right, top)` in unrotated Map meters, or `None`; excludes the Map group's display transform and does not perform full metadata/profile validation. |
| `validate()` | Validate supported SVG structure, embedded artwork and semantic cross-links. |
| `to_svg(*, margin=.5, scale=1, responsive=False, metadata=True)` | Validate, copy, frame and serialize XML with a declaration and final newline; leaves `root` unchanged. False metadata exports presentation-only SVG. |
| `write(path, *, margin=.5, scale=1, responsive=False, metadata=True)` | Atomically write `to_svg(...)`. |
| `select_sections(ids, *, fit_viewbox=True)` | Validate and return an independent ownership selection. |
| `to_track()` | Return a newly assembled expanded Track Description from a full drawing's source metadata; reject selections or inconsistent source structure with `SvgError`. |

Changing a dictionary returned by `objects`, `parts`, `assets` or `metadata` does
not update the document. Cache one returned mapping while inspecting many
records: each property access decodes the semantic payload again. Direct XML
changes affect rendering but do not recalculate physical poses or source data.
Saving and loading require the supported profile, so arbitrary external-editor
changes may need to stay outside these helpers.

Projection categories accepted by `pose_only` are `traffic_sign`, `landmark`,
`static_obstacle`, `dynamic_obstacle`, `pedestrian` and `crosswalk_waiting_area`.
`projections=False` suppresses optional depictions globally. Physical parts and
poses remain. Road surfaces, painted markings, mandatory-turn guidance and
invisible selection corridors have separate purposes. Artwork needed only by an
omitted projection is not necessarily loaded or embedded. Suppressed geometry is
absent, rather than hidden with opacity; enabling it requires another render,
which can reuse the same `PreparedTrack` with different options.

### Export dimensions

Margin is finite, nonnegative and measured in meters. SVG scale is a positive
finite physical scale denominator: `10` means 1:10, without changing drawing
coordinates. Physical width/height are millimeters; responsive output omits
them and retains the viewBox. Scale is still validated when responsive sizing is
enabled. Saving normally recomputes framing from visible
geometry after the Map group's display transform, with the requested margin.
An empty drawing can be saved as SVG with a
default 1×1 viewBox centered at the origin.

`fit_viewbox=False` selection marks the document with
`data-fixed-viewbox="true"`. This preserves its existing frame through saving and
loading. Margin no longer changes that frame; scale and responsive sizing still
apply. JPEG uses the exported viewBox, including fixed framing, and requires
drawable geometry. Its `dpi` is relative to the full-size Map geometry:
`pixel_width = round(viewBox_width_in_meters * dpi / 0.0254)`. The viewBox already
includes the margin. Default `dpi=20` gives approximately 787.4 pixels per meter.
Explicit positive integer `width` overrides this
calculation; height follows the viewport aspect ratio. SVG scale is not applied
to JPEG dimensions.

DPI must be finite and positive, and `round(dpi)` must be between 1 and 65,535,
even with explicit width. It also sets nominal JPEG print-density metadata
independently of raster sizing. JFIF stores
whole-number densities: requested `20.4` DPI is recorded as `20`, while the
fractional value remains in the raster-size calculation when width is omitted.
Dimensions must be at least one pixel. Exports exceeding 100 million pixels or
32,767 pixels per axis are rejected before rasterization, with a suggestion to
reduce DPI or width. Cairo errors raised during rasterization become export
`ValueError`s. Missing Python image dependencies also produce a `ValueError`
requesting the image extra; an unavailable native Cairo runtime can instead
raise `OSError` while importing CairoSVG.
CLI JPEG quality is fixed at the API default of 95.

## CLI contract

`track-render TRACK [options]` and `python -m track_renderer TRACK [options]`
have the same interface. `TRACK` is a YAML/JSON file path; CLI input does not use
the API's in-memory/URI forms. Drawing output goes to `-o` or stdout; findings go
to stderr. Without an output path the format defaults to SVG. Extensions `.svg`,
`.jpg` and `.jpeg` infer formats; other suffixes require `--format`.

| Option | Meaning/default |
| --- | --- |
| `-h`, `--help` | Argument help. |
| `-o PATH`, `--output PATH` | Destination file; existing output is atomically replaced. |
| `--format {svg,jpg}` | Explicit format override. |
| `--force` | Attempt usable rendering despite validation or compilation findings. |
| `--section SECTION` | Keep a section and its owned descendants; repeatable. Selection follows full source rendering. |
| `--no-projections` | Suppress optional drawings globally. |
| `--pose-only TYPE` | Suppress one supported projection category; repeatable. |
| `--curve-tolerance FLOAT` | Positive finite maximum chord error in meters; catalog default if absent. |
| `--margin FLOAT` | SVG/JPEG margin in meters; default `0.5`. |
| `--scale FLOAT` | SVG physical scale denominator; default `1`; ineffective with responsive output. |
| `--svg-responsive` | Omit SVG physical width/height, retain viewBox. |
| `--no-metadata` | SVG only: omit track JSON, semantic attributes, selection aids and unnecessary IDs/groups from the export. Does not affect the in-memory drawing, reports or JPEG output. |
| `--dpi FLOAT` | Positive finite JPEG dots per inch of full-size Map geometry; rounded density must be 1–65,535. Default `20` (approximately 787.4 pixels per meter). Also sets nominal print-density metadata. |
| `--width INT` | Positive JPEG width in pixels; overrides DPI-based pixel sizing. |
| `--report PATH` | Separate JSON report with `schema_uri`, `complete`, `validation` and `diagnostics`. |

Input, output and report paths must resolve to different paths. Parent output
directories must exist. `reporting.build_report()` constructs both report forms.
Successful/forced drawing reports resolve relative `schema_ref` values against
their `schema_uri`. A `RenderError` report has `complete: false`, `schema_uri: null`,
`validation: null` and original diagnostics with absolute schema references.
Argument errors and other failures before report writing do not
guarantee a report. Exit status is part of the integration contract:

| Code | Meaning |
| --- | --- |
| `0` | Complete rendering and `validation.valid is True`; warnings are allowed. |
| `1` | Invalid/incomplete validation or incomplete rendering; forced mode may have emitted usable output. |
| `2` | Argument, input or output error. |

```sh
.venv/bin/track-render examples/intersection_showcase.yaml -o /tmp/caudri-crossing.svg --section crossing --svg-responsive --report /tmp/caudri-crossing.report.json
```

## Pipeline, validation and error handling

```text
Description path/URI/dictionary
  -> prepare_track: load document and bundle, expand defaults, validate
  -> PreparedTrack: expanded source, provenance, findings, geometry model
  -> render: Context + semantic index + placement/route index
  -> build_phases: continuous marking runs, control gaps, junction preparation
  -> section compilers: reference parts, surfaces, lane paint
  -> element compilers: crossings, parking, starting areas and other elements
  -> feature, actor and zone compilers: placed parts, artwork, selection corridors
  -> DrawingBuilder.finish: ordered native SVG, embedded assets, semantic metadata
  -> SvgDocument: inspect / select / serialize / rasterize
```

Preparation invokes upstream expansion and `validate_geometry()`, which includes
structural/schema validation. The renderer enables the normal schema and planar
geometry check groups and exposes no per-group skip/allow/deny interface. The
full competition-rule validator is a separate upstream operation. Successful
rendering is not evidence of competition compliance. Changing `force` changes
failure handling, not which prerequisite validation groups run.

Input/schema loading failures become `RenderError` with an `input.unavailable`
diagnostic. A failed or blocked validation can still return `PreparedTrack`:
`valid` is true only if the report's `valid` is exactly `True`. Reports can be
false or incomplete (`None`). Blocked paths become `validation.blocked`
diagnostics, and an otherwise unexplained incomplete report gets
`validation.incomplete`.

If normal validation leaves no geometry model, preparation attempts a partial
model through `build_sections`, `assemble`, `build_surfaces`, `index_objects`,
`intervals`, `resolve_zones` and `place_features`. Failed recovery steps produce
findings without changing the original validation result. Strict `render()`
rejects a nonvalid prepared input before compiling; forced rendering attempts the
remaining usable geometry. Unreadable input cannot be rendered this way.

Every render creates a fresh `Context`, `DrawingBuilder`, semantic index and
instance/route index. The context shallow-copies the upstream model wrapper to
adjust approximation tolerance; prepared sections and placements remain shared,
read-only data. It copies diagnostics and validation before compiling.

`Context.attempt()` converts expected `RenderFailure`, `OSError` and Shapely
`GEOSException` failures into source-linked findings and continues. On invalid
prepared input it also records expected failures from missing/malformed values.
Unexpected key/type/value/attribute errors on validated input propagate for
debugging. Error-severity findings set `complete=False`; warnings do not. Strict
rendering raises `RenderError` when drawing is incomplete. Forced drawing keeps
the findings; `complete` and `validation.valid` remain independent.

`Diagnostic` is a frozen dataclass with `code`, `message`, `path`, `severity`,
optional `source` location and `details`; `to_dict()` produces copied JSON-compatible
data. Use codes and source pointers for logic, not prose. `RenderError` carries
`diagnostics`; `SvgError` carries a document `path`. Both derive from `ValueError`.
Export option failures use `ValueError`; filesystem failures can use `OSError`.

## Native SVG document and metadata

The SVG namespace is `http://www.w3.org/2000/svg`. The root has `data-track-id`
and `data-complete` matching its metadata, a viewBox, optional physical dimensions,
a title, one metadata container, one definitions container, one background
rectangle and one Map group. The Map group has `id="map"` and
`transform="scale(1,-1) rotate(angle)"`, where `angle` is `map_orientation`;
the rotation term is omitted when the angle is zero.

The Map group contains ordinary `<g>` layers with `data-layer`. Each layer contains
identified geometry groups, each with one native `<polyline>`, `<path>` or `<use>`.
The builder sorts layers numerically and geometry groups within each layer by
logical geometry ID. Typical layers are 0 for road/additional surfaces, 10 for
selection corridors, 20 for ordinary lane/junction markings, 30 for other paint,
35 for surface-marking artwork, 50 for object footprints and 60 for symbols.
Drawing order is independent of semantic ownership: a section contributes to
several layers, each containing its corresponding geometry groups.

Filled regions use absolute `M/L/Z` paths and `fill-rule="evenodd"`, preserving
holes. Strokes use polylines with explicit widths/caps/joins; dashed paint is
already split into visible pieces. Curves are sampled to the configured chord
tolerance. Symbols use `<use href="#asset-HASH">`; each unique asset is an
embedded SVG data URI in a `<defs><image id="asset-HASH">` definition. Artwork is
centered in a 1000×1000 viewport and transformed to its physical drawing footprint.
The top of artwork points along its pose's forward axis.

### Coordinates and identity

Map x follows the root port's forward tangent, y points left and z points up.
Lengths are meters; physical pose angles are degrees and positive yaw is
counter-clockwise. Upstream headings are radians: compilers convert at the
boundary. The outer Map group rotates the complete track around the Map origin
by `map_orientation`, then flips y exactly once for image display. Positive
rotation is counter-clockwise on screen: the Map x-axis points right at 0 degrees
and up at 90 degrees. SVG and JPEG share this transform. The export viewBox fits
the transformed geometry, including painted extents and margin.

`map_orientation` does not rewrite primitive vertices or part poses; they remain
in the unrotated Map frame. `bounds()` returns those Map-frame painted bounds and
deliberately excludes the Map group's display transform. Consumers interpreting
the SVG transform must not apply metadata orientation a second time. Physical
parts normally describe component centers.
Section `reference` parts explicitly use `properties.anchor: "entry_port"` and
record port positions and outward yaws. No unspecified physical dimension is
inferred from an illustration's size.

Semantic object IDs are source JSON Pointers, with `~0`/`~1` escaping. Part and
drawing IDs append deterministic local roles. A drawing XML ID is
`geometry-` plus the SHA-256 hash of its logical drawing ID; asset IDs are content
hashes. Source renames change semantic identity. XML hashes are not an interface
for recovering source paths; read the semantic attributes instead.

| Drawing attribute | Meaning |
| --- | --- |
| `data-geometry-id` | Logical drawing identity, stable for its source/role. |
| `data-object-id` | Owning semantic object. |
| `data-section-id` | Owning section, if any. |
| `data-parent-id` | Immediate semantic parent, if any. |
| `data-placement-section-id` | Placement section when separately recorded. |
| `data-part-id` | Associated physical part, if any; must belong to the same owner. |
| `data-role` | Local drawing role. |
| `data-purpose` | `physical`, `projection` or `selection`. |
| `data-source-ids` | JSON array of contributing source object IDs, if any. |

Physical geometry describes surfaces/paint. Projection geometry depicts physical
parts for readability. Selection geometry supports hit testing and is not a
physical/collision surface. Selection groups use `opacity="0"` with
`pointer-events="all"`; they do not enlarge visible bounds. Zone holes and
separate route visits are preserved.

### Annotation payload

Inside SVG's `<metadata>`, a namespaced `<caudri:track encoding="application/json">`
contains semantic JSON. The namespace URI is
`urn:caudri:track-renderer:metadata:1`; match the URI/local name, not the prefix.
Native SVG contains all drawing geometry
and artwork bytes; neither is duplicated in the JSON.

| Field | Meaning |
| --- | --- |
| `track` | Expanded global source values: `id`, `$schema`, `root`, `connections`, `road`, `rendering`, optional `metadata` and `discipline`, plus residual source collection mappings. |
| `coordinates` | `frame: map`, `length_unit: m`, `angle_unit: deg`, axes `{x: root_forward, y: left, z: up}`, `positive_yaw: counter_clockwise`. |
| `complete` | Rendering completeness, independent of validation success. |
| `validation`, `diagnostics` | Source-render validation evidence and findings. |
| `background` | Hex RGB background color. |
| `objects` | ID-to-object dictionaries. |
| `parts` | ID-to-physical-part dictionaries. |
| `assets` | Content-hash-to-artwork-description dictionaries. |
| `dependencies` | Input, loaded schema and attempted external artwork URI list. |
| `selection` | Optional `{section_ids: [...], validation_scope: "source_track"}` on selected documents. |

Object records: `id`, `type`, `category`, `parent_id`, `section_id`,
`source_pointer`, `properties`, `provenance`, and optional `reference_only`.
Properties retain expanded values with child objects stored separately. Collection
mappings keep disabled slots and empty mappings. Provenance records
defaults/generated values. Ownership references are nullable. Top-level
features, zones and actors remain global even if their placement uses `at.section`.

Schema references in object provenance, validation records and diagnostics use
`track.$schema` as their URI resolution base, never the SVG location.
Resolve with `urllib.parse.urljoin(metadata["track"]["$schema"], schema_ref)` or equivalent URI
resolution. The renderer emits relative paths for same-origin references when
resolution preserves the exact original URI, retaining query and fragment;
other origins, non-hierarchical URIs and existing relative refs remain unchanged.
Absolute refs are valid too. `rendering/schema_refs.py` performs this conversion
when `DrawingBuilder.finish()` builds metadata. Prepared input, object/part
properties, asset URIs, source locations and dependency URIs are not rewritten.
SVG loading and display never dereference schemas. Local file bases are provenance
locations, not a guarantee that a downstream machine has those schema files.

Part records: `id`, `object_id`, `role`, `pose`, `size`, `properties`. Poses emitted
by compilers contain `x`, `y`, `z`, `yaw`, `pitch`, `roll`; positive finite physical
dimensions are stored by name. Asset records contain `mime_type: "image/svg+xml"`,
`sources`, and optional `generation` details such as QR payload, version, error
correction, mask and template URI. There is no asset `content` field in metadata.

### Expanded track reconstruction

`track` and `objects` partition the expanded input without duplicating semantic
child bodies. `track` retains all global source fields, including the complete
`root` and ordered `connections` array. The public `track_id`, `schema_uri` and
`map_orientation` accessors read `track.id`, `track.$schema` and
`track.root.map_orientation`, respectively (orientation defaults to zero if
absent). Root/connection port references use Track Description names, not SVG IDs.
The standalone report still exposes `schema_uri` as its schema-reference base.

`rendering/indexing.py:collection_properties()` retains ordinary expanded values,
empty collection mappings and non-object slots such as false. Dict-valued
children move into the flat object index. Object `type` is stored in the record,
not repeated in properties. For parking areas, dict-valued parallel/perpendicular
lots move out of parameters, while disabled lots stay false. Lots retain a spots
mapping whose dict-valued children have separate spot records. The synthetic
`parking_lot` and `parking_spot` types classify metadata records; their original
source dictionaries have no type field.

`svg/track.py:to_track()` validates annotations and rejects any `selection` or
`reference_only` records. It copies the global track block and visits objects
parent-first, decodes JSON Pointer tokens, verifies parent/category/section
relationships, and inserts each object's properties at its source slot. Ordinary
objects receive the record's type; parking helpers remain untyped. Missing
collection mappings, collisions with existing parent values and inconsistent
ownership raise `SvgError`. Arrays such as connections preserve order; object
mapping order carries no contract. The result is independent of the document.

Reconstruction performs no expansion, schema loading or geometry calculation.
Its annotation/source-tree checks do not validate the Track Description schema,
connection topology or current native drawing. `drawing.validate()` checks the
SVG profile and semantic cross-links; `prepare_track()` checks the reconstructed
description. These are separate validation boundaries.

Reconstruction uses neither provenance nor parts/paths to infer source values.
Native XML presentation edits therefore have no effect on the result; direct
changes to the serialized source records do. A forced drawing can
retain its expanded source even if artwork failed or geometry is incomplete;
the returned description may still be invalid. `prepare_track()` validates it
again. Full valid renders reconstruct the same expanded values, including
disabled/generated entries, settings, object simulation data and parking slots.
Authored YAML formatting, shorthand and original authoring choices are not
recreated. Render options, selection and export settings are not part of the
reconstructed description. Use the same options and resources to reproduce its
rendering; the embedded artwork is not an alternate resource source for
`prepare_track()` or `render()`. Saved reference SVGs under `docs/img/` use
illustrative workspace URIs; render the root examples for references to actual
local resources.

### Presentation-only SVG

`metadata=False` is an export option on `to_svg`, `write` and `export_svg`;
`--no-metadata` exposes it on the CLI. Rendering still builds a semantic document
for validation, reports, selection and reuse. The option reduces output size;
it does not bypass source preparation or geometry compilation. The export
validates and frames a copy, then `svg/presentation.py:strip_metadata()` removes
metadata elements and selection-purpose geometry. It prunes unused artwork, removes data-* attributes
and IDs not needed by surviving use references, and unwraps attribute-free groups
while preserving painter order. Groups with transforms or presentation attributes
remain. Required artwork IDs/payloads, the title and viewport remain standard SVG.
No alternative track-reconstruction payload is stored in this output. Ordinary
viewers can display it, but `load_svg()` requires the annotated renderer profile.
The original drawing remains usable for `to_track`, selection, metadata export
or reports.

### Selection and references

`select_sections()` accepts iterable short section names or full section pointers
and also handles one string. Empty selections are valid SVGs. Unknown or
`reference_only` section IDs raise `SvgError`. Selection deep-copies the document,
keeps requested sections and their transitive semantic children, filters drawing
groups/parts and removes unused embedded artwork. Original coordinates, source
IDs, painter order and dependencies remain intact.

The `track` block also remains intact as full-source context. Root and connection
references may therefore name excluded sections. Selection never rewrites the
topology into a standalone track; `to_track()` rejects even selections that happen
to contain every section, since global objects may have been filtered out.

Needed ancestors, contributing objects and metadata references remain as
`reference_only: true` records without their drawing or physical parts. Selecting
such a section cannot recover excluded geometry; choose it from the original
document. Source validation findings are preserved, not recomputed for the
selected subset. Global objects are not implicitly selected by proximity or an
`at.section` reference. A sign owned by an element stays with it even if placed on
another road. Excluding a zone does not undo paint effects already compiled into
section drawings.

An editor can hide matching geometry groups using SVG presentation attributes
without recompiling. A browser UI needs inline SVG or direct access to the SVG
DOM for hit testing and semantic lookup; an HTML `<img>` does not expose that DOM.
Browser-only CSS changes are outside the Python loader's supported profile.

### Bounds and supported loading profile

`svg/geometry.py` measures native drawing elements and the embedded image
rectangles, not duplicate metadata. Bounds are conservative: stroke padding,
square caps and visible miter tips are included; embedded artwork uses its full
image viewport, not an exact opaque-pixel contour. The default SVG miter limit is
4. Full floating-point viewBox coordinates avoid inward rounding/clipping.

Bounds honor affine `matrix`, `translate`, `scale`, `rotate`, `skewX` and `skewY`
transforms below the Map group, presentation inheritance, hidden paint and group
opacity. Export framing additionally includes the Map group's transform. `display=none`
or zero group opacity excludes descendants; inherited `visibility=hidden` can be
overridden by a visible child. Selection geometry and the document background do
not contribute. `bounds()` calculates geometry only; use `validate()` for the
complete document/metadata checks.

`GeometryReader` in `svg/geometry.py` shares parsed paths, numeric values and
transforms within one operation. Construction and export reuse those values for
validation and viewport bounds; each later call creates a fresh reader so direct
XML edits are observed. `SvgDocument._export()` returns one internal snapshot of
SVG text, viewBox, background and whether visible geometry exists. JPEG consumes
that snapshot without reparsing the XML/metadata or measuring the drawing again.
There is no persistent geometry or validation cache attached to the mutable tree.

`load_svg()` reads this renderer's passive, annotated profile and returns an
`SvgDocument`; call `to_track()` separately to reconstruct its expanded source.
It does not infer a road model from arbitrary SVG editor output. The supported
root structure, native primitives, ownership links and embedded artwork are
validated. The profile rejects root-level transforms, unsupported elements/attributes, active/external resources,
conflicting `href`/`xlink:href`, duplicate XML/logical IDs, unknown object/part
references, nonfinite coordinates and incoherent metadata. Paths in the outer
drawing use absolute M/L/Z commands; embedded SVG artwork has its own passive
artwork checks and can contain richer shapes.

Saved SVG input must be UTF-8 with a viewBox. Outer-document DTDs, entity declarations
and stylesheet instructions are rejected. Embedded artwork permits inert external
DOCTYPE declarations without fetching them; entity declarations remain rejected.
Document limits are 64 MiB, 250,000
elements and nesting depth 64; embedded artwork is limited to 8 MiB per asset.
Serialization also enforces the document byte limit. These profile constraints
apply to Python helpers, independently of what an ordinary SVG viewer supports.

## Caching and repeat rendering

`description/bundle_cache.py` keeps up to eight pristine initial local bundles
in a process-local LRU keyed by upstream bundle type and resolved schema URI.
It hashes actual file contents before/after initial loading and checks them on
reuse. Cached resources include entry schema, catalog and regulations. Changed,
unavailable, remote or concurrently changing initial resources do not yield a
reusable snapshot. Each preparation receives a deep copy with its own reference
registry and identity-based origin index. Lazy schema references are loaded per
preparation. Cache bookkeeping is locked; caller state never owns the snapshot.

Description loading, expansion, validation and geometry preparation still run
for each newly prepared revision. Reusing `PreparedTrack` avoids those stages.
Each render rebuilds indices, marking plans and SVG. There is no automatic
document/JPEG cache or dependency-aware partial geometry rebuild after edits.
Loading or selecting an existing SVG reuses computed geometry.

Artwork is deduplicated by source request and content hash within one drawing.
Failed reads remain dependencies so a missing asset appearing later can invalidate
a preview. Generated QR URNs are not external resources; their template URI is a
dependency. Dependencies survive saved SVG round trips.

Application cache keys should include source contents, render options,
`renderer_fingerprint()`, and dependency contents or availability states from
`dependency_uris(...)`. In-memory descriptions need their own content key;
`source_uri` supplies resolution context, not dictionary contents, and may name
a nonexistent file. Revalidate remote URIs and compare bytes rather than only
timestamps. Include selection/export settings when caching those results.
The fingerprint covers core code/dependencies; include the rasterization runtime
when reproducibility of externally cached JPEG bytes matters.

## Source map and dependency boundaries

All paths in the table are relative to `source/track_renderer/`.

| Module/package | Responsibilities and likely changes |
| --- | --- |
| `api.py` | Pipeline order, strict/forced behavior, returned document. |
| `options.py` | Immutable options and projection-category checks. |
| `cli.py`, `__main__.py` | Arguments, output/report policy, stderr findings, exit statuses. |
| `reporting.py` | Shared standalone report construction, including the schema-reference base. |
| `diagnostics.py`, `io.py`, `cache.py` | Findings/errors, atomic writes, dependency/fingerprint helpers. |
| `description/loading.py` | Resource discovery, private upstream imports, preparation and partial-model recovery. |
| `description/bundle_cache.py` | Content-checked initial bundle snapshots and safe per-preparation copies. |
| `description/types.py` | Protocols for upstream attributes/methods consumed by the renderer, without runtime imports of dynamically loaded scripts. |
| `rendering/context.py` | Per-render model/options/index state, checked geometry/part helpers and expected-failure handling. |
| `rendering/indexing.py`, `pointers.py` | Semantic source identity, ownership, provenance and escaped JSON Pointers. |
| `rendering/instance_index.py` | Placed-instance and route-visit lookups for marking queries, rebuilt per render. |
| `rendering/builder.py` | Immediate native SVG construction, stable XML IDs, layer sorting, asset definitions and metadata assembly. |
| `rendering/schema_refs.py` | Relativize provenance/report schema references against the track's schema URI without changing their resolved targets. |
| `rendering/records.py`, `types.py` | Private physical/object dataclasses and transient compiler argument types. |
| `svg/document.py` | Public document properties, framing, serialization, selection wrapper and loading. |
| `svg/metadata.py`, `annotations.py` | Metadata namespaces/encoding and semantic record validation. |
| `svg/track.py` | Reassemble the expanded Track Description and check source-tree consistency. |
| `svg/presentation.py` | Strip semantics from an export copy while retaining visible SVG content. |
| `svg/validation.py` | Supported XML profile, passive content and semantic/drawing cross-links. |
| `svg/selection.py` | Ownership selection, reference-only closure, asset pruning and fixed framing. |
| `svg/geometry.py`, `strokes.py` | Native SVG transforms, visible extents, square caps and miter bounds. |
| `sections/compilation.py` | Section registry, entry reference parts/ports and road surfaces. |
| `sections/road.py` | Shared straight, arc and clothoid lane drawing. |
| `sections/intersection/geometry.py` | Prepared arms, corners, boundaries and geometry used by both planning and drawing. |
| `sections/intersection/compilation.py` | Junction drawing coordinator. |
| `sections/intersection/boundaries.py`, `approaches.py` | Outer paint, width transitions and ordinary approach centerlines. |
| `sections/intersection/controls.py`, `mandatory_turn.py` | Stop/give-way controls and mandatory-turn center/outer guidance. |
| `elements/` | Separate crosswalk, side-road junction, parking area, barred area, start-box and starting-line compilers. |
| `features/traffic_sign.py`, `surface_marking.py` | Panel placement and physical surface controls/arrows/speed artwork. |
| `features/landmark.py`, `objects.py` | Roadside landmark panels and static obstacles/artifacts/custom markers. |
| `markings/planning.py` | Continuous dash coordinates, loop closure, terminal lengths and control gaps. |
| `markings/drawing.py`, `styles.py`, `visibility.py` | Shared strokes, centerline component styles and missing-marking masks. |
| `geometry/primitives.py`, `placement.py`, `directions.py` | Sampling/intervals, explicit placement/zone endpoints, travel-relative sides. |
| `assets/loading.py`, `validation.py`, `dimensions.py`, `landmark_artwork.py` | Source artwork embedding, passive SVG/CSS checks, intrinsic display dimensions and QR generation. |
| `exporters/svg.py`, `jpeg.py` | SVG serialization helper and raster conversion. |
| `actors.py`, `zones.py` | Spawn bodies/projections and invisible route-selection corridors. |

Schema defaults, expansion recipes and geometry validation belong upstream.
`description/` integrates that model; `rendering/` and domain compilers translate
it into SVG and metadata. `svg/` and exporters operate without access to the
prepared track. Keep these dependency directions.

Section, element and feature dispatch use explicit registries:
`SECTION_COMPILERS` in `sections/compilation.py`, and `COMPILERS` in
`elements/__init__.py` and `features/__init__.py`. Straight/arc/clothoid compilers
share the same resolved curve interface; their common algorithm lives together.
Actor/zone variants share small compilers; elements have independent files for
their distinct constructions. Feature-specific placement lives beside its
feature, shared transforms in `geometry/placement.py`.

Marking planning and drawing both depend on junction geometry preparation.
`sections/intersection/geometry.py` must not import drawing compilers. Lightweight
package initializers preserve this direction; coordinator modules invoke drawing
stages explicitly. Semantic indexing and route indexing serve different queries:
global zones can influence many sections without owning or belonging to them.

## Domain geometry and placement behavior

### Supported objects

- Sections: `straight`, `arc`, `clothoid`, `intersection`.
- Elements: `crosswalk`, `side_road_junction`, `parking_area`, `barred_area`,
  `start_box`, `starting_line`. Parking lots/spots are indexed owned objects but
  drawn by the containing parking-area compiler.
- Features: `traffic_sign`, `surface_marking`, `landmark`, `static_obstacle`,
  `artifact`, `custom_marker`.
- Actors: `dynamic_obstacle`, `pedestrian`; physical spawn bodies and optional
  depictions only.
- Zones: `centerline`, `missing_marking`, `speed_limit`, `no_passing`, `expressway`,
  `grade`. The renderer uses expanded features and route information and gives
  zones selectable route corridors.

### Junctions and marking continuity

`corner_radius: 0` produces a sharp boundary join: a normal 90° corner for
right-angle arms, the configured angle for oblique arms. Zero is not replaced by
a small rounded corner. Generated stop/give-way paint meets the correct inner
boundary, including where paint extends beyond a corner tangency.

Each arm uses its connected road width. Opposite T-junction arms with unequal
widths blend their outer offsets over `2 * port_distance` using
`b(t) = b0 + (b1 - b0) * (10*t**3 - 15*t**4 + 6*t**5)`. This matches tangent and
zero curvature at both ports; equal widths produce a straight edge. Branch-side
corners retain their own radius. Drawing and the validated road envelope share
the transition construction, including paint thickness. Controls clip against
the curved boundary; generated sign clearance follows it. Mandatory-turn outer
guidance meets the taper tangentially and follows it to the port. Mask ownership
switches between the opposing arms at the transition midpoint.

Missing-marking left/right follows the selected route direction through a
junction. Only visited arm sides and adjoining boundary arcs are masked;
unrelated arm paint remains. Side-road replacement boundaries also obey masks.
Mandatory-turn center and outer guidance are exempt. Disable their source
configuration when those lines are unwanted.

Dash lengths are not stretched to fit a road. Marking plans preserve phases and
control gaps across ownership boundaries and connected approaches. Minimum
terminal stroke lengths apply to complete visible runs, including pieces on
neighboring sections and loops. Boundaries of unrelated marking masks or
provenance changes do not interrupt an otherwise continuous centerline style.
Centerline and mandatory-arrow gaps use the
approach-facing painted edge of a control line; without paint, use the theoretical
control boundary.

### Areas, parts and explicit placement

Area dimensions generally use marking centerlines; free clearances use the
nearest relevant paint/body edges according to the schema. Parking and waiting
areas anchor at the road marking's center. Roadside sign/landmark clearance runs
from the outer road-marking edge to the nearest panel edge, so a panel center
includes half its width. Parking obstacle gaps use inner paint edges and the
actual oriented body footprint. Do not silently resize bodies or substitute
length for width after rotation. Barred-area lateral extent starts at the inner
road-marking edge.

An explicit `pose` supplies Map coordinates directly. Section-relative `at`
placement uses distance/offset on a linear section, local x/y in a junction, and
explicit yaw/upward offsets. Placement requires a component anchored to the Map
root. Explicit `at.distance` is bounded by `0 <= distance <= section.curve.length`,
including actor spawns and explicit overrides on generated features. The upstream
structural placement check reports `schema.position_range`. Upstream
`GeometryModel.locate_local()` and the renderer's `explicit_placement()` enforce
the same bound during geometry construction, including forced rendering. The
separate `locate()` helper remains available for automatic sign advances.
Explicit values are not silently moved. Global absolute stop/give-way
markings take explicit size first, otherwise use rendering width for longitudinal
thickness, track-wide lane width for lateral size and track marking color.
Section-relative controls use the section's road settings.

Start boxes attach a straight bay to a left root arc's exit tangent. The compiler
searches backward for the nearest crossing of the outer road boundary with the
bay's inner edge; long arcs can have multiple crossings. A shorter bay instead
meets the curve at its rear edge. Starting-line support and marking gaps share
one placement helper. An implicit starting line at a root exit is placed on the
connected successor, and support must be a linear section with sufficient length.

Crosswalk waiting sides follow travel direction. A pedestrian without explicit
spawn starts in the relevant enabled waiting area and faces across the road;
explicit spawn uses authored placement. Landmark panels can occupy one or both
sides of a road. Their physical placements are recorded before artwork generation,
so a forced preview retains panel poses even when artwork fails.
Section-relative landmark panels use their selected section's width and local
tangent while retaining their original semantic owner.

Grade signs walk outward along their approach, checking each traversed section.
Automatic placement is omitted with `render.sign_omitted_at_junction` when the
advance reaches/crosses an intersection. A zero-grade zone has no uphill/downhill
approach. Ordinary generated sign positions use upstream resolved placement;
explicit `at`/`pose` handles specific layouts.

### Artwork and QR generation

Source artwork can be a local/file URI or HTTP(S); HTTP reads use a 15-second
timeout. Source fragments, unsupported URI schemes and query-bearing file URIs
are rejected. Artwork must be UTF-8, passive and self-contained: scripts,
animation, external CSS/resources and active content are checked; local fragment
references remain supported. Missing artwork becomes a finding, not a substitute
image. Artwork reads are bounded to 8 MiB. Reader and parser failures are handled
at the artwork-import boundary, so forced rendering can retain the other objects.

Custom markers without authored `size` can use an SVG's absolute viewport width
and height as projection dimensions. SVG height maps to forward length; SVG width
maps to lateral width. Absolute CSS units are converted to meters; CSS pixels
and unitless viewport lengths use 96 pixels per inch. A viewBox alone, percentages
or font-relative dimensions cannot establish Map scale and produce a diagnostic
requesting explicit `size.length` and `size.width`. Authored dimensions take
precedence. Intrinsic artwork dimensions never fill in physical body sizes.

Landmark generation uses the numeric identifier as printed text and the configured
`qr_payload` as data. Digit-specific mode/mask profiles apply when payload equals
the identifier; arbitrary payloads use automatic mode/mask selection. QR version
and error-correction settings remain explicit; encoding failure reports an error
instead of silently changing them. Unicode payloads use UTF-8/ECI. A configured
asset differing from the default landmark asset bypasses QR generation. Generated
artwork retains the panel template; high error correction supports an overlaid
label, while weaker correction places the label below the matrix. Generation
metadata and the template dependency are retained.

## Local verification workflow

Use `.venv/bin/python` and the repository's configured tools when available.
Check `track_renderer.__file__` and
`track_renderer.description.loading.description_directory()` when diagnosing
differences between a checkout and an installed wheel. Use an editable install
or `PYTHONPATH="$PWD/source" .venv/bin/python ...` from the repository root to
exercise checkout code. Resource discovery still prefers any bundled resources
present inside that package.
Ruff targets Python 3.11 with line length 100. Run focused checks for changed
behavior and relevant existing local tests; keep new tests under `/tmp`. Do not
add a published test suite or CI configuration.

For geometry or compiler refactors, compare deterministic semantic records and
native SVG drawings from representative tracks before/after changes, then check
actual raster appearance. Include sharp/rounded corners, unequal junction
widths, loops, markings across boundaries, parking, crosswalks, zone holes,
repeated visits and embedded artwork as relevant. Preserve source identities,
physical parts, projection suppression, hit regions and drawing order.

For SVG changes, exercise save/load round trips, metadata copies, valid native
presentation edits, section selection and reference-only records, empty/partial
drawings, fitted/fixed viewBoxes and JPEG dimensions. Check loaded documents
without access to original sources. Validate error paths and source-linked
diagnostics as well as successful previews. Browser checks should verify visible
artwork and actual hit testing for transparent selection corridors.

For source-metadata changes, compare
`load_svg(drawing.to_svg()).to_track()` with `prepared.expanded_track`. Cover
disabled entries, empty collections, generated features, nested parking slots,
global objects, actor behavior, Unicode values, root placement and ordered
connections. Repeat with optional projections disabled: source reconstruction
must not depend on their geometry or assets. Re-prepare and render the result
with the same resources/options to compare geometry and physical parts;
provenance can differ because the reconstructed input is already expanded.
Check that selections, including selections of all sections, reject `to_track()`.

For presentation exports, compare visible output with and without metadata,
check surviving artwork references and verify that export leaves the original
document unchanged. The compact SVG must contain no renderer metadata, data-*
attributes or selection aids; rejection by `load_svg()` is expected. Full
annotated SVG loading and `to_track()` must work without the original schema,
track and artwork files; re-rendering the reconstructed dictionary still needs
its resources.

For API/CLI/documentation changes, run example code and CLI commands, check exit
statuses and report contents, and verify Markdown links/assets. Useful fixtures:
`examples/intersection_showcase.yaml`, `examples/regulation_example.yaml`,
`examples/track.yaml`, `examples/curved_track.yaml` and
`examples/example_track.yaml`. Executable
documentation generators live in `docs/scripts/`: `render_reference.py` exports
annotated SVG variants, while `render_svg_figures.py` and `render_header.py`
compose the illustrations described above.

For packaging changes, build wheel and source distribution in a temporary copy,
check required resources/documentation and excluded tests/artifacts, rebuild a
wheel from the source archive, and exercise an installed package using its
bundled resources. Record commands, results and remaining limits in the task
report, not dated verification counts or temporary audit paths in this file.
