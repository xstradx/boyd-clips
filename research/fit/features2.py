"""Artifact-controlled features.

Fixes over features.py:
  * duration = SPEECH SPAN (last word - first word), not the nominal chapter
    span. The #1 case is always the last chapter of a countdown, so its
    nominal slice runs to end-of-video and swallows the outro; nominal wpm
    therefore measures outro length, not delivery.
  * inter-word gaps capped at 10s so caption dropouts / music beds do not
    register as 'pauses'.
  * the question grab-bag is split -- 'right' alone is a discourse tic and
    was doing the work of the whole family.
"""
import re
from features import norm, toks, PUNCT, WS

MAXGAP = 10.0


def span(words):
    return max(words[-1][0] - words[0][0], 1.0) if len(words) > 1 else 1.0


def gaps(words):
    g = [words[i + 1][0] - words[i][0] for i in range(len(words) - 1)]
    return [x for x in g if x <= MAXGAP]


def runs(words, thr=0.6):
    out, cur = [], 0
    for i in range(len(words) - 1):
        cur += 1
        d = words[i + 1][0] - words[i][0]
        if thr < d <= MAXGAP:
            out.append(cur)
            cur = 0
    if cur:
        out.append(cur)
    return out


FAM = {
    "q_polar": re.compile(r"\b(do you|did you|are you|were you|is that|was that|"
                          r"can you|could you|would you|have you|you understand)\b"),
    "q_wh": re.compile(r"\b(what do|what did|what is|what's|why do|why did|"
                       r"why would|how many|how much|how long|who told|where were)\b"),
    "tag_right": re.compile(r"\b(right)\b"),
    "second_person": re.compile(r"\b(you|your|you're|yours|yourself)\b"),
    "first_person": re.compile(r"\b(i|me|my|i'm|i've|i'll)\b"),
    "third_person": re.compile(r"\b(he|she|him|her|his|hers|they|them)\b"),
    "negation": re.compile(r"\b(not|no|don't|didn't|can't|won't|isn't|"
                           r"wasn't|nothing|never|ain't)\b"),
    "custody": re.compile(r"\b(custody|handcuff|handcuffs|cuffs|jail|bond|"
                          r"bailiff|deputy|remand|arrest|arrested|prison)\b"),
    "politeness": re.compile(r"\b(your honor|ma'am|sir|respectfully|please)\b"),
    "hedge": re.compile(r"\b(i think|i guess|maybe|probably|kind of|sort of)\b"),
    "modal_order": re.compile(r"\b(going to|gonna|will|i'm going|you will|"
                              r"you need to|you have to|i want you)\b"),
    "counsel": re.compile(r"\b(attorney|counsel|lawyer|mr|ms|mister)\b"),
    "money_time": re.compile(r"\b(\d+|dollars|days|months|years)\b"),
}


def build(seg):
    w = seg["words"]
    n = max(len(w), 1)
    sp = span(w)
    g = gaps(w)
    r = sorted(runs(w, 0.6))
    per1k = 1000.0 / n
    f = {}
    f["pause_rate_05"] = sum(1 for x in g if x > 0.5) * per1k
    f["pause_rate_10"] = sum(1 for x in g if x > 1.0) * per1k
    f["pause_rate_20"] = sum(1 for x in g if x > 2.0) * per1k
    f["mean_gap"] = sum(g) / max(len(g), 1)
    f["mean_run"] = sum(r) / len(r) if r else 0.0
    f["p90_run"] = r[int(len(r) * 0.9)] if r else 0.0
    f["long_run_frac"] = sum(x for x in r if x >= 40) / float(n)
    f["wpm_speech"] = n / (sp / 60.0)
    t = toks(seg["text"])
    f["ttr"] = len(set(t)) / float(max(len(t), 1))
    nt = " ".join(t)
    nw = max(len(t), 1)
    for k, p in FAM.items():
        f[k] = len(p.findall(nt)) * 1000.0 / nw
    return f
