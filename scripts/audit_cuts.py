"""Measure where a short's cut points actually land, against the audio.

Nathan: "it could just be cut a little bit better... I don't know what it is, but
it could just be cut just a tad bit better."

That is a real defect and it has a measurable cause. Every cut point in the
pipeline comes from a TRANSCRIPT - YouTube's auto-caption word timings - and
those know nothing about breath, pause, or where a line lands. So a cut can sit
mid-word, or a beat late, or hold dead air.

This does not guess. For each cut it reports:
  * how far the IN point sits from the nearest measured speech onset - negative
    means it opens on silence (dead air), positive means it opens mid-speech
    (the first syllable is already gone, which is the one that sounds wrong)
  * how much silence trails the OUT point before the cut
  * whether the OUT lands mid-speech, which truncates a word

Run it on any rendered short with a .map.json beside it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boydclips import render                     # noqa: E402

OUTDIR = Path.home() / "OneDrive" / "Desktop" / "Boyd Clips" / "READY-TO-REVIEW"


def speech_edges(sil: list, t0: float, t1: float) -> list:
    """Turn silent spans into (speech_start, speech_end) pairs across [t0,t1]."""
    out, cur = [], t0
    for a, b in sil:
        if b < t0 or a > t1:
            continue
        if a > cur:
            out.append((cur, min(a, t1)))
        cur = max(cur, b)
    if cur < t1:
        out.append((cur, t1))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--short", required=True, help="mp4 in READY-TO-REVIEW")
    ap.add_argument("--noise-db", type=float, default=-32.0)
    ap.add_argument("--min-sil", type=float, default=0.18,
                    help="shorter than detect_silences' default: a breath is ~0.2s")
    args = ap.parse_args()

    mp = OUTDIR / args.short
    side = mp.with_suffix(".map.json")
    if not side.exists():
        print("no .map.json beside " + mp.name)
        return
    d = json.loads(side.read_text(encoding="utf-8"))
    sec = float(d.get("section_start_s") or 0.0)

    srcs = sorted((ROOT / "work" / d["video"]).glob(d["video"] + "_h_*.mp4"))
    if not srcs:
        print("no downloaded section for " + d["video"])
        return
    src = srcs[0]

    print(f"analysing {mp.name}  ({len(d['pieces'])} cuts)")
    print(f"  source {src.name}, section starts at {sec:.1f}s\n")
    sil = render.detect_silences(src, noise_db=args.noise_db, min_silence_s=args.min_sil)
    print(f"  {len(sil)} silent spans >= {args.min_sil}s at {args.noise_db}dB\n")

    def in_silence(t: float) -> tuple | None:
        for a, b in sil:
            if a <= t <= b:
                return (a, b)
        return None

    def next_speech(t: float) -> float | None:
        for a, b in sil:
            if b > t:
                return b if a <= t else None
        return None

    rows = []
    for i, p in enumerate(d["pieces"], 1):
        a = p["src_start"] - sec            # file time
        b = p["src_end"] - sec

        si = in_silence(a)
        if si:
            # opens on silence: how long until someone speaks
            lead = si[1] - a
            in_note = f"opens on {lead:+.2f}s of dead air"
            in_flag = "DEAD AIR" if lead > 0.35 else "ok"
        else:
            # opens mid-speech: how far past the onset
            onset = None
            for x, y in sil:
                if y <= a:
                    onset = y
            late = (a - onset) if onset is not None else None
            in_note = (f"opens {late:.2f}s INTO speech" if late is not None
                       else "opens mid-speech")
            in_flag = "CLIPPED" if (late is not None and late > 0.12) else "ok"

        so = in_silence(b)
        if so:
            tail = b - so[0]
            out_note = f"holds {tail:.2f}s after the last word"
            out_flag = "SAGS" if tail > 0.60 else ("TIGHT" if tail < 0.12 else "ok")
        else:
            out_note = "cuts while someone is still talking"
            out_flag = "MID-WORD"

        rows.append((i, p["src_start"], p["src_end"], in_flag, in_note, out_flag, out_note))

    print(f"{'#':>2}  {'in':>9}  {'IN':<9} {'':<32} {'OUT':<9} {''}")
    bad = 0
    for i, s0, s1, inf, inn, outf, outn in rows:
        if inf != "ok" or outf != "ok":
            bad += 1
        print(f"{i:>2}  {s0:>9.1f}  {inf:<9} {inn:<32} {outf:<9} {outn}")

    print(f"\n{bad} of {len(rows)} cuts have a measurable problem.")
    print("\nCLIPPED = the first syllable is already gone before the cut opens.")
    print("SAGS    = dead air before the next clip starts.")
    print("MID-WORD= the cut lands while someone is still speaking.")


if __name__ == "__main__":
    main()
