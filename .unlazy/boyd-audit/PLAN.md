# Boyd Clips reliability audit — PLAN

Scope name: `boyd-audit`. Started 2026-08-29.
**READ-ONLY on the pipeline.** No leaf may write outside its own findings file.
Nathan's instruction: audit first, change nothing, present every proposed change
with the reason it should happen. Stated priority: **make the output far more
reliable.**

## Contract every leaf obeys

Findings file format — the verifier enforces it, a block missing any field fails:

```
## F<n>: <one-line claim>
SEVERITY: blocker | high | medium | low
EVIDENCE: <the command actually run and its decisive output, or file:line quoted>
WHY-IT-MATTERS: <the consequence for shipping a video>
PROPOSAL: <the change, or NONE>
COST: <effort + what it risks breaking>
```

Rules binding every leaf:

- **NON-INTROSPECTIVE.** No finding from recall. Every claim carries a command
  that was run or a file:line that was read. No source, no finding — strike it,
  do not soften it to a maybe.
- **Read-only.** Do not edit, delete, move or run anything that writes to the
  pipeline. Rendering, downloading and uploading are forbidden this pass.
- Prefer `ffprobe`/`PIL`/`sqlite3` over reading code when a claim is about an
  artifact. A claim about a shipped file must be measured off that file.
- Severity is about SHIPPING: blocker = a video goes out wrong or not at all.
- If a suspicion cannot be measured, say "not measured" and name what would
  measure it. Do not fill the gap.

## Ownership — disjoint, one findings file each

| leaf | owns | territory |
|---|---|---|
| leaf-1.1 | findings/leaf-1.1.md | ingest + transcription + store |
| leaf-1.2 | findings/leaf-1.2.md | selection + scoring |
| leaf-1.3 | findings/leaf-1.3.md | render path + the six mandatory elements |
| leaf-2.1 | findings/leaf-2.1.md | spec/doc vs code drift |
| leaf-2.2 | findings/leaf-2.2.md | dead-code + duplicate-script census |
| leaf-3.1 | findings/leaf-3.1.md | silent-failure hunt |
| leaf-3.2 | findings/leaf-3.2.md | verification + test coverage |
| leaf-3.3 | findings/leaf-3.3.md | state, provenance, reproducibility |
| leaf-4.1 | findings/leaf-4.1.md | re-measure every claimed open defect |
| leaf-4.2 | findings/leaf-4.2.md | what is actually live on the channel |
| leaf-5.1 | findings/leaf-5.1.md | intent archaeology — what each build attempt was for |
| leaf-5.2 | findings/leaf-5.2.md | the human-input surface per finished video |
| leaf-5.3 | findings/leaf-5.3.md | external: how this is actually built in 2026 |

## States

All leaves are independent and read-only, so all start READY and dispatch
together. No leaf depends on another; the driver integrates at branch level.

| leaf | state |
|---|---|
| leaf-1.1 | READY |
| leaf-1.2 | READY |
| leaf-1.3 | READY |
| leaf-2.1 | READY |
| leaf-2.2 | READY |
| leaf-3.1 | READY |
| leaf-3.2 | READY |
| leaf-3.3 | READY |
| leaf-4.1 | READY |
| leaf-4.2 | READY |
| leaf-5.1 | READY |
| leaf-5.2 | READY |
| leaf-5.3 | READY |

## Branches

- node-1 pipeline (1.1, 1.2, 1.3)
- node-2 honesty (2.1, 2.2)
- node-3 reliability (3.1, 3.2, 3.3)
- node-4 reality (4.1, 4.2)
- node-5 intent and the road to unattended (5.1, 5.2, 5.3)

## The outcome, restated — added 2026-08-29 after Nathan clarified

Not "audit the code". The thing he is chasing:

> a Judge Boyd video maker — clip, short, title, thumbnail — that runs without
> him putting in much of any input, once the styles and rules are locked in.

His words for the ambition on top: *"some self learning"*, *"a lightweight
automated research team"*, *"a complex background smart system that pays
attention to what thumbnails work or if the majority of competitors start doing
[something]."* **Those are him painting a picture, not filing requirements** —
he said so himself: *"i pitch a lot of ideas to paint you a picture and
sometimes you run with an example."* leaf-5.3 goes and finds out what the real
version of that is instead of implementing the sketch.
- root: one breakdown for Nathan, every proposal carrying its reason and cost.
