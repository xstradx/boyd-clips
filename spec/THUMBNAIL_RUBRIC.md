# The thumbnail rubric — the eye, not the ruler

Nathan, 2026-08-29: *"i could literally throw anything at you and you could make
a viral/winning looking thumbnail just like pikzels"*, and on the earlier
approach: *"youre not reverse engineering the actual system youre basing it off
of such limited information"*.

He was right. Two earlier attempts were wrong:

- **Attempt 1 — a competitor corpus.** 37 rows of other channels. Not his audience.
- **Attempt 2 — his own complaints.** Transcribed into thresholds, which can only
  catch mistakes he already caught.
- **Attempt 3 — his own back catalogue.** n=8, and every one is the same
  construction, so it varies by topic, not by craft. Measured result: Spearman
  rho between the current gate score and actual views = **-0.571**. The scorer
  gave 95.1 SHIP to the 55-view video and 71.4 WEAK to the 9,800-view one.

## What Pikzels actually is

Its score endpoint returns `main_score` plus subscores named **clarity,
curiosity, emotion, idea, virality**, and one free-text `suggestion`
(schema fetched from docs.pikzels.com/openapi.json, 2026-08-29).

Those are **rubric dimensions**, not the output of a pixels-to-CTR regressor -
a trained regressor emits one number, and "idea" is not a pixel property. So
Pikzels is a vision-language model grading against a rubric. That is why it
needs no context about the channel and works on anything thrown at it: the
general knowledge of what a good thumbnail looks like is already inside the
model, absorbed from the whole internet, not learned from the user's data.

This also explains the measured absence: no public model predicts CTR from
pixels, because that is not how these products work.

**So the eye is a VLM with a rubric.** Ours runs locally on the 5080 against
`qwen3.6-35b-abliterated-vision`, so it is free, unlimited and offline.

## Calibration anchors — measured on this channel, same format, same judge

The rubric is anchored on two real outcomes rather than adjectives.

**The winner was made IN PIKZELS.** Nathan, 2026-08-29: *"the 92.1 i rememeber i
actually made it with pikzels"*. Three things follow and none of them are small:

1. Our local eye scoring it 92.1 against the loser's 61.2 means it agreed with
   Pikzels' own output. That is real evidence the rubric points the right way.
2. It explains `EDGE_ARTEFACT`, which both verifiers keep raising on it: the
   hard white stroke around the cut-outs is Pikzels' styling. `CLAUDE.md`
   defines this channel's house style as *"feathered, **unstroked**"* — so the
   best-performing thumbnail on the channel is **not in the house style at
   all**, and the verifier is calling a deliberate winning choice a defect.
3. The back catalogue is therefore a MIXTURE of tools, not one construction
   improving or degrading. Any comparison across it that ignores which tool
   made each image is measuring the tool, not the craft. Which images were
   Pikzels-made is unrecorded and only Nathan knows it - ASK, do not assume.

**WINNER - `cSz-vkSwVlk`, 9,800 views, the channel's best Boyd long-form**
Two words of headline: "HE'S SCARED..." - all caps, huge, yellow, heavy black
stroke. Both subjects cut out and composited with a white edge stroke, isolated
from any background. Defendant in orange jail scrubs against the judge's black
robe. One large red arrow. **Two focal points and nothing else.**

**LOSER - `OGj_eLUXjrk`, 55 views**
Six words in sentence case - "No monkey business in my court!" - which reads as
a caption, not a headline. Both subjects left inside a raw uncropped courtroom
frame: ceiling, doors, an exit sign and a seated bystander all competing.
Neutral expression on the defendant. Milky, washed-out exposure. A tiny red
arrow floating in empty ceiling, pointing at nothing.

The winner is not better lit. It is **isolated, saturated, two-focal-point and
headline-cased.** The loser is a screenshot with words on it.

## The eight dimensions

Each scores 0-100 and must cite the observable thing that drove it. A score
without a stated mechanism is not a score.

1. **FOCAL CLARITY** - how many elements compete for the eye. One to three wins;
   the practitioner threads converge on this independently, and it is the
   strongest separation in this channel's own data (detail energy 443 for
   winners vs 834 for losers).
2. **SUBJECT ISOLATION** - are the subjects cut out and separated from their
   background, or embedded in a raw screenshot? This is the single biggest
   visible difference between the two anchors.
3. **EMOTIONAL READ** - does at least one face carry a strong, legible emotion
   recognisable in a glance? Neutral faces lose.
4. **HEADLINE FORCE** - word count (2-4 wins, 6+ loses), CASE (all-caps reads as
   a headline, sentence case reads as a caption), cap height, stroke weight,
   and colour contrast against what sits behind it.
5. **COLOUR SEPARATION** - does the subject separate from the background by hue
   and saturation, or does everything sit in one washed-out band?
6. **FEED SURVIVAL** - does it still read at 168x94? Score what survives the
   shrink, not what looks good at full size. (ThumbnailPeak's public teardown,
   2026-08-26, evaluates at exactly this size.)
7. **CURIOSITY GAP** - does it pose a question that only the video answers,
   without lying about what is in it?
8. **AUTHENTICITY** - does it read as real footage? The one thing the
   practitioner community mocks with actual consensus is AI-looking thumbnails
   ("you can always tell"). Real court footage is a structural advantage here
   and must never be traded away.

## HARD LIMIT ON FIXES — never alter what happened

Every fix you suggest must be one of: **choose a different frame**, **crop or
compose differently**, **change the type**, or **adjust grade / colour /
sharpness**. Nothing else.

**Never suggest changing a person's face, expression, pose, clothing or
surroundings, and never suggest generating or painting anything in.** This is
real court footage of real people on a monetised channel. Altering a
defendant's expression to look more afraid is fabricating evidence about a
named person in a criminal proceeding, and it also destroys the single
structural advantage this channel has: the practitioner community's one strong
consensus is that AI-looking thumbnails are obvious and worth mocking, and real
footage cannot be caught by that.

This is not advisory. Recorded 2026-08-29 because the local model, grading a
real build, returned: *"Enhance the defendant's facial expression (e.g.,
slightly wider eyes or a more distinct look)"*. An unattended repair loop acting
on that would have fabricated a defendant's face. If a face reads as too
neutral, the correct fix is **pick a different frame from the hearing** — the
expression that already happened, not one we invent.

## What this rubric is NOT allowed to claim

It cannot predict CTR and must never report a "viral percentage" as if it were
one. Views-over-channel-median is a proxy that also carries the title, the topic
and the timing. The honest claim is: *this looks like the thumbnails that
outperform, and here is the specific reason it does not.*

## Layer separation - the structural fix

`spec/NATHAN_RULES.md` R1-R15 are **constraints**: type never on a face, no
severed limb, her eyes never down. They are binary and non-negotiable, and they
are NOT success predictors. Scoring them as if they predicted views is exactly
why rho went negative. They gate; this rubric scores. The two never mix.
