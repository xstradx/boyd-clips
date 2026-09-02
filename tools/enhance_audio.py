# -*- coding: utf-8 -*-
"""Speech enhancement for courtroom audio. All open source, all local.

Measured on SANCHEZ_SHORT_FINAL: SNR 18.7 dB, but the 2-4 kHz presence band sits
26.6 dB below 100-500 Hz. That is a MUFFLED signal, not a noisy one - courtroom
mics in a hard room, picked up mostly boom and room. Denoising alone would have
done almost nothing, which is why the chain below is mostly spectral.

Chain, in order and why:
  highpass 85      kill HVAC rumble and desk thumps below speech
  equalizer 250    -4 dB, pull the boom that masks everything above it
  afftdn           gentle broadband denoise (nr 12, not 25 - over-denoising
                   makes speech watery and hurts the transcriber)
  equalizer 2600   +6 dB, the consonant/presence band, the actual fix
  equalizer 4200   +3 dB, sibilance and detail
  deesser          put back only what the presence lift over-brightens
  acompressor      even out near/far speakers at the bench
  speechnorm       lift the quiet passages without pumping
  loudnorm I=-16   YouTube/Shorts target, two-pass would be better but one is fine

    python tools/enhance_audio.py IN.mp4 OUT.wav
"""
import subprocess, sys, os, json
import numpy as np, wave

CHAIN = (
    "highpass=f=85,"
    "equalizer=f=250:t=q:w=1.0:g=-4,"
    "afftdn=nr=12:nf=-28:tn=1,"
    "equalizer=f=2600:t=q:w=1.2:g=6,"
    "equalizer=f=4200:t=q:w=1.4:g=3,"
    "deesser=i=0.35,"
    "acompressor=threshold=-20dB:ratio=3:attack=8:release=180:makeup=2,"
    "speechnorm=e=12.5:r=0.0003:l=1,"
    "loudnorm=I=-16:TP=-1.5:LRA=11"
)


def measure(path, tag):
    w = wave.open(path)
    a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    sr = w.getframerate()
    fr = sr // 10
    E = np.array([np.sqrt((a[i:i + fr] ** 2).mean()) for i in range(0, len(a) - fr, fr)])
    Ed = 20 * np.log10(E + 1e-9)
    lo, hi = np.percentile(Ed, 10), np.percentile(Ed, 90)
    seg = a[:sr * 20] if len(a) > sr * 20 else a
    sp = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
    f = np.fft.rfftfreq(len(seg), 1 / sr)

    def band(a_, b_):
        m = (f >= a_) & (f < b_)
        return 20 * np.log10(sp[m].mean() + 1e-9)

    low, pres = band(100, 500), band(2000, 4000)
    print(f"{tag:12} RMS {20*np.log10(np.sqrt((a**2).mean())+1e-9):6.1f}  "
          f"SNR {hi-lo:5.1f} dB  100-500 {low:6.1f}  2k-4k {pres:6.1f}  "
          f"tilt {low-pres:5.1f} dB")
    return dict(snr=float(hi - lo), tilt=float(low - pres))


def enhance(src, out_wav):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-vn", "-ac", "1",
                    "-ar", "16000", "-c:a", "pcm_s16le", "_raw.wav"], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", "_raw.wav",
                    "-af", CHAIN, "-ac", "1", "-ar", "16000",
                    "-c:a", "pcm_s16le", out_wav], check=True)
    before = measure("_raw.wav", "BEFORE")
    after = measure(out_wav, "AFTER")
    print(f"\n  tilt {before['tilt']:.1f} dB -> {after['tilt']:.1f} dB  "
          f"({before['tilt']-after['tilt']:+.1f} dB of masking removed)")
    os.remove("_raw.wav")
    return after


if __name__ == "__main__":
    enhance(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "enhanced.wav")
