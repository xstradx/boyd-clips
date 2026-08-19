"""Does the RGBA PNG sequence composite cleanly over video with ffmpeg overlay?

    python alpha_verify.py

The question that matters is not "is there an alpha channel" - it is whether the
alpha is STRAIGHT or PREMULTIPLIED, and whether ffmpeg's overlay agrees. Get it
wrong and every antialiased glyph edge gets a dark halo against bright footage
and a bright halo against dark footage. It is invisible on a mid-grey test card
and obvious on real footage, which is exactly how it ships.

Method: composite over a background that is BRIGHTER than the graphic's ink in
some places and darker in others, then compare ffmpeg's result against the
analytic straight-alpha composite computed here in numpy:

    out = fg*a + bg*(1-a)

If the file were premultiplied and ffmpeg treated it as straight, partial-alpha
pixels would come out too DARK by fg*a*(1-a). The test reports the signed error
bucketed by alpha, so the failure mode is identifiable, not just detectable.
"""
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import measure as M

HERE = os.path.dirname(os.path.abspath(__file__))
FFMPEG = r"C:\ffmpeg\ffmpeg.exe"
OUT = os.path.join(HERE, "renders", "alpha")
SEQ = os.path.join(HERE, "renders", "lower_third")
FRAME = 60


def sh(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode:
        print(p.stderr[-2500:])
        raise SystemExit("ffmpeg failed: %s" % cmd[:6])
    return p


def main():
    os.makedirs(OUT, exist_ok=True)
    fg_path = os.path.join(SEQ, "f_%04d.png" % FRAME)

    # ---- background: four vertical bands spanning black -> white, plus a
    # saturated blue, so the halo direction is unambiguous in both directions.
    bg_path = os.path.join(OUT, "bg.png")
    sh([FFMPEG, "-v", "error", "-y", "-f", "lavfi",
        "-i", "color=c=0x000000:s=1920x1080",
        # 60px bands CYCLING across the whole frame, not four quarters. The
        # lower third only occupies x=117..671, so quarter-width bands left the
        # white and blue cases with zero partial-alpha pixels - and a dark
        # fringe is only visible against a BRIGHT background, so that was the
        # half of the test that mattered.
        "-vf", ",".join(
            "drawbox=x=%d:y=0:w=60:h=1080:color=0x%s:t=fill"
            % (i * 60, ("000000", "808080", "FFFFFF", "1B4FD8")[i % 4])
            for i in range(32)),
        "-frames:v", "1", bg_path])

    # ---- ffmpeg's composite
    comp_path = os.path.join(OUT, "composited.png")
    sh([FFMPEG, "-v", "error", "-y", "-i", bg_path, "-i", fg_path,
        "-filter_complex", "[0][1]overlay=0:0:format=rgb,format=rgb24",
        "-frames:v", "1", comp_path])

    fg = M.read_ffmpeg(fg_path).astype(np.float64)
    bg = M.read_ffmpeg(bg_path).astype(np.float64)[..., :3]
    got = M.read_ffmpeg(comp_path).astype(np.float64)[..., :3]

    a = (fg[..., 3:4] / 255.0)
    want_straight = fg[..., :3] * a + bg * (1.0 - a)
    # what it WOULD look like if the file were premultiplied and ffmpeg
    # treated it as straight (the classic dark-halo failure)
    want_premul = (fg[..., :3] * a) * a + bg * (1.0 - a)

    err_s = got - want_straight
    err_p = got - want_premul
    al = fg[..., 3]

    print("=" * 74)
    print("ALPHA COMPOSITE OVER VIDEO - ffmpeg overlay vs analytic straight alpha")
    print("=" * 74)
    print("foreground : %s (frame %d of the Blender lower third)" % (fg_path, FRAME))
    print("background : 4 bands  #000000 | #808080 | #FFFFFF | #1B4FD8")
    print()
    print("%-16s %8s %10s %10s %10s" % ("alpha bucket", "px",
                                        "max|err| S", "mean|err| S", "mean|err| P"))
    for lo, hi in ((1, 64), (64, 128), (128, 192), (192, 255), (255, 256)):
        m = (al >= lo) & (al < hi)
        n = int(m.sum())
        if not n:
            continue
        print("%-16s %8d %10.3f %10.4f %10.4f"
              % ("a=%d..%d" % (lo, hi - 1), n,
                 float(np.abs(err_s[m]).max()),
                 float(np.abs(err_s[m]).mean()),
                 float(np.abs(err_p[m]).mean())))

    partial = (al > 0) & (al < 255)
    print()
    print("VERDICT")
    print("  partial-alpha pixels          : %d" % int(partial.sum()))
    print("  max |error| vs STRAIGHT       : %.3f / 255"
          % float(np.abs(err_s[partial]).max()))
    print("  mean |error| vs STRAIGHT      : %.4f / 255"
          % float(np.abs(err_s[partial]).mean()))
    print("  mean |error| vs PREMULTIPLIED : %.4f / 255"
          % float(np.abs(err_p[partial]).mean()))
    print("  signed mean error (halo dir)  : %+.4f  (negative = dark fringe)"
          % float(err_s[partial].mean()))

    # ---- per-background-band, because a halo is direction-dependent
    print()
    print("  signed mean error by background band (partial-alpha px only):")
    for bi, name in enumerate(("black  #000000", "grey   #808080",
                               "white  #FFFFFF", "blue   #1B4FD8")):
        band = np.zeros(1920, bool)
        for i in range(bi, 32, 4):
            band[i * 60:(i + 1) * 60] = True
        m = partial & band[None, :]
        n = int(m.sum())
        if n:
            print("    %-16s n=%-6d signed mean %+.4f   max|err| %.3f"
                  % (name, n, float(err_s[m].mean()),
                     float(np.abs(err_s[m]).max())))
        else:
            print("    %-16s n=0" % name)

    # ---- and the full-sequence path, which is what production actually runs
    print()
    print("  full-sequence composite (PNG seq -> H.264 over a moving bg):")
    mp4 = os.path.join(OUT, "composite_test.mp4")
    sh([FFMPEG, "-v", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=s=1920x1080:r=30:d=4.5",
        "-framerate", "30", "-start_number", "1",
        "-i", os.path.join(SEQ, "f_%04d.png"),
        "-filter_complex", "[0][1]overlay=0:0:format=rgb:shortest=1[v]",
        "-map", "[v]", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p",
        mp4])
    p = subprocess.run([r"C:\ffmpeg\ffprobe.exe", "-v", "error",
                        "-select_streams", "v:0", "-show_entries",
                        "stream=codec_name,width,height,nb_frames,pix_fmt",
                        "-of", "csv=p=0", mp4], capture_output=True, text=True)
    print("    %s -> %s" % (os.path.basename(mp4), p.stdout.strip()))
    print("    size: %d bytes" % os.path.getsize(mp4))


if __name__ == "__main__":
    main()
