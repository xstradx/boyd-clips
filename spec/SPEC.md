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

- **Target 25–58 minutes.** Measured on @courtroomtime, pre-Oct-2025 where age
  is uniform: 0–20m 0.39×, 20–35m 0.86×, 35–50m 1.06×, **50–58m 1.35×**, 58+
  0.83×. It falls off after 58, so this is a band and not "longer is better".
  One appearance rarely fills it; that is fine, and it is another reason the
  format stacks appearances rather than padding one.
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

Everything else is a note, a measurement or a log, and **binds nothing**.

### Retired 2026-08-18

- **`spec/LONGFORM-ANTIPATTERNS.md`** — §5 items 12–13 demanded a written
  script, chapters and legal exposition, and called a lightly-trimmed feed a
  failure. That is the opposite of §4 here. It was one specialist's
  negative-space output, it was never reconciled, and the build ignored it.
- **`spec/CONTENT_SPEC.md`** — superseded by §4 and §5. Its cold-open rule was
  already amended once when the sting was added.
- **`spec/PACKAGING.md`** — its thumbnail rules came from 12 thumbnails of a
  different channel and are superseded by §5, measured from 25 thumbnails of the
  channel clipping this same judge.
- **`POST-IT-YOURSELF.md`** — stale, with three retracted claims.
- **`src/boydclips/notoriety.py`, `banger.py`, `scripts/dialogue_metrics.py`** —
  replaced by §3.

### Standing rules

- Profanity: leave it in the audio, censor every text surface.
- Never declare Made for Kids.
- **Publishing is a hard stop** and needs Nathan's confirmation in that turn.
  Rendering locally does not.
- Court footage is public record. Do not invent rights or privacy restrictions
  around it; if a real one applies, quote it.
- Every published clip's manifest records its source timestamps, so any clip can
  be pulled and traced (SAFETY_RULES R7).
