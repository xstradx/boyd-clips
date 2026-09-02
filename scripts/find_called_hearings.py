"""Cut hearings on Nathan's own boundary: "the court is calling".

Nathan, 2026-08-21: "the video of that defendant should always start with 'the
court is calling'". That solved a problem two other approaches could not.
Cause-number segmentation fails - the numbers are not transcribed recognisably,
and a 2022 docket sampled had none at all. Speaker-marker windowing only works
after July 2025. This phrase appears 3.1 to 5.5 times per docket in every year
from 2021 to 2026, including the unpunctuated early captions.

A hearing runs from one call to the next. Nathan's shape, in his words: a
motion to revoke, "judge Boyd calling out people for their bs or asking them
what actually happened and then the defendant talks to the judge", ending a
beat after the ruling.

Rewritten 2026-09-01 on `tools/hearing_measure.py` after it was measured
against his own winners (`data/catalog_vs_picker.json`) and found to see none
of them - the reasons are in that module's docstring. Every regex, gate and
score now lives there; `tools/check_picker.py --selftest` proves the eleven
winners come out as candidates and the known-bad controls do not.

Both sides must talk. A monologue is not the product and neither is a defendant
who only says "yes ma'am". Because the auto captions cannot tell WHO is
speaking, that is measured without attribution: her questions at "you" per
minute, and first-person narrative per 100 words.

    python scripts/find_called_hearings.py            # -> state/called_hearings.json
"""

from __future__ import annotations

import collections
import glob
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import hearing_measure as hm  # noqa: E402

OUT = ROOT / "state" / "called_hearings.json"
SUMMARY = ROOT / "state" / "called_hearings_summary.json"
PROBE = ROOT / "state" / "picker_probe.json"     # every hearing seen, gated or not

KEEP = ("video_id", "date", "t", "span_s", "over_cap", "jury_cut", "score",
        "q_per_min", "narr_per_100", "punct_frac", "mtr", "sent", "outcome",
        "defer", "chall", "bond", "words", "open")


def main() -> int:
    cfg = hm.load_cfg()
    db = sqlite3.connect(ROOT / "state" / "pipeline.db")
    db.row_factory = sqlite3.Row
    dates = {r["video_id"]: (r["docket_date"] or "")
             for r in db.execute("select video_id, docket_date from dockets")}

    out, scanned, seen, probe = [], 0, 0, []
    fails: collections.Counter = collections.Counter()
    for tp in sorted(glob.glob(str(ROOT / "work" / "*" / "*.transcript.json"))):
        vid = os.path.basename(os.path.dirname(tp))
        try:
            rows = hm.scan(vid, cfg, path=tp)
        except Exception as e:                       # noqa: BLE001
            print(f"  skip {vid}: {e}")
            continue
        if not rows:
            continue
        scanned += 1
        for r in rows:
            seen += 1
            probe.append({"vid": vid, "date": dates.get(vid, ""), "t": r["t"],
                          "span": r["span_s"], "q_per_min": r["q_per_min"],
                          "narr_per_100": r["narr_per_100"], "mtr": r["mtr"],
                          "sent": r["sent"], "punct": r["punct_frac"],
                          "words": r["words"], "fails": r["fails"]})
            if r["fails"]:
                fails[",".join(r["fails"])] += 1
                continue
            row = {k: r[k] for k in KEEP if k in r}
            row["date"] = dates.get(vid, "")
            out.append(row)
        if scanned % 300 == 0:
            print(f"  scanned {scanned}, candidates {len(out)}", flush=True)

    out.sort(key=lambda r: -r["score"])
    keep_top = int(cfg.get("keep_top", 0)) or len(out)
    dropped = max(0, len(out) - keep_top)
    OUT.write_text(json.dumps(out[:keep_top], indent=2), encoding="utf-8")

    by_year = dict(sorted(collections.Counter(r["date"][:4] for r in out if r["date"]).items()))
    summary = {
        "transcripts_scanned": scanned,
        "hearings_seen": seen,
        "candidates": len(out),
        "written": min(len(out), keep_top),
        "dropped_by_keep_top": dropped,
        "over_cap": sum(1 for r in out if r["over_cap"]),
        "jury_cut": sum(1 for r in out if r["jury_cut"]),
        "by_year": by_year,
        "excluded_by_reason": dict(fails.most_common()),
        "gates": {"min_s": cfg["min_s"], "max_s": cfg["max_s"],
                  "q_per_min_min": cfg["q_per_min_min"],
                  "narr_per_100_min": cfg["narr_per_100_min"],
                  "overlong_s": cfg.get("overlong_s")},
    }
    SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    PROBE.write_text(json.dumps(probe), encoding="utf-8")

    print(f"\ntranscripts scanned : {scanned}")
    print(f"hearings seen       : {seen}")
    print(f"candidates          : {len(out)}  (over cap {summary['over_cap']}, "
          f"jury-cut {summary['jury_cut']})")
    if dropped:
        print(f"DROPPED by keep_top : {dropped}  (config/picker.json keep_top={keep_top})")
    print("by year             :", by_year)
    print("excluded            :", summary["excluded_by_reason"])
    print(f"-> {OUT}\n-> {SUMMARY}\n")
    for r in out[:10]:
        t = int(r["t"])
        print(f"[{r['score']:5.1f}] {r['date']}  {r['span_s']/60:4.1f} min  "
              f"q/min {r['q_per_min']:4.2f}  narr {r['narr_per_100']:4.2f}"
              f"{'  OVER CAP' if r['over_cap'] else ''}")
        print(f"        youtu.be/{r['video_id']}?t={max(0, t - 6)}")
        print(f"        {r['open'][:140]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
