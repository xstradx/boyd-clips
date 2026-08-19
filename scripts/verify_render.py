"""Look at a rendered video before calling it done.

WHY THIS EXISTS
---------------
2026-08-18: the first moment render was reported as a success on the strength
of its log lines - "render: short (1 beats, 58.0s)", "framing: duo_fill",
"thumbnail: house style" - and a glance at the thumbnail. Every one of those
lines was true. The video was still unusable: roughly 30% of every frame was
black, the judge's tile was offset and clipped, a stray picture-frame panel
filled the middle, and the watermark was burned in twice.

Logs describe what the code attempted. They cannot describe what came out.

So this samples frames, MEASURES them against a render already approved by
Nathan, writes a contact sheet to be looked at, and exits non-zero when the
composition is broken. A render is not done until this passes and the sheet
has actually been opened.

    python scripts/verify_render.py out/review/<stamp>/short.mp4
    python scripts/verify_render.py <path> --baseline out/review/2026-04-27_JgvW7oCQxuI_6698/short.mp4
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

# FIRST METRIC, WRONG, RECORDED SO IT IS NOT RETRIED: total black share, limit
# 12%. Validated against the approved Thompson short and FAILED IT — Thompson
# measures 34.7% black with 3 "void" bands, WORSE than the broken render's
# 29.6% and 0. Total black is not the signal: a correct 9:16 short of two 16:9
# tiles is mostly letterbox by design, and the captions sit in that letterbox.
#
# WHAT ACTUALLY SEPARATES THEM, from looking at both contact sheets:
#   approved  - each tile spans the FULL canvas width, x=0 to x=1080. Black is
#               only above, below and between the tiles.
#   broken    - tiles are inset. Black appears INSIDE a content band, beside
#               the picture, because the 2-up crop was applied to a 3-tile
#               source and the geometry came out wrong.
#
# So measure coverage: for every row that contains any picture at all, what
# fraction of that row's width is picture? Full-width tiles ~= 1.0.
# THRESHOLD FROM A DISTRIBUTION, not from two points. Swept all 24 renders on
# disk (scripts/sweep_renders.py):
#
#   88.5% - 95.1%   21 renders, INCLUDING both Nathan approved (92.0%, 88.8%)
#   ---- gap ----
#   72.2%           4zkUTUavW4I:116  Blackburn - already documented in
#                   PIPELINE.md as unpostable, "3-4 tile Zoom grid throughout,
#                   every tile ~1/4 width, no face legible". The metric found
#                   it without being told, which is the validation.
#   70.4%           zHchVGBX9iA:10740  the first moment render
#   37.8%           t99ncB_5tw4_5707   a failure nobody had noticed
#
# 0.85 sits in the gap with room on both sides. A first attempt at 0.90 failed
# the approved Thompson short at 88.8% and was wrong.
MIN_ROW_COVERAGE = 0.85
FRAMES = 8


def sample(video: Path, n: int = FRAMES) -> list["object"]:
    import numpy as np
    from PIL import Image
    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(video)],
        capture_output=True, text=True).stdout.strip() or 0)
    if dur <= 0:
        raise SystemExit(f"{video}: no duration - not a video")
    tmp = Path(tempfile.mkdtemp(prefix="verify_"))
    out = []
    for i in range(1, n + 1):
        t = dur * i / (n + 1)
        p = tmp / f"f{i:02d}.png"
        subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video),
                        "-frames:v", "1", "-y", str(p)], capture_output=True)
        if p.exists() and p.stat().st_size:
            with Image.open(p) as im:
                out.append((t, np.asarray(im.convert("RGB"))))
    return out


def measure(frames):
    """Mean horizontal coverage of the rows that contain picture.

    A row is "content" if at least 15% of it is non-black — enough to exclude
    the letterbox bands, low enough to include a row crossing a dark tile.
    Coverage is then how much of that row is picture. Full-width tiles give
    ~1.0 whatever the letterboxing above and below them.
    """
    import numpy as np
    covs, blacks = [], []
    for _t, rgb in frames:
        g = rgb.mean(axis=2)
        lit = g >= 18
        blacks.append(1.0 - float(lit.mean()))
        row_cov = lit.mean(axis=1)
        content = row_cov[row_cov >= 0.15]
        covs.append(float(content.mean()) if content.size else 0.0)
    return {"coverage": sum(covs) / len(covs),
            "black": sum(blacks) / len(blacks), "frames": len(frames)}


def contact_sheet(frames, dst: Path, cols: int = 4) -> Path:
    from PIL import Image
    import numpy as np
    thumbs = [Image.fromarray(rgb).resize((270, 480)) for _t, rgb in frames]
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 270, rows * 480), "magenta")
    for i, th in enumerate(thumbs):
        sheet.paste(th, ((i % cols) * 270, (i // cols) * 480))
    sheet.save(dst)
    return dst


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    video = Path(args[0])
    baseline = None
    if "--baseline" in sys.argv:
        baseline = Path(sys.argv[sys.argv.index("--baseline") + 1])

    frames = sample(video)
    m = measure(frames)
    sheet = contact_sheet(frames, video.parent / "verify_sheet.png")
    print(f"{video}")
    print(f"  frames sampled : {m['frames']}")
    print(f"  row coverage   : {100 * m['coverage']:.1f}%   "
          f"(floor {100 * MIN_ROW_COVERAGE:.0f}%)")
    print(f"  black share    : {100 * m['black']:.1f}%   (informational — a correct "
          f"9:16 short is mostly letterbox)")
    print(f"  contact sheet  : {sheet}   <-- OPEN THIS")

    if baseline and baseline.exists():
        b = measure(sample(baseline))
        print(f"\n  baseline {baseline.parent.name}: coverage "
              f"{100 * b['coverage']:.1f}%, black {100 * b['black']:.1f}%")

    ok = m["coverage"] >= MIN_ROW_COVERAGE
    print("\n  " + ("PASS — still open the sheet before calling it done"
                    if ok else
                    "FAIL — tiles are inset, the composition is broken"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
