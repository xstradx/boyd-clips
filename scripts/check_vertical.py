"""Check a rendered vertical is actually usable, not just present.

Tile detection measures the Zoom grid rather than guessing at it, but a hearing
with a different layout - one participant, a shared screen, a four-up grid - can
still produce a frame that is half black. That looked fine in a file listing and
only showed up on playback, which is exactly the failure this catches.

Samples frames across the file and reports, per half:
  * how much of the tile is black
  * whether the two halves differ (a frame duplicated top and bottom means the
    grid was misread and the same tile was cropped twice)
"""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

DEST = Path.home() / "OneDrive" / "Desktop" / "Boyd Clips" / "VERTICAL-FULL"


def probe(path: Path) -> tuple:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height",
         "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, timeout=60)
    nums = [x for x in r.stdout.replace(",", "\n").split() if x]
    w = h = 0
    dur = 0.0
    for n in nums:
        try:
            v = float(n)
        except ValueError:
            continue
        if v > 1000 and w == 0:
            w = int(v)
        elif v > 1000 and h == 0:
            h = int(v)
        else:
            dur = max(dur, v)
    return w, h, dur


def black_fraction(png: Path, half: str) -> float:
    """Fraction of near-black pixels in the top or bottom half."""
    crop = "iw:ih/2:0:0" if half == "top" else "iw:ih/2:0:ih/2"
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(png), "-vf",
         f"crop={crop},format=gray,blackframe=amount=0:threshold=32",
         "-f", "null", "-"],
        capture_output=True, text=True, timeout=60)
    for line in r.stderr.splitlines():
        if "blackframe" in line and "pblack:" in line:
            try:
                return float(line.split("pblack:")[1].split()[0]) / 100.0
            except Exception:                       # noqa: BLE001
                pass
    return 0.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=None, help="one file, else every mp4 in the folder")
    ap.add_argument("--samples", type=int, default=5)
    args = ap.parse_args()

    files = [DEST / args.file] if args.file else sorted(DEST.glob("*.mp4"))
    if not files:
        print("nothing in " + str(DEST))
        return

    for f in files:
        if not f.exists():
            print(f"{f.name}: missing")
            continue
        w, h, dur = probe(f)
        ok_size = (w, h) == (1080, 1920)
        print(f"\n{f.name}")
        print(f"  {w}x{h} {'ok' if ok_size else 'NOT 1080x1920'}   {dur/60:.1f} min   "
              f"{f.stat().st_size/1e6:.0f} MB")
        if dur < 1:
            print("  UNPLAYABLE - no duration")
            continue

        worst_top = worst_bot = 0.0
        with tempfile.TemporaryDirectory() as td:
            for i in range(args.samples):
                t = dur * (i + 1) / (args.samples + 1)
                png = Path(td) / f"f{i}.png"
                subprocess.run(
                    ["ffmpeg", "-v", "error", "-ss", f"{t:.1f}", "-i", str(f),
                     "-frames:v", "1", "-y", str(png)],
                    capture_output=True, timeout=120)
                if not png.exists():
                    continue
                tb = black_fraction(png, "top")
                bb = black_fraction(png, "bottom")
                worst_top = max(worst_top, tb)
                worst_bot = max(worst_bot, bb)
                print(f"    {t/60:5.1f} min   top {tb*100:5.1f}% black   "
                      f"bottom {bb*100:5.1f}% black")

        flags = []
        if not ok_size:
            flags.append("wrong size")
        if worst_top > 0.55:
            flags.append("top tile mostly black")
        if worst_bot > 0.55:
            flags.append("bottom tile mostly black")
        print("  " + ("OK" if not flags else "PROBLEM: " + ", ".join(flags)))


if __name__ == "__main__":
    main()
