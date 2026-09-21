# -*- coding: utf-8 -*-
"""Thumbnail CAPTION check - the hook, not the summary (R60, 2026-09-07).

    python tools/check_caption.py "WHO TASED YOU?" --title "<video title>" --transcript work/<vid>/<vid>.transcript.json [--from S --to E]
    python tools/check_caption.py --selftest

Nathan, 2026-09-07: "The current captions are weak because some of them read
like transcript summaries instead of high-CTR thumbnail copy." The goal:
"What does THAT mean? I need to click." NOT "Oh, the thumbnail already told
me the story."

REFUSES (accuracy / channel rules, the same class check_title refuses):
  - the generic filler he listed: "Judge Boyd Reacts", "Courtroom Drama",
    "He Says...", "She Explains...", "Defendant Tells Court...", "BIG MISTAKE"
    (and their obvious siblings: "she says", "he explains", "judge reacts")
  - profanity (boydclips.censor)
  - a forbidden token (the defendant's name) when --forbid is given
FLAGS (editorial advice, printed, not a veto):
  - word count outside 2-5 ("Prefer 2-5 words")
  - repeats the title: two or more content words shared with the title
    ("complement the video title instead of repeating the same information")
  - unverified spelling: a word that is in neither the transcript span nor
    the small allow-list ("Spellcheck every caption before use" - there is no
    dictionary on this machine, so the transcript is the dictionary; a word
    the hearing never said is either invented or misspelt, and either way it
    is said out loud)
Prints CAPTION_OK or CAPTION_REFUSED and exits 0 / 1.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from boydclips.censor import has_profanity  # noqa: E402

FILLER = [
    "judge boyd reacts", "judge reacts", "boyd reacts", "courtroom drama", "he says", "she says",
    "he explains", "she explains", "defendant tells court", "defendant tells the court",
    "tells court", "big mistake", "judge boyd responds", "judge boyd reacts to",
]
STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "his", "her", "him", "he", "she", "it",
        "its", "it's", "is", "was", "are", "at", "by", "from", "with", "that", "this", "you", "your", "me",
        "my", "our", "we", "i", "so", "do", "did", "not", "don't", "no", "yes", "what", "who", "why", "how",
        "judge", "boyd", "court", "courtroom"}
ALLOW = {"years", "year", "days", "day", "months", "again", "consecutive", "record", "jail", "prison",
         "guilty", "denied", "revoked", "probation", "deferred", "sentence", "life", "vs", "or", "and",
         "the", "a", "an", "of", "to", "in", "on", "for", "his", "her", "he", "she", "it's", "so", "our",
         "you", "me", "my", "i", "who", "what", "why", "how", "not", "don't", "no", "yes", "from", "with",
         "back", "time", "money", "move", "makes", "make", "judge", "boyd", "texted", "texts"}


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9' ]+", " ", s.lower().replace("’", "'")).strip()


def tokens(s: str) -> list[str]:
    return [t.strip("'") for t in norm(s).split() if t.strip("'")]


def content(toks: list[str]) -> set[str]:
    return {t for t in toks if len(t) > 3 and t not in STOP}


def check(caption: str, title: str | None = None, transcript: list[str] | None = None,
          forbid: list[str] | None = None) -> dict:
    out = {"caption": caption, "refusals": [], "flags": [], "ok": True}
    low = norm(caption)
    for f in FILLER:
        if f in low:
            out["refusals"].append(f"generic filler: {f!r}")
    if has_profanity(caption):
        out["refusals"].append("profanity")
    toks = tokens(caption)
    for f in (forbid or []):
        if f.lower() in toks:
            out["refusals"].append(f"forbidden token {f!r}")
    n = len(toks)
    if not 2 <= n <= 5:
        out["flags"].append(f"{n} words (prefer 2-5)")
    if title:
        shared = content(toks) & content(tokens(title))
        if len(shared) >= 2:
            out["flags"].append(f"repeats the title: {sorted(shared)}")
    if transcript is not None:
        vocab = set()
        for w in transcript:
            vocab.update(tokens(w))
        # numbers spoken as words ("twenty-five") are grounded by check_title / text_grounded; digits pass here
        unknown = [t for t in toks if t not in vocab and t not in ALLOW and not re.match(r"^\d", t)]
        if unknown:
            out["flags"].append(f"unverified spelling (not in the hearing): {unknown}")
    out["ok"] = not out["refusals"]
    return out


def load_transcript(path: str, lo: float | None, hi: float | None) -> list[str]:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    words = d.get("words") if isinstance(d, dict) else d
    if lo is None and hi is None:
        return [w["w"] for w in words]
    return [w["w"] for w in words if (lo or 0) - 1 <= float(w.get("t", 0)) <= (hi or 1e12) + 1]


def selftest() -> int:
    tr = ("who tased you give me a name i cannot remember any names four years deferred adjudication "
          "thirty days or i will give you a conviction which do you choose").split()
    title = "Judge Boyd Offered 30 Days in Jail. He Took the Conviction."
    cases = [
        ("WHO TASED YOU?", True, [], "his style, verbatim, 3 words, no title overlap"),
        ("JUDGE BOYD REACTS", False, [], "listed filler"),
        ("COURTROOM DRAMA", False, [], "listed filler"),
        ("SHE EXPLAINS EVERYTHING", False, [], "listed filler"),
        ("BIG MISTAKE", False, [], "listed filler"),
        ("WHO TAZED YOU?", True, ["unverified spelling"], "misspelling must be flagged"),
        ("30 DAYS OR THE CONVICTION", True, ["repeats the title"], "two content words shared with the title"),
        ("I CANNOT REMEMBER ANY NAMES OK", True, ["6 words"], "over five words is flagged"),
        ("F*** THIS", False, [], "profanity refused"),
    ]
    bad = 0
    for cap, want_ok, want_flags, why in cases:
        r = check(cap.replace("F***", "fuck"), title, tr)
        ok = (r["ok"] == want_ok) and all(any(wf in f for f in r["flags"]) for wf in want_flags)
        bad += 0 if ok else 1
        print(f"  {'PASS' if ok else 'FAIL'} {cap!r:34} ok={r['ok']} refusals={r['refusals']} flags={r['flags']}  ({why})")
    print("CHECK_CAPTION_SELFTEST", "ALL_OK" if not bad else f"{bad} FAILED")
    return 0 if not bad else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("caption", nargs="?")
    ap.add_argument("--title")
    ap.add_argument("--transcript")
    ap.add_argument("--from", dest="lo", type=float)
    ap.add_argument("--to", dest="hi", type=float)
    ap.add_argument("--forbid", nargs="*", default=[])
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.caption:
        ap.error("caption required")
    tr = load_transcript(a.transcript, a.lo, a.hi) if a.transcript else None
    r = check(a.caption, a.title, tr, a.forbid)
    for x in r["refusals"]:
        print(f"  REFUSE {x}")
    for x in r["flags"]:
        print(f"  flag   {x}")
    print("CAPTION_OK" if r["ok"] else "CAPTION_REFUSED", repr(a.caption))
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())