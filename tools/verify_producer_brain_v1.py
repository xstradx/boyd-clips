"""Verify PRODUCER BRAIN V1 artifacts without network, model, or media calls."""
from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from boydclips.producer_brain import (  # noqa: E402
    load_json,
    load_transcript,
    render_report,
    validate_plan,
)


DEFAULT_MATERIAL = ROOT / "docs" / "producer_brain_v1" / "real_case_input.json"
DEFAULT_PLAN = ROOT / "docs" / "producer_brain_v1" / "real_case_plan.json"
DEFAULT_REPORT = ROOT / "docs" / "producer_brain_v1" / "REAL_CASE_REPORT.md"


def verify(material_path: Path, plan_path: Path, report_path: Path) -> list[str]:
    material = load_json(material_path)
    transcript = load_transcript(material)
    plan = load_json(plan_path)
    errors = validate_plan(plan, material, transcript)
    if not report_path.is_file():
        errors.append(f"report missing: {report_path}")
    else:
        expected = render_report(plan).replace("\r\n", "\n").rstrip() + "\n"
        actual = report_path.read_text(encoding="utf-8").replace("\r\n", "\n").rstrip() + "\n"
        if actual != expected:
            errors.append("report does not exactly match the validated plan")
    return errors


def self_test() -> list[str]:
    material = load_json(DEFAULT_MATERIAL)
    transcript = load_transcript(material)
    plan = load_json(DEFAULT_PLAN)
    failures: list[str] = []
    failures.extend(verify(DEFAULT_MATERIAL, DEFAULT_PLAN, DEFAULT_REPORT))
    if validate_plan(plan, material, transcript):
        failures.append("known-good plan did not pass")

    controls = []
    bad = copy.deepcopy(plan)
    bad["cold_open"]["end_s"] = bad["cold_open"]["start_s"] + 13
    controls.append((bad, "duration must be 5-12 seconds"))

    bad = copy.deepcopy(plan)
    bad["title_angles"][0]["title"] = f"{material['case_source']['defendant_name_internal']} Explains Everything"
    controls.append((bad, "contains defendant name"))

    bad = copy.deepcopy(plan)
    bad["intro_facts"][0]["sources"][0]["quote"] = "this line was never spoken"
    controls.append((bad, "not found in cited transcript range"))

    bad = copy.deepcopy(plan)
    bad["story_arc"]["payoff"]["start_s"] = bad["story_arc"]["setup"]["start_s"] - 1
    controls.append((bad, "must be chronological"))

    bad = copy.deepcopy(plan)
    bad["thumbnail_plan"] = bad["thumbnail_plan"][:2]
    controls.append((bad, "require A confrontation"))

    bad = copy.deepcopy(plan)
    bad["longform_end_cta"]["end_screen_duration_s"] = 20
    controls.append((bad, "must be 5-8 seconds"))

    bad = copy.deepcopy(plan)
    bad["short_plan"]["sequence"][0]["end_s"] += 20
    controls.append((bad, "MAKE duration must be 15-59 seconds"))

    for index, (candidate, marker) in enumerate(controls, start=1):
        got = validate_plan(candidate, material, transcript)
        if not any(marker in error for error in got):
            failures.append(f"negative control {index} was not rejected by {marker!r}: {got}")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("material", nargs="?", type=Path, default=DEFAULT_MATERIAL)
    parser.add_argument("plan", nargs="?", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("report", nargs="?", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    errors = self_test() if args.self_test else verify(args.material, args.plan, args.report)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("PRODUCER_BRAIN_ORACLE_OK" if args.self_test else "PRODUCER_BRAIN_REAL_CASE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
