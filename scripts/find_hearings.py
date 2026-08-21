"""Find whole hearings worth a video - the product, not a 60-second moment.

Nathan, 2026-08-21: "complete video would be the defendant comes in usually most
times when there's a MTR defendant judge Boyd always kinda talks to them and if
it's actually at least 6-7 min long that's a good video just something with
drama and judge Boyd calling out people for their bs or asking them what
actually happened and then the defendant talks to the judge".

So the unit is the hearing at 8-20 minutes, not a moment. Both halves are
required: she engages, and they answer at length. A monologue is not the
product, and neither is a defendant who only says "yes ma'am".

Runs on dockets with `>>` speaker markers, which is roughly 300 of 1,701 - the
court only began emitting them around July 2025. Cause-number segmentation was
tried first as a way to reach the older years and does not work: the numbers are
not transcribed recognisably, and a 2022 docket sampled had none at all.

Scored per WINDOW of contiguous turns, sized to the target runtime, so the
output is something that can be cut as-is.
"""

from __future__ import annotations

import glob
import json
import os
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "state" / "hearings.json"

MIN_S, MAX_S = 360.0, 1200.0          # 6 to 20 minutes

MTR = re.compile(r"motion to revoke|revocation|violated condition|"
                 r"adjudicat\w+|your probation|revoke your", re.I)
DEFER = re.compile(r"\byour honou?r\b|\b(yes|no),?\s+(ma'?am|sir)\b", re.I)
CTRL = re.compile(r"\ball right\b|\bthe court\b|\bhere'?s the thing\b|"
                  r"\bi'?m going to\b|\bcounsel\b|\blet me ask you\b", re.I)
CHALL = re.compile(r"\b(why|what|how|who)\b.*\byou\b|"
                   r"\bdo you (know|think|want|realize|expect)\b|"
                   r"\bare you (serious|kidding|telling me)\b", re.I)
PROC = re.compile(r"raise your right hand|solemnly swear|jury panel|voir dire|"
                  r"members of the jury|state calls", re.I)


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


def score(win):
    """win is a list of (t, text). Returns (score, detail) or None."""
    span = win[-1][0] - win[0][0]
    if not (MIN_S <= span <= MAX_S):
        return None
    text = " ".join(t for _, t in win)
    if PROC.search(text):
        return None                       # a trial, not a docket hearing
    if not MTR.search(text):
        return None                       # Nathan's typical setting

    bench, other = [], []
    for _, t in win:
        (other if DEFER.search(t) else bench).append(t)
    if len(bench) < 4 or len(other) < 4:
        return None                       # needs both sides present

    bw = sum(len(t.split()) for t in bench)
    ow = sum(len(t.split()) for t in other)
    if bw < 250 or ow < 120:
        return None                       # she must talk, and so must they

    # Balance: a monologue and a rubber-stamping both fail.
    balance = min(bw, ow) / max(1.0, max(bw, ow))
    # Do they answer, or only acknowledge?
    real_replies = sum(1 for t in other if len(t.split()) >= 15)
    chall = sum(1 for t in bench if CHALL.search(t) and "?" in t)
    control = sum(1 for t in bench if CTRL.search(t))

    sc = 0.0
    sc += min(30, balance * 75)            # both sides genuinely talking
    sc += min(26, real_replies * 3.5)      # they answer at length
    sc += min(24, chall * 6.0)             # she calls it out / asks what happened
    sc += min(10, control * 1.5)
    sc += 10 if 420 <= span <= 900 else 0  # squarely in the sweet spot
    return round(sc, 1), {
        "span_s": round(span, 1), "turns": len(win),
        "boyd_words": bw, "other_words": ow,
        "balance": round(balance, 2), "real_replies": real_replies,
        "challenges": chall,
    }


def main() -> None:
    db = sqlite3.connect(ROOT / "state" / "pipeline.db")
    db.row_factory = sqlite3.Row
    dates = {r["video_id"]: (r["docket_date"] or "")
             for r in db.execute("select video_id, docket_date from dockets")}

    found, usable = [], 0
    for tp in sorted(glob.glob(str(ROOT / "work" / "*" / "*.transcript.json"))):
        vid = os.path.basename(os.path.dirname(tp))
        try:
            d = json.load(open(tp, encoding="utf-8"))
        except Exception:
            continue
        ws = d.get("words") or []
        if sum(1 for x in ws if x.get("w", "").strip().startswith(">>")) < 20:
            continue                       # no speaker structure to work with
        usable += 1
        ts = turns(ws)
        i = 0
        while i < len(ts):
            j = i
            while j < len(ts) and ts[j][0] - ts[i][0] <= MAX_S:
                j += 1
            best = None
            for k in range(i + 8, j + 1):
                r = score(ts[i:k])
                if r and (best is None or r[0] > best[0]):
                    best = (r[0], r[1], k)
            if best:
                sc, det, k = best
                found.append({"video_id": vid, "date": dates.get(vid, ""),
                              "t": round(ts[i][0], 1), "score": sc, **det,
                              "open": " ".join(t for _, t in ts[i:i + 4])[:300]})
                i = k
            else:
                i += 1

    found.sort(key=lambda r: -r["score"])
    OUT.write_text(json.dumps(found[:300], indent=2), encoding="utf-8")
    print(f"dockets with speaker structure : {usable}")
    print(f"hearings found                 : {len(found)}")
    print(f"-> {OUT}\n")
    for r in found[:10]:
        t = int(r["t"])
        print(f"[{r['score']:5.1f}] {r['date']}  {r['span_s']/60:4.1f} min  "
              f"balance {r['balance']:.2f}  replies {r['real_replies']:2d}  "
              f"challenges {r['challenges']}")
        print(f"        youtu.be/{r['video_id']}?t={max(0, t - 10)}")
        print(f"        {re.sub(r'  +', ' ', r['open'])[:150]}")


if __name__ == "__main__":
    main()
