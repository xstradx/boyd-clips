# -*- coding: utf-8 -*-
"""One place that cuts a docket stream into hearings and MEASURES each one.

`scripts/find_called_hearings.py`, `scripts/rank_hearings.py` and
`tools/check_picker.py` all import this; none of them carries its own regex.

WHY THIS FILE EXISTS (measured 2026-09-01)
Nathan: "Like how it finds a certified banger judge boyd clip? Also I just
realized you could look at my previous manual clipped shorts of judge boyd and
see what my viewers liked and compare". Measured against his own winners
(`data/catalog_vs_picker.json`), the finder that existed could not see them:

  * 69.2% of the archive's transcripts carry no punctuation, and the finder
    split on `[.?!]` then required 3 sentences with a deference marker
    ("your honor" / "yes ma'am"). Unpunctuated hearings are one sentence.
  * "yes ma'am" is transcribed "yes M" / "no ma'" by the auto captions
    (IZZY93: 36x "yes", 3x "ma'am"), so the marker itself under-counts 10x.
  * `TRIAL` excluded anything containing the witness OATH ("raise your right
    hand" / "solemnly swear") - 437 of 443 hits are contested MTRs, which are
    the product, not jury trials.
  * The 1200 s cap loop walked to the cap and then the `MIN_S <= span <= MAX_S`
    gate rejected every hearing longer than the cap instead of truncating it.
  * MTR-only: STALKER (a plea / sentencing) is a winner and was never eligible.
  * The call phrase itself is mis-heard: "Port is calling" 191x, "report is
    calling" 175x, "cour is calling" 92x ... across 1702 streams; the regex
    only knew "court".
  * Pause-gap and sentence "turns" cannot attribute a speaker on auto
    captions (cue boundaries fake ~1.0 s gaps; G>=1.2 s merges Q and A) -
    measured on IZZY93/MONKEY/SANCHEZ, so NOTHING here claims to know who is
    speaking. The gates below are attribution-free.

WHAT IS MEASURED PER HEARING (all counts over the whole segment)
  q_per_min     judge-style questions aimed at "you" per minute (QYOU)
  narr_per_100  defendant-style first-person narrative per 100 words (NARR)
  mtr / sent    motion-to-revoke language / plea-or-sentencing language
  jury_open     a live-jury phrase inside the first MIN_S of the hearing
  punct_frac    words ending in . ? ! (says how readable the text is)
  defer, chall, bond, asks, nums, concrete, harsh_tail, soft_tail

Archive distribution (6039 called segments >= 360 s, `state/picker_probe.json`):
  q_per_min    p10 0.65  p30 1.35  p50 2.10  p70 2.85  p90 3.91
  narr_per_100 p10 0.12  p30 0.27  p50 0.41  p70 0.59  p90 0.91
His eleven winners: q/min 1.42 (CROSS) .. 4.73 (OFFERUP); narr 0.27 (STALKER)
.. 1.38 (IZZY93). The gates in config/picker.json sit under the lowest winner;
CROSS and STALKER clear them by 0.22 q/min and 0.02 narr/100 - thin, said so.

    python tools/hearing_measure.py <video_id>      # print every hearing in a stream
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

import yaml

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
PICKER_CFG = os.path.join(ROOT, "config", "picker.json")
PIPELINE_CFG = os.path.join(ROOT, "config", "pipeline.yaml")

# --- call boundary -----------------------------------------------------------
# What precedes "is calling" in 7688 hits over 1702 streams: court 6913,
# port 191, report 175, cour 92, record 33, p 29, support 12, cord 10, rep 10,
# fort 6, ourt 4, sport 3, por 3, coordinator 3. 137 further hits have none of
# these but a cause number follows ("what is calling 2024 CR ..."); the 70
# with neither are speech ("that person is calling the police").
CALL_WORDS = ("court", "port", "report", "cour", "ourt", "record", "cord", "rep",
              "support", "fort", "por", "sport", "coordinator", "p")
CALL = re.compile(r"\b(?:%s)\s+is\s+calling\b|\bis\s+calling\b(?=[^\n]{0,40}\d)|"
                  r"\bthe court calls\b|\bcalling the case\b" % "|".join(CALL_WORDS), re.I)

# --- hearing type --------------------------------------------------------------
MTR = re.compile(r"motion to revoke|revocation|violated condition|adjudicat\w+|"
                 r"your probation|revoke your", re.I)
SENT = re.compile(r"plea of guilty|plead guilty|pleading guilty|sentence you|punishment|"
                  r"years? (?:in|of) (?:prison|tdc|the penitentiary|state jail)|"
                  r"texas department of criminal justice|\btdcj?\b|deferred adjudication|"
                  r"plea agreement|plea bargain", re.I)
# Live-jury phrases only. "jurors" (334, scheduling), "jury trial" (3920,
# admonishments), the oath (1562 / 1094, contested MTRs) and "state calls"
# (66, witness calls inside MTRs) are NOT jury markers - measured 2026-09-01.
JURY = re.compile(r"jury panel|voir dire|members of the jury|ladies and gentlemen of the jury|"
                  r"bring (?:in |down |back )?the jury|presence of the jury", re.I)

# --- attribution-free proxies --------------------------------------------------
QYOU = re.compile(r"\b(why|what|how|who|where|when)\b[^.?!]{0,60}\byou\b|"
                  r"\bdo you (know|think|want|realize|expect|understand|have|remember)\b|"
                  r"\bare you (serious|kidding|telling me|working|going)\b|"
                  r"\b(did|do|were|have|had|can|could|will|would) you\b|\bwhat happened\b", re.I)
NARR = re.compile(r"\bi (was|had|went|got|did|didn'?t|couldn'?t|wasn'?t|have been|had been|been|"
                  r"am|'m|'ve|tried|told|thought|know|don'?t know|work|worked|lost|need)\b|"
                  r"\bmy (mom|mother|dad|father|kids?|son|daughter|wife|girlfriend|boyfriend|"
                  r"family|job|boss|house|apartment|car|phone|probation officer|po|baby|"
                  r"brother|sister|grandma)\b", re.I)
# "yes ma'am" arrives as "yes M" / "no ma'" - accept the ASR fragments.
DEFER = re.compile(r"\byour honou?r\b|\b(yes|no),?\s+(ma'?a?m?|m|sir)\b", re.I)
CHALL = re.compile(r"\b(why|what|how|who)\b[^.?!]{0,60}\byou\b|"
                   r"\bdo you (know|think|want|realize|expect)\b|"
                   r"\bare you (serious|kidding|telling me)\b", re.I)
BOND = re.compile(r"\bbond\b|\bsurety\b|\bmagistrat\w+\b", re.I)

# --- specifics (rank_hearings) -------------------------------------------------
ASK = re.compile(r"\bhow many\b|\bhow much\b|\bhow long\b|\bwhat time\b|"
                 r"\bwhere were you\b|\bwho (was|were)\b|\bwhen did you\b|"
                 r"\bwhat happened\b|\bwhat did you\b|\bwhy did you\b|"
                 r"\bwhere did you\b|\bwhat kind of\b", re.I)
NUM = re.compile(r"\b\d{1,4}\b|\bone\b|\btwo\b|\bthree\b|\bfour\b|\bfive\b|"
                 r"\bsix\b|\bseven\b|\beight\b|\bnine\b|\bten\b|\btwenty\b|\bthirty\b", re.I)
CONCRETE = re.compile(r"\bdollars?\b|\bmonths?\b|\bweeks?\b|\bdays?\b|\byears?\b|"
                      r"\bhours?\b|\bo'?clock\b|\bjob\b|\bwork(ing|ed)?\b|"
                      r"\brent\b|\bapartment\b|\bhouse\b|\bcar\b|\bschool\b|"
                      r"\bhospital\b|\bmoney\b|\bpaid\b|\bphone\b", re.I)
HARSH_END = re.compile(r"take (?:him|her|them) into custody|place the handcuffs|"
                       r"remand|sentence you to|penitentiary|revoke your probation|"
                       r"going to prison|state jail|adjudicate you guilty|"
                       r"find you guilty|i'?m revoking", re.I)
SOFT_END = re.compile(r"give you (?:a|another) chance|continue you on|reinstate|"
                      r"good luck to you|god bless|recall you|reset form|"
                      r"appear by zoom|proud of you", re.I)
PUNCT = re.compile(r"[.?!]$")

NARR_WINDOW = 8        # words either side of a NARR hit that count as "their" detail
TAIL_S = 75.0          # the closing stretch that decides the outcome
BACKOFF_S = 12.0       # stop this far before the next case is called


# --- config ---------------------------------------------------------------------
class DuplicateKey(ValueError):
    pass


class _NoDupes(yaml.SafeLoader):
    pass


def _mapping(loader, node):
    seen = set()
    for k_node, _ in node.value:
        k = loader.construct_object(k_node, deep=True)
        if k in seen:
            raise DuplicateKey(f"duplicate key {k!r} at line {k_node.start_mark.line + 1}")
        seen.add(k)
    return loader.construct_mapping(node, deep=True)


_NoDupes.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def load_yaml_no_dupes(path: str) -> dict:
    """PyYAML silently keeps the LAST duplicate key. config/pipeline.yaml carried
    `min_duration_s` twice (120 dead, 360 live) until 2026-09-01."""
    with open(path, encoding="utf-8") as f:
        return yaml.load(f, Loader=_NoDupes) or {}


def load_cfg(picker_path: str = PICKER_CFG, pipeline_path: str = PIPELINE_CFG) -> dict:
    cfg = json.load(open(picker_path, encoding="utf-8"))
    lf = load_yaml_no_dupes(pipeline_path)["output"]["longform"]
    cfg["min_s"] = float(lf["min_duration_s"])
    cfg["max_s"] = float(lf["max_duration_s"])
    return cfg


# --- transcript ------------------------------------------------------------------
def transcript_path(vid: str) -> str | None:
    p = glob.glob(os.path.join(ROOT, "work", vid, "*.transcript.json"))
    return p[0] if p else None


def load_words(path: str) -> tuple[list[str], list[float]]:
    d = json.load(open(path, encoding="utf-8"))
    ws = d.get("words") or []
    return [x.get("w", "") for x in ws], [float(x.get("t", 0.0)) for x in ws]


def call_indices(words: list[str]) -> list[int]:
    """Word index of every call phrase (character offset -> word index)."""
    txt = " ".join(words)
    starts, pos = [], 0
    for w in words:
        starts.append(pos)
        pos += len(w) + 1
    out = []
    for m in CALL.finditer(txt):
        lo, hi = 0, len(starts) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if starts[mid] < m.start():
                lo = mid + 1
            else:
                hi = mid
        if not out or out[-1] != lo:
            out.append(lo)
    return out


def _word_starts(words: list[str], a: int, b: int) -> list[int]:
    starts, pos = [], 0
    for w in words[a:b]:
        starts.append(pos)
        pos += len(w) + 1
    return starts


def _first_hit(rx, words, a, b) -> int | None:
    """Word index of the first regex hit inside words[a:b], else None."""
    seg = " ".join(words[a:b])
    m = rx.search(seg)
    if not m:
        return None
    starts = _word_starts(words, a, b)
    lo, hi = 0, len(starts) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if starts[mid] < m.start():
            lo = mid + 1
        else:
            hi = mid
    return a + lo


def cut(words: list[str], times: list[float], cfg: dict) -> list[dict]:
    """Every hearing in a stream: from one call to the next, ended early at a
    live-jury phrase. The WHOLE hearing is kept and measured - the ruling is
    at its end, and STALKER's narrative starts 200 s after its call; the old
    cut-at-1200-s lost both. `over_cap` says the editor must trim it
    (config/pipeline.yaml output.longform.max_duration_s - the builder trims
    on a piece boundary). Nothing is dropped here except hearings shorter
    than min_s, hearings that OPEN on a jury, and stretches with no call for
    `overlong_s` (a missed boundary, not one hearing) - the row says why
    (`excluded`), so a control can prove it."""
    min_s, max_s = cfg["min_s"], cfg["max_s"]
    overlong = float(cfg.get("overlong_s", 3600))
    marks = call_indices(words)
    out = []
    for a, b in zip(marks, marks[1:] + [len(words)]):
        t0 = times[a]
        row = {"a": a, "t": round(t0, 1), "jury_cut": False, "excluded": None}
        j = _first_hit(JURY, words, a, b)
        if j is not None and j < len(times):
            if times[j] - t0 < min_s:
                row.update(b=j, span_s=round(times[j] - t0, 1), over_cap=False,
                           excluded="jury_open")
                out.append(row)
                continue
            b, row["jury_cut"] = j, True
        span = times[min(b, len(times) - 1)] - t0
        row.update(b=b, span_s=round(span, 1), over_cap=span > max_s)
        if span < min_s:
            row["excluded"] = "short"
        elif span > overlong:
            row["excluded"] = "overlong"
        out.append(row)
    return out


# --- measurement -------------------------------------------------------------------
def measure(words: list[str], times: list[float], a: int, b: int) -> dict:
    seg_words = words[a:b]
    seg = " ".join(seg_words)
    n = max(1, len(seg_words))
    t0 = times[a]
    t1 = times[min(b, len(times) - 1)] if b > a else t0
    span = max(1.0, t1 - t0)
    tail_from = t1 - BACKOFF_S - TAIL_S
    tail = " ".join(w for w, t in zip(seg_words, times[a:b]) if t >= tail_from)

    q = len(QYOU.findall(seg))
    starts = _word_starts(words, a, b)
    narr_hits = []
    for mm in NARR.finditer(seg):
        lo, hi = 0, len(starts) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if starts[mid] < mm.start():
                lo = mid + 1
            else:
                hi = mid
        narr_hits.append(a + lo)
    narr = len(narr_hits)
    # "their" specifics without knowing who speaks: numbers and concrete nouns
    # within NARR_WINDOW words of a first-person narrative hit.
    near = set()
    for i in narr_hits:
        near.update(range(max(a, i - NARR_WINDOW), min(b, i + NARR_WINDOW + 1)))
    near_txt = " ".join(words[i] for i in sorted(near))
    m = {
        "words": n,
        "span_s": round(span, 1),
        "punct_frac": round(sum(1 for w in seg_words if PUNCT.search(w)) / n, 3),
        "q": q,
        "q_per_min": round(q / (span / 60.0), 2),
        "narr": narr,
        "narr_per_100": round(narr / (n / 100.0), 2),
        "defer": len(DEFER.findall(seg)),
        "chall": len(CHALL.findall(seg)),
        "bond": len(BOND.findall(seg)),
        "mtr": bool(MTR.search(seg)),
        "sent": bool(SENT.search(seg)),
        "outcome": len(HARSH_END.findall(seg)),
        "asks": len(ASK.findall(seg)),
        "their_nums": len(NUM.findall(near_txt)),
        "their_concrete": len(CONCRETE.findall(near_txt)),
        "ends_harsh": len(HARSH_END.findall(tail)),
        "ends_soft": len(SOFT_END.findall(tail)),
        "open": re.sub(r"\s+", " ", seg[:220]),
        "tail": re.sub(r"\s+", " ", tail)[-200:],
    }
    m["detail_rate"] = round((m["their_nums"] + m["their_concrete"]) / (max(1, len(near)) / 100.0), 1)
    return m


def gate(row: dict, m: dict, cfg: dict) -> list[str]:
    """Names of the gates this hearing FAILS. Empty = candidate."""
    fails = []
    if row.get("excluded"):
        fails.append(row["excluded"])
    if not (m["mtr"] or m["sent"]):
        fails.append("not_mtr_or_sent")
    if m["q_per_min"] < cfg["q_per_min_min"]:
        fails.append("q_per_min")
    if m["narr_per_100"] < cfg["narr_per_100_min"]:
        fails.append("narr_per_100")
    return fails


def find_score(m: dict, span: float) -> float:
    """Ordering only - the ranker and the LLM judges re-score. Attribution-free:
    her questions, their narrative, the outcome she reaches, minus bond talk."""
    sc = min(30.0, m["q_per_min"] * 7.5)
    sc += min(30.0, m["narr_per_100"] * 33.0)
    sc += min(12.0, m["defer"] * 0.8)
    sc += 8.0 if m["outcome"] else 0.0
    sc += 12.0 if 420 <= span <= 900 else 0.0
    sc -= min(20.0, m["bond"] * 4.0)
    return round(sc, 1)


def rank_score(m: dict, span: float) -> float:
    """Ordering for the LLM judges. Nathan 2026-08-21: "if judge Boyd and the
    defendant are actually talking about specifics you should look there".

    Rates only. The first version summed COUNTS (asks, numbers, nouns) and its
    top 200 was 152 over-cap hearings with a median length of 35 min and none
    of his eleven winners (measured 2026-09-01 on state/rank_probe.json).
    Measured on the same probe, the winners' median rank:
      counts (old)                       606 / 3395, 0 in the top 200
      asks/min + detail only             782,        2
      finder score alone                 735,        2
      all four rates, no ending          269,        7 in the top 500, worst 2772
      all four rates + ending (this)     396,        6 in the top 500, worst 1931
    No lexical score puts them at the top - the "banger" call is the judges'
    and his, NOT AUTOMATED. This only orders what they read first."""
    asks_pm = m["asks"] / (span / 60.0) if span else 0.0
    sc = min(30.0, m["q_per_min"] * 7.5)
    sc += min(30.0, m["narr_per_100"] * 33.0)
    sc += min(30.0, asks_pm * 6.0)
    sc += min(30.0, m["detail_rate"] * 3.0)
    sc += m["ends_harsh"] * 6.0 - m["ends_soft"] * 5.0
    return round(sc, 1)


def scan(vid: str, cfg: dict, path: str | None = None) -> list[dict]:
    """Every hearing in one stream with its measurement, gates and score."""
    path = path or transcript_path(vid)
    if not path:
        return []
    words, times = load_words(path)
    if not words:
        return []
    rows = []
    for row in cut(words, times, cfg):
        m = measure(words, times, row["a"], row["b"])
        fails = gate(row, m, cfg)
        rows.append({"video_id": vid, **row, **m, "fails": fails,
                     "score": find_score(m, row["span_s"])})
    return rows


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    cfg = load_cfg()
    for r in scan(argv[0], cfg):
        flag = "CANDIDATE" if not r["fails"] else ",".join(r["fails"])
        print(f"t={r['t']:8.1f} span={r['span_s']:6.0f} cap={'Y' if r['over_cap'] else '-'} "
              f"q/min={r['q_per_min']:4.2f} narr={r['narr_per_100']:4.2f} "
              f"mtr={int(r['mtr'])} sent={int(r['sent'])} punct={r['punct_frac']:.2f} "
              f"score={r['score']:5.1f}  {flag}")
        print(f"    {r['open'][:120]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
