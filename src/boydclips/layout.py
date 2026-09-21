# -*- coding: utf-8 -*-
"""The short's fixed courtroom layout and the ONE overlay-layout calculation.

Nathan, 2026-09-06 (third pass on the Flores render):

    * a stable 50/50 split — defendant top, Judge Boyd bottom (or whatever
      the case's tile map says, fixed for the whole Short); divider at
      y = 960 and it never moves, not for focus, not for punch-ins;
    * each person deliberately CENTRED in their 1080×960 slot from a
      subject anchor (a face, measured), not from the geometric centre of
      the source tile; natural headroom; no cropped head, chin or shoulders;
    * a punch-in is a zoom of about 1.06–1.12 INSIDE the fixed tile around
      that anchor — the divider stays put, the other tile stays put;
    * captions live ON the divider: centre (540, 960), straddling it a
      little, never moving with focus or punch-ins;
    * one authoritative overlay layout — caption block, watermark, anything
      later — with known bounding boxes and a collision check before the
      render; NO end card.

Everything here is geometry from measured inputs. It runs no detector; the
pipeline passes the anchors in.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Sequence

CANVAS_W = 1080
CANVAS_H = 1920
DIVIDER_Y = CANVAS_H // 2          # 960
SLOT_H = CANVAS_H // 2             # 960
SLOT_ASPECT = CANVAS_W / SLOT_H    # 1.125

DEFAULTS: dict[str, Any] = {
    "target_x_frac": 0.5,          # subject centre lands at 540
    "target_y_frac": 0.42,         # subject (face) centre sits a little above the slot's middle: natural headroom
    "center_max_zoom": 1.15,       # conservative: a slightly off-centre sharp face beats a centred 4x upscale
    "center_tolerance_px": 40,     # residual offset accepted once the zoom cap is reached
    "headroom_frac": 0.35,         # of the face height, kept above the face box
    "chinroom_frac": 0.9,          # of the face height, kept below the face box (chin + shoulders)
    "punch_zoom": 1.08,            # inside the 1.06–1.12 band he named
    "caption_rail_y": DIVIDER_Y,
    "caption_side_margin": 60,
    "caption_line_height_frac": 1.12,   # line height as a fraction of the font size (Anton at 120 measured ~1.1)
    "caption_pad": 12,
    "watermark_margin_frac": 0.035,
}


def _cfg(cfg: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(DEFAULTS)
    for k, v in (cfg or {}).items():
        if k in out and v is not None:
            out[k] = v
    return out


# ---------------------------------------------------------------- boxes


@dataclass
class Box:
    x: float
    y: float
    w: float
    h: float
    name: str = ""
    critical: bool = True

    @property
    def x2(self) -> float:
        return self.x + self.w

    @property
    def y2(self) -> float:
        return self.y + self.h

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.w / 2.0, self.y + self.h / 2.0)

    def intersects(self, o: "Box") -> bool:
        return not (self.x2 <= o.x or o.x2 <= self.x or self.y2 <= o.y or o.y2 <= self.y)

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "x": round(self.x, 1), "y": round(self.y, 1), "w": round(self.w, 1),
                "h": round(self.h, 1), "critical": self.critical}


def parse_crop(crop: str) -> tuple[int, int, int, int]:
    m = re.fullmatch(r"crop=(\d+):(\d+):(\d+):(\d+)", crop.strip())
    if not m:
        raise ValueError(f"not a crop expression: {crop!r}")
    w, h, x, y = (int(v) for v in m.groups())
    return w, h, x, y


# ---------------------------------------------------------------- subject-centred windows


@dataclass
class Anchor:
    """Where the subject sits inside its source tile, as fractions of the
    tile, plus the face box (fractions) when a detector measured it."""
    fx: float
    fy: float
    face_w: float | None = None
    face_h: float | None = None
    source: str = "geometric fallback"
    samples: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {"fx": round(self.fx, 4), "fy": round(self.fy, 4),
                "face_w": None if self.face_w is None else round(self.face_w, 4),
                "face_h": None if self.face_h is None else round(self.face_h, 4),
                "source": self.source, "samples": self.samples}


@dataclass
class Window:
    """A crop window inside a source tile that fills one 1080×960 slot."""
    crop: str                    # ffmpeg crop=w:h:x:y in SOURCE coordinates
    zoom: float                  # relative to the largest slot-shaped window the tile allows
    subject_x: float             # the anchor's X in the slot (0..1080) after the transform
    subject_y: float             # the anchor's Y in the slot (0..960)
    residual_x: float            # subject_x - 540
    notes: list[str] = field(default_factory=list)

    @property
    def upscale(self) -> float:
        """Source-to-slot magnification: slot width / window width."""
        w = parse_crop(self.crop)[0]
        return CANVAS_W / float(max(1, w))

    def as_dict(self) -> dict[str, Any]:
        return {"crop": self.crop, "zoom": round(self.zoom, 4), "subject_x": round(self.subject_x, 1),
                "subject_y": round(self.subject_y, 1), "residual_x": round(self.residual_x, 1),
                "upscale": round(self.upscale, 2), "notes": self.notes}


def _window_at(tile: str, anchor: Anchor, zoom: float, cfg: dict[str, Any]) -> Window:
    tw, th, tx, ty = parse_crop(tile)
    # the largest slot-shaped window the tile allows, then zoomed in
    if tw / th > SLOT_ASPECT:
        base_h, base_w = th, SLOT_ASPECT * th
    else:
        base_w, base_h = tw, tw / SLOT_ASPECT
    win_w = int(base_w / zoom)
    win_h = int(base_h / zoom)
    win_w -= win_w % 2
    win_h -= win_h % 2
    ax, ay = anchor.fx * tw, anchor.fy * th
    x = ax - float(cfg["target_x_frac"]) * win_w
    y = ay - float(cfg["target_y_frac"]) * win_h
    notes: list[str] = []
    # keep the head and the chin inside when the face box is known
    if anchor.face_h:
        fh = anchor.face_h * th
        top_needed = ay - fh / 2.0 - float(cfg["headroom_frac"]) * fh
        bottom_needed = ay + fh / 2.0 + float(cfg["chinroom_frac"]) * fh
        if y > top_needed:
            y = top_needed
            notes.append("headroom")
        if y + win_h < bottom_needed:
            y = bottom_needed - win_h
            notes.append("chin/shoulders")
    x = max(0.0, min(x, tw - win_w))
    y = max(0.0, min(y, th - win_h))
    x_i, y_i = int(round(x)), int(round(y))
    subject_x = (ax - x_i) / win_w * CANVAS_W
    subject_y = (ay - y_i) / win_h * SLOT_H
    return Window(f"crop={win_w}:{win_h}:{tx + x_i}:{ty + y_i}", zoom, subject_x, subject_y,
                  subject_x - CANVAS_W / 2.0, notes)


def center_window(tile: str, anchor: Anchor, cfg: dict[str, Any] | None = None, extra_zoom: float = 1.0) -> Window:
    """The base (or punched, with extra_zoom) window that centres the
    subject in the slot. The window may only crop IN — never pad — so a
    subject near a tile edge needs a narrower window to sit at 540: the
    smallest zoom that centres it is chosen, capped at center_max_zoom (past
    that the residual is accepted and recorded). Deterministic."""
    c = _cfg(cfg)
    tw, th, _tx, _ty = parse_crop(tile)
    if tw / th > SLOT_ASPECT:
        base_w = SLOT_ASPECT * th
    else:
        base_w = float(tw)
    ax = anchor.fx * tw
    room = max(1.0, min(ax, tw - ax))                    # how far the subject is from the nearer edge
    need = base_w / (2.0 * room)                          # zoom that lets the window centre on it
    zoom = max(1.0, min(float(c["center_max_zoom"]), need))
    # try the exact zoom, then widen a little if the head/chin rule pushed the window off-centre vertically
    win = _window_at(tile, anchor, zoom * extra_zoom, c)
    if abs(win.residual_x) > float(c["center_tolerance_px"]) and zoom < float(c["center_max_zoom"]):
        win = _window_at(tile, anchor, float(c["center_max_zoom"]) * extra_zoom, c)
    if abs(win.residual_x) > float(c["center_tolerance_px"]):
        win.notes.append(f"residual {win.residual_x:+.0f}px at zoom cap {c['center_max_zoom']}")
    return win


def punch_window(tile: str, anchor: Anchor, base: Window, punch: float, cfg: dict[str, Any] | None = None) -> Window:
    """The punched window: the base window zoomed by `punch` ABOUT THE
    SUBJECT WHERE IT ALREADY SITS. The subject keeps its slot position
    (whatever residual the base window has), so a punch-in reads as a zoom
    on the person and never as a sideways jump — measured: re-centring at
    the punch moved a capped subject 36 px."""
    c = dict(_cfg(cfg))
    c["target_x_frac"] = base.subject_x / CANVAS_W
    c["target_y_frac"] = base.subject_y / SLOT_H
    win = _window_at(tile, anchor, base.zoom * punch, c)
    win.notes = [n for n in win.notes if n not in ("headroom", "chin/shoulders")] + [f"punch {punch:.2f} about the subject"]
    return win


# ---------------------------------------------------------------- overlays


def caption_box(style: dict[str, Any], cfg: dict[str, Any] | None = None) -> Box:
    """The caption rail block: centred at (540, rail_y), two lines tall at
    the configured font size, straddling the divider."""
    c = _cfg(cfg)
    font = int(style.get("font_size", 120))
    lines = int(style.get("max_lines", 2))
    line_h = font * float(c["caption_line_height_frac"])
    h = lines * line_h + 2 * int(c["caption_pad"])
    w = CANVAS_W - 2 * int(c["caption_side_margin"])
    rail = float(style.get("rail_y", c["caption_rail_y"]))
    return Box(CANVAS_W / 2.0 - w / 2.0, rail - h / 2.0, w, h, "caption", True)


def watermark_box(sh_cfg: dict[str, Any], wm_w: float | None = None, wm_h: float | None = None) -> Box:
    """The watermark's reserved location: top-right, the same margin and
    11 % width render_short uses; height from the image aspect when known."""
    frac = float(sh_cfg.get("watermark_margin_frac", DEFAULTS["watermark_margin_frac"]))
    margin = int(round(CANVAS_W * frac))
    w = float(wm_w) if wm_w else round(CANVAS_W * 0.11)
    h = float(wm_h) if wm_h else w * 0.6
    return Box(CANVAS_W - margin - w, margin, w, h, "watermark", True)


def overlay_layout(style: dict[str, Any], sh_cfg: dict[str, Any], wm_size: tuple[float, float] | None = None,
                   extra: Sequence[Box] | None = None, cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Every overlay's bounding box and whether any two critical ones
    intersect. Nothing is drawn that is not in here; nothing here may
    collide. `overlay_collision` is the QC verdict."""
    boxes = [caption_box(style, cfg), watermark_box(sh_cfg, *(wm_size or (None, None)))]
    boxes += list(extra or [])
    collisions = []
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            if a.critical and b.critical and a.intersects(b):
                collisions.append((a.name, b.name))
    safe_top, safe_bottom = 288, 1248
    cap = boxes[0]
    inside_safe = cap.y >= safe_top and cap.y2 <= safe_bottom
    return {
        "boxes": [b.as_dict() for b in boxes],
        "collisions": collisions,
        "caption_center": [round(cap.center[0], 1), round(cap.center[1], 1)],
        "caption_in_safe_band": inside_safe,
        "ok": not collisions and inside_safe,
        "overlay_collision": "PASS" if not collisions else "FAIL",
        "end_card": "none",
    }


# ---------------------------------------------------------------- the composition


@dataclass
class SegmentLayout:
    index: int
    top: Window
    bottom: Window
    punch: str                     # "top" | "bottom" | ""
    punch_scale: float

    def as_dict(self) -> dict[str, Any]:
        return {"index": self.index, "divider_y": DIVIDER_Y, "top": self.top.as_dict(),
                "bottom": self.bottom.as_dict(), "punch": self.punch, "punch_scale": round(self.punch_scale, 3)}


def compose(segment_focus: Sequence[str], segment_punch: Sequence[bool], tiles: tuple[str, str],
            tile_map: dict[str, Any], anchors: dict[str, Anchor], sh_cfg: dict[str, Any]) -> dict[str, Any]:
    """Per-segment windows for a fixed 50/50 stack. The base windows are the
    same for every segment; a punched segment zooms the SPEAKER's tile by
    punch_zoom around its anchor and leaves the other tile and the divider
    exactly where they were."""
    c = _cfg(sh_cfg)
    top_tile, bottom_tile = tiles[0], tiles[1]
    top_anchor = anchors.get("top") or Anchor(0.5, float(c["target_y_frac"]))
    bottom_anchor = anchors.get("bottom") or Anchor(0.5, float(c["target_y_frac"]))
    base_top = center_window(top_tile, top_anchor, c)
    base_bottom = center_window(bottom_tile, bottom_anchor, c)
    pz = float(c["punch_zoom"])
    punched_top = punch_window(top_tile, top_anchor, base_top, pz, c)
    punched_bottom = punch_window(bottom_tile, bottom_anchor, base_bottom, pz, c)
    segs: list[SegmentLayout] = []
    for i, (focus, punch) in enumerate(zip(segment_focus, segment_punch)):
        tile = tile_map.get(focus) if focus in ("boyd", "defendant") else None
        if punch and tile == "top":
            segs.append(SegmentLayout(i, punched_top, base_bottom, "top", pz))
        elif punch and tile == "bottom":
            segs.append(SegmentLayout(i, base_top, punched_bottom, "bottom", pz))
        else:
            segs.append(SegmentLayout(i, base_top, base_bottom, "", 1.0))
    return {
        "divider_y": DIVIDER_Y,
        "slot": [CANVAS_W, SLOT_H],
        "tile_map": dict(tile_map),
        "anchors": {"top": top_anchor.as_dict(), "bottom": bottom_anchor.as_dict()},
        "base": {"top": base_top.as_dict(), "bottom": base_bottom.as_dict()},
        "punch_zoom": pz,
        "segments": [s.as_dict() for s in segs],
        "_segments": segs,
    }


def composition_checks(comp: dict[str, Any], overlay: dict[str, Any], tolerance_px: int = 60) -> list[dict[str, Any]]:
    """Deterministic checks over the composition table: caption centre on
    the rail, subjects near the horizontal centre of their slots, the
    divider identical on every segment, no overlay collision."""
    out: list[dict[str, Any]] = []
    cx, cy = overlay["caption_center"]
    out.append({"check": "caption_center_x", "ok": abs(cx - CANVAS_W / 2.0) <= 2, "value": cx, "want": CANVAS_W / 2.0})
    out.append({"check": "caption_center_y", "ok": abs(cy - comp["divider_y"]) <= 20, "value": cy, "want": comp["divider_y"]})
    for slot in ("top", "bottom"):
        sx = comp["base"][slot]["subject_x"]
        at_cap = any("zoom cap" in n for n in comp["base"][slot].get("notes", []))
        # centred within tolerance, OR as centred as the quality cap allows
        # (the residual is reported either way — composition over geometry)
        out.append({"check": f"{slot}_subject_centered", "ok": abs(sx - CANVAS_W / 2.0) <= tolerance_px or at_cap,
                    "value": sx, "want": CANVAS_W / 2.0, "residual": comp["base"][slot]["residual_x"],
                    "at_zoom_cap": at_cap, "upscale": comp["base"][slot].get("upscale")})
        sy = comp["base"][slot]["subject_y"]
        # Floor 0.12, not 0.2: a defendant standing at the lectern has his face
        # centre at ~13 % of the source tile (Garcia, 2026-09-06, fy 0.128 ->
        # 123 px of the 960 slot) and the slot is already the tile's full
        # height, so no zoom the taste cap allows can lower it. 12 % keeps the
        # whole face inside the slot and its top clear of the caption box
        # (66 px into the bottom slot).
        #
        # The ceiling used to be a flat 0.65 * SLOT_H on the face CENTRE, which
        # ignores how big the face is. Measured 2026-09-13 on IDGfe1rPUQo:6130:
        # the judge's webcam close-up (face_h 0.392 of the tile) centres at
        # 626.9 px (65.3 %) with the head top at 438.7 px and the chin at
        # 815.1 px — a correctly framed close-up refused by 3 px, and refused
        # for every legal window, because the slot is the tile's full height
        # (subject_y == fy * SLOT_H at any zoom). The bounds that matter are
        # where the head and the chin land, so they are what is checked when
        # the face box was measured. With no measurement the old centre band
        # still applies.
        fh = ((comp.get("anchors") or {}).get(slot) or {}).get("face_h")
        if fh:
            fh_px = float(fh) * SLOT_H
            out.append({"check": f"{slot}_subject_headroom",
                        "ok": (0.12 * SLOT_H <= sy
                               and sy - 0.5 * fh_px <= 0.62 * SLOT_H
                               and sy + 0.5 * fh_px <= 0.94 * SLOT_H),
                        "value": round(sy, 1), "face_h_px": round(fh_px, 1),
                        "head_top": round(sy - 0.5 * fh_px, 1), "chin": round(sy + 0.5 * fh_px, 1)})
        else:
            out.append({"check": f"{slot}_subject_headroom", "ok": 0.12 * SLOT_H <= sy <= 0.65 * SLOT_H,
                        "value": round(sy, 1), "face_h_px": None})
    divs = {s["divider_y"] for s in comp["segments"]}
    out.append({"check": "divider_fixed", "ok": divs == {DIVIDER_Y} or not divs, "value": sorted(divs)})
    scales = sorted({s["punch_scale"] for s in comp["segments"]})
    out.append({"check": "punch_scale_band", "ok": all(s == 1.0 or 1.04 <= s <= 1.15 for s in scales), "value": scales})
    # A punch-in is one zoom that stays on through a beat; the interior cuts
    # the planner makes inside that beat split it into several SEGMENTS but
    # not into several punch-ins. Counting segments refused Robinson's short
    # (2026-09-06: two punched beats, four punched segments). Count runs.
    flags = [bool(s["punch"]) for s in comp["segments"]]
    punches = sum(1 for k, p in enumerate(flags) if p and (k == 0 or not flags[k - 1]))
    # Count for evidence only. Editorial beat selection and spacing happen in
    # shorts_editor; layout validates geometry without reintroducing a hidden
    # global ceiling.
    out.append({"check": "punch_count", "ok": True, "value": punches, "segments_punched": sum(flags),
                "policy": "editorial_spacing"})
    out.append({"check": "overlay_collision", "ok": overlay["overlay_collision"] == "PASS", "value": overlay["collisions"]})
    out.append({"check": "end_card", "ok": overlay.get("end_card") == "none", "value": overlay.get("end_card")})
    return out
