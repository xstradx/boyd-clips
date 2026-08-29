"""One command: raw 2-up short -> tightened, deblocked, speaker-side captioned.

Nathan's goal, 2026-08-28: "we need to memorize this and get it right so you
could automate these shorts every day". So this takes an existing 2-up short and
runs the whole chain with no hand-tuning, and REFUSES rather than emitting
something broken.

    python scripts/make_short_auto.py --short READY-TO-POST/X_SHORT.mp4
        --transcript work/ID/ID.transcript.json --src-start 3931.8
        --out READY-TO-POST/X_SHORT_FINAL.mp4

THE FIVE THINGS THIS ENCODES, each of which was a measured bug:

1. DEAD AIR COMES FROM WORD GAPS, NEVER silencedetect. Measured on CARTHIEF at
   -30, -25, -20 AND -18 dBFS: zero spans every time. The courtroom room tone
   never drops that low, so the detector this repo used for every dead-air pass
   is blind here. The transcript showed 22 gaps over 0.7s totalling 31.2s of
   56.2s - 56% of the runtime.

2. THE SPEAKER SERIES IS COMPUTED ON THE UNCUT SHORT AND REMAPPED. Every cut is
   a hard scene change that spikes frame-difference, so a series computed on the
   cut video is corrupted at exactly the number of cuts.

3. ATTRIBUTION IS AUDIO-VISUAL CORRELATION, not raw motion. A talking mouth
   moves in time with the sound; a nodding head does not. 9/9 on hand-labelled
   windows against 4/9 for comparing movement. Judge Boyd is animated while
   LISTENING, which is exactly why raw movement handed her the defendant's lines.

4. CAPTION BLOCKS MUST NOT STRADDLE A SPEAKER TURN, or they cannot be placed on
   either half. Blocks end at every turn boundary.

5. -pix_fmt yuv420p IS FORCED. Four shorts silently shipped High 4:4:4
   Predictive, which no consumer hardware decoder plays.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable

# Deblock chain, chosen by measuring six candidates on this footage:
#   block-boundary ratio 1.099 -> 0.763, with detail UP from 1.55 to 2.37.
#   fftdnoiz made it WORSE (1.399). hqdn3d is weighted toward chroma because the
#   artefact is chroma-dominant - luma metrics miss it entirely, which is why it
#   went unnoticed until the thumbnails were measured in YCbCr.
DEBLOCK = ("deblock=filter=strong:block=8:alpha=0.14:beta=0.06:gamma=0.06:delta=0.06,"
           "hqdn3d=1.2:6:2:9,"
           "deband=1thr=0.015:2thr=0.015:3thr=0.015:range=20:blur=1,"
           "unsharp=5:5:0.6:3:3:0.0")


def run(cmd, label):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=5400)
    if p.returncode != 0:
        print(f"  FAILED at {label}")
        print("\n".join((p.stderr or p.stdout).strip().splitlines()[-10:]))
        return None
    return p.stdout


def probe(path, stream, field):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", stream,
         "-show_entries", f"stream={field}", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True).stdout.strip().splitlines()
    return out[0] if out else ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--short", required=True, type=Path)
    ap.add_argument("--transcript", required=True, type=Path)
    ap.add_argument("--src-start", type=float, required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--cap", type=int, default=156)
    ap.add_argument("--gap-min", type=float, default=0.70)
    ap.add_argument("--keep", type=float, default=0.22)
    ap.add_argument("--work", type=Path, default=None)
    a = ap.parse_args()

    name = a.short.stem
    wk = a.work or (a.out.parent / "_auto" / name)
    wk.mkdir(parents=True, exist_ok=True)
    tight = wk / "tight.mp4"
    clean = wk / "clean.mp4"
    tmap = wk / "timemap.json"
    ttr = wk / "tight.transcript.json"
    spk_full = wk / "speakers_full.json"
    spk = wk / "speakers.json"

    print(f"\n=== {name} ===")

    print("[1/5] speaker detection on the UNCUT short")
    if run([PY, str(ROOT / "scripts" / "who_speaks.py"),
            "--video", str(a.short), "--out", str(spk_full)], "who_speaks") is None:
        return 1

    print("[2/5] cutting dead air from word gaps")
    out = run([PY, str(ROOT / "scripts" / "tighten_short.py"),
               "--video", str(a.short), "--transcript", str(a.transcript),
               "--src-start", str(a.src_start), "--gap-min", str(a.gap_min),
               "--keep", str(a.keep), "--out", str(tight),
               "--map-out", str(tmap)], "tighten")
    if out is None:
        return 1
    for line in out.strip().splitlines():
        print("   " + line.strip())

    print("[3/5] deblocking")
    if run(["ffmpeg", "-v", "error", "-i", str(tight), "-vf", DEBLOCK,
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart",
            str(clean), "-y"], "deblock") is None:
        return 1

    print("[4/5] remapping transcript and speaker series onto the cut timeline")
    import numpy as np
    tm = json.load(open(tmap, encoding="utf-8"))
    tr = json.load(open(a.transcript, encoding="utf-8"))
    segs = tm["segments"]

    words = []
    for x in tr["words"]:
        t = x["t"] - a.src_start
        for s in segs:
            if s["old_start"] <= t <= s["old_end"]:
                words.append({"t": round(a.src_start + s["new_start"]
                                         + (t - s["old_start"]), 3), "w": x["w"]})
                break
    ttr.write_text(json.dumps({"video_id": name, "source": "remapped",
                               "words": words}), encoding="utf-8")

    sp = json.load(open(spk_full, encoding="utf-8"))
    fps = sp["fps"]
    top, bot = np.array(sp["top"]), np.array(sp["bottom"])
    env = np.array(sp.get("audio") or [])
    has_env = len(env) == len(top)
    T, B, E = [], [], []
    for s in segs:
        i0 = max(0, min(int(s["old_start"] * fps), len(top)))
        i1 = max(i0, min(int(s["old_end"] * fps), len(top)))
        T.extend(top[i0:i1])
        B.extend(bot[i0:i1])
        if has_env:
            E.extend(env[i0:i1])
    spk.write_text(json.dumps({"fps": fps, "top": list(map(float, T)),
                               "bottom": list(map(float, B)),
                               "audio": list(map(float, E))}), encoding="utf-8")
    print(f"   {len(words)} words, {len(T)} speaker samples ({len(T) / fps:.1f}s)")

    print("[5/5] captions on the speaking half")
    out = run([PY, str(ROOT / "scripts" / "caption_short.py"),
               "--video", str(clean), "--transcript", str(ttr),
               "--src-start", str(a.src_start), "--cap", str(a.cap),
               "--margin", "110", "--max-chars", "18", "--max-words", "4",
               "--speakers", str(spk), "--out", str(a.out)], "captions")
    if out is None:
        return 1
    for line in out.strip().splitlines():
        if any(k in line for k in ("turns", "split", "blocks")):
            print("   " + line.strip())

    # --- verify, and REFUSE rather than claim success -------------------
    print("\n   VERIFICATION")
    pf = probe(a.out, "v:0", "pix_fmt")
    vd = float(probe(a.out, "v:0", "duration") or 0)
    ad = float(probe(a.out, "a:0", "duration") or 0)
    w = int(probe(a.out, "v:0", "width") or 0)
    h = int(probe(a.out, "v:0", "height") or 0)
    gaps = [words[i]["t"] - words[i - 1]["t"] for i in range(1, len(words))]
    big = [g for g in gaps if g > a.gap_min]
    dec = subprocess.run(["ffmpeg", "-v", "error", "-i", str(a.out), "-f", "null", "-"],
                         capture_output=True, text=True)

    checks = [
        ("pix_fmt yuv420p", pf == "yuv420p", pf),
        ("1080x1920", (w, h) == (1080, 1920), f"{w}x{h}"),
        ("A/V in sync", abs(vd - ad) < 0.15, f"{vd:.2f}s / {ad:.2f}s"),
        (f"no word-gap over {a.gap_min}s", not big,
         f"{len(big)} remain, longest {max(gaps):.2f}s" if gaps else "n/a"),
        ("decodes clean", dec.returncode == 0 and not dec.stderr.strip(),
         (dec.stderr.strip().splitlines() or ["clean"])[0][:60]),
    ]
    ok = True
    for label, good, detail in checks:
        print(f"     {'PASS' if good else 'FAIL'}  {label:28} {detail}")
        ok &= bool(good)
    print("\n   " + (f"-> {a.out}" if ok else "REFUSED: a check failed above"))
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
