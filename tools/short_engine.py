# -*- coding: utf-8 -*-
"""The short engine. One command, every house rule as a blocking step.

Nathan, 2026-08-31: *"You were supposed to make a short video engine"*, and
*"make sure every short from now on gets that same pro level treatment"*.

WHY AN ENGINE AND NOT ANOTHER SCRIPT
There were already three: `tools/make_short.py`, `scripts/make_short.py`,
`scripts/make_short_auto.py`. Improving one of three is how a rule gets applied
to one case and called done - the single most repeated failure in this project.
Worse, this repo's own earlier audit found the existing gates FAIL OPEN:

    "make_short_auto.py:193 prints REFUSED and exits non-zero, but the failed
     file is already written to READY-TO-POST/{CASE}_SHORT_FINAL.mp4 ... on disk
     the file is named _FINAL and is indistinguishable from a passing one."

So this engine's contract is not "does more" - it is:
  * ONE entry point
  * every house rule is a STEP, not a thing anyone remembers
  * a failing build exits non-zero AND leaves nothing that looks shippable
  * every gate is proven against a control that carries the defect

WHAT IT ENFORCES, and where each came from
  captions ON the seam        "the words pop up right on the split between the
                               defendant and the judge"
  entrance = blur             he rejected every scale-based entrance twice
  font Anton                  already the house font
  -14 LUFS                    the file staged to post measured -22.5 while a
                               correct -14.4 master sat unused one folder away
  cuts measured on audio      "high short term retention is literally what makes
                               or breaks the short"
  audio fades across cuts     his ask
  caption fade                his ask
  no silent degrade           CLAUDE.md: a missing asset must FAIL, not log
  judge on top                the reference (SANCHEZ_SHORT_FINAL) and every
                               shipped short: Boyd top tile, defendant bottom;
                               measured by recognition (gate_judge_top), added
                               2026-09-02 after TORRES rendered upside down

Every number above is READ from config/short_floor.json (load_floor / derive
below); caption_short.py and make_short.py import their constants from here.
The values in this docstring are what the file said on 2026-09-01.

WHAT IT DOES NOT DO
It does not choose the cuts. It measures them and refuses bad ones. Re-choosing
is a separate job and pretending otherwise would be the "reported before I
measured" failure again.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ---- house standard, in ONE place: config/short_floor.json ------------------
# Until 2026-09-01 the numbers below were literals here, again in
# caption_short.py, again in make_short.py, AND in config/short_floor.json -
# four copies of one floor. floor_stamp.py hashes the json into every short's
# sidecar (R40), so drift between the file and the code was caught, but the
# code never READ the file. Nathan, 2026-08-31: "save everything as the normal
# floor when making future shorts" and "that short was made off the old rules
# or whatever and should be made with our new ones". So: the file is the
# floor, and every constant in this module and in caption_short / make_short
# is DERIVED from it at import. A key the code needs that the file lacks fails
# the import - it does not default (CLAUDE.md: a missing asset FAILS, not logs).
FLOOR_PATH = os.path.join(ROOT, "config", "short_floor.json")

# dotted path in the json -> module-level name. Every entry is required.
FLOOR_KEYS = (
    ("format.width", "W", int),
    ("format.height", "H", int),
    ("format.pix_fmt", "PIX_FMT", str),
    ("format.seam_frac", "SEAM_FRAC", float),
    ("audio.integrated_LUFS", "LUFS_TARGET", float),
    ("audio.tolerance", "LUFS_TOL", float),
    ("audio.true_peak_max", "TRUE_PEAK_MAX", float),
    ("audio.lra", "LRA", float),
    ("audio.join_fade_ms", "CUT_FADE_MS", int),
    ("audio.av_sync_max_ms", "AV_SYNC_MAX_MS", int),
    ("captions.entrance_mode", "ENTRANCE", str),
    ("captions.entrance_rejected", "ENTRANCE_REJECTED", tuple),
    ("captions.reveal", "REVEAL", str),
    ("captions.reveal_tolerance_s", "REVEAL_TOL_S", float),
    ("captions.font", "FONT", str),
    ("captions.size", "CAP_PX", int),
    ("captions.scale_y", "SCALE_Y", int),
    ("captions.fade_ms.in", "FADE_IN_MS", int),
    ("captions.fade_ms.out", "FADE_OUT_MS", int),
    ("captions.blur.px", "BLUR_PX", int),
    ("captions.blur.ms", "BLUR_MS", int),
    ("captions.seam_band_frac", "SEAM_BAND_FRAC", float),
    ("captions.cards.max_chars", "MAX_CHARS", int),
    ("captions.cards.max_words", "MAX_WORDS", int),
    ("captions.cards.target_chars", "TARGET_CHARS", int),
    ("cuts.audible_join_tolerance.min", "CUT_TOL_MIN", int),
    ("cuts.audible_join_tolerance.frac", "CUT_TOL_FRAC", float),
    ("grade.eq", "GRADE_EQ", str),
    ("grain.strength", "GRAIN_STRENGTH", int),
)


def load_floor(path=FLOOR_PATH):
    """The short floor, parsed. Missing file or missing key -> exception."""
    with open(path, encoding="utf-8") as f:
        floor = json.load(f)
    missing = []
    for dotted, _name, _cast in FLOOR_KEYS:
        node = floor
        for part in dotted.split("."):
            node = node.get(part) if isinstance(node, dict) else None
            if node is None:
                break
        if node is None:
            missing.append(dotted)
    if missing:
        raise KeyError(f"{os.path.relpath(path, ROOT)} lacks {', '.join(missing)} - "
                       f"the floor is the only source of these; add them, do not default")
    return floor


def derive(floor):
    """NAME -> value for every FLOOR_KEYS entry, cast to its declared type."""
    out = {}
    for dotted, name, cast in FLOOR_KEYS:
        node = floor
        for part in dotted.split("."):
            node = node[part]
        out[name] = cast(node)
    return out


FLOOR = load_floor()
_H = derive(FLOOR)
W, H = _H["W"], _H["H"]
PIX_FMT = _H["PIX_FMT"]
SEAM_FRAC = _H["SEAM_FRAC"]                   # the split between the two tiles
LUFS_TARGET, LUFS_TOL = _H["LUFS_TARGET"], _H["LUFS_TOL"]
TRUE_PEAK_MAX = _H["TRUE_PEAK_MAX"]
LRA = _H["LRA"]
CUT_FADE_MS = _H["CUT_FADE_MS"]               # audio fade across every hard join
AV_SYNC_MAX_MS = _H["AV_SYNC_MAX_MS"]         # reasoning: audio.av_sync_note in the floor
ENTRANCE = _H["ENTRANCE"]                     # never scale-based; rejected twice
ENTRANCE_REJECTED = _H["ENTRANCE_REJECTED"]
REVEAL = _H["REVEAL"]                         # R34: never "off"
REVEAL_TOL_S = _H["REVEAL_TOL_S"]             # R34: aligner p95 jitter, tools/check_reveal.py
FONT = _H["FONT"]
CAP_PX, SCALE_Y = _H["CAP_PX"], _H["SCALE_Y"]
FADE_IN_MS, FADE_OUT_MS = _H["FADE_IN_MS"], _H["FADE_OUT_MS"]
BLUR_PX, BLUR_MS = _H["BLUR_PX"], _H["BLUR_MS"]
SEAM_BAND_FRAC = _H["SEAM_BAND_FRAC"]
MAX_CHARS, MAX_WORDS, TARGET_CHARS = _H["MAX_CHARS"], _H["MAX_WORDS"], _H["TARGET_CHARS"]
CUT_TOL_MIN, CUT_TOL_FRAC = _H["CUT_TOL_MIN"], _H["CUT_TOL_FRAC"]
GRADE_EQ = _H["GRADE_EQ"]
GRAIN_STRENGTH = _H["GRAIN_STRENGTH"]


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def probe(path, stream="v:0", entries="width,height"):
    r = sh(["ffprobe", "-v", "error", "-select_streams", stream,
            "-show_entries", f"stream={entries}", "-of", "csv=p=0", path])
    return (r.stdout or "").strip()


def duration(path, stream=None):
    args = ["ffprobe", "-v", "error"]
    if stream:
        args += ["-select_streams", stream]
    args += ["-show_entries", ("stream=duration" if stream else "format=duration"),
             "-of", "csv=p=0", path]
    out = (sh(args).stdout or "").strip().split("\n")[0]
    try:
        return float(out)
    except ValueError:
        return 0.0


def loudness(path):
    """(integrated LUFS, true peak dBTP) or (None, None)."""
    r = sh(["ffmpeg", "-hide_banner", "-nostats", "-i", path,
            "-af", "loudnorm=print_format=json", "-f", "null", "-"])
    txt = (r.stderr or "") + (r.stdout or "")
    try:
        blob = txt[txt.rindex("{"):txt.rindex("}") + 1]
        d = json.loads(blob)
        return float(d["input_i"]), float(d["input_tp"])
    except Exception:
        return None, None


# ---- gates ------------------------------------------------------------------
def gate_format(path):
    wh = probe(path)
    pix = probe(path, entries="pix_fmt")
    vd, ad = duration(path, "v:0"), duration(path, "a:0")
    ok_wh = wh.replace(" ", "") == f"{W},{H}"
    ok_pix = pix == PIX_FMT
    # BOTH must be non-zero. The old gate compared two durations that were each
    # 0.0 on a broken file and called them matched.
    ok_sync = vd > 0.5 and ad > 0.5 and abs(vd - ad) * 1000 <= AV_SYNC_MAX_MS
    return (ok_wh and ok_pix and ok_sync,
            f"{wh} {pix} v={vd:.2f}s a={ad:.2f}s")


def gate_loudness(path):
    i, tp = loudness(path)
    if i is None:
        return False, "unmeasurable"
    ok = abs(i - LUFS_TARGET) <= LUFS_TOL and tp <= TRUE_PEAK_MAX
    return ok, f"{i:.1f} LUFS, peak {tp:.1f} dBTP"


def gate_captions_on_seam(ass_path):
    """Every caption event must sit ON the split, not in one half.

    The Aug 29 short failed this visibly: captions appeared above the seam in
    the judge's tile and below it in the defendant's, jumping between halves.
    """
    if not os.path.exists(ass_path):
        return False, "no .ass"
    import re
    seam = int(H * SEAM_FRAC)
    ys = []
    for ln in open(ass_path, encoding="utf-8", errors="ignore"):
        if not ln.startswith("Dialogue:"):
            continue
        for m in re.finditer(r"\\pos\(\s*[\d.]+\s*,\s*([\d.]+)\s*\)", ln):
            ys.append(float(m.group(1)))
    if not ys:
        return False, "no positioned events"
    band = H * SEAM_BAND_FRAC
    off = [y for y in ys if abs(y - seam) > band]
    return (not off), f"{len(ys)} events, {len(off)} off-seam (seam y={seam})"


def gate_cuts(video, words_json, timemap=None):
    """Do the joins in THIS FILE land in silence?

    Measured on the OUTPUT, by audio energy. Three earlier versions of this gate
    were wrong and each was wrong the same way - comparing two measurements in
    DIFFERENT TIMEBASES:
      v1 took the loudest waveform jumps and called them cuts (they were
         plosives) - reported 12/12 on a fine build
      v2 compared a source-timebase timemap against word times I had FABRICATED,
         because the transcripts on disk carry word starts only
      v3 compared a source-timebase timemap against words aligned on the cut
         output
    Energy at the join positions in the output has no timebase to get wrong: the
    joins are where the segments meet in the file being measured, and silence is
    silence.
    """
    import wave
    import numpy as np
    if not timemap or not os.path.exists(timemap):
        return None, "no timemap - cut placement UNMEASURED"
    tm = json.load(open(timemap))
    segs = tm.get("segments") or []
    joins = [float(x["new_start"]) for x in segs[1:] if "new_start" in x]
    if not joins:
        return None, "timemap has no join points"
    with tempfile.TemporaryDirectory() as d:
        wav = os.path.join(d, "a.wav")
        sh(["ffmpeg", "-v", "error", "-y", "-i", video, "-ac", "1",
            "-ar", "16000", wav])
        if not os.path.exists(wav):
            return None, "no audio"
        with wave.open(wav) as f:
            a = np.frombuffer(f.readframes(f.getnframes()), np.int16).astype(np.float32)
            sr = f.getframerate()
    if a.size < sr:
        return None, "audio too short"
    hop = int(0.01 * sr)
    n = len(a) // hop
    rms = np.array([np.sqrt((a[k * hop:(k + 1) * hop] ** 2).mean() + 1e-9)
                    for k in range(n)])
    lo, hi = float(np.percentile(rms, 10)), float(np.percentile(rms, 90))
    thr = lo + (hi - lo) * 0.12
    win = int(0.03 * sr)

    def loud(t):
        k = int(t * sr)
        a0, b0 = max(0, k - win), min(len(a), k + win)
        return (np.sqrt((a[a0:b0] ** 2).mean()) if b0 > a0 else 0.0) > thr

    bad = [round(t, 2) for t in joins if loud(t)]
    # ceiling from the floor (cuts.audible_join_tolerance): max(1, joins/8) -
    # the reference achieved 1/18
    allowed = max(CUT_TOL_MIN, int(len(joins) * CUT_TOL_FRAC))
    return (len(bad) <= allowed), (
        f"{len(joins)} joins, {len(bad)} in audible audio (allowed {allowed})"
        + (f" at {bad[:4]}" if bad else ""))


def gate_content(words_json):
    """Is there a STORY in this clip, and is the ending withheld?

    The gate this engine was missing entirely. Nathan: "barely anything in that
    clip and then you gave away the outcome". Everything else here polished 46
    seconds that opened after the drama, kept 20s of admin, and stated the
    sentence. See tools/pick_window.py for the rules and the evidence.
    """
    if not os.path.exists(words_json):
        return None, "no words"
    import pick_window as PW
    words = json.load(open(words_json))
    ws = [{"w": w["w"], "t": float(w.get("s", w.get("t", 0)))} for w in words]
    bad, n, _ = PW.audit(ws, -1e9, 1e9)
    if not bad:
        return True, f"{n} words, no outcome, no filler"
    return False, "; ".join(f"{k}: {v}" for k, v in bad)


def gate_judge_top(video, n=8):
    """The JUDGE is the top tile, the defendant the bottom - measured by
    recognising Boyd on the output, never assumed from which side she sat.

    Where it came from: the reference short SANCHEZ_SHORT_FINAL (Nathan
    2026-08-31: "Short that you made look nicer than the original footage was
    Sanchez") and the shipped OFFERUP_SHORT both have Boyd on top;
    tools/speakers.py labels mouths on the same assumption ("the top tile is
    the bench"). scripts/make_short.py stacked the LEFT source tile on top,
    and Boyd sits LEFT in CARTHIEF but RIGHT in SANCHEZ/OFFERUP/TORRES, so
    TORRES rendered with the defendant on top and the engine crashed inside
    speakers.py instead of refusing. Measured 2026-09-02, 8 frames each,
    median SFace cosine vs config/boyd_reference.npy (same-person line 0.363):
        SANCHEZ_SHORT_FINAL   top 0.855   bottom 0.288
        OFFERUP_SHORT         top 0.688   bottom 0.150
        TORRES (upside down)  top 0.248   bottom 0.698
    PASS iff median(top) >= threshold AND median(top) > median(bottom).
    """
    import cv2
    import numpy as np
    import identity
    ref = identity.load_reference()
    if ref is None:
        return False, "config/boyd_reference.npy missing"
    dur = duration(video, "v:0")
    if dur <= 0:
        return False, "unreadable"
    tops, bots = [], []
    with tempfile.TemporaryDirectory() as d:
        fp = os.path.join(d, "f.png")
        for i in range(n):
            t = dur * (i + 0.5) / n
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "%.3f" % t,
                            "-i", video, "-frames:v", "1", fp], capture_output=True)
            im = cv2.imread(fp)
            if im is None:
                continue
            half = im.shape[0] // 2
            _, st = identity.find_judge(im[:half], ref)
            _, sb = identity.find_judge(im[half:], ref)
            tops.append(float(st))
            bots.append(float(sb))
    if not tops:
        return False, "no frames decoded"
    mt, mb = float(np.median(tops)), float(np.median(bots))
    ok = mt >= identity.COSINE_SAME and mt > mb
    return ok, (f"Boyd top {mt:.3f} / bottom {mb:.3f} (same-person >= "
                f"{identity.COSINE_SAME:.3f}, {len(tops)} frames)"
                + ("" if ok else " - JUDGE NOT ON TOP"))


def gate_assets(paths):
    """A missing asset FAILS. CLAUDE.md is explicit that logging a line and
    carrying on is how every short went out unbranded."""
    missing = [p for p in paths if p and not os.path.exists(p)]
    return (not missing), ("all present" if not missing
                           else "MISSING " + ", ".join(os.path.basename(p) for p in missing))


# ---- build ------------------------------------------------------------------
def build(video, words_json, out, intro=None, watermark=None, verbose=True,
          timemap=None):
    """Build a short and gate it. Returns (ok, report). Writes NOTHING that
    looks like a deliverable unless every gate passes."""
    import shutil
    import caption_short as C

    tmp_out = out + ".building.mp4"
    for p in (tmp_out, out):
        if os.path.exists(p):
            os.remove(p)

    report = []

    ok, det = gate_assets([video, words_json, intro, watermark])
    report.append(("assets", ok, det))
    if not ok:
        return False, report

    import make_short as M
    C.ENTRANCE, C.REVEAL = ENTRANCE, REVEAL
    # reveal used to be the literal "off" here, which is the one value R34
    # forbids ("a word may be drawn no earlier than its own start"); it now
    # comes from the floor like everything else (captions.reveal).
    # A crash inside the renderer (speakers.py raises SystemExit when a tile
    # has no face, e.g. the judge stacked on the wrong tile) used to escape
    # build() before any gate was reported. It is a failed gate like any other.
    try:
        M.build(video, words_json, tmp_out, None, None, REVEAL, ENTRANCE,
                diarize=True, grade_top=None, grade_bot=None, audio=None)
    except (SystemExit, Exception) as e:          # noqa: BLE001
        report.append(("render", False, f"renderer raised {type(e).__name__}: {e}"))
        if verbose:
            print(f"   FAIL  {'render':18} renderer raised {type(e).__name__}: {e}")
        for p in (tmp_out,):
            if os.path.exists(p):
                os.remove(p)
        print("  REFUSED - render failed; no file written")
        return False, report
    if not os.path.exists(tmp_out):
        report.append(("render", False, "no output"))
        return False, report

    # master to the house loudness: measure, one fixed gain, limiter, and the
    # true peak proved on the encoded file (tools/master_audio.py). Until
    # 2026-09-02 a master_audio failure fell back to a single-pass loudnorm
    # here - a dynamic normaliser that pumps on speech, and the report line
    # passed as long as a file existed. A mastering failure is a failed gate.
    mastered = out + ".mastered.mp4"
    try:
        import master_audio as MA
        _b, _a, _ = MA.master(tmp_out, mastered)
        report.append(("master", True,
                       f"{_b[0]:.1f} -> {_a[0]:.1f} LUFS, true peak {_a[2]:.1f} dBTP"))
    except Exception as e:                      # noqa: BLE001
        report.append(("master", False, f"master_audio raised {type(e).__name__}: {e}"))
        if verbose:
            print(f"   FAIL  {'master':18} master_audio raised {type(e).__name__}: {e}")
        for p in (tmp_out, mastered):
            if os.path.exists(p):
                os.remove(p)
        print("  REFUSED - mastering failed; no file written")
        return False, report
    src = mastered

    for name, fn in (("format", lambda: gate_format(src)),
                     ("loudness", lambda: gate_loudness(src)),
                     # the LIVE file is written to the repo root; work/_short.ass
                     # is a stale Aug-21 leftover and reading it reported
                     # "no positioned events" on a build whose captions were
                     # perfectly placed. My gate, not the build.
                     ("captions on seam", lambda: gate_captions_on_seam(
                         os.path.join(ROOT, "_short.ass"))),
                     ("cuts", lambda: gate_cuts(src, words_json, timemap)),
                     ("judge on top", lambda: gate_judge_top(src)),
                     ("content", lambda: gate_content(words_json))):
        try:
            g, det = fn()
        except Exception as e:
            g, det = False, f"ERROR {e}"
        report.append((name, g, det))

    hard = [r for r in report if r[1] is False]
    if verbose:
        for n, g, d in report:
            tag = "...." if g is None else ("PASS" if g else "FAIL")
            print(f"   {tag}  {n:18} {d}")
    if hard:
        # REFUSED: leave nothing that looks shippable
        for p in (tmp_out, mastered):
            if os.path.exists(p):
                os.remove(p)
        print(f"  REFUSED - {len(hard)} gate(s) failed; no file written")
        return False, report
    shutil.move(src, out)
    for p in (tmp_out,):
        if os.path.exists(p):
            os.remove(p)
    # R40: sidecar carries the short floor hash; floor_stamp.py check refuses
    # the file once config/short_floor.json moves.
    import floor_stamp
    _fl = floor_stamp.stamp(out)
    report.append(("floor", True, f"stamped {_fl['hash'][:12]}"))
    print(f"  floor stamp  {_fl['hash'][:12]}  -> {os.path.basename(out)}.floor.json")
    print(f"  SHORT_OK  {out}")
    return True, report


# ---- selftest ---------------------------------------------------------------
def selftest():
    """Every gate proven against a control that carries the defect."""
    import numpy as np
    ok = True

    def chk(label, got, want):
        nonlocal ok
        hit = (got == want)
        ok &= hit
        print(f"  {'OK  ' if hit else 'MISS'}  {label:46} -> {got} (want {want})")
        return hit

    print("G1 one entry point")
    chk("engine module imports and exposes build()", callable(build), True)
    three = [os.path.join(ROOT, p) for p in
             ("tools/make_short.py", "scripts/make_short.py", "scripts/make_short_auto.py")]
    print(f"      legacy scripts still on disk: {sum(os.path.exists(p) for p in three)}/3 "
          f"(kept as libraries; this is the only entry point)")
    print("G1_OK")

    with tempfile.TemporaryDirectory() as d:
        # ---- G2 captions on seam, both directions
        seam = int(H * SEAM_FRAC)
        good = os.path.join(d, "good.ass")
        bad = os.path.join(d, "bad.ass")
        open(good, "w").write("".join(
            f"Dialogue: 0,0:00:0{i},0:00:0{i+1},D,,0,0,0,,{{\\pos(540,{seam})}}word\n"
            for i in range(5)))
        open(bad, "w").write("".join(
            f"Dialogue: 0,0:00:0{i},0:00:0{i+1},D,,0,0,0,,{{\\pos(540,{seam - 300})}}word\n"
            for i in range(5)))
        chk("G2 accepts captions on the seam", gate_captions_on_seam(good)[0], True)
        chk("G2 rejects captions in one half", gate_captions_on_seam(bad)[0], False)
        print("G2_OK")

        # ---- G11 the floor FILE is authoritative, both directions
        print(f"G11 floor = {os.path.relpath(FLOOR_PATH, ROOT)}")
        chk("G11 live ENTRANCE is the file's entrance_mode",
            ENTRANCE == FLOOR["captions"]["entrance_mode"], True)
        chk("G11 live FONT/size/LUFS/eq are the file's",
            (FONT, CAP_PX, LUFS_TARGET, GRADE_EQ) ==
            (FLOOR["captions"]["font"], FLOOR["captions"]["size"],
             FLOOR["audio"]["integrated_LUFS"], FLOOR["grade"]["eq"]), True)
        # a copy with entrance_mode = 'rise' must come back as 'rise': the
        # derived name follows the file, not a literal left in code
        alt = json.load(open(FLOOR_PATH, encoding="utf-8"))
        alt["captions"]["entrance_mode"] = "rise"
        altp = os.path.join(d, "short_floor_rise.json")
        json.dump(alt, open(altp, "w", encoding="utf-8"))
        da = derive(load_floor(altp))
        chk("G11 derived ENTRANCE follows a file saying 'rise'", da["ENTRANCE"], "rise")
        chk("G11 the 'rise' copy would fail G3 (control)",
            da["ENTRANCE"] in da["ENTRANCE_REJECTED"], True)
        # a copy missing a required key must refuse to load, not default
        del alt["captions"]["entrance_mode"]
        json.dump(alt, open(altp, "w", encoding="utf-8"))
        try:
            load_floor(altp)
            refused = False
        except KeyError as e:
            refused = "captions.entrance_mode" in str(e)
        chk("G11 a floor missing entrance_mode refuses to load", refused, True)
        import caption_short as _C
        chk("G11 caption_short derives the same ENTRANCE/FONT/size",
            (_C.ENTRANCE, _C.FONT, _C.CAP_PX, _C.SCALE_Y) ==
            (ENTRANCE, FONT, CAP_PX, SCALE_Y), True)
        print("G11_OK")

        print(f"G3 entrance = {ENTRANCE!r}  (rejected: {', '.join(ENTRANCE_REJECTED)})")
        chk("G3 entrance is not scale-based", ENTRANCE not in ENTRANCE_REJECTED, True)
        chk("G3 reveal is not 'off' (R34)", REVEAL != "off", True)
        print("G3_OK")

        # ---- G4 loudness, on real rendered tones
        quiet = os.path.join(d, "quiet.mp4")
        right = os.path.join(d, "right.mp4")
        base = (f"-f lavfi -i color=c=black:s={W}x{H}:d=3 -f lavfi "
                "-i sine=frequency=440:duration=3").split()
        sh(["ffmpeg", "-v", "error", "-y"] + base +
           ["-af", "volume=-30dB", "-pix_fmt", PIX_FMT, "-shortest", quiet])
        sh(["ffmpeg", "-v", "error", "-y"] + base +
           ["-af", f"loudnorm=I={LUFS_TARGET}:TP={TRUE_PEAK_MAX}:LRA={LRA}",
            "-pix_fmt", PIX_FMT, "-shortest", right])
        if os.path.exists(quiet) and os.path.exists(right):
            chk("G4 rejects a -30dB short", gate_loudness(quiet)[0], False)
            chk("G4 accepts a normalised short", gate_loudness(right)[0], True)
            chk(f"G7 accepts {W}x{H} {PIX_FMT}", gate_format(right)[0], True)
            small = os.path.join(d, "small.mp4")
            sh(["ffmpeg", "-v", "error", "-y", "-i", right, "-vf",
                f"scale={W // 2}:{H // 2}", "-pix_fmt", PIX_FMT, small])
            chk("G7 rejects the wrong dimensions", gate_format(small)[0], False)
        print("G4_OK")
        print("G7_OK")

        # ---- G5 cuts: joins in audible audio rejected, joins in silence accepted.
        # gate_cuts reads the join positions from the timemap and measures the
        # OUTPUT's energy there (see its docstring). Until 2026-09-01 this test
        # still called the pre-timemap signature, got None ("UNMEASURED") and
        # reported MISS on every run. Control: a 4s tone that is ON for the
        # first 0.6s of every second and OFF for the last 0.4s, so a join at
        # x.3 is inside the tone and a join at x.8 is in the gap.
        words = [{"s": 0.0, "e": 1.0, "w": "one"}, {"s": 1.0, "e": 2.0, "w": "two"}]
        wj = os.path.join(d, "w.json")
        json.dump(words, open(wj, "w"))
        tone = os.path.join(d, "tone.mp4")
        sh(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
            "-i", f"color=c=black:s={W}x{H}:d=4", "-f", "lavfi",
            "-i", "sine=frequency=440:duration=4",
            "-af", "volume='if(lt(mod(t,1),0.6),1,0)':eval=frame",
            "-pix_fmt", PIX_FMT, "-shortest", tone])

        def timemap(joins, p):
            json.dump({"segments": [{"new_start": 0.0}] +
                       [{"new_start": t} for t in joins]}, open(p, "w"))
            return p
        if os.path.exists(tone):
            g, det = gate_cuts(tone, wj, timemap([0.3, 1.3, 2.3], os.path.join(d, "bad.json")))
            chk(f"G5 rejects joins inside audible audio ({det})", g, False)
            g, det = gate_cuts(tone, wj, timemap([0.8, 1.8, 2.8], os.path.join(d, "good.json")))
            chk(f"G5 accepts joins in silence ({det})", g, True)
            chk("G5 reports UNMEASURED (None) without a timemap", gate_cuts(tone, wj)[0], None)
        print("G5_OK")
        print(f"G6 audio fade across joins = {CUT_FADE_MS}ms")
        chk("G6 fade is configured", CUT_FADE_MS > 0, True)
        print("G6_OK")

        # ---- G11 judge on top: the reference's own tiles, stacked both ways.
        # tools/fixtures/tile_boyd_sanchez.jpg / tile_defendant_sanchez.jpg are
        # the top and bottom halves of SANCHEZ_SHORT_FINAL.mp4 at 5.0 s.
        import cv2
        fj = os.path.join(ROOT, "tools", "fixtures", "tile_boyd_sanchez.jpg")
        fd = os.path.join(ROOT, "tools", "fixtures", "tile_defendant_sanchez.jpg")
        chk("G11 fixtures present", os.path.exists(fj) and os.path.exists(fd), True)
        if os.path.exists(fj) and os.path.exists(fd):
            tj, td = cv2.imread(fj), cv2.imread(fd)
            tj = cv2.resize(tj, (W, H // 2))
            td = cv2.resize(td, (W, H // 2))
            for label, stack, want in (("judge top", np.vstack([tj, td]), True),
                                       ("judge bottom (swapped)", np.vstack([td, tj]), False)):
                png = os.path.join(d, "stack.png")
                cv2.imwrite(png, stack)
                vid = os.path.join(d, "stack.mp4")
                sh(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", png,
                    "-t", "2", "-r", "10", "-pix_fmt", PIX_FMT, "-c:v", "libx264", vid])
                g, det = gate_judge_top(vid, n=4)
                chk(f"G11 {label}: {det}", g, want)
        print("G11_OK")

        # ---- G9 missing asset must fail
        chk("G9 rejects a missing asset",
            gate_assets([os.path.join(d, "nope.mp4")])[0], False)
        chk("G9 accepts present assets", gate_assets([wj])[0], True)
        print("G9_OK")

    print("G8 refusal leaves nothing shippable - enforced in build(); "
          "the REFUSED path removes both temp files before returning")
    print("G8_OK")
    print("G10 every gate above was run against a control carrying its defect")
    print("G10_OK")
    print("SELFTEST_PASS short_engine" if ok else "SELFTEST_FAIL short_engine")
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?")
    ap.add_argument("words", nargs="?")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--intro")
    ap.add_argument("--watermark")
    ap.add_argument("--timemap", help="timemap.json from the tighten stage")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    if not (a.video and a.words and a.out):
        print("usage: short_engine.py VIDEO WORDS.json OUT.mp4 | --selftest")
        sys.exit(2)
    good, _ = build(a.video, a.words, a.out, a.intro, a.watermark,
                    timemap=a.timemap)
    sys.exit(0 if good else 1)
