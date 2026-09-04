# GATES — the short renderer gets a TIMELINE

2026-09-03. Nathan: *"I think you're still going off of examples and not fixing
the problem inside the pipeline."* He is right.

## The structural defect

`tools/make_short.py:build()` takes ONE video and crops it into a 2-up:

    inputs = ["-i", src]
    fc = "[0:v]crop=W:top:0:0,GT[t];[0:v]crop=W:H-top:0:top,GB[b];[t][b]vstack..."

Every short the pipeline has ever produced is therefore a 2-up crop of a single
continuous courtroom video. The things his winning shorts are BUILT from cannot
be expressed at all:

| his 39k / 865k does | pipeline can express it? |
|---|---|
| tease card "Clip From Izzys Instagram Incoming..." | no |
| 9s full-bleed cutaway to outside footage | no |
| persistent corner label "court clip incoming" | no |
| mugshot / victim photo stills | no |
| source label "POLICE BODYCAM – DECEMBER 26, 2023" | no |
| "FULL VIDEO OUT NOW" end card + arrow | no |
| speaker name tag on a tile | no |

`card` exists but is a single static PNG overlaid on the one source at fixed
times — not an element in a sequence.

## The fix

A TIMELINE: an ordered list of heterogeneous elements, each normalised to
1080x1920 / same fps / same pix_fmt / with an audio track, concatenated, then
captioned as one piece.

    court   a 2-up span of a source video      (what exists today, now one element type)
    clip    an external video, fitted          (the IZZY93 cutaway)
    still   an image, optional slow push       (mugshot, victim photo, news screenshot)
    card    a full-frame text card             (the tease, the date card)

Overlays are per-element and declared, not hard-coded: corner label, speaker tag,
CTA. Captions come from aligning the FINAL audio, so they stay correct across cuts.

SCOPE: nothing is posted. Publishing stays a hard stop.

---

- [ ] G1  A timeline of all four element types renders to one playable file
      CHECK: `python tools/short_timeline.py --selftest-render`
      EXPECT: TIMELINE_RENDER_OK

- [ ] G2  Output is exactly 1080x1920, yuv420p, with audio, and its duration
      equals the sum of the declared element durations within 0.15s
      CHECK: `python tools/short_timeline.py --selftest-format`
      EXPECT: TIMELINE_FORMAT_OK
      (the CONTROL is a deliberately mismatched element list, which must FAIL)

- [ ] G3  Element boundaries are real cuts — the renderer actually changed the
      picture where the timeline says it does
      CHECK: `python tools/short_timeline.py --selftest-cuts`
      EXPECT: TIMELINE_CUTS_OK
      (measures frame difference at each declared boundary; the CONTROL is a
      timeline of two identical court elements, which must show NO cut and so
      must FAIL this check — an edge detector never seen to fail is not evidence)

- [ ] G4  A declared corner label / speaker tag / CTA is actually drawn
      CHECK: `python tools/short_timeline.py --selftest-overlays`
      EXPECT: TIMELINE_OVERLAY_OK
      (pixel test inside the declared box, against the same render without it)

- [ ] G5  A missing asset is refused with the path named, never silently skipped
      CHECK: `python tools/short_timeline.py --selftest-missing`
      EXPECT: TIMELINE_MISSING_OK

- [ ] G6  The existing single-source path still works — no regression
      CHECK: `python tools/short_chain.py --selftest`
      EXPECT: SELFTEST_PASS

- [ ] G7  Whole suite still green
      CHECK: `python tools/selftest_all.py`
      EXPECT: ALL_OK

- [ ] G8  MANUAL — a real short is rendered through the timeline with a card, a
      court span, a still and a CTA, and I have WATCHED it before showing him.

## Not gated, said out loud

- Whether the resulting short is good is his call. These gates prove the
  renderer can now express the structure; they say nothing about the edit.
- Sourcing the cutaway material is a separate problem (the heinous-case
  workflow). The renderer must not care where an asset came from.
