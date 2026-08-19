"""CLI wrapper around boydclips.censor -- censor a text/subtitle file.

The implementation moved into the package (src/boydclips/censor.py) so the
renderer and packaging stage can import it. This file stays because
spec/CONTENT_SPEC.md documents `scripts/censor.py` as the entry point.

    python scripts/censor.py in.srt out.srt
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from boydclips.censor import _PATTERN, censor, has_profanity  # noqa: E402,F401


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    src, dst = Path(argv[1]), Path(argv[2])
    raw = src.read_text(encoding="utf-8")
    out = censor(raw)
    hits = len(_PATTERN.findall(raw))
    dst.write_text(out, encoding="utf-8")
    print(f"{hits} term(s) censored -> {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
