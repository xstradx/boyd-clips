# -*- coding: utf-8 -*-
"""The short's "FULL VIDEO OUT NOW" call to action — a compact lower-third.

Nathan, 2026-09-07 (third brief, rebuilt from scratch): a very subtle,
premium Shorts CTA that leads the eye to the related-video button near the
bottom of the screen. Phone-readable semi-condensed bold type (Archivo,
weight 800 / width 75), off-white on a compact dark backing. A short,
clean motion-graphics stroke — not an underline, not a scribble — leaves
the side of the text and curves down toward the button; its small head
eases into place with a tiny overshoot, then nudges ONCE toward the
button. The whole unit is about 15-20 % of the frame width, low in the
frame, away from faces, hands and the caption rail. Soft UI tone on the
text, a light swish under the draw, a tiny tick as the head settles — all
well under the courtroom audio. No end card, no freeze, no loop.

Module layout
-------------
* ``plan_cta``      WHERE and WHEN: lower-left or lower-right of the bottom
  slot, whichever the measured face (hard veto), the body under it, the
  caption rail, the watermark, YouTube's own UI and the sampled picture
  leave clearest; end-anchored so the CTA holds through the last frame.
  Returns a ``CtaPlacement`` whose ``box`` joins the ONE overlay layout.
* ``build_assets``  the RGBA PNG sequence at the project frame rate (PIL,
  drawn at 3x, Lanczos down) and the synthesised sound, level-matched to
  the kept dialogue by measurement.
* ``ffmpeg_chain``  the extra inputs and filter fragments render_short
  composites in its ONE pass (overlay in 4:4:4 after the watermark, amix
  under the dialogue). No second encode.

Motion (every curve is a cubic-bezier; nothing linear)
    text    opacity 0 -> 1, 10 px rise, 98 -> 100 % scale, ~280 ms ease-out
    stroke  draws on over ~500 ms from 180 ms in (standard ease: slow-in, long ease-out)
    head    eases into the tip over ~220 ms with a small overshoot (ease-out-back)
    nudge   ONE 2.5 px push of the arrow toward the button, ~260 ms, then still
    hold    ~3.7 s; fade ~350 ms only if the video continues afterwards
Everything is a parameter under output.short.cta in config/pipeline.yaml.
"""
from __future__ import annotations

import json
import logging
import math
import re
import subprocess
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from . import layout

log = logging.getLogger("boydclips.cta")

ROOT = Path(__file__).resolve().parents[2]
CANVAS_W = layout.CANVAS_W
CANVAS_H = layout.CANVAS_H

DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "text": "FULL VIDEO OUT NOW",
    "lines": 2,                # balanced word wrap into this many lines (a compact lower-third block)
    # OUTPUT-time start in seconds, or "auto": end-anchored so the CTA is
    # still on screen on the last frame (no fade — the video does not
    # continue). A numeric start earlier than that fades out after the hold.
    "start_s": "auto",
    "tail_s": 0.0,
    # motion
    "enter_s": 0.28,
    "rise_px": 10,
    "scale_from": 0.98,
    "arrow_delay_s": 0.18,
    "draw_s": 0.50,
    "head_settle_s": 0.22,
    "head_overshoot_px": 3.0,
    "nudge_delay_s": 0.12,
    "nudge_s": 0.26,
    "nudge_px": 2.5,
    "hold_s": 3.7,
    "fade_s": 0.35,
    # placement
    "side": "auto",            # auto | left | right
    "edge_margin_px": 56,
    "text_top_frac": 0.75,     # phone-readable block above the related-video row
    "face_margin_frac": 0.30,
    "scale": 1.0,
    "opacity": 0.95,
    # type — Archivo variable: weight 800, width 75 (semi-condensed), tracked caps
    "font": "assets/fonts/Archivo-Var.ttf",
    "font_weight": 800,
    "font_width": 75,
    "font_size": 52,
    "tracking_em": 0.08,
    "line_gap_frac": 0.30,     # gap between the two lines, as a fraction of the font size
    "color": "#F2EFE9",
    "shadow": {"opacity": 0.45, "blur_px": 5, "dy_px": 2},
    "backing": {"opacity": 0.58, "pad_x_px": 9, "pad_y_px": 7, "radius_px": 10},
    # arrow — a short stroke that leaves the side of the block at its
    # vertical middle, curves and points down at the button row below
    "arrow": {
        "stroke_px": 6,
        "head_len_px": 20,
        "head_angle_deg": 30,
        "gap_px": 18,          # between the text block and the stroke's start
        "reach_px": 28,        # how far the stroke travels sideways (away from the text)
        "drop_px": 110,        # how far it drops
        # Optional absolute end point as canvas fractions (e.g. a measured
        # related-video chip). null = relative to the text block.
        "target": [0.36, 0.855],
        # The stroke is decorative; the subject's face is not. A stroke whose
        # lane is blocked by the measured face box is clamped to the clear lane,
        # and omitted entirely when even its start would sit over the face
        # (2026-09-13: a close-up judge fills the bottom slot and the fixed
        # target [0.36, 0.855] put the head on her cheek).
        "clearance_px": 14,    # minimum gap between the stroke and the face box
    },
    # YouTube's own UI as canvas fractions: the right action column and the
    # bottom band (chip, channel row, title). The text keeps out of both;
    # the arrow tip may point into the band, on purpose.
    "ui_reserved": {"right_col_x": 0.815, "right_col_y": [0.52, 0.93], "bottom_band_y": 0.885},
    # sound — three quiet cues, level set against the measured dialogue
    "sound": {
        "enabled": True,
        "relative_db": -20.0,
        "ui": True,            # soft two-partial tone as the text appears
        "swish": True,         # light airy swish under the draw
        "tick": True,          # tiny tick as the head settles
    },
}


def cfg_with_defaults(cta_cfg: dict[str, Any] | None) -> dict[str, Any]:
    """Deep-merge the configured block over the tuned defaults."""
    out: dict[str, Any] = json.loads(json.dumps(DEFAULTS))
    for k, v in (cta_cfg or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update({kk: vv for kk, vv in v.items() if vv is not None})
        elif v is not None:
            out[k] = v
    return out


def enabled(cta_cfg: dict[str, Any] | None) -> bool:
    return bool(cfg_with_defaults(cta_cfg).get("enabled", True))


# ---------------------------------------------------------------- easing


def cubic_bezier(x1: float, y1: float, x2: float, y2: float):
    """CSS-style cubic-bezier(x1, y1, x2, y2); f(t) on [0, 1]. y may exceed 1
    (overshoot) when y1/y2 do."""

    def bez(a: float, b: float, t: float) -> float:
        return 3 * a * (1 - t) ** 2 * t + 3 * b * (1 - t) * t ** 2 + t ** 3

    def f(t: float) -> float:
        if t <= 0.0:
            return 0.0
        if t >= 1.0:
            return 1.0
        lo, hi = 0.0, 1.0
        u = t
        for _ in range(40):
            u = (lo + hi) / 2.0
            if bez(x1, x2, u) < t:
                lo = u
            else:
                hi = u
        return bez(y1, y2, u)

    return f


EASE_OUT = cubic_bezier(0.16, 1.0, 0.30, 1.0)         # text entrance
EASE_DRAW = cubic_bezier(0.40, 0.0, 0.20, 1.0)        # stroke draw: slow in, long ease out
EASE_BACK = cubic_bezier(0.34, 1.56, 0.64, 1.0)       # head settle with a small overshoot
EASE_SMOOTH = cubic_bezier(0.40, 0.0, 0.60, 1.0)      # nudge / fade


# ---------------------------------------------------------------- placement


@dataclass
class CtaPlacement:
    side: str
    text_box: layout.Box            # the text block, canvas px
    lines: list[str]
    arrow_start: tuple[float, float] | None
    arrow_target: tuple[float, float] | None
    box: layout.Box                 # union of text + arrow: the overlay-layout entry
    start_s: float
    end_s: float
    fade: bool
    timeline: dict[str, float]
    scores: dict[str, Any]
    font_px: int
    tracking_px: float
    # The arrow config this stroke was actually drawn with (a clamped target
    # when the lane beside the subject was narrower than the configured one),
    # or None when no stroke is drawn at all this time.
    arrow_override: dict[str, Any] | None = None
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "side": self.side, "lines": self.lines,
            "text_box": self.text_box.as_dict(), "box": self.box.as_dict(),
            "arrow_start": None if self.arrow_start is None else [round(v, 1) for v in self.arrow_start],
            "arrow_target": None if self.arrow_target is None else [round(v, 1) for v in self.arrow_target],
            "arrow_override": self.arrow_override,
            "start_s": round(self.start_s, 3), "end_s": round(self.end_s, 3), "fade_out": self.fade,
            "timeline": {k: round(v, 3) for k, v in self.timeline.items()},
            "scores": self.scores, "font_px": self.font_px, "tracking_px": round(self.tracking_px, 2),
            "notes": self.notes,
        }


def _font_path(c: dict[str, Any]) -> Path:
    p = Path(str(c["font"]))
    return p if p.is_absolute() else ROOT / p


def load_font(c: dict[str, Any], px: int):
    from PIL import ImageFont
    font = ImageFont.truetype(str(_font_path(c)), px)
    try:
        axes = font.get_variation_axes()
        values = []
        for ax in axes:
            name = ax["name"].decode() if isinstance(ax["name"], bytes) else str(ax["name"])
            if name.lower().startswith("weight"):
                values.append(min(ax["maximum"], max(ax["minimum"], float(c["font_weight"]))))
            elif name.lower().startswith("width"):
                values.append(min(ax["maximum"], max(ax["minimum"], float(c["font_width"]))))
            else:
                values.append(ax["default"])
        if values:
            font.set_variation_by_axes(values)
    except OSError:
        pass                                  # a static face: nothing to set
    return font


def wrap_lines(text: str, lines: int) -> list[str]:
    """Balanced word wrap of `text` into `lines` lines (by character count)."""
    words = text.split()
    n = max(1, min(int(lines), len(words)))
    if n == 1:
        return [" ".join(words)]

    def splits(ws: list[str], k: int):
        if k == 1:
            yield [ws]
            return
        for i in range(1, len(ws) - k + 2):
            for rest in splits(ws[i:], k - 1):
                yield [ws[:i]] + rest

    best: list[str] | None = None
    best_cost = None
    for parts in splits(words, n):
        lens = [len(" ".join(p)) for p in parts]
        cost = max(lens) - min(lens) + 0.01 * max(lens)
        if best_cost is None or cost < best_cost:
            best, best_cost = [" ".join(p) for p in parts], cost
    return best or [" ".join(words)]


def _line_width(font, line: str, tracking_px: float) -> float:
    w = 0.0
    for i, ch in enumerate(line):
        w += font.getlength(ch)
        if i < len(line) - 1:
            w += tracking_px
    return w


def measure_block(c: dict[str, Any], lines: Sequence[str], px: int, tracking_px: float) -> dict[str, Any]:
    """Width / height / cap-top offset of the text block: cap height from the
    glyph boxes, lines separated by line_gap_frac of the size."""
    font = load_font(c, px)
    widths = [_line_width(font, ln, tracking_px) for ln in lines]
    top, bottom = 1e9, -1e9
    for ln in lines:
        for ch in ln:
            if ch == " ":
                continue
            l, t, r, b = font.getbbox(ch)
            top, bottom = min(top, t), max(bottom, b)
    if top > bottom:
        top, bottom = 0.0, float(px)
    cap_h = float(bottom - top)
    gap = float(c["line_gap_frac"]) * px
    return {"w": max(widths), "h": cap_h * len(lines) + gap * (len(lines) - 1), "cap_h": cap_h,
            "top_off": float(top), "gap": gap, "widths": widths}


def _face_boxes(comp: dict[str, Any], c: dict[str, Any], punch: float = 1.0
                ) -> tuple[layout.Box | None, layout.Box | None, str]:
    """The BOTTOM slot's subject as canvas boxes: (face grown by the margin,
    body below it), from the measured anchor and the base window. None
    when no face was measured (geometric fallback).

    `punch` is the punch-in scale of the bottom tile while the CTA is on
    screen: a punched tile is a tighter window, so the subject on the canvas
    is that much bigger and the box has to grow with it. Ignoring it
    (until 2026-09-13) under-sized the box whenever the CTA ran over a
    punched beat."""
    base = (comp.get("base") or {}).get("bottom") or {}
    anchor = (comp.get("anchors") or {}).get("bottom") or {}
    div = int(comp.get("divider_y", layout.DIVIDER_Y))
    sx = float(base.get("subject_x", CANVAS_W / 2.0))
    sy = float(base.get("subject_y", 0.42 * layout.SLOT_H)) + div
    fw, fh = anchor.get("face_w"), anchor.get("face_h")
    source = str(anchor.get("source", ""))
    if not fw or not fh:
        return None, None, source
    zoom = float(base.get("zoom", 1.0)) or 1.0
    scale = zoom * max(1.0, float(punch or 1.0))
    face_w = float(fw) * CANVAS_W * scale
    face_h = float(fh) * layout.SLOT_H * scale
    m = float(c["face_margin_frac"])
    face = layout.Box(sx - face_w * (0.5 + m), sy - face_h * (0.5 + m),
                      face_w * (1 + 2 * m), face_h * (1 + 2 * m), "face_bottom", True)
    body = layout.Box(sx - 1.7 * face_w, sy + face_h * 0.5, 3.4 * face_w,
                      max(0.0, CANVAS_H - (sy + face_h * 0.5)), "body_bottom", False)
    return face, body, source


def _overlap(a: layout.Box, b: layout.Box) -> float:
    w = min(a.x2, b.x2) - max(a.x, b.x)
    h = min(a.y2, b.y2) - max(a.y, b.y)
    return max(0.0, w) * max(0.0, h)


def arrow_path(text_box: layout.Box, side: str, c: dict[str, Any], n: int = 200) -> list[tuple[float, float]]:
    """The stroke as sampled points in draw order: it leaves the side of the
    text block at its vertical middle, travels a little sideways, bends and
    arrives pointing straight down at the button row. A left-side block has
    the stroke on its right; a right-side block, mirrored, on its left.
    `arrow.target` (canvas fractions) forces the end point."""
    ar = c["arrow"]
    sc = float(c["scale"])
    sign = 1.0 if side == "left" else -1.0
    sx = (text_box.x2 if side == "left" else text_box.x) + sign * float(ar["gap_px"]) * sc
    sy = text_box.y + text_box.h * 0.5
    if isinstance(ar.get("target"), (list, tuple)) and len(ar["target"]) == 2:
        ex, ey = float(ar["target"][0]) * CANVAS_W, float(ar["target"][1]) * CANVAS_H
    else:
        ex, ey = sx + sign * float(ar["reach_px"]) * sc, sy + float(ar["drop_px"]) * sc
    reach = abs(ex - sx)
    drop = max(1.0, ey - sy)
    p1 = (sx + sign * reach * 0.85, sy)                    # leaves horizontally
    p2 = (ex, ey - drop * 0.55)                             # arrives vertically
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        x = u ** 3 * sx + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * ex
        y = u ** 3 * sy + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * ey
        pts.append((x, y))
    return pts


def _arrow_geometry(text_box: layout.Box, side: str, c: dict[str, Any]
                    ) -> tuple[tuple[float, float], tuple[float, float], layout.Box]:
    pts = arrow_path(text_box, side, c, n=64)
    xs = [q[0] for q in pts]
    ys = [q[1] for q in pts]
    pad = (float(c["arrow"]["stroke_px"]) * 3 + float(c["arrow"]["head_len_px"]) + float(c["head_overshoot_px"])
           + float(c["nudge_px"])) * float(c["scale"])
    return pts[0], pts[-1], layout.Box(min(xs) - pad, min(ys) - pad, (max(xs) - min(xs)) + 2 * pad,
                                       (max(ys) - min(ys)) + 2 * pad, "cta_arrow", True)


def frame_busyness(frames: Sequence[Any], box: layout.Box) -> float | None:
    """Mean gradient magnitude (0..1) of canvas frames inside `box`; emptier
    picture scores lower. None when nothing was sampled."""
    if not frames:
        return None
    x0, y0 = int(max(0, box.x)), int(max(0, box.y))
    x1, y1 = int(min(CANVAS_W, box.x2)), int(min(CANVAS_H, box.y2))
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None
    vals = []
    for fr in frames:
        g = fr[y0:y1, x0:x1].astype("float32").mean(axis=2) / 255.0
        gx = abs(g[:, 1:] - g[:, :-1]).mean()
        gy = abs(g[1:, :] - g[:-1, :]).mean()
        vals.append(float(gx + gy))
    return round(sum(vals) / len(vals), 4)


def core_duration(c: dict[str, Any]) -> float:
    """Visible time before the hold ends, excluding any fade."""
    motion = (float(c["arrow_delay_s"]) + float(c["draw_s"]) + float(c["head_settle_s"])
              + float(c["nudge_delay_s"]) + float(c["nudge_s"]))
    return max(float(c["enter_s"]), motion) + float(c["hold_s"])


def plan_cta(cta_cfg: dict[str, Any] | None, duration_s: float, comp: dict[str, Any],
             cap_box: layout.Box, wm_box: layout.Box | None, frames: Sequence[Any] | None = None,
             fps: int = 30) -> CtaPlacement:
    """Choose side and timing; deterministic given the composition (and the
    optional sampled frames); records every score it used."""
    c = cfg_with_defaults(cta_cfg)
    scale = float(c["scale"])
    px = int(round(float(c["font_size"]) * scale))
    tracking = float(c["tracking_em"]) * px
    lines = wrap_lines(str(c["text"]), int(c["lines"]))
    blk = measure_block(c, lines, px, tracking)
    tw, th = blk["w"], blk["h"]
    margin = float(c["edge_margin_px"])
    top = float(c["text_top_frac"]) * CANVAS_H
    ui = c["ui_reserved"]
    right_col_x = float(ui["right_col_x"]) * CANVAS_W
    bottom_band_y = float(ui["bottom_band_y"]) * CANVAS_H

    # The bottom subject is punched on some beats; the CTA is end-anchored and
    # usually lands on one, so the face box has to account for the largest
    # bottom-tile punch in the plan.
    punch = 1.0
    for seg in (comp.get("segments") or []):
        if isinstance(seg, dict) and seg.get("punch") == "bottom":
            try:
                punch = max(punch, float(seg.get("punch_scale") or 1.0))
            except (TypeError, ValueError):
                continue
    face, body, face_source = _face_boxes(comp, c, punch)
    ui_right = layout.Box(right_col_x, float(ui["right_col_y"][0]) * CANVAS_H,
                          CANVAS_W - right_col_x, (float(ui["right_col_y"][1]) - float(ui["right_col_y"][0])) * CANVAS_H,
                          "yt_right_column", False)
    ui_bottom = layout.Box(0, bottom_band_y, CANVAS_W, CANVAS_H - bottom_band_y, "yt_bottom_band", False)

    candidates: dict[str, dict[str, Any]] = {}
    for side in ("left", "right"):
        if side == "left":
            x = margin
        else:
            x = min(CANVAS_W - margin - tw, right_col_x - 28.0 - tw)
        tbox = layout.Box(x, top, tw, th, "cta_text", True)
        start, tgt, abox = _arrow_geometry(tbox, side, c)
        union = layout.Box(min(tbox.x, abox.x), min(tbox.y, abox.y), 0, 0, "cta", True)
        union.w = max(tbox.x2, abox.x2) - union.x
        union.h = max(tbox.y2, abox.y2) - union.y
        area = max(1.0, union.w * union.h)
        veto: list[str] = []
        score = 0.0
        if face is not None and _overlap(face, union) > 0:
            veto.append("over the bottom subject's face")
        if _overlap(cap_box, union) > 0:
            veto.append("inside the caption rail")
        if wm_box is not None and _overlap(wm_box, union) > 0:
            veto.append("collides with the watermark")
        if _overlap(ui_right, union) > 0:
            veto.append("inside YouTube's action column")
        if _overlap(ui_bottom, tbox) > 0:
            veto.append("text inside YouTube's bottom band")
        body_frac = (_overlap(body, union) / area) if body is not None else 0.0
        score += 30.0 * body_frac
        busy = frame_busyness(frames or [], union)
        if busy is not None:
            score += 120.0 * busy
        if side == "right":
            score += 12.0                     # the chip is bottom-left; taste cost, not a rule
        candidates[side] = {"text_box": tbox, "arrow_start": start, "arrow_end": tgt, "arrow_box": abox, "box": union,
                            "score": round(score, 2), "veto": veto, "body_overlap_frac": round(body_frac, 3),
                            "busyness": busy}

    want = str(c["side"]).lower()
    notes: list[str] = []
    if want in ("left", "right"):
        chosen = want
        if candidates[want]["veto"]:
            notes.append(f"forced side {want} despite: " + "; ".join(candidates[want]["veto"]))
    else:
        clear = [s for s in ("left", "right") if not candidates[s]["veto"]]
        pool = clear or ["left", "right"]
        if not clear:
            notes.append("both sides vetoed — least-bad side chosen; review the frame")
        chosen = min(pool, key=lambda s: (candidates[s]["score"], s != "left"))
    if face is None:
        notes.append(f"no measured face in the bottom slot ({face_source or 'unknown'}); placement from busyness + UI only")

    # timing — OUTPUT time
    enter, delay, draw = float(c["enter_s"]), float(c["arrow_delay_s"]), float(c["draw_s"])
    settle, ndelay, nudge = float(c["head_settle_s"]), float(c["nudge_delay_s"]), float(c["nudge_s"])
    fade = float(c["fade_s"])
    core = core_duration(c)
    raw_start = c.get("start_s", "auto")
    if isinstance(raw_start, (int, float)) and not isinstance(raw_start, bool):
        start = float(raw_start)
        end = start + core + fade
        do_fade = end <= duration_s - 0.04
        if not do_fade:
            end = min(duration_s, start + core)
            notes.append("explicit start runs into the last frame: holds, no fade")
    else:
        tail = max(0.0, float(c["tail_s"]))
        do_fade = tail > 0.05
        end = duration_s - tail
        start = end - core - (fade if do_fade else 0.0)
    if start < 0.5:
        notes.append(f"CTA start clamped from {start:.2f}s to 0.5s — the short is very short")
        start = 0.5
        end = min(duration_s, start + core + (fade if do_fade else 0.0))
    start = round(start * float(fps)) / float(fps)
    end = round(end, 4)
    timeline = {
        "text_in": start, "text_settled": start + enter,
        "arrow_draw_start": start + delay, "arrow_drawn": start + delay + draw,
        "head_settled": start + delay + draw + settle,
        "nudge_start": start + delay + draw + settle + ndelay,
        "nudge_end": start + delay + draw + settle + ndelay + nudge,
        "hold_until": end - (fade if do_fade else 0.0), "end": end,
    }
    # The stroke is decoration; the subject's face is not. Clamp the stroke
    # into the clear lane beside the subject, and drop it entirely when the
    # lane is too narrow for even its start. The text block itself was already
    # checked against the face box above.
    cand = candidates[chosen]
    arrow_override: dict[str, Any] | None = None
    if (face is not None and cand.get("arrow_start") is not None
            and cand["arrow_box"].intersects(face)):
        clearance = float(c["arrow"].get("clearance_px", 0.0)) * scale
        if chosen == "left":
            lane = face.x - clearance
            start_x = cand["arrow_start"][0]
            too_narrow = start_x >= lane
            outside = cand["arrow_end"][0] > lane
        else:
            lane = face.x2 + clearance
            start_x = cand["arrow_start"][0]
            too_narrow = start_x <= lane
            outside = cand["arrow_end"][0] < lane
        if too_narrow:
            notes.append("stroke omitted: no clear lane between the block and the "
                         "bottom subject's face")
            cand = {**cand, "arrow_start": None, "arrow_end": None, "box": cand["text_box"]}
        elif outside:
            # A stroke clamped down to a stub reads as a glitch, not a pointer:
            # below this lateral run the whole stroke is dropped instead.
            min_run = max(8.0, 0.5 * float(c["arrow"].get("reach_px", 28.0)) * scale)
            run = (lane - cand["arrow_start"][0]) if chosen == "left" else (cand["arrow_start"][0] - lane)
            if run < min_run:
                notes.append(f"stroke omitted: only {run:.0f}px of clear lane beside the "
                             "bottom subject's face (a stub would read as a glitch)")
                cand = {**cand, "arrow_start": None, "arrow_end": None, "box": cand["text_box"]}
                arrow_override = None
            else:
                arrow_override = {"target": [lane / CANVAS_W, cand["arrow_end"][1] / CANVAS_H]}
                c_eff = dict(c)
                c_eff["arrow"] = {**c["arrow"], **arrow_override}
                start, tgt, abox = _arrow_geometry(cand["text_box"], chosen, c_eff)
                union = layout.Box(min(cand["text_box"].x, abox.x), min(cand["text_box"].y, abox.y), 0, 0, "cta", True)
                union.w = max(cand["text_box"].x2, abox.x2) - union.x
                union.h = max(cand["text_box"].y2, abox.y2) - union.y
                notes.append(f"stroke clamped to x={lane:.0f}px: the configured target sits "
                             "on the bottom subject's face")
                cand = {**cand, "arrow_start": start, "arrow_end": tgt, "arrow_box": abox, "box": union}

    scores = {s: {k: (v.as_dict() if isinstance(v, layout.Box) else v) for k, v in d.items()
                  if k not in ("text_box", "box", "arrow_start", "arrow_end")}
              for s, d in candidates.items()}
    scores["face_box"] = face.as_dict() if face else None
    scores["face_source"] = face_source
    scores["face_punch"] = round(punch, 4)
    scores["block_width_frac"] = round(cand["box"].w / CANVAS_W, 3)          # padded layout box
    # the VISIBLE unit: text block to the far edge of the stroke + head
    stroke_pad = (float(c["arrow"]["stroke_px"]) + float(c["arrow"]["head_len_px"]) * 0.5) * scale
    if cand["arrow_start"] is None:
        unit_w = cand["text_box"].w
    elif chosen == "left":
        unit_w = max(cand["arrow_end"][0], cand["arrow_start"][0]) + stroke_pad - cand["text_box"].x
    else:
        unit_w = cand["text_box"].x2 - (min(cand["arrow_end"][0], cand["arrow_start"][0]) - stroke_pad)
    scores["unit_width_frac"] = round(unit_w / CANVAS_W, 3)
    return CtaPlacement(
        side=chosen, text_box=cand["text_box"], lines=lines, arrow_start=cand["arrow_start"],
        arrow_target=cand["arrow_end"], box=cand["box"], start_s=start, end_s=end, fade=do_fade,
        timeline=timeline, scores=scores, font_px=px, tracking_px=tracking,
        arrow_override=arrow_override, notes=notes,
    )


# ---------------------------------------------------------------- frame sampling (for busyness)


def out_to_source(t_out: float, segments: Sequence[Any]) -> float | None:
    acc = 0.0
    for seg in segments:
        a, b = (seg.start_s, seg.end_s) if hasattr(seg, "start_s") else (float(seg[0]), float(seg[1]))
        d = b - a
        if acc - 1e-6 <= t_out <= acc + d + 1e-6:
            return a + (t_out - acc)
        acc += d
    return None


def sample_canvas_frames(source: Path, offset_s: float, segments: Sequence[Any], comp: dict[str, Any],
                         times_out: Sequence[float], work_dir: Path) -> list[Any]:
    """The BOTTOM slot as it will be composed, at output times, on a black
    canvas — only to measure how busy the candidate regions are."""
    import numpy as np
    from PIL import Image
    base = (comp.get("base") or {}).get("bottom") or {}
    try:
        cw, ch, cx, cy = layout.parse_crop(str(base.get("crop", "")))
    except ValueError:
        return []
    div = int(comp.get("divider_y", layout.DIVIDER_Y))
    work_dir.mkdir(parents=True, exist_ok=True)
    out: list[Any] = []
    for k, t in enumerate(times_out):
        ts = out_to_source(t, segments)
        if ts is None:
            continue
        png = work_dir / f"_cta_probe_{k}.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(0.0, ts - offset_s):.3f}", "-i", str(source),
                        "-frames:v", "1", str(png)], capture_output=True)
        if not png.exists():
            continue
        try:
            with Image.open(png) as im:
                tile = im.convert("RGB").crop((cx, cy, cx + cw, cy + ch)).resize((CANVAS_W, layout.SLOT_H), Image.LANCZOS)
                canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), (0, 0, 0))
                canvas.paste(tile, (0, div))
                out.append(np.asarray(canvas))
        finally:
            try:
                png.unlink()
            except OSError:
                pass
    return out


# ---------------------------------------------------------------- rendering


def _hex(color: str) -> tuple[int, int, int]:
    s = color.lstrip("#")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def _lighten(a, b):
    from PIL import ImageChops
    return ImageChops.lighter(a, b)


def _envelope(t: float, p: CtaPlacement, c: dict[str, Any]) -> dict[str, float]:
    """Animation state at OUTPUT time t."""
    tl = p.timeline
    enter = max(1e-3, float(c["enter_s"]))
    draw = max(1e-3, float(c["draw_s"]))
    settle = max(1e-3, float(c["head_settle_s"]))
    nudge_s = max(1e-3, float(c["nudge_s"]))
    fade = max(1e-3, float(c["fade_s"]))
    e_text = EASE_OUT((t - tl["text_in"]) / enter)
    e_draw = EASE_DRAW((t - tl["arrow_draw_start"]) / draw)
    # the head starts settling as the stroke reaches its last tenth
    head_t0 = tl["arrow_drawn"] - 0.1 * draw
    e_head = EASE_BACK((t - head_t0) / (settle + 0.1 * draw)) if t > head_t0 else 0.0
    u = (t - tl["nudge_start"]) / nudge_s
    nudge = math.sin(math.pi * EASE_SMOOTH(u)) if 0.0 <= u <= 1.0 else 0.0
    alpha = 1.0
    if p.fade and t > tl["hold_until"]:
        alpha = 1.0 - EASE_SMOOTH((t - tl["hold_until"]) / fade)
    return {"text": e_text, "draw": e_draw, "head": e_head, "nudge": nudge, "alpha": max(0.0, alpha)}


def _stroke(draw_obj, path: list[tuple[float, float]], width: float) -> None:
    if len(path) >= 2:
        draw_obj.line(path, fill=255, width=int(round(width)), joint="curve")
    r = width / 2.0
    for (x, y) in (path[0], path[-1]):
        draw_obj.ellipse((x - r, y - r, x + r, y + r), fill=255)


def render_frame(t: float, p: CtaPlacement, c: dict[str, Any], region: tuple[int, int, int, int],
                 ss: int = 3):
    """One canvas-sized RGBA frame at output time t, drawn at `ss` x inside
    `region` (x, y, w, h in canvas px) and downsampled with Lanczos."""
    from PIL import Image, ImageDraw, ImageFilter
    rx, ry, rw, rh = region
    W, H = rw * ss, rh * ss
    env = _envelope(t, p, c)
    sc = float(c["scale"])
    canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    if env["alpha"] <= 0.0 or (env["text"] <= 0.0 and env["draw"] <= 0.0):
        return canvas
    ink = Image.new("L", (W, H), 0)

    # --- text block: fade + rise + 98 -> 100 % scale, all about the block's centre
    if env["text"] > 0.0:
        px = p.font_px * ss
        tracking = p.tracking_px * ss
        font = load_font(c, px)
        blk = measure_block(c, p.lines, px, tracking)
        bw, bh = int(math.ceil(blk["w"])) + 4, int(math.ceil(blk["h"])) + 4
        block = Image.new("L", (bw, bh), 0)
        d = ImageDraw.Draw(block)
        y = 2 - blk["top_off"]
        for ln in p.lines:
            x = 2.0
            for ch in ln:
                if ch != " ":
                    d.text((x, y), ch, font=font, fill=255)
                x += font.getlength(ch) + tracking
            y += blk["cap_h"] + blk["gap"]
        s_now = float(c["scale_from"]) + (1.0 - float(c["scale_from"])) * env["text"]
        if s_now < 1.0:
            block = block.resize((max(1, int(round(bw * s_now))), max(1, int(round(bh * s_now)))), Image.LANCZOS)
        if env["text"] < 1.0:
            block = block.point(lambda v: int(v * env["text"]))
        rise = float(c["rise_px"]) * sc * (1.0 - env["text"])
        cx = (p.text_box.x + p.text_box.w / 2.0 - rx) * ss
        cy = (p.text_box.y + p.text_box.h / 2.0 + rise - ry) * ss
        ink.paste(block, (int(round(cx - block.width / 2.0)), int(round(cy - block.height / 2.0))), block)

    # --- stroke: draws on; head eases in with overshoot; ONE nudge of the whole arrow
    if env["draw"] > 0.0 and p.arrow_start is not None:
        c_stroke = c
        if p.arrow_override:
            c_stroke = dict(c)
            c_stroke["arrow"] = {**c["arrow"], **p.arrow_override}
        pts = arrow_path(p.text_box, p.side, c_stroke, n=240)
        seg_len = [math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]) for i in range(len(pts) - 1)]
        total = sum(seg_len) or 1.0
        want = env["draw"] * total
        drawn: list[tuple[float, float]] = [pts[0]]
        acc = 0.0
        for i, L in enumerate(seg_len):
            if acc + L >= want:
                f = (want - acc) / L if L else 0.0
                drawn.append((pts[i][0] + (pts[i + 1][0] - pts[i][0]) * f, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * f))
                break
            drawn.append(pts[i + 1])
            acc += L
        # the final tangent (toward the button) drives the head and the nudge
        ex, ey = pts[-1]
        bx, by = pts[-6]
        tx, ty = ex - bx, ey - by
        tl_ = math.hypot(tx, ty) or 1.0
        tx, ty = tx / tl_, ty / tl_
        push = float(c["nudge_px"]) * sc * env["nudge"]
        off = (push * tx, push * ty)
        stroke = max(1.0, float(c["arrow"]["stroke_px"]) * sc) * ss
        arrow_layer = Image.new("L", (W, H), 0)
        da = ImageDraw.Draw(arrow_layer)
        path = [((x + off[0] - rx) * ss, (y + off[1] - ry) * ss) for x, y in drawn]
        _stroke(da, path, stroke)
        if env["head"] > 0.0:
            h = env["head"]                                   # ease-out-back: peaks ~1.1 then settles at 1
            over = float(c["head_overshoot_px"]) * sc * ss * max(0.0, h - 1.0) / 0.1
            tipx = (ex + off[0] - rx) * ss + tx * over
            tipy = (ey + off[1] - ry) * ss + ty * over
            hl = float(c["arrow"]["head_len_px"]) * sc * ss * min(1.0, 0.6 + 0.4 * h)
            ang = math.radians(float(c["arrow"]["head_angle_deg"]))
            head_layer = Image.new("L", (W, H), 0)
            dh = ImageDraw.Draw(head_layer)
            r = stroke / 2.0
            for s_ in (-1, 1):
                ca, sa = math.cos(s_ * ang), math.sin(s_ * ang)
                dx, dy = -tx * ca + ty * sa, -tx * sa - ty * ca   # back along the tangent, rotated
                ex_, ey_ = tipx + dx * hl, tipy + dy * hl
                dh.line([(tipx, tipy), (ex_, ey_)], fill=255, width=int(round(stroke)))
                dh.ellipse((ex_ - r, ey_ - r, ex_ + r, ey_ + r), fill=255)
            dh.ellipse((tipx - r, tipy - r, tipx + r, tipy + r), fill=255)
            a_head = min(1.0, h / 0.6)
            if a_head < 1.0:
                head_layer = head_layer.point(lambda v: int(v * a_head))
            arrow_layer = _lighten(arrow_layer, head_layer)
        ink = _lighten(ink, arrow_layer)

    # --- separation: ONE soft shadow under the ink
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    backing = dict(c.get("backing") or {})
    if env["text"] > 0 and float(backing.get("opacity", 0)) > 0:
        pad_x = float(backing.get("pad_x_px", 0)) * sc
        pad_y = float(backing.get("pad_y_px", 0)) * sc
        box = (
            int(round((p.text_box.x - pad_x - rx) * ss)),
            int(round((p.text_box.y - pad_y - ry) * ss)),
            int(round((p.text_box.x2 + pad_x - rx) * ss)),
            int(round((p.text_box.y2 + pad_y - ry) * ss)),
        )
        alpha = int(255 * float(backing["opacity"]) * env["text"])
        ImageDraw.Draw(layer).rounded_rectangle(
            box,
            radius=int(round(float(backing.get("radius_px", 0)) * sc * ss)),
            fill=(0, 0, 0, alpha),
        )
    sh = c["shadow"]
    if float(sh.get("opacity", 0)) > 0:
        shadow = ink.filter(ImageFilter.GaussianBlur(float(sh["blur_px"]) * sc * ss))
        shadow = shadow.point(lambda v: int(v * float(sh["opacity"])))
        shadow_rgba = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        shadow_rgba.putalpha(shadow)
        layer.alpha_composite(shadow_rgba, (0, int(round(float(sh["dy_px"]) * sc * ss))))
    ink_rgba = Image.new("RGBA", (W, H), _hex(str(c["color"])) + (0,))
    ink_rgba.putalpha(ink)
    layer.alpha_composite(ink_rgba)
    small = layer.resize((rw, rh), Image.LANCZOS)
    a = float(c["opacity"]) * env["alpha"]
    if a < 1.0:
        small.putalpha(small.getchannel("A").point(lambda v: int(v * a)))
    canvas.paste(small, (rx, ry))
    return canvas


def render_frames(p: CtaPlacement, cta_cfg: dict[str, Any] | None, out_dir: Path, fps: int) -> dict[str, Any]:
    """The PNG sequence for the CTA's visible span at the project fps."""
    c = cfg_with_defaults(cta_cfg)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("cta_*.png"):
        old.unlink()
    pad = 32
    rx = int(max(0, math.floor(p.box.x - pad)))
    ry = int(max(0, math.floor(p.box.y - pad - float(c["rise_px"]) * float(c["scale"]))))
    rx2 = int(min(CANVAS_W, math.ceil(p.box.x2 + pad)))
    ry2 = int(min(CANVAS_H, math.ceil(p.box.y2 + pad)))
    region = (rx, ry, rx2 - rx, ry2 - ry)
    n = int(math.ceil((p.end_s - p.start_s) * fps)) + 1
    for k in range(n):
        t = p.start_s + k / float(fps)
        render_frame(t, p, c, region).save(out_dir / f"cta_{k:04d}.png", compress_level=3)
    return {"pattern": str((out_dir / "cta_%04d.png").resolve()).replace("\\", "/"), "frames": n,
            "region": list(region), "fps": fps, "supersample": 3}


# ---------------------------------------------------------------- sound


SR = 48000


def _bandpass_noise(n: int, lo_hz: float, hi_hz: float, seed: int):
    import numpy as np
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(n)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1.0 / SR)
    lo_edge, hi_edge = lo_hz / 2 ** 0.5, hi_hz * 2 ** 0.5
    gain = np.ones_like(f)
    gain[f < lo_edge] = 0.0
    gain[f > hi_edge] = 0.0
    m = (f >= lo_edge) & (f < lo_hz)
    gain[m] = 0.5 - 0.5 * np.cos(np.pi * (f[m] - lo_edge) / max(1e-6, lo_hz - lo_edge))
    m = (f > hi_hz) & (f <= hi_edge)
    gain[m] = 0.5 + 0.5 * np.cos(np.pi * (f[m] - hi_hz) / max(1e-6, hi_edge - hi_hz))
    return np.fft.irfft(X * gain, n)


def _place(y, seg, at_s: float) -> None:
    i0 = max(0, int(at_s * SR))
    seg = seg[: max(0, len(y) - i0)]
    y[i0:i0 + len(seg)] += seg


def synth_sfx(p: CtaPlacement, cta_cfg: dict[str, Any] | None, out_wav: Path) -> dict[str, Any]:
    """Three quiet cues on the CTA's own timeline (from start_s):
    ui    — a soft two-partial sine tone (660 + 990 Hz, 8 ms attack, ~90 ms) as the text lands
    swish — light airy noise, 1.4-3.6 kHz thinning to 0.9-2 kHz, shaped to the draw
    tick  — a 25 ms damped tick as the head settles
    Peak -6 dBFS; the mix gain is set later against the measured dialogue."""
    import numpy as np
    c = cfg_with_defaults(cta_cfg)
    snd = c["sound"]
    tl = p.timeline
    length = (tl["nudge_end"] - p.start_s) + 0.4
    n = int(length * SR)
    y = np.zeros(n)
    events: dict[str, float] = {}
    if snd.get("ui", True):
        m = int(0.11 * SR)
        t = np.arange(m) / SR
        tone = 0.6 * np.sin(2 * np.pi * 660.0 * t) + 0.4 * np.sin(2 * np.pi * 990.0 * t + 0.4)
        att = 0.008
        env = np.where(t < att, t / att, np.exp(-(t - att) / 0.03))
        tone = tone * env
        tone = np.convolve(tone, np.ones(7) / 7.0, mode="same")           # softens the top
        tone /= (np.abs(tone).max() or 1.0)
        at = tl["text_in"] - p.start_s + 0.04
        _place(y, tone * 0.32, at)
        events["ui_s"] = round(p.start_s + at, 3)
    if snd.get("swish", True):
        dur = float(c["draw_s"]) + 0.10
        m = int(dur * SR)
        t = np.arange(m) / SR
        k = np.clip(t / dur, 0, 1)
        bright = _bandpass_noise(m, 1400.0, 3600.0, 7)
        dark = _bandpass_noise(m, 900.0, 2000.0, 11)
        body = bright * (1 - k) ** 1.4 + dark * (0.3 + 0.7 * k)
        env = np.sin(np.pi * k) ** 1.6                                     # rises, peaks mid-draw, dies out
        w = body * env
        w /= (np.abs(w).max() or 1.0)
        at = tl["arrow_draw_start"] - p.start_s - 0.03
        _place(y, w * 0.55, at)
        events["swish_s"] = round(p.start_s + at, 3)
    if snd.get("tick", True):
        m = int(0.03 * SR)
        t = np.arange(m) / SR
        tick = (np.sin(2 * np.pi * 2100.0 * t) * np.exp(-t / 0.0025) * 0.8
                + np.sin(2 * np.pi * 720.0 * t) * np.exp(-t / 0.005) * 0.5)
        tick = np.convolve(tick, np.ones(5) / 5.0, mode="same")
        tick /= (np.abs(tick).max() or 1.0)
        at = tl["arrow_drawn"] - p.start_s + 0.02                          # as the head lands on the tip
        _place(y, tick * 0.45, at)
        events["tick_s"] = round(p.start_s + at, 3)
    peak = float(np.abs(y).max() or 1.0)
    y = y / peak * (10 ** (-6.0 / 20.0))
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(y, -1, 1) * 32767.0).astype("<i2")
    with wave.open(str(out_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())
    return {"file": str(out_wav), "duration_s": round(n / SR, 3), "peak_dbfs": -6.0, **events}


_LUFS_RE = re.compile(r"I:\s*(-?[\d.]+)\s*LUFS")


def measure_lufs_filter(inputs: list[str], filter_complex: str, out_label: str) -> float | None:
    p = subprocess.run(["ffmpeg", "-nostats", "-hide_banner", *inputs, "-filter_complex",
                        f"{filter_complex};[{out_label}]ebur128=peak=none[eb]", "-map", "[eb]", "-f", "null", "-"],
                       capture_output=True, text=True, errors="replace")
    m = _LUFS_RE.findall(p.stderr or "")
    return float(m[-1]) if m else None


def measure_dialogue_lufs(source: Path, offset_s: float, segments: Sequence[Any]) -> float | None:
    """Integrated loudness of the kept dialogue — the render's own trims, audio only."""
    parts = []
    for i, seg in enumerate(segments):
        a, b = (seg.start_s, seg.end_s) if hasattr(seg, "start_s") else (float(seg[0]), float(seg[1]))
        a, b = max(0.0, a - offset_s), max(0.0, b - offset_s)
        parts.append(f"[0:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS[a{i}]")
    graph = ";".join(parts) + ";" + "".join(f"[a{i}]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=0:a=1[dlg]"
    return measure_lufs_filter(["-vn", "-i", str(source)], graph, "dlg")


def measure_file_lufs(path: Path) -> float | None:
    return measure_lufs_filter(["-i", str(path)], "[0:a]anull[a]", "a")


def build_assets(p: CtaPlacement, cta_cfg: dict[str, Any] | None, out_dir: Path, fps: int,
                 source: Path | None = None, offset_s: float = 0.0, segments: Sequence[Any] | None = None) -> dict[str, Any]:
    """Frames + sound for one placement, into out_dir; the record render_short's `cta=` takes."""
    c = cfg_with_defaults(cta_cfg)
    rec: dict[str, Any] = {"placement": p.as_dict(), "config": c}
    rec["frames"] = render_frames(p, c, out_dir, fps)
    rec["start_s"], rec["end_s"] = p.start_s, p.end_s
    snd = c["sound"]
    if snd.get("enabled", True) and (snd.get("ui", True) or snd.get("swish", True) or snd.get("tick", True)):
        wav = out_dir / "cta_sfx.wav"
        sfx = synth_sfx(p, c, wav)
        sfx_lufs = measure_file_lufs(wav)
        dlg_lufs = measure_dialogue_lufs(source, offset_s, segments) if (source is not None and segments) else None
        rel = float(snd.get("relative_db", -20.0))
        if sfx_lufs is not None and dlg_lufs is not None:
            gain = (dlg_lufs + rel) - sfx_lufs
        else:
            gain = -22.0 + rel + 18.0        # unmeasured fallback: court dialogue raw ~ -20 LUFS
        gain = max(-60.0, min(0.0, gain))
        sfx.update({"lufs": sfx_lufs, "dialogue_lufs": dlg_lufs, "relative_db": rel, "gain_db": round(gain, 2)})
        rec["sound"] = sfx
    else:
        rec["sound"] = None
    (out_dir / "cta.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    return rec


# ---------------------------------------------------------------- ffmpeg


def ffmpeg_chain(rec: dict[str, Any], next_input_index: int, v_in: str, v_out: str,
                 a_in: str, a_out: str) -> tuple[list[str], str, str | None]:
    """(extra inputs, video filter, audio filter or None): the sequence
    overlaid at its start in 4:4:4 so text edges are not chroma-subsampled
    before the final yuv420p; the level-matched SFX mixed under the dialogue."""
    fr = rec["frames"]
    start, end = float(rec["start_s"]), float(rec["end_s"])
    inputs = ["-framerate", str(fr["fps"]), "-start_number", "0", "-i", fr["pattern"]]
    idx = next_input_index
    vf = (f"[{idx}:v]format=rgba,setpts=PTS+{start:.4f}/TB[ctaov];"
          f"[{v_in}][ctaov]overlay=0:0:format=yuv444:eof_action=pass:"
          f"enable='between(t,{start - 0.001:.3f},{end + 0.05:.3f})'[{v_out}]")
    af = None
    snd = rec.get("sound")
    if snd:
        inputs += ["-i", str(snd["file"])]
        ms = int(round(start * 1000))
        af = (f"[{idx + 1}:a]adelay={ms}:all=1,volume={float(snd['gain_db']):.2f}dB[ctasfx];"
              f"[{a_in}][ctasfx]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[{a_out}]")
    return inputs, vf, af


def review_frame_times(p: CtaPlacement) -> list[tuple[str, float]]:
    """The frames the quality check asks for."""
    tl = p.timeline
    return [("before_cta", max(0.0, p.start_s - 0.25)),
            ("cta_enter", p.start_s + (tl["text_settled"] - p.start_s) * 0.55),
            ("cta_arrow_mid_draw", (tl["arrow_draw_start"] + tl["arrow_drawn"]) / 2.0),
            ("cta_hold", min(p.end_s - 0.05, tl["nudge_end"] + 0.5))]
