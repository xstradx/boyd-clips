"""BOYD_EDITORIAL_V2 — the one definition of what makes a Judge Boyd video.

Every editorial rule the pipeline applies lives here or in the prompt files that
quote it; nothing else carries its own copy. Readers:

  * ``analyze.py``          — schema dimension names, total, gate, decision
  * ``config.py``           — validates ``analysis.rubric_weights`` against DIMENSIONS
  * ``tools/check_title.py``— editorial title validation (hype words, families, band)
  * ``tools/banger_digest.py`` / ``tools/hearing_measure.py`` — the manual path's
    proxy labels and its ranking order
  * ``thumbgen/make.py``    — what the thumbnail builder is told about the story
  * ``prompts/*.md``        — quote the same numbers; ``tests/test_pipeline.py``
    asserts the prompt and this file agree

Nathan, 2026-09-06: the pipeline is not looking for "court cases involving Judge
Boyd". It is looking for a clear human story with tension, escalation, surprise,
consequence, emotion, contradiction, absurdity, or a memorable Judge Boyd
interaction that can be understood and packaged honestly. A serious charge, a
long hearing, a loud judge or a sentence on its own is not a video.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

RULESET = "BOYD_EDITORIAL_V2"

# ---------------------------------------------------------------- the rubric
# dimension -> maximum points. The model scores each dimension on ITS OWN scale
# (0..max); the total is the plain sum. Sums to 100.
DIMENSIONS: dict[str, int] = {
    "story_engine": 20,   # setup -> escalation/reveal -> payoff; one-sentence explainable
    "payoff": 20,         # the footage delivers the receipt on camera
    "boyd_factor": 15,    # her editorial contribution, not her presence or volume
    "stakes": 15,         # visible consequence tied to the story
    "clarity": 10,        # who wants what, what went wrong, what happens next
    "packaging": 15,      # several truthful, materially different title angles exist
    "thumbnail": 5,       # a reaction / compact verified line; never rescues a dull case
}
assert sum(DIMENSIONS.values()) == 100

# Score bands per dimension, as the prompt states them (kept here so the prompt
# and the code cannot drift; the test compares them).
BANDS: dict[str, list[tuple[int, int, str]]] = {
    "story_engine": [(0, 4, "routine proceeding, no clear narrative"),
                     (5, 9, "one mildly interesting detail, little progression"),
                     (10, 14, "clear setup and understandable tension or problem"),
                     (15, 17, "strong escalation, contradiction, emotional turn or unusual situation"),
                     (18, 20, "exceptional clean narrative: setup -> escalation/reveal -> payoff")],
    "payoff": [(0, 4, "interesting premise but the payoff is off-camera or unclear"),
               (5, 9, "partial payoff"),
               (10, 14, "clear on-camera payoff"),
               (15, 17, "strong, memorable payoff"),
               (18, 20, "extremely clean 'THIS is the moment' payoff that anchors the video")],
    "boyd_factor": [(0, 3, "mostly passive or procedural"),
                    (4, 7, "she explains or handles the matter normally"),
                    (8, 11, "memorable exchange, probing question, reaction, warning, correction or sentencing explanation"),
                    (12, 15, "her interaction drives the story: she exposes, challenges, changes tone, or delivers the central consequence")],
    "stakes": [(0, 3, "little visible consequence"),
               (4, 7, "some meaningful legal or personal consequence"),
               (8, 11, "clear incarceration, supervision, family, safety, freedom or major legal stakes"),
               (12, 15, "the consequence is significant AND directly tied to the story and payoff")],
    "clarity": [(0, 2, "very difficult to understand"),
                (3, 5, "requires substantial explanation"),
                (6, 8, "understandable with brief setup"),
                (9, 10, "the viewer understands the conflict almost immediately")],
    "packaging": [(0, 3, "only boring docket-style titles are truthful"),
                  (4, 7, "one usable angle"),
                  (8, 11, "several strong truthful curiosity angles"),
                  (12, 15, "extremely packageable: clear tension/reveal/consequence, multiple accurate titles")],
    "thumbnail": [(0, 0, "no useful visual or verbal moment"),
                  (1, 2, "usable but generic"),
                  (3, 4, "strong expression or compact verified line"),
                  (5, 5, "excellent reaction plus a short quote or visual that instantly reinforces the story")],
}

# ---------------------------------------------------------------- decisions
TIER_A = 85          # exceptional
TIER_MAKE = 78       # good enough to make; must pass every hard gate
TIER_HOLD = 70       # manual review; say what is missing
REPEAT_TIE_WINDOW = 3.0   # a repeat defendant may break a tie only within this many points

DECISIONS = ("MAKE", "HOLD", "SKIP")

# Editorial eligibility gate — applied by the model BEFORE numeric scoring,
# checked by the code before the score threshold. Any one normally rejects.
GATE_REASONS: dict[str, str] = {
    "routine": "mostly scheduling, resets, admonishments, paperwork, logistics, or a straightforward sentencing with no distinguishing moment",
    "no_story": "cannot complete 'This video is interesting because ___' beyond 'because Judge Boyd sentenced somebody'",
    "no_payoff": "the interesting premise is mentioned but the footage contains no reveal, reaction, decision, admission, confrontation or consequence",
    "context_dependency": "the viewer would need minutes of legal or procedural explanation before the moment matters",
    "fake_packaging": "fewer than three materially different, truthful, interesting title angles exist without exaggeration",
    "charge_severity": "the only thing compelling is the charge (murder, children, guns, drugs, death, injury, exposure), not the footage",
    "empty_conflict": "ordinary disagreement with no escalation, revelation, consequence, unusual behaviour or memorable line",
}

STORY_ENGINES = [
    "defendant gives an absurd or unbelievable explanation",
    "defendant contradicts themselves",
    "Boyd catches a lie or inconsistency",
    "an important fact is revealed during the hearing",
    "defendant keeps arguing or pushing back",
    "defendant does not understand or accept the seriousness of the situation",
    "defendant was previously given leniency and squandered it",
    "supervision violation with a clear last chance -> blew it arc",
    "defendant makes an unexpected admission",
    "Boyd discovers something that changes the direction or tone of the hearing",
    "an attorney reveals a surprising fact",
    "defendant minimises conduct and Boyd challenges it",
    "emotional family / victim / defendant moment with understandable stakes",
    "unusually consequential sentencing decision",
    "unusual set of facts that can be explained simply",
    "defendant's behaviour creates escalating tension",
    "Boyd delivers a memorable, specific response or consequence",
    "expectation -> reversal", "setup -> reveal", "excuse -> receipt",
    "warning -> violation -> consequence",
]

# ---------------------------------------------------------------- titles
TITLE_HARD_MAX = 70            # never changes (analyze._trim_title enforces it)
TITLE_TARGET = (45, 65)        # editorial target, not a rule to damage a title for
TITLE_WEIGHTS = {"truthfulness": 30, "curiosity": 25, "specificity": 20,
                 "clarity": 15, "natural_language": 10}
TITLE_MIN_CANDIDATES = 8
TITLE_MIN_FAMILIES = 4

TITLE_FAMILIES: dict[str, str] = {
    "reveal": "an actual reveal occurs on camera",
    "consequence": "a consequence is clearly present",
    "contradiction": "the record supports a contradiction; say 'doesn't add up' unless deception is clearly shown",
    "behavior": "sustained pushback or behaviour actually occurs",
    "absurd_explanation": "an explanation is genuinely central",
    "warning_last_chance": "a prior chance is supported by the record",
    "admission": "an actual admission occurs",
    "emotional_stakes": "a family / victim / defendant turn drives the case",
    "decision": "the judge's decision itself is the tension",
}

# Words that make a title hype instead of event. Advisory unless obviously false.
HYPE_WORDS = ["shocking", "insane", "destroyed", "destroys", "owned", "owns",
              "humiliated", "humiliates", "brutal", "savage", "epic",
              "instant karma", "instantly regrets", "regrets"]
GENERIC_CLICKBAIT = [
    r"couldn'?t believe this\b", r"can'?t believe this\b", r"you won'?t believe",
    r"what happens next", r"changes everything", r"\bthis\s*[!.]*$",
    r"wait for it", r"gone wrong",
]
DOCKET_LANGUAGE = [r"\bappears before\b", r"\bregarding\b", r"\bmotion to (revoke|adjudicate)\b",
                   r"\bcause (number|no\.?)\b", r"\bpursuant\b", r"\bdefendant appears\b"]
_EMOJI = re.compile(r"[\U0001F300-\U0001FAFF☀-➿]")
_CAPSWORD = re.compile(r"\b[A-Z]{3,}\b")

# ---------------------------------------------------------------- thumbnail quotes
QUOTE_WORDS = (2, 6)   # ideal combined length; shorter is generally better
FILLER_QUOTES = ["yes your honor", "no your honor", "yes ma'am", "no ma'am", "yes sir",
                 "no sir", "okay", "ok", "i understand", "thank you judge", "thank you",
                 "yes judge", "no judge"]

# ---------------------------------------------------------------- manual-path proxies
# The lexical tools cannot read a story. They order what the editorial pass
# reads FIRST. Each proxy names the dimension it approximates so nobody
# mistakes a regex count for the rubric.
PROXIES: dict[str, dict[str, Any]] = {
    "family":    {"dimension": "stakes",       "weight": 3.0},
    "confront":  {"dimension": "story_engine", "weight": 3.0},
    "prison":    {"dimension": "stakes",       "weight": 2.5},
    "disbelief": {"dimension": "boyd_factor",  "weight": 2.5},
    "heinous":   {"dimension": "stakes",       "weight": 1.0},   # DEMOTED: charge severity is a trap (PART 2)
    "begging":   {"dimension": "story_engine", "weight": 2.0},
    "sharp_q":   {"dimension": "boyd_factor",  "weight": 2.0},
    "reveal":    {"dimension": "payoff",       "weight": 3.0},   # NEW: "turns out", "police report says", "didn't tell"
    "excuse":    {"dimension": "story_engine", "weight": 2.5},   # NEW: "I didn't know", "I was just", "it wasn't me"
    "notoriety": {"dimension": "packaging",    "weight": 1.0},
}
MANUAL_RANK_ORDER = ["gate_pass", "total", "story_engine", "payoff", "packaging"]


# ---------------------------------------------------------------- helpers
def total_score(scores: Mapping[str, Mapping[str, Any]]) -> float:
    """Plain sum of per-dimension points, each clamped to its maximum."""
    tot = 0.0
    for dim, mx in DIMENSIONS.items():
        raw = float((scores.get(dim) or {}).get("score", 0) or 0)
        tot += max(0.0, min(raw, float(mx)))
    return round(tot, 1)


def over_max(scores: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """Dimensions the model scored above their maximum (clamped, but say so)."""
    out = []
    for dim, mx in DIMENSIONS.items():
        raw = float((scores.get(dim) or {}).get("score", 0) or 0)
        if raw > mx:
            out.append(f"{dim} {raw:g}>{mx}")
    return out


def tier(total: float) -> str:
    if total >= TIER_A:
        return "A"
    if total >= TIER_MAKE:
        return "MAKE"
    if total >= TIER_HOLD:
        return "HOLD"
    return "SKIP"


def decision(total: float, gate_pass: bool) -> str:
    """MAKE / HOLD / SKIP. The editorial gate outranks the number."""
    if not gate_pass:
        return "SKIP"
    t = tier(total)
    return "MAKE" if t in ("A", "MAKE") else t


def prefer_repeat(candidate_total: float, repeat_total: float, window: float = REPEAT_TIE_WINDOW) -> bool:
    """PART 5: a repeat defendant may win only when within the tie window."""
    return (candidate_total - repeat_total) <= window


def tiebreak_order(cases: list, is_repeat, window: float = REPEAT_TIE_WINDOW) -> list:
    """Order ELIGIBLE candidates by total, letting repeat-defendant continuity
    break ties only inside `window` points.

    Semantics, deliberately explicit (no multiplier):
      * a candidate whose total is more than `window` above another always
        stays ahead of it, repeat or not;
      * a repeat may move ahead of a non-repeat only when the non-repeat's
        total exceeds the repeat's by at most `window`;
      * two repeats, or two non-repeats, compare on raw total;
      * ties on the key keep the incoming order (stable sort).
    This is exactly the ordering produced by comparing `total + window` for
    repeats against raw totals for one-offs, so that is how it is computed.
    Gates are not this function's job: pass it only cases that already passed.
    """
    def key(c):
        t = float(c.get("total_score") or 0.0)
        return -(t + (window if is_repeat(c) else 0.0))
    return sorted(cases, key=key)


def rationale_block(case: Mapping[str, Any]) -> str:
    """PART 6 — the auditable rationale for one scored case, from existing fields."""
    ed = case.get("editorial") or {}
    sc = case.get("scores") or {}
    lines = [
        f"STORY ANGLE: {ed.get('story_angle', '')}",
        f"MONEY MOMENT: {ed.get('money_moment', '')}"
        + (f"  (@{float(ed['money_moment_s']):.0f}s)" if ed.get("money_moment_s") is not None else ""),
        f"WHY VIEWER CARES: {ed.get('why_viewer_cares', '')}",
        "SCORE BREAKDOWN:",
    ]
    labels = {"story_engine": "Story Engine", "payoff": "Payoff", "boyd_factor": "Boyd Factor",
              "stakes": "Stakes", "clarity": "Clarity", "packaging": "Packaging", "thumbnail": "Thumbnail"}
    for dim, mx in DIMENSIONS.items():
        d = sc.get(dim) or {}
        lines.append(f"  {labels[dim]} {float(d.get('score', 0) or 0):g}/{mx} — {d.get('justification', '')}")
    total = case.get("total_score", total_score(sc))
    lines.append(f"TOTAL: {float(total):g}/100  ({tier(float(total))})")
    gate_fail = list(ed.get("gate_failures") or [])
    lines.append("GATE: " + ("pass" if ed.get("gate_pass", True) and not gate_fail else "FAIL " + ", ".join(gate_fail)))
    lines.append(f"DECISION: {case.get('decision') or decision(float(total), bool(ed.get('gate_pass', True)))}")
    if case.get("ineligible_reason"):
        lines.append(f"INELIGIBLE: {case['ineligible_reason']}")
    lines.append(f"WEAKNESS: {ed.get('weakness', '')}")
    angles = ed.get("title_angles") or []
    if angles:
        lines.append("TITLE ANGLES: " + " | ".join(angles))
    return "\n".join(lines)


# ---------------------------------------------------------------- title checks
def title_flags(title: str) -> list[str]:
    """Advisory editorial flags (PART 7). Accuracy refusals live in check_title.py."""
    low = title.lower()
    flags = []
    for w in HYPE_WORDS:
        if re.search(r"\b" + re.escape(w) + r"\b", low):
            flags.append(f"hype word '{w}' — let the event carry it (RULE 7)")
    for pat in GENERIC_CLICKBAIT:
        if re.search(pat, low):
            flags.append("generic clickbait pattern — specific curiosity beats vague hype (RULE 3)")
            break
    for pat in DOCKET_LANGUAGE:
        if re.search(pat, low):
            flags.append("docket language — say it the way a person would (RULE 5)")
            break
    if _EMOJI.search(title):
        flags.append("emoji (RULE 7)")
    caps = _CAPSWORD.findall(title)
    if len(caps) > 4:
        flags.append(f"{len(caps)} ALL-CAPS words — reads as fake urgency (RULE 7)")
    n = len(title)
    if n > TITLE_HARD_MAX:
        flags.append(f"{n} chars over the hard ceiling {TITLE_HARD_MAX}")
    elif not TITLE_TARGET[0] <= n <= TITLE_TARGET[1]:
        flags.append(f"{n} chars, editorial target {TITLE_TARGET[0]}–{TITLE_TARGET[1]} (soft)")
    if re.search(r"\b(lying|liar|lied)\b", low):
        flags.append("asserts deception — only if the record clearly supports it; else 'doesn't add up' (RULE 2)")
    return flags


_FAMILY_PATTERNS = [
    ("reveal", r"\b(learns|finds out|discovers|turns out|realizes|realises|reveals)\b"),
    ("admission", r"\b(admits|admission|confesses|comes clean)\b"),
    ("contradiction", r"\b(doesn'?t add up|story (falls apart|unravels)|catches|contradicts|notices)\b"),
    ("warning_last_chance", r"\b(last chance|one more chance|another chance|second chance|warned|warning)\b"),
    ("consequence", r"\b(changes everything|did it again|comes back|back in court|sent to prison|revoked|loses|costs him|costs her)\b"),
    ("behavior", r"\b(keeps (arguing|talking|interrupting)|won'?t stop|argues with|talks back)\b"),
    ("absurd_explanation", r"\b(explanation|excuse|his story|her story|explains why)\b"),
    ("emotional_stakes", r"\b(family|mother|father|son|daughter|speaks|breaks down|tears)\b"),
    ("decision", r"\b(has to decide|had to decide|decides|decision|whether to)\b"),
]


def title_family(title: str) -> str | None:
    low = title.lower()
    for fam, pat in _FAMILY_PATTERNS:
        if re.search(pat, low):
            return fam
    return None


# ---------------------------------------------------------------- quote checks
def quote_flags(quote: str) -> list[str]:
    q = re.sub(r"[^a-z' ]+", " ", quote.lower()).split()
    flags = []
    if not q:
        return ["empty quote"]
    if not QUOTE_WORDS[0] <= len(q) <= QUOTE_WORDS[1]:
        flags.append(f"{len(q)} words, ideal {QUOTE_WORDS[0]}–{QUOTE_WORDS[1]} (shorter is better)")
    norm = " ".join(q)
    if norm in FILLER_QUOTES:
        flags.append("generic filler — only if the context makes it unusually meaningful (PART 9)")
    return flags


def quote_repeats_title(quote: str, title: str) -> bool:
    """PART 8: title and thumbnail are two halves of one idea, not the same words."""
    def toks(s: str) -> set[str]:
        return {w for w in re.sub(r"[^a-z' ]+", " ", s.lower()).split() if len(w) > 3}
    qt, tt = toks(quote), toks(title)
    if not qt:
        return False
    return len(qt & tt) / len(qt) >= 0.6


def selftest() -> int:
    ok = True
    def chk(label, got, want):
        nonlocal ok
        good = got == want
        ok = ok and good
        print(f"  {'ok ' if good else '!! '} {label}: {got!r}" + ("" if good else f" (want {want!r})"))
    chk("dimensions sum", sum(DIMENSIONS.values()), 100)
    s = {d: {"score": m} for d, m in DIMENSIONS.items()}
    chk("perfect total", total_score(s), 100.0)
    s["story_engine"]["score"] = 99
    chk("clamped over-max", total_score(s), 100.0)
    chk("over_max reports", over_max(s), ["story_engine 99>20"])
    chk("tier 85", tier(85), "A"); chk("tier 78", tier(78), "MAKE")
    chk("tier 70", tier(70), "HOLD"); chk("tier 69.9", tier(69.9), "SKIP")
    chk("gate outranks score", decision(95, False), "SKIP")
    chk("repeat 88 vs 79", prefer_repeat(88, 79), False)
    chk("repeat 80 vs 79", prefer_repeat(80, 79), True)
    mk = lambda n, t, rep: {"n": n, "total_score": t, "rep": rep}
    order = lambda cs: [c["n"] for c in tiebreak_order(cs, lambda c: c["rep"])]
    chk("88 one-off beats 79 repeat", order([mk("rep79", 79, True), mk("one88", 88, False)]), ["one88", "rep79"])
    chk("83 repeat beats 85 one-off", order([mk("one85", 85, False), mk("rep83", 83, True)]), ["rep83", "one85"])
    chk("81 repeat loses to 85 one-off", order([mk("one85", 85, False), mk("rep81", 81, True)]), ["one85", "rep81"])
    chk("two repeats raw", order([mk("rep80", 80, True), mk("rep84", 84, True)]), ["rep84", "rep80"])
    chk("hype flagged", any("hype" in f for f in title_flags("Judge Boyd DESTROYS Him")), True)
    chk("clickbait flagged", any("clickbait" in f for f in title_flags("Judge Boyd Couldn't Believe THIS")), True)
    chk("docket flagged", any("docket" in f for f in title_flags("Defendant Appears Before Judge Boyd Regarding Motion to Revoke")), True)
    chk("clean title", title_flags("He Was Given Another Chance — Then Came Back to Judge Boyd"), [])
    chk("family reveal", title_family("Then Judge Boyd Finds Out What Happened"), "reveal")
    chk("family last chance", title_family("Judge Boyd Gave Him One Last Chance. He's Back."), "warning_last_chance")
    chk("filler quote", any("filler" in f for f in quote_flags("Yes, Your Honor")), True)
    chk("good quote", quote_flags("I didn't know"), [])
    chk("quote repeats title", quote_repeats_title("Can't believe his excuse", "Judge Boyd Can't Believe His Excuse"), True)
    chk("quote complements title", quote_repeats_title("I didn't know", "Judge Boyd Notices His Story Doesn't Add Up"), False)
    print("EDITORIAL_SELFTEST_OK" if ok else "EDITORIAL_SELFTEST_FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(selftest())
