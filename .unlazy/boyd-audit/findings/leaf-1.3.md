# leaf-1.3 — render path and the six mandatory elements

Scope: `src/boydclips/{render,refine,thumbnail,censor,publish}.py`, the render/thumbnail
scripts, and every finished artifact in `C:\Users\natha\OneDrive\Desktop\Boyd Clips\READY-TO-POST`.
Read-only throughout: measurements use `ffprobe` (including `-f lavfi` analysis graphs,
which write nothing) and PIL/numpy reads. No frame was extracted, no file written except
this one.

### Two retractions of my own working notes

Recorded because both wrong versions were more alarming than the truth, and either would
have sent someone rebuilding six videos for no reason.

**(1) A CSV parsing error.** My first silencedetect probe appeared to show ~20 spans per
threshold and I was one step from filing "STATE.md's headline measurement is false". It was
my parsing that was false: `silence_start` and `silence_duration` are emitted on *different
frames*, so a naive 2-column read counts unpaired values. Correctly paired, STATE.md's
short-clip measurement is right.

**(2) A reversed column order, which cost me my headline finding.** `astats` emits
`Peak_level` before `RMS_level` regardless of the order you request them, so I read a peak of
−36.8 dB alongside an RMS of −15.0 dB — physically impossible, since peak cannot sit below
RMS, and I should have caught it on sight. The true values are Peak −15.04 / RMS −36.81. I had
drafted F1 as a **blocker** claiming "every long-form violates element 2, 6.7–44.7% of runtime
is dead air", measured at a −12 dBFS threshold I picked myself. Tested at the pipeline's own
−30 dBFS definition of silence, **all six long-forms contain zero spans of 4s or more** —
element 2 passes its literal test everywhere. F1 below is the rewritten, defensible version,
and it is a different and smaller finding. My −12 dB threshold was measuring quiet speech:
ROMERO's three longest "spans" peak at −12.0, −13.8 and −14.6 dBFS, i.e. audible content.

### The six-element audit table

Contract = `CLAUDE.md` "Start working on videos means ALL of this" (1 download, 2 dead air
>4s removed, 3 branded sting, 4 watermark on body not intro, 5 Thompson-style 2-up short
with speaker-side captions, 6 house-style graded thumbnail).

| Case | Long-form | dur | pix_fmt / profile | A/V skew | 2 dead air | 3 intro | 4 watermark | 5 short | 6 thumbnail |
|---|---|---|---|---|---|---|---|---|---|
| Thompson | `1_LONGFORM_Thompson.mp4` | 657.70s | yuv420p / High | +0.011s | 0 spans >=4s (PASS on letter); 31.3% silent, longest 3.67s | **WRONG ASSET** sting.mp4 1.4s | unverified | `2_SHORT_Thompson.mp4` 32.9s | **FAIL** flat_chroma 3.70 > 3.5 |
| CARTHIEF | `CARTHIEF_LONGFORM.mp4` | 1002.87s | yuv420p / High | +0.010s | 0 spans >=4s (PASS on letter); 35.5% silent, longest 3.94s | **WRONG ASSET** sting.mp4 1.4s | unverified | `CARTHIEF_SHORT_FINAL.mp4` 34.8s | **FAIL** flat_chroma 89.90 (see F4 — artefact) |
| MONKEY | `MONKEY_LONGFORM.mp4` | 808.93s | yuv420p / High | −0.007s | 0 spans >=4s (PASS on letter); 28.8% silent, longest 3.39s | **WRONG ASSET** sting.mp4 1.4s | unverified | **ABSENT** — no MONKEY short exists | pass, flat_chroma 0.96 |
| OFFERUP | `OFFERUP_LONGFORM.mp4` | 550.30s | yuv420p / High | +0.020s | 0 spans >=4s (PASS on letter); 20.9% silent, longest 3.26s | **WRONG ASSET** sting.mp4 1.4s | unverified | `OFFERUP_SHORT_FINAL.mp4` 41.9s | **FAIL** flat_chroma 5.61 |
| ROMERO | `ROMERO_LONGFORM.mp4` | 419.90s | yuv420p / High | +0.002s | 0 spans >=4s (PASS on letter); 32.3% silent, longest 3.00s | **WRONG ASSET** sting.mp4 1.4s | unverified | **INCOMPLETE** `_CAP` only, no `_FINAL` | **FAIL** flat_chroma 10.39 |
| SANCHEZ | `SANCHEZ_LONGFORM.mp4` | 443.83s | yuv420p / High | +0.035s | 0 spans >=4s (PASS on letter); 19.0% silent, longest 2.24s | **WRONG ASSET** sting.mp4 1.4s | unverified | `SANCHEZ_SHORT_FINAL.mp4` 49.1s | pass, flat_chroma 0.77 |

Element 1 (download) is out of my territory and passes trivially — every case resolves to a
`work/<id>/...mp4` in `config/cases.json`. Element 4 is a labelled unknown, not a pass: see F6.

Score: **0 of 6 cases satisfy all six** — but element 2 is not the reason. Measured at the
pipeline's own −30 dBFS silence definition, every long-form passes the literal "no dead air
over 4s" rule (longest contiguous span 2.24s–3.94s, all under the line). What every long-form
*does* carry is 19.0%–35.5% of total runtime as silence in sub-4s pieces, which the rule does
not catch — see F1. The universal, unambiguous failure is element 3 (wrong intro asset, all
six) and element 6 (4 of 6 thumbnails fail the project's own gate).

### Where the pix_fmt scare landed

STATE.md warns four captioned shorts once shipped as High 4:4:4 Predictive. **Refuted for the
current set** — all 21 mp4s in READY-TO-POST measure `pix_fmt=yuv420p`, `profile=High`, and
every A/V duration pair is within 0.035s. That regression is fixed and stayed fixed. This is
the one of the six that the code genuinely holds closed (F5).

## F1: Element 2 passes its literal test on all six long-forms while a third of every runtime is silence — the "over 4s" rule is defeated by transients, and CARTHIEF ships a 37.3s stretch that is half dead
SEVERITY: high
EVIDENCE: Contract element 2 is "dead air over 4s removed". Tested exactly, using the
pipeline's own definition of silence (`render.detect_silences` default, −30 dBFS) and the
contract's own duration:

```
$ ffprobe -v error -f lavfi -i "amovie='...<FILE>',silencedetect=n=-30dB:d=4.0" \
    -show_entries frame_tags=lavfi.silence_duration -of csv=p=0
1_LONGFORM_Thompson  dur= 657.7s  spans>=4s=0
CARTHIEF_LONGFORM    dur=1002.9s  spans>=4s=0
MONKEY_LONGFORM      dur= 808.9s  spans>=4s=0
OFFERUP_LONGFORM     dur= 550.3s  spans>=4s=0
ROMERO_LONGFORM      dur= 419.9s  spans>=4s=0
SANCHEZ_LONGFORM     dur= 443.9s  spans>=4s=0
```

**The rule passes everywhere.** The trimmer works. But dropping the duration gate to 0.30s
shows what the rule lets through:

```
$ ... silencedetect=n=-30dB:d=0.30
1_LONGFORM_Thompson  spans=248  silent=205.9s (31.3%)  longest contiguous=3.67s
CARTHIEF_LONGFORM    spans=381  silent=355.7s (35.5%)  longest contiguous=3.94s
MONKEY_LONGFORM      spans=283  silent=232.6s (28.8%)  longest contiguous=3.39s
OFFERUP_LONGFORM     spans=183  silent=115.0s (20.9%)  longest contiguous=3.26s
ROMERO_LONGFORM      spans=161  silent=135.5s (32.3%)  longest contiguous=3.00s
SANCHEZ_LONGFORM     spans=135  silent= 84.3s (19.0%)  longest contiguous=2.24s
```

Every longest-contiguous figure sits just under the 4.0s line (2.24–3.94s) — the shape of a
gate being satisfied rather than a problem being solved. The failure mode is contiguity:
a genuinely dead stretch punctuated by a cough or a chair scrape is scored as many short spans,
none of which reach 4s. Measured directly on CARTHIEF at 441.75–479.07s, a 37.3-second stretch
whose overall RMS is −36.81 dB (against −21.74 dB for a speech control at 300–337s, i.e. 15 dB
quieter):

```
$ ffprobe ... atrim=start=441.75:end=479.07,asetpts=PTS-STARTPTS,silencedetect=n=-30dB:d=0.30
  sub-spans=27   total_silent=18.3s of 37.3s   LONGEST CONTIGUOUS=1.71s
```

Half that stretch is literally silent, and the trimmer saw nothing above 1.71s in it. Peak
inside the window is −15.04 dB — occasional small transients, not speech. This is on
`CARTHIEF_LONGFORM.mp4`; `1_LONGFORM_Thompson.mp4`, the file STATE.md records as already
posted ("i alreADY POSTED THE THIMPSON"), is 31.3% silence by the same measure.
WHY-IT-MATTERS: The contract is written as a threshold rule and is therefore satisfiable without
the video getting better. A viewer does not experience "spans over 4 seconds"; they experience
37 seconds where almost nothing happens, and they swipe. Worse for reliability: because element 2
*passes*, no gate, log or reviewer will ever flag these files, so the one element with a
machine-checkable definition is the one giving false assurance.
PROPOSAL: Replace the contiguity rule with a windowed density rule — reject any 20s window that
is more than ~50% silent at −30 dBFS, which is exactly what catches the CARTHIEF stretch (18.3s
of 37.3s) while ignoring normal courtroom pauses. The word-gap cutter
(`scripts/tighten_short.py`) already solves this properly for shorts by cutting on transcript
word gaps rather than audio level, and is immune to the transient problem; routing long-forms
through it is the better fix, with the density rule as the post-render gate that proves it worked.
COST: Moderate. The density gate is ~30 lines and can run read-only over existing files today,
so the six shipped long-forms can be triaged before anything is re-rendered. Routing long-forms
through the word-gap cutter needs a transcript per case (three of six are registered — see F10)
and re-tuning `--gap-min` from its shorts value of 0.70s to something like 2.0–4.0s, since 0.70s
on a 17-minute hearing would strip the natural pacing of courtroom speech and sound machine-gunned.

## F2: All six long-forms carry the wrong intro asset — the 1.4s `sting.mp4`, not the `sting_v2.mp4` the contract names
SEVERITY: high
EVIDENCE: `CLAUDE.md` element 3 names the asset explicitly: "the branded sting on the front
(`boyd-brand/sting_v2.mp4`, 2.6s)". Both assets exist on disk and have distinguishable luma
signatures — `sting.mp4` is flat, `sting_v2.mp4` ramps:

```
$ ffprobe -v error -f lavfi -i "movie='...boyd-brand/sting.mp4',signalstats" \
    -show_entries frame_tags=lavfi.signalstats.YAVG -of csv=p=0 | head -5
sting.mp4    head:  37.2094 37.2279 37.2139 37.2146 37.2199    (duration 1.400000)
sting_v2.mp4 head:  36.0945 36.4467 36.7869 37.0688 37.2979    (duration 2.600000)
```

First five frames of every shipped long-form, same measurement:

```
1_LONGFORM_Thompson    37.2065 37.2236 37.2261 37.2328 37.2124
CARTHIEF_LONGFORM      37.2065 37.2236 37.2261 37.2328 37.2124
MONKEY_LONGFORM        37.2065 37.2236 37.2261 37.2328 37.2124
OFFERUP_LONGFORM       37.2065 37.2236 37.2261 37.2328 37.2124
ROMERO_LONGFORM        37.2065 37.2236 37.2261 37.2328 37.2124
SANCHEZ_LONGFORM       37.2065 37.2236 37.2261 37.2328 37.2124
```

Identical opening across all six, matching the flat `sting.mp4` profile and not the ramping
`sting_v2.mp4`. The cause is a deliberate, documented override at
`scripts/build_case_longform.py:41-44`, quoted verbatim:

```
# The channel sting. sting.mp4 is the 1.4s fade-up to the mark and is what the
# SHIPPED Thompson long-form carries (verified by extracting its frame at 0.7s),
# so it is the house default rather than the flashier 2.6s sting_v2.
INTRO = Path(r"C:\Users\natha\OneDrive\Desktop\Boyd Clips\boyd-brand\sting.mp4")
```

Meanwhile `render.resolve_intro`'s `_INTRO_CANDIDATES` at `src/boydclips/render.py:1185-1187`
still point at `sting_v2.mp4` and are bypassed entirely by that constant.
WHY-IT-MATTERS: This is not a silent degrade — it is a *documented contradiction between the
contract and the builder that nobody reconciled*. CLAUDE.md says any of the six being absent "is
a bug, not a preference"; the builder says sting.mp4 "is the house default". Both are live, so
the next person to touch this reintroduces whichever they read first. Two code paths
(`resolve_intro` and `build_case_longform.INTRO`) now disagree about what the brand is.
PROPOSAL: Nathan's call which sting is house style — this is taste, not measurement. Then make one
of them true and delete the other: either update `CLAUDE.md` element 3 to name `sting.mp4`/1.4s, or
change `build_case_longform.py:44` to use `render.resolve_intro()` and re-render. Do not leave two.
COST: Trivial to fix (one line or one doc edit). If sting_v2 wins, six re-renders. Risks nothing
technically; the risk is picking without asking, since it is a branding decision.

## F3: STATE.md's "silencedetect is blind on this footage, every pass before 2026-08-28 was therefore blind" is over-broad — it is blind on tightened shorts and works fine on long-forms, and the difference decides which files need rebuilding
SEVERITY: high
EVIDENCE: STATE.md:16 states, in bold: "`silencedetect` DOES NOT WORK ON THIS FOOTAGE. Do not use
it." with "Every dead-air pass in this repo before 2026-08-28 used it and was therefore blind."

The first half reproduces. On the already-cut `CARTHIEF_SHORT.mp4`:

```
$ ffprobe -v error -f lavfi -i "amovie='...CARTHIEF_SHORT.mp4',silencedetect=n=${db}dB:d=0.3" \
    -show_entries frame_tags=lavfi.silence_start,lavfi.silence_duration -of csv=p=0
-30dB: spans=1 total_silence_s=0.31
-25dB: spans=0   -20dB: spans=0   -18dB: spans=0
```

The generalisation does not. The same detector at the same −30 dBFS setting, on the long-forms
the same code path actually processes:

```
$ ... silencedetect=n=-30dB:d=0.30
CARTHIEF_LONGFORM    spans=381  total=355.7s
MONKEY_LONGFORM      spans=283  total=232.6s
1_LONGFORM_Thompson  spans=248  total=205.9s
```

381 spans is not blindness. The explanation is that the short is a *pre-tightened highlight* —
the dead air had already been cut out of it, so of course a silence detector finds nothing left;
that is the expected result of a working pipeline, not evidence the detector is broken. The
long-form still contains the pauses, and the detector sees all of them.

Separately, the docstring at `src/boydclips/render.py:583-593` claims verification I cannot
reproduce: "Verified against the shipped 34.55s Thompson short, where it found 10 spans totalling
4.75s". No 34.55s Thompson short exists in READY-TO-POST (`2_SHORT_Thompson.mp4` is 32.90s), so
the cited measurement refers to a file that is no longer on disk and cannot be checked.
Callers: `scripts/build_case_longform.py` (docstring lines 12-13, "detect_silences +
plan_silence_trim for CONTENT_SPEC §2 dead air") — the builder behind MONKEY, CARTHIEF, OFFERUP,
ROMERO and SANCHEZ. `src/boydclips/refine.py:12` describes the same approach. `scripts/fix_mutes.py:61`
uses −50 dB for a different job (locating source mutes) and is legitimate.
WHY-IT-MATTERS: This is the highest-consequence doc error in the repo, because it prescribes work.
Read literally, STATE.md says every long-form was dead-aired blind and implies all six need
rebuilding on a new cutter — days of re-rendering. The measurement says the long-form trim worked
(F1: zero spans over 4s in all six) and the real defect is the contiguity rule, which is a gate
change, not a rebuild. A rule stated more broadly than the evidence supports sends the next session
down the expensive branch, and STATE.md is explicitly the file every session reads first.
PROPOSAL: Narrow STATE.md:16 to what was measured — silencedetect returns ~nothing on
already-tightened shorts, so it cannot be used to verify a short is tight; it remains valid on
untrimmed long-form audio. Keep the "do not use it" ban scoped to the shorts pipeline, where
word gaps are genuinely the right signal. Then add the F1 density gate, which is what actually
catches the residual problem on long-forms.
COST: A STATE.md edit plus the F1 gate. The real cost is in *not* doing it: the current wording
justifies re-rendering six long-forms that measurement says do not need it. Risk: narrowing a
safety warning can read as weakening it, so the edit should keep the ban explicit for shorts
rather than softening it to a caveat.

## F4: 4 of 6 shipped thumbnails fail the project's own `flat_chroma` gate, and the metric mis-selects its region so one score is meaningless
SEVERITY: high
EVIDENCE: The gate is `scripts/verify_thumbnail.py:49`, `flat_chroma_dev=3.5`, commented
"ungraded ceiling measures 1.33; the broken grade measured 8.13". I replicated `flat_chroma`
(verify_thumbnail.py:422-446) exactly in PIL/numpy — brightest 100x100 patch with luma std <=12,
then mean `sqrt((Cb-128)^2 + (Cr-128)^2)` — over every shipped thumbnail:

```
GATE flat_chroma_dev = 3.5
1_LONGFORM_thumbnail.jpg   flat_chroma= 3.70  FAIL   region=(638,117) luma 245.6
CARTHIEF_thumbnail.jpg     flat_chroma=89.90  FAIL   region=(518,477) luma 117.6
MONKEY_thumbnail.jpg       flat_chroma= 0.96  pass   region=(598,177) luma 228.2
OFFERUP_thumbnail.jpg      flat_chroma= 5.61  FAIL   region=(1158,57) luma 218.2
ROMERO_thumbnail.jpg       flat_chroma=10.39  FAIL   region=(38,277)  luma 217.9
SANCHEZ_thumbnail.jpg      flat_chroma= 0.77  pass   region=(598,177) luma 228.1
```

All six are 1280x720, 182-287 KB, well inside YouTube limits. OFFERUP's 5.61 corroborates
STATE.md's Q3 figure of 5.54. But **CARTHIEF's 89.90 is a metric artefact, not 25x blocking**: the
selected patch has luma 117.6, a midtone, not a bright flat area. The selector maximises luma among
low-variance patches with *no neutrality precondition*, so when an image has no bright neutral
region it happily returns a legitimately saturated flat one — here almost certainly the orange jail
scrubs, whose true chroma distance from neutral really is ~90. The gate cannot distinguish
"chroma blocking" from "a big orange object".
WHY-IT-MATTERS: Two failures at once. The three genuine fails (Thompson 3.70, OFFERUP 5.61, ROMERO
10.39) shipped anyway, so the gate is not wired into the thumbnail build. And the gate as written
would raise a false blocker on any thumbnail containing a large saturated flat object — which on a
jail-scrubs docket is most of them — so wiring it in as-is would produce a checker nobody trusts,
which is how gates get switched off.
PROPOSAL: Two changes. (a) Add a neutrality precondition to region selection: require the patch
luma >= ~180 and reject patches whose chroma is *uniformly* offset (blocking is high-variance
chroma in a flat-luma area; an orange object is low-variance chroma). Score on chroma **standard
deviation** within the patch, not mean distance from neutral — that is what "blocking" actually is.
(b) Wire the recomputed gate into `make_thumbnail_auto.py` as a build-failing check.
COST: Half a day, mostly re-deriving the threshold against known-good and known-broken examples
(both exist: ungraded 1.33, broken grade 8.13). Risk: changing the metric invalidates the 3.5
threshold and STATE.md's recorded Q3 5.54, so both must be re-measured and STATE.md updated or
the numbers on the page stop meaning anything.

## F5: `make_short_auto.py`'s five gates are real but fail OPEN — a refused run leaves the broken file at the final destination, and one of the five verifies arithmetic rather than the artifact
SEVERITY: high
EVIDENCE: The gates exist and are honest about their subject (`scripts/make_short_auto.py:180-194`):

```python
checks = [
    ("pix_fmt yuv420p", pf == "yuv420p", pf),
    ("1080x1920", (w, h) == (1080, 1920), f"{w}x{h}"),
    ("A/V in sync", abs(vd - ad) < 0.15, f"{vd:.2f}s / {ad:.2f}s"),
    (f"no word-gap over {a.gap_min}s", not big, ...),
    ("decodes clean", dec.returncode == 0 and not dec.stderr.strip(), ...),
]
...
print("\n   " + (f"-> {a.out}" if ok else "REFUSED: a check failed above"))
return 0 if ok else 4
```

Three defects.

(1) **The refusal does not remove the file.** `grep -n "unlink\|remove\|rmtree\|rename" scripts/make_short_auto.py`
returns nothing. `scripts/caption_short.py:364` writes straight to `str(a.out.resolve())` with `-y`.
So on failure the script prints "REFUSED", exits 4, and the broken short is sitting at exactly the
path a human or a later script will pick up. The header promises it "REFUSES rather than emitting
something broken" — it emits it and then says it refused.

(2) **The word-gap gate checks its own arithmetic, not the render.** `big` is derived from `words`,
the in-memory remapped word list built at lines 121-131 — the same list the cut plan came from. It
will essentially always pass, because it is asking "did my remap produce the gaps my remap intended".
It never probes the rendered file. A cut that ffmpeg applied wrongly passes this gate.

(3) **The docstring's "five things" and the five checks are different sets.** The docstring
(lines 12-32) lists word-gap cutting, uncut speaker series, AV-correlation attribution, non-straddling
caption blocks, and yuv420p. The runtime checks cover yuv420p, resolution, A/V sync, word gaps and
decode. Items 2, 3 and 4 — the speaker-attribution work that is the actual novelty here — have
**no verification gate at all**. Nothing measures whether captions landed on the correct half.

Exit codes are otherwise well-behaved: every stage returns 1 on subprocess failure (lines 105, 115,
137). Gate 1 (pix_fmt) demonstrably holds — all 21 shipped mp4s measure yuv420p.
WHY-IT-MATTERS: The value of this script is that it is trustworthy unattended — Nathan's stated goal
is "automate these shorts every day". A gate that leaves the artifact behind converts a caught
failure into a silent one the moment anyone globs the output directory, which is precisely the
degradation mode CLAUDE.md describes. And the headline feature (speaker-side captions) is unverified,
so the one thing most likely to be wrong is the one thing nothing checks.
PROPOSAL: Render to `a.out.with_suffix('.part.mp4')` and only rename onto `a.out` after all checks
pass; unlink the part file on refusal. Re-probe the *rendered* file for gaps instead of the word
list. Add a sixth check for caption placement: `who_speaks.py` already produces the per-frame
speaker series, so assert that each burned block's `MarginV` matches the series majority over that
block's time range, and fail below ~90% agreement.
COST: The part-file rename and unlink are ~10 lines and risk nothing. The placement check is a day's
work and needs a labelled ground-truth set — the nine hand-labelled windows referenced in
STATE.md:20-24 are the obvious seed if they were retained.

## F6: Element 4 (watermark) cannot be verified from the shipped files, and the logs that were the only evidence it ran were never retained
SEVERITY: medium
EVIDENCE: I could not confirm or refute the watermark, and I am labelling it rather than guessing.
What I tried, read-only:

Top strip is pure black — the court's own letterbox, not picture:
```
$ ffprobe ... crop=120:120:${x}:40,signalstats   (x = 60..1740, CARTHIEF/Thompson/MONKEY)
all cells Y=16   (Y=16 is video black)
```
Picture bounds located by vertical scan: black to y~240, picture y~250-880, full width.
Temporal-difference test inside the picture, 200-215s (a burned-in static mark should appear as a
near-zero island against moving footage):
```
  y=260 :  x1380=0.016  x1500=0.003  x1620=0.016  x1740=0.012  x1800=0.013
  y=320 :  x1380=0.257  x1500=0.136  x1620=0.009  x1740=0.009  x1800=0.014
  y=380 :  x1380=1.457  x1500=1.175  x1620=0.025  x1740=0.030  x1800=0.032
  centre control (900,500) = 0.283
```
Inconclusive: the whole right side of this frame is static courtroom wall (0.009-0.032), so a
static overlay is indistinguishable from static background there. The mark is also low-opacity with
a baked halo, so it does not shift regional luma detectably.

The design intends a warning to be the evidence — `src/boydclips/render.py:1248`
`log.warning("watermark not found, rendering without it: %s", path)`, with the comment at
`render.py:1180-1183` stating the failure history outright: "_watermark_chain degrades to 'no
watermark' rather than failing the render, so every short since then went out unbranded with only a
log line to say so." That evidence does not exist:
```
$ grep -rn "watermark not found\|rendering without it" logs/ *.log     -> no matches
$ ls logs/    -> newest is 2026-08-17.log (dir mtime 2026-08-20)
```
The shipped long-forms are dated 2026-08-23 to 2026-08-27. **No log covering any run that produced
a shipped artifact was retained.**

The assets themselves are present, so the degrade is not currently armed:
`boyd-brand/sting_v2.mp4` (401174 bytes), `boyd-brand/sting.mp4` (515084),
`boyd-brand/watermarks_v2/wm_brand_halo_40.png` — all at `_CANDIDATES[0]`.
WHY-IT-MATTERS: A safety mechanism whose entire output is a log line, in a pipeline that keeps no
logs, is not a safety mechanism. Whether the six shipped videos carry the mark is currently
unknowable from disk. Separately, `render.py:1215-1216` — `DEFAULT_WATERMARK = next((p for p in
_WATERMARK_CANDIDATES if p.is_file()), _WATERMARK_CANDIDATES[0])` — falls back to a *non-existent*
path when none resolve, which then fails the `is_file()` test at line 1247 and degrades to no
watermark. The fallback is decorative; the real behaviour is always "silently unbranded".
PROPOSAL: Two things. (a) Make `resolve_intro`/`_watermark_chain` raise rather than warn when the
asset is missing and the config did not explicitly disable it — `build_case_longform.py:285-286`
already proves the pattern works ("REFUSING: intro missing", return 1). (b) Write a render manifest
JSON next to every output recording the exact intro path, watermark path, filter chain and durations
used, so element 4 is answerable from disk forever. To answer it *now*, extract one body frame per
long-form and look — one write, and it settles all six.
COST: Small. The raise is a few lines and its risk is that a legitimately watermark-free render now
needs an explicit `watermark: false` in config, which is the correct behaviour anyway. The manifest
is ~20 lines and risks nothing.

## F7: The shipped `CARTHIEF_thumbnail.jpg` predates the severed-arm guard by 30 minutes — it never passed through it
SEVERITY: medium
EVIDENCE: STATE.md:174-178 records the guard being added to `regroup_plate.py` and notes "the shipped
CARTHIEF_thumbnail.jpg is still wrong". The mtimes settle why — the artifact is older than the fix:

```
$ stat -c '%y  %n' scripts/regroup_plate.py ".../READY-TO-POST/CARTHIEF_thumbnail.jpg"
2026-08-28 21:30:32  scripts/regroup_plate.py
2026-08-28 21:00:43  CARTHIEF_thumbnail.jpg
```

29m49s earlier. The guard did not fail — it never ran on this file. It is real and correct code
(`scripts/regroup_plate.py:110-119`):
```
# MERGED-BLOB GUARD. If he and his attorney touch, the matte returns them as
# ONE component and there is no honest way to split it — any cut is a guess
...
print(f"  REFUSING: component is {ratio:.2f}x the scrubs width — he is "
      f"merged with another person in the matte, so any separation "
      f"would cut through a body. Pick a frame where they do not touch.")
```
Git history is uninformative here: `git log -- scripts/regroup_plate.py` returns a single commit
(c56d8b5, 2026-08-29 02:37), i.e. the guard and everything else landed in one commit *after* both
timestamps, so mtime is the only available ordering evidence and I am relying on it.
WHY-IT-MATTERS: Small in itself — regenerate and it is fixed. It matters as a pattern: nothing in
this pipeline records which code version produced which artifact, so "is the shipped file affected
by fix X" is answerable only by filesystem timestamps that any file copy destroys. STATE.md was
right that the file is wrong, but for the reason "never rebuilt", not "guard failed" — and those
demand different responses.
PROPOSAL: Re-run the CARTHIEF thumbnail through `make_thumbnail_auto.py --case CARTHIEF` and confirm
the guard either passes it or refuses the frame. Longer term this is the same manifest as F6 —
stamp the producing commit into a sidecar next to every artifact.
COST: Minutes to regenerate. Risk: if the guard refuses (STATE.md records src 4437 giving a 2.51x
merged component), CARTHIEF needs a different plate frame chosen, which `pick_plate.py` automates.

## F8: `verify_thumbnail.py`'s arrow-aim check measures distance to the face, not aim error — the metric is wrong, not just the threshold
SEVERITY: medium
EVIDENCE: STATE.md:186-188 says the checker fails the Thompson reference on arrow-aim and concludes
"the threshold is wrong, not Thompson". The threshold is wrong, but only because the quantity is.
`scripts/verify_thumbnail.py:386-398`:

```python
miss = 1.0
for step in range(4, int(W * 0.45), 4):
    px, py = tx + ux * step, ty + uy * step
    ...
    for (fx, fy, fw, fh) in faces:
        if fx <= px <= fx + fw and fy <= py <= fy + fh:
            miss = step / W
            break
```
compared against `arrow_aim_miss_frac=0.16` at line 45, commented "the ray from the tip must reach
a face box within 16% of the frame width".

`miss` is assigned `step / W` — the **distance travelled along the ray before hitting a face**, as
a fraction of frame width. It is not a miss distance at all; it is a hit distance. A perfectly aimed
arrow whose target face sits 30% of the frame away scores 0.30 and **fails**, while the same arrow
aimed at a face 10% away scores 0.10 and passes. The variable name, the threshold name
(`_miss_frac`) and the comment all describe angular aim error; the code computes range. Thompson
fails because its arrow "comes down from empty space" (make_thumbnail_v5.py:189) toward a face
further than 0.16·W away — i.e. it fails for being a *long* arrow, not a badly aimed one.

Compounding it, both arrow and chroma checks fail open. `verify_thumbnail.py:473-481` catches every
exception and sets `arrow_px=0` / `flat_chroma=None`; the consumers at line 522
(`if m.get("arrow_px", 0) >= 200:`) and line 530 (`if m.get("flat_chroma") is not None and ...`)
then skip the check entirely, with no message. A missing `rembg`/`birefnet` model would silently
disable arrow checking and the report would read clean. (All deps do import on this machine:
cv2, rembg, scipy, numpy, PIL, onnxruntime all OK — so this is latent, not active.)
WHY-IT-MATTERS: A checker that fails its own declared ground truth gets ignored, and this one is the
only automated defence for the thumbnail — the surface Nathan judges hardest. Raising the threshold
to make Thompson pass (the obvious reading of STATE.md) would make the check meaningless, because a
larger allowed *range* does not test aim at all. The real check was never written.
PROPOSAL: Replace range with true aim error: from the tip, take the angle between the arrow axis and
the vector to each face centre, and gate on the minimum angle (e.g. fail above ~12-15 degrees), with
a separate sanity bound that some face lies ahead of the tip rather than behind it. Validate against
the shipped Thompson thumbnail, which by the file's own rule is ground truth and must pass. Replace
the two bare excepts with an explicit `arrow_error`/`chroma_error` that the report prints as
UNCHECKED, so a missing dependency reads as "not tested" rather than "passed".
COST: An hour for the angle metric, plus re-deriving the threshold against the 12-image competitor
set the other thresholds were calibrated on. Risk: the new metric may fail thumbnails that currently
pass, which is the point but will need Nathan's eye to confirm the calls.

## F9: Element 5 is simply absent for MONKEY and incomplete for ROMERO, and nothing reports it
SEVERITY: medium
EVIDENCE: Contract element 5 requires a Thompson-style short per case. Directory listing of
READY-TO-POST by case:

```
MONKEY :  MONKEY_LONGFORM.mp4, MONKEY_thumbnail.jpg, MONKEY_verify_sheet.png
          -> no MONKEY_SHORT* file of any kind exists
ROMERO :  ROMERO_SHORT.mp4 (48.0s), ROMERO_SHORT_CAP.mp4 (48.0s)
          -> no ROMERO_SHORT_FINAL.mp4; stops at the captioned stage
CARTHIEF: SHORT, SHORT_CAP, SHORT_CLEAN, SHORT_TIGHT, SHORT_TIGHT_V2, SHORT_FINAL (34.8s)
OFFERUP : SHORT, SHORT_CAP, SHORT_FINAL (41.9s)
SANCHEZ : SHORT, SHORT_CAP, SHORT_FINAL (49.1s)
```

MONKEY_LONGFORM.mp4 is dated 2026-08-23 09:38 and STATE.md records it as uploaded on 2026-08-27 —
so a long-form went out with no companion short at all. Separately, STATE.md:180-181 states "SANCHEZ
and OFFERUP shorts have not been through the new pipeline. Only CARTHIEF has", but
`SANCHEZ_SHORT_FINAL.mp4` (2026-08-29 04:01) and `OFFERUP_SHORT_FINAL.mp4` (2026-08-29 04:02) both
exist and predate STATE.md's own last write (2026-08-29 04:25). STATE.md is stale on its own
highest-priority open item.

There is also no artifact-level inventory anywhere in the render path — no script enumerates
READY-TO-POST and reports which of the six each case has. The six-element contract exists only as
English prose in CLAUDE.md.
WHY-IT-MATTERS: The short is the discovery mechanism for the long-form; a long-form published
without one is the funnel with its top removed. That MONKEY has none was not flagged by any tool —
it is visible only by listing the directory, which is exactly why it survived to publication.
PROPOSAL: Write a `scripts/audit_ready.py` that walks READY-TO-POST plus `config/cases.json` and
prints the table at the top of this document — per case, the six elements with the measurement
behind each (probe pix_fmt/duration, luma-signature the intro against both stings, count >=4s spans,
check for a `_FINAL` short, run flat_chroma on the thumbnail). Everything in it is already measured
above with read-only probes, so it is assembly, not research. Run it before any upload.
COST: Half a day. Risks nothing — it is read-only. The value is that it converts a prose contract
into something that returns a non-zero exit code, which is the only form of the contract that has
ever held.

## F10: The parametric case registry covers only three of the six shipped cases, so half the shipped catalogue cannot be rebuilt through the automated path
SEVERITY: low
EVIDENCE: Case names appearing in `scripts/` and `src/`:

```
$ grep -rn "<NAME>" --include=*.py scripts/ src/ | wc -l
Thompson: 122 refs across 30 files      CARTHIEF: 45 refs across 19 files
OFFERUP:  31 refs across 11 files       SANCHEZ:  14 refs across  9 files
ROMERO:    6 refs across  6 files       MONKEY:    1 ref  across  1 file
CASTILLO:  6 refs across  5 files
```

Most of that is legitimate — measured constants documented against the reference they came from
(`make_thumbnail_v5.py` derives its geometry from the shipped Thompson thumbnail and says so, and
the arrow tip was already un-hardcoded per STATE.md:396). The genuine parameterisation is real and
recent: `config/cases.json` holds 13 fields per case (`video, transcript, offset, case_from,
case_to, judge_t, judge_crop, plate_t, plate_crop, white, yellow, short, short_src_start`) and
`make_thumbnail_auto.py:63-78` resolves `--case` against it, failing cleanly on an unknown key.
`build_case_longform.py` and `make_short_auto.py` take every boundary as a CLI argument.

The gap is coverage, not design:
```
$ python -c "import json; print(list(json.load(open('config/cases.json'))))"
['CARTHIEF', 'SANCHEZ', 'OFFERUP']
```
Thompson, MONKEY and ROMERO — three of the six shipped cases, including the only published one —
have no registry entry, so they cannot be rebuilt through the parametric path at all. Hand-editing
per new video is therefore not "edit the scripts" but "author 13 JSON fields", of which
`judge_t`, `judge_crop`, `plate_crop` and the two caption strings are genuine human judgement
(STATE.md records that three automated gaze metrics failed to reproduce Nathan's eye on judge frame
choice, so that one is deliberately manual).
WHY-IT-MATTERS: Lower severity than the raw grep counts imply — this is closer to a real pipeline
than "hardcoded per case", and I want to be accurate rather than alarming. The concrete cost is that
the three unregistered cases cannot be re-rendered at all through the automated path. That bites the
moment F2 is resolved in favour of `sting_v2.mp4`, which would require re-rendering all six —
including Thompson, MONKEY and ROMERO, none of which are registered. It is a prerequisite for that
fix rather than an architectural complaint.
PROPOSAL: Backfill `Thompson`, `MONKEY` and `ROMERO` into `config/cases.json` before attempting the
F2 re-render. Add a `--case` flag to `build_case_longform.py` so long-form and thumbnail read the
same registry instead of long-form taking loose CLI boundaries.
COST: An hour of backfill, mostly recovering the offsets from the STATE.md build commands, which
records MONKEY's verbatim (`--offset 5895.0 --in 5915.92 --out-s 6739.30`). Risk: the boundaries for
Thompson and ROMERO may not be recorded anywhere and would need re-deriving from the transcripts.
