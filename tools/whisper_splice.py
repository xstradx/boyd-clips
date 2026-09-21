"""Re-transcribe ONE case span with faster-whisper and splice it into the
docket's cached transcript.

    python tools/whisper_splice.py <video_id> <start_s> <end_s> [--model large-v3-turbo] [--pad 8]

Why (2026-09-06): the 2024 dockets' auto-captions are the old lowercase,
unpunctuated kind and they are garbled where it matters - Alonzo's short
would have burned in "do you SOLLY swear", "for a SPOTED S judge", "we WAVE
the other violations". Captions must be what was said (CONTENT_SPEC §5), so
the case's own span is transcribed again from the fetched docket audio
(work/<vid>/<vid>.full.mp4) with word timestamps, and those words replace
the auto-caption words inside [start-pad, end+pad]. Everything outside the
span is untouched, the timeline is the same audio clock, and the original
file is kept beside it as <vid>.transcript.autocaps.json (first splice only).
The store rows, hook and money-moment timestamps stay valid.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boydclips.render import full_docket_path            # noqa: E402
from boydclips.transcribe import Transcript, Word, apply_phrase_fixes  # noqa: E402


def transcribe_span(audio_src: Path, start_s: float, end_s: float, model: str,
                    threads: int = 8) -> list[Word]:
    from faster_whisper import WhisperModel
    with tempfile.TemporaryDirectory(prefix="boyd-whisper-") as td:
        wav = Path(td) / "span.wav"
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                        "-ss", f"{start_s:.3f}", "-i", str(audio_src), "-t", f"{end_s - start_s:.3f}",
                        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)], check=True)
        wm = WhisperModel(model, device="cpu", compute_type="int8", cpu_threads=threads)
        segments, info = wm.transcribe(str(wav), word_timestamps=True, language="en", beam_size=5,
                                       condition_on_previous_text=False, vad_filter=False)
        words: list[Word] = []
        for seg in segments:
            for w in (seg.words or []):
                tok = w.word.strip()
                if tok:
                    words.append(Word(t=round(start_s + float(w.start), 3), w=tok))
    return words


def merge_apostrophes(words: list[Word]) -> tuple[list[Word], int]:
    """faster-whisper sometimes emits a contraction as two tokens ("y" +
    "'all", "ma" + "'am.", "5" + "'10\","). A token that starts with an
    apostrophe belongs to the word before it; the earlier start time is kept."""
    out: list[Word] = []
    merged = 0
    for w in words:
        if out and w.w[:1] in ("'", "’") and len(w.w) > 1:
            out[-1] = Word(t=out[-1].t, w=out[-1].w + w.w)
            merged += 1
        else:
            out.append(w)
    return out, merged


def splice(video_id: str, start_s: float, end_s: float, model: str = "large-v3-turbo", pad: float = 8.0) -> dict:
    work = ROOT / "work" / video_id
    tpath = work / f"{video_id}.transcript.json"
    backup = work / f"{video_id}.transcript.autocaps.json"
    full = full_docket_path(video_id, work)
    if not full.exists():
        raise SystemExit(f"no fetched docket at {full}; run tools/fetch_docket.py {video_id}")
    tr = Transcript.from_json(tpath.read_text(encoding="utf-8"))
    lo, hi = max(0.0, start_s - pad), end_s + pad
    t0 = time.time()
    new = transcribe_span(full, lo, hi, model)
    new, fixed = apply_phrase_fixes(new)
    new, joined = merge_apostrophes(new)
    took = time.time() - t0
    before = [w for w in tr.words if lo <= w.t <= hi]
    kept = [w for w in tr.words if not (lo <= w.t <= hi)]
    merged = sorted(kept + new, key=lambda w: w.t)
    if not backup.exists():
        backup.write_text(tpath.read_text(encoding="utf-8"), encoding="utf-8")
    src = tr.source if "whisper" in tr.source else f"{tr.source}+whisper:{model}"
    out = Transcript(video_id=video_id, words=merged, source=f"{src}@{int(lo)}-{int(hi)}")
    tpath.write_text(out.to_json(), encoding="utf-8")
    rep = {"video_id": video_id, "span": [lo, hi], "model": model, "seconds": round(took, 1),
           "auto_words_replaced": len(before), "whisper_words": len(new), "phrase_fixes": fixed, "apostrophes_joined": joined,
           "sample": " ".join(w.w for w in new[:40])}
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    return rep


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video_id")
    ap.add_argument("start_s", type=float)
    ap.add_argument("end_s", type=float)
    ap.add_argument("--model", default="large-v3-turbo")
    ap.add_argument("--pad", type=float, default=8.0)
    a = ap.parse_args()
    splice(a.video_id, a.start_s, a.end_s, a.model, a.pad)
    return 0


if __name__ == "__main__":
    sys.exit(main())
