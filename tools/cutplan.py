#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cutplan.py - turn solved offsets into a multi-angle edit.

THE DESIGN DECISION THAT MATTERS: video cuts, audio does not.

Every camera at a scene hears the same event through a different chest-mounted
mic at a different distance with its own automatic gain control. Cutting the
audio at every angle change makes the room tone, level and reverb jump on every
cut - it sounds broken, and it is the single most obvious tell of a naive
multicam assembly. So one camera is chosen as the AUDIO BED and runs
continuously underneath, while the picture cuts freely between angles. That is
what a real multicam edit does and it is why this file separates the two.

The bed is chosen by measured speech presence, not by guessing which officer
was closest: the camera whose audio has the most speech-band energy across the
window carries the scene.

WHAT THIS FILE WILL NOT DO
    - invent an officer name. Denver names its files by number, so labels read
      CAMERA 4 unless a release memo supplies a name.
    - cut to a camera at a time that camera was not recording. Every segment is
      checked against the source's real duration and REFUSED, never clamped -
      a clamped segment silently shows the wrong moment.

    python tools/cutplan.py --selftest
    python tools/cutplan.py --dir <d> --plan
    python tools/cutplan.py --dir <d> --render out.mp4
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# PACING. Nathan, 2026-09-03, watching the first cut: *"Why are you editing so
# fast?"* - and he was right. The first version changed angle every MAX_SEG
# seconds on a timer, which produced 9 cuts in 2 minutes for no reason at all.
#
# A timer is the wrong instrument. An edit cuts when something MOTIVATES a cut:
# the current camera stops showing the thing worth seeing, or another camera
# starts showing it better. Most of the time nothing motivates one, so a
# motivated edit is naturally much slower than a metronome.
#
# MAX_SEG is therefore a long backstop, not a target - it exists only so a
# single angle cannot run for minutes if the measurements go flat. MIN_HOLD is
# the real pacing control: no matter how the scores move, an angle is held at
# least this long, because a cut faster than that reads as a glitch rather than
# as a decision.
#
# NOT MEASURED: the actual cut rate of the channels that win this niche.
# YouTube refuses to serve their video to this machine without cookies, so any
# number claimed for them would be invented. These are stated as reasoned
# defaults and should be replaced with measurements when that footage is
# reachable.
MIN_SEG = 4.0
MIN_HOLD = 8.0       # an angle is never cut away from sooner than this
MAX_SEG = 45.0       # backstop only - reached when nothing motivates a cut
SWITCH_MARGIN = 0.25 # another angle must be THIS much better to earn a cut
W, H = 1920, 1080


def load(d):
    with open(os.path.join(d, "offsets.json"), encoding="utf-8") as fh:
        data = json.load(fh)
    g = max(data["groups"], key=lambda g: len(g["offsets"]))
    cams = []
    for f, start in g["offsets"].items():
        p = os.path.join(d, f)
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                            "format=duration", "-of", "default=nw=1:nk=1", p],
                           capture_output=True, text=True)
        cams.append({"file": f, "path": p, "start": float(start),
                     "dur": float((r.stdout or "0").strip() or 0)})
    cams.sort(key=lambda c: c["start"])
    for i, c in enumerate(cams):
        c["end"] = c["start"] + c["dur"]
        c["label"] = "CAMERA %d" % (i + 1)
    return cams


def live_at(cams, t):
    return [c for c in cams if c["start"] <= t < c["end"]]


def speech_energy(path, start, dur, sr=8000):
    """Mean speech-band (300-3400 Hz) energy over a window. Used to pick the
    audio bed by measurement rather than by assuming which camera was closest."""
    cmd = ["ffmpeg", "-v", "error", "-ss", "%.3f" % start, "-t", "%.3f" % dur,
           "-i", path, "-af", "highpass=f=300,lowpass=f=3400",
           "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0 or not r.stdout:
        return 0.0
    import numpy as np
    x = np.frombuffer(r.stdout, dtype=np.float32)
    return float(np.sqrt(np.mean(x.astype(np.float64) ** 2))) if len(x) else 0.0


def build_plan(cams, t0=None, t1=None, min_seg=MIN_SEG, max_seg=MAX_SEG,
               scorer=None, bed=None):
    """-> (segments, bed). Each segment: incident window + which camera is on
    screen. Angles rotate among whatever is actually recording."""
    if t0 is None:
        t0 = max(c["start"] for c in cams)          # start when coverage is richest
    if t1 is None:
        t1 = min(c["end"] for c in cams if c["end"] > t0)
    if t1 <= t0:
        return [], None

    if bed is None:
        # audio bed: most speech across the whole window, measured
        scored = []
        for c in cams:
            a, b = max(t0, c["start"]), min(t1, c["end"])
            if b - a < 1.0:
                continue
            scored.append((speech_energy(c["path"], a - c["start"], b - a), c))
        if not scored:
            return [], None
        bed = max(scored, key=lambda s: s[0])[1]

    # The scorer is injectable so the pacing logic can be tested without any
    # video on disk. The default measures the real footage.
    if scorer is None:
        import shotqual

        def scorer(cam, at, span):
            w = max(1.0, min(span, cam["end"] - at))
            return shotqual.score_window(cam["path"], at - cam["start"], w,
                                         samples=3)["score"]
    q = scorer

    segs = []
    t = t0
    last = None
    while t < t1 - MIN_SEG:
        avail = [c for c in live_at(cams, t) if c["end"] - t >= MIN_SEG]
        if not avail:
            break
        probe = min(MIN_HOLD, t1 - t)
        scores = {c["file"]: q(c, t, probe) for c in avail}
        cam = max(avail, key=lambda c: scores[c["file"]])
        if last is not None and last in avail:
            # Stay on the current angle unless another is clearly better. A
            # near-tie is not a reason to cut; without this margin the edit
            # flickers between two similar angles on measurement noise.
            if scores[last["file"]] + SWITCH_MARGIN >= scores[cam["file"]]:
                cam = last

        # Hold this angle until it is BEATEN, not until a timer expires. The
        # window is probed forward in MIN_HOLD steps; the cut lands at the first
        # step where a different camera is meaningfully better.
        seg_end = min(t + MIN_HOLD, t1, cam["end"])
        while seg_end < min(t + MAX_SEG, t1, cam["end"]) - 0.5:
            nxt = min(seg_end + MIN_HOLD, t1, cam["end"])
            here = q(cam, seg_end, nxt - seg_end)
            rivals = [c for c in live_at(cams, seg_end)
                      if c is not cam and c["end"] - seg_end >= MIN_SEG]
            best = max((q(c, seg_end, nxt - seg_end) for c in rivals), default=-9.0)
            if best > here + SWITCH_MARGIN:
                break
            seg_end = nxt
        if seg_end - t < MIN_SEG:
            break
        segs.append({"t0": round(t, 3), "t1": round(seg_end, 3),
                     "file": cam["file"], "label": cam["label"],
                     "local_in": round(t - cam["start"], 3),
                     "local_out": round(seg_end - cam["start"], 3)})
        last = cam
        t = seg_end
    # Merge adjacent segments that are the SAME camera. The hold loop advances
    # in MIN_HOLD steps, so staying on one angle emits several segments in a
    # row; leaving them split misreports the cut count (4 "segments" that are
    # really 2 cuts) and makes the renderer re-encode at boundaries where
    # nothing changes.
    merged = []
    for sg in segs:
        if merged and merged[-1]["file"] == sg["file"] and                 abs(merged[-1]["t1"] - sg["t0"]) < 0.001:
            merged[-1]["t1"] = sg["t1"]
            merged[-1]["local_out"] = sg["local_out"]
        else:
            merged.append(dict(sg))
    segs = merged
    if segs:
        segs[-1]["t1"] = round(t1, 3)
        segs[-1]["local_out"] = round(t1 - next(c for c in cams
                                                if c["file"] == segs[-1]["file"])["start"], 3)
    return segs, bed


def check_plan(segs, cams):
    """Every segment must sit inside its camera's real recording. REFUSE, never
    clamp: a clamped segment shows a different moment than the plan claims."""
    by = {c["file"]: c for c in cams}
    errs = []
    for i, s in enumerate(segs):
        c = by.get(s["file"])
        if not c:
            errs.append("seg %d: unknown file %s" % (i, s["file"]))
            continue
        if s["local_in"] < -0.001 or s["local_out"] > c["dur"] + 0.001:
            errs.append("seg %d: %.2f-%.2f outside %s (0-%.2f)"
                        % (i, s["local_in"], s["local_out"], s["file"], c["dur"]))
        if s["t1"] <= s["t0"]:
            errs.append("seg %d: non-positive duration" % i)
    for a, b in zip(segs, segs[1:]):
        if abs(b["t0"] - a["t1"]) > 0.001:
            errs.append("gap/overlap between %.2f and %.2f" % (a["t1"], b["t0"]))
    return errs


def render(d, segs, bed, out):
    """Video cuts between angles; audio is one continuous take from the bed."""
    if not segs:
        return 3, "empty plan"
    t0, t1 = segs[0]["t0"], segs[-1]["t1"]
    tmp = os.path.join(d, "_seg")
    os.makedirs(tmp, exist_ok=True)
    parts = []
    for i, s in enumerate(segs):
        p = os.path.join(tmp, "s%03d.mp4" % i)
        label = s["label"].replace(":", "\\:")
        vf = ("scale=%d:%d:force_original_aspect_ratio=decrease,"
              "pad=%d:%d:(ow-iw)/2:(oh-ih)/2,setsar=1,"
              "drawtext=text='%s':x=42:y=h-96:fontsize=40:fontcolor=white@0.92:"
              "box=1:boxcolor=black@0.45:boxborderw=14"
              % (W, H, W, H, label))
        cmd = ["ffmpeg", "-v", "error", "-ss", "%.3f" % s["local_in"],
               "-t", "%.3f" % (s["local_out"] - s["local_in"]),
               "-i", os.path.join(d, s["file"]), "-an", "-vf", vf,
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
               "-r", "30", "-pix_fmt", "yuv420p", "-y", p]
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode != 0:
            return 3, "segment %d failed: %s" % (i, r.stderr[-200:].decode("utf-8", "replace"))
        parts.append(p)
    lst = os.path.join(tmp, "concat.txt")
    with open(lst, "w", encoding="utf-8") as fh:
        for p in parts:
            fh.write("file '%s'\n" % os.path.abspath(p).replace("\\", "/"))
    silent = os.path.join(tmp, "_video.mp4")
    r = subprocess.run(["ffmpeg", "-v", "error", "-f", "concat", "-safe", "0",
                        "-i", lst, "-c", "copy", "-y", silent], capture_output=True)
    if r.returncode != 0:
        return 3, "concat failed: %s" % r.stderr[-200:].decode("utf-8", "replace")
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", silent,
                        "-ss", "%.3f" % (t0 - bed["start"]), "-t", "%.3f" % (t1 - t0),
                        "-i", bed["path"], "-map", "0:v:0", "-map", "1:a:0",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                        "-shortest", "-y", out], capture_output=True)
    if r.returncode != 0:
        return 3, "mux failed: %s" % r.stderr[-200:].decode("utf-8", "replace")
    return 0, ""


def verify_render(out, segs, tol=0.5):
    want = segs[-1]["t1"] - segs[0]["t0"]
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of", "default=nw=1:nk=1", out],
                       capture_output=True, text=True)
    got = float((r.stdout or "0").strip() or 0)
    return abs(got - want) <= tol, got, want


def selftest():
    fails = []

    def t(cond, what):
        if not cond:
            fails.append(what)
        print("  %-4s %s" % ("ok" if cond else "FAIL", what))

    cams = [{"file": "a.mp4", "start": 0.0, "dur": 100.0, "end": 100.0, "label": "CAMERA 1"},
            {"file": "b.mp4", "start": 20.0, "dur": 100.0, "end": 120.0, "label": "CAMERA 2"},
            {"file": "c.mp4", "start": 40.0, "dur": 100.0, "end": 140.0, "label": "CAMERA 3"}]

    print("pacing - cuts are MOTIVATED, not on a timer")
    for c in cams:
        c["path"] = c["file"]

    flat = lambda cam, at, span: 1.0           # every angle equally good
    segs, _ = build_plan(cams, t0=40.0, t1=100.0, scorer=flat, bed=cams[0])
    t(len(segs) <= 2,
      "when nothing is better than anything else it does NOT keep cutting "
      "(%d segment(s) over 60s)" % len(segs))
    t(not check_plan(segs, cams), "the slow plan is still valid")
    t(abs(segs[-1]["t1"] - 100.0) < 0.01, "the plan covers the window to the end")

    # camera c becomes clearly better halfway through
    def rising(cam, at, span):
        return 2.0 if (cam["file"] == "c.mp4" and at >= 70.0) else 1.0
    segs2, _ = build_plan(cams, t0=40.0, t1=100.0, scorer=rising, bed=cams[0])
    t(len(segs2) >= 2, "a clearly better angle DOES earn a cut (%d segments)" % len(segs2))
    t(any(x["file"] == "c.mp4" for x in segs2), "and the edit switches to it")
    t(all(x["t1"] - x["t0"] >= MIN_SEG - 1e-6 for x in segs2),
      "no segment shorter than MIN_SEG")
    holds = [x["t1"] - x["t0"] for x in segs2[:-1]]
    t(all(h >= MIN_HOLD - 1e-6 for h in holds) if holds else True,
      "no angle is cut away from before MIN_HOLD (%s)"
      % ", ".join("%.0fs" % h for h in holds))

    # a near-tie must NOT cause a cut
    def noisy(cam, at, span):
        return 1.0 + (0.05 if cam["file"] == "b.mp4" else 0.0)
    segs3, _ = build_plan(cams, t0=40.0, t1=100.0, scorer=noisy, bed=cams[0])
    t(len(segs3) <= 2,
      "KNOWN-BAD CONTROL: a %.2f difference is below SWITCH_MARGIN and does NOT "
      "flicker the edit (%d segments)" % (0.05, len(segs3)))

    segs = segs2
    print("KNOWN-BAD CONTROLS - a bad plan must be REFUSED, not clamped")
    bad = list(segs)
    bad.append({"t0": 100.0, "t1": 110.0, "file": "a.mp4", "label": "CAMERA 1",
                "local_in": 100.0, "local_out": 110.0})
    e = check_plan(bad, cams)
    t(any("outside" in x for x in e), "a segment past the camera's duration is refused")

    gap = [dict(segs[0]), dict(segs[1])]
    gap[1]["t0"] = gap[0]["t1"] + 3.0
    t(any("gap" in x for x in check_plan(gap, cams)), "a gap in the timeline is refused")

    ov = [dict(segs[0]), dict(segs[1])]
    ov[1]["t0"] = ov[0]["t1"] - 2.0
    t(any("gap" in x for x in check_plan(ov, cams)), "an overlap is refused")

    unk = [{"t0": 0, "t1": 5, "file": "zzz.mp4", "label": "X",
            "local_in": 0, "local_out": 5}]
    t(any("unknown file" in x for x in check_plan(unk, cams)), "an unknown source is refused")

    print("labels never invent a name")
    t(all(s["label"].startswith("CAMERA") for s in segs),
      "labels are CAMERA n - Denver files carry no officer name")

    print()
    if fails:
        print("SELFTEST FAILED: %d" % len(fails))
        for f in fails:
            print("   - %s" % f)
        return 1
    print("CUTPLAN_SELFTEST_OK")
    return 0


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--dir")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--render", metavar="OUT")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.dir:
        ap.print_help()
        return 0
    cams = load(a.dir)
    segs, bed = build_plan(cams)
    errs = check_plan(segs, cams)
    print("CAMERAS")
    for c in cams:
        print("   %-42s start %+8.2fs  dur %7.1fs  %s"
              % (c["file"][:42], c["start"], c["dur"], c["label"]))
    print()
    print("PLAN  %d segments, %.1fs -> %.1fs (%.1f min)"
          % (len(segs), segs[0]["t0"] if segs else 0, segs[-1]["t1"] if segs else 0,
             ((segs[-1]["t1"] - segs[0]["t0"]) / 60.0) if segs else 0))
    for s in segs:
        print("   %7.1f-%7.1f  %-9s  %s @ %.1fs"
              % (s["t0"], s["t1"], s["label"], s["file"][:34], s["local_in"]))
    print("   audio bed: %s (most speech energy, measured)" % (bed["file"] if bed else "none"))
    if errs:
        print("PLAN_REFUSED")
        for e in errs:
            print("   %s" % e)
        return 3
    print("PLAN_OK")
    with open(os.path.join(a.dir, "cutplan.json"), "w", encoding="utf-8") as fh:
        json.dump({"segments": segs, "bed": bed["file"]}, fh, indent=1)
    if a.render:
        print("rendering...")
        rc, err = render(a.dir, segs, bed, a.render)
        if rc:
            print("RENDER_FAILED %s" % err)
            return rc
        ok, got, want = verify_render(a.render, segs)
        print("rendered %s  duration %.2fs (plan %.2fs)" % (a.render, got, want))
        print("RENDER_MATCHES_PLAN" if ok else "RENDER_LENGTH_MISMATCH")
        return 0 if ok else 3
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
