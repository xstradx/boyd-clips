"""Hook-first short with one-word centred captions.

Three things the daily pipeline does not do:

1. HOOK FIRST. The payoff line is lifted to the front, then the clip plays from
   its real start. The viewer hears the line twice on purpose — once as the
   hook, once earned.
2. LOOP-FRIENDLY OUT. The body ends on a line that reads as a lead-in to the
   hook, so the replay is seamless. Not every clip has one; when it does not,
   pass loop_note="" and take the natural ending.
3. ONE-WORD CENTRED CAPTIONS. ASS alignment 5 puts each word dead centre of the
   1080x1920 frame — the gap between the two Zoom panes in a split_stack — which
   is where editors put them because it is the only part of the frame with no
   picture in it.

Usage:  python scripts/hook_short.py [out_dir]
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from boydclips import render                      # noqa: E402
from boydclips.config import load_config          # noqa: E402
from boydclips.render import Segment              # noqa: E402
from boydclips.transcribe import get_transcript   # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("hook")

# video_id, hook (start,end), body (start,end), slug
JOBS_ALL = [
    # Body opens on "Are you proceeding with sentencing?" (8106.64) rather than
    # mid-way through the deferred-adjudication boilerplate — after the hook,
    # the viewer needs a line that starts something, not one that finishes it.
    dict(vid="XiWwYFPhPn0", hook=(8142.20, 8145.30), body=(8106.50, 8160.20),
         slug="guns-are-not-toys",
         note='hook "You shot somebody in the face" -> body ends on '
              '"Guns are not toys." which reads straight back into the hook',
         punch={"SHOT", "FACE", "FRIEND", "GUN", "GUNS", "TOYS", "18",
                "KILLED", "THINKING", "MOM", "LASER", "POINTER"},
         # YouTube auto-captions mishear things, and burning them in ships the
         # error. Verified against the audio, not guessed.
         fixes={"LADY ON HER": "LASER POINTER"}),

    dict(vid="BLtJn8XTfzA", hook=(1542.60, 1545.60), body=(1540.70, 1600.20),
         slug="could-have-killed-somebody",
         note='hook "You could have killed somebody" -> body opens on '
              '"Here\'s the thing", ends on "Good luck to you." Ends rather '
              'than loops: a dismissal closes, it does not lead anywhere.',
         punch={"KILLED", "SOMEBODY", "THIRD", "DRINK", "PRISON", "DWI",
                "DANGEROUS", "STOP", "DRINKING", "EXCESS", "LUCK"}),

    dict(vid="jcf7y3da_W8", hook=(1427.60, 1431.20), body=(1369.70, 1438.60),
         slug="legally-an-adult",
         note='hook "Legally you\'re an adult, but technically you\'re not" -> '
              'body opens on "why are you quitting a job", ends on '
              '"probably to get you here to court"',
         punch={"ADULT", "LEGALLY", "TECHNICALLY", "PARENTS", "QUIT",
                "DEPENDENT", "FOOD", "SHELTER", "CLOTHES", "COURT", "FELONY"}),

    dict(vid="QzcSk3BNYqI", hook=(9204.00, 9208.20), body=(9152.30, 9237.00),
         slug="marijuana-cigarette",
         note='hook "Would you give your child a marijuana cigarette to '
              'smoke?" -> body opens on the drug-test question, ends on '
              '"You need to change. You understand?"',
         punch={"MARIJUANA", "CIGARETTE", "CHILD", "CHILDREN", "SMOKE",
                "SMOKING", "ALCOHOL", "BRAIN", "DAD", "PROUD", "CHANGE"}),

    # Almaguer, felony DWI 3rd+. Hook is Boyd's framing question and his one-word
    # answer; body opens on the same line so the hook lands twice, and ends on
    # her stating the undue-detriment finding — a conclusion that reads straight
    # back into "you're one of the people who cannot drink".
    dict(vid="SPSHGzlOe8c", hook=(3024.20, 3029.60), body=(3024.10, 3082.00),
         slug="cannot-drink-and-know-when-to-stop",
         note='hook "you\'re one of the people who cannot drink alcohol and '
              'know when to stop, right?" / "Correct." Loops on the same claim.',
         punch={"DRINK", "ALCOHOL", "STOP", "JAIL", "GPS", "DWI", "PRISON",
                "CORRECT", "JOB", "CHILDREN", "DAYS", "FELONY"}),

    dict(vid="0OXHpQjbb8Y", hook=(4826.30, 4828.40), body=(4823.10, 4880.40),
         slug="batman-could-beat-anybody",
         note='hook "Batman could beat anybody" -> body opens on the question '
              'that prompts it, ends on "don\'t get him killed". Loops: the '
              'closing joke reads straight back into the opening claim.',
         punch={"BATMAN", "ANYBODY", "MARVEL", "HARLEY", "QUINN", "MONEY",
                "GENTLEMAN", "WOMAN", "KILLED", "DC", "COMICS"}),
]
import os as _os
JOBS=[j for j in JOBS_ALL if j['slug']=='cannot-drink-and-know-when-to-stop']

# Anton: OFL-licensed, condensed and heavy. Condensed matters twice over —
# it reads less "thick" than Arial Black at the same weight, and long words
# like SUPERVISION fit without dropping the size. Ships in assets/fonts/.
FONT = _os.environ.get("CAP_FONT", "Arial Black")
FONT_SIZE = int(_os.environ.get("CAP_SIZE", "140"))
# The band is 195px tall. Arial Black cap-height is ~0.72em, so 104pt gives
# ~75px of glyph + 6px outline either side = ~87px, comfortably inside it.
# Above ~120 the outline starts clipping the pane edges.
# Lighter stroke than the default 6. A heavy outline on a heavy face is what
# makes auto-captions look like auto-captions; depth comes from the shadow.
OUTLINE = int(_os.environ.get("CAP_OUTLINE", "4"))
SHADOW = 5

# Caption treatment. Researched 2026-08-10 rather than guessed: short-form
# sources converge on word-by-word display with an ACTIVE HIGHLIGHT, colour
# shift (not boxes or underlines) for emphasis, and emphasis on only the
# important words rather than all of them.
#   plain   - white throughout (baseline)
#   keyword - punch words shift to accent colour
#   glow    - keyword, plus a soft coloured bloom behind the accent words
STYLE = __import__("os").environ.get("CAP_STYLE", "keyword")

ACCENT = r"&H0000E5FF"   # ASS is BGR: this is amber/yellow
WHITE = r"&H00FFFFFF"

# Generic content words carry the meaning; these never get emphasised.
STOP = {
    "THE", "A", "AN", "AND", "OR", "BUT", "IF", "SO", "TO", "OF", "IN", "ON",
    "AT", "IS", "IT", "ITS", "WAS", "ARE", "YOU", "YOUR", "I", "IM", "ID",
    "THAT", "THIS", "THERE", "HERE", "WITH", "FOR", "FROM", "BE", "BEEN",
    "HAVE", "HAS", "HAD", "DO", "DOES", "DID", "WILL", "WOULD", "CAN",
    "COULD", "ALL", "ANY", "MY", "ME", "WE", "THEY", "HE", "SHE", "HIS",
    "HER", "OKAY", "OK", "ALRIGHT", "RIGHT", "WELL", "UM", "UH", "YES", "NO",
    "NOT", "WHAT", "WHO", "WHY", "HOW", "WHEN", "JUST", "REALLY", "ABOUT",
    "GOING", "GO", "GET", "KNOW", "THINK", "LIKE", "MEAN", "SAY", "SAID",
}

# Vertical centre of the black band between the two stacked Zoom panes.
# Measured off a rendered split_stack frame, not assumed: the panes leave a
# 195px gap centred at y=826 in a 1080x1920 frame. ASS alignment 5 centres on
# the FRAME (y=960), which lands the text on the lower pane's picture — so the
# position is set explicitly instead.
BAND_Y = 826
CAPTION_MODE = "band"   # "band" = in the letterbox gap, "centre" = frame centre


def _t(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def _clean(tok: str) -> str:
    """Strip caption artefacts. YouTube's auto-captions carry speaker markers
    and stray punctuation that read as glitches one word at a time."""
    tok = tok.replace(">>", "").replace("[", "").replace("]", "").strip()
    return tok.strip(" ,").upper()


def write_word_ass(words, total_s: float, out_path: Path,
                   punch: set[str] | None = None,
                   fixes: dict[str, str] | None = None) -> Path:
    """One dialogue event per word, sitting in the letterbox band.

    Smoothness comes from three things the first pass got wrong:

    * NO DEAD AIR. Each word holds until the next one starts, so there is
      always a word on screen during speech. Previously every word was capped
      at 0.85s, which left the band empty in every natural pause and made the
      captions look like they were dropping out.
    * A SHORT FADE. 40ms in/out. Hard cuts at word rate read as flicker.
    * A SCALE POP. Each word lands at 92% and snaps to 100% over 90ms. That is
      the motion editors add by default; without it the words feel pasted on.

    Words closer together than MIN_ON are merged rather than flashed — YouTube
    caption timings quantise to ~0.16s and sometimes stack two words on the
    same timestamp, which is unreadable at one word per event.
    """
    punch = punch or set()
    fixes = fixes or {}
    MIN_ON = 0.14
    MAX_ON = 1.10   # a long pause should clear the band, not park a word in it
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Word,{FONT},{FONT_SIZE},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,{OUTLINE},{SHADOW},5,40,40,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    # Merge anything closer together than MIN_ON into a single event.
    #
    # This threshold must match the minimum on-screen time exactly. The first
    # version merged at 0.06s but enforced a 0.14s minimum by pushing a word's
    # end past the next word's start — so any pair 0.06-0.14s apart rendered
    # SIMULTANEOUSLY, one ghosted over the other. That was the "something's
    # off": two words stacked in the band, not a timing feel.
    toks: list[tuple[float, str]] = []
    for w in words:
        text = _clean(w.w)
        if not text:
            continue
        t = max(0.0, w.t)
        if toks and t - toks[-1][0] < MIN_ON:
            toks[-1] = (toks[-1][0], f"{toks[-1][1]} {text}")
        else:
            toks.append((t, text))

    # Apply phrase corrections across token boundaries. Done after merging so
    # the phrase is contiguous, and before styling so the replacement can be a
    # punch word in its own right.
    if fixes:
        i = 0
        while i < len(toks):
            for wrong, right in fixes.items():
                parts = wrong.split()
                window = [toks[j][1] for j in range(i, min(i + len(parts), len(toks)))]
                if [w.strip(".,?!") for w in window] == parts:
                    new = right.split()
                    start_t = toks[i][0]
                    end_t = (toks[i + len(parts)][0] if i + len(parts) < len(toks)
                             else start_t + 0.4)
                    del toks[i:i + len(parts)]
                    # Spread the replacement across the span the wrong words
                    # occupied, in order. Inserting reversed put LASER at a
                    # LATER timestamp than POINTER, and the overlap guard then
                    # dropped it silently — the caption read "with a pointer".
                    step = max(0.08, (end_t - start_t) / max(len(new), 1))
                    for k, word in enumerate(new):
                        toks.insert(i + k, (start_t + k * step, word))
                    break
            i += 1

    y = BAND_Y if CAPTION_MODE == "band" else 960
    lines = []
    for i, (start, text) in enumerate(toks):
        if start >= total_s:
            break
        nxt = toks[i + 1][0] if i + 1 < len(toks) else total_s
        # Never run past the next word. An event that outlives its successor's
        # start puts two words on screen at once.
        end = min(nxt, start + MAX_ON, total_s)
        if end <= start:
            continue
        # Emphasise only words that carry meaning — sources are explicit that
        # highlighting everything defeats the purpose.
        bare = text.replace("?", "").replace(".", "").replace("!", "").strip()
        # Punch list only. An earlier version also accented any word >=4 chars
        # not in STOP, which lit up most of the line — the opposite of what the
        # sources prescribe, and it stops reading as emphasis entirely.
        hot = STYLE != "plain" and bare in punch

        col = ACCENT if hot else WHITE
        # Grow in, overshoot slightly, settle — with EASING.
        #
        # \t interpolates linearly unless given an acceleration parameter, and
        # linear motion is the single biggest reason captions read as cheap:
        # nothing physical moves at constant speed. accel<1 decelerates into
        # the target, which is the ease-out every editor applies by default.
        base = (r"\an5\pos(540," + str(y) + r")\fad(25,45)"
                r"\fscx80\fscy80"
                r"\t(0,90,0.55,\fscx106\fscy106)"
                r"\t(90,190,0.7,\fscx100\fscy100)")

        if STYLE == "glow" and hot:
            # Standard ASS glow: a blurred coloured copy underneath, crisp on
            # top. One layer cannot be both sharp and bloomed.
            lines.append(
                f"Dialogue: 0,{_t(start)},{_t(end)},Word,,0,0,0,,"
                f"{{{base}\\bord14\\blur12\\3c{ACCENT}\\1c{ACCENT}\\alpha&H60&}}{text}")
            lines.append(
                f"Dialogue: 1,{_t(start)},{_t(end)},Word,,0,0,0,,"
                f"{{{base}\\1c{col}}}{text}")
        else:
            lines.append(f"Dialogue: 0,{_t(start)},{_t(end)},Word,,0,0,0,,"
                         f"{{{base}\\1c{col}}}{text}")

    out_path.write_text(head + "\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def main() -> int:
    cfg = load_config()
    out_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("out/hooked")
    out_root.mkdir(parents=True, exist_ok=True)
    work = Path("work")

    sh_cfg = dict(cfg.get("output.short") or {})
    sh_cfg["max_duration_s"] = 90
    sh_cfg["captions"] = {"enabled": False}   # we build our own

    for job in JOBS:
        vid, slug = job["vid"], job["slug"]
        hs, he = job["hook"]
        bs, be = job["body"]
        log.info("\n=== %s", slug)
        log.info("  hook %0.1f-%0.1f (%.1fs) + body %0.1f-%0.1f (%.1fs)",
                 hs, he, he - hs, bs, be, be - bs)

        source, offset = render.download_section(
            vid, min(hs, bs), max(he, be), work / vid / f"hook_{slug}.mp4")
        crop = render.detect_content_crop(source)

        segs = [Segment(hs, he), Segment(bs, be)]
        total = (he - hs) + (be - bs)

        t = get_transcript(vid, work / vid)
        words, elapsed = [], 0.0
        for seg in segs:
            for w in t.slice(seg.start_s, seg.end_s):
                words.append(type(w)(t=elapsed + (w.t - seg.start_s), w=w.w))
            elapsed += seg.duration
        ass = write_word_ass(words, total, out_root / f"{slug}-{STYLE}.ass",
                             set(job.get("punch", [])), job.get("fixes"))

        out = out_root / f"{slug}-{STYLE}.mp4"
        dur = render.render_short(source, offset, segs, sh_cfg, ass, out, crop=crop)
        (out_root / f"{slug}-{STYLE}.txt").write_text(
            f"{job['note']}\n\nhook {hs:.1f}-{he:.1f}\nbody {bs:.1f}-{be:.1f}\n"
            f"rendered {dur:.1f}s\nsource https://youtu.be/{vid}?t={int(bs)}\n",
            encoding="utf-8")
        log.info("  -> %s (%.1fs)", out.name, dur)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
