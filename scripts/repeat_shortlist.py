"""
LEGACY — 2026-08-18 repeat-shortlist workflow. NOT on the daily path and not
the current scoring definition. The live editorial layer is BOYD_EDITORIAL_V2
(src/boydclips/editorial.py, prompts/score_cases.md); use tools/editorial_eval.py
to re-score stored cases and `tools/banger_digest.py --editorial` on the manual
path. Rows in the `rescores` table are keyed by rubric_version, so anything this
workflow stored under the retired rubric is ignored under the current version.

The shortlist that actually decides what to build next.

Joins the three checks that each answer a different question:

  repeats.py    did this person come back?          (the 1.36x format lift)
  rescores      is the hearing any good on the      (the CURRENT rubric —
                rubric we actually use?              the 727 stored scores are
                                                     from a retired one)
  oncamera.json is there anyone on screen?          (a transcript cannot see
                                                     an empty Zoom tile)

An episode needs all three. Nothing here promotes anything past the safety
gate — every hearing listed already passed it independently.

    python scripts/repeat_shortlist.py
    python scripts/repeat_shortlist.py --all     # include failures, with reasons
"""
from __future__ import annotations

import sys as _sys
_sys.stderr.write('[LEGACY] ' + __doc__.strip().splitlines()[0] + ' -- see the module docstring\n')

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boydclips import repeats                     # noqa: E402
from boydclips.config import load_config, prompt_text  # noqa: E402
from boydclips.state import Store                 # noqa: E402


def main() -> int:
    show_all = "--all" in sys.argv
    cfg = load_config()
    store = Store(cfg.path("paths.state_db"))
    version, _, _ = prompt_text("score_cases")

    new: dict[str, dict] = {}
    try:
        for k, sc, old, elig, reason in store.conn.execute(
                "SELECT case_key, total_score, old_score, eligible, reason "
                "FROM rescores WHERE rubric_version = ?", (version,)):
            new[k] = {"score": sc, "old": old, "eligible": bool(elig),
                      "reason": reason}
    except Exception:
        print("no rescores table — run scripts/rescore_repeats.py first")
        return 1

    cam_path = ROOT / "state" / "oncamera.json"
    cam = json.loads(cam_path.read_text()) if cam_path.exists() else {}

    eps = repeats.qualifying(
        store.conn, dict(cfg.get("analysis.repeat_defendant", {}) or {}))

    rows = []
    for e in eps:
        scored = [(new[h["case_key"]]["score"], h) for h in e.hearings
                  if h["case_key"] in new and new[h["case_key"]]["score"] is not None]
        if not scored:
            rows.append((None, e, None, None, "not re-scored yet"))
            continue
        best_new, best_h = max(scored, key=lambda t: t[0])
        c = cam.get(best_h["case_key"])
        camera = None if c is None else c.get("usable")
        why = ""
        if camera is False:
            why = c.get("reason", "no live tiles")
        elif camera is None:
            why = "camera not probed"
        elif not new[best_h["case_key"]]["eligible"]:
            why = new[best_h["case_key"]]["reason"] or "below the score gate"
        rows.append((best_new, e, best_h, camera, why))

    good = [r for r in rows if r[0] is not None and r[3] is True and not r[4]]
    good.sort(key=lambda r: -r[0])

    print(f"rubric v{version} · {len(new)} hearings re-scored · "
          f"{len(cam)} camera-probed\n")
    print(f"{'#':>2}  {'defendant':24}{'old':>6}{'new':>7}{'hrs':>5}{'min':>7}  best hearing")
    for i, (sc, e, h, _cam, _why) in enumerate(good, 1):
        print(f"{i:>2}  {e.defendant[:22]:24}{e.best_score:>6.1f}{sc:>7.1f}"
              f"{len(e.hearings):>5}{e.total_s/60:>7.1f}  {h['case_key']}")
    if not good:
        print("  (nothing clears all three checks yet)")

    if show_all:
        print("\nfiltered out:")
        for sc, e, h, cam, why in sorted(
                (r for r in rows if r not in good),
                key=lambda r: -(r[0] or -1)):
            s = f"{sc:.1f}" if sc is not None else "  - "
            print(f"    {e.defendant[:22]:24} new={s:>5}  {why}")

    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
