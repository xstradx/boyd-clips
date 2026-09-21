"""Re-run thumbnail.mode direct_gen for a finished review directory.

    python scripts/thumb_direct_rerun.py out/review/<date>_<vid>_<start>

Used when the daily route fell back to the legacy compositor because the
Codex/ChatGPT usage limit refused the image session (2026-09-06). Rebuilds
the same case dict the route builds (store row + the packaging already in
the manifest + the cached source section) and, on an accepted A control,
records the direct_gen result under outputs.thumbnail, keeping the fallback
image under outputs.thumbnail_legacy. Nothing else in the manifest changes.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from boydclips import thumbnail                 # noqa: E402
from boydclips.pipeline import Pipeline         # noqa: E402
from boydclips.artifacts import require_thumbnail  # noqa: E402


def main() -> int:
    review = Path(sys.argv[1]).resolve()
    man_path = review / "manifest.json"
    man = json.loads(man_path.read_text(encoding="utf-8"))
    case_key = man.get("case_key")
    if not case_key:
        m = re.search(r"_([A-Za-z0-9_-]{11})_(\d+)$", review.name)
        case_key = f"{m.group(1)}:{m.group(2)}"
    vid, start = case_key.split(":")

    pipe = Pipeline()
    case = pipe.store.get_case(case_key)
    if case is None:
        print(f"no store row for {case_key}")
        return 1
    pkg = man.get("packaging") or {}
    work = pipe.work / vid
    sections = sorted(work.glob(f"{vid}_{start}_*.mp4"))
    if not sections:
        print(f"no cached source section under {work}")
        return 1
    source = sections[-1]
    offset = float(re.search(r"_(\d+)-\d+\.mp4$", source.name).group(1))
    tcfg = pipe.cfg.get("packaging.thumbnail", {})
    print(f"case {case_key}  source {source.name}  offset {offset:.0f}s  mode {tcfg.get('mode')}")

    res = thumbnail.build_direct(source, offset, case, pkg, review, tcfg)
    if not res:
        print("direct_gen produced no accepted A control; manifest unchanged")
        pipe.close()
        return 2
    require_thumbnail(Path(res["file_path"]))
    outs = man.setdefault("outputs", {})
    if outs.get("thumbnail") and outs["thumbnail"].get("mode") != "direct_gen":
        outs["thumbnail_legacy"] = outs["thumbnail"]
    outs["thumbnail"] = res
    man_path.write_text(json.dumps(man, indent=2, ensure_ascii=False), encoding="utf-8")
    print("direct_gen accepted:", json.dumps(res, indent=2))
    pipe.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
