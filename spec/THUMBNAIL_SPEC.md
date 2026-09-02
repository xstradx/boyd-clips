# Thumbnail spec — the single source of truth

Written 2026-08-29 from a three-way investigation: every verdict Nathan has given
across 1,156 sessions, every approved and rejected artefact measured, and a
post-mortem of every defect that has shipped.

**This file replaces judgement.** If a build disagrees with a number here, the
build is wrong. If Nathan states something this file contradicts, HE is right and
this file gets edited in the same turn — with the count incremented.

---

## 0. Why the same defects kept coming back

> *"everything I tell you leads you further away from what you've already learned
> and I just don't understand how to stop that"* — 2026-08-29

The mechanism, from the code: **every operation was global and every requirement
he states is local.** "Make the background darker" became a whole-frame multiply;
"more pop" became a whole-frame saturation push. So each instruction moved four
dimensions and broke three of them, and a compensating stage was added to repair
the damage. `v3.py` ended with five corrective stages, four of which existed only
to undo the previous one.

**The rule that follows: one function per dimension, and it may not return any
dimension it is not allowed to move.** Layers stay as separate values until a
single composite at the end. No stage repairs another stage.

---

## 1. The four measured gates that actually separate good from bad

Derived by measuring every approved and rejected file. **0 false positives,
0 false negatives** across the set. Checker: `tools/verify_thumb.py`.

| # | Metric | Approved | Rejected | Catches |
|---|---|---|---|---|
| A | tiled flatness `flatG_p90` (40px tiles) | 0.235–0.297 | 0.373–0.664 | posterisation |
| B | `bg_mush_f1`, background tiles, text masked | 0.295–0.316 | 0.585–0.729 | mushed background |
| C | subject face median L* | 144–160 | 221 | blown-out subject |
| D | duplicate-face SIFT inliers | **0** | 3–14 | the same person twice |

**Gate D is absolute.** All 15 approved and competitor files score exactly zero.
It is the only gate valid on any image from any source.

**A, B and C are PRE-DELIVERY ONLY.** 10 of 12 competitor thumbnails trip A and
3 of 12 trip C *after YouTube re-encodes them*. Running these on a downloaded
thumbnail condemns work that is fine.

### The JPEG trap that invalidates most cross-set comparison

Every competitor thumbnail carries an identical JPEG quantisation table
(sum **736** — YouTube's re-encode). Everything we render is **369**. Our rejected
thumbnails measure *sharper* than all twelve competitors purely because of the
encoder. **Any sharpness, detail or flatness metric compared against a downloaded
thumbnail measures YouTube, not quality.** The only valid quality comparison is
our own files against each other.

---

## 2. Metrics that look decisive and are not

Each of these was tried, validated against known answers, and discarded. They are
listed so nobody re-derives them and ships a false result.

- **Whole-frame flatness.** HS_REMAKE 0.1131, the broken V3 0.1132. The rejected
  range *contains* the approved range. The defect only appears when you tile and
  take the p90. A frame-level number cannot see posterisation.
- **Laplacian variance.** Approved spans 236–2431 — a 10× spread *inside* the
  approved set. Rejected sits entirely within it.
- **Equal-sized, level faces.** Looks like a clean discriminator. It is a mirage:
  **he asked for parity**, verbatim — *"the defendant about the same size as Judge
  Boyd… defendant's gonna be on the left side, Judge Boyd's gonna be on the
  right."* Never "fix" this.
- **Halo / rim detection.** Inverted: approved score *higher* than rejected.
- **Saturation.** `ref9800`, the winning thumbnail, is MORE saturated than a
  thumbnail he rejected.
- **Per-face chroma band-pass.** Ranked the deliberately pure-red arrow as the
  worst blotching, and scored a clean face as the worst offender.

---

## 3. What he actually asks for, ranked by how often he has had to repeat it

From 39 positive and 87 negative verdicts, dated and verbatim, in
`docs/verdicts/team_A_verdicts.md`.

| times | requirement |
|---|---|
| **8** | Surgical cuts — no hard crop, no severed limb, no sticker edge |
| **8** | Judge Boyd not pale / washed out / blue against the defendant side |
| **8** | The arrow must make sense — placement, angle, size, never occluded |
| **8** | Even spacing, defendant toward the middle, size parity with Boyd |
| **7** | Background REBUILT at the new geometry, never reused or stretched |
| **6** | Upscale AND regenerate, not upscale alone |
| **6** | No blown highlights |
| **6** | A real reaction frame, not any frame |

---

## 4. The three principles that resolve his apparent contradictions

Resolved from the full record, **not** by taking the most recent quote.

### 4.1 "Darker" always means LOCAL, around the subjects
Never a global plate level. Every time this was applied as a whole-frame
multiply, the ceiling blew out or the room went muddy and he rejected it. The
courtroom keeps its own measured level; darkening happens as separation *around*
the subjects.

### 4.2 "Pop" means local contrast + subject separation + glow
It does **not** mean saturation. Saturation appears four times in his words and
**every one is qualified by "slight"**. Pushing global saturation to chase "pop"
is the single most repeated wrong turn.

### 4.3 Size is never absolute — it is parity plus edge contact
Never "make her 300px". Always: the same size as the other subject, and touching
an edge so no cut line shows inside the frame.

### 4.4 His colour verdicts are PHONE-referenced
> *"I didn't say go make this picture look good on my monitor."*

His HDR OLED tone-maps: measured, it renders ~40 points more saturation than the
file contains. Several apparent colour flip-flops are mechanically explained by
this. **Never take a colour target from a screenshot of his screen.** Measure the
file. See `[[monitor-oversaturates-judge-from-file]]` in memory.

### 4.5 The Boyd-tint "reversal" never happened
An earlier version of `NATHAN_RULES.md` recorded that he reversed himself on
Judge Boyd's tint and marked the old rule superseded. **That was a misreading.**
The *"we don't have to do that, I kind of like how it is"* was a pass on ONE
image, sandwiched between rejections before and after it. He has complained that
she is washed out or blue **eight separate times**. There is no reversal.

---

## 5. Build order — one linear pass, no compensation stages

```
1  pick reaction frame        -> a frame where the face is doing something
2  HYPIR 4x restore           -> per tile, never on the composite
3  regenerate                 -> Qwen-Image-Edit when available (see R28)
4  matte                      -> BiRefNet + full-res guided filter, ALPHA ONLY
5  place                      -> parity size, edge contact, defendant left
6  grade ONCE                 -> per layer, to its own measured target
7  composite                  -> single operation, float32
8  type                       -> one line, top, sentence case
9  arrow                      -> solved against real mattes and the glyph mask
10 verify                     -> gates A/B/C/D; refuse to write on failure
```

**Rules that make this hold:**

- Nothing after step 6 changes colour. No knee, no re-seat, no settle loop.
- All colour maths in **float32**. Every uint8 round trip costs a quantisation;
  six of them posterised both faces while every gate reported PASS.
- The matte step changes **alpha only**. Verified: `plate_surgical.png` has
  byte-identical RGB to the HYPIR plate. That is correct — a matte that changes
  colour is a bug.
- The source is never the limit. The HYPIR plate scores posterisation **0.000**.
  Every defect ever shipped was introduced downstream.

---

## 6. Verification rules, learned the hard way

A gate that cannot fail is worse than no gate — it manufactures confidence.

- **Every gate must be validated against a known-bad control** before it is
  trusted. Two candidate metrics were discarded only because they were tested
  this way; both would otherwise have shipped as green.
- **Grade the file you built.** The old runner wrote facts once per variant,
  last-write-wins, and graded a different variant — so ~29,000 px of Judge Boyd
  were measured as "background", and two of three variants were never checked.
- **Print the real count.** The old runner executed 15 gates and printed
  `13 - failures` out of 13.
- **A measured number that is printed and ignored is worse than not measuring.**
  The build printed *"62.7% of her old position still showing"* and wrote the
  file anyway. Any measurement that would embarrass us must be an assert.
- **Never author a threshold you invented.** Derive it from the approved set.

---

## 7. Never do these

- Never push global saturation to chase "pop".
- Never darken the whole plate to satisfy "too bright".
- Never use `cv2.inpaint` for background reconstruction — it fills flat and
  measured 785.8 detail against the reference's 2464.7.
- Never resize an RGBA image as one unit; resize RGB and alpha separately.
- Never take a colour target from a screenshot of his monitor.
- Never let the same person appear twice — Gate D, no exceptions.
- Never mark a rule superseded without checking whether the "reversal" was just
  a pass on one image.


---

## 8. Measured settings — every number below was measured, none chosen

Added 2026-08-29 after the rebuild. *"Please learn from all your mistakes and the
things I call out and things I tell you I like."* These are those things, as
numbers, so they cannot be re-litigated or forgotten.

### 8.1 His own regrade is the look target

He took a screenshot of a build and graded it himself. Measured, that regrade is:

| | build | his regrade |
|---|---|---|
| luma | 119.9 | **109.7** |
| contrast sd | 59.5 | **69.3** |
| saturation | 55.0 | **91.4** |
| definition (high-pass mean) | 5.27 | **6.52** (+24%) |

His S 91.4 lands on HS_REMAKE's 98.4. The build was under-saturated **because a
saturation target was set for the background and never for the subjects** — in the
reference the PEOPLE carry the chroma, not the room. Fix at the layer.

### 8.2 The 9800 caption and arrow, sampled off that file

| | |
|---|---|
| caption fill | **#EDCB09** — golden, NOT the primary #FEFB03 |
| caption stroke | pure black |
| caption cap height | **0.167 H** (120px at 720) |
| caption case | **ALL CAPS** |
| caption band | x 0.19–0.78 W, y 0.81–0.98 H |
| arrow size | **0.230 W × 0.263 H** |
| arrow centre | y **0.524 H** |

His *"vibrant, almost golden yellow"* is exactly what his own winning thumbnail
uses. The ALL CAPS here deliberately breaks the Audit sentence-case pattern
because he asked for this specific style — that exception is scoped to the kicker
line, not the top title.

### 8.3 Background blur has a hard measured ceiling

He asked for a slight blur behind both subjects. Measured against gate A:

```
none      flat 0.110  poster 0.0132   ships
sigma 1.6 flat 0.298  poster 0.0133   ships   <- the maximum available
sigma 3.0 flat 0.314  poster 0.0265   BLOCKED
sigma 5.0 flat 0.270  poster 0.0398   BLOCKED
```

Blurring the room IS the mush defect he rejected. At the pixel level there is no
difference between "artistic depth" and "smeared background". **1.6 is the limit.**

### 8.4 Four bugs that were invisible until measured

1. **Save JPEG 4:4:4.** Pillow defaults to 4:2:0. Chroma subsampling makes a*
   piecewise-constant across smooth areas: the composite measured poster_fa 0.000
   and the saved file 0.032. HS_REMAKE is 4:4:4.
2. **Highlight compression must be luminance-only.** Per-channel pulls bright
   pixels toward a common value and flattens their chroma — it took a crop that
   was poster_fa 0.000 to 0.046 in the render.
3. **Gate A is nothing without the text mask.** Unmasked it partly measures how
   much text is on the frame. Text area varies 0.057–0.233 between files, so the
   error is not a constant offset and it destroys separability entirely.
4. **Never estimate a face box from a matte.** Estimating put Judge Boyd's "skin"
   at S 33.9 when her detected face measures S 88.1 — which inverted a balance
   and washed the defendant further in the direction he had just complained about.
   Detect the face inside each layer.

### 8.5 Balance the two subjects at the skin, to their midpoint

> *"boyd is a little too colorful and defendant is a little too washed — make the
> colors meet in the middle between them so it looks as natural as possible"*

Measure saturation on each DETECTED face, take the midpoint, drive both to it.
A whole-silhouette mean is dominated by a black robe and a set of scrubs and says
nothing about skin.

### 8.6 Regenerate the subject's OWN crop before cutting

> *"regenerate in 4k before you surgically cut to replace the picture of her
> that's there now pls don't skip steps"*

Taking the cut-out from a whole-plate HYPIR pass is skipping a step. Crop the
subject from the raw tile, run HYPIR on THAT crop with a caption describing that
person, then matte, then cut. HYPIR is caption-conditioned — a generic plate
caption spends none of its capacity on her face.

### 8.7 Layout, current locked values

| | |
|---|---|
| defendant | LEFT, cx 300 |
| Judge Boyd | RIGHT, cx 990 |
| face heights | **equal**, 300px — parity is a requirement, never "fixed" |
| Boyd frame | **4026** (his pick) |
| top title | "This is why your son is struggling!" |
| kicker | "SHE'S SCARED..." in 9800 style |
| background blur | sigma 1.6 |

Subject vertical placement DERIVES from the title box: the title is sized by
width, so its height is an output, and a taller title pushes the heads down
rather than landing on them.

### 8.8 Open, not solved

**The attorney standing behind Judge Boyd.** *"the attorney behind just kinda
kills it honestly."* He is in the real plate. Covering him needs Boyd larger,
which breaks the size parity in 8.7. Painting him out reintroduces the mush of
§7. Unsolved — do not pretend otherwise.


---

## 9. SANCHEZ, the first one he approved — what went wrong and what we shipped

He approved it for posting on 2026-08-29 with: *"I'm okay with posting this so I
guess take notes of everything that went wrong and what we ended up going with
but remember there's always room to improve."* This is that record.

**Shipped:** `D:\Boyd Clips\READY-TO-POST\SANCHEZ_thumbnail_APPROVED.jpg`
Built by the pipeline, then colour-graded and the arrow repositioned BY HIM, then
grain 1.5 added back. Final: luma 113.2, sd 73.8, S 96.2, b* +14.9, 4:4:4 q95.

### The settings we ended on

| | |
|---|---|
| background | a harvested CLEAN plate — real courtroom, nobody standing, HYPIR 4x |
| blur | sigma 1.6 (hard ceiling; past this it is the mush he rejects) |
| faces | 300px, EQUAL. Defendant left cx 300, Boyd right cx 990 |
| Boyd frame | 4026 |
| title | "This is why your son is struggling!", Anton, ~96.5% frame width, top |
| kicker | "SHE'S SCARED..." ALL CAPS, gold #EDCB09, cap 0.167 H, low |
| arrow | 0.240 W, centre (0.505 W, 0.661 H) — HIS placement, not a solve |
| grade | luma 113.5, sd 73.8, S 96.2, b* +14.9 |
| grain | 1.5, monochromatic, midtone-weighted WITH a floor, applied last |

### What went wrong, in order, and what each one actually was

1. **Flattening things that had detail.** The same bug three times in different
   clothes: resizing RGBA as one unit destroyed the hair band (Pillow flattens
   colour where alpha is soft); a per-channel highlight knee flattened chroma;
   recolouring the arrow collapsed **4,387 distinct colours into one flat red**.
   That last one is the whole reason it read "dead, cheap, fake" for hours.
2. **Sharpening and graining the graphics.** Type, kicker and arrow were being
   composited BEFORE the look pass and grain, so unsharp was crunching antialiased
   letterforms and grain was speckling the glyphs. That is the "processed, heavy,
   not HD" type. Photo is finished first; graphics go on a finished photo.
3. **Inpainting the background.** `cv2.inpaint` fills flat: detail 785.8 against
   the reference's 2464.7. Then removing the inpaint left 62.7% of her original
   silhouette showing — the same person twice, measured, printed, and shipped
   anyway.
4. **Solving a problem that should have been removed.** The contorted crop solver,
   the size bump to 340, the tightened spacing — all of it existed to bury the
   attorney standing behind Boyd. HIS idea (harvest a clean plate) deleted the
   problem, and all three workarounds came out with it.
5. **Gates that measured the wrong thing.** Two of four gates turned out redundant
   (0 FP / 0 FN with or without them) while failing legitimate uniform content.
   One gate ran on a PNG against JPEG-derived thresholds and read 0.50 where the
   same pixels as JPEG read 0.35.
6. **Guessing instead of bisecting.** Four blind changes chasing one number before
   testing which change caused it. The answer was none of them.

### The one rule that would have prevented most of it

> *"you also tend to over complicate stuff... it makes everything counterproductive"*

Every real fix today was SMALLER than the thing it replaced: one line of grain
instead of a crop solver and two gates; a clean plate instead of an inpaint; not
recolouring the arrow instead of tuning its colour. **When a fix is getting
bigger, it is the wrong fix.**

### Still open — there is room to improve

- **Gate A's threshold is stale.** It was derived when grain covered the graphics,
  which hid their flatness from the metric. Now the graphics are correctly clean
  and it reads 0.446 against a 0.30 limit. The number must be re-derived on an
  approved set — and that set is n=2, which is the real bottleneck.
- **The arrow's bend.** He says the 9800's leans toward the subject; ours sits
  flat. Never measured.
- **The Boyd reaction library.** `tools/harvest.py reactions` is written and has
  never been run. No saved reusable cut-outs yet.
- **The push-button wrapper.** `GATES-thumbwrapper.md` has 15 gates across 4
  leaves and none of them have been executed.
- **He is still the calibration set.** Every threshold traces back to two files he
  approved. More approve/reject calls from him buy more than any new code.


---

## 10. The rim, settled

He rejected the outline three times: *"too much in some areas"*, then *"looks so
sloppy still"*, then *"kinda looks like it's scribbled randomly"*. Three separate
causes, found in order:

1. **Bloom.** The ring was `dilate(alpha) - alpha` on a SOFT alpha. Dilating soft
   values blooms, so the outline grew thickest exactly where the matte is most
   delicate — the hair. Fix: build the ring from a HARDENED silhouette
   (`alpha > 0.5`) so its width is constant, and multiply by `(1 - alpha)` so it
   fades out of hair instead of painting over it.
2. **Noise.** The rim traces the silhouette exactly, so every speck, pinhole and
   stray strand became a squiggle. Fix: open/close, keep the largest component,
   fill holes, median the contour — trace ONE smooth closed shape.
3. **The part that cannot be polished.** Hair has a genuinely irregular
   silhouette. A hard line traces every bump of it *by definition*. No amount of
   contour cleaning fixes that, which is why 1 and 2 both fell short.

**Settled: `RIM_MODE = 'smooth'`** — the outline is gated by local curvature. It
stays where the boundary is smooth (jaw, shoulder, cheek) and fades where it is
ragged. He picked it from four options viewed at full size, 2026-08-29.

**The lesson worth keeping:** when a fix does not hold twice, stop polishing and
ask whether the effect is achievable at all in that place. Showing four options
took one round; guessing took three.

### The arrow, settled
He supplied a high-res cut-out (1120x912 on white). Matted by distance-to-white
so the black outline survives, de-fringed, giving 815x591 at 1.1% soft edge.
**De-jagging is now conditional** — it only runs when the source is under 1.5x
the target width. Running that median over a clean high-res asset rounds its
corners and softens the outline, destroying the crispness that makes it look
professional.


---

## 11. Shorts — the short pipeline, 2026-08-29

### 11.1 The colour fix he approved
> *"Colors look really nice"* ... *"Remember how you fixed the color here I really
> like it and it looks natural"*

The short was washed AND its two halves did not match each other — the same
two-camera problem as the thumbnail, and for the same reason.

| | luma | sd | S |
|---|---|---|---|
| top (Boyd) BEFORE | 161.9 | 67.9 | 40.4 |
| bottom (defendant) BEFORE | 128.2 | 69.5 | 61.8 |
| top AFTER | 121.8 | 73.6 | 78.2 |
| bottom AFTER | 116.7 | 73.1 | 73.3 |

34 luma apart -> 5 apart. Final sd 73.4 against the approved thumbnail's 73.7.

**Grade each half separately, never the whole frame:**
```
top:    eq=brightness=-0.149:contrast=1.10:saturation=1.45
bottom: eq=brightness=-0.0201:contrast=1.06:saturation=1.16
```
Brightness was SOLVED by bisection against a luma target of 120, not chosen. Do
that again per case — these numbers are for this footage, the method is general.

### 11.2 Audio: the problem was tilt, not noise
Measured: SNR 39.7 dB (fine) but the 2-4 kHz presence band sat **26.2 dB** below
100-500 Hz. Courtroom mics in a hard room pick up boom. Denoising alone would
have done almost nothing.

`tools/enhance_audio.py` — highpass 85, -4 dB at 250, gentle afftdn, **+6 dB at
2600 and +3 dB at 4200**, de-ess, compress, speechnorm, loudnorm I=-16.
Result: tilt 26.2 -> 18.0 dB, presence 11.4 -> 24.6 dB, +7 dB louder.

**The transcriber was never the bottleneck** — word confidence only moved 0.971
-> 0.986. The audio was hard for HUMAN ears, not for Whisper. Enhancement is for
playback; do not justify it as a transcription fix.

### 11.3 Captions
> *"straight in the middle of their split screen"*, *"don't let them be all long
> like where it touches the ends"*, *"the words sitting right in the middle of
> the line"*

`tools/caption_short.py`. The seam is FOUND (largest horizontal luminance
discontinuity in the middle third), not assumed — measured y=959 of 1920.
Captions use ASS `n5` + `\pos(540, seam)`: centred ON the line, never above or
below it. Cards capped at 20 CHARACTERS, which is what actually drives rendered
width. Anton, cap 104px.

The old behaviour moved captions to the speaker's half, which is why they jumped
between tiles.

### 11.4 The end card
> *"a pop up somewhere where the person can clearly see and let them know the
> full video is linked... a pop up sound when the line came up"*

Gold card, black Anton, **"FULL VIDEO OUT NOW"**, centred at y=1580, 2.6s-7.2s,
fading in and out. The pop is SYNTHESISED locally (`pop.wav`, 260ms: pitch drop
+ click + shimmer, hard attack, fast decay) — no licence question and it can be
retuned.

**Two bugs worth remembering:** a single PNG input has one frame at PTS 0, so
`fade=st=2.6` never fires and the card stays invisible — it needs `-loop 1 -t`.
And dropping `fontsdir` silently falls back to a default font; Anton looked
"thin" only because a contact sheet had downscaled it.

---

## 12. The plate must be FACE-FREE, and the pipeline is one command — 2026-08-29

### 12.1 The plate must not contain OUR SUBJECT (not: "zero faces")

`READY-TO-POST/QUIET/CARTHIEF.jpg` was used as a clean plate and was not one. It
was a frame lifted from an EDITED video: the defendant and his attorney were
still in it, along with burned-in subtitles ("Cuz it's too fun there") and a
187th DC bug. Consequences, both caught:

- Gate D blocked the build at **9 SIFT inliers** — the defendant appeared twice,
  once in the background and once as the cut-out.
- Nathan saw it independently and named it exactly: *"the black letters are
  still there in the thumbnail"*.

`harvest.py backgrounds` ranks by STANDING coverage, so it will happily return a
plate holding five seated gallery faces — two of its three CARTHIEF candidates
did. Standing coverage is not the test.

**CORRECTED same day.** I first wrote the rule as "a plate must contain ZERO
detected faces". That is wrong, and his own approved SANCHEZ thumbnail disproves
it: its plate holds **12 detected faces** and passes Gate D. Seated gallery
strangers are normal courtroom and are not the defect.

**The actual rule: the plate must not contain OUR SUBJECT.** That is exactly
what Gate D measures, so Gate D is the authority - not a face count. A face
count as a hard gate also fails outright on MONKEY, whose only face-free
candidate was t=0, the black intro sting (sd 0.4).

`pick_clean_plate()` therefore: rejects DEGENERATE frames (sd < 5), ranks by
room detail, and breaks ties toward fewer faces. CARTHIEF still resolves to
`bg_CARTHIEF_3554.png` and Gate D went 9 inliers -> **0**.

Never hand-pick a plate out of QUIET/ again. The others in that folder have not
been checked and are suspect for the same reason.

### 12.2 The kicker is clamped to the frame, not just placed in a band

`KICKER_BAND[1]` positions the TOP of the text box, which bounds nothing. On
CARTHIEF, size 139 at y=558 put **475 gold pixels on the very last row**, bottom
margin 0 — the kicker was running off the frame. A band is a target; the edge is
a limit. `kicker()` now measures the real ink box including `stroke_width` and
clamps y to `H - KICKER_MARGIN - ink_h`, logging `kicker_clamped_from` when it
fires. Margin 16px. After: bottom margin 8px of fill, 0 px on the last row.

### 12.3 The whole build is `tools/thumb_pipeline.py`

His instruction: *"You have to make them correctly every single time the entire
thing with regenerating and the lighting and the background and cutting and all
of that every single time... Go back and basically follow all the steps."*

The SANCHEZ build only ever existed as loose scratchpad scripts, which is how
steps got skipped. One command now runs frames -> face-free plate -> HYPIR 4x
per crop (caption-conditioned) -> BiRefNet matte (alpha only) -> face detect ->
composite -> gates, and every stage is resumable.

**HYPIR runs on `C:/Users/natha/miniconda3/envs/wan2gp/python.exe`** — torch
2.7.1+cu128, diffusers 0.36.0. NOT the Fooocus venv, which has torch but no
diffusers and fails on import. That was recorded wrongly and cost a run.

### 12.4 Detect the face on the RAW crop, never on the HYPIR output

`thumb.cut()` scales each layer so the DETECTED face box becomes `FACE_H`. That
makes the detector the thing that sets parity — so a bad box silently breaks the
rule that parity is a requirement.

Measured on MONKEY: YuNet on `judge_hypir.png` returned a **648px** box at score
**0.66**; her real face is ~979px. The layer was therefore scaled so a
34%-too-small box hit 300px, rendering her actual face at **453px**. Both people
came out as giant cropped heads — and **every gate passed**, because no gate
measures face parity. The same crop pre-HYPIR detects at **0.92**.

**Rule: detect on `*_raw.png` and multiply the box by the HYPIR upscale factor.**
Restoration changes local contrast and texture, which is exactly what a face
detector keys on; the source is the reliable reference.

Corollary worth remembering: this defect was invisible to A, C and D. Gates
catch what they measure and nothing else — look at the picture.

### 12.5 Trim the plate border: the stream burns its own label into it

Every 187th DC stream carries an on-screen court label ("187TH DC", "Judge
Boyd"). It survives harvesting and lands in the thumbnail background as stray
text — the same class of defect as the CARTHIEF subtitles Nathan caught.
`pick_clean_plate()` now crops `PLATE_TRIM = 4%` off each edge, which cleared the
label on every plate measured. Trim, do not inpaint (§7).

### 12.6 A third element is supported, and the arrow can be retargeted

`Thumb.extra = dict(png, h, cx, cy)` composites a prop WITH the photo layers, so
it takes the same look pass, grain and rim — a prop pasted after finishing reads
as a sticker. `Thumb.arrow_xy` overrides the placed arrow position.

Built for MONKEY on his instruction: *"Cut out the monkey put him in the
thumbnail and point the arrow at him."* The monkey is the subject of that
hearing, so he is what the arrow serves. He is deliberately NOT HYPIR'd — source
is 634x793 and he lands 352px tall, so restoring would only soften a downscale
(the arrow lesson, §10).

### 12.7 Gate A flags a file that already shipped — the threshold is not trustworthy

Measured 2026-08-30 across every finished thumbnail:

| file | flat_g_p90 | Gate A (limit 0.30) |
|---|---|---|
| CARTHIEF_thumbnail_V2 | 0.0169 | pass |
| MONKEY_thumbnail_V2 | 0.1234 | pass |
| THOMPSON_thumbnail_V2 | 0.1700 | pass |
| SANCHEZ_thumbnail_APPROVED | 0.2315 | pass |
| OFFERUP (rejected by the gate) | 0.3791 | **FAIL** |
| **SANCHEZ_thumbnail_FINAL — already in READY-TO-POST** | **0.4055** | **FAIL** |

A file that shipped scores WORSE than the build the gate was blocking. The
threshold does not separate good from bad at this boundary, and §1's own caveat
says why: it was derived on an approved set of n=2.

**Do not lower the threshold to make a build pass** (§6: never author a threshold
you invented). Re-derive it against a larger approved set, and until then treat a
0.3-0.4 reading as "look at it", not "reject it".

**Also measured: Gate A can be satisfied by covering the frame with faces.**
OFFERUP at `face_h=400` scored 0.2828 and passed while looking obviously wrong -
Boyd reduced to hair, the defendant's face cut off at the bottom. flat_g_p90
measures flatness, not composition, so a passing number is not evidence the
image is good.

### 12.8 What actually drives flat_g_p90 in a composite

Ruled out by measurement on the failing OFFERUP build, in this order:
- **judge frame choice** — reframing on hair detail moved 0.4024 -> 0.4024
- **source layer flatness** — OFFERUP's own layers are the LEAST flat of the
  three cases (0.2097 vs CARTHIEF 0.3130)
- **grain** — 1.5 / 2.5 / 3.5 / 4.5 all sat at 0.39-0.40. Grain is not the lever.
- **crop width** — tight 152x161 vs wide 340x338 moved 0.4024 -> 0.3791
- **background blur** — 1.6 -> 0.6 moved 0.3791 -> 0.3207, still failing
- **plate choice** — best plate by post-blur flatness beats the worst by ~0.006

What DOES drive it: **how much canvas the subjects cover.** CARTHIEF's plate is
the flattest of all after blur (0.4146) yet its composite is the cleanest
(0.0169), because its subjects cover more frame. MONKEY and OFFERUP share an
identical plate (0.3028) and composite to 0.1234 vs 0.3791.

**Consequence for `pick_clean_plate`:** it ranks candidates by Laplacian detail,
but the gate measures flat-pixel share after a 1.6 blur. Those are different
metrics and the ranking disagrees - `bg_MONKEY_420` has 6x less detail than
`bg_SANCHEZ_4391` yet blurs to a comparable flatness. Rank by the metric the
gate uses.

### 12.9 autocrop was the wrong fix, and why it is kept anyway

`FACE_FRAC_TARGET = 0.42` was added after MONKEY rendered giant cropped heads.
That was misdiagnosed: **the real cause was detecting the face on the HYPIR
output instead of the raw crop** (§12.4). CARTHIEF composes correctly with its
face at 23% of a 620x338 crop, so a wide crop with a small face fraction is fine.
Forcing 42% on OFFERUP shrank its crop to 152x161, the subject then covered too
little canvas, and Gate A failed.

Use autocrop only to CENTRE a subject and exclude the wrong person from the
region - never to tighten a crop that already frames the subject.

### 12.10 NEVER build a thumbnail from one of our own renders

MONKEY's defendant came out soft and waxy no matter what HYPIR did, because the
source was `READY-TO-POST/MONKEY_LONGFORM.mp4` — **our own finished render**, a
letterboxed composite already upscaled to 1080p and re-encoded.

| | resolution | sharpness |
|---|---|---|
| our render (what was being used) | 1920x1080 | **190.3** |
| original stream clip | 1280x720 | **714.9** |

The original is LOWER resolution and **3.8x sharper**. On the defendant crop
specifically: **45.4 -> 767.4**, and after HYPIR **92.7 -> 422.6**.

HYPIR restores; it does not invent what a second-generation encode threw away.
Compare CARTHIEF, which always looked right: its source is a direct clip of the
court stream at 446.7 sharpness.

**Rule: `cases.json.video` must point at a `work/<id>/` clip of the original
stream, never at anything in READY-TO-POST.** Check it before prep — the defect
is invisible in the config and only shows up as a soft face at the end.

### 12.11 Gate D must ignore nested detections

YuNet fires small extra detections INSIDE a real face. On MONKEY it returned a
32x42 box at (1000,471), sitting inside Judge Boyd's own 183x254 box; SIFT
matched them at 9 inliers, which is correct — they are the same pixels. That is
one person detected twice, not the same person twice, and it failed a good build.

`_dup_inliers` now skips a pair when the intersection exceeds 50% of the smaller
box. Verified with `--selftest` that Gate D still fails on a genuine duplicate.
