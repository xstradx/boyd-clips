# leaf-4.1 — re-measurement of every claimed open defect

Measured 2026-08-29 on this machine. ffprobe/ffmpeg 8.0.1-essentials_build-www.gyan.dev
(`/c/ffmpeg/ffprobe`), Python 3.14, PIL + numpy + scipy + cv2. Read-only: every
ffmpeg invocation used `-f null -` (writes nothing) or the lavfi `movie=` probe
source; the only file created is this one.

`READY-TO-POST` is **not** in the repo — it is
`C:\Users\natha\OneDrive\Desktop\Boyd Clips\READY-TO-POST`
(`find /c/Users/natha -maxdepth 6 -type d -name "READY-TO-*"`). Every media path
below is under that directory.

**Verdict table** — claim, verdict, and the measurement behind it.

| # | Claim (source) | Verdict | The measurement |
|---|---|---|---|
| 1 | "The thumbnails still ship a severed arm" — shipped `CARTHIEF_thumbnail.jpg` is still wrong (STATE.md:177) | **STILL TRUE**, but only as *"not rebuilt"*. The severed-arm wording is **NOT MEASURABLE** on the shipped file | Shipped jpg mtime `2026-08-28 21:00:43.250`; `scripts/regroup_plate.py` mtime `2026-08-28 21:30:32.016` — the guard is **29m 49s newer than the file it was supposed to fix**, and the whole `QUALITY/` rebuild is 7h newer. My boundary-straightness test does not separate the shipped file from the rebuilt Q3, and `ARM_CHECK.png` template-matches nothing in READY-TO-POST (best NCC 0.58) |
| 2 | "SANCHEZ and OFFERUP shorts have not been through the new pipeline. Only CARTHIEF has." (STATE.md:182) | **FIXED — the bullet is stale, and STATE.md contradicts itself** | `SANCHEZ_SHORT_FINAL.mp4` (49.14s, mtime 08-29 04:01:32) and `OFFERUP_SHORT_FINAL.mp4` (41.90s, 04:02:29) both exist and match STATE.md's own "all three cases pass" table 60 lines earlier (line 122). Separately: **ROMERO has no `_FINAL` at all** and is named in neither list |
| 3 | "The long-forms were dead-aired with the blind `silencedetect` … almost certainly still carry gaps nobody measured" (STATE.md:184) | **STILL TRUE — and now measured** | `silencedetect=n=-20dB:d=4.0`: CARTHIEF_LONGFORM **23 spans ≥4s totalling 134.9s**, incl. an 11.40s hole ending t=479.06 and a 9.83s hole ending t=464.24 — 21s of silence inside a 30s window. ROMERO 4/17.9s, OFFERUP 3/15.3s, Thompson 2/11.8s, MONKEY 1/5.3s, SANCHEZ 0 |
| 3b | STATE.md's *headline* rule: "**`silencedetect` DOES NOT WORK ON THIS FOOTAGE. Do not use it.** Measured on CARTHIEF_SHORT.mp4 at -30, -25, -20 AND -18 dBFS: **zero spans, every time.** The courtroom room tone never drops that low." (STATE.md:16-18) | **NEVER TRUE** | 18 sweeps over that exact unmodified file returned spans at **every** threshold. `-30dB d=2.0` → 3 spans / 10.01s. `-20dB d=0.7` → 10 spans / **31.14s**, which reproduces the word-gap method's own headline number (31.2s) to within 0.06s. `astats` on the same file: **noise floor −83.0 dBFS**, 53 dB *below* the −30 threshold the rule says the room tone never reaches |
| 4 | "`verify_thumbnail.py` fails the Thompson reference on its own arrow-aim check" (STATE.md:186) | **STILL TRUE, and understated** | Thompson fails on **two** checks, not one: `ARROW_AIMS_AT_NOTHING` *and* `CHROMA_BLOCKING … deviates 3.7` against a 3.5 gate. Run across all 12 shipped + candidate thumbnails: **0/12 passed** |
| 5 | "All four captioned shorts shipped as High 4:4:4 Predictive once; no consumer hardware decoder plays it" (STATE.md:39) | **FIXED — zero files affected today** | ffprobe over **all 21** mp4s in READY-TO-POST: every one is `profile=High`, `pix_fmt=yuv420p`, `level=40`. Plus `ffmpeg -v error -f null -` on all 21: **zero decode errors**; worst A/V duration drift 35 ms (SANCHEZ_LONGFORM) |
| 6 | "MONKEY's local thumbnail is fixed but the LIVE video still carries the old blocky one" (STATE.md:348) | **Local half FIXED. Live half NOT MEASURABLE from this leaf** | `MONKEY_thumbnail.jpg` is the only shipped thumbnail whose gate failures exclude `CHROMA_BLOCKING`; my independent block-spread metric gives 1.63. The live half needs the YouTube Data API (`youtube-channel` skill) — another leaf |
| 7 | "Q3 carries chroma deviation 5.54, above the 3.5 gate" (STATE.md:102) | **STILL TRUE — independently confirmed at 5.56** | My own flat-bright-block method (defined in F6 below, never reads repo code) gives Q3_detail = **5.56** vs the recorded 5.54. But the repo carries **three mutually exclusive numbers for this same file**: 5.54 (STATE.md), **1.685** (`Q3_detail.jpg.meta.json`), **90.9** (`verify_thumbnail.py`, run today) |
| 8a | OPEN-THREADS: overexposed courtroom light bulb, "never attempted on our side" | **STILL TRUE**, and now quantified | `lutyuv=y='if(gte(val,250),255,0)',signalstats`: CARTHIEF_LONGFORM mean clipped-pixel fraction **0.0206**, worst frame **0.0563**; Thompson 0.0148. `signalstats` YMAX = 255 on every sampled frame at YAVG ≈ 75. `grep -rn -i "bulb\|overexpos\|clipped highlight"` finds nothing in the video render path |
| 8b | OPEN-THREADS: Blackburn's short is a 3-4 tile Zoom grid; closes when per-beat cropping is implemented | **STILL TRUE, both halves** | `out/oncam/blackburn_BADGRID/f04.png` is a **3-tile** grid; Haar face detection measures the two visible faces at 65x65 and 28x28 px, i.e. **5.1% and 2.2% of the 1280 frame width** (55px and 24px once `blur_pad` scales to 1080 wide). `src/boydclips/render.py:1146 _concat_filter` still emits `[0:v]trim=…,setpts=PTS-STARTPTS[vN]` with **no crop filter of any kind** |
| 8c | OPEN-THREADS: the documentary opening was rejected twice | **STILL TRUE**, weakly measured | The only opening builders on disk are `scripts/build_open.py` (2026-08-12), `doc_cards.py` (2026-08-12), `animate_docs.py` (2026-08-14) — all predate both rejections. No newer artifact exists. Whether a rebuild would satisfy him is not measurable from disk |
| 9 | A/V sync and decode integrity on every shipped mp4 | **CLEAN — no blocker** | See row 5. Detail per file in F8 |

Two things I looked for and did **not** find, stated so they are not mistaken for
untested: (a) I could not confirm the shipped thumbnails are the *frames* Nathan
picked — `AB-THUMBNAILS/*_thumb_{A,B,C}.jpg` turn out to be **headline-text**
variants over an identical plate (CARTHIEF A vs C, mean |Δ| below the text band =
**0.016**, max 14), not the frame variants his "i like C on car theif" quote
judges, so the obvious inference that we shipped a rejected variant is wrong and
I struck it; (b) I could not attribute `ARM_CHECK.png` to any build in
READY-TO-POST.

---

## F1: STATE.md's headline rule "`silencedetect` DOES NOT WORK ON THIS FOOTAGE … zero spans, every time" is NEVER TRUE — it returns spans at every threshold on the exact file it names

SEVERITY: blocker
EVIDENCE: 18-cell sweep over the unmodified `CARTHIEF_SHORT.mp4` (mtime 2026-08-27 03:37:56, i.e. it predates the 08-28 claim and has not changed since), `ffmpeg -v info -nostats -i CARTHIEF_SHORT.mp4 -af "silencedetect=n=${th}dB:d=${d}" -f null -`, counting `silence_start` and summing `silence_duration`:

```
n=-30dB d=2.0  spans=3   total_silent=10.01s of 56.20s
n=-30dB d=1.0  spans=11  total_silent=21.70s
n=-30dB d=0.7  spans=16  total_silent=25.58s
n=-25dB d=2.0  spans=5   total_silent=19.22s
n=-20dB d=2.0  spans=6   total_silent=25.82s
n=-20dB d=0.7  spans=10  total_silent=31.14s   <-- word-gap method's own figure is 31.2s
n=-18dB d=2.0  spans=6   total_silent=25.98s
n=-12dB d=0.7  spans=12  total_silent=35.72s
n=-10dB d=0.7  spans=14  total_silent=40.80s
```

Not one cell returns zero. The stated *reason* is independently false too — `ffmpeg -i CARTHIEF_SHORT.mp4 -af astats=metadata=0 -f null -` returns `Noise floor dB: -83.009947`, `RMS level dB: -24.388671`, `Peak level dB: -5.163749`. The room tone sits **53 dB below** the −30 dBFS the rule says it never reaches. And at −20 dB/0.7s silencedetect and the word-gap transcript method agree to within 0.06 s (31.14 vs 31.2), so they are not even measuring different things.
WHY-IT-MATTERS: This is the first substantive line of STATE.md, written in bold as a standing prohibition, and it is the stated justification for building an entire replacement pipeline (`tighten_short.py` word-gap cuts). A future session reading STATE.md will refuse to use a working, one-line, transcript-free measurement — including on the long-forms, where there is no word-level transcript pass at all and silencedetect is the only instrument available. A false "do not use X" is worse than a missing note, because it forecloses the check rather than leaving it undone.
PROPOSAL: Replace STATE.md lines 16-18 with the measured table above. Keep the word-gap cutter (it is better: it cuts on *speech* boundaries, and the two agree), but demote the prohibition to what is actually true — "ffmpeg's default `d=2.0` and thresholds at/below −30 dB under-report on this footage; use `n=-20dB:d=0.7`, which reproduces the word-gap total to 0.06 s, and use it as the acceptance check on rendered files where no word-level transcript exists." Most likely root cause of the original zero result, worth one minute to confirm: `noise=-30` passed without the `dB` suffix is parsed as a *linear* amplitude, not decibels.
COST: Doc edit, ~20 minutes including re-running the sweep. Zero risk — no code changes. The follow-on work (F2, F3) is where the effort is.

## F2: The long-forms carry unmeasured dead air, and CARTHIEF_LONGFORM is far worse than "almost certainly" — 23 spans ≥4s totalling 134.9s, including 21s of silence inside one 30s window

SEVERITY: blocker
EVIDENCE: `ffmpeg -v info -nostats -i <f> -af "silencedetect=n=-20dB:d=1.0" -f null -` and the same at `d=4.0`, summing `silence_duration`:

```
file                     dur       spans@d=1.0  silent   %      spans>=4s / total
MONKEY_LONGFORM.mp4      808.9s    121          208.4s   25.8%   1 /   5.3s
1_LONGFORM_Thompson.mp4  657.7s     80          146.3s   22.2%   2 /  11.8s
CARTHIEF_LONGFORM.mp4   1002.9s    128          338.9s   33.8%  23 / 134.9s
OFFERUP_LONGFORM.mp4     550.3s     45           84.4s   15.3%   3 /  15.3s
SANCHEZ_LONGFORM.mp4     443.9s     20           31.9s    7.2%   0 /   0.0s
ROMERO_LONGFORM.mp4      419.9s     74          136.2s   32.4%   4 /  17.9s
```

The individual CARTHIEF holes, `silence_end | silence_duration`, longest first:
`479.06 | 11.397`, `464.24 | 9.831`, `348.31 | 7.484`, `862.14 | 7.375`, `931.42 | 6.722`, `875.58 | 6.701`, `868.69 | 6.555`, `720.70 | 6.428`, `726.69 | 5.960`, `971.07 | 5.948`, `850.14 | 5.735`, `960.32 | 5.259` — and 11 more ≥4s. The 11.40s and 9.83s holes end 14.8s apart, so t≈454-479 of that video is 21.2s of silence out of 25s.

Two of these files are **already published**: Thompson (posted 2026-08-23) at 2 spans/11.8s and MONKEY (posted 2026-08-27) at 1 span/5.3s. CARTHIEF_LONGFORM, the worst by an order of magnitude, is not yet posted.

Two honest caveats. (a) The `d=1.0` percentages (7-34%) are inter-sentence pacing, not defects — the meaningful column is spans ≥4s, which is CONTENT_SPEC §2's own threshold. (b) −20 dBFS is a silence proxy, not a transcript; the discrimination is real though — the same measurement gives SANCHEZ 0 and CARTHIEF 23.
WHY-IT-MATTERS: CLAUDE.md's definition of "start working on videos" lists "dead air over 4s removed (CONTENT_SPEC §2)" as item 2 of the six things that must be true before a video is done. CARTHIEF_LONGFORM violates it 23 times. MONKEY's build log claims "dead air >4.0s removed, 825s → 808s" — that pass ran and left 1 span; the same pass on CARTHIEF left 23, so whatever ran on CARTHIEF either did not run or ran blind. A 16.7-minute video with an 11-second hole at the 8-minute mark loses the retention curve exactly where it is still recoverable.
PROPOSAL: (1) Do not upload CARTHIEF_LONGFORM until re-cut. (2) Add `silencedetect=n=-20dB:d=4.0` as a hard acceptance gate on every rendered long-form — the same shape as the five gates `make_short_auto.py` already runs, refusing rather than emitting; that gate is what would have caught this at render time instead of at audit time. (3) Re-cut CARTHIEF_LONGFORM and ROMERO_LONGFORM against it. Thompson and MONKEY are already live at 2 and 1 spans — leave them; the fix is not worth a re-upload.
COST: Gate ~1 hour (the measurement is one ffmpeg call; the plumbing is copying `make_short_auto.py`'s refuse-on-fail pattern). Re-cutting two long-forms is a re-render each, ~10 min of machine time. Risk: low — the gate is additive and fails closed, and re-cutting uses an existing code path.

## F3: `CARTHIEF_SHORT_FINAL.mp4` still contains a 4.90s silent hole at t=4.92-9.83s, while STATE.md's table reports "gaps >0.7s: 0" for it

SEVERITY: blocker
EVIDENCE: `ffmpeg -v info -nostats -i CARTHIEF_SHORT_FINAL.mp4 -af "silencedetect=n=-20dB:d=0.7" -f null -`:

```
silence_start: 2.405578   silence_end: 3.444036  | silence_duration: 1.038458
silence_start: 4.921406   silence_end: 9.825601  | silence_duration: 4.904195   <-- seconds 5-10 of 34.8
silence_start: 19.884308  silence_end: 21.514626 | silence_duration: 1.630317
silence_start: 22.017302  silence_end: 23.089070 | silence_duration: 1.071769
silence_start: 23.518027  silence_end: 24.876508 | silence_duration: 1.358481
silence_start: 30.959116  silence_end: 31.973560 | silence_duration: 1.014444
```

6 spans ≥0.7s, 11.02s of 34.80s. Same measurement across the family:

```
CARTHIEF_SHORT.mp4        56.20s -> 10 spans / 31.14s / longest 7.48s
CARTHIEF_SHORT_FINAL.mp4  34.80s ->  6 spans / 11.02s / longest 4.90s
SANCHEZ_SHORT.mp4         53.00s ->  6 spans /  5.72s / longest 1.27s
SANCHEZ_SHORT_FINAL.mp4   49.14s ->  3 spans /  2.27s / longest 0.81s
OFFERUP_SHORT.mp4         55.50s -> 14 spans / 18.90s / longest 2.79s
OFFERUP_SHORT_FINAL.mp4   41.90s ->  4 spans /  4.41s / longest 1.56s
ROMERO_SHORT_CAP.mp4      48.00s -> 12 spans / 19.07s / longest 3.75s  (no _FINAL exists)
```

STATE.md:122-125 reports `gaps >0.7s` as `0` for all three FINALs. SANCHEZ (0.81s max) and OFFERUP (1.56s max) are defensible. CARTHIEF is not: a 4.90s continuous span below −20 dBFS is not quiet speech, and the pipeline demonstrably removed the other 20 seconds around it.
WHY-IT-MATTERS: The hole sits at seconds 5-10 of a 34.8-second vertical short — inside the window that decides whether the viewer swipes. The pipeline's own gate passed the file, so the gate is measuring word gaps in the transcript and calling that "no gaps", while the rendered audio disagrees by 11 seconds. That is the exact failure mode STATE.md warns about elsewhere ("critique the rendered artifact, never the source") reappearing in the tool built to prevent it. A gate that passes a file with a 4.9s hole in the hook is worse than no gate, because it is now trusted.
PROPOSAL: Add a post-render acoustic check to `make_short_auto.py`'s gate set — run `silencedetect=n=-20dB:d=0.7` on the **emitted** file, not the transcript, and refuse if any span exceeds ~1.2s (which passes SANCHEZ and OFFERUP as-is and catches CARTHIEF). Then re-run CARTHIEF through the chain. Worth investigating why the word-gap cutter left this specific hole: 4.92-9.83s is likely a stretch with no transcript words at all (a pause the ASR never emitted tokens for), which the gap-between-words method structurally cannot see.
COST: Gate ~45 min. Re-render CARTHIEF short ~5 min. Risk: low, additive and fails closed. The diagnosis of *why* the cutter missed it may take longer than the gate.

## F4: `verify_thumbnail.py` does not fail only the Thompson reference — it fails 12 of 12, including every shipped thumbnail, and Thompson fails on two checks not one

SEVERITY: blocker
EVIDENCE: `python scripts/verify_thumbnail.py <12 files>` — full output, exit 0, `0/12 passed`:

```
FAIL 1_LONGFORM_thumbnail.jpg     ARROW_AIMS_AT_NOTHING ; CHROMA_BLOCKING deviates 3.7 (gate 3.5)
FAIL CARTHIEF_thumbnail.jpg       ARROW_ON_PERSON 2% ; CHROMA_BLOCKING deviates 89.9
FAIL SANCHEZ_thumbnail.jpg        EDGE_ARTEFACT ridge 0.89H (longest 0.36H) ; ARROW_AIMS_AT_NOTHING
FAIL OFFERUP_thumbnail.jpg        EDGE_ARTEFACT ridge 2.02H (longest 0.59H) ; CHROMA_BLOCKING 5.6
FAIL MONKEY_thumbnail.jpg         EDGE_ARTEFACT ridge 0.71H (longest 0.26H) ; ARROW_AIMS_AT_NOTHING
FAIL ROMERO_thumbnail.jpg         EDGE_ARTEFACT ridge 0.92H (longest 0.55H) ; CHROMA_BLOCKING 10.4
FAIL Q3_detail.jpg                EDGE_ARTEFACT ridge 4.48H ; ARROW_AIMS_AT_NOTHING ; CHROMA_BLOCKING 90.9
FAIL Q1_noregroup.jpg / Q2_surgical.jpg / Q4_light.jpg / Q3SET/SANCHEZ.jpg / Q3SET/OFFERUP.jpg  (all 2-3 failures)
0/12 passed
```

STATE.md:186 records only the arrow-aim failure on Thompson. The chroma failure on Thompson (3.7 against `flat_chroma_dev=3.5`, `scripts/verify_thumbnail.py:49`) is not recorded anywhere I could find. `--calibrate` on Thompson also reports `nf=4` — four faces — against STATE.md:295's rule that "the measured set never runs more than two."
WHY-IT-MATTERS: The file's own stated principle is that the competitor set is ground truth, so a gate that fails its own ground truth on two of its checks is not calibrated on either. A gate at 0/12 has no discriminating power at all: it cannot tell a good thumbnail from a bad one, so nobody can act on it, and in practice nobody does — five thumbnails shipped through it. It is currently a source of false confidence ("we have a gate") rather than a check.
PROPOSAL: Recalibrate every threshold in `THRESH` against the Thompson reference plus the measured competitor set, so the reference passes by construction — that is what "ground truth" means operationally. Specifically: `flat_chroma_dev` must exceed Thompson's own value (see F5 — but fix the metric first, because the current number is not measuring chroma blocking), and `arrow_aim_miss_frac=0.16` must admit Thompson's actual ray geometry. Then re-run: any file still failing is a real defect. Do not raise thresholds one at a time until things pass — set them from the reference distribution.
COST: Half a day. Risk: medium — a mis-set threshold silently readmits the defect it was written for, so each threshold needs the reference value recorded next to it in the source, the way `arrow_person_overlap` already is.

## F5: `verify_thumbnail.flat_chroma()` measures the defendant's orange jail scrubs, not a flat bright area — its 89.9 and 90.9 readings are the scrubs' real colour, and there is no luma floor to prevent it

SEVERITY: blocker
EVIDENCE: `scripts/verify_thumbnail.py:422-444` scans 100x100 windows from `y=0.08H` to `0.75H`, keeps any window with `std(Y) <= 12`, and picks **the one with the highest mean luma** — with no minimum-luma requirement. I replicated that exact selection and printed which window it lands on:

```
CARTHIEF_thumbnail.jpg    window x= 518 y= 477 (y/H=0.662)  meanY=117.6  dev=89.9  meanRGB=(203,97,1)
QUALITY/Q3_detail.jpg     window x= 638 y= 497 (y/H=0.690)  meanY=113.6  dev=90.9  meanRGB=(207,88,5)
1_LONGFORM_thumbnail.jpg  window x= 638 y= 117 (y/H=0.163)  meanY=245.6  dev= 3.7  meanRGB=(245,247,241)
OFFERUP_thumbnail.jpg     window x=1158 y=  57 (y/H=0.079)  meanY=218.2  dev= 5.6  meanRGB=(223,218,211)
```

meanRGB (203,97,1) at two-thirds frame height is the orange jail jumpsuit. Its meanY is **117.6** — the function accepted a mid-dark window as "the flattest *bright* region" because nothing in it requires brightness. On the two files where a genuine ceiling window happens to win (Thompson at meanY 245.6, OfferUp at 218.2) the readings are sane (3.7, 5.6); on the two where the courtroom ceiling carries moulding lines and fails `std<=12`, the scrubs win and the number jumps 16-24x. `measure()` computes a text mask two lines later (`glyphs, tmask = text_glyphs(bgr)`) and never passes it to `flat_chroma`, so coloured graphics are unguarded too.
WHY-IT-MATTERS: This is the check that exists specifically because a luma blockiness metric missed the artefact Nathan saw by eye. It is now the deciding number in a build comparison (STATE.md's Q1/Q2/Q3/Q4 table) and a hard gate, and on the flagship case it is reporting the saturation of a jumpsuit. Q2 was **disqualified** on this column ("Q2 is disqualified on chroma (14.96 — the blocky artefact back at seven times the reference)"), which means a build decision may have been made on a measurement of clothing. It also explains the 3-way contradiction in F6.
PROPOSAL: Three concrete changes to `flat_chroma`: (a) require `mean(Y) > 185` on the selected window and return `None` if no window qualifies, rather than degrading to the brightest thing available; (b) exclude any pixel in `tmask` (already computed in `measure`) and any pixel whose local 24x24 luma std exceeds ~5, which removes glyphs, the arrow and garment folds without ever inspecting chroma; (c) aggregate over **all** qualifying windows rather than the single argmax, so one unlucky window cannot decide the verdict. Then re-derive the 3.5 threshold from the reference set and re-run the Q1-Q4 comparison — the Q2 disqualification specifically needs revisiting.
COST: ~2 hours to fix and re-derive. Risk: medium — it changes a number already written into a decision record, so the Q1-Q4 table and the "Q3 is chosen" conclusion must be re-checked rather than assumed to survive.

## F6: "Q3 carries chroma deviation 5.54" is STILL TRUE and I reproduce it at 5.56 — but the repo holds three mutually exclusive numbers for that same file, 5.54 vs 1.685 vs 90.9

SEVERITY: high
EVIDENCE: My own method, written without reading `verify_thumbnail.py` first: RGB→YCbCr (BT.601), tile into 8x8 blocks, keep blocks with `mean(Y) > 185` AND `mean(local 24x24 luma std) < 5.0` (the neighbourhood test excludes every glyph and the arrow via their black strokes, without looking at chroma), then per-block `hypot(mean(Cb)-128, mean(Cr)-128)`. Column A is the mean of that; column B is the block-to-block chroma spread within each 3x3 block window — the actual *blocking* signature Nathan described ("coloured 16x16 blocks in flat bright areas"):

```
file                       A: chroma dev   A p95   B: blocking   blocks
CARTHIEF_thumbnail.jpg              6.24   16.34          1.35      574
SANCHEZ_thumbnail.jpg               6.76   27.84          0.78     1046
OFFERUP_thumbnail.jpg               9.88   34.21          0.98     1193
MONKEY_thumbnail.jpg                9.15   36.04          1.63     1749
ROMERO_thumbnail.jpg               16.11   36.40          2.54     1027
1_LONGFORM_thumbnail.jpg           10.09   37.92          0.70      675
QUALITY/Q1_noregroup.jpg            5.51    9.58          1.22      395
QUALITY/Q2_surgical.jpg             4.60   14.18          0.87      453
QUALITY/Q3_detail.jpg               5.56   17.65          1.01      486
Q3SET/SANCHEZ.jpg                   6.27   26.31          0.61      891
Q3SET/OFFERUP.jpg                   2.07    3.41          0.49      466
```

Q3_detail = **5.56** against the recorded **5.54**. That confirms the STATE.md figure. But `QUALITY/Q3_detail.jpg.meta.json`, written by the build script at 04:21:27, records `"flat_area_local_chroma_deviation": 1.685` for the same file, and `verify_thumbnail.py` run today returns **90.9** for it. Also note column B, which nobody has measured: **`ROMERO_thumbnail.jpg` is the worst shipped file on actual blocking (2.54), 2-5x every other**, and it is named as a defect nowhere. My first attempt at this metric was itself contaminated by the yellow headline (p95 came out at 127.9 = saturated yellow on every file); the 24x24 neighbourhood test is what fixed it, and it is the same fix F5 needs.
WHY-IT-MATTERS: Three numbers for one property of one file, spanning 54x, is not a measurement — it is a coin flip that happens to be written down. Q3 was chosen partly on this column and Q2 was disqualified on it. And the file that is genuinely worst on blocking, ROMERO, is invisible to all three because none of them measures block-to-block variation; they all measure distance from neutral, which a warmly-lit cream wall fails legitimately.
PROPOSAL: Pick one definition, put it in one place (`src/boydclips/thumbnail.py`), and have STATE.md, the meta.json writer and `verify_thumbnail.py` all call it — the current state is three implementations. Make it the block-spread metric (column B), not distance-from-neutral: blocking is *variation between adjacent blocks in a region that should be uniform*, and a legitimately cream wall scores high on the current metric while a genuinely blocky one can score low. Re-measure ROMERO before it ships.
COST: ~3 hours including reconciling the three call sites and re-running the build comparison. Risk: medium — same as F5, it moves a number a decision already rests on.

## F7: "SANCHEZ and OFFERUP shorts have not been through the new pipeline" is FIXED and stale — STATE.md contradicts itself 60 lines apart, and an undocumented fourth case (ROMERO) has been left out of both lists

SEVERITY: high
EVIDENCE: `ls -la --time-style=full-iso` plus ffprobe on READY-TO-POST:

```
CARTHIEF_SHORT_FINAL.mp4  34.800s  2026-08-29 00:39:43
SANCHEZ_SHORT_FINAL.mp4   49.142s  2026-08-29 04:01:32
OFFERUP_SHORT_FINAL.mp4   41.900s  2026-08-29 04:02:29
ROMERO_SHORT_CAP.mp4      48.000s  2026-08-28 22:51:09   <- no _FINAL exists
```

The three durations match STATE.md:122-125's own "All three cases pass" table (34.8 / 49.1 / 41.8) exactly, and that table sits **60 lines above** the "What is NOT fixed" bullet at line 182 that says the same two cases have not been through the pipeline. Both were in the file when it was last written (`git log`: `1e56ef1 2026-08-29 04:21:45 "Automate the shorts: one command, five gates, all three cases pass"`, then `babc7b3 04:25:27`). ROMERO has `ROMERO_LONGFORM.mp4` (419.9s), `ROMERO_SHORT.mp4`, `ROMERO_SHORT_CAP.mp4` and `ROMERO_thumbnail.jpg` on disk, appears in neither list, and its `_CAP` measures 12 silent spans ≥0.7s totalling 19.07s of 48.00s (F3) — i.e. it is exactly the state SANCHEZ and OFFERUP were in before the pipeline ran.
WHY-IT-MATTERS: STATE.md is the file CLAUDE.md orders every session to read first, and it now asserts P and ¬P about the same two files. A session that reads the bottom section re-does finished work; one that reads the top misses that ROMERO exists at all. The self-contradiction also makes the rest of the "What is NOT fixed" list untrustworthy by association — which is why this leaf had to re-measure every entry rather than triage.
PROPOSAL: Delete the stale bullet at STATE.md:182 and add ROMERO to the case list with its real state (long-form: 4 spans ≥4s / 17.9s of dead air per F2; short: no `_FINAL`; thumbnail: worst-in-set on blocking per F6). Then make "What is NOT fixed" a derived section rather than a hand-maintained one where possible — most of its entries are things a gate could assert, and a hand-maintained defect list is exactly what drifted here.
PROPOSAL-NOTE: the doc correction is the whole fix for the SANCHEZ/OFFERUP half; ROMERO is real new work.
COST: Doc edit ~30 min. Running ROMERO through `make_short_auto.py` is one command plus a render. Risk: none for the edit.

## F8: "All four captioned shorts shipped as High 4:4:4 Predictive" is FIXED — 21/21 files are yuv420p, decode clean, and A/V drift never exceeds 35 ms

SEVERITY: low
EVIDENCE: `ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,profile,level,pix_fmt,width,height,r_frame_rate,nb_frames,duration -of default=nw=1` over every mp4 in READY-TO-POST. All 21 return `codec_name=h264`, `profile=High`, `level=40`, `pix_fmt=yuv420p`, `r_frame_rate=30/1`. No file returns `High 4:4:4 Predictive` or `yuv444p`. Long-forms are 1920x1080, shorts 1080x1920, audio `aac / LC` throughout (48 kHz on long-forms, 44.1 kHz on shorts).

Decode integrity — `ffmpeg -v error -i <f> -f null -` on all 21 (writes nothing), exit 0, **not one line of error output on any file**.

A/V drift, video-stream duration vs audio-stream duration, worst offenders:
```
SANCHEZ_LONGFORM.mp4   v=443.833  a=443.868   drift 35 ms
MONKEY_LONGFORM.mp4    v=808.933  a=808.926   drift  7 ms
CARTHIEF_LONGFORM.mp4  v=1002.867 a=1002.877  drift 10 ms
1_LONGFORM_Thompson    v=657.700  a=657.711   drift 11 ms
```
35 ms is ~1 frame at 30fps and below the ~45 ms audio-lead perceptual threshold. Nothing here is a blocker.
WHY-IT-MATTERS: The `-pix_fmt yuv420p` fix held across every file, including the ones rendered after it. Worth recording as closed so nobody re-audits it, and worth keeping as a gate — the original failure was *silent* (libx264 inheriting precision from `curves`/`eq` and picking 4:4:4 on its own), so it can return the moment a filter chain changes without anyone touching the pix_fmt line.
PROPOSAL: Correct STATE.md:39 from a live defect to a closed one with the date and the verifying command. Keep the pix_fmt assertion in `make_short_auto.py`'s gate set and add the same assertion to the long-form render path, which does not currently have it — the four files that shipped 4:4:4 were shorts, but nothing structurally prevents a long-form from doing it.
COST: Doc edit, 10 minutes. Extending the gate to long-forms ~30 min. Risk: none.

## F9: The shipped `CARTHIEF_thumbnail.jpg` predates its own fix by 29 minutes and predates the rebuild by 7 hours — so it cannot carry the guard, but I could not confirm the "severed arm" wording on that specific file

SEVERITY: high
EVIDENCE: mtimes, `ls -la --time-style=full-iso`:

```
READY-TO-POST/CARTHIEF_thumbnail.jpg   2026-08-28 21:00:43.250784600
scripts/regroup_plate.py               2026-08-28 21:30:32.016388800   (+29m 49s)
scripts/make_thumbnail_v5.py           2026-08-28 22:02:58.395607400   (+62m)
READY-TO-POST/QUALITY/Q1..Q3           2026-08-29 04:10:26 .. 04:21:27 (+7h)
```

`git log -- scripts/regroup_plate.py` shows a single commit, `c56d8b5 2026-08-29 02:37:17 "Shorts pipeline: word-gap cuts, AV speaker attribution, deblocking"` — the guard reached git 5.6 hours after the thumbnail was written. The shipped file is byte-identical to `AB-THUMBNAILS/CARTHIEF_thumb_A.jpg` (both md5 `cfc75fee40231c137fdedbd12feb46ef`). So the shipped thumbnail is a pre-guard artifact and STATE.md is right that it "is still wrong" in the sense of not having been rebuilt.

What I could **not** establish, stated rather than guessed: whether that file contains a severed limb. My silhouette test (largest orange-scrubs connected component; longest run of consecutive rows whose mask edge moves ≤1px) does not discriminate — shipped file LEFT 79 rows / 0.110H, RIGHT 70 / 0.097H, against the rebuilt `Q3_detail.jpg` at 57 / 0.079H and 121 / 0.168H, i.e. the rebuild scores *worse* on the right edge. `ARM_CHECK.png` (798x770, mtime 21:55:55, the diagnostic that named the defect) template-matches nothing in READY-TO-POST at multiple scales — best NCC 0.581 on Q3_detail, 0.544 on the shipped thumbnail — so I could not determine which build it diagnoses. Reading the shipped image directly, the defendant's silhouette runs continuously to the frame bottom and the only hard edge is the intended composite against Judge Boyd's robe.
WHY-IT-MATTERS: The distinction matters for what gets done. "Not rebuilt" is a five-minute re-render. "Ships a severed arm" is a claim about a specific visible artefact that Nathan reacted to ("it doesnt look good when you have those hard crops"), and if it is attached to the wrong file, the re-render will not fix what he actually saw. Right now the state file asserts the stronger version without a file the assertion was measured on.
PROPOSAL: Two things. (1) Re-render CARTHIEF's thumbnail through the current `make_thumbnail_v5.py` + `regroup_plate.py` path so the shipped file postdates its guard — this is unambiguously owed regardless of the arm question. (2) Record which file `ARM_CHECK.png` was cropped from, in `ARM_CHECK`'s own sidecar or in STATE.md; a diagnostic image that cannot be traced to its subject cannot settle the claim it was made to settle, and this one now cannot.
COST: Re-render ~10 min. Provenance note ~5 min if whoever made it remembers; otherwise it is unrecoverable and the claim should be restated as "not rebuilt" only. Risk: low.

## F10: MONKEY's local thumbnail fix held — it is the only shipped file that clears the chroma gate; the live half is out of this leaf's reach, and ROMERO is the file that actually needs attention

SEVERITY: medium
EVIDENCE: `python scripts/verify_thumbnail.py` on `MONKEY_thumbnail.jpg` (mtime 2026-08-28 21:01:40) returns exactly two failures — `EDGE_ARTEFACT: cut-out outline/halo, ridge length 0.71H (longest 0.26H)` and `ARROW_AIMS_AT_NOTHING` — and **no `CHROMA_BLOCKING` line**. It is the only one of the five shipped thumbnails for which that check does not fire, so the 2026-08-28 deblocking work (saturation knee, chroma median, UnsharpMask threshold 3→10) did hold on this file. My independent metric agrees on direction: block-spread B = 1.63.

Where the local half is *not* clean: on that same independent block-spread metric, `ROMERO_thumbnail.jpg` scores **2.54**, the worst of the six thumbnails measured and 3.6x the Thompson reference (0.70), and its gate run reports `CHROMA_BLOCKING flat bright area deviates 10.4`. ROMERO is named in no defect list anywhere in STATE.md or OPEN-THREADS.

The live half — whether youtube.com still serves the pre-fix thumbnail on the MONKEY video — is not determinable from disk. It needs the YouTube Data API `videos.list(part=snippet)` thumbnail URL for the posted video, fetched and compared against the local file; the `youtube-channel` skill on this machine covers exactly that. Explicitly another leaf's job, not measured here.
WHY-IT-MATTERS: The half of this claim that could be checked is genuinely closed, which is worth knowing so the deblocking work is not redone. But the same audit surfaced a file in worse shape than the one being tracked, which is the general hazard of a hand-maintained defect list: it tracks what someone noticed, not what is worst.
PROPOSAL: Add ROMERO_thumbnail.jpg to the defect list at the same severity MONKEY had, and re-grade it through the fixed `thumbnail.grade()` path — it appears to predate or bypass the 2026-08-28 chroma fix. Separately, hand the live-thumbnail question to whichever leaf holds channel access, with the specific check named: compare the `maxres` thumbnail bytes from `videos.list` against the local `MONKEY_thumbnail.jpg` md5 `e92a72e990cad1dc4149d7a43e157768`.
COST: ROMERO re-grade ~15 min (existing code path). The live check is one API call for another leaf. Risk: low.

## F11: Blackburn is confirmed a 3-tile Zoom grid and the named fix is not implemented — `_concat_filter` still emits trim/setpts with no crop filter of any kind

SEVERITY: medium
EVIDENCE: Both halves of the OPEN-THREADS entry checked separately.

The grid: `out/oncam/blackburn_BADGRID/f04.png` (1280x720, mtime 2026-08-18 04:50:15) is a **3-tile** layout — a wide 187TH DC courtroom shot top-left, Judge Boyd top-right, the Witness tile bottom-centre with black filling the bottom corners. Face sizes measured with OpenCV `haarcascade_frontalface_default` at scaleFactor 1.06, minNeighbors 6: **two faces, 65x65 px and 28x28 px, i.e. 5.1% and 2.2% of the 1280 frame width**. `blur_pad` scales the whole grid to 1080 wide, so those become 55px and 24px on a 1080-wide vertical canvas — the defendant's face occupies about a twentieth of the short's width. That is the thread's complaint, measured. (`out/tilediag/blackburn_frame.png` shows a 2-tile moment from the same source, so the grid count varies through the hearing — "3-4 tile throughout" is right in substance.)

The fix: `src/boydclips/render.py:1146` `_concat_filter` builds, per segment,
`[0:v]trim=start={a}:end={b},setpts=PTS-STARTPTS[v{i}]` and the matching `atrim`/`afade` — the filter chain contains `trim`, `setpts`, `afade`, `concat` and nothing else. `grep -rn "_concat_filter" --include=*.py .` finds only its definition and two call sites (`render.py:1320`, `:1407`). There is no per-beat crop, and no parameter through which one could be passed.
WHY-IT-MATTERS: The thread is filed as "diagnosed, not fixed", and that is accurate — but "`_concat_filter` already trims segments separately, so the crop attaches there" reads like the attachment point is prepared. It is not; `_concat_filter` has no crop parameter and no caller that could supply one, so the work is larger than the note implies. Meanwhile Blackburn stays unpostable, and every multi-tile hearing in the READY-TO-REVIEW set (13 `HEARING_*.mp4` files) has the same constraint.
PROPOSAL: Add a per-segment optional crop to `Segment` and thread it through `_concat_filter` as `crop=w:h:x:y` before `setpts`, defaulting to no-op so existing callers are unaffected. The speaker-tile choice per beat can come from the audio-visual correlation already built for `who_speaks.py` — that machinery exists and is measured at 9/9, so this is plumbing rather than new detection. Verify on Blackburn by measuring face height as a fraction of canvas width in the rendered output, not by reading the filter string.
COST: ~half a day for the plumbing plus the tile-selection wiring. Risk: medium — `_concat_filter` is on the path of every short and long-form render, so the no-op default and a before/after render comparison on an existing short are mandatory.

## F12: The overexposed courtroom light is real and measurable — CARTHIEF_LONGFORM clips 2.06% of pixels on average and 5.63% at worst — and nothing in the render path addresses it

SEVERITY: medium
EVIDENCE: Clipped-pixel fraction measured without writing a frame, by thresholding luma in the filter graph and reading back the mean: `ffprobe -f lavfi -i "movie=<f>,select=not(mod(n\,600)),lutyuv=y='if(gte(val,250),255,0)',signalstats" -show_entries frame_tags=lavfi.signalstats.YAVG`, then YAVG/255 = the fraction of pixels at Y≥250:

```
file                      frames   mean clipped   worst frame
MONKEY_LONGFORM.mp4          41         0.0006       0.0007
CARTHIEF_LONGFORM.mp4        51         0.0206       0.0563
1_LONGFORM_Thompson.mp4      33         0.0148       0.0167
OFFERUP_LONGFORM.mp4         28         0.0005       0.0007
```

Raw `signalstats` on MONKEY_LONGFORM confirms the ceiling is genuinely at the top of the range and not merely bright: every sampled frame after the intro sting returns `YMAX=255` with `YAVG≈75` and `YHIGH≈206-210`. The blown fixture is directly visible in `out/oncam/blackburn_BADGRID/f04.png`, top-centre of the courtroom tile.

Nothing on our side addresses it: `grep -rn -i "bulb\|overexpos\|blown highlight\|clipped highlight" --include=*.py --include=*.md .` returns only `scripts/q3lib.py:356` (a *thumbnail* note that a blown highlight is achromatic) and `src/boydclips/thumbnail.py:336` (recording that our thumbnails clip 0.145 against a competitor's 0.076). Both are thumbnail-side. The video render path has no highlight handling at all.
WHY-IT-MATTERS: The dockets split cleanly — CARTHIEF and Thompson show the ceiling and clip 1.5-2%; MONKEY and OFFERUP barely show it and clip 0.06%. So this is not a global grade problem, it is a per-docket one, which is why an attempt to fix it globally would fail and why matching another channel by eye did not work. It is also now the only OPEN-THREADS item with a number attached, which makes it the one where "does this look natural" can actually be A/B'd.
PROPOSAL: Build one graded sample on CARTHIEF_LONGFORM only, since it is the worst and not yet posted. Highlight recovery is the mechanism, not exposure reduction: a soft knee applied above roughly Y=200 (ffmpeg `curves` with a compressed top segment, which the render path already uses for the tone curve) rolls the ceiling back without darkening faces the way an exposure pull would. Show him a still pair from the same frame and let his eye decide — the thread's own closing condition is "a graded sample he agrees looks natural, not 'edited'", so the deliverable is a comparison image, not a re-render. Target the measured 0.0206 down toward Thompson's 0.0148 rather than to zero; the competitor data in the repo shows winners clip *more* than losers (0.022 vs 0.011), so driving it to zero would be optimising the wrong direction.
COST: ~2 hours to the comparison still. Risk: low — nothing ships until he picks, and the measurement makes the iteration bounded instead of open-ended.

## F13: The documentary opening has no rebuild on disk — every opening builder predates both rejections, so the thread is STILL TRUE but only weakly measurable from here

SEVERITY: low
EVIDENCE: The complete set of opening builders in the repo, `ls -la --time-style=full-iso`:

```
scripts/build_open.py    4266 bytes  2026-08-12 23:05:22
scripts/doc_cards.py     8220 bytes  2026-08-12 04:41:21
scripts/animate_docs.py  7157 bytes  2026-08-14 03:59:05
```

Nothing newer exists; `grep -rn -i "documentary" --include=*.py --include=*.md .` returns only `docs/reference/LONGFORM-ANTIPATTERNS.md` (a monetisation note about documentary framing moving a video from No ads to Limited ads) and two research files about caption register. The rendered artifacts are `castillo_open.mp4` (1,050,662 bytes, 2026-08-12 23:05:31) and the `castillo_open.*` planning files, all from the same 08-12 sitting. So no rebuilt opening has been attempted since the rejections.

What is **not** measurable from disk: whether a rebuild would satisfy him. The thread's requirements — "real records with literal motion highlighting, news footage, evidence photos, and an aerial view of the scene" — are about *sourcing*, and I cannot verify from here whether the Bexar County records, news footage or aerial imagery for any of these cases have been obtained. That is the gating question, not the animation code.
WHY-IT-MATTERS: The thread is filed as an editing task and is really an acquisition task. Item 1 of CLAUDE.md's six-part definition of done is "Download the case's minutes from the source stream", and the rejected version failed by substituting invented cards for real records — which is the no-silent-substitution failure, not a rendering failure. Re-running `animate_docs.py` on nothing would reproduce it exactly.
PROPOSAL: Before any opening is rebuilt, establish what real material exists per case: the Bexar County record for the case number, any news coverage, any evidence photos in the public filing, and whether an aerial of the location is obtainable. If the material is not there for a given case, that case does not get a documentary opening — say so rather than filling the hole with cards. Note this collides with an existing hard stop: STATE.md:257 records that charge and status for Joseph Grant (2024CR011920) are UNVERIFIED and nothing goes in a public description until the record is pulled and sourced. Same material, same blocker.
COST: Unknown until the records question is answered — that is the honest state. The records pull itself is the boyd-clips-data-sources Tyler portal route and is a known procedure; the opening build on top is ~half a day once material exists. Risk: low technically, but shipping invented records on a real named defendant is a factual problem, not an aesthetic one.
