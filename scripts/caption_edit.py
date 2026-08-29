"""Transcribe a finished cut properly, and work out who is speaking.

The captions on this channel have been wrong twice over, and both faults are
separate:

  TEXT - YouTube's auto-captions are inaccurate on courtroom audio. Fixed here
  with faster-whisper, run over the edit itself so the timings are already in
  the edit's own clock and no mapping is needed.

  SPEAKER - the old attribution used lexical tells and was measured wrong: a
  riff Boyd dominates came back 29 defendant lines against 6 of hers. There is
  no diarization model on this machine, but this material does not need one.
  The frame is a two-tile stack, defendant over judge, so whoever is MOVING is
  speaking. Per-tile temporal variance across a caption's span is a direct
  measurement of that, and it cannot be fooled by vocabulary.

Writes an ASS subtitle file with the defendant's lines above the centre line and
the judge's below, which is how Nathan asked for it.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SPEAKER_SYSTEM = """You label who is speaking in a court hearing transcript.

Two people: the JUDGE (Stephanie Boyd, 187th District Court, Bexar County) and
the DEFENDANT appearing before her. Occasionally a lawyer, whom you should label
as the defendant's side.

The judge asks the questions, explains the law, lectures, scolds, and announces
what the court will do. The defendant answers, explains, and makes excuses. A
line that questions or admonishes is hers; a line that answers or justifies is
his. Announcements of conditions and sentences are always hers.

You are given each line in order with its timecode, plus a weak motion hint from
the video: which tile moved more while the line was spoken. The hint is often
wrong, because both faces are on camera the whole time and the listener nods -
use it only to break a genuine tie, never against the sense of the words.

Return one label per line, in order, for every line you are given."""

SPEAKER_SCHEMA = {
    "type": "object", "required": ["lines"],
    "properties": {"lines": {"type": "array", "items": {
        "type": "object", "required": ["i", "who"],
        "properties": {"i": {"type": "integer"},
                       "who": {"type": "string"},
                       "why": {"type": "string"}}}}}}


def attribute_by_text(segs: list, model: str = "claude-opus-5") -> bool:
    """Label speakers from the words. Returns False if the model is unavailable.

    Motion alone was measured wrong on 6 of 16 lines of this edit - the judge
    lecturing while the defendant nods looks identical to the reverse. The words
    are unambiguous where the pixels are not.
    """
    from boydclips.llm import ClaudeCliBackend
    lines = []
    for i, s in enumerate(segs):
        hint = "top(defendant)" if s.get("who") == "D" else "bottom(judge)"
        lines.append(f"[{i}] {s['a']:.1f}s  (motion hint: {hint})  {s['text']}")
    try:
        be = ClaudeCliBackend(model=model, timeout_s=600)
        out = be.complete(SPEAKER_SYSTEM, chr(10).join(lines), SPEAKER_SCHEMA, "speakers")
    except Exception as exc:                            # noqa: BLE001
        print(f"  speaker model unavailable ({str(exc)[:70]})")
        return False
    got = {r["i"]: r for r in out.get("lines", []) if 0 <= r.get("i", -1) < len(segs)}
    if len(got) < len(segs) * 0.8:
        print(f"  model labelled only {len(got)}/{len(segs)} lines - keeping motion")
        return False
    for i, s in enumerate(segs):
        r = got.get(i)
        if not r:
            continue
        w = str(r.get("who", "")).strip().lower()
        new = "B" if w.startswith("j") or w.startswith("b") else "D"
        s["motionWho"] = s.get("who")
        s["who"] = new
        if r.get("why"):
            s["whoWhy"] = r["why"]
    return True


def ass_time(t: float) -> str:
    if t < 0:
        t = 0.0
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def transcribe(path: Path, model_size: str) -> list:
    from faster_whisper import WhisperModel

    # ask CTranslate2, not torch: faster-whisper runs on CTranslate2, and this
    # machine has a CPU-only torch build alongside a working CUDA runtime, so
    # torch.cuda.is_available() says False on a box with an RTX 5080 in it
    device, compute = "cpu", "int8"
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            device, compute = "cuda", "float16"
    except Exception:                                  # noqa: BLE001
        pass
    prompt = ("A Texas criminal district court hearing. Judge Stephanie Boyd "
              "speaks with a defendant about probation, community supervision, "
              "restitution and a pet spider monkey.")

    def run(dev: str, ct: str):
        print(f"  whisper {model_size} on {dev}")
        model = WhisperModel(model_size, device=dev, compute_type=ct)
        segs, _ = model.transcribe(
            str(path), language="en", word_timestamps=True,
            vad_filter=True, beam_size=5, initial_prompt=prompt)
        return list(segs)                     # force it here so a CUDA fault
                                              # surfaces now, not mid-iteration

    try:
        segs = run(device, compute)
    except Exception as exc:                  # noqa: BLE001
        # ctranslate2 loads a CUDA model happily and only fails on the first
        # encode, when cuBLAS turns out to be missing. Fall back rather than
        # ask for a CUDA install to caption a minute of audio.
        if device == "cuda":
            print(f"  cuda unusable ({str(exc)[:60]}) - falling back to cpu")
            segs = run("cpu", "int8")
        else:
            raise
    out = []
    for s in segs:
        words = [{"w": w.word.strip(), "a": w.start, "b": w.end}
                 for w in (s.words or []) if w.word.strip()]
        if words:
            out.append({"a": s.start, "b": s.end, "text": s.text.strip(), "words": words})
    return out


def activity_series(path: Path, dur: float, step: float = 0.25) -> tuple:
    """Per-tile motion over the whole file, as two time series.

    Three things this gets right that the naive version did not:

      * metadata=print writes at INFO level, so running ffmpeg with -v error
        silently discarded every value and the first attempt scored 0.0000 for
        every line. It writes to stdout here instead.
      * one pass per tile over the whole file, not one per caption.
      * each tile is judged against ITS OWN baseline. The two tiles have
        different lighting, compression and grain, so their raw motion numbers
        are not comparable - only "how active is this tile compared to how it
        usually looks" is.

    The crop excludes the outer edges of each tile: the defendant's tile carries
    a B-roll insert in the top-right corner in this edit, and a static overlay
    would otherwise read as an absence of motion.
    """
    def series(half: str) -> list:
        y0 = "0" if half == "top" else "ih/2"
        # centre 70% of the tile, where a face is
        crop = f"iw*0.7:ih/2*0.68:iw*0.15:{y0}+ih/2*0.16"
        r = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(path), "-vf",
             f"fps=1/{step},crop={crop},scale=192:-2,format=gray,"
             f"tblend=all_mode=difference,signalstats,metadata=print:file=-",
             "-an", "-f", "null", "-"],
            capture_output=True, text=True, timeout=1800)
        vals = []
        for line in (r.stdout or "").splitlines():
            if "YAVG" in line:
                try:
                    vals.append(float(line.split("=")[-1]))
                except ValueError:
                    pass
        return vals

    return series("top"), series("bottom")


def _baseline(vals: list) -> float:
    if not vals:
        return 0.0
    srt = sorted(vals)
    return srt[len(srt) // 2] or 1e-6


def attribute(segs: list, top: list, bot: list, step: float = 0.25) -> None:
    """Mark each line D or B by which tile is most above its own baseline."""
    tb, bb = _baseline(top), _baseline(bot)
    for s in segs:
        i0 = max(0, int(s["a"] / step))
        i1 = max(i0 + 1, int(s["b"] / step))
        t = top[i0:i1] or [0.0]
        b = bot[i0:i1] or [0.0]
        # relative lift over each tile's own typical level
        tl = (sum(t) / len(t)) / tb
        bl = (sum(b) / len(b)) / bb
        s["topLift"], s["botLift"] = round(tl, 3), round(bl, 3)
        s["who"] = "D" if tl >= bl else "B"
        s["conf"] = round(abs(tl - bl) / max(tl + bl, 1e-6), 3)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True, help="the finished cut to caption")
    ap.add_argument("--model", default="medium.en",
                    help="faster-whisper size: small.en / medium.en / large-v3")
    ap.add_argument("--out", default=None, help="where to write the .ass")
    ap.add_argument("--json", default=None, help="also dump the transcript as json")
    args = ap.parse_args()

    src = Path(args.file)
    if not src.exists():
        print("no such file: " + str(src))
        return

    print(f"transcribing {src.name}")
    segs = transcribe(src, args.model)
    print(f"  {len(segs)} segments, {sum(len(s['words']) for s in segs)} words")

    print("measuring which tile is moving ...")
    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(src)], capture_output=True, text=True).stdout.strip() or 0)
    top, bot = activity_series(src, dur)
    print(f"  {len(top)} samples top, {len(bot)} bottom")
    if not top or not bot:
        print("  MEASUREMENT FAILED - refusing to guess the speaker")
        return
    attribute(segs, top, bot)
    motion_call = [s["who"] for s in segs]
    print("labelling speakers from the words ...")
    if attribute_by_text(segs):
        flips = sum(1 for a, s in zip(motion_call, segs) if a != s["who"])
        print(f"  the words overruled the motion hint on {flips} of {len(segs)} lines")

    d = sum(1 for s in segs if s["who"] == "D")
    print(f"  defendant {d}, judge {len(segs)-d}")
    weak = [s for s in segs if s["conf"] < 0.08]
    if weak:
        print(f"  {len(weak)} lines were close to call (under 8% difference)")

    if args.json:
        Path(args.json).write_text(json.dumps(segs, indent=1), encoding="utf-8")
        print("  transcript -> " + args.json)

    dest = Path(args.out) if args.out else src.with_suffix(".ass")
    w, h = 1080, 1920
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: D,Arial,76,&H00FFFFFF,&H00101010,&H90000000,-1,1,5,2,2,60,60,{int(h*0.5)+30},1
Style: B,Arial,76,&H0000E6FF,&H00101010,&H90000000,-1,1,5,2,8,60,60,{int(h*0.5)+30},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for s in segs:
        txt = s["text"].replace("\\n", " ").strip()
        if not txt:
            continue
        # keep captions short enough to read at a glance
        chunks, cur = [], ""
        for word in txt.split():
            if len(cur) + len(word) + 1 > 42:
                chunks.append(cur)
                cur = word
            else:
                cur = (cur + " " + word).strip()
        if cur:
            chunks.append(cur)
        span = max(0.4, s["b"] - s["a"]) / max(1, len(chunks))
        for i, c in enumerate(chunks):
            a = s["a"] + i * span
            b = a + span
            lines.append(f"Dialogue: 0,{ass_time(a)},{ass_time(b)},{s['who']},,0,0,0,,"
                         + c.replace("{", "").replace("}", ""))

    dest.write_text(head + "\n".join(lines) + "\n", encoding="utf-8")
    print(f"  subtitles -> {dest}  ({len(lines)} lines)")
    print("\ndefendant is white and sits ABOVE the centre line; "
          "the judge is yellow and sits BELOW it.")


if __name__ == "__main__":
    main()
