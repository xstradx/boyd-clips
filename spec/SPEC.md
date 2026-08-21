# THE SPEC

**This file governs. If anything else in the repo disagrees with it, this wins
and the other file is wrong.**

Written 2026-08-18 to replace a set of documents that contradicted each other in
six places and had the build following whichever one was read last. Superseded
files are listed at the bottom.

---

## 1. THE PRODUCT

One defendant. Every appearance of theirs we have. Cut together in order.

    LONG-FORM   one defendant's story across all their hearings
    SHORT       the single best moment from that long-form, hook first

Not a compilation of different people. Not one isolated hearing. **A person, and
what happened to them across the weeks.**

This is the format because it is the only one that is simultaneously: what the
channel owner wants, what the archive uniquely supports (238 defendants scored,
and the arcs are already sitting there), and what the rival channel's numbers
back — 5 of @courtroomtime's top 10 are return appearances.

**Two kinds of "again", and both count:**

- *Same docket, recalled later the same day.* Already handled — `Store.case_windows`
  merges recessed-and-recalled sittings.
- *A different day entirely.* Robert Castillo has 9 appearances across 6 dockets;
  Eric Mason 4 across 3, spanning May to August. This is the new capability and
  it is the point of the format.

A defendant with only one appearance is still publishable. It is just a
one-chapter story rather than a five-chapter one.

---

## 2. WHAT MAKES A CLIP GOLD

Derived by reading ~65,000 words of transcript from the top 8 videos of
@courtroomtime (204k–891k views) against their bottom 6 (388–1,700). They clip
this same judge — 318 of their 322 dated titles name her.

Counts below are "videos containing this beat", winners of 8 / losers of 6.

| Beat | W | L | What it looks like |
|---|---|---|---|
| **Someone disputes Boyd** | 8 | 1 | ≥3 alternating turns where the defendant or counsel pushes back |
| **Boyd is sarcastic or mocking** | 8 | 1 | "guess what" (21× in winners, 1× in losers), "Mhm", "Are you doing this for the YouTube?" |
| **Boyd produces a receipt** | 6 | 0 | She quotes a document back at them: *"they found it in your purse. That's what the police report says, 'cause it says right here"* |
| **Consequence lands on camera** | 6 | 2 | *"Deputy Laura, could you do me a favor — could you place the handcuffs on him please."* |
| **Boyd riffs** | 5 | 0 | An extended vivid hypothetical — the grocery store, KFC, the middle of a movie |
| Defendant cries or begs | 6 | 2 | |
| A third party is the lever | 6 | 2 | A mother, a girlfriend, an officer called up |
| ~~Boyd raises her voice~~ | **1** | 0 | **NOISE. Do not build for this.** |

### The two findings that matter most

**An antagonist is the whole thing — 8/8 vs 1/6.** Their worst video has tears,
a remand and a life sentence, and it died, because the defendant *agreed with
everything*. Boyd stayed gentle and there was no video. **Compliance kills a
clip, not low stakes.**

**She does not yell.** The channel's whole reputation is that she does; across
all eight winners it happens once. Her register is flat, unhurried and
declarative, then a rhetorical hammer. A loudness detector would find nothing.

### The mechanism, from Nathan 2026-08-20

The table above says an antagonist is the whole thing but never says what the
antagonism looks like. It looks like an excuse. His words, kept verbatim:

> "it's also when people have ridiculous excuses"

> "she goes off on people and really calls people out and people give up their
> right to stay silent and they have to talk"

> "it's dead serious but funny to us or like oh damn, or when she scolds a
> person for doing something bad so also it's when it's harsh too"

> "sometimes judge Boyd warns them then throws them in the slammer"

**It is a setup and a punchline.** Someone offers an excuse that sounds
reasonable to them and ridiculous to everyone else. She demolishes it, flat and
personal, in her own words. Two flavours, one shape - funny, or harsh. Both are
"she went there".

Four things follow, and each one changed how the search works:

1. **Funny to the viewer, never to the room.** Nobody in there is laughing;
   someone is facing prison. The contrast IS the entertainment.
2. **She puts herself in it.** Her nose, her mind, her walk to work in heels,
   her hair getting wet, riding the VIA bus as a new attorney. First person and
   second person together, at length. Procedural speech has neither, so this is
   the cleanest single discriminator we have.
3. **The excuse can come from anyone** - "lawyer mother anything". What matters
   is that she answers it at length instead of moving on. When she lets it go,
   there is no clip.
4. **Warning then consequence is its own arc.** She flags it herself - "you
   were previously here before", "it appears that you have learned nothing" -
   so it is findable without auditing every appearance a defendant ever made.

Search the SETUP, not the punchline. Scoring her language for unusualness found
the good moments by accident and could not find more of them.

### Two dead ends - do not retry

- **`[laughter]` markers.** 550 of them across 146 of 352 dockets, and they
  find staff banter between cases - Batman, Grease 2, the Cowboys. The rival
  channel used 4 of 462 such bits. Nathan: *"people in the court aren't
  laughing"*. Wrong signal entirely.
- **Ranking whole cases.** A case-level score averages one devastating exchange
  against fifteen procedural minutes, so long dull hearings outrank the moment
  worth cutting. The unit is the exchange.

- **Mining the rival's clips for her tells.** Their published spans were aligned
  onto our own dockets (`scripts/align_clips.py`, 139 of 148 matched) and scored
  by lift against the speech nobody clipped - a real contrast set, so boilerplate
  should have cancelled. It returned case-specific nouns from a single hearing
  and probation-condition boilerplate. The cause is structural and checked:
  **their catalogue contains zero videos under three minutes** - 280 run 30-60
  minutes and 157 run over an hour. A compilation includes whole cases, so
  "published" means "this case was chosen", never "this line landed", and their
  editors never had to cut to a punchline.

  It also graded the hand-written phrases as weak - "here's the thing" 1.62,
  "you know what" 1.65, "guess what" 2.51, "let me tell you" absent from clipped
  spans entirely - which is evidence about the contrast set, not about the
  phrases.

  Consequence: **moment-level labels cannot be obtained from that channel at
  all.** They exist only in Nathan's ratings (`scripts/review_moments.py`).
  Their alignment remains useful for which CASES are worth using, which is a
  different question.

- **"We can go off the record" as a locator.** Reading the two biggest rival
  clips, both payloads began right after she said it, and the ramen-noodle line
  does too - she finishes the legal formalities, goes off the record, then talks
  bluntly. It looked like a structural boundary rather than a keyword, which
  would have beaten any phrase list.

  It does not survive measurement. The marker is common and real - 2,546
  occurrences across 692 of 880 dockets - but candidates cluster after it barely
  above chance: 1.27x at a 45-second window, 1.06x at 240. The top-60 figures
  range 1.30x to 2.06x across windows on samples of 8 to 18, which is noise.

  **The test is also circular and should be redone**, because it validated the
  marker against this scorer's own output rather than against known-good
  moments. It shows the marker disagrees with the scorer; it cannot show whether
  it predicts a good clip. That question needs labels, and the only labels are
  Nathan's.

### The archive splits in two, July 2025

The court changed how it captions around July 2025. Before that the captions are
raw machine transcription with no speaker changes marked; after, nearly all
carry `>>` turn markers.

    2022-03 .. 2025-06     0 transcripts with markers,  589 without
    2025-07 .. 2026-08   291 with markers,                9 without

`find_wentthere.py` splits speech into turns on those markers, so **it works on
291 dockets and is blind to 589** - the preceding 3.3 years. The ramen-noodle
line sits in that blind spot, which is why a raw text search found it and the
finder never could.

**Pause-based segmentation was tried and does not work.** Tested against the 291
marker-bearing transcripts as ground truth, the best threshold scores F1 0.445 -
55.8% recall at 37.0% precision at 1.0s, and every other threshold is worse.
She pauses mid-sentence constantly and speakers hand off without pausing, so
silence is not a speaker change. Do not retry it; use the labelled transcripts
to test any replacement.

What remains open for the older 589: score sliding windows of raw text rather
than turns, which is how the first moments miner worked and how the spearmint
riff was originally found. Less precise, but it does not need speaker
structure. They are also still searchable by plain text today.

Implementation: `scripts/find_wentthere.py`. Turn-level speaker attribution is
in `is_boyd()` - validated at 5/7 on known-good moments and 3/3 on known junk.
Precision at the top of the ranking is roughly 60%; the residual misses are
staff conversation, not garbage.

---

---

## 3. SELECTION

**One scorer.** The model reads the transcript and answers concrete questions
from §2. That is the whole system.

There were three overlapping scorers — an abstract 5-part rubric, a notoriety
ranker, and a keyword banger-scorer. They are gone. The reason is not tidiness:
each was fitted by hand against a handful of cases, none was validated against a
single published outcome, and the keyword one measured caption formatting. A
model reading the transcript already has the human-like judgement being
approximated; it was being asked the wrong questions.

Scoring lives in `prompts/score_cases.md`. Weights are in
`config/pipeline.yaml` under `analysis.rubric_weights`, and if you change one
you change it in both.

**Safety runs first and separately.** See `spec/SAFETY_RULES.md`, unchanged: the
court redacts at the source, so the gate catches only narrow nameable failures,
and uncertainty resolves to ACCEPT.

**No gate may reject on interest alone.** A low score means "not today", and the
case stays in the bank. Only safety rejects outright.

---

## 4. FORMAT

### Long-form

```
[0:00]  STING       branded open, 2.6s
        CHAPTER 1   earliest appearance, in full
        CHAPTER 2   the next one
        ...
[end]   HARD CUT    no outro
```

- **Target 8–20 minutes.** Nathan, 2026-08-21, and this supersedes the
  25–58 minute band that stood here: *"no they're usually like 8min to 20
  sometimes it really depends but 50 min is way too long"*. A hearing under
  about **6–7 minutes is too thin to carry a video**.

  The old band came from @courtroomtime, whose house style is hour-long
  compilations, and it was read as a general law. It is not. **Court Trials TV
  Network - 1,000,000 views on its best Boyd video, against Courtroom Time's
  564,000 - runs a 970s median. That is 16 minutes**, inside Nathan's range.
  The strongest channel in the niche and the channel owner agree; the earlier
  figure was one house style mistaken for a rule.

### What one finished video is

Nathan, 2026-08-21, verbatim:

> "complete video would be the defendant comes in usually most times when
> there's a MTR defendant judge Boyd always kinda talks to them and if it's
> actually at least 6-7 min long that's a good video just something with drama
> and judge Boyd calling out people for their bs or asking them what actually
> happened and then the defendant talks to the judge"

Read that as a shape, not a wish list:

1. **A motion to revoke** is the typical setting. Independently supported -
   revocation language runs 1.50× inside rival clips against the docket at
   large, the only case-type that scores positive.
2. **She engages the defendant directly**, rather than processing them.
3. **The defendant answers back at length.** Both halves are required. A
   monologue is not the product and neither is a compliant defendant.
4. **6-7 minutes minimum**, 8-20 the target.

The unit is therefore **the hearing**, not a 60-second moment. Moments are the
hook for the short that advertises it - the long-form is the hearing itself.

Cadence is **every other day**. Additions - narration, graphics, context - come
later; today the video is the hearing, cut. Where someone else has already
posted a case, Nathan: *"if we're gonna clip and bring back what someone already
posted we will do it better and add more to the video"*.
- Chapters run in **chronological order**. Never reordered (SAFETY_RULES R5).
- Dead air over **4 seconds** removed inside each chapter. Shorter gaps stay —
  courtroom pauses carry weight.
- Watermark over the body only, never over the sting.
- No music, no narration, no zooms, no reaction overlays.

### Short

One moment, cut from the long-form, **hook first**.

- 25–59s, vertical 1080×1920.
- **`duo_fill`**: each Zoom tile cropped to the half-canvas aspect so there is
  no black anywhere on the frame.
- Captions **Anton 140**, 13 chars/line, 2 lines max, per-word colour emphasis,
  hard cuts — 340+ of ~350 measured caption transitions in the winner set are a
  single frame. No fades, no slides.
- Captions sit **beside whoever is speaking** (`slot_margins`), driven by ECAPA
  speaker embeddings in `diarize.py`.
- The short's description carries the long-form URL. **Long-form publishes
  first** — a short pointing at nothing is a broken funnel, not a degraded one.

---

## 5. PACKAGING

### Title

- **50–70 characters.** Length itself is flat across 70–120 chars (0.88–1.01×) —
  it is not a lever, just do not truncate.
- **Name Judge Boyd.** Median 16,000 views with her name vs 9,400 without
  (n=491/408). On the rival's top 50, 32 name her; on their bottom 50, 5 do.
- **Name the beat**, not the procedure — the reaction, the regret, the moment
  she puts someone in their place. 1.12–1.73× across three channels.
- One capitalised emotional verb. **Do not** rely on ALL-CAPS hype: it appears
  in 1,785 of 1,785 videos measured. Zero variance, zero signal.
- Measured as noise, do not chase: "DESTROYS/RAGES/SLAMS" (1.01×), sentence
  length in the title (1.00×), quoted defendant speech (**0.77× — worse than
  nothing**).

### Thumbnail

Judge Boyd traced out and composited over the courtroom plate.

- Frame grabbed at a **hot moment** — a timestamp where the transcript shows her
  delivering a hammer or receipt line. She is animated because she is mid-line.
  Do not rank frames by edge energy; measured spread across nine candidates was
  1.7%, which is noise.
- Subject width **0.52 W**, centre **0.78 W**, bottom-anchored.
- Quote **3–6 words, 18–32 chars**, sentence case, white then yellow, split
  mid-sentence. Short enough to fit **one line** — two-line quotes are what put
  text across a face.
- Text sits **below the top quarter**. Rows above y=0.20: 6.5% in winners,
  25.8% in losers.
- **No arrow.** 0/15 winners have one; 5/10 losers do.
- Graded: `sat_gain` 1.45, highlight rolloff to 0.97 so whites do not clip.

---

## 6. WHAT GOVERNS WHAT

1. `spec/SPEC.md` — this file. The contract.
2. `spec/SAFETY_RULES.md` — safety only, and it outranks this file on safety.
3. `config/pipeline.yaml` — the numbers the code actually reads.
4. `prompts/*.md` — what the model is asked.
5. `spec/CONTENT_SPEC.md`, `spec/PACKAGING.md`, `spec/RECORDS-API.md` —
   subordinate specs. Where one disagrees with §1–§5, this file wins; on
   anything this file does not cover, they stand.

Anything under `docs/` is a note, a measurement or a log, and **binds nothing**.

### Corrected 2026-08-20 — this list used to be wrong

The 2026-08-18 edition declared `CONTENT_SPEC.md` and `PACKAGING.md` retired.
**They were not.** Both are still read by things that run, which was verified
rather than assumed:

- `tests/test_pipeline.py:950` opens `spec/CONTENT_SPEC.md` and asserts §2 still
  states a dead-air threshold. Delete the file and the suite fails.
- `config/pipeline.yaml` cites CONTENT_SPEC §2 in three places for the cold open
  and the 4-second rule.
- `prompts/package_post.md` cites `spec/PACKAGING.md` three times, at runtime,
  and `scripts/make_thumbnail.py` builds to its rules.

A file that is declared dead while the build still obeys it is the exact
failure this spec was written to end. They are demoted to subordinate, at
rank 5 above — not retired.

### Genuinely retired

- **`docs/archive/POST-IT-YOURSELF.md`** — stale, three retracted claims. It
  carries its own superseded banner. Was briefly renamed `Notes`, which hid the
  warning its filename was doing; the name is restored.
- **`src/boydclips/notoriety.py`, `banger.py`, `scripts/dialogue_metrics.py`** —
  replaced by §3. Moved to `research/retired/`.
- **`docs/archive/SCOREBOARD.md`** — scoring history from the pre-2026-08-19
  rubric. Kept for the record; the numbers in it are not comparable to current
  scores.

### Moved to reference, one question still open

- **`docs/reference/LONGFORM-ANTIPATTERNS.md`** and
  **`docs/reference/SOURCING.md`** — 90 KB of specialist research. Informative,
  binding on nothing.

  **Open, and Nathan's call, not mine** (`STATE.md`): LONGFORM-ANTIPATTERNS §5
  items 12–13 demand a written script, chapters and legal exposition, and call a
  lightly-trimmed feed a failure. §4 of this file says the opposite. The build
  has followed §4 throughout. Filing the document under reference does not
  settle that — it just stops it being read as a contract while it is unsettled.

### Standing rules

- Profanity: leave it in the audio, censor every text surface.
- Never declare Made for Kids.
- **Publishing is a hard stop** and needs Nathan's confirmation in that turn.
  Rendering locally does not.
- Court footage is public record. Do not invent rights or privacy restrictions
  around it; if a real one applies, quote it.
- Every published clip's manifest records its source timestamps, so any clip can
  be pulled and traced (SAFETY_RULES R7).
