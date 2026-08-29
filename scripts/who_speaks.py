"""Who is talking in a 2-up short — audio-visual correlation, not raw motion.

Nathan, twice: the captions must sit on the speaking person's half, and the
first version was "still not 100% correct".

WHY v1 WAS WRONG. It compared raw mouth-region motion between the two halves
and took the larger. That cannot tell "moving because talking" from "moving
because nodding, shifting, or reacting" — and Judge Boyd is animated while
listening, so she stole blocks from the defendant. Measured 5/6 on hand-labelled
windows, i.e. visibly wrong about one block in six.

WHAT THIS DOES INSTEAD. A talking mouth moves IN TIME WITH THE AUDIO; a nodding
head does not. So both mouth-motion series are correlated against the audio
envelope over the block's own window, and the speaker is whoever's motion
actually tracks the sound. That is a cheap version of what SyncNet-family
active-speaker models do, and it needs no model, no weights and no licence.

Three other things v1 got wrong and this fixes:
  * 5fps is below the 4-8Hz modulation rate of speech, so it aliased. Now 15fps.
  * The band included hair and shoulders. The tiles are LOCKED Zoom crops, so
    the mouth sits in the same place all clip — found once by face detection and
    then reused, rather than guessed per frame.
  * Median normalisation only. Now each series is z-scored so the two tiles are
    comparable despite different lighting and camera noise.
"""
from __future__ import annotations
import argparse, json, subprocess, tempfile, wave
from pathlib import Path
import numpy as np
from PIL import Image

FPS = 15.0


def audio_envelope(video: Path, fps: float, n: int) -> np.ndarray:
    with tempfile.TemporaryDirectory() as td:
        w = Path(td) / "a.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-ac", "1",
                        "-ar", "16000", str(w), "-y"], capture_output=True, timeout=900)
        if not w.is_file():
            return np.zeros(n)
        with wave.open(str(w), "rb") as f:
            raw = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16)
            sr = f.getframerate()
    step = int(sr / fps)
    env = np.array([np.abs(raw[i * step:(i + 1) * step]).mean()
                    for i in range(min(n, len(raw) // max(1, step)))], dtype=float)
    if len(env) < n:
        env = np.pad(env, (0, n - len(env)), mode="edge")
    return env[:n]


def mouth_boxes(video: Path, split_y: int, w: int, h: int):
    """Locate each half's mouth once. The Zoom tiles are locked, so a position
    found on a handful of frames holds for the whole clip - which is why this
    does not need per-frame detection, and why per-frame detection (which picks
    the attorney on this docket) is not required."""
    import cv2
    cc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_alt2.xml")
    out = {}
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf",
                        "fps=1/3", "-q:v", "3", str(td / "s_%03d.jpg")],
                       capture_output=True, timeout=900)
        for half, (y0, y1) in (("top", (0, split_y)), ("bottom", (split_y, h))):
            boxes = []
            for f in sorted(td.glob("s_*.jpg")):
                im = cv2.imread(str(f))
                if im is None:
                    continue
                sub = im[y0:y1]
                g = cv2.equalizeHist(cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY))
                for (fx, fy, fw, fh) in cc.detectMultiScale(g, 1.08, 5, minSize=(90, 90)):
                    boxes.append((fx, fy, fw, fh))
            if boxes:
                b = max(boxes, key=lambda b: b[2] * b[3])
                fx, fy, fw, fh = b
                # mouth: lower third of the face box, middle 70%
                out[half] = (fx + int(fw * 0.15), y0 + fy + int(fh * 0.58),
                             int(fw * 0.70), int(fh * 0.42))
            else:
                # fall back to the band that v1 used
                hh = y1 - y0
                out[half] = (int(w * 0.20), y0 + int(hh * 0.45),
                             int(w * 0.60), int(hh * 0.35))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True, type=Path)
    ap.add_argument("--split-y", type=int, default=960)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()

    dim = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                          "-show_entries", "stream=width,height", "-of", "csv=p=0",
                          str(a.video)], capture_output=True, text=True).stdout.strip().split(",")
    W, H = int(dim[0]), int(dim[1])
    mb = mouth_boxes(a.video, a.split_y, W, H)
    print(f"  mouth boxes: top={mb['top']}  bottom={mb['bottom']}")

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(a.video), "-vf",
                        f"fps={FPS}", "-q:v", "4", str(td / "f_%05d.jpg")],
                       capture_output=True, timeout=1800)
        fs = sorted(td.glob("f_*.jpg"))
        if len(fs) < 4:
            print("too few frames"); return 1
        prev, top, bot = None, [], []
        for f in fs:
            im = np.asarray(Image.open(f).convert("L"), dtype=np.float32)
            cur = {}
            for k, (x, y, bw, bh) in mb.items():
                cur[k] = im[y:y + bh, x:x + bw]
            if prev is not None:
                top.append(float(np.abs(cur["top"] - prev["top"]).mean()))
                bot.append(float(np.abs(cur["bottom"] - prev["bottom"]).mean()))
            prev = cur

    top = np.array(top); bot = np.array(bot)
    env = audio_envelope(a.video, FPS, len(top))

    def z(x):
        s = x.std()
        return (x - x.mean()) / (s if s > 1e-6 else 1.0)

    a.out.write_text(json.dumps({
        "fps": FPS, "top": z(top).tolist(), "bottom": z(bot).tolist(),
        "audio": z(env).tolist()}), encoding="utf-8")
    print(f"  {len(top)} samples at {FPS}fps, audio envelope aligned")
    print(f"  -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
