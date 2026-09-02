# GATES — automatic thumbnail wrapper

Goal, in his words: *"this automatic thumbnail wrapper is actually being built
properly... when we're finished you will know exactly how to make them
autonomously and with a push of a button."*

**Definition of the button:** `python tools/make_thumb.py SANCHEZ` takes a case
key from `config/cases.json` and writes a gated thumbnail, with NO hardcoded face
boxes, NO hand-run HYPIR, NO manually-picked crops, and a non-zero exit if any
quality gate fails.

Spec: `spec/THUMBNAIL_SPEC.md`. Gate implementation: `tools/verify_thumb.py`.

CHECK commands run from the repo root with `python`.

---

## Leaf 1 — frame selection (OWNS: tools/pick_frames.py)

- [ ] L1:G1 — Picks a reaction frame per subject from the case video, no hand-picking
      CHECK: python tools/pick_frames.py SANCHEZ --json
      EXPECT: PICK_OK
- [ ] L1:G2 — Rejects a frame with no detectable face rather than returning it
      CHECK: python tools/pick_frames.py --selftest
      EXPECT: PICKSELF_PASS

## Leaf 2 — restore + matte (OWNS: tools/restore.py, tools/matte.py)

- [ ] L2:G1 — HYPIR runs per SUBJECT CROP, captioned for that person (spec 8.6)
      CHECK: python tools/restore.py --selftest
      EXPECT: RESTORE_PASS
- [ ] L2:G2 — Matte changes ALPHA ONLY; RGB byte-identical to the restore input
      CHECK: python tools/matte.py --selftest
      EXPECT: MATTE_RGB_IDENTICAL
- [ ] L2:G3 — RGB and alpha resized separately (Pillow flattens RGBA colour)
      CHECK: python tools/matte.py --selftest-resize
      EXPECT: RESIZE_SAFE

## Leaf 3 — compositor (OWNS: tools/thumb.py)

- [ ] L3:G1 — Face boxes come from detection, never constants (spec 8.4)
      CHECK: python tools/thumb.py --selftest-faces
      EXPECT: FACES_DETECTED
- [ ] L3:G2 — Kicker caption does not by itself push poster_fa over the limit
      CHECK: python tools/thumb.py --selftest-kicker
      EXPECT: KICKER_WITHIN_BUDGET
- [ ] L3:G3 — Blur and chroma are independent knobs; blur must not move poster_fa
      CHECK: python tools/thumb.py --selftest-knobs
      EXPECT: KNOBS_INDEPENDENT
- [ ] L3:G4 — Saved JPEG is 4:4:4, not Pillow's 4:2:0 default (spec 8.4)
      CHECK: python tools/thumb.py --selftest-jpeg
      EXPECT: JPEG_444

## Leaf 4 — the button (OWNS: tools/make_thumb.py)

- [ ] L4:G1 — One command, case key in, gated thumbnail out
      CHECK: python tools/make_thumb.py SANCHEZ
      EXPECT: THUMB_SHIPPED
- [ ] L4:G2 — Exits non-zero and writes NOTHING when a gate fails
      CHECK: python tools/make_thumb.py --selftest-blocks
      EXPECT: BLOCKS_ON_FAIL
- [ ] L4:G3 — Runs on a second case without code edits
      CHECK: python tools/make_thumb.py CARTHIEF
      EXPECT: THUMB_SHIPPED

## Integration

- [ ] INT:G1 — Every quality gate passes on the produced file
      CHECK: python tools/verify_thumb.py out/thumbs/SANCHEZ.jpg
      EXPECT: SHIP
- [ ] INT:G2 — The gate checker can still fail (negative control)
      CHECK: python tools/verify_thumb.py --selftest
      EXPECT: SELFTEST_PASS
- [ ] INT:G3 — No hardcoded case-specific constants left in the pipeline
      CHECK: python tools/audit_constants.py
      EXPECT: NO_HARDCODED_CASE_VALUES
