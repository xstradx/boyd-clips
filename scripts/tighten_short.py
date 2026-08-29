"""Remove dead air from a short using WORD GAPS, not silencedetect.

Nathan, 2026-08-28: "theres some silence in the clip but you could already see
what they were gonna say ... make sure theres no dead space causing people to
know what its gonna say 3-4 sec before it does".

WHY silencedetect CANNOT be used here, measured on CARTHIEF_SHORT.mp4:

    -30dB / 0.4s  ->  0 spans
    -25dB / 0.4s  ->  0 spans
    -20dB / 0.4s  ->  0 spans
    -18dB / 0.4s  ->  0 spans

Zero. The courtroom's room tone, HVAC and mic hiss never drop below -18dBFS, so
the detector this repo has used for every dead-air pass is completely blind on
this material. Meanwhile the word-level transcript shows **22 gaps over 0.7s
totalling 31.2s of a 56.2s short - 56% of the runtime**, including a 4.20s hole
after "far?" and a 3.68s hole after "hour?". Those are exactly the 3-4 second
dead spots Nathan noticed.

So the gaps are found from the transcript's word timings instead, which is the
only signal on this footage that actually sees them.

Each gap is closed to `keep` seconds rather than to zero: speech has attack and
decay that no detector counts as sound, and cutting flush clips the consonant
off the front of the next word and reads as broken rather than tight.
"""
from __future__ import annotations
import argparse, json, subprocess
from pathlib import Path


def keep_segments(words, dur, gap_min, keep, pad_end):
    segs, cur = [], [0.0, None]
    for i in range(1, len(words)):
        g = words[i][0] - words[i - 1][0]
        if g > gap_min:
            cur[1] = min(dur, words[i - 1][0] + keep)
            if cur[1] > cur[0]:
                segs.append(tuple(cur))
            cur = [max(0.0, words[i][0] - keep), None]
    cur[1] = min(dur, words[-1][0] + pad_end)
    if cur[1] > cur[0]:
        segs.append(tuple(cur))
    return segs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True, type=Path)
    ap.add_argument("--transcript", required=True, type=Path)
    ap.add_argument("--src-start", type=float, required=True)
    ap.add_argument("--gap-min", type=float, default=0.70,
                    help="a gap longer than this is dead air")
    ap.add_argument("--keep", type=float, default=0.22,
                    help="seconds of the gap left at each edge")
    ap.add_argument("--pad-end", type=float, default=0.80)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--map-out", default=None, type=Path,
                    help="write the old->new time map for re-captioning")
    a = ap.parse_args()

    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(a.video)],
        capture_output=True, text=True).stdout.strip())

    tr = json.load(open(a.transcript, encoding="utf-8"))
    words = [(x["t"] - a.src_start, x["w"]) for x in tr["words"]
             if a.src_start - 0.2 <= x["t"] <= a.src_start + dur]
    if len(words) < 5:
        print("not enough words in range")
        return 1

    segs = keep_segments(words, dur, a.gap_min, a.keep, a.pad_end)
    kept = sum(b - x for x, b in segs)
    print(f"  {len(words)} words, {len(segs)} keep-segments")
    print(f"  {dur:.1f}s -> {kept:.1f}s  (-{dur - kept:.1f}s, "
          f"{(dur - kept) / dur * 100:.0f}% removed) across {len(segs) - 1} cuts")

    parts = []
    for i, (s0, s1) in enumerate(segs):
        parts.append(f"[0:v]trim=start={s0:.3f}:end={s1:.3f},setpts=PTS-STARTPTS[v{i}]")
        parts.append(f"[0:a]atrim=start={s0:.3f}:end={s1:.3f},asetpts=PTS-STARTPTS[a{i}]")
    cat = "".join(f"[v{i}][a{i}]" for i in range(len(segs)))
    parts.append(f"{cat}concat=n={len(segs)}:v=1:a=1[v][a]")
    fg = ";".join(parts)

    a.out.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(a.video), "-filter_complex", fg,
         "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium",
         "-crf", "19", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
         "-movflags", "+faststart", str(a.out), "-y"],
        capture_output=True, text=True, timeout=3600)
    if p.returncode != 0:
        print("\n".join(p.stderr.strip().splitlines()[-8:]))
        return 1

    if a.map_out:
        # old time -> new time, so captions can be regenerated on the cut
        # timeline instead of drifting out of sync with it.
        remap, acc = [], 0.0
        for s0, s1 in segs:
            remap.append({"old_start": s0, "old_end": s1, "new_start": acc})
            acc += s1 - s0
        a.map_out.write_text(json.dumps(
            {"src_start": a.src_start, "segments": remap,
             "new_duration": acc}, indent=1), encoding="utf-8")
        print(f"  time map -> {a.map_out}")
    print(f"  -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
