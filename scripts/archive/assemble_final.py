"""Final assembly: sting -> card opening -> long-form body, watermarked and mastered.

Watermark placement and size follow scripts/make_watermarks_v2.py, which Nathan
signed off: TOP-RIGHT (YouTube's own bug and the player controls both live
bottom-right, and the progress bar eats the bottom edge on hover), 6% of frame
width, translucent.

Audio is mastered ONCE over the assembled programme -- see scripts/master_body.py
for why the limiter must come after loudnorm and why `alimiter level` must be
disabled.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

LOGO = Path(r"C:\Users\natha\OneDrive\Desktop\boyd-brand\logo_transparent.png")
STING = Path(r"C:\Users\natha\OneDrive\Desktop\boyd-brand\sting.mp4")

WM_WIDTH_PCT = 0.06
WM_OPACITY = 0.55        # raised from 0.42 after the shadow test - see watermark()
WM_MARGIN = 34           # px from the top-right corner

PROG_I, PROG_TP, PROG_LRA = -14.0, -1.5, 7.0


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode:
        raise RuntimeError(" ".join(str(c) for c in cmd[:6]) + "\n" + r.stderr[-1500:])
    return r


def silent_audio(src: Path, dst: Path) -> None:
    """Give a video without an audio track a silent stereo one, so concat matches."""
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
         "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
         "-shortest", "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(dst)])


def has_audio(p: Path) -> bool:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a",
                        "-show_entries", "stream=index", "-of", "csv=p=0", str(p)],
                       capture_output=True, text=True)
    return bool(r.stdout.strip())


def watermark(src: Path, dst: Path) -> None:
    """Overlay the TTT mark top-right, with a soft dark shadow behind it.

    The shadow is not decoration. Tested against a real frame first: the plain
    translucent mark is near-invisible on a bright courtroom wall, which is the
    exact failure make_watermarks_v2.py warns about in its own docstring. A
    blurred black copy offset 2px behind holds the mark on light AND dark
    backgrounds without raising its opacity into distraction.
    """
    wm_w = int(1920 * WM_WIDTH_PCT)
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-i", str(src), "-i", str(LOGO),
         "-filter_complex",
         f"[1:v]scale={wm_w}:-1,format=rgba,split=2[m1][m2];"
         f"[m1]lutrgb=r=0:g=0:b=0,boxblur=4:1,colorchannelmixer=aa=0.60[sh];"
         f"[0:v][sh]overlay=W-w-{WM_MARGIN-2}:{WM_MARGIN+2}[bg];"
         f"[m2]colorchannelmixer=aa={WM_OPACITY}[mk];"
         # format=rgb keeps the brand red exact through the alpha composite;
         # format=yuv420p AFTER it is what makes the file playable. Without the
         # second one, libx264 sees 4:4:4 data and writes High 4:4:4 Predictive
         # / yuv444p — which ffprobe and ffmpeg read happily and no consumer
         # player, hardware decoder or browser can open. Shipped that once.
         f"[bg][mk]overlay=W-w-{WM_MARGIN}:{WM_MARGIN}:format=rgb,format=yuv420p[v]",
         "-map", "[v]", "-map", "0:a?",
         "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.0",
         "-c:a", "copy", "-movflags", "+faststart", str(dst)])


def loudnorm_json(p: Path) -> dict:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(p),
                        "-af", f"loudnorm=I={PROG_I}:TP={PROG_TP}:LRA={PROG_LRA}:print_format=json",
                        "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr, re.S)
    if not m:
        raise RuntimeError("no loudnorm json\n" + r.stderr[-800:])
    return json.loads(m.group())


def measure(p: Path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(p),
                        "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True)
    t = r.stderr[-1500:]
    g = lambda pat: float(re.search(pat, t).group(1))
    return g(r"I:\s*(-?[\d.]+) LUFS"), g(r"LRA:\s*(-?[\d.]+) LU"), g(r"Peak:\s*(-?[\d.]+) dBFS")


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    work = root / "out/review/_final"
    work.mkdir(parents=True, exist_ok=True)

    body = root / "out/review/castillo_long/castillo_long_body.mp4"
    opening = root / "out/review/castillo_open.mp4"
    if not body.exists():
        print("long body missing - run build_longform.py first")
        return 1

    pieces = []

    if STING.exists():
        s = work / "00_sting.mp4"
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(STING),
             "-vf", "scale=1920:1080,fps=30,format=yuv420p",
             "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-an", str(work / "_s.mp4")])
        silent_audio(work / "_s.mp4", s)
        pieces.append(s)

    if opening.exists():
        o = work / "01_opening.mp4"
        silent_audio(opening, o) if not has_audio(opening) else run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(opening),
             "-c", "copy", str(o)])
        pieces.append(o)

    b = work / "02_body.mp4"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(body),
         "-c", "copy", str(b)])
    pieces.append(b)

    lst = work / "_concat.txt"
    lst.write_text("\n".join(f"file '{p.name}'" for p in pieces), encoding="utf-8")
    joined = work / "joined.mp4"
    # Audio is re-encoded, never stream-copied, across this join. The pieces are
    # a silent sting, a silent card opening and a live body; with -c copy the AAC
    # priming samples accumulate and the decoder can drop audio outright.
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat",
         "-safe", "0", "-i", str(lst), "-c:v", "copy",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
         "-af", "aresample=async=1:first_pts=0", str(joined)])

    marked = work / "marked.mp4"
    if LOGO.exists():
        watermark(joined, marked)
        print(f"watermark: top-right, {int(1920*WM_WIDTH_PCT)}px wide, {int(WM_OPACITY*100)}% opacity")
    else:
        print(f"NO LOGO at {LOGO} - shipping unwatermarked, flagged")
        marked = joined

    final = root / "out/review/castillo_FINAL.mp4"
    meas = loudnorm_json(marked)
    limit = 10 ** ((PROG_TP - 0.5) / 20.0)
    af = (f"loudnorm=I={PROG_I}:TP={PROG_TP}:LRA={PROG_LRA}"
          f":measured_I={meas['input_i']}:measured_TP={meas['input_tp']}"
          f":measured_LRA={meas['input_lra']}:measured_thresh={meas['input_thresh']}"
          f":linear=true,alimiter=limit={limit:.4f}:attack=5:release=50:level=disabled")
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(marked),
         "-af", af, "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-ar", "48000", "-ac", "2", "-movflags", "+faststart", str(final)])

    i, lra, pk = measure(final)
    d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "csv=p=0", str(final)],
                             capture_output=True, text=True).stdout.strip())
    print(f"\nFINAL  {d/60:.2f} min")
    print(f"  integrated {i:.1f} LUFS   {'PASS' if -15.0 <= i <= PROG_I + 0.1 else 'FAIL'}")
    print(f"  LRA        {lra:.1f} LU")
    print(f"  true peak  {pk:.1f} dBFS  {'PASS' if pk <= PROG_TP + 0.05 else 'FAIL'}")
    print(f"-> {final}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
