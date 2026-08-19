"""Rebuild the subtitle track against the current cut.

The previous SRT was authored against a 28:50 timeline. Re-cutting every scene
to avoid the courtroom mutes moved every boundary, so patching it was never an
option — it has to be regenerated from the source transcripts through the same
mapping the picture went through.

Two corrections are applied on the way:

  * VICTIM'S NAME. Whisper heard "Eric Moody" four times and "Derek Moody"
    twice. Spoken audio cannot distinguish Erik from Eric, so the transcript
    carries no spelling information at all; every WRITTEN source we hold — the
    dossier, the document cards, the KSAT report — says **Erik Moody**. "Derek"
    is simply a mis-hearing. Publishing a film about a man's death that misnames
    him, in two different wrong ways, is the kind of error that is invisible to
    us and unmissable to his family.

  * PROFANITY. Censored in TEXT ONLY, per the channel rule: the audio ships as
    the courtroom record, the caption reads f***ing.

Usage:  python scripts/build_srt.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from censor import censor  # noqa: E402

LONG = ROOT / "out/review/castillo_long"
SRC = ROOT / "out/source"
FINAL_DIR = ROOT / "out/review/_final"
OUT = ROOT / "out/review/castillo_FINAL.srt"

# spoken -> written. Applied word-boundary, case-insensitively.
NAME_FIXES = [
    # Whisper's actual mis-hearings, enumerated from src_transcripts.json rather
    # than guessed: "eric moody" x6, "eric michael" x4, "derek movie" x1.
    (r"\bderek\s+movie\b", "Erik Moody"),
    (r"\bderrick\s+movie\b", "Erik Moody"),
    (r"\b(derek|derrick|eric|erick)\s+moody\b", "Erik Moody"),
    (r"\b(derek|derrick|eric|erick)\s+michael\b", "Erik Michael"),
    (r"\bmr\.?\s+(derek|derrick)\b", "Mr. Erik"),
]

MAX_CHARS = 84          # two lines at ~42
MIN_DUR = 1.0
MAX_DUR = 7.0


def dur(p: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(p)], capture_output=True, text=True).stdout
    try:
        return float(out.strip().splitlines()[0])
    except Exception:
        return 0.0


def ts(t: float) -> str:
    if t < 0:
        t = 0.0
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):06.3f}".replace(".", ",")


def fix_names(s: str) -> str:
    for pat, rep in NAME_FIXES:
        s = re.sub(pat, rep, s, flags=re.I)
    return s


def main() -> int:
    cuts = json.loads((LONG / "live_cuts.json").read_text(encoding="utf-8"))
    trans = json.loads((SRC / "src_transcripts.json").read_text(encoding="utf-8"))

    head = dur(FINAL_DIR / "00_sting.mp4") + dur(FINAL_DIR / "01_opening.mp4")
    # The news beat sits between the cold open (scene_01) and Act 1 proper, so
    # every cue from scene_02 onward is pushed back by its duration.
    NEWS = LONG / "scene_01b.mp4"
    news_d = dur(NEWS) if NEWS.exists() else 0.0
    print(f"head offset (sting + card opening): {head:.2f}s")

    cues: list[tuple[float, float, str]] = []
    body_t = 0.0
    for entry in sorted(cuts, key=lambda c: c["n"]):
        segs = entry["segs"]
        tsegs = trans.get(entry["src"]) or []
        if entry["n"] >= 2 and news_d and not getattr(main, "_shifted", False):
            body_t += news_d
            main._shifted = True
        for (a, b) in segs:
            for seg in tsegs:
                s, e = float(seg["s"]), float(seg["e"])
                if s < a or e > b:
                    continue
                text = str(seg.get("t") or seg.get("w") or "").strip()
                if not text:
                    continue
                start = head + body_t + (s - a)
                end = head + body_t + (e - a)
                cues.append((start, end, text))
            body_t += (b - a)

    print(f"{len(cues)} raw cues from {len(cuts)} scenes")

    # merge fragments, split over-long lines, clamp durations
    merged: list[list] = []
    for st, en, tx in sorted(cues):
        if merged and st - merged[-1][1] < 0.35 and len(merged[-1][2]) + len(tx) < MAX_CHARS:
            merged[-1][1] = en
            merged[-1][2] = f"{merged[-1][2]} {tx}".strip()
        else:
            merged.append([st, en, tx])

    renamed = 0
    lines = []
    for i, (st, en, tx) in enumerate(merged, 1):
        before = tx
        tx = fix_names(tx)
        if tx != before:
            renamed += 1
        tx = censor(tx)
        if en - st < MIN_DUR:
            en = st + MIN_DUR
        if en - st > MAX_DUR:
            en = st + MAX_DUR
        if len(tx) > 42:
            words = tx.split()
            half = len(words) // 2
            tx = " ".join(words[:half]) + "\n" + " ".join(words[half:])
        lines.append(f"{i}\n{ts(st)} --> {ts(en)}\n{tx}\n")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(merged)} cues written, {renamed} name corrections applied")
    print(f"first cue at {merged[0][0]:.1f}s, last ends {merged[-1][1]:.1f}s")
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
