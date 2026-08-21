"""Find hearings where the DEFENDANT explains himself - not his attorney.

Nathan, 2026-08-21, on the five-year cut: "his lawyer asked he didn't talk, have
opus look for dialogue of the defendants trying to explain themselves".

That exposes a fault running through every measurement made so far. The
"defendant talks" metric keys on "your honor" and "yes ma'am", which is exactly
how an ATTORNEY speaks. So the share being scored was largely counsel, and a
hearing could look like a conversation while the defendant said almost nothing.

No regex separates the two: both defer to the bench, both use first person. It
is a contextual judgement, so it goes to the model.

What is wanted, in his words from earlier: "people give up their right to stay
silent and they have to talk" - the defendant explaining, justifying, arguing
back, digging in. Not agreeing, not answering yes/no.

Unlike the outcome pass, this needs the middle of the hearing rather than the
ending, so a condensed sample of the exchange is sent.
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
OUT = ROOT / "state" / "defendant_voice.json"
MODEL = "claude-opus-5"
SAMPLE_WORDS = 900

SYSTEM = """You read an excerpt from a criminal hearing before Judge Boyd and
judge ONE thing: how much the DEFENDANT personally speaks for himself.

The defendant is the person the case is against. He is NOT his attorney.
Attorneys announce themselves for the record, say "my client", speak in legal
register, and negotiate. Both attorney and defendant say "your honor" and
"yes ma'am", so wording alone will not separate them - use context.

defendant_voice, 1 to 5:
  5 - the defendant speaks at length, explaining, justifying or arguing back,
      giving his own account of what happened
  4 - he explains himself several times, more than short answers
  3 - he speaks a few real sentences beyond yes/no
  2 - almost entirely yes ma'am / no ma'am
  1 - he says essentially nothing; the attorney does the talking

explains is true only when he actually offers a reason, an excuse or his own
version of events - not when he merely agrees or accepts.

quote: up to 15 words of the defendant's own speech, verbatim from the text, or
"" if he never speaks. Do not invent one."""

SCHEMA = {
    "type": "object",
    "required": ["verdicts"],
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "defendant_voice", "explains", "quote"],
                "properties": {
                    "id": {"type": "integer"},
                    "defendant_voice": {"type": "integer"},
                    "explains": {"type": "boolean"},
                    "quote": {"type": "string"},
                },
            },
        }
    },
}


def sample(vid: str, a: float, b: float, cache: dict) -> str:
    """Condensed middle of the hearing, where the exchange happens."""
    if vid not in cache:
        p = glob.glob(str(ROOT / "work" / vid / "*.transcript.json"))
        cache[vid] = json.load(open(p[0], encoding="utf-8"))["words"] if p else []
    ws = cache[vid]
    seg = [x.get("w", "") for x in ws if a <= x.get("t", 0) <= b]
    txt = re.sub(r"\s+", " ", " ".join(seg)).strip()
    words = txt.split()
    if len(words) <= SAMPLE_WORDS:
        return txt
    # skip the opening formalities, keep the body
    start = int(len(words) * 0.12)
    return " ".join(words[start:start + SAMPLE_WORDS])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=6)
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
        t = sample(r["video_id"], r["t"], r["t"] + r["span_s"], cache)
        if len(t.split()) < 150:
            continue
        todo.append((key, r, t))
    if args.limit:
        todo = todo[: args.limit]

    print(f"to judge: {len(todo)}   already done: {len(done)}")
    if not todo:
        print("nothing to do.")
        return
    w = sum(len(t.split()) for _, _, t in todo)
    print(f"words   : {w:,}  ({(len(todo)+args.batch-1)//args.batch} calls, {args.model})\n")

    be = ClaudeCliBackend(model=args.model, timeout_s=900)
    results = list(done.values())
    for i in range(0, len(todo), args.batch):
        chunk = todo[i:i + args.batch]
        user = "Judge each excerpt.\n\n" + "\n\n".join(
            f"### id {n}\n{t}" for n, (_, _, t) in enumerate(chunk))
        try:
            data = be.complete(SYSTEM, user, SCHEMA, f"voice-{i}")
        except Exception as e:                      # noqa: BLE001
            print(f"  batch {i} failed: {str(e)[:120]}")
            continue
        by = {v["id"]: v for v in data.get("verdicts", [])}
        for n, (key, r, _) in enumerate(chunk):
            v = by.get(n)
            if not v:
                continue
            results.append({"key": key, "video_id": r["video_id"], "date": r["date"],
                            "t": r["t"], "span_s": r["span_s"],
                            "defendant_voice": v["defendant_voice"],
                            "explains": v["explains"], "quote": v["quote"][:160]})
        OUT.write_text(json.dumps(results, indent=1), encoding="utf-8")
        print(f"  {min(i+args.batch, len(todo))}/{len(todo)}", flush=True)

    import collections
    print(f"\njudged: {len(results)}")
    print("voice :", dict(sorted(collections.Counter(r["defendant_voice"] for r in results).items())))
    print("explains:", sum(1 for r in results if r["explains"]))
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
