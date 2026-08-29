"""Snap proposed cut points onto real speech boundaries.

Nathan, on a short Opus planned: "it could just be cut just a tad bit better."
Measured on that short, every one of its five cuts was defective - three opened
between 1.5s and 3.1s INTO a sentence, four ended mid-word.

The cause is structural, not a prompting problem. Every cut point in the
pipeline originates in YouTube's auto-caption word timings. Those drift, and
more importantly they encode where a WORD is, never where a LINE starts or
lands. So a cut can open after the first syllable is already gone.

This module fixes it from the audio instead: silencedetect gives the real speech
bursts, and each proposed boundary is pulled onto the nearest one.

Two deliberate asymmetries, because a cut is not symmetric to the ear:

  PRE_ROLL is small. Opening a hair early sounds intentional; opening a hair
  late clips the first consonant and sounds broken.

  HOLD is much larger. On this material the beat AFTER a line is where the
  comedy is - the judge's pause, the defendant's silence. Cutting on the last
  word kills it. Nathan's own note about the monkey riff was that he wanted
  more of the exchange, not less.

Nothing here runs silently over hand-placed cuts. make_short renders exactly
what it is handed; refinement is applied where a cut was proposed by a machine
(Opus plans, moment boundaries) or asked for explicitly in the editor.
"""

from __future__ import annotations

from pathlib import Path

PRE_ROLL = 0.12      # open this far before the first phoneme
HOLD = 0.38          # let the line land before cutting
MAX_PULL = 6.0       # never drag a boundary further than this to find speech
MIN_GAP = 0.10       # keep at least this much of a silence between neighbours


def speech_spans(silences: list, t0: float, t1: float) -> list:
    """Invert silent spans into speech spans across [t0, t1]."""
    out, cur = [], t0
    for a, b in silences:
        if b <= t0 or a >= t1:
            continue
        if a > cur:
            out.append((cur, min(a, t1)))
        cur = max(cur, b)
    if cur < t1:
        out.append((cur, t1))
    return [(a, b) for a, b in out if b - a > 0.05]


def _burst_at(spans: list, t: float):
    """The speech burst containing t, else None."""
    for a, b in spans:
        if a <= t <= b:
            return (a, b)
    return None


def _prev_end(spans: list, t: float):
    best = None
    for a, b in spans:
        if b <= t:
            best = b
    return best


def _next_start(spans: list, t: float):
    for a, b in spans:
        if a >= t:
            return a
    return None


def refine(a: float, b: float, silences: list, span: tuple | None = None,
           fine: list | None = None) -> tuple:
    """Return a snapped (a, b) plus a note describing what moved.

    Times are in the same clock as `silences` - file time throughout.

    `fine` is an optional second silence pass at a shorter minimum duration -
    the gaps BETWEEN WORDS rather than between lines. It is only consulted when
    a boundary cannot be resolved against the line-level pass, which happens
    when someone talks straight through for longer than MAX_PULL. Landing on a
    word gap is not as good as landing on the end of a line, but it is much
    better than landing mid-word.
    """
    lo = (span or (a - 30.0, b + 30.0))[0]
    hi = (span or (a - 30.0, b + 30.0))[1]
    spans = speech_spans(silences, min(lo, a - 30.0), max(hi, b + 30.0))
    if not spans:
        return a, b, "no speech detected; left alone"

    a0, b0 = a, b
    notes = []

    # ---- IN: never open mid-sentence ----
    burst = _burst_at(spans, a)
    if burst:
        pulled = burst[0]
        if a - pulled <= MAX_PULL:
            a = pulled                                  # back to the line's start
            notes.append(f"in -{a0 - a:.2f}s to the start of the line")
        else:
            nxt = _next_start(spans, a)
            if nxt is not None and nxt - a <= MAX_PULL:
                a = nxt
                notes.append(f"in +{a - a0:.2f}s to the next line")
    else:
        nxt = _next_start(spans, a)
        if nxt is not None and nxt - a <= MAX_PULL:
            if nxt - a > 0.30:                          # opening on dead air
                a = nxt
                notes.append(f"in +{a - a0:.2f}s past dead air")

    a = max(0.0, a - PRE_ROLL)

    # ---- OUT: never cut mid-word; hold for the beat after ----
    burst = _burst_at(spans, b)
    if burst:
        pushed = burst[1]
        if pushed - b <= MAX_PULL:
            b = pushed                                  # let the line finish
            notes.append(f"out +{b - b0:.2f}s to the end of the line")
        else:
            prev = _prev_end(spans, b)
            if prev is not None and b - prev <= MAX_PULL and prev > a + 1.0:
                b = prev
                notes.append(f"out -{b0 - b:.2f}s back off the word")
            elif fine:
                # continuous speech: settle for the nearest gap between words
                fs = speech_spans(fine, min(lo, a - 30.0), max(hi, b + 30.0))
                wb = _burst_at(fs, b)
                if wb and wb[1] - b <= 1.5:
                    b = wb[1]
                    notes.append(f"out +{b - b0:.2f}s to a word gap")
                else:
                    pw = _prev_end(fs, b)
                    if pw is not None and b - pw <= 1.5 and pw > a + 1.0:
                        b = pw
                        notes.append(f"out -{b0 - b:.2f}s to a word gap")
    b = b + HOLD

    # do not run into the next speaker
    nxt = _next_start(spans, b - HOLD + 0.01)
    if nxt is not None and b > nxt - MIN_GAP:
        b = max(b - HOLD + 0.05, nxt - MIN_GAP)

    if b - a < 0.5:
        return a0, b0, "would collapse; left alone"
    return a, b, ("; ".join(notes) if notes else "already on the boundaries")


def refine_all(segs: list, silences: list, fine: list | None = None) -> list:
    """Refine a list of (a, b) file-time segments. Returns (a, b, note) triples."""
    return [refine(a, b, silences, None, fine) for a, b in segs]


LIMIT_S = 58.0       # under YouTube's 60, with room for the sting


def fit_to_limit(segs: list, silences: list, fine: list | None = None,
                 limit: float = LIMIT_S) -> tuple:
    """Bring a refined plan under `limit` without breaking its boundaries.

    Refining lengthens a plan - it opens earlier and holds longer - so a plan
    that measured 58s from transcript timings can finish at 70s. Asking the
    model to allow for that does not work: it cannot know how much any given
    cut will move. So it is done here, deterministically.

    The move is always to pull the END of the longest clip back to the previous
    real boundary, never to shave an arbitrary number of seconds off. That keeps
    every cut landing where speech actually stops.
    """
    segs = [list(x[:2]) for x in segs]
    notes = []
    guard = 0
    while sum(b - a for a, b in segs) > limit and guard < 60:
        guard += 1
        k = max(range(len(segs)), key=lambda i: segs[i][1] - segs[i][0])
        a, b = segs[k]
        spans = speech_spans(silences, a - 5.0, b + 5.0)
        target = _prev_end(spans, b - HOLD - 0.05)
        if target is None or target <= a + 1.5:
            if fine:
                fs = speech_spans(fine, a - 5.0, b + 5.0)
                target = _prev_end(fs, b - HOLD - 0.05)
            if target is None or target <= a + 1.5:
                break                                   # nothing safe left to cut
        new_b = target + HOLD
        if new_b >= b - 0.05:
            break
        notes.append("clip %d shortened %.1fs to the previous boundary" % (k + 1, b - new_b))
        segs[k][1] = new_b
    return [tuple(x) for x in segs], notes
