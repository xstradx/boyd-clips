"""A_NOTEXT - zero manufactured type. The entire hook is the frame.

FRAME SELECTION (measured, not eyeballed):
  Swept every 1s of the case, source 3574 -> 4628 (1055 frames), both Zoom
  tiles, with OpenCV YuNet -> 4993 face detections (work file A_sweep.json).

  1. The defendant's face is LOCKED at ~80px tall for the whole hearing:
     min 66.2, median 80.7, p99 86.3, max 90.1. The court camera never pushes
     in. So frame choice here cannot buy face size - it can only buy GAZE and
     EXPRESSION. That single measurement decided the whole construction.
  2. Judge Boyd's face is far larger (median 137px, max 232px) and was the
     tempting pick on pixels alone. Rejected: in every high-scoring judge frame
     she is looking DOWN at her bench, and a judge on her own carries no story.
     A kid who looks 16 in orange jail scrubs IS the story, told with no words.
  3. Ranked all 1055 defendant frames on frontality (nose offset from eye
     midpoint / interocular distance), roll, and Laplacian sharpness, then
     hand-reviewed the top 20 plus the flagged beats at 0.2s granularity.
  4. WINNER t=4437.4 - the one frame where he looks straight down the lens,
     eyes fully open, mouth set. Runner-up was 4577.4 (chin up, more attitude)
     but his gaze is off-axis, and for a thumbnail with no type, direct eye
     contact is the entire attention mechanism.

CROP: hard, so his head is 43% of frame height (309px). Right-anchored inside
the tile at x0=800 because the attorney's face ends at x=785 - this is the
tightest crop that excludes his head and leaves only an anonymous navy
shoulder, which reads as "flanked by counsel" without competing for the eye.
"""
import sys
import cv2
import numpy as np

sys.path.insert(0, "C:/Users/natha/Projects/boyd-clips/src")
from PIL import Image, ImageDraw, ImageFont
from boydclips.thumbnail import grade_image

SRC = "C:/Users/natha/Projects/boyd-clips/work/EwwnbiAQtFk/EwwnbiAQtFk_h_3574_3554-4697.mp4"
T0 = 3554.0
T_PICK = 4437.4
FONT = "C:/Users/natha/Projects/boyd-clips/assets/fonts/TTTHeadline-Regular.ttf"
OUT = ("C:/Users/natha/OneDrive/Desktop/Boyd Clips/READY-TO-POST/"
       "CONSTRUCTIONS/A_NOTEXT.jpg")

# Zoom tile geometry, measured off the decoded frame:
#   right tile inner content  x 646..1262, y 192..503
#   green active-speaker border    x 640..645 and 1263..1268   -> excluded
#   burned-in "187th DC" label     y 505..530, bottom-left     -> excluded
TILE = (646, 1262, 192, 503)
CROP_X0, CROP_Y0, CROP_W, CROP_H = 800, 228, 456, 256


def grab(t):
    cap = cv2.VideoCapture(SRC)
    cap.set(cv2.CAP_PROP_POS_MSEC, (t - T0) * 1000.0)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise RuntimeError(f"could not decode t={t}")
    return frame


def vignette(img, amount=0.20):
    """Gentle elliptical falloff. Sinks the two clerks at the back of the room
    and the blown ceiling so the eye lands on his face. Photographic, not a
    retouch - no pixel is moved, only luminance rolled off toward the corners.
    """
    w, h = img.size
    yy, xx = np.mgrid[0:h, 0:w]
    nx = (xx - w / 2.0) / (w / 2.0)
    ny = (yy - h / 2.0) / (h / 2.0)
    r = np.sqrt(nx ** 2 + ny ** 2) / np.sqrt(2.0)
    mask = 1.0 - amount * np.clip((r - 0.45) / 0.55, 0.0, 1.0) ** 1.6
    a = np.asarray(img, dtype=np.float32) * mask[..., None]
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def wordmark(img, text="TEXAS TRIAL TRACKER", target_frac=0.26):
    """Channel wordmark only - the one thing on this image that is type, and it
    is identity, not a hook. Law&Crime and Court TV both do exactly this on
    their text-free thumbnails. Bottom-left, over the attorney's navy shoulder,
    which the face-box check below confirms is not a face.
    """
    size = 10
    while True:
        f = ImageFont.truetype(FONT, size)
        w = f.getbbox(text)[2] - f.getbbox(text)[0]
        if w >= img.size[0] * target_frac or size > 200:
            break
        size += 1
    f = ImageFont.truetype(FONT, size - 1)
    d = ImageDraw.Draw(img)
    bb = d.textbbox((0, 0), text, font=f)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    x, y = 46, img.size[1] - th - 52
    for dx, dy in ((2, 2), (2, 3), (3, 2)):
        d.text((x + dx - bb[0], y + dy - bb[1]), text, font=f, fill=(0, 0, 0, 255))
    d.text((x - bb[0], y - bb[1]), text, font=f, fill=(255, 255, 255))
    return (x, y, x + tw, y + th)


frame = grab(T_PICK)

x0, y0, w, h = CROP_X0, CROP_Y0, CROP_W, CROP_H
assert TILE[0] <= x0 and x0 + w <= TILE[1], "crop leaves tile / hits green border"
assert TILE[2] <= y0 and y0 + h <= TILE[3], "crop would include the 187th DC label"
assert abs((w / h) - (16 / 9)) < 0.01, "crop is not 16:9"

crop = frame[y0:y0 + h, x0:x0 + w]
up = cv2.resize(crop, (1280, 720), interpolation=cv2.INTER_LANCZOS4)
img = Image.fromarray(cv2.cvtColor(up, cv2.COLOR_BGR2RGB))

# sat_gain pulled 1.45 -> 1.16. At the 1.45 default his lips rendered neon red
# on a face that fills 43% of frame - a tell that the frame has been treated.
# The orange scrubs are already the most saturated object in the room and need
# no help. Curve strength kept at the briefed 1.35.
img = grade_image(img, {"curve_strength": 1.35, "sat_gain": 1.16})
img = vignette(img)
wm = wordmark(img)

# ---- verification: no type over any face -------------------------------
det = cv2.FaceDetectorYN.create(
    "C:/Users/natha/AppData/Local/Temp/claude/C--Users-natha/"
    "bfd92cc4-ce5e-4bc4-a876-3eccaae1aaad/scratchpad/models/yunet_2026may.onnx",
    "", (1280, 720), 0.6, 0.3, 5000)
bgr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
_, faces = det.detect(bgr)
boxes = []
if faces is not None:
    for f in faces:
        bx, by, bw, bh = f[:4]
        boxes.append((int(bx), int(by), int(bx + bw), int(by + bh)))
for b in boxes:
    overlap = not (wm[2] < b[0] or wm[0] > b[2] or wm[3] < b[1] or wm[1] > b[3])
    assert not overlap, f"wordmark {wm} overlaps face {b}"
print("faces found in final:", boxes)
print("wordmark box:", wm, "-> width frac",
      round((wm[2] - wm[0]) / 1280, 3))

img.save(OUT, quality=95, subsampling=0, optimize=True)

chk = Image.open(OUT)
print("WROTE", OUT)
print("size", chk.size, "mode", chk.mode)
assert chk.size == (1280, 720)
