# Team C — Failure-mode post-mortem, Sanchez thumbnail pipeline

Blameless on people, not on code. Every number below was re-measured today from
the files on disk; nothing is carried over from a prior session's claims. Where a
previously-asserted number did not reproduce, that is stated.

The visual proof of the worst defect is `sanchez/DEFECT6_ghost_silhouette.png`.

**Headline:** the current build `V3_4046.jpg` fails one of its own gates
(`G12_FAIL`), the gate runner reports the score as `12/13 met` while running 15
gates, and the file it grades is not the file its facts describe. The picture
contains the defendant **twice**, and the red arrow points at the **copy**.

---

## A. DEFECT TABLE

`f:n` = file:line. "Class" refers to section B.

| # | What the client saw | Root cause | Class | The check that would have caught it |
|---|---|---|---|---|
| **D1** | Red arrow sitting on top of the title text | `build.py:225` calls `free_space_arrow(...)`, **a function that does not exist in the file**. `solve_arrow()` (the fix) was written at `build.py:155` and the caller was never rewired. Measured on the shipped output: **52.9 / 54.7 / 57.7 %** of the arrow's ink lands on the title's ink in `A_boyd4026 / B_boyd4046 / C_boyd4058.jpg`, arrow bbox x1033-1161 y41-114 — inside the title band y37-122. Z-order compounds it: in every generation the arrow is `alpha_composite`d *after* the type, so any overlap at all renders arrow-over-type. Current tolerance still permits it: `v3.py:283` `cost[ov > 0.02] = 1e9` allows 2 % overlap by design | E, G | Assert `(arrow_ink & type_ink_dilated_by_glow_radius).sum() == 0` on the **rendered file**, plus a static import check that every called name resolves (`python -c "import build"`) |
| **D2** | "she's super pale" — skin S 86.3 → 16.6 | Not the RGB multiply itself (a linear multiply is S-invariant); it is the multiply **plus clipping and a per-channel knee**. `build_audit.py:46` `base_plate` multiplies the whole plate by `gain` then clips at 255; `build_audit.py:219-223` `lift_faces` multiplies again then applies `f[hi] = knee + (f[hi]-knee)*scale` **per channel**. Measured today on the exact knee still live at `v3.py:224` and `v3.py:360`: RGB(255,214,190) S 65.0 → S 51.0; RGB(246,200,178) S 70.0 → S 59.0. R is compressed, G/B are not, chroma leaves | A, F | Per-layer, pre/post: mean S inside the **matte** must not drop >10 % across any tonal operation. Ratio, measured on the layer, not the canvas |
| **D3** | Rainbow colour on a near-white collar (neutral pixel out at S 102) | The "vibrance" formula `sat * (1 + k*(1 - sat/255))`. The multiplier is **largest where saturation is lowest**. Measured today at k=0.5: gain ×1.500 at S=0, ×1.108 at S=200. Iterated, a pixel at **S=2 reaches S=238.7 in 16 passes**. Present at `v2.py:168`, `build_glow.py:178`, `:226`, `:280` — and **still live at `v3.py:352`**, inside a 40-iteration background loop. `build_glow.py:161-163` carries a comment claiming the formula "scales WITH existing saturation"; the code 15 lines below does the opposite. **The fix was written in the docstring and never in the code** | B, F | Neutral-preservation unit test on the transfer function itself, not the image: assert `f(S=0)==0` and that the gain is monotone non-increasing in S. Runs in 1 ms, needs no render |
| **D4** | "weird hairs, smooth where it's not supposed to be smooth" | Pillow ≥12 alpha-premultiplies on `Image.resize` of RGBA: RGB is zeroed where alpha is low. Reproduced today, Pillow 12.3.0, at the operative scale 0.98: max abs ΔRGB = **255**, flat-plateau fraction 0.49 % (no resize) → **42.20 %** (resized). Was in `build.py:83`, `v2.py:125`, `build9800.py:128`, `build_audit.py:105`, `build_glow.py:188`. Fixed at `v3.py:165` `resize_rgba` | C | Golden-value test on the library: resize a synthetic RGBA gradient, assert RGB is bit-identical to resizing the RGB band alone. Pin the assertion, not the Pillow version |
| **D4b** | *(correction to the record)* | The "41.68 % flat plateaus landing exactly on the hair" number is measured over the **whole tile including the fully-transparent region**, which is 89 % of the damage and is invisible. Measured by alpha band today: α<8 → 89.1 % of pixels damaged >32 codes (irrelevant); α 8-63 (the hair) → 40.6 %; α 64-191 → 7.7 %; α≥248 → **0.0 %**. Real harm: **727 of 8,279 soft-band pixels**. The fix is right; the number that justified it overstates it ~50× and is the same measurement-domain error as D22 | D | Report the metric restricted to the pixels that are actually composited (`8 < α < 248`) |
| **D5** | "background is all weird / not surgical / too dark" | `v2.py:56-60`: `cv2.resize` to **628×348**, `cv2.inpaint(TELEA)` there, `INTER_CUBIC` back to 2512×1392, then `GaussianBlur(9)`. A 4× downsample before inpainting means the detail was destroyed before the inpaint ever ran. Same pattern at `build.py:55-60`. Result: bg detail 785.8 vs reference 2464.7 | A | Masked Laplacian variance of the background region against the **untouched source plate at final scale**, ratio ≥0.6 — normalised for luma gain (see E/G1) |
| **D6** | **The same woman appears twice**, and "in the middle between them it doesn't even really make sense" | `v3.py:63-93` `background()` deliberately removed the inpaint (correct) but nothing replaced the requirement that her old position be covered. Re-measured today: original silhouette 123,625 px on canvas, **77,570 px (62.7 %) uncovered**, bbox **x405-763 y263-719** — dead centre, exactly the region he complained about. `v3.py:327-329` writes it to `facts["original_uncovered_px"]` and prints it. **`verify_v3.py` never reads that key.** Measured, logged, shipped | D, G | `assert facts["original_uncovered_px"] <= 0.02 * original_area` in the build, **and** a gate that reads it. Stronger: template-match the placed subject's face crop against the rest of the frame and fail on a second peak >0.7 |
| **D7** | Colour blotches on both faces | `v3.py:375` `solve_sat(ga, face_S_source*0.92, mask=sub_soft, iters=14)`. `k` is clipped to 1.18 (`v3.py:123`) and 14 iterations compound to **×10.1**. It never converges, because of D22 | A, D | Cap **cumulative** gain, not per-iteration gain, and fail the build if the solver exits on iteration count rather than on tolerance |
| **D8** | Gates said 13/13 while the image was visibly broken | Three separate mechanisms, all still present: (i) the gates that could fail are wired to the wrong artifact (D13); (ii) five of the fifteen are tautologies or cannot-fail (see E); (iii) **the build never runs the gates** — `v3.py` has exactly one assertion, `:387`, for type overlap. The verifier is a separate script a human must remember to run | D, G | The build calls the gates and refuses to write the JPEG on any FAIL. A gate that is not in the build's exit path is documentation |
| **D9** | Gates authored badly | Confirmed and enumerated in section E. Concretely: `verify_v3.py:59,62,63` compute `bg_detail`, `frame_detail` and `S` thresholds "measured off HS_REMAKE" that **no gate ever references** — dead decoration. `verify_v3.py:56` compares a 140×260 patch (36,400 px, sd 80.9, detail 2464.7) against our 432,239-px scattered background. `verify_v3.py:129` invents `<= 14.0 %` — HS_REMAKE's own top third measures **13.1 %**, so the "measured" threshold is the reference plus 0.9 with no stated derivation | D, E | Every threshold must name the file, the region and the statistic it came from, in code, as data — not in a comment |
| **D10** | Colours targeted at a screenshot of his HDR monitor | `build_glow.py:127` still prints `(phone target L146.1 S32.1 a-0.9 b+6.6)` next to the file-derived `BG_TARGET L130.2 S38.1 a3.1 b7.8` (`:94`). A 15.9-point luma and 6-point saturation error baked into a target | F | Any reference number must carry the file path it came from. Assert the source is a file this repo can re-open and re-measure |
| **D11** | **The arrow points at the ghost, not at her** | `v3.py:388` targets `(DEF_C[0] + 200, DEF_C[1] - 10)` = (500, 382) — a hardcoded offset 200 px right of her placed face. Her duplicate happens to sit at x405-763, so the arrow lands on the copy. Visible in `DEFECT6_ghost_silhouette.png`. Direct violation of R3 ("a ray cast from the tip must strike the defendant") and R27 | E, G | R3's own check, on the rendered file: cast a ray from the arrow tip and require it to strike the **placed** subject matte |
| **D12** | — (latent) | `verify_v3.py:13` `IMG = "V3_4046.jpg"`. Two of the three deliverables, `V3_4026.jpg` and `V3_4058.jpg`, are **never gated at all** | D | The runner takes the output set, not one filename, and fails if any member is missing |
| **D13** | — (latent, and it is why D8 was possible) | `v3.py:406` and `:394` write `v3_facts.json` and `v3_bgmask.png` **once per key, last write wins**. The loop order is `("4046","4026","4058")` → both files describe **4058**, while `verify_v3.py` grades **V3_4046.jpg**. Proved today by reconstructing each judge matte: the shipped `v3_bgmask.png` matches judge 4058 with **0.00 %** leakage and 4026/4046 with **11.55 % / 11.89 %**. So G1/G2/G3/G13 measure ~29,000 px of **Judge Boyd's face and robe** as "background", and G12's `defendant_face_S` is 4058's number scored against 4046's pixels | D, G | Per-image sidecars keyed to the output filename; the gate refuses to run if `facts["source"] != image_path` |
| **D14** | — (latent) | `verify_v3.py:245` iterates **15** gates; `:252` prints `f"{13 - bad}/13 met"`. Run today: 1 failure printed as `12/13 met`. G16 exists in code and is **absent from `GATES.md`**; G11 is in `GATES.md` and is not in the runner list | D | Derive the denominator from the list. Assert the code's gate set equals the ledger's gate set |
| **D15** | Highlights lose colour, skin goes waxy | The knee at `v3.py:224` and `v3.py:360` (and `build9800.py:237`, `build_audit.py:91`, `build_glow.py:253`, `:286`) compresses **each RGB channel independently** above a threshold. Live, and `v3.py:357` runs it **6 times** per build. Measured: −11 to −14 S on skin highlights | A, F | Apply the knee to luminance and rescale RGB by the luminance ratio — the same shape `lift_luma` at `v3.py:128` already uses. Gate: mean S of pixels above the knee, before vs after |
| **D16** | — | D3's inverted formula is **still in the shipping build**, `v3.py:352`, inside a 40-iteration loop over the background | B | as D3 |
| **D17** | — | `G12_FAIL defendant face S 48.4 vs source 86.3 (need >= 70 %)` today, on the current file. The desaturation regression the gate exists to prevent **has already returned**, and the file is still on disk as the deliverable | D, G | as D8 — the build must not produce an output that fails a gate |
| **D18** | — | `build.py` cannot run: `free_space_arrow` undefined, and `place()` at `:79` takes 9 parameters while `:214` calls it with 7. The file was edited in place *after* it shipped A/B/C, leaving neither a working old version nor a working new one | E | Nothing ships from a file that does not import |
| **D19** | "you need to actually regenerate the picture" (R28) | Order is specified as HYPIR → Qwen → cut → composite → grade. `v3.py:22` says **"HYPIR only."** in the docstring. `qwen.py` sits unused in the directory. A stated hard rule was dropped, and declared only in a comment | F, G | R28's own stated check: assert both stages ran on every person layer and log the tile sizes |
| **D20** | "it shouldn't be something set but chosen based off of what you have to work with" (R27) | `v3.py:34-39`: `FACE_H = 300`, `DEF_C = (300,392)`, `JUD_C = (990,392)`, `CROP`, `SUB_FACE`, `JF` — every position is a constant. D11 is the direct consequence | E, G | Solve positions from the frame's own content, and **print the derived value with the two edges it came from**, per R27 |
| **D21** | — | `build_glow.py:49-72` keeps a 24-line `de_mic()` that `:75-77` documents as producing "a blocky grey smear that read worse than the real mic", and never calls it. Dead code retained next to live code | E | — (hygiene) |
| **D22** | why D7 needed 10× | `solve_sat` at `v3.py:117` measures over `sel = mask > 0.5` — the whole blurred **body** matte — but `v3.py:375` gives it a target derived from her **face box** (`facts["defendant_face_S_source"]`, `v3.py:306`). Driving a body mean to a face number is unreachable, so the solver runs all 14 iterations at the clip | D | The measurement region and the target region must be the same region. Assert it in the solver's signature |
| **D23** | **the wrong defendant shipped** (prior session) | `HANDOFF-2026-08-29.md:24-36`: a PALE guard in `thumb_Q3_detail.py:~1109` calibrated on the old saturated pipeline refuses her layer; `make_thumbnail_auto.py` treats `LAYER REFUSED` as retryable and walks to the next cached plate; the cache key `<case>_plate_<time>.png` carries **no case check**. Then `thumbdoctor diagnose` scored it **SHIP 94.2/100, no defects** | A, D, G | Identity assertion: the composited face must match a reference crop of the correct defendant above a fixed similarity, and the plate cache key must contain a content hash of the source hearing |

---

## B. MISTAKE CLASSES

Six classes account for all 23. Ordered by damage done.

### Class A — Correction stacked on correction
A complaint is answered by adding a **new global operation at the end of the
pipeline**, which perturbs everything the previous operations had settled. The
signature is a loop that exists only to undo the loop before it.

`v3.py` build order, verbatim from the code: grade the background to a target
(`:81-87`) → composite → `match_reference()` re-grades the whole frame (`:333`)
→ a 40-iteration loop **re-seats the background** because the re-grade moved it
(`:341-353`) → a 6-iteration "settle" loop alternating knee, contrast, luma and
background because *those* now fight (`:357-369`) → a 14-iteration saturation
solve on her layer because the knee took her chroma (`:375`). **Five corrective
stages, four of which exist only to repair the previous one.** The comment at
`:354-356` admits it: "The knee, the contrast target and the background target
all move each other, so alternate them until they stop moving."

Cost: D2, D5, D7, D15, D23.

### Class B — The fix written in the comment, not the code
`build_glow.py:161-163` documents the corrected vibrance formula in a comment;
`:178` implements the broken one. `v3.py:66-70` documents why the inpaint was
removed; nothing implements the coverage requirement that removing it created
(D6). `build.py:155` implements the corrected arrow solver; `:225` still calls
the deleted one.

Cost: D3, D16, D6, D1, D18.

### Class C — Library behaviour assumed rather than probed
Pillow's RGBA resize was used in five consecutive builds without one line of
verification. It takes four lines to check, and it was never checked. `cv2.inpaint`
was applied at 1/4 resolution on the assumption it would upscale back.

Cost: D4, D5.

### Class D — Measured, then ignored; or measured on the wrong region
The most expensive class, because it manufactures false confidence.
- **Measured and ignored:** `original_uncovered_px = 77570` printed to the log
  and written to JSON, never gated (D6). `G12_FAIL` today, file still on disk (D17).
- **Measured on the wrong region:** solver measures a body, targets a face (D22).
  Gate measures a 36,400-px ceiling patch, compares a 432,239-px background (D9).
  Defect metric measured over transparent pixels (D4b). A prior session compared a
  face box in one image to a mostly-background box in another — `verify_v3.py:145-147`
  records this as already-known.
- **Measured on the wrong file entirely:** D13.

Cost: D6, D7, D8, D9, D12, D13, D14, D17, D22, D4b, D23.

### Class E — Ordering and z-order treated as incidental
Whether the arrow goes on before or after the type is a **rule**, not an
implementation detail, and it is expressed nowhere except the sequence of
statements at the bottom of `build()`. Same for "the background must be rebuilt
when geometry changes" (R30) — expressed only by `background()` happening to be
called before `place()`.

Cost: D1, D11, D18, D20, D21.

### Class F — Provenance lost between generations
A number is derived once, copied into the next build, and its origin decays into
a comment: the "phone target" at `build_glow.py:127`; `BG_REF` drifting
L130.2/S38.1 (v2, build_glow) → L127.7/S46.8 (v3) with no record of which is
right; three thresholds computed at `verify_v3.py:59-63` and never used; R28
dropped in a docstring.

Cost: D2, D3, D10, D15, D19.

### Class G — No enforcement in the build's exit path
`v3.py` writes the JPEG at `:391`. Nothing between `:377` and `:391` can stop it
except the single R1 assert at `:387`. Every other rule is checked, if at all, by
a script a human runs afterwards, on one of three files.

Cost: D1, D6, D8, D11, D12, D13, D17, D19, D20, D23.

---

## C. STRUCTURAL DIAGNOSIS — why every new instruction breaks something already working

He is describing a real property of this code, not a memory problem.

**1. Every operation is global; every requirement is local.**
His requirements are per-object: *her* skin colour, *Boyd's* white balance, *the
room's* brightness, *the type's* brightness. But `match_reference` (`v3.py:210`),
the settle loop (`:357`), the knee (`:360`) and `solve_sat` with `mask=None`
(`:117`) all operate on the **whole canvas**. There is therefore no operation in
the pipeline that can change one requirement without changing all of them. Fixing
her skin necessarily moves the room; fixing the room necessarily moves her skin.
The masks bolted on later (`soft` at `:338`, `sub_soft` at `:374`) retrofit
locality onto operations designed global, and they are applied *after* the global
pass has already done the damage — so they are corrections, not controls.

**2. Every target is a mean, and the means share pixels.**
`REF["luma"]`, `REF["sd"]`, `BG_REF["L"]`, `BG_REF["S"]` and
`defendant_face_S_source` are scalar means over **overlapping** regions. Frame
luma includes the background; background luma includes the ceiling; her face S is
a subset of the frame S. Driving any one to target necessarily moves the others.
That is the literal, mechanical reason the code contains three nested convergence
loops (`:341`, `:357`, `:375`) and still does not converge — G12 is off by 44 %.
There is no fixed point, because the targets are over-determined on
under-determined controls.

**3. Corrections are appended, so the pipeline grows monotonically.**
Nothing in this code has ever been *removed* in response to a complaint; the
response is always another stage. `v2` had 2 grading stages; `build_glow` had 4
(`grade`, `lift_faces`, `match_reference`, `recover_highlights`); `v3` has 5 plus
3 loops. Each addition makes the next addition's effect harder to predict, so
each round of feedback needs a larger correction, which perturbs more. This is
the mechanism behind "everything I tell you leads you further away."

**4. Measurement is downstream of the composite, so blame cannot be assigned.**
Every check reads the flattened JPEG. Once the layers are flattened there is no
way to attribute a bad number to a layer, so the response is another global
correction (goto 1). The one gate that *does* measure per-layer, G12, is the one
gate currently failing — because it is the only one looking in the right place.

**5. State is a directory, not a value.**
`v3.py` reads `plate_surgical.png`, `plate_smoothed.png`, `judge_{k}_surgical.png`
and `arrow_9800.png`, and writes `v3_facts.json` and `v3_bgmask.png` — all by bare
filename, into a shared folder holding five generations of output. `verify_v3.py`
reads those same bare names. There is no binding between an output image and the
facts that describe it, which is exactly how D13 happened. Regression is the
default because nothing in the system *knows* which artifact any number belongs
to.

**6. The rules live in prose; the pipeline lives in statement order.**
`NATHAN_RULES.md` holds 33 rules; 9 are explicitly marked NOT AUTOMATED, and of
those claimed automated, several are checked by scripts (`verify_set.py`,
`kill_hotspots.py`) that `v3.py` never calls. A rule that exists only as a
paragraph regresses the moment the paragraph is not re-read — and he is the one
re-reading it. He is right that he became the regression test.

---

## D. ARCHITECTURE VERDICT — what a correct build looks like

He is right: start over. Do not port `v3.py`. Port `mattes.py` (it is sound) and
the measured constants, and nothing else.

### The invariant
> **One dimension, one owner, one place it is decided. A function may read any
> number of dimensions and must write exactly one.**

Everything below follows from that.

### Layers as values, composite once
```
Layer = { rgb:    float32 [h,w,3]   # float from load to save, one uint8 at the end
          alpha:  float32 [h,w]
          origin: str               # source file, hearing id, which restore stage
          role:   'room' | 'subject' | 'graphic' }
```
There is exactly **one** `composite(layers) -> frame`, called **once**, at the
end. Nothing reads the composite and writes back into it. That single rule
deletes Class A: there is no "after the grade" for a correction to be appended to.

### Function boundaries — each writes one dimension

| Function | Reads | Writes | May not touch |
|---|---|---|---|
| `load_plate(hearing) -> Plate` | disk | pixels + `origin` | anything |
| `matte(plate) -> alpha` | plate | **alpha only** | rgb |
| `solve_layout(subjects, frame_size) -> Placement` | matte bboxes, face boxes | **geometry only** (scale, x, y) | colour |
| `white_balance(layer, ref_ab) -> Layer` | layer + one reference a*/b* | **a\*, b\* only** | L, alpha, geometry |
| `match_luma(layer, target_L) -> Layer` | layer + one target | **L only**, RGB rescaled by the L ratio | a*, b*, alpha |
| `set_chroma(layer, target_S) -> Layer` | layer + one target | **S only**, luminance-preserving | L, hue, alpha |
| `render_type(frame_size, copy) -> Layer(graphic)` | copy, font spec | its own pixels | the photograph |
| `solve_arrow(placement, type_mask) -> Layer(graphic)` | geometry + masks | its own pixels + position | the photograph |
| `composite(layers) -> Frame` | all layers | the frame | — |
| `gate(frame, layers, placement) -> Report` | everything | **nothing** | — |

`white_balance` cannot move brightness. `match_luma` cannot move colour.
`set_chroma` cannot move brightness. This is enforced by what each function is
allowed to return, and asserted: after `set_chroma`, `abs(ΔL) < 0.5`; after
`match_luma`, `abs(Δa*) < 0.5 and abs(Δb*) < 0.5`. **Changing one dimension
cannot silently move another, because the function that changes it does not have
the other dimension in its return value.**

### Order of operations — one pass, no loops
```
 1. load_plate(hearing)                        # provenance stamped here, once
 2. restore = hypir(plate); regen = qwen(restore)      # R28, both, asserted
 3. alpha   = matte(regen)                             # mattes.py, unchanged
 4. layers  = split(regen, alpha)                      # room / defendant / boyd
 5. place   = solve_layout(layers, (1280,720))         # R27: derived, printed
 6. room    = rebuild_room(plate, place.crop)          # R30: at FINAL geometry
 7. per layer, in this order, each exactly once:
        white_balance(layer, ref_ab = defendant_plate) # R31, Boyd only
        match_luma  (layer, target = per-layer target) # R31
        set_chroma  (layer, target = per-layer target) # R32
 8. frame   = composite([room, boyd, defendant])       # ONCE
 9. type    = render_type(...); arrow = solve_arrow(place, type.mask)
10. frame   = composite([frame, arrow, type])          # arrow UNDER type, always
11. report  = gate(frame, layers, place)
12. if report.failed: raise — the JPEG is not written
```

What each line buys:
- **Step 7 has per-layer targets, not one frame target.** The frame's luma is then
  whatever it is. If he wants the frame darker, that changes the *room's* target —
  one number, one layer — and her skin cannot move as a side effect. This single
  change prevents D2, D7, D15 and most of D5.
- **Step 9/10 put the arrow before the type in the composite list**, so z-order is
  a data fact rather than a line-ordering accident (D1, D11).
- **Step 6 is inside the same run as step 5**, so R30 is structurally true rather
  than a rule someone must remember.
- **No loop anywhere.** If a target is not reachable in one pass, that is a
  *finding to report*, not something to iterate toward. Every convergence loop in
  this codebase is a symptom of an over-determined target set (C.2).
- Float from step 2 to step 12. One `uint8` quantisation, at the write.

### Change protocol — what he actually asked for
He said: *"You need to completely start over when making the thumbnails, not try
to edit over them over and over."* That is a build-system requirement, not a mood.

- Every build runs from `load_plate` with a **spec** — a dict of targets and copy.
  A change to the spec is a **new full build**, never a mutation of an output.
- The spec is a file. Diffing two builds means diffing two specs, so "what did you
  change" has a literal answer.
- The 2026-08-29 handoff's advice ("edit `WORKING.jpg` pixel by pixel, do NOT
  re-run the builder") is the correct *tactical* response to a builder that
  re-decides forty things per run. It is the wrong *architecture*. A build that
  re-decides forty things is the defect; the fix is a build where one spec key
  moves one thing.

---

## E. GATE CRITIQUE — 15 gates: 2 sound, 4 salvageable, 9 theatre

Run today against `V3_4046.jpg`:
`G1 G2 G3 G4 G5 G6 G7 G8 G9 G10 G13 G14 G15 G16 PASS`, **`G12 FAIL`**,
printed as `12/13 met`.

### Sound
- **G12** — defendant face S vs source S; a ratio, per-layer, on the rendered
  file. The only gate that measures the right quantity in the right place with a
  derived threshold. It is failing. **It was ignored.** A sound gate that does not
  block the write is worth nothing.
- **G11 (selftest)** — a real negative control, and it passes honestly. But it
  proves only that G1/G2/G4 reject blur+darken. It says nothing about the other
  twelve, and it derives its bad input from the output under test.

### Salvageable
- **G1** — right idea (background detail vs the untouched plate at final scale),
  two flaws. (i) Laplacian variance scales with the **square** of a luma gain, so
  brightening inflates the ratio; normalise by mean luma. (ii) It uses the
  cross-wired `v3_bgmask.png`, so ~29,000 px of Judge Boyd count as background
  (D13). Fix both and it is a good gate.
- **G5** — luma and sd against the reference frame is legitimate, and the comment
  at `:98-102` explaining why frame-mean S is *not* gated is the best reasoning in
  the file. Weakness: our frame carries a large glowing title the reference does
  not; measure on the photograph, excluding graphics.
- **G9** — checks a real rule, but only the **bottom** edge (`bottom_clear`). R29
  is about every edge inherited from the source tile boundary. Extend to all four.
- **G14** — derived from geometry rather than invented, but derived from hardcoded
  constants, so it only re-checks arithmetic the build already did.

### Theatre
- **G7** — *cannot fail*. `v3.py:387` already asserts `hit == 0` and crashes the
  build. The gate then reads the fact written by the code that just proved it. It
  can only ever run when it would pass.
- **G8** — *cannot fail*. `d.h` and `b.h` both come from `FACE_H = 300`; the `cx`
  values are `DEF_C[0]=300` and `JUD_C[0]=990`. The gate asserts `300 == 300` and
  `300 < 990`. Two compile-time constants compared at runtime.
- **G6** — measures **the matte file**, upstream of every defect it claims to
  cover. D4 destroyed the hair *after* the matte; G6 reads 2.40× and passes. Its
  baseline is the same pipeline's other output (guided filter vs
  `post_process_mask`), so it cannot fail while guided filtering is switched on.
  And it covers only the defendant — Boyd's matte is never checked.
- **G13** — *structurally blind to the defect it was written for*.
  `verify_v3.py:137-139` tests `bright & bg_mask & ~halo`. The rainbow collar is
  **on Judge Boyd**, therefore inside the subject matte, therefore excluded from
  `bg_mask` by definition; the 61×61 dilation then removes another 30-px ring
  around every subject and glyph. It also returns `True` when it has fewer than
  200 pixels to test — a gate that passes on absence of data.
- **G15** — wrong metric. Exact 3×3 flat plateaus in **grayscale** cannot see
  chroma blotching. Measured today it reads 1.36 % / 2.04 % against a 3.00 % limit,
  on faces that are visibly mottled (see `DEFECT6_ghost_silhouette.png`).
- **G16** — *cannot fail by construction*. `lim = max(max(ref)*1.8, 12.0)` =
  **35.0 %** — i.e. 80 % worse than the reference is acceptable, with a 12 % floor.
  Ours reads 9.6 / 18.9, **below** the reference's own 17.8 / 19.4. The gate would
  pass a face nearly twice as broken as the bar it was written from.
- **G2 / G3** — a 140×260 patch of a different room region (36,400 px, sd 80.9)
  used as the target for a 432,239-px scattered mask, with invented tolerances
  (±14 luma, ±16 S) and the wrong mask file (D13). `verify_v3.py:47-48` states in
  its own docstring that this patch is *not* an honest yardstick, then uses it.
- **G4** — reads **177 %** today. It rewards adding ink: the title's stroke and
  glow raise Laplacian variance. It can only fail on blur, which G1 already covers.
- **G10** — the `<= 14.0` threshold is invented. HS_REMAKE's own top third is
  **13.1 %**. The gate permits the reference plus 0.9 points, derivation unstated.

### Missing — the gates that would have caught D6 and D8

**G17 — duplicate-subject / ghost silhouette** *(catches D6)*
```
uncovered = (original_silhouette_on_canvas & ~placed_subject_matte).sum()
FAIL if uncovered > 0.02 * original_silhouette.sum()
```
Today: 77,570 / 123,625 = **62.7 %** → hard FAIL. The number already exists in
`v3_facts.json`; nothing reads it. Stronger companion: normalised template-match
of the placed face crop against the rest of the frame, FAIL on a second peak >0.7 —
this also catches the R18 "two Judge Boyds" failure mode.

**G18 — the arrow strikes the subject** *(catches D11, and R3 as written)*
Cast a ray from the arrow tip along its axis; it must intersect the **placed**
subject matte within 400 px. Zero overlap is necessary and not sufficient — R3
already says this, and it was never implemented.

**G19 — gate-set integrity** *(catches D8 and D14)*
- the runner's gate list == the gate list in `GATES.md` (today: 15 vs 14; G16
  missing from the ledger, G11 missing from the runner);
- the denominator is `len(gates)`, not a literal (today `12/13` for 15 gates);
- **every key written to the facts sidecar is consumed by at least one gate** —
  today `original_uncovered_px`, `soft_alpha_px_smoothed` and `mic_row_y` are
  written and `original_uncovered_px` is never read; that unread key *was* the
  defect;
- **every gate has a negative control that makes it fail.** A gate with no
  reachable failing input is deleted, not shipped. G7, G8 and G16 have none.

**G20 — artifact binding** *(catches D13, and the wrong-defendant D23)*
The facts sidecar records the output path and a content hash of every source it
consumed. The gate refuses to run if they do not match the image it was handed.
Today `v3_bgmask.png` matches judge 4058 at 0.00 % leakage while the graded image
is 4046 at 11.89 % — three lines of check would have caught it.

**G21 — mid-scale chroma mottle on faces** *(catches D7, which G15 and G16 both miss)*
Prototyped and validated today. Band-pass the a* channel (σ 6 minus σ 40) inside
each detected face, take the std:

| file | face a* mottle |
|---|---|
| HS_REMAKE (reference) | 3.10 / 1.59 |
| V3_4046 (current) | **5.51** / 2.14 |
| GLW_4046 | 5.88 / 4.61 |
| AUD_4046 | 7.10 / 5.33 |
| S_4046 | **11.33** / 8.77 |

Monotone across the known-bad generations, and it separates the reference from
every build we made. Threshold `max(ref) * 1.3 ≈ 4.0` fails all five of ours,
correctly. This is what "the faces look blotchy" measures as.

**G22 — build-blocking**
The gates run inside `build()`. A FAIL raises before the JPEG is written. Every
gate runs on **every** output, not on one hardcoded filename.

**Also missing entirely:** a check for R28 (both restore stages ran), R16 (the
quote is verbatim in the transcript), and R23 (the rendered cap height, stroke and
sampled fills match the Audit spec). All three are stated rules with no runnable
check anywhere in this pipeline.

---

## Evidence index

| claim | how it was re-measured today |
|---|---|
| arrow-on-type 52.9–57.7 % | reproduced `build.py`'s title mask, intersected with pure-red ink in `A_/B_/C_*.jpg` |
| ghost silhouette 62.7 %, x405-763 y263-719 | replicated `v3.py` `place()` geometry; rendered to `sanchez/DEFECT6_ghost_silhouette.png` |
| bgmask describes 4058 (0.00 % vs 11.55/11.89 %) | reconstructed each judge matte at final placement, intersected with `v3_bgmask.png` |
| vibrance gain ×1.500 @ S=0; S=2 → 238.7 in 16 iters | direct evaluation of the transfer function |
| per-channel knee −11 to −14 S | evaluated `v3.py:224`'s knee on three skin values |
| Pillow RGBA resize, ΔRGB 255, 0.49 → 42.20 % | Pillow 12.3.0, the defendant cut-out, seven scale factors |
| damage by alpha band (α 8-63 → 40.6 %) | per-band diff of the two resize paths |
| `G12_FAIL`, `12/13 met` for 15 gates | `python verify_v3.py` |
| HS_REMAKE top third 13.1 %; G2/G3 patch 36,400 px sd 80.9 | direct measurement of `HS_REMAKE.jpg` |
| G21 mottle table | YuNet faces + a* band-pass σ6/σ40 across five generations |
| `build.py` unrunnable | AST scan: `free_space_arrow` called, never defined |
