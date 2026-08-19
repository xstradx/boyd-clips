"""Build YouTube banner variants from the channel avatar.

The avatar sits on a flat #15181D field, so the canvas can be extended without
any reconstruction — the logo is lifted off its background and re-placed, which
is lossless rather than an upscale or a fake.

YouTube crops banners hard and differently per device. Only the centre
1546x423 of a 2560x1440 image is guaranteed visible everywhere, so anything
that must be seen lives inside that box:

    2560 x 1440   full asset (TV)
    2560 x  423   desktop
    1546 x  423   MOBILE / safe area  <- design to this

Usage:  python scripts/make_banner.py [out_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BG = (0x15, 0x18, 0x1D)
INK = (0xF2, 0xEE, 0xE3)
RED = (0xD4, 0x2B, 0x2B)

W, H = 2560, 1440
SAFE_W, SAFE_H = 1546, 423
FONTS = Path(r"C:\Users\natha\Projects\boyd-clips\assets\fonts")
WIN = Path(r"C:\Windows\Fonts")


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for p in (FONTS / "Anton-Regular.ttf", FONTS / "BebasNeue-Regular.ttf",
              WIN / "ariblk.ttf", WIN / "arialbd.ttf"):
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def extract_logo(avatar: Path) -> Image.Image:
    """Lift the mark off its flat background, trimmed to its own bounds."""
    im = Image.open(avatar).convert("RGB")
    px = im.load()
    w, h = im.size
    mask = Image.new("L", (w, h), 0)
    mp = mask.load()
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            # anything meaningfully brighter or redder than the flat field
            if abs(r - BG[0]) + abs(g - BG[1]) + abs(b - BG[2]) > 40:
                mp[x, y] = 255
    rgba = im.convert("RGBA")
    rgba.putalpha(mask)
    return rgba.crop(mask.getbbox())


def paste_fit(canvas: Image.Image, logo: Image.Image, box, anchor="center"):
    bx, by, bw, bh = box
    scale = min(bw / logo.width, bh / logo.height)
    lg = logo.resize((max(1, int(logo.width * scale)),
                      max(1, int(logo.height * scale))), Image.LANCZOS)
    x = bx + (bw - lg.width) // 2 if anchor == "center" else bx
    y = by + (bh - lg.height) // 2
    canvas.paste(lg, (x, y), lg)
    return lg, (x, y)


def base_canvas() -> tuple[Image.Image, tuple[int, int, int, int]]:
    c = Image.new("RGB", (W, H), BG)
    safe = ((W - SAFE_W) // 2, (H - SAFE_H) // 2, SAFE_W, SAFE_H)
    return c, safe


def variant_mark_only(logo):
    """The mark, centred, breathing. Reads at every crop."""
    c, safe = base_canvas()
    sx, sy, sw, sh = safe
    paste_fit(c, logo, (sx, sy + int(sh * 0.10), sw, int(sh * 0.72)))
    return c


def variant_wordmark(logo):
    """Mark plus the channel name — the version that tells a new viewer who you are."""
    c, safe = base_canvas()
    sx, sy, sw, sh = safe
    d = ImageDraw.Draw(c)
    _, (lx, ly) = paste_fit(c, logo, (sx, sy + int(sh * 0.02), sw, int(sh * 0.46)))
    f = load_font(int(sh * 0.20))
    t = "TEXAS TRIAL TRACKER"
    bb = d.textbbox((0, 0), t, font=f)
    d.text(((W - (bb[2] - bb[0])) // 2 - bb[0], sy + int(sh * 0.60)),
           t, font=f, fill=INK)
    return c


def variant_tagline(logo):
    """Mark, name, and what the channel actually is."""
    c, safe = base_canvas()
    sx, sy, sw, sh = safe
    d = ImageDraw.Draw(c)
    paste_fit(c, logo, (sx, sy - int(sh * 0.02), sw, int(sh * 0.40)))
    f1 = load_font(int(sh * 0.17))
    f2 = load_font(int(sh * 0.085))
    t1 = "TEXAS TRIAL TRACKER"
    t2 = "187TH DISTRICT COURT  ·  BEXAR COUNTY  ·  NEW CASES DAILY"
    for t, f, yy, col in ((t1, f1, 0.50, INK), (t2, f2, 0.74, (0xA8, 0xA4, 0x9C))):
        bb = d.textbbox((0, 0), t, font=f)
        d.text(((W - (bb[2] - bb[0])) // 2 - bb[0], sy + int(sh * yy)),
               t, font=f, fill=col)
    return c


def variant_rule(logo):
    """Mark with a red rule — borrows the star's accent as structure."""
    c, safe = base_canvas()
    sx, sy, sw, sh = safe
    d = ImageDraw.Draw(c)
    paste_fit(c, logo, (sx, sy + int(sh * 0.06), sw, int(sh * 0.52)))
    f = load_font(int(sh * 0.13))
    t = "TEXAS TRIAL TRACKER"
    bb = d.textbbox((0, 0), t, font=f)
    tw = bb[2] - bb[0]
    ty = sy + int(sh * 0.70)
    d.text(((W - tw) // 2 - bb[0], ty), t, font=f, fill=INK)
    ry = ty + int(sh * 0.155)
    d.rectangle([(W - tw) // 2, ry, (W + tw) // 2, ry + 8], fill=RED)
    return c


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("out/brand")
    out.mkdir(parents=True, exist_ok=True)
    avatar = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(
        r"C:\Users\natha\OneDrive\Desktop\boyd-moments\avatar.png")

    logo = extract_logo(avatar)
    print(f"logo lifted: {logo.size}")
    logo.save(out / "logo_transparent.png")

    for name, fn in (("01_mark", variant_mark_only),
                     ("02_wordmark", variant_wordmark),
                     ("03_tagline", variant_tagline),
                     ("04_rule", variant_rule)):
        img = fn(logo)
        img.save(out / f"banner_{name}.png")
        # what a phone actually shows
        sx, sy = (W - SAFE_W) // 2, (H - SAFE_H) // 2
        img.crop((sx, sy, sx + SAFE_W, sy + SAFE_H)).save(out / f"safe_{name}.png")
        print(f"  {name}")

    print(f"\n-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
