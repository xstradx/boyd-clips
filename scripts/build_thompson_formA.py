"""Re-cut the Thompson short as CONTENT_SPEC §3 Form A, across both sittings.

The shipped short was Form B — one contiguous 53s stretch from the first
sitting — and it ended on the defendant's claim that his ex-wife, children,
sister and nieces had been murdered, with that claim unchallenged. The court
recessed, checked, found no record of any of it, and said so on the record. A
short that stops before the check leaves an unverified quintuple-murder claim
standing as fact about a named person.

The original analysis was not wrong to pick Form B: it only ever saw sitting 1,
and within sitting 1 there genuinely is no turn. Its own note says a four-beat
build "would require either an inferior hook or reordering material — which is
prohibited". Both sittings in scope, the four beats exist in chronological order
and nothing has to be manufactured, so Form A is available and is the honest cut.

Beats are written out explicitly rather than re-derived by the model, because
the in/out points were chosen by reading the word-level transcript and the
choice of where the hook lands is editorial.

    python scripts/build_thompson_formA.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from boydclips import render                                    # noqa: E402
from boydclips.config import load_config                        # noqa: E402
from boydclips.transcribe import Transcript                     # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work" / "JgvW7oCQxuI" / "JgvW7oCQxuI_6698_6674-8866.mp4"
TRANSCRIPT = ROOT / "work" / "JgvW7oCQxuI" / "JgvW7oCQxuI.transcript.json"
REVIEW = ROOT / "out" / "review" / "2026-04-27_JgvW7oCQxuI_6698"

# ffprobe on SOURCE returns exactly 2192.0s and the section was requested as
# 6674-8866, so the file starts precisely at 6674 with no keyframe slop.
OFFSET = 6674.0

# (start, end, why) in absolute source time.
BEATS = [
    # HOOK — first frame is "Wait", not a breath. Runs through the full
    # escalation: ex-wife, children, sister, nieces.
    (6930.85, 6943.60, "HOOK: 'Wait, you're saying your ex-wife and your children were killed?'"),
    # STAKES/SETUP — the judge stops the hearing to check it, and sends him to
    # sit down. Ending the beat on "we'll see what's going on with that" makes
    # the recess legible as a cut rather than hiding it.
    (6949.85, 6959.80, "SETUP: 'That should be easy to verify... we'll Google.'"),
    # TURN — 22 minutes later, on the record, nothing found.
    (8313.90, 8321.60, "TURN: 'Google search of all names didn't reveal any murders'"),
    # BUTTON — the judge's decisive line, and the direct answer to the hook.
    (8560.25, 8564.40, "BUTTON: 'you're saying that these people are deceased, I don't believe it.'"),
]


def main() -> int:
    if not SOURCE.is_file():
        print(f"missing source: {SOURCE}", file=sys.stderr)
        return 1

    cfg = load_config(ROOT / "config" / "pipeline.yaml")
    sh_cfg = cfg.require("output.short")
    transcript = Transcript.from_json(TRANSCRIPT.read_text(encoding="utf-8"))

    segments = [render.Segment(a, b) for a, b, _ in BEATS]
    total = sum(s.duration for s in segments)
    for (a, b, why), seg in zip(BEATS, segments):
        print(f"  {seg.duration:5.2f}s  {why}")
    print(f"  ------\n  {total:5.2f}s of footage + end card "
          f"(spec: 25-59s, target 45s)")
    if not 25.0 <= total <= 59.0:
        print(f"REFUSING: {total:.1f}s is outside the spec's 25-59s window",
              file=sys.stderr)
        return 1

    # Chronological order is a hard rule — a short compresses a case, it never
    # rearranges it. Asserted rather than assumed, since the beats are hand-written.
    starts = [s.start_s for s in segments]
    if starts != sorted(starts):
        print("REFUSING: beats are not in chronological order", file=sys.stderr)
        return 1

    crop = render.detect_content_crop(SOURCE)
    bg_crop = crop or render.detect_content_crop(SOURCE, min_agreement=0.25)
    mode, caption_margin = render.choose_vertical_layout(SOURCE, crop, sh_cfg)
    print(f"  framing: crop={crop} mode={mode} caption_margin={caption_margin}")

    cap_cfg = dict(sh_cfg.get("captions", {}))
    cap_cfg["margin_v"] = caption_margin
    words = []
    elapsed = 0.0
    for seg in segments:
        for w in transcript.slice(seg.start_s, seg.end_s):
            words.append(type(w)(t=elapsed + (w.t - seg.start_s), w=w.w))
        elapsed += seg.duration

    ass_path = render.build_ass(
        words, 0.0, elapsed, cap_cfg,
        cfg.get("packaging.short.end_card"),
        REVIEW / "captions_formA.ass",
    )

    out = REVIEW / "short_formA.mp4"
    dur = render.render_short(
        SOURCE, OFFSET, segments, sh_cfg, ass_path, out,
        crop=crop, bg_crop=bg_crop,
    )
    print(f"  rendered {dur:.1f}s -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
