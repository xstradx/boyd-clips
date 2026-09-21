# -*- coding: utf-8 -*-
"""SHORTS_EDITOR_V2 — the mini-story planner behind the daily short.

WHAT THIS REPLACES. Before this module the daily short was whatever beats the
score-stage model wrote into `short_segments`, clamped by
`render.plan_short_segments` and rendered as a static two-tile stack. Nothing
checked that the beats told a story, nothing removed dead air or procedure
inside a beat, the framing never followed the speaker, and a short that failed
was reported as "beat plan rejected" with no reason a person could act on.

THE CONTINUITY RULE (Nathan, 2026-09-06, after the first Flores render).
The first version of this planner assembled beats: it walked back from the
payoff over the turns it liked, trimmed the front of the defendant's answer
to "the excuse sentence", and rendered Boyd's question followed by a line the
defendant said twenty seconds later about something else — a FALSE Q→A that
both clips being from the same hearing does not excuse. His rule, now the
law of this file:

    MAIN BODY = contiguous conversation with compression,
    not a montage of semantically guessed lines.

  * A declared cold-open teaser may come from another nearby point (the
    payoff line, repeated in place afterwards). After it, the body is ONE
    contiguous stretch of the source in order.
  * Inside the body only these may be removed: dead air, acknowledgments,
    repeated wording, clearly procedural filler. Nothing substantive is ever
    jumped over.
  * If a kept sentence ends in a genuine question, the next substantive kept
    sentence is the answer that actually followed it in the source
    (`question_answer` gate). If that answer is unusable the clip starts
    elsewhere; it never jumps to a better-scoring line.
  * Every interior cut is audited: the omitted transcript is recorded in the
    plan (`interior_cuts`) and the `continuity_gaps` gate fails the plan if
    any omitted sentence is substantive.

The only editorial freedom left is WHERE THE BODY STARTS (a turn start or a
Boyd opener within reach of the payoff) and WHERE IT ENDS (the payoff line,
optionally the rest of that riff and a short reaction). Every start/end pair
is a candidate; the 100-point rubric ranks them.

WHAT IT DOES NOT DO. It never invents a beat, never reorders, does not touch
BOYD_EDITORIAL_V2 scoring, does not publish, and runs no model — `judge` is
an optional callable so a model can re-rank candidates later; by default the
planner is deterministic so the tests are exact.

SCORE PROXIES ARE PROXIES. Hook/clarity/payoff/escalation/quote/visual are
computed from measurable transcript features. They rank candidates; they do
not prove a short is good. Nathan's review of rendered output is the judge.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from . import captions, layout, moments, render
from .render import Segment
from .transcribe import Word

RULESET = "SHORTS_EDITOR_V2"

SCORE_DIMENSIONS: dict[str, int] = {
    "hook": 25,        # immediacy: is the first line a question, a tell, an excuse, stakes?
    "clarity": 20,     # can a stranger follow it with no legal context?
    "payoff": 25,      # does the clip resolve on a real turn / receipt / answer?
    "escalation": 15,  # does tension rise (alternation, excuse -> response)?
    "quote": 10,       # is there a standalone quotable line?
    "visual": 5,       # can the frame follow the speakers (both identified)?
}
assert sum(SCORE_DIMENSIONS.values()) == 100

SPEAKER_BOYD = "boyd"
SPEAKER_DEFENDANT = "defendant"
SPEAKER_COUNSEL = "counsel"
SPEAKER_UNKNOWN = "unknown"

# Tunables with stated defaults; `output.short.planner` overrides any key.
# None of them is a rule Nathan set — they are the values the dry runs were
# built against and every one is meant to be revisited on rendered output.
DEFAULTS: dict[str, Any] = {
    "min_duration_s": 15.0,      # a complete 18 s story ships; nothing is padded to reach 25
    "max_duration_s": 59.0,      # platform ceiling, shared with the legacy planner
    "target_min_s": 25.0,        # the sweet spot; scoring nudges toward it, never pads
    "target_max_s": 60.0,
    "word_hold_s": 0.6,          # a word with no successor is assumed to last this long
    "cut_pre_s": 0.12,           # pre-roll before the first word of a range
    "cut_post_s": 0.18,          # tail after the last word of a range
    "dead_gap_s": 1.2,           # a pause longer than this inside the body is dead air
    "keep_gap_s": 0.35,          # ...and is shortened to keep this much on each side
    "max_window_s": 95.0,        # how far back from the payoff a start may sit (raw source time)
    "max_payoff_s": 22.0,        # the payoff riff is capped here (from its lead-in to its last kept line)
    "reaction_max_s": 4.0,       # the reaction after the payoff, kept only when this short
    "teaser_max_s": 3.0,         # cold-open teaser: the payoff line, no longer than this
    "allow_teaser": True,
    "hook_teaser_below": 14,     # only tease when the natural hook scores under this
    # THE HOOK FLOOR (added 2026-09-19). The only acceptance test used to be the
    # TOTAL >= min_score, so a candidate could ship a 7/25 opening on the back of
    # a 20/25 payoff — which is exactly what the rejected dAKO7myCd-g:8929 cut
    # did (hook 7, escalation 7, total 65, bundle `ready: true`, Nathan rejected
    # it). The recorded profile rule is that the opening IS the confrontation,
    # not a preamble to it, so the opening beat is now floored on its own
    # dimension instead of riding on the total. A declared cold-open teaser —
    # the payoff line played first and repeated in place, which is what the
    # heuristic path already builds via `hook_teaser_below` — satisfies the
    # floor, because it replaces the weak opening line on screen. 0 disables it.
    "hook_min_score": 14,
    "punch_zoom": 1.12,
    "max_punch_ins": None,
    "punch_in_min_spacing_s": 3.0,
    "max_accents": 2,
    "min_score": 55,             # a candidate under this is refused as "weak", explicitly
    "money_moment_window": 6,    # the editorial money moment wins a tie within this many points
    "rapid_exchange_s": 3.0,     # turns shorter than this in a run of >= rapid_alternations -> duo
    "rapid_alternations": 3,
    "sentence_gap_s": 0.6,       # a pause this long ends a sentence for the planner
    "canvas_h": 1920,
    "focus_share": 0.60,         # must match output.short.focus_share (render.duo_focus_filter)
    # Platform-safe band on the 1920 canvas: text must sit inside y 288..1248
    # (the same numbers config/pipeline.yaml documents for slot_margins).
    "safe_area": {"top": 288, "bottom": 1248},
}


def _cfg(cfg: dict[str, Any] | None) -> dict[str, Any]:
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULTS.items()}
    for k, v in (cfg or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update(v)
        else:
            out[k] = v
    return out


# ------------------------------------------------------------------ lexicons
#
# Copied, with provenance, from the manual chain so the daily planner and the
# hand tools agree on what "procedure" and "outcome" mean:
#   tools/pick_window.py  OUTCOME / NOT_OUTCOME / FILLER   (measured 2026-09-02)
#   src/boydclips/moments.py  JUDICIAL / BOILER / TELLS / CONFRONT / EXAMINATION

OUTCOME = [
    "this is what the court is going to do", "i'm going to sentence",
    "i sentence you", "years to court", "years in the",
    "adjudicate you", "adjudicates you", "adjudicated guilty",
    "grant the state's motion", "allegations true", "allegation true",
    "allegations are true", "allegation is true",
    "i find you guilty", "probation is revoked", "remanded", "i'm revoking",
    "the court finds", "sentenced to", "days in jail", "months in",
]
NOT_OUTCOME = ["deferred adjudication", "motion to adjudicate",
               "motion to proceed to adjudication", "adjudication of guilt"]
FILLER = [
    "names of all the tattoos", "how old are", "what are their ages",
    "do you have any drug issues", "are they living with you",
    "restitution hearing date", "community service", "reporting by zoom",
    "field visits", "parenting classes", "life skills", "anti-theft course",
    "date of birth", "your address", "phone number",
]
# Scheduling / clerking that is procedure in every hearing, and the call of
# the case (parties announce, the plea read back).
SCHEDULING = re.compile(
    r"\b(reset (it|this|the case)|next (setting|court date)|court date|sign (the|this|that|your)"
    r"|paperwork|the clerk|bailiff|raise your right hand|do you swear|so help you"
    r"|state your (full )?name|spell (your|that)|call(ing)? the next|next case"
    r"|have a seat|anything further|off the record|on the record|your honor,? (may|if) (i|we)"
    r"|(thank you|thanks),? (your honor|judge)|we'?ll be in recess|approach the bench"
    r"|parties announce|for the state( of texas)?|for the defendant|you entered a plea|plea bargain agreement"
    r"|punishment (is|to) be assessed|count (one|two|three)|affirmative finding|no contact with"
    r"|application for|state is silent|taking in(to)? consideration|chance to review)\b", re.I)

QUESTION = re.compile(r"\?\s*$|\b(why|how|what|when|where|who|did you|do you|are you|were you|is that|isn'?t that|have you|can you|could you)\b", re.I)
EXCUSE = re.compile(
    r"\b(i didn'?t know|i did not know|i was just|i thought|it wasn'?t (me|my)|nobody told me"
    r"|i couldn'?t|i tried|i was trying|my (phone|car|ride|job|boss) (got|was|is|had|broke|died|wouldn'?t)"
    r"|i lost|i forgot|i had no|i don'?t have (a|the|no|any)|they told me|he told me|she told me|i was told"
    r"|self[- ]defense|i didn'?t mean|i had to|i never (got|had|knew|received|heard)|i just (didn'?t|couldn'?t|forgot))\b", re.I)
RECEIPT = re.compile(
    r"\b(last time i checked|it says (right )?here|the report says|according to (the|your)|you told me"
    r"|correct me if i'?m wrong|so why|then why|guess what|you had a chance|but you (did|didn'?t|could|couldn'?t)"
    r"|the record (says|shows)|i have (it|the report|the paperwork) (right )?here|you (just )?said"
    r"|that'?s not what|didn'?t reveal|no record|is that (right|correct)\?)\b", re.I)
DEFERENTIAL = re.compile(r"^\W*(yes|no|yeah|okay|ok|correct|right)\b[,.]?\s*(ma'?am|sir|your honor|judge)?", re.I)
# Things only the bench says that JUDICIAL (moments.py) does not list — it was
# built to find riffs, not to label every sentence.
BENCH = re.compile(
    r"\b(back on the record|state versus|court is calling|what are you requesting|what is the state"
    r"|the court (is|will|has|would|can|cannot|finds?|going)|this court|the court'?s|court'?s going"
    r"|it'?ll be nice if i had|i can tell you|let me (just )?explain|my courtroom|good luck to you"
    r"|is there a proposed|find(s|ing)? the (violation|allegation)|you may proceed|you'?re asking (me|this court)"
    r"|do you still wish|knowing that|the motion to|so why shouldn'?t i|why shouldn'?t i"
    r"|you'?re (saying|telling me)|you (said|told me)|explain to me|so what does)\b", re.I)
# Vocabulary of the bench and the bar: Boyd's reasoning monologues are first
# person and read as the defendant on pronouns alone.
BENCH_VOCAB = re.compile(
    r"\b(probation|evidence|candidate|deferred|adjudicat\w+|sentenc\w+|the court|record|cases?|violation\w*"
    r"|plea|motion|the state|defense|attorney|counsel|prison|tdc|jail|supervision|conditions|revok\w+"
    r"|testimony|allegation\w*|offense|charged?|convict\w+|judgment|dismissed|terminated|community)\b", re.I)
# A short acknowledgment is never a payoff: "Okay. All right, you may proceed."
ACK = re.compile(
    r"^\W*((okay|ok|all right|alright|thank you|thanks|yes|no|yeah|yep|mhm|uh-huh|go ahead|you may proceed"
    r"|proceed|very well|sure|got it|good luck( to you)?|have a seat|ma'?am|sir|judge|your honor|please|correct"
    r"|right|i understand|understood|of course)[\s,.!?]*)+$", re.I)
COUNSEL = re.compile(
    r"\b(my client|the state (would|is|has|asks|recommends)|the defense|we'?d ask|we would ask|judge,|your honor,? (we|the state|my client)"
    r"|state'?s recommendation|plea (bargain|agreement|offer)|counsel|i represent)\b", re.I)
STAKES = re.compile(r"\b(\d+ (years?|months?|days?)|prison|jail|tdc|penitentiary|chance|deferred|revok\w+|lose|losing|custody|handcuffs)\b", re.I)
FILLER_TOKEN = re.compile(r"^(um+|uh+|uh-huh|mm+|hmm+|er+|ah+|huh)[,.!?]*$", re.I)
TERMINAL = re.compile(r"[.!?]+[\"”')]*$")

# tools/caption_short.py GLUE_FORWARD — used here only to pick content words
# when matching the editorial quote to transcript sentences.
GLUE_FORWARD = {
    "a", "an", "the", "my", "your", "his", "her", "our", "their", "its",
    "this", "that", "these", "those", "of", "to", "for", "in", "on", "at",
    "with", "from", "by", "into", "about", "and", "but", "or", "if", "so",
    "because", "when", "while", "is", "was", "are", "were", "be", "been",
    "am", "do", "does", "did", "have", "has", "had", "can", "could", "will",
    "would", "should", "you", "i", "he", "she", "we", "they", "it", "not",
    "no", "any", "some", "all", "more", "than", "as", "up", "out", "there",
    "you're", "i'm", "i've", "don't", "doesn't", "didn't", "haven't",
    "isn't", "aren't", "we're", "they're", "that's", "there's", "let",
}


def _norm(w: str) -> str:
    return w.strip().strip('.,!?";:“”\'').lower()


def _lower(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower())


def has_outcome(text: str) -> bool:
    t = _lower(text)
    for p in NOT_OUTCOME:
        t = t.replace(p, " ")
    return any(p in t for p in OUTCOME)


def is_ack(text: str) -> bool:
    return len(text.split()) <= 8 and bool(ACK.match(text.strip()))


def is_procedural(text: str) -> bool:
    """Clerical content — filler, boilerplate, scheduling, the call of the
    case. An acknowledgment ("No, ma'am.") is NOT procedural: short answers
    are the exchange. They are only refused as a PAYOFF (is_ack)."""
    t = _lower(text)
    if any(p in t for p in FILLER):
        return True
    if moments.BOILER.search(t) or moments.EXAMINATION.search(t):
        return True
    words = len(t.split())
    hits = len(SCHEDULING.findall(t))
    return hits > 0 and (words <= 12 or hits * 8 >= words)


def procedural_share(text: str) -> float:
    """Fraction of a turn's words that sit in procedural sentences. A whole
    turn is procedure only when most of it is."""
    sents = [x for x in re.split(r"(?<=[.!?])\s+", text.strip()) if x.strip()]
    if not sents:
        return 0.0
    total = sum(len(x.split()) for x in sents) or 1
    proc = sum(len(x.split()) for x in sents if is_procedural(x))
    return proc / total


# ------------------------------------------------------------------ words / turns


@dataclass
class TWord:
    i: int          # index in the case word list
    t: float        # start, source time
    e: float        # end, source time (next start, capped by word_hold_s)
    w: str          # token as spoken (">>" markers stripped)
    turn: int = -1


@dataclass
class Turn:
    idx: int
    words: list[TWord]
    speaker: str = SPEAKER_UNKNOWN
    speaker_evidence: str = ""
    speaker_margin: float = 0.0
    marker: bool = False      # started by a '>>' in the captions (a real change), not by text

    @property
    def start_s(self) -> float:
        return self.words[0].t

    @property
    def end_s(self) -> float:
        return self.words[-1].e

    @property
    def duration(self) -> float:
        return self.end_s - self.start_s

    @property
    def text(self) -> str:
        return " ".join(w.w for w in self.words)

    @property
    def procedural(self) -> bool:
        return procedural_share(self.text) >= 0.5

    @property
    def ack(self) -> bool:
        return is_ack(self.text)

    @property
    def tells(self) -> list[str]:
        t = self.text
        return [lab for rx, _w, lab in moments._TELLS if rx.search(t)]

    @property
    def question(self) -> bool:
        return bool(QUESTION.search(self.text))

    @property
    def excuse(self) -> bool:
        return bool(EXCUSE.search(self.text))

    @property
    def receipt(self) -> bool:
        return bool(RECEIPT.search(self.text))

    @property
    def confront(self) -> int:
        return len(set(m.group(0).lower() for m in moments.CONFRONT.finditer(self.text)))


def timed_words(words: Sequence[Word], lo: float, hi: float, hold_s: float = 0.6) -> list[TWord]:
    """Case words with END times. Transcript words carry only a start; the end
    is the next word's start, capped at `hold_s` so a word before a pause is
    not stretched across the pause."""
    idx = [i for i, w in enumerate(words)
           if lo <= w.t <= hi and w.w.strip() and not re.fullmatch(r"\[.*\]", w.w.strip())]
    idx.sort(key=lambda i: (words[i].t, i))
    out: list[TWord] = []
    for k, i in enumerate(idx):
        w = words[i]
        nxt = words[idx[k + 1]].t if k + 1 < len(idx) else w.t + hold_s
        e = min(nxt, w.t + hold_s)
        if e <= w.t:
            e = w.t + 0.05
        out.append(TWord(i=i, t=float(w.t), e=float(e), w=w.w.strip()))
    return out


def _sentence_starts(words: list[TWord], gap_s: float) -> set[int]:
    starts = {0}
    for k in range(1, len(words)):
        p = words[k - 1]
        if TERMINAL.search(p.w) or (words[k].t - p.e) > gap_s:
            starts.add(k)
    return starts


def _sentences(words: list[TWord], gap_s: float) -> list[list[TWord]]:
    starts = sorted(_sentence_starts(words, gap_s))
    out = []
    for a, b in zip(starts, starts[1:] + [len(words)]):
        if b > a:
            out.append(words[a:b])
    return out


def _label_sentences(sents: list[list[TWord]], min_margin: float = 0.6) -> list[str | None]:
    """Per-sentence speaker labels from the text, forward-filled: a sentence
    the classifier cannot read ("All right.") belongs to whoever was just
    speaking. Returns None everywhere when nothing in the turn is readable."""
    raw: list[str | None] = []
    for k, s in enumerate(sents):
        txt = " ".join(w.w for w in s)
        head = s[0].w
        # A fragment that starts lowercase after a pause ("that would tell me
        # how") is the same sentence continuing across the pause.
        if k > 0 and head[:1].islower() and not TERMINAL.search(sents[k - 1][-1].w):
            raw.append(None)
            continue
        spk, _ev = classify_turn(txt)
        if spk == SPEAKER_UNKNOWN or classify_margin(txt) < min_margin:
            raw.append(None)
        else:
            raw.append(spk)
    known = [x for x in raw if x]
    if not known:
        return raw
    # A SHORT lone sentence that disagrees with two confident neighbours on
    # a thin margin is a misread, not a speaker change. Kept narrow.
    for k in range(1, len(raw) - 1):
        a, b, c = raw[k - 1], raw[k], raw[k + 1]
        if a and c and a == c and b and b != a and len(sents[k]) <= 6:
            txt = " ".join(w.w for w in sents[k])
            strong = min(classify_margin(" ".join(w.w for w in sents[k - 1])),
                         classify_margin(" ".join(w.w for w in sents[k + 1])))
            if classify_margin(txt) < 1.0 and strong >= 1.5:
                raw[k] = a
    out: list[str | None] = []
    cur = known[0]
    for x in raw:
        if x:
            cur = x
        out.append(cur)
    return out


def has_speaker_structure(words: Sequence[Any], min_terminals_per_50: float = 1.0) -> bool:
    """Whether the transcript text can be split into speaker turns at all.

    The 2024 dockets' auto-captions (bHAuH5U4NYI, dAKO7myCd-g, jdzBCVXENUk,
    measured 2026-09-06) carry no '>>' markers and no punctuation at all:
    1,489 lowercase words in Alonzo's hearing, zero terminals. Text splitting
    then yields ONE turn and the planner refuses a case that has a story.
    Flores-style captions (4 markers, punctuated) and marker-rich ones (126
    in Robinson) read as structured."""
    toks = [str(getattr(w, "w", w)) for w in words]
    n = len(toks)
    if n == 0:
        return False
    markers = sum(1 for t in toks if t.startswith(">>"))
    terminals = sum(1 for t in toks if TERMINAL.search(t))
    return markers >= 1 or terminals >= min_terminals_per_50 * n / 50.0


def _diar_split(pieces: list[tuple[bool, list[TWord], str | None]],
                diar: Sequence[tuple[float, str]], min_words: int = 2,
                min_gap_s: float = 1.0) -> list[tuple[bool, list[TWord], str | None]]:
    """Split text pieces at diarised speaker CHANGES. A change at time b cuts
    before the first word starting at/after b - 0.15 s; both sides keep at
    least `min_words`, and cuts closer than `min_gap_s` to the previous cut
    are ECAPA jitter, not a second change. Labels are left to label_speakers
    (which reads the diarisation at each turn's midpoint)."""
    marks = sorted(diar)
    bounds = [t for k, (t, who) in enumerate(marks) if k > 0 and who != marks[k - 1][1]]
    if not bounds:
        return pieces
    out: list[tuple[bool, list[TWord], str | None]] = []
    for marker, ws, lab in pieces:
        # The text label of an unstructured blob describes the whole blob, so
        # it is dropped; label_speakers re-reads each part (text, then diar).
        if len(ws) < 2 * min_words:
            out.append((marker, ws, None))
            continue
        lab = None
        cur: list[TWord] = list(ws)
        first = marker
        last_cut = cur[0].t - min_gap_s
        for b in bounds:
            if b <= cur[0].t or b >= cur[-1].e:
                continue
            k = next((i for i, w in enumerate(cur) if w.t >= b - 0.15), None)
            if k is None or k < min_words or len(cur) - k < min_words:
                continue
            if cur[k].t - last_cut < min_gap_s:
                continue
            out.append((first, cur[:k], None))
            cur = cur[k:]
            first = False
            last_cut = cur[0].t
        out.append((first, cur, lab))
    return out


def split_turns(words: list[TWord], sentence_gap_s: float = 0.6, refine: bool = True,
                diar: Sequence[tuple[float, str]] | None = None) -> list[Turn]:
    """Speaker turns.

    The `>>` markers are the primary signal, but MEASURED on the archive they
    are not enough: Flores and Thompson carry 0.7 markers/min against the
    8.3/min of Jimenez and Gunther, and their "turns" hold both people. So
    every marker turn is re-split at sentence boundaries wherever the text
    reads as a different speaker (`_label_sentences`). A turn that begins at
    a marker keeps `marker=True` so label_speakers can trust that boundary
    more than a text one."""
    raw: list[tuple[bool, list[TWord]]] = []
    cur: list[TWord] = []
    cur_marker = False
    pending = False
    for w in words:
        tok = w.w
        if tok.startswith(">>"):
            pending = True
            tok = tok[2:].strip()
        if pending and cur:
            raw.append((cur_marker, cur))
            cur = []
            cur_marker = True
            pending = False
        elif pending and not cur:
            cur_marker = True
            pending = False
        if not tok:
            continue
        cur.append(TWord(i=w.i, t=w.t, e=w.e, w=tok))
    if cur:
        raw.append((cur_marker, cur))

    # A marker that lands mid-sentence — the previous block ends without
    # punctuation and this one starts lowercase — is a caption-line boundary,
    # not a speaker change.
    merged: list[tuple[bool, list[TWord]]] = []
    for marker, ws in raw:
        if merged and marker and ws and merged[-1][1]:
            prev_last = merged[-1][1][-1].w
            head = ws[0].w
            if not TERMINAL.search(prev_last) and head[:1].islower() and (ws[0].t - merged[-1][1][-1].e) < 1.5:
                merged[-1] = (merged[-1][0], merged[-1][1] + ws)
                continue
        merged.append((marker, ws))
    raw = merged

    pieces: list[tuple[bool, list[TWord], str | None]] = []
    for marker, ws in raw:
        if not refine:
            pieces.append((marker, ws, None))
            continue
        sents = _sentences(ws, sentence_gap_s)
        labels = _label_sentences(sents)
        groups: list[tuple[list[TWord], str | None]] = []
        for s, lab in zip(sents, labels):
            if groups and groups[-1][1] == lab:
                groups[-1][0].extend(s)
            else:
                groups.append((list(s), lab))
        for gi, (gw, lab) in enumerate(groups):
            pieces.append((marker if gi == 0 else False, gw, lab))

    # No '>>' and no punctuation: the text cannot say where anyone stopped
    # talking, so the diarisation supplies the boundaries (2026-09-06).
    if diar and not has_speaker_structure(words):
        pieces = _diar_split(pieces, diar)

    out: list[Turn] = []
    for k, (marker, ws, lab) in enumerate(pieces):
        for w in ws:
            w.turn = k
        out.append(Turn(idx=k, words=ws, speaker=lab or SPEAKER_UNKNOWN,
                        speaker_evidence="sentence-level text" if lab else "", marker=marker))
    return out


def classify_turn(text: str) -> tuple[str, str]:
    """(speaker, evidence) from what is said. Boyd is the only person who
    sentences, asks 'do you understand', uses her tells and holds someone to
    account in the second person; counsel addresses the court and speaks for
    a client; the defendant answers in the first person."""
    boyd, dfd, cns, ev = _speaker_scores(text)
    best = max(boyd, dfd, cns)
    if best < 1.0:
        return SPEAKER_UNKNOWN, f"weak signals (boyd {boyd:.1f} dfd {dfd:.1f} cns {cns:.1f})"
    if best == boyd:
        return SPEAKER_BOYD, ev["boyd"]
    if best == cns:
        return SPEAKER_COUNSEL, ev["counsel"]
    return SPEAKER_DEFENDANT, ev["defendant"]


def _speaker_scores(text: str) -> tuple[float, float, float, dict[str, str]]:
    n = max(1, len(text.split()))
    you = len(moments._YOU.findall(text)) * 100.0 / n
    me = len(moments._I.findall(text)) * 100.0 / n
    judicial = len(moments.JUDICIAL.findall(text))
    bench = len(BENCH.findall(text))
    tells = sum(1 for rx, _w, _l in moments._TELLS if rx.search(text))
    confront = len(moments.CONFRONT.findall(text))
    counsel = len(COUNSEL.findall(text))
    defer = 1 if DEFERENTIAL.match(text) else 0
    question_to_you = 1 if (text.rstrip().endswith("?") and moments._YOU.search(text)) else 0
    receipt = len(RECEIPT.findall(text))
    vocab = len(BENCH_VOCAB.findall(text)) * 100.0 / n

    boyd = (judicial * 3.0 + bench * 2.0 + tells * 4.0 + receipt * 2.0 + confront * 0.8
            + (you / 8.0) + question_to_you * 1.5 + (vocab / 6.0 if n >= 6 else 0.0))
    if re.search(r"\b(ma'?am|your honor|judge)\b", text, re.I) and n <= 25 and not bench:
        boyd -= 2.0     # people address HER, she does not address herself
    dfd = me / 8.0 + defer * 2.0 + (1.5 if EXCUSE.search(text) else 0.0)
    cns = counsel * 2.5 + (1.0 if re.search(r"\byour honor\b", text, re.I) else 0.0)
    ev = {
        "boyd": f"judicial {judicial} bench {bench} tells {tells} confront {confront} you/100w {you:.0f}",
        "counsel": f"counsel markers {counsel}",
        "defendant": f"first-person/100w {me:.0f} deferential {defer}",
    }
    return boyd, dfd, cns, ev


def classify_margin(text: str) -> float:
    boyd, dfd, cns, _ev = _speaker_scores(text)
    scores = sorted([boyd, dfd, cns], reverse=True)
    return scores[0] - scores[1]


def _honorific_answer(text: str) -> bool:
    """"Yes, ma'am." / "No, your honor." — never hers, whatever any label says."""
    return bool(DEFERENTIAL.match(text) and re.search(r"(ma'?am|sir|your honor|judge)", text, re.I))


DEFENDANT_TEXT_TRUST_MARGIN = 1.5   # classify_margin at/above this keeps a defendant read against diarisation


def label_speakers(turns: list[Turn], diar: Sequence[tuple[float, str]] | None = None) -> list[Turn]:
    """Label every turn. Text classification first; `diar` — [(source_time,
    'boyd'|'defendant')] from diarize.py — overrides the Boyd / not-Boyd split
    when present (except for a deferential answer, which is never hers).
    Unknown turns take the speaker the alternation implies."""
    for t in turns:
        if t.speaker == SPEAKER_UNKNOWN:
            t.speaker, t.speaker_evidence = classify_turn(t.text)
        t.speaker_margin = classify_margin(t.text)

    if diar:
        marks = sorted(diar)

        def who_at(x: float) -> str | None:
            cur = None
            for tt, name in marks:
                if tt <= x + 1e-9:
                    cur = name
                else:
                    break
            return cur

        for t in turns:
            mid = (t.start_s + t.end_s) / 2.0
            d = who_at(mid)
            # A first-person answer the text reads confidently as the
            # defendant is never hers either: on the 2024 dockets the ECAPA
            # pass attributed 86-100 % of the hearing to Boyd (Alonzo,
            # Robinson) and would have relabelled "Because I was supposed to
            # be in custody and y'all let me out" as the judge (2026-09-06).
            confident_defendant = (t.speaker == SPEAKER_DEFENDANT
                                   and t.speaker_margin >= DEFENDANT_TEXT_TRUST_MARGIN)
            if d == SPEAKER_BOYD and not _honorific_answer(t.text) and not confident_defendant:
                t.speaker, t.speaker_evidence = SPEAKER_BOYD, "diarize"
            elif d == SPEAKER_DEFENDANT:
                if t.speaker == SPEAKER_BOYD or t.speaker == SPEAKER_UNKNOWN:
                    t.speaker, t.speaker_evidence = SPEAKER_DEFENDANT, "diarize (not Boyd)"
            elif d == SPEAKER_BOYD and t.speaker == SPEAKER_BOYD:
                t.speaker = SPEAKER_DEFENDANT
                t.speaker_evidence = "deferential answer (never hers), diarisation overruled"

    # A '>>' marker means the speaker CHANGED, so two consecutive turns with
    # the same label contradict the transcript. Where neither came from
    # diarisation, the shorter, weaker one flips.
    for k in range(1, len(turns)):
        a, b = turns[k - 1], turns[k]
        if not b.marker:
            continue
        if a.speaker != b.speaker or a.speaker not in (SPEAKER_BOYD, SPEAKER_DEFENDANT):
            continue
        if "diarize" in a.speaker_evidence or "diarize" in b.speaker_evidence:
            continue
        other = SPEAKER_DEFENDANT if a.speaker == SPEAKER_BOYD else SPEAKER_BOYD
        weak = None
        if len(b.words) <= 4 and (len(a.words) > 4 or b.speaker_margin <= a.speaker_margin):
            weak = b
        elif len(a.words) <= 4:
            weak = a
        if weak is not None and other == SPEAKER_BOYD and _honorific_answer(weak.text):
            weak = None
        if weak is not None:
            weak.speaker = other
            weak.speaker_evidence = "flipped: '>>' marks a change and the neighbour is the stronger read"

    # alternation prior for the unknowns
    for k, t in enumerate(turns):
        if t.speaker != SPEAKER_UNKNOWN:
            continue
        prev = turns[k - 1].speaker if k > 0 else SPEAKER_UNKNOWN
        nxt = turns[k + 1].speaker if k + 1 < len(turns) else SPEAKER_UNKNOWN
        if prev == SPEAKER_BOYD or nxt == SPEAKER_BOYD:
            t.speaker, t.speaker_evidence = SPEAKER_DEFENDANT, "alternation (beside a Boyd turn)"
        elif prev in (SPEAKER_DEFENDANT, SPEAKER_COUNSEL) or nxt in (SPEAKER_DEFENDANT, SPEAKER_COUNSEL):
            t.speaker, t.speaker_evidence = SPEAKER_BOYD, "alternation (beside a non-Boyd turn)"
    return turns


# ------------------------------------------------------------------ anchors


ANCHOR_PRIORITY = {"money_moment": 0, "tell": 1, "receipt": 2, "excuse_response": 3, "model_beat": 4}


@dataclass
class Anchor:
    t: float
    kind: str
    turn: int
    note: str

    @property
    def priority(self) -> int:
        return ANCHOR_PRIORITY.get(self.kind, 9)


def _turn_at(turns: list[Turn], t: float) -> int | None:
    for k, tr in enumerate(turns):
        if tr.start_s - 0.3 <= t <= tr.end_s + 0.3:
            return k
    for k, tr in enumerate(turns):
        if tr.start_s > t:
            return k
    return len(turns) - 1 if turns else None


def find_anchors(case: dict[str, Any], turns: list[Turn], lo: float, hi: float) -> list[Anchor]:
    anchors: list[Anchor] = []
    ed = case.get("editorial") or {}
    mm = ed.get("money_moment_s")
    if isinstance(mm, (int, float)) and lo <= float(mm) <= hi:
        k = _turn_at(turns, float(mm))
        if k is not None:
            anchors.append(Anchor(float(mm), "money_moment", k, "editorial.money_moment_s"))
    for seg in case.get("short_segments") or []:
        beat = str(seg.get("beat", ""))
        if beat in ("turn", "button", "moment", "hook", "stakes"):
            try:
                t = float(seg["start_s"])
            except (KeyError, TypeError, ValueError):
                continue
            if lo <= t <= hi:
                k = _turn_at(turns, t)
                if k is not None:
                    anchors.append(Anchor(t, "model_beat", k, f"short_segments.{beat}"))
    # The first stretch of a case is the call of the case; "according to the
    # plea bargain agreement" there is not a receipt. Tells and the money
    # moment are still allowed.
    opening_s = min(45.0, 0.1 * (hi - lo))
    for k, tr in enumerate(turns):
        if tr.speaker != SPEAKER_BOYD or tr.procedural or len(tr.words) < 5:
            continue
        last = _sentences(tr.words, 0.6)[-1]
        if is_ack(" ".join(w.w for w in last)) or re.search(r"\bthank you\b", " ".join(w.w for w in last), re.I):
            continue        # somebody addressing the bench, whatever tell it borrowed
        if tr.tells:
            anchors.append(Anchor(tr.start_s, "tell", k, ", ".join(tr.tells[:3])))
        elif tr.receipt and tr.start_s - lo >= opening_s:
            anchors.append(Anchor(tr.start_s, "receipt", k, RECEIPT.search(tr.text).group(0)))
    for k, tr in enumerate(turns):
        if tr.speaker == SPEAKER_DEFENDANT and tr.excuse and len(tr.words) >= 4 and tr.start_s - lo >= opening_s \
                and not BENCH.search(tr.text) and not moments.JUDICIAL.search(tr.text):
            for j in range(k + 1, min(k + 4, len(turns))):
                if turns[j].speaker == SPEAKER_BOYD and turns[j].start_s - tr.end_s <= 45.0 \
                        and not turns[j].procedural and not turns[j].ack and len(turns[j].words) >= 12:
                    anchors.append(Anchor(turns[j].start_s, "excuse_response", j,
                                          f"answers: {EXCUSE.search(tr.text).group(0)!r}"))
                    break
    best: dict[int, Anchor] = {}
    for a in anchors:
        cur = best.get(a.turn)
        if cur is None or a.priority < cur.priority:
            best[a.turn] = a
    return sorted(best.values(), key=lambda a: (a.priority, a.t))


# ------------------------------------------------------------------ sentences of the case


@dataclass
class Sentence:
    """One sentence of the case, in order. `k` is its index in the case's
    sentence list; a window is a contiguous slice of that list."""
    k: int
    turn: int
    speaker: str
    words: list[TWord]
    clerical: bool = False     # the one-line answer to a procedural question ("March 3rd 2005.")

    @property
    def text(self) -> str:
        return " ".join(w.w for w in self.words)

    @property
    def start_s(self) -> float:
        return self.words[0].t

    @property
    def end_s(self) -> float:
        return self.words[-1].e

    @property
    def n(self) -> int:
        return len(self.words)

    @property
    def procedural(self) -> bool:
        return is_procedural(self.text)

    @property
    def ack(self) -> bool:
        return is_ack(self.text)

    @property
    def question(self) -> bool:
        """A genuine question: a question mark, or the bench's imperative
        forms that demand an answer ("Explain to me why…", "Tell me…")."""
        return is_question(self.text)

    @property
    def substantive(self) -> bool:
        """What an interior cut may never skip: a real sentence of the
        conversation — not an acknowledgment, not procedure, not the clerical
        answer to a procedural question, not filler."""
        if self.ack or self.procedural or self.clerical:
            return False
        content = [w for w in self.words if not FILLER_TOKEN.match(w.w)]
        return len(content) >= 3

    @property
    def opener(self) -> bool:
        txt = self.text
        return (self.speaker == SPEAKER_BOYD and (txt.rstrip().endswith("?")
                or bool(moments.CONFRONT.search(txt))
                or any(rx.search(txt) for rx, _w, _l in moments._TELLS)))


IMPERATIVE_QUESTION = re.compile(
    r"^\W*((so|and|now|well|okay|all right),?\s+)*(explain (to me|it to me|that)|tell me|why|how come|how|what|where|who|when"
    r"|did you|do you|are you|were you|have you|can you|could you|is that|so what)\b", re.I)


def is_question(text: str) -> bool:
    t = text.strip()
    return t.endswith("?") or bool(IMPERATIVE_QUESTION.match(t))


def _clerical_answer(prev_text: str, prev_speaker: str, text: str, speaker: str) -> bool:
    """The one-line answer to a clerical question, by a different speaker."""
    return (is_procedural(prev_text) and is_question(prev_text) and len(text.split()) <= 8
            and speaker != prev_speaker and not is_procedural(text))


def case_sentences(turns: list[Turn], gap_s: float) -> list[Sentence]:
    out: list[Sentence] = []
    for tr in turns:
        for s in _sentences(tr.words, gap_s):
            out.append(Sentence(k=len(out), turn=tr.idx, speaker=tr.speaker, words=s))
    for k in range(1, len(out)):
        prev, cur = out[k - 1], out[k]
        if _clerical_answer(prev.text, prev.speaker, cur.text, cur.speaker):
            cur.clerical = True
    return out


def _span(sents: Sequence[Sentence]) -> float:
    return (sents[-1].end_s - sents[0].start_s) if sents else 0.0


def _payoff_stop(s: Sentence) -> bool:
    """A sentence after the payoff line that the clip must not run into:
    procedure, an acknowledgment, or somebody else addressing the court."""
    return s.procedural or s.ack or bool(re.search(r"\byour honor\b|\bjudge,", s.text, re.I))


def _tokens(text: str) -> set[str]:
    return {t for t in (_norm(x) for x in text.split()) if len(t) >= 3 and t not in GLUE_FORWARD}


def quote_span(sents: Sequence[Sentence], quote: str | None, min_overlap: float = 0.45) -> tuple[int, int] | None:
    """Which of these sentences the editorial money-moment QUOTE covers
    (indices into `sents`). The model gives one timestamp for a moment that
    is usually several sentences long; the quote says where it ENDS."""
    if not quote or not sents:
        return None
    q_sents = [q for q in re.split(r"(?<=[.!?])\s+|\s*'\s+[A-Z][a-z]+:\s*'", quote.strip()) if len(_tokens(q)) >= 3]
    if not q_sents:
        return None
    toks = [_tokens(s.text) for s in sents]
    hits: list[int] = []
    for q in q_sents:
        qt = _tokens(q)
        best, best_j = 0.0, -1
        for j, st in enumerate(toks):
            if not st:
                continue
            jac = len(qt & st) / float(len(qt | st))
            if jac > best:
                best, best_j = jac, j
        if best >= min_overlap:
            hits.append(best_j)
    if not hits:
        return None
    return min(hits), max(hits)


# ------------------------------------------------------------------ candidates: contiguous windows


@dataclass
class Cut:
    """An interior removal inside the body — recorded so it can be audited."""
    after_s: float
    before_s: float
    text: str
    reason: str          # procedural | duplicate | clerical answer


@dataclass
class Beat:
    role: str                      # hook | setup | turn | payoff | reaction
    turn: int
    speaker: str
    words: list[TWord]             # the words KEPT in this beat
    purpose: str = ""
    focus: str = "duo"             # defendant | boyd | duo
    punch_in: bool = False
    audio_accent: str | None = None
    dropped: list[str] = field(default_factory=list)   # interior cuts inside this beat (audited)

    @property
    def start_s(self) -> float:
        return self.words[0].t

    @property
    def end_s(self) -> float:
        return self.words[-1].e

    @property
    def text(self) -> str:
        return " ".join(w.w for w in self.words)

    @property
    def duration(self) -> float:
        return self.end_s - self.start_s


@dataclass
class Candidate:
    anchor: Anchor
    start_k: int                  # first sentence of the body (index into the case sentences)
    end_k: int                    # last sentence of the body
    kept: list[Sentence]
    cuts: list[Cut]
    beats: list[Beat] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    disqualified: list[str] = field(default_factory=list)
    scores: dict[str, int] = field(default_factory=dict)
    total: int = 0
    teaser: dict[str, Any] | None = None
    payoff_k: int = -1            # the anchor sentence

    @property
    def payoff(self) -> Beat | None:
        for b in self.beats:
            if b.role == "payoff":
                return b
        return None


class _Neighbours:
    """Word neighbours inside the case, so a cut can be placed in the real
    silence around a word and never inside the word next to it."""

    def __init__(self, all_words: Sequence[TWord] | None):
        self.words = list(all_words or [])
        self.pos = {w.i: k for k, w in enumerate(self.words)}

    def prev_end(self, w: TWord) -> float:
        k = self.pos.get(w.i)
        return self.words[k - 1].e if k else float("-inf")

    def next_start(self, w: TWord) -> float:
        k = self.pos.get(w.i)
        return self.words[k + 1].t if k is not None and k + 1 < len(self.words) else float("inf")

    def adjacent(self, a: TWord, b: TWord) -> bool:
        ka, kb = self.pos.get(a.i), self.pos.get(b.i)
        if ka is None or kb is None:
            return (b.i - a.i) == 1
        return kb - ka == 1

    def cut_in(self, w: TWord, pre: float) -> float:
        return max(w.t - pre, self.prev_end(w))

    def cut_out(self, w: TWord, post: float) -> float:
        return min(w.e + post, self.next_start(w))


def ranges_for(words: list[TWord], cfg: dict[str, Any],
               all_words: Sequence[TWord] | None = None) -> list[tuple[float, float]]:
    """Source ranges for a run of kept words: one range per contiguous stretch,
    split wherever the kept words skip (an audited cut) or the pause between
    two words exceeds dead_gap_s. Every boundary lands in the silence around
    a word — pre/post roll is clamped to the neighbouring words — never
    inside a word."""
    if not words:
        return []
    pre, post = float(cfg["cut_pre_s"]), float(cfg["cut_post_s"])
    dead, keep = float(cfg["dead_gap_s"]), float(cfg["keep_gap_s"])
    nb = _Neighbours(all_words)
    out: list[tuple[float, float]] = []
    start = nb.cut_in(words[0], pre)
    prev = words[0]
    for w in words[1:]:
        gap = w.t - prev.e
        if nb.adjacent(prev, w):
            verified = (not cfg.get("producer_preserve_ranges") or any(
                a <= prev.e + min(post, keep) + .12 and b >= w.t - min(pre, keep) - .12
                for a, b in cfg.get("verified_audio_silences", [])))
            if gap > dead and verified:
                out.append((start, prev.e + min(post, keep)))
                start = w.t - min(pre, keep)
        else:                                  # words were dropped in between: cut on the edges
            out.append((start, nb.cut_out(prev, post)))
            start = nb.cut_in(w, pre)
        prev = w
    out.append((start, nb.cut_out(prev, post)))
    return [(round(a, 3), round(b, 3)) for a, b in out]


def compress(window: Sequence[Sentence], protect: set[int]) -> tuple[list[Sentence], list[Cut]]:
    """The only removals the body allows: clearly procedural sentences (and
    the clerical one-line answer to a procedural question), and repeated
    wording (a sentence repeating the previous one). Protected sentences —
    the hook line, the payoff lines, the reaction — are never removed.
    Dead air is handled later, on the word ranges."""
    kept: list[Sentence] = []
    cuts: list[Cut] = []
    for s in window:
        if s.k in protect:
            kept.append(s)
            continue
        prev_kept = kept[-1] if kept else None
        if s.procedural or s.clerical:
            cuts.append(Cut(prev_kept.end_s if prev_kept else s.start_s, s.end_s, s.text,
                            "clerical answer" if s.clerical else "procedural"))
            continue
        if prev_kept is not None and s.n >= 3 and \
                [_norm(w.w) for w in s.words] == [_norm(w.w) for w in prev_kept.words]:
            cuts.append(Cut(prev_kept.end_s, s.end_s, s.text, "duplicate"))
            continue
        kept.append(s)
    # a cut's `before_s` is the next kept sentence's start; fix up now that
    # the kept list is known
    fixed: list[Cut] = []
    for c in cuts:
        nxt = next((s.start_s for s in kept if s.start_s > c.after_s - 1e-6), c.before_s)
        fixed.append(Cut(c.after_s, nxt, c.text, c.reason))
    # merge adjacent cuts with the same boundaries into one record
    merged: list[Cut] = []
    for c in fixed:
        if merged and abs(merged[-1].after_s - c.after_s) < 1e-6 and abs(merged[-1].before_s - c.before_s) < 1e-6:
            merged[-1] = Cut(c.after_s, c.before_s, merged[-1].text + " " + c.text,
                             merged[-1].reason if merged[-1].reason == c.reason else merged[-1].reason + " + " + c.reason)
        else:
            merged.append(c)
    return kept, merged


def _beats_from(kept: list[Sentence], anchor_k: int, cuts: list[Cut]) -> list[Beat]:
    """Beats are labels on the contiguous body: one beat per turn present,
    in order. First = hook (unless it is the payoff itself), the turn holding
    the anchor = payoff, the last non-Boyd beat before it = turn, the rest
    before = setup, after = reaction."""
    groups: list[list[Sentence]] = []
    for s in kept:
        if groups and groups[-1][0].turn == s.turn:
            groups[-1].append(s)
        else:
            groups.append([s])
    payoff_i = next((i for i, g in enumerate(groups) if any(s.k == anchor_k for s in g)), len(groups) - 1)
    beats: list[Beat] = []
    turn_i = None
    for i in range(payoff_i - 1, -1, -1):
        if groups[i][0].speaker != SPEAKER_BOYD:
            turn_i = i
            break
    for i, g in enumerate(groups):
        if i == payoff_i:
            role = "payoff"
        elif i > payoff_i:
            role = "reaction"
        elif i == 0:
            role = "hook"
        elif i == turn_i:
            role = "turn"
        else:
            role = "setup"
        words = [w for s in g for w in s.words]
        dropped = [c.text for c in cuts if g[0].start_s - 1e-6 <= c.after_s <= g[-1].end_s + 1e-6]
        beats.append(Beat(role=role, turn=g[0].turn, speaker=g[0].speaker, words=words, dropped=dropped,
                          purpose={
                              "hook": "opens the exchange on a line that needs no context",
                              "setup": "what the payoff answers",
                              "turn": "the claim / excuse / question that the payoff answers",
                              "payoff": "the payoff",
                              "reaction": "the reaction is the point",
                          }[role]))
    return beats


def payoff_end(sents: list[Sentence], anchor_k: int, cfg: dict[str, Any], quote: str | None) -> list[int]:
    """Where the body may END: the last sentence of the payoff line (the
    editorial quote's end when it can be matched, otherwise the anchor line
    and up to three more of the same riff, stopping at procedure, an
    acknowledgment or counsel's voice), plus the same with a short reaction
    turn after it when nothing is skipped in between. Several options, all
    ending on the payoff; the rubric picks."""
    turn_sents = [s for s in sents if s.turn == sents[anchor_k].turn]
    local = [s.k for s in turn_sents]
    ai = local.index(anchor_k)
    span = quote_span(turn_sents, quote)
    ends: list[int] = []
    if span and span[0] - 3 <= ai <= span[1] + 2:
        ends.append(local[max(span[1], ai)])
    else:
        end_i = ai
        added = 0
        for s in turn_sents[ai + 1:]:
            if added >= 3 or _payoff_stop(s):
                break
            end_i += 1
            added += 1
            ends.append(local[end_i])
        ends.append(local[ai])
    ends = sorted(set(ends))
    # An end must complete a thought: from the anchor line to the end at
    # least six words, or "Here's the thing." would be a 0.6 s payoff that
    # ends the clip on the set-up of her point (measured on Flores).
    full = [k for k in ends if sum(s.n for s in sents[anchor_k:k + 1]) >= 6]
    if full:
        ends = full
    # the reaction: the whole next turn, only if the body reaches the end of
    # the payoff turn (nothing skipped) and that turn is short and close
    last_k = local[-1]
    out: list[int] = list(ends)
    if last_k in ends:
        nxt_turn = [s for s in sents[last_k + 1:] if s.turn == sents[last_k].turn + 1]
        if nxt_turn:
            first, last = nxt_turn[0], nxt_turn[-1]
            if sum(s.n for s in nxt_turn) <= 12 and (last.end_s - first.start_s) <= float(cfg["reaction_max_s"]) \
                    and first.start_s - sents[last_k].end_s < 2.5 and not any(s.procedural for s in nxt_turn):
                out.append(last.k)
    return sorted(set(out))


def start_options(sents: list[Sentence], anchor_k: int, cfg: dict[str, Any]) -> list[int]:
    """Where the body may START: any sentence that opens a turn or is a Boyd
    opener (question / confrontation / tell), from the anchor line back to
    max_window_s before it. Never a procedural sentence."""
    out: list[int] = []
    anchor_t = sents[anchor_k].start_s
    for s in reversed(sents[: anchor_k + 1]):
        if anchor_t - s.start_s > float(cfg["max_window_s"]):
            break
        if s.procedural:
            continue
        first_of_turn = s.k == 0 or sents[s.k - 1].turn != s.turn
        if first_of_turn or s.opener:
            out.append(s.k)
    return sorted(set(out))


def build_window(sents: list[Sentence], start_k: int, end_k: int, anchor_k: int,
                 anchor: Anchor, protect_extra: set[int]) -> Candidate:
    window = sents[start_k: end_k + 1]
    protect = {start_k, anchor_k, end_k} | protect_extra
    kept, cuts = compress(window, protect)
    cand = Candidate(anchor=anchor, start_k=start_k, end_k=end_k, kept=kept, cuts=cuts, payoff_k=anchor_k)
    cand.beats = _beats_from(kept, anchor_k, cuts)
    return cand


# ------------------------------------------------------------------ scoring


def _clauses(s: list[TWord]) -> list[list[TWord]]:
    """A sentence and its comma / conjunction clauses: "…but I can tell you
    right now, I'm not going to send you to 12 years" is quotable as a
    clause when the sentence around it is not."""
    out = [s]
    cur: list[TWord] = []
    for w in s:
        if cur and _norm(w.w) in ("but", "and", "because", "so"):
            out.append(cur)
            cur = []
        cur.append(w)
        if w.w.rstrip('"”\')').endswith((",", ";", ":")):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return [c for c in out if c]


def _quote_score(txt: str, n: int, whole_sentence: bool) -> int:
    sc = 3
    if any(rx.search(txt) for rx, _w, _l in moments._TELLS):
        sc = 9
    elif RECEIPT.search(txt) or EXCUSE.search(txt):
        sc = 8
    elif txt.rstrip().endswith(("?", "!")):
        sc = 7
    elif STAKES.search(txt):
        sc = 7
    elif moments.CONFRONT.search(txt):
        sc = 6
    if n <= 6:
        sc += 1
    if not whole_sentence:
        sc -= 1
    return max(0, min(10, sc))


def _quotable(words: list[TWord]) -> tuple[int, str]:
    """(score 0..10, line) for the best standalone line — a sentence, or a
    clause of one, of 3 to 9 words."""
    best, line = 0, ""
    for sent in _sentences(words, 0.6):
        for s in _clauses(sent):
            n = len(s)
            if not 3 <= n <= 9:
                continue
            txt = " ".join(w.w for w in s)
            sc = _quote_score(txt, n, s is sent)
            if sc > best:
                best, line = sc, txt
    return best, line


def score_candidate(cand: Candidate, cfg: dict[str, Any], tile_map_known: bool, duration_s: float) -> Candidate:
    beats = cand.beats
    if not beats or cand.payoff is None:
        cand.disqualified.append("payoff_missing")
        cand.scores = {k: 0 for k in SCORE_DIMENSIONS}
        cand.total = 0
        return cand
    hook_b = beats[0]
    payoff = cand.payoff
    d = duration_s

    # hook 25 — the first two sentences of the first beat are what opens the clip
    first_two = _sentences(hook_b.words, 0.6)[:2]
    ht = " ".join(w.w for s in first_two for w in s)
    h = 5
    if ht.rstrip().endswith("?") or QUESTION.search(" ".join(w.w for w in hook_b.words[:8])):
        h += 10
    if any(rx.search(ht) for rx, _w, _l in moments._TELLS):
        h += 8
    if EXCUSE.search(ht):
        h += 8
    if RECEIPT.search(ht):
        h += 6
    if "!" in ht:
        h += 3
    if STAKES.search(ht):
        h += 6
    if hook_b.duration <= 8.0:
        h += 4
    elif hook_b.duration <= 15.0:
        h += 2
    if is_procedural(ht):
        h -= 8
    if moments.BOILER.search(ht):
        h -= 6
    if cand.teaser:
        h = max(h, 18)
    hook = max(0, min(25, h))

    # clarity 20
    c = 6
    early = [b for b in beats if b.start_s - beats[0].start_s <= 15.0]
    if {b.speaker for b in early} >= {SPEAKER_BOYD} and any(b.speaker != SPEAKER_BOYD for b in early):
        c += 6
    if any(b.speaker == SPEAKER_BOYD and QUESTION.search(b.text) for b in beats if b.role in ("hook", "setup")):
        c += 4
    n_words = sum(len(b.words) for b in beats) or 1
    unknown_share = sum(len(b.words) for b in beats if b.speaker == SPEAKER_UNKNOWN) / n_words
    if unknown_share > 0.3:
        c -= 5
    jargon = sum(len(moments.BOILER.findall(b.text)) + len(moments.JUDICIAL.findall(b.text)) for b in beats)
    if jargon * 100.0 / n_words > 2.0:
        c -= 4
    if len({b.speaker for b in beats}) <= 1:
        c -= 4
    if float(cfg["target_min_s"]) <= d <= float(cfg["target_max_s"]):
        c += 2
    clarity = max(0, min(20, c))

    # payoff 25
    base = {"money_moment": 20, "tell": 16, "receipt": 16, "excuse_response": 15, "model_beat": 13}.get(cand.anchor.kind, 8)
    p = base
    if any(b.role == "reaction" for b in beats):
        p += 3
    q, _line = _quotable(payoff.words)
    if q >= 7:
        p += 2
    if is_procedural(payoff.text) or is_ack(payoff.text):
        p -= 12
        cand.disqualified.append("payoff_procedural")
    if payoff.duration < 2.5 and not any(rx.search(payoff.text) for rx, _w, _l in moments._TELLS):
        p -= 6
    payoff_score = max(0, min(25, p))

    # escalation 15
    changes = sum(1 for a, b in zip(beats, beats[1:]) if a.speaker != b.speaker)
    e = {0: 1, 1: 4, 2: 7, 3: 10}.get(changes, 12)
    if any(b.role == "turn" and EXCUSE.search(b.text) for b in beats) and payoff.speaker == SPEAKER_BOYD:
        e += 3
    dom = max((sum(x.duration for x in beats if x.speaker == s) for s in {b.speaker for b in beats}), default=0.0)
    if d > 0 and dom / max(d, 1e-6) > 0.85 and changes <= 1:
        e -= 4
    escalation = max(0, min(15, e))

    # quote 10
    quote, line = max((_quotable(b.words) for b in beats), key=lambda x: x[0])
    quote = max(0, min(10, quote))

    # visual 5
    v = 5 if tile_map_known else 3
    if unknown_share > 0.0:
        v = min(v, 2)
    visual = max(0, min(5, v))

    # misleading edits are disqualified, not just penalised
    for b in beats:
        if b.role == "payoff":
            break
        if has_outcome(b.text) and not has_outcome(payoff.text):
            cand.disqualified.append(f"outcome_before_payoff: {b.role} turn {b.turn} gives the ruling away")
            break

    cand.scores = {"hook": hook, "clarity": clarity, "payoff": payoff_score,
                   "escalation": escalation, "quote": quote, "visual": visual}
    cand.total = sum(cand.scores.values())
    cand.notes.append(f"best line: {line!r}" if line else "no quotable line")
    return cand


# ------------------------------------------------------------------ framing / accents / teaser


def assign_focus(cand: Candidate, cfg: dict[str, Any]) -> Candidate:
    """Speaker-driven framing. The focused tile is the speaker's; a run of
    fast alternating turns stays on both (duo) rather than whipping between
    them; a reaction beat looks at the person reacting."""
    beats = cand.beats
    rapid_s = float(cfg["rapid_exchange_s"])
    n_rapid = int(cfg["rapid_alternations"])
    for b in beats:
        b.focus = {SPEAKER_BOYD: "boyd", SPEAKER_DEFENDANT: "defendant", SPEAKER_COUNSEL: "defendant"}.get(b.speaker, "duo")
    k = 0
    while k < len(beats):
        j = k
        while j < len(beats) and beats[j].duration <= rapid_s and (j == k or beats[j].speaker != beats[j - 1].speaker):
            j += 1
        if j - k >= n_rapid:
            for b in beats[k:j]:
                b.focus = "duo"
        k = max(j, k + 1)
    punches = 0
    raw_max = cfg.get("max_punch_ins")
    mx = None if raw_max in (None, "", 0, "0") else int(raw_max)
    payoff = cand.payoff
    if payoff is not None and cand.anchor.kind in ("money_moment", "tell", "receipt", "excuse_response") and payoff.focus != "duo":
        payoff.punch_in = True
        punches += 1
    if (mx is None or punches < mx) and beats and beats[0].role == "hook" and beats[0].speaker == SPEAKER_BOYD \
            and beats[0].focus != "duo" and QUESTION.search(beats[0].text):
        beats[0].punch_in = True
        punches += 1
    # Continue selecting motivated beats when no legacy numeric ceiling is
    # configured. Meaning and temporal spacing govern this pass: it may mark
    # more than two beats, but never filler, acknowledgements, duo frames, or
    # adjacent beats that would produce visual jitter.
    min_spacing = float(cfg.get("punch_in_min_spacing_s", 3.0))
    selected_at = [(b.start_s + b.end_s) / 2 for b in beats if b.punch_in]
    for b in beats:
        if mx is not None and punches >= mx:
            break
        if b.punch_in or b.focus == "duo" or b.duration < 0.45:
            continue
        text = b.text.strip()
        purpose = b.purpose.lower()
        meaningful = (
            b.role in ("payoff", "reaction")
            or any(tag in purpose for tag in ("receipt", "evidence", "contradiction", "reaction", "turn"))
            or (b.speaker == SPEAKER_BOYD and bool(RECEIPT.search(text) or STAKES.search(text) or QUESTION.search(text)))
        )
        midpoint = (b.start_s + b.end_s) / 2
        if (not meaningful or ACK.match(text) or is_procedural(text)
                or any(abs(midpoint - t) < min_spacing for t in selected_at)):
            continue
        b.punch_in = True
        punches += 1
        selected_at.append(midpoint)
    accents = 0
    mxa = int(cfg["max_accents"])
    for b in beats:
        if accents >= mxa:
            break
        if b.role == "payoff":
            b.audio_accent = "payoff"
            accents += 1
        elif b.role == "turn" and accents < mxa - 1:
            b.audio_accent = "turn"
            accents += 1
    return cand


def maybe_teaser(cand: Candidate, cfg: dict[str, Any], all_words: Sequence[TWord] | None = None) -> Candidate:
    """Cold-open teaser: when the natural hook is weak and the payoff has a
    short quotable line, play that line first, then the story in order. The
    line appears again in place, so nothing is misrepresented; the plan says
    exactly where the teaser came from."""
    if not cfg.get("allow_teaser", True) or cand.payoff is None or not cand.scores:
        return cand
    if cand.scores.get("hook", 0) >= int(cfg["hook_teaser_below"]):
        return cand
    q, line = _quotable(cand.payoff.words)
    if q < 7:
        return cand
    nb = _Neighbours(all_words)
    for s in _sentences(cand.payoff.words, float(cfg["sentence_gap_s"])):
        if " ".join(w.w for w in s) == line:
            a, b = nb.cut_in(s[0], float(cfg["cut_pre_s"])), nb.cut_out(s[-1], float(cfg["cut_post_s"]))
            if b - a <= float(cfg["teaser_max_s"]):
                cand.teaser = {"start_s": round(a, 3), "end_s": round(b, 3), "text": line,
                               "source": "payoff line, repeated in place", "turn": cand.payoff.turn}
                cand.notes.append("cold open: payoff line teased first (declared, non-chronological)")
            break
    return cand


# ------------------------------------------------------------------ segments / captions / QC


def _segments_for(cand: Candidate, cfg: dict[str, Any],
                  all_words: Sequence[TWord] | None = None) -> tuple[list[Segment], list[str], list[bool]]:
    """Render segments in order, with the focus and punch-in of each.

    Two consecutive beats that are continuous speech (no word dropped
    between them, pause under dead_gap_s) with the same framing become ONE
    segment. When the framing differs the boundary stays, clipped so the
    pre/post rolls of neighbouring beats never overlap."""
    nb = _Neighbours(all_words)
    dead = float(cfg["dead_gap_s"])
    items: list[tuple[Segment, str, bool, TWord | None, TWord | None]] = []
    if cand.teaser:
        items.append((Segment(float(cand.teaser["start_s"]), float(cand.teaser["end_s"])),
                      cand.teaser.get("focus", "duo"), False, None, None))
    for b in cand.beats:
        for a, e in ranges_for(b.words, cfg, all_words):
            inside = [w for w in b.words if a - 1e-6 <= w.t <= e + 1e-6]
            items.append((Segment(a, e), b.focus, b.punch_in, inside[0] if inside else None,
                          inside[-1] if inside else None))
    segs: list[Segment] = []
    focus: list[str] = []
    punch: list[bool] = []
    last_word: TWord | None = None
    for k, (seg, f, p, first, last) in enumerate(items):
        is_teaser = bool(cand.teaser) and k == 0
        if segs and not is_teaser and not (bool(cand.teaser) and k == 1):
            prev = segs[-1]
            if (prev.end_s < seg.start_s and any(
                    a <= prev.end_s and seg.start_s <= b
                    for a, b in cfg.get("producer_preserve_ranges", []))
                    and not any(a <= prev.end_s + .12 and b >= seg.start_s - .12
                                for a, b in cfg.get("verified_audio_silences", []))):
                # Keep untranscribed audio inside an approved passage. Different
                # speaker framing must not manufacture an unsupported audio cut.
                prev = Segment(prev.start_s, seg.start_s)
                segs[-1] = prev
            continuous = (last_word is not None and first is not None and nb.adjacent(last_word, first)
                          and (first.t - last_word.e) <= dead)
            # On the fixed 50/50 layout only a punch-in changes the picture,
            # so two continuous beats merge unless one of them is punched on
            # a different tile — a speaker change alone is not a cut.
            same_picture = (punch[-1] == p) and (not p or focus[-1] == f)
            if continuous and same_picture:
                segs[-1] = Segment(prev.start_s, seg.end_s)
                last_word = last or last_word
                continue
            if seg.start_s < prev.end_s:
                seg = Segment(prev.end_s, seg.end_s)
        segs.append(seg)
        focus.append(f)
        punch.append(p)
        last_word = last
    return segs, focus, punch


def _boundary_inside_word(t: float, words: Sequence[TWord]) -> TWord | None:
    for w in words:
        if w.t + 0.01 < t < w.e - 0.01:
            return w
    return None


def _omitted_between(a_end: float, b_start: float, all_words: Sequence[TWord]) -> list[TWord]:
    return [w for w in all_words if a_end - 1e-6 < w.t < b_start - 1e-6]


def audit_interior_cuts(segments: list[Segment], all_words: Sequence[TWord], kept_words: Sequence[TWord],
                        teaser: bool, gap_s: float) -> list[dict[str, Any]]:
    """For every join inside the body: what the source said between the two
    kept ranges, and whether skipping it is allowed. Allowed = nothing
    (silence), acknowledgments, procedural filler, filler tokens, or wording
    that repeats a kept neighbour. Anything else is substantive and the join
    is a false cut."""
    body = segments[1:] if teaser else segments
    kept_texts = {" ".join(_norm(w.w) for w in s) for s in _sentences(list(kept_words), gap_s)}
    out: list[dict[str, Any]] = []
    for a, b in zip(body, body[1:]):
        omitted = _omitted_between(a.end_s, b.start_s, all_words)
        entry: dict[str, Any] = {"after_s": round(a.end_s, 3), "before_s": round(b.start_s, 3),
                                 "gap_s": round(b.start_s - a.end_s, 3), "skipped_text": "",
                                 "classes": [], "ok": True}
        if omitted:
            classes: list[str] = []
            prev_txt: str | None = None
            for s in _sentences(omitted, gap_s):
                txt = " ".join(w.w for w in s)
                key = " ".join(_norm(w.w) for w in s)
                content = [w for w in s if not FILLER_TOKEN.match(w.w)]
                if not content:
                    classes.append("filler")
                elif is_ack(txt):
                    classes.append("acknowledgment")
                elif is_procedural(txt):
                    classes.append("procedural")
                elif prev_txt is not None and is_procedural(prev_txt) and is_question(prev_txt) and len(content) <= 8:
                    classes.append("clerical answer")
                elif key in kept_texts:
                    classes.append("duplicate")
                elif len(content) < 3:
                    classes.append("fragment")
                else:
                    classes.append("SUBSTANTIVE")
                prev_txt = txt
            entry["skipped_text"] = " ".join(w.w for w in omitted)
            entry["classes"] = classes
            entry["ok"] = "SUBSTANTIVE" not in classes
        else:
            entry["classes"] = ["silence"]
        out.append(entry)
    return out


def last_word_completes_a_line(kept: Sequence[TWord], all_words: Sequence[TWord] | None,
                              cfg: dict[str, Any]) -> tuple[bool, str]:
    """Does the Short STOP on a complete line? (Added 2026-09-19.)

    A boundary on a word edge is not the same thing as a complete line. The
    saved `bHAuH5U4NYI:2725` Short ends on the attorney's "...all right and
    here's the thing I" — source 3574.42 s — and the rest of that sentence
    ("...I understand, because I used to represent people who had mental health
    issues") is never heard. Every technical gate passed. The contract says a
    chopped sentence is a defect even when technical QC passes, so the ending
    is checked against the source word stream: the last kept word must end a
    sentence, or be followed by a real pause (>= `sentence_gap_s`), or be the
    last word of the case.
    """
    kept = [w for w in kept if w is not None]
    if not kept:
        return False, "no kept words: nothing to end on"
    words = list(all_words or [])
    if not words:
        return True, "no source word stream supplied: the ending is unverified"
    last = max(kept, key=lambda w: float(w.t))
    nxt = next((w for w in words if float(w.t) > float(last.e) - 1e-6), None)
    if nxt is None:
        return True, f"ends on the last word of the case: {last.w!r}"
    pause = float(nxt.t) - float(last.e)
    terminal = last.w.strip().rstrip('"\u201d\u2019\'').endswith((".", "?", "!"))
    if terminal or pause >= float(cfg["sentence_gap_s"]):
        return True, f"ends on {last.w!r} (pause {pause:.2f}s before {nxt.w!r})"
    return False, (f"ends mid-sentence on {last.w!r}: the source resumes {pause:.2f}s later "
                   f"with {nxt.w!r} and the viewer never hears the rest of the line")


def question_answer_pairs(kept: Sequence[Sentence], sents: Sequence[Sentence]) -> list[dict[str, Any]]:
    """Every kept genuine question and what follows it on screen versus what
    followed it in the source. `ok` is False when the on-screen follow-up is
    not the actual answer."""
    kept_ks = [s.k for s in kept]
    out: list[dict[str, Any]] = []
    for pos, s in enumerate(kept):
        if not (s.question and s.substantive):
            continue
        nxt_kept = next((x for x in kept[pos + 1:] if x.substantive), None)
        if nxt_kept is None:
            continue                                 # the clip ends on the question
        nxt_src = next((x for x in sents[s.k + 1:] if x.substantive), None)
        ok = nxt_src is not None and nxt_src.k == nxt_kept.k
        out.append({"question": s.text, "at_s": round(s.start_s, 3),
                    "on_screen_next": nxt_kept.text, "source_next": nxt_src.text if nxt_src else "",
                    "ok": ok})
    return out


def qc_gates(cand: Candidate, segments: list[Segment], captions_cards: list[dict[str, Any]],
             case: dict[str, Any], case_key: str, all_words: Sequence[TWord], sents: Sequence[Sentence],
             cfg: dict[str, Any], cap_style: dict[str, Any] | None,
             cres: dict[str, Any] | None = None,
             hard_breaks: Sequence[int] | None = None,
             kept_words: Sequence[TWord] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    gates: list[dict[str, Any]] = []
    lo, hi = float(case["start_s"]), float(case["end_s"])
    pre, post = float(cfg["cut_pre_s"]), float(cfg["cut_post_s"])
    gap_s = float(cfg["sentence_gap_s"])

    def gate(name: str, ok: bool, detail: str, critical: bool = True) -> None:
        gates.append({"gate": name, "ok": bool(ok), "detail": detail, "critical": critical})

    gate("same_case", bool(case_key) and ":" in case_key, f"plan bound to {case_key}")
    tail = float(cfg["word_hold_s"]) + post
    inside = all(lo - pre - 1e-6 <= s.start_s and s.end_s <= hi + tail + 1e-6 for s in segments)
    gate("ranges_within_case", inside, f"case {lo:.1f}-{hi:.1f}; segments {[(round(s.start_s, 1), round(s.end_s, 1)) for s in segments]}")
    body = segments[1:] if cand.teaser else segments
    chrono = all(b.start_s >= a.end_s - 1e-6 for a, b in zip(body, body[1:]))
    gate("chronological_except_teaser", chrono, "kept ranges stay in source order" if chrono else "a range precedes an earlier one")
    dup_ok = True
    if cand.teaser:
        ta, tb = float(cand.teaser["start_s"]), float(cand.teaser["end_s"])
        covered = sum(max(0.0, min(s.end_s, tb) - max(s.start_s, ta)) for s in body)
        dup_ok = covered >= (tb - ta) - 0.05 and (tb - ta) <= float(cfg["teaser_max_s"]) + 1e-6
    gate("teaser_declared_and_repeated", dup_ok, "teaser line appears again in place" if cand.teaser else "no teaser")

    # THE CONTINUITY RULE
    #
    # 2026-09-16: the declared word stream defaults to the candidate's kept
    # sentences, but an explicit Producer-plan candidate builds its captions
    # from its BEATS (see the producer path, which passes kept_words). Deriving
    # the declaration from a different source than the captions made the
    # captions_from_kept_words gate compare two different word lists and refuse
    # a render that was in fact correct — it cost one word, appearing only when
    # the plan opened mid-turn. Callers that know the exact stream they captioned
    # pass it in; the heuristic path is unchanged.
    kept_words = list(kept_words) if kept_words is not None else [w for s in cand.kept for w in s.words]
    cuts = audit_interior_cuts(segments, all_words, kept_words, bool(cand.teaser), gap_s)
    bad = [c for c in cuts if not c["ok"]]
    gate("continuity_gaps", not bad,
         f"{len(cuts)} interior join(s), all silence / acknowledgment / procedural / duplicate" if not bad
         else f"{len(bad)} join(s) skip substantive dialogue, e.g. {bad[0]['after_s']:.1f}s -> {bad[0]['before_s']:.1f}s: {bad[0]['skipped_text'][:140]!r}")
    qa = question_answer_pairs(cand.kept, sents)
    bad_qa = [q for q in qa if not q["ok"]]
    gate("question_answer", not bad_qa,
         f"{len(qa)} kept question(s), each followed on screen by its actual answer" if not bad_qa
         else f"{bad_qa[0]['question'][:80]!r} is followed on screen by {bad_qa[0]['on_screen_next'][:60]!r}, in the source by {bad_qa[0]['source_next'][:60]!r}")

    mid = [(s, t) for s in segments for t in (s.start_s, s.end_s) if _boundary_inside_word(t, all_words)]
    gate("no_mid_word_cuts", not mid, "every boundary sits on a word edge or in a pause" if not mid
         else f"{len(mid)} boundary(ies) inside a word, e.g. {mid[0][1]:.2f}s in {_boundary_inside_word(mid[0][1], all_words).w!r}")
    zero = [s for s in segments if s.duration < 0.2]
    gate("no_zero_segments", not zero, f"{len(segments)} segments, shortest {min((s.duration for s in segments), default=0):.2f}s")
    d = sum(s.duration for s in segments)
    gate("duration_bounds", float(cfg["min_duration_s"]) - 1e-6 <= d <= float(cfg["max_duration_s"]) + 1e-6,
         f"{d:.1f}s (floor {cfg['min_duration_s']:.0f}, ceiling {cfg['max_duration_s']:.0f})")
    payoff = cand.payoff
    p_ok = payoff is not None and any(s.start_s - 1e-6 <= payoff.words[-1].t <= s.end_s + 1e-6 for s in body)
    gate("payoff_present", p_ok, f"payoff turn {payoff.turn if payoff else None} kept whole" if p_ok else "payoff line missing from the kept ranges")
    ends_ok, ends_detail = last_word_completes_a_line(
        kept_words if kept_words is not None else [w for s in cand.kept for w in s.words],
        all_words, cfg)
    gate("ending_is_a_complete_line", ends_ok, ends_detail)

    # captions: the source word stream must be exactly the kept words mapped
    # through the shared timeline (the display stream is an audited
    # subsequence of it), and the kinetic QC must pass
    if captions_cards and cres is not None:
        out_words = render.map_words_to_timeline(
            [Word(t=w.t, w=w.w) for w in kept_words], segments, absorb_gap_s=0.0)
        want = [(round(w.t, 2), _norm(render.strip_caption_artifact(w.w))) for w in out_words
                if render.strip_caption_artifact(w.w)]
        got = [(round(float(a["t"]), 2), _norm(render.strip_caption_artifact(a["w"]))) for a in cres["audit"]
               if render.strip_caption_artifact(a["w"])]
        gate("captions_from_kept_words", want == got,
             f"{len(captions_cards)} phrases over {len(cres['display'])} displayed of {len(cres['audit'])} kept words "
             f"({len(cres['omitted'])} disfluencies omitted for display, audited)"
             if want == got else f"word stream differs from the kept words ({len(got)} vs {len(want)})")
        for g in captions.kinetic_qc(captions_cards, cres["display"], cap_style, sorted(hard_breaks or []), cres["audit"]):
            gate(g["gate"], g["ok"], g["detail"])
    else:
        gate("captions_from_kept_words", False, "no caption cards produced")
    rail = layout.overlay_layout(cap_style or {}, {}, None)
    gate("caption_rail", rail["ok"],
         f"caption block centred at {rail['caption_center']}, inside the safe band, overlay_collision {rail['overlay_collision']}"
         if rail["ok"] else f"caption block {rail['boxes'][0]} collides {rail['collisions']} or leaves the safe band")
    punches = sum(1 for b in cand.beats if b.punch_in)
    raw_max = cfg.get("max_punch_ins")
    if raw_max in (None, "", 0, "0"):
        gate("punch_in_selection", True, f"{punches} editorially selected punch-in(s); spacing and beat fit govern selection")
    else:
        gate("punch_in_budget", punches <= int(raw_max), f"{punches} punch-in(s), max {raw_max}")
    gate("not_disqualified", not cand.disqualified, "; ".join(cand.disqualified) or "no disqualifier")
    # The hook is floored on its OWN dimension before the total is judged: a
    # strong payoff must not buy a weak opening (see DEFAULTS["hook_min_score"]).
    hook_floor = int(cfg.get("hook_min_score", 0) or 0)
    hook_points = int(cand.scores.get("hook", 0) or 0)
    hook_ok = hook_points >= hook_floor or bool(cand.teaser)
    gate("hook_floor", hook_ok,
         f"hook {hook_points}/{SCORE_DIMENSIONS['hook']} (floor {hook_floor})"
         + (" — satisfied by the declared cold-open teaser" if hook_ok and hook_points < hook_floor else "")
         + ("" if hook_ok else
            "; the opening beat is a preamble, not the confrontation — re-plan the hook, or declare a teaser,"
            " instead of shipping it on the strength of the total"))
    gate("score_floor", cand.total >= int(cfg["min_score"]), f"{cand.total}/100 (floor {cfg['min_score']})")
    return gates, cuts, qa


def caption_hard_breaks(plan_or_cand: Any, words_out: Sequence[Any]) -> set[int]:
    """Word indices where a caption MUST break because the picture cuts: the
    start of every render segment after the first. (Speaker changes are
    carried by the word stream itself — captions.plan_phrases never crosses
    them — so they are not listed here.)"""
    segments = plan_or_cand.segments if hasattr(plan_or_cand, "segments") else plan_or_cand["segments"]
    segs = [(float(s.start_s), float(s.end_s)) if hasattr(s, "start_s") else (float(s[0]), float(s[1])) for s in segments]
    offsets: list[float] = []
    acc = 0.0
    for a_, b_ in segs:
        offsets.append(acc)
        acc += b_ - a_
    hard: set[int] = set()
    for T in offsets[1:]:
        idx = next((i for i, x in enumerate(words_out)
                    if (x["t"] if isinstance(x, dict) else x[0]) >= T - 1e-3), None)
        if idx is not None and 0 < idx < len(words_out):
            hard.add(idx)
    return hard


def word_stream_for(cand: Candidate, segments: list[Segment]) -> list[dict[str, Any]]:
    """THE AUTHORITATIVE WORD STREAM: every kept word with its source index,
    its output time (through the same segment list the renderer cuts) and
    the verified speaker of the beat it belongs to. Captions are built from
    this and nothing else."""
    offsets: list[float] = []
    acc = 0.0
    for s in segments:
        offsets.append(acc)
        acc += s.duration

    # One entry per OCCURRENCE in the output — the same rule as
    # render.map_words_to_timeline (segment start <= t < segment end), so a
    # teaser's words appear twice, once per segment that carries them.
    stream: list[dict[str, Any]] = []
    for s, off in zip(segments, offsets):
        for b in cand.beats:
            for w in b.words:
                if s.start_s - 1e-6 <= w.t < s.end_s:
                    stream.append({"i": w.i, "src_t": round(w.t, 3), "t": round(off + (w.t - s.start_s), 3),
                                   "w": w.w, "speaker": b.speaker})
    stream.sort(key=lambda x: (x["t"], x["i"]))
    return stream


def caption_cards_for(cand: Candidate, segments: list[Segment], cfg: dict[str, Any],
                      cap_style: dict[str, Any] | None, kept_words: Sequence[TWord],
                      key_words: set[str] | None = None) -> tuple[list[dict[str, Any]], set[int], str, list[dict[str, Any]]]:
    """The plan's caption record: the word stream (kept words, output times,
    verified speakers), phrased by captions.plan_phrases (deterministic here;
    the pipeline may run a provider and re-record)."""
    stream = word_stream_for(cand, segments)
    hard = caption_hard_breaks({"segments": segments}, stream)
    res = captions.plan_captions(stream, cap_style, sorted(hard), None)
    return res["cards"], set(res["hard_breaks"]), res["planner_used"], res


# ------------------------------------------------------------------ the plan


def producer_alignment(plan_or_segments: Any, brain_plan: dict[str, Any] | None,
                       words: Sequence[Word] | None = None) -> dict[str, Any]:
    """Prove the rendered source ranges execute the approved Shorts Brain cut.

    With transcript evidence, every planned spoken word must survive. Without
    it, only a small boundary tolerance is allowed. A percentage allowance
    cannot distinguish silence from a missing question, negation or payoff.
    Audio silence verification remains a separate pre-render check.
    """
    brain = dict(brain_plan or {})
    required = list(brain.get("sequence") or [])
    if hasattr(plan_or_segments, "segments"):
        raw_segments = list(plan_or_segments.segments)
    else:
        raw_segments = list(plan_or_segments or [])
    segments = [
        (float(s.start_s), float(s.end_s)) if hasattr(s, "start_s") else (float(s[0]), float(s[1]))
        for s in raw_segments
    ]

    def covered(start_s: float, end_s: float) -> float:
        clipped = sorted(
            (max(start_s, a), min(end_s, b))
            for a, b in segments
            if min(end_s, b) > max(start_s, a)
        )
        merged: list[tuple[float, float]] = []
        for a, b in clipped:
            if merged and a <= merged[-1][1] + 1e-6:
                merged[-1] = (merged[-1][0], max(merged[-1][1], b))
            else:
                merged.append((a, b))
        return sum(b - a for a, b in merged)

    checks: list[dict[str, Any]] = []
    for row in required:
        start_s, end_s = float(row["start_s"]), float(row["end_s"])
        duration = max(0.001, end_s - start_s)
        amount = covered(start_s, end_s)
        allowed_loss = min(0.8, duration * 0.35)
        spoken = timed_words(words, start_s, end_s) if words is not None else []
        missing = [word.w for word in spoken
                   if not any(a <= word.t + 0.04 and b >= min(word.e, end_s) - 0.04
                              for a, b in segments)]
        range_ok = (bool(spoken) and not missing) if words is not None else amount >= duration - allowed_loss - 1e-6
        checks.append({
            "edit_order": int(row.get("edit_order") or len(checks) + 1),
            "role": str(row.get("role") or "moment"),
            "start_s": start_s,
            "end_s": end_s,
            "coverage": round(amount / duration, 3),
            "spoken_words": len(spoken) if words is not None else None,
            "missing_words": missing,
            "ok": range_ok,
        })

    hook_start = float(brain.get("hook_start_s") or (required[0]["start_s"] if required else 0.0))
    hook_first = bool(segments) and segments[0][0] <= hook_start + 0.8 and segments[0][1] >= hook_start - 0.4
    chronological = all(a[0] <= b[0] and a[1] <= b[0] + 0.04
                        for a, b in zip(segments, segments[1:]))
    order_ok = brain.get("chronology_strategy") != "chronological" or chronological
    return {
        "ok": bool(required) and hook_first and order_ok and all(row["ok"] for row in checks),
        "order_ok": order_ok,
        "decision": str(brain.get("decision") or ""),
        "chronology_strategy": str(brain.get("chronology_strategy") or ""),
        "hook_first": hook_first,
        "required_ranges": checks,
        "rendered_segments": [[round(a, 3), round(b, 3)] for a, b in segments],
    }


def producer_silence_checks(segments: Sequence[Segment], brain: dict[str, Any],
                            silences: Sequence[tuple[float, float]], offset_s: float = 0.0) -> list[dict[str, Any]]:
    """Check long transcript gaps against measured audio before calling them silence."""
    checks = []
    for left, right in zip(segments, segments[1:]):
        for row in brain.get("sequence") or []:
            start = max(left.end_s, float(row["start_s"]))
            end = min(right.start_s, float(row["end_s"]))
            if end - start <= 0.8:
                continue
            ok = any(a + offset_s <= start + 0.12 and b + offset_s >= end - 0.12
                     for a, b in silences)
            checks.append({"start_s": round(start, 3), "end_s": round(end, 3), "ok": ok})
    return checks


@dataclass
class ShortPlan:
    ruleset: str
    case_key: str
    source_case_key: str
    video_id: str
    ok: bool
    refusal: str | None
    anchor: dict[str, Any]
    beats: list[dict[str, Any]]
    segments: list[Segment]
    teaser: dict[str, Any] | None
    nonlinear: bool
    duration_s: float
    scores: dict[str, int]
    total: int
    disqualified: list[str]
    qc: list[dict[str, Any]]
    captions: list[dict[str, Any]]
    alternatives: list[dict[str, Any]]
    notes: list[str]
    tile_map: dict[str, Any]
    fit_log: list[str]
    speaker_turns: int
    mismatch_with_scorer: str | None = None
    segment_focus: list[str] = field(default_factory=list)
    segment_punch: list[bool] = field(default_factory=list)
    interior_cuts: list[dict[str, Any]] = field(default_factory=list)
    question_answer: list[dict[str, Any]] = field(default_factory=list)
    caption_hard_breaks: list[int] = field(default_factory=list)
    caption_planner: str = "deterministic"
    key_words: set[str] = field(default_factory=set)
    body_text: str = ""
    word_stream: list[dict[str, Any]] = field(default_factory=list)
    caption_style: dict[str, Any] = field(default_factory=dict)
    caption_audit: list[dict[str, Any]] = field(default_factory=list)
    caption_density: dict[str, Any] = field(default_factory=dict)

    @property
    def focus_plan(self) -> list[str]:
        return list(self.segment_focus) if self.segment_focus else ["duo"] * len(self.segments)

    @property
    def punch_plan(self) -> list[bool]:
        return list(self.segment_punch) if self.segment_punch else [False] * len(self.segments)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ruleset": self.ruleset,
            "case_key": self.case_key,
            "source_case_key": self.source_case_key,
            "video_id": self.video_id,
            "ok": self.ok,
            "refusal": self.refusal,
            "anchor": self.anchor,
            "beats": self.beats,
            "segments": [[s.start_s, s.end_s] for s in self.segments],
            "segment_focus": self.focus_plan,
            "segment_punch": self.punch_plan,
            "teaser": self.teaser,
            "nonlinear": self.nonlinear,
            "chronological_except_teaser": True,
            "duration_s": round(self.duration_s, 3),
            "scores": self.scores,
            "total": self.total,
            "disqualified": self.disqualified,
            "qc": self.qc,
            "interior_cuts": self.interior_cuts,
            "question_answer": self.question_answer,
            "captions": self.captions,
            "caption_planner": self.caption_planner,
            "caption_hard_breaks": list(self.caption_hard_breaks),
            "caption_rail": {"x": 540, "y": 960, "end_card": "none", "mode": "kinetic"},
            "word_stream": self.word_stream,
            "caption_style": self.caption_style,
            "caption_audit": self.caption_audit,
            "caption_density": self.caption_density,
            "body_text": self.body_text,
            "alternatives": self.alternatives,
            "notes": self.notes,
            "tile_map": self.tile_map,
            "fit_log": self.fit_log,
            "speaker_turns": self.speaker_turns,
            "mismatch_with_scorer": self.mismatch_with_scorer,
        }


class ShortPlanError(ValueError):
    """Raised when a plan is asked to serve a different case than it was built for."""


def plan_short(case: dict[str, Any], case_key: str, words: Sequence[Word], cfg: dict[str, Any] | None = None,
               cap_style: dict[str, Any] | None = None, diar: Sequence[tuple[float, str]] | None = None,
               tile_map: dict[str, Any] | None = None,
               judge: Callable[[list[dict[str, Any]]], dict[str, dict[str, Any]]] | None = None) -> ShortPlan:
    """Plan the short for ONE case. `words` is the whole transcript; only the
    case's own span is ever read. Returns a plan whose `ok` says whether it
    may be rendered; a refused plan carries the reason and the failed gates.

    `judge` (optional) receives the scored candidates and may return
    {candidate_id: {"bonus": int, "note": str}} — bounded to ±10 — so a model
    can re-rank later without the planner depending on one provider.
    """
    c = _cfg(cfg)
    vid = case_key.split(":")[0] if case_key else str(case.get("video_id", ""))
    lo, hi = float(case["start_s"]), float(case["end_s"])
    gap_s = float(c["sentence_gap_s"])
    tw = timed_words(words, lo, hi, float(c["word_hold_s"]))
    turns = label_speakers(split_turns(tw, gap_s, diar=diar), diar)
    sents = case_sentences(turns, gap_s)
    tile_known = bool(tile_map and tile_map.get("boyd") in ("top", "bottom"))
    brain_plan = dict(case.get("producer_short_plan") or {})
    alignment_failures: list[dict[str, Any]] = []
    quote = str((case.get("editorial") or {}).get("money_moment") or "") or None
    key_words: set[str] = set()                      # the case's own words, for caption emphasis
    for tok in re.findall(r"[A-Za-z']+", quote or ""):
        n = tok.lower()
        if len(n) >= 4 and n not in GLUE_FORWARD and n not in moments.STOP:
            key_words.add(n)

    def refused(reason: str, extra_notes: list[str] | None = None, alts: list[dict[str, Any]] | None = None) -> ShortPlan:
        return ShortPlan(RULESET, case_key, case_key, vid, False, reason, {}, [], [], None, False, 0.0,
                         {k: 0 for k in SCORE_DIMENSIONS}, 0, [], [], [], alts or [], extra_notes or [],
                         tile_map or {}, [], len(turns))

    if not tw or not sents:
        return refused("no transcript words inside the case span")

    # Producer Brain already supplied a validated, evidence-grounded edit
    # contract. Build that exact sequence first; the heuristic search below is
    # only the fallback when no Producer sequence exists. This prevents a
    # complete continuous exchange from being discarded merely because a
    # keyword anchor did not resemble the planner's older court-story shapes.
    producer_rows = list(brain_plan.get("sequence") or [])
    if brain_plan.get("decision") == "MAKE" and producer_rows:
        ranges = list(
            (float(row["start_s"]), float(row["end_s"]), row)
            for row in producer_rows
        )
        if (brain_plan.get("chronology_strategy") != "chronological"
                or any(a[1] > b[0] for a, b in zip(ranges, ranges[1:]))
                or any(int(row.get("edit_order", index)) != index
                       or int(row.get("source_order", index)) != index
                       for index, (_, _, row) in enumerate(ranges, 1))):
            return refused("Producer sequence requires explicit chronological, non-overlapping edit order")
        kept_sents: list[Sentence] = []
        for sent in sents:
            selected = [
                word for word in sent.words
                if any(start - 1e-6 <= word.t <= end + 1e-6 for start, end, _row in ranges)
            ]
            if selected:
                kept_sents.append(Sentence(sent.k, sent.turn, sent.speaker, selected, sent.clerical))

        beat_rows: list[tuple[Beat, str]] = []
        for start, end, row in ranges:
            row_role = str(row.get("role") or "moment").lower()
            for turn_index, turn in enumerate(turns):
                selected = [word for word in turn.words if start - 1e-6 <= word.t <= end + 1e-6]
                if selected:
                    beat_rows.append((Beat(
                        role="setup",
                        turn=turn_index,
                        speaker=turn.speaker,
                        words=selected,
                        purpose=f"Producer Brain approved {row_role}",
                    ), row_role))

        # A one-speaker plan still needs distinct opening and payoff beats.
        # Split on a real sentence boundary; never duplicate or reorder words.
        if len(beat_rows) == 1:
            beat, row_role = beat_rows[0]
            parts = _sentences(beat.words, gap_s)
            if len(parts) >= 2:
                split = max(1, len(parts) - 1)
                first_words = [word for part in parts[:split] for word in part]
                last_words = [word for part in parts[split:] for word in part]
                beat_rows = [
                    (Beat("hook", beat.turn, beat.speaker, first_words,
                          f"Producer Brain approved {row_role} opening"), row_role),
                    (Beat("payoff", beat.turn, beat.speaker, last_words,
                          f"Producer Brain approved {row_role} payoff"), row_role),
                ]

        if kept_sents and beat_rows:
            beats = [item[0] for item in beat_rows]
            beats[0].role = "hook"
            beats[0].purpose = "Producer Brain approved hook"
            payoff_index = next(
                (index for index in range(len(beats) - 1, -1, -1)
                 if not is_ack(beats[index].text) and not is_procedural(beats[index].text)),
                len(beats) - 1,
            )
            beats[payoff_index].role = "payoff"
            beats[payoff_index].purpose = "Producer Brain verified payoff"
            for index, (beat, row_role) in enumerate(beat_rows[1:], start=1):
                if index == payoff_index:
                    continue
                if index > payoff_index:
                    beat.role = "reaction"
                    beat.purpose = "complete reaction retained after Producer Brain payoff"
                    continue
                beat.role = "turn" if "turn" in row_role and index >= len(beat_rows) // 2 else "setup"
            anchor = Anchor(beats[payoff_index].start_s, "money_moment", beats[payoff_index].turn,
                            "producer_short_plan")
            payoff_k = next(
                (sent.k for sent in kept_sents
                 if sent.start_s - 1e-6 <= beats[payoff_index].start_s <= sent.end_s + 1e-6),
                kept_sents[-1].k,
            )
            cand = Candidate(
                anchor, kept_sents[0].k, kept_sents[-1].k, kept_sents, [],
                beats=beats, payoff_k=payoff_k,
                notes=["executed validated Producer Brain sequence before heuristic search"],
            )
            cand = assign_focus(cand, c)
            if not tile_known:
                for beat in cand.beats:
                    beat.focus, beat.punch_in = "duo", False
            segs, seg_focus, seg_punch = _segments_for(cand, c, tw)
            duration = sum(segment.duration for segment in segs)
            cand = score_candidate(cand, c, tile_known, duration)
            alignment = producer_alignment(segs, brain_plan, words)
            kept_words = [word for beat in cand.beats for word in beat.words]
            cards, hard, planner_used, cres = caption_cards_for(
                cand, segs, c, cap_style, kept_words, key_words,
            )
            gates, cuts, qa = qc_gates(
                cand, segs, cards, case, case_key, tw, sents, c, cap_style, cres, hard,
                kept_words=kept_words,
            )
            if not alignment["ok"]:
                gates.append({
                    "gate": "producer_alignment", "ok": False,
                    "detail": "rendered ranges do not execute every Producer Brain beat",
                    "critical": True,
                })
            else:
                gates.append({
                    "gate": "producer_alignment", "ok": True,
                    "detail": "all Producer Brain ranges retained and the approved hook stays first",
                    "critical": True,
                })
            failed = [gate["gate"] for gate in gates if gate["critical"] and not gate["ok"]]
            if failed:
                return refused(
                    "Producer Short plan failed technical QC: " + ", ".join(failed),
                    cand.notes,
                    [{"anchor": "producer_short_plan", "at_s": anchor.t, "start_s": ranges[0][0], "total": cand.total,
                      "passes_qc": False, "failed": failed,
                      "duration_s": round(duration, 1)}],
                )
            plan = ShortPlan(
                RULESET, case_key, case_key, vid, True, None,
                {"kind": anchor.kind, "t": round(anchor.t, 3), "turn": anchor.turn,
                 "note": anchor.note},
                [{
                    "role": beat.role, "turn": beat.turn, "speaker": beat.speaker,
                    "purpose": beat.purpose, "start_s": round(beat.start_s, 3),
                    "end_s": round(beat.end_s, 3), "ranges": ranges_for(beat.words, c, tw),
                    "focus": beat.focus, "punch_in": beat.punch_in,
                    "audio_accent": beat.audio_accent, "text": beat.text,
                    "dropped": beat.dropped,
                } for beat in cand.beats],
                segs, None, False, duration, cand.scores, cand.total,
                cand.disqualified, gates, cards,
                [{"anchor": "producer_short_plan", "at_s": anchor.t, "start_s": ranges[0][0], "total": cand.total,
                  "passes_qc": True, "failed": [], "duration_s": round(duration, 1)}],
                cand.notes, tile_map or {},
                [f"Producer Brain sequence retained across {len(segs)} render segment(s)"],
                len(turns), None, seg_focus, seg_punch, cuts, qa, sorted(hard),
                planner_used, set(key_words), " ".join(sent.text for sent in kept_sents),
                word_stream_for(cand, segs),
            )
            plan.caption_style = dict(cap_style or {})
            plan.caption_audit = cres["audit"]
            plan.caption_density = cres["density"]
            return plan

    anchors = find_anchors(case, turns, lo, hi)
    if not anchors:
        return refused("no valid mini-story: no money moment, tell, receipt or answered excuse found in the case",
                       [f"{len(turns)} speaker turns scanned"])

    # every anchor -> its anchor sentence -> every (start, end) window
    scored: list[dict[str, Any]] = []
    for a in anchors[:12]:
        anchor_k = next((s.k for s in sents if s.turn == a.turn and s.start_s - 0.3 <= a.t <= s.end_s + 0.3), None)
        if anchor_k is None:
            anchor_k = next((s.k for s in sents if s.turn == a.turn), None)
        if anchor_k is None:
            continue
        ends = payoff_end(sents, anchor_k, c, quote if a.kind == "money_moment" else None)
        starts = start_options(sents, anchor_k, c)
        for end_k in ends:
            protect = set(range(anchor_k, end_k + 1))
            for start_k in starts:
                if start_k > anchor_k:
                    continue
                cand = build_window(sents, start_k, end_k, anchor_k, a, protect)
                if not cand.beats or cand.payoff is None:
                    continue
                segs, seg_focus, seg_punch = _segments_for(cand, c, tw)
                dur = sum(s.duration for s in segs)
                if dur > float(c["max_duration_s"]) + 1e-6 or dur < float(c["min_duration_s"]) - 1e-6:
                    continue                      # not a fit: another start or end will be
                cand = score_candidate(cand, c, tile_known, dur)
                cand = maybe_teaser(cand, c, tw)
                cand = assign_focus(cand, c)
                if not tile_known:
                    for b in cand.beats:
                        b.focus, b.punch_in = "duo", False
                    cand.notes.append("tile map unknown: framing stays duo, no punch-ins")
                if cand.teaser and cand.payoff is not None:
                    cand.teaser["focus"] = cand.payoff.focus
                    cand.teaser["punch_in"] = False
                segs, seg_focus, seg_punch = _segments_for(cand, c, tw)
                dur = sum(s.duration for s in segs)
                if dur > float(c["max_duration_s"]) + 1e-6:
                    cand.teaser = None            # the teaser pushed it over: drop it, keep the body
                    segs, seg_focus, seg_punch = _segments_for(cand, c, tw)
                    dur = sum(s.duration for s in segs)
                if brain_plan:
                    alignment = producer_alignment(segs, brain_plan, words)
                    if not alignment["ok"]:
                        alignment_failures.append(alignment)
                        continue
                kept_words = [w for s in cand.kept for w in s.words]
                cards, hard, planner_used, cres = caption_cards_for(cand, segs, c, cap_style, kept_words, key_words)
                gates, cuts, qa = qc_gates(cand, segs, cards, case, case_key, tw, sents, c, cap_style, cres, hard)
                scored.append({"cand": cand, "segs": segs, "focus": seg_focus, "punch": seg_punch,
                               "cards": cards, "gates": gates, "cuts": cuts, "qa": qa,
                               "hard": hard, "planner": planner_used, "duration": dur,
                               "kept_words": kept_words, "stream": word_stream_for(cand, segs),
                               "captions": cres})

    if judge and scored:
        try:
            summaries = [{"id": i, "anchor": s["cand"].anchor.kind, "note": s["cand"].anchor.note, "total": s["cand"].total,
                          "beats": [{"role": b.role, "speaker": b.speaker, "text": b.text} for b in s["cand"].beats]}
                         for i, s in enumerate(scored)]
            verdict = judge(summaries) or {}
            for i, s in enumerate(scored):
                adj = verdict.get(str(i)) or verdict.get(i) or {}
                bonus = max(-10, min(10, int(adj.get("bonus", 0))))
                if bonus:
                    s["cand"].total += bonus
                    s["cand"].notes.append(f"judge: {bonus:+d} ({adj.get('note', '')})")
        except Exception as exc:
            for s in scored:
                s["cand"].notes.append(f"judge unavailable: {exc}")

    def passes(entry: dict[str, Any]) -> bool:
        return all(g["ok"] for g in entry["gates"] if g["critical"])

    window = float(c.get("money_moment_window", 6))
    scored.sort(key=lambda s: (-(s["cand"].total + (window if s["cand"].anchor.kind == "money_moment" else 0.0)),
                               s["cand"].anchor.priority, -s["duration"], s["cand"].start_k))
    alts = [{"anchor": s["cand"].anchor.kind, "note": s["cand"].anchor.note, "at_s": round(s["cand"].anchor.t, 1),
             "start_s": round(s["cand"].kept[0].start_s, 1), "total": s["cand"].total, "scores": s["cand"].scores,
             "passes_qc": passes(s), "failed": [g["gate"] for g in s["gates"] if g["critical"] and not g["ok"]],
             "duration_s": round(s["duration"], 1)} for s in scored[:24]]
    winner = next((s for s in scored if passes(s)), None)
    if winner is None:
        why = "no candidate passed QC"
        if scored:
            best = scored[0]
            failed = [f"{g['gate']} ({g['detail']})" for g in best["gates"] if g["critical"] and not g["ok"]]
            why = (f"no candidate passed QC; best was {best['cand'].anchor.kind} @{best['cand'].anchor.t:.0f}s "
                   f"scoring {best['cand'].total}/100 — failed: " + "; ".join(failed))
        else:
            if alignment_failures:
                missing = [
                    row["role"] for row in alignment_failures[0]["required_ranges"] if not row["ok"]
                ]
                why = (
                    "Producer Short plan could not be executed without replacing its hook or "
                    f"dropping planned ranges: {', '.join(missing) or 'hook'}"
                )
            else:
                why = ("no valid mini-story: no contiguous window from an opener to a payoff fits "
                       f"{c['min_duration_s']:.0f}-{c['max_duration_s']:.0f}s")
        return refused(why, [], alts)

    cand = winner["cand"]
    beats = [{
        "role": b.role, "turn": b.turn, "speaker": b.speaker, "purpose": b.purpose,
        "start_s": round(b.start_s, 3), "end_s": round(b.end_s, 3),
        "ranges": ranges_for(b.words, c, tw), "focus": b.focus, "punch_in": b.punch_in,
        "audio_accent": b.audio_accent, "text": b.text, "dropped": b.dropped,
    } for b in cand.beats]
    mismatch = None
    if case.get("shortable") is False:
        mismatch = "scorer said not shortable; SHORTS_EDITOR_V2 found a valid mini-story"
    plan = ShortPlan(
        RULESET, case_key, case_key, vid, True, None,
        {"kind": cand.anchor.kind, "t": round(cand.anchor.t, 3), "turn": cand.anchor.turn, "note": cand.anchor.note},
        beats, winner["segs"], cand.teaser, bool(cand.teaser), winner["duration"],
        cand.scores, cand.total, cand.disqualified, winner["gates"], winner["cards"], alts, cand.notes,
        tile_map or {}, [f"body = sentences {cand.start_k}..{cand.end_k} of the case, contiguous; "
                         f"{len(cand.cuts)} audited interior cut(s)"], len(turns), mismatch,
        winner["focus"], winner["punch"], winner["cuts"], winner["qa"], sorted(winner["hard"]), winner["planner"],
        set(key_words), " ".join(s.text for s in cand.kept), winner["stream"],
    )
    plan.caption_style = dict(cap_style or {})
    plan.caption_audit = winner["captions"]["audit"]
    plan.caption_density = winner["captions"]["density"]
    return plan


def verify_same_case(plan: ShortPlan | dict[str, Any], case_key: str, case: dict[str, Any]) -> None:
    """The same-case invariant, checked at the point of use (produce()). A
    plan built for another case, or one whose ranges leave this case's span,
    raises rather than rendering."""
    d = plan.as_dict() if isinstance(plan, ShortPlan) else plan
    if d.get("case_key") != case_key or d.get("source_case_key") != case_key:
        raise ShortPlanError(f"short plan is for {d.get('case_key')!r}, not {case_key!r}")
    lo, hi = float(case["start_s"]), float(case["end_s"])
    for a, b in d.get("segments") or []:
        if a < lo - 1.0 or b > hi + 1.0:
            raise ShortPlanError(f"short range {a:.1f}-{b:.1f} leaves case {case_key} ({lo:.1f}-{hi:.1f})")


def verify_chronology(plan: ShortPlan | dict[str, Any]) -> None:
    """A short is a compression of the case, never a rearrangement of it
    (CONTENT_SPEC §3). The only permitted exception is the declared teaser:
    one range, at most teaser_max_s, that is repeated in place afterwards.
    Anything else out of order — or any other duplicated range — raises."""
    d = plan.as_dict() if isinstance(plan, ShortPlan) else plan
    segs = [(float(a), float(b)) for a, b in d.get("segments") or []]
    teaser = d.get("teaser")
    body = segs[1:] if teaser else segs
    for (a0, b0), (a1, b1) in zip(body, body[1:]):
        if a1 < b0 - 1e-6:
            raise ShortPlanError(f"short ranges out of order: {a0:.1f}-{b0:.1f} then {a1:.1f}-{b1:.1f}")
    if teaser:
        ta, tb = float(teaser["start_s"]), float(teaser["end_s"])
        if abs(segs[0][0] - ta) > 1e-6 or abs(segs[0][1] - tb) > 1e-6:
            raise ShortPlanError("teaser segment does not match the declared teaser range")
        covered = sum(max(0.0, min(b, tb) - max(a, ta)) for a, b in body)
        if covered < (tb - ta) - 0.05:
            raise ShortPlanError("teaser line is not repeated in place — that would be a rearrangement")


def verify_continuity(plan: ShortPlan | dict[str, Any], words: Sequence[Word], case: dict[str, Any],
                      cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Re-audit a plan's interior joins against the transcript at the point
    of use. Raises ShortPlanError on a join that skips substantive dialogue;
    returns the audit otherwise. This is the same check the planner runs,
    applied to whatever plan is about to be rendered — including one edited
    by hand."""
    c = _cfg(cfg)
    d = plan.as_dict() if isinstance(plan, ShortPlan) else plan
    lo, hi = float(case["start_s"]), float(case["end_s"])
    tw = timed_words(words, lo, hi, float(c["word_hold_s"]))
    segs = [Segment(float(a), float(b)) for a, b in d.get("segments") or []]
    kept = [w for s in segs for w in tw if s.start_s - 1e-6 <= w.t <= s.end_s + 1e-6]
    cuts = audit_interior_cuts(segs, tw, kept, bool(d.get("teaser")), float(c["sentence_gap_s"]))
    bad = [x for x in cuts if not x["ok"]]
    if bad:
        raise ShortPlanError(
            f"join {bad[0]['after_s']:.1f}s -> {bad[0]['before_s']:.1f}s skips substantive dialogue: "
            f"{bad[0]['skipped_text'][:160]!r}")
    return cuts


def hhmmss(t: float) -> str:
    t = max(0.0, t)
    return f"{int(t // 3600):02d}:{int(t % 3600 // 60):02d}:{t % 60:04.1f}"


def describe(plan: ShortPlan) -> str:
    """Human-readable edit plan, the thing a person reviews."""
    L: list[str] = []
    L.append(f"{RULESET}  {plan.case_key}  {'OK' if plan.ok else 'REFUSED'}"
             + (f" — {plan.refusal}" if plan.refusal else ""))
    if plan.anchor:
        L.append(f"anchor: {plan.anchor['kind']} @{hhmmss(plan.anchor['t'])} ({plan.anchor['note']})")
    L.append(f"score {plan.total}/100  " + "  ".join(f"{k} {v}/{SCORE_DIMENSIONS[k]}" for k, v in plan.scores.items()))
    if plan.disqualified:
        L.append("disqualified: " + "; ".join(plan.disqualified))
    L.append(f"duration {plan.duration_s:.1f}s over {len(plan.segments)} segment(s); "
             f"{'NON-LINEAR (declared teaser)' if plan.nonlinear else 'chronological'}; {plan.speaker_turns} speaker turns in case")
    if plan.teaser:
        L.append(f"  TEASER {hhmmss(plan.teaser['start_s'])}-{hhmmss(plan.teaser['end_s'])}  {plan.teaser['text']!r}  <- {plan.teaser['source']}")
    for b in plan.beats:
        flags = []
        if b["punch_in"]:
            flags.append("PUNCH-IN")
        if b["audio_accent"]:
            flags.append(f"accent:{b['audio_accent']}")
        L.append(f"  {b['role']:<8} {b['speaker']:<9} focus={b['focus']:<9} {hhmmss(b['start_s'])}-{hhmmss(b['end_s'])} "
                 f"({b['end_s'] - b['start_s']:.1f}s) {' '.join(flags)}")
        L.append(f"           {b['purpose']}")
        txt = b["text"]
        L.append(f"           \"{txt[:200]}{'…' if len(txt) > 200 else ''}\"")
        for r in b["ranges"]:
            L.append(f"           range {hhmmss(r[0])}-{hhmmss(r[1])}")
        for dsent in b["dropped"]:
            L.append(f"           cut: \"{dsent[:100]}{'…' if len(dsent) > 100 else ''}\"")
    L.append("segments: " + "  ".join(
        f"[{hhmmss(s.start_s)}-{hhmmss(s.end_s)} {f}{'+punch' if p else ''}]"
        for s, f, p in zip(plan.segments, plan.focus_plan, plan.punch_plan)))
    if plan.interior_cuts:
        for cut in plan.interior_cuts:
            L.append(f"  join {hhmmss(cut['after_s'])} -> {hhmmss(cut['before_s'])}: "
                     f"{'/'.join(cut['classes'])}{'' if cut['ok'] else '  FAIL'}"
                     + (f"  skipped: \"{cut['skipped_text'][:120]}\"" if cut['skipped_text'] else ""))
    for q in plan.question_answer:
        L.append(f"  Q/A {'ok  ' if q['ok'] else 'FAIL'} \"{q['question'][:70]}\" -> \"{q['on_screen_next'][:70]}\"")
    if plan.fit_log:
        L.append("fit: " + " | ".join(plan.fit_log))
    if plan.captions:
        L.append(f"captions: {len(plan.captions)} one-line phrases ({plan.caption_planner}), kinetic on the rail, "
                 f"{plan.caption_density.get('per_second', '?')} changes/s, "
                 f"{sum(1 for a in plan.caption_audit if not a.get('kept'))} disfluencies omitted for display; first: " + " / ".join(
            f"[{c['speaker'][:3] if c.get('speaker') else '?'}: {' | '.join(c.get('chunks') or [c['text']])}]" for c in plan.captions[:10]))
    L.append("QC: " + "  ".join(f"{g['gate']}={'ok' if g['ok'] else 'FAIL'}" for g in plan.qc))
    for g in plan.qc:
        if not g["ok"]:
            L.append(f"   FAIL {g['gate']}: {g['detail']}")
    if plan.alternatives:
        L.append("alternatives: " + "; ".join(
            f"{a['anchor']}@{a['at_s']:.0f}s start {a['start_s']:.0f}s {a['duration_s']:.0f}s {a['total']}"
            f"{'' if a['passes_qc'] else ' (QC: ' + ','.join(a['failed']) + ')'}"
            for a in plan.alternatives[:12]))
    for n in plan.notes:
        L.append(f"note: {n}")
    if plan.mismatch_with_scorer:
        L.append(f"MISMATCH: {plan.mismatch_with_scorer}")
    return "\n".join(L)
