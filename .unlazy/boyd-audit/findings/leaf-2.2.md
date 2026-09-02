# leaf-2.2 — dead code and duplicate script census

### Method

Reachability was computed with an AST + regex scan over 181 code files
(`.py`/`.ps1`/`.cmd` under `scripts/`, `src/`, `tools/`, `tests/`, repo root)
and 15 markdown files (`*.md` at root, `docs/`, `spec/`). A file counts as
CODE-REFERENCED only if its basename or module stem appears in another
*executable* file — imports, `subprocess` argv, PowerShell invocations. Prose
mentions in `STATE.md` / `spec/` were scored separately, because a mention in a
29,834-byte chronological history is a diary entry, not a call site. `out/`,
`work/`, `state/`, `.git/` and `__pycache__` were excluded from the corpus.
174 targets scanned. Result: **79 code-referenced, 5 doc-only, 90 with no
reference of any kind.**

One correction applied by hand: `src/boydclips/cli.py` scored zero because the
scan's boundary rule rejects a match preceded by `.`, so `boydclips.cli` in
`run_daily.ps1:41` did not match. It is the real entry point and is counted
REACHABLE below. No other target needed this correction.

### The two live entry chains

There are **two**, and they do not share a single line of thumbnail code.

**Chain A — the automated daily run.** `run_daily.ps1:41-44` →
`python -m boydclips.cli run` → `cli.cmd_run` → `pipeline.Pipeline` →
`thumbnail.build()` (`pipeline.py:553`) → `subprocess` to
`scripts/make_thumbnail_v2.py` (`src/boydclips/thumbnail.py:48`), falling back
to `scripts/make_thumbnail.py` (`thumbnail.py:49`).

**Chain B — the routine Nathan is actually building right now**, per `GATES.md`
and `STATE.md`. `scripts/run_case.py` → `scripts/make_thumbnail_auto.py`
(`run_case.py:97`) → `scripts/pick_plate.py` (`make_thumbnail_auto.py:47`) +
`scripts/thumb_Q3_detail.py` (`make_thumbnail_auto.py:91`) → `scripts/q3lib.py`
(`thumb_Q3_detail.py:59`). And `run_case.py:110` → `scripts/make_short_auto.py`
→ `scripts/who_speaks.py` (`:99`), `scripts/tighten_short.py` (`:104`),
`scripts/caption_short.py` (`:157`). Verification: `scripts/verify_set.py`
(`GATES.md:36,44,52,60,68,76`).

### REACHABLE — 34 files

Chain A: `run_daily.ps1`, `src/boydclips/cli.py`, `pipeline.py`, `config.py`,
`state.py`, `publish.py`, `transcribe.py`, `analyze.py`, `records.py`,
`moments.py`, `momentrun.py`, `oncamera.py`, `repeats.py`, `diarize.py`,
`discover.py`, `render.py`, `thumbnail.py`, `censor.py` (imported by
`analyze.py` and `render.py`), `llm.py` (imported by `analyze.py`),
`scripts/make_thumbnail_v2.py`, `scripts/make_thumbnail.py`.

Chain B: `scripts/run_case.py`, `scripts/make_thumbnail_auto.py`,
`scripts/pick_plate.py`, `scripts/thumb_Q3_detail.py`, `scripts/q3lib.py`,
`scripts/verify_Q3_detail.py`, `scripts/verify_set.py`,
`scripts/make_short_auto.py`, `scripts/who_speaks.py`,
`scripts/tighten_short.py`, `scripts/caption_short.py`,
`config/cases.json`, `GATES.md`.

### ORPHANED — 90 files with zero code reference and zero doc reference

Repo root (21): `_bangers.ps1`, `_batch.ps1`, `_ctbeats.py`, `_cthits.py`,
`_ctopen.py`, `_ctpick.py`, `_ctsubs.py`, `_ctvo.py`, `_render_pair.ps1`,
`_renders.cmd`, `_restyle.ps1`, `_vtt2txt.py`, `build_A_NOTEXT.py`, `ct_an.py`,
`ct_an2.py`, `ct_an3.py`, `ct_an4.py`, `ct_an5.py`, `ct_dump.py`, `ct_fetch.py`,
`ct_retry.py`. (`_final.ps1` scored a hit and is AMBIGUOUS, below.)

`scripts/` (69): `_beatdump.py`, `animate_docs.py`, `assemble_final.py`,
`audit_cuts.py`, `backfill_analyse.py`, `batch_vertical.py`,
`build_C_MAGNIFIER.py`, `build_arc.py`, `build_browse_editor.py`,
`build_compilation.py`, `build_editor.py`, `build_open.py`,
`build_rating_page.py`, `build_short_editor.py`, `build_srt.py`,
`build_thompson_v2.py`, `build_thompson_v3.py`, `calibrate_hearingtype.py`,
`case_dossier.py`, `check_vertical.py`, `diag_camacho.py`, `diag_drift.py`,
`diag_identity.py`, `discover_phrases.py`, `find_funny.py`, `find_hearings.py`,
`find_questions.py`, `fix_mutes.py`, `hook_short.py`, `inspect_transcript.py`,
`judge_defendant_voice.py`, `judge_hearings.py`, `judge_nathan.py`,
`layout_L1_system.py`, `layout_L2_eyeline.py`, `layout_L3_tight.py`,
`make_banner.py`, `make_thumbnail_v3.py`, `make_thumbnail_v4.py`,
`make_watermarks.py`, `mine_clip_phrases.py`, `news_cards.py`,
`next_videos.py`, `peek_rescore.py`, `pipeline_map.py`,
`probe_missing_oncamera.py`, `probe_tiles.py`, `pull_archive.py`,
`pull_competitor_subs.py`, `rank_hearings.py`, `repeat_shortlist.py`,
`reverse_edit.py`, `scan_repeats_oncamera.py`, `serve_range.py`,
`shortlist_brief.py`, `split_logo.py`, `studio_server.py`, `sync_dockets.py`,
`thumb_Q2_surgical.py`, `thumb_eval.py`, `thumb_frames.py`, `thumb_picker.py`,
`top_picks.py`, `upscale_tile.py`, `validate_oncamera.py`,
`verify_Q3_detail.py` (see note), `verify_Q4_light.py`, `wm_preview.py`.

Note: `verify_Q3_detail.py` has no *inbound* reference but imports `q3lib`, so
it is the checker for the live Q3 builder and is listed REACHABLE above as well
— it is reachable by intent, orphaned by measurement. That contradiction is
itself the finding: nothing invokes it.

Three `src/boydclips/` modules are reachable only through orphaned drivers and
are therefore dead in practice: `arcs.py` (only `scripts/build_arc.py`),
`priors.py` (only `scripts/case_dossier.py`), `hearingtype.py` (only
`scripts/calibrate_hearingtype.py` and `scripts/top_picks.py`).

### AMBIGUOUS — 50 files

Referenced only by another orphan, or only by prose. The five doc-only ones,
with the exact citation the scan found:
`scripts/build_case_longform.py` ← `STATE.md:204`;
`scripts/cut_shortlist.py` ← `STATE.md:248`;
`scripts/make_thumbnail_quiet.py` ← `STATE.md:156`;
`scripts/review_moments.py` ← `spec/SPEC.md:182`;
`scripts/verify_set.py` ← `GATES.md:36`.

The remaining 45 are code-referenced but only from files that are themselves
orphaned — e.g. `scripts/build_longform.py` is named only by
`scripts/assemble_final.py:108`, which nothing calls; `scripts/caption_probe.py`
only by `scripts/build_thompson_v2.py:17,56`, which nothing calls;
`scripts/caption_variants.py` only by `scripts/calibrate_variants.py:23`, which
nothing calls. `scripts/build_studio.py` is 80,171 bytes / 1,603 lines and is
named only by `scripts/studio.py`, itself orphaned.

---

## F1: The automated daily pipeline still builds thumbnails with make_thumbnail_v2.py, four builder generations behind the one the current routine uses — so a scheduled overnight run and Nathan's own run_case.py produce different thumbnails from the same footage
SEVERITY: blocker
EVIDENCE: The live daily path hardcodes v2. `src/boydclips/thumbnail.py:48-49`:
```
BUILDER = ROOT / "scripts" / "make_thumbnail_v2.py"
FALLBACK_BUILDER = ROOT / "scripts" / "make_thumbnail.py"
```
That module is on the scheduled path — `run_daily.ps1:41` runs
`python -m boydclips.cli run`; `src/boydclips/pipeline.py:22` does
`from . import diarize, discover, momentrun, render, thumbnail`; and
`pipeline.py:553` is `thumbnail.build(`. The subprocess argv is built at
`thumbnail.py:257` (`cmd = [sys.executable, str(BUILDER),`) and executed at
`thumbnail.py:283` (`_run_builder(cmd, out)`); the v1 fallback argv is at
`thumbnail.py:224`. The v2 lineage has four successors —
`v3` → `v4` → `v5` → `thumb_Q3_detail.py`.

Meanwhile the current routine never touches v2. `scripts/run_case.py:97` shells
to `scripts/make_thumbnail_auto.py`, and `make_thumbnail_auto.py:91` shells to
`scripts/thumb_Q3_detail.py` — not v2, not v5. And `STATE.md:406` names a third
answer: "`scripts/make_thumbnail_v5.py` produces `READY-TO-POST/MONKEY_thumbnail.jpg`".

`wc -l` on the family shows how far apart they are: `make_thumbnail_v2.py` 398,
`v3` 229, `v4` 255, `v5` 776, `thumb_Q3_detail.py` 901 lines. The `build`
function is defined 13 times across the repo with 13 distinct AST hashes
(`make_thumbnail_v2.py:182` 80d11a90, `v3:131` a0445b28, `v4:147` 3dc134a2,
`v5:375` d105db0c, `thumb_Q1_noregroup.py:603` da6eacf2,
`thumb_Q2_surgical.py:699` c9b59020, `thumb_Q3_detail.py:305` 55d75695,
`src/boydclips/thumbnail.py:190` 5bd85a93, plus five more) — no two agree.

`thumb_Q3_detail.py:1-40` names five specific defects it fixes that v2 has:
severed limbs from `regroup_plate.py`, matte edge, softness, arrow ray-casting,
chroma blocking. `STATE.md:288` records "The cut-out was masked with the wrong
model. `make_thumbnail_v2.py`'s ..." — a known-bad model in the file the daily
run still calls.
WHY-IT-MATTERS: If the scheduled task ever fires (it is registered per
`run_daily.ps1:3-5`), it ships a thumbnail built by code that is documented in
this repo as producing severed limbs and a wrong matte model, on a monetised
channel, with nobody watching. Worse for the next session: `thumbnail.py` reads
as the canonical implementation because it lives in the package and has a
30-line design docstring, so the obvious move — "fix the thumbnail code, it's in
`src/`" — edits the wrong file entirely and the real builder is three
`subprocess` hops away in `scripts/`.
PROPOSAL: Decide which chain is the product. If Chain B is (and `GATES.md` says
it is), repoint `src/boydclips/thumbnail.py:48` at the Chain B entry
(`scripts/make_thumbnail_auto.py`) and adapt the argv at `thumbnail.py:257-267`
to its `--case`/`--cases`/`--out` interface; if the daily path is not meant to
build thumbnails any more, make `thumbnail.build()` raise with a message naming
`run_case.py` rather than silently producing a v2 render.
COST: A few hours. The argv shapes are incompatible — v2 takes
`--bg/--subject/--cutout` file paths, `make_thumbnail_auto.py` takes a case key
and reads `config/cases.json` — so `thumbnail.py`'s frame-extraction half
(`_sharpest_frame`, the plate-matte locator at `:123`) either has to feed a
generated cases entry or be deleted. Risks breaking the daily run's only
thumbnail output; it currently has no test (`tests/` contains 1 tracked file).

## F2: Every file of the current thumbnail routine is untracked — a fresh clone gets a repo whose own GATES.md cites six commands that do not exist
SEVERITY: high
EVIDENCE: `git status --porcelain` (run at the repo root):
```
 M scripts/layout_L3_tight.py
 M scripts/thumb_Q3_detail.py
?? .unlazy/
?? GATES.md
?? config/cases.json
?? scripts/make_thumbnail_auto.py
?? scripts/pick_plate.py
?? scripts/run_case.py
?? scripts/verify_set.py
```
None of them are ignored — they are simply uncommitted:
```
GATES.md                           ignored=no tracked=NO
config/cases.json                  ignored=no tracked=NO
scripts/make_thumbnail_auto.py     ignored=no tracked=NO
scripts/pick_plate.py              ignored=no tracked=NO
scripts/run_case.py                ignored=no tracked=NO
scripts/verify_set.py              ignored=no tracked=NO
```
(`git check-ignore -q <f>` / `git ls-files --error-unmatch <f>` per file.)

That is 30,704 bytes of real, load-bearing work (`stat -c'%s %n'` on the six,
summed: 4983 + 1420 + 4555 + 5925 + 4348 + 9473): `run_case.py` is the routine
entry point, `make_thumbnail_auto.py` the wrapper whose 20-line docstring
explains why frame choice must be inside the routine, `pick_plate.py` the frame
sweep it depends on, `verify_set.py` the checker for gates G3–G8, and
`config/cases.json` (1,420 bytes) the file that makes the whole thing
per-case-configurable — `run_case.py:3-9` says "adding a fourth hearing is a
JSON entry, not a code change. That is the whole test of whether this
generalises."

`GATES.md` cites these untracked files as the CHECK for six of its ten gates —
`GATES.md:21` (`make_thumbnail_auto.py --help`), `:29` and `:81`
(`run_case.py`), `:36,44,52,60,68,76` (`verify_set.py`). Three of those gates
are already marked `[x]` with recorded evidence.

Last commit is `babc7b3 2026-08-29 04:25:27`; the untracked files were written
between 04:46 and 04:57 — after it. Commit cadence, `git log --format=%ad
--date=short | sort | uniq -c`: 7 on 08-09, 5 on 08-10, 2 on 08-11, then
**nothing until 08-19** (15), 19 on 08-20, 6 on 08-21, then **nothing until
08-29** (3). Two gaps of seven and eight days during which the repo was being
worked on daily — `.gitignore:26` even carries the scar: "--- 2026-08-19:
committing two days of untracked work ---".
WHY-IT-MATTERS: The pattern is established and has already lost visibility
twice. Right now the repo cannot reproduce its own gate evidence: clone it and
`python scripts/run_case.py --list` is `No such file`, so G1, G2 and G9 read as
MET against code that is not there. Nathan's stated complaint is projects that
become "sloppy and broken until he doesn't want to work with them"; a repo whose
HEAD does not contain its current product is the mechanical form of that.
PROPOSAL: Commit the six files now as one commit. Separately, decide whether
`scripts/layout_L3_tight.py` (+26 lines) and `scripts/thumb_Q3_detail.py`
(+149/-12) are finished — `thumb_Q3_detail.py` is the live builder and its
working copy is 149 lines ahead of HEAD.
COST: Minutes, zero risk — it is a commit of files nothing else depends on being
absent. The judgement call is only whether to squash the two modified files into
the same commit or keep them separate.

## F3: Five files still point readers at superseded thumbnail builders, naming three different answers (v1, v2, v5) to "which file builds the thumbnail" — and one of them is the package's own architecture map
SEVERITY: high
EVIDENCE: `grep -rn "make_thumbnail" --include=*.py --include=*.md .` (excluding
`out/`, `work/`, `.git/`, `__pycache__`) returns these stale pointers:

- `scripts/pipeline_map.py:107` — the repo's own pipeline diagram, step 11:
  `"thumbnail.build() → scripts/make_thumbnail_v2.py"`, with constants
  `"subject_w 0.52 · subject_cx 0.78 · sat_gain 1.45 · arrow off"`. This one is
  accurate about the daily path and wrong about the product.
- `spec/PACKAGING.md:142` — ``Construction constants live in
  `scripts/make_thumbnail_v2.py` and``
- `spec/SPEC.md:395` — ``and `scripts/make_thumbnail.py` builds to its rules.``
  (the v1 builder, five generations back)
- `research/reference/courtroomtime/SPEC.md:232` — ``Current constants in
  `scripts/make_thumbnail_v2.py`:``
- `src/boydclips/thumbnail.py:9` — ``All the pixel constants live in
  `scripts/make_thumbnail_v2.py`, measured from ...``

Against `STATE.md:406` ("`scripts/make_thumbnail_v5.py` produces
`READY-TO-POST/MONKEY_thumbnail.jpg`") and `make_thumbnail_auto.py:91`, which
calls `thumb_Q3_detail.py`. So the repo contains four different documented
answers to "which file builds the thumbnail": v1, v2, v5 and Q3_detail.

`scripts/pipeline_map.py` is itself in the 90-file orphan list — nothing calls
it — so the map is both wrong and unreachable.
WHY-IT-MATTERS: Nathan asks for a thumbnail change; the next session greps for
"construction constants", lands on `spec/PACKAGING.md:142`, edits
`make_thumbnail_v2.py`, renders, and sees no change — because `run_case.py`
never touches that file. That is an hour lost per occurrence and it will recur
every time, because the docs are the first thing anyone reads.
PROPOSAL: One pass repointing all five citations at `scripts/thumb_Q3_detail.py`
and `scripts/q3lib.py`, and either delete `scripts/pipeline_map.py` or update
step 11. If `spec/` is meant to describe Chain A specifically, say so in one
line at the top of each file rather than leaving the version bare.
COST: Under an hour, text only, zero runtime risk. The one judgement is whether
`spec/SPEC.md` documents the daily pipeline or the product — if the former, its
v2 reference is correct today and becomes wrong the moment F1 is fixed.

## F4: Dead-air removal is implemented twice with different mechanisms, and the live daily pipeline uses the one STATE.md records as returning zero results on this footage
SEVERITY: high
EVIDENCE: Implementation 1, on the daily path. `src/boydclips/pipeline.py:294`
calls `render.detect_silences(`, defined at `src/boydclips/render.py:580`:
```
def detect_silences(source, noise_db: float = -30.0, min_silence_s: float = 0.30)
...
     "-af", f"silencedetect=n={noise_db}dB:d={min_silence_s}",
```
(`render.py:598`). Enabled by default in config — `config/pipeline.yaml:137`
`trim_dead_air: true`, `:139` `silence_noise_db: -30.0`. Note the call site does
not use the function's `min_silence_s=0.30` default — `pipeline.py:292-297`
passes `min_silence_s=dead_air_s`, i.e. 4.0s:
```
        if lf_cfg.get("trim_dead_air", True):
            dead_air_s = float(lf_cfg.get("dead_air_s", 4.0))
            silences = render.detect_silences(
                source,
                noise_db=float(lf_cfg.get("silence_noise_db", -30.0)),
                min_silence_s=dead_air_s,
            )
```
So the live daily call is silencedetect at -30 dB requiring a 4-second span —
strictly harder to satisfy than any of the four thresholds STATE.md tested.

Implementation 2, in the current routine. `scripts/tighten_short.py:1`:
`"""Remove dead air from a short using WORD GAPS, not silencedetect.` — its
`keep_segments` at `:33-41` walks `words[i][0] - words[i-1][0]`. It is invoked by
`scripts/make_short_auto.py:104`, which is invoked by `run_case.py:110`.

They disagree on the mechanism, and `STATE.md:17-24` records a measurement
against the first one: "**`silencedetect` DOES NOT WORK ON THIS FOOTAGE. Do not
use it.** Measured on CARTHIEF_SHORT.mp4 at -30, -25, -20 AND -18 dBFS: **zero
spans, every time.** ... **Every dead-air pass in this repo before 2026-08-28
used it and was therefore blind.**" The same short had "22 word-gaps over 0.7s
totalling 31.2s of 56.2s — 56% of the runtime".

Stated precisely, because the two claims are about different files: the
`detect_silences` docstring at `render.py:592-595` reports its own measurement —
"Verified against the shipped 34.55s Thompson short, where it found 10 spans
totalling 4.75s". So it worked on Thompson and returned nothing on CARTHIEF at
four thresholds. Either way the daily path's dead-air pass is unreliable across
hearings and the repo already knows it.
WHY-IT-MATTERS: `pipeline.py:280-288` says the daily path previously "shipped"
long-form with "179.6s of silence in runs over 4s across 838s (21.4%), including
a 75s run". If `silencedetect` returns zero spans on a given hearing's room
tone, `trim_dead_air: true` silently does nothing and that is exactly what ships
again — no error, no log line saying "found 0 spans, probably wrong".
PROPOSAL: Move `tighten_short.py`'s word-gap logic into `src/boydclips/render.py`
as the primary and keep `detect_silences` only as a cross-check, or at minimum
make `pipeline.py:294` log a warning when `detect_silences` returns zero spans
on a source longer than a few minutes — a silent zero is the failure mode.
COST: Half a day to unify (the word-gap path needs a word-level transcript,
which `transcribe.Word` already provides). The warning alone is 3 lines and near
zero risk. Unifying risks changing every future long-form's cut list, so it
wants one A/B render before it is trusted.

## F5: The colour grade exists in four divergent implementations with three different algorithms and two different saturation constants
SEVERITY: medium
EVIDENCE: AST-normalised hashing of every `def` in `scripts/` + `src/boydclips/`
(docstrings stripped) found `grade` defined in 4 files, 4 distinct hashes:
```
grade  in 4 files  DIVERGENT(4 variants)
    22a4e363   14L  scripts/layout_L1_system.py:507
    5b79c4d0   15L  scripts/layout_L2_eyeline.py:508
    ea412b98   28L  scripts/layout_L3_tight.py:822
    45c578b5   14L  src/boydclips/thumbnail.py:292
```
Reading them, they are not variants of one algorithm — they are three:
- `layout_L1_system.py:507-520`: LAB gamma solve clamped `(0.62, 1.6)`, then an
  S-curve `x + 0.16*(x-0.5)*(1-|2x-1|)`, then **saturation × 1.08**.
- `layout_L2_eyeline.py:508-522`: RGB gamma solve clamped `(0.75, 1.35)`, then a
  black point at `HOUSE["blacks"]` quantile scaled `0.85`, then **× 1.10**.
- `layout_L3_tight.py:822-849`: black point at a luma percentile, then a gain
  **bisected over 40 iterations** to land the mean on `HOUSE["lum_mean"]`, then
  **× 1.10**. Its own docstring admits "Saturation +10% is a DEFAULT, not a
  measurement."
- `src/boydclips/thumbnail.py:292` is a file-in-place wrapper over a fourth,
  `grade_image`, which is PIL `ImageEnhance` contrast/colour/brightness/unsharp
  — a completely different colour model from the three OpenCV ones.

The same scan shows the pattern is not isolated to grading:
`place_arrow` 4 files / 4 hashes (`thumb_Q1_noregroup.py:513`,
`thumb_Q2_surgical.py:626`, `thumb_Q3_detail.py:169`, `thumb_Q4_light.py:529`);
`draw_arrow` 4 files / 4 hashes; `arrow_poly` 6 files / 5 hashes;
`matte` 4 files / 4 hashes; `_cover` 5 files / 4 hashes
(`make_thumbnail_v2.py:93` 2e26993b vs `v3:90` daa2a84d vs `v4:103`/`v5:139`
f6b9669b vs `thumb_Q3_detail.py:122` b659ac34) — and
`src/boydclips/thumbnail.py:123` documents the fifth copy in its own docstring:
"Replicate make_thumbnail_v2._cover so plate pixels can be located."
WHY-IT-MATTERS: `GATES.md:60-66` (G6) is *specifically* an exposure-matching
gate, quoting Nathan: "sanchez and offerup had different lighting than the first
thumbnail and video so they look really brifht", measured at 118.6 / 147.1 /
155.9 against a Thompson reference of 124.9. That gate cannot be closed while
which grade runs depends on which of four files was invoked, and a hand-copied
`_cover` in `thumbnail.py` means the plate-matte locator drifts from the builder
it is supposed to mirror the moment either is edited.
PROPOSAL: `scripts/q3lib.py` already exists as the shared library for this
family. Move `grade` (the `layout_L3_tight.py` bisect version, since it is the
only one that provably hits a target number and returns its measurements) into
`q3lib`, and have the other three import it. Same for `_cover` — and delete
`thumbnail.py:123`'s hand-copy in favour of an import.
COST: A day, and it is the risky one in this list: three of the four graders are
in files that are otherwise orphaned, but `thumbnail.py`'s is on the live daily
path, so unifying changes daily output pixel values. Do it behind a before/after
render of the same frame with luma means printed.

## F6: q3lib.py was extracted as the shared library but the copies it replaced were never deleted — three files still carry byte-identical duplicates
SEVERITY: medium
EVIDENCE: `scripts/q3lib.py` (405 lines) is imported by exactly two files:
```
./scripts/thumb_Q3_detail.py:59:import q3lib as Q
./scripts/verify_Q3_detail.py:25:import q3lib as Q
```
The AST hash scan shows its functions still living, unchanged, inside three
files that do not import it:
```
rl_deconv  in 4 files  IDENTICAL
    d7ad0c2b    8L  scripts/q3lib.py:233
    d7ad0c2b   10L  scripts/thumb_Q1_noregroup.py:265
    d7ad0c2b   13L  scripts/thumb_Q2_surgical.py:244
    d7ad0c2b   12L  scripts/thumb_Q4_light.py:220

_ycc  in 4 files  IDENTICAL
    21654d80    2L  scripts/q3lib.py:225
    21654d80    2L  scripts/thumb_Q1_noregroup.py:257
    21654d80    2L  scripts/thumb_Q2_surgical.py:236
    21654d80    2L  scripts/thumb_Q4_light.py:212
```
Identical hashes mean the extraction was a copy, not a move. All three hosts —
`thumb_Q1_noregroup.py` (933 lines), `thumb_Q2_surgical.py` (1,163),
`thumb_Q4_light.py` (1,086) — are in the orphan list: nothing in the repo calls
them. That is 3,182 lines of shadow copy against a 405-line library.

The four `thumb_Q*` files share only three top-level `def` names in common
(`draw_arrow`, `main`, `place_arrow`) and all three are divergent, so they have
already drifted apart since the fork.
WHY-IT-MATTERS: `q3lib` is the one piece of deliberate structure in this family
and it is currently 25% adopted. Any fix to the Richardson-Lucy deconvolution or
the YCbCr conversion has to be made in four places or it silently applies to
whichever variant happened to run. And 3,182 lines of near-duplicate makes
`grep` in `scripts/` return four hits for every question, which is the
mechanism behind picking the wrong file.
PROPOSAL: The Q-comparison is decided — `babc7b3 Record Q3 as the chosen
thumbnail approach`. Delete `thumb_Q1_noregroup.py`, `thumb_Q2_surgical.py`,
`thumb_Q4_light.py` and their verifiers `verify_Q1_noregroup.py`,
`verify_Q4_light.py`, or move all five to an `experiments/` directory so `grep`
in `scripts/` stops returning them.
COST: Deletion is minutes and they are committed, so recoverable from git.
Risk: `thumb_Q4_light.py` has 37 top-level defs against Q3's 14 and its `main`
is 260 lines against Q3's 105 — there may be per-hearing handling in Q4 that Q3
lacks. Diff the two `main`s before deleting, or take the `experiments/` option.

## F7: 90 of 174 scripts (52%) have no reference from any code file or any document
SEVERITY: low
EVIDENCE: The scan described under Method. `CODE-corpus=181 DOC-corpus=15
TARGETS=174` / `NO REF AT ALL: 90 | DOC-ONLY: 5 | CODE-REFERENCED: 79`. Full
list in the ORPHANED section above.

Weight, not just count. `wc -l` on the orphans includes
`scripts/layout_L1_system.py` 1,532 lines, `scripts/layout_L3_tight.py` 1,528,
`scripts/thumb_Q2_surgical.py` 1,163, `scripts/thumb_Q4_light.py` 1,086,
`scripts/thumb_Q1_noregroup.py` 933. `scripts/` totals 31,711 lines against
`src/boydclips/` at 8,562 — the scripts directory is 3.7× the package.

Whole abandoned sub-systems are visible in the list: four HTTP servers
(`pipeline_map.py`, `review_moments.py`, `studio_server.py`, `thumb_picker.py`,
each with its own divergent `do_GET`/`do_POST` and an *identical* 2-line
`log_message` — hash 517b93f1 in five files), three editor page builders
(`build_editor.py`, `build_browse_editor.py`, `build_short_editor.py`), and a
`build_studio.py` at 80,171 bytes reachable only from the orphaned
`scripts/studio.py`.
WHY-IT-MATTERS: This is the measurable form of the complaint. Every question
asked of this repo returns four to thirteen candidate files and no signal about
which is live — the `build` function alone is defined 13 times. The cost is paid
on every single session, not once.
PROPOSAL: Move the 90 orphans to `scripts/attic/` in one commit rather than
deleting — history is preserved either way but a directory move makes the live
set (34 files) legible immediately, and anything that turns out to be needed is
one `git mv` back. Do this only after F2 (commit first, then move).
COST: An hour. Risk is low but not zero: the scan cannot see invocations that
exist only in Nathan's shell history or in a `.claude` skill outside the repo,
so an attic move is right and outright deletion is not.

## F8: 21 root-level scratch files were committed in a single catch-up batch on 2026-08-19 and none has been touched since — including ct_an.py through ct_an5.py, five forks of the same throwaway analysis
SEVERITY: low
EVIDENCE: `git log -1 --format='%ad' --date=short -- <f>` against `stat -c%y`
for each root file:
```
_bangers.ps1           2026-08-19  |  2026-08-18
_ctbeats.py            2026-08-19  |  2026-08-18
ct_an.py               2026-08-19  |  2026-08-18
ct_an2.py              2026-08-19  |  2026-08-18
ct_an3.py              2026-08-19  |  2026-08-18
ct_an4.py              2026-08-19  |  2026-08-18
ct_an5.py              2026-08-19  |  2026-08-18
```
— identical for all 21 (`_bangers.ps1`, `_batch.ps1`, `_ctbeats.py`,
`_cthits.py`, `_ctopen.py`, `_ctpick.py`, `_ctsubs.py`, `_ctvo.py`,
`_final.ps1`, `_render_pair.ps1`, `_renders.cmd`, `_restyle.ps1`, `_vtt2txt.py`,
`ct_an.py`, `ct_an2.py`, `ct_an3.py`, `ct_an4.py`, `ct_an5.py`, `ct_dump.py`,
`ct_fetch.py`, `ct_retry.py`, plus `mm.txt`, `moments.txt`, `phrases.txt`). One
commit date, one mtime day, eleven days of nothing since. `.gitignore:26` names
the batch: `# --- 2026-08-19: committing two days of untracked work ---`.

`ct_an*` are five forks of one script, sharing an identical preamble:
```
import json, re, statistics as st
from datetime import datetime
BASE = r"C:\Users\natha\Projects\boyd-clips"
R = {}
for fn in [BASE+r"\ct_meta.jsonl", BASE+r"\ct_meta2.jsonl"]:
```
Identical leading lines against `ct_an2.py` (63 lines): `ct_an3.py` 13,
`ct_an4.py` 12, `ct_an5.py` 15 — same setup, then five different one-off
analyses over the same two input files. One of those inputs, `ct_meta2.jsonl`,
is 0 bytes and is tracked. All 21 are in the ORPHANED list.

Also stranded at root: `build_A_NOTEXT.py` (last commit 2026-08-29), whose
sibling `scripts/build_C_MAGNIFIER.py` lives in `scripts/` — and there is no
`build_B` anywhere (`find . -maxdepth 2 -name "build_B*"` returns nothing). Two
thirds of a thumbnail-concept comparison, split across two directories, both
orphaned.
WHY-IT-MATTERS: These are the first thing anyone sees on `ls` at the repo root —
21 files with underscore prefixes and no README entry, mixed in with
`run_daily.ps1` and `pyproject.toml`. It reads as an abandoned project before
anything else is looked at, and it is the visual half of the "sloppy" complaint.
PROPOSAL: `git mv` the 21 root scratch files plus `mm.txt`, `moments.txt`,
`phrases.txt`, `ct_flat.txt`, `ct_compact.tsv`, `ct_meta.jsonl` and the empty
`ct_meta2.jsonl` into `research/reference/courtroomtime/` — that is what they
analyse, and `research/reference/courtroomtime/SPEC.md` already exists. Move
`build_A_NOTEXT.py` next to `build_C_MAGNIFIER.py` in `scripts/`.
COST: Fifteen minutes. `ct_an*.py` hardcode `BASE = r"C:\Users\natha\Projects\boyd-clips"`
and then `BASE+r"\ct_meta.jsonl"`, so moving the jsonl breaks them — they are
orphaned one-offs whose output is already written into `research/`, so that is
acceptable, but say so rather than discovering it later.

## F9: Build artefacts and a render cache are tracked in git, and the repo is 18.8 GB of generated output against 46.7 MB tracked
SEVERITY: low
EVIDENCE: Biggest tracked files, `git ls-files -z | xargs -0 stat -c'%s %n' | sort -rn`:
```
29683482 assets/models/4xNomosWebPhoto_RealPLKSR.pth
 4885111 assets/models/realesr-general-x4v3.pth
 1098338 scripts/._eval_tmp.png
  744936 assets/fonts/Montserrat-Var.ttf
  658596 assets/fonts/Archivo-Var.ttf
  376196 ct_meta.jsonl
  326096 research/gaze/gz_pick.json
  279746 scripts/_l2cache/census_CARTHIEF_200.json
```
`scripts/._eval_tmp.png` — 1,098,338 bytes, name says temp file — is tracked
(`git ls-files --error-unmatch` succeeds, `git check-ignore` says not ignored).
So is the whole of `scripts/_l2cache/`: 10 files, 9 matte PNGs named
`CARTHIEF_bench_16807_birefnet-portrait.png` etc. plus a 279,746-byte
`census_CARTHIEF_200.json`, all written 2026-08-29 04:10–04:15 — a per-run cache
of one hearing, in version control.

Two model checkpoints totalling 34.6 MB are tracked while `.gitignore:44`
excludes a third (`assets/ecapa/`) on exactly the grounds that would apply to
these: "85 MB of checkpoints, re-downloadable".

Disk split, `du -sm`: `work` 12,100 MB, `out` 6,698 MB, `state` 15 MB, `logs`
1 MB = 18,814 MB generated (all gitignored, `.gitignore:8-12`), against 46.7 MB
across 615 tracked files, of which 34.6 MB is the two `.pth` checkpoints. Actual
source: `scripts/` 31,711 lines + `src/boydclips/` 8,562 lines.
WHY-IT-MATTERS: `_l2cache` is a cache — it will be rewritten on the next run and
show up as a dirty working tree every time, which is how the *real* signal in
`git status` gets buried. That is the same mechanism that lost eleven days of
work twice already (F2).
PROPOSAL: Add `scripts/_l2cache/`, `scripts/._eval_tmp.png`, `assets/models/*.pth`
to `.gitignore` and `git rm --cached` them, with a one-line note next to the
existing `assets/ecapa/` entry saying where the checkpoints download from — the
`ecapa` entry is the model to copy.
COST: Ten minutes. Removing the `.pth` files from tracking means a fresh clone
must download them; nothing in the repo currently documents where from, so that
note is required, not optional. The blobs stay in history either way, so this
shrinks the working tree, not `.git`.

## F10: The NUL file at the repo root is invisible to os.path.isfile but present in os.listdir, so any tree walk that filters on isfile silently skips it
SEVERITY: low
EVIDENCE: Measured directly at the repo root with a Python one-liner; the three probes disagree with each other, which is the whole point:
```
$ python -c "import os; print('os.path.isfile:', os.path.isfile('NUL')); print('in os.listdir:', 'NUL' in os.listdir('.')); print('open().read() bytes:', len(open('NUL','rb').read()))"
os.path.isfile: False
in os.listdir: True
open().read() bytes: 0
```
`os.stat('NUL').st_size` returns 0 and `shutil.copy('NUL', ...)` succeeds
producing a 0-byte file — because on Windows `NUL` resolves to the null *device*
before it resolves to the file, so every read returns the device's empty stream
rather than the file's contents. `ls -la NUL` confirms a real 0-byte file exists
on disk, dated 2026-08-12 23:42.

It is not in git and cannot accidentally be: `git check-ignore -v NUL` returns
`.gitignore:30:NUL	NUL`, added in the same 2026-08-19 catch-up batch, with the
comment at `.gitignore:28`: "Transient run logs and a Windows reserved-name
artefact". `git log --diff-filter=A --all -- NUL` returns nothing, confirming it
was never committed.

Concrete damage measured: none. `tar -cf /dev/null NUL` exits 0. The file is
0 bytes so the isfile/listdir inconsistency costs nothing today. It cannot be
deleted with `rm NUL` from a normal shell — it needs `\\?\` UNC-prefixed
deletion — which is presumably why it is still there.
WHY-IT-MATTERS: It is a landmine only for a future tool that walks the tree and
opens what it finds — an indexer, a packager, a `shutil.copytree` — which would
read the null device and get silence rather than an error. Right now it is
mostly a visible symptom: an undeletable reserved-name file at the root of a
project, which is exactly the surface texture Nathan is describing.
PROPOSAL: Delete it with `Remove-Item -LiteralPath '\\?\C:\Users\natha\Projects\boyd-clips\NUL'`,
which is the only form that reaches the file rather than the device. Keep the
`.gitignore:30` entry — it is cheap insurance against the shell redirect that
created it happening again.
COST: One command, zero risk (the file is empty and untracked). This is
cosmetic; do it last.
