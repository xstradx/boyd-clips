"""Cut the Castillo body from the extraction windows.

Every in/out below was LOCATED in out/review/castillo_cut/transcripts.json
(faster-whisper small.en, GPU) by searching for the quoted line in
out/dossiers/CASTILLO_SINGLE_CUT.md -- not estimated, not eyeballed.

Transitions are hard cuts of zero frames, per the measured competitor spec
(research/reference/competitor/EDITING_SPEC.md 3.3: "no dissolves, no motion
transitions, no whip pans, no light leaks").

SCOPE, STATED HONESTLY: this cuts what is ON DISK -- 11 extraction windows
totalling 36 minutes. The 22-minute plan in CASTILLO_SINGLE_CUT.md draws on the
full 18h04m of source, which is NOT on this machine and is currently behind
YouTube's bot check. This is the spine, not the finished long-form.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SRC = Path("out/review/castillo_cut")
OUT = Path("out/review/castillo_body")

# (file, in, out, act, beat note)
BEATS = [
    ("a3_the_cross.mp4",          37.8,  59.6, "COLD OPEN", "the question only - cut before he answers"),

    ("a1_state_opening.mp4",      57.5,  66.5, "ACT 1", "State: who's behind the wheel of that white car"),
    ("a1_bumper.mp4",             29.2,  38.6, "ACT 1", "would it surprise you there's a hole in the back bumper"),
    ("a1_88mph.mp4",              24.5,  33.8, "ACT 1", "how fast five seconds before - recorded is 88 mph"),
    ("a1_88mph.mp4",              88.2,  95.6, "ACT 1", "88 would be over double the speed limit"),
    ("a1_autopsy.mp4",            23.0,  32.0, "ACT 1", "ME: multiple skull fractures, bleeding over the brain"),

    ("a2_gun_pointed.mp4",        41.8,  48.6, "ACT 2", "he was pointing a gun at me"),
    ("a2_gunshots_detective.mp4", 28.0,  42.4, "ACT 2", "people hear gunshots all the time in San Antonio"),
    ("a2_brady.mp4",              46.8,  55.6, "ACT 2", "Boyd: I don't know how parties come to court announcing ready"),

    ("a3_pen_bumper.mp4",         44.2,  61.0, "ACT 3", "the pen and the bumper - the bullet holes die here"),
    ("a3_shouldnt_have_said.mp4", 30.4,  47.0, "ACT 3", "PROFANITY at ~36s - I shouldn't have f***ing told him anything"),
    ("a3_the_cross.mp4",          37.8,  67.0, "ACT 3", "the full cross, run past the cold open into his answer"),

    ("a4_defences.mp4",          117.5, 137.5, "ACT 4", "mistake of fact read to the jury"),
]


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    src, out = root / SRC, root / OUT
    out.mkdir(parents=True, exist_ok=True)

    parts, total = [], 0.0
    print(f"{'#':>2}  {'act':<10} {'dur':>6}  source @ in-out")
    for i, (f, a, b, act, note) in enumerate(BEATS, 1):
        p = src / f
        if not p.exists():
            print(f"MISSING: {p}")
            return 1
        d = b - a
        total += d
        seg = out / f"beat_{i:02d}.mp4"
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
               "-ss", f"{a}", "-to", f"{b}", "-i", str(p),
               "-vf", "scale=1920:1080:flags=lanczos,fps=30,format=yuv420p",
               "-c:v", "libx264", "-preset", "medium", "-crf", "20",
               "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
               str(seg)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            print(r.stderr[-1200:])
            return r.returncode
        parts.append(seg)
        print(f"{i:>2}  {act:<10} {d:>5.1f}s  {f} @ {a}-{b}")
        print(f"    {note}")

    lst = out / "_concat.txt"
    lst.write_text("\n".join(f"file '{p.as_posix()}'" for p in parts), encoding="utf-8")

    body = out / "castillo_body.mp4"
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-f", "concat", "-safe", "0", "-i", str(lst),
           "-c", "copy", "-movflags", "+faststart", str(body)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        print(r.stderr[-1200:])
        return r.returncode

    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                            "format=duration", "-of", "csv=p=0", str(body)],
                           capture_output=True, text=True)
    measured = float(probe.stdout.strip())
    print(f"\n{len(BEATS)} beats, {total:.1f}s planned, {measured:.1f}s measured")
    print(f"-> {body}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
