"""Rank hearings by whether she and the defendant get into SPECIFICS.

Nathan, 2026-08-21: "basically if judge Boyd and the defendant are actually
talking about specifics you should look there".

That is a better signal than the two tried before it, and it is testable.
Harshness failed on its first pick - it scored language found anywhere in the
hearing, but she says "prison" and "revoke" constantly while warning people, so
that is her register rather than an outcome. Specificity is different: it needs
BOTH sides producing concrete detail, which procedural talk never does.

What specifics look like in a transcript:
  she asks   - how many, how much, how long, what time, where were you, who was
  he answers - numbers, money, dates, durations, place and job detail

Two boundary faults are fixed here as well, both visible in earlier output:

  * The previous cut ran from one "court is calling" to the NEXT one, so it
    carried the following case's opening - "Dorian Murphrey, if you'll come up"
    was inside a finished file. It now stops before the next call.
  * The outcome was scored across the whole hearing rather than at the end. It
    is now read from the closing stretch only.
"""

from __future__ import annotations

import glob
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IN = ROOT / "state" / "called_hearings.json"
OUT = ROOT / "state" / "ranked_hearings.json"

TAIL_S = 75.0          # the closing stretch that decides the outcome
BACKOFF_S = 12.0       # stop this far before the next case is called

ASK = re.compile(r"\bhow many\b|\bhow much\b|\bhow long\b|\bwhat time\b|"
                 r"\bwhere were you\b|\bwho (was|were)\b|\bwhen did you\b|"
                 r"\bwhat happened\b|\bwhat did you\b|\bwhy did you\b|"
                 r"\bwhere did you\b|\bwhat kind of\b", re.I)
NUM = re.compile(r"\b\d{1,4}\b|\bone\b|\btwo\b|\bthree\b|\bfour\b|\bfive\b|"
                 r"\bsix\b|\bseven\b|\beight\b|\bnine\b|\bten\b|\btwenty\b|\bthirty\b", re.I)
CONCRETE = re.compile(r"\bdollars?\b|\bmonths?\b|\bweeks?\b|\bdays?\b|\byears?\b|"
                      r"\bhours?\b|\bo'?clock\b|\bjob\b|\bwork(ing|ed)?\b|"
                      r"\brent\b|\bapartment\b|\bhouse\b|\bcar\b|\bschool\b|"
                      r"\bhospital\b|\bmoney\b|\bpaid\b|\bphone\b", re.I)
DEFER = re.compile(r"\byour honou?r\b|\b(yes|no),?\s+(ma'?am|sir)\b", re.I)
HARSH_END = re.compile(r"take (?:him|her|them) into custody|place the handcuffs|"
                       r"remand|sentence you to|penitentiary|revoke your probation|"
                       r"going to prison|state jail|adjudicate you guilty|"
                       r"find you guilty|i'?m revoking", re.I)
SOFT_END = re.compile(r"give you (?:a|another) chance|continue you on|reinstate|"
                      r"good luck to you|god bless|recall you|reset form|"
                      r"appear by zoom|proud of you", re.I)


def main() -> None:
    rows = json.loads(IN.read_text(encoding="utf-8"))
    cache: dict[str, list] = {}

    def words(vid):
        if vid not in cache:
            p = glob.glob(str(ROOT / "work" / vid / "*.transcript.json"))
            cache[vid] = json.load(open(p[0], encoding="utf-8"))["words"] if p else []
        return cache[vid]

    out = []
    for r in rows:
        ws = words(r["video_id"])
        if not ws:
            continue
        a = r["t"]
        b = a + r["span_s"] - BACKOFF_S          # stop before the next case
        span = b - a
        if span < 300:
            continue

        seg = [x for x in ws if a <= x.get("t", 0) <= b]
        text = " ".join(x.get("w", "") for x in seg)
        tail = " ".join(x.get("w", "") for x in seg if x.get("t", 0) >= b - TAIL_S)
        if not text:
            continue

        sents = re.split(r"(?<=[.?!])\s+", text)
        # Guard, because this has produced a wrong ranking three times now.
        # Pre-2023 captions carry no full stops, so the split returns one giant
        # "sentence"; if it contains "your honor" the whole hearing is credited
        # to the defendant and her side comes back empty, scoring 0 asks. Those
        # then sort to the top on a measurement that never ran.
        if len(sents) < 40:
            continue
        theirs = [s for s in sents if DEFER.search(s)]
        hers = [s for s in sents if not DEFER.search(s)]
        if len(hers) < 15 or len(theirs) < 5:
            continue
        her_txt, their_txt = " ".join(hers), " ".join(theirs)

        asks = len(ASK.findall(her_txt))
        their_nums = len(NUM.findall(their_txt))
        their_conc = len(CONCRETE.findall(their_txt))
        their_words = max(1, len(their_txt.split()))
        # both sides on specifics, not one side lecturing
        specifics = min(asks, 12) * 2.2 + min(their_nums, 30) * 0.7 + min(their_conc, 25) * 0.8
        detail_rate = (their_nums + their_conc) / (their_words / 100.0)

        harsh = len(HARSH_END.findall(tail))
        soft = len(SOFT_END.findall(tail))
        ending = harsh * 6.0 - soft * 5.0

        sc = specifics + ending
        sc += 8 if 480 <= span <= 960 else 0
        out.append({**r, "span_s": round(span, 1), "asks": asks,
                    "their_nums": their_nums, "their_concrete": their_conc,
                    "detail_rate": round(detail_rate, 1),
                    "ends_harsh": harsh, "ends_soft": soft,
                    "rank_score": round(sc, 1),
                    "tail": re.sub(r"\s+", " ", tail)[-200:]})

    out.sort(key=lambda r: -r["rank_score"])
    OUT.write_text(json.dumps(out[:200], indent=2), encoding="utf-8")
    print(f"hearings ranked : {len(out)}")
    print(f"ending harsh    : {sum(1 for r in out if r['ends_harsh'])}")
    print(f"ending soft     : {sum(1 for r in out if r['ends_soft'])}")
    print(f"-> {OUT}\n")
    print(f"{'date':11s} {'min':>5} {'asks':>5} {'detail':>7} {'end':>4}  link")
    print("-" * 70)
    for r in out[:12]:
        t = int(r["t"])
        end = "HARSH" if r["ends_harsh"] and not r["ends_soft"] else (
              "soft" if r["ends_soft"] else "-")
        print(f"{r['date']:11s} {r['span_s']/60:5.1f} {r['asks']:5d} "
              f"{r['detail_rate']:7.1f} {end:>5}  youtu.be/{r['video_id']}?t={max(0,t-6)}")


if __name__ == "__main__":
    main()
