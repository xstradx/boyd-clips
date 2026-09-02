# -*- coding: utf-8 -*-
"""Remove dead air from a short, and re-time the word list to match.

A short lives or dies on pace, and a 1.1s hole in a 51s clip is a scroll cue. But
courtroom pauses do carry weight, so this does not close gaps to zero - it trims
anything over THRESH down to KEEP, which reads as a breath rather than a stall.

The important part is that the WORD TIMINGS come back re-mapped. Cutting the video
without re-timing the captions is how captions drift out of sync, and he asked for
the font and sound to align surgically.

    python tools/tighten.py IN.mp4 words.json OUT.mp4 OUT_words.json \
        [--tail S] [--timemap OUT_tm.json] [--src-start SOURCE_S]

--tail    seconds kept after the LAST transcribed word (default 0.32). Whisper
          drops quiet speech - TORRES's "please, your honor, please" at -30..-39
          dB after "orders." was not in the word list, and the default tail cut
          it off. `--tail auto` MEASURES it (measured_tail): the tail runs to
          the last audible sound after the last word, plus the default margin.
          On TORRES that is 1.58 s (last audible 59.54 s, "orders." ends 58.28)
          against the 1.47 that was typed by hand on 2026-09-02. A number a
          human types per short is a step that gets skipped; the chain
          (tools/short_chain.py) always passes auto.
--timemap writes the old->new segment map tools/short_engine.py needs for its
          cut gate (without it the engine reports cut placement UNMEASURED).
          Until 2026-09-02 this map was built by hand in a scratch script every
          time, which is how a step gets skipped.
"""
import sys, json, subprocess, argparse


EDGE = 0.03     # the engine's cut gate listens 30 ms either side of a join


def _edges_in_silence(a_end, b_start, keep, sil):
    """Where to cut the gap between word end `a_end` and word start `b_start`
    so that BOTH sides of the join are quiet.

    Whisper's word ends are estimates; the reverb tail of "do." ran ~0.15 s past
    its transcribed end on TORRES and the symmetric keep/2 cut landed in it -
    the engine's cut gate (energy at the join, +/-30 ms) refused 2 of 3 joins.
    So the edges come from the measured silences (`snap_cuts.silences`): the
    out-point sits >= EDGE inside the first silence that follows the word, the
    in-point >= EDGE before the end of the last silence that precedes the next
    word, and the kept pause is still ~`keep`.  Returns None when no silence
    lies in the gap - then there is nothing quiet to cut on and the gap is left
    alone (the gate on the output is the final word).
    """
    lo, hi = a_end - 0.08, b_start + 0.08
    inside = [(s0, e0) for s0, e0 in sil if e0 > lo and s0 < hi]
    if not inside:
        return None
    s0, e0 = inside[0]
    c0 = max(s0 + EDGE, a_end + keep / 2)
    if c0 > e0 - 0.005:
        c0 = max(s0 + EDGE, e0 - 0.005)
    s1, e1 = inside[-1]
    c1 = min(e1 - EDGE, b_start - keep / 2)
    if c1 < s1 + 0.005:
        c1 = min(e1 - EDGE, s1 + 0.005)
    if c1 - c0 < 0.05:
        return None
    return c0, c1


TAIL_DEFAULT = 0.32     # seconds kept after the last audible sound / last word


def measured_tail(sil, last_word_end, dur, base=TAIL_DEFAULT):
    """Seconds to keep after the last transcribed word so that nothing AUDIBLE
    is cut off. Whisper drops quiet speech (TORRES: -30..-39 dB pleading after
    the last transcribed word), so the tail is measured from the waveform: the
    end of the last non-silent run after the word, plus `base`. Falls back to
    `base` when the clip is silent after the word, and never exceeds the clip.
    """
    end = last_word_end
    # walk the silences: audible runs are the gaps between them
    prev_end = last_word_end
    for s0, e0 in sorted(sil):
        if e0 <= last_word_end:
            continue
        if s0 > prev_end + 0.005:           # audible run (prev_end, s0)
            end = max(end, s0)
        prev_end = max(prev_end, e0)
    # silences are measured on 10 ms hops and the wav can be a few ms shorter
    # than ffprobe's duration, so "ends in silence" gets a 50 ms allowance
    if prev_end < dur - 0.05:               # clip ends on audible audio
        end = dur
    return round(min(dur - last_word_end, (end - last_word_end) + base), 3)


def plan(words, dur, thresh=0.45, keep=0.20, tail=0.32, sil=None):
    """Return (keep_segments, remapped_words, removed). Segments are [start, end)
    in the SOURCE timeline; remapped words carry OUTPUT timestamps. `sil` is an
    optional list of measured silent intervals (see _edges_in_silence); without
    it the edges are keep/2 either side of the transcribed gap."""
    cuts = []                       # (gap_start, gap_end) to shorten
    for a, b in zip(words, words[1:]):
        g = b["s"] - a["e"]
        if g > thresh:
            c = _edges_in_silence(a["e"], b["s"], keep, sil) if sil else None
            if c is None and sil:
                continue            # nothing quiet to cut on: leave the pause
            cuts.append(c or (a["e"] + keep / 2, b["s"] - keep / 2))
    lead = words[0]["s"]
    if lead > thresh:
        cuts.insert(0, (keep / 2, lead - keep / 2))

    segs, prev = [], 0.0
    for c0, c1 in cuts:
        segs.append((prev, c0))
        prev = c1
    segs.append((prev, min(dur, words[-1]["e"] + tail)))
    segs = [(a, b) for a, b in segs if b - a > 0.01]

    # map a source time to output time
    def remap(t):
        out = 0.0
        for a, b in segs:
            if t < a:
                return out
            if t <= b:
                return out + (t - a)
            out += b - a
        return out

    rw = []
    for w in words:
        s, e = remap(w["s"]), remap(w["e"])
        if e > s:
            rw.append(dict(w=w["w"], s=round(s, 3), e=round(e, 3), p=w.get("p", 1.0)))
    removed = (segs[-1][1] - segs[0][0]) - sum(b - a for a, b in segs)
    return segs, rw, sum(c1 - c0 for c0, c1 in cuts)


def render(src, segs, out, audio=None, extra_vf=""):
    v = "".join(f"[0:v]trim={a}:{b},setpts=PTS-STARTPTS[v{i}];" for i, (a, b) in enumerate(segs))
    ai = 1 if audio else 0
    a = "".join(f"[{ai}:a]atrim={s}:{e},asetpts=PTS-STARTPTS[a{i}];" for i, (s, e) in enumerate(segs))
    cat = "".join(f"[v{i}][a{i}]" for i in range(len(segs)))
    fc = v + a + cat + f"concat=n={len(segs)}:v=1:a=1[vc][ac]"
    if extra_vf:
        fc += f";[vc]{extra_vf}[vo]"
    vmap = "[vo]" if extra_vf else "[vc]"
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", src]
    if audio:
        cmd += ["-i", audio]
    cmd += ["-filter_complex", fc, "-map", vmap, "-map", "[ac]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", out]
    subprocess.run(cmd, check=True)


def selftest():
    """Known answer, constructed. The engine gate listens +/-EDGE around each
    join, so every cut edge must sit >= EDGE inside a silence."""
    ok = True

    def chk(label, got, want):
        nonlocal ok
        hit = got == want
        ok &= hit
        print(f"  {'OK  ' if hit else 'MISS'}  {label:52} -> {got} (want {want})")

    words = [dict(w="a", s=0.10, e=0.50), dict(w="b", s=1.50, e=1.90),
             dict(w="c", s=2.00, e=2.40), dict(w="d", s=4.00, e=4.40)]
    # silence 1 starts 0.15 s AFTER "a" ends (reverb tail); silence 2 is clean
    sil = [(0.65, 1.45), (2.45, 3.95)]
    segs, rw, removed = plan(words, 5.0, sil=sil)
    chk("two gaps cut", len(segs), 3)
    (s0, e0), (s1, e1), (s2, e2) = segs
    chk("out-point >= EDGE inside silence 1 (not in the tail)", e0 >= 0.65 + EDGE, True)
    chk("in-point >= EDGE before silence 1 ends", s1 <= 1.45 - EDGE, True)
    chk("out-point >= EDGE inside silence 2", e1 >= 2.45 + EDGE, True)
    chk("in-point >= EDGE before silence 2 ends", s2 <= 3.95 - EDGE, True)
    chk("kept pause about `keep` (gap 2)", abs((s2 - e1) - ((3.95 - 2.45) - 0.20)) < 0.2, True)
    chk("words re-timed monotonic", all(x["s"] < y["s"] for x, y in zip(rw, rw[1:])), True)
    # control: the old word-based edges land in the reverb tail
    segs0, _, _ = plan(words, 5.0)
    chk("CONTROL word-based out-point lands in the tail (< silence start)",
        segs0[0][1] < 0.65, True)
    # no silence in the gap -> the gap is left alone
    segs1, _, _ = plan(words, 5.0, sil=[(2.45, 3.95)])
    chk("gap with no measured silence is left uncut", len(segs1), 2)
    # --tail auto: quiet speech AFTER the last transcribed word (Whisper dropped
    # it) must be kept. Shape is TORRES's: "d" ends 4.40; audible 4.60-5.30
    # between two silences; the clip ends in silence at 6.0.
    sil_t = [(4.45, 4.60), (5.30, 6.00)]
    t_auto = measured_tail(sil_t, 4.40, 6.0)
    chk("auto tail reaches past the last audible sound", t_auto >= (5.30 - 4.40), True)
    chk("auto tail stays inside the clip", 4.40 + t_auto <= 6.0, True)
    segs_a, _, _ = plan(words, 6.0, tail=t_auto, sil=sil_t)
    chk("auto out-point >= EDGE inside the final silence", segs_a[-1][1] >= 5.30 + EDGE, True)
    # control: the fixed default tail cuts INSIDE the audible run
    segs_f, _, _ = plan(words, 6.0, sil=sil_t)
    chk("CONTROL fixed tail cuts inside audible audio", 4.60 < segs_f[-1][1] < 5.30, True)
    chk("silent clip after the last word -> the default tail",
        measured_tail([(4.40, 6.0)], 4.40, 6.0), TAIL_DEFAULT)
    chk("the word's own reverb (silence starts 50 ms late) is kept",
        measured_tail([(4.45, 6.0)], 4.40, 6.0), round(0.05 + TAIL_DEFAULT, 3))
    chk("clip ending on audible audio keeps it all",
        measured_tail([(4.45, 4.60)], 4.40, 6.0), round(6.0 - 4.40, 3))
    print("SELFTEST_PASS tighten" if ok else "SELFTEST_FAIL tighten")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    ap = argparse.ArgumentParser()
    ap.add_argument("video"); ap.add_argument("words")
    ap.add_argument("out"); ap.add_argument("out_words")
    ap.add_argument("--audio", default=None)
    ap.add_argument("--thresh", type=float, default=0.45)
    ap.add_argument("--keep", type=float, default=0.20)
    ap.add_argument("--tail", default="auto",
                    help="seconds kept after the last transcribed word, or "
                         "'auto' (default) = measured to the last audible sound")
    ap.add_argument("--timemap", default=None,
                    help="write the old->new segment map for short_engine --timemap")
    ap.add_argument("--src-start", type=float, default=None,
                    help="source-stream second the raw short starts at (recorded in the timemap)")
    a = ap.parse_args()
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                "format=duration", "-of", "default=nw=1:nk=1", a.video],
                               capture_output=True, text=True).stdout.strip())
    words = json.load(open(a.words))
    # measured silences from the waveform (snap_cuts.silences), so the cut
    # edges land where the audio is quiet, not where Whisper guessed a word ended
    import os, tempfile
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import snap_cuts
    with tempfile.TemporaryDirectory() as d:
        wav = os.path.join(d, "a.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a.video, "-ac", "1",
                        "-ar", "16000", wav], check=True)
        sil, _thr = snap_cuts.silences(wav)
    print(f"  {len(sil)} silences measured in the audio")
    if str(a.tail).lower() == "auto":
        a.tail = measured_tail(sil, words[-1]["e"], dur)
        print(f"  tail measured: {a.tail:.2f}s after the last word "
              f"(last word ends {words[-1]['e']:.2f}s, clip {dur:.2f}s)")
    else:
        a.tail = float(a.tail)
    segs, rw, removed = plan(words, dur, a.thresh, a.keep, a.tail, sil=sil)
    new_dur = sum(b - s0 for s0, b in segs)
    print(f"  {len(segs)} keep-segments, {removed:.2f}s of dead air removed, "
          f"tail {a.tail:.2f}s after the last word ({dur:.2f}s -> {new_dur:.2f}s)")
    render(a.video, segs, a.out, a.audio)
    json.dump(rw, open(a.out_words, "w"), indent=0)
    print(f"  wrote {a.out} and re-timed {len(rw)} words")
    if a.timemap:
        acc, remap = 0.0, []
        for s0, b in segs:
            remap.append({"old_start": round(s0, 3), "old_end": round(b, 3),
                          "new_start": round(acc, 3)})
            acc += b - s0
        tm = {"src_start": a.src_start, "segments": remap,
              "new_duration": round(acc, 3),
              "source": f"tighten.plan thresh={a.thresh} keep={a.keep} tail={a.tail} on {a.words}"}
        json.dump(tm, open(a.timemap, "w"), indent=1)
        print(f"  wrote timemap {a.timemap} ({len(remap)} segments, {acc:.2f}s)")
