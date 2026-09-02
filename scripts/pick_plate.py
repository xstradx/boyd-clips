"""Find a plate frame whose right side is free for the judge cut-out.

Nathan on the first OFFERUP build, 2026-08-29: "it looks weird how his lawyer ir
right behind judge boyd".

Three attempts to fix that in the layout solver all failed, and the reason is
structural rather than parametric: at src 10884 the attorney stands exactly where
Judge Boyd has to be composited, so her coverage of his head sat at 0.55 - the
precise half-peeking state - for every candidate scale, shift and offset. A
solver cannot compose its way out of a frame that has no room in it.

So the frame is chosen for the room it has, the same way `pick_reaction.py`
chooses the defendant's frame for his expression. For each candidate time this
measures, from the person matte:

  * how much of the RIGHT PORTION (where the cut-out lands) is occupied by
    somebody other than the defendant - lower is better
  * that the defendant is present and reasonably large, so the frame is usable
  * sharpness, because a blurred frame is unusable however clear the right side

It prints a ranked table rather than picking silently, because which frame reads
best is still Nathan's eye - this only guarantees the candidates have room.
"""
from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import scipy.ndimage as nd
from PIL import Image, ImageFilter, ImageStat


def grab(src: Path, t: float, crop: str, dst: Path) -> bool:
    subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(src),
         "-frames:v", "1", "-vf", f"crop={crop}", "-q:v", "2", str(dst), "-y"],
        capture_output=True, timeout=180)
    return dst.is_file()


def scrub_mask(img: Image.Image) -> np.ndarray:
    hsv = np.asarray(img.convert("HSV"), dtype=np.uint8)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    return ((((h > 5) & (h < 32)) | ((h > 125) & (h < 165)))
            & (s > 110) & (v > 80))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, type=Path)
    ap.add_argument("--offset", type=float, required=True)
    ap.add_argument("--from", dest="t0", type=float, required=True)
    ap.add_argument("--to", dest="t1", type=float, required=True)
    ap.add_argument("--crop", required=True, help="the PLATE tile W:H:X:Y")
    ap.add_argument("--step", type=float, default=8.0)
    ap.add_argument("--right", type=float, default=0.52,
                    help="fraction of width from the right the judge occupies")
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--sheet", type=Path, default=None)
    ap.add_argument("--json", dest="jsonout", type=Path, default=None,
                    help="write the whole ranked table here. make_thumbnail_"
                         "auto.py reads it so that when the builder REFUSES a "
                         "frame it can move to the next candidate instead of "
                         "shipping a shrunken judge.")
    a = ap.parse_args()

    from rembg import new_session, remove
    sess = new_session("birefnet-portrait")

    rows = []
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        t = a.t0
        n = 0
        while t <= a.t1:
            f = td / f"{n}.jpg"
            n += 1
            tt, t = t, t + a.step
            if not grab(a.source, tt - a.offset, a.crop, f):
                continue
            img = Image.open(f).convert("RGB")
            W, H = img.size
            sharp = ImageStat.Stat(
                img.convert("L").filter(ImageFilter.FIND_EDGES)).stddev[0]
            alpha = np.asarray(remove(img.convert("RGBA"), session=sess)
                               .getchannel("A"), dtype=np.uint8)
            people = alpha > 24
            lbl, k = nd.label(people)
            if k == 0:
                continue
            sm = scrub_mask(img)
            counts = nd.sum(sm, lbl, range(1, k + 1))
            him = int(np.argmax(counts)) + 1
            him_px = int((lbl == him).sum())
            if him_px < W * H * 0.03:
                continue                       # defendant not really present
            x0 = int(W * (1.0 - a.right))
            others = people & (lbl != him)
            occ = float(others[:, x0:].mean())
            rows.append({"t": tt, "occ": occ, "sharp": sharp,
                         "him": him_px / (W * H), "img": img.copy()})

    if not rows:
        print("no usable frames")
        return 1

    med = sorted(r["sharp"] for r in rows)[len(rows) // 2]
    keep = [r for r in rows if r["sharp"] >= med * 0.85] or rows
    keep.sort(key=lambda r: r["occ"])

    print(f"{len(rows)} frames measured, {len(rows) - len(keep)} rejected as soft\n")
    print(f"  {'src time':>9}  {'right-side occupied':>19}  {'defendant':>9}  {'sharp':>6}")
    for r in keep[: a.top]:
        print(f"  {r['t']:9.1f}  {r['occ'] * 100:18.1f}%  {r['him'] * 100:8.1f}%  {r['sharp']:6.1f}")
    best = keep[0]
    print(f"\n  clearest right side: src {best['t']:.1f} "
          f"({best['occ'] * 100:.1f}% occupied by someone other than him)")

    if a.jsonout:
        import json
        a.jsonout.parent.mkdir(parents=True, exist_ok=True)
        a.jsonout.write_text(json.dumps(
            {"crop": a.crop, "step": a.step,
             "candidates": [{"t": r["t"], "occ": r["occ"], "sharp": r["sharp"],
                             "him": r["him"]} for r in keep]}, indent=1))
        print(f"  -> {a.jsonout}")

    if a.sheet:
        from PIL import ImageDraw, ImageFont
        try:
            F = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 16)
        except Exception:
            F = ImageFont.load_default()
        show = keep[: min(a.top, 12)]
        tw, th = 300, int(300 * show[0]["img"].height / show[0]["img"].width)
        cols = 4
        rowsn = (len(show) + cols - 1) // cols
        sheet = Image.new("RGB", (tw * cols, (th + 26) * rowsn + 24), (12, 12, 16))
        d = ImageDraw.Draw(sheet)
        d.text((6, 5), "PLATE candidates - ranked by how CLEAR the right side is",
               font=F, fill=(255, 225, 80))
        for i, r in enumerate(show):
            x, y = tw * (i % cols), 24 + (th + 26) * (i // cols)
            sheet.paste(r["img"].resize((tw, th)), (x, y))
            d.text((x + 4, y + th + 4),
                   f"src {r['t']:.0f}   right side {r['occ'] * 100:.0f}% busy",
                   font=F, fill=(170, 170, 185))
        a.sheet.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(a.sheet)
        print(f"  -> {a.sheet}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
