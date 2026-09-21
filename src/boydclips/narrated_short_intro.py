"""Reusable moving source B-roll for explicitly approved Short narration."""
from __future__ import annotations

import json
import hashlib
import math
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import render
from PIL import Image, ImageDraw, ImageFont


@dataclass(frozen=True)
class Shot:
    source_start_s: float
    voice_end_s: float
    crop: str


@dataclass(frozen=True)
class FreezeCircleCue:
    """A brief deliberate freeze at the narration seam, followed by live B-roll."""

    source_frame_s: float
    duration_s: float
    crop: str
    circle_box: tuple[int, int, int, int]
    circle_start_s: float
    circle_complete_s: float
    ding_path: Path
    ding_at_s: float


@dataclass(frozen=True)
class SourceHookSpec:
    """One exact, separately rendered courtroom hook clip before narration."""

    path: Path
    source_start_s: float
    source_end_s: float
    text: str
    speaker: str
    sha256: str

    def validate(self) -> None:
        if not self.path.is_file():
            raise FileNotFoundError(f"approved source hook missing: {self.path}")
        if self.source_start_s < 0 or self.source_end_s <= self.source_start_s:
            raise ValueError("source hook requires a complete positive source span")
        if not self.text.strip() or not self.speaker.strip():
            raise ValueError("source hook requires its own exact text and speaker")
        digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        if digest != self.sha256:
            raise ValueError("approved source hook hash differs")
        expected = self.source_end_s - self.source_start_s
        if abs(render.probe_duration(self.path) - expected) > 0.12:
            raise ValueError("source hook duration does not match its exact source span")


def validate_source_hooks(hooks: tuple[SourceHookSpec, ...]) -> None:
    """Keep each hook as an exact clip; gaps never become joined caption text."""
    previous_end = -1.0
    for hook in hooks:
        hook.validate()
        if hook.source_start_s < previous_end:
            raise ValueError("source hook spans must stay in declared source order without overlap")
        previous_end = hook.source_end_s


@dataclass(frozen=True)
class NarratedIntroSpec:
    voice_path: Path
    text: str
    shots: tuple[Shot, ...]
    caption_cues: tuple[tuple[float, float, str], ...]
    narrator_label: str = ""
    freeze_circle: FreezeCircleCue | None = None
    transition_sfx_path: Path | None = None
    transition_sfx_gain_db: float = -24.0

    def validate(self, voice_duration: float) -> None:
        if not self.voice_path.is_file():
            raise FileNotFoundError(f"approved narration missing: {self.voice_path}")
        if self.transition_sfx_path is not None and not self.transition_sfx_path.is_file():
            raise FileNotFoundError(f"approved handoff SFX missing: {self.transition_sfx_path}")
        if not self.shots or not self.caption_cues:
            raise ValueError("approved narration requires moving shots and timed caption cues")
        moving_start = 0.0
        if self.freeze_circle is not None:
            cue = self.freeze_circle
            if not cue.ding_path.is_file():
                raise FileNotFoundError(f"approved ding missing: {cue.ding_path}")
            if cue.source_frame_s < 0 or not 0 < cue.duration_s <= 0.8:
                raise ValueError("freeze must be a brief in-range source beat")
            if not 0 <= cue.circle_start_s < cue.circle_complete_s <= cue.duration_s:
                raise ValueError("circle timing must complete inside the brief freeze")
            visible_complete_s = math.ceil(cue.circle_complete_s * 30 - 1e-7) / 30
            if cue.ding_at_s + 1e-7 < visible_complete_s or cue.ding_at_s > cue.duration_s:
                raise ValueError("ding cannot land before the circle is complete")
            x1, y1, x2, y2 = cue.circle_box
            if not (0 <= x1 < x2 <= 1080 and 0 <= y1 < y2 <= 1920):
                raise ValueError("circle box must lie inside the vertical frame")
            moving_start = cue.duration_s
        ends = [s.voice_end_s for s in self.shots]
        if ends[0] <= moving_start or any(b <= a for a, b in zip(ends, ends[1:])) or abs(ends[-1] - voice_duration) > 0.12:
            raise ValueError("shot timing must end on the measured narration duration")
        if abs(self.caption_cues[-1][1] - voice_duration) > 0.2:
            raise ValueError("narrator captions must cover the measured narration duration")
        for shot in self.shots:
            parts = [int(v) for v in shot.crop.split(":" )]
            if len(parts) != 4 or min(parts[2:]) < 0 or min(parts[:2]) <= 0:
                raise ValueError(f"invalid source crop: {shot.crop}")
            if shot.source_start_s < 0:
                raise ValueError("source shot time cannot be negative")
        previous = -1.0
        spoken = []
        for start, end, text in self.caption_cues:
            if start < 0 or end <= start or start < previous or end > voice_duration + 0.12:
                raise ValueError("narrator caption cues overlap or leave the voice range")
            previous = end; spoken.append(text)
        norm = lambda s: re.sub(r"[^a-z0-9']+", " ", s.replace(r"\N", " ").lower()).strip()
        if norm(" ".join(spoken)) != norm(self.text):
            raise ValueError("narrator caption text does not match the approved spoken text")


def _crop_parts(value: str) -> tuple[int, int, int, int]:
    try:
        width, height, x, y = (int(part) for part in value.split(":"))
    except (TypeError, ValueError):
        raise ValueError(f"invalid source crop: {value}") from None
    if width <= 0 or height <= 0 or x < 0 or y < 0:
        raise ValueError(f"invalid source crop: {value}")
    return width, height, x, y


def _validate_crop_bounds(value: str, source_size: tuple[int, int]) -> None:
    width, height, x, y = _crop_parts(value)
    source_width, source_height = source_size
    if x + width > source_width or y + height > source_height:
        raise ValueError(f"source crop lies outside the local source: {value}")


def _circle_frames(cue: FreezeCircleCue, folder: Path, fps: int = 30) -> int:
    """Write the measured callout only; the frozen source frame stays video-derived."""
    folder.mkdir(parents=True, exist_ok=True)
    count = max(1, math.ceil(cue.duration_s * fps))
    for old in folder.glob("circle_*.png"):
        old.unlink()
    for index in range(count):
        frame_time = index / fps
        progress = min(1.0, max(0.0, (frame_time - cue.circle_start_s) /
                                (cue.circle_complete_s - cue.circle_start_s)))
        image = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
        if progress > 0:
            draw = ImageDraw.Draw(image)
            end = -92 + 360 * progress
            draw.arc(cue.circle_box, start=-92, end=end, fill=(238, 48, 48, 230), width=13)
            inset = (cue.circle_box[0] + 4, cue.circle_box[1] - 3,
                     cue.circle_box[2] - 2, cue.circle_box[3] + 3)
            draw.arc(inset, start=-88, end=-88 + 354 * progress,
                     fill=(255, 74, 48, 145), width=5)
        image.save(folder / f"circle_{index:03d}.png")
    return count


def _ass(spec: NarratedIntroSpec, path: Path) -> None:
    def ts(t: float) -> str:
        cs = round(t * 100); return f"0:{cs // 6000:02d}:{(cs // 100) % 60:02d}.{cs % 100:02d}"
    head = """[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 2\n\n[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\nStyle: Narrator,Archivo,68,&H00FFFFFF,&H00FFFFFF,&H00101010,&H70000000,1,0,0,0,100,100,0,0,1,4,1,2,90,90,330,1\nStyle: Label,Archivo,28,&H003FD2FF,&H003FD2FF,&H00101010,&H70000000,1,0,0,0,100,100,1,0,1,3,0,2,90,90,430,1\n\n[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"""
    font_path = Path(__file__).resolve().parents[2] / "assets/fonts/Archivo-Var.ttf"
    font = ImageFont.truetype(str(font_path), 68)
    def wrap(text: str) -> str:
        if r"\N" in text:
            lines = text.split(r"\N")
            if len(lines) != 2 or max(font.getlength(line) for line in lines) > 850:
                raise ValueError("explicit narrator caption split exceeds two phone-safe lines")
            return text
        words = text.split(); best = text; best_balance = float("inf")
        for k in range(1, len(words)):
            a, b = " ".join(words[:k]), " ".join(words[k:])
            widths = [font.getlength(a), font.getlength(b)]
            balance = abs(widths[0] - widths[1])
            if max(widths) <= 850 and balance < best_balance:
                best = a + r"\N" + b
                best_balance = balance
        if r"\N" not in best and font.getlength(best) > 850:
            raise ValueError("narrator caption cannot fit within x=90..940 in two lines")
        return best
    rows = []
    for start, end, text in spec.caption_cues:
        if spec.narrator_label.strip():
            rows.append(f"Dialogue: 0,{ts(start)},{ts(end)},Label,,0,0,0,,{{\\pos(540,1390)}}{spec.narrator_label}")
        rows.append(f"Dialogue: 0,{ts(start)},{ts(end)},Narrator,,0,0,0,,{{\\pos(540,1530)}}{wrap(text)}")
    path.write_text(head + "\n".join(rows) + "\n", encoding="utf-8")


def render_moving_broll(source: Path, source_offset_s: float, spec: NarratedIntroSpec,
                        output: Path, encode_cfg: dict, evidence_path: Path | None = None) -> dict:
    """Render normal-speed source shots; missing approved timing fails closed."""
    duration = render.probe_duration(spec.voice_path)
    spec.validate(duration)
    ass = output.with_suffix(".narrator.ass")
    _ass(spec, ass)
    inputs: list[str] = []
    filters: list[str] = []
    prior = spec.freeze_circle.duration_s if spec.freeze_circle else 0.0
    if not source.is_file():
        raise FileNotFoundError(f"source video missing: {source}")
    source_duration = render.probe_duration(source)
    source_size = render.probe_dimensions(source)
    input_index = 0
    video_labels: list[str] = []
    if spec.freeze_circle is not None:
        cue = spec.freeze_circle
        _validate_crop_bounds(cue.crop, source_size)
        local_frame = cue.source_frame_s - source_offset_s
        if local_frame < 0 or local_frame > source_duration:
            raise ValueError("approved freeze frame lies outside the local source")
        inputs += ["-ss", f"{local_frame:.3f}", "-t", "0.100", "-i", str(source)]
        freeze_input = input_index
        input_index += 1
    for i, shot in enumerate(spec.shots):
        _validate_crop_bounds(shot.crop, source_size)
        d = shot.voice_end_s - prior
        local_start = shot.source_start_s - source_offset_s
        if local_start < 0 or local_start + d > source_duration + 0.05:
            raise ValueError("approved narration shot lies outside the local source")
        inputs += ["-ss", f"{shot.source_start_s-source_offset_s:.3f}", "-t", f"{d:.3f}", "-i", str(source)]
        source_index = input_index
        input_index += 1
        bg = (f"[{source_index}:v]crop={shot.crop},setpts=PTS-STARTPTS,split=2[b{i}][p{i}];[b{i}]scale=1080:1920:force_original_aspect_ratio=increase,"
              f"crop=1080:1920,gblur=sigma=28,eq=brightness=-0.22[bg{i}];"
              f"[p{i}]scale=1080:1198:flags=lanczos[panel{i}];"
              f"[bg{i}][panel{i}]overlay=0:100,setsar=1,fps=30[v{i}]")
        filters.append(bg)
        video_labels.append(f"[v{i}]")
        prior = shot.voice_end_s
    voice_index = input_index
    inputs += ["-i", str(spec.voice_path)]
    input_index += 1
    ding_index: int | None = None
    if spec.freeze_circle is not None:
        cue = spec.freeze_circle
        circle_folder = output.parent / f"{output.stem}_circle_frames"
        _circle_frames(cue, circle_folder)
        inputs += ["-framerate", "30", "-t", f"{cue.duration_s:.3f}", "-i",
                   str(circle_folder / "circle_%03d.png")]
        circle_index = input_index
        input_index += 1
        inputs += ["-i", str(cue.ding_path)]
        ding_index = input_index
        input_index += 1
        freeze = (
            f"[{freeze_input}:v]crop={cue.crop},setpts=PTS-STARTPTS,split=2[fb][fp];"
            "[fb]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
            "gblur=sigma=28,eq=brightness=-0.22[fbg];"
            "[fp]scale=1080:1198:flags=lanczos[fpanel];"
            f"[fbg][fpanel]overlay=0:100,setsar=1,trim=end_frame=1,setpts=PTS-STARTPTS,"
            f"tpad=stop_mode=clone:stop_duration={cue.duration_s:.3f},fps=30,"
            f"trim=duration={cue.duration_s:.3f}[freezebase];"
            f"[freezebase][{circle_index}:v]overlay=0:0:shortest=1[freeze]"
        )
        filters.append(freeze)
        video_labels.insert(0, "[freeze]")
    filters.append("".join(video_labels) + f"concat=n={len(video_labels)}:v=1:a=0[cat]")
    escaped = str(ass).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    fonts = str(Path(__file__).resolve().parents[2] / "assets/fonts").replace("\\", "/").replace(":", "\\:")
    filters.append(f"[cat]subtitles='{escaped}':fontsdir='{fonts}'[sub]")
    wm_inputs, wm_filter = render._watermark_chain(encode_cfg, 1080, 1920, "sub", "v", 0.11,
                                                    wm_index=input_index, y=135)
    inputs += wm_inputs
    filters.append(wm_filter)
    if spec.freeze_circle is not None:
        cue = spec.freeze_circle
        delay_ms = round(cue.ding_at_s * 1000)
        filters.append(
            f"[{voice_index}:a]aresample=48000,aformat=channel_layouts=stereo[voice];"
            f"[{ding_index}:a]aresample=48000,aformat=channel_layouts=stereo,"
            f"volume=0.20,adelay={delay_ms}:all=1[ding];"
            "[voice][ding]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]"
        )
        audio_map = "[a]"
    else:
        audio_map = f"{voice_index}:a"
    cmd = ["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(filters),
           "-map", "[v]", "-map", audio_map, *render.encode_args(encode_cfg),
           "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2", "-shortest", str(output)]
    subprocess.run(cmd, check=True)
    record = {"output": str(output.resolve()), "duration_s": render.probe_duration(output), "text": spec.text,
              "shots": [s.__dict__ for s in spec.shots], "caption_cues": list(spec.caption_cues),
              "moving_source": True, "court_dialogue_captions": False}
    if spec.freeze_circle is not None:
        cue = spec.freeze_circle
        record["freeze_circle"] = {
            "source_frame_s": cue.source_frame_s,
            "duration_s": cue.duration_s,
            "crop": cue.crop,
            "circle_box": list(cue.circle_box),
            "circle_start_s": cue.circle_start_s,
            "circle_complete_s": cue.circle_complete_s,
            "visible_circle_complete_s": math.ceil(cue.circle_complete_s * 30 - 1e-7) / 30,
            "ding_at_s": cue.ding_at_s,
            "moving_broll_starts_s": cue.duration_s,
            "whole_narration_frozen": False,
        }
    if spec.transition_sfx_path is not None:
        record["transition_sfx"] = {
            "path": str(spec.transition_sfx_path.resolve()),
            "gain_db": spec.transition_sfx_gain_db,
            "cue": "narration_body_seam",
        }
    if evidence_path:
        evidence_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def mix_transition_sfx(video: Path, output: Path, sfx_path: Path, at_s: float,
                       gain_db: float = -24.0) -> dict:
    """Add an approved local handoff sound without changing the video stream."""
    if not video.is_file():
        raise FileNotFoundError(f"handoff input video missing: {video}")
    if not sfx_path.is_file():
        raise FileNotFoundError(f"approved handoff SFX missing: {sfx_path}")
    duration = render.probe_duration(video)
    if at_s < 0 or at_s >= duration:
        raise ValueError("handoff SFX cue must lie inside the output timeline")
    delay_ms = round(at_s * 1000)
    cmd = [
        "ffmpeg", "-y", "-v", "error", "-i", str(video), "-i", str(sfx_path),
        "-filter_complex",
        f"[1:a]aresample=48000,aformat=channel_layouts=stereo,volume={gain_db}dB,"
        f"adelay={delay_ms}:all=1[whoosh];"
        "[0:a][whoosh]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]",
        "-map", "0:v", "-map", "[a]", "-map_metadata", "0", "-c:v", "copy",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", str(output),
    ]
    subprocess.run(cmd, check=True)
    return {"path": str(sfx_path.resolve()), "at_s": at_s, "gain_db": gain_db,
            "duration_s": render.probe_duration(sfx_path)}
