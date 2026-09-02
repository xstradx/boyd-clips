"""Entertainment layer on top of the picker - the observer's pass.

The picker (config/picker.json, tools/hearing_measure.py) measures density:
questions per minute, narrative per 100 words, MTR/sentencing. It finds
HEARINGS. It does not know what a viewer stays for. 2026-09-02, on a shortlist
I had delivered unwatched: *"I think you have to use observer skill to
actually pic actual entertaining banger clips"* and *"Shouldn't u upgraded the
picker with task observer?"*.

What his viewers actually stayed for, measured on the channel catalog
(data/catalog_vs_picker.json, Boyd-only, views): family confrontation 61k,
notoriety 40k, prison + disbelief 28k, heinous facts 22.6k, begging 16.5k,
begging long 9.8k; the pipeline's plea-lecture shorts sit at 255-1500/day.
So the signals here are those categories, counted on the hearing's own
turns, plus the one thing every winner shares - a line she says that stands
alone as a title.

Usage:
  python tools/banger_digest.py VIDEO_ID T SPAN_S        one hearing, digest
  python tools/banger_digest.py --rows FILE [--top N]    rank rows (video_id,t,span_s)
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
from boydclips.transcribe import Transcript  # noqa: E402

# Each signal: (name, regex, weight). Weights follow the measured order above.
SIGNALS = [
    ("family",    re.compile(r"\b(my (mom|mother|dad|father|son|daughter|kids?|children|baby|wife|husband|girlfriend|grand\w+))\b|\b(mom|mother|daughter|baby|kids|children)\b", re.I), 3.0),
    ("confront",  re.compile(r"\b(look at (me|her|him)|say (it|that) to|face (her|him|them)|(she|he|they)('s| is) (here|in the courtroom|sitting)|victim)\b", re.I), 3.0),
    ("prison",    re.compile(r"\b(TDC|penitentiary|prison|(\d+|two|three|four|five|six|seven|eight|nine|ten|fifteen|twenty) years?|life sentence|revoke|revoked|remand|custody|take (him|her) into)\b", re.I), 2.5),
    ("disbelief", re.compile(r"\b(are you (serious|kidding)|you('ve| have) got to be|what is wrong with you|i don't believe you|that('s| is) a lie|lying to me|excuse me\?|really\?|wow\b|unbelievable|i('m| am) not (going to|gonna))", re.I), 2.5),
    ("heinous",   re.compile(r"\b(gun|shot|shoot|shooting|stab|choke|strangl|kill|murder|dead|died|starv|assault|sexual|child|minor|abuse|fentanyl|meth|overdose|drunk driving|DWI|evad)", re.I), 2.0),
    ("begging",   re.compile(r"\b(please|i('m| am) (sorry|begging)|one more chance|another chance|last chance|give me a chance|i promise|i swear|forgive)\b", re.I), 2.0),
    ("sharp_q",   re.compile(r"\b(why (are|do|did|would|were|aren't|didn't|can't) you|what (were|are) you (thinking|doing)|how many times|do you think|is that (fair|okay|right)|what('s| is) (wrong|going on|up) with)\b", re.I), 1.5),
    ("notoriety", re.compile(r"\b(news|reporter|viral|famous|tiktok|instagram|youtube|facebook|police chase|standoff|swat)\b", re.I), 1.5),
]
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
    # Weighted hits, log-damped so one word repeated does not win, scaled by
    # the number of distinct categories - the measured winners mix them.
    score = sum(wt * math.log1p(hits[name]) for name, _, wt in SIGNALS) * (1 + 0.25 * cats)
    return {"ent_score": round(score, 1), "hits": hits, "turns": len(tt),
            "lines": [(int(round(o)), txt[:160]) for _, o, txt in lines[:max_lines]]}


def load(vid: str) -> Transcript:
    p = ROOT / "work" / vid / f"{vid}.transcript.json"
    return Transcript.from_json(p.read_text(encoding="utf-8"))


def selftest() -> int:
    from boydclips.transcribe import Word

    def mk(text: str) -> Transcript:
        return Transcript(video_id="x", words=[Word(t=float(i), w=w) for i, w in enumerate(text.split())])

    good = mk("Court is calling state versus Test. >> Why did you put a gun to your son's head? "
              ">> Please judge, one more chance, I promise. >> Are you serious? Your motion to "
              "revoke is granted, ten years TDC. >> My mom is here, please.")
    dull = mk("Court is calling state versus Test. >> Parties announce. >> Ready for the state. "
              ">> We need a reset for the PSI. >> All right, sixty days. >> Thank you judge. >> Next case.")
    g, d = digest(good, 0, 999), digest(dull, 0, 999)
    ok = g["ent_score"] > 3 * max(d["ent_score"], 1.0) and d["ent_score"] < 3 and g["turns"] == 5 and d["turns"] == 7
    print(f"good ent {g['ent_score']} turns {g['turns']} hits {g['hits']}")
    print(f"dull ent {d['ent_score']} turns {d['turns']} hits {d['hits']}")
    print("BANGER_DIGEST_SELFTEST_OK" if ok else "BANGER_DIGEST_SELFTEST_FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pos", nargs="*")
    ap.add_argument("--rows")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--lines", type=int, default=8)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.rows:
        rows = json.loads(Path(a.rows).read_text(encoding="utf-8"))
        out = []
        for r in rows:
            try:
                d = digest(load(r["video_id"]), r["t"], r["span_s"], a.lines)
            except FileNotFoundError:
                continue
            out.append({**r, **d})
        out.sort(key=lambda r: -r["ent_score"])
        for r in out[: a.top]:
            m = NAME.search(r.get("open", ""))
            who = m.group(1) if m else r.get("open", "")[:50]
            sig = ", ".join(f"{k}{v}" for k, v in r["hits"].items() if v)
            print(f"\n=== {r['video_id']}@{int(r['t'])} {r.get('date', '')} {r['span_s'] / 60:.0f}m "
                  f"ent{r['ent_score']} pick{r.get('score', 0):.0f} | {who} | {sig}")
            for off, txt in r["lines"]:
                print(f"  +{off:4d}s {txt}")
        return 0
    vid, t, span = a.pos[0], float(a.pos[1]), float(a.pos[2])
    d = digest(load(vid), t, span, a.lines)
    print(json.dumps({k: v for k, v in d.items() if k != "lines"}))
    for off, txt in d["lines"]:
        print(f"  +{off:4d}s {txt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
