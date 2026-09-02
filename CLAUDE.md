# Boyd Clips — read this before doing anything

> **Thumbnails: the `boyd-thumbnail` skill owns the build order, the gates and
> the rules table; `spec/NATHAN_RULES.md` holds every rule verbatim with its
> checker and the Checker registry.** Frame by expression first, arrow LAST;
> no hard cuts; rebuild the background whenever geometry changes; arrow and
> spacing are solved per-image, never constants.

Automated daily clipping of Judge Stephanie Boyd's 187th District Court
livestream. Architecture is in `README.md`; **current state is in `STATE.md`.**

## Start every session here

1. **`STATE.md`** — read it first. The running state: what's rendered, what's
   blocked, what was measured and by which command. Kept current as work
   happens, not written up at the end.
2. **`spec/SPEC.md`** — the contract. What the product is, what makes a clip
   gold, how it gets selected, cut and packaged. If anything disagrees with it,
   SPEC wins. Its §6 says what governs what.
3. **`README.md`** — only if the task touches how the pipeline is wired
   (discover → transcribe → segment → gate/score → select → render → publish).

Update `STATE.md` as part of the work, not as a write-up afterwards. If a
session ends and STATE.md didn't move, the next session starts blind.

## Where the documents live — consolidated 2026-08-20

Three roots, and the folder tells you the authority:

| | |
|---|---|
| `STATE.md`, `README.md`, this file | what's true now, how it's wired, how to work |
| `spec/**` | **binds.** SPEC + SAFETY_RULES, then CONTENT_SPEC, PACKAGING, RECORDS-API |
| `docs/reference/**` | research. Informs, binds nothing |
| `docs/archive/**` | superseded. Do not plan from it |

`spec/SAFETY_RULES.md` outranks SPEC on safety. `docs/archive/POST-IT-YOURSELF.md`
is stale (2026-08-14) with three retracted claims — the retractions are at the
bottom of `STATE.md`.

Before this consolidation the repo carried six root documents and seven specs,
two of which SPEC declared retired while the tests and prompts still read them.
If you find a document that contradicts `spec/SPEC.md`, that is a bug in the
document — fix it or move it, do not quietly follow it.

## "Start working on videos" means ALL of this

Nathan's standing definition, 2026-08-17. When he says work on videos, do not
stop at rendering a raw cut — a video is not done until every one of these is
true:

1. **Download** the case's minutes from the source stream.
2. **Edit** — dead air over 4s removed (CONTENT_SPEC §2), chronological, nothing
   reordered.
3. **Intro** — the branded sting on the front (`boyd-brand/sting_v2.mp4`, 2.6s).
   `output.longform.intro_enabled`.
4. **Watermark** — burned into the body, not the intro.
5. **Short** with a real hook, in the Thompson style: full-bleed 2-up, each tile
   cropped to the half-canvas and centred on its subject, captions moving to the
   speaker's half via per-event ASS `MarginV`.
6. **Thumbnail** — built by `tools/thumb_pipeline.py` in the order the
   `boyd-thumbnail` skill gives (frame by expression → layout → subjects →
   title → kicker → grade → arrow last), floor-stamped, and gated inside the
   build. "House style" is whatever `config/quality_floor.json` measures on the
   five accepted builds — not a description from memory.

Every one of these has silently degraded to "off" at some point because the
code accepted a missing asset and logged a line instead of failing. If a render
finishes and any of the six is absent, that is a bug, not a preference.

**Before any of that: pick the case.** His words, 2026-08-30: *"I've told you
10 times soto case was high profile and no one was posting it there are no
trials like that and even if cases are jury trial boyd doesn't let anyone in
the room so there's very low quality zoom audio that's all we get"*. Selection
outranks packaging - a high-profile case nobody else is posting beats a
well-packaged ordinary one. Jury trials are closed-room Zoom audio and are not
clip material. Before packaging, search YouTube for the defendant / case and
record who has posted it in `config/cases.json`.

**A pick is read, not ranked.** 2026-09-02: *"I think you have to use observer
skill to actually pic actual entertaining banger clips"*. The picker finds
hearings; `tools/banger_digest.py` scores what viewers stay for and prints the
lines. A shortlist row without the digest score, three quoted lines, the
ruling, an on-camera frame and the rival count is a lead, not a pick
(`spec/NATHAN_RULES.md` R50).

**When a floor moves, everything pending is rebuilt.** 2026-08-31: *"that short
was made off the old rules or whatever and should be made with our new ones"*.
Every render carries a floor stamp (`tools/floor_stamp.py`); an artifact whose
stamp differs from the current `config/quality_floor.json` /
`config/short_floor.json` is rebuilt before it is shown or posted.

## Before reporting ANY thumbnail or short as done

Read `spec/NATHAN_RULES.md` and run its checks. It holds every rule Nathan has
stated, his verbatim words, the measurement that decides each one, and a count of
how many times he has had to repeat it — three times for speaker-side captions,
three for surgical cuts, three for the arrow.

He said, 2026-08-29: *"i have to keep repeating myself multiple times for each and
every one and you keep brining me the same exact flaws ... you have taken them all
as a fix and you didnt rememeber them"*.

The cause was structural: each complaint got fixed in the image in front of me
instead of becoming a check, so nothing stopped it regressing and he became the
regression test. **When he states a new flaw, add the rule AND its check in the
same turn.** A rule that cannot be automated gets reported out loud as
unautomated every time — a silent gap is how these regressed.

The check has to be on the build path, not just on disk: `python
tools/check_rules_refs.py` proves every checker the rules name is WIRED (or
declared MANUAL), and `python tools/selftest_all.py` runs all of them. Both
must print `ALL_OK` before a build is shown. His verdicts on every build go to
`docs/verdicts/team_A_verdicts.md` the same turn; the skill gap each one
exposes goes to `~/.claude/projects/C--Users-natha/skill-observations/`.

## Standing rules for this project

- **Profanity: leave it in the audio, censor it in every text surface** —
  captions, titles, thumbnails, descriptions, on-screen cards, docs.
- **Never set "Made for Kids"** on the channel, uploads, or streams. Declare
  Not Made for Kids.
- **Publishing is a hard stop.** Uploading, posting, or making anything public
  requires Nathan's confirmation in that turn. Rendering locally does not.
- **Court footage is public record.** Do not invent rights, defamation, or
  privacy restrictions around it. If a real restriction applies, quote the
  actual text; if it hasn't been checked, say it hasn't been checked.
- "Ready" means rendered and verified on disk — not shipped. The first two
  shipped 2026-08-31 (OFFERUP long `ESSF8lSkNN4` + short `LqAneu_GSOM`); the
  procedure is the `youtube-channel` skill (`scripts/ui2.ps1`) and it works
  from this PC. Track the shipped outcome, not the file.

## Where memory lives

Durable cross-project memory is at
`C:\Users\natha\.claude\projects\C--Users-natha\memory\` (start with
`MEMORY.md`). That store is scoped to the home directory but applies
everywhere — read it when starting substantial work here.
