# TEAM B — MEASUREMENT ANALYST REPORT
### Numeric signature separating approved from rejected thumbnails

Measured 28 files: 2 approved, 1 soft-pass, 12 competitor, 9 rejected (5 named +
4 siblings), 4 source plates. All code in
`scratchpad\measure_thumbs.py`, `local_metrics.py`, `pass3.py`, `pass4_skin.py`,
`pass5_mottle.py`, `pass6_subject.py`, `pass7_gap.py`, `dupcheck.py`,
`verify_faces.py`, `bgzoom.py`. Raw output: `measurements.json`,
`local_metrics.json`, `pass3.json`, `pass5_mottle.json`, `pass6.json`,
`dupcheck.json`.

Environment: cv2 5.0.0, numpy 2.5.2, YuNet `yunet2023.onnx` via
`cv2.FaceDetectorYN`. Face boxes were verified **by eye** on
`face_verify_sheet.png` before any per-face number was believed.

---

## 0. READ THIS FIRST — THE DELIVERY-PATH CONFOUND

Every competitor thumbnail carries an **identical** JPEG luma quantisation
table (sum = 736). Every file I render carries sum = 369. `ref9800.jpg` is 700.

| set | jpg_qtsum | bits/pixel |
|---|---|---|
| competitor thumbs (all 12) | **736** | 0.100 – 0.197 |
| ref9800 (his own, off YouTube) | **700** | 0.135 |
| everything I render | **369** | 0.297 – 0.448 |

736 is YouTube's re-encode. It is a *much* coarser quantiser than 369.
Consequence, measured:

```
mush_f2.0  (share of 40px tiles with fine-detail std < 2.0)
  COMPETITOR   mean 0.651   [0.382 – 0.888]
  REJECTED     mean 0.290   [0.124 – 0.488]
```

**The rejected thumbnails are objectively sharper than every competitor
thumbnail, purely because of the encoder.** Any sharpness, flatness, detail,
banding or blockiness metric compared against the competitor set is measuring
YouTube's encoder, not design quality. Anyone who "matches competitor
sharpness" will deliberately destroy the image.

**Rule: image-quality metrics are only valid inside the qtsum=369 group** —
i.e. `HS_REMAKE` + `WORKING` (good) vs `V2 / V3 / GLW / AUD / S` (bad).
The competitor set and `ref9800` are valid **only** for layout, subject
placement, and colour intent.

---

## 1. THE SIGNATURE — four independent gates

Applied to the same-encoder set. Every rejected file trips at least one gate.
Both approved files trip none. **0 false positives, 0 false negatives.**

| file | verdict | A flatG_p90 | A poster_fA>.8 | B bg_mush_f1 | B gap_mush | C subj max L | D dup inliers | GATES FAILED |
|---|---|---|---|---|---|---|---|---|
| HS_REMAKE | **APPROVED** | 0.297 | 0.0137 | 0.316 | n/a | 160 | 0 | **none** |
| WORKING | soft-pass | 0.235 | 0.0159 | 0.295 | n/a | 155 | 0 | **none** |
| V2_4046 | rejected | **0.664** | **0.0857** | **0.729** | **0.844** | 150 | 0 | **A, B** |
| V3_4046 | rejected | **0.402** | **0.0603** | 0.115 | 0.110 | 119 | **14** | **A, D** |
| GLW_4046 | rejected | **0.438** | **0.0434** | **0.585** | **0.583** | 146 | **3** | **A, B, D** |
| AUD_4046 | rejected | **0.373** | **0.0417** | 0.053 | 0.000 | 150 | **9** | **A, D** |
| S_4046 | rejected | 0.037 | 0.0049 | 0.008 | 0.405 | **221** | 0 | **C** |
| *ref9800 (control)* | *approved* | *0.263* | *0.0189* | *0.435†* | *0.420†* | *133* | *0* | *none* |

† `ref9800` is post-YouTube, so Gate B does not apply to it. See §0.

Re-derived by code in `verify_gates.py`, not read off the table:
```
HS_REMAKE.jpg  truth=GOOD pred=GOOD failed=-
WORKING.jpg    truth=GOOD pred=GOOD failed=-
V2_4046.jpg    truth=BAD  pred=BAD  failed=A,B
V3_4046.jpg    truth=BAD  pred=BAD  failed=A,D
GLW_4046.jpg   truth=BAD  pred=BAD  failed=A,B,D
AUD_4046.jpg   truth=BAD  pred=BAD  failed=A,D
S_4046.jpg     truth=BAD  pred=BAD  failed=C
SAME-ENCODER RESULT: 0 FP / 0 FN - CONFIRMED
ref9800.jpg (Gate B correctly withheld)  failed=-  -> PASS
ref9800.jpg (Gate B wrongly applied)     failed=B  -> would be a FALSE POSITIVE
```

### Scope limits on the gates — measured, not assumed
Running A/C/D against the 12 competitor thumbnails (Gate B withheld as invalid
post-YouTube):

```
10 of 12 competitors trip Gate A
 3 of 12 competitors trip Gate C  (1200000: L 204, 42000: L 204, 971000: L 192)
 0 of 12 competitors trip Gate D
```

So, honestly:
- **Gate A is a PRE-DELIVERY gate, like Gate B.** YouTube's coarse quantiser
  manufactures flat tiles, so 10/12 successful competitor thumbnails fail it.
  `ref9800` passing A (0.263 / 0.0189) is not enough to claim general validity.
  Apply A and B to the render, never to anything already through YouTube.
- **Gate C is a flag, not a hard fail.** Three successful competitor thumbnails
  (1.2M, 42k, 971k views) exceed L\* 180 on a subject. Absolute brightness is
  not intrinsically wrong; his complaint was that **Boyd** is brighter and paler
  *than the defendant beside her*. S_4046 at L\* 221 is an extreme worth
  flagging, but do not treat >180 as proof of a defect.
- **Gate D is the only gate valid in every context** — 0/15 approved and
  competitor files, nonzero only in the V3/AUD/GLW family.

Sibling files behave identically to their parents (`V2_4026` 0.616/0.0853/0.739,
`V2_4058` 0.617/0.0469/0.770, `V3_4026` 0.418/0.0620/dup 9, `V3_4058`
0.384/0.0433/dup 9) — the signature is stable across the three cases, not a
one-frame accident.

### Gate A — LOCAL FLATNESS / POSTERISATION  *(catches V2, V3, GLW, AUD)*
The single best general quality discriminator.
- `flatG_p90` = 90th percentile, over 40×40px tiles, of the share of pixels whose
  3×3 dilate == erode in **grayscale**.
- `poster_fA>.8` = share of tiles where **>80% of pixels are locally flat in Lab a\***.

```
              flatG_p90        poster_fA>.8
APPROVED    0.235 – 0.297      0.0137 – 0.0189
REJECTED    0.373 – 0.664      0.0417 – 0.0857
gap         1.26×              2.2×
```
Non-overlapping on both, for 4 of the 5 rejects.

### Gate B — SMEAR / MUSH  *(catches V2, GLW)*
This is his "background is all weird", "smooth areas where it's not supposed to
be smooth", "the background is slop".
- `bg_mush_f1` = share of background tiles (faces, title text and arrow excluded)
  whose high-pass std < 1.0.
- `gap_mush_f2` = same, restricted to the empty column between the two subjects.

```
              bg_mush_f1       gap_mush_f2
APPROVED    0.295 – 0.316      no gap exists
REJECTED    0.585 – 0.729      0.583 – 0.865   (V2 family + GLW)
```
Confirmed by eye at 3× in `bg_zoom.png`: the same 200×150 patch is real fabric
weave in HS_REMAKE/WORKING and a featureless blur in GLW.

### Gate C — SUBJECT EXPOSURE  *(catches S)*
His repeated complaint: *"boyd still looks so bright and pale"*, *"boyds cut out
looks washed out ... make sure boyd isnt way too bright"*.
- Median Lab **L\*** of each subject's face, graphics-inpainted, hair/shadow excluded.

```
              max subject L*
APPROVED    144 – 160   (ref9800 112 – 133)
COMPETITOR  109 – 204
S_4046      221         <-- left subject; right 167, p95 232, blowout 3.5%
all others  ≤ 167
```
S_4046 is the only file in the entire 28 with a subject face median above 180.

### Gate D — DUPLICATE SUBJECT  *(catches V3, AUD)*
The same person present twice. SIFT ratio-test correspondences between every
pair of face crops, RANSAC-filtered by one similarity transform.

**The checker was validated against known answers before use:**
```
V3_4046   f1~f2   inliers=14   truth = SAME (duplicate)      <- detected
V3_4046   f0~f1   inliers= 0   truth = DIFFERENT (control)
V2_4046   f0~f1   inliers= 0   truth = DIFFERENT (control)
HS_REMAKE f0~f1   inliers= 0   truth = DIFFERENT (control)
ref9800   f0~f1   inliers= 0   truth = DIFFERENT (control)
```
Full scan result — **every one of the 15 approved + competitor thumbnails scores
exactly 0 inliers, with no exceptions.** Nonzero only here:

```
V3_4046  14   V3_4026   9   V3_4058   9   AUD_4046  9   GLW_4046  3
```
Visually confirmed in `dup_evidence.png`: V3 has the defendant twice side by
side (the left copy also carrying heavy grey blotching); AUD has her again as a
small blurred face in the plate behind her.

### Supporting signature — V3's grey blotching is global desaturation
V3's two subject faces sit at Lab chroma **C = 12.2 and 15.0**, the lowest of
any subject measured (approved 14.0 – 37.4; every other render 24 – 46), and
its whole-frame HSV saturation is **67.6** vs 98.4 / 123.9 for the approved
pair. The "colour blotching" is measurable as chroma collapse, not as noise.

---

## 2. TOLERANCES  (targets from the approved set; bands with headroom)

| metric | target | accept | fail | derived from |
|---|---|---|---|---|
| `flatG_p90` *(pre-delivery only)* | ≤ 0.27 | **≤ 0.30** | > 0.35 | approved max 0.297, rejected min 0.373 |
| `poster_fA>.8` *(pre-delivery only)* | ≤ 0.016 | **≤ 0.020** | > 0.030 | approved max 0.0189, rejected min 0.0417 |
| `bg_mush_f1` *(pre-delivery only)* | ≤ 0.32 | **≤ 0.35** | > 0.45 | approved max 0.316, rejected min 0.585 |
| `gap_mush_f2` *(pre-delivery only)* | n/a | **≤ 0.45** | > 0.55 | ref9800 0.420, rejected 0.583+ |
| subject face median L\* *(flag, not fail)* | 110 – 160 | **≤ 175** | > 180 | approved 112–160, S 221; but 3/12 competitors also >180 |
| subject face blowout (L\*>235) | ≤ 0.005 | **≤ 0.020** | > 0.030 | approved ≤0.008, S 0.035 |
| subject Lab chroma C | 20 – 37 | **14 – 40** | < 13 | approved 14.0–37.4, V3 12.2 |
| whole-frame HSV S | 98 – 147 | **90 – 150** | < 80 | approved 98.4/147.0, V3 67.6 |
| duplicate-face SIFT inliers | 0 | **0** | ≥ 1 | 15/15 clean files score exactly 0 |
| face h_frac (largest) | 0.40 – 0.48 | 0.28 – 0.50 | — | approved 0.461/0.479; does not discriminate |

Encoding note: render at qtsum ≈ 369 (high-quality JPEG). Do **not** pre-soften
to match competitor thumbnails — YouTube applies qtsum 736 on top.

---

## 3. TRAPS — measurements that look meaningful and are not

**T1. Whole-frame flatness is IDENTICAL between good and bad. Say it out loud.**
```
c_flat_gray:  HS_REMAKE (approved)  0.1131
              V3_4046   (rejected)  0.1132
```
One part in ten thousand. Approved range 0.086–0.113, rejected range
0.040–0.167 — the rejected range *contains* the approved range. `c_flat_a` and
`c_flat_b` overlap the same way (approved 0.206–0.245 / 0.222–0.264; rejected
0.099–0.282 / 0.123–0.291). **The defect only appears when you tile the frame
and take the 90th percentile.** Global means average the defect away to nothing.
This is the trap most likely to be fallen into.

**T2. Laplacian variance is useless here.** Approved spans 236 (ref9800) to 2431
(HS_REMAKE) — a 10× range *inside the approved set*. Rejected spans 1129–1625,
entirely inside it. It is measuring the JPEG encoder and text-edge ringing.

**T3. Near-equal, level faces are NOT a defect — he asked for them.** Rejected
files have face-height ratio 1.03–1.19 and Δcy ≈ 0.001–0.029 (perfectly level),
while approved are 1.27–2.08 / Δcy 0.135–0.256. This looks like a clean
discriminator and it is a mirage. Verbatim, 2026-08-29:
> *"you need to make the defendant about the same size as Judge Boyd ... they
> just need to be, like, about equal sizes. And the defendant's gonna be on the
> left side. Judge Boyd's gonna be on the right side."*
The level, equal-sized, left/right layout **is the spec**. Do not "fix" it.

**T4. Halo / fringe detection scores the APPROVED files worse.**
```
halo_f>60:  HS_REMAKE 0.0246   WORKING 0.0227
            S_4046    0.0147   AUD 0.0143   GLW 0.0052
```
Inverted. A tophat ridge detector cannot tell a cut-out fringe from a text
stroke or genuine fine detail. There *is* a visible white fringe on S_4046 (see
`bg_zoom.png` bottom-right) but this metric does not find it. Unsolved.

**T5. Saturation does not separate.** `ref9800` — *the winning thumbnail* — is
the most saturated file in the approved set (wf_sat 147.0, satclip 0.141,
sat_p95 253.6), **higher than S_4046** (133.0 / 0.097 / 252.3) which was
rejected. High saturation is not the S_4046 defect; brightness is.

**T6. Per-face chroma band-pass ranks the RED ARROW as blotching.** My first
per-face metric gave V3_4046 face[2] the highest chroma-blotch score in the
entire dataset (8.31). Face[2] is the **clean** copy — the big saturated arrow
simply sits inside its bounding box. Mask and inpaint graphics before any
chroma measurement.

**T7. Skin-range masking inverts the blotch ranking.** Restricting to
Lab a\* 5–32 excludes the grey blotches *themselves*, so the metric measured
everything except the defect and scored the blotched face (1.81) *below* the
clean one (4.86). Discarded. A tone-adaptive replacement (deviation from each
face's own median chroma) also failed validation — it is dominated by ordinary
lit/shadow falloff. **Per-face blotch localisation is unsolved; V3 is caught by
Gate D + global chroma collapse instead.**

**T8. `plate_surgical.png` and `plate_4046_hypir.png` have byte-identical RGB.**
Every RGB metric matches to 4 decimals; only alpha coverage differs (100% vs
36.5%). The "surgical" pass is an alpha matte only — it changed no pixel colour
and added no detail. Same for `judge_4046_surgical` vs `judge_4046_hypir`.

**T9. No separation at all** (approved range fully overlaps rejected):
`wf_luma` (approved 80.9–100.9 / rejected 96.4–115.3), `top_bot_ratio`
(0.97–2.20 / 1.31–2.24), `wf_gt245` (0.009–0.024 / 0.002–0.022),
`uniq_colors_q4`, `c_edge_frac`, `c_hf_std`, `n_faces`, `max_face_hfrac`,
`c_blotch_a/b`. Do not build on any of these.

**T10. `contrast_std` looks clean but is not trustworthy.** Approved 58.8–66.4,
rejected 69.3–81.9 — no overlap on n=7. But the competitor set spans 55.4–79.1,
straddling both, and the metric is heavily driven by how much title text is on
the frame (text_frac ranges 0.057–0.243). Treat as coincidence unless it
survives a larger sample.

---

## 4. WHAT THE SOURCE MATERIAL WOULD ALLOW

The plate before damage is measurably clean, and better than every render made
from it:

| | plate_4046_hypir | best approved render | worst reject |
|---|---|---|---|
| `c_flat_gray` | **0.0352** | 0.0991 | 0.1666 |
| `c_flat_a` | **0.1189** | 0.2062 | 0.2818 |
| `poster_fA>.8` | **0.000** | 0.0137 | 0.0857 |
| `flatG_p90` | **0.0735** | 0.235 | 0.664 |
| `bg_mush_f1` | **0.119** | 0.295 | 0.739 |
| `c_blotch_a` | **1.156** | 3.246 | 4.737 |

`poster_fA>.8` is exactly **0.000** on both source plates and on the judge tile —
zero posterised tiles anywhere. Every posterisation, every mush tile and every
duplicate in the rejected outputs was introduced downstream of the plate. The
material was never the limit.

---

## 5. CODE — the two metrics that carry the result

```python
# Gate A — local flatness, 40x40 tiles at canonical 1280x720, title text masked
def flat3(ch):                       # locally-flat pixel map
    k = np.ones((3,3), np.uint8)
    return (cv2.dilate(ch,k) == cv2.erode(ch,k))

lab = cv2.cvtColor(cn, cv2.COLOR_BGR2LAB); gray = cv2.cvtColor(cn, cv2.COLOR_BGR2GRAY)
fa, fg = flat3(lab[:,:,1]), flat3(gray)
fav, fgv = [], []
for y in range(0, 720-40+1, 40):
    for x in range(0, 1280-40+1, 40):
        if content[y:y+40, x:x+40].mean() < 200:   # skip tiles touching text
            continue
        fav.append(fa[y:y+40, x:x+40].mean())
        fgv.append(fg[y:y+40, x:x+40].mean())
flatG_p90     = np.percentile(fgv, 90)
poster_fA_gt8 = (np.array(fav) > 0.8).mean()

# Gate D — duplicate subject; 0 inliers on all 15 approved+competitor files
def dup_score(a, b):                 # a, b = two face crops, normalised to 256px tall
    ka, da = SIFT.detectAndCompute(norm(a), None)
    kb, db = SIFT.detectAndCompute(norm(b), None)
    good = [m for m, n in BF.knnMatch(da, db, k=2) if m.distance < 0.75*n.distance]
    if len(good) < 6: return 0
    src = np.float32([ka[m.queryIdx].pt for m in good]).reshape(-1,1,2)
    dst = np.float32([kb[m.trainIdx].pt for m in good]).reshape(-1,1,2)
    _, mask = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC,
                                          ransacReprojThreshold=3.0)
    return 0 if mask is None else int(mask.sum())
```

---

## 6. HONEST LIMITS

- n = 2 approved renders in the only encoder-valid comparison group. The gates
  separate perfectly, but 2 is 2. The 4 sibling files and the 12 competitors
  were used as consistency checks, not as training data.
- **Gates A and B are pre-delivery only** (10/12 and ~all competitors trip them
  post-YouTube). **Gate C is a flag** (3/12 successful competitors trip it).
  **Gate D is the only universally valid gate.** Any scoring system that runs
  A/B/C on a downloaded thumbnail will condemn work that is actually fine.
- Per-face blotch localisation failed twice and is unsolved (T6, T7). V3 is
  caught by other gates; a *future* blotched frame with no duplicate and normal
  global chroma would slip through.
- Cut-out fringe / feathering quality — the thing he explicitly praised in
  HS_REMAKE — has **no working metric** (T4). This is the largest open gap.
- "The middle between them doesn't make sense": gap *width* does not separate
  (approved 0.275/0.274 vs rejected 0.211–0.365, fully overlapping). Only gap
  *content* (mush, or a duplicate face) does.
