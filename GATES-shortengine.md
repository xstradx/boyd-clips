# GATES — short engine

One command builds a publishable short and refuses to pass a bad one.
Nathan, 2026-08-31: *"You were supposed to make a short video engine"* and
*"make sure every short from now on gets that same pro level treatment"*.

OWNS: tools/short_engine.py

Every gate below is checked by `tools/short_engine.py --selftest`, which builds
its controls rather than pointing at old renders — a lesson from the thumbnail
gates, where comparing to stale files measured unrelated pixels.

---

- [ ] G1 — ONE ENTRY POINT. The engine exists and runs end to end from a case
      name, and the three older scripts are no longer the way in.
      CHECK: `python tools/short_engine.py --selftest 2>&1 | tail -40`
      EXPECT: `G1_OK`

- [ ] G2 — CAPTIONS ON THE SEAM. Every caption event straddles the split between
      the two tiles. His words: *"the words pop up, like, right on the split
      between the defendant and the judge"*. The Aug 29 file failed this —
      captions sat above the seam in Boyd's tile and below it in the
      defendant's, jumping between halves.
      CHECK: `python tools/short_engine.py --selftest 2>&1 | grep -c "G2_OK"`
      EXPECT: `1`

- [ ] G3 — ENTRANCE IS NOT SCALE-BASED. `blur` (defocus → sharp). He rejected
      bounce/punch/rise/scale twice, and a fifth variation of a rejected
      property is the "parameter, not approach" failure.
      CHECK: `python tools/short_engine.py --selftest 2>&1 | grep -c "G3_OK"`
      EXPECT: `1`

- [ ] G4 — LOUDNESS. Integrated between −15.0 and −13.0 LUFS, true peak ≤ −1.0
      dBTP. Measured, not assumed: the file staged in READY-TO-POST on
      2026-08-31 was −22.5 LUFS while a correct −14.4 master sat unused in
      READY-TO-REVIEW.
      CHECK: `python tools/short_engine.py --selftest 2>&1 | grep -c "G4_OK"`
      EXPECT: `1`

- [ ] G5 — CUTS MEASURED AGAINST THE AUDIO. No cut lands inside a word, and no
      cut leaves a discontinuity above the clip's own 99.9th-percentile
      transient. *"high short term retention is literally what makes or breaks
      the short"*.
      CHECK: `python tools/short_engine.py --selftest 2>&1 | grep -c "G5_OK"`
      EXPECT: `1`

- [ ] G6 — AUDIO FADES ACROSS HARD CUTS. Every join carries a short fade.
      CHECK: `python tools/short_engine.py --selftest 2>&1 | grep -c "G6_OK"`
      EXPECT: `1`

- [ ] G7 — FORMAT. 1080x1920, yuv420p, and audio/video durations within 100 ms.
      The old gate passed a broken file because both durations read 0.0 and
      "matched".
      CHECK: `python tools/short_engine.py --selftest 2>&1 | grep -c "G7_OK"`
      EXPECT: `1`

- [ ] G8 — GATES BLOCK. A failing build exits non-zero AND does not leave a file
      named like a deliverable. The prior audit found REFUSED shorts landing in
      READY-TO-POST as `_FINAL`, indistinguishable from passing ones.
      CHECK: `python tools/short_engine.py --selftest 2>&1 | grep -c "G8_OK"`
      EXPECT: `1`

- [ ] G9 — NO SILENT DEGRADE. A missing intro, watermark or caption file fails
      the build. CLAUDE.md: *"the code accepted a missing asset and logged a
      line instead of failing"*.
      CHECK: `python tools/short_engine.py --selftest 2>&1 | grep -c "G9_OK"`
      EXPECT: `1`

- [ ] G10 — EVERY GATE CAN FAIL. Each of G2, G4, G5, G7 is run against a
      deliberately-broken control and must REJECT it. A gate only ever seen
      passing is indistinguishable from one that cannot fail.
      CHECK: `python tools/short_engine.py --selftest 2>&1 | grep -c "G10_OK"`
      EXPECT: `1`
