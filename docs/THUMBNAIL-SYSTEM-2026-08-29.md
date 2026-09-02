# The thumbnail system — what exists, what to build

Five disjoint non-introspective specialists, 2026-08-29. Every claim below has a
fetched source or a command output. Nathan's ask, verbatim: *"something
intelligent"* that scores, says what is wrong, fixes it and does it
automatically — the way **Pikzels** did.

---

## The finding that matters most

**The automated pipeline does not run the thumbnail Nathan approved.**

- `src/boydclips/thumbnail.py:48` — `BUILDER = ROOT / "scripts" / "make_thumbnail_v2.py"`
- `src/boydclips/pipeline.py:549` — the comment above the call says *"produces the
  construction Nathan approved on"*
- `STATE.md:75` — what he actually approved is Q3: *"q3 thumbnail is fire"*,
  `scripts/thumb_Q3_detail.py`
- `grep -rn "thumb_Q3_detail\|make_thumbnail_auto" src/` → **zero hits**

So the construction he picked is unreachable from the thing that runs
unattended, and the code comment asserts the opposite. This is the mechanical
cause of "it's just slop": what ships is not what he chose. Fixing this is a
restructure, not a patch, and it is the highest-value single change in the repo.

## Both live thumbnails fail the repo's own scorer

Re-run directly, not taken from an agent:

```
$ python scripts/verify_thumbnail.py "READY-TO-POST/1_LONGFORM_thumbnail.jpg"
FAIL 1_LONGFORM_thumbnail.jpg
   - ARROW_AIMS_AT_NOTHING the ray from the tip reaches no face - it points at empty background
   - CHROMA_BLOCKING flat bright area deviates 3.7 from neutral (clean is ~1.3)
0/1 passed
```

`thumb_eval.py --score`: **1_LONGFORM 62.5/100 REJECT**, **MONKEY 83.9/100 REJECT**.
Thompson's `survival210 = 0.33` — only a third of its type survives at feed size.
Monkey's hard fail is `text_on_face_frac = 0.081`.

`thumb_eval.py`'s own message on that metric: *"our shipped 1_LONGFORM_thumbnail
scored 0.12 and Nathan called it horrible. this is his complaint expressed as a
number."* **The repo already encoded his complaint as a metric, and then shipped
a thumbnail that violates it.**

## What the outside world has — searched, not recalled

**Pikzels is alive and scriptable.** `api.pikzels.com/v2`, `X-Api-Key` header,
documented **Score endpoint** ("main score with subscores": Virality, Clarity,
Idea, Curiosity, Emotion), plus create-from-text, create-from-image, edit,
one-click-fix. $40/mo, or $28/mo billed annually; an analysis costs 5 credits.
Sources: pikzels.com/pricing, docs.pikzels.com/quickstart, docs.pikzels.com/llms.txt.
It is the **only** product in the category with working public REST docs —
TubeBuddy has no public API, Thumblytics is a $999/mo human service, Pictiny and
CreatiCalc are browser-only.

**YouTube's own Test & Compare** (support.google.com/youtube/answer/16391400):
up to 3 variants, resolves within two weeks, winner chosen on watch-time-per-
impression, desktop Studio only, **not available for Shorts**, and **no API** —
so it cannot be part of an unattended routine.

**GitHub has nothing that closes the loop.** Every repo calling itself a
thumbnail "scorer" is an LLM critiquing text against a static style guide, not
computer vision against pixels. The closest functional match,
`jayadevrana/youtube-mcp-server`, is source-available at **$1,000/year** and
macOS-only. Searches that returned nothing real: `"thumbnail ctr prediction"`
(2 results, both spam), npm and PyPI for CTR/aesthetic scoring (zero),
`awesome-youtube-automation` (does not exist).

**No model predicts CTR from a thumbnail image.** Measured absence, not an
unsearched gap. The one public attempt (`codencoding/Red-Means-Go`) found
thumbnail pixel features performed *worse than predicting the mean*.

## The eye we can actually run, locally and free

| what it sees | model | licence | note |
|---|---|---|---|
| where the eye lands first | **MSI-Net** | MIT | `from_pretrained_keras("alexanderkroner/MSI-Net")` |
| technical quality | **NIMA** | Apache-2.0 | aesthetic + technical heads |
| face reads as high-arousal | **RetinaFace → HSEmotionONNX `enet_b0_8_va_mtl`** | MIT / Apache-2.0 | continuous valence AND arousal |
| survives feed size | OCR-confidence at 168x94 + WCAG contrast | deterministic | no model exists for this — confirmed absence |

Avoid **pyiqa** (PolyForm **Noncommercial** — unusable on a monetised channel)
and **DeepGaze IIE** / **TranSalNet** (no stated code licence).

These are tens of MB and run in milliseconds on the 5080. That matters because a
repair loop scores the same thumbnail 20+ times; locally that is free.

## What the community actually says (so we do not "fix" the wrong thing)

- **Arrows and cut-outs are NOT dead.** No source calls the motif dead. One
  creator's own CTR breakdown has a big clean arrow in a **7.8% CTR winner** and
  a *"near invisible weird AI arrow"* in a **3.7% loser**. It is execution, not
  the motif. **Do not throw away the current construction.**
- **The one strong consensus mock is AI-looking thumbnails** — "uncanny valley",
  "you can always tell", 4+ independent commenters, no dissent. Real courtroom
  footage is an advantage here, not a constraint.
- **1-3 focus points maximum** — the most-repeated independently-arrived-at rule.
- **Score at the rendered size, not the canvas.** ThumbnailPeak's public teardown
  (2026-08-26) evaluates legibility at **168x94**. Our Thompson thumbnail scores
  0.33 survival at 210px.
- Practitioner-normal CTR: *"5-10% is VERY GOOD, 2-5% is also good."*
- Honest gap: **no courtroom/true-crime-specific critique threads exist** with
  real depth. The niche evidence is two hiring posts, which do name two competing
  lanes — *"gritty, true-to-footage"* vs *"fully cinematic and stylized"*. That
  is a real editorial fork and nobody has chosen ours.

## Recommendation

**Build the loop here; do not buy a judge.** The repo already owns the two hard
parts — a weighted SHIP/WEAK/REJECT scorer calibrated on 37 rows of THIS niche's
winners vs losers, and four builders that each expose the exact flag
(`--sat-gain`, `--target-luma`, `--arrow-scale`, `--max-shift`, `--top-adjust`)
that fixes a given failure. Nothing on the market or on GitHub connects them.
Pikzels' score is generic-YouTube and cannot know that the arrow must point at
*the defendant*.

Order of work:
1. **Rewire the automated path to the approved builder.** Structural, cheap,
   and until it is done every other improvement ships into a dead branch.
2. **Close the loop**: read the verifier's named FAIL, map it to the builder flag,
   re-render, re-check, stop at SHIP or after N attempts. All parts exist.
3. **Add the local eye** (saliency + arousal + feed-size OCR) as new gates, so
   the loop optimises where the eye lands, not just luma and chroma.
4. **Wire in the 85-image panel findings**, which currently live only in
   `THUMBNAIL_VERDICT.md` and are enforced by nothing.
5. **Then** consider Pikzels at $28/mo as an external second opinion — not judge.

## Still Nathan's call, not mine

- **Loud vs quiet construction.** STATE.md has flagged this undecided since
  2026-08-29 and both workflows optimised the loud one by default.
- **Gritty vs cinematic**, the fork the niche's own hiring posts name.
- **Whether to spend on Pikzels at all.**
