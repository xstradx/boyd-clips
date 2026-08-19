"""Watermark set v2 — mark only (TTT + star), translucent.

Nathan, 2026-08-11: "water marks on the video should be a little translucent
with just the cut out ttt and star maybe" — so the wordmark lockups from v1 are
dropped. This emits the mark alone at several opacities and two colourways, and
critically PREVIEWS EACH ONE COMPOSITED OVER REAL FOOTAGE rather than over a
flat swatch. A watermark that reads on a grey plate can vanish on a bright
courtroom wall; the flat-plate preview is the thing that hides that.

Placement: TOP-RIGHT. YouTube's own branding watermark and the player controls
both live bottom-right, and the progress bar eats the bottom edge on hover.

Size: 6% of frame width. Broadcast bug convention is 4-8%; below 4% it is
illegible after YouTube's compression, above 8% it starts competing with the
content.

Opacity: 30-55%. A persistent burn-in sits lower than a title — it should be
readable when looked for and ignorable when not.

Usage:  python scripts/make_watermarks_v2.py [out_dir]
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageFilter

LOGO = Path(r"C:\Users\natha\OneDrive\Desktop\boyd-brand\logo_transparent.png")
FOOTAGE = Path("out/review/2026-08-06_SPSHGzlOe8c/longform.mp4")
INK = (0xF2, 0xEE, 0xE3)

# frame width fraction, and where the mark sits relative to the safe area
WIDTH_FRAC = 0.06
MARGIN_FRAC = 0.035          # from frame edge, inside the 5% title-safe area


def recolour(img: Image.Image, ink=None, keep_star=True) -> Image.Image:
    """Recolour the cream ink. The red star is left alone unless keep_star=False."""
    out = img.copy()
    px = out.load()
    w, h = out.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a <= 8:
                continue
            is_star = r > g + 40
            if is_star and keep_star:
                continue
            tgt = ink if ink else (r, g, b)
            px[x, y] = (tgt[0], tgt[1], tgt[2], a)
    return out


def with_shadow(img: Image.Image, blur: int = 6, alpha: int = 150) -> Image.Image:
    """A soft dark halo so the mark survives a bright background.

    Not a 2010s drop shadow — it is centred, not offset, so it reads as
    separation rather than as fake depth.
    """
    pad = blur * 3
    W, H = img.width + pad * 2, img.height + pad * 2
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    mask = Image.new("L", (W, H), 0)
    mask.paste(img.getchannel("A"), (pad, pad))
    mask = mask.filter(ImageFilter.GaussianBlur(blur))
    mask = mask.point(lambda v: int(v * alpha / 255))
    shadow.putalpha(mask)
    shadow = Image.composite(Image.new("RGBA", (W, H), (0, 0, 0, 255)), shadow, mask)
    shadow.putalpha(mask)
    out = shadow
    out.paste(img, (pad, pad), img)
    return out


def fade(img: Image.Image, pct: int) -> Image.Image:
    out = img.copy()
    out.putalpha(out.getchannel("A").point(lambda v: int(v * pct / 100)))
    return out


def grab_frames(n: int = 2) -> list[Image.Image]:
    """Pull a dark and a bright frame from the real longform render."""
    frames = []
    tmp = Path("research/blender/renders/_wm_frames")
    tmp.mkdir(parents=True, exist_ok=True)
    if not FOOTAGE.exists():
        print(f"  !! no footage at {FOOTAGE} — falling back to flat plates")
        return []
    for i, t in enumerate(("00:00:12", "00:01:40")):
        p = tmp / f"f{i}.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", t, "-i", str(FOOTAGE),
                        "-frames:v", "1", str(p)], check=True)
        im = Image.open(p).convert("RGB")
        lum = sum(im.convert("L").resize((32, 18)).getdata()) / (32 * 18)
        print(f"  frame @{t}  {im.size[0]}x{im.size[1]}  mean luma {lum:.0f}")
        frames.append(im)
    return frames


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        r"C:\Users\natha\OneDrive\Desktop\boyd-brand\watermarks_v2")
    out.mkdir(parents=True, exist_ok=True)

    mark = Image.open(LOGO).convert("RGBA")
    print(f"source mark {mark.size[0]}x{mark.size[1]}")

    colourways = {
        "brand": recolour(mark, INK, keep_star=True),          # cream ink, red star
        "mono":  recolour(mark, (255, 255, 255), keep_star=False),  # all white
    }

    print("\nemitting mark-only watermarks (2x display size, 4K-safe):")
    variants = {}
    for cname, cimg in colourways.items():
        for halo in (False, True):
            base = with_shadow(cimg) if halo else cimg
            for pct in (30, 40, 55):
                key = f"{cname}{'_halo' if halo else ''}_{pct}"
                # 2x the 1080p display size so it stays crisp if reused at 4K
                target_w = int(1920 * WIDTH_FRAC * 2)
                s = target_w / base.width
                v = base.resize((target_w, max(1, int(base.height * s))), Image.LANCZOS)
                v = fade(v, pct)
                v.save(out / f"wm_{key}.png")
                variants[key] = v
    print(f"  {len(variants)} files")

    # --- the real test: composite over actual footage -----------------------
    print("\ncompositing over real footage:")
    frames = grab_frames()
    show = ["brand_30", "brand_40", "brand_55", "mono_40", "brand_halo_40", "mono_halo_40"]

    for fi, frame in enumerate(frames):
        FW, FH = frame.size
        sheet = Image.new("RGB", (FW, FH * len(show) // 3 // 2 or FH), (0, 0, 0))
        # one full-frame composite per option, stacked in a 2x3 grid at 1/2 scale
        cell_w, cell_h = FW // 2, FH // 2
        grid = Image.new("RGB", (cell_w * 3, cell_h * 2), (10, 10, 10))
        for i, key in enumerate(show):
            comp = frame.copy().convert("RGBA")
            wm = variants[key]
            s = (FW * WIDTH_FRAC) / wm.width
            w = wm.resize((int(wm.width * s), max(1, int(wm.height * s))), Image.LANCZOS)
            m = int(FW * MARGIN_FRAC)
            comp.alpha_composite(w, (FW - w.width - m, m))
            cell = comp.convert("RGB").resize((cell_w, cell_h), Image.LANCZOS)
            grid.paste(cell, ((i % 3) * cell_w, (i // 3) * cell_h))
        grid.save(out / f"preview_footage_{fi}.png")
        print(f"  preview_footage_{fi}.png  ({' | '.join(show)})")

        # and one 1:1 crop of the corner so the detail is judgeable
        crop_w = int(FW * 0.22)
        strip = Image.new("RGB", (crop_w * len(show), int(FH * 0.16)), (10, 10, 10))
        for i, key in enumerate(show):
            comp = frame.copy().convert("RGBA")
            wm = variants[key]
            s = (FW * WIDTH_FRAC) / wm.width
            w = wm.resize((int(wm.width * s), max(1, int(wm.height * s))), Image.LANCZOS)
            m = int(FW * MARGIN_FRAC)
            comp.alpha_composite(w, (FW - w.width - m, m))
            strip.paste(comp.convert("RGB").crop(
                (FW - crop_w, 0, FW, int(FH * 0.16))), (i * crop_w, 0))
        strip.save(out / f"preview_corner_{fi}.png")
        print(f"  preview_corner_{fi}.png  (1:1 detail)")

    print(f"\n-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
