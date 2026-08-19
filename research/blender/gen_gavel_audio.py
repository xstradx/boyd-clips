"""Synthesise the two gavel impacts. Pure stdlib — no numpy on this machine.

A gavel strike is three things layered, and leaving any out makes it read as a
click rather than a blow:
  * a low thump (~70 Hz) with fast pitch decay — the mass
  * a wood crack: filtered noise burst, ~8 ms — the contact
  * a short body resonance (~180 Hz) — the block it lands on

Hit 2 is louder and slightly lower than hit 1. Gavels go tap ... TAP; equal
hits read as a stutter.

Timing is authored in FRAMES at 60 fps so it lines up with sting_gavel.py
without conversion drift. Audio must peak ON the contact frame — ITU-R
BT.1359-1 puts audio-early unacceptability at +90 ms, and a lead is far more
noticeable than a lag.
"""
from __future__ import annotations

import math
import random
import struct
import sys
import wave
from pathlib import Path

SR = 48000
FPS = 60
OUT = Path(__file__).parent / "renders" / "gavel_audio.wav"

# contact frames — must match BEAT in sting_gavel.py
HIT1_FRAME = 30
HIT2_FRAME = 49
TOTAL_FRAMES = 108


def f2s(frame: int) -> int:
    return int((frame - 1) / FPS * SR)


def impact(buf: list[float], at: int, gain: float, pitch: float) -> None:
    """One strike, written in place at sample offset `at`."""
    rnd = random.Random(1337 + at)

    # wood crack — noise through a crude one-pole low-pass, 9 ms
    n = int(0.009 * SR)
    lp = 0.0
    for i in range(n):
        white = rnd.uniform(-1.0, 1.0)
        lp += 0.42 * (white - lp)
        env = math.exp(-i / (n * 0.30))
        idx = at + i
        if idx < len(buf):
            buf[idx] += lp * env * gain * 0.85

    # low thump with downward pitch sweep — the mass behind the hit
    n = int(0.16 * SR)
    for i in range(n):
        t = i / SR
        freq = pitch * (1.0 + 1.6 * math.exp(-t * 55))
        env = math.exp(-t * 26)
        idx = at + i
        if idx < len(buf):
            buf[idx] += math.sin(2 * math.pi * freq * t) * env * gain

    # block resonance
    n = int(0.11 * SR)
    for i in range(n):
        t = i / SR
        env = math.exp(-t * 38)
        idx = at + i
        if idx < len(buf):
            buf[idx] += math.sin(2 * math.pi * (pitch * 2.6) * t) * env * gain * 0.28


def main() -> int:
    total = int(TOTAL_FRAMES / FPS * SR) + SR // 2
    buf = [0.0] * total

    # a near-silent room tone so the cut to content is not a dead drop
    for i in range(total):
        buf[i] += math.sin(2 * math.pi * 47 * i / SR) * 0.004 * math.exp(-i / (total * 1.6))

    impact(buf, f2s(HIT1_FRAME), gain=0.62, pitch=78.0)
    impact(buf, f2s(HIT2_FRAME), gain=1.00, pitch=68.0)   # harder, lower

    peak = max(abs(v) for v in buf) or 1.0
    ceiling = 10 ** (-1.5 / 20)          # -1.5 dBFS, leaves headroom for the mux
    scale = ceiling / peak

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUT), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(b"".join(
            struct.pack("<h", max(-32767, min(32767, int(v * scale * 32767))))
            for v in buf))

    print(f"wrote {OUT}")
    print(f"  {total/SR:.3f}s @ {SR}Hz mono")
    print(f"  hit1 frame {HIT1_FRAME} ({(HIT1_FRAME-1)/FPS:.3f}s)  gain 0.62")
    print(f"  hit2 frame {HIT2_FRAME} ({(HIT2_FRAME-1)/FPS:.3f}s)  gain 1.00 (harder, lower)")
    print(f"  peak normalised to -1.5 dBFS (raw peak was {peak:.3f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
