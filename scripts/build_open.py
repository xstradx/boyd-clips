"""Assemble the document-card opening as a real cut.

Card holds are NOT arbitrary. Each card holds for exactly as long as its beat of
narration takes at the pace measured off Audit the Court's narrator
(176.3 WPM -- see research/reference/competitor/VOICE_TARGET.md), plus the
measured inter-clause pause (300 ms) and a beat of air at the cut.

That means when the real VO lands, it drops straight onto these timings.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

WPM = 176.3          # measured, both reference videos agree
PAUSE = 0.30         # measured pause median between clauses
TAIL = 0.45          # air after the last word before the hard cut
LEAD_1 = 0.60        # the first card gets a beat before speech starts

# beat -> card. 1:1 with CARDS in doc_cards.py.
BEATS = [
    "On the night of March 25th, 2023, a man was struck and killed on South Alamo Street in San Antonio, Texas.",
    "Erik Michael Moody, thirty-six years old, was found on the sidewalk outside the Blue Star complex. The driver did not stop.",
    "Two days later, Robert Castillo, twenty-nine, surrendered to the Bexar County Sheriff's Office.",
    "He was booked on a charge of collision involving death, and released five days later on a one hundred thousand dollar corporate surety bond.",
    "Castillo had been arrested twice before, in 2011 and 2013, both times as a teenager. There was nothing in the decade before the crash.",
    "A grand jury indicted him on two felony counts: manslaughter, and failure to stop and render aid.",
    "His trial began on May 11th, 2026, in the 187th District Court, before Judge Stephanie Boyd. It ran eight days, and Castillo testified in his own defense.",
    "His attorneys argued mistake of fact, necessity, and duress. He said he was being shot at.",
    "On May 19th, the jury returned its verdict.",
]


def beat_duration(text: str, first: bool) -> float:
    words = len(text.split())
    speech = words / WPM * 60.0
    # one internal pause per sentence boundary after the first
    internal = (text.count(".") + text.count(":") - 1) * PAUSE
    return round(speech + max(internal, 0.0) + TAIL + (LEAD_1 if first else 0.0), 2)


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    cards = sorted((root / "out/review/castillo_cards").glob("card_*.png"))
    if len(cards) != len(BEATS):
        print(f"MISMATCH: {len(cards)} cards, {len(BEATS)} beats")
        return 1

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "out/review/castillo_open.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)

    durations = [beat_duration(b, i == 0) for i, b in enumerate(BEATS)]
    total = sum(durations)

    print(f"{'#':>2}  {'words':>5}  {'hold':>6}  beat")
    for i, (b, d) in enumerate(zip(BEATS, durations), 1):
        print(f"{i:>2}  {len(b.split()):>5}  {d:>5.2f}s  {b[:62]}...")
    print(f"\n{len(BEATS)} cards, {total:.2f}s total")
    print(f"(placeholder flat-9.1s version was 75.7s; Audit's measured opening is 51.7s)")

    concat = out.parent / "_open_concat.txt"
    lines = []
    for p, d in zip(cards, durations):
        lines.append(f"file '{p.as_posix()}'")
        lines.append(f"duration {d}")
    lines.append(f"file '{cards[-1].as_posix()}'")   # concat demuxer needs the last frame repeated
    concat.write_text("\n".join(lines), encoding="utf-8")

    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat),
        "-t", f"{total:.2f}",          # concat repeats the last frame; trim to the real length
        "-vf", "fps=30,format=yuv420p",
        "-c:v", "libx264", "-preset", "slow", "-crf", "18",
        "-movflags", "+faststart",
        str(out),
    ]
    print("\n$ " + " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        print(r.stderr[-2000:])
        return r.returncode

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration,size",
         "-of", "default=nw=1", str(out)], capture_output=True, text=True)
    print(probe.stdout.strip())
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
