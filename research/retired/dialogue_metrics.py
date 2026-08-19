"""Measure how much the DEFENDANT speaks in each scored case.

Recorded as data, not as a scoring weight. Nathan's read is that clips where
the defendant talks a lot perform best; turn-density alone did not predict his
picks (the marijuana clip he liked is 23% non-Boyd, and "you could have killed
somebody" is a 1% pure monologue), so this exists to be correlated against real
retention once clips have numbers — rather than baked into the rubric on a
sample of seven and my inference of what he liked.

Speaker attribution is approximate and says so. ">>" marks a speaker CHANGE,
not an identity, so turns are classified by register:

  * judge      - the dominant speaker; Boyd runs the room and always speaks most
  * attorney   - addresses the court ("Judge,", "Your Honor", "the State",
                 "my client", "we would ask")
  * defendant  - what's left: answers, deference ("yes ma'am"), first person

Anything built on this must treat it as a proxy. It is good enough to rank
cases against each other, not to make a claim about a specific person.

Usage:  python scripts/dialogue_metrics.py [--out state/dialogue_metrics.json]
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from boydclips.config import load_config          # noqa: E402
from boydclips.transcribe import get_transcript   # noqa: E402

ATTORNEY = re.compile(
    r"\b(your honor|judge[,.]|the state|my client|we would ask|counsel|"
    r"defence|defense|prosecutor|on behalf of|announce ready|waive)\b", re.I)
DEFERENCE = re.compile(r"\b(yes\s*(ma'?am|sir|judge)|no\s*(ma'?am|sir|judge)|correct)\b", re.I)


def turns_for(words) -> list[str]:
    turns, cur = [], []
    for w in words:
        if w.w.startswith(">>"):
            if cur:
                turns.append(" ".join(cur))
            cur = [w.w.lstrip("> ")]
        else:
            cur.append(w.w)
    if cur:
        turns.append(" ".join(cur))
    return [t.strip() for t in turns if t.strip()]


def classify(turns: list[str]) -> dict:
    if not turns:
        return {}
    lens = [len(t.split()) for t in turns]
    total = sum(lens)
    judge_i = max(range(len(turns)), key=lambda i: lens[i])

    # The judge is whoever speaks most overall; her turns are the long ones and
    # the ones issuing instructions. Approximated as the longest turn plus any
    # turn longer than the median non-longest turn.
    others = [i for i in range(len(turns)) if i != judge_i]
    med = sorted(lens[i] for i in others)[len(others) // 2] if others else 0

    counts = {"judge": 0, "attorney": 0, "defendant": 0}
    words = {"judge": 0, "attorney": 0, "defendant": 0}
    for i, t in enumerate(turns):
        n = lens[i]
        if i == judge_i or n > max(med * 3, 40):
            role = "judge"
        elif ATTORNEY.search(t):
            role = "attorney"
        elif DEFERENCE.search(t) or n <= 25:
            role = "defendant"
        else:
            role = "attorney"
        counts[role] += 1
        words[role] += n

    return {
        "turns": len(turns),
        "words_total": total,
        "defendant_turns": counts["defendant"],
        "defendant_words": words["defendant"],
        "defendant_word_share": round(words["defendant"] / total, 3) if total else 0.0,
        "attorney_word_share": round(words["attorney"] / total, 3) if total else 0.0,
        "judge_word_share": round(words["judge"] / total, 3) if total else 0.0,
    }


def main() -> int:
    out = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv \
        else Path("state/dialogue_metrics.json")
    cfg = load_config()
    conn = sqlite3.connect(cfg.path("paths.state_db"))
    conn.row_factory = sqlite3.Row

    rows = list(conn.execute(
        "SELECT case_key, video_id, start_s, end_s, defendant, total_score, "
        "safety_pass FROM cases"))
    print(f"{len(rows)} cases in the store")

    results, skipped = [], 0
    cache: dict[str, object] = {}
    for r in rows:
        vid = r["video_id"]
        if vid not in cache:
            try:
                cache[vid] = get_transcript(vid, Path("work") / vid)
            except Exception:
                cache[vid] = None
        t = cache[vid]
        if t is None:
            skipped += 1
            continue
        ws = [w for w in t.words if r["start_s"] <= w.t <= r["end_s"]]
        m = classify(turns_for(ws))
        if not m:
            skipped += 1
            continue
        m.update(case_key=r["case_key"], defendant=r["defendant"],
                 score=r["total_score"], safety_pass=bool(r["safety_pass"]),
                 duration_min=round((r["end_s"] - r["start_s"]) / 60, 1))
        results.append(m)

    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(f"wrote {len(results)} ({skipped} skipped) -> {out}")

    talky = sorted((r for r in results if r["safety_pass"] and (r["score"] or 0) >= 50),
                   key=lambda r: -r["defendant_word_share"])[:12]
    print("\nmost defendant-heavy eligible cases:")
    print(f"  {'case':22s} {'def%':>5} {'turns':>6} {'min':>5} {'score':>6}  defendant")
    for r in talky:
        print(f"  {r['case_key']:22s} {r['defendant_word_share']*100:>4.0f}% "
              f"{r['defendant_turns']:>6} {r['duration_min']:>5.1f} "
              f"{r['score'] or 0:>6.1f}  {str(r['defendant'])[:24]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
