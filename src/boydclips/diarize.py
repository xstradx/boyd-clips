"""Who is talking - Judge Boyd, or the person in front of her.

Captions in the approved Thompson short move to the speaker's half of the
frame. ASS supports that per Dialogue line via MarginV, and build_ass already
takes `turns` + `slot_margins`; the missing piece was ever knowing who is
speaking. v3 got it by hand-writing the turns for four beats.

WHAT WAS TRIED FIRST, and why it is not used:

  * Zoom's active-speaker highlight. detect_tile_crops insets every tile
    specifically to crop off "a bright green rectangle drawn just inside the
    tile border", so the signal ought to be in the pixels for free. Measured on
    RzjGikNbHMA with scripts/probe_speaker_highlight.py across 10 frames:
    green-dominance 0.0000 on BOTH tiles at every sample. The court's recording
    does not carry the highlight. Not usable.

  * pyannote / WhisperX. The right tool, and both need torch (~2.5GB) plus
    gated HuggingFace weights. Not installed here.

  * MFCC + 2-way agglomerative clustering, using only librosa and sklearn,
    which were already installed. Built and REJECTED on measurement. Checked
    against the transcript on RzjGikNbHMA:8485 it put "I thought it was
    discovery, but it may be plea deadline, **Judge**" and "We're going to have
    an investigator appointed, **Judge**" in Boyd's slot - both are counsel
    addressing her. MFCC captures channel and loudness as much as voice, and a
    docket has four speakers (judge, defendant, defence, State), so forcing two
    clusters splits on the wrong axis. Kept in git history; do not rebuild it.

WHAT THIS DOES INSTEAD. SpeechBrain's ECAPA-TDNN speaker encoder - the same
class of model as pyannote's, trained on VoxCeleb, but ungated and pure torch.
It emits a 192-d embedding per window that encodes WHO is speaking rather than
what the audio looks like. Windows are then clustered and smoothed.

Installed on CPU torch. pyannote and Resemblyzer were both attempted first and
both failed on this machine: pyannote needs gated HuggingFace weights, and
Resemblyzer depends on webrtcvad, which has no wheel for Python 3.14 and needs
a C toolchain to build.

Assignment of cluster -> person does NOT use pitch. Judge Boyd is female and
most defendants are male, so f0 looks like a free answer and is a trap: it
inverts on every female defendant, and this docket has several (Ganal, Gyos,
Diamond Garcia). The rule used instead is the one this repo already relies on
in dialogue_metrics.py - **Boyd runs the room and speaks most** - which holds
regardless of who is in front of her.

HONEST LIMITS. This is clustering, not speaker recognition. It has no model of
either voice, so it will mislabel when a third person speaks at length (an
attorney, a probation officer testifying), and short interjections inside
another speaker's turn get absorbed by the smoothing. It is good enough to put
captions on the right half of the screen and not good enough to caption a name.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import tempfile
import types
from pathlib import Path

log = logging.getLogger("boydclips.diarize")


def _patch_speechbrain_lazy_import() -> None:
    """Work around a SpeechBrain 1.1.0 crash on Python 3.14.

    from_hparams calls inspect.stack() to find its caller. On 3.14 that walk
    touches SpeechBrain's LazyModule.__getattr__ for the optional k2_fsa
    integration, which tries to import k2, which is not installed — and the
    whole call dies with "Lazy import of LazyModule(...k2_fsa) failed".

    The real defect is the exception TYPE. inspect asks `hasattr(module,
    '__file__')`, and hasattr only swallows AttributeError — LazyModule raises
    ImportError, which propagates and kills the caller. Seeding module names
    was tried first and is whack-a-mole: k2_fsa, then
    integrations.huggingface.wordemb, and so on for every optional extra.

    So convert the exception instead. A lazy module whose optional dependency
    is absent genuinely does not have the attribute, and AttributeError is what
    "does not have it" means — inspect then skips the frame and moves on. Real
    attribute access on a real lazy module is untouched.

    The version matrix is why this exists rather than a pin: 1.1.0 is the only
    release that works with torchaudio 2.11 (1.0.2 calls
    torchaudio.list_audio_backends, removed in 2.x), and 1.1.0 is the one that
    carries the lazy-import shim.
    """
    try:
        from speechbrain.utils import importutils
    except Exception:                                     # pragma: no cover
        return
    lazy = getattr(importutils, "LazyModule", None)
    if lazy is None or getattr(lazy, "_boyd_patched", False):
        return

    original = lazy.__getattr__

    def __getattr__(self, attr):                          # noqa: N807
        try:
            return original(self, attr)
        except ImportError as exc:
            raise AttributeError(attr) from exc

    lazy.__getattr__ = __getattr__
    lazy._boyd_patched = True

BOYD = "boyd"
DEFENDANT = "defendant"

WIN_S = 0.75          # analysis window
HOP_S = 0.25          # window hop
SMOOTH_WIN = 7        # median-filter width, in hops (~1.75s)
MIN_TURN_S = 0.8      # turns shorter than this are absorbed into the neighbour


def _extract_wav(source: Path, out: Path, sr: int = 16000) -> Path:
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(source),
         "-ac", "1", "-ar", str(sr), "-vn", str(out)],
        check=True, capture_output=True, timeout=900,
    )
    return out


def diarize(source: Path, sr: int = 16000) -> list[tuple[float, str]]:
    """Return [(start_seconds, speaker), ...] over the whole file.

    Times are in the file's own timeline. The caller maps them onto the short's
    edited timeline the same way it maps words.
    """
    import librosa
    import numpy as np
    import torch
    from sklearn.cluster import AgglomerativeClustering

    _patch_speechbrain_lazy_import()
    from speechbrain.inference.speaker import EncoderClassifier

    with tempfile.TemporaryDirectory(prefix="boyd-diar-") as td:
        wav = _extract_wav(source, Path(td) / "a.wav", sr)
        y, sr = librosa.load(str(wav), sr=sr, mono=True)

    win = int(WIN_S * sr)
    hop = int(HOP_S * sr)
    if len(y) < win * 2:
        return []

    starts, chunks = [], []
    for i in range(0, len(y) - win, hop):
        seg = y[i:i + win]
        # Silence carries no voice; embedding it would create a third group and
        # scatter the turn boundaries.
        if float(np.sqrt(np.mean(seg ** 2))) < 0.008:
            continue
        chunks.append(seg)
        starts.append(i / sr)

    if len(chunks) < 8:
        log.info("  diarize: too little speech to cluster (%d windows)", len(chunks))
        return []

    from speechbrain.utils.fetching import LocalStrategy

    encoder = EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        savedir=str(Path(__file__).resolve().parents[2] / "assets" / "ecapa"),
        run_opts={"device": "cpu"},
        # Windows refuses symlinks without Developer Mode or admin, and
        # from_hparams symlinks the checkpoint out of the HF cache by default —
        # WinError 1314. COPY costs ~80MB of disk once and needs no privilege.
        local_strategy=LocalStrategy.COPY,
    )
    embs = []
    for k in range(0, len(chunks), 64):          # batched; CPU, so keep it small
        batch = torch.tensor(np.stack(chunks[k:k + 64]), dtype=torch.float32)
        with torch.no_grad():
            e = encoder.encode_batch(batch).squeeze(1)
        embs.append(e.cpu().numpy())
    X = np.concatenate(embs, axis=0).astype(np.float64)

    # Cosine geometry: speaker embeddings are trained so that the ANGLE between
    # two vectors encodes same-speaker-or-not. Clustering on raw Euclidean
    # distance would let loudness, which lives in the magnitude, leak back in —
    # the exact failure the MFCC version had.
    X /= (np.linalg.norm(X, axis=1, keepdims=True) + 1e-9)
    labels = AgglomerativeClustering(
        n_clusters=2, metric="cosine", linkage="average"
    ).fit_predict(X)

    # Median smoothing. Raw per-window labels flicker on breaths and plosives;
    # a caption that changes side for 250ms reads as a glitch, not as dialogue.
    sm = labels.copy()
    half = SMOOTH_WIN // 2
    for i in range(len(labels)):
        lo, hi = max(0, i - half), min(len(labels), i + half + 1)
        sm[i] = int(np.round(np.median(labels[lo:hi])))

    # Which cluster is the judge: the one holding the most speech. Not pitch -
    # see the module docstring.
    totals = {c: int((sm == c).sum()) for c in (0, 1)}
    boyd_cluster = max(totals, key=lambda c: totals[c])
    who = {boyd_cluster: BOYD, 1 - boyd_cluster: DEFENDANT}

    turns: list[tuple[float, str]] = []
    for t, lab in zip(starts, sm):
        name = who[int(lab)]
        if not turns or turns[-1][1] != name:
            turns.append((float(t), name))

    # Drop turns too short to be real, then re-merge equal neighbours.
    pruned: list[tuple[float, str]] = []
    for i, (t, name) in enumerate(turns):
        end = turns[i + 1][0] if i + 1 < len(turns) else starts[-1] + WIN_S
        if end - t < MIN_TURN_S and pruned:
            continue
        if pruned and pruned[-1][1] == name:
            continue
        pruned.append((t, name))

    log.info("  diarize: %d turns (%d windows, boyd holds %.0f%%)",
             len(pruned), len(sm), 100.0 * totals[boyd_cluster] / len(sm))
    return pruned
