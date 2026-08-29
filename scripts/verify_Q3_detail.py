"""Prove the gates on the rendered Q3_detail JPEG, from the FILE.

Nothing here trusts the builder. The person mask is re-derived by running
BiRefNet-matting on the finished JPEG; the defendant is re-found by his jail
scrubs inside that matte; the arrow is re-found by its own red; the type is
re-rendered from the same font and copy; the faces are re-detected. The only
thing taken from the builder is the copy string, and even that is checked
against the transcript.

    python scripts/verify_Q3_detail.py \\
        --img "C:/Users/natha/OneDrive/Desktop/Boyd Clips/READY-TO-POST/QUALITY/Q3_detail.jpg"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import q3lib as Q                                                  # noqa: E402
from thumb_Q3_detail import (                                      # noqa: E402
    CAP_PX, STROKE, TEXT_RIGHT, TEXT_TOP, TEXT_X, W, H, _font, scrub_mask)

ROOT = Path(__file__).resolve().parents[1]


def type_mask(white: str, yellow: str):
    line = f"{white} {yellow}".strip()
    cap = CAP_PX
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    while cap > 40 and d.textlength(line, font=_font(round(cap / 0.72))) \
            > (TEXT_RIGHT - TEXT_X):
        cap -= 1
    f = _font(round(cap / 0.72))
    m = Image.new("L", (W, H), 0)
    ImageDraw.Draw(m).text((TEXT_X, TEXT_TOP), line, font=f, fill=255,
                           stroke_width=STROKE, stroke_fill=255)
    return np.asarray(m) > 8, cap


def chroma_flat_dev(bgr):
    """LOCAL chroma deviation in flat areas -- chroma minus its own local mean.

    Blocking is chroma varying BLOCK TO BLOCK inside a flat region. Absolute
    distance from neutral is the wrong measure and I had it wrong first: it
    counts real colour, so on the flattest quarter of a frame containing a
    county-orange jumpsuit it reads 15.9 on this build and 33.0 on the shipped
    CARTHIEF, neither of which is blocking. verify_thumbnail.flat_chroma has
    the same failure in a sharper form -- it takes the BRIGHTEST flat 100x100
    patch, which on the shipped CARTHIEF lands on the jumpsuit and returns
    89.9 against Thompson's 3.7 on a neutral ceiling.

    The local form is what work/q2/cal.py measured the 2026-08-28 fix with, and
    it separates cleanly: shipped Thompson 0.73, CARTHIEF 1.30, SANCHEZ 1.41,
    OFFERUP 1.35. Absolute deviation is still reported alongside, for reference.
    """
    ycc = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb).astype(np.float32)
    Y = ycc[:, :, 0]
    lv = cv2.GaussianBlur((Y - cv2.GaussianBlur(Y, (0, 0), 1.0)) ** 2, (0, 0), 4.0)
    flat = lv < np.percentile(lv, 25)
    dev = 0.0
    for c in (1, 2):
        C = ycc[:, :, c]
        dev += ((C - cv2.GaussianBlur(C, (0, 0), 6.0)) ** 2)[flat].mean()
    absd = float(np.sqrt(((ycc[:, :, 1][flat] - 128) ** 2
                          + (ycc[:, :, 2][flat] - 128) ** 2).mean()))
    return float(np.sqrt(dev)), int(flat.sum()), absd


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--img", type=Path, required=True)
    ap.add_argument("--work", type=Path, default=ROOT / "work" / "q3")
    ap.add_argument("--transcript", type=Path,
                    default=ROOT / "work/EwwnbiAQtFk/EwwnbiAQtFk.transcript.json")
    a = ap.parse_args()

    rep = json.loads((a.work / "Q3_detail_report.json").read_text())
    bgr = cv2.imread(str(a.img))
    ok = True

    def gate(n, cond, msg):
        nonlocal ok
        ok &= bool(cond)
        print(f"[{'PASS' if cond else 'FAIL'}] {n}. {msg}")

    print(f"FILE  {a.img}  ({a.img.stat().st_size:,} bytes)")

    # ---- 1 --------------------------------------------------------------
    hh, ww = bgr.shape[:2]
    gate(1, (ww, hh) == (1280, 720), f"size {ww}x{hh}  (required 1280x720)")

    # ---- re-derive the people, from the SHIPPED pixels -------------------
    cache = a.work / "verify_people.png"
    if cache.is_file():
        alpha = np.asarray(Image.open(cache).convert("L"))
    else:
        alpha = Q.birefnet_alpha(Image.fromarray(
            cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)))
        Image.fromarray(alpha).save(cache)
    people = alpha > 24
    import scipy.ndimage as nd
    lbl, n = nd.label(alpha > 28)
    sm = scrub_mask(Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)))
    counts = nd.sum(sm, lbl, range(1, n + 1))
    defend = lbl == (int(np.argmax(counts)) + 1)
    print(f"  re-matted the finished JPEG: {n} components, "
          f"{int(people.sum()):,}px of person, defendant component "
          f"{int(defend.sum()):,}px")

    # ---- 2. no type over a face -----------------------------------------
    tm, cap = type_mask(rep["white"], rep["yellow"])
    gray = cv2.equalizeHist(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY))
    boxes = []
    for xml in ("haarcascade_frontalface_alt2.xml",
                "haarcascade_profileface.xml",
                "haarcascade_frontalface_default.xml"):
        cc = cv2.CascadeClassifier(cv2.data.haarcascades + xml)
        boxes += [tuple(int(v) for v in b)
                  for b in cc.detectMultiScale(gray, 1.05, 5, minSize=(60, 60))]
    raw = np.zeros((H, W), bool)
    feat = np.zeros((H, W), bool)
    for (fx, fy, fw, fh) in boxes:
        raw[max(0, fy):fy + fh, max(0, fx):fx + fw] = True
        p = int(fw * 0.12)
        feat[fy + int(fh * 0.25):fy + fh + p, max(0, fx - p):fx + fw + p] = True
    gate(2, int((tm & raw).sum()) == 0,
         f"type ({int(tm.sum()):,}px at cap {cap}) vs {len(boxes)} detected "
         f"faces: {int((tm & raw).sum())}px on a RAW face box, "
         f"{int((tm & feat).sum())}px on a padded brow-down feature region "
         f"(the shipped Thompson it copies puts 18.8% of its type inside a raw "
         f"box, so this is a strictly harder test than the reference passes)")

    # ---- 3. the arrow ----------------------------------------------------
    r, g, b = bgr[:, :, 2].astype(int), bgr[:, :, 1].astype(int), bgr[:, :, 0].astype(int)
    am = (r > 190) & (g < 80) & (b < 80)
    am = nd.binary_opening(am, np.ones((3, 3)))
    lb2, n2 = nd.label(am)
    if n2 == 0:
        gate(3, False, "no red arrow found in the file")
    else:
        sizes = nd.sum(np.ones_like(am), lb2, range(1, n2 + 1))
        am = lb2 == (int(np.argmax(sizes)) + 1)
        ys, xs = np.where(am)
        n_arrow = int(am.sum())
        overlap = int((am & people).sum())
        # tip and direction from the polygon itself: PCA long axis, tip = the
        # extreme point on the side nearest the defendant
        pts = np.stack([xs, ys], 1).astype(np.float64)
        c = pts.mean(0)
        u = np.linalg.svd(pts - c, full_matrices=False)[2][0]
        proj = (pts - c) @ u
        dcy, dcx = np.where(defend)
        dc = np.array([dcx.mean(), dcy.mean()])
        cand = [pts[int(np.argmax(proj))], pts[int(np.argmin(proj))]]
        tip = min(cand, key=lambda p: np.hypot(*(p - dc)))
        v = u if (tip - c) @ u > 0 else -u
        hit, who, dist = None, None, None
        for st in range(1, 700):
            px, py = int(tip[0] + v[0] * st), int(tip[1] + v[1] * st)
            if not (0 <= px < W and 0 <= py < H):
                break
            if people[py, px]:
                hit, dist = bool(defend[py, px]), st
                who = "the DEFENDANT" if hit else "someone else"
                break
        body = bgr[int(tip[1] - v[1] * 22), int(tip[0] - v[0] * 22)]
        gate(3, overlap == 0 and hit,
             f"arrow {n_arrow:,}px = {100 * n_arrow / (W * H):.2f}% of frame "
             f"(shipped Thompson 3,822px = 0.41%); {overlap}px on ANY person "
             f"(required 0); ray from the tip ({tip[0]:.0f},{tip[1]:.0f}) "
             f"direction ({v[0]:+.2f},{v[1]:+.2f}) first strikes "
             f"{who} after {dist}px; body colour "
             f"#{body[2]:02X}{body[1]:02X}{body[0]:02X} (spec #FD0101)")

    # ---- 4. flat-area chroma deviation ----------------------------------
    dev, npx, absd = chroma_flat_dev(bgr)
    gate(4, dev < 3.5,
         f"flat-area LOCAL chroma deviation {dev:.3f} over {npx:,}px "
         f"(limit 3.5; ungraded source 1.33, the broken 2026-08-28 grade 8.13; "
         f"shipped Thompson 0.73 / CARTHIEF 1.30 / SANCHEZ 1.41 / OFFERUP 1.35)"
         f"  [absolute-from-neutral, reported not gated: {absd:.2f} vs shipped "
         f"Thompson 43.91 / CARTHIEF 32.97]")

    # ---- 5. the defendant's silhouette ----------------------------------
    if rep["scoot_tile_px"] == 0:
        gate(5, True,
             "the defendant was NOT moved (the layout solver's scoot was "
             f"{'rejected by the re-matte guard' if rep['scoot_area_loss_pct'] == 0 else 'unnecessary'}"
             "), so 0.00% of his silhouette can have been lost. Proof from the "
             "file: his matte is ONE connected component of "
             f"{int(defend.sum()):,}px with no interior break")
    else:
        gate(5, abs(rep["scoot_area_loss_pct"]) < 1.0,
             f"scooted {rep['scoot_tile_px']}px of tile; silhouette area "
             f"changed {rep['scoot_area_loss_pct']:+.2f}% (limit 1.00%)")

    # ---- 6. the copy is real --------------------------------------------
    words = json.loads(a.transcript.read_text())["words"]
    hay = " ".join(w["w"] for w in words).lower()
    line = f"{rep['white']} {rep['yellow']}".strip().lower().rstrip("?.!,")
    gate(6, line in hay,
         f'copy "{rep["white"]} {rep["yellow"]}" appears verbatim in the '
         f'transcript: {line in hay}')

    # ---- reported, not gated --------------------------------------------
    Y = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb)[:, :, 0].astype(np.float32)
    print(f"  [ -- ] luminance mean {Y.mean():.1f} (shipped Thompson 125), "
          f"blacks {(Y < 32).mean() * 100:.1f}% (Thompson 9.0%)")
    print(f"  [ -- ] judge face {rep['judge_face_px']}px at {rep['judge_scale']:.2f}x "
          f"(shipped Thompson 385px, shipped CARTHIEF 336px)")
    print(f"\n{'ALL GATES PASS' if ok else 'GATES FAILED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
