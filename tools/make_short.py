# -*- coding: utf-8 -*-
"""One command: tightened split-screen source -> finished, captioned short.

Everything Nathan settled between 2026-08-29 03:00 and 12:00 lives here as a
default, so the next case does not re-litigate any of it:

  grade      per-TILE eq. The two halves come from different cameras and the
             single global grade is what made the short look washed out. Values
             are the ones he approved ("colors look really nice").
  captions   Anton, cap 132, scale_y 108, cards of <=4 words / <=20 chars,
             sitting ON the seam, snapping in - and gated so a word is never
             readable before it is spoken (NATHAN_RULES R34).
  card       "FULL VIDEO OUT NOW" at y=1580, 2.7-7.0s, with a pop on entry.

Since 2026-09-01 every one of those numbers is READ from config/short_floor.json
through short_engine.derive() - the values quoted above are what the file said
that day, not a second copy of them.

    python tools/make_short.py tight.mp4 words_tight.json OUT.mp4 \
        --card popcard.png --pop pop.wav
"""
import os, sys, json, argparse, subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import short_engine as _SE          # the floor loader; nothing else from it
import caption_short as C
import speakers as S

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
FONTDIR = os.path.join(ROOT, "assets", "fonts")

# Per-tile grade. The two tiles are different cameras, so ONE global grade is
# what made the first short look washed out. These defaults are the SANCHEZ
# values he approved ("colors look really nice") - but they are a starting
# point, not a constant: CARTHIEF measured the opposite way round (top too dark
# and flat, bottom too bright and hot), so its grade was solved separately.
# Solve per case against the approved SANCHEZ look: top L 125.7 S 80.0 sd 74.1,
# bottom L 120.9 S 73.1 sd 72.9 - matching LUMINANCE between tiles, never mean
# saturation (a bright jumpsuit or shirt distorts mean S and crushing it to
# match drains real colour).
# SOLVED AGAINST SANCHEZ, the short he says looks right.
# Nathan, 2026-08-31: "in another short you normalized the colors and made it
# look hd" -> "Short that you made look nicer than the original footage was
# Sanchez".
#
# MEASURED across the shipped shorts:
#     SANCHEZ (reference)  skin L*123.2  chroma 19.7  contrast sd 74.3  grain 11.50
#     CARTHIEF V2          skin L*125.9  chroma 14.0  contrast sd 74.4
#     OFFERUP (old)        skin L*167.9  chroma 12.7  contrast sd 58.3  grain  9.55
# OFFERUP was the outlier on every axis - bright, flat, undersaturated.
#
# An EARLIER attempt solved these against the THUMBNAIL floor (L*134/20.6) and
# he rejected it as over-processed. A still composite is not footage; the
# reference for a short is a SHORT. That is the whole lesson.
#
# Re-solve for any clip with:  python tools/solve_grade.py <short.mp4>
#
# The eq string itself lives in config/short_floor.json (grade.eq, applies_to
# "both tiles"); the numbers in the comment above are the floor's `measured`
# block. Both tiles get the same string unless a caller passes grade_top /
# grade_bot for a case solved separately.
GRADE_TOP = _SE.GRADE_EQ
GRADE_BOT = _SE.GRADE_EQ

# GRAIN. Nathan: "I was also going to tell you to add grain because I think it
# makes it look like a legit video idk why".
#
# HIS PREFERENCE, not a measurement. An earlier version of this comment claimed
# SANCHEZ was "already grainier" at 11.50 high-frequency energy against
# OFFERUP's 9.55 - he corrected it: "I don't think Sanchez had grain on the
# short", and he is right. SANCHEZ's contrast sd is 74.3 against OFFERUP's 58.3,
# and a stronger grade AMPLIFIES whatever texture the footage already has. The
# hf difference is a by-product of the grade, not added grain. Nothing in the
# reference supports a grain number.
#
# So this is set from his stated preference and kept light. The reason he gives
# is sound - a composite is two crops re-encoded and graded, and a shared grain
# is what stops it reading as processed - but the LEVEL is a taste call, not a
# derived one. Say so rather than dressing it up as measured.
# Value: config/short_floor.json grain.strength (its `provenance` says the same).
GRAIN_STRENGTH = _SE.GRAIN_STRENGTH

# The "FULL VIDEO OUT NOW" card. Not in the floor: short_engine.build() passes
# card=None, so the engine path never draws it; these only apply when a caller
# gives --card.
CARD_Y, CARD_IN, CARD_OUT, CARD_FADE = 1580, 2.70, 7.00, 0.28
CAP_PX, SCALE_Y = _SE.CAP_PX, _SE.SCALE_Y            # floor captions.size / scale_y
# floor captions.cards - measured 2026-08-29 on SANCHEZ. Widening from
# (15 ch, 3 words) to (20 ch, 4 words, target 15) cut cards ending on a
# stranded function word from 25 to 11 and sub-0.30s flashes from 3 to 1, at a
# cost of 2.2 chars of mean line length. Wider than this stops paying for itself.
MAX_CHARS, MAX_WORDS, TARGET_CHARS = _SE.MAX_CHARS, _SE.MAX_WORDS, _SE.TARGET_CHARS
PIX_FMT = _SE.PIX_FMT                                # floor format.pix_fmt
ENTRANCE_MODES = ["none", "fade", "lift", "blur", "bounce", "punch", "rise", "scale"]
REVEAL_MODES = ["build", "reserve", "off"]


def build(src, words_json, out, card=None, pop=None, reveal=None,
          entrance=None, ass_path="_short.ass", diarize=True,
          grade_top=None, grade_bot=None, audio=None):
    # reveal / entrance default to the floor (captions.reveal / entrance_mode).
    # The old default here was reveal="off" - the one value R34 forbids.
    reveal = _SE.REVEAL if reveal is None else reveal
    entrance = _SE.ENTRANCE if entrance is None else entrance
    seam, H, W = C.find_seam(src)
    words = json.load(open(words_json))
    C.REVEAL, C.ENTRANCE = reveal, entrance

    # WHO is talking, so a card can never straddle a turn. See speakers.py and
    # NATHAN_RULES R35 - this is the fix for "you need to learn when to start
    # the sentences", and it is upstream of every styling decision.
    if diarize and not any("spk" in w for w in words):
        t, et, eb, _ = S.energy(src)
        words, sents = S.label_sentences(words, t, et, eb)
        turns = sum(1 for a, b in zip(words, words[1:]) if a["spk"] != b["spk"])
        print(f"  {len(sents)} sentences, {turns} speaker changes")

    cs = C.cards_phrase(words, max_chars=MAX_CHARS, max_words=MAX_WORDS,
                        target_chars=TARGET_CHARS)
    n = C.build_snap(cs, ass_path, W, H, seam, CAP_PX, scale_y=SCALE_Y)

    # R34/R35 proof, measured not assumed.
    straddle = sum(1 for c in cs
                   if any(x["w"].rstrip("\"”')").endswith((".", "!", "?"))
                          for x in c[:-1]))
    mixed = sum(1 for c in cs if len({x.get("spk") for x in c}) > 1)
    glue = sum(1 for c in cs if C._norm(c[-1]["w"]) in C.GLUE_FORWARD)
    print(f"  seam y={seam} ({seam/H:.3f} H)   {len(cs)} cards -> {n} events   "
          f"reveal={reveal}   straddle={straddle}  mixed-speaker={mixed}  "
          f"ends-on-glue={glue}")
    if straddle or mixed:
        raise SystemExit("R35 VIOLATION: a card crosses a sentence or a speaker turn")

    # CROP AT THE MEASURED SEAM - but on an EVEN row.
    # yuv420p subsamples chroma 2x2, so an odd crop height is silently rounded
    # DOWN by ffmpeg. Measured 2026-08-31: seam=959 gave tiles of 958 and 960,
    # and the "1080x1920" short was actually 1080x1918. Nothing checked it, and
    # two lost rows is the kind of defect that only ever shows up as a video
    # that looks subtly wrong. Rounding the seam to even makes both tiles even
    # and their sum exactly H.
    top = (seam // 2) * 2
    if top != seam:
        print(f"  seam {seam} -> {top} (even, so {PIX_FMT} does not round the tiles)")
    gt = grade_top or GRADE_TOP
    gb = grade_bot or GRADE_BOT
    fc = (f"[0:v]crop={W}:{top}:0:0,{gt}[t];"
          f"[0:v]crop={W}:{H-top}:0:{top},{gb}[b];"
          f"[t][b]vstack=inputs=2" +
          (f",noise=alls={GRAIN_STRENGTH}:allf=t+u" if GRAIN_STRENGTH else "") +
          f"[g]")
    last, idx = "[g]", 1
    inputs = ["-i", src]
    if card:
        inputs += ["-loop", "1", "-t", str(CARD_OUT + 1), "-i", card]
        fc += (f";[{idx}:v]format=rgba,fade=t=in:st={CARD_IN}:d={CARD_FADE}:alpha=1,"
               f"fade=t=out:st={CARD_OUT-CARD_FADE}:d={CARD_FADE}:alpha=1[c];"
               f"{last}[c]overlay=0:{CARD_Y}:enable='between(t,{CARD_IN},{CARD_OUT})'[k]")
        last, idx = "[k]", idx + 1
    fd = FONTDIR.replace(chr(92), "/").replace(":", chr(92) + ":")
    fc += f";{last}subtitles={ass_path}:fontsdir='{fd}'[v]"

    amap = "0:a"
    if audio:
        inputs += ["-i", audio]
        amap = f"{idx}:a"
        aidx = idx
        idx += 1
    if pop:
        inputs += ["-i", pop]
        base = f"{aidx}:a" if audio else "0:a"
        fc += (f";[{idx}:a]adelay={int(CARD_IN*1000)}|{int(CARD_IN*1000)},volume=0.85[p];"
               f"[{base}][p]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]")
        amap = "[a]"

    cmd = (["ffmpeg", "-v", "error", "-y"] + inputs +
           ["-filter_complex", fc, "-map", "[v]", "-map", amap,
            "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", PIX_FMT,
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out])
    subprocess.run(cmd, check=True)
    d = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", out], capture_output=True, text=True)
    print(f"  wrote {out}  ({float(d.stdout.strip()):.2f}s)")

    # CHECK THE RENDER, HERE, not in a script someone has to remember to run.
    # Both of these existed and were invoked by NOTHING - `audit_cuts`
    # immediately found 5 of 5 cuts defective in a short that had already
    # shipped, and `check_vertical` is the only thing that proves a "vertical"
    # is actually 1080x1920 and usable rather than merely present.
    import subprocess as _sp, sys as _sys, os as _os
    _root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    _cv = _os.path.join(_root, "scripts", "check_vertical.py")
    if _os.path.exists(_cv):
        print("  [check_vertical]")
        _sp.run([_sys.executable, _cv, "--file", _os.path.basename(out)], cwd=_root)
    _ac = _os.path.join(_root, "scripts", "audit_cuts.py")
    if _os.path.exists(_ac) and _os.path.exists(_os.path.splitext(out)[0] + ".map.json"):
        print("  [audit_cuts]")
        _sp.run([_sys.executable, _ac, "--short", _os.path.basename(out)], cwd=_root)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("video"); ap.add_argument("words"); ap.add_argument("out")
    ap.add_argument("--card"); ap.add_argument("--pop")
    ap.add_argument("--reveal", default=_SE.REVEAL, choices=REVEAL_MODES,
                    help="default: floor captions.reveal")
    ap.add_argument("--no-diarize", action="store_true")
    ap.add_argument("--audio", help="replace the audio with this wav")
    ap.add_argument("--grade-top"); ap.add_argument("--grade-bot")
    ap.add_argument("--entrance", default=_SE.ENTRANCE, choices=ENTRANCE_MODES,
                    help="default: floor captions.entrance_mode")
    a = ap.parse_args()
    build(a.video, a.words, a.out, a.card, a.pop, a.reveal, a.entrance,
          diarize=not a.no_diarize, grade_top=a.grade_top, grade_bot=a.grade_bot,
          audio=a.audio)
