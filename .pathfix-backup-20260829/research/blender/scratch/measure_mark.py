"""Measure the TTT mark: shear angle of the stems, exact palette, star geometry.
No numpy available -> pure PIL + stdlib.
"""
from PIL import Image
from collections import Counter
import math

P = r"C:\Users\natha\OneDrive\Desktop\Boyd Clips\boyd-brand\logo_transparent.png"
im = Image.open(P).convert("RGBA")
W, H = im.size
px = im.load()
print(f"logo_transparent.png size = {W}x{H}")

# --- exact palette of opaque pixels ---
c = Counter()
for y in range(H):
    for x in range(W):
        r, g, b, a = px[x, y]
        if a > 250:
            c[(r, g, b)] += 1
print("\ntop opaque colours (hex, count, % of opaque):")
tot = sum(c.values())
for col, n in c.most_common(6):
    print(f"  #{col[0]:02X}{col[1]:02X}{col[2]:02X}  {n:>7}  {100*n/tot:5.2f}%")

# --- classify ink vs red ---
def is_red(r, g, b):
    return r > 120 and r - g > 60 and r - b > 60
def is_ink(r, g, b):
    return r > 180 and g > 180 and b > 170 and abs(r - g) < 40

# --- measure stem shear: for the LEFT-most T stem, find x-centre of ink per row ---
# isolate rows below the crossbar so we only catch stems
rows = {}
for y in range(H):
    xs = [x for x in range(W) if px[x, y][3] > 250 and is_ink(*px[x, y][:3])]
    if xs:
        rows[y] = xs
ys = sorted(rows)
print(f"\nink rows span y={ys[0]}..{ys[-1]}")

# Find crossbar bottom: crossbars are wide, stems are narrow.
widths = {y: len(rows[y]) for y in ys}
maxw = max(widths.values())
# first row (from top) where total ink width drops below 55% of max -> below crossbars
stem_start = None
for y in ys:
    if widths[y] < 0.55 * maxw:
        stem_start = y
        break
print(f"max ink width per row = {maxw}px ; stem region starts at y={stem_start}")

# In the stem region, group each row's xs into contiguous runs (the 3 stems)
def runs(xs):
    out, s, p = [], xs[0], xs[0]
    for x in xs[1:]:
        if x != p + 1:
            out.append((s, p)); s = x
        p = x
    out.append((s, p))
    return out

stem_rows = [y for y in ys if y >= stem_start + 10 and y <= ys[-1] - 5]
tracks = {}  # stem index -> list of (y, centre)
for y in stem_rows:
    rr = [r for r in runs(rows[y]) if r[1] - r[0] > 20]
    if len(rr) != 3:
        continue
    for i, (a, b) in enumerate(rr):
        tracks.setdefault(i, []).append((y, (a + b) / 2.0, b - a + 1))

print("\nstem shear measurement (centre-x drift vs y):")
angles = []
for i in sorted(tracks):
    t = tracks[i]
    (y0, x0, w0), (y1, x1, w1) = t[0], t[-1]
    dy = y1 - y0
    dx = x1 - x0
    ang = math.degrees(math.atan2(dx, dy))
    angles.append(ang)
    print(f"  stem {i}: y {y0}->{y1} (dy={dy}), centre x {x0:.1f}->{x1:.1f} (dx={dx:.1f}), "
          f"width {w0}->{w1}px, lean = {ang:.2f} deg from vertical")
print(f"  mean stem lean = {sum(angles)/len(angles):.2f} deg")

# --- is the crossbar horizontal? measure top edge of crossbar across its width ---
top_edge = {}
for x in range(W):
    for y in range(H):
        r, g, b, a = px[x, y]
        if a > 250 and is_ink(r, g, b):
            top_edge[x] = y
            break
xs_sorted = sorted(top_edge)
# sample the first crossbar only (left ~25% of ink)
seg = [x for x in xs_sorted if x < W * 0.25]
if seg:
    print(f"\ncrossbar 1 top edge: x={seg[0]} y={top_edge[seg[0]]}  ->  x={seg[-1]} y={top_edge[seg[-1]]}")
    print(f"  slope over {seg[-1]-seg[0]}px = {top_edge[seg[-1]]-top_edge[seg[0]]}px "
          f"({math.degrees(math.atan2(top_edge[seg[-1]]-top_edge[seg[0]], seg[-1]-seg[0])):.2f} deg)")

# --- star bbox & where it sits relative to ink ---
rx0 = ry0 = 10**9; rx1 = ry1 = -1
ix1 = -1
for y in range(H):
    for x in range(W):
        r, g, b, a = px[x, y]
        if a > 250:
            if is_red(r, g, b):
                rx0 = min(rx0, x); rx1 = max(rx1, x)
                ry0 = min(ry0, y); ry1 = max(ry1, y)
            elif is_ink(r, g, b):
                ix1 = max(ix1, x)
print(f"\nstar bbox: x {rx0}..{rx1} (w={rx1-rx0+1}), y {ry0}..{ry1} (h={ry1-ry0+1})")
print(f"ink right edge x={ix1}; star overlaps ink horizontally by {ix1-rx0+1}px "
      f"({100*(ix1-rx0+1)/(rx1-rx0+1):.1f}% of star width)")
print(f"star top y={ry0} vs ink top y={ys[0]}  -> star rises {ys[0]-ry0}px above the crossbar line")
print(f"star height / mark height = {(ry1-ry0+1)/H:.3f}")
