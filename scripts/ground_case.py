"""Ground a stored case's timestamps to its own quotes and save the row.

    python scripts/ground_case.py <case_key>

The scorer's quotes are verbatim; its timestamps are not (Rodriguez,
2026-09-06). analyze.ground_case_times now runs inside the scorer; this
applies the same grounding to a row that was scored before it existed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from boydclips import analyze                         # noqa: E402
from boydclips.pipeline import Pipeline               # noqa: E402
from boydclips.transcribe import Transcript           # noqa: E402


def main() -> int:
    key = sys.argv[1]
    vid = key.split(":")[0]
    pipe = Pipeline()
    case = pipe.store.get_case(key)
    if case is None:
        print(f"no row {key}")
        return 1
    tr = Transcript.from_json((pipe.work / vid / f"{vid}.transcript.json").read_text(encoding="utf-8"))
    notes = analyze.ground_case_times(case, tr.words)
    for n in notes:
        print("grounded:", n)
    if notes:
        pipe.store.save_case(vid, case, case.get("rank"))
        print("saved", key)
    else:
        print("nothing to move")
    pipe.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
