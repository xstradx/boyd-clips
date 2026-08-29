"""Sweep a hearing for the defendant's best REACTION frame.

Nathan, 2026-08-28: "i need you to always make sure you get a good frame of the
defandant like with a good reaction". Standing rule, not a one-off.

Until now the defendant frame was whatever decoded near the hammer line, which
is a timestamp chosen for what the JUDGE said. There is no reason the defendant's
face is doing anything at that instant, and on CARTHIEF it wasn't — he is
flat-neutral in the shipped thumbnail.

Two things are scored, and the split matters because only one of them is a real
measurement:

  SHARPNESS is objective. Edge energy (FIND_EDGES then std-dev) rejects
  motion-blurred frames outright, and on this footage heads move constantly, so
  a large share of frames are unusable. This filter is trustworthy.

  MOTION is a heuristic. A reaction is a CHANGE, so the face region is compared
  against itself half a second earlier; a face mid-expression differs from its
  own baseline more than a static one. It correlates with "something is
  happening" but it cannot tell shocked from mid-blink.

So this tool does NOT pick. It ranks, and lays the top N out as a contact sheet
for Nathan to choose from — the same conclusion reached on 2026-08-28 about
Judge Boyd's frames, where three automated gaze metrics all failed to reproduce
his eye and the contact sheet did. His eye is the instrument; the job here is to
make choosing cheap and to guarantee the candidates are at least in focus.

    python scripts/pick_reaction.py --source work/X/X_h.mp4 --offset 3554 \\
        --from 3574 --to 4628 --crop 620:338:644:190 --out sheet.png
"""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageStat


def grab(src: Path, t: float, crop: str, dst: Path, w: int = 300) -> bool:
    subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(src),
         "-frames:v", "1", "-vf", f"crop={crop},scale={w}:-1", "-q:v", "3",
         str(dst), "-y"], capture_output=True, timeout=120)
    return dst.is_file()


def sharpness(img: Image.Image) -> float:
    return ImageStat.Stat(img.convert("L").filter(ImageFilter.FIND_EDGES)).stddev[0]


def diff(a: Image.Image, b: Image.Image) -> float:
    import numpy as np
    x = np.asarray(a.convert("L"), dtype=float)
    y = np.asarray(b.convert("L"), dtype=float)
    n = min(x.shape[0], y.shape[0]), min(x.shape[1], y.shape[1])
    return float(np.abs(x[:n[0], :n[1]] - y[:n[0], :n[1]]).mean())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, type=Path)
    ap.add_argument("--offset", type=float, required=True,
                    help="source-time of the file's first frame")
    ap.add_argument("--from", dest="t0", type=float, required=True)
    ap.add_argument("--to", dest="t1", type=float, required=True)
    ap.add_argument("--crop", required=True, help="W:H:X:Y of the defendant tile")
    ap.add_argument("--step", type=float, default=3.0)
    ap.add_argument("--top", type=int, default=24)
    ap.add_argument("--cols", type=int, default=8)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--save-dir", default=None, type=Path)
    a = ap.parse_args()

    rows = []
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        t = a.t0
        n = 0
        while t <= a.t1:
            f = td / f"{n}.jpg"
            fp = td / f"{n}_p.jpg"
            if grab(a.source, t - a.offset, a.crop, f) and \
               grab(a.source, t - a.offset - 0.5, a.crop, fp):
                im = Image.open(f).copy()
                imp = Image.open(fp).copy()
                rows.append({"t": t, "sharp": sharpness(im),
                             "motion": diff(im, imp), "img": im})
            t += a.step
            n += 1

        if not rows:
            print("no frames decoded")
            return 1

        # Sharpness is a hard gate, not a weight: a blurred frame is unusable
        # however animated it is. Median keeps roughly the better half.
        med = sorted(r["sharp"] for r in rows)[len(rows) // 2]
        keep = [r for r in rows if r["sharp"] >= med] or rows
        keep.sort(key=lambda r: -r["motion"])
        keep = keep[: a.top]
        keep.sort(key=lambda r: r["t"])

        print(f"{len(rows)} frames sampled, {len(rows) - len([r for r in rows if r['sharp'] >= med])}"
              f" rejected as soft, showing top {len(keep)} by motion")

        tw = keep[0]["img"].width
        th = keep[0]["img"].height
        cols = a.cols
        import math
        nrow = math.ceil(len(keep) / cols)
        sheet = Image.new("RGB", (tw * cols, (th + 24) * nrow + 26), (12, 12, 16))
        d = ImageDraw.Draw(sheet)
        try:
            F = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 17)
        except Exception:
            F = ImageFont.load_default()
        d.text((6, 5), f"DEFENDANT reaction candidates - {a.source.name}",
               font=F, fill=(255, 225, 80))
        for i, r in enumerate(keep):
            x, y = tw * (i % cols), 26 + (th + 24) * (i // cols)
            sheet.paste(r["img"], (x, y))
            d.text((x + 4, y + th + 3),
                   f"src {r['t']:.0f}  m{r['motion']:.1f}", font=F,
                   fill=(170, 170, 185))
            if a.save_dir:
                a.save_dir.mkdir(parents=True, exist_ok=True)
                r["img"].save(a.save_dir / f"{int(r['t'])}.jpg", quality=95)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(a.out)
        print(f"  -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
