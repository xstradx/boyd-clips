#!/usr/bin/env python
"""
thumb_frames.py -- measured frame scout for thumbnail hero selection.

The thumbnail builder needs the single best frame of each participant, not a
frame someone eyeballed.  This walks a time window of the source Zoom-grid clip,
crops each participant tile, and scores every sampled frame on things that can be
counted.  It prints a ranked table and writes the top N crops to disk so the
builder can drop them straight in.

Scores per frame, per tile:
  face_h_frac   detected face height / tile height           (bigger = better hero)
  sharp         variance of Laplacian over the face box      (rejects motion blur)
  eyes          Haar eye detections inside the face box      (2 = not mid-blink)
  mouth_open    vertical gradient energy in the lower third of the face box,
                normalised by the face box - a talking/shouting proxy
  exposure      median luminance of the face box, 0.35-0.65 is usable

Tile geometry for work/2XkPnvstmRQ/2XkPnvstmRQ_h_5915_5895-7108.mp4 (1280x720,
30fps, first frame = 5895.0s on the parent stream clock):
  defendant+attorney  crop 628x344 @ (6,6)     Zoom label burned bottom-left
  Judge Boyd          crop 468x344 @ (726,6)   Zoom label burned bottom-left
The bottom 30px of each tile is dropped to remove the burned-in Zoom name label.

Usage:
  python scripts/thumb_frames.py --src <mp4> --tile boyd --start 6239 --end 6302 --step 0.5
  python scripts/thumb_frames.py --src <mp4> --tile def  --start 6729 --end 6737 --step 0.25 --out work/heroes
"""
import os, sys, json, argparse, subprocess, tempfile
import numpy as np, cv2

CLOCK0 = 5895.0          # parent-stream time of this file's first frame
TILES = {
    "def":  {"x": 6,   "y": 6, "w": 628, "h": 344, "label_h": 30},
    "boyd": {"x": 726, "y": 6, "w": 468, "h": 344, "label_h": 30},
}
FACE_C = None
EYE_C = None

def cascades():
    global FACE_C, EYE_C
    if FACE_C is None:
        FACE_C = [cv2.CascadeClassifier(cv2.data.haarcascades + n) for n in
                  ("haarcascade_frontalface_alt2.xml", "haarcascade_profileface.xml")]
        EYE_C = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye.xml")
    return FACE_C, EYE_C

def grab(src, t_abs, tile):
    """Pull one frame at parent-clock t_abs and return the cropped tile as BGR."""
    off = t_abs - CLOCK0
    T = TILES[tile]
    fd, tmp = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    cmd = ["ffmpeg", "-nostdin", "-loglevel", "error", "-ss", "%.3f" % off,
           "-i", src, "-frames:v", "1",
           "-vf", "crop=%d:%d:%d:%d" % (T["w"], T["h"] - T["label_h"], T["x"], T["y"]),
           "-y", tmp]
    subprocess.run(cmd, check=True)
    img = cv2.imread(tmp)
    os.remove(tmp)
    return img

def score_tile(img):
    faces_c, eye_c = cascades()
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    H, W = g.shape
    boxes = []
    for c in faces_c:
        for b in c.detectMultiScale(g, 1.06, 5, minSize=(int(H*0.10),)*2):
            boxes.append(tuple(int(v) for v in b))
    if not boxes:
        return None
    x, y, w, h = max(boxes, key=lambda b: b[2]*b[3])
    fg = g[y:y+h, x:x+w].astype(np.float64)
    if fg.size < 100:
        return None
    eyes = eye_c.detectMultiScale(g[y:y+int(h*0.6), x:x+w], 1.06, 6)
    lower = fg[int(h*0.60):, :]
    mouth = float(np.abs(np.diff(lower, axis=0)).mean()) if lower.size else 0.0
    return {
        "face_box": [x, y, w, h],
        "face_h_frac": round(h / H, 3),
        "sharp": round(float(cv2.Laplacian(fg, cv2.CV_64F).var()), 1),
        "eyes": int(len(eyes)),
        "mouth_open": round(mouth, 2),
        "exposure": round(float(np.median(fg)) / 255, 3),
        "tile_wh": [W, H],
    }

def rank(rows):
    """Composite: hero size and sharpness dominate, blink is a hard penalty."""
    if not rows:
        return rows
    sm = max(r["sharp"] for r in rows) or 1.0
    mm = max(r["mouth_open"] for r in rows) or 1.0
    for r in rows:
        exp_ok = 1.0 if 0.30 <= r["exposure"] <= 0.70 else 0.4
        r["rank"] = round(
            0.40 * min(1.0, r["face_h_frac"] / 0.55) +
            0.25 * (r["sharp"] / sm) +
            0.20 * (r["mouth_open"] / mm) +
            0.15 * (1.0 if r["eyes"] >= 2 else 0.5)
            , 3) * exp_ok
    rows.sort(key=lambda r: -r["rank"])
    return rows

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--tile", choices=list(TILES), required=True)
    ap.add_argument("--start", type=float, required=True, help="parent-stream seconds")
    ap.add_argument("--end", type=float, required=True)
    ap.add_argument("--step", type=float, default=0.5)
    ap.add_argument("--out", default=None, help="write top-N crops here")
    ap.add_argument("--top", type=int, default=8)
    a = ap.parse_args()

    rows = []
    t = a.start
    while t <= a.end:
        img = grab(a.src, t, a.tile)
        if img is not None:
            s = score_tile(img)
            if s:
                s["t_abs"] = round(t, 2)
                s["t_off"] = round(t - CLOCK0, 2)
                rows.append(s)
        print(".", end="", flush=True)
        t += a.step
    print()
    rank(rows)
    print("%-9s %-9s %-12s %-8s %-5s %-10s %-9s %s" %
          ("t_abs", "t_off", "face_h_frac", "sharp", "eyes", "mouth_open", "exposure", "rank"))
    for r in rows[:30]:
        print("%-9.2f %-9.2f %-12.3f %-8.1f %-5d %-10.2f %-9.3f %.3f" %
              (r["t_abs"], r["t_off"], r["face_h_frac"], r["sharp"], r["eyes"],
               r["mouth_open"], r["exposure"], r["rank"]))
    if a.out:
        os.makedirs(a.out, exist_ok=True)
        for r in rows[:a.top]:
            img = grab(a.src, r["t_abs"], a.tile)
            p = os.path.join(a.out, "%s_%.2f_r%.3f.png" % (a.tile, r["t_abs"], r["rank"]))
            cv2.imwrite(p, img)
            print("wrote", p)
        with open(os.path.join(a.out, "%s_scout.json" % a.tile), "w") as fh:
            json.dump(rows, fh, indent=1)

if __name__ == "__main__":
    main()
