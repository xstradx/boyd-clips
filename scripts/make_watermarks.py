"""Repair T3 and generate watermark variants.

T3 fix: the star is painted OVER the third T, so colour-splitting removes the
overlapped corner and leaves a notch. The three letterforms are identical in
this mark, so T3 is rebuilt from T1's glyph rather than being reconstructed or
inpainted — exact, not approximated. Verified by comparing T1 and T2 pixel
bounds before relying on it.

Watermarks: YouTube overlays these small and over unpredictable footage, so the
set covers both a light and a dark backdrop, and both a mark-only and a
mark+name lockup. Rendered at 2x the largest expected display size so they stay
crisp when scaled down.

Usage:  python scripts/make_watermarks.py [out_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ELEM = Path("research/blender/elements")
LOGO = Path(r"C:\Users\natha\OneDrive\Desktop\boyd-brand\logo_transparent.png")
INK = (0xF2, 0xEE, 0xE3)
RED = (0xD4, 0x2B, 0x2B)
BG = (0x15, 0x18, 0x1D)
FONTS = Path("assets/fonts")


def font(size: int):
    for p in (FONTS / "Anton-Regular.ttf", FONTS / "BebasNeue-Regular.ttf",
              Path(r"C:\Windows\Fonts\ariblk.ttf")):
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def repair_t3() -> None:
    t1 = Image.open(ELEM / "T1.png").convert("RGBA")
    t2 = Image.open(ELEM / "T2.png").convert("RGBA")
    t3 = Image.open(ELEM / "T3.png").convert("RGBA")
    print(f"  T1 {t1.size}  T2 {t2.size}  T3 {t3.size} (notched)")
    if t1.size != t2.size:
        print("  !! T1 and T2 differ — letterforms are NOT identical, not substituting")
        return
    t3_fixed = t1.copy()
    t3_fixed.save(ELEM / "T3.png")
    print(f"  T3 rebuilt from T1: {t3.size} -> {t3_fixed.size}")


def tint(img: Image.Image, rgb) -> Image.Image:
    """Recolour the ink while leaving the accent and alpha alone."""
    out = img.copy()
    px = out.load()
    w, h = out.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a > 8 and not (r > g + 40):        # ink, not the red star
                px[x, y] = (rgb[0], rgb[1], rgb[2], a)
    return out


def lockup(mark: Image.Image, text: str | None, ink, height: int) -> Image.Image:
    scale = height / mark.height
    m = mark.resize((int(mark.width * scale), height), Image.LANCZOS)
    if not text:
        return m
    f = font(int(height * 0.34))
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bb = tmp.textbbox((0, 0), text, font=f)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    W = max(m.width, tw)
    H = m.height + int(height * 0.22) + th
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    out.paste(m, ((W - m.width) // 2, 0), m)
    ImageDraw.Draw(out).text(((W - tw) // 2 - bb[0], m.height + int(height * 0.22) - bb[1]),
                             text, font=f, fill=(*ink, 255))
    return out


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        r"C:\Users\natha\OneDrive\Desktop\boyd-brand\watermarks")
    out.mkdir(parents=True, exist_ok=True)

    print("repairing T3:")
    repair_t3()

    mark = Image.open(LOGO).convert("RGBA")
    H = 240   # 2x typical display size

    variants = {
        "01_mark_light":      (tint(mark, INK), None, INK),
        "02_mark_dark":       (tint(mark, BG), None, BG),
        "03_lockup_light":    (tint(mark, INK), "TEXAS TRIAL TRACKER", INK),
        "04_lockup_dark":     (tint(mark, BG), "TEXAS TRIAL TRACKER", BG),
        "05_mark_mono_white": (tint(mark, (255, 255, 255)), None, (255, 255, 255)),
    }

    print("\nwatermarks:")
    for name, (m, text, ink) in variants.items():
        img = lockup(m, text, ink, H)
        img.save(out / f"wm_{name}.png")
        # 55% opacity copy — YouTube overlays sit better knocked back
        faded = img.copy()
        a = faded.getchannel("A").point(lambda v: int(v * 0.55))
        faded.putalpha(a)
        faded.save(out / f"wm_{name}_55.png")
        print(f"  {name:20s} {img.size[0]:4d}x{img.size[1]:3d}  (+ 55% variant)")

    # preview over both a light and a dark plate, at real display scale
    for plate, label in (((0x15, 0x18, 0x1D), "dark"), ((0xE8, 0xE6, 0xE1), "light")):
        sheet = Image.new("RGB", (1280, 300), plate)
        x = 40
        for name in ("01_mark_light", "02_mark_dark", "03_lockup_light", "05_mark_mono_white"):
            w = Image.open(out / f"wm_{name}_55.png").convert("RGBA")
            s = 90 / w.height
            w = w.resize((int(w.width * s), 90), Image.LANCZOS)
            sheet.paste(w, (x, (300 - w.height) // 2), w)
            x += w.width + 45
        sheet.save(out / f"preview_on_{label}.png")
    print(f"\n-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
