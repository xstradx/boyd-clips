# -*- coding: utf-8 -*-
"""Word timings for a rendered cut, measured on the cut itself.

The editor hands the engine a video id and source-second segments. Captions
need word starts and ends in the OUTPUT's clock. The transcripts on disk
(`work/<vid>/<vid>.transcript.json`) carry YouTube word STARTS only, in the
source clock, so building a word list from them means inventing every end
time and mapping through the cut - two of the three earlier gate_cuts
versions were wrong for exactly that class of reason (short_engine.gate_cuts
docstring). Running the aligner over the finished cut gives both numbers in
the one clock that matters, with no mapping.

This is how OFFERUP V7's `v4_words.json` was made on 2026-08-31, by hand.
Now it is a step.

    python tools/align_words.py CUT.mp4 OUT_words.json [--model large-v3]
    python tools/align_words.py --jitter CUT.mp4     # measure the aligner's
                                                     # own timing noise
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

# NO initial_prompt. Measured 2026-09-01 on OFFERUP v4_full.mp4 (38.6s, 136
# words): with a one-sentence courtroom prompt, large-v3 on CUDA returned the
# PROMPT TEXT twice as the transcript - 36 words, mean probability 0.00.
# Without it: 136 words, mean probability 0.95, identical on cuda and cpu.
# scripts/caption_edit.py still passes a prompt; that is its risk to carry.
PROMPT = None


def _model(model_size):
    from faster_whisper import WhisperModel
    device, compute = "cpu", "int8"
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            device, compute = "cuda", "float16"
    except Exception:                                  # noqa: BLE001
        pass
    try:
        return WhisperModel(model_size, device=device, compute_type=compute), device
    except Exception as exc:                           # noqa: BLE001
        if device == "cuda":
            print(f"  cuda unusable ({str(exc)[:60]}) - falling back to cpu")
            return WhisperModel(model_size, device="cpu", compute_type="int8"), "cpu"
        raise


def align(media, out_json=None, model_size="large-v3", verbose=True, _m=None):
    """[{s, e, w, p}] in the media's own clock. Writes out_json if given."""
    m, dev = _m or _model(model_size)
    if verbose:
        print(f"  align_words: {model_size} on {dev} -> {os.path.basename(media)}")
    segs, _ = m.transcribe(media, language="en", word_timestamps=True,
                           vad_filter=True, beam_size=5, initial_prompt=PROMPT)
    words = []
    for s in segs:
        for w in (s.words or []):
            tok = w.word.strip()
            if tok:
                words.append({"s": round(float(w.start), 3),
                              "e": round(float(w.end), 3),
                              "w": tok, "p": round(float(w.probability), 3)})
    if out_json:
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(words, f, indent=1)
    if verbose:
        print(f"  align_words: {len(words)} words"
              + (f" -> {os.path.basename(out_json)}" if out_json else ""))
    return words


def jitter(media, model_size="large-v3", shift=0.37, verbose=True):
    """How much the aligner's word starts move when the SAME audio is offset.

    The same words in the same audio, shifted by a known amount, should come
    back shifted by exactly that amount. Whatever they come back shifted by
    instead is the aligner's own noise, and that is the only honest tolerance
    for a gate that compares a drawn caption time to a spoken-word time.
    Returns (n_matched, mean_abs, p95_abs, max_abs) in seconds.
    """
    m, dev = _model(model_size)
    a = align(media, model_size=model_size, verbose=False, _m=(m, dev))
    with tempfile.TemporaryDirectory() as d:
        wav = os.path.join(d, "shifted.wav")
        ms = int(round(shift * 1000))
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", media, "-vn",
                        "-af", f"adelay={ms}|{ms}", "-ac", "1", "-ar", "16000",
                        wav], check=True)
        b = align(wav, model_size=model_size, verbose=False, _m=(m, dev))
    # match by normalised text with difflib, so a token the second pass
    # dropped or merged does not desynchronise every word after it (the first
    # one-token-lookahead matcher lost 122 of 136 OFFERUP words that way)
    import difflib

    def norm(w):
        return "".join(ch for ch in w.lower() if ch.isalnum())
    ta, tb = [norm(x["w"]) for x in a], [norm(x["w"]) for x in b]
    ds = []
    for tag, i0, i1, j0, j1 in difflib.SequenceMatcher(None, ta, tb, autojunk=False).get_opcodes():
        if tag != "equal":
            continue
        for i, j in zip(range(i0, i1), range(j0, j1)):
            ds.append(abs((b[j]["s"] - shift) - a[i]["s"]))
    if not ds:
        return 0, None, None, None
    ds.sort()
    mean = sum(ds) / len(ds)
    p95 = ds[min(len(ds) - 1, int(0.95 * len(ds)))]
    if verbose:
        print(f"  jitter {model_size} shift={shift}s: {len(ds)}/{len(a)} words matched, "
              f"mean |d|={mean:.3f}s  p95={p95:.3f}s  max={ds[-1]:.3f}s")
    return len(ds), mean, p95, ds[-1]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("media")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--model", default="large-v3")
    ap.add_argument("--jitter", action="store_true")
    ap.add_argument("--shift", type=float, default=0.37)
    a = ap.parse_args()
    if a.jitter:
        n, mean, p95, mx = jitter(a.media, a.model, a.shift)
        sys.exit(0 if n else 1)
    if not a.out:
        print("usage: align_words.py CUT.mp4 OUT_words.json | --jitter CUT.mp4")
        sys.exit(2)
    align(a.media, a.out, a.model)
