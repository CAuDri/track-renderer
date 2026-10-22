"""Generate a landmark's QR code and label inside the supplied sign frame.

Catalog QR settings control the encoding, while the renderer fits the matrix
and readable identifier into the template. An explicitly selected asset bypasses
generation and is loaded as ordinary artwork.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

import segno

from ..diagnostics import RenderFailure
from .loading import embed_svg, read_asset

if TYPE_CHECKING:
    from ..rendering.context import Context

SVG = "http://www.w3.org/2000/svg"


def landmark_asset(ctx: Context, value: dict[str, Any]) -> str:
    """@return Embedded generated artwork, or an explicitly selected asset URI.

    The numeric identifier remains the printed label. Only its decimal payload
    selects a digit-specific QR profile; arbitrary payloads use automatic mode
    and mask selection. Version and error correction always remain as specified.
    """
    parameters, rendering = value["parameters"], value["rendering"]
    identifier = str(parameters["identifier"])
    base = ctx.track["rendering"]["asset_path"]
    if rendering["asset"] != urljoin(base, f"landmark/{identifier}.svg"):
        return rendering["asset"]

    payload = rendering["qr_payload"]
    profile = rendering.get("qr_profiles", {}).get(identifier, {}) if payload == identifier else {}
    try:
        code = segno.make_qr(
            payload,
            version=rendering["qr_version"],
            error=rendering["qr_error_correction"],
            mode=profile.get("mode"),
            mask=profile.get("mask_pattern"),
            boost_error=False,
            encoding="utf-8",
            eci=not payload.isascii(),
        )
    except ValueError as exc:
        raise RenderFailure(
            f"Landmark QR payload cannot be encoded with version {rendering['qr_version']} "
            f"and error correction {rendering['qr_error_correction']}: {exc}"
        ) from exc

    reference = urljoin(base, "landmark/0.svg")
    ctx.drawing._asset_dependencies.add(reference)
    content = _artwork(read_asset(reference), code, identifier)
    generated_uri = "urn:caudri:landmark:" + hashlib.sha256(content.encode()).hexdigest()
    return embed_svg(
        ctx.drawing,
        content,
        generated_uri,
        generation={
            "kind": "landmark_qr",
            "identifier": parameters["identifier"],
            "payload": payload,
            "version": code.version,
            "error_correction": code.error,
            "mode": code.mode,
            "mask_pattern": code.mask,
            "template_uri": reference,
            "label_placement": "overlay" if code.error == "H" else "below",
        },
    )


def _artwork(template: str, code: segno.QRCode, identifier: str) -> str:
    """Compose a QR and readable ID inside the supplied landmark frame."""
    root = ET.fromstring(template)
    group = next((g for g in root.iter() if g.get("id") == "generated-qr"), None)
    if group is None:
        raise RenderFailure("Landmark template needs a generated-qr group")

    # Retain the supplied frame and its quiet area. The original matrix occupies
    # 21 modules in this viewport; larger explicitly requested versions scale
    # into the same panel footprint.
    modules = len(code.matrix)
    group.set("transform", group.get("transform", "") + f" scale({21 / modules:.12g})")
    group[:] = []

    overlay = code.error == "H"
    matrix = (
        group
        if overlay
        else ET.SubElement(
            group, f"{{{SVG}}}g", {"transform": f"translate({modules * 0.1} 0) scale(.8)"}
        )
    )
    ET.SubElement(
        matrix,
        f"{{{SVG}}}rect",
        {
            "width": str(modules),
            "height": str(modules),
            "fill": "white",
        },
    )
    commands = [
        f"M{x},{y}h1v1h-1z"
        for y, row in enumerate(code.matrix)
        for x, dark in enumerate(row)
        if dark
    ]
    ET.SubElement(matrix, f"{{{SVG}}}path", {"d": "".join(commands), "fill": "black"})
    if overlay:
        ET.SubElement(
            group,
            f"{{{SVG}}}rect",
            {
                "x": str(modules * 0.36),
                "y": str(modules * 0.36),
                "width": str(modules * 0.28),
                "height": str(modules * 0.28),
                "rx": str(modules / 14),
                "fill": "white",
            },
        )

    # Weaker error correction cannot reliably recover a covered matrix. Move
    # the label below it, preserving at least four clear modules around the QR.
    label_y = modules * 0.514 if overlay else modules * 0.91 + 3.2
    font_size = modules * min(0.196 if overlay else 0.14, 0.39 / len(identifier))

    label = ET.SubElement(
        group,
        f"{{{SVG}}}text",
        {
            "x": str(modules / 2),
            "y": str(label_y),
            "font-size": str(font_size),
            "text-anchor": "middle",
            "dominant-baseline": "central",
            "font-family": "Arial, sans-serif",
            "font-weight": "bold",
            "fill": "black",
        },
    )
    label.text = identifier
    return ET.tostring(root, encoding="unicode")
