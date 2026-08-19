"""External pixel measurement. Never uses bpy.

BLENDER-CAPABILITY.md 4.2: Blender's Image.pixels is colour-managed and
buffer-type dependent, and reads straight alpha back as premultiplied. Every
number in GRAPHICS-SPEC.md that describes a DELIVERED file comes through here.

Primary reader is ffmpeg -> rawvideo rgba. PIL is cross-checked against it once
(see selftest) and then used for speed on large sweeps.
"""
import os
import subprocess
import sys

import numpy as np

FFMPEG = r"C:\ffmpeg\ffmpeg.exe"
FFPROBE = r"C:\ffmpeg\ffprobe.exe"


def read_ffmpeg(path):
    """(H, W, 4) uint8 RGBA, decoded by ffmpeg. The authoritative reader."""
    w, h = probe_size(path)
    p = subprocess.run(
        [FFMPEG, "-v", "error", "-i", path, "-f", "rawvideo",
         "-pix_fmt", "rgba", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    a = np.frombuffer(p.stdout, dtype=np.uint8)
    return a.reshape(h, w, 4)


def read_pil(path):
    from PIL import Image
    return np.asarray(Image.open(path).convert("RGBA"))


def probe_size(path):
    p = subprocess.run(
        [FFPROBE, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", path],
        stdout=subprocess.PIPE, check=True, text=True)
    w, h = p.stdout.strip().split(",")[:2]
    return int(w), int(h)


def hexat(img, x, y):
    r, g, b, a = img[y, x]
    return "#%02X%02X%02X" % (r, g, b), int(a)


def unique_colors(img, alpha_min=250):
    m = img[..., 3] >= alpha_min
    px = img[m][:, :3]
    if not len(px):
        return []
    v = px.astype(np.uint32)
    key = (v[:, 0] << 16) | (v[:, 1] << 8) | v[:, 2]
    u, c = np.unique(key, return_counts=True)
    o = np.argsort(-c)
    return [("#%06X" % u[i], int(c[i])) for i in o]


def edge_profile(img, y, x0, x1):
    """Alpha across a horizontal run. Used to count antialiasing steps."""
    return [int(v) for v in img[y, x0:x1, 3]]


def aa_stats(img):
    """How many pixels are partially transparent, and how wide is the ramp.

    A hard-aliased (stair-stepped) edge has almost no intermediate alpha.
    A well antialiased edge has a 1-2 px band of intermediates all round the
    ink. Reported as a fraction of the fully-opaque area.
    """
    a = img[..., 3].astype(np.int32)
    opaque = int((a == 255).sum())
    partial = int(((a > 0) & (a < 255)).sum())
    empty = int((a == 0).sum())
    return dict(opaque=opaque, partial=partial, empty=empty,
                partial_per_opaque=round(partial / max(opaque, 1), 4),
                distinct_alpha=int(len(np.unique(a))))


def fringe_check(img):
    """Straight vs premultiplied alpha, measured.

    Premultiplied RGBA stored in a file that a compositor treats as straight
    produces DARK fringes. The tell: at low alpha, RGB has been pulled toward
    black. Report mean luma of ink pixels bucketed by alpha; if the low-alpha
    buckets are much darker than the opaque bucket, the file is premultiplied.
    """
    a = img[..., 3].astype(np.float64)
    lum = img[..., :3].astype(np.float64).mean(axis=2)
    out = {}
    for lo, hi in ((1, 64), (64, 128), (128, 192), (192, 254), (255, 256)):
        m = (a >= lo) & (a < hi)
        n = int(m.sum())
        out["a%d-%d" % (lo, hi - 1)] = (n, round(float(lum[m].mean()), 1) if n else None)
    return out


def selftest(path):
    f = read_ffmpeg(path)
    p = read_pil(path)
    same = f.shape == p.shape and bool((f == p).all())
    diff = int((f.astype(int) != p.astype(int)).sum()) if f.shape == p.shape else -1
    print("ffmpeg vs PIL identical: %s (differing components: %d)" % (same, diff))
    return same


if __name__ == "__main__":
    path = sys.argv[1]
    img = read_ffmpeg(path)
    print("file:", path, "shape:", img.shape)
    selftest(path)
    print("aa:", aa_stats(img))
    print("top colours (opaque):", unique_colors(img)[:8])
    for arg in sys.argv[2:]:
        if arg.startswith("px:"):
            x, y = (int(v) for v in arg[3:].split(","))
            print("px (%d,%d) ->" % (x, y), hexat(img, x, y))
        if arg.startswith("row:"):
            y, x0, x1 = (int(v) for v in arg[4:].split(","))
            print("alpha row y=%d x=%d..%d:" % (y, x0, x1),
                  edge_profile(img, y, x0, x1))
