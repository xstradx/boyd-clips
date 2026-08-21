"""Ask the model the actual question: would Nathan post this hearing?

Nathan, 2026-08-21: "I don't understand why you haven't just promoted opus 5
yourself to find exactly what we're looking for".

Fair. Every previous pass decomposed his spec into features chosen here -
outcome, drama, defendant voice, specificity, receipts, question types - and had
the model fill in that schema. That is still this project deciding what matters
and using the model as a measuring instrument. He corrected the decomposition
four separate times, which is the signal that the decomposition was the problem.

So the criteria below are his own words, quoted, not a paraphrase. Paraphrasing
a spec is how it drifts into meaning something else.

Sends the body of the hearing plus its ending, and asks for one judgement.
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boydclips.llm import ClaudeCliBackend      # noqa: E402

IN = ROOT / "state" / "ranked_hearings.json"
OUT = ROOT / "state" / "judged_nathan.json"
MODEL = "claude-opus-5"
BODY_WORDS = 1100
TAIL_WORDS = 260

SYSTEM = """You are picking hearings for a YouTube channel that clips Judge
Stephanie Boyd's court. The channel owner described what he wants in his own
words. These are his criteria, quoted:

  "complete video would be the defendant comes in usually most times when
   there's a MTR defendant judge Boyd always kinda talks to them and if it's
   actually at least 6-7 min long that's a good video just something with drama
   and judge Boyd calling out people for their bs or asking them what actually
   happened and then the defendant talks to the judge"

  "people really like it when she's harsh"

  "it's dead serious but funny to us or like oh damn"

  "it's also when people have ridiculous excuses"

  "basically if judge Boyd and the defendant are actually talking about
   specifics you should look there"

  "she goes off on people and really calls people out and people give up their
   right to stay silent and they have to talk"

On one hearing he rejected, his reason was: "his lawyer asked he didn't talk".
So the DEFENDANT speaking for himself is essential. An attorney negotiating on
his behalf does not count, and both say "your honor" and "yes ma'am", so use
context rather than wording to tell them apart.

Judge each excerpt as a whole. Do not score sub-qualities; answer the question
he would ask: is this a video worth posting?

post: 1 to 5.
  5 - he would definitely post this
  3 - borderline
  1 - he would skip it

Be strict. Most hearings are procedural and deserve a 1 or 2. Reserve 4 and 5
for hearings that genuinely deliver what he described.

why: one sentence, concrete, naming what happens.
best_line: up to 20 words quoted verbatim from the text - the moment that would
sell the clip. Use "" if there isn't one. Never invent a line."""

SCHEMA = {
    "type": "object",
    "required": ["verdicts"],
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "post", "why", "best_line"],
                "properties": {
                    "id": {"type": "integer"},
                    "post": {"type": "integer"},
                    "why": {"type": "string"},
                    "best_line": {"type": "string"},
                },
            },
        }
    },
}


def excerpt(vid: str, a: float, b: float, cache: dict) -> str:
    if vid not in cache:
        p = glob.glob(str(ROOT / "work" / vid / "*.transcript.json"))
        cache[vid] = json.load(open(p[0], encoding="utf-8"))["words"] if p else []
    ws = cache[vid]
    seg = [x.get("w", "") for x in ws if a <= x.get("t", 0) <= b]
    txt = re.sub(r"\s+", " ", " ".join(seg)).strip()
    w = txt.split()
    if len(w) <= BODY_WORDS + TAIL_WORDS:
        return txt
    start = int(len(w) * 0.10)                       # skip announcements
    body = " ".join(w[start:start + BODY_WORDS])
    tail = " ".join(w[-TAIL_WORDS:])
    return body + " [...] " + tail


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--model", default=MODEL)
    args = ap.parse_args()

    rows = json.loads(IN.read_text(encoding="utf-8"))
    done = {}
    if OUT.exists():
        try:
            done = {d["key"]: d for d in json.loads(OUT.read_text(encoding="utf-8"))}
        except Exception:
            done = {}

    cache: dict[str, list] = {}
    todo = []
    for r in rows:
        key = "%s:%d" % (r["video_id"], int(r["t"]))
        if key in done:
            continue
        t = excerpt(r["video_id"], r["t"], r["t"] + r["span_s"], cache)
        if len(t.split()) < 200:
            continue
        todo.append((key, r, t))
    if args.limit:
        todo = todo[: args.limit]

    print(f"to judge: {len(todo)}   done already: {len(done)}")
    if not todo:
        print("nothing to do.")
        return
    w = sum(len(t.split()) for _, _, t in todo)
    print(f"words   : {w:,}   calls: {(len(todo)+args.batch-1)//args.batch}   model: {args.model}\n")

    be = ClaudeCliBackend(model=args.model, timeout_s=900)
    results = list(done.values())
    for i in range(0, len(todo), args.batch):
        chunk = todo[i:i + args.batch]
        user = "Judge each hearing.\n\n" + "\n\n".join(
            f"### id {n}\n{t}" for n, (_, _, t) in enumerate(chunk))
        try:
            data = be.complete(SYSTEM, user, SCHEMA, f"nathan-{i}")
        except Exception as e:                       # noqa: BLE001
            print(f"  batch {i} failed: {str(e)[:120]}")
            continue
        by = {v["id"]: v for v in data.get("verdicts", [])}
        for n, (key, r, _) in enumerate(chunk):
            v = by.get(n)
            if not v:
                continue
            results.append({"key": key, "video_id": r["video_id"], "date": r["date"],
                            "t": r["t"], "span_s": r["span_s"], "post": v["post"],
                            "why": v["why"][:220], "best_line": v["best_line"][:180]})
        OUT.write_text(json.dumps(results, indent=1), encoding="utf-8")
        print(f"  {min(i+args.batch, len(todo))}/{len(todo)}", flush=True)

    import collections
    print(f"\njudged: {len(results)}")
    print("post  :", dict(sorted(collections.Counter(r["post"] for r in results).items())))
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
