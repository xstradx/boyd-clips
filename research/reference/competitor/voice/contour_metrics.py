#!/usr/bin/env python
"""contour_metrics.py - measure the SHAPE of the F0 contour, not its statistics.

score_voice.py measures global statistics (WPM, F0 median/sd, pauses, LUFS). A
render can pass every one of those bands and still be instantly identifiable as
synthetic, because the tell is SHAPE: every sentence ending traces the same
stereotyped curve, and the accent lands on the wrong syllable of names and
numbers. This module measures those two things.

RUN WITH THE ABSOLUTE INTERPRETER PATH:
  C:\\Users\\natha\\AppData\\Local\\Programs\\Python\\Python312\\python.exe contour_metrics.py cand.wav

METHOD / PROVENANCE
  * Pitch:   Praat autocorrelation via parselmouth, pitch_ceiling=170 (see
             score_voice.py bottom note - 350 octave-doubles this narrator).
  * Nuclei:  syllabic-nucleus detection after de Jong & Wempe (2009), Behavior
             Research Methods 41(2):385-390 - intensity peaks that are voiced,
             above (max99 - 25) dB, and separated by a >= 2 dB dip.
  * Glide:   the glissando threshold from Prosogram 3.05 (Piet Mertens,
             https://sites.google.com/site/prosogram/ , fetched 2026-08-13):
             a pitch movement of duration T seconds is heard as a GLIDE rather
             than a LEVEL tone only if its slope exceeds G = 0.32/T^2 st/s
             (0.16/T^2 when the movement is pre-pausal). Everything below G is
             perceptually flat no matter what the regression says. This is what
             lets us call a boundary "level" on a perceptual basis instead of an
             arbitrary semitone cutoff.
  * Stress:  CMUdict via nltk (123455 entries) + a local override table for the
             proper nouns in this script that CMUdict does not carry.
"""
import json, os, re, sys, subprocess
import numpy as np
import parselmouth
from parselmouth.praat import call

PITCH_FLOOR   = 60
PITCH_CEILING = 170          # MANDATORY - see score_voice.py
TIME_STEP     = 0.01
SIL_DB_REL    = 25.0         # de Jong & Wempe silence threshold, dB below max99
MIN_DIP_DB    = 2.0          # de Jong & Wempe minimum dip between nuclei
TERMINAL_WIN  = 0.40         # s of speech before a boundary used for shape
SHAPE_POINTS  = 12           # resample length for the stereotypy comparison
PREPAUSAL_S   = 0.25         # a following gap this long makes a boundary pre-pausal

ABBREV = {"mr.", "mrs.", "ms.", "dr.", "jr.", "sr.", "st.", "vs.", "no.", "inc."}
FUNCTION_WORDS = set("""a an the and or but nor for so yet of in on at to from by with
without into onto upon over under about after before during against between among
is are was were be been being am do does did done have has had having will would
shall should can could may might must not no nor as if then than that this these
those there here it its it's he she they them his her their our your my me we us
you i who whom whose which what when where why how all any some each every both
either neither one two too very just also only more most other another such own
same s t re ve ll d m""".split())

# CMUdict has no Texas county names, no legal Latin, no docket formats.
STRESS_OVERRIDE = {
    "bexar":        [1, 0],            # BAY-har
    "castillo":     [0, 1, 0],
    "moody":        [1, 0],
    "erik":         [1, 0],
    "nolo":         [1, 0],
    "contendere":   [0, 1, 0, 0],
    "fleischer":    [1, 0],
    "fleischer's":  [1, 0],
    "boyd":         [1],
    "garcia":       [0, 1, 0],
    "martinez":     [0, 1, 0],
    "187th":        [0, 1, 0, 0],      # one-eighty-SEV-enth
}


# ---------------------------------------------------------------- infrastructure

def load_words(wav):
    """Word timings: prefer a sidecar <stem>_words.json, else transcribe."""
    side = os.path.splitext(wav)[0] + "_words.json"
    if os.path.exists(side):
        w = json.load(open(side))
        return [(float(x["s"]), float(x["e"]), x["w"]) for x in w]
    from faster_whisper import WhisperModel
    m = WhisperModel("small.en", device="cpu", compute_type="int8")
    segs, _ = m.transcribe(wav, word_timestamps=True, language="en")
    return [(w.start, w.end, w.word) for s in segs for w in (s.words or [])]


def narration_span(words, gap_cut=3.0):
    """Words up to the first gap > gap_cut. NOTE this is NOT sufficient for the
    reference files - see the --span override and the note in the report."""
    out = [words[0]]
    for a, b in zip(words, words[1:]):
        if b[0] - a[1] > gap_cut:
            break
        out.append(b)
    return out


class Track:
    """Pitch + intensity over one narration span, with semitone conversion."""

    def __init__(self, wav, t0, t1, margin=0.30):
        snd = parselmouth.Sound(wav)
        if snd.n_channels > 1:
            snd = snd.convert_to_mono()
        a = max(t0 - margin, snd.xmin)
        b = min(t1 + margin, snd.xmax)
        # Extract the narration span BEFORE tracking. Praat's AC pitch path
        # search is global over the object; building it across a speaker change
        # lets the other voice's range influence this one's.
        part = snd.extract_part(from_time=a, to_time=b, preserve_times=True)
        self.snd = part
        p = part.to_pitch_ac(time_step=TIME_STEP, pitch_floor=PITCH_FLOOR,
                             pitch_ceiling=PITCH_CEILING)
        self.pt = np.asarray(p.xs())
        self.pf = np.asarray(p.selected_array["frequency"])
        inspan = (self.pt >= t0) & (self.pt <= t1)
        self.pf[~inspan] = 0.0
        v = self.pf[self.pf > 0]
        if len(v) < 50:
            raise SystemExit("too little voiced speech in span")
        self.med = float(np.median(v))
        self.t0, self.t1 = t0, t1
        # semitones re speaker median; unvoiced -> nan
        self.st = np.where(self.pf > 0, 12 * np.log2(np.maximum(self.pf, 1e-9) / self.med), np.nan)
        inten = part.to_intensity(minimum_pitch=PITCH_FLOOR, time_step=TIME_STEP)
        self.it = np.asarray(inten.xs())
        self.iv = np.asarray(inten.values[0])
        self.sil_db = float(np.percentile(self.iv[np.isfinite(self.iv)], 99)) - SIL_DB_REL

    def seg(self, a, b):
        """(times, semitones) of voiced frames in [a,b]."""
        m = (self.pt >= a) & (self.pt <= b) & np.isfinite(self.st)
        return self.pt[m], self.st[m]

    def nuclei(self, a, b):
        """Syllabic nuclei in [a,b] as (t_peak, t_start, t_end, db) - de Jong &
        Wempe: voiced intensity maxima above the silence floor, separated by a
        dip of at least MIN_DIP_DB."""
        m = (self.it >= a) & (self.it <= b)
        t, v = self.it[m], self.iv[m]
        if len(t) < 3:
            return []
        peaks = []
        for i in range(1, len(v) - 1):
            if v[i] >= v[i - 1] and v[i] > v[i + 1] and v[i] > self.sil_db:
                peaks.append(i)
        # require a real dip between consecutive peaks, else keep the louder
        kept = []
        for i in peaks:
            if not kept:
                kept.append(i); continue
            j = kept[-1]
            dip = v[j:i + 1].min()
            if min(v[j], v[i]) - dip >= MIN_DIP_DB:
                kept.append(i)
            elif v[i] > v[j]:
                kept[-1] = i
        out = []
        for i in kept:
            # voiced check
            k = np.argmin(np.abs(self.pt - t[i]))
            if not np.isfinite(self.st[k]):
                continue
            # nucleus extent = contiguous voiced frames around the peak
            lo = hi = k
            while lo > 0 and np.isfinite(self.st[lo - 1]) and self.pt[lo - 1] >= a - 0.02:
                lo -= 1
            while hi < len(self.st) - 1 and np.isfinite(self.st[hi + 1]) and self.pt[hi + 1] <= b + 0.02:
                hi += 1
            out.append((float(t[i]), float(self.pt[lo]), float(self.pt[hi]), float(v[i])))
        # merge nuclei that ended up sharing one voiced run
        return out


# ---------------------------------------------------------------- segmentation

def sentences(words):
    """Group words into sentences on terminal punctuation, skipping abbreviations
    ('Mr.' is not a sentence boundary) and single-letter initials."""
    sents, cur = [], []
    for w in words:
        cur.append(w)
        tok = w[2].strip().lower()
        if re.search(r"[.!?]\"?$", tok) and tok not in ABBREV and not re.fullmatch(r"[a-z]\.", tok):
            sents.append(cur); cur = []
    if cur:
        sents.append(cur)
    return [s for s in sents if s]


def boundaries(words):
    """Every prosodic boundary candidate: (index, kind, word). kind in
    {sentence, clause}. Clause = trailing comma / semicolon / colon."""
    out = []
    for i, w in enumerate(words):
        tok = w[2].strip().lower()
        if re.search(r"[.!?]\"?$", tok) and tok not in ABBREV and not re.fullmatch(r"[a-z]\.", tok):
            out.append((i, "sentence", w))
        elif re.search(r"[,;:]$", tok):
            out.append((i, "clause", w))
    return out


def syl_stress(word):
    """[stress per syllable] from CMUdict, 1=primary 2=secondary 0=unstressed."""
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


# ---------------------------------------------------------------- contour metrics

def _endpoints(st, k=3):
    """Robust start/end values of a short contour."""
    k = max(1, min(k, len(st) // 2 or 1))
    return float(np.median(st[:k])), float(np.median(st[-k:]))


def glissando_G(T, prepausal):
    """Prosogram perceptual glide threshold in st/s for a movement of T seconds."""
    T = max(T, 0.03)
    return (0.16 if prepausal else 0.32) / (T * T)


def boundary_metrics(tr, words, bnds):
    rows = []
    for idx, kind, w in bnds:
        a, b = w[0], w[1]
        nxt_gap = (words[idx + 1][0] - b) if idx + 1 < len(words) else 1.0
        prepausal = nxt_gap >= PREPAUSAL_S
        nuc = tr.nuclei(a, b)
        # --- final nucleus (the syllable carrying the boundary tone)
        if nuc:
            _, ns, ne, _ = nuc[-1]
        else:
            ns, ne = a, b
        t, s = tr.seg(ns, ne)
        if len(t) < 4:
            t, s = tr.seg(max(a, b - 0.30), b)
        if len(t) < 4:
            continue
        T = float(t[-1] - t[0])
        s0, s1 = _endpoints(s)
        slope = float(np.polyfit(t, s, 1)[0]) if T > 0.02 else 0.0
        G = glissando_G(T, prepausal)
        is_glide = abs(slope) >= G
        # direction & internal shape
        net = s1 - s0
        imax, imin = int(np.argmax(s)), int(np.argmin(s))
        interior = 0.20 < (imax / max(len(s) - 1, 1)) < 0.80
        interior_lo = 0.20 < (imin / max(len(s) - 1, 1)) < 0.80
        if not is_glide:
            cls = "level"
        elif net < 0 and interior and (s[imax] - s0) > 0.5:
            cls = "rise-fall"
        elif net > 0 and interior_lo and (s0 - s[imin]) > 0.5:
            cls = "fall-rise"
        elif net < 0:
            cls = "fall"
        else:
            cls = "rise"

        # --- pre-boundary tail: the last TERMINAL_WIN s of voiced speech
        tt, ts = tr.seg(b - TERMINAL_WIN, b)
        tail_net = float(_endpoints(ts)[1] - _endpoints(ts)[0]) if len(ts) >= 4 else float("nan")
        tail_range = float(np.nanmax(ts) - np.nanmin(ts)) if len(ts) >= 4 else float("nan")

        rows.append(dict(
            i=idx, kind=kind, word=w[2].strip(), t_end=round(b, 2),
            gap_after_ms=round(nxt_gap * 1000), prepausal=prepausal,
            nuc_dur_ms=round(T * 1000), nuc_net_st=round(net, 2),
            nuc_slope_st_s=round(slope, 2), gliss_G_st_s=round(G, 2),
            perceived_glide=bool(is_glide), cls=cls,
            end_level_st=round(s1, 2),
            tail_net_st=round(tail_net, 2) if np.isfinite(tail_net) else None,
            tail_range_st=round(tail_range, 2) if np.isfinite(tail_range) else None,
            shape=_shape_vector(tr, b),
        ))
    return rows


def _shape_vector(tr, b):
    """Normalised terminal contour: the last TERMINAL_WIN s of voiced speech,
    resampled to SHAPE_POINTS, expressed in st relative to its own first point.
    Level is removed on purpose - this compares SHAPE only."""
    t, s = tr.seg(b - TERMINAL_WIN, b)
    if len(t) < 6:
        return None
    grid = np.linspace(t[0], t[-1], SHAPE_POINTS)
    v = np.interp(grid, t, s)
    return [round(float(x - v[0]), 3) for x in v]


def stereotypy(rows, kind="sentence"):
    """How SAME are this passage's endings? Mean pairwise Pearson r between
    normalised terminal contours (1.0 = every sentence ends identically) and
    mean pairwise RMS distance in semitones."""
    V = [np.array(r["shape"]) for r in rows if r["kind"] == kind and r["shape"]]
    if len(V) < 3:
        return dict(n=len(V), shape_corr_mean=None, shape_rmsd_st=None)
    cs, ds = [], []
    for i in range(len(V)):
        for j in range(i + 1, len(V)):
            x, y = V[i], V[j]
            if x.std() > 1e-6 and y.std() > 1e-6:
                cs.append(float(np.corrcoef(x, y)[0, 1]))
            ds.append(float(np.sqrt(np.mean((x - y) ** 2))))
    return dict(n=len(V),
                shape_corr_mean=round(float(np.mean(cs)), 3) if cs else None,
                shape_rmsd_st=round(float(np.mean(ds)), 2))


def entropy_bits(labels):
    if not labels:
        return None
    _, c = np.unique(labels, return_counts=True)
    p = c / c.sum()
    return round(float(-(p * np.log2(p)).sum()), 3)


def declination(tr, sents):
    """Slope of F0 (st) against time within each declarative, plus the reset
    across each sentence boundary."""
    slopes, resets, spans = [], [], []
    prev_end = None
    for s in sents:
        a, b = s[0][0], s[-1][1]
        if b - a < 1.2:
            continue
        t, v = tr.seg(a, b)
        if len(t) < 25:
            continue
        sl = float(np.polyfit(t, v, 1)[0])
        slopes.append(sl); spans.append(b - a)
        st_first = float(np.median(v[:5])); st_last = float(np.median(v[-5:]))
        if prev_end is not None:
            resets.append(st_first - prev_end)
        prev_end = st_last
    def q(x):
        if not x:
            return None
        x = np.asarray(x)
        return [round(float(np.percentile(x, p)), 2) for p in (25, 50, 75)]
    return dict(n_declaratives=len(slopes),
                declination_st_s_q=q(slopes),
                reset_st_q=q(resets),
                mean_sent_dur_s=round(float(np.mean(spans)), 2) if spans else None)


def accent_placement(tr, words):
    """On polysyllabic CONTENT words: does the F0 peak land on the syllable
    CMUdict marks as primary stress? Nuclei are matched to syllables in order;
    a word whose nucleus count != syllable count is reported separately rather
    than silently guessed at."""
    hit = miss = unmatched = 0
    misses = []
    for a, b, tok in words:
        key = re.sub(r"[^a-z']", "", tok.strip().lower())
        if not key or key in FUNCTION_WORDS or key in ABBREV:
            continue
        st = syl_stress(tok)
        if not st or len(st) < 2 or 1 not in st:
            continue
        nuc = tr.nuclei(a, b)
        if len(nuc) != len(st):
            unmatched += 1
            continue
        pk = []
        for _, ns, ne, _ in nuc:
            _, s = tr.seg(ns, ne)
            pk.append(float(np.max(s)) if len(s) else -99.0)
        if int(np.argmax(pk)) == st.index(1):
            hit += 1
        else:
            miss += 1
            misses.append((tok.strip(), st.index(1), int(np.argmax(pk)), len(st)))
    tot = hit + miss
    return dict(n_scored=tot, n_unmatchable=unmatched,
                accent_hit_rate=round(hit / tot, 3) if tot else None,
                example_misses=misses[:10])


# ---------------------------------------------------------------- driver

def analyze(wav, span=None, label=None):
    words = load_words(wav)
    if span:
        t0, t1 = span
        words = [w for w in words if w[1] > t0 and w[0] < t1]
    else:
        words = narration_span(words)
        t0, t1 = words[0][0], words[-1][1]
    tr = Track(wav, t0, t1)
    sents = sentences(words)
    bnds = boundaries(words)
    rows = boundary_metrics(tr, words, bnds)
    sfin = [r for r in rows if r["kind"] == "sentence"]
    cfin = [r for r in rows if r["kind"] == "clause"]

    def q(rs, k):
        x = [r[k] for r in rs if r.get(k) is not None]
        if not x:
            return None
        x = np.asarray(x, float)
        return [round(float(np.percentile(x, p)), 2) for p in (25, 50, 75)]

    def iqr(rs, k):
        v = q(rs, k)
        return round(v[2] - v[0], 2) if v else None

    out = dict(
        file=os.path.basename(wav), label=label or os.path.basename(wav),
        span=[round(t0, 2), round(t1, 2)], span_s=round(t1 - t0, 2),
        n_words=len(words), n_sentences=len(sents),
        f0_med_hz=round(tr.med, 1),
        # ---- terminal contour, sentence-final
        sf_n=len(sfin),
        sf_nuc_net_st_q=q(sfin, "nuc_net_st"), sf_nuc_net_IQR=iqr(sfin, "nuc_net_st"),
        sf_slope_st_s_q=q(sfin, "nuc_slope_st_s"),
        sf_end_level_st_q=q(sfin, "end_level_st"), sf_end_level_IQR=iqr(sfin, "end_level_st"),
        sf_tail_net_st_q=q(sfin, "tail_net_st"), sf_tail_net_IQR=iqr(sfin, "tail_net_st"),
        sf_tail_range_st_q=q(sfin, "tail_range_st"),
        sf_glide_frac=round(float(np.mean([r["perceived_glide"] for r in sfin])), 3) if sfin else None,
        sf_cls=dict(zip(*[list(x) for x in np.unique([r["cls"] for r in sfin], return_counts=True)])) if sfin else {},
        sf_cls_entropy_bits=entropy_bits([r["cls"] for r in sfin]),
        # ---- terminal contour, clause-final
        cf_n=len(cfin),
        cf_nuc_net_st_q=q(cfin, "nuc_net_st"), cf_nuc_net_IQR=iqr(cfin, "nuc_net_st"),
        cf_end_level_st_q=q(cfin, "end_level_st"),
        cf_glide_frac=round(float(np.mean([r["perceived_glide"] for r in cfin])), 3) if cfin else None,
        cf_cls=dict(zip(*[list(x) for x in np.unique([r["cls"] for r in cfin], return_counts=True)])) if cfin else {},
        # ---- separation between the two boundary strengths
        sf_minus_cf_end_level_st=None,
        # ---- stereotypy
        stereotypy_sentence=stereotypy(rows, "sentence"),
        stereotypy_clause=stereotypy(rows, "clause"),
        # ---- declination
        **declination(tr, sents),
        # ---- accent
        accent=accent_placement(tr, words),
    )
    if out["sf_end_level_st_q"] and out["cf_end_level_st_q"]:
        out["sf_minus_cf_end_level_st"] = round(out["sf_end_level_st_q"][1] - out["cf_end_level_st_q"][1], 2)
    out["_rows"] = rows
    return out


# Pass bands. Derived from the two Audit the Court narration spans; see
# report for which bands the reference itself passes.
CONTOUR_BANDS = {
    "sf_nuc_net_IQR":            (1.50, 9.00),   # ending VARIETY - the headline
    "sf_end_level_IQR":          (1.20, 9.00),
    "sf_tail_net_IQR":           (1.50, 12.0),
    "sf_glide_frac":             (0.40, 0.95),   # some endings must be flat
    "sf_cls_entropy_bits":       (1.00, 2.40),   # >=2 boundary types in real use
    "sf_minus_cf_end_level_st":  (-9.0, -0.30),  # sentences must end LOWER than commas
    "declination_st_s_med":      (-1.60, 0.10),
    "accent_hit_rate":           (0.70, 1.01),
    "stereo_corr_sentence":      (-1.00, 0.55),  # identical endings -> r -> 1
    "stereo_rmsd_sentence_st":   (1.20, 9.00),
}


def grade_contour(o):
    flat = dict(o)
    flat["declination_st_s_med"] = o["declination_st_s_q"][1] if o["declination_st_s_q"] else None
    flat["accent_hit_rate"] = o["accent"]["accent_hit_rate"]
    flat["stereo_corr_sentence"] = o["stereotypy_sentence"]["shape_corr_mean"]
    flat["stereo_rmsd_sentence_st"] = o["stereotypy_sentence"]["shape_rmsd_st"]
    res, fails = {}, []
    for k, (lo, hi) in CONTOUR_BANDS.items():
        v = flat.get(k)
        if v is None:
            res[k] = "n/a"; continue
        ok = lo <= v <= hi
        res[k] = f"{'PASS' if ok else 'FAIL'} {v} in [{lo},{hi}]"
        if not ok:
            fails.append(k)
    res["VERDICT"] = "PASS" if not fails else "FAIL: " + ", ".join(fails)
    return res


if __name__ == "__main__":
    args, spans = [], {}
    it = iter(sys.argv[1:])
    for a in it:
        if a == "--span":
            spans[len(args) - 1] = tuple(float(x) for x in next(it).split(","))
        else:
            args.append(a)
    for i, path in enumerate(args):
        o = analyze(path, spans.get(i))
        rows = o.pop("_rows")
        print(json.dumps({"contour": o, "graded": grade_contour(o)}, indent=2, default=str))
        if os.environ.get("CONTOUR_ROWS"):
            print(json.dumps(rows, indent=1, default=str))
