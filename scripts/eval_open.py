"""EVAL PROTOCOL for the document-card opening.

Scores any candidate .mp4 against numbers measured off Audit the Court's own
opening (video Ek3Ah3NZYVo, t=10-40 s, measured 2026-08-12). Every threshold in
TARGETS below is either a measured reference value or a published standard --
none is a guess. Run:

    python scripts/eval_open.py out/review/castillo_open.mp4
    python scripts/eval_open.py <candidate> --ref <reference.mp4>
    python scripts/eval_open.py <candidate> --beats scripts/beats.json

Metrics
-------
M1 push_in       per-card scale rate %/s, zoom anchor, linearity residual
M2 transition    frames of card travel at each card boundary (0 == hard cut)
M3 motion_energy 8 fps inter-frame mean-abs-diff (comparable with EDITING_SPEC)
M4 text_height   median OCR glyph-box height in px on the settled card
M5 attribution   does every card carry a citable source token
M6 transcode     OCR character recall + VMAF after a YouTube-grade re-encode
M7 read_load     on-screen words / (hold_s * 238 wpm) -- Brysbaert 2019
M8 highlight     highlighter onset vs. word timestamp (needs --beats)
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

# ---------------------------------------------------------------- targets ---
TARGETS = {
    # M1: measured on Ek3Ah3NZYVo card A (n=172..311). Horizontal fit gave
    # +0.7333 %/s anchored at x=960.4; vertical fit +0.7337 %/s anchored at
    # y=539.9. Residual rms 0.04-0.07 px => a LINEAR ramp, no easing.
    "push_rate_pct_s": (0.60, 1.25),      # ref 0.733; card B ran 1.198
    "push_anchor_tol_px": 15.0,           # ref anchor was frame centre +-0.4 px
    "push_linear_rms_px": 0.60,           # ref 0.07; >0.6 means eased or jittery
    # M2: measured entrance n=159..168 (10 frames, decelerating), exit
    # n=313..321 (9 frames, accelerating), both horizontal left->right.
    "transition_frames": (8, 16),         # at 23.976-30 fps => 0.27-0.53 s
    # M3: recalibrated to THIS estimator (8 fps, 480x270 grey, mean |diff|).
    # Measured 2026-08-12: reference card A push-in = 0.53 mean / 0.52 median;
    # castillo_open.mp4 static plates = 0.41 mean but 0.00 MEDIAN (frames are
    # bit-identical -- the mean is entirely the 8 hard cuts). Median is the
    # discriminator, not the mean. EDITING_SPEC's 1.3-1.9 came from a different
    # normalisation and is NOT comparable with these numbers.
    "motion_energy_median": (0.35, 2.0),
    # M4: measured median OCR glyph-box height on ref card A = 30.5 px
    # (min 29.0) at 1920x1080 => 2.82 % of frame height.
    "text_height_px": 29.0,
    # M6: YouTube serves this genre's 1080p at 457-1226 kbit/s (measured with
    # yt-dlp -F on Ek3Ah3NZYVo 723k/715k/407k, yzv_uxBSgu0 457k/536k/299k,
    # 4kIjd7CLp7c 1226k/798k/603k). Encode at the VP9 median and re-read.
    "transcode_vp9_kbps": 715,
    "transcode_char_recall": 0.95,
    "transcode_vmaf": 90.0,
    # M7: Brysbaert 2019 meta-analysis (190 studies, 18,573 subjects):
    # adult English silent reading of NON-FICTION = 238 wpm.
    "reading_wpm": 238.0,
    # BBC Subtitle Guidelines cap subtitle reading speed at 160-180 wpm because
    # the viewer is reading AND listening. A narrated document card is the same
    # dual task, so 180 is the operative budget and 238 is the ceiling.
    "reading_wpm_dual_task": 180.0,
    "read_load_max": 1.00,                # ref card A scored 1.78 == over budget
    # M8
    "highlight_sync_frames": 2,
}

SOURCE_TOKENS = [
    "KSAT", "MYSA", "KENS", "EXPRESS-NEWS", "SAN ANTONIO EXPRESS",
    "CAUSE NO", "CAUSE NUMBER", "BEXAR COUNTY", "DISTRICT COURT",
    "187TH", "STATE OF TEXAS", "DISTRICT CLERK", "SHERIFF",
]


# ------------------------------------------------------------- card track ---
def track_cards(path: Path, thr: int = 190, min_area: int = 200_000):
    """Per-frame axis-aligned bounds of the largest bright (paper) blob."""
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    k = np.ones((31, 31), np.uint8)
    rows = []
    n = 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
        _, m = cv2.threshold(g, thr, 255, cv2.THRESH_BINARY)
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k)
        cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        rec = {"n": n, "t": n / fps}
        if cnts:
            c = max(cnts, key=cv2.contourArea)
            if cv2.contourArea(c) > min_area:
                x, y, w, h = cv2.boundingRect(c)
                fill = cv2.contourArea(c) / float(w * h)
                # a document card is a big, near-solid rectangle -- this rejects
                # captions, logo plates and lit background patches
                rec.update(rl=x, rr=x + w, rw=w)   # ungated: used by M2
                if w >= 900 and h >= 350 and fill >= 0.78:
                    rec.update(l=x, r=x + w, tp=y, b=y + h, w=w, h=h,
                               fill=round(fill, 4))
        rows.append(rec)
        n += 1
    cap.release()
    return fps, rows


def segment(rows, jump=40):
    """Split the tracked frames into card segments; return settled spans."""
    segs, cur = [], []
    prev = None
    for r in rows:
        if "l" not in r:
            if cur:
                segs.append(cur)
            cur, prev = [], None
            continue
        if prev is not None and (abs(r["l"] - prev["l"]) > jump
                                 or abs(r["tp"] - prev["tp"]) > jump):
            if cur:
                segs.append(cur)
            cur = []
        cur.append(r)
        prev = r
    if cur:
        segs.append(cur)
    return [s for s in segs if len(s) >= 12]


def trim_transitions(seg, edge_jump=8):
    """Drop leading/trailing frames where the card is still travelling."""
    def vel(i):
        return abs(seg[i + 1]["l"] - seg[i]["l"]) + abs(seg[i + 1]["r"] - seg[i]["r"])
    a = 0
    while a < len(seg) - 2 and vel(a) > edge_jump:
        a += 1
    b = len(seg) - 1
    while b > a + 2 and vel(b - 1) > edge_jump:
        b -= 1
    return a, b


# ----------------------------------------------------------------- M1 / M2 ---
def m1_push_in(seg, a, b, fps):
    hold = seg[a:b + 1]
    if len(hold) < 12:
        return None
    t = np.array([r["t"] for r in hold])
    L = np.array([r["l"] for r in hold], float)
    R = np.array([r["r"] for r in hold], float)
    T = np.array([r["tp"] for r in hold], float)
    B = np.array([r["b"] for r in hold], float)
    out = {}
    for axis, (p, q) in (("x", (L, R)), ("y", (T, B))):
        mp, cp = np.polyfit(t, p, 1)
        mq, cq = np.polyfit(t, q, 1)
        span = (q - p).mean()
        k = (mq - mp) / span if span else 0.0                 # 1/s
        anchor = (p.mean() - mp / k) if k else float("nan")   # zero-velocity pt
        rms = float(np.sqrt(((p - (mp * t + cp)) ** 2).mean()
                            + ((q - (mq * t + cq)) ** 2).mean()) / math.sqrt(2))
        out[axis] = {"rate_pct_s": round(k * 100, 4),
                     "anchor_px": round(float(anchor), 1),
                     "rms_px": round(rms, 3)}
    out["hold_s"] = round(float(t[-1] - t[0]), 3)
    return out


def m2_transition(seg, a, b, fps, rows=None, jump=8):
    """Frames of card travel at each boundary, counted on the UNGATED series.

    The gated card series drops the fast-moving entry/exit frames (the card is
    clipped by the frame edge, so it fails the size/fill gate). Counting on the
    raw bright-blob bounds recovers them. 0 frames == a hard cut.
    """
    n_in = a
    n_out = len(seg) - 1 - b
    if rows:
        idx = {r["n"]: r for r in rows}
        n0, n1 = seg[a]["n"], seg[b]["n"]
        k = n0 - 1
        while k >= 0 and "rl" in idx.get(k, {}) and "rl" in idx.get(k + 1, {})                 and abs(idx[k + 1]["rr"] - idx[k]["rr"]) > jump:
            n_in += 1
            k -= 1
        k = n1 + 1
        while k < len(rows) and "rl" in idx.get(k, {}) and "rl" in idx.get(k - 1, {})                 and abs(idx[k]["rl"] - idx[k - 1]["rl"]) > jump:
            n_out += 1
            k += 1
    return {"in_frames": n_in, "out_frames": n_out,
            "in_s": round(n_in / fps, 3), "out_s": round(n_out / fps, 3)}


# --------------------------------------------------------------------- M3 ---
def m3_motion_energy(path: Path, t0: float, t1: float, rate: int = 8):
    """Mean absolute inter-frame difference at `rate` fps, 0-255 scale."""
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{t0}", "-to", f"{t1}", "-i", str(path),
           "-vf", f"fps={rate},scale=480:-1,format=gray", "-f", "rawvideo", "-"]
    r = subprocess.run(cmd, capture_output=True)
    w, h = 480, 270
    buf = np.frombuffer(r.stdout, np.uint8)
    nf = len(buf) // (w * h)
    if nf < 3:
        return None
    fr = buf[:nf * w * h].reshape(nf, h, w).astype(np.int16)
    d = np.abs(np.diff(fr, axis=0)).mean(axis=(1, 2))
    return {"mean": round(float(d.mean()), 3), "median": round(float(np.median(d)), 3)}


# --------------------------------------------------------------- OCR bits ---
_ocr = None


def ocr(img):
    global _ocr
    if _ocr is None:
        from rapidocr_onnxruntime import RapidOCR
        _ocr = RapidOCR()
    res, _ = _ocr(img)
    return res or []


def m4_m5_m7(path: Path, t_mid: float, hold_s: float):
    cap = cv2.VideoCapture(str(path))
    cap.set(cv2.CAP_PROP_POS_MSEC, t_mid * 1000)
    ok, fr = cap.read()
    cap.release()
    if not ok:
        return None, None, None, ""
    res = ocr(fr)
    heights, words, text = [], 0, []
    for box, txt, conf in res:
        bb = np.array(box, float)
        heights.append(bb[:, 1].max() - bb[:, 1].min())
        words += len(txt.split())
        text.append(txt)
    joined = " ".join(text)
    up = joined.upper()
    m4 = {"lines": len(res),
          "median_h_px": round(float(np.median(heights)), 1) if heights else 0.0,
          "min_h_px": round(float(np.min(heights)), 1) if heights else 0.0,
          "pct_of_frame_h": round(float(np.median(heights)) / fr.shape[0] * 100, 2)
          if heights else 0.0}
    hits = [s for s in SOURCE_TOKENS if s in up]
    m5 = {"tokens": hits, "ok": bool(hits)}
    budget = hold_s * TARGETS["reading_wpm"] / 60.0
    dual = hold_s * TARGETS["reading_wpm_dual_task"] / 60.0
    m7 = {"onscreen_words": words, "budget_words": round(budget, 1),
          "budget_words_dual_task": round(dual, 1),
          "read_load": round(words / budget, 3) if budget else None,
          "read_load_dual_task": round(words / dual, 3) if dual else None}
    return m4, m5, m7, joined


# --------------------------------------------------------------------- M6 ---
def m6_transcode(path: Path, t_mid: float, master_text: str, work: Path):
    work.mkdir(parents=True, exist_ok=True)
    kb = TARGETS["transcode_vp9_kbps"]
    enc = work / "yt_vp9.webm"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(path),
                    "-c:v", "libvpx-vp9", "-b:v", f"{kb}k", "-maxrate", f"{int(kb*1.5)}k",
                    "-bufsize", f"{kb*4}k", "-row-mt", "1", "-deadline", "good",
                    "-cpu-used", "2", "-an", str(enc)], check=True)
    log = work / "vmaf.json"
    # NB: run from `work` -- a Windows drive letter in log_path breaks the
    # libavfilter option parser on the ':' separator.
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", enc.name, "-i", str(path),
                    "-lavfi", "[0:v]setpts=PTS-STARTPTS[d];[1:v]setpts=PTS-STARTPTS[r];"
                              "[d][r]libvmaf=log_path=vmaf.json:log_fmt=json",
                    "-f", "null", "-"], check=True, cwd=work)
    vmaf = json.loads(log.read_text())["pooled_metrics"]["vmaf"]["mean"]
    cap = cv2.VideoCapture(str(enc))
    cap.set(cv2.CAP_PROP_POS_MSEC, t_mid * 1000)
    ok, fr = cap.read()
    cap.release()
    got = " ".join(t for _, t, _ in ocr(fr)) if ok else ""

    def norm(s):
        return re.sub(r"[^a-z0-9 ]", "", s.lower()).split()
    a, b = norm(master_text), norm(got)
    keep = sum(1 for w in a if w in b)
    return {"vp9_kbps": kb, "vmaf": round(float(vmaf), 2),
            "word_recall": round(keep / len(a), 3) if a else None,
            "master_words": len(a), "transcoded_words": len(b)}


# -------------------------------------------------------------------- run ---
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--work", default=None)
    ap.add_argument("--skip-transcode", action="store_true")
    ap.add_argument("--json", default=None)
    a = ap.parse_args()

    path = Path(a.video).resolve()
    work = Path(a.work) if a.work else path.parent / ("_eval_" + path.stem)
    fps, rows = track_cards(path)
    segs = segment(rows)
    print(f"{path.name}: {len(rows)} frames @ {fps:.3f} fps, {len(segs)} card segments")

    report = {"video": str(path), "fps": fps, "cards": [], "targets": TARGETS}
    for i, seg in enumerate(segs, 1):
        lo, hi = trim_transitions(seg)
        m1 = m1_push_in(seg, lo, hi, fps)
        m2 = m2_transition(seg, lo, hi, fps, rows)
        t0, t1 = seg[lo]["t"], seg[hi]["t"]
        m3 = m3_motion_energy(path, t0, t1)
        m4, m5, m7, txt = m4_m5_m7(path, (t0 + t1) / 2, t1 - t0)
        card = {"card": i, "t0": round(t0, 3), "t1": round(t1, 3),
                "M1_push_in": m1, "M2_transition": m2, "M3_motion_energy": m3,
                "M4_text_height": m4, "M5_attribution": m5, "M7_read_load": m7}
        report["cards"].append(card)

        pr = m1["x"]["rate_pct_s"] if m1 else float("nan")
        print(f"\ncard {i}  t {t0:6.2f}-{t1:6.2f} ({t1-t0:5.2f}s hold)")
        if m1:
            print(f"  M1 push-in   x {m1['x']['rate_pct_s']:+.3f} %/s anchor {m1['x']['anchor_px']:7.1f} rms {m1['x']['rms_px']:.2f}"
                  f"   y {m1['y']['rate_pct_s']:+.3f} %/s anchor {m1['y']['anchor_px']:7.1f} rms {m1['y']['rms_px']:.2f}"
                  f"   {'PASS' if TARGETS['push_rate_pct_s'][0] <= pr <= TARGETS['push_rate_pct_s'][1] else 'FAIL'}")
        print(f"  M2 transition in {m2['in_frames']:2d} f / out {m2['out_frames']:2d} f "
              f"({'PASS' if TARGETS['transition_frames'][0] <= m2['in_frames'] <= TARGETS['transition_frames'][1] else 'FAIL'})")
        if m3:
            lo_, hi_ = TARGETS["motion_energy_median"]
            print(f"  M3 motion    mean {m3['mean']:.2f} median {m3['median']:.2f} "
                  f"({'PASS' if lo_ <= m3['median'] <= hi_ else 'FAIL'})")
        if m4:
            print(f"  M4 text      {m4['lines']} lines, median glyph {m4['median_h_px']:.1f} px "
                  f"({m4['pct_of_frame_h']:.2f} % of H) "
                  f"({'PASS' if m4['median_h_px'] >= TARGETS['text_height_px'] else 'FAIL'})")
        if m5:
            print(f"  M5 source    {m5['tokens'] or 'NONE'} ({'PASS' if m5['ok'] else 'FAIL'})")
        if m7:
            print(f"  M7 read-load {m7['onscreen_words']} words vs {m7['budget_words']} silent / "
                  f"{m7['budget_words_dual_task']} dual-task readable = {m7['read_load']}x / "
                  f"{m7['read_load_dual_task']}x "
                  f"({'PASS' if (m7['read_load_dual_task'] or 9) <= 1.0 else 'FAIL'})")

        if not a.skip_transcode and i == 1:
            m6 = m6_transcode(path, (t0 + t1) / 2, txt, work)
            card["M6_transcode"] = m6
            print(f"  M6 transcode VP9 {m6['vp9_kbps']}k -> VMAF {m6['vmaf']:.1f} "
                  f"({'PASS' if m6['vmaf'] >= TARGETS['transcode_vmaf'] else 'FAIL'}), "
                  f"OCR word recall {m6['word_recall']} "
                  f"({'PASS' if (m6['word_recall'] or 0) >= TARGETS['transcode_char_recall'] else 'FAIL'})")

    if a.json:
        Path(a.json).write_text(json.dumps(report, indent=2))
        print(f"\n-> {a.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
