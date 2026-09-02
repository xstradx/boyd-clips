# Gates: thumbdoctor — constraints, the rubric eye, and a repair loop

Scope: one system that grades ANY thumbnail with no context, enforces Nathan's
R1-R15 constraints as binary gates that never trade against the score, and
repairs a real thumbnail end to end until it passes — rendering the fixed file,
not predicting it.

## Why the shape changed, recorded so it is not re-litigated

Three earlier calibration attempts were measured and rejected:

1. A 37-row competitor corpus — other channels, not his audience.
2. His own complaints transcribed to thresholds — can only catch mistakes he
   already caught. Measured: Spearman rho(gate score, his views) = **-0.571**.
3. His own back catalogue — n=8, one construction, varies by topic not craft.

Nathan, 2026-08-29: *"youre not reverse engineering the actual system youre
basing it off of such limited information"*. He was right.

The actual mechanism: Pikzels' score endpoint returns subscores named clarity /
curiosity / emotion / idea / virality plus a free-text suggestion (schema
fetched from docs.pikzels.com/openapi.json). Those are RUBRIC DIMENSIONS. A
pixels-to-CTR regressor emits one number and "idea" is not a pixel property. So
the product is a VLM grading against a rubric — which is why it needs no channel
context. Ours runs locally on qwen3.6-35b-abliterated-vision: free, unlimited,
offline.

- [x] G1: every defect either verifier can emit is mapped; none silently dropped
  CHECK: python scripts/thumbdoctor.py selftest-map
  EXPECT: MAP_COMPLETE
  EVIDENCE: MET. cmd exit 0. Output: "25 defect codes emitted by the verifiers, all mapped. 19 have a real lever; 6 are honestly declared unfixable-by-parameter. every mapped flag verified to exist on thumb_Q3_detail.py / MAP_COMPLETE"

- [x] G2: CONTROL - an unknown defect is reported as unmapped, never swallowed
  CHECK: python scripts/thumbdoctor.py selftest-unknown
  EXPECT: UNMAPPED_REPORTED
  EVIDENCE: MET. cmd exit 0. Runs a positive control first (a mapped defect must keep its lever) so the check cannot pass for the wrong reason. Output: "control kept its lever (--face-margin); fabricated defect surfaced as unmapped / UNMAPPED_REPORTED"

- [x] G3: the rubric eye is reachable and grades a real image end to end
  CHECK: python scripts/eye.py selftest
  EXPECT: VISION_READY
  EVIDENCE: MET. exit 0. "vision-capable: qwen3.6-35b-abliterated-vision:latest / VISION_READY". Model restored from the GGUF on D: via ollama create; a full-rubric grade of a real 1280x720 thumbnail returns valid JSON in ~16s at ~34 tok/s.

- [x] G4: constraints and the rubric score are separate layers, never averaged
  CHECK: python scripts/thumbdoctor.py selftest-layers
  EXPECT: LAYERS_SEPARATED
  EVIDENCE: MET. exit 0. Asserts a 100/100 render with 1 constraint violation LOSES to a 1/100 clean render, with a positive control that among clean renders the rubric still decides. Output: "constraint layer : spec/NATHAN_RULES.md + 6 hard gates / rubric layer : spec/THUMBNAIL_RUBRIC.md, 8 dimensions / LAYERS_SEPARATED"

- [x] G5: the eye separates the two measured extremes by a wide margin
  CHECK: python scripts/eye.py separates
  EXPECT: SEPARATES
  EVIDENCE: MET. exit 0. winner cSz-vkSwVlk (9,800 views) = 92.1; loser OGj_eLUXjrk (55 views) = 61.2; margin 30.9 against a required 20.0. The old gate score ranked these two BACKWARDS (95.1 SHIP for the loser, 71.4 WEAK for the winner). Claim is scoped to the extremes only - G6 holds the line on what this does not license.

- [x] G6: CONTROL - the eye is NOT claimed to predict views on unseen thumbnails
  CHECK: python scripts/eye.py honesty
  EXPECT: NO_OVERCLAIM
  EVIDENCE: MET. exit 0. Measured and on record at research/reference/ttt_own/eye_vs_views.txt: rho(views, eye) = +0.50 across all 8 Boyd long-forms BUT -0.20 across the 6 the rubric has never seen. The +0.50 is driven by the two anchors named in the rubric, so the honest number is -0.20 and the gate refuses to let the flattering one stand alone. Old gate score on the same 8: -0.571.

- [ ] G7: the repair loop renders a REAL fixed thumbnail and improves it,
      measured on the re-rendered file rather than predicted
  CHECK: python scripts/thumbdoctor.py repair --case CARTHIEF --out work/repair/CARTHIEF.jpg --max-rounds 4
  EXPECT: REPAIR_IMPROVED
  EVIDENCE: pending

- [x] G8: the automated pipeline PRODUCES a Q3 thumbnail, not merely mentions it
  CHECK: python scripts/thumbdoctor.py selftest-pipeline
  EXPECT: PIPELINE_PRODUCES_Q3
  EVIDENCE: MET. exit 0. Intercepts the real _run_builder call inside boydclips.thumbnail.build() and inspects the command line. Output: "pipeline invoked thumb_Q3_detail.py / judge-crop 612:338:18:190 and plate-crop 620:338:644:190 were DERIVED from the video and match config/cases.json exactly". detect_tile_crops returns ffmpeg crop strings byte-identical to the hand-written per-case geometry, so that tuning was never necessary.

  NOTE, 2026-08-29: the original check was a string grep for "thumb_Q3_detail"
  in src/boydclips/thumbnail.py. That gate was BADLY AUTHORED and would have
  passed on a broken edit: thumbnail.build() feeds --bg/--subject/--cutout to
  make_thumbnail_v2, while thumb_Q3_detail takes --video/--judge-crop/--plate-t.
  Renaming the constant satisfies a grep and produces nothing. Replaced with a
  check that runs the path and inspects the artifact.

- [ ] G9: a cross-channel corpus exists at scale with an outlier label
  EVIDENCE: pending

- [ ] G10: a learned pixels-to-performance model beats chance on held-out data
  EVIDENCE: pending

- [ ] G11: which half holds the judge is DETECTED, never assumed
  EVIDENCE: pending

  Found while proving G8, 2026-08-29, and it is a live production bug rather
  than a test artifact. boydclips.thumbnail.build() defaults
  subject_side="right"; Judge Boyd is on the LEFT in CARTHIEF and the RIGHT in
  SANCHEZ and OFFERUP. Unattended, CARTHIEF would put the defendant in the hero
  slot and trace the wrong person. STATE.md already warned "any system that
  assumes a side is already broken" - it is still assumed. The G8 check derives
  the side from config/cases.json so the wiring could be proven; that is a
  scaffold, not the fix. A real fix detects her (face match against a reference
  of Boyd, or largest-robed-figure) and must be measured on all three cases.

- [x] G12: every constraint check DISCRIMINATES - none fires on the known-good corpus
  CHECK: python scripts/thumbdoctor.py selftest-checks
  EXPECT: CHECKS_DISCRIMINATE
  EVIDENCE: MET. exit 0. Output: "checked 12 known-good reference thumbnails /
    ARROW_AIMS_AT_NOTHING 2/12 = 17% / no check fires on a majority of the
    reference set / CHECKS_DISCRIMINATE".
    Route to green: EDGE_ARTEFACT fired on 15/15 winners AND 10/10 losers (100%
    of both) and CHROMA_BLOCKING on 11/12 known-good references. Distributions
    measured to decide re-threshold vs retire:
      edge_len     (thr 0.40)  competitor med 0.39  winners med 2.35  losers med 1.90
      flat_chroma  (thr 3.50)  competitor med 14.58 winners med 28.98 losers med 26.30
    Neither separates winners from losers, so neither is re-thresholdable - both
    were DEMOTED from failures to warnings in verify_thumbnail.py, with the
    numbers recorded inline. Second finding: the documented calibrations no
    longer reproduce. edge_len_frac cites "all 12 at 0.00 -> 0.40"; those same 12
    now measure med 0.39 / max 1.25. flat_chroma_dev cites "ungraded ceiling
    1.33"; the known-good set now medians 14.58. The thresholds were set from
    measurements that have since drifted. Full table:
    research/reference/check_calibration.txt

  Measured 2026-08-29 and it is the root cause of G7's three failed runs:
  EDGE_ARTEFACT fires on 15/15 courtroomtime winners AND 10/10 losers (100% of
  both - zero information), and CHROMA_BLOCKING fires on 11/12 of the known-good
  competitor references. The repair loop stepped --light-wrap 0.18->0.33,
  --arrow-prefer-deg 25->61 and --chroma-r 5->11 across four clean rounds and
  violations never moved off 3, because two of those three "defects" are
  constants rather than faults. A repair loop tuned against a check that fires
  on everything cannot converge, and no amount of lever tuning would have
  revealed that - only testing the checker against a known answer did.

ABANDON: G9 A cross-channel scraped corpus is NOT the source of the rules and building one as such was the mistake Nathan corrected. The rules come from the rubric, which is general knowledge already inside the VLM. A corpus is still wanted LATER as an independent test set (views over each channel's own median, so channel size cancels), but it is validation, not construction, and nothing in this build depends on it. Handoff: research/reference/ttt_own/ holds the 28-image own-channel start; scale it cross-channel when validating, not before.

ABANDON: G10 A learned pixels-to-performance model is superseded and should not be built. Measured absence 2026-08-29: no public model predicts CTR from a thumbnail image, and the one published attempt (codencoding/Red-Means-Go) found thumbnail pixel features performed WORSE than predicting the mean. The rubric VLM replaces it. Its shuffled-label control (former G6) goes with it; the honesty control that survives is G6 above, which asserts what the eye may NOT claim.
