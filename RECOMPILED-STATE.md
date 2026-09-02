# RECOMPILED STATE — 2026-08-31

Built by re-reading the whole thread as requirements, not by editing the
previous state file. Supersedes the scattered picture across `STATE.md`,
`BANGERS/GAPS.md`, `thumbnail-engine/PLAN.md` and `hook-engine/GATES.md`.

---

## THE FINDING THAT REORDERS EVERYTHING

Four independent measurements, same day, all negative:

| test | n | result |
|---|---|---|
| thumbnail image, 126 features, FDR-corrected | 231 win / 259 lose, 15 channels | nothing clears effect size |
| title surface structure | 234 win / 263 lose | identical on every feature |
| title semantics, held-out channels | 258 test rows, 8 channels | AUC 0.475 vs chance 0.493 |
| topic clusters, 12, FDR-corrected | 618 titles, 21 channels | zero findings; the one hypothesis the extremes suggested was falsified at p=1.0000 |

**Nothing measurable about the packaging predicts whether a video beats its own
channel.** The shuffled-label control returned 0.493, so the pipeline works and
the negative is trustworthy.

Nathan said this before any of it was measured: *"I've told you 10 times soto
case was high profile and no one was posting it there are no trials like that."*
That is a claim about WHICH HEARING YOU PICK. It survived the whole session
unacted-on because he only said it once, which is exactly the fragment patch
mode loses first.

**Consequence: case selection outranks packaging craft.** Not a reason to ship
ugly thumbnails - a reason to stop treating thumbnail micro-craft as the lever.

---

## WHAT IS BUILT AND VERIFIED

**`tools/thumbeng/`** — the one engine. 7 modules, `ENGINE_SELFTEST_PASS (6/6)`.
`ingest, understand, harvest, measure, styles, grammar, critique, variety`,
one CLI, video in to critique out. `harvest` scores each video against its own
channel's median, which removes the subscriber confound.

**`Projects/hook-engine/`** — separate by Nathan's call. 618 labelled titles, 21
channels, channel-split with zero leakage. Generator, NOT predictor — fixed by
its own AUC. Label gate 14/14 on controls; enforced diversity took the
most-similar pair from 0.988 to 0.639.

**Pipeline defects found and fixed today:**

| defect | evidence | state |
|---|---|---|
| cuts land mid-word / open past the first syllable | `SHORT_monkey-plan1` 5 of 5 defective, shipped | gate, exits 1, `--allow-rough-cuts` to override |
| every video ~7dB too quiet | -21.2 LUFS, true peak -5.1 dBFS, 5dB headroom unused | mastered to -14.3 / -1.6, gated, automatic in shorts AND long-form |
| no audio fades at cuts | none in the codebase | 30ms per segment (NOT the choppiness cause - measured) |
| arrow gate stale | enforced a size from before he resized it; compared glow-inclusive px to a polygon-only reference, 8.4x | reads `ARROW_W_FRAC` from `thumb.py` |
| checks going orphaned | 8 of 12 called by nothing | `tools/check_registry.py`, selftested |

---

## THE STRUCTURAL PROBLEM, NAMED

Every defect above existed because **a detector was written and then never
called.** `audit_cuts` found 5-of-5 broken cuts the first time it was ever run.
`assemble_final.py` had the correct two-pass loudnorm targeting exactly -14.0
and was invoked by nothing, so every video shipped quiet for months.

CLAUDE.md already diagnosed this for thumbnails. It was never fixed for video.

**9 orphans remain** - measured, after two false positives were removed from
the registry itself. Each needs wiring, deleting, or an explicit "human runs
this" with a reason:

    assemble_final  audit_cuts  check_vertical  validate_oncamera
    verify_Q1_noregroup  verify_Q3_detail  verify_Q4_light  verify_set
    verify_thumb_metrics

Only THREE checks in the whole repo are genuinely invoked: verify_render,
verify_thumb, verify_thumbnail.

The registry lied twice before it told the truth, and both lies flattered the
codebase. First it counted its own docstring, reporting zero orphans. Then it
counted `#` comments ABOUT a script as calls to it. Then it counted a
DOCSTRING mention - which is what hid `assemble_final`, the exact file whose
absence left every video 7dB quiet. A tool that measures whether checks run
needed three corrections before its own number could be trusted.

---

## PARKED AND NOT DONE — the list he cannot hold himself

These have been raised, agreed, and dropped repeatedly across the session.

1. **Spider Monkey thumbnail** built, never swapped onto `OGj_eLUXjrk`
2. **Three dead titles** never rewritten — 73 / 94 / 37 views between them
3. **`OFFERUP_LONGFORM.mp4` and `ROMERO_LONGFORM.mp4`** rendered, never posted,
   no audio/colour/caption pass, no thumbnail to current spec
4. **CARTHIEF monetization warning** never re-checked — Studio warned
   "visibility and monetization may be restricted" at schedule time
5. **CARTHIEF A/B test** set and saved, shows `Ineligible` until the premiere
   ends — needs re-checking after
6. **The slate is 17, not 30** — 35 hearings with footage on disk unread

Items 1-4 are outward-facing and need his go in the turn.

---

## WHAT I WOULD DO NEXT, IN ORDER

1. **Clear 1-5 above.** Small, real, and repeatedly dropped.
2. **Point `thumbeng` at case selection instead of packaging.** The harvest
   already carries titles + own-channel outlier scores for 644 videos. Ask
   "what KIND of hearing outperforms" rather than "what kind of thumbnail".
   That is the question the data might actually answer, and it serves the slate.
3. **Wire or kill the 8 orphans.**
4. **Re-master and re-cut the existing library** — every shipped video is 7dB
   quiet and some have defective cuts. `tools/master_audio.py` fixes the first
   in seconds per file.

## STANDING RULES — restated because they are easy to lose

- Profanity in audio, censored in every text surface
- Never Made for Kids
- Ad suitability: "None of the above" only
- Publishing is a hard stop needing confirmation in the turn
- Court footage is public record
- Zoom-quality audio and a closed courtroom are the ceiling, not a bug
