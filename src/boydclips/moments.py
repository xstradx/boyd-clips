"""Find the moments Judge Boyd goes off, anywhere in the archive.

WHAT THIS IS FOR
----------------
Nathan, 2026-08-18: "the clips we're supposed to get is when judge boyd is all
sassy and saying out of pocket stuff to defendants" ... "when she chews people
out."

Everything upstream of this treated a CASE as the unit - score a hearing, gate
it, render it end to end. Wrong unit. The product is a MOMENT: the ninety
seconds where she stops doing procedure and starts talking. The case is just
the container, and most of a container is paperwork.

TWO DEAD ENDS, RECORDED SO THEY ARE NOT RETRIED
-----------------------------------------------
1. HAND-WRITTEN SASS PATTERNS. A list of phrases seeded from
   prompts/score_cases.md. Fires on anyone - a prosecutor saying "excuse me"
   scores - and only ever finds phrasings already known.

2. N-GRAM FREQUENCY MINING. Segment turns, split judicial vs other, mine
   n-grams enriched on the judicial side. Ran it twice, both times it returned
   pure boilerplate: "the court will find there's sufficient evidence", then
   after filtering, "no employment as a home health care provider", "field
   visits one time per month". Those are probation conditions being read aloud.

   The failure is structural and worth stating plainly: FREQUENCY MINING CANNOT
   FIND RIFFS, because a riff is said once. Boilerplate repeats verbatim across
   hundreds of dockets, so it dominates every frequency ranking by construction.
   The thing that makes a riff a riff is the opposite property - it is unlike
   anything else in the corpus.

THE METHOD: NOVELTY, THEN TWO CORRECTIONS IT NEEDS
---------------------------------------------------
Score a turn by how UNUSUAL its vocabulary is for this courtroom. Corpus-wide
document frequency over every judicial turn; a turn's novelty is the mean IDF
of its content words. Reading probation conditions scores near zero - every
word is standard. The spearmint-gum riff and the dirty-kitchen riff are full of
words that appear nowhere else in a courtroom.

Run raw, that ranking is WRONG in two specific ways, both measured on the
archive rather than guessed:

  * DOCKET ROLL-CALL took 4 of the top 8. "Luis Alec Martinez, Carlos Pettis,
    Emanuel Moses Perez..." - every proper name is a corpus hapax, so a list of
    forty of them scores maximum novelty. FIX: proper-noun suppression. A token
    capitalised in more than 60% of its corpus appearances is a name, and names
    are dropped from the novelty calculation entirely.

  * EXPERT TESTIMONY took 2 more. A medical examiner describing "irregular
    contour of the nasal bridge... hemorrhage beneath the skin" is rare
    vocabulary and is not the judge talking at all. FIX: the JUDICIAL and
    EXAMINATION filters, NOT address density - a pathologist says "you can
    see" constantly and clears the second-person floor easily. Measured after
    a test asserting the opposite failed.

  * ADDRESS DENSITY is what removes ROLL CALL specifically. When Boyd goes
    after somebody she says YOU constantly and, in the riffs, I constantly -
    "I don't drink. Why don't I drink?" A list of forty names has neither.

Final score = novelty (proper nouns removed) + second-person rate + first-person
rate + her documented tells. The tells are a BOOST, never a gate, so the search
is not limited to phrasings already known.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

# --- speaker turns -------------------------------------------------------
# Auto-captions mark speaker changes with '>>' inside a word token
# ('>> Yes,'). Verified on the archive: ~4.7 markers/min, median turn 9 words,
# p90 48. There are no speaker NAMES - 1 of 40 transcripts contains any.
TURN = ">>"

# Only used to decide "is the bench talking". Deliberately boring and frequent.
# MEASURED CORRECTION: this list originally ended "|ma'?am|sir\b", which put
# cross-examination straight into the top 10 - counsel says "sir" in every
# other sentence. Removed. Everything left is something only the bench says.
JUDICIAL = re.compile(
    r"\b(the court (will|is|finds|orders|accepts)|i'?m going to (sentence|order|find|accept)"
    r"|do you understand|have a seat|raise your right hand"
    r"|you'?re (placed on|sentenced to)|i'?ll accept|community supervision"
    r"|deferred adjudication|go (on|off) the record|anything further"
    r"|call(ing)? the next|court costs"
    r"|let me (just )?(tell|ask) you|here'?s the (thing|problem)|guess what)", re.I)

# Turns that are somebody EXAMINING a witness. High "you" density, high
# novelty, not her. Measured: without this, 4 of the top 8 were cross.
EXAMINATION = re.compile(
    r"\b(no further questions|pass the witness|your witness|objection|hearsay"
    r"|sustain(ed)?|overruled|showing you what|marked as|move to admit"
    r"|for the record what is|redirect|may i approach)\b", re.I)

# Two or more deferential answers inside ONE turn means the caption stream
# dropped a '>>' and the turn actually spans both speakers. Her monologues do
# not contain the replies to themselves.
DIALOGUE = re.compile(r"\b(yes|no),?\s+(sir|ma'?am)\b", re.I)

# Long stretches that are still procedure. Measured: without this the top of
# every ranking is the probation-conditions recital, which runs 200+ words.
BOILER = re.compile(
    r"\b(sufficient evidence|exhibits one and attachments|application for deferred"
    r"|state jail facility|fine probated|home health care provider|field visits"
    r"|proof of employment within|urinalysis|restitution in the amount"
    r"|right to appeal|court costs and fees|report to the (probation|community))\b", re.I)

# Her documented tells. A BOOST, never a gate. Every one is quoted in
# prompts/score_cases.md as coming from a winning video, or was pulled verbatim
# from a hearing that scored 70+ on boyd_register during this session.
TELLS: list[tuple[str, float, str]] = [
    (r"\bguess what\b", 2.5, "guess what"),
    (r"\bfor the youtube\b", 3.0, "for the YouTube"),
    (r"\bi'?m not feeling you\b", 3.0, "not feeling you"),
    (r"\blet me (just )?(tell you|stop you|ask you)\b", 1.5, "let me tell you"),
    (r"\bso why shouldn'?t i\b", 2.5, "why shouldn't I"),
    (r"\bthen why (do|does|did) you\b", 2.0, "then why do you"),
    (r"\bhere'?s the (thing|problem)\b", 1.5, "here's the thing"),
    (r"\bthat'?s not what i asked\b|\bi asked you\b|\banswer my question\b", 2.0, "answer the question"),
    (r"\bmumbl\w+|\brun[- ]on sentences\b", 2.5, "mumbling"),
    (r"\bstop (interrupting|talking)\b", 2.5, "stop talking"),
    (r"\bdo you think i\b|\bdo you know how many\b", 2.5, "do you know how many"),
    (r"\bgrown (man|woman)\b|\byou'?re an adult\b", 2.0, "you're an adult"),
    (r"\bthose were (not mistakes|horrible choices)\b|\bthose are choices\b", 3.0, "those were choices"),
    (r"\bmake better (decisions|choices)\b", 2.0, "make better choices"),
    (r"\bdon'?t blame it on\b", 2.5, "don't blame it on"),
    (r"\bsmell(s|ed)? like\b|\bsense of smell\b", 2.0, "smell"),
    (r"\bkeep bringing children\b|\bcannot (financially )?support\b", 3.0, "children you can't support"),
    (r"\bnot my first rodeo\b|\bi wasn'?t born yesterday\b", 3.0, "not my first rodeo"),
    (r"\bat what point\b", 1.5, "at what point"),
    (r"\bcorrect me if i'?m wrong\b", 1.5, "correct me if I'm wrong"),
    (r"\bconsequences for (your )?actions\b", 2.0, "consequences"),
    (r"\bwhat did you think was going to happen\b", 3.0, "what did you think"),
    (r"\bthose are not your friends\b", 3.0, "not your friends"),
    (r"\bget out of my courtroom\b|\bplace the handcuffs\b", 2.5, "custody"),
]
_TELLS = [(re.compile(p, re.I), w, lab) for p, w, lab in TELLS]

_WORD = re.compile(r"[a-z']{3,}")
_TOKEN = re.compile(r"[A-Za-z']{3,}")
_YOU = re.compile(r"\b(you|your|you'?re|you'?ve|you'?ll|yourself)\b", re.I)
_I = re.compile(r"\b(i|i'?m|i'?ve|i'?ll|my|me|myself)\b", re.I)
STOP = set(
    "the and that you your for with have has this not but they them there their "
    "was were are all any can did does from going him her his how into its just "
    "like more most now one only other our out over said she some such than then "
    "these those too very what when where which who why will would about after "
    "again because been before being below between both during each few further "
    "here once same should some until while yes okay right well know think mean "
    "want going get got say tell told back come came take took give gave make "
    "made need needs case court judge state county today morning".split())

# She also chats. Measured on the v4 ranking: 5 of the top 12 were her talking
# about LSU's coaching hires, the Pittsburgh Steelers, a self-checkout receipt
# and driverless taxis - all high novelty, all directed at courtroom staff
# between cases. Novel and second-person, but nobody is being chewed out.
BANTER = re.compile(
    r"\b(lsu|steelers|texas a&m|touchdown|coach(ing)?|football|quarterback|season"
    r"|netflix|tv show|movie|uber|lyft|driverless|thanksgiving|christmas party"
    r"|birthday|vacation|air ?fryer|recipe)\b", re.I)

# What separates a chew-out from a chat: she is holding somebody to account.
CONFRONT = re.compile(
    r"\b(excuse[sd]?\b|responsib\w+|consequence|choices?|blame|accountab\w+"
    r"|you (need|have|had|ought) to|you should(n'?t)?|you can'?t|you didn'?t"
    r"|why (would|did|do) you|explain to me|that'?s not|you'?re not\b"
    r"|probation|violat\w+|positive|jail|prison|charge[sd]?|victim|offense"
    r"|drugs?|marijuana|alcohol|test(ed)?|court order|supervision|child support"
    r"|your (kids?|children|son|daughter)|grown|adult)\b", re.I)

MIN_TURN_WORDS = 45      # below this it is procedure, not a riff
MIN_CONFRONT = 3         # distinct accountability markers, measured floor
PROPER_RATIO = 0.6       # capitalised this often in the corpus => it is a name

# Measured floors. A roll-call of forty names and a pathologist describing a
# fracture both score high novelty and both sit near zero on these.
MIN_YOU_RATE = 2.0       # "you" words per 100 words


@dataclass
class Moment:
    video_id: str
    start_s: float
    end_s: float
    novelty: float
    tell_score: float
    labels: list[str] = field(default_factory=list)
    text: str = ""
    words: int = 0
    you_rate: float = 0.0
    i_rate: float = 0.0

    @property
    def score(self) -> float:
        """Novelty carries the ranking; address density and tells sharpen it.

        Weights are a starting position, chosen so that a turn has to be BOTH
        unusual and directed at somebody to reach the top. No published clip
        has a view count yet, so nothing here is fitted to an outcome.
        """
        return round(self.novelty * 100
                     + min(self.you_rate, 12.0) * 2.0
                     + min(self.i_rate, 12.0) * 1.5
                     + self.tell_score * 4, 1)

    @property
    def url(self) -> str:
        return (f"https://www.youtube.com/watch?v={self.video_id}"
                f"&t={int(max(0, self.start_s - 4))}s")

    @property
    def clock(self) -> str:
        m = int(self.start_s // 60)
        return f"{m // 60}:{m % 60:02d}:{int(self.start_s % 60):02d}"


def turns(transcript) -> list[tuple[float, float, str]]:
    """Split a transcript into speaker turns on the '>>' markers."""
    ws = transcript.words
    idx = [i for i, w in enumerate(ws) if TURN in w.w]
    out = []
    for a, b in zip(idx, idx[1:] + [len(ws)]):
        txt = " ".join(w.w for w in ws[a:b]).replace(TURN, " ").strip()
        if txt:
            out.append((ws[a].t, ws[min(b, len(ws) - 1)].t, txt))
    return out


def content_words(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in STOP]


def build_idf(all_turn_texts) -> dict[str, float]:
    """Document frequency over judicial turns, corpus-wide, names removed.

    Built ONCE across every transcript rather than per docket - a word is only
    genuinely unusual if it is unusual for this courtroom as a whole.

    Proper nouns are identified here rather than by a name list: a token
    capitalised in more than PROPER_RATIO of its appearances is a name. They
    are recorded in the "__PROPER__" set and excluded from novelty, because a
    docket roll-call is nothing but hapax names and would otherwise win.
    """
    df: Counter = Counter()
    cap: Counter = Counter()
    tot: Counter = Counter()
    n = 0
    for txt in all_turn_texts:
        n += 1
        df.update(set(content_words(txt)))
        for tok in _TOKEN.findall(txt):
            low = tok.lower()
            tot[low] += 1
            if tok[0].isupper():
                cap[low] += 1
    proper = {w for w, c in tot.items()
              if c >= 2 and cap.get(w, 0) / c > PROPER_RATIO}
    out: dict[str, float] = {w: math.log(n / c) for w, c in df.items()}
    out["__N__"] = float(n)
    out["__PROPER__"] = proper          # type: ignore[assignment]
    return out


def novelty(text: str, idf: dict[str, float]) -> float:
    """Mean IDF of a turn's content words, names excluded, normalised to ~0..1.

    High = vocabulary this courtroom does not otherwise use, which once names
    are removed means she is telling a story rather than reciting or reading a
    list.
    """
    proper = idf.get("__PROPER__") or set()
    ws = [w for w in content_words(text) if w not in proper]
    if len(ws) < 12:
        return 0.0
    n = idf.get("__N__", 1000.0)
    ceiling = math.log(n)  # a word seen exactly once
    vals = [min(idf.get(w, ceiling), ceiling) for w in set(ws)]
    return sum(vals) / (len(vals) * ceiling)


def address_rates(text: str) -> tuple[float, float]:
    """(second-person, first-person) words per 100 words.

    Removes docket roll call, which is lexically novel and addressed to nobody.
    It does NOT remove expert testimony - "you can see the fracture site" is
    second-person too. EXAMINATION and JUDICIAL handle that.
    """
    n = max(1, len(text.split()))
    return (100.0 * len(_YOU.findall(text)) / n,
            100.0 * len(_I.findall(text)) / n)


def tells(text: str) -> tuple[float, list[str]]:
    score, labels = 0.0, []
    for rx, w, lab in _TELLS:
        if rx.search(text):
            score += w
            labels.append(lab)
    return score, labels


def judicial_turns(transcript) -> list[tuple[float, float, str]]:
    """Her turns, long enough to be a riff and actually spoken by her.

    Four filters, each added because the ranking without it was measurably
    wrong on the archive:
      MIN_TURN_WORDS  - shorter than this is procedure, not a riff
      JUDICIAL        - the bench is speaking
      BOILER          - long, but it is conditions being read aloud
      EXAMINATION     - counsel questioning a witness, which reads as her
      DIALOGUE (x2)   - the caption stream dropped a speaker marker
      BANTER          - she is talking about football, not about the defendant
      CONFRONT        - somebody is actually being held to account
    """
    out = []
    for a, b, txt in turns(transcript):
        if len(txt.split()) < MIN_TURN_WORDS:
            continue
        if not JUDICIAL.search(txt):
            continue
        if BOILER.search(txt) or EXAMINATION.search(txt):
            continue
        if len(DIALOGUE.findall(txt)) >= 2:
            continue
        if BANTER.search(txt):
            continue
        if len({m.group(0).lower() for m in CONFRONT.finditer(txt)}) < MIN_CONFRONT:
            continue
        out.append((a, b, txt))
    return out


def scan(transcript, idf: dict[str, float], min_score: float = 0.0,
         min_you: float = MIN_YOU_RATE) -> list[Moment]:
    """Score every riff-length judge turn in one docket.

    `min_you` is a hard floor, not a weight: a turn that never says "you" is
    not a chew-out, whatever else it scores. It is what removes roll call and
    expert testimony.
    """
    out = []
    for a, b, txt in judicial_turns(transcript):
        you, me = address_rates(txt)
        if you < min_you:
            continue
        nov = novelty(txt, idf)
        ts, labels = tells(txt)
        m = Moment(transcript.video_id, a, b, round(nov, 4), ts, labels,
                   txt, len(txt.split()), round(you, 2), round(me, 2))
        if m.score >= min_score:
            out.append(m)
    return out
