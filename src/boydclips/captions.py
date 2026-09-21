# -*- coding: utf-8 -*-
"""Kinetic captions for SHORTS_EDITOR_V2.

Nathan, 2026-09-06 (fifth and sixth pass): premium short-form kinetic
captions, not subtitles — and captions for MEANING, not for every
disfluency. The rules, which this module makes structural:

    ONE LINE ONLY      every phrase fits one line at the configured font; a
                       phrase that does not fit is SPLIT, never wrapped and
                       never shrunk (widths MEASURED with the font file);
    SPEAKER PURITY     a phrase never holds words from two speakers — the
                       verified speaker label is an INPUT constraint: phrases
                       are planned inside one speaker run at a time, so a
                       cross-speaker card cannot be produced;
    DISPLAY CLEANUP    the audio is untouched; the caption text may omit
                       purely non-semantic disfluencies — fillers (um, uh),
                       immediate accidental repetitions ("I I"), restarts
                       ("I just I don't" → "I just don't"), a trailing
                       abandoned fragment that ends in a verbal stumble —
                       and never negation, numbers, names, admissions,
                       denials or intentional emphasis. Every displayed word
                       maps back to its source word (the AUDIT); nothing is
                       invented;
    CHUNK BUILD        a phrase is revealed in 1–3 natural micro-phrases,
                       not word by word; the newly revealed chunk is warm
                       yellow with one short pop-in (88 → 105 → 100 %,
                       ~110 ms), earlier text is white and never moves;
                       about 1–2 visual changes per second on average;
    CLEAR              a completed phrase holds briefly and clears before
                       the next thought; at a speaker change the old text is
                       gone and the new speaker starts from empty;
    READABLE PHRASES   2–5 words typically, semantic units first, no
                       dangling glue ends (to / that / because / and / the /
                       a subject pronoun) unless the delivery pauses there.

THE AUTHORITATIVE WORD STREAM: kept words + final output timestamps +
verified speaker (`shorts_editor.word_stream_for`) → display cleanup with
audit → speaker runs → phrase breaks → reveal chunks → ASS.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Sequence

from .censor import censor
from .render import strip_caption_artifact

RULESET = "CAPTIONS_V3_KINETIC"

# ---------------------------------------------------------------- lexicons

NEVER_SPLIT: set[tuple[str, str]] = {
    ("judge", "boyd"), ("your", "honor"), ("your", "honour"), ("yes", "ma'am"), ("no", "ma'am"),
    ("yes", "sir"), ("no", "sir"), ("yes", "judge"), ("no", "judge"), ("ms", "jimenez"),
}
# verb + particle: "BROUGHT | BACK" is not a phrase boundary
_PARTICLE_VERBS = {
    ("bring", "brought", "come", "came", "go", "went", "get", "got", "sent", "send", "take", "took"): ("back", "in", "out", "away"),
    ("show", "showed", "pick", "picked", "set", "give", "gave", "lock", "locked", "mess", "messed", "screw", "screwed",
     "end", "ended", "wake", "woke", "sign", "signed", "stand", "stood", "shut", "hold", "held", "make", "made", "grow", "grew"): ("up",),
    ("figure", "figured", "find", "found", "get", "got", "turn", "turned", "throw", "threw", "walk", "walked", "run", "ran"): ("out", "in", "away", "off", "over"),
    ("sit", "sat", "calm", "settle", "settled", "turn", "turned"): ("down",),
}
for _verbs, _parts in _PARTICLE_VERBS.items():
    for _v in _verbs:
        for _p in _parts:
            NEVER_SPLIT.add((_v, _p))
AUXILIARIES = {
    "am", "is", "are", "was", "were", "be", "been", "being", "do", "does", "did", "don't", "doesn't",
    "didn't", "have", "has", "had", "haven't", "hasn't", "hadn't", "can", "can't", "cannot", "could",
    "couldn't", "will", "won't", "would", "wouldn't", "should", "shouldn't", "shall", "may", "might",
    "must", "gonna", "gotta", "wanna", "ain't", "wasn't", "weren't", "isn't", "aren't", "i'm", "you're",
    "he's", "she's", "we're", "they're", "i've", "you've", "we've", "they've", "i'd", "you'd", "i'll",
    "you'll", "we'll", "they'll", "that's", "there's", "it's", "let",
}
ARTICLES = {"a", "an", "the", "this", "that", "these", "those", "my", "your", "his", "her", "our",
            "their", "its", "some", "any", "every", "each", "no"}
PREPOSITIONS = {"on", "in", "at", "to", "for", "of", "with", "from", "by", "into", "about", "under",
                "over", "without", "before", "after", "through", "against", "between", "toward", "towards",
                "during", "until", "upon", "onto"}
SUBJECT_PRONOUNS = {"i", "you", "we", "they", "he", "she", "it"}
ALWAYS_SUBJECT = {"i", "we", "they", "he", "she"}
CLAUSE_OPENERS = {"and", "but", "so", "if", "when", "because", "that", "or", "then", "while", "unless", "until", "why", "how", "what", "where"}
GLUE_END = {"the", "and", "to", "of", "for", "because", "that", "a", "an", "or", "but", "with", "in",
            "on", "at", "my", "your", "his", "her", "their", "our", "so", "if", "when", "as", "than", "very",
            "who", "which", "while", "unless", "until"} | SUBJECT_PRONOUNS
PHRASE_OPENERS = {"that", "because", "but", "and", "so", "when", "which", "who", "if", "then", "well",
                  "now", "okay", "all", "guess", "why", "how", "what", "where", "unless", "until", "while"}
FUNCTION_WORDS = (AUXILIARIES | ARTICLES | PREPOSITIONS | GLUE_END | SUBJECT_PRONOUNS
                  | {"me", "him", "them", "us", "there", "here", "just", "well", "okay", "yeah", "no", "yes",
                     "not", "then", "really", "even", "like", "oh", "all", "any", "it's", "that's"})
FILLER_TOKEN = re.compile(r"^(um+|uh+|uh-huh|mm+|hmm+|er+|ah+|huh)[,.!?]*$", re.I)
RESTART_PRONOUNS = {"i", "you", "we", "they", "he", "she", "it", "my", "the", "i'm", "we're", "you're", "and"}
EMPHASIS_KEEP = {"no", "yes", "never", "not", "right", "wrong", "yeah"}      # repeated as an ANSWER = emphasis
# NEGATION SAFETY (Nathan, 2026-09-06): semantic negation is protected. No
# rule removes an isolated negation as a stutter or duplicate; a negation
# leaves the display only inside a WHOLE abandoned fragment (see
# clean_disfluencies) or as the earlier copy of an exact repeated n-gram whose
# kept copy carries the same negation ("I don't I don't have" -> "I don't have").
NEGATIONS = {"no", "not", "don't", "didn't", "doesn't", "wasn't", "weren't", "can't", "cannot", "couldn't", "won't",
             "wouldn't", "shouldn't", "isn't", "aren't", "ain't", "hasn't", "haven't", "hadn't", "never", "nothing",
             "nobody", "none", "nowhere", "neither", "nor", "mustn't", "needn't", "daren't"}
# a trailing fragment may only be omitted whole when it HANGS OFF the completed
# statement: it opens with a connector, not with a subject or a negation
FRAGMENT_OPENERS = {"to", "that", "and", "but", "or", "because", "so", "if", "when", "the", "a", "an", "which", "who",
                    "then", "of", "for", "with", "in", "on", "at", "from", "by", "about", "into", "like", "as"}
STUMBLE_ENDINGS = {"no", "yeah", "okay", "well", "um", "uh", "like", "so"}
TERMINAL = (".", "!", "?")
ANY_PUNCT = (".", ",", "!", "?", ";", ":", "…")
ABBREVIATIONS = {"mr.", "mrs.", "ms.", "dr.", "jr.", "sr.", "st.", "vs.", "no.", "hon.", "esq.", "inc.", "co."}
_NUMBER = re.compile(r"^\$?\d[\d,.]*%?$")
NUMBER_WORDS = {"zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven",
                "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty",
                "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety", "hundred", "thousand", "million",
                "first", "second", "third", "fourth", "fifth", "once", "twice", "half", "dozen"}

DEFAULTS: dict[str, Any] = {
    "preset": "kinetic_chunk",
    "mode": "kinetic",           # kinetic | static
    "font": "Anton",
    "font_size": 96,             # visual polish 2026-09-06: 84 -> 96 (+14 % cap height); wider phrases split, never shrink
    "canvas_w": 1080,
    "safe_width": 980,           # 1080 - 2 x 50 side margins; measured advance width must fit
    "outline": 6,
    "shadow": 2,
    "rail_x": 540,
    "rail_y": 960,
    "target_words": 4.0,
    "min_words": 2,
    "max_words": 6,
    "hard_max_words": 7,
    "min_phrase_s": 0.5,
    "max_phrase_s": 3.5,
    "pause_break_s": 0.35,
    "hold_s": 1.0,
    "gap_ms": 60,
    "pop_ms": 110,               # the whole entrance
    "pop_from": 92,              # eased overshoot: 92 % -> 106 % at pop_rise_ms -> 100 % at pop_ms
    "pop_peak": 106,
    "pop_rise_ms": 55,
    "pop_fade_ms": 60,           # opacity 0 -> 100 % over the first 60 ms of the new chunk
    "ease_rise": 0.6,            # \t accel < 1 = ease-out (fast start, soft landing on the overshoot)
    "ease_settle": 1.3,          # \t accel > 1 = ease-in into the rest size (no bounce)
    "ease_fade": 0.7,
    "max_chunks": 3,             # reveal steps per phrase
    "min_chunk_words": 2,
    "density_target": 1.5,       # visual changes per second the chunking aims at
    "density_max": 2.5,          # QC ceiling on the clip average
    "clean_disfluencies": True,
    "uppercase": True,
    "speaker_colors": {},
}
FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"

# Named choices keep timing, the divider rail and face-safe layout unchanged.
# Only typography, phrase density and reveal treatment vary.
CAPTION_STYLE_PRESETS: dict[str, dict[str, Any]] = {
    "kinetic_chunk": {},
    "clean_phrase": {
        "mode": "static", "font": "Anton", "font_size": 82,
        "target_words": 5.0, "min_words": 3, "max_words": 7,
        "hard_max_words": 9, "max_chunks": 1, "density_target": 0.55,
        "speaker_colors": {"boyd": "&H00FFFFFF", "defendant": "&H003FD2FF"},
    },
    "bold_phrase": {
        "mode": "static", "font": "Anton", "font_size": 100,
        "target_words": 4.0, "min_words": 2, "max_words": 6,
        "hard_max_words": 7, "max_chunks": 1, "density_target": 0.7,
        "speaker_colors": {"boyd": "&H00FFFFFF", "defendant": "&H003FD2FF"},
    },
}


def _cfg(style: dict[str, Any] | None) -> dict[str, Any]:
    requested = str((style or {}).get("preset", DEFAULTS["preset"]))
    if requested not in CAPTION_STYLE_PRESETS:
        raise ValueError(f"unknown caption preset: {requested}")
    out = copy.deepcopy(DEFAULTS)
    out.update(copy.deepcopy(CAPTION_STYLE_PRESETS[requested]))
    for k, v in (style or {}).items():
        if k in out and v is not None:
            out[k] = copy.deepcopy(v)
    out["preset"] = requested
    return out


def resolve_style(style: dict[str, Any] | None = None) -> dict[str, Any]:
    """Public resolved style used by planning and ASS rendering."""
    return _cfg(style)


def _norm(w: str) -> str:
    return w.strip().strip('.,!?";:“”\'()').lower()


def _ends_terminal(w: str) -> bool:
    core = w.rstrip('"”\')')
    if core.lower() in ABBREVIATIONS:
        return False
    return core.endswith(TERMINAL)


def _ends_punct(w: str) -> bool:
    return w.rstrip('"”\')').endswith(ANY_PUNCT)


# ---------------------------------------------------------------- the word stream


def normalize_stream(words: Sequence[Any]) -> list[dict[str, Any]]:
    """Accept [(t, w)] tuples or stream dicts; return stream dicts with
    `i` (source index), `t` (output seconds), `w` (raw token), `speaker`."""
    out: list[dict[str, Any]] = []
    for k, x in enumerate(words):
        if isinstance(x, dict):
            out.append({"i": x.get("i", k), "t": float(x["t"]), "w": str(x["w"]),
                        "speaker": x.get("speaker"), "src_t": x.get("src_t"), "src": list(x.get("src", [x.get("i", k)]))})
        else:
            t, w = x[0], x[1]
            out.append({"i": k, "t": float(t), "w": str(w), "speaker": None, "src_t": None, "src": [k]})
    return out


def display_tokens(stream: Sequence[dict[str, Any]], upper: bool = True) -> list[str]:
    """What each word looks like on screen: artifacts stripped, censored
    (CONTENT_SPEC §9), cased. Never paraphrased."""
    out = []
    for x in stream:
        tok = censor(strip_caption_artifact(x["w"]).strip())
        out.append(tok.upper() if upper else tok)
    return out


def speaker_runs(stream: Sequence[dict[str, Any]]) -> list[tuple[int, int, Any]]:
    """[(start, end, speaker)] — maximal runs of one verified speaker label.
    Hard boundaries: no phrase is ever planned across them."""
    runs: list[tuple[int, int, Any]] = []
    for k, x in enumerate(stream):
        spk = x.get("speaker")
        if runs and runs[-1][2] == spk:
            runs[-1] = (runs[-1][0], k + 1, spk)
        else:
            runs.append((k, k + 1, spk))
    return runs


# ---------------------------------------------------------------- display cleanup (audited)


def _is_content(tok: str) -> bool:
    n = _norm(tok)
    if not n:
        return False
    if _NUMBER.match(n) or n in NUMBER_WORDS:
        return True
    if n in FUNCTION_WORDS or FILLER_TOKEN.match(n):
        return False
    return True


def _is_name(stream: Sequence[dict[str, Any]], k: int) -> bool:
    """A capitalised token that is not sentence-initial reads as a name."""
    w = strip_caption_artifact(stream[k]["w"]).strip()
    if not w or not w[0].isupper() or _norm(w) in ("i", "i'm", "i've", "i'd", "i'll"):
        return False
    if _norm(w) in FUNCTION_WORDS or _norm(w) in EMPHASIS_KEEP or FILLER_TOKEN.match(w):
        return False                      # "didn't No, no." — the ASR capitalises a stumble, that is not a name
    if k == 0 or _ends_terminal(stream[k - 1]["w"]) or stream[k - 1].get("speaker") != stream[k].get("speaker"):
        return False
    return True


def clean_disfluencies(stream: Sequence[dict[str, Any]], style: dict[str, Any] | None = None
                       ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Conservative DISPLAY-ONLY cleanup of the word stream. Returns
    (display_stream, audit). The audio is untouched; every displayed word
    keeps its source index in `src`; every omitted word is listed with a
    reason. Rules, per speaker run, never across one:

      filler              um / uh / er / mm …
      repeat              an immediate exact repetition of 1–3 words keeps the
                          completed (later) occurrence — never numbers or
                          names, and never "no"/"yes"/"never"/"not" when they
                          open an answer (that is emphasis: "No, no, I didn't")
      restart             "I just I don't" → "I just don't": a subject pronoun
                          restarting within two words
      abandoned_fragment  a trailing fragment at the END of a speaker run —
                          mid-sentence, 2–6 function words, no content word,
                          opening with a connector (to / that / and / because
                          …), ending in a verbal stumble ("… to that I didn't
                          no, no.") — is not a proposition; omitted WHOLE, the
                          original words and any negation inside recorded in
                          the audit. A tail that opens with a subject or a
                          negation ("no, I didn't") is an answer and stays.

    Negation safety: a negation token is never removed by the filler,
    restart or single-word repeat rules; "I didn't do it" cannot become
    "I did it", "No, I didn't" cannot lose its negation. Enforced by the
    rules and re-checked at the end (a violation restores the word).
    """
    cfg = _cfg(style)
    src = normalize_stream(stream)
    n = len(src)
    keep = [True] * n
    reason: list[str | None] = [None] * n
    note: list[str] = [""] * n
    if not cfg.get("clean_disfluencies", True):
        display = [dict(x, src=[x["i"]]) for x in src]
        audit = [{"i": x["i"], "w": x["w"], "kept": True, "reason": None, "note": ""} for x in src]
        return display, audit
    for lo, hi, _spk in speaker_runs(src):
        # 1. fillers
        for k in range(lo, hi):
            if FILLER_TOKEN.match(strip_caption_artifact(src[k]["w"]).strip() or "x"):
                keep[k], reason[k] = False, "filler"

        def alive() -> list[int]:
            return [k for k in range(lo, hi) if keep[k]]

        # 2. immediate repeats of 1-3 words (keep the completed, later one)
        changed = True
        passes = 0
        while changed and passes < 4:
            changed = False
            passes += 1
            ids = alive()
            toks = [_norm(src[k]["w"]) for k in ids]
            for size in (3, 2, 1):
                p = 0
                while p + 2 * size <= len(ids):
                    if toks[p:p + size] == toks[p + size:p + 2 * size] and all(toks[p:p + size]):
                        first = ids[p:p + size]
                        protected = False
                        for k in first:
                            nn = _norm(src[k]["w"])
                            if _NUMBER.match(nn) or nn in NUMBER_WORDS or _is_name(src, k):
                                protected = True      # numbers and names are never collapsed
                            if size == 1 and (nn in EMPHASIS_KEEP or nn in NEGATIONS):
                                protected = True      # "no, no" / "never never": an isolated negation is never a duplicate
                        if not protected:
                            for k in first:
                                keep[k], reason[k] = False, "repeat"
                                note[k] = f"kept the later {' '.join(src[j]['w'] for j in ids[p + size:p + 2 * size])!r}"
                            changed = True
                            break
                    p += 1
                if changed:
                    break
        # 3. pronoun restart: "I just I don't" -> "I just don't"
        ids = alive()
        for q in range(2, len(ids)):
            a, b, c = ids[q - 2], ids[q - 1], ids[q]
            mid = _norm(src[b]["w"])
            if keep[c] and _norm(src[c]["w"]) == _norm(src[a]["w"]) and _norm(src[c]["w"]) in RESTART_PRONOUNS \
                    and not _ends_punct(src[b]["w"]) and mid not in RESTART_PRONOUNS \
                    and mid not in AUXILIARIES and mid not in NEGATIONS:      # "I didn't I did" is a correction, not a restart
                keep[c], reason[c] = False, "restart"
                note[c] = f"restart of {src[a]['w']!r} after {src[b]['w']!r}"
        # 4. abandoned trailing fragment at the end of the run
        ids = alive()
        if len(ids) >= 4:
            tail: list[int] = []
            for k in reversed(ids):
                if _is_content(src[k]["w"]) or _is_name(src, k):
                    break
                tail.insert(0, k)
            if 2 <= len(tail) <= 6 and len(tail) < len(ids):
                before = ids[len(ids) - len(tail) - 1]
                first_norm = _norm(src[tail[0]]["w"])
                last_norm = _norm(src[tail[-1]]["w"])
                mid_sentence = not _ends_terminal(src[before]["w"])          # 1. incomplete: hangs off the statement
                stumble = last_norm in STUMBLE_ENDINGS                          # 1. garbled: ends in a verbal stumble
                hangs_off = first_norm in FRAGMENT_OPENERS                      # 3. the completed statement before it is intact
                complete_before = _is_content(src[before]["w"]) or _is_name(src, before)
                # 2. no proposition: no content word (checked by the tail scan) and no answer-like opening
                if mid_sentence and stumble and hangs_off and complete_before:
                    original = " ".join(src[j]["w"] for j in tail)
                    negs = [src[k]["w"] for k in tail if _norm(src[k]["w"]) in NEGATIONS]
                    for k in tail:
                        keep[k], reason[k] = False, "abandoned_fragment"
                        note[k] = f"whole fragment omitted, original: {original!r}" + (f"; negation inside: {negs}" if negs else "")
        # negation safety re-check: a negation may leave only inside a whole
        # fragment or as the earlier copy of an exact repeat (its twin kept)
        for k in range(lo, hi):
            if keep[k] or _norm(src[k]["w"]) not in NEGATIONS:
                continue
            if reason[k] == "abandoned_fragment":
                continue
            if reason[k] == "repeat":
                nn = _norm(src[k]["w"])
                later = [j for j in range(k + 1, hi) if keep[j] and _norm(src[j]["w"]) == nn]
                if later:
                    continue
            keep[k], reason[k], note[k] = True, None, ""                        # restored: never drop a negation
    display: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    for k, x in enumerate(src):
        audit.append({"i": x["i"], "w": x["w"], "t": x["t"], "speaker": x.get("speaker"), "kept": keep[k],
                      "reason": reason[k], "note": note[k], "display_index": len(display) if keep[k] else None})
        if keep[k]:
            display.append(dict(x, src=[x["i"]]))
    return display, audit


def map_hard_breaks(hard_breaks: Sequence[int] | None, audit: Sequence[dict[str, Any]]) -> set[int]:
    """Source-stream break indices → display-stream indices (the first
    displayed word at or after the break)."""
    out: set[int] = set()
    for h in (hard_breaks or []):
        for a in audit:
            if a["kept"] and a["display_index"] is not None and int(a["i"]) >= int(h):
                if a["display_index"] > 0:
                    out.add(int(a["display_index"]))
                break
    return out


# ---------------------------------------------------------------- measured widths


@lru_cache(maxsize=8)
def _font(name: str, size: int):
    try:
        from PIL import ImageFont
    except Exception:  # pragma: no cover
        return None
    for cand in (FONT_DIR / f"{name}-Regular.ttf", FONT_DIR / f"{name}.ttf", FONT_DIR / f"{name}-Var.ttf"):
        if cand.exists():
            try:
                return ImageFont.truetype(str(cand), size)
            except Exception:  # pragma: no cover
                return None
    return None


def text_width(text: str, style: dict[str, Any] | None) -> float:
    cfg = _cfg(style)
    font = _font(str(cfg["font"]), int(cfg["font_size"]))
    if font is not None:
        return float(font.getlength(text))
    return 0.45 * int(cfg["font_size"]) * len(text)


def text_ink_box(text: str, style: dict[str, Any] | None) -> tuple[float, float, float, float]:
    """The INK bounding box of `text` relative to the pen origin, in pixels:
    (left, top, right, bottom). Unlike text_width (advance width) this is
    what the eye sees — the first glyph's left side bearing and the last
    glyph's right edge — so a phrase can be centred on its visual box."""
    cfg = _cfg(style)
    font = _font(str(cfg["font"]), int(cfg["font_size"]))
    if font is not None:
        l, t, r, b = font.getbbox(text)
        return float(l), float(t), float(r), float(b)
    w = text_width(text, cfg)
    return 0.0, 0.0, w, float(cfg["font_size"])


def caption_origin(card: dict[str, Any], style: dict[str, Any] | None) -> dict[str, Any]:
    """Where the COMPLETED phrase's left edge goes so that its visual box —
    ink plus the symmetric outline plus the shadow that hangs off the right
    — is centred on rail_x. Every reveal state of the phrase uses this same
    origin; earlier words never move. Returns
    {x_left, ink_left, ink_right, visual_width, predicted_center}."""
    cfg = _cfg(style)
    rail_x = float(cfg.get("rail_x", 540))
    outline = float(cfg.get("outline", 6))
    shadow = float(cfg.get("shadow", 2))
    l, _t, r, _b = text_ink_box(card["text"], cfg)
    visual_left = l - outline                     # relative to the pen origin
    visual_right = r + outline + shadow
    x_left = rail_x - (visual_left + visual_right) / 2.0
    return {"x_left": int(round(x_left)), "ink_left": round(l, 1), "ink_right": round(r, 1),
            "visual_width": round(visual_right - visual_left, 1),
            "predicted_center": round(int(round(x_left)) + (visual_left + visual_right) / 2.0, 1)}


def width_source(style: dict[str, Any] | None) -> str:
    cfg = _cfg(style)
    return "measured (PIL, %s-Regular.ttf)" % cfg["font"] if _font(str(cfg["font"]), int(cfg["font_size"])) else "estimated (0.45 em/char)"


# ---------------------------------------------------------------- boundaries and costs


def _gap_after(stream: Sequence[dict[str, Any]], i: int, hold_s: float = 0.6) -> float:
    if i + 1 >= len(stream):
        return 10.0
    span = stream[i + 1]["t"] - stream[i]["t"]
    return max(0.0, span - min(hold_s, span * 0.5))


def boundary_forbidden(stream: Sequence[dict[str, Any]], i: int, pause_break_s: float) -> str | None:
    """Why a phrase may NOT end after word i (None = it may). A speaker
    change after i is always allowed (it is required)."""
    if i + 1 >= len(stream):
        return None
    if stream[i].get("speaker") != stream[i + 1].get("speaker"):
        return None
    a, b = _norm(stream[i]["w"]), _norm(stream[i + 1]["w"])
    if (a, b) in NEVER_SPLIT:
        return f"never split {a!r} {b!r}"
    if _ends_punct(stream[i]["w"]):
        return None
    if _gap_after(stream, i) >= pause_break_s:
        return None
    if a in AUXILIARIES and b not in ARTICLES and b not in PREPOSITIONS and not b.endswith("?"):
        return f"auxiliary {a!r} attaches to {b!r}"
    if a in ARTICLES and b not in ARTICLES and b not in PREPOSITIONS and b not in AUXILIARIES:
        return f"article {a!r} attaches to {b!r}"
    if a in PREPOSITIONS and b not in PREPOSITIONS and b not in AUXILIARIES:
        return f"preposition {a!r} attaches to {b!r}"
    if a in ALWAYS_SUBJECT:
        return f"subject {a!r} dangles before {b!r}"                 # "... TO THAT I" | "DIDN'T"
    if a in ("you", "it"):
        # subject or object? "DID YOU | STOP" and "IF YOU | DON'T" dangle;
        # "CAN YOU DO IT | BEFOREHAND?" and "TOLD YOU | THAT" do not
        prev = _norm(stream[i - 1]["w"]) if i > 0 and stream[i - 1].get("speaker") == stream[i].get("speaker") else ""
        prev2 = _norm(stream[i - 2]["w"]) if i > 1 and stream[i - 2].get("speaker") == stream[i].get("speaker") else ""
        inverted = prev in AUXILIARIES and prev2 not in SUBJECT_PRONOUNS
        if b in AUXILIARIES or inverted or prev in CLAUSE_OPENERS or not prev:
            return f"subject {a!r} dangles before {b!r}"
    return None


def boundary_cost(stream: Sequence[dict[str, Any]], i: int, cfg: dict[str, Any]) -> float:
    if i + 1 >= len(stream):
        return 0.0
    tok = stream[i]["w"].rstrip('"”\')')
    a, b = _norm(stream[i]["w"]), _norm(stream[i + 1]["w"])
    c = 4.0
    if tok.endswith(TERMINAL):
        c -= 9.0
    elif tok.endswith((",", ";", ":", "…")):
        c -= 5.0
    gap = _gap_after(stream, i)
    c -= min(gap, 0.8) * 8.0
    if b in PHRASE_OPENERS:
        c -= 2.5
    if a in GLUE_END and gap < float(cfg["pause_break_s"]):
        c += 9.0
    return c


def phrase_cost(stream: Sequence[dict[str, Any]], tokens: Sequence[str], start: int, end: int,
                cfg: dict[str, Any]) -> float | None:
    """Cost of the phrase [start, end); None when it cannot be shown on one
    line (FIT) or exceeds hard_max_words."""
    n = end - start
    if n <= 0 or n > int(cfg["hard_max_words"]):
        return None
    if text_width(" ".join(tokens[start:end]), cfg) > float(cfg["safe_width"]):
        return None
    c = 0.0
    lo, hi = int(cfg["min_words"]), int(cfg["max_words"])
    if n < lo:
        c += (lo - n) * 5.0
    elif n > hi:
        c += (n - hi) * 4.0
    c += abs(n - float(cfg["target_words"])) * 0.8
    # the phrase's LIFE on the rail: until the next phrase of the same
    # speaker replaces it, or the hold after its last word
    if end < len(stream) and stream[end].get("speaker") == stream[end - 1].get("speaker"):
        dur = min(stream[end]["t"] - stream[start]["t"], (stream[end - 1]["t"] - stream[start]["t"]) + float(cfg["hold_s"]))
    else:
        dur = (stream[end - 1]["t"] - stream[start]["t"]) + float(cfg["hold_s"])
    if dur < 0.35:
        c += 15.0                                     # a flicker: "WHY" for 0.2 s is not a caption
    elif dur < float(cfg["min_phrase_s"]):
        c += (float(cfg["min_phrase_s"]) - dur) * 12.0
    if dur > float(cfg["max_phrase_s"]):
        c += (dur - float(cfg["max_phrase_s"])) * 3.0
    if n == 1 and end < len(stream) and stream[end - 1].get("speaker") == stream[end].get("speaker") \
            and _gap_after(stream, end - 1) < float(cfg["pause_break_s"]):
        c += 6.0
    if n > 1 and start > 0 and _ends_terminal(stream[start]["w"]):
        c += 8.0                                      # must not open on the previous sentence's tail
    for i in range(start, end - 1):
        if _ends_terminal(stream[i]["w"]):
            return None                               # a sentence never ends inside a phrase: no "THAT. WHY"
    if not any(_is_content(stream[i]["w"]) for i in range(start, end)) and n > 1:
        c += 6.0                                      # readability: a phrase of pure function words
    return c


# ---------------------------------------------------------------- the card


@dataclass
class Card:
    start: int
    end: int

    def as_dict(self, stream: Sequence[dict[str, Any]], tokens: Sequence[str], style: dict[str, Any]) -> dict[str, Any]:
        toks = [tokens[i] for i in range(self.start, self.end)]
        text = " ".join(toks)
        return {
            "start": self.start, "end": self.end,
            "speaker": stream[self.start].get("speaker"),
            "words": [(round(stream[i]["t"], 3), stream[i]["w"]) for i in range(self.start, self.end)],
            "src": [list(stream[i].get("src", [stream[i]["i"]])) for i in range(self.start, self.end)],
            "tokens": toks,
            "lines": [text],
            "text": text,
            "width_px": round(text_width(text, style), 1),
            "start_s": round(stream[self.start]["t"], 3),
            "end_s": round(stream[self.end - 1]["t"], 3),
        }


# ---------------------------------------------------------------- the planner


def _plan_run(stream: Sequence[dict[str, Any]], tokens: Sequence[str], lo: int, hi: int,
              hard: set[int], cfg: dict[str, Any]) -> list[Card]:
    n = hi - lo
    if n <= 0:
        return []
    INF = float("inf")
    best = [INF] * (n + 1)
    prev = [-1] * (n + 1)
    best[0] = 0.0
    hard_max = int(cfg["hard_max_words"])
    for j in range(1, n + 1):
        for i in range(max(0, j - hard_max), j):
            if best[i] == INF:
                continue
            if any((lo + k) in hard for k in range(i + 1, j)):
                continue
            end_abs = lo + j
            if end_abs < hi and end_abs not in hard and boundary_forbidden(stream, end_abs - 1, float(cfg["pause_break_s"])):
                continue
            pc = phrase_cost(stream, tokens, lo + i, end_abs, cfg)
            if pc is None:
                continue
            c = pc + (boundary_cost(stream, end_abs - 1, cfg) if end_abs < hi else 0.0)
            if best[i] + c < best[j]:
                best[j] = best[i] + c
                prev[j] = i
    if best[n] == INF:
        return [Card(lo + k, lo + k + 1) for k in range(n)]
    cards: list[Card] = []
    j = n
    while j > 0:
        i = prev[j]
        cards.append(Card(lo + i, lo + j))
        j = i
    cards.reverse()
    return cards


def plan_phrases_deterministic(stream: Sequence[dict[str, Any]], tokens: Sequence[str],
                               hard_breaks: set[int], cfg: dict[str, Any]) -> list[Card]:
    cards: list[Card] = []
    for lo, hi, _spk in speaker_runs(stream):
        cards.extend(_plan_run(stream, tokens, lo, hi, hard_breaks, cfg))
    return cards


Provider = Callable[[list[dict[str, Any]], list[int], dict[str, Any]], dict[str, Any]]
PROVIDERS: dict[str, Provider] = {}


def validate_cards(raw: Any, stream: Sequence[dict[str, Any]], tokens: Sequence[str],
                   hard_breaks: set[int], cfg: dict[str, Any]) -> tuple[list[Card] | None, str]:
    n = len(stream)
    try:
        items = raw["cards"] if isinstance(raw, dict) else raw
        cards = [Card(int(x[0]), int(x[1])) for x in items]
    except Exception as exc:  # noqa: BLE001
        return None, f"malformed proposal: {exc}"
    if not cards:
        return None, "empty proposal"
    run_end = {}
    for lo, hi, _s in speaker_runs(stream):
        for k in range(lo, hi):
            run_end[k] = hi
    # structural checks first (partition, speaker purity, joins, size) ...
    pos = 0
    for c in cards:
        if c.start != pos or c.end <= c.start or c.end > n:
            return None, f"cards do not partition the words in order (at {pos})"
        if c.end > run_end[c.start]:
            return None, f"card {c.start}-{c.end} crosses a speaker boundary"
        if c.end - c.start > int(cfg["hard_max_words"]):
            return None, f"card {c.start}-{c.end} exceeds hard_max_words"
        if any(k in hard_breaks for k in range(c.start + 1, c.end)):
            return None, f"card {c.start}-{c.end} crosses a segment join"
        pos = c.end
    if pos != n:
        return None, "cards do not cover every word"
    # ... then readability and fit
    for c in cards:
        if c.end < n and c.end not in hard_breaks:
            why = boundary_forbidden(stream, c.end - 1, float(cfg["pause_break_s"]))
            if why:
                return None, f"card ends on a forbidden boundary: {why}"
        if text_width(" ".join(tokens[c.start:c.end]), cfg) > float(cfg["safe_width"]):
            return None, f"card {c.start}-{c.end} does not fit one line"
    return cards, "ok"


# ---------------------------------------------------------------- reveal chunks + events


def reveal_chunks(card: dict[str, Any], stream: Sequence[dict[str, Any]], cfg: dict[str, Any]) -> list[tuple[int, int]]:
    """Split a phrase into 1–3 reveal chunks on its most natural interior
    boundaries (pause, punctuation, phrase opener), never a forbidden one,
    each chunk at least min_chunk_words unless the phrase is that short.
    How many: about density_target changes per second of the phrase's life,
    capped at max_chunks — a 1.1 s four-word phrase reveals in two steps, a
    0.6 s one in one."""
    start, end = int(card["start"]), int(card["end"])
    n = end - start
    life = float(card["clear_s"]) - float(card["start_s"])
    want = int(round(max(0.0, life) * float(cfg["density_target"])))
    want = max(1, min(int(cfg["max_chunks"]), want))
    mcw = int(cfg["min_chunk_words"])
    if n < 2 * mcw:
        want = 1
    if want == 1:
        return [(start, end)]
    cands = []
    for b in range(start + mcw, end - mcw + 1):
        if boundary_forbidden(stream, b - 1, float(cfg["pause_break_s"])):
            continue
        cands.append((boundary_cost(stream, b - 1, cfg), b))
    cands.sort()
    chosen: list[int] = []
    for _cost, b in cands:
        if len(chosen) >= want - 1:
            break
        if all(abs(b - c) >= mcw for c in chosen):
            chosen.append(b)
    bounds = [start] + sorted(chosen) + [end]
    return [(a, b) for a, b in zip(bounds, bounds[1:]) if b > a]


def _clear_time(card: dict[str, Any], next_start: float | None, cfg: dict[str, Any]) -> float:
    last_t = float(card["words"][-1][0])
    hold_end = last_t + float(cfg["hold_s"])
    if next_start is None:
        return round(hold_end, 3)
    gap = float(cfg["gap_ms"]) / 1000.0
    if next_start - last_t > 0.35:
        return round(min(hold_end, next_start - gap), 3)
    return round(min(hold_end, next_start), 3)


def _card_events(card: dict[str, Any], stream: Sequence[dict[str, Any]], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """The reveal states of one card: state k shows the words up to chunk
    k, the new chunk yellow with its pop, from the chunk's first word start
    to the next chunk's first word (the last to the clear time)."""
    toks = card["tokens"]
    times = [float(t) for t, _w in card["words"]]
    pop = float(cfg["pop_ms"]) / 1000.0
    chunks = reveal_chunks(card, stream, cfg)
    out = []
    for k, (a, b) in enumerate(chunks):
        la, lb = a - card["start"], b - card["start"]
        t0 = times[la]
        t1 = times[chunks[k + 1][0] - card["start"]] if k + 1 < len(chunks) else float(card["clear_s"])
        out.append({"t": round(t0, 3), "end": round(max(t1, t0 + 0.05), 3),
                    "visible": " ".join(toks[:lb]), "new": " ".join(toks[la:lb]), "new_range": [la, lb],
                    "pop": [round(t0, 3), round(t0 + pop, 3)]})
    return out


def plan_captions(words: Sequence[Any], style: dict[str, Any] | None = None,
                  hard_breaks: Sequence[int] | None = None, provider: Provider | None = None) -> dict[str, Any]:
    """The whole caption plan for a word stream:
    {cards, planner_used, display (the cleaned stream), audit, density}.
    Hard breaks are given in SOURCE indices and mapped through the audit."""
    cfg = _cfg(style)
    source = normalize_stream(words)
    display, audit = clean_disfluencies(source, cfg)
    tokens = display_tokens(display, bool(cfg.get("uppercase", True)))
    hb = map_hard_breaks(hard_breaks, audit)
    used = "deterministic"
    cards: list[Card] | None = None
    if provider is not None and display:
        try:
            proposal = provider([{"i": i, "t": x["t"], "w": tokens[i], "speaker": x.get("speaker")} for i, x in enumerate(display)],
                                sorted(hb), dict(cfg))
            cards, why = validate_cards(proposal, display, tokens, hb, cfg)
            used = "provider" if cards else f"deterministic (provider rejected: {why})"
        except Exception as exc:  # noqa: BLE001
            cards, used = None, f"deterministic (provider failed: {exc})"
    if cards is None:
        cards = plan_phrases_deterministic(display, tokens, hb, cfg)
    out = [c.as_dict(display, tokens, cfg) for c in cards]
    for k, d in enumerate(out):
        d["clear_s"] = _clear_time(d, out[k + 1]["start_s"] if k + 1 < len(out) else None, cfg)
        d["events"] = _card_events(d, display, cfg)
        d["chunks"] = [ev["new"] for ev in d["events"]]
        d.update(caption_origin(d, cfg))                 # the fixed origin of every reveal state
    return {"cards": out, "planner_used": used, "display": display, "audit": audit,
            "hard_breaks": sorted(hb), "density": density(out), "omitted": [a for a in audit if not a["kept"]]}


def plan_phrases(words: Sequence[Any], style: dict[str, Any] | None = None,
                 hard_breaks: Sequence[int] | None = None, provider: Provider | None = None,
                 key_words: set[str] | None = None) -> tuple[list[dict[str, Any]], str]:
    """(cards, planner_used) — the cards of plan_captions()."""
    res = plan_captions(words, style, hard_breaks, provider)
    return res["cards"], res["planner_used"]


def density(cards: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Visual changes per second: every reveal state plus every clear that
    leaves the rail empty (a clear that is immediately replaced is one
    change, the reveal)."""
    if not cards:
        return {"changes": 0, "span_s": 0.0, "per_second": 0.0}
    changes = sum(len(c["events"]) for c in cards)
    for k, c in enumerate(cards):
        nxt = cards[k + 1]["start_s"] if k + 1 < len(cards) else None
        if nxt is None or float(c["clear_s"]) < float(nxt) - 0.05:
            changes += 1
    span = float(cards[-1]["clear_s"]) - float(cards[0]["start_s"])
    return {"changes": changes, "span_s": round(span, 2), "per_second": round(changes / span, 2) if span > 0 else 0.0}


def kinetic_states(cards: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    states: list[dict[str, Any]] = []
    for k, c in enumerate(cards):
        for ev in c["events"]:
            states.append({"t": ev["t"], "kind": "REVEAL", "card": k, "speaker": c["speaker"],
                           "text": ev["visible"], "new": ev["new"], "pop": ev["pop"], "width_px": c["width_px"]})
        nxt = cards[k + 1] if k + 1 < len(cards) else None
        kind = "CLEAR"
        if nxt is not None and nxt["speaker"] != c["speaker"]:
            kind = "CLEAR (speaker reset)"
        elif nxt is not None and float(c["clear_s"]) >= float(nxt["start_s"]) - 1e-6:
            kind = "CLEAR (replaced)"
        states.append({"t": c["clear_s"], "kind": kind, "card": k, "speaker": c["speaker"],
                       "text": "", "new": None, "pop": None, "width_px": c["width_px"]})
    states.sort(key=lambda s: (s["t"], 0 if s["kind"].startswith("CLEAR") else 1))
    return states


# ---------------------------------------------------------------- QC

ALLOWED_OMISSIONS = {"filler", "repeat", "restart", "abandoned_fragment"}


def kinetic_qc(cards: Sequence[dict[str, Any]], display: Sequence[Any], style: dict[str, Any] | None,
               hard_breaks: Sequence[int] | None = None, audit: Sequence[dict[str, Any]] | None = None,
               timing_tol_s: float = 0.02) -> list[dict[str, Any]]:
    """Deterministic caption QC, every gate critical."""
    cfg = _cfg(style)
    stream = normalize_stream(display)
    tokens = display_tokens(stream, bool(cfg.get("uppercase", True)))
    gates: list[dict[str, Any]] = []

    def gate(name: str, ok: bool, detail: str) -> None:
        gates.append({"gate": name, "ok": bool(ok), "detail": detail, "critical": True})

    multi = [c for c in cards if len(c.get("lines", [c["text"]])) != 1]
    gate("ONE_LINE_ONLY", not multi, "every phrase is one line" if not multi else f"{len(multi)} multi-line phrase(s)")
    impure = [c for c in cards if len({stream[i].get("speaker") for i in range(c["start"], c["end"])}) > 1]
    gate("SPEAKER_PURITY", not impure, "every phrase holds one speaker" if not impure
         else f"{len(impure)} phrase(s) mix speakers, e.g. {impure[0]['text']!r}")
    gate("NO_CROSS_SPEAKER_CARD", not impure, "no card holds word indices of two speakers" if not impure
         else f"{impure[0]['start']}-{impure[0]['end']} spans a speaker change")
    resets_ok, detail = True, "each new speaker starts from an empty rail"
    for a, b in zip(cards, cards[1:]):
        if a["speaker"] != b["speaker"]:
            if not (a["clear_s"] <= b["start_s"] + 1e-6 and b["events"][0]["visible"] == b["events"][0]["new"]):
                resets_ok, detail = False, f"{a['text']!r} still up when {b['speaker']} starts {b['text']!r}"
                break
    gate("SPEAKER_RESET", resets_ok, detail)
    order = [i for c in cards for i in range(c["start"], c["end"])]
    rendered = [tok for c in cards for tok in c["tokens"]]
    gate("WORD_ORDER", order == list(range(len(stream))) and rendered == tokens,
         f"{len(rendered)} displayed words in transcript order" if order == list(range(len(stream))) and rendered == tokens
         else "rendered words differ from the display stream")
    if audit is not None:
        bad_reason = [a for a in audit if not a["kept"] and a["reason"] not in ALLOWED_OMISSIONS]
        src_order = [a["i"] for a in audit if a["kept"]]
        disp_src = [x["i"] for x in stream]
        gate("DISPLAY_AUDIT", not bad_reason and src_order == disp_src,
             f"{sum(1 for a in audit if not a['kept'])} word(s) omitted for display "
             f"({', '.join(sorted({a['reason'] for a in audit if not a['kept']})) or 'none'}), every displayed word maps to its source word"
             if not bad_reason and src_order == disp_src else "display words do not map back to the source in order")
    wide = [c for c in cards if float(c["width_px"]) > float(cfg["safe_width"]) + 0.5]
    gate("FIT", not wide, f"widest phrase {max((c['width_px'] for c in cards), default=0):.0f} px <= {cfg['safe_width']} ({width_source(cfg)})"
         if not wide else f"{len(wide)} phrase(s) wider than {cfg['safe_width']} px, e.g. {wide[0]['text']!r} {wide[0]['width_px']} px")
    late = []
    for c in cards:
        for ev in c["events"]:
            la = ev["new_range"][0]
            want = float(c["words"][la][0])
            if abs(float(ev["t"]) - want) > timing_tol_s:
                late.append((ev["new"], ev["t"], want))
    gate("TIMING", not late, f"every reveal lands on its first word's mapped start (tol {timing_tol_s:.2f}s)" if not late
         else f"{len(late)} reveal(s) off, e.g. {late[0]}")
    hb = {int(k) for k in (hard_breaks or [])}
    crossing = [c for c in cards if any(k in hb for k in range(c["start"] + 1, c["end"]))]
    gate("SEGMENT_JOINS", not crossing, "no phrase spans a render join" if not crossing
         else f"{crossing[0]['text']!r} spans a join")
    too_many = [c for c in cards if len(c["events"]) > int(cfg["max_chunks"])]
    dens = density(cards)
    gate("DENSITY", not too_many and dens["per_second"] <= float(cfg["density_max"]),
         f"{dens['changes']} visual changes over {dens['span_s']}s = {dens['per_second']}/s (ceiling {cfg['density_max']}), "
         f"<= {cfg['max_chunks']} reveals per phrase")
    return gates
