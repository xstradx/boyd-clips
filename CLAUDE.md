# Boyd Clips — read this before doing anything

Automated daily clipping of Judge Stephanie Boyd's 187th District Court
livestream. Architecture is in `README.md`; **current state is in `STATE.md`.**

## Start every session here

1. **Read `STATE.md` first.** It is the running state — what's rendered, what's
   blocked, what was measured and by which command. It is kept current as work
   happens, not at the end.
2. `README.md` for how the pipeline is wired (discover → transcribe → segment →
   gate/score → select → render → publish).
3. `SCOREBOARD.md` for case scoring history.
4. **`POST-IT-YOURSELF.md` is STALE (2026-08-14).** Three of its central claims
   were retracted — see the "Retracted" section at the bottom of `STATE.md`.
   Do not plan work from it.

Update `STATE.md` as part of the work, not as a write-up afterwards. If a
session ends and STATE.md didn't move, the next session starts blind.

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
6. **Thumbnail** — house style (traced judge over the courtroom plate,
   feathered, unstroked, no arrow) **and graded** so it pops at feed size.

Every one of these has silently degraded to "off" at some point because the
code accepted a missing asset and logged a line instead of failing. If a render
finishes and any of the six is absent, that is a bug, not a preference.

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
- Nothing has ever been published from this pipeline. "Ready" means rendered
  and verified on disk — not shipped. Track the shipped outcome, not the file.

## Where memory lives

Durable cross-project memory is at
`C:\Users\natha\.claude\projects\C--Users-natha\memory\` (start with
`MEMORY.md`). That store is scoped to the home directory but applies
everywhere — read it when starting substantial work here.
