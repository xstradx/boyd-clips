# -*- coding: utf-8 -*-
"""True alpha matting for the subject cut-outs.

Nathan, 2026-08-31: *"with the hair you're comparing it to all the thumbnails we
have but every single thumbnail had very low effort cut outs"*.

That is the correction that unblocked this. Every threshold in the matte gate
had been calibrated against the mattes already in this repo - so the bar was set
by the low-effort work, exactly the "SHIPPED IS NOT GOOD" trap, applied to
cut-outs instead of layouts.

And the tool was wrong at the category level, not the setting level:
`birefnet-general` and `birefnet-portrait` are SEGMENTATION models. They answer
"is this pixel the subject", which is a yes/no question, and soft edges are a
by-product. Hair needs a MATTING model, which answers "how much of this pixel is
the subject" - that is what an alpha channel is for.

The right model was already on this machine, in the HuggingFace cache, unused:
`emrikol/birefnet-matting-onnx`. Also present and not needed here: ViTMatte
(trimap-based) and InSPyReNet.

Measured against birefnet-portrait on the five judge crops - partial-alpha
pixels, i.e. how much of the edge is genuinely fractional rather than binary:

    MONKEY    19349 -> 23540  (1.22x)   and the stair-stepping is GONE
    OFFERUP   22001 -> 23649  (1.07x)
    THOMPSON  55979 -> 80131  (1.43x)
    CARTHIEF  22198 -> 31327  (1.41x)
    SANCHEZ   18338 -> 21087  (1.15x)

Cloth stayed tight (4-7px) throughout, so this is not the `birefnet-massive`
failure of buying hair detail with a mushy body edge.

The ONNX exposes logits, not probabilities - min-max normalising them (the first
attempt) produced an alpha that was 100% partial, a gradient across the whole
frame. It needs a sigmoid.
"""
import glob
import os

import cv2
import numpy as np

MODEL_GLOB = os.path.expanduser(
    "~/.cache/huggingface/hub/models--emrikol--birefnet-matting-onnx/"
    "snapshots/*/birefnet-matting.onnx")
SIZE = 1024                     # the export is fixed at 1024x1024
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)
PROVIDERS = ["CUDAExecutionProvider", "CPUExecutionProvider"]

_sess = None


def available():
    return bool(glob.glob(MODEL_GLOB))


def _session():
    global _sess
    if _sess is None:
        import onnxruntime as ort
        hits = glob.glob(MODEL_GLOB)
        if not hits:
            raise SystemExit("birefnet-matting.onnx not in the HuggingFace cache")
        _sess = ort.InferenceSession(hits[0], providers=PROVIDERS)
    return _sess


def alpha(bgr, refine=True):
    """Alpha for one BGR image, at the image's own resolution.

    The model runs at 1024 and the result is lifted back with a guided filter
    against the FULL-RES image as guide - that is what puts the edge back on the
    real hair rather than on a 1024-grid approximation of it.
    """
    h, w = bgr.shape[:2]
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    small = cv2.resize(rgb, (SIZE, SIZE), interpolation=cv2.INTER_AREA)
    x = ((small.astype(np.float32) / 255.0 - MEAN) / STD).transpose(2, 0, 1)[None]
    logits = _session().run(None, {"input_image": x})[0][0, 0]
    a = 1.0 / (1.0 + np.exp(-logits))          # LOGITS -> sigmoid, not min-max
    a = cv2.resize((a * 255).astype(np.uint8), (w, h), interpolation=cv2.INTER_LINEAR)
    if refine:
        a = cv2.ximgproc.guidedFilter(bgr, a, radius=6, eps=1e-4 * 255 * 255)
    return a


def selftest():
    """Known answer: on a judge crop the alpha must be mostly solid, mostly
    empty, and have a THIN band of genuinely fractional pixels between. A matte
    that is ~100% partial is the un-sigmoided failure this module hit first, and
    a matte with ~0% partial is the segmentation behaviour it replaces."""
    ok = True
    if not available():
        print("  SELFTEST_SKIP model not in cache")
        return 0
    src = "D:/Boyd Clips/thumbwork/OFFERUP/judge_hypir.png"
    if not os.path.exists(src):
        print("  SELFTEST_SKIP control crop missing")
        return 0
    a = alpha(cv2.imread(src))
    solid = float((a > 230).mean())
    empty = float((a < 25).mean())
    part = float(((a >= 25) & (a <= 230)).mean())
    print(f"  solid {solid*100:5.1f}%   empty {empty*100:5.1f}%   partial {part*100:5.2f}%")
    if not (0.30 < solid < 0.85):
        print("  FAIL solid fraction implausible for a half-frame subject"); ok = False
    if part > 0.08:
        print("  FAIL too much partial alpha - logits not squashed?"); ok = False
    if part < 0.002:
        print("  FAIL almost no partial alpha - this is segmentation, not matting"); ok = False
    print("SELFTEST_PASS matting" if ok else "SELFTEST_FAIL matting")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    sys.exit(selftest() if "--selftest" in sys.argv else 0)
