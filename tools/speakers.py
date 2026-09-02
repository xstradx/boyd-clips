# -*- coding: utf-8 -*-
"""Who is talking, per word, on a two-tile split-screen short.

Nathan, 2026-08-29:

  "let's just say Judge Boyd is talking, and then the defendant starts talking.
   And their beginning of the other person's sentence is at the end of the
   sentence in the video. So, like, you kind of already hear what they say.
   Basically, you need to learn when to start the sentences"

The defect he is describing is SEGMENTATION, not animation. Cards were cut by a
character budget, so a card could hold the tail of one speaker's sentence plus
the head of the other's - measured on SANCHEZ: 7 of 78 cards straddled a
sentence end, including "life. Exactly." where "life." is Judge Boyd and
"Exactly." is the defendant. No amount of reveal trickery fixes that; the card
boundary is simply in the wrong place.

Punctuation alone is not enough (Whisper does not always punctuate an
interruption), so this measures the ACTUAL speaker from the picture:

  the top tile is the bench, the bottom tile is the defendant, both cameras are
  locked off, so whoever's mouth is moving is the one talking.

Method - deliberately no new dependency, mediapipe 1.x dropped the solutions API:
  1. detect a face box per tile on a spread of frames, take the median box
  2. mouth ROI = lower 45% of that box, central 60%
  3. per sampled frame, motion energy = mean |frame - prev| inside the ROI
  4. per word, compare the two tiles' mean energy over [start, end]

Output is one label per word: "top" | "bot" | "?" (below confidence).

    python tools/speakers.py IN.mp4 words.json OUT_words.json
"""
import sys, os, json, argparse
import numpy as np
import cv2

CASCADE = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")


def find_seam(g):
    h = g.shape[0]
    d = np.abs(np.diff(g.mean(axis=1)))
    band = slice(int(h * 0.35), int(h * 0.65))
    return int(np.argmax(d[band]) + band.start)


def face_box(frames, det):
    """Median face box across sample frames, or None."""
    boxes = []
    for f in frames:
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        r = det.detectMultiScale(g, 1.1, 5, minSize=(int(g.shape[1] * 0.08),) * 2)
        if len(r):
            boxes.append(max(r, key=lambda b: b[2] * b[3]))
    if not boxes:
        return None
    return np.median(np.array(boxes), axis=0).astype(int)


def mouth_roi(box, shape):
    x, y, w, h = box
    mx0 = x + int(w * 0.20)
    mx1 = x + int(w * 0.80)
    my0 = y + int(h * 0.55)
    my1 = min(shape[0], y + int(h * 1.00))
    return mx0, mx1, my0, my1


def energy(video, step=2):
    """Return (t[], e_top[], e_bot[], seam). Motion energy in each mouth ROI."""
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    frames, i = [], 0
    while len(frames) < 12:
        ok, f = cap.read()
        if not ok:
            break
        if i % 40 == 0:
            frames.append(f)
        i += 1
    if not frames:
        raise SystemExit("no frames")
    seam = find_seam(cv2.cvtColor(frames[0], cv2.COLOR_BGR2GRAY))
    det = cv2.CascadeClassifier(CASCADE)
    tops = [f[:seam] for f in frames]
    bots = [f[seam:] for f in frames]
    bt, bb = face_box(tops, det), face_box(bots, det)
    if bt is None or bb is None:
        raise SystemExit(f"face not found (top={bt is not None} bot={bb is not None})")
    rt = mouth_roi(bt, tops[0].shape)
    rb = mouth_roi(bb, bots[0].shape)
    print(f"  seam y={seam}   mouth ROI top x{rt[0]}-{rt[1]} y{rt[2]}-{rt[3]}   "
          f"bot x{rb[0]}-{rb[1]} y{rb[2]}-{rb[3]}")

    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    t, et, eb = [], [], []
    prev_t = prev_b = None
    i = 0
    while True:
        ok, f = cap.read()
        if not ok:
            break
        if i % step == 0:
            a = cv2.cvtColor(f[:seam][rt[2]:rt[3], rt[0]:rt[1]], cv2.COLOR_BGR2GRAY).astype(np.int16)
            b = cv2.cvtColor(f[seam:][rb[2]:rb[3], rb[0]:rb[1]], cv2.COLOR_BGR2GRAY).astype(np.int16)
            if prev_t is not None:
                t.append(i / fps)
                et.append(float(np.abs(a - prev_t).mean()))
                eb.append(float(np.abs(b - prev_b).mean()))
            prev_t, prev_b = a, b
        i += 1
    cap.release()
    return np.array(t), np.array(et), np.array(eb), seam


def label_words(words, t, et, eb, margin=1.18):
    """Per word: which tile carries more mouth motion over its span."""
    # normalise each tile to its own scale - the two cameras differ in noise,
    # gain and framing, so raw energies are not comparable.
    nt = et / (np.median(et) + 1e-6)
    nb = eb / (np.median(eb) + 1e-6)
    out = []
    for w in words:
        m = (t >= w["s"] - 0.06) & (t <= w["e"] + 0.06)
        if m.sum() < 2:
            m = (t >= w["s"] - 0.20) & (t <= w["e"] + 0.20)
        a, b = (nt[m].mean(), nb[m].mean()) if m.sum() else (0.0, 0.0)
        if a > b * margin:
            spk = "top"
        elif b > a * margin:
            spk = "bot"
        else:
            spk = "?"
        x = dict(w)
        x["spk"] = spk
        x["_e"] = (round(float(a), 3), round(float(b), 3))
        out.append(x)
    # fill unknowns from the nearest confident neighbour on either side
    for i, x in enumerate(out):
        if x["spk"] != "?":
            continue
        back = next((out[j]["spk"] for j in range(i - 1, -1, -1) if out[j]["spk"] != "?"), None)
        fwd = next((out[j]["spk"] for j in range(i + 1, len(out)) if out[j]["spk"] != "?"), None)
        x["spk"] = back if back == fwd else (back or fwd or "top")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("video"); ap.add_argument("words"); ap.add_argument("out")
    ap.add_argument("--margin", type=float, default=1.18)
    a = ap.parse_args()
    words = json.load(open(a.words))
    t, et, eb, seam = energy(a.video)
    lab = label_words(words, t, et, eb, a.margin)
    n_top = sum(1 for x in lab if x["spk"] == "top")
    turns = sum(1 for p, q in zip(lab, lab[1:]) if p["spk"] != q["spk"])
    print(f"  {len(lab)} words: {n_top} top / {len(lab)-n_top} bottom, {turns} speaker changes")
    json.dump([{k: v for k, v in x.items() if k != "_e"} for x in lab],
              open(a.out, "w"), indent=0)
    print(f"  wrote {a.out}")


SENT_END = ('.', '!', '?')


def sentences(words, max_gap=0.60):
    """Split a word list into SENTENCES.

    A sentence ends at terminal punctuation, or at a pause long enough that the
    next word cannot belong to the same breath. Everything downstream keys off
    this: a caption card may never cross a sentence boundary, because that is
    exactly the defect - "life. Exactly." held the end of the judge's sentence
    and the start of the defendant's.
    """
    out, cur = [], []
    for w in words:
        if cur and w["s"] - cur[-1]["e"] > max_gap:
            out.append(cur); cur = []
        cur.append(w)
        if w["w"].rstrip('"\u201d\')').endswith(SENT_END):
            out.append(cur); cur = []
    if cur:
        out.append(cur)
    return out


def label_sentences(words, t, et, eb, margin=1.05, max_gap=0.60):
    """One speaker per SENTENCE, decided on the whole sentence's energy.

    Per-word attribution measured 28 speaker changes in 49s, flapping every
    ~0.3s through a continuous monologue - frame differencing sees head turns,
    hands and compression noise, not just lips. A sentence is long enough for
    those to average out, and a speaker change that is not at a sentence
    boundary is not a change worth cutting a card for anyway.
    """
    nt = et / (np.median(et) + 1e-6)
    nb = eb / (np.median(eb) + 1e-6)
    sents = sentences(words, max_gap)
    out = []
    for si, s in enumerate(sents):
        m = (t >= s[0]["s"] - 0.06) & (t <= s[-1]["e"] + 0.06)
        if m.sum() < 3:
            m = (t >= s[0]["s"] - 0.25) & (t <= s[-1]["e"] + 0.25)
        a = float(nt[m].mean()) if m.sum() else 0.0
        b = float(nb[m].mean()) if m.sum() else 0.0
        spk = "top" if a > b * margin else ("bot" if b > a * margin else "?")
        for w in s:
            x = dict(w); x["spk"] = spk; x["sent"] = si
            out.append(x)
    # an unresolved sentence inherits from whichever neighbour agrees
    for i, x in enumerate(out):
        if x["spk"] != "?":
            continue
        back = next((out[j]["spk"] for j in range(i - 1, -1, -1) if out[j]["spk"] != "?"), None)
        fwd = next((out[j]["spk"] for j in range(i + 1, len(out)) if out[j]["spk"] != "?"), None)
        x["spk"] = back if back == fwd else (back or fwd or "top")
    return out, sents
