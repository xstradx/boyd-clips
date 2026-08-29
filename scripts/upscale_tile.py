"""Upscale a courtroom tile before compositing. Commercially-licensed weights only.

    python scripts/upscale_tile.py in.png out.png [--model general|nomos] [--width W --height H]

Measured on RTX 5080 (sm_120), torch 2.13.0+cu130: 612x338 -> 2448x1352 in 0.27s, 220MB VRAM.
Run SR at the model's native 4x then INTER_AREA down to the target - supersampling beats
upscaling straight to the target size.
"""
import argparse, sys, numpy as np, cv2, torch
from PIL import Image
from pathlib import Path
from spandrel import ModelLoader

MODELS = Path(__file__).resolve().parent.parent / "assets" / "models"
WEIGHTS = {"general": "realesr-general-x4v3.pth",        # BSD-3-Clause, no attribution needed
           "nomos":   "4xNomosWebPhoto_RealPLKSR.pth"}   # CC-BY-4.0, ATTRIBUTION REQUIRED

def upscale(img, model="general", target=None, device="cuda"):
    """img: HWC uint8 RGB -> HWC uint8 RGB."""
    w = MODELS / WEIGHTS[model]
    if not w.exists():
        sys.exit(f"missing weights: {w}  (see assets/models/LICENCES.md)")
    if device == "cuda" and not torch.cuda.is_available():
        device = "cpu"
    net = ModelLoader().load_from_file(str(w)).eval().to(device)
    t = torch.from_numpy(img).float().div(255).permute(2, 0, 1).unsqueeze(0).to(device)
    with torch.no_grad():
        o = net(t)
    o = o.squeeze(0).permute(1, 2, 0).clamp(0, 1).mul(255).round().byte().cpu().numpy()
    del net
    if device == "cuda":
        torch.cuda.empty_cache()
    if target and tuple(target) != o.shape[1::-1]:
        o = cv2.resize(o, tuple(target), interpolation=cv2.INTER_AREA)
    return o

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("src"); p.add_argument("dst")
    p.add_argument("--model", default="general", choices=list(WEIGHTS))
    p.add_argument("--width", type=int); p.add_argument("--height", type=int)
    a = p.parse_args()
    src = np.array(Image.open(a.src).convert("RGB"))
    tgt = (a.width, a.height) if a.width and a.height else None
    out = upscale(src, a.model, tgt)
    Image.fromarray(out).save(a.dst)
    print(f"{a.src} {src.shape[1]}x{src.shape[0]} -> {a.dst} {out.shape[1]}x{out.shape[0]} [{a.model}]")
