# Upscaler weights shipped here - commercial-use status

## realesr-general-x4v3.pth  -- RECOMMENDED DEFAULT
- Source: https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-general-x4v3.pth
- Repo: https://github.com/xinntao/Real-ESRGAN  (BSD-3-Clause, no carve-outs, verified by reading LICENSE)
- Commercial use: YES. No attribution required beyond retaining the BSD-3 copyright notice.

## 4xNomosWebPhoto_RealPLKSR.pth  -- optional, more aggressive
- Source: https://github.com/Phhofm/models/releases/download/4xNomosWebPhoto_RealPLKSR/4xNomosWebPhoto_RealPLKSR.pth
- Author: Philip Hofmann. Licence: CC-BY-4.0 (per openmodeldb.info entry 4x-NomosWebPhoto-RealPLKSR)
- Commercial use: YES **with attribution**. If used, credit "4xNomosWebPhoto_RealPLKSR by Philip Hofmann (CC BY 4.0)".
- Provenance flag: trained on Nomos-v2, which neosr's readme states is distilled from 14+ datasets
  *including FFHQ* (FFHQ dataset itself is CC BY-NC-SA 4.0). Publisher declares CC-BY-4.0 on the weights.

## DO NOT USE on this channel (all verified by reading the licence text)
- CodeFormer  -- S-Lab License 1.0: "Redistribution and use for non-commercial purpose".
- GFPGAN      -- LICENSE says "Apache ... except for the third-party components listed below";
                 StyleGAN2 component carries the NVIDIA licence s3.3 "only may be used ...
                 non-commercially"; DFDNet component is CC BY-NC-SA 4.0.
- 4xFaceUpDAT / 4xFFHQDAT -- author's own release note: "License: free use, redistribution, and
                 adaptation for non-commercial purposes - check Lincense(s) of FFHQ".
- rembg default weights (u2net / bria-rmbg) -- CC BY-NC 4.0. Only birefnet-* are MIT.
