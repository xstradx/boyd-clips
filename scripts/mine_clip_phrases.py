"""Learn Boyd's tells from the clips someone already chose to publish.

Nathan, 2026-08-20: she says "here's the thing" and "and let me tell you" -
go through the rival's viral clips and find more of them rather than guessing.

The phrase list in find_wentthere.py was hand-written, which only ever finds
phrasings already thought of. This derives it instead. state/clip_alignment.json
maps 139 of the rival's clips onto spans inside our own dockets, so every docket
splits into two piles of the same judge in the same courtroom:

    CLIPPED    speech inside a span someone published
    PASSED     speech in the same docket that nobody used

Scoring is lift - how much more often a phrase appears in the clipped pile than
the passed one - not raw frequency. Frequency mining was tried before and
returned "the court will find there is sufficient evidence", because boilerplate
repeats everywhere. With a contrast set it appears on both sides and cancels.

Free: local counting, no model calls.
"""

from __future__ import annotations

import collections
import glob
import json
import math
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALIGN = ROOT / "state" / "clip_alignment.json"
OUT = ROOT / "state" / "clip_phrases.json"

DEFER = re.compile(r"\byour honou?r\b|\b(yes|no),?\s+(ma'?am|sir)\b", re.I)
MIN_N, MAX_N = 2, 5
MIN_CLIPPED = 6          # a phrase must actually recur before lift means anything


def turns(words):
    cur, buf, out = None, [], []
    for it in words:
        w = it.get("w", "")
        if w.strip().startswith(">>"):
            if buf:
                out.append((cur, " ".join(buf)))
            buf, cur = [], it.get("t", 0.0)
            w = w.strip()[2:]
        if cur is None:
            cur = it.get("t", 0.0)
        if w.strip():
            buf.append(w.strip())
    if buf:
        out.append((cur, " ".join(buf)))
    return out


def norm(text: str) -> list[str]:
    text = re.sub(r"[^A-Za-z' ]", " ", text.lower())
    return [w for w in text.split() if w]


def grams(tokens):
    for n in range(MIN_N, MAX_N + 1):
        for i in range(len(tokens) - n + 1):
            yield " ".join(tokens[i:i + n])


def main() -> None:
    if not ALIGN.exists():
        print("run scripts/align_clips.py first")
        return
    align = json.loads(ALIGN.read_text(encoding="utf-8"))
    spans = collections.defaultdict(list)
    for cid, v in align.items():
        spans[v["video_id"]].append((v["start_s"], v["end_s"]))

    clipped = collections.Counter()
    passed = collections.Counter()
    c_turns = p_turns = 0

    for vid, ranges in spans.items():
        hits = glob.glob(str(ROOT / "work" / vid / f"{vid}.transcript.json"))
        if not hits:
            continue
        ws = json.loads(Path(hits[0]).read_text(encoding="utf-8")).get("words") or []
        for t, txt in turns(ws):
            if len(txt.split()) < 25:
                continue                       # too short to be her talking
            if DEFER.search(txt):
                continue                       # someone else's words in here
            inside = any(a <= t <= b for a, b in ranges)
            toks = norm(txt)
            bag = clipped if inside else passed
            for g in set(grams(toks)):         # presence per turn, not raw count
                bag[g] += 1
            if inside:
                c_turns += 1
            else:
                p_turns += 1

    print(f"dockets with an aligned clip : {len(spans)}")
    print(f"turns inside a clipped span  : {c_turns}")
    print(f"turns nobody clipped         : {p_turns}\n")
    if not c_turns or not p_turns:
        print("not enough on one side to compare")
        return

    rows = []
    for g, c in clipped.items():
        if c < MIN_CLIPPED:
            continue
        p = passed.get(g, 0)
        rate_c = c / c_turns
        rate_p = (p + 0.5) / p_turns          # smoothed, so unseen is not infinite
        rows.append({"phrase": g, "clipped": c, "passed": p,
                     "lift": round(rate_c / rate_p, 2),
                     "per100_clipped": round(rate_c * 100, 2)})
    rows.sort(key=lambda r: (-r["lift"], -r["clipped"]))
    OUT.write_text(json.dumps(rows[:400], indent=1), encoding="utf-8")

    known = ["here's the thing", "let me tell you", "guess what", "you know what",
             "let me ask you", "do you know how many", "i always tell"]
    print("=" * 66)
    print("PHRASES OVER-REPRESENTED IN CLIPS SOMEONE PUBLISHED")
    print("=" * 66)
    print(f"  {'lift':>5}  {'in':>4} {'out':>5}  phrase")
    for r in rows[:34]:
        print(f"  {r['lift']:5.2f}  {r['clipped']:4d} {r['passed']:5d}  {r['phrase']}")

    print("\n" + "=" * 66)
    print("HOW THE HAND-WRITTEN ONES ACTUALLY SCORE")
    print("=" * 66)
    idx = {r["phrase"]: r for r in rows}
    for k in known:
        r = idx.get(k)
        if r:
            print(f"  {r['lift']:5.2f}  {r['clipped']:4d} {r['passed']:5d}  {k}")
        else:
            c, p = clipped.get(k, 0), passed.get(k, 0)
            print(f"      -  {c:4d} {p:5d}  {k}   (below the {MIN_CLIPPED} threshold)")

    print(f"\n-> {OUT}")


if __name__ == "__main__":
    main()
