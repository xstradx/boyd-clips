"""
Contour probe: shape of F0 at prosodic boundaries, measured per-segment.

Fixes the earlier probe's two errors:
  1. Pitch object is built on the SENTENCE window (+/- pad), never the whole file,
     so non-narration audio elsewhere in the file cannot enter the analysis.
  2. Explicit pitch_floor=55 / pitch_ceiling=170 (autocorrelation) everywhere,
     so no octave doubling.

Outputs, per file:
  - per-boundary table: type (period / comma), final-word F0 slope (st/s),
    net movement (st), boundary-end F0 re speaker median (st), nucleus->end
    excursion (st), voiced fraction and creak proxy in final 200 ms,
    pre-boundary lengthening ratio, following pause (s)
  - sentence-level declination (st/s) fitted on voiced frames
  - summary quartiles
"""
import json, sys, math, statistics as st
import numpy as np
import parselmouth
from parselmouth.praat import call

FLOOR, CEIL = 55.0, 170.0
SR_PAD = 0.25          # seconds of context on each side for the Pitch window
CREAK_WIN = 0.20       # final 200 ms of the boundary word


def hz2st(f, ref):
    return 12.0 * np.log2(f / ref)


def load_words(p):
    return json.load(open(p, encoding="utf-8"))


def sentences(words):
    """Group words into sentences; also record clause (comma) boundaries."""
    out, cur = [], []
    for w in words:
        cur.append(w)
        t = w["w"].strip()
        if t.endswith((".", "!", "?")):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def pitch_of(snd, t0, t1):
    seg = snd.extract_part(from_time=max(0, t0 - SR_PAD),
                           to_time=min(snd.get_total_duration(), t1 + SR_PAD),
                           preserve_times=True)
    p = seg.to_pitch_ac(time_step=0.01, pitch_floor=FLOOR, max_number_of_candidates=15,
                        very_accurate=False, silence_threshold=0.03,
                        voicing_threshold=0.45, octave_cost=0.01,
                        octave_jump_cost=0.35, voiced_unvoiced_cost=0.14,
                        pitch_ceiling=CEIL)
    return seg, p


def frames(pitch, t0, t1):
    ts = np.asarray(pitch.xs())
    fs = np.asarray(pitch.selected_array["frequency"])
    m = (ts >= t0) & (ts <= t1) & (fs > FLOOR) & (fs < CEIL) & np.isfinite(fs)
    return ts[m], fs[m]


def slope_st_per_s(ts, fs, ref):
    if len(ts) < 4:
        return None
    y = hz2st(fs, ref)
    A = np.vstack([ts - ts[0], np.ones(len(ts))]).T
    m, _ = np.linalg.lstsq(A, y, rcond=None)[0]
    return float(m)


def creak_metrics(snd, t0, t1):
    """Praat-based irregularity on the final window: jitter(local) + voiced frac
    from a point process, and low-F0 fraction (< 0.75x speaker floor region)."""
    try:
        seg = snd.extract_part(from_time=t0, to_time=t1, preserve_times=True)
        pp = call(seg, "To PointProcess (periodic, cc)", FLOOR, CEIL)
        jit = call(pp, "Get jitter (local)", 0, 0, 0.0001, 0.02, 1.3)
        npts = call(pp, "Get number of points")
        return (None if (jit is None or math.isnan(jit)) else float(jit)), int(npts)
    except Exception:
        return None, 0


def syl_count(word):
    w = "".join(c for c in word.lower() if c.isalpha())
    if not w:
        return 1
    groups = 0
    prev = False
    for c in w:
        v = c in "aeiouy"
        if v and not prev:
            groups += 1
        prev = v
    if w.endswith("e") and groups > 1:
        groups -= 1
    return max(1, groups)


def analyse(wav, wordjson, label, t_max=None):
    snd = parselmouth.Sound(wav)
    words = load_words(wordjson)
    if t_max:
        words = [w for w in words if w["e"] <= t_max]
    sents = sentences(words)

    # speaker median F0 from all sentence windows only (never the whole file)
    allf = []
    for s in sents:
        _, p = pitch_of(snd, s[0]["s"], s[-1]["e"])
        _, f = frames(p, s[0]["s"], s[-1]["e"])
        allf.extend(f.tolist())
    allf = np.array(allf)
    med = float(np.median(allf))

    # per-syllable duration for non-boundary words (lengthening baseline)
    base = []
    finals = set()
    for s in sents:
        for i, w in enumerate(s):
            t = w["w"].strip()
            isb = (i == len(s) - 1) or t.endswith((",", ";", ":"))
            d = w["e"] - w["s"]
            if d <= 0:
                continue
            if isb:
                finals.add(id(w))
            else:
                base.append(d / syl_count(t))
    base_med = float(np.median(base)) if base else None

    rows = []
    decl = []
    for si, s in enumerate(sents):
        seg, p = pitch_of(snd, s[0]["s"], s[-1]["e"])
        ts, fs = frames(p, s[0]["s"], s[-1]["e"])
        d = slope_st_per_s(ts, fs, med)
        if d is not None and (s[-1]["e"] - s[0]["s"]) > 1.5:
            decl.append(d)

        for i, w in enumerate(s):
            t = w["w"].strip()
            is_sent = (i == len(s) - 1)
            is_cl = t.endswith((",", ";", ":"))
            if not (is_sent or is_cl):
                continue
            wt0, wt1 = w["s"], w["e"]
            if wt1 - wt0 < 0.06:
                continue
            wts, wfs = frames(p, wt0, wt1)
            if len(wfs) < 4:
                rows.append(dict(kind="SENT" if is_sent else "CLAUSE", word=t,
                                 t0=wt0, t1=wt1, note="unvoiced/creaked out",
                                 voiced_frac=len(wfs) / max(1, round((wt1 - wt0) / 0.01))))
                continue
            sl = slope_st_per_s(wts, wfs, med)
            # halves split by TIME, not by frame index, so creak-driven tracking
            # dropout cannot masquerade as a rise
            mid = (wt0 + wt1) / 2.0
            h1 = wfs[wts < mid]; h2 = wfs[wts >= mid]
            net = (float(hz2st(np.median(h2), np.median(h1)))
                   if len(h1) >= 2 and len(h2) >= 2 else None)
            # tracking dropout over the final 150 ms = glottalisation proxy
            tail0 = max(wt0, wt1 - 0.15)
            exp_fr = max(1, round((wt1 - tail0) / 0.01))
            got_fr = int(((wts >= tail0) & (wts <= wt1)).sum())
            tail_drop = round(1.0 - got_fr / exp_fr, 2)
            f300 = slope_st_per_s(*frames(p, max(wt0, wt1 - 0.30), wt1), med)
            end_re = float(hz2st(np.median(wfs[-max(3, len(wfs)//4):]), med))
            peak_re = float(hz2st(np.max(wfs), med))
            exc = peak_re - end_re
            jit, npts = creak_metrics(snd, max(wt0, wt1 - CREAK_WIN), wt1)
            nsyl = syl_count(t)
            leng = ((wt1 - wt0) / nsyl) / base_med if base_med else None
            # following pause
            nxt = None
            flat = [x for ss in sents for x in ss]
            k = flat.index(w)
            if k + 1 < len(flat):
                nxt = flat[k + 1]["s"] - wt1
            rows.append(dict(kind="SENT" if is_sent else "CLAUSE", word=t,
                             t0=round(wt0, 2), t1=round(wt1, 2),
                             slope_st_s=None if sl is None else round(sl, 2),
                             net_st=None if net is None else round(net, 2),
                             final300_slope_st_s=None if f300 is None else round(f300,2),
                             tail_drop_150ms=tail_drop,
                             end_re_med_st=round(end_re, 2),
                             excursion_st=round(exc, 2),
                             voiced_frac=round(len(wfs) / max(1, round((wt1 - wt0) / 0.01)), 2),
                             jitter_local=None if jit is None else round(jit, 4),
                             leng_ratio=None if leng is None else round(leng, 2),
                             pause_s=None if nxt is None else round(nxt, 2)))
    return dict(label=label, median_hz=round(med, 1), n_sent=len(sents),
                base_syl_dur=None if base_med is None else round(base_med, 3),
                declination_st_s=decl, rows=rows)


def q(vals):
    v = sorted(x for x in vals if x is not None)
    if not v:
        return None
    return dict(n=len(v), p25=round(np.percentile(v, 25), 2),
                med=round(np.percentile(v, 50), 2),
                p75=round(np.percentile(v, 75), 2),
                min=round(min(v), 2), max=round(max(v), 2),
                iqr=round(np.percentile(v, 75) - np.percentile(v, 25), 2))


if __name__ == "__main__":
    import pprint
    jobs = [("ek3_open.wav", "ek3_words.json", "ek3", None),
            ("yzv_open.wav", "yzv_words.json", "yzv", None)]
    out = {}
    for wav, wj, lab, tm in jobs:
        r = analyse(wav, wj, lab, tm)
        out[lab] = r
        print("=" * 70)
        print(lab, "median", r["median_hz"], "Hz  sentences", r["n_sent"],
              " base syl dur", r["base_syl_dur"])
        print("declination st/s :", q(r["declination_st_s"]))
        for kind in ("SENT", "CLAUSE"):
            rs = [x for x in r["rows"] if x["kind"] == kind and "net_st" in x]
            print(f"-- {kind}  n={len(rs)}")
            print("   net_st        ", q([x["net_st"] for x in rs]))
            print("   slope_st_s    ", q([x["slope_st_s"] for x in rs]))
            print("   end_re_med_st ", q([x["end_re_med_st"] for x in rs]))
            print("   excursion_st  ", q([x["excursion_st"] for x in rs]))
            print("   voiced_frac   ", q([x["voiced_frac"] for x in rs]))
            print("   jitter_local  ", q([x["jitter_local"] for x in rs]))
            print("   leng_ratio    ", q([x["leng_ratio"] for x in rs]))
            print("   final300_slope", q([x["final300_slope_st_s"] for x in rs]))
            print("   tail_drop150  ", q([x["tail_drop_150ms"] for x in rs]))
            print("   pause_s       ", q([x["pause_s"] for x in rs if (x["pause_s"] or 0) < 3]))
            fl = [x for x in rs if (x["end_re_med_st"] is not None)]
            nf = sum(1 for x in fl if x["end_re_med_st"] < -1.0)
            nr = sum(1 for x in fl if (x["net_st"] or 0) > 1.5)
            print(f"   class: low-ending {nr and ''}{nf}/{len(fl)}  rising-tail {nr}/{len(fl)}  level {len(fl)-nf-nr}/{len(fl)}")
        bad = [x for x in r["rows"] if "note" in x]
        print("   fully-devoiced/creaked boundaries:", len(bad), [b["word"] for b in bad])
    json.dump(out, open("contour_probe_out.json", "w"), indent=1)
    print("\nwrote contour_probe_out.json")
