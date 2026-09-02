# -*- coding: utf-8 -*-
"""Video in -> transcript and candidate frames out. Stage 1 of 6.

Two hard rules, both learned the expensive way:

1. REFUSE, never default. A video with no speech and no faces gets an explicit
   refusal with the reason. The temptation is to emit a template anyway so the
   pipeline "works"; that turns every downstream absence result into a lie.
2. Candidate frames are chosen for FACE and EXPRESSION, not for scene change.
   `ffmpeg -vf thumbnail` picks the most statistically AVERAGE frame in a
   window - the mathematical opposite of a frame worth clicking.
"""
import os, json, subprocess, shutil, sys
import numpy as np
import cv2

from . import measure as M   # thumbeng's 133-feature module, not a local copy


class Refused(Exception):
    """The engine cannot honestly work with this input. Carries the reason."""


_YUNET = r"C:/Users/natha/Projects/boyd-clips/models/yunet2023.onnx"


def _faces(bgr, thresh=0.6):
    """FAST PATH only - a bare face count for choosing candidate frames.

    Deliberately NOT thumbeng.measure.measure_file: that computes 133 features
    and is the right tool for scoring a finished thumbnail, but running it over
    ~120 probe frames per video would cost minutes for a number we use to sort.
    The full measurement is still what judges the OUTPUT. Two call sites, one
    authority - this one may never be used to make a claim about a thumbnail.
    """
    h, w = bgr.shape[:2]
    det = cv2.FaceDetectorYN.create(_YUNET, "", (w, h), thresh, 0.3, 5000)
    det.setInputSize((w, h))
    _, f = det.detect(bgr)
    if f is None:
        return []
    raw = [(max(0, int(r[0])), max(0, int(r[1])), int(r[2]), int(r[3]), float(r[-1]))
           for r in f]
    keep = []
    for i, a in enumerate(raw):
        ax, ay, aw, ah = a[:4]
        if any(i != j and b[0] <= ax and b[1] <= ay and
               b[0] + b[2] >= ax + aw and b[1] + b[3] >= ay + ah
               for j, b in enumerate(raw)):
            continue          # YuNet fires inside a face it already found
        keep.append(a)
    return keep


def _ffprobe(video):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration:stream=codec_type,width,height",
         "-of", "json", video],
        capture_output=True, text=True)
    if out.returncode != 0:
        raise Refused(f"ffprobe could not read the file: {out.stderr.strip()[:200]}")
    d = json.loads(out.stdout)
    streams = d.get("streams", [])
    return {
        "duration": float(d.get("format", {}).get("duration", 0.0)),
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
        "width": next((s.get("width") for s in streams
                       if s.get("codec_type") == "video"), 0),
        "height": next((s.get("height") for s in streams
                        if s.get("codec_type") == "video"), 0),
    }


def transcribe(video, out_dir, model_size="small.en"):
    """faster-whisper. Returns [] when there is no audio at all - the caller
    decides whether that is fatal, because for some niches it is not."""
    from faster_whisper import WhisperModel
    wav = os.path.join(out_dir, "_audio.wav")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", video, "-vn",
                    "-ac", "1", "-ar", "16000", wav], check=True)
    try:
        import ctranslate2
        dev = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
    except Exception:
        dev = "cpu"
    ct = "float16" if dev == "cuda" else "int8"
    model = WhisperModel(model_size, device=dev, compute_type=ct)
    segs, _ = model.transcribe(wav, vad_filter=True, word_timestamps=False)
    rows = [{"s": round(s.start, 2), "e": round(s.end, 2), "t": s.text.strip()}
            for s in segs if s.text.strip()]
    try:
        os.remove(wav)
    except OSError:
        pass
    return rows, dev


def candidate_frames(video, out_dir, meta, want=40):
    """Sample widely, then KEEP the frames a thumbnail could actually use.

    Ranked by: a face is present, the face is big, the face is sharp, and the
    frame is not a near-duplicate of one already kept. Scene-change detection
    is deliberately not used - a cut is where the picture changes, not where
    the picture is good.
    """
    fdir = os.path.join(out_dir, "frames")
    os.makedirs(fdir, exist_ok=True)
    for f in os.listdir(fdir):
        os.remove(os.path.join(fdir, f))

    dur = meta["duration"]
    n_probe = max(want * 3, 60)
    times = np.linspace(dur * 0.04, dur * 0.96, n_probe)
    kept, sigs = [], []
    for t in times:
        raw = os.path.join(fdir, "_p.jpg")
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}",
                            "-i", video, "-frames:v", "1", "-q:v", "2", raw],
                           capture_output=True)
        if r.returncode != 0 or not os.path.exists(raw):
            continue
        im = cv2.imread(raw)
        if im is None:
            continue
        fs = _faces(im)
        big = max((w * h for _, _, w, h, _ in fs), default=0)
        g = cv2.cvtColor(cv2.resize(im, (1280, 720), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
        sharp = float(cv2.Laplacian(g, cv2.CV_64F).var())
        sig = cv2.resize(g, (16, 9)).astype(np.float32).ravel()
        sig = (sig - sig.mean()) / (sig.std() + 1e-6)
        # 0.93 was far too aggressive for a LOCKED-OFF camera: on control A
        # (a fixed courtroom cam) it collapsed 72 probes to 7 frames, and the
        # 7 survivors were whatever happened to differ, not whatever was good.
        # A static source is exactly the case where frames differ only by the
        # subject's expression - the thing we are actually shopping for.
        if any(float(np.corrcoef(sig, s)[0, 1]) > 0.985 for s in sigs):
            continue
        sigs.append(sig)
        kept.append({"t": round(float(t), 2), "faces": len(fs),
                     "big_face_px": int(big), "sharpness": round(sharp, 1),
                     "_raw": raw})
    try:
        os.remove(os.path.join(fdir, "_p.jpg"))
    except OSError:
        pass

    # Score: a usable thumbnail frame has a big, sharp face in it. Frames with
    # no face at all are kept at the tail - some niches have no faces and the
    # engine must still have something to work with.
    for k in kept:
        k["score"] = (k["big_face_px"] ** 0.5) * 3.0 + min(k["sharpness"], 900) * 0.4
    kept.sort(key=lambda k: -k["score"])
    kept = kept[:want]

    final = []
    for i, k in enumerate(kept):
        dst = os.path.join(fdir, f"f{i:02d}_t{k['t']:.0f}.jpg")
        # re-extract at full quality rather than re-encoding the probe
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{k['t']:.2f}",
                        "-i", video, "-frames:v", "1", "-q:v", "2", dst],
                       capture_output=True)
        k.pop("_raw", None)
        k["path"] = dst
        final.append(k)
    return final


def run(video, out_dir, model_size="small.en"):
    if not os.path.exists(video):
        raise Refused(f"no such file: {video}")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise Refused("ffmpeg/ffprobe not on PATH")
    os.makedirs(out_dir, exist_ok=True)
    meta = _ffprobe(video)
    if meta["duration"] <= 0:
        raise Refused("video has no duration")

    if meta["has_audio"]:
        rows, dev = transcribe(video, out_dir, model_size)
    else:
        rows, dev = [], "none"

    frames = candidate_frames(video, out_dir, meta)
    words = sum(len(r["t"].split()) for r in rows)
    has_face = any(f["faces"] > 0 for f in frames)

    # THE REFUSAL. Nothing to say and nobody to show is not a thumbnail brief.
    if words < 12 and not has_face:
        raise Refused(
            f"no usable content: {words} transcribed words and no face in any of "
            f"{len(frames)} sampled frames"
            + ("" if meta["has_audio"] else " (file has no audio stream at all)")
            + ". The engine will not emit a default template.")

    doc = {"video": os.path.abspath(video), "meta": meta, "asr_device": dev,
           "transcript": rows, "words": words, "frames": frames,
           "has_face": has_face}
    with open(os.path.join(out_dir, "ingest.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)
    return doc
