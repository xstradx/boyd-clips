"""bg_generate - regenerate ONLY the room, under the Fooocus CUDA interpreter.

Run with the Fooocus venv python, NOT the repo python:
    C:\\Users\\natha\\AI-Tools\\Fooocus\\venv\\Scripts\\python.exe

Why that interpreter: the repo's python has torch 2.13.0+cpu, so generation
would run on the CPU. Fooocus's venv has torch 2.10.0+cu128 with cuda True on
the RTX 5080. diffusers is installed separately at D:\\AI-Models\\pylibs with
--no-deps so Fooocus's own 120-package environment is never mutated - upgrading
transformers in place could break a working tool for no benefit.

MODEL: RealVisXL V5.0, OpenRAIL++ (commercial use permitted - this is a
monetised channel, and FLUX.1-Fill-dev was rejected specifically because its
licence is NON-COMMERCIAL). No dedicated inpainting checkpoint is needed;
diffusers' own docs state a regular checkpoint plus a mask works, and that
`VaeImageProcessor.apply_overlay()` "force[s] the unmasked area of an image to
remain the same" - which is exactly the invariant this project requires.

THE MASK IS INVERTED FROM THE INTUITION: white = regenerate. We pass the
BACKGROUND as white and the PEOPLE as black, so the people are never denoised.

  python bg_generate.py --frame in.jpg --mask people.png --out room.png
                        [--strength 0.45] [--prompt "..."]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, r"D:\AI-Models\pylibs")

CKPT = Path(r"D:\AI-Models\checkpoints\RealVisXL_V5.0_fp16.safetensors")

# Deliberately plain and photographic. The single biggest risk is the room
# coming back looking obviously AI-generated, which is the one thing this
# niche's practitioners mock by consensus - so this asks for a real room with
# controlled light, not a dramatic illustration.
DEFAULT_PROMPT = (
    "interior of a real courtroom, wood panelling, soft even key light on the "
    "left, gentle falloff into shadow, muted neutral colours, shallow depth of "
    "field, photographic, natural, unremarkable, documentary still"
)
DEFAULT_NEGATIVE = (
    "illustration, cartoon, 3d render, cgi, painting, oversaturated, neon, "
    "glowing, lens flare, hdr, over-sharpened, plastic, artificial, "
    "text, watermark, logo, people, faces, hands"
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", required=True)
    ap.add_argument("--mask", required=True,
                    help="WHITE = regenerate (the room). BLACK = keep (the people).")
    ap.add_argument("--out", required=True)
    ap.add_argument("--strength", type=float, default=0.45,
                    help="how far the room moves from the real one. Low keeps "
                         "the same room and only relights it.")
    ap.add_argument("--steps", type=int, default=30)
    ap.add_argument("--guidance", type=float, default=5.0)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--prompt", default=DEFAULT_PROMPT)
    ap.add_argument("--negative", default=DEFAULT_NEGATIVE)
    a = ap.parse_args()

    if not CKPT.is_file():
        raise SystemExit("checkpoint missing: %s" % CKPT)

    import torch
    from PIL import Image
    from diffusers import StableDiffusionXLInpaintPipeline

    frame = Image.open(a.frame).convert("RGB")
    mask = Image.open(a.mask).convert("L").resize(frame.size, Image.NEAREST)
    W, H = frame.size
    # SDXL wants multiples of 8
    W8, H8 = (W // 8) * 8, (H // 8) * 8
    if (W8, H8) != (W, H):
        frame = frame.resize((W8, H8), Image.LANCZOS)
        mask = mask.resize((W8, H8), Image.NEAREST)

    print("loading %s ..." % CKPT.name, flush=True)
    pipe = StableDiffusionXLInpaintPipeline.from_single_file(
        str(CKPT), torch_dtype=torch.float16, variant="fp16",
        use_safetensors=True)
    pipe = pipe.to("cuda")
    pipe.set_progress_bar_config(disable=True)
    # 16 GB is shared with everything else on this box; slicing keeps headroom
    # 16 GB is shared with everything else on this box; keep headroom. These
    # moved off the pipeline onto the VAE in recent diffusers, so call them
    # where they actually live and never let a missing helper kill the run.
    for fn in (getattr(pipe, "enable_attention_slicing", None),
               getattr(getattr(pipe, "vae", None), "enable_tiling", None),
               getattr(getattr(pipe, "vae", None), "enable_slicing", None)):
        if callable(fn):
            try:
                fn()
            except Exception as exc:
                print("  (skipped %s: %s)" % (getattr(fn, "__name__", fn), exc))

    print("device=%s  size=%dx%d  strength=%.2f  steps=%d"
          % (pipe.device, W8, H8, a.strength, a.steps), flush=True)

    g = torch.Generator(device="cuda").manual_seed(a.seed)
    out = pipe(prompt=a.prompt, negative_prompt=a.negative,
               image=frame, mask_image=mask,
               strength=a.strength, num_inference_steps=a.steps,
               guidance_scale=a.guidance, generator=g,
               width=W8, height=H8).images[0]

    # Force every unmasked pixel back to the original. diffusers documents this
    # as the mechanism for preserving the unmasked area; we do it explicitly
    # rather than trusting the sampler, and bgregen.py then verifies the faces
    # independently.
    out = pipe.image_processor.apply_overlay(mask, frame, out)

    if out.size != (W, H):
        out = out.resize((W, H), Image.LANCZOS)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    out.save(a.out)
    print("GENERATED %s" % a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
