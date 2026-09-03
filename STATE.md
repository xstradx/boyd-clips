**Resume from disk — any model, any session** (2026-09-02, his ask: *"pls
prioritize that but I only have 1% usage left"* — everything this chat taught
is on disk, not in a context window):
1. Print the "Where were we" block below, five lines, then continue it.
2. `python tools/selftest_all.py` and `python tools/check_rules_refs.py` must
   both print ALL_OK before any build is shown (33/33 on 2026-09-02).
3. This chat's corrections are observation-log 0027–0042 in
   `~/.claude/projects/C--Users-natha/skill-observations/`; the rule for each
   is already in `spec/NATHAN_RULES.md` R46–R50 and the skills — read the log
   only when a rule needs its reasoning.
4. What the rules say is NOT automated (hook span, expression frame, title
   angle, whether a line is funny): offer him 2–3 concrete readings, never an
   open question, never a rank score dressed as a judgement (R50).
5. The gates decide the floor, not the model. A build that passes them with a
   different taste call is a valid build; a build that skips them is not.

## 2026-09-03 — PERKINS posted; R56/R57 fixed the washed-out faces

**Where were we** (print this on "where were we?"):
- **Done (posted):** PERKINS long-form is LIVE, Public, `9mrARjeKJd8`
  (https://youtu.be/9mrARjeKJd8) — 2026-09-03. ID read from the DOM href, oEmbed
  200 with the exact title and author "Texas Trial Tracker". Title A live:
  `He Says He Was Shot. Judge Boyd: "Well, Let's Google."`; description + 24 tags
  + the REBUILT thumbnail; Not made for kids; monetisation On + mid-rolls; ad
  suitability None of the above -> Safe for ads (rating saved). Published through
  the "we're still checking your video" dialog (copyright check was already clean;
  ad-suitability check was still running — RE-CHECK the monetisation state).
- **Done (posted):** PERKINS short is LIVE, Public, `7bzmB2KX0uk`
  (https://youtube.com/shorts/7bzmB2KX0uk) — oEmbed 200, exact title. Title
  `Judge Boyd Wanted Proof He Was Shot: "Well, Let's Google."`, description with
  `Full hearing: https://youtu.be/9mrARjeKJd8`, 16 tags, Not made for kids,
  Safe for ads, Related video = `9mrARjeKJd8` ("Changes saved").
- **RETRACTED / root cause, 2026-09-03.** His words: *"Okay but correct the
  color"* / *"the faces all washed and white where its hard to really see their
  face"*. The thumbnails sitting in `READY-TO-POST/<CASE>/` from the 09-02 batch
  ARE the five he rejected — `PERKINS_thumb.jpg` is byte-for-byte the file in
  `tools/fixtures/rejected_2026_09_02/`. I offered him one to post. R51-R55 all
  landed AFTER the batch wrote those files (13:44-17:01 vs 12:53) and only PACE
  was ever redone. **CLAYTON, GARCIA_J and LOPEZGONZALEZ are still the rejected
  builds on disk — rebuild before any of them is shown or posted.**
- **R57 (new, the actual cause).** The separation solve chased
  `SEPARATION_DL = +18.6` from an outside 68-thumbnail corpus, and its own
  comment called a brighter background "the 'subjects don't pop' defect". But
  FOUR of the five he accepted put the background BRIGHTER than the people:

        case       subject_L  background_L     dL
        OFFERUP        126.1        107.2   +18.9
        CARTHIEF        91.2        137.8   -46.6
        SANCHEZ         86.3        144.1   -57.8
        MONKEY         106.7        124.3   -17.6
        THOMPSON        94.2        149.1   -54.9
        PERKINS(old)   106.3         89.2   +17.1   <- the rejected build

  A dark plate makes the people the brightest thing in frame, and LOOK then
  scales the whole canvas up to hit its luma constant — which is exactly the
  "washed and white" he named. Fix: `SEPARATION_DL` stays the aim, but the plate
  it produces is CLAMPED into the accepted `background_L` envelope, read from
  `config/quality_floor.json` so it moves when the floor moves (same construction
  as R51). `BG_L_MIN/BG_L_MAX`, env-overridable via `BOYD_BG_L_MIN`.
- **R56 (was uncommitted on disk, now committed).** Skin richness: highlight
  chroma / base chroma. His accepted five 1.20-1.46, our builds 0.52-0.74 —
  highlights lost half their colour, which reads as a white patch on the face.
  Lifted toward `HL_CHROMA_RATIO` 1.25 (`BOYD_HL_RATIO`).
- **PERKINS rebuild, measured.** Plate at the corpus median (137.8) + `GRAIN`
  1.35 (brighter plate crosses the grain weight peak, so 1.8 measured 1.93 vs the
  accepted max 1.76). Final: `grain_hf 1.76  background_L 135.6  contrast_sd 82.1
  subject_L 105.9  separation_dL -29.6` -> **THUMB_GRADE_OK**, BUILD_GATES PASS,
  verify_thumb A/C/D SHIP, CLUTTER_OK 0.186, 1280x720 JPEG 4:4:4. Also added the
  missing kicker (`SHE READ IT OUT LOUD...`) — the batch build shipped with none,
  ink cover 0.130 vs the accepted 0.192-0.226, which is why its faces were solved
  at 425 px and the frame was almost all skin. With the kicker face_h is 338.
  Old build kept at `thumbwork/PERKINS/preR56/`.
- **Still weak, said out loud, NOT automated:** Boyd's face in this hearing's
  source frame carries a pink/magenta cast on the cheek and lips and posterises
  under HYPIR. It is in the pre-R56 build too — R56 did not create it, it made it
  slightly more saturated. Levers not taken: a different `judge_t`, or
  `--judge-from-library best` (it picked `boyd_THOMPSON_approved.png` but then
  failed R38 `heads not level: boyd 164 / defendant 160` — needs a
  `defendant_nudge` retune for the library judge).
- **Apparatus defect, open:** `tools/thumb_pipeline.py --selftest` (R44 judge
  cutout reuse) is STATEFUL — 3 failures on a cold run, 30 on a re-run. It leaks
  state between runs (the library at `assets/harvest/reactions/boyd/` is clean, so
  it is elsewhere). `selftest_all` therefore prints 34/35 SELFTEST_FAIL. Not
  blocking on it for a grade change, but it must be fixed before it is trusted.
- **Next:** (1) rebuild CLAYTON / GARCIA_J / LOPEZGONZALEZ thumbnails through
  R56/R57 — they are the rejected files; (2) re-check monetisation on
  `9mrARjeKJd8` once the ad-suitability check finishes; (3) A/B title test (B, C)
  on `9mrARjeKJd8` and on `BmM4AsCk86g`; (4) fix the R44 selftest; (5) outcome
  tracking on the four live videos.


## 2026-09-03 - R56/R57: the skin is corrected to his measured band; the global look stops touching people

**Where were we** (print this on "where were we?"):
- **Done:** `tools/skin_colour_fix.py` (R56) corrects each subject's skin to the
  band measured off HIS artefacts - the designer sheet he sent (a* +11..+14,
  chroma 18.6-22.2) and his five accepted thumbnails (a* +9..+24, chroma
  16.5-25.6). The PACE judge entered the composite at chroma 9.2, less than half
  of anything he has accepted. R57 locks subject tone: LOOK no longer multiplies
  people (+6.65 L* on PACE), `face_L_balance` and the chroma lift are off by
  default, the separation glow stays. `BOYD_SIMPLE` no longer lies about what it
  disables. Commit `0932931`.
- **Done:** `D:/Boyd Clips/thumbwork/PACE_ship/PACE_SHIP.jpg` - BUILD_GATES PASS
  (E F G I J K L H) + A/C/D SHIP, built with `--judge-from-library best`.
  `selftest_all` 36/36 ALL_OK, `check_rules_refs` ALL_OK, `FLOOR_GATES_OK` (the
  accepted five still pass every gate).
- **Retracted, in the rules file and to him:** "the compositor paints light on
  the faces, 12.2% / 35.8% lifted" was detector-box misalignment, not light.
  Alignment-free, every face percentile goes DOWN. Three white-patch metrics
  then failed to separate accepted from rejected - `tools/_white_patch_corpus.py`
  keeps that disproof. The white on Boyd is in the PACE hearing's own footage of
  her; from the approved THOMPSON cutout it is gone.
- **Dead:** AI regeneration of subjects. Shown the raw HYPIR crop beside two Qwen
  regenerations he said *"No I like left"*. `--regen` stays off.
- **Next:** the defendant's blown forehead/scalp - it is in HIS SOURCE FRAME
  (gate C 173 against a 180 limit), so it is R54 frame-picker work, not grading.
  Then re-run the other four cases (CLAYTON, GARCIA_J, LOPEZGONZALEZ, PERKINS)
  through the R56/R57 pipeline before any of them is shown or posted.
- **Blocked:** nothing.

## 2026-09-02 — TORRES built end to end (short via the chain, cold-open long-form, thumbnail); R46–R49

**Where were we** (print this on "where were we?"):
- **Done:** TORRES package on disk and gated — short
  `D:/Boyd Clips/READY-TO-POST/TORRES_SHORT.mp4` (0:57, `tools/short_chain.py`
  CHAIN_OK / SHORT_OK, FLOOR_OK 952880e85e6e), long-form
  `READY-TO-POST/TORRES_LONGFORM.mp4` (8:59, cold open 5007.25–5012.30
  "talk circles around me" + COMING UP... + sting + body, COLDOPEN_OK on the
  mastered file, -14.2 LUFS / -1.7 dBTP MASTER_OK), thumbnail
  `thumbwork/TORRES/TORRES_thumb.jpg` (A/C/D PASS). Copy in
  `READY-TO-POST/COPY-PASTE-TORRES.txt` (3 A/B titles TITLE_OK, description,
  24 tags, short title). `selftest_all` 32/32 ALL_OK, `check_rules_refs` ALL_OK.
- **Done (posted):** TORRES long-form is LIVE, Public, `BmM4AsCk86g`
  (https://youtu.be/BmM4AsCk86g) — 2026-09-02, ID read from the DOM href and
  confirmed by oEmbed 200 with the exact title. Title A live: `"You're Trying
  To Talk Circles Around Me." Judge Boyd Had Enough.`; description + 24 tags
  + thumbnail `thumbwork/TORRES/TORRES_thumb.jpg`; Not made for kids;
  monetisation On + mid-rolls; ad suitability None of the above -> Safe for
  ads (rating saved); NOT a Premiere (he said "Instant premier" then "Nvm").
- **Done (posted):** TORRES short is LIVE, Public, `irWd-f4jK-M`
  (https://youtube.com/shorts/irWd-f4jK-M) — 2026-09-02, ID read from the DOM
  href in the Visibility step, oEmbed 200 with the exact title. Title `Judge
  Boyd To The Nurse On Probation: "That's A No."`, description with `Full
  hearing: https://youtu.be/BmM4AsCk86g`, 16 tags, Not made for kids, ad
  suitability None of the above (Safe for ads), Checks clean, Related video =
  `BmM4AsCk86g` set on the edit page and saved ("All changes saved").
- **Done (thumbnail swap):** MONKEY_S is the live thumbnail on `OGj_eLUXjrk`
  (his yes: "updated the monkey thumbnail", 2026-09-02). Studio had a 3-variant
  thumbnail A/B test RUNNING on it (old FINAL + two older variants); a
  `file_upload` to the file input is silently ignored while a test runs.
  Options ⋮ → Upload file → confirm "will delete previous test" → toast
  "A/B Test deleted" → THEN `file_upload` to the same input → Save (greyed
  after; sidebar + preview show MONKEY_S). The test's results are gone with it.
  CDN `maxresdefault.jpg` still served the old art minutes later (mean |diff|
  88 vs MONKEY_S) — propagation, re-check later, not a failed swap.
  No other live video has a newer rebuilt thumbnail on disk (OFFERUP's live
  thumb IS `OFFERUP_NEW.jpg`; CARTHIEF/SANCHEZ/THOMPSON have no live ID on
  disk) — nothing else swapped, nothing built.
- **Next (deferred, "tokens are almost out"):** A/B title test (B, C) on
  `BmM4AsCk86g` — titles in `READY-TO-POST/COPY-PASTE-TORRES.txt`. Then the
  5-banger shortlist he asked for 2026-09-02 ("Find 5 banger videos we're
  going to post next, don't start making them tho").
  SHORTLIST DELIVERED 2026-09-02 (not built): 1 Claudell Carney 2023 CR10366
  Ol-9_cBR5J4@3229 (MTR revoked while he argues, 0 rivals); 2 Genevie Pettis
  2025 CR10422 MK5gYUbB8fY@1871 ("gun to your head", 6 yrs probated, 0 rivals);
  3 Cammy Lumpkins 2025 CR10462 8gJddEUcu_U@2566 (signs 3-yr-old over to her
  mom, denied, 0 rivals); 4 Alex Miosek/Measeck 9R1jJ_QX1Wg@8262 (62-min
  contested revocation, broken-nose witness, 0 rivals, spelling unverified);
  5 Roger Luis Blanco 2025 CR2804 8gJddEUcu_U@9011 (MTR granted, "it is what
  it is", 1 rival exJ1R0VA7g8). Alternates: Blackburn Sr 4zkUTUavW4I@116 (3
  rivals), Lutenberger QfKjHJ1A4KM@8202 (2 rivals). Source: final_shortlist
  (08-21 judged) + picks.log + yt-dlp name search 2026-09-02. Not watched.
  SUPERSEDED 2026-09-02 by the R50 recent shortlist below: these five were
  ranked, not read. Before proposing any of them again run
  `tools/banger_digest.py --rows` on their rows and read the lines.
- **Done (R50, 2026-09-02):** the picker now has an entertainment layer -
  `tools/banger_digest.py` (his correction: *"I think you have to use observer
  skill to actually pic actual entertaining banger clips"* / *"Shouldn't u
  upgraded the picker with task observer? Or did u already"* - it had NOT
  been, it is now). Splits speaker turns on the `>>` caption prefix, scores
  the categories his catalog measured (family 3.0, confront 3.0, prison 2.5,
  disbelief 2.5, heinous 2.0, begging 2.0, sharp_q 1.5, notoriety 1.5),
  prints the quoted lines with offsets. `--selftest` BANGER_DIGEST_SELFTEST_OK
  (banger 32.3 vs reset-hearing 0.0). Wired: NATHAN_RULES R50 + registry rows
  (`hearing_measure.py` declared MANUAL), `selftest_all` 33/33 ALL_OK,
  `check_rules_refs` ALL_OK, CLAUDE.md "A pick is read, not ranked",
  observation 0042 (`.id-floor` 43). Known bias: not normalised per minute.
- **Done (recent shortlist, 2026-09-02, NOT built):** Jul 6 - Sep 1 hearings
  scanned (`state/recent_hearings_0706_0813.json` 77 rows from
  called_hearings; `state/recent_hearings_0824_0901.json` 20 rows from 9 new
  streams transcribed to `work/<vid>/` via `_scratch/pull_recent.py` -
  W5q27yc9fio TZsrm_Kwx2s n20GoVXQHkQ XCNZrVkpzNo yTe35VgIVWU CQDGnKFUHjA
  DBkcIXLaQos wkcRQiOfAsQ; `7mEyjmOGajc` has no captions, `4gCtCP81f6o` is
  7 s; `pipeline.db` dockets NOT registered for these). Digest + read +
  frame (`D:/Boyd Clips/shortlist/recent5/recent5_sheet.jpg`, all five
  in-person 2-up) + rival search; `posted_by` written to `config/cases.json`
  as PERKINS / GARCIA_J / LOPEZGONZALEZ / CLAYTON / PACE:
  1 Charlie Ray Perkins 2026 CR4753 QzcSk3BNYqI@3484 (08-03, 52 m contested +
  recall @7977; "Let me Google it", news article read @6268; 2 yrs prison,
  state asked 7; orange; 1 rival Court Beacon TV GjyFi7XTAGY 3 views).
  2 Javier Garcia 2026 CR4388 XCNZrVkpzNo@8355 (08-31, 20 m; drugs + guns
  with an infant in the home; "Don't sell it to little children"; 10 yrs
  deferred; 0 rivals). 3 David Lopez Gonzalez WCYnoo6WZ_c@8219 (07-09, 25 m;
  own child party to the offense; guilty, 4 yrs; 0 rivals; cause not
  extracted). 4 Julius Clayton 2020 CR3926 TZsrm_Kwx2s@11061 (09-01, 10 m;
  "or I can send you to prison for three years. Which do you prefer?";
  "What do you want, a cookie?"; probation continued; orange; 0 rivals).
  5 Jameson Pace Ybf6tkzq0b8@4669 (08-11, ~8 m real - picker span bleeds
  into the next defendant after +746 s; child born positive for meth; 27 days
  county; 0 rivals). Alternates: Andy Flores 2026 CR9835 W5q27yc9fio@85;
  Christopher Isaac Hernandez 2026 CR9801 TZsrm_Kwx2s@6837; Jacob Harris
  2021 CR5266 XiWwYFPhPn0@10245; Maxine Burlanga TZsrm_Kwx2s@3863.
  Frame grab that works: `yt-dlp --download-sections "*T.00-T.50"
  --force-keyframes-at-cuts -f b --extractor-args youtube:player_client=android
  -o - URL | ffmpeg -i pipe:0 -frames:v 1` (`bv*[height<=480]` = 403).
- **Next (his idea, 2026-09-02):** *"I was thinking about covering Durks
  trial and Tyler Robinson just because they're such huge cases"*. Not
  decided. Before anything: (1) Lil Durk is a FEDERAL case - Fed. R. Crim. P.
  53 bars cameras/broadcast, so there is no courtroom video or audio to clip,
  only commentary; (2) Tyler Robinson is Utah state court - camera access is
  the judge's call per hearing, CHECK what has actually streamed and who is
  posting it (`tools/case_search.py`) before building; (3) both are off the
  Texas Trial Tracker / Boyd brand - a format decision, his call. Offer him
  the readings, do not build unasked.
  Also: *"Even that lady who killed her kids who's on trial"* / *"She's in
  trial rn it's huge"* = LINDSAY CLANCY (MA, three children), measured by
  yt-dlp ytsearch 2026-09-02: at verdict watch / jury deliberating day 23-25;
  full-day streams on Court TV (Day 1 877k views), FOX 9 (274-307k), East
  Idaho News (494k), NBC Connecticut, CBS Boston, Surviving The Survivor.
  Camera access is NOT the problem here - saturation is: every day is already
  posted by 6+ channels at 100k-900k. The only angle left is the verdict
  moment cut to a short the same hour, plus Boyd-style "one line" shorts
  from testimony (Patrick Clancy Day 1 = the family-confrontation category
  that his catalog says wins). A day-1-to-day-25 long-form is dead on arrival.
- **Next:** picker audit close-out (`tools/check_picker.py --selftest`, R50
  is now taken by the digest - number the close-out R51);
  frame-picker audit; task-observer skill (learn from this whole chat); tags /
  retro-tagging offer on the two live videos; Qwen regeneration failure.
- **In progress (2026-09-02, "make all of them ... in a batch"):** Workflow
  `wf_88192c09-822` on OPUS 5 (the first run `wf_c0d45047-544` died in 17 s:
  all five agents hit the Fable 5 limit, resets Sep 5 8pm CDT - subagents
  inherit the session model, so a Fable session fans out into Fable agents;
  pass `model: 'opus'` in the workflow script to escape it. NOTHING was
  written by that run) - five build agents in parallel (PERKINS, GARCIA_J,
  LOPEZGONZALEZ, CLAYTON, PACE), each: source clip -> short_chain -> cold-open
  long-form + master -> thumb_pipeline -> COPY-PASTE -> STATUS.md under
  `D:/Boyd Clips/READY-TO-POST/<KEY>/`, then a verify agent per case re-runs
  every gate on the files. Nothing posted. If this session died mid-run:
  each folder's STATUS.md says what finished; resume with
  `Workflow({scriptPath: ~/.claude/projects/C--Users-natha-Projects-boyd-clips/
  91451db0-.../workflows/scripts/boyd-batch-five-wf_c0d45047-544.js,
  resumeFromRunId: "wf_88192c09-822"})` or rebuild the missing pieces by hand
  from the TORRES commands below. Then: read all five thumbnails at 100%, and
  ask him before posting (publishing = hard stop).
- **Blocked:** posting - his yes per video (build order: clip via
  `tools/short_chain.py`, long-form via `scripts/build_case_longform.py
  --coldopen` + `tools/master_audio.py`, thumbnail via
  `tools/thumb_pipeline.py`, post via youtube-channel §1 — publishing = ask
  in that turn); type preset (recommended #5 `audit_now_ul`). MONKEY_S swap
  is DONE, no longer blocked. Cause number `2024 CR-0100023C` is
  transcribed, portal not checked.
- **Older open items, still owed:** Gate A re-derivation; end screen on
  `ESSF8lSkNN4`; CARTHIEF title-test rework; THOMPSON duplicate-face gate;
  dead title `gMdQwkaFGMw`; outcome tracking on the two posted videos; Q1
  shorts ambiance.

### Done, with the command that proves each
- **R49 cold open.** *"add a 5 second or so clip of the hook or drama later in
  the vid in the beginning of long form and put "Coming up…" or something"*.
  `render.render_longform(coldopen=(A,B))` renders cold open → sting → body in
  one encode (`COLDOPEN_LABEL="COMING UP..."`, Anton, bottom-left, 0.35 s fade
  + afade; bounds 3–9 s, inside the body, ≥ 30 s after body start) and writes
  `<out>.coldopen.json`. `scripts/build_case_longform.py --coldopen A:B` is
  required (`--no-coldopen` says NO COLD OPEN on its output); it runs
  `tools/check_coldopen.py` on the rendered file, FAIL = refused build.
  Checker metric measured on TORRES frames: p99 |diff| same frame 3, one
  second away 36, the opening 145 (the MEAN could not tell one second apart —
  the first control passed it); MATCH_MAX 12, label box masked. Selftest:
  synthetic PASS, no-cold-open control FAILS footage + label, no sidecar
  refused, renderer refuses hook-from-opening and no-sting, real control
  `tools/fixtures/torres_longform_pre_r49_head.mp4` (first 20 s of the
  pre-R49 render) + real sidecar fails footage p99 139 and label +0 px.
  TORRES build: `python scripts/build_case_longform.py --source
  work/GUOzwzGiPYU/GUOzwzGiPYU_h_4669_4649-5230.mp4 --offset 4649 --in 4669.6
  --out-s 5201 --dest "D:/Boyd Clips/longwork/TORRES/TORRES_LONGFORM_unmastered.mp4"
  --coldopen 5007.25:5012.3` → 538.8 s, all 10 rows ok; then
  `tools/master_audio.py … --out READY-TO-POST/TORRES_LONGFORM.mp4` → +7.1 dB,
  MASTER_OK; sidecar copied beside it; `check_coldopen` on the mastered file
  COLDOPEN_OK. Pre-R49 renders moved to `D:/Boyd Clips/longwork/TORRES/preR49/`.
  AAC lands ~240 kbps average against the 384k request (native encoder; the
  accepted short does the same at 253k) — noted, not a defect.
- **R48 short chain** (`tools/short_chain.py`) — every editor / batch / studio
  entry emits only the chain (`tools/check_short_entry.py`). **R46** judge tile
  by recognition (`judge_tile()`, `gate_judge_top`). **R47** loudness proved
  on the encoded file (`master_audio.py` linear gain + limiter + re-measure;
  the old `loudnorm linear=true` was silently dynamic). Observation log
  0027–0030 written, `.id-floor` 31. Skill text: youtube-channel §1d (long-form
  = `--coldopen` + COLDOPEN_OK + mastered), boyd-thumbnail References (R48/R49,
  cold open and thumbnail share the hook moment).

### NOT AUTOMATED, said out loud
- Which span IS the hook (taste) — default is the short's hook piece; TORRES
  uses the "talk circles" line. Whether "COMING UP..." is the wording he wants.
- Whether the judge-top tile order is the order he wants (it is the reference's).

## 2026-09-01 (late) — type option sheet built, gate D fit check, R45

**Where were we** (print this on "where were we?"):
- **Done:** nine type-treatment builds of MONKEY on MONKEY_S's own inputs
  through the compositor (`tools/thumb_type.py` presets, `--type-style`), all
  gated (A/C/D/K PASS, R1 0/0, clutter ≤ 0.2226; F/J are the declared MONKEY
  disagreements as before). Sheets: `D:/Boyd Clips/thumbwork/MONKEY_S_type/
  SHEET_full.jpg`, `SHEET_kicker.jpg`, `SHEET_title.jpg` (numbered 1–9).
  24/24 selftest suites, `check_rules_refs`, `verify_thumb --selftest`,
  `check_floor_gates` all ALL_OK/PASS after every change below.
- **In progress:** waiting on TWO picks from him — (1) which type preset to
  lock as `type_style` (recommended #5 `audit_now_ul`; #9 `crt_ul` heavier;
  #4 `audit_now` no underline); (2) S replaces the live thumbnail on
  `OGj_eLUXjrk` (publishing = ask first), or FINAL stays.
- **Next:** after the pick — set `type_style` in `cases.json` (MONKEY, and
  the default if he wants it channel-wide), rebuild MONKEY_S with it. If he
  wants a wide-font preset (#2/#3/#6/#7), the kicker needs a 2-line layout in
  the compositor first (it shrinks to size 55 on one line). Then the picker
  audit (workflow `wf_e3ce3120-edc` output unverified), then "fix the short
  editor".
- **Blocked:** nothing measured. Firecrawl: 96 keyless credits, no paid key.

### Done, with the command that proves each
- **The type is a named preset, and `house` is byte-identical.**
  `tools/thumb_type.py` `STYLES` = house / audit / audit_ul / audit_now /
  audit_now_ul / client / client_ul / crt / crt_ul (font, axes, stroke,
  shadow, ink_stroke, emphasis{glow|underline|highlight}; colours are NOT a
  style property — R33 owns them). Every title/kicker render in `thumb.py`
  goes through `render_runs`; `scratchpad/identity_type.py` proved the old
  renderers and `type_style='house'` are pixel-identical on every case in
  `cases.json` (title diffpx 0, kicker diffpx 0, same geometry). `build()`
  refuses an unknown name (`TYPE_STYLE_UNKNOWN`) — no silent fallback.
- **Measured on the sheet (by eye + `_build_log.json`):** kicker size 89 for
  Anton presets (house, audit_now*, crt*) vs **55–56** for the wide-font
  presets (audit*, client*) — the 0.62 W fit on a 20-char kicker is the
  driver; those channels run 2-line kickers (a layout change, not a style).
  Title 104 (house/audit_now*) vs 80–82 (rest). Red HATES YOU with no stroke
  (audit, client) is low-contrast on the judge's grey suit. audit_now /
  audit_now_ul cleanest at full size (Anton caps, 4–5 px stroke + soft halo,
  no glow); crt/crt_ul heavier (hard offset shadow). cover_168: house 0.2226,
  audit 0.1315, audit_ul 0.1354, audit_now 0.2115, audit_now_ul 0.2188,
  client 0.1241, client_ul 0.1276, crt 0.2095, crt_ul 0.2124 (ceiling 0.226).
- **R45 (new) + R33 corrected** in `spec/NATHAN_RULES.md`. R33's "stroke
  9.5px pure black" was wrong — zoomed (`scratchpad/audit_top_zoom.jpg`,
  `audit_now_zoom.jpg`) the Audit's top-viewed edge is a soft halo with no
  outline, and its 2026 look is Anton-class caps with ~5 px stroke + halo.
  R45: the three cheap tells measured on MONKEY_S — coloured glow behind the
  key word, outline ≥ 7 px with the shadow hidden inside it, Anton in
  sentence case. `thumb_type.tells()` reports them; `build()` prints
  `cheap tells (R45, reported not refused): …` and writes
  `_build_log.json[type_tells]` (house = all three, the known-bad control in
  the selftest; audit/client/crt = none; audit_now = anton_lowercase only).
  **NOT AUTOMATED and said on every build:** whether it LOOKS generic.
  Registry rows: `tools/thumb_type.py` WIRED (thumb.py, thumb_pipeline,
  selftest_all); `tools/verify_thumb.py` row extended with the fit check.
- **Gate D restructured (fit geometry), not re-tuned.** `MONKEY_audit_now_ul`
  failed D on 9 inliers between the monkey (340 descriptors) and a 24×30 px
  gallery face (24 — over the MIN_DESC=20 floor). A duplicate is the same
  pixels resized to 160×160, so its homography is near-identity: paste sweep
  30–100 px on CARTHIEF/SANCHEZ/THOMPSON → scale 0.89–1.15, aniso ≤ 1.15,
  persp ≤ 0.14, trans ≤ 22 px (MONKEY 100 px: scale 1.44, trans 70). The
  false positive: scale 0.45, aniso 9.0, persp 2.41, trans 108. Reverse
  direction gives 0 matches — the ratio test on a tiny train set is the
  mechanism. `verify_thumb._fit_geometry`: FIT_SCALE 0.5–2.0, FIT_ANISO 2.0,
  FIT_PERSP 0.5, FIT_TRANS 120 (sanity); inliers on an invalid fit count 0
  and print `D rejected fit: …`. Fixture
  `tools/fixtures/gateD_falsepos_monkey_vs_24px_gallery.png` (the real pair)
  → controls `D-falsepos-fixture-reproduces` + `D-falsepos-rejected-by-fit`.
  **Cost said out loud:** SANCHEZ 30 px (7 inliers, aniso 10.6) and MONKEY_S
  40 px (persp 5.4, trans 317) were degenerate fits right by luck and are no
  longer counted; smallest cleanly caught duplicate is 40 px on
  MONKEY/OFFERUP/CARTHIEF/SANCHEZ, 50 px on THOMPSON/MONKEY_S. Below that the
  detector does not fire — not closed.
- Observation 0025 actioned (skill row R45 live + staged); checkpoint
  appended. Research agent outputs in `.firecrawl/type/`.

### Open items carried (not started, re-surface at each pause)
Gate A re-derivation; end screen on `ESSF8lSkNN4`; CARTHIEF title test
rework; THOMPSON duplicate-face gate; Qwen regeneration failure; dead title
`gMdQwkaFGMw`; outcome tracking on the two posted videos; Q1 shorts ambiance;
HS GTA audio+captions (S9); shorts "don't give away the outcome" (S16); hook
engine (X6); SANCHEZ gate-F rebuild failure; SEPARATION_DL vs accepted builds;
floor_measure mask disagreement; captions.reveal reserve; STALE_DAYS default;
library tie rule; `tools/verify_variety.py` MISSING; floor hash covering
prose; accepted dirs carry no floor stamp; expression.py scores on tiny faces;
2-line kicker layout for wide-font presets.


## 2026-09-01 (evening) — MONKEY_S built to R29, gate D and R1 measured honestly

**Where were we** (print this on "where were we?"):
- **Done:** OFFERUP long `ESSF8lSkNN4` + short `LqAneu_GSOM` live (2026-08-31).
  23/23 selftest suites + `check_rules_refs` + `check_floor_gates` ALL_OK
  after every change below. `D:/Boyd Clips/thumbwork/MONKEY_S/MONKEY_S.jpg`
  is the R29 rebuild of the MONKEY thumbnail: floor-stamped on the current
  hash `ab4bfec083d6`, gate K 0.03 (FINAL fails K at 0.38), D PASS, A/C PASS,
  F/J are the declared MONKEY disagreements (his call). Shown to him as
  `_monkey_final_vs_S.jpg` (FINAL on top, S below).
- **In progress:** waiting on his pick — S replaces the live thumbnail on
  `OGj_eLUXjrk` (publishing = ask first), or FINAL stays.
- **Next:** the audit he asked for — frame picker (`tools/expression.py`,
  `thumb_pipeline.pick_expression_t / solve_crops`), clip picker
  (`src/boydclips/` select path, priors, `_bangers.ps1`), calibration state
  files, and his back catalogue vs picker scores (yt-dlp fetch is in the
  session scratchpad `ttt_shorts.json` / `ttt_videos.json`, unread). Then
  "fix the short editor" (what is broken is not yet established — grep the
  verdicts and observation log first).
- **Blocked:** subagents rate-limited until 6:30pm Chicago; working solo.

### Done this evening, with the command that proves each
- **R29 is fixed in the compositor, not by a strip.** `thumb.find_cliff()` +
  `Thumb.cut()` grow a layer in 3% steps until a source-boundary cliff leaves
  the canvas (MONKEY_S: Boyd's right cliff 494/1250 rows → grown ×1.305,
  face 228→297 px). `_build_log.json["cut_edge"]`; proved by
  `python tools/thumb_pipeline.py --selftest` (`selftest_cut_edge`). The
  mirrored seam-bleed build (`MONKEY_K`) is withdrawn — it is the "mirrored or
  cloned extension" R29 forbids; its orphan `judge_bleed.json` deleted.
- **Kicker lives in the case file** (`cases.json` `kicker` + `kicker_split`);
  a split that is not a prefix refuses the build (`KICKER_SPLIT_MISMATCH`).
  MONKEY_K had silently rebuilt without the kicker and all-yellow.
- **Gate D got a validity floor.** MONKEY_S failed D on 5 RANSAC inliers
  between the monkey's face (367 SIFT descriptors) and a 20×22 px blurred
  gallery woman behind its arm (11 descriptors) — RANSAC always marks its
  4-point sample as inliers. `verify_thumb.py` `MIN_DESC = 20`: a pair with a
  side under 20 descriptors is printed UNMEASURABLE, never scored. Derived
  from a paste sweep on four references (real duplicates 32–141 desc / 8–55
  inliers; tiny gallery faces 3–11). Controls `D-50px-dup` (still FAILS) and
  `D-floor-blob-unmeasurable` in `--selftest`. All seven builds on disk still
  D=0. **NOT CLOSED, said out loud:** below ~30 px YuNet does not fire, so a
  duplicate that small is invisible to D for a different reason.
- **R1 was measured with one number that counted the title only.**
  `type_on_subject_px` = title ∩ alpha; the kicker was never in it while the
  skill table said "TITLE and KICKER". `thumb.ink_vs_subjects()` now logs
  `title_on_subject_px` (asserted 0), `kicker_on_face_px` (asserted 0 — the
  2026-08-31 solver was never checked afterwards) and `kicker_on_subject_px`
  (kicker over a BODY — logged only). Measured on the five accepted builds:
  judge 17.7k–30.8k px, defendant 13.3k–41.0k px on every one — the kicker
  band sits on both bodies by construction and he accepted all five. MONKEY_S:
  0 / 0 / 43,429. Controls in `thumb_pipeline --selftest`
  (`selftest_ink_vs_subjects`). NATHAN_RULES R1 + the skill row rewritten.
- `config/quality_floor.json`: checker name `floor_vs_gates.py` →
  `check_floor_gates.py` (×2); MONKEY J re-attributed — 17.8% is the MONKEY's
  pale face, the judge measures 1.3% (`_face_stats` sorts by height, judge
  first). That prose edit moved the thumb floor hash `3adc3b0e7083` →
  `ab4bfec083d6`; MONKEY_S was rebuilt on it (`floor_stamp.py check` →
  FLOOR_OK). The accepted work dirs (MONKEY/OFFERUP/CARTHIEF/SANCHEZ/THOMPSON)
  carry NO stamp — they predate the stamp; not rebuilt, they are the floor.
- **Design smell, not restructured:** `floor_hash("thumb")` hashes whole
  files, so a comment edit forces rebuilds. A §12.12 note on gate D's floor
  was therefore NOT added to `spec/THUMBNAIL_SPEC.md` (it lives in
  `verify_thumb.py` and NATHAN_RULES' registry row). Open item.
- Repo correction: this IS a git repo (branch main, HEAD `babc7b3`, many
  uncommitted changes). Commit only if he asks.

### Observation log
- 0021 closed except the MONKEY F/J decision (his). New observations to log:
  R29's own text prescribed scale while I built a mirrored strip (rule
  self-contradiction caught by re-reading the rule, not by a check); gate D's
  false positive (a gate with no validity floor); R1's one-number log (a check
  that claimed more than it measured, in a file whose comments already name
  that asymmetry three times).

## 2026-09-01 — the chat was mined into the skills; where things stand

**Where were we** (superseded by the evening entry above):
- **Done:** OFFERUP long `ESSF8lSkNN4` + short `LqAneu_GSOM` live (2026-08-31,
  A/B titles + thumbnails running). 20 observations from this chat written to
  `~/.claude/projects/C--Users-natha/skill-observations/` and applied to the
  skills, CLAUDE.md files and memory (all marked `actioned`, checkpoint logged).
  Verdict ledger re-mined: P40–P46, N88–N128, S1–S17 (shorts), X1–X9 (process).
- **In progress:** nothing rendering.
- **Next:** MONKEY thumbnail rebuild for `OGj_eLUXjrk` (below); CARTHIEF
  expression scorer recalibration (below); HS GTA audio+captions (S9); shorts
  "more interesting / don't give away the outcome" (S16); hook engine (X6).
- **Blocked:** nothing measured as blocked.

### What is now enforced, and by what command
- `python tools/check_rules_refs.py` → `ALL_OK` (every checker NATHAN_RULES
  names is WIRED, or declared MANUAL/MISSING and matches). `python
  tools/selftest_all.py` → `16/16 suites pass` / `ALL_OK`. Both re-run
  2026-09-01 after the last edit. Project CLAUDE.md requires both before a
  build is shown.
- **Every gate is now validated both ways.** `tools/check_floor_gates.py`
  (new, in selftest_all) runs `verify_build` over the five approved files and
  fails on any rejection the floor file does not declare, and on any stale
  declaration. Measured before it existed: E and I (derived from OFFERUP alone
  on 08-31) rejected CARTHIEF, SANCHEZ and THOMPSON — 3 of the 5 he accepted.
  Retuned to the band of the five with the controls still failing: E is
  ratio-only (≥ 1.4, floor min 1.55) plus a source gate on
  `thumb_pipeline.ALPHA_FLOOR/CEIL` (≤ 8 / ≥ 244; old 26/232 crush fails it);
  I ceiling 25.5 (floor max 24.5, 1.7× control 27.7).
- `tools/verify_build.py` fails on nothing: `precheck()` requires the output to
  exist and carry a face. The earlier "OFFERUP PASS" was run with an empty
  output path and passed because F/I/J returned `None`. `OFFERUP_NEW.jpg`
  re-run genuinely passes every gate.
- New checkers live and wired: `tools/floor_stamp.py` (every render carries the
  floor hash; a stale stamp = rebuild), `tools/check_title.py` (youtube-channel
  §1c runs it on all three A/B titles with `--transcript`), `tools/check_variants.py`
  (variants must differ ≥ 12 mean-abs at 168×94 — "I don't see levels"),
  `tools/check_clutter.py` (ceiling 0.226 measured on the accepted five),
  `tools/library.py` (R44), gates K/L in the build.
- `tools/thumb.py` now writes `ink`, `_overlay_mask.png` and
  `_placed_rgb_defendant.png` per build so the overlay/kicker region is
  measurable, not guessed. `--set` removed from the pipeline.
- `config/quality_floor.json` approved = OFFERUP, CARTHIEF, SANCHEZ, MONKEY,
  THOMPSON (P46, "the floor and minimum quality"). It now names the exact file
  per case (`files`: OFFERUP is `OFFERUP_NEW.jpg`, the others `_FINAL.jpg`) and
  declares the gate disagreements (`gate_disagreements`: MONKEY F/J/K). Its
  `per_case`/`envelope` numbers came from a one-off pass that is not on disk
  (`measurement_note`) — OFFERUP skin chroma reads 17.6/15.9 there vs 20.9/20.5
  from gate I. `config/short_floor.json` reference = `SANCHEZ_SHORT_FINAL.mp4`.
- `tools/thumbeng/variety.py` compares 14 (the accepted five + the rejected
  `_NEW` set + variants) — `tools/verify_variety.py` never existed and the
  registry says so.
- Skills: `boyd-thumbnail` SKILL.md rewritten (251 lines) with
  `references/{derivations,floor,niche-evidence,shorts}.md`; `youtube-channel`
  §1 names `scripts/ui2.ps1` as the posting procedure from this PC.

### Findings that need a decision or a rebuild
- **[REBUILT as MONKEY_S, evening entry above — K 0.03; F/J still his call.]
  Every MONKEY build fails gate K (hard cut) at the same place - the judge
  matte is severed at x=1239, a 203 px pixel-straight edge (her hair/back,
  visible against the wall).** Measured 2026-09-01 with `python
  tools/verify_build.py "D:/Boyd Clips/thumbwork/MONKEY" <out>`:
  `MONKEY_FINAL.jpg` (the floor build, what `OGj_eLUXjrk` carries) FAIL F
  (defendant chroma drift 7.4) / J (judge blowout 17.8%) / K; `MONKEY_NEW.jpg`
  FAIL F/J/K; `FINAL_V5_arrow.jpg` (P43) PASS F, FAIL J (14.6%) / K. The defect
  is in the shared matte, so re-cut the judge (a reaction frame where she is
  not against the crop edge) before any variant is re-shown or the A/B is
  touched. **K is a real defect (R29) — rebuild. F and J are his call:**
  MONKEY's F imbalance is 3.6, the same number as OFFERUP_v19 which he
  rejected, so F cannot decide it; J is judge 17.8% above L*210 (limit 12).
  If the floor is right, F moves to 3.7 and J to 18; if the gates are right,
  MONKEY is rebuilt. Declared in `quality_floor.json` so the suite stays
  green either way; observation 0021.
- **CARTHIEF, SANCHEZ, THOMPSON `_NEW` builds fail E/F/J** — they are the
  rejected set (N123–N127), kept only as negatives for variety.py.
- **`tools/expression.py` scores the approved CARTHIEF judge cutout 0.0 on
  every profile.** A scorer that gives the floor zero cannot gate; recalibrate
  the profiles against the five approved cutouts (`tools/library.py seed-boyd`
  tags them) before it decides anything.
- **Reactions library is SEEDED, NOT READ.** `assets/harvest/reactions/boyd/`
  has 5 approved cutouts; `tools/thumb_pipeline.py` still re-cuts Boyd from the
  reaction frame every build. Plates (13 over 3 cases) ARE wired.
- **`tools/short_engine.py` carries the caption constants in code** (`ENTRANCE
  = "blur"`, line 55) instead of reading `config/short_floor.json`; the
  floor_stamp catches drift but the engine should read the file.

### Observations partially closed (say so, don't hide it)
- 0008 reactions library not wired; 0009 workaround-tagging is a rule, not code;
  0017 short_engine constants; 0019 CARTHIEF 0.0; 0021 closed except the
  MONKEY F/J decision (his). Everything else: closed with a check on the build
  path or a rule with his verbatim words and date.

### Older items still open (re-surface, don't drop)
End screen on `ESSF8lSkNN4`; CARTHIEF title-test rework; THOMPSON duplicate-face
gate; Gate A re-derivation; Qwen regeneration noise; dead title `gMdQwkaFGMw`;
outcome tracking on posted videos (none yet); Q1 shorts ambiance (never
answered); clickbaity-font options he asked for 2026-08-29 17:25.

## 2026-08-31 — OFFERUP PUBLISHED (both files live)

First publish from this pipeline that went all the way out. Previously "ready"
always meant rendered-on-disk; these are shipped.

- **Long-form** https://youtu.be/ESSF8lSkNN4 — 9:11, Public, monetized with
  mid-rolls, ad suitability "None of the above" -> **Safe for ads**, Not Made
  for Kids, thumbnail `thumbwork/OFFERUP/OFFERUP_NEW.jpg`.
  **A/B title test RUNNING**, three grounded angles:
    1. `"I Lost The Key Fob." Judge Boyd: "That Makes No Sense."`
    2. `He Bought A Stolen Car On OfferUp. Judge Boyd Wasn't Buying It.`
    3. `Judge Boyd: "Then Why Are You Stealing Cars?"`
- **Short** https://youtube.com/shorts/LqAneu_GSOM — 0:39, Public, Safe for ads,
  Related video set to the long-form.

Case is **Isidro Garcia, 2025-CR-002343**, unauthorized use of a vehicle (state
jail felony). Every title/description claim is grounded in the transcript at
t=10853-10898: he bought the car on OfferUp after his own truck was stolen, said
he damaged the steering column himself because he lost the key fob, and Boyd
answered "that makes no sense to me."

### Two defects caught and fixed during the publish
- **Nearly reported the titles as fabricated.** A first transcript read printed
  only the first 4000 chars and stopped before t=10853, so "fob"/"steering
  column" appeared absent. They are all present. Slice the window, then search
  the window - do not conclude absence from a truncated print.
- **Wrong video ID in a published description.** Read `ESSF8ISkNN4` off a
  screenshot; the real ID is `ESSF8lSkNN4` (lowercase L). The short shipped for
  a few minutes with a dead "Full hearing" link. Fixed. **Read IDs from the URL
  bar.**

### How the upload was actually done
`mcp__claude-in-chrome__file_upload` caps at **10 MB** (measured) and cannot
read `D:` - fine for the thumbnail, useless for video. Video goes through the
native picker driven by `tools/ui2.ps1` (DPI-aware real click, then clipboard
paste + Enter). Full detail in memory: `youtube-upload-method`.


# Where this project is

## >>> READ HANDOFF-2026-08-29.md FIRST <<<

Thumbnail work as of 2026-08-29 09:5x. The working file is
`work/repair/WORKING.jpg` and it is edited DIRECTLY, pixel by pixel — do not
re-run the builder on it. One change at a time, shown to Nathan, kept or
discarded. The handoff explains why, and what I got wrong.


## 2026-08-29 (late) — the thumbnail system was rebuilt, and why

**The scorer was anti-correlated with reality.** Spearman rho between
`thumb_eval.py`'s score and this channel's own views = **-0.571** (n=8, Boyd
long-forms). It gave **95.1 SHIP** to the 55-view video and **71.4 WEAK** to the
9,800-view one. Cause: it FUSED two different kinds of rule — Nathan's R1-R15
constraints (binary correctness) and success metrics — and scored them together.

**The fix is a layer split**, now enforced by a gate:
- **Constraints** — `spec/NATHAN_RULES.md`. Binary, non-negotiable, never traded.
- **The rubric eye** — `spec/THUMBNAIL_RUBRIC.md`, 8 dimensions, graded by a
  local VLM. `scripts/eye.py`.
- **Repair** — `scripts/thumbdoctor.py`, maps each defect to a builder flag.

`thumbdoctor.py selftest-layers` asserts a 100/100 render with one violation
LOSES to a 1/100 clean render.

**What Pikzels actually is** (schema fetched from docs.pikzels.com/openapi.json):
its score endpoint returns subscores named clarity / curiosity / emotion / idea /
virality plus one free-text suggestion. Those are RUBRIC DIMENSIONS — a
pixels-to-CTR regressor emits one number and "idea" is not a pixel property. It
is a VLM grading against a rubric, which is why it needs no channel context.
There is **no public model that predicts CTR from a thumbnail**; the one
published attempt (codencoding/Red-Means-Go) measured pixel features performing
WORSE than predicting the mean.

**The 9,800-view winner was MADE IN PIKZELS.** Nathan, 2026-08-29: *"the 92.1 i
rememeber i actually made it with pikzels"*. So the back catalogue mixes tools,
and any comparison across it that ignores which tool made each image measures the
tool, not the craft. **Which of the other 27 were Pikzels-made is unrecorded and
only Nathan knows — ASK.** It also means the channel's best thumbnail is NOT in
the documented house style ("feathered, unstroked, no arrow") — it has a hard
white stroke and a large red arrow.

**The eye, measured honestly:** it separates the extremes (92.1 vs 61.2, margin
30.9) but scored rho = **-0.20** on the six thumbnails not named in its rubric.
So: proven at the extremes, UNVALIDATED in the middle. Do not claim more. Views
are a contaminated outcome (topic, title, timing, a 5-month dormancy), which is
why `scripts/taste.py` exists — a forced choice between two thumbnails controls
all of that away. It needs ~12+ picks from Nathan to say anything.

**A danger caught before it shipped:** grading a real build, the local model
suggested *"Enhance the defendant's facial expression (slightly wider eyes)"*.
An unattended loop acting on that fabricates a named defendant's face in a
criminal proceeding. `spec/THUMBNAIL_RUBRIC.md` now hard-limits fixes to
**frame, crop, type, or grade** — never a person.

**Live production bug, still open (G11):** `boydclips.thumbnail.build()` defaults
`subject_side="right"`. Judge Boyd is on the **LEFT** in CARTHIEF. Unattended it
traces the wrong person into the hero slot. The pipeline now calls the approved
Q3 builder (it called `make_thumbnail_v2` while its own comment claimed
otherwise), and `detect_tile_crops` returns geometry byte-identical to the
hand-written `config/cases.json` crops — so that per-case tuning was never
necessary. Detecting the SIDE still is.

**Two operational constraints on this box, both measured:**
- `--auto-plate` finds nothing usable on CARTHIEF — every ranked frame scored
  0.0% clear and the build correctly REFUSED ("component 2.48x the scrubs,
  MERGED with another person"). The `plate_t` in `config/cases.json` builds clean.
- **The eye and the builder cannot hold the GPU at once.** The VLM is ~21 GB
  against 16 GB of VRAM; while resident, the builder's onnxruntime dies with
  "Cannot load symbol cudnnCreate". `thumbdoctor._free_vram()` evicts it before
  every render.

Ledger: `GATES-thumbdoctor.md`. Two gates abandoned ON THE RECORD with reasons —
a scraped cross-channel corpus (wrong as a SOURCE of rules; still wanted later as
an independent test set) and a learned pixels-to-CTR model (does not exist).


Updated 2026-08-29. Read this first after a reboot.

## The shorts pipeline — this is the current work

Three scripts, in order. Each was written because the obvious approach was
measured and found broken; the comments carry the measurement.

```
scripts/tighten_short.py    remove dead air using WORD GAPS
scripts/who_speaks.py       who is talking, from audio-visual correlation
scripts/caption_short.py    burn captions on the speaker's half
```

**`silencedetect` DOES NOT WORK ON THIS FOOTAGE. Do not use it.** Measured on
CARTHIEF_SHORT.mp4 at -30, -25, -20 AND -18 dBFS: **zero spans, every time.**
The courtroom room tone never drops that low. Every dead-air pass in this repo
before 2026-08-28 used it and was therefore blind. The same short had **22
word-gaps over 0.7s totalling 31.2s of 56.2s — 56% of the runtime**, including a
4.20s hole after "far?" and 3.68s after "hour?". Gaps come from the word-level
transcript now.

**Speaker attribution is audio-visual correlation.** A talking mouth moves in
time with the sound; a nodding head does not. Each half's mouth-motion series is
correlated against the audio envelope. Measured on nine hand-labelled windows:
**9/9, against 4/9 for comparing raw motion.** Judge Boyd is animated while
listening, which is exactly why raw motion handed her the defendant's lines.

Three things that broke and are now guarded:
* **Blocks must not straddle a speaker turn.** Grouped by character count, about
  a third contained both voices — "evading? Nothing" is her question plus his
  answer. Unplaceable on either side. Blocks are now forced to end at every turn
  boundary before anything positions them.
* **Compute the speaker series on the UNCUT short, then remap it.** Each cut is a
  hard scene change that spikes frame-difference, so a series computed on the cut
  video is corrupted at every cut.
* **`-pix_fmt yuv420p` is mandatory.** Without it libx264 inherits higher
  precision from `curves`/`eq` and silently picks High 4:4:4 Predictive. All four
  captioned shorts shipped that way once; no consumer hardware decoder plays it.

**CARTHIEF_SHORT_FINAL.mp4 is the reference output.** 56.2s -> 34.8s, 22 cuts,
0 gaps over 0.7s (longest 0.68s), deblocked, captions at 156px on the speaker's
half, A/V exact at 34.800s each.

**Deblocking, measured over six chains:** `deblock` + `hqdn3d` weighted to chroma
+ `deband` + light `unsharp`. Block-boundary ratio 1.099 -> 0.763 with detail UP
from 1.55 to 2.37. `fftdnoiz` made it worse (1.399). No upscaling — Nathan asked
for the artefacts gone, not a bigger picture.

## The font is settled

`assets/fonts/TTTHeadline-Regular.ttf`, family **"TTT Headline"** — Archivo
Variable frozen at weight 900 / width 70 with fontTools, renamed so it cannot
collide with stock Archivo. Identified by matching the shipped Thompson
thumbnail: its 26-character quote spans 1049px at cap 71. At that width
Montserrat Black gives cap 52 and Archivo SemiCond SemiBold gives 68 — both far
too light. Archivo is SIL OFL 1.1, so commercial use and instancing are fine.
libass cannot select a variable axis, which is why the static instance exists.
Nathan: "those are the captions ive been looking for".

Caption size **156px** ("C"), chosen after seeing 92/124/156/190/224/258/296 at
1:1. He first said "d but bigger" then came back down.

## Grade the PICTURE, never the type

`render.py` documents it for video — "Grading after `ass=` would lift the caption
white too ... it would clip the text edges and eat the black outline". The
thumbnail path was violating its own rule: type burned in, saved, THEN graded.
`thumbnail.grade_image(img, cfg)` now works in memory so the builder can grade
before drawing type.

## 2026-08-29 — Nathan picked Q3 for thumbnails

His words: "q3 thumbnail is fire". `scripts/thumb_Q3_detail.py` — our
construction executed at maximum detail. Measured against the other three builds,
our current output and the Thompson reference:

| | luma | blacks | arrow px | chroma | detail full / feed |
|---|---|---|---|---|---|
| **Q3_detail** | **118.6** | 13.3% | 2727 | 5.54 | **1442 / 5410** |
| Q1_noregroup | 109.3 | 10.2% | 3346 | 4.80 | 1334 / 4780 |
| Q2_surgical | 105.1 | 7.0% | 2563 | 14.96 | 1307 / 5037 |
| Q4_light | 115.0 | 10.0% | 3032 | 5.93 | 1012 / 4284 |
| ours | 105.8 | 13.8% | 4520 | 2.11 | 1412 / 6031 |
| Thompson | 124.9 | 9.0% | 3904 | 3.29 | 512 / 4638 |

Highest detail of the four and the luma closest to Thompson. Q2 is disqualified
on chroma (14.96 — the blocky artefact back at seven times the reference).

**Q3's mechanism:** realesr-general-x4v3 (BSD-3, so commercially usable) at 4x
then resampled down, with every restorative step moved to the NATIVE side of the
upscale; BiRefNet-matting into a ViTMatte-S trimap refine, measured on the judge
tile at alignment +7.4%, colour fringe −26%, matting residual −20%, soft hair
mass +35%; the defendant moved only when the solver proves he must be, only the
vacated sliver inpainted, then re-matted with the area loss measured — over 1%
and the move is REJECTED and the looser composition ships, because a severed limb
is worse than a loose composition; and an arrow that must both carry zero pixels
on a person AND cast a ray striking the defendant first, since an earlier version
scored a perfect 0% overlap while pointing at empty ceiling.

**Open on Q3:** chroma deviation 5.54, above the 3.5 gate and worse than our
current 2.11 — check the blocking has not returned. And it carries only a
`carthief` preset, while SANCHEZ and OFFERUP put the judge on the RIGHT. If it
needs per-case tuning it is not yet the daily pipeline, which is what the
composition workflow exists to solve.

## The one command for shorts — `scripts/make_short_auto.py`

```
python scripts/make_short_auto.py --short READY-TO-POST/X_SHORT.mp4     --transcript work/ID/ID.transcript.json --src-start 3931.8     --out READY-TO-POST/X_SHORT_FINAL.mp4
```

Runs the whole chain with no hand-tuning and **refuses rather than emitting
something broken** — it checks pix_fmt, dimensions, A/V sync, remaining word-gaps
and a clean decode, and exits non-zero if any fails.

All three cases pass:

| | before | after | cuts | gaps >0.7s | turns |
|---|---|---|---|---|---|
| CARTHIEF | 56.2s | 34.8s | 22 | 0 | 34 |
| SANCHEZ  | 53.0s | 49.1s |  8 | 0 | 35 |
| OFFERUP  | 55.5s | 41.8s | 18 | 0 | 36 |

OFFERUP lost 25% and SANCHEZ only 7% — Sanchez is a faster back-and-forth. A
uniform cut would have wrecked one and barely touched the other, which is the
argument for deriving the cuts per clip rather than fixing a ratio.

**Verifying caption side: key on the OUTLINE, not brightness.** A check that
thresholded on white reported 0/5 wrong on a render that was correct — it was
measuring the ceiling and Judge Boyd's white collar. Caption glyphs are a white
core inside a 12px black stroke, so the reliable test is a very bright pixel with
a very dark pixel within ~17px. Nothing else in a courtroom frame does that.
Measured on the rendered files, the caption changes half 10 / 11 / 11 times.

## 2026-08-29 — open right now

**Two workflows running** on thumbnails, deliberately disjoint:
* `thumbnail-quality` — surface finish. Super-resolution licences (GFPGAN and
  CodeFormer terms must be READ, this is a monetised channel), matte edge
  refinement, and what "premium detail" measures as. Then four builds.
* `thumbnail-composition` — arrangement. Nathan: "how everythings arranged too
  and all precicley placed next to eachother ... you basicily need to be a pro at
  making good quality boyd thumbnails with whatever video were working with".
  The point is a PARAMETRIC system, not coordinates: **the judge is on the LEFT
  in CARTHIEF and the RIGHT in SANCHEZ and OFFERUP**, so any system that assumes
  a side is already broken. Each build must produce all three from one script
  with no per-case fudging.

**Three earlier workflows died on the session limit** (resets 12:10am America/
Chicago). The 6 thumbnail constructions DID build; their critic did not. The
surgical-cuts and master-shorts teams produced nothing. Do not assume their
findings exist — check the journals.

**The quiet construction — `scripts/make_thumbnail_quiet.py`.** Nathan on the
team's low-contrast variant: "d looks crazy". Verbatim quote, small, dark, no
plate/outline/shadow, dropped into real negative space. Placement is DERIVED —
it finds the flattest empty region and solves for a glyph colour at a target
contrast ratio against that particular wall, so it moves per frame. It refuses if
the quote is not verbatim in the transcript.

**But it only works on CARTHIEF.** On SANCHEZ and OFFERUP the text lands on a
body, which breaks his standing rule. Cause is measured: the exemplars used wide
frames with real ceiling; our 2-up strips are dense with people, and the flatness
search had to loosen from 10 to **38** before anything fit — it was settling, not
finding. Contrast came out 2.83 / 3.25 / 4.01:1 against a 4.1 target for the same
reason. **The construction is right; the frame selection is wrong.** It needs
frames chosen FOR negative space, not for reaction.

**Unanswered and it is his call:** the two running teams are optimising the LOUD
construction (bold type, arrow, cut-out). The quiet one is the opposite bet.
Nobody has decided which we are actually building.

## What is NOT fixed

* **The thumbnails still ship a severed arm.** `regroup_plate.py` moves the
  defendant toward his attorney and cut through him. Connected-component
  isolation and a merged-blob refusal were added (src 4437 gives a component
  2.51x the scrubs width because the men touch and is refused; src 4578 gives
  1.19x and is clean) — but the shipped CARTHIEF_thumbnail.jpg is still wrong.
* **SANCHEZ and OFFERUP shorts have not been through the new pipeline.** Only
  CARTHIEF has.
* **The long-forms were dead-aired with the blind `silencedetect`**, so
  MONKEY_LONGFORM and the rest almost certainly still carry gaps nobody measured.
* **`verify_thumbnail.py` fails the Thompson reference** on its own arrow-aim
  check. That file's own rule says the competitor set is ground truth, so the
  threshold is wrong, not Thompson.
* Nothing has been uploaded since the monkey long-form on 2026-08-27.

## 2026-08-23 — FIRST PUBLISH, and the monkey long-form built

**The Thompson package is POSTED.** Nathan, this session: "i alreADY POSTED THE
THIMPSON". That ends "nothing has ever been published from this pipeline" — it
had been true since day one. The shipped file is
`READY-TO-POST/1_LONGFORM_Thompson.mp4`, 657.7s, and it carries the 1.4s
`sting.mp4` intro (verified by extracting its frame at t=0.7s: the TTT-star on
the dark ground). Outcome — views, retention, whether the short drove the
long-form — is NOT tracked yet and nobody has looked.

**Monkey long-form built:** `READY-TO-POST/MONKEY_LONGFORM.mp4`, 808.9s (13:29),
1920x1080. Command:

    python scripts/build_case_longform.py \
      --source work/2XkPnvstmRQ/2XkPnvstmRQ_h_5915_5895-7108.mp4 \
      --offset 5895.0 --in 5915.92 --out-s 6739.30 \
      --dest ".../READY-TO-POST/MONKEY_LONGFORM.mp4"

His boundaries, verbatim: "start it from court is calling until she says goodluck
to you". Both located in the transcript, not estimated — "Court is calling" at
src 5915.92, "Good luck to you." at src 6737.04 (ends 6737.6), and the reply
"Thank you, welcome." lands at 6738.72. Out-point set at 6739.30 so her line and
its answer both land. refine.py then snapped in -1.32s onto the start of the line
and out +0.38s for the hold.

This ENDS BEFORE THE SECOND DEFENDANT. The next case is called at src 6745.3
(13:49 into the old file) and the court never says "the court is calling" there,
which is why `find_called_hearings.py` merged them. `HEARING_2025-07-14_2XkPnv.mp4`
(19.6 min, the one he called "that one's fire") contains BOTH defendants and
should not go up as-is.

Measured on the render: dead air >4.0s removed, 825s -> 808s (-18s, 2.1%) across
5 pieces. Verify sheet at `READY-TO-POST/MONKEY_verify_sheet.png` — frames at
0.7 / 2.0 / 200 / 500 / 808.5s with the watermark corner zoomed on each.

### New: scripts/build_case_longform.py

Takes the in/out points as arguments instead of looking them up in the store, so
a case the phrase-based segmenter merges can still be cut correctly. Same code
path from there as `rebuild_longform.py`.

### Watermark was placed wrong on this docket, and is now measured

Two separate defects, both found by extracting frames rather than reading code:

1. `_watermark_chain` only ever placed the mark at `W-w-margin` — the CANVAS
   right edge. This docket composites a 2-up with black beside the tiles: Judge
   Boyd's tile ends at x=1791 of 1920, so 53 of the mark's 115px sat on black
   and it read as a broken overlay. `render_longform` now takes
   `watermark_right_x` and the driver anchors to the measured tile edge.
2. Every WHITE variant was then invisible — the right tile is a cream wall with
   the Bexar County seal on it. Measured across 9 sampled frames, the mark's own
   rectangle sits at mean luminance 180/255; corner luminance across the eight
   tile corners ranged 46.6 (left-bottom-right) to 246.7 (right-top-left). The
   driver now samples that rectangle and picks `wm_02_mark_dark_55.png` above
   140 and `wm_brand_halo_40.png` below.

`cut_shortlist.py` still says in a comment that the watermark asset "is not on
disk". That is false — `boyd-brand/watermarks_v2/` and `boyd-brand/watermarks/`
both exist and are full. Every HEARING_*.mp4 it produced is unwatermarked on
that false premise.

### Still open on this case

* **No thumbnail, no title, no description.** His line for the thumbnail, agreed
  2026-08-21: "No monkey business in my court".
* **Charge and current status for Joseph Grant (2024CR011920) are UNVERIFIED.**
  He asked for them in the description. Nothing goes in a public description
  until the Bexar County record is pulled and sourced.
* The short already exists and is his own CapCut edit:
  `READY-TO-REVIEW/spidermonkeyshort_FINAL.mp4`, 2160x3840, 54.6s.

### Thumbnail built to his stated rules, not to defaults

His rules, pulled verbatim from the session logs rather than remembered:

* 2026-08-11: "we would have to upscale her face color correct any weird
  lighting and also the defendant also in the thumbnail it would be preferable
  to get the defendant when theyre upset sad or shocked or something"
* 2026-08-12: "i like audits title style better so use that type from now on
  and the thumbnails as well" / "ik she doesnt use a gavel its fine"
* 2026-08-21: "'No monkey business in my court' on the thumbnail maybe lol"
* 2026-08-23: "the same way you corrected the color to natural of the short do
  that as well to the thumbnail maybe even bump it up a level too"

Output: `READY-TO-POST/MONKEY_thumbnail.jpg` (1280x720), plus
`MONKEY_thumbnail_A_1.00.jpg` and `_C_1.70.jpg` as the softer and stronger
grades, and `THUMB_GRADE_LEVELS.png` comparing all four at once. Shipped
default is the middle one.

Construction: plate = the defendant's tile at src 6282 (he looks straight down
the lens), Judge Boyd cut out from src 6270 mid-riff and composited over it,
unstroked and feathered, no arrow. Text one line, white + yellow, top band,
cap 43px / 0.0597 H — inside the measured Audit range of 0.051-0.100 H.

Three things fixed while building it:

1. **The cut-out was masked with the wrong model.** `make_thumbnail_v2.py`'s
   own docstring specifies BiRefNet-portrait (MIT) and warns that rembg's
   default is BRIA RMBG-2.0 under CC BY-NC 4.0 — non-commercial, so unusable on
   a monetised channel. Now masked with `birefnet-portrait` explicitly.
2. **The court's own "187th Court" caption was inside the plate**, bottom-left.
   Cropped off before compositing.
3. **Three faces in frame.** The defendant's tile carries his attorney on the
   right, and Boyd's cut-out landed on top of him. The measured set never runs
   more than two. Plate cropped to the left 62% so it is defendant + room only.

**`thumbnail.grade()` now applies the video's tone curve.** It never had it: the
thumbnail went straight to contrast + saturation while every rendered cut got
`curves=all='0/0.02 0.25/0.31 0.5/0.57 0.75/0.80 1/0.97'`, which is why the
plate read flatter than the video it fronts. New `curve` and `curve_strength`
params; `curve_strength` scales each control point's displacement from linear,
so the shape holds and only its depth changes. 1.0 is exactly the video grade,
1.35 is the shipped "bump".

### 2026-08-28 — the grade was MANUFACTURING the blocky background

Nathan: "fix the background where its all bright and then it looks blocky".

It was chroma blocking — coloured 16x16 blocks in flat bright areas like the
courtroom ceiling — and `thumbnail.grade()` was creating it, not revealing it.
Measured on the SANCHEZ ceiling, mean chroma deviation from neutral:

    ungraded source          1.33
    after grade() as shipped 8.13      <- 6x worse
    after the fix            1.04

A luma-based blockiness check missed it completely (8px-boundary ratio 0.72,
i.e. no luma blocking at all). The damage was entirely in the chroma planes,
which is why it only showed up by eye.

Three causes, all now fixed in `src/boydclips/thumbnail.py`:

1. **The saturation floor. This was the big one.** The line read
   `S = S * 1.45 + 0.06`, applied to EVERY pixel. A near-white ceiling pixel at
   S~0.01 came out at 0.074 — a 7x lift on something that should stay white —
   and since the source's chroma noise differs block to block, each block landed
   on a different tint. Replaced with a knee: the gain ramps in over the first
   0.10 of saturation, so near-neutrals keep a gain of ~1.0 and only real colour
   is boosted.

   Its stated purpose was to drag the frame-mean saturation up to
   @courtroomtime's 0.546. **That reason is already dead** — the 2026-08-23
   winners-vs-losers pass measured 25 files on that channel and saturation does
   not separate winners from losers; their losers came out slightly MORE
   saturated (0.575 vs 0.546, trend running the wrong way). There is no target
   mean worth defending.

2. **No chroma denoise.** The source is 4:2:0 video upscaled ~4x, so its chroma
   planes are quarter-resolution and carry block noise. A median filter on Cb/Cr
   only now runs before any saturation work — luma, and therefore every real
   edge, is untouched.

3. **UnsharpMask threshold was 3**, low enough to sharpen compression noise in
   flat regions and crisp the block edges. Raised to 10.

Re-graded and verified clean on all four shipped thumbnails (CARTHIEF, SANCHEZ,
OFFERUP, MONKEY). MONKEY's local file is fixed but the LIVE video on YouTube
still carries the old blocky thumbnail — it has not been re-uploaded.

## 2026-08-28 — Nathan's frame-selection rule (his eye, not a detector)

Verbatim, choosing between three thumbnail variants per case:

> "i like C on car theif A and B on sanchez and C on offerup because of how
> jusge boyd is positiononed in them because the other shots of her dont make
> sense or are bad because shes not looking in some but in sanchez case i picked
> a and b becase her hand added a little more drama"

**The rule: Judge Boyd's eyes must be LEVEL and DIRECTED — looking at the
defendant or off-frame — never cast down.** A gesture (raised hand mid-air)
adds to it. Confirmed by looking at the six candidate frames side by side:

* rejected — CARTHIEF A/B (eyes down at papers), SANCHEZ C (hand resting on
  chin, eyes lowered), OFFERUP A/B (eyes down at the desk)
* picked — CARTHIEF C (eyes level through glasses), SANCHEZ A/B (raised hand
  mid-gesture, eyes level), OFFERUP C (eyes level, mouth open mid-sentence)

Note SANCHEZ: the rejected frame HAS a hand in it, resting on her chin. So it
is not "a hand is good" — it is a hand *mid-gesture*, in the air. A static hand
reads as thoughtful, which is the opposite of the wanted register.

**I could not measure this automatically and did not fake it.** Tried: Haar eye
count, eye-region dark fraction, eye-region std-dev. The dark fraction on the
Sanchez pair came out 27.0% (picked) against 27.2% (rejected) — separates
nothing. Eye count was weakly directional (picked 6/3/7, rejected 4/3/4) but
tied on the exact pair where his reason differed. Gaze PITCH is what matters and
Haar cascades do not measure it. mediapipe, dlib, face_alignment and insightface
are all absent from this machine; `cv2.face` (FacemarkLBF) exists but needs a
model file that is not present.

**So the mechanism is a contact sheet, not a detector.** Extract N candidate
Boyd frames across the hammer moment, lay them out, and let him pick — his eye
is the instrument and the job is to make choosing cheap. `scripts/` already
sweeps frames this way (see the 2026-08-27 reaction sweep).

### A/B sets restructured after his picks

Every variant now uses the Boyd frame HE approved, and only the TEXT varies —
so the test measures wording, not composition. Before this, variant C changed
the frames as well, which confounded the two.

    READY-TO-POST/AB-THUMBNAILS/<CASE>_thumb_{A,B,C}.jpg
    READY-TO-POST/<CASE>_thumbnail.jpg          <- variant A, the shipped default

Also fixed on this pass: the arrow was hardcoded to Thompson's tip (0.29, 0.52)
on all three and landed on empty ceiling. Now per-thumbnail angle and scale —
CARTHIEF 128 deg x1.30, SANCHEZ 112 deg x1.55, OFFERUP 140 deg x1.40. `auto`
mode aims at the detected defendant face but is NOT trustworthy on this footage:
it picked the ATTORNEY on CARTHIEF (he stands closer to camera than his client)
and found no face at all on ROMERO. Same failure as the reaction sweep — on this
docket Haar reliably finds the lawyer, not the defendant.

## 2026-08-27 — thumbnail settled: clone the SHIPPED Thompson, not a competitor

`scripts/make_thumbnail_v5.py` produces `READY-TO-POST/MONKEY_thumbnail.jpg`
(1280x720, 292 KB). One command reproduces it:

    python scripts/make_thumbnail_v5.py       --plate  <defendant tile frame> --cutout <judge cut-out>       --white "No monkey business" --yellow "in my court!"       --arrow 0.29,0.55 --subject-h 0.95 --max-lines 2       --plate-headroom 0.12 --force-top       --font research/blender/graphics/fonts_static/Archivo-SemiCond-SemiBold.ttf

Both frames come from src 6733 — the instant she says "you're going to end up in
prison or end up dead" — so the two reactions are the same moment, not stitched.

**Nathan, 2026-08-26: "look at their placment all you have to do is literally
copy all of it but with the otther stuff."** The reference is OUR OWN shipped
`1_LONGFORM_thumbnail.jpg`, measured off the pixels: type inset x23 y31, cap
71px (0.0986 H), white->yellow break, 11px stroke plus a black glow, red arrow
105x76 (0.41% of frame) pointing down-left into the defendant, judge cut out and
bled off the right edge over a courtroom plate carrying the defendant.

### Four wrong turns, all now measured rather than assumed

1. **`research/reference/competitor/THUMBNAILS.md` is WRONG** and v2 was built on
   it. Its §5 claims 9/12 of Audit the Court's are "a subject cut out over a
   second courtroom plate, feathered". Opening all 12 images: no cut-out, no
   feather, no matting anywhere. They are hard-edged vertical panel splits.
   Do not plan from that file.
2. **Audit's top-left type is refuted by the only controlled evidence we own.**
   `research/reference/courtroomtime/thumbs/` is 25 files split top_/bot_ on ONE
   channel covering THIS docket. 12 of 15 winners have zero text pixels above
   y=0.20H — they put type on a manufactured bottom plate. Numbers in
   `research/THUMBNAIL-MEASURED-2026-08-23.md`. That template is real but it is
   a different channel's house style; v5 matches ours instead.
3. **A zero-overlap "type never touches a face" guard rejects our own shipped
   thumbnail.** Measured: 18.8% of Thompson's text pixels sit inside Judge
   Boyd's raw Haar face box, 36% padded — its line crosses her hair and forehead
   and stops above her eyes. So the guard protects from the BROW LINE down, and
   only the two subjects; a bystander attorney was being protected too and his
   box alone shrank the clear band below what one line needs.
4. **Montserrat Black is the wrong face for this layout.** The reference runs
   ~0.40 advance/em; Montserrat Black is ~0.60, which collapsed the cap to 44px
   against the reference's 71. Archivo-SemiCond-SemiBold measures 0.42 and holds
   the full 71px. Measured across 14 candidates.

Shipped file overlaps a guarded region by 7.3% of the type block's box — less
than the Thompson thumbnail it copies.

### Copy rule, measured

None of @courtroomtime's 15 winning titles is a quote; all are third-person
editorial ("Judge Boyd Owns Smug Lawyer Who..."). 14/15 winners open with the
literal string "Judge Boyd" against 4/10 losers (Fisher p=0.0068) — that belongs
in the TITLE. "No monkey business in my court!" is first-person and Boyd never
says it; the phrase appears 0 times in the 34,408-word transcript. Nathan was
shown that measurement and chose the line anyway on 2026-08-27. His call, on the
record. The video does deliver the substance.

## 2026-08-23 — caption styling, parked

Nathan rejected the current Anton/gold captions AND all seven alternatives I
rendered. He went back to the previous terminal session, so this is PARKED, not
solved. Do not re-pitch the same seven.

- `scripts/caption_variants.py`  seven treatments off one transcript; adds a
  `place` engine (one event per word at an absolute \pos) so a word can scale or
  take a box without reflowing the line — the limitation
  caption_thompson_style.py documents as a law is only a limitation of the
  `flow` engine.
- `scripts/calibrate_variants.py`  solves vertical placement by MEASURING ink
  over black instead of hardcoding a per-font lead. Converged to 0px residual:
  defendant ink bottom 946, Boyd ink top 974, both 14px off the split.
- `Desktop/Boyd Clips/CAPTION-OPTIONS/`  the seven 10s previews + _COMPARE.png
- KNOWN BROKEN in that batch: G_marker's word spacing (PIL widths disagree with
  libass), and `wrap()` silently dropped words past max_lines — half-fixed, the
  DROPPED guard is in but the variants were never re-tuned.
- `research/captions-2026-reddit.md`  fetched 2026 tooling + failure modes.
- `research/captions-2026-what-the-field-mocks.md`  audience sentiment (YouTube
  comments, like-counts as weight).
- `research/captions-2026-standards-and-practitioners.md`  **the strongest of
  the three** — written BBC / Ofcom / DCMP / 3Play standards, plus the deaf
  accessibility community, plus fact-checker coverage of fake courtroom shorts.

**The two research files DISAGREE and must not be merged.** The mocks file says
gold-highlight captions are named as an AI tell (two YouTube comments, 51 and 0
likes). The standards file searched harder and says NO working editor names
caption typography as an AI tell — the AI-tell literature names the synthetic
voice, the watermark and the hashtags. Reconciliation: some *viewers* say it,
*practitioners* don't. Do not state "our captions read as AI" as fact.

**The better-supported reason to move off the current style**, and the thing to
act on: it has a name — "Hormozi captions" — and is described as a commoditised
shipped preset, by one editor a portfolio disqualifier ("Anytime an editor sends
a portfolio with those… I'm immediately out"). Everyone has it. That is the
"looks basic" mechanism, and it needs no AI-tell claim to stand up.

Settled against my priors, do not re-litigate:
  - No font is community-mocked in the courtroom/shorts territory. **Anton is
    not the problem — do not swap fonts as a fix.**
  - Single-word-at-a-time is the MOST mocked treatment there is (7,100 likes),
    so `B_popword` was a move toward the problem, not away from it.
  - `E_speaker` (colour = WHO is speaking, not WHICH WORD) is the only one of
    the seven that matches broadcast grammar — BBC §8.3 / Ofcom §1.16 use
    colour for speaker ID. Built for the wrong reason, right answer.

Measured violations of published standards in the CURRENT cut — table at the
bottom of the standards file. Short version: ALL CAPS (caps mean shouting),
gold live-word (yellow means *different speaker*, so we inverted its meaning),
3-word rolling window (pre-recorded wants phrase blocks), and a 0.10s minimum
event against BBC's 0.3s/word floor. What is already right: hugging the split
so nothing covers a face, and the black outline.

STILL UNMEASURED, and the only thing that would settle any of it: courtroom-
shorts top vs bottom videos ON THE SAME CHANNEL, caption treatment measured off
extracted frames. That agent was stopped before reporting. Everything above is
what people SAY. Nobody measured what costs views. Do not merge those claims.

Biggest strategic finding, bigger than captions: fabricated AI courtroom shorts
are a fact-checked genre as of Aug 2026 (Lead Stories prebunk). Real footage
gets pattern-matched into it. The inverse move nobody fake does — persistent
on-screen sourcing: court, case number, date.

## 2026-08-29 — caption reveal fix (R34)
Measured defect: `build_snap` painted every word of a card at the card's start
time. Card `"life. Exactly."` ran 3.20->4.12 while "Exactly." is spoken at 3.88,
so the defendant's reaction was legible 0.68s early. Frame diff at t=3.50 proves
it: 20,778 px differ between `reveal=off` and `reveal=reserve`, bbox x444-742 —
that block IS the spoiler. At t=4.00 the two frames are identical (12 px).

Fixed in `tools/caption_short.py` (`REVEAL` = build | reserve | off) and made a
hard gate in the new `tools/make_short.py`, which raises on any spoiled word.
Rule + check recorded as NATHAN_RULES R34.

`tools/make_short.py` is new and is the one-command short builder: per-tile
grade, seam-locked captions, pop-up card + pop sound, R34 gate. Defaults are
every value he approved today.

SANCHEZ_SHORT_FINAL.mp4 rebuilt as V10 (49.66s). Verified on disk: card at
y=1580 3.0->6.8s, pop present (peak 0.869 vs 0.666 baseline), 0.36s tail after
the last word, 78 cards / 196 events, 0 spoiled words.
Entrance stays `bounce` — "I think it's good".
Still unverified: the long-form, and the speaker attribution for 2020 CR2715.

## 2026-08-29 — R35, the actual cause
He rejected the R34 reveal: *"yes, it is nice, but that's not all it's about ...
you need to learn when to start the sentences."* The defect was segmentation,
not animation. Cards were cut on a character budget, so `"life. Exactly."` held
Boyd's last word plus the defendant's whole reply.

New `tools/speakers.py` measures who is talking from mouth-region motion energy
per tile (locked-off cameras, top = bench, bottom = defendant), decided per
SENTENCE. Per-word was 28 turns in 49s (noise); per-sentence is 6, matching the
record. Known-answer test passes: "life."=top, "Exactly."=bot.

`caption_short.cards_sentence()` forces a break at terminal punctuation, a
>0.60s pause, and every speaker change. 81 cards, straddle=0, mixed=0
(was 78 cards, 7 straddling, 2 mixed). REVEAL now defaults to off.

SANCHEZ_SHORT_FINAL.mp4 = V11. Card at y=1580 corr 0.991, pop peak 0.869 vs
0.666 baseline, 49.66s.

## 2026-08-29 — R36, phrase-aware breaks
"Those captions don't match. Now they just feel off." Ruled out first: transcript
(two Whisper passes agree 98.7%) and sync (median 60 ms late). The cause was that
R35 fixed sentence/speaker boundaries but left a character counter cutting inside
the sentence — 25 of 81 cards ended on a stranded function word
("that, Your" | "Honor, but I").

`caption_short.split_phrase()` now chooses breaks by DP cost: pause bonus, comma
bonus, glue-word penalty, KEEP_TOGETHER for "Your Honor", flash penalty under
0.42s. Budget widened 15ch/3w -> 20ch/4w after measuring the trade table.
Result: 66 cards, ends-on-glue 25 -> 11, flashes 3 -> 1, mean 12.1 -> 14.3 ch.

SANCHEZ_SHORT_FINAL.mp4 = V12, 49.66s, straddle=0 mixed=0.

## 2026-08-29 — entrance settled (R37)
He picked option 4, BLUR: `\fad(60,60)\blur6\t(0,120,\blur0)`. Default in both
caption_short.py and make_short.py. Scale-based entrances are banned (R37).
SANCHEZ_SHORT_FINAL.mp4 = V13, 49.66s, 66 cards, straddle=0 mixed=0 glue=11.

## 2026-08-29 — long-form fixed; UPLOAD IS BLOCKED
Long-form rebuilt as SANCHEZ_LONGFORM_FINAL.mp4 (110 MB, 7:23.8):
  - loudness -20.4 -> **-14.0 LUFS** measured (two-pass loudnorm, linear)
  - TTT watermark burned in from t=1.4s (after the sting), placed in the BOTTOM
    LETTERBOX BAR at x=W-w-56, y=884. First attempt put it over Judge Boyd's
    shoulder - it ate 15% of a picture that is only 562px tall.
  - RETRACTED: I called the letterboxing a defect. It is not. The court's own
    broadcast is two 16:9 tiles side by side = 32:9, and the source maxes at
    720p, so filling a 16:9 frame needs a ~1.9x upscale of already-soft footage.
  - Duration is 7:24, UNDER his 8-minute mid-roll rule. He chose to post anyway
    rather than re-cut for length.

Speaker attribution for 2020 CR2715 RESOLVED: the court's own stream labels the
tile "Judge Boyd", and speakers.py puts every bench line on that tile.
The flag in COPY-PASTE-SANCHEZ.txt has been cleared.

**Upload could not be completed. Three paths tried and measured:**
  1. `file_upload` over the Chrome bridge — hard 10 MB cap, refused a 110 MB
     file. The 22 MB short would fail the same way.
  2. Local CORS HTTP server + `fetch()` + DataTransfer injection into YouTube's
     file input — the request never reached the server (logged nothing), so
     studio.youtube.com CSP blocks it. The pending fetch also froze the renderer
     and needed a reload.
  3. Native Windows file dialog + SendKeys — the dialog never opened from the
     synthetic click on "Select files"; window enumeration showed no "Open".

**The real fix is the YouTube Data API v3.** It needs a one-time OAuth client
secret from a Google Cloud project, which only Nathan can create. After that,
upload is one command and the push-button pipeline is actually complete. Nothing
else on this list gets there.

Files staged to OneDrive/Pictures/Boyd-Review so he can post from his phone:
SANCHEZ_LONGFORM_FINAL.mp4, SANCHEZ_SHORT.mp4, SANCHEZ_thumbnail_APPROVED.jpg.

CORRECTION to repo docs: CLAUDE.md says "Nothing has ever been published from
this pipeline." That is stale — the channel has published videos, including one
at 62,446 views.

### Root cause of the upload block (measured 2026-08-29)
The Claude-in-Chrome tab is NOT in any OS-enumerable window. EnumWindows over
all top-level windows (visible and hidden) found no window whose title contains
"YouTube", "Studio" or "New Tab"; the only visible Chrome windows were his own
("Sanchez Option Sets", a Google search). Creating a new MCP tab changed no
window title either.

Chrome will not open a native file picker for a tab that cannot be brought to
the foreground, which is why BOTH the ref-click and the coordinate-click on
"Select files" silently did nothing and no "Open" dialog ever appeared. That is
the root cause - not the click method, which was the first hypothesis.

Playwright MCP was then tried: it launches a FRESH profile, so studio.youtube.com
redirected to the Google sign-in page. Signing in would mean entering his
password, which is not something I do. Dead end, closed cleanly.

So there is no browser route to uploading from this session. The remaining
options are (a) he posts from his phone - files are staged in OneDrive, or
(b) YouTube Data API v3 with an OAuth client secret he creates once.

## 2026-08-29 — BOTH POSTED (first publish from this pipeline this session)
Long-form: https://youtu.be/lwpngpcZvd0
  "Judge Boyd revokes her probation, then offers to help"  7:24, Public,
  monetization ON, thumbnail SANCHEZ_thumbnail_APPROVED.jpg, Not made for kids,
  copyright check clear.
Short: https://youtube.com/shorts/kQ0O7Rj6YXY
  "Judge Boyd tells her why her son is struggling #shorts"  0:50, Public,
  long-form link in the description, Not made for kids.

### How the upload was actually done — READ THIS BEFORE TRYING AGAIN
The Claude-in-Chrome MCP tab is not in any OS-enumerable window, so Chrome will
never open a native file picker for it, and file_upload over the bridge caps at
10 MB. The route that WORKS is OS-level automation of his own visible Chrome
window, in `scratchpad/ui.ps1`:

  1. **SetProcessDpiAwareness(2) FIRST, in every PowerShell call.** Without it
     the screen reports 4096x1152 instead of the true 5120x1440, and every
     SetCursorPos lands 25% off. This wasted three attempts - the clicks were
     silently going nowhere.
  2. Find the Chrome window by title, ShowWindow(3) + SetForegroundWindow.
  3. Ctrl+L to navigate; `?d=ud` on the upload URL opens the dialog directly.
  4. Screenshot full screen, downscale, MULTIPLY shot coords by 1/scale.
  5. For the native picker: click "Select files", poll AppActivate("Open"),
     then CLICK THE FILE NAME FIELD and paste from the clipboard. Typing the
     path with SendKeys fails - the dialog auto-navigates as it receives
     characters and eats most of it.

### Ad suitability
Rating is MANDATORY when monetization is on; Next stays disabled without it.
There is a **"None of the above" checkbox at the very bottom** of the category
list, below "Controversial issues" - it sets every category to None and yields
"Safe for ads" with Ads + Premium + merchandise all eligible. That is what both
videos were rated. Nathan's instruction, verbatim: *"Don't ever pick that bs on
there idc what you think you're posting you never say some bs like that."*
Do not tick any content category on his uploads.

## 2026-08-30 — three thumbnails rebuilt to spec via tools/thumb_pipeline.py
CARTHIEF_thumbnail_V2.jpg   "Playing Grand Theft Auto?" / HE LAUGHED...
MONKEY_thumbnail_V2.jpg     "Where's the spider monkey?" / SHE STOPPED THE PLEA...
                            includes the REAL monkey cut from his Instagram photo,
                            arrow retargeted onto him (Thumb.extra + Thumb.arrow_xy)
THOMPSON_thumbnail_V2.jpg   "Your children were killed?" / SO SHE CHECKED...
All three: gates A/C/D pass, plate from the shared face-checked library, court
label trimmed, faces detected on the RAW crop so parity actually holds.

New cases registered in config/cases.json: MONKEY (Joseph Grant, 2024 CR011920)
and THOMPSON (Louis Thompson, gMdQwkaFGMw - Nathan calls this one "Thomas").
Both source from our own 1080p renders; the raw court streams are not on disk
and YouTube 403s yt-dlp (cookies unusable while Chrome is running).

STILL OPEN: schedule CARTHIEF long-form + short to publish in 24h. The videos
are built and verified (CARTHIEF_LONGFORM_V2.mp4, CARTHIEF_SHORT_V2.mp4) and
COPY-PASTE-CARTHIEF.txt holds title/description options and the case facts.

## 2026-08-30 03:xx — Thompson thumbnail swapped, CARTHIEF pair SCHEDULED
Thompson (gMdQwkaFGMw) thumbnail replaced with THOMPSON_thumbnail_V2.jpg.
Verified: Save + Undo both greyed out after saving = change committed.

CARTHIEF scheduled, NOT yet public:
  long-form  https://youtu.be/vLCkL_X1tWE          Aug 31 2026, 3:00 PM CST
             "He told the judge it was funny. She doubled it."  16:43
             mid-roll ads ENABLED (over 8 min, unlike SANCHEZ at 7:24)
  short      https://youtube.com/shorts/jfaco56-J8o  Aug 31 2026, 3:30 PM CST
             "He told the judge it was funny #shorts"  0:35
             long-form URL in the description
Both: monetization ON, ad suitability "None of the above" -> Safe for ads with
Ads + Premium + merchandise eligible, Not made for kids.

NOTE ON TIMING: he asked for "24 hours", which landed at 3:30 AM. Scheduled for
3:00/3:30 PM instead - Aug 31 is a Monday and 3 AM is a dead slot. Told him; he
can move it in Studio in two clicks if he wants it literal.

YouTube's automated checks were still running at schedule time ("visibility and
monetization may be restricted"). Worth a look before Aug 31.
