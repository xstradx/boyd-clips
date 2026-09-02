# -*- coding: utf-8 -*-
"""Every build gate must PASS the five builds he accepted as the floor.

WHY THIS FILE EXISTS
Measured 2026-09-01: `verify_build.py` run over the accepted five rejected
three of them (CARTHIEF, SANCHEZ, THOMPSON failed E and I; MONKEY failed F, J
and K). Every gate had been validated one way only - against a constructed
known-bad control - and never against the builds Nathan called *"the floor and
minimum quality we should put out"* (2026-08-31). A gate that rejects the floor
is not strict, it is mis-tuned, and the next good build would have failed it.

This runs `verify_build.run` over `config/quality_floor.json["files"]` and
compares the failures to `["gate_disagreements"]`:

    undeclared failure   a gate rejects a floor build nobody has looked at
                         -> FLOOR_GATES_FAIL. Retune the gate to the measured
                            band of the five (keep its known-bad control
                            failing) or, if the build really is defective,
                            declare it with the numbers and take it to Nathan.
    declared, still fails    known, waiting on his call - reported, not fatal
    declared, now passes     stale declaration -> FLOOR_GATES_FAIL, remove it
    passes, undeclared       the normal state

    python tools/check_floor_gates.py             # the audit (~2 min: YuNet x5)
    python tools/check_floor_gates.py --selftest  # prove it can fail both ways
"""
import io
import json
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
FLOOR = os.path.join(ROOT, "config", "quality_floor.json")
MEDIA = "D:/Boyd Clips"


def _load(path=FLOOR):
    return json.load(io.open(path, encoding="utf-8"))


def _letter(name):
    """'E matte softness' -> 'E'; 'E alpha stretch' -> 'E'; '0 output exists' -> '0'."""
    return name.split()[0]


def audit(floor=None, run=None, verbose=True):
    """Returns (ok, problems, table). `run` is injectable for the selftest."""
    floor = floor or _load()
    if run is None:
        import verify_build
        run = verify_build.run
    files = floor.get("files") or {}
    declared = {k: v for k, v in (floor.get("gate_disagreements") or {}).items() if k != "note"}
    problems, table = [], []
    for case in floor.get("approved", []):
        rel = files.get(case)
        if not rel:
            problems.append(f"NO FILE      {case}: approved but quality_floor.json['files'] does not name its file")
            continue
        out = os.path.join(MEDIA, rel)
        work = os.path.dirname(out)
        if not os.path.exists(out):
            problems.append(f"MISSING      {case}: {out} is not on disk")
            continue
        _, results = run(work, out, verbose=False)
        failed = {_letter(n): d for n, ok, d in results if ok is False}
        dec = declared.get(case, {})
        for g, det in sorted(failed.items()):
            if g in dec:
                table.append((case, g, "DECLARED", det))
            else:
                table.append((case, g, "UNDECLARED", det))
                problems.append(f"UNDECLARED   {case} gate {g}: {det}")
        for g in sorted(dec):
            if g not in failed:
                table.append((case, g, "STALE-DECL", "declared as a disagreement but the gate passes now"))
                problems.append(f"STALE DECL   {case} gate {g}: declared, now passes - remove the entry")
        if not failed and not dec:
            table.append((case, "-", "PASS", "every gate"))
    if verbose:
        for case, g, state, det in table:
            print(f"  {state:10} {case:9} {g:2} {det[:96]}")
        for p in problems:
            print("  " + p)
        print("FLOOR_GATES_OK" if not problems else "FLOOR_GATES_FAIL")
    return (not problems), problems, table


def selftest():
    """The checker must fail on an undeclared rejection and on a stale
    declaration, and pass when the declared set equals the measured set. The
    gate runner is faked so this costs nothing and cannot drift with the
    thumbwork on disk."""
    ok = True

    def check(label, got, want, why=""):
        nonlocal ok
        hit = (got == want)
        ok &= hit
        print(f"  {'OK  ' if hit else 'MISS'}  {label:52} -> {got} (want {want})")
        if not hit and why:
            print(f"        {why}")

    real = _load()
    # any floor file that exists on D:, so the on-disk check passes for the fakes
    some = next(iter((real.get("files") or {}).values()), None)
    base = {"approved": ["A", "B"], "files": {"A": some, "B": some}}

    def fake(verdicts):
        def run(work, out, verbose=False):
            # both cases point at the same file; tell them apart by call order
            run.calls += 1
            case = base["approved"][run.calls - 1]
            res = [(f"{g} fake", (g not in verdicts.get(case, {})), verdicts.get(case, {}).get(g, "fine"))
                   for g in ("E", "F", "I", "J", "K")]
            return all(r[1] for r in res), res
        run.calls = 0
        return run

    # 1. gate rejects a floor build, nothing declared -> FAIL
    fl = dict(base, gate_disagreements={})
    got, probs, _ = audit(fl, fake({"A": {"J": "blowout 17.8%"}}), verbose=False)
    check("undeclared rejection fails", got, False, "; ".join(probs))
    check("  ...and names the case and gate", any("A gate J" in p for p in probs), True)
    # 2. the same rejection, declared -> OK (reported, not fatal)
    fl = dict(base, gate_disagreements={"A": {"J": "waiting on Nathan"}})
    got, probs, table = audit(fl, fake({"A": {"J": "blowout 17.8%"}}), verbose=False)
    check("declared rejection passes", got, True, "; ".join(probs))
    check("  ...and is still reported", any(t[2] == "DECLARED" for t in table), True)
    # 3. declared but the gate passes now -> FAIL (stale)
    fl = dict(base, gate_disagreements={"A": {"J": "waiting on Nathan"}})
    got, probs, _ = audit(fl, fake({}), verbose=False)
    check("stale declaration fails", got, False, "; ".join(probs))
    # 4. approved case with no file named -> FAIL
    fl = {"approved": ["A"], "files": {}, "gate_disagreements": {}}
    got, probs, _ = audit(fl, fake({}), verbose=False)
    check("approved case without a file fails", got, False, "; ".join(probs))
    # 5. the real floor file names a file for every approved case
    missing = [c for c in real["approved"] if c not in (real.get("files") or {})]
    check("real floor names a file for every approved case", missing, [])
    absent = [c for c, rel in (real.get("files") or {}).items()
              if not os.path.exists(os.path.join(MEDIA, rel))]
    check("every named floor file is on disk", absent, [])
    print("SELFTEST_PASS check_floor_gates" if ok else "SELFTEST_FAIL check_floor_gates")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    good, _, _ = audit()
    sys.exit(0 if good else 1)
