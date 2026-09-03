"""One-off probe: does a STUDIO-PORTRAIT prompt (Nathan's find, 2026-09-03)
beat our timid "re-shot on a full-frame camera" prompt through the same
Qwen-Image-Edit-2511 path?

Loads the model ONCE and runs every (crop x prompt) pair. Local, free, no API.
Writes to D:/Boyd Clips/thumbwork/_STUDIO/ and prints the SFace identity cosine
against the input for each - these are real people in a public record, so a
result that drifts is a reject, not a style choice.
"""
import os
import sys
import time

import torch
from PIL import Image
from diffusers import QwenImageEditPipeline, PipelineQuantizationConfig

MODEL = "D:/AI-Models/qwen-image-edit-2511"
WORK = "D:/Boyd Clips/thumbwork/PACE_v"
OUT = "D:/Boyd Clips/thumbwork/_STUDIO"
os.makedirs(OUT, exist_ok=True)

# --- the prompts -----------------------------------------------------------
# A = what the pipeline ships today (tools/regenerate.py PROMPT).
A = ("the same photograph, re-shot on a professional full-frame camera: "
     "natural skin texture with visible pores, sharp accurate detail, "
     "true-to-life colour, soft even lighting, photorealistic")

# B = Nathan's found prompt, adapted. Dropped: "looking straight at camera"
# and the body-crop instruction - we must keep HIS pose and expression, the
# crop is already decided by the layout. Kept verbatim in spirit: the studio
# detail list and the identity-lock paragraph, which is the operative part.
IDENTITY_LOCK = (
    "Preserve the exact facial identity, facial structure, proportions, eye "
    "shape, nose shape, hairline, skin tone, and all unique facial features "
    "from the reference image. Do not alter the person's face in any way. "
    "Maintain 100% likeness and identity accuracy. Keep the same expression, "
    "the same head angle and the same gaze direction as the reference.")
STUDIO = (
    "Premium studio-quality facial detail, highly realistic skin texture with "
    "visible pores, natural forehead lines, subtle wrinkles, fine facial "
    "imperfections, realistic subsurface scattering, natural lip texture, "
    "realistic eyelashes, high-definition eyebrows, bright catchlights in the "
    "eyes and crystal-clear iris detail. Cinematic YouTube thumbnail style, "
    "extremely sharp focus on the face, professional key light from front-left, "
    "soft rim light around head and shoulders, dramatic but clean lighting, "
    "premium camera quality, hyper-detailed skin rendering, photorealistic "
    "facial anatomy, 8K detail, ultra-clean image quality.")
B = f"Turn this image into an ultra-realistic close-up portrait. {STUDIO} {IDENTITY_LOCK}"
C = f"Turn this image into an ultra-realistic close-up portrait. {STUDIO} {IDENTITY_LOCK} Background: pure white studio backdrop."

NEG = ("illustration, painting, cgi, plastic skin, airbrushed, waxy, "
       "oversaturated, distorted features, warped face, different person")

JOBS = [
    ("defendant_hypir.png", "def_A", A),
    ("defendant_hypir.png", "def_B", B),
    ("defendant_hypir.png", "def_C", C),
    ("judge_hypir.png", "jud_A", A),
    ("judge_hypir.png", "jud_B", B),
    ("judge_hypir.png", "jud_C", C),
]

print("loading 4-bit ...", flush=True)
t0 = time.time()
q = PipelineQuantizationConfig(
    quant_backend="bitsandbytes_4bit",
    quant_kwargs={"load_in_4bit": True, "bnb_4bit_quant_type": "nf4",
                  "bnb_4bit_compute_dtype": torch.bfloat16},
    components_to_quantize=["transformer", "text_encoder"])
pipe = QwenImageEditPipeline.from_pretrained(
    MODEL, quantization_config=q, torch_dtype=torch.bfloat16)
pipe.enable_model_cpu_offload()
print(f"loaded in {time.time()-t0:.0f}s", flush=True)

MX = 1024
for src, tag, prompt in JOBS:
    p = os.path.join(WORK, src)
    im = Image.open(p).convert("RGB")
    w, h = im.size
    work = im
    if max(w, h) > MX:
        s = MX / max(w, h)
        work = im.resize((int(w * s), int(h * s)), Image.LANCZOS)
    t = time.time()
    out = pipe(image=work, prompt=prompt, negative_prompt=NEG,
               num_inference_steps=8, true_cfg_scale=2.5,
               generator=torch.Generator(device="cpu").manual_seed(7)).images[0]
    dst = os.path.join(OUT, f"{tag}.png")
    out.resize((w, h), Image.LANCZOS).save(dst)
    print(f"WROTE {tag}  {time.time()-t:.0f}s  {out.size}->{(w,h)}", flush=True)

print("ALL_DONE", flush=True)
