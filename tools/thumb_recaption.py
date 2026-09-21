# -*- coding: utf-8 -*-
"""Re-caption a finished direct_gen thumbnail WITHOUT regenerating the image.

    python tools/thumb_recaption.py REVIEW_DIR "WHO {TASED}|YOU?" [--family A] [--apply]
    python tools/thumb_recaption.py REVIEW_DIR --family B \
        --block "Y'ALL LET|ME {OUT.}@40,470,560>defendant" \
        --block "SO IT'S|OUR {FAULT?}@700,470,520>boyd" --apply

The direct_gen finals are flat JPEGs with the type baked in. Nathan
(2026-09-07): fix the captions, keep the images. So: find the old type
(loose ink mask - the generated type can be textured grey, not white),
inpaint it out of the plate (two passes: background fills from background,
ink that sat on the subject fills from the subject; the BiRefNet subject
alpha keeps the shoulder intact), typeset the new line(s) with the house
Anton preset (tools/thumb_type, title element), then run the same
deterministic gates direct_gen runs (thumb_direct.qc_concept) plus
`old_type_removed` and `no_old_type_residue`, and R60's caption check.

Two-speaker exchange (R61, 2026-09-07): `--block "TEXT@x,y,maxw>who"` once
per speaker. Each block sits on its speaker's side and carries a short
speech tail up to that person's chin, so the line is attributed by position
AND by the tail. `who` is `defendant` / `boyd` (YuNet face + SFace match) or
`mx,my`. Reading order left -> right is the order the lines were said.

Caption syntax: '|' breaks the line, '{word}' is the yellow run (the old
'*word*' still works; write a backslash before an asterisk for a literal one).

Without --apply the result is written next to the original as
<name>_recaption.jpg; with --apply the original is copied to
superseded_captions/ and the recaption takes its exact path, and the sidecar
and the manifest record the change. --source recaptions from a given file
(a superseded_captions backup) instead of the current final.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))

import thumb_direct as TD   # noqa: E402
import thumb_type as TT     # noqa: E402
import check_caption as CC  # noqa: E402

WHITE = (255, 255, 255)
YELLOW = (253, 224, 0)
W, H = 1280, 720
RESIDUE_MAX = 150
LITERAL_STAR = "\x00STAR\x00"


# ---------------------------------------------------------------- caption text


def parse_caption(s: str) -> list[list[tuple[str, tuple, bool]]]:
    s = s.replace("\\*", LITERAL_STAR)
    lines = []
    for raw in s.split("|"):
        runs = []
        for part in re.split(r"(\{[^}]+\}|\*[^*]+\*)", raw.strip()):
            if not part:
                continue
            if (part.startswith("{") and part.endswith("}")) or (part.startswith("*") and part.endswith("*") and len(part) > 2):
                runs.append((part[1:-1].replace(LITERAL_STAR, "*"), YELLOW, False))
            else:
                runs.append((part.replace(LITERAL_STAR, "*"), WHITE, False))
        lines.append(runs)
    return lines


def plain_text(lines) -> str:
    return " ".join("".join(r[0] for r in runs).strip() for runs in lines)


def parse_block(spec: str) -> dict:
    """'TEXT@x,y,maxw[>who]' -> dict. who = defendant | boyd | 'mx,my'."""
    m = re.match(r"^(.*)@(\d+),(\d+),(\d+)(?:>(.+))?$", spec.strip())
    if not m:
        raise SystemExit(f"bad --block {spec!r}: want 'TEXT@x,y,maxw[>defendant|boyd|mx,my]'")
    text, x, y, w, who = m.groups()
    return {"lines": parse_caption(text), "x": int(x), "y": int(y), "max_w": int(w), "tail": who}


# ---------------------------------------------------------------- old type off


def loose_ink_mask(bgr):
    """thumb_direct.ink_mask keys on near-white ink; the generated type is
    sometimes a textured light grey (Rodriguez: 'YEAH, I RELAPSED.' at
    L~190). Same dark-ring test, looser fill: light and unsaturated, or the
    yellow accent."""
    h, w = bgr.shape[:2]
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    light = (hsv[:, :, 2] > 150) & (hsv[:, :, 1] < 70)
    b, g, r = bgr[:, :, 0].astype(int), bgr[:, :, 1].astype(int), bgr[:, :, 2].astype(int)
    yellow = (r > 180) & (g > 150) & (b < 120)
    bright = (light | yellow).astype(np.uint8)
    dark = (cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY) < 70).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(bright, 8)
    keep = np.zeros(n, dtype=bool)
    k = np.ones((5, 5), np.uint8)
    for i in range(1, n):
        a, ch, cw = stats[i, cv2.CC_STAT_AREA], stats[i, cv2.CC_STAT_HEIGHT], stats[i, cv2.CC_STAT_WIDTH]
        if a < 12 or ch > 0.40 * h or cw > 0.60 * w or ch < 12:
            continue
        x, y = stats[i, cv2.CC_STAT_LEFT], stats[i, cv2.CC_STAT_TOP]
        y0, y1, x0, x1 = max(0, y - 6), min(h, y + ch + 6), max(0, x - 6), min(w, x + cw + 6)
        comp = (lab[y0:y1, x0:x1] == i).astype(np.uint8)
        ring = cv2.dilate(comp, k) - comp
        if ring.sum() and (dark[y0:y1, x0:x1] & ring).sum() / ring.sum() >= 0.45:
            keep[i] = True
    return np.maximum(keep[lab].astype(np.uint8), TD.ink_mask(bgr))


def old_type_mask(bgr, grow: int = 22, wipe=None):
    m = loose_ink_mask(bgr)
    if wipe:
        x0, y0, x1, y1 = wipe
        m[y0:y1, x0:x1] = 1
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * grow + 1, 2 * grow + 1))
    return cv2.dilate(m, k)


def subject_alpha(bgr):
    """Person alpha over the whole frame (tools/matting, BiRefNet matting).
    The old type's outline sat against the defendant's shoulder on Garcia
    and Rodriguez; a mask grown 22 px ate the shoulder edge and the inpaint
    smeared it. The subject is never inpainted from the background."""
    try:
        import matting as M
        if M.available():
            a = M.alpha(bgr)
            return np.clip(np.asarray(a, dtype=np.float32), 0, 1)
    except Exception as exc:  # noqa: BLE001
        print(f"  (no subject alpha: {exc})")
    return np.zeros(bgr.shape[:2], np.float32)


def remove_type(bgr, mask, protect=None):
    """Inpaint, then soften inside the hole: the plates are blurred rooms,
    so a smoothed fill reads as the same plate; Telea's streaks do not.
    Two passes so neither side bleeds into the other: the background hole
    is filled from background only (the subject is masked out of the source
    inside a window around the type), the ink that sat ON the subject is
    filled from the subject only. Then blend by the subject alpha."""
    m = (mask > 0).astype(np.uint8)
    if protect is None:
        out = cv2.inpaint(bgr, m * 255, 9, cv2.INPAINT_TELEA)
        soft = cv2.GaussianBlur(out, (0, 0), 6)
        a = cv2.GaussianBlur(m.astype(np.float32), (0, 0), 4)[..., None]
        return np.clip(out * (1 - a) + soft * a, 0, 255).astype(np.uint8)
    near = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (121, 121)))
    subj = (protect > 0.15).astype(np.uint8)
    hole_bg = (m & (1 - subj)).astype(np.uint8)
    hole_sub = (m & subj).astype(np.uint8)
    src_bg = ((hole_bg | (subj & near)) > 0).astype(np.uint8) * 255
    fill_bg = cv2.inpaint(bgr, src_bg, 9, cv2.INPAINT_TELEA)
    soft = cv2.GaussianBlur(fill_bg, (0, 0), 6)
    a = cv2.GaussianBlur(hole_bg.astype(np.float32), (0, 0), 4)[..., None]
    fill_bg = fill_bg * (1 - a) + soft * a
    if hole_sub.sum():
        src_sub = ((hole_sub | ((1 - subj) & near)) > 0).astype(np.uint8) * 255
        fill_sub = cv2.inpaint(bgr, src_sub, 9, cv2.INPAINT_TELEA).astype(np.float32)
        # (2026-09-07: a row-mirror fill was tried here for cloth and pulled the
        # chin's skin tone down into the jumpsuit - worse than Telea. A wide
        # hole on cloth is COVERED by placing the new type over it: see the
        # Alonzo duo, defendant line sized onto the old line's footprint.)
    else:
        fill_sub = bgr.astype(np.float32)
    pa = np.clip(protect, 0, 1)[..., None]
    res = fill_bg * (1 - pa) + fill_sub * pa
    keep = (1 - cv2.dilate(m, np.ones((3, 3), np.uint8)))[..., None].astype(np.float32)
    res = res * (1 - keep) + bgr.astype(np.float32) * keep   # outside the hole nothing changes
    return np.clip(res, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------- new type on


def fit_size(lines, cap_px: int, max_w: int, style: str) -> int:
    spec = TT.resolve(style, "title")
    size = None
    for runs in lines:
        lay = TT.fit(spec, runs, cap_px, max_w, 400, x=0, y=0)
        size = lay.size if size is None else min(size, lay.size)
    return size


def typeset(lines, x: int, y_top: int, cap_px: int, size: int, style: str = "house"):
    """Draw the lines at a fixed glyph size, cap-top of the first line at y_top."""
    spec = TT.resolve(style, "title")
    rgba = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gap = int(round(cap_px * 0.28))
    y = y_top
    boxes = []
    for runs in lines:
        lay = TT.Layout(spec, runs, size, x, y)
        bb = lay.ink_bbox(0)
        lay = TT.Layout(spec, runs, size, x, y - (bb[1] - y))
        layer, _ink = TT.render_runs(lay, spec, W, H, cap_px)
        rgba.alpha_composite(layer)
        bb = lay.ink_bbox(spec["stroke"])
        boxes.append([int(v) for v in bb])
        y = int(bb[3]) + gap
    return rgba, boxes


def draw_tail(rgba: Image.Image, block_bbox, mouth, stroke: int = 7):
    """A short speech tail from the block's top edge up toward the speaker's
    chin. White, black outline, drawn UNDER the type so the text outline
    sits on top of its base."""
    x0, y0, x1, y1 = block_bbox
    mx, my = mouth
    if my > y0:                      # speaker is below the block: tail from the bottom edge instead
        base_y, apex_y = y1 - 4, min(my - 12, y1 + 120)
    else:
        base_y, apex_y = y0 + 4, max(my + 28, y0 - 130)
    bx = int(min(max(mx, x0 + 60), x1 - 60))
    half = 34
    pts = [(bx - half, base_y), (bx + half, base_y), (mx, apex_y)]
    d = ImageDraw.Draw(rgba)
    # outline: draw the polygon fattened by the stroke
    outline = Image.new("L", (W, H), 0)
    ImageDraw.Draw(outline).polygon(pts, fill=255)
    outline = outline.filter(__import__("PIL.ImageFilter", fromlist=["MaxFilter"]).MaxFilter(2 * stroke + 1))
    black = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    black.putalpha(outline)
    rgba.alpha_composite(black)
    d.polygon(pts, fill=(*WHITE, 255))
    return [min(pts[0][0], mx) - stroke, min(base_y, apex_y) - stroke, max(pts[1][0], mx) + stroke, max(base_y, apex_y) + stroke]



# ---------------------------------------------------------------- comic bubbles (R61)

BLACK = (18, 18, 18)
RED = (222, 28, 28)
BUBBLE_STROKE = 9
BUBBLE_PAD = (30, 24)
BUBBLE_RADIUS = 30


def _bubble_spec():
    return {"font": "Anton-Regular.ttf", "tracking": 0.0, "skew": 0.0, "stroke": 0, "shadow": None,
            "extrude": None, "gradient": None, "ink_stroke": 0, "emphasis": {}}


def _recolour(lines):
    out = []
    for runs in lines:
        out.append([(t, RED if fill == YELLOW else BLACK, e) for t, fill, e in runs])
    return out


def bubble_fit_size(lines, cap_px: int, max_w: int) -> int:
    spec = _bubble_spec()
    size = None
    for runs in _recolour(lines):
        lay = TT.fit(spec, runs, cap_px, max_w - 2 * BUBBLE_PAD[0], 400, x=0, y=0)
        size = lay.size if size is None else min(size, lay.size)
    return size


def render_bubble(lines, x: int, y: int, cap_px: int, size: int, mouth, side: str):
    """A comic speech bubble: white rounded panel, black stroke, black Anton
    type (key word red), and a WIDE tail whose apex ends at the speaker's
    chin. Nathan, 2026-09-07: "a proper speech-tail / comic-bubble style
    pointer aimed clearly at that speaker, not just a generic triangle
    floating above the text". Returns (RGBA layer, bbox incl. tail)."""
    from PIL import ImageFilter
    spec = _bubble_spec()
    px, py = BUBBLE_PAD
    gap = int(round(cap_px * 0.26))
    # lay the text first to know the panel
    text_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    yy = y + py
    boxes = []
    for runs in _recolour(lines):
        lay = TT.Layout(spec, runs, size, x + px, yy)
        bb = lay.ink_bbox(0)
        lay = TT.Layout(spec, runs, size, x + px, yy - (bb[1] - yy))
        layer, _ink = TT.render_runs(lay, spec, W, H, cap_px)
        text_layer.alpha_composite(layer)
        bb = lay.ink_bbox(0)
        boxes.append([int(v) for v in bb])
        yy = int(bb[3]) + gap
    tx0, ty0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    tx1, ty1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
    rx0, ry0, rx1, ry1 = tx0 - px, ty0 - py, tx1 + px, ty1 + py
    mx, my = mouth
    # tail: base on the edge facing the speaker, apex at the chin
    if my <= ry0:
        base_y, apex = ry0 + 6, (mx, my + 4)
        bx = int(min(max(mx, rx0 + 90), rx1 - 90))
        tail = [(bx - 46, base_y), (bx + 46, base_y), apex]
    else:
        base_y, apex = ry1 - 6, (mx, my - 4)
        bx = int(min(max(mx, rx0 + 90), rx1 - 90))
        tail = [(bx - 46, base_y), (bx + 46, base_y), apex]
    shape = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(shape)
    d.rounded_rectangle([rx0, ry0, rx1, ry1], radius=BUBBLE_RADIUS, fill=255)
    d.polygon(tail, fill=255)
    outline = shape.filter(ImageFilter.MaxFilter(2 * BUBBLE_STROKE + 1))
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    # soft drop shadow lifts the panel off the room
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sh.putalpha(outline.filter(ImageFilter.GaussianBlur(7)).point(lambda v: int(v * 0.55)))
    out.alpha_composite(sh, (6, 8))
    blk = Image.new("RGBA", (W, H), (*BLACK, 0)); blk.putalpha(outline); out.alpha_composite(blk)
    wht = Image.new("RGBA", (W, H), (*WHITE, 0)); wht.putalpha(shape); out.alpha_composite(wht)
    out.alpha_composite(text_layer)
    bbox = [min(rx0, mx) - BUBBLE_STROKE, min(ry0, apex[1]) - BUBBLE_STROKE, max(rx1, mx) + BUBBLE_STROKE + 8, max(ry1, apex[1]) + BUBBLE_STROKE + 10]
    return out, [int(v) for v in bbox], boxes, [int(rx0), int(ry0), int(rx1), int(ry1)]

# ---------------------------------------------------------------- case context


def case_context(review: Path, family: str):
    td = review / "thumb_direct"
    man = json.loads((td / "manifest.json").read_text(encoding="utf-8"))
    key = man["case"]
    jpg = td / f"{key}_{family}.jpg"
    side = td / f"{key}_{family}.json"
    vid, _start, span = re.match(r"^(.+)_(\d+)_(\d+-\d+)$", key).groups()
    lo, hi = (float(v) for v in span.split("-"))
    tpath = ROOT / "work" / vid / f"{vid}.transcript.json"
    words = json.loads(tpath.read_text(encoding="utf-8"))["words"]
    transcript = [w["w"] for w in words if lo - 1 <= float(w["t"]) <= hi + 1]
    wd = TD.THUMBWORK / key
    refs = {}
    # the same references direct_gen scored the concept against: the case
    # cutout for the defendant, the approved library Boyd for the judge
    for who, ps in (man.get("assets") or {}).items():
        if who in ("defendant", "boyd") and ps and Path(ps[0]).exists():
            refs[who] = Path(ps[0])
    for who, name in (("defendant", "defendant_extracted.png"), ("boyd", "boyd_extracted.png")):
        p = wd / name
        if who not in refs and p.exists():
            refs[who] = p
    return man, key, jpg, side, transcript, refs


FACE_BOXES: list = []


def mouth_points(bgr, refs, cfg) -> dict:
    fi = TD.faces_and_identity(bgr, refs, cfg)
    out = {}
    FACE_BOXES.clear()
    for f in fi.get("faces", []):
        x, y, w, h = f["box"]
        FACE_BOXES.append([int(x), int(y), int(x + w), int(y + h)])
        who = f.get("match")
        if who and who not in out:
            out[who] = (int(x + w / 2), int(y + 0.88 * h))
    return out


# ---------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("review")
    ap.add_argument("caption", nargs="?", help="'|' breaks lines, '{word}' is the yellow run")
    ap.add_argument("--bubble", action="store_true", help="R61: render each --block as a comic speech bubble with a tail to its speaker")
    ap.add_argument("--block", action="append", default=[], help="'TEXT@x,y,maxw[>defendant|boyd|mx,my]' - one per speaker (R61)")
    ap.add_argument("--family", default="A")
    ap.add_argument("--x", type=int, default=None, help="left edge of the type (default: old text left edge)")
    ap.add_argument("--y", type=int, default=None, help="cap top of the first line (default: old text top)")
    ap.add_argument("--cap", type=int, default=118, help="cap height px per line")
    ap.add_argument("--max-w", dest="max_w", type=int, default=None, help="max line width (default: old text width + 20)")
    ap.add_argument("--grow", type=int, default=22, help="dilation around the old ink for the inpaint mask")
    ap.add_argument("--style", default="house")
    ap.add_argument("--wipe", type=int, nargs=4, metavar=("X0", "Y0", "X1", "Y1"), help="also inpaint this rectangle (stubborn old type)")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--source", help="image to recaption instead of the current final (e.g. a superseded_captions backup)")
    ap.add_argument("--title", help="the video title, for the repeats-the-title flag (default: the review manifest packaging title)")
    args = ap.parse_args()
    if not args.caption and not args.block:
        ap.error("a caption or at least one --block is required")

    review = Path(args.review).resolve()
    man, key, jpg, side, transcript, refs = case_context(review, args.family)
    bgr = cv2.imread(str(Path(args.source).resolve() if args.source else jpg))
    assert bgr is not None and bgr.shape[:2] == (H, W), jpg
    cfg = dict(TD.DEFAULTS, **(man.get("config") or {}))
    old_geo = TD.text_geometry(bgr, cfg)
    ob = old_geo.get("bbox") or [60, 200, 640, 450]

    if args.block:
        blocks = [parse_block(b) for b in args.block]
    else:
        x = args.x if args.x is not None else max(40, ob[0])
        y = args.y if args.y is not None else ob[1]
        max_w = args.max_w if args.max_w is not None else max(360, ob[2] - x + 20)
        blocks = [{"lines": parse_caption(args.caption), "x": x, "y": y, "max_w": max_w, "tail": None}]
    texts = [plain_text(b["lines"]) for b in blocks]
    text = " ".join(texts)

    # R60: the caption check runs before a pixel moves
    title = args.title
    if not title:
        try:
            pk = json.loads((review / "manifest.json").read_text(encoding="utf-8")).get("packaging") or {}
            title = pk.get("title") or (pk.get("longform") or {}).get("title")
        except Exception:  # noqa: BLE001
            title = None
    forbid = (man.get("brief") or {}).get("forbidden_tokens", [])
    checks = []
    for t in texts:
        cc = CC.check(t, title, transcript, forbid)
        checks.append(cc)
        for x_ in cc["refusals"]:
            print(f"  REFUSE caption {t!r}: {x_}")
        for x_ in cc["flags"]:
            print(f"  flag   caption {t!r}: {x_}")
    if not all(c["ok"] for c in checks):
        print(f"CAPTION_REFUSED {text!r} (R60) - nothing rendered")
        return 3

    mask = old_type_mask(bgr, args.grow, args.wipe)
    protect = subject_alpha(bgr)
    # the old type itself is never subject, even where it sat on a shoulder: ink + outline + soft shadow
    protect[cv2.dilate(loose_ink_mask(bgr), np.ones((2 * args.grow + 1, 2 * args.grow + 1), np.uint8)) > 0] = 0
    plate = remove_type(bgr, mask, protect)
    plate_residue = int(loose_ink_mask(plate).sum())

    mouths = mouth_points(bgr, refs, cfg) if (args.bubble or any(b["tail"] for b in blocks)) else {}
    if args.bubble:
        size = min(bubble_fit_size(b["lines"], args.cap, b["max_w"]) for b in blocks)
    else:
        size = min(fit_size(b["lines"], args.cap, b["max_w"], args.style) for b in blocks)
    comp = Image.fromarray(cv2.cvtColor(plate, cv2.COLOR_BGR2RGB)).convert("RGBA")
    tails = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    type_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    boxes, tail_boxes, bubble_text_boxes, panels = [], [], [], []
    for b in blocks:
        if args.bubble:
            who = b["tail"] or ""
            if re.match(r"^\d+,\d+$", who):
                mouth = tuple(int(v) for v in who.split(","))
            elif who in mouths:
                mouth = mouths[who]
            else:
                raise SystemExit(f"--bubble needs a speaker for every block; no face matched {who!r} (have {sorted(mouths)})")
            layer, bb, lb, panel = render_bubble(b["lines"], b["x"], b["y"], args.cap, size, mouth, who)
            type_layer.alpha_composite(layer)
            boxes.append(bb)
            bubble_text_boxes += lb
            panels.append(panel)
            continue
        layer, bxs = typeset(b["lines"], b["x"], b["y"], args.cap, size, args.style)
        type_layer.alpha_composite(layer)
        boxes += bxs
        if b["tail"]:
            who = b["tail"]
            if re.match(r"^\d+,\d+$", who):
                mouth = tuple(int(v) for v in who.split(","))
            elif who in mouths:
                mouth = mouths[who]
            else:
                print(f"  no face matched {who!r} (have {sorted(mouths)}); tail skipped")
                continue
            bb = [min(v[0] for v in bxs), min(v[1] for v in bxs), max(v[2] for v in bxs), max(v[3] for v in bxs)]
            tail_boxes.append(draw_tail(tails, bb, mouth))
    comp.alpha_composite(tails)
    comp.alpha_composite(type_layer)
    out_png = jpg.with_name(jpg.stem + "_recaption.png")
    comp.convert("RGB").save(out_png, "PNG")

    brief = dict(man.get("brief") or {})
    out_jpg = jpg.with_name(jpg.stem + "_recaption.jpg")
    rep = TD.qc_concept(out_png, args.family, {"text": text}, brief, refs, transcript, cfg, out_jpg)
    if args.bubble:
        m = float(cfg["text_margin_frac"])
        inside = all(b[0] >= m * W and b[1] >= m * H and b[2] <= (1 - m) * W and b[3] <= (1 - m) * H for b in boxes)
        tallest = max(b[3] - b[1] for b in bubble_text_boxes) / H
        for g in rep["gates"]:
            if g["gate"] == "text_present":
                g["ok"], g["detail"] = True, f"{len(blocks)} speech bubble(s) (black type on white; ink_mask cannot see it)"
            elif g["gate"] == "text_inside_frame":
                g["ok"], g["detail"] = inside, f"bubble boxes {boxes} margin {m:.0%}"
            elif g["gate"] == "text_size":
                g["ok"], g["detail"] = tallest >= float(cfg["text_min_height_frac"]), f"tallest bubble line {tallest:.1%} of height (floor {cfg['text_min_height_frac']:.0%})"
            elif g["gate"] == "text_clear_of_faces":
                # the PANEL must stay off the faces; the tail is meant to touch the chin
                worst = 0.0
                for fx0, fy0, fx1, fy1 in FACE_BOXES:
                    fa = max(1, (fx1 - fx0) * (fy1 - fy0))
                    for px0, py0, px1, py1 in panels:
                        ix = max(0, min(fx1, px1) - max(fx0, px0)); iy = max(0, min(fy1, py1) - max(fy0, py0))
                        worst = max(worst, ix * iy / fa)
                g["ok"], g["detail"] = worst < 0.10, f"bubble panel overlaps a face by {worst:.0%} (tails excluded)"
        rep["text_geometry"] = {"found": True, "bbox": [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)], "bubbles": boxes, "lines": bubble_text_boxes}
    if True:
        # each speaker's line is grounded on its own (the joined text is not a phrase anyone
        # said), and a censor star (D*ED) is not a word boundary for the grounding count
        per = [TD.text_grounded(t.replace("*", ""), brief, transcript, cfg) for t in texts]
        for g in rep["gates"]:
            if g["gate"] == "text_grounded":
                g["ok"] = all(ok for ok, _ in per)
                g["detail"] = "; ".join(f"{t!r}: {why}" for t, (ok, why) in zip(texts, per))
        rep["ok"] = all(g["ok"] for g in rep["gates"])
    rep["caption_check"] = checks
    rep["recaption"] = {"text": text, "blocks": [{"text": t, "x": b["x"], "y": b["y"], "max_w": b["max_w"], "tail": b["tail"]} for t, b in zip(texts, blocks)],
                        "font_size": size, "cap_px": args.cap, "boxes": boxes, "tail_boxes": tail_boxes, "old_bbox": ob,
                        "inpaint_px": int((mask > 0).sum()), "style": args.style, "source": str(args.source or jpg),
                        "when": time.strftime("%Y-%m-%d %H:%M:%S")}
    new_ink = loose_ink_mask(cv2.imread(str(out_jpg)))
    nb = np.zeros((H, W), np.uint8)
    for b_ in boxes + tail_boxes:
        nb[max(0, b_[1] - 30):b_[3] + 30, max(0, b_[0] - 30):b_[2] + 30] = 1
    residue = int((new_ink & (1 - nb)).sum())
    rep["gates"].append({"gate": "old_type_removed", "ok": plate_residue < RESIDUE_MAX,
                         "detail": f"{plate_residue} old ink px left on the inpainted plate (max {RESIDUE_MAX})"})
    rep["gates"].append({"gate": "no_old_type_residue", "ok": residue < RESIDUE_MAX,
                         "detail": f"{residue} ink px outside the new type (max {RESIDUE_MAX})"})
    rep["ok"] = bool(rep.get("ok")) and residue < RESIDUE_MAX and plate_residue < RESIDUE_MAX
    for g in rep["gates"]:
        print(f"  {'PASS' if g['ok'] else 'FAIL'} {g['gate']:24s} {g['detail']}")
    print(f"{key} {args.family}: {'OK' if rep['ok'] else 'FAILED'}  text={text!r}  size={size}  boxes={boxes}")
    out_jpg.with_suffix(".json").write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    out_png.unlink(missing_ok=True)

    if args.apply:
        if not rep["ok"]:
            print("not applied: gates failed")
            return 2
        sup = jpg.parent / "superseded_captions"
        sup.mkdir(exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        shutil.copy2(jpg, sup / f"{jpg.stem}_{stamp}.jpg")
        if side.exists():
            shutil.copy2(side, sup / f"{side.stem}_{stamp}.json")
        shutil.move(str(out_jpg), str(jpg))
        s = json.loads(side.read_text(encoding="utf-8")) if side.exists() else {"case": key, "family": args.family}
        s["previous_text"] = (s.get("previous_text") if args.source else None) or s.get("text")
        s["text"] = text
        s["qc"] = rep
        s["recaption"] = rep["recaption"]
        side.write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")
        man.setdefault("recaptions", []).append({"family": args.family, "from": s["previous_text"], "to": text,
                                                 "backup": str(sup / f"{jpg.stem}_{stamp}.jpg"), "when": rep["recaption"]["when"]})
        (review / "thumb_direct" / "manifest.json").write_text(json.dumps(man, indent=2, ensure_ascii=False), encoding="utf-8")
        out_jpg.with_suffix(".json").unlink(missing_ok=True)
        print(f"applied -> {jpg}  (backup {sup})")
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())