"""Is there anyone in the other Zoom window? Answered BEFORE the case is chosen.

THE PROBLEM THIS EXISTS FOR
---------------------------
Nathan, 2026-08-18: "the thing about jury trials is that the defendant doesn't
ever stand in the camera so it's just Judge Boyd with an empty camera in the
other zoom window... although the jury trials of course have serious and
interesting stuff going on it's hard to find the ones that actually have enough
content to show."

The rubric in `prompts/score_cases.md` reads a TRANSCRIPT. A transcript cannot
see an empty tile. So the pipeline systematically over-rates exactly the cases
Nathan cannot use: contested sentencings and trial segments, where lawyers and
witnesses generate rich text while the camera holds on the bench and a dead
rectangle.

This is not hypothetical. `4zkUTUavW4I:116` (Blackburn) scored 92.1 — the
highest in the database — and its short was unpostable, because the source is a
3-4 tile grid and no face lands wide enough to read. That was discovered after
rendering. This module moves the discovery to before the download.

WHAT IT MEASURES, AND WHY THESE SIGNALS
---------------------------------------
For each tile in the frame, across a handful of frames spread over the case:

  motion  mean absolute pixel difference between consecutive samples.
          A person breathes, shifts, gestures. An empty chair, a name-card
          placeholder and a frozen feed do not. This is the primary signal
          because it needs no model and cannot be fooled by a static photo.

  detail  variance of the Laplacian — edge energy within a single frame.
          Separates a real (if still) picture from a flat colour placeholder
          or a black tile, which motion alone would also score at zero.

  faces   OpenCV Haar frontal-face hits, used only to CONFIRM. Optional:
          if cv2 is missing the verdict falls back to motion+detail rather
          than failing. Haar misses profiles and masks constantly, so a zero
          face count is never on its own a reason to reject.

A tile is LIVE when it has motion AND detail. The verdict is the number of
live tiles, which is the thing Nathan actually needs: one live tile means the
judge talking to an empty room.

DELIBERATELY NOT A SAFETY RULE. This decides whether a clip is watchable, not
whether it is publishable. It runs after the safety gate, never in front of it.
"""
from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Sequence

log = logging.getLogger(__name__)

# CALIBRATED 2026-08-18 against four cases with known outcomes. Per-tile
# Laplacian variance, 2-up halves:
#
#   Thompson  (approved short, defendant + counsel visible)   465 / 678
#   Rodriguez (approved short, faces legible)                 628 / 467
#   Blackburn (people visible; short failed for TILE SIZE)    617 / 679
#   Pena      (51-min sentencing, feed is a BLACK NAME CARD)   50 /  69
#
# Every real picture clears 330 even at quadrant granularity; the name card
# never exceeds 91. 200 sits in the gap with room on both sides.
DETAIL_LIVE = 200.0

# Frames are sampled MINUTES apart, so this is scene CHANGE across the case,
# not human motion. It caught nothing the other two signals missed on the
# calibration set — Pena's black card still scored 13.7 because the docket
# cuts between cases — so it is kept as a weak floor only. Do not raise it
# into a primary signal without re-measuring.
MOTION_LIVE = 0.5

# The clincher, and the cheapest signal here. Pena's tiles are ~99% black;
# every real courtroom picture in the calibration set is under 30%.
DARK_SHARE_DEAD = 0.85
DARK_LEVEL = 24        # 8-bit luma below this counts as black


@dataclass
class Tile:
    name: str
    motion: float
    detail: float
    faces: int
    dark: float = 0.0

    @property
    def live(self) -> bool:
        """A tile holds a real picture of a real room.

        Ordered cheapest-and-most-decisive first: a tile that is almost
        entirely black is a Zoom name card, full stop — no amount of edge
        energy elsewhere rescues it.
        """
        if self.dark >= DARK_SHARE_DEAD:
            return False
        return self.detail >= DETAIL_LIVE and self.motion >= MOTION_LIVE


@dataclass
class Verdict:
    live_tiles: int
    tiles: list[Tile]
    frames: int
    layout: str          # "2up" | "grid" | "single"

    @property
    def usable(self) -> bool:
        """Two or more live tiles = someone is on camera opposite the judge."""
        return self.live_tiles >= 2

    @property
    def reason(self) -> str:
        if self.frames == 0:
            return "no frames could be sampled"
        if self.usable:
            return f"{self.live_tiles} live tiles in a {self.layout} layout"
        if self.live_tiles == 1:
            return ("only one tile is live — the other window is empty, frozen "
                    "or a Zoom name card")
        return ("no live tiles — the feed is a name card or the camera was off "
                "for this whole case")

    def to_json(self) -> str:
        d = asdict(self)
        d["usable"] = self.usable
        d["reason"] = self.reason
        return json.dumps(d, indent=2)


def sample_frames(video_id: str, start_s: float, end_s: float,
                  n: int = 8, out_dir: Path | None = None) -> list[Path]:
    """Pull `n` single frames spread across the case WITHOUT downloading it.

    `yt-dlp --download-sections` fetches only the requested seconds, so probing
    a 51-minute case costs about 8 seconds of video. Frames are taken at 12%,
    24% ... 96% of the span, skipping the very start and end where the docket
    is still switching between cases.
    """
    out_dir = out_dir or Path(tempfile.mkdtemp(prefix="oncam_"))
    out_dir.mkdir(parents=True, exist_ok=True)
    span = max(1.0, end_s - start_s)
    frames: list[Path] = []
    for i in range(1, n + 1):
        t = start_s + span * (i / (n + 1.0))
        dst = out_dir / f"f{i:02d}.png"
        cmd = [
            "yt-dlp", "--quiet", "--no-warnings",
            "--download-sections", f"*{t:.2f}-{t + 0.5:.2f}",
            "--force-keyframes-at-cuts",
            "-f", "bv*[height<=720]/b[height<=720]/b",
            "-o", "-", f"https://www.youtube.com/watch?v={video_id}",
        ]
        try:
            blob = subprocess.run(cmd, capture_output=True, timeout=180).stdout
            if not blob:
                continue
            ff = subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
                 "-frames:v", "1", "-y", str(dst)],
                input=blob, capture_output=True, timeout=120)
            if dst.exists() and dst.stat().st_size > 0:
                frames.append(dst)
            else:
                log.debug("oncamera: no frame at %.1fs (%s)", t,
                          ff.stderr.decode()[:120])
        except subprocess.TimeoutExpired:
            log.warning("oncamera: timed out sampling at %.1fs", t)
    return frames


def frames_from_file(source: Path, n: int = 8,
                     out_dir: Path | None = None) -> list[Path]:
    """Same sampling against a file already on disk — no network."""
    out_dir = out_dir or Path(tempfile.mkdtemp(prefix="oncam_"))
    out_dir.mkdir(parents=True, exist_ok=True)
    dur = _duration(source)
    frames: list[Path] = []
    for i in range(1, n + 1):
        t = dur * (i / (n + 1.0))
        dst = out_dir / f"f{i:02d}.png"
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{t:.2f}",
             "-i", str(source), "-frames:v", "1", "-y", str(dst)],
            capture_output=True, timeout=120)
        if dst.exists() and dst.stat().st_size > 0:
            frames.append(dst)
    return frames


def _duration(source: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(source)],
        capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def _regions(w: int, h: int, layout: str) -> list[tuple[str, tuple[int, int, int, int]]]:
    if layout == "2up":
        return [("left", (0, 0, w // 2, h)), ("right", (w // 2, 0, w, h))]
    if layout == "grid":
        return [("tl", (0, 0, w // 2, h // 2)), ("tr", (w // 2, 0, w, h // 2)),
                ("bl", (0, h // 2, w // 2, h)), ("br", (w // 2, h // 2, w, h))]
    return [("full", (0, 0, w, h))]


def analyse(frames: Sequence[Path], layout: str = "2up") -> Verdict:
    """Score each tile for motion, detail and faces across the sampled frames."""
    import numpy as np
    from PIL import Image

    if len(frames) < 2:
        return Verdict(0, [], len(frames), layout)

    grays = []
    for f in frames:
        with Image.open(f) as im:
            grays.append(np.asarray(im.convert("L"), dtype=np.float32))
    h, w = grays[0].shape

    try:
        import cv2
        cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    except Exception:                                   # pragma: no cover
        cascade = None

    tiles: list[Tile] = []
    for name, (x1, y1, x2, y2) in _regions(w, h, layout):
        crops = [g[y1:y2, x1:x2] for g in grays]
        motion = float(np.mean([np.mean(np.abs(b - a))
                                for a, b in zip(crops, crops[1:])]))
        # Laplacian via a 4-neighbour kernel, no scipy dependency.
        c = crops[len(crops) // 2]
        lap = (c[:-2, 1:-1] + c[2:, 1:-1] + c[1:-1, :-2] + c[1:-1, 2:]
               - 4 * c[1:-1, 1:-1])
        detail = float(np.var(lap))
        dark = float(np.mean([np.mean(cr < DARK_LEVEL) for cr in crops]))
        faces = 0
        if cascade is not None:
            for cr in crops[::2]:
                found = cascade.detectMultiScale(
                    cr.astype("uint8"), scaleFactor=1.15, minNeighbors=5,
                    minSize=(28, 28))
                faces = max(faces, len(found))
        tiles.append(Tile(name, round(motion, 3), round(detail, 1), faces,
                          round(dark, 3)))

    return Verdict(sum(1 for t in tiles if t.live), tiles, len(frames), layout)


def detect_layout(frames: Sequence[Path]) -> str:
    """2-up (the docket's default) or a 2x2 grid.

    FIRST ATTEMPT, RECORDED SO IT IS NOT RETRIED: comparing the centre seam's
    brightness against the WHOLE FRAME's mean returned "single" on all four
    calibration cases, including Thompson, which is unambiguously a 2-up. The
    frames are heavily letterboxed — the picture occupies a band roughly
    y=180..680 of 720 — so the frame mean is dragged down by the black bars
    and no seam ever looks dark "relative to the body".

    Measuring inside the CONTENT BAND fixes it. The band is found by keeping
    rows whose mean exceeds the frame's own 60th percentile of row means.

    This docket is a 2-up by construction, so 2up is the fallback rather than
    "single" — a wrong grid guess costs a coarser measurement, a wrong single
    guess throws away the whole point of the check.
    """
    import numpy as np
    from PIL import Image
    if not frames:
        return "2up"
    with Image.open(frames[len(frames) // 2]) as im:
        g = np.asarray(im.convert("L"), dtype=np.float32)
    h, w = g.shape
    rows = g.mean(axis=1)
    keep = np.where(rows > np.percentile(rows, 60))[0]
    if keep.size < 16:
        return "2up"
    y1, y2 = int(keep[0]), int(keep[-1])
    band = g[y1:y2 + 1, :]
    bh, bw = band.shape
    k = max(2, bw // 200)
    body = float(np.mean(band))
    vseam = float(np.mean(band[:, bw // 2 - k:bw // 2 + k]))
    hseam = float(np.mean(band[bh // 2 - k:bh // 2 + k, :]))
    if vseam < body * 0.55 and hseam < body * 0.55:
        return "grid"
    return "2up"
