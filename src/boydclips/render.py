"""Stage 3 — download only what gets published, then cut it.

Video enters the pipeline here and nowhere else. By this point exactly one case
has been selected, so we fetch that case's minutes rather than the docket's
hours, using yt-dlp's --download-sections with keyframe forcing so the returned
file starts precisely at the requested timestamp.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .transcribe import Word

# Generous margin around the requested case so head/tail padding and any
# keyframe slop have material to work with.
SECTION_MARGIN_S = 20.0

# Where the stacked pair sits on the 1920px canvas, and how much clear space
# the captions need beneath it.
STACK_TOP_Y = 120
CAPTION_BAND_MIN = 180

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


def detect_content_crop(source: Path, sample_start: float = 5.0, sample_s: float = 25.0) -> str | None:
    """Find the real content rectangle inside a letterboxed source.

    The court's Zoom recordings are letterboxed *inside* their own 16:9 frame —
    the participant tiles sit in a band with baked-in black bars above and
    below. Scaling that whole frame into a 9:16 canvas leaves the courtroom at
    a fraction of the screen and fills the rest with blurred black.

    Returns an ffmpeg `crop=` argument, or None when the frame is already full.
    """
    proc = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-nostats",
            "-ss", f"{sample_start:.2f}", "-t", f"{sample_s:.2f}",
            "-i", str(source),
            "-vf", "cropdetect=limit=24:round=2:reset=0",
            "-f", "null", "-",
        ],
        capture_output=True, text=True, timeout=300,
    )

    crops = re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", proc.stderr)
    if not crops:
        return None

    w, h, x, y = (int(v) for v in crops[-1])
    if w <= 0 or h <= 0:
        return None

    src_w, src_h = probe_dimensions(source)
    if not src_w or not src_h:
        return None

    # A crop that keeps almost everything isn't worth applying, and one that
    # throws most of the frame away is usually cropdetect misreading a dark
    # shot rather than a genuine letterbox.
    area_ratio = (w * h) / float(src_w * src_h)
    if area_ratio > 0.92 or area_ratio < 0.15:
        return None

    return f"crop={w}:{h}:{x}:{y}"


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


# --------------------------------------------------------------- acquisition


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

    _run(
        [
            "yt-dlp", "--no-warnings", "--ignore-config",
            # A single transient 403 from googlevideo otherwise kills the whole
            # unattended run. Observed 2026-08-10: the section download failed
            # with "403 Forbidden" while the same command succeeded moments
            # later, so the URL was expiring or being throttled mid-transfer
            # rather than the video being unavailable.
            "--retries", "10",
            "--fragment-retries", "10",
            "--extractor-retries", "5",
            "--retry-sleep", "exp=2:60",
            "--download-sections", f"*{section_start:.2f}-{section_end:.2f}",
            # Without this, the file starts at the preceding keyframe and every
            # timestamp downstream drifts by up to several seconds.
            "--force-keyframes-at-cuts",
            "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "--merge-output-format", "mp4",
            "-o", str(out_path),
            f"https://www.youtube.com/watch?v={video_id}",
        ],
        timeout=3600,
    )

    if not out_path.exists():
        raise RuntimeError(f"section download produced no file for {video_id}")
    return out_path, section_start


# ------------------------------------------------------------------ captions


def group_words(
    words: list[Word], max_chars: int, max_lines: int
) -> list[list[Word]]:
    """Chunk the word stream into caption cards of at most max_lines lines."""
    budget = max_chars * max_lines
    groups: list[list[Word]] = []
    current: list[Word] = []
    length = 0

    for w in words:
        token = w.w.strip()
        if not token:
            continue
        added = len(token) + (1 if current else 0)
        if current and length + added > budget:
            groups.append(current)
            current, length = [], 0
            added = len(token)
        current.append(w)
        length += added

    if current:
        groups.append(current)
    return groups


def _wrap(tokens: list[str], max_chars: int, max_lines: int) -> list[list[int]]:
    """Distribute token indices across lines, returning index lists per line."""
    lines: list[list[int]] = [[]]
    width = 0
    for i, tok in enumerate(tokens):
        add = len(tok) + (1 if lines[-1] else 0)
        if lines[-1] and width + add > max_chars and len(lines) < max_lines:
            lines.append([])
            width = 0
            add = len(tok)
        lines[-1].append(i)
        width += add
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
) -> Path:
    """Word-highlight subtitles.

    One Dialogue event per word, each rendering the full caption card with only
    the active word recoloured. Simpler and far more predictable across libass
    versions than karaoke (\\k) timing tags.

    timeline_offset_s converts absolute source timestamps into output-clip time.
    """
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

    events: list[str] = []
    for group in group_words(words, max_chars, max_lines):
        tokens = [(w.w.strip().upper() if upper else w.w.strip()) for w in group]
        line_map = _wrap(tokens, max_chars, max_lines)

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
                    f"{{\\c{highlight}}}{tokens[j]}{{\\c{primary}}}" if j == i else tokens[j]
                    for j in line
                ]
                rendered_lines.append(" ".join(parts))
            text = "\\N".join(rendered_lines)
            events.append(
                f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Main,,0,0,0,,{text}"
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


def _concat_filter(segments: list[Segment], offset_s: float) -> tuple[str, str, str]:
    """Build trim/concat filter chains for N segments of one input."""
    parts: list[str] = []
    for i, seg in enumerate(segments):
        a = max(0.0, seg.start_s - offset_s)
        b = max(a + 0.05, seg.end_s - offset_s)
        parts.append(
            f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS[v{i}];"
            f"[0:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS[a{i}]"
        )
    pairs = "".join(f"[v{i}][a{i}]" for i in range(len(segments)))
    concat = f"{pairs}concat=n={len(segments)}:v=1:a=1[vc][ac]"
    return ";".join(parts), concat, "[vc]"


def render_longform(
    source: Path,
    offset_s: float,
    segments: list[Segment],
    cfg: dict[str, Any],
    out_path: Path,
    crop: str | None = None,
) -> float:
    w, h = cfg.get("resolution", [1920, 1080])
    trims, concat, vlabel = _concat_filter(segments, offset_s)
    pre = f"{crop}," if crop else ""

    chain = (
        f"{vlabel}{pre}scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"fps={cfg.get('fps', 30)},format=yuv420p[vout]"
    )
    filter_complex = f"{trims};{concat};{chain}"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y", "-i", str(source),
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "[ac]",
        "-c:v", "libx264", "-preset", "medium", "-crf", str(cfg.get("crf", 20)),
        "-c:a", "aac", "-b:a", cfg.get("audio_bitrate", "192k"),
        "-movflags", "+faststart",
        str(out_path),
    ])
    return probe_duration(out_path)


def render_short(
    source: Path,
    offset_s: float,
    segments: list[Segment],
    cfg: dict[str, Any],
    ass_path: Path | None,
    out_path: Path,
    crop: str | None = None,
) -> float:
    w, h = cfg.get("resolution", [1080, 1920])
    fps = cfg.get("fps", 30)
    trims, concat, vlabel = _concat_filter(segments, offset_s)
    # Strip the source's baked-in letterbox first, or the participants end up
    # occupying a fraction of the vertical canvas.
    pre = f"{crop}," if crop else ""

    mode = cfg.get("vertical_mode", "auto")
    if mode == "auto":
        mode, _ = choose_vertical_layout(source, crop, cfg)

    if mode == "center_crop":
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
        vertical = (
            f"{vlabel}{pre}split=3[bg][l][r];"
            f"[bg]scale={sw}:{sh}:force_original_aspect_ratio=increase,"
            f"crop={sw}:{sh},gblur=sigma={sigma:.1f},"
            f"eq=brightness=-0.25:saturation=0.6,scale={w}:{h}[bgb];"
            f"[l]crop=iw/2:ih:0:0,scale={w}:-2[lt];"
            f"[r]crop=iw/2:ih:iw/2:0,scale={w}:-2[rt];"
            f"[lt][rt]vstack=inputs=2[stk];"
            # Anchored near the top rather than centred, so the lower band is
            # free for captions instead of them sitting over a participant.
            f"[bgb][stk]overlay=(W-w)/2:{STACK_TOP_Y}[vv]"
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
            f"{vlabel}{pre}split=2[bg][fg];"
            f"[bg]scale={sw}:{sh}:force_original_aspect_ratio=increase,"
            f"crop={sw}:{sh},gblur=sigma={sigma:.1f},"
            f"eq=brightness=-{(1 - darken) * 0.5:.3f}:saturation=0.7,"
            f"scale={w}:{h}[bgb];"
            f"[fg]scale={w}:-2[fgs];"
            f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2[vv]"
        )

    tail = f"[vv]fps={fps}"
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
    tail += ",format=yuv420p[vout]"

    filter_complex = f"{trims};{concat};{vertical};{tail}"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cwd = ass_path.parent if ass_path is not None else None
    _run([
        "ffmpeg", "-y", "-i", str(source.resolve()),
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
