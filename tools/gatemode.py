# -*- coding: utf-8 -*-
"""ADVISORY GATES. Nathan, 2026-09-03: *"I need you to not anchor all these rules
down so hard because u think that's what's causing this because you literally
know what's good and what's not"*.

Asked to choose what to do with the rule stack, he picked: **delete what is
disproven, and convert every remaining rule from a build-refusing gate to a
printed warning, so nothing can silently block a build again.**

The word that matters in his sentence is *silently*. This module does not make
gates quiet - it makes them LOUD and non-fatal. A gate that would have killed a
build now prints, records itself, and lets the build finish, and the run ends
with a block listing everything that would have been refused. Judgement then
belongs to whoever looks at the picture, which is the point.

    BOYD_GATES=advise   (DEFAULT)  gates warn, builds complete
    BOYD_GATES=refuse              the old behaviour, gates kill the build

Two classes are deliberately distinguished, because "advisory" is right for
taste and wrong for a broken file:

    kind="taste"    grade envelopes, pace floors, ink budgets, house look.
                    Always advisory under 'advise'. These are the ones that
                    have been wrong.
    kind="defect"   the output is BROKEN, not merely off-taste: a severed
                    matte, a duplicated face, audio that does not match video,
                    a missing file, a cut mid-word. Still advisory under
                    'advise' (he asked for that), but printed as DEFECT so it
                    can never be mistaken for a taste note - and listed first
                    in the summary.

Nothing here silences a gate, changes a threshold, or edits a rule. It only
decides whether a failure stops the program.
"""
from __future__ import annotations

import os

_RECORD = []


def mode() -> str:
    m = (os.environ.get("BOYD_GATES") or "advise").strip().lower()
    return m if m in ("advise", "refuse") else "advise"


def advisory() -> bool:
    return mode() == "advise"


def note(gate: str, detail: str = "", kind: str = "taste") -> bool:
    """Record a gate failure. Returns True if the caller should STOP.

    Under 'advise' this always returns False - the build continues - after
    printing the failure so it is on the record.
    """
    kind = "defect" if kind == "defect" else "taste"
    _RECORD.append((gate, detail, kind))
    tag = "DEFECT " if kind == "defect" else "WARN   "
    if advisory():
        print(f"  {tag} {gate}  {detail}")
        print(f"         (advisory - BOYD_GATES=refuse to make this stop the build)")
        return False
    print(f"  REFUSED {gate}  {detail}")
    return True


def summary(label: str = "") -> None:
    """Print everything that would have been refused. Call at the end of a build."""
    if not _RECORD:
        return
    defects = [r for r in _RECORD if r[2] == "defect"]
    taste = [r for r in _RECORD if r[2] == "taste"]
    head = f"GATES ADVISORY{(' - ' + label) if label else ''}: "
    print(f"\n{head}{len(_RECORD)} would have refused this build "
          f"({len(defects)} defect, {len(taste)} taste)")
    for gate, detail, _ in defects:
        print(f"  DEFECT  {gate}  {detail}")
    for gate, detail, _ in taste:
        print(f"  taste   {gate}  {detail}")
    print("  Look at the output before shipping it. BOYD_GATES=refuse restores the veto.")


def reset() -> None:
    _RECORD.clear()


def record():
    return list(_RECORD)


def selftest() -> int:
    ok = True
    reset()
    os.environ["BOYD_GATES"] = "advise"
    if note("X test", "a taste failure") is not False:
        ok = False; print("  !! advise mode told the caller to stop")
    if note("Y test", "a broken file", kind="defect") is not False:
        ok = False; print("  !! advise mode stopped on a defect")
    if len(record()) != 2:
        ok = False; print("  !! failures were not recorded")
    reset()
    os.environ["BOYD_GATES"] = "refuse"
    if note("Z test", "a taste failure") is not True:
        ok = False; print("  !! refuse mode did NOT tell the caller to stop")
    reset()
    os.environ.pop("BOYD_GATES", None)
    if mode() != "advise":
        ok = False; print("  !! default is not 'advise'")
    if note("W test", "default path") is not False:
        ok = False; print("  !! default path stopped the build")
    reset()
    print("  ok   advise never stops, refuse always stops, default is advise")
    print("GATEMODE_SELFTEST_OK" if ok else "GATEMODE_SELFTEST_FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    sys.exit(selftest())
