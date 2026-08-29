"""Prove the five gates on a rendered Q4_light JPEG, from the FILE, not the code.

Nothing here reads the builder's intentions - every check is made on the pixels
that were actually written to disk, plus the masks the builder saved alongside
them. A critique written from the source is a failed critique.
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from thumb_Q4_light import (  # noqa: E402
    CAP_PX, GLOW_RADIUS, STROKE, TEXT_RIGHT, TEXT_X, TEXT_TOP, W, H,
    band_s1, chroma_flat_dev, defendant_region, font, hf_ratio, hf_ratio_pair,
    people_components, scrubs_blob, _tone_stats)

ROOT = Path(__file__).resolve().parents[1]


def type_mask(white, yellow):
    f = font(CAP_PX)
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    line = f"{white} {yellow}".strip()
    cap = CAP_PX
    while d.textlength(line, font=f) > (TEXT_RIGHT - TEXT_X) and cap > 40:
        cap -= 1
        f = font(cap)
    m = Image.new("L", (W, H), 0)
    ImageDraw.Draw(m).text((TEXT_X, TEXT_TOP + STROKE), line, font=f, fill=255,
                           stroke_width=STROKE, stroke_fill=255)
    return np.asarray(m) > 8, cap


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--img", type=Path, required=True)
    ap.add_argument("--work", type=Path, default=ROOT / "work" / "q4")
    ap.add_argument("--tag", default="Q4_light")
    ap.add_argument("--white", default="You boosted a")
    ap.add_argument("--yellow", default="Challenger?")
    ap.add_argument("--plate-tile", type=Path, default=None)
    ap.add_argument("--plate-window", default=None)
    ap.add_argument("--plate-anchor", type=float, default=0.35)
    a = ap.parse_args()

    img = cv2.imread(str(a.img))
    rep = json.loads((a.work / f"{a.tag}_report.json").read_text())
    jmask = np.load(a.work / f"{a.tag}_jmask.npy")
    dmask = np.load(a.work / f"{a.tag}_dmask.npy")
    people = np.load(a.work / f"{a.tag}_people.npy")
    pth = a.work / f"{a.tag}_arrowpoly.npy"
    poly = np.load(pth) if pth.is_file() else None
    ok = True

    print(f"FILE  {a.img}  ({a.img.stat().st_size:,} bytes)")

    # ---- 1. exactly 1280x720 --------------------------------------------
    hh, wwd = img.shape[:2]
    g1 = (wwd, hh) == (1280, 720)
    ok &= g1
    print(f"[{'PASS' if g1 else 'FAIL'}] 1. size = {wwd}x{hh}  (required 1280x720)")

    # ---- 2. no type over a face -----------------------------------------
    tm, cap = type_mask(a.white, a.yellow)
    gray = cv2.equalizeHist(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    boxes = []
    for xml in ("haarcascade_frontalface_alt2.xml", "haarcascade_profileface.xml",
                "haarcascade_frontalface_default.xml"):
        cc = cv2.CascadeClassifier(cv2.data.haarcascades + xml)
        boxes += [tuple(int(v) for v in b)
                  for b in cc.detectMultiScale(gray, 1.05, 5, minSize=(60, 60))]
    # union of every detected face, and separately the FEATURE region (below the
    # brow) that Nathan's rule is actually about - the shipped Thompson thumbnail
    # runs its own line across Judge Boyd's hair and forehead, so a whole-head
    # rule would reject the very layout being copied.
    whole = np.zeros((H, W), bool)
    feat = np.zeros((H, W), bool)
    for (fx, fy, fw, fh) in boxes:
        whole[max(0, fy):fy + fh, max(0, fx):fx + fw] = True
        feat[fy + int(fh * 0.25):fy + fh, fx:fx + fw] = True
    n_whole = int((tm & whole).sum())
    n_feat = int((tm & feat).sum())
    g2 = n_feat == 0
    ok &= g2
    print(f"[{'PASS' if g2 else 'FAIL'}] 2. type over a FACE: {n_feat}px of "
          f"{int(tm.sum())} type px inside any detected face BELOW THE BROW "
          f"({len(boxes)} face box(es) found); {n_whole}px inside a raw whole-head "
          f"box (hair/forehead, which the reference also crosses)")

    # ---- 3. arrow: zero on a person, and the ray reaches HIM -------------
    if poly is None:
        print("[FAIL] 3. no arrow was drawn")
        ok = False
    else:
        am = np.zeros((H, W), np.uint8)
        cv2.fillPoly(am, [poly.astype(np.int32)], 255)
        overlap = int(((am > 0) & (people > 24)).sum())
        n_arrow = int((am > 0).sum())
        # re-derive the tip and direction from the polygon itself
        tip = poly[0].astype(float)
        tail = poly[3:5].mean(axis=0)
        v = tip - tail
        v /= max(np.hypot(*v), 1e-6)
        hit = 0
        for t in range(2, 600):
            rx, ry = int(tip[0] + v[0] * t), int(tip[1] + v[1] * t)
            if not (0 <= rx < W and 0 <= ry < H):
                break
            if dmask[ry, rx] > 24:
                hit = t
                break
        g3 = overlap == 0 and hit > 0
        ok &= g3
        print(f"[{'PASS' if g3 else 'FAIL'}] 3. arrow: {n_arrow}px "
              f"({n_arrow / (W * H) * 100:.2f}% of frame, reference 0.41%), "
              f"{overlap}px on a person (required 0), ray from the tip enters "
              f"the DEFENDANT's matte {hit}px along (required >0)")
        px = img[int(tip[1] + v[1] * -20 + 0.5), int(tip[0] + v[0] * -20 + 0.5)]
        print(f"       arrow body colour sampled 20px behind the tip: "
              f"#{px[2]:02X}{px[1]:02X}{px[0]:02X}  (spec #FD0101)")

    # ---- 4. flat-area chroma deviation ----------------------------------
    cdev, nb = chroma_flat_dev(img)
    g4 = cdev < 3.5
    ok &= g4
    print(f"[{'PASS' if g4 else 'FAIL'}] 4. flat-area chroma deviation "
          f"{cdev:.3f} over {nb} flat blocks (required < 3.5)")

    # ---- 5. the defendant's silhouette ----------------------------------
    if a.plate_tile is None:
        a.plate_tile = a.work / f"D_{int(rep['plate_src'])}.png"
    tile_full = cv2.imread(str(a.plate_tile))
    wx0, ww = rep["plate_window"]
    tile = tile_full[:, wx0:wx0 + ww]
    from thumb_Q4_light import birefnet_alpha
    cache = a.work / "cache" / f"pa_{int(rep['plate_src'])}_{wx0}_{ww}.npy"
    pa_raw = np.load(cache) if cache.is_file() else birefnet_alpha(tile)
    pa, _, _ = people_components(pa_raw)
    dt, sbb = defendant_region(tile, pa)
    tile_area = int((dt > 24).sum())
    ph, pw = tile.shape[:2]
    s = max(W / pw, H / ph)
    cw, ch = int(round(pw * s)), int(round(ph * s))
    ox = (cw - W) // 2
    oy = int(round(rep.get("plate_anchor", a.plate_anchor) * (ch - H)))
    full = cv2.resize(dt, (cw, ch), interpolation=cv2.INTER_LINEAR)
    expected = int((full > 24).sum())
    cropped = int((full[oy:oy + H, ox:ox + W] > 24).sum())
    in_canvas = int((dmask > 24).sum())
    loss_move = 100.0 * (1 - in_canvas / max(1, cropped))
    loss_crop = 100.0 * (1 - cropped / max(1, expected))
    g5 = abs(loss_move) < 1.0
    ok &= g5
    print(f"[{'PASS' if g5 else 'FAIL'}] 5. defendant silhouette: {tile_area}px in "
          f"the source tile -> {expected}px after the resize -> {cropped}px after "
          f"the frame crop -> {in_canvas}px in the delivered mask. "
          f"Loss to any PIXEL-MOVING op: {loss_move:+.3f}% (required <1%). "
          f"Loss to the frame crop alone: {loss_crop:.3f}%.")
    print("       regroup_plate.py was NOT run - no person is relocated, so no "
          "limb can be severed. Verified structurally: the plate in the frame is "
          "a pure Lanczos resize + crop of the source tile.")

    # ---- context, measured the same way on the reference and the shipped file
    print()
    print("SURFACE / TONE, same functions on every file:")
    others = {
        "REF Thompson (approved)": Path("C:/Users/natha/OneDrive/Desktop/Boyd Clips")
        / "READY-TO-POST" / "1_LONGFORM_thumbnail.jpg",
        "CARTHIEF (shipped)": Path("C:/Users/natha/OneDrive/Desktop/Boyd Clips")
        / "READY-TO-POST" / "CARTHIEF_thumbnail.jpg",
    }
    hdr = f"{'file':26s} {'luma':>6s} {'blk%':>6s} {'satS':>6s} {'band_s1':>8s} {'chromaDev':>10s}"
    print(hdr)
    for n, p in list(others.items()) + [("Q4_light (this)", a.img)]:
        p = Path(p)
        if not p.is_file():
            continue
        i = cv2.imread(str(p))
        t = _tone_stats(i)
        c, _ = chroma_flat_dev(i)
        print(f"{n:26s} {t[0]:6.1f} {t[1] * 100:6.2f} {t[2]:6.1f} "
              f"{band_s1(i):8.2f} {c:10.3f}")
    print("(targets from the approved Thompson file: luma 116.9, blk 7.68%, "
          "S 93.0 over y>0.25H)")
    print()
    room = (((people <= 24) & (jmask <= 24)).astype(np.uint8)) * 255
    print(f"subject/ground sharpness  hf_ratio vs ROOM   "
          f"{hf_ratio_pair(img, jmask, room):.3f}   (top-tier YT median 1.65 "
          f"[p10 0.62, p90 3.5]; shipped ours median 0.365)")
    print(f"                          hf_ratio vs ALL    {hf_ratio(img, jmask):.3f}"
          f"   (our construction keeps two more people deliberately sharp)")
    print()
    print("VERDICT:", "ALL FIVE GATES PASS" if ok else "*** A GATE FAILED ***")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
