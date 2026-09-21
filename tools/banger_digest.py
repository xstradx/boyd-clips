"""The manual path's editorial pass — same brain as the daily pipeline.

Two layers, and the second is the one that decides:

1. PROXY (no model call).  Lexical signals counted on a hearing's own speaker
   turns. Each signal is labelled with the BOYD_EDITORIAL_V2 dimension it
   approximates (src/boydclips/editorial.py PROXIES) so nobody mistakes a
   regex count for the rubric. It orders what the editorial pass reads first.
   Charge-severity words are deliberately demoted (PART 2: charge severity is
   a trap).

2. EDITORIAL (`--editorial`).  Runs the SAME prompt the daily pipeline uses
   (prompts/score_cases.md via Analyzer.score) on the hearing and prints the
   PART 6 rationale block: story angle, money moment, seven scores, total,
   gate, MAKE/HOLD/SKIP, weakness, title angles. This is the definition of a
   banger; there is no second one.

Ranking for `--rows`: editorial gate -> total -> story_engine -> payoff ->
packaging (editorial.MANUAL_RANK_ORDER) when `--editorial` has run; the proxy
score alone otherwise, printed as `proxy` so it is never read as a verdict.

Usage:
  python tools/banger_digest.py VIDEO_ID T SPAN_S               proxy digest, one hearing
  python tools/banger_digest.py VIDEO_ID T SPAN_S --editorial   + the editorial pass (one model call)
  python tools/banger_digest.py --rows FILE [--top N] [--editorial]
  python tools/banger_digest.py --selftest
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from boydclips import editorial  # noqa: E402
from boydclips.transcribe import Transcript  # noqa: E402

# Each signal: (name, regex). The weight comes from editorial.PROXIES so the
# manual path and the ruleset cannot drift apart.
_SIGNALS = [
    ("family",    re.compile(r"\b(my (mom|mother|dad|father|son|daughter|kids?|children|baby|wife|husband|girlfriend|grand\w+))\b|\b(mom|mother|daughter|baby|kids|children)\b", re.I)),
    ("confront",  re.compile(r"\b(look at (me|her|him)|say (it|that) to|face (her|him|them)|(she|he|they)('s| is) (here|in the courtroom|sitting)|victim)\b", re.I)),
    ("prison",    re.compile(r"\b(TDC|penitentiary|prison|(\d+|two|three|four|five|six|seven|eight|nine|ten|fifteen|twenty) years?|life sentence|revoke|revoked|remand|custody|take (him|her) into)\b", re.I)),
    ("disbelief", re.compile(r"\b(are you (serious|kidding)|you('ve| have) got to be|what is wrong with you|i don't believe you|that('s| is) a lie|lying to me|excuse me\?|really\?|wow\b|unbelievable|i('m| am) not (going to|gonna)|let'?s google|that makes no sense|doesn'?t make sense)", re.I)),
    ("heinous",   re.compile(r"\b(gun|shot|shoot|shooting|stab|choke|strangl|kill|murder|dead|died|starv|assault|sexual|child|minor|abuse|fentanyl|meth|overdose|drunk driving|DWI|evad)", re.I)),
    ("begging",   re.compile(r"\b(please|i('m| am) (sorry|begging)|one more chance|another chance|last chance|give me a chance|i promise|i swear|forgive)\b", re.I)),
    ("sharp_q",   re.compile(r"\b(why (are|do|did|would|were|aren't|didn't|can't) you|what (were|are) you (thinking|doing)|how many times|do you think|is that (fair|okay|right)|what('s| is) (wrong|going on|up) with|where did (he|she|you) go wrong)\b", re.I)),
    ("reveal",    re.compile(r"\b(turns out|it says (right )?here|the (police )?report says|according to the|didn'?t tell|never told|found out|come to find out|as it turns out|the record shows|stipulat)", re.I)),
    ("excuse",    re.compile(r"\b(i didn'?t know|i was just|it wasn'?t me|i thought|i don'?t (really )?know|i forgot|nobody told me|i was (going|trying) to|misbehav)", re.I)),
    ("notoriety", re.compile(r"\b(news|reporter|viral|famous|tiktok|instagram|youtube|facebook|police chase|standoff|swat)\b", re.I)),
]
SIGNALS = [(name, rx, float(editorial.PROXIES[name]["weight"])) for name, rx in _SIGNALS]
TITLE_LINE = re.compile(r"[?!]$")
NAME = re.compile(r"(?:versus|vs\.?)\s+(?:uh\s+)?([A-Z][\w'.-]+(?:\s+[A-Z][\w'.-]+){0,3})")


def turns(tr: Transcript, t: float, span: float) -> list[tuple[float, str]]:
    """Speaker turns: the captions mark a change with a '>>' prefix on the word."""
    out, cur, ct = [], [], None
    for w in tr.slice(t, t + span):
        tok = w.w
        if tok.startswith(">>"):
            if cur:
                out.append((ct, " ".join(cur)))
            cur, ct = [], None
            tok = tok[2:].strip()
            if not tok:
                continue
        if ct is None:
            ct = w.t
        cur.append(tok)
    if cur:
        out.append((ct, " ".join(cur)))
    return out


def digest(tr: Transcript, t: float, span: float, max_lines: int = 10) -> dict:
    """PROXY layer. `proxy_score` orders reading; it is not the rubric."""
    tt = turns(tr, t, span)
    hits: dict[str, int] = {s[0]: 0 for s in SIGNALS}
    lines: list[tuple[float, float, str]] = []      # (weight, offset, text)
    for off, txt in tt:
        nw = len(txt.split())
        w = 0.0
        for name, rx, wt in SIGNALS:
            n = len(rx.findall(txt))
            if n:
                hits[name] += n
                w += wt * min(n, 3)
        if 5 <= nw <= 45 and TITLE_LINE.search(txt.strip()):
            w += 1.0                                  # a line that can be a title
        if w and nw <= 70:
            lines.append((w, off - t, txt))
    lines.sort(key=lambda x: -x[0])
    cats = sum(1 for v in hits.values() if v)
    score = sum(wt * math.log1p(hits[name]) for name, _, wt in SIGNALS) * (1 + 0.25 * cats)
    by_dim: dict[str, float] = {}
    for name, _, wt in SIGNALS:
        d = editorial.PROXIES[name]["dimension"]
        by_dim[d] = round(by_dim.get(d, 0.0) + wt * math.log1p(hits[name]), 2)
    return {"proxy_score": round(score, 1), "ent_score": round(score, 1),   # ent_score kept for old callers
            "proxy_by_dimension": by_dim, "hits": hits, "turns": len(tt),
            "lines": [(int(round(o)), txt[:160]) for _, o, txt in lines[:max_lines]]}


def load(vid: str) -> Transcript:
    p = ROOT / "work" / vid / f"{vid}.transcript.json"
    return Transcript.from_json(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- the editorial pass
def editorial_pass(tr: Transcript, t: float, span: float, name_hint: str = "") -> dict:
    """One Analyzer.score call on this hearing with the daily pipeline's prompt.
    Returns the scored case dict (scores, editorial block, total, decision)."""
    from boydclips.analyze import Analyzer
    from boydclips.config import load_config
    cfg = load_config()
    an = Analyzer(cfg)
    case = {
        "start_s": float(t), "end_s": float(t + span), "defendant_name": name_hint or "unknown",
        "cause_number": "unknown", "charge": "unknown", "proceeding_type": "other",
        "outcome": "unknown", "one_line": "manual-path hearing", "continued": False,
        "extraction_confidence": "low",
    }
    meta = {"title": f"manual {tr.video_id}", "docket_date": "unknown",
            "url": f"https://www.youtube.com/watch?v={tr.video_id}"}
    scored = an.score(tr, [case], meta)
    return scored[0] if scored else {}


def print_rationale(case: dict) -> None:
    print(editorial.rationale_block(case))


def _rank_key(r: dict):
    ed = r.get("editorial") or {}
    sc = r.get("scores") or {}
    if "total_score" in r:
        return (
            0 if ed.get("gate_pass") else 1,
            -float(r.get("total_score") or 0),
            -float((sc.get("story_engine") or {}).get("score", 0) or 0),
            -float((sc.get("payoff") or {}).get("score", 0) or 0),
            -float((sc.get("packaging") or {}).get("score", 0) or 0),
        )
    return (2, -float(r.get("proxy_score") or 0), 0, 0, 0)


def selftest() -> int:
    from boydclips.transcribe import Word

    def mk(text: str) -> Transcript:
        return Transcript(video_id="x", words=[Word(t=float(i), w=w) for i, w in enumerate(text.split())])

    good = mk("Court is calling state versus Test. >> Why did you put a gun to your son's head? "
              ">> I didn't know it was loaded, I was just holding it. >> The police report says right here "
              "you pointed it. >> Please judge, one more chance, I promise. >> Are you serious? Your motion to "
              "revoke is granted, ten years TDC. >> My mom is here, please.")
    dull = mk("Court is calling state versus Test. >> Parties announce. >> Ready for the state. "
              ">> We need a reset for the PSI. >> All right, sixty days. >> Thank you judge. >> Next case.")
    # charge-severity trap: heinous words with nothing happening
    grim = mk("Court is calling state versus Test. >> This is a murder case with a child victim and a gun. "
              ">> We need a reset for DNA. >> All right, sixty days. >> Thank you judge.")
    g, d, h = digest(good, 0, 999), digest(dull, 0, 999), digest(grim, 0, 999)
    ok = (g["proxy_score"] > 3 * max(d["proxy_score"], 1.0) and d["proxy_score"] < 3
          and g["turns"] == 7 and d["turns"] == 7
          and g["proxy_score"] > 2 * h["proxy_score"]            # story beats charge words
          and g["hits"]["reveal"] >= 1 and g["hits"]["excuse"] >= 1
          and set(g["proxy_by_dimension"]) <= set(editorial.DIMENSIONS))
    ranked = sorted([{"k": "dull", **d}, {"k": "good", **g}, {"k": "grim", **h}], key=_rank_key)
    ok = ok and [r["k"] for r in ranked] == ["good", "grim", "dull"]
    print(f"good proxy {g['proxy_score']} by_dim {g['proxy_by_dimension']} hits {g['hits']}")
    print(f"grim proxy {h['proxy_score']} (charge words only)")
    print(f"dull proxy {d['proxy_score']} turns {d['turns']}")
    print("BANGER_DIGEST_SELFTEST_OK" if ok else "BANGER_DIGEST_SELFTEST_FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pos", nargs="*")
    ap.add_argument("--rows")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--lines", type=int, default=8)
    ap.add_argument("--editorial", action="store_true", help="run the daily pipeline's editorial pass (one model call per hearing)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.rows:
        rows = json.loads(Path(a.rows).read_text(encoding="utf-8"))
        out = []
        for r in rows:
            try:
                tr = load(r["video_id"])
            except FileNotFoundError:
                continue
            d = digest(tr, r["t"], r["span_s"], a.lines)
            row = {**r, **d}
            if a.editorial:
                m = NAME.search(r.get("open", "") or "")
                row.update(editorial_pass(tr, r["t"], r["span_s"], m.group(1) if m else ""))
            out.append(row)
        out.sort(key=_rank_key)
        print(f"ranked by {' -> '.join(editorial.MANUAL_RANK_ORDER)}" if a.editorial else "ranked by proxy only — run --editorial for the verdict")
        for r in out[: a.top]:
            m = NAME.search(r.get("open", "") or "")
            who = m.group(1) if m else (r.get("defendant_name") or r.get("open", "")[:50])
            sig = ", ".join(f"{k}{v}" for k, v in r["hits"].items() if v)
            verdict = f" {r.get('decision')} {r.get('total_score')}/100" if "total_score" in r else ""
            print(f"\n=== {r['video_id']}@{int(r['t'])} {r.get('date', '')} {r['span_s'] / 60:.0f}m "
                  f"proxy{r['proxy_score']}{verdict} | {who} | {sig}")
            if "total_score" in r:
                print_rationale(r)
            for off, txt in r["lines"]:
                print(f"  +{off:4d}s {txt}")
        return 0
    vid, t, span = a.pos[0], float(a.pos[1]), float(a.pos[2])
    tr = load(vid)
    d = digest(tr, t, span, a.lines)
    print(json.dumps({k: v for k, v in d.items() if k != "lines"}))
    for off, txt in d["lines"]:
        print(f"  +{off:4d}s {txt}")
    if a.editorial:
        print()
        print_rationale(editorial_pass(tr, t, span))
    return 0


if __name__ == "__main__":
    sys.exit(main())
