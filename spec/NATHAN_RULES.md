> **Build numbers live in `spec/THUMBNAIL_SPEC.md`.** This file is the record
> of what he said and how often. That file is what the builder must obey.

# Nathan's rules — every one he has had to state, and what checks it

He said, 2026-08-29:

> "i noticed that i have to keep repeating myself multiple times for each and
> every one and you keep brining me the same exact flaws give or take with all of
> them and you have taken them all as a fix and you didnt rememeber them"

He is right, and the cause is structural rather than forgetfulness. Each
complaint was fixed **in the image in front of me** instead of being encoded as a
constraint checked on every build. Nothing then stopped it regressing, so he
became the regression test.

**This file is the fix.** Every rule he has stated is here with the measurement
that decides it and the count of how many times he has had to say it. A rule
without a runnable check is marked NOT AUTOMATED and that is itself a defect to
close, not a note to leave.

**Nothing ships until `tools/verify_build.py <work> <out.jpg>` prints
`BUILD_GATES PASS` and `tools/verify_thumb.py <out.jpg>` is clean.** Until
2026-09-01 this line named `verify_set.py --check all`, which never ran once on
a shipped build — see the checker registry at the end of this file, verified
by `tools/check_rules_refs.py`. A rule leaving this file requires him to say so
— not my judgement that it is obsolete.

---

## The count — where I have failed him most

**Recounted 2026-08-29 against all 1,156 sessions.** The figures below were
roughly half the truth, because the earlier mining missed his VOICE NOTES
(they arrive as transcription results, not user turns) and the live turns from
the same day. Corrected tallies: surgical cuts **8**, Boyd pale/washed **8**,
arrow **8**, spacing/size parity **8**, background rebuilt **7**, upscale AND
regenerate **6**, blown highlights **6**, reaction frame **6**.

| times said | rule | now checked by |
|---|---|---|
| 3 | Captions on the speaker's half | `tools/caption_short.py` turn-split + `tools/make_short.py` R35 VIOLATION |
| 3 | Surgical cuts, no severed limb | `tools/verify_build.py` gate K — longest visible straight edge ≤ 0.18 of the subject's span |
| 3 | The arrow must make sense | `_build_log.json` `arrow.on_face_px` — **WARNING only, not enforced**; ray-cast **NOT AUTOMATED** |
| 2 | A good reaction frame of the defendant | `tools/expression.py` measured pick (selftest in `tools/selftest_all.py`); `pick_reaction.py` is dead |
| 2 | Judge Boyd bright / washed out | `tools/verify_thumb.py` gate C on the canvas; the inside-the-matte check is **NOT AUTOMATED** (`verify_set.py --check pale` read a `.meta.json` nothing writes) |
| 1 | No bystander half-behind her | `tools/verify_build.py` gate L — judge-alpha coverage of any defendant-layer face outside 0.12–0.88 |
| 1 | Blown white spots | `tools/verify_build.py` gate J (faces) + `tools/verify_thumb.py` gate C; whole-frame blobs **NOT AUTOMATED** (`kill_hotspots.py` is dead) |
| 1 | Judge must not shrink | `thumb.py` solves `face_h_solved` and logs it; **no gate asserts the 300 px floor** |
| 2 | Upscale AND regenerate, never just upscale (R28) | HYPIR automated, Qwen **NOT** |
| 2 | No hard cuts - bleed off the edge (R29) | `tools/verify_build.py` gate K (added 2026-09-01; MONKEY_NEW fails it at x=1239); FIXED in the build by `thumb.cut()` growing the layer until the cliff leaves the canvas (`tools/thumb_pipeline.py --selftest`, `selftest_cut_edge`) |
| 1 | Rebuild the background when geometry changes (R30) | **NOT AUTOMATED** |
| 2 | Match layer brightness / white balance (R31) | `tools/verify_thumb.py` gate C + `tools/verify_build.py` gate F (face repaint) |
| 3 | Leave the grade alone - vibrance, not saturation (R32) | `tools/verify_build.py` gate I (skin chroma band); `verify_set.py` luma/S numbers retired — they contradict `config/quality_floor.json` |

---

## Rules, with their checks

### R1 — Type never on a face or body
> "the words should never be on defendants or judges face or body"

CHECK: `tools/thumb.py` `ink_vs_subjects()` at the end of every build, three
numbers in `_build_log.json` (2026-09-01, replacing one number that counted the
TITLE alone while the skill said it covered the kicker too):
- `title_on_subject_px` — title ink over either placed alpha > 0.4. Asserted 0.
- `kicker_on_face_px` — kicker ink inside either face box. Asserted 0. The
  kicker solver has pushed itself below the faces since 2026-08-31; nothing
  measured the result until now.
- `kicker_on_subject_px` — kicker ink over either BODY. **Logged, not
  asserted.** Measured on the five accepted builds: judge 17.7k–30.8k px and
  defendant 13.3k–41.0k px on every one — the kicker band is the bottom of the
  frame and both bodies live there. He accepted all five, so "or body" is
  satisfied by the title and NOT by the kicker; that is the house style, said
  out loud here rather than hidden behind a 0.
`type_on_subject_px` stays for its readers and equals the two asserted numbers
summed. Controls in `tools/thumb_pipeline.py --selftest`
(`selftest_ink_vs_subjects`). The outline method (a >238 core with a <45 pixel
within 17px, never brightness alone — brightness measured the ceiling and a
white collar) lived in `verify_set.py --check type`, which nothing runs any more.

### R2 — Surgical cuts, no severed limb
> "you cut the defendants whole arm off ... theres have to be surgical cuts not slop"
> "still could be more surgical way over all theres just too many little things"

CHECK: `tools/verify_build.py` gate K, on `_placed_alpha_*.png`. The longest
perfectly straight visible edge of a subject's silhouette (columns or rows, with
type ink and the other subject masked out) must be ≤ 0.18 of that subject's
span. Measured on the five accepted builds: 0.05–0.14; the 55%-drop rule this
replaced lived in `verify_set.py --check limb`, which nothing runs. The builder
additionally re-mattes after any move and REJECTS a move losing over 1% of area.

### R3 — The arrow must make sense
> "you need to rememeber t5o make the red arrow actually make sense"
> "how did you miss that???"

CHECK: **NOT ENFORCED.** `tools/thumb.py` writes `arrow.on_face_px` and
`arrow.on_any_face_px` to `_build_log.json` and prints a WARNING when they are
non-zero — it does not refuse. Zero overlap is necessary and NOT sufficient — a
build once scored a perfect 0% while aimed at empty ceiling. The ray cast from
the tip that must strike the defendant is **NOT AUTOMATED**. The 1500–6000 px
size band from `verify_set.py --check arrow` is retired: it was never run on a
shipped build.

Added 2026-09-02 (TORRES): the plate's gallery faces - every YuNet detection
below `SUBJECT_FACE_MIN_AREA` outside the subject layers - are a SOFT cost in
the arrow's 2D search (`ARROW_GALLERY_COST`), not a block. Before this the tip
sat on the man seated at counsel table between the two subjects: pixel-perfect
zero overlap with both subjects, and pointing at a stranger. Blocking gallery
faces outright would leave SANCHEZ (9-12 of them in the plate) with no clear
spot, so the cost is small enough that a subject or the type always wins and
large enough to slide off a stranger when a clear spot exists nearby. The log
records `arrow_placed.on_gallery_px` (0 on TORRES after the change; a non-zero
value is reported, not refused - the aim itself is still NOT AUTOMATED).

### R4 — Captions on the speaking person's half
> "everytime the defendant talks the captions must be on his side of the screen and when judge boyd talks her captions are on her side"
> "i need you to master the captions too because i told you"
> "captyiosn are still not 100% correct on the speakers side"

CHECK: blocks are forced to end at speaker turns so none straddles two voices;
attribution is audio-visual correlation (9/9 on hand-labelled windows against
4/9 for raw motion); verified on the RENDERED file, not the detector.

### R5 — A good reaction frame of the defendant
> "i need you to always make sure you get a good frame of the defandant like with a good reaction"

`pick_reaction.py` ranks by sharpness gate + motion. **NOT AUTOMATED into the
routine — this is an open defect.**

### R6 — Judge Boyd must not look washed out
> "in sanchez thumbnail boyd still looks so bright and pale, same thing in offer up"
> "boyds cut out looks washed out it needs to look good compare to the defendant"

CHECK: **NOT AUTOMATED inside her matte.** `verify_set.py --check pale` read a
`.meta.json` that nothing writes, so it never measured anything. What runs:
`tools/verify_thumb.py` gate C on the canvas, and `_build_log.json`
`boyd.L_before` / `skin_final.L` against `config/quality_floor.json`
`subject_L` (R40). Her matte interior still has to be measured, because: Canvas metrics cannot see her: OFFERUP shipped at mean luma 114.2 —
DARKER than both files he approved — and he still called it pale, because the
plate supplies the deep blacks while her layer floats 24–37 code values above
them. Measured: her black floor 28.2 against the plate's 0.1.

### R7 — Her eyes level and directed, never down
> frames where she looks down are rejected; a hand mid-gesture adds drama, a hand resting on her chin does not

**NOT AUTOMATED.** Three automated gaze metrics all failed to reproduce his eye.
Stays a contact-sheet choice. Saying so is the honest state; inventing a metric
that does not work is worse.

### R8 — No bystander half-behind her
> "it looks weird how his lawyer ir right behind judge boyd"

CHECK: `verify_set.py --check bystander`. Fully covered is fine and fully clear
is fine; 12%–88% coverage is the defect band.

### R9 — Judge Boyd must not shrink
> "the judge shrank and now looks weird"

CHECK: her face height must be ≥300px (Thompson 385, shipped CARTHIEF 336, the
collapsed failure 208). The builder REFUSES and tries another frame rather than
shipping her small.

### R10 — No blown white spots
> "the super bright white spots need to be fixed some how"

CHECK: on faces, `tools/verify_build.py` gate J and `tools/verify_thumb.py`
gate C. Whole-frame blobs over 250 px are **NOT AUTOMATED** — `kill_hotspots.py
--check <dir>` exists in `scripts/` and nothing on the build path runs it. The
fix is LOCAL to each blob; a global knee moved the mean 5.6 points and he could not see
any difference, because it spread the change everywhere and fixed nothing.

### R11 — Profanity: audio yes, text never
Leave it in the audio, censor it in every text surface — captions, titles,
thumbnails, descriptions, on-screen cards, docs.

### R12 — Never "Made for Kids"
Declare Not Made for Kids on the channel, uploads and streams.

### R13 — Publishing is a hard stop
Uploading, posting or making anything public requires his confirmation in that
turn. Rendering locally does not.

### R14 — Never the defendant's name in a title

### R15 — Court footage is public record
Do not invent rights, defamation or privacy restrictions. Quote the actual text
of a real restriction or say it has not been checked.


---

## Rules found by mining all 87 of his messages (2026-08-29)

He asked: *"all the stuff ive been telling you since weve been making them can you
go back and take note??"* — so the whole transcript was extracted rather than
worked from memory. These are the ones that were NEVER encoded. Several explain
failures that kept recurring.

### R16 — A quote must be what she ACTUALLY said
> "Not 100% of the time is it 100% what she really said"

His words, early on, about thumbnail copy. Any line in quotes must appear
verbatim in the transcript. **NOT AUTOMATED** — the only script that ever
grepped the transcript and REFUSED (`make_thumbnail_quiet.py`) is dead, and
`tools/thumb.py` does not check. R41's `tools/check_title.py` is where this
lands. **This is an open defect.**

### R17 — Colour must match ACROSS videos, not just look right alone
> "did you edit the colors on those to match with the last one we did?"

Asked on 2026-08-27 and I have broken it repeatedly since: CARTHIEF 118.6,
SANCHEZ 147.1, OFFERUP 155.9 mean luma — three videos of the same channel that do
not match each other. This is the ROOT of the "really brifht" complaint two days
later. A per-image grade that ignores the previous videos is the bug.

CHECK: the envelope in `config/quality_floor.json` (`subject_L`, `background_L`,
`separation_dL` per accepted case), enforced by R40's `tools/floor_stamp.py`.
The `verify_set.py --check luma` band (122 ± 12) is retired: measured
2026-09-01, four of the five ACCEPTED builds fail it (CARTHIEF 108.5, MONKEY
109.2, OFFERUP 102.3, THOMPSON 109.1) — a band that rejects what he approved is
the wrong band. NOT SUFFICIENT on its own; see R6.

### R18 — It must look 100% real
> "still looking 100% real just more about the placing of stuff and lighting"
> "that trhumnail is slop0 take nots from audit the courts thumbnails"

No effect that reads as a graphic. This is why the cut-out carries NO outline
stroke (0 of 12 competitor thumbnails have one), why the magnifier construction
was rejected (two Judge Boyds in one frame), and why a severed limb is fatal
rather than cosmetic.

### R19 — Audit the Court is the placement reference
> "okay now look at their placment all you have to do is literally copy all of it but with the otther stuff"

Their geometry is measured in `research/reference/competitor/thumbs/` (12 JPEGs,
view count in the filename). The shipped Thompson thumbnail is our own clone of
it and is the spec: type x23 y31, cap 71px = 0.0986 H, white→yellow at 0.466 W,
arrow 105x76 = 0.41% of frame with ZERO pixels on a person.

### R20 — The arrow adapts to each thumbnail
> "can you make the red arrows better fiiting in each thumbnail? like maybe move it or turn it or make it bigger depending on the thumbnail"

Not a fixed position. Angle, size and placement are solved per image against
where the people actually are. Covered by R3's check plus the builder's
full-circle search for clear space.

### R21 — Type must not overlap either person
> "try to fit \"in my court!\" without it overlapping on either of them"

Stronger than R1: not just faces — neither person. Type sits in clear space.

### R22 — Captions: not small, not long
> "i dont like how theyre small and long on the short"
> "i like d (ay yo?) but still needs to be bigger ( AYYYOOOO??)"
> "also bump down the captions to c instead of d"

Settled at 156px ("C"), max 18 chars / 4 words per block, after he saw
92/124/156/190/224/258/296 at 1:1.

### R23 — The font must not look low quality
> "yes and if you look the font is off and looks way lower quality"

TTT Headline = Archivo frozen at weight 900 / width 70. Identified by matching
the shipped Thompson quote: 26 characters spanning 1049px at cap 71. Montserrat
Black gives cap 52 at that width and Archivo SemiCond SemiBold gives 68 — both
far too light. Do not substitute.

### R24 — Videos must actually play
> "btw it keeps saying something wenty wrong when you try to play a viodeo"

`-pix_fmt yuv420p`, always. Four shorts shipped as High 4:4:4 Predictive, which
no consumer hardware decoder plays. `tools/make_short.py` encodes with it and
`tools/short_engine.py` verifies `pix_fmt == yuv420p` on the rendered file
(`make_short_auto.py`, where this was first gated, is dead).

### R25 — Frame choice, in his own reasoning
> "i like C on car theif A and B on sanchez and C on offerup because of how jusge boyd is positiononed in them because the other shots of her dont make sense or are bad because shes not looking in some but in sanchez case i picked a and b becase her hand added a little more drama"

Two separate criteria, and he gave the reason for each: her eyes must be
DIRECTED (not looking away or down), and a hand MID-GESTURE adds drama. See R7 —
still not automated.

### R26 — A/B test titles and thumbnails
> "Okay and also ab test all the captions and thumbnails for these videos"

YouTube Test & Compare optimises WATCH TIME, not CTR — worth saying out loud
whenever a test is proposed, because it is not what he is asking it to measure.

---

## Asked and never answered

### Q1 — Ambiance and zooms on the shorts
> "also what do you think aboyut the shorts are they missing ambiance?? maybe little zooms on thhe hook or key words or dramatic zooms?? idk what do you think dont anchor anything"

Asked 2026-08-28. **Never answered.** He explicitly asked for an opinion and
said not to anchor him. Still open.

---

## How this file is used

1. Before reporting any thumbnail or short as done, run the checks.
2. When he states a new rule, ADD IT HERE with its check in the same turn — not
   after it has been broken twice.
3. When a rule cannot be automated, say so out loud in the report. A silent
   NOT AUTOMATED is how these regressed in the first place.

### R27 — Every position is SOLVED per frame, never a fixed value

Nathan, 2026-08-29, verbatim: *"every time you have to move anyones position
just know it shouldnt be something set but choosen based off of what you have to
work with"* — said while asking, of the GTA thumbnail, that the defendant sit
closer to the middle "so hes not too far to boyd or too far from his attoryny".

**The rule:** any placement — how far the defendant scoots, where the arrow tip
goes, the judge's headroom, the gap between subjects — is DERIVED from what is
in that particular frame. A constant that happened to look right on one hearing
is not a setting, it is a coincidence that will be wrong on the next one.

**Why this keeps biting, measured:** the arrow tip was a fixed fraction and
landed on a defendant's face three separate times. `subject_side` defaults to
"right" and Judge Boyd is on the LEFT in CARTHIEF, so unattended it traces the
wrong person. `--auto-plate` on CARTHIEF ranked every candidate at 0.0% clear.
Three separate constants standing in for a measurement.

**The check:** for the defendant, solve for the midpoint of the gap between the
judge's inner edge and the attorney rather than applying a fixed pixel shift;
clamp to `--max-area-loss` so no limb is ever severed; and PRINT the derived
value together with the two edges it came from, so a wrong solve shows up in the
log instead of shipping silently.

**Status: NOT AUTOMATED YET.** The old `scoot()` in `thumb_Q3_detail.py` took a
`shift` the caller chose; that script is dead and `tools/thumb.py` has no
spacing solver at all. Until the solver exists, say out loud every time a
position was set by hand rather than derived — a silent constant is how all
three failures above happened.

---

## Rules from the 29 Aug screen recording + the SANCHEZ session

Source: `D:\Screen Recordings\screen-2026-08-29_101437.mp4` (9:56, narrated) and
his live notes while reviewing SANCHEZ the same afternoon. Transcript:
`docs/transcripts/2026-08-29_thumbnail-lesson.txt`. His stated goal:

> *"this is not something you're anchoring in, this is - I'm showing you this so
> you can learn how to make these thumbnails a hundred percent by yourself."*

> *"I will pass this overall, but really I wouldn't be happy if this was
> happening autonomously."*

### R28 - Upscale AND regenerate, every time, before any other edit

> *"I gave you an open source thing. You need to use that every single time. The
> open source upscaler gets used every single time, and once it's upscaled then
> you can add the outlines, you can change the colors... then you could lay this over."*

> *"you need to upscale Judge Boyd - and not just upscale, you need to actually
> regenerate the picture."*

He showed a 3-up off his own screen: `1 REAL raw tile 612x338` / `2 MY SDXL
attempt (slop)` / `3 HYPIR restore 4x 2448x1352`. **Slop is his word for the SDXL
attempt.** HYPIR is at `D:\AI-Models\HYPIR`; working invocation in
`tools/run_hypir.sh`. Licence is NON-COMMERCIAL and he has been told and said
*"if it works then use it"* - decided, do not re-litigate.

**But HYPIR alone is not the whole instruction.** 2026-08-29 he said the second
half had been dropped: *"like when you go tell an AI, make this picture look like
it was taken in 4k, and it's remaking the person to its best ability... it's a
remade AI picture of the person that looks hyper realistic. I gave you that local
stuff to do that already."* That is **Qwen-Image-Edit 2511**, which was sitting
on disk unwired the whole time:

| | |
|---|---|
| unet | `D:/AI-Models/comfyui/unet/qwen-image-edit-2511-Q5_K_M.gguf` |
| text encoder | `text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors` |
| vae | `vae/qwen_image_vae.safetensors` |
| lora | `loras/Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors` |

Order is fixed: **HYPIR restore -> Qwen regenerate -> cut -> composite -> grade.**

CHECK: assert both stages ran on every person layer and log the tile sizes.
**Status: HYPIR automated; Qwen NOT AUTOMATED YET** (ComfyUI had no venv, no
`extra_model_paths.yaml` and no GGUF node until 2026-08-29).

### R29 - No hard cuts. Every cut edge falls outside the frame

> *"There should never be, like, showing hard cuts in the thumbnail... what you
> really could have done was expanded her to make her bigger, and the top of her
> body could have touched the screen. It should always touch the screen or the
> edges, and it should not show any hard cuts like that."*

A matte that stops inside the frame reads as a sticker. **The fix is always
SCALE** - never a stretched, mirrored or cloned extension to reach the edge.

Precisely: a *cut* edge is one inherited from the source tile boundary (the Zoom
frame ending at her chest). Those must land outside the canvas. A subject's real
left/right silhouette may sit inside the frame - an earlier "must touch 2 edges"
version of this rule was too strict and forced her absurdly large.

CHECK: `tools/verify_build.py` gate K — a source-boundary edge that lands inside
the canvas shows up as a long perfectly straight run in the placed alpha.
Validated 2026-09-01: MONKEY_NEW fails with a 203 px vertical cut at x=1239
(Boyd's right shoulder, chair visible beyond it, 0.38 of her span); the five
accepted builds measure 0.05–0.14.

FIX, in the compositor (2026-09-01): `tools/thumb.py` `find_cliff()` finds a
source-boundary cliff in a layer's alpha (a straight far-side run of at least
gate K's 0.18 of the span) and `Thumb.cut()` grows the layer in 3% steps until
that cliff is outside the canvas - scale, exactly as he said. Logged per layer
in `_build_log.json["cut_edge"]` (`grew`, `cliffs`, `unresolvable`); proved by
`tools/thumb_pipeline.py --selftest` (`selftest_cut_edge`). MONKEY_S, built
this way: Boyd's right cliff (494 of 1250 rows at column 1279) -> layer grown
x1.305, gate K 0.03. A mirrored seam-bleed strip (`seam_bleed`, the MONKEY_K
build) was written the same day and REMOVED - it is the "mirrored or cloned
extension" the rule forbids.

Every text element lives in the case file, like the title. MONKEY_K rebuilt
without "YOUR OWNER HATES YOU" because the kicker had only ever been passed on
the command line; the monkey grew into the space the kicker reserves and the
build silently changed shape. `kicker` and `kicker_split` are now read from
`config/cases.json`, and a split that is not a prefix of the kicker refuses the
build (`KICKER_SPLIT_MISMATCH`) instead of quietly rendering all-yellow.

### R30 - A change that moves the subject means the background is REBUILT

> *"the background, it's just not what it should be. And I know I told you to make
> her smaller, so that's probably why the background got all distorted. So instead,
> next time, if I tell you to make a change like that where it's gonna affect the
> background, you have to go back and just redo the background."* - 2026-08-29

Any change to scale, crop, or position invalidates the background. Regenerate it
at the new geometry - never scale, stretch, or letterbox the one already built.
This applies to his *own* mid-flight requests: "make her smaller" is an
instruction to rebuild, not to resize what is on screen.

CHECK: the background must be produced from the source plate at the final crop
geometry in the same run. **Status: NOT AUTOMATED YET.**

### R31 - Match the two layers, and the defendant's side is the reference

**CORRECTION 2026-08-29.** An earlier version of this rule claimed he REVERSED
himself on Judge Boyd's tint, and marked the morning's "leave it alone" note as
superseded. That was my misreading and it is withdrawn.

Checked against all 126 dated verdicts: *"honestly we don't have to do that, I
kind of like how it is right now"* was a **pass on one image**, sitting between
rejections before it and after it. He has complained that Boyd is pale, washed
out, or blue against the defendant's side **eight separate times** - tied for the
most-repeated complaint on record. There was never a reversal to supersede.

> *"only pay attention to the defendant and attorney the way their colors are.
> Idk why but judge boyd has that bluish tint and that's not how I like it but
> the other side is good"*

> *"now the defendant looks dark - you're supposed to have the defendant as bright
> as the judge"*

1. **White balance Boyd TO the defendant plate**, never the reverse. Cause is
   known and is not a bug to chase: *"there was two different cameras filming this
   and Judge Boyd at this time."*
2. **Equalise face brightness.** Lift the defendant UP to the judge - never pull
   the judge down. Measured on SANCHEZ: defendant face 120.7 vs judge 146-151.
3. The mechanism that actually caused the washed-out skin was NOT the brightness
   match on its own - a linear RGB multiply is saturation-invariant. It was the
   per-channel highlight knee, running six times per build, measured at -11 to -14
   saturation points on skin highlights, plus clipping.

CHECK: `tools/verify_thumb.py` gate C (subject face median L*, approved 144-160)
and per-layer face-box luma within 8.

CHECK (repaint, added 2026-09-01, restructured 2026-09-02): `tools/verify_build.py`
gate F - each face's skin chroma drift from its OWN raw crop (`judge_raw.png`,
`defendant_raw.png`), and the two drifts must agree within
`MAX_CHROMA_IMBALANCE = 2.5`. The accepted THOMPSON measures 10.5 / 8.1,
imbalance 2.4. A face that is repainted harder than the other is the "bluish
tint" complaint by another route.

**Measured conflict, 2026-09-02, TORRES.** The last skin stage in
`tools/thumb.py` drove BOTH faces to the same absolute chroma
(`SKIN_CHROMA_TARGET` 20.6). With sources 12.3 (Boyd, library cutout) and 16.5
(Torres) that is drift 7.5 vs 3.4 - imbalance 4.1, gate F refused it, and no
amount of tuning the pull (0.35 / 0.15 / 0.0 all failed) could pass it, because
the two rules contradicted each other whenever the sources sat more than ~2.5
apart. THOMPSON had only passed because its sources happened to sit close. The
fix is structural, not a parameter: the stage now applies ONE SHARED LIFT - the
pair's mean lands on the target and each face keeps its own offset (TORRES:
lift +5.7, goals 19.0 / 22.2, drift 5.7 / 4.4, imbalance 1.3, PASS). The build
log records it as `skin_chroma_lift`. Gate I (R32) still bounds the absolute
band, so a very muted pair cannot hide behind parity.

### R32 - Leave the grade alone. Vibrance, not saturation

Measured across all 12 Audit the Court thumbnails: saturation 56-130 (mean ~90),
luma 81-144, contrast sd 55-79, and **12/12 read brighter at the top than the
bottom**. No vignette, no scrim, no saturation push.

> *"the color is supposed to be a little saturated but more than anything it's
> supposed to pop"* ... then, after I pushed saturation: *"that's not the right
> pop I was talking about"* ... then *"saturation might have been a tiny bit too
> much, I think vibrancy should be better"*

Pop is **local contrast and subject separation**, not chroma. Use vibrance (lift
the muted, leave the loud alone). Targets come from `work/repair/HS_REMAKE.jpg`,
which he picked himself - *"the middle one here is a good color"* - measured on
the DEFENDANT side only: **S 99.0, luma 85.6, sd 70.3, face luma 108.7**.

Also: **blown highlights are a defect.** SANCHEZ measured 36.6% of the top third
over 215 before recovery. He called it *"the heavy over exposure from the
courtroom lights behind her."*

CHECK: skin chroma — `tools/verify_build.py` gate I against the measured band,
and `config/quality_floor.json` `skin_chroma` per accepted case (R40). The
`verify_set.py` numbers above are retired: its 6.5 chroma ceiling fails three of
the five ACCEPTED builds (MONKEY 19.3, SANCHEZ 20.5, THOMPSON 26.8). The >215
fraction in the top third is **NOT AUTOMATED**.

### R33 - Type: top of frame, sentence case, pure primary yellow

From the measured Audit set: cap height **0.0773 H (~56px)**, yellow **#FEFB03**
(a pure primary - not gold, not amber), white **#FFFFFF**, arrow red **#FD0101**.
**Zero all-caps in 12/12** - every title is a sentence-case accusatory quote, 4-9
words.

**Corrected 2026-09-01:** the earlier "stroke 9.5px pure black" was wrong. Zoomed
on the Audit's top-viewed thumbnails (`scratchpad/audit_top_zoom.jpg`) the edge
is a **soft dark halo with no hard outline** on a wide grotesque; the Audit's
CURRENT 2026 look (`scratchpad/audit_now_zoom.jpg`) is Anton-class caps with a
**~5 px stroke plus a soft halo**. What was measured as a 9.5 px stroke was the
halo's dark core. The sentence-case rule stands; the stroke number does not.

He asked 2026-08-29 for *"a little bit more click baity type font"* and options to
pick from; the options are the presets in R45. Whatever is picked must stay
sentence case on the title (the kicker is deliberately ALL CAPS).

CHECK: **NOT AUTOMATED.** `tools/thumb.py` records `type.size` / `type.cap` in
`_build_log.json` but nothing asserts cap height or fill; the check in
`verify_set.py --check type` never ran on a shipped build. Sentence case on the
title is asserted by nothing - the title text comes from `config/cases.json`
as written.


## R34 — A caption word is NEVER readable before it is spoken
*Stated 2026-08-29, once.* His words:

> "where it really matters is for example when Judge Boyd says because you're
> not in his life pause pause pause pause pause, and then the girl goes exactly
> ... it says cause you're not in his life and then it shows the word exactly
> like I already knew she was gonna say that see that's where it really matters
> right there in those type of moments"

**The defect was structural, not stylistic.** `build_snap` painted every word of
a card at `card[0].start`. Measured on SANCHEZ: card `"life. Exactly."` ran
3.20→4.12 while "Exactly." is spoken at 3.88 — the punchline was legible **0.68s
early**, so every reaction, every gotcha and every landed line in the whole short
arrived pre-announced. This is the single highest-value caption defect found so
far: it does not make the captions look bad, it makes the CONTENT not work.

**Rule:** a word may be drawn no earlier than its own `start`. Cards still group
(he approved 3 words / ~12 chars), but grouping is a LAYOUT decision and must
never be a TIMING decision.

**CHECK** — `caption_short.REVEAL` must not be `"off"`. Automated proof, run on
any short before it is called done:

    for every card, for every word w after the first:
        assert no Dialogue event containing w has start < w.start

Measured proof for SANCHEZ, frame diff at t=3.50 (before "Exactly." is spoken):
`off` vs `reserve` = 20,778 px differ, bbox x444-742 — that block of pixels IS
the spoiler. At t=4.00 the two are identical (12 px, encoder noise).

Two ways to satisfy it, both implemented:
  - `reserve` — full card laid out, unspoken words at `\alpha&HFF&`. Nothing
    moves, but the visible text sits off-centre until the card completes.
  - `build`   — only spoken words drawn; the line re-centres as it grows.

**Do not "fix" this by shortening cards.** One word per card satisfies the timing
but is the karaoke look he rejected on 2026-08-29 ("like it's kereokee or
something"). Grouping stays; only the paint time changes.

## R35 — A caption card never crosses a sentence or a speaker turn
*Stated 2026-08-29, and it supersedes R34 as the real cause.* His words:

> "let's just say Judge Boyd is talking, and then the defendant starts talking.
> And their beginning of the other person's sentence is at the end of the
> sentence in the video. So, like, you kind of already hear what they say.
> Basically, you need to learn when to start the sentences because I don't
> really want that pop in, pop out effect all fast like that. That's not what
> I'm saying. Like, yes, it is nice, but that's not all it's about."

**Read that last line carefully.** R34's per-word reveal was a real fix for a
real defect, and he still rejected it, because it treated a SEGMENTATION bug as
an ANIMATION problem. `cards()` cut purely on a character budget, so a card
could hold the tail of one speaker's sentence plus the head of the other's.
Measured on SANCHEZ: 7 of 78 cards straddled a sentence end, 2 mixed two
speakers, the worst being `"life. Exactly."` — Judge Boyd's last word and the
defendant's entire reply in one card. No reveal trick repairs that; the boundary
is simply in the wrong place.

**Rule:** a card boundary is forced at
  1. terminal punctuation `. ! ?`
  2. a pause longer than 0.60s
  3. **a change of speaker**

The character budget only ever splits *within* one speaker's sentence.

**Speaker is measured, not guessed** — `tools/speakers.py`. The two tiles are
locked-off cameras, so whoever's mouth is moving is talking: face box per tile
(OpenCV Haar; mediapipe 1.x dropped `solutions`), mouth ROI = lower 45%, motion
energy per frame, compared **per sentence**. Per-WORD comparison measured 28
speaker changes in 49s — flapping every 0.3s through a continuous monologue,
because frame differencing sees head turns and hands too. Per-sentence gives 6,
and the turn structure matches the court record.

**CHECK** — `make_short.py` raises `R35 VIOLATION` unless
`straddle == 0 and mixed-speaker == 0`. Measured on V11: 81 cards, 0 and 0.
Known-answer test the detector must pass: `"life."` = top (bench),
`"Exactly."` = bot (defendant).

**Do not** reach for a reveal/fade/karaoke effect when a caption feels like it
gives something away. Check the card boundaries first.

## R36 — Cards break where the PHRASE ends, not where the counter runs out
*Stated 2026-08-29:* **"Those captions don't match. Now they just feel off."**

R35 fixed sentence and speaker boundaries and he still rejected it, because
inside a sentence the cards were still cut by a character counter. Measured on
V11's 81 cards, that produced:

    "that, Your" | "Honor, but I"        "tell people, if" | "you're not"
    "And I don't" | "know if you"        "for your" | "children."
    "You haven't" | "learned" (0.22s)    "I am, Your" | "Honor." (0.14s)

25 of 81 cards ended on a stranded function word. A counter cannot know where a
phrase ends. Checked first and ruled out: transcript accuracy (two independent
Whisper passes agree 98.7%) and sync (median 60 ms). It was purely phrasing.

**Rule:** boundaries inside a sentence are chosen by minimising a cost, not by a
counter — `caption_short.split_phrase()`, an exact DP over the sentence.

    - the speaker's own pause is the strongest cue and is a bonus
    - a comma / semicolon is a bonus
    - ending on a glue word (a, the, your, for, and, to, is, you're, ...) is a
      heavy penalty  -> GLUE_FORWARD
    - "Your Honor" / "Yes sir" and similar can never be split -> KEEP_TOGETHER
    - a card under 0.42s on screen is penalised as a flash

**Budget, measured — do not widen further:**

| max_chars | max_words | cards | mean ch | ends-on-glue | flashes |
|---|---|---|---|---|---|
| 18 | 3 | 77 | 12.1 | 25 | 3 |
| **20** | **4** | **66** | **14.3** | **11** | **1** |
| 22 | 4 | 63 | 15.0 | 10 | 1 |
| 24 | 4 | 61 | 15.5 |  9 | 2 |

20/4 buys 14 fewer bad breaks for 2.2 characters of line length. Past that it
stops paying and the lines start creeping toward the edges, which he has
rejected twice.

**CHECK** — `make_short.py` prints `ends-on-glue`. Investigate above ~15 on a
50s clip.

## R37 — Caption entrance is BLUR. No scale animation, ever.
*Settled 2026-08-29 by pick, after three rejections.*

He rejected `scale` ("popping all big on every syllable"), then `bounce`, then
the whole family — *"I don't really want that pop in, pop out effect all fast
like that"*, then *"I just don't like the animation"*. Four options were shown
using four different properties instead of four tunings of the same one:

    1 none   hard cut, no animation
    2 fade   opacity only, 70 ms
    3 lift   rises 20 px into place, 130 ms
    4 blur   defocus 6 -> 0 over 120 ms, with a 60 ms fade   <-- PICKED

Tag: `{\pos(cx,seam)\fad(60,60)\blur6\t(0,120,\blur0)}`

**Never re-introduce `\fscx`/`\fscy` on a caption entrance.** It has been
rejected three separate times. If a future note says the captions feel dead, the
answer is a different PROPERTY, not a bigger scale move — that is the mistake
that cost three rounds here.

Lesson recorded alongside: showing four options that differ in KIND took one
round. Showing variations of one effect took three.

## R38 — Their heads must be LEVEL with Judge Boyd's head
*Stated 2026-08-30:* **"you kept making this choice to put the defendant so low
and idk why. I never said that. Their head should be level with Boyd's head."**

"You kept making this choice" — it was in every build. Measured across the set:

| | face-top delta |
|---|---|
| SANCHEZ_APPROVED (his own approved file) | **0 px** |
| MONKEY | +10 |
| THOMPSON | -12 |
| OFFERUP | +25 |
| CARTHIEF | +33 |

The one he approved has them level. Everything built since drifted.

**It is not an eye-line problem.** The eye lines were already level to within
1-4px (CARTHIEF 400.6 vs 401.8; SANCHEZ 372.3 vs 376.3). It is HEAD EXTENT:
Boyd's bob puts her silhouette top far above the defendant's, so with faces
centred she still reads as higher and he reads as sunk.

**Rule:** both subjects are placed by the TOP OF THE HEAD, on the same row,
`HEAD_GAP = 14` px below the title's lowest ink. `cut(..., top_y=)` does this and
`build()` asserts `head_top_delta <= 2`.

This replaced an 8-pass nudge loop that pushed subjects down only until the
HIGHER of the two cleared the title — which by construction left the other one
low by however much their hair differed. The loop was the mechanism of the bug.

**Anchor on the SUBJECT's head, not the layer's topmost pixel.** First attempt
anchored on `alpha.min()` over the whole cut-out; CARTHIEF's cut-out also
contains the attorney standing behind, so his head became the anchor and the
thumbnail showed the wrong man — while the heads-level assert reported delta 0.
Search only the columns within 0.9x the face width of the subject's own face.

---

## R39 — judge the thumbnail at 168x94, never at 1280, and never against itself

**Stated by:** nobody. I found it on 2026-08-30 by finally rendering our four
thumbnails at the size YouTube serves them, beside Audit the Court's four
biggest, and looking at the sheet. It is the direct answer to his
2026-08-30 complaint: *"it's like you don't actually visually see it and judge
it harsh visually before confirming ... you have no sense of taste."*

He was describing a real mechanism, not a vibe. I had been confirming every
thumbnail as a 1280px file on a 49" OLED. The sidebar serves 168x94.

**Measured, same judge, same courtroom:**

| | ours (n=4) | Audit the Court (n=12) |
|---|---|---|
| text bands | 1, 1, 2, 3 | 10 of 12 have exactly ONE |
| ink cover | 0.11 0.11 0.17 0.20 | their four biggest: 0.09 0.05 0.07 0.10 |
| layout self-similarity | mean 0.32, max 0.46 | mean 0.09, max 0.26 |
| structure surviving downscale (r) | mean 0.749 | mean 0.840 |
| feed attention share | 8.6-9.8% | median 7.4% |

Our thumbnails do NOT fail to get noticed - they out-pull the competitor median.
They fail by being **the same image four times**: identical headline band,
identical red arrow angle, identical yellow kicker, identical two-up head crop.
A channel whose thumbnails are a template competes against its own back
catalogue, and attention in a feed goes to whatever breaks the pattern of its
neighbours.

**CHECK:** `python tools/thumbeng/variety.py OUT.jpg` — layout similarity at
168×94 against everything already shipped, limit 0.30;
`python tools/thumbeng/variety.py --selftest`. Text bands and ink cover are
measured by R43's `tools/check_clutter.py`. `python tools/sidebar_sheet.py`
builds the 168 px comparison sheet (manual). The `tools/verify_variety.py` and
`tools/thumb_measure.py` this line used to name never existed on disk.

**All five accepted thumbnails FAIL this gate** — pairwise 0.23–0.46, max
MONKEY–THOMPSON 0.455 (measured 2026-09-01). That is the finding, not a bug, and
it is why variety is NOT a ship gate: a gate that rejects the set he approved is
calibrated to the competitor, not to him. It stays a report.

**Correlation caveat, stated so it is not overclaimed later:** across the same 12
competitor thumbnails, NO single measured property (dominance, roundtrip r,
figure/ground, face size, face count, saturation, warmth, luminance, balance)
correlates with view count at n=12 significance (all |rho| < 0.587). View count
is not CTR. So these thresholds describe what winners in this niche look like -
they do not prove the image caused the win, and only Nathan's own Studio CTR
can settle that.

### R40 — A floor change means every pending artifact is rebuilt

> "Okay but that short was made off the old rules or whatever and should be
> made with our new ones how me did all the steps for the most recent ones u
> made" — 2026-08-31 17:17

The OFFERUP short had been rendered before `config/short_floor.json` existed
and I was about to post it as-is. An artifact carries the rules it was built
under; if the floor moved after the render, the file is stale even though it
plays. Nothing on disk said which rules a file was built with, so nothing could
refuse it.

CHECK: `tools/floor_stamp.py`. Every thumbnail build writes the SHA-256 of
`config/quality_floor.json` + `spec/THUMBNAIL_SPEC.md` into
`_build_log.json["floor"]`; every short writes the hash of
`config/short_floor.json` to a `<short>.floor.json` sidecar.
`python tools/floor_stamp.py check <artifact>` refuses when the stamp is not
the current hash, and the youtube-channel skill runs it before anything is
posted (§1d).

### R41 — Titles are hooks, not descriptions

> "Those titles are weak" — #173, 2026-08-31
> "I guess a/b test them but idk I think title could be better do 3 different
> ones" — #174

My titles described what the video was about. The evidence already in hand:
his best recent performer withholds the ending; the worst states the sentence;
on the reference channel a 2–5 word specific act beat a summary 200×. The
measured house constants are in `spec/PACKAGING.md`: 50–65 characters with a
hard ceiling of 70, name the judge (80% of the winning top 40 do), 2–4
emphasised words that are the beats — actor, verb, stake.

A title names a specific act or quote grounded in a transcript line, withholds
the outcome, and never states the sentence. Three angles for the A/B test.
Profanity censored (channel rule). If the browser tool refuses a string, that
is a rewrite with the same angle, not a stop.

CHECK: `python tools/check_title.py "<title>" --transcript <file>` — refuses
over 70 characters, a stated sentence (`N years`, `sentenced to`, `found
guilty`, `verdict`), uncensored profanity, a quoted span that is not verbatim
in the transcript (R16), and warns when the judge is not named or the length is
outside 50–65.

### R42 — Variants must differ at feed size

> "I don't see levels" — #41, 2026-08-29 21:26

I offered three background-darkening "levels" at −8 / −14 / −20%. Measured
2026-09-01 by `tools/check_variants.py` (`feed_diff`: 1280×720 → 168×94
INTER_AREA, gray, mean absolute difference; background darkened under the
placed subject alphas): **4.4 / 7.5 / 10.5** code values — and he could not
see any of them. Pairs he did tell apart: the two CARTHIEF title variants
12.5, MONKEY A vs B 14.2, circle vs arrow 46.8. A pair he called the same
(MONKEY_B vs B2) is 9.9. A choice he cannot perceive is not a choice; it is a
delay.

CHECK: `python tools/check_variants.py A.jpg B.jpg [...]` — every pair must
differ by ≥ 12 mean-abs code values at 168×94. The margin between the largest
invisible level (10.5) and the smallest distinguished pair (12.5) is thin and
is printed with every verdict; a pair he calls identical above 12 moves the
threshold up. `--selftest` proves the ×0.80 level still fails (10.47) and
MONKEY A vs B still passes (14.17).

### R43 — The frame has an element budget

> "Ehh now it looks just a like but too cluttered but the spacing looks better
> over all" — #110, 2026-08-31 07:23

Two subjects, a title, a kicker, an arrow AND a circle were on one 1280×720
frame. Budget: at most two subjects, one title block, at most one kicker, ONE
pointer (arrow or circle, never both).

CHECK: `python tools/check_clutter.py <work> [out.jpg]` — counts the elements
from `_build_log.json` (`boyd`/`defendant`/`extra`, `type`, `kicker`, `arrow`,
`extra_circle`) and refuses more than two subjects, more than one kicker, or
more than one pointer; measures the ink of the graphics (title + kicker +
arrow + circle) at 168×94 and refuses anything above the maximum of the five
accepted builds. Measured 2026-09-01 on the five `_NEW` builds: OFFERUP 0.192,
CARTHIEF 0.218, SANCHEZ 0.226, MONKEY 0.201, THOMPSON 0.217 → ceiling
**0.226**. The number is printed with the accepted maximum beside it. Builds
from 2026-09-01 on carry the exact mask (`_build_log.json["ink"]`,
`_overlay_mask.png`); older builds are reconstructed (kicker and circle
redrawn from the log, arrow = red in its box, title = stroked fill in its
band; kicker redraw vs pixels IoU 0.94 on SANCHEZ). `--selftest` proves
arrow+circle refuses and a second title line (0.281) refuses.

### R44 — Plates and Boyd reactions are a library, not a per-build harvest

> "go look at some real footage in the courtroom, take a screenshot when
> there's no defendant or no lawyer standing there, save it as the background
> ... You should have presets of a couple different backgrounds to pick from.
> Same thing with Judge Boyd. You should have, like, ten good reactions to pick
> from ... you always save those cutouts of Judge Boyd so you could reuse
> them." — #32, 2026-08-29 19:54

The pipeline re-derived a background and a Boyd cutout from scratch on every
build, which is why the attorney-behind-her and the flat-mush background kept
coming back. An asset he approved once is the floor for the next build.

Two libraries, and they are in different states - say which every time:

- **Plates - WIRED.** `assets/harvest/backgrounds/<CASE>/bg_<CASE>_<t>.png` +
  `index.json`, filled by `python tools/harvest.py backgrounds <case> --n 8`.
  `tools/thumb_pipeline.py` picks the flattest plate across EVERY case on every
  build (rejects sd<5, ranks by `flat_g_p90` after the 1.6 blur). Measured
  2026-09-01: 13 plates over 3 cases (CARTHIEF 3, MONKEY 4, SANCHEZ 6), and all
  five accepted build logs say `crop_source: "clean harvested plate"`.
- **Boyd reactions - SEEDED, NOT READ.** `assets/harvest/reactions/boyd/` +
  `index.json`, seeded 2026-09-01 by `python tools/library.py seed-boyd` from
  the five approved `judge_surgical.png` (OFFERUP, CARTHIEF, SANCHEZ, MONKEY,
  THOMPSON - the floor, never AUTOTEST), each with its face box and its
  `tools/expression.py` blendshape profile. `python tools/harvest.py reactions
  <case>` adds more, but scores on sharpness + mouth openness, not blendshapes.
  `tools/thumb_pipeline.py` does not read this library; every build still
  re-cuts Boyd from the reaction frame.

CHECK: `python tools/library.py list` prints both libraries with their WIRED /
NOT WIRED state, and `seed-boyd` re-syncs the five (idempotent, `--selftest`
proves a changed source is re-copied). **The reactions half is NOT AUTOMATED:**
until `tools/thumb_pipeline.py` reads `assets/harvest/reactions/boyd/`, say so
every time a build harvests a fresh cutout. Finding from the seed: the scorer
gives the approved CARTHIEF cutout 0.0 on every profile (eyes-look-down +
blink penalties) - the expression scorer is calibrated on a hearing sample, not
on his approvals, and would have rejected a face he accepted. Validate it
against the five before trusting it to pick.

### R45 — The type is a named preset he picked, and its cheap tells are said out loud

2026-09-01, on MONKEY_S: *"Maybe throw in a underline under hates you"* /
*"Also maybe make the words look so generic and cheap"* / *"And maybe not*"*.
Third time on the type: N17 2026-08-29 *"font is off and looks way lower quality"*,
P36 2026-08-29 *"a little bit more click baity type font so tweak it and give me
multiple options to pick from and we could lock one in"* - the options were never
delivered, so the complaint came back.

Symptom, not fix: the TYPE reads generic and cheap. The underline is his
illustrative fix. Measured on MONKEY_S, the three tells of cheap type are:

1. a **coloured glow behind the key word** (HATES YOU had a red glow),
2. a **uniform 7-10 px outline as the only edge device** - the offset shadow is
   smaller than the outline, so it disappears inside it,
3. **Anton set in sentence case** (Anton is a caps face; lowercase Anton is the
   generic-clickbait default).

What the references do instead (`.firecrawl/type/`, research 2026-09-01): the
Audit's top-viewed = wide grotesque, sentence case, no stroke, soft halo; the
Audit 2026 = Anton-class caps, ~5 px stroke + halo, 17% H; Court TV winners =
condensed caps, hard stroke, hard offset shadow; his own top 3 = Archivo 900 /
Montserrat 800, no stroke, deep soft shadow.

**Rule.** Every build's type is a named preset in `tools/thumb_type.py` `STYLES`
(`house`, `audit`, `audit_ul`, `audit_now`, `audit_now_ul`, `client`, `client_ul`,
`crt`, `crt_ul`), selected by `type_style` in `config/cases.json`; `house` is
byte-identical to the accepted 2026-08-31 treatment and stays the default until he
locks one in. Colours are NOT a style property (R33 owns them). Every build
prints which of the three tells its preset carries. The option sheet he asked
for is `D:/Boyd Clips/thumbwork/MONKEY_S_type/SHEET_full.jpg` (+ `SHEET_kicker`,
`SHEET_title`), nine builds on MONKEY_S's own inputs.

Measured on the sheet: the kicker's width fit (0.62 W, 20 chars) drives a wide
grotesque down to size 55-56 against Anton's 89 - the channels that use wide
faces run a **2-line kicker**, which is a compositor layout change, not a style.
The wide presets (`audit*`, `client*`) are therefore not fairly judged at one
line.

CHECK: `tools/thumb_type.py` (selftest in `tools/selftest_all.py`) - every preset
renders; the underline is in the ink mask (a control places it on a face box and
R1 sees it); `house` equals `thumb.py`'s constants; `tells()` reports `house` =
glow + heavy_outline + anton_lowercase (the known-bad control) and the clean
presets = none. `tools/thumb_pipeline.py build()` refuses an unknown
`type_style` (`TYPE_STYLE_UNKNOWN`) instead of falling back to house, and prints
`cheap tells (R45, reported not refused): ...` on every build; the list is in
`_build_log.json[type_tells]`. **NOT AUTOMATED:** whether a preset LOOKS generic
is his call - the checker names the tells he has already identified, nothing
judges taste. Say so on every build.
---

### R46 — The JUDGE is the top tile of a short, the defendant the bottom - by recognition, never by side

2026-09-02. **Not his verbatim words - measured from the reference.** The short
he accepted as the reference (2026-08-31: *"Short that you made look nicer than
the original footage was Sanchez"*, `SANCHEZ_SHORT_FINAL.mp4`) and the shipped
`OFFERUP_SHORT.mp4` (`LqAneu_GSOM`) both stack **Judge Boyd on top, the defendant
on the bottom**, and `tools/speakers.py` labels every mouth on that assumption
(*"the top tile is the bench, the bottom tile is the defendant"*). His
speaker-side caption rule (R9: *"when boyd is talking her captions are on her
half of the screen"*) only works if the halves are the same halves every time.

The defect: `scripts/make_short.py` stacked the LEFT source tile on top.
Boyd sits LEFT in CARTHIEF and RIGHT in SANCHEZ, OFFERUP and TORRES
(`config/pipeline.yaml` `subject_side: right` is labelled an ASSUMPTION). TORRES
rendered upside down - defendant top, judge bottom - and the engine died inside
`speakers.py` (`face not found (top=True bot=False)`: her downward-looking face
in the wrong tile) before any gate printed.

**Rule.** The judge tile is found by RECOGNITION (`tools/identity.py`, SFace vs
`config/boyd_reference.npy`, same-person line 0.363) on frames sampled across
the clip in each `detect_tile_crops` tile, and stacked on top; `defendant_at`
must land inside the other tile or the build aborts loudly. Measured 2026-09-02,
median cosine over 8 frames, top / bottom: SANCHEZ_SHORT_FINAL 0.855 / 0.288,
OFFERUP_SHORT 0.688 / 0.150, the upside-down TORRES 0.248 / 0.698.

CHECK: `scripts/make_short.py judge_tile()` picks the tile (aborts when neither
tile reaches the line, or when `defendant_at` disagrees); `tools/short_engine.py
gate_judge_top()` measures the OUTPUT (median Boyd score top >= 0.363 and top >
bottom) and is wired into the gate tuple as `judge on top`; a renderer crash is
now a failed `render` gate, not an escape. Controls in `--selftest` G11:
`tools/fixtures/tile_boyd_sanchez.jpg` + `tile_defendant_sanchez.jpg` (the
reference's own halves at 5.0 s) stacked judge-top -> PASS (0.797 / 0.228),
swapped -> FAIL (0.136 / 0.798). **NOT AUTOMATED:** whether he wants the order
the other way round - he has never said; this is the reference's order.

### R47 — The loudness a short ships at is proved on the encoded file, and the gain is one fixed number

2026-09-02. **Not his verbatim words - measured.** The floor he accepted
(`config/short_floor.json` audio block: -14 LUFS +/- 1, true peak <= -1.0,
2026-08-31) is a number on the FILE, and the chain that was supposed to hit it
never did what its code said. `tools/master_audio.py` ran `loudnorm ...
linear=true` for pass two; that flag is a request, and loudnorm silently
falls back to its DYNAMIC mode whenever the linear gain would push the true
peak past its TP target. Speech has a 15-20 dB crest; the target leaves
12.5 dB; so it fell back on essentially every court file. Measured on
TORRES_tight.mp4: `"normalization_type" : "dynamic"`, a -0.9 dBTP peak at
0.3 s (the gain riding up through the silent head into the first word), and
the engine refused the short. Every file mastered before this date went
through that mode, including `TORRES_LONGFORM_MASTERED.mp4`; the shipped
`OFFERUP_LONGFORM.mp4` (`ESSF8lSkNN4`) was never mastered at all
(-21.9 LUFS, TP -5.6 - `scripts/build_case_longform.py` does not master).

**Rule.** Pass one measures; pass two is `volume=+G dB` (G = -14 - measured
I) then `alimiter` with `level=disabled`, ceiling TARGET_TP - 0.5; AAC at
384 kbps (YouTube's upload spec; the native encoder re-grew peaks 0.3 dB at
192k, ~0 at 256k/384k); then the ENCODED file is measured and, if its true
peak is above -1.5, the ceiling is lowered by the overshoot and it is encoded
again (up to 4 passes) or master() raises. A mastering exception in
`tools/short_engine.py` is a failed `master` gate and a REFUSED build - until
this date it fell back to a single-pass loudnorm and the report passed as
long as a file existed.

CHECK: `tools/master_audio.py --selftest` (in `tools/selftest_all.py`):
A tone 12 dB under comes back at target; B a correct file barely moves;
C `tools/fixtures/speech_overshoot_torres.mp4` (first 8 s of the TORRES short,
crest 14.7 dB) - the CONTROL runs the old chain on it and must read
`dynamic`, then master() must land -14 +/- 1 with LRA unchanged (+/- 0.5, a
linear gain cannot change LRA, dynamic mode does) and encoded TP <= -1.5;
D a stand-in encoder that re-grows peaks 3 dB on pass one must force a
second pass. `tools/short_engine.py gate_loudness` measures the output
against the floor. **NOT AUTOMATED:** whether a file that raises should be
delivered at all (it is not - the engine refuses; he has not said otherwise).

### R48 — Every short is rendered by ONE command, and that command is the whole chain

2026-09-01, on the editor pages: *"Can you fix the short editor as well
after"*. 2026-09-02, asked whether every short from the editor pages should get
the engine's treatment: *"Okay then make it have it pls"*.

**What was wrong.** The shorts path that TORRES shipped through was four
commands typed by hand: `scripts/make_short.py --no-master` (raw 2-up) ->
`tools/align_words.py --model large-v3` -> `tools/tighten.py --timemap` ->
`tools/short_engine.py` (gates + floor stamp). Every entry a person would
actually use - the three editor pages (`scripts/build_short_editor.py`,
`scripts/build_editor.py`, `scripts/build_browse_editor.py`), the batch
renderer (`scripts/batch_vertical.py`) and the studio server's Render button
(`scripts/studio_server.py`) - emitted or ran the FIRST command only. A short
made from an editor page had no alignment, no tightening, none of R34 / R35 /
R36 / R38 / R46 / R47 and no floor stamp; it was the old short by another
door. The tail after the last word was a second hand-typed number
(`--tail 1.47` on TORRES) - a step that gets skipped is a step that gets
skipped.

**Rule.** `tools/short_chain.py --video ID --seg S:E [--seg ...] --out X.mp4`
is the only way a short is rendered. It runs the four steps in order in
`D:/Boyd Clips/shortwork/<stem>/`, refuses (and removes the output and its
sidecars) if any step fails or the engine does not print `SHORT_OK`, composes
the raw `.map.json` through tighten's timemap so the editor's player-time ->
source-time map is still true after cuts, and always passes `--tail auto`:
`tools/tighten.py measured_tail` walks the silences after the last transcribed
word to the last AUDIBLE sound and adds the default margin (TORRES: 1.58 s
measured against the 1.47 typed; "please, your honor, please" at -30..-39 dB
that Whisper dropped is inside it). The editor pages, the batch renderer and
the studio server emit / run that command and nothing else; `--captions` /
`--no-captions` are accepted and ignored (captions are the engine's, always
on). The one raw render left is `scripts/studio.py`'s PLAYER file
(`VERTICAL_<id>.mp4`, the whole hearing the editor scrubs) - not a short, and
the exemption is tied to that filename.

CHECK: `tools/check_short_entry.py` (in `tools/selftest_all.py`) scans
`scripts/*editor*.py`, `scripts/studio*.py`, `scripts/batch_vertical.py`: no
non-comment quoted `make_short.py` (the player-file exemption needs
`VERTICAL_` within 3 lines), and every entry file carries a quoted
`short_chain.py`. Its `--selftest` runs the pre-2026-09-02 studio_server
command as the known-bad CONTROL (must be refused), a new `*editor*.py`
emitting the raw command (caught by the glob), and studio.py with the player
file renamed (refused). `tools/short_chain.py --selftest`: map composition
known answers, a seam-straddling segment, the refusal removes every sidecar,
step order in `chain()`, `--tail auto` is literally passed.
`tools/tighten.py --selftest`: auto tail reaches past the last audible sound
and stays inside the clip; the CONTROL fixed tail cuts inside audible audio.
**NOT AUTOMATED:** whether the measured tail is too LONG for taste (it keeps
everything audible; he has not said it should cut earlier).

### R49 — A long-form opens on the hook, labelled "COMING UP...", before the sting

2026-09-02: *"Also I think you should add a 5 second or so clip of the hook or
drama later in the vid in the beginning of long form and put "Coming up…" or
something"*.

**What was wrong.** Every long-form to date opened on the branded sting and
then the hearing from its first word. The best five seconds of the case sat
five or ten minutes in, behind the docket call and the swearing-in, and the
viewer had nothing to stay for. The short had a hook (R36/R38); the long-form
had an intro.

**Rule.** `scripts/build_case_longform.py --coldopen A:B` (source-absolute
seconds; the short's hook piece is the default candidate) renders
`cold open -> sting -> body` in ONE encode (`render.render_longform(coldopen=)`):
the span gets the body's own crop / scale / mark, the label
`render.COLDOPEN_LABEL` ("COMING UP...", Anton, white on a black border,
bottom-left, `h * 0.065`), a 0.35 s fade to black and matching afade, then
the sting, then the body. Bounds: 3-9 s ("5 second or so"), inside the body,
and at least 30 s after the body starts ("later in the vid" - the opening
shown twice is not a tease). The renderer writes `<out>.coldopen.json`
(source, src span, body span, label box, intro length, crop, canvas) - that is
what the checker measures the FILE against. A build without `--coldopen`
is refused unless `--no-coldopen` is passed, and then it says so on its own
output ("NO COLD OPEN"). Both builders refuse a missing sting.

CHECK: `tools/check_coldopen.py OUT.mp4` (run by
`scripts/build_case_longform.py` on its own output; a FAIL is a refused
build; in `tools/selftest_all.py`) measures on the file: the frame 2.5 s in
is the SOURCE frame at `src_start + 2.5` after the same crop (p99 |diff| <=
12, label box masked; measured on TORRES: same frame 3, one second away 36,
the opening 145) and matches the hook better than the body's opening; the
label box holds >= 1500 more near-white pixels than the untouched source
frame during the cold open and <= 600 more after it; the last cold-open frame
is near black (mean luma <= 40) and its last 0.1 s of audio is under half the
middle's RMS; the frame at `cold + sting/2` is the sting's own; the duration
matches the sidecar. `--selftest` renders a synthetic hearing with the cold
open (PASS) and without it beside the good sidecar (CONTROL: must FAIL on the
footage comparison AND the missing label), a file with no sidecar (refused),
the renderer refusing a hook from the opening and a cold open without the
sting, and the REAL known-bad `tools/fixtures/torres_longform_pre_r49_head.mp4`
(the first 20 s of the pre-R49 TORRES long-form - sting, then the docket
call - beside the real R49 sidecar: must fail the footage comparison, p99
139, and the label, +0 px; SKIPPED out loud when the source is not on the
machine).
**NOT AUTOMATED:** whether the span chosen IS the hook - which five seconds
carry the drama is taste; the short's hook piece is the default and he picks
otherwise. Whether "COMING UP..." is the wording he wants ("or something").

### R50 — A shortlist is judged for entertainment and read before it reaches him

2026-09-02, on a five-case shortlist I delivered from the picker's density
score without reading one hearing: *"I think you have to use observer skill to
actually pic actual entertaining banger clips"* and *"Shouldn't u upgraded the
picker with task observer? Or did u already"*. I had not. The picker
(`tools/hearing_measure.py`, `config/picker.json`) measures questions per
minute, narrative and sentencing - it finds hearings. It does not know what a
viewer stays for, and I handed him its ordering as if it did.

RULE: no case is proposed to him from a rank score alone. Every shortlist row
carries (1) `tools/banger_digest.py` entertainment score and its hit
categories - family confrontation, prison + disbelief, heinous facts, begging,
sharp questions, notoriety, the categories measured on his own catalog
(`data/catalog_vs_picker.json`) - (2) three or more quoted lines from the
hearing with offsets, read by me, (3) the ruling, (4) a frame proving the
defendant is on camera, (5) the rival count from `tools/case_search.py`. A row
missing any of the five is not a pick, it is a lead.

CHECK: `tools/banger_digest.py --selftest` (a synthetic hearing with a gun, a
son, begging and a revocation must score more than 3x a reset-and-PSI hearing,
and the speaker-turn split must find every `>>` turn); on real rows
`tools/banger_digest.py --rows FILE` prints the score, the categories and the
quoted lines per hearing. Not automated, said out loud: whether the lines are
funny or shocking is still read by me, and the digest is not normalised per
minute - a long hearing accumulates hits.

## Checker registry (verified by `tools/check_rules_refs.py`)

Every `*.py` named anywhere in this file has a row, and the state is measured
against the disk and the build path (`tools/thumb_pipeline.py`, `tools/thumb.py`,
`tools/verify_build.py`, `tools/verify_thumb.py`, `tools/make_short.py`,
`tools/short_engine.py`, `tools/selftest_all.py`, `tools/floor_stamp.py`, and
the two skill files). WIRED = a build-path file invokes it. ORPHAN = on disk,
nothing invokes it. STALE = orphan whose thresholds contradict the current
floor. MISSING = not on disk. MANUAL = a human runs it on purpose.

Measured 2026-09-01. `python tools/check_rules_refs.py` re-measures and fails
the selftest suite when a row lies.

| checker | state | evidence |
|---|---|---|
| `tools/caption_short.py` | WIRED | `tools/make_short.py`, `tools/short_engine.py`, `tools/selftest_all.py` (`--selftest` since 2026-09-01: reveal / entrance / speaker-side controls) |
| `tools/make_short.py` | WIRED | `tools/short_engine.py` |
| `tools/short_engine.py` | WIRED | boyd-thumbnail skill; top of the shorts path; `tools/selftest_all.py` (`--selftest` G1-G11 since 2026-09-02 - G11 is R46 judge-on-top, fixtures from the reference; G1-G10 since 2026-09-01: every caption / cut / audio constant is read from `config/short_floor.json`, none left in code) |
| `tools/speakers.py` | WIRED | `tools/make_short.py` |
| `tools/identity.py` | WIRED | `tools/thumb_pipeline.py`, `tools/selftest_all.py` (leave-one-out selftest), `tools/short_engine.py` (R46 `gate_judge_top`), `scripts/make_short.py` (R46 `judge_tile`) |
| `tools/master_audio.py` | WIRED | R47 - `tools/short_engine.py` (master step, a raise is a REFUSED build), `scripts/make_short.py`, `scripts/build_body.py`, `scripts/build_longform.py`; `tools/selftest_all.py` (`--selftest` A-D, control fixture `tools/fixtures/speech_overshoot_torres.mp4`) |
| `tools/short_chain.py` | WIRED | R48 - the ONLY short render entry: `scripts/make_short.py --no-master` -> `tools/align_words.py` -> `tools/tighten.py --tail auto` -> `tools/short_engine.py` (must print `SHORT_OK`) -> composed `.map.json`; emitted by `scripts/build_short_editor.py`, `scripts/build_editor.py`, `scripts/build_browse_editor.py`, run by `scripts/batch_vertical.py`, `scripts/studio_server.py`; `tools/selftest_all.py` (`--selftest`) |
| `tools/check_short_entry.py` | WIRED | R48 - `tools/selftest_all.py` (`--selftest` with the old studio_server command as the CONTROL, then the scan of `scripts/*editor*.py`, `scripts/studio*.py`, `scripts/batch_vertical.py`) |
| `tools/tighten.py` | WIRED | R35/R47/R48 shorts path, run by `tools/short_chain.py` (`--tail auto` = `measured_tail`, `--timemap` for the engine's cut gate); `tools/selftest_all.py` (`--selftest`, reverb-tail control, auto-tail vs fixed-tail control) |
| `tools/snap_cuts.py` | WIRED | `tools/tighten.py` (silences), `tools/short_engine.py`; `tools/selftest_all.py` (`--selftest`) |
| `tools/align_words.py` | WIRED | R48 - word timestamps for the shorts path (whisper large-v3), run by `tools/short_chain.py`; its output is gated downstream by `tools/short_engine.py` |
| `scripts/build_case_longform.py` | MANUAL | long-form body builder; run by hand per case; R47: does NOT master - `tools/master_audio.py` runs on its output before posting; R49: `--coldopen A:B` required (or `--no-coldopen`, said out loud), runs `tools/check_coldopen.py` on its output |
| `tools/check_coldopen.py` | WIRED | R49 - run by `scripts/build_case_longform.py` on the rendered file (FAIL = refused build); `tools/selftest_all.py` (`--selftest`: synthetic with/without cold open, no-sidecar, renderer refusals, `tools/fixtures/torres_longform_pre_r49_head.mp4` + real sidecar as the real known-bad) |
| `tools/banger_digest.py` | WIRED | R50 - entertainment layer on the picker; `tools/selftest_all.py` (`--selftest`: banger vs reset-hearing control 3x, turn split); `--rows` on `state/recent_hearings_*.json` for a shortlist |
| `tools/hearing_measure.py` | MANUAL | R50 - the density picker (questions/min, narrative, MTR); run by hand over a stream to produce the rows the digest reads; finds hearings, does not judge them |
| `scripts/build_body.py` | MANUAL | older long-form builder; calls `tools/master_audio.py` |
| `scripts/build_short_editor.py` | MANUAL | R48 - editor page builder, run by hand per case; the page's Copy button emits `tools/short_chain.py` and nothing else (`tools/check_short_entry.py`) |
| `scripts/build_editor.py` | MANUAL | R48 - editor page builder, run by hand per case; emits `tools/short_chain.py` (`tools/check_short_entry.py`) |
| `scripts/build_browse_editor.py` | MANUAL | R48 - browse-editor page builder, run by hand per case; emits `tools/short_chain.py` (`tools/check_short_entry.py`) |
| `scripts/batch_vertical.py` | MANUAL | R48 - batch short renderer, run by hand; runs `tools/short_chain.py` per cut (`tools/check_short_entry.py`) |
| `scripts/studio_server.py` | MANUAL | R48 - the studio's Render button, started by hand; `run_render` runs `tools/short_chain.py` (`tools/check_short_entry.py`) |
| `scripts/studio.py` | MANUAL | R48 - one-command editor builder, run by hand; its `scripts/make_short.py` call renders the PLAYER file `VERTICAL_<id>.mp4` (the whole hearing), not a short - the only raw render `tools/check_short_entry.py` allows, tied to that filename |
| `scripts/build_longform.py` | MANUAL | older long-form builder; calls `tools/master_audio.py` |
| `scripts/make_short.py` | WIRED | R46/R48 - the raw 2-up render (`--seg START:END ... --no-master`), run by `tools/short_chain.py` as step one and never emitted by an editor page (`tools/check_short_entry.py`); the engine gates its output. `scripts/studio.py` also runs it for the editor's PLAYER file, which is not a short |
| `tools/thumb.py` | WIRED | `tools/thumb_pipeline.py` |
| `tools/thumb_type.py` | WIRED | `tools/thumb.py` (every title/kicker render goes through `render_runs`), `tools/thumb_pipeline.py` (`build()` resolves `type_style`, refuses unknown names, prints the R45 tells), `tools/selftest_all.py`. R45 — presets, underline-in-ink control, `house == thumb.py constants`, `tells()` with `house` as the known-bad control |
| `tools/thumb_pipeline.py` | WIRED | `tools/verify_build.py`; top of the thumbnail path; `tools/selftest_all.py` (`--selftest` since 2026-09-01 proves `judge_from_library()` on the real `prep()`: same-case reuse, by-name override, auto vs video, and every refusal) |
| `tools/verify_thumb.py` | WIRED | `tools/thumb_pipeline.py`, both skills, `tools/selftest_all.py`. Gate D (duplicate face, never waived) got a validity floor 2026-09-01: a pair with a side under `MIN_DESC`=20 SIFT descriptors is printed UNMEASURABLE, not scored - MONKEY_S failed D on 5 RANSAC inliers between the monkey's face (367 descriptors) and a 20x22 px blurred gallery face (11); RANSAC always marks its 4-point sample as inliers. Real duplicates YuNet can detect measure 32-141 descriptors / 8-55 inliers (same-size, 50 px and 30-40 px pastes on four references); tiny gallery faces 3-11. Controls `D-50px-dup` (still FAILS) and `D-floor-blob-unmeasurable` in `--selftest`. **Fit check 2026-09-01:** the floor was not enough - MONKEY_audit_now_ul failed D on 9 RANSAC inliers between the monkey (340 descriptors) and a 24x30 px gallery face (24). A real duplicate is the same pixels resized to 160x160, so its homography is near-identity (paste sweep 30-100 px on three references: scale 0.89-1.15, anisotropy <= 1.15, perspective <= 0.14); the false positive fit scale 0.45, anisotropy 9.0, perspective 2.41. `_fit_geometry` rejects inliers on a transform no duplicate gives (`FIT_ANISO` 2.0, `FIT_PERSP` 0.5; scale 0.5-2.0 and translation 120 px as sanity bounds) and prints `D rejected fit: ...`. Fixture `tools/fixtures/gateD_falsepos_monkey_vs_24px_gallery.png` (the real pair) is a selftest control: `D-falsepos-fixture-reproduces` + `D-falsepos-rejected-by-fit`. **Cost, said out loud:** the smallest cleanly caught duplicate is now 40 px (MONKEY/OFFERUP/CARTHIEF/SANCHEZ) and 50 px (THOMPSON/MONKEY_S); the 30 px SANCHEZ and 40 px MONKEY_S catches before this were degenerate fits right by luck. **NOT AUTOMATED:** below that the DETECTOR does not fire, so a duplicate that small is invisible to D - said out loud, not closed |
| `tools/verify_build.py` | WIRED | `tools/thumb_pipeline.py` (`build()` returns `ok and _ok` since 2026-09-01), `tools/selftest_all.py`, both skills |
| `tools/expression.py` | WIRED | `tools/thumb_pipeline.py`, `tools/thumb.py`, `tools/library.py` (`rank()` re-scores live), `tools/selftest_all.py`. 2026-09-01: eyeLookDown penalty replaced by a head-pitch cost + lid ramp; FLOOR 0.04 anchored on the approved minimum (SANCHEZ 0.0520 full-cutout); the approved CARTHIEF cutout no longer scores 0.0 |
| `tools/check_registry.py` | WIRED | `tools/verify_build.py` gate H, `tools/selftest_all.py` |
| `tools/check_rules_refs.py` | WIRED | `tools/selftest_all.py` |
| `tools/selftest_all.py` | WIRED | boyd-thumbnail skill; the runner itself |
| `tools/thumbeng/variety.py` | WIRED | boyd-thumbnail skill (R39). Its 0.30 limit rejects all five accepted builds (max pair 0.455) — a report, not a ship gate |
| `tools/sidebar_sheet.py` | WIRED | boyd-thumbnail skill - the 168 px sheet is read into the chat with every build he is shown |
| `tools/floor_stamp.py` | WIRED | `tools/thumb_pipeline.py` (`build()` stamps `_build_log.json["floor"]`), `tools/short_engine.py` (`build()` writes `<short>.floor.json`), `tools/selftest_all.py`; youtube-channel skill §1d runs `check` before posting |
| `tools/check_title.py` | WIRED | `tools/selftest_all.py`; youtube-channel skill §1c runs it on all three title variants (with `--transcript`) before anything is typed into Studio or the A/B test is set |
| `tools/check_variants.py` | WIRED | `tools/selftest_all.py`; boyd-thumbnail skill §3 runs it on every set of variants before they are shown to him |
| `tools/check_clutter.py` | WIRED | `tools/selftest_all.py`; boyd-thumbnail skill §3 runs it beside `verify_build.py`; `tools/thumb.py` writes the exact ink mask it reads |
| `tools/check_floor_gates.py` | WIRED | `tools/selftest_all.py` (selftest + the audit) — every gate in `verify_build.py` must pass the five accepted builds in `config/quality_floor.json["files"]`, or the floor file must declare the disagreement by case and gate (`gate_disagreements`). 2026-09-01: the gates as tuned rejected 3 of the 5 |
| `tools/harvest.py` | MANUAL | R44 — `backgrounds` fills the plate library `tools/thumb_pipeline.py` reads; `reactions` fills `assets/harvest/reactions/boyd/` (sharpness + openness score, not blendshapes) |
| `tools/library.py` | WIRED | `tools/thumb_pipeline.py` (`judge_from_library()`, called from `prep()` - the compositor READS the library since 2026-09-01: own-case reuse when the cutout is usable, `library:<CASE>` by name, `auto` ranks the library against the searched frame by expression), `tools/selftest_all.py`; R44 — `seed-boyd` syncs the five approved cutouts with their usable / defects state from `quality_floor.json[gate_disagreements]` (MONKEY UNUSABLE F/J/K), `list` prints WIRED-via-judge_from_library |
| `tools/case_search.py` | WIRED | `tools/thumb_pipeline.py` (`build()` runs `check(case)` as a build gate since 2026-09-01: no `posted_by`, or a search older than `STALE_DAYS`=14, fails the build), `tools/selftest_all.py` (`--selftest` + `--check --all --recorded`). CLAUDE.md 2026-08-30: *"search YouTube for the defendant / case and record who has posted it in config/cases.json"* - was a manual step nothing checked |
| `tools/floor_measure.py` | WIRED | `tools/selftest_all.py` (`--selftest` + `--check`): the generator for `config/quality_floor.json[per_case, envelope]` - the house style is now what `thumb.py`'s own separation solve measures on the five accepted builds, and `--check` goes STALE when the file and a fresh measurement disagree. The 2026-08-31 numbers had no generator and did not reproduce |
| `tools/verify_variety.py` | MISSING | named by R39 on 2026-08-31; never existed — the code is `tools/thumbeng/variety.py` |
| `tools/thumb_measure.py` | MISSING | named by R39 on 2026-08-31; never existed (retired the same day) |
| `scripts/verify_set.py` | STALE | no caller since `verify_build --set` was removed 2026-09-01; luma band 122±12 fails 4/5 accepted builds, chroma ceiling 6.5 fails 3/5; `--check all` crashes on rembg CUDA OOM; `--check pale` reads a `.meta.json` nothing writes |
| `scripts/kill_hotspots.py` | ORPHAN | R10 — whole-frame blob check, never on the build path |
| `scripts/make_short_auto.py` | ORPHAN | R24 — superseded by `tools/make_short.py` + `tools/short_engine.py` |
| `scripts/make_thumbnail_quiet.py` | ORPHAN | R16 — the only transcript-grep refusal, dead |
| `scripts/pick_reaction.py` | ORPHAN | superseded by `tools/expression.py` |
| `scripts/thumb_Q3_detail.py` | ORPHAN | the old builder; called `verify_set.py`; called by nothing |
