"""Preview the v2 watermarks in the two places they actually have to survive.

The Boyd longform is a Zoom two-panel composite letterboxed top and bottom, so
the top-right corner is dead black — a watermark there never covers content and
never fights it. That is the intended home. But Shorts reframe to 9:16 and future
footage may be full-bleed, so the same mark is also composited OVER the bright
chamber panel as a stress test. A watermark that only works on its easy
background is not finished.

Usage:  python scripts/wm_preview.py
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

WM = Path(r"C:\Users\natha\OneDrive\Desktop\boyd-brand\watermarks_v2")
LONG = Path("out/review/2026-08-06_SPSHGzlOe8c/longform.mp4")
SHORT = Path("out/review/2026-08-06_SPSHGzlOe8c/short.mp4")
SHOW = ["brand_30", "brand_40", "brand_55", "mono_40", "brand_halo_40", "mono_halo_40"]


def frame(video: Path, t: str) -> Image.Image:
    p = Path("research/blender/renders/_wm_scan") / f"pv_{video.stem}_{t.replace(':','')}.png"
    p.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", t, "-i", str(video),
                    "-frames:v", "1", str(p)], check=True)
    return Image.open(p).convert("RGBA")


def place(base: Image.Image, key: str, anchor: str, frac: float = 0.06) -> Image.Image:
    wm = Image.open(WM / f"wm_{key}.png").convert("RGBA")
    FW, FH = base.size
    s = (FW * frac) / wm.width
    w = wm.resize((max(1, int(wm.width * s)), max(1, int(wm.height * s))), Image.LANCZOS)
    m = int(FW * 0.035)
    if anchor == "tr":                       # top-right, in the letterbox bar
        xy = (FW - w.width - m, m)
    elif anchor == "content":                # over the bright chamber — stress test
        xy = (int(FW * 0.74), int(FH * 0.30))
    else:                                    # bottom-right of the content area
        xy = (FW - w.width - m, int(FH * 0.60))
    out = base.copy()
    out.alpha_composite(w, xy)
    return out


def label(img: Image.Image, text: str) -> Image.Image:
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 260, 34], fill=(0, 0, 0, 220))
    d.text((10, 9), text, fill=(255, 220, 90, 255))
    return img


def sheet(base: Image.Image, anchor: str, title: str, out_path: Path, crop=None):
    cells = []
    for k in SHOW:
        c = place(base, k, anchor)
        if crop:
            c = c.crop(crop)
        cells.append(label(c, f"{k}  [{title}]"))
    cw, ch = cells[0].size
    scale = min(1.0, 640 / cw)
    cw, ch = int(cw * scale), int(ch * scale)
    grid = Image.new("RGB", (cw * 3, ch * 2), (12, 12, 12))
    for i, c in enumerate(cells):
        grid.paste(c.convert("RGB").resize((cw, ch), Image.LANCZOS),
                   ((i % 3) * cw, (i // 3) * ch))
    grid.save(out_path)
    print(f"  {out_path.name}  {grid.size[0]}x{grid.size[1]}")


def main() -> int:
    print("previews:")
    f = frame(LONG, "00:01:00")
    FW, FH = f.size
    # 1) intended home: top-right letterbox, shown as a 1:1 corner crop
    sheet(f, "tr", "top-right letterbox",
          WM / "PV_1_letterbox_corner.png",
          crop=(int(FW * 0.68), 0, FW, int(FH * 0.22)))
    # 2) stress test: same mark over the bright chamber panel
    sheet(f, "content", "OVER BRIGHT CONTENT",
          WM / "PV_2_stress_bright.png",
          crop=(int(FW * 0.68), int(FH * 0.22), FW, int(FH * 0.48)))
    # 3) the Short, full frame — different aspect, different framing
    if SHORT.exists():
        s = frame(SHORT, "00:00:06")
        sheet(s, "tr", "Short 9:16", WM / "PV_3_short.png")
    print(f"\n-> {WM}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
