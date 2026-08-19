# Audit the Court — narrator voice, measured

Measured 2026-08-12 from source audio pulled with `yt-dlp -x --audio-format wav`.
Analysis: `faster-whisper small.en` (CPU int8, word timestamps) for rate and pause
distribution; `librosa 1.0.0` `pyin` (fmin 60, fmax 350) for F0; `ffmpeg ebur128` for
loudness. Two videos measured independently as a cross-check.

Corpus: `Ek3Ah3NZYVo` (2026-07-17, Judge Boyd — our closest analogue) and
`yzv_uxBSgu0` (2026-03-14). Narration span isolated by cutting at the first inter-word
gap > 3.0 s, which is where the read hands off to courtroom audio.

## The numbers

| | `Ek3Ah3NZYVo` | `yzv_uxBSgu0` | target |
|---|---:|---:|---|
| narration span | 72.50 s (213 words) | 27.72 s (82 words) | — |
| **speech rate** | **176.3 WPM** | **177.5 WPM** | **176–178 WPM** |
| **F0 median** | **103.9 Hz** | **103.9 Hz** | **104 Hz** |
| F0 p10 | 82.9 Hz | 85.3 Hz | ~84 Hz |
| F0 sd (semitones) | 5.85 st * | 3.45 st | **~3.5 st** |
| voiced fraction | 58 % | 61 % | ~60 % |
| pauses > 120 ms | n=28 | n=11 | — |
| pause median | 250 ms | 340 ms | **250–340 ms** |
| pause p90 | 500 ms | 500 ms | **500 ms** |
| pause max | 1160 ms | 500 ms | ≤ 1.2 s |
| RMS crest (p95−p50) | 3.9 dB | 6.1 dB | **4–6 dB** |
| spectral centroid | 1133 Hz | 1420 Hz | 1.1–1.4 kHz |

\* The EK3 F0 p90 of 200.4 Hz against a 103.9 Hz median is almost certainly `pyin`
octave-doubling, not real range — which inflates that video's 5.85 st figure. Treat the
YZV **3.45 st** as the honest expressiveness number until re-measured with a second
tracker. Flagged rather than averaged.

Loudness (first 80 s of `Ek3Ah3NZYVo`, `ebur128`):
**I = −19.1 LUFS · LRA = 2.4 LU · true peak = −1.0 dBFS**

## What those numbers mean as a casting brief

**F0 median 104 Hz** is a low-mid male voice — not a bass, not a bright young read.
**176 WPM sustained** is brisk-but-unhurried: faster than the "documentary gravitas" cliché
(140–150) and far off audiobook pace. He does not slow down for effect.

**F0 sd ≈ 3.5 st** is the crucial one. That is *moderately* expressive — above the flat
2 st that reads as synthetic, well below the 5 st+ of an excited delivery. The read is
level and credible over grim material, which is exactly the casting: it never sounds
pleased with the story it is telling.

**LRA 2.4 LU with a 4–6 dB crest** means a hard broadcast VO chain — compressed
aggressively so every syllable sits at the same level. This is a post-production fact,
not a performance fact, and it is reproducible on any source.

**Pause median 250–340 ms, p90 500 ms, hard ceiling ~1.2 s.** Short, regular breaths at
clause boundaries. No dramatic silences.

## Why this file exists

The narration script is full of exactly what exposes synthetic speech: `January 18, 2023`,
`Bexar County`, `nolo contendere`, `DC2023CR8866`, `seven counts`, dollar amounts. Any
candidate voice gets scored against the table above **and** on whether it says those
classes correctly.

Reference audio and word-timing JSON: `research/reference/competitor/voice/`.
