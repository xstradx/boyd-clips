"""Module boundaries: who owns which output, and who refuses what.

Step 2 of docs/PIPELINE-ARCHITECTURE-AND-LEARNING-LAYER.md §7. A defect should
be attributed to the module that owns it, not guessed at from whichever file a
session happened to open first.

    python tools/modules.py list                 # modules, outputs, owners
    python tools/modules.py verify               # every cited file and gate exists
    python tools/modules.py attribute <text>     # which module owns this gate/word

`verify` is what keeps this honest: it fails if a file moved or if a gate named
here no longer appears anywhere in src/, so the map cannot rot into fiction.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "boydclips"

# Each module: the code it owns, the manifest outputs it produces, and the
# refusals it raises. Refusal strings are checked against src/ by `verify`.
MODULES: dict[str, dict[str, list[str]]] = {
    "case finder": {
        "owns": ["discover.py", "transcribe.py", "analyze.py", "editorial.py", "capfit.py"],
        "outputs": ["source", "case", "scores", "outputs.longform"],
        "refusals": ["TooShortError", "ReadinessError"],
    },
    "intro": {
        "owns": ["narrated_short_intro.py", "cta.py"],
        "outputs": ["short_intro"],
        "refusals": [],
    },
    "short editor": {
        "owns": ["shorts_editor.py", "short_thumbnail.py", "spotlight.py"],
        "outputs": ["outputs.short", "short_editor", "outputs.short.vertical_thumbnail"],
        "refusals": ["captions_from_kept_words", "continuity_gaps", "score_floor",
                     "producer_alignment", "duration_bounds", "payoff_present",
                     "no_mid_word_cuts", "teaser_declared_and_repeated",
                     "no valid mini-story", "ShortPlanError"],
    },
    "thumbnail": {
        "owns": ["thumbnail.py", "thumbnail_copy.py", "thumbnail_visible.py"],
        "outputs": ["outputs.thumbnail", "packaging.packaging_pairs"],
        "refusals": ["thumbnail meaning review", "no A/B/C generated candidates exist",
                     "is not understandable to a blind viewer"],
    },
    "title": {
        "owns": ["metadata.py", "producer_brain.py"],
        "outputs": ["packaging.longform_title", "packaging.short_title", "packaging.tags"],
        "refusals": ["must be written for the Short", "case-specific tag"],
    },
    "publisher": {
        "owns": ["publish.py"],
        "outputs": [],
        "refusals": ["NotImplementedError", "publish"],
    },
}


def _src_text() -> str:
    return "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in SRC.glob("*.py"))


def verify() -> int:
    text = _src_text()
    problems: list[str] = []
    for name, spec in MODULES.items():
        for owner in spec["owns"]:
            if not (SRC / owner).is_file():
                problems.append(f"{name}: owns missing file {owner}")
        for refusal in spec["refusals"]:
            if refusal not in text:
                problems.append(f"{name}: refusal {refusal!r} no longer appears in src/")
    if problems:
        print("modules: FAIL")
        for problem in problems:
            print("  " + problem)
        return 1
    print(f"module-boundaries-ok {len(MODULES)} modules, every owner and gate present")
    return 0


def listing() -> int:
    for name, spec in MODULES.items():
        print(f"{name}")
        print(f"  owns:    {', '.join(spec['owns'])}")
        print(f"  outputs: {', '.join(spec['outputs']) or '(none)'}")
        print(f"  refuses: {', '.join(spec['refusals']) or '(none)'}")
    return 0


def attribute(argv: list[str]) -> int:
    if not argv:
        print("usage: python tools/modules.py attribute <gate-or-word>")
        return 1
    needle = " ".join(argv).lower()
    hits = []
    for name, spec in MODULES.items():
        haystack = " ".join(spec["outputs"] + spec["refusals"] + spec["owns"]).lower()
        if needle in haystack:
            hits.append(name)
    if not hits:
        print(f"no module claims {needle!r}; it is unattributed — investigate before editing")
        return 1
    print(f"{needle!r} -> " + ", ".join(hits))
    return 0


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "list"
    if command == "verify":
        raise SystemExit(verify())
    if command == "attribute":
        raise SystemExit(attribute(sys.argv[2:]))
    raise SystemExit(listing())
