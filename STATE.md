# Boyd Clips — current state

## START HERE — 2026-08-17 ~15:50, pipeline audit

**The canonical cross-session doc now lives in the "texas trial tracker"
Claude project as `claude/PIPELINE.md`.** Read it alongside this file; this
one stays the running log.

### The automated path was not producing the approved output

The three approved clips were built by one-off scripts in `scripts/`.
`pipeline.produce()` did something materially different and worse, so
switching on daily auto-posting would have shipped a broken product every day.
Five defects found and fixed in the pipeline itself, each with tests:

1. **Long-forms were never trimmed.** `detect_silences`/`plan_silence_trim`
   existed and only `scripts/build_thompson_longform.py` called them. The daily
   path concatenated raw sitting windows — 21.4% dead air measured on its
   output, one 75s run, opening on 4.8s of nothing, against CONTENT_SPEC §2.
   Now trimmed in `produce()` with the constants the Thompson rebuild was
   verified against.
2. **`max_duration_s: 1200` was enforced nowhere** (flagged in the old Retracted
   §3 and left open). Both bounds now checked before the encode; over the cap it
   cuts mid-piece rather than dropping the last piece, which is what loses the
   ruling.
3. **Packaging ran before the sittings merge** — titles and descriptions
   described the first sitting only. Now runs after, against the full span.
   This was the root cause behind Thompson's truncated description and it
   affects all 20 split cases.
4. **Nothing wrote `thumbnail_quote.jpg`**, which `publish.py` attaches — every
   upload would have used a YouTube-picked frame. `make_thumbnail.py` is now
   wired in, plus a `thumbnail_quote_yellow` field (schema + prompt v2.1.0) so
   the white/yellow split in PACKAGING.md rule 4 is a model judgement validated
   as a verbatim suffix, not a word-count guess.
5. **The pipeline started happily while paused.** `run_daily` now refuses when
   `state/paused.flag` exists, instead of being suspended mid-download.

`python -m pytest tests -q` → **62 passed** (was 54). One new test locks
CONTENT_SPEC §2's stated dead-air threshold to the config value so the prose
and the behaviour cannot drift apart again.

### Publishing: "assisted mode" is a trap, not a workaround

Verified live against Google's docs. An unaudited API project does not upload
"as private so you can flip it" — the video is **locked private, cannot be
appealed, and cannot be made public by hand**
(support.google.com/youtube/answer/7300965). And `publish_pair`'s duplicate
guard then refuses to re-upload it, so one run in `assisted` or `auto`
permanently spends the case. Added `publish.youtube.api_audited: false`;
`publish_pair` hard-refuses while it is false.

### Ledger reality

`publications` = 0 rows, `ledger` = 0 rows. The documented promotion gate for
`auto` is 30 consecutive approvals with zero safety rejects. Also: git commit
`a165a41` is titled "First clip published" — that message is wrong, it added
the publish machinery. The DB is authoritative.

---

## Previous handoff, 2026-08-17 ~10:30

**Thompson is built and approved. It is NOT posted.** Nathan said "go ahead and
post" and is logged into YouTube Studio as Texas Trial Tracker (2,881 subs).

**The one blocker:** the browser bridge caps file transfers at **10 MB**, so the
124 MB long-form and the 11 MB short cannot be pushed through it, and "Select
files" opens a native OS dialog that cannot be driven either. Nathan has to pick
the file; everything after that (title, description, thumbnail at 0.2 MB, Not
Made for Kids, publish) can be done in the browser. He last said **"cant find
it"** — files were therefore staged at:

    C:\Users\natha\OneDrive\Desktop\Boyd Clips\READY-TO-POST\
      1_LONGFORM_Thompson.mp4    124 MB   10:58
      1_LONGFORM_thumbnail.jpg
      2_SHORT_Thompson.mp4        11 MB   0:33
      COPY-PASTE.txt             titles + descriptions

The YouTube API is NOT an alternative: no OAuth client on disk, and verified
live against Google's docs — "All videos uploaded via the videos.insert
endpoint from unverified API projects created after 28 July 2020 will be
restricted to private viewing mode."

**Order is load-bearing:** long-form first, then paste its URL into the short's
description before the short goes up.

**Open decision, not yet made.** A channel found late — `@Courtroom`, top videos
20M/20M/14M/12M/9.1M — uses a template 6x bigger than Audit the Court's best:
two-panel hard split, white divider 5-7px at exactly x=0.500, faces 0.36-0.56 of
frame height, and **no text, no logo, no arrow** in 10 of 10. Nathan was offered
either posting the approved thumbnail as-is or a ten-minute @Courtroom-style
variant, and had not answered.

**Retracted:** I told Nathan the data supported judge-on-the-right. It does not.
Measured across 60 thumbnails, robed judges sit LEFT 4 / RIGHT 2. The "7/12"
figure was *primary subject* on the right, not judges. His preference is fine as
a preference; it was not evidence.

**Measured as NOISE — present equally in winners and losers:** face size (hi
median 0.35 vs lo 0.37), the split composite itself, the yellow/white
sentence-case headline, and the red arrow (4/6 winners, 4/4 losers). What did
survive: no high-view thumbnail in 60 has a stroked or glowing cutout edge — the
only one is a 10k flop.

---


Updated 2026-08-16. Every claim here was produced by a command run on this
machine, and the command is named. Where something was not measured, it says so.

**Read this first, not `POST-IT-YOURSELF.md`.** That file is from 2026-08-14 and
three of its central claims turned out to be wrong. See "Retracted" at the
bottom — they are kept there deliberately, because a stale hand-off doc that
reads as authoritative is what caused the wrong work to be planned.

---

## Where we actually are

Nothing is published. Nothing has ever been published from this pipeline —
`publications` is empty.

| case | long-form | short | state |
|---|---|---|---|
| Thompson `JgvW7oCQxuI:6698` | **10:56 ✅ `longform_v2.mp4`** | **0:33 ✅ v3, speaker-anchored** | ready — copy in `UPLOAD.txt` |
| Rodriguez `mvGmUbuS0sU:1358` | 11:01 ✅ complete | **0:57 ✅ re-rendered** | ready |
| Blackburn `4zkUTUavW4I:116` | 33:56 ✅ complete | 0:58 ⚠️ | long-form ready, **short not postable** |

### 2026-08-17 — the long-form was never trimmed, and the short was rebuilt

**Long-form.** `longform.mp4` was a straight concat of the two sitting windows.
Measured on the rendered file: **179.6s of silence in runs over 4 seconds
across its 838s — 21.4%**, including a 75s run and a 30s run, and it opened on
4.8s of nothing. CONTENT_SPEC §2 requires dead air over 4s removed and a cold
open on the case, so this was rendered against the spec, not to it.

`scripts/build_thompson_longform.py` rebuilds it: 824s of hearing → **656.3s
(10:56)** across 12 pieces. Verified on the output — **zero remaining runs over
4s**, opening silence 4.8s → 0.81s. Nothing reordered; no gap under 4s touched.
Framing changed to **no crop**: the old cut inherited `detect_content_crop`,
which is threshold-per-pixel and measures this source wrong (below).

**Short.** Rebuilt as `short_v3_*.mp4` — full-bleed 2-up with each tile cropped
to the half-canvas aspect and centred on its subject (zero black rows or
columns on any edge, measured), and captions that move to the speaker's half of
the frame via per-event ASS `MarginV` (88 events in Boyd's slot, 13 in the
defendant's). Speaker turns are hand-written in the script: the transcript holds
125 `>>` markers but only one falls inside these four beats.

**Caption motion — measured, same card, identical text.** Scaling one word
inside a line makes libass re-lay out the whole block: `pop_color` drifts 33px
left and 65px wide on every word. Colour-only drifts **0/0/0**. Renders exist
for `highlight`, `card_punch` and `pop_color`; the choice is Nathan's and is
open. An agent measuring what current top-performing shorts actually do was
still running when this was written.

**Two measurement traps, both mine, both now fixed in code:**

- `bbox` is max-based — one bright pixel keeps a whole row inside the box. A
  flag down the edge of Judge Boyd's tile kept 132 rows of pure black in her
  measured tile, which is what put a 152px black band across the bottom of the
  first v3 render. `_content_boxes` now uses row/column *mean* occupancy and the
  longest contiguous run. Both tiles then measure identically at 628x348 — they
  are NOT different shapes, which an earlier note here implied.
- `cropdetect` models black *bars*, not ink, and returns a negative width on
  text. Caption geometry is measured with `bbox` instead, via
  `scripts/caption_probe.py`.

**Caption sizing is now measured, not derived.** Rendered cap height =
**0.514 × ASS font_size** (identical for Arial Black and Anton). The shipped
74px font was 38px of visible letter against a 72px floor (BBC/EBU-TT-D
vertical 3.75%, cross-checked against W3C IMSC1.3). Now Anton at 140. At that
size Arial Black overflows the safe band at ~9 chars/line and Anton at ~13, and
Anton ships in `assets/fonts/`.

**Watermark had been silently absent from every render** since the brand folder
moved to `OneDrive\Desktop\Boyd Clips\boyd-brand\`. `_watermark_chain` degrades
to "no watermark" with only a log line. Now resolved from a candidate list.

**Unresolved conflict, needs Nathan.** `spec/LONGFORM-ANTIPATTERNS.md` §5 items
12–13 require a written script, chapters and legal exposition and treat a
lightly-trimmed feed as a failure. CONTENT_SPEC §2 defines the long-form as the
proceeding itself, uncut but for dead air. CONTENT_SPEC calls itself the format
contract and the antipatterns file calls itself one specialist's negative-space
output, so the contract was followed — but the two documents disagree and one
of them should be amended.

---

Both re-rendered free from stored beats and cached sources via
`scripts/rerender_short.py` — no Claude call, no re-download. Verified on both:
`>>` count 0, caption lines over 22 chars 0.

### Blackburn's short is not postable, and cropping cannot fix it

Sampled all four beats. The participants are small in **every** beat, not just
one. The backdrop fix worked — it is a real blurred fill now rather than black
— but the source for this docket is a 3-4 tile Zoom grid throughout, and
blur_pad scales the *whole grid* to 1080 wide, so each tile lands at roughly a
quarter of that. Nobody's face is legible at thumb distance.

This is not an unfixed bug. `detect_content_crop` correctly returns None here:
the layout alternates 51.3% full-bleed / 48.7% letterboxed, so any single crop
would push participants out of frame for half the clip. The framing code is
doing the right thing with material that does not suit the treatment.

**The fix is per-beat cropping.** Each beat has one speaker whose tile is known
and static within that beat, so each segment could crop to its own tile and
scale that to full width. `render_short` currently applies one `crop` to every
segment; `_concat_filter` already trims each segment separately, so the crop
would attach there. Not attempted yet — it is a real change to the filter
graph, and Blackburn is the weakest of the three cases anyway.

### Thompson: the short was misleading, not just badly framed

The shipped 53s short was Form B, cut entirely from sitting 1, and it ended on
the defendant's claim that his ex-wife, children, sister and nieces had been
murdered — with the claim unchallenged. Sitting 2 is where the court reports a
search found no record of any of it, he concedes he is "assuming", and Boyd
says "I don't believe it". Publishing the fragment would have left an
unverified quintuple-murder claim standing as fact about a named person.

Re-cut as Form A across both sittings, 34.55s, chronological, nothing
rearranged. `scripts/build_thompson_formA.py` holds the beats and the in/out
points; it refuses to render if the beats fall outside 25-59s or out of order.

The original analysis was not wrong to choose Form B — it only ever saw
sitting 1, where there genuinely is no turn. Its own note says a four-beat
build "would require either an inferior hook or reordering material — which is
prohibited." That reasoning was correct on the evidence it had. **Merging the
sittings therefore changes shortability, not just duration**, and the 20 split
cases in the bank all need re-scoring for the same reason.

### Packaging is written before the sittings merge

`produce()` runs the packaging step before `case_windows()`, so titles and
descriptions describe the first sitting only. Thompson's description stopped at
"so the claim could be checked" — no mention that nothing was found or that he
got five years. Corrected copy is hand-written in the clip folder as
`UPLOAD.txt`; the stale copy is still in `manifest.json` and is listed there
under "DO NOT USE". **Real fix: move packaging after the merge** so this does
not recur on the other 19 split cases.

### Caption artifacts

`>>` speaker-change markers and bracketed sound cues (`[clears throat]`) were
rendering on screen — both appeared in shipped output. `strip_caption_artifact`
now removes them before grouping, so line wrapping is measured against the text
that actually appears. Verified: 0 occurrences, 0 lines over 22 chars.

All three pass the safety gate. Titles, descriptions and disclaimers are
written and reviewed. House-style quote thumbnails now exist for all three as
`thumbnail_quote.jpg`.

---

## What was broken, and what fixed it

Four defects, all found on 2026-08-15 by looking at the rendered frames rather
than at the logs. Every one of them rendered "successfully" and wrote a valid
mp4 — which is why the logs said the run was fine.

### 1. Long-forms stopped at the recess

A hearing that is recessed and recalled later in the docket is one case heard
in two sittings. The segmenter writes two rows; the pipeline rendered the row it
was handed. Thompson (cause 2022 CR0273) was published-ready as `6698-6958`
(260s) when the ruling is in the second sitting at `8279-8843` — so the video
ended on *"have a seat and we'll see what's going on with that"* and never
showed the outcome.

**20 cases in the bank are split this way.** Query that finds them:

```sql
SELECT video_id, cause_number, COUNT(*) n FROM cases
WHERE cause_number IS NOT NULL AND cause_number != 'unknown'
GROUP BY video_id, cause_number HAVING n > 1;
```

Fixed by `Store.case_windows()` (state.py), which groups by cause number, and by
`pipeline.produce()` passing every window to `render_longform` — which already
accepted a segment list, so no render change was needed. Cases whose cause
number never parsed fall back to the single window; grouping every "unknown" in
a docket would merge strangers.

### 2. `cropdetect` reported "no letterbox" on letterboxed footage

It ran with `reset=0`, which unions every frame it sees. On `JgvW7oCQxuI:6698`,
259 of 265 sampled frames agree on `crop=1920:712:0:270` — but 5 full-frame
outliers widened the union to the whole frame, so detection returned nothing and
the short rendered with the courtroom at **17% of the canvas**.

Now sampled at 1 fps across the whole clip with `reset=1` and reduced by mode,
with a 60% agreement floor: below that the layout genuinely changes mid-clip and
cropping would push participants out of frame, so it stays uncropped.

### 3. The "blurred fill" was rendering as black

The backdrop is made by scaling the frame to fill 9:16 and centre-cropping —
which takes a narrow vertical column out of a 16:9 frame. When that frame has
its own black bars, the column is mostly bar, so CONTENT_SPEC §4's blurred fill
came out flat black with a smear through it.

`render_short` now takes a separate `bg_crop`. A backdrop may use a crop the
foreground cannot: clipping a participant out of a blurred, darkened backdrop
loses nothing, so `bg_crop` is accepted at 25% agreement and full-frame samples
are dropped before the vote rather than after it. `4zkUTUavW4I:116` alternates
51.3% full-bleed screen-share / 48.7% letterboxed 2-up, so counting them
together elected "no crop" by three tenths of a percent.

### 4. Captions ran past the documented line limit

`_wrap` stopped opening new lines once it reached `max_lines` and let the final
line run unbounded. `KILLED? YES, INCLUDING MY` — 25 characters against a
documented 22-char limit — shipped in a rendered short.

Grouping is now done by the wrap the card will actually get, not by a
`max_chars * max_lines` character budget. Those are different constraints:
greedy wrapping fills line 1 to 22 and drops the remainder on line 2, so a
44-char budget routinely produced a 22/26 split. Verified: 0 lines over limit.

### 5. Thumbnails were never the house style

`publish.py` attaches `thumbnail_quote.jpg`; the pipeline only ever wrote a bare
frame grab called `thumbnail.jpg`. Nothing generated the file publish looked
for, so every upload would have gone out on whatever frame YouTube picked.
`scripts/make_thumbnail.py` existed and was simply never wired in. All three
now have one.

`python -m pytest tests -q` → **49 passed**.

---

## Uploading — read before planning any automation

**The YouTube API cannot post these publicly.** Google's own documentation on
`videos.insert`:

> "All videos uploaded via the videos.insert endpoint from unverified API
> projects created after 28 July 2020 will be restricted to private viewing
> mode."

Lifting it requires a compliance audit, which takes 2–4 weeks. So building the
OAuth client does not get a public video, and it is not the path to posting.

**Upload through YouTube Studio by hand**, long-form first, then paste its URL
into the short's description before uploading the short. `publish.py` enforces
that order and it matters — the short exists to route traffic to the long-form,
so backwards means the short points at nothing.

---

## Retracted from POST-IT-YOURSELF.md

1. *"All three long-forms and their shorts were rendered … Nothing left to
   render — tomorrow is upload only."* Wrong. The shorts were unwatchable and
   Thompson's long-form was missing its ruling. The renders completed; nobody
   looked at the frames.
2. *"YouTube upload is not configured … Automatic publishing therefore cannot
   work yet."* True but misleading — it framed OAuth as the blocker. Configuring
   it would still not have produced a public video.
3. *"Measured: it rendered the full 33.9 minutes … The `max_duration_s: 1200`
   cap did not truncate it."* Accurate as stated, but the cap is in fact
   enforced nowhere, so it is not evidence the cap works. Not yet fixed.

---

## Next

1. Finish the Thompson re-render (running), then re-render the Rodriguez and
   Blackburn shorts for the caption and backdrop fixes.
2. Look at the output frames before calling any of it done.
3. Decide which case posts first, and public vs unlisted. Nathan's call.
4. Not started: the `max_duration_s` cap is unenforced; the 20 split cases in
   the bank still have stale single-window rows.

### Known, measured, not yet fixed: the multi-sitting download over-fetches

A merged case downloads one contiguous span from the first sitting to the last,
then uses only the sittings inside it. Measured across all 20 split cases:
**904 minutes fetched for 400 minutes used, 2.3x overall**, worst case
`k6O8Ev7XZjU` / 2025CR010725 at **18.3x** — 68.8 minutes downloaded to use 3.8.

This is waste, not breakage: the rendered video is correct either way, and
download is free. Left alone deliberately rather than restructured mid-run.
The fix is to fetch each window separately and concat them before rendering —
`render_longform` already accepts a segment list, so the change is in
`pipeline.produce()` and `render.download_section()`, not the filter graph.

### Operational trap that cost a day

The tray switch had been left **RED (paused)** since 2026-08-14 13:14. It
suspends boyd-clips processes with `NtSuspendProcess` rather than killing them,
so the 2026-08-15 re-render started, downloaded 99.75 MB, and was frozen
mid-download — leaving a process that looked alive, a `.part` file that never
grew, and no error anywhere in the log. Nothing distinguishes "suspended" from
"slow" in the log output.

**Check `state/paused.flag` before diagnosing any stalled run.** Resume with
`powershell -File tools/boyd-toggle.ps1`. Worth making the pipeline refuse to
start, or at least warn loudly, while that flag is present.
