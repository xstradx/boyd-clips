"""
LEGACY — 2026-08-18 repeat-shortlist workflow. NOT on the daily path and not
the current scoring definition. The live editorial layer is BOYD_EDITORIAL_V2
(src/boydclips/editorial.py, prompts/score_cases.md); use tools/editorial_eval.py
to re-score stored cases and `tools/banger_digest.py --editorial` on the manual
path. Rows in the `rescores` table are keyed by rubric_version, so anything this
workflow stored under the retired rubric is ignored under the current version.

What the shortlisted episodes are actually about, hearing by hearing."""
import sys as _sys
_sys.stderr.write('[LEGACY] ' + __doc__.strip().splitlines()[0] + ' -- see the module docstring\n')

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
from boydclips import editorial, repeats
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
    if not any(h["case_key"] in new for h in e.hearings):
        print(f"  (no hearings of {e.defendant} re-scored under {version}; run scripts/rescore_repeats.py)")
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
        for dim in [d for d in editorial.DIMENSIONS if d in (pay.get("scores") or {})]:
            d = (pay.get("scores") or {}).get(dim)
            if d and d.get("score", 0) >= 0.6 * editorial.DIMENSIONS[dim]:   # v2: points on each dim's own max
                print(textwrap.fill(f"{dim} {d['score']}: {d.get('justification','')}",
                                    W - 3, initial_indent="   * ",
                                    subsequent_indent="     "))
    print()
store.close()
