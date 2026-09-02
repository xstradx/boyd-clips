# Gates: the render gate — stage 11

Scope: one real check per mandatory output element, measured on the FINISHED
file rather than on the code that made it, each proven against a known-good and
a known-bad control before it is trusted, and wired so a failing render is
quarantined instead of landing in the publish folder named `_FINAL`.

This is step 1 of the build order because until a video can be checked, every
other improvement is unverifiable.

OWNS: scripts/gate/**

Constraint: the other Claude session owns `scripts/*.py` at the root and
`READY-TO-POST/`. Nothing here writes to either.

- [ ] G1: purpose-built control fixtures exist — for every check, a file it must pass and a file it must fail
  CHECK: python scripts/gate/build_fixtures.py --verify
  EXPECT: fixtures verified
  EVIDENCE: pending

- [ ] G2: the integrity check separates its controls (yuv420p passes, yuv444p fails) and catches A/V drift
  CHECK: python scripts/gate/selftest.py --check integrity
  EXPECT: integrity selftest passed
  EVIDENCE: pending

- [ ] G3: the dead-air check is a windowed DENSITY measure, not a max-span threshold, and separates its controls
  CHECK: python scripts/gate/selftest.py --check deadair
  EXPECT: deadair selftest passed
  EVIDENCE: pending

- [ ] G4: the intro check detects the branded sting at t=0 and rejects a render without one
  CHECK: python scripts/gate/selftest.py --check intro
  EXPECT: intro selftest passed
  EVIDENCE: pending

- [ ] G5: the caption check keys on the glyph signature (bright core inside dark stroke) and reports WHICH half, separating captioned from uncaptioned
  CHECK: python scripts/gate/selftest.py --check captions
  EXPECT: captions selftest passed
  EVIDENCE: pending

- [ ] G6: every check runs together in one runner that exits non-zero on any failure and never leaves a failed render at the destination path
  CHECK: python scripts/gate/selftest.py --check runner
  EXPECT: runner selftest passed
  EVIDENCE: pending

- [ ] G7: checks that cannot be validated today are reported as NOT-VALIDATED rather than silently passing
  CHECK: python scripts/gate/selftest.py --check honesty
  EXPECT: honesty selftest passed
  EVIDENCE: pending
