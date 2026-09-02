# GATES — rebuild the five Boyd thumbnails to the accepted grade (2026-09-02)

CONTRACT: PERKINS, GARCIA_J, LOPEZGONZALEZ, CLAYTON, PACE thumbnails are
rebuilt — not re-tuned, not patched — so the judge and defendant read as the
accepted builds do, on a plate that is not shared between them.

His words (2026-09-02): *"I don't like the way the judge and defendant look.
Looks very cheap and colored/brightness wrong and don't have that professional
hd look"*. Measured cause, against `config/quality_floor.json`:

| metric | accepted envelope | the five he rejected |
|---|---|---|
| `grain_hf` | 0.87 – 1.72 | 4.04 – 4.65 (4 of 5) — oversharpened crunch |
| `background_L` | 107.2 – 149.1 | 90.8 – 101.8 (5 of 5) — plate too dark |
| `contrast_sd` | 78.2 – 82.8 | 72.4 – 77.9 (5 of 5) — flat |
| plate `bg_raw.png` | one per case | `9e01114e2875` on ALL FIVE |

OWNS: `D:/Boyd Clips/thumbwork/{PERKINS,GARCIA_J,LOPEZGONZALEZ,CLAYTON,PACE}/`,
`D:/Boyd Clips/READY-TO-POST/<KEY>/<KEY>_thumb.jpg`, `config/cases.json` (own
key only). Does NOT own: `config/quality_floor.json` (never edited), the
videos, `STATE.md`.

The rejected five are preserved as the known-bad control in
`tools/fixtures/rejected_2026_09_02/` — the gate below is proven against them.

## Gates

- [ ] G1: the grade gate can still fail: accepted builds inside the envelope,
  all five rejected builds outside it.
  CHECK: `python tools/check_thumb_grade.py --selftest`
  EXPECT: `THUMB_GRADE_SELFTEST_OK`
  EVIDENCE: pending
- [ ] G2: PERKINS is inside the envelope and does not share a plate.
  CHECK: `python tools/check_thumb_grade.py PERKINS "D:/Boyd Clips/READY-TO-POST/PERKINS/PERKINS_thumb.jpg" --peers GARCIA_J LOPEZGONZALEZ CLAYTON PACE`
  EXPECT: `THUMB_GRADE_OK`
  EVIDENCE: pending
- [ ] G3: GARCIA_J likewise.
  CHECK: `python tools/check_thumb_grade.py GARCIA_J "D:/Boyd Clips/READY-TO-POST/GARCIA_J/GARCIA_J_thumb.jpg" --peers PERKINS LOPEZGONZALEZ CLAYTON PACE`
  EXPECT: `THUMB_GRADE_OK`
  EVIDENCE: pending
- [ ] G4: LOPEZGONZALEZ likewise.
  CHECK: `python tools/check_thumb_grade.py LOPEZGONZALEZ "D:/Boyd Clips/READY-TO-POST/LOPEZGONZALEZ/LOPEZGONZALEZ_thumb.jpg" --peers PERKINS GARCIA_J CLAYTON PACE`
  EXPECT: `THUMB_GRADE_OK`
  EVIDENCE: pending
- [ ] G5: CLAYTON likewise.
  CHECK: `python tools/check_thumb_grade.py CLAYTON "D:/Boyd Clips/READY-TO-POST/CLAYTON/CLAYTON_thumb.jpg" --peers PERKINS GARCIA_J LOPEZGONZALEZ PACE`
  EXPECT: `THUMB_GRADE_OK`
  EVIDENCE: pending
- [ ] G6: PACE likewise.  <!-- v2 rebuild 2026-09-02 14:5x: THUMB_GRADE_FAIL 5
  (contrast_sd 74.50 < 78.20; four metrics unmeasurable - mask UNALIGNED).
  Fresh judge cut + regen off did NOT change the picture; measured new defect:
  the matte eats the hair - defendant hair band mean alpha 61/255, only 23.3%
  of hair pixels opaque, which is the bald-dome hairline he pointed at. -->
  CHECK: `python tools/check_thumb_grade.py PACE "D:/Boyd Clips/READY-TO-POST/PACE/PACE_thumb.jpg" --peers PERKINS GARCIA_J LOPEZGONZALEZ CLAYTON`
  EXPECT: `THUMB_GRADE_OK`
  EVIDENCE: pending
- [ ] G7: the old gates still hold on all five (A posterisation, C blow-out,
  D duplicate face) — a grade fix must not trade one defect for another.
  CHECK: `python tools/verify_thumb.py "D:/Boyd Clips/READY-TO-POST/PERKINS/PERKINS_thumb.jpg" && python tools/verify_thumb.py "D:/Boyd Clips/READY-TO-POST/GARCIA_J/GARCIA_J_thumb.jpg" && python tools/verify_thumb.py "D:/Boyd Clips/READY-TO-POST/LOPEZGONZALEZ/LOPEZGONZALEZ_thumb.jpg" && python tools/verify_thumb.py "D:/Boyd Clips/READY-TO-POST/CLAYTON/CLAYTON_thumb.jpg" && python tools/verify_thumb.py "D:/Boyd Clips/READY-TO-POST/PACE/PACE_thumb.jpg"`
  EXPECT: `SHIP`
  EVIDENCE: pending
- [ ] G8: the rule and its checker are wired, not just written.
  CHECK: `python tools/check_rules_refs.py && python tools/selftest_all.py`
  EXPECT: `ALL_OK`
  EVIDENCE: pending
- [ ] G9: MANUAL - every rebuilt thumbnail opened at 100% and read in the chat
  by me before he sees it: judge once (never twice), defendant recognisable,
  no hacked hairline or matte halo, text legible at phone size.
  No command decides "professional HD look" — this one is my eyes, and it
  is reported out loud as unautomated every time (project CLAUDE.md).
  EVIDENCE: pending

## Known defects to fix in the rebuild, beyond the grade

1. PACE — the defendant's cut-out has a hacked hairline (top of head reads as a
   bald dome). Matte failure, not his hair.
2. GARCIA_J — no arrow while the other four have one.
3. All five — one shared plate (`9e01114e2875`); each case takes its own
   background from its own hearing.

## Attempt log (2026-09-02, his `/task-observer /unlazy` redo)

| build | change | result |
|---|---|---|
| v2 | fresh judge attempt + regen off | unchanged - the fresh cut never ran (library re-decided it) |
| v3 | `judge_source: video` (real fresh cut) | judge tone better, defendant unchanged |
| v4 | defendant frame 5150 (0.1% blown vs 11.7%) | scalp fixed, real hair returns |
| simple | `BOYD_SIMPLE=1` - no rim, no skin balance, no chroma lift, no skin L | halo, magenta fringe and plastic rim all GONE |
| redo | best frames both + fresh HYPIR + BOYD_SIMPLE | defendant photographic; JUDGE POSE WRONG (hand over mouth) - I picked her by pixels and dropped expression |

Retracted during this work, both told to him: (1) "the people are not being
upscaled / crops too small" - HYPIR 4x runs on every crop and the accepted
builds started from SMALLER faces (CARTHIEF 111px, SANCHEZ 116px vs PACE
128px, PERKINS 134px, GARCIA_J 138px); (2) "skin a* is a clean separator" -
measured on 4 faces, overlaps across 10.

Open, in order:
1. Frame picker scores expression OR pixels, never both. It must score
   expression AND face size AND blow-out AND sharpness, and say what it traded.
2. The frame still reads high-key next to the accepted five (no true blacks).
3. `selftest_all` 34/35 - `thumb_pipeline` R44 suite broke when PACE moved to
   `judge_source: video`. Fix before anything ships.
