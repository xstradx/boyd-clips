"""Animated document plates — fly in, push in, highlighter DRAWS across the line.

Nathan, 2026-08-14: "theres no motion at all?? and when its highlighted its
actually supposed to be HIGHLIGHTED!! like literal motion!! also the card is
supposed to fly in and then inside the card instead of being titled have it
slowly zoom in on the relavent thing and then actually highlight it".

My own eval already said this — eval_open.py reported `M1 push-in FAIL` and
`M3 motion mean 0.41 median 0.00` — and I shipped static plates twice after
reading it. This is that fixed.

Per plate, 6.0s at 30fps:
    0.00-0.40  FLY IN from the right, decelerating, settles. No overshoot —
               0 of 7 measured broadcast references overshoot on a settle.
    0.40-3.00  PUSH IN toward the target line. Slow: 1.00 -> 1.18 over 2.6s.
    3.00-3.60  HIGHLIGHTER WIPES left to right across the line, 18 frames.
               Multiply, not paint-over, so the words stay readable under it —
               a marker pen darkens, it does not cover.
    3.60-6.00  hold on the highlighted line.

NO ROTATION. The +4.81 degree tilt was measured off Audit's static cards, but
Nathan explicitly does not want it — and a tilted plate fights a push-in, because
the zoom axis and the page axis stop agreeing.

Renderer: PIL, frame by frame. The measured bake-off put PIL at 0.186px error on
a moving edge against Blender's 0.021px; for a 0.6s wipe that is sub-pixel either
way, and PIL renders 2.1x faster, which matters when iterating. If the motion
bake-off says otherwise this swaps to the Blender kit's shader `wipe_x`, which is
the same mechanism done properly.

Usage:  python scripts/animate_docs.py [plate_index]
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from doc_cards import _text, body, head  # noqa: E402
from real_doc_cards import PLATES, SHOTS, snap, stitch  # noqa: E402

W, H, FPS = 1920, 1080, 30
GROUND = (0x15, 0x18, 0x1D)
PAPER = (0xF4, 0xF2, 0xED)
INK = (0x1A, 0x1A, 0x1A)
RED = (0xD4, 0x2B, 0x2B)
HIGHLIGHT = (0xFD, 0xC5, 0x01)

OUT = Path("out/review/castillo_anim")

F_IN = 12          # fly-in frames
F_PUSH_END = 90    # push-in finishes
F_WIPE = (90, 108)  # highlighter draw
F_TOTAL = 180
PUSH_TO = 1.18


def ease_out_cubic(t: float) -> float:
    return 1 - (1 - t) ** 3


def build_page(spec) -> tuple[Image.Image, list]:
    """The document with its caption bar, plus snapped highlight boxes."""
    im = (stitch(spec["shot"], spec["bands"]) if spec.get("bands")
          else Image.open(SHOTS / spec["shot"]).convert("RGB").crop(spec["crop"]))
    boxes = [snap(im, b) for b in spec["boxes"]]

    bar_h = 96
    card = Image.new("RGB", (im.width, im.height + bar_h), PAPER)
    card.paste(im, (0, 0))
    d = ImageDraw.Draw(card)
    d.rectangle([0, im.height, card.width, card.height], fill=INK)
    d.rectangle([28, im.height + 26, 36, im.height + 70], fill=RED)
    _text(d, (52, im.height + 20), spec["caption"].upper(), head(30), PAPER, spacing=1.4)
    _text(d, (52, im.height + 60), spec["source"], body(19), (0x9A, 0x95, 0x8C), spacing=1.0)
    return card, boxes


def highlighted(card: Image.Image, boxes, frac: float, pad=5) -> Image.Image:
    """Draw the marker across `frac` of each box. frac 0 = untouched, 1 = full."""
    if frac <= 0:
        return card
    out = card.copy()
    px = out.load()
    for (x0, y0, x1, y1) in boxes:
        edge = x0 + (x1 - x0 + pad * 2) * frac - pad
        for y in range(max(0, y0 - pad), min(out.height, y1 + pad)):
            for x in range(max(0, x0 - pad), min(out.width, int(edge))):
                r, g, b = px[x, y]
                # multiply by the highlighter colour: dark ink survives, paper goes yellow
                px[x, y] = (r * HIGHLIGHT[0] // 255,
                            g * HIGHLIGHT[1] // 255,
                            b * HIGHLIGHT[2] // 255)
    return out


def render(spec, idx: int) -> Path:
    card, boxes = build_page(spec)
    seq = OUT / f"p{idx:02d}"
    seq.mkdir(parents=True, exist_ok=True)

    # where the push-in aims: the centre of the first highlight box
    tx = (boxes[0][0] + boxes[0][2]) / 2 / card.width
    ty = (boxes[0][1] + boxes[0][3]) / 2 / card.height

    # base fit: the whole plate inside frame with a margin
    base = min((W - 200) / card.width, (H - 170) / card.height)

    # blurred backdrop, rendered once
    bg = card.resize((int(W * 2.2), int(W * 2.2 * card.height / card.width)), Image.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(26))
    bg = Image.blend(bg.convert("RGB"), Image.new("RGB", bg.size, GROUND), 0.34)
    backdrop = Image.new("RGB", (W, H), GROUND)
    backdrop.paste(bg, ((W - bg.width) // 2, (H - bg.height) // 2))

    for f in range(F_TOTAL):
        # --- highlighter progress -------------------------------------------
        if f < F_WIPE[0]:
            frac = 0.0
        elif f >= F_WIPE[1]:
            frac = 1.0
        else:
            frac = ease_out_cubic((f - F_WIPE[0]) / (F_WIPE[1] - F_WIPE[0]))
        plate = highlighted(card, boxes, frac)

        # --- push in ---------------------------------------------------------
        p = 0.0 if f <= F_IN else min(1.0, (f - F_IN) / (F_PUSH_END - F_IN))
        scale = base * (1 + (PUSH_TO - 1) * ease_out_cubic(p))
        pw, ph = int(card.width * scale), int(card.height * scale)
        plate = plate.resize((pw, ph), Image.LANCZOS)

        # --- fly in from the right, decelerating ------------------------------
        t = min(1.0, f / F_IN)
        slide = (1 - ease_out_cubic(t)) * (W * 0.55)

        # keep the push centred on the target as it grows
        cx = W / 2 - (tx - 0.5) * (pw - W) * p
        cy = H / 2 - (ty - 0.5) * (ph - H) * p
        x = int(cx - pw / 2 + slide)
        y = int(cy - ph / 2)

        frame = backdrop.copy()
        sh = Image.new("L", (pw, ph), 190)
        sh = sh.filter(ImageFilter.GaussianBlur(20))
        frame.paste(Image.new("RGB", (pw, ph), (0, 0, 0)), (x + 10, y + 16), sh)
        frame.paste(plate, (x, y))
        frame.save(seq / f"f_{f:04d}.png")

    mp4 = OUT / f"plate_{idx:02d}.mp4"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-framerate", str(FPS), "-i", str(seq / "f_%04d.png"),
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
        "-shortest", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p", "-profile:v", "high",
        "-c:a", "aac", "-b:a", "192k", str(mp4)], check=True)
    for p_ in seq.glob("*.png"):
        p_.unlink()
    seq.rmdir()
    return mp4


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    only = int(sys.argv[1]) if len(sys.argv) > 1 else None
    for i, spec in enumerate(PLATES, 1):
        if only and i != only:
            continue
        mp4 = render(spec, i)
        print(f"  plate {i}  {spec['caption'][:46]:46s} -> {mp4.name}")
    print(f"\n-> {OUT.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
