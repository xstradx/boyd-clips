# -*- coding: utf-8 -*-
"""R43 - the frame has an element budget.

Nathan, 2026-08-31 07:23: "Ehh now it looks just a like but too cluttered but
the spacing looks better over all" (#110). Two subjects, a title, a kicker, an
arrow AND a circle were on one 1280x720 frame.

Budget   subjects <= 2, one title block, kicker <= 1, ONE pointer (arrow or
         circle, never both).
Cover    ink of the graphics (title + kicker + arrow + circle) as a fraction of
         the frame at 168x94, the sidebar size he judges at. Refused above the
         maximum of the five accepted builds, and the number is printed with
         that maximum beside it.

    python tools/check_clutter.py <work_dir> [out.jpg]
    python tools/check_clutter.py --accepted        # the five, and the max
    python tools/check_clutter.py --selftest

Where the numbers come from, in order of trust:
  exact          _build_log.json["ink"]["cover_168"] written by thumb.py
                 (builds after 2026-09-01), or _overlay_mask.png in the work dir
  reconstructed  title and kicker = the ink masks thumb.py saved next to the
                 build (title_ink.png / kicker_ink.png, 2026-09-01: the type
                 treatment is data now - an underline, a halo, another face -
                 and only the renderer knows its reach); for builds without
                 them, kicker REDRAWN from the logged geometry in the house
                 font/stroke and title = white/yellow fill plus its black
                 stroke inside the logged title band, subjects excluded by
                 the placed alphas. Circle redrawn from the log; arrow = red
                 pixels inside its logged box.
The verdict always uses the reconstructed number against the reconstructed
maximum, so both sides of the comparison are the same function; the exact
number is printed beside it when the build has one. Once the five accepted
builds carry exact stamps, switch COMPARE to "exact".
"""
import glob
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
FONTS = os.path.join(ROOT, "assets", "fonts")
THUMBWORK = "D:/Boyd Clips/thumbwork"
W, H = 1280, 720
SIDEBAR = (168, 94)
KICKER_STROKE = 9          # tools/thumb.py KICKER_STROKE
TITLE_STROKE = 8           # tools/thumb.py type_layer stroke_width
COMPARE = "reconstructed"  # "exact" once the accepted five carry ink stamps

BUDGET = dict(subjects=2, title=1, kicker=1, pointer=1)


# ----------------------------------------------------------------- elements --
def elements(log):
    """Counts straight off the build log. Every key here is written by
    tools/thumb.py; an absent key is an absent element."""
    subjects = sum(1 for k in ("boyd", "defendant")
                   if isinstance(log.get(k), dict) and log[k].get("face_h"))
    if isinstance(log.get("extra"), dict):
        subjects += 1                      # the monkey, the artefact
    title = 1 if isinstance(log.get("type"), dict) else 0
    kicker = 1 if isinstance(log.get("kicker"), dict) and log["kicker"].get("text") else 0
    arrow = 1 if isinstance(log.get("arrow"), dict) and log["arrow"].get("w", 0) > 0 else 0
    circle = 1 if isinstance(log.get("extra_circle"), dict) else 0
    return dict(subjects=subjects, title=title, kicker=kicker, arrow=arrow,
                circle=circle, pointer=arrow + circle)


def budget_fails(el):
    fails = []
    for k, cap in BUDGET.items():
        if el[k] > cap:
            what = k
            if k == "pointer":
                what = "pointers (arrow + circle)"
            fails.append(f"{el[k]} {what}, budget {cap}")
    if el["title"] == 0:
        fails.append("no title block logged")
    return fails


# --------------------------------------------------------------- ink masks --
def _subject_alpha(work):
    m = np.zeros((H, W), np.float32)
    for nm in ("_placed_alpha_judge.png", "_placed_alpha_defendant.png"):
        a = cv2.imread(os.path.join(work, nm), cv2.IMREAD_GRAYSCALE)
        if a is None:
            continue
        if a.shape != (H, W):
            a = cv2.resize(a, (W, H), interpolation=cv2.INTER_AREA)
        m = np.maximum(m, a.astype(np.float32) / 255.0)
    return m


def _saved_ink(work, name):
    """The ink mask thumb.py wrote next to the build (builds after
    2026-09-01: title_ink.png / kicker_ink.png). This is the mask the build
    itself measured R1 and the arrow against, so it is right for EVERY type
    treatment - the redraw below assumes the house font and stroke and is
    wrong for an underline, a panel or an extrude. None when absent."""
    if not work:
        return None
    m = cv2.imread(os.path.join(work, name), cv2.IMREAD_GRAYSCALE)
    if m is None:
        return None
    if m.shape != (H, W):
        m = cv2.resize(m, (W, H), interpolation=cv2.INTER_NEAREST)
    return m > 127


def kicker_mask(log, work=None):
    k = log.get("kicker")
    if not isinstance(k, dict) or not k.get("text"):
        return np.zeros((H, W), bool)
    saved = _saved_ink(work, "kicker_ink.png")
    if saved is not None:
        return saved
    font = ImageFont.truetype(os.path.join(FONTS, "Anton-Regular.ttf"), int(k["size"]))
    ink = Image.new("L", (W, H), 0)
    ImageDraw.Draw(ink).text((int(k["x"]), int(k["y"])), k["text"], font=font,
                             fill=255, stroke_width=KICKER_STROKE, stroke_fill=255)
    return np.asarray(ink) > 40


def circle_mask(log):
    c = log.get("extra_circle")
    if not isinstance(c, dict):
        return np.zeros((H, W), bool)
    ann = np.zeros((H, W), np.float32)
    cx, cy = (int(v) for v in c["centre"])
    cv2.ellipse(ann, (cx, cy), (int(c["rx"]), int(c["ry"])), 0, 0, 360, 1.0,
                int(c.get("thickness", 11)), lineType=cv2.LINE_AA)
    return ann > 0.5


def arrow_mask(log, bgr):
    a = log.get("arrow")
    if not isinstance(a, dict) or a.get("w", 0) <= 0:
        return np.zeros((H, W), bool)
    x0, y0 = max(0, int(a["x"])), max(0, int(a["y"]))
    x1, y1 = min(W, x0 + int(a["w"])), min(H, y0 + int(a["h"]))
    m = np.zeros((H, W), bool)
    box = bgr[y0:y1, x0:x1].astype(np.int32)
    b, g, r = box[..., 0], box[..., 1], box[..., 2]
    red = (r > 150) & (g < 90) & (b < 90) & (r - np.maximum(g, b) > 90)
    m[y0:y1, x0:x1] = red
    return m


def title_mask(log, bgr, subj, work=None):
    t = log.get("type")
    if not isinstance(t, dict):
        return np.zeros((H, W), bool)
    saved = _saved_ink(work, "title_ink.png")
    if saved is not None:
        return saved & (subj < 0.4)
    top = max(0, int(t.get("top", 26)) - 14)
    bot = int(log.get("title_bottom") or (t["top"] + t["cap"] + 40)) + 14
    bot = min(H, bot)
    m = np.zeros((H, W), bool)
    band = bgr[top:bot].astype(np.int32)
    b, g, r = band[..., 0], band[..., 1], band[..., 2]
    mn, mx = band.min(axis=2), band.max(axis=2)
    white = (mn > 200)
    yellow = (r > 170) & (g > 150) & (b < 120) & (r - b > 90)
    dark = (mx < 60)
    # Type is fill WRAPPED IN A BLACK STROKE. A ceiling light is white too, but
    # nothing dark wraps it - so keep only fill blobs whose 2 px ring is mostly
    # dark. Measured on OFFERUP_NEW: without this the lights above the title
    # were counted as ink.
    cand = (white | yellow).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(cand, connectivity=8)
    fill = np.zeros(cand.shape, bool)
    ring_k = np.ones((5, 5), np.uint8)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] < 20:
            continue
        comp = lab == i
        ring = (cv2.dilate(comp.astype(np.uint8), ring_k) > 0) & ~comp
        if ring.any() and float(dark[ring].mean()) >= 0.5:
            fill |= comp
    # the stroke itself: dark within TITLE_STROKE+2 px of the kept fill
    k = 2 * (TITLE_STROKE + 2) + 1
    near = cv2.dilate(fill.astype(np.uint8), np.ones((k, k), np.uint8)) > 0
    m[top:bot] = (fill | (near & dark)) & (subj[top:bot] < 0.4)
    return m


def reconstructed_mask(work, log, bgr, saved=True):
    """`saved=False` ignores title_ink.png / kicker_ink.png in the work dir
    and reconstructs from the log + pixels (the selftest's synthetic controls
    paint on the JPEG, so a saved mask would not describe them)."""
    subj = _subject_alpha(work)
    w = work if saved else None
    parts = dict(title=title_mask(log, bgr, subj, w), kicker=kicker_mask(log, w),
                 arrow=arrow_mask(log, bgr), circle=circle_mask(log))
    ov = np.zeros((H, W), bool)
    for v in parts.values():
        ov |= v
    return ov, {k: int(v.sum()) for k, v in parts.items()}


def cover_168(mask):
    small = cv2.resize(mask.astype(np.float32), SIDEBAR, interpolation=cv2.INTER_AREA)
    return float((small > 0.5).mean())


def exact_cover(work, log):
    ink = log.get("ink")
    if isinstance(ink, dict) and "cover_168" in ink:
        return float(ink["cover_168"]), "log"
    p = os.path.join(work, "_overlay_mask.png")
    m = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
    if m is not None:
        return cover_168(m > 127), "_overlay_mask.png"
    return None, None


def _load(work, out_jpg=None):
    log = json.load(open(os.path.join(work, "_build_log.json"), encoding="utf-8"))
    if out_jpg is None:
        case = os.path.basename(os.path.normpath(work))
        cands = [os.path.join(work, f"{case}_NEW.jpg"), os.path.join(work, f"{case}_FINAL.jpg")]
        out_jpg = next((c for c in cands if os.path.exists(c)), None)
        if out_jpg is None:
            raise FileNotFoundError(f"no {case}_NEW.jpg / _FINAL.jpg in {work}")
    bgr = cv2.imread(out_jpg)
    if bgr is None:
        raise FileNotFoundError(out_jpg)
    if bgr.shape[:2] != (H, W):
        bgr = cv2.resize(bgr, (W, H), interpolation=cv2.INTER_AREA)
    return log, bgr, out_jpg


def measure(work, out_jpg=None):
    log, bgr, out_jpg = _load(work, out_jpg)
    el = elements(log)
    ov, parts = reconstructed_mask(work, log, bgr)
    rec = cover_168(ov)
    ex, ex_src = exact_cover(work, log)
    return dict(work=work, jpg=out_jpg, elements=el, reconstructed=rec,
                parts=parts, exact=ex, exact_src=ex_src)


# ------------------------------------------------------------- accepted max --
def accepted_dirs():
    fl = json.load(open(os.path.join(ROOT, "config", "quality_floor.json"), encoding="utf-8"))
    out = []
    for case in fl.get("approved", []):
        d = os.path.join(THUMBWORK, case)
        if os.path.isdir(d) and os.path.exists(os.path.join(d, "_build_log.json")):
            out.append(d)
    return out


def accepted_max(verbose=False):
    rows = []
    for d in accepted_dirs():
        m = measure(d)
        rows.append(m)
        if verbose:
            print(f"  {os.path.basename(d):9} recon {m['reconstructed']:.3f}"
                  + (f"  exact {m['exact']:.3f} ({m['exact_src']})" if m['exact'] is not None else "")
                  + f"  parts {m['parts']}  elements {m['elements']}")
    if not rows:
        return None, rows
    key = "exact" if COMPARE == "exact" else "reconstructed"
    vals = [r[key] for r in rows if r[key] is not None]
    return (max(vals) if vals else None), rows


# ----------------------------------------------------------------- check ----
def check(work, out_jpg=None, verbose=True, _accepted=None):
    m = measure(work, out_jpg)
    fails = budget_fails(m["elements"])
    amax = _accepted if _accepted is not None else accepted_max()[0]
    key = "exact" if COMPARE == "exact" else "reconstructed"
    val = m[key]
    if amax is None:
        fails.append("no accepted builds mounted to set the cover ceiling")
    elif val is None:
        fails.append(f"no {key} ink cover for this build")
    elif val > amax + 1e-6:
        fails.append(f"ink cover {val:.3f} at 168x94 is above the accepted maximum {amax:.3f}")
    ok = not fails
    if verbose:
        el = m["elements"]
        print(("CLUTTER_OK    " if ok else "CLUTTER_FAIL  ") + os.path.basename(m["jpg"]))
        print(f"    elements  subjects {el['subjects']}/{BUDGET['subjects']}  title {el['title']}"
              f"  kicker {el['kicker']}/{BUDGET['kicker']}  pointer {el['pointer']}/{BUDGET['pointer']}"
              f" (arrow {el['arrow']}, circle {el['circle']})")
        line = f"    ink cover {m['reconstructed']:.3f} reconstructed"
        if m["exact"] is not None:
            line += f", {m['exact']:.3f} exact ({m['exact_src']})"
        line += f"  |  accepted max {amax:.3f} ({COMPARE})" if amax is not None else "  |  accepted max: none"
        print(line)
        print(f"    parts px  {m['parts']}")
        for f in fails:
            print("    REFUSED  " + f)
    return ok, m, fails


# --------------------------------------------------------------- selftest ----
def selftest():
    """Known answers before any number is trusted: a log with arrow AND circle
    refuses, one pointer passes, the accepted five pass under their own
    maximum, and the reconstruction agrees with the pixels where it can be
    checked (kicker redraw vs kicker-coloured pixels in the JPEG)."""
    ok = True

    def case(label, good):
        nonlocal ok
        ok = ok and good
        print(f"  {'ok  ' if good else 'FAIL'} {label}")

    # 1. budget arithmetic on synthetic logs
    base = dict(type=dict(size=100, cap=90, top=26), title_bottom=170,
                boyd=dict(face_h=200), defendant=dict(face_h=200),
                kicker=dict(text="X", size=80, x=0, y=560),
                arrow=dict(x=500, y=300, w=278, h=232))
    both = dict(base, extra_circle=dict(centre=(300, 300), rx=60, ry=60, thickness=11))
    case("arrow + circle refuses", bool(budget_fails(elements(both))))
    case("arrow only passes the budget", not budget_fails(elements(base)))
    case("circle only passes the budget",
         not budget_fails(elements(dict(base, arrow="off",
                                        extra_circle=both["extra_circle"]))))
    three = dict(base, extra=dict(png="monkey.png", h=100, w=90, cx=400, cy=400, px=1000))
    case("third pictorial element refuses (3 subjects)", bool(budget_fails(elements(three))))
    case("no title refuses", bool(budget_fails(elements(dict(base, type=None)))))

    # 2. the accepted five pass under their own maximum, and none is empty
    amax, rows = accepted_max(verbose=True)
    if rows:
        case(f"accepted max measured = {amax:.3f} on {len(rows)} builds", amax is not None and amax > 0.02)
        for r in rows:
            got, _, fails = check(r["work"], r["jpg"], verbose=False, _accepted=amax)
            case(f"accepted {os.path.basename(r['work'])} passes ({r['reconstructed']:.3f})", got)
        # 3. a synthetic overload on the worst accepted build must refuse: the
        #    same JPEG with a SECOND title line (same Anton, same black stroke)
        #    drawn under the first -> cover refusal. A plain white band is NOT
        #    a control here: it has no stroke, so the reconstruction rightly
        #    ignores it - this measure is type ink, not brightness.
        r = max(rows, key=lambda x: x["reconstructed"])
        log, bgr, jpg = _load(r["work"], r["jpg"])
        t = log["type"]
        pil = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        font = ImageFont.truetype(os.path.join(FONTS, "Anton-Regular.ttf"), int(t["size"]))
        y2 = int(log.get("title_bottom") or 170) + 6
        ImageDraw.Draw(pil).text((20, y2), "AND THEN SHE SAID THIS", font=font,
                                 fill=(255, 255, 255), stroke_width=TITLE_STROKE,
                                 stroke_fill=(0, 0, 0))
        over = cv2.cvtColor(np.asarray(pil), cv2.COLOR_RGB2BGR)
        over_log = dict(log, title_bottom=y2 + int(t["cap"]) + 40)
        ov, _ = reconstructed_mask(r["work"], over_log, over, saved=False)
        case(f"second title line on {os.path.basename(jpg)} = {cover_168(ov):.3f} > {amax:.3f} refuses",
             cover_168(ov) > amax)
        # 4. reconstruction vs pixels: kicker redraw must agree with the
        #    kicker-coloured pixels inside its own bbox
        km = kicker_mask(log)
        ys, xs = np.where(km)
        if len(xs):
            x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
            box = bgr[y0:y1, x0:x1].astype(np.int32)
            b, g, rr = box[..., 0], box[..., 1], box[..., 2]
            mn, mx = box.min(axis=2), box.max(axis=2)
            gold = (rr > 170) & (g > 140) & (b < 120)
            white = mn > 200
            dark = mx < 60
            pix = gold | white | dark
            inter = float((pix & km[y0:y1, x0:x1]).sum())
            union = float((pix | km[y0:y1, x0:x1]).sum())
            iou = inter / union if union else 0.0
            case(f"kicker redraw vs kicker pixels IoU {iou:.2f} >= 0.60 ({os.path.basename(jpg)})", iou >= 0.60)
    else:
        print("  skip  thumbwork tree not mounted; accepted-max cases not run")
    print("SELFTEST_PASS check_clutter" if ok else "SELFTEST_FAIL check_clutter")
    return ok


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] == "--selftest":
        sys.exit(0 if selftest() else 1)
    if a[0] == "--accepted":
        amax, rows = accepted_max(verbose=True)
        print(f"  accepted max ({COMPARE}) = {amax:.3f}" if amax is not None else "  none mounted")
        sys.exit(0)
    work = a[0]
    out = a[1] if len(a) > 1 else None
    sys.exit(0 if check(work, out)[0] else 1)
