"""The 8-step/cfg2.5 output was blotchy garbage on BOTH prompts, so the noise is
the SAMPLING, not the prompt: 8 steps is a Lightning-LoRA setting and the base
model was being run half-denoised. Two candidate fixes, same crop, same prompt:

  LIGHT4  - Lightning 4-step LoRA (on disk), 4 steps, true_cfg 1.0
  FULL40  - no LoRA, 40 steps, true_cfg 4.0  (the model card's own defaults)

One variable at a time. Prompts get re-tested only after the sampler is clean.
"""
import os
import time

import torch
from PIL import Image
from diffusers import QwenImageEditPipeline, PipelineQuantizationConfig

MODEL = "D:/AI-Models/qwen-image-edit-2511"
LORA = ("D:/AI-Models/comfyui/loras/"
        "Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors")
SRC = "D:/Boyd Clips/thumbwork/PACE_v/defendant_hypir.png"
OUT = "D:/Boyd Clips/thumbwork/_STUDIO"
os.makedirs(OUT, exist_ok=True)

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
PROMPT = f"Turn this image into an ultra-realistic close-up portrait. {STUDIO} {IDENTITY_LOCK}"
NEG = ("illustration, painting, cgi, plastic skin, airbrushed, waxy, "
       "oversaturated, distorted features, warped face, different person")

print("loading 4-bit ...", flush=True)
t0 = time.time()
q = PipelineQuantizationConfig(
    quant_backend="bitsandbytes_4bit",
    quant_kwargs={"load_in_4bit": True, "bnb_4bit_quant_type": "nf4",
                  "bnb_4bit_compute_dtype": torch.bfloat16},
    components_to_quantize=["transformer", "text_encoder"])
pipe = QwenImageEditPipeline.from_pretrained(MODEL, quantization_config=q,
                                             torch_dtype=torch.bfloat16)
pipe.enable_model_cpu_offload()
print(f"loaded in {time.time()-t0:.0f}s", flush=True)

im = Image.open(SRC).convert("RGB")
w, h = im.size
MX = 1024
work = im
if max(w, h) > MX:
    s = MX / max(w, h)
    work = im.resize((int(w * s), int(h * s)), Image.LANCZOS)


def run(tag, steps, cfg):
    t = time.time()
    out = pipe(image=work, prompt=PROMPT, negative_prompt=NEG,
               num_inference_steps=steps, true_cfg_scale=cfg,
               generator=torch.Generator(device="cpu").manual_seed(7)).images[0]
    out.resize((w, h), Image.LANCZOS).save(os.path.join(OUT, f"{tag}.png"))
    print(f"WROTE {tag}  steps={steps} cfg={cfg}  {time.time()-t:.0f}s", flush=True)


# --- LIGHT4 -----------------------------------------------------------------
try:
    pipe.load_lora_weights(LORA)
    print("LORA_LOADED", flush=True)
    run("def_LIGHT4", 4, 1.0)
    pipe.unload_lora_weights()
    print("LORA_UNLOADED", flush=True)
except Exception as e:
    print(f"LORA_FAILED {type(e).__name__}: {e}", flush=True)
    try:
        pipe.unload_lora_weights()
    except Exception:
        pass

# --- FULL40 -----------------------------------------------------------------
run("def_FULL40", 40, 4.0)
print("ALL_DONE", flush=True)
