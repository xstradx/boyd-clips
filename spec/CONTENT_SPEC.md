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
- end with a card pointing at the full case — **AMENDED 2026-09-06:** the
  SHORTS_EDITOR_V2 short carries NO end card; it ends on the story's payoff
  or reaction and nothing is drawn over the final spoken caption. A CTA, if
  wanted, will be designed separately (Nathan). The legacy path keeps its
  card,
- carry the long-form URL in its description.

**Ordering is load-bearing.** The long-form publishes first, returns a URL, and
that URL is injected into the short's description before the short publishes.
A short that publishes without a resolvable long-form URL is a bug, not a
degraded case.

---

## 2. Long-form structure

```
[0:00]  STING         — branded open, 2.6s, then straight into the case
        BODY          — the proceeding, uncut except for dead air > 4s
        RESOLUTION    — the judge's ruling or the case's natural end
[end]   HARD CUT      — no outro, no "like and subscribe"
```

Rules:

- **The sting is branding, not content.** `boyd-brand/sting_v2.mp4`, 2.6s,
  1920x1080, with audio. It goes in front of the body inside the same filter
  graph, so the court footage is compressed once. The watermark is applied to
  the BODY only — stacking the mark on top of the sting reads as a mistake.
  Config: `output.longform.intro_enabled`.

  **AMENDED 2026-08-17, Nathan's instruction.** This section previously
  specified `COLD OPEN — the case begins; no intro, no branding, no logo
  sting`. That rule was written before the channel had a brand, and the build
  had diverged from it in practice: `render_longform` accepted an `intro`
  argument from the start. Keep the sting short. The 5.1s and 7.7s `_SLOW`
  variants exist and are the wrong choice — both are silent, which forces a
  synthesised audio branch to keep concat happy, and long branding in front of
  a hearing is retention spent on nothing.

- **Never** cut mid-sentence. Boundaries snap to caption-segment edges.
- Dead air longer than 25 seconds is removed. Shorter gaps stay — courtroom
  pauses carry weight and cutting them makes proceedings feel falsified.

  Raised from 4 seconds on 2026-08-21, asked directly. Nathan: *"only cut if the
  screen goes black or she says shes gonna call them back in a couple min"*. The
  four-second rule was written here, not by him, and it was removing the pause
  before an answer — which is the moment, not dead air. His actual rule needs
  black-frame detection, which does not exist yet; 25 seconds is a stand-in that
  clears recesses and camera cuts while leaving ordinary pauses alone, and it is
  recorded as a stand-in rather than as his rule.
- No music. No sound effects. No added narration. The audio is the record.
  The sting carries its own audio; nothing is added over the proceeding.
- No zooms, speed ramps, or reaction overlays. This is a document.
- Trim only at the head and tail plus interior dead air. **Never reorder.**
  Reordering courtroom speech misrepresents a proceeding.

  **AMENDED 2026-09-06 — the story-preserving cap (accepted).** A long-form
  that still exceeds `output.longform.max_duration_s` after the trims above
  may lose *interior* lower-value material, but only through the cap-fit
  planner (`src/boydclips/capfit.py`), which:
  - keeps an under-cap long-form exactly as the rules above produce it —
    chronological, unchanged except for the existing head/tail/dead-air trims;
  - protects the setup, the money-moment window and the ending
    (`output.longform.cap_fit`) so they survive whole, and refuses the case
    with the reason if even those do not fit — nothing is truncated silently;
  - drops the free material farthest from the story first, never the run-up
    to the payoff;
  - places every interior cut on a transcript pause where one is available
    within reach, never inside a word;
  - never reorders — every kept range stays in source order;
  - records the plan (protected, kept, dropped, money-moment source) in the
    manifest under `outputs.longform.cap_fit`, so the edit is auditable.

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

**AMENDED 2026-09-06 — SHORTS_EDITOR_V2 (implemented, awaiting Nathan's
review of rendered output).** With `output.short.editor: v2` (the default)
the daily short is planned by `src/boydclips/shorts_editor.py` instead of
being taken from the model's beats; Form A / Form B above describe the legacy
planner, which `editor: legacy` restores unchanged.

- The short is a **mini-story from inside the one case**: setup → tension →
  turn → payoff, plus a short reaction when the reaction is the point. It is
  found around the editorial money moment (which wins a tie inside
  `planner.money_moment_window` points), Boyd's documented tells, receipts
  and answered excuses, and scored out of 100 (hook 25 / clarity 20 /
  payoff 25 / escalation 15 / quote 10 / visual 5). Those are transcript
  proxies that rank candidates; they do not prove a short is good.
- **Duration:** 25–60 s is the target; the floor is `planner.min_duration_s`
  (15 s), because a complete 18-second story ships as 18 seconds and nothing
  is padded. The 59 s ceiling stands. Over it the planner drops setup, then
  the reaction, then trims the claim from its front — the payoff line is
  never cut. Under the floor it extends only with material that belongs to
  the story (the rest of the payoff turn, the exchange just before the hook).
- **Chronology holds, with one declared exception:** a cold-open teaser — the
  payoff line, at most `planner.teaser_max_s` (3 s), played first and then
  again in place. The plan records the teaser's source range, the manifest
  carries `nonlinear: true`, and a plan whose order differs in any other way
  is refused (`shorts_editor.verify_chronology`).
- **THE CONTINUITY RULE (Nathan, 2026-09-06, after the first Flores render
  cut his question to a line the defendant said twenty seconds later about
  something else).** After the teaser, the body is ONE contiguous stretch of
  the source: chronological order and actual conversational adjacency are
  preserved. Inside it only dead air over `planner.dead_gap_s`,
  acknowledgments, repeated wording and clearly procedural filler may be
  removed; nothing substantive is ever jumped over. A kept sentence that
  ends in a genuine question is followed on screen by the answer that
  actually followed it in the source, or the clip starts elsewhere. Every
  interior join is audited — the omitted transcript is recorded in the plan
  (`interior_cuts`) and `question_answer` lists each kept question with what
  follows it on screen and in the source; `shorts_editor.verify_continuity`
  re-runs the audit right before the render and refuses a false join.
  Chronological proximity, speaker alternation and score are never evidence
  that two lines belong together. Main body = contiguous conversation with
  compression, not a montage of semantically guessed lines.
- Every cut lands in the silence around a word, never inside one, and two
  continuous beats with the same framing are one segment (no jump cut for
  nothing).
- A case with no valid mini-story is **refused with the reason** —
  `short_plan.txt` beside the render, `short_editor.refusal` in the manifest —
  and the long-form still ships. The scorer's `shortable` flag is advisory;
  disagreement is logged as MISMATCH. The full edit plan (beats, source
  ranges, speaker, purpose, focus, punch-ins, accents, captions, QC gates)
  is in `outputs.short.edit_plan`, with `source_case_key` beside it.

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

**AMENDED 2026-09-06 — the FIXED courtroom layout (SHORTS_EDITOR_V2, Nathan,
third pass).** The blurred-fill treatment above is the fallback; the V2
short is a stable 50/50 stack: defendant in the top 1080×960 slot, Judge
Boyd in the bottom one (roles from recognition, `tools/identity.py`, fixed
for the whole Short), divider at y = 960 that never moves — not for speaker
focus, not for punch-ins. Each person is deliberately CENTRED in their slot
from a measured subject anchor (YuNet face, median over frames inside the
kept ranges — never the geometric centre of the source tile), with natural
headroom and no cropped head, chin or shoulders (`layout.center_window`,
zoom bounded by `center_max_zoom`, residual recorded). A punch-in is a zoom
of about 1.06–1.12 (`punch_zoom`) INSIDE the speaker's tile around that
anchor, at most about two per Short, on a pivotal question / contradiction /
reveal / admission / consequence / reaction; the other tile and the divider
stay exactly where they were. The earlier 60/40 "weighted focus" layout is
gone. One overlay layout (`layout.overlay_layout`) knows every overlay's box
before the render — caption block, watermark — and a collision between
critical overlays refuses the render (`overlay_collision`). After the
render, `render.visual_qc` writes a contact sheet (opening, first speaker
change, first punch-in, middle, payoff, final) and the composition data for
those frames, and measures the divider on each.

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

**AMENDED 2026-09-06 — SHORTS_EDITOR_V2 captions live on the divider
(Nathan, third pass).** Neither the first V2 phrase-DP ("AND SHE TOLD" / "ME
THAT SHE" / "WAS") nor the legacy 3-word / 13-character grouping is what he
wants; both produced arbitrary chunks. The V2 short now has ONE caption
system (`src/boydclips/captions.py` + `render.build_rail_ass`):
- **Position:** the caption block is anchored at centre (540, 960) — on the
  dividing line between Boyd and the defendant, straddling it slightly —
  and never moves with focus or punch-ins. Not on anyone's face, chest or
  tile. The legacy per-speaker slots apply to the legacy path only.
- **Phrasing:** cards are natural phrases chosen by a planner that returns
  INDICES into the exact kept words (card boundaries, the line break, one
  emphasised word) and never text: about 3–7 words as a preference (one
  dramatic word or eight can be right); never split "Judge Boyd", "Your
  Honor", auxiliary+verb, article+noun, preposition+object or an obvious
  short noun phrase; do not end a card on a glue word unless the delivery
  pauses; prefer punctuation, breath and semantic boundaries; two lines
  max. A configured provider may propose the same indices; its proposal is
  validated against the same rules and the deterministic plan is used when
  it is unavailable or invalid. Cards are built from the words that survive
  the edit, mapped through the render segments (`captions_from_kept_words`
  gate); a cut sentence never reaches the screen.
- **Style:** white, bold clean font (Anton), black outline, subtle shadow;
  one genuinely important word per card in yellow when it earns it, never
  on adjacent cards; no karaoke, no word-by-word motion, no boxes, no fade.
  The courtroom is the visual; captions assist it.
- **No end card** (see §1).

**AMENDED 2026-09-06 — kinetic chunk-build captions (Nathan, fifth and
sixth passes).** Supersedes the "no word-by-word motion" style line above
and qualifies "captions are verbatim" (`src/boydclips/captions.py`,
CAPTIONS_V3_KINETIC; `docs/CAPTIONS-V3-CHUNK-BUILD-2026-09-06.md`):
- **One line only** on the fixed rail (540, 960), widths measured with the
  font file; a phrase that does not fit is split, never wrapped or shrunk.
- **Hard speaker boundaries:** phrases are planned inside one verified
  speaker run; a speaker change clears the rail and the next speaker starts
  from empty. Structural, not a post-check.
- **Caption for meaning:** the audio is untouched; the DISPLAY may omit
  non-semantic disfluencies — fillers, immediate accidental repetitions,
  pronoun restarts ("I just I don't" → "I just don't"), a trailing
  abandoned stumble at the end of a speaker run. Never omitted: negation,
  numbers, names, admissions, denials, intentional emphatic repeats. Every
  displayed word maps to its source word and every omission is audited in
  the plan (`caption_audit`); nothing is ever invented or paraphrased.
- **Chunk build:** a phrase reveals in 1–3 natural micro-phrases, the new
  chunk warm yellow with one 88 → 105 → 100 % pop (~110 ms), earlier
  text white and unmoving, the left anchor fixed per phrase; about 1–2
  visual changes per second on average (QC `DENSITY`). A completed phrase
  holds briefly, then clears before the next thought.
- **Readable phrases:** 2–6 words typically, complete units; no sentence
  end inside a phrase; no dangling glue or subject pronoun unless the
  delivery pauses; particle verbs and titles never split; no flicker.
- **Size and centring (visual polish, 2026-09-06):** the rail font is a
  96 px em (Anton; libass Fontsize = em × 1.7334 because Fontsize is the
  cell height — `render.ass_font_scale`), safe width 980 px; a completed
  phrase is centred on its VISUAL box (ink + outline + shadow) at x = 540,
  verified by rendering the ASS on a black canvas and measuring
  (`caption_visual_center_error_px`, target ≤ 10 px), and the block of
  capitals is centred on the divider by one uniform offset. The new chunk
  enters with an eased overshoot (92 → 106 → 100 %, 110 ms) and a 60 ms
  opacity rise; nothing already visible moves.

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

---

## 9. Profanity — audio uncensored, text always censored

Nathan, 2026-08-13: *"leave the sound in but always cencor it in the text pls."*

**Audio ships as recorded.** Bleeping testimony edits what a witness actually
said, and primary-source fidelity is this channel's entire claim. Leave it.

**Every text surface is censored** — burned-in captions, SRT/VTT sidecars,
titles, descriptions, thumbnails, on-screen cards, chapter names, and the shot
lists and dossiers in this repo.

The asymmetry is not inconsistency: text is what gets **indexed, thumbnailed and
read out of context**. A caption or title carries the word stripped of the
courtroom around it, to a classifier or a scrolling viewer. Spoken audio inside
the clip is contextualised by the footage carrying it.

Use `scripts/censor.py`:

```python
from censor import censor, has_profanity
caption = censor(line)     # "I shouldn't have f***ing told him anything"
```

Style is first letter, asterisks, trailing letters — `f***ing`. Never delete the
word and never paraphrase it; the reader should know exactly what was said.

**Corollary, and it has already bitten once:** a quote in our own notes may have
been sanitised at write time and is therefore not evidence of what was said.
`out/dossiers/CASTILLO_SINGLE_CUT.md` rendered this line clean; the transcript at
`a3_shouldnt_have_said.mp4` 32.32–46.16 is stronger. Check the transcript before
trusting a quote from our own documents.
