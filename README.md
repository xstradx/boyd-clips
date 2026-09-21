# Boyd Clips

Automated daily clipping of Judge Stephanie Boyd's 187th District Court
livestream ([`@judgestephanieboyd4233`](https://www.youtube.com/@judgestephanieboyd4233/streams)).

The target is **one long-form video** and **one vertical Short** from the same
best available case each day. One global daily limit covers all new dockets and
the unproduced case bank. Production remains in manual review mode. See the
[September 12 build record](docs/DAILY-V1-BUILD-2026-09-12.md) for exact limits,
proof, and what will happen on the next run.

---

## How it works

```
lead scan    inspect six recent competitor clips    metadata + captions only
   ↓         match exact phrases to original court footage
discover     list new original streams              metadata only
   ↓
transcribe   YouTube auto-captions → word timings   free, no video downloaded
   ↓
segment      split the docket into individual cases  DeepSeek V4.1 Flash
   ↓
gate + score safety rules first, then the rubric     DeepSeek V4.1 Flash
   ↓
select       global best eligible case or strongest unproduced bank case
   ↓
plan         Producer/Shorts Brain + three paired title/thumbnail concepts
   ↓
render       download ONLY original court minutes, cut, caption, QC
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

codex login

python -m boydclips.cli doctor
```

`doctor` checks yt-dlp, ffmpeg (including libass, needed for burned-in
captions), the configured backend, credentials, and your config. Astra is the
project orchestrator. Bounded workers run through `scripts/deepseek_worker.py`;
isolated production calls use DeepSeek V4.1 Flash through API name
`deepseek-flash`; no Anthropic key is needed. Image generation uses a separate
tool and allowance. A healthy environment does not prove
editorial or unattended production readiness; follow the audit's staged gates.

For one bounded worker task, pipe the complete assignment to
`python scripts/deepseek_worker.py`. For independent work, pass a JSON array of
`id`, `task`, `effort`, and `sandbox` fields to
`python scripts/deepseek_workers.py MANIFEST --output-dir OUTPUT`. The batch
runner caps concurrency at eight, saves each final message and log, and requires
Astra to inspect the live result. Eight is a ceiling, not a default.

**Keep yt-dlp current.** An old build once returned only 360p while 720p was
available. The daily driver does not upgrade software during a production run;
update yt-dlp separately after testing the update.

### Daily schedule

The repository includes the guarded driver below, but this task does not install
the schedule automatically. Install it only after a reviewed live rehearsal:

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
| `boyd run --dry-run` | Rank locally banked cases only; zero discovery, model, download, or render work |
| `boyd run` | The full pipeline |
| `boyd approve <case_key> --concept A|B|C` | Bind approval to one exact title-thumbnail pair and artifact hashes |
| `boyd reject <case_key> --reason "..."` | Record rejection (`--safety` if safety-related) |
| `boyd stats` | Reliability ledger and autonomy promotion readiness |
| `boyd bank` | Qualifying runner-up cases held for slow days |
| `boyd auth youtube` | One-time OAuth |
| `boyd release-check <packet>` | Verify the selected long-form and thumbnail for manual Studio release; no production or upload |

`release-check` reads an existing release JSON packet and checks its exact video/thumbnail hashes, media, title, description and Not Made for Kids setting. It reuses the selected files without requiring a Short or unselected A/B/C arms. `local_files_verified` is an integrity result, not editorial approval, upload or scheduling confirmation. The full-package/API release checks remain unchanged.

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

## Limits and usage

Each run is capped at one complete long-form/Short pair, 20 model calls,
one attempt per call, six competitor leads, and nine generated thumbnail
images. Starting another A/B/C set requires at least three images left. Exhausted
technical budgets return a failed-run signal; an honest editorial `HOLD` or weak
case returns a clean skip. Every run writes the call records, prompt/input hashes,
reported image count, candidates, failures, and output paths to
`logs/daily-runs/`. Token counts and cost stay `null` until measured data exists.

---

## Status

The daily V1 control path is proved offline: global selection and fallback,
competitor matching, one canonical case story, Producer/Shorts Brain handoff,
three paired packaging candidates, readiness hashes/QC, resumable delivery,
hard usage caps, zero-usage dry-run behavior, and a single-run process lock.

**September 19 model routing:** `gpt-6-astra` orchestrates. Project workers,
analysis, Producer Brain, and thumbnail direction use DeepSeek V4.1 Flash
(`deepseek-flash`). No Claude or Sol fallback is enabled. A fresh unattended
render on this exact routing is still unproven. `autonomy.mode` remains `manual`,
the YouTube API audit flag remains false, and no schedule has been installed;
therefore the next run can attempt a local review bundle but cannot public-post.

**Not implemented:** TikTok and Instagram publishing. Both need platform
approval that hasn't happened yet, and Instagram additionally requires the video
at a public HTTPS URL (the Graph API won't take a file upload). The adapters
raise with setup instructions rather than failing silently, and one
unconfigured platform never blocks the others.
