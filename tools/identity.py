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

The reference is built from the five checked-in APPROVED Boyd cutouts - the only
stable place in this repo where "that is definitely Boyd" is established by
Nathan rather than asserted by the pipeline.  Their index stores the approved
face box, so a stray small face in a background cannot contaminate the model.
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
APPROVED_INDEX = os.path.join(
    ROOT, "assets", "harvest", "reactions", "boyd", "index.json")

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


def _approved_faces():
    """Yield (case, image, Boyd face row) from stable approved cutouts."""
    import json

    if not os.path.exists(APPROVED_INDEX):
        raise SystemExit(f"build_reference: missing approved index {APPROVED_INDEX}")
    with open(APPROVED_INDEX, encoding="utf-8") as f:
        items = json.load(f)
    for item in items:
        path = item.get("file") or ""
        if not os.path.isabs(path):
            path = os.path.join(ROOT, path)
        if not os.path.exists(path):
            path = os.path.join(os.path.dirname(APPROVED_INDEX),
                                os.path.basename(path))
        im = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if im is None:
            raise SystemExit(f"build_reference: unreadable approved cutout {path}")
        if im.ndim == 3 and im.shape[2] == 4:
            im = cv2.cvtColor(im, cv2.COLOR_BGRA2BGR)
        rows = faces_in(im)
        x, y, w, h = [float(v) for v in item["face_box"]]
        inside = [r for r in rows
                  if x <= r[0] + r[2] / 2 <= x + w
                  and y <= r[1] + r[3] / 2 <= y + h]
        if not inside:
            raise SystemExit(
                f"build_reference: approved face not detected for {item['case']}")
        yield item["case"], im, max(inside, key=lambda r: r[3])


def build_reference(out=REF, verbose=True):
    """Build Boyd embeddings from the checked-in approved face assets."""
    vecs, names = [], []
    for name, im, row in _approved_faces():
        vecs.append(embed(im, row))
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
    """Leave each approved view out, then identify it from the other four."""
    arr, names = build_reference(verbose=True)
    print()
    ok = True
    hits = 0
    total = 0
    approved = list(_approved_faces())
    for i, (name, im, expected) in enumerate(approved):
        loo = np.delete(arr, i, axis=0)          # leave THIS case out
        row, sc = find_judge(im, ref=loo)
        total += 1
        if row is None:
            print(f"  {name:9} FAIL no face found"); ok = False; continue
        picked = tuple(np.round(row[:4]).astype(int))
        want = tuple(np.round(expected[:4]).astype(int))
        match = picked == want and sc >= COSINE_SAME
        hits += match
        print(f"  {name:9} cosine={sc:.3f}  "
              f"{'APPROVED FACE' if match else 'WRONG OR BELOW THRESHOLD'}")
        if not match:
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
