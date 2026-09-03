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
import os
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


def face_focus(src: Path, crop: str, a: float, b: float, side: str,
               prefer_x: float | None = None) -> float:
    """Where the SUBJECT is, as a fraction of the tile's width.

    Replaces motion_focus. Nathan, 2026-08-31: *"why isn't the defendant and the
    judge centered in the screen?"* and *"Make sure they're always centered like
    they should be"*.

    Measured on the OFFERUP short before this: the defendant sat +121 to +227px
    right of frame centre and Boyd -266 to -290px left. CLAUDE.md has always
    said each tile is "cropped to the half-canvas and CENTRED ON ITS SUBJECT" -
    but the focus point came from `motion_focus`, whose own docstring admits it
    "centres on neither": it aims at the PEAK OF MOTION. In a courtroom that is
    a bailiff walking past, a door, a gesturing hand - anything but the face.

    This samples faces across the window and takes the MEDIAN x of the largest
    face per frame, so one bad frame cannot drag the framing. Falls back to
    motion_focus, out loud, when no face is found in enough frames.
    """
    import cv2 as _cv2
    import tempfile as _tf
    w, h, x, y = (int(v) for v in re.match(r"crop=(\d+):(\d+):(\d+):(\d+)", crop).groups())
    yunet = str(ROOT / "models" / "yunet2023.onnx")
    if not Path(yunet).exists():
        return motion_focus(src, crop, a, b, side)
    xs = []
    with _tf.TemporaryDirectory() as d:
        step = max(0.5, (b - a) / 12.0)
        t = a
        while t < b:
            fp = str(Path(d) / "f.png")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "%.2f" % t,
                            "-i", str(src), "-frames:v", "1", fp],
                           capture_output=True)
            im = _cv2.imread(fp)
            t += step
            if im is None:
                continue
            tile = im[y:y + h, x:x + w]
            if tile.size == 0:
                continue
            th, tw = tile.shape[:2]
            det = _cv2.FaceDetectorYN.create(yunet, "", (tw, th), 0.6, 0.3, 5000)
            det.setInputSize((tw, th))
            _, r = det.detect(tile)
            if r is None or not len(r):
                continue
            cand = [q for q in r if q[3] >= th * 0.06]
            if not cand:
                continue
            if prefer_x is None:
                # LARGEST FACE IS WRONG and this project already knows it.
                # thumb_pipeline.face_of: "Without it this picks the largest
                # face, and that has now chosen the WRONG PERSON three times:
                # MONKEY the attorney had the larger face in the tile; OFFERUP
                # ditto; CARTHIEF the attorney measured 80px against the
                # defendant's 77px." I wrote this function with max() anyway and
                # it centred the attorney. Only used when no hint exists.
                pick = max(cand, key=lambda q: q[3])
            else:
                want = prefer_x * tw
                pick = min(cand, key=lambda q: abs(q[0] + q[2] / 2.0 - want))
            xs.append(float(pick[0] + pick[2] / 2.0) / tw)
    if len(xs) < 3:
        print(f"    face_focus: only {len(xs)} faces found in the {side} tile "
              f"- falling back to motion")
        return motion_focus(src, crop, a, b, side)
    xs.sort()
    med = xs[len(xs) // 2]
    print(f"    face_focus[{side}]: {len(xs)} samples, subject at {med:.3f} of tile width")
    return med


def judge_tile(src: Path, crops, a: float, b: float, n: int = 8):
    """Which tile holds Judge Boyd - RECOGNISED, never assumed from a side.

    The reference short (SANCHEZ_SHORT_FINAL, Nathan 2026-08-31: "Short that
    you made look nicer than the original footage was Sanchez") and every
    shipped short put the JUDGE ON TOP and the defendant on the bottom, and
    tools/speakers.py reads the mouths on that assumption ("the top tile is
    the bench"). Until 2026-09-02 this script stacked the LEFT source tile on
    top regardless. Boyd sits LEFT in CARTHIEF and RIGHT in SANCHEZ, OFFERUP and
    TORRES, so TORRES rendered upside down: defendant top, judge bottom, and
    the engine died in speakers.py ("face not found") on her downward-looking
    face in the wrong tile.

    Same fix as tools/identity.py made for the thumbnail crops: Boyd is the same
    person in every case, so recognise her (SFace against
    config/boyd_reference.npy) on frames sampled across the clip in each tile.
    Returns (index_of_judge_tile, detail) or (None, detail) when neither tile
    reaches the same-person threshold - the caller aborts, it does not guess.
    """
    import cv2 as _cv2
    import tempfile as _tf
    sys.path.insert(0, str(ROOT / "tools"))
    import identity
    ref = identity.load_reference()
    if ref is None:
        return None, {"error": "config/boyd_reference.npy missing"}
    boxes = []
    for c in crops:
        boxes.append(tuple(int(v) for v in re.match(
            r"crop=(\d+):(\d+):(\d+):(\d+)", c).groups()))
    scores = [[] for _ in crops]
    with _tf.TemporaryDirectory() as d:
        step = max(0.5, (b - a) / float(n))
        t = a
        while t < b:
            fp = str(Path(d) / "f.png")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "%.2f" % t,
                            "-i", str(src), "-frames:v", "1", fp],
                           capture_output=True)
            im = _cv2.imread(fp)
            t += step
            if im is None:
                continue
            for i, (w, h, x, y) in enumerate(boxes):
                tile = im[y:y + h, x:x + w]
                if tile.size == 0:
                    continue
                _, sc = identity.find_judge(tile, ref)
                if sc > -1.0:
                    scores[i].append(float(sc))
    med = [float(np.median(s)) if s else -1.0 for s in scores]
    best = int(np.argmax(med))
    detail = {"median": med, "threshold": identity.COSINE_SAME,
              "samples": [len(s) for s in scores]}
    if med[best] < identity.COSINE_SAME:
        return None, detail
    return best, detail


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
    # Nathan: captions sit on the SPEAKER'S half ("when boyd is talking her
    # captions are on her half of the screen and when the defendant is talking
    # thier captuions are on their half", 2026-08-29). Since 2026-09-02 the
    # judge tile is on TOP (judge_tile()), so Boyd's style B is anchored inside
    # the top tile and the defendant's style D inside the bottom one. Two
    # styles, both bottom-anchored; MarginV places one inside each tile.
    style_top = ("Style: B,Arial Black,72,&H0000E5FF,&H00000000,&H90000000,"
                 "-1,0,0,0,100,100,0,0,1,7,3,2,60,60," + str(HALF + 90) + ",1")
    style_bot = ("Style: D,Arial Black,72,&H00FFFFFF,&H00000000,&H90000000,"
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
    ap.add_argument("--no-master", action="store_true",
                    help="skip loudness mastering. Default is ON: measured "
                         "2026-08-31, unmastered shorts ship ~7dB quiet.")
    ap.add_argument("--allow-rough-cuts", action="store_true",
                    help="ship even if the cut gate fails. Deliberate and "
                         "visible, which is the opposite of the old behaviour "
                         "where a rough cut just printed a line and shipped.")
    ap.add_argument("--no-tighten", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--no-captions", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()

    srcs = sorted(glob.glob(str(ROOT / "work" / args.video / (args.video + "_h_*.mp4"))))
    if not srcs:
        print("no downloaded section for " + args.video)
        return
    # Pick the section that CONTAINS the requested segments, not srcs[0].
    # 2026-09-03: it took srcs[0] blindly. With two sections on disk for one
    # video that silently cuts from the wrong part of the hearing - the segment
    # times are absolute, so a wrong `sec` offset just slides the cut somewhere
    # else in the stream and everything downstream still "succeeds".
    _want = []
    for sp in args.seg:
        x, y = sp.split(":")
        _want.append((float(x), float(y)))
    _lo, _hi = min(a for a, _ in _want), max(b for _, b in _want)
    _cands = []
    for p in srcs:
        mm = re.search(r"_(\d+)-(\d+)\.mp4$", Path(p).name)
        if not mm:
            continue
        a, b = float(mm.group(1)), float(mm.group(2))
        _cands.append((a, b, p))
    _fit = [c for c in _cands if c[0] <= _lo and c[1] >= _hi]
    if not _fit:
        have = ", ".join(f"{a:.0f}-{b:.0f}" for a, b, _ in _cands) or "none parseable"
        print(f"no downloaded section covers {_lo:.1f}-{_hi:.1f} for {args.video}; "
              f"sections on disk: {have}. Pull the span first "
              f"(scripts/prefetch_sources.py) rather than cutting from the wrong one.")
        return
    # the tightest covering section
    _fit.sort(key=lambda c: c[1] - c[0])
    src = Path(_fit[0][2])
    sec = _fit[0][0]
    if len(_cands) > 1:
        print(f"    source section {src.name} (covers {sec:.0f}-{_fit[0][1]:.0f}, "
              f"chosen because it contains {_lo:.1f}-{_hi:.1f})")

    segs = []
    for sp in args.seg:
        x, y = sp.split(":")
        segs.append((float(x) - sec, float(y) - sec))

    crops = render.detect_tile_crops(src)
    if not crops:
        print("tiles not measurable; aborting rather than guessing")
        return
    # JUDGE ON TOP, DEFENDANT ON THE BOTTOM - by recognition. detect_tile_crops
    # returns (left, right) and this used to stack them in that order, which
    # is only right when Boyd happens to sit on the left (CARTHIEF). See
    # judge_tile().
    _ji, _jd = judge_tile(src, crops, segs[0][0], segs[-1][1])
    if _ji is None:
        print(f"    judge not recognised in either tile {_jd}; aborting rather "
              f"than guessing which one is the bench")
        return
    crops = (crops[1 - _ji], crops[_ji])     # crops[0] = defendant, crops[1] = judge
    print(f"    judge recognised in the {'left' if _ji == 0 else 'right'} source "
          f"tile (median cosine {_jd['median'][_ji]:.3f} vs "
          f"{_jd['median'][1 - _ji]:.3f}, {_jd['samples']} samples) "
          f"-> judge tile on TOP, defendant BELOW")
    # FACE, not motion. See face_focus() - motion_focus aims at whatever moved
    # most, which in a courtroom is rarely the person the clip is about.
    # sample across the WHOLE clip, not just segs[0]. A focus taken from the
    # first segment is applied to every frame, so if the subject shifts at all
    # the framing is wrong for most of the video - measured mean offset 109px
    # with a first-segment focus, against 174px for motion.
    _fa, _fb_t = segs[0][0], segs[-1][1]
    # WHICH person, from the case file. `defendant_at` is his x as a fraction of
    # the FULL FRAME; the top tile is a window into that frame, so convert.
    _pref = None
    try:
        _cases = json.loads((ROOT / "config" / "cases.json").read_text(encoding="utf-8"))
        _hit = next((c for c in _cases.values()
                     if str(args.video) in str(c.get("video", ""))), None)
        if not _hit:
            print("    NO CASE MATCHED - falling back to largest face, which "
                  "has picked the attorney before")
        elif _hit.get("defendant_at") is None:
            print(f"    case matched but defendant_at is UNSET - falling back to "
                  f"largest face. Set it in config/cases.json.")
        if _hit and _hit.get("defendant_at") is not None:
            _sw, _sh = render.probe_dimensions(src)
            _tw, _th, _tx, _ty = (int(v) for v in re.match(
                r"crop=(\d+):(\d+):(\d+):(\d+)", crops[0]).groups())
            _pref = (float(_hit["defendant_at"]) * _sw - _tx) / float(_tw)
            if not (0.0 <= _pref <= 1.0):
                print(f"    defendant_at {_hit['defendant_at']} lands OUTSIDE the "
                      f"tile the judge was NOT recognised in ({_pref:.3f}) - the "
                      f"case file and the recognition disagree; aborting")
                return
            print(f"    defendant_at {_hit['defendant_at']} -> {_pref:.3f} of the defendant tile")
    except Exception as _e:
        print(f"    (no defendant_at hint: {_e})")
    ft = face_focus(src, crops[0], _fa, _fb_t, "left", prefer_x=_pref)
    fb = face_focus(src, crops[1], _fa, _fb_t, "any")
    slot = W / float(HALF)
    # ZOOM SO THE SUBJECT CAN ACTUALLY BE CENTRED.
    # plan_fill_window clamps the window to the tile, so a subject near an edge
    # ends up off-centre rather than the window running off the picture. On
    # OFFERUP the defendant sits at 0.737 of his tile's width: at the natural
    # window size the clamp leaves him ~109px right of centre no matter what
    # focus you pass. Narrowing the window (zoom) gives the focus room to move.
    # Computed per tile from how far off-centre the subject actually is, capped
    # so a subject dead-centre is never needlessly magnified.
    def _zoom_for(f):
        edge = min(f, 1.0 - f)          # distance to the nearer tile edge
        need = 0.5 / max(edge, 0.05)    # half-window must fit inside that
        return float(min(1.45, max(1.0, need * 0.62)))
    zt, zb = _zoom_for(ft), _zoom_for(fb)
    print("zoom   defendant(bottom) %.2f  judge(top) %.2f" % (zt, zb))
    # crops[0] is the DEFENDANT (framed on defendant_at), crops[1] the JUDGE.
    # The judge's window goes on TOP, the defendant's BELOW - the reference
    # order (judge_tile docstring); short_engine gate "judge on top" measures
    # it on the output.
    bot = render.plan_fill_window(crops[0], slot, (ft, 0.42), zoom=zt)
    top = render.plan_fill_window(crops[1], slot, (fb, 0.42), zoom=zb)
    print("focus  defendant(bottom) %.2f  judge(top) %.2f" % (ft, fb))

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
        return 1          # was a bare `return` -> exit code 0 on a FAILED render
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
        _cut_bad, _cut_total, _cut_err = _bad, len(keep), None
    except Exception as _e:                          # noqa: BLE001
        # NOT "not checked, carry on". Measured 2026-08-31: SHORT_monkey-plan1
        # shipped with 5 of 5 cuts defective - 3 opening 1.5-3.1s INTO speech,
        # 4 landing mid-word - and nothing stopped it, because this check
        # printed a line and the build continued. A check that cannot fail a
        # build is a comment.
        _cut_bad, _cut_total, _cut_err = None, 0, str(_e)[:120]
        print("cut quality: COULD NOT BE CHECKED (%s)" % _cut_err)

    side.write_text(json.dumps({"video": args.video, "section_start_s": sec,
                                "duration_s": round(acc, 2), "pieces": pieces},
                               indent=1), encoding="utf-8")
    # ------------------------------------------------------------ MASTERING
    # Measured 2026-08-31: every shipped file sat at -20.5 to -21.9 LUFS with
    # 5dB of headroom unused, i.e. audibly quieter than everything beside it in
    # a feed. scripts/assemble_final.py already did this correctly and was
    # called by NOTHING - it is hardcoded to one case's paths, which is why it
    # never became part of the pipeline. tools/master_audio.py is the same maths
    # with a file in and a file out.
    #
    # In-place, video stream-copied, so it costs seconds and cannot re-encode
    # the picture.
    if not getattr(args, "no_master", False):
        try:
            sys.path.insert(0, str(ROOT / "tools"))
            import master_audio as _ma
            _tmp = out.with_name(out.stem + "_m.mp4")
            _b, _a, _ = _ma.master(str(out), str(_tmp))
            os.replace(str(_tmp), str(out))
            print(NL + "mastered: %.1f -> %.1f LUFS (%+.1f dB), true peak %.1f dBFS"
                  % (_b[0], _a[0], _a[0] - _b[0], _a[2]))
            if not (-15.0 <= _a[0] <= -13.5):
                print("  LOUDNESS GATE FAILED: %.1f LUFS is outside -14 +/- 1"
                      % _a[0])
                if not getattr(args, "allow_rough_cuts", False):
                    return 1
        except Exception as _me:                     # noqa: BLE001
            # Not "carry on quietly" - that is how assemble_final went unused.
            print(NL + "MASTERING FAILED: %s" % str(_me)[:160])
            print("  Shipping an unmastered file is a decision, not a default.")
            if not getattr(args, "allow_rough_cuts", False):
                return 1

    print(NL + "-> " + str(out) + "  %.1f MB" % (out.stat().st_size / 1e6))
    print("   map -> " + side.name + "  (%d pieces)" % len(pieces))

    # ------------------------------------------------------------------ GATE
    # Nathan, 2026-08-31: "that makes sense why my edits are always choppy".
    # It was not the audio - measured, the AAC join discontinuity is 0.31x a
    # normal speech transient, so there is no click. It is cut PLACEMENT:
    # SHORT_monkey-plan1 audited at 5 of 5 cuts defective, 4 of them landing
    # mid-word, and it shipped anyway.
    #
    # scripts/audit_cuts.py has existed for exactly this since the last time he
    # said the same thing ("it could just be cut a tad bit better") and an audit
    # on 2026-08-31 found it referenced by ZERO other files. Every check in this
    # repo that nothing calls has silently stopped protecting anything.
    #
    # So this exits NON-ZERO. --allow-rough-cuts ships it anyway, deliberately
    # and visibly, which is a different thing from not noticing.
    if _cut_bad is None:
        print(NL + "CUT GATE: COULD NOT RUN (%s)" % _cut_err)
        print("  Refusing to call this shippable. A check that failed to run is"
              " not a check that passed.")
        if not getattr(args, "allow_rough_cuts", False):
            return 1
    elif _cut_bad:
        print(NL + "CUT GATE FAILED: %d of %d cuts are rough" % (_cut_bad, _cut_total))
        print("  Rough = opens past the first syllable, opens on dead air, or"
              " cuts mid-word. This is what 'choppy' sounds like.")
        print("  Re-cut, or pass --allow-rough-cuts to ship it knowingly.")
        if not getattr(args, "allow_rough_cuts", False):
            return 1
    else:
        print(NL + "CUT GATE PASS: all %d cuts land on speech boundaries" % _cut_total)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)     # main() returned into the void; gates need an exit code
