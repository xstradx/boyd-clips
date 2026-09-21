"""Verify a four-hearing PRODUCER BRAIN V1 evaluation batch offline."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from boydclips.producer_brain import load_json  # noqa: E402
from verify_producer_brain_v1 import verify  # noqa: E402


def discover_cases(batch_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    cases: list[tuple[Path, dict[str, Any]]] = []
    for input_path in sorted(batch_dir.glob("*/input.json")):
        case_dir = input_path.parent
        plan_path = case_dir / "plan.json"
        if plan_path.is_file():
            cases.append((case_dir, load_json(plan_path)))
    return cases


def voice_errors(plan: Mapping[str, Any], label: str) -> list[str]:
    text = str(plan["sample_intro_narration"]["text"]).strip()
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
    errors: list[str] = []
    if not 3 <= len(sentences) <= 5:
        errors.append(f"{label}: intro must use 3-5 spoken sentences, got {len(sentences)}")
    if text.lower().startswith("at this hearing"):
        errors.append(f"{label}: intro opens like a legal summary")
    if any(len(sentence.split()) > 35 for sentence in sentences):
        errors.append(f"{label}: intro contains a sentence over 35 words")
    return errors


def diversity_errors(cases: Sequence[tuple[Path, Mapping[str, Any]]]) -> list[str]:
    errors: list[str] = []
    if len(cases) != 4:
        errors.append(f"batch: expected exactly four cases, found {len(cases)}")
        return errors
    plans = [plan for _, plan in cases]
    case_ids = [str(plan["case_source"]["internal_case_id"]) for plan in plans]
    video_ids = {str(plan["case_source"]["video_id"]) for plan in plans}
    proceeding_types = {str(plan["case_source"]["proceeding_type"]) for plan in plans}
    decisions = [str(plan["video_decision"]["decision"]) for plan in plans]
    short_decisions = [str(plan["short_plan"]["decision"]) for plan in plans]
    if len(set(case_ids)) != 4:
        errors.append("batch: internal case ids must be unique")
    if len(video_ids) < 3:
        errors.append("batch: hearings must span at least three source dockets")
    if len(proceeding_types) < 3:
        errors.append("batch: hearings must span at least three proceeding types")
    if "SKIP" not in decisions:
        errors.append("batch: at least one hearing must earn SKIP")
    if not any(decision in {"MAKE", "HOLD"} for decision in decisions):
        errors.append("batch: at least one hearing must remain viable")
    if "MAKE" not in short_decisions:
        errors.append("batch: Shorts Brain must find at least one viable Short")
    if not any(decision in {"HOLD", "SKIP"} for decision in short_decisions):
        errors.append("batch: Shorts Brain must refuse or hold at least one Short")
    return errors


def self_test() -> list[str]:
    def fake(case_id: str, video_id: str, proceeding: str, decision: str, short_decision: str = "MAKE"):
        return Path(case_id), {
            "case_source": {
                "internal_case_id": case_id,
                "video_id": video_id,
                "proceeding_type": proceeding,
            },
            "video_decision": {"decision": decision},
            "short_plan": {"decision": short_decision},
        }

    good = [
        fake("a", "v1", "plea", "MAKE"),
        fake("b", "v2", "sentencing", "MAKE"),
        fake("c", "v3", "motion", "HOLD"),
        fake("d", "v1", "status", "SKIP", "HOLD"),
    ]
    failures: list[str] = []
    if diversity_errors(good):
        failures.append("known-good diversity control failed")
    controls = [
        (good[:3], "exactly four"),
        (good[:-1] + [fake("a", "v1", "status", "SKIP")], "unique"),
        ([fake(str(i), "v1", "plea", "SKIP" if i == 3 else "MAKE") for i in range(4)], "three source"),
        ([fake(str(i), f"v{i}", "plea", "SKIP" if i == 3 else "MAKE") for i in range(4)], "three proceeding"),
        ([fake(str(i), f"v{i}", f"p{i}", "MAKE") for i in range(4)], "earn SKIP"),
        ([fake(str(i), f"v{i}", f"p{i}", "SKIP" if i == 3 else "MAKE", "MAKE") for i in range(4)], "refuse or hold"),
    ]
    for candidate, marker in controls:
        got = diversity_errors(candidate)
        if not any(marker in error for error in got):
            failures.append(f"negative control did not fail on {marker!r}: {got}")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch_dir", type=Path)
    parser.add_argument("--check-diversity", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    cases = discover_cases(args.batch_dir)
    errors: list[str] = []
    for case_dir, plan in cases:
        errors.extend(
            f"{case_dir.name}: {error}"
            for error in verify(
                case_dir / "input.json",
                case_dir / "plan.json",
                case_dir / "REPORT.md",
            )
        )
        errors.extend(voice_errors(plan, case_dir.name))
    if len(cases) != 4:
        errors.append(f"batch: expected exactly four complete case directories, found {len(cases)}")
    if args.check_diversity:
        errors.extend(diversity_errors(cases))
    if args.self_test:
        errors.extend(self_test())
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("PRODUCER_BRAIN_DIVERSITY_OK" if args.check_diversity else "PRODUCER_BRAIN_BATCH_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
