#!/usr/bin/env python
"""
thumb_eval.py -- runnable scorer for Boyd Clips thumbnails.

Scores a candidate 16:9 thumbnail against a MEASURED baseline built from the two
reference corpora already on disk:

  research/reference/courtroomtime/thumbs/  25 imgs, SAME Judge Boyd docket,
      filename-prefixed top_/bot_ = winners (204k-891k views) vs losers (388-1700 views).
      This is a winners-vs-losers control on ONE channel: same creator, same
      audience, same niche, so any metric that separates the two groups is a
      property of the thumbnail and not of the channel.
  research/reference/competitor/thumbs/     12 Audit the Court imgs (42k-1.2M views).

Everything here is measured, not asserted. Run --baseline to (re)build the
baseline json, then --score <img> to gate a candidate.

Dependencies, all already installed and all commercial-use OK:
  opencv-python 4.14.0.94        Apache-2.0
  rapidocr_onnxruntime 1.2.3     Apache-2.0  (bundles PP-OCRv3 det/rec/cls ONNX)
  onnxruntime 1.28.0             MIT
  numpy 2.5.2, scipy 1.18.0

Spec source, fetched 2026-08-23 from https://support.google.com/youtube/answer/72431 :
  16:9, JPG or PNG, min width 640px, recommended 3840x2160,
  max 2 MB on mobile / 50 MB on desktop.  We gate on the 2 MB mobile limit.

Usage:
  python scripts/thumb_eval.py --baseline
  python scripts/thumb_eval.py --summary
  python scripts/thumb_eval.py --score path/to/candidate.jpg
  python scripts/thumb_eval.py --score "out/*.jpg" --json
"""
import os, sys, json, glob, math, argparse
import numpy as np, cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CT   = os.path.join(ROOT, "research", "reference", "courtroomtime", "thumbs")
AU   = os.path.join(ROOT, "research", "reference", "competitor", "thumbs")
REFS = os.path.join(ROOT, "research", "reference", "thumb_baseline.json")

_ENG = None
def ocr_engine():
    global _ENG
    if _ENG is None:
        from rapidocr_onnxruntime import RapidOCR
        _ENG = RapidOCR()
    return _ENG

_CASC = None
def cascades():
    global _CASC
    if _CASC is None:
        _CASC = [cv2.CascadeClassifier(cv2.data.haarcascades + n) for n in
                 ("haarcascade_frontalface_alt2.xml", "haarcascade_profileface.xml")]
    return _CASC

# ---------------------------------------------------------------- primitives
def colorfulness(bgr):
    """Hasler & Suesstrunk 2003, 'Measuring colourfulness in natural images',
    Proc. SPIE 5007 pp.87-95.  M = sqrt(std_rg^2+std_yb^2) + 0.3*sqrt(mu_rg^2+mu_yb^2)"""
    B, G, R = [x.astype(np.float64) for x in cv2.split(bgr)]
    rg = R - G
    yb = 0.5 * (R + G) - B
    return math.sqrt(rg.std()**2 + yb.std()**2) + 0.3 * math.sqrt(rg.mean()**2 + yb.mean()**2)

def _srgb_lin(c):
    c = c / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)

def rel_luminance(bgr):
    """WCAG 2.2 relative luminance.  https://www.w3.org/TR/WCAG22/#dfn-relative-luminance"""
    b, g, r = [_srgb_lin(bgr[..., i].astype(np.float64)) for i in (0, 1, 2)]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b

def _iou(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0, min(ax+aw, bx+bw) - max(ax, bx))
    iy = max(0, min(ay+ah, by+bh) - max(ay, by))
    i = ix * iy
    return i / float(aw*ah + bw*bh - i + 1e-9)

def _ov(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return (max(0, min(ax+aw, bx+bw) - max(ax, bx)) *
            max(0, min(ay+ah, by+bh) - max(ay, by)))

def detect_faces(gray):
    out = []
    for c in cascades():
        for (x, y, w, h) in c.detectMultiScale(gray, 1.08, 5,
                                               minSize=(int(gray.shape[0]*0.06),)*2):
            out.append((int(x), int(y), int(w), int(h)))
    out.sort(key=lambda b: -b[2]*b[3])
    keep = []
    for b in out:
        if all(_iou(b, k) < 0.30 for k in keep):
            keep.append(b)
    return keep

def ocr_boxes(bgr):
    """Return [{'box':[x,y,w,h],'txt':..,'conf':..}] via PP-OCRv3 (rapidocr_onnxruntime)."""
    ok, buf = cv2.imencode(".png", bgr)
    tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "._eval_tmp.png")
    with open(tmp, "wb") as fh:
        fh.write(buf.tobytes())
    try:
        res, _ = ocr_engine()(tmp)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    out = []
    for it in (res or []):
        p = np.array(it[0], dtype=np.float64)
        x0, y0, x1, y1 = p[:, 0].min(), p[:, 1].min(), p[:, 0].max(), p[:, 1].max()
        out.append({"box": [int(x0), int(y0), int(x1-x0), int(y1-y0)],
                    "txt": it[1], "conf": round(float(it[2]), 2)})
    return out

def vertical_seams(gray, z=6.0):
    """Hard panel joins: columns whose mean |dI/dx| sits >z sigma above the frame mean."""
    g = gray.astype(np.float64)
    col = np.abs(np.diff(g, axis=1)).mean(axis=0)
    zz = (col - col.mean()) / (col.std() + 1e-9)
    W = gray.shape[1]
    pk = [(i+1)/W for i in range(int(W*0.12), int(W*0.88)) if zz[i] > z]
    merged = []
    for p in pk:
        if merged and p - merged[-1][-1] < 0.01:
            merged[-1].append(p)
        else:
            merged.append([p])
    return [round(float(np.mean(c)), 3) for c in merged], round(float(zz.max()), 1)

# ---------------------------------------------------------------- measurement
def measure(path):
    bgr0 = cv2.imread(path, cv2.IMREAD_COLOR)
    if bgr0 is None:
        raise SystemExit("cannot read " + path)
    h0, w0 = bgr0.shape[:2]
    bgr = bgr0 if (w0, h0) == (1280, 720) else cv2.resize(bgr0, (1280, 720),
                                                          interpolation=cv2.INTER_AREA)
    H, W = 720, 1280
    hsv  = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    y    = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb)[:, :, 0].astype(np.float64)
    L    = rel_luminance(bgr)

    m = {"path": path, "src_w": w0, "src_h": h0,
         "bytes": os.path.getsize(path), "ext": os.path.splitext(path)[1].lower()}
    m["sat_mean"]      = round(float(hsv[:, :, 1].mean()/255), 3)
    m["val_mean"]      = round(float(hsv[:, :, 2].mean()/255), 3)
    m["rms_contrast"]  = round(float(y.std()/255), 3)
    m["clip_hi"]       = round(float((y >= 250).mean()), 4)
    m["clip_lo"]       = round(float((y <= 5).mean()), 4)
    m["colorfulness"]  = round(colorfulness(bgr), 1)
    m["global_detail"] = round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 1)
    m["seams"], m["seam_zmax"] = vertical_seams(gray)

    faces = detect_faces(gray)
    m["faces"]   = faces
    m["n_faces"] = len(faces)
    hs = sorted((fh for _, _, _, fh in faces), reverse=True)
    m["face_max_h_frac"] = round((hs[0]/H) if hs else 0.0, 3)
    m["face_2nd_h_frac"] = round((hs[1]/H) if len(hs) > 1 else 0.0, 3)

    tb = ocr_boxes(bgr)
    m["text"]            = tb
    m["n_text_lines"]    = len(tb)
    m["text_area_frac"]  = round(sum(b["box"][2]*b["box"][3] for b in tb)/(W*H), 4)
    m["text_max_h_frac"] = round(max([b["box"][3] for b in tb], default=0)/H, 3)
    m["text_med_h_frac"] = (round(float(np.median([b["box"][3] for b in tb]))/H, 3)
                            if tb else 0.0)
    ta = sum(b["box"][2]*b["box"][3] for b in tb)
    tf = sum(_ov(tuple(b["box"]), f) for b in tb for f in faces)
    m["text_on_face_frac"] = round(tf/(ta+1e-9), 3)
    if tb:
        xs = [b["box"][0] for b in tb]
        ys = [b["box"][1] for b in tb]
        xe = [b["box"][0]+b["box"][2] for b in tb]
        ye = [b["box"][1]+b["box"][3] for b in tb]
        m["text_cx"] = round(((min(xs)+max(xe))/2)/W, 3)
        m["text_cy"] = round(((min(ys)+max(ye))/2)/H, 3)
    else:
        m["text_cx"] = m["text_cy"] = None

    # WCAG contrast of glyph vs its own local backdrop, per text line (Otsu split)
    wc = []
    for b in tb:
        x, yy, w, h = b["box"]
        x = max(0, x); yy = max(0, yy); w = min(w, W-x); h = min(h, H-yy)
        if w < 8 or h < 8:
            continue
        Lr = L[yy:yy+h, x:x+w]
        g8 = cv2.normalize(gray[yy:yy+h, x:x+w], None, 0, 255,
                           cv2.NORM_MINMAX).astype(np.uint8)
        _, msk = cv2.threshold(g8, 0, 255, cv2.THRESH_BINARY+cv2.THRESH_OTSU)
        fg = msk > 0
        if fg.sum() < 10 or (~fg).sum() < 10:
            continue
        a, bq = float(np.median(Lr[fg])), float(np.median(Lr[~fg]))
        wc.append((max(a, bq)+0.05)/(min(a, bq)+0.05))
    m["wcag_min"] = round(min(wc), 1) if wc else None
    m["wcag_med"] = round(float(np.median(wc)), 1) if wc else None

    # FEED-SIZE TEST: 210x118 is the desktop suggested-column card.  Downscale with
    # area averaging (what the browser does), blow back up nearest-neighbour so the
    # OCR sees exactly the information that survived, and re-detect.
    small = cv2.resize(bgr, (210, 118), interpolation=cv2.INTER_AREA)
    up    = cv2.resize(small, (1280, 720), interpolation=cv2.INTER_NEAREST)
    t210  = ocr_boxes(up)
    m["n_text_lines_210"] = len(t210)
    m["ocr_survival_210"] = round(len(t210)/max(1, len(tb)), 2)
    # Line-count survival conflates "a small decorative line dropped" with "the
    # headline is unreadable".  The gate that matters is whether the LARGEST line
    # at full res is still detected in the same place at card size.
    m["primary_survives_210"] = 0
    if tb:
        big = max(tb, key=lambda b: b["box"][3])["box"]
        for b in t210:
            if _ov(tuple(big), tuple(b["box"])) / float(big[2]*big[3] + 1e-9) >= 0.35:
                m["primary_survives_210"] = 1
                break

    ymask = (hsv[:, :, 0] >= 22) & (hsv[:, :, 0] <= 34) & (hsv[:, :, 1] >= 140) & (hsv[:, :, 2] >= 180)
    rmask = ((hsv[:, :, 0] <= 6) | (hsv[:, :, 0] >= 174)) & (hsv[:, :, 1] >= 200) & (hsv[:, :, 2] >= 170)
    m["yellow_frac"] = round(float(ymask.mean()), 4)
    m["red_frac"]    = round(float(rmask.mean()), 4)
    return m

# ---------------------------------------------------------------- baseline
def build_baseline():
    out = {}
    for f in sorted(glob.glob(os.path.join(CT, "*.jpg")) + glob.glob(os.path.join(AU, "*.jpg"))):
        b = os.path.basename(f)
        g = "CT_TOP" if b.startswith("top_") else "CT_BOT" if b.startswith("bot_") else "AUDIT"
        m = measure(f)
        m["grp"] = g
        out[b] = m
        print(".", end="", flush=True)
    print()
    with open(REFS, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)
    print("wrote", REFS, len(out))
    summarise(out)
    return out

def summarise(d):
    import statistics as st
    from scipy.stats import mannwhitneyu
    keys = ["sat_mean", "val_mean", "rms_contrast", "clip_hi", "colorfulness",
            "global_detail", "n_faces", "face_max_h_frac", "face_2nd_h_frac",
            "n_text_lines", "text_area_frac", "text_max_h_frac", "text_med_h_frac",
            "text_on_face_frac", "text_cy", "text_cx", "wcag_min", "yellow_frac", "primary_survives_210",
            "red_frac", "ocr_survival_210", "seam_zmax"]
    grps = ["CT_TOP", "CT_BOT", "AUDIT"]
    print("%-20s" % "metric" + "".join("%18s" % g for g in grps) + "%9s%8s" % ("AUC", "p"))
    print("-" * (20 + 18*3 + 17))
    for k in keys:
        row = "%-20s" % k
        vv = {}
        for g in grps:
            v = [x[k] for x in d.values() if x["grp"] == g and x.get(k) is not None]
            vv[g] = v
            row += "%18s" % ("%.3f | %.3f" % (st.median(v), float(np.mean(v))) if v else "-")
        try:
            a, b = np.array(vv["CT_TOP"], float), np.array(vv["CT_BOT"], float)
            u, p = mannwhitneyu(a, b, alternative="two-sided")
            row += "%9.2f%8.3f" % (u/(len(a)*len(b)), p)
        except Exception:
            row += "%9s%8s" % ("-", "-")
        print(row)
    print("\nmedian | mean per group.  AUC = P(a random CT_TOP scores above a random CT_BOT);"
          "\n0.50 = no signal, >0.5 = winners score higher, <0.5 = winners score LOWER.")

# ---------------------------------------------------------------- gates
# Bands are the MEASURED distribution of the 37 reference images (see --summary).
HARD = [
    ("text_on_face_frac", lambda v, m: v is not None and v <= 0.02,
     "no glyph may sit on a detected face. corpus median 0.000 in all three groups; "
     "worst single reference 0.08. our shipped 1_LONGFORM_thumbnail scored 0.12 and "
     "Nathan called it horrible. this is his complaint expressed as a number."),
    ("primary_survives_210", lambda v, m: not (v == 0 and m.get("ocr_survival_210", 1) < 0.5),
     "feed-size legibility, gated as a conjunction: fail only when the LARGEST line is "
     "gone AND fewer than half the lines survive the downscale to the 210x118 "
     "suggested-column card. calibration on the labelled corpus: this fires on 1 of 15 "
     "winners and 1 of 10 losers, and on 1_LONGFORM_thumbnail (primary gone, 0.33 "
     "survival). two stricter versions were tried and discarded because they were wrong, "
     "not strict: 'all lines survive' rejected 8 of 15 winners, 'primary line survives' "
     "rejected 4 of 15. PP-OCRv3 on a 210px card is a CONSERVATIVE proxy for human "
     "reading, with a measured 27% false-negative rate on known winners - so it is only "
     "trustworthy as a floor, never as a target."),
    ("text_max_h_frac", lambda v, m: v is not None and v >= 0.107,
     "largest text line >= 0.107 of frame height. that is the AUDIT median and all 12 "
     "Audit thumbs clear it. rejected attempt (a) ran a single line at 0.060."),
    ("face_max_h_frac", lambda v, m: v is not None and v >= 0.280,
     "hero face >= 0.280 H. CT_BOT (losers) mean 0.243, CT_TOP (winners) mean 0.360, "
     "AUDIT mean 0.358. under 0.28 is measurably the losing band."),
    ("bytes", lambda v, m: v < 2_000_000,
     "YouTube mobile custom-thumbnail cap is 2 MB (support.google.com/youtube/answer/72431, "
     "fetched 2026-08-23). desktop allows 50 MB; gate on the tighter one."),
    ("_geom", lambda v, m: m["src_w"]*9 == m["src_h"]*16 and m["src_w"] >= 1280
     and m["ext"] in (".jpg", ".jpeg", ".png"),
     "16:9 exactly, >=1280 wide, JPG or PNG."),
]

# (key, lo, hi, weight, note) - 1.0 inside the band, linear falloff over half the band width
SOFT = [
    ("sat_mean",        0.38,  0.55,  12,
     "CT_TOP mean 0.498 vs CT_BOT 0.558, AUC 0.27 p=0.056 -> HIGHER saturation tracks "
     "LOSING on this docket. the old repo note that pushed us toward 0.546 read winners "
     "only, with no control group."),
    ("val_mean",        0.50,  0.66,  10,
     "CT_TOP 0.512 vs CT_BOT 0.481, AUC 0.71 p=0.085. brighter wins."),
    ("text_max_h_frac", 0.14,  0.22,  14,
     "CT_TOP 0.198 vs CT_BOT 0.168, AUC 0.68 p=0.134. AUDIT 0.108 is the floor, not the target."),
    ("n_faces",         2,     4,     12,
     "CT_TOP median 2, 13 of 15 winners carry >=2 faces. judge and defendant both visible."),
    ("face_max_h_frac", 0.30,  0.48,  12,
     "CT_TOP mean 0.360, AUDIT mean 0.358, CT_BOT 0.243."),
    ("wcag_min",        4.5,   21.0,  10,
     "worst-line glyph/backdrop contrast ratio. CT_TOP median 4.9, AUDIT median 15.4."),
    ("clip_hi",         0.0,   0.035,  8,
     "CT_TOP mean 0.022. our previous grade ran 0.063 - nearly 3x the winners."),
    ("red_frac",        0.015, 0.060,  8,
     "CT_TOP 0.044 vs CT_BOT 0.030, AUC 0.65. the red arrow / ring / bar."),
    ("yellow_frac",     0.020, 0.100,  6,
     "MEASURED CONTRADICTION: AUDIT 0.018, courtroomtime 0.086-0.099. the band spans both "
     "houses on purpose - pick a side deliberately, do not land in the middle by accident."),
    ("primary_survives_210", 1, 1,     8,
     "1 = the biggest line still reads on a 210x118 card. AUDIT scores 12/12, CT_TOP "
     "11/15. conservative proxy - see the HARD note."),
    ("rms_contrast",    0.26,  0.34,   8,
     "all three groups sit 0.271-0.299; this one does not discriminate, it only catches blowouts."),
]

def band_score(v, lo, hi):
    if v is None:
        return 0.0
    if lo <= v <= hi:
        return 1.0
    span = (hi - lo) * 0.5 + 1e-9
    d = (lo - v) if v < lo else (v - hi)
    return max(0.0, 1.0 - d/span)

def score(path, verbose=True):
    m = measure(path)
    fails = []
    for k, test, why in HARD:
        v = m.get(k)
        if not test(v, m):
            fails.append((k, v, why))
    pts = tot = 0.0
    detail = []
    for k, lo, hi, w, note in SOFT:
        s = band_score(m.get(k), lo, hi)
        pts += s*w
        tot += w
        detail.append((k, m.get(k), lo, hi, round(s, 2), w))
    m["_hard_fails"] = [f[0] for f in fails]
    m["_score"] = round(100*pts/tot, 1)
    m["_verdict"] = "REJECT" if fails else ("SHIP" if m["_score"] >= 75 else "WEAK")
    if verbose:
        print("=" * 80)
        print("%s   %dx%d  %.0f KB" % (os.path.basename(path), m["src_w"], m["src_h"],
                                       m["bytes"]/1024))
        print("VERDICT: %s     soft score %.1f / 100" % (m["_verdict"], m["_score"]))
        if fails:
            print("-- HARD FAILS")
            for k, v, why in fails:
                print("   %-20s = %-9s %s" % (k, v, why))
        print("-- soft bands")
        for k, v, lo, hi, s, w in detail:
            flag = "  " if s == 1.0 else ("!!" if s < 0.4 else " ~")
            print("%s %-18s %-9s target[%s .. %s]  s=%.2f  w=%d" % (flag, k, v, lo, hi, s, w))
        print("-- context  text_cy=%s text_cx=%s n_text=%s survival210=%s seams=%s" %
              (m.get("text_cy"), m.get("text_cx"), m.get("n_text_lines"),
               m.get("ocr_survival_210"), m.get("seams")))
        print("   OCR read:", [t["txt"] for t in m["text"]])
    return m

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", action="store_true", help="rebuild the reference baseline json")
    ap.add_argument("--summary", action="store_true", help="print the baseline table")
    ap.add_argument("--score", nargs="*", default=[])
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.baseline:
        build_baseline()
        return
    if a.summary:
        with open(REFS, encoding="utf-8") as fh:
            summarise(json.load(fh))
        return
    outs = []
    for p in a.score:
        for f in (sorted(glob.glob(p)) or [p]):
            outs.append(score(f, verbose=not a.json))
    if a.json:
        for o in outs:
            o.pop("faces", None)
        print(json.dumps(outs, indent=1, ensure_ascii=False))

if __name__ == "__main__":
    main()
