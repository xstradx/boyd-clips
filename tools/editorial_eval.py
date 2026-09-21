"""Re-score historical cases with the current editorial brain and compare.

    python tools/editorial_eval.py KEY [KEY ...] [--out FILE.md] [--full-context]

KEY is a case_key from state/pipeline.db (video_id:start_s). The old score,
old rank and old dimension scores are read from the stored payload; the case's
stage-1 fields (span, name, charge, proceeding, one_line) are reused so the new
pass scores exactly the same hearing. One Analyzer.score call per case, on the
transcript already on disk. Nothing is rendered, uploaded or published.

Output: a markdown table + the full rationale block per case, printed and
optionally written to --out. Old payloads written under the retired rubric
carry pushback/boyd_register/... ; those are shown for reference only.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from boydclips import editorial  # noqa: E402
from boydclips.analyze import Analyzer  # noqa: E402
from boydclips.config import load_config  # noqa: E402
from boydclips.transcribe import Transcript  # noqa: E402


def load_case(conn: sqlite3.Connection, key: str) -> dict:
    row = conn.execute("SELECT video_id, payload, rank, total_score FROM cases WHERE case_key = ?", (key,)).fetchone()
    if not row:
        raise SystemExit(f"no such case_key in state/pipeline.db: {key}")
    payload = json.loads(row[1])
    payload["_old_rank"] = row[2]
    payload["_old_total"] = row[3]
    payload["_video_id"] = row[0]
    return payload


def stage1_view(p: dict) -> dict:
    """The fields the segment stage produces — what score() expects as input."""
    return {
        "start_s": float(p["start_s"]), "end_s": float(p["end_s"]),
        "defendant_name": p.get("defendant_name") or "unknown",
        "cause_number": p.get("cause_number") or "unknown",
        "charge": p.get("charge") or p.get("summary", "")[:80] or "unknown",
        "proceeding_type": p.get("proceeding_type") or "other",
        "outcome": p.get("outcome") or "unknown",
        "one_line": p.get("one_line") or (p.get("summary") or "")[:140] or "case",
        "continued": bool(p.get("continued", False)),
        "extraction_confidence": p.get("extraction_confidence") or "medium",
    }


def old_dims(p: dict) -> str:
    sc = p.get("scores") or {}
    parts = []
    for d in ("pushback", "boyd_register", "receipt", "consequence", "hook_strength"):
        if d in sc:
            parts.append(f"{d[:4]}{sc[d].get('score')}")
    return " ".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("keys", nargs="+")
    ap.add_argument("--out")
    ap.add_argument("--full-context", action="store_true", help="give the model the whole docket transcript instead of the case span (+45 s)")
    ap.add_argument("--package", action="store_true", help="also run the packaging stage (title/quote/description) on every case that scores MAKE or HOLD")
    a = ap.parse_args()

    cfg = load_config()
    an = Analyzer(cfg)
    conn = sqlite3.connect(str(ROOT / "state" / "pipeline.db"))
    rows, blocks = [], []
    for key in a.keys:
        p = load_case(conn, key)
        vid = p["_video_id"]
        tp = ROOT / "work" / vid / f"{vid}.transcript.json"
        if not tp.exists():
            print(f"!! {key}: no transcript on disk ({tp})"); continue
        tr = Transcript.from_json(tp.read_text(encoding="utf-8"))
        meta = {"title": f"docket {vid}", "docket_date": "historical", "url": f"https://www.youtube.com/watch?v={vid}"}
        t0 = time.time()
        scored = an.score(tr, [stage1_view(p)], meta, full_context=a.full_context)
        secs = round(time.time() - t0)
        if not scored:
            print(f"!! {key}: scorer returned nothing"); continue
        c = scored[0]
        ed = c.get("editorial") or {}
        old_dec = "eligible" if p.get("eligible") else (p.get("ineligible_reason") or "ineligible")
        rows.append({
            "case": f"{p.get('defendant_name','?')} ({key})",
            "old": f"{p.get('_old_total') if p.get('_old_total') is not None else p.get('total_score')} / {old_dec} [{old_dims(p)}]",
            "new": f"{c['total_score']:g}",
            "decision": c["decision"] + ("" if ed.get("gate_pass") else " (gate: " + ", ".join(ed.get("gate_failures") or []) + ")"),
            "angle": ed.get("story_angle", ""),
            "moment": ed.get("money_moment", ""),
            "title": (ed.get("title_angles") or [""])[0],
            "why": ed.get("why_viewer_cares", ""),
            "secs": secs,
        })
        blocks.append(f"### {p.get('defendant_name','?')} — {key}  ({(p['end_s']-p['start_s'])/60:.1f} min, {secs}s)\n\n```\n{editorial.rationale_block(c)}\n```\n")
        print(f"[{key}] old {rows[-1]['old']} -> new {c['total_score']:g} {c['decision']}  ({secs}s)")
        if a.package and c["decision"] in ("MAKE", "HOLD"):
            t1 = time.time()
            pkg = an.package(tr, c, meta, cfg.get("spec_version", "1.1.0"))
            flags = editorial.title_flags(pkg["longform_title"])
            qflags = editorial.quote_flags(pkg["thumbnail_quote"])
            overlap = editorial.quote_repeats_title(pkg["thumbnail_quote"], pkg["longform_title"])
            rows[-1]["title"] = pkg["longform_title"]
            blocks.append(
                "PACKAGING (package_post " + an.prompt_versions.get("package_post", "?") + f", {round(time.time()-t1)}s)\n\n"
                f"- longform_title: {pkg['longform_title']}  [{len(pkg['longform_title'])} chars, family {editorial.title_family(pkg['longform_title']) or 'unrecognised'}]"
                + (f"\n  flags: {flags}" if flags else "") + "\n"
                f"- short_title: {pkg['short_title']}\n"
                f"- thumbnail_quote: {pkg['thumbnail_quote']}  (yellow: {pkg['thumbnail_quote_yellow']})"
                + (f"  flags: {qflags}" if qflags else "") + (f"  REPEATS TITLE" if overlap else "  complements title") + "\n"
                f"- hook_line: {pkg['hook_line']}  verified={pkg.get('hook_verified')}\n"
                f"- title_support_quote: {pkg['title_support_quote']}\n"
                f"- guilt_posture_check: {pkg['guilt_posture_check']}\n"
                f"- summary:\n\n{pkg['summary']}\n\n"
                f"- packaging_rationale:\n\n{pkg['packaging_rationale']}\n"
            )
            print(f"    packaged: {pkg['longform_title']!r} | quote {pkg['thumbnail_quote']!r}")

    md = ["| CASE | OLD SCORE / DECISION | NEW | NEW DECISION | STORY ANGLE | MONEY MOMENT | PROPOSED TITLE | WHY |",
          "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append("| " + " | ".join(str(r[k]).replace("|", "/").replace("\n", " ") for k in
                                    ("case", "old", "new", "decision", "angle", "moment", "title", "why")) + " |")
    out = "\n".join(md) + "\n\n" + "\n".join(blocks)
    print("\n" + out)
    if a.out:
        Path(a.out).write_text(f"# Editorial eval — {editorial.RULESET} — {time.strftime('%Y-%m-%d %H:%M')}\n\n" + out, encoding="utf-8")
        print(f"\nwritten {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
