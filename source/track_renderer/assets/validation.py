"""Check that SVG artwork stays passive and self-contained.

Imported files and assets in saved scenes use the same checks. Static drawing
and local fragment references are allowed; scripts, animation and references
that could fetch another resource are rejected, including those hidden in CSS.
"""

import re
from xml.etree import ElementTree as ET

import tinycss2

from ..diagnostics import RenderFailure

SVG_LIMIT = 8 * 1024 * 1024


_RESOURCE_ATTRIBUTES = frozenset(
    {
        "fill",
        "stroke",
        "filter",
        "clip-path",
        "mask",
        "cursor",
        "marker",
        "marker-start",
        "marker-mid",
        "marker-end",
        "color-profile",
    }
)


_ACTIVE_ELEMENTS = frozenset(
    {
        "script",
        "foreignobject",
        "animate",
        "animatetransform",
        "animatemotion",
        "animatecolor",
        "set",
        "discard",
        "handler",
        "listener",
        "iframe",
        "object",
        "embed",
        "audio",
        "video",
    }
)


def _local_reference(value: str) -> None:
    """Require a nonempty reference to a fragment in this same SVG document."""
    if not value.startswith("#") or len(value) == 1:
        raise RenderFailure("SVG contains an external stylesheet/resource reference")


def _css_tokens(tokens) -> None:
    """Inspect parsed CSS tokens, including escapes and nested blocks/functions."""
    significant = [token for token in tokens if token.type not in {"whitespace", "comment"}]
    for index, token in enumerate(significant):
        if token.type == "error":
            raise RenderFailure(f"Invalid SVG CSS: {token.message}")
        if token.type == "at-keyword" and (
            token.lower_value == "import" or token.lower_value.endswith("keyframes")
        ):
            raise RenderFailure("SVG contains an external stylesheet or CSS animation")

        if (
            token.type == "ident"
            and (
                token.lower_value.startswith(
                    ("animation", "transition", "-webkit-animation", "-webkit-transition")
                )
            )
            and index + 1 < len(significant)
            and significant[index + 1].type == "literal"
            and significant[index + 1].value == ":"
        ):
            raise RenderFailure("SVG contains a CSS animation or transition")

        if token.type == "url":
            _local_reference(token.value)
        elif token.type == "function":
            if token.lower_name == "url":
                arguments = [t for t in token.arguments if t.type not in {"whitespace", "comment"}]
                if len(arguments) != 1 or arguments[0].type != "string":
                    raise RenderFailure("Invalid SVG CSS URL")
                _local_reference(arguments[0].value)
            elif token.lower_name in {"image", "image-set", "-webkit-image-set", "src", "paint"}:
                # These forms can load resources from bare strings, not only url().
                raise RenderFailure(f"Unsupported SVG CSS resource function: {token.lower_name}")
            # Functions and rule blocks may contain more functions, URLs or
            # declarations. Follow the parsed tree so nesting and CSS escapes
            # cannot hide a reference from the checks above.
            _css_tokens(token.arguments)
        elif hasattr(token, "content"):
            _css_tokens(token.content)


def validate_svg(content: str) -> None:
    """@brief Require bounded, passive SVG with only local fragment references.

    Inline CSS is parsed rather than matched as text. Script, animation, external
    resources and changed XML base URIs are rejected; static CSS and ordinary
    editor metadata are retained. The same policy applies to embedded artwork.
    """
    try:
        _validate_svg(content)
    except RenderFailure:
        raise
    except Exception as exc:
        # Treat parser failures as unusable artwork, including failures in CSS
        # libraries. Do not let one imported asset abort a forced track render.
        raise RenderFailure(f"Cannot validate SVG artwork: {exc}") from exc


def _validate_svg(content: str) -> None:
    """Check the XML and CSS of one imported or embedded SVG."""
    if not isinstance(content, str):
        raise RenderFailure("SVG artwork must be text")
    try:
        encoded = content.encode("utf-8")
    except UnicodeError as exc:
        raise RenderFailure("SVG artwork must contain valid Unicode text") from exc
    if len(encoded) > SVG_LIMIT:
        raise RenderFailure("SVG artwork exceeds 8 MiB")

    # Conventional external SVG DTD declarations are inert under ElementTree.
    # Entity declarations and internal subsets are never needed by our artwork.
    if re.search(r"<!\s*ENTITY|<!\s*DOCTYPE[^>]*\[", content, re.I):
        raise RenderFailure("SVG entity declarations are not supported")
    if re.search(r"<\?\s*xml-stylesheet\b", content, re.I):
        raise RenderFailure("SVG external stylesheet processing instructions are not supported")

    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise RenderFailure(f"Invalid SVG: {exc}") from exc
    if root.tag not in {"svg", "{http://www.w3.org/2000/svg}svg"}:
        raise RenderFailure("Artwork is not an SVG document")

    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1].lower()
        if tag in _ACTIVE_ELEMENTS or element.tag.startswith(
            ("{http://www.w3.org/1999/xhtml}", "{http://www.w3.org/1998/Math/MathML}")
        ):
            raise RenderFailure(f"Active SVG element: {tag}")

        for key, value in element.attrib.items():
            name = key.rsplit("}", 1)[-1].lower()
            if name.startswith("on"):
                raise RenderFailure("SVG contains an event handler")
            if key == "{http://www.w3.org/XML/1998/namespace}base":
                raise RenderFailure("SVG xml:base is not supported")
            if name == "href":
                _local_reference(value)
            if name == "style" or name in _RESOURCE_ATTRIBUTES:
                _css_tokens(tinycss2.parse_component_value_list(value))
        if tag == "style":
            _css_tokens(tinycss2.parse_component_value_list("".join(element.itertext())))
