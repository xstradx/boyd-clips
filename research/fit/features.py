"""Style-independent features.

Two caption styles exist in this corpus: 'rich' (punctuation + '>>' speaker
markers) and 'plain' (no punctuation, no markers). Style is uncorrelated with
views, so it is not a confound for the LABEL -- but any feature that reads
punctuation or '>>' is undefined on half the corpus. Everything here is
computed from lowercased, punctuation-stripped tokens plus word TIMINGS,
which both styles have.
"""
import re

PUNCT = re.compile(r"[^a-z0-9' ]+")
WS = re.compile(r"\s+")


def norm(text):
    t = text.lower().replace(">>", " ")
    t = t.replace("’", "'")
    t = PUNCT.sub(" ", t)
    return WS.sub(" ", t).strip()


def toks(text):
    return norm(text).split()


def gaps(words):
    """Inter-word time gaps, in seconds."""
    return [words[i + 1][0] - words[i][0] for i in range(len(words) - 1)]


def runs_between_pauses(words, thr=0.6):
    """Word-counts of uninterrupted stretches, split at pauses > thr."""
    out, cur = [], 0
    for i in range(len(words) - 1):
        cur += 1
        if words[i + 1][0] - words[i][0] > thr:
            out.append(cur)
            cur = 0
    if cur:
        out.append(cur)
    return out


def structural(d):
    w = d["words"]
    n = max(len(w), 1)
    g = gaps(w)
    per1k = 1000.0 / n
    r = runs_between_pauses(w, 0.6)
    r_sorted = sorted(r)
    f = {}
    f["pause_rate_05"] = sum(1 for x in g if x > 0.5) * per1k
    f["pause_rate_10"] = sum(1 for x in g if x > 1.0) * per1k
    f["pause_rate_20"] = sum(1 for x in g if x > 2.0) * per1k
    f["mean_run"] = (sum(r) / len(r)) if r else 0.0
    f["p90_run"] = r_sorted[int(len(r_sorted) * 0.9)] if r_sorted else 0.0
    f["long_run_frac"] = sum(x for x in r if x >= 40) / float(n)
    f["wpm"] = n / (d["dur"] / 60.0) if d.get("dur") else 0.0
    t = toks(d["text"])
    f["ttr"] = len(set(t)) / float(max(len(t), 1))
    return f


# Lexical families, expressed WITHOUT punctuation so both caption styles match.
QUESTION = re.compile(
    r"\b(do you|did you|are you|is that|was that|what do|what did|what is|"
    r"why do|why did|why would|how many|how much|how long|who told|"
    r"can you|could you|would you|have you|has he|did he|did she|"
    r"you understand|right)\b")

FAMILIES = {
    "question": QUESTION,
    "second_person": re.compile(r"\b(you|your|you're|yours|yourself)\b"),
    "first_person": re.compile(r"\b(i|me|my|i'm|i've|i'll)\b"),
    "negation": re.compile(r"\b(not|no|don't|didn't|can't|won't|isn't|"
                           r"wasn't|nothing|never|ain't)\b"),
    "money_time": re.compile(r"\b(\d+|dollars|days|months|years|thousand)\b"),
    "custody": re.compile(r"\b(custody|handcuff|handcuffs|cuffs|jail|bond|"
                          r"bailiff|deputy|remand|arrest|arrested)\b"),
    "politeness": re.compile(r"\b(your honor|ma'am|sir|yes ma'am|no ma'am|"
                             r"respectfully|please)\b"),
    "hedge": re.compile(r"\b(i think|i guess|maybe|probably|kind of|sort of)\b"),
}


def lexical(d):
    t = norm(d["text"])
    n = max(len(t.split()), 1)
    return {k: len(p.findall(t)) * 1000.0 / n for k, p in FAMILIES.items()}


def all_feats(d):
    f = {}
    f.update(structural(d))
    f.update(lexical(d))
    return f
