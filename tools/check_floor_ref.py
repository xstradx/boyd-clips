# -*- coding: utf-8 -*-
"""No floor NUMBER may be stated as current in prose. Print it or don't say it.

2026-09-03. `~/.claude/skills/boyd-thumbnail/references/floor.md` published a
table of "the floor" that SKILL.md cited as the authority. Measured against
`config/quality_floor.json`, every row of it was wrong, and two were the exact
shape of Nathan's two standing complaints:

    metric        actually measured     the file claimed
    grain_hf      0.9 - 1.7             min 23.3        -> 15-25x too much = "cheap"
    skin_chroma   min 19.1              MAX 18.6        -> cap BELOW the floor = "washed"

A number copied into prose cannot be re-measured. It rots silently and is then
quoted back with authority, which is worse than having no reference at all. His
instruction, 2026-09-03: *"if there's something in the instructions that you know
is wrong and ESPECIALLY if I spend DAYS telling you it's wrong then maybe it would
be smart to undo whatever's causing and delete it"*.

THE INVARIANT: in a scanned document, a floor metric name may not appear next to
a number outside an explicitly fenced historical block. Current floor numbers come
from `tools/floor_measure.py --check`, never from prose.

A historical block is fenced like this, and is skipped:

    <!-- floor-ref:historical -->
    ...a table of numbers that are documented as WRONG...
    <!-- /floor-ref:historical -->

A markdown section whose heading matches HISTORICAL_HEADING is also skipped, so
the "why this file no longer carries a table" section can keep the evidence.

    python tools/check_floor_ref.py
    python tools/check_floor_ref.py --selftest
"""
from __future__ import annotations

import argparse
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SKILL = os.path.join(os.path.expanduser("~"), ".claude", "skills", "boyd-thumbnail")

SCAN = [
    os.path.join(SKILL, "references", "floor.md"),
    os.path.join(SKILL, "references", "derivations.md"),
    os.path.join(SKILL, "SKILL.md"),
    os.path.join(ROOT, "CLAUDE.md"),
]

# the metric names that live in config/quality_floor.json, plus the prose spellings
METRICS = [
    r"grain(?:\s*\(hf\s*sd\))?(?:_hf)?",
    r"skin\s*chroma|skin_chroma",
    r"separation\s*dL|separation_dL",
    r"subject\s*L\*?|subject_L",
    r"background\s*L\*?|background_L",
    r"contrast\s*sd|contrast_sd",
    r"face\s*blowout|face_blowout(?:_pct)?",
]
_METRIC_RE = re.compile("|".join(f"(?:{m})" for m in METRICS), re.I)
# a claim = metric name, then within 60 chars a bare number (allow -, %, decimals)
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?\s*%?")

HISTORICAL_HEADING = "no longer carries a table"
FENCE_OPEN = "<!-- floor-ref:historical -->"
FENCE_CLOSE = "<!-- /floor-ref:historical -->"


def _strip_historical(text: str) -> str:
    """Remove fenced blocks and the documented-history section."""
    out = []
    fenced = False
    in_hist = False
    for line in text.splitlines():
        low = line.lower()
        if FENCE_OPEN in line:
            fenced = True
            continue
        if FENCE_CLOSE in line:
            fenced = False
            continue
        if low.startswith("#"):
            in_hist = HISTORICAL_HEADING in low
        if fenced or in_hist:
            continue
        out.append(line)
    return "\n".join(out)


def offenders(text: str):
    """Lines that state a floor metric next to a number, outside history."""
    bad = []
    for i, line in enumerate(_strip_historical(text).splitlines(), 1):
        if line.strip().startswith(">"):          # a quote of him is not a claim
            continue
        for m in _METRIC_RE.finditer(line):
            tail = line[m.end():m.end() + 60]
            num = _NUM_RE.search(tail)
            if num:
                bad.append((i, line.strip()[:110], m.group(0).strip(), num.group(0)))
                break
    return bad


def check(paths=None, verbose=True) -> bool:
    paths = paths or SCAN
    ok = True
    for p in paths:
        if not os.path.isfile(p):
            if verbose:
                print(f"  ....  {os.path.basename(p)} not on this machine, skipped")
            continue
        bad = offenders(open(p, encoding="utf-8", errors="replace").read())
        if bad:
            ok = False
            if verbose:
                print(f"  FAIL  {p}")
                for ln, txt, met, num in bad:
                    print(f"          line {ln}: '{met}' stated with {num}  ->  {txt}")
        elif verbose:
            print(f"  PASS  {os.path.basename(p)}  states no floor number as current")
    if verbose:
        print("FLOOR_REF_OK" if ok else "FLOOR_REF_FAIL")
    return ok


# the real table that shipped in floor.md until 2026-09-03 - the known-bad control
_OLD_TABLE = """# The floor

    separation dL   min -22.8   median -10.2   max 5.9
    subject L*      min 99.0   median 109.1
    background L*   min 108.7  median 120.0
    grain (hf sd)   min 23.3   median 25.2
    contrast sd     min 75.2   median 76.6
    skin chroma     max 18.6  (corpus median 17.8)
    face blowout    max 14.7%
"""
_GOOD = """# The floor

Print them, do not read them from prose:

    python tools/floor_measure.py --check

## Why this file no longer carries a table

    grain_hf   0.9 - 1.7   the file used to claim min 23.3
    skin chroma  min 19.1  the file used to claim max 18.6
"""


def selftest() -> int:
    ok = True
    print("R41-class invariant: floor numbers are printed, never written into prose")
    bad = offenders(_OLD_TABLE)
    if not bad:
        ok = False
        print("    !! the CONTROL passed - the checker cannot see the table that shipped")
    else:
        print(f"    ok   the shipped-and-wrong table is caught ({len(bad)} claims)")
    good = offenders(_GOOD)
    if good:
        ok = False
        print(f"    !! the replacement file is flagged - history section not exempt: {good[:2]}")
    else:
        print("    ok   a file whose numbers are all inside the history section passes")
    fenced = offenders(f"# x\n{FENCE_OPEN}\ngrain_hf min 23.3\n{FENCE_CLOSE}\nplain text\n")
    if fenced:
        ok = False
        print("    !! an explicitly fenced historical block was not exempt")
    else:
        print("    ok   an explicitly fenced block is exempt")
    leak = offenders("# current\n\nskin chroma max 18.6 is the ceiling.\n")
    if not leak:
        ok = False
        print("    !! a floor number outside any history section was NOT caught")
    else:
        print("    ok   a floor number stated as current is caught")
    print("FLOOR_REF_SELFTEST_OK" if ok else "FLOOR_REF_SELFTEST_FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("paths", nargs="*")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    return 0 if check(a.paths or None) else 1


if __name__ == "__main__":
    sys.exit(main())
