# -*- coding: utf-8 -*-
"""Garcia (dAKO7myCd-g:8340) A/B thumbnail set, generated with gpt-5.6-sol.

Nathan, 2026-09-07: run the A/B test on the posted long-form with
"30 DAYS IN THE BEXAR COUNTY JAIL" and a REGENERATED "WHO TASED YOU?"
("regenerate that one with 5.6 sol with its original assets"), plus a
Matrix red-pill/blue-pill concept - upper third of the defendant on the
left, Judge Boyd on the right holding out both hands.

Writes to out/review/<dir>/thumb_ab_sol so the LIVE thumbnail and the
Sep-6 A/B/C set are never touched. Reads the original extracted assets
from a copy of the Sep-6 thumbwork dir, so those originals are preserved.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))

import thumb_direct as TD  # noqa: E402

KEY = "dAKO7myCd-g_8340_8296-9488"
REVIEW = ROOT / "out" / "review" / "2024-03-07_dAKO7myCd-g_8340"
SOURCE = ROOT / "work" / "dAKO7myCd-g" / f"{KEY}.mp4"
ASSETS = Path(r"D:/Boyd Clips/thumbwork/dAKO7myCd-g_8340_8296-9488_solab")
OFFSET = 8296.0

# The hearing, then the art direction for the three families. Both reach the
# model under THE STORY; `prop` carries the family-C device.
STORY = (
    "This is a sentencing hearing in the 187th District Court in Bexar County, Texas. "
    "A former Bexar County jail deputy pled guilty to tampering with a government record. "
    "The state opposed deferred adjudication, telling Judge Boyd that cadets he supervised "
    "and trained at the jail had been tased when they did not consent. Judge Boyd asks him "
    "repeatedly for a single name of anyone else who was tasing cadets and he will not give "
    "one. She then puts a choice to him directly: four years deferred adjudication with 30 "
    "days in the Bexar County Jail today in handcuffs, or a guilty conviction on his record. "
    "Which do you choose. He takes the conviction.\n\n"
    "ART DIRECTION - one caption per family, use exactly these pairings:\n"
    "  A: caption \"WHO TASED YOU?\" - the defendant alone, tight and clean, courtroom behind him.\n"
    "  B: caption \"30 DAYS OR A CONVICTION\" - the defendant and Judge Boyd, her question hanging.\n"
    "  C: caption \"WHICH DO YOU CHOOSE?\" - the red pill / blue pill concept described under Prop idea.\n"
)

PROP = (
    "Family C only. A red-pill / blue-pill choice, in the style of a green digital-code "
    "science-fiction scene - build the look yourself, do NOT copy any film still, poster, "
    "character or logo. Composition: the LEFT third of the frame is the upper third of the "
    "defendant (head and shoulders, light blue dress shirt exactly as in the reference - he is "
    "NOT in a jail uniform, facing right toward her, uncertain). "
    "The RIGHT of the frame is Judge Boyd in her black robe, leaning slightly forward, both "
    "hands held out toward him, open palms up - one palm holds a single glowing RED pill, the "
    "other a single glowing BLUE pill. The two pills are the brightest points in the frame. "
    "Behind them the courtroom is dark with faint green falling code. The red pill reads as "
    "jail, the blue pill as the conviction; do not label them with words. Keep both faces "
    "exactly like the references. Caption \"WHICH DO YOU CHOOSE?\" clear of both faces."
)


def case_dict() -> dict:
    pkg = (ROOT / "out" / "batch_2026-09-06" / "PACKAGE_2026-09-07_garcia.txt").read_text(
        encoding="utf-8", errors="replace")
    desc = pkg.split("title:", 1)[1].split("\n", 1)[1] if "title:" in pkg else pkg
    return {
        "_key": KEY,
        "video": str(SOURCE),
        "offset": OFFSET,
        "plate_t": 9215.5,          # the cold-open / hook moment the route used
        "call_t": 8296.0,
        "case_from": 8296.0,
        "case_to": 9488.0,
        "transcript": "work/dAKO7myCd-g/dAKO7myCd-g.transcript.json",
        # allowed_lines = [white+yellow, kicker] + quoted strings inside titles
        "white": "WHICH DO YOU CHOOSE?",
        "yellow": "",
        "kicker": "WHO TASED YOU?",
        "defendant": "Andrew Garcia",
        "note": desc[:4000],
        "story_angle": STORY,
        "hearing_date": "2024-03-07",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gpt-5.6-sol")
    ap.add_argument("--effort", default="high")
    ap.add_argument("--budget", type=int, default=9)
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--dry-run", dest="dry_run", action="store_true")
    a = ap.parse_args()

    if not SOURCE.exists():
        print(f"missing source section: {SOURCE}")
        return 1
    if not ASSETS.exists():
        print(f"missing asset copy: {ASSETS}")
        return 1

    out_dir = REVIEW / "thumb_ab_sol"
    work = Path(r"D:/Boyd Clips/thumbwork") / KEY / "sol_ab"
    args = SimpleNamespace(
        assets=ASSETS,          # gather_assets does Path arithmetic on this
        story=STORY,
        money_moment="Who tased you?",
        titles=['Judge Boyd gave him "30 DAYS OR A CONVICTION" and made him pick'],
        prop=PROP,
        dry_run=a.dry_run,
    )
    cfg = {"model": a.model, "effort": a.effort, "budget": a.budget, "retries": a.retries}

    c = case_dict()
    if a.dry_run:
        work.mkdir(parents=True, exist_ok=True)
        brief = TD.build_brief(c, args)
        assets = TD.gather_assets(c, ASSETS)
        prompt = TD.build_prompt(brief, assets.attachments(), dict(TD.DEFAULTS, **cfg))
        (work / "brief.json").write_text(json.dumps(brief, indent=2, ensure_ascii=False), encoding="utf-8")
        (work / "prompt.txt").write_text(prompt, encoding="utf-8")
        print(json.dumps(brief, indent=2, ensure_ascii=False)[:3000])
        print(f"\n[dry-run] prompt -> {work / 'prompt.txt'}  ({len(prompt)} chars)")
        return 0

    man = TD.run_case(KEY, out_dir, work, args, cfg=cfg, case_dict=c)
    print(json.dumps({k: man.get(k) for k in
                      ("finals", "complete", "control_present", "images_generated_total",
                       "retries_used", "contact_sheet")}, indent=2, ensure_ascii=False))
    return 0 if man.get("finals") else 2


if __name__ == "__main__":
    raise SystemExit(main())
