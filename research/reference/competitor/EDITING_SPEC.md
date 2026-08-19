# Audit the Court — editing grammar, measured frame-by-frame

Forensic pass, 2026-08-12. Territory: **the cut only.** Titles and thumbnails are in
`TITLES.md` / `THUMBNAILS.md` and are not repeated here.

## 0. Corpus and method

| id | uploaded | dur | views | fps | src |
|---|---|---:|---:|---:|---|
| `yzv_uxBSgu0` | 2026-03-14 | 36:01.8 (2161.8 s) | 1,254,593 | 23.976 | 1920×1080 AV1 |
| `4kIjd7CLp7c` | 2026-03-28 | 46:42.6 (2802.6 s) | 971,961 | 29.97 | 1920×1080 |
| `Ek3Ah3NZYVo` | 2026-07-17 | 20:36.6 (1236.6 s) | 415,962 | 23.976 | 1920×1080 (Judge Boyd) |

Method: `yt-dlp` full files; `ffmpeg 8.0.1` scene detection (`select='gt(scene,thr)'` on a
384×216 downscale, full native frame rate); `-vsync 0` native-rate frame bursts for anything
timing-critical; per-frame RGB piped to numpy for caption/layout/colour metrology;
`ebur128` for loudness; normalised-cross-correlation scale search for zoom measurement.
Every number below came out of one of those. Anything I could not measure says **UNMEASURED**.

**Ek3Ah3NZYVo is the closest analogue to our client's job** — 20:37, single sentencing
hearing, Judge Boyd, two court cameras. Weight it accordingly. It is also the *newest*
video and it carries one element the two March videos do not (§3).

---

## 1. CUT RHYTHM

### 1.1 The headline: this is a SLOW-cut channel

Scene-detected hard cuts at threshold 0.30, whole video:

| video | cuts | cuts/min | median shot | p25 | p75 | p90 | longest hold |
|---|---:|---:|---:|---:|---:|---:|---:|
| `Ek3Ah3NZYVo` | 51 | 2.47 | **10.05 s** | 5.10 | 19.46 | 47.69 | **271.6 s** (split-screen, 5.9→277.5) |
| `yzv_uxBSgu0` | 83 | 2.30 | **17.37 s** | 10.54 | 36.54 | 52.39 | **104.1 s** |
| `4kIjd7CLp7c` | 24 | 0.51 | **34.90 s** | 15.92 | 97.60 | 308.53 | **702.3 s** (single locked 9th-Cir. camera) |

Shortest shots in each video are all 0.96 s — that is the logo-sting cut at 0:00.96, present
in all three. Excluding the sting, the shortest real shot measured is **1.88 s**
(`Ek3Ah3NZYVo` 5.88→... 277.53 boundary region) and **2.71 s** (`yzv_uxBSgu0`).

### 1.2 Scene cuts undercount the real intervention rate

Scene detection cannot see a layout swap that keeps the same camera, so I built a second
signal: a per-frame layout classifier at 8 fps (green-divider detection, static-background-plate
luminance signature, saturation). "Intervention" = union of {scene cut, layout-mode change,
caption on/off}, deduped at 0.6 s, measured over body only (6 s → dur−10 s):

| video | interventions | rate/min | median gap | p25 | p75 | p90 | max |
|---|---:|---:|---:|---:|---:|---:|---:|
| `Ek3Ah3NZYVo` | 95 | **4.67 /min** | **8.0 s** | 4.7 | 12.3 | 23.1 | 205.9 |
| `yzv_uxBSgu0` | 109 | **3.05 /min** | **15.1 s** | 9.1 | 23.0 | 42.7 | 100.3 |

**An uninterrupted courtroom talking-head runs a median 8 s (Ek3) / 15 s (yzv) before any
intervention.** A quarter of them run past 12 s / 23 s. Holding a shot for 20 s is normal here.
The single longest untouched stretch measured in the Boyd video is **205.9 s of one unchanged
split-screen** (`Ek3Ah3NZYVo` 71.4→277.3). That is not a mistake; it is the house style.

### 1.3 Pace across the three thirds

Layout-mode changes per minute (8 fps classifier, segments ≥0.5 s):

| video | third 1 | third 2 | third 3 |
|---|---:|---:|---:|
| `Ek3Ah3NZYVo` | 3.35 | **6.55** | 3.49 |
| `yzv_uxBSgu0` | **3.83** | 3.08 | 2.41 |
| `4kIjd7CLp7c` (scene cuts) | 0.26 | 0.58 | 0.71 |

Scene cuts per third, `yzv_uxBSgu0`: 2.91 → 2.16 → 1.83 /min; median shot 12.1 → 20.6 → 22.1 s.

**The pace does not build to a climax — in the 1.2 M-view video it decelerates monotonically.**
Front-loaded cutting, then progressively longer holds as the courtroom argument takes over.
`Ek3Ah3NZYVo` peaks in the middle third (the judge's interrogation of the deputy) and settles
again for the sentence itself.

---

## 2. PUNCH-INS / REFRAMING — **there are none**

This is the finding I most expected to be wrong, so I measured it three ways.

### 2.1 There is no animated zoom anywhere I measured

Normalised-cross-correlation scale search on a *static background* patch (wall + flag,
640×360 proxy, scale step 0.004) inside one held shot, `Ek3Ah3NZYVo`:

| pair | Δt | best-fit scale | offset | corr |
|---|---:|---:|---|---:|
| t 687.0 → 689.0 | 2.0 s | **1.0000** | (470,20) → (470,20) | 0.993 |
| t 687.0 → 692.0 | 5.0 s | **1.0040** | (470,20) → (473,20) | 0.979 |

0.4 % over 5 s is at the noise floor of the estimator. **No Ken Burns drift, no push-in,
no keyframed scale.** Frames inside a shot are pixel-locked.

### 2.2 The "zoom" is a hard cut between two fixed layouts

`Ek3Ah3NZYVo` split→full at t = 686.84 → 686.88 (frames 16466→16467) and full→split at
t = 692.22 → 692.26. Extracted at native 23.976 fps with `-vsync 0`: **1 frame. No dissolve,
no motion blur, no transition of any kind.**

### 2.3 The magnification step is exactly ×2.04, and it is a template constant

Ref-patch scale search, split-panel content vs. full-bleed content of the same camera:

| test | ratio full : panel |
|---|---:|
| `Ek3Ah3NZYVo` judge cam (panel t 686.7 vs full t 687.0) | **2.041** (fit 0.490) |
| `Ek3Ah3NZYVo` 187th-DC cam (panel t 800 vs full t 452) | **2.041** (fit 0.490) |
| `yzv_uxBSgu0` wide cam (panel t 1352.5 vs full t 1360) | ~2.09 (fit 0.955 on a partly-occluded patch — weaker) |

The panel is the source frame at **49.0–49.8 % scale**; full-bleed is the source at **100 %**.
There is no editorial crop beyond that. What reads as "punching in on the judge" is
**switching the composite off** so one camera fills 1920×1080.

### 2.4 What motivates the switch

Sampled by hand against the transcript at the mode changes in `Ek3Ah3NZYVo`
(686.9, 692.3, 793.1, 797.1, 809.8, 814.0, 817.9, 820.5):
the cut to full-bleed lands on the **judge asking a direct question** or delivering a verdict
line, and cuts back to the 2-up on the **answer** — so the viewer sees the deputy's reaction
while he speaks. The switch is on *speaker turn*, not on a specific word.
Frequency of full-bleed episodes: **47 in `Ek3Ah3NZYVo` (2.28/min), 62 in `yzv_uxBSgu0`
(1.72/min)**; median hold 6.9 s and 15.8 s respectively.

---

## 3. CAPTIONS

### 3.1 They are NOT subtitles, they are 8 highlighter moments per video — and only in the new video

Full-frame yellow-pixel scan at native rate over the bottom 288 rows of every frame:

| video | yellow-caption events | rate | on-screen total | % of runtime |
|---|---:|---:|---:|---:|
| `Ek3Ah3NZYVo` (Jul 2026) | **8** | 0.39/min | 15.7 s | **1.3 %** |
| `yzv_uxBSgu0` (Mar 2026) | **0** | — | 0 | 0 % |
| `4kIjd7CLp7c` (Mar 2026) | **0** | — | 0 | 0 % |

(The scanner's other hits were false positives I verified by eye: a brass courtroom nameplate
at `Ek3Ah3NZYVo` 55–63 s, document highlighter, and — at `4kIjd7CLp7c` 400–406 s —
the sodium/emergency lights in a stock plate, frame 12 in `editing/`.)

**So captions are a 2026-H2 addition to the format, not a load-bearing part of the two
million-view videos.** If our client is copying the 1.2 M video, he should ship *no* captions.
If he is copying current AtC, he ships about eight of them in 22 minutes.

There is no burnt-in continuous subtitle track of AtC's own anywhere in the three videos. Where
you see a monospace white line at frame bottom it is the *court's own CART feed*, part of the
source, not AtC's typography.

### 3.2 The eight captions, verbatim, with durations

`Ek3Ah3NZYVo`:

| t_on | dur | text | words | s/word |
|---:|---:|---|---:|---:|
| 636.55 | 1.13 | `You do need to be punished.` | 6 | 0.19 |
| 676.26 | 4.05 | `…Bexar County Jail` (fragment; keyword only) | 3 | 1.35 |
| 683.60 | 1.08 | `Which do you choose?` | 4 | 0.27 |
| 689.56 | 2.38 | `Why don't you want to go` → `to the Bexar County Jail?` (two sequential one-line cards) | 6 + 5 | 0.22 |
| 782.78 | 1.59 | `Why were you tasing people?` | 5 | 0.32 |
| 810.39 | 3.38 | `Why were you tasing cadets?` | 5 | 0.68 |
| 832.08 | 1.17 | `Who tased you?` | 3 | 0.39 |
| 834.42 | 0.92 | `Give me a name.` | 4 | 0.23 |

Median **0.28 s/word**; median caption duration **1.38 s**; median **5 words**.
**Max words on screen at once: 6. Always exactly one line. Never two.**
Every one of the eight is a **question or an imperative from the judge**. Not a single one is
narration, and not one is on the defendant's dialogue.

### 3.3 The transition: zero frames

Native-rate burst (`ffmpeg -ss 688.0 -t 5.2 -vsync 0`), yellow-pixel count per frame,
`Ek3Ah3NZYVo`:

```
f16530  t689.439   20 px   (noise floor: an orange handbag in shot)
f16531  t689.480   20 px
f16532  t689.522   20 px
f16533  t689.564 3541 px   <-- full text, full size, final bbox x 352..1556
f16534  t689.606 3541 px
```

Bounding box is **identical on the first visible frame and every frame after**.
**Entrance = 0 frames. No scale pop, no fade, no wipe, no colour swap, no per-word
progression, no karaoke highlight.** Exit is the same: one frame on, one frame off
(verified at 691.97 and at the 692.26 layout cut). See
`editing/04_…_caption-entrance-5-consecutive-frames.png`.

There is no second colour. No word is ever highlighted differently from the rest.

### 3.4 Typography (measured at 1920×1080, `Ek3Ah3NZYVo` t = 690.0)

| property | measurement |
|---|---|
| Fill | **`#FBF601`** (median of 2-px-eroded glyph interiors, n = 48,575 px) |
| Stroke | **`#010000` → pure black `#000000`**, codec-lifted (n = 50,628 ring px) |
| Stroke width | **median 7 px, mean 10.3** at 1080p (run-length scan across the densest row). Thick enough that it merges between adjacent letters and reads as a slab |
| Background box | **none** — the black mass is the stroke, and it follows the ascender of `t` |
| Drop shadow / glow | **none detected** beyond the stroke ring |
| Cap height | **94–95 px = 0.0870 H**, consistent to ±1 px across all 8 events |
| x-height | 68 px → x/cap **0.716** |
| Descender | 26 px → desc/cap **0.274** |
| Line height (cap-top→desc-bottom) | 121 px = 0.112 H |
| Case | **Sentence case, not all-caps** |
| Baseline | **y = 1025.5 → 0.9495 H** (range 0.9491–0.9500 across 8 events) |
| Cap top | y = 931 → 0.8620 H |
| Horizontal | **centred, cx = 0.4975 ± 0.005 W** |
| Movement | **none** — position is frame-fixed, identical whether the shot is full-bleed or a letterboxed composite |
| Line width | 1202 px (0.626 W) for 6 words; longest measured 1471 px (0.766 W) |
| Letter spacing | 6–9 px between glyphs (≈0.06–0.09 em) — tight |
| Word spacing | 24–29 px |

Per-glyph advance widths, normalised to cap height = 1.00
(`W .81  w .81  o .57  a .57  n .57  u .58  h .58  d .57  y .57  g .58  t .37  x .72(x-ht)`).

**Family: UNIDENTIFIED.** I metric-matched against 22 downloaded faces. Best fits by mean
absolute error over 13 measured ratios:

| candidate | mean err | note |
|---|---:|---|
| Barlow Condensed ExtraBold | **4.0 %** | 11 of 13 ratios within 3 %; only `W` (0.96 vs 0.81) and `w` (0.86 vs 0.81) off |
| Roboto Condensed Bold (700) | 4.6 % | same pattern |
| Asap Condensed Bold | 5.0 % | |
| Anton | 14.5 % | x-height and descender wrong |
| Montserrat ExtraBold | 50.8 % | far too wide — **not this** |

So: a **condensed neo-grotesque at ExtraBold/Black weight**, Barlow-Condensed / Roboto-Condensed
class, with a narrower-than-standard `W`. Shape evidence from a 4× pixel crop
(`editing/03_…CAPTION-2x-typography-crop.png`): double-storey `a`, single-storey `g` with a
short flat-terminal tail, straight flat-cut `y` descender, angled top cut on `t`, `W` with the
middle apex at full cap height, superelliptical `o` with very small counters, wedge apostrophe.
Do not ship Montserrat and call it a match.

**To reproduce at 1080p:** cap height 94 px, sentence case, fill `#FBF601`, black stroke 7 px,
tracking ≈ −2 %, single line, centred, baseline y = 1025.

---

## 4. B-ROLL AND STOCK

### 4.1 Inventory — what the clips actually are

`Ek3Ah3NZYVo` (7 inserts): drone/aerial city skyline at dusk (under the date card) · brass
**scales of justice** on black, shallow DOF · **Lady Justice bronze statue**, warm, backlit
window · **county sheriff's office & detention centre exterior**, real building, handheld ·
**Texas state flag** waving, slow-motion · **prison bars with hands in an orange jumpsuit** ·
**handcuffs lying on printed legal paper**, top-down, shallow DOF.

`yzv_uxBSgu0`: the **same Lady Justice statue asset** reappears (t ≈ 480).

`4kIjd7CLp7c`: **night emergency scene** — ambulance/patrol light bars, high-vis vests,
wet asphalt, heavy bokeh (t ≈ 400–406). See `editing/12_…`.

**Not present in any of the three: a gavel. No generic-hands-typing, no stock-footage
courtroom, no news-anchor plates.** The B-roll vocabulary is *justice iconography +
the actual buildings of the actual case*.

### 4.2 Duration and rate

Fine scene detection (thr 0.06→0.10) over the opening 90 s and closing 70 s of `Ek3Ah3NZYVo`:

| insert | in | out | dur |
|---|---:|---:|---:|
| aerial city (under date card) | 5.88 | 10.64 | **4.76 s** |
| Lady Justice | 39.21 | 45.38 | **6.17 s** |
| scales of justice | ≤1176 | 1183.56 | ≥7.5 s |
| detention-centre exterior | 1187.60 | 1192.52 | **4.92 s** |
| Texas flag (statute card over it) | 1203.87 | 1205.79 | **1.92 s** |
| prison bars | 1219.89 | ~1223.9 | **~4.0 s** |
| handcuffs on documents | ~1223.9 | 1227.81 | **~3.9 s** |

**Mean stock insert 4.4 s (n = 5 with both boundaries measured); range 1.9–6.2 s.
7 per 20:37 = 0.34/min.** They cluster: **2 in the opening 45 s, 5 in the closing 60 s.**
The middle 18 minutes of the Boyd video contains **zero** stock.

### 4.3 How they are cut in

Hard cuts. Every stock in/out boundary above was resolved at native rate and is
**1 frame**. **No dissolves, no motion transitions, no whip pans, no light leaks.**

### 4.4 Grading — they are NOT matched

`grade.py` (Rec.709 luma percentiles, HSV-style saturation percent, per-channel deviation
from frame mean):

| frame | p1 Y | median Y | median sat % | R/G/B deviation |
|---|---:|---:|---:|---|
| courtroom, full-bleed (t 690.0) | **0.2** | 108.2 | **25.3** | R+13.8 G−5.6 B−8.1 |
| stock: scales (t 1178.5) | 12.0 | 25.0 | 20.7 | R+7.5 G−0.7 B−6.7 |
| stock: detention centre (t 1191.0) | 4.4 | 101.3 | 24.0 | R+12.9 G−0.9 B−12.1 |
| stock: prison bars (t 1217.5) | 9.4 | 35.9 | 20.3 | R+3.0 G−1.5 B−1.6 |
| stock: handcuffs (t 1223.5) | **0.0** | 125.4 | 18.2 | R+8.5 G+1.0 B−9.5 |
| stock: Lady Justice (t 43.0) | **45.8** | 188.5 | **36.2** | **R+29.1 G+5.9 B−34.9** |

**Black point ranges 0.0 → 45.8 across five stock plates while the courtroom sits at 0.2.**
Saturation runs 18.2 → 36.2 vs the courtroom's 25.3. The Lady Justice plate is +25 % more
saturated and 4.4× brighter in the shadows than the footage it sits next to. **There is no
matching grade.** The stock is dropped in as licensed. The only thing that makes it cohere is
that the library clips they pick are all warm (every one has R > B, deviation +3 to +29).

### 4.5 Overlay behaviour

Stock **fully replaces** the frame — full-bleed 1920×1080, no picture-in-picture, no split
with live footage. Two exceptions, both graphic-over-stock:
the date card sits over the aerial plate (`Ek3Ah3NZYVo` 5.88–10.64) and a statute card sits over
the waving Texas flag (1203.87–1205.79).

---

## 5. GRAPHICS

### 5.1 The frame template — this is the single biggest structural device

Two states, hard-cut between them (§2). Measured on `Ek3Ah3NZYVo` t = 800.0 and
`yzv_uxBSgu0` t = 1352.5:

| element | `Ek3Ah3NZYVo` | `yzv_uxBSgu0` |
|---|---|---|
| Background plate | static photo: dark walnut courtroom panelling, US flag upper-right, court seal — **sharp, not blurred**, never moves | same asset family |
| Band top edge | y = **272** (0.2519 H) | y = **305** (0.2824 H) |
| Band bottom edge | y = **805** (0.7454 H) | y = **773** (0.7157 H) |
| Band height | **534 px = 0.4944 H** | **469 px = 0.4343 H** |
| Band width | full 1920 | full 1920 |
| Band vertical centre | 538.5 (frame centre 540) — **centred** | 539 — centred |
| Panel size | 956 × 534 (≈16:9, whole source frame at 0.498×) | 960 × 469 (2.05:1 — a **centre crop** of the source, then 0.50×) |
| Divider x | cols **959–963** | cols **954–959** |
| Divider width | **5 px** | **6 px** |
| Divider centre | 961 → **0.5005 W** | 956.5 → **0.4982 W** |
| Divider height | full band, 272–805 | full band, 306–771 |
| Divider colour | p99 `#84E82E`; peak px `#90F632` | p90 `#8DE939` |

Divider is a **lime green ≈ `#8CE93A`**, 5–6 px, dead centre, full band height, hard edges,
no glow. It is the only saturated non-content colour in the whole layout.

Split-screen occupancy: **53.5 % of `Ek3Ah3NZYVo`, 39.9 % of `yzv_uxBSgu0`.**

### 5.2 Speaker name plate

Bottom-left of **each panel**, baked in before the panel is scaled (so it halves in the split).

| property | full-bleed (t 690.0) | split panel (t 800.0) |
|---|---|---|
| Text | `Judge Boyd` / `187th DC` | same |
| Colour | white `#FFFFFF` | white |
| Cap height | 36 px | 18 px |
| **Cap height / panel height** | **0.0333** | **0.0337** — identical fraction |
| Baseline | y 1049 → **0.971** of panel height | y 787.5 → 0.966 |
| Left inset | x = 2 px (**flush left**, ≈0.001 W) | x = 7 px |
| Backing | soft dark scrim behind the text, extending ~6 px past the glyphs, hard top edge, no rounding. **Alpha UNMEASURED** (no clean uniform backdrop available) |
| Typeface | humanist sans, single-storey `g` with an open tail, straight `y` — **family UNIDENTIFIED**, clearly *not* the caption face |
| Animation | **none.** On for the whole shot, off with the cut |

### 5.3 Document / record cards

The workhorse graphic. `Ek3Ah3NZYVo` spends **104.8 s = 8.5 %** of runtime on them
(10 segments, median 9.1 s, p25 6.4, p75 12.7, max 23.6). `yzv_uxBSgu0`: 52.6 s = 2.4 %
(7 segments, median 7.9 s).

Recipe (measured on `Ek3Ah3NZYVo` t = 300.0, `editing/05_…`):

| property | measurement |
|---|---|
| Card bbox | x **0.131 → 0.876 W**, y **0.130 → 0.999 H** (bleeds off the bottom) |
| Rotation | **+4.81°** clockwise (least-squares fit of the top edge, slope 0.0842) |
| Background | a **blurred, enlarged copy of the same document**, desaturated cool grey — never a solid colour, never the courtroom |
| Shadow | soft drop shadow under the card |
| Highlighter | drawn as a **marker stroke**, ragged ends, over the running text — not a rectangle |
| Highlighter colours | **yellow `#FDC501`** on court records / news copy; **blue `#77ABF8`** on statutes |
| Motion | the card drifts slowly (8 fps inter-frame diff 1.3–1.9 vs 0.1–0.3 for a static plate) — **direction and rate UNMEASURED**; correlation fits were too low to trust because the visible text scrolls |
| Entrance / exit | **hard cut, 1 frame** — verified at 1197.82, 1203.87, 1205.79, 1209.75 |

Card sources actually used, in order, `Ek3Ah3NZYVo`: local-news article (KSAT.com, logo left
in) → TV-station charge card (`NEWS4SA`, mugshot in a red border) → county arrest record →
county case-information record → Cornell LII definition page → district-court dispositions
record → Texas State Law Library guide → NICCC website → Texas Penal Code section.
**Every card is a real, citable document with its source branding visible.**

### 5.4 Date cards

`Ek3Ah3NZYVo` t = 57.0 (`editing/08_…`): white text over a live/stock plate.

| property | measurement |
|---|---|
| Text bbox | x 482 → 1426 (**width 0.492 W**), centre x = 954 → **0.497 W** |
| Cap top / baseline | y 486 / **y 599** |
| Cap height | **113 px = 0.1046 H** — i.e. **1.20× the caption cap height** |
| Vertical centre | 0.502 H — **dead centre of frame** |
| Colour | white `#FFFFFF` with a soft dark shadow |
| Case | Sentence case (`March 7th, 2024`, `Jan 18th, 2023`) |
| Animation | **UNMEASURED** for the text; the badge graphic beneath it does scale/settle over ~2 s |

### 5.5 Black-and-white mode

**`Ek3Ah3NZYVo` 111.9 s = 9.0 %; `yzv_uxBSgu0` 135.6 s = 6.3 %.**
Measured at t = 1186.5: median saturation **0.0 %**, per-channel deviation **R±0.0 G±0.0 B±0.0**.
It is a **true monochrome**, not a partial desaturation, and it is applied to the **entire
composite output** — the wood background plate and the green divider go grey with the footage.
Used under narrated explainer passages while the hearing continues silently underneath.

### 5.6 Arrows, circles, callouts

**Zero.** None in any of the three videos. (Contrast the thumbnails, which use a red arrow
`#FD0101` in 9 of 12 — it never appears inside the video.)

---

## 6. AUDIO

| video | integrated | LRA | true peak | LRA low / high |
|---|---:|---:|---:|---|
| `yzv_uxBSgu0` | **−16.7 LUFS** | 6.4 LU | −0.1 dBTP | −20.6 / −14.2 |
| `4kIjd7CLp7c` | **−14.0 LUFS** | 4.7 LU | **+0.2 dBTP** | −16.8 / −12.0 |
| `Ek3Ah3NZYVo` | **−15.8 LUFS** | **2.8 LU** | −0.0 dBTP | −17.6 / −14.8 |

Loud, flat, and clipping the ceiling. LRA 2.8–6.4 LU means aggressive levelling —
courtroom mics and narration are pulled to the same place.

### 6.1 There is no music bed

50 ms RMS over the whole file:

| video | % of file below −40 dBFS | below −60 | below −80 |
|---|---:|---:|---:|
| `yzv_uxBSgu0` | 19.5 % | 11.95 % | **7.22 %** |
| `Ek3Ah3NZYVo` | 12.8 % | 0.028 % | 0.004 % |

7.2 % of the 1.2 M-view video is **digital silence**. A music bed makes that impossible.
`Ek3Ah3NZYVo` never goes below −60 only because the courtroom room-tone floor sits at ≈−46 dBFS.
**Music exists only in the 6-second opening sting. Nothing under the body, nothing under B-roll,
nothing under the outro.** Consequently there is no ducking to measure — **N/A, not
UNMEASURED**.

### 6.2 The sting, sample-identical across videos

50 ms RMS, `Ek3Ah3NZYVo` and `yzv_uxBSgu0` return the *same* values frame for frame:

```
t 0.00  −103 dBFS  (digital silence)
t 0.05  −23 → builds
t 1.05  −2 dBFS    PEAK, coincident with the light-burst at f023 = 0.959 s
t 1.8–5.35        sustained bed at −15 to −17 dBFS
t 5.35 → 6.00     fade-out: −19 −21 −24 −26 −28 −31 −34 −38 −40 −44 −51 −61 −76
t 6.00            hard cut to silence; narration starts t 6.03
```

**13-frame (650 ms) fade, ≈ −4.5 dB per 50 ms, hard-terminated at exactly 6.00 s.**

### 6.3 Sound design on graphics

**None.** RMS windows ±1 s around the caption on at 689.56, the doc-card cuts at 304.5, and
the layout cuts at 277.5 / 797.1 show only speech-pause dips (−15 → −50 dBFS during
silence). **No whooshes, no impacts, no risers, no sub drops anywhere.**

---

## 7. STRUCTURE

### 7.1 Cold open? No.

**The sting is at 0:00.00. Zero seconds of content precede it.** No hook, no cold open,
no "wait for it".

| beat | `Ek3Ah3NZYVo` |
|---|---|
| 0.00–0.96 | 3D metallic `AUDIT THE COURT` logo assembles under a light sweep, on the wood + flag plate |
| 0.96 | logo locked (scene cut, score 0.61) |
| ~2.6 | music enters |
| ~3.0–5.9 | small DISCLAIMER paragraph fades up bottom-left |
| 5.88–6.01 | **white flash out** (peak at f144 = 6.006 s) |
| 6.00 | audio hard cut; **narration starts at 6.03** |

Same 0.96 / 5.88 cut pair in all three videos → **the sting is a fixed 6.00 s asset.**

### 7.2 Narrated setup before the first courtroom frame

`Ek3Ah3NZYVo`, boundaries from fine scene detection:

```
5.88   date card "Jan 18th, 2023" over aerial city + county badge   4.76 s
10.64  press photo, deputy receiving a commendation                 5.92 s
16.56  KSAT.com news article, yellow highlighter                    ~7.8 s
~24.4  NEWS4SA charge card, mugshot in red border                   ~6 s
30.36  county arrest record, yellow highlighter                     8.85 s
39.21  Lady Justice stock                                           6.17 s
45.38  Cornell LII "plea bargain" page                              4.13 s
49.51  187th District Court dispositions record                     5.71 s
55.22  date card "March 7th, 2024" over the bench nameplate         ~2.5 s
57.7   court footage begins (rack focus on the judge's desk plate)
62.98  first split-screen composite
```

**Narrated card-stack = 6.0 → ~57.7 s ≈ 51.7 s (4.2 % of runtime) with 9 graphics/stock beats
in it — a beat every 5.7 s — before one frame of the hearing is shown.**
`yzv_uxBSgu0` runs the same structure over its first ~75 s.

### 7.3 Do they narrate over the footage?

Yes. The B&W mode (§5.5) is the marker: **9.0 % / 6.3 % of runtime** is the hearing playing
in monochrome under a voice-over explainer, and the hearing's own audio drops out under it.
Outside those passages the courtroom runs unnarrated at full audio.

### 7.4 Ending

`Ek3Ah3NZYVo`, exact cut times:

```
~1176–1183.56  scales-of-justice stock (voice-over conclusion)
1183.56–1187.60  B&W split composite         4.04 s
1187.60–1192.52  detention-centre exterior   4.92 s
1192.52–1197.82  full-bleed defendant        5.30 s
1197.82–1203.87  Texas State Law Library page 6.05 s
1203.87–1205.79  statute card over Texas flag 1.92 s
1205.79–1209.75  NICCC website card          3.96 s
1209.75–1219.89  B&W split composite        10.14 s
1219.89–1227.81  prison bars → handcuffs     7.92 s
1227.81–1236.63  AUDIT THE COURT logo card   8.82 s   <- END
```

**The last 60 s is a second card-stack — the "what happens to him now" coda — built from the
same vocabulary as the opening.** Then a **static logo endcard held 8.8 s** on the wood + flag
plate. No subscribe animation, no end-screen video tiles, no talking head, no spoken CTA
detected in the final 9 s (audio present is the tail of the voice-over, which stops before the
card). Video ends on the hard stop.

---

## 8. IMPLEMENTATION CHECKLIST FOR A 22-MINUTE CUT

1. **Build the composite template first**, not the timeline. Static courtroom-panelling plate;
   band 1920 × 534 centred at y 272–805; two panels at 49.8 % source scale; **5 px `#8CE93A`
   divider at x 959–963**; white speaker plate at 3.35 % of panel height, flush bottom-left.
2. **Cut at 3–4.7 interventions/min, median gap 8–15 s.** If you are cutting faster than
   2.5 hard cuts a minute you are not making this show.
3. **Never animate a zoom.** Toggle composite ↔ full-bleed on speaker turns, 1-frame cut,
   ×2.04 apparent magnification, no easing.
4. **Nine graphics beats in the first 52 s** before any hearing footage, and a matching
   9-beat coda in the last 60 s.
5. **Document cards, not lower thirds.** Real records, source branding left visible, rotated
   ≈5°, over a blurred copy of themselves, marker highlighter `#FDC501` / `#77ABF8`, held 6–13 s.
6. **True monochrome for narrated passages**, ~6–9 % of runtime, applied to the whole comp.
7. **No music under anything but the 6.00 s sting.** Master to −14 to −16.7 LUFS with
   LRA 3–6 LU.
8. **Captions are optional and rare.** If used: 8 per 20 min, one line, ≤6 words, sentence
   case, `#FBF601` on a 7 px black stroke, cap height 0.087 H, baseline 0.9495 H, centred,
   **zero-frame in and out**, and only on the judge's questions.
9. **Zero arrows, zero circles, zero whooshes, zero dissolves.** Every transition in 100
   minutes of measured footage is a hard cut.
10. **Static logo endcard, ~9 s, hard stop.**

---

## 9. Frames

All in `research/reference/competitor/editing/`:

```
01_Ek3Ah3NZYVo_t0800.0_split-composite-template-green-divider.png
02_Ek3Ah3NZYVo_t0690.0_fullbleed-yellow-caption-nameplate.png
03_Ek3Ah3NZYVo_t0690.0_CAPTION-2x-typography-crop.png
04_Ek3Ah3NZYVo_t0689.52-689.69_caption-entrance-5-consecutive-frames.png
05_Ek3Ah3NZYVo_t0300.0_doccard-tilt4.8deg-blue-highlighter.png
06_Ek3Ah3NZYVo_t0018.0_newscard-yellow-highlighter-KSAT.png
07_Ek3Ah3NZYVo_t0026.0_chargecard-mugshot-red-border.png
08_Ek3Ah3NZYVo_t0057.0_datecard-centered.png
09_Ek3Ah3NZYVo_t1186.5_BW-mode-saturation-zero.png
10_Ek3Ah3NZYVo_t1223.5_stock-handcuffs-on-documents.png
11_Ek3Ah3NZYVo_t1232.0_endcard-logo-hold.png
12_4kIjd7CLp7c_t0405.0_stock-police-lights-night-bokeh.png
13_yzv_uxBSgu0_t1352.5_split-composite-2to1-panels-no-caption.png
```

## 10. Open / unmeasured

- Caption **font family** — narrowed to a Barlow-Condensed/Roboto-Condensed-class condensed
  grotesque at ExtraBold/Black; exact face not identified. Full metric fingerprint is in §3.4
  so a designer can match it by eye against the 4× crop.
- Speaker-plate **scrim alpha** and its **font family**.
- Document-card **drift direction and rate** (motion confirmed, parameters not fitted).
- Date-card **entrance animation**.
- `4kIjd7CLp7c` was analysed for cuts, loudness, captions and stock only; its layout classifier
  was not run (30 fps source, different plate).
- n = 3 videos. The caption finding in particular rests on **one** video containing them.
