# -*- coding: utf-8 -*-
"""R41 (REWRITTEN 2026-09-03) - titles follow the formula that actually wins
this niche. R16 - a quoted span is verbatim.

WHY THIS FILE WAS REWRITTEN. The old R41 said "withhold the outcome, never
state the sentence" and this checker REFUSED any title that did. Measured
2026-09-03 against the real corpus - his own channel ranked by views, and every
Judge Boyd video on YouTube over 100k:

    865k  Day 1: The family found them in a locked car - Savanah Soto ...  REFUSED (80 chars)
     39k  Judge Boyd Sentences San Antonio Rapper "IZZY93" To PRISON!     REFUSED (sentences)
     27k  Thug In Disbelief After Judge Boyd Sentences Him To Prison.     REFUSED (sentences)
     22k  Judge Boyd Sentences Father Who STARVED his 10-Year Old ...     REFUSED (10-year)
    747k  Judge Boyd Sentences 22-Year-Old in Predator Sting              REFUSED (22-year)
    281k  Judge Boyd Sentences Honors Student to 6 YEARS PRISON           REFUSED (6 years)

Seven of the nine best-performing Judge Boyd titles in existence were refused by
this file. Meanwhile the five WORST shorts on his channel (977 - 2,000 views)
are the quote-led, outcome-withheld ones this file was built to produce, four of
them written by me.

Nathan, 2026-09-03: *"if there's something in the instructions that you know is
wrong and ESPECIALLY if I spend DAYS telling you it's wrong then maybe it would
be smart to undo whatever's causing and delete it"*. He then chose "copy the
rival formula". So the outcome refusal is DELETED, not relaxed.

THE FORMULA, read off the 100k+ corpus (see WINNERS below):
    [who + what they did, in blunt words] + Judge Boyd + [reaction verb] + [outcome]
    - state the outcome; it is the payoff, not a spoiler
    - CAPS the payoff word (PRISON, STARVED, LIFE, MONSTER)
    - a reaction verb for the judge: SNAPS / LOSES IT / RAGES / ERUPTS /
      HAMMERS / SLAMS / SHOWS NO MERCY / HUMILIATES / DENIES / REJECTS
    - name the crime concretely; asterisk the sensitive word (Se* / Rap*d /
      MOLEST*D) - that is what the winning channels do and it matches his
      standing censor rule
    - up to ~85 characters; his 865k best is 80

WHAT STILL REFUSES (only two things, both accuracy, not taste)
    uncensored profanity          - his standing channel rule, audio yes text no
    a quoted span that is not verbatim in the transcript (R16) - inventing a
        quote from a real person in a real courtroom is a factual error
Everything else is a SCORE and a WARNING. This file no longer blocks a title.

    python tools/check_title.py "<title>" ["<title B>" ...] [--transcript <file>]
    python tools/check_title.py --selftest
"""
import json
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
from boydclips.censor import censor, has_profanity  # noqa: E402

# 80 chars is his own 865k best; 85 leaves a little room. This is a WARN now.
SOFT_MAX = 85
BAND = (45, 80)

# ---- the winning formula, as positive signals (measured, not invented) ------
# Every verb below appears in a Judge Boyd video over 100k views, 2026-09-03.
REACTION_VERBS = [
    "snaps", "loses it", "rages", "erupts", "hammers", "slams", "shows no mercy",
    "humiliates", "denies", "rejects", "stuns", "shuts down", "checks", "turns on",
    "cant believe", "can't believe", "couldn't believe", "couldnt believe",
    "instantly regrets", "backfired", "pushed too far", "pushes", "warns",
    "in disbelief", "begs", "caught", "exposes", "shocked", "had enough",
]
# Outcome words - now a POSITIVE signal. This list used to be the refusal list.
OUTCOME_WORDS = [
    "sentence", "sentences", "sentenced", "prison", "years", "life", "probation",
    "denied", "granted", "guilty", "verdict", "maximum", "no mercy", "decades",
]
# Concrete stakes. Vague nouns ("case", "hearing", "court") do not count.
STAKE_WORDS = [
    "child", "daughter", "son", "baby", "infant", "toddler", "kid", "mother",
    "father", "murder", "killed", "stabbed", "shot", "gun", "stolen", "drugs",
    "meth", "fentanyl", "predator", "molest", "rape", "rap*d", "se*", "assault",
    "starved", "abuse", "dui", "drunk", "elderly", "dog", "animal", "gang",
    "robbery", "burglary", "parole", "stalker", "trafficking", "capital",
]

_QUOTE = re.compile(r"[\"\u201c\u201d]([^\"\u201c\u201d]{3,})[\"\u201c\u201d]|(?<![A-Za-z])'([^']{3,})'(?![A-Za-z])")
_TS = re.compile(r"^\d+$|^\d\d:\d\d:\d\d[,.]\d+ -->|^WEBVTT|^NOTE\b")
_CAPSWORD = re.compile(r"\b[A-Z]{3,}\b")


def _norm(s):
    """Censored, lower, letters/digits/* only - NO spaces or apostrophes."""
    s = s.replace("\u2019", "'").replace("\u2018", "'").replace(">>", " ")
    s = censor(s).lower()
    return re.sub(r"[^a-z0-9*]", "", s)


def load_transcript(path):
    if not path:
        return None
    raw = open(path, encoding="utf-8", errors="replace").read()
    if path.lower().endswith(".json"):
        d = json.loads(raw)
        if isinstance(d, dict):
            d = d.get("words", d)
        if isinstance(d, list):
            parts = []
            for w in d:
                if isinstance(w, dict):
                    parts.append(w.get("w") or w.get("word") or w.get("text") or "")
                else:
                    parts.append(str(w))
            return _norm(" ".join(parts))
        return _norm(raw)
    lines = [ln for ln in raw.splitlines() if not _TS.match(ln.strip())]
    return _norm(" ".join(lines))


def quoted_spans(title):
    return [a or b for a, b in _QUOTE.findall(title)]


def score(title):
    """0-100 against the measured winning formula. Advisory."""
    low = title.lower()
    pts, hits = 0, []
    if any(v in low for v in REACTION_VERBS):
        pts += 30; hits.append("reaction verb")
    if any(w in low for w in OUTCOME_WORDS):
        pts += 30; hits.append("states the outcome")
    if any(w in low for w in STAKE_WORDS):
        pts += 25; hits.append("names a concrete stake")
    if _CAPSWORD.search(title):
        pts += 15; hits.append("CAPS payoff word")
    return pts, hits


def check(title, transcript=None, verbose=True):
    """Returns (ok, fails, warns). Only accuracy can make ok False now."""
    fails, warns = [], []
    n = len(title)

    # --- the only two refusals left, both accuracy ---------------------------
    if has_profanity(title):
        fails.append(f"uncensored profanity - text is always censored: '{censor(title)}'")
    for span in quoted_spans(title):
        if transcript is None:
            warns.append(f"quoted span '{span}' unverified - pass --transcript to check it (R16)")
        elif _norm(span) not in transcript:
            fails.append(f"quoted span '{span}' is not verbatim in the transcript (R16)")

    # --- everything else is advice -------------------------------------------
    if n > SOFT_MAX:
        warns.append(f"{n} chars - over the soft max {SOFT_MAX} (his 865k best is 80)")
    elif not BAND[0] <= n <= BAND[1]:
        warns.append(f"{n} chars, house band {BAND[0]}-{BAND[1]}")
    if "judge" not in title.lower():
        warns.append("judge not named - every 100k+ Judge Boyd title names her")

    pts, hits = score(title)
    missing = []
    if "reaction verb" not in hits:
        missing.append("a reaction verb (SNAPS / LOSES IT / HAMMERS / DENIES / BEGS)")
    if "states the outcome" not in hits:
        missing.append("the OUTCOME - every 100k+ title states it; withholding it is what lost")
    if "names a concrete stake" not in hits:
        missing.append("a concrete stake (the crime, the victim, the thing taken)")
    if "CAPS payoff word" not in hits:
        missing.append("a CAPS payoff word")

    ok = not fails
    if verbose:
        print(("TITLE_OK    " if ok else "TITLE_FAIL  ") + f"[{n}] score {pts:>3}/100  {title}")
        for f in fails:
            print("    REFUSED  " + f)
        for w in warns:
            print("    warn     " + w)
        if hits:
            print("    has      " + ", ".join(hits))
        for m in missing:
            print("    missing  " + m)
    return ok, fails, warns


# ---- the known-answer set is now HIS CHANNEL, not my invention --------------
# (title, views) - measured 2026-09-03 with yt-dlp on @TexasTrialTracker and on
# every Judge Boyd video found over 100k views.
WINNERS = [
    ("Judge Boyd Sentences San Antonio Rapper \"IZZY93\" To PRISON!", 39000),
    ("Thug In Disbelief After Judge Boyd Sentences Him To Prison.", 27000),
    ("Judge Boyd Sentences Father Who STARVED his 10-Year Old Daughter", 22000),
    ("Stalker Ex Boyfriend BEGS Judge Boyd To Not Send Him To Prison", 16000),
    ("Judge Boyd Sentences 22-Year-Old in Predator Sting", 747486),
    ("Judge Boyd LOSES IT After Finding Out What This Cop Did", 504707),
    ("Judge Boyd Sentences Honors Student to 6 YEARS PRISON", 281247),
    ("Judge Boyd Hands Down 50-year Sentence To Savage Animal!", 117225),
    ("Murderer Begs For Last Chance - Judge Boyd Shows No Mercy", 110233),
]
LOSERS = [
    ("Judge Boyd tells her why her son is struggling #shorts", 2000),
    ("He told the judge it was funny #shorts", 1500),
    ("Judge Boyd To The Nurse On Probation: \"That's A No.\"", 1500),
    ("Judge Boyd Stops a Plea to Ask About a Spider Monkey #shorts", 1200),
    ("Judge Boyd Wanted Proof He Was Shot: \"Well, Let's Google.\"", 977),
]


def selftest():
    """The control set is his own channel. Winners must outscore losers, and
    NOTHING in the winning corpus may be refused."""
    ok = True
    print("R41 rewritten - the corpus is his own channel and the 100k+ Judge Boyd videos")
    ws, ls = [], []
    print("  WINNERS (must never be refused):")
    for t, v in WINNERS:
        good, fails, _ = check(t, verbose=False)
        p, _h = score(t)
        ws.append(p)
        flag = "" if good else "   !! REFUSED: " + "; ".join(fails)
        if not good:
            ok = False
        print(f"    {v:>8,}  score {p:>3}  {t[:62]}{flag}")
    print("  LOSERS (his five worst shorts - must score lower):")
    for t, v in LOSERS:
        p, _h = score(t)
        ls.append(p)
        print(f"    {v:>8,}  score {p:>3}  {t[:62]}")
    wmin, lmax = min(ws), max(ls)
    print(f"  winners min score {wmin}  vs  losers max score {lmax}")
    if wmin <= lmax:
        ok = False
        print("    !! the score does not separate his winners from his losers")
    # accuracy refusals must still bite
    for bad, why in [("Judge Boyd Tells Him \"You're Full of Shit\" to His Face", "profanity"),
                     ("Judge Boyd Said \"I Will Bury You Under The Jail\" Today", "fabricated quote")]:
        T = _norm("Judge Boyd: you keep this up and you are going to end up in prison or dead.")
        good, fails, _ = check(bad, T, verbose=False)
        if good:
            ok = False
            print(f"    !! {why} was NOT refused - the accuracy gate is dead")
        else:
            print(f"    ok   still refuses {why}")
    print("TITLE_SELFTEST_OK" if ok else "TITLE_SELFTEST_FAIL")
    return 0 if ok else 1


def main():
    args = [a for a in sys.argv[1:]]
    if "--selftest" in args:
        return selftest()
    tpath = None
    if "--transcript" in args:
        i = args.index("--transcript")
        tpath = args[i + 1]
        del args[i:i + 2]
    if not args:
        print(__doc__)
        return 2
    transcript = load_transcript(tpath)
    allok = True
    for t in args:
        good, _f, _w = check(t, transcript)
        allok = allok and good
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
