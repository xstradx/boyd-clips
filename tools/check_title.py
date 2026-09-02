# -*- coding: utf-8 -*-
"""R41 - titles are hooks, not descriptions. R16 - a quoted span is verbatim.

Nathan, 2026-08-31: "Those titles are weak" (#173); "I guess a/b test them but
idk I think title could be better do 3 different ones" (#174). My titles
described the video. His best recent performer withholds the ending, the worst
states the sentence. House constants measured on Court Trials TV (n=899) in
spec/PACKAGING.md: 50-65 characters, hard ceiling 70, name the judge (80% of
the top 40 do), the beats are 2-4 emphasised words.

    python tools/check_title.py "<title>" ["<title B>" ...] --transcript <file>
    python tools/check_title.py --selftest

REFUSES (TITLE_FAIL, exit 1)
    over 70 characters
    a stated outcome: N years / months, sentenced, guilty, verdict, acquitted,
        life sentence, without parole
    uncensored profanity (channel rule: audio yes, text no)
    a quoted span that is not verbatim in the transcript (R16); a quoted span
        with no --transcript is refused too - unverifiable is not verified
WARNS (printed, does not fail)
    the judge is not named
    length outside 50-65

The transcript may be a words JSON (list of {"w": ...} or {"words": [...]}),
an .srt/.vtt, or plain text. Both sides are censored and normalised before the
verbatim match, so "s***" in the title matches "shit" in the transcript.
"""
import json
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
from boydclips.censor import censor, has_profanity  # noqa: E402

HARD_MAX = 70
BAND = (50, 65)

# each pattern is an outcome the title must withhold
OUTCOME = [
    (r"\b\d+\s*(?:-|to)?\s*\d*\s*(?:years?|yrs?|months?)\b", "states the sentence length"),
    (r"\bsentenc(?:e|es|ed|ing)\b", "states the sentence"),
    (r"\bguilty\b", "states the verdict"),
    (r"\bverdict\b", "states the verdict"),
    (r"\bacquitt(?:ed|al)\b", "states the verdict"),
    (r"\blife (?:sentence|in prison|without parole)\b", "states the sentence"),
    (r"\bwithout parole\b", "states the sentence"),
    (r"\bgets? (?:\d+|life|prison|probation)\b", "states the outcome"),
]
_QUOTE = re.compile(r"[\"\u201c\u201d]([^\"\u201c\u201d]{3,})[\"\u201c\u201d]|(?<![A-Za-z])'([^']{3,})'(?![A-Za-z])")
_TS = re.compile(r"^\d+$|^\d\d:\d\d:\d\d[,.]\d+ -->|^WEBVTT|^NOTE\b")


def _norm(s):
    """Censored, lower, letters/digits/* only - NO spaces or apostrophes. The
    source words JSON tokenises "ma'am" as "ma" + "'am" and a title is not
    wrong for writing it as one word. A span is verbatim if its letters are."""
    s = s.replace("\u2019", "'").replace("\u2018", "'").replace(">>", " ")
    s = censor(s).lower()
    return re.sub(r"[^a-z0-9*]", "", s)


def load_transcript(path):
    """Words JSON, srt/vtt or plain text -> one normalised string."""
    raw = open(path, encoding="utf-8", errors="replace").read()
    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":
        d = json.loads(raw)
        if isinstance(d, dict):
            d = d.get("words") or d.get("segments") or next(
                (v for v in d.values() if isinstance(v, list)), [])
        words = []
        for it in d:
            if isinstance(it, dict):
                words.append(str(it.get("w") or it.get("word") or it.get("text") or ""))
            else:
                words.append(str(it))
        return _norm(" ".join(words))
    if ext in (".srt", ".vtt"):
        keep = [ln for ln in raw.splitlines() if ln.strip() and not _TS.match(ln.strip())]
        return _norm(" ".join(keep))
    return _norm(raw)


def quoted_spans(title):
    return [a or b for a, b in _QUOTE.findall(title)]


def check(title, transcript=None, verbose=True):
    """transcript: normalised string (from load_transcript) or None."""
    fails, warns = [], []
    n = len(title)
    if n > HARD_MAX:
        fails.append(f"{n} chars, hard ceiling {HARD_MAX}")
    elif not BAND[0] <= n <= BAND[1]:
        warns.append(f"{n} chars, house band {BAND[0]}-{BAND[1]}")
    low = title.lower()
    for pat, why in OUTCOME:
        m = re.search(pat, low)
        if m:
            fails.append(f"{why}: '{m.group(0)}'")
            break
    if has_profanity(title):
        fails.append(f"uncensored profanity - text is always censored: '{censor(title)}'")
    if "judge" not in low:
        warns.append("judge not named (80% of the reference top 40 name the judge)")
    for span in quoted_spans(title):
        if transcript is None:
            fails.append(f"quoted span '{span}' cannot be verified - pass --transcript (R16)")
        elif _norm(span) not in transcript:
            fails.append(f"quoted span '{span}' is not verbatim in the transcript (R16)")
    ok = not fails
    if verbose:
        print(("TITLE_OK    " if ok else "TITLE_FAIL  ") + f"[{n}] {title}")
        for f in fails:
            print("    REFUSED  " + f)
        for w in warns:
            print("    warn     " + w)
    return ok, fails, warns


def selftest():
    """Known answers: his winning variant passes, the stated sentence fails."""
    ok = True
    T = _norm("Judge Boyd: You keep this up and you're going to end up in prison or dead. "
              "You're full of shit and you know it. Do you understand me?")
    cases = [
        ("Judge Boyd Warns Him He'll End Up in Prison or Dead", T, True),
        ("Man Gets 40 Years After Judge Boyd Loses Patience", T, False),
        ("Judge Boyd Sentences Him After He Argues With Her in Court", T, False),
        ("Judge Boyd Loses Patience With a Defendant Who Will Not Stop Talking Back to Her", T, False),
        ("Judge Boyd Tells Him \"You're Full of Shit\" to His Face", T, False),
        ("Judge Boyd Tells Him \"You're Full of S***\" to His Face", T, True),
        ("Judge Boyd Tells Him \"You Disgust Me\" to His Face", T, False),
        ("Judge Boyd Tells Him \"You're Full of S***\" to His Face", None, False),
    ]
    for title, tr, want in cases:
        got, fails, warns = check(title, tr, verbose=False)
        good = got == want
        ok = ok and good
        print(f"  {'ok  ' if good else 'FAIL'} {'pass' if want else 'refuse'}: {title}"
              + (f"  -> {fails[0]}" if fails else ""))
    print("SELFTEST_PASS check_title" if ok else "SELFTEST_FAIL check_title")
    return ok


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] == "--selftest":
        sys.exit(0 if selftest() else 1)
    tr = None
    if "--transcript" in a:
        i = a.index("--transcript")
        tr = load_transcript(a[i + 1])
        del a[i:i + 2]
    if not a:
        print(__doc__)
        sys.exit(2)
    all_ok = True
    for t in a:
        all_ok = check(t, tr)[0] and all_ok
    sys.exit(0 if all_ok else 1)
