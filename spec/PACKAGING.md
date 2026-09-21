# Packaging spec — titles and thumbnails

**Rewritten 2026-08-18. The previous version derived this whole spec from
Audit the Court, which is the wrong benchmark.** What that version got right is
kept and now rests on 30x more data; what it got wrong is marked RETRACTED
below rather than deleted, so it is not re-derived from the same source.

---

## Why the benchmark changed

The old spec named **Audit the Court** "a direct competitor who covers the same
courtrooms" and rested on **ten titles and twelve thumbnails**, justified by one
Boyd video at 414,784 views.

Measured 2026-08-18 — full catalogues, every channel clipping this docket,
pulled with `yt-dlp --flat-playlist`:

| channel | subs | videos | total views | views/video |
|---|---:|---:|---:|---:|
| **Court Trials TV Network** | 134,000 | 899 | 42.5M | **47,285** |
| Courtroom Time | 46,200 | 553 | 16.5M | 29,829 |
| Court Of Justice | 23,400 | 706 | 7.4M | 10,435 |
| AmericanJusticeFiles | 7,660 | 180 | 2.6M | 14,702 |
| Boyd's Court | 5,090 | 415 | 1.2M | 2,825 |
| Trial Tales | 3,110 | 505 | 1.1M | 2,098 |
| Courtroom Reality Network | 5,620 | 387 | 0.8M | 2,026 |
| *Texas Trial Tracker* | *2,880* | *14* | *244K* | *17,421* |

**Court Trials TV Network holds 29 of the 40 highest-viewed videos in this
niche and three at 1M.** Audit the Court is a broad police-accountability
channel that clipped Boyd once. One video at 414K is a sample of one.

Everything below is now measured **winners against losers inside the same
channel** — Court Trials TV's top 40 titles against their own bottom 40, n=899.
A trait present in both is noise and is labelled as such.

---

## Titles — BOYD_EDITORIAL_V2 (2026-09-06)

Nathan's ruleset. The measured notes that follow this section are kept as
background about the niche; where they conflict with these rules, these rules
win. The single machine-readable copy is `src/boydclips/editorial.py`;
`prompts/package_post.md` and `tools/check_title.py` read it.

**Objective.** A title communicates the most interesting CHANGE, CONFLICT,
REVEAL, DECISION, CONSEQUENCE or BEHAVIOR in the hearing. It is not a case
summary — the description handles context. The title earns the click.

1. **One story only.** One central angle (the case's `story_angle`). Never
   charge + probation + judge reaction + sentence + behaviour in one title.
2. **Promise a real payoff.** Anything the title implies must occur in the
   footage. Never invent intent; never call something a lie unless the record
   supports it — soften to "doesn't add up".
3. **Curiosity without nonsense.** Open an information gap with a specific
   setup; never "You Won't Believe…", "Couldn't Believe THIS", "Changes
   EVERYTHING".
4. **"Judge Boyd"** when her action or reaction is the hook. Not mechanically.
5. **Plain spoken English.** No docket language.
6. **Length.** Hard maximum 70 characters (unchanged, enforced in code).
   Editorial target 45–65. Front-load the interesting information.
7. **No empty hype.** SHOCKING / INSANE / DESTROYED / OWNED / HUMILIATED /
   BRUTAL / SAVAGE / EPIC / INSTANT KARMA / REGRETS only when literally
   accurate. No emoji. No fake all-caps urgency.
8. **Title families** — REVEAL, CONSEQUENCE, CONTRADICTION, BEHAVIOR, ABSURD
   EXPLANATION, WARNING/LAST CHANCE, ADMISSION, EMOTIONAL STAKES,
   SENTENCE/DECISION — used only where the case supports them; patterns, not
   templates.
9. **Generate, score, select.** ≥ 8 candidates across ≥ 4 families; scored on
   Truthfulness 30 / Curiosity 25 / Specificity 20 / Clarity 15 / Natural
   language 10; any exaggeration disqualifies; one winner returned.

**Current thumbnail-copy correction (Nathan, September 12, 2026):** Meaning comes
before a verbatim fragment or a word-count target. Faithful paraphrases and
stylistic quotation marks are allowed in thumbnail text; supporting transcript
quotes and audio captions stay accurate. Require a clear complete idea and a
coherent dialogue exchange, no invented meaning or factual claim. Up to 12 words
including labels is the current ceiling, with full-size and feed-size review.
The daily Sol meaning gate, rendered-copy comparison and image hashes enforce
this handoff. This correction supersedes older verbatim-only/shorter-copy defaults.

**Title + thumbnail are two halves of one idea.** The thumbnail quote (2–6
verbatim words, denial / admission / disbelief / excuse / defiance / reaction /
surprising answer) must not repeat the title's words.

**Still true from the measurements below:** name the judge when she is the
hook; the ceiling is 70; return appearances may be announced ("He's Back").
**Retired:** the mandatory reaction verb, the CAPS payoff word, "withhold the
outcome" as a refusal, and the R41 scoring formula — kept in the checker as
reported signals only.

### Background — the measured notes (2026-08-18 / 2026-09-03)


#### CONFIRMED — 50–65 characters, hard ceiling 70

Court Trials TV's median title is **56 characters** in the top 40 and **57**
across all 899. The old spec's 50–65 band was right; it is now supported by 899
videos instead of ten. Over 70 truncates in suggested and search.

Note this is **length as a house constant, not a lever** — their top 40 and
bottom 40 have the *same* median length (56 vs 56). Staying in the band buys
nothing on its own. It is a floor, and the rules below are the levers.

#### CONFIRMED — name the judge

80% of their top 40 name a judge, against 62% of their bottom 40. Across the
whole niche, titles naming Boyd run a 1.11x median lift (n=2,715). Keep it.

#### RETRACTED — "sentence case otherwise. One emotional verb, exactly one — two reads as spam."

Directly contradicted by the channel that wins. Court Trials TV's **top 40
average four ALL-CAPS words per title; their bottom 40 average two.** 57% of
their winners carry four or more caps words against 35% of their losers.

`Judge Boyd SMUG DEFENDANT Brings Her LOUIS VUITTON TO COURT!!` — 851K.

Caps intensity is house-dependent, not universal: Courtroom Time and Court Of
Justice run 0–1 caps words and do fine. But on the channel with the best
numbers, **more caps correlates with winning, not with spam.** The old blanket
prohibition came from a ten-title sample of a channel outside this niche.

**New rule: 2–4 emphasised words, and they must be the beats — the actor, the
verb, and the stake.** Not decoration spread across the sentence.

#### RETRACTED — "REGRETS" as a recommended verb

The old rule 4 listed `REGRETS` among the emotional verbs to use. Measured
across all 3,645 videos, `Instantly Regrets` / `Regrets It` lands in the
channel-normalised **top 5% only 3.2% of the time — 0.64x the base rate.** It
has the worst tail performance of any pattern tested. It reads as a lift on
medians (1.04x) because it is everywhere on small channels; it does not produce
hits. **Do not use it.**

#### NEW — the verbs that actually carry the tail

P(video lands in the channel-normalised top 5%) against the 5% base rate,
n=3,645 across seven channels:

| beat in the title | n | vs base |
|---|---:|---:|
| **the judge REFUSES / REJECTS the deal, "no mercy"** | 256 | **1.88x** |
| **"SHUTS DOWN"** | 70 | **1.72x** |
| **"LOSES IT" / "SNAPS" / "GOES NUCLEAR"** | 171 | **1.64x** |
| the sentence length ("20 YEARS") | 305 | 1.18x |
| the defendant BEGS / PLEADS / CRIES | 195 | **0.72x** |
| "Top N" compilation framing | 196 | **0.72x** |
| "Instantly Regrets" | 63 | **0.64x** |

The pattern underneath all of it: **the title sells the judge ACTING, not the
defendant reacting.** `Judge Boyd Refuses Plea Deal! & 17 year old gets 5 years`
did 885K. Every negative row above is the defendant's emotional state.

This also corrects the old rule 3 ("lead with the actor, not the procedure").
Right instinct, wrong actor — the actor is Boyd.

#### NEW — announce the return appearance

The single most valuable thing a title can say on the biggest channel:

- `NEW UPDATE!! Judge Boyd SPOILED BRAT IS BACK AGAIN!!` — 1M
- `Judge Boyd Defendant PANICS Over Her Sentence! BACK AGAIN!` — 1M
- `Judge Boyd Entitled BRAT Back Again Facing 20 Years Watch Both Cases` — 765K

Return-appearance titles: **median 15,000 vs 11,000 for one-offs (n=348 vs
551) at the same runtime.** See `analysis.repeat_defendant` in
`config/pipeline.yaml` and `src/boydclips/repeats.py`; `boyd repeats` lists the
32 episodes already buildable from material on disk.

#### CARRIED FORWARD — unchanged, still supported

1. **No proper nouns except the judge.** No defendant names, no cause numbers,
   no county, no court number.
2. **A withheld payoff beats a stated one.** `FAKE ATTORNEY in Judge Boyd's
   Courtroom! THE COMPLETE STORY!` (1M) sells the question.
3. **Terminal `!`** — 97% of the winning channel's titles, though it is present
   in 85% of their losers too, so it is house style, not a lever.

---

## Thumbnails

**This section is Nathan's stated preference, not a measurement, and it is
labelled that way now.**

> **Decision, Nathan, 2026-08-12: "i like audits title style better so use that
> type from now on and the thumbnails as well."**

The first-person quote thumbnail (4–9 words, sentence case, terminal `!`/`?`,
white with the loaded half in `#FEFB04`) stands as the house style because
Nathan chose it. What is retracted is the *claim that it was validated* — it
was measured on twelve thumbnails from a channel that is not in this niche's
top three, and it has never been tested against Court Trials TV's set.

Construction constants live in `scripts/make_thumbnail_v2.py` and
`config/pipeline.yaml → packaging.thumbnail`.

**Known unmeasured, do not treat as settled:**

- Whether the quote thumbnail beats Court Trials TV's construction on this
  niche. Untested either way.
- **The red arrow is noise** — 4/6 winners and 4/4 losers carry one. Kept as
  style, not as evidence.
- `@Courtroom` (220K subs, 13 videos, 111.7M views, **zero Boyd content**) runs
  a two-panel hard-split template with no text, no logo and no arrow in 10 of
  10. Its numbers come from being a cross-court compilation channel, so its
  template is **not transferable evidence** — a previous note treating it as a
  6x-better thumbnail benchmark overstated it.

The single thing that did survive 60 thumbnails: **no high-view thumbnail has a
stroked or glowing cutout edge.** Keep the feathered, unstroked composite.

---

## Precedence

`spec/CONTENT_SPEC.md` is the format contract. This file governs titles and
thumbnails only. Where a rule here is marked RETRACTED, the retraction wins over
any older doc that still repeats it — including `spec/SPEC.md §2` and
`STATE.md`.

*Method: full-catalogue `yt-dlp --flat-playlist` dumps, 2026-08-18, 3,645
videos across 7 channels. Views normalised within each channel's upload decile
to control for age. Tail figures are P(top 5%) against base rate; median
figures are median-of-normalised with a per-channel sign check.*
