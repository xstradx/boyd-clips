# Gates: background regeneration — real people, controlled room

Nathan, 2026-08-29: *"depending on how good you regeneration is maybe you could
regenerate the backgrounds every time and you will have full control over the
lighting ofc because youre remaking it yourself with the real reference and know
exactly what to change ... instead of guessing pls get it correct"*

Scope: matte the real people out of the courtroom frame, generate a controlled
background behind them, composite so they sit in it convincingly — and never
alter a single pixel of any real person's face.

## Why this shape, and what it is NOT

Measured 2026-08-29 against the 9,800-view Pikzels thumbnail: **it regenerates
the person, it does not upscale them.** Judge Boyd's eyes come back BRIGHT BLUE
where hers are brown, her glasses change from rounded burgundy frames to gold
cat-eye, and the skin is poreless. Eye colour does not change between hearings,
so that difference is diagnostic and not explained by different footage.

Nathan's proposal splits the problem exactly right: **regenerate the ROOM, keep
the PERSON.** That buys the lighting control that makes the reference look good,
while the faces stay real — which is the channel's only structural advantage
over the AI-slop courtroom channels the practitioner community mocks by
consensus, and it avoids publishing an altered depiction of a sitting judge in a
criminal proceeding.

## What is actually on this machine (probed, not assumed)

- **ComfyUI** at `C:\Users\natha\AI-Tools\ComfyUI` — installed, `models/*` empty.
- **Fooocus** at `C:\Users\natha\AI-Tools\Fooocus` — installed, and its venv has
  **torch 2.10.0+cu128 with cuda True**, so it is GPU-capable today.
- **Wan2GP** at `C:\Users\natha\Wan2GP` — `wan2.1_text2video_1.3B` (2.68 GB) and
  **SAM ViT-H** (1.19 GB) for masking.
- **No image-generation checkpoint anywhere on C: or D:** — searched for
  `*.safetensors` / `*.ckpt` over 500 MB. SDXL/Flux/SD1.5 all absent.
- Already present and proven in this repo: BiRefNet matting, ViTMatte-S refine,
  realesr-general-x4v3, OpenCV, PIL, scipy.

So generation is possible locally and free, but a checkpoint has to be
downloaded first. That is a download, not a purchase.

- [ ] G1: a local image-generation backend produces a real image, on the GPU, free
  CHECK: python scripts/bgregen.py selftest-backend
  EXPECT: BACKEND_READY
  EVIDENCE: pending

- [x] G2: the people are matted out and their FACES ARE UNTOUCHED
      — pixel-identical, not "looks the same"
  CHECK: python scripts/bgregen.py selftest-faces-untouched
  EXPECT: FACES_BIT_IDENTICAL
  EVIDENCE: MET. exit 0. Replaced the ENTIRE background with flat magenta on a
    real 1280x720 courtroom frame carrying 2 detected faces; max absolute pixel
    difference over the person's opaque pixels = 0. Output kept at
    work/bgregen/faces_untouched.png.
    This gate FAILED first at max diff 240, and the fault was the gate, not the
    compositor: face boxes are padded 30%, so they necessarily contain
    background, and background is exactly what is being replaced. Face 0 was
    only 53% covered by the person's matte. Corrected to compare only pixels
    where alpha > 0.995 - the person, not the room.

- [x] G3: CONTROL — the face check must FAIL on a deliberately altered face,
      or it proves nothing
  CHECK: python scripts/bgregen.py selftest-faces-control
  EXPECT: CONTROL_DETECTED_ALTERATION
  EVIDENCE: MET. exit 0. Alters ONE face by +1 code value on a SINGLE channel,
    restricted to pixels the person actually occupies, and the checker reports
    max diff 1 - detected. The negative control also holds: an identical copy
    still passes at max diff 0. So G2's pass is not vacuous; the invariant is
    sensitive to the smallest possible alteration, which is well below anything
    a relight would do.

- [ ] G4: a regenerated background composites with the real subjects and the
      result still satisfies every R1-R27 constraint
  CHECK: python scripts/thumbdoctor.py diagnose work/bgregen/OUT.jpg
  EXPECT: no defects
  EVIDENCE: pending

- [ ] G5: the composite is measurably better than the current build on the
      rubric eye, scored on the RENDERED file
  EVIDENCE: pending

- [ ] G6: lighting on the subject is consistent with the generated room —
      measured, not eyeballed (direction and colour temperature agree)
  EVIDENCE: pending

## The rule this must never break

`spec/THUMBNAIL_RUBRIC.md` limits every fix to **frame, crop, type, or grade**.
Background regeneration is a fifth category and is allowed ONLY because it never
touches a person. G2 and G3 exist to make that testable rather than promised: G2
asserts the face pixels are bit-identical to the source frame, and G3 proves the
checker can actually detect an alteration by feeding it one on purpose.
