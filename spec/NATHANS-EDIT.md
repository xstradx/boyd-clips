# How Nathan cut the spider monkey short

Recovered 2026-08-22 from `spidermonkeyshort.mp4` (his CapCut export) by matching
its Whisper transcript against the source transcript. 16 of 16 lines located,
match scores 0.86–1.00, so this is measured rather than inferred.

This is the only ground truth we have for his taste. Where it disagrees with what
the pipeline does, the pipeline is wrong.

## The shape

54.6s finished, built from **7 takes** out of a 456-second span (6227–6683).
That is an **8:1 compression** of the material.

| # | in the edit | length | from source |
|---|---|---|---|
| 1 | 0.0–13.2 | 13.2s | 6227 |
| 2 | 13.4–13.7 | **0.3s** | 6390 |
| 3 | 13.8–30.8 | 17.0s | 6249 |
| 4 | 31.0–33.9 | 2.9s | 6299 |
| 5 | 34.0–39.1 | 5.2s | 6391 |
| 6 | 39.5–45.8 | 6.3s | 6516 |
| 7 | 46.1–54.3 | 8.1s | 6675 |

Median take 6.3s. Shortest 0.3s, longest 17.0s.

## What he does that the pipeline does not

**1. He cuts more often, and much shorter.** Seven takes where our plans use
five, and his median take is 6.3s against our ~11s. The variance is the point:
a 17-second run and a 0.3-second stab in the same 55 seconds.

**2. He splices in a reaction as an interjection.** Take 2 is "So what?" — a
**0.3-second** stab lifted from 6390, dropped between material from 6244 and
6249. He reached two and a half minutes forward in the hearing to fetch a
three-word reaction and cut it in as a beat. Nothing in the pipeline does this;
Opus proposes whole moments in the 8–30s range and never a punch-in.

**3. He gives the hook a runway instead of opening cold.** Opus picked "Where is
Cash the spider monkey" (6232) as the hook and would open on it. Nathan starts
5 seconds earlier at 6227, on "So there are some things that I can just let
go" — the setup line — and lets it roll into the monkey demand. So the loop
opens with a wind-up, not a cold question.

**4. He reorders freely.** Take 3 goes back to 6249 after take 2 was at 6390.
Chronology is not preserved. This is legal in shorts and he uses it.

**5. He keeps almost only her.** 14 of 16 lines are Boyd. The defendant's total
contribution is two lines: "My brother had brought it" and "He has papers. He's
legal." He is a foil, not a participant.

**6. He adds B-roll.** A photograph of the spider monkey — in a balaclava and a
tactical vest — composited into the top-right of the defendant's tile with a
**red arrow** pointing at it. The pipeline has no concept of an insert. This is
probably the single biggest gap: the thing being talked about is shown.

**7. He stays inside one defendant.** Everything sits between 6227 and 6683, and
the second case starts at 6745. He did not cross it.

**8. He exports 2160x3840 at 60fps.** CapCut upscales our 1080x1920/30. No
practical benefit for a Short, but it is what his output looks like.

## What to change in the pipeline

* Let plans propose **short interjections** (< 1s), not only whole moments, and
  let them be pulled from anywhere in the hearing.
* Stop opening exactly on the hook moment. Offer a **runway** option that starts
  a few seconds before it, on the setup line.
* Target **6–8 takes** for a 55s short, with deliberately uneven lengths, rather
  than 5 even ones.
* Build a **B-roll insert** step — at minimum, a still image over one tile with
  an arrow, timed to the line that mentions it.
* Weight plans toward Boyd's lines; the defendant is there to be answered.
