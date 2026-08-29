# Where this project is

Updated 2026-08-29. Read this first after a reboot.

## The shorts pipeline — this is the current work

Three scripts, in order. Each was written because the obvious approach was
measured and found broken; the comments carry the measurement.

```
scripts/tighten_short.py    remove dead air using WORD GAPS
scripts/who_speaks.py       who is talking, from audio-visual correlation
scripts/caption_short.py    burn captions on the speaker's half
```

**`silencedetect` DOES NOT WORK ON THIS FOOTAGE. Do not use it.** Measured on
CARTHIEF_SHORT.mp4 at -30, -25, -20 AND -18 dBFS: **zero spans, every time.**
The courtroom room tone never drops that low. Every dead-air pass in this repo
before 2026-08-28 used it and was therefore blind. The same short had **22
word-gaps over 0.7s totalling 31.2s of 56.2s — 56% of the runtime**, including a
4.20s hole after "far?" and 3.68s after "hour?". Gaps come from the word-level
transcript now.

**Speaker attribution is audio-visual correlation.** A talking mouth moves in
time with the sound; a nodding head does not. Each half's mouth-motion series is
correlated against the audio envelope. Measured on nine hand-labelled windows:
**9/9, against 4/9 for comparing raw motion.** Judge Boyd is animated while
listening, which is exactly why raw motion handed her the defendant's lines.

Three things that broke and are now guarded:
* **Blocks must not straddle a speaker turn.** Grouped by character count, about
  a third contained both voices — "evading? Nothing" is her question plus his
  answer. Unplaceable on either side. Blocks are now forced to end at every turn
  boundary before anything positions them.
* **Compute the speaker series on the UNCUT short, then remap it.** Each cut is a
  hard scene change that spikes frame-difference, so a series computed on the cut
  video is corrupted at every cut.
* **`-pix_fmt yuv420p` is mandatory.** Without it libx264 inherits higher
  precision from `curves`/`eq` and silently picks High 4:4:4 Predictive. All four
  captioned shorts shipped that way once; no consumer hardware decoder plays it.

**CARTHIEF_SHORT_FINAL.mp4 is the reference output.** 56.2s -> 34.8s, 22 cuts,
0 gaps over 0.7s (longest 0.68s), deblocked, captions at 156px on the speaker's
half, A/V exact at 34.800s each.

**Deblocking, measured over six chains:** `deblock` + `hqdn3d` weighted to chroma
+ `deband` + light `unsharp`. Block-boundary ratio 1.099 -> 0.763 with detail UP
from 1.55 to 2.37. `fftdnoiz` made it worse (1.399). No upscaling — Nathan asked
for the artefacts gone, not a bigger picture.

## The font is settled

`assets/fonts/TTTHeadline-Regular.ttf`, family **"TTT Headline"** — Archivo
Variable frozen at weight 900 / width 70 with fontTools, renamed so it cannot
collide with stock Archivo. Identified by matching the shipped Thompson
thumbnail: its 26-character quote spans 1049px at cap 71. At that width
Montserrat Black gives cap 52 and Archivo SemiCond SemiBold gives 68 — both far
too light. Archivo is SIL OFL 1.1, so commercial use and instancing are fine.
libass cannot select a variable axis, which is why the static instance exists.
Nathan: "those are the captions ive been looking for".

Caption size **156px** ("C"), chosen after seeing 92/124/156/190/224/258/296 at
1:1. He first said "d but bigger" then came back down.

## Grade the PICTURE, never the type

`render.py` documents it for video — "Grading after `ass=` would lift the caption
white too ... it would clip the text edges and eat the black outline". The
thumbnail path was violating its own rule: type burned in, saved, THEN graded.
`thumbnail.grade_image(img, cfg)` now works in memory so the builder can grade
before drawing type.

## 2026-08-29 — Nathan picked Q3 for thumbnails

His words: "q3 thumbnail is fire". `scripts/thumb_Q3_detail.py` — our
construction executed at maximum detail. Measured against the other three builds,
our current output and the Thompson reference:

| | luma | blacks | arrow px | chroma | detail full / feed |
|---|---|---|---|---|---|
| **Q3_detail** | **118.6** | 13.3% | 2727 | 5.54 | **1442 / 5410** |
| Q1_noregroup | 109.3 | 10.2% | 3346 | 4.80 | 1334 / 4780 |
| Q2_surgical | 105.1 | 7.0% | 2563 | 14.96 | 1307 / 5037 |
| Q4_light | 115.0 | 10.0% | 3032 | 5.93 | 1012 / 4284 |
| ours | 105.8 | 13.8% | 4520 | 2.11 | 1412 / 6031 |
| Thompson | 124.9 | 9.0% | 3904 | 3.29 | 512 / 4638 |

Highest detail of the four and the luma closest to Thompson. Q2 is disqualified
on chroma (14.96 — the blocky artefact back at seven times the reference).

**Q3's mechanism:** realesr-general-x4v3 (BSD-3, so commercially usable) at 4x
then resampled down, with every restorative step moved to the NATIVE side of the
upscale; BiRefNet-matting into a ViTMatte-S trimap refine, measured on the judge
tile at alignment +7.4%, colour fringe −26%, matting residual −20%, soft hair
mass +35%; the defendant moved only when the solver proves he must be, only the
vacated sliver inpainted, then re-matted with the area loss measured — over 1%
and the move is REJECTED and the looser composition ships, because a severed limb
is worse than a loose composition; and an arrow that must both carry zero pixels
on a person AND cast a ray striking the defendant first, since an earlier version
scored a perfect 0% overlap while pointing at empty ceiling.

**Open on Q3:** chroma deviation 5.54, above the 3.5 gate and worse than our
current 2.11 — check the blocking has not returned. And it carries only a
`carthief` preset, while SANCHEZ and OFFERUP put the judge on the RIGHT. If it
needs per-case tuning it is not yet the daily pipeline, which is what the
composition workflow exists to solve.

## The one command for shorts — `scripts/make_short_auto.py`

```
python scripts/make_short_auto.py --short READY-TO-POST/X_SHORT.mp4     --transcript work/ID/ID.transcript.json --src-start 3931.8     --out READY-TO-POST/X_SHORT_FINAL.mp4
```

Runs the whole chain with no hand-tuning and **refuses rather than emitting
something broken** — it checks pix_fmt, dimensions, A/V sync, remaining word-gaps
and a clean decode, and exits non-zero if any fails.

All three cases pass:

| | before | after | cuts | gaps >0.7s | turns |
|---|---|---|---|---|---|
| CARTHIEF | 56.2s | 34.8s | 22 | 0 | 34 |
| SANCHEZ  | 53.0s | 49.1s |  8 | 0 | 35 |
| OFFERUP  | 55.5s | 41.8s | 18 | 0 | 36 |

OFFERUP lost 25% and SANCHEZ only 7% — Sanchez is a faster back-and-forth. A
uniform cut would have wrecked one and barely touched the other, which is the
argument for deriving the cuts per clip rather than fixing a ratio.

**Verifying caption side: key on the OUTLINE, not brightness.** A check that
thresholded on white reported 0/5 wrong on a render that was correct — it was
measuring the ceiling and Judge Boyd's white collar. Caption glyphs are a white
core inside a 12px black stroke, so the reliable test is a very bright pixel with
a very dark pixel within ~17px. Nothing else in a courtroom frame does that.
Measured on the rendered files, the caption changes half 10 / 11 / 11 times.

## 2026-08-29 — open right now

**Two workflows running** on thumbnails, deliberately disjoint:
* `thumbnail-quality` — surface finish. Super-resolution licences (GFPGAN and
  CodeFormer terms must be READ, this is a monetised channel), matte edge
  refinement, and what "premium detail" measures as. Then four builds.
* `thumbnail-composition` — arrangement. Nathan: "how everythings arranged too
  and all precicley placed next to eachother ... you basicily need to be a pro at
  making good quality boyd thumbnails with whatever video were working with".
  The point is a PARAMETRIC system, not coordinates: **the judge is on the LEFT
  in CARTHIEF and the RIGHT in SANCHEZ and OFFERUP**, so any system that assumes
  a side is already broken. Each build must produce all three from one script
  with no per-case fudging.

**Three earlier workflows died on the session limit** (resets 12:10am America/
Chicago). The 6 thumbnail constructions DID build; their critic did not. The
surgical-cuts and master-shorts teams produced nothing. Do not assume their
findings exist — check the journals.

**The quiet construction — `scripts/make_thumbnail_quiet.py`.** Nathan on the
team's low-contrast variant: "d looks crazy". Verbatim quote, small, dark, no
plate/outline/shadow, dropped into real negative space. Placement is DERIVED —
it finds the flattest empty region and solves for a glyph colour at a target
contrast ratio against that particular wall, so it moves per frame. It refuses if
the quote is not verbatim in the transcript.

**But it only works on CARTHIEF.** On SANCHEZ and OFFERUP the text lands on a
body, which breaks his standing rule. Cause is measured: the exemplars used wide
frames with real ceiling; our 2-up strips are dense with people, and the flatness
search had to loosen from 10 to **38** before anything fit — it was settling, not
finding. Contrast came out 2.83 / 3.25 / 4.01:1 against a 4.1 target for the same
reason. **The construction is right; the frame selection is wrong.** It needs
frames chosen FOR negative space, not for reaction.

**Unanswered and it is his call:** the two running teams are optimising the LOUD
construction (bold type, arrow, cut-out). The quiet one is the opposite bet.
Nobody has decided which we are actually building.

## What is NOT fixed

* **The thumbnails still ship a severed arm.** `regroup_plate.py` moves the
  defendant toward his attorney and cut through him. Connected-component
  isolation and a merged-blob refusal were added (src 4437 gives a component
  2.51x the scrubs width because the men touch and is refused; src 4578 gives
  1.19x and is clean) — but the shipped CARTHIEF_thumbnail.jpg is still wrong.
* **SANCHEZ and OFFERUP shorts have not been through the new pipeline.** Only
  CARTHIEF has.
* **The long-forms were dead-aired with the blind `silencedetect`**, so
  MONKEY_LONGFORM and the rest almost certainly still carry gaps nobody measured.
* **`verify_thumbnail.py` fails the Thompson reference** on its own arrow-aim
  check. That file's own rule says the competitor set is ground truth, so the
  threshold is wrong, not Thompson.
* Nothing has been uploaded since the monkey long-form on 2026-08-27.

## 2026-08-23 — FIRST PUBLISH, and the monkey long-form built

**The Thompson package is POSTED.** Nathan, this session: "i alreADY POSTED THE
THIMPSON". That ends "nothing has ever been published from this pipeline" — it
had been true since day one. The shipped file is
`READY-TO-POST/1_LONGFORM_Thompson.mp4`, 657.7s, and it carries the 1.4s
`sting.mp4` intro (verified by extracting its frame at t=0.7s: the TTT-star on
the dark ground). Outcome — views, retention, whether the short drove the
long-form — is NOT tracked yet and nobody has looked.

**Monkey long-form built:** `READY-TO-POST/MONKEY_LONGFORM.mp4`, 808.9s (13:29),
1920x1080. Command:

    python scripts/build_case_longform.py \
      --source work/2XkPnvstmRQ/2XkPnvstmRQ_h_5915_5895-7108.mp4 \
      --offset 5895.0 --in 5915.92 --out-s 6739.30 \
      --dest ".../READY-TO-POST/MONKEY_LONGFORM.mp4"

His boundaries, verbatim: "start it from court is calling until she says goodluck
to you". Both located in the transcript, not estimated — "Court is calling" at
src 5915.92, "Good luck to you." at src 6737.04 (ends 6737.6), and the reply
"Thank you, welcome." lands at 6738.72. Out-point set at 6739.30 so her line and
its answer both land. refine.py then snapped in -1.32s onto the start of the line
and out +0.38s for the hold.

This ENDS BEFORE THE SECOND DEFENDANT. The next case is called at src 6745.3
(13:49 into the old file) and the court never says "the court is calling" there,
which is why `find_called_hearings.py` merged them. `HEARING_2025-07-14_2XkPnv.mp4`
(19.6 min, the one he called "that one's fire") contains BOTH defendants and
should not go up as-is.

Measured on the render: dead air >4.0s removed, 825s -> 808s (-18s, 2.1%) across
5 pieces. Verify sheet at `READY-TO-POST/MONKEY_verify_sheet.png` — frames at
0.7 / 2.0 / 200 / 500 / 808.5s with the watermark corner zoomed on each.

### New: scripts/build_case_longform.py

Takes the in/out points as arguments instead of looking them up in the store, so
a case the phrase-based segmenter merges can still be cut correctly. Same code
path from there as `rebuild_longform.py`.

### Watermark was placed wrong on this docket, and is now measured

Two separate defects, both found by extracting frames rather than reading code:

1. `_watermark_chain` only ever placed the mark at `W-w-margin` — the CANVAS
   right edge. This docket composites a 2-up with black beside the tiles: Judge
   Boyd's tile ends at x=1791 of 1920, so 53 of the mark's 115px sat on black
   and it read as a broken overlay. `render_longform` now takes
   `watermark_right_x` and the driver anchors to the measured tile edge.
2. Every WHITE variant was then invisible — the right tile is a cream wall with
   the Bexar County seal on it. Measured across 9 sampled frames, the mark's own
   rectangle sits at mean luminance 180/255; corner luminance across the eight
   tile corners ranged 46.6 (left-bottom-right) to 246.7 (right-top-left). The
   driver now samples that rectangle and picks `wm_02_mark_dark_55.png` above
   140 and `wm_brand_halo_40.png` below.

`cut_shortlist.py` still says in a comment that the watermark asset "is not on
disk". That is false — `boyd-brand/watermarks_v2/` and `boyd-brand/watermarks/`
both exist and are full. Every HEARING_*.mp4 it produced is unwatermarked on
that false premise.

### Still open on this case

* **No thumbnail, no title, no description.** His line for the thumbnail, agreed
  2026-08-21: "No monkey business in my court".
* **Charge and current status for Joseph Grant (2024CR011920) are UNVERIFIED.**
  He asked for them in the description. Nothing goes in a public description
  until the Bexar County record is pulled and sourced.
* The short already exists and is his own CapCut edit:
  `READY-TO-REVIEW/spidermonkeyshort_FINAL.mp4`, 2160x3840, 54.6s.

### Thumbnail built to his stated rules, not to defaults

His rules, pulled verbatim from the session logs rather than remembered:

* 2026-08-11: "we would have to upscale her face color correct any weird
  lighting and also the defendant also in the thumbnail it would be preferable
  to get the defendant when theyre upset sad or shocked or something"
* 2026-08-12: "i like audits title style better so use that type from now on
  and the thumbnails as well" / "ik she doesnt use a gavel its fine"
* 2026-08-21: "'No monkey business in my court' on the thumbnail maybe lol"
* 2026-08-23: "the same way you corrected the color to natural of the short do
  that as well to the thumbnail maybe even bump it up a level too"

Output: `READY-TO-POST/MONKEY_thumbnail.jpg` (1280x720), plus
`MONKEY_thumbnail_A_1.00.jpg` and `_C_1.70.jpg` as the softer and stronger
grades, and `THUMB_GRADE_LEVELS.png` comparing all four at once. Shipped
default is the middle one.

Construction: plate = the defendant's tile at src 6282 (he looks straight down
the lens), Judge Boyd cut out from src 6270 mid-riff and composited over it,
unstroked and feathered, no arrow. Text one line, white + yellow, top band,
cap 43px / 0.0597 H — inside the measured Audit range of 0.051-0.100 H.

Three things fixed while building it:

1. **The cut-out was masked with the wrong model.** `make_thumbnail_v2.py`'s
   own docstring specifies BiRefNet-portrait (MIT) and warns that rembg's
   default is BRIA RMBG-2.0 under CC BY-NC 4.0 — non-commercial, so unusable on
   a monetised channel. Now masked with `birefnet-portrait` explicitly.
2. **The court's own "187th Court" caption was inside the plate**, bottom-left.
   Cropped off before compositing.
3. **Three faces in frame.** The defendant's tile carries his attorney on the
   right, and Boyd's cut-out landed on top of him. The measured set never runs
   more than two. Plate cropped to the left 62% so it is defendant + room only.

**`thumbnail.grade()` now applies the video's tone curve.** It never had it: the
thumbnail went straight to contrast + saturation while every rendered cut got
`curves=all='0/0.02 0.25/0.31 0.5/0.57 0.75/0.80 1/0.97'`, which is why the
plate read flatter than the video it fronts. New `curve` and `curve_strength`
params; `curve_strength` scales each control point's displacement from linear,
so the shape holds and only its depth changes. 1.0 is exactly the video grade,
1.35 is the shipped "bump".

### 2026-08-28 — the grade was MANUFACTURING the blocky background

Nathan: "fix the background where its all bright and then it looks blocky".

It was chroma blocking — coloured 16x16 blocks in flat bright areas like the
courtroom ceiling — and `thumbnail.grade()` was creating it, not revealing it.
Measured on the SANCHEZ ceiling, mean chroma deviation from neutral:

    ungraded source          1.33
    after grade() as shipped 8.13      <- 6x worse
    after the fix            1.04

A luma-based blockiness check missed it completely (8px-boundary ratio 0.72,
i.e. no luma blocking at all). The damage was entirely in the chroma planes,
which is why it only showed up by eye.

Three causes, all now fixed in `src/boydclips/thumbnail.py`:

1. **The saturation floor. This was the big one.** The line read
   `S = S * 1.45 + 0.06`, applied to EVERY pixel. A near-white ceiling pixel at
   S~0.01 came out at 0.074 — a 7x lift on something that should stay white —
   and since the source's chroma noise differs block to block, each block landed
   on a different tint. Replaced with a knee: the gain ramps in over the first
   0.10 of saturation, so near-neutrals keep a gain of ~1.0 and only real colour
   is boosted.

   Its stated purpose was to drag the frame-mean saturation up to
   @courtroomtime's 0.546. **That reason is already dead** — the 2026-08-23
   winners-vs-losers pass measured 25 files on that channel and saturation does
   not separate winners from losers; their losers came out slightly MORE
   saturated (0.575 vs 0.546, trend running the wrong way). There is no target
   mean worth defending.

2. **No chroma denoise.** The source is 4:2:0 video upscaled ~4x, so its chroma
   planes are quarter-resolution and carry block noise. A median filter on Cb/Cr
   only now runs before any saturation work — luma, and therefore every real
   edge, is untouched.

3. **UnsharpMask threshold was 3**, low enough to sharpen compression noise in
   flat regions and crisp the block edges. Raised to 10.

Re-graded and verified clean on all four shipped thumbnails (CARTHIEF, SANCHEZ,
OFFERUP, MONKEY). MONKEY's local file is fixed but the LIVE video on YouTube
still carries the old blocky thumbnail — it has not been re-uploaded.

## 2026-08-28 — Nathan's frame-selection rule (his eye, not a detector)

Verbatim, choosing between three thumbnail variants per case:

> "i like C on car theif A and B on sanchez and C on offerup because of how
> jusge boyd is positiononed in them because the other shots of her dont make
> sense or are bad because shes not looking in some but in sanchez case i picked
> a and b becase her hand added a little more drama"

**The rule: Judge Boyd's eyes must be LEVEL and DIRECTED — looking at the
defendant or off-frame — never cast down.** A gesture (raised hand mid-air)
adds to it. Confirmed by looking at the six candidate frames side by side:

* rejected — CARTHIEF A/B (eyes down at papers), SANCHEZ C (hand resting on
  chin, eyes lowered), OFFERUP A/B (eyes down at the desk)
* picked — CARTHIEF C (eyes level through glasses), SANCHEZ A/B (raised hand
  mid-gesture, eyes level), OFFERUP C (eyes level, mouth open mid-sentence)

Note SANCHEZ: the rejected frame HAS a hand in it, resting on her chin. So it
is not "a hand is good" — it is a hand *mid-gesture*, in the air. A static hand
reads as thoughtful, which is the opposite of the wanted register.

**I could not measure this automatically and did not fake it.** Tried: Haar eye
count, eye-region dark fraction, eye-region std-dev. The dark fraction on the
Sanchez pair came out 27.0% (picked) against 27.2% (rejected) — separates
nothing. Eye count was weakly directional (picked 6/3/7, rejected 4/3/4) but
tied on the exact pair where his reason differed. Gaze PITCH is what matters and
Haar cascades do not measure it. mediapipe, dlib, face_alignment and insightface
are all absent from this machine; `cv2.face` (FacemarkLBF) exists but needs a
model file that is not present.

**So the mechanism is a contact sheet, not a detector.** Extract N candidate
Boyd frames across the hammer moment, lay them out, and let him pick — his eye
is the instrument and the job is to make choosing cheap. `scripts/` already
sweeps frames this way (see the 2026-08-27 reaction sweep).

### A/B sets restructured after his picks

Every variant now uses the Boyd frame HE approved, and only the TEXT varies —
so the test measures wording, not composition. Before this, variant C changed
the frames as well, which confounded the two.

    READY-TO-POST/AB-THUMBNAILS/<CASE>_thumb_{A,B,C}.jpg
    READY-TO-POST/<CASE>_thumbnail.jpg          <- variant A, the shipped default

Also fixed on this pass: the arrow was hardcoded to Thompson's tip (0.29, 0.52)
on all three and landed on empty ceiling. Now per-thumbnail angle and scale —
CARTHIEF 128 deg x1.30, SANCHEZ 112 deg x1.55, OFFERUP 140 deg x1.40. `auto`
mode aims at the detected defendant face but is NOT trustworthy on this footage:
it picked the ATTORNEY on CARTHIEF (he stands closer to camera than his client)
and found no face at all on ROMERO. Same failure as the reaction sweep — on this
docket Haar reliably finds the lawyer, not the defendant.

## 2026-08-27 — thumbnail settled: clone the SHIPPED Thompson, not a competitor

`scripts/make_thumbnail_v5.py` produces `READY-TO-POST/MONKEY_thumbnail.jpg`
(1280x720, 292 KB). One command reproduces it:

    python scripts/make_thumbnail_v5.py       --plate  <defendant tile frame> --cutout <judge cut-out>       --white "No monkey business" --yellow "in my court!"       --arrow 0.29,0.55 --subject-h 0.95 --max-lines 2       --plate-headroom 0.12 --force-top       --font research/blender/graphics/fonts_static/Archivo-SemiCond-SemiBold.ttf

Both frames come from src 6733 — the instant she says "you're going to end up in
prison or end up dead" — so the two reactions are the same moment, not stitched.

**Nathan, 2026-08-26: "look at their placment all you have to do is literally
copy all of it but with the otther stuff."** The reference is OUR OWN shipped
`1_LONGFORM_thumbnail.jpg`, measured off the pixels: type inset x23 y31, cap
71px (0.0986 H), white->yellow break, 11px stroke plus a black glow, red arrow
105x76 (0.41% of frame) pointing down-left into the defendant, judge cut out and
bled off the right edge over a courtroom plate carrying the defendant.

### Four wrong turns, all now measured rather than assumed

1. **`research/reference/competitor/THUMBNAILS.md` is WRONG** and v2 was built on
   it. Its §5 claims 9/12 of Audit the Court's are "a subject cut out over a
   second courtroom plate, feathered". Opening all 12 images: no cut-out, no
   feather, no matting anywhere. They are hard-edged vertical panel splits.
   Do not plan from that file.
2. **Audit's top-left type is refuted by the only controlled evidence we own.**
   `research/reference/courtroomtime/thumbs/` is 25 files split top_/bot_ on ONE
   channel covering THIS docket. 12 of 15 winners have zero text pixels above
   y=0.20H — they put type on a manufactured bottom plate. Numbers in
   `research/THUMBNAIL-MEASURED-2026-08-23.md`. That template is real but it is
   a different channel's house style; v5 matches ours instead.
3. **A zero-overlap "type never touches a face" guard rejects our own shipped
   thumbnail.** Measured: 18.8% of Thompson's text pixels sit inside Judge
   Boyd's raw Haar face box, 36% padded — its line crosses her hair and forehead
   and stops above her eyes. So the guard protects from the BROW LINE down, and
   only the two subjects; a bystander attorney was being protected too and his
   box alone shrank the clear band below what one line needs.
4. **Montserrat Black is the wrong face for this layout.** The reference runs
   ~0.40 advance/em; Montserrat Black is ~0.60, which collapsed the cap to 44px
   against the reference's 71. Archivo-SemiCond-SemiBold measures 0.42 and holds
   the full 71px. Measured across 14 candidates.

Shipped file overlaps a guarded region by 7.3% of the type block's box — less
than the Thompson thumbnail it copies.

### Copy rule, measured

None of @courtroomtime's 15 winning titles is a quote; all are third-person
editorial ("Judge Boyd Owns Smug Lawyer Who..."). 14/15 winners open with the
literal string "Judge Boyd" against 4/10 losers (Fisher p=0.0068) — that belongs
in the TITLE. "No monkey business in my court!" is first-person and Boyd never
says it; the phrase appears 0 times in the 34,408-word transcript. Nathan was
shown that measurement and chose the line anyway on 2026-08-27. His call, on the
record. The video does deliver the substance.

## 2026-08-23 — caption styling, parked

Nathan rejected the current Anton/gold captions AND all seven alternatives I
rendered. He went back to the previous terminal session, so this is PARKED, not
solved. Do not re-pitch the same seven.

- `scripts/caption_variants.py`  seven treatments off one transcript; adds a
  `place` engine (one event per word at an absolute \pos) so a word can scale or
  take a box without reflowing the line — the limitation
  caption_thompson_style.py documents as a law is only a limitation of the
  `flow` engine.
- `scripts/calibrate_variants.py`  solves vertical placement by MEASURING ink
  over black instead of hardcoding a per-font lead. Converged to 0px residual:
  defendant ink bottom 946, Boyd ink top 974, both 14px off the split.
- `Desktop/Boyd Clips/CAPTION-OPTIONS/`  the seven 10s previews + _COMPARE.png
- KNOWN BROKEN in that batch: G_marker's word spacing (PIL widths disagree with
  libass), and `wrap()` silently dropped words past max_lines — half-fixed, the
  DROPPED guard is in but the variants were never re-tuned.
- `research/captions-2026-reddit.md`  fetched 2026 tooling + failure modes.
- `research/captions-2026-what-the-field-mocks.md`  audience sentiment (YouTube
  comments, like-counts as weight).
- `research/captions-2026-standards-and-practitioners.md`  **the strongest of
  the three** — written BBC / Ofcom / DCMP / 3Play standards, plus the deaf
  accessibility community, plus fact-checker coverage of fake courtroom shorts.

**The two research files DISAGREE and must not be merged.** The mocks file says
gold-highlight captions are named as an AI tell (two YouTube comments, 51 and 0
likes). The standards file searched harder and says NO working editor names
caption typography as an AI tell — the AI-tell literature names the synthetic
voice, the watermark and the hashtags. Reconciliation: some *viewers* say it,
*practitioners* don't. Do not state "our captions read as AI" as fact.

**The better-supported reason to move off the current style**, and the thing to
act on: it has a name — "Hormozi captions" — and is described as a commoditised
shipped preset, by one editor a portfolio disqualifier ("Anytime an editor sends
a portfolio with those… I'm immediately out"). Everyone has it. That is the
"looks basic" mechanism, and it needs no AI-tell claim to stand up.

Settled against my priors, do not re-litigate:
  - No font is community-mocked in the courtroom/shorts territory. **Anton is
    not the problem — do not swap fonts as a fix.**
  - Single-word-at-a-time is the MOST mocked treatment there is (7,100 likes),
    so `B_popword` was a move toward the problem, not away from it.
  - `E_speaker` (colour = WHO is speaking, not WHICH WORD) is the only one of
    the seven that matches broadcast grammar — BBC §8.3 / Ofcom §1.16 use
    colour for speaker ID. Built for the wrong reason, right answer.

Measured violations of published standards in the CURRENT cut — table at the
bottom of the standards file. Short version: ALL CAPS (caps mean shouting),
gold live-word (yellow means *different speaker*, so we inverted its meaning),
3-word rolling window (pre-recorded wants phrase blocks), and a 0.10s minimum
event against BBC's 0.3s/word floor. What is already right: hugging the split
so nothing covers a face, and the black outline.

STILL UNMEASURED, and the only thing that would settle any of it: courtroom-
shorts top vs bottom videos ON THE SAME CHANNEL, caption treatment measured off
extracted frames. That agent was stopped before reporting. Everything above is
what people SAY. Nobody measured what costs views. Do not merge those claims.

Biggest strategic finding, bigger than captions: fabricated AI courtroom shorts
are a fact-checked genre as of Aug 2026 (Lead Stories prebunk). Real footage
gets pattern-matched into it. The inverse move nobody fake does — persistent
on-screen sourcing: court, case number, date.
