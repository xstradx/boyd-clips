# Archived checkers

Moved here 2026-08-31. These are NOT orphans to wire up - each was a one-off
that has already served its purpose, and leaving them in `scripts/` made the
orphan gate report noise instead of real gaps.

| file | why archived |
|---|---|
| `assemble_final.py` | its loudness stage was extracted to `tools/master_audio.py`, which is the live path now. Kept for the reference chain (two-pass loudnorm, then alimiter with `level=disabled`). |
| `validate_oncamera.py` | calibration run against cases with known outcomes; a one-time measurement, not a per-build check. |
| `verify_Q1_noregroup.py`, `verify_Q3_detail.py`, `verify_Q4_light.py` | gates written for three specific past experiments, each measured off its own shipped file. Superseded by `tools/verify_thumb.py` + `tools/verify_build.py`. |

Nothing here is deleted - if one of these is needed again it is a `git mv` away.

**Do not add to this folder to quiet the orphan gate.** A checker that is still
relevant gets WIRED, not archived. The gate exists because four defects on
2026-08-31 traced to a correct tool nothing called.
