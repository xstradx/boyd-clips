"""Stage 3 — download only what gets published, then cut it.

Video enters the pipeline here and nowhere else. By this point exactly one case
has been selected, so we fetch that case's minutes rather than the docket's
hours, using yt-dlp's --download-sections with keyframe forcing so the returned
file starts precisely at the requested timestamp.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .censor import censor
from .transcribe import Word

log = logging.getLogger("boydclips.render")

# Generous margin around the requested case so head/tail padding and any
# keyframe slop have material to work with.
SECTION_MARGIN_S = 20.0

# Where the stacked pair sits on the 1920px canvas, and how much clear space
# the captions need beneath it.
STACK_TOP_Y = 120
CAPTION_BAND_MIN = 180

# Clearance under a bottom-anchored tile stack. The captions no longer live in
# the band below the stack — the platform safe zone puts them over the picture —
# so this is breathing room, not a caption band.
STACK_BOTTOM_MARGIN = 100

# Minimum content aspect for tile stacking.
#
# Each half of a 2-up becomes 1080 wide, so a tile is 1080/(aspect/2) tall and
# the stacked pair is twice that. For the pair plus STACK_TOP_Y plus a caption
# band to fit inside 1920, the aspect has to clear ~2.6 — at 2.2 the stack is
# 2084px and the lower participant is pushed off-frame while the captions land
# on top of them. Derived rather than guessed, so the two stay in sync.
SPLIT_STACK_MIN_ASPECT = 2.0 * 1080 / ((1920 - STACK_TOP_Y - CAPTION_BAND_MIN) / 2.0)


def choose_vertical_layout(
    source: Path, crop: str | None, cfg: dict[str, Any]
) -> tuple[str, int]:
    """Pick a framing mode and the caption margin that suits it.

    Returns (mode, caption_margin_v). The margin differs per mode because the
    captions must land in empty space, and where that space is depends on how
    the frame was assembled.

    Honours an explicit `vertical_mode`. Deciding the margin from a layout the
    renderer was never going to use burns captions at the wrong height — and
    silently, since the frame still renders.
    """
    default_margin = cfg.get("captions", {}).get("margin_v", 420)
    configured = cfg.get("vertical_mode", "auto")
    if configured != "auto":
        if configured == "split_stack":
            return configured, _stack_margin(_aspect_of(source, crop) or 2.7)
        return configured, default_margin

    aspect = _aspect_of(source, crop)
    if aspect is None:
        return "blur_pad", default_margin

    if aspect >= SPLIT_STACK_MIN_ASPECT:
        return "split_stack", _stack_margin(aspect)

    return "blur_pad", default_margin


def _aspect_of(source: Path, crop: str | None) -> float | None:
    if crop:
        cw, ch = (int(v) for v in crop.split("=")[1].split(":")[:2])
    else:
        cw, ch = probe_dimensions(source)
    return (cw / float(ch)) if ch else None


def _stack_margin(aspect: float) -> int:
    tile_h = int(round(1080 / (aspect / 2)))
    stack_bottom = STACK_TOP_Y + 2 * tile_h
    return max(CAPTION_BAND_MIN // 2, 1920 - stack_bottom - 40)


@dataclass
class Segment:
    start_s: float   # absolute, in source-video time
    end_s: float

    @property
    def duration(self) -> float:
        return self.end_s - self.start_s


def _run(cmd: Sequence[str], cwd: Path | None = None, timeout: int = 3600) -> None:
    proc = subprocess.run(
        list(cmd), cwd=str(cwd) if cwd else None,
        capture_output=True, text=True, timeout=timeout,
    )
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-25:])
        raise RuntimeError(f"command failed: {cmd[0]}\n{tail}")


def detect_content_crop(
    source: Path,
    sample_start: float = 5.0,
    sample_s: float = 25.0,
    min_agreement: float = 0.66,
) -> str | None:
    """Find the real content rectangle inside a letterboxed source.

    The court's Zoom recordings are letterboxed *inside* their own 16:9 frame —
    the participant tiles sit in a band with baked-in black bars above and
    below. Scaling that whole frame into a 9:16 canvas leaves the courtroom at
    a fraction of the screen and fills the rest with blurred black.

    Sampled one frame per second across the WHOLE clip and reduced by mode, not
    by cropdetect's own accumulator. `reset=0` unions every frame it sees, so a
    single full-bleed frame — a screen-share, a flash, a layout change — widens
    the accumulated rectangle to the entire frame and detection silently
    reports "no letterbox". Measured on JgvW7oCQxuI:6698: 259 of 265 sampled
    frames agree on crop=1920:712:0:270, but 5 full-frame outliers were enough
    to make the union return 1920:1080 and the short rendered with the
    courtroom occupying 17% of the canvas.

    The mode is also the honest statistic here: the letterbox is a fixed
    property of the recording, so the common value is the true one and the
    outliers are the noise — averaging them would land between two layouts and
    match neither.

    Returns an ffmpeg `crop=` argument, or None when the frame is already full.
    """
    proc = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-nostats",
            "-i", str(source),
            "-vf", "fps=1,cropdetect=limit=24:round=2:reset=1",
            "-f", "null", "-",
        ],
        capture_output=True, text=True, timeout=900,
    )

    crops = re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", proc.stderr)
    if not crops:
        return None

    src_w, src_h = probe_dimensions(source)
    if not src_w or not src_h:
        return None

    def _usable(c: tuple[str, str, str, str]) -> bool:
        """A crop worth applying: not the whole frame, not a dark-shot misread.

        One that keeps almost everything buys nothing, and one that throws most
        of the frame away is usually cropdetect reading a dark shot rather than
        a genuine letterbox.
        """
        cw, ch = int(c[0]), int(c[1])
        if cw <= 0 or ch <= 0:
            return False
        ratio = (cw * ch) / float(src_w * src_h)
        return 0.15 <= ratio <= 0.92

    # Full-frame samples are dropped before the vote rather than after it.
    # 4zkUTUavW4I:116 alternates between a full-bleed screen-share (51.3% of
    # frames) and the letterboxed 2-up (48.7%), so counting them together
    # elects "no crop" by three tenths of a percent and the backdrop is built
    # from black bars again. The question this function answers is "where is
    # the letterbox when there is one", and frames with no letterbox are not
    # evidence about that.
    candidates = [c for c in crops if _usable(c)]
    if not candidates:
        return None

    (w, h, x, y), agree = Counter(candidates).most_common(1)[0]
    w, h, x, y = int(w), int(h), int(x), int(y)

    # A rectangle that only a minority of frames agree on is a layout that
    # changes mid-clip, not a baked-in letterbox. Cropping to it would clip
    # participants out of frame for the rest of the clip, which is the exact
    # failure §4 of CONTENT_SPEC.md exists to prevent — so leave it uncropped.
    # Measured against every sampled frame, not just the usable ones: a clip
    # that is mostly full-bleed has no stable letterbox to strip.
    if agree / float(len(crops)) < min_agreement:
        log.info("framing: crop unstable (%d/%d frames agree) — leaving frame uncropped",
                 agree, len(crops))
        return None

    return f"crop={w}:{h}:{x}:{y}"


def _content_boxes(
    source: Path,
    win_w: int,
    win_h: int,
    x_off: int,
    samples_per_s: float,
    row_floor: float = 12.0,
) -> list[tuple[int, int, int, int]]:
    """Per-frame content rectangles of a region, by row/column occupancy.

    Deliberately NOT ffmpeg's `bbox`, which is a max-based test: one bright
    pixel anywhere in a row keeps that row inside the box. Judge Boyd's Zoom
    tile carries a US flag down its right edge over an otherwise black lower
    band, so bbox reported the tile as 628x488 when rows 354-486 average below
    1.0 of luminance. Scaling that up put a 152px black band across the bottom
    of the rendered short, and the measurement said the tile was fine.

    A row counts as content when its MEAN luminance clears `row_floor`, which
    is the question actually being asked: is there a picture here, or is this
    padding with a highlight in it.
    """
    try:
        import numpy as np
    except ImportError:                      # pragma: no cover - numpy is present
        log.warning("numpy unavailable; tile detection falling back to bbox")
        return []

    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(source),
         "-vf", f"fps={samples_per_s},crop={win_w}:{win_h}:{x_off}:0",
         "-pix_fmt", "gray", "-f", "rawvideo", "-"],
        capture_output=True, timeout=1800,
    )
    frame_bytes = win_w * win_h
    n = len(proc.stdout) // frame_bytes
    if n == 0:
        return []

    buf = np.frombuffer(proc.stdout[: n * frame_bytes], dtype=np.uint8)
    frames = buf.reshape(n, win_h, win_w).astype(np.float32)

    def longest_run(mask) -> tuple[int, int] | None:
        """Bounds of the longest unbroken stretch of content.

        First-to-last would be defeated by a single bright line inside the
        padding: seven scattered rows in Judge Boyd's black lower band kept the
        measured tile at 486 rows when the picture stops at 353.
        """
        best = cur = None
        for i, on in enumerate(mask):
            if on:
                cur = (i, i) if cur is None else (cur[0], i)
                if best is None or cur[1] - cur[0] > best[1] - best[0]:
                    best = cur
            else:
                cur = None
        return best

    boxes: list[tuple[int, int, int, int]] = []
    for f in frames:
        rows = longest_run(f.mean(axis=1) >= row_floor)
        cols = longest_run(f.mean(axis=0) >= row_floor)
        if rows is None or cols is None:
            continue
        boxes.append((cols[0], cols[1], rows[0], rows[1]))
    return boxes


# A pixel at or below this luminance is padding, not picture. Zoom's gutters
# are true black; anti-aliasing on a tile edge lifts a pixel or two above it.
TILE_BLACK_LEVEL = 16.0

# A column is a gutter when it is dark for this fraction of a band's rows.
# Measured on zHchVGBX9iA: the real gutter at x640-719 is dark for 0.933 of the
# band because the "Judge Boyd" name label is drawn ON the gutter, while no
# content column exceeds 0.5. An earlier 0.95 sat above the gutter and merged
# the two tiles into one 1200px rectangle, which is what put a black stripe
# through the rendered short.
TILE_GUTTER_Q = 0.85

# Smallest tile worth cutting to, in either axis.
TILE_MIN_SIDE = 64

# A second tile this much less active than the first is furniture, not a
# person. 4zkUTUavW4I is a clean 2-up whose right tile is an EMPTY witness
# stand; forcing duo_fill on it renders half a frame of static wall.
DEAD_TILE_ACTIVITY_RATIO = 0.25


def _gray_stack(source: Path, samples_per_s: float):
    """Sampled luminance frames of the whole frame, as (stack, w, h)."""
    try:
        import numpy as np
    except ImportError:                      # pragma: no cover - numpy is present
        return None, 0, 0
    src_w, src_h = probe_dimensions(source)
    if not src_w or not src_h:
        return None, 0, 0
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(source),
         "-vf", f"fps={samples_per_s}", "-pix_fmt", "gray", "-f", "rawvideo", "-"],
        capture_output=True, timeout=1800,
    )
    fb = src_w * src_h
    n = len(proc.stdout) // fb
    if n == 0:
        return None, src_w, src_h
    buf = np.frombuffer(proc.stdout[: n * fb], dtype=np.uint8)
    return buf.reshape(n, src_h, src_w).astype(np.float32), src_w, src_h


def _spans(mask, min_len: int = 1) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    cur: tuple[int, int] | None = None
    for i, on in enumerate(mask):
        if on:
            cur = (i, i) if cur is None else (cur[0], i)
        elif cur is not None:
            out.append(cur)
            cur = None
    if cur is not None:
        out.append(cur)
    return [s for s in out if s[1] - s[0] + 1 >= min_len]


def detect_tile_grid(
    source: Path,
    samples_per_s: float = 0.2,
    black_level: float = TILE_BLACK_LEVEL,
    gutter_q: float = TILE_GUTTER_Q,
    min_side: int = TILE_MIN_SIDE,
    min_agreement: float = 0.66,
) -> list[dict[str, Any]]:
    """Every tile in the source's Zoom layout, with how much each one moves.

    Makes no assumption about how many tiles there are or where they sit.
    zHchVGBX9iA is a 2-over-1 grid: "187TH DC" at x0-639 and "Judge Boyd" at
    x720-1199 across the top, an empty witness stand at x320-959 underneath.

    Two properties of the real frames rule out the obvious approaches, and both
    were measured rather than assumed:

    * There is no black ROW between the upper and lower bands - the tiles touch
      at y359/360 - so connected-component labelling merges them into one
      region. Bands are therefore found where the dark-column SIGNATURE
      changes, not where a dark row appears.
    * Participant name labels are drawn on top of the gutters, so a gutter is
      not dark for every row of its band. Hence `gutter_q` rather than "all".

    `activity` is the per-pixel standard deviation across sampled frames: a
    talking participant moves, an empty witness stand does not. Measured on
    zHchVGBX9iA the two live tiles score 20.8 and 8.6 against the empty stand's
    1.7, a five-fold gap.

    Returns tiles as dicts of x/y/w/h/activity in SOURCE coordinates.
    """
    try:
        import numpy as np
    except ImportError:                      # pragma: no cover - numpy is present
        return []

    stack, src_w, src_h = _gray_stack(source, samples_per_s)
    if stack is None or len(stack) < 2:
        return []

    def layout(frame) -> tuple[tuple[int, int, int, int], ...]:
        dark = frame < black_level
        # Band boundaries: rows whose dark-column signature differs sharply
        # from the row above. A tile edge changes many columns at once.
        churn = np.abs(np.diff(dark.astype(np.int8), axis=0)).sum(axis=1)
        cuts = ([0] + [int(i) + 1 for i in np.where(churn > src_w * 0.10)[0]]
                + [src_h])
        found: list[tuple[int, int, int, int]] = []
        for top, bot in zip(cuts, cuts[1:]):
            if bot - top < min_side:
                continue
            gutter = dark[top:bot, :].mean(axis=0) >= gutter_q
            for x1, x2 in _spans(~gutter, min_side):
                # Tiles in one band are not always the same height, so trim
                # padding off each tile's own top and bottom.
                col = dark[top:bot, x1:x2 + 1]
                keep = _spans(~(col.mean(axis=1) >= gutter_q), min_side)
                if not keep:
                    continue
                y1, y2 = keep[0][0] + top, keep[-1][1] + top
                found.append((x1, y1, x2 - x1 + 1, y2 - y1 + 1))
        return tuple(sorted(found))

    # Segment every sampled frame separately and keep the layout only if most
    # of them agree. Averaging first looks tidier and is wrong: over a 34-minute
    # section participants join and leave, and the mean of two different Zoom
    # layouts is a grid that appears in no actual frame. Measured on
    # JgvW7oCQxuI:3211 the averaged mask invented a 1205x178 tile, and on
    # 4zkUTUavW4I:116 a 640x143 sliver, in both cases displacing a correct
    # fallback with confident nonsense.
    # Vote on how MANY tiles there are, not on their exact pixels. Measured
    # across the sampled frames: the count is stable where the layout is stable
    # (zHchVGBX9iA, a 2-over-1 grid, shows 3 tiles in 20 of 21 frames) while the
    # exact boxes agree only 8 times in 21, because an edge moves a pixel or two
    # between frames. Voting on exact tuples therefore rejected a layout that
    # never actually changed.
    #
    # Where the layout really does change mid-section the count says so and this
    # returns nothing, which is correct: 4zkUTUavW4I splits 217/198 between two
    # tiles and one, and JgvW7oCQxuI 37/26, as participants join and leave over
    # half an hour. Those fall back to halving the frame, which is what produced
    # the approved renders.
    per_frame = [layout(f) for f in stack]
    counts = Counter(len(b) for b in per_frame if b)
    if not counts:
        return []
    modal, agree = counts.most_common(1)[0]
    if not modal or agree / float(len(stack)) < min_agreement:
        log.info("framing: layout unstable (%d/%d frames show %d tiles)",
                 agree, len(stack), modal)
        return []

    # Median box per tile position, over the frames that saw the modal count.
    agreeing = [b for b in per_frame if len(b) == modal]
    tiles: list[dict[str, Any]] = []
    for idx in range(modal):
        xs = sorted(b[idx][0] for b in agreeing)
        ys = sorted(b[idx][1] for b in agreeing)
        ws = sorted(b[idx][2] for b in agreeing)
        hs = sorted(b[idx][3] for b in agreeing)
        mid = len(agreeing) // 2
        x, y, w, h = xs[mid], ys[mid], ws[mid], hs[mid]
        act = float(stack[:, y:y + h, x:x + w].std(axis=0).mean())
        tiles.append({"x": int(x), "y": int(y), "w": int(w), "h": int(h),
                      "activity": round(act, 2)})
    return tiles


def detect_tile_crops(
    source: Path,
    inset: int = 6,
    samples_per_s: float = 0.2,
    min_agreement: float = 0.5,
) -> tuple[str, str] | None:
    """Content rectangle of each half of a side-by-side 2-up, measured separately.

    `detect_content_crop` finds one rectangle for the whole frame, which is the
    union of both tiles. On this docket the two tiles are not the same shape —
    measured on JgvW7oCQxuI at four separate beats, all agreeing: the left tile
    holds 640x360 of picture and the right tile 640x500, both starting at y=180
    inside a 1280x720 frame. A single crop of 1280x476 therefore leaves 116px of
    black under the left tile and cuts 24px off the bottom of the right one, so
    the stacked pair renders with a black stripe through the middle.

    `inset` trims a few pixels off every edge to lose Zoom's active-speaker
    highlight, which is a bright green rectangle drawn just inside the tile
    border and reads as a rendering glitch once the tile is blown up to 1080
    wide.

    Returns (left_crop, right_crop) as ffmpeg `crop=` arguments in the SOURCE
    frame's coordinates, or None when the halves are not stably letterboxed.
    """
    src_w, src_h = probe_dimensions(source)
    if not src_w or not src_h:
        return None

    # Prefer a measured grid. Only fall back to halving the frame when the
    # layout has no gutters to measure, which is the 2-up this function was
    # originally written for.
    grid = detect_tile_grid(source, samples_per_s=samples_per_s)
    if len(grid) >= 2:
        ranked = sorted(grid, key=lambda t: -t["activity"])
        best, second = ranked[0], ranked[1]
        if second["activity"] < best["activity"] * DEAD_TILE_ACTIVITY_RATIO:
            log.info("framing: one live tile of %d (activity %.1f vs %.1f) - "
                     "not forcing a duo onto furniture",
                     len(grid), best["activity"], second["activity"])
            return None
        pair = sorted((best, second), key=lambda t: t["x"])
        cuts: list[str] = []
        for t in pair:
            w = t["w"] - 2 * inset
            h = t["h"] - 2 * inset
            if w < 32 or h < 32:
                break
            w -= w % 2
            h -= h % 2
            cuts.append(f"crop={w}:{h}:{t['x'] + inset}:{t['y'] + inset}")
        if len(cuts) == 2:
            log.info("framing: %d tiles measured, using %s | %s",
                     len(grid), cuts[0], cuts[1])
            return cuts[0], cuts[1]

    half = src_w // 2

    out: list[str] = []
    for side, x_off in (("left", 0), ("right", half)):
        boxes = _content_boxes(source, half, src_h, x_off, samples_per_s)
        if not boxes:
            return None
        (x1, x2, y1, y2), agree = Counter(boxes).most_common(1)[0]
        if agree / float(len(boxes)) < min_agreement:
            log.info("framing: %s tile unstable (%d/%d frames agree)",
                     side, agree, len(boxes))
            return None
        w = x2 - x1 + 1 - 2 * inset
        h = y2 - y1 + 1 - 2 * inset
        if w < 32 or h < 32:
            return None
        # ffmpeg's crop rejects odd sizes on some pixel formats, and libx264
        # needs even dimensions after scaling anyway.
        w -= w % 2
        h -= h % 2
        out.append(f"crop={w}:{h}:{x_off + x1 + inset}:{y1 + inset}")

    return out[0], out[1]


def plan_fill_window(
    tile_crop: str,
    target_aspect: float,
    focus: tuple[float, float] = (0.5, 0.5),
    zoom: float = 1.0,
) -> str:
    """Narrow a tile's crop to `target_aspect`, centred on a point of interest.

    The tiles do not match the shape of the slot they have to fill, so
    something has to give: either the picture is letterboxed into the slot
    (black bands, which is what we are removing) or it is cropped to the slot's
    aspect. This crops.

    `focus` is where the subject sits inside the tile as a fraction of its own
    width and height, so it survives the tile being re-measured. The window is
    clamped to the tile, which means a subject near an edge ends up off-centre
    rather than the window running outside the picture and reintroducing black.

    `zoom` above 1.0 takes a smaller window and therefore magnifies further.
    """
    m = re.fullmatch(r"crop=(\d+):(\d+):(\d+):(\d+)", tile_crop.strip())
    if not m:
        raise ValueError(f"not a crop expression: {tile_crop!r}")
    tw, th, tx, ty = (int(v) for v in m.groups())

    if tw / th > target_aspect:          # too wide: take height, trim width
        win_h = th
        win_w = target_aspect * th
    else:                                 # too tall: take width, trim height
        win_w = tw
        win_h = tw / target_aspect
    win_w = int(win_w / max(1.0, zoom))
    win_h = int(win_h / max(1.0, zoom))
    win_w -= win_w % 2                     # libx264 wants even dimensions
    win_h -= win_h % 2

    x = int(round(focus[0] * tw - win_w / 2))
    y = int(round(focus[1] * th - win_h / 2))
    x = max(0, min(x, tw - win_w))
    y = max(0, min(y, th - win_h))
    return f"crop={win_w}:{win_h}:{tx + x}:{ty + y}"


def probe_dimensions(path: Path) -> tuple[int, int]:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json", str(path)],
        capture_output=True, text=True, check=True, timeout=120,
    )
    streams = json.loads(proc.stdout).get("streams") or [{}]
    return int(streams[0].get("width", 0)), int(streams[0].get("height", 0))


def probe_duration(path: Path) -> float:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=True, timeout=120,
    )
    return float(json.loads(proc.stdout)["format"]["duration"])


# ------------------------------------------------------------------ dead air


def detect_silences(
    source: Path,
    noise_db: float = -30.0,
    min_silence_s: float = 0.30,
) -> list[tuple[float, float]]:
    """Silent spans in the file, in FILE time (t=0 is the file's first frame).

    One decode pass over the audio only — measured at 7.3s for the 2192s
    Thompson section, so there is no reason to sample or to run this per beat.

    The threshold is absolute, not relative: a courtroom mic carries constant
    room tone, and -30dBFS sits below that tone but above the level of anyone
    actually speaking. Verified against the shipped 34.55s Thompson short,
    where it found 10 spans totalling 4.75s — 13.7% of a short that had been
    called finished.
    """
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(source),
         "-af", f"silencedetect=n={noise_db}dB:d={min_silence_s}",
         "-f", "null", "-"],
        capture_output=True, text=True, timeout=1800,
    )
    spans: list[tuple[float, float]] = []
    start: float | None = None
    for m in re.finditer(r"silence_(start|end): (-?[\d.]+)", proc.stderr):
        kind, value = m.group(1), float(m.group(2))
        if kind == "start":
            start = value
        elif start is not None:
            spans.append((start, value))
            start = None
    return spans


def plan_silence_trim(
    segments: list[Segment],
    silences: list[tuple[float, float]],
    offset_s: float,
    min_silence_s: float = 0.40,
    keep_s: float = 0.12,
    min_piece_s: float = 0.35,
    edge_keep_s: float = 0.05,
) -> list[Segment]:
    """Split each beat around its own dead air, returning the pieces to keep.

    Beats are chosen by where the *meaning* starts and stops, so they carry the
    pauses that sat between those points — page turns, the judge reading, a
    defendant deciding what to say. On a 9:16 short those pauses are the whole
    difference between a clip that holds and one that gets swiped.

    What this deliberately does NOT do is close every gap. `keep_s` leaves
    120ms of the silence at each edge, because speech has attack and decay that
    silencedetect does not count as sound: cutting flush to the detected
    boundary clips the consonant off the front of the next word and the edit
    reads as broken rather than tight. A pause shorter than `min_silence_s`
    survives untouched — under half a second it is breath, not dead air, and
    removing it makes courtroom speech sound machine-gunned.

    `min_piece_s` refuses a cut that would leave a fragment too short to read as
    a shot. Two cuts 200ms apart is a stutter, not pacing.

    Silences are in file time; segments and the return value are in source time.
    Keeping the units apart is why offset_s is required rather than optional —
    getting it wrong desyncs every burned-in caption from the audio, and the
    render still succeeds.
    """
    kept: list[Segment] = []

    for seg in segments:
        a = seg.start_s - offset_s
        b = seg.end_s - offset_s
        pieces: list[tuple[float, float]] = []
        cursor = a

        for s0, s1 in sorted(silences):
            if s1 <= a or s0 >= b:
                continue
            s0, s1 = max(s0, a), min(s1, b)
            if s1 - s0 < min_silence_s:
                continue

            # At a beat's own edges there is no speech on the outside to
            # protect, so the pad shrinks. Leading dead air is the worst case
            # of all — a hook that opens on half a second of nothing has
            # already lost the swipe.
            head_pad = edge_keep_s if s0 <= a + 0.05 else keep_s
            tail_pad = edge_keep_s if s1 >= b - 0.05 else keep_s
            cut0, cut1 = s0 + head_pad, s1 - tail_pad
            if cut1 - cut0 < 0.10:
                continue
            if cut0 - cursor < min_piece_s and cut0 > a:
                continue
            pieces.append((cursor, cut0))
            cursor = cut1

        pieces.append((cursor, b))
        for p0, p1 in pieces:
            if p1 - p0 >= 0.08:
                kept.append(Segment(p0 + offset_s, p1 + offset_s))

    return kept


def map_words_to_timeline(
    words: list[Word], segments: list[Segment], absorb_gap_s: float = 1.5
) -> list[Word]:
    """Re-time transcript words from source time into output-clip time.

    A word landing inside a *trimmed silence* is snapped back to the end of the
    piece before it rather than dropped. Auto-caption timings drift by a
    fraction of a second against the audio, so a word can be timestamped inside
    a gap that genuinely held no speech, and dropping it would silently delete
    a caption the viewer can hear being spoken.

    `absorb_gap_s` is what keeps that from swallowing the clip. Only gaps short
    enough to be a removed pause get absorbed; the gap between two beats is
    minutes of unrelated docket. Without this bound the Thompson cut mapped
    15,568 words onto a 32.9s timeline — every word spoken between the second
    beat and the third, which are 22 minutes apart.
    """
    out: list[Word] = []
    elapsed = 0.0
    for i, seg in enumerate(segments):
        hi = seg.end_s
        if i + 1 < len(segments):
            gap = segments[i + 1].start_s - seg.end_s
            if 0.0 < gap <= absorb_gap_s:
                hi = segments[i + 1].start_s
        for w in words:
            if seg.start_s <= w.t < hi:
                t = elapsed + max(0.0, min(w.t, seg.end_s) - seg.start_s)
                out.append(type(w)(t=t, w=w.w))
        elapsed += seg.duration
    out.sort(key=lambda w: w.t)
    return out


# --------------------------------------------------------------- acquisition


# WHY THE CLIENT HAS TO BE PINNED. With no PO-token provider configured,
# yt-dlp falls back to the ANDROID_VR player client, and googlevideo now serves
# those URLs only as a short prefix: measured 2026-08-18 on a freshly extracted
# URL, `Range: bytes=0-2097151` returned 206 but `bytes=0-4194303` and *every*
# mid-file offset returned 403. Sequential 1 MB chunks died at the fourth.
#
# That is what broke `--download-sections`. The flag hands the URL to ffmpeg,
# ffmpeg opens an HTTP input with a single open-ended `Range: bytes=0-`, and
# the server refuses it — so the section fails instantly with 403 while
# yt-dlp's own small-range probes still succeed. It is not DRM, not this video,
# and not rate limiting: RzjGikNbHMA, which had downloaded fine before,
# reproduces the identical pattern today.
#
# WEB_EMBEDDED_PLAYER still returns the full adaptive ladder (136 avc1 720p +
# 140 m4a) on URLs that accept both open-ended and mid-file ranges, which is
# exactly what ffmpeg needs to seek into hour two of a livestream and pull only
# the requested window. The rest are fallbacks: mweb/tv_simply/android offer
# only itag 18 (muxed 360p) but still render, and "default" is kept last so a
# video with embedding disabled is still attempted the old way.
SECTION_PLAYER_CLIENTS = (
    "web_embedded", "mweb", "tv_simply", "android", "default",
)


def download_section(
    video_id: str, start_s: float, end_s: float, out_path: Path
) -> tuple[Path, float]:
    """Fetch just the requested window.

    Returns (path, section_start_s). Everything downstream expresses cut points
    relative to section_start_s, since the downloaded file's t=0 corresponds to
    that moment in the source video.
    """
    section_start = max(0.0, start_s - SECTION_MARGIN_S)
    section_end = end_s + SECTION_MARGIN_S

    # The cached file is only reusable if it holds the same window. Keying the
    # name on the window itself means changing pad_before_s can't silently
    # return a file whose t=0 is somewhere else — which would shift every
    # downstream trim and desync the burned-in captions from the audio.
    out_path = out_path.with_name(
        f"{out_path.stem}_{int(section_start)}-{int(section_end)}{out_path.suffix}"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if out_path.exists():
        return out_path, section_start

    last_error: RuntimeError | None = None
    for client in SECTION_PLAYER_CLIENTS:
        try:
            _run(
                [
                    "yt-dlp", "--no-warnings", "--ignore-config",
                    # A single transient 403 from googlevideo otherwise kills
                    # the whole unattended run. Observed 2026-08-10: the
                    # section download failed with "403 Forbidden" while the
                    # same command succeeded moments later, so the URL was
                    # expiring or being throttled mid-transfer rather than the
                    # video being unavailable.
                    "--retries", "10",
                    "--fragment-retries", "10",
                    "--extractor-retries", "5",
                    "--retry-sleep", "exp=2:60",
                    # Node is what makes the non-default clients usable at all:
                    # without a JS runtime the n-signature challenge goes
                    # unsolved and web_embedded reports "Requested format is
                    # not available", which is how the alternate clients were
                    # wrongly ruled out earlier. Node 22 is on PATH; if it ever
                    # isn't, yt-dlp warns and degrades rather than failing.
                    "--js-runtimes", "node",
                    *(() if client == "default" else
                      ("--extractor-args", f"youtube:player_client={client}")),
                    "--download-sections",
                    f"*{section_start:.2f}-{section_end:.2f}",
                    # Without this, the file starts at the preceding keyframe
                    # and every timestamp downstream drifts by up to several
                    # seconds.
                    "--force-keyframes-at-cuts",
                    # Explicitly avc1+mp4a rather than "best mp4". The generic
                    # selector picked itag 398 (AV1), which costs a re-encode
                    # on the way into the render chain. The trailing branches
                    # cover the fallback clients, which only expose itag 18.
                    "-f",
                    "bv*[vcodec^=avc1][height<=1080]+ba[acodec^=mp4a]/"
                    "bv*[height<=1080]+ba/best[ext=mp4]/best",
                    "--merge-output-format", "mp4",
                    "-o", str(out_path),
                    f"https://www.youtube.com/watch?v={video_id}",
                ],
                timeout=3600,
            )
        except RuntimeError as exc:
            # A half-written section is worse than none: the next client would
            # otherwise resume onto a file whose t=0 came from a different
            # stream. Clear the partials before falling through.
            last_error = exc
            for stale in out_path.parent.glob(f"{out_path.stem}*.part"):
                stale.unlink(missing_ok=True)
            out_path.unlink(missing_ok=True)
            continue

        if out_path.exists():
            return out_path, section_start

    raise RuntimeError(
        f"section download produced no file for {video_id} "
        f"(tried {', '.join(SECTION_PLAYER_CLIENTS)})"
    ) from last_error


# ------------------------------------------------------------------ captions


# YouTube's auto-captions carry two things that are not speech: ">>" as a
# speaker-change marker, and bracketed sound cues like "[clears throat]" or
# "[inaudible]". Both were rendering on screen — the shipped Thompson short
# burned in "[CLEARS THROAT]" mid-sentence, and ">> YOU'RE SAYING" appeared in
# the re-cut. CONTENT_SPEC §5 requires captions be verbatim, which is a rule
# about not paraphrasing what was *said*; a speaker-change glyph was never said
# by anyone, so removing it is not an edit to the testimony.
_CAPTION_ARTIFACT = re.compile(r">>+|\[[^\]]*\]")


def strip_caption_artifact(token: str) -> str:
    """Drop non-speech auto-caption markers, returning "" if nothing remains."""
    return _CAPTION_ARTIFACT.sub("", token).strip()


def group_words(
    words: list[Word], max_chars: int, max_lines: int,
    max_words: int | None = None,
) -> list[list[Word]]:
    """Chunk the word stream into caption cards of at most max_lines lines.

    Grouped by the wrap the card will actually get, not by a character budget.
    A budget of max_chars * max_lines is not the same constraint: greedy
    wrapping fills line 1 to max_chars and drops the remainder on line 2, so a
    44-character budget at 22x2 routinely produced a 22/26 split. That is how
    "KILLED? YES, INCLUDING MY" — 25 characters against a documented 22-char
    limit — reached a published short. CONTENT_SPEC §5 sets the limit per line
    because the constraint is legibility at thumb distance, and only the line
    length is visible to a viewer.
    """
    groups: list[list[Word]] = []
    current: list[Word] = []

    for w in words:
        if not w.w.strip():
            continue
        trial = current + [w]
        # A word cap, when set, binds before the character cap. Measured across
        # nine current high-view shorts, cards hold 1-4 words (mode 3) and the
        # character budget never becomes the constraint.
        if max_words and current and len(trial) > max_words:
            groups.append(current)
            current = [w]
        elif current and len(_wrap([x.w.strip() for x in trial], max_chars)) > max_lines:
            groups.append(current)
            current = [w]
        else:
            current = trial

    if current:
        groups.append(current)
    return groups


def _wrap(tokens: list[str], max_chars: int) -> list[list[int]]:
    """Distribute token indices across lines, returning index lists per line.

    Wraps unconditionally. It used to stop opening new lines once it reached
    max_lines and let the final line run past max_chars instead — silently,
    since the card still rendered. group_words is what bounds the line count
    now, by only grouping words that fit.
    """
    lines: list[list[int]] = [[]]
    width = 0
    for i, tok in enumerate(tokens):
        add = len(tok) + (1 if lines[-1] else 0)
        if lines[-1] and width + add > max_chars:
            lines.append([])
            width = len(tok)
        else:
            width += add
        lines[-1].append(i)
    return lines


def _ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def build_ass(
    words: list[Word],
    timeline_offset_s: float,
    total_duration_s: float,
    style: dict[str, Any],
    end_card: dict[str, Any] | None,
    out_path: Path,
    turns: list[tuple[float, str]] | None = None,
) -> Path:
    """Burned-in caption cards, in one of four treatments.

    `style["animation"]` picks the treatment. The mechanism for the animated
    ones is not invented here — it is what every current generator ships:
    a static card with the active word carrying `\\fscx/\\fscy` inside a `\\t()`,
    anchored by the style rather than by `\\move`. Checked against
    nicolaigaina/ai-video-captions (`backend/subtitles.py`, pushed 2026-03-27),
    sebetancurch/auto-caption (`autocaption/ass_builder.py`, 2026-07-17) and
    kperreau/wordsubgen (`generator.go`). None of the three uses `\\move`.

      plain      one event per card, no per-word treatment, short fade in/out.
                 What editors doing serious/broadcast work default to — the
                 r/editors thread on a CNN captioning workflow treats
                 "professional captioning" and "capcut adhd style captions" as
                 two different jobs.
      pop        card re-rendered per word, active word scales 112 -> 100 over
                 70ms and stays white. Motion without colour.
      pop_color  as pop, plus the active word recoloured. The mainstream 2026
                 look.
      highlight  colour change only, no motion. The original behaviour, kept so
                 old renders stay reproducible.

    Which of these is right is a taste call and it is not settled: the same
    search that found the pop mechanism also found the field mocking it —
    "flashing words at someone rapidly is optimized for being annoying and
    attention grabbing, not for readability" (r/mildlyinfuriating, 2026-05-08),
    and "big yellow subtitles... when mom and dad are doing it, it's not cool
    anymore" (r/smallbusiness, 2026-07-27). So all four are buildable and the
    choice is made by looking at rendered output, not by argument.

    One event per word for the animated modes rather than karaoke (\\k) tags:
    far more predictable across libass versions, and it is what the three
    reference implementations do.

    timeline_offset_s converts absolute source timestamps into output-clip time.
    """
    # Cleaned before grouping, not at render time: the artifacts change token
    # lengths, so stripping them afterwards would wrap the lines against text
    # that is not what ends up on screen.
    words = [
        type(w)(t=w.t, w=strip_caption_artifact(w.w))
        for w in words
        if strip_caption_artifact(w.w)
    ]

    max_chars = style.get("max_chars_per_line", 22)
    max_lines = style.get("max_lines", 2)
    upper = style.get("uppercase", True)
    primary = style.get("primary_color", "&H00FFFFFF")
    highlight = style.get("highlight_color", "&H0000D7FF")

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,{style.get('font', 'Arial Black')},{style.get('font_size', 74)},{primary},{primary},{style.get('outline_color', '&H00000000')},&H80000000,-1,0,0,0,100,100,0,0,1,{style.get('outline', 5)},{style.get('shadow', 2)},2,60,60,{style.get('margin_v', 420)},1
Style: Card,{style.get('font', 'Arial Black')},64,{highlight},{highlight},&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,5,2,5,60,60,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    # Speaker-anchored caption slots. `turns` is [(output_time, speaker)]
    # sorted ascending; `slot_margins` maps a speaker to the MarginV that puts
    # the text beside them. ASS carries MarginV per Dialogue line, so this
    # needs no second Style and no \pos — the alignment stays \an2 and only the
    # distance from the bottom changes.
    slot_margins: dict[str, int] = style.get("slot_margins") or {}
    default_margin = int(style.get("margin_v", 420))

    def speaker_at(t: float) -> str | None:
        if not turns:
            return None
        who = None
        for turn_t, name in turns:
            if turn_t <= t + 1e-9:
                who = name
            else:
                break
        return who

    def margin_at(t: float) -> int:
        return slot_margins.get(speaker_at(t) or "", default_margin)

    anim = style.get("animation", "highlight")
    pop_scale = int(style.get("pop_scale", 112))
    pop_ms = int(style.get("pop_ms", 70))
    card_fade_ms = int(style.get("card_fade_ms", 80))

    def active(token: str) -> str:
        """The active word's markup for the chosen treatment.

        `pop` and `pop_color` scale ONE word inside a line that libass then
        re-lays-out, so the whole block shifts. Measured on short_v3_slots.mp4
        by rendering its own .ass over black and taking the ink box per frame:
        on a word change the line moved 33px left and grew 65px, then snapped
        back over two frames — every word, all the way through. That is the
        jitter, and it is why `card_punch` exists: the scale moves to the card
        as a whole, where it cannot reflow anything relative to anything else.
        """
        if anim == "pop":
            return (f"{{\\fscx{pop_scale}\\fscy{pop_scale}"
                    f"\\t(0,{pop_ms},\\fscx100\\fscy100)}}{token}{{\\r}}")
        if anim == "pop_color":
            return (f"{{\\c{highlight}\\fscx{pop_scale}\\fscy{pop_scale}"
                    f"\\t(0,{pop_ms},\\fscx100\\fscy100)}}{token}{{\\r}}")
        return f"{{\\c{highlight}}}{token}{{\\c{primary}}}"

    def card_prefix(is_first_event: bool) -> str:
        """Scale applied to the entire card, once, as it appears."""
        if anim != "card_punch" or not is_first_event:
            return ""
        return (f"{{\\fscx{pop_scale}\\fscy{pop_scale}"
                f"\\t(0,{pop_ms},\\fscx100\\fscy100)}}")

    # Cards are grouped within a speaker's run, never across a change. A card
    # holding the end of one person's sentence and the start of the other's
    # would have to sit in one slot or the other and would be wrong beside
    # whichever it chose.
    runs: list[list[Word]] = []
    for word in words:
        who = speaker_at(word.t - timeline_offset_s)
        if runs and speaker_at(runs[-1][0].t - timeline_offset_s) == who:
            runs[-1].append(word)
        else:
            runs.append([word])

    max_words = style.get("max_words_per_card")
    cards: list[tuple[list[Word], int]] = []
    for run in runs:
        slot = margin_at(run[0].t - timeline_offset_s)
        for g in group_words(run, max_chars, max_lines, max_words):
            cards.append((g, slot))

    timed: list[tuple[float, float, str, int]] = []
    for group, marginv in cards:
        # CONTENT_SPEC §9: the audio ships as recorded, every text surface is
        # censored. Captions are a text surface — they get indexed and read
        # without the footage around them.
        tokens = [censor(w.w.strip()) for w in group]
        if upper:
            tokens = [t.upper() for t in tokens]
        line_map = _wrap(tokens, max_chars)
        plain_text = "\\N".join(
            " ".join(tokens[j] for j in line) for line in line_map
        )

        if anim == "plain":
            # One event for the whole card. Nothing moves inside it, so
            # re-emitting it per word would only give libass more chances to
            # collide with itself.
            start = group[0].t - timeline_offset_s
            end = group[-1].t - timeline_offset_s + 0.45
            if end > 0 and start < total_duration_s:
                start = max(0.0, start)
                end = min(total_duration_s, max(end, start + 0.05))
                fade = f"{{\\fad({card_fade_ms},{card_fade_ms})}}" if card_fade_ms else ""
                timed.append((start, end, fade + plain_text, marginv))
            continue

        for i, word in enumerate(group):
            start = word.t - timeline_offset_s
            end = (
                group[i + 1].t - timeline_offset_s
                if i + 1 < len(group)
                else start + 0.45
            )
            if end <= 0 or start >= total_duration_s:
                continue
            start = max(0.0, start)
            end = min(total_duration_s, max(end, start + 0.05))

            rendered_lines = []
            for line in line_map:
                parts = [
                    active(tokens[j]) if j == i else tokens[j] for j in line
                ]
                rendered_lines.append(" ".join(parts))
            timed.append((start, end,
                          card_prefix(i == 0) + "\\N".join(rendered_lines),
                          marginv))

    # A card's last word had no successor to end against, so it ran for a flat
    # 0.45s — straight over the start of the next card. libass does not discard
    # a collision, it stacks it: two 2-line cards became FOUR lines on screen,
    # which is what the shipped Thompson short opens on (events 0:01.27-1.72 and
    # 0:01.39-1.75). Clamping every event against its successor is the general
    # fix; the last-word case was only where it showed.
    timed.sort(key=lambda e: e[0])
    events: list[str] = []
    for i, (start, end, text, marginv) in enumerate(timed):
        if i + 1 < len(timed):
            end = min(end, timed[i + 1][0])
        if end - start < 0.02:
            continue
        events.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Main,,0,0,"
            f"{marginv},,{text}"
        )

    if end_card and end_card.get("enabled"):
        card_len = float(end_card.get("duration_s", 2.0))
        card_start = max(0.0, total_duration_s - card_len)
        events.append(
            f"Dialogue: 1,{_ass_time(card_start)},{_ass_time(total_duration_s)},"
            f"Card,,0,0,0,,{end_card.get('text', 'FULL CASE IN DESCRIPTION')}"
        )

    out_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return out_path


# ------------------------------------------------------------------ renderers


def _concat_filter(
    segments: list[Segment], offset_s: float, join_fade_s: float = 0.015
) -> tuple[str, str, str]:
    """Build trim/concat filter chains for N segments of one input.

    Every join gets a 15ms fade on the audio only. A hard splice lands wherever
    the waveform happened to be, and joining two non-zero samples puts a step
    discontinuity into the signal — a click. It is inaudible as a fade at 15ms
    and it is the standard fix; the video stays a hard cut, because the jump
    IS the edit.

    This matters more now than it did with four hand-placed beats: trimming
    dead air turns a 4-piece cut into an 11-piece one, so the same short went
    from 3 joins to 10.
    """
    parts: list[str] = []
    for i, seg in enumerate(segments):
        a = max(0.0, seg.start_s - offset_s)
        b = max(a + 0.05, seg.end_s - offset_s)
        fade = ""
        if join_fade_s > 0:
            d = min(join_fade_s, (b - a) / 4.0)
            fade = (f",afade=t=in:st=0:d={d:.3f}"
                    f",afade=t=out:st={b - a - d:.3f}:d={d:.3f}")
        parts.append(
            f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS[v{i}];"
            f"[0:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS{fade}[a{i}]"
        )
    pairs = "".join(f"[v{i}][a{i}]" for i in range(len(segments)))
    concat = f"{pairs}concat=n={len(segments)}:v=1:a=1[vc][ac]"
    return ";".join(parts), concat, "[vc]"


# The brand folder was moved into a per-project Desktop folder at some point
# and the old absolute path stopped resolving. _watermark_chain degrades to "no
# watermark" rather than failing the render, so every short since then went out
# unbranded with only a log line to say so. Candidates rather than one path,
# newest location first, so a move costs a warning instead of the mark.
_INTRO_CANDIDATES = [
    Path(r"D:\Boyd Clips\boyd-brand\sting_v2.mp4"),
    Path(r"C:\Users\natha\OneDrive\Desktop\boyd-brand\sting_v2.mp4"),
    Path(__file__).resolve().parents[2] / "assets" / "brand" / "sting_v2.mp4",
]


def resolve_intro(configured: str | None = None) -> Path | None:
    """The branded sting that opens the long-form, or None.

    Candidates rather than one path, for the same reason the watermark uses
    them: the brand folder has already moved once, and the failure mode was a
    silent one - every render went out unbranded with a single log line to say
    so.

    sting_v2.mp4 is 2.6s at 1920x1080 WITH an audio stream. The _SLOW variants
    are 5.1-7.7s and silent; a silent branch forces render_longform to
    synthesise an anullsrc to keep concat happy, and 7.7s of branding in front
    of a cold open is retention paid for nothing.
    """
    if configured:
        p = Path(configured)
        return p if p.is_file() else None
    return next((p for p in _INTRO_CANDIDATES if p.is_file()), None)


_WATERMARK_CANDIDATES = [
    Path(r"D:\Boyd Clips\boyd-brand\watermarks_v2\wm_brand_halo_40.png"),
    Path(r"C:\Users\natha\OneDrive\Desktop\boyd-brand\watermarks_v2\wm_brand_halo_40.png"),
    Path(__file__).resolve().parents[2] / "assets" / "brand" / "wm_brand_halo_40.png",
]
DEFAULT_WATERMARK = next(
    (p for p in _WATERMARK_CANDIDATES if p.is_file()), _WATERMARK_CANDIDATES[0]
)


def _watermark_chain(
    cfg: dict[str, Any],
    w: int,
    h: int,
    in_label: str,
    out_label: str,
    width_frac: float,
    wm_index: int = 1,
    y: int | list[int] | None = None,
    right_x: int | None = None,
) -> tuple[list[str], str]:
    """Overlay the channel mark top-right. Returns (extra ffmpeg inputs, filter).

    Top-right because YouTube's own player controls and branding watermark both
    live bottom-right, and the progress bar eats the bottom edge on hover. The
    mark file already carries its opacity and halo baked in, so this only scales
    and places it — no alpha maths here, which keeps the one chosen file the
    single source of truth.

    When disabled or missing, returns a `null` pass-through on the same labels so
    a missing asset degrades to "no watermark" rather than failing a render that
    is otherwise fine.
    """
    raw = cfg.get("watermark", DEFAULT_WATERMARK)
    if raw in (None, False, ""):
        return [], f"[{in_label}]null[{out_label}]"
    path = Path(raw)
    if not path.is_file():
        log.warning("watermark not found, rendering without it: %s", path)
        return [], f"[{in_label}]null[{out_label}]"

    frac = float(cfg.get("watermark_width_frac", width_frac))
    margin = int(round(w * float(cfg.get("watermark_margin_frac", 0.035))))
    wm_w = int(round(w * frac))
    # `y` places the mark inside the PICTURE rather than inside the canvas. The
    # court's frame carries its own black band across the top, so the default
    # margin put the mark on black where it read as a channel bug rather than a
    # watermark over the footage.
    #
    # A list of positions puts one mark on each tile. When the 2-up is stacked
    # a single top-right mark lands on the upper participant only, leaving the
    # judge's half unbranded — castillo_FINAL.mp4 carries the mark over Judge
    # Boyd's tile, which is the house precedent.
    tops = [margin] if y is None else ([y] if isinstance(y, int) else list(y))
    tops = [int(v) for v in tops]

    # `right_x` is the right edge of the PICTURE to hug, in canvas pixels. The
    # canvas edge is only the right place to hug when the footage fills the
    # frame. This docket's 2-up does not: measured on 2XkPnvstmRQ, Judge Boyd's
    # tile ends at x=1791 of 1920, so the canvas-relative default put 53 of the
    # mark's 115 px on the black beside her tile and the mark read as broken.
    # Half the outer margin inside the tile, so it sits as a corner bug rather
    # than floating.
    if right_x is None:
        x_expr = f"W-w-{margin}"
    else:
        x_expr = str(max(0, int(right_x) - wm_w - margin // 2))

    if len(tops) == 1:
        return (
            ["-i", str(path.resolve())],
            f"[{wm_index}:v]scale={wm_w}:-1[wm];"
            f"[{in_label}][wm]overlay={x_expr}:{tops[0]}[{out_label}]",
        )

    n = len(tops)
    parts = [f"[{wm_index}:v]scale={wm_w}:-1,split={n}"
             + "".join(f"[wm{i}]" for i in range(n))]
    src = in_label
    for i, top in enumerate(tops):
        dst = out_label if i == n - 1 else f"{out_label}_{i}"
        parts.append(f"[{src}][wm{i}]overlay={x_expr}:{top}[{dst}]")
        src = dst
    return ["-i", str(path.resolve())], ";".join(parts)


# Cold open (R49). Nathan, 2026-09-02: "add a 5 second or so clip of the hook
# or drama later in the vid in the beginning of long form and put 'Coming
# up...' or something". The clip is BODY footage (same crop, scale, mark) cut
# from later in the same source, labelled, faded to black, and concatenated in
# front of the sting: cold open -> sting -> body. The label is the shorts'
# caption face (Anton, white, black outline) so it reads as the channel, not as
# a stock lower-third.
COLDOPEN_LABEL = "COMING UP..."
COLDOPEN_LABEL_FONT = Path(__file__).resolve().parents[2] / "assets" / "fonts" / "Anton-Regular.ttf"
COLDOPEN_FADE_S = 0.35          # video + audio fade to black at the cold open's end
COLDOPEN_MIN_S, COLDOPEN_MAX_S = 3.0, 9.0   # "5 second or so"
# "later in the vid": the hook must come from at least this far into the body,
# or it is the opening shown twice, not a tease.
COLDOPEN_MIN_AHEAD_S = 30.0


def _ff_escape(text: str) -> str:
    """drawtext text= value: ffmpeg's filter parser eats : \\ ' and %."""
    return (text.replace("\\", "\\\\").replace(":", "\\:")
                .replace("'", "\\'").replace("%", "\\%"))


def _ff_path(path: Path) -> str:
    """fontfile= value on Windows: the drive colon has to be escaped."""
    return str(path).replace("\\", "/").replace(":", "\\:")


def coldopen_label_filter(w: int, h: int, label: str = COLDOPEN_LABEL,
                          font: Path = COLDOPEN_LABEL_FONT) -> str:
    """drawtext for the cold-open label: bottom-left, safe margins, sized to the
    canvas (the shorts' caption look). Raises if the font is missing - a cold
    open without its label is the defect, not a degraded render."""
    if not Path(font).is_file():
        raise FileNotFoundError(f"cold-open label font not found: {font}")
    size = int(round(h * 0.065))            # 70 px at 1080p
    border = max(2, int(round(size * 0.10)))
    margin_x = int(round(w * 0.045))
    margin_y = int(round(h * 0.08))
    return (f"drawtext=fontfile='{_ff_path(Path(font))}':text='{_ff_escape(label)}'"
            f":fontsize={size}:fontcolor=white:borderw={border}:bordercolor=black"
            f":x={margin_x}:y=h-th-{margin_y}")


def coldopen_label_box(w: int, h: int) -> tuple[int, int, int, int]:
    """(x0, y0, x1, y1) of the region the label occupies - what the checker
    measures. Derived from the same numbers as the filter above."""
    size = int(round(h * 0.065))
    margin_x = int(round(w * 0.045))
    margin_y = int(round(h * 0.08))
    # Anton at `size` px: cap height ~0.72*size, "COMING UP..." ~3.6*size wide
    return (margin_x, h - margin_y - size, margin_x + int(3.8 * size), h - margin_y + border_pad(size))


def border_pad(size: int) -> int:
    return max(2, int(round(size * 0.10)))


def render_longform(
    source: Path,
    offset_s: float,
    segments: list[Segment],
    cfg: dict[str, Any],
    out_path: Path,
    crop: str | None = None,
    intro: Path | None = None,
    watermark_y: int | None = None,
    watermark_right_x: int | None = None,
    coldopen: tuple[float, float] | None = None,
    coldopen_label: str = COLDOPEN_LABEL,
) -> float:
    """The case, trimmed, optionally behind a branded intro.

    `intro` is concatenated in front of the body inside the same filter graph
    rather than by a second encode, so the court footage is compressed once.
    The watermark is applied to the BODY only — the intro is already branding
    and stacking the mark on top of it reads as a mistake.

    `coldopen` = (start_s, end_s) in SOURCE-absolute seconds (same frame of
    reference as `segments`): that span is rendered first - body treatment,
    the `coldopen_label` drawn bottom-left, a fade to black - then the intro,
    then the body. R49. Requires `intro`.

    `watermark_y` anchors the mark inside the picture instead of inside the
    canvas. Measured on this docket: the court's own frame carries a black band
    across its top 279 rows at 1080p, and the default margin dropped the mark
    into it, where it sat on black instead of over the footage.
    """
    w, h = cfg.get("resolution", [1920, 1080])
    trims, concat, vlabel = _concat_filter(segments, offset_s)
    pre = f"{crop}," if crop else ""

    if coldopen is not None:
        c0, c1 = float(coldopen[0]), float(coldopen[1])
        if intro is None:
            raise ValueError("cold open needs the intro sting behind it")
        if not (COLDOPEN_MIN_S <= c1 - c0 <= COLDOPEN_MAX_S):
            raise ValueError(f"cold open {c1 - c0:.2f}s is outside "
                             f"{COLDOPEN_MIN_S:.0f}-{COLDOPEN_MAX_S:.0f}s")
        body0 = min(sg.start_s for sg in segments)
        body1 = max(sg.end_s for sg in segments)
        if not (body0 <= c0 and c1 <= body1):
            raise ValueError(f"cold open {c0:.2f}-{c1:.2f} is not inside the "
                             f"body {body0:.2f}-{body1:.2f}")
        if c0 - body0 < COLDOPEN_MIN_AHEAD_S:
            raise ValueError(f"cold open starts {c0 - body0:.1f}s into the body; "
                             f"it must come from later than {COLDOPEN_MIN_AHEAD_S:.0f}s "
                             f"(\"the hook or drama later in the vid\")")

    inputs: list[str] = ["-i", str(source)]
    intro_idx = None
    if intro is not None:
        if not Path(intro).is_file():
            raise FileNotFoundError(f"intro not found: {intro}")
        intro_idx = 1
        inputs += ["-i", str(Path(intro).resolve())]

    wm_index = 1 if intro_idx is None else 2
    wm_in, wm_filter = _watermark_chain(cfg, w, h, "vbase", "vwm", 0.06,
                                        wm_index=wm_index, y=watermark_y,
                                        right_x=watermark_right_x)
    if not wm_in:                      # no watermark file -> nothing to index
        wm_index = None
    inputs += wm_in

    # THE COLD OPEN GETS ITS OWN DECODER, SEEKED. Reading it as a sixth
    # `[0:v]trim` off input 0 makes the concat ask for the hook FIRST while the
    # split behind it is still pushing body frames from second one, so every
    # frame between the body's start and the hook is held in the graph.
    # Measured 2026-09-02 on CLAYTON (hook 409 s into the body, 1280x720):
    # "Error while filtering: Cannot allocate memory", frame=0, twice, with
    # 21 GB free - 409 s * 30 fps * 1.38 MB is ~17 GB of buffer. TORRES (hook
    # 337 s in) fit and hid the defect; every longer hearing hits it.
    # A second `-i` with an input `-ss` seeks straight to the hook and buffers
    # nothing. Input seek is frame-exact here: measured on this file,
    # `-ss T -i F` and `-i F -ss T` produced identical pixels (p99 |diff| 0),
    # and `trim=start=0` after the input seek gave the same frame again.
    cold_idx = None
    if coldopen is not None:
        cold_idx = 1 + (1 if intro_idx is not None else 0) \
                     + (1 if wm_index is not None else 0)
        inputs += ["-ss", f"{max(0.0, float(coldopen[0]) - offset_s):.3f}",
                   "-i", str(source)]

    fps = cfg.get("fps", 30)
    chain = (
        f"{vlabel}{pre}scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"fps={fps}[vbase]"
    )
    parts = [trims, concat, chain, wm_filter]

    if intro_idx is None:
        parts.append("[vwm]format=yuv420p[vout]")
        amap = "[ac]"
    else:
        # Both branches must agree on pixel format, SAR, frame rate, sample
        # rate and channel layout or concat refuses to join them.
        parts.append("[vwm]format=yuv420p,setsar=1[vbody]")
        parts.append(
            f"[{intro_idx}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"fps={fps},format=yuv420p,setsar=1[iv]"
        )
        norm = "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo"
        if _has_audio(Path(intro)):
            parts.append(f"[{intro_idx}:a]{norm}[ia]")
        else:
            # A silent intro still needs an audio stream, or concat drops it.
            parts.append(
                f"anullsrc=channel_layout=stereo:sample_rate=48000:"
                f"d={probe_duration(Path(intro)):.3f},{norm}[ia]"
            )
        parts.append(f"[ac]{norm}[ab]")
        if coldopen is None:
            parts.append("[iv][ia][vbody][ab]concat=n=2:v=1:a=1[vout][aout]")
        else:
            # The cold open is the body's own treatment (crop, scale, mark)
            # on a second trim of the same input, plus the label and a fade
            # to black so the cut into the sting is not a hard splice.
            a0, a1 = max(0.0, c0 - offset_s), c1 - offset_s
            cdur = a1 - a0
            fade_st = max(0.0, cdur - COLDOPEN_FADE_S)
            if wm_index is not None:
                # the mark input is consumed once by wm_filter; split it
                parts[3] = wm_filter.replace(f"[{wm_index}:v]", "[wmsplit0]", 1)
                parts.insert(3, f"[{wm_index}:v]split=2[wmsplit0][wmsplit1]")
                # every intermediate label ([wm], [wm0], [vwm_0]) is renamed
                # or the two chains collide on the same pad name
                cwm = (wm_filter.replace("[wm", "[cm").replace("[vbase]", "[cbase]")
                       .replace("[vwm", "[cwm").replace(f"[{wm_index}:v]", "[wmsplit1]", 1))
            else:
                cwm = "[cbase]null[cwm]"
            parts.append(
                f"[{cold_idx}:v]trim=start=0:end={cdur:.3f},setpts=PTS-STARTPTS,"
                f"{pre}scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,fps={fps}[cbase]"
            )
            parts.append(cwm)
            parts.append(
                f"[cwm]{coldopen_label_filter(w, h, coldopen_label)},"
                f"fade=t=out:st={fade_st:.3f}:d={COLDOPEN_FADE_S:.3f},"
                f"format=yuv420p,setsar=1[cv]"
            )
            parts.append(
                f"[{cold_idx}:a]atrim=start=0:end={cdur:.3f},asetpts=PTS-STARTPTS,"
                f"afade=t=in:st=0:d=0.015,"
                f"afade=t=out:st={fade_st:.3f}:d={COLDOPEN_FADE_S:.3f},{norm}[ca]"
            )
            parts.append("[cv][ca][iv][ia][vbody][ab]concat=n=3:v=1:a=1[vout][aout]")
        amap = "[aout]"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y", *inputs,
        "-filter_complex", ";".join(parts),
        "-map", "[vout]", "-map", amap,
        "-c:v", "libx264", "-preset", "medium", "-crf", str(cfg.get("crf", 20)),
        "-c:a", "aac", "-b:a", cfg.get("audio_bitrate", "192k"),
        "-movflags", "+faststart",
        str(out_path),
    ])
    dur = probe_duration(out_path)
    if coldopen is not None:
        # What the checker (tools/check_coldopen.py) measures the file against.
        side = {
            "source": str(Path(source).resolve()),
            "src_start": round(c0, 3), "src_end": round(c1, 3),
            "duration_s": round(c1 - c0, 3), "label": coldopen_label,
            "body_start": round(min(sg.start_s for sg in segments), 3),
            "body_end": round(max(sg.end_s for sg in segments), 3),
            "label_box": list(coldopen_label_box(w, h)),
            "intro": str(intro), "intro_s": round(probe_duration(Path(intro)), 3),
            "offset_s": offset_s, "crop": crop,
            "fade_s": COLDOPEN_FADE_S, "canvas": [w, h], "fps": fps,
            "output_s": round(dur, 3),
        }
        out_path.with_name(out_path.name + ".coldopen.json").write_text(
            json.dumps(side, indent=1), encoding="utf-8")
    return dur


def _has_audio(path: Path) -> bool:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
         "stream=codec_type", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, timeout=60,
    )
    return "audio" in proc.stdout


def render_short(
    source: Path,
    offset_s: float,
    segments: list[Segment],
    cfg: dict[str, Any],
    ass_path: Path | None,
    out_path: Path,
    crop: str | None = None,
    bg_crop: str | None = None,
    tile_crops: tuple[str, str] | None = None,
) -> float:
    w, h = cfg.get("resolution", [1080, 1920])
    fps = cfg.get("fps", 30)
    trims, concat, vlabel = _concat_filter(segments, offset_s)
    # Strip the source's baked-in letterbox first, or the participants end up
    # occupying a fraction of the vertical canvas.
    pre = f"{crop}," if crop else ""

    # The blurred backdrop is built by scaling the frame to fill 9:16 and centre
    # cropping, which takes a narrow vertical column out of a 16:9 frame. When
    # that frame carries its own black bars the column is mostly bar, so the
    # "blurred fill" of CONTENT_SPEC §4 renders as flat black with a smear
    # through it — which is what shipped for JgvW7oCQxuI:6698 and 4zkUTUavW4I:116.
    #
    # A backdrop may use a crop the foreground cannot. Clipping a participant
    # out of the foreground loses the content; clipping one out of a blurred,
    # darkened backdrop loses nothing, so bg_crop is accepted on much weaker
    # agreement than `crop` and simply falls back to it when the frame is full.
    bg_pre = pre or (f"{bg_crop}," if bg_crop else "")

    mode = cfg.get("vertical_mode", "auto")
    if mode == "auto":
        mode, _ = choose_vertical_layout(source, crop, cfg)

    if mode == "duo_fill":
        # Both participants, each filling half the canvas exactly, so the
        # rendered frame has no black anywhere — not at the top, not between
        # the tiles, not at the bottom. The two windows must already be cropped
        # to the slot's aspect (w : h/2); plan_fill_window does that, and it is
        # the caller's job because choosing what the window centres on is an
        # editorial decision, not a property of the file.
        if not tile_crops:
            raise ValueError("duo_fill needs tile_crops (use plan_fill_window)")
        half = h // 2
        vertical = (
            f"{vlabel}split=2[l0][r0];"
            f"[l0]{tile_crops[0]},scale={w}:{half},setsar=1[lt];"
            f"[r0]{tile_crops[1]},scale={w}:{half},setsar=1[rt];"
            f"[lt][rt]vstack=inputs=2[vv]"
        )
    elif mode == "center_crop":
        vertical = (
            f"{vlabel}{pre}scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h}[vv]"
        )
    elif mode == "split_stack":
        # A side-by-side Zoom layout letterboxed into 9:16 leaves the
        # participants tiny. Splitting the two tiles and stacking them fills
        # roughly four times as much of the canvas with the same pixels.
        sigma = max(2.0, float(cfg.get("blur_sigma", 28)) / 4.0)
        sw, sh = w // 4, h // 4

        # Each half gets its own crop when they were measured separately. The
        # halves are not the same shape on this docket, so one shared crop
        # leaves a black stripe between the stacked tiles — visible in
        # short_v2_*.mp4 before this existed.
        if tile_crops:
            left_pre, right_pre = (f"{c}," for c in tile_crops)
            bg_source = f"{tile_crops[1]},"   # the taller tile has more picture
        else:
            left_pre = f"{pre}crop=iw/2:ih:0:0,"
            right_pre = f"{pre}crop=iw/2:ih:iw/2:0,"
            bg_source = bg_pre

        # Anchored to the BOTTOM, not the top. The caption band is fixed by the
        # platform safe zone rather than by the layout, so the only free choice
        # left is which part of the picture sits under the text — and pushing
        # the stack down puts the lower participant's face below the captions
        # instead of behind them.
        vertical = (
            f"{vlabel}split=3[bg0][l0][r0];"
            f"[bg0]{bg_source}scale={sw}:{sh}:force_original_aspect_ratio=increase,"
            f"crop={sw}:{sh},gblur=sigma={sigma:.1f},"
            f"eq=brightness=-0.12:saturation=0.6,scale={w}:{h}[bgb];"
            f"[l0]{left_pre}scale={w}:-2[lt];"
            f"[r0]{right_pre}scale={w}:-2[rt];"
            f"[lt][rt]vstack=inputs=2[stk];"
            f"[bgb][stk]overlay=(W-w)/2:H-h-{STACK_BOTTOM_MARGIN}[vv]"
        )
    else:
        # Zoom court puts several people on screen; cropping to 9:16 removes
        # participants. Fit the whole frame and fill the gap with a blurred,
        # darkened copy of itself.
        #
        # The blur runs at quarter resolution and is then scaled up — visually
        # identical to a full-res gblur and several times faster.
        sigma = max(2.0, float(cfg.get("blur_sigma", 28)) / 4.0)
        darken = float(cfg.get("blur_darken", 0.55))
        sw, sh = w // 4, h // 4
        vertical = (
            f"{vlabel}split=2[bg0][fg0];"
            f"[bg0]{bg_pre}scale={sw}:{sh}:force_original_aspect_ratio=increase,"
            f"crop={sw}:{sh},gblur=sigma={sigma:.1f},"
            f"eq=brightness=-{(1 - darken) * 0.5:.3f}:saturation=0.7,"
            f"scale={w}:{h}[bgb];"
            f"[fg0]{pre}scale={w}:-2[fgs];"
            f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2[vv]"
        )

    tail = f"[vv]fps={fps}"

    # Colour grade the PICTURE, before the captions are burned in.
    #
    # Order is the whole point. Grading after `ass=` would lift the caption
    # white too, and white is already at ceiling — it would clip the text
    # edges and eat the black outline that makes them readable. Everything
    # below therefore touches court footage only.
    #
    # The court's Zoom feed is flat and slightly grey. The naive fix is
    # `eq=brightness=...`, which raises every pixel including the ones already
    # near white — the jail scrubs, the paper on the bench and the overhead
    # lights blow out and the frame reads washed rather than bright.
    #
    # A curve fixes that: lift the shadows and midtones hard, then pull the
    # top end DOWN to 0.97 so the highlights roll off instead of clipping.
    # Brighter picture, whites intact.
    if cfg.get("color", {}).get("enabled", True):
        c = cfg.get("color", {})
        curve = c.get(
            "curve",
            # x/y control points. 0.25 -> 0.31 and 0.5 -> 0.57 is the lift;
            # 1.0 -> 0.97 is the highlight rolloff that protects the whites.
            "0/0.02 0.25/0.31 0.5/0.57 0.75/0.80 1/0.97",
        )
        tail += (
            f",curves=all='{curve}'"
            f",eq=saturation={float(c.get('saturation', 1.10)):.3f}"
            f":contrast={float(c.get('contrast', 1.05)):.3f}"
        )

    if ass_path is not None:
        # ffmpeg's filter parser mangles Windows drive letters and backslashes,
        # so run with cwd set to the file's directory and reference it by name.
        tail += f",ass={ass_path.name}"
        # Project fonts travel with the repo rather than being installed into
        # Windows. Without this libass silently falls back to a default face,
        # which renders but looks nothing like the design.
        fonts_dir = Path(__file__).resolve().parents[2] / "assets" / "fonts"
        if fonts_dir.is_dir() and any(fonts_dir.iterdir()):
            rel = os.path.relpath(fonts_dir, ass_path.parent).replace("\\", "/")
            tail += f":fontsdir='{rel}'"
    tail += "[vbase]"

    # Shorts are 1080 wide against a 1920-tall canvas, so the same 6% used on the
    # longform renders a 65px mark that vanishes on a phone. 11% matches its
    # apparent size on the 16:9 cut.
    # One mark per participant when the tiles are stacked. A single top-right
    # mark brands the upper tile only and leaves Judge Boyd's half bare;
    # castillo_FINAL.mp4 carries it over her tile, so both is the house look.
    wm_margin = int(round(w * float(cfg.get("watermark_margin_frac", 0.035))))
    wm_y: int | list[int] | None = None
    if mode == "duo_fill" and cfg.get("watermark_per_tile", True):
        wm_y = [wm_margin, h // 2 + wm_margin]
    wm_in, wm_filter = _watermark_chain(cfg, w, h, "vbase", "vwm", 0.11,
                                        y=wm_y)
    post = "[vwm]format=yuv420p[vout]"

    filter_complex = f"{trims};{concat};{vertical};{tail};{wm_filter};{post}"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cwd = ass_path.parent if ass_path is not None else None
    _run([
        "ffmpeg", "-y", "-i", str(source.resolve()), *wm_in,
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "[ac]",
        "-c:v", "libx264", "-preset", "medium", "-crf", str(cfg.get("crf", 20)),
        "-c:a", "aac", "-b:a", cfg.get("audio_bitrate", "160k"),
        "-movflags", "+faststart",
        str(out_path.resolve()),
    ], cwd=cwd)
    return probe_duration(out_path)


def extract_thumbnail(source: Path, at_s: float, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y", "-ss", f"{max(0.0, at_s):.2f}", "-i", str(source),
        "-frames:v", "1", "-q:v", "2", str(out_path),
    ], timeout=300)
    return out_path


def plan_short_segments(
    case: dict[str, Any], cfg: dict[str, Any]
) -> list[Segment] | None:
    """Turn the model's four-beat plan into cut points.

    CONTENT_SPEC §3 and SAFETY_RULES R5: segments may drop material but must
    stay in the order they occurred. A plan that is out of order is rejected
    outright rather than silently sorted — out-of-order beats mean the model
    tried to build an exchange that did not happen.
    """
    raw = case.get("short_segments") or []
    if not raw:
        return None

    segments = [Segment(float(s["start_s"]), float(s["end_s"])) for s in raw]

    for a, b in zip(segments, segments[1:]):
        if b.start_s < a.end_s:
            return None

    # Never take audio from outside the case: the seconds before case_start
    # belong to the previous defendant, and splicing them in would put another
    # person's hearing into this clip.
    #
    # Clamp rather than reject. The model routinely opens the hook a few
    # seconds early because the quotable line sits near the boundary that
    # segmentation drew — observed 2026-08-10, where a hook starting 6s before
    # case_start discarded an otherwise valid 52s short. Clamping can only ever
    # shrink a segment toward the case, so it is strictly more conservative
    # than what was asked for, and it keeps the short.
    case_start, case_end = case["start_s"], case["end_s"]
    clamped: list[Segment] = []
    for s in segments:
        start = max(s.start_s, case_start)
        end = min(s.end_s, case_end)
        if end - start < 1.0:
            return None  # a beat lying (almost) wholly outside is a bad plan
        clamped.append(Segment(start, end))
    segments = clamped

    total = sum(s.duration for s in segments)
    if total < cfg.get("min_duration_s", 25):
        return None

    # Trim from the tail if over budget — the hook is worth more than the button.
    limit = cfg.get("max_duration_s", 59)
    if total > limit:
        kept: list[Segment] = []
        budget = limit
        for seg in segments:
            if budget <= 0.5:
                break
            if seg.duration <= budget:
                kept.append(seg)
                budget -= seg.duration
            else:
                kept.append(Segment(seg.start_s, seg.start_s + budget))
                budget = 0
        segments = kept
        if sum(s.duration for s in segments) < cfg.get("min_duration_s", 25):
            return None

    return segments
