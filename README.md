# Boyd Clips

Automated daily clipping of Judge Stephanie Boyd's 187th District Court
livestream ([`@judgestephanieboyd4233`](https://www.youtube.com/@judgestephanieboyd4233/streams)).

Each run produces **one long-form video** of a full case and **one vertical
short** cut from inside it, with the short's description pointing back at the
long-form. Shorts feed long-form; that's the funnel.

---

## How it works

```
discover     list new streams                       metadata only, ~2s
   ↓
transcribe   YouTube auto-captions → word timings   free, no video downloaded
   ↓
segment      split the docket into individual cases  Claude
   ↓
gate + score safety rules first, then the rubric     Claude
   ↓
select       highest-scoring case that clears every gate
   ↓
render       download ONLY that case's minutes, cut, caption
   ↓
publish      long-form first → URL → short          gated by autonomy.mode
```

**The design decision that matters most:** captions are fetched without
downloading video. A 3-hour docket is analysed as ~40k tokens of free text, and
only the 5–15 minutes that actually get published are ever downloaded. Running
the other way round would mean ~15 GB/week of video to find one good case.

---

## Setup

```powershell
cd C:\Users\natha\Projects\boyd-clips
python -m pip install -e .

copy config\.env.example config\.env
# add your ANTHROPIC_API_KEY to config\.env

python -m boydclips.cli doctor
```

`doctor` checks yt-dlp, ffmpeg (including libass, needed for burned-in
captions), the Anthropic SDK, credentials, and your config. Do not schedule
anything until it reports `ready`.

**Keep yt-dlp current.** A five-month-old yt-dlp silently returned only 360p
for this channel while 720p was available — `run_daily.ps1` self-updates it on
every run for exactly this reason.

### Daily schedule

```powershell
schtasks /create /tn "BoydClips" /sc daily /st 19:40 /f `
  /tr "powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\natha\Projects\boyd-clips\run_daily.ps1"
```

19:40 is deliberate — afternoon dockets have ended and YouTube's auto-captions
have usually landed. Running earlier means analysing a docket whose captions
don't exist yet.

---

## Commands

| Command | What it does |
|---|---|
| `boyd doctor` | Environment and config check |
| `boyd discover` | List new dockets, touch nothing else |
| `boyd run --dry-run` | Analyse and select, download and render nothing |
| `boyd run` | The full pipeline |
| `boyd approve <case_key>` | Record approval; publishes when mode allows |
| `boyd reject <case_key> --reason "..."` | Record rejection (`--safety` if safety-related) |
| `boyd stats` | Reliability ledger and autonomy promotion readiness |
| `boyd bank` | Qualifying runner-up cases held for slow days |
| `boyd auth youtube` | One-time OAuth |

---

## The files you'll actually edit

| File | Controls |
|---|---|
| `spec/SPEC.md` | **The contract.** The product, what makes a clip gold, selection, format, packaging. Wins over everything else |
| `spec/SAFETY_RULES.md` | What must never be published, and why. Outranks SPEC on safety |
| `config/pipeline.yaml` | Every threshold, duration, format, and platform switch |
| `prompts/*.md` | What the model is asked, versioned |
| `spec/CONTENT_SPEC.md`, `spec/PACKAGING.md` | Subordinate specs. Still read by the tests and the packaging prompt |

`docs/reference/` is research and binds nothing. `docs/archive/` is superseded —
do not plan from it. See `spec/SPEC.md` §6 for the full order of authority.

Code doesn't hardcode policy. If output drifts, the fix belongs in one of
these — and because prompt versions are stamped into every clip's manifest, you
can always tell which version produced a given clip.

---

## Autonomy

`autonomy.mode` in `config/pipeline.yaml`:

- **`manual`** (current) — renders everything to `out/review/<date>_<id>/`,
  publishes nothing. Each folder has a `REVIEW.txt` and a `manifest.json`.
- **`assisted`** — uploads as private/draft; you flip to public.
- **`auto`** — publishes with no human in the loop.

### Earning `auto`

Every `approve`/`reject` writes to the ledger, so promotion is a measurement
rather than a feeling. `boyd stats` reports against the gate in config:

```
min_consecutive_approvals: 30
max_safety_rejects: 0
```

Reject with `--safety` when the problem was a safety-rule miss rather than a
taste call. One safety miss resets the case for autonomy entirely — that
asymmetry is the point.

---

## Safety

These are real people, mostly presumed innocent, on the worst day of their
lives. The system enforces `spec/SAFETY_RULES.md` as a **hard gate before
anything is downloaded**: juveniles, sexual-offense victims, third-party
identifiers, jury material, and clips whose drama is someone's mental-health
crisis or poverty are dropped outright.

The rule that catches the most cases is R7 — *the clip must be honest standing
alone*. Courtroom exchanges routinely look outrageous once the surrounding
twenty minutes are removed, and the most misleading cut is frequently the most
engaging one. The model is instructed that **uncertainty resolves to
rejection**: a false reject costs one day's clip, a false accept can cost
considerably more.

Every clip writes a `manifest.json` with exact source timestamps, the full
scoring breakdown, the safety determination and its reasoning, and the model
and prompt versions used — so any published clip can be reconstructed and
explained in one step.

---

## Video treatment

The court's encoder bakes black bars into its own 16:9 frame, and the layout is
usually a side-by-side two-participant Zoom view. Naive handling produces a
short where the courtroom occupies about 15% of the screen.

`vertical_mode: auto` handles this: `cropdetect` strips the baked-in letterbox,
then content wider than 2.2:1 is treated as a 2-up and the tiles are **split and
stacked** — same pixels, roughly four times the screen coverage. Anything else
falls back to a blurred-fill letterbox. Captions are placed in whatever band the
chosen layout leaves free.

Center-crop exists as an option but will cut participants out of frame; it is
not the default for good reason.

---

## Cost

Measured against real transcripts from this channel (claude-opus-5,
`effort: high`):

| Docket | Transcript | Cost |
|---|---|---|
| 52 min | 4.7k tokens | $0.38 |
| 108 min | 18k tokens | $0.52 |
| 171 min | 28k tokens | $0.61 |

A typical two-session day is about **$1.00**. Roughly $30/month.

**Output tokens dominate** — ~12k out per docket at $25/1M costs more than the
input on shorter dockets. If you want this cheaper, `analysis.effort` is the
lever, not transcript size; dropping the segmentation stage to `medium` is the
obvious first try.

Cross-call prompt caching does *not* apply, despite the `cache_control` block
in `analyze.py`: caching is a prefix match over `tools → system → messages`,
and each stage sends a different system prompt, so the prefix diverges before
the transcript is reached. Unifying the three system prompts behind a shared
cached prefix would make the transcript reusable — worth doing if cost matters,
not done yet.

Transcription is free. Bandwidth is a few hundred MB/day rather than several
GB, because only the published case is ever downloaded.

---

## Status

Verified working end to end against the live channel: discovery, caption
fetching and word-timing parse, section download, long-form and short renders,
word-highlight captions, letterbox detection, and tile stacking.

**Not yet exercised:** the three Claude calls, which need `ANTHROPIC_API_KEY`
set in `config/.env`. Run `boyd run --dry-run` first — it analyses and selects
without downloading or rendering anything.

**Not implemented:** TikTok and Instagram publishing. Both need platform
approval that hasn't happened yet, and Instagram additionally requires the video
at a public HTTPS URL (the Graph API won't take a file upload). The adapters
raise with setup instructions rather than failing silently, and one
unconfigured platform never blocks the others.
