# Codebase merge — 2026-08-31

Three overlapping codebases became one engine plus one deliberately separate one.

## BEFORE
| where | lines | verdict |
|---|---|---|
| `boyd-clips/tools/thumbeng/` | 10,015 | best methodology, all selftests pass — **KEPT** |
| `Projects/thumbnail-engine/` | 1,470 | duplicated 4 of 6 stages, worse — **RETIRED** |
| `boyd-clips/tools/thumb_measure.py` + 4 tools | ~900 | superseded — **RETIRED** |

Three separate measurement modules existed: 1868 / 284 / 213 lines. Nothing
forced them to agree, and they didn't.

## WHAT MOVED
- `ingest.py` — video → transcript + candidate frames. The only thing in this
  repo that could take a VIDEO rather than an image.
- `understand.py` — names the niche and a search query FROM the video, so
  `harvest --query` no longer has to be typed by hand.
- `variety.py` (NEW) — the one check nothing else does: how similar is this to
  YOUR OWN back catalogue. Ported from the retired `verify_variety.py`.

## WHAT WAS DELETED AND WHY
| retired | superseded by |
|---|---|
| `thumbnail-engine/measure.py` | `thumbeng/measure.py` (1868 lines, 133 features, 21 checks) |
| `thumbnail-engine/scout.py` | `thumbeng/harvest.py` (per-channel outlier baselines) |
| `thumbnail-engine/decide.py` | `thumbeng/grammar.py` (FDR-corrected, refuses to guess) |
| `thumbnail-engine/grade.py` | `thumbeng/critique.py` (provenance on every defect) |
| `thumbnail-engine/render.py` | nothing — it was a crop with white text |
| `tools/thumb_measure.py` and 4 dependents | `thumbeng/measure.py` + `thumbeng/variety.py` |

## STILL SEPARATE, ON PURPOSE
`Projects/hook-engine/` stays its own project. Nathan's call, 2026-08-31: the
hook problem appears in four places (long-form title, thumbnail text, Shorts
hook, TikTok opener) and inside a thumbnail pipeline it would serve one.

## ONE ENTRY POINT
    python -m tools.thumbeng.engine {ingest,understand,harvest,measure,styles,
                                     grammar,critique,all,status,selftest}

`critique --history "<glob>"` now runs the variety check inline.

## VERIFIED AFTER THE MERGE
All six module selftests PASS. `engine selftest` reports 6/6 — and the count is
now DERIVED from the module list, because it was hardcoded "5/5" and would have
kept saying 5/5 forever while silently never running variety.

## ONE LOOSE END
`Projects/thumbnail-engine/` could not be moved into `_retired_2026-08-31/`
("Device or resource busy"). It carries a `RETIRED.md` saying so. Move it when
nothing holds a handle. Its GATES.md / PLAN.md / spec/CONTROLS.md are still
worth reading — they record the measured findings and a control-design mistake.
