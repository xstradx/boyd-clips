#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""shotqual.py - RANK the available angles by how much there is to see.

WHY
---
The first multi-angle cut rotated angles on a timer and cut to a camera whose
view was an officer's arm across the lens - the camera was recording, the file
was fine, every existing gate passed, and there was nothing on screen. Nathan,
looking at the strip: *"I don't understand what you're saying what shot is
usable??"* - because the cut itself did not distinguish them.

A body camera spends a lot of its life pointed at a sleeve, a thigh, the ground
or a headlight. Duration is not coverage. This measures whether a frame carries
a legible scene, so the editor can refuse to cut to one that does not.

THREE INDEPENDENT MEASURES, because each alone has an obvious false positive:

  detail   - variance of the Laplacian. A blocked lens is smooth; a scene has
             edges. On its own it is fooled by sensor noise in the dark, which
             is high-variance and carries no information.
  spread   - how much of the frame sits in the dominant colour bin. A hand
             fills the frame with one hue; a scene does not. On its own it is
             fooled by a legible but monochrome night shot.
  range    - the 5th-95th percentile luminance spread. A blown-out or crushed
             frame has none. On its own it is fooled by a flat grey wall.

WHY THIS RANKS INSTEAD OF JUDGING, which is the finding that shaped the file.

The first attempt was a binary usable/not-usable test with thresholds. Measured
across 120 frames sampled from all five real cameras, no cheap global statistic
separates "lens obstructed" from "legitimate dark close-up":

    smooth_frac   arm across the lens          0.423
                  woman's face filling the
                  frame in a dark patrol car   0.495   <- MORE smooth, and fine
    tonal range   median 152, min 71 - and a low range mostly means NIGHT,
                  which is the normal condition here, not a defect.

Any threshold that catches the blocked frame also throws away good close-ups.
So the binary test was abandoned. A RANKING needs no threshold and degrades
gracefully: at each cut the editor takes the best-scoring camera that is
actually recording, so a blocked lens loses to any clearer angle without
anyone having to define "unusable". When every angle is poor the cut still
happens - it just picks the least bad, which is what a human editor does.

    python tools/shotqual.py --selftest
    python tools/shotqual.py --frame <img.jpg>
    python tools/shotqual.py --video <v.mp4> --at 12.5
    python tools/shotqual.py --scan <v.mp4> --start 0 --end 60
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

import numpy as np

# Calibrated on the Denver 2025-08-23 pair. The blocked frame measures
# detail 27.7 / spread 0.62 / range 74; the legible one 181.6 / 0.10 / 128.
MIN_DETAIL = 60.0     # Laplacian variance
MAX_SPREAD = 0.40     # fraction of pixels in the dominant hue/value bin
MIN_RANGE = 90.0      # p95 - p5 luminance


def frame_from_video(path, at, tmp=None):
    tmp = tmp or os.path.join(os.path.dirname(os.path.abspath(path)), "_sq.png")
    subprocess.run(["ffmpeg", "-v", "error", "-ss", "%.3f" % at, "-i", path,
                    "-frames:v", "1", "-y", tmp], capture_output=True)
    return tmp if os.path.exists(tmp) else None


def measure(img_path):
    """-> dict(detail, spread, range, ok). Pure measurement, no policy."""
    from PIL import Image
    im = Image.open(img_path).convert("RGB")
    # Work at a fixed small size so the numbers do not move with resolution -
    # the sources here are a mix of 720p and 1080p.
    im = im.resize((320, 180), Image.LANCZOS)
    rgb = np.asarray(im).astype(np.float64)
    g = rgb @ np.array([0.299, 0.587, 0.114])

    # detail: 4-neighbour Laplacian
    lap = (-4 * g[1:-1, 1:-1] + g[:-2, 1:-1] + g[2:, 1:-1]
           + g[1:-1, :-2] + g[1:-1, 2:])
    detail = float(lap.var())

    # spread: how concentrated the picture is in one colour cell
    q = (rgb // 32).astype(np.int64)
    keys = q[..., 0] * 64 + q[..., 1] * 8 + q[..., 2]
    counts = np.bincount(keys.ravel())
    spread = float(counts.max()) / float(keys.size)

    lo, hi = np.percentile(g, 5), np.percentile(g, 95)
    rng = float(hi - lo)

    # obstruction: fraction of 16px blocks that are near-featureless. A hand or
    # sleeve against the lens is a large smooth region.
    B = 16
    bh, bw = g.shape[0] // B, g.shape[1] // B
    blocks = (g[:bh * B, :bw * B].reshape(bh, B, bw, B)
              .transpose(0, 2, 1, 3).reshape(bh, bw, -1))
    smooth = float((blocks.var(axis=2) < 12.0).mean())

    # One comparable score. Detail and range are rewarded on a log/linear scale
    # normalised to the measured medians of real bodycam (1245 and 152), and
    # the smooth fraction is penalised. Only ever compared BETWEEN cameras at
    # the same instant, so the absolute value carries no meaning on its own.
    score = (min(detail / 1245.0, 2.0) * 0.45
             + min(rng / 152.0, 2.0) * 0.35
             - smooth * 1.20)

    ok = (detail >= MIN_DETAIL and rng >= MIN_RANGE and smooth < 0.60)
    return {"detail": round(detail, 1), "spread": round(spread, 3),
            "range": round(rng, 1), "smooth": round(smooth, 3),
            "score": round(float(score), 3), "ok": bool(ok)}


def why(m):
    r = []
    if m["detail"] < MIN_DETAIL:
        r.append("no detail (%.0f < %.0f) - lens blocked or out of focus"
                 % (m["detail"], MIN_DETAIL))
    if m.get("smooth", 0) >= 0.60:
        r.append("%.0f%% of the frame is featureless - lens obstructed"
                 % (100 * m["smooth"]))
    if m["range"] < MIN_RANGE:
        r.append("no tonal range (%.0f < %.0f) - crushed or blown out"
                 % (m["range"], MIN_RANGE))
    return "; ".join(r) or "legible"


def score_window(video, start, dur, samples=5):
    """Fraction of sampled frames across a window that are usable, plus the
    mean detail. A segment is only as good as its worst stretch, so the
    editor should use the FRACTION, not a single mid-point frame."""
    oks, sc = 0, []
    for i in range(samples):
        at = start + dur * (i + 0.5) / samples
        f = frame_from_video(video, at)
        if not f:
            continue
        m = measure(f)
        oks += bool(m["ok"])
        sc.append(m["score"])
    n = max(1, len(sc))
    return {"usable_frac": oks / float(n),
            "score": round(float(np.mean(sc)), 3) if sc else -9.0}


def selftest():
    fails = []

    def t(cond, what):
        if not cond:
            fails.append(what)
        print("  %-4s %s" % ("ok" if cond else "FAIL", what))

    here = os.path.dirname(os.path.abspath(__file__))
    good = os.path.join(here, "fixtures", "shot_usable.jpg")
    bad = os.path.join(here, "fixtures", "shot_blocked.jpg")

    print("real fixtures from the Denver 2025-08-23 traffic stop")
    if not (os.path.exists(good) and os.path.exists(bad)):
        print("  FAIL fixtures missing: %s / %s" % (good, bad))
        return 1

    mg, mb = measure(good), measure(bad)
    print("  usable  detail=%7.1f spread=%.3f range=%6.1f -> %s"
          % (mg["detail"], mg["spread"], mg["range"], "PASS" if mg["ok"] else "FAIL"))
    print("  blocked detail=%7.1f spread=%.3f range=%6.1f -> %s   (%s)"
          % (mb["detail"], mb["spread"], mb["range"], "PASS" if mb["ok"] else "FAIL", why(mb)))

    t(mg["score"] > mb["score"],
      "THE CLAIM THAT MATTERS: the legible frame OUTRANKS the blocked one "
      "(%.3f > %.3f)" % (mg["score"], mb["score"]))
    t(mb["smooth"] > mg["smooth"],
      "the blocked frame is measurably smoother (%.3f vs %.3f)"
      % (mb["smooth"], mg["smooth"]))
    # Deliberately NOT asserted: that the blocked frame fails a binary test.
    # Measured on 120 real frames, no threshold separates an obstructed lens
    # from a dark close-up - a face filling a patrol car scored smoother (0.495)
    # than the arm over the lens (0.423). Ranking is the claim; judgement is not.

    print("synthetic degenerate frames")
    from PIL import Image
    tmp = os.path.join(here, "fixtures", "_sq_tmp.png")
    Image.new("RGB", (320, 180), (12, 12, 12)).save(tmp)
    t(not measure(tmp)["ok"], "a black frame is refused")
    Image.new("RGB", (320, 180), (250, 250, 250)).save(tmp)
    t(not measure(tmp)["ok"], "a blown-white frame is refused")
    Image.new("RGB", (320, 180), (170, 40, 40)).save(tmp)
    t(not measure(tmp)["ok"], "a flat red frame (a hand) is refused")
    arr = (np.random.RandomState(0).rand(180, 320, 3) * 255).astype(np.uint8)
    Image.fromarray(arr).save(tmp)
    m = measure(tmp)
    t(m["spread"] <= MAX_SPREAD,
      "pure noise is not flagged as one-colour (spread %.3f)" % m["spread"])
    os.remove(tmp)

    print()
    if fails:
        print("SELFTEST FAILED: %d" % len(fails))
        for f in fails:
            print("   - %s" % f)
        return 1
    print("SHOTQUAL_SELFTEST_OK")
    return 0


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--frame")
    ap.add_argument("--video")
    ap.add_argument("--at", type=float, default=0.0)
    ap.add_argument("--scan")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=60.0)
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.frame:
        m = measure(a.frame)
        print("%s  detail=%.1f spread=%.3f range=%.1f  %s  (%s)"
              % (os.path.basename(a.frame), m["detail"], m["spread"], m["range"],
                 "USABLE" if m["ok"] else "NOT USABLE", why(m)))
        return 0 if m["ok"] else 3
    if a.video:
        f = frame_from_video(a.video, a.at)
        m = measure(f)
        print("t=%.1f  %s  (%s)" % (a.at, "USABLE" if m["ok"] else "NOT USABLE", why(m)))
        return 0 if m["ok"] else 3
    if a.scan:
        t_ = a.start
        while t_ < a.end:
            f = frame_from_video(a.scan, t_)
            m = measure(f)
            print("  %7.1fs  %-11s detail=%7.1f spread=%.3f range=%6.1f  %s"
                  % (t_, "USABLE" if m["ok"] else "NOT USABLE",
                     m["detail"], m["spread"], m["range"], why(m)))
            t_ += 5.0
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
