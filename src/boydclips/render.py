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


def align_body_to_court_call(
    words: Sequence[Word],
    segments: list[Segment],
    max_wait_s: float = 90.0,
    lead_s: float = 0.08,
) -> tuple[list[Segment], float | None]:
    """Start a Boyd long-form body at the first "court is calling" line.

    The cold open and sting already supply the setup. Keeping the Zoom room
    before Boyd calls the case leaves a long, silent second opening after the
    branded intro. Only align when the exact three-word phrase occurs inside
    the opening window and inside a kept segment; otherwise preserve the
    editor's original start unchanged.
    """
    if not segments:
        return segments, None
    first = min(s.start_s for s in segments)
    deadline = first + max(0.0, float(max_wait_s))

    def token(word: str) -> str:
        return re.sub(r"[^a-z0-9']+", "", word.lower())

    opening = [w for w in words if first <= float(w.t) <= deadline]
    target = ("court", "is", "calling")
    call_s: float | None = None
    for i in range(len(opening) - len(target) + 1):
        sample = opening[i:i + len(target)]
        if tuple(token(w.w) for w in sample) != target:
            continue
        if float(sample[-1].t) - float(sample[0].t) > 2.5:
            continue
        t = float(sample[0].t)
        if any(s.start_s <= t < s.end_s for s in segments):
            call_s = max(first, t - max(0.0, float(lead_s)))
            break
    if call_s is None:
        return segments, None

    aligned: list[Segment] = []
    for seg in segments:
        if seg.end_s <= call_s:
            continue
        aligned.append(Segment(max(seg.start_s, call_s), seg.end_s))
    return aligned, call_s


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
    # uint8, not float32: the float copy of a 28-minute 720p section was a
    # 1.2 GiB allocation that failed under load (Diaz, 2026-09-06) and a 1080p
    # section would be 2.8 GiB. Consumers convert the slice they measure.
    return buf.reshape(n, src_h, src_w), src_w, src_h


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
        act = float(stack[:, y:y + h, x:x + w].astype(np.float32).std(axis=0).mean())
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

    # Local full-docket cut (2026-09-06). yt-dlp's --download-sections hands
    # the transfer to ffmpeg as a ranged HTTP fetch, which googlevideo served
    # at ~110 KB/s that day: a 54-minute span would have taken hours. A full
    # docket fetched with the normal fragment downloader (tools/fetch_docket.py)
    # arrives at line speed, and the section is then cut here with a
    # frame-accurate re-encode (-ss before -i, video and audio both decoded),
    # so the file's t=0 is section_start exactly as the cached-file contract
    # above requires. Same name, same offset semantics, same downstream.
    full = full_docket_path(video_id, out_path.parent)
    if full.exists():
        cut_section(full, section_start, section_end, out_path)
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


def full_docket_path(video_id: str, work_dir: Path) -> Path:
    """Where tools/fetch_docket.py puts the complete stream for a docket."""
    return work_dir / f"{video_id}.full.mp4"


CUT_SECTION_ARGS = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"]


def cut_section(full: Path, section_start: float, section_end: float, out_path: Path) -> Path:
    """Frame-accurate cut of [section_start, section_end) from a local file.

    `-ss` before `-i` with a re-encode: ffmpeg seeks to the preceding keyframe
    and decodes forward, so the first output frame is the frame at
    section_start (not the keyframe). CRF 14 keeps the intermediate visually
    lossless ahead of the render's own encode.
    """
    tmp = out_path.with_name(out_path.stem + ".cut.part.mp4")
    _run([
        "ffmpeg", "-y", "-hide_banner", "-nostats", "-loglevel", "error",
        "-ss", f"{section_start:.3f}", "-i", str(full),
        "-t", f"{max(0.0, section_end - section_start):.3f}",
        *CUT_SECTION_ARGS, str(tmp),
    ])
    tmp.replace(out_path)
    return out_path


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


def caption_cards(
    words: list[Word],
    timeline_offset_s: float,
    style: dict[str, Any],
    turns: list[tuple[float, str]] | None = None,
) -> list[dict[str, Any]]:
    """The caption cards a short carries — ONE grouping for every path.

    This is the grouping the approved Thompson short shipped with and the
    daily path has always used: words grouped inside a speaker's run by
    `group_words` (max_words_per_card, max_chars_per_line, max_lines), each
    card on the slot its speaker's turn label maps to in `slot_margins`.
    SHORTS_EDITOR_V2's first render replaced it with a phrase-DP that cut
    1–4-word cards ("AND SHE TOLD" / "ME THAT SHE" / "WAS") and Nathan
    refused it; the planner now calls THIS for its audit record and
    build_ass draws exactly these cards.

    `words` are in source time; `timeline_offset_s` converts them to the
    output clip (pass words already mapped through map_words_to_timeline
    with offset 0.0 for an edited short). `turns` is [(output_time, label)]
    ascending; a label is looked up in style["slot_margins"], so a caller
    may key it by anything it likes ("boyd|bottom").

    Returns one dict per card: words [(output_t, token)], tokens (censored,
    cased as drawn), lines, text, margin_v, slot, start_s, end_s.
    """
    words = [
        type(w)(t=w.t, w=strip_caption_artifact(w.w))
        for w in words
        if strip_caption_artifact(w.w)
    ]
    max_chars = style.get("max_chars_per_line", 22)
    max_lines = style.get("max_lines", 2)
    upper = style.get("uppercase", True)
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

    # Cards are grouped within a speaker's run, never across a change. A
    # card holding the end of one person's sentence and the start of the
    # other's would have to sit in one slot or the other and would be wrong
    # beside whichever it chose.
    runs: list[list[Word]] = []
    for word in words:
        who = speaker_at(word.t - timeline_offset_s)
        if runs and speaker_at(runs[-1][0].t - timeline_offset_s) == who:
            runs[-1].append(word)
        else:
            runs.append([word])

    max_words = style.get("max_words_per_card")
    out: list[dict[str, Any]] = []
    for run in runs:
        slot = speaker_at(run[0].t - timeline_offset_s)
        marginv = int(slot_margins.get(slot or "", default_margin))
        for g in group_words(run, max_chars, max_lines, max_words):
            # CONTENT_SPEC §9: the audio ships as recorded, every text
            # surface is censored.
            tokens = [censor(w.w.strip()) for w in g]
            if upper:
                tokens = [t.upper() for t in tokens]
            line_map = _wrap(tokens, max_chars)
            lines = [" ".join(tokens[j] for j in line) for line in line_map]
            out.append({
                "words": [(round(w.t - timeline_offset_s, 3), w.w) for w in g],
                "tokens": tokens,
                "lines": lines,
                "text": " ".join(tokens),
                "margin_v": marginv,
                "slot": slot,
                "start_s": round(g[0].t - timeline_offset_s, 3),
                "end_s": round(g[-1].t - timeline_offset_s + 0.45, 3),
            })
    return out


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
      pop        card re-rendered per word, active word scales 112 -> 100 over
                 70ms and stays white. Motion without colour.
      pop_color  as pop, plus the active word recoloured. The mainstream 2026
                 look.
      highlight  colour change only, no motion. The original behaviour, kept so
                 old renders stay reproducible.

    The cards themselves come from caption_cards() — the legacy grouping —
    so what this draws is exactly what the planner recorded.

    timeline_offset_s converts absolute source timestamps into output-clip time.
    """
    max_chars = style.get("max_chars_per_line", 22)
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

    anim = style.get("animation", "highlight")
    pop_scale = int(style.get("pop_scale", 112))
    pop_ms = int(style.get("pop_ms", 70))
    card_fade_ms = int(style.get("card_fade_ms", 80))

    def active(token: str) -> str:
        """The active word's markup for the chosen treatment."""
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

    cards = caption_cards(words, timeline_offset_s, style, turns)

    timed: list[tuple[float, float, str, int]] = []
    for card in cards:
        tokens = card["tokens"]
        marginv = card["margin_v"]
        group = card["words"]                       # [(output_t, token)]
        line_map = _wrap(tokens, max_chars)
        plain_text = "\\N".join(
            " ".join(tokens[j] for j in line) for line in line_map
        )

        if anim == "plain":
            start = group[0][0]
            end = group[-1][0] + 0.45
            if end > 0 and start < total_duration_s:
                start = max(0.0, start)
                end = min(total_duration_s, max(end, start + 0.05))
                fade = f"{{\\fad({card_fade_ms},{card_fade_ms})}}" if card_fade_ms else ""
                timed.append((start, end, fade + plain_text, marginv))
            continue

        for i, (word_t, _tok) in enumerate(group):
            start = word_t
            end = group[i + 1][0] if i + 1 < len(group) else start + 0.45
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
    # a collision, it stacks it. Clamping every event against its successor is
    # the general fix.
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


_FONT_SCALE_CACHE: dict[str, float] = {}


def ass_font_scale(font: str) -> float:
    """libass (like VSFilter) treats the ASS Fontsize as the font's CELL
    height — OS/2 usWinAscent + usWinDescent — not the em size, so a face
    is rendered at em = Fontsize / ((winAscent + winDescent) / unitsPerEm).
    For Anton that factor is 1.7334: "Fontsize 84" rendered as a 48 px em
    (measured 2026-09-06: cap height 42 px, ink widths 0.577 x the PIL
    widths the planner measured — which is also why the captions sat left
    of centre). The planner measures widths in em pixels; this factor turns
    the intended em into the Fontsize libass needs. 1.0 when the font file
    cannot be read."""
    if font in _FONT_SCALE_CACHE:
        return _FONT_SCALE_CACHE[font]
    import struct
    fonts_dir = Path(__file__).resolve().parents[2] / "assets" / "fonts"
    k = 1.0
    for cand in (fonts_dir / f"{font}-Regular.ttf", fonts_dir / f"{font}.ttf", fonts_dir / f"{font}-Var.ttf"):
        if not cand.exists():
            continue
        try:
            data = cand.read_bytes()
            num = struct.unpack(">H", data[4:6])[0]
            tables = {}
            for i in range(num):
                off = 12 + 16 * i
                tag = data[off:off + 4].decode("latin-1")
                toff, tlen = struct.unpack(">II", data[off + 8:off + 16])
                tables[tag] = toff
            upem = struct.unpack(">H", data[tables["head"] + 18:tables["head"] + 20])[0]
            os2 = tables["OS/2"]
            win_asc, win_desc = struct.unpack(">HH", data[os2 + 74:os2 + 78])
            if upem and (win_asc + win_desc):
                k = (win_asc + win_desc) / float(upem)
            else:
                h = tables["hhea"]
                asc, desc = struct.unpack(">hh", data[h + 4:h + 8])
                k = (asc - desc) / float(upem)
        except Exception:  # noqa: BLE001
            k = 1.0
        break
    _FONT_SCALE_CACHE[font] = k
    return k


def build_rail_ass(
    cards: Sequence[dict[str, Any]],
    style: dict[str, Any],
    total_duration_s: float,
    out_path: Path,
) -> Path:
    """KINETIC captions on the DIVIDER RAIL (SHORTS_EDITOR_V2, 2026-09-06).

    One phrase at a time, one line, built in 1–3 natural CHUNKS as it is
    spoken (captions.plan_captions decides the phrases, the display cleanup
    and the reveal chunks). Each reveal is one Dialogue event whose text is
    the words revealed so far: the earlier chunks white and unmoving, the
    newest chunk in the active colour with one short pop-in (pop_from →
    pop_peak → 100 % over pop_ms).

    Why the phrase is LEFT-anchored: with a centred anchor every change of
    width — a new word, the pop — re-centres the whole line and the earlier
    words slide (measured 33 px on short_v3_slots.mp4). So each phrase is
    placed at `\\an4\\pos(x_left, rail_y)` with x_left = rail_x − width/2 of
    the COMPLETED phrase (width measured with the font file), and words
    only ever appear to the right of what is already there; the finished
    phrase sits centred on the rail. A phrase clears at its `clear_s`; a new
    speaker's phrase starts from empty by construction.

    mode "static" draws each phrase whole and white (the fallback). No
    boxes, no fade, no end card.
    """
    font = style.get("font", "Anton")
    size = int(style.get("font_size", 96))
    size_ass = round(size * ass_font_scale(str(font)), 1)      # em px -> libass Fontsize (see ass_font_scale)
    primary = style.get("primary_color", "&H00FFFFFF")
    active = style.get("active_color", "&H003FD2FF")
    outline_color = style.get("outline_color", "&H00000000")
    outline = style.get("outline", 6)
    shadow = style.get("shadow", 2)
    rail_x = int(style.get("rail_x", 540))
    # the anchor line is the divider; rail_y_offset (set by the calibration
    # from a measurement) centres the ink block on it — one value for all
    rail_y = int(round(int(style.get("rail_y", 960)) + float(style.get("rail_y_offset", 0.0))))
    mode = str(style.get("mode", "kinetic")).lower()
    speaker_colors = dict(style.get("speaker_colors") or {})
    pop_ms = int(style.get("pop_ms", 110))
    pop_from = int(style.get("pop_from", 92))
    pop_peak = int(style.get("pop_peak", 106))
    rise = int(style.get("pop_rise_ms", max(20, int(pop_ms * 0.5))))
    fade_ms = int(style.get("pop_fade_ms", 60))
    ease_rise = float(style.get("ease_rise", 0.6))
    ease_settle = float(style.get("ease_settle", 1.3))
    ease_fade = float(style.get("ease_fade", 0.7))

    header = f"""[Script Info]
ScriptType: v4.00+
; Rail captions: em {size} px rendered as Fontsize {size_ass} (libass Fontsize = winAscent + winDescent)
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Rail,{font},{size_ass},{primary},{primary},{outline_color},&H80000000,-1,0,0,0,100,100,0,0,1,{outline},{shadow},4,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    # The new chunk's entrance (visual polish 2026-09-06): scale 92 % ->
    # 106 % over pop_rise_ms with an ease-out (\t accel 0.6), then 106 % ->
    # 100 % with an ease-in (accel 1.3) — one smooth overshoot, no bounce —
    # while its opacity rises 0 -> 100 % over pop_fade_ms (accel 0.7). Only
    # the chunk inside this override block animates; the words before it are
    # plain text at the same origin and never move.
    pop_tag = (f"\\fscx{pop_from}\\fscy{pop_from}\\alpha&HFF&"
               + (f"\\t(0,{fade_ms},{ease_fade:g},\\alpha&H00&)" if fade_ms > 0 else "\\alpha&H00&")
               + f"\\t(0,{rise},{ease_rise:g},\\fscx{pop_peak}\\fscy{pop_peak})"
               f"\\t({rise},{pop_ms},{ease_settle:g},\\fscx100\\fscy100)")
    events: list[str] = []
    for c in cards:
        toks = list(c["tokens"])
        # the origin of the COMPLETED phrase, centred on its visual box
        # (captions.caption_origin, calibrated by calibrate_caption_positions);
        # every reveal state of the phrase uses it
        if c.get("x_left") is not None:
            x_left = int(c["x_left"])
        else:
            x_left = int(round(rail_x - float(c.get("width_px", 0.0)) / 2.0))
        pos = f"{{\\an4\\pos({x_left},{rail_y})}}"
        if mode == "static":
            start = max(0.0, float(c["start_s"]))
            end = min(float(total_duration_s), float(c["clear_s"]))
            if end - start >= 0.05:
                speaker_color = speaker_colors.get(str(c.get("speaker") or ""))
                color = f"{{\\c{speaker_color}}}" if speaker_color else ""
                events.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Rail,,0,0,0,,{pos}{color}{' '.join(toks)}")
            continue
        for ev in c["events"]:
            start = max(0.0, float(ev["t"]))
            end = min(float(total_duration_s), float(ev["end"]))
            if end - start < 0.02:
                continue
            la, lb = int(ev["new_range"][0]), int(ev["new_range"][1])
            before = " ".join(toks[:la])
            newest = f"{{\\c{active}{pop_tag}}}{' '.join(toks[la:lb])}{{\\r}}"
            text = f"{before} {newest}" if before else newest
            events.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Rail,,0,0,0,,{pos}{text}")
    out_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return out_path


def measure_caption_centering(ass_path: Path, cards: Sequence[dict[str, Any]], style: dict[str, Any],
                              w: int = 1080, h: int = 1920, fps: int = 50) -> list[dict[str, Any]]:
    """MEASURE where each completed phrase actually lands: render the ASS on
    a black canvas with the same libass + fonts the short uses, grab one
    frame per phrase after its last chunk has settled, and take the bounding
    box of the bright (fill) pixels on the rail. Returns per-card
    {index, text, t, ink_left, ink_right, center, error_px} (error = centre −
    rail_x); cards whose life is too short to settle are reported with
    error None."""
    import numpy as np
    rail_x = float(style.get("rail_x", 540))
    rail_y = int(style.get("rail_y", 960))
    pop_s = float(style.get("pop_ms", 110)) / 1000.0
    picks: list[tuple[int, float]] = []
    for k, c in enumerate(cards):
        evs = c.get("events") or []
        if not evs:
            continue
        last_t = float(evs[-1]["t"])
        t = min(last_t + pop_s + 0.06, float(c["clear_s"]) - 0.03)
        if t < last_t + pop_s + 0.01:
            continue
        picks.append((k, t))
    out: list[dict[str, Any]] = [{"index": k, "text": c["text"], "t": None, "ink_left": None, "ink_right": None,
                                  "center": None, "error_px": None} for k, c in enumerate(cards)]
    if not picks:
        return out
    frames = sorted({int(round(t * fps)) for _k, t in picks})
    sel = "+".join(f"eq(n\\,{n})" for n in frames)
    fonts_dir = Path(__file__).resolve().parents[2] / "assets" / "fonts"
    rel = os.path.relpath(fonts_dir, ass_path.parent).replace("\\", "/")
    dur = max(t for _k, t in picks) + 0.5
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"color=c=black:s={w}x{h}:r={fps}:d={dur:.2f}",
         "-vf", f"ass={ass_path.name}:fontsdir='{rel}',select='{sel}'", "-fps_mode", "passthrough",
         "-frames:v", str(len(frames)), "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True, cwd=ass_path.parent)
    if proc.returncode != 0 or len(proc.stdout) < w * h:
        raise RuntimeError("caption centering measurement failed: " + proc.stderr.decode("utf-8", "replace")[-300:])
    buf = np.frombuffer(proc.stdout, dtype=np.uint8)
    got = len(buf) // (w * h)
    imgs = buf[: got * w * h].reshape(got, h, w)
    by_frame = {n: imgs[i] for i, n in enumerate(frames[:got])}
    y0, y1 = max(0, rail_y - 160), min(h, rail_y + 160)
    for k, t in picks:
        n = int(round(t * fps))
        if n not in by_frame:
            continue
        band = by_frame[n][y0:y1]
        cols = np.where((band > 100).any(axis=0))[0]
        rows = np.where((band > 100).any(axis=1))[0]
        if cols.size == 0:
            continue
        left, right = float(cols[0]), float(cols[-1] + 1)
        top, bottom = float(rows[0] + y0), float(rows[-1] + 1 + y0)
        center = (left + right) / 2.0
        out[k].update({"t": round(t, 3), "ink_left": left, "ink_right": right, "center": round(center, 1),
                       "error_px": round(center - rail_x, 1),
                       "ink_top": top, "ink_bottom": bottom, "center_y": round((top + bottom) / 2.0, 1),
                       "error_y_px": round((top + bottom) / 2.0 - rail_y, 1)})
    return out


def calibrate_caption_positions(cards: Sequence[dict[str, Any]], style: dict[str, Any], total_duration_s: float,
                                ass_path: Path, w: int = 1080, h: int = 1920, tolerance_px: float = 1.0,
                                rounds: int = 2) -> dict[str, Any]:
    """TRUE VISUAL CENTRING (visual polish 2026-09-06). Write the rail ASS
    from the predicted origins, measure each completed phrase's rendered
    ink centre on a black canvas, shift any phrase that is off by more than
    tolerance_px by its measured error (the whole phrase, so no reveal state
    moves relative to another), rewrite, re-measure. Returns
    {predicted_max_error_px, measured_before, measured_after, max_error_px,
    mean_error_px, per_card} and leaves the calibrated ASS at ass_path with
    card["x_left"] / card["center_error_px"] updated in place."""
    build_rail_ass(cards, style, total_duration_s, ass_path)
    before = measure_caption_centering(ass_path, cards, style, w, h)
    summary: dict[str, Any] = {
        "predicted_max_error_px": round(max((abs(float(c.get("predicted_center", 540)) - float(style.get("rail_x", 540)))
                                              for c in cards), default=0.0), 1),
        "measured_before": {"max_error_px": _max_abs(before), "mean_error_px": _mean_abs(before)},
        "rounds": 0,
    }
    current = before
    for _r in range(rounds):
        moved = 0
        for m in current:
            if m["error_px"] is None or abs(m["error_px"]) <= tolerance_px:
                continue
            cards[m["index"]]["x_left"] = int(cards[m["index"]]["x_left"]) - int(round(m["error_px"]))
            moved += 1
        if not moved:
            break
        summary["rounds"] += 1
        build_rail_ass(cards, style, total_duration_s, ass_path)
        current = measure_caption_centering(ass_path, cards, style, w, h)
    # vertical: the ink block (capitals) sits lower in the cell than its
    # middle, so centre the MEAN ink block on the rail with one uniform
    # offset for every phrase (the rail stays one line at one height)
    ys = [float(m["error_y_px"]) for m in current if m.get("error_y_px") is not None]
    y_off = round(sum(ys) / len(ys), 1) if ys else 0.0
    if abs(y_off) > 1.0:
        style = dict(style, rail_y_offset=float(style.get("rail_y_offset", 0.0)) - y_off)
        build_rail_ass(cards, style, total_duration_s, ass_path)
        current = measure_caption_centering(ass_path, cards, style, w, h)
    summary["rail_y_offset"] = float(style.get("rail_y_offset", 0.0))
    ys2 = [float(m["error_y_px"]) for m in current if m.get("error_y_px") is not None]
    summary["vertical_error_px"] = {"before": y_off, "after_mean": round(sum(ys2) / len(ys2), 1) if ys2 else 0.0,
                                    "after_max": round(max(abs(v) for v in ys2), 1) if ys2 else 0.0}
    for m in current:
        cards[m["index"]]["center_error_px"] = m["error_px"]
        cards[m["index"]]["measured_center"] = m["center"]
        cards[m["index"]]["center_error_y_px"] = m.get("error_y_px")
    summary["measured_after"] = {"max_error_px": _max_abs(current), "mean_error_px": _mean_abs(current)}
    summary["max_error_px"] = summary["measured_after"]["max_error_px"]
    summary["mean_error_px"] = summary["measured_after"]["mean_error_px"]
    summary["measured_phrases"] = sum(1 for m in current if m["error_px"] is not None)
    summary["per_card"] = current
    return summary


def _max_abs(ms: Sequence[dict[str, Any]]) -> float:
    vals = [abs(float(m["error_px"])) for m in ms if m.get("error_px") is not None]
    return round(max(vals), 1) if vals else 0.0


def _mean_abs(ms: Sequence[dict[str, Any]]) -> float:
    vals = [abs(float(m["error_px"])) for m in ms if m.get("error_px") is not None]
    return round(sum(vals) / len(vals), 2) if vals else 0.0


def _gray_frame(path: Path, t: float, vf: str) -> "np.ndarray | None":
    try:
        import numpy as np
    except Exception:  # pragma: no cover - numpy is a hard dependency elsewhere
        return None
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", str(path), "-frames:v", "1",
         "-vf", vf, "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True,
    )
    if proc.returncode != 0 or not proc.stdout:
        return None
    return np.frombuffer(proc.stdout, dtype=np.uint8)


def measure_divider_y(path: Path, t: float, w: int = 1080, h: int = 1920,
                      band: tuple[int, int] = (900, 1020), margin_px: int = 50) -> float | None:
    """The row of the strongest horizontal edge around the expected divider,
    measured on the OUTER columns only (the caption block sits in the
    middle of the frame and would otherwise dominate). None if the frame
    cannot be read."""
    try:
        import numpy as np
    except Exception:  # pragma: no cover
        return None
    lo, hi = band
    buf = _gray_frame(path, t, f"scale={w}:{h}")
    if buf is None or buf.size < w * h:
        return None
    img = buf[: w * h].reshape(h, w).astype(float)
    cols = np.concatenate([img[:, :margin_px], img[:, w - margin_px:]], axis=1)
    diff = np.abs(np.diff(cols, axis=0)).mean(axis=1)       # diff[r] = |row r+1 - row r|
    seg = diff[lo:hi]
    r = int(np.argmax(seg)) + lo
    return float(r + 1)


def visual_qc(
    sh_path: Path,
    plan: dict[str, Any],
    comp: dict[str, Any],
    overlay: dict[str, Any],
    checks: list[dict[str, Any]],
    out_dir: Path,
    extra_frames: Sequence[tuple[str, float]] | None = None,
) -> dict[str, Any]:
    """The review contact sheet and the deterministic composition record for
    ONE short: frames at the opening, the first speaker change, the first
    punch-in, the middle, the payoff and the last frame, tiled into
    visual_qc_contact.jpg; visual_qc.json with the per-frame composition
    data (divider, caption centre, subject anchors, punch scale, overlay
    boxes), the layout checks, and the divider measured on every frame —
    it must sit at the same row on normal and punched frames.

    A vision-capable reviewer can be plugged in later on the same inputs
    (the sheet + this JSON); it is not required for the checks here.
    """
    duration = float(plan.get("duration_s", 0.0))
    segments = plan.get("segments") or []
    focus = plan.get("segment_focus") or []
    punch = plan.get("segment_punch") or []
    offsets: list[float] = []
    acc = 0.0
    for a, b in segments:
        offsets.append(acc)
        acc += float(b) - float(a)

    def out_time(t_src: float) -> float | None:
        for (a, b), off in zip(segments, offsets):
            if float(a) - 1e-6 <= t_src <= float(b) + 1e-6:
                return off + (t_src - float(a))
        return None

    frames: list[tuple[str, float]] = [("opening", min(0.3, max(0.0, duration - 0.1)))]
    for i in range(1, len(segments)):
        if focus[i] != focus[i - 1]:
            frames.append(("first_speaker_change", offsets[i] + 0.3))
            break
    for i, p in enumerate(punch):
        if p:
            frames.append(("first_punch_in", offsets[i] + 0.4))
            break
    frames.append(("middle", duration / 2.0))
    payoff = next((b for b in plan.get("beats") or [] if b.get("role") == "payoff"), None)
    if payoff and payoff.get("ranges"):
        ot = out_time(float(payoff["ranges"][0][0]))
        if ot is not None:
            frames.append(("payoff", ot + 0.4))
    frames.append(("final", max(0.0, duration - 0.15)))
    # e.g. the CTA's before / entrance / mid-draw / hold (cta.review_frame_times)
    frames += [(str(lab), float(t)) for lab, t in (extra_frames or [])]
    frames = [(lab, min(max(0.0, t), max(0.0, duration - 0.05))) for lab, t in frames]

    out_dir.mkdir(parents=True, exist_ok=True)
    pngs: list[Path] = []
    records: list[dict[str, Any]] = []
    seg_layouts = comp.get("segments") or []
    for k, (label, t) in enumerate(frames):
        png = out_dir / f"_vqc_{k}_{label}.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(sh_path),
                        "-frames:v", "1", "-vf", "scale=360:640", str(png)], capture_output=True)
        if png.exists():
            pngs.append(png)
        seg_idx = 0
        for i, off in enumerate(offsets):
            if off <= t + 1e-6:
                seg_idx = i
        lay = seg_layouts[seg_idx] if seg_idx < len(seg_layouts) else {}
        measured = measure_divider_y(sh_path, t)
        records.append({
            "label": label, "t_s": round(t, 3), "segment": seg_idx,
            "divider_y": lay.get("divider_y"), "measured_divider_y": measured,
            "caption_center": overlay.get("caption_center"),
            "top_subject": [lay.get("top", {}).get("subject_x"), lay.get("top", {}).get("subject_y")],
            "bottom_subject": [lay.get("bottom", {}).get("subject_x"),
                               (lay.get("bottom", {}).get("subject_y") or 0) + int(comp.get("divider_y", 960))],
            "punch": lay.get("punch", ""), "punch_scale": lay.get("punch_scale", 1.0),
            "overlay_boxes": overlay.get("boxes"),
        })
    sheet = out_dir / "visual_qc_contact.jpg"
    if pngs:
        inputs: list[str] = []
        for png in pngs:
            inputs += ["-i", str(png)]
        subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex",
                        "".join(f"[{i}]" for i in range(len(pngs))) + f"hstack=inputs={len(pngs)}",
                        "-q:v", "3", str(sheet)], capture_output=True)
        for png in pngs:
            try:
                png.unlink()
            except OSError:
                pass
    measured = [r["measured_divider_y"] for r in records if r["measured_divider_y"] is not None]
    div_checks: list[dict[str, Any]] = []
    if measured:
        want = int(comp.get("divider_y", 960))
        div_checks.append({"check": "divider_measured_at_960", "ok": all(abs(m - want) <= 8 for m in measured),
                           "value": measured, "want": want})
        div_checks.append({"check": "divider_stable_normal_vs_punch", "ok": (max(measured) - min(measured)) <= 6,
                           "value": [min(measured), max(measured)]})
    else:
        div_checks.append({"check": "divider_measured_at_960", "ok": False, "value": None, "want": 960})
    all_checks = list(checks) + div_checks
    report = {
        "contact_sheet": str(sheet) if sheet.exists() else None,
        "frames": records,
        "checks": all_checks,
        "ok": all(c["ok"] for c in all_checks),
        "reviewer": "deterministic (a vision reviewer may be attached to the same sheet + json later)",
    }
    (out_dir / "visual_qc.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


# ------------------------------------------------------------------ renderers


SHORT_FLOOR_PATH = Path(__file__).resolve().parents[2] / "config" / "short_floor.json"
DAILY_CURVE = "0/0.02 0.25/0.31 0.5/0.57 0.75/0.80 1/0.97"


def short_grade_filter(cfg: dict[str, Any]) -> str:
    """The short's colour correction — ONE source for every short renderer.

    `config/short_floor.json` `grade.eq` is the house grade: solved by
    tools/solve_grade.py against SANCHEZ_SHORT_FINAL.mp4 (the short Nathan
    named as the one that looks right — "save everything as the normal floor
    when making future shorts", 2026-08-31) and applied to both tiles by the
    manual chain (tools/short_engine.py / make_short.py). The daily renderer
    carried its own curves+eq instead (config output.short.color), so a
    daily short — legacy or SHORTS_EDITOR_V2 — never received the treatment
    the shipped shorts had. Traced 2026-09-06 on the first Flores render:
    both daily graphs contained the daily curve and neither contained the
    floor grade.

    color.source: short_floor (default) reads the floor and FAILS if the key
    is missing (the manual chain does the same — no silent default);
    short_floor_no_brightness reads the floor and drops its brightness term
    (the per-camera curves handle the highlights; see below); curve keeps
    the old daily block for reproducing earlier renders; none disables
    grading. Returns the filter fragment without a leading comma.
    """
    color = dict(cfg.get("color") or {})
    if not color.get("enabled", True):
        return ""
    source = str(color.get("source", "short_floor")).lower()
    if source == "none":
        return ""
    if source == "curve":
        curve = color.get("curve", DAILY_CURVE)
        return (f"curves=all='{curve}'"
                f",eq=saturation={float(color.get('saturation', 1.10)):.3f}"
                f":contrast={float(color.get('contrast', 1.05)):.3f}")
    floor = json.loads(SHORT_FLOOR_PATH.read_text(encoding="utf-8"))
    eq = floor["grade"]["eq"]                      # KeyError on purpose
    if not isinstance(eq, str) or not eq.startswith("eq="):
        raise ValueError(f"short_floor.json grade.eq is not an eq filter: {eq!r}")
    if source == "short_floor_no_brightness":
        # Nathan, 2026-09-06 ("b"): with each camera's highlights rolled off
        # BEFORE assembly (camera_grade_filter), the floor's global
        # brightness=-0.10 only darkens the faces — measured on Flores,
        # defendant face p50 134 -> 105, Boyd 116 -> 80. The common stage
        # keeps the floor's contrast and saturation, derived from the floor
        # file so the numbers stay its numbers, and drops the brightness term.
        params = [kv for kv in eq[len("eq="):].split(":") if not kv.strip().startswith("brightness=")]
        return "eq=" + ":".join(params) if params else ""
    return eq


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


def camera_grade_filter(color_cfg: dict[str, Any] | None, role: str) -> str:
    """The PER-CAMERA correction for one tile, applied to that tile before
    the two are assembled (Nathan, 2026-09-06: the defendant camera's
    fluorescent ceiling blows out; the two cameras do not share exposure).

    `output.short.color.<role>` is either a filter fragment string or a dict
    with `curve` (a `curves=all=` point list — the same mechanism the daily
    grade used, so shadows and midtones can be held while the top of the
    range is rolled off) and/or `eq` (an `eq=` string, the floor's
    convention). Missing or empty → no per-camera stage. The common floor
    grade (short_grade_filter) still runs on the assembled frame afterwards.
    """
    spec = (color_cfg or {}).get(role)
    if not spec:
        return ""
    if isinstance(spec, str):
        return spec.strip().strip(",")
    parts: list[str] = []
    curve = spec.get("curve")
    if curve:
        parts.append(f"curves=all='{curve}'")
    eq = spec.get("eq")
    if eq:
        parts.append(str(eq) if str(eq).startswith("eq=") else f"eq={eq}")
    return ",".join(parts)


def camera_clarity_filter(clarity_cfg: dict[str, Any] | None, role: str | None) -> str:
    """The per-tile POST-SCALE clarity chain (visual polish 2026-09-06).
    output.short.clarity: {scale_flags, defendant, boyd, default} — each
    role maps to an ffmpeg filter fragment (e.g. cas=strength=0.35) or
    null/"" for none. The defendant tile carries the larger upscale, so it
    may take a modestly stronger pass than Boyd's. Applied after the tile
    scale and before the stack; captions burn in after the stack."""
    if not clarity_cfg or not clarity_cfg.get("enabled", True):
        return ""
    key = (role or "").lower()
    val = clarity_cfg.get(key, clarity_cfg.get("default"))
    return str(val) if val else ""


def duo_punch_filter(
    segments: list[Segment],
    offset_s: float,
    windows: Sequence[tuple[str, str]],
    w: int,
    h: int,
    join_fade_s: float = 0.015,
    tile_filters: tuple[str, str] | None = None,
    scale_flags: str = "",
    tile_post: tuple[str, str] | None = None,
) -> str:
    """Per-segment picture for the FIXED 50/50 stack (layout.compose).

    `scale_flags` are swscale flags for the tile upscale (visual polish
    2026-09-06: lanczos+accurate_rnd+full_chroma_int instead of the default
    bicubic); `tile_post` = (top, bottom) chains applied AFTER the scale —
    the per-tile clarity (camera_clarity_filter). Captions are burned in
    later, after the stack, so they never pass through the clarity filter.

    `windows[i]` is (top_crop, bottom_crop) for segments[i] — the subject-
    centred base windows, or the punched window on the speaker's tile. Every
    segment scales both windows to w × h/2 and stacks them, so the divider is
    at h/2 on every frame and a punch-in is a zoom INSIDE a tile, never a
    change of the split. `tile_filters` = (top, bottom) per-camera grades
    (camera_grade_filter), applied to each tile BEFORE it is scaled and
    stacked. Same trims and 15 ms audio fades as _concat_filter, so the cut
    points are identical to the unpunched render.

    Returns the whole chain ending in [vv] (video) and [ac] (audio).
    """
    half = h // 2
    n = len(segments)
    tf_top, tf_bottom = tile_filters or ("", "")
    tf_top = f"{tf_top}," if tf_top else ""
    tf_bottom = f"{tf_bottom}," if tf_bottom else ""
    sf = f":flags={scale_flags}" if scale_flags else ""
    tp_top, tp_bottom = tile_post or ("", "")
    tp_top = f",{tp_top}" if tp_top else ""
    tp_bottom = f",{tp_bottom}" if tp_bottom else ""
    parts: list[str] = []
    for i, seg in enumerate(segments):
        a = max(0.0, seg.start_s - offset_s)
        b = max(a + 0.05, seg.end_s - offset_s)
        fade = ""
        if join_fade_s > 0:
            d = min(join_fade_s, (b - a) / 4.0)
            fade = (f",afade=t=in:st=0:d={d:.3f}"
                    f",afade=t=out:st={b - a - d:.3f}:d={d:.3f}")
        parts.append(f"[0:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS{fade}[a{i}]")
        top, bottom = windows[i]
        parts.append(
            f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS,split=2[l{i}][r{i}];"
            f"[l{i}]{top},{tf_top}scale={w}:{half}{sf}{tp_top},setsar=1[lt{i}];"
            f"[r{i}]{bottom},{tf_bottom}scale={w}:{half}{sf}{tp_bottom},setsar=1[rt{i}];"
            f"[lt{i}][rt{i}]vstack=inputs=2[vv{i}]"
        )
    vpairs = "".join(f"[vv{i}]" for i in range(n))
    apairs = "".join(f"[a{i}]" for i in range(n))
    return (";".join(parts)
            + f";{vpairs}concat=n={n}:v=1:a=0[vv]"
            + f";{apairs}concat=n={n}:v=0:a=1[ac]")


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
    The asset may carry its own alpha, but every enabled render also applies the
    configured opacity multiplier.  This keeps the logo faint even when a new
    source asset is more opaque than the current TTT mark.

    Explicitly disabled marks use a null pass-through. A configured missing
    asset is an error so a render cannot silently lose required branding.
    """
    raw = cfg.get("watermark", DEFAULT_WATERMARK)
    if raw in (None, False, ""):
        return [], f"[{in_label}]null[{out_label}]"
    path = Path(raw)
    if not path.is_file():
        raise FileNotFoundError(f"configured watermark not found: {path}")

    frac = float(cfg.get("watermark_width_frac", width_frac))
    opacity = float(cfg.get("watermark_opacity", 0.45))
    if not 0.0 < opacity < 1.0:
        raise ValueError("watermark_opacity must be greater than 0 and less than 1")
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
            f"[{wm_index}:v]scale={wm_w}:-1,format=rgba,"
            f"colorchannelmixer=aa={opacity:.4f}[wm];"
            f"[{in_label}][wm]overlay={x_expr}:{tops[0]}[{out_label}]",
        )

    n = len(tops)
    parts = [f"[{wm_index}:v]scale={wm_w}:-1,format=rgba,"
             f"colorchannelmixer=aa={opacity:.4f},split={n}"
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
COLDOPEN_WORD_TAIL_S = 0.9      # a word's end when the next word is far away
COLDOPEN_LEAD_S = 0.15          # breath before the first word
_SENTENCE_END = (".", "?", "!")
_TRAIL_PUNCT = "\"')]"


def coldopen_span(words: Sequence[Word], moment_s: float | None, pieces: Sequence[Segment],
                  min_s: float = COLDOPEN_MIN_S, max_s: float = COLDOPEN_MAX_S,
                  ahead_s: float = COLDOPEN_MIN_AHEAD_S) -> tuple[tuple[float, float] | None, str]:
    """The R49 cold-open span for the daily route: (start, end) in source
    seconds, or (None, why).

    Starts a breath before the word at `moment_s` and runs to the first
    sentence end that is at least `min_s` away, never past `max_s`, never past
    the long-form piece that holds the moment, and never earlier than
    `ahead_s` into the body (render_longform refuses those, so they are
    refused here with a reason instead of a crash mid-render). Word ends are
    the next word's start, capped at COLDOPEN_WORD_TAIL_S, because the
    transcript carries start times only.
    """
    if moment_s is None:
        return None, "no money moment on the case"
    m = float(moment_s)
    piece = next((p for p in pieces if p.start_s <= m <= p.end_s), None)
    if piece is None:
        return None, f"money moment {m:.1f}s is not inside a long-form piece"
    body0 = min(p.start_s for p in pieces)
    if m - body0 < ahead_s:
        return None, f"money moment is {m - body0:.1f}s into the body; needs >= {ahead_s:.0f}s"
    ws = sorted((float(w.t), str(w.w)) for w in words if piece.start_s <= float(w.t) <= piece.end_s)
    if not ws:
        return None, "no transcript words inside the piece"
    k0 = max((i for i, (t, _) in enumerate(ws) if t <= m), default=0)
    c0 = max(piece.start_s, ws[k0][0] - COLDOPEN_LEAD_S, body0 + ahead_s)
    limit = min(piece.end_s, c0 + max_s)
    best = None          # first sentence end inside [min_s, max_s]
    last_ok = None       # last word end inside max_s
    for i in range(k0, len(ws)):
        t, txt = ws[i]
        nxt = ws[i + 1][0] if i + 1 < len(ws) else piece.end_s
        end = min(nxt, t + COLDOPEN_WORD_TAIL_S, limit)
        if end <= c0:
            continue
        if end - c0 > max_s + 1e-6 or t >= limit:
            break
        last_ok = end
        if txt.rstrip(_TRAIL_PUNCT).endswith(_SENTENCE_END) and end - c0 >= min_s:
            best = end
            break
    c1 = best if best is not None else last_ok
    if c1 is None or c1 - c0 < min_s:
        return None, f"could not fit {min_s:.0f}s of speech after {m:.1f}s inside the piece"
    return (round(c0, 3), round(c1, 3)), "ok"


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
        cold_min = float(cfg.get("coldopen_min_s", COLDOPEN_MIN_S))
        cold_max = float(cfg.get("coldopen_max_s", COLDOPEN_MAX_S))
        if not (cold_min <= c1 - c0 <= cold_max):
            raise ValueError(f"cold open {c1 - c0:.2f}s is outside "
                             f"{cold_min:.0f}-{cold_max:.0f}s")
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
    scale_flags = str(cfg.get("scale_flags", "")).strip()
    scale_suffix = f":flags={scale_flags}" if scale_flags else ""
    clarity = str(cfg.get("clarity_filter", "")).strip().strip(",")
    clarity_suffix = f",{clarity}" if clarity else ""
    chain = (
        f"{vlabel}{pre}scale={w}:{h}:force_original_aspect_ratio=decrease{scale_suffix}"
        f"{clarity_suffix},"
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
                f"{pre}scale={w}:{h}:force_original_aspect_ratio=decrease{scale_suffix}"
                f"{clarity_suffix},"
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
        *encode_args(cfg),
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
    duo_punch: Sequence[tuple[str, str]] | None = None,
    duo_punch_filters: tuple[str, str] | None = None,
    duo_punch_post: tuple[str, str] | None = None,
    cta: dict[str, Any] | None = None,
) -> float:
    """Render the short. `duo_punch` (SHORTS_EDITOR_V2) gives per-segment
    (top, bottom) windows for the fixed 50/50 stack from layout.compose —
    subject-centred, with the speaker's tile zoomed on a punched segment.
    Without it the render is exactly the static duo_fill / legacy path.

    `cta` is the record cta.build_assets returned: the "FULL VIDEO" call to
    action's PNG sequence (and its sound) composited AFTER the watermark in
    this same pass — one encode, no second re-encode of the picture."""
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

    # SHORTS_EDITOR_V2: per-segment windows on the fixed 50/50 stack. Same
    # trims, same cut points; the divider never moves.
    punched = bool(mode == "duo_fill" and duo_punch)
    punch_chain = ""
    if punched:
        if len(duo_punch) != len(segments):
            raise ValueError("duo_punch needs one (top, bottom) window per segment")
        clarity_cfg = cfg.get("clarity") or {}
        punch_chain = duo_punch_filter(segments, offset_s, duo_punch, w, h, tile_filters=duo_punch_filters,
                                       scale_flags=str(clarity_cfg.get("scale_flags", "") or ""),
                                       tile_post=duo_punch_post)

    tail = f"[vv]fps={fps}"

    # Colour correction — the SHORT FLOOR grade, one source for the legacy
    # and the V2 path alike (see short_grade_filter). It grades the PICTURE
    # before the captions burn in, so caption white is never lifted.
    grade = short_grade_filter(cfg)
    if grade:
        tail += "," + grade

    # The paragraphs below describe the daily curve that this block applied
    # until 2026-09-06; it is still available as color.source: curve.
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
    # SHORTS_EDITOR_V2 keeps ONE mark in its reserved top-right box
    # (layout.watermark_box): the second, seam-pinned mark of the legacy stack
    # would sit inside the caption rail on the divider.
    if mode == "duo_fill" and cfg.get("watermark_per_tile", True) and not punched:
        wm_y = [wm_margin, h // 2 + wm_margin]
    wm_in, wm_filter = _watermark_chain(cfg, w, h, "vbase", "vwm", 0.11,
                                        y=wm_y)
    post = "[vwm]format=yuv420p[vout]"

    # The call to action (src/boydclips/cta.py) rides on top of the marked
    # frame: last overlay in, so nothing grades or sharpens its edges. Its
    # sound is mixed under the concatenated dialogue at the measured gain.
    cta_in: list[str] = []
    cta_filters = ""
    audio_out = "[ac]"
    if cta:
        from . import cta as _cta
        next_idx = 1 + len(wm_in) // 2
        cta_in, cta_v, cta_a = _cta.ffmpeg_chain(cta, next_idx, "vwm", "vcta", "ac", "acta")
        cta_filters = ";" + cta_v
        post = "[vcta]format=yuv420p[vout]"
        if cta_a:
            cta_filters += ";" + cta_a
            audio_out = "[acta]"

    if punched:
        filter_complex = f"{punch_chain};{tail};{wm_filter}{cta_filters};{post}"
    else:
        filter_complex = f"{trims};{concat};{vertical};{tail};{wm_filter}{cta_filters};{post}"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cwd = ass_path.parent if ass_path is not None else None
    _run([
        "ffmpeg", "-y", "-i", str(source.resolve()), *wm_in, *cta_in,
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", audio_out,
        *encode_args(cfg),
        "-c:a", "aac", "-b:a", cfg.get("audio_bitrate", "160k"),
        "-movflags", "+faststart",
        str(out_path.resolve()),
    ], cwd=cwd)
    return probe_duration(out_path)


def encode_args(cfg: dict[str, Any]) -> list[str]:
    """Return the shared upload encode policy for any pipeline video.

    ``encode.mode: average_bitrate`` gives Shorts a measurable upload target;
    ``encode.mode: crf`` preserves the long-form CRF workflow.  Legacy top-level
    ``preset``/``crf`` keys remain valid so old fixtures and saved configs render
    reproducibly.
    """
    policy = dict(cfg.get("encode") or {})
    mode = str(policy.get("mode", "crf")).strip().lower()
    preset = str(policy.get("preset", cfg.get("preset", "medium")))
    args = ["-c:v", "libx264", "-preset", preset]
    if mode == "average_bitrate":
        bitrate = str(policy.get("video_bitrate", "")).strip()
        if not bitrate:
            raise ValueError("average_bitrate encode mode needs video_bitrate")
        args += ["-b:v", bitrate]
        if policy.get("minrate"):
            args += ["-minrate", str(policy["minrate"])]
        if policy.get("maxrate"):
            args += ["-maxrate", str(policy["maxrate"])]
        if policy.get("bufsize"):
            args += ["-bufsize", str(policy["bufsize"])]
        if policy.get("x264_params"):
            args += ["-x264-params", str(policy["x264_params"])]
    elif mode == "crf":
        args += ["-crf", str(policy.get("crf", cfg.get("crf", 20)))]
    else:
        raise ValueError(f"unknown encode mode: {mode}")
    args += ["-pix_fmt", "yuv420p"]
    return args


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
