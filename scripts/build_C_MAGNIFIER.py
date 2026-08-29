"""C_MAGNIFIER - raw wide courtroom frame + a circular self-magnifier on Judge Boyd.

One real frame from the hearing. No matting, no cut-out, no plate, no text,
no arrow. The only addition is a white-ringed circular loupe holding a
magnified crop of Judge Boyd's face taken from THAT SAME FRAME, sitting in the
right third over the defendant's chest and the letterbox below it.

Geometry is measured, not guessed:
  haar frontal-face on the chosen frame gave
    Boyd     x329-457  y256-384
    attorney x718-794  y262-338
    defendant x944-1023 y269-348
  active picture band (non-black rows) = y181..543, full width.
"""
import sys, subprocess
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, "C:/Users/natha/Projects/boyd-clips/src")
from boydclips.thumbnail import grade_image

SRC   = Path("C:/Users/natha/Projects/boyd-clips/work/EwwnbiAQtFk/EwwnbiAQtFk_h_3574_3554-4697.mp4")
T0    = 3554.0
PICK  = 3960.0                       # "cuz it's too fun there" beat; Boyd flat down the lens
OUT   = Path("C:/Users/natha/OneDrive/Desktop/Boyd Clips/READY-TO-POST/CONSTRUCTIONS/C_MAGNIFIER.jpg")
TMP   = Path("C:/Users/natha/AppData/Local/Temp/claude/C--Users-natha/bfd92cc4-ce5e-4bc4-a876-3eccaae1aaad/scratchpad/mag/base_3960.png")

# ---- 1. the raw frame -----------------------------------------------------
TMP.parent.mkdir(parents=True, exist_ok=True)
subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", str(PICK - T0),
                "-i", str(SRC), "-frames:v", "1", str(TMP), "-y"], check=True)
raw = Image.open(TMP).convert("RGB")
assert raw.size == (1280, 720), raw.size

# ---- 2. no re-window ------------------------------------------------------
# First build cropped to a tight 16:9 around both heads to kill the letterbox.
# Rejected on inspection: Boyd's Zoom tile is ALREADY a medium close-up, so at
# that scale the loupe was only ~1.5x her in-frame size and added nothing, and
# the defendant got squeezed against the right edge. The construction only
# earns its keep on the genuinely wide plate. So the base is the frame exactly
# as recorded - both tiles, both burned-in labels, letterbox, watermark.
base = raw.copy()

def to_final(sx, sy):
    return sx, sy

# ---- 3. barely graded -----------------------------------------------------
# curve_strength 1.0 is exactly the tone curve the rendered VIDEO gets, so the
# thumbnail matches its own clip. Saturation/contrast pulled back near unity so
# this still reads as an unretouched screen grab rather than a graded poster.
base = grade_image(base, {"curve_strength": 0.85, "contrast": 1.02,
                          "sat_gain": 1.12, "brightness": 1.0,
                          "sharpen_percent": 55})

# ---- 4. the magnifier -----------------------------------------------------
# Content sampled from the ORIGINAL frame, not from the already-upscaled base,
# so the loupe is 1.7x off native pixels instead of 2.8x.
FCX, FCY, FSIDE = 393, 312, 172      # square around Boyd's head, from the haar box
D = 336                              # loupe diameter -> 1.95x off native pixels
CX, CY = 1072, 540                   # right third; top edge y362 clears the
                                     # defendant's chin (y348), bottom y718 in frame

face = raw.crop((FCX - FSIDE // 2, FCY - FSIDE // 2,
                 FCX + FSIDE // 2, FCY + FSIDE // 2)).resize((D, D), Image.LANCZOS)
face = grade_image(face, {"curve_strength": 1.0, "contrast": 1.04,
                          "sat_gain": 1.16, "brightness": 1.02,
                          "sharpen_radius": 1.6, "sharpen_percent": 150})

SS = 4                               # supersampled masks so the ring is not stair-stepped
def disc(d, pad=0):
    m = Image.new("L", ((d + 2 * pad) * SS,) * 2, 0)
    ImageDraw.Draw(m).ellipse((pad * SS, pad * SS, (pad + d) * SS - 1, (pad + d) * SS - 1), fill=255)
    return m.resize(((d + 2 * pad),) * 2, Image.LANCZOS)

# drop shadow first, so the loupe reads as sitting ON the frame
PAD = 26
sh = Image.new("L", base.size, 0)
sh.paste(disc(D, PAD), (CX - D // 2 - PAD, CY - D // 2 - PAD + 6))
sh = sh.filter(ImageFilter.GaussianBlur(14)).point(lambda v: int(v * 0.55))
base = Image.composite(Image.new("RGB", base.size, (0, 0, 0)), base, sh)

# white ring: a filled white disc slightly larger than the loupe, then the
# picture punched into the middle of it
RING = 10
white = Image.new("RGB", base.size, (255, 255, 255))
ringmask = Image.new("L", base.size, 0)
ringmask.paste(disc(D + 2 * RING), (CX - D // 2 - RING, CY - D // 2 - RING))
base = Image.composite(white, base, ringmask)

base.paste(face, (CX - D // 2, CY - D // 2), disc(D))

# ---- 5. out ---------------------------------------------------------------
assert base.size == (1280, 720)
OUT.parent.mkdir(parents=True, exist_ok=True)
base.save(OUT, "JPEG", quality=95, subsampling=0, optimize=True)
print("wrote", OUT, Image.open(OUT).size, OUT.stat().st_size, "bytes")
print("boyd face final  ", [round(v) for v in to_final(329, 256)], [round(v) for v in to_final(457, 384)])
print("defendant final  ", [round(v) for v in to_final(944, 269)], [round(v) for v in to_final(1023, 348)])
print("loupe box        ", CX - D // 2 - RING, CY - D // 2 - RING, CX + D // 2 + RING, CY + D // 2 + RING)
print("magnification    ", round(D / FSIDE, 2), "x")
