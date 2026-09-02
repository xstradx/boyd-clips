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

Rewritten 2026-09-01 on `tools/hearing_measure.py`. The version before split
the hearing into sentences and credited every sentence containing "your honor"
to the defendant. 69% of the archive has no punctuation, so the split returned
one sentence and the guard `len(sents) < 40` threw the hearing away - three
wrong rankings, then silence on everything before mid-2023. Nothing here
claims to know who is speaking now: "their" detail is numbers and concrete
nouns within `NARR_WINDOW` words of a first-person narrative hit; her asks are
counted over the whole text. The outcome is still read from the closing
stretch only (`TAIL_S`, stopping `BACKOFF_S` before the next call).

    python scripts/rank_hearings.py                   # -> state/ranked_hearings.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import hearing_measure as hm  # noqa: E402

IN = ROOT / "state" / "called_hearings.json"
OUT = ROOT / "state" / "ranked_hearings.json"
PROBE = ROOT / "state" / "rank_probe.json"    # every measured row, for re-deriving the score

MIN_Q, MIN_NARR = 8, 4       # below this the specifics measure has nothing to measure
TOP = 200


def main() -> int:
    rows = json.loads(IN.read_text(encoding="utf-8"))
    cache: dict[str, tuple[list, list]] = {}

    def words(vid):
        if vid not in cache:
            p = hm.transcript_path(vid)
            cache[vid] = hm.load_words(p) if p else ([], [])
        return cache[vid]

    out, thin = [], 0
    for r in rows:
        ws, ts = words(r["video_id"])
        if not ws:
            continue
        a = next((i for i, t in enumerate(ts) if t >= r["t"] - 0.05), None)
        if a is None:
            continue
        end = r["t"] + r["span_s"]
        b = a
        while b < len(ts) and ts[b] <= end:
            b += 1
        m = hm.measure(ws, ts, a, b)
        if m["q"] < MIN_Q or m["narr"] < MIN_NARR:
            thin += 1
            continue
        out.append({**r, "asks": m["asks"], "their_nums": m["their_nums"],
                    "their_concrete": m["their_concrete"],
                    "detail_rate": m["detail_rate"],
                    "ends_harsh": m["ends_harsh"], "ends_soft": m["ends_soft"],
                    "rank_score": hm.rank_score(m, r["span_s"]),
                    "tail": m["tail"]})

    out.sort(key=lambda r: -r["rank_score"])
    OUT.write_text(json.dumps(out[:TOP], indent=2), encoding="utf-8")
    PROBE.write_text(json.dumps([{k: v for k, v in r.items() if k not in ("tail", "open")}
                                 for r in out]), encoding="utf-8")
    print(f"hearings ranked : {len(out)}  (written top {min(TOP, len(out))}, "
          f"{thin} too thin to measure: q<{MIN_Q} or narr<{MIN_NARR})")
    print(f"ending harsh    : {sum(1 for r in out if r['ends_harsh'])}")
    print(f"ending soft     : {sum(1 for r in out if r['ends_soft'])}")
    print(f"-> {OUT}\n")
    print(f"{'date':11s} {'min':>5} {'asks':>5} {'detail':>7} {'end':>5}  link")
    print("-" * 70)
    for r in out[:12]:
        t = int(r["t"])
        end = "HARSH" if r["ends_harsh"] and not r["ends_soft"] else (
              "soft" if r["ends_soft"] else "-")
        print(f"{r['date']:11s} {r['span_s']/60:5.1f} {r['asks']:5d} "
              f"{r['detail_rate']:7.1f} {end:>5}  youtu.be/{r['video_id']}?t={max(0, t-6)}"
              f"{'  OVER CAP' if r.get('over_cap') else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
