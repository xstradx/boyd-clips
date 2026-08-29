"""Recover how a finished cut was assembled, by matching its WORDS to the source.

Nathan edited a short himself in CapCut and asked for notes on how he did it.
His decisions are the only ground truth for taste in this project, so they are
worth recovering exactly.

The first attempt matched loudness envelopes and produced garbage - 26 identical
1.8-second "takes" scattered incoherently through the hearing. Courtroom audio is
too self-similar for envelope correlation: one stretch of measured speech looks
like any other, so every window found a confident false peak.

Text does not have that problem. Two transcripts are compared instead:
  * the EDIT, transcribed by Whisper large-v3 (accurate)
  * the SOURCE, from YouTube auto-captions (inaccurate, but word-timed)
They disagree on spelling and punctuation, so matching is fuzzy - a sliding
window scored by difflib on normalised word sequences. Wrong words in the source
transcript hurt the score but do not move the position.
"""

from __future__ import annotations

import argparse
import difflib
import glob
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def load_source(video: str) -> list:
    f = glob.glob(str(ROOT / "work" / video / "*.transcript.json"))
    if not f:
        raise SystemExit("no source transcript for " + video)
    ws = json.loads(Path(f[0]).read_text(encoding="utf-8"))["words"]
    out = []
    for w in ws:
        t = norm(w.get("w", ""))
        if t:
            out.append((float(w.get("t", 0.0)), t))
    return out


def best_match(needle: list, src: list, lo: float, hi: float) -> tuple:
    """Slide `needle` (list of words) over the source and score with difflib."""
    n = len(needle)
    if n < 2:
        return (-1.0, 0.0)
    target = " ".join(needle)
    best, best_t = 0.0, -1.0
    sm = difflib.SequenceMatcher(autojunk=False)
    sm.set_seq2(target)
    step = max(1, n // 4)
    for i in range(0, max(1, len(src) - n), step):
        t0 = src[i][0]
        if t0 < lo or t0 > hi:
            continue
        cand = " ".join(w for _, w in src[i:i + n])
        sm.set_seq1(cand)
        if sm.real_quick_ratio() < best or sm.quick_ratio() < best:
            continue
        r = sm.ratio()
        if r > best:
            best, best_t = r, t0
    return best, best_t


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcript", required=True, help="the EDIT's whisper json")
    ap.add_argument("--video", required=True, help="source video id")
    ap.add_argument("--lo", type=float, default=0.0, help="earliest source second to search")
    ap.add_argument("--hi", type=float, default=1e9)
    ap.add_argument("--min-score", type=float, default=0.55)
    args = ap.parse_args()

    edit = json.loads(Path(args.transcript).read_text(encoding="utf-8"))
    src = load_source(args.video)
    print(f"edit: {len(edit)} lines   source: {len(src)} words "
          f"({src[0][0]:.0f}-{src[-1][0]:.0f}s)\n")

    rows = []
    for i, sg in enumerate(edit):
        words = [norm(w["w"]) for w in (sg.get("words") or []) if norm(w["w"])]
        score, t = best_match(words, src, args.lo, args.hi)
        rows.append({"i": i, "edit_a": sg["a"], "edit_b": sg["b"], "src": t,
                     "score": score, "who": sg.get("who"), "text": sg["text"]})

    ok = [r for r in rows if r["score"] >= args.min_score and r["src"] >= 0]
    print(f"{len(ok)}/{len(rows)} lines located in the source "
          f"(score >= {args.min_score})\n")

    print(f"{'edit':>7}  {'source':>8}  {'sc':>4}  who  line")
    for r in rows:
        loc = f"{r['src']:.0f}" if r["score"] >= args.min_score else "  ?"
        who = "BOYD" if r["who"] == "B" else "DEF "
        print(f"{r['edit_a']:>7.1f}  {loc:>8}  {r['score']:>4.2f}  {who} {r['text'][:52]}")

    # group consecutive located lines that also advance in the source
    takes, cur = [], None
    for r in ok:
        if cur and 0 <= r["src"] - cur["src_end"] < 12:
            cur["src_end"] = r["src"]
            cur["edit_end"] = r["edit_b"]
            cur["lines"] += 1
        else:
            if cur:
                takes.append(cur)
            cur = {"edit_a": r["edit_a"], "edit_end": r["edit_b"],
                   "src": r["src"], "src_end": r["src"], "lines": 1}
    if cur:
        takes.append(cur)

    print(f"\n{len(takes)} takes\n")
    print(f"{'#':>2} {'in edit':>13} {'len':>6}  {'from source':>15}  order")
    prev = None
    for k, t in enumerate(takes, 1):
        ln = t["edit_end"] - t["edit_a"]
        flag = ""
        if prev is not None and t["src"] < prev - 5:
            flag = "REORDERED (earlier material moved later)"
        prev = t["src"]
        print(f"{k:>2} {t['edit_a']:>6.1f}-{t['edit_end']:<6.1f} {ln:>6.1f}s  "
              f"{t['src']:>7.0f}s        {flag}")

    if takes:
        lens = [t["edit_end"] - t["edit_a"] for t in takes]
        print(f"\ntake length: shortest {min(lens):.1f}s  longest {max(lens):.1f}s  "
              f"median {sorted(lens)[len(lens)//2]:.1f}s")


if __name__ == "__main__":
    main()
