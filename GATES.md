# GATES — Boyd thumbnail automation, general across hearings

One observable outcome per gate. A gate is met only when its CHECK exits zero
and its EXPECT matches. Evidence recorded inline.

The target, in Nathan's words: *"well enough to be applied to any set of
defendants or pics of judge boyd and whatever is in the video so when youre
automated to post videos by youre self you always master the thumbnails yourself
too and from start to finish can handle everything from a routine"*.

So the test is not "does one thumbnail look good" — it is **does the same code,
given only a hearing and a line of copy, produce a correct thumbnail on hearings
it was not tuned for.**

---

- [x] G1 — The plate frame is CHOSEN, not supplied
    Frame selection must be part of the routine. Nathan has now twice been given
    a bad frame that no amount of layout solving could fix (the attorney standing
    exactly where Judge Boyd must be composited).
    CHECK: python scripts/make_thumbnail_auto.py --help
    EXPECT: --auto-plate

    EVIDENCE: MET — `--auto-plate` present. Evidence: `python scripts/make_thumbnail_auto.py --help` prints `--auto-plate`, exit 0.
- [x] G2 — All three hearings build from ONE command shape, no per-case tuning
    The judge is on the LEFT in CARTHIEF and the RIGHT in SANCHEZ and OFFERUP,
    and the tiles are different sizes. Any code that needs hand-holding per case
    is not a routine.
    CHECK: python scripts/run_case.py --list
    EXPECT: 3 cases configured

    EVIDENCE: MET — Evidence: `run_case.py --list` prints `3 cases configured`, and correctly reports judge LEFT for CARTHIEF, RIGHT for SANCHEZ and OFFERUP, read from config rather than hardcoded.
- [ ] G3 — No type on any face, all three
    Nathan's standing rule: "the words should never be on defendants or judges
    face or body".
    CHECK: python scripts/verify_set.py --dir "READY-TO-POST/Q3SET" --check type
    EXPECT: TYPE-ON-FACE: 0 failures

- [ ] G4 — Arrow points at the defendant and touches nobody, all three
    Zero overlap is necessary and NOT sufficient — an earlier build scored a
    perfect 0% while aimed at empty ceiling.
    CHECK: python scripts/verify_set.py --dir "READY-TO-POST/Q3SET" --check arrow
    EXPECT: ARROW: 0 failures

- [ ] G5 — No severed limb, all three
    "theres have to be surgical cuts not slop". Silhouette area loss over 1%
    is a cut limb.
    CHECK: python scripts/verify_set.py --dir "READY-TO-POST/Q3SET" --check limb
    EXPECT: LIMB: 0 failures

- [ ] G6 — Exposure matched across hearings
    "sanchez and offerup had different lighting than the first thumbnail and
    video so they look really brifht". Measured: 118.6 / 147.1 / 155.9 against
    the Thompson reference at 124.9.
    CHECK: python scripts/verify_set.py --dir "READY-TO-POST/Q3SET" --check luma
    EXPECT: LUMA: 0 failures

- [ ] G7 — No bystander half-hidden behind Judge Boyd
    "it looks weird how his lawyer ir right behind judge boyd". Fully covered is
    fine, fully clear is fine; the half-peeking state is the defect.
    CHECK: python scripts/verify_set.py --dir "READY-TO-POST/Q3SET" --check bystander
    EXPECT: BYSTANDER: 0 failures

- [ ] G8 — Chroma clean, all three
    The blocky artefact is chroma-dominant and luma metrics miss it entirely.
    CHECK: python scripts/verify_set.py --dir "READY-TO-POST/Q3SET" --check chroma
    EXPECT: CHROMA: 0 failures

- [x] G9 — One routine does thumbnail AND short for a case
    "from start to finish can handle everything from a routine".
    CHECK: python scripts/run_case.py --case OFFERUP --dry-run
    EXPECT: DRY RUN OK

    EVIDENCE: MET — Evidence: `run_case.py --case OFFERUP --dry-run` resolves video, transcript and short (all `found`) and prints `DRY RUN OK`, exit 0.
- [x] G10 — The lessons are written down, not just fixed in place
    Nathan: "i hope youre learning from all these mistakes right??"
    CHECK: node -e "const fs=require('fs');const p='C:/Users/natha/.claude/projects/C--Users-natha/memory/MEMORY.md';const s=fs.readFileSync(p,'utf8');console.log(/thumbnail-frame-selection|measure-the-rendered-artifact/.test(s)?'LESSONS RECORDED':'missing')"
    EXPECT: LESSONS RECORDED

    EVIDENCE: MET — Evidence: `measure-the-rendered-artifact.md` and `thumbnail-frame-selection.md` written to the home memory store and indexed in MEMORY.md; node check prints `LESSONS RECORDED`.
- [ ] G11 — The blown white SPOTS are gone, not just the highlight range
    Nathan, 2026-08-29: "i cant tell much of a difference i just think the super
    bright white spots need to be fixed some how". A global knee moved every
    highlight a little and the specific blown ceiling fixtures stayed readable as
    white holes. Measured blobs over 400px at >250: CARTHIEF 12, SANCHEZ 15,
    OFFERUP 9. The fix has to be LOCAL to those blobs or the change is invisible.
    CHECK: python scripts/kill_hotspots.py --check "READY-TO-POST/Q3SET"
    EXPECT: HOTSPOTS: 0 failures

---

## Status

Met: G1, G2, G9, G10.
Pending: G3-G8 — they measure the rendered set, and the three thumbnails are
still building through the routine (`run_case.py --all`, background bk84u3zau).

**Checker validated against a positive control before being trusted**, per the
lesson recorded in G10: run against the four QUALITY builds it correctly FAILS
Q2_surgical on chroma (14.96 over 6.5) and fails Q1 and Q2 on luma. A check that
cannot fail is not a check.
