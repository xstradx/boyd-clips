# Boyd Clips — full audit, 2026-08-29

Read-only. 13 specialists, disjoint territories, every finding carrying a command
that was run or a file:line that was read. **107+ findings, 25 blockers.**
Nothing in the pipeline was modified; a gate snapshotting 4,656 files enforced it
and caught the one violation that occurred.

---

### 0. The outcome this is measured against

Nathan's words: a Judge Boyd video maker — clip, short, title, thumbnail — that
runs *"without me putting in much of any input once we get all the styles and
rules down."*

Everything below is scored by one question: **what stands between the current
system and that.**

---

### 1. The finding that reframes everything else

The channel was never a 2-video channel. `@TexasTrialTracker`
(`UCT5Fde6OzBSFRmxw5mPn2CA`, 2,880 subs) has **28 public videos back to
November 2024**, including a Short at **865,301 views**.

The two long-forms this pipeline produced are **the two worst-performing videos
on the channel** — 51 and 72 views, ranked last and second-last of 15, against a
Boyd long-form median of 2,385.

But the Shorts from the same two cases did 5,349 and 1,153, at 446 and 577
views/day — among the highest daily rates on the channel outside the Soto trial.

**Short to long-form carry-over: 1.35% and 4.42%.** Same case, same day:
5,349 people watched the Short, 72 watched the long-form.

So the pipeline's Shorts work and its long-forms do not, and this was knowable
for twelve days and was never looked at. That is the single largest process
failure in the audit, and it is not a code defect.

---

### 2. What the system actually is

**There are two pipelines, and they share almost no code.**

| | the "automated" one | the one that makes the videos |
|---|---|---|
| entry | `run_daily.ps1` -> `boyd run` | `scripts/run_case.py` |
| thumbnails | `make_thumbnail_v2.py` | `make_thumbnail_auto.py` -> `thumb_Q3_detail.py` |
| dead air | `render.detect_silences` (measured blind) | `tighten_short.py` (word gaps, validated) |
| shipped | **nothing, ever** | all 5 live videos |
| in git | yes | **no** |

`scripts/` is 31,711 lines against the package's 8,562. Of 174 script/module
targets, **90 have zero reference of any kind — 52% of the repo is unreachable.**
The `build` function is defined **13 times with 13 distinct AST hashes.**

---

### 3. Why the output is unreliable — the mechanism

It is one pattern, repeated: **the code turns a missing input into a quietly
worse video instead of a stopped run.** CLAUDE.md already names it. It is worse
than documented.

- `pipeline.py` wraps the entire thumbnail stage in a bare `except Exception`
- `render.py` degrades a missing watermark to a `null` filter pass-through
- a missing intro sting is skipped, and the "redundant candidates" list has one
  live entry
- an empty word list produces a header-only `.ass` that ffmpeg burns as nothing
- `cli run` **exits 0 when it produced nothing** — a run where all 7 dockets
  403'd logged "run complete"

And the checkers that should catch it do not work:

- the severed-limb gate needs a silhouette to drop **55% of body height in one
  column**; a severed forearm is ~5%. It passes the known-bad file.
- the one correct limb check is gated behind an env var **nothing in the repo
  sets** — `grep` finds exactly one occurrence, the read itself
- **no CI, no git hook, no scheduled verification.** 97 tests pass in 2.85s and
  import no ffmpeg, ffprobe, cv2, PIL or numpy — zero artifact-level coverage
- three of the six mandatory elements have no checker at all

---

### 4. The human-input count

**18 human decisions per finished video: 6 taste calls, 7 parameters, 2 file
edits, 3 publish/copy steps. 10 of the 18 are reducible with a named mechanism.**

The 6 taste calls: which hearing, the long-form in/out, the Short's segment list,
Judge Boyd's frame, the thumbnail copy, the title.

**One of those six is not taste and is already solved.** `layout_L3_tight.py:169`
defines a de-rolled pitch proxy — *"HIGHER = looking DOWN"* — and asserts his
exact rule at line 1497: `nv <= 0.50, |roll| <= 4`. `models/yunet.onnx` is on
disk. The shipping path never calls it. STATE.md says this could not be
automated; someone built it anyway and nothing was wired.

---

### 5. What the research says about the smart system

Fetched today, 18 URLs. Three things change what should be built:

1. **Thumbnail CTR is collect-now-or-lose-it.** It is not in the Analytics query
   API at all — only in Reporting API bulk report `channel_reach_basic_a1`,
   which starts collecting *the day the job is created* and retains 60 days.
   **No backfill exists.** Every day without that job is history that cannot be
   recovered.
2. **Competitor retention cannot be observed.** The most-replayed heatmap was
   absent on 8 of 8 sampled competitor videos. Views, thumbnails, titles,
   cadence and transcripts are free and unquotaed; retention is not obtainable.
3. **Two policy traps sit on the unattended design.** YouTube's July 2026 rework
   names AI personas discussing *"legal issues"* and template-driven output with
   little variation as non-monetizable. **Do not build AI narration.**

And: `ffmpeg 8.0.1` on this machine already ships `blackdetect`, `freezedetect`,
`scdet`, `ssim`, `psnr` and `libvmaf` — deterministic render QC needs zero new
installs. Verified locally.

---

### 6. The proposed changes, in the order they should happen

The order matters more than the list. Two sequencing rules came out of the
audit and both are counter-intuitive:

- **Make failure visible BEFORE making it fail.** Turn on fail-closed first and
  runs start dying while we still do not know how much was already broken.
- **Fix the checkers before wiring them.** Two currently pass the exact file
  they were written to catch. Wiring a lying checker is worse than none.

## F1: Start the CTR clock today - the only item whose value decays permanently
SEVERITY: blocker
EVIDENCE: `videoThumbnailImpressions` is absent from the Analytics query API metrics page; it exists only in Reporting API bulk report `channel_reach_basic_a1` (`video_thumbnail_impressions`, `video_thumbnail_impressions_ctr`), added 2026-01-15, and the docs state "the first available report will be for the day that you scheduled the job", 60-day retention. Verified separately by the driver: `C:\Users\natha\.claude\secrets\` does not exist and no `*client_secret*` exists anywhere under `~/Projects`.
WHY-IT-MATTERS: There is no backfill. Every day this is not running is thumbnail CTR history that can never be recovered - and CTR is the only number that answers "does this thumbnail work", the exact question the system is eventually meant to answer for itself.
PROPOSAL: Nathan does the one-time Google OAuth setup (his account, his consent click). Then create the `channel_reach_basic_a1` and `channel_basic_a3` reporting jobs plus a daily fetch into a local store. Build no learning logic yet.
COST: Five minutes of his time, half a day of mine. Zero risk. Doing it in a month costs a month of unrecoverable data.

## F2: Commit the current production system before touching anything else
SEVERITY: blocker
EVIDENCE: `run_case.py`, `make_thumbnail_auto.py`, `pick_plate.py`, `verify_set.py`, `config/cases.json` and `GATES.md` are untracked - 30,704 bytes, none gitignored, simply uncommitted. `git log` shows no commit between 08-21 19:39 and 08-29 02:37, the entire window in which MONKEY, CARTHIEF, ROMERO, SANCHEZ and OFFERUP were built. `.gitignore:26` carries the scar of last time: "committing two days of untracked work".
WHY-IT-MATTERS: That set of files IS the system that makes the videos. One bad edit or one crash loses the only working configuration in the project, and no shipped artifact could be rebuilt even in principle.
PROPOSAL: Commit those six files as-is, no cleanup, before any other change. Then have `run_case.py` stamp `git rev-parse HEAD` into a sidecar beside every artifact and refuse to run on a dirty worktree.
COST: Minutes for the commit, ~15 lines for the stamp. No risk.

## F3: Add an elements block to the manifest - the highest-leverage 30 lines in the repo
SEVERITY: blocker
EVIDENCE: `manifest.json` stores path/title/duration; `REVIEW.txt` prints duration/title. Neither records whether any of the six mandatory elements was applied. Every value is already computed and in scope: `raw_s - kept_s` at `pipeline.py:311`, `mode` at `:477`, `intro` at `:384-390`, `len(events)` at `render.py:1120`.
WHY-IT-MATTERS: This is why nineteen instances of missing-asset tolerance survived. The warning line is not a weak signal, it is the ONLY signal, and it scrolls past unread under Task Scheduler. Recording the six makes every other defect self-reporting, and it must land FIRST so the scale of existing damage is measurable rather than guessed.
PROPOSAL: Write a six-key elements block into the manifest and a six-line checklist into REVIEW.txt. Change no render decision.
COST: ~30 lines, zero behaviour risk. Nothing else in the audit has this ratio.

## F4: Stage renders and promote only on pass
SEVERITY: blocker
EVIDENCE: `make_short_auto.py:193` prints REFUSED and exits non-zero, but the failed file is already written to `READY-TO-POST/{CASE}_SHORT_FINAL.mp4` by `run_case.py:113`. The refusal exists only in an exit code and in scrollback; on disk the file is named `_FINAL` and is indistinguishable from a passing one. Independently confirmed by the driver during this audit: an agent wrote `NOW.png` into the same folder and it sat there looking like a deliverable.
WHY-IT-MATTERS: READY-TO-POST is the folder a human grabs from. If a refused render sits in it under a `_FINAL` name, the refusal did not happen.
PROPOSAL: Render to a staging path, run the checks against that, `os.replace` into READY-TO-POST only when all pass; on failure move to `_QUARANTINE/` with the failing check names in the filename.
COST: ~15 lines in one file plus a matching change in run_case.py. Near-zero risk; it strictly reduces what reaches the publish folder.

## F5: Fix the two limb checkers before wiring anything, because both currently lie
SEVERITY: blocker
EVIDENCE: `verify_set.py:173` fails only when the silhouette drops `worst > 0.55 * span` - 55% of body height in a single column. Against controls: known-bad `CARTHIEF_thumbnail.jpg` measures 32/676 (4.7%) and produces NO failure; known-good Thompson measures 26/715 (3.6%). The metric cannot separate them. The correct check, `verify_thumbnail.silhouette_loss` (1% area loss), is gated at `verify_thumbnail.py:484` behind `os.environ.get("THUMB_SOURCE_PLATE")`, and driver-verified `grep -rn THUMB_SOURCE_PLATE` returns exactly one hit in the whole repo: that read itself. Nothing sets it, so `limb_loss` is always None.
WHY-IT-MATTERS: Two limb checkers, zero working ones, and the gate reads as MET. Same defect class as the caption checker that scored 0/5 wrong on a correct render - a checker never tested against a known answer proves nothing.
PROPOSAL: Delete the column-jump metric, use the 1% area rule, add a `--plate` flag, and emit an explicit LIMB_NOT_CHECKED line when no plate is given so an unrun check is visible rather than absent.
COST: ~30 lines; the correct measurement already exists in the sibling file. The real cost is that the gate must be un-ticked and the thumbnails re-checked.

## F6: Fix the gates that pass vacuously on empty input
SEVERITY: blocker
EVIDENCE: `make_short_auto.py`'s dead-air gate is `not big` where `big == []`, so an empty word list returns PASS. Its A/V-sync gate calls `probe()` with no returncode test, so on a broken file `float("" or 0)` makes both durations 0.0 and they match. Separately `build_ass` writes a header-only `.ass` on an empty word list and ffmpeg burns it as nothing - a caption-free short that passes the caption stage.
WHY-IT-MATTERS: The repo's best verifier returns PASS on exactly the failure it was built to catch. A gate that cannot fail is worse than no gate, because it issues a completion certificate.
PROPOSAL: Every gate asserts non-empty input before asserting the property. `build_ass` raises rather than writing a zero-event file. `probe()` checks the returncode.
COST: ~8 lines across three files. Risk: cases whose transcript does not cover their beats now fail loudly instead of shipping a silent short, which is the point.

## F7: Make missing brand assets fail, and fix the path that has never resolved
SEVERITY: blocker
EVIDENCE: `assemble_final.py:20-21` points at `C:\Users\natha\OneDrive\Desktop\boyd-brand\`. Driver-verified: `ls` returns "No such file or directory". The real folder is `Desktop\Boyd Clips\boyd-brand\`. So `if STING.exists():` at :113 is false on every run with no else branch - it prints nothing at all - and `if LOGO.exists():` at :145 falls through to `marked = joined`. Elements 3 and 4 are off right now, not latently. Separately `render.py` degrades a missing watermark to a null filter and `pipeline.py` wraps the whole thumbnail stage in a bare `except Exception`.
WHY-IT-MATTERS: CLAUDE.md says a missing element is a bug, not a preference. The code says the opposite in nineteen places, and in this one it does not even log.
PROPOSAL: Correct the paths, then make the guards fail closed - if brand assets are configured they are required, so raise. Route through one resolver rather than hardcoded absolute paths.
COST: Low. Risk: scripts that currently succeed will start failing until paths are fixed. Intended.

## F8: cli run must not exit 0 on a run that produced nothing
SEVERITY: blocker
EVIDENCE: `cli.py:140-142` returns 0 on "no clips produced this run"; `run_daily.ps1:38-41` then logs "run complete" and exits 0. Measured on the real 2026-08-14 run: 7 dockets discovered, every one died on `yt-dlp HTTP error 403 Forbidden`, zero clips, exit 0.
WHY-IT-MATTERS: An outage is indistinguishable from a quiet court day. This is how the pipeline went 16 days without ingesting and nothing said so.
PROPOSAL: Distinct non-zero code when dockets were discovered but zero clips resulted; a genuinely empty channel day stays 0. `run_daily.ps1` treats that code as alertable. Add a doctor check that warns when MAX(docket_date) is more than 3 days stale.
COST: ~10 lines plus a branch. Risk: days where every case fails the safety gate now exit non-zero, so that case needs excluding explicitly.

## F9: Fix the off-by-one that silently deletes 2,863 hearings
SEVERITY: blocker
EVIDENCE: `find_called_hearings.py:85-94`. The while loop exits on the first index whose time EXCEEDS MAX_S, then assigns that index to t1, so the capped span is by construction over MAX_S and the next line discards it. Driver-verified by reading the code directly. Across the corpus: 6,997 call-to-call runs, 2,863 over 1200s, all dropped; `called_hearings.json` holds 244 rows.
WHY-IT-MATTERS: The discarded pool is up to 4.6x the entire candidate list, and biased toward exactly the long multi-exchange hearings needed for 8+ minute long-form. The comment says "cap an over-long run"; the code deletes it.
PROPOSAL: Step back one word after the loop. Better, emit successive MAX_S windows across a long run so the tail of a 40-minute run is also a candidate. Then re-scan.
COST: Two-line fix, then a full re-scan of 1,702 transcripts (minutes, CPU only). Everything keyed to the current 244 must be regenerated.

## F10: Replace the dead-air THRESHOLD with a density measure - the rule is structurally wrong
SEVERITY: high
EVIDENCE: Corrected during the audit. An earlier draft claimed up to 44.7% dead air with astats columns reversed; re-measured at the pipeline's own -30 dBFS definition, **all six long-forms have ZERO spans over 4s. Element 2 passes its literal test.** But at -30 dB / 0.30s, CARTHIEF is 35.5% silent across 381 spans with the longest contiguous span 3.94s - and every file's longest sits just under the 4.0s line (2.24-3.94s). CARTHIEF ships a 37.3s stretch at src 441.75s whose RMS is -36.81 dB against -21.74 dB for speech; the detector sees 27 sub-spans inside it, longest 1.71s. The posted Thompson is 31.3% silence.
WHY-IT-MATTERS: The pipeline is passing its own dead-air gate while a third of every long-form is silence, because the silence arrives in sub-threshold chunks. A "no span over 4s" rule cannot catch this no matter what number is chosen. This is a plausible mechanism for 51- and 72-view long-forms and it was invisible to every check we had.
PROPOSAL: Replace the max-span threshold with a windowed density gate - reject when any 60s window exceeds N% silence - and route long-forms through the validated word-gap cutter, which measures gaps between words rather than absolute level. Also narrow STATE.md's claim: silencedetect is blind on already-tightened SHORTS (correctly, they have no gaps left), but finds 381/283/248 spans on the long-forms. Left as written it sends the next session rebuilding six videos that measurement says are fine on the letter of the rule.
COST: Moderate. The density gate is ~20 lines. Re-rendering six long-forms is CPU time. Risk: a density gate will fail the current set, which is the point.

## F11: Stop uncensored profanity reaching a published description
SEVERITY: high
EVIDENCE: `cli.py:248` passes `context={"hook_line": case.get("hook_quote", "")}` - the raw quote - while `pipeline.py:797` passes the censored `result["package"]["hook_line"]`. Driver-verified by reading both. Two paths, one censored, one not; the uncensored one is the approve/publish path.
WHY-IT-MATTERS: The standing rule is profanity stays in the audio and is censored in every text surface. This puts it in a YouTube description.
PROPOSAL: Censor at one place, the packaging step, so no caller can pass the raw quote. Add a test asserting the published description contains no uncensored token.
COST: A few lines plus one test. No risk.

## F12: Wire verification so it runs without anyone typing it
SEVERITY: blocker
EVIDENCE: No `.github/`, no pre-commit config, no installed git hook, no pytest config in `pyproject.toml`. Grepping the entire pipeline for any verify/check/audit call returns exactly one hit: `run_case.py:109`. The 97 tests pass in 2.85s and import no ffmpeg, ffprobe, cv2, PIL or numpy - zero artifact-level coverage. Three of the six mandatory elements have no checker of any kind.
WHY-IT-MATTERS: Every checker in this repo ran once when it was written and never again. That is how four broken checkers stayed simultaneously true and undetected.
PROPOSAL: (a) a pre-commit hook running the 2.85s suite - ten minutes of work; (b) `run_case.py` gates promotion into READY-TO-POST on the repaired checkers; (c) the validated gate set - caption presence AND side (validated at 12,914-38,207px in the caption half against max 2,878 uncaptioned, a 4.5x gap), dead-air measured on the RENDERED audio, limb via area loss, framing via the already-correct `verify_render.py` that nothing calls.
COST: A few hours; (a) is ten minutes. Requires F5 and F6 first or the gates block on their own bugs.

## F13: Wire the gaze detector that already encodes his rule
SEVERITY: high
EVIDENCE: `scripts/layout_L3_tight.py:169` defines a de-rolled pitch proxy documented as "HIGHER = looking DOWN", gated at :493, sorted on at :500, refused on at :880 and asserted at :1497 as `chk("Judge Boyd eyes LEVEL not down (nv <= 0.50, |roll| <= 4)")`. `models/yunet.onnx` is present, 229,738 bytes. Driver-verified: grepping the shipping path (`run_case.py`, `make_thumbnail_auto.py`, `thumb_Q3_detail.py`) for `layout_L3_tight` or `yunet` returns no matches.
WHY-IT-MATTERS: STATE.md records this as an irreplaceable taste call after three metrics were tried and failed. A fourth was built, encodes his stated rule exactly, and the shipping path ignores it in favour of a hand-set timestamp. This is one of the six taste calls removed for the cost of a validation run.
PROPOSAL: Score the detector against his nine already-labelled picks first. If it clears them, wire it into the thumbnail path; if it does not, say so and keep the contact sheet.
COST: One validation run. Do not wire it before the validation - that would repeat the exact mistake this audit found four times.

## F14: Implement the one title rule that was measured
SEVERITY: high
EVIDENCE: Nothing on the shipping path generates a title. `config/cases.json` has 13 fields and no title/description/tags. The p=0.0068 finding - titles opening with the literal string "Judge Boyd", 14/15 winners against 4/10 losers - appears only in `research/THUMBNAIL-MEASURED-2026-08-23.md:392` and `STATE.md:452`, with zero hits in `prompts/`, `src/` or `scripts/`. All four pipeline uploads shipped with `tags = []`, and the one long-form title that breaks the rule is Thompson's, the 72-view video.
WHY-IT-MATTERS: The channel's own back catalogue follows the pattern and outperforms; the pipeline's output does not follow it and underperforms. n is small, so this is a default to adopt rather than a law - but adopting a measured default costs nothing.
PROPOSAL: Add title/description to `config/cases.json`, port the rule into `prompts/package_post.md` as a hard constraint, and add a mechanical post-check with an override flag.
COST: One prompt edit plus a ~10-line validator. Low risk; keep the override because the rule came from one channel's 25 videos.

## F15: Restart ingest, and decide about the lost fortnight
SEVERITY: blocker
EVIDENCE: Driver-verified: `Get-ScheduledTask` matching "boyd" returns count 0 - the daily task was never registered. `select max(docket_date) from dockets` returns 2026-08-13 against today 2026-08-29. `config/pipeline.yaml:21` sets `max_age_days: 4`. The source channel has 1,760 public entries with the newest at 2026-08-27; the five newest source IDs are all absent from `work/`.
WHY-IT-MATTERS: The system has not ingested for 16 days and nothing reported it. The 4-day window means those streams are out of reach of the normal path even once the task is registered.
PROPOSAL: Register the task, then run a one-off backfill with the age limit raised for the missing window. Pair with F8 so the next outage is visible on day one rather than day sixteen.
COST: Minutes to register; the backfill is bandwidth and CPU. Decide whether the missing fortnight is worth pulling - that is an editorial call, not a technical one.

## F16: Do NOT build the AI narration, the adaptive thumbnail learner, or competitor retention monitoring
SEVERITY: blocker
EVIDENCE: YouTube's July 2026 monetisation rework names three non-monetizable categories, one being AI personas that "discuss more sensitive topics, like finance, legal issues, healthcare"; another is template-driven output with little variation. Separately, measured with yt-dlp: LawAndCrime's 30 most recent videos show a 22.5x view spread with duration not separating them, and YouTube's own A/B tool - with access to every impression and a randomised control - still needs up to two weeks on a single video. The most-replayed heatmap was absent on 8 of 8 sampled competitor videos, so competitor retention is not observable at all.
WHY-IT-MATTERS: These are the three most attractive-sounding parts of the sketched system, and each is either a monetisation risk, statistically impossible at n=2, or built on data that does not exist. Building them would produce a system that makes confidently wrong changes to a channel that currently works.
PROPOSAL: Build the collector, not the learner. Store per video: the exact thumbnail file, title, chosen moments with their scores and reasons, publish time, then join the daily reach CSV and retention curve to it. Write no adaptation logic. Revisit at roughly 30 videos. Keep the value-add human and non-synthetic.
COST: Storage and discipline only. The cost of the alternative is real build time plus a system that acts on noise.

---

### 7. What is Nathan's call, not mine

These are not technical questions and I should not decide them.

**7.1 — Is the long-form worth fixing, or is this a Shorts channel?**
The pipeline's Shorts do 5,349 and 1,153 views at 446 and 577/day. Its
long-forms do 72 and 51. Carry-over from Short to long-form is 1.35% and 4.42%.
Meanwhile the channel's own back catalogue proves long-form CAN work here -
the Soto trial ran 4,549 to 72,180 - but that was a single ongoing case
serialised day by day, which is a different product from one-hearing clips.
Three readings, pick one:
  (a) the long-form format is fine and the execution is broken - fix the
      density/dead-air problem and the titles, re-render, measure again;
  (b) one-hearing long-forms do not work and serialised multi-day trials do -
      change what we make, not how we make it;
  (c) Shorts are the product and long-form exists only for RPM - in which case
      the 8-minute rule is the whole reason it exists and it should be measured
      against actual RPM, not views.
I lean (a) then (b), because we have never once measured retention and are
guessing about where viewers leave.

**7.2 — Did the rejected thumbnail ship, or did the labels move?**
`CARTHIEF_thumbnail.jpg` is byte-identical to `CARTHIEF_thumb_A.jpg` and
`OFFERUP_thumbnail.jpg` to `OFFERUP_thumb_A.jpg` (md5, driver-verified). STATE.md
records Nathan picking C for both and rejecting A for eyes-down. Either the
rejected variant shipped twice, or the recorded labels are wrong. It cannot be
settled from disk - it needs his eye on the six frames.

**7.3 — Which sting is house style?**
CLAUDE.md mandates `sting_v2.mp4` (2.6s). All six long-forms carry the old
1.4s `sting.mp4`, because `build_case_longform.py:44` overrides it and calls
sting.mp4 "the house default" in writing. The contract and the builder
contradict each other and both are live. Whichever loses should be deleted.

**7.4 — Is the missing fortnight worth backfilling?**
Ingest stopped 2026-08-13; the source has five newer streams. `max_age_days: 4`
puts them out of reach of the normal path. Pulling them is bandwidth and a
one-off flag. Editorial call.

**7.5 — One pipeline or two?**
The "automated" pipeline has shipped nothing, and its thumbnail path uses a
builder this repo documents as masking with the wrong model. The hand-driven one
made all five live videos and is untracked. Converging them is 3-5 days. Not
converging them means the unattended goal is unreachable, because the thing that
runs on a schedule is not the thing that makes the videos.

---

### 8. What I did not do, and what is still unknown

- **Nothing in the pipeline was modified.** A gate snapshotting 4,656 files
  enforced it and fired once: an audit agent wrote `NOW.png` into READY-TO-POST.
  Left in place as evidence; it should be deleted.
- **The watermark could not be verified read-only.** The region it occupies is
  static courtroom wall, so a static overlay is indistinguishable from static
  background without extracting a frame. Labelled unknown, not a pass. No log
  covering any shipped artifact survives - logs stop 2026-08-17, artifacts are
  08-23 to 08-27.
- **No retention or CTR data exists**, so every claim about WHY the long-forms
  underperform is a hypothesis. That is what F1 fixes.
- **Two agent claims were retracted after re-measurement** and are recorded as
  retracted rather than deleted: a 44.7% dead-air figure (astats columns
  reversed) and an overstated watermark claim. Three further findings were
  struck as unreachable after a hostile re-read.
- **The driver's own checkers were wrong twice** while verifying a single claim
  about transcript text - both times because the checker was not tested against
  a known answer first. Recorded in DRIVER-VERIFICATION.md, because it is the
  same defect class as four of the blockers above.

---

### 9. Sequenced plan

| # | do | why now | cost |
|---|---|---|---|
| 1 | OAuth + reporting jobs | value decays daily, no backfill | Nathan 5 min |
| 2 | commit the 6 untracked files | one crash loses the whole system | minutes |
| 3 | manifest elements block | makes every other bug self-reporting | ~30 lines |
| 4 | stage-and-promote | refused files stop reaching the publish folder | ~15 lines |
| 5 | fix the 2 lying limb checkers + vacuous gates | never wire a checker that passes its own known-bad | ~40 lines |
| 6 | wire verification (hook, then gates) | every checker currently runs once, ever | hours |
| 7 | fail closed on brand assets; fix the dead path | elements 3 and 4 are off right now | low |
| 8 | non-zero exit on empty run + staleness warn | 16 silent days | ~10 lines |
| 9 | the off-by-one; re-scan | recovers up to 4.6x the candidate pool | 2 lines + rescan |
| 10 | dead-air density gate; re-render | a third of every long-form is silence | moderate |
| 11 | censor at one place | profanity on the publish path | few lines |
| 12 | validate then wire the gaze detector | removes a taste call, already built | one run |
| 13 | title rule + tags | measured, implemented nowhere | low |
| 14 | restart ingest + backfill decision | 14 days behind | minutes + editorial |

Items 1-8 are reliability and cost about two days. 9-14 are correctness and
capability. Nothing above is the "smart system" - that is item 15, and item 15
is a collector that writes no adaptation logic until there are ~30 videos to
learn from.
