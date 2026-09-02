# -*- coding: utf-8 -*-
"""Every finished thumbnail on one sheet, at the size YouTube actually serves.

Nathan judges these at feed size, not at 1280px - the skill has said so since
the beginning and it is the single most common reason a build that "looks fine"
reads as sloppy in a sidebar. So each row shows the same file twice: large
enough to inspect the craft, and at 168x94, which is what a viewer sees.

    python tools/contact_sheet.py OUT.png FILE [FILE ...]
"""
import os
import sys

import cv2
import numpy as np

BIG_W = 640
SMALL_W = 168          # the sidebar size YouTube serves
PAD = 14
LABEL_H = 30
BG = (250, 250, 250)


def row(path):
    im = cv2.imread(path)
    if im is None:
        return None
    h, w = im.shape[:2]
    big = cv2.resize(im, (BIG_W, int(h * BIG_W / w)), interpolation=cv2.INTER_AREA)
    small = cv2.resize(im, (SMALL_W, int(h * SMALL_W / w)), interpolation=cv2.INTER_AREA)
    rh = big.shape[0]
    canvas = np.full((rh + LABEL_H, BIG_W + PAD + SMALL_W, 3), BG, np.uint8)
    canvas[LABEL_H:LABEL_H + big.shape[0], :BIG_W] = big
    # the sidebar copy sits top-aligned beside it
    canvas[LABEL_H:LABEL_H + small.shape[0], BIG_W + PAD:BIG_W + PAD + SMALL_W] = small
    name = os.path.splitext(os.path.basename(path))[0]
    cv2.putText(canvas, name, (4, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (20, 20, 20), 2)
    cv2.putText(canvas, "168px", (BIG_W + PAD, 21), cv2.FONT_HERSHEY_SIMPLEX,
                0.5, (110, 110, 110), 1)
    return canvas


def main(out, paths):
    rows = [r for r in (row(p) for p in paths) if r is not None]
    if not rows:
        print("nothing to draw")
        return 1
    w = max(r.shape[1] for r in rows)
    padded = []
    for r in rows:
        if r.shape[1] < w:
            r = cv2.copyMakeBorder(r, 0, 0, 0, w - r.shape[1],
                                   cv2.BORDER_CONSTANT, value=BG)
        padded.append(r)
        padded.append(np.full((PAD, w, 3), BG, np.uint8))
    cv2.imwrite(out, np.vstack(padded))
    print(f"wrote {out}  ({len(rows)} thumbnails)")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: contact_sheet.py OUT.png FILE [FILE ...]")
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2:]))
