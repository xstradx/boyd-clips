"""Render the house-style quote thumbnail over a frame from the clip.

The rules are spec/PACKAGING.md, measured from Audit the Court (12/12 samples):
a first-person quote, 4-9 words, sentence case with terminal punctuation, two
colours only -- white for the setup, #FEFB04 for the emotionally loaded half,
split mid-sentence rather than by line.

The pipeline only ever extracted a bare frame (`render.extract_thumbnail`), so
this closes the gap between what it produced and what the spec asks for.

    python scripts/make_thumbnail.py frame.jpg out.jpg \
        --white "He was pointing" --yellow "a gun at me!"

The split is passed explicitly rather than guessed. Which half of a sentence
carries the charge is an editorial judgement, and a heuristic that gets it
wrong produces a thumbnail that reads as broken rather than as emphasis.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "assets" / "fonts"

WHITE = (255, 255, 255)
YELLOW = (254, 251, 4)          # #FEFB04, sampled across all 12 references
STROKE = (0, 0, 0)

W, H = 1280, 720
SIDE_MARGIN = 56
BOTTOM_MARGIN = 48
MAX_TEXT_FRAC = 0.46            # text block never eats more than this of the height


def _font(size: int) -> ImageFont.FreeTypeFont:
    """Montserrat at its heaviest axis position, or Anton as a static fallback."""
    var = FONTS / "Montserrat-Var.ttf"
    if var.is_file():
        f = ImageFont.truetype(str(var), size)
        try:
            f.set_variation_by_axes([900])      # wght
            return f
        except Exception:
            pass
    for name in ("Anton-Regular.ttf", "Archivo-Var.ttf", "BebasNeue-Regular.ttf"):
        p = FONTS / name
        if p.is_file():
            return ImageFont.truetype(str(p), size)
    raise SystemExit(f"no usable font in {FONTS}")


def _wrap(words: list[tuple[str, tuple[int, int, int]]],
          font: ImageFont.FreeTypeFont, max_w: int) -> list[list[tuple[str, tuple]]]:
    """Greedy wrap that keeps each word's colour attached to it."""
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    lines: list[list[tuple[str, tuple]]] = [[]]
    for word, colour in words:
        trial = " ".join(w for w, _ in lines[-1] + [(word, colour)])
        if lines[-1] and draw.textlength(trial, font=font) > max_w:
            lines.append([(word, colour)])
        else:
            lines[-1].append((word, colour))
    return [ln for ln in lines if ln]


def _trim_letterbox(img: Image.Image, threshold: int = 22) -> Image.Image:
    """Strip the court encoder's baked-in black bars.

    The court streams a 16:9 frame with the Zoom view letterboxed *inside* it,
    so a raw extracted frame can be ~45% black. Cover-fitting that keeps the
    bars and throws away the courtroom, which is the whole subject.

    Scans inward row by row and column by column, treating a line as letterbox
    only if nearly all of it is dark. A plain bounding box does not work here:
    the stream burns a "zoom" watermark into the bottom black band, and one
    bright word is enough to anchor the box and keep the whole bar.

    The darkness test only looks at the middle 60% of each line, because that
    watermark defeats a full-width test too -- it lights ~14% of its row, which
    is well above any sane "this row is black" threshold. Burned-in marks live
    in corners; real picture content reaches the centre.
    """
    grey = img.convert("L")
    w, h = grey.size
    px = grey.load()
    keep = 0.02          # a line survives as letterbox if <2% of it is lit

    x0, x1 = int(w * 0.2), int(w * 0.8)
    y0, y1 = int(h * 0.2), int(h * 0.8)

    def dark_row(y: int) -> bool:
        xs = range(x0, x1, 3)
        lit = sum(1 for x in xs if px[x, y] > threshold)
        return lit <= keep * len(xs)

    def dark_col(x: int) -> bool:
        ys = range(y0, y1, 3)
        lit = sum(1 for y in ys if px[x, y] > threshold)
        return lit <= keep * len(ys)

    top = 0
    while top < h - 1 and dark_row(top):
        top += 1
    bottom = h - 1
    while bottom > top and dark_row(bottom):
        bottom -= 1
    left = 0
    while left < w - 1 and dark_col(left):
        left += 1
    right = w - 1
    while right > left and dark_col(right):
        right -= 1

    # Ignore a detection that found almost nothing, or that trimmed nothing.
    if (right - left) < w * 0.4 or (bottom - top) < h * 0.25:
        return img
    return img.crop((left, top, right + 1, bottom + 1))


def _pick_tile(img: Image.Image, tile: str) -> Image.Image:
    """Take one half of a side-by-side Zoom view.

    Once the letterbox is stripped these frames come back around 3.5:1, and
    cover-fitting that to 16:9 crops hard into the seam between the two tiles --
    the one part of the frame with nobody in it, while both faces get pushed off
    the edges. Choosing a side keeps a face at full size.
    """
    if tile == "both" or img.width / img.height < 2.2:
        return img
    half = img.width // 2
    return img.crop((0, 0, half, img.height)) if tile == "left" \
        else img.crop((half, 0, img.width, img.height))


def render(frame: Path, out: Path, white_part: str, yellow_part: str,
           gravity: str = "bottom", tile: str = "both") -> Path:
    img = Image.open(frame).convert("RGB")
    img = _trim_letterbox(img)
    img = _pick_tile(img, tile)

    # Cover-fit to 1280x720 rather than stretching -- a squashed face is the
    # most obvious tell that a thumbnail was generated.
    scale = max(W / img.width, H / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    img = img.crop((
        (img.width - W) // 2, (img.height - H) // 2,
        (img.width - W) // 2 + W, (img.height - H) // 2 + H,
    ))

    words = [(w, WHITE) for w in white_part.split()]
    words += [(w, YELLOW) for w in yellow_part.split()]
    if not words:
        raise SystemExit("empty quote")

    max_w = W - 2 * SIDE_MARGIN

    # Largest size that fits the width budget in <= 3 lines and the height cap.
    size = 132
    while size > 40:
        font = _font(size)
        lines = _wrap(words, font, max_w)
        line_h = round(size * 1.12)
        if len(lines) <= 3 and len(lines) * line_h <= H * MAX_TEXT_FRAC:
            break
        size -= 4
    font = _font(size)
    lines = _wrap(words, font, max_w)
    line_h = round(size * 1.12)
    block_h = len(lines) * line_h

    top = H - BOTTOM_MARGIN - block_h if gravity == "bottom" else (H - block_h) // 2

    # Scrim behind the text so it survives a bright or busy frame. Without it the
    # stroke alone fails on white courtroom walls, which is most of this footage.
    # Runs to the bottom edge and fades in at the top -- a floating grey band
    # with a hard upper edge reads as a mistake, and the text's descenders were
    # spilling past a fixed-height rectangle.
    scrim = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(scrim)
    fade = 90
    for i in range(fade):
        y = top - 40 + i
        if 0 <= y < H:
            sd.line([(0, y), (W, y)], fill=(0, 0, 0, round(150 * i / fade)))
    sd.rectangle([0, top - 40 + fade, W, H], fill=(0, 0, 0, 150))
    img = Image.alpha_composite(img.convert("RGBA"), scrim).convert("RGB")

    draw = ImageDraw.Draw(img)
    stroke_w = max(4, round(size * 0.055))
    for i, line in enumerate(lines):
        text = " ".join(w for w, _ in line)
        x = (W - draw.textlength(text, font=font)) / 2
        y = top + i * line_h
        for word, colour in line:
            draw.text((x, y), word, font=font, fill=colour,
                      stroke_width=stroke_w, stroke_fill=STROKE)
            x += draw.textlength(word + " ", font=font)

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, quality=92)
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("frame", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--white", required=True, help="setup half of the quote")
    ap.add_argument("--yellow", required=True, help="emotionally loaded half")
    ap.add_argument("--gravity", default="bottom", choices=["bottom", "center"])
    ap.add_argument("--tile", default="both", choices=["both", "left", "right"],
                    help="on a side-by-side two-up, keep only this half")
    a = ap.parse_args(argv[1:])

    quote = f"{a.white} {a.yellow}".strip()
    n = len(quote.split())
    if not 4 <= n <= 9:
        print(f"warning: {n} words, spec band is 4-9", file=sys.stderr)
    if not 18 <= len(quote) <= 43:
        print(f"warning: {len(quote)} chars, spec band is 18-43", file=sys.stderr)
    if quote[-1] not in "!?":
        print("warning: spec wants terminal ! or ?", file=sys.stderr)
    if quote.isupper():
        print("warning: spec is sentence case, never all-caps", file=sys.stderr)

    print(render(a.frame, a.out, a.white, a.yellow, a.gravity, a.tile))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
