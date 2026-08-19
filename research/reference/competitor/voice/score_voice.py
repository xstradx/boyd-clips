#!/usr/bin/env python
"""score_voice.py - score a narrator candidate against the Audit the Court target.

RUN WITH THE ABSOLUTE INTERPRETER PATH. `python` and `pip` on this box point at
two OTHER interpreters that lack these packages:
  C:\\Users\\natha\\AppData\\Local\\Programs\\Python\\Python312\\python.exe score_voice.py cand.wav

Deps, all already installed in Python312: faster-whisper 1.2.1, praat-parselmouth
0.4.7, numpy 1.26.4. ffmpeg 8.0.1 at C:\\ffmpeg\\ffmpeg.exe. No GPU, no network
after the model cache is warm.
"""
import json, subprocess, sys, re, os
import numpy as np
import parselmouth
from faster_whisper import WhisperModel

FFMPEG = r"C:\ffmpeg\ffmpeg.exe"
FFPROBE = r"C:\ffmpeg\ffprobe.exe"
PITCH_CEILING = 170          # MANDATORY - see note at bottom
GAP_CUT_S = 3.0
PAUSE_FLOOR_S = 0.120

# !!! CONTAMINATED REFERENCE - READ BEFORE TRUSTING ANY ek3 NUMBER BELOW !!!
# Found 2026-08-13. cut_at_gap(gap=3.0) does NOT cut ek3_open.wav at its speaker
# change. The narrator stops at 62.92 s; Judge Boyd starts at 63.50 s - a 0.58 s
# gap. So 14.58 s of a SECOND, FEMALE speaker is inside every ek3 reference
# value here. Praat at ceiling 170 halves her cleanly (she reads 103.9 Hz at
# ceiling 170 and 192.8 Hz under torchcrepe 0.0.24 'full' with no ceiling), so
# the contamination left no trace in F0.
#   metric        as shipped   narration-only (--span 5.5,62.95)
#   wpm             176.3         184.2      <-- OUTSIDE the 172-182 band below
#   f0_med_hz        97.8          96.8
#   f0_sd_st          3.16          3.02
# The WPM band is therefore anchored on a rate the narrator does not speak at.
# Bands left UNCHANGED here on purpose - other work in flight is calibrated
# against them and silently moving a gate mid-flight is worse than a documented
# wrong one. Fix deliberately, not as a side effect.
# yzv_open.wav is NOT affected: its handoff is across a 25.4 s gap.
# Verification:  contour_shape.py speaker_guard() flags words 177-212 of
# ek3_words.json at 189.6 / 196.5 Hz against a passage median of 99.7 Hz.
#
# Pass bands. Reference values re-measured 2026-08-12 with Praat AC, ceiling 170,
# word-masked, on ek3_open.wav / yzv_open.wav.
BANDS = {
    "wpm":          (172.0, 182.0),    # ref 176.3 / 177.5 - SEE WARNING ABOVE
    "f0_med_hz":    (96.0, 110.0),     # ref 97.8 / 104.1
    "f0_sd_st":     (2.6, 3.4),        # ref 3.16 / 2.81
    "voiced_frac":  (0.58, 0.68),      # ref 0.645 / 0.608
    "pause_med_ms": (240.0, 360.0),    # ref 270 / 340
    "pause_p90_ms": (0.0, 560.0),      # ref 500 / 500
    # ref 1360 when small.en re-transcribes ek3_open; the shipped ek3_words.json
    # says 1160. Pause extremes are ASR-boundary dependent by ~15%; WPM is not
    # (176.2 re-transcribed vs 176.3 shipped). Ceiling set above the looser run.
    "pause_max_ms": (0.0, 1450.0),
    "lra_lu":       (0.0, 3.0),        # ref 2.4 mono / 2.3 stereo
    "true_peak_db": (-99.0, -1.0),     # ref -1.0
}
# Loudness target depends on the DELIVERABLE channel count. BS.1770 sums
# per-channel weighted power, so dual-mono stereo reads 10*log10(2) = 3.01 LU
# hotter than the identical audio as one channel. Measured on the same 80 s of
# Ek3Ah3NZYVo: stereo 48k = -16.0 LUFS, mono 16k = -19.1 LUFS.
LUFS_TARGET = {1: -19.1, 2: -16.0}
LUFS_TOL = 0.5

# Pronunciation gate. VOICE_TARGET.md names these classes as what exposes
# synthetic speech in this script. ASR mishearing is a cheap objective proxy.
GATE_PATTERNS = [
    ("date",        r"january\s+(18|eighteen)"),
    ("county",      r"bexar"),
    ("latin",       r"nolo\s+contendere"),
    ("case_number", r"d\.?\s?c\.?\s?2023\s?c\.?\s?r\.?\s?8866|dc2023cr8866"),
    ("count",       r"seven\s+counts"),
    ("money",       r"47[,\s]?200|forty[- ]seven\s+thousand"),
]

_model = None
def model():
    global _model
    if _model is None:
        _model = WhisperModel("small.en", device="cpu", compute_type="int8")
    return _model


def probe(path):
    # ffprobe emits stream fields in ITS OWN order, not the order you ask for -
    # `stream=channels,sample_rate` comes back sample_rate-first. Query each
    # field separately so the mapping cannot silently transpose.
    def one(entry, stream=True):
        args = [FFPROBE, "-v", "error"]
        if stream:
            args += ["-select_streams", "a:0", "-show_entries", "stream=" + entry]
        else:
            args += ["-show_entries", "format=" + entry]
        args += ["-of", "default=nw=1:nk=1", path]
        return subprocess.run(args, capture_output=True, text=True, check=True).stdout.strip()
    return int(one("channels")), int(one("sample_rate")), float(one("duration", False))


def ebur128(path, t0=None, t1=None):
    # Loudness MUST be measured over the same narration span used for prosody.
    # yzv_open.wav is an 80 s clip whose narration ends at 33.3 s and then hands
    # off to courtroom audio: measured whole it reads -20.5 LUFS / LRA 4.3 LU,
    # measured over the narration span it reads -19.4 / 2.6. Same file.
    pre = []
    if t0 is not None:
        pre = ["-ss", f"{max(t0 - 0.10, 0):.3f}", "-t", f"{(t1 - t0) + 0.20:.3f}"]
    r = subprocess.run([FFMPEG, "-hide_banner", "-nostats"] + pre + ["-i", path,
                        "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True)
    t = r.stderr
    def grab(pat):
        m = re.findall(pat, t)
        return float(m[-1]) if m else float("nan")
    return dict(lufs=grab(r"I:\s+(-?\d+\.\d+) LUFS"),
                lra=grab(r"LRA:\s+(-?\d+\.\d+) LU"),
                tp=grab(r"Peak:\s+(-?\d+\.\d+) dBFS"))


def transcribe(path):
    segs, _ = model().transcribe(path, word_timestamps=True, language="en")
    words, text = [], []
    for s in segs:
        for w in (s.words or []):
            words.append((w.start, w.end, w.word))
            text.append(w.word)
    return words, "".join(text)


def cut_at_gap(words, gap=GAP_CUT_S):
    out = [words[0]]
    for a, b in zip(words, words[1:]):
        if b[0] - a[1] > gap:
            break
        out.append(b)
    return out


def measure(path, cut=True):
    ch, sr, dur = probe(path)
    words, text = transcribe(path)
    if not words:
        raise SystemExit("no speech detected in " + path)
    span_words = cut_at_gap(words) if cut else words
    span = span_words[-1][1] - span_words[0][0]
    wpm = len(span_words) / span * 60.0

    snd = parselmouth.Sound(path)
    if ch > 1:
        snd = snd.convert_to_mono()
    p = snd.to_pitch_ac(time_step=0.01, pitch_floor=60, pitch_ceiling=PITCH_CEILING)
    t, f = p.xs(), p.selected_array["frequency"]
    mask = np.zeros(len(t), bool)
    for s, e, _ in span_words:
        mask |= (t >= s) & (t <= e)
    inw = f[mask]
    voiced = inw[inw > 0]
    med = float(np.median(voiced))
    sd_st = float(np.std(12 * np.log2(voiced / med)))

    gaps = [(b[0] - a[1]) * 1000 for a, b in zip(span_words, span_words[1:])]
    pz = [g for g in gaps if g > PAUSE_FLOOR_S * 1000]

    lo = ebur128(path, span_words[0][0], span_words[-1][1])
    m = dict(
        file=os.path.basename(path), channels=ch, sample_rate=sr, duration_s=round(dur, 2),
        words=len(span_words), span_s=round(span, 2), wpm=round(wpm, 1),
        f0_med_hz=round(med, 1),
        f0_p10_hz=round(float(np.percentile(voiced, 10)), 1),
        f0_p90_hz=round(float(np.percentile(voiced, 90)), 1),
        f0_sd_st=round(sd_st, 2),
        octave_doubling_frac=round(float((voiced > 1.7 * med).mean()), 3),
        voiced_frac=round(len(voiced) / max(len(inw), 1), 3),
        n_pause=len(pz),
        pause_med_ms=round(float(np.median(pz))) if pz else None,
        pause_p90_ms=round(float(np.percentile(pz, 90))) if pz else None,
        pause_max_ms=round(max(pz)) if pz else None,
        lufs=lo["lufs"], lra_lu=lo["lra"], true_peak_db=lo["tp"],
        text=text.strip(),
    )
    return m


def grade(m):
    res, fails = {}, []
    for k, (lo, hi) in BANDS.items():
        v = m.get(k)
        if v is None or (isinstance(v, float) and np.isnan(v)):
            res[k] = "n/a"; continue
        ok = lo <= v <= hi
        res[k] = f"{'PASS' if ok else 'FAIL'} {v} in [{lo},{hi}]"
        if not ok:
            fails.append(k)
    tgt = LUFS_TARGET.get(m["channels"])
    if tgt is not None and not np.isnan(m["lufs"]):
        ok = abs(m["lufs"] - tgt) <= LUFS_TOL
        res["lufs"] = f"{'PASS' if ok else 'FAIL'} {m['lufs']} vs {tgt} +/-{LUFS_TOL} ({m['channels']}ch)"
        if not ok:
            fails.append("lufs")
    if m["octave_doubling_frac"] > 0.05:
        res["tracker_warn"] = f"{m['octave_doubling_frac']} of voiced frames >1.7x median - F0 sd suspect"
    low = m["text"].lower()
    gate = {n: bool(re.search(p, low)) for n, p in GATE_PATTERNS}
    hit = {n: v for n, v in gate.items() if v or True}
    res["pronunciation_gate"] = hit
    for n, v in gate.items():
        if not v:
            fails.append("gate:" + n)
    res["VERDICT"] = "PASS" if not fails else "FAIL: " + ", ".join(fails)
    return res


if __name__ == "__main__":
    for path in sys.argv[1:]:
        m = measure(path)
        print(json.dumps({"measured": m, "graded": grade(m)}, indent=2))

# WHY pitch_ceiling=170 IS NOT OPTIONAL:
# At the ceiling of 350 Hz that VOICE_TARGET.md's librosa pyin run used, 14.8% of
# Ek3's word-masked voiced frames land above 1.7x the median and F0 sd reads
# 5.53 st. Drop the ceiling to 170 and that collapses to 0.9% and 3.16 st while
# voiced fraction barely moves (0.654 -> 0.645) - proof those frames were the
# same frames re-estimated an octave up, not extra voicing. The published
# "~3.5 st" target is an artefact-inflated number; the corrected band is 2.6-3.4.
