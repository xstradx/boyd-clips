# GATES — the bright white on their faces (2026-09-03)

His words, this session, in order:

1. *"No I like left"* — shown the raw HYPIR crop beside two AI regenerations.
   **So the people are never regenerated. Qwen is dead as a subject path.**
2. *"Yes I like those colors I also fix the thumbnail that exact same method"* —
   the R56 skin colour correction is ACCEPTED.
3. *"No no they still looked washed"*
4. *"Like there's something that you did to judge Boyd's face and the guy to
   have that bright white effect"*

MEASURED before writing this file (`tools/_white_proof`, faces aligned on their
own detected boxes, so the two selections are the same pixels):

| | lifted > +8 L* | max lift |
|---|---|---|
| defendant | **12.2%** of the face | +78 L* |
| judge | **35.8%** of the face | +85 L* |

He is right and my earlier claim that the blown highlights were "in the source"
is RETRACTED — the crop leaving the colour fix is clean; the compositor paints
the white on afterwards.

Cause, from `_build_log.json` of that exact build (BOYD_SIMPLE=1):

- `face_L_balance` pull **0.60** — Boyd 108.0 pulled toward the 135.5 midpoint
  with the defendant. A brightness-parity stage lifting her whole face.
- `skin_chroma_lift` lift **2.1** — final skin chroma **26.8 / 28.5**, ABOVE the
  accepted band's top of 25.6.
- Both ran despite `BOYD_SIMPLE=1`, whose own docstring says it turns off
  "rim, skin balance, chroma lift, skin L". **The switch does not do what it
  says**, which is why every "surgery off" build still came back washed.

## Gates

- [ ] **G1 — the oracle fails on the known-bad before it is trusted.**
  CHECK: `python tools/check_face_light.py "D:/Boyd Clips/thumbwork/PACE_colour" "D:/Boyd Clips/thumbwork/PACE_colour/PACE_SIMPLE.jpg"`
  EXPECT: `FACE_LIGHT_FAIL`
  (PACE_SIMPLE.jpg is the build he just rejected. An oracle that passes it is
  measuring something other than what he is pointing at.)

- [ ] **G2 — no stage after the colour correction paints light on a face.**
  CHECK: `python tools/check_face_light.py <work> <new build>`
  EXPECT: `FACE_LIGHT_OK` — both subjects under 2.0% of face pixels lifted
  more than +8 L* against their own colour-corrected crop.

- [ ] **G3 — finished skin lands inside his accepted band.**
  CHECK: the same command's chroma line
  EXPECT: both faces inside 16.5–25.6 (currently 26.8 / 28.5, outside).

- [ ] **G4 — BOYD_SIMPLE tells the truth.**
  CHECK: `_build_log.json` of a `BOYD_SIMPLE=1` build
  EXPECT: `face_L_balance.pull == 0.0` and `skin_chroma_lift.lift == 0.0`.

- [ ] **G5 — the rule and its checker are on the build path.**
  CHECK: `python tools/check_rules_refs.py` and `python tools/selftest_all.py`
  EXPECT: `ALL_OK` from both.

- [ ] **G6 — the whole frame is read at 100% before it is shown to him.**
  MANUAL. Both faces opened at native size, plus the full 1280x720.

ABANDON: G1 the per-pixel lift oracle was INVALID - it measured detector-box
misalignment, not light. Alignment-free, every face percentile goes DOWN from
crop to composite. `tools/check_face_light.py` deleted rather than registered;
enshrining a wrong oracle is worse than having none.
ABANDON: G2/G3 as written depended on that oracle. Replaced by the corpus
measurement in `tools/_white_patch_corpus.py`, which DISPROVED three
white-patch hypotheses - none separates his accepted five from the rejected
builds. Recorded as a disproof, not converted into a gate.

MET: G4 - `_build_log.json` of the BOYD_SIMPLE=1 build now shows
`face_L_balance.pull 0.0` and `look_subject_locked {px: 355468,
mean_lift_reverted: 6.65}`.
MET: G5 - `check_rules_refs.py` ALL_OK.
MET: G6 - both faces and both full frames opened at 100%; the comparison that
settled it is `_STUDIO/_boyd_final.png`.

OUTCOME: the white on Boyd is in the PACE hearing's own footage of her, not in
a stage. Rebuilt from the approved THOMPSON cutout it is gone. The defendant's
pale scalp is in his source frame - R54 frame-picker work, still open.
