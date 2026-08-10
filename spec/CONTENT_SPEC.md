# CONTENT SPEC — Boyd Clips

**This file is the format contract.** Every clip the system produces conforms to
it. If output starts drifting, the fix belongs here, not in a one-off prompt
tweak. Version this file; the version is stamped into every clip's manifest.

**Spec version: 1.1.0** — §3 gained the Form B single-moment short after Form A
measured 0/10 against real dockets.

---

## 1. The daily unit

One docket day produces **one publishable pair**:

| Piece | What it is | Where it goes |
|---|---|---|
| **Long-form** | The complete case, start to finish, lightly trimmed | YouTube (primary) |
| **Short** | A 25–59s vertical hook cut from *inside* that case | Shorts, TikTok, Reels |

The short is not a standalone product. It is a **routing device**: its entire
job is to make someone watch the long-form. Every short must therefore:

- be cut from a case that has a long-form version already rendered,
- end with a card pointing at the full case,
- carry the long-form URL in its description.

**Ordering is load-bearing.** The long-form publishes first, returns a URL, and
that URL is injected into the short's description before the short publishes.
A short that publishes without a resolvable long-form URL is a bug, not a
degraded case.

---

## 2. Long-form structure

```
[0:00]  COLD OPEN     — the case begins; no intro, no branding, no logo sting
        BODY          — the proceeding, uncut except for dead air > 4s
        RESOLUTION    — the judge's ruling or the case's natural end
[end]   HARD CUT      — no outro, no "like and subscribe"
```

Rules:

- **Never** cut mid-sentence. Boundaries snap to caption-segment edges.
- Dead air longer than 4 seconds is removed. Shorter gaps stay — courtroom
  pauses carry weight and cutting them makes proceedings feel falsified.
- No music. No sound effects. No added narration. The audio is the record.
- No zooms, speed ramps, or reaction overlays. This is a document.
- Trim only at the head and tail plus interior dead air. **Never reorder.**
  Reordering courtroom speech misrepresents a proceeding.

---

## 3. Short structure

There are two permitted forms. Try the first; fall back to the second.

### Form A — four beats (preferred)

```
0.0 – 3.0s    HOOK      The single most arresting line in the case.
                        Starts on a word, not a breath. No setup.
3.0 – 8.0s    STAKES    What is actually at risk for this person.
8.0 – Xs      TURN      The moment something changes.
X – end       BUTTON    The judge's ruling or the last decisive line.
+2.0s         END CARD  "FULL CASE IN DESCRIPTION"
```

### Form B — single moment (fallback)

One contiguous 25–59s stretch. No arc, no assembly, no beats.

```
0.0 – end     MOMENT    The strongest continuous stretch of the case.
+2.0s         END CARD  "FULL CASE IN DESCRIPTION"
```

**Why this exists.** Form A was originally the only permitted structure, and
measured against real dockets it fitted **zero of ten** safety-passing cases.
That is not a defect in the footage — a pretrial docket is mostly continuances,
resets and counsel substitutions, and a fifty-five-second continuance request
genuinely has no "turn". Requiring a narrative arc from proceedings that have
none produced a system that could never publish. Form B matches what the
material actually is.

Do not treat Form B as a failure state. A single unbroken exchange is often the
stronger clip precisely because nothing was assembled.

Rules for both forms:

- The hook — or the moment's first word — is the **first frame**. Not a title
  card, not a countdown.
- Segments appear in **chronological order as they occurred**. A short is a
  compression of the case, never a rearrangement of it.
- Prefer Form A when all four beats genuinely exist. Never manufacture a beat
  by splicing unrelated material to fill the shape — that is precisely the
  R8 violation the structure is meant to prevent.
- If neither form can be built (no 25s of usable continuous audio), the case is
  **not shortable** — render the long-form only and bank it.
- Target 45s. Hard ceiling 59s.

---

## 4. Vertical framing

Zoom court puts multiple people on screen at once — judge, defendant, counsel.
Center-cropping to 9:16 cuts participants out of frame and destroys the thing
that makes the footage worth watching.

**Standard treatment:** scale the full 16:9 frame to 1080px wide, center it
vertically, and fill the remaining space with a blurred, darkened copy of the
same frame.

```
┌─────────────┐
│ blurred fill│
├─────────────┤
│             │
│  full 16:9  │  ← nothing cropped, everyone stays in frame
│    frame    │
├─────────────┤
│ captions    │
│ blurred fill│
└─────────────┘
```

---

## 5. Captions

- Burned in, always. Most viewing is sound-off.
- Word-level highlight — the active word changes color as it is spoken.
- Max 22 characters per line, max 2 lines. Longer lines get unreadable at
  thumb distance.
- Uppercase.
- Positioned in the lower blurred band, never over a participant's face.
- **Captions are verbatim.** Auto-caption errors get corrected against what was
  actually said; they never get "improved," paraphrased, or punched up.

---

## 6. Titles

A title must be **a claim the clip itself proves**. If a viewer watching only
the clip would not agree the title is accurate, the title is wrong.

| Do | Don't |
|---|---|
| "Judge Boyd revokes bond after defendant admits he left the county" | "Judge DESTROYS defendant" |
| "Defendant asks for more time; the judge explains why that's the third request" | "You won't BELIEVE what happened next" |
| Quote a line actually spoken | Invent a line, paraphrase into a quote |
| "charged with" / "accused of" | "the man who did X" |

Rules:

- Max 100 characters long-form, 90 short.
- No ALL-CAPS words except a quoted phrase that was actually shouted.
- No "DESTROYS", "ANNIHILATES", "SHOCKED", "SPEECHLESS", "GONE WRONG".
- No question-bait ("What happens next will...").
- If the clip's own audio does not support the title, regenerate the title.

---

## 7. Hard rejects

A case is rejected outright — no score, no render — if **any** apply. See
`spec/SAFETY_RULES.md` for why each one is here.

- Involves a juvenile, in any capacity.
- Involves a victim or alleged victim of a sexual offense.
- Contains a name, address, phone number, or workplace of a victim, witness,
  or juror.
- Contains identifying detail about a juror or the jury's deliberations.
- Would require context from outside the clip to avoid being misleading.
- The dramatic content is a person's visible mental-health crisis, addiction
  symptoms, disability, or poverty.
- Audio is unintelligible in the load-bearing moment.
- Turns on a legal technicality the clip cannot explain — those read as
  "judge is unfair" when they are routine.

---

## 8. Manifest

Every rendered clip writes `manifest.json` beside it, containing: spec version,
source video ID, exact source timestamps, transcript excerpt, the full scoring
breakdown, the safety determination with reasoning, the model and prompt
versions used, and the generated title/description.

This exists so that if a clip is ever challenged, you can reconstruct in one
step exactly what was published, from where, and why the system chose it.
