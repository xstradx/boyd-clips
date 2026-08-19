import sys, sqlite3, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
c = sqlite3.connect(ROOT/"state"/"pipeline.db"); c.row_factory = sqlite3.Row
d = {v: dt for v, dt in c.execute("select video_id, docket_date from dockets")}
for k in ("cj9gKdNcJdk:5277", "9R1jJ_QX1Wg:8262", "4zkUTUavW4I:116", "UXSXYgPa_bY:6900"):
    r = c.execute("select * from cases where case_key=?", (k,)).fetchone()
    if not r: print(k, "NOT FOUND"); continue
    p = json.loads(r["payload"] or "{}")
    print("%-18s %s  %-42s cause=%-16s %.1fmin  score %.1f" % (
        k, d.get(r["video_id"], "?"), (r["defendant"] or "?")[:42],
        r["cause_number"] or "-", (r["end_s"]-r["start_s"])/60, r["total_score"] or 0))
print("\nall cases on those four dockets w/ similar names:")
for r in c.execute("select case_key, video_id, defendant, cause_number, total_score from cases "
                   "where lower(defendant) like '%mios%' or lower(defendant) like '%mease%' "
                   "or lower(defendant) like '%miel%' or lower(defendant) like '%milos%' "
                   "or lower(defendant) like '%blackburn%'"):
    print("  %-20s %s  %-44s %s  %s" % (r["case_key"], d.get(r["video_id"],"?"),
          (r["defendant"] or "")[:44], r["cause_number"], r["total_score"]))
