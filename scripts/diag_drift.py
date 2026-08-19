"""Did something overwrite cases.total_score? Compare against what the
re-score captured as old_score at the time it ran."""
import sys, sqlite3
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
c = sqlite3.connect(ROOT / "state" / "pipeline.db"); c.row_factory = sqlite3.Row

print("rescores rows:", c.execute("select count(*) from rescores").fetchone()[0])
print("\ncase_key                 rescores.old  rescores.new  cases.total_score  DRIFT")
drift = 0
for r in c.execute("""
    SELECT r.case_key, r.old_score, r.total_score AS new_score, x.total_score AS live
    FROM rescores r JOIN cases x ON x.case_key = r.case_key
    ORDER BY r.case_key"""):
    d = abs((r["old_score"] or 0) - (r["live"] or 0)) > 0.01
    if d:
        drift += 1
    if d or r["case_key"].startswith("JjRfzudxY1w"):
        print("%-24s %12s %13s %18s  %s" % (
            r["case_key"], r["old_score"], r["new_score"], r["live"], "CHANGED" if d else ""))
print("\n%d of %d re-scored cases no longer hold the score the re-score saw" % (
    drift, c.execute("select count(*) from rescores").fetchone()[0]))

print("\ndockets touched most recently:")
for r in c.execute("SELECT video_id, status, analyzed_at, transcribed_at FROM dockets "
                   "ORDER BY COALESCE(analyzed_at, transcribed_at) DESC LIMIT 8"):
    print("  ", tuple(r))
print("\ncases.created_at range:")
print("  ", c.execute("SELECT min(created_at), max(created_at) FROM cases").fetchone()[0:2])
print("\nrows created in the last day:",
      c.execute("SELECT count(*) FROM cases WHERE created_at > datetime('now','-1 day')").fetchone()[0])
