# -*- coding: utf-8 -*-
"""Title check — accuracy refusals + BOYD_EDITORIAL_V2 editorial validation.

TWO THINGS REFUSE (accuracy, never taste):
    uncensored profanity          - his standing channel rule, audio yes text no
    a quoted span that is not verbatim in the transcript (R16) - inventing a
        quote from a real person in a real courtroom is a factual error

EVERYTHING ELSE IS ADVICE, printed as `flag`. The editorial rules are the
single definition in src/boydclips/editorial.py (Nathan, 2026-09-06):
    one story only · promise a real payoff · specific curiosity, not generic
    clickbait · "Judge Boyd" when her action is the hook, not mechanically ·
    plain spoken English, no docket language · hard max 70 (analyze._trim_title
    enforces it), editorial target 45-65 · no empty hype words, no emoji, no
    fake all-caps urgency · candidates from several title FAMILIES.

HISTORY (kept so nobody re-derives it): the 2026-09-03 rewrite deleted the
"withhold the outcome" refusal after it was measured refusing seven of the nine
best-performing Judge Boyd titles in existence. The measured winning signals
from that corpus (reaction verb, outcome stated, concrete stake) are still
reported below as `measured`, because they are real data about this niche —
but they no longer drive a score. The 2026-09-06 ruleset asks for the EVENT to
carry the title; a reaction verb is welcome when it is true, not required.

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
from boydclips import editorial  # noqa: E402

HARD_MAX = editorial.TITLE_HARD_MAX
TARGET = editorial.TITLE_TARGET

# ---- measured niche signals (reported, not scored) --------------------------
REACTION_VERBS = [
    "snaps", "loses it", "rages", "erupts", "hammers", "slams", "shows no mercy",
    "humiliates", "denies", "rejects", "stuns", "shuts down", "checks", "turns on",
    "cant believe", "can't believe", "couldn't believe", "couldnt believe",
    "backfired", "pushed too far", "pushes", "warns", "in disbelief", "begs",
    "caught", "exposes", "shocked", "had enough", "notices", "learns", "finds out",
]
OUTCOME_WORDS = [
    "sentence", "sentences", "sentenced", "prison", "years", "life", "probation",
    "denied", "granted", "guilty", "verdict", "maximum", "no mercy", "decades",
    "revoked", "another chance", "last chance",
]
STAKE_WORDS = [
    "child", "daughter", "son", "baby", "infant", "toddler", "kid", "mother",
    "father", "murder", "killed", "stabbed", "shot", "gun", "stolen", "drugs",
    "meth", "fentanyl", "predator", "molest", "rape", "rap*d", "se*", "assault",
    "starved", "abuse", "dui", "drunk", "elderly", "dog", "animal", "gang",
    "robbery", "burglary", "parole", "stalker", "trafficking", "capital",
]

_QUOTE = re.compile(r"[\"\u201c\u201d]([^\"\u201c\u201d]{3,})[\"\u201c\u201d]|(?<![A-Za-z])'([^']{3,})'(?![A-Za-z])")
_TS = re.compile(r"^\d+$|^\d\d:\d\d:\d\d[,.]\d+ -->|^WEBVTT|^NOTE\b")


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


def measured(title):
    """Which of the measured niche signals the title carries. Reported only."""
    low = title.lower()
    hits = []
    if any(v in low for v in REACTION_VERBS):
        hits.append("reaction verb")
    if any(w in low for w in OUTCOME_WORDS):
        hits.append("names the outcome or stake of the decision")
    if any(w in low for w in STAKE_WORDS):
        hits.append("names a concrete stake")
    return hits


def score(title):
    """Kept for callers that import it. Advisory: measured signals as points."""
    hits = measured(title)
    pts = 30 * ("reaction verb" in hits) + 30 * (any(h.startswith("names the outcome") for h in hits)) \
        + 25 * ("names a concrete stake" in hits)
    return pts, hits


def check(title, transcript=None, verbose=True):
    """Returns (ok, fails, flags). Only accuracy can make ok False."""
    fails, flags = [], []
    n = len(title)

    # --- the only two refusals, both accuracy ---------------------------------
    if has_profanity(title):
        fails.append(f"uncensored profanity - text is always censored: '{censor(title)}'")
    for span in quoted_spans(title):
        if transcript is None:
            flags.append(f"quoted span '{span}' unverified - pass --transcript to check it (R16)")
        elif _norm(span) not in transcript:
            fails.append(f"quoted span '{span}' is not verbatim in the transcript (R16)")

    # --- editorial validation (advisory) ---------------------------------------
    flags.extend(editorial.title_flags(title))
    fam = editorial.title_family(title)
    hits = measured(title)

    ok = not fails
    if verbose:
        print(("TITLE_OK    " if ok else "TITLE_FAIL  ") + f"[{n}] {title}")
        for f in fails:
            print("    REFUSED  " + f)
        for w in flags:
            print("    flag     " + w)
        print("    family   " + (fam or "none recognised - is the story angle in the title?"))
        if hits:
            print("    measured " + ", ".join(hits))
    return ok, fails, flags


# ---- known-answer sets -------------------------------------------------------
# His channel and the 100k+ Judge Boyd corpus (measured 2026-09-03). Nothing in
# this list may ever be REFUSED - only accuracy refuses, and these are accurate.
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
# BOYD_EDITORIAL_V2 example titles: must carry NO editorial flags except length.
CLEAN = [
    "Judge Boyd Learns Why He Really Came Back to Court",
    "He Was Given Another Chance — Then Did It Again",
    "Judge Boyd Notices His Story Doesn't Add Up",
    "He Keeps Arguing With Judge Boyd — It Doesn't Help",
    "His Explanation Leaves Judge Boyd With One Question",
    "Judge Boyd Gave Him One Last Chance. He's Back.",
    "Then He Admits Why He Violated Probation",
    "The Hearing Changes When His Family Speaks",
]
# Must be FLAGGED (generic clickbait / hype / docket language) but never refused.
WEAK = [
    ("Judge Boyd Couldn't Believe THIS", "clickbait"),
    ("You Won't Believe What Happens", "clickbait"),
    ("This Changes EVERYTHING", "clickbait"),
    ("Judge Boyd DESTROYS Him In SAVAGE Takedown", "hype"),
    ("Defendant Appears Before Judge Boyd Regarding Motion to Revoke Probation", "docket"),
]


def selftest():
    ok = True
    print("check_title - BOYD_EDITORIAL_V2")
    print("  WINNERS (never refused):")
    for t, v in WINNERS:
        good, fails, _ = check(t, verbose=False)
        if not good:
            ok = False
        print(f"    {v:>8,}  {'ok ' if good else '!! REFUSED: ' + '; '.join(fails)} {t[:62]}")
    print("  CLEAN v2 examples (no editorial flag beyond length):")
    for t in CLEAN:
        good, fails, flags = check(t, verbose=False)
        bad = [f for f in flags if "chars" not in f]
        if not good or bad:
            ok = False
        print(f"    {'ok ' if good and not bad else '!! '} {t}  {bad if bad else ''}")
    print("  WEAK examples (flagged, not refused):")
    for t, why in WEAK:
        good, fails, flags = check(t, verbose=False)
        hit = any(why in f for f in flags)
        if not good or not hit:
            ok = False
        print(f"    {'ok ' if good and hit else '!! '} {why:9s} {t}")
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
    # families
    fams = {editorial.title_family(t) for t in CLEAN}
    if len(fams - {None}) < editorial.TITLE_MIN_FAMILIES:
        ok = False
        print(f"    !! only {len(fams - {None})} families recognised among the clean examples")
    else:
        print(f"    ok   {len(fams - {None})} title families recognised: {sorted(f for f in fams if f)}")
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
