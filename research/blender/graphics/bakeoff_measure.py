"""Measure the three lower-third implementations against each other.

    python bakeoff_measure.py

Everything here reads the DELIVERED PNGs with ffmpeg (measure.read_ffmpeg),
never with Blender's Image.pixels (BLENDER-CAPABILITY 4.2).
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bakeoff_spec as S
import measure as M

HERE = os.path.dirname(os.path.abspath(__file__))
DIRS = {"blender": "renders/bakeoff_blender",
        "ffmpeg": "renders/bakeoff_ffmpeg",
        "pil": "renders/bakeoff_pil"}
HOLD = 60          # a frame where everything is fully open and static


def load(k, f):
    return M.read_ffmpeg(os.path.join(HERE, DIRS[k], "f_%04d.png" % f))


def glyph_aa(img):
    """AA on the NAME glyphs, measured in the RED channel.

    The name is ink over an opaque-ish plate, so its antialiasing shows up in
    COLOUR, not in alpha: plate R = 0x15 (21), ink R = 0xF2 (242). Anything in
    between is an antialiased glyph edge pixel. Counting distinct intermediate
    levels along a scanline through the middle of the cap height is a direct
    read of how many coverage steps the rasteriser produced.
    """
    y = S.NAME_BASE - S.NAME_CAP // 2
    row = img[y, S.X0 + S.RULE_W + 10:S.X0 + S.W1 - 6, 0].astype(int)
    mid = row[(row > 30) & (row < 232)]
    # count edge CROSSINGS so the ratio is per-edge, not per-pixel
    solid = (row > 232).astype(int)
    crossings = int(np.abs(np.diff(solid)).sum())
    return dict(distinct_R_levels=int(len(np.unique(row))),
                intermediate_px=int(len(mid)),
                glyph_edges=crossings,
                px_per_edge=round(len(mid) / max(crossings, 1), 2))


def edge_subpixel(k):
    """Where does the wipe edge land, per frame, to sub-pixel precision?

    Measured by summing alpha along the plate row and comparing with the
    analytic edge position the spec asks for. A whole-pixel implementation
    quantises; a supersampled one does not.
    """
    # y must be a row with NOTHING on it but the plate: above the name ink
    # (which starts at 780) and to the right of the accent rule (which is
    # alpha 255, not 237). Including either makes every renderer look 12-16px
    # wrong - that was a fault in this measurement, not in the renderers.
    y = S.T1_TOP + 2
    x0 = S.X0 + S.RULE_W
    rows = []
    for f in range(5, 13):
        img = load(k, f)
        row = img[y, :, 3].astype(float)
        want = S.edge_tier1(f)
        seg = row[x0:S.X0 + S.W1 + 6] / 237.0
        got = x0 + float(seg.sum())
        rows.append((f, round(want, 2), round(got, 2), round(got - want, 2)))
    return rows


def main():
    print("=" * 74)
    print("1. GLYPH ANTIALIASING  (name band, frame %d)" % HOLD)
    print("=" * 74)
    for k in DIRS:
        print("  %-8s %s" % (k, glyph_aa(load(k, HOLD))))

    print()
    print("=" * 74)
    print("2. WHOLE-FRAME ALPHA STRUCTURE (frame %d)" % HOLD)
    print("=" * 74)
    for k in DIRS:
        img = load(k, HOLD)
        print("  %-8s %s" % (k, M.aa_stats(img)))

    print()
    print("=" * 74)
    print("3. BRAND COLOUR ON DELIVERED PIXELS (frame %d)" % HOLD)
    print("=" * 74)
    for k in DIRS:
        img = load(k, HOLD)
        print("  %-8s plate=%s  red=%s  ink_top3=%s"
              % (k,
                 M.hexat(img, S.X0 + 300, S.T1_TOP + 8),
                 M.hexat(img, S.X0 + 300, S.T2_TOP + 20),
                 [c for c, _ in M.unique_colors(img)[:3]]))

    print()
    print("=" * 74)
    print("4. WIPE EDGE, SUB-PIXEL  (frame, wanted_x, measured_x, error_px)")
    print("=" * 74)
    for k in DIRS:
        rows = edge_subpixel(k)
        err = [abs(r[3]) for r in rows]
        print("  %-8s max|err|=%.3f px  mean|err|=%.3f px" %
              (k, max(err), sum(err) / len(err)))
        print("           %s" % rows)

    print()
    print("=" * 74)
    print("5. GEOMETRY AGREEMENT vs blender (frame %d)" % HOLD)
    print("=" * 74)
    ref = load("blender", HOLD)
    for k in DIRS:
        img = load(k, HOLD)
        a = (img[..., 3] > 128)
        b = (ref[..., 3] > 128)
        inter = int((a & b).sum())
        union = int((a | b).sum())
        nz = np.nonzero(a)
        print("  %-8s bbox x%d..%d y%d..%d  IoU_vs_blender=%.4f"
              % (k, nz[1].min(), nz[1].max(), nz[0].min(), nz[0].max(),
                 inter / max(union, 1)))

    print()
    print("=" * 74)
    print("6. SOURCE SIZE (lines of code, blank+comment excluded)")
    print("=" * 74)
    files = {"blender": ["boyd_gfx.py", "bakeoff_blender.py"],
             "ffmpeg": ["bakeoff_ffmpeg.py"],
             "pil": ["bakeoff_pil.py"]}
    for k, fs in files.items():
        tot = 0
        per = []
        for fn in fs:
            n = 0
            block = False
            for ln in open(os.path.join(HERE, fn), encoding="utf-8"):
                t = ln.strip()
                if t.startswith('"""') and t.count('"""') == 1:
                    block = not block
                    continue
                if block or not t or t.startswith("#") or t.startswith('"""'):
                    continue
                n += 1
            per.append("%s=%d" % (fn, n))
            tot += n
        print("  %-8s total=%-5d  %s" % (k, tot, " ".join(per)))


if __name__ == "__main__":
    main()
