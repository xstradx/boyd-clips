"""Deterministic, editable TEXT-ONLY thumbnail experiment builder.

Nathan, 2026-09-19: *"make the thumbnail ... audit the court does them and then
a/b test what it says on the thumbnail"* - i.e. hold the picture still and test
the WORDS. The photographic base is produced upstream (one shared base, arrow
already baked in by whoever made it). This module never generates, crops,
grades, blurs, recolours or re-encodes that base. It draws editable text layers
on top of it and then proves the experiment is what it claims to be.

What an experiment is here:

  * exactly THREE variants, labelled A, B and C, each a headline plus the
    substring of that headline that renders in the house key-phrase yellow.
  * ONE fixed video title for all three - the title is the control, so a
    difference between variants can never be blamed on a changed title.
  * ONE common font size, fitted against the width of the widest variant, so
    the test compares the WORDS and not the type scale.
  * a shared text rectangle. Outside that rectangle every export must decode
    pixel-for-pixel identical to the base; inside it the three exports must
    differ from each other and from the base.

Editable output: next to each 1280x720 PNG goes a native text-layer SVG and a
structured layer JSON. Nothing in this module rewraps, rewords, uppercases,
truncates or "improves" the operator's words.

Type treatment (Audit-the-Court pass): Montserrat variable font at weight 700,
natural sentence case as supplied, white fill with the yellow run on the
supplied emphasis substring, black stroke and a soft black shadow.

What this module does NOT do, and does not claim: it does not judge whether a
headline is good, whether the source evidence supports it, or whether the
picture is any good. `source_evidence` is recorded as present, never as
verified - semantic review happens elsewhere. The receipt checksum binds the
settings; it is a checksum, not a signature.

Failures are collected and raised together as `ThumbnailTextTestError` BEFORE
any file is written, so a too-long headline or an ink escape costs nothing and
leaves no half-built directory behind.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from xml.sax.saxutils import escape as _xml_escape

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from .censor import has_profanity

__all__ = [
    "CANVAS",
    "DEFAULT_FONT",
    "DEFAULT_RECTANGLE",
    "EMPHASIS_YELLOW",
    "LABELS",
    "RECEIPT_TYPE",
    "RENDERER_VERSION",
    "GateFailure",
    "TextRectangle",
    "TextVariant",
    "ThumbnailTextTestError",
    "Typography",
    "build_text_only_experiment",
    "validate_experiment",
]

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FONT = ROOT / "assets" / "fonts" / "Montserrat-Var.ttf"

RENDERER_VERSION = "thumbnail-text-only/2"
RECEIPT_TYPE = "thumbnail_text_only"
LABELS: tuple[str, ...] = ("A", "B", "C")
CANVAS = (1280, 720)

# The house key-phrase yellow, measured off the reference set (the same value
# the legacy compositor and the Audit-the-Court pass use).
EMPHASIS_YELLOW = "#FEFB03"
WHITE = "#FFFFFF"
STROKE_BLACK = "#000000"

# Current requested presentation: one row across the top, clear of faces.
DEFAULT_RECTANGLE = (15, 5, 1265, 140)

_SCRATCH = Image.new("L", (8, 8))
_SCRATCH_DRAW = ImageDraw.Draw(_SCRATCH)


class ThumbnailTextTestError(Exception):
    """Raised before any file output when a gate refuses the experiment."""

    def __init__(self, failures: Sequence["GateFailure"]):
        self.failures = tuple(failures)
        super().__init__("; ".join(str(f) for f in self.failures) or "refused")

    @property
    def codes(self) -> list[str]:
        return [f.code for f in self.failures]


@dataclass(frozen=True)
class GateFailure:
    code: str
    detail: str

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


@dataclass(frozen=True)
class TextRectangle:
    """The ONLY pixels this builder may touch, in canvas coordinates."""

    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    @property
    def height(self) -> int:
        return self.y1 - self.y0

    def as_dict(self) -> dict[str, int]:
        return {"x0": self.x0, "y0": self.y0, "x1": self.x1, "y1": self.y1}


@dataclass(frozen=True)
class Typography:
    """Type and ink settings.

    Font size here is a BOUND, not the answer: the fitted common size is solved
    to the rectangle and recorded in the receipt.
    """

    font_path: Path = DEFAULT_FONT
    weight: int = 700
    min_font_px: int = 44
    max_font_px: int = 120
    max_lines: int = 1
    fill: str = WHITE
    emphasis_fill: str = EMPHASIS_YELLOW
    stroke_fill: str = STROKE_BLACK
    stroke_ratio: float = 0.055
    shadow_offset_ratio: float = 0.05
    shadow_blur_ratio: float = 0.04
    shadow_alpha: int = 165
    line_spacing: float = 1.08
    rect_padding_px: int = 16
    align: str = "left"
    valign: str = "center"
    wrap: str = "greedy_word"


@dataclass(frozen=True)
class TextVariant:
    label: str
    text: str
    emphasis: str

    def normalized_text(self) -> str:
        return _normalize_whitespace(self.text)

    def as_dict(self) -> dict[str, str]:
        return {"label": self.label, "text": self.text, "emphasis": self.emphasis}


@dataclass
class _Line:
    text: str
    runs: list[tuple[str, bool]]  # (text, is_emphasis_yellow)
    tokens: list[tuple[str, int, int]] = field(default_factory=list)


@dataclass
class _Layout:
    variant: TextVariant
    lines: list[_Line]
    font_px: int
    line_step: int
    baseline0: int  # y of the FIRST line's text baseline (same origin as the SVG)
    left: int
    ink_h: int
    emphasis_ranges: list[tuple[int, int]] = field(default_factory=list)
    ink_bbox: tuple[int, int, int, int] | None = None


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.split())


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(Path(path).read_bytes())


def _sha256_image(img: Image.Image) -> str:
    """Normalized pixel hash: decoded, RGB, canvas order - independent of the
    container, the compression settings and the original colour mode."""
    return _sha256_bytes(img.convert("RGB").tobytes())


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _canonical_sha256(obj: Any) -> str:
    return _sha256_bytes(_canonical_json(obj).encode("utf-8"))


def _coerce_rect(
    value: TextRectangle | Sequence[int] | Mapping[str, int] | None,
) -> TextRectangle:
    if value is None:
        return TextRectangle(*DEFAULT_RECTANGLE)
    if isinstance(value, TextRectangle):
        return value
    if isinstance(value, Mapping):
        return TextRectangle(
            int(value["x0"]), int(value["y0"]), int(value["x1"]), int(value["y1"])
        )
    seq = list(value)
    if len(seq) != 4:
        raise ValueError("rectangle must be (x0, y0, x1, y1)")
    return TextRectangle(*(int(v) for v in seq))


def _coerce_variants(
    variants: Iterable[TextVariant | Mapping[str, Any]],
) -> list[TextVariant]:
    out: list[TextVariant] = []
    for item in variants:
        if isinstance(item, TextVariant):
            out.append(item)
            continue
        out.append(
            TextVariant(
                label=str(item["label"]),
                text=str(item["text"]),
                emphasis=str(item["emphasis"]),
            )
        )
    return out


def _font_for(path: Path, size: int, weight: int) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(str(path), size)
    font.set_variation_by_axes([weight])
    return font


def _text_width(text: str, font: ImageFont.FreeTypeFont) -> float:
    # ImageDraw (not ImageFont.getlength) is what honours the variation axes.
    return _SCRATCH_DRAW.textlength(text, font=font)


def _line_metrics(font: ImageFont.FreeTypeFont) -> tuple[int, int, int]:
    """(top_above_baseline, ink_height, ink_below_baseline) from a font probe.

    The layout is built in BASELINE coordinates so the editable SVG and the
    rendered PNG share one origin - a text layer whose `y` is not the baseline
    would re-typeset itself the moment it was opened in an editor.
    """
    bbox = _SCRATCH_DRAW.textbbox((0, 0), "Ag", font=font, anchor="ls")
    return -bbox[1], bbox[3] - bbox[1], bbox[3]


def _ink_margins(font_px: int, typo: Typography) -> tuple[int, int, int]:
    """How far the drawn stroke and the soft shadow reach past the type box:
    (side, top, bottom). PIL's Gaussian blur spreads about 2.5x its radius, so
    the side margin is what keeps a soft shadow from crossing the rectangle."""
    stroke = max(1, int(round(font_px * typo.stroke_ratio)))
    blur = max(0, int(round(font_px * typo.shadow_blur_ratio)))
    spread = int(blur * 2.5) + 2 if blur else 0
    shadow_dy = int(round(font_px * typo.shadow_offset_ratio))
    return stroke + spread, stroke + spread, stroke + spread + shadow_dy


def _emphasis_ranges(text: str, emphasis: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    start = 0
    while True:
        found = text.find(emphasis, start)
        if found < 0:
            return ranges
        ranges.append((found, found + len(emphasis)))
        start = found + len(emphasis)


def _wrap(
    text: str, font: ImageFont.FreeTypeFont, inner_width: float, max_lines: int,
    emphasis: str = "",
) -> list[list[tuple[str, int, int]]] | None:
    """Greedy word wrap. Never splits, drops or rewrites a word: a single word
    wider than the band means this font size does not fit."""
    tokens = [(m.group(0), m.start(), m.end()) for m in re.finditer(r"\S+", text)]
    if not tokens:
        return None
    # Keep the highlighted phrase together. Splitting "is / doomed!" weakens
    # the reading order despite technically fitting inside the canvas.
    groups: list[list[tuple[str, int, int]]] = []
    spans = _emphasis_ranges(text, emphasis) if emphasis else []
    for token in tokens:
        span = next(((lo, hi) for lo, hi in spans if lo <= token[1] < hi), None)
        if span and groups and span[0] <= groups[-1][0][1] < span[1]:
            groups[-1].append(token)
        else:
            groups.append([token])
    lines: list[list[tuple[str, int, int]]] = []
    current: list[tuple[str, int, int]] = []
    for group in groups:
        if _text_width(" ".join(t[0] for t in group), font) > inner_width:
            return None
        if current and _text_width(" ".join(t[0] for t in current + group), font) > inner_width:
            lines.append(current)
            current = list(group)
        else:
            current = current + group
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        return None
    return lines


def _line_from_tokens(
    tokens: list[tuple[str, int, int]], text: str, ranges: list[tuple[int, int]]
) -> _Line:
    chars: list[tuple[str, int]] = []
    for index, (word, start, end) in enumerate(tokens):
        if index:
            prev_end = tokens[index - 1][2]
            sep_offset = prev_end if text[prev_end:prev_end + 1].isspace() else -1
            chars.append((" ", sep_offset))
        for offset in range(start, end):
            chars.append((text[offset], offset))
    runs: list[tuple[str, bool]] = []
    for char, offset in chars:
        yellow = bool(offset >= 0 and any(lo <= offset < hi for lo, hi in ranges))
        if runs and runs[-1][1] == yellow:
            runs[-1] = (runs[-1][0] + char, yellow)
        else:
            runs.append((char, yellow))
    return _Line(
        text="".join(char for char, _ in chars),
        runs=runs,
        tokens=list(tokens),
    )


def _layout_for_size(
    variant: TextVariant,
    font: ImageFont.FreeTypeFont,
    rect: TextRectangle,
    typo: Typography,
    font_px: int,
) -> _Layout | None:
    ranges = _emphasis_ranges(variant.text, variant.emphasis)
    side, top_margin, bottom_margin = _ink_margins(font_px, typo)
    inner_width = rect.width - 2 * (typo.rect_padding_px + side)
    band_top = rect.y0 + typo.rect_padding_px + top_margin
    band_bottom = rect.y1 - typo.rect_padding_px - bottom_margin
    inner_height = band_bottom - band_top
    if inner_width <= 0 or inner_height <= 0:
        return None
    wrapped = _wrap(variant.text, font, inner_width, typo.max_lines, variant.emphasis)
    if wrapped is None:
        return None
    ink_top, ink_h, _ = _line_metrics(font)
    line_step = max(1, int(round(ink_h * typo.line_spacing)))
    total_ink = ink_h + line_step * (len(wrapped) - 1)
    if total_ink > inner_height:
        return None
    baseline0 = int(round(band_top + (inner_height - total_ink) / 2 + ink_top))
    return _Layout(
        variant=variant,
        lines=[_line_from_tokens(tokens, variant.text, ranges) for tokens in wrapped],
        font_px=font_px,
        line_step=line_step,
        baseline0=baseline0,
        left=rect.x0 + typo.rect_padding_px + side,
        ink_h=ink_h,
        emphasis_ranges=ranges,
    )


def _fit_common_size(
    variants: Sequence[TextVariant],
    typo: Typography,
    rect: TextRectangle,
) -> tuple[int, list[_Layout]] | None:
    """Largest font size at which EVERY variant fits, so the three exports share
    one type scale. Solved against the widest variant, not the first one."""
    for size in range(typo.max_font_px, typo.min_font_px - 1, -1):
        font = _font_for(typo.font_path, size, typo.weight)
        layouts = [_layout_for_size(v, font, rect, typo, size) for v in variants]
        if all(layout is not None for layout in layouts):
            return size, [layout for layout in layouts if layout is not None]
    return None


def _render_layer(layout: _Layout, typo: Typography) -> Image.Image:
    font = _font_for(typo.font_path, layout.font_px, typo.weight)
    stroke = max(1, int(round(layout.font_px * typo.stroke_ratio)))
    shadow_dy = int(round(layout.font_px * typo.shadow_offset_ratio))
    blur = max(0, int(round(layout.font_px * typo.shadow_blur_ratio)))

    layer = Image.new("RGBA", CANVAS, (0, 0, 0, 0))

    if blur or shadow_dy:
        mask = Image.new("L", CANVAS, 0)
        mask_draw = ImageDraw.Draw(mask)
        for index, line in enumerate(layout.lines):
            mask_draw.text(
                (layout.left, layout.baseline0 + shadow_dy + index * layout.line_step),
                line.text,
                font=font,
                fill=255,
                stroke_width=stroke,
                stroke_fill=255,
                anchor="ls",
            )
        if blur:
            mask = mask.filter(ImageFilter.GaussianBlur(blur))
        alpha = mask.point(lambda value: value * typo.shadow_alpha // 255)
        shadow = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
        shadow.putalpha(alpha)
        layer.alpha_composite(shadow)

    draw = ImageDraw.Draw(layer)
    for index, line in enumerate(layout.lines):
        y = layout.baseline0 + index * layout.line_step
        cursor = layout.left
        for run_text, yellow in line.runs:
            draw.text(
                (cursor, y),
                run_text,
                font=font,
                fill=typo.emphasis_fill if yellow else typo.fill,
                stroke_width=stroke,
                stroke_fill=typo.stroke_fill,
                anchor="ls",
            )
            cursor += _text_width(run_text, font)
    return layer


def _bbox_within(bbox: tuple[int, int, int, int] | None, rect: TextRectangle) -> bool:
    if bbox is None:
        return True
    x0, y0, x1, y1 = bbox
    return x0 >= rect.x0 and y0 >= rect.y0 and x1 <= rect.x1 and y1 <= rect.y1


def _diff_bbox(a: Image.Image, b: Image.Image) -> tuple[int, int, int, int] | None:
    return ImageChops.difference(a.convert("RGB"), b.convert("RGB")).getbbox()


def _changed_pixels(a: Image.Image, b: Image.Image) -> int:
    histogram = ImageChops.difference(a.convert("RGB"), b.convert("RGB")).convert("L").histogram()
    return sum(histogram[1:])


def _relative_href(target: Path, start: Path) -> str:
    return Path(os.path.relpath(target, start)).as_posix()


def _config_basis(
    title: str,
    rect: TextRectangle,
    typo: Typography,
    variants: Sequence[TextVariant],
    font_sha: str,
) -> dict[str, Any]:
    """Everything a caller could change to move the experiment: title, type,
    rectangle and the three headlines. Hashed into `config_sha256`."""
    return {
        "fixed_title": title,
        "text_rectangle": rect.as_dict(),
        "canvas": {"width": CANVAS[0], "height": CANVAS[1]},
        "typography": {
            "font_path": str(Path(typo.font_path)),
            "font_sha256": font_sha,
            "font_weight": typo.weight,
            "fill": typo.fill,
            "emphasis_fill": typo.emphasis_fill,
            "stroke_fill": typo.stroke_fill,
            "stroke_ratio": typo.stroke_ratio,
            "shadow_offset_ratio": typo.shadow_offset_ratio,
            "shadow_blur_ratio": typo.shadow_blur_ratio,
            "shadow_alpha": typo.shadow_alpha,
            "line_spacing": typo.line_spacing,
            "rect_padding_px": typo.rect_padding_px,
            "align": typo.align,
            "valign": typo.valign,
            "wrap": typo.wrap,
            "min_font_px": typo.min_font_px,
            "max_font_px": typo.max_font_px,
            "max_lines": typo.max_lines,
        },
        "variants": [v.as_dict() for v in variants],
    }


def _svg_for(
    layout: _Layout, typo: Typography, rect: TextRectangle, base_href: str, title: str
) -> str:
    """A native, editable text layer. The picture is linked, never copied."""
    stroke = max(1, int(round(layout.font_px * typo.stroke_ratio)))
    shadow_dy = int(round(layout.font_px * typo.shadow_offset_ratio))
    blur = max(1, int(round(layout.font_px * typo.shadow_blur_ratio)))
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{CANVAS[0]}" height="{CANVAS[1]}" '
        f'viewBox="0 0 {CANVAS[0]} {CANVAS[1]}">',
        "  <!-- EDITABLE TEXT LAYER. The background is linked, not copied: the",
        "       picture is owned by the upstream common base. -->",
        f'  <image x="0" y="0" width="{CANVAS[0]}" height="{CANVAS[1]}" '
        f'xlink:href="{_xml_escape(base_href)}" />',
        '  <filter id="softShadow" x="-20%" y="-20%" width="140%" height="140%">'
        f'<feDropShadow dx="0" dy="{shadow_dy}" stdDeviation="{blur}" '
        'flood-color="#000000" flood-opacity="0.65" /></filter>',
        f'  <g font-family="Montserrat" font-weight="{typo.weight}" '
        f'font-size="{layout.font_px}" fill="{typo.fill}" '
        f'stroke="{typo.stroke_fill}" stroke-width="{stroke}" '
        'stroke-linejoin="round" paint-order="stroke" filter="url(#softShadow)">',
    ]
    for index, line in enumerate(layout.lines):
        y = layout.baseline0 + index * layout.line_step
        parts.append(f'    <text x="{layout.left}" y="{y}">')
        for run_text, yellow in line.runs:
            fill = typo.emphasis_fill if yellow else typo.fill
            parts.append(f'      <tspan fill="{fill}">{_xml_escape(run_text)}</tspan>')
        parts.append("    </text>")
    parts.append("  </g>")
    parts.append(f"  <!-- fixed title, identical for A/B/C: {_xml_escape(title)} -->")
    parts.append(f'  <!-- text rectangle: {rect.as_dict()} -->')
    parts.append("</svg>")
    parts.append("")
    return "\n".join(parts)


def _layers_json_for(
    layout: _Layout,
    typo: Typography,
    rect: TextRectangle,
    base_href: str,
    title: str,
    evidence: str,
) -> dict[str, Any]:
    stroke = max(1, int(round(layout.font_px * typo.stroke_ratio)))
    return {
        "label": layout.variant.label,
        "text": layout.variant.text,
        "emphasis": layout.variant.emphasis,
        "fixed_title": title,
        "source_evidence": evidence,
        "renderer_version": RENDERER_VERSION,
        "canvas": {"width": CANVAS[0], "height": CANVAS[1]},
        "text_rectangle": rect.as_dict(),
        "base": {
            "path": base_href,
            "editable": False,
            "note": "background owned upstream; this layer renders above it",
        },
        "typography": {
            "font_family": "Montserrat",
            "font_path": str(Path(typo.font_path)),
            "font_weight": typo.weight,
            "font_px": layout.font_px,
            "fill": typo.fill,
            "emphasis_fill": typo.emphasis_fill,
            "stroke_fill": typo.stroke_fill,
            "stroke_width": stroke,
            "shadow": {
                "dx": 0,
                "dy": int(round(layout.font_px * typo.shadow_offset_ratio)),
                "blur": max(0, int(round(layout.font_px * typo.shadow_blur_ratio))),
                "alpha": typo.shadow_alpha,
            },
            "line_spacing": typo.line_spacing,
            "align": typo.align,
            "valign": typo.valign,
        },
        "lines": [
            {
                "text": line.text,
                "x": layout.left,
                "baseline_y": layout.baseline0 + index * layout.line_step,
                "runs": [
                    {
                        "text": run_text,
                        "fill": typo.emphasis_fill if yellow else typo.fill,
                        "emphasis": bool(yellow),
                    }
                    for run_text, yellow in line.runs
                ],
            }
            for index, line in enumerate(layout.lines)
        ],
        "coordinate_space": "canvas pixels; y is the text BASELINE, the same "
                            "origin the SVG text element uses",
    }


def _coerce_typography(receipt_typo: Mapping[str, Any], font_path: Path) -> Typography:
    defaults = Typography()
    return Typography(
        font_path=font_path,
        weight=int(receipt_typo.get("font_weight", defaults.weight)),
        min_font_px=int(receipt_typo.get("font_px", receipt_typo.get("min_font_px",
                                                                    defaults.min_font_px))),
        max_font_px=int(receipt_typo.get("font_px", receipt_typo.get("max_font_px",
                                                                    defaults.max_font_px))),
        max_lines=int(receipt_typo.get("max_lines", defaults.max_lines)),
        fill=str(receipt_typo.get("fill", defaults.fill)),
        emphasis_fill=str(receipt_typo.get("emphasis_fill", defaults.emphasis_fill)),
        stroke_fill=str(receipt_typo.get("stroke_fill", defaults.stroke_fill)),
        stroke_ratio=float(receipt_typo.get("stroke_ratio", defaults.stroke_ratio)),
        shadow_offset_ratio=float(
            receipt_typo.get("shadow_offset_ratio", defaults.shadow_offset_ratio)),
        shadow_blur_ratio=float(
            receipt_typo.get("shadow_blur_ratio", defaults.shadow_blur_ratio)),
        shadow_alpha=int(receipt_typo.get("shadow_alpha", defaults.shadow_alpha)),
        line_spacing=float(receipt_typo.get("line_spacing", defaults.line_spacing)),
        rect_padding_px=int(receipt_typo.get("rect_padding_px", defaults.rect_padding_px)),
        align=str(receipt_typo.get("align", defaults.align)),
        valign=str(receipt_typo.get("valign", defaults.valign)),
    )


def _receipt_checksum(receipt: Mapping[str, Any]) -> str:
    body = json.loads(json.dumps(receipt))
    hashes = body.get("hashes")
    if isinstance(hashes, dict):
        hashes.pop("receipt_checksum_sha256", None)
    return _canonical_sha256(body)


def build_text_only_experiment(
    *,
    base: Path | str,
    title: str,
    variants: Iterable[TextVariant | Mapping[str, Any]],
    evidence: str,
    outdir: Path | str,
    rectangle: TextRectangle | Sequence[int] | Mapping[str, int] | None = None,
    typography: Typography | None = None,
) -> dict[str, Any]:
    """Build the A/B/C text-only experiment over one shared base.

    `base` is the supplied common picture (arrow already baked in upstream);
    `title` is the single fixed video title; `variants` are exactly the A/B/C
    records of (label, text, yellow emphasis substring); `evidence` is the
    source text the headlines come from - recorded as supplied, never judged
    here. Writes the exports and the receipt into `outdir` and returns it.

    Raises `ThumbnailTextTestError` carrying every gate failure, before any file
    is written, when the experiment is not valid or provably not buildable.
    """
    typo = typography or Typography()
    outdir_path = Path(outdir)
    rect = _coerce_rect(rectangle)
    base_path = Path(base)
    variant_list = _coerce_variants(variants)

    # ---- stage 1: inputs (no files, no rendering) ------------------------
    failures: list[GateFailure] = []
    labels = [v.label for v in variant_list]
    if sorted(labels) != sorted(LABELS) or len(labels) != len(LABELS):
        failures.append(GateFailure(
            "VARIANT_LABELS",
            f"need exactly the labels {list(LABELS)} once each, got {labels}",
        ))
    if not _normalize_whitespace(title):
        failures.append(GateFailure("MISSING_TITLE", "the fixed video title is blank"))
    if not _normalize_whitespace(evidence):
        failures.append(GateFailure(
            "MISSING_EVIDENCE",
            "source evidence text is required; it is recorded here and reviewed "
            "elsewhere, but the experiment will not run without it",
        ))
    seen: dict[str, str] = {}
    for variant in variant_list:
        normalized = variant.normalized_text()
        if not normalized:
            failures.append(GateFailure(
                "BLANK_HEADLINE", f"variant {variant.label} has no headline text"))
        elif normalized in seen:
            failures.append(GateFailure(
                "DUPLICATE_HEADLINE",
                f"variant {variant.label} repeats variant {seen[normalized]}: {normalized}",
            ))
        else:
            seen[normalized] = variant.label
        if not variant.emphasis:
            failures.append(GateFailure(
                "MISSING_EMPHASIS",
                f"variant {variant.label} has no yellow emphasis substring",
            ))
        elif variant.text.find(variant.emphasis) < 0:
            if variant.text.lower().find(variant.emphasis.lower()) >= 0:
                failures.append(GateFailure(
                    "EMPHASIS_NOT_EXACT",
                    f"variant {variant.label}: the emphasis matches only "
                    "case-insensitively; pass the exact substring",
                ))
            else:
                failures.append(GateFailure(
                    "EMPHASIS_NOT_FOUND",
                    f"variant {variant.label}: the emphasis is not a substring of "
                    "the headline text",
                ))
        if has_profanity(variant.text):
            failures.append(GateFailure(
                "PROFANITY_IN_TEXT",
                f"variant {variant.label}: channel text is always censored "
                "(standing rule) - pass censored copy",
            ))
    if rect.x0 < 0 or rect.y0 < 0 or rect.x1 > CANVAS[0] or rect.y1 > CANVAS[1]:
        failures.append(GateFailure(
            "RECTANGLE_OUT_OF_CANVAS",
            f"{rect.as_dict()} is not inside {CANVAS[0]}x{CANVAS[1]}",
        ))
    if rect.width <= 2 * typo.rect_padding_px or rect.height <= 2 * typo.rect_padding_px:
        failures.append(GateFailure(
            "RECTANGLE_TOO_SMALL",
            f"{rect.as_dict()} leaves no room after {typo.rect_padding_px}px padding",
        ))
    if not base_path.is_file():
        failures.append(GateFailure("BASE_MISSING", f"no common base at {base_path}"))
    if not Path(typo.font_path).is_file():
        failures.append(GateFailure("FONT_MISSING", f"no font file at {typo.font_path}"))
    if failures:
        raise ThumbnailTextTestError(failures)

    font_sha = _sha256_file(Path(typo.font_path))

    opened_base = Image.open(base_path)
    opened_base.load()
    base_rgb = opened_base.convert("RGB")
    if base_rgb.size != CANVAS:
        raise ThumbnailTextTestError([GateFailure(
            "BASE_WRONG_SIZE",
            f"{base_path} decodes to {base_rgb.size}, expected {CANVAS}",
        )])
    base_bytes_sha = _sha256_file(base_path)
    base_pixel_sha = _sha256_image(base_rgb)

    # ---- stage 2: fit, then render into memory --------------------------
    fitted = _fit_common_size(variant_list, typo, rect)
    if fitted is None:
        widest = max(
            variant_list,
            key=lambda v: _text_width(v.text, _font_for(typo.font_path, 100, typo.weight)),
        )
        raise ThumbnailTextTestError([GateFailure(
            "TEXT_TOO_LONG",
            f"no common font size between {typo.min_font_px}px and "
            f"{typo.max_font_px}px fits all three headlines inside {rect.as_dict()} "
            f"in <= {typo.max_lines} lines (widest variant is {widest.label}); "
            "shorten the copy or widen the rectangle - nothing was written",
        )])
    font_px, layouts = fitted

    rendered: list[tuple[_Layout, Image.Image, Image.Image]] = []
    for layout in layouts:
        layer = _render_layer(layout, typo)
        ink_bbox = layer.getchannel("A").getbbox()
        layout.ink_bbox = ink_bbox
        if not _bbox_within(ink_bbox, rect):
            failures.append(GateFailure(
                "INK_OUTSIDE_TEXT_RECT",
                f"variant {layout.variant.label}: ink bbox {ink_bbox} escapes "
                f"{rect.as_dict()}; no pixel outside the rectangle may change",
            ))
        composite = base_rgb.copy()
        composite.paste(layer, (0, 0), layer)
        rendered.append((layout, layer, composite))

    # ---- stage 3: experiment invariants, still in memory ----------------
    for layout, _layer, composite in rendered:
        if _changed_pixels(composite, base_rgb) == 0:
            failures.append(GateFailure(
                "NO_INK",
                f"variant {layout.variant.label}: rendering changed no pixel",
            ))
        diff = _diff_bbox(composite, base_rgb)
        if not _bbox_within(diff, rect):
            failures.append(GateFailure(
                "BASE_MODIFIED_OUTSIDE_RECT",
                f"variant {layout.variant.label}: pixels outside {rect.as_dict()} "
                f"differ from the base (diff bbox {diff})",
            ))
    for i in range(len(rendered)):
        for j in range(i + 1, len(rendered)):
            left_label = rendered[i][0].variant.label
            right_label = rendered[j][0].variant.label
            diff = _diff_bbox(rendered[i][2], rendered[j][2])
            if diff is None:
                failures.append(GateFailure(
                    "IDENTICAL_RENDER",
                    f"variants {left_label} and {right_label} render identical bytes; "
                    "A/B/C must differ",
                ))
            elif not _bbox_within(diff, rect):
                failures.append(GateFailure(
                    "DIFF_OUTSIDE_RECT",
                    f"variants {left_label} and {right_label} differ outside "
                    f"{rect.as_dict()}",
                ))
    if failures:
        raise ThumbnailTextTestError(failures)

    # ---- stage 4: write the exports, then the receipt -------------------
    outdir_path.mkdir(parents=True, exist_ok=True)
    try:
        base_href = _relative_href(base_path, outdir_path)
    except ValueError:
        base_href = base_path.resolve().as_uri()

    variant_records: list[dict[str, Any]] = []
    for layout, layer, composite in rendered:
        label = layout.variant.label
        layer_path = outdir_path / f"text_{label}.layers.json"
        layer_path.write_text(
            json.dumps(
                _layers_json_for(layout, typo, rect, base_href, title, evidence),
                indent=2,
                ensure_ascii=False,
            ) + "\n",
            encoding="utf-8",
        )
        svg_path = outdir_path / f"text_{label}.svg"
        svg_path.write_text(_svg_for(layout, typo, rect, base_href, title), encoding="utf-8")
        png_path = outdir_path / f"variant_{label}.png"
        composite.save(png_path, format="PNG")
        variant_records.append({
            "label": label,
            "text": layout.variant.text,
            "emphasis": layout.variant.emphasis,
            "normalized_text": layout.variant.normalized_text(),
            "font_px": font_px,
            "lines": [line.text for line in layout.lines],
            "ink_bbox": list(layer.getchannel("A").getbbox() or ()),
            "png_path": str(png_path.resolve()),
            "png_sha256": _sha256_file(png_path),
            "png_pixel_sha256": _sha256_image(composite),
            "png_bytes": png_path.stat().st_size,
            "svg_path": str(svg_path.resolve()),
            "svg_sha256": _sha256_file(svg_path),
            "layer_path": str(layer_path.resolve()),
            "layer_sha256": _sha256_file(layer_path),
            "changed_pixels_vs_base": _changed_pixels(composite, base_rgb),
        })

    config = _config_basis(title, rect, typo, variant_list, font_sha)
    receipt: dict[str, Any] = {
        "receipt_type": RECEIPT_TYPE,
        "renderer": {
            "module": "boydclips.thumbnail_text_test",
            "version": RENDERER_VERSION,
            "pillow": getattr(Image, "__version__", "unknown"),
        },
        "fixed_title": title,
        "canvas": {"width": CANVAS[0], "height": CANVAS[1]},
        "text_rectangle": rect.as_dict(),
        "typography": dict(config["typography"], font_px=font_px),
        "source_evidence": {
            "text": evidence,
            "present": True,
            "verified": False,
            "note": "recorded as supplied; not checked here - semantic review "
                    "against the transcript happens elsewhere",
        },
        "base": {
            "path": str(base_path.resolve()),
            "sha256": base_bytes_sha,
            "pixel_sha256": base_pixel_sha,
            "pixel_normalization": "decoded, converted to RGB, canvas order",
            "size": list(base_rgb.size),
            "original_mode": opened_base.mode,
            "background_modifications": "none - text layers only",
        },
        "hashes": {
            "font_sha256": font_sha,
            "config_sha256": _canonical_sha256(config),
            "checksum_note": "receipt_checksum_sha256 is a sha256 over the canonical "
                             "receipt body without that field. It binds the settings; "
                             "it is a checksum, NOT a signature - anyone holding this "
                             "file can recompute it.",
        },
        "config": config,
        "variants": variant_records,
        "invariants": {
            "same_base_for_all_variants": True,
            "outside_text_rect_identical_to_base": True,
            "inside_text_rect_differs_across_variants": True,
            "common_font_size_px": font_px,
            "fitted_against": "widest_variant",
            "same_fixed_title": True,
        },
        "not_claimed": [
            "not editorial approval of any headline",
            "not proof that the source evidence supports the words",
            "not published, uploaded or delivered anywhere",
        ],
    }
    receipt["hashes"]["receipt_checksum_sha256"] = _receipt_checksum(receipt)
    receipt_path = outdir_path / "thumbnail-text-only.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return receipt


def validate_experiment(
    receipt: Mapping[str, Any] | Path | str,
    *,
    base_path: Path | str | None = None,
) -> dict[str, Any]:
    """Malformed or unreadable required evidence fails closed."""
    try:
        return _validate_experiment(receipt, base_path=base_path)
    except (OSError, ValueError, TypeError, AttributeError, KeyError, OverflowError) as exc:
        return _validation_result([GateFailure("INVALID_EVIDENCE", str(exc))], {})


def _validate_experiment(
    receipt: Mapping[str, Any] | Path | str,
    *,
    base_path: Path | str | None = None,
) -> dict[str, Any]:
    """Re-open the whole experiment and re-check every claim in the receipt.

    Reloads the receipt, the base, the font and every variant PNG (plus each
    editable layer), and reports a failure for: a missing label or file, a
    swapped or mislabelled image, a changed base, a changed title / typography /
    rectangle, a modified background, ink outside the text rectangle, or
    variants that no longer differ from each other.

    Returns `{"ok": bool, "failures": [{"code", "detail"}], "checks": {...}}`.
    It does not raise for a bad experiment: a raise here would be a bug in the
    validator, not a verdict on the files.
    """
    failures: list[GateFailure] = []
    checks: dict[str, Any] = {}

    if isinstance(receipt, (str, Path)):
        try:
            receipt = json.loads(Path(receipt).read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            return _validation_result([GateFailure("RECEIPT_MISSING", str(exc))], checks)
        except OSError as exc:
            return _validation_result([GateFailure("RECEIPT_UNREADABLE", str(exc))], checks)
        except json.JSONDecodeError as exc:
            return _validation_result([GateFailure("RECEIPT_UNREADABLE", str(exc))], checks)

    if not isinstance(receipt, Mapping):
        return _validation_result(
            [GateFailure("RECEIPT_TYPE", "receipt must be a mapping or a path to JSON")],
            checks,
        )

    checks["receipt_type"] = receipt.get("receipt_type")
    if receipt.get("receipt_type") != RECEIPT_TYPE:
        failures.append(GateFailure(
            "RECEIPT_TYPE",
            f"receipt_type is {receipt.get('receipt_type')!r}, expected {RECEIPT_TYPE!r}",
        ))

    renderer = receipt.get("renderer") or {}
    checks["renderer_version"] = renderer.get("version")
    if renderer.get("version") != RENDERER_VERSION:
        failures.append(GateFailure(
            "RENDERER_VERSION",
            f"built by {renderer.get('version')!r}, this validator is "
            f"{RENDERER_VERSION!r}",
        ))

    stored = (receipt.get("hashes") or {}).get("receipt_checksum_sha256")
    recomputed = _receipt_checksum(receipt)
    checks["receipt_checksum"] = {"stored": stored, "recomputed": recomputed}
    if stored != recomputed:
        failures.append(GateFailure(
            "RECEIPT_CHECKSUM_MISMATCH",
            "the receipt body no longer matches its own checksum",
        ))

    config = receipt.get("config")
    if not isinstance(config, Mapping):
        failures.append(GateFailure("CONFIG_MISSING", "receipt carries no config basis"))
        config = {}
    config_sha = _canonical_sha256(config)
    stored_config_sha = (receipt.get("hashes") or {}).get("config_sha256")
    checks["config_sha256"] = {"stored": stored_config_sha, "recomputed": config_sha}
    if stored_config_sha != config_sha:
        failures.append(GateFailure(
            "CONFIG_HASH_MISMATCH",
            "title, rectangle, typography or variant copy changed after the build",
        ))
    if config.get("fixed_title") != receipt.get("fixed_title"):
        failures.append(GateFailure(
            "TITLE_CHANGED",
            f"receipt title {receipt.get('fixed_title')!r} != config title "
            f"{config.get('fixed_title')!r}",
        ))
    if config.get("text_rectangle") != receipt.get("text_rectangle"):
        failures.append(GateFailure(
            "RECTANGLE_CHANGED",
            f"receipt rectangle {receipt.get('text_rectangle')} != config "
            f"{config.get('text_rectangle')}",
        ))
    config_typo = dict(config.get("typography") or {})
    receipt_typo_raw = dict(receipt.get("typography") or {})
    compared = {k: receipt_typo_raw.get(k) for k in config_typo if k != "font_px"}
    if config_typo and any(config_typo[k] != compared[k] for k in compared):
        failures.append(GateFailure(
            "TYPOGRAPHY_CHANGED",
            "receipt typography no longer matches the config that was built",
        ))
    # The variant copy is bound to the config as well: a tampered headline in
    # the receipt is caught even if the receipt checksum has been recomputed.
    config_variants = {
        str(v.get("label")): v
        for v in (config.get("variants") or [])
        if isinstance(v, Mapping)
    }
    for variant in receipt.get("variants") or []:
        if not isinstance(variant, Mapping):
            continue
        label = str(variant.get("label"))
        if variant.get("font_px") != receipt_typo_raw.get("font_px"):
            failures.append(GateFailure("FONT_SIZE_DIFFERS", f"variant {label} does not use the common font size"))
        expected = config_variants.get(label)
        if expected is None:
            continue
        for field_name in ("text", "emphasis"):
            if str(variant.get(field_name, "")) != str(expected.get(field_name, "")):
                failures.append(GateFailure(
                    "VARIANT_COPY_CHANGED",
                    f"variant {label}: receipt {field_name} no longer matches the "
                    "copy the experiment was built from",
                ))

    font_path = Path(str(receipt_typo_raw.get("font_path", "")))
    font_sha_stored = (receipt.get("hashes") or {}).get("font_sha256")
    checks["font"] = {"path": str(font_path), "sha256": font_sha_stored}
    if not font_path.is_file():
        failures.append(GateFailure("FONT_MISSING", f"no font at {font_path}"))
    elif _sha256_file(font_path) != font_sha_stored:
        failures.append(GateFailure(
            "FONT_HASH_MISMATCH",
            f"{font_path} is not the font this receipt was built with",
        ))

    evidence = receipt.get("source_evidence") or {}
    checks["evidence"] = {
        "present": bool(str(evidence.get("text", "")).strip()),
        "verified": evidence.get("verified"),
        "note": evidence.get("note"),
    }
    if not str(evidence.get("text", "")).strip():
        failures.append(GateFailure(
            "EVIDENCE_MISSING", "receipt carries no source evidence text"))

    base_meta = receipt.get("base") or {}
    base_file = Path(str(base_path)) if base_path is not None else Path(str(base_meta.get("path", "")))
    checks["base"] = {"path": str(base_file), "sha256": base_meta.get("sha256")}
    base_image: Image.Image | None = None
    if not base_file.is_file():
        failures.append(GateFailure("BASE_MISSING", f"no base image at {base_file}"))
    else:
        if _sha256_file(base_file) != base_meta.get("sha256"):
            failures.append(GateFailure(
                "BASE_BYTES_HASH_MISMATCH",
                f"{base_file} is not the file this experiment was built on",
            ))
        try:
            opened = Image.open(base_file)
            opened.load()
            base_image = opened.convert("RGB")
        except OSError as exc:
            failures.append(GateFailure("BASE_UNREADABLE", str(exc)))
        if base_image is not None:
            if _sha256_image(base_image) != base_meta.get("pixel_sha256"):
                failures.append(GateFailure(
                    "BASE_PIXEL_HASH_MISMATCH",
                    "the base pixels changed after the build",
                ))
            if list(base_image.size) != list(base_meta.get("size") or []):
                failures.append(GateFailure(
                    "BASE_SIZE_CHANGED",
                    f"{list(base_image.size)} != receipt {base_meta.get('size')}",
                ))
            if base_image.size != CANVAS:
                failures.append(GateFailure(
                    "BASE_WRONG_SIZE",
                    f"base decodes to {base_image.size}, expected {CANVAS}",
                ))

    rect_raw = receipt.get("text_rectangle") or {}
    try:
        rect = TextRectangle(
            int(rect_raw["x0"]), int(rect_raw["y0"]),
            int(rect_raw["x1"]), int(rect_raw["y1"]),
        )
    except (KeyError, TypeError, ValueError):
        failures.append(GateFailure("RECTANGLE_MISSING", f"bad rectangle {rect_raw!r}"))
        rect = TextRectangle(*DEFAULT_RECTANGLE)

    variants = receipt.get("variants")
    if not isinstance(variants, list):
        failures.append(GateFailure("VARIANTS_MISSING", "receipt carries no variants"))
        variants = []
    labels = [str(v.get("label")) for v in variants if isinstance(v, Mapping)]
    checks["labels"] = labels
    if sorted(labels) != sorted(LABELS):
        failures.append(GateFailure(
            "VARIANT_LABELS", f"labels {labels} are not exactly {list(LABELS)}"))

    images: dict[str, Image.Image] = {}
    texts: dict[str, str] = {}
    for variant in variants:
        if not isinstance(variant, Mapping):
            failures.append(GateFailure("VARIANT_MALFORMED", "variant record is not a mapping"))
            continue
        label = str(variant.get("label"))
        texts[label] = str(variant.get("text", ""))
        png_path = Path(str(variant.get("png_path", "")))
        if not png_path.is_file():
            failures.append(GateFailure(
                "VARIANT_FILE_MISSING", f"variant {label}: no file at {png_path}"))
            continue
        if _sha256_file(png_path) != variant.get("png_sha256"):
            failures.append(GateFailure(
                "VARIANT_BYTES_HASH_MISMATCH",
                f"variant {label}: {png_path} bytes are not the built bytes",
            ))
        try:
            opened = Image.open(png_path)
            opened.load()
            image = opened.convert("RGB")
        except OSError as exc:
            failures.append(GateFailure("VARIANT_UNREADABLE", f"variant {label}: {exc}"))
            continue
        images[label] = image
        if image.size != CANVAS:
            failures.append(GateFailure(
                "VARIANT_WRONG_SIZE",
                f"variant {label}: {image.size} is not {CANVAS}",
            ))
        if _sha256_image(image) != variant.get("png_pixel_sha256"):
            failures.append(GateFailure(
                "VARIANT_PIXEL_HASH_MISMATCH",
                f"variant {label}: decoded pixels changed after the build",
            ))
        layer_path = Path(str(variant.get("layer_path", "")))
        if not layer_path.is_file():
            failures.append(GateFailure(
                "LAYER_FILE_MISSING",
                f"variant {label}: no editable layer at {layer_path}",
            ))
            continue
        if _sha256_file(layer_path) != variant.get("layer_sha256"):
            failures.append(GateFailure("LAYER_HASH_MISMATCH", f"variant {label} editable layer changed"))
        svg_path = Path(str(variant.get("svg_path", "")))
        if not variant.get("svg_path"):
            failures.append(GateFailure(
                "SVG_FILE_MISSING", f"variant {label}: receipt records no editable SVG"))
        elif not svg_path.is_file():
            failures.append(GateFailure(
                "SVG_FILE_MISSING", f"variant {label}: no editable SVG at {svg_path}"))
        elif _sha256_file(svg_path) != variant.get("svg_sha256"):
            failures.append(GateFailure(
                "SVG_HASH_MISMATCH",
                f"variant {label}: the editable text layer was edited after the build",
            ))
        try:
            layer = json.loads(layer_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            failures.append(GateFailure("LAYER_UNREADABLE", f"variant {label}: {exc}"))
            continue
        if isinstance(layer, Mapping):
            layer_words = _normalize_whitespace(
                " ".join(str(line.get("text", "")) for line in layer.get("lines", []))
            )
            if layer_words != _normalize_whitespace(texts[label]):
                failures.append(GateFailure(
                    "VARIANT_TEXT_CHANGED",
                    f"variant {label}: layer words {layer_words!r} != receipt text "
                    f"{texts[label]!r} (reworded, uppercased or truncated?)",
                ))
            layer_text = layer.get("text")
            if layer_text is not None and layer_text != texts[label]:
                failures.append(GateFailure(
                    "VARIANT_TEXT_CHANGED",
                    f"variant {label}: layer text is not the receipt text",
                ))

    normalized = [_normalize_whitespace(t) for t in texts.values() if t]
    if len(set(normalized)) != len(normalized):
        failures.append(GateFailure(
            "DUPLICATE_HEADLINE", "two variants carry the same headline text"))

    if base_image is not None:
        for label in sorted(images):
            diff = _diff_bbox(images[label], base_image)
            if not _bbox_within(diff, rect):
                failures.append(GateFailure(
                    "BACKGROUND_MODIFIED",
                    f"variant {label} differs from the base outside {rect.as_dict()} "
                    f"(diff bbox {diff})",
                ))
            elif diff is None:
                failures.append(GateFailure(
                    "VARIANT_IDENTICAL_TO_BASE",
                    f"variant {label} has no ink at all",
                ))
    present = [label for label in LABELS if label in images]
    for i in range(len(present)):
        for j in range(i + 1, len(present)):
            diff = _diff_bbox(images[present[i]], images[present[j]])
            if diff is None:
                failures.append(GateFailure(
                    "VARIANT_SWAPPED",
                    f"{present[i]} and {present[j]} are the same image - one was "
                    "overwritten by the other",
                ))
            elif not _bbox_within(diff, rect):
                failures.append(GateFailure(
                    "BACKGROUND_MODIFIED",
                    f"{present[i]} and {present[j]} differ outside {rect.as_dict()}",
                ))

    # Anti-swap: redraw each variant's own words from the receipt and compare.
    pillow_now = getattr(Image, "__version__", "unknown")
    pillow_built = renderer.get("pillow")
    checks["re_render"] = "skipped"
    if base_image is not None and images and pillow_now == pillow_built:
        try:
            typo = _coerce_typography(receipt_typo_raw, font_path)
            for variant in variants:
                if not isinstance(variant, Mapping):
                    continue
                label = str(variant.get("label"))
                if label not in images:
                    continue
                record = TextVariant(
                    label=label,
                    text=str(variant.get("text", "")),
                    emphasis=str(variant.get("emphasis", "")),
                )
                size = int(variant.get("font_px", receipt_typo_raw.get("font_px", 44)))
                layout = _layout_for_size(
                    record, _font_for(typo.font_path, size, typo.weight), rect, typo, size
                )
                if layout is None:
                    failures.append(GateFailure(
                        "VARIANT_LAYOUT_UNSOLVABLE",
                        f"variant {label} no longer lays out with the receipt settings",
                    ))
                    continue
                re_layer = _render_layer(layout, typo)
                re_composite = base_image.copy()
                re_composite.paste(re_layer, (0, 0), re_layer)
                if _diff_bbox(re_composite, images[label]) is not None:
                    failures.append(GateFailure(
                        "VARIANT_SWAPPED",
                        f"variant {label}: the file does not match a fresh render of "
                        "its own headline - image swapped, edited or mislabelled",
                    ))
            checks["re_render"] = "compared"
        except (OSError, ValueError, KeyError) as exc:  # pragma: no cover - defensive
            checks["re_render"] = f"failed: {exc}"
            failures.append(GateFailure("RENDER_CHECK_FAILED", str(exc)))
    elif pillow_now != pillow_built:
        checks["re_render"] = f"skipped: pillow {pillow_now} != {pillow_built}"
        failures.append(GateFailure("RENDERER_ENV_CHANGED", "Pillow changed; rebuild the experiment before accepting its text binding"))

    return _validation_result(failures, checks)


def _validation_result(
    failures: Sequence[GateFailure], checks: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "ok": not failures,
        "failures": [f.as_dict() for f in failures],
        "checks": dict(checks),
    }
