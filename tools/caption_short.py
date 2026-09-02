# -*- coding: utf-8 -*-
"""Burn captions onto a split-screen short, sitting ON the seam.

His spec, 2026-08-29:
  "do the captions straight in the middle of their split screen"
  "don't let them be all long like where it touches the ends of the screen"
  "I want the words sitting right in the middle of the line"

So: horizontally centred, VERTICALLY CENTRED ON THE SEAM (\\an5 + \\pos), and
width-capped so a card never runs to the edges. The old behaviour moved captions
to the speaker's half, which is why they jump between tiles in SANCHEZ_SHORT.

The seam is FOUND, not assumed: the largest horizontal luminance discontinuity in
the frame. Measured on this short it is y=959 of 1920 (0.499 H).

    python tools/caption_short.py IN.mp4 words.json OUT.mp4 [--cap 132] [--width 0.62]
    python tools/caption_short.py --selftest
"""
import sys, os, json, subprocess, argparse
import numpy as np
import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import short_engine as _SE          # the floor loader; nothing else from it

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
FONTDIR = os.path.join(ROOT, "assets", "fonts")
# House constants come from config/short_floor.json via short_engine.derive()
# (2026-09-01). They were literals here before, a second copy of the floor.
ENTRANCE = _SE.ENTRANCE   # PICKED 2026-08-29: defocus -> sharp. He rejected every
                          # scale-based entrance (bounce/punch/rise/scale) twice.
                          # none | fade | lift | blur | bounce | punch | rise | scale
REVEAL   = _SE.REVEAL     # reserve | build | off  -- never draw a word before it is spoken
FONT     = _SE.FONT       # the Fontname in every ASS style line below
CAP_PX   = _SE.CAP_PX     # Fontsize
SCALE_Y  = _SE.SCALE_Y    # ScaleY
FADE_IN_MS, FADE_OUT_MS = _SE.FADE_IN_MS, _SE.FADE_OUT_MS   # \fad on the blur entrance
BLUR_PX, BLUR_MS = _SE.BLUR_PX, _SE.BLUR_MS                 # \blur{px}\t(0,{ms},\blur0)
MAX_CHARS, MAX_WORDS, TARGET_CHARS = _SE.MAX_CHARS, _SE.MAX_WORDS, _SE.TARGET_CHARS


def find_seam(video):
    """Largest horizontal luminance discontinuity = where the two tiles meet."""
    tmp = "_seam.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "2", "-i", video,
                    "-frames:v", "1", tmp], check=True)
    g = cv2.cvtColor(cv2.imread(tmp), cv2.COLOR_BGR2GRAY)
    os.remove(tmp)
    h = g.shape[0]
    rows = g.mean(axis=1)
    d = np.abs(np.diff(rows))
    band = slice(int(h * 0.35), int(h * 0.65))       # only look near the middle
    y = int(np.argmax(d[band]) + band.start)
    return y, h, g.shape[1]


def cards(words, max_chars=22, max_gap=0.55, max_words=4):
    """Short cards. A caption that spans the frame is unreadable at speed and he
    has asked twice for them not to touch the edges - so cap by CHARACTERS, which
    is what actually drives rendered width, not by word count alone."""
    out, cur = [], []
    for w in words:
        if cur:
            gap = w["s"] - cur[-1]["e"]
            joined = " ".join(x["w"] for x in cur + [w])
            if gap > max_gap or len(joined) > max_chars or len(cur) >= max_words:
                out.append(cur)
                cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    return out



def cards_sentence(words, max_chars=15, max_words=3, max_gap=0.60):
    """Cards cut by SENTENCE and SPEAKER first, character budget second.

    Nathan, 2026-08-29: "let's just say Judge Boyd is talking, and then the
    defendant starts talking. And their beginning of the other person's sentence
    is at the end of the sentence in the video ... you need to learn when to
    start the sentences."

    The old cards() cut purely on a character budget, so a card could carry the
    tail of one speaker's sentence plus the head of the other's. Measured on
    SANCHEZ: 7 of 78 cards straddled a sentence end, the worst being
    "life. Exactly." - the judge's last word and the defendant's whole reply in
    one card, so her reaction was on screen before she gave it.

    A boundary here is NEVER crossed:
      - terminal punctuation  . ! ?
      - a pause longer than max_gap
      - a change of speaker, when words carry a "spk" label from speakers.py

    Inside one speaker's sentence the character budget still applies, because
    that is what keeps a card off the edges of the frame.
    """
    groups, cur = [], []
    for w in words:
        brk = False
        if cur:
            prev = cur[-1]
            if w["s"] - prev["e"] > max_gap:
                brk = True
            if w.get("spk") and prev.get("spk") and w["spk"] != prev["spk"]:
                brk = True
            if prev["w"].rstrip("\"”')").endswith((".", "!", "?")):
                brk = True
        if brk:
            groups.append(cur); cur = []
        cur.append(w)
    if cur:
        groups.append(cur)

    out = []
    for g in groups:
        cur = []
        for w in g:
            if cur:
                joined = " ".join(x["w"] for x in cur + [w])
                if len(joined) > max_chars or len(cur) >= max_words:
                    out.append(cur); cur = []
            cur.append(w)
        if cur:
            out.append(cur)
    return out



# A card must not END on one of these - they bind forward to the next word, so
# breaking after them splits a phrase in half. Measured from the V11 card list,
# which produced "that, Your" / "Honor, but I" and "for your" / "children."
GLUE_FORWARD = {
    "a", "an", "the", "my", "your", "his", "her", "our", "their", "its",
    "this", "that", "these", "those", "of", "to", "for", "in", "on", "at",
    "with", "from", "by", "into", "about", "and", "but", "or", "if", "so",
    "because", "when", "while", "is", "was", "are", "were", "be", "been",
    "am", "do", "does", "did", "have", "has", "had", "can", "could", "will",
    "would", "should", "you", "i", "he", "she", "we", "they", "it", "not",
    "no", "any", "some", "all", "more", "than", "as", "up", "out", "there",
    "you're", "i'm", "i've", "don't", "doesn't", "didn't", "haven't",
    "isn't", "aren't", "we're", "they're", "that's", "there's", "let",
}

# Pairs that must never be split across a card boundary.
KEEP_TOGETHER = {("your", "honor"), ("no", "sir"), ("yes", "sir"),
                 ("yes", "ma'am"), ("no", "ma'am"), ("your", "honour")}


def _norm(w):
    return w.strip().strip('.,!?";:\u201c\u201d\'').lower()


def _break_cost(words, i):
    """Cost of ending a card after words[i]. Lower is better."""
    w = words[i]
    nxt = words[i + 1] if i + 1 < len(words) else None
    if nxt is None:
        return 0.0
    a, b = _norm(w["w"]), _norm(nxt["w"])
    c = 0.0
    gap = nxt["s"] - w["e"]
    c -= min(gap, 0.45) * 9.0            # the speaker's own phrasing is the best cue
    t = w["w"].rstrip('"\u201d\')')
    if t.endswith((",", ";", ":")):
        c -= 3.5                          # punctuation is a real boundary
    if a in GLUE_FORWARD:
        c += 7.0                          # never strand "for" / "your" / "and"
    if (a, b) in KEEP_TOGETHER:
        c += 40.0
    return c


def split_phrase(words, max_chars=None, max_words=None, target_chars=None,
                 min_dur=0.42):
    """Choose card boundaries inside ONE speaker's sentence by minimising cost.

    The character counter alone cut "that, Your" | "Honor, but I". A counter
    cannot know where a phrase ends; a cost function can, and the strongest
    signal is free: the speaker already paused where the phrase ended.

    Cost per card = |chars - target| + a flash penalty for very short cards,
    plus the cost of the boundary chosen after its last word (see _break_cost:
    a pause is a bonus, a comma is a bonus, ending on a glue word is a penalty,
    splitting "Your Honor" is forbidden).

    Solved exactly with a small DP - a sentence is short, so this is cheap and
    beats any greedy rule.
    """
    # budgets default to the floor's captions.cards (measured on SANCHEZ)
    max_chars = MAX_CHARS if max_chars is None else max_chars
    max_words = MAX_WORDS if max_words is None else max_words
    target_chars = TARGET_CHARS if target_chars is None else target_chars
    n = len(words)
    if n == 0:
        return []
    INF = float("inf")
    best = [INF] * (n + 1)
    prev = [-1] * (n + 1)
    best[0] = 0.0
    for j in range(1, n + 1):
        for i in range(max(0, j - max_words), j):
            if best[i] == INF:
                continue
            chunk = words[i:j]
            txt = " ".join(x["w"] for x in chunk)
            if len(txt) > max_chars and len(chunk) > 1:
                continue
            dur = chunk[-1]["e"] - chunk[0]["s"]
            c = abs(len(txt) - target_chars) * 0.55
            if dur < min_dur:
                c += (min_dur - dur) * 12.0
            c += _break_cost(words, j - 1)
            if best[i] + c < best[j]:
                best[j] = best[i] + c
                prev[j] = i
    out, j = [], n
    while j > 0:
        i = prev[j]
        out.append(words[i:j])
        j = i
    return out[::-1]


def cards_phrase(words, max_chars=None, max_words=None, max_gap=0.60,
                 target_chars=None, min_dur=0.42):
    """cards_sentence(), but each sentence is split on PHRASE boundaries.
    Budgets default to the floor's captions.cards (see split_phrase)."""
    groups, cur = [], []
    for w in words:
        brk = False
        if cur:
            p = cur[-1]
            if w["s"] - p["e"] > max_gap:
                brk = True
            if w.get("spk") and p.get("spk") and w["spk"] != p["spk"]:
                brk = True
            if p["w"].rstrip("\"\u201d')").endswith((".", "!", "?")):
                brk = True
        if brk:
            groups.append(cur); cur = []
        cur.append(w)
    if cur:
        groups.append(cur)
    out = []
    for g in groups:
        out.extend(split_phrase(g, max_chars, max_words, target_chars, min_dur))
    return out


def ass_time(t):
    h = int(t // 3600); m = int((t % 3600) // 60); s = t % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def _entrance(W, seam, sy, grow_ms=110, from_pct=88):
    """(anim_tags, pos_tag) for the current ENTRANCE mode.

    2026-08-29: he rejected every scale-based entrance - "I don't really want
    that pop in, pop out effect all fast like that" and then "I just don't like
    the animation". So the modes below are deliberately NOT variations on a
    scale pop; each uses a different property, and `none` is a real option.
    """
    C = f"\\pos({W//2},{seam})"
    if ENTRANCE == "none":
        return "", C                                    # hard cut. no movement.
    if ENTRANCE == "fade":
        return "\\fad(70,70)", C                        # opacity only
    if ENTRANCE == "lift":                              # rise into place + fade
        return ("\\fad(90,60)",
                f"\\move({W//2},{seam+20},{W//2},{seam},0,130)")
    if ENTRANCE == "blur":                              # defocus -> sharp
        return (f"\\fad({FADE_IN_MS},{FADE_OUT_MS})"
                f"\\blur{BLUR_PX}\\t(0,{BLUR_MS},\\blur0)"), C
    if ENTRANCE == "bounce":
        return (f"\\fscx72\\fscy{int(72*sy/100)}"
                f"\\t(0,90,\\fscx110\\fscy{int(110*sy/100)})"
                f"\\t(90,175,\\fscx100\\fscy{sy})", C)
    if ENTRANCE == "punch":
        return (f"\\fscx62\\fscy{int(62*sy/100)}"
                f"\\t(0,80,\\fscx100\\fscy{sy})", C)
    if ENTRANCE == "rise":
        return (f"\\fscx84\\fscy{int(84*sy/100)}"
                f"\\t(0,140,\\fscx100\\fscy{sy})",
                f"\\move({W//2},{seam+26},{W//2},{seam},0,140)")
    return (f"\\fscx{from_pct}\\fscy{int(from_pct*sy/100)}"
            f"\\t(0,{grow_ms},\\fscx100\\fscy{sy})", C)


def build_snap(cards_, path, W, H, seam, cap_px=None, scale_y=None,
               fill="&H00FFFFFF", grow_ms=110, from_pct=88):
    """Short, big, punchy cards that snap in - and NEVER spoil the next word.

    Measured 2026-08-29: the card "life. Exactly." painted both words at t=3.20
    while Judge Boyd was still saying "life". The defendant's "Exactly." at 3.88
    was legible 0.68s before she said it, so the reaction landed dead. His words:
    "it shows the word exactly like I already knew she was gonna say that ...
    that's where it really matters right there in those type of moments."

    So REVEAL gates every word on its own start time:
      reserve - full card laid out, unspoken words invisible. Nothing shifts.
      build   - only spoken words drawn. The line grows and re-centres.
      off     - old behaviour, whole card at once. Spoils reactions.

    The ENTRANCE animation plays on the first step of a card only. Re-snapping
    the line on every word is the "popping all big on every syllable" he
    already rejected.
    """
    cap_px = CAP_PX if cap_px is None else cap_px        # floor captions.size
    scale_y = SCALE_Y if scale_y is None else scale_y    # floor captions.scale_y
    ol = max(3, int(cap_px * 0.12))
    sh = max(2, int(cap_px * 0.055))
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Mid,{FONT},{cap_px},{fill},&H00000000,&HC0000000,0,0,0,0,100,{scale_y},0,0,1,{ol},{sh},5,40,40,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    starts = [c[0]["s"] for c in cards_]
    for i, c in enumerate(cards_):
        words = [x for x in c if x["w"].strip()]
        if not words:
            continue
        s_ = words[0]["s"]
        e_ = words[-1]["e"] + 0.26
        if i + 1 < len(cards_):
            e_ = min(e_, starts[i + 1])
        e_ = max(e_, s_ + 0.18)
        sy = scale_y
        anim, pos = _entrance(W, seam, sy, grow_ms, from_pct)

        if REVEAL == "off" or len(words) == 1:
            steps = [(s_, e_, " ".join(x["w"] for x in words))]
        else:
            steps = []
            for k, w in enumerate(words):
                t0 = s_ if k == 0 else w["s"]
                t1 = words[k + 1]["s"] if k + 1 < len(words) else e_
                if t1 <= t0:
                    continue
                if REVEAL == "reserve":
                    txt = " ".join(
                        x["w"] if j <= k
                        else "{\\alpha&HFF&}" + x["w"] + "{\\alpha&H00&}"
                        for j, x in enumerate(words))
                else:
                    txt = " ".join(x["w"] for x in words[:k + 1])
                steps.append((t0, t1, txt))
            if not steps:
                steps = [(s_, e_, " ".join(x["w"] for x in words))]

        for k, (t0, t1, txt) in enumerate(steps):
            tags = pos + (anim if k == 0 else "")
            lines.append(f"Dialogue: 0,{ass_time(t0)},{ass_time(t1)},Mid,,0,0,0,,"
                         f"{{{tags}}}{txt}")
    open(path, "w", encoding="utf-8").write(head + "\n".join(lines) + "\n")
    return len(lines)


def build_karaoke(cards_, path, W, H, seam, cap_px=None, scale_y=None,
                  base="&H00FFFFFF", hot="&H0009CBED"):
    """A STABLE line with the spoken word tracked in gold.

    Why not the fading-card version: cards of 3-4 words fading in and out every
    half second read as PULSING - the eye keeps re-acquiring a new block and
    nothing carries through. "It just doesn't feel alive" is that. The life in a
    good short caption comes from something MOVING across a line that stays put,
    not from the line itself appearing and disappearing.

    So: longer cards, no fade on the card, and one Dialogue per word where only
    the active word is gold. The line holds still; the emphasis travels.
    """
    cap_px = CAP_PX if cap_px is None else cap_px
    scale_y = SCALE_Y if scale_y is None else scale_y
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Mid,{FONT},{cap_px},{base},&H00000000,&HB4000000,0,0,0,0,100,{scale_y},0,0,1,{max(3,int(cap_px*0.13))},{max(2,int(cap_px*0.06))},5,40,40,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for ci, c in enumerate(cards_):
        for wi, w in enumerate(c):
            s_ = w["s"]
            e_ = c[wi + 1]["s"] if wi + 1 < len(c) else w["e"] + 0.22
            if e_ <= s_:
                continue
            parts = []
            for j, x in enumerate(c):
                t = x["w"]
                parts.append(f"{{\\c{hot}}}{t}{{\\c{base}}}" if j == wi else t)
            txt = " ".join(parts)
            lines.append(f"Dialogue: 0,{ass_time(s_)},{ass_time(e_)},Mid,,0,0,0,,"
                         f"{{\\pos({W//2},{seam})}}{txt}")
    open(path, "w", encoding="utf-8").write(head + "\n".join(lines) + "\n")
    return len(lines)


def build_ass(cards_, path, W, H, seam, cap_px=None, fill="&H00FFFFFF",
              scale_y=None, fade_ms=90):
    cap_px = CAP_PX if cap_px is None else cap_px
    scale_y = SCALE_Y if scale_y is None else scale_y
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Mid,{FONT},{cap_px},{fill},&H00000000,&HB4000000,0,0,0,0,100,{scale_y},0,0,1,{max(3,int(cap_px*0.13))},{max(2,int(cap_px*0.06))},5,40,40,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    # Smooth transitions. Two parts: every card carries a short \fad so it eases
    # in and out instead of snapping, and each card holds until the NEXT one
    # starts so there is no dead frame where the line has vanished and nothing
    # has replaced it. Hard cuts between cards are what read as jumpy.
    lines = []
    starts = [c[0]["s"] for c in cards_]
    for i, c in enumerate(cards_):
        txt = " ".join(x["w"] for x in c).strip()
        if not txt:
            continue
        s_ = c[0]["s"]
        e_ = c[-1]["e"] + 0.30
        if i + 1 < len(cards_):
            e_ = min(e_, starts[i + 1])          # butt up to the next card
        e_ = max(e_, s_ + 0.20)
        lines.append(f"Dialogue: 0,{ass_time(s_)},{ass_time(e_)},Mid,,0,0,0,,"
                     f"{{\\fad({fade_ms},{fade_ms})\\pos({W//2},{seam})}}{txt}")
    open(path, "w", encoding="utf-8").write(head + "\n".join(lines) + "\n")
    return len(lines)


def selftest():
    """The ASS style line and the entrance tags come from the floor, and the
    check can fail: the same builders, pointed at other values, produce other
    lines. No ffmpeg - only the .ass text is inspected."""
    import re
    import tempfile
    global ENTRANCE, REVEAL, FONT, CAP_PX, SCALE_Y
    ok = True

    def chk(label, got, want):
        nonlocal ok
        hit = (got == want)
        ok &= hit
        print(f"  {'OK  ' if hit else 'MISS'}  {label:52} -> {got!r} (want {want!r})")
        return hit

    floor = _SE.FLOOR["captions"]
    W_, H_ = _SE.W, _SE.H
    seam = int(H_ * _SE.SEAM_FRAC)
    two = [[{"s": 1.00, "e": 1.40, "w": "one"}, {"s": 1.60, "e": 2.00, "w": "two"}]]
    keep = (ENTRANCE, REVEAL, FONT, CAP_PX, SCALE_Y)
    try:
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.ass")

            def style_and_events():
                txt = open(p, encoding="utf-8").read()
                st = next(l for l in txt.splitlines() if l.startswith("Style: Mid,"))
                ev = [l for l in txt.splitlines() if l.startswith("Dialogue:")]
                return st, ev

            print(f"C1 floor says font={floor['font']} size={floor['size']} "
                  f"scale_y={floor['scale_y']} entrance={floor['entrance_mode']} "
                  f"reveal={floor['reveal']}")
            chk("C1 module constants are the floor's",
                (FONT, CAP_PX, SCALE_Y, ENTRANCE, REVEAL),
                (floor["font"], floor["size"], floor["scale_y"],
                 floor["entrance_mode"], floor["reveal"]))
            for name, fn in (("build_snap", build_snap), ("build_karaoke", build_karaoke),
                             ("build_ass", build_ass)):
                fn(two, p, W_, H_, seam)
                st, ev = style_and_events()
                chk(f"C1 {name} style carries floor font+size",
                    st.startswith(f"Style: Mid,{floor['font']},{floor['size']},"), True)
                chk(f"C1 {name} style carries floor scale_y",
                    f",100,{floor['scale_y']}," in st, True)
                chk(f"C1 {name} events sit on the seam",
                    all(f"\\pos({W_ // 2},{seam})" in l for l in ev) and bool(ev), True)

            # C2 the blur entrance is assembled from the floor's numbers and
            # equals the prose 'fade' + 'entrance' strings the floor states
            build_snap(two, p, W_, H_, seam)
            st, ev = style_and_events()
            want_tags = (f"\\fad({floor['fade_ms']['in']},{floor['fade_ms']['out']})"
                         f"\\blur{floor['blur']['px']}\\t(0,{floor['blur']['ms']},\\blur0)")
            chk("C2 first event carries the floor's blur entrance", want_tags in ev[0], True)
            chk("C2 tags equal the floor's prose 'fade' + 'entrance'",
                want_tags == floor["fade"] + floor["entrance"].split(" - ", 1)[1], True)
            chk("C2 no scale tag (\\fscx) in a blur entrance",
                any("\\fscx" in l for l in ev), False)

            # C3 R34: with the floor's reveal, 'two' is hidden while 'one' is spoken
            first = ev[0]
            chk("C3 R34 first event starts at the first word",
                first.split(",")[1], ass_time(1.00))
            chk("C3 R34 floor reveal is not 'off'", REVEAL != "off", True)
            chk("C3 R34 'two' is not legible before it is spoken",
                ("{\\alpha&HFF&}two" in first) or ("two" not in first), True)

            # NEGATIVE CONTROLS - the same checks must FAIL on other values
            FONT, CAP_PX, SCALE_Y = "Impact", 96, 100
            build_snap(two, p, W_, H_, seam)
            st, _ = style_and_events()
            chk("C1 control: Impact/96/100 does NOT read as the floor",
                st.startswith(f"Style: Mid,{floor['font']},{floor['size']},")
                or f",100,{floor['scale_y']}," in st, False)
            FONT, CAP_PX, SCALE_Y = keep[2], keep[3], keep[4]
            ENTRANCE = "rise"
            build_snap(two, p, W_, H_, seam)
            _, ev = style_and_events()
            chk("C2 control: entrance 'rise' DOES emit a scale tag",
                any("\\fscx" in l for l in ev), True)
            ENTRANCE = keep[0]
            REVEAL = "off"
            build_snap(two, p, W_, H_, seam)
            _, ev = style_and_events()
            chk("C3 control: reveal 'off' paints 'two' at the first word",
                "one two" in ev[0] and "\\alpha&HFF&" not in ev[0], True)
    finally:
        ENTRANCE, REVEAL, FONT, CAP_PX, SCALE_Y = keep
    print("SELFTEST_PASS caption_short" if ok else "SELFTEST_FAIL caption_short")
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    ap = argparse.ArgumentParser()
    ap.add_argument("video"); ap.add_argument("words"); ap.add_argument("out")
    ap.add_argument("--audio", default=None, help="replace audio with this wav")
    ap.add_argument("--cap", type=int, default=CAP_PX, help="floor captions.size")
    ap.add_argument("--chars", type=int, default=22)
    a = ap.parse_args()

    seam, H, W = find_seam(a.video)
    print(f"  frame {W}x{H}   seam found at y={seam} ({seam/H:.3f} H)")
    words = json.load(open(a.words))
    cs = cards(words, max_chars=a.chars)
    n = build_ass(cs, "_caps.ass", W, H, seam, a.cap)
    longest = max((" ".join(x["w"] for x in c) for c in cs), key=len)
    print(f"  {len(words)} words -> {n} cards, longest \"{longest}\" ({len(longest)} chars)")

    vf = f"subtitles=_caps.ass:fontsdir={FONTDIR.replace(chr(92), '/')}"
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", a.video]
    if a.audio:
        cmd += ["-i", a.audio, "-map", "0:v", "-map", "1:a"]
    cmd += ["-vf", vf, "-c:v", "libx264", "-preset", "slow", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", a.out]
    subprocess.run(cmd, check=True)
    os.remove("_caps.ass")
    print(f"  wrote {a.out}")


if __name__ == "__main__":
    main()
