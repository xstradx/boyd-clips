# Gates: face regeneration that is NOT slop

Nathan, 2026-08-29, on my first attempt: *"that regeneration is horrible
literaslly the definition of slop. audit youtself nonintrospectivly take a step
back and have a team using /unlazy correct this"*.

He is right. What I produced has every marker of AI slop and I should have seen
it before showing him:

- poreless, over-smoothed, waxy skin
- the generic "AI portrait" sheen
- identity drift — it moved toward the model's prior of "Black woman judge in a
  robe" rather than staying HER
- expression flattened toward a posed neutral at higher strength

## Why it was slop — my method, named honestly

1. Generic photoreal SDXL checkpoint with a generic text prompt.
2. **ZERO identity conditioning.** No face embedding, no reference adapter,
   nothing that tells the model who she is. The model had a text description and
   a noisy latent; of course it drew a stock judge.
3. Whole-tile img2img at 0.35-0.50 with no face-specific handling at all.
4. I never asked what the actual technique is. I reached for the tool I had
   already installed and assumed it was the right one.

That last point is the real failure and it is the one Nathan has flagged before:
filling a capability gap with my defaults instead of going to find what
practitioners actually use.

## What this ledger must establish, NON-INTROSPECTIVELY

Nothing below may be answered from my own knowledge. Every finding carries a
fetched URL, a model card, a repo, or a command output. No source, no finding.

- [ ] G1: the actual identity-preserving technique is named, with sources
  EVIDENCE: pending

- [ ] G2: every candidate's LICENCE is checked and commercial use confirmed —
      this is a monetised channel, and rembg's default (CC BY-NC) and
      FLUX.1-Fill-dev (non-commercial) were both already landmines here
  EVIDENCE: pending

- [ ] G3: the "is it restoration or regeneration" question is settled with
      evidence, not preference. Upscaling a compressed 612x338 video frame of a
      real person may be a FACE RESTORATION problem, not a text-to-image one.
  EVIDENCE: pending

- [ ] G4: what the field actually calls slop, from practitioners, with dated
      sources — so the output can be checked against their criteria and not mine
  EVIDENCE: pending

- [ ] G5: identity is MEASURED, not eyeballed — a face-embedding similarity
      between the real Judge Boyd and any regenerated output, with a stated
      threshold, so "still looks like her" stops being my opinion
  EVIDENCE: pending

- [ ] G6: CONTROL — the identity metric must score a DIFFERENT person as
      dissimilar. An identity check never tested against a negative is worthless,
      exactly like the face-alteration check earlier in this project.
  EVIDENCE: pending

- [ ] G7: a rebuilt output that Nathan does not call slop
  EVIDENCE: pending — his eye, not a metric

## Standing constraint

Nathan has now clearly asked for regeneration of the person, and that is
settled. But `spec/THUMBNAIL_RUBRIC.md`'s reason for caution still holds as a
QUALITY bar rather than a prohibition: the one thing this niche's practitioners
mock by consensus is thumbnails that read as AI-generated. A regeneration that
looks generated is worse than no regeneration at all. That is the bar.
