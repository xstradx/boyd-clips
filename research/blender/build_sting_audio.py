"""Assemble the v2 sting audio from the real CC0 recordings.

Pure stdlib (no numpy on this machine). Everything is placed against the SAME
frame numbers sting_v2.py animates to, so picture and sound cannot drift apart.

Three decisions here come from measurement rather than convention:

  * The gavel is a real recording, not synthesis. Its two blows are 322 ms apart
    and within 1.1 dB of each other. The "second strike is quieter" bounce model
    is wrong for a deliberate double strike — a judge is not a dropped ball.
    So we align the recording to the picture rather than editing its internals.

  * Recorded whooshes are pass-bys: they peak mid-flight and decay symmetrically,
    carrying 32-72% of their energy AFTER the peak (measured across 8 files). A
    letterform that slams to a stop needs the sound to END on arrival, so each
    whoosh is trimmed just past its peak with a fast fade. Real source, re-shaped.

  * Whoosh peaks land ~15 ms BEFORE the element arrives. ITU-R BT.1359 puts
    detectability at 45 ms early against 125 ms late, so 15 ms early is safely
    inside the window and reads as anticipation rather than as an error.

Run:  python research/blender/build_sting_audio.py
"""
from __future__ import annotations

import math
import struct
import subprocess
import wave
from pathlib import Path

SR = 48000
FPS = 30
ROOT = Path(__file__).resolve().parents[2]
SFX = ROOT / "assets" / "sfx" / "clean"
OUT = Path(__file__).resolve().parent / "renders" / "sting_v2.wav"

# frame numbers, 1-based, matching sting_v2.py exactly
F_LAND = (7, 12, 17)
F_HIT1, F_HIT2 = 26, 36
F_STAR_LAUNCH, F_STAR_LAND = 36, 54
F_END = 78

LEAD_MS = 15.0            # whoosh peaks this far before arrival


def f2t(frame: int) -> float:
    return (frame - 1) / FPS


def read_wav(p: Path) -> list[float]:
    with wave.open(str(p), "rb") as w:
        assert w.getframerate() == SR and w.getnchannels() == 1
        n = w.getnframes()
        return [v / 32768.0 for v in struct.unpack(f"<{n}h", w.readframes(n))]


def envelope_peak(d: list[float], win_ms: float = 5.0) -> int:
    win = int(win_ms / 1000 * SR)
    best, bi = -1.0, 0
    for i in range(0, len(d) - win, win):
        e = math.sqrt(sum(v * v for v in d[i:i + win]) / win)
        if e > best:
            best, bi = e, i
    return bi


def first_onset(d: list[float], frac: float = 0.45) -> int:
    thr = max(abs(v) for v in d) * frac
    for i, v in enumerate(d):
        if abs(v) > thr:
            return i
    return 0


def shape_whoosh(d: list[float], tail_ms: float = 45.0,
                 fade_ms: float = 35.0) -> tuple[list[float], int]:
    """Trim a pass-by whoosh so it terminates just past its peak.

    Returns (samples, peak_index_within_result).
    """
    pk = envelope_peak(d)
    end = min(len(d), pk + int(tail_ms / 1000 * SR))
    out = d[:end]
    fade = int(fade_ms / 1000 * SR)
    for i in range(max(0, len(out) - fade), len(out)):
        k = (len(out) - i) / fade
        out[i] *= k * k
    return out, pk


def mix(buf: list[float], src: list[float], at: int, gain: float) -> None:
    for i, v in enumerate(src):
        j = at + i
        if 0 <= j < len(buf):
            buf[j] += v * gain


def main() -> int:
    total = int((f2t(F_END) + 0.35) * SR)
    buf = [0.0] * total

    gavel = read_wav(SFX / "gavel_2blow.wav")
    wl = read_wav(SFX / "whoosh_c.wav")      # short and tight, for the letters
    ws = read_wav(SFX / "whoosh_a.wav")      # longer body, for the star flight

    letter_w, letter_pk = shape_whoosh(wl)
    star_w, star_pk = shape_whoosh(ws, tail_ms=70.0, fade_ms=55.0)
    lead = int(LEAD_MS / 1000 * SR)

    print("placement:")
    # --- three letter whooshes, on the stagger --------------------------------
    for i, f in enumerate(F_LAND):
        at = int(f2t(f) * SR) - letter_pk - lead
        # descending gain: the first entrance establishes, the rest follow it
        mix(buf, letter_w, at, (0.52, 0.46, 0.42)[i])
        print(f"  whoosh {i+1}  peak at f{f} ({f2t(f):.3f}s)  start {at/SR:+.3f}s")

    # --- the gavel: align the recording's FIRST strike to the contact frame ---
    on = first_onset(gavel)
    at = int(f2t(F_HIT1) * SR) - on
    mix(buf, gavel, at, 1.0)
    real_gap = 322.0
    picture_gap = (F_HIT2 - F_HIT1) / FPS * 1000
    print(f"  gavel    strike1 at f{F_HIT1} ({f2t(F_HIT1):.3f}s)")
    print(f"           recording gap {real_gap:.0f} ms vs picture gap "
          f"{picture_gap:.0f} ms  -> drift {picture_gap - real_gap:+.0f} ms "
          f"(limit 45 ms early / 125 ms late)")

    # --- the star's flight ----------------------------------------------------
    at = int(f2t(F_STAR_LAND) * SR) - star_pk - lead
    mix(buf, star_w, at, 0.40)
    print(f"  star     peak at f{F_STAR_LAND} ({f2t(F_STAR_LAND):.3f}s)")

    # --- headroom -------------------------------------------------------------
    peak = max(abs(v) for v in buf) or 1.0
    ceiling = 10 ** (-3.0 / 20)          # -3 dBFS, room for the AAC encode
    scale = ceiling / peak
    for i in range(len(buf)):
        buf[i] *= scale

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUT), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(b"".join(
            struct.pack("<h", max(-32767, min(32767, int(v * 32767))))
            for v in buf))

    print(f"\nwrote {OUT}  ({len(buf)/SR:.3f}s, raw peak {peak:.3f} -> -3.0 dBFS)")

    # A 2.6s file is too short for integrated or short-term LUFS — both gate it
    # away (measured: a 2s sting reports -120 LUFS short-term). Momentary max is
    # the only valid meter at this length.
    r = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", str(OUT), "-af", "ebur128=peak=true",
         "-f", "null", "-"], capture_output=True, text=True).stderr
    mom = [float(x) for x in __import__("re").findall(r"M:\s*(-?\d+\.\d+)", r)]
    tp = __import__("re").findall(r"Peak:\s*(-?\d+\.\d+)", r)
    if mom:
        print(f"momentary max: {max(mom):.1f} LUFS   true peak: "
              f"{tp[-1] if tp else '?'} dBFS")
        print("(YouTube normalises to -14 LUFS and only ever turns audio DOWN,")
        print(" so match the body of the video rather than relying on it.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
