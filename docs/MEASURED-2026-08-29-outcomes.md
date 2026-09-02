# Measured 2026-08-29 — what the posted videos actually did

Pulled with `yt-dlp -J` per video from `@TexasTrialTracker`
(`UCT5Fde6OzBSFRmxw5mPn2CA`, 2,880 subs). Public counts only — no OAuth yet, so
impressions, CTR and retention are still unmeasured.

## The two surfaces diverged hard

| posted | short | views | long-form | views |
|---|---|---|---|---|
| 2026-08-11 | Teen Shot His Friend In The Face | **1,122** | — | — |
| 2026-08-17 | Judge Boyd checks his story | **5,349** | He says his family was murdered | **72** |
| 2026-08-27 | Spider Monkey | **1,153** | Judge Boyd Wants to Know Where the Spider Monkey Is | **55** |

Against this channel's OWN Judge Boyd back catalogue (Feb 2025, same format):

- old Boyd **shorts**: 2,611 / 2,902 / 16,523 / 22,621 / 27,971 / 39,816 / 61,366
- old Boyd **long-forms**: 1,414 / 2,385 / 3,098 / 4,384 / 4,692 / 9,813

## What that says

**The shorts are roughly in band. The long-forms are 20-140x below the
channel's own floor.** Thompson's long-form has had twelve days to run and sat
at 72 while its own short did 5,349 in the same window. The channel is not
shadow-dead — Shorts got served.

So the long-form entry surface (thumbnail + title + whether the short hands
viewers over) is the broken thing, not the pipeline that cuts the video.

**Do not over-read it.** Long-form and Shorts are different recommendation
surfaces, and the channel was dormant 2025-02-27 to 2026-03-18 and again to
2026-08-17. Dormancy plus a format switch is a live alternative explanation.
The measurement that separates them is impressions vs CTR vs retention, which
needs the YouTube Analytics OAuth (`youtube-channel` skill).

## Dead air still in the long-forms — measured, not assumed

STATE.md said the long-forms "almost certainly still carry gaps nobody
measured". Measured now, using `tighten_short.py`'s own definition (consecutive
word-start spacing > 0.70s). **Control first:** the CARTHIEF short reproduces
STATE.md's documented 22 gaps / 31.2s exactly, so the counter is trustworthy.

| long-form | runtime | gaps >0.7s | dead air | share |
|---|---|---|---|---|
| CARTHIEF | 1054s | 340 | 489.0s | **46.4%** |
| SANCHEZ | 445s | 124 | 136.2s | **30.6%** |
| OFFERUP | 547s | 122 | 141.2s | **25.8%** |

**The tension this creates is Nathan's call, not mine:** tightening drops
SANCHEZ to ~5:08 and OFFERUP to ~6:49, both under the 8-minute mid-roll
threshold in `boyd-clips-production-rules`. CARTHIEF survives at ~8:34.
SANCHEZ (7:24) and ROMERO (7:00) are ALREADY under 8 minutes untightened.

## Renders on disk are technically clean

All checked with ffprobe 2026-08-29: every FINAL short and every long-form is
`yuv420p` High profile — the 4:4:4 bug that shipped once is gone. Shorts are
1080x1920, long-forms 1920x1080. All six thumbnails are 1280x720 and 183-287 KB,
well inside the YouTube API's 2 MB limit.

STATE.md's line "SANCHEZ and OFFERUP shorts have not been through the new
pipeline" is **stale** — `SANCHEZ_SHORT_FINAL.mp4` (49.1s) and
`OFFERUP_SHORT_FINAL.mp4` (41.9s) both exist, dated 2026-08-29.
