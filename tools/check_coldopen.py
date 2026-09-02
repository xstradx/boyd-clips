# -*- coding: utf-8 -*-
"""R49 - a long-form opens on the hook, labelled, before the sting.

Nathan, 2026-09-02: *"Also I think you should add a 5 second or so clip of the
hook or drama later in the vid in the beginning of long form and put "Coming
up..." or something"*.

WHAT WAS WRONG. Every long-form to date opened on the sting and then the
hearing from its first word; the viewer had no reason to stay past the intro.

WHAT IS MEASURED - on the FILE, against the sidecar `<out>.coldopen.json` the
renderer writes (a file with no sidecar has no cold open and FAILS):
  1. the frame at output t = 2.5 s is the SOURCE frame at src_start + 2.5 s
     (crop / scale / pad applied) - the footage is the hook, not the opening;
  2. that frame matches the hook BETTER than it matches the body's own start,
     and src_start is >= 30 s into the body ("later in the vid");
  3. the label box holds far more near-white pixels than the same box in the
     untouched source frame (the label is drawn), and the same box after the
     cold open holds no more than the source (the label is gone);
  4. the last frame of the cold open is near black (fade out), and the last
     0.1 s of its audio is quieter than its middle (afade);
  5. the sting follows: the frame at cold_end + intro/2 is the sting's own
     frame at intro/2;
  6. the file is at least cold + sting + body-floor long, and the sidecar's
     output_s matches ffprobe.

    python tools/check_coldopen.py OUT.mp4     -> COLDOPEN_OK / COLDOPEN_FAIL
    python tools/check_coldopen.py --selftest  -> synthetic render with and
        without the cold open; the one without must FAIL; the real known-bad
        (a READY-TO-POST long-form that starts on the sting) must FAIL
"""
import json
import os
import subprocess
import sys
import tempfile

import numpy as np

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

CMP_W, CMP_H = 480, 270          # frames are compared downscaled, grey
# "same footage" = the 99th percentile of |diff| (0-255). Measured on TORRES:
# the same frame after a re-encode is p99 3.0 (mean 1.7); ONE second away it is
# p99 36 (mean 2.5); the opening is p99 145. The mean cannot tell a static
# courtroom one second apart; p99 can.
MATCH_MAX = 12.0
FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
LABEL_MIN_EXTRA_WHITE = 1500     # near-white pixels the label adds to its box
LABEL_MAX_AFTER_WHITE = 600      # extra near-white allowed in the box once the label is gone
FADE_MAX_LUMA = 40.0             # mean luma of the cold open's last frame
WHITE = 225
PROBE_T = 2.5                    # seconds into the cold open where frames are compared
BODY_FLOOR_S = 60.0              # a file shorter than cold + sting + this is not a long-form


def _run(argv):
    return subprocess.run(argv, capture_output=True)


def probe_duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def frame(path, t, vf=None, size=None, gray=True):
    """One frame at t as float32 (H, W) grey or (H, W, 3) RGB."""
    filters = []
    if vf:
        filters.append(vf)
    if size:
        filters.append(f"scale={size[0]}:{size[1]}")
    argv = ["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(path)]
    if filters:
        argv += ["-vf", ",".join(filters)]
    argv += ["-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray" if gray else "rgb24", "-"]
    r = _run(argv)
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError(f"ffmpeg frame failed at {t}: {r.stderr.decode(errors='replace')[-300:]}")
    buf = np.frombuffer(r.stdout, dtype=np.uint8)
    if gray:
        n = buf.size
        if size:
            return buf.reshape(size[1], size[0]).astype(np.float32)
        # no explicit size: ask ffprobe for the dimensions
        w, h = video_size(path)
        return buf[: w * h].reshape(h, w).astype(np.float32)
    w, h = size if size else video_size(path)
    return buf[: w * h * 3].reshape(h, w, 3).astype(np.float32)


def video_size(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    w, h = (int(x) for x in r.stdout.strip().split(",")[:2])
    return w, h


def audio_rms(path, t0, t1):
    r = _run(["ffmpeg", "-v", "error", "-ss", f"{t0:.3f}", "-t", f"{t1 - t0:.3f}", "-i", str(path),
              "-vn", "-ac", "1", "-ar", "48000", "-f", "s16le", "-"])
    a = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32)
    return float(np.sqrt(np.mean(a * a))) if a.size else 0.0


def treatment(side):
    """The body's own crop/scale/pad, so a source frame lands on the canvas
    exactly where the renderer put it."""
    w, h = side["canvas"]
    pre = f"{side['crop']}," if side.get("crop") else ""
    return (f"{pre}scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black")


def p99_match(out_f, path, t, vf, fps, mask=None):
    """p99 |diff| between `out_f` and the source frame at t, taking the best of
    t-1, t, t+1 frames: `-ss` seeks and a trim can land one frame apart, which
    is nothing on court footage (p99 3) and everything on a test pattern.
    `mask` (bool, compare size) drops pixels the renderer is EXPECTED to change
    - the label box - so the label does not count as a footage mismatch."""
    best = 255.0
    for k in (0, -1, 1):
        f = frame(path, max(0.0, t + k / fps), vf=vf, size=(CMP_W, CMP_H))
        d = np.abs(out_f - f)
        if mask is not None:
            d = d[mask]
        best = min(best, float(np.percentile(d, 99)))
    return best


def outside_box(box, w, h):
    """bool mask at compare size: True everywhere except the label box."""
    m = np.ones((CMP_H, CMP_W), dtype=bool)
    x0, y0, x1, y1 = box
    sx, sy = CMP_W / w, CMP_H / h
    m[int(y0 * sy):int(np.ceil(y1 * sy)) + 1, int(x0 * sx):int(np.ceil(x1 * sx)) + 1] = False
    return m


def white_count(rgb, box):
    x0, y0, x1, y1 = box
    r = rgb[y0:y1, x0:x1]
    return int(np.sum(np.all(r >= WHITE, axis=2)))


def check(out_path, source=None, verbose=True):
    """-> list of problems (empty = PASS). `source` overrides the sidecar's
    source path (the renderer writes it; a moved file can be pointed at)."""
    probs = []
    side_path = str(out_path) + ".coldopen.json"
    if not os.path.exists(side_path):
        return [f"no cold open: {os.path.basename(side_path)} missing (R49)"]
    side = json.load(open(side_path, encoding="utf-8"))
    if source is None:
        source = side.get("source")
    if not source or not os.path.exists(source):
        return [f"source not found for frame comparison: {source}"]
    cold = float(side["duration_s"])
    intro_s = float(side["intro_s"])
    off = float(side["offset_s"])
    src0 = float(side["src_start"])
    body0 = float(side["body_start"])
    box = [int(v) for v in side["label_box"]]
    w, h = side["canvas"]
    vf = treatment(side)

    def rep(name, val, ok):
        nonlocal probs
        if verbose:
            print(f"  {'ok  ' if ok else 'FAIL'} {name}: {val}")
        if not ok:
            probs.append(f"{name}: {val}")

    # 6. length
    dur = probe_duration(out_path)
    rep("duration matches sidecar", f"{dur:.3f}s vs {side['output_s']:.3f}s",
        abs(dur - float(side["output_s"])) < 0.15)
    rep("file is cold + sting + a body", f"{dur:.1f}s >= {cold + intro_s + BODY_FLOOR_S:.1f}s",
        dur >= cold + intro_s + BODY_FLOOR_S)
    rep("hook is from later in the body", f"src_start {src0 - body0:.1f}s after body start",
        src0 - body0 >= 30.0)

    # 1 + 2. the footage at t=2.5 is the hook, and not the opening
    t = min(PROBE_T, max(0.5, cold - 1.0))
    fps = float(side.get("fps", 30))
    out_f = frame(out_path, t, size=(CMP_W, CMP_H))
    mask = outside_box(box, w, h)
    d_hook = p99_match(out_f, source, src0 - off + t, vf, fps, mask)
    d_open = p99_match(out_f, source, body0 - off + t, vf, fps, mask)
    rep("cold open frame == source at src_start+t", f"p99 diff {d_hook:.1f} (max {MATCH_MAX})",
        d_hook <= MATCH_MAX)
    rep("cold open frame matches the hook better than the opening",
        f"hook {d_hook:.2f} < opening {d_open:.2f}", d_hook < d_open)

    # 3. the label is drawn during the cold open and gone after it
    t_lab = min(1.0, max(0.2, cold - 1.0))
    out_rgb = frame(out_path, t_lab, size=(w, h), gray=False)
    src_rgb = frame(source, src0 - off + t_lab, vf=vf, size=(w, h), gray=False)
    extra = white_count(out_rgb, box) - white_count(src_rgb, box)
    rep("label drawn in its box during the cold open",
        f"+{extra} near-white px (min {LABEL_MIN_EXTRA_WHITE})", extra >= LABEL_MIN_EXTRA_WHITE)
    t_after = cold + intro_s + t_lab
    after_rgb = frame(out_path, t_after, size=(w, h), gray=False)
    body_rgb = frame(source, body0 - off + t_lab, vf=vf, size=(w, h), gray=False)
    extra_after = white_count(after_rgb, box) - white_count(body_rgb, box)
    rep("label gone after the cold open", f"+{extra_after} near-white px (max {LABEL_MAX_AFTER_WHITE})",
        extra_after <= LABEL_MAX_AFTER_WHITE)

    # 4. fade out, picture and sound
    last = frame(out_path, cold - 0.04, size=(CMP_W, CMP_H))
    rep("cold open ends on black", f"mean luma {float(last.mean()):.1f} (max {FADE_MAX_LUMA})",
        float(last.mean()) <= FADE_MAX_LUMA)
    mid = audio_rms(out_path, cold / 2 - 0.5, cold / 2 + 0.5)
    tail = audio_rms(out_path, cold - 0.10, cold)
    rep("cold open audio fades", f"tail rms {tail:.0f} < 0.5 * mid rms {mid:.0f}",
        tail < 0.5 * mid)

    # 5. the sting follows
    intro = side["intro"]
    if os.path.exists(intro):
        st_out = frame(out_path, cold + intro_s / 2, size=(CMP_W, CMP_H))
        d_st = p99_match(st_out, intro, intro_s / 2,
                         f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                         f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black", fps)
        rep("sting follows the cold open", f"p99 diff {d_st:.1f} (max {MATCH_MAX})", d_st <= MATCH_MAX)
    else:
        rep("sting follows the cold open", f"intro file missing: {intro}", False)
    return probs


def selftest():
    from pathlib import Path
    from boydclips import render
    ok = True

    def chk(name, got, want):
        nonlocal ok
        good = got == want
        ok &= good
        print(f"  {'ok  ' if good else 'MISS'} {name}: got {got!r} want {want!r}")

    with tempfile.TemporaryDirectory() as td:
        # a synthetic hearing: moving test pattern + tone, 100 s, 1280x720
        src = os.path.join(td, "src.mp4")
        _run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
              "testsrc2=size=1280x720:rate=30:duration=100", "-f", "lavfi", "-i",
              "sine=frequency=440:sample_rate=48000:duration=100",
              "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-pix_fmt", "yuv420p",
              "-c:a", "aac", "-shortest", src])
        sting = os.path.join(td, "sting.mp4")
        _run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
              "color=c=0x303030:size=1280x720:rate=30:duration=1", "-f", "lavfi", "-i",
              "sine=frequency=880:sample_rate=48000:duration=1",
              "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
              "-c:a", "aac", "-shortest", sting])
        chk("synthetic source rendered", os.path.exists(src) and probe_duration(src) > 99, True)
        cfg = {"resolution": [1280, 720], "fps": 30, "crf": 28, "watermark": None}
        segs = [render.Segment(start_s=1000.0, end_s=1090.0)]     # source offset 1000
        good = os.path.join(td, "good.mp4")
        render.render_longform(Path(src), 1000.0, segs, cfg, Path(good), intro=Path(sting),
                               coldopen=(1050.0, 1055.0))
        side = json.load(open(good + ".coldopen.json", encoding="utf-8"))
        chk("sidecar written by the renderer", side["src_start"], 1050.0)
        probs = check(good, source=src, verbose=False)
        chk("synthetic cold open PASSES", probs, [])
        # CONTROL 1: the same body without a cold open, with the good sidecar
        # copied beside it - the FILE has to be measured, not the json
        bad = os.path.join(td, "bad.mp4")
        render.render_longform(Path(src), 1000.0, segs, cfg, Path(bad), intro=Path(sting), coldopen=None)
        json.dump(side, open(bad + ".coldopen.json", "w", encoding="utf-8"))
        probs = check(bad, source=src, verbose=False)
        for pr in probs:
            print("        control: " + pr)
        chk("CONTROL no-cold-open file is refused", len(probs) >= 3, True)
        chk("CONTROL fails on the footage comparison",
            any("src_start+t" in p for p in probs), True)
        chk("CONTROL fails on the missing label", any("label drawn" in p for p in probs), True)
        # CONTROL 2: no sidecar at all
        os.remove(bad + ".coldopen.json")
        chk("CONTROL file with no sidecar is refused",
            any("no cold open" in p for p in check(bad, source=src, verbose=False)), True)
        # CONTROL 3: the renderer refuses a hook that is the opening
        try:
            render.render_longform(Path(src), 1000.0, segs, cfg, Path(td) / "x.mp4",
                                   intro=Path(sting), coldopen=(1002.0, 1007.0))
            chk("CONTROL renderer refuses a cold open from the opening", "rendered", "refused")
        except ValueError as e:
            chk("CONTROL renderer refuses a cold open from the opening", "later" in str(e), True)
        try:
            render.render_longform(Path(src), 1000.0, segs, cfg, Path(td) / "y.mp4",
                                   intro=None, coldopen=(1050.0, 1055.0))
            chk("CONTROL renderer refuses a cold open without the sting", "rendered", "refused")
        except ValueError as e:
            chk("CONTROL renderer refuses a cold open without the sting", "sting" in str(e), True)
    # CONTROL 4: the real known-bad. The first 20 s of the pre-R49
    # TORRES_LONGFORM (sting, then the docket call) sit in tools/fixtures with
    # the REAL R49 sidecar beside them - a file that claims a cold open it does
    # not have. It must fail on the footage comparison (its opening is not the
    # hook) AND on the label. The comparison needs the real source; when that
    # is not on this machine the control is SKIPPED out loud, never silently.
    fx = os.path.join(FIX, "torres_longform_pre_r49_head.mp4")
    side = json.load(open(fx + ".coldopen.json", encoding="utf-8"))
    if os.path.exists(side["source"]):
        probs = check(fx, verbose=False)
        chk("CONTROL real pre-R49 opening fails the footage comparison",
            any("src_start+t" in p for p in probs), True)
        chk("CONTROL real pre-R49 opening fails the label check",
            any("label drawn" in p for p in probs), True)
        for p in probs:
            print("        control problem:", p)
    else:
        print("  SKIP  CONTROL real pre-R49 opening: source not on this machine:",
              side["source"])
    print("SELFTEST_PASS check_coldopen" if ok else "SELFTEST_FAIL check_coldopen")
    return 0 if ok else 1


def main(argv):
    if "--selftest" in argv:
        return selftest()
    args = [a for a in argv if not a.startswith("--")]
    src = None
    if "--source" in argv:
        src = argv[argv.index("--source") + 1]
        args = [a for a in args if a != src]
    if not args:
        print(__doc__)
        return 2
    probs = check(args[0], source=src)
    for p in probs:
        print("  " + p)
    print("COLDOPEN_OK" if not probs else f"COLDOPEN_FAIL {len(probs)} problem(s)")
    return 0 if not probs else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
