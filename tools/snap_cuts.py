# -*- coding: utf-8 -*-
"""Move every cut off a word and into the gap beside it.

Nathan, 2026-08-31: *"you need to be surgical with the cuts because main thing
high short term retention is literally what makes or breaks the short"*.

Measured on the OFFERUP short: **12 of 19 cuts land inside a word** - mid
syllable on "stolen.", "vehicle", "when". A viewer does not consciously notice a
clipped consonant, they just feel the video is choppy, which is precisely the
complaint that has followed these shorts around.

TIME ORIGINS - the trap here
`timemap.json` counts from `src_start`; the word list counts from the first
word. On OFFERUP those differ by 0.26s. Comparing them unaligned reported 13
bad cuts where the truth is 12. Small, but it is the same class of error as
grading a still against a video: two measurements in different frames of
reference, silently compared. Every function here takes an explicit offset.

WHAT IT DOES NOT DO
It does not decide WHICH moments to keep - that is content selection. It only
moves a boundary that was already chosen off the middle of a word and into the
nearest silence, which is a strictly local, strictly safe correction.
"""
import json
import os
import sys


def gaps(words):
    """Silent intervals between consecutive words, as (start, end)."""
    out = []
    for a, b in zip(words, words[1:]):
        s, e = float(a["e"]), float(b["s"])
        if e > s:
            out.append((s, e))
    return out


def inside_word(t, words, pad=0.03):
    for w in words:
        if float(w["s"]) + pad < t < float(w["e"]) - pad:
            return w
    return None


def snap_one(t, words, gap_list, max_move=0.35):
    """Nearest gap centre to t, if the move is small enough to be safe."""
    if inside_word(t, words) is None:
        return t, 0.0
    best = None
    for s, e in gap_list:
        c = (s + e) / 2.0
        d = abs(c - t)
        if best is None or d < best[0]:
            best = (d, c)
    if best is None or best[0] > max_move:
        return t, None          # None = could not fix within tolerance
    return best[1], best[1] - t


def snap(timemap_path, words_path, out_path=None, verbose=True,
         mid_lo=0.20, mid_hi=0.80, max_move=0.40):
    """Rewrite a timemap so no boundary sits GENUINELY mid-word.

    "Genuinely" matters. A boundary 2% into a word is inside the accuracy of the
    aligner itself, not a defect - flagging those produced a 15/18 figure where
    the honest number is 10/18. Only 20-80% through a word counts.

    `words_path` MUST be aligned in the SAME timebase as the timemap. On this
    project that is the ORIGINAL source (55.5s), not clean.mp4 or tight.mp4 -
    both of those are already post-cut and aligning them measures the output,
    which is how two earlier attempts measured nothing.

    Returns (n_boundaries, n_midword, n_moved, n_unfixable).
    """
    tm = json.load(open(timemap_path))
    words = [w for w in json.load(open(words_path))
             if float(w["e"]) - float(w["s"]) >= 0.03]
    g = gaps(words)

    def mid(t):
        for w in words:
            a, b = float(w["s"]), float(w["e"])
            f = (t - a) / (b - a)
            if mid_lo <= f <= mid_hi:
                return w
        return None

    segs = tm["segments"]
    _refuse_inverted(segs, timemap_path)
    centres = [(a + b) / 2.0 for a, b in g]
    original = [dict(seg) for seg in segs]
    n = midword = moved = unfix = 0
    for i, seg in enumerate(segs):
        for key in ("old_start", "old_end"):
            if key not in seg:
                continue
            n += 1
            t = float(seg[key])
            if mid(t) is None:
                continue
            midword += 1
            # nearest gap CENTRE, but never move so far that the segment
            # inverts or swallows a neighbour
            best = None
            for c in centres:
                d = abs(c - t)
                if d < max_move and (best is None or d < best[0]):
                    best = (d, c)
            if best is None:
                unfix += 1
                continue
            seg[key] = round(best[1], 3)
            moved += 1
    moved, unfix = _repair_collapse(segs, original, centres, max_move,
                                    moved, unfix)
    # rebuild new_start so the output timeline stays contiguous
    t = 0.0
    for seg in segs:
        seg["new_start"] = round(t, 3)
        t += float(seg.get("old_end", 0)) - float(seg.get("old_start", 0))
    if verbose:
        print(f"  snap_cuts: {n} boundaries, {midword} genuinely mid-word -> "
              f"{moved} moved into silence, {unfix} unfixable within {max_move}s")
    if out_path:
        json.dump(tm, open(out_path, "w"), indent=1)
    return n, midword, moved, unfix


def _refuse_inverted(segs, where):
    """An input segment whose end precedes its start is not a cut, it is a
    broken timemap. Snapping it produced a boundary that landed mid-word and
    the old selftest fixture carried exactly that (old_start 1.0, old_end
    0.65) - the test was failing on its own bad input. Refuse, do not repair."""
    for i, seg in enumerate(segs):
        if "old_start" in seg and "old_end" in seg:
            if float(seg["old_end"]) <= float(seg["old_start"]):
                raise ValueError(
                    f"{where}: segment {i} is inverted or empty "
                    f"(old_start={seg['old_start']} old_end={seg['old_end']})")


def _repair_collapse(segs, original, centres, max_move, moved, unfix,
                     min_len=0.0):
    """Two boundaries of one segment can snap to the SAME gap and collapse it.

    The previous repair put old_end at old_start + 0.30s blind, which is a cut
    placed by arithmetic instead of by silence - on the selftest fixture it
    landed inside the word "two". Now: old_end goes to the nearest gap centre
    AFTER old_start, if that is within max_move of where the boundary was
    originally; otherwise the snap of old_end is reverted and it is counted
    unfixable so the report says so instead of the render hiding it."""
    for seg, orig in zip(segs, original):
        if "old_start" not in seg or "old_end" not in seg:
            continue
        a, b = float(seg["old_start"]), float(seg["old_end"])
        if b > a + min_len:
            continue
        t0 = float(orig["old_end"])
        best = None
        for c in centres:
            if c <= a + min_len:
                continue
            d = abs(c - t0)
            if d < max_move and (best is None or d < best[0]):
                best = (d, c)
        if best is None:
            # revert BOTH boundaries to the (valid, non-inverted) input and
            # report them - a cut we could not place is not a cut we invent
            for key in ("old_start", "old_end"):
                if float(seg[key]) != float(orig[key]):
                    moved -= 1
                    unfix += 1
                seg[key] = orig[key]
        else:
            seg["old_end"] = round(best[1], 3)
    return moved, unfix




# ---- energy-based silence, the ground truth --------------------------------
def silences(wav_path, min_len=0.06, frac=0.12):
    """Quiet intervals measured from the WAVEFORM, not from a transcript.

    Whisper's word ends are estimates and they disagree with the audio: snapping
    to its gaps left 16 of 19 boundaries "unfixable" because the gaps it
    reported were not where the silence actually is. Raw energy has no such
    problem, and it corroborated the defect independently - Whisper said 19/38
    boundaries were mid-word, energy said 20/38 landed in audible audio.
    """
    import wave
    import numpy as np
    with wave.open(wav_path) as f:
        a = np.frombuffer(f.readframes(f.getnframes()), np.int16).astype(np.float32)
        sr = f.getframerate()
    hop = int(0.01 * sr)
    n = len(a) // hop
    rms = np.array([np.sqrt((a[i * hop:(i + 1) * hop] ** 2).mean() + 1e-9)
                    for i in range(n)])
    speech = float(np.percentile(rms, 90))
    floor = float(np.percentile(rms, 10))
    thr = floor + (speech - floor) * frac
    quiet = rms < thr
    out, i = [], 0
    while i < n:
        if quiet[i]:
            j = i
            while j < n and quiet[j]:
                j += 1
            if (j - i) * 0.01 >= min_len:
                out.append((i * 0.01, j * 0.01))
            i = j
        else:
            i += 1
    return out, thr


def snap_to_silence(timemap_path, wav_path, out_path=None, max_move=0.60,
                    verbose=True):
    """Move every boundary that lands in audible audio into the nearest silence."""
    import wave
    import numpy as np
    tm = json.load(open(timemap_path))
    sil, thr = silences(wav_path)
    with wave.open(wav_path) as f:
        a = np.frombuffer(f.readframes(f.getnframes()), np.int16).astype(np.float32)
        sr = f.getframerate()
    win = int(0.03 * sr)

    def loud(t):
        i = int(t * sr)
        lo, hi = max(0, i - win), min(len(a), i + win)
        return (np.sqrt((a[lo:hi] ** 2).mean()) if hi > lo else 0.0) > thr

    segs = tm["segments"]
    _refuse_inverted(segs, timemap_path)
    centres = [(s0 + e0) / 2.0 for s0, e0 in sil]
    original = [dict(seg) for seg in segs]
    n = bad = moved = unfix = 0
    for seg in segs:
        for key in ("old_start", "old_end"):
            if key not in seg:
                continue
            n += 1
            t = float(seg[key])
            if not loud(t):
                continue
            bad += 1
            best = None
            for c in centres:
                d = abs(c - t)
                if d <= max_move and (best is None or d < best[0]):
                    best = (d, c)
            if best is None:
                unfix += 1
                continue
            seg[key] = round(best[1], 3)
            moved += 1
    moved, unfix = _repair_collapse(segs, original, centres, max_move,
                                    moved, unfix, min_len=0.15)
    t = 0.0
    for seg in segs:
        seg["new_start"] = round(t, 3)
        t += float(seg.get("old_end", 0)) - float(seg.get("old_start", 0))
    if verbose:
        print(f"  snap_to_silence: {n} boundaries, {bad} in audible audio -> "
              f"{moved} moved, {unfix} unfixable within {max_move}s "
              f"({len(sil)} silences found)")
    if out_path:
        json.dump(tm, open(out_path, "w"), indent=1)
    return n, bad, moved, unfix


def selftest():
    """Known answer, constructed - not read off a real render, so it cannot
    drift out from under the test."""
    import tempfile
    ok = True
    words = [{"s": 0.0, "e": 0.5, "w": "one"},
             {"s": 0.8, "e": 1.3, "w": "two"},
             {"s": 1.9, "e": 2.4, "w": "three"}]
    with tempfile.TemporaryDirectory() as d:
        wp = os.path.join(d, "w.json")
        json.dump(words, open(wp, "w"))
        # 1.0 is mid-"two" (twice: one segment ends there, the next starts);
        # 1.6 is the centre of the two/three gap and is already clean.
        # Until 2026-09-01 this fixture's second segment was INVERTED
        # (old_start 1.0, old_end 0.65) and the test failed on its own input.
        tm = {"src_start": 0.0,
              "segments": [{"old_start": 0.0, "old_end": 1.0},
                           {"old_start": 1.0, "old_end": 1.6},
                           {"old_start": 1.6, "old_end": 2.4}]}
        tp = os.path.join(d, "t.json")
        json.dump(tm, open(tp, "w"))
        op = os.path.join(d, "o.json")
        n, bad, fixed, unf = snap(tp, wp, op, verbose=False)
        got = json.load(open(op))["segments"]
        moved_ok = all(inside_word(float(s[k]), words) is None
                       for s in got for k in ("old_start", "old_end"))
        print(f"  {bad} bad boundaries, {fixed} moved, {unf} unfixable")
        print(f"  after snapping, any cut still inside a word: {not moved_ok}")
        # 2, not 3: old_start 0.0 sits AT a word start, which is a boundary,
        # not mid-word. My first expectation here was simply wrong.
        if bad != 2:
            print(f"  FAIL expected 2 mid-word boundaries, got {bad}"); ok = False
        if fixed != 2 or unf != 0:
            print(f"  FAIL expected 2 moved / 0 unfixable, got {fixed}/{unf}"); ok = False
        if not moved_ok:
            print("  FAIL a cut is still inside a word"); ok = False
        # the two mid-"two" boundaries both belong in the one/two gap centre
        if abs(float(got[0]["old_end"]) - 0.65) > 1e-6 or \
                abs(float(got[1]["old_start"]) - 0.65) > 1e-6:
            print(f"  FAIL mid-word cut not moved to the gap centre: {got}"); ok = False
        # a boundary already in silence must NOT be moved
        if abs(float(got[1]["old_end"]) - 1.6) > 1e-6:
            print("  FAIL moved a boundary that was already clean"); ok = False
        # segments must stay ordered and contiguous in the output timeline
        for s in got:
            if float(s["old_end"]) <= float(s["old_start"]):
                print(f"  FAIL output segment inverted: {s}"); ok = False
        # and a cut with no gap within tolerance must be reported, not faked
        far = {"src_start": 0.0, "segments": [{"old_end": 1.05}]}
        fp = os.path.join(d, "f.json")
        json.dump(far, open(fp, "w"))
        _, b2, f2, u2 = snap(fp, wp, os.path.join(d, "f2.json"), verbose=False)
        print(f"  distant-cut case: bad={b2} fixed={f2} unfixable={u2}")
        if (b2, f2, u2) != (1, 0, 1):
            print("  FAIL distant cut must be reported unfixable"); ok = False
        # CONTROL: an inverted input segment is refused, never repaired
        inv = {"src_start": 0.0,
               "segments": [{"old_start": 1.0, "old_end": 0.65}]}
        ip = os.path.join(d, "i.json")
        json.dump(inv, open(ip, "w"))
        try:
            snap(ip, wp, os.path.join(d, "i2.json"), verbose=False)
            print("  FAIL inverted input segment was accepted"); ok = False
        except ValueError as exc:
            print(f"  inverted-input case: refused ({str(exc)[-52:]})")
        # CONTROL: both ends of a segment snap into the SAME gap (collapse).
        # 1.0 and 1.02 are both mid-"two" and both nearest to 0.65.
        col = {"src_start": 0.0,
               "segments": [{"old_start": 0.0, "old_end": 1.0},
                            {"old_start": 1.0, "old_end": 1.02}]}
        cp = os.path.join(d, "c.json")
        json.dump(col, open(cp, "w"))
        # within the default 0.40s the next gap (1.6) is out of reach: the
        # segment must come back untouched and be REPORTED, not padded by
        # +0.30s into the middle of "two" (0.95) as the old repair did
        _, b3, f3, u3 = snap(cp, wp, os.path.join(d, "c2.json"), verbose=False)
        g3 = json.load(open(os.path.join(d, "c2.json")))["segments"]
        print(f"  collapse case @0.40s: bad={b3} fixed={f3} unfixable={u3} "
              f"seg1={g3[1]['old_start']}..{g3[1]['old_end']}")
        if (float(g3[1]["old_start"]), float(g3[1]["old_end"])) != (1.0, 1.02) \
                or u3 != 2 or f3 != 1:
            print("  FAIL collapse must revert the segment and report it"); ok = False
        # with reach, old_end goes to the next silence AFTER old_start (1.6)
        _, b4, f4, u4 = snap(cp, wp, os.path.join(d, "c3.json"), verbose=False,
                             max_move=0.70)
        g4 = json.load(open(os.path.join(d, "c3.json")))["segments"]
        print(f"  collapse case @0.70s: bad={b4} fixed={f4} unfixable={u4} "
              f"seg1={g4[1]['old_start']}..{g4[1]['old_end']}")
        if (float(g4[1]["old_start"]), float(g4[1]["old_end"])) != (0.65, 1.6) \
                or u4 != 0:
            print("  FAIL collapse must land old_end in the next silence"); ok = False
        if any(inside_word(float(s[k]), words) for s in g4
               for k in ("old_start", "old_end")):
            print("  FAIL collapse repair left a cut inside a word"); ok = False
    print("SELFTEST_PASS snap_cuts" if ok else "SELFTEST_FAIL snap_cuts")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    if len(sys.argv) < 3:
        print("usage: snap_cuts.py timemap.json words.json [out.json] | --selftest")
        sys.exit(2)
    snap(sys.argv[1], sys.argv[2],
         sys.argv[3] if len(sys.argv) > 3 else None)
