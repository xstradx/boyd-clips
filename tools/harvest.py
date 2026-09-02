# -*- coding: utf-8 -*-
"""Harvest reusable assets from real courtroom footage.

His idea, and it removes a constraint rather than working around one:

    "go look at some real footage in the courtroom, take a screenshot when
     there's no defendant or no lawyer standing there, save it as the background
     ... you should have presets of a couple different backgrounds to pick from.
     Same thing with Judge Boyd. You should have like ten good reactions to pick
     from ... you always save those cutouts so you could reuse them."

Why it matters beyond convenience: with a genuinely EMPTY plate there is nothing
to hide, so the crop solver stops contorting the framing to bury the attorney and
the defendant's original position. Every previous background problem tonight -
the inpaint mush, the ghost duplicate, the blank-ceiling zoom - was a symptom of
having to hide people who were in the plate.

    python tools/harvest.py backgrounds SANCHEZ --n 6
    python tools/harvest.py reactions   SANCHEZ --n 10
"""
import os, sys, json, argparse, subprocess
import numpy as np
import cv2
from PIL import Image

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
YUNET = os.path.join(ROOT, "models", "yunet2023.onnx")
ASSETS = os.path.join(ROOT, "assets", "harvest")


def cases():
    return json.load(open(os.path.join(ROOT, "config", "cases.json"), encoding="utf-8"))


def crop_args(spec):
    w, h, x, y = [int(v) for v in spec.split(":")]
    return w, h, x, y


def grab(video, t_src, offset, crop, out):
    w, h, x, y = crop_args(crop)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t_src - offset), "-i", video,
                    "-frames:v", "1", "-vf", f"crop={w}:{h}:{x}:{y}", out],
                   check=True, capture_output=True)
    return out


def person_coverage(img_path, sess):
    from rembg import remove
    im = Image.open(img_path).convert("RGB")
    a = np.asarray(remove(im, session=sess, post_process_mask=True).split()[-1])
    return float((a > 60).mean())


def faces(img_path):
    bgr = cv2.imread(img_path)
    h, w = bgr.shape[:2]
    d = cv2.FaceDetectorYN.create(YUNET, "", (w, h), 0.6, 0.3, 5000)
    d.setInputSize((w, h))
    _, raw = d.detect(bgr)
    return [] if raw is None else list(raw)


def harvest_backgrounds(case, n, step):
    """A clean plate = the courtroom with nobody standing in it."""
    from rembg import new_session
    sess = new_session("birefnet-general", providers=["CPUExecutionProvider"])
    c = cases()[case]
    video = os.path.join(ROOT, c["video"])
    out_dir = os.path.join(ASSETS, "backgrounds", case)
    os.makedirs(out_dir, exist_ok=True)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                "-of", "default=nw=1:nk=1", video],
                               capture_output=True, text=True).stdout.strip())
    t0, t1 = c["offset"], c["offset"] + dur
    tmp = os.path.join(out_dir, "_probe.png")
    scored = []
    for t in range(int(t0), int(t1), step):
        try:
            # bg_crop, not plate_crop: the plate crop frames the DEFENDANT, so
            # harvesting a background from it yields a blown-up close-up of the
            # very person we are about to cut out and place in front of it.
            # Measured on MONKEY 2026-08-29 - the build put Grant in the frame
            # twice and Gate D missed it because the two differ in scale/pose.
            grab(video, t, c["offset"], c.get("bg_crop") or c["plate_crop"], tmp)
        except Exception:
            continue
        cov = person_coverage(tmp, sess)
        nf = len(faces(tmp))
        g = cv2.cvtColor(cv2.imread(tmp), cv2.COLOR_BGR2GRAY)
        detail = float(cv2.Laplacian(g, cv2.CV_64F).var())
        # "Empty" means nobody STANDING in the foreground. Seated gallery in the
        # background is normal courtroom and must NOT be penalised - weighting
        # faces like coverage let a 45.9%-covered frame into the top 6.
        scored.append((cov, cov, nf, detail, t))
        print(f"  t={t:5d}  coverage={cov*100:5.1f}%  faces={nf}  detail={detail:6.1f}")

    # hard filter first, then prefer the most real room texture among the empties
    empty = sorted([r for r in scored if r[1] < 0.05], key=lambda r: -r[3])
    if len(empty) < n:
        empty += sorted([r for r in scored if r[1] >= 0.05], key=lambda r: r[1])[: n - len(empty)]
    picked, spread = [], []
    for r in empty:
        if any(abs(r[4] - u) < 20 for u in spread):
            continue
        spread.append(r[4])
        picked.append(r)
        if len(picked) >= n:
            break
    keep = []
    for (s, cov, nf, detail, t) in picked:
        dst = os.path.join(out_dir, f"bg_{case}_{t}.png")
        grab(video, t, c["offset"], c["plate_crop"], dst)
        keep.append(dict(file=dst, t=t, coverage=round(cov, 4), faces=nf, detail=round(detail, 1)))
    if os.path.exists(tmp):
        os.remove(tmp)
    json.dump(keep, open(os.path.join(out_dir, "index.json"), "w"), indent=1)
    print(f"\nHARVEST_OK  {len(keep)} clean plates -> {out_dir}")
    for k in keep:
        print(f"   {os.path.basename(k['file']):28} people {k['coverage']*100:4.1f}%  faces {k['faces']}")
    return keep


def harvest_reactions(case, n, step):
    """Judge Boyd's best reactions, scored on how much her face is DOING."""
    c = cases()[case]
    video = os.path.join(ROOT, c["video"])
    out_dir = os.path.join(ASSETS, "reactions", "boyd")
    os.makedirs(out_dir, exist_ok=True)
    tmp = os.path.join(out_dir, "_probe.png")
    lo, hi = c.get("case_from", c["offset"]), c.get("case_to", c["offset"] + 400)
    scored = []
    for t in range(int(lo), int(hi), step):
        try:
            grab(video, t, c["offset"], c["judge_crop"], tmp)
        except Exception:
            continue
        fs = faces(tmp)
        if not fs:
            continue
        f = max(fs, key=lambda r: r[3])
        x, y, w, h = [max(0, int(v)) for v in f[:4]]
        img = cv2.imread(tmp)
        patch = img[y:y + h, x:x + w]
        if patch.size == 0:
            continue
        g = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
        sharp = float(cv2.Laplacian(g, cv2.CV_64F).var())
        # mouth-open proxy: vertical variance in the lower third of the face
        lower = g[int(h * 0.55):, :]
        openness = float(lower.std()) if lower.size else 0.0
        score = sharp * 0.4 + openness * 6.0
        scored.append((score, t, sharp, openness, (x, y, w, h)))
        print(f"  t={t:5d}  sharp={sharp:7.1f}  openness={openness:5.1f}  score={score:7.1f}")
    scored.sort(reverse=True)
    picked, used = [], []
    for score, t, sharp, openness, box in scored:
        if any(abs(t - u) < 6 for u in used):     # spread them out in time
            continue
        used.append(t)
        dst = os.path.join(out_dir, f"boyd_{case}_{t}.png")
        grab(video, t, c["offset"], c["judge_crop"], dst)
        picked.append(dict(file=dst, t=t, sharp=round(sharp, 1),
                           openness=round(openness, 1), score=round(score, 1)))
        if len(picked) >= n:
            break
    if os.path.exists(tmp):
        os.remove(tmp)
    idx = os.path.join(out_dir, "index.json")
    prev = json.load(open(idx)) if os.path.exists(idx) else []
    keep = {p["file"]: p for p in prev + picked}
    json.dump(list(keep.values()), open(idx, "w"), indent=1)
    print(f"\nHARVEST_OK  {len(picked)} reactions -> {out_dir}")
    return picked


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["backgrounds", "reactions"])
    ap.add_argument("case")
    ap.add_argument("--n", type=int, default=6)
    ap.add_argument("--step", type=int, default=5)
    a = ap.parse_args()
    if a.what == "backgrounds":
        harvest_backgrounds(a.case, a.n, a.step)
    else:
        harvest_reactions(a.case, a.n, a.step)
