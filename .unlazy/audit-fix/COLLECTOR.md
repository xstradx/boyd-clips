# Collect to learn what

The answer to "build the collector, not the learner" is only useful if it names
the questions. Every field below exists to answer one, and no field is here
without one. If a question gets dropped, its fields get dropped.

**The reason half of this is local, not from YouTube:** the API tells you what
happened. It cannot tell you which of your choices caused it, because it never
saw the choice. A retention curve with no record of which frame, which wording,
which hook and which cut produced it is a number with nothing to attach to. That
is exactly why the current two long-forms cannot teach us anything even now that
we can see their view counts — nothing on disk records what was decided.

So the collector has two halves, written at two different times:

- **At production time**, before the file is uploaded: what we chose.
- **Daily after publish**: what happened.

The join key is the video id, backfilled onto the case row at upload.

---

## Q1 — Does the thumbnail earn the click?

This is the question Nathan asked the system to eventually answer for itself,
and the only one whose data is unrecoverable if not started now.

| FIELD | SOURCE | QUESTION |
|---|---|---|
| `video_thumbnail_impressions` | Reporting API bulk `channel_reach_basic_a1` | how many people saw it at all |
| `video_thumbnail_impressions_ctr` | Reporting API bulk `channel_reach_basic_a1` | did the thumbnail earn the click |
| `thumbnail_file` | local, copied at build time | which exact image produced that CTR |
| `thumbnail_variant` | local, the A/B/C letter | which wording produced that CTR |
| `thumbnail_judge_frame_t` | local, the source timestamp | which Boyd frame produced that CTR |
| `thumbnail_headline` | local, the burned-in text | which words produced that CTR |
| `thumbnail_flat_chroma` | local, the gate's own metric plus its selected region | whether a build gate predicts anything real |

Not in the query API — bulk report only, starts the day the job is created,
60-day server retention, no backfill.

## Q2 — Does the opening hold?

| FIELD | SOURCE | QUESTION |
|---|---|---|
| `audienceWatchRatio` by `elapsedVideoTimeRatio` | Analytics API `reports.query` | where in the video people leave |
| `relativeRetentionPerformance` | Analytics API `reports.query` | how that compares to videos of the same length |
| `hook_line` | local, the chosen cold-open quote | which hook produced that first-30s shape |
| `hook_reentry_t` | local, the cut-back-in point | whether the re-entry point costs viewers |
| `first_cut_at_s` | local, computed from the cut list | whether the first cut lands before people go |

`elapsedVideoTimeRatio` is 0.0-1.0, so multiply by duration to get the second.

## Q3 — Do the Shorts feed the long-form, or not?

Currently measurable at 1.35% and 4.42% carry-over, from public data only.

| FIELD | SOURCE | QUESTION |
|---|---|---|
| `insightTrafficSourceType` | Analytics API `reports.query` | where long-form viewers actually came from |
| `paired_short_id` | local, written at upload | which Short belongs to which long-form |
| `short_published_at` / `long_published_at` | local | whether the gap between them matters |
| `views` daily series | Analytics API `reports.query` by day | whether the long-form moves when the Short spikes |

## Q4 — Which cases are worth cutting?

The research measured a 22.5x view spread on a competitor with duration not
separating them — case selection did. We have 1,702 transcripts and no idea
which case attributes matter.

| FIELD | SOURCE | QUESTION |
|---|---|---|
| `case_charge` | local, from the Bexar record | do violent cases outperform property cases |
| `defendant_talk_ratio` | local, computed from the transcript | is Nathan's "the defendant talks a lot" rule real |
| `hearing_duration_s` | local | is there a length that works |
| `boyd_question_count` | local, from the scorer | does her engagement predict anything |
| `selection_score` + `selection_reasons` | local, what the scorer thought and why | is the scorer predictive at all, or noise |

The last row is the one that turns the scorer from an assertion into something
falsifiable. It has never been recorded.

## Q5 — Does the title pattern hold on our own channel?

Measured on a competitor at p=0.0068 and implemented nowhere. Our own channel
is the only sample that matters.

| FIELD | SOURCE | QUESTION |
|---|---|---|
| `title` | local + Data API | does it open with the literal string "Judge Boyd" |
| `title_source` | local, `human` or `generated` | are generated titles worse than written ones |
| `tags` | local + Data API | all four uploads shipped with none; does that cost anything |
| `description_has_case_no` | local | does on-screen sourcing correlate with anything |

## Q6 — Did a change we made actually help?

The question every other question exists to serve, and the one that needs a
build record or it is unanswerable.

| FIELD | SOURCE | QUESTION |
|---|---|---|
| `git_sha` | local, `git rev-parse HEAD` at render | which version of the code made this file |
| `worktree_dirty` | local, `git status --porcelain` at render | whether that sha is even meaningful |
| `elements_applied` | local, the six-key manifest block | which of the six were actually on |
| `dead_air_removed_s` and its parameters | local | how much was cut and at what threshold |
| `render_gates_passed` | local, the gate results | whether a passing gate predicts a better video |

---

## What NOT to collect, and why

- **Competitor retention.** Does not exist. The most-replayed heatmap was absent
  on 8 of 8 sampled competitor videos. Collecting a field that is always null
  teaches nothing and creates the impression of coverage.
- **Anything requiring an adaptive decision now.** At n=2 published videos, and
  even at n=5, no adaptation is distinguishable from noise. YouTube's own A/B
  tool needs up to two weeks on a single video with access to every impression.
- **Sentiment or comment analysis.** Both pipeline long-forms have zero comments.
  There is nothing to analyse.

## When it becomes a learner

Not on a date — on a count. At roughly 30 published videos with complete rows,
the first honest question is a single comparison, not a model: does the
"Judge Boyd" title prefix change CTR on OUR channel. One variable, one test.
Everything before that is collection, and the collection has to start now
precisely because the learning has to start later.
