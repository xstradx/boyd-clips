"""realesr-general-x4v3 (SRVGGNetCompact) forward pass, self-contained.

Licence: Real-ESRGAN is BSD-3-Clause (xinntao/Real-ESRGAN). The weights file
assets/models/realesr-general-x4v3.pth ships under that licence. Commercial use
permitted. This module reimplements the 60-line SRVGGNetCompact architecture so
the build does not depend on basicsr/realesrgan (neither is installed here).
"""
import torch, torch.nn as nn, torch.nn.functional as F, numpy as np, cv2

class SRVGG(nn.Module):
    def __init__(self, nf=64, nc=32, scale=4):
        super().__init__()
        self.scale = scale
        b = [nn.Conv2d(3, nf, 3, 1, 1), nn.PReLU(nf)]
        for _ in range(nc):
            b += [nn.Conv2d(nf, nf, 3, 1, 1), nn.PReLU(nf)]
        b += [nn.Conv2d(nf, 3 * scale * scale, 3, 1, 1)]
        self.body = nn.Sequential(*b)

    def forward(self, x):
        out = self.body(x)
        out = F.pixel_shuffle(out, self.scale)
        return out + F.interpolate(x, scale_factor=self.scale, mode='nearest')

_NET = None
def _net(path):
    global _NET
    if _NET is None:
        sd = torch.load(path, map_location='cpu')
        sd = sd.get('params', sd)
        n = SRVGG()
        n.load_state_dict(sd, strict=True)
        n.eval()
        _NET = n
    return _NET

@torch.no_grad()
def upscale(bgr, weights, out_w, out_h):
    """4x through the net, then Lanczos down to the exact target size."""
    n = _net(weights)
    x = torch.from_numpy(bgr[:, :, ::-1].copy()).float().div(255).permute(2, 0, 1)[None]
    y = n(x)[0].clamp(0, 1).permute(1, 2, 0).numpy()[:, :, ::-1]
    y = (y * 255).round().astype(np.uint8)
    return cv2.resize(y, (out_w, out_h), interpolation=cv2.INTER_LANCZOS4)
