# STING-SPEC.md — Texas Trial Tracker

**The design spec for the TTT channel sting.** Build notes and API idioms are in
`BLENDER-CAPABILITY.md`; this file is the design decision record. Every number here traces to
a measurement that survived adversarial review. Where a plausible-sounding rule was *disproved*
by measurement, it appears only in §11 as a do-not.

---

## 0. The three decisions that shape everything else

**0.1 — The sting does not run before the hook.**
Nine of ten channels in TTT's exact lane ship no head sting at all: That Chapter, Explore With
Us, Coffeezilla, Barely Sociable, MrBallen, Internet Historian, Fascinating Horror, Scary
Interesting, Wendigoon — all cold-open on picture, verified by scene-cut and luminance analysis.
LEMMiNO is the only exception and it front-loads 1.5 s. The market in this genre has already
decided a head sting is optional, so the sting runs **after the hook, at the first chapter
break** (typically 20–45 s in), where it costs retention nothing and reads as a chapter marker
rather than a toll booth.

**0.2 — The motion is a SHEAR, because the mark is a shear.**
Measured on `logo_transparent.png`: crossbar top edges run at **0.00°** over 351 px of travel;
all three stems lean **9.08°** from vertical, drifting exactly 43 px over 269 px of rise; stem
width is a constant **122–123 px** top to bottom. A rotation would tilt the crossbars. A scale
would change the stem width. Neither happens — the mark is a **pure horizontal shear of flat
polygons**, and that is its entire grammar. Shear is closed under composition, so a mark that
arrives over-sheared and settles is *never illegal at any intermediate frame*: crossbars stay
pinned at 0.00°, stem width stays constant. No other channel can copy this reveal, because it
is derived from this mark's construction.

**0.3 — `logo_transparent.png` is a production blocker and must be redrawn before a frame is
rendered.** See §12.

---

## 1. Format

| | |
|---|---|
| Master resolution | **1920 × 1080** |
| Master frame rate | **60 fps** (`fps=60`, `fps_base=1.0`) |
| Total length | **84 frames = 1.400 s** |
| Delivery rates | 60 fps master; 30 fps conform (42 frames) by frame decimation, **not** re-authoring |

**Why 60, not 30.** The single closest reference (LEMMiNO) is natively 1920×1080 **at 60 fps**;
the original recon measured a 854×480/30 fps proxy and lost half the frames, which is what
destroyed its easing and audio conclusions. The reveal's opacity ramp is 11 frames at 60 fps —
5.5 frames at 30, i.e. unrepresentable. Author at 60 and conform down.

**Why 1.400 s.** A YouTube channel sting is not a distributor ident. Measured totals:
LEMMiNO **1.500 s**, HBO Max Originals 2.92 s, Netflix 4.108 s, Apple TV 5.005 s, A24 (2013)
7.588 s. The distributor lengths are earned by a two-hour film the viewer already paid for.
The YouTube-native band is 1.2–1.5 s; 1.400 s sits inside it without matching LEMMiNO's number.

---

## 2. Beat sheet

All frame numbers are 60 fps. The 30 fps conform is in the last column.

| beat | frames | dur | what happens | @30 |
|---|---|---|---|---|
| **A — GROUND** | 1 – 24 | 24 f / 400 ms | Ground `#15181D` full frame with live grain. Nothing else on screen. Audio riser runs alone. | 1 – 12 |
| **B1 — STAR ON** | 25 | 1 f | Red star cuts on at full opacity, at its rest position, unsheared. A hard cut, not a fade. | 13 |
| **B2 — TYPE FADE-UP** | 25 – 36 | 12 f / 200 ms | Wordmark alpha 0 → 1. | 13 – 18 |
| **B3 — SHEAR SETTLE** | 25 – 48 | 24 f / 400 ms | Wordmark shear K 0.479448 → 0.159816 (25.62° → 9.08°). | 13 – 24 |
| **C — LOCK** | 49 | 1 f | Shear reaches rest. Audio transient peaks. Nothing overshoots. | 25 |
| **D — HOLD** | 50 – 84 | 35 f / 583 ms | Absolutely nothing moves except the grain. | 26 – 42 |
| **E — CUT** | 85 | 0 f | First frame of content. Hard cut. No fade, no dip to black. | 43 |

Proportions: picture is on for 60 of 84 frames; **35 of those 60 (58 %) are a dead hold.**

**Why the hold is that large.** This is the actual expensive-vs-template tell. Apple TV's 2025
ident spends 72 of its 120 frames — **60 %** — with the settled mark holding still; its build is
only 25 %. Template stings animate continuously because motion is the product being sold. If
the mark is never still, nobody ever reads it.

**Why the sound runs alone for 400 ms first.** Measured at native 60 fps, LEMMiNO's audio begins
at 83 ms and its picture at 633 ms — the sound is alone for 550 ms, 37 % of the runtime. That
is the real structure and it is the opposite of "add a whoosh to the animation." Scaled to a
1.400 s asset, 400 ms is 29 %. It is not dead air: the brand ground is on screen from frame 1
and it is a designed field.

**Why the exit is one frame.** Every modern ident measured cuts in a single frame:
Netflix YAVG 17 → 0, HBO Max Originals 79 → 16, Apple TV 15 → 1. Only the 1990s HBO (14-frame
fade) and 2013 A24 (~25-frame fade) dissolve, and they read their age.

---

## 3. What moves — exact values

### 3.1 The shear

| | |
|---|---|
| Rest shear coefficient | **K_rest = tan(9.08°) = 0.159816** |
| Start shear coefficient | **K_start = 3 × K_rest = 0.479448** (25.6153°) |
| Travel | ΔK = 0.319632 = exactly **2 × the mark's own lean** |
| Pivot | the **baseline** — the bottom edge of the stems. Feet never move; only tops travel. |
| Duration | frames 25 → 48 (24 f / 400 ms) |

At the specified mark size (§4), stem height is 129.5 px, so the mark's own built-in lean is
20.7 px and **the tops travel exactly 41.4 px — twice that lean — and land on it.**
1.72 px/frame at 60 fps, 3.4 px/frame at 30 fps: smooth, sub-pixel-clean, and readable.

Every one of those numbers is derived from the mark rather than chosen. Nothing here is a taste
call except the multiplier 3, and that has a stated failure mode: **if in review the settle
reads as too subtle, raise K_start to 4 × K_rest. Do not add a second kind of motion.**

### 3.2 The opacity ramp

Wordmark alpha 0 → 1 over frames 25 – 36 (12 f / 200 ms), running *underneath* the shear, which
continues for another 12 frames after opacity completes. So the mark is fully present while
still settling — the settle is the last thing you see.

**Why an opacity ramp at all.** The reference has one and the original recon missed it. At
native resolution LEMMiNO's max luma climbs `38, 57, 76, 96, 118, 135, 150, 178, 190, 207, 228,
248` across frames 38–48 — an **11-frame / 183 ms** fade-up — while the reveal edge advances only
48 px of its 882 px travel. The mark dissolves up, *then* resolves. 200 ms is that, rounded.

### 3.3 The star does not move

The star is on screen at full opacity from frame 25 and never shears, never scales, never
translates. It is a fixed point that the type shears **into register against**.

**Why.** The 93 px / **28.3 %** overlap between the star and the third T's ink is the only place
the mark breaks its own grid, and it is the only tension in the composition. Motion that
separates them destroys it. During beat B the over-sheared third T reaches further under the
star; as the shear settles it withdraws to the designed 93 px, and that closing of the register
*is* the lock. The transient lands there.

This requires the redrawn mark to ship as **two separately transformable objects** — `WORDMARK`
(the three T's) and `STAR`. See §12.

### 3.4 The grain

Live white noise, reseeded every frame, added in linear.

| | |
|---|---|
| Amplitude | **0.0015 linear** (≈ +0 to +3 sRGB codes on the ground) |
| Reseed | per frame, via `SceneTime.Frame → WhiteNoise.W` (4D noise) |
| Runs | frames 1 – 84, unbroken, including the audio-only beat |

**Why grain, when the references look flat.** They only look flat because they were measured
through VP9: temporal standard deviation is **0.00** in every downloaded reference file and
spatial sd is 0.00–1.97 — the codec annihilated all grain and halation. "The pros ship flat" is
a measurement of the encoder, not of the design. Meanwhile the current top-of-market brief
(DixonBaxi, WBD Olympics, Feb 2026) names **"flexible texture"** as a shipped system component
alongside logos, palette and motion. And practically: a large flat `#15181D` field is exactly
what YouTube's VP9 bands, and grain is what stops it.

Working idiom and the measured amplitude ladder are in `BLENDER-CAPABILITY.md` §1.13. Amplitude
0.02 lifts the ground to roughly `#2B2B2B` — 10× too strong.

---

## 4. Layout

| | value | of frame |
|---|---|---|
| Mark bounding box | **680 × 260 px** | 35.4 % w, 24.1 % h |
| Lit pixels | ≈ 59,758 | **2.88 %** |
| Position | optically centred, mark centre at frame centre | |
| Aspect | 2.6167 : 1 (locked — 1413/540) | |

**Why 680 wide and not ~57 % like LEMMiNO.** The real restraint measurement is the *lit-pixel
budget*, not the width: LEMMiNO lights only **2.89 %** of pixels above luma 100. Matching its
width percentage would blow the height budget, because its wordmark is 6.1:1 while TTT is
2.6167:1. Matching the lit-pixel budget instead — TTT's mark is 33.8 % ink inside its own
bounding box, measured — gives 680 × 260 and lands at 2.88 %. A mark filling 80 % of frame width
with a glow is what reads as a template preset.

---

## 5. Easing

**One curve, everywhere: `cubic-bezier(0.42, 0, 0.58, 1)` — symmetric ease-in-out.**
Applied identically to the shear F-curve and the alpha F-curve. One curve because the piece is
one object.

**Why symmetric, when every design system says otherwise.** It was measured. Fitting five
candidate curves to LEMMiNO's actual reveal by RMS error at native resolution and frame rate:

| curve | RMS error |
|---|---|
| **symmetric ease-in-out (0.42, 0, 0.58, 1)** | **0.0376** |
| linear | 0.1086 |
| IBM Carbon entrance-expressive (0, 0, 0.3, 1) | 0.2638 |
| M3 emphasized (0.2, 0, 0, 1) | 0.3089 |
| M3 emphasized-decelerate (0.05, 0.7, 0.1, 1) | 0.4550 |

The reference's mid-phase per-frame deltas at 60 fps are near-constant
(8, 8, 10, 12, 14, 16, 16, 16 px/frame) with ease at both ends — a symmetric S, decelerating
only in the last 8 frames. See §11.2 for why the design-system tokens are wrong here.

Blender idiom for placing these handles is in `BLENDER-CAPABILITY.md` §1.8. Verified evaluation
over 6 frames: `[0.2, 0.2653, 0.4655, 0.7345, 0.9347, 1.0]`.

---

## 6. Colour

All values delivered **exactly**, via `image_settings.color_management = 'OVERRIDE'` +
`view_transform = 'Standard'` (`BLENDER-CAPABILITY.md` §5). At the Blender default AgX the
accent ships as `#C4372A` and the ink as `#C0BFBB` — a visible brand miss.

| role | hex | linear RGB |
|---|---|---|
| Ground | **`#15181D`** | `(0.007499, 0.009134, 0.012286)` |
| Ink (wordmark) | **`#F2EEE3`** | `(0.887923, 0.854993, 0.768151)` |
| Accent (star) | **`#D42B2B`** | `(0.658375, 0.024158, 0.024158)` |

### 6.1 The ground is `#15181D` because it is the brand, not because "lifted black is correct"

That justification was **disproved**. Measured sRGB backgrounds of the reference set after
correct limited-range YUV → RGB conversion: Apple TV `#000000`, HBO Max Originals `#000000`,
Nick Crowley `#000000`, Netflix `#010101`, A24 `#030303`, HBO-1990s `#101010`, LEMMiNO
`#111111`. **Five of seven are pure or effectively pure black**, including all three modern
best-in-class references. `#15181D` is lighter than every one of them and the only blue-tinted
ground in the set.

Keep it anyway: it is the ground of the banner and every other TTT asset, consistency across the
system is worth more than matching a reference, and a lifted ground plus grain is what survives
VP9 without banding. But state the reason honestly — it is a brand position, not a measurement.

### 6.2 The ink is already almost the exact inverse of the ground

LEMMiNO's ground/ink pair is `#111111` / `#EEEEEE` — exact hex mirrors, the mark sitting as far
below white as the ground sits above black, and **238 rather than 255 is what stops it ringing
against near-black without any glow**. `#15181D` inverted is `#EAE7E2`; TTT's ink is `#F2EEE3`
— within 8/255 on the strongest channel. **This is why the mark needs no glow, ever.** Do not
"help" it with bloom.

### 6.3 One red. `#D42B2B`.

The assets currently disagree: `#D02D2E` in `logo_transparent.png` and in the star of every
banner, `#D42B2B` in the rule of `banner_04_rule.png` / `safe_04_rule.png`, and `#D42B2B` is
what the brand doc states. The two are **1.02 : 1** apart — nobody will ever see the difference,
which is exactly why it will survive uncorrected into every future asset and quietly rot the
system. Ship `#D42B2B` and reissue the logo.

### 6.4 Never set type in the red

`#D42B2B` on `#15181D` is **3.47 : 1** — WCAG AA-large only, fails AA body. The red is a marker,
not a text colour, and using it for type would also dilute the star's exclusivity. Ink is
15.35 : 1; the muted system tone `#A8A49C` is 7.16 : 1 (AAA).

---

## 7. Audio

**Do not ship this silent.** Every ident measured with a real audio track carries a transient at
the reveal: Netflix −16 dBFS, HBO −28, LEMMiNO −17.6. The only silent file in the reference set
read as 7.6 s of stall. On YouTube a silent sting arrives immediately after the previous video's
audio stopped, so the viewer reads the silence as a buffering fault.

### 7.1 Structure

| layer | frames | spec |
|---|---|---|
| **Riser** | 1 – 48 (0 – 800 ms) | Exponential sine sweep 45 Hz → 165 Hz. Envelope from silence to **−38 dBFS RMS** at f48. |
| **Transient** | peak at **f49** (816.7 ms) | (a) 55 Hz sine, 8 ms attack / 220 ms decay; (b) band-passed white noise 800 Hz – 4 kHz, 2 ms attack / 60 ms decay, −12 dB relative to (a). |
| **Peak** | f49 | **−17.6 dBFS RMS**, true peak ≤ −8.2 dBFS |
| **Bed** | f50 – f84 and beyond | decays to **−36 dBFS RMS** over ~20 frames and runs under the cut into content |

Bed-to-peak dynamic range ≈ **35 dB** — measured on the reference, and a lot more headroom than
a stock "logo whoosh" uses. The riser is what buys the sting its perceived scale; without it the
impact is a thud. LEMMiNO's riser is 833 ms; this is 800 ms.

The attack is **one frame**: the reference goes −36.8 → −18.7 dBFS RMS between two adjacent
60 fps frames. One transient, not stacked whooshes.

### 7.2 Sync tolerance — the transient lands ON the lock, not before it

**The peak must fall in frames 47–49, i.e. between 0 and −33 ms relative to the lock. Never
earlier.** Measured at native 60 fps, LEMMiNO's audio peak leads the reveal's centre-crossing by
**67 ms** and *lags* full opacity by 50 ms — it sits essentially on the visual event.
ITU-R BT.1359-1 puts audio-leading-video detectability at **+45 ms** and unacceptability at
**+90 ms** (versus −125 / −185 ms in the other direction — the asymmetry runs against leading).
See §11.3.

### 7.3 Synthesize it. Do not license it.

This asset plays on **every** upload, so a single Content ID match compounds across the entire
library. "Royalty-free" is not claim-free: Pixabay's licence permits commercial use but forbids
standalone redistribution, and rights holders can still register audio with Content ID, so a
legally licensed sound can be claimed anyway. Both layers here are a sine sweep and filtered
noise — roughly 30 lines of code, and unclaimable. Render to 48 kHz PCM and mux with Blender's
VSE (`BLENDER-CAPABILITY.md` §1.6) or with ffmpeg.

---

## 8. The handoff into content

* **f84 is the last sting frame. f85 is content.** Hard cut. No dissolve, no dip to black, no
  cross-fade.
* **Audio crosses the cut.** The −36 dBFS bed runs 8–12 frames into the content. VO starts
  4 frames after the cut. In the reference the mark clears and narration comes up ~4 frames
  later, with audio rising −36 → −25 dBFS across the next 10 frames.
* **The sting's real job is to buy the 1–2 seconds the next line of VO needs.** Handing off to
  picture with audio already moving means it costs almost nothing in retention. Dissolving into
  footage costs you those frames twice.

---

## 9. The tiered system

Ship three things from one asset, not one file. Apple shipped its 2025 ident as 1 s / 5 s / 12 s
for exactly this reason (I measured the 5 s and 12 s cuts at 5.005 s and 12.054 s — the reported
spec is real). A single length forces you to misuse it.

| tier | length | contents | where |
|---|---|---|---|
| **T1 — STAMP** | 24 f / 400 ms @60 | Mark already at rest. Hard cut on, hard cut off. No shear, no fade, no audio. | end cards, chapter cards, Shorts, thumbnails-in-motion |
| **T2 — STING** | 84 f / 1.400 s @60 | The full piece specified above. | once per video, at the first chapter break |
| **T3 — DEVICE** | n/a | The 9.08° edge and the 396.5 px module pitch as a layout system: lower thirds, date stamps, chapter cards, end card, exhibit callouts. | throughout |

**T3 is the one that matters most.** The mark's stem centres sit at x = 205.5, 602.0, 999.0 — a
constant pitch of 396.5 px — and it already contains a rule of three plus a single accent. A
shear-derived device that animates, navigates and reveals information keeps the brand present
for twenty minutes instead of 1.4 seconds. DixonBaxi's podium device for WBD Olympics is exactly
this: a working layout element that happens to also be the brand, shipped to run through 2032.
Combined with §0.1 — nine of ten competitors ship nothing at the head — T3 is where the budget
should go.

---

## 10. Render and delivery

| deliverable | settings |
|---|---|
| **Alpha master** | 1920×1080, 60 fps, PNG16 sequence, `film_transparent=True`, `color_mode='RGBA'` |
| **Alpha video** | QuickTime + **QTRLE** (`argb`) or ProRes **4444** (`yuva444p12le`) — set `ffmpeg_prores_profile='4444'` **before** `color_mode` |
| **Flat delivery** | MPEG4 + H264 + AAC, 60 fps, with audio |
| **30 fps conform** | decimate the 60 fps master; do not re-author |
| Colour | `image_settings.color_management='OVERRIDE'`, `view_transform='Standard'`, `look='None'` |
| Dither | `render.dither_intensity = 1.0` for delivery, `0.0` only for hex-verification renders |
| Engine | `BLENDER_EEVEE` — flat emissive graphics, no light transport needed. ~0.34 s/frame steady state at 1080p, so all 84 frames are ~30 s |
| Verification | external ffmpeg/ffprobe on the delivered file. **Never** `bpy.data.images.load().pixels` (see `BLENDER-CAPABILITY.md` §4.2) |

**Never WEBM/VP9 for the alpha version** — Blender accepts `RGBA`, reports success, and writes
`yuv420p`. Silent data loss.

**Ship one file and never change it.** LEMMiNO's sting is byte-for-byte identical across
unrelated uploads, verified by matching frame-for-frame luminance curves on two different
videos. Consistency is the entire mechanism; a different animation each upload is not a brand.

---

## 11. Deliberately NOT done — and why

### 11.1 No mask wipe. No reveal by uncovering.

A left-anchored horizontal wipe is available to every logo ever drawn, has no relationship
whatsoever to TTT's construction, and **LEMMiNO already owns it in front of this exact
audience** (its bounding-box left edge stays pinned within 9 px across the entire build while
the right edge grows 292 → 671 px). Copying it means the one viewer segment most likely to
recognise the reference will recognise the clone. The shear is the move only this mark can make.

### 11.2 ❌ DO NOT use Material Design 3 or IBM Carbon easing tokens.

M3 `emphasized-decelerate cubic-bezier(0.05, 0.7, 0.1, 1)` and Carbon
`entrance-expressive cubic-bezier(0, 0, 0.3, 1)` are the most machine-readable easing token sets
on the public internet, which is exactly why they get reached for. They are wrong here twice
over. **Empirically:** fitted against the reference, M3 emphasized-decelerate is the *worst* of
five candidates at RMS 0.455 — worse than linear (0.109) — and symmetric ease-in-out, which
those systems explicitly warn against, wins at 0.038. **Categorically:** they are UI motion
tokens, built so a button ripple or a bottom sheet feels responsive to a finger. They encode
nothing about broadcast ident craft, and using them reads as a web designer's ident.

### 11.3 ❌ DO NOT lead the audio hit by 200 ms.

An earlier analysis prescribed "land the audio transient 6–8 frames (200–267 ms) before the
visual lock." That was measured at 30 fps by comparing a windowed RMS **peak** (which lags the
attack by construction) against a luminance **peak** (which lags the visual event) — two
non-equivalent events, with 33 ms quantisation. Re-measured at native 60 fps, the reference's
audio peak leads the centre-crossing by **67 ms** and *lags* full opacity by 50 ms. And
ITU-R BT.1359-1 puts audio-lead detectability at +45 ms and unacceptability at +90 ms.
**A 200 ms lead is more than twice past the unacceptability threshold in the more sensitive
direction and would read as broken sync, not as weight.** See §7.2 for the correct window.

### 11.4 ❌ DO NOT step the build or animate on 2s.

An earlier analysis read "discrete luminance plateaus" in a Nick Crowley title card and
recommended a stepped build. Converted to sRGB, those plateaus are `0.00 → 1.75 → 2.91 → 8.15`
— the entire "stepped build" spans **8 sRGB codes on pure black**, and the frame's modal colour
is `#000000` at 92 % of pixels. It is the frame-mean of a small white card fading up, quantised
by an 8-bit near-black encode. There is no stepped build. Corroborating: at native 60 fps
LEMMiNO's reveal advances on **every** frame with zero duplicate pairs.

### 11.5 ❌ DO NOT justify the ground as "lifted black, never 0."

Disproved — five of seven references are pure or effectively pure black. See §6.1 for the
correct justification.

### 11.6 No transform of the mark other than shear.

No rotation (would tilt the 0.00° crossbars). No non-uniform scale (would change the constant
122–123 px stem width). No scale-from-zero, no fly-in, no perspective, no Z. A logo that flies,
spins or scales is a logo being *handled*.

### 11.7 No dimensionality at all.

No bevel, no extrude, no metallic shading, no HDRI reflection, no glassy floor reflection. The
mark is flat polygons under a pure 2D affine map — its construction carries **no shading
information whatsoever**, so any lighting model is foreign to it and announces itself as an
effect. "Metallic 3D without purpose" is named explicitly as outdated in the 2026 trend surveys,
and it is the default output of every free Blender logo template.

### 11.8 No stagger across the three T's.

They shear as one object, because it is one word. Three identical modules on a constant 396.5 px
pitch, staggered at a uniform interval, is the *definition* of a template — uniform spacing is
named across the animation literature as the single biggest giveaway of unrefined work. If a
future version wants separation, use *differential residual shear* (leftmost settles first,
rightmost carries the most lean), because that is how a physically sheared stack behaves.

### 11.9 The star does not arrive last with an overshoot.

That beat — everything lands, *then the accent pops* — is the most instantly legible preset in
the category. It also politely resolves the one piece of tension the composition has. See §3.3.

### 11.10 No glow, no bloom, no lens flare, no chromatic aberration.

The ink is already 3 % off the exact inverse of the ground (§6.2), which is what stops it
ringing. Bloom in Blender 5.0 is compositor-only anyway; the point is not to use it. Lens flare
is the single most instantly dated element in this category — it says 2011 and it says preset.

### 11.11 No particles, shatters, smoke, dust motes, energy trails, glitch, datamosh, RGB-split
or VHS chroma noise.

If the effect could belong to any company in any category, it is decoration, not identity. TTT
is a court-record brand with a Constructivist mark; glitch belongs to neither.

### 11.12 No fade out, and no letter-by-letter kinetic type.

One-frame cut (§2). And the wordmark resolves as one continuous object, never as animated
glyphs with per-character wiggle.

### 11.13 No 30 fps authoring, and no silent version.

See §1 and §7.

---

## 12. BLOCKER — the mark must be redrawn as vector first

`D:\Boyd Clips\boyd-brand\logo_transparent.png` cannot be used for motion as
it stands. Independently re-verified on this machine (`scratch\arch_03_shearrender.py`):

```
size: (1413, 540)  channels: 4  total px: 763020
alpha == 0 : 505090
alpha == 1 : 257930
0 < alpha < 1 (antialiased edge pixels): 0   -> 0.0000%
```

**Zero antialiased pixels.** Every edge is a hard staircase; the 9.08° stem edge advances 1 px
per ~5.5 rows. On top of that: **4,245 distinct opaque RGB values** in a three-colour mark (only
71 % of opaque pixels are the exact ink `#F2EEE3`; **1,304 distinct reds**), and a 1–2 px
near-black fringe on every edge (1.97 % of opaque pixels, 635 distinct near-black values) which
is JPEG ringing from a white background keyed out, not a designed keyline. The fringe is
visible in my own render at `renders/arch/mir_minusY.png`.

An aliased diagonal under sub-pixel motion **crawls and shimmers**. Nothing else in this spec
matters until this is fixed — the timing, easing and sound can all be perfect and the piece will
still read as amateur.

### Redraw spec

1. **Two separate objects**: `WORDMARK` (three T's) and `STAR`, independently transformable.
2. Crossbar top edges exactly **0.00°**.
3. Stem lean exactly **9.08°**, i.e. shear coefficient **0.159816**.
4. Stem width constant, **122–123 px** at the 1413 × 540 reference scale.
5. Module pitch exactly **396.5** reference units (stem centres 205.5 / 602.0 / 999.0).
6. Star **329 × 313** at reference scale, overlapping the wordmark ink by **93 px** (28.3 % of
   star width), rising 156 px above the crossbar line.
7. Exactly **two** colours: ink `#F2EEE3`, accent `#D42B2B`. **No keyline. No third value.**
8. Overall aspect locked at **2.6167 : 1**.

Deliver as SVG. Blender ships `io_curve_svg`, which is the obvious import route — **untested on
this install**, so verify it before committing to it. The fallback that *is* proven is a 4× or
8× supersampled PNG with real antialiasing, imported via
`bpy.ops.image.import_as_mesh_planes(align_axis='-Y', ...)` and sheared with a shape key
(`BLENDER-CAPABILITY.md` §1.9, §1.10, §4.8).

---

## 13. Open questions before build

* **`io_curve_svg` import quality** — untested. If it produces clean curves this becomes a FONT/
  curve pipeline and `TextCurve.shear` / object shear can be used directly.
* **Motion blur on a shape-key shear** — untested. Deformation blur was never verified in either
  engine on this install. At 1.72 px/frame it is probably unnecessary; confirm rather than assume.
* **Grain amplitude in review** — 0.0015 linear is derived from a code-ladder measurement, not
  from looking at 84 frames of it on a phone. Check it on a phone before locking.
* **The 3× over-shear multiplier** — the only value in this spec chosen by judgement rather than
  derived. Review beat B at 4× as well before locking.
* **Whether the sting should exist at all.** §0.1 and §9 both point at T3, the layout device, as
  the higher-value artifact. If the schedule forces a choice, build T3 first.
