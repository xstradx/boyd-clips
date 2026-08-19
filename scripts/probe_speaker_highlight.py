"""Is Zoom's active-speaker highlight visible on this docket's tiles?

If it is, speaker turns are already in the pixels and no audio diarisation is
needed: the tile Zoom is outlining IS the person talking, frame by frame, with
no model, no GPU and no gated weights.

`detect_tile_crops` already knows the highlight exists - it insets every tile
by a few pixels specifically to crop it off, describing it as "a bright green
rectangle drawn just inside the tile border". This checks whether it is strong
enough to classify on.

Method: sample frames, and for each tile measure a thin band just inside the
tile border against the tile's own interior. A highlighted tile should show a
clear excess of green-dominant, saturated pixels in the band.

    python scripts/probe_speaker_highlight.py <video_id> [n_samples]
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PIL import Image                                            # noqa: E402

from boydclips import render                                     # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BAND = 6          # px band just inside the tile edge
PAD = 10          # start the band this far in, to skip the frame's own border


def band_score(img: Image.Image, box: tuple[int, int, int, int]) -> float:
    """Green-dominance of a thin ring just inside `box`, 0..1.

    Green-DOMINANT rather than simply bright: the courtroom is full of bright
    pixels, but very few where G materially exceeds both R and B. That is what
    makes the highlight separable from wood panelling and overhead lights.
    """
    x0, y0, x1, y1 = box
    ring = []
    for a, b, c, d in (
        (x0 + PAD, y0 + PAD, x1 - PAD, y0 + PAD + BAND),          # top
        (x0 + PAD, y1 - PAD - BAND, x1 - PAD, y1 - PAD),          # bottom
        (x0 + PAD, y0 + PAD, x0 + PAD + BAND, y1 - PAD),          # left
        (x1 - PAD - BAND, y0 + PAD, x1 - PAD, y1 - PAD),          # right
    ):
        if c <= a or d <= b:
            continue
        ring.append(img.crop((a, b, c, d)))
    if not ring:
        return 0.0
    hits = total = 0
    for patch in ring:
        for r, g, bl in patch.convert("RGB").getdata():
            total += 1
            if g > r + 25 and g > bl + 25 and g > 90:
                hits += 1
    return hits / float(total or 1)


def main() -> int:
    video_id = sys.argv[1] if len(sys.argv) > 1 else "RzjGikNbHMA"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 12

    work = ROOT / "work" / video_id
    srcs = sorted(work.glob(f"{video_id}_*-*.mp4"))
    if not srcs:
        print(f"no cached section in {work}")
        return 1
    source = srcs[0]

    tiles = render.detect_tile_crops(source, inset=0)
    if not tiles:
        print("tiles not measurable")
        return 1

    def to_box(crop: str) -> tuple[int, int, int, int]:
        w, h, x, y = (int(v) for v in crop.split("=")[1].split(":"))
        return (x, y, x + w, y + h)

    left, right = to_box(tiles[0]), to_box(tiles[1])
    dur = render.probe_duration(source)
    print(f"{source.name}  {dur:.0f}s")
    print(f"  left  {tiles[0]}\n  right {tiles[1]}\n")
    print(f"{'t':>7}  {'left':>7}  {'right':>7}   verdict")

    tmp = work / "_hl.png"
    diffs = []
    for i in range(n):
        t = dur * (i + 0.5) / n
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(source),
             "-frames:v", "1", str(tmp)],
            capture_output=True, timeout=120,
        )
        if not tmp.is_file():
            continue
        with Image.open(tmp) as im:
            img = im.convert("RGB")
            ls, rs = band_score(img, left), band_score(img, right)
        winner = "LEFT" if ls > rs * 1.8 and ls > 0.02 else (
                 "RIGHT" if rs > ls * 1.8 and rs > 0.02 else "-")
        diffs.append(abs(ls - rs))
        print(f"{t:7.1f}  {ls:7.4f}  {rs:7.4f}   {winner}")
    tmp.unlink(missing_ok=True)

    avg = sum(diffs) / len(diffs) if diffs else 0.0
    print(f"\nmean |left-right| = {avg:.4f}")
    print("USABLE — the highlight separates the tiles" if avg > 0.01
          else "NOT USABLE — no separable highlight; needs audio diarisation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
