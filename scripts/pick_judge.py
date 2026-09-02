"""Find a Judge Boyd frame whose skin has real colour in it.

SANCHEZ refused on all eight plate frames with the same reason:

    PALE her skin a* 11.7 < 13 (approved 17.6/18.3, rejected 9.0/9.7)

a* is the green-to-red axis in CIE Lab, so it measures how much red is in her
skin independent of how bright the shot is - which is the whole point, because
Nathan's complaint ("boyd still looks so bright and pale") survived every
brightness correction I tried. The threshold is calibrated on his own verdicts:
the two thumbnails he approved sit at 17.6 and 18.3, the two he rejected at 9.0
and 9.7.

The value barely moved across eight different PLATE frames because the plate is
not the variable - HER tile is. Her Zoom camera exposes for whatever is in her
room at that moment, so some frames of the same hearing have far more colour in
her face than others. So the judge frame gets chosen the same way the plate
frame does: by measuring, not by inheriting a timestamp picked for what she said.

Sharpness is a hard gate rather than a weight - a blurred frame is unusable
however good the colour is.

RANKED, NOT PICKED. Nathan's rule R7 is that her eyes must be LEVEL and
DIRECTED, never cast down, and that a hand mid-gesture adds drama while a hand
resting on her chin does not. Three automated gaze metrics all failed to
reproduce that judgement, so this prints a table and writes a contact sheet for
him to choose from; it only guarantees the candidates have colour and focus.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageStat


def grab(src: Path, t: float, crop: str, dst: Path) -> bool:
    subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(src),
         "-frames:v", "1", "-vf", f"crop={crop}", "-q:v", "2", str(dst), "-y"],
        capture_output=True, timeout=180)
    return dst.is_file()


def skin_lab(img: Image.Image):
    """Mean Lab of the skin pixels. Returns (L, a, b, fraction_of_frame)."""
    rgb = np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0
    hsv = np.asarray(img.convert("HSV"), dtype=np.float32)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    skin = ((h > 3) & (h < 34)) & (s > 28) & (s < 170) & (v > 60)
    if skin.sum() < 400:
        return None
    # sRGB -> linear -> XYZ (D65) -> Lab
    c = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    M = np.array([[0.4124, 0.3576, 0.1805],
                  [0.2126, 0.7152, 0.0722],
                  [0.0193, 0.1192, 0.9505]], dtype=np.float32)
    xyz = c.reshape(-1, 3) @ M.T
    white = np.array([0.95047, 1.0, 1.08883], dtype=np.float32)
    t = xyz / white
    d = 6.0 / 29.0
    f = np.where(t > d ** 3, np.cbrt(t), t / (3 * d * d) + 4.0 / 29.0)
    L = 116 * f[:, 1] - 16
    a = 500 * (f[:, 0] - f[:, 1])
    b = 200 * (f[:, 1] - f[:, 2])
    m = skin.reshape(-1)
    return float(L[m].mean()), float(a[m].mean()), float(b[m].mean()), float(skin.mean())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, type=Path)
    ap.add_argument("--offset", type=float, required=True)
    ap.add_argument("--from", dest="t0", type=float, required=True)
    ap.add_argument("--to", dest="t1", type=float, required=True)
    ap.add_argument("--crop", required=True, help="the JUDGE tile W:H:X:Y")
    ap.add_argument("--step", type=float, default=5.0)
    ap.add_argument("--min-a", type=float, default=13.0,
                    help="the builder's pale gate. approved 17.6/18.3, "
                         "rejected 9.0/9.7")
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--sheet", type=Path, default=None)
    ap.add_argument("--json", dest="jsonout", type=Path, default=None)
    a = ap.parse_args()

    rows = []
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        t, n = a.t0, 0
        while t <= a.t1:
            f = td / f"{n}.jpg"
            n += 1
            tt, t = t, t + a.step
            if not grab(a.source, tt - a.offset, a.crop, f):
                continue
            img = Image.open(f).convert("RGB")
            lab = skin_lab(img)
            if lab is None:
                continue
            L, aa, bb, frac = lab
            sharp = ImageStat.Stat(
                img.convert("L").filter(ImageFilter.FIND_EDGES)).stddev[0]
            rows.append({"t": tt, "L": L, "a": aa, "b": bb, "skin": frac,
                         "sharp": sharp, "img": img.copy()})

    if not rows:
        print("no usable frames")
        return 1

    med = sorted(r["sharp"] for r in rows)[len(rows) // 2]
    keep = [r for r in rows if r["sharp"] >= med * 0.9] or rows
    keep.sort(key=lambda r: -r["a"])

    print(f"{len(rows)} frames measured, {len(rows) - len(keep)} rejected as soft\n")
    print(f"  {'src':>8}  {'skin a*':>8}  {'skin L':>7}  {'skin %':>7}  {'sharp':>6}  gate")
    for r in keep[: a.top]:
        ok = "PASS" if r["a"] >= a.min_a else "fail"
        print(f"  {r['t']:8.1f}  {r['a']:8.2f}  {r['L']:7.1f}  "
              f"{r['skin']*100:6.1f}%  {r['sharp']:6.1f}  {ok}")
    passing = [r for r in keep if r["a"] >= a.min_a]
    print(f"\n  {len(passing)} of {len(keep)} frames clear the a* >= {a.min_a} gate")
    if passing:
        print(f"  best: src {passing[0]['t']:.1f} at a* {passing[0]['a']:.2f}")
    else:
        print("  NONE clear it - her camera never gives more colour than "
              f"a* {keep[0]['a']:.2f} in this hearing")

    if a.jsonout:
        a.jsonout.parent.mkdir(parents=True, exist_ok=True)
        a.jsonout.write_text(json.dumps(
            {"crop": a.crop, "min_a": a.min_a,
             "candidates": [{"t": r["t"], "a": r["a"], "L": r["L"],
                             "sharp": r["sharp"]} for r in keep]}, indent=1))
        print(f"  -> {a.jsonout}")

    if a.sheet:
        from PIL import ImageDraw, ImageFont
        try:
            F = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 16)
        except Exception:
            F = ImageFont.load_default()
        show = keep[: min(a.top, 12)]
        tw = 300
        th = int(tw * show[0]["img"].height / show[0]["img"].width)
        cols = 4
        nrow = (len(show) + cols - 1) // cols
        sheet = Image.new("RGB", (tw * cols, (th + 26) * nrow + 26), (12, 12, 16))
        d = ImageDraw.Draw(sheet)
        d.text((6, 5), "JUDGE BOYD candidates - ranked by skin colour (a*). "
                       "Her eyes must be LEVEL and DIRECTED - your call.",
               font=F, fill=(255, 225, 80))
        for i, r in enumerate(show):
            x, y = tw * (i % cols), 26 + (th + 26) * (i // cols)
            sheet.paste(r["img"].resize((tw, th)), (x, y))
            d.text((x + 4, y + th + 4),
                   f"src {r['t']:.0f}   a* {r['a']:.1f}   "
                   f"{'PASS' if r['a'] >= a.min_a else 'fail'}",
                   font=F, fill=(150, 255, 170) if r["a"] >= a.min_a
                   else (200, 140, 130))
        a.sheet.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(a.sheet)
        print(f"  -> {a.sheet}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
