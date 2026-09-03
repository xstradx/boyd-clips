# -*- coding: utf-8 -*-
"""Run every selftest in the repo. One command that proves the checkers work.

Nathan, 2026-08-31: *"Okay but are you gonna make sure it never happens again"*.

The gates in `verify_thumb.py` and `verify_build.py` are what stop a defect
shipping. This is what stops the GATES rotting - because a gate that has
silently stopped being able to fail is worse than no gate, and nothing was
checking that.

It is also the legitimate caller for `verify_thumb_metrics.py`, which is not a
per-build check at all: it re-runs `thumb_metrics` over the seven same-encoder
control files and proves the metric numbers still reproduce and the gates are
still separable. That belongs in a selftest suite, not in a render.

    python tools/selftest_all.py
"""
import os
import subprocess
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# (label, argv). Order is cheapest-first so a broken environment shows up fast.
SUITE = [
    ("tiles          seam / tile detection", ["tools/tiles.py", "--selftest"]),
    ("identity       Boyd recognition, leave-one-out", ["tools/identity.py", "--selftest"]),
    ("expression     measured frame selection", ["tools/expression.py", "--selftest"]),
    ("verify_thumb   gates A/C/D can still fail", ["tools/verify_thumb.py", "--selftest"]),
    ("verify_build   gates E/F/G/I/J/K/L/H can still fail", ["tools/verify_build.py", "--selftest"]),
    ("skin_colour    R56 correction lands inside his accepted band", ["tools/skin_colour_fix.py", "--selftest"]),
    ("thumb_metrics  metric reproduction + separability", ["tools/verify_thumb_metrics.py"]),
    ("master_audio   loudness stage", ["tools/master_audio.py", "--selftest"]),
    ("check_registry no orphaned checkers", ["tools/check_registry.py"]),
    # every checker the rules file names must exist and be on the build path,
    # or the rules file must say it is not (2026-09-01: 14 citations of a
    # script nothing called, two of a file that did not exist)
    ("check_rules_refs rules cite only real, wired checkers", ["tools/check_rules_refs.py"]),
    ("floor_stamp    R40 stale-floor refusal can still fail", ["tools/floor_stamp.py", "--selftest"]),
    ("check_title    R41 weak/stated-outcome title refusal can still fail", ["tools/check_title.py", "--selftest"]),
    ("check_variants R42 invisible-variant refusal can still fail", ["tools/check_variants.py", "--selftest"]),
    ("check_clutter  R43 element-budget / ink-cover refusal can still fail", ["tools/check_clutter.py", "--selftest"]),
    ("thumb_type     every type preset renders, its devices are ink, house == thumb constants", ["tools/thumb_type.py"]),
    ("library        R44 reactions seed is idempotent and re-copies a moved source", ["tools/library.py", "--selftest"]),
    # 2026-09-01: the gates rejected 3 of the 5 builds he accepted as the floor.
    # Every gate must pass the floor, or the floor file must declare the
    # disagreement by case and gate. The audit runs YuNet on all five (~2 min).
    ("check_floor_gates selftest: undeclared / stale disagreements are caught", ["tools/check_floor_gates.py", "--selftest"]),
    ("check_floor_gates every approved build passes every gate, or is declared", ["tools/check_floor_gates.py"]),
    # 2026-09-01, "make it have it": the five items reported out loud as NOT
    # automated. Each one is now a checker on the build path, and each one
    # proves here that it can still fail.
    ("caption_short  R34 reveal / entrance / speaker-side can still fail", ["tools/caption_short.py", "--selftest"]),
    ("short_engine   every short constant read from config/short_floor.json (G1-G10)", ["tools/short_engine.py", "--selftest"]),
    ("thumb_pipeline R44 judge cutout reuse: same-case / by-name / auto, and the refusals", ["tools/thumb_pipeline.py", "--selftest"]),
    ("case_search    who-posted-it search is recorded, --check can fail (missing / stale)", ["tools/case_search.py", "--selftest"]),
    ("case_search    every case in cases.json has a recorded search (age is gated at build time)", ["tools/case_search.py", "--check", "--all", "--recorded"]),
    ("floor_measure  per_case / envelope have a generator that can disagree", ["tools/floor_measure.py", "--selftest"]),
    ("floor_measure  config/quality_floor.json matches a fresh measurement of the five", ["tools/floor_measure.py", "--check"]),
    # 2026-09-01, "Can you fix the short editor as well after": the short
    # side's checkers were on disk and not in this suite. snap_cuts had been
    # failing its own selftest (exit 1, inverted fixture) with nothing noticing.
    ("snap_cuts      R35 mid-word cut snapping: collapse / inverted / distant controls", ["tools/snap_cuts.py", "--selftest"]),
    ("tighten        cut edges in measured silence (reverb-tail control) + no-silence gap left uncut", ["tools/tighten.py", "--selftest"]),
    ("pick_window    R36/R38 shipped OFFERUP window fails, fixed window passes", ["tools/pick_window.py", "--selftest"]),
    # 2026-09-02, "Okay then make it have it pls": one entry for every short.
    ("short_chain    raw -> words -> tight -> engine -> map; refusal removes sidecars", ["tools/short_chain.py", "--selftest"]),
    ("check_short_entry the old studio_server command is refused, player-file exemption is narrow", ["tools/check_short_entry.py", "--selftest"]),
    ("check_short_entry no editor page / script emits scripts/make_short.py", ["tools/check_short_entry.py"]),
    ("check_reveal   R34 on the RENDERED .ass: shipped V7 fails, reserve build passes", ["tools/check_reveal.py", "--selftest"]),
    # 2026-09-02, "add a 5 second or so clip of the hook ... 'Coming up'": R49.
    # Synthetic render with / without the cold open; without must FAIL, and so
    # must the pre-R49 TORRES_LONGFORM (opens on the sting).
    ("check_coldopen R49 hook + label + fade + sting, measured on the file; no-cold-open control fails", ["tools/check_coldopen.py", "--selftest"]),
    # 2026-09-02, "you have to use observer skill to actually pic actual
    # entertaining banger clips": R50. The digest must rank a synthetic banger
    # hearing 3x over a reset-and-PSI hearing and split every >> turn.
    ("banger_digest R50 entertainment layer on the picker; dull control scores ~0", ["tools/banger_digest.py", "--selftest"]),
    # 2026-09-02, "looks very cheap and colored/brightness wrong": R51. The
    # five he rejected that day are the control and must all fail the gate.
    ("check_thumb_grade R51 grade envelope + shared plate; the five rejected builds are the control", ["tools/check_thumb_grade.py", "--selftest"]),
    # 2026-09-02, "fix the reason why you're not able to see or detect that":
    # R52. Five invented scalars failed; the comparison sheet found it at once.
    ("vs_accepted R52 six-up sheet vs the accepted five; missing and stale sheets refused", ["tools/vs_accepted.py", "--selftest"]),
    # 2026-09-03, "Short was kinda underwhelming and slow, boring": R58. Every
    # other short gate passed it. The short he called slow is the control.
    ("check_short_pace R58 wpm envelope of his accepted shorts; the slow one is the control", ["tools/check_short_pace.py", "--selftest"]),
]

PASS_TOKENS = ("SELFTEST_PASS", "VS_ACCEPTED_SELFTEST_OK", "THUMB_GRADE_SELFTEST_OK", "BANGER_DIGEST_SELFTEST_OK", "ENGINE_SELFTEST_PASS", "ALL_OK", "REPRO_OK", "FLOOR_GATES_OK",
               "FLOOR_MEASURE_OK", "CASE_SEARCH_OK", "SHORT_ENTRY_OK", "COLDOPEN_OK")
FAIL_TOKENS = ("SELFTEST_FAIL", "RULES_REFS_FAIL", "FLOOR_GATES_FAIL",
               "FLOOR_MEASURE_STALE", "FLOOR_MEASURE_INCOMPLETE",
               "CASE_SEARCH_MISSING", "CASE_SEARCH_STALE", "CASE_SEARCH_UNKNOWN",
               "SHORT_ENTRY_FAIL", "COLDOPEN_FAIL")


def main():
    results = []
    for label, argv in SUITE:
        path = os.path.join(ROOT, argv[0])
        if not os.path.exists(path):
            # 2026-09-02: a MISSING row was appended and never printed, so the
            # suite said "28/30 pass" with no visible failure. Print it.
            results.append((label, "MISSING", argv[0]))
            print(f"  MISSING {label}")
            print(f"          {argv[0]} does not exist")
            continue
        r = subprocess.run([sys.executable] + argv, cwd=ROOT,
                           capture_output=True, text=True)
        out = (r.stdout or "") + (r.stderr or "")
        # a non-zero exit or a FAIL token is a failure even if a PASS token
        # also appears in the output - the old order looked for PASS first.
        # A token counts only at column 0 (where every verdict line is
        # printed): a selftest's negative control legitimately ECHOES the
        # token it just proved ("  ok   CASE_SEARCH_MISSING ..."), and the
        # 2026-09-01 suite marked case_search FAIL over exactly that echo.
        lines = out.splitlines()
        if r.returncode != 0 or any(ln.startswith(FAIL_TOKENS) for ln in lines):
            verdict = "FAIL"
        else:
            verdict = "PASS"
        tail = ""
        for ln in reversed(out.splitlines()):
            if ln.strip():
                tail = ln.strip()[:88]
                break
        results.append((label, verdict, tail))
        print(f"  {verdict:7} {label}")
        if verdict != "PASS":
            print(f"          {tail}")
    bad = [r for r in results if r[1] != "PASS"]
    print()
    print(f"  {len(results) - len(bad)}/{len(results)} suites pass")
    print("ALL_OK" if not bad else "SELFTEST_FAIL selftest_all")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
