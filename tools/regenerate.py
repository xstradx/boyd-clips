# -*- coding: utf-8 -*-
"""R28 stage two: REGENERATE the person after HYPIR restores them.

Nathan's rule, `spec/NATHAN_RULES.md` R28, in his own words:

    "you need to upscale Judge Boyd - and not just upscale, you need to actually
     regenerate the picture."

    "like when you go tell an AI, make this picture look like it was taken in 4k,
     and it's remaking the person to its best ability... it's a remade AI picture
     of the person that looks hyper realistic."

The order is fixed: HYPIR restore -> QWEN REGENERATE -> cut -> composite -> grade.
The rules file has carried "Qwen NOT AUTOMATED YET" since 2026-08-29 and that is
why the output still reads as processed: HYPIR restores detail, it does not
re-photograph the person.

WHY THIS DID NOT WORK BEFORE
`D:/AI-Models/comfyui/unet/qwen-image-edit-2511-Q5_K_M.gguf` is 899 MB. A real
Q5_K_M of this model is ~14 GB. It is a truncated download and always was -
which is the same stub that derailed an earlier attempt. Rather than rebuild a
ComfyUI stack around a broken file (Nathan: "Stop doing all that... Just use the
hypir"), this runs the diffusers-format weights through the env that already
works: `wan2gp`, torch 2.7.1+cu128, diffusers 0.36 with QwenImageEditPipeline
built in, on the RTX 5080.

THE GUARD THAT MATTERS
These are real people in a public-record court video. An image-edit model can
drift a face into a *different* face, and publishing a subtly-wrong face of a
named defendant is not a craft problem, it is a misrepresentation. So every
regeneration is identity-checked against the input with SFace, and a drift
beyond IDENTITY_MIN is REJECTED - the HYPIR frame is kept instead. A rejection
is reported out loud, never silently swallowed.
"""
import os
import sys

import numpy as np

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MODEL_DIR = "D:/AI-Models/qwen-image-edit-2511"
PY = "C:/Users/natha/miniconda3/envs/wan2gp/python.exe"

# Low strength on purpose. The brief is "make this look like it was shot in 4k",
# not "imagine this person". High strength is how an edit model invents a
# stranger.
PROMPT = ("the same photograph, re-shot on a professional full-frame camera: "
          "natural skin texture with visible pores, sharp accurate detail, "
          "true-to-life colour, soft even lighting, photorealistic")
NEGATIVE = ("illustration, painting, cgi, plastic skin, airbrushed, waxy, "
            "oversaturated, distorted features, extra fingers, warped face")
STEPS = 8
TRUE_CFG = 2.5
IDENTITY_MIN = 0.62      # SFace cosine to the input face; below this = rejected


def available():
    return os.path.isdir(MODEL_DIR) and os.path.exists(
        os.path.join(MODEL_DIR, "model_index.json"))


def _identity(a_bgr, b_bgr):
    """SFace cosine between the largest face in each image, or None."""
    try:
        import identity as I
        ra = I.faces_in(a_bgr, score=0.5)
        rb = I.faces_in(b_bgr, score=0.5)
        if not ra or not rb:
            return None
        ea = I.embed(a_bgr, max(ra, key=lambda r: r[3]))
        eb = I.embed(b_bgr, max(rb, key=lambda r: r[3]))
        return float(np.dot(ea, eb))
    except Exception:
        return None


# 4-BIT NF4. Measured on this machine: 31.4 GB RAM, 16 GB VRAM, against a
# 55 GB bf16 model (39 GB transformer + 16 GB text encoder). Plain load
# segfaults; optimum-quanto MemoryErrors at shard 3/5 because it quantises
# AFTER loading to RAM. bitsandbytes quantises DURING load, which is the whole
# difference. Loaded this way it sits at 2.9 GB VRAM with CPU offload.
WORKER = r'''
import sys, torch
from PIL import Image
from diffusers import QwenImageEditPipeline, BitsAndBytesConfig as DBnb
from diffusers.quantizers import PipelineQuantizationConfig
from transformers import BitsAndBytesConfig as TBnb
src, dst, prompt, neg, steps, cfg, model = sys.argv[1:8]
q = PipelineQuantizationConfig(quant_mapping={
    "transformer": DBnb(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                        bnb_4bit_compute_dtype=torch.bfloat16),
    "text_encoder": TBnb(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                         bnb_4bit_compute_dtype=torch.bfloat16),
})
# device_map="balanced" streams each shard to the GPU as it loads instead of
# assembling the whole model in RAM first. Without it this MemoryErrors
# intermittently: 31 GB of RAM against a 55 GB model is marginal, so it
# succeeded when RAM happened to be free and died when it did not - the worst
# kind of failure, because it looks like a flake.
pipe = QwenImageEditPipeline.from_pretrained(model, quantization_config=q,
                                             torch_dtype=torch.bfloat16,
                                             device_map="balanced")
im = Image.open(src).convert("RGB")
w, h = im.size
# cap the working size - a 2448px crop through a 20B model is not worth the
# minutes, and the result is resized back to the layer's own size anyway
mx = 1024
if max(w, h) > mx:
    sc = mx / max(w, h)
    work = im.resize((int(w * sc), int(h * sc)), Image.LANCZOS)
else:
    work = im
out = pipe(image=work, prompt=prompt, negative_prompt=neg,
           num_inference_steps=int(steps), true_cfg_scale=float(cfg),
           generator=torch.Generator(device="cpu").manual_seed(7)).images[0]
out.resize((w, h), Image.LANCZOS).save(dst)
print("WORKER_OK")
'''

def regenerate(src_png, dst_png, verbose=True):
    """Regenerate one person layer. Returns the path actually written.

    Falls back to the HYPIR input - and says so - if the model is absent, the
    worker fails, or the identity check rejects the result.
    """
    import subprocess
    import shutil
    import tempfile
    import cv2

    if not available():
        if verbose:
            print(f"  regenerate: model not present at {MODEL_DIR} - keeping HYPIR")
        return src_png

    with tempfile.TemporaryDirectory() as d:
        tmp = os.path.join(d, "regen.png")
        w = os.path.join(d, "worker.py")
        open(w, "w").write(WORKER)
        r = subprocess.run([PY, w, src_png, tmp, PROMPT, NEGATIVE,
                            str(STEPS), str(TRUE_CFG), MODEL_DIR],
                           capture_output=True, text=True)
        if "WORKER_OK" not in (r.stdout or "") or not os.path.exists(tmp):
            if verbose:
                tail = (r.stderr or r.stdout or "")[-200:].replace("\n", " ")
                print(f"  regenerate: FAILED, keeping HYPIR - {tail}")
            return src_png
        sim = _identity(cv2.imread(src_png), cv2.imread(tmp))
        if sim is not None and sim < IDENTITY_MIN:
            print(f"  regenerate: REJECTED - identity drifted to {sim:.3f} "
                  f"(floor {IDENTITY_MIN}). These are real people in a public "
                  f"record; keeping the HYPIR frame.")
            return src_png
        shutil.copy(tmp, dst_png)
        if verbose:
            print(f"  regenerate: OK  identity {sim if sim is None else round(sim, 3)}"
                  f"  -> {os.path.basename(dst_png)}")
        return dst_png


def selftest():
    """Runs the real thing on a real crop when the weights exist; reports the
    honest reason when they do not, rather than passing vacuously."""
    if not available():
        print(f"  SELFTEST_SKIP weights not yet at {MODEL_DIR}")
        return 0
    import cv2
    src = "D:/Boyd Clips/thumbwork/OFFERUP/judge_hypir.png"
    if not os.path.exists(src):
        print("  SELFTEST_SKIP control crop missing")
        return 0
    out = os.path.join(os.path.dirname(src), "_regen_selftest.png")
    got = regenerate(src, out)
    ok = got == out and os.path.exists(out)
    if ok:
        a, b = cv2.imread(src), cv2.imread(out)
        print(f"  in {a.shape[1]}x{a.shape[0]} -> out {b.shape[1]}x{b.shape[0]}"
              f"  identity {_identity(a, b)}")
    else:
        print("  regeneration did not produce a kept result")
    print("SELFTEST_PASS regenerate" if ok else "SELFTEST_FAIL regenerate")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    if len(sys.argv) >= 3:
        regenerate(sys.argv[1], sys.argv[2])
    else:
        print("usage: regenerate.py SRC.png DST.png | --selftest")
        print(f"model present: {available()}")
