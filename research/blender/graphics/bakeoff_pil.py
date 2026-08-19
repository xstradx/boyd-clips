"""Implementation B: Python + PIL. Same lower third as bakeoff_spec.

    python bakeoff_pil.py [outdir]

Clipping is done by drawing each layer to its own RGBA image and then zeroing
the alpha outside the wipe edge, which is the direct analogue of the shader
threshold Blender uses - except that the cut lands on a whole pixel, so the
moving edge has no sub-pixel position. That is the measurable difference.
"""
import os
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bakeoff_spec as S

HERE = os.path.dirname(os.path.abspath(__file__))


def font_px(path, cap_px, cap_per_em):
    return ImageFont.truetype(path, int(round(cap_px / cap_per_em)))


def draw_tracked(dr, xy, text, font, fill, track_per_1000em, em_px):
    """PIL has no letterspacing, so advance by hand, glyph by glyph."""
    x, y = xy
    extra = track_per_1000em / 1000.0 * em_px
    for ch in text:
        dr.text((x, y), ch, font=font, fill=fill, anchor="ls")
        x += dr.textlength(ch, font=font) + extra
    return x


def clip_x(img, edge_px):
    """Zero alpha to the right of edge_px. Whole-pixel cut."""
    a = np.asarray(img).copy()
    e = int(round(edge_px))
    if e < a.shape[1]:
        a[:, max(e, 0):, 3] = 0
    if e <= 0:
        a[..., 3] = 0
    return Image.fromarray(a)


def clip_y(img, edge_px):
    a = np.asarray(img).copy()
    e = int(round(edge_px))
    if e < a.shape[0]:
        a[max(e, 0):, :, 3] = 0
    return Image.fromarray(a)


def build(outdir=None):
    outdir = outdir or os.path.join(HERE, "renders", "bakeoff_pil")
    os.makedirs(outdir, exist_ok=True)
    ink = S.hexrgb(S.INK_HEX)
    ground = S.hexrgb(S.GROUND_HEX)
    red = S.hexrgb(S.RED_HEX)
    f_name = font_px(S.NAME_FONT, S.NAME_CAP, S.NAME_CAP_PER_EM)
    f_charge = font_px(S.CHARGE_FONT, S.CHARGE_CAP, S.CHARGE_CAP_PER_EM)
    em_charge = int(round(S.CHARGE_CAP / S.CHARGE_CAP_PER_EM))

    t0 = time.perf_counter()
    for fr in range(1, S.FRAMES + 1):
        # --- tier 1 layer ------------------------------------------------
        l1 = Image.new("RGBA", (S.W, S.H), (0, 0, 0, 0))
        d1 = ImageDraw.Draw(l1)
        d1.rectangle([S.X0, S.T1_TOP, S.X0 + S.W1 - 1, S.T1_TOP + S.T1_H - 1],
                     fill=ground + (int(round(255 * S.PLATE_ALPHA)),))
        # ImageDraw does NOT alpha-blend, it OVERWRITES. Drawing the 14%-alpha
        # hairline straight onto the plate replaced the plate pixels with
        # (242,238,227,36) instead of compositing - measured as an ink-coloured
        # row where a barely-visible rule was intended. Translucent elements
        # need their own layer and alpha_composite.
        lh = Image.new("RGBA", (S.W, S.H), (0, 0, 0, 0))
        ImageDraw.Draw(lh).rectangle(
            [S.X0 + S.RULE_W, S.T1_TOP + S.T1_H - 1,
             S.X0 + S.W1 - 1, S.T1_TOP + S.T1_H - 1], fill=ink + (36,))
        l1.alpha_composite(lh)
        l1 = clip_x(l1, S.edge_tier1(fr))

        ln = Image.new("RGBA", (S.W, S.H), (0, 0, 0, 0))
        ImageDraw.Draw(ln).text((S.X0 + S.RULE_W + S.PAD_L, S.NAME_BASE),
                                S.NAME, font=f_name, fill=ink + (255,),
                                anchor="ls")
        ln = clip_x(ln, S.edge_tier1(fr) - S.LEAD)

        # --- tier 2 layer ------------------------------------------------
        l2 = Image.new("RGBA", (S.W, S.H), (0, 0, 0, 0))
        ImageDraw.Draw(l2).rectangle(
            [S.X0, S.T2_TOP, S.X0 + S.W2 - 1, S.T2_TOP + S.T2_H - 1],
            fill=red + (255,))
        l2 = clip_x(l2, S.edge_tier2(fr))

        lc = Image.new("RGBA", (S.W, S.H), (0, 0, 0, 0))
        draw_tracked(ImageDraw.Draw(lc),
                     (S.X0 + S.RULE_W + S.PAD_L, S.CHARGE_BASE), S.CHARGE,
                     f_charge, ink + (255,), S.CHARGE_TRACK, em_charge)
        lc = clip_x(lc, S.edge_tier2(fr) - S.LEAD)

        # --- accent rule --------------------------------------------------
        lr = Image.new("RGBA", (S.W, S.H), (0, 0, 0, 0))
        ImageDraw.Draw(lr).rectangle(
            [S.X0, S.T1_TOP, S.X0 + S.RULE_W - 1,
             S.T1_TOP + S.T1_H + S.T2_H - 1], fill=red + (255,))
        lr = clip_y(lr, S.edge_rule(fr))

        out = Image.new("RGBA", (S.W, S.H), (0, 0, 0, 0))
        for layer in (l1, l2, lr, ln, lc):
            out.alpha_composite(layer)
        out.save(os.path.join(outdir, "f_%04d.png" % fr), compress_level=1)
    dt = time.perf_counter() - t0
    print("PIL   %d frames in %.2fs  (%.4f s/frame)  -> %s"
          % (S.FRAMES, dt, dt / S.FRAMES, outdir))
    return dt


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else None)
