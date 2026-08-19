# GRAPHICS-SPEC.md

**Broadcast 2D graphics for the Boyd cut, built and rendered on this machine.**
Blender 5.0.1, headless, RGBA PNG sequences at 1920×1080/30.

Every number below came out of a command run here. Where something is untested
it says so. Delivered pixels are always read with external ffmpeg, never with
`Image.pixels` (BLENDER-CAPABILITY §4.2).

---

## 0. What exists

```
research/blender/graphics/
├─ boyd_gfx.py            THE KIT. Stage + Elem. Everything else imports this.
├─ gfx_lower_third.py     DELIVERABLE 1
├─ gfx_fact_panel.py      DELIVERABLE 2
├─ gfx_quote_card.py      DELIVERABLE 3
├─ gfx_verdict_card.py    DELIVERABLE 4
├─ make_static_fonts.py   variable-font instancing (see §3) -> fonts_static/
├─ metrics.json           measured per-face cap/x-height/advance table
├─ measure.py             external pixel reader + AA / fringe metrics
├─ sheet.py               contact-sheet helper
├─ probe_00.py            node availability, keyframing, colour, wipe AA
├─ probe_01_fonts.py      font metrics + proof the instancing changed glyphs
├─ probe_02_curves.py     fcurve dump / evaluate (no render)
├─ probe_03_mask.py       x-clip orientation + material animation in -b
├─ probe_04_z.py          z-clip orientation, both directions, and the band
├─ bakeoff_spec.py        one shared lower-third spec
├─ bakeoff_blender.py     implementation A
├─ bakeoff_pil.py         implementation B
├─ bakeoff_ffmpeg.py      implementation C
├─ bakeoff_measure.py     the comparison
├─ alpha_verify.py        RGBA-over-video composite proof
└─ renders/…              1,242 delivered PNGs + composite_test.mp4
```

Run any deliverable:

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.0\blender.exe" -b --python gfx_lower_third.py -- "MARCUS D. BOYD" "MANSLAUGHTER, SECOND DEGREE"
```

---

## 1. VERDICT: is Blender the right tool for this?

**Yes for the wipe-driven graphics, and the margin is smaller than expected.
PIL is the right answer if you only ever need static plates and whole-pixel
reveals. ffmpeg is the wrong answer for all of it.**

Same lower third, same geometry, same easing curve
(easeOutCubic = cubic-bezier(⅓,1,⅔,1), so the three are exact, not approximate),
135 frames at 1920×1080, RGBA PNG:

| | Blender 5.0.1 | Python + PIL | pure ffmpeg |
|---|---|---|---|
| **render time** | 24.06 s (**0.178 s/f**) | **11.45 s (0.085 s/f)** | 24.25 s (0.180 s/f) |
| **code, first graphic** | 200 lines (145 kit + 55) | 82 lines | 101 lines |
| **code, each graphic after** | ~55 lines | ~80 lines | ~100 lines |
| **glyph AA, distinct R levels** | **67** | 32 | 27 |
| **glyph AA, px per edge** | **1.55** | 1.00 | 0.82 |
| **distinct alpha levels/frame** | **43** | 20 | 20 |
| **wipe edge error vs analytic** | **0.021 px mean, 0.030 max** | 0.186 / 0.400 px | 0.349 / 0.770 px |
| **brand colour delivered** | exact¹ | exact | exact² |
| **layout agreement (IoU)** | 1.0000 (ref) | 1.0000 | 1.0000 |

¹ modal colours exactly `#D42B2B` / `#F2EEE3` / `#15181D`; individual pixels vary
±9 because `dither_intensity = 1.0`. Ship with dither on, verify with it off.
² **only after forcing `overlay=format=rgb`** — see §5.

### The number that decides it

The **sub-pixel wipe edge**. Blender's edge lands where the curve says to within
**0.021 px**; PIL and ffmpeg quantise to whole pixels:

```
frame        6       7       8       9      10      11      12
wanted   260.40  363.87  433.23  475.30  496.90  504.86  506.00
blender  260.42  363.90  433.24  475.32  496.93  504.89  506.01
ffmpeg   261.0   364.0   434.0   476.0   497.0   505.0   506.0
pil      260.0   364.0   433.0   475.0   497.0   505.0   506.0
```

Over a 7-frame wipe that is a **sub-pixel judder on every reveal in the video**.
It is invisible on a still and visible in motion, which is the worst way for a
defect to behave. Both alternatives could be fixed by supersampling the clip
(render the mask at 4× and downsample) — at which point their speed advantage
goes away.

Blender also produces roughly **2× the tonal resolution on glyph edges** (67 vs
27–32 distinct levels), because 64 TAA samples supersample the whole shader,
not just the glyph outline. On dark ground under YouTube's compression this is
the difference between clean type and slightly chewed type.

### Where PIL genuinely wins

**2.1× faster, and 40 % less code for a one-off.** If a graphic is a static
plate that fades, PIL is the correct tool and Blender is overkill. The kit only
earns its 145 lines once you want eased sub-pixel wipes, band clipping and
odometer rolls — which is exactly what deliverables 1, 2 and 4 need.

### Why ffmpeg loses outright

It is the slowest **and** the least accurate **and** the most code, and it needed
five workarounds to produce the picture at all (§5). Its one advantage —
no dependency beyond ffmpeg, which the pipeline already has — is not worth it.
**ASS/subtitles was not built**: it cannot express a plate, an alpha wipe, or a
per-element reveal, so it is not a candidate for anything but flat captions.

---

## 2. Alpha: does it composite cleanly over video?

**Yes. Measured max error 0.498/255 — pure rounding — with no directional halo
on any background.**

`alpha_verify.py` composites frame 60 of the lower third over 60-px bands
cycling `#000000 / #808080 / #FFFFFF / #1B4FD8`, then compares ffmpeg's
`overlay` against the analytic straight-alpha composite `out = fg·a + bg·(1−a)`
computed in numpy.

```
partial-alpha pixels          : 27,716
max |error| vs STRAIGHT       : 0.498 / 255      <- half an LSB = rounding
mean |error| vs STRAIGHT      : 0.2619 / 255
mean |error| vs PREMULTIPLIED : 2.6370 / 255     <- 10x worse, so the file is
                                                    STRAIGHT and ffmpeg agrees
signed mean error             : -0.0058          <- no halo in either direction

by background band (partial-alpha px only):
  black  #000000   n=6387   signed mean +0.0218   max|err| 0.498
  grey   #808080   n=4843   signed mean +0.0193   max|err| 0.494
  white  #FFFFFF   n=8374   signed mean +0.0347   max|err| 0.498
  blue   #1B4FD8   n=8112   signed mean -0.0844   max|err| 0.498
```

A premultiplied-treated-as-straight file would show a strong **negative** signed
error against white. It does not. **No fringing.**

The white and blue bands are the ones that matter — a dark halo is only visible
against a bright background — and the first version of this test scored `n=0` on
both because the graphic sits entirely inside the first two quarters of the
frame. Cycling narrow bands fixed it.

Full-sequence path also verified end to end:

```powershell
ffmpeg -f lavfi -i testsrc2=s=1920x1080:r=30:d=4.5 `
       -framerate 30 -start_number 1 -i renders\lower_third\f_%04d.png `
       -filter_complex "[0][1]overlay=0:0:format=rgb:shortest=1[v]" `
       -map "[v]" -c:v libx264 -crf 16 -pix_fmt yuv420p out.mp4
# -> h264,1920,1080,yuv420p,135 frames
```

**Always pass `overlay=…:format=rgb`.** Without it overlay round-trips through
YUV and shifts the brand colours (§5).

---

## 3. The variable-font gap, and the fix

**Blender 5.0 has no variable-font axis API anywhere.** Enumerated live:
`VectorFont` has no axis/variation/weight property; neither does `TextCurve`;
`TextCharacterFormat` exposes only `use_bold` / `use_italic` / `use_small_caps`,
which switch to a *separate font datablock*, not an `fvar` axis.

So `bpy.data.fonts.load()` on a variable font silently gives you its **default
named instance** and there is no way off it:

| file | fvar axes | Blender reports | stem width of `I` @ size 100 |
|---|---|---|---|
| `Montserrat-Var.ttf` | wght 100–900, default **100** | *Montserrat **Thin*** | **1.39** |
| `Archivo-Var.ttf` | wght 100–900 default 600, wdth 62–125 | *Archivo SemiBold* | 8.68 |
| `Oswald-Var.ttf` | wght 200–700, default 400 | *Oswald Regular* | 7.01 |

Montserrat at Thin is a hairline. Using it for a lower third would have been a
silent substitution of the worst kind — it renders, and it looks deliberate.

**Fix:** `make_static_fonts.py` instances the three VFs to nine static TTFs with
`fontTools.varLib.instancer` (fontTools 4.63.0, installed for this). Proven at
the geometry level, not just in the name table — stem width of `I` at size 100:

```
Montserrat-Var (Thin)  1.39      Archivo-SemiCond-SemiBold  8.34
Archivo-Regular        6.43      Archivo-Var (SemiBold)     8.68
Montserrat-Medium      6.69      Oswald-Medium              8.95
Oswald-Regular         7.01      Anton                      9.60
Archivo-Medium         7.53      Bebas Neue                 9.89
                                 Archivo-Bold               9.93
                                 Montserrat-Bold           10.44
                                 Oswald-Bold               10.69
```

A **7.5× stem-weight range** that was previously inaccessible.

> `instantiateVariableFont(..., updateFontNames=True)` raises
> `ValueError: Cannot find Axis Values {'wdth': 87}` — the STAT table has no
> Axis Value record for an off-ramp width. Rewrite name IDs 1/2/4/6/16/17 by
> hand instead.

**Recommendation:** promote `fonts_static/` into `assets/fonts/static/` so the
whole pipeline shares it. Not done here — it is outside this folder.

---

## 4. Blender 5.0.1 findings not in BLENDER-CAPABILITY.md

### 4.1 A shader threshold antialiases exactly like real geometry

The load-bearing finding for the whole kit. Alpha across the edge, `taa=64`,
`filter_size=1.5`:

```
hard shader wipe (feather 0.001) : [0,0,…, 31, 225, 255, 255, …]
soft shader wipe (feather 1.5px) : [0,0,…, 29, 166, 251, 255, …]
TRUE GEOMETRY EDGE (control)     : […, 255, 255, 224,  30, 0, 0, …]
```

A hard shader threshold gives the **same 2-pixel ramp** as a real polygon edge,
because EEVEE's TAA supersamples the shader too. So a wipe costs nothing in edge
quality, needs no deliberate feather (a feather only makes it *softer* than
geometry), and can cut through the middle of a glyph — which object scaling
cannot. Every reveal in the kit is built on this.

### 4.2 `TextCurve.size` is NOT the em square

Measured cap height at `size = 100`, against the value in the font file:

| font | font file cap/upm | Blender cap @ size 100 |
|---|---|---|
| Anton | 0.8594 | **49.70** |
| Bebas Neue | 0.7000 | 62.95 |
| Oswald Regular | 0.8100 | 51.14 |
| Montserrat Thin | 0.7000 | 48.51 |
| Archivo SemiBold | 0.6860 | 45.79 |

Four normalisation hypotheses were tested against all five faces — `upm`,
`hhea.ascender−descender`, `OS/2` typo metrics, `OS/2` win metrics — and **none
fits all of them**. Unexplained. The kit therefore sizes type from the
*measured* ratio in `metrics.json` and does not care what the mechanism is.
FreeType-based renderers (ffmpeg, PIL) *do* size by em, so the same cap height
needs a different number in each tool.

### 4.3 Corrections to BLENDER-CAPABILITY.md

| § | says | actually, on 5.0.1 |
|---|---|---|
| 1.14 | `fill_mode`: `FULL BACK FRONT HALF` | **`NONE BACK FRONT BOTH`**, default `BOTH` |
| 1.14 | (not covered) | `align_y`: **`TOP TOP_BASELINE CENTER BOTTOM_BASELINE BOTTOM`** — there is no `BASELINE`, and the default is `TOP_BASELINE` |
| 1.4 | `prores_profile` | RNA name is **`ffmpeg_prores_profile`** |

### 4.4 `Map Range`'s *From* range must ascend

Writing `from_min=0, from_max=−F` to express "opaque above the edge" is the
algebraically obvious form and **does not work**: a rule that should have been
fully clipped rendered at a flat alpha of 237/255 over its whole height, with no
error. Keep *From* ascending and invert the *To* range instead. Both directions
and the two-sided band are now regression-tested in `probe_04_z.py`:

```
A wipe_z(400) keep y<=400        got y=100..399    expected 100..400
B upper edge 400 keep y>=400     got y=400..699    expected 400..700
C band(300,500)                  got y=300..499    expected 300..500
D control                        got y=100..699    expected 100..700
```

### 4.5 Material node-tree animation IS evaluated per frame in `-b`

Not previously recorded. An edge keyed 300→1300 over 3 frames measured exactly
300 / 800 / 1300. Data path is
`nodes["NAME"].inputs[N].default_value` on the **node tree's** `animation_data`.

### 4.6 Three silent bugs, all of which produced plausible pictures

These cost most of the build time. All three render without error.

**(a) Animating one half of a two-socket range.** `MapRange(from_min=edge,
from_max=edge+F)` needs *both* sockets to move together. Animating only
`From Min` turns the hard clip into a 2280-px gradient: a bar whose edge was set
to x=600 rendered fully opaque from 200 to 1399. **Fix:** subtract first, so a
single socket carries the edge and the MapRange window is a compile-time
constant. The two can then never desynchronise.

**(b) `css_ease` setting all four handles FREE.** `sting_v2.py` has this too, and
it is latent there. Setting both handles of both keyframes to `FREE` leaves the
*far* handle frozen at whatever `AUTO_CLAMPED` computed when the curve had fewer
keys; append a later key and that stale handle swings the next segment. The
charge text vanished for a 100-frame hold whose two endpoints held the identical
value. **Fix:** set only the two handles bounding the segment, plus
`flatten_holds()` to force equal-valued segments dead flat.

**(c) Ease indices counted per-call, not per-curve.** A socket keyed twice
(entrance, then exit) got the exit's easing applied to the *entrance* segment,
because `enumerate(de)` numbers from 0 within the call while the curve already
holds earlier keys. **Fix:** look the segment up by frame.

**(d) Inverted depth.** The camera sits at `y=-1000` looking toward `+Y`, so
nearer means **more negative** y. Getting it backwards reads as a *colour* bug,
not a depth bug: the ink name rendered grey (behind a 93 %-opaque plate) and the
charge vanished entirely (behind a 100 %-opaque one). `Elem.layer(n)` now owns
this; 0 is backmost.

### 4.7 Anton has slab quote marks

`U+201C` in Anton is **14 vertices** — two hard rectangles, not a comma form —
so a large decorative opening quote renders as two red blocks. Vertex count is a
reliable tell: slab quotes 14 (Anton, Bebas), drawn quotes 152–224
(Oswald-Bold 152, Archivo-Bold 154, Montserrat-Bold 224). The quote card uses
Archivo-Bold for the mark only.

Also: `cap=` means **cap height**, and a quotation mark is only ~0.3 of the cap
height, so `cap=132` renders a 40-px mark. Size decorative punctuation against
the H, not against the glyph.

---

## 5. ffmpeg findings (all measured in `bakeoff_ffmpeg.py`)

1. **`drawbox` never writes alpha.** On a transparent `rgba` *or* `argb` source
   it blends colour into RGB and leaves the alpha plane at 0 — measured
   `px(200,100) = #D42B2B` at **alpha 0**, max alpha over the whole frame **0**.
   The box looks perfectly fine previewed on black and is invisible in the
   delivered PNG. Use a `color` source + `overlay`, which does write alpha
   (measured 237 for `@0.93`).
2. **`drawtext` does write alpha** and antialiases well — 133 distinct alpha
   levels on one word.
3. **`overlay` defaults to a YUV format and silently shifts brand colours.**
   Without `format=rgb`: red delivered as `#D3292A` instead of `#D42B2B`, ink as
   `#F1ECE0` instead of `#F2EEE3`. This is ffmpeg's exact analogue of Blender's
   AgX default.
4. **`drawtext` has no letter-spacing.** Tracking needs **one `drawtext` filter
   per character** with advances computed outside ffmpeg. The 27-character
   charge line becomes 27 chained filters; the final graph is 108 filter nodes,
   5,988 characters.
5. **`crop` cannot animate its width** (`w`/`h` are evaluated once at
   configuration time), so a wipe cannot be a crop. It must be `geq` rewriting
   the alpha plane: `a='alpha(X,Y)*lt(X,<edge expr>)'`.
6. **`drawtext`'s `y` is the top of the INK bounding box**, not the line box.
   `y = baseline − hhea_ascent` put caps 16 px too high (ink rows 764..805 where
   Blender and PIL both give 780..821). For all-caps, `y = baseline − cap`. For
   mixed case you would need the tallest ink above the baseline, which ffmpeg
   gives no way to query.
7. **ffmpeg cannot evaluate a cubic bezier**, so easing must be closed-form
   arithmetic.

**PIL finding:** `ImageDraw` does **not** alpha-blend, it **overwrites**. Drawing
a 14 %-alpha hairline straight onto a plate replaced the plate pixels with
`(242,238,227,36)` instead of compositing. Translucent elements each need their
own layer and `alpha_composite`.

---

## 6. The kit

`boyd_gfx.Stage` builds an empty scene with an **orthographic camera whose
`ortho_scale` equals the frame width, so one world unit is exactly one pixel**,
and layout is authored in top-left screen pixels. `Stage.rect()` and
`Stage.text()` return an `Elem`; every `Elem` owns its own material carrying:

* `opacity(keys)` — animated
* `wipe_x(keys)` — horizontal reveal edge, in screen px
* `wipe_z(keys)` / `wipe_z_top(keys)` / `band(y_top, y_bottom)` — two independent
  vertical edges, which is what makes the odometer roll possible
* `slide_y / move_x / scale / layer`

Delivery settings are forced in `Stage.render()`: `film_transparent`,
`color_mode='RGBA'`, and `image_settings.color_management='OVERRIDE'` with
`view_transform='Standard'` — without which AgX ships `#F2EEE3` as `#C0BFBB`.

### Motion constants

Reused from the nine broadcast idents already frame-measured for this channel
(`sting_v2.py` header), not invented here:

* **no overshoot** anywhere — 0 of 7 references with a trackable settle overshoot
* **no motion blur** — the two pure-letterform references render a 3-px edge
  whether moving 31 px/frame or standing still
* **stagger +4…+5 frames**, travel **6–8 frames**
* `EASE_OUT = cubic-bezier(0.33, 1.0, 0.68, 1.0)` — which is easeOutCubic
* 30 fps, matching the channel's longform

### The one design rule that runs through all four

**A reveal must have a cause.** The plate's own leading edge is what uncovers
the text (the text's wipe edge is the plate's edge minus the padding, the same
curve); the fact panel's descending plate edge is what *times* each row in —
the row entrances are read off the plate's fcurve with `fc.evaluate()`, not set
by an independent stagger. That is not decoration: with an independent stagger,
rows lit up *below* the plate edge, in open space, at f10 and f22.

---

## 7. Deliverables, as rendered

All four re-run clean from the current kit in one regression pass (`taa=64`,
CPU EEVEE, RGBA PNG, 1920×1080/30):

| | frames | render | s/frame | notes |
|---|---|---|---|---|
| **1 lower third** | 135 (4.5 s) | **21.6 s** | 0.160 | rule strikes down → plate wipes right → plate uncovers name → tier 2 at +5f → hold 105f → reverse wipe, tier 2 leading by 3 |
| **2 fact panel** | 340 (11.3 s) | **55.7 s** | 0.164 | 5 rows; values roll on an odometer hard-clipped to a 40-px band; accent underline flags the changed row |
| **3 quote card** | 137 (4.6 s) | **25.0 s** | 0.182 | wrap measured in Blender; per-line mask rise, +4f stagger; fades out rather than retracting |
| **4 verdict card** | 150 (5.0 s) | **28.3 s** | 0.189 | plate opens as a band from the centre in 4f on EASE_IN, 11-px frame shake on the landing frame, verdict scales 1.045→1.000 in 3f |

762 frames, 130.6 s total. Scene complexity barely moves the per-frame cost
(0.160→0.189 s across 6 to 40 elements), so cost is dominated by the 64 TAA
samples, not by element count.

Verified closed states: lower third frame 1 = **20 non-zero pixels at alpha ≤ 1**
(i.e. genuinely empty), frame 60 bbox `x117..671 y761..890`, frame 135 empty.

### Parameters that are layout, not mechanism

Type sizes, tracking values, plate alphas and the exact palette assignments in
the four `gfx_*.py` files are all module-level constants and were set to be
defensible, not final. **Typeface selection and type sizing belong to the design
specialist** — the mechanism does not care what they become.

---

## 8. Known limits / not done

* **Motion blur on these graphics: untested.** Deliberate — the measured
  references do not blur letterforms.
* **No GPU.** Every timing is CPU EEVEE on this machine.
* **The fact-panel row band is tight**: at `ROW_H=74` the outgoing value passes
  ~4 px under the label during a roll. It reads correctly and is clipped
  correctly; it would breathe better at `ROW_H=82`.
* **ASS/libass was not built** as a fourth arm — it cannot express plates or
  alpha wipes, so it was ruled out on capability rather than measured.
* **Supersampled PIL/ffmpeg not built.** Rendering their masks at 4× and
  downsampling would close the sub-pixel gap; the speed comparison in §1 would
  then need redoing.
* **`compositing_nodes_essentials.blend` ships a `Rounded Square Mask` node
  group** (parametric rounded-rect matte: `Scale`, `Corner Roundness`, `Feather`,
  `Offset`, `Angle`; appendable headless via `bpy.data.libraries.load`). Not
  used here — the per-object shader clip is more direct and needs no append —
  but it is the route if rounded corners or feathered plates are ever wanted.
* **`StripModifiers.new()` hard-crashes 5.0.1 in background mode**
  (`EXCEPTION_ACCESS_VIOLATION`, reproducible with `--factory-startup`). Any VSE
  strip-modifier route is unavailable headless.

---

## 9. Ryan King Art — what was actually usable

Six videos watched. **Three of six are floor-level and should be rejected
outright.** No video in the set opens the Graph Editor even once, so nothing on
that channel informs easing, cadence or timing — which is most of what makes
these graphics read as broadcast. None of the six touches colour management
either, so none would have warned about AgX.

| video | verdict |
|---|---|
| *Typewriter Text Animation Effect* (2.93) — [4Mva3d_hyZ0](https://www.youtube.com/watch?v=4Mva3d_hyZ0) | The effect is a third-party add-on (doakey3), **not** a Build modifier. It registers `character_count` / `character_start` on `bpy.types.TextCurve` and mutates `text.body` from a `frame_change_post` handler — which is an off-by-one-frame hazard for `-f N` single-frame renders. Usable idea: `obj.data.body = source[:n]` written yourself. Also the **burst-and-hold** keyframe pattern (duplicate a key, slide it right) so a reveal pauses between phrases — the only genuine craft idea in the set. |
| *New Compositing Features in Blender 5.0* — [vPF8Aj20Bqc](https://www.youtube.com/watch?v=vPF8Aj20Bqc) | The most useful. The "new nodes" are **Essentials asset node groups, not new `bpy.types` classes** — a viewer would write `nodes.new("CompositorNodeVignette")` and get a `RuntimeError`. Confirms `Composite` node gone, trees terminate in `Group Output`. `Glare` now has separate `Image`/`Glare`/`Highlights` outputs. |
| *New Compositing Effects in Blender 5.2* — [UhlIT_-3xQM](https://www.youtube.com/watch?v=UhlIT_-3xQM) | One transferable item: **Rim 2D**'s parameter model (outline + independent blur + lightwrap + separate rim output, requires a transparent render), rebuildable in 5.0 from `DilateErode`+`Blur`+`Mix`. `String To Image` is 5.2-only **and has no alpha** — text must stay as FONT objects. |
| *How to Render Transparent Backgrounds* — [GhwUHKLz_5E](https://www.youtube.com/watch?v=GhwUHKLz_5E) | **Reject.** Three facts in four minutes, both already documented here. Scrolls past the Color Management panel twice. |
| *New Compositor Layout in 5.1* — [l2KVmWXgkpQ](https://www.youtube.com/watch?v=l2KVmWXgkpQ) | **Reject.** Workspace layout tour, nothing scriptable. Its one implied claim — that `Group Output` is new in 5.1 — is wrong; probed, it was already true in 5.0. |
| *Cutout a Video with a Custom Mask* (4.5.1) — [L9gFuWv5_04](https://www.youtube.com/watch?v=L9gFuWv5_04) | **Reject.** Static mask, zero keyframes, never opens the compositor, and its VSE strip-modifier route crashes 5.0.1 headless. |

**Honest summary: probing the binary produced more usable mechanism than the six
tutorials combined.** The kit's central technique — a per-object shader position
threshold as the reveal primitive — appears in none of them.
