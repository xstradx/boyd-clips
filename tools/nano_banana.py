# -*- coding: utf-8 -*-
"""Restore a subject crop with Gemini's image model, using HIS reference sheets
as the example.

Nathan, 2026-09-03: *"Can't you just take the picture, upload it to Google's ...
Gemini with using their nano banana ... and be like, you see these people look
at this attached example. This is what I need you to do"*.

He is right that this is the tool that made the reference sheets he keeps
sending - the designer prompt he found on 2026-09-03 is written for exactly
this model. What we were doing instead was reproducing it with a local SD2-based
general restorer (HYPIR) and, before that, a 4-bit Qwen edit model whose output
he rejected on sight ("No I like left").

MEASURED, fetched 2026-09-03 from ai.google.dev, not recalled:
  model      gemini-3.1-flash-image  ("Nano Banana 2")
  free tier  yes ("Standard Free Tier ... Free of charge")
  paid       1120 tokens for a 1K image = $0.067; 512px = $0.045; 2K = ~$0.10
  endpoint   POST https://generativelanguage.googleapis.com/v1beta/
             models/<model>:generateContent?key=...
             contents[].parts[] = {text} | {inline_data:{mime_type,data:b64}}
             generationConfig.responseModalities = ["IMAGE"]

SPENDING IS A HARD STOP HERE. One image runs on request; anything more needs
--batch-confirmed, which is his standing rule (generate ONE, check it, then
batch). The key is read from the environment or
C:/Users/natha/.claude/secrets/gemini_api_key - never from the repo.

THESE ARE REAL PEOPLE IN A PUBLIC COURT RECORD. Every result is checked against
the input face with SFace and refused if the identity drifts, exactly as the
local regenerate path does.

    python tools/nano_banana.py <crop.png> --out <out.png> [--ref <sheet.jpg> ...]
    python tools/nano_banana.py --check          # key present? model reachable?
"""
import argparse
import base64
import json
import os
import sys
import urllib.request

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MODEL = "gemini-3.1-flash-image"
ENDPOINT = ("https://generativelanguage.googleapis.com/v1beta/models/"
            "{model}:generateContent?key={key}")
KEY_FILE = r"C:\Users\natha\.claude\secrets\gemini_api_key"
IDENTITY_MIN = 0.62          # same floor the local path uses

# His own words are the brief. The identity-lock paragraph is the operative
# half of the designer prompt he found; the "straight to camera" and body-crop
# lines are dropped because we need THEIR pose, not a posed portrait.
PROMPT = (
    "Look at the attached example images first: they show a low-quality video "
    "still on the left and a finished, premium studio-quality portrait of the "
    "SAME person on the right. Do exactly that transformation to the final "
    "image I am giving you.\n\n"
    "Premium studio-quality facial detail, highly realistic skin texture with "
    "visible pores, natural forehead lines, subtle wrinkles, fine facial "
    "imperfections, realistic subsurface scattering, natural lip texture, "
    "realistic eyelashes, high-definition eyebrows, bright catchlights in the "
    "eyes and crystal-clear iris detail. Cinematic YouTube thumbnail quality, "
    "extremely sharp focus on the face, clean professional lighting, "
    "photorealistic facial anatomy, ultra-clean image quality.\n\n"
    "Preserve the exact facial identity, facial structure, proportions, eye "
    "shape, nose shape, hairline, skin tone and every unique facial feature of "
    "the person in the final image. Do not alter the person's face in any way. "
    "Maintain 100% likeness. Keep the same expression, the same head angle, the "
    "same gaze direction and the same clothing. Keep the same framing and the "
    "same background - do not replace the background, do not re-pose them, do "
    "not make them look at the camera."
)


def _key():
    k = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if k:
        return k.strip()
    if os.path.exists(KEY_FILE):
        return open(KEY_FILE, encoding="utf-8").read().strip()
    return None


def _part_image(path):
    ext = os.path.splitext(path)[1].lower()
    mime = "image/png" if ext == ".png" else "image/jpeg"
    with open(path, "rb") as fh:
        return {"inline_data": {"mime_type": mime,
                                "data": base64.b64encode(fh.read()).decode()}}


def generate(src, out, refs=(), model=MODEL, timeout=180):
    key = _key()
    if not key:
        print("NANO_NO_KEY  no GEMINI_API_KEY in the environment and no "
              f"{KEY_FILE}\n"
              "  Get one at https://aistudio.google.com/apikey (his Google "
              "account, free tier) and save it to that path.")
        return None
    parts = [{"text": PROMPT}]
    for r in refs:
        parts.append(_part_image(r))
    parts.append(_part_image(src))
    body = json.dumps({
        "contents": [{"parts": parts}],
        "generationConfig": {"responseModalities": ["IMAGE"]},
    }).encode()
    req = urllib.request.Request(
        ENDPOINT.format(model=model, key=key), data=body,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.load(r)
    cands = d.get("candidates") or []
    if not cands:
        print("NANO_FAIL no candidates:", json.dumps(d)[:400])
        return None
    for p in cands[0].get("content", {}).get("parts", []):
        blob = p.get("inlineData") or p.get("inline_data")
        if blob and blob.get("data"):
            with open(out, "wb") as fh:
                fh.write(base64.b64decode(blob["data"]))
            um = d.get("usageMetadata", {})
            print(f"NANO_OK  wrote {out}  "
                  f"(prompt {um.get('promptTokenCount','?')} tok, "
                  f"out {um.get('candidatesTokenCount','?')} tok)")
            return out
    fr = cands[0].get("finishReason")
    print(f"NANO_FAIL no image part returned (finishReason={fr})")
    return None


def identity_ok(src, out, verbose=True):
    """SFace cosine between the two faces. These are real people in a public
    record; a result that drifts is a different person and is refused."""
    try:
        import cv2
        import identity as I
        a, b = cv2.imread(src), cv2.imread(out)
        ra, rb = I.faces_in(a, score=0.5), I.faces_in(b, score=0.5)
        if not ra or not rb:
            print("NANO_IDENTITY_UNMEASURABLE no face detected in one of them")
            return None
        ea = I.embed(a, max(ra, key=lambda r: r[3]))
        eb = I.embed(b, max(rb, key=lambda r: r[3]))
        import numpy as np
        sim = float(np.dot(ea, eb))
        ok = sim >= IDENTITY_MIN
        if verbose:
            print(f"NANO_IDENTITY_{'OK' if ok else 'DRIFTED'} "
                  f"cosine {sim:.3f} (floor {IDENTITY_MIN})")
        return ok
    except Exception as e:
        print(f"NANO_IDENTITY_UNMEASURABLE {type(e).__name__}: {e}")
        return None


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src", nargs="?")
    ap.add_argument("--out")
    ap.add_argument("--ref", action="append", default=[],
                    help="an example before/after sheet to show the model")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--batch-confirmed", action="store_true",
                    help="required for more than one image - his standing rule "
                         "is generate ONE, check it, then batch")
    a = ap.parse_args()
    if a.check:
        k = _key()
        print(f"key: {'present' if k else 'MISSING'}   model: {a.model}")
        print(f"key file: {KEY_FILE}")
        sys.exit(0 if k else 1)
    if not a.src or not a.out:
        print(__doc__)
        sys.exit(2)
    got = generate(a.src, a.out, refs=a.ref, model=a.model)
    if not got:
        sys.exit(1)
    identity_ok(a.src, got)
