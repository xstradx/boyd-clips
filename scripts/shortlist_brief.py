"""What the shortlisted episodes are actually about, hearing by hearing."""
import json, sys, textwrap
from pathlib import Path

# Windows defaults stdout to cp1252 and the model's justifications contain
# en-dashes and arrows. Without this the script dies mid-report on a character.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from boydclips import repeats
from boydclips.config import load_config, prompt_text
from boydclips.state import Store

# Match on surname — the episode label is the FIRST hearing's name string,
# and the docket spells the same person differently between settings.
WANT = ("mccaskill", "mason", "kilpatrick", "camacho")
cfg = load_config(); store = Store(cfg.path("paths.state_db"))
version, _, _ = prompt_text("score_cases")
new = {}
for k, sc, js in store.conn.execute(
        "SELECT case_key, total_score, payload FROM rescores WHERE rubric_version=?",
        (version,)):
    new[k] = (sc, json.loads(js))
cam = json.loads((ROOT / "state" / "oncamera.json").read_text()) if (
    ROOT / "state" / "oncamera.json").exists() else {}
dates = {v: d for v, d in store.conn.execute("SELECT video_id, docket_date FROM dockets")}
old = {k: json.loads(p or "{}") for k, p in store.conn.execute(
    "SELECT case_key, payload FROM cases")}

W = 96
for e in repeats.qualifying(store.conn, dict(cfg.get("analysis.repeat_defendant", {}) or {})):
    if not any(w in (e.defendant or "").lower() for w in WANT):
        continue
    best = max((new[h["case_key"]][0], h) for h in e.hearings if h["case_key"] in new)
    print("=" * W)
    print(f"{e.defendant}  —  {len(e.hearings)} hearings across {e.dockets} dockets, "
          f"{e.total_s/60:.1f} min total   BEST NEW SCORE {best[0]:.1f}")
    print("=" * W)
    for h in e.hearings:
        k = h["case_key"]
        o = old.get(k, {})
        sc, pay = new.get(k, (None, {}))
        star = "  <<< the pick" if k == best[1]["case_key"] else ""
        c = cam.get(k)
        camtxt = "" if c is None else ("  [camera OK]" if c.get("usable") else "  [NO PICTURE]")
        print(f"\n-- {dates.get(h['video_id'],'?')}  {k}  {h['proceeding_type']}  "
              f"{(h['end_s']-h['start_s'])/60:.1f} min  "
              f"score {sc if sc is None else round(sc,1)}{camtxt}{star}")
        summ = (pay.get("summary") or o.get("summary") or "").strip()
        if summ:
            print(textwrap.fill(summ, W - 3, initial_indent="   ", subsequent_indent="   "))
        hq = pay.get("hook_quote") or o.get("hook_quote")
        if hq:
            print(textwrap.fill(f'HOOK: "{hq.strip()}"', W - 3,
                                initial_indent="   ", subsequent_indent="         "))
        for dim in ("pushback", "boyd_register", "receipt", "consequence"):
            d = (pay.get("scores") or {}).get(dim)
            if d and d.get("score", 0) >= 40:
                print(textwrap.fill(f"{dim} {d['score']}: {d.get('justification','')}",
                                    W - 3, initial_indent="   * ",
                                    subsequent_indent="     "))
    print()
store.close()
