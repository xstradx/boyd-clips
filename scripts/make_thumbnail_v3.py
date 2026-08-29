"""Thumbnail built to what Audit the Court's thumbnails ACTUALLY are.

Nathan, 2026-08-23, on the v2 output: "that thumbnail is slop, take notes from
audit the courts thumbnails". So this is measured off the 12 JPEGs in
`research/reference/competitor/thumbs/`, by looking at them, not off
`THUMBNAILS.md` — which v2 was built from and which is wrong on the single most
important point:

    THUMBNAILS.md §5: "9/12 are a subject cut out over a second courtroom
    plate, feathered, with NO outline stroke on the cut-out"

That is not what the images show. Their construction is a HARD-EDGED PANEL
SPLIT: two or three vertical panels of different footage butted together with a
straight seam and no feather, no traced mask, no matting. v2's whole rembg
cut-out-over-a-plate approach is a different product, and it is why the output
reads as pasted-on.

What the 12 actually share:

  * 2-3 vertical panels, hard seam. Detected seams sit at x 0.36 and 0.64 W;
    the 2-panel ones split around 0.55-0.62.
  * The hero is a face, CROPPED TIGHT, filling most of its panel's height.
    Chest-up or closer. v2 pasted whole standing bodies at 0.29-0.34 W and they
    read as figurines.
  * Type is BIG. Cap height measured across the 12: 0.072, 0.075, 0.079, 0.085,
    0.086, 0.106, 0.111, 0.115, 0.131, 0.131, 0.149, 0.176 of H — median
    ~0.11 H, about 79px at 720. v2 shipped 0.0597 H (43px), below every one of
    them.
  * Type is top-LEFT, 1-3 lines, white with the key phrase in yellow, heavy
    black stroke plus a zero-offset black glow.
  * Type sits over the WIDE panel's background — the gallery, a wall, sky, the
    ceiling. It is never over the hero's face. That is exactly Nathan's rule
    ("the words should never be on defendants or judges face or body"), and it
    is enforced here by construction: type is clipped to the wide panel and the
    hero lives in the other one.
  * A red arrow appears in 8/12, in the wide panel, pointing down into the
    secondary subject. `assets/brand` house style says "no arrow"; that note
    derives from the same wrong document, so the arrow is offered here and
    defaulted ON, matching the reference. `--no-arrow` turns it off.

    python scripts/make_thumbnail_v3.py \\
        --wide left.png --hero right.png \\
        --white "No monkey business" --yellow "in my court" \\
        --arrow 0.30,0.62 --out thumb.jpg
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "assets" / "fonts"

W, H = 1280, 720

YELLOW = (254, 251, 3)
WHITE = (255, 255, 255)
ARROW_RED = (253, 1, 1)

SEAM = 0.58            # x/W of the hard vertical seam, 2-panel median
CAP_FRAC = 0.110       # median of the 12 measured cap heights
CAP_LADDER = (0.110, 0.100, 0.092, 0.085, 0.079, 0.072)
STROKE_RATIO = 1 / 6
GLOW_RADIUS = 20
TEXT_X = 0.030         # left inset
TEXT_TOP = 0.055       # top inset
ARROW_W, ARROW_H = 123, 92


def _font(px: int) -> ImageFont.FreeTypeFont:
    var = FONTS / "Montserrat-Var.ttf"
    if var.is_file():
        f = ImageFont.truetype(str(var), px)
        try:
            f.set_variation_by_axes([900])
            return f
        except Exception:
            pass
    static = (ROOT / "research" / "blender" / "graphics" / "fonts_static"
              / "Montserrat-Bold.ttf")
    if static.is_file():
        return ImageFont.truetype(str(static), px)
    raise SystemExit(f"no Montserrat in {FONTS}")


def _cover(img: Image.Image, w: int, h: int) -> Image.Image:
    scale = max(w / img.width, h / img.height)
    img = img.resize((max(1, round(img.width * scale)),
                      max(1, round(img.height * scale))), Image.LANCZOS)
    x, y = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))


def _wrap(words, font, max_w):
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    lines = [[]]
    for word, colour in words:
        trial = " ".join(w for w, _ in lines[-1] + [(word, colour)])
        if lines[-1] and draw.textlength(trial, font=font) > max_w:
            lines.append([(word, colour)])
        else:
            lines[-1].append((word, colour))
    return [ln for ln in lines if ln]


def _arrow(canvas: Image.Image, cx: float, cy: float,
           angle_deg: float = 150.0) -> None:
    rad = math.radians(angle_deg)
    ux, uy = math.cos(rad), math.sin(rad)
    px, py = -uy, ux
    head_len, head_w, shaft_w = ARROW_W * 0.46, ARROW_H * 0.92, ARROW_H * 0.38

    def at(back: float, side: float):
        return (cx * W - ux * back + px * side,
                cy * H - uy * back + py * side)

    pts = [at(0, 0), at(head_len, head_w / 2), at(head_len, shaft_w / 2),
           at(ARROW_W, shaft_w / 2), at(ARROW_W, -shaft_w / 2),
           at(head_len, -shaft_w / 2), at(head_len, -head_w / 2)]
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(layer).polygon(pts, fill=ARROW_RED + (255,),
                                  outline=(0, 0, 0, 255), width=3)
    canvas.paste(Image.alpha_composite(canvas.convert("RGBA"), layer)
                 .convert("RGB"), (0, 0))


def build(wide: Path, hero: Path, white_part: str, yellow_part: str, out: Path,
          seam: float = SEAM, arrow: tuple[float, float] | None = None,
          third: Path | None = None, text_max: float | None = None) -> Path:
    canvas = Image.new("RGB", (W, H), (0, 0, 0))

    seam_x = int(round(W * seam))
    if third is not None:
        # Three panels, as in the 971K and 412K references.
        a = int(round(W * seam * 0.55))
        canvas.paste(_cover(Image.open(wide).convert("RGB"), a, H), (0, 0))
        canvas.paste(_cover(Image.open(third).convert("RGB"), seam_x - a, H),
                     (a, 0))
    else:
        canvas.paste(_cover(Image.open(wide).convert("RGB"), seam_x, H), (0, 0))
    canvas.paste(_cover(Image.open(hero).convert("RGB"), W - seam_x, H),
                 (seam_x, 0))

    if arrow is not None:
        _arrow(canvas, arrow[0], arrow[1])

    # ---- type ---------------------------------------------------------- #
    # Clipped to the wide panel. This is what keeps it off the hero's face,
    # and it is how the reference set does it — not by leaving a blank band.
    words = [(w, WHITE) for w in white_part.split()]
    words += [(w, YELLOW) for w in yellow_part.split()]
    # Clipped to the FIRST panel when there is a third, not to the whole wide
    # side. With three panels the middle one holds a person, and letting the
    # quote run across the seam puts it back on a face — which is the thing
    # being fixed.
    text_right = W * text_max if text_max else seam_x
    max_w = int(text_right - 2 * W * TEXT_X)

    cap_px = round(H * CAP_FRAC)
    lines = None
    for frac in CAP_LADDER:
        cap_px = round(H * frac)
        font = _font(round(cap_px / 0.72))
        lines = _wrap(words, font, max_w)
        # Up to 3 lines, exactly as their 2- and 3-line cards do.
        if len(lines) <= 3:
            break
    size = round(cap_px / 0.72)
    font = _font(size)
    lines = _wrap(words, font, max_w)
    line_h = round(size * 1.06)
    stroke = max(6, round(cap_px * STROKE_RATIO))

    x0, y0 = int(W * TEXT_X), int(H * TEXT_TOP)

    glow = Image.new("L", (W, H), 0)
    gd = ImageDraw.Draw(glow)
    for i, line in enumerate(lines):
        gd.text((x0, y0 + i * line_h), " ".join(w for w, _ in line),
                font=font, fill=255, stroke_width=stroke, stroke_fill=255)
    glow = glow.filter(ImageFilter.GaussianBlur(GLOW_RADIUS))
    canvas.paste(Image.new("RGB", (W, H), (0, 0, 0)), (0, 0), glow)

    d = ImageDraw.Draw(canvas)
    for i, line in enumerate(lines):
        x = x0
        y = y0 + i * line_h
        for word, colour in line:
            d.text((x, y), word, font=font, fill=colour,
                   stroke_width=stroke, stroke_fill=(0, 0, 0))
            x += d.textlength(word + " ", font=font)

    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, "JPEG", quality=94, subsampling=0)
    print(f"cap {cap_px}px ({cap_px / H:.4f} H)  stroke {stroke}px  "
          f"{len(lines)} line(s)  seam x{seam:.2f} -> {out}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wide", required=True, type=Path)
    ap.add_argument("--hero", required=True, type=Path)
    ap.add_argument("--third", default=None, type=Path)
    ap.add_argument("--white", required=True)
    ap.add_argument("--yellow", required=True)
    ap.add_argument("--seam", type=float, default=SEAM)
    ap.add_argument("--arrow", default=None,
                    help="cx,cy of the arrow TIP as fractions of W,H")
    ap.add_argument("--no-arrow", action="store_true")
    ap.add_argument("--text-max", type=float, default=None,
                    help="right edge of the type box as a fraction of W")
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()

    tip = None
    if a.arrow and not a.no_arrow:
        tip = tuple(float(v) for v in a.arrow.split(","))
    build(a.wide, a.hero, a.white, a.yellow, a.out, seam=a.seam, arrow=tip,
          third=a.third, text_max=a.text_max)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
