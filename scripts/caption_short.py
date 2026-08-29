"""Burn captions and the house colour grade onto a contiguous short.

Two things this deliberately does NOT do, both because they are the measured
defects in the caption work Nathan rejected on 2026-08-23:

  * NO speaker attribution. The auto-transcript's speaker split was measured
    wrong — a Boyd-dominated riff came back 29 defendant lines against 6 of
    hers. So captions are not colour-coded or moved by speaker; guessing wrong
    is worse than not guessing.
  * NO 3-word rolling window and NO gold live-word highlight. Both are recorded
    in STATE.md as violations of the published standards the research pass
    measured us against: a rolling window is for live captioning, pre-recorded
    wants phrase blocks, and yellow means *different speaker* in BBC 8.3 /
    Ofcom 1.16, so a gold current-word inverts its meaning.

What it keeps is the one thing that measured RIGHT in the old work: the block
hugs the split between the two stacked panels, where there is no face. That
satisfies Nathan's standing rule that type never sits on a face or body.

The colour grade is the same one every rendered cut gets, from
config/pipeline.yaml — curves then saturation then contrast, applied to the
PICTURE before the captions burn in so caption white is never lifted or clipped.

    python scripts/caption_short.py --video SHORT.mp4 --transcript work/X/X.transcript.json \\
        --src-start 3931.8 --out SHORT_CAPTIONED.mp4
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "assets" / "fonts"
# The house face, shared with the thumbnails so captions and covers match.
#
# Nathan, 2026-08-28, on the thumbnail render: "what font is that ... because
# those are the captions ive been looking for and have been want you to use".
#
# It is Archivo Variable frozen at Weight 900 / Width 70 — the combination
# identified by matching the shipped Thompson thumbnail (its 26-character quote
# spans 1049px at cap 71; Montserrat Black gives cap 52 at that width and
# Archivo SemiCond SemiBold gives 68, both far lighter than the real
# letterforms). libass cannot select a variable axis, and Archivo's named
# instances cover weight only, so the instance is baked to a static file with
# fontTools and renamed to avoid colliding with stock Archivo. Archivo is SIL
# OFL 1.1, which permits commercial use and instancing.
#
#   python -c "from fontTools.varLib import instancer; ..."  -> TTTHeadline-Regular.ttf
FONT_FAMILY = "TTT Headline"

# From config/pipeline.yaml output.longform.color — the grade the video gets.
CURVE = "0/0.02 0.25/0.31 0.5/0.57 0.75/0.80 1/0.97"
SATURATION = 1.10
CONTRAST = 1.05

MAX_CHARS = 44          # a 1080-wide frame at cap ~92 fits this comfortably.
                        # 34 produced 2-word scraps ("those friends", "to the")
                        # — the rolling-window failure the standards pass
                        # names as wrong for pre-recorded material.
MAX_WORDS = 9
CAP_PX = 92             # caption cap height on a 1080x1920 short
MAX_DUR = 3.2           # seconds per block
GAP_SPLIT = 0.95        # courtroom speech is halting; 0.55 split mid-clause


def blocks(words: list[tuple[float, str]], max_chars: int = MAX_CHARS,
           max_words: int = MAX_WORDS,
           turns: list[float] | None = None) -> list[tuple[float, float, str]]:
    """Group words into phrase blocks, split on pauses, length AND SPEAKER TURNS.

    `turns` is a list of times where the speaker changes. A block that straddles
    a turn cannot be placed on either person's half, and that was the real bug
    behind "captions are still not 100% correct on the speaker's side" — blocks
    were grouped purely by character count, so roughly a third of them contained
    both voices. Measured examples from the shipped file: "evading? Nothing"
    (her question plus his answer) and "your action? Yes, sir." A block is now
    forced to end at every turn boundary, so each one belongs to exactly one
    person before anything tries to position it.
    """
    out: list[tuple[float, float, str]] = []
    cur: list[tuple[float, str]] = []

    def flush(end: float) -> None:
        if not cur:
            return
        text = " ".join(w for _, w in cur).strip()
        text = text.replace(">>", "").strip()
        if text:
            out.append((cur[0][0], end, text))
        cur.clear()

    for i, (t, w) in enumerate(words):
        nxt = words[i + 1][0] if i + 1 < len(words) else t + 0.4
        if cur:
            span = nxt - cur[0][0]
            joined = " ".join(x for _, x in cur) + " " + w
            starts_speaker = w.startswith(">>")
            crosses_turn = bool(turns) and any(
                cur[0][0] < tt <= t for tt in turns)
            if (span > MAX_DUR or len(joined) > max_chars
                    or len(cur) >= max_words or starts_speaker or crosses_turn
                    or (t - words[i - 1][0]) > GAP_SPLIT):
                flush(min(words[i - 1][0] + 0.9, t))
        cur.append((t, w))
    if cur:
        flush(words[-1][0] + 0.7)

    # Enforce a floor of 0.3s per word (BBC's readability floor) without
    # letting a block run into the next one.
    fixed = []
    for i, (a, b, txt) in enumerate(out):
        need = 0.30 * len(txt.split())
        end = max(b, a + need)
        if i + 1 < len(out):
            end = min(end, out[i + 1][0] - 0.02)
        if end > a:
            fixed.append((a, end, txt))

    # Bridge short pauses. Measured on ROMERO: captions were visible in only
    # 27 of 32 sampled frames, and every gap turned out to be a real 1.5-2.5s
    # pause between words rather than a missing block. Blinking the caption off
    # for that long mid-sentence reads as broken, so a block now holds until
    # the next one starts whenever the gap is under BRIDGE seconds.
    BRIDGE = 2.8
    bridged = []
    for i, (a, b, txt) in enumerate(fixed):
        if i + 1 < len(fixed):
            nxt = fixed[i + 1][0]
            if nxt - b < BRIDGE:
                b = nxt - 0.02
        else:
            b = b + 0.35
        bridged.append((a, b, txt))
    return bridged


def speaker_track(speakers, fps, win=1.0, hold=0.45):
    """Per-frame speaker label, and the times the speaker changes.

    A sliding correlation window is used rather than per-block windows, so a
    turn boundary can be located BEFORE the words are grouped. `hold` refuses a
    turn shorter than 0.45s, which is below the length of any real utterance
    here and would otherwise flicker on a cough or a nod.
    """
    import numpy as _np
    top = _np.array(speakers["top"]); bot = _np.array(speakers["bottom"])
    env = _np.array(speakers.get("audio") or [])
    n = len(top)
    if len(env) != n or n < 8:
        return None, []
    half = max(2, int(win * fps / 2))

    def corr(x, y):
        sx, sy = x.std(), y.std()
        if sx < 1e-6 or sy < 1e-6:
            return 0.0
        return float(((x - x.mean()) * (y - y.mean())).mean() / (sx * sy))

    lab = []
    for i in range(n):
        a, b = max(0, i - half), min(n, i + half)
        lab.append(1 if corr(top[a:b], env[a:b]) >= corr(bot[a:b], env[a:b]) else 0)
    lab = _np.array(lab)
    # median-smooth over the hold length so single-frame flips vanish
    k = max(3, int(hold * fps) | 1)
    pad = _np.pad(lab, k // 2, mode="edge")
    sm = _np.array([int(_np.median(pad[i:i + k])) for i in range(n)])
    turns = [i / fps for i in range(1, n) if sm[i] != sm[i - 1]]
    return sm, turns


def assign_speakers(bl, speakers, fps, margin=0.06, track=None):
    """Put each caption block on the side of whoever was talking.

    Attribution is AUDIO-VISUAL CORRELATION, not raw motion. A talking mouth
    moves in time with the sound; a nodding or reacting head does not. So each
    half's mouth-motion series is correlated against the audio envelope over the
    block's own window and the speaker is whoever actually tracks the audio.

    Measured on nine hand-labelled windows of the CARTHIEF short:
        audio-visual correlation   9/9
        raw motion (the old rule)  4/9
    Judge Boyd is animated while listening, which is precisely why comparing
    raw movement handed her the defendant's lines.

    HYSTERESIS is kept but is now small (0.06 of correlation): a switch must
    clear the current speaker by that margin, so a block sitting on a genuine
    turn boundary does not flicker. A block with no usable signal keeps the
    previous side rather than defaulting.
    """
    import numpy as _np
    top = _np.array(speakers["top"])
    bot = _np.array(speakers["bottom"])
    env = _np.array(speakers.get("audio") or [])
    have_audio = len(env) == len(top) and len(env) > 4

    def corr(x, y):
        if len(x) < 3:
            return 0.0
        sx, sy = x.std(), y.std()
        if sx < 1e-6 or sy < 1e-6:
            return 0.0
        return float(((x - x.mean()) * (y - y.mean())).mean() / (sx * sy))

    if track is not None:
        # A turn track exists, so every block already lies inside one turn.
        # Take the majority label over the block rather than re-correlating on
        # a window that may be far too short to be reliable.
        out = []
        for (a, b, txt) in bl:
            i0 = max(0, min(int(a * fps), len(track) - 1))
            i1 = max(i0 + 1, min(int(b * fps), len(track)))
            out.append((a, b, txt,
                        "top" if track[i0:i1].mean() >= 0.5 else "bottom"))
        return out

    out, cur = [], None
    for (a, b, txt) in bl:
        i0, i1 = int(a * fps), int(b * fps)
        i0 = max(0, min(i0, len(top) - 2))
        i1 = max(i0 + 3, min(i1, len(top)))
        if have_audio:
            st = corr(top[i0:i1], env[i0:i1])
            so = corr(bot[i0:i1], env[i0:i1])
        else:
            st, so = float(top[i0:i1].mean()), float(bot[i0:i1].mean())
        if cur is None:
            cur = "top" if st > so else "bottom"
        elif cur == "top" and so > st + margin:
            cur = "bottom"
        elif cur == "bottom" and st > so + margin:
            cur = "top"
        out.append((a, b, txt, cur))
    return out


def ass(bl, w: int, h: int, split_y: int,
        fontsize: int = CAP_PX, margin_lr: int = 60) -> str:
    def ts(x: float) -> str:
        cs = int(round(x * 100))
        hh, cs = divmod(cs, 360000)
        mm, cs = divmod(cs, 6000)
        ss, cs = divmod(cs, 100)
        return f"{hh:d}:{mm:02d}:{ss:02d}.{cs:02d}"

    # Anchored bottom-centre (alignment 2) with MarginV measured up from the
    # frame bottom, so the block sits ON the seam between the two panels.
    margin_v = h - split_y - 18
    stroke = max(4, round(fontsize / 13))
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{FONT_FAMILY},{fontsize},&H00FFFFFF,&H00000000,&H80000000,0,0,1,{stroke},2,2,{margin_lr},{margin_lr},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    # Per-event vertical placement. \an2 anchors bottom-centre, so the y given
    # is the baseline of the last line. The judge's half is above the split and
    # the defendant's below it, and both hug the split — which is the one thing
    # the earlier caption work got right, because there is no face there.
    lines = []
    for item in bl:
        if len(item) == 4:
            a, b, t, side = item
            y = split_y - 26 if side == "top" else split_y + fontsize + 26
            tag = "{\\an2\\pos(" + str(w // 2) + "," + str(y) + ")}"
            lines.append(f"Dialogue: 0,{ts(a)},{ts(b)},Cap,,0,0,0,,{tag}{t}")
        else:
            a, b, t = item
            lines.append(f"Dialogue: 0,{ts(a)},{ts(b)},Cap,,0,0,0,,{t}")
    return head + "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True, type=Path)
    ap.add_argument("--transcript", required=True, type=Path)
    ap.add_argument("--src-start", type=float, required=True,
                    help="source-time of the short's first frame")
    ap.add_argument("--split-y", type=int, default=960)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--cap", type=int, default=CAP_PX,
                    help="caption size; bigger means fewer words per line")
    ap.add_argument("--margin", type=int, default=60,
                    help="left/right margin; larger forces earlier wrapping")
    ap.add_argument("--max-chars", type=int, default=MAX_CHARS)
    ap.add_argument("--max-words", type=int, default=MAX_WORDS)
    ap.add_argument("--speakers", default=None, type=Path,
                    help="who_speaks.py JSON; puts each caption on the "
                         "speaker's half of the screen")
    ap.add_argument("--no-captions", action="store_true")
    a = ap.parse_args()

    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(a.video)],
        capture_output=True, text=True).stdout.strip())
    dim = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height", "-of", "csv=p=0", str(a.video)],
        capture_output=True, text=True).stdout.strip().split(",")
    w, h = int(dim[0]), int(dim[1])

    d = json.load(open(a.transcript, encoding="utf-8"))
    words = [(x["t"] - a.src_start, x["w"]) for x in d["words"]
             if a.src_start - 0.2 <= x["t"] <= a.src_start + dur]
    track, turns = None, None
    sp = None
    if a.speakers and a.speakers.is_file():
        sp = json.load(open(a.speakers, encoding="utf-8"))
        track, turns = speaker_track(sp, sp.get("fps", 15.0))
        if turns:
            print(f"  {len(turns)} speaker turns detected")
    bl = blocks(words, a.max_chars, a.max_words, turns=turns)
    if sp is not None:
        bl = assign_speakers(bl, sp, sp.get("fps", 15.0), track=track)
        n_top = sum(1 for x in bl if x[3] == "top")
        print(f"  speaker split: {n_top} blocks on the judge's side, "
              f"{len(bl) - n_top} on the defendant's")
    print(f"  {len(words)} words -> {len(bl)} caption blocks over {dur:.1f}s")

    grade = (f"curves=all='{CURVE}',"
             f"eq=saturation={SATURATION:.3f}:contrast={CONTRAST:.3f}")

    work = a.video.parent / f"_{a.video.stem}.ass"
    vf = grade
    font_copy = None
    if not a.no_captions:
        work.write_text(ass(bl, w, h, a.split_y, fontsize=a.cap,
                            margin_lr=a.margin), encoding="utf-8")
        # ffmpeg's filter parser splits options on ":", so an absolute Windows
        # path in fontsdir ("C:/...") is read as an option break and the whole
        # filterchain fails. Copy the face next to the .ass and run with cwd
        # set there, so both are referenced by bare filename.
        import shutil as _sh
        src_font = FONTS / "TTTHeadline-Regular.ttf"
        font_copy = a.video.parent / src_font.name
        if not font_copy.exists():
            _sh.copy(src_font, font_copy)
        vf = f"{grade},ass={work.name}:fontsdir=."

    # -pix_fmt yuv420p is NOT optional.
    #
    # Without it libx264 inherits the higher precision that `curves` and `eq`
    # hand it and picks High 4:4:4 Predictive / yuv444p. Measured on this
    # machine: every captioned short came out 4:4:4 while every other render
    # was 4:2:0. Consumer hardware decoders do not support 4:4:4 H.264 —
    # Windows Photos refused to play them, and phones, TVs and browsers would
    # have done the same. It looks fine in ffplay and fails everywhere else,
    # which is why it survived several renders unnoticed.
    cmd = ["ffmpeg", "-v", "error", "-i", str(a.video.resolve()),
           "-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", "19",
           "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.0",
           "-c:a", "copy", "-movflags", "+faststart", str(a.out.resolve()), "-y"]
    p = subprocess.run(cmd, cwd=str(a.video.parent), capture_output=True, text=True)
    if p.returncode != 0:
        print("\n".join(p.stderr.strip().splitlines()[-12:]))
        return 1
    if work.exists():
        work.unlink()
    if font_copy is not None and font_copy.exists():
        font_copy.unlink()
    print(f"  -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
