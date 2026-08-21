"""Cut hearings on Nathan's own boundary: "the court is calling".

Nathan, 2026-08-21: "the video of that defendant should always start with 'the
court is calling'". That solved a problem two other approaches could not.
Cause-number segmentation fails - the numbers are not transcribed recognisably,
and a 2022 docket sampled had none at all. Speaker-marker windowing only works
after July 2025. This phrase appears 3.1 to 5.5 times per docket in every year
from 2021 to 2026, including the unpunctuated early captions.

A hearing therefore runs from one call to the next, capped at the target
runtime. Nathan's shape, in his words: a motion to revoke, "judge Boyd calling
out people for their bs or asking them what actually happened and then the
defendant talks to the judge", ending a beat after the ruling.

Both sides must talk. A monologue is not the product and neither is a defendant
who only says "yes ma'am".
"""

from __future__ import annotations

import glob
import json
import os
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "state" / "called_hearings.json"

MIN_S, MAX_S = 360.0, 1200.0

CALL = re.compile(r"court is calling|the court calls|calling the case", re.I)
MTR = re.compile(r"motion to revoke|revocation|violated condition|adjudicat\w+|"
                 r"your probation|revoke your", re.I)
DEFER = re.compile(r"\byour honou?r\b|\b(yes|no),?\s+(ma'?am|sir)\b", re.I)
CHALL = re.compile(r"\b(why|what|how|who)\b[^.?!]{0,60}\byou\b|"
                   r"\bdo you (know|think|want|realize|expect)\b|"
                   r"\bare you (serious|kidding|telling me)\b", re.I)
TRIAL = re.compile(r"raise your right hand|solemnly swear|jury panel|voir dire|"
                   r"members of the jury|state calls", re.I)
BOND = re.compile(r"\bbond\b|\bsurety\b|\bmagistrat\w+\b", re.I)


def main() -> None:
    db = sqlite3.connect(ROOT / "state" / "pipeline.db")
    db.row_factory = sqlite3.Row
    dates = {r["video_id"]: (r["docket_date"] or "")
             for r in db.execute("select video_id, docket_date from dockets")}

    out, scanned = [], 0
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
        words = [x.get("w", "") for x in ws]
        times = [x.get("t", 0.0) for x in ws]
        txt = " ".join(words)

        # map character offset -> word index once
        starts, pos = [], 0
        for w in words:
            starts.append(pos)
            pos += len(w) + 1

        marks = []
        for m in CALL.finditer(txt):
            lo, hi = 0, len(starts) - 1
            while lo < hi:
                mid = (lo + hi) // 2
                if starts[mid] < m.start():
                    lo = mid + 1
                else:
                    hi = mid
            marks.append(lo)
        if not marks:
            continue

        for a, b in zip(marks, marks[1:] + [len(words)]):
            t0, t1 = times[a], times[min(b, len(times) - 1)]
            if t1 - t0 > MAX_S:                     # cap an over-long run
                cut = a
                while cut < len(times) and times[cut] - t0 <= MAX_S:
                    cut += 1
                b, t1 = cut, times[min(cut, len(times) - 1)]
            span = t1 - t0
            if not (MIN_S <= span <= MAX_S):
                continue
            seg = " ".join(words[a:b])
            if TRIAL.search(seg) or not MTR.search(seg):
                continue

            sents = re.split(r"(?<=[.?!])\s+", seg)
            theirs = [s for s in sents if DEFER.search(s)]
            if len(theirs) < 3:
                continue
            their_words = sum(len(s.split()) for s in theirs)
            total = max(1, len(seg.split()))
            if their_words < 80:
                continue

            chall = len(CHALL.findall(seg))
            bond = len(BOND.findall(seg))
            share = their_words / total
            sc = 0.0
            sc += min(30, share * 140)            # they genuinely answer
            sc += min(28, chall * 3.5)            # she calls it out / asks
            sc += min(14, len(theirs) * 1.2)
            sc += 12 if 420 <= span <= 900 else 0
            sc -= min(20, bond * 4.0)
            out.append({"video_id": vid, "date": dates.get(vid, ""),
                        "t": round(t0, 1), "span_s": round(span, 1),
                        "score": round(sc, 1), "challenges": chall,
                        "their_share": round(share, 3),
                        "open": re.sub(r"\s+", " ", seg[:220])})
        if scanned % 300 == 0:
            print(f"  scanned {scanned}, hearings {len(out)}", flush=True)

    out.sort(key=lambda r: -r["score"])
    OUT.write_text(json.dumps(out[:400], indent=2), encoding="utf-8")
    import collections
    print(f"\ntranscripts scanned : {scanned}")
    print(f"hearings found      : {len(out)}")
    print("by year             :",
          dict(sorted(collections.Counter(r["date"][:4] for r in out if r["date"]).items())))
    print(f"-> {OUT}\n")
    for r in out[:10]:
        t = int(r["t"])
        print(f"[{r['score']:5.1f}] {r['date']}  {r['span_s']/60:4.1f} min  "
              f"they talk {r['their_share']*100:4.1f}%  challenges {r['challenges']:2d}")
        print(f"        youtu.be/{r['video_id']}?t={max(0, t - 6)}")
        print(f"        {r['open'][:140]}")


if __name__ == "__main__":
    main()
