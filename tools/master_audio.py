# -*- coding: utf-8 -*-
"""Master any rendered video's audio to broadcast level. Video is copied.

WHY THIS EXISTS AS A SEPARATE TOOL
scripts/assemble_final.py already did this correctly - two-pass loudnorm to
I=-14 TP=-1.5 LRA=7, then a limiter - and NOTHING CALLED IT. Measured
2026-08-31, every shipped file:

    1_LONGFORM_Thompson   -21.2 LUFS   true peak -5.1 dBFS
    2_SHORT_Thompson      -20.5 LUFS   true peak -6.5 dBFS
    SHORT_monkey-v2       -21.9 LUFS   true peak -5.5 dBFS

About 7 dB under the level streaming platforms normalise toward, with 5 dB of
headroom sitting unused. Platforms attenuate loud content; they do not raise
quiet content. So these play quieter than everything beside them in a feed and
the viewer has to reach for the volume.

assemble_final.py is hardcoded to one case's paths, which is why it never became
part of the pipeline. This is the same maths with a file in and a file out.

THREE THINGS THAT MUST NOT BE "SIMPLIFIED":

  1. MEASURE, THEN ONE FIXED GAIN. Single-pass loudnorm is a dynamic
     normaliser: it rides the gain during the file and audibly pumps on speech
     with long pauses, which is exactly what a courtroom recording is. Pass
     one MEASURES (loudnorm print_format=json); pass two applies volume=+G dB
     with G = TARGET_I - measured I. Nothing in pass two can ride the gain.

     Until 2026-09-02 pass two was `loudnorm ... linear=true`, and that flag is
     a REQUEST, not a guarantee: loudnorm falls back to its dynamic mode
     whenever the linear gain would push the true peak past its TP target.
     Speech has a 15-20 dB crest factor and the target leaves 12.5 dB
     (-14 to -1.5), so it fell back on essentially every court file. Measured
     on TORRES_tight.mp4 with print_format=json on the second pass:
     `"normalization_type" : "dynamic"`. The gain-riding at the near-silent
     head of that file followed by the first loud word put a -0.9 dBTP peak
     at 0.3 s (WAV of the same chain: -3.1 dBFS there) and the short engine
     refused the short on its true_peak_max -1.0 floor. With volume+limiter
     the same file measures -14.1 LUFS / -1.9 dBTP and the head peak is gone.

  2. THE LIMITER COMES AFTER THE GAIN, WITH level=disabled. alimiter's own
     auto-level would re-normalise the output and throw away the target that
     was just hit. attack 5 / release 50 ms; the ceiling is a sample ceiling
     (TARGET_TP - CEILING_MARGIN) so the true peak lands under TARGET_TP.

  3. THE CEILING IS PROVED ON THE ENCODED FILE. AAC re-grows peaks the
     limiter removed: on the fixed-gain chain the native encoder added 0.3 dB
     at 192k and ~0 at 256k/384k (2026-09-02, TORRES). YouTube's upload spec
     asks for 384 kbps stereo AAC-LC, so that is the bitrate, and master()
     still measures dst after the encode and, if the true peak is above
     TARGET_TP, lowers the ceiling by the overshoot and encodes again. What is
     guaranteed is the number on the file that ships, not the filter graph.

WHAT THIS DOES NOT DO: it does not fix a bad recording. Raising a -21 LUFS file
to -14 raises its noise floor by the same 7 dB. On Zoom court audio that noise
is real. Denoising is a separate decision and is deliberately NOT bundled in
here, so that if the result sounds worse it is obvious which stage to blame.
"""
import argparse
import json
import os
import re
import subprocess
import sys

TARGET_I, TARGET_TP, TARGET_LRA = -14.0, -1.5, 7.0
CEILING_MARGIN = 0.5      # alimiter sample ceiling sits this far under TARGET_TP
AUDIO_BITRATE = "384k"    # YouTube upload spec, stereo AAC-LC
MAX_PASSES = 4
FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures",
                       "speech_overshoot_torres.mp4")


def _run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError((r.stderr or "")[-1200:])
    return r


def measure(path):
    """Integrated loudness, range and true peak, from ebur128."""
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", path,
         "-af", "ebur128=framelog=quiet:peak=true", "-f", "null", "-"],
        capture_output=True, text=True)
    txt = r.stderr

    def g(rx):
        m = re.findall(rx, txt)
        return float(m[-1]) if m else float("nan")
    return (g(r"I:\s*(-?[\d.]+) LUFS"),
            g(r"LRA:\s*(-?[\d.]+) LU"),
            g(r"Peak:\s*(-?[\d.]+) dBFS"))


def analyse(path):
    """Pass one: loudnorm's own measurement, as JSON."""
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", path, "-af",
         f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}:print_format=json",
         "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"\{[^{}]*input_i[^{}]*\}", r.stderr, re.S)
    if not m:
        raise RuntimeError("loudnorm produced no measurement:\n"
                           + (r.stderr or "")[-800:])
    return json.loads(m.group(0))


def _chain(gain_db, ceiling_db):
    """Pass two: fixed gain, then the limiter. Point 1 and 2 of the docstring."""
    limit = 10 ** (ceiling_db / 20.0)
    return (f"volume={gain_db:.3f}dB,"
            f"alimiter=limit={limit:.4f}:attack=5:release=50:level=disabled")


def _encode(src, dst, gain_db, ceiling_db):
    """One fixed-gain -> limiter -> AAC pass. Video is copied."""
    _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", src,
          "-af", _chain(gain_db, ceiling_db), "-c:v", "copy",
          "-c:a", "aac", "-b:a", AUDIO_BITRATE,
          "-ar", "48000", "-ac", "2", "-movflags", "+faststart", dst])


def master(src, dst, verbose=False):
    """Master src -> dst. Returns (before, after, meas); `after` is measured on
    the ENCODED dst, and dst's true peak is <= TARGET_TP when this returns
    normally (point 3). Raises if MAX_PASSES cannot get there."""
    before = measure(src)
    meas = analyse(src)
    gain = TARGET_I - float(meas["input_i"])
    ceiling = TARGET_TP - CEILING_MARGIN
    after = None
    for n in range(1, MAX_PASSES + 1):
        _encode(src, dst, gain, ceiling)
        after = measure(dst)
        if verbose:
            print(f"       pass {n}: gain {gain:+.2f} dB, ceiling {ceiling:.1f} dBFS"
                  f" -> encoded {after[0]:.1f} LUFS, true peak {after[2]:.1f} dBTP")
        if after[2] <= TARGET_TP:
            return before, after, meas
        # the codec re-grew the peaks; take the ceiling down by what it added
        ceiling -= (after[2] - TARGET_TP) + 0.3
    raise RuntimeError(f"encoded true peak {after[2]:.1f} dBTP still above "
                       f"{TARGET_TP} after {MAX_PASSES} passes (ceiling {ceiling:.1f})")


def report(src, dst, before, after):
    print(f"  in   {os.path.basename(src)}")
    print(f"       integrated {before[0]:6.1f} LUFS   LRA {before[1]:5.1f} LU"
          f"   true peak {before[2]:6.1f} dBFS")
    print(f"  out  {os.path.basename(dst)}")
    print(f"       integrated {after[0]:6.1f} LUFS   LRA {after[1]:5.1f} LU"
          f"   true peak {after[2]:6.1f} dBFS")
    print(f"       gain applied {after[0] - before[0]:+.1f} dB")
    ok_i = -15.0 <= after[0] <= TARGET_I + 0.5
    # no tolerance: master() proves this on the encoded file or raises
    ok_tp = after[2] <= TARGET_TP
    print(f"  loudness {'PASS' if ok_i else 'FAIL'}  "
          f"(want {TARGET_I} +/- 1.0, got {after[0]:.1f})")
    print(f"  peak     {'PASS' if ok_tp else 'FAIL'}  "
          f"(want <= {TARGET_TP}, got {after[2]:.1f})")
    return ok_i and ok_tp


def selftest():
    """Known answers, each with a control that can fail.

    A. a tone 12 dB too quiet comes back at the target (direction + amount).
    B. re-mastering a correct file barely moves it.
    C. tools/fixtures/speech_overshoot_torres.mp4 - the first 8 s of the
       TORRES short (speech, crest 14.7 dB): the OLD `loudnorm linear=true`
       pass two reports normalization_type "dynamic" on it (the control - the
       material really does trigger the fallback), and master() on the same
       file lands at the target with its LRA unchanged (linear gain cannot
       change LRA; dynamic mode does) and the ENCODED true peak <= TARGET_TP.
    D. the encoded-peak retry: with a stand-in encoder that re-grows peaks
       by 3 dB on its first pass, master() must come back <= TARGET_TP in
       more than one pass - the guarantee is measured, not assumed. Runs on
       the speech fixture, whose peaks sit AT the limiter ceiling (the tone
       peaks 10 dB under it and +3 dB never crosses the target there).
    """
    import tempfile
    d = tempfile.mkdtemp(prefix="master_")
    ok = True

    def chk(label, hit):
        nonlocal ok
        ok &= bool(hit)
        print(f"  {'OK  ' if hit else 'FAIL'}  {label}")

    # A + B
    quiet = os.path.join(d, "quiet.mp4")
    out = os.path.join(d, "loud.mp4")
    _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
          "-f", "lavfi", "-i", "sine=frequency=300:duration=20:sample_rate=48000",
          "-f", "lavfi", "-i", "color=c=black:s=320x180:d=20:r=30",
          "-af", "volume=-26dB", "-c:v", "libx264", "-preset", "ultrafast",
          "-c:a", "aac", "-shortest", quiet])
    b, a, _ = master(quiet, out)
    chk(f"A tone {b[0]:.1f} -> {a[0]:.1f} LUFS, peak {a[2]:.1f} (target {TARGET_I}, <= {TARGET_TP})",
        abs(a[0] - TARGET_I) <= 1.5 and a[2] <= TARGET_TP)
    b2, a2, _ = master(out, os.path.join(d, "again.mp4"))
    chk(f"B already-correct file moves {a2[0] - b2[0]:+.1f} dB (want ~0)",
        abs(a2[0] - b2[0]) <= 1.5)

    # C
    chk(f"C fixture present {os.path.relpath(FIXTURE)}", os.path.exists(FIXTURE))
    if os.path.exists(FIXTURE):
        m = analyse(FIXTURE)
        old_af = (f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}"
                  f":measured_I={m['input_i']}:measured_TP={m['input_tp']}"
                  f":measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}"
                  f":linear=true:print_format=json")
        r = subprocess.run(["ffmpeg", "-hide_banner", "-i", FIXTURE, "-af", old_af,
                            "-f", "null", "-"], capture_output=True, text=True).stderr
        nt = re.search(r'"normalization_type"\s*:\s*"(\w+)"', r)
        nt = nt.group(1) if nt else "?"
        chk(f"C CONTROL old chain (loudnorm linear=true) on speech reports '{nt}' (want dynamic)",
            nt == "dynamic")
        bf, af_, _ = master(FIXTURE, os.path.join(d, "fixture_mastered.mp4"))
        chk(f"C master(): {bf[0]:.1f} -> {af_[0]:.1f} LUFS (target {TARGET_I} +/- 1)",
            abs(af_[0] - TARGET_I) <= 1.0)
        chk(f"C master(): LRA {bf[1]:.1f} -> {af_[1]:.1f} LU (linear gain keeps it, +/- 0.5)",
            abs(af_[1] - bf[1]) <= 0.5)
        chk(f"C master(): encoded true peak {af_[2]:.1f} dBTP (<= {TARGET_TP})",
            af_[2] <= TARGET_TP)

    # D - the retry is exercised with an encoder that misbehaves once
    global _encode
    real = _encode
    calls = []

    def growing(src, dst, gain_db, ceiling_db):
        calls.append(ceiling_db)
        extra = ",volume=3dB" if len(calls) == 1 else ""
        limit = 10 ** (ceiling_db / 20.0)
        _run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", src,
              "-af", f"volume={gain_db:.3f}dB,alimiter=limit={limit:.4f}"
                     f":attack=5:release=50:level=disabled{extra}",
              "-c:v", "copy", "-c:a", "aac", "-b:a", AUDIO_BITRATE,
              "-ar", "48000", "-ac", "2", dst])
    try:
        _encode = growing
        _, a4, _ = master(FIXTURE if os.path.exists(FIXTURE) else out,
                          os.path.join(d, "retry.mp4"))
    finally:
        _encode = real
    chk(f"D stand-in encoder +3 dB on pass 1: {len(calls)} passes, ceilings "
        f"{[round(c, 1) for c in calls]}, final peak {a4[2]:.1f} (<= {TARGET_TP})",
        len(calls) >= 2 and a4[2] <= TARGET_TP)

    print("SELFTEST_PASS master_audio" if ok else "SELFTEST_FAIL master_audio")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", nargs="?")
    ap.add_argument("--out")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.src:
        ap.error("give a source file, or --selftest")
    dst = a.out or os.path.splitext(a.src)[0] + "_MASTERED.mp4"
    before, after, _ = master(a.src, dst, verbose=True)
    ok = report(a.src, dst, before, after)
    print(("MASTER_OK " if ok else "MASTER_FAIL ") + dst)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
