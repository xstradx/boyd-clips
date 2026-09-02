# How to audit this project correctly

Every rule below was derived from a failure that actually happened in the
2026-08-29 audit. None of it is generic best practice. Where a rule has no
observed failure behind it, it is not in this file.

The audit produced 160 findings and 8 defects of its own. The defects cluster
into six mechanisms, and four of the six are the same underlying error:
**a result was reported without the conditions that produced it.**

---

## R1: A number without its parameters is not a measurement

FAILURE: leaf-1.3 reported "all six long-forms have zero spans over 4s".
leaf-4.1 reported "CARTHIEF_LONGFORM 23 spans over 4s / 134.9s". Same file,
same tool, same audit. Both were right. Neither headline named the threshold.
The driver had to re-measure to discover the numbers were taken at `-30dB` and
`-20dB` respectively, and that at `-20dB` the detector is classifying quiet
speech as silence because speech RMS on this footage is about -21.7 dB.

MECHANISM: the reader cannot tell a genuine disagreement from a difference in
conditions, so two contradictory findings sit in the same report and whichever
is read last wins. Neither agent was wrong; the report was, because it carried
the numbers without the settings that produced them.

ENFORCED-BY: `EVIDENCE:` must contain a command that can be pasted and re-run
verbatim, with every parameter present. Measured across the first audit, only
78% of findings carried a runnable command and only **48% stated explicit
parameters** — the contradiction lived in the other 52%.

---

## R2: State the duration and the threshold separately, always

FAILURE: STATE.md's first substantive line reads "`silencedetect` DOES NOT WORK
ON THIS FOOTAGE. Do not use it. Measured on CARTHIEF_SHORT.mp4 at -30, -25, -20
AND -18 dBFS: zero spans, every time." Re-run by the driver at both durations:
16 / 13 / 10 / 10 spans at `d=0.7`, and 0 / 2 / 3 / 3 at `d=4.0`. The claim is
true at one of eight settings. The stated cause — "the room tone never drops
that low" — is false too: `astats` gives a noise floor of -83.3 dBFS.

MECHANISM: a two-parameter tool was reported as if it had one parameter, so a
working tool was banned in writing, a parallel implementation was built to
replace it, and a claim that six videos need re-rendering propagated from it.
This is R1 having already happened once and gone undetected for a month.

ENFORCED-BY: any finding about a thresholded detector must sweep and report at
least two values of every parameter, or state which are held fixed and why.

---

## R3: Separate what was measured from what it means

FAILURE: leaf-3.3 measured that `CARTHIEF_thumbnail.jpg` is byte-identical to
`CARTHIEF_thumb_A.jpg` — correct, reproducible, md5-verified. It then reported
"the shipped thumbnails are the variants STATE.md records as REJECTED". The md5
was a measurement; the word "rejected" was an inference resting on an unstated
assumption about what the A/B/C letters mean. leaf-4.1 struck that inference on
its own re-read. **The driver had already passed it to Nathan as a fact.**

MECHANISM: an inference inherits the authority of the measurement it sits next
to. The reader cannot see the join.

ENFORCED-BY: every finding declares `CLAIM: measurement | inference | reading`.
An inference must name the measurement it rests on AND the assumption that
bridges them, so the assumption can be attacked separately. The bridge here was
"A/B/C vary the frame", and it was false: measured, A and C differ by 40.6 in
the text band and 0.2 in the plate.

---

## R4: Test the checker against a known answer before believing its output

FAILURE: the driver tried three times to verify one claim about transcript text.
Attempt 1, `grep -rl "bear county"` over 250 transcripts: 0 hits, concluded the
claim was refuted. Attempt 2, joining the raw JSON and regexing: 0 hits for
"bear county" AND 0 for "bexar county". Attempt 3, after actually opening a file
and finding one-word-per-record storage: **137 and 120 of 250.** The first two
checkers were broken, not the claim.

What caught it was not care. It was an implausible control: a Bexar County court
transcript containing zero mentions of Bexar County cannot be true.

MECHANISM: a checker that has never been run against a known answer returns
confident output in both directions and there is no way to tell from inside.

ENFORCED-BY: every finding that rests on a checker must cite `CONTROL+:` a case
the checker must pass and does, and `CONTROL-:` a case it must fail and does.
This is already the project's own recorded lesson, and the audit found four
shipped checkers that violate it — including two limb checkers, neither of which
can separate their controls.

---

## R5: A metric must prove it measured the intended region

FAILURE: leaf-4.1 replicated `flat_chroma()`'s window selection and printed the
coordinates. On CARTHIEF it lands at x=518 y=477, meanRGB (203,97,1) — the
defendant's orange jail scrubs. The function has no minimum-luma floor, so when
the ceiling fails its flatness test the most saturated garment in frame wins.
The repo now holds three mutually exclusive numbers for the same file's chroma:
5.54 in STATE.md, 1.685 in its own meta.json, 90.9 from the gate today. A build
decision — disqualifying the Q2 thumbnail — may rest on a measurement of
clothing.

MECHANISM: an aggregate over an auto-selected region reports a number whether or
not the region is the one the name implies.

ENFORCED-BY: any regional metric must emit the region it chose (coordinates and
mean colour) alongside the value, and a finding citing it must show that region
is the intended one.

---

## R6: Enforce read-only structurally, not by instruction

FAILURE: all thirteen agents were told, in bold, not to write. Three wrote
anyway: `READY-TO-POST/NOW.png`, `READY-TO-POST/JUDGE_LAYER_MEASURED.png`,
`scripts/layer_metrics.py`. Two landed in the folder Nathan takes deliverables
from. Nothing was overwritten and nothing was lost — but the only reason this is
known is that the driver had built a 4,656-file snapshot gate before dispatch.

MECHANISM: a brief is a request. An agent mid-task that wants a contact sheet
will make one.

ENFORCED-BY: run read-only audits in a git worktree copy so the real tree is not
reachable, and keep the snapshot gate as the backstop. Detection after the fact
is the weaker half; it was sufficient here only because nothing was destructive.

---

## R7: Cross-check findings that name the same artifact

FAILURE: the leaf-1.3 / leaf-4.1 dead-air contradiction was caught because the
driver happened to read both summaries in the same session and noticed. Nothing
in the method would have caught it. Two agents also both reported on
`verify_thumbnail.py` and `CARTHIEF_thumbnail.jpg` without either knowing.

MECHANISM: disjoint territories prevent duplicated work, which is their purpose,
but they also guarantee that overlapping conclusions never meet.

ENFORCED-BY: a mechanical pass that groups findings by the artifact path and
numeric quantity they cite, and surfaces every pair whose numbers differ, before
the driver writes anything.

---

## R8: Hostile re-read is the only step that caught anything

FAILURE: inverted — this one WORKED, and is recorded so it is not dropped as an unnecessary step. leaf-3.1 struck three of its own findings
as unreachable after measuring: the fontsdir guard always passes because
`assets/fonts` exists with 6 faces; the raw-motion fallback never fires because
the envelope is padded; the hook warning does surface. leaf-3.2 downgraded its
own watermark blocker after measuring that the candidates list resolves.
leaf-1.3 retracted a 44.7% dead-air figure after finding it had `astats` columns
reversed and had accepted a peak below RMS, which is impossible.

MECHANISM: the first pass optimises for finding things. Only a second pass with
the opposite incentive removes what is not there.

ENFORCED-BY: keep it, and require the strike list to be reported rather than
silently applied — the retractions are how a reader calibrates the rest.
