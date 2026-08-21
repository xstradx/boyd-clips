"""Find her challenge questions across the WHOLE archive, including the old years.

The turn-based finder splits speech on `>>` speaker markers, which the court
only started emitting around July 2025 - so it can rank roughly 300 dockets and
is blind to the other 1,400. This detector keys on punctuation instead, so it
works everywhere.

What it looks for is the speech act Nathan identified: a real question put to
the person - why did you, what makes you think, do you know how many - as
opposed to the confirmations she recites all day ("do you understand?") and the
"right?" she tags onto sentences.

Sentences are split before matching. Running the alternation over a whole
20,000-word transcript backtracks catastrophically and does not finish.
"""

from __future__ import annotations

import glob
import json
import os
import re
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "state" / "questions.json"

SPLIT = re.compile(r"(?<=[.?!])\s+")
CHALL = re.compile(r"\b(why|what|how|who)\b.*\byou\b|"
                   r"\bdo you (know|think|want|realize|expect)\b|"
                   r"\bare you (serious|kidding|telling me)\b", re.I)
DROP = re.compile(r"do you understand|is that correct|any objection|how do you plead|"
                  r"raise your right hand|do you swear|do you need|do you have any "
                  r"questions|what do you mean|what's your name|how do you spell", re.I)


def main() -> None:
    db = sqlite3.connect(ROOT / "state" / "pipeline.db")
    db.row_factory = sqlite3.Row
    dates = {r["video_id"]: (r["docket_date"] or "")
             for r in db.execute("select video_id, docket_date from dockets")}

    hits, scanned = [], 0
    for tp in sorted(glob.glob(str(ROOT / "work" / "*" / "*.transcript.json"))):
        vid = os.path.basename(os.path.dirname(tp))
        try:
            d = json.load(open(tp, encoding="utf-8"))
        except Exception:
            continue
        ws = d.get("words") or []
        if not ws:
            continue
        scanned += 1
        # word index -> time, so a match can be placed without re-scanning
        text_parts, idx = [], []
        for i, x in enumerate(ws):
            w = x.get("w", "")
            if w:
                text_parts.append(w)
                idx.append(i)
        txt = " ".join(text_parts)
        pos = 0
        for sent in SPLIT.split(txt):
            n = len(sent)
            start = pos
            pos += n + 1
            wc = len(sent.split())
            if not (5 <= wc <= 26) or "?" not in sent:
                continue
            if DROP.search(sent) or not CHALL.search(sent):
                continue
            frac = start / max(1, len(txt))
            wi = min(len(idx) - 1, int(frac * len(idx)))
            hits.append({"date": dates.get(vid, ""), "video_id": vid,
                         "t": round(ws[idx[wi]].get("t", 0.0), 1),
                         "q": sent.strip()[:200]})
        if scanned % 200 == 0:
            print(f"  scanned {scanned} transcripts, {len(hits)} questions", flush=True)

    OUT.write_text(json.dumps(hits, indent=1), encoding="utf-8")
    print(f"\ntranscripts scanned : {scanned}")
    print(f"challenge questions : {len(hits)}")
    print("by year             :",
          dict(sorted(Counter(h["date"][:4] for h in hits if h["date"]).items())))
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
