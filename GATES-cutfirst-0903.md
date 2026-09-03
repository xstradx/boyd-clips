# GATES — cut out FIRST, then upscale, then colour (2026-09-03)

His instruction, verbatim: *"whatever your process is is when you cut out the
defendant and the judge like whatever your processes is like it's not right, so
what I would probably say what you need to do is cut them out put them there or
cut them out actually upscale them with the HYPIR or whatever else whatever
thing you had and then once they're upscale, go ahead and color them in those
examples that I showed you on that screenshot"*.

So the order he wants is **matte → HYPIR → colour**. What runs today is
**HYPIR → colour → matte**, which means:

- the matte is computed on a RESTORED image, so the alpha is traced around
  whatever HYPIR invented at the hair edge rather than around the real hair;
- the colour correction measures and moves the WHOLE rectangular crop,
  background included, and only the face's skin pixels steer it.

MEASURED BEFORE BUILDING (the defect he is pointing at, PACE judge, current
order): in the hair band mean alpha **61 of 255** and only **23% of hair pixels
fully opaque** — three quarters of her hair is being made transparent.

Scope: add the `matte -> hypir -> colour` path, measure it against the current
order on the same cases, and keep whichever the numbers and his eye support.
No posting in this pass.

OWNS: `tools/thumb_pipeline.py` (the subject stages), `tools/cutfirst_probe.py`,
`D:/Boyd Clips/thumbwork/_CUTFIRST/**`.

## Gates

- [ ] **G0 — the oracle is proven before any of it is trusted.**
  The hair/halo metrics must reject a deliberately bad matte (alpha crushed to a
  hard 0/255 cut) and accept the current build, BEFORE they are used to choose
  an order.
  CHECK: `python tools/cutfirst_probe.py --selftest`
  EXPECT: `CUTFIRST_ORACLE_OK`

- [ ] **G1 — the new order exists and runs end to end.**
  CHECK: `python tools/thumb_pipeline.py PACE --work D:/Boyd Clips/thumbwork/_CUTFIRST/PACE --cut-first --out .../PACE_CUTFIRST.jpg`
  EXPECT: `GATES PASS` and `BUILD_GATES PASS`

- [ ] **G2 — the hair survives.** Mean alpha in the hair band and the fraction
  of fully-opaque hair pixels, both orders, same case, same band.
  CHECK: `python tools/cutfirst_probe.py --compare PACE`
  EXPECT: the cut-first hair numbers are no worse than the current order's, and
  the actual numbers are printed for both — a regression here is reported, not
  hidden.

- [ ] **G3 — no halo.** The ring immediately outside the silhouette must not be
  lighter than the plate it sits on.
  CHECK: same command
  EXPECT: `halo_dL` printed for both orders; cut-first not worse.

- [ ] **G4 — the colour still lands in his band, measured under the alpha.**
  EXPECT: skin chroma 16.5–25.6 for both subjects, and the correction measured
  on subject pixels only (never on the background rectangle).

- [ ] **G5 — nothing else broke.**
  CHECK: `python tools/selftest_all.py` and `python tools/check_rules_refs.py`
  EXPECT: `ALL_OK` from both.

- [ ] **G6 — both cut-outs read at 100% before he sees anything**, side by side
  at the same scale, plus the 168 px feed sheet.
  MANUAL.

## Outcome

MET G0 - `CUTFIRST_ORACLE_OK`. Both metrics reject their known-bad: soft-edge
22.06% (soft hair) vs 0.00% (hard 0/255 cut); halo_dL +43.0 (fringe present) vs
+0.0 (absent). The halo control itself was wrong twice before it measured
anything - it painted the fringe where the dilated band never reached, and then
against the soft alpha whose >200 contour sits outside the drawn axes. Recorded
because a control that reads +0.0 for both cases looks like a passing gate.

MET G1 - `--cut-first` runs end to end. GATES PASS on the finished JPEG.

MET G2/G3 - measured, three times, as the order was fixed:

| | judge soft edge | defendant soft edge |
|---|---|---|
| current order (HYPIR -> colour -> matte) | 3.23% | 3.57% |
| his order, first attempt | 11.39% | 15.93% |
| + full-res re-matte on the grey field | 5.70% | 8.49% |
| + my own clamp removed | **4.74%** | **4.44%** |

The first attempt was much worse and the green control made it unmissable: the
alpha is born at 250x320 / 358x378 and everything downstream is 4x bigger, so
the plate showed straight through both heads. Three of my own bugs, in order:
(a) upscaling the small alpha instead of re-matting at full resolution;
(b) leaving the neutral grey of step 2 baked into every partial-alpha pixel -
the fringe was literally the grey I put there, and it is exactly recoverable as
F = (C - (1-a)B)/a; (c) clamping the full-res alpha to a dilated copy of the
small one, which threw away the thin-hair alpha the re-matte exists to recover.

MET G4 - skin chroma 19.2 / 19.0, inside 16.5-25.6, and gate F drift is the
tightest of any build so far (0.2 / 0.4) because the colour is now measured and
applied under the subject's own alpha instead of over a rectangle.

MET G5 - `selftest_all` 36/36 ALL_OK, `check_rules_refs` ALL_OK.

MET G6 - both cut-outs read at 100% over a saturated control field, and both
finished frames read at full size.

**NOT MET, reported not tuned away: gate E on the defendant.** `hair 13.0 cloth
18.5 ratio 0.70` against a 1.4 floor - under his order this subject's cloth edge
comes out SOFTER than his head edge. He is bald at the crown, so the band gate E
calls "hair" is scalp skin (a hard edge) while the band it calls "cloth" is a
t-shirt shoulder. The same gate passes the same person under the current order
(1.46), so it is detecting a real difference, not only a bald-subject artefact.
The order is therefore NOT adopted as the default in this pass - it is behind
`--cut-first` until that is either fixed or his eye overrules the gate.

ALSO FIXED, and it applies to every build in either order: the heads-level
assert measured the alpha at 0.4 while `cut()` places the head from 0.502. A
check that measures a different contour than the thing it checks fails builds
that are correct - it refused a cut-first build the placement had levelled to
within 0 px.
