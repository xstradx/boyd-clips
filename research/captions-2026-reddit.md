# Caption tooling + caption-craft complaints, 2026 — fetched research

**Provenance / how much to trust this.** Gathered 2026-08-23 by a background
research agent under a NON-INTROSPECTIVE brief (no answering from model
knowledge; every finding must carry a fetched source). Every line below carries
a URL and a date, which is the bar that was set. **Claude has not independently
re-verified any individual link.** Treat the URLs as leads to check, not as
already-confirmed facts.

Reproduced verbatim from the agent's report — not re-worded, not summarised.

---

## Access note (method, since it constrains what's verifiable)

reddit.com returns **HTTP 403 "blocked by network security"** to this IP for curl *and* for a real Playwright browser; `WebSearch`/`WebFetch` refuse reddit.com entirely ("domains are not accessible to our user agent"). pullpush.io returns 429. Everything below was fetched live through the **redlib mirror `safereddit.com`** driven by Playwright (it passes an Anubis PoW challenge that curl can't). Canonical reddit.com URLs are given; dates are the `created_utc` title attributes redlib carries through. HN came from `hn.algolia.com` via curl.

---

## Named tools — what practitioners say they actually use (2026)

**Premiere-side plugins (the crowded, contested space)**
- Brevidy — the most-repeated recommendation in r/premiere and r/editors 2026; the mod (u/greenysmac) endorses it over Captioneer/SubMachine — https://reddit.com/r/premiere/comments/1vljwyb/ — 2026-08-11
- Brevidy claims *millisecond word-level timing*; dev says rivals reuse Premiere's phrase-level transcript + averages — https://reddit.com/r/editors/comments/1rvqmu6/ — 2026-03-17
- Brevidy pricing complaint: "deliberately misleading… monthly prices are actually billed annually"; another editor rejects the 100 min/mo + 3-preset tier as a non-starter vs CapCut at $20 — https://reddit.com/r/premiere/comments/1tvt7yr/ — 2026-06-03
- SubMachine — $135–150 lifetime, one-time; requires restructuring to 1 word / 1 line per caption before feeding it — https://reddit.com/r/editors/comments/1u6jue5/ — 2026-06-15
- SubMachine license failure report: "purchased a lifetime licence for $135 and the key never worked… emailing them for the past 1.5 months without any reply" — same thread — 2026-08-21
- Captioneer — heavily used, offline/unlimited transcription, custom MOGRTs per client; drift on single-word mode is the standing complaint — https://reddit.com/r/editors/comments/1rvqmu6/ — 2026-03-16
- CaptionPlug — £14.99 one-time, ships local Whisper large-v3 (moved from API-only to fully offline); named by a clipper who edits for Marlon/Mizkif — https://reddit.com/r/premiere/comments/1vebya0/ — 2026-08-03
- CaptionPlug malware report (twice, unanswered support): "windows detected that it has a Trojan virus on it" — https://reddit.com/r/premiere/comments/1vjvjxy/ — 2026-08-12
- CaptionPlug limitation: "no option to switch to single or double line captions. It randomly switches" — same thread — 2026-08-15
- Substyle (substyle.io), CaptionX, AutoCut, Premiere Assistant, Firecut, Phantom/Echoe Scribe, "TikTokText" script on aescripts, Cutback, Sublyfier, OutCaps — all named as Premiere caption routes — https://reddit.com/r/premiere/comments/1uliv9y/ — 2026-07-02
- Free Premiere extension built on Whisper by an editor (cyrilplugin.com/sub-creator) with highlight animation — https://reddit.com/r/premiere/comments/1vljwyb/ — 2026-08-11

**Resolve-side**
- AutoSubs (tmoroney, github.com/tmoroney/auto-subs, tom-moroney.com/auto-subs) — the single most-named *free* tool; works in Resolve **Free**, local models, supports word-by-word via "Animated Text Style" — https://reddit.com/r/davinciresolve/comments/1tklyg4/ — 2026-05-22
- AutoSubs timing complaint + model advice ("canary used to be decent… whisper large-v3 nails word-level timing more consistently") — https://reddit.com/r/davinciresolve/comments/1vuuyni/ — 2026-08-21
- Snap Captions — widely used, but paid-license failures reported and no text editing in free tier — https://reddit.com/r/davinciresolve/comments/1v24gqd/ — 2026-07-21
- MrAlexTech "Magic Subtitles Pro / MagicCaptions" — repeatedly named as the more configurable Snap Captions replacement, has a Free-version build — https://reddit.com/r/davinciresolve/comments/1v1poz6/ — 2026-07-20
- Caption Cat (~$50 one-time, Whisper-based), Bunny Captions, Ember (embersubs.com) — also named — same thread + https://reddit.com/r/davinciresolve/comments/1tklyg4/ — 2026-07-20 / 2026-05-24
- TypeFlare (tagger.mov, $49 one-time) — dev-posted repeatedly across r/davinciresolve: faster-whisper local, exports **editable Fusion Text+ comps** rather than baked captions; free tier = unlimited SRT + one karaoke preset — https://reddit.com/r/editors/comments/1vd42r0/ — 2026-08-02
- SuckLessWriteOn (SLWO) fuse via Reactor — named for lines/words/characters write-on, "must-have… for karaoke" — https://reddit.com/r/davinciresolve/comments/1vt9i2v/ — 2026-08-20
- Practitioner stack, verbatim: "Descript ai to generate subs, mralextech preset, snap captions to apply different colors and timeline tools v2 to copy paste changes in bulk" — https://reddit.com/r/davinciresolve/comments/1vn9jzt/ — 2026-08-13

**Open-source / DIY / ffmpeg + ASS**
- The explicit free stack, spelled out by a practitioner: WhisperX word-level → generate `.ass` with karaoke highlight tags → `ffmpeg -vf "ass=subs.ass"` — https://reddit.com/r/editors/comments/1vljvhi/ — 2026-08-13
- Same stack recommended again for "Hormozi-style" captions, plus why free web tools aren't free (they gate export/watermark/styles) — https://reddit.com/r/AIToolsAndTips/comments/1vi61yk/ — 2026-08-07
- faster-whisper `word_timestamps=True` + **Silero VAD** pre-pass + per-word confidence flagging (<0.6) as the forced-alignment recipe, and gap-based line grouping — https://reddit.com/r/editors/comments/1v813lw/ — 2026-07-27
- Subtitle Edit (nikse.dk) — the perennial free answer; runs local Whisper/Parakeet models, per-audio-track selection, huge format support; "killer functionality when combined with faster whisper. But the UI takes some getting used to" — https://reddit.com/r/VideoEditing/comments/1ueeuah/ — 2026-06-25
- Aegisub still cited as the fansub-standard ASS editor — same thread — 2026-06-24
- withsubtitles.com — browser-local, no signup/watermark/limits, Hormozi-style word-by-word; repeatedly thanked by real users in-thread — https://reddit.com/r/NewTubers/comments/1s7jik8/ — 2026-03-30
- Subber (github.com/AndreaZero/subber, MIT, local, SRT for Resolve) — https://reddit.com/r/SideProject/comments/1vtfttk/ — 2026-08-20
- McFadden Editing Suite (Python, open source, times subtitles and outputs timed Resolve **Text+**) — https://reddit.com/r/VideoEditing/comments/1up45iy/ — 2026-07-07
- Claude-Code pipeline replacing Premiere entirely: Whisper + SAM2 tracking + Remotion/ffmpeg for cuts, captions and motion graphics — github.com/angelarose210/video-clipping — https://reddit.com/r/premiere/comments/1vebya0/ — 2026-08-12
- Remotion as the caption renderer (drawn onto the frame at render, not MOGRTs) — https://reddit.com/r/editors/comments/1v813lw/ — 2026-07-28
- Rescript (github.com/wassgha/rescript) — open-source Descript alternative, transcript-based editing only — https://reddit.com/r/editors/comments/1r2yi48/ — 2026-07-29
- ffmpeg lavfi CC extraction to `.ass`, and the fact that you cannot set `BorderStyle` from ffmpeg — workaround is post-hoc regex/PowerShell rewrite of the Style line — https://reddit.com/r/ffmpeg/comments/1vjh02z/ — 2026-08-09
- ffmpeg `-codec:s text` vs default `subrip` to strip `{\an7}` positioning tags on lavfi SRT extraction; ASS reveals the real mechanism (`{\an7}{\pos(x,y)}` per line) — https://reddit.com/r/ffmpeg/comments/1v7e2dx/ — 2026-07-27
- ffmpeg hardsub gotcha: two `-vf` flags silently drop one; must combine `-vf "subtitles=subs.ass,scale=-1:320"` — https://reddit.com/r/ffmpeg/comments/1v0x5do/ — 2026-07-19
- HN: someone shipped a PGS subtitle encoder for FFmpeg (ticket #3819) that preserves **ASS fades as palette-only updates**, wired libass + Tesseract into the main pipeline; built with Claude Code — https://news.ycombinator.com/item?id=47415044 — 2026-03-17
- HN: "Ask your coding agent to subtitle, translate, and clip video (FFmpeg)" — https://news.ycombinator.com/item?id=49238442 — 2026-08-10
- HN: auto-captions with face-tracking reframe for vertical — https://news.ycombinator.com/item?id=48368712 — 2026-06-02

**Transcription engines named by name**
- greenysmac (r/premiere lead mod) ranks them: "Whisper isn't always the best transcriber. Nowadays, I tend to use **Parakeet** way more. When it's really difficult, I throw it at **DeepGram**" — https://reddit.com/r/premiere/comments/1uiu04i/ — 2026-06-29
- MacWhisper Pro with the **Parakeet** model "blows everything else off the table" for English — https://reddit.com/r/davinciresolve/comments/1tkf8ab/ — 2026-05-22
- Also named: Rev (AI + human tiers), aTrain, AssemblyAI, Gladia, Vrew, Trint, Reduct.video, Lumberjack Builder, HappyScribe, Simon Says, Verbatim.mov (5¢/min, 100 custom keyterms), freesubtitlesai — across https://reddit.com/r/editors/comments/1r2yi48/ and https://reddit.com/r/premiere/comments/1ufx7id/ — 2026-02-12 / 2026-06-26

---

## Specific complaints (the recurring failure modes)

- **Word-timing drift is the #1 complaint, and it's phrase-level vs word-level**: "premiere and capcut are phrase-level which is why srt exports land off the frame" — https://reddit.com/r/premiere/comments/1s5ukkl/ — 2026-08-21
- Estimating timing from a script instead of the audio breaks the moment someone talks fast — the whole thread is that diagnosis — https://reddit.com/r/editors/comments/1v813lw/ — 2026-07-27
- Resolve's built-in Word Timing Analysis "sometimes gets stuck or fails… **you can't manually fix or edit the word timing afterward**" — https://reddit.com/r/davinciresolve/comments/1v1poz6/ — 2026-07-20
- Resolve auto-segmentation puts the next sentence's first word after a period, deterministically per-video: "it'll keep doing that regardless of if you regenerate the subtitles" — https://reddit.com/r/davinciresolve/comments/1uvroxe/ — 2026-07-13
- Line-break taxonomy from a 10+ clips/day shortform editor: bad breaks on "and/to/of", **cliffhanger words** alone on a line, punctuation orphans ("The fox jumped. And"), hundreds of micro-edit clicks/day — https://reddit.com/r/editors/comments/1sp8u0z/ — 2026-04-18
- Premiere's caption tool doesn't respect edit points, ignores stated char limits, and "split the caption" splits in HALF not at the CTI — https://reddit.com/r/editors/comments/1u6jue5/ — 2026-06-15
- Premiere transcription turns any pause >~200ms into a comma with no exposed parameter; workaround is regex `,\s*$` on the SRT, or strip all punctuation and go all-caps — https://reddit.com/r/premiere/comments/1txtm7c/ — 2026-06-05
- Resolve free has **no** auto-transcribe at all (Studio $295 gates it) — the reason SRT-from-elsewhere is the standard free workflow — https://reddit.com/r/NewTubers/comments/1ur99k4/ — 2026-07-09
- Resolve forgets to include subtitles at export unless you re-tick it; 36 upvotes, community split on whether it's a flaw — https://reddit.com/r/davinciresolve/comments/1vngfra/ — 2026-08-13
- Twitch clip captions are **burned in, non-editable, non-toggleable, and default-on** — "There's no option to edit the subtitles… the groupings of words is wrong, and the timing is off" — https://reddit.com/r/Twitch/comments/1twv6lj/ — 2026-06-05
- Accents / non-native English are the unfixed accuracy hole across CapCut, Opus Clip, Veed, Submagic — https://reddit.com/r/VideoEditingTips/comments/1veoh9n/ — 2026-08-03
- Submagic specifically: "buggy product with poor mobile UX. They also have very poor customer service" — https://reddit.com/r/VideoEditors/comments/1qg090m/ — 2026-05-09
- Captions-look-samey complaint (closest thing to your "everyone's look the same"): "only a few preset styles, and the results look a bit 'samey'" — https://reddit.com/r/NewTubers/comments/1r339nn/ — 2026-02-12
- Client-side version: presets meant for special moments are now demanded on every video, "This is not time conducive" — https://reddit.com/r/VideoEditing/comments/1uryh7p/ — 2026-07-09
- The revision-cycle argument for staying in-NLE: "If the captions are made in CapCut, it becomes frustrating to go back and update the video" — https://reddit.com/r/premiere/comments/1v9xzzh/ — 2026-07-29

---

## Aesthetic / retention findings (thin but 2026-dated)

- Word-by-word karaoke called "seizure-inducing" / dizzying past ~1 min; the poster switched to static blocks and complaints stopped — https://reddit.com/r/NewTubers/comments/1usbo8q/ — 2026-07-10
- The countervailing claim, from the same subreddit era: 2–3 word chunking, **dead center or slightly below** (bottom third is eaten by platform UI), white body text with one bright yellow/green emphasis color — same thread — 2026-07-10
- Independent restatement: 1–3 words for fast talking heads because "full sentences make the eye read ahead, finish the point early, and leave"; middle third, bigger than looks right on a laptop — https://reddit.com/r/SideProject/comments/1vilyue/ — 2026-08-08
- Why word-by-word persists despite editors hating it: "It leads to bigger retention numbers on socials… people can't just read the whole context right away and realize they're not interested" — https://reddit.com/r/davinciresolve/comments/1vhjjb2/ — 2026-08-07
- One measured-ish account of burned-in captions moving TikTok Shop commissions (n=1, self-reported) — https://reddit.com/r/TikTokMonetizing/comments/1v7yiqk/ — 2026-07-27

---

## The single most quotable structural finding

Professional editors round-trip through CapCut *specifically for captions* and are embarrassed about it:

> "The irony is CapCut is leading this field given that its purpose-built to make more engaging TikTok videos. I've sent videos through it merely to get better animated captions without spending two hours in After Effects." — https://reddit.com/r/editors/comments/1u6jue5/ — 2026-06-15

> "your only option at the moment are paid plugins like Captioneer (which aren't perfect) or sending the whole thing through CapCut (which seems to be, astonishingly, the leading method.)" — same thread, 2026-06-15

> "The tools that are good at editing captions aren't aware of the edit, and the tools that are aware of the edit don't really do captions properly." — same thread — 2026-06-18

---

## Verbatim quotes naming a tool or a specific defect

- "faster-whisper with word_timestamps enabled gets you there directly… It's worth running a VAD pass first too, something like Silero VAD to strip dead air" — https://reddit.com/r/editors/comments/1v813lw/ — 2026-07-27
- "Whisper (specifically WhisperX, which gives word-level timestamps) will transcribe with per-word timing, and that timing is the actual thing the paid tools are selling. From there you generate an .ass subtitle file with karaoke highlight tags per word, and burn it in with ffmpeg (-vf \"ass=subs.ass\")" — https://reddit.com/r/editors/comments/1vljvhi/ — 2026-08-13
- "Our tool Brevidy has 95% accurate transcriptions… Most tools take Premiere's transcription (which is not word level timing) and use averages. Our's has millisecond level timing data baked in for every word." — https://reddit.com/r/editors/comments/1rvqmu6/ — 2026-03-17
- "my one gripe is when I set it to single word captioning, it drift severely so I end up having to realign it. It feels like the time I saved copying attributes is just spent lining up the captions per word." — https://reddit.com/r/editors/comments/1rvqmu6/ — 2026-03-17
- "The biggest issue is that you can't manually fix or edit the word timing afterward." — https://reddit.com/r/davinciresolve/comments/1v1poz6/ — 2026-07-20
- "the timing issues with autosubs are pretty common… canary used to be decent but honestly the whisper models (large-v3 specifically) tend to nail word level timing way more consistently" — https://reddit.com/r/davinciresolve/comments/1vuuyni/ — 2026-08-21
- "Anything other than Submachine. I purchased a lifetime licence from them for $135 and the key never worked. I've been emailing them for the past 1.5 months without any reply." — https://reddit.com/r/editors/comments/1u6jue5/ — 2026-08-21
- "Be careful, I paid for it, and when I downloaded it, windows detected that has a trojan virus on it. I contact customer support and they never reply back" (CaptionPlug) — https://reddit.com/r/premiere/comments/1vjvjxy/ — 2026-08-12
- "Premiere's transcription engine uses a rigid punctuation restoration model that translates almost any acoustic pause over ~200ms into a comma, regardless of syntax. Because Adobe doesn't expose these model parameters, there is no native slider to turn it down." — https://reddit.com/r/premiere/comments/1txtm7c/ — 2026-06-06
- "I had to spend 2 hours on an 8 minute video correcting the wrong translations… when you correct the words it fs up the timings of the captions so then I have to manually adjust the timings of every caption one by one" — https://reddit.com/r/premiere/comments/1qpj9m0/ — 2026-01-28
- "Whisper isn't always the best transcriber. Nowadays, I tend to use Parakeet way more. When it's really difficult, I throw it at DeepGram." — https://reddit.com/r/premiere/comments/1uiu04i/ — 2026-06-29
- "resolve is not great at that. for english, even FCP is better (and faster). i always have been using MacWhisperPro, especially the latest Parakeet Model there blows everything else off the table" — https://reddit.com/r/davinciresolve/comments/1tkf8ab/ — 2026-05-22
- "The transcribe itself is so bad i can't share it with clients for review as it's all broken sentences with some lines being a single word!" — https://reddit.com/r/davinciresolve/comments/1tkf8ab/ — 2026-05-22
- "SubMachine works best if you create captions with 1 word per caption and only 1 line per caption… it is *not* something you should ever show anyone who does not understand what the end goal is" — https://reddit.com/r/editors/comments/1u6jue5/ — 2026-06-18
- "The really wild styles you see are almost never a caption plugin out of the box - they're Text+ with custom animation… transcription gets words onto the timeline, styling is a separate problem." — https://reddit.com/r/davinciresolve/comments/1vn9jzt/ — 2026-08-13
- "I used to do word by word and a few folks in my comments mentioned it made them dizzy on anything over a minute, switched to static blocks and nobody's complained since." — https://reddit.com/r/NewTubers/comments/1usbo8q/ — 2026-07-10
- "It's burnt into the video so users can't toggle it off… There's no option to edit the subtitles. Sometimes it picks the wrong words, and often the groupings of words is wrong, and the timing is off." (Twitch clip captions) — https://reddit.com/r/Twitch/comments/1twv6lj/ — 2026-06-05
- "Getting the captions 100% perfect is where most of my time sink is… They're typically 30-90 seconds so it's 50+ captions." — https://reddit.com/r/premiere/comments/1vebya0/ — 2026-08-03
- "the paywall hits at export. resolve sidesteps that since the whole render is free." — https://reddit.com/r/VideoEditing/comments/1ueeuah/ — 2026-06-26

---

## Marked "not found"

- **"submagic captions look the same as everyone"** verbatim — **not found**. Nearest 2026 equivalents are the "samey preset styles" complaint (r/NewTubers 1r339nn, 2026-02-12) and Submagic being called buggy with bad support (r/VideoEditors 1qg090m, 2026-05-09).
- **"capcut captions drift"** as a 2026 complaint — **not found**. In 2026 the drift complaints attach to Premiere/Captioneer/Resolve/AutoSubs; CapCut is repeatedly cited as the *accuracy and animation benchmark* people escape to.
- **Hacker News discussion threads about short-form/karaoke captions** — **not found**. HN 2026 caption/whisper hits are near-100% zero-comment Show HNs; the only substantive 2026 HN thread touching ASS/libass is the FFmpeg PGS encoder (49405044 → item 47415044), and its comments are about upstreaming and AI-authored patches, not caption craft.
- **r/SideProject discussion** — posts exist in volume but are almost all zero-to-two-comment launch announcements (Subies, Subber, MotionCaptions, Polley Captions, AI Subtitle Studio, Aulyr). No practitioner debate there.

---

## What was NOT researched (the gaps, so nobody mistakes this for complete)

Two sibling agents were stopped before reporting when Nathan redirected:
- **What editors argue about / what the field mocks** — the played-out-styles and
  credible-vs-clickbait territory. Not covered.
- **Courtroom-shorts winners vs losers, measured** — top vs bottom videos on the
  same channel. Not covered. This is the one that would actually say whether
  caption treatment moves anything in *this* niche.

So: this file answers "what tools exist and what breaks", not "what taste is
right for a Boyd short".
