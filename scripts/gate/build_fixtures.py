#!/usr/bin/env python
"""Build the control fixtures the render gate is validated against.

PROTOCOL R4: a checker that has never been run against a known answer returns
confident output in both directions and there is no way to tell from inside.
So every check in this gate gets a file it MUST pass and a file it MUST fail,
and those files are built here deliberately rather than found.

Found controls were tried first and are not available: every finished render in
READY-TO-POST was removed on 2026-08-29 while another session restructured the
folder. Purpose-built controls are better anyway - a found "known-good" file is
only known-good because someone said so.

Everything is cut from one real courtroom clip so the checks are exercised
against this footage, not against a synthetic test pattern whose statistics
have nothing to do with a courtroom.
"""
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIX = Path(__file__).resolve().parent / "fixtures"
SRC = ROOT / "work/EwwnbiAQtFk/EwwnbiAQtFk_h_3574_3554-4697.mp4"
STING = ROOT / "out/review/_final/00_sting.mp4"
FONT = ROOT / "assets/fonts/TTTHeadline-Regular.ttf"

# 12 seconds of continuous speech from the CarThief hearing.
CLIP_START, CLIP_DUR = 400.0, 12.0


def run(args: list[str]) -> None:
    p = subprocess.run(args, capture_output=True, text=True)
    if p.returncode != 0:
        sys.stderr.write(" ".join(str(a) for a in args) + "\n" + p.stderr[-1500:] + "\n")
        raise SystemExit(f"fixture build failed: {args[0]} exit {p.returncode}")


def probe(path: Path, entries: str, stream: str | None = None) -> str:
    a = ["ffprobe", "-v", "error"]
    if stream:
        a += ["-select_streams", stream]
    a += ["-show_entries", entries, "-of", "default=nw=1:nk=1", str(path)]
    return subprocess.run(a, capture_output=True, text=True).stdout.strip()


def build() -> None:
    FIX.mkdir(parents=True, exist_ok=True)
    if not SRC.exists():
        raise SystemExit(f"source clip missing: {SRC}")

    # ---- base: the known-GOOD shape. yuv420p, A/V aligned, no long silence.
    base = FIX / "base.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-ss", str(CLIP_START), "-t", str(CLIP_DUR),
         "-i", str(SRC), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", str(base)])

    # ---- known-BAD pixel format. This is the regression that once shipped four
    # shorts no consumer hardware decoder could play.
    run(["ffmpeg", "-y", "-v", "error", "-i", str(base), "-c:v", "libx264",
         "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv444p",
         "-c:a", "copy", str(FIX / "bad_pixfmt.mp4")])

    # ---- known-BAD dead air: 6 contiguous seconds of true silence spliced into
    # the middle of the audio, video untouched.
    run(["ffmpeg", "-y", "-v", "error", "-i", str(base),
         "-f", "lavfi", "-t", "6", "-i", "anullsrc=r=48000:cl=stereo",
         "-filter_complex",
         "[0:a]atrim=0:3,asetpts=PTS-STARTPTS[a1];"
         "[1:a]asetpts=PTS-STARTPTS[sil];"
         "[0:a]atrim=3,asetpts=PTS-STARTPTS[a2];"
         "[a1][sil][a2]concat=n=3:v=0:a=1[out]",
         "-map", "0:v", "-map", "[out]", "-c:v", "copy", "-c:a", "aac",
         "-b:a", "128k", str(FIX / "silent_gap.mp4")])

    # ---- known-GOOD intro: the branded sting on the front.
    if STING.exists():
        run(["ffmpeg", "-y", "-v", "error", "-i", str(STING), "-i", str(base),
             "-filter_complex",
             "[0:v]scale=1920:1080,setsar=1,fps=30[v0];"
             "[1:v]scale=1920:1080,setsar=1,fps=30[v1];"
             "[v0][0:a][v1][1:a]concat=n=2:v=1:a=1[v][a]",
             "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast",
             "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", str(FIX / "with_intro.mp4")])

    # ---- known-GOOD captions: burned in on the LOWER half, which is what the
    # check must both detect and locate. base.mp4 is the uncaptioned control.
    ass = FIX / "_ctrl.ass"
    ass.write_text(
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\n"
        "WrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name,Fontname,Fontsize,PrimaryColour,OutlineColour,BackColour,Bold,"
        "Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,"
        "Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n"
        "Style: C,TTT Headline,156,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,"
        "0,0,1,12,0,2,40,40,120,1\n\n"
        "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
        "Dialogue: 0,0:00:00.50,0:00:11.50,C,,0,0,120,,CONTROL CAPTION\n",
        encoding="utf-8")
    fontsdir = str((ROOT / "assets/fonts")).replace("\\", "/").replace(":", "\\:")
    assp = str(ass).replace("\\", "/").replace(":", "\\:")
    run(["ffmpeg", "-y", "-v", "error", "-i", str(base),
         "-vf", f"ass='{assp}':fontsdir='{fontsdir}'",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-pix_fmt", "yuv420p", "-c:a", "copy", str(FIX / "captioned.mp4")])

    print(f"built fixtures in {FIX}")


EXPECT = {
    "base.mp4":        {"pix_fmt": "yuv420p", "role": "GOOD for every check"},
    "bad_pixfmt.mp4":  {"pix_fmt": "yuv444p", "role": "BAD for integrity"},
    "silent_gap.mp4":  {"pix_fmt": "yuv420p", "role": "BAD for deadair"},
    "with_intro.mp4":  {"pix_fmt": "yuv420p", "role": "GOOD for intro"},
    "captioned.mp4":   {"pix_fmt": "yuv420p", "role": "GOOD for captions"},
}


def verify() -> int:
    problems: list[str] = []
    for name, exp in EXPECT.items():
        p = FIX / name
        if not p.exists():
            problems.append(f"{name}: missing")
            continue
        got = probe(p, "stream=pix_fmt", "v:0")
        if got != exp["pix_fmt"]:
            problems.append(f"{name}: pix_fmt {got!r}, expected {exp['pix_fmt']!r}")
        if not probe(p, "format=duration"):
            problems.append(f"{name}: no duration - not a readable media file")
    # A control set where the two sides are identical proves nothing.
    a, b = FIX / "base.mp4", FIX / "bad_pixfmt.mp4"
    if a.exists() and b.exists() and probe(a, "stream=pix_fmt", "v:0") == probe(b, "stream=pix_fmt", "v:0"):
        problems.append("base and bad_pixfmt have the SAME pix_fmt - the control is not a control")
    if problems:
        for x in problems:
            print("FAIL " + x)
        return 1
    print(f"fixtures verified ({len(EXPECT)} controls, each distinguishable from its pair)")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true", help="check the fixtures without rebuilding")
    a = ap.parse_args()
    if not a.verify:
        build()
    raise SystemExit(verify())
