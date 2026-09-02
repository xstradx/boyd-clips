# leaf-5.2 — the human-input surface

Read-only audit. Nothing was edited, created, deleted or run except this file
and the read-only commands quoted below.

### Scope note: there are TWO pipelines, and only one of them ships

**Path A — `boyd run`** (`src/boydclips/`): discover -> transcribe -> LLM score
-> LLM package (title/description/thumbnail_quote) -> render long-form + short
-> `thumbnail.build` -> `boyd approve` -> `publish_pair`. Fully automated in
principle. It has not produced a shipped video: `logs/` stops at
`2026-08-20.log`, and `state/pipeline.db` has **`publications` = 0 rows**.

**Path B — the `scripts/` path**: what actually produced CARTHIEF, SANCHEZ,
OFFERUP, MONKEY and the shipped Thompson, and what every entry in `STATE.md`
from 2026-08-23 onward describes. Every number below is measured against Path B,
because Path B is the one making videos.

**`STATE.md` is 30 minutes stale.** It was last written at 04:25 and does not
mention `scripts/run_case.py` + `config/cases.json` (both 04:54–04:55 today),
which are now the closest thing to a one-command routine. Verified:
`ls -la scripts/run_case.py config/cases.json` -> `Aug 29 04:55` / `Aug 29 04:54`
against `STATE.md` at `Aug 29 04:25`.

### The path from "a new Boyd stream went up" to "long-form + short + title + thumbnail"

| # | Step | Class | Evidence |
|---|---|---|---|
| 1 | Discover the stream | **AUTO** | `src/boydclips/discover.py`; `config/pipeline.yaml` `source.channel_url`, `scan_depth: 8`, `max_age_days: 4` |
| 2 | Download section + transcribe | **AUTO** | `state/pipeline.db` `dockets` = 1701 rows; `scripts/backfill_transcripts.py` |
| 3 | Split the docket into hearings | **AUTO** | `scripts/find_called_hearings.py:126` `OUT.write_text(...)` -> `state/called_hearings.json`, cutting on "the court is calling" |
| 4 | Choose WHICH hearing to make | **TASTE** | no code selects; `STATE.md` records his pick verbatim — "that one's fire" — and `state/judged_nathan.json` is his label file |
| 5 | Fix the long-form in/out points | **TASTE** + 4x**PARAM** | `build_case_longform.py:115-120` — `--source`, `--offset`, `--in`, `--out-s`, `--dest` all `required=True`. `STATE.md`: his boundary was "start it from court is calling until she says goodluck to you" |
| 6 | Render the long-form | **AUTO** | same script; snap/dead-air/watermark all internal |
| 7 | Choose the short's segments | **TASTE** | `make_short.py:205` `ap.add_argument("--seg", action="append", required=True, help="START:END in absolute source seconds")`; supplied by dragging blocks in `build_studio.py`, which emits the command at line 1416 |
| 8 | Finish the short | 1x**PARAM** | `make_short_auto.py:76-79` — `--short`, `--transcript`, `--src-start`, `--out` all `required=True` |
| 9 | Choose Judge Boyd's frame | **TASTE** | `config/cases.json` `judge_t`; `STATE.md` records three automated gaze metrics tried and failed |
| 10 | Choose the defendant plate frame | **AUTO** (wrong objective — see F4) | `make_thumbnail_auto.py --auto-plate` -> `pick_plate.py` |
| 11 | Supply the two tile crops | **PARAM** | `cases.json` `judge_crop` / `plate_crop`; `render.py:435 detect_tile_crops` already exists and is unused here |
| 12 | Write the thumbnail copy | **TASTE** | `cases.json` `white` / `yellow` |
| 13 | Register the case | **EDIT** | a new 13-field object in `config/cases.json`, plus duplicate entries in `layout_L1_system.py` / `L2` / `L3` |
| 14 | Write the title | **manual, no code path on Path B** | `cases.json` has no title field; `READY-TO-POST/COPY-PASTE.txt` is a hand-written title + description |
| 15 | Write the description | **manual** + a blocked records pull | `STATE.md`: "Charge and current status for Joseph Grant (2024CR011920) are UNVERIFIED" |
| 16 | Upload | **manual (browser)** | `autonomy.mode: manual`, `publish.youtube.api_audited: false`, `publications` = 0 rows |

### THE HEADLINE NUMBER

> **Producing one finished Boyd video today requires 18 human decisions:
> 6 taste calls, 7 parameters, 2 file edits, and 3 manual publish/copy steps.**

Working:

* **6 TASTE** — (1) which hearing; (2) the long-form start/end boundary;
  (3) the short's `--seg` list; (4) `judge_t`, Boyd's frame; (5) the
  `white`/`yellow` thumbnail copy; (6) the title.
* **7 PARAM** — `--source`, `--offset`, `--in`, `--out-s`, `--src-start`,
  `--transcript`, and the `judge_crop`+`plate_crop` pair. All seven are values
  a machine could compute; all seven are typed by hand today.
* **2 EDIT** — a new object in `config/cases.json`, and the same case re-entered
  in the `JOBS`/`HEARINGS` dicts of `layout_L1_system.py`, `layout_L2_eyeline.py`
  and `layout_L3_tight.py`.
* **3 MANUAL** — write the description (blocked on a Bexar County records pull),
  upload the long-form by hand, upload the short + attach the thumbnail + tick
  Not Made for Kids.

> **Of those 18, 10 are reducible to AUTO with a named mechanism, and 5 are
> genuinely taste.** The remaining 3 are the manual publish/description block,
> which is blocked by policy and by an unfetched public record — not by
> automation difficulty.

Reducible (M=10): the 7 PARAMs, both EDITs, and the long-form boundary.
Genuinely taste (K=5): which hearing, the `--seg` list, `judge_t`, the
thumbnail copy, the title.

**Caveat on K, and it is the most useful single fact in this leaf.** `judge_t`
is counted as taste because that is what the shipping path does today. But a
detector implementing Nathan's exact rule already exists in this repo and is not
wired in — `layout_L3_tight.py:169` `nv`, gated at line 493 and asserted at line
1498 as "Judge Boyd eyes LEVEL not down (nv <= 0.50, |roll| <= 4)". It has never
been scored against his nine labelled picks. **If it clears 9/9, K drops from 5
to 4 for the cost of one validation run** — no new model, no new dependency. See
F3.

### The shortest honest path to unattended — the three that matter

Ranked by (occurs every video) x (removable with a named mechanism).

1. **The short's `--seg` list** (F6) — the largest wall-clock step, one
   hand-dragged timeline per video, and the only review page on the critical
   path.
2. **`judge_t`, Boyd's frame** (F3) — the highest ratio of leverage to effort in
   the whole audit: the detector, the ONNX model and the nine labelled frames
   are all already on disk. It is a validation run, not a build.
3. **The 13-field case registration** (F5) — 7 of the 13 fields are already
   computable from the filename, `state/called_hearings.json` and
   `render.detect_tile_crops`, and the case is currently entered in four
   separate places that already disagree with each other.

`--src-start` (F2) is the cheapest single fix in the file — the value is already
written to a `.map.json` sidecar no script reads — but it is one typed number,
so it ranks below the three above on leverage.

---

## F1: Nothing on the shipping path generates a title, and the one measured title rule is written down but implemented nowhere

SEVERITY: blocker
EVIDENCE: `config/cases.json` has 13 fields per case (`video, transcript, offset, case_from, case_to, judge_t, judge_crop, plate_t, plate_crop, white, yellow, short, short_src_start`) and **no title, description or tags field**. `scripts/run_case.py` — the 2026-08-29 "routine" whose docstring quotes Nathan's "from start to finish can handle everything from a routine" — runs exactly two things: `make_thumbnail_auto.py` and `make_short_auto.py`. Grep for the measured rule: `grep -rn "0.0068|startswith(\"Judge Boyd\")" --include=*.py --include=*.md .` returns hits in only two places — `research/THUMBNAIL-MEASURED-2026-08-23.md:392` ("Title starts with 'Judge Boyd': top 14/15 (93%), bot 4/10 (40%), Fisher p=0.0068") and `STATE.md:452`. **Zero hits in `prompts/`, `src/` or `scripts/`.** `prompts/package_post.md:51` says only "No proper nouns except 'Judge Boyd'" — permission to use it, not a requirement to open with it, and only two of its four worked examples in the "Write this" column actually open with the string (the other two start with "He" and "His"). The only title ever shipped, `READY-TO-POST/COPY-PASTE.txt`, is hand-written and its own header says why: "The title and description in manifest.json were written by the packaging step before the two sittings were merged, so they describe only the first 4.5 minutes".
WHY-IT-MATTERS: One full taste call per video, and the highest-leverage copy decision in the product is currently made from memory with no rule enforced. Path A's LLM packaging exists but its one real-world output was rejected and rewritten by hand.
PROPOSAL: (a) Add `title`/`description` to `config/cases.json` so the routine at least carries them; (b) port the p=0.0068 finding into `prompts/package_post.md` as a hard constraint — "the title MUST begin with the literal string `Judge Boyd`" — and add a mechanical post-check in `analyze.package()` beside the existing `_trim_title` length check at `analyze.py:372-383`, rejecting and re-prompting on failure. Proof it works: run `package()` over the 25 `research/reference/courtroomtime/thumbs/` cases and assert 25/25 generated titles satisfy `title.startswith("Judge Boyd")` and land in the 50-65 char band — the same two properties the winners were measured on.
COST: Low effort (one prompt edit plus a ~10-line validator). Risk: the rule was measured on one competitor channel's 25 videos, so it should be enforced as a default with an override, not as a law.

## F2: `--src-start` is required with no default on three scripts, and the value already sits in a sidecar nobody reads

SEVERITY: high
EVIDENCE: `scripts/make_short_auto.py:78` — `ap.add_argument("--src-start", type=float, required=True)`; identically at `tighten_short.py:52` and `caption_short.py:288`. The docstring at `make_short_auto.py:9` shows it hand-typed: `--src-start 3931.8`. But `scripts/make_short.py:333` already writes a sidecar for exactly this: `side = out.with_suffix(".map.json")` carrying `"video"`, `"section_start_s"` and per-piece `"src_start"` — its own comment says "Sidecar map so the short can be edited on its OWN timeline later." Running `find "C:/Users/natha/OneDrive/Desktop/Boyd Clips" -name "*.map.json"` returns 14 files, all for `SHORT_monkey-*` and `VERTICAL_*` — **none for CARTHIEF, SANCHEZ or OFFERUP**, whose shorts were therefore cut outside `make_short.py` and whose `src_start` had to be found by hand. It was then re-typed into `config/cases.json` as `"short_src_start": 3931.8`.
WHY-IT-MATTERS: One parameter per video that a human currently recovers by scrubbing footage, and a value that silently produces wrong captions if it is off — every caption timing in `caption_short.py` is computed as `word.t - src_start`.
PROPOSAL: Make `--src-start` optional in all three scripts and default to reading `<short>.map.json` beside the input, erroring with the exact missing path if neither is present. Then make every short-producing route (`make_short.py`, `build_studio.py`'s render, `batch_vertical.py`) write that sidecar unconditionally. Proof: `python scripts/make_short_auto.py --short X_SHORT.mp4 --transcript ... --out Y.mp4` with no `--src-start` reproduces `CARTHIEF_SHORT_FINAL.mp4` with identical timing — the same 22 cuts, the same 34.800s A/V, the same 0 gaps over 0.7s that `STATE.md` records as the reference output.
COST: Low effort, ~20 lines. Risk near zero — the fallback is the current explicit flag.

## F3: Judge Boyd's frame is counted as an irreplaceable taste call, but a detector implementing his exact rule ALREADY EXISTS in this repo — on a script that is not the shipping builder

SEVERITY: high
EVIDENCE: `config/cases.json` carries a hand-set `judge_t` per case (CARTHIEF 3944, SANCHEZ 4021, OFFERUP 10884), and `scripts/make_thumbnail_auto.py`'s docstring says the judge frame "stays a contact-sheet choice and is passed in", because "three automated gaze metrics all failed". `STATE.md` records those three and their numbers — Haar eye count (picked 6/3/7 vs rejected 4/3/4, tied on the decisive pair), eye-region dark fraction (27.0% vs 27.2%, separates nothing), eye-region std-dev — and names the signal that was missing: "Gaze PITCH is what matters and Haar cascades do not measure it." **That signal is implemented.** `scripts/layout_L3_tight.py:169-180` defines `nv` as a property on a YuNet detection: `"""pitch proxy, de-rolled. HIGHER = looking DOWN."""` — it de-rolls the face by `-radians(self.roll)`, rotates the nose point about the eye midpoint, and normalises by interocular distance. It is thresholded and enforced: `layout_L3_tight.py:65` `gate_nv=0.50, # 0.412-0.468 = head up; 0.623-0.635 = reading`; line 493 `if f["nv"] > HOUSE["gate_nv"]: continue`; line 500 `out.sort(key=lambda d: (d["nv"], sign * d["nd"]))`; line 880 `raise SystemExit(f"REFUSE {name}: zero frames pass nd/nv/roll/size gate")`; and line 1498 states Nathan's rule verbatim as a shipped check: `chk("Judge Boyd eyes LEVEL not down (nv <= 0.50, |roll| <= 4)", ...)`. `models/yunet.onnx` is present on disk and referenced at `layout_L2_eyeline.py:60`. So the hero frame is already chosen automatically — by `layout_L3_tight.py`, which is NOT what `run_case.py` calls. The shipping path (`run_case.py` -> `make_thumbnail_auto.py` -> `thumb_Q3_detail.py`) takes `judge_t` from the JSON by hand.
WHY-IT-MATTERS: This is the difference between "one irreplaceable taste call per video" and "one wire that was never connected". It is also the gate on the thumbnail, the highest-leverage asset in the package. It has never been validated against his labelled picks, so it cannot simply be switched on either.
PROPOSAL: Validate first, then wire. The measurable signal is `nv` as defined at `layout_L3_tight.py:169`. What would prove it: compute `nv` over the six candidate frames whose verdicts he gave verbatim on 2026-08-28 (picked: CARTHIEF C, SANCHEZ A, SANCHEZ B, OFFERUP C; rejected: CARTHIEF A, CARTHIEF B, SANCHEZ C, OFFERUP A, OFFERUP B) and require **9/9 correct separation with a margin**, including the SANCHEZ A-vs-C pair the dark-fraction metric tied on and where his stated reason was a raised hand mid-gesture rather than the eyes. If it passes, make `judge_t` optional in `cases.json` and have `make_thumbnail_auto.py` sweep the case range for the lowest-`nv` frame the same way `--auto-plate` already sweeps for plate room. 9/9 is the same bar the audio-visual speaker attribution had to clear (9/9 against 4/9) before it was trusted.
COST: Low effort to validate (the detector, the model file and the nine labelled frames all exist); low to wire. Risk: `nv` is a head-pitch proxy, not eye gaze, so it can pass a frame where she looks down with her head level — which is exactly what the 9/9 test catches. It also does not model the raised-hand-mid-gesture half of his rule at all. **Do not ship it as automatic until it passes 9/9.**

## F4: The defendant plate frame is auto-picked for an objective that is not Nathan's stated rule, and the tool that measures his rule is called by nothing

SEVERITY: medium
EVIDENCE: `scripts/run_case.py` calls `make_thumbnail_auto.py ... --auto-plate`, which calls `pick_plate.py` and takes its top-1 by regex: `m = re.search(r"clearest right side: src ([\d.]+)", p.stdout)`. `pick_plate.py`'s docstring states its objective: "Find a plate frame whose right side is free for the judge cut-out ... how much of the RIGHT PORTION (where the cut-out lands) is occupied by somebody other than the defendant - lower is better". It also says of itself: "It prints a ranked table rather than picking silently, because which frame reads best is still Nathan's eye - this only guarantees the candidates have room." `make_thumbnail_auto.py` picks silently anyway. Meanwhile `scripts/pick_reaction.py` — whose docstring opens with Nathan's standing rule, "i need you to always make sure you get a good frame of the defandant like with a good reaction" — is called by nothing: `grep -rn "pick_reaction" --include=*.py .` returns only its own file. Its own docstring concedes its limit: "MOTION is a heuristic ... it cannot tell shocked from mid-blink." There is now a **third** competing objective for the same frame: `layout_L3_tight.py:895-896` picks the plate by `plate_pool.sort(key=lambda p: p[1]["nv"])` under the comment "a good reaction = eyes up, head not buried: lowest nv first". So three scripts choose the defendant frame by three different criteria — composition room, motion-vs-baseline, and head pitch — and the one on the shipping path is the only one that is not about his expression.
WHY-IT-MATTERS: Zero human decisions saved, but the automation quietly optimises composition room over the defendant's expression — a substitution of the objective that is invisible in the output. `STATE.md` already records the cost of getting this wrong: on CARTHIEF "he is flat-neutral in the shipped thumbnail."
PROPOSAL: Make the plate choice a two-term score rather than one: filter candidates by `pick_plate`'s right-side-occupancy gate (composition feasibility), then rank the survivors by `pick_reaction`'s sharpness-plus-motion score (expression), and emit the top 6 as a contact sheet rather than silently taking top-1. Proof it works: on OFFERUP — the case that motivated `pick_plate` — show that at least 3 of the 5 frames it found with "a completely clear right side" survive the reaction ranking, i.e. the two objectives are not in conflict. If fewer than 3 survive, the two-term score is the wrong shape and the sheet must show both rankings side by side.
COST: Low effort (composing two scripts that already exist). Risk: it reintroduces one human choice per video unless the combined score is validated — which is the honest trade, since neither script claims to be able to pick.

## F5: A brand-new case needs 13 hand-set values in `config/cases.json` plus duplicate entries in three layout scripts, and the chosen thumbnail builder still carries a `carthief`-only preset

SEVERITY: high
EVIDENCE: `config/cases.json` requires per case: `video, transcript, offset, case_from, case_to, judge_t, judge_crop, plate_t, plate_crop, white, yellow, short, short_src_start` — 13 values. The same case facts are re-entered in three more places: `layout_L1_system.py:50` `JOBS = {...}`, `layout_L2_eyeline.py:69` `HEARINGS = {...}`, `layout_L3_tight.py:109` `HEARINGS = {...}` — each with `src, off, case, tiles, white, yellow`, i.e. four independent copies of the same facts, and L1 and L3 already disagree with L2 on the SANCHEZ copy ("You're why your son" vs "You are why your son"). Separately, `scripts/thumb_Q3_detail.py` — the build Nathan chose ("q3 thumbnail is fire") — hardcodes one case only: `PRESETS = {"carthief": dict(video=..., clip_start=3554.0, judge_t=3944.0, judge_crop="612:338:18:190", plate_t=4578.0, plate_crop="620:338:644:190", white="Playing Grand", yellow="Theft Auto?")}` with `ap.add_argument("--preset", default="carthief", choices=sorted(PRESETS))` and the preset back-filling any unset field at lines 893-896. Of the 13 fields at least 7 are mechanically derivable: `video` and `offset` are both encoded in the filename (`EwwnbiAQtFk_h_3574_3554-4697.mp4` -> offset 3554), `transcript` is `work/<id>/<id>.transcript.json`, `case_from`/`case_to` come from `state/called_hearings.json`, and `judge_crop`/`plate_crop` from `render.py:435 detect_tile_crops`, which `make_short.py:238` already calls and which refuses rather than guessing ("tiles not measurable; aborting rather than guessing").
WHY-IT-MATTERS: 2 file edits per video, plus 7 of the 13 fields being hand-typed values a machine already has. It is also exactly the concern `STATE.md` flags about the chosen builder: "If it needs per-case tuning it is not yet the daily pipeline."
PROPOSAL: Add `scripts/register_case.py <video_id> <case_index>` emitting the `cases.json` object with all 7 derivable fields filled from the filename, `state/called_hearings.json` and `detect_tile_crops`, leaving only the 6 taste fields blank. Then delete the `JOBS`/`HEARINGS` dicts from `layout_L1/L2/L3` and have all three read `config/cases.json`, so a case is registered once. Proof: regenerate the CARTHIEF, SANCHEZ and OFFERUP entries from scratch and assert all 7 derived fields match the hand-set values now in the file exactly — including `judge_crop: "468:348:726:6"` for SANCHEZ, where the judge is on the RIGHT while CARTHIEF has her on the LEFT, which is the case any side-assuming code gets wrong.
COST: Medium effort. Risk: `detect_tile_crops` may disagree with a hand-measured rect; the 3-case replay is precisely the test that catches that before it ships.

## F6: The review pages are optional tools with one exception — `build_studio.py` is the only way the short's segment list gets made, and it is a hand-dragged timeline

SEVERITY: high
EVIDENCE: `build_rating_page.py` has no argparse at all (it reads `state/wentthere.json` and writes an HTML file to the Desktop) — it fits Nathan's ranking model and produces no video. `build_editor.py`, `build_browse_editor.py` and `build_studio.py` each take `--file --video --base` as `required=True` and all three write an HTML page. Only `build_studio.py` is on the shipping path, and only for one thing: line 1416 emits `"python scripts/make_short.py --video " + VIDEO + " " + f.join(" ") + " --out \"" + OUT + "\""` — the `--seg` list. `make_short.py:205-207` makes that list mandatory: `ap.add_argument("--seg", action="append", required=True, help="START:END in absolute source seconds; repeatable, plays in the order given")`, and the comment above it at line 209 makes the dependence deliberate: "The editor is authoritative about where a cut starts and ends; this renders what it was handed." The page was really used — `READY-TO-REVIEW/STUDIO_2XkPnvstmRQ.html` exists on disk. `state/moments.json`, `state/moments_2XkPnvstmRQ.json` and `state/suggest_2XkPnvstmRQ.json` also exist, so candidate moments ARE indexed automatically; nothing turns them into a `--seg` list without a person.
WHY-IT-MATTERS: This is the single largest remaining human step by wall-clock — sitting in a timeline editor once per video — and the one whose removal `STATE.md` never claims. Every other review page can be skipped; this one cannot.
PROPOSAL: Close the loop that already exists. `state/moments_<id>.json` holds ranked candidate moments and `state/suggest_<id>.json` holds proposed edits. Add a `--from-moments <json> --top N` mode to `make_short.py` that composes the `--seg` list from the top-N indexed moments, snapped to word boundaries in the transcript the way `refine.py` already snaps the long-form. Proof it works, and this is the measurable part: build a short for CARTHIEF from the index with no human, run it through `make_short_auto.py`, and require it to clear the same five gates the hand-cut one does (pix_fmt yuv420p, 1080x1920, A/V within tolerance, zero remaining word-gaps over 0.70s, clean decode) **and** land within +/-15% of the hand-cut 34.8s. Then show both to Nathan blind. If he cannot reliably pick the hand-cut one, the studio comes off the critical path; if he can, it stays and the index becomes a pre-filled timeline he trims instead of a blank one.
COST: Medium-high effort. Risk: the highest of anything here — a machine-chosen moment is a taste call, and `STATE.md` already shows a uniform ratio failing (OFFERUP lost 25%, SANCHEZ only 7%). Ship it as a pre-filled timeline inside the studio, not as a replacement for it.

## F7: The upload mechanism is fully implemented, but two config flags and an unpassed API audit mean every publish is done by hand in a browser

SEVERITY: medium
EVIDENCE: `src/boydclips/publish.py` implements a complete resumable YouTube upload — `MediaFileUpload(str(video), chunksize=8 * 1024 * 1024, resumable=True)`, `service.videos().insert(part="snippet,status", body=body, media_body=media)`, plus a `thumbnails().set()` call wrapped in try/except so a rejected thumbnail cannot lose an upload that already succeeded. It is gated twice. `config/pipeline.yaml:31` `mode: manual` makes `publish_pair` return early with "autonomy.mode=manual — files rendered to out/review/, nothing published". `config/pipeline.yaml:572` `api_audited: false` triggers a hard refusal whose in-code comment gives the real reason: "An unaudited API project does not upload 'as private' — it uploads to a video that is LOCKED private, cannot be appealed, and cannot be made public by hand". Confirmed nothing has ever gone through it: `state/pipeline.db` `publications` = 0 rows against `clips` = 50. TikTok and Instagram raise `NotImplementedError` with each specific blocker named (Content Posting API app audit; the Graph API needing a public HTTPS URL rather than a file upload). The one published video went up by hand — `READY-TO-POST/COPY-PASTE.txt` is the paste sheet, and it instructs "Post the long-form FIRST, then paste its URL into the short's description", which is the exact funnel ordering `publish_pair` would have enforced in code.
WHY-IT-MATTERS: 3 manual steps per video (long-form upload, short upload, thumbnail attach plus the Not-Made-for-Kids declaration), and the funnel ordering is currently enforced by a text file rather than by code.
PROPOSAL: Do NOT flip `api_audited` — the refusal comment is correct and the failure mode is a case permanently spent on a locked-private video. The mechanism that removes these three steps without the audit is browser automation against the YouTube Studio upload page (`claude-in-chrome` and `playwright` MCP servers are both connected on this machine), driven from the same `publish_pair` ordering so the long-form URL still lands in the short's description before the short posts, and still calling `store.record_publication` so the duplicate guard and the takedown row that SAFETY_RULES R7 depends on keep working. Proof: upload one video to **private**, confirm `publications` gains a row whose `url` resolves, confirm the custom thumbnail attached, and confirm `selfDeclaredMadeForKids` reads false on the live video. Uploading remains a hard stop needing Nathan's explicit confirmation regardless — this reduces three operations to one confirmation, it does not remove the confirmation.
COST: Medium effort. Risk: the confirmation gate must stay a real gate; browser automation that publishes without an in-turn confirmation would be worse than the status quo.

## F8: `run_case.py` covers 2 of the 4 deliverables — the long-form and both pieces of copy are outside the routine entirely

SEVERITY: high
EVIDENCE: `scripts/run_case.py`, the file whose docstring quotes "from start to finish can handle everything from a routine", dispatches exactly two subprocesses: `make_thumbnail_auto.py` (behind `--skip-thumb`) and `make_short_auto.py` (behind `--skip-short`). `build_case_longform.py` is never invoked from it, and `config/cases.json` carries no long-form render bounds — its `case_from`/`case_to` are the hearing bounds used for the frame sweep, not the render points, which `STATE.md` records as separately located per case ("Court is calling" at src 5915.92; "Good luck to you." ending 6737.6; out-point set at 6739.30 so her line and its answer both land). There is likewise no title or description field. The routine's own output directory confirms the partial coverage: `ls -la "…/READY-TO-POST/Q3SET"` returns `OFFERUP.jpg`, `SANCHEZ.jpg` and `_probe.jpg` — **no CARTHIEF.jpg** — so even the two deliverables it does cover have not been completed for all three configured cases.
WHY-IT-MATTERS: The "one routine" framing overstates coverage by half. Someone reading `run_case.py --all` reasonably concludes a case is finished, while the long-form — the monetising asset, and the reason for the 8-minute floor — plus both pieces of copy are still entirely by hand. That is 1 taste call, 4 params and 2 manual steps sitting outside the thing named as the routine.
PROPOSAL: Extend `config/cases.json` with `lf_in`, `lf_out`, `title` and `description`, and add a third dispatch in `run_case.py` to `build_case_longform.py`, so the registry describes a whole video rather than half of one. Derive `lf_in` from `state/called_hearings.json` (the "court is calling" hit is already located there) and `lf_out` from an end-of-hearing phrase bank fitted against the 13 `HEARING_*.mp4` files already cut — his own boundary was a phrase ("until she says goodluck to you"), so the mechanism is a phrase match over the word-level transcript, not a heuristic. Proof: the bank must recover the MONKEY out-point in the range src 6737.04-6739.30 **and** must not run past src 6745.3, where `STATE.md` records the next case being called without the "court is calling" phrase — that is the exact merge failure `find_called_hearings.py` produced, and it is the test the bank has to pass before it is trusted.
COST: Medium effort. Risk: a phrase bank fitted on 13 hearings will miss on unseen wording; it should propose the out-point and require a one-key confirm, not cut silently.
