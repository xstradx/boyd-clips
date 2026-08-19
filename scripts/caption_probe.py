"""Render one caption card to a still and measure where its ink actually lands.

Caption geometry was being chosen by arithmetic on font metrics, which is a
guess: libass applies the style's outline, shadow, spacing and its own line
gap, and Arial Black's advance width is not the 0.6em that a back-of-envelope
calculation assumes. The only honest number comes from rendering the thing and
measuring the pixels.

Two published limits are checked against, both from primary sources:

  * bottom clearance 672px on a 1080x1920 canvas — Google's own Universal Video
    Ad Safe Zones (services.google.com/fh/files/misc/universalsafezones-youtube.pdf)
    gives 35% bottom for YouTube, and Meta's Instagram Reels ad spec gives the
    same 35%. This is the advertiser CTA buffer rather than a measurement of
    the organic player chrome — no platform publishes that — so it is the
    conservative bound, not a confirmed collision point.
  * cap height 72px — BBC/EBU-TT-D gives 3.75% of height for vertical, and
    W3C IMSC1.3's default 32x15 cellResolution lands on the same 72px from a
    different direction.

    python scripts/caption_probe.py --font-size 96 --max-chars 16 --margin-v 700
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from boydclips import render                                    # noqa: E402
from boydclips.transcribe import Word                           # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

CANVAS_W, CANVAS_H = 1080, 1920
SAFE_TOP = 288        # y, Google/Meta ad safe zone
SAFE_BOTTOM = 1248    # y = 1920 - 672
SAFE_LEFT = 65
SAFE_RIGHT = 888
MIN_CAP_PX = 72       # BBC/EBU-TT-D vertical


def ink_box(png: Path) -> tuple[int, int, int, int] | None:
    """Bounding box of everything non-black in the frame, as (w, h, x, y).

    `bbox`, not `cropdetect`. cropdetect models black *bars* — it asks how far
    in from each edge a uniform border runs — so a line of text on black gives
    it mostly-black columns and it reports a negative width. Measured: a single
    'H' returned crop=-1078:-1918, i.e. "nothing here", while bbox returned the
    correct 37x38 at (521,1066). Using the wrong instrument read as "the
    caption did not draw" and would have sent me looking for a font bug.
    """
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(png),
         "-vf", "bbox=min_val=24", "-frames:v", "1", "-f", "null", "-"],
        capture_output=True, text=True, timeout=120,
    )
    hits = re.findall(r"x1:(\d+) x2:(\d+) y1:(\d+) y2:(\d+)", proc.stderr)
    if not hits:
        return None
    x1, x2, y1, y2 = (int(v) for v in hits[-1])
    return x2 - x1 + 1, y2 - y1 + 1, x1, y1


def cap_height(font: str, font_size: int, outline: int) -> int:
    """Rendered height of a single capital letter, outline included.

    Measured rather than derived: 'H' alone on the canvas, so the ink box IS
    the cap height. The outline counts because it is what the viewer sees at
    thumb distance.
    """
    # Timed to straddle the 1.0s sample: a card's last word runs for 0.45s, so
    # a word at 0.5 has already left the screen by the time the frame is taken.
    return _render_and_measure(
        [Word(0.9, "H")], font, font_size, outline, max_chars=4, margin_v=800
    )[1]


def _render_and_measure(
    words: list[Word], font: str, font_size: int, outline: int,
    max_chars: int, margin_v: int,
) -> tuple[int, int, int, int]:
    style = {
        "font": font, "font_size": font_size, "outline": outline, "shadow": 2,
        "margin_v": margin_v, "max_chars_per_line": max_chars, "max_lines": 2,
        "uppercase": True,
    }
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        ass = render.build_ass(words, 0.0, 3.0, style, None, tmp / "probe.ass")
        png = tmp / "probe.png"
        fonts = ROOT / "assets" / "fonts"
        chain = f"ass={ass.name}"
        if fonts.is_dir() and any(fonts.iterdir()):
            rel = str(fonts.resolve()).replace("\\", "/").replace(":", "\\:")
            chain += f":fontsdir='{rel}'"
        subprocess.run(
            ["ffmpeg", "-y", "-hide_banner", "-nostats",
             "-f", "lavfi", "-i", f"color=c=black:s={CANVAS_W}x{CANVAS_H}:d=3",
             "-vf", chain, "-ss", "1.0", "-frames:v", "1", "-update", "1",
             str(png.resolve())],
            cwd=str(tmp), capture_output=True, text=True, timeout=180, check=True,
        )
        box = ink_box(png)
    if box is None:
        raise RuntimeError("nothing rendered — the caption did not draw")
    return box


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--font", default="Arial Black")
    ap.add_argument("--font-size", type=int, default=74)
    ap.add_argument("--outline", type=int, default=5)
    ap.add_argument("--max-chars", type=int, default=22)
    ap.add_argument("--margin-v", type=int, default=154)
    ap.add_argument("--text", default="YOU'RE SAYING YOUR EX-WIFE WAS KILLED")
    a = ap.parse_args()

    # Worst case for width is the longest line the wrapper can produce, so the
    # probe text is deliberately long enough to fill both lines.
    words = [Word(0.4 + 0.05 * i, t) for i, t in enumerate(a.text.split())]
    w, h, x, y = _render_and_measure(
        words, a.font, a.font_size, a.outline, a.max_chars, a.margin_v
    )
    cap = cap_height(a.font, a.font_size, a.outline)

    print(f"font {a.font!r} size {a.font_size} outline {a.outline} "
          f"max_chars {a.max_chars} margin_v {a.margin_v}")
    print(f"  ink box     {w}x{h} at ({x},{y})  -> spans y {y}..{y + h}, "
          f"x {x}..{x + w}")
    print(f"  cap height  {cap}px")

    ok = True
    for label, cond, detail in [
        ("cap height >= 72px", cap >= MIN_CAP_PX, f"{cap}px"),
        ("clears bottom UI", y + h <= SAFE_BOTTOM,
         f"bottom of ink at y={y + h}, limit {SAFE_BOTTOM}"),
        ("clears top UI", y >= SAFE_TOP, f"top of ink at y={y}, limit {SAFE_TOP}"),
        ("inside left edge", x >= SAFE_LEFT, f"x={x}, limit {SAFE_LEFT}"),
        ("inside right edge", x + w <= SAFE_RIGHT,
         f"right of ink at x={x + w}, limit {SAFE_RIGHT}"),
    ]:
        print(f"  [{'PASS' if cond else 'FAIL'}] {label}: {detail}")
        ok &= bool(cond)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
