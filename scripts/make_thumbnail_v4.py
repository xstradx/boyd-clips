"""Thumbnail built to the @courtroomtime WINNER template, measured 2026-08-23.

Why a fourth builder: v2 was built on `research/reference/competitor/THUMBNAILS.md`,
which is wrong about Audit the Court's construction, and v3 was built on Audit's
top-left type. Both were then refuted by the only controlled evidence we own —
`research/reference/courtroomtime/thumbs/`, 25 thumbnails split top_/bot_ on ONE
channel covering THIS judge's docket, so creator, audience and niche are held
constant. Full numbers in `research/THUMBNAIL-MEASURED-2026-08-23.md`.

The three findings this file is built on:

1. TYPE GOES AT THE BOTTOM, ON A PLATE IT BRINGS WITH IT. Twelve of fifteen
   winners have literally zero text pixels above y=0.20H. The copy never has to
   find an empty region in the footage because an opaque plate manufactures one.
   That is also the mechanical answer to Nathan's hard rule — "the words should
   never be on defendants or judges face or body" — and it is why the four
   earlier attempts all failed: they hunted for a gap that does not exist in a
   Zoom tile.

2. TEMPLATE DISCIPLINE IS THE SHARPEST DISCRIMINATOR, not taste. The bottom
   plate is 83-86px tall at 720 in 9 of 12 winners that have one, and in 0 of 8
   losers (Fisher p=0.00138). The losers' bar height varies 2.5x more. So the
   numbers below are locked, not tuned.

3. TWO CHEAP TELLS SIT ONLY IN LOSERS: a yellow border ring around the frame
   (0/15 top, 5/10 bot) and a yellow arrow (0/15 top, 5/10 bot). Neither is
   available here. Winners that use an arrow use red.

And the copy rule, measured rather than assumed: none of the 15 winning titles
is a quote. They are third-person editorial — "Judge Boyd Owns Smug Lawyer
Who...". A first-person line she never said would be putting words in her mouth;
a third-person claim the video delivers is what the winners actually ship.

    python scripts/make_thumbnail_v4.py --left boyd.png --right def.png \\
        --hero "NO MONKEY BUSINESS" --plate "IN HER COURT" --out t.jpg
"""

from __future__ import annotations

import argparse
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "assets" / "fonts"
W, H = 1280, 720

# Locked to the measured winner template. Do not tune these by eye.
PLATE_FILL = (234, 220, 7)        # #EADC07, median of the winning plate family
PLATE_H = 84                      # px at 720; winners 83-86, losers 0/8 in band
PLATE_TOP = 620                   # y; winners' plate top edge 0.843-0.872 H
PLATE_CAP = 62                    # black caps inside the plate, 0.083-0.089 H
NAME_FILL = (200, 24, 24)         # red name plate above the yellow one
NAME_W = 0.45                     # of frame width
NAME_H = 0.125                    # of frame height
NAME_CAP = 68
HERO_CAP = 128                    # free-floating hero phrase, winners 115-152px
TEAR_MIN, TEAR_MAX = 19, 52       # torn-paper divider width, measured
SEAM = 0.40                       # left panel runs 0 to 0.34-0.41 W


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


def _headroom(img: Image.Image, frac: float) -> Image.Image:
    """Extend a panel UPWARD by stretching its own top rows.

    Measured on the winners: the largest face is a median 0.293 of frame height,
    and the hero phrase sits on picture ABOVE the heads. Our source is a Zoom
    tile framed chest-up, so a crop tight enough to read at 210px leaves no band
    above the head for type — which is how four earlier builds ended with words
    across a face. Rather than shrink the face (which kills the read at feed
    size), this manufactures the band out of the panel's own ceiling/wall, so
    the added rows are the real room, not a flat colour.
    """
    if frac <= 0:
        return img
    add = int(round(img.height * frac))
    top = img.crop((0, 0, img.width, max(2, int(img.height * 0.06))))
    top = top.resize((img.width, add), Image.LANCZOS)
    out = Image.new("RGB", (img.width, img.height + add))
    out.paste(top, (0, 0))
    out.paste(img, (0, add))
    return out


def _cover(img: Image.Image, w: int, h: int, anchor_top: bool = False) -> Image.Image:
    """Fill w x h. `anchor_top` keeps the top rows instead of centre-cropping.

    This matters once _headroom has run: a centre crop throws away exactly the
    band that was just manufactured AND the bottom of the face, which is how the
    headroom pass made things worse rather than better on first attempt.
    """
    s = max(w / img.width, h / img.height)
    img = img.resize((max(1, round(img.width * s)), max(1, round(img.height * s))),
                     Image.LANCZOS)
    x = (img.width - w) // 2
    y = 0 if anchor_top else (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))


def _tear(canvas: Image.Image, x: int, seed: int = 7) -> None:
    """Ragged white paper tear, not a butt seam.

    Measured: a grey-scale column-discontinuity detector finds ZERO seams on all
    25 courtroomtime files, because the divider is a ragged near-white strip
    17-67px wide rather than a clean edge. Only 2 of 25 use a hard butt seam,
    and one of those is the worst-performing file in the set (388 views).
    """
    rng = random.Random(seed)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    left, right = [], []
    y = 0
    lx, rx = x, x + rng.randint(TEAR_MIN, TEAR_MAX)
    while y <= H:
        left.append((lx + rng.randint(-9, 9), y))
        right.append((rx + rng.randint(-9, 9), y))
        y += rng.randint(14, 34)
    pts = left + list(reversed(right))
    d.polygon(pts, fill=(252, 251, 247, 255))
    canvas.paste(Image.alpha_composite(canvas.convert("RGBA"), layer)
                 .convert("RGB"), (0, 0))


def _stroked(d: ImageDraw.ImageDraw, xy, text, font, fill, stroke):
    d.text(xy, text, font=font, fill=fill, stroke_width=stroke,
           stroke_fill=(0, 0, 0))


def build(left: Path, right: Path, hero: str, plate_text: str, out: Path,
          name: str = "JUDGE BOYD", seam: float = SEAM, seed: int = 7,
          hero_cap: int = HERO_CAP, headroom: float = 0.55) -> Path:
    canvas = Image.new("RGB", (W, H), (0, 0, 0))
    sx = int(round(W * seam))
    lp = _headroom(Image.open(left).convert("RGB"), headroom)
    rp = _headroom(Image.open(right).convert("RGB"), headroom)
    canvas.paste(_cover(lp, sx, H, anchor_top=headroom > 0), (0, 0))
    canvas.paste(_cover(rp, W - sx, H, anchor_top=headroom > 0), (sx, 0))
    _tear(canvas, sx - 14, seed=seed)

    d = ImageDraw.Draw(canvas)

    # --- bottom yellow plate: the manufactured empty space ----------------
    d.rectangle([0, PLATE_TOP, W, PLATE_TOP + PLATE_H], fill=PLATE_FILL)
    pf = _font(round(PLATE_CAP / 0.72))
    t = plate_text.upper()
    while d.textlength(t, font=pf) > W - 48 and PLATE_CAP > 30:
        pf = _font(round(pf.size * 0.94))
    tw = d.textlength(t, font=pf)
    bb = pf.getbbox(t)
    d.text(((W - tw) / 2, PLATE_TOP + (PLATE_H - (bb[3] - bb[1])) / 2 - bb[1]),
           t, font=pf, fill=(0, 0, 0))

    # --- red name plate, directly above it --------------------------------
    nh = int(H * NAME_H)
    nw = int(W * NAME_W)
    ny = PLATE_TOP - nh
    d.rectangle([0, ny, nw, ny + nh], fill=NAME_FILL)
    nf = _font(round(NAME_CAP / 0.72))
    nb = nf.getbbox(name)
    d.text((26, ny + (nh - (nb[3] - nb[1])) / 2 - nb[1]), name, font=nf,
           fill=(255, 255, 255))

    # --- hero phrase, free-floating on the picture ------------------------
    # Kept strictly ABOVE the plates and wrapped to the frame, so it never
    # needs to sit on a face: the plates own the bottom, the hero owns the
    # sky/wall band, and the two panels' subjects sit between them.
    # Ladder the cap down until the hero fits TWO lines. Three lines of type at
    # the measured winner cap (115-152px) is 384-456px of the 720, and with the
    # two plates owning another 174 there is no picture left — the faces the
    # thumbnail exists to show end up behind the words. The winners' hero
    # phrases are two or three SHORT words for exactly this reason.
    def _lay(cap):
        f = _font(round(cap / 0.72))
        out, cur = [], ""
        for wd in hero.upper().split():
            trial = (cur + " " + wd).strip()
            if cur and d.textlength(trial, font=f) > W - 90:
                out.append(cur)
                cur = wd
            else:
                cur = trial
        if cur:
            out.append(cur)
        return f, out

    hf, lines = _lay(hero_cap)
    while len(lines) > 2 and hero_cap > 62:
        hero_cap = int(hero_cap * 0.92)
        hf, lines = _lay(hero_cap)
    lh = round(hf.size * 1.02)
    stroke = max(8, round(hero_cap / 6))
    block_h = lh * len(lines)
    # Top of frame, not just above the plates. With the headroom band at the top
    # of the picture this is the only place the type can go and still leave the
    # faces a full 280px between the type and the plates.
    y0 = 18 if headroom > 0 else max(14, ny - block_h - 18)

    glow = Image.new("L", (W, H), 0)
    gd = ImageDraw.Draw(glow)
    for i, ln in enumerate(lines):
        gd.text((40, y0 + i * lh), ln, font=hf, fill=255,
                stroke_width=stroke, stroke_fill=255)
    canvas.paste(Image.new("RGB", (W, H), (0, 0, 0)), (0, 0),
                 glow.filter(ImageFilter.GaussianBlur(22)))
    d = ImageDraw.Draw(canvas)
    for i, ln in enumerate(lines):
        _stroked(d, (40, y0 + i * lh), ln, hf, (255, 255, 255), stroke)

    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, "JPEG", quality=94, subsampling=0)
    print(f"{out.name}: hero {len(lines)} line(s) cap {hero_cap}px "
          f"({hero_cap / H:.3f} H), plate {PLATE_H}px @ y{PLATE_TOP} "
          f"({PLATE_TOP / H:.3f} H), seam {seam:.2f}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--left", required=True, type=Path)
    ap.add_argument("--right", required=True, type=Path)
    ap.add_argument("--hero", required=True)
    ap.add_argument("--plate", required=True)
    ap.add_argument("--name", default="JUDGE BOYD")
    ap.add_argument("--seam", type=float, default=SEAM)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--hero-cap", type=int, default=HERO_CAP)
    ap.add_argument("--headroom", type=float, default=0.55,
                    help="fraction of panel height to add above the subject")
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()
    build(a.left, a.right, a.hero, a.plate, a.out, name=a.name, seam=a.seam,
          seed=a.seed, hero_cap=a.hero_cap, headroom=a.headroom)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
