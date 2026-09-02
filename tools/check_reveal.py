# -*- coding: utf-8 -*-
"""R34 on the RENDERED captions: no word is on screen before it is spoken.

NATHAN_RULES R34 - *"it shows the word exactly like I already knew she was
gonna say that ... that's where it really matters right there in those type of
moments"*. Its check until 2026-09-01 was `caption_short.REVEAL != "off"` - a
check on a SETTING, not on the file. The OFFERUP short that shipped as
LqAneu_GSOM (OFFERUP_SHORT_V7, 2026-08-31) passed that check and its .ass
draws every card whole at card start: 93 of 93 non-leading words legible
before they were spoken, mean 0.45s early, worst 1.90s. That file is kept as
tools/fixtures/OFFERUP_V7_shipped.ass and is this checker's known-bad control.

WHAT IS MEASURED
For every word in the words json, the earliest .ass event in which that word is
VISIBLE (drawn, and not wrapped in the reserve mode's {\\alpha&HFF&} span).
`early = word.s - first_visible`. A word is early when early > tolerance.

THE TOLERANCE is not a guess. It is the aligner's own timing noise, measured
by tools/align_words.py --jitter (the same audio offset by a known amount;
whatever the word starts move by beyond that offset is noise):
    SANCHEZ_SHORT_FINAL.mp4 (the reference)  195/195 words  p95 0.03s
    OFFERUP_SHORT_V7.mp4 (mastered, shipped)  129/136       p95 0.05s
    OFFERUP v4_full.mp4 (raw cut, unmastered) 128/136       p95 0.51s
The floor carries the reference's p95 as captions.reveal_tolerance_s; a word
drawn earlier than that is early by more than the aligner could be wrong.

    python tools/check_reveal.py SHORT.ass words.json     -> REVEAL_OK / REVEAL_FAIL
    python tools/check_reveal.py --selftest
"""
import difflib
import json
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import short_engine as _SE

TOL = _SE.REVEAL_TOL_S           # floor captions.reveal_tolerance_s
FIXTURE_ASS = os.path.join(ROOT, "tools", "fixtures", "OFFERUP_V7_shipped.ass")
FIXTURE_WORDS = os.path.join(ROOT, "tools", "fixtures", "OFFERUP_V7_words.json")

_TAG = re.compile(r"\{[^}]*\}")


def ass_seconds(t):
    h, m, s = t.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def _norm(w):
    return "".join(ch for ch in w.lower() if ch.isalnum())


def visible_tokens(text):
    """Words a viewer can read in this event, in order.

    Override blocks toggle visibility: {\\alpha&HFF&} hides what follows,
    {\\alpha&H00&} shows it again. Everything else inside braces is styling.
    """
    out, hidden, pos = [], False, 0
    for m in _TAG.finditer(text):
        seg = text[pos:m.start()]
        if not hidden:
            out += [w for w in seg.split() if _norm(w)]
        tag = m.group(0).replace(" ", "")
        if "\\alpha&HFF&" in tag:
            hidden = True
        elif "\\alpha&H00&" in tag:
            hidden = False
        pos = m.end()
    seg = text[pos:]
    if not hidden:
        out += [w for w in seg.split() if _norm(w)]
    return out


def first_visible(ass_path):
    """[(token, time)] - each token the moment it first becomes readable.

    Events are read in file order (caption_short writes cards in order and
    steps in order). Consecutive events whose visible words extend the
    previous event's are the same card growing; only the new words count.
    """
    events = []
    with open(ass_path, encoding="utf-8", errors="ignore") as f:
        for ln in f:
            if not ln.startswith("Dialogue:"):
                continue
            parts = ln.rstrip("\n").split(",", 9)
            if len(parts) < 10:
                continue
            events.append((ass_seconds(parts[1]), ass_seconds(parts[2]), parts[9]))
    seen, prev_vis, prev_end = [], [], None
    for st, en, text in events:
        vis = visible_tokens(text)
        same_card = (prev_end is not None and abs(st - prev_end) < 0.011
                     and len(vis) > len(prev_vis)
                     and [_norm(w) for w in vis[:len(prev_vis)]] ==
                     [_norm(w) for w in prev_vis])
        new = vis[len(prev_vis):] if same_card else vis
        seen += [(w, st) for w in new]
        prev_vis, prev_end = vis, en
    return seen


def check(ass_path, words_path, tol=None, verbose=True):
    """(ok, detail). ok is None when too few words could be matched to say."""
    tol = TOL if tol is None else tol
    if not os.path.exists(ass_path):
        return False, "no .ass"
    words = json.load(open(words_path, encoding="utf-8"))
    words = [w for w in words if _norm(w["w"])]
    seen = first_visible(ass_path)
    ta = [_norm(w["w"]) for w in words]
    tb = [_norm(w) for w, _ in seen]
    early, matched = [], 0
    for tag, i0, i1, j0, j1 in difflib.SequenceMatcher(None, ta, tb, autojunk=False).get_opcodes():
        if tag != "equal":
            continue
        for i, j in zip(range(i0, i1), range(j0, j1)):
            matched += 1
            d = float(words[i]["s"]) - seen[j][1]
            if d > tol + 1e-9:
                early.append((round(d, 2), words[i]["w"], float(words[i]["s"])))
    if not words or matched < 0.8 * len(words):
        return None, (f"only {matched}/{len(words)} words matched between .ass and "
                      f"words json - reveal UNMEASURED")
    if early:
        ds = [e[0] for e in early]
        worst = max(early)
        return False, (f"{len(early)}/{matched} words readable before spoken "
                       f"(tol {tol:.2f}s): mean {sum(ds)/len(ds):.2f}s early, "
                       f"worst {worst[0]:.2f}s ('{worst[1]}' at {worst[2]:.2f}s)")
    return True, f"{matched}/{len(words)} words matched, none readable before spoken (tol {tol:.2f}s)"


def selftest():
    ok = True

    def chk(label, got, want):
        nonlocal ok
        hit = (got == want)
        ok &= hit
        print(f"  {'OK  ' if hit else 'MISS'}  {label:58} -> {got} (want {want})")

    # CONTROL 1: the shipped V7 .ass (whole card at card start) must FAIL
    g, det = check(FIXTURE_ASS, FIXTURE_WORDS)
    print(f"  shipped V7: {det}")
    chk("shipped OFFERUP_V7 .ass (reveal off) fails", g, False)
    m = re.search(r"(\d+)/(\d+) words readable.*mean ([\d.]+)s early, worst ([\d.]+)s", det or "")
    if m:
        chk("V7 control reproduces 93 early words", int(m.group(1)), 93)
        chk("V7 control mean early 0.45s", round(float(m.group(3)), 2), 0.45)
        chk("V7 control worst early 1.90s", float(m.group(4)), 1.9)
    # CONTROL 2: the same words rendered by caption_short in the floor's reveal
    # mode must PASS - and in 'off' mode must FAIL, from the same generator
    import tempfile
    import caption_short as C
    words = json.load(open(FIXTURE_WORDS, encoding="utf-8"))
    keep = C.REVEAL
    with tempfile.TemporaryDirectory() as d:
        for mode, want in (("reserve", True), ("build", True), ("off", False)):
            C.REVEAL = mode
            cs = C.cards_phrase(words, max_chars=_SE.MAX_CHARS, max_words=_SE.MAX_WORDS,
                                target_chars=_SE.TARGET_CHARS)
            p = os.path.join(d, f"{mode}.ass")
            n = C.build_snap(cs, p, _SE.W, _SE.H, _SE.H // 2)
            g, det = check(p, FIXTURE_WORDS)
            print(f"  {mode:8}: {n} events, {det}")
            chk(f"caption_short reveal={mode!r} -> {'PASS' if want else 'FAIL'}", g, want)
        C.REVEAL = keep
        # CONTROL 3: a hand-made .ass with a reserve-hidden word is not 'seen'
        # until its own event - the alpha parser, both directions
        p = os.path.join(d, "alpha.ass")
        open(p, "w", encoding="utf-8").write(
            "[Events]\n"
            "Dialogue: 0,0:00:01.00,0:00:02.00,Mid,,0,0,0,,{\\pos(540,960)}one {\\alpha&HFF&}two{\\alpha&H00&}\n"
            "Dialogue: 0,0:00:02.00,0:00:03.00,Mid,,0,0,0,,{\\pos(540,960)}one two\n")
        wj = os.path.join(d, "w.json")
        json.dump([{"s": 1.0, "e": 1.5, "w": "one"}, {"s": 2.0, "e": 2.5, "w": "two"}], open(wj, "w"))
        chk("hidden (alpha FF) word counts as unseen", check(p, wj)[0], True)
        json.dump([{"s": 1.0, "e": 1.5, "w": "one"}, {"s": 2.5, "e": 3.0, "w": "two"}], open(wj, "w"))
        chk("a word revealed 0.5s before its start is early", check(p, wj)[0], False)
        json.dump([{"s": 1.0, "e": 1.5, "w": "one"}, {"s": 2.0 + TOL, "e": 3.0, "w": "two"}], open(wj, "w"))
        chk(f"a word revealed exactly tol={TOL}s early is within the aligner's noise",
            check(p, wj)[0], True)
        # CONTROL 4: unmatched words -> None (unmeasured), never a silent pass
        json.dump([{"s": 1.0, "e": 1.5, "w": "alpha"}, {"s": 2.0, "e": 2.5, "w": "beta"}], open(wj, "w"))
        chk("an .ass whose words do not match the json is UNMEASURED (None)",
            check(p, wj)[0], None)
    print("SELFTEST_PASS check_reveal" if ok else "SELFTEST_FAIL check_reveal")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    if len(sys.argv) < 3:
        print("usage: check_reveal.py SHORT.ass words.json | --selftest")
        sys.exit(2)
    g, det = check(sys.argv[1], sys.argv[2])
    print(("REVEAL_OK " if g else ("REVEAL_UNMEASURED " if g is None else "REVEAL_FAIL ")) + det)
    sys.exit(0 if g else 1)
