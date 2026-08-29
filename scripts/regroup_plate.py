"""Move the defendant closer to his attorney, without leaving a seam.

Nathan, 2026-08-28: "maybe even somehow scoot the defendant closer to his
attorny? just so everything just fits better in the thumbjail??"

Cropping cannot do this. The two men stand apart in the tile, and a crop changes
what is included, never the distance between them. So the pixels have to move —
which is the one operation that can break "still looking 100% real", and the
first attempt proved it: panning the whole plate and mirroring the edge to fill
produced a visible GHOST, the defendant duplicated across the frame.

Done properly it is three steps:

  1. Matte the defendant alone. He is found by his jail scrubs, not by face
     detection — face detection picks the attorney on this docket because the
     lawyer stands nearer the camera.
  2. Erase him from the plate by cloning background columns from beside his old
     position across it. The courtroom wall behind him is near-uniform, so a
     column clone is indistinguishable; this is not a general inpaint and it
     would fail against a patterned background.
  3. Paste him back `shift` pixels to the left, and feather the alpha edge a
     little so the join does not read as a cut line.

The result is checked, not assumed: `--report` prints the residual difference
in the vacated strip, which is what a visible seam would show up as.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter


def find_scrubs(img: Image.Image) -> tuple[int, int, int, int] | None:
    hsv = np.asarray(img.convert("HSV"), dtype=np.uint8)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    H, W = s.shape
    mask = (((h > 5) & (h < 32)) | ((h > 125) & (h < 165))) & (s > 110) & (v > 80)
    mask[: int(H * 0.20), :] = False
    ys, xs = np.where(mask)
    if len(xs) < H * W * 0.004:
        return None
    hist, edges = np.histogram(xs, bins=24, range=(0, W))
    peak = int(np.argmax(hist))
    lo, hi = edges[max(0, peak - 3)], edges[min(len(edges) - 1, peak + 4)]
    sel = (xs >= lo) & (xs <= hi)
    return (int(xs[sel].min()), int(ys[sel].min()),
            int(xs[sel].max() - xs[sel].min()), int(ys[sel].max() - ys[sel].min()))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plate", required=True, type=Path)
    ap.add_argument("--shift", type=int, required=True,
                    help="pixels to move him LEFT")
    ap.add_argument("--pad", type=int, default=40,
                    help="extra px around the scrubs bbox to take as 'him'")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--max-width-ratio", type=float, default=1.8,
                    help="refuse if the matte component is wider than this "
                         "multiple of the scrubs, i.e. it merged two people")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()

    plate = Image.open(a.plate).convert("RGB")
    W, H = plate.size
    sc = find_scrubs(plate)
    if sc is None:
        print("no scrubs found - cannot identify the defendant")
        return 1
    sx, sy, sw, sh = sc
    print(f"  scrubs at x{sx}-{sx+sw} y{sy}-{sy+sh}")

    from rembg import new_session, remove
    sess = new_session("birefnet-portrait")
    cut = remove(plate.convert("RGBA"), session=sess)
    alpha = np.asarray(cut.getchannel("A"), dtype=np.uint8)

    # Isolate him as a CONNECTED COMPONENT, never as a rectangle.
    #
    # Nathan, 2026-08-28: "it doesnt look good when you have those hard crops
    # like you cut the defendants whole arm off in one theres have to be
    # surgical cuts not slop". The previous version kept the alpha inside the
    # scrubs' column range, so any limb crossing that vertical boundary was
    # sliced clean off. A component follows his actual silhouette, so nothing
    # can be cut mid-limb.
    import scipy.ndimage as nd
    solid = alpha > 28
    lbl, n = nd.label(solid)
    if n == 0:
        print("empty matte")
        return 1
    # the component carrying the most scrubs pixels is him
    hsv = np.asarray(plate.convert("HSV"), dtype=np.uint8)
    hh, ss, vv = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    scrub_mask = ((((hh > 5) & (hh < 32)) | ((hh > 125) & (hh < 165)))
                  & (ss > 110) & (vv > 80))
    counts = nd.sum(scrub_mask, lbl, range(1, n + 1))
    comp = int(np.argmax(counts)) + 1
    him_mask = lbl == comp
    ys, xs = np.where(him_mask)
    hx0, hx1 = int(xs.min()), int(xs.max())
    hy0, hy1 = int(ys.min()), int(ys.max())
    print(f"  component {comp} of {n}: x{hx0}-{hx1} y{hy0}-{hy1} "
          f"({int(him_mask.sum())}px)")

    # MERGED-BLOB GUARD. If he and his attorney touch, the matte returns them as
    # ONE component and there is no honest way to split it — any cut is a guess
    # about where one body ends. Measured on this footage: src 4578 gives a
    # component 1.19x the scrubs width (clean), src 4437 gives 2.5x because the
    # two men are joined. Refuse rather than cut.
    ratio = (hx1 - hx0) / max(1, sw)
    if ratio > a.max_width_ratio:
        print(f"  REFUSING: component is {ratio:.2f}x the scrubs width — he is "
              f"merged with another person in the matte, so any separation "
              f"would cut through a body. Pick a frame where they do not touch.")
        return 2

    him = np.where(him_mask, alpha, 0).astype(np.uint8)
    him_img = Image.fromarray(him, "L").filter(ImageFilter.GaussianBlur(1.4))

    # --- erase him, PER ROW, following the silhouette -------------------
    #
    # For each row, take the first background pixel to the right of him and
    # extend it leftward across only the pixels he actually covers. A single
    # rectangle cloned one column across every row smeared a bright block into
    # the ceiling where the room's curved moulding does not repeat.
    arr = np.asarray(plate, dtype=np.uint8).copy()
    for yy in range(hy0, hy1 + 1):
        row = np.where(him_mask[yy])[0]
        if len(row) == 0:
            continue
        rx0, rx1 = int(row.min()), int(row.max())
        src = min(W - 1, rx1 + 8)
        arr[yy, rx0:rx1 + 1, :] = arr[yy, src, :]
    cleaned = Image.fromarray(arr, "RGB").filter(ImageFilter.GaussianBlur(1.1))
    keep = (him_mask * 255).astype(np.uint8)
    keep = np.asarray(Image.fromarray(keep, "L").filter(
        ImageFilter.MaxFilter(9)), dtype=np.uint8)
    base = Image.composite(cleaned, plate, Image.fromarray(keep, "L"))

    # --- paste him back, shifted left ---
    shifted_rgb = Image.new("RGB", (W, H))
    shifted_rgb.paste(plate, (-a.shift, 0))
    shifted_a = Image.new("L", (W, H), 0)
    shifted_a.paste(him_img, (-a.shift, 0))
    out = base.copy()
    out.paste(shifted_rgb, (0, 0), shifted_a)

    if a.report:
        # the strip he vacated: hx1-shift .. hx1
        s0, s1 = max(0, hx1 - a.shift), min(W, hx1 + 4)
        strip = np.asarray(out.convert("L"), dtype=float)[:, s0:s1]
        left = np.asarray(out.convert("L"), dtype=float)[:, max(0, s0 - 20):s0]
        print(f"  vacated strip x{s0}-{s1}: mean {strip.mean():.1f} "
              f"vs neighbour {left.mean():.1f}  (a seam shows as a gap here)")

    a.out.parent.mkdir(parents=True, exist_ok=True)
    out.save(a.out)
    print(f"  -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
