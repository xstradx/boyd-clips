#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""title_grammar.py - derive a niche's title formula from measured performance,
and say out loud which "rules" are actually noise.

WHY THIS EXISTS AND WHY IT IS NOT "COPY THE WINNER"
---------------------------------------------------
Nathan, 2026-09-03: *"just because theyre refeneces it always hurts us when you
anchor stuff so chikll with the anchoring were literally building youtube
channels from scratch creativity is neccisary"*.

Reading one big channel and copying its title style is anchoring, and in this
niche it is also the documented way to get refused from the Partner Programme -
the one recorded bodycam rejection was diagnosed *"You're not getting hit for
using public domain footage, you're getting hit for being a clone."*

So this file does the opposite thing. It pools MANY channels, throws away
everything about who wrote a title, and asks one question per FEATURE: does a
title that has this feature out-perform a title that does not, inside the same
channel? A feature is a mechanism ("names a dollar amount") rather than a style
("sounds like Code Blue Cam"). What comes out is a set of levers we can compose
freshly, not a house style to imitate.

THE CONFOUND THIS FILE EXISTS TO KILL. Raw view counts cannot be pooled across
channels: Dr Insanity's median video does 9.5M and Rogue Fugitive's does 22k,
so ANY feature that Dr Insanity happens to use would look like a winning
feature. Every title is therefore scored by its PERCENTILE RANK INSIDE ITS OWN
CHANNEL, which is unitless and comparable. Only then are channels pooled.

THE OTHER HALF, AND THE HARDER ONE: saying "noise". With ~1,800 titles and ~20
features, several will separate by chance. Each feature gets a permutation test
- the labels are shuffled many times to build the null distribution of the
observed effect - and anything that fails is printed as NOISE, not quietly
omitted. A feature list with no noise line in it is a list that has not been
tested.

    python tools/title_grammar.py --selftest
    python tools/title_grammar.py --report
    python tools/title_grammar.py --report --min-videos 40 --iters 20000
    python tools/title_grammar.py --score "Busted With $600,000 Of Fentanyl"
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import random
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NICHE = os.path.join(ROOT, "data", "bwc", "niche")

MIN_VIDEOS = 30          # a channel with fewer than this cannot give a stable percentile
ITERS = 10000            # permutation iterations
ALPHA = 0.01             # two-sided; deliberately strict because ~20 features are tested


# --------------------------------------------------------------- features
# Every feature is a MECHANISM, phrased so it could be satisfied a hundred
# different ways. None of them encode a particular channel's wording.
_MONEY = re.compile(r"\$\s?[\d,]+|\b\d[\d,]*\s?(?:k|million|billion)\b", re.I)
_NUMBER = re.compile(r"\b\d[\d,]*\b")
_SPEED = re.compile(r"\b\d+\s?(?:mph|km/h)\b", re.I)
_CAPS = re.compile(r"\b[A-Z]{3,}\b")
_ARCHETYPE = re.compile(
    r"\b(?:man|woman|teen|teens|mom|mother|dad|father|guy|kid|kids|driver|"
    r"cop|cops|officer|officers|deputy|trooper|suspect|couple|felon|"
    r"grandma|grandpa|boy|girl|kar[ae]n|kkkaren)\b", re.I)
_OUTCOME = re.compile(
    r"\b(?:arrest\w*|prison|jail|guilty|convict\w*|sentenc\w*|busted|caught|"
    r"charged|years|life|deported|fired|indicted)\b", re.I)
_WITHHELD = re.compile(
    r"\b(?:what happened|you won'?t believe|here'?s why|this is why|the reason|"
    r"until|before|goes wrong|takes a turn|then everything|didn'?t expect|"
    r"never expected|instantly regrets?)\b", re.I)
_CONNECTIVE = re.compile(r"\b(?:then|until|after|before|when|while|as soon as)\b", re.I)
_SUPERLATIVE = re.compile(
    r"\b(?:worst|best|biggest|largest|most|craziest|wildest|dumbest|deadliest|"
    r"scariest|fastest|greatest|insane|massive|unbelievable|perfect)\b", re.I)
_REACTION = re.compile(
    r"\b(?:snaps?|loses? it|rages?|erupts?|slams?|hammers?|humiliat\w*|"
    r"breaks? down|panics?|freaks? out|regrets?|begs?|cries|destroys?|ruins?|"
    r"backfires?|shocks?|stuns?|instantly)\b", re.I)
_SECOND_PERSON = re.compile(r"\b(?:you|your|you'?re)\b", re.I)
_QUOTE = re.compile(r"[\"“”'']{1}[^\"“”]{4,}[\"“”'']{1}")
_PLACE = re.compile(
    r"\b(?:alabama|alaska|arizona|arkansas|california|colorado|connecticut|"
    r"delaware|florida|georgia|hawaii|idaho|illinois|indiana|iowa|kansas|"
    r"kentucky|louisiana|maine|maryland|massachusetts|michigan|minnesota|"
    r"mississippi|missouri|montana|nebraska|nevada|ohio|oklahoma|oregon|"
    r"pennsylvania|tennessee|texas|utah|vermont|virginia|washington|wisconsin|"
    r"wyoming)\b", re.I)
_CENSORED = re.compile(r"[a-z]\*+[a-z]?|\b\w+\*\w*\b", re.I)
_SEGMENT = re.compile(r"[|:]")

# A proper name: a capitalised word that is not sentence-initial, not all-caps,
# and not a common title word. Crude but it only needs to separate "Man Gets
# Arrested" from "Arrest of Joel Arciniega-Saenz".
_TITLECASE_STOP = set("""a an the and or but of to in on for at by from with as is are was were be
been do does did his her their its this that these those he she it they them you your my our
after before then until when while during over under into out off up down not no so than if
gets get got makes made turns turned goes went comes came takes took leaves left runs ran
police officer cop cops deputy trooper sheriff bodycam body cam camera arrest arrested
man woman teen mom dad guy kid driver suspect video footage full part day new raw""".split())


# Corpus-derived vocabulary of ordinary words. Set by build_common(); until it
# is, _proper_name falls back to the hand-written stoplist.
_COMMON = None


def build_common(rows, min_df=0.004):
    """Words that appear in at least `min_df` of all titles are ORDINARY words,
    whatever their capitalisation.

    A hand-written stoplist cannot do this job and the selftest proved it:
    these titles are Title Case, so EVERY word is capitalised and "has a
    capital letter" carries no information at all. "Man Gets Arrested Then
    Makes It Worse" was read as naming a person because "Worse" happened not to
    be on my list - and no list I write by hand will ever be complete.

    Corpus frequency is the right instrument because it measures the actual
    distinguishing property: an ordinary word recurs across many titles, a
    person's name appears in one or two. It also adapts to the niche for free -
    "Bodycam" and "Trooper" become ordinary here without anyone deciding so.
    """
    from collections import Counter
    df = Counter()
    for _, t, _ in rows:
        for w in set(re.findall(r"\b[A-Za-z][a-z]{2,}\b", t)):
            df[w.lower()] += 1
    n = max(1, len(rows))
    return {w for w, c in df.items() if c / float(n) >= min_df}


def _proper_name(title, common=None):
    """A capitalised token that the corpus says is NOT an ordinary word."""
    vocab = common if common is not None else _COMMON
    for w in re.findall(r"\b[A-Z][a-z]{2,}(?:['’-][A-Za-z]+)*\b", title):
        lw = w.lower()
        if vocab is not None:
            if lw not in vocab:
                return True
        elif lw not in _TITLECASE_STOP:
            return True
    return False


FEATURES = [
    ("names a dollar amount",       lambda t: bool(_MONEY.search(t))),
    ("contains any number",         lambda t: bool(_NUMBER.search(t))),
    ("names a speed",               lambda t: bool(_SPEED.search(t))),
    ("has an ALL-CAPS word",        lambda t: bool(_CAPS.search(t))),
    ("archetype noun (Man/Mom/..)", lambda t: bool(_ARCHETYPE.search(t))),
    ("names a real person",         _proper_name),
    ("states the outcome",          lambda t: bool(_OUTCOME.search(t))),
    ("withholds the outcome",       lambda t: bool(_WITHHELD.search(t))),
    ("consequence connective",      lambda t: bool(_CONNECTIVE.search(t))),
    ("superlative",                 lambda t: bool(_SUPERLATIVE.search(t))),
    ("reaction verb",               lambda t: bool(_REACTION.search(t))),
    ("addresses the viewer (you)",  lambda t: bool(_SECOND_PERSON.search(t))),
    ("asks a question",             lambda t: "?" in t),
    ("quoted speech",               lambda t: bool(_QUOTE.search(t))),
    ("names a state",               lambda t: bool(_PLACE.search(t))),
    ("censored word (a*terisk)",    lambda t: bool(_CENSORED.search(t))),
    ("segmented with : or |",       lambda t: bool(_SEGMENT.search(t))),
    ("60+ characters",              lambda t: len(t) >= 60),
    ("10+ words",                   lambda t: len(t.split()) >= 10),
]


# --------------------------------------------------------------- corpus
def load_corpus(min_videos=MIN_VIDEOS, path=NICHE, age_bands=4):
    """-> [(channel, title, pct)] where pct is the title's view percentile
    inside its own channel AND its own age band.

    Two confounds, not one. The obvious one is channel size: Dr Insanity's
    median video does 9.5M and Rogue Fugitive's does 22k, so any feature Dr
    Insanity happens to favour would look like a winner. Percentile inside the
    channel removes that.

    The second is video AGE, and it is the one that quietly ruins this kind of
    analysis: lifetime view counts keep accruing, so a channel's older videos
    outrank its newer ones for reasons that have nothing to do with the title.
    Any style a channel has DRIFTED toward or away from over time would then be
    scored on when it was used rather than how well it worked. yt-dlp returns a
    channel newest-first, so position in that list is upload recency; each
    channel is cut into `age_bands` equal slices and the percentile is computed
    inside the slice. Titles are then only ever compared against titles of
    roughly the same vintage.
    """
    rows = []
    for f in sorted(glob.glob(os.path.join(path, "*.json"))):
        with open(f, encoding="utf-8") as fh:
            d = json.load(fh) or {}
        ch = d.get("channel") or os.path.basename(f)[:-5]
        vids = [e for e in (d.get("entries") or [])
                if e.get("title") and e.get("view_count")]
        if len(vids) < min_videos:
            continue
        # `vids` is newest-first as returned; index = recency rank.
        nb = max(1, min(age_bands, len(vids) // 10))
        size = len(vids) / float(nb)
        bands = {}
        for i, e in enumerate(vids):
            bands.setdefault(int(i / size), []).append(e)
        for band in bands.values():
            band.sort(key=lambda e: e["view_count"])
            n = len(band)
            for i, e in enumerate(band):
                rows.append((ch, e["title"], i / float(n - 1) if n > 1 else 0.5))
    return rows


# --------------------------------------------------------------- statistics
def effect(rows, fn):
    """Mean percentile WITH the feature minus mean percentile WITHOUT it."""
    a = [p for _, t, p in rows if fn(t)]
    b = [p for _, t, p in rows if not fn(t)]
    if not a or not b:
        return None, len(a), len(b)
    return sum(a) / len(a) - sum(b) / len(b), len(a), len(b)


def permutation_p(rows, fn, iters=ITERS, seed=7):
    """Two-sided permutation test. Shuffling the PERCENTILES against the titles
    builds the distribution of effects attributable to chance alone, which is
    the only honest way to say a feature is noise when ~20 are being tried."""
    obs, na, nb = effect(rows, fn)
    if obs is None:
        return None, obs
    pcts = [p for _, _, p in rows]
    flags = [fn(t) for _, t, _ in rows]
    rnd = random.Random(seed)
    hits = 0
    pool = list(pcts)
    for _ in range(iters):
        rnd.shuffle(pool)
        sa = sb = 0.0
        ca = cb = 0
        for f, p in zip(flags, pool):
            if f:
                sa += p
                ca += 1
            else:
                sb += p
                cb += 1
        if ca and cb and abs(sa / ca - sb / cb) >= abs(obs):
            hits += 1
    return (hits + 1) / float(iters + 1), obs


def analyse(rows, iters=ITERS, alpha=ALPHA):
    global _COMMON
    _COMMON = build_common(rows)
    out = []
    for name, fn in FEATURES:
        p, obs = permutation_p(rows, fn, iters=iters)
        if p is None:
            out.append({"name": name, "verdict": "NOT PRESENT", "effect": None,
                        "p": None, "n_with": 0})
            continue
        _, na, nb = effect(rows, fn)
        out.append({"name": name, "effect": obs, "p": p, "n_with": na,
                    "n_without": nb,
                    "verdict": ("HELPS" if obs > 0 else "HURTS") if p < alpha else "NOISE"})
    out.sort(key=lambda r: -(abs(r["effect"]) if r["effect"] is not None else -1))
    return out


# --------------------------------------------------------------- report
def report(min_videos=MIN_VIDEOS, iters=ITERS, path=NICHE):
    rows = load_corpus(min_videos, path)
    chans = sorted({c for c, _, _ in rows})
    if not rows:
        print("no corpus. Harvest channels into %s first." % path)
        return 2
    print("TITLE GRAMMAR - derived from measured performance, not from imitation")
    print("=" * 92)
    print("%d titles from %d channels: %s" % (len(rows), len(chans), ", ".join(chans)))
    print("Each title scored by its view percentile INSIDE ITS OWN CHANNEL, so a")
    print("5.8M-sub channel and a 51k-sub channel contribute on equal terms.")
    print("Permutation test, %d iterations, alpha %.2f." % (iters, ALPHA))
    print("-" * 92)
    print("%-30s %8s %9s %7s  %s" % ("FEATURE", "EFFECT", "p", "n_with", "VERDICT"))
    print("-" * 92)
    res = analyse(rows, iters=iters)
    for r in res:
        if r["effect"] is None:
            print("%-30s %8s %9s %7d  %s" % (r["name"], "-", "-", 0, r["verdict"]))
            continue
        print("%-30s %+7.1f%% %9.4f %7d  %s" %
              (r["name"], 100 * r["effect"], r["p"], r["n_with"], r["verdict"]))
    print("-" * 92)
    helps = [r for r in res if r["verdict"] == "HELPS"]
    hurts = [r for r in res if r["verdict"] == "HURTS"]
    noise = [r for r in res if r["verdict"] == "NOISE"]
    print("EFFECT is percentile points. +6%% means titles with the feature sit 6")
    print("points higher in their own channel's ranking than titles without it.")
    print()
    print("USE   : %s" % ("; ".join(r["name"] for r in helps) or "nothing separated"))
    print("AVOID : %s" % ("; ".join(r["name"] for r in hurts) or "nothing separated"))
    print("NOISE (do NOT treat these as rules - they did not separate): %s"
          % ("; ".join(r["name"] for r in noise) or "none"))
    return 0


def score_title(title, min_videos=MIN_VIDEOS, iters=2000, path=NICHE):
    rows = load_corpus(min_videos, path)
    res = {r["name"]: r for r in analyse(rows, iters=iters)}
    print("TITLE: %s" % title)
    print("-" * 78)
    tot = 0.0
    for name, fn in FEATURES:
        r = res.get(name) or {}
        if r.get("verdict") not in ("HELPS", "HURTS"):
            continue
        has = fn(title)
        if has:
            tot += r["effect"]
        print("  %-30s %-5s %+6.1f%% %s" %
              (name, "yes" if has else "no", 100 * r["effect"],
               ("<- applied" if has else "")))
    print("-" * 78)
    print("projected percentile shift vs a title with none of these: %+.1f points" % (100 * tot))
    print("(a projection from single-feature effects, NOT a prediction - features")
    print(" are not independent and no interaction terms were fitted)")
    return 0


# --------------------------------------------------------------- selftest
def selftest():
    fails = []

    def t(cond, what):
        if not cond:
            fails.append(what)
        print("  %-4s %s" % ("ok" if cond else "FAIL", what))

    print("features fire on the right strings")
    t(FEATURES[0][1]("Busted With Over $600,000 Of Fentanyl"), "dollar amount detected")
    t(not FEATURES[0][1]("Man Runs From Police"), "no dollar amount in a plain title")
    t(FEATURES[2][1]("Woman's 116 MPH Escape Plan"), "speed detected")
    t(FEATURES[3][1]("Judge Boyd Sentences Him To PRISON"), "ALL-CAPS word detected")
    t(not FEATURES[3][1]("Judge Boyd Sentences Him To Prison"), "title case is not ALL-CAPS")
    t(FEATURES[4][1]("Mom Crashes With 2 Kids"), "archetype noun detected")
    # _proper_name is corpus-relative by design, so it is tested that way: a
    # small vocabulary of words the "corpus" considers ordinary.
    vocab = {"man", "gets", "arrested", "then", "makes", "worse", "traffic",
             "stop", "turns", "cocaine", "interrogation", "police", "runs"}
    t(_proper_name("Interrogation of Joel Arciniega", vocab), "real person name detected")
    t(not _proper_name("Man Gets Arrested Then Makes It Worse", vocab),
      "KNOWN-BAD CONTROL: archetype title is NOT read as naming a person")
    t(not _proper_name("Traffic Stop Turns Up Cocaine", vocab),
      "KNOWN-BAD CONTROL: leading capital is not a name")
    built = build_common([("c", "Man Runs From Police", 0.5)] * 50 +
                         [("c", "Arrest of Joel Arciniega", 0.5)], min_df=0.05)
    t("man" in built and "arciniega" not in built,
      "build_common keeps recurring words and excludes a one-off surname")

    print("percentile normalisation kills the channel-size confound")
    corpus = [("big", "a", 0), ("big", "b", 0)]
    fake = {"channel": "X", "entries": [{"title": "t%d" % i, "view_count": v}
                                        for i, v in enumerate([10, 20, 30, 40, 50])]}
    import tempfile
    dtmp = tempfile.mkdtemp()
    with open(os.path.join(dtmp, "x.json"), "w", encoding="utf-8") as fh:
        json.dump(fake, fh)
    rows = load_corpus(min_videos=3, path=dtmp)
    pcts = sorted(p for _, _, p in rows)
    t(len(rows) == 5, "all videos loaded")
    t(all(0.0 <= p <= 1.0 for _, _, p in rows), "every percentile in range")
    t(abs(pcts[0] - 0.0) < 1e-9 and abs(pcts[-1] - 1.0) < 1e-9,
      "percentiles span 0..1 regardless of the raw view scale")

    print("the noise verdict actually fires")
    rnd = random.Random(1)
    # A feature attached to titles at RANDOM must come back NOISE. If this ever
    # says HELPS the test is not testing anything.
    noise_rows = [("c", ("ZZQ " if rnd.random() < 0.5 else "") + "title %d" % i,
                   rnd.random()) for i in range(400)]
    p, obs = permutation_p(noise_rows, lambda s: "ZZQ" in s, iters=2000)
    t(p is not None and p > ALPHA,
      "KNOWN-BAD CONTROL: a randomly-assigned feature is reported as NOISE (p=%.3f)" % (p or 0))
    # And a feature that genuinely separates must NOT be called noise.
    sig_rows = [("c", ("ZZQ " if i < 200 else "") + "t%d" % i,
                 (0.9 if i < 200 else 0.1)) for i in range(400)]
    p2, obs2 = permutation_p(sig_rows, lambda s: "ZZQ" in s, iters=2000)
    t(p2 is not None and p2 < ALPHA and obs2 > 0,
      "POSITIVE CONTROL: a real separation is detected (p=%.4f, effect %+.2f)" % (p2 or 1, obs2 or 0))

    print()
    if fails:
        print("SELFTEST FAILED: %d" % len(fails))
        for f in fails:
            print("   - %s" % f)
        return 1
    print("TITLE_GRAMMAR_SELFTEST_OK")
    return 0


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--score", metavar="TITLE")
    ap.add_argument("--min-videos", type=int, default=MIN_VIDEOS)
    ap.add_argument("--iters", type=int, default=ITERS)
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.score:
        return score_title(a.score, a.min_videos, min(a.iters, 4000))
    if a.report:
        return report(a.min_videos, a.iters)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
