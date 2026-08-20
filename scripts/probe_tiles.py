"""Measure the real tile layout of a source frame.

detect_tile_crops assumed a side-by-side 2-up and split at src_w // 2. This
probe makes no such assumption: it averages sampled frames, then finds the
vertical black gutters that separate tiles and reports the segmentation it
actually observes.
"""
import subprocess, sys
from pathlib import Path
import numpy as np


def frames(src: Path, w: int, h: int, n: int = 12):
    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(src)], capture_output=True, text=True).stdout.strip())
    out = []
    for i in range(n):
        t = dur * (i + 0.5) / n
        p = subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(src),
             "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
            capture_output=True)
        if len(p.stdout) == w * h:
            out.append(np.frombuffer(p.stdout, np.uint8).reshape(h, w))
    return out


def runs(mask):
    """[(start, end)] inclusive spans where mask is True."""
    spans, cur = [], None
    for i, on in enumerate(mask):
        if on:
            cur = (i, i) if cur is None else (cur[0], i)
        elif cur:
            spans.append(cur); cur = None
    if cur:
        spans.append(cur)
    return spans


def main(path, floor=8.0, min_tile=64):
    src = Path(path)
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height", "-of", "csv=p=0:s=x", str(src)],
        capture_output=True, text=True).stdout.strip()
    w, h = (int(v) for v in p.split("x"))
    fs = frames(src, w, h)
    if not fs:
        print("no frames"); return
    avg = np.mean(np.stack(fs).astype(np.float32), axis=0)

    print(f"{src.name}  {w}x{h}  {len(fs)} frames averaged")

    col = avg.mean(axis=0)
    tiles = [s for s in runs(col >= floor) if s[1] - s[0] + 1 >= min_tile]
    print(f"\ncolumn luminance floor={floor}  ->  {len(tiles)} horizontal band(s)")
    for i, (x1, x2) in enumerate(tiles):
        band = avg[:, x1:x2 + 1]
        row = band.mean(axis=1)
        vr = [s for s in runs(row >= floor) if s[1] - s[0] + 1 >= min_tile]
        print(f"  band {i}: x {x1:4d}-{x2:4d}  w={x2-x1+1:4d}"
              f"   vertical content: {[(a, b, b-a+1) for a, b in vr]}")

    print(f"\nmidpoint split would cut at x={w//2}")
    for i, (x1, x2) in enumerate(tiles):
        if x1 < w // 2 < x2:
            print(f"  !! band {i} (x {x1}-{x2}) is CUT IN HALF by the midpoint split")


if __name__ == "__main__":
    main(*sys.argv[1:])
