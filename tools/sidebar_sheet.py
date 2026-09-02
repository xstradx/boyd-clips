# -*- coding: utf-8 -*-
"""The comparison I should have built weeks ago.

Ours against the competitor's biggest winners, both rendered at the size YouTube
actually serves them (168x94) and then blown up equally so the screen shows the
same information a sidebar does. No 1280px masters anywhere on this sheet - the
master is the thing that has been misleading me.

Written to D:/Boyd Clips/thumbwork/_FEEDTEST/SIDEBAR_SHEET.png and opened.
"""
import os, sys, glob, re
import numpy as np
import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from thumbeng import variety as _V     # thumb_measure retired 2026-08-31


class TM:                               # tiny shim; the sheet needs 2 constants
    SIDEBAR = _V.SIDEBAR
    MASTER = (1280, 720)

    @staticmethod
    def measure(path):
        import cv2, numpy as np
        im = cv2.resize(cv2.imread(path), TM.MASTER, interpolation=cv2.INTER_AREA)
        a = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY).astype(np.float32).ravel()
        sm = cv2.resize(im, TM.SIDEBAR, interpolation=cv2.INTER_AREA)
        sm = cv2.GaussianBlur(sm, (0, 0), 2.0)
        b = cv2.cvtColor(cv2.resize(sm, TM.MASTER, interpolation=cv2.INTER_CUBIC),
                         cv2.COLOR_BGR2GRAY).astype(np.float32).ravel()
        return {"roundtrip_r": float(np.corrcoef(a, b)[0, 1])}

OUT = r"D:/Boyd Clips/thumbwork/_FEEDTEST"
COMP = r"C:/Users/natha/Projects/boyd-clips/research/reference/competitor/thumbs/*.jpg"
OURS = [
    (r"D:/Boyd Clips/thumbwork/CARTHIEF/CARTHIEF_thumb.jpg", "CARTHIEF"),
    (r"D:/Boyd Clips/thumbwork/MONKEY/MONKEY_thumb.jpg", "SPIDER MONKEY"),
    (r"D:/Boyd Clips/thumbwork/THOMPSON/THOMPSON_thumb.jpg", "THOMPSON"),
    (r"D:/Boyd Clips/thumbwork/OFFERUP/OFFERUP_thumb.jpg", "OFFERUP"),
]

K = 4                       # sidebar cells drawn 4x - readable on a 5120 panel
CW, CH = TM.SIDEBAR[0] * K, TM.SIDEBAR[1] * K
PAD, HEAD, GUT = 18, 96, 70
FONT = cv2.FONT_HERSHEY_SIMPLEX


def txt(img, s, xy, sc=0.6, col=(240, 240, 240), th=1, shadow=True):
    if shadow:
        cv2.putText(img, s, xy, FONT, sc, (0, 0, 0), th + 3, cv2.LINE_AA)
    cv2.putText(img, s, xy, FONT, sc, col, th, cv2.LINE_AA)


def cell(path, caption, sub, accent):
    """One thumbnail, downscaled to the literal sidebar size and back up."""
    im = cv2.imread(path)
    im = cv2.resize(im, TM.MASTER, interpolation=cv2.INTER_AREA)
    small = cv2.resize(im, TM.SIDEBAR, interpolation=cv2.INTER_AREA)
    big = cv2.resize(small, (CW, CH), interpolation=cv2.INTER_NEAREST)
    panel = np.full((CH + 54, CW, 3), 22, np.uint8)
    panel[:CH] = big
    cv2.rectangle(panel, (0, 0), (CW - 1, CH - 1), accent, 2)
    txt(panel, caption, (4, CH + 20), 0.5, (245, 245, 245), 1, shadow=False)
    txt(panel, sub, (4, CH + 42), 0.44, accent, 1, shadow=False)
    return panel


def main():
    os.makedirs(OUT, exist_ok=True)
    comp = sorted(glob.glob(COMP),
                  key=lambda p: -int(re.match(r"(\d+)_", os.path.basename(p)).group(1)))[:4]

    ours, theirs = [], []
    for p, name in OURS:
        m = TM.measure(p)
        ours.append(cell(p, name, f"r={m['roundtrip_r']:.3f}", (80, 190, 255)))
    for p in comp:
        v = int(re.match(r"(\d+)_", os.path.basename(p)).group(1))
        m = TM.measure(p)
        theirs.append(cell(p, f"{v//1000}K views", f"r={m['roundtrip_r']:.3f}",
                           (120, 255, 140)))

    ch = ours[0].shape[0]
    W = PAD * 2 + CW * 4 + GUT * 3
    H = HEAD + ch * 2 + GUT + PAD + 40
    sheet = np.full((H, W, 3), 16, np.uint8)

    txt(sheet, "WHAT THE SIDEBAR ACTUALLY SERVES  -  every tile below is a real "
               "168x94 render, magnified equally", (PAD, 34), 0.66, (255, 255, 255), 2,
        shadow=False)
    txt(sheet, "r = structure surviving the downscale.  ours mean 0.749   "
               "Audit the Court mean 0.840", (PAD, 64), 0.55, (170, 170, 175), 1,
        shadow=False)

    for i, p in enumerate(ours):
        x = PAD + i * (CW + GUT)
        sheet[HEAD:HEAD + ch, x:x + CW] = p
    txt(sheet, "TEXAS TRIAL TRACKER", (PAD, HEAD - 10), 0.58, (80, 190, 255), 1, shadow=False)

    y2 = HEAD + ch + GUT
    for i, p in enumerate(theirs):
        x = PAD + i * (CW + GUT)
        sheet[y2:y2 + ch, x:x + CW] = p
    txt(sheet, "AUDIT THE COURT  -  same judge, same courtroom, their four biggest",
        (PAD, y2 - 10), 0.58, (120, 255, 140), 1, shadow=False)

    out = os.path.join(OUT, "SIDEBAR_SHEET.png")
    cv2.imwrite(out, sheet)
    print("wrote", out, sheet.shape)
    return out


if __name__ == "__main__":
    main()
