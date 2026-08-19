#!/usr/bin/env python
"""align_chars.py - character-level forced alignment, so accent placement can be
measured against real syllable boundaries instead of guessed ones.

WHY: contour_shape.py's accent metric has to answer "did the pitch peak land on
the stressed syllable of Bexar / 187th / Castillo?". That needs syllable
boundaries. Counting intensity nuclei does not supply them - on ek3_open.wav the
nucleus count disagreed with the CMUdict syllable count for 61 of 76 candidate
words, so 80% of the metric was discarded and the human narrator scored 0.50.

torchaudio 2.10.0+cu128 ships torchaudio.functional.forced_align and the MMS_FA
bundle (CTC alignment, multilingual romanized, 28 labels). Verified present:
  C:/AI/comfyui_env/Scripts/python.exe -c "import torchaudio.functional as F; print(F.forced_align)"
That env has torch 2.10.0+cu128 with cuda True (sm_120). The Python312 install
CANNOT be used: its torchaudio fails to load libtorchaudio.pyd.

RUN (comfyui_env interpreter, NOT Python312):
  C:/AI/comfyui_env/Scripts/python.exe align_chars.py ek3_open.wav
Writes <stem>_chars.json: [{"w": word, "s":..., "e":..., "chars":[[ch,s,e],...]}]
contour_shape.py picks that sidecar up automatically if it exists.
"""
import json, os, sys, re
import torch, torchaudio
from torchaudio.pipelines import MMS_FA as BUNDLE


def norm(w):
    return re.sub(r"[^a-z']", "", w.strip().lower())


def main(wav, words_json=None):
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    if not words_json:
        stem = os.path.splitext(wav)[0]
        for c in (stem + "_words.json", stem.rsplit("_", 1)[0] + "_words.json"):
            if os.path.exists(c):
                words_json = c; break
    if not words_json:
        raise SystemExit("no _words.json sidecar for " + wav)
    W = json.load(open(words_json))
    # MMS_FA's label set is romanized letters only; digits and punctuation have
    # no token, so they are spelled out before alignment and mapped back after.
    NUM = {"0": "zero", "1": "one", "2": "two", "3": "three", "4": "four",
           "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine"}
    toks, keep = [], []
    for i, x in enumerate(W):
        k = re.sub(r"[^a-z0-9']", "", x["w"].strip().lower())
        if not k:
            continue
        k = "".join(NUM.get(c, c) for c in k)
        if not k:
            continue
        toks.append(k); keep.append(i)

    # torchaudio 2.10 routes torchaudio.load through TorchCodec, which is not
    # installed; librosa reads and resamples without it.
    import librosa
    y, sr = librosa.load(wav, sr=BUNDLE.sample_rate, mono=True)
    wave = torch.from_numpy(y)[None]

    model = BUNDLE.get_model().to(dev)
    tokenizer = BUNDLE.get_tokenizer()
    aligner = BUNDLE.get_aligner()
    with torch.inference_mode():
        emission, _ = model(wave.to(dev))
        spans = aligner(emission[0], tokenizer(toks))
    ratio = wave.shape[1] / emission.shape[1] / sr   # seconds per emission frame

    out = []
    for n, i in enumerate(keep):
        sp = spans[n]
        ch = [[BUNDLE.get_dict() and t.token, round(t.start * ratio, 4), round(t.end * ratio, 4)]
              for t in sp]
        # token ids -> characters
        labels = BUNDLE.get_labels() if hasattr(BUNDLE, "get_labels") else None
        chars = []
        for t, c in zip(sp, toks[n]):
            chars.append([c, round(t.start * ratio, 4), round(t.end * ratio, 4)])
        out.append(dict(w=W[i]["w"], i=i, s=round(sp[0].start * ratio, 4),
                        e=round(sp[-1].end * ratio, 4), spelled=toks[n], chars=chars))
    dst = os.path.splitext(wav)[0] + "_chars.json"
    json.dump(out, open(dst, "w"), indent=0)
    print("wrote", dst, len(out), "words, device", dev)
    # sanity: alignment must track the ASR word times, or the mapping is wrong
    import numpy as np
    d = [abs(o["s"] - W[o["i"]]["s"]) for o in out]
    print("median |align_start - asr_start| = %.3f s, p90 = %.3f s"
          % (float(np.median(d)), float(np.percentile(d, 90))))


if __name__ == "__main__":
    main(*sys.argv[1:])
