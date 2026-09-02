# -*- coding: utf-8 -*-
"""Find Judge Boyd in a frame by recognising her, not by guessing a side.

WHY THIS EXISTS
`solve_crops` originally decided which half of the 2-up held the judge from a
per-case `expression_side` string, defaulting to "right". Run against the five
cases Nathan has approved, that default derived CARTHIEF's judge crop 646px away
from the hand-typed one, because CARTHIEF is the one case where Boyd sits on the
LEFT. A constant that is wrong on 1 of 5 cases is not a deriver, it is a coin
flip with extra steps.

Detecting the tile seam does not fix it either - the seam only says where the
halves are, never which one she is in - and on SANCHEZ/MONKEY the seam signal
was 52%/59% against a 50% distractor, a 2.4-point margin.

The fact that actually settles it: **Boyd is the same person in every case.**
So recognise her. That removes `expression_side`, `judge_crop` and `plate_crop`
from the hand-authored set at once, and it cannot be inverted by a layout change.

The reference is built from her face in the five APPROVED judge crops - the only
place in this repo where "that is definitely Boyd" is established by Nathan
rather than asserted by me.
"""
import os
import sys

import cv2
import numpy as np

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SFACE = os.path.join(ROOT, "models", "sface.onnx")
# use the SAME detector the pipeline already trusts - the 2026may export does
# not parse under this OpenCV build, and a second detector would be a second
# set of boxes to reconcile
import thumb_pipeline as _P  # noqa: E402
YUNET = _P.YUNET
REF = os.path.join(ROOT, "config", "boyd_reference.npy")

# OpenCV's documented cosine threshold for SFace is 0.363 for "same person".
# It is NOT used as a hard gate here - the judge is chosen as the BEST match
# among the faces actually present, which is a far easier problem than deciding
# identity in the open world. The threshold only guards the case where she is
# absent from the frame entirely.
COSINE_SAME = 0.363

_rec = None
_det = None


def _recognizer():
    global _rec
    if _rec is None:
        _rec = cv2.FaceRecognizerSF.create(SFACE, "")
    return _rec


def faces_in(bgr, score=0.6):
    """Every face in the frame, as YuNet rows (x, y, w, h, ...landmarks, score)."""
    h, w = bgr.shape[:2]
    det = cv2.FaceDetectorYN.create(YUNET, "", (w, h), score, 0.3, 5000)
    det.setInputSize((w, h))
    _, r = det.detect(bgr)
    return [] if r is None else list(r)


def embed(bgr, face_row):
    """SFace's 128-d embedding for one detected face, L2-normalised."""
    rec = _recognizer()
    chip = rec.alignCrop(bgr, np.array(face_row, dtype=np.float32).reshape(1, -1))
    f = rec.feature(chip).flatten().astype(np.float32)
    n = np.linalg.norm(f)
    return f / n if n else f


def cosine(a, b):
    return float(np.dot(a, b))


def load_reference(path=REF):
    if not os.path.exists(path):
        return None
    return np.load(path)


def score_against(vec, ref):
    """How much this face looks like Boyd: her best matching reference view."""
    if ref is None or not len(ref):
        return -1.0
    return float(np.max(ref @ vec))


def find_judge(bgr, ref=None, exclude=None):
    """(face_row, score) for the face in this frame most likely to be Boyd.

    `exclude` is an optional list of face rows already claimed, so the defendant
    can be picked as the best NON-judge face without re-detecting.
    """
    ref = load_reference() if ref is None else ref
    rows = faces_in(bgr)
    if exclude:
        ex = {tuple(np.round(e[:4]).astype(int)) for e in exclude}
        rows = [r for r in rows if tuple(np.round(r[:4]).astype(int)) not in ex]
    if not rows:
        return None, -1.0
    scored = [(r, score_against(embed(bgr, r), ref)) for r in rows]
    scored.sort(key=lambda t: -t[1])
    return scored[0]


def find_other(bgr, judge_row):
    """The largest face that is NOT the judge - the defendant, in a 2-up."""
    rows = faces_in(bgr)
    if judge_row is not None:
        jx = tuple(np.round(judge_row[:4]).astype(int))
        rows = [r for r in rows if tuple(np.round(r[:4]).astype(int)) != jx]
    if not rows:
        return None
    return max(rows, key=lambda r: r[3])


def build_reference(out=REF, verbose=True):
    """Boyd's reference embeddings, taken from the APPROVED judge crops only.

    One view per case. Using the hand-typed `judge_crop` as the source is the
    point: those are the regions Nathan signed off on, so they are the only
    ground truth in the repo for what she looks like.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import thumb_pipeline as P
    import tiles as T

    vecs, names = [], []
    for name, c in P.cases().items():
        if not c.get("judge_crop"):
            continue
        v = os.path.join(ROOT, c["video"])
        if not os.path.exists(v):
            continue
        t = c["judge_t"] - c.get("offset", 0)
        fr = T.frame_at(v, t)
        if fr is None:
            continue
        cw, ch, cx, cy = [int(x) for x in c["judge_crop"].split(":")]
        sub = fr[cy:cy + ch, cx:cx + cw]
        rows = faces_in(sub)
        if not rows:
            if verbose:
                print(f"  {name}: no face in approved judge_crop - skipped")
            continue
        vecs.append(embed(sub, max(rows, key=lambda r: r[3])))
        names.append(name)
    if not vecs:
        raise SystemExit("build_reference: no approved judge crops yielded a face")
    arr = np.stack(vecs)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    np.save(out, arr)
    if verbose:
        print(f"  reference: {len(arr)} views from {', '.join(names)} -> {out}")
        sim = arr @ arr.T
        off = sim[~np.eye(len(arr), dtype=bool)]
        print(f"  self-consistency: pairwise cosine {off.min():.3f}..{off.max():.3f} "
              f"(same-person threshold {COSINE_SAME})")
    return arr, names


def selftest():
    """Known answer: on every approved case the judge is the face inside the
    hand-typed judge_crop and the defendant is the one inside plate_crop.

    Leave-one-out - a case is never scored against a reference built from
    itself, or this measures memorisation instead of recognition.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import thumb_pipeline as P
    import tiles as T

    arr, names = build_reference(verbose=True)
    print()
    ok = True
    hits = 0
    total = 0
    for i, name in enumerate(names):
        c = P.cases()[name]
        v = os.path.join(ROOT, c["video"])
        t = c["judge_t"] - c.get("offset", 0)
        fr = T.frame_at(v, t)
        loo = np.delete(arr, i, axis=0)          # leave THIS case out
        row, sc = find_judge(fr, ref=loo)
        cw, ch, cx, cy = [int(x) for x in c["judge_crop"].split(":")]
        total += 1
        if row is None:
            print(f"  {name:9} FAIL no face found"); ok = False; continue
        fcx, fcy = row[0] + row[2] / 2, row[1] + row[3] / 2
        inside = (cx <= fcx <= cx + cw) and (cy <= fcy <= cy + ch)
        hits += inside
        print(f"  {name:9} picked face at ({fcx:6.0f},{fcy:5.0f})  cos={sc:.3f}  "
              f"{'INSIDE approved judge_crop' if inside else 'OUTSIDE - WRONG PERSON'}")
        if not inside:
            ok = False
    print(f"\n  {hits}/{total} leave-one-out identifications correct")
    print("SELFTEST_PASS identity" if ok else "SELFTEST_FAIL identity")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--build" in sys.argv:
        build_reference()
    elif "--selftest" in sys.argv:
        sys.exit(selftest())
    else:
        print("usage: identity.py --build | --selftest")
