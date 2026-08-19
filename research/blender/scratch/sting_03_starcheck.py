"""sting_03_starcheck.py -- (a) star is a fixed point, (b) alpha survives ProRes 4444."""
import os, subprocess
import numpy as np

FFMPEG = r"C:\ffmpeg\ffmpeg.exe"
R   = r"C:\Users\natha\Projects\boyd-clips\research\blender\renders"
TMP = r"C:\Users\natha\AppData\Local\Temp\claude\C--Users-natha\13b079a6-7fa2-406d-a5ce-b8f3295a6b37\scratchpad"
W, H = 1920, 1080

def rgba16(path):
    raw = os.path.join(TMP, "s_rgba.raw")
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", path,
                    "-f", "rawvideo", "-pix_fmt", "rgba64le", raw], check=True)
    return np.fromfile(raw, "<u2").reshape(H, W, 4)

print("=== STAR IS A FIXED POINT (spec sec 3.3) ===")
print("  frame  star_bbox(x0,x1,y0,y1)          fully-opaque star px")
prev = None
allsame = True
for f in (25, 26, 30, 36, 42, 48, 49, 60, 84):
    a = rgba16(os.path.join(R, "seq_alpha", "a_%04d.png" % f))
    rgb = a[:, :, :3].astype(np.int32); al = a[:, :, 3]
    red = (al == 65535) & ((rgb[:, :, 0] - rgb[:, :, 1]) > 20000)
    ys, xs = np.nonzero(red)
    bb = (int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max()))
    print("  %5d  %-32s %d" % (f, str(bb), int(red.sum())))
    if prev is not None and bb != prev:
        allsame = False
    prev = bb
print("  star bounding box identical on every sampled frame: %s" % allsame)

print("\n=== ALPHA SURVIVES ProRes 4444 (external ffprobe already says yuva444p12le) ===")
mov = os.path.join(R, "sting_alpha_prores4444.mov")
raw = os.path.join(TMP, "pr_f60.raw")
subprocess.run([FFMPEG, "-v", "error", "-y", "-i", mov, "-vf", "select=eq(n\\,59)",
                "-vframes", "1", "-f", "rawvideo", "-pix_fmt", "rgba", raw], check=True)
p = np.fromfile(raw, np.uint8).reshape(H, W, 4)
al = p[:, :, 3]
print("  decoded ProRes frame 60:")
print("    alpha==0    : %d px (%.2f%%)" % ((al == 0).sum(), 100.0 * (al == 0).sum() / al.size))
print("    alpha==255  : %d px (%.2f%%)" % ((al == 255).sum(), 100.0 * (al == 255).sum() / al.size))
print("    0<alpha<255 : %d px (antialiased edge preserved)" % (((al > 0) & (al < 255)).sum()))
op = al == 255
opx = p[:, :, :3][op]
v = opx.astype(np.uint32)
key = (v[:, 0] << 16) | (v[:, 1] << 8) | v[:, 2]
u, c = np.unique(key, return_counts=True)
order = np.argsort(-c)[:3]
print("    top opaque colours:")
for i in order:
    k = int(u[i])
    print("      #%02X%02X%02X  x%d" % ((k >> 16) & 255, (k >> 8) & 255, k & 255, c[i]))
# corner must be fully transparent
print("    corner pixel (4,4) RGBA = %s  -> transparent: %s"
      % (tuple(int(x) for x in p[4, 4]), p[4, 4, 3] == 0))
print("\nDONE")
