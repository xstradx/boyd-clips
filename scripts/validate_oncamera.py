"""Calibrate the on-camera probe against cases whose outcome we already know.

GROUND TRUTH (established by actually rendering them — see PIPELINE.md):
  Thompson  JgvW7oCQxuI:6698 — short rendered and APPROVED, faces legible.
  Rodriguez mvGmUbuS0sU:1358 — short rendered, ready, faces legible.
  Blackburn 4zkUTUavW4I:116  — short UNPOSTABLE: "3-4 tile Zoom grid
                               throughout, every tile ~1/4 width, no face legible".
  Pena      oL6lV6gCyOc:3047 — unknown. 51-min contested PSI sentencing.

Frames are KEPT in out/oncam/<label>/ so they can be looked at, because a
number that disagrees with the picture is the number that is wrong.
"""
import sys, logging
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
logging.basicConfig(level=logging.INFO, format="%(message)s")

from boydclips import oncamera

CASES = [
    ("thompson_GOOD", "JgvW7oCQxuI", 6698, 6958),
    ("rodriguez_GOOD", "mvGmUbuS0sU", 1358, 2012),
    ("blackburn_BADGRID", "4zkUTUavW4I", 116, 2145),
    ("pena_UNKNOWN", "oL6lV6gCyOc", 3047, 6115),
]

for label, vid, a, b in CASES:
    out = ROOT / "out" / "oncam" / label
    print(f"\n=== {label}  {vid} {a}-{b}s")
    frames = sorted(out.glob("f*.png")) or oncamera.sample_frames(
        vid, a, b, n=6, out_dir=out)
    if len(frames) < 2:
        print("   could not sample frames")
        continue
    from PIL import Image
    with Image.open(frames[0]) as im:
        print(f"   {len(frames)} frames, {im.size[0]}x{im.size[1]}")
    auto = oncamera.detect_layout(frames)
    for layout in (auto, "grid" if auto != "grid" else "2up"):
        v = oncamera.analyse(frames, layout)
        cells = "  ".join(
            f"{t.name}:{'LIVE' if t.live else 'DEAD'}(d{t.detail:.0f} "
            f"blk{t.dark:.2f} f{t.faces})" for t in v.tiles)
        tag = "AUTO " if layout == auto else "     "
        print(f"   {tag}{layout:5} live={v.live_tiles} usable={str(v.usable):5} {cells}")
    print(f"   frames kept in {out}")
