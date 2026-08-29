"""Cut a vertical short from a hearing - the advert for the long-form.

Nathan, 2026-08-21:
  "the defendant and boy have to be in the middle of the screen so scoot them
   over ... you're not editing the short cuts good enough"
  "you could reorder the shorts for the hook just not long form"
  "it could be UP TO 60 seconds ... you could have included more at the ending
   and then finish it with no contact with blah blah blah and kash the spider
   monkey ... actually make it to where I can precisely edit this short quickly"

A short is composed from SEGMENTS given in playback order:

    --seg 6235.5:6277  --seg 6673:6687.5

They play in the order written, which need not be chronological. Reordering is
permitted on shorts and forbidden on long-form (SAFETY_RULES R5).

FRAMING. A tile holding two people is bimodal in movement - defendant left,
attorney right - so centring on the tile's middle lands in the gap between them
and centres on neither. The focus point is the PEAK of motion per side.

TIGHTENING. Silence runs are removed and the pieces butted together. Cut with
paired trim/atrim, never select/aselect: with select the video shortened to
33.6s while the audio stayed 41.5s and the result was silently out of sync.
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np                              # noqa: E402
from boydclips import render                    # noqa: E402

W, H = 1080, 1920
HALF = H // 2
NL = chr(10)
LIMIT_S = 60.0


def ass_time(t: float) -> str:
    cs = int(round(max(0.0, t) * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return "%d:%02d:%02d.%02d" % (h, m, s, cs)


def motion_focus(src: Path, crop: str, a: float, b: float, side: str) -> float:
    w, h, x, y = (int(v) for v in re.match(r"crop=(\d+):(\d+):(\d+):(\d+)", crop).groups())
    sw, sh = render.probe_dimensions(src)
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", "%.2f" % a, "-i", str(src),
         "-t", "%.2f" % (b - a), "-vf", "fps=2", "-pix_fmt", "gray",
         "-f", "rawvideo", "-"], capture_output=True, timeout=900)
    n = len(p.stdout) // (sw * sh)
    if n < 4:
        return 0.5
    st = np.frombuffer(p.stdout[: n * sw * sh], np.uint8).reshape(n, sh, sw).astype(np.float32)
    col = st[:, y:y + h, x:x + w].std(axis=0).mean(axis=0)
    col = col - col.min()
    if col.max() <= 0:
        return 0.5
    if side == "left":
        return float(np.argmax(col[: len(col) // 2])) / w
    return float(np.argmax(col)) / w


def keep_intervals(src: Path, a: float, b: float, pad: float = 0.12,
                   min_gap: float = 0.40) -> list:
    """Spans of (a,b) worth keeping, silence removed. Absolute file times."""
    sil = render.detect_silences(src, noise_db=-32.0, min_silence_s=min_gap)
    keep, cur = [], a
    for s, e in sil:
        if e <= a or s >= b:
            continue
        s = max(a, s) + pad
        e = min(b, e) - pad
        if e - s < 0.15:
            continue
        if s > cur:
            keep.append((cur, s))
        cur = max(cur, e)
    if cur < b:
        keep.append((cur, b))
    return [k for k in keep if k[1] - k[0] > 0.25]


BOYD_TELL = re.compile(r"^\s*(all right|alright|okay so|so,? here|here's the thing)"
                       r"|i'?m gonna|i'?m going to|let me|the court"
                       r"|do you understand|guess what", re.I)
DEFER_TELL = re.compile(r"your honou?r|yes,? ma'?am|no,? ma'?am|yes,? sir", re.I)


def speaker_turns(words, sec):
    """Split into >> turns and guess who is speaking.

    Deference markers alone do not work - across the monkey riff nobody says
    "your honor" and every turn came back unclassified. Her real tell is how she
    opens: "All right", "I'm gonna", "Let me". Everything else is taken to be
    the other party. Approximate, and wrong on a bare "Yeah", but it puts the
    right captions on the right side of the line most of the time.
    """
    turns, cur = [], []
    for x in words:
        w = x.get("w", "")
        t = x.get("t", 0.0) - sec
        if w.strip().startswith(">>"):
            if cur:
                turns.append(cur)
            cur = [(t, w.strip()[2:].strip())]
        else:
            cur.append((t, w))
    if cur:
        turns.append(cur)
    out = []
    for tn in turns:
        txt = " ".join(w for _, w in tn if w).strip()
        boyd = bool(BOYD_TELL.search(txt)) or (len(txt.split()) > 22
                                               and not DEFER_TELL.search(txt))
        for t, w in tn:
            out.append((t, w, boyd))
    return out


def build_ass(words, sec: float, keep, path: Path, per: int = 3) -> None:
    """Captions across pieces in PLAYBACK order, which may be non-chronological.

    Placed in the lower third of the top tile. Centred on the seam, they
    collided with the "187th Court" label burned into the source.
    """
    # Nathan: "the defendant's captions are supposed to be above the line, and
    # then Judge Boyd's captions are supposed to be below". Two styles, both
    # bottom-anchored; MarginV places one inside each tile.
    style_top = ("Style: D,Arial Black,72,&H00FFFFFF,&H00000000,&H90000000,"
                 "-1,0,0,0,100,100,0,0,1,7,3,2,60,60," + str(HALF + 90) + ",1")
    style_bot = ("Style: B,Arial Black,72,&H0000E5FF,&H00000000,&H90000000,"
                 "-1,0,0,0,100,100,0,0,1,7,3,2,60,60,90,1")
    fmt = ("Format: Name,Fontname,Fontsize,PrimaryColour,OutlineColour,"
           "BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,"
           "Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,"
           "MarginV,Encoding")
    head = NL.join([
        "[Script Info]", "ScriptType: v4.00+",
        "PlayResX: " + str(W), "PlayResY: " + str(H),
        "WrapStyle: 2", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]", fmt, style_top, style_bot, "",
        "[Events]",
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
        "",
    ])

    tagged = speaker_turns(words, sec)
    rows, chunk, acc, cur_boyd = [], [], 0.0, None

    def flush(pad):
        if chunk:
            rows.append((chunk[0][0], chunk[-1][0] + pad,
                         " ".join(c[1] for c in chunk), cur_boyd))

    for ks, ke in keep:
        for t, w, boyd in tagged:
            if not (ks <= t <= ke):
                continue
            txt = w.replace(">>", "").strip()
            if not txt:
                continue
            if cur_boyd is None:
                cur_boyd = boyd
            if boyd != cur_boyd:          # speaker changed: close the caption
                flush(0.6)
                chunk = []
                cur_boyd = boyd
            chunk.append((acc + (t - ks), txt))
            if len(chunk) >= per:
                flush(0.6)
                chunk = []
        acc += ke - ks
    flush(0.8)

    out = []
    for i, (a0, a1, txt, boyd) in enumerate(rows):
        if i + 1 < len(rows):
            a1 = min(a1, rows[i + 1][0])
        if a1 - a0 < 0.25:
            a1 = a0 + 0.25
        txt = txt.replace("{", "").replace("}", "")
        st = "B" if boyd else "D"          # B = Boyd, below the line
        out.append("Dialogue: 0," + ass_time(a0) + "," + ass_time(a1)
                   + "," + st + ",,0,0,0,," + txt)
    path.write_text(head + NL.join(out) + NL, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--seg", action="append", required=True,
                    help="START:END in absolute source seconds; repeatable, "
                         "plays in the order given")
    ap.add_argument("--out", required=True)
    # Exact is the DEFAULT. Tightening used to be on, and it silently re-cut what
    # the editor had already decided: a hand-picked 12.0s segment came out as 7
    # pieces totalling 9.16s. Measured, not guessed. The editor is authoritative
    # about where a cut starts and ends; this renders what it was handed.
    ap.add_argument("--tighten", action="store_true",
                    help="remove silence INSIDE each segment (off by default; it "
                         "moves cuts the editor already placed)")
    ap.add_argument("--captions", action="store_true",
                    help="burn captions (off by default - speaker attribution and "
                         "the auto-transcript are both still wrong)")
    # accepted so older commands keep working; they are the defaults now
    ap.add_argument("--no-tighten", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--no-captions", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()

    srcs = sorted(glob.glob(str(ROOT / "work" / args.video / (args.video + "_h_*.mp4"))))
    if not srcs:
        print("no downloaded section for " + args.video)
        return
    src = Path(srcs[0])
    m = re.search(r"_(\d+)-(\d+)\.mp4$", src.name)
    sec = float(m.group(1)) if m else 0.0

    segs = []
    for sp in args.seg:
        x, y = sp.split(":")
        segs.append((float(x) - sec, float(y) - sec))

    crops = render.detect_tile_crops(src)
    if not crops:
        print("tiles not measurable; aborting rather than guessing")
        return
    ft = motion_focus(src, crops[0], segs[0][0], segs[0][1], "left")
    fb = motion_focus(src, crops[1], segs[0][0], segs[0][1], "any")
    slot = W / float(HALF)
    top = render.plan_fill_window(crops[0], slot, (ft, 0.42))
    bot = render.plan_fill_window(crops[1], slot, (fb, 0.42))
    print("focus  top %.2f  bottom %.2f" % (ft, fb))

    keep = []
    for s0, s1 in segs:
        keep += keep_intervals(src, s0, s1) if args.tighten else [(s0, s1)]
    kept = sum(e - s for s, e in keep)
    raw = sum(y - x for x, y in segs)
    print("segments %d   pieces %d   %.1fs of %.1fs (%.0f%%)"
          % (len(segs), len(keep), kept, raw, 100 * kept / max(1e-9, raw)))
    if kept > LIMIT_S:
        print("  WARNING: %.1fs exceeds the %.0fs Shorts limit" % (kept, LIMIT_S))

    if args.captions:
        tj = glob.glob(str(ROOT / "work" / args.video / "*.transcript.json"))
        ws = json.load(open(tj[0], encoding="utf-8"))["words"]
        build_ass(ws, sec, keep, ROOT / "work" / "_short.ass")

    parts, labels = [], ""
    for i, (s, e) in enumerate(keep):
        parts.append("[0:v]trim=%.3f:%.3f,setpts=PTS-STARTPTS[v%d];" % (s, e, i))
        parts.append("[0:a]atrim=%.3f:%.3f,asetpts=PTS-STARTPTS[a%d];" % (s, e, i))
        labels += "[v%d][a%d]" % (i, i)
    vf = ("".join(parts)
          + labels + "concat=n=%d:v=1:a=1[cv][aa];" % len(keep)
          + "[cv]split=2[p][q];"
          + "[p]" + top + ",scale=%d:%d,setsar=1[t];" % (W, HALF)
          + "[q]" + bot + ",scale=%d:%d,setsar=1[u];" % (W, HALF)
          + "[t][u]vstack=inputs=2[vv]"
          + (";[vv]subtitles=_short.ass[vc]" if args.captions else ""))
    last = "[vc]" if args.captions else "[vv]"

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(src.resolve()),
           "-filter_complex", vf, "-map", last, "-map", "[aa]",
           "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-r", "30",
           "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
           str(out.resolve())]
    p = subprocess.run(cmd, cwd=str(ROOT / "work"), capture_output=True,
                       text=True, timeout=2400)
    if p.returncode != 0:
        print("ffmpeg failed: " + p.stderr.strip()[:400])
        return
    # Sidecar map so the short can be edited on its OWN timeline later. The
    # short is shorter than the span it came from - silence was removed - so a
    # mark at 0:20 in the short is not 0:20 in the hearing. Each piece records
    # where it starts in the short and where it came from in the source.
    pieces, acc = [], 0.0
    for ks, ke in keep:
        pieces.append({"short_start": round(acc, 3),
                       "short_end": round(acc + (ke - ks), 3),
                       "src_start": round(ks + sec, 2),
                       "src_end": round(ke + sec, 2)})
        acc += ke - ks
    side = out.with_suffix(".map.json")
    # ---- guard: report the quality of every cut we just rendered -------------
    # Nathan noticed "it could just be cut a tad bit better" only by watching.
    # This makes it visible at render time instead, so a bad cut cannot ship
    # quietly again.
    try:
        from boydclips import refine as _rf
        _sil = render.detect_silences(src, noise_db=-32.0, min_silence_s=0.18)
        _sp = _rf.speech_spans(_sil, 0.0, 1e9)
        _bad = 0
        print("cut quality:")
        for _i, (_a, _b) in enumerate(keep, 1):
            _bi = _rf._burst_at(_sp, _a)
            if _bi and _a - _bi[0] > 0.12:
                _in = "opens %.2fs INTO speech" % (_a - _bi[0])
            elif not _bi:
                _n = _rf._next_start(_sp, _a)
                _in = ("opens on %.2fs of dead air" % (_n - _a)) if _n and _n - _a > 0.35 else "clean in"
            else:
                _in = "clean in"
            _bo = _rf._burst_at(_sp, _b)
            _out = "cuts MID-WORD" if _bo else "clean out"
            if _in != "clean in" or _out != "clean out":
                _bad += 1
                print("  %d. %-32s %s" % (_i, _in, _out))
        if _bad:
            print("  %d of %d cuts are rough - 'Tighten to speech' in the editor fixes them"
                  % (_bad, len(keep)))
        else:
            print("  all %d cuts land on speech boundaries" % len(keep))
    except Exception as _e:                          # noqa: BLE001
        print("cut quality: not checked (%s)" % str(_e)[:80])

    side.write_text(json.dumps({"video": args.video, "section_start_s": sec,
                                "duration_s": round(acc, 2), "pieces": pieces},
                               indent=1), encoding="utf-8")
    print(NL + "-> " + str(out) + "  %.1f MB" % (out.stat().st_size / 1e6))
    print("   map -> " + side.name + "  (%d pieces)" % len(pieces))


if __name__ == "__main__":
    main()
