# thumbeng — the thumbnail engine

Measures what a thumbnail actually *is*, harvests what a niche is doing right
now, works out what separates that niche's winners from its losers, and
critiques a candidate against it.

Everything here is public data and local pixels. No API key, no neural model,
no paid call. numpy / cv2 / sklearn / scipy only.

---

## The one-minute version

```bash
cd C:/Users/natha/Projects/boyd-clips

python tools/thumbeng/engine.py harvest  --channel UCT5Fde6OzBSFRmxw5mPn2CA
python tools/thumbeng/engine.py measure  --niche texas-trial-tracker
python tools/thumbeng/engine.py styles   --niche texas-trial-tracker
python tools/thumbeng/engine.py grammar  --niche texas-trial-tracker
python tools/thumbeng/engine.py critique --image "D:/Boyd Clips/READY-TO-POST/MONKEY_thumbnail_V2.jpg" --niche texas-trial-tracker
```

or the whole chain in one:

```bash
python tools/thumbeng/engine.py all --channel UCT5Fde6OzBSFRmxw5mPn2CA \
       --image "D:/Boyd Clips/READY-TO-POST/MONKEY_thumbnail_V2.jpg"
```

and to see what has run without opening anything:

```bash
python tools/thumbeng/engine.py status
```

---

## Read this before you believe a number

**On a 16-video channel this engine produces NO findings, and that is the
correct answer.** Verified on Texas Trial Tracker, 2026-08-31:

```
confidence: NONE
groups: 6 winners (>=1.50x own-channel pace), 6 losers (<=0.80x), 2 discarded middle
!! SAMPLE TOO SMALL: 6 winners / 6 losers, need >= 8 in each.
   Every rule is reported with meaningful=False. Nothing in this grammar is a finding.

-- WHAT WORKS RIGHT NOW ------------------------------------------------------
  no rule cleared sample size + effect size + FDR.
  That is a finding about the sample, not about design.
```

Sixteen videos split into 6 winners and 6 losers. `MIN_GROUP` is 8. So the
grammar reports every one of its 126 tested keys as `meaningful=False` and the
critique that consumes it says so on its own second line. If you want measured
niche rules rather than heuristics, harvest a **query** across many channels,
not one small channel.

A grammar's `confidence` is `none`, `weak` or `moderate`. It is never
`strong`, by design — see "What it cannot know" below.

---

## What each module does

| module | writes | one line |
|---|---|---|
| `__init__.py` | — | paths, slugs, atomic JSON/JSONL/CSV, `run.json` manifest. No image work. |
| `harvest.py` | `thumbs/`, `harvest.jsonl`, `channels.json` | finds videos, pulls thumbnails, scores each against its **own channel's** normal pace |
| `measure.py` | `measurements.jsonl`, `.csv` | turns any image into the frozen 133-key vocabulary |
| `styles.py` | `styles.json` | clusters those vectors into the niche's recurring looks |
| `grammar.py` | `grammar.json` | what separates winners from losers, with the honesty gates |
| `critique.py` | `critique/<stem>.json` | scores a candidate, returns ranked actionable defects |
| `engine.py` | `run.json` | the single CLI that chains all of it |

### `harvest.py` — where "what works right now" comes from

Drives `yt-dlp` for listings (metadata only, never video) and plain HTTPS for
thumbnails. `https://i.ytimg.com/vi/<id>/maxresdefault.jpg` needs no key.

The number it produces is `outlier_score` = this video's views-per-day divided
by **its own channel's median views-per-day**, over settled videos only,
leave-one-out.

- *views-per-day*, not raw views, because raw views conflate "good thumbnail"
  with "published three years ago".
- *ratio to its own channel*, because 200k views on a 5M-sub channel is a flop
  and 200k on a 2,880-sub channel is a phenomenon. Subscriber count is the
  confound this removes.
- *leave-one-out*, because dividing a video's pace by a median that contains
  that video understates it — measured 16.67x vs a true 20.00x on a 5-video
  channel.
- *settled only* (7+ days), because a video published yesterday has not
  settled its pace, and including it inflates its own score and deflates every
  sibling's.

Below 5 settled videos a channel median is noise and `outlier_score` is `NaN`
rather than a number you might believe. A channel seen only through a search is
marked `search_only` and refused as a baseline — its median would be a median
of its own winners, so every ratio against it lands near 1.0.

### `measure.py` — the shared vocabulary

Every image is resized to a canonical 1280x720 before anything is measured
(the metrics are explicitly not scale-invariant), then every geometric key is
normalised to a fraction of the frame.

133 keys across: provenance, face, luminance, colour, palette, edge/detail,
saliency, text-like regions, **downscale survival**, and balance. Plus five
`tm_*` keys carried through from the existing `thumb_metrics.py` so critique
can speak `verify_thumb.py`'s exact language.

De-letterboxing is mandatory and done by **aspect arithmetic**, never by
detecting dark rows — a legitimately dark court thumbnail must not be eaten by
a darkness detector. (`hqdefault.jpg` is 480x360 with 45 black rows top and
bottom; `maxresdefault` / `hq720` / `mqdefault` are native 16:9.)

Exactly one set of keys may be `NaN`, and only when `face_count == 0`.
`face_count` and `face_area_frac_total` are `0.0` and never `NaN` — a faceless
thumbnail genuinely has zero face area, and NaN-ing it would silently drop
faceless thumbnails from the comparison, which is exactly the finding a court
creator most needs.

### `styles.py` — the recurring looks

KMeans on RobustScaler-scaled features. Robust (median/IQR) rather than
mean/std because one blown-out white thumbnail in the set would otherwise
squash everything else toward zero. The fitted scaler is serialised into
`styles.json` so a candidate months later is projected into exactly the space
the clusters were built in, never refitted on a population of one.

It labels a cluster ("big-face, high-contrast, warm"). That is a
**description, not a diagnosis** — whether a look works is `grammar.py`'s job
and nothing else's. A cluster with fewer than 4 scored members gets no rank and
no median outlier.

Auto-`k` needs at least 10 measured thumbnails. Below that, pass `--k`
explicitly or the stage refuses and says so.

### `grammar.py` — the honesty module

For each of 126 tested keys it reports the winners' range against the losers'.
A rule is `meaningful` **only** when all four hold:

1. `n_win >= 8` and `n_lose >= 8`
2. `|Cliff's delta| >= 0.33` (a nonparametric effect size — these
   distributions are skewed and small-n, so a t-test's assumptions do not hold)
3. Benjamini-Hochberg FDR `q < 0.05` across all tested keys
4. it survived both of the above together

Point 3 is the whole point. 126 simultaneous tests at alpha 0.05 produce
roughly 6 fake findings on pure noise; the module's own selftest asserts that
FDR buries 130 pure-noise keys. `critique.py` may never raise a defect from a
non-meaningful rule.

Target bands are the winners' **interquartile range**, not their min/max — the
middle half of what worked is something you can aim at; the full range includes
the one weird thumbnail that won anyway.

### `critique.py` — the part you actually read

Every defect carries its provenance, and the renderer prints the tag:

| tag | means |
|---|---|
| `[measured n=14/11, delta +0.61]` | a grammar rule measured on this niche's harvest |
| `[gate, verify_thumb thresholds]` | inherited from `verify_thumb.py`, whose approved set is n=2 |
| `[heuristic, unvalidated]` | a general design principle with **no threshold measured on this machine** |

If no measured rule contributed, the report says so above the defect list:

```
!! no MEASURED rule contributed: every defect below is a heuristic or an
   inherited gate, so the score and the verdict are opinions with numbers
   attached, not findings
```

The 12 principles (text legibility at grid size, single read, text-on-face,
detail survival, crop safety, …) are honest heuristics. The `10px` minimum
readable cap height and the `20px` recognisable face are **assumptions stated
as assumptions**, not measurements from this machine.

**The pre-delivery scope rule.** `verify_thumb.py` measured that 10 of 12
competitor thumbnails trip the posterisation gate purely because YouTube
re-encodes them (quantisation table sum 736 vs 369 for a local export). So
`tm_flat_g_p90` and `tm_poster_fa` may raise a defect only when
`source_kind == "local"`; on a `youtube` row they are demoted to a
zero-severity diagnostic. Measured on the same pixels
(`thumbs/o1S6Kbnckro.jpg`):

| source_kind | score | verdict | posterisation |
|---|---|---|---|
| `local` | 39.0 | rebuild | counted as a defect |
| `youtube` | 60.0 | fix | diagnostic only, no severity |

The engine therefore **infers** `source_kind` from the path — anything under a
niche's `thumbs/` came from harvest and is `youtube`; anything else is `local`.
Override with `--source-kind`.

---

## How they chain

```
harvest ──► thumbs/, harvest.jsonl, channels.json
              │
measure  ──► measurements.jsonl, measurements.csv        (joins on video_id == image_id)
              │
styles   ──► styles.json          (optional input to grammar, not a prerequisite)
              │
grammar  ──► grammar.json
              │
critique ──► critique/<stem>.json
```

Exactly one module writes each file. No module reads a file another module has
not finished writing. Every stage stamps itself into `run.json`, which is what
`engine.py status` reads.

Everything lives under `work/thumbeng/<niche-slug>/`. Every stage addresses its
work by **niche name**, never a raw path.

---

## Exact commands

### harvest

```bash
# one channel — niche name is derived from the channel's real name
python tools/thumbeng/engine.py harvest --channel UCT5Fde6OzBSFRmxw5mPn2CA
#   -> niche: texas-trial-tracker

# a whole niche across many channels (this is what gives grammar enough n)
python tools/thumbeng/engine.py harvest --niche court \
       --query "courtroom judge sentencing" --limit 60

# search + the back catalogue of every channel that appeared
#   (deepening is ON by default and is what makes outlier scores possible)
python tools/thumbeng/engine.py harvest --niche court --query "judge sentencing" \
       --limit 60 --baseline-limit 60
```

`--no-deepen` skips the per-channel baseline pass. It is fast, and every
outlier score from a search then stays `NaN` — a search never surfaces a
channel's flops, so without the second pass there are no losers.

### measure

```bash
python tools/thumbeng/engine.py measure --niche texas-trial-tracker
python tools/thumbeng/engine.py measure --dir "D:/Boyd Clips/READY-TO-POST"
python tools/thumbeng/engine.py measure --dir "D:/Boyd Clips/READY-TO-POST" --pattern "*.jpg"
```

`--dir` defaults to jpg/jpeg/png/webp. Narrow it with `--pattern "*.jpg"` on
`READY-TO-POST`, which mixes real thumbnails with PNG **contact sheets** —
`AB_THUMBNAILS.png` measures 30 faces and
`COURTROOMTIME_WINNERS_vs_LOSERS.png` measures 58, because they are grids of
thumbnails, not thumbnails.

Re-measuring is cheap: a cached row is reused only when its `image_sha1` **and**
`schema_version` still match, so re-exporting a thumbnail over itself
re-measures it rather than returning the replaced file's old numbers.

### styles / grammar

```bash
python tools/thumbeng/engine.py styles  --niche court            # auto-k, needs n >= 10
python tools/thumbeng/engine.py styles  --niche court --k 3      # force k
python tools/thumbeng/engine.py grammar --niche court
python tools/thumbeng/engine.py grammar --niche court --win 2.0 --lose 0.7
```

### critique

```bash
# one candidate
python tools/thumbeng/engine.py critique --image "D:/x/THUMB.jpg" --niche court

# A/B — "which of these two do I post"
python tools/thumbeng/engine.py critique --niche court \
       --image "D:/x/THUMB.jpg" --image "D:/x/THUMB_V2.jpg"

# before any harvest exists: general principles only, clearly labelled
python tools/thumbeng/engine.py critique --image "D:/x/THUMB.jpg"
```

### everything else

```bash
python tools/thumbeng/engine.py all --channel UC... --image "D:/x/THUMB.jpg"
python tools/thumbeng/engine.py status                 # every niche
python tools/thumbeng/engine.py status --niche court   # one niche
python tools/thumbeng/engine.py selftest               # all five modules
```

Exit codes: `0` ran, `2` refused (bad arguments or a missing prerequisite),
`1` crashed. Each module also keeps its own CLI
(`python -m tools.thumbeng.grammar --selftest`).

---

## What the engine CANNOT know

Be blunt about this. The engine is built so its output cannot be mistaken for
more than it is.

**No CTR. No impressions. No watch time. No audience retention.** Not for any
channel but Nathan's own. Those live behind YouTube Analytics, which requires
authentication as the channel owner. There is no YouTube Data API key on this
machine and this engine never asks for one. Everything here is derived from
public view counts and public thumbnail JPEGs.

*Click-through rate is the thing a thumbnail actually controls, and this engine
cannot see it for anyone else.* `outlier_score` is the closest honest proxy
available from public data, and it is a proxy for **the whole video package**.

**It cannot attribute anything to the thumbnail.** `outlier_score` measures a
video's pace against its own channel's norm. It removes the subscriber-count
confound and *nothing else*. Title, topic, upload timing, the case being
newsworthy, and the algorithm are all still in there. Every grammar rule is a
correlation in a small observational sample, never a cause.

**The sample is small and biased.**
- 16 videos on Texas Trial Tracker → 6 winners / 6 losers → below `MIN_GROUP=8`
  → zero meaningful rules. Correctly reported as `confidence: none`.
- Search results are ranked by YouTube's own relevance, which is itself a
  popularity signal, so a search-harvested set is biased toward winners. That
  bias is stated in the run manifest, not hidden.
- `n_distinct_channels` matters independently of `n`: 30 winners drawn from two
  channels measures those two channels, not the niche. The grammar caps
  `confidence` at `weak` below 4 distinct channels.
- Clustering 16 thumbnails in 107 dimensions is arithmetic, not evidence.
  `styles.py` says so on its own output and names the ~535 thumbnails the
  geometry would need.

**Dates are approximate.** The flat listing that makes harvesting fast returns
dates that can be ~18h out (measured: 20260828 vs a true 20260827). Good enough
for `age_days`, and recorded as `date_is_approximate=True`. Never present one
as an exact publish date.

**Most thresholds are conventions, not measurements.** `MIN_GROUP=8`, the
1.5x/0.8x win/lose split, `EFFECT_MIN=0.33` (Romano's mapping of Cohen's
benchmarks — a convention adopted, not measured here), the 80/50 ship/fix/rebuild
verdict bands, and all 12 principle thresholds. Each is labelled as a judgement
call where it is defined. The measured numbers on this machine are the
de-letterbox geometry, the YouTube re-encode quantisation gap, and the
`survive_*` downscale behaviour.

**`confidence` never reads `strong`.** No sample this pipeline can gather from
public data separates thumbnail effect from title and topic. That word is not
in the vocabulary.

### What CAN see the real numbers

For Nathan's **own** channels there is a separate tool: the `youtube-channel`
skill pulls real views, watch time, CTR and audience-retention curves for
Texas Trial Tracker and stradawrld, because those are authenticated. Use that
to check whether a thumbnail this engine liked actually performed. This engine
is for reading *other people's* thumbnails, which is exactly the case where the
real numbers are unavailable.

---

## Environment (verified 2026-08-30/31)

python 3.14.2 · numpy 2.5.2 · cv2 5.0.0 (ximgproc, FaceDetectorYN, MSER) ·
sklearn 1.9.0 · scipy 1.18.0 · PIL · requests 2.33.1

- **pandas is NOT installed.** Every table is stdlib `json` + `csv`.
- **torch is not on this interpreter.** No neural embeddings anywhere.
- `numpy 2.5` removed `ndarray.ptp()` — use `np.ptp(a)`.
- Face model is `models/yunet2023.onnx` and nothing else. `models/` also holds
  `yunet.onnx` and `face_detection_yunet_2026may.onnx`; a different model
  changes every face number and `thumb_metrics`/`verify_thumb` were derived
  against the 2023 one.
- `yt-dlp` at `C:/Users/natha/miniconda3/Scripts/yt-dlp.exe`. Video downloads
  currently 403 — irrelevant, this engine only reads metadata and JPEGs.

**Import discipline.** `tools/harvest.py` already exists and is an unrelated
courtroom-frame harvester. `thumbeng` is a package; modules reach the legacy
`thumb_metrics` / `verify_thumb` / `comp_pro` only after appending (never
prepending) `tools/` to `sys.path`, so `tools/harvest.py` can never shadow
`tools/thumbeng/harvest.py`. Both `python -m tools.thumbeng.engine` and
`python tools/thumbeng/engine.py` work.

`SCHEMA_VERSION = 1` is stamped into every row. Any loader that meets a
different version raises rather than silently mixing vocabularies.
