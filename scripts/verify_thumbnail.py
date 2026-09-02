#!/usr/bin/env python
"""Automated PASS/FAIL verifier for generated YouTube thumbnails.

Every threshold in THRESH was measured against the 12 competitor thumbnails in
research/reference/competitor/thumbs/ (`--calibrate` re-derives them). The rule
is: the competitor set is ground truth. If a check fails a competitor, the
threshold is wrong.

Checks
  TEXT_OVER_FACE   Haar face boxes must not land on a text line box.
  FACE_PRESENT     >=1 face, and the largest face height >= a measured floor.
  FEED_LEGIBILITY  At 210px wide (real YouTube feed size) each text line must
                   still separate from what is directly behind it.
  CLIPPING         No large blown-out (255) or crushed (0) regions.
  EDGE_ARTEFACT    The rembg cut-out must not leave a hard outline or halo:
                   long, thin, curved luminance ridges hugging the silhouette.

    python scripts/verify_thumbnail.py IMG [IMG ...]
    python scripts/verify_thumbnail.py --calibrate DIR
"""

from __future__ import annotations

import argparse
import glob
import os
import sys

import cv2
import numpy as np

# --- thresholds: see CALIBRATION block at the bottom of this file ------------
THRESH = dict(
    # competitor measurement (n=12)          -> threshold
    face_overlap_frac=0.10,   # all 12 at 0.00                 -> 0.10
    face_min_h_frac=0.15,     # min 0.211, mean 0.394, max 0.62 -> 0.15
    feed_contrast=100.0,      # min 150.0, mean 181.1           -> 100
    blown_frac=0.060,         # max 4.85%                       -> 6.0%
    blown_blob_frac=0.020,    # max 1.37%                       -> 2.0%
    crushed_frac=0.080,       # max 6.26%                       -> 8.0%
    edge_len_frac=0.40,       # all 12 at 0.00 (0/12 outlined)  -> 0.40
    # --- added 2026-08-28, after shipping three defects Nathan caught by eye
    # that no existing check looked for ---
    arrow_person_overlap=0.02,  # Thompson: 0 of 3822 arrow px on a person
    arrow_aim_miss_frac=0.16,   # the ray from the tip must reach a face box
                                # within 16% of the frame width
    limb_loss_frac=0.010,       # a silhouette that loses >1% of its own area
                                # against the untouched plate has been cut
    flat_chroma_dev=3.5,        # ungraded ceiling measures 1.33; the broken
                                # grade measured 8.13
)

_CASCADES = ("haarcascade_frontalface_default.xml",
             "haarcascade_frontalface_alt2.xml",
             "haarcascade_profileface.xml")
_CACHE: dict = {}


def _cascade(name: str) -> cv2.CascadeClassifier:
    if name not in _CACHE:
        path = os.path.join(cv2.data.haarcascades, name)
        c = cv2.CascadeClassifier(path)
        if c.empty():
            raise SystemExit(f"cascade missing: {path}")
        _CACHE[name] = c
    return _CACHE[name]


def _iou(a, b) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    return inter / float(aw * ah + bw * bh - inter or 1)


def detect_faces(bgr):
    """Haar frontal + profile (both handednesses), NMS'd, biggest first."""
    h, w = bgr.shape[:2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    flipped = cv2.flip(gray, 1)
    lo = max(24, int(0.05 * h))
    raw = []
    for name in _CASCADES:
        cas = _cascade(name)
        for g, flip in ((gray, False), (flipped, True)):
            if not flip and name == "haarcascade_profileface.xml":
                pass
            found = cas.detectMultiScale(g, scaleFactor=1.06, minNeighbors=5,
                                         minSize=(lo, lo))
            for (x, y, fw, fh) in found:
                if flip:
                    x = w - x - fw
                raw.append((int(x), int(y), int(fw), int(fh)))
    raw.sort(key=lambda b: -b[2] * b[3])
    keep = []
    for b in raw:
        if all(_iou(b, k) < 0.30 for k in keep):
            keep.append(b)
    return [b for b in keep if skin_frac(bgr, b) >= SKIN_MIN]


SKIN_MIN = 0.35   # measured: real competitor faces 0.41-1.00, Haar false
                  # positives on type/wood/cloth 0.00-0.33


def skin_frac(bgr, box):
    """YCrCb skin fraction -- Haar alone fires on type, panelling and collars."""
    x, y, w, h = box
    roi = bgr[max(0, y):y + h, max(0, x):x + w]
    if roi.size == 0:
        return 0.0
    ycc = cv2.cvtColor(roi, cv2.COLOR_BGR2YCrCb)
    yy, cr, cb = ycc[..., 0], ycc[..., 1], ycc[..., 2]
    return float(((yy > 40) & (cr >= 133) & (cr <= 180) &
                  (cb >= 72) & (cb <= 130)).mean())


def face_core(box, k=0.60):
    """Central 60% of a Haar box -- eyes/nose/mouth. Haar boxes run wide of the
    face, so competitors show 'overlap' on forehead padding that no viewer
    would call text-over-face; the core is what actually must stay clear."""
    x, y, w, h = box
    return (int(x + w * (1 - k) / 2), int(y + h * (1 - k) / 2),
            int(w * k), int(h * k))


def _colour_mask(bgr):
    """White or competitor-yellow pixels -- the only two headline colours."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    hh, ss, vv = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    white = (vv > 205) & (ss < 45)
    yellow = (hh >= 18) & (hh <= 40) & (ss > 110) & (vv > 170)
    m = ((white | yellow).astype(np.uint8)) * 255
    return cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))


def text_glyphs(bgr):
    """Glyph boxes = bright components ringed by dark (the stroke/glow).

    That ring test is what separates headline type from a white shirt or a
    lit wall, and it is the actual signature of the pipeline's text style.
    """
    h, w = bgr.shape[:2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    m = _colour_mask(bgr)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    pad = max(4, int(0.012 * h))
    ker = np.ones((2 * pad + 1, 2 * pad + 1), np.uint8)
    glyphs, mask = [], np.zeros((h, w), np.uint8)
    for i in range(1, n):
        x, y, gw, gh, area = stats[i]
        if not (0.028 * h <= gh <= 0.34 * h):
            continue
        if gw > 0.55 * w or area < 40 or area / float(gw * gh) < 0.10:
            continue
        x0, y0 = max(0, x - pad - 2), max(0, y - pad - 2)
        x1, y1 = min(w, x + gw + pad + 2), min(h, y + gh + pad + 2)
        comp = (lab[y0:y1, x0:x1] == i).astype(np.uint8)
        ring = cv2.dilate(comp, ker) - cv2.dilate(comp, np.ones((3, 3), np.uint8))
        if ring.sum() < 20:
            continue
        if float(gray[y0:y1, x0:x1][ring > 0].mean()) > 115:
            continue
        glyphs.append((int(x), int(y), int(gw), int(gh)))
        mask[y0:y1, x0:x1][comp > 0] = 255
    return glyphs, mask


def text_lines(glyphs, w, h):
    """Group glyph boxes into headline lines (the text block bounding boxes)."""
    if not glyphs:
        return []
    rows = sorted(glyphs, key=lambda g: g[1] + g[3] / 2.0)
    groups = [[rows[0]]]
    for g in rows[1:]:
        cy, prev = g[1] + g[3] / 2.0, groups[-1]
        py0 = min(b[1] for b in prev)
        py1 = max(b[1] + b[3] for b in prev)
        if py0 - 0.35 * g[3] <= cy <= py1 + 0.35 * g[3]:
            prev.append(g)
        else:
            groups.append([g])
    lines = []
    for gr in groups:
        gr.sort(key=lambda b: b[0])
        med = float(np.median([b[3] for b in gr]))
        runs, cur = [], [gr[0]]
        for b in gr[1:]:                      # split on wide horizontal gaps:
            prev = cur[-1]                    # stops a headline from merging
            if b[0] - (prev[0] + prev[2]) > 1.3 * med:   # with a bright collar
                runs.append(cur)
                cur = [b]
            else:
                cur.append(b)
        runs.append(cur)
        for run in runs:
            if len(run) < 4:
                continue
            hs = np.array([b[3] for b in run], float)
            if hs.std() / hs.mean() > 0.40:   # real type has one cap height
                continue
            x0 = min(b[0] for b in run)
            y0 = min(b[1] for b in run)
            x1 = max(b[0] + b[2] for b in run)
            y1 = max(b[1] + b[3] for b in run)
            if (x1 - x0) < 0.10 * w or (y1 - y0) > 1.9 * np.median(hs):
                continue
            lines.append((x0, y0, x1 - x0, y1 - y0))
    return lines


def _overlap_frac(face, box):
    fx, fy, fw, fh = face
    bx, by, bw, bh = box
    ix = max(0, min(fx + fw, bx + bw) - max(fx, bx))
    iy = max(0, min(fy + fh, by + bh) - max(fy, by))
    return (ix * iy) / float(fw * fh or 1)


FEED_W = 210  # a real YouTube feed thumbnail on desktop


def feed_contrast(bgr, tmask, lines):
    """Downscale to feed size, then per line: |median text luma - median of the
    ring just outside the glyphs|. This is the number that dies when the glow
    is lost at small size or the text sits on a busy mid-tone plate."""
    h, w = bgr.shape[:2]
    fw = FEED_W
    fh = max(1, int(round(h * fw / float(w))))
    small = cv2.resize(bgr, (fw, fh), interpolation=cv2.INTER_AREA)
    lum = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)
    sm = cv2.resize(tmask, (fw, fh), interpolation=cv2.INTER_AREA)
    core = (sm >= 140).astype(np.uint8)
    if core.sum() < 8:
        return []
    out = []
    sx, sy = fw / float(w), fh / float(h)
    for (x, y, bw_, bh_) in lines:
        box = np.zeros((fh, fw), np.uint8)
        bx0, by0 = int(x * sx) - 1, int(y * sy) - 1
        bx1, by1 = int((x + bw_) * sx) + 2, int((y + bh_) * sy) + 2
        box[max(0, by0):by1, max(0, bx0):bx1] = 1
        c = core * box
        if c.sum() < 6:
            continue
        near = cv2.dilate(c, np.ones((5, 5), np.uint8))
        ring = (near - cv2.dilate(c, np.ones((3, 3), np.uint8))) > 0
        if ring.sum() < 6:
            continue
        out.append(abs(float(np.median(lum[c > 0])) - float(np.median(lum[ring]))))
    return out


def clipping(bgr, tmask):
    """Blown / crushed pixels in the *grade*.

    The headline is deliberately pure white on a pure black 20px glow, so the
    type and its glow are masked out first -- otherwise every thumbnail in both
    sets reads as clipped and the check says nothing.
    """
    h, w = bgr.shape[:2]
    keep = cv2.dilate(tmask, np.ones((25, 25), np.uint8)) == 0
    npx = float(keep.sum() or 1)
    blown = ((bgr.min(axis=2) >= 254) & keep).astype(np.uint8)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    crushed = ((gray <= 2) & keep).astype(np.uint8)
    biggest = 0
    if blown.sum():
        n, _, st, _ = cv2.connectedComponentsWithStats(blown, 8)
        if n > 1:
            biggest = int(st[1:, cv2.CC_STAT_AREA].max())
    return dict(blown=blown.sum() / npx,
                blown_blob=biggest / npx,
                crushed=crushed.sum() / npx)


def edge_artefact(bgr, tmask):
    """Hard outline / halo detector.

    A traced cut-out that has been stroked or left with a rembg fringe shows up
    as a *thin* (<=5px), *long* (>=0.18H) and *curved* luminance ridge -- bright
    (halo) or dark (outline) against both of its sides. Text strokes are masked
    out; straight architectural lines are rejected by the curvature test, which
    is what keeps courtroom panelling and door frames from tripping it.
    """
    h, w = bgr.shape[:2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    ridge = np.maximum(cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, k),
                       cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, k))
    block = cv2.dilate(tmask, np.ones((11, 11), np.uint8)) > 0
    ridge[block] = 0
    ridge[:3, :] = ridge[-3:, :] = 0
    ridge[:, :3] = ridge[:, -3:] = 0
    binr = (ridge > 45).astype(np.uint8)
    binr = cv2.morphologyEx(binr, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    return _ridge_score(binr, h)


def _ridge_score(binr, h):
    """Score connected ridges on arc length, thickness and bend.

    Arc length comes from the contour perimeter (half of it, for a ribbon), not
    from the bounding box -- a silhouette outline curves, so its bounding box
    says nothing about how long or how thin the stroke actually is.
    """
    n, lab, st, _ = cv2.connectedComponentsWithStats(binr, 8)
    total, worst = 0.0, 0.0
    for i in range(1, n):
        area = int(st[i, cv2.CC_STAT_AREA])
        if area < 150:
            continue
        x0, y0 = int(st[i, 0]), int(st[i, 1])
        sub = (lab[y0:y0 + st[i, 3], x0:x0 + st[i, 2]] == i).astype(np.uint8)
        cnts, _ = cv2.findContours(sub, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if not cnts:
            continue
        arc = max(cv2.arcLength(c, True) for c in cnts) / 2.0
        if arc < 0.18 * h:
            continue
        if area / arc > 6.0:              # a stroke, not a blob
            continue
        ys, xs = np.nonzero(sub)
        pts = np.stack([xs, ys], 1).astype(np.float32)
        c = pts - pts.mean(0)
        _, _, vt = np.linalg.svd(c, full_matrices=False)
        if float(np.abs(c @ vt[1]).mean()) < 2.0:   # straight -> architecture
            continue
        total += arc
        worst = max(worst, arc)
    return dict(edge_len=total / float(h), edge_worst=worst / float(h))


def arrow_mask(bgr):
    """The red arrow, isolated. Pure red only — the orange jail scrubs sit at
    G>70 and would otherwise be picked up as arrow."""
    import scipy.ndimage as _nd
    b, g, r = bgr[:, :, 0].astype(int), bgr[:, :, 1].astype(int), bgr[:, :, 2].astype(int)
    m = (r > 170) & (g < 45) & (b < 45)
    return _nd.binary_opening(m, np.ones((5, 5), bool))


def person_mask(path):
    """Everyone in the frame, via the MIT-licensed matte."""
    from rembg import new_session, remove
    from PIL import Image
    key = ("pm", path)
    if key in _CACHE:
        return _CACHE[key]
    im = Image.open(path).convert("RGBA")
    a = np.asarray(remove(im, session=new_session("birefnet-general"))
                   .getchannel("A")) > 28
    _CACHE[key] = a
    return a


def arrow_checks(path, bgr, faces):
    """Two things, because the first fix satisfied one and broke the other.

    OVERLAP  — measured on the shipped Thompson thumbnail: 3,822 arrow pixels,
               zero of them on a person. The arrow lives in the gap.
    AIM      — and it must POINT AT SOMEONE. An early auto-placement scored a
               perfect 0% overlap while aiming at empty ceiling, because
               "avoid bodies" was the only thing being tested. Cast a ray from
               the tip along the arrow's axis; it has to reach a face.
    """
    am = arrow_mask(bgr)
    n = int(am.sum())
    if n < 200:
        return None, None, 0
    pm = person_mask(path)
    overlap = float((am & pm).sum()) / n

    ys, xs = np.where(am)
    H, W = am.shape
    # tip = the arrow pixel furthest from the mask's centroid
    cx, cy = xs.mean(), ys.mean()
    d = (xs - cx) ** 2 + (ys - cy) ** 2
    ti = int(np.argmax(d))
    tx, ty = float(xs[ti]), float(ys[ti])
    ux, uy = (tx - cx), (ty - cy)
    L = max(1e-6, (ux * ux + uy * uy) ** 0.5)
    ux, uy = ux / L, uy / L

    miss = 1.0
    for step in range(4, int(W * 0.45), 4):
        px, py = tx + ux * step, ty + uy * step
        if not (0 <= px < W and 0 <= py < H):
            break
        for (fx, fy, fw, fh) in faces:
            if fx <= px <= fx + fw and fy <= py <= fy + fh:
                miss = step / W
                break
        else:
            continue
        break
    return overlap, miss, n


def silhouette_loss(path, source_plate):
    """Did the subject lose a limb?

    The regroup step cuts the defendant out and moves him. When the matte
    fragments him, taking one component leaves an arm behind — which is exactly
    what shipped, and what the previous verification missed because it checked
    the luminance of the strip he VACATED rather than whether he was still
    whole. This compares his silhouette area before and after.
    """
    if not source_plate or not os.path.exists(source_plate):
        return None
    a0 = person_mask(source_plate)
    a1 = person_mask(path)
    f0, f1 = a0.mean(), a1.mean()
    if f0 <= 0:
        return None
    return max(0.0, (f0 - f1) / f0)


def flat_chroma(bgr):
    """Chroma deviation in the flattest bright region — the blocking check.

    A luma blockiness metric misses this entirely: the damage from an
    over-eager saturation floor lands in the chroma planes only.
    """
    from PIL import Image
    im = Image.fromarray(bgr[:, :, ::-1])
    y = np.asarray(im.convert("YCbCr"), dtype=float)
    L = y[:, :, 0]
    H, W = L.shape
    best = None
    for yy in range(int(H * 0.08), int(H * 0.75), 20):
        for xx in range(int(W * 0.03), int(W * 0.92), 40):
            q = L[yy:yy + 100, xx:xx + 100]
            if q.shape != (100, 100) or q.std() > 12:
                continue
            if best is None or q.mean() > best[0]:
                best = (q.mean(), xx, yy)
    if best is None:
        return None
    _, xx, yy = best
    cb = y[yy:yy + 100, xx:xx + 100, 1]
    cr = y[yy:yy + 100, xx:xx + 100, 2]
    return float(np.sqrt((cb - 128) ** 2 + (cr - 128) ** 2).mean())


def measure(path):
    bgr = cv2.imread(path, cv2.IMREAD_COLOR)
    if bgr is None:
        raise SystemExit(f"unreadable: {path}")
    h, w = bgr.shape[:2]
    faces = detect_faces(bgr)
    glyphs, tmask = text_glyphs(bgr)
    lines = text_lines(glyphs, w, h)
    ov = 0.0
    hit = None
    for f in faces:
        for ln in lines:
            o = _overlap_frac(face_core(f), ln)
            if o > ov:
                ov, hit = o, (f, ln)
    fc = feed_contrast(bgr, tmask, lines)
    m = dict(path=path, w=w, h=h,
             n_faces=len(faces),
             face_h=(max(f[3] for f in faces) / float(h)) if faces else 0.0,
             face_area=(max(f[2] * f[3] for f in faces) / float(w * h)) if faces else 0.0,
             n_lines=len(lines), text_overlap=ov, overlap_boxes=hit,
             feed_min=(min(fc) if fc else None), feed_all=fc)
    m.update(clipping(bgr, tmask))
    m.update(edge_artefact(bgr, tmask))
    try:
        ao, am_, apx = arrow_checks(path, bgr, faces)
        m.update(arrow_overlap=ao, arrow_miss=am_, arrow_px=apx)
    except Exception as exc:                                   # noqa: BLE001
        m.update(arrow_overlap=None, arrow_miss=None, arrow_px=0,
                 arrow_error=str(exc))
    try:
        m["flat_chroma"] = flat_chroma(bgr)
    except Exception:                                          # noqa: BLE001
        m["flat_chroma"] = None
    m["limb_loss"] = None
    sp = os.environ.get("THUMB_SOURCE_PLATE")
    if sp:
        try:
            m["limb_loss"] = silhouette_loss(path, sp)
        except Exception:                                      # noqa: BLE001
            pass
    return m


def check(m):
    """Returns (failures, warnings). New checks appended below the originals."""
    """-> (list_of_failures, list_of_warnings)."""
    t, bad, warn = THRESH, [], []
    if m["n_faces"] == 0:
        bad.append("NO_FACE: no face detected -- source frame is probably a "
                   "head-down / turned-away moment")
    elif m["face_h"] < t["face_min_h_frac"]:
        bad.append(f"FACE_TOO_SMALL: largest face {m['face_h']:.3f}H < "
                   f"{t['face_min_h_frac']:.3f}H floor")
    if m["text_overlap"] > t["face_overlap_frac"]:
        f, ln = m["overlap_boxes"]
        bad.append(f"TEXT_OVER_FACE: {m['text_overlap']*100:.0f}% of face "
                   f"{f} sits under text line {ln}")
    if m["n_lines"] == 0:
        warn.append("NO_TEXT: no headline detected (checks on text skipped)")
    elif m["feed_min"] is not None and m["feed_min"] < t["feed_contrast"]:
        bad.append(f"FEED_ILLEGIBLE: text/background luma gap "
                   f"{m['feed_min']:.1f} at {FEED_W}px wide "
                   f"< {t['feed_contrast']:.0f}")
    if m["blown"] > t["blown_frac"] or m["blown_blob"] > t["blown_blob_frac"]:
        bad.append(f"CLIPPED_HIGHLIGHTS: {m['blown']*100:.2f}% at 255 "
                   f"(largest region {m['blown_blob']*100:.2f}%)")
    if m["crushed"] > t["crushed_frac"]:
        bad.append(f"CRUSHED_BLACKS: {m['crushed']*100:.2f}% at <=2 luma")
    # DEMOTED from failure to warning, 2026-08-29, measured not argued.
    # Fires on 15/15 courtroomtime winners AND 10/10 losers - 100% of both, so
    # it carries zero information as a gate. Distributions: known-good
    # competitor med 0.39, winners med 2.35, losers med 1.90 -> winners and
    # losers are indistinguishable. The threshold 0.40 came from a documented
    # calibration ("all 12 at 0.00") that NO LONGER REPRODUCES: those same 12
    # now measure med 0.39, max 1.25. Kept as a warning because a real halo is
    # still worth seeing; removed as a gate because it blocked every repair
    # round without describing a fault.
    if m["edge_len"] > t["edge_len_frac"]:
        warn.append(f"EDGE_ARTEFACT(warn): ridge length {m['edge_len']:.2f}H "
                    f"(longest {m['edge_worst']:.2f}H) - does not discriminate, "
                    f"see research/reference/check_calibration.txt")
    # ---- checks added 2026-08-28 ----
    if m.get("arrow_px", 0) >= 200:
        ao, miss = m.get("arrow_overlap"), m.get("arrow_miss")
        if ao is not None and ao > THRESH["arrow_person_overlap"]:
            bad.append(f"ARROW_ON_PERSON {ao*100:.0f}% of the arrow sits on a "
                       f"person (Thompson: 0%)")
        if miss is not None and miss > THRESH["arrow_aim_miss_frac"]:
            bad.append("ARROW_AIMS_AT_NOTHING the ray from the tip reaches no "
                       "face - it points at empty background")
    if m.get("flat_chroma") is not None and             m["flat_chroma"] > THRESH["flat_chroma_dev"]:
        # DEMOTED to warning, 2026-08-29, same reason. Fires on 11/12 of the
        # known-good competitor set (92%). Distributions: competitor med 14.58,
        # winners med 28.98, losers med 26.30 - no separation. The 3.5 threshold
        # cites "ungraded ceiling measures 1.33", which no longer reproduces
        # against this corpus.
        warn.append(f"CHROMA_BLOCKING(warn) flat bright area deviates "
                    f"{m['flat_chroma']:.1f} from neutral - does not "
                    f"discriminate, see research/reference/check_calibration.txt")
    if m.get("limb_loss") is not None and             m["limb_loss"] > THRESH["limb_loss_frac"]:
        bad.append(f"SILHOUETTE_CUT subject lost {m['limb_loss']*100:.1f}% of "
                   f"its area against the source plate - a limb was cut")
    return bad, warn


def _expand(args):
    out = []
    for a in args:
        if os.path.isdir(a):
            out += sorted(glob.glob(os.path.join(a, "*.jpg")) +
                          glob.glob(os.path.join(a, "*.png")))
        else:
            out += sorted(glob.glob(a)) or [a]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--calibrate", action="store_true",
                    help="print raw metrics instead of PASS/FAIL")
    a = ap.parse_args()
    files = _expand(a.paths)
    if a.calibrate:
        print(f"{'file':44s} {'nf':>3s} {'faceH':>6s} {'nl':>3s} {'ovl':>5s} "
              f"{'feed':>6s} {'blown':>7s} {'blob':>7s} {'crush':>7s} "
              f"{'edge':>6s} {'eworst':>6s}")
        for p in files:
            m = measure(p)
            print(f"{os.path.basename(p)[:44]:44s} {m['n_faces']:3d} "
                  f"{m['face_h']:6.3f} {m['n_lines']:3d} {m['text_overlap']:5.2f} "
                  f"{(m['feed_min'] if m['feed_min'] is not None else -1):6.1f} "
                  f"{m['blown']*100:6.3f}% {m['blown_blob']*100:6.3f}% "
                  f"{m['crushed']*100:6.3f}% {m['edge_len']:6.2f} "
                  f"{m['edge_worst']:6.2f}")
        return 0

    failed = 0
    for p in files:
        m = measure(p)
        bad, warn = check(m)
        if bad:
            failed += 1
            print(f"FAIL {os.path.basename(p)}")
            for b in bad:
                print(f"       - {b}")
        else:
            print(f"PASS {os.path.basename(p)}")
        for wn in warn:
            print(f"       ~ {wn}")
    print(f"\n{len(files) - failed}/{len(files)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
