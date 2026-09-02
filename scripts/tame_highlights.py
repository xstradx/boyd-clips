"""Pull the courtroom's blown lights back without flattening the picture.

Nathan, 2026-08-29: "the one i called fire the top of boyds hair is still bright
and im sure you can turn the background super bright lights down just a bit while
keeping the thumbnail still looking bright just without that over powering and
the really bright ligh needs to be fixed in all of them because thats just how
her zoom camera picks up the court".

Two things in that, and the last clause is the important one: this is a property
of the SOURCE, not of one bad frame. Judge Boyd's Zoom camera meters for her face
and lets the courtroom's ceiling fixtures clip, on every hearing. So the
correction belongs in the pipeline permanently rather than being dialled in per
image.

MEASURED, share of pixels above 245:

                      whole frame   ceiling band   rest of frame
    CARTHIEF (liked)      5.21%        11.49%          2.00%
    SANCHEZ               7.51%        14.49%          3.93%
    OFFERUP               1.85%         5.45%          0.00%
    Thompson (shipped)    7.03%        16.58%          2.14%

The blowout is concentrated in the top third by a factor of five, which is what
makes it fixable without touching the rest of the image.

TWO SEPARATE CORRECTIONS, because they are two different problems:

  1. THE LIGHTS.  A soft knee above `knee` compresses the top end toward a
     ceiling below pure white. Everything below the knee is untouched, so the
     midtones - the faces, the scrubs, the wood - keep their brightness. That is
     the "still looking bright, just without that over powering" part: this
     lowers the CEILING, not the exposure.

  2. HER HAIR.  A rim of clipped highlight along the top of the cut-out, from the
     light behind her in her own room. It survives a global knee because it is a
     thin band, so it gets extra compression applied only within the top of the
     matte. Doing this globally instead would grey the whole picture.

Both work on V in HSV so hue and saturation are untouched; a naive RGB clamp
shifts blown pixels toward whichever channel clipped last and turns white lights
faintly cyan.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import scipy.ndimage as nd
from PIL import Image


def soft_knee(v: np.ndarray, knee: float, ceiling: float,
              strength: float = 1.0) -> np.ndarray:
    """Compress values above `knee` toward `ceiling`, leaving the rest alone.

    tanh is used rather than a hard clamp so the rolloff has no visible edge -
    a clamp puts a hard contour exactly where the lights are brightest, which
    reads as a blown-out shape rather than a light.
    """
    out = v.copy()
    hi = v > knee
    if not hi.any():
        return out
    span = max(ceiling - knee, 1e-6)
    x = (v[hi] - knee) / max(1.0 - knee, 1e-6)
    out[hi] = knee + span * np.tanh(x * strength)
    return out


def adaptive_knee(img: Image.Image, hot_pct: float = 0.5,
                  ceiling: float = 0.90) -> tuple[float, float]:
    """Derive the knee from THIS image's own highlight distribution.

    Nathan, 2026-08-29: "the older judge boy videos had a different quality
    camera and the color grading was different now the more recent years are
    different". Measured on the raw plate tiles, he is right and it is not
    subtle - share of pixels over 250:

        CARTHIEF  9.94%   (0.4 Mb/s encode)
        SANCHEZ   7.91%   (0.7 Mb/s)
        OFFERUP   8.07%   (0.7 Mb/s)

    A fixed knee therefore over-corrects one hearing and under-corrects another,
    and every future hearing is a new unknown. So the knee is placed where this
    image's highlights actually begin - the percentile above which only `hot_pct`
    of the frame sits - rather than at a number tuned on one courtroom.
    """
    v = np.asarray(img.convert("HSV"), dtype=np.float32)[:, :, 2] / 255.0
    knee = float(np.percentile(v, 100.0 - max(hot_pct, 0.05) * 12.0))
    # keep it sane: never so low it eats midtones, never so high it does nothing
    knee = float(min(max(knee, 0.62), 0.86))
    return knee, ceiling


def tame(img: Image.Image, knee: float = 0.78, ceiling: float = 0.93,
         strength: float = 1.15, hair_alpha: np.ndarray | None = None,
         hair_knee: float = 0.66, hair_ceiling: float = 0.86,
         hair_rows: float = 0.22) -> Image.Image:
    hsv = np.asarray(img.convert("HSV"), dtype=np.float32) / 255.0
    v = hsv[:, :, 2]
    v = soft_knee(v, knee, ceiling, strength)

    if hair_alpha is not None and hair_alpha.any():
        ys = np.where(hair_alpha.any(axis=1))[0]
        if len(ys):
            y0 = int(ys.min())
            y1 = int(y0 + hair_rows * (ys.max() - y0)) + 1
            band = np.zeros_like(hair_alpha, dtype=bool)
            band[y0:y1, :] = hair_alpha[y0:y1, :]
            # feather so the extra correction does not leave a horizontal seam
            w = nd.gaussian_filter(band.astype(np.float32), sigma=9.0)
            w = np.clip(w / max(w.max(), 1e-6), 0, 1)
            vh = soft_knee(v, hair_knee, hair_ceiling, strength)
            v = v * (1 - w) + vh * w

    hsv[:, :, 2] = np.clip(v, 0, 1)
    return Image.fromarray(
        (np.asarray(Image.fromarray((hsv * 255).round().astype(np.uint8), "HSV")
                    .convert("RGB"))).astype(np.uint8), "RGB")


def judge_alpha(img: Image.Image) -> np.ndarray | None:
    """Her silhouette: the matte component that bleeds off an edge and is tall."""
    try:
        from rembg import new_session, remove
        if not hasattr(judge_alpha, "_s"):
            judge_alpha._s = new_session("birefnet-portrait")
        a = np.asarray(remove(img.convert("RGBA"), session=judge_alpha._s)
                       .getchannel("A"), dtype=np.uint8)
        m = a > 24
        lbl, k = nd.label(m)
        if not k:
            return None
        H, W = m.shape
        best, score = None, -1
        for i in range(1, k + 1):
            c = lbl == i
            ys, xs = np.where(c)
            if len(ys) < 3000:
                continue
            # she is the one running off the bottom and off a side edge
            s = int(c.sum())
            if ys.max() >= H - 3:
                s *= 2
            if xs.max() >= W - 3 or xs.min() <= 2:
                s *= 2
            if s > score:
                best, score = c, s
        return best
    except Exception as e:
        print(f"  (matte unavailable: {e})")
        return None


def report(img: Image.Image, label: str) -> None:
    L = np.asarray(img.convert("L"), dtype=float)
    H = L.shape[0]
    print(f"  {label:9} >245 {(L > 245).mean() * 100:5.2f}%   "
          f"ceiling band {(L[:int(H * 0.34)] > 245).mean() * 100:5.2f}%   "
          f"mean {L.mean():5.1f}   p90 {np.percentile(L, 90):5.1f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--knee", type=float, default=0.78)
    ap.add_argument("--ceiling", type=float, default=0.93)
    ap.add_argument("--strength", type=float, default=1.15)
    ap.add_argument("--no-hair", action="store_true")
    ap.add_argument("--adaptive", action="store_true",
                    help="derive the knee from this image rather than using a "
                         "fixed one, so a different camera era self-corrects")
    ap.add_argument("--hot-pct", type=float, default=0.5)
    a = ap.parse_args()

    img = Image.open(a.image).convert("RGB")
    report(img, "before")
    if a.adaptive:
        a.knee, a.ceiling = adaptive_knee(img, a.hot_pct, a.ceiling)
        print(f"  adaptive knee {a.knee:.3f} ceiling {a.ceiling:.3f} "
              f"(derived from this image, not a fixed number)")
    ha = None if a.no_hair else judge_alpha(img)
    if ha is not None:
        print(f"  judge silhouette found ({int(ha.sum())}px), "
              f"extra rolloff on the top of her hair")
    out = tame(img, a.knee, a.ceiling, a.strength, ha)
    report(out, "after")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    out.save(a.out, "JPEG", quality=95, subsampling=0)
    print(f"  -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
