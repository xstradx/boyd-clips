#!/usr/bin/env python
"""contour_shape.py - measure the SHAPE of the F0 contour.

SUPERSEDES contour_metrics.py. See DEFECTS-FOUND at the bottom for the four
concrete bugs in that file (and the one in score_voice.py) that this replaces,
each with the command that demonstrates it.

WHY THIS EXISTS
  score_voice.py grades GLOBAL statistics: WPM, F0 median, F0 sd, voiced
  fraction, pause stats, LRA, LUFS, true peak. A render can pass all eight and
  still be identified as synthetic inside two sentences, because the tell is
  SHAPE, not average:
    * every sentence ends on the same stereotyped curve, and
    * the pitch accent lands on the wrong syllable of names and numbers.
  Both are invisible to every band in score_voice.py. This module measures them.

RUN (absolute interpreter path - `python` on this box is a different install):
  C:\\Users\\natha\\AppData\\Local\\Programs\\Python\\Python312\\python.exe contour_shape.py cand.wav
  ... --span 5.5,62.95      restrict to a narration span (see SPEAKER GUARD)
  ... --ref                 print the reference-derived bands alongside

METHOD / PROVENANCE (every constant below is sourced, not chosen)
  * Pitch: Praat autocorrelation via parselmouth, pitch_ceiling=170 for this
    narrator (score_voice.py bottom note). Cross-validated against torchcrepe
    0.0.24 'full' on GPU - see SPEAKER GUARD.
  * Nucleus: Mertens, "The Prosogram: Semi-Automatic Transcription of Prosody
    Based on a Tonal Perception Model", Speech Prosody 2004, sprosig.org/sp2004
    /PDF/Mertens.pdf (fetched 2026-08-13), section 3, verbatim: "For each vowel
    the vocalic nucleus is determined. It is defined as the voiced part around
    the local intensity peak, and delimited by the points located at -3 dB
    (left) and -9 dB (right) from the peak." The asymmetry is deliberate: -3 dB
    on the left "eliminates most microprosody perturbations at syllable onset".
    contour_metrics.py used "contiguous voiced frames", which is not this and
    is why its nuclei degenerate - see DEFECTS-FOUND #2.
  * Glissando: same paper. G = 0.16/T^2 ST/s is the "standard" psychoacoustic
    threshold for ISOLATED VOWELS; the paper states that in running speech it
    "overestimates the capabilities of the average listener", and that
    G = 0.32/T^2 - twice the standard - is the value whose stylization matched
    two trained transcribers' manual notation. So 0.32 is the running-speech
    default here. House (cited as [7] in that paper) shows a following pause
    LOWERS the threshold, so pre-pausal boundaries use 0.16.
  * Nucleus peak-picking dip rule: de Jong & Wempe (2009), Behavior Research
    Methods 41(2):385-390 - >= 2 dB dip between adjacent intensity peaks.
  * Declination slope: Theil-Sen (median of pairwise slopes), not least
    squares. Least squares over raw F0 frames is dominated by voiced-segment
    density and by single octave-error frames; the reference passage has both.
  * Stress: CMUdict via nltk + a local override table for the proper nouns and
    ordinals in this script that CMUdict does not carry.
"""
import json, os, re, sys, itertools
import numpy as np
import parselmouth

PITCH_FLOOR   = 60
PITCH_CEILING = 170
WIDE_CEILING  = 500          # speaker-guard pass only
TIME_STEP     = 0.01
SIL_DB_REL    = 25.0         # de Jong & Wempe silence floor, dB below the p99
MIN_DIP_DB    = 2.0
NUC_LEFT_DB   = 3.0          # Mertens 2004 s.3
NUC_RIGHT_DB  = 9.0          # Mertens 2004 s.3
MIN_NUC_MS    = 50.0         # 5 frames at 10 ms - below this a slope is noise
FALLBACK_S    = 0.60         # how far back to look for a scoreable nucleus
PREPAUSAL_S   = 0.25
TERMINAL_WIN  = 0.40
SHAPE_POINTS  = 12
ACCENT_MIN_ST = 1.5          # excursion needed before a word counts as accented

ABBREV = {"mr.", "mrs.", "ms.", "dr.", "jr.", "sr.", "st.", "vs.", "no.", "inc."}
FUNCTION_WORDS = set("""a an the and or but nor for so yet of in on at to from by with
without into onto upon over under about after before during against between among
is are was were be been being am do does did done have has had having will would
shall should can could may might must not no nor as if then than that this these
those there here it its it's he she they them his her their our your my me we us
you i who whom whose which what when where why how all any some each every both
either neither one two too very just also only more most other another such own
same s t re ve ll d m""".split())

STRESS_OVERRIDE = {
    "bexar": [1, 0], "castillo": [0, 1, 0], "moody": [1, 0], "erik": [1, 0],
    "nolo": [1, 0], "contendere": [0, 1, 0, 0], "contenderae": [0, 1, 0, 0],
    "fleischer": [1, 0], "fleischer's": [1, 0], "boyd": [1],
    "garcia": [0, 1, 0], "martinez": [0, 1, 0], "187th": [0, 0, 1, 0],
    "bexar's": [1, 0], "cadet": [0, 1], "cadets": [0, 1], "taser": [1, 0],
}

# Tokens whose mis-accentuation is the reported failure. Reported INDIVIDUALLY,
# never folded into a rate - a 0.82 hit rate tells you nothing about whether
# "Bexar" was wrong, and "Bexar" is the word that gets noticed.
WATCHLIST = ["bexar", "castillo", "moody", "erik", "michael", "garcia", "martinez",
             "contendere", "contenderae", "nolo", "187th", "taser", "cadet",
             "indicted", "surety", "misdemeanor", "felony", "duress", "necessity"]


# ------------------------------------------------------------------ words/spans

def words_sidecar(wav):
    """<stem>_words.json, else <stem-minus-_suffix>_words.json.

    The reference sidecars are named ek3_words.json / yzv_words.json but the
    audio is ek3_open.wav / yzv_open.wav. contour_metrics.py looked only for the
    exact stem, found nothing, and silently re-ran faster-whisper small.en on
    every invocation - 36 s per file, and a DIFFERENT word segmentation from the
    shipped one, so its numbers were not reproducible against the sidecars."""
    stem = os.path.splitext(wav)[0]
    for cand in (stem + "_words.json", stem.rsplit("_", 1)[0] + "_words.json"):
        if os.path.exists(cand):
            return cand
    return None


def load_words(wav):
    side = words_sidecar(wav)
    if side:
        return [(float(x["s"]), float(x["e"]), x["w"]) for x in json.load(open(side))]
    from faster_whisper import WhisperModel
    m = WhisperModel("small.en", device="cpu", compute_type="int8")
    segs, _ = m.transcribe(wav, word_timestamps=True, language="en")
    return [(w.start, w.end, w.word) for s in segs for w in (s.words or [])]


def speaker_guard(wav, words, t0, t1):
    """Refuse to score across a speaker change.

    THIS IS NOT OPTIONAL. score_voice.py and contour_metrics.py both cut a span
    at the first gap > 3.0 s. On ek3_open.wav the narrator hands off to Judge
    Boyd across a 0.58 s gap, so neither cuts, and 14.58 s of a ~193 Hz female
    voice is folded into the narrator's statistics while a 170 Hz ceiling halves
    her to ~104 Hz so nothing looks wrong. See DEFECTS-FOUND #1.

    Detection is ceiling-free on purpose: a WIDE_CEILING pass, per-word median
    F0, then a scan for a run of >= 5 words whose median sits > 4 semitones off
    the passage median. 4 st is a wide margin - a single speaker's word medians
    stay well inside it - so this flags speakers, not emphasis.
    """
    snd = parselmouth.Sound(wav)
    if snd.n_channels > 1:
        snd = snd.convert_to_mono()
    part = snd.extract_part(from_time=max(t0 - 0.3, snd.xmin),
                            to_time=min(t1 + 0.3, snd.xmax), preserve_times=True)
    p = part.to_pitch_ac(time_step=TIME_STEP, pitch_floor=PITCH_FLOOR,
                         pitch_ceiling=WIDE_CEILING)
    t, f = np.asarray(p.xs()), np.asarray(p.selected_array["frequency"])
    wm = []
    for s, e, w in words:
        m = (t >= s) & (t <= e) & (f > 0)
        wm.append((s, e, w, float(np.median(f[m])) if m.sum() >= 4 else np.nan))
    vals = np.array([x[3] for x in wm], float)
    good = vals[np.isfinite(vals)]
    if len(good) < 10:
        return dict(ok=True, note="too few voiced words to guard"), wm
    passage = float(np.median(good))
    dev = 12 * np.log2(np.where(np.isfinite(vals), vals, passage) / passage)
    off = np.abs(dev) > 4.0
    runs, i = [], 0
    while i < len(off):
        if off[i]:
            j = i
            while j + 1 < len(off) and off[j + 1]:
                j += 1
            if j - i + 1 >= 5:
                runs.append(dict(w0=i, w1=j, t0=round(wm[i][0], 2), t1=round(wm[j][1], 2),
                                 n_words=j - i + 1,
                                 median_hz=round(float(np.nanmedian(vals[i:j + 1])), 1),
                                 passage_hz=round(passage, 1),
                                 text=" ".join(x[2].strip() for x in wm[i:j + 1])[:90]))
            i = j + 1
        else:
            i += 1
    return dict(ok=not runs, passage_med_hz_wide=round(passage, 1),
                suspect_runs=runs), wm


# ------------------------------------------------------------------ pitch track

class Track:
    def __init__(self, wav, t0, t1, margin=0.30):
        snd = parselmouth.Sound(wav)
        if snd.n_channels > 1:
            snd = snd.convert_to_mono()
        part = snd.extract_part(from_time=max(t0 - margin, snd.xmin),
                                to_time=min(t1 + margin, snd.xmax), preserve_times=True)
        self.snd = part
        p = part.to_pitch_ac(time_step=TIME_STEP, pitch_floor=PITCH_FLOOR,
                             pitch_ceiling=PITCH_CEILING)
        self.pt = np.asarray(p.xs())
        self.pf = np.asarray(p.selected_array["frequency"]).copy()
        self.pf[(self.pt < t0) | (self.pt > t1)] = 0.0
        v = self.pf[self.pf > 0]
        if len(v) < 50:
            raise SystemExit("too little voiced speech in span")
        self.med = float(np.median(v))
        self.st = np.where(self.pf > 0, 12 * np.log2(np.maximum(self.pf, 1e-9) / self.med), np.nan)
        inten = part.to_intensity(minimum_pitch=PITCH_FLOOR, time_step=TIME_STEP)
        self.it = np.asarray(inten.xs())
        self.iv = np.asarray(inten.values[0])
        fin = np.isfinite(self.iv)
        self.sil_db = float(np.percentile(self.iv[fin], 99)) - SIL_DB_REL
        self.t0, self.t1 = t0, t1
        self._nuc_cache = {}

    def seg(self, a, b):
        m = (self.pt >= a) & (self.pt <= b) & np.isfinite(self.st)
        return self.pt[m], self.st[m]

    def nuclei(self, a, b):
        """Prosogram nuclei: voiced part around each intensity peak, cut at
        -3 dB left / -9 dB right of that peak, peaks separated by a >=2 dB dip."""
        key = (round(a, 3), round(b, 3))
        if key in self._nuc_cache:
            return self._nuc_cache[key]
        m = (self.it >= a) & (self.it <= b)
        t, v = self.it[m], self.iv[m]
        out = []
        if len(t) >= 3:
            peaks = [i for i in range(1, len(v) - 1)
                     if v[i] >= v[i - 1] and v[i] > v[i + 1] and v[i] > self.sil_db]
            kept = []
            for i in peaks:
                if not kept:
                    kept.append(i); continue
                j = kept[-1]
                if min(v[j], v[i]) - v[j:i + 1].min() >= MIN_DIP_DB:
                    kept.append(i)
                elif v[i] > v[j]:
                    kept[-1] = i
            for i in kept:
                lo = i
                while lo > 0 and v[lo - 1] >= v[i] - NUC_LEFT_DB:
                    lo -= 1
                hi = i
                while hi < len(v) - 1 and v[hi + 1] >= v[i] - NUC_RIGHT_DB:
                    hi += 1
                ns, ne = float(t[lo]), float(t[hi])
                # intersect with the voiced part, as Mertens specifies
                tt, ss = self.seg(ns, ne)
                if len(tt) < 2:
                    continue
                out.append(dict(peak=float(t[i]), s=float(tt[0]), e=float(tt[-1]),
                                db=float(v[i]), dur_ms=(float(tt[-1]) - float(tt[0])) * 1000,
                                # intensity extent, INCLUDING voiceless frames. The
                                # voiced extent is the wrong duration unit at a
                                # boundary: every sentence-final word in this
                                # material is a trochee with a voiceless coda
                                # (Taser. offenses. records. charges. record.
                                # hearing.), so voiced duration SHRINKS at exactly
                                # the place pre-boundary lengthening should show.
                                # Measured on ek3: voiced-based ratio reads 0.64,
                                # i.e. it reports the human narrator as SHORTENING
                                # his final syllables. He is not.
                                int_s=ns, int_e=ne, int_dur_ms=(ne - ns) * 1000))
        self._nuc_cache[key] = out
        return out

    def stylize(self, nuc, prepausal=False):
        """One nucleus -> a Prosogram tonal segment. Returns start/end semitone,
        the raw slope, the glissando threshold applied, and whether the movement
        is perceptually a glide at all."""
        t, s = self.seg(nuc["s"], nuc["e"])
        if len(t) < 3:
            return None
        T = float(t[-1] - t[0])
        if T < MIN_NUC_MS / 1000.0:
            return None
        slope = float(np.polyfit(t, s, 1)[0])
        icept = float(np.polyfit(t, s, 1)[1])
        G = (0.16 if prepausal else 0.32) / (T * T)
        glide = abs(slope) >= G
        s0 = slope * t[0] + icept
        s1 = slope * t[-1] + icept
        mid = float(np.median(s))
        if not glide:                     # perceived as a level tone
            s0 = s1 = mid
        return dict(t0=float(t[0]), t1=float(t[-1]), dur_ms=T * 1000,
                    int_s=nuc["int_s"], int_e=nuc["int_e"], int_dur_ms=nuc["int_dur_ms"],
                    st_start=s0, st_end=s1, st_mid=mid,
                    slope_st_s=slope, G_st_s=G, glide=bool(glide),
                    move_st=s1 - s0, raw_range_st=float(np.max(s) - np.min(s)))

    def voiceless_tail_ms(self, last_voiced_t, word_end):
        """Energy still radiating after voicing stops, before the boundary.

        A separate boundary cue from pitch, and one no band in score_voice.py or
        contour_metrics.py touches. Human ek3 sentence-finals: 30, 60, 210, 50,
        140, 80 ms - a 7x spread. A TTS that clips every utterance at the last
        voiced frame reads ~0 here on every sentence, which is audible as the
        ending being 'cut' even when the pitch contour is right."""
        m = (self.it > last_voiced_t) & (self.it <= word_end) & (self.iv > self.sil_db + 6.0)
        return float(m.sum()) * TIME_STEP * 1000.0


# ------------------------------------------------------------------ segmentation

def _is_sent_end(tok):
    tok = tok.strip().lower()
    return bool(re.search(r"[.!?][\"')]?$", tok)) and tok not in ABBREV \
        and not re.fullmatch(r"[a-z]\.", tok)


def boundaries(words):
    out = []
    for i, w in enumerate(words):
        tok = w[2].strip().lower()
        if _is_sent_end(tok):
            out.append((i, "sentence", w))
        elif re.search(r"[,;:]$", tok):
            out.append((i, "clause", w))
    return out


def sentences(words):
    sents, cur = [], []
    for w in words:
        cur.append(w)
        if _is_sent_end(w[2]):
            sents.append(cur); cur = []
    if cur:
        sents.append(cur)
    return [s for s in sents if s]


def syl_stress(word):
    key = re.sub(r"[^a-z']", "", word.strip().lower())
    if not key:
        return None
    if key in STRESS_OVERRIDE:
        return STRESS_OVERRIDE[key]
    try:
        from nltk.corpus import cmudict
    except Exception:
        return None
    global _CMU
    try:
        _CMU
    except NameError:
        _CMU = cmudict.dict()
    ent = _CMU.get(key) or _CMU.get(key.rstrip("'s")) or _CMU.get(key.replace("'", ""))
    if not ent:
        return None
    return [int(p[-1]) for p in ent[0] if p[-1].isdigit()]


# ------------------------------------------------------------------ metrics

def terminal_rows(tr, words, bnds, med_nuc_ms):
    """One row per prosodic boundary. NOTHING is dropped silently: a boundary
    whose own final nucleus is unscoreable falls back to the last scoreable
    nucleus within FALLBACK_S and records that in `src`; if even that fails the
    row is kept with src='none' and null metrics, so the count is honest.

    contour_metrics.py `continue`d past these, and because the sentence-final
    words in this script end in voiceless codas (Texas., offenses., records.,
    charges.) it silently discarded 2 of yzv's 3 sentence boundaries and
    reported sf_n=1. See DEFECTS-FOUND #3."""
    rows = []
    for idx, kind, w in bnds:
        a, b = w[0], w[1]
        gap = (words[idx + 1][0] - b) if idx + 1 < len(words) else 1.0
        prepausal = gap >= PREPAUSAL_S
        nuc = tr.nuclei(a, b)
        sty, src = None, "none"
        for n in reversed(nuc):
            s = tr.stylize(n, prepausal)
            if s:
                sty, src = s, "word_final_nucleus"; break
        if sty is None:
            for n in reversed(tr.nuclei(b - FALLBACK_S, b)):
                s = tr.stylize(n, prepausal)
                if s:
                    sty, src = s, "fallback_%dms" % round((b - n["e"]) * 1000); break
        prev = None
        for n in reversed(tr.nuclei(max(tr.t0, b - 1.60), (sty["t0"] - 0.01) if sty else b)):
            p = tr.stylize(n, False)
            if p:
                prev = p; break

        r = dict(i=idx, kind=kind, word=w[2].strip(), t_end=round(b, 2),
                 gap_after_ms=round(gap * 1000), prepausal=prepausal, src=src)
        if sty:
            r.update(
                move_st=round(sty["move_st"], 2),
                raw_move_st=round(sty["slope_st_s"] * (sty["dur_ms"] / 1000.0), 2),
                slope_st_s=round(sty["slope_st_s"], 2),
                G_st_s=round(sty["G_st_s"], 1),
                glide=sty["glide"],
                end_level_st=round(sty["st_end"], 2),
                nuc_dur_ms=round(sty["dur_ms"]),
                rhyme_ms=round((b - sty["int_s"]) * 1000),
                lengthening=round((b - sty["int_s"]) * 1000 / med_nuc_ms, 2) if med_nuc_ms else None,
                voiceless_tail_ms=round(tr.voiceless_tail_ms(sty["t1"], b)),
                step_st=round(sty["st_start"] - prev["st_end"], 2) if prev else None,
                nuclear_range_st=round(
                    max(sty["st_start"], sty["st_end"], prev["st_start"] if prev else -99,
                        prev["st_end"] if prev else -99) -
                    min(sty["st_start"], sty["st_end"], prev["st_start"] if prev else 99,
                        prev["st_end"] if prev else 99), 2) if prev else None,
                cls=_classify(sty, prev),
                shape=_shape_vector(tr, b),
            )
        rows.append(r)
    return rows


def _classify(sty, prev):
    if not sty["glide"]:
        return "level"
    if sty["move_st"] < 0:
        return "rise-fall" if (prev and sty["st_start"] - prev["st_end"] > 1.0) else "fall"
    return "fall-rise" if (prev and prev["st_end"] - sty["st_start"] > 1.0) else "rise"


def _shape_vector(tr, b):
    """Terminal contour over the last TERMINAL_WIN s of VOICED speech before the
    boundary, resampled to SHAPE_POINTS, re-zeroed to its own first point so the
    comparison is of SHAPE, not level. Unvoiced gaps inside the window are
    linearly bridged - stated here because np.interp does it silently."""
    t, s = tr.seg(b - TERMINAL_WIN, b)
    if len(t) < 6:
        return None
    v = np.interp(np.linspace(t[0], t[-1], SHAPE_POINTS), t, s)
    return [round(float(x - v[0]), 3) for x in v]


def theil_sen(x, y):
    if len(x) < 3:
        return None
    sl = [(y[j] - y[i]) / (x[j] - x[i])
          for i, j in itertools.combinations(range(len(x)), 2) if x[j] != x[i]]
    return float(np.median(sl)) if sl else None


def declination(tr, sents):
    """Slope in st/s of the NUCLEUS medians across each sentence, Theil-Sen.
    Topline (nucleus maxima) and baseline (nucleus minima) fitted separately -
    natural declination lowers the topline faster than the baseline, and a flat
    topline with a falling baseline is a different defect from both falling."""
    mid_s, top_s, bot_s, resets, durs = [], [], [], [], []
    prev_end = None
    for s in sents:
        a, b = s[0][0], s[-1][1]
        nucs = [tr.stylize(n) for n in tr.nuclei(a, b)]
        nucs = [n for n in nucs if n]
        if b - a < 1.2 or len(nucs) < 5:
            continue
        x = np.array([(n["t0"] + n["t1"]) / 2 for n in nucs])
        mid_s.append(theil_sen(x, np.array([n["st_mid"] for n in nucs])))
        top_s.append(theil_sen(x, np.array([max(n["st_start"], n["st_end"]) for n in nucs])))
        bot_s.append(theil_sen(x, np.array([min(n["st_start"], n["st_end"]) for n in nucs])))
        durs.append(b - a)
        if prev_end is not None:
            resets.append(nucs[0]["st_start"] - prev_end)
        prev_end = nucs[-1]["st_end"]
    def q(v):
        v = [x for x in v if x is not None]
        return [round(float(np.percentile(v, p)), 2) for p in (25, 50, 75)] if v else None
    return dict(n_declaratives=len(durs), declination_mid_st_s_q=q(mid_s),
                declination_top_st_s_q=q(top_s), declination_base_st_s_q=q(bot_s),
                reset_st_q=q(resets),
                mean_sent_dur_s=round(float(np.mean(durs)), 2) if durs else None)


def load_chars(wav):
    """<stem>_chars.json from align_chars.py, keyed by word index."""
    p = os.path.splitext(wav)[0] + "_chars.json"
    if not os.path.exists(p):
        return None
    return {o["i"]: o for o in json.load(open(p))}


VOWELS = set("aeiouy")


def vowel_groups(spelled, chars):
    """Contiguous runs of vowel letters -> (t_start, t_end). One run per
    orthographic syllable nucleus. Cheap, but grounded in a forced alignment
    rather than in an intensity heuristic that disagreed with the syllable count
    80% of the time."""
    out, i = [], 0
    n = min(len(spelled), len(chars))
    while i < n:
        if spelled[i] in VOWELS:
            j = i
            while j + 1 < n and spelled[j + 1] in VOWELS:
                j += 1
            out.append((float(chars[i][1]), float(chars[j][2])))
            i = j + 1
        else:
            i += 1
    return out


def accent_aligned(tr, words, chars_by_i):
    """Accent placement using FORCED-ALIGNED syllable nuclei.

    Path of record when <stem>_chars.json exists. Each word's spelled form is
    split into vowel-letter runs whose times come from torchaudio MMS_FA CTC
    alignment; the F0 maximum is located per run; the run holding the maximum is
    compared with CMUdict primary stress. Scored only when the word is actually
    ACCENTED (>= ACCENT_MIN_ST excursion) - a deaccented word has no pitch
    accent to place, so asking where its accent landed is meaningless."""
    hit = miss = deacc = unmatched = 0
    misses, watch, scored, deacc_recs = [], [], [], []
    # chars_by_i is keyed by index into the FULL sidecar; `words` here is the
    # span-filtered subset, so match on start time (tolerance 0.30 s - the
    # measured median CTC-vs-ASR start offset is 0.090 s, p90 0.250 s).
    by_t = sorted(chars_by_i.values(), key=lambda o: o["s"])
    tstarts = np.array([o["s"] for o in by_t])
    for (a, b, tok) in words:
        rec_key = re.sub(r"[^a-z']", "", tok.strip().lower())
        on_watch = rec_key in WATCHLIST or rec_key.rstrip("'s") in WATCHLIST
        stpat = syl_stress(tok)
        if not stpat or len(stpat) < 2 or 1 not in stpat:
            continue
        if not on_watch and rec_key in FUNCTION_WORDS:
            continue
        k = int(np.argmin(np.abs(tstarts - a)))
        c = by_t[k] if abs(tstarts[k] - a) <= 0.30 and \
            re.sub(r"[^a-z0-9']", "", by_t[k]["w"].strip().lower()) else None
        if not c:
            unmatched += 1; continue
        vg = vowel_groups(c["spelled"], c["chars"])
        rec = dict(word=tok.strip(), t=round(a, 2), n_syl=len(stpat),
                   expect_idx=stpat.index(1), n_vgroup=len(vg))
        if len(vg) != len(stpat):
            unmatched += 1
            rec["verdict"] = "unmatchable(vowelgroups!=syllables)"
            if on_watch:
                watch.append(rec)
            continue
        pk, lo = [], []
        for s0, s1 in vg:
            _, ss = tr.seg(s0, s1)
            pk.append(float(np.max(ss)) if len(ss) else -99.0)
            lo.append(float(np.min(ss)) if len(ss) else 99.0)
        if max(pk) < -98:
            unmatched += 1; continue
        exc = max(pk) - min(x for x in lo if x < 98)
        # DURATION ratio: the stressed vowel against the mean of the others.
        # This, not F0, is the reliable lexical-stress correlate in English -
        # it is present whether or not the word carries a pitch accent, so it
        # is defined for every word. A TTS that says "bex-AR" instead of
        # "BEX-ar" shows it here even when its F0 looks plausible.
        durs = [s1 - s0 for s0, s1 in vg]
        si = stpat.index(1)
        others = [d for k, d in enumerate(durs) if k != si]
        dur_ratio = durs[si] / (float(np.mean(others)) if others and np.mean(others) > 0 else np.nan)
        rec.update(peak_idx=int(np.argmax(pk)), excursion_st=round(float(exc), 2),
                   syl_peaks_st=[round(x, 2) for x in pk],
                   peak_delay_syl=int(np.argmax(pk)) - si,
                   syl_dur_ms=[round(d * 1000) for d in durs],
                   stress_dur_ratio=round(float(dur_ratio), 2) if np.isfinite(dur_ratio) else None)
        if exc < ACCENT_MIN_ST:
            deacc += 1; rec["verdict"] = "deaccented"
            deacc_recs.append(rec)
        elif int(np.argmax(pk)) == si:
            hit += 1; rec["verdict"] = "hit"; scored.append(rec)
        else:
            miss += 1; rec["verdict"] = "MISS"; misses.append(rec); scored.append(rec)
        if on_watch:
            watch.append(rec)
    tot = hit + miss

    def qq(vals):
        v = [x for x in vals if x is not None and np.isfinite(x)]
        return [round(float(np.percentile(v, p)), 2) for p in (25, 50, 75)] if v else None

    delays = [r["peak_delay_syl"] for r in scored]
    dr_all = [r["stress_dur_ratio"] for r in scored + deacc_recs
              if r.get("stress_dur_ratio") is not None]
    return dict(method="forced_alignment(MMS_FA)+cmudict",
                n_accented_scored=tot, n_deaccented=deacc, n_unmatchable=unmatched,
                # "hit rate" is NOT a correctness rate. English H* peaks align
                # late and routinely spill into the post-stress syllable (peak
                # delay), so a human narrator does not score near 1.0 - ek3
                # measures 0.52 over 48 accented words. The band is set from
                # that, and the DISTRIBUTION metrics below carry the real signal.
                accent_hit_rate=round(hit / tot, 3) if tot else None,
                peak_delay_syl_q=qq(delays),
                peak_delay_far_frac=round(float(np.mean([abs(d) >= 2 for d in delays])), 3)
                if delays else None,
                stress_dur_ratio_q=qq(dr_all),
                misses=misses[:12], watchlist=watch)


def accent(tr, words, sents):
    """Accent placement, restricted to words that ACTUALLY BEAR AN ACCENT.

    contour_metrics.py asked "is the F0 peak on the CMUdict-primary syllable?"
    of every polysyllabic content word. That question is undefined for an
    unaccented word - a deaccented word has no pitch accent to place - so the
    metric was measuring tracker noise on those words and scored the human
    reference at 0.40. Here a word qualifies only if some nucleus in it rises
    ACCENT_MIN_ST above the LOWEST nucleus of the same word, i.e. there is a
    real excursion to locate. Nuclei-to-syllable count mismatch is reported,
    never guessed at."""
    hit = miss = unmatched = unaccented = 0
    misses, watch = [], []
    for a, b, tok in words:
        key = re.sub(r"[^a-z']", "", tok.strip().lower())
        if not key:
            continue
        stpat = syl_stress(tok)
        on_watch = key in WATCHLIST or key.rstrip("'s") in WATCHLIST
        if not on_watch and (key in FUNCTION_WORDS or key in ABBREV):
            continue
        if not stpat or len(stpat) < 2 or 1 not in stpat:
            continue
        nucs = [tr.stylize(n) for n in tr.nuclei(a, b)]
        nucs = [n for n in nucs if n]
        rec = dict(word=tok.strip(), t=round(a, 2), n_syl=len(stpat),
                   expect_idx=stpat.index(1), n_nuc=len(nucs))
        if len(nucs) != len(stpat):
            unmatched += 1
            rec["verdict"] = "unmatchable(nuc!=syl)"
            if on_watch:
                watch.append(rec)
            continue
        pk = [max(n["st_start"], n["st_end"], n["st_mid"]) for n in nucs]
        lo = min(min(n["st_start"], n["st_end"], n["st_mid"]) for n in nucs)
        exc = max(pk) - lo
        rec.update(peak_idx=int(np.argmax(pk)), excursion_st=round(float(exc), 2),
                   peak_st=round(float(max(pk)), 2))
        if exc < ACCENT_MIN_ST:
            unaccented += 1
            rec["verdict"] = "deaccented(excursion<%.1fst)" % ACCENT_MIN_ST
        elif int(np.argmax(pk)) == stpat.index(1):
            hit += 1; rec["verdict"] = "hit"
        else:
            miss += 1; rec["verdict"] = "MISS"
            misses.append(rec)
        if on_watch:
            watch.append(rec)
    tot = hit + miss
    return dict(n_accented_scored=tot, n_deaccented=unaccented,
                n_unmatchable=unmatched,
                accent_hit_rate=round(hit / tot, 3) if tot else None,
                misses=misses[:12], watchlist=watch)


def stereotypy(rows, kind):
    """How SAME are this passage's endings?

    mean pairwise r and mean RMSD were already here; the one that matters is
    MIN pairwise RMSD. A model that reuses one memorised contour for two of six
    sentences leaves the mean looking healthy and the minimum near zero. The
    mean cannot see a duplicate; the minimum is the duplicate detector."""
    V = [np.array(r["shape"]) for r in rows if r["kind"] == kind and r.get("shape")]
    if len(V) < 3:
        return dict(n=len(V), corr_mean=None, rmsd_mean=None, rmsd_min=None)
    cs, ds = [], []
    for i, j in itertools.combinations(range(len(V)), 2):
        x, y = V[i], V[j]
        if x.std() > 1e-6 and y.std() > 1e-6:
            cs.append(float(np.corrcoef(x, y)[0, 1]))
        ds.append(float(np.sqrt(np.mean((x - y) ** 2))))
    return dict(n=len(V),
                corr_mean=round(float(np.mean(cs)), 3) if cs else None,
                corr_max=round(float(np.max(cs)), 3) if cs else None,
                rmsd_mean=round(float(np.mean(ds)), 2),
                rmsd_min=round(float(np.min(ds)), 2))


def entropy_bits(labels):
    if not labels:
        return None
    _, c = np.unique(labels, return_counts=True)
    p = c / c.sum()
    return round(float(-(p * np.log2(p)).sum()), 3)


# ------------------------------------------------------------------ driver

def analyze(wav, span=None, guard=True):
    words = load_words(wav)
    if span:
        t0, t1 = span
        words = [w for w in words if w[1] > t0 and w[0] < t1]
    else:
        keep = [words[0]]
        for a, b in zip(words, words[1:]):
            if b[0] - a[1] > 3.0:
                break
            keep.append(b)
        words = keep
        t0, t1 = words[0][0], words[-1][1]
    g = dict(ok=None, note="guard skipped")
    if guard:
        g, _ = speaker_guard(wav, words, t0, t1)

    tr = Track(wav, t0, t1)
    all_nuc = [tr.stylize(n) for n in tr.nuclei(t0, t1)]
    all_nuc = [n for n in all_nuc if n]
    # median NUCLEUS INTENSITY EXTENT - the denominator for lengthening ratios
    med_nuc_ms = float(np.median([n["int_dur_ms"] for n in all_nuc])) if all_nuc else None

    bnds = boundaries(words)
    rows = terminal_rows(tr, words, bnds, med_nuc_ms)
    sf = [r for r in rows if r["kind"] == "sentence" and r["src"] != "none"]
    cf = [r for r in rows if r["kind"] == "clause" and r["src"] != "none"]

    def q(rs, k):
        x = [r[k] for r in rs if r.get(k) is not None]
        if not x:
            return None
        return [round(float(np.percentile(np.asarray(x, float), p)), 2) for p in (25, 50, 75)]

    def iqr(rs, k):
        # An IQR over fewer than 3 boundaries is not a spread, it is a pair of
        # numbers. Returning 0.0 there manufactures a FAIL on a one-clause
        # passage; return None so the band reports n/a instead.
        n = len([r for r in rs if r.get(k) is not None])
        v = q(rs, k)
        return round(v[2] - v[0], 2) if (v and n >= 3) else None

    def frac(rs, k):
        x = [r[k] for r in rs if r.get(k) is not None]
        return round(float(np.mean(x)), 3) if x else None

    def counts(rs):
        c = {}
        for r in rs:
            c[r.get("cls", "?")] = c.get(r.get("cls", "?"), 0) + 1
        return c

    out = dict(
        file=os.path.basename(wav), span=[round(t0, 2), round(t1, 2)],
        span_s=round(t1 - t0, 2), n_words=len(words),
        f0_med_hz=round(tr.med, 1), med_nucleus_ms=round(med_nuc_ms) if med_nuc_ms else None,
        speaker_guard=g,
        n_boundaries=len(rows),
        n_unscoreable=sum(1 for r in rows if r["src"] == "none"),
        n_fallback=sum(1 for r in rows if r["src"].startswith("fallback")),

        sf_n=len(sf),
        sf_move_st_q=q(sf, "move_st"), sf_move_IQR=iqr(sf, "move_st"),
        sf_end_level_st_q=q(sf, "end_level_st"), sf_end_level_IQR=iqr(sf, "end_level_st"),
        sf_step_st_q=q(sf, "step_st"), sf_step_IQR=iqr(sf, "step_st"),
        sf_nuclear_range_st_q=q(sf, "nuclear_range_st"),
        sf_lengthening_q=q(sf, "lengthening"),
        sf_voiceless_tail_ms_q=q(sf, "voiceless_tail_ms"),
        sf_voiceless_tail_IQR=iqr(sf, "voiceless_tail_ms"),
        sf_glide_frac=frac(sf, "glide"),
        sf_cls=counts(sf), sf_cls_entropy_bits=entropy_bits([r["cls"] for r in sf]),
        sf_n_distinct_cls=len(counts(sf)),

        cf_n=len(cf),
        cf_move_st_q=q(cf, "move_st"), cf_move_IQR=iqr(cf, "move_st"),
        cf_end_level_st_q=q(cf, "end_level_st"), cf_end_level_IQR=iqr(cf, "end_level_st"),
        cf_step_IQR=iqr(cf, "step_st"),
        cf_lengthening_q=q(cf, "lengthening"),
        cf_voiceless_tail_ms_q=q(cf, "voiceless_tail_ms"),
        cf_glide_frac=frac(cf, "glide"),
        cf_cls=counts(cf), cf_cls_entropy_bits=entropy_bits([r["cls"] for r in cf]),

        stereotypy_sentence=stereotypy(rows, "sentence"),
        stereotypy_clause=stereotypy(rows, "clause"),
        **declination(tr, sentences(words)),
        accent=(accent_aligned(tr, words, load_chars(wav)) if load_chars(wav)
                else accent(tr, words, sentences(words))),
    )
    if out["sf_end_level_st_q"] and out["cf_end_level_st_q"]:
        out["sf_minus_cf_end_level_st"] = round(
            out["sf_end_level_st_q"][1] - out["cf_end_level_st_q"][1], 2)
        out["sf_minus_cf_lengthening"] = round(
            (out["sf_lengthening_q"][1] - out["cf_lengthening_q"][1]), 2) \
            if out["sf_lengthening_q"] and out["cf_lengthening_q"] else None
    out["_rows"] = rows
    return out


# ------------------------------------------------------------------ bands
#
# DERIVED, NOT INVENTED. Every band below is anchored on the two Audit the Court
# narration spans measured with the speaker guard on:
#   ek3_open.wav --span 5.5,62.95   (176 words, 57.3 s, 6 sentence boundaries)
#   yzv_open.wav --span 5.5,33.3    ( 82 words, 27.7 s, 3 sentence boundaries)
# `ref` is [ek3, yzv]. Bands are printed WITH the reference values by --ref so a
# gate that its own reference fails is visible rather than discovered later.
#
# SMALL-N WARNING, stated up front: n=6 and n=3 sentence-final boundaries. An
# IQR from n=3 is a statement about three numbers. Every sentence-final band is
# therefore ONE-SIDED where the direction of the reported failure is known -
# too-uniform is the tell, too-varied is not - and the better-powered
# clause-final set (n=12 / n=7) carries the two-sided bands.
# Format: metric -> (lo, hi, "ek3 / yzv reference values")
CONTOUR_BANDS = {
    # ---- THE STEP. The single most consistent thing this narrator does.
    # step_st = semitones from the END of the penultimate nucleus to the START
    # of the final nucleus. Positive on 9 OF 9 pooled sentence endings across
    # both speakers: 3.86 2.93 4.12 0.32 3.61 2.55 5.02 4.52 5.43, median 3.86.
    # He does not glide down INTO a full stop - he steps UP onto the last
    # syllable and then holds or falls off it. A TTS that decays smoothly into
    # the boundary is out of band here while matching every global statistic.
    "sf_step_med":            (1.50, 7.00, "3.27 / 5.02"),
    "sf_step_min":            (0.00, 99.0, "0.32 / 4.77"),   # never negative
    # ---- variety of endings. One-sided: only "too same" is the reported tell.
    "sf_move_IQR":            (0.60, 99.0, "4.20 / 1.67"),
    "sf_end_level_IQR":       (0.60, 99.0, "5.07 / 1.56"),
    "stereo_rmsd_min_sent":   (0.90, 99.0, "2.08 / 2.08"),   # duplicate detector
    "stereo_corr_max_sent":   (-1.00, 0.75, "0.42 / 0.569"),
    "sf_n_distinct_cls":      (2, 9, "2 / 2"),
    # ---- boundary TYPE. 0 of 9 sentence endings is a plain fall; 5 of 19
    # clause endings is. The narrator's plain falls live at COMMAS, and his full
    # stops are level (5/9) or rise-fall (4/9) - the inverse of the stereotyped
    # terminal fall. This band fails a render that puts a plain fall on every
    # sentence, which is the specific behaviour being complained about.
    "sf_plain_fall_frac":     (0.00, 0.34, "0.00 / 0.00"),
    "sf_glide_frac":          (0.15, 0.80, "0.50 / 0.333"),
    # ---- duration cues at the boundary
    "sf_lengthening_med":     (1.35, 2.40, "1.72 / 1.83"),
    "cf_lengthening_med":     (0.85, 2.30, "1.12 / 1.63"),
    "sf_voiceless_tail_med":  (15.0, 260.0, "110 / 40"),
    # ---- clause-final is the better-powered set (n=12 / n=7)
    "cf_move_IQR":            (1.00, 8.00, "3.93 / 2.98"),
    "cf_end_level_IQR":       (1.00, 8.00, "2.53 / 2.44"),
    # ---- declination
    "declination_mid_med":    (-1.00, 0.05, "-0.17 / -0.53"),
    # ---- accent placement. accent_hit_rate is NOT a correctness rate: English
    # H* peaks align late, so the HUMAN scores 0.521 and 0.619. The gate that
    # actually catches a wrong-syllable render is peak_delay_far_frac - the
    # share of accented words whose F0 peak sits >= 2 syllables from lexical
    # stress. Human: 0.042 and 0.095.
    "accent_hit_rate":        (0.42, 1.01, "0.521 / 0.619"),
    "peak_delay_med":         (-0.5, 1.5, "0.0 / 0.0"),
    "peak_delay_far_frac":    (0.00, 0.20, "0.042 / 0.095"),
    "stress_dur_ratio_med":   (0.85, 2.00, "1.00 / 1.00"),
}

# MEASURED AND DELIBERATELY NOT GATED - the two references disagree in SIGN, so
# any band would be a coin flip dressed as a threshold:
#   sf_minus_cf_end_level_st   ek3 -1.38, yzv +2.23
#     "sentences must end lower than commas" is false for this narrator. yzv
#     ends full stops 2.2 st HIGHER than its commas. contour_metrics.py gated
#     this at (-9.0, -0.30) and would have failed its own reference.
#   sf_step_IQR                ek3 1.15, yzv 0.45
#     n=6 and n=3. A floor of 0.80 fails yzv. Reported, not gated.
#   reset_st_q (median)        ek3 -0.07, yzv +3.14
#
# THRESHOLD SENSITIVITY, stated rather than buried: the glissando test scales as
# 1/T^2, so a short final nucleus is hard to call a glide. yzv's second "Texas."
# has a real -4.22 st raw movement over a 70 ms nucleus (slope -60.4 st/s) and
# is still classed 'level' because G = 65.3 st/s. Both stylized (`move_st`) and
# unstylized (`raw_move_st`) movement are reported on every row for this reason.
# Pooled sentence-final nucleus durations are 60-180 ms, median 90 ms.


def grade(o, rows=None):
    f = dict(o)
    med = lambda q: q[1] if q else None
    f["stereo_rmsd_min_sent"] = o["stereotypy_sentence"]["rmsd_min"]
    f["stereo_corr_max_sent"] = o["stereotypy_sentence"]["corr_max"]
    f["declination_mid_med"] = med(o["declination_mid_st_s_q"])
    f["sf_lengthening_med"] = med(o["sf_lengthening_q"])
    f["cf_lengthening_med"] = med(o["cf_lengthening_q"])
    f["sf_voiceless_tail_med"] = med(o["sf_voiceless_tail_ms_q"])
    f["sf_step_med"] = med(o["sf_step_st_q"])
    a = o["accent"]
    f["accent_hit_rate"] = a.get("accent_hit_rate")
    f["peak_delay_med"] = med(a.get("peak_delay_syl_q"))
    f["peak_delay_far_frac"] = a.get("peak_delay_far_frac")
    f["stress_dur_ratio_med"] = med(a.get("stress_dur_ratio_q"))
    sf = [r for r in (rows or []) if r["kind"] == "sentence" and r.get("cls")]
    if sf:
        f["sf_plain_fall_frac"] = round(sum(r["cls"] == "fall" for r in sf) / len(sf), 3)
        st = [r["step_st"] for r in sf if r.get("step_st") is not None]
        f["sf_step_min"] = round(min(st), 2) if st else None
    res, fails, na = {}, [], []
    for k, (lo, hi, ref) in CONTOUR_BANDS.items():
        v = f.get(k)
        if v is None:
            res[k] = f"n/a  (ref {ref})"; na.append(k); continue
        ok = lo <= v <= hi
        res[k] = f"{'PASS' if ok else 'FAIL'} {v} in [{lo},{hi}]  (ref {ref})"
        if not ok:
            fails.append(k)
    if not o["speaker_guard"].get("ok", True):
        res["SPEAKER_GUARD"] = "FAIL - span contains a second speaker: " + \
            json.dumps(o["speaker_guard"]["suspect_runs"])
        fails.append("speaker_guard")
    res["n_not_applicable"] = len(na)
    res["VERDICT"] = "PASS" if not fails else "FAIL: " + ", ".join(fails)
    return res


if __name__ == "__main__":
    args, spans, opts = [], {}, set()
    it = iter(sys.argv[1:])
    for a in it:
        if a == "--span":
            spans[len(args) - 1] = tuple(float(x) for x in next(it).split(","))
        elif a.startswith("--"):
            opts.add(a)
        else:
            args.append(a)
    for i, path in enumerate(args):
        o = analyze(path, spans.get(i), guard="--noguard" not in opts)
        rows = o.pop("_rows")
        print(json.dumps({"contour": o, "graded": grade(o, rows)}, indent=2, default=str))
        if "--rows" in opts:
            print(json.dumps(rows, indent=1, default=str))

# ============================================================ DEFECTS-FOUND
# Four bugs in the code this file replaces, each reproducible.
#
# 1. SPEAKER CONTAMINATION IN THE REFERENCE ITSELF (score_voice.py AND
#    contour_metrics.py). Both cut a span at the first gap > 3.0 s.
#    ek3_open.wav's narrator stops at 62.92 s and Judge Boyd starts at 63.50 s -
#    a 0.58 s gap. Nothing cuts. 14.58 s of a second speaker is inside every
#    published ek3 reference number. Measured, narration-only vs as-shipped:
#        WPM        184.2  vs 176.3   (band is 172-182: the TRUE rate FAILS it)
#        F0 median   96.8  vs  97.8
#        F0 sd st     3.02 vs   3.16
#    The intruder is female: torchcrepe 0.0.24 'full' on GPU, no ceiling
#    assumption, reads that segment at 192.8 Hz median. Praat at ceiling 170
#    reads the SAME segment at 103.9 Hz - a clean halving - which is exactly why
#    the contamination left no trace in the statistics. CREPE and Praat agree to
#    within 0.5 st on both narrators (ek3 99.6 vs 96.8; yzv 105.3 vs 103.7) and
#    disagree by an octave only where the second speaker is. yzv_open.wav is
#    fine: its handoff is across a 25.4 s gap, so the 3.0 s rule does cut it.
#    The brief had this backwards - yzv was the file believed contaminated.
#
# 2. NUCLEI WERE NOT PROSOGRAM NUCLEI. contour_metrics.py extended each
#    intensity peak over "contiguous voiced frames", not to -3/-9 dB. That makes
#    nuclei both degenerate and fused, and it produced sentence-final nucleus
#    slopes of -84.75 st/s on the human reference - a number with no physical
#    meaning. Because glissando G = 0.16/T^2 explodes as T shrinks (T=0.03 s ->
#    G=178 st/s), those degenerate nuclei were then all classified "level", and
#    sf_glide_frac came out 0.0 for a human narrator.
#
# 3. BOUNDARIES WERE DROPPED SILENTLY. boundary_metrics() did `continue` when it
#    found fewer than 4 voiced frames. The sentence-final words in this material
#    end in voiceless codas - Texas. offenses. records. charges. - so the drop
#    was systematic, not random. yzv has 3 sentence boundaries; the old file
#    reported sf_n=1 and then computed an IQR of 0.00 from that single value and
#    FAILED the human reference on it. Every dropped row is now kept with
#    src='none' and counted in n_unscoreable.
#
# 4. THE ACCENT METRIC ASKED AN UNDEFINED QUESTION. It scored every polysyllabic
#    content word for "F0 peak on the primary-stress syllable", including
#    deaccented words that carry no pitch accent at all, and rated the human
#    narrator 0.40 with 32 of 42 words unmatchable. Now a word is scored only if
#    it shows a >= 1.5 st excursion, and the tokens that actually matter
#    (Bexar, 187th, nolo contendere, the names) are reported INDIVIDUALLY via
#    WATCHLIST instead of averaged into a rate that cannot be acted on.
#
# 5. NOT A BUG BUT A LIMIT, MEASURED: the reference gives n=6 and n=3
#    sentence-final boundaries. Bands on sentence-final distributions are
#    one-sided for that reason and are stated as such above.
