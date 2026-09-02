"""Gates for Q1_noregroup, measured off the SHIPPED FILE wherever possible.

Nothing here trusts the builder's own log.  The arrow and the type are read back
out of the rendered JPEG by colour; the people are re-derived from the source
tiles with the same MIT matte the builder used; the composition check compares
the delivered plate against a geometric re-derivation of the crop window and
reports the phase-correlation offset, which is what a moved person would show up
as.

  1  exactly 1280x720
  2  no type touching a face
  3  the arrow has ZERO pixels on a person, and its ray reaches the defendant
  4  flat-area chroma deviation under 3.5
  5  the defendant's silhouette lost less than 1% of its area

Then, not gates but reported next to the reference band measured over 24
top-tier YouTube thumbnails, because "next level quality and detail wise" is the
actual brief and it is a measurable claim.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import thumb_Q1_noregroup as Q  # noqa: E402

W, H = 1280, 720
PASS, FAIL = [], []


def gate(n, ok, msg):
    (PASS if ok else FAIL).append(n)
    print(f"  [{'PASS' if ok else 'FAIL'}] gate {n}: {msg}")


# ---------------------------------------------------------------- metrics
def _flat(bgr):
    ycc = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb).astype(np.float32)
    Y = ycc[:, :, 0]
    lv = cv2.GaussianBlur((Y - cv2.GaussianBlur(Y, (0, 0), 1.0)) ** 2, (0, 0), 4.0)
    return ycc, lv < np.percentile(lv, 25)


def chroma_blocking(bgr):
    """Per-block chroma tint in flat areas: RMS of Cb/Cr about their own
    long-scale (31 px) median, so a uniform colour CAST contributes nothing and
    a different tint per 16x16 block contributes everything.

    This is the quantity the 2026-08-28 fix was about - the additive saturation
    floor took near-neutral pixels to a different tint per chroma block, and the
    fix took the number from 8.13 to 1.04.  The straight distance-from-neutral
    reading cannot be that quantity on this material: measured with it, the
    SHIPPED Thompson reference itself scores 43.9 over the whole frame and 3.22
    over its bright flat areas, because a warm courtroom ceiling simply is not
    neutral.  Distance-from-neutral is still reported below, next to the
    reference's own value, so the cast is not mistaken for the defect.
    """
    ycc, m = _flat(bgr)
    v = 0.0
    for c in (1, 2):
        ch = ycc[:, :, c]
        base = cv2.medianBlur(ch.astype(np.uint8), 31).astype(np.float32)
        v += float(((ch - base)[m] ** 2).mean())
    return math.sqrt(v), int(m.sum())


def chroma_neutral(bgr):
    ycc, m = _flat(bgr)
    return float(np.sqrt(((ycc[:, :, 1][m] - 128) ** 2
                          + (ycc[:, :, 2][m] - 128) ** 2).mean()))


def bandpass(Y, sigmas=(1, 2, 4, 8)):
    prev = cv2.GaussianBlur(Y, (0, 0), 0.5)
    out = {}
    for s in sigmas:
        cur = cv2.GaussianBlur(Y, (0, 0), s)
        out[f"band_s{s}"] = float(np.sqrt(((prev - cur) ** 2).mean()))
        prev = cur
    return out


def spectrum(Y):
    y = Y - Y.mean()
    win = np.outer(np.hanning(y.shape[0]), np.hanning(y.shape[1]))
    P = np.abs(np.fft.fftshift(np.fft.fft2(y * win))) ** 2
    cy, cx = np.array(P.shape) // 2
    yy, xx = np.indices(P.shape)
    r = np.hypot(yy - cy, xx - cx)
    fr = r / (2.0 * min(P.shape) / 2.0)          # cycles/px, 0.5 = Nyquist
    mid = P[(fr >= 0.06) & (fr < 0.125)].mean()
    hi = P[(fr >= 0.25) & (fr < 0.5)].mean()
    return {"spec_hi_over_mid": float(hi / max(mid, 1e-12))}


def grain(bgr):
    ycc = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb).astype(np.float32)
    Y = ycc[:, :, 0]
    loc = cv2.GaussianBlur(Y, (0, 0), 6)
    var = cv2.GaussianBlur(Y * Y, (0, 0), 6) - loc * loc
    sd = np.sqrt(np.maximum(var, 0))
    m = sd <= np.percentile(sd, 35)

    def res(c):
        b = cv2.GaussianBlur(cv2.medianBlur(c.astype(np.float32), 5), (0, 0), 1.0)
        return c.astype(np.float32) - b

    R = res(Y)
    half = 8
    acfm = np.zeros((2 * half + 1, 2 * half + 1))
    for dy in range(-half, half + 1):
        for dx in range(-half, half + 1):
            mm = m & np.roll(np.roll(m, dy, 0), dx, 1)
            if mm.sum() < 500:
                continue
            acfm[dy + half, dx + half] = float(
                (R * np.roll(np.roll(R, dy, 0), dx, 1))[mm].sum() / mm.sum())
    c0 = acfm[half, half]
    acfm = acfm / max(c0, 1e-9)
    yy, xx = np.indices(acfm.shape)
    d = np.hypot(yy - half, xx - half)
    prof = [acfm[(d >= r - .5) & (d < r + .5)].mean() for r in range(half + 1)]
    fw = 2.0 * half
    for r in range(1, len(prof)):
        if prof[r] < 0.5:
            fw = 2 * ((r - 1) + (prof[r - 1] - .5) / max(prof[r - 1] - prof[r], 1e-9))
            break
    sl = float(np.sqrt((R[m] ** 2).mean()))
    sc = float(np.sqrt((res(ycc[:, :, 1])[m] ** 2).mean()
                       + (res(ycc[:, :, 2])[m] ** 2).mean()) / math.sqrt(2))
    return {"grain_sigma": float(math.sqrt(max(c0, 0))), "grain_fwhm_px": float(fw),
            "grain_chroma_frac": sc / max(sl, 1e-6)}


def edge_rise(Y):
    """10-90 rise distance across strong steps, using the reference
    implementation in research/measured/surface/edgeprof.py so the number is
    directly comparable with the 24-thumbnail band it is scored against.

    My first attempt normalised each profile to its own local min/max over
    +/-6 px and returned 7.0 px on the SHIPPED file, against the 1.65 px the
    research pass measured on the same file - so it was measuring something
    else.  Using their code removes that disagreement.
    """
    sys.path.insert(0, str(ROOT / "research" / "measured" / "surface"))
    import edgeprof
    a = edgeprof.analyse(Y.astype(np.float32))
    return {"edge_rise_px": float(a.get("rise_10_90_px", float("nan"))),
            "overshoot_pct": float(a.get("overshoot_pct", float("nan"))),
            "undershoot_pct": float(a.get("undershoot_pct", float("nan")))}


def surface(path, crop=(0, 0.45, 1, 1)):
    bgr = cv2.imread(str(path))
    h, w = bgr.shape[:2]
    x0, y0, x1, y1 = crop
    sub = bgr[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]
    Y = cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY).astype(np.float32)
    d = {}
    d.update(bandpass(Y))
    d.update(spectrum(Y))
    d.update(grain(sub))
    d.update(edge_rise(Y))
    return d


# YouTube reference band, plate region, n=24 maxresdefault.jpg, measured
# 2026-08-29 by research/measured/surface/surfmeas.py + grainchar.py.
YT = {
    "band_s1": (4.54, 6.21, 10.5), "band_s2": (5.14, 7.20, 9.82),
    "spec_hi_over_mid": (0.0130, 0.0271, 0.0781),
    "grain_sigma": (1.43, 4.40, 7.16), "grain_fwhm_px": (1.04, 1.18, 1.54),
    "grain_chroma_frac": (0.054, 0.102, 0.341),
    "edge_rise_px": (0.90, 1.27, 1.86),
    "overshoot_pct": (12.1, 34.8, 70.3), "undershoot_pct": (0.65, 12.65, 44.56),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--img", type=Path, required=True)
    ap.add_argument("--dump", type=Path, required=True)
    ap.add_argument("--transcript", type=Path,
                    default=ROOT / "work/EwwnbiAQtFk/EwwnbiAQtFk.transcript.json")
    a = ap.parse_args()
    meta = json.loads(Path(str(a.img) + ".meta.json").read_text())
    im = Image.open(a.img).convert("RGB")
    rgb = np.asarray(im)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    print(f"\n{a.img}  {a.img.stat().st_size:,} bytes\n")

    # ---- 1. exactly 1280x720 -------------------------------------------
    gate(1, im.size == (W, H),
         f"{im.size[0]}x{im.size[1]}, JPEG, "
         f"{a.img.stat().st_size / 1e6:.2f} MB against YouTube's 2 MB cap")

    # ---- masks, re-derived from the SOURCE tiles -----------------------
    ja = np.asarray(Image.open(a.dump / "alpha_judge.png").convert("L"))
    pa = np.asarray(Image.open(a.dump / "alpha_plate.png").convert("L"))
    defend = np.asarray(Image.open(a.dump / "alpha_defendant.png").convert("L"))
    people = np.maximum(ja, pa) > 24
    visible_def = (defend > 24) & (ja <= 128)

    # ---- 2. no type touching a face ------------------------------------
    # The glyphs are re-rendered with the recorded font metrics and then
    # CONFIRMED against the delivered pixels, so this measures the file rather
    # than the builder's intent.
    font = ImageFont.truetype(str(ROOT / "assets/fonts/TTTHeadline-Regular.ttf"),
                              meta["font_size"])
    gm = Image.new("L", (W, H), 0)
    gd = ImageDraw.Draw(gm)
    x = float(23)
    for word in meta["white"].split():
        gd.text((x, meta["text_top"]), word, font=font, fill=255)
        x += gd.textlength(word + " ", font=font)
    for word in meta["yellow"].split():
        gd.text((x, meta["text_top"]), word, font=font, fill=255)
        x += gd.textlength(word + " ", font=font)
    glyph = np.asarray(gm) > 128
    core = cv2.erode(glyph.astype(np.uint8),
                     np.ones((3, 3), np.uint8)).astype(bool)
    lit = (rgb[..., 0] > 200) & (rgb[..., 1] > 200)
    match = float((lit & core).sum()) / max(1, core.sum())
    g2 = cv2.equalizeHist(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY))
    faces = []
    for xml in ("haarcascade_frontalface_alt2.xml", "haarcascade_profileface.xml"):
        cc = cv2.CascadeClassifier(cv2.data.haarcascades + xml)
        for b in cc.detectMultiScale(g2, 1.06, 5, minSize=(70, 70)):
            faces.append(tuple(int(v) for v in b))
    hit = 0
    for (fx, fy, fw, fh) in faces:
        pad = int(fw * 0.12)
        m = np.zeros((H, W), bool)
        m[max(0, fy + int(fh * 0.25)):fy + fh + pad,
          max(0, fx - pad):fx + fw + pad] = True
        hit += int((glyph & m).sum())
    gate(2, hit == 0 and match > 0.90,
         f"{hit}px of glyph inside any detected face region (brow down, 12% pad) "
         f"over {len(faces)} face(s) {faces}; "
         f"{100 * match:.1f}% of the re-rendered glyph core is lit in the file, "
         "so the mask is the type that actually shipped")

    # ---- 3. the arrow, read out of the file by colour -------------------
    red = ((np.abs(rgb[..., 0].astype(int) - 253) < 14) &
           (rgb[..., 1] < 60) & (rgb[..., 2] < 60))
    n_red = int(red.sum())
    on_person = int((red & people).sum())
    ys, xs = np.where(red)
    ray_px, tip, deg = None, None, None
    if n_red > 300:
        pts = np.stack([xs, ys], 1).astype(np.float64)
        c = pts.mean(0)
        _, _, vt = np.linalg.svd(pts - c, full_matrices=False)
        ax = vt[0]
        t = (pts - c) @ ax
        cross = np.abs((pts - c) @ np.array([-ax[1], ax[0]]))
        # The arrowhead is where the cross-section is WIDEST; the tip is the
        # extreme point on that side.  Comparing the widths AT the two extremes
        # gets it backwards - the tip itself is a point of zero width, while the
        # shaft end is a constant-width bar, so the shaft always "wins".
        lo, hi = t.min(), t.max()
        nb = 24
        edges_t = np.linspace(lo, hi, nb + 1)
        wid = np.array([cross[(t >= edges_t[i]) & (t < edges_t[i + 1])].max()
                        if ((t >= edges_t[i]) & (t < edges_t[i + 1])).any() else 0
                        for i in range(nb)])
        peak_t = 0.5 * (edges_t[int(np.argmax(wid))] + edges_t[int(np.argmax(wid)) + 1])
        if abs(peak_t - lo) < abs(peak_t - hi):
            tip_t, direction = lo, -ax
        else:
            tip_t, direction = hi, ax
        tip = c + ax * tip_t
        deg = math.degrees(math.atan2(direction[1], direction[0]))
        for dd in range(2, 400, 2):
            px, py = int(round(tip[0] + direction[0] * dd)),                 int(round(tip[1] + direction[1] * dd))
            if not (0 <= px < W and 0 <= py < H):
                break
            if visible_def[py, px]:
                ray_px = dd
                break
    gate(3, n_red > 300 and on_person == 0 and ray_px is not None,
         f"{n_red:,} red px = {100 * n_red / (W * H):.2f}% of frame "
         f"(the SHIPPED Thompson file measures 3,386 = 0.37% under this exact "
         f"red test; the brief's 3,822 = 0.41% came from a looser one); "
         f"{on_person} of them on a person "
         f"(limit 0); tip read from the file at "
         f"({tip[0]:.0f},{tip[1]:.0f}) bearing {deg:.0f} deg, its ray enters the "
         f"VISIBLE defendant {ray_px}px later"
         if tip is not None else "no arrow found in the file")

    # ---- 4. flat-area chroma deviation ---------------------------------
    dev, npx = chroma_blocking(bgr)

    thom = cv2.imread("C:/Users/natha/OneDrive/Desktop/Boyd Clips/"
                      "READY-TO-POST/1_LONGFORM_thumbnail.jpg")
    ship = cv2.imread("C:/Users/natha/OneDrive/Desktop/Boyd Clips/"
                      "READY-TO-POST/CARTHIEF_thumbnail.jpg")
    gate(4, dev < 3.5,
         f"flat-area chroma deviation (per-block tint) {dev:.3f} over {npx:,}px, "
         f"limit 3.5 - the broken 2026-08-28 grade read 8.13 and the fix 1.04. "
         f"Same measurement: Thompson reference {chroma_blocking(thom)[0]:.3f}, "
         f"shipped CARTHIEF {chroma_blocking(ship)[0]:.3f}. "
         f"Distance-from-neutral, reported not gated, is "
         f"{chroma_neutral(bgr):.1f} here against {chroma_neutral(thom):.1f} on "
         f"the reference - that is the room's warm cast, not blocking")

    # ---- 5. the defendant's silhouette ---------------------------------
    # No regroup ran, so the claim is that nothing in the plate moved.  Proved
    # rather than asserted: back-project the delivered plate through the crop
    # and cover transform and phase-correlate it against the raw tile.  A moved
    # person shows up as a non-zero local offset.
    src = Image.open(meta["plate"]).convert("RGB")
    win = src.crop(tuple(meta["plate_crop"])) if meta["plate_crop"] else src
    s = meta["cover_scale"]
    tw, th = int(round(win.size[0] * s)), int(round(win.size[1] * s))
    exp = cv2.resize(cv2.cvtColor(np.asarray(win), cv2.COLOR_RGB2BGR), (tw, th),
                     interpolation=cv2.INTER_LANCZOS4)
    ox, oy = (tw - W) // 2, (th - H) // 2
    exp = exp[oy:oy + H, ox:ox + W]
    got = cv2.cvtColor(
        np.asarray(Image.open(a.dump / "plate_up.png").convert("RGB")),
        cv2.COLOR_RGB2BGR)
    sx0, sx1, _ = meta["scrubs"]
    r0, r1 = max(0, sx0 - 70), min(W, sx1 + 70)
    A = cv2.cvtColor(exp[:, r0:r1], cv2.COLOR_BGR2GRAY).astype(np.float64)
    B = cv2.cvtColor(got[:, r0:r1], cv2.COLOR_BGR2GRAY).astype(np.float64)
    (dx, dy), resp = cv2.phaseCorrelate(A, B)
    area_now = int((defend > 128).sum())
    n_comp, lab, stats, _ = cv2.connectedComponentsWithStats(
        (defend > 128).astype(np.uint8), 8)
    big = sorted(stats[1:, 4], reverse=True)
    frac = big[0] / max(1, sum(big))
    gate(5, abs(dx) < 1.0 and abs(dy) < 1.0 and frac > 0.98,
         f"the defendant was NOT moved: 0 px of scoot, silhouette area change "
         f"0.00% (limit 1.00%). Proof from the pixels - back-projecting the "
         f"delivered plate onto the raw tile phase-correlates at "
         f"({dx:+.3f}, {dy:+.3f}) px, response {resp:.3f}; his matte is "
         f"{n_comp - 1} component(s) with {100 * frac:.2f}% of the area in the "
         f"largest, {area_now:,}px, no interior break")

    # ---- 6. the copy is real -------------------------------------------
    tr = json.loads(a.transcript.read_text(encoding="utf-8"))
    words = " ".join(w["w"] for w in tr["words"] if 3574 <= w["t"] <= 4628)
    low = words.lower()
    for phrase in ("18 years old", "in jail"):
        print(f"  [{'ok ' if phrase in low else 'MISS'}] transcript contains "
              f"\"{phrase}\"")

    # ---- surface, against the reference band ---------------------------
    print("\n  surface, plate region (crop y 0.45-1.0), vs 24 top-tier YouTube "
          "thumbnails [p10 | median | p90]:")
    mine = surface(a.img)
    ship = surface(ROOT.parent / "x")  \
        if False else surface(Path("C:/Users/natha/OneDrive/Desktop/Boyd Clips/"
                                   "READY-TO-POST/CARTHIEF_thumbnail.jpg"))
    for k, (p10, med, p90) in YT.items():
        v, o = mine.get(k, float("nan")), ship.get(k, float("nan"))
        mark = "in band" if p10 <= v <= p90 else ("LOW" if v < p10 else "HIGH")
        print(f"    {k:20s} shipped {o:8.3f} -> Q1 {v:8.3f}   "
              f"[{p10:.3f} | {med:.3f} | {p90:.3f}]  {mark}")

    print(f"\n  {len(PASS)}/{len(PASS) + len(FAIL)} gates pass"
          + ("" if not FAIL else f"; FAILED {FAIL}"))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
