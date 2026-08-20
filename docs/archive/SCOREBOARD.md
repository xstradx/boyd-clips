# Scoreboard — Boyd Clips

Read this first. It is the only honest answer to "are we going forward?"

Numbers only. A number that goes down is a finding, not a failure to explain
away.

| metric | meaning |
|---|---|
| **published** | clips live on the channel. The only one that pays. |
| **eligible/docket** | cases clearing the gate. Zero = the pipeline is stuck. |
| **safety rejects** | dropped by the gate. High = gate is miscalibrated. |
| **top score** | best case found. Rising = better picks available. |
| **analysis failures** | dockets lost to malformed JSON. Should be 0. |

---

## 2026-08-10

| metric | value | vs prev |
|---|---|---|
| published | **1** | 0 → 1 |
| eligible/docket | **7** (SPSHGzlOe8c, 20 cases) | 0 → 7 |
| safety rejects | **0** | 6+ → 0 |
| top score | **85.2** | 57.0 → 85.2 |
| analysis failures | **0** (5/5 batches clean) | 1 → 0 |
| banked runner-ups | 6 | 0 → 6 |
| clips rendered | **2** | 1 → 2 |

Changed: safety gate cut 10 rules → 7, only 3 can reject, uncertainty now
resolves to ACCEPT (`77ce58b`). JSON repair for `undefined` / `\'` / trailing
commas; batch 6 → 4.

Later same day: added `boyd run --case <key>` to render a chosen defendant
instead of the top pick, fixed the `boyd bank` crash, added yt-dlp retries (a
single transient 403 was killing whole runs), and stopped `plan_short_segments`
discarding a valid short when the hook opens a few seconds before the case
boundary — it now clamps into the case instead. That last one had silently
suppressed the short on the 85.2 pick, and the short is the entire
distribution mechanism.

**First clip published** — "Teen Shot His Friend In The Face — Judge Boyd Turns
On His Mother", a 57s Short cut from XiWwYFPhPn0 (2026-07-21 docket). Hook-first
cut, one-word captions in the letterbox band, amber keyword glow.

**The baseline clock starts here.** Roughly 10 posts are needed before "outlier"
means anything on this channel — until then, per-video numbers are noise, not
signal. Do not tune anything off post #1. What to record for each: views,
retention curve shape, and where the drop-off sits.

Two clips remain rendered and unpublished: `W8IvfROpZc8:774` (60.4) and
`SPSHGzlOe8c:6031` (85.2, De Hoyos), plus four more hand-cut shorts.

Open question: `min_total_score: 50` was calibrated when nothing scored above
57. Scores now reach 85. The floor is probably too low — measure before moving.

---

## 2026-08-09 (baseline)

| metric | value |
|---|---|
| published | 0 |
| eligible/docket | 0 (18 cases scored across 2 dockets) |
| safety rejects | 6 on safety, rest on rubric |
| top score | 57.0 |
| analysis failures | 1 (SPSHGzlOe8c lost entirely) |
