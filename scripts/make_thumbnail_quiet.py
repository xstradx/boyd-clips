"""The quiet construction: a verbatim line, small and low-contrast, in real negative space.

Nathan, 2026-08-29, on the six alternatives: "d looks crazy".

This is the opposite bet to our loud construction. Measured on the two exemplars
the research pass found — 47,000,000 and 66,000,000 views:

    glyphs RGB(44,45,43) on wall RGB(135,137,131)   WCAG 3.91:1
    glyphs RGB(55,67,71) on wall RGB(161,174,168)   WCAG 4.44:1

Both BELOW the 4.5:1 accessibility minimum, on purpose. No plate, no outline, no
drop shadow, no cut-out, no arrow. The frame is left ungraded and soft (their
mean saturation 0.083, luminance 124).

What actually does the work there is NOT the type — at a 210px feed tile a 43px
cap renders about 7px, below the measured habitual reading size, so it cannot be
read before the click. It is texture that says "this is a record, not an
advertisement". Copy the reservoir of empty space; do not expect the words to be
read.

The line must be VERBATIM from the transcript. A quote-shaped line that was never
said is the exact fact pattern of YouTube's egregious-clickbait rule, and on a
courtroom channel quoted text reads as a transcript quote rather than a joke.

Placement is derived, not fixed: the emptiest, flattest region of the frame is
measured and the type is dropped into it, so the same code works whichever side
of the Zoom grid the wall happens to be on.
"""
from __future__ import annotations
import argparse, json, subprocess, tempfile
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "assets" / "fonts"
W, H = 1280, 720
CAP_FRAC = 0.060          # 43px at 720, the measured exemplar
TARGET_CONTRAST = 4.1     # sit just under the 4.5:1 floor, as they do


def serif(px: int) -> ImageFont.FreeTypeFont:
    """A plain humanist face, not the loud headline one. The quiet construction
    is defined partly by NOT using display type."""
    for p in (r"C:\Windows\Fonts\georgia.ttf", r"C:\Windows\Fonts\constan.ttf",
              r"C:\Windows\Fonts\times.ttf"):
        if Path(p).is_file():
            return ImageFont.truetype(p, px)
    return ImageFont.truetype(str(FONTS / "Archivo-Var.ttf"), px)


def grab(src: Path, t: float, crop: str | None, out: Path) -> bool:
    vf = f"crop={crop},scale={W}:{H}" if crop else f"scale={W}:{H}"
    subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(src),
                    "-frames:v", "1", "-vf", vf, "-q:v", "1", str(out), "-y"],
                   capture_output=True, timeout=300)
    return out.is_file()


def find_reservoir(img: Image.Image, need_w: int, need_h: int,
                   flat_max: float = 14.0):
    """The emptiest, flattest, most uniform rectangle big enough for the line.

    Derived rather than fixed: on one exemplar the type sits in the LEFT third
    and on the other in the RIGHT third, because that is where each frame's wall
    happened to be. Hardcoding a corner is what breaks on the next hearing.
    """
    L = np.asarray(img.convert("L"), dtype=np.float32)
    best = None
    step = 24
    for y in range(0, H - need_h, step):
        for x in range(0, W - need_w, step):
            q = L[y:y + need_h, x:x + need_w]
            sd = float(q.std())
            if sd > flat_max:                 # must be genuinely flat
                continue
            m = float(q.mean())
            if not (70 < m < 215):            # not blown, not crushed
                continue
            score = -sd + m * 0.05            # flat first, then brighter
            if best is None or score > best[0]:
                best = (score, x, y, m, sd)
    return best


def relative_luminance(rgb):
    c = np.array(rgb, dtype=float) / 255.0
    c = np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def glyph_colour(bg_mean: float, target: float):
    """Darken from the background until the contrast ratio hits `target`.

    The exemplars are not 'dark grey' in the abstract — they are a specific
    ratio away from whatever wall they sit on. Solving for the ratio is what
    makes this transfer to a different room.
    """
    bgl = relative_luminance((bg_mean, bg_mean, bg_mean))
    want = (bgl + 0.05) / target - 0.05
    lo, hi = 0.0, bg_mean
    for _ in range(40):
        mid = (lo + hi) / 2
        if relative_luminance((mid, mid, mid)) > want:
            hi = mid
        else:
            lo = mid
    v = int(round((lo + hi) / 2))
    return (max(0, v - 6), max(0, v - 3), max(0, v - 14))   # faintly warm-neutral


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, type=Path)
    ap.add_argument("--offset", type=float, required=True)
    ap.add_argument("--at", type=float, required=True, help="source time of the frame")
    ap.add_argument("--crop", default=None)
    ap.add_argument("--quote", required=True)
    ap.add_argument("--transcript", default=None, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()

    if a.transcript and a.transcript.is_file():
        tr = json.load(open(a.transcript, encoding="utf-8"))
        hay = " ".join(x["w"] for x in tr["words"]).lower()
        needle = a.quote.strip('"').strip("'").lower()
        needle = " ".join(needle.replace(",", "").replace("?", "").split())
        clean = " ".join(hay.replace(">>", "").replace(",", "").replace("?", "").split())
        if needle not in clean:
            print(f"  REFUSING: '{a.quote}' is not in the transcript verbatim")
            return 2
        print("  quote verified verbatim in the transcript")

    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "f.png"
        if not grab(a.source, a.at - a.offset, a.crop, f):
            print("could not grab frame"); return 1
        img = Image.open(f).convert("RGB")

    cap = int(H * CAP_FRAC)
    font = serif(int(cap / 0.70))
    d0 = ImageDraw.Draw(img)
    text = f'\u201c{a.quote}\u201d'
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if cur and d0.textlength(t, font=font) > W * 0.34:
            lines.append(cur); cur = w
        else:
            cur = t
    if cur:
        lines.append(cur)
    lh = int(font.size * 1.28)
    tw = int(max(d0.textlength(l, font=font) for l in lines))
    th = lh * len(lines)

    # Widen the flatness tolerance until something fits. A courtroom 2-up is
    # much busier than the wide single-camera frames the exemplars used, so a
    # fixed threshold simply refuses on this material.
    res = None
    for fm in (10.0, 14.0, 20.0, 28.0, 38.0):
        res = find_reservoir(img, tw + 60, th + 50, flat_max=fm)
        if res is not None:
            print(f"  reservoir found at flatness tolerance {fm}")
            break
    if res is None:
        print("  REFUSING: no flat empty region big enough — pick another frame")
        return 3
    _, rx, ry, bgm, sd = res
    col = glyph_colour(bgm, TARGET_CONTRAST)
    ratio = (max(relative_luminance((bgm,) * 3), relative_luminance(col)) + 0.05) / \
            (min(relative_luminance((bgm,) * 3), relative_luminance(col)) + 0.05)
    print(f"  reservoir at ({rx},{ry}) mean {bgm:.0f} sd {sd:.1f}")
    print(f"  glyph RGB {col}  contrast {ratio:.2f}:1  cap {cap}px = {cap/H:.3f} H")

    d = ImageDraw.Draw(img)
    for i, l in enumerate(lines):
        d.text((rx + 30, ry + 25 + i * lh), l, font=font, fill=col)

    a.out.parent.mkdir(parents=True, exist_ok=True)
    img.save(a.out, "JPEG", quality=95, subsampling=0)
    print(f"  -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
