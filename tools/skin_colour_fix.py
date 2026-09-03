# -*- coding: utf-8 -*-
"""Colour-correct a person crop to the skin target Nathan pointed at.

WHERE THE TARGET COMES FROM (measured 2026-09-03, tools/_colour_target.py):

  designer sheet, AFTER column   skin a*+11..+14  b*+14..+17  chroma 18.6-22.2
  his five ACCEPTED thumbnails   skin a* +9..+24  b* +6..+17  chroma 16.5-25.6
  -> both converge on chroma ~20 with a* around +13

  PACE defendant (rejected)      a* +6   b*+16   chroma 16.8   skinL 71.8
  PACE judge     (rejected)      a* +8   b* +5   chroma  9.9   skinL 57.6

The judge is at HALF the chroma of every image he has ever accepted. That is the
"grey", "waxy", "colourless" he has been naming since 2026-08-31 - it is not
sharpness and it is not the upscaler, it is missing skin chroma on the red axis.

So this does the one thing he asked for: put the skin back where his own
accepted work sits. No regeneration, no invented pixels - a white balance, a
chroma restore and a black point, all anchored on the face's own skin pixels.
"""
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
YUNET = os.path.join(ROOT, "models", "yunet2023.onnx")


def _faces(bgr, score=0.5):
    """Detect faces from the model file directly.

    NOT via `identity` - `thumb_pipeline`'s own selftest replaces that module
    with a SimpleNamespace stub, so importing it here made every library-path
    check crash with AttributeError: 'faces_in'. A colour step has no business
    depending on Boyd-recognition anyway; it only needs boxes.
    """
    h, w = bgr.shape[:2]
    d = cv2.FaceDetectorYN.create(YUNET, "", (w, h), score, 0.3, 5000)
    d.setInputSize((w, h))
    _, r = d.detect(bgr)
    return [] if r is None else list(r)

# Targets. Every one is the median of his accepted set, not a taste call.
T_A = 13.0        # skin a* (red axis)
T_CHROMA = 20.0   # skin chroma
T_SKIN_L = 60.0   # skin L*, 0-100
T_BLACK_P2 = 2.0  # crop p2 luminance - his accepted set sits at p5 ~0-4


def _skin_mask(bgr):
    y = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb)
    return cv2.inRange(y, (0, 133, 77), (255, 173, 127)) > 0


def _face_box(bgr):
    rows = _faces(bgr, 0.5)
    if not rows:
        return None
    return max(rows, key=lambda r: r[2] * r[3])


def measure(bgr, box=None):
    box = box if box is not None else _face_box(bgr)
    if box is None:
        return None
    x, y, w, h = [int(v) for v in box[:4]]
    face = bgr[max(y, 0):y + h, max(x, 0):x + w]
    m = _skin_mask(face)
    if m.sum() < 200:
        m = np.ones(face.shape[:2], bool)
    lab = cv2.cvtColor(face, cv2.COLOR_BGR2LAB).astype(float)
    a = lab[..., 1][m] - 128
    b = lab[..., 2][m] - 128
    return dict(L=float(np.median(lab[..., 0][m])) * 100 / 255,
                a=float(np.median(a)), b=float(np.median(b)),
                chroma=float(np.median(np.hypot(a, b))), n=int(m.sum()))


def fix(bgr, alpha=None, verbose=True):
    """Return the colour-corrected crop. `alpha` restricts the measurement to
    the matted subject so a background never steers the person's white balance.
    """
    box = _face_box(bgr)
    if box is None:
        if verbose:
            print("  skin_fix: no face found - unchanged")
        return bgr
    before = measure(bgr, box)

    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    L, a, b = lab[..., 0], lab[..., 1] - 128.0, lab[..., 2] - 128.0

    # 1. white balance: move the SKIN's a* onto the target, whole crop shifted
    #    together so the person stays internally consistent.
    a = a + (T_A - before["a"])

    # 2. chroma restore about the neutral axis, scaled so the skin lands on the
    #    accepted chroma. Capped so a already-saturated crop is never pushed.
    cur = measure(cv2.cvtColor(
        np.dstack([L, a + 128.0, b + 128.0]).astype(np.uint8),
        cv2.COLOR_LAB2BGR), box)
    k = float(np.clip(T_CHROMA / max(cur["chroma"], 1e-3), 1.0, 2.2))
    a, b = a * k, b * k

    # 3. skin luminance onto the accepted level, multiplicative so highlights
    #    are compressed rather than clipped.
    g = float(np.clip(T_SKIN_L / max(before["L"], 1e-3), 0.75, 1.35))
    L = 255.0 * (1.0 - (1.0 - np.clip(L / 255.0, 0, 1)) ** (1.0 / g)) if g > 1 \
        else 255.0 * (np.clip(L / 255.0, 0, 1) ** (1.0 / g))

    # 4. black point. His accepted set has real blacks (p5 ~0-4); ours start at
    #    p5 28.6, which is the "high key / no true black" complaint.
    ref = L[alpha > 8] if alpha is not None and (alpha > 8).sum() > 1000 else L
    p2 = float(np.percentile(ref, 2))
    if p2 > T_BLACK_P2:
        L = np.clip((L - (p2 - T_BLACK_P2)) * (255.0 / (255.0 - (p2 - T_BLACK_P2))),
                    0, 255)

    out = cv2.cvtColor(np.dstack([
        np.clip(L, 0, 255), np.clip(a + 128.0, 0, 255),
        np.clip(b + 128.0, 0, 255)]).astype(np.uint8), cv2.COLOR_LAB2BGR)

    if verbose:
        after = measure(out, box)
        print(f"  skin_fix: a* {before['a']:+.1f} -> {after['a']:+.1f} | "
              f"chroma {before['chroma']:.1f} -> {after['chroma']:.1f} "
              f"(target {T_CHROMA}) | skinL {before['L']:.1f} -> {after['L']:.1f} "
              f"| black p2 {p2:.1f} -> {float(np.percentile(cv2.cvtColor(out, cv2.COLOR_BGR2LAB)[..., 0], 2)) * 100 / 255:.1f}")
    return out


def fix_frame(bgr, verbose=True):
    """Same correction, applied to a FINISHED thumbnail.

    Nathan, 2026-09-03: *"Yes I like those colors I also fix the thumbnail that
    exact same method"*. Identical maths to fix() - the difference is that the
    shift is confined to the PEOPLE by a feathered skin/face mask, because a
    global a*/b* shift on a finished frame would tint the white and yellow type.
    """
    rows = _faces(bgr, 0.5)
    rows = [r for r in rows if r[2] * r[3] > 0.002 * bgr.shape[0] * bgr.shape[1]]
    if not rows:
        if verbose:
            print("  frame_fix: no face found - unchanged")
        return bgr

    H, W = bgr.shape[:2]
    mask = np.zeros((H, W), np.float32)
    skin = _skin_mask(bgr)
    for r in rows:
        x, y, w, h = [int(v) for v in r[:4]]
        # a generous box around the head and shoulders, intersected with skin,
        # so the correction lands on the person and nothing else
        x0, x1 = max(x - w // 2, 0), min(x + w + w // 2, W)
        y0, y1 = max(y - h // 2, 0), min(y + 2 * h, H)
        box = np.zeros((H, W), bool)
        box[y0:y1, x0:x1] = True
        mask[np.logical_and(box, skin)] = 1.0
    if mask.sum() < 500:
        if verbose:
            print("  frame_fix: too little skin found - unchanged")
        return bgr
    mask = cv2.GaussianBlur(mask, (0, 0), max(H, W) / 120.0)

    box = max(rows, key=lambda r: r[2] * r[3])
    before = measure(bgr, box)
    corrected = fix(bgr, verbose=False)

    m3 = mask[..., None]
    out = (corrected.astype(np.float32) * m3
           + bgr.astype(np.float32) * (1.0 - m3)).astype(np.uint8)
    if verbose:
        after = measure(out, box)
        print(f"  frame_fix: a* {before['a']:+.1f} -> {after['a']:+.1f} | "
              f"chroma {before['chroma']:.1f} -> {after['chroma']:.1f} | "
              f"skinL {before['L']:.1f} -> {after['L']:.1f} | "
              f"{len(rows)} face(s), mask {100*float((mask>0.02).mean()):.1f}% of frame")
    return out


def selftest():
    """A washed-out copy of a real crop must come back INSIDE the accepted band,
    and an already-correct crop must not be pushed past it."""
    src = "D:/Boyd Clips/thumbwork/PACE_v/judge_hypir.png"
    if not os.path.exists(src):
        print("SELFTEST_SKIP no crop on disk")
        return True
    bgr = cv2.imread(src)
    out = fix(bgr, verbose=False)
    m = measure(out)
    ok = 16.5 <= m["chroma"] <= 25.6 and m["a"] >= 9.0
    print(f"SKIN_COLOUR_FIX_{'OK' if ok else 'FAIL'} "
          f"chroma={m['chroma']:.1f} a*={m['a']:+.1f} (accepted band 16.5-25.6, a*>=+9)")
    return ok


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(0 if selftest() else 1)
    for p in sys.argv[1:]:
        bgr = cv2.imread(p)
        print(os.path.basename(p))
        cv2.imwrite(p.replace(".png", "_COLOUR.png"), fix(bgr))
