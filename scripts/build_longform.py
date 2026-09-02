"""Build the full Castillo long-form from the pulled source sections.

Each scene is anchored on a quote LOCATED in src_transcripts.json (faster-whisper
medium.en, GPU, word timestamps) -- never on an estimated timecode. The scene
then expands outward from that anchor to a target duration, snapping to sentence
boundaries so no scene starts or ends mid-clause.

Structure follows out/dossiers/CASTILLO_SINGLE_CUT.md: cold open, then four acts.
Transitions are hard cuts of zero frames per the measured competitor spec.
"""
from __future__ import annotations

import json
import subprocess
import os
import sys
from pathlib import Path

SRC = Path("out/source")
OUT = Path("out/review/castillo_long")

# (source file, anchor substring, target seconds, act, note)
SCENES = [
    ("cross_full_2ks4a-kHG9I.mp4",         "do not remember"      ,   26, "COLD OPEN",
     "the question only - cut before the answer"),

    ("state_opening_nWkWEjol89g.mp4",      "behind the wheel",         150, "ACT 1 - THE NIGHT",
     "State's opening: who was behind the wheel"),
    ("bumper_hole_9hW7kh5WCsA.mp4",        "hole in the back bumper",  140, "ACT 1 - THE NIGHT",
     "the first crack: a hole in the bumper"),
    ("tesla_88mph_QGUbKowPfBk.mp4",        "88 miles per hour",        140, "ACT 1 - THE NIGHT",
     "the Tesla's own data: 88 mph five seconds out"),
    ("me_autopsy_4zkUTUavW4I.mp4",         "skull fracture" ,           90, "ACT 1 - THE NIGHT",
     "the medical examiner - kept short deliberately"),

    ("gun_pointed_TxxAq5nMLJY.mp4",        "pointing a gun",           150, "ACT 2 - HIS STORY",
     "he was pointing a gun at me"),
    ("gunshots_detective_ClJbZCYeVJ4.mp4", "gunshots all the time",    140, "ACT 2 - HIS STORY",
     "people hear gunshots all the time in San Antonio"),
    ("brady_fight_jK9OM6ZCkF0.mp4",        "announcing ready",         150, "ACT 2 - HIS STORY",
     "Boyd on the undisclosed witnesses"),

    ("pen_bumper_jK9OM6ZCkF0.mp4",         "stabbed it into",          150, "ACT 3 - IT COMES APART",
     "the pen and the bumper - the bullet holes die here"),
    ("shouldnt_have_said_2ks4a-kHG9I.mp4", "told him anything",        160, "ACT 3 - IT COMES APART",
     "the jail call - PROFANITY present, censor in text only"),
    ("cross_full_2ks4a-kHG9I.mp4",         "do not remember"      ,  180, "ACT 3 - IT COMES APART",
     "the full cross, run past the cold open into his answer"),

    ("defences_2ks4a-kHG9I.mp4",           "mistake of fact",          150, "ACT 4 - THE VERDICT",
     "the three defences read to the jury"),
]


def find_anchor(segs: list, needle: str) -> int:
    n = needle.lower()
    for i, s in enumerate(segs):
        if n in s["t"].lower():
            return i
    return -1


def expand(segs: list, i: int, target: float, cold_open: bool) -> tuple[float, float]:
    """Grow a window around segment i until it reaches `target` seconds.

    Snaps to segment (sentence) boundaries. A cold open only grows BACKWARD --
    it must end on the anchor so the answer is withheld.
    """
    lo = hi = i
    while True:
        dur = segs[hi]["e"] - segs[lo]["s"]
        if dur >= target:
            break
        grew = False
        if lo > 0:
            lo -= 1
            grew = True
        if not cold_open and hi < len(segs) - 1:
            hi += 1
            grew = True
        if not grew:
            break

    # Growing adds a whole segment to each side per pass, so it can overshoot the
    # target by up to two long segments (one scene came out at 265 s against 160).
    # Give back the outermost segments while the window still clears the target,
    # preferring to trim the tail so the anchor keeps its run-up.
    while hi > lo:
        if not cold_open and segs[hi - 1]["e"] - segs[lo]["s"] >= target:
            hi -= 1
            continue
        if segs[hi]["e"] - segs[lo + 1]["s"] >= target:
            lo += 1
            continue
        break

    return segs[lo]["s"], segs[hi]["e"]


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    src, out = root / SRC, root / OUT
    out.mkdir(parents=True, exist_ok=True)

    tpath = src / "src_transcripts.json"
    if not tpath.exists():
        print("src_transcripts.json missing - transcribe the source sections first")
        return 1
    T = json.loads(tpath.read_text(encoding="utf-8"))

    parts, total, rows = [], 0.0, []
    for idx, (f, anchor, target, act, note) in enumerate(SCENES, 1):
        segs = T.get(f)
        if not segs:
            print(f"NO TRANSCRIPT for {f}")
            return 1
        i = find_anchor(segs, anchor)
        if i < 0:
            print(f"ANCHOR NOT FOUND in {f}: {anchor!r}")
            return 1
        a, b = expand(segs, i, target, cold_open=(act == "COLD OPEN"))
        d = b - a
        total += d
        seg = out / f"scene_{idx:02d}.mp4"
        # 30ms audio fade in and out on EVERY segment.
        #
        # Honest note on why, because I got this wrong first: I told Nathan the
        # missing fade was why his edits sound choppy. Then I measured it -
        # concatenated two segments cut at the loudest points in a real hearing,
        # with and without fades - and the join discontinuity was 670 against a
        # 99.9th-percentile speech transient of 2151, i.e. 0.31x. There is no
        # audible click, because each segment is AAC-encoded separately and the
        # decoder's overlap-add smooths the boundary. The real cause of choppy
        # was cut PLACEMENT (see the cut gate in make_short.py).
        #
        # It goes in anyway: it is standard practice, it costs nothing, and it
        # protects the case this pipeline does not currently hit - a segment
        # boundary that lands on a sustained loud vowel, or any future path that
        # concatenates PCM rather than separately-encoded AAC.
        fade = 0.03
        af = (f"afade=t=in:st=0:d={fade},"
              f"afade=t=out:st={max(0.0, (b - a) - fade):.3f}:d={fade}")
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
               "-ss", f"{a:.2f}", "-to", f"{b:.2f}", "-i", str(src / f),
               "-vf", "scale=1920:1080:flags=lanczos,fps=30,format=yuv420p",
               "-af", af,
               "-c:v", "libx264", "-preset", "medium", "-crf", "20",
               "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
               str(seg)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            print(r.stderr[-1200:])
            return r.returncode
        parts.append(seg)
        rows.append((idx, act, d, f, a, b, note))
        print(f"{idx:>2}  {act:<22} {d:>6.1f}s  {f} @ {a:.1f}-{b:.1f}", flush=True)

    lst = out / "_concat.txt"
    lst.write_text("\n".join(f"file '{p.name}'" for p in parts), encoding="utf-8")
    body = out / "castillo_long_body.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-c", "copy", "-movflags", "+faststart", str(body)], check=True)

    # ------------------------------------------------------------- MASTERING
    # ONCE over the assembled programme, never per segment. Normalising each
    # scene independently would push every scene to the same loudness and so
    # make the level JUMP at each join - a quiet aside and a raised voice would
    # come out equally loud, which destroys exactly the dynamics that make a
    # hearing worth watching.
    #
    # Measured 2026-08-31: shipped long-form sat at -21.2 LUFS with true peak
    # -5.1 dBFS, about 7dB under the level platforms normalise toward and with
    # 5dB of headroom unused. scripts/assemble_final.py already had this exact
    # two-pass loudnorm and was called by nothing.
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
        import master_audio as _ma
        _tmp = body.with_name(body.stem + "_m.mp4")
        _b, _a, _ = _ma.master(str(body), str(_tmp))
        os.replace(str(_tmp), str(body))
        print(f"\nmastered: {_b[0]:.1f} -> {_a[0]:.1f} LUFS ({_a[0]-_b[0]:+.1f} dB), "
              f"true peak {_a[2]:.1f} dBFS")
        if not (-15.0 <= _a[0] <= -13.5):
            print(f"  LOUDNESS GATE FAILED: {_a[0]:.1f} LUFS outside -14 +/- 1")
            return 1
    except Exception as _me:                          # noqa: BLE001
        # Loud failure. Silence is how assemble_final.py went unused for months.
        print(f"\nMASTERING FAILED: {str(_me)[:200]}")
        print("  Shipping an unmastered long-form is a decision, not a default.")
        return 1

    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "csv=p=0", str(body)], capture_output=True, text=True)
    m = float(probe.stdout.strip())
    print(f"\n{len(SCENES)} scenes, {total/60:.1f} min planned, {m/60:.1f} min measured")
    print(f"-> {body}")

    (out / "EDL.md").write_text(
        "# Castillo long-form EDL\n\nEvery in/out located in src_transcripts.json, "
        "snapped to sentence boundaries.\n\n"
        "| # | act | dur | source | in | out | note |\n|---|---|---:|---|---:|---:|---|\n" +
        "\n".join(f"| {i} | {a} | {d:.1f}s | `{f}` | {s:.1f} | {e:.1f} | {n} |"
                  for i, a, d, f, s, e, n in rows) + "\n",
        encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
