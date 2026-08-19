# @courtroomtime THUMBNAIL BUILD SPEC

Measured 2026-08-18. Everything below is a number produced by
`_catalog.py -> _fetch.py -> _measure.py -> _measure2.py -> _stats.py -> _consts.py -> _ours.py`
in this directory. Raw per-image data: `measurements.json` (25 refs), `ours.json` (17 ours).
Contact sheets used for the visual census: `sheet_top.jpg`, `sheet_bot.jpg`; census in `_census.json`.

## 0. Sample and controls

| | n | views (median) | playlist idx (mean, 0 = newest of 500) | duration (median) |
|---|---|---|---|---|
| WINNERS (top by views) | 15 | 308,000 | 332 | 3,545 s |
| LOSERS (bottom by views) | 10 | 1,100 | 338 | 1,279 s |
| OURS (`BANGERS/*.jpg`) | 17 | - | - | - |

- Catalogue: 500 videos. Winners span 204k-891k views, losers 388-1,700.
- **Age is controlled.** Mean playlist index 332 vs 338 out of 500 -> the two groups are the
  same vintage. This is not a "losers are new uploads" artifact.
- **Duration is NOT controlled and is the strongest variable in the whole study**
  (d = 1.52, AUC = 0.84, p = 0.005). Winners are ~59-minute "Top N" compilations; losers are
  ~21-minute single cases. Every thumbnail effect below is confounded with that. Treat the
  thumbnail as a secondary lever.
- All 25 references fetched at `maxresdefault`; **all 25 are exactly 1280x720**.
- Multiple-comparison honesty: 36 continuous + 15 binary tests were run at n=25.
  Only `duration` survives Bonferroni. Everything else is directional evidence, not proof.

## 1. Canvas

```
W, H = 1280, 720          # 25/25 references, no exceptions
```

## 2. Layout: two-panel, off-centre seam

- **2-panel split (judge on one side, antagonist on the other): 15/15 winners, 8/10 losers**
  (p = 0.150 — the 2 single-frame losers are suggestive but not significant at this n).
- Seam x position, winners (n=15): percentiles [10,25,50,75,90] = **0.229, 0.350, 0.459, 0.541, 0.643**.
  The distribution is **bimodal**, not centred: judge-left builds land near **x = 0.35**,
  judge-right builds near **x = 0.64**.
- Winners split off-centre; losers centre the seam.
  `|seam - 0.5|` median **0.141 (winners) vs 0.028 (losers)**, d = 0.40, AUC = 0.68, p = 0.141.
  Only 47% of winner seams fall in 0.40-0.60, vs 70% of loser seams.
- Seam runs most of the frame height: `seam_rowfrac` median **0.769** (winners) vs 0.692 (losers).
- The two panels are graded differently: mean |left-right| saturation gap
  **0.111 (winners) vs 0.077 (losers)**.

```
SEAM_X       = 0.35   if judge_on_left else 0.64    # NOT 0.50
SEAM_FULL_H  = 0.77                                  # seam visible over >=77% of H
PANEL_SAT_DELTA = 0.11                               # grade the two panels apart
```

Divider treatment is a **ragged / torn-paper white edge**, not a clean rule.
Census: torn edge 10/15 winners vs 6/10 losers — **noise**, use it for style, not for lift.

## 3. Subject and faces

Haar (frontalface_default + alt2 + profile, NMS'd), winners n=15:

```
HERO_FACE_H_FRAC   = 0.354     # median; IQR 0.288 - 0.452
HERO_FACE_CY       = 0.362     # median
HERO_FACE_CX       = 0.20  or  0.75            # bimodal, follows the panel it sits in
SECOND_FACE_H_FRAC = 0.263     # the antagonist
SECOND_FACE_CX     = 0.572
FACE_RATIO         = 1.35      # hero : antagonist face height
```

- Hero face height: **0.354 (winners) vs 0.301 (losers)**, d = 0.72, p = 0.34 — directional only.
- Median face height across *all* detected faces: 0.228 (winners) vs 0.204 (losers);
  p90 0.425 vs 0.307.
- Face count is **noise**: median 3 in both groups (p = 0.530).
- **Judge Boyd specifically is the cutout in 15/15 winners vs 6/10 losers** (p = 0.017).
  The 4 losers that miss are: 2 with no judge cutout at all, 1 Judge Fleischer, 1 unnamed judge.
  Grayscale template matching could NOT separate the groups (`boyd_match` 0.461 vs 0.453,
  AUC 0.55) — the signal is "a recognisable recurring judge is present", not pixel identity.

## 4. Text: two tiers, and keep the top 24% of the frame clear

**100% of all 25 references carry text** (15/15 and 10/10) — having text is table stakes, not an edge.

### 4.1 Two-tier cap heights

Winners run a large display line and a small banner line at a **3.85 : 1** ratio:

```
DISPLAY_CAP_FRAC = 0.179    # p95 glyph height / H, median over 15 winners
BANNER_CAP_FRAC  = 0.0465   # median glyph height / H, same 15
CAP_TIER_RATIO   = 3.85     # winners; losers run a flatter 3.07
```

- `cap_frac_max`: **0.179 (winners) vs 0.159 (losers)**, d = 0.56, AUC = 0.71, p = 0.091.
- `cap_frac_mainrow` (0.078 vs 0.083) and `cap_frac_med` (0.047 vs 0.052) are **noise**
  (p = 0.868 / 0.718). Only the *display* tier separates the groups.

### 4.2 Vertical placement — the cleanest text finding

Fraction of all detected text rows sitting above y = 0.20:

| | winners | losers | ours |
|---|---|---|---|
| rows above y=0.20 | **6.5%** | 25.8% | 25.0% |
| row cy p10 | **0.236** | 0.067 | 0.104 |
| row cy p25 | 0.316 | 0.187 | 0.219 |
| row cy p50 | 0.628 | 0.471 | 0.581 |
| row cy p90 | 0.901 | 0.894 | 0.966 |

Winners essentially never put a text row in the top quarter. Losers (and we) do.

```
TEXT_MIN_CY   = 0.24     # winners' 10th-percentile row centre = 0.236
DISPLAY_CY    = 0.30     # display line centre, winners' 25th pct = 0.316
BANNER_CY     = 0.90     # winners' 90th pct row centre = 0.901
TEXT_BOT_MAX  = 0.99     # median text bottom = 0.988
```

### 4.3 Bottom lockup (solid bars)

Every solid yellow and red bar detected in the 15 winners sits in the bottom third
(19 yellow bars, 5 red bars, **100%** with top_y > 0.66):

```
BAR_TOP_Y_YELLOW = 0.872   # median of 19 measured yellow bars
BAR_TOP_Y_RED    = 0.844   # median of 5 measured red bars
BAR_TOTAL_H_FRAC = 0.130   # sum of flat-bar row height / H, winners mean
```

- Total bar height: 0.130 (winners) vs 0.159 (losers), d = -0.49, p = 0.390 — **noise**.
  Presence of a bottom yellow plate: 10/15 vs 7/10 (p = 1.000) — **noise**.
  Red tag plate: 6/15 vs 4/10 (p = 1.000) — **noise**.
  Build the lockup because it is house style, not because it wins.

### 4.4 Text volume and colour

```
TEXT_INK_FRAC = 0.157      # glyph pixels / frame, winners median (mean 0.166)
```

- **`text_ink_frac` 0.157 vs 0.139 (means 0.166 vs 0.129), d = 1.03, AUC = 0.75, p = 0.043.**
  Winners carry *more* bright text ink, not less.
- Row count is **noise**: 3.0 vs 3.5 rows (p = 0.773); 3.07 vs 3.10 rows per image.
- Number of distinct text colours is **noise**: median 3 in both (p = 0.457).
- Glyph-ink colour share is **noise between the groups** — do not read a rule into it:

| | yellow | white | red | green |
|---|---|---|---|---|
| winners | 0.146 | 0.406 | **0.427** | 0.021 |
| losers | 0.190 | 0.368 | 0.419 | 0.023 |
| **ours** | 0.263 | **0.589** | **0.143** | 0.005 |

  Red carries ~43% of channel glyph ink in *both* reference groups; we are at 14%.

### 4.5 Type treatment

All caps in 25/25. Heavy condensed grotesque, black outline plus a black glow on every
glyph. Sentence case appears nowhere in the sample.

## 5. Colour grade

Winners (n=15) vs losers (n=10), whole-frame HSV/gray:

```
SAT_MEAN      = 0.546      # winners median (mean 0.499)
VAL_MEAN      = 0.516      # winners median (mean 0.512)
CONTRAST_STD  = 0.297      # gray std / 255
CLIP_HI       = 0.076      # fraction of pixels at V >= 250
CLIP_LO       = 0.088      # fraction at V <= 8
FLAT_FRAC     = 0.0009     # almost no flat regions outside the text bars
```

- Brightness separates: `val_mean` **0.516 vs 0.483**, d = 0.82, p = 0.081.
- Saturation separates in the **opposite** direction to intuition:
  **0.546 (winners) vs 0.575 (losers)**, d = -0.71, p = 0.056. Losers over-saturate.
  Target 0.55, do not push past it.
- `contrast_std` (0.297 vs 0.293, p = 0.890), `clip_hi` (0.076 vs 0.080, p = 0.978) and
  `clip_lo` (0.088 vs 0.069, p = 0.846) are **noise** — no rule available from this data.

## 6. Overlay props

| motif | winners | losers | Fisher p | verdict |
|---|---|---|---|---|
| **yellow arrow** | **0/15** | **5/10** | **0.005** | strongest binary: never ship a yellow arrow |
| any arrow | 8/15 | 9/10 | 0.088 | losers lean on arrows more |
| red / magenta arrow | 8/15 | 4/10 | 0.688 | noise |
| rotated stamp badge (SHOCKING / EXPOSED) | 5/15 | 3/10 | 1.000 | noise |
| handcuffs prop | 5/15 | 2/10 | 0.659 | noise |
| judge on the left | 10/15 | 5/10 | 0.442 | noise |
| torn divider | 10/15 | 6/10 | 1.000 | noise |
| bottom yellow plate | 10/15 | 7/10 | 1.000 | noise |
| red name plate | 6/15 | 4/10 | 1.000 | noise |
| any text | 15/15 | 10/10 | 1.000 | noise |

Also non-separating: `n_circles` (1 vs 2, p = 0.571), `graphic_area_frac` (0.150 vs 0.165,
p = 0.718), `border_vs_center` (41.5 vs 54.2, p = 0.760). **No reference in the sample uses a
frame border.**

## 7. Exact colours

Median of per-image median RGB over the pixels matching each key, winners:

```
YELLOW = "#EBDD06"   # n = 15 images, per-image sd +/- (6.9, 15.4, 15.8)
RED    = "#F41212"   # n = 14 images, per-image sd +/- (42.8, 12.4, 13.5)
WHITE  = "#FCF9F8"   # n = 15 images, per-image sd +/- (4.2, 3.5, 3.8)
BLACK  = "#000000"   # outline + glow on every glyph, 25/25
```

Losers land at `#F0E806` / `#D6150E` / `#FCFCFA` — the palette itself is **noise**.
Our current `YELLOW = #FEFB03` is ~19 units brighter and greener than the measured `#EBDD06`;
this is within their per-image spread and is **not** a defect worth fixing.

## 8. Where our output sits (BANGERS n=17 vs winners n=15)

Same code path, same metrics. `d` is ours minus winners, pooled SD.

| metric | winners | LOSERS | ours | d (ours-win) | read |
|---|---|---|---|---|---|
| `text_ink_frac` | 0.166 | 0.129 | **0.095** | **-2.38** | far too little text ink |
| `sat_mean` | 0.499 | 0.558 | **0.343** | **-2.14** | badly undersaturated, below both groups |
| `bar_height_frac` | 0.130 | 0.159 | **0.040** | **-1.89** | almost no solid banner bars |
| `cap_frac_max` | 0.184 | 0.159 | **0.133** | **-1.84** | no display tier |
| `face_max_hfrac` | 0.382 | 0.301 | **0.498** | **+1.33** | hero face 30% too large |
| `clip_hi` | 0.093 | 0.095 | **0.145** | **+1.03** | blowing highlights ~1.6x |
| rows above y=0.20 | 6.5% | 25.8% | **25.0%** | - | we match the LOSERS exactly |
| `flat_frac` | 0.0009 | 0.0024 | **0.036** | - | 40x their flat-plate area |
| red glyph share | 0.427 | 0.419 | **0.143** | - | we under-use red 3x |
| `\|seam-0.5\|` | 0.141 | 0.028 | 0.219 | - | ok, already off-centre |
| `cap_frac_mainrow` | 0.078 | 0.083 | 0.064 | - | our `CAP_FRAC=0.0773` matches their banner tier |
| `val_mean` | 0.512 | 0.481 | 0.539 | - | fine |
| `contrast_std` | 0.295 | 0.299 | 0.305 | - | fine |

Current constants in `scripts/make_thumbnail_v2.py`:
`CAP_FRAC=0.0773`, `TEXT_TOP_FRAC=0.045`, `SUBJECT_W=0.38`, `SUBJECT_CX=0.78`, `YELLOW=#FEFB03`.

## 9. Change list (ranked by measured gap)

1. **Saturate.** `sat_mean` 0.343 -> target **0.546** (d = -2.14). Apply an HSV S multiplier of
   ~1.6 with a soft knee. Ceiling at 0.55: losers sit at 0.575 and lose.
   Simultaneously pull `clip_hi` 0.145 -> 0.076 (highlight rolloff before the S boost).
2. **Add a display text tier.** Keep `CAP_FRAC = 0.0773` for the bottom banner (it already
   matches their 0.078 main-row tier) and add
   `DISPLAY_CAP_FRAC = 0.179` for line 1 — a 3.85:1 two-tier lockup.
   This is what closes both `cap_frac_max` (d = -1.84) and `text_ink_frac` (d = -2.38).
3. **Move text out of the top band.** `TEXT_TOP_FRAC = 0.045` puts our display line at
   cy ~0.084, which is the loser signature. Set `TEXT_MIN_CY = 0.24` (winners' p10 = 0.236),
   display line centre 0.30, banner lockup at 0.87-0.99.
4. **Shrink the hero and add the antagonist.** Our hero face is 0.498 H vs their 0.354 H
   (d = +1.33). Scale the subject by ~0.71 and add a second cutout at face height 0.263 H,
   cx 0.572 — a 1.35:1 hero:antagonist pair with the seam at 0.35 or 0.64, never 0.50.
5. **Shift the accent palette to red and ban yellow arrows.** Red is 42.7% of winner glyph
   ink and 14.3% of ours. Add the red name plate (`#F41212`) under the display line and
   render arrows in `#F41212`. Yellow arrows appear in **0/15 winners and 5/10 losers**
   (p = 0.005) — this is the single strongest binary in the study.

## 10. Explicitly not actionable

The data does **not** separate winners from losers on any of the following. Do not invent a
rule for them: presence of text, number of text rows, number of text colours, glyph colour
share, bottom yellow plate, red name plate, rotated stamp badges, handcuff props, torn
divider, which side the judge sits on, face count, contrast, highlight/shadow clipping,
circle count, graphic area, border treatment, or the exact yellow/red/white hex values.

The largest real difference between these two groups is that winners are 59-minute
compilations and losers are 21-minute single cases (d = 1.52, p = 0.005). Format probably
outranks every pixel in this document.
