"""Score a stretch of transcript for the things that actually travel.

Derived by reading ~65,000 words of transcript from @courtroomtime's top 8
videos (204k-891k views) against their bottom 6 (388-1,700), 2026-08-18. They
clip THIS docket - 318 of their 322 dated titles name Judge Boyd - so it is the
closest available ground truth, not an analogy.

NOT A GATE. Every signal here is a weight, and `score()` returns a number plus
the evidence behind it. Nothing is rejected on this alone. That is deliberate:
the last selection filter built here was a stack of hard gates tuned against
ten hand-picked cases, it passed all ten and rejected the two best renders in
the project, and it had to be thrown away. Weights can be re-fit when real view
counts exist; a gate silently deletes the cases that would have taught you
something.

The weights below are a STARTING POSITION from winner-vs-loser frequency, not
a finding. No clip this pipeline made has a recorded view count yet.

WHAT THE READING FOUND, ranked by how cleanly it separated the two groups
(count of videos containing the beat, winners of 8 / losers of 6):

    sustained back-and-forth, someone disputes Boyd    8 / 1
    Boyd sarcasm or mockery                            8 / 1
    Boyd catches a contradiction on the record         6 / 0
    someone cuffed, ejected or remanded on camera      6 / 2
    Boyd riffs - an extended vivid hypothetical        5 / 0
    defendant cries or begs                            6 / 2
    a third party is used as the lever                 6 / 2
    Boyd orders silence                                5 / 0
    Boyd RAISES HER VOICE                              1 / 0   <- noise

That last line is the useful one. The channel's whole reputation is that she
yells; across all eight winners it happens once. The register that carries is
flat, unhurried and declarative - "Deputy Laura, could you do me a favor" -
so a loudness or exclamation detector would find nothing. Do not build one.

The losers are not missing drama. One has tears, a remand and a life sentence.
It is missing an ANTAGONIST: the defendant agrees with everything, Boyd stays
gentle, and there is no video. Compliance is the killer, not low stakes.
"""

from __future__ import annotations

import re
from typing import Any

# Each signal: (name, weight, compiled pattern). Weights are proportional to
# the winner/loser separation above, then rounded — there is no more precision
# in n=14 than that.
SIGNALS: list[tuple[str, float, re.Pattern]] = [
    # Boyd quoting a document back at someone. 6/0 — the cleanest separator
    # that does not need turn structure to detect.
    ("receipt", 26, re.compile(
        r"\b(the (police )?report says|it says right here|says right here|"
        r"correct me if i'?m wrong|did i say (for )?anything else|"
        r"what i have (here|in front of me)|according to (the|this)|"
        r"that'?s not what (it|the report) says)\b", re.I)),

    # The rhetorical hammer. "guess what" 21x in winners, 1x in losers.
    ("hammer", 24, re.compile(
        r"\b(guess what|mhm+|why would you|so let'?s be honest|"
        r"those are the facts|do you think i|excuse me\.? (no|stop)|"
        r"stop interrupting)\b", re.I)),

    # Physical consequence, on camera. 6/2.
    ("consequence", 22, re.compile(
        r"\b(place the handcuffs|put the handcuffs|in cuffs|handcuff|"
        r"out of the courtroom now|take (him|her|them) into custody|"
        r"taken into custody today|remand|put (him|her) in the box|"
        r"bailiff|deputy,? could you)\b", re.I)),

    # Someone disputing Boyd. 8/1 by turn analysis; this is the lexical proxy,
    # and it is the weakest part of this module — the real signal is turn
    # structure, which needs diarisation. See dispute_turns() below.
    ("dispute", 20, re.compile(
        r"\b(that'?s not true|respectfully|but i (did|didn'?t|was|have)|"
        r"i don'?t recall|i understand,? but|no ma'?am,? but|"
        r"that'?s incorrect|i never said)\b", re.I)),

    # The extended vivid hypothetical — grocery store, KFC, the movie. 5/0.
    # Detected by length in dispute-free prose rather than by keyword, since
    # the subject changes every time. See long_riff().
    ("riff", 16, None),  # handled separately

    # 6/2. Note this is NOT the top signal, despite being the obvious one.
    ("begging", 12, re.compile(
        r"\b(please don'?t send me|i'?m begging|beg(ging)? you|"
        r"(started|starts|began|begins) (to )?cry|crying|in tears|sobbing|"
        r"one more chance|please your honor)\b", re.I)),

    # A mother, girlfriend or officer used as the lever. 6/2.
    ("third_party", 10, re.compile(
        r"\b(your (mother|mom|momma|girlfriend|wife|husband|father|dad)|"
        r"bringing your mom|she'?s here today|he'?s here today|"
        r"who is that with you|step (up|forward))\b", re.I)),
]

RIFF_MIN_WORDS = 40


def long_riff(text: str) -> int:
    """Count stretches of 40+ uninterrupted words — Boyd's hypotheticals.

    Keyword matching cannot find these; the subject is different every time
    (a grocery checkout, KFC, the middle of a movie). What is constant is the
    SHAPE: she holds the floor for a long, unbroken run. Splitting on the
    transcript's own turn markers and measuring run length finds it without
    needing to know what she is talking about.
    """
    runs = re.split(r">>|\n\n", text)
    return sum(1 for r in runs if len(r.split()) >= RIFF_MIN_WORDS)


def dispute_turns(text: str) -> int:
    """Alternations at '>>' markers — a proxy for back-and-forth density.

    Honest limitation: '>>' marks a change of speaker, not who. It cannot tell
    Boyd being contradicted from two attorneys conferring. It is a density
    measure, and density is the part of the 8/1 finding that is measurable
    without diarisation.
    """
    return text.count(">>")


def hot_moments(words: list, start_s: float, end_s: float,
                limit: int = 12) -> list[float]:
    """Timestamps where Boyd is delivering a line worth being photographed on.

    Nathan, 2026-08-18: "judge boyd could be bigger or look more pissed."

    Size is a constant. Expression is not — and it cannot be got by scoring
    pixels, because "annoyed" and "listening" are the same face to an edge
    detector, which is why frame choice has been wrong repeatedly. The previous
    heuristic ranked frames by edge energy across the whole canvas and its
    spread across nine candidates was 1.7%; it was choosing noise.

    The words know, though. She is animated at the moment she says the cutting
    line, so instead of guessing from the image, find WHEN the hammer and
    receipt patterns fire in the transcript and photograph her there. Same
    signals the clip scorer uses — no new model, no expression classifier.

    Returns source-time timestamps, best first, nudged 0.6s late so the frame
    lands mid-delivery rather than on the intake breath.
    """
    tokens = [w for w in words if start_s <= getattr(w, "t", 0.0) <= end_s]
    if not tokens:
        return []

    # Rebuild short rolling phrases so multi-word patterns can match.
    hits: list[tuple[float, float]] = []
    WINDOW = 12
    for i in range(len(tokens)):
        phrase = " ".join(t.w for t in tokens[i:i + WINDOW])
        weight = 0.0
        for name, wt, pattern in SIGNALS:
            if pattern is None:
                continue
            if name in ("hammer", "receipt", "consequence") and pattern.search(phrase):
                weight += wt
        if weight:
            hits.append((weight, tokens[i].t + 0.6))

    hits.sort(key=lambda h: -h[0])
    out: list[float] = []
    for _, t in hits:
        # Keep them apart; ten frames of the same sentence is not a choice.
        if all(abs(t - u) > 2.5 for u in out):
            out.append(t)
        if len(out) >= limit:
            break
    return out


def score(text: str, *, weights: dict[str, float] | None = None) -> dict[str, Any]:
    """Score a transcript window. Returns the total plus what fired.

    Nothing here rejects anything. A zero score means these particular signals
    were absent, which is information, not a verdict.
    """
    w = dict(weights or {})
    hits: dict[str, int] = {}
    total = 0.0

    for name, weight, pattern in SIGNALS:
        weight = w.get(name, weight)
        if name == "riff":
            n = long_riff(text)
        elif pattern is not None:
            n = len(pattern.findall(text))
        else:
            n = 0
        if n:
            hits[name] = n
            # Diminishing returns: the second "guess what" in a clip adds far
            # less than the first, and without this a single tic dominates.
            total += weight * (1 + 0.35 * (min(n, 6) - 1))

    turns = dispute_turns(text)
    if turns:
        hits["turn_markers"] = turns
        total += min(turns, 40) * 0.8

    return {
        "score": round(total, 1),
        "hits": hits,
        "signals_present": len([k for k in hits if k != "turn_markers"]),
        # The read said 4 of 6 signals is where a clip becomes worth cutting.
        # Reported, not enforced.
        "meets_read_threshold": len([k for k in hits if k != "turn_markers"]) >= 4,
    }
