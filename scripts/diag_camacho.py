import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from boydclips import repeats
from boydclips.config import load_config
from boydclips.state import Store
cfg = load_config(); store = Store(cfg.path("paths.state_db"))
eps = repeats.qualifying(store.conn, dict(cfg.get("analysis.repeat_defendant", {}) or {}))
print("qualifying episodes:", len(eps))
for e in eps:
    print("  %-30r hearings=%d" % (e.defendant, len(e.hearings)))
print("\ncases table rows matching 'camacho':")
for r in store.conn.execute(
        "SELECT case_key, video_id, defendant, cause_number, total_score, safety_pass "
        "FROM cases WHERE lower(defendant) LIKE '%camacho%'"):
    print("  ", tuple(r))
print("\nJjRfzudxY1w:2775 ->")
row = store.conn.execute("SELECT case_key, defendant, cause_number FROM cases WHERE case_key='JjRfzudxY1w:2775'").fetchone()
print("  ", tuple(row) if row else "NOT FOUND")
store.close()
