"""Rank the bank and print the next N candidate videos.

Reads every scored case in state/pipeline.db, keeps the ones that already
passed safety and the gates and have not been published, and ranks them by the
blended rubric + notoriety score. Coverage lookups are network calls, so they
run only on the shortlist.

    python scripts/next_videos.py [N]
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boydclips import notoriety                      # noqa: E402
from boydclips.transcribe import hhmmss              # noqa: E402

WANT = int(sys.argv[1]) if len(sys.argv) > 1 else 10
SHORTLIST = WANT * 3


def main() -> int:
    db = sqlite3.connect(ROOT / "state" / "pipeline.db")
    db.row_factory = sqlite3.Row

    published = {r["clip_id"] for r in db.execute("SELECT clip_id FROM publications")}
    dockets = {r["video_id"]: r for r in db.execute("SELECT * FROM dockets")}

    cases = []
    for row in db.execute("SELECT video_id, payload FROM cases"):
        try:
            p = json.loads(row["payload"])
        except Exception:
            continue
        if not p.get("eligible"):
            continue
        if not (p.get("safety") or {}).get("safety_pass"):
            continue
        if not p.get("shortable"):
            continue
        p["_video_id"] = row["video_id"]
        cases.append(p)

    print(f"{len(cases)} eligible, safety-passed, shortable cases in the bank")
    if not cases:
        return 1

    # Cheap pass first: rubric + severity only, no network.
    cheap = notoriety.rank(cases, check_competitors=False)
    shortlist = cheap[:SHORTLIST]
    print(f"checking coverage on the top {len(shortlist)}...\n")

    ranked = notoriety.rank(shortlist, check_competitors=True)

    for i, c in enumerate(ranked[:WANT], 1):
        d = dockets.get(c["_video_id"])
        date = (d["docket_date"] if d else None) or "undated"
        key = f'{c["_video_id"]}:{int(round(c["start_s"]))}'
        dur = (c.get("end_s", 0) - c.get("start_s", 0)) / 60.0
        cov = c["notoriety"]["coverage"]

        print(f'{i:2}. {c.get("defendant_name") or "?"}   [{key}]')
        print(f'    blended {c["blended_score"]:.1f}  '
              f'(rubric {float(c.get("total_score") or 0):.1f}, '
              f'notoriety {c["notoriety"]["total"]:.0f})')
        print(f'    {date}  @{hhmmss(c["start_s"])}  ~{dur:.0f} min  '
              f'{c.get("proceeding_type") or "?"}')
        print(f'    {c["notoriety"]["severity_why"]}')
        if cov.get("covered"):
            print(f'    COVERAGE: {cov["why"]}')
        summary = (c.get("summary") or "").strip().replace("\n", " ")
        print(f'    {summary[:190]}')
        print(f'    render: boyd run --case {key}')
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
