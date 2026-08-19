"""
sting_01_measure2.py -- precise rebuild coordinates for the TTT mark.
Uses PURE INK mask (excludes the JPEG dark fringe) so widths are the real drawn widths.
"""
import os, math, subprocess
import numpy as np

FFMPEG = r"C:\ffmpeg\ffmpeg.exe"
SCRATCH = r"C:\Users\natha\AppData\Local\Temp\claude\C--Users-natha\13b079a6-7fa2-406d-a5ce-b8f3295a6b37\scratchpad"
RAW = os.path.join(SCRATCH, "logo_rgba.raw")
W, H = 1413, 540

a = np.fromfile(RAW, dtype=np.uint8).reshape(H, W, 4)
alpha = a[:, :, 3]; rgb = a[:, :, :3].astype(np.int16)
op = alpha == 255
r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
lum = rgb.mean(axis=2)
RED = op & ((r - g) > 60) & (r > 80)
INK = op & (lum > 150) & (~RED)          # PURE ink, fringe excluded

def runs(row):
    xs = np.nonzero(row)[0]; out = []
    if len(xs) == 0: return out
    s = p = xs[0]
    for x in xs[1:]:
        if x != p + 1: out.append((int(s), int(p))); s = x
        p = x
    out.append((int(s), int(p))); return out

# ---------- vertical extent of the wordmark ----------
rows = INK.sum(axis=1); nz = np.nonzero(rows)[0]
print("INK rows y_top %d..%d" % (nz.min(), nz.max()))

# crossbar top = first row where a run wider than 200px exists
bar_top = None
for y in range(H):
    if any((e - s + 1) > 200 for s, e in runs(INK[y])):
        bar_top = y; break
bar_bot = None
for y in range(H - 1, -1, -1):
    if any((e - s + 1) > 200 for s, e in runs(INK[y])):
        bar_bot = y; break
print("crossbar rows y_top %d..%d  -> bar height %d" % (bar_top, bar_bot, bar_bot - bar_top + 1))

stem_bot = nz.max()
print("stem bottom y_top %d  -> stem-only height (bar_bot..stem_bot) %d" % (stem_bot, stem_bot - bar_bot))
print("TOTAL wordmark height %d" % (stem_bot - bar_top + 1))

# ---------- crossbar: width + edge angles, bars 0 and 1 only (bar 2 is masked by star) ----------
print("\n=== CROSSBAR (bars 0,1 -- bar 2 is occluded by the star) ===")
samples = {}
for y in range(bar_top + 2, bar_bot - 1):
    rr = [x for x in runs(INK[y]) if (x[1] - x[0] + 1) > 200]
    if len(rr) >= 2: samples[y] = rr[:2]
ys = sorted(samples)
for y in ys[::max(1, len(ys)//10)]:
    print("  y=%3d" % y, [(s, e, e - s + 1) for s, e in samples[y]])

for i in (0, 1):
    yA, yB = ys[0], ys[-1]
    lA, rA = samples[yA][i]; lB, rB = samples[yB][i]
    rise = yB - yA
    print("bar %d: left %d->%d (K=%.5f, %.3f deg)  right %d->%d (K=%.5f, %.3f deg)  width %d->%d"
          % (i, lA, lB, (lA - lB) / rise, math.degrees(math.atan((lA - lB) / rise)),
             rA, rB, (rA - rB) / rise, math.degrees(math.atan((rA - rB) / rise)),
             rA - lA + 1, rB - lB + 1))
wid = [samples[y][i][1] - samples[y][i][0] + 1 for y in ys for i in (0, 1)]
print("crossbar width: min %d max %d mean %.2f" % (min(wid), max(wid), float(np.mean(wid))))

# crossbar TOP edge angle: for bar0, find first opaque row per column across the bar
print("\ncrossbar TOP-edge flatness (bar 0, first ink row per column):")
cols = range(samples[ys[0]][0][0] + 20, samples[ys[0]][0][1] - 20, 40)
tops = []
for x in cols:
    col = np.nonzero(INK[:, x])[0]
    col = col[col < bar_bot]
    tops.append((x, int(col.min()) if len(col) else -1))
print("  ", tops)
xs_ = np.array([t[0] for t in tops], float); ys_ = np.array([t[1] for t in tops], float)
slope = np.polyfit(xs_, ys_, 1)[0]
print("  fitted slope dy/dx = %.6f  -> top edge angle = %.4f deg" % (slope, math.degrees(math.atan(slope))))

# ---------- stems ----------
print("\n=== STEMS (pure ink) ===")
srows = {}
for y in range(bar_bot + 3, stem_bot - 1):
    rr = [x for x in runs(INK[y]) if 80 < (x[1] - x[0] + 1) < 200]
    if len(rr) == 3: srows[y] = rr
sy = sorted(srows)
sw = [e - s + 1 for y in sy for s, e in srows[y]]
print("stem width: min %d max %d mean %.2f  (rows %d..%d)" % (min(sw), max(sw), float(np.mean(sw)), sy[0], sy[-1]))
yA, yB = sy[0], sy[-1]; rise = yB - yA
for i in range(3):
    cA = (srows[yA][i][0] + srows[yA][i][1]) / 2.0
    cB = (srows[yB][i][0] + srows[yB][i][1]) / 2.0
    print("  stem %d: centre %.1f@y%d -> %.1f@y%d  K=%.6f  %.4f deg"
          % (i, cA, yA, cB, yB, (cA - cB) / rise, math.degrees(math.atan((cA - cB) / rise))))

# ---------- UNSHEAR to get the upright construction ----------
K = 0.159816                      # spec rest shear
BASE = stem_bot                   # baseline row (y_top)
print("\n=== UNSHEARED construction (K=%.6f, pivot=baseline y_top=%d) ===" % (K, BASE))
def unshear_x(x, y_top):
    yup = BASE - y_top
    return x - K * yup
for i in range(3):
    cA = (srows[yA][i][0] + srows[yA][i][1]) / 2.0
    cB = (srows[yB][i][0] + srows[yB][i][1]) / 2.0
    print("  stem %d unsheared centre: %.2f (from y%d) / %.2f (from y%d)"
          % (i, unshear_x(cA, yA), yA, unshear_x(cB, yB), yB))
for i in (0, 1):
    for y in (ys[0], ys[-1]):
        l, rr_ = samples[y][i]
        print("  bar %d unsheared @y%d: L=%.2f R=%.2f  (w %d)" % (i, y, unshear_x(l, y), unshear_x(rr_, y), rr_ - l + 1))

# ---------- star ----------
print("\n=== STAR ===")
rys, rxs = np.nonzero(RED)
x0, x1, y0, y1 = rxs.min(), rxs.max(), rys.min(), rys.max()
cx = (x0 + x1) / 2.0
Rw = (x1 - x0 + 1) / (2 * math.sin(math.radians(72)))
Rh = (y1 - y0 + 1) / (1 + math.cos(math.radians(36)))
print("bbox x %d..%d (w %d)  y %d..%d (h %d)" % (x0, x1, x1 - x0 + 1, y0, y1, y1 - y0 + 1))
print("centre x %.1f ; R from width %.2f ; R from height %.2f  -> regular 5-point star" % (cx, Rw, Rh))
R = (Rw + Rh) / 2.0
cy = y0 + R
print("star centre (x=%.1f, y_top=%.1f)  R=%.2f  r_inner(pentagram)=%.2f" % (cx, cy, R, R * math.cos(math.radians(72)) / math.cos(math.radians(36))))
print("star top point y_top=%d ; predicted %.1f" % (y0, cy - R))
print("star vertical position vs crossbar top (y_top %d): star rises %d px above it" % (bar_top, bar_top - y0))

# overlap: third bar right edge (reconstructed) vs star left edge
bar_w = float(np.mean(wid))
# stem2 unsheared centre
c2 = unshear_x((srows[yA][2][0] + srows[yA][2][1]) / 2.0, yA)
bar2_right_unsheared = c2 + bar_w / 2.0
print("bar2 unsheared centre %.2f -> unsheared right edge %.2f" % (c2, bar2_right_unsheared))
for probe_y in (bar_top, int(cy)):
    shx = K * (BASE - probe_y)
    print("  at y_top=%d bar2 right edge sheared = %.1f ; star left edge %d ; overlap %.1f px"
          % (probe_y, bar2_right_unsheared + shx, x0, bar2_right_unsheared + shx - x0))
print("\nDONE")
