"""Level each beat, then master the programme once.

Measured problem: the 13 beats come from different source clips and span
-19.3 to -28.0 LUFS integrated -- an 8.7 LU jump between cuts.

Two stages, in this order, per the sequencing rule (all editing on the stem, all
processing once over the assembled file):

  1. Per-beat LINEAR two-pass loudnorm to a common stem level. Linear matters:
     single-pass loudnorm silently applies a dynamic gain rider and returns
     "normalization_type": "dynamic", which pumps courtroom room tone.
  2. Concat, then ONE two-pass linear master over the whole programme.

Targets: programme -14 LUFS integrated, -1.5 dBTP. The -1.5 rather than -1.0
buys headroom for YouTube's AAC/Opus re-encode (AES TD1008 s4 recommends not
exceeding -1 dBTP at a lossy encoder input).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

STEM_TARGET = -19.0     # working stem level for the beats
PROG_I = -14.0          # YouTube programme integrated
PROG_TP = -1.5          # true peak ceiling
PROG_LRA = 7.0


def measure(path: Path, target_i: float, tp: float, lra: float) -> dict:
    """Pass 1: measure with loudnorm in analysis mode, return its JSON."""
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
         "-af", f"loudnorm=I={target_i}:TP={tp}:LRA={lra}:print_format=json",
         "-f", "null", "-"],
        capture_output=True, text=True)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr, re.S)
    if not m:
        raise RuntimeError(f"no loudnorm json for {path.name}:\n{r.stderr[-800:]}")
    return json.loads(m.group())


def apply(src: Path, dst: Path, meas: dict, target_i: float, tp: float,
          lra: float, video: str = "copy", brickwall: float | None = None) -> None:
    """Pass 2: apply linear normalisation using the measured values.

    `brickwall` is a limiter ceiling in dBFS, applied AFTER loudnorm. It is
    needed because loudnorm computes true peak on the float signal, and the AAC
    encode afterwards lifts inter-sample peaks back above the ceiling -- measured
    -1.2 dBFS against a -1.5 target on the first run of this script.

    NOTE: alimiter's `level` option defaults to TRUE, which auto-levels the
    output and undoes the ceiling you just set. It must be disabled.
    """
    f = (f"loudnorm=I={target_i}:TP={tp}:LRA={lra}"
         f":measured_I={meas['input_i']}:measured_TP={meas['input_tp']}"
         f":measured_LRA={meas['input_lra']}:measured_thresh={meas['input_thresh']}"
         f":linear=true:print_format=summary")
    if brickwall is not None:
        limit = 10 ** (brickwall / 20.0)
        f += f",alimiter=limit={limit:.4f}:attack=5:release=50:level=disabled"
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
           "-af", f, "-c:v", video, "-c:a", "aac", "-b:a", "192k",
           "-ar", "48000", "-ac", "2", str(dst)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr[-1200:])


def integrated(path: Path) -> tuple[float, float, float]:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
                        "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True)
    tail = r.stderr[-1500:]
    g = lambda p: float(re.search(p, tail).group(1))
    return g(r"I:\s*(-?[\d.]+) LUFS"), g(r"LRA:\s*(-?[\d.]+) LU"), g(r"Peak:\s*(-?[\d.]+) dBFS")


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    d = root / "out/review/castillo_body"
    beats = sorted(d.glob("beat_*.mp4"))
    if not beats:
        print("no beats found - run build_body.py first")
        return 1

    lvl = d / "levelled"
    lvl.mkdir(exist_ok=True)

    print(f"{'beat':<14} {'before':>9}  ->  {'after':>9}")
    out_beats = []
    for b in beats:
        dst = lvl / b.name
        meas = measure(b, STEM_TARGET, -2.0, PROG_LRA)
        apply(b, dst, meas, STEM_TARGET, -2.0, PROG_LRA)
        after, _, _ = integrated(dst)
        print(f"{b.name:<14} {float(meas['input_i']):>8.1f}  ->  {after:>8.1f} LUFS")
        out_beats.append(dst)

    lst = lvl / "_concat.txt"
    lst.write_text("\n".join(f"file '{p.name}'" for p in out_beats), encoding="utf-8")

    joined = d / "_body_levelled.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-c", "copy", str(joined)], check=True)

    mastered = d / "castillo_body_master.mp4"
    meas = measure(joined, PROG_I, PROG_TP, PROG_LRA)
    # limit 0.5 dB under the TP target: alimiter is sample-domain, the AAC encode
    # afterwards lifts inter-sample peaks back up (measured -1.2 then -1.4 against -1.5)
    apply(joined, mastered, meas, PROG_I, PROG_TP, PROG_LRA, brickwall=PROG_TP - 0.5)

    i, lra, pk = integrated(mastered)
    # Asymmetric tolerance, deliberately. On material with this crest factor you
    # cannot hold both -14.0 integrated AND -1.5 dBTP without compressing harder
    # than courtroom dialogue should be. Landing QUIET is free -- YouTube only
    # attenuates content louder than its target, so a 1 LU deficit is inaudible --
    # whereas breaching true peak costs real codec distortion on every replay.
    # So: never louder than target, up to 1.0 LU quieter is a pass.
    ok_i = (i <= PROG_I + 0.1) and (i >= PROG_I - 1.0)
    ok_pk = pk <= PROG_TP + 0.05
    print(f"\nPROGRAMME MASTER")
    print(f"  integrated {i:.1f} LUFS  (target {PROG_I})   {'PASS' if ok_i else 'FAIL'}")
    print(f"  LRA        {lra:.1f} LU")
    print(f"  true peak  {pk:.1f} dBFS  (ceiling {PROG_TP})  {'PASS' if ok_pk else 'FAIL'}")
    print(f"-> {mastered}")
    return 0 if (ok_i and ok_pk) else 1


if __name__ == "__main__":
    raise SystemExit(main())
