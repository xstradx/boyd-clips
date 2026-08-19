# Audit the Court — title formula, measured

Retrieved 2026-08-11. Competitor n=40 longform. Client = **Texas Trial Tracker**, FOUND
(`UCT5Fde6OzBSFRmxw5mPn2CA`, 2,880 subs), 13 longform + 11 Shorts = 24 videos.

---

## 0. CONTROL INTEGRITY — read this first

**The blind control was contaminated before I started.** The task prompt handed me all 40
competitor titles in the assignment text, so I had already read "When a Cop's Testimony
IMMEDIATELY Backfires in Court!" before I opened a single transcript. A true blind is no
longer available for these 40 videos.

What I did instead: for each of the 10 videos below I read the transcript opening
(~220 deduped caption lines) and the closing summary, and wrote the title from the case
facts. I did not consult the title list while writing. That makes the exercise an
*honest reconstruction*, not a clean control — anchoring toward their phrasing cannot be
ruled out, and if anything that biases my titles to look **closer** to theirs than a real
blind would produce. The measured gap below is therefore a floor, not a ceiling.

A clean control is still runnable on videos whose titles were not in the prompt
(e.g. Audit the Audit's back catalogue, or new AtC uploads).

---

## 1. STEP 1 + 2 — my title vs theirs, 10 videos, top-performer weighted

| # | id | views | MY title (written from transcript) | chars | THEIR title (verbatim) | chars |
|---|----|------:|---|---:|---|---:|
| 1 | yzv_uxBSgu0 | 1,200,000 | Defense Attorney Cross-Examines Officer Over DWI Testimony \| Martinez DWI Trial, Harris County (Judge Fleischer) | 112 | `When a Cop's Testimony IMMEDIATELY Backfires in Court!` | 54 |
| 2 | 4kIjd7CLp7c | 971,000 | Ninth Circuit Oral Argument on Qualified Immunity: CHP Officer Arrested a Firefighter Treating a Patient (Gregoire v. Flores, 2017) | 131 | `Cop ARRESTS a Firefighter on Duty and Gets SUED` | 47 |
| 3 | amiWU58HFpM | 591,000 | Judge Kristen Simmons Dismisses Both Counts After Finding a Pretextual Traffic Stop \| People v. Sautello Preliminary Examination | 128 | `This Cop Totally EMBARRASSES Himself in Front of the Judge!` | 59 |
| 4 | SpO2yU2mG78 | 552,000 | Deposition of Sgt. Nick Dial in Knowles v. Royse City: Sign Slapping, Disorderly Conduct and the First Amendment | 112 | `Cop GETS SUED and DESTROYED By Attorney [AtA x AtC]` | 51 |
| 5 | 5VLPFCTlyss | 444,000 | Sergeant Charged With Assault for Macing a Handcuffed Arrestee \| People v. Deya Preliminary Examination, 14A District Court | 123 | `When a Judge Holds a Corrupt Cop Accountable in Court!` | 54 |
| 6 | lzOg8heXmV0 | 439,000 | Bench Trial: City of Detroit v. David Pletz — Disobeying a Lawful Order and Interfering With Traffic (Judge Ramsey-Heath) | 121 | `Cop ILLEGALLY Arrests a Man and REGRETS It in Court [AtA x AtC]` | 63 |
| 7 | Ek3Ah3NZYVo | 414,784 | Bexar County Deputy Who Tased Jail Cadets Sentenced by Judge Boyd \| 1 Year Probated 4 Years, Tampering With a Government Record | 127 | `Judge Boyd LOSES IT After Finding Out What This Cop Did` | 55 |
| 8 | IPpy830CJkQ | 412,000 | Dash Cam Contradicts Trooper's Testimony and Judge Simmons Dismisses the Fleeing Charge \| People v. Winfrey | 107 | `When a Cop's Fake Story Completely Collapses in Court` | 53 |
| 9 | B3unsajFoXc | 402,000 | Florida Supreme Court Oral Argument on Permanent Disbarment \| The Bubba the Love Sponge DUI Setup Case (Florida Bar v. Adams) | 125 | `Corrupt Attorneys and Dirty Cop Team Up and Get DESTROYED` | 57 |
| 10 | 1qmeHyUkad4 | 397,000 | Karen Read Retrial: Bob Alessi Cross-Examines Forensic Analyst Shannon Burgess on the SUV Data Timeline | 103 | `Clueless Prosecutor's Expert DESTROYS the State's Murder Case` | 61 |

Median mine **122** chars. Median theirs **54.5** chars. Delta range −42 to −84.
Mine over 70 chars: **10/10**. Theirs over 70 chars: **0/10**.

---

## 2. STEP 3 — the diff, ranked by size of gap

### 3a. First three words

| # | my first 3 | their first 3 |
|---|---|---|
| 1 | Defense Attorney Cross-Examines | When a Cop's |
| 2 | Ninth Circuit Oral | Cop ARRESTS a |
| 3 | Judge Kristen Simmons | This Cop Totally |
| 4 | Deposition of Sgt. | Cop GETS SUED |
| 5 | Sergeant Charged With | When a Judge |
| 6 | Bench Trial: City | Cop ILLEGALLY Arrests |
| 7 | Bexar County Deputy | Judge Boyd LOSES |
| 8 | Dash Cam Contradicts | When a Cop's |
| 9 | Florida Supreme Court | Corrupt Attorneys and |
| 10 | Karen Read Retrial: | Clueless Prosecutor's Expert |

I lead with **venue / procedural posture / party name** in 10/10.
They lead with **the antagonist noun** in 10/10 — `Cop` (or `Cops`/`Sergeant`) inside the
first 3 words in 6/10, `Judge` in 2/10, `Prosecutor`/`Attorneys` in 2/10. Across all 40:
`Cop`/`Cops` appear in **22/40** titles; `When a` opens **6/40**.

Their first 3 words never contain a place, a court, a case number, a date, or a party's
surname. Across all 40 titles: **0/40 contain a digit**, **1/40 contains a person's proper
name** (`Afroman`), **0/40 name a state or county**, **0/40 use a colon**.

### 3b. What I included that they deleted

Counted across my 10 titles vs all 40 of theirs:

| element | mine (of 10) | theirs (of 40) |
|---|---:|---:|
| named individual (surname) | 9 | 1 |
| named judge by name | 4 | 1 (`Judge Boyd`, in Ek3Ah3NZYVo) |
| court / venue named | 8 | 0 |
| case caption (`v.`) | 5 | 0 |
| statute / charge named | 6 | 4 |
| sentence or number stated | 2 | 0 |
| date or year | 1 | 0 |
| pipe `\|` or colon `:` separator | 10 | 0 |

Their entire vocabulary of specificity is **role nouns**: Cop, Judge, Attorney,
Prosecutor, Sergeant, Firefighter. Nobody has a name. Nothing has a docket.

### 3c. Where the ALL CAPS sits

- 33/40 titles carry ≥1 all-caps token; 7/40 carry none.
- **Median word index of the first caps token = 2 (0-based)** — i.e. the third word — in a
  median 10-word title. Median relative position **0.31**, so the caps token lands in the
  first third, not at the end.
- Most common index is **1** (second word): 10/40. Index 2: 7/40.
- Part of speech: the caps token is a **finite verb** in the large majority.
  Frequency: `EXPOSED` 5, `DESTROYS` 5, `DESTROYED` 5, `LOSES` 4, `IT` 4, `IMMEDIATELY` 3,
  `SUED` 2, `NOT` 2, `WELL` 2, then 22 singletons (`SHUTS`, `DOWN`, `CHALLENGED`,
  `EXPOSES`, `CALLS`, `OUT`, `CAUGHT`, `DENIES`, `ILLEGALLY`, `REGRETS`, `EMBARRASSES`,
  `LIES`, `POWER`, `DID`, `GO`, `DOES`, `END`, `ARRESTS`, `GETS`, `FAILED`, `ONE`,
  `SECOND`).
- Only two adverbs are ever capitalised (`IMMEDIATELY` ×3, `ILLEGALLY` ×1); only two nouns
  (`POWER`, `ONE`). Caps is a **verb highlighter**, not emphasis-at-random.
- 14/40 use 2+ caps tokens, and those are almost always one lexical unit —
  `LOSES IT` (×4), `SHUTS DOWN`, `DID NOT GO WELL`, `DOES NOT END WELL`, `GETS SUED`.
- I used **0 caps tokens in 10/10**.

### 3d. Punctuation, questions, quotes

- ends with `!`: **12/40**. ends with `.`: **0/40**.
- question mark: **0/40**. ellipsis: **0/40**. double-quote: **0/40**. colon: **0/40**.
- Only bracket use is the collab tag `[AtA x AtC]` (2/40).
- I used a colon or pipe in 10/10 and never an exclamation mark.

### 3e. Outcome — revealed or withheld

They **withhold the specific outcome and promise the shape of it**. 18/40 contain an
outcome-shaped predicate (`Backfires`, `REGRETS`, `Gets EXPOSED/SUED/DESTROYED/CAUGHT`,
`DID NOT GO WELL`, `DOES NOT END WELL`, `FAILED`, `Ends Up`, `Collapses`) — the viewer is
told *someone loses*, never *what the ruling was*. **0/40** state a verdict, a sentence, a
dismissal, or a dollar figure.

I revealed the literal disposition in 6/10 ("Dismisses Both Counts", "Sentenced… 1 Year
Probated 4 Years", "Life Without Parole"-class specifics). That kills the open loop.

---

## 3. STEP 4 — the formula

### Primary template (fits 33/40)

```
[ADJECTIVE?] <ROLE-NOUN> <VERB-IN-CAPS> <OBJECT> [and|After|When <CONSEQUENCE-CLAUSE>] [in Court] [!]
```

Slots:

| slot | fill values observed | frequency |
|---|---|---|
| ADJECTIVE (optional) | Clueless, Corrupt, Clever, Arrogant, Genius, Disbarred, Dirty, Bad | 9/40 |
| ROLE-NOUN | Cop/Cops (22), Attorney/Lawyer (13), Judge (11), Prosecutor (6), Sergeant (1), Police Department (1) | — |
| VERB-IN-CAPS | DESTROY* (10), EXPOSE* (6), LOSES IT (4), SUED (2), plus singletons | 33/40 have ≥1 |
| CONSEQUENCE | `and Gets X` / `and it IMMEDIATELY Backfires` / `and It DID NOT GO WELL` / `and REGRETS It` | 18/40 |
| SETTING TAG | `in Court` (15/40), `Court` anywhere (17/40) | — |
| TERMINATOR | `!` (12/40), nothing (28/40) | — |

### Secondary template (fits 10/40) — the "When" wrapper

```
When [a] <SUBJECT> <VERB> <COMPLEMENT> [in Court] [!]
```

`When` opens 10/40; `When a` opens 6/40. It converts the headline into a dependent clause
with no main clause — grammatically unresolved, which is the open loop.

### Hard constraints the 40 titles obey without exception

1. **No digits.** 0/40.
2. **No proper names except one.** 1/40 (`Afroman`).
3. **No venue, no state, no county, no docket.** 0/40.
4. **No colon, no question mark, no quote marks, no ellipsis.** 0/40 each.
5. **Never states the disposition.** 0/40.
6. **Title case throughout**, except the caps token.
7. **`Judge Boyd` named exactly once in 40 titles** — despite the channel being built on
   her court. Generic `Judge` appears 11/40.

### Length distribution (n=40)

min **35** · median **55.0** · mean **55.3** · max **77**
≤50 chars: 11 · 51–60: 20 · 61–70: 5 · **>70: 4/40 (10%)**

Longest: `Disbarred Attorney Tries to Get His License Back and Gets CAUGHT Lying Again!` (77)
Shortest: `How ONE Question DESTROYED the Case` (35)

**Half of all their titles fit in 51–60 characters.** They sit deliberately inside the
~70-char truncation window.

---

## 4. STEP 5 — pattern vs views. n is small; treat as directional only.

Channel baseline: mean **299,084**, median **224,535** (n=40).

### By opener bucket

| bucket | n | mean | median | min | max |
|---|--:|--:|--:|--:|--:|
| A `When`-clause | 10 | 372,345 | 259,477 | 172,631 | 1,200,000 |
| C Cop-first | 11 | 327,775 | 252,000 | 82,783 | 971,000 |
| B Judge-first | 6 | 253,101 | 256,000 | 42,000 | 414,784 |
| E Prosecutor-first | 4 | 250,375 | 228,000 | 148,502 | 397,000 |
| F other | 4 | 249,500 | 174,000 | 59,000 | 591,000 |
| D Attorney-first | 5 | 223,259 | 215,000 | 101,000 | 402,000 |

### Binary splits

| feature | YES n / mean / median | NO n / mean / median |
|---|---|---|
| has ALL-CAPS token | 33 / 301,949 / 222,870 | 7 / 285,581 / 301,000 |
| ends with `!` | 12 / 364,224 / 278,436 | 28 / 271,167 / 211,935 |
| contains `in Court` | 15 / 324,420 / 252,000 | 25 / 283,883 / 224,000 |
| starts with `When` | 10 / 372,345 / 259,477 | 30 / 274,664 / 219,500 |
| DESTROY/EXPOSE verb | 16 / 242,122 / 206,000 | 24 / 337,059 / 269,000 |
| outcome-shaped predicate | 18 / 335,140 / 238,000 | 22 / 269,584 / 223,970 |

### Length buckets

| chars | n | mean | median |
|---|--:|--:|--:|
| ≤45 | 5 | 268,811 | 293,884 |
| 46–55 | 17 | 344,504 | 211,000 |
| 56–65 | 13 | 286,530 | 252,000 |
| **66+** | **5** | **207,574** | **195,000** |

Pearson r, characters vs views: **−0.109**. Pearson r, duration vs views: **+0.297**.

### What can and cannot be claimed

**Cannot claim:** that caps causes views. 33 vs 7 split, and the no-caps group has a
*higher median* (301,000 vs 222,870). The sample cannot separate these.

**Cannot claim:** that `DESTROY`/`EXPOSE` helps. The split runs the wrong way
(median 206,000 with vs 269,000 without, n=16/24). Most plausible reading is that those
words are the channel's older default and the newer titles diversified — not that the word
is harmful. Do not act on this.

**Weakly supported:** `When`-openers over-index (n=10, mean 372,345 vs 274,664; median
259,477 vs 219,500) — but the single 1.2M outlier is a `When` title, and removing it drops
the `When` mean to 280,383, at parity. **n=10 with one dominant outlier supports nothing.**

**The only claim the data supports on its own:** every one of the 40 titles obeys the hard
constraints in §3 — no digits, no names, no venue, no disposition, ≤77 chars — and the
channel's median video is 224,535 views at 192K subs. There is no counterexample in the set
of a long, name-and-venue title performing well, because **there is no long, name-and-venue
title in the set.** The formula's evidence is its uniformity, not a within-set correlation.

Also: the 66+ char bucket is the worst of four (mean 207,574, median 195,000, n=5). Weak,
but it is the only length signal present and it points the same direction as the ≤77 cap.

---

## 5. STEP 6 — Texas Trial Tracker, full inventory

Found at `https://www.youtube.com/@TexasTrialTracker` — channel id `UCT5Fde6OzBSFRmxw5mPn2CA`,
2,880 subscribers as reported by yt-dlp on 2026-08-11.

**The ~865K video is a Short, not a longform video** (`sp3IXJYBFwY`, 49s, 865,270 views).
Only listed under `/shorts`; it does not appear in `/videos`.

### Longform (13)

| id | date | dur (s) | views | title (verbatim) | chars |
|---|---|--:|--:|---|--:|
| y_43R2cDx-A | 2026-03-28 | 6745 | 16,944 | The Closing Argument That Sent Christopher Preciado to Prison For Life - Savanah Soto Murder Trial | 98 |
| 6V1pKKVR17k | 2026-03-27 | 1073 | 62,357 | Christopher Preciado Found GUILTY — Reaction & Family Impact Statements \| Savanah Soto Murder Trial | 99 |
| ztBrTKT2Gbk | 2026-03-26 | 513 | 37,843 | Savanah Soto Murder Trial Update: Deleted DMs Exposed a Killers Plan In Court \| Day 6 | 85 |
| VkgyONGqcGk | 2026-03-24 | 2853 | 16,270 | The Interrogation That Got Him Life Without Parole \| Christopher Preciado, Savanah Soto Murder Trial | 100 |
| Y-_2z7D65Rw | 2026-03-21 | 472 | 72,119 | Savanah Soto Capital Murder Trial \| DNA Evidence, Bloody Money & Courtroom Drama \| Day 4 | 87 |
| hpvtEyIqBao | 2026-03-19 | 402 | 11,848 | Savanah Soto Capital Murder Trial \| NEW Bodycam Footage Released \| Day 2 | 71 |
| mZDSXG_dt18 | 2026-03-18 | 941 | 4,516 | Savanah Soto Capital Murder Trial \| Opening Statements \| Day 1 | 61 |
| iaJQCLjtW6c | 2025-02-27 | 917 | 2,385 | Judge Boyd EXPOSES Credit Card Fraud Scheme | 43 |
| wpfuNO92PzE | 2025-02-25 | 733 | 1,414 | Judge Boyd SHUTS DOWN Gang Member's Request for Early Probation Release | 70 |
| 1vxNnl1ULv4 | 2025-02-22 | 1099 | 4,384 | Thug In Disbelief After Judge Boyd Sentences Him To Prison. | 58 |
| fDBeKRd8lxg | 2025-02-13 | 1429 | 3,084 | Judge Boyd Sentences Famous San Antonio Rapper "IZZY93" To PRISON! Both Cases | 76 |
| cSz-vkSwVlk | 2025-02-06 | 965 | 9,813 | Drug Dealer BEGS Judge Boyd To Not Send Him To Prison | 52 |
| o1S6Kbnckro | 2024-11-20 | 1238 | 4,692 | Teen Stole His Mom's PILLS Then SLAPS Her! Judge Fletcher Reacts Like This | 73 |

Longform total **247,669** views. Mean **19,051**, median **9,813**.

### Shorts (11)

| id | date | dur (s) | views | title (verbatim) |
|---|---|--:|--:|---|
| sp3IXJYBFwY | 2026-03-22 | 49 | **865,270** | Day 1: The family found them in a locked car — Savanah Soto Capital Murder Trial #shorts |
| dAI3GNmNt_s | 2025-01-30 | 58 | 61,359 | Family Starting Drama In Judge Boyds Court Room! WITH FULL NEWS STORY |
| upjOR9Tr0P8 | 2025-02-13 | 59 | 39,453 | Judge Boyd Sentences San Antonio Rapper "IZZY93" To PRISON! |
| oJvViwEhFyk | 2025-02-22 | 57 | 27,967 | Thug In Disbelief After Judge Boyd Sentences Him To Prison. |
| Usxub-MQm9k | 2025-02-04 | 60 | 22,618 | Judge Boyd Sentences Father Who STARVED his 10-Year Old Daughter |
| Zl0i8N8botY | 2025-03-08 | 58 | 16,513 | Stalker Ex Boyfriend BEGS Judge Boyd To Not Send Him To Prison |
| 9sPIAJDtrCY | 2024-11-20 | 59 | 7,920 | Teen Steals His Moms PILLS Then SLAPS Her! - Judge Fleischer Reacts Like This. #judgefleischer |
| Z6xw2FGUCsc | 2026-03-25 | 60 | 4,110 | Day 5 "The Angles Don't Match." Detective Catches Every Lie. \| Savanah Soto Capital Murder Trial |
| 78F7VBVbUps | 2025-02-07 | 60 | 2,897 | Drug Dealer BEGS Judge Boyd To Not Send Him To Prison |
| AQSXir0b4Tc | 2025-02-25 | 57 | 2,601 | Judge Boyd SHUTS DOWN Gang Members Request for Early Probation Release |
| 2fZLGdu5SPM | 2026-08-11 | 57 | 1,081 | Teen Shot His Friend In The Face — Judge Boyd Turns On His Mother #shorts |

Shorts total **1,051,789**. Mean **95,617**, median **16,513**. One video is 82% of it.

### Client vs competitor, side by side

| metric | Texas Trial Tracker | Audit the Court |
|---|---|---|
| titles measured | 24 (13 long + 11 short) | 40 longform |
| median chars (longform) | **74.0** | **55.0** |
| mean chars (longform) | 75.5 | 55.3 |
| max chars | **100** | 77 |
| longform titles >70 chars | **9/13 (69%)** | **4/40 (10%)** |
| contains a digit | 6/24 (`Day 1..6`, `10-Year`, `IZZY93`) | **0/40** |
| names a real person / case | **24/24** | **1/40** |
| names `Judge Boyd` | **13/24 (54%)** | **1/40 (2.5%)** |
| uses `\|` pipe separator | 7/24 | 0/40 |
| uses `:` colon | 3/24 | 0/40 |
| uses `"` quote marks | 3/24 | 0/40 |
| has ≥1 ALL-CAPS token | 13/24 (54%) | 33/40 (83%) |
| ALL-CAPS token position | scattered; often final (`To PRISON!`, `PILLS`) | median word index **2**, relative 0.31 |
| ends with `!` | 1/24 | 12/40 |
| ends with `.` | **2/24** | 0/40 |
| reveals the outcome | **11/24 (46%)** — `GUILTY`, `Prison For Life`, `Life Without Parole`, `Sentences… To Prison` | **0/40** |
| starts with `When` | 0/24 | 10/40 |
| contains `Cop`/`Police` | **0/24** | 22/40 |
| contains `Attorney`/`Lawyer` | **0/24** | 13/40 |
| contains `in Court` | 1/24 | 15/40 |
| `DESTROY`/`EXPOSE` verb | 2/24 | 16/40 |
| first word (top) | `Judge` 6, `Savanah` 4, `Teen` 3 | `When` 10, `Judge` 6, `Cop` 4 |

### The seven concrete differences

1. **Length.** Median 74 vs 55 chars; 69% of client longform titles exceed the ~70-char
   truncation point vs 10% of competitor's. Four client titles are 98–100 chars — every
   character past ~70 is invisible in search and suggested.
2. **The client titles a *case*; the competitor titles a *conflict*.** `Savanah Soto` appears
   in 9/24; `Christopher Preciado` in 3. Competitor names one person across 40 titles.
   A case name only works on viewers who already follow that case.
3. **Serialisation.** `Day 1`/`Day 2`/`Day 4`/`Day 5`/`Day 6` in 6/24. Day 1 got 4,516 views;
   there is no evidence viewers arrive at Day 4 without Day 1. Competitor has zero
   serialisation — every video is a standalone.
4. **Outcome revealed in 11/24.** `Found GUILTY`, `Sent Christopher Preciado to Prison For
   Life`, `Got Him Life Without Parole`, `Sentences Him To Prison`. Competitor: **0/40**.
   The competitor's entire mechanism is a named loser with an unnamed loss.
5. **No antagonist noun.** Client uses `Cop`/`Police` **0/24** and `Attorney` **0/24**;
   competitor uses them in 22/40 and 13/40. Client's villains are defendants
   (`Thug`, `Drug Dealer`, `Teen`, `Stalker Ex Boyfriend`, `Gang Member`) — that is the
   opposite side of the conflict from the one the competitor sells.
6. **Caps placement.** Competitor's caps token is a *verb* at median word index 2.
   Client's caps land on nouns and at the end (`To PRISON!`, `PILLS`, `NEWS STORY`,
   `GUILTY`, `STARVED`) — 11/24 have no caps at all.
7. **Judge Boyd is the client's lead, not the competitor's.** 13/24 client titles name her,
   6 of them as the first two words. The competitor names her once in 40. The client is
   spending its highest-value real estate on a proper noun that only converts viewers who
   already know who she is.

### One thing the numbers say that the brief did not assume

The client's single hit (865,270) is a **Short with a client-style title**:
`Day 1: The family found them in a locked car — Savanah Soto Capital Murder Trial #shorts`
— 87 chars, a colon, a case name, a serial marker, no caps, no `!`. It violates every rule
of the competitor's longform formula and outperformed the client's entire longform library
3.5×. Shorts and longform are different distribution systems; do not port that title's
lessons to longform, and do not assume the formula below is what produced it.

---

## 6. The template, as an operational spec

```
<[ADJ] ROLE-NOUN>  <VERB-IN-CAPS>  <OBJECT>  [and <CONSEQUENCE>]  [in Court]  [!]
     ^ word 0-1        ^ word 1-2 (median index 2)
```

Targets, from the measured distribution:
- **51–60 characters** (20/40 land here). Never exceed 70. Never exceed 77.
- **8–12 words** (median 10).
- **Exactly one all-caps token** in 19/40, two-plus only when they form one phrase
  (`LOSES IT`, `SHUTS DOWN`, `DID NOT GO WELL`).
- **Caps the verb**, at word index 1–3.
- **Role noun, not a name.** Cop > Attorney > Judge > Prosecutor by frequency.
- **Zero digits, zero venue, zero docket, zero colon, zero question mark, zero quote.**
- **Never state the ruling.** Promise the shape of the loss (`Backfires`, `Gets EXPOSED`,
  `REGRETS It`, `DOES NOT END WELL`), never the content of it.
- `in Court` as a closer is available in 15/40 and is the channel's setting anchor.
- `!` in 12/40 — optional, not load-bearing.
