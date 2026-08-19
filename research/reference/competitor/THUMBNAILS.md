# Audit the Court — thumbnail system, measured

Competitor: **Audit the Court** (`@AudittheCourt`, ~192K subs).
Client: **Texas Trial Tracker** (`@TexasTrialTracker`) — FOUND, ~2.9K subs.

Every number below comes from a pixel read on a file in
`research/reference/competitor/thumbs/`. All 12 competitor thumbs pulled at
`maxresdefault` = **1280×720**. Anything not measured is written `UNMEASURED`.

Tooling used: PIL 12.3.0 (pixel sampling, glyph masks, crops), OpenCV 5.0.0 +
YuNet `face_detection_yunet_2023mar.onnx` (face boxes, eye landmarks),
11 candidate fonts rendered and IoU-matched against extracted glyphs.

---

## 1. Verbatim text + typography

| Views | ID | String (verbatim) | Words | Chars | Case | Colour split |
|---|---|---|---|---|---|---|
| 1.2M | yzv_uxBSgu0 | `This cop was lying!` | 4 | 19 | Sentence | white `This` / yellow `cop was lying!` |
| 971K | 4kIjd7CLp7c | `He destroyed the cop's attorney` | 5 | 31 | Sentence | yellow `He destroyed` / white `the cop's attorney` |
| 591K | amiWU58HFpM | `That is not the law!` | 5 | 20 | Sentence | white `That is` / yellow `not the law!` |
| 552K | SpO2yU2mG78 | `He lost this case!` | 4 | 18 | Sentence | white `He` / yellow `lost this case!` |
| 444K | 5VLPFCTlyss | `Cops can't do that!` | 4 | 19 | Sentence | white `Cops` / yellow `can't do that!` |
| 439K | lzOg8heXmV0 | `This is what an arrogant cop looks like` | 8 | 38 | Sentence | white / yellow `arrogant cop` / white — 3 lines |
| 414K | Ek3Ah3NZYVo | `This is what a bully with a badge looks like` | 9 | 43 | Sentence | white / yellow `bully with a badge` / white — 4 lines |
| 412K | IPpy830CJkQ | `I'm sick of bad cops!` | 5 | 21 | Sentence | white `I'm sick of` / yellow `bad cops!` |
| 364K | AAVDROvkXsU | `I'm sure that was uncomfortable!` | 5 | 31 | Sentence | white `I'm sure that was` / yellow `uncomfortable!` |
| 301K | qyETv1lTSuA | `Get out of my courtroom!` | 5 | 24 | Sentence | yellow `Get out` / white `of my courtroom!` |
| 59K | bXbyg2vK6CI | `I don't need a lawyer!` | 5 | 22 | Sentence | white `I don't` / yellow `need a lawyer!` |
| 42K | muF8LBaKZrI | `Are you completely insane?` | 4 | 26 | Sentence | white `Are you` / yellow `completely insane?` |

**Zero all-caps in 12/12.** Every string is a first-person or accusatory
*quote* in sentence case. Word count 4–9, median 5. Char count 18–43, median 23.

### Colour — every value a sampled pixel

| Role | Sampled hex | n images | Method |
|---|---|---|---|
| Yellow fill | `#FEFB04` `#FDFB06` `#FFFC02` `#FDFC05` `#FFFB03` `#FFFC01` `#FEFC05` `#FEFB04` | 12/12 | median of 2px-eroded glyph interior |
| White fill | `#FFFFFF` (±1 LSB) | 12/12 | same |
| Stroke | `#050300`–`#0E0B00` → **pure black `#000000`**, JPEG-lifted | 12/12 | black pixels ringing glyph |
| Arrow fill | `#FD0101` `#FD0100` `#FC0100` `#FB0202` `#FC0101` `#FE0000` | 9/12 | median of red mask |

Yellow is a **pure-primary yellow**, mean of all 12 medians ≈ `#FEFB03`.
It is not gold, not amber. Red arrow is a **pure red**, mean ≈ `#FD0101`.

### Cap height, stroke, shadow

| ID | Cap height px | as fraction of H | Stroke width px (median) | Text band y (frac H) | Text band x (frac W) |
|---|---|---|---|---|---|
| yzv_uxBSgu0 | 56 | 0.078 | 11.0 | 0.069–0.175 | 0.036–0.666 |
| 4kIjd7CLp7c | 37 | 0.051 | 8.5 | 0.061–0.113 | 0.016–0.723 |
| amiWU58HFpM | 57 | 0.079 | 10.0 | 0.085–0.169 | 0.031–0.698 |
| SpO2yU2mG78 | 69 | 0.096 | 8.0 | 0.061–0.164 | 0.023–0.690 |
| 5VLPFCTlyss | 59 | 0.082 | 9.0 | 0.061–0.146 | 0.373–0.963 |
| lzOg8heXmV0 | 70 | 0.097 | 8.0 | 0.19–0.63 (3 lines) | 0.050–0.590 |
| Ek3Ah3NZYVo | 72 | 0.100 | 10.5 | 0.18–0.79 (4 lines) | 0.047–0.420 |
| IPpy830CJkQ | 57 | 0.079 | 9.0 | 0.082–0.161 | 0.34–0.936 |
| AAVDROvkXsU | 43 | 0.060 | 10.0 | 0.047–0.110 | 0.029–0.870 |
| qyETv1lTSuA | 51 | 0.071 | 10.0 | 0.139–0.208 | 0.030–0.710 |
| bXbyg2vK6CI | 56 | 0.078 | 10.0 | 0.265–0.965 → y 0.072–0.153 | 0.265–0.965 |
| muF8LBaKZrI | 40 | 0.056 | 10.0 | 0.029–0.101 | 0.009–0.677 |

Cap height mean **0.0773 H** (σ 0.0155) = **~56 px at 1280×720**.
Stroke width mean **9.5 px** (range 8.0–11.0). Very tight.

**Drop shadow: none directional.** Measured by shifting the glyph mask ±6 px
and comparing mean luminance of the exposed ring:

| ID | down6 | up6 | right6 | left6 |
|---|---|---|---|---|
| yzv_uxBSgu0 | 49.1 | 48.8 | 63.2 | 64.3 |
| lzOg8heXmV0 | 83.2 | 83.9 | 109.1 | 105.4 |
| 5VLPFCTlyss | 43.8 | 42.0 | 65.7 | 63.7 |

Vertical up = vertical down to within 1.5 L. It is a **zero-offset black glow**,
not a drop shadow. Falloff profile (yzv_uxBSgu0), median hex by distance ring:

- 0–3 px out: `#0A0702` (L 28)
- 4–8 px out: `#2F2E2B` (L 44)
- 8–14 px out: `#61625F` (L 94)
- 14–22 px out: `#A4A5A3` (L 160)

So: **hard black stroke ~9 px, then a soft black glow decaying over ~20 px.**

### Typeface

Extracted the yellow glyphs of `arrogant` from `439000_lzOg8heXmV0.jpg`,
segmented individual letters, and IoU-matched against 11 candidates rendered
locally and scaled to the target bounding box:

| Candidate | mean IoU on `g`+`a` | native `g` aspect (target 0.815) |
|---|---|---|
| **Montserrat Black (wght 900)** | **0.9038** | **0.842** |
| Nunito (1000) | 0.8877 | 0.814 |
| Inter (900) | 0.8803 | 0.736 |
| Segoe UI Black | 0.8607 | 0.759 |
| Roboto (900) | 0.8501 | 0.670 |
| Verdana Bold | 0.8377 | 0.741 |
| Arial Bold | 0.8064 | 0.679 |
| Poppins Bold | 0.8007 | 0.702 |
| Open Sans (800) | 0.7452 | 0.727 |
| Century Gothic Bold | 0.7209 | 0.733 |
| Archivo (900) | 0.6726 | 0.777 |

**Montserrat Black wins on both metrics.** Classification: **heavy/black
geometric-leaning grotesque sans**; double-storey `a` with a spur, single-storey
`g` with an open left hook, round `i` dots, high x-height, no condensation.
Called "closest match of 11 tested", not confirmed — I did not obtain the
channel's source file.

---

## 2. Faces (YuNet, conf ≥ 0.55, primary subject only)

| Views | ID | Faces | Primary subject | Face box (frac W × frac H) | Face centre (x,y) | Eyes (frac H) | Crop |
|---|---|---|---|---|---|---|---|
| 1.2M | yzv_uxBSgu0 | 6 | attorney (bow tie), right | 0.161 × 0.435 | 0.785, 0.317 | 0.289 | head+shoulders |
| 971K | 4kIjd7CLp7c | 3 | judge (9th Cir.), right panel | 0.111 × 0.282 | 0.806, 0.283 | 0.254 | head+shoulders |
| 591K | amiWU58HFpM | 3 | judge, right | 0.125 × 0.326 | 0.805, 0.347 | 0.304 | head+shoulders |
| 552K | SpO2yU2mG78 | 5 | cop (cut-out), right | **0.310 × 0.699** | 0.807, 0.575 | 0.483 | **head only, extreme** |
| 444K | 5VLPFCTlyss | 5 | judge, left | 0.127 × 0.293 | 0.221, 0.321 | 0.280 | head+shoulders |
| 439K | lzOg8heXmV0 | 2 | cop (webcam), right | 0.157 × 0.409 | 0.765, 0.425 | 0.390 | head+shoulders |
| 414K | Ek3Ah3NZYVo | 1 | detective, right | 0.155 × 0.340 | 0.756, 0.247 | 0.204 | head+shoulders |
| 412K | IPpy830CJkQ | 3 | judge, left | 0.062 × 0.186 | 0.228, 0.393 | 0.366 | wide |
| 364K | AAVDROvkXsU | 5 | judge, right | 0.169 × 0.410 | 0.778, 0.477 | 0.420 | head+shoulders |
| 301K | qyETv1lTSuA | 3 | judge Milliron, right | 0.082 × 0.192 | 0.794, 0.286 | 0.263 | wide (pointing) |
| 59K | bXbyg2vK6CI | 7 | 3 equal faces | 0.210 / 0.190 / 0.192 W | 0.145 / 0.528 / 0.849 | 0.386–0.460 | head+shoulders ×3 |
| 42K | muF8LBaKZrI | 3 | judge (Zoom), left | 0.138 × 0.360 | 0.254, 0.508 | 0.458 | head+shoulders |

Primary-face width **mean 0.151 W** (excluding SpO outlier: 0.136 W).
Primary-face eyes **mean 0.345 H**.

Expressions (read from the images): mouth open mid-speech in 10/12
(yzv, 4kI, ami, SpO, 5VL, qyE, bXb, muF, IPp, AAV); closed-mouth deadpan in
2/12 (lzO, Ek3 — both the "This is what a … looks like" format). Hands raised /
gesturing in 3 (yzv, 5VL, qyE-pointing). Nobody smiles except the cop in AAV,
where the *smirk* is the point.

---

## 3. Graphic devices

**Red arrow — 9 of 12.** Absent in lzOg8heXmV0, Ek3Ah3NZYVo (both the
deadpan-portrait format) and qyETv1lTSuA (judge points with his own arm).

| ID | Arrow bbox (frac W, frac H) | size px | area px | fill | direction |
|---|---|---|---|---|---|
| yzv_uxBSgu0 | 0.339–0.422, 0.278–0.375 | 107×71 | 3376 | `#FD0101` | left, ~15° down |
| 4kIjd7CLp7c | 0.222–0.309, 0.208–0.310 | 112×74 | 3903 | `#FD0100` | left-down |
| amiWU58HFpM | 0.272–0.330, 0.353–0.471 | 76×86 | 3016 | `#FC0100` | down-left |
| SpO2yU2mG78 | 0.191–0.277, 0.263–0.365 | 111×75 | 3917 | `#FB0202` | left-down |
| 5VLPFCTlyss | 0.523–0.600, 0.392–0.507 | 99×84 | 3821 | `#FC0101` | down-right |
| IPpy830CJkQ | 0.689–0.755, 0.336–0.442 | 86×77 | 3044 | `#FD0100` | down-right |
| AAVDROvkXsU | 0.259–0.335, 0.250–0.353 | 98×75 | 3410 | `#FC0101` | down-left |
| bXbyg2vK6CI | 0.323–0.414, 0.289–0.392 | 117×75 | 4133 | `#FD0100` | down-right |
| muF8LBaKZrI | 0.527–0.665, 0.419–0.590 | **178×124** | **5992** | `#FE0000` | down-right |

Arrow area of the 8 non-outliers: **3016–4133 px, mean 3578**.
`muF8LBaKZrI` (worst performer) is **5992 px = 67 % above that mean**.
All arrows carry a thin black outline (ring mean L 27–59).

**Circles / rings: 0 of 12.** **Logo / watermark: 0 of 12.**
**Borders: 0 of 12** (edge-pixel std 48–87 on every image; no uniform frame).

**Split-screen divider — only 2 of 12 have a real drawn divider.**

| ID | x | frac W | width px | colour (sampled at 4 heights) |
|---|---|---|---|---|
| 4kIjd7CLp7c | 821–825 | 0.643 | ~5 | `#A4A19C` `#F0EBE7` `#F6EFE5` `#F3EEEB` — white bar, image-dependent |
| IPpy830CJkQ | 458–465 | 0.360 | ~8 | `#FBCABC` `#FFC9B8` `#FFCCB7` — warm off-white |

`muF8LBaKZrI` uses an **irregular torn/jagged white edge** (x ≈ 595–607 varying
with height, `#F8FAF9`–`#FEF0F0`) instead of a straight bar — the only one.
The remaining 9 are single-plate composites: a **subject cut out and pasted over
a second courtroom plate**, with soft feathered edges and **no white outline
stroke on the cut-out**.

**Background treatment.** Only `SpO2yU2mG78` desaturates: mean saturation
**left/back plate 0.155 vs right/foreground 0.357** — the back plate is pushed
to near-greyscale while the cut-out cop stays full colour. Nothing else does it.

**No darkening band behind text.** Mean L of the top 18 % (excluding text
pixels) vs the bottom half:

| ID | top L | bottom L | ratio |
|---|---|---|---|
| yzv | 147.6 | 124.2 | 1.19 |
| 4kI | 107.0 | 63.3 | 1.69 |
| ami | 116.5 | 63.6 | 1.83 |
| SpO | 148.3 | 82.7 | 1.79 |
| muF | 140.0 | 63.0 | 2.22 |

Every ratio ≥ 1.17 — the top strip is *brighter*, not darkened. The text is
legible purely from the 9 px black stroke + glow. No scrim, no gradient, no
colour block anywhere in the 12.

Global saturation across the set: **0.207–0.457, mean 0.331**. No punched
saturation. Luminance σ 53–77 — natural-contrast footage, lightly graded.

---

## 4. Blind control

I read the full auto-transcript of three videos, wrote the thumbnail I would
have made, committed it to disk, and only then opened theirs. My designs are at
`…/scratchpad/blind_designs.md`, written before the reads.

### 4kIjd7CLp7c (971K) — CHP officer arrests a firefighter; 9th Cir. qualified-immunity argument

| | Mine (blind) | Theirs (measured) |
|---|---|---|
| Subject | split: judge + deputy AG | split: two counsel at lectern (L, 64 % of frame) + judge (R panel) |
| Text | `YOU ARRESTED A FIREFIGHTER?` — 4 w, 27 ch, ALL CAPS | `He destroyed the cop's attorney` — 5 w, 31 ch, sentence case |
| Colour | white + yellow `FIREFIGHTER` | yellow `He destroyed` + white remainder |
| Cap height | ~0.13 H | 0.051 H |
| Divider | white, ~6 px, centre | white, 5 px, at **0.643 W** |
| Arrow | judge → attorney | red, left-down, 0.222–0.309 W |
| Bg treatment | desaturate + vignette | none |

**What they did that I did not:**
1. **They abandoned the facts of the case entirely.** No firefighter. No fire
   truck. No qualified immunity. The thumbnail sells a *social event* — one man
   humiliating another — that the transcript barely supports.
2. Sentence case, not caps. I defaulted to caps; 12/12 of theirs are not.
3. Cap height 0.051 H — **2.5× smaller than I'd have set it.** They let the
   faces carry the frame.
4. Divider at 0.643 W, not 0.5 — a **deliberately asymmetric 2:1 split**.
5. The yellow lands on the *verb* (`destroyed`), not the noun. Across all 12,
   yellow marks the accusation, never the subject.

### 5VLPFCTlyss (444K) — sergeant maces a handcuffed woman; Judge Simpson prelim

| | Mine (blind) | Theirs (measured) |
|---|---|---|
| Subject | judge L + bodycam still of the mace R | judge L (face 0.127 W, eyes 0.280 H) + defendant & counsel R — **single continuous courtroom plate** |
| Text | `HE MACED A HANDCUFFED WOMAN` — 5 w, 27 ch, caps, top band | `Cops can't do that!` — 4 w, 19 ch, sentence case, **top-RIGHT** (x 0.373–0.963) |
| Devices | red ring on the mace can, arrow, divider | arrow only (0.523–0.600 W, down-right), **no divider, no ring** |
| Colours | white + red accent | white `Cops` + yellow `#FFFB03` |

**What they did that I did not:**
1. **No bodycam.** They never show the incident. The whole frame is the
   courtroom reaction to it.
2. **Text moved to the top-right** to clear the judge's head — the only layout
   variable that moves, and it moves *for the face*.
3. I invented a red ring. **There is not a single circle or ring in all 12.**
4. My string was 27 chars against their 19. Theirs is a generic rule
   (`Cops can't do that!`) — reusable across dozens of videos; mine was
   case-specific and therefore un-reusable.

### muF8LBaKZrI (42K, worst) — Zoom jail review, disruptive defendant Rudolph

| | Mine (blind) | Theirs (measured) |
|---|---|---|
| Subject | judge L + defendant R, Zoom tiles | judge L (face 0.138 W, eyes 0.458 H) + defendant R, hand raised over head |
| Text | `I PAID $25 TO PEE IN A BOTTLE` — 8 w, 29 ch, caps, bottom-left | `Are you completely insane?` — 4 w, 26 ch, sentence case, top-left flush to x 0.009 |
| Cap height | ~0.10 H | **0.056 H** |
| Divider | plain | **irregular torn white edge** |
| Arrow | at defendant | at defendant, but **178×124 px / 5992 px area** |

**What they did that I did not:**
1. **They discarded the best line in the transcript.** `I paid $25 to pee in a
   bottle` is the most quotable thing said; they used a generic
   `Are you completely insane?`. This is their worst performer at 42K — which
   is a point *for* my instinct, but n=1.
2. Torn divider instead of a bar — a break from their own system.
3. Oversized arrow — 67 % above their own mean.
4. Text pushed flush to x = 0.009 W and y = 0.029 H, tighter to the edge than
   any other in the set.

**Net across the three:** I over-indexed on the *facts* of each case and on
ALL-CAPS. Their system is the opposite — a **generic emotional quote** in
**sentence case at half the size I'd choose**, with the faces doing the work.

---

## 5. The system: constants vs variables

### CONSTANTS — 12/12 unless noted. Rebuildable spec at 1280×720.

```
CANVAS      1280 × 720. No border. No logo. No watermark. No frame.

TYPE        Heavy/black grotesque sans, closest tested match Montserrat Black
            (wght 900), IoU 0.904 on isolated glyphs.
            Sentence case. NEVER all caps. (12/12)
            Ends in ! or ? in 10/12; the 2 exceptions are the "This is what a
            … looks like" format, which ends with no punctuation.
            One line, unless the string is >30 chars, then 3–4 short lines.

SIZE        Cap height 0.0773 H mean, σ 0.0155  →  ~56 px at 720 h.
            Range 0.051–0.100 H. Longer string → smaller cap.

FILL        Two colours only, per string:
              yellow #FEFB03  (mean of 12 sampled medians; pure primary)
              white  #FFFFFF
            Split by MEANING: yellow takes the accusation / verdict phrase,
            white takes the setup. Yellow is 1–3 words in 10/12.

STROKE      Solid black #000000, uniform, median 9.5 px (range 8–11) at 720 h.
            = ~0.0132 H. Scale with cap height, roughly 1 : 6.

SHADOW      Zero-offset black GLOW, not a drop shadow. Verified symmetric
            (up6 vs down6 within 1.5 L on 3 images). Radius ~20 px, opacity
            falling from near-black at 3 px to L 160 at 22 px.
            NO offset shadow anywhere in the set.

COPY        4–9 words (median 5), 18–43 chars (median 23).
            First-person or second-person accusatory QUOTE.
            Generic and reusable — almost never names the case, the person,
            the charge, the court or the date. 0/12 contain a proper noun.
            0/12 contain a number, a date, or a "Day N".

TEXT POS    Top band in 10/12: y 0.029–0.208 H.
            Horizontal position is the ONE thing that moves, and it moves to
            clear the primary face:
              face on the right (7 imgs) → text starts x 0.016–0.057 (left)
              face on the left  (3 imgs) → text starts x 0.265–0.373 (right)
            2/12 (lzO, Ek3) run 3–4 lines down the left half; both are the
            deadpan "This is what a … looks like" format with no arrow.

FACE        One dominant face, head-and-shoulders.
            Width 0.11–0.21 W (mean 0.151), height 0.28–0.44 H.
            Eyes at 0.20–0.46 H (mean 0.345).
            Placed at cx ≈ 0.78 W (7/12) or cx ≈ 0.23 W (4/12) — never centred.
            Mouth open mid-speech in 10/12.

ARROW       Red #FD0101 with a thin black outline.
            ~100 × 78 px, area 3016–4133 (mean 3578) = ~0.4 % of frame.
            Points from empty space INTO the secondary subject, always
            downward-diagonal. Present in 9/12.

COMPOSITE   Subject cut out and pasted over a second courtroom plate,
            feathered edge, NO outline stroke on the cut-out. (9/12)
            A drawn white divider bar appears in only 2/12.

GRADE       Untouched. Mean saturation 0.331 (range 0.207–0.457).
            No vignette, no scrim, no gradient, no darkening behind text,
            no colour block. Top strip measures BRIGHTER than the bottom
            half in 12/12 (ratio 1.17–2.22).
```

### VARIABLES

- Which side the face sits (left cx≈0.23 / right cx≈0.78) — and text follows it.
- Cap height, 0.051–0.100 H, inversely with string length.
- Arrow presence (9/12) and target.
- Line count (1 line for ≤31 chars, 3–4 for 38–43).
- Which phrase gets yellow (leading vs trailing).
- Desaturating the back plate (1/12 only — `SpO2yU2mG78`).
- A drawn divider (2/12) vs a feathered cut-out (9/12) vs torn edge (1/12).

---

## 6. Correlation against views

**n = 12. That is far too small to conclude anything causal**, and these are 10
top performers plus 2 chosen *because* they underperformed, so the sample is
selected on the dependent variable. Treat everything below as description.

**Consistent** (holds across the whole spread, so it explains nothing about
variance): sentence case, two-colour fill, black stroke + glow, no scrim,
no border, no logo, generic quote copy.

**Differences between the 1.2M/971K/591K group and the 42K/59K group:**

| Measure | 1.2M / 971K / 591K | 42K | 59K | Consistent? |
|---|---|---|---|---|
| Primary face width | 0.161 / 0.111 / 0.125 W | 0.138 W | 0.210 W | **No** — the worst two are inside or above the top range |
| Cap height | 0.078 / 0.051 / 0.079 H | 0.056 H | 0.078 H | **No** |
| Word count | 4 / 5 / 5 | 4 | 5 | **No** |
| Char count | 19 / 31 / 20 | 26 | 22 | **No** |
| Stroke px | 11 / 8.5 / 10 | 10 | 10 | **No** |
| Arrow area px | 3376 / 3903 / 3016 | **5992** | 4133 | **Yes** — 42K is 67 % above the mean of the other 8 |
| Number of faces ≥0.15 W | 1 / 1 / 1 | 1 | **3** | **Yes** — 59K is the only image with 3 co-equal faces |
| Divider | feather / white bar 5 px | **torn jagged edge** | feather | **Yes** — 42K is the only torn edge in 12 |
| Copy names the drama | "cop was lying" / "destroyed" / "not the law" | "completely insane" | "don't need a lawyer" | — subjective |

**The only three measurable things unique to the two worst performers are all
deviations from their own system:**

1. `muF8LBaKZrI` (42K) — arrow 67 % oversized **and** the only torn divider in
   the set. Two system breaks in one image.
2. `bXbyg2vK6CI` (59K) — the only thumbnail with **three co-equal faces**
   (0.210 / 0.190 / 0.192 W). Every other image has one clear hero face; this
   one has no focal point.

That is a hypothesis worth testing, not a finding. n=2 on the low side.
It is at least as likely that the topic (a Zoom probation review; a
self-represented defendant) is what capped these at 42K and 59K, and the
thumbnail is downstream of a weak clip.

**What does NOT correlate:** face size, cap height, word count, char count,
stroke width, arrow presence, saturation. The 971K thumbnail has the *smallest*
cap height in the set (0.051 H) and the *second-smallest* hero face (0.111 W).

---

## 7. The client: Texas Trial Tracker

**FOUND.** `https://www.youtube.com/@TexasTrialTracker` — 13 long-form + 11
Shorts enumerated via `yt-dlp --flat-playlist`. The ~865K video is
`sp3IXJYBFwY`, a **Short**, not a long-form upload. Top long-form is 72K.

12 thumbnails downloaded to `thumbs/client/` (11 maxres, 1 hqdefault —
`dAI3GNmNt_s` has no maxres, 480×360 only).

### The client has FOUR incompatible visual systems in 12 thumbnails

| System | Count | Files |
|---|---|---|
| **A. Auto-generated Shorts frame** — vertical 9:16 letterboxed into 16:9 with a blurred-copy background, burnt-in caption from the video, no designed thumbnail at all | **5** | sp3IXJYBFwY (865K), upjOR9Tr0P8, oJvViwEhFyk, Usxub-MQm9k, Zl0i8N8botY, dAI3GNmNt_s |
| **B. True-crime documentary** — dark plate, mugshot-style portrait with a white outer glow, polaroid inset, red + white ALL-CAPS condensed type at the bottom | **4** | Y-_2z7D65Rw (72K), 6V1pKKVR17k (62K), ztBrTKT2Gbk (37K), y_43R2cDx-A (16K) |
| **C. AI-upscaled cut-outs + gold caps** — plasticky retouched faces, thick white outlines, gold text | **1** | cSz-vkSwVlk (9.8K) |
| **D. Purple-outline meme** — Impact-style caps with a magenta outline, comic "OMG!!" sticker, green SMS bubble, black letterbox bars | **1** | o1S6Kbnckro (4.6K) |

### Measured diff, client vs competitor

| Dimension | Audit the Court (12/12) | Texas Trial Tracker | Gap |
|---|---|---|---|
| **Case** | Sentence case, 12/12 | **ALL CAPS in 6/6** designed thumbs (`CAPITAL MURDER`, `TRIAL DAY 6`, `NEW UPDATE`, `HE'S SCARED…`, `YOU CANT KEEP SLAPPING YOUR MOM!`, `"3 DEATHS, $300."`) | Total inversion |
| **Text colour** | yellow `#FEFB03` + white `#FFFFFF`, 12/12 | red `#F30400`, red `#FE3229`, banner red `#FD2F2F`, gold `#F1CA03`/`#EECB05`, white, magenta outline `#BF5DCA`/`#CF4BEC` — **six palettes across six images** | No brand colour exists |
| **Cap height** | mean 0.0773 H (σ 0.0155) | 0.093 / 0.101 / 0.111 / **0.165** / 0.117 H — mean 0.117, σ 0.028 | **51 % larger, 80 % more variable** |
| **Stroke** | black `#000000`, median 9.5 px, 12/12 | 15.5 / 19.0 / 19.5 px black on system B; 9 px on C; **2 px** on D; 3–4 px on the Shorts frames | 2× too heavy where present, absent elsewhere |
| **Primary face width** | mean 0.151 W (0.111–0.310) | Shorts frames: 0.059–0.085 W. Designed: 0.225 / 0.233 / 0.139 / 0.127 / 0.193 W | The 6 Shorts thumbs are at **~40 % of competitor face size** |
| **Copy content** | 0/12 contain a proper noun, number or date | `CAPITAL MURDER TRIAL DAY 4`, `TRIAL DAY 6`, `NEW UPDATE`, `Savannah Soto`, `POLICE BODYCAM — DECEMBER 26, 2023` — proper nouns, dates and day numbers in **4/6** | Selling a *series index*, not a moment |
| **Copy form** | first-person accusatory quote, 12/12 | label/headline in 5/6 (`CAPITAL MURDER`, `NEW UPDATE`). Only `HE'S SCARED…` and `"3 DEATHS, $300."` are quotes | Wrong grammatical mode |
| **Word count** | median 5 | `CAPITAL MURDER TRIAL DAY 4` = 5; `YOU CANT KEEP SLAPPING YOUR MOM!` = 6; `HE'S SCARED…` = 2 | Comparable — this is not the problem |
| **Red arrow** | `#FD0101`, ~3578 px area, 9/12 | present in 1/6 designed (cSz-vkSwVlk) at **16147 px = 4.5× competitor size** | Wrong scale when used |
| **Cut-out outline** | **none** — feathered edges, 12/12 | thick white/glow outline on **4/6** (Y-_2z7D65Rw, 6V1pKKVR17k, cSz-vkSwVlk, y_43R2cDx-A teal glow) | Adds an amateur tell the competitor never uses |
| **Devices competitor never uses** | — | polaroid frames, `NEW UPDATE` badge banner, comic starburst stickers, SMS bubbles, black letterbox bars, teal chromatic-aberration glow | 6 extra device families |
| **Saturation** | mean 0.331 | 0.186–0.576, mean 0.318 | Comparable mean, **3× the spread** |
| **Face treatment** | untouched frame grabs | AI-upscaled / retouched in 2 (cSz-vkSwVlk, and the eyes on ztBrTKT2Gbk) | Uncanny |

### The single largest gap

**Half the client's catalogue has no thumbnail at all.** Six of twelve —
including the 865K "hit" — are YouTube's automatic Shorts frame: a vertical
video letterboxed into 16:9 with a blurred duplicate filling the sides, and
whatever caption happened to be burnt into that frame (`prison`,
`*HANDCUFS*` [sic], `SEND YOU TO PRISON`, `*Families Start Arguing*`). Face
width on those is 0.059–0.085 W against the competitor's 0.151 W mean. There is
no design decision in them to critique.

---

## 8. Ranked copyable changes

Ordered by measured size of gap × cheapness to fix.

1. **Stop shipping Shorts frames as thumbnails.** 6/12. Face at 0.059–0.085 W
   vs 0.151 W; blurred letterbox eating ~31 % of the frame width on each side.
   Upload a designed 1280×720 for every Short. Zero design skill required to
   beat the current state.
2. **Switch to sentence case.** 12/12 vs 6/6 — a total inversion, and free.
3. **Lock one two-colour palette: `#FEFB03` yellow + `#FFFFFF` white.**
   The client currently runs six palettes across six images. Yellow on the
   accusation phrase, white on the setup.
4. **Rewrite copy as a first-person quote with no proper noun, number or date.**
   `CAPITAL MURDER TRIAL DAY 6` → the thing the judge actually said.
   0/12 competitor thumbs name a case; 4/6 client thumbs do.
5. **Set cap height to 0.077 H (≈56 px at 720) and hold it.** Client mean is
   0.117 H with σ 0.028. Shrinking the type is counter-intuitive and is exactly
   what the 971K thumbnail does (0.051 H).
6. **Black stroke `#000000` at 9–10 px, plus a zero-offset black glow at ~20 px
   radius.** Client is at 15–20 px stroke on system B and 2 px on system D.
   Never an offset drop shadow.
7. **Hero face at 0.15 W, eyes at 0.35 H, cx at 0.23 or 0.78 — never centred.**
   Text goes on the empty side.
8. **Delete every outline/glow on cut-outs.** 0/12 competitor thumbs have one;
   4/6 client thumbs do. It is the loudest amateur tell in the set.
9. **Red arrow `#FD0101` at ~100 × 78 px (0.4 % of frame), thin black outline,
   pointing diagonally down into the secondary subject.** Client's one arrow is
   4.5× oversized. Note the competitor's own 42K flop also oversized its arrow
   by 67 %.
10. **Remove polaroids, badge banners, comic stickers, SMS bubbles, letterbox
    bars and teal glows.** The competitor's entire device vocabulary is: one red
    arrow, one optional white divider bar, one cut-out. Nothing else.
11. **Ship exactly one hero face.** The competitor's 59K flop is the only image
    in 12 with three co-equal faces (0.210 / 0.190 / 0.192 W).
12. **Leave the grade alone.** No scrim behind text, no vignette, no saturation
    push. 12/12 measure *brighter* at the top than the bottom.

Caveat carried forward: items 9 and 11 rest on n=2 underperformers selected on
the dependent variable. Items 1–8, 10 and 12 rest on 12/12 vs 6/6 category
differences, which is a much stronger footing.

---

## Files

Competitor — `C:\Users\natha\Projects\boyd-clips\research\reference\competitor\thumbs\`

```
1200000_yzv_uxBSgu0.jpg   1280x720  maxres
971000_4kIjd7CLp7c.jpg    1280x720  maxres
591000_amiWU58HFpM.jpg    1280x720  maxres
552000_SpO2yU2mG78.jpg    1280x720  maxres
444000_5VLPFCTlyss.jpg    1280x720  maxres
439000_lzOg8heXmV0.jpg    1280x720  maxres
414000_Ek3Ah3NZYVo.jpg    1280x720  maxres
412000_IPpy830CJkQ.jpg    1280x720  maxres
364000_AAVDROvkXsU.jpg    1280x720  maxres
301000_qyETv1lTSuA.jpg    1280x720  maxres
59000_bXbyg2vK6CI.jpg     1280x720  maxres
42000_muF8LBaKZrI.jpg     1280x720  maxres
```

Client — `…\competitor\thumbs\client\`

```
865000_sp3IXJYBFwY.jpg    1280x720  maxres   (Short)
72000_Y-_2z7D65Rw.jpg     1280x720  maxres
62000_6V1pKKVR17k.jpg     1280x720  maxres
61000_dAI3GNmNt_s.jpg      480x360  hqdefault (no maxres)
39000_upjOR9Tr0P8.jpg     1280x720  maxres   (Short)
37000_ztBrTKT2Gbk.jpg     1280x720  maxres
27000_oJvViwEhFyk.jpg     1280x720  maxres   (Short)
22000_Usxub-MQm9k.jpg     1280x720  maxres   (Short)
16000_y_43R2cDx-A.jpg     1280x720  maxres
16000_Zl0i8N8botY.jpg     1280x720  maxres   (Short)
9800_cSz-vkSwVlk.jpg      1280x720  maxres
4600_o1S6Kbnckro.jpg      1280x720  maxres
```
