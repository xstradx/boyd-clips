# leaf-3.3 — state, provenance and reproducibility

Scope audited read-only on 2026-08-29: `state/pipeline.db` (+ its one `.bak`), the 34
loose `state/*.json` files, `src/boydclips/state.py`, `src/boydclips/config.py`,
`config/`, `logs/`, and the finished artifacts in
`C:\Users\natha\OneDrive\Desktop\Boyd Clips\READY-TO-POST\`.

### Answer to the central question, up front

**No shipped video in READY-TO-POST can be rebuilt from anything recorded on disk.**
Not byte-for-byte, and for two of the five cases not even approximately. The
database that was built to be the record of truth stopped being written on
2026-08-20 and contains zero rows about any currently shipped artifact. Everything
that has actually shipped since is recorded — where it is recorded at all — in
prose in `STATE.md`, in an untracked 1.4 KB `config/cases.json`, and in filenames.

### Database inventory (measured)

```
$ for t in dockets cases clips publications ledger rescores sqlite_sequence; do
    printf "%-16s " "$t"; sqlite3 state/pipeline.db "SELECT COUNT(*) FROM $t;"; done
dockets          1701
cases            757
clips            50
publications     0
ledger           1
rescores         85
sqlite_sequence  1
```

`publications` — the table whose entire job is "what did we ship" — has never had a
row. `ledger`, the "reliability ledger" that `state.py:promotion_ready()` reads to
decide whether autonomy may advance, has exactly one row, a rejection from
2026-08-18. `clips` has 50 rows, last written 2026-08-20T19:00:43Z, none of which
point at READY-TO-POST:

```
$ sqlite3 state/pipeline.db "SELECT COUNT(*) FROM clips WHERE file_path LIKE '%READY-TO-POST%';"
0
```

### Per-artifact provenance table

Sources checked for each artifact: `clips`/`publications` rows; `config/cases.json`;
a `.meta.json` or other sidecar next to the file; a build command in `STATE.md`;
the source-window encoding in the `work/*/*_h_{t}_{a}-{b}.mp4` filename; `logs/`
(last entry 2026-08-20, nothing after); and `git log` for the script named.

| artifact | mtime | dur | source stream | in/out | exact command | code version | verdict |
|---|---|---|---|---|---|---|---|
| `MONKEY_LONGFORM.mp4` | 08-23 09:38 | 808.9s | `2XkPnvstmRQ` (STATE.md + `work/` filename) | yes: `--offset 5895.0 --in 5915.92 --out-s 6739.30` (STATE.md:204-207) | in prose only | **lost** — `build_case_longform.py` first committed 08-29, worktree mtime 08-27 | **NOT** |
| `MONKEY_thumbnail.jpg` | 08-28 21:01 | — | frames "from src 6733" (prose) | — | STATE.md:409 command contains literal placeholders `<defendant tile frame>` `<judge cut-out>` | `make_thumbnail_v5.py` mtime 08-28 22:02 = 1h **after** the file | **NOT** |
| `CARTHIEF_LONGFORM.mp4` | 08-27 01:30 | 1002.9s | `EwwnbiAQtFk`, window 3554-4697 from filename | partial — `cases.json` says 3574→4628 (1054s), file is 1002.9s, **51s unexplained** | none | lost | **PARTIAL** |
| `CARTHIEF_SHORT_FINAL.mp4` | 08-29 00:39 | 34.8s | via `CARTHIEF_SHORT.mp4` | `short_src_start: 3931.8` in `cases.json`; **no out-point recorded anywhere**; `CARTHIEF_timemap.json` sidecar exists | `run_case.py` (untracked) | `caption_short.py`/`make_short_auto.py` first committed 08-29 | **PARTIAL** |
| `CARTHIEF_thumbnail.jpg` | 08-28 21:00 | — | `judge_t 3944` / `plate_t 4578` in `cases.json` | n/a | no script on disk writes `AB-THUMBNAILS/*_thumb_?.jpg` | uncommitted | **NOT** (and see F3) |
| `SANCHEZ_LONGFORM.mp4` | 08-27 01:31 | 443.9s | `3FMy2Kvu3UA`, window 3683-4448 | `cases.json` 3703→4148 = 445s ≈ 443.9s ✓ | none | lost | **PARTIAL** |
| `SANCHEZ_SHORT_FINAL.mp4` | 08-29 04:01 | 49.1s | via `SANCHEZ_SHORT.mp4` | `short_src_start: 4019.0`, no out-point, **no sidecar** | `run_case.py` | first committed 08-29 | **PARTIAL** |
| `SANCHEZ_thumbnail.jpg` | 08-28 21:00 | — | `cases.json` `judge_t/plate_t 4021` | n/a | none | uncommitted | **NOT** |
| `OFFERUP_LONGFORM.mp4` | 08-27 05:44 | 550.3s | `l19Ijva3Rsk`, window 10550-11137 | `cases.json` 10570→11117 = 547s ≈ 550.3s ✓ | none | lost | **PARTIAL** |
| `OFFERUP_SHORT_FINAL.mp4` | 08-29 04:02 | 41.9s | via `OFFERUP_SHORT.mp4` | `short_src_start: 10881.5`, no out-point, no sidecar | `run_case.py` | first committed 08-29 | **PARTIAL** |
| `OFFERUP_thumbnail.jpg` | 08-28 21:00 | — | `cases.json` `judge_t/plate_t 10884` | n/a | none | uncommitted | **NOT** (and see F3) |
| `ROMERO_LONGFORM.mp4` | 08-27 01:35 | 419.9s | **unknown** | **none** | **none** | lost | **NOT** |
| `ROMERO_SHORT.mp4` | 08-27 03:38 | 48.0s | **unknown** | **none** | **none** | lost | **NOT** |
| `ROMERO_SHORT_CAP.mp4` | 08-28 22:51 | 48.0s | **unknown** | **none** | **none** | lost | **NOT** |
| `ROMERO_thumbnail.jpg` | 08-27 01:52 | — | **unknown** | **none** | **none** | lost | **NOT** |
| `1_LONGFORM_Thompson.mp4` | 08-17 09:52 | 657.7s | `JgvW7oCQxuI` — the 4 `clips` rows for that video are 838.0s / 53.0s / 292.3s / 50.0s; **no row matches 657.7s** | no db row corresponds | none | `1.1.0` (meaningless — see F9) | **NOT** |
| `2_SHORT_Thompson.mp4` | 08-17 09:53 | 32.9s | as above; **no `clips` row matches 32.9s** (verified: `SELECT ... WHERE abs(duration_s-32.9)<3` returns nothing) | no db row corresponds | none | `1.1.0` | **NOT** |
| `CARTHIEF_SHORT_CAP/CLEAN/TIGHT/TIGHT_V2`, `OFFERUP_SHORT_CAP`, `SANCHEZ_SHORT_CAP`, `ROMERO_SHORT_CAP` (7 intermediate mp4s) | 08-28 | — | — | none | none | lost | **NOT** |

Zero artifacts are FULLY REPRODUCIBLE. Six are PARTIAL (source window recoverable
from a `work/` filename or `config/cases.json`; the code that cut them is not).
Everything else is NOT.

### State-file staleness table

`work/` holds 1701 directories containing a `*.transcript.json` (the brief's 1768
counts all subdirectories; 1760 are directories, 1701 have a transcript). The db
sets `transcribed_at` on 1698 of 1701. Measured by counting transcripts whose mtime
is later than the state file's:

| state file | mtime | transcripts written after it | share of corpus it never saw |
|---|---|---|---|
| `archive_transcripts.json` | 2026-08-11 04:56 | 1351 | 79% |
| `dialogue_metrics.json` | 2026-08-17 23:26 | 1350 | 79% |
| `thumb_prefs.json` | 2026-08-18 02:48 | 1350 | 79% |
| `fetch_queue.json` | 2026-08-18 05:29 | 1349 | 79% |
| `moments.json` | 2026-08-18 10:45 | 1349 | 79% |
| `moments_judged.json` | 2026-08-18 11:04 | 1349 | 79% |
| `oncamera.json` | 2026-08-18 11:06 | 1349 | 79% |
| `funny.json` | 2026-08-20 12:56 | 1349 | 79% |
| `goingoff.json` | 2026-08-20 12:57 | 1349 | 79% |
| `competitor_subs.json` | 2026-08-20 15:12 | 821 | 48% |
| `clip_alignment.json`, `clip_phrases.json` | 2026-08-20 15:13 | 821 | 48% |
| `labels.json` | 2026-08-20 17:43 | 821 | 48% |
| `wentthere.json` | 2026-08-20 17:49 | 821 | 48% |
| `handpicked_alignment.json` | 2026-08-20 22:20 | 821 | 48% |
| `pipeline.db` | 2026-08-21 00:11 | 0 | — (but see F1: it stopped for other reasons) |
| everything else (18 files) | 2026-08-21 → 08-22 | 0 | — |

The ranking chain that produced the current shortlist is the *shallowest*: `questions.json`
(08-21 02:39) → `ranked_hearings.json` → `judged_*.json` → `final_shortlist.json`
(08-21 05:16) all post-date the last transcript, so they are complete as of the
corpus. The *taste* chain that trained the scorer is not: `wentthere.json` (500
candidates) and `labels.json` (Nathan's 60 hand ratings) were computed over a corpus
missing 821 of its 1701 transcripts, and `moments.json` over one missing 1349.

---

## F1: The database records nothing about anything currently shipped — `publications` is empty, `clips` stopped on 2026-08-20, and every identifiable shipped case is absent from `cases`
SEVERITY: blocker
EVIDENCE: row counts and max timestamps read directly out of `state/pipeline.db` with sqlite3 3.50.4 on 2026-08-29.
```
$ sqlite3 state/pipeline.db "SELECT COUNT(*) FROM publications;"
0
$ sqlite3 state/pipeline.db "SELECT MAX(rendered_at) FROM clips;"
2026-08-20T19:00:43+00:00
$ sqlite3 state/pipeline.db "SELECT COUNT(*) FROM clips WHERE file_path LIKE '%READY-TO-POST%';"
0
```
Every currently-shipped case is invisible to the db. Cross-referencing `config/cases.json`
and STATE.md against the `cases` and `dockets` tables:
```
CARTHIEF  key=EwwnbiAQtFk:3574   cases-rows-for-video=0  docket.status=transcribed analyzed=None
SANCHEZ   key=3FMy2Kvu3UA:3703   cases-rows-for-video=0  docket.status=transcribed analyzed=None
OFFERUP   key=l19Ijva3Rsk:10570  cases-rows-for-video=0  docket.status=transcribed analyzed=None
MONKEY    key=2XkPnvstmRQ:5915   cases-rows-for-video=0  docket.status=transcribed analyzed=None
```
(ROMERO is not listed because its source cannot be identified at all — F5.)
Only 44 of 1701 dockets ever reached `analyzed`, and `analyzed_at` maxes out at
2026-08-18T10:33:56Z.
Whether anything has been published cannot be settled from disk, because the two
governing documents contradict each other and `publications` is empty either way.
`CLAUDE.md` states: *"Nothing has ever been published from this pipeline. 'Ready'
means rendered and verified on disk — not shipped."* `STATE.md:348` states:
*"MONKEY's local file is fixed but the LIVE video on YouTube still carries the old
blocky thumbnail — it has not been re-uploaded."* One of those is wrong and the
database, which exists to answer exactly this question, answers neither.
The two Thompson files that *do* have `clips` rows disagree with the shipped files:
`clips` says `JgvW7oCQxuI:6698:longform` is 838.0s and `:short` is 53.0s; `ffprobe`
on `1_LONGFORM_Thompson.mp4` returns 657.7s and on `2_SHORT_Thompson.mp4` 32.9s.
WHY-IT-MATTERS: There is no answer to "what is live, where did it come from, and has
this case already gone out" — and two project documents give opposite answers.
Duplicate-publish protection (`state.py:case_published()`)
queries `publications` and therefore returns False for every case that has ever
shipped — the idempotency guarantee in the module docstring ("a case never published
twice") is not in force. `promotion_ready()` reads a ledger with one row. And the
takedown path has nothing to look up: if a defendant complains, nothing on disk maps
a YouTube URL back to a source stream and timestamp.
PROPOSAL: Make `run_case.py` write a `clips` row and a `publications` row (even for a
manual upload: `platform='youtube-manual'`, the URL pasted in) as the last step of
every case, keyed on the same `video_id:start_s` used by `config/cases.json`. Backfill
the five shipped cases by hand from the table above. Add a `--verify` mode that fails
if a file in READY-TO-POST has no `clips` row.
COST: ~80 lines in `run_case.py` plus a one-off backfill script; low risk (append-only
inserts, existing schema, no migration).

## F2: 55 of 128 scripts first entered git on 2026-08-29 — after every shipped artifact was built — so the code that produced them exists in no commit
SEVERITY: blocker
EVIDENCE: Every script named as a builder in STATE.md was untracked for the whole
period in which the shipped artifacts were made. First-appearance dates for
`scripts/*.py`, computed with `git log --diff-filter=A --name-only -- scripts/`:
```
2026-08-10  3
2026-08-11  3
2026-08-19  60
2026-08-20  10
2026-08-21  11
2026-08-29 55      <-- after every shipped artifact
scripts/*.py total: 128   still untracked: 4
  UNTRACKED make_thumbnail_auto.py 2026-08-29 04:54
  UNTRACKED pick_plate.py          2026-08-29 04:46
  UNTRACKED run_case.py            2026-08-29 04:55
  UNTRACKED verify_set.py          2026-08-29 04:55
```
```
$ git log -1 --format='%h %ad' --date=short -- scripts/build_case_longform.py
c56d8b5 2026-08-29
$ ls -la --time-style=long-iso scripts/build_case_longform.py
-rw-r--r-- ... 14649 2026-08-27 01:34 scripts/build_case_longform.py
```
`MONKEY_LONGFORM.mp4` was built 2026-08-23 09:38 by `build_case_longform.py`. The
worktree copy is dated 08-27, four days *after* the render; the only version in git
is dated 08-29, six days after. The 08-23 source no longer exists anywhere.
Same for `make_thumbnail_v2/v3/v4/v5.py`, `make_short.py`, `caption_short.py` — all
first committed in `c56d8b5` (2026-08-29 02:37), which added 100 files at once. There
was no commit at all between `48929d2` (08-21 19:39) and `c56d8b5` (08-29 02:37) — the
entire window in which MONKEY, CARTHIEF, ROMERO, SANCHEZ and OFFERUP were produced.
WHY-IT-MATTERS: `git checkout <sha>` cannot reconstruct the build environment for any
shipped video. If a render regresses, there is no known-good revision to diff against;
if Nathan asks "why does the new one look different", the honest answer is that the
old code is gone. This is the single largest reproducibility hole and it also silently
invalidates every "measured on X" claim in STATE.md, because the code that produced
the measurement is not the code on disk.
PROPOSAL: Commit the 4 untracked scripts and the 2 modified ones now, before any
further work. Then have `run_case.py` stamp `git rev-parse HEAD` plus
`git status --porcelain` into a sidecar next to every artifact it writes, and refuse
to run (or loudly stamp `DIRTY`) when the worktree is not clean. There is currently no
`git rev-parse` anywhere in the codebase — verified:
`grep -rn "git rev-parse\|GIT_SHA" --include=*.py scripts/ src/` returns nothing.
COST: commit is minutes; the SHA stamp is ~15 lines and one subprocess call. Low risk.

## F3: The shipped CARTHIEF and OFFERUP thumbnails are byte-identical to the A/B variants STATE.md records as REJECTED, and nothing machine-readable records which variant was chosen
SEVERITY: blocker
EVIDENCE: STATE.md:355-367 records Nathan's verbatim pick and its decoding:
```
> "i like C on car theif A and B on sanchez and C on offerup ..."
* rejected — CARTHIEF A/B (eyes down at papers), SANCHEZ C (hand resting on
  chin, eyes lowered), OFFERUP A/B (eyes down at the desk)
* picked — CARTHIEF C (eyes level through glasses), SANCHEZ A/B (raised hand
  mid-gesture, eyes level), OFFERUP C (eyes level, mouth open mid-sentence)
```
Hashing the shipped files against the variant set:
```
$ md5sum *_thumbnail.jpg AB-THUMBNAILS/*.jpg | sort
cfc75fee40231c137fdedbd12feb46ef *AB-THUMBNAILS/CARTHIEF_thumb_A.jpg
cfc75fee40231c137fdedbd12feb46ef *CARTHIEF_thumbnail.jpg
32dd0a2aeef4468dfcf3ad6356be38d1 *AB-THUMBNAILS/OFFERUP_thumb_A.jpg
32dd0a2aeef4468dfcf3ad6356be38d1 *OFFERUP_thumbnail.jpg
bf0a194ab2cdb4a5b98e8d3f365849df *AB-THUMBNAILS/SANCHEZ_thumb_A.jpg
bf0a194ab2cdb4a5b98e8d3f365849df *SANCHEZ_thumbnail.jpg
6468b079c0f9449b7feb1bc7fc47c4e5 *AB-THUMBNAILS/CARTHIEF_thumb_C.jpg
a41ddeec90dd547ef8759a7fbf748c99 *AB-THUMBNAILS/OFFERUP_thumb_C.jpg
```
The shipped file equals variant **A** in all three cases — the pattern of a generator
writing index 0, not of a recorded choice being honoured. That happens to match the
pick for SANCHEZ (A/B) and to contradict it for CARTHIEF (picked C) and OFFERUP
(picked C). The files were written in the same sub-second by the same run:
`CARTHIEF_thumb_A.jpg` at `21:00:43.8460`, `CARTHIEF_thumbnail.jpg` at `21:00:43.8560`.
Nothing can settle it, because **no script on disk writes these files**:
`grep -rn "thumb_A\|AB-THUMBNAILS" --include=*.py scripts/` returns nothing, and there
is no `.meta.json` beside any shipped thumbnail.
Either the rejected variant shipped for two of three cases, or the A/B/C labels moved
between the pick and the regrade. Neither reading is resolvable from disk.
WHY-IT-MATTERS: This is the reliability failure in its purest form — an explicit
editorial decision from Nathan, written down in prose, and the artifact on disk
contradicts it with no way to tell whether the output or the note is wrong. The
thumbnail is the single highest-leverage asset on a YouTube video. It also means the
whole "his eye confirms the hit" loop has no closing check: the pick is recorded in a
markdown paragraph and never compared to the bytes.
PROPOSAL: Record the pick in `config/cases.json` (`"thumb_variant": "C"`) and have
whatever produces the A/B set write each variant with a `.meta.json` carrying its
variant letter and input frame time. Add a check to `verify_set.py`: the shipped
`<CASE>_thumbnail.jpg` must hash-match `AB-THUMBNAILS/<CASE>_thumb_<variant>.jpg`, and
fail loudly otherwise. Re-run it against the current five before anything else ships.
COST: ~40 lines plus a `cases.json` field; low risk. Resolving *which* of the two
readings is true needs Nathan to look at the three CARTHIEF and OFFERUP variants again
— that is his call, not a measurement.

## F4: The only artifact on disk carrying a written build command names a script that has been edited twice since — 149 uncommitted lines that change the layout
SEVERITY: high
EVIDENCE: `READY-TO-POST/QUALITY/Q3_detail.jpg.meta.json` is the single best piece of
provenance in the whole tree. It says:
```
"command": "python scripts/thumb_Q3_detail.py --preset carthief --out \".../QUALITY/Q3_detail.jpg\"  (all settings are now the script defaults)"
```
That claim depends entirely on the script not moving. It has moved twice:
```
$ ls -la --time-style=long-iso .../QUALITY/Q3_detail.jpg .../Q3_detail.jpg.meta.json
486727 2026-08-29 04:19 Q3_detail.jpg
  1755 2026-08-29 04:21 Q3_detail.jpg.meta.json
$ git log -1 --format='%h %ad' --date=iso -- scripts/thumb_Q3_detail.py
babc7b3 2026-08-29 04:25:27 -0500
$ ls -la --time-style=long-iso scripts/thumb_Q3_detail.py
45489 2026-08-29 04:45 scripts/thumb_Q3_detail.py
$ git diff --stat scripts/thumb_Q3_detail.py scripts/layout_L3_tight.py
 scripts/layout_L3_tight.py |  26 ++++++--
 scripts/thumb_Q3_detail.py | 149 ++++++++++++++++++++++++++++++++++++++++++---
```
The uncommitted diff is not cosmetic — it adds a bystander-detection pass that moves
the composition:
```
+    def judge_layer(face_h, cx_off=0.0):
-        px = int(round(a.face_cx * W - (jfx + jfw / 2) * s))
+        px = int(round((a.face_cx + cx_off) * W - (jfx + jfw / 2) * s))
+    bystanders = []
```
So running the recorded command today produces a different image; and because the
committed version (04:25) already post-dates the artifact (04:19), even
`git checkout babc7b3` will not reproduce it.
WHY-IT-MATTERS: The `.meta.json` sidecar is the right idea and is the pattern that
should be generalised — but as written it records a *command*, which is only
provenance if the code is pinned. It currently reads as verified provenance while
being unverifiable, which is worse than an absent record because it will be trusted.
Only 3 of ~90 files in READY-TO-POST have such a sidecar at all, and all 3 are
Q1/Q2/Q3 experiment outputs, not shipped assets.
PROPOSAL: Add `"git_sha"` and `"git_dirty"` (plus the SHA-256 of the script itself)
to the `meta` dict written at `scripts/thumb_Q1_noregroup.py:871` and
`scripts/thumb_Q2_surgical.py:1103`, and extend the same sidecar to every shipped
artifact via `run_case.py`. Drop the parenthetical "(all settings are now the script
defaults)" and serialise the resolved argument namespace instead.
COST: ~20 lines in the two existing writers, ~30 in `run_case.py`. Low risk.

## F5: ROMERO has four shipped artifacts and zero provenance anywhere on disk — the source stream is not recoverable
SEVERITY: high
EVIDENCE: `ROMERO_LONGFORM.mp4` (419.9s, 08-27 01:35), `ROMERO_SHORT.mp4` (48.0s),
`ROMERO_SHORT_CAP.mp4` (48.0s), `ROMERO_thumbnail.jpg` (08-27 01:52) all exist in
READY-TO-POST. Exhaustive search for any record:
```
$ grep -rni "romero" . | grep -v .unlazy | grep -v Binary
./data/jail-activity/*.json          (unrelated inmate names)
./research/gaze/gz_*.json            (only measures the finished thumbnail's pixels)
./research/reference/court-trials-tv/subs/NIfDekyr2Iw.en.vtt   (a different channel)
$ grep -rni "romero" "/c/Users/natha/OneDrive/Desktop/Boyd Clips"
(no output)
$ python -c "...": ROMERO in config/cases.json -> absent (keys: CARTHIEF, SANCHEZ, OFFERUP)
$ grep -n "ROMERO" STATE.md
401:and found no face at all on ROMERO. Same failure as the reaction sweep — on this
```
The single STATE.md mention is about a face detector failing, not about how the clip
was cut. The db has five `cases` rows for a "Romero Espinosa Jr." on video
`X4fifbLpvYs`, but no `clips` row references ROMERO and no window in that
video matches the 419.9s render — the 28 `cases` rows for `X4fifbLpvYs` have spans
of 392.0s and 406.0s either side of it, nothing within 5s:
```
$ sqlite3 state/pipeline.db "SELECT case_key,round(end_s-start_s,1) FROM cases
    WHERE abs((end_s-start_s)-419.9)<5;"
SPSHGzlOe8c:5615|Isabel Arias|416.0
9R1jJ_QX1Wg:3045|Mr. Howie|417.0
```
Neither is on a Romero video. The name match is a coincidence, not evidence.
There are exactly 10 `work/*/*_h_*.mp4` source cuts on disk and none of them
corresponds to a ROMERO window — the four configured/known cases account for four of
them and the other six belong to `-4WiCeWxBu0`, `QfKjHJ1A4KM`, `VaTsQzjOUYw`,
`XiWwYFPhPn0`, `cxApCV_usBQ`, `g8D85ATxkGk`.
WHY-IT-MATTERS: If ROMERO is live, or goes live, nothing maps it back to a court
stream and a timestamp. That is the exact record needed to answer a takedown request,
to verify the defendant's name is spelled right, or to re-cut the clip. It also means
`run_case.py --all` silently covers only 3 of the 5 shipped cases while presenting
itself as the whole routine.
PROPOSAL: Identify ROMERO's source by matching the 419.9s render against transcripts
(a frame hash or an audio fingerprint against the 1701 transcripts will find it),
then add it and MONKEY to `config/cases.json`. Until then, do not publish ROMERO.
COST: an hour of search; zero risk (read-only until the JSON entry is added).

## F6: Two sources of truth that overlap on the same primary key have ZERO rows in common, and where they do overlap they disagree
SEVERITY: high
EVIDENCE: `state/final_shortlist.json` keys its 48 rows on exactly the db's
`cases.case_key` format (`video_id:start_s`). Intersection with the `cases` table:
```
final_shortlist entries: 48  distinct keys: 48
keys ALSO in cases table: 0
keys ABSENT from cases table: 48
  e.g. ['-4WiCeWxBu0:2884', '2XkPnvstmRQ:5915', '3FMy2Kvu3UA:3703', ...]
final_shortlist covers 40 videos; 2 of them have any row in cases
```
Same case, two files, different end point:
```
CARTHIEF  json: t=3574.1 span=1103.1    cases.json: 3574 -> 4628  span=1054
SANCHEZ   json: t=3703.4 span=725.1     cases.json: 3703 -> 4148  span=445
OFFERUP   json: t=10570.4 span=547.5    cases.json: 10570 -> 11117 span=547
```
SANCHEZ disagrees by 280 seconds — nearly five minutes of where the hearing ends —
and neither file is marked authoritative. A third overlap, docket duration:
```
=== archive_transcripts.json duration_s vs dockets.duration_s ===
archive_transcripts rows: 350   not in dockets: 0
duration mismatch >2s: 141   e.g. ('SPSHGzlOe8c', 6486.9, 6500.0)  # 13.1s apart
date mismatch        : 0
```
141 of 350 disagree; the db values are rounded to whole seconds (5757.0, 6500.0,
10681.0) while the JSON carries measured decimals.
WHY-IT-MATTERS: 40% of the corpus has two different recorded durations, and the
production shortlist and the database describe two disjoint universes of cases. Any
offset arithmetic — and every clip in this pipeline is offset arithmetic — silently
picks whichever file the script happened to read. The `dockets`/`cases` tables also
carry a `FOREIGN KEY` and index built for a join that nothing performs any more.
PROPOSAL: Pick one. The evidence says the db lost: `analyzed_at` stopped on 08-18 and
the JSON chain is what actually produced the shipped work. Either (a) make
`final_shortlist.json` the input to a script that writes `dockets`/`cases` rows so the
db becomes a derived index rather than a rival, or (b) declare the db read-only
history and delete the FK/schema pretence. Do not leave both. Whichever is chosen,
add a `scripts/check_state_consistency.py` that fails when `final_shortlist.json`
keys, `config/cases.json` spans and `cases` rows disagree.
COST: (a) ~120 lines and a backfill; (b) a docs change and deleting dead writers.
Medium risk either way — the choice is Nathan's, not a measurement.

## F7: No state write is atomic — `open(path, "w")` truncates the file to zero bytes before any data is written, and there is no temp-file-then-rename, no lock and no automatic backup anywhere in the codebase
SEVERITY: high
EVIDENCE: The pattern in every state writer, e.g. `scripts/find_funny.py:68`:
```python
json.dump(rows, open("state/funny.json", "w", encoding="utf-8"), indent=1)
```
and `scripts/find_wentthere.py:228`, `scripts/align_clips.py:158`. The `Path.write_text`
variants (`find_questions.py`, `cut_shortlist.py:122`) truncate identically.
```
$ grep -rn "os.replace" --include=*.py scripts/ src/
(no matches — the one hit is scripts/wm_preview.py:26, a str.replace on a filename)
$ grep -rn "flock\|msvcrt\|portalocker\|filelock" --include=*.py scripts/ src/
(no matches)
$ grep -rn "backup\|shutil.copy.*pipeline.db" --include=*.py --include=*.yaml scripts/ src/ config/
(no matches)
```
Demonstrated on a scratch copy of the same pattern (no project file touched):
```
before: 2290 bytes, parses: True
after open(w), size: 0            <-- truncated at open, before one byte is written
interrupted: simulated interrupt / reboot mid-write
after: 0 bytes
parses: FALSE -> JSONDecodeError Expecting value: line 1 column 1 (char 0)
```
The exposure window is real: `state/questions.json` is 2.01 MB and
`state/goingoff.json` is 1.82 MB, both serialised and written in one call at the end
of a run that scans 1701 transcripts. The one backup that exists,
`pipeline.db.bak-20260820-141142`, is a manual copy — no code creates it — and it is
now 8 days and 1650 dockets stale:
```
dockets    live=1701   bak=51
cases      live=757    bak=757
clips      live=50     bak=50
```
WHY-IT-MATTERS: Nathan reboots constantly (recorded in his memory files). A reboot or
Ctrl-C inside the write window destroys the file outright — not corrupts it,
*empties* it — and there is no rotation to fall back to. `goingoff.json` alone
represents an hour-plus of scanning; `labels.json` is 60 hand ratings that cannot be
regenerated by any machine. The db itself is on `journal_mode=delete` with
`synchronous=2`, which is crash-safe, so the JSON files are strictly the weaker half.
PROPOSAL: One helper — `write_json_atomic(path, obj)` doing
`tmp = path.with_suffix('.tmp'); tmp.write_text(...); os.replace(tmp, path)` — and
replace all ~35 call sites mechanically. Keep one rotated `.bak` per file. Add a
scheduled `pipeline.db` copy so the backup is not a manual artefact of one afternoon.
COST: ~15 lines for the helper plus a mechanical sweep of the writers; very low risk,
and the single highest reliability-per-line change in this territory.

## F8: The scorer's training data and the moment index were computed over a corpus missing 48-79% of the transcripts that now exist, and nothing detects this
SEVERITY: medium
EVIDENCE: measured by comparing each state file's mtime against the mtimes of the
1701 `work/*/*.transcript.json` files (full table above):
```
moments.json          2026-08-18 10:45   1349 transcripts written after it  (79%)
moments_judged.json   2026-08-18 11:04   1349
oncamera.json         2026-08-18 11:06   1349
goingoff.json         2026-08-20 12:57   1349
wentthere.json        2026-08-20 17:49    821  (48%)
labels.json           2026-08-20 17:43    821
clip_alignment.json   2026-08-20 15:13    821
```
Transcript arrivals by day: 345 on 08-11, then **1250 on 08-20** and 99 on 08-21. So
`moments.json` (the source of `moments_judged.json`, which feeds the shortlists) saw
352 of 1701 transcripts. `wentthere.json`'s 500 candidates and the 60 human labels in
`labels.json` that `build_rating_page.py` uses to fit the scorer were drawn from a
pool that is now roughly half the corpus.
No script checks this. `find_questions.py` re-globs `work/*/*.transcript.json` on
every run, but nothing compares its output's age against the corpus, and nothing warns
when a downstream file is older than its input.
WHY-IT-MATTERS: The pipeline is silently ranking over a stale subset, so the "best"
hearings are the best of an arbitrary 21-48% sample. This is invisible — a stale
ranking file looks exactly like a fresh one — and it is a direct answer to "why do
the picks feel hit-and-miss". It also means a rerun would produce a materially
different shortlist, which is itself a reproducibility problem for anything already
chosen from `final_shortlist.json`.
PROPOSAL: Stamp `{"corpus_n": <count>, "corpus_max_mtime": <iso>}` into the head of
every derived state file, and have each consumer refuse (or warn loudly) when the
current corpus exceeds the recorded one by more than a few percent. Re-run the
`moments`/`wentthere` chain over the full 1701 before the next batch of picks.
COST: ~10 lines per writer plus one guard function; low risk. The re-run is compute
time, not risk.

## F9: `spec_version` is a hardcoded constant that has not changed since 2026-08-09, so the one provenance field in the schema records nothing
SEVERITY: medium
EVIDENCE: `src/boydclips/config.py:15` plus the git history of that line and the value stored on all 50 clip rows.
```
$ grep -n "SPEC_VERSION" src/boydclips/config.py
15:SPEC_VERSION = "1.1.0"
$ git log --format='%h %ad' --date=short -S"SPEC_VERSION = " -- src/boydclips/config.py
429e43a 2026-08-09
$ sqlite3 state/pipeline.db "select spec_version, count(*) from clips group by 1;"
1.1.0|50
```
All 50 clip rows carry the same value, spanning renders from 2026-08-10T04:41 to
2026-08-20T19:00 — a period in which `git log` shows the render path being rewritten
repeatedly ("Let each clip be trimmed at either end", "Refit the scorer to Nathan's
labels", "Fix the syntax error that made every button inert").
WHY-IT-MATTERS: `spec_version` occupies the schema slot where a code identity belongs
and makes the table *look* versioned. Anyone reasoning about "which spec produced
this clip" gets a constant. It is the same failure mode as F4 — a provenance field
that will be trusted and is empty.
PROPOSAL: Either bump it as part of the release ritual, or replace it with the git SHA
(F2) and keep `spec_version` for genuine output-format breaks only.
COST: trivial; low risk.

## F10: `config/cases.json` is the right shape for a real per-case registry but is untracked, covers 3 of 5 shipped cases, and takes an already-rendered artifact as its input
SEVERITY: medium
EVIDENCE: The file is 1420 bytes, untracked (`git ls-files config/` returns only
`.env.example` and `pipeline.yaml`), and holds exactly three entries — CARTHIEF,
SANCHEZ, OFFERUP. Each carries source video, transcript, offset, case window, the
frame times and crops for both thumbnail tiles, the copy, and `short_src_start`. It
is read by `scripts/run_case.py:52` and `scripts/make_thumbnail_auto.py:63-64`, both
of which are themselves untracked. `run_case.py` is explicit about the intent:
```
Everything a case needs lives in `config/cases.json` — the source video, its
offset, the tile crops, the copy. Nothing is hardcoded per case in any script, so
adding a fourth hearing is a JSON entry, not a code change.
```
Three gaps against that promise:
1. MONKEY and ROMERO are absent, so `--all` covers 3 of the 5 shipped cases.
2. The short's input is a finished artifact, not a source:
   `"short": "READY-TO-POST/CARTHIEF_SHORT.mp4"`, resolved by `run_case.py` and passed
   to `make_short_auto.py`. `short_src_start` is recorded; **no out-point is**. If
   `CARTHIEF_SHORT.mp4` (56.2s) is deleted, `cases.json` cannot regenerate it.
3. `case_from`/`case_to` reproduces SANCHEZ (445 vs measured 443.9s) and OFFERUP
   (547 vs 550.3s) but not CARTHIEF (1054 vs measured 1002.9s — 51s unexplained).
WHY-IT-MATTERS: This is genuinely the thing that should replace prose-notes
provenance, and it is one `git add` and two entries away from being it. Left
untracked it can be lost by a stray checkout, and it silently defines "all cases" as
a subset.
PROPOSAL: `git add config/cases.json` plus the four untracked scripts. Add MONKEY
(all fields are in STATE.md:204-207) and ROMERO once F5 recovers its source. Add
`short_src_end` so a short is defined by a window on the hearing cut rather than by a
prior artifact. Add the resolved `thumb_variant` from F3.
COST: minutes for the commit; ~30 lines to make `make_short_auto.py` accept a window.
Low risk.

## F11: Nothing prevents two concurrent runs from clobbering the same state file, and 18 call sites open the database directly rather than through `Store`
SEVERITY: medium
EVIDENCE: Nathan runs work in several terminals (recorded in his memory files).
```
$ grep -rln "pipeline.db\|Store(" --include=*.py scripts/ src/ | wc -l
29
$ grep -rn "sqlite3.connect" --include=*.py scripts/ src/ | wc -l
18
$ python -c "...pragma..."
journal_mode: delete
busy_timeout(ms): 5000
synchronous: 2
```
`journal_mode=delete` means a single writer excludes all readers for the duration of
its transaction; a second process gets `database is locked` after the 5-second default
and raises. The 18 direct `sqlite3.connect` call sites bypass `Store` entirely, so the
`PRAGMA foreign_keys = ON` and the `tx()` rollback in `state.py:100-128` do not apply
to them. `state.py` itself holds one long-lived connection per `Store` with no
`WAL`, no explicit `busy_timeout`, and no cross-process lock.
For the 34 JSON files the situation is worse — there is no lock of any kind (F7), so
two runs of the same script race on a truncating write and the loser's data is gone
with no error raised. The only lock in the tree, `scripts/studio_server.py:38`
(`LOCK = threading.Lock()`), is in-process and guards an in-memory `JOBS` dict.
WHY-IT-MATTERS: The failure is silent for JSON (last writer wins, no exception) and
noisy-but-random for SQLite (a `database is locked` traceback mid-run leaves the db
consistent but the run half-done, and there is no resume record). Both make "run it
again and see" an unreliable debugging strategy, which is the practical face of
unreliable output.
PROPOSAL: Set `PRAGMA journal_mode=WAL` and `PRAGMA busy_timeout=30000` in
`Store.__init__` (WAL lets readers proceed during a write, which is the common case
here). Route the 18 direct connects through `Store`. For the JSON files, the
`os.replace` from F7 makes a partial write impossible and reduces the race to
last-writer-wins, which is acceptable; add a `.lock` sentinel only for the long
scanners (`find_questions.py`, `find_wentthere.py`).
COST: 2 lines for the pragmas, ~1 day to route the direct connects; low risk (WAL is
backwards-compatible and the file is already `integrity_check: ok`).

## F12: `state.py`'s own docstring describes guarantees the running system no longer provides
SEVERITY: medium
EVIDENCE: `src/boydclips/state.py:1-9`:
```python
"""Durable pipeline state.

Two jobs:
  1. Idempotency — a docket is never processed twice, a case never published
     twice, even if a run dies halfway and the scheduler retries.
  2. The reliability ledger — the record that decides whether autonomy.mode is
     allowed to advance from `manual` to `auto`.
"""
```
Job 1 rests on `case_published()` (`state.py:196-202`), which joins `publications` —
a table with 0 rows (F1). Job 2 rests on `reliability()` / `promotion_ready()`
(`state.py:353-409`), which read a `ledger` holding exactly 1 row, a rejection dated
2026-08-18. Neither can fire. Meanwhile 1654 of 1701 dockets sit at status
`transcribed`, which `TERMINAL_STATUSES` (`state.py:96`) correctly treats as
retryable — so `pending_dockets()` returns essentially the entire corpus on every run.
```
$ sqlite3 state/pipeline.db "SELECT status, COUNT(*) FROM dockets GROUP BY status;"
analyzed|40
complete|1
discovered|3
no_eligible_cases|3
transcribed|1654
```
Exactly one docket in 1701 has ever reached `complete`.
WHY-IT-MATTERS: The module is careful, well-reasoned code — the comments at
`case_windows()` and `reliability()` document real bugs found and fixed — and it is
now disconnected from the thing that actually ships. That combination is the most
dangerous state for a codebase: it reads as the authority, so any future work will
build on guarantees that are not in force. It is also why the audit's central question
has the answer it does.
PROPOSAL: Decide (per F6) whether `Store` is the record of truth. If yes, wire
`run_case.py` into `save_clip`/`record_publication`/`record_decision` and the
guarantees come back for free — the code is already written and tested. If no, mark
the module's unused half explicitly so nobody trusts it.
COST: wiring is ~80 lines (shared with F1); low risk.
