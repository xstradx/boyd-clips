# -*- coding: utf-8 -*-
"""Choose WHICH seconds of a hearing become the short.

Nathan, 2026-08-31: *"You need to make the shorts more interesting because
barely anything in that clip and then you gave away the outcome"* and
*"make sure you learn from this to apply to any future shorts u make"*.

This is the gap the short engine explicitly did not cover - its own docstring
said "It does not choose the cuts". Everything else in this project got built
first: colour, grain, centring, cut placement, loudness. All craft, applied to
46 seconds that had no moment in them.

WHAT WAS WRONG WITH THE OFFERUP SHORT, measured against its transcript:

    10861  "so you go on OfferUp for a vehicle..."   THE SETUP - cut off
    10866  "the steering column - I did it"          THE EXCUSE - cut off
    10868  "because I lost the key fob"              cut off
    10871  "that makes no sense to me"               HER REBUTTAL - cut off
    10881  ................................          the clip STARTED here
    10900  "who are the names of the tattoos"        20s of filler INCLUDED
    10921  "this is what the court is going to do"   THE OUTCOME - INCLUDED
    10923  "three years"

So it opened after the drama, kept the admin, and gave away the ending. The
thumbnail said "WORST EXCUSE EVER" and the excuse was not in the video.

THE RULES, each from evidence
1. THE CLIP MUST CONTAIN WHAT THE THUMBNAIL PROMISES. If the kicker says
   "WORST EXCUSE EVER", the excuse is in the clip or the packaging lies.
2. NEVER INCLUDE THE OUTCOME. Grounded, from the niche study: "JUDGE GIVES HIM
   8 YEARS INSTEAD" = 8.7k views; "This cop was lying!" = 1.34M. Stating the
   sentence removes the reason to watch.
3. OPEN ON THE SETUP QUESTION, not mid-exchange. The judge's framing question is
   what makes the excuse land.
4. CUT ADMINISTRATIVE FILLER - names, ages, addresses, drug questions,
   scheduling, restitution dates. It is most of a hearing and none of the story.
5. END ON THE JUDGE'S JUDGEMENT OF THE STORY, before the sentence.
"""
import json
import os
import re
import sys

# Sentencing / outcome language. If any of this is in the window, the outcome
# has been given away.
OUTCOME = [
    "this is what the court is going to do", "i'm going to sentence",
    "i sentence you", "years to court", "years in the",
    "adjudicate you", "adjudicates you", "adjudicated guilty",
    "grant the state's motion", "allegations true", "allegation true",
    "allegations are true", "allegation is true",
    "i find you guilty", "probation is revoked", "remanded", "i'm revoking",
    "the court finds", "sentenced to", "days in jail", "months in",
]
# Not outcomes, even though they contain outcome words. "Deferred adjudication"
# is the KIND of probation she names in nearly every revocation hearing
# (TORRES 4908.3: "I mean sorry a deferred adjudication for"), and "motion to
# adjudicate" is the motion being heard, read out at the call. Measured
# 2026-09-02: the bare term "adjudication" flagged the TORRES opening window
# (4893.6-4926.55) as OUTCOME GIVEN AWAY when the sentence is 3 minutes later.
NOT_OUTCOME = ["deferred adjudication", "motion to adjudicate",
               "motion to proceed to adjudication", "adjudication of guilt"]
# Administrative filler - real hearing content, no story in it.
FILLER = [
    "names of all the tattoos", "how old are", "what are their ages",
    "do you have any drug issues", "are they living with you",
    "restitution hearing date", "community service", "reporting by zoom",
    "field visits", "parenting classes", "life skills", "anti-theft course",
    "date of birth", "your address", "phone number",
]


def words_between(words, lo, hi):
    return [w for w in words if lo <= float(w.get("t", w.get("s", 0))) <= hi]


def text_of(ws):
    return " ".join(str(w["w"]) for w in ws)


def audit(words, lo, hi):
    """What is wrong with a proposed window. Returns a list of problems."""
    ws = words_between(words, lo, hi)
    t = text_of(ws).lower()
    for p in NOT_OUTCOME:
        t = t.replace(p, " ")
    bad = []
    for p in OUTCOME:
        if p in t:
            bad.append(("OUTCOME GIVEN AWAY", p))
    hits = [p for p in FILLER if p in t]
    if hits:
        bad.append(("ADMIN FILLER", ", ".join(hits[:3])))
    if len(ws) < 40:
        bad.append(("TOO LITTLE SAID", f"{len(ws)} words"))
    return bad, len(ws), t


def selftest():
    """Known answer: the window that SHIPPED must fail, the corrected one pass."""
    ok = True
    tp = "work/l19Ijva3Rsk/l19Ijva3Rsk.transcript.json"
    if not os.path.exists(tp):
        print("  SELFTEST_SKIP transcript missing")
        return 0
    words = json.load(open(tp))["words"]
    shipped, _, _ = audit(words, 10881.5, 10937.0)
    fixed, n, _ = audit(words, 10859.0, 10899.5)
    print(f"  SHIPPED window 10881.5-10937.0: {len(shipped)} problems")
    for k, v in shipped:
        print(f"    {k}: {v}")
    print(f"  FIXED   window 10859.0-10899.5: {len(fixed)} problems, {n} words")
    for k, v in fixed:
        print(f"    {k}: {v}")
    if not shipped:
        print("  FAIL the shipped window should have been rejected"); ok = False
    if fixed:
        print("  FAIL the corrected window still has problems"); ok = False

    # Controls for the "adjudication" false positive (2026-09-02).
    def syn(text):
        return [{"t": float(i), "w": w} for i, w in enumerate(text.split())]
    pad = "so why are you not reporting that is the easiest thing to do " * 5
    deferred, _, _ = audit(syn(pad + "you are on a deferred adjudication for possession " + pad), 0, 1e9)
    motion, _, _ = audit(syn(pad + "this is the state's motion to adjudicate guilt " + pad), 0, 1e9)
    real, _, _ = audit(syn(pad + "i adjudicate you guilty of the offense " + pad), 0, 1e9)
    granted, _, _ = audit(syn(pad + "i find the allegations true and grant the state's motion " + pad), 0, 1e9)
    print(f"  CONTROL 'deferred adjudication' -> {deferred}")
    print(f"  CONTROL 'motion to adjudicate'  -> {motion}")
    print(f"  CONTROL 'i adjudicate you guilty' -> {real}")
    print(f"  CONTROL 'grant the state's motion' -> {granted}")
    if deferred or motion:
        print("  FAIL probation type / motion name flagged as an outcome"); ok = False
    if not real or not granted:
        print("  FAIL a real adjudication line was not caught"); ok = False
    tt = "work/GUOzwzGiPYU/GUOzwzGiPYU.transcript.json"
    if os.path.exists(tt):
        tw = json.load(open(tt, encoding="utf-8"))["words"]
        t_open, n_open, _ = audit(tw, 4893.6, 4926.55)
        t_end, _, _ = audit(tw, 5088.0, 5130.0)
        print(f"  TORRES opening 4893.6-4926.55: {len(t_open)} problems, {n_open} words")
        for k, v in t_open:
            print(f"    {k}: {v}")
        print(f"  TORRES ruling  5088.0-5130.0: {len(t_end)} problems")
        if t_open:
            print("  FAIL the TORRES opening (has 'deferred adjudication') was rejected"); ok = False
        if not t_end:
            print("  FAIL the TORRES ruling was not rejected"); ok = False
    print("SELFTEST_PASS pick_window" if ok else "SELFTEST_FAIL pick_window")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    if len(sys.argv) < 4:
        print("usage: pick_window.py transcript.json LO HI | --selftest")
        sys.exit(2)
    words = json.load(open(sys.argv[1]))["words"]
    bad, n, t = audit(words, float(sys.argv[2]), float(sys.argv[3]))
    print(f"  {n} words in window")
    for k, v in bad:
        print(f"  {k}: {v}")
    print("  WINDOW OK" if not bad else f"  {len(bad)} PROBLEM(S)")
    sys.exit(0 if not bad else 1)
