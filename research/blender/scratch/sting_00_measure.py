"""
sting_00_measure.py -- measure logo_transparent.png so the mark can be REBUILT as
clean vector polygons (STING-SPEC.md sec 12 blocker).

Run with Blender's bundled python (numpy 1.26.4):
  blender.exe -b --python sting_00_measure.py

Reads raw RGBA via external ffmpeg (BLENDER-CAPABILITY.md sec 4.2: never Image.pixels).
"""
import os, subprocess, sys
import numpy as np

FFMPEG = r"C:\ffmpeg\ffmpeg.exe"
LOGO   = r"C:\Users\natha\OneDrive\Desktop\Boyd Clips\boyd-brand\logo_transparent.png"
SCRATCH = r"C:\Users\natha\AppData\Local\Temp\claude\C--Users-natha\13b079a6-7fa2-406d-a5ce-b8f3295a6b37\scratchpad"
os.makedirs(SCRATCH, exist_ok=True)
RAW = os.path.join(SCRATCH, "logo_rgba.raw")

W, H = 1413, 540

subprocess.run([FFMPEG, "-v", "error", "-y", "-i", LOGO,
                "-f", "rawvideo", "-pix_fmt", "rgba", RAW], check=True)
a = np.fromfile(RAW, dtype=np.uint8).reshape(H, W, 4)   # row 0 = TOP row (ffmpeg is top-down)
print("shape", a.shape)

alpha = a[:, :, 3]
rgb   = a[:, :, :3].astype(np.int16)

print("\n=== ALPHA AUDIT (spec sec 12) ===")
print("alpha==0   :", int((alpha == 0).sum()))
print("alpha==255 :", int((alpha == 255).sum()))
mid = ((alpha > 0) & (alpha < 255))
print("0<alpha<255:", int(mid.sum()), "-> %.4f%%" % (100.0 * mid.sum() / alpha.size))

op = alpha == 255
opx = rgb[op]
uniq = np.unique(opx.reshape(-1, 3), axis=0)
print("distinct opaque RGB values:", len(uniq))

# --- classify ink / red / fringe -------------------------------------------
# ink  ~ (242,238,227)  red ~ (208,45,46)   fringe = dark
lum = opx.mean(axis=1)
r, g, b = opx[:, 0], opx[:, 1], opx[:, 2]
is_red_v  = (r.astype(int) - g.astype(int) > 60) & (r > 80)
is_ink_v  = (lum > 150) & (~is_red_v)
is_drk_v  = (lum <= 150) & (~is_red_v)
print("opaque px: ink %d  red %d  dark-fringe %d" % (is_ink_v.sum(), is_red_v.sum(), is_drk_v.sum()))
print("pct exactly #F2EEE3 : %.2f%%" % (100.0 * ((opx == [242, 238, 227]).all(axis=1)).sum() / len(opx)))
print("distinct reds       :", len(np.unique(opx[is_red_v], axis=0)))

# full-image masks
INK = np.zeros((H, W), bool); RED = np.zeros((H, W), bool); DRK = np.zeros((H, W), bool)
INK[op] = is_ink_v; RED[op] = is_red_v; DRK[op] = is_drk_v
SOLID = INK | RED | DRK       # everything opaque

def bbox(m, name):
    ys, xs = np.nonzero(m)
    if len(ys) == 0:
        print(name, "EMPTY"); return None
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    print("%-10s x %4d..%4d (w %4d)   yTOP %4d..%4d (h %4d)   px %d"
          % (name, x0, x1, x1 - x0 + 1, y0, y1, y1 - y0 + 1, m.sum()))
    return x0, x1, y0, y1

print("\n=== BOUNDING BOXES (y measured from TOP) ===")
bb_all = bbox(SOLID, "ALL")
bb_ink = bbox(INK | DRK, "INK+fringe")
bb_red = bbox(RED, "STAR(red)")

# --- baseline / crossbar line ----------------------------------------------
inkmask = INK | DRK
rowcount = inkmask.sum(axis=1)
nz = np.nonzero(rowcount)[0]
print("\nink rows: top=%d bottom=%d" % (nz.min(), nz.max()))
# print a coarse profile so the T structure is visible
print("\nrow profile of INK (y_top: count, every 15 rows):")
for y in range(nz.min(), nz.max() + 1, 15):
    print("  y=%3d  n=%4d" % (y, rowcount[y]))

# find the crossbar->stem transition: big drop in row count
d = np.diff(rowcount.astype(int))
drop_y = int(np.argmin(d))
print("\nlargest row-count drop at y_top=%d  (%d -> %d)  == bottom of crossbar"
      % (drop_y, rowcount[drop_y], rowcount[drop_y + 1]))

# --- stem geometry: measure runs on rows well below the crossbar -----------
def runs(row):
    xs = np.nonzero(row)[0]
    out = []
    if len(xs) == 0: return out
    s = xs[0]; p = xs[0]
    for x in xs[1:]:
        if x != p + 1:
            out.append((s, p)); s = x
        p = x
    out.append((s, p))
    return out

print("\n=== STEM RUNS (rows below crossbar) ===")
stem_rows = {}
ybot = nz.max()
for y in range(drop_y + 6, ybot + 1, 20):
    rr = runs(inkmask[y])
    stem_rows[y] = rr
    print("  y=%3d " % y, [(int(s), int(e), int(e - s + 1)) for s, e in rr])

# lean: track centre of each stem run vs y
ys_probe = [y for y in range(drop_y + 6, ybot - 1) if len(runs(inkmask[y])) == 3]
if ys_probe:
    y_hi, y_lo = ys_probe[0], ys_probe[-1]
    rhi, rlo = runs(inkmask[y_hi]), runs(inkmask[y_lo])
    print("\nstem lean measurement between y_top=%d and y_top=%d (rise %d px):" % (y_hi, y_lo, y_lo - y_hi))
    import math
    for i in range(3):
        chi = (rhi[i][0] + rhi[i][1]) / 2.0
        clo = (rlo[i][0] + rlo[i][1]) / 2.0
        drift = chi - clo                      # top is further RIGHT than bottom
        rise = y_lo - y_hi
        K = drift / rise
        print("   stem %d: centre %.1f (top) -> %.1f (bottom)  drift %.1f over rise %d"
              "  K=%.6f  angle=%.3f deg  width %d/%d"
              % (i, chi, clo, drift, rise, K, math.degrees(math.atan(K)),
                 rhi[i][1] - rhi[i][0] + 1, rlo[i][1] - rlo[i][0] + 1))
    print("   stem centre pitch at top: %.1f, %.1f"
          % ((rhi[1][0] + rhi[1][1]) / 2.0 - (rhi[0][0] + rhi[0][1]) / 2.0,
             (rhi[2][0] + rhi[2][1]) / 2.0 - (rhi[1][0] + rhi[1][1]) / 2.0))

print("\n=== CROSSBAR RUNS (rows in the bar) ===")
for y in range(nz.min(), drop_y + 1, max(1, (drop_y - nz.min()) // 8)):
    rr = runs(inkmask[y])
    print("  y=%3d " % y, [(int(s), int(e), int(e - s + 1)) for s, e in rr])

# crossbar top edge angle: for the first bar, first/last x of top row region
print("\n=== STAR ===")
if bb_red:
    x0, x1, y0, y1 = bb_red
    print("star bbox w=%d h=%d" % (x1 - x0 + 1, y1 - y0 + 1))
    # star row widths
    for y in range(y0, y1 + 1, max(1, (y1 - y0) // 10)):
        rr = runs(RED[y])
        print("  y=%3d " % y, [(int(s), int(e)) for s, e in rr])
    # overlap of star column range with ink
    ink_right = np.nonzero((INK | DRK).any(axis=0))[0].max()
    print("ink right edge x=%d ; star left edge x=%d ; overlap=%d px"
          % (ink_right, x0, ink_right - x0 + 1))

print("\n=== DONE ===")
