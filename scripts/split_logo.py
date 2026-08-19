"""Split the TTT mark into individually animatable elements.

The three glyph columns are not three letters: the star overlaps the third T
horizontally, so column-splitting yields T, T, and (T+star) fused. They separate
cleanly by COLOUR instead — ink #F2EEE3 vs accent #D42B2B — which is exact here
because the mark is flat two-colour with no blending between them.

Outputs T1/T2/T3/star as separate transparent PNGs, each trimmed to its own
bounds, plus a manifest recording where each sat in the original so the sting
can reassemble them in register.

Usage:  python scripts/split_logo.py [out_dir]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

SRC = Path(r"C:\Users\natha\OneDrive\Desktop\boyd-brand\logo_transparent.png")
INK = (0xF2, 0xEE, 0xE3)
RED = (0xD4, 0x2B, 0x2B)


def closer_to_red(c) -> bool:
    dr = abs(c[0] - RED[0]) + abs(c[1] - RED[1]) + abs(c[2] - RED[2])
    di = abs(c[0] - INK[0]) + abs(c[1] - INK[1]) + abs(c[2] - INK[2])
    return dr < di


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("research/blender/elements")
    out.mkdir(parents=True, exist_ok=True)

    im = Image.open(SRC).convert("RGBA")
    W, H = im.size
    px = im.load()

    # column runs to find the letter boundaries
    cols = [any(px[x, y][3] > 16 for y in range(H)) for x in range(W)]
    runs, inrun = [], False
    for x, v in enumerate(cols):
        if v and not inrun:
            s, inrun = x, True
        elif not v and inrun:
            runs.append((s, x)); inrun = False
    if inrun:
        runs.append((s, W))
    runs = [r for r in runs if r[1] - r[0] > 8]

    # ink layer and accent layer, full canvas each
    ink = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    red = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ip, rp = ink.load(), red.load()
    for y in range(H):
        for x in range(W):
            c = px[x, y]
            if c[3] <= 8:
                continue
            (rp if closer_to_red(c) else ip)[x, y] = c

    manifest = {"source": str(SRC), "canvas": [W, H], "elements": {}}

    def emit(name: str, layer: Image.Image, x0: int, x1: int):
        crop = layer.crop((x0, 0, x1, H))
        bb = crop.getbbox()
        if not bb:
            return
        glyph = crop.crop(bb)
        glyph.save(out / f"{name}.png")
        manifest["elements"][name] = {
            "file": f"{name}.png",
            "size": list(glyph.size),
            # origin in the ORIGINAL canvas — the sting reassembles from this
            "origin": [x0 + bb[0], bb[1]],
        }
        print(f"  {name:6s} {glyph.size[0]:4d}x{glyph.size[1]:4d}  at ({x0+bb[0]},{bb[1]})")

    # first two runs are clean Ts; the third holds T3 fused with the star
    emit("T1", ink, runs[0][0], runs[0][1])
    emit("T2", ink, runs[1][0], runs[1][1])
    emit("T3", ink, runs[2][0], runs[2][1])
    emit("star", red, runs[2][0], runs[2][1])

    (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"\n-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
