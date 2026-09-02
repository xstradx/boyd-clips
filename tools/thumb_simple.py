# -*- coding: utf-8 -*-
"""A thumbnail the simple way: the right frame, cropped, with words on it.

Nathan, 2026-08-31: "maybe use logic to fix root problems that we maybe have
over complicated???"

THE CASE FOR THIS FILE, entirely from measurements taken today.

  1. Audit the Court's thumbnails - the channel covering the SAME judge, whose
     top video has 1.2M views - are raw frames with a caption. No cut-outs, no
     compositing, no restoration. Measured across their 12: one text band,
     ink covering 5-10% of frame.

  2. No image feature predicts performance. 126 features, 231 winners vs 259
     losers, own-channel outlier scores, FDR corrected: nothing cleared effect
     size. The elaborate composite is not measurably beating a plain frame.

  3. thumb.py is ~950 lines and needs roughly twenty hand-tuned numbers per
     case - judge_crop, plate_crop, def_c, jud_c, plate choice, blur, face
     target. Every one of them is a place a build can go wrong, and today they
     produced: a face cropped off the frame edge, a burned-in station label, a
     duplicate person, four consecutive gate-A failures, and one regression I
     introduced myself trying to fix the placement.

So this is the control arm. Same expression-picked frame, same headline, no
compositing at all. If it looks comparable, the pipeline's complexity is not
earning its keep and can be retired for most cases. If the composite is clearly
better, THAT is worth knowing too - and then the complexity has evidence behind
it for the first time.

WHAT IT DELIBERATELY KEEPS
  * expression.py picks the frame - the one stage that changes WHICH face the
    viewer sees, and the one Nathan has asked for three times.
  * The house type: Anton, white with a yellow accent, heavy stroke.
  * The 168px sidebar as the thing being judged.

WHAT IT DELIBERATELY DROPS
  HYPIR, BiRefNet, the harvested plate, rim light, light wrap, grain, the look
  pass, and every per-case placement number.
"""
import os
import subprocess
import sys
import tempfile

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720
ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
FONTS = os.path.join(ROOT, "assets", "fonts")
YELLOW = (254, 251, 3)


def grab(video, t, out):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", video,
                    "-frames:v", "1", out], check=True)
    return cv2.imread(out)


def crop_to_face(bgr, face_frac=0.30, subj_x=0.42):
    """One 16:9 crop that puts the face at `face_frac` of frame height.

    This replaces judge_crop + plate_crop + def_c + jud_c + face_h. Those five
    hand-tuned numbers exist to answer one question - how big and where - and
    the answer is computable from the face box.
    """
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import expression as X
    faces = X.blendshapes(bgr)
    h0, w0 = bgr.shape[:2]
    if not faces:
        k = min(w0 / 16.0, h0 / 9.0)
        cw, ch = int(16 * k), int(9 * k)
        return bgr[(h0 - ch) // 2:(h0 - ch) // 2 + ch,
                   (w0 - cw) // 2:(w0 - cw) // 2 + cw], None
    f = max(faces, key=lambda z: z["box"][2] * z["box"][3])
    fx, fy, fw, fh = f["box"]
    want_h = fh / face_frac                      # crop height that lands the target
    ch = int(min(h0, max(120, want_h)))
    cw = int(ch * 16 / 9)
    if cw > w0:
        cw, ch = w0, int(w0 * 9 / 16)
    fcx, fcy = fx + fw / 2, fy + fh / 2
    x0 = int(np.clip(fcx - cw * subj_x, 0, w0 - cw))
    y0 = int(np.clip(fcy - ch * 0.42, 0, h0 - ch))   # eyes in the upper third
    return bgr[y0:y0 + ch, x0:x0 + cw], (fx - x0, fy - y0, fw, fh)


def draw(bgr, white, yellow_txt, cap=112):
    img = Image.fromarray(cv2.cvtColor(cv2.resize(bgr, (W, H),
                                                  interpolation=cv2.INTER_LANCZOS4),
                                       cv2.COLOR_BGR2RGB))
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(os.path.join(FONTS, "Anton-Regular.ttf"), cap)
    line = f"{white} {yellow_txt}".strip()
    while d.textlength(line, font=f) > W * 0.94 and cap > 48:
        cap -= 2
        f = ImageFont.truetype(os.path.join(FONTS, "Anton-Regular.ttf"), cap)
    x, y = int(W * 0.03), int(H * 0.045)
    wl = d.textlength(white + " ", font=f)
    for txt, col, off in ((white, (255, 255, 255), 0),
                          (yellow_txt, YELLOW, wl)):
        d.text((x + off, y), txt, font=f, fill=col,
               stroke_width=max(6, cap // 13), stroke_fill=(0, 0, 0))
    return cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)


def build(video, headline_white, headline_yellow, out, window=None, side=None):
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import expression as X
    headline = f"{headline_white} {headline_yellow}"
    prof = X.profile_for(headline)
    with tempfile.TemporaryDirectory() as d:
        if window:
            best, _ = X.search(video, window[0], window[1], prof, side=side)
            if not best:
                raise RuntimeError("no usable face in the window")
            t = best["t"]
            print(f"  expression {prof!r}: t={t:.1f}s expr={best['expr']:.4f} "
                  f"(floor {X.FLOOR})")
        else:
            t = 0.0
        fr = grab(video, t, os.path.join(d, "f.png"))
        if side == "right":
            fr = fr[:, fr.shape[1] // 2:]
        elif side == "left":
            fr = fr[:, :fr.shape[1] // 2]
        cropped, _ = crop_to_face(fr)
        final = draw(cropped, headline_white, headline_yellow)
    cv2.imwrite(out, final, [cv2.IMWRITE_JPEG_QUALITY, 95,
                             cv2.IMWRITE_JPEG_SAMPLING_FACTOR,
                             cv2.IMWRITE_JPEG_SAMPLING_FACTOR_444])
    return out


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) < 4:
        print("usage: thumb_simple.py VIDEO WHITE YELLOW OUT "
              "[--window T0 T1] [--side left|right]")
        sys.exit(2)
    win = None
    if "--window" in a:
        i = a.index("--window")
        win = (float(a[i + 1]), float(a[i + 2]))
    side = a[a.index("--side") + 1] if "--side" in a else None
    print(build(a[0], a[1], a[2], a[3], window=win, side=side))
