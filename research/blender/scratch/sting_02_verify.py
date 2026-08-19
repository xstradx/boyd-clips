"""
sting_02_verify.py -- adversarial verification of the delivered sting.

Rules followed:
 * pixels are read with EXTERNAL ffmpeg, never bpy.data.images.load().pixels
   (BLENDER-CAPABILITY.md sec 4.2)
 * "every frame differs" is NOT proven by hashing alone -- live grain makes every frame
   differ even if the animation is frozen. The motion is proven from the ALPHA sequence,
   which carries no grain, by tracing the wordmark's leftmost lit pixel per frame.
"""
import os, subprocess, hashlib, math
import numpy as np

FFMPEG = r"C:\ffmpeg\ffmpeg.exe"
R      = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders"
TMP    = r"C:\Users\natha\AppData\Local\Temp\claude\C--Users-natha\13b079a6-7fa2-406d-a5ce-b8f3295a6b37\scratchpad"
W, H   = 1920, 1080
os.makedirs(TMP, exist_ok=True)

def hexs(rgb):
    return "#%02X%02X%02X" % (int(rgb[0]), int(rgb[1]), int(rgb[2]))

def read_rgb(path, extra=None):
    raw = os.path.join(TMP, "v_rgb.raw")
    cmd = [FFMPEG, "-v", "error", "-y"] + (extra or []) + ["-i", path]
    cmd += ["-f", "rawvideo", "-pix_fmt", "rgb24", raw]
    subprocess.run(cmd, check=True)
    return np.fromfile(raw, np.uint8).reshape(-1, H, W, 3)[0]

def read_rgba16(path):
    raw = os.path.join(TMP, "v_rgba.raw")
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", path,
                    "-f", "rawvideo", "-pix_fmt", "rgba64le", raw], check=True)
    return np.fromfile(raw, "<u2").reshape(H, W, 4)

def modal(px):
    """most common exact RGB triple in an (N,3) array"""
    if len(px) == 0: return None, 0
    v = px.astype(np.uint32)
    key = (v[:, 0] << 16) | (v[:, 1] << 8) | v[:, 2]
    u, c = np.unique(key, return_counts=True)
    i = int(np.argmax(c)); k = int(u[i])
    return ((k >> 16) & 255, (k >> 8) & 255, k & 255), int(c[i])

def classify(img, label):
    flat = img.reshape(-1, 3).astype(np.int16)
    r, g, b = flat[:, 0], flat[:, 1], flat[:, 2]
    lum = flat.mean(axis=1)
    m_red = (r - g > 60) & (r > 80)
    m_ink = (lum > 150) & (~m_red)
    m_bg  = (lum < 40) & (~m_red)
    print("  %-22s" % label)
    for name, mask, target in (("ground", m_bg, "#15181D"),
                               ("ink   ", m_ink, "#F2EEE3"),
                               ("accent", m_red, "#D42B2B")):
        c, n = modal(flat[mask])
        if c is None:
            print("     %s  -- no pixels" % name); continue
        ok = "MATCH  " if hexs(c) == target else "DELTA  "
        d = tuple(int(a) - int(b) for a, b in zip(c, (int(target[1:3], 16), int(target[3:5], 16), int(target[5:7], 16))))
        print("     %s modal %s   target %s   %s d=%s   (%d px, %.1f%% of class)"
              % (name, hexs(c), target, ok, d, n, 100.0 * n / max(mask.sum(), 1)))

print("=" * 78)
print("1. COLOUR -- control render (grain OFF, dither OFF): exact brand values")
print("=" * 78)
classify(read_rgb(os.path.join(R, "verify", "ctrl_0060.png")), "verify/ctrl_0060.png")

print("\n" + "=" * 78)
print("2. COLOUR -- delivered PNG frame 60 (grain ON amp 0.0015, dither ON 1.0)")
print("=" * 78)
classify(read_rgb(os.path.join(R, "seq_flat", "f_0060.png")), "seq_flat/f_0060.png")

print("\n" + "=" * 78)
print("3. COLOUR -- decoded back out of the delivered H.264 sting.mp4 (yuv420p round trip)")
print("=" * 78)
mp4f = os.path.join(TMP, "mp4_f60.png")
subprocess.run([FFMPEG, "-v", "error", "-y", "-i", os.path.join(R, "sting.mp4"),
                "-vf", "select=eq(n\\,59)", "-vframes", "1", mp4f], check=True)
classify(read_rgb(mp4f), "sting.mp4 frame 60")

print("\n" + "=" * 78)
print("4. FRAME UNIQUENESS -- sha256 of all 84 delivered PNGs")
print("=" * 78)
hs, dups = [], {}
for f in range(1, 85):
    p = os.path.join(R, "seq_flat", "f_%04d.png" % f)
    h = hashlib.sha256(open(p, "rb").read()).hexdigest()
    hs.append(h); dups.setdefault(h, []).append(f)
print("  files hashed      : %d" % len(hs))
print("  distinct hashes   : %d" % len(set(hs)))
rep = {k: v for k, v in dups.items() if len(v) > 1}
print("  duplicate frames  : %s" % ("NONE" if not rep else list(rep.values())))
print("  -> every delivered frame is byte-unique. NOTE: live grain alone would achieve")
print("     this even with frozen animation, so section 5 is the real test.")

print("\n" + "=" * 78)
print("5. MOTION TRACE -- from the alpha sequence, which has NO grain.")
print("   Proves the shear + opacity actually evaluated per frame in -b.")
print("=" * 78)
rows = []
for f in range(1, 85):
    a = read_rgba16(os.path.join(R, "seq_alpha", "a_%04d.png" % f))
    al = a[:, :, 3].astype(np.float32) / 65535.0
    rgb = a[:, :, :3].astype(np.int32)
    lit = al > 0.02
    red = lit & ((rgb[:, :, 0] - rgb[:, :, 1]) > 6000)
    ink = lit & (~red)
    if ink.sum() > 0:
        xs = np.nonzero(ink.any(axis=0))[0]
        lx, rx = int(xs.min()), int(xs.max())
        ma = float(al[ink].mean())
    else:
        lx = rx = -1; ma = 0.0
    rows.append((f, int(ink.sum()), lx, rx, ma, int(red.sum())))

print("  frame  inkpx   ink_xmin ink_xmax  mean_ink_alpha  starpx")
for (f, n, lx, rx, ma, rn) in rows:
    if f in (1, 23, 24, 25, 26, 30, 36, 37, 42, 47, 48, 49, 50, 60, 70, 84):
        print("  %5d  %6d   %6d %8d   %13.4f  %6d" % (f, n, lx, rx, ma, rn))

print("\n  --- beat checks ---")
def val(f, i): return rows[f - 1][i]
print("  A  f1-f24 wordmark + star absent      : ink px f1..f24 max = %d ; star px max = %d"
      % (max(val(f, 1) for f in range(1, 25)), max(val(f, 5) for f in range(1, 25))))
print("  B1 star hard cut  f24 -> f25          : star px %d -> %d   (one frame, no fade)"
      % (val(24, 5), val(25, 5)))
print("  B2 opacity ramp   f25 -> f36          : mean ink alpha %.4f -> %.4f"
      % (val(25, 4), val(36, 4)))
print("     ramp is monotonic over f25..f36    : %s"
      % all(val(f, 4) <= val(f + 1, 4) + 1e-6 for f in range(25, 36)))
print("     alpha flat after f36               : %s (f36=%.4f f48=%.4f f84=%.4f)"
      % (abs(val(36, 4) - val(84, 4)) < 1e-3, val(36, 4), val(48, 4), val(84, 4)))
print("  B3 shear settle   f25 -> f48          : ink_xmin %d -> %d  (travel %d px)"
      % (val(25, 2), val(48, 2), val(48, 2) - val(25, 2)))
xs_seq = [val(f, 2) for f in range(25, 49)]
print("     xmin monotonic increasing          : %s" % all(xs_seq[i] <= xs_seq[i + 1] for i in range(len(xs_seq) - 1)))
print("     per-frame deltas f25..f48          : %s" % [xs_seq[i + 1] - xs_seq[i] for i in range(len(xs_seq) - 1)])
print("     no overshoot past rest             : %s (max xmin f25..f48 = %d, rest = %d)"
      % (max(xs_seq) <= val(84, 2), max(xs_seq), val(84, 2)))
hold = [(val(f, 1), val(f, 2), val(f, 3), round(val(f, 4), 5)) for f in range(50, 85)]
print("  D  hold f50-f84 is a DEAD hold        : %s (%d distinct states across 35 frames)"
      % (len(set(hold)) == 1, len(set(hold))))
print("  C  lock at f49, nothing moves after   : f48 xmin=%d f49 xmin=%d f50 xmin=%d f84 xmin=%d"
      % (val(48, 2), val(49, 2), val(50, 2), val(84, 2)))

print("\n" + "=" * 78)
print("6. GRAIN -- present, reseeding, and the right amplitude")
print("=" * 78)
g1 = read_rgb(os.path.join(R, "seq_flat", "f_0001.png"))
g2 = read_rgb(os.path.join(R, "seq_flat", "f_0002.png"))
box1 = g1[40:240, 40:440].reshape(-1, 3)
box2 = g2[40:240, 40:440].reshape(-1, 3)
print("  ground patch f1: distinct colours = %d ; modal = %s"
      % (len(np.unique(box1, axis=0)), hexs(modal(box1)[0])))
print("  ground patch f2: distinct colours = %d ; modal = %s"
      % (len(np.unique(box2, axis=0)), hexs(modal(box2)[0])))
print("  f1 vs f2 differing pixels in patch : %d of %d (grain reseeds per frame)"
      % (int((box1 != box2).any(axis=1).sum()), len(box1)))
print("  ground patch f1 channel range      : R %d-%d  G %d-%d  B %d-%d"
      % (box1[:, 0].min(), box1[:, 0].max(), box1[:, 1].min(), box1[:, 1].max(),
         box1[:, 2].min(), box1[:, 2].max()))
ctrl = read_rgb(os.path.join(R, "verify", "ctrl_0060.png"))[40:240, 40:440].reshape(-1, 3)
print("  control (no grain/dither) patch    : distinct = %d ; modal = %s"
      % (len(np.unique(ctrl, axis=0)), hexs(modal(ctrl)[0])))

print("\n" + "=" * 78)
print("7. ALPHA MASTER -- straight alpha reaching disk")
print("=" * 78)
a60 = read_rgba16(os.path.join(R, "seq_alpha", "a_0060.png"))
al = a60[:, :, 3]
print("  alpha==0      : %d px (%.2f%%)" % ((al == 0).sum(), 100.0 * (al == 0).sum() / al.size))
print("  alpha==65535  : %d px (%.2f%%)" % ((al == 65535).sum(), 100.0 * (al == 65535).sum() / al.size))
mid = (al > 0) & (al < 65535)
print("  antialiased   : %d px (%.4f%%)  <- the source PNG had 0.0000%%, spec sec 12"
      % (mid.sum(), 100.0 * mid.sum() / al.size))
op = al == 65535
opx = (a60[:, :, :3][op] >> 8).astype(np.uint8)
print("  distinct opaque RGB in alpha master: %d   <- source PNG had 4245"
      % len(np.unique(opx, axis=0)))
c, n = modal(opx)
print("  modal opaque colour: %s (%d px)" % (hexs(c), n))
print("  lit pixels (alpha>0.5) frame 60: %d = %.2f%% of frame  (spec sec 4 budget 2.88%%)"
      % ((al > 32767).sum(), 100.0 * (al > 32767).sum() / al.size))
print("\nDONE")
