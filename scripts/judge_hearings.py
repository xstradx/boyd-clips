"""Have a model read each hearing's ending and say what actually happened.

Five lexical detectors were built for this and all five failed: harshness,
specificity, receipts, question types, the off-the-record marker. Each either
reversed on held-out data or fell over on inspection - the last one scored a
hearing "harsh" because the word *sentencing* appeared in a sentence postponing
it. Word matching cannot tell an outcome from a warning, because she talks about
prison constantly while warning people.

A model can. Nathan authorised roughly 5% of usage for this, so it is kept
deliberately cheap:

  * only the closing stretch is sent - the ending decides the outcome, and it is
    about 250 words against 2,500 for a whole hearing
  * hearings are batched per call
  * it runs on Haiku, not Opus. This is classification, not judgement.

Reuses ClaudeCliBackend, so it goes through the existing Claude Code login and
there is no separate bill.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boydclips.llm import ClaudeCliBackend      # noqa: E402

IN = ROOT / "state" / "ranked_hearings.json"
OUT = ROOT / "state" / "judged_hearings.json"
TAIL_S = 110.0
MODEL = "claude-haiku-4-5-20251001"

SYSTEM = """You classify the ENDING of a criminal court hearing before Judge Boyd.

For each item you are given the closing stretch of one hearing. Decide what
actually happened to the defendant, and how much drama the exchange carries.

outcome must be exactly one of:
  jail        - taken into custody, remanded, sentenced to confinement now
  revoked     - probation revoked or guilt adjudicated
  punished    - a real sanction short of jail (added conditions, fines, programs)
  chance      - given another chance, continued, reinstated, praised
  reset       - postponed, recalled, continued to a later date, nothing decided
  unclear     - cannot tell from this text

drama is 1 to 5:
  5 - she is blunt or cutting and a hard consequence lands
  3 - real back and forth, moderate stakes
  1 - routine, procedural, warm, or nothing happens

Judge only what the text shows. Do not infer beyond it."""

SCHEMA = {
    "type": "object",
    "required": ["verdicts"],
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "outcome", "drama", "why"],
                "properties": {
                    "id": {"type": "integer"},
                    "outcome": {"type": "string"},
                    "drama": {"type": "integer"},
                    "why": {"type": "string"},
                },
            },
        }
    },
}


def tail_text(vid: str, start: float, end: float, cache: dict) -> str:
    if vid not in cache:
        p = glob.glob(str(ROOT / "work" / vid / "*.transcript.json"))
        cache[vid] = json.load(open(p[0], encoding="utf-8"))["words"] if p else []
    ws = cache[vid]
    seg = [x.get("w", "") for x in ws if end - TAIL_S <= x.get("t", 0) <= end]
    return re.sub(r"\s+", " ", " ".join(seg)).strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=20)
    ap.add_argument("--limit", type=int, default=0, help="stop after N hearings")
    ap.add_argument("--model", default=MODEL, help="override the model")
    ap.add_argument("--out", default=str(OUT), help="write verdicts here")
    args = ap.parse_args()

    rows = json.loads(IN.read_text(encoding="utf-8"))
    outfile = Path(args.out)
    done = {}
    if outfile.exists():
        try:
            done = {d["key"]: d for d in json.loads(outfile.read_text(encoding="utf-8"))}
        except Exception:
            done = {}

    cache: dict[str, list] = {}
    todo = []
    for r in rows:
        key = "%s:%d" % (r["video_id"], int(r["t"]))
        if key in done:
            continue
        t = tail_text(r["video_id"], r["t"], r["t"] + r["span_s"], cache)
        if len(t.split()) < 40:
            continue
        todo.append((key, r, t))
    if args.limit:
        todo = todo[: args.limit]

    print(f"hearings to judge : {len(todo)}   already done: {len(done)}")
    if not todo:
        print("nothing to do.")
        return
    words = sum(len(t.split()) for _, _, t in todo)
    print(f"words to send     : {words:,}  (~{words//args.batch:,} per call, "
          f"{(len(todo)+args.batch-1)//args.batch} calls, model {MODEL})\n")

    be = ClaudeCliBackend(model=args.model, timeout_s=900)
    results = list(done.values())
    for i in range(0, len(todo), args.batch):
        chunk = todo[i:i + args.batch]
        parts = []
        for n, (_, r, t) in enumerate(chunk):
            parts.append(f"### id {n}\n{t[:1400]}")
        user = ("Classify the ending of each hearing below.\n\n"
                + "\n\n".join(parts))
        try:
            data = be.complete(SYSTEM, user, SCHEMA, f"judge-{i}")
        except Exception as e:                     # noqa: BLE001
            print(f"  batch {i} failed: {str(e)[:140]}")
            continue
        by = {v["id"]: v for v in data.get("verdicts", [])}
        for n, (key, r, t) in enumerate(chunk):
            v = by.get(n)
            if not v:
                continue
            results.append({"key": key, "video_id": r["video_id"], "date": r["date"],
                            "t": r["t"], "span_s": r["span_s"],
                            "outcome": v["outcome"], "drama": v["drama"],
                            "why": v["why"][:200]})
        outfile.write_text(json.dumps(results, indent=1), encoding="utf-8")
        print(f"  judged {min(i+args.batch, len(todo))}/{len(todo)}", flush=True)

    import collections
    print(f"\ntotal judged: {len(results)}")
    print("outcomes:", dict(collections.Counter(r["outcome"] for r in results)))
    print("drama   :", dict(sorted(collections.Counter(r["drama"] for r in results).items())))
    print(f"-> {outfile}")


if __name__ == "__main__":
    main()
