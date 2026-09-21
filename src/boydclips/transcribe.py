"""Stage 1 — get a word-timed transcript without downloading any video.

This is the load-bearing efficiency decision in the whole pipeline. The channel
publishes 1.5–3 hour streams, often twice a day. Downloading all of that to find
one good case would be ~15 GB/week. YouTube's auto-captions are free, available
on this channel, and carry per-word timings in the json3 format — enough to both
analyse the docket and cut it frame-accurately later.

Video is only ever downloaded for the handful of minutes we actually publish.
"""

from __future__ import annotations

import glob
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Word:
    t: float   # seconds from video start
    w: str


@dataclass
class Transcript:
    video_id: str
    words: list[Word] = field(default_factory=list)
    source: str = "auto_captions"

    @property
    def duration_s(self) -> float:
        return self.words[-1].t if self.words else 0.0

    def slice(self, start_s: float, end_s: float) -> list[Word]:
        return [w for w in self.words if start_s <= w.t <= end_s]

    def text_between(self, start_s: float, end_s: float) -> str:
        return " ".join(w.w for w in self.slice(start_s, end_s))

    def to_json(self) -> str:
        return json.dumps(
            {
                "video_id": self.video_id,
                "source": self.source,
                "words": [{"t": round(w.t, 3), "w": w.w} for w in self.words],
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, raw: str) -> "Transcript":
        data = json.loads(raw)
        return cls(
            video_id=data["video_id"],
            source=data.get("source", "auto_captions"),
            words=[Word(t=w["t"], w=w["w"]) for w in data["words"]],
        )

    def render_for_llm(self, window_s: float = 10.0) -> str:
        """Timestamped lines for the analysis prompts.

        Grouping to ~10s windows rather than emitting per-word keeps a 3-hour
        docket around 35-45k tokens while preserving enough timing granularity
        for the model to return usable cut points.
        """
        if not self.words:
            return ""

        lines: list[str] = []
        bucket: list[str] = []
        bucket_start = self.words[0].t

        for w in self.words:
            if w.t - bucket_start >= window_s and bucket:
                lines.append(f"[{_hhmmss(bucket_start)}] {' '.join(bucket)}")
                bucket = []
                bucket_start = w.t
            bucket.append(w.w)

        if bucket:
            lines.append(f"[{_hhmmss(bucket_start)}] {' '.join(bucket)}")
        return "\n".join(lines)


def _hhmmss(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def hhmmss(seconds: float) -> str:
    return _hhmmss(seconds)


def fetch_captions(video_id: str, work_dir: Path, language: str = "en") -> Transcript | None:
    """Download auto-captions in json3 and parse to word timings.

    Returns None when the video has no usable English captions, which is the
    signal for the Whisper fallback.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    stem = work_dir / video_id

    proc = subprocess.run(
        [
            "yt-dlp", "--no-warnings", "--ignore-config",
            "--skip-download",
            "--write-auto-subs", "--write-subs",
            "--sub-langs", f"{language}.*,{language}",
            "--sub-format", "json3",
            "-o", str(stem),
            f"https://www.youtube.com/watch?v={video_id}",
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )

    matches = sorted(glob.glob(str(stem) + f".{language}*.json3"))
    if not matches:
        if proc.returncode != 0:
            raise RuntimeError(f"caption fetch failed: {proc.stderr.strip()[:400]}")
        return None

    # YouTube often exposes several near-identical English tracks (en, en-orig,
    # en-US). Prefer the plain tag so the choice is stable rather than whatever
    # sorts first.
    exact = str(stem) + f".{language}.json3"
    chosen = Path(exact) if exact in matches else Path(matches[0])

    words = parse_json3(chosen.read_text(encoding="utf-8"))
    if not words:
        return None
    return Transcript(video_id=video_id, words=words, source="auto_captions")


def parse_json3(raw: str) -> list[Word]:
    """Parse YouTube's json3 caption format into a flat word stream.

    json3 events carry `tStartMs` plus a `segs` list, where each segment has
    `utf8` text and an optional `tOffsetMs` from the event start. Events without
    `segs` are window/style definitions and carry no text. Auto-captions also
    emit rolling-duplicate events for the scroll-up effect; those are marked
    with `aAppend` and must be skipped or every word appears twice.
    """
    data = json.loads(raw)
    words: list[Word] = []

    for event in data.get("events", []):
        if event.get("aAppend"):
            continue
        segs = event.get("segs")
        if not segs:
            continue
        base_ms = event.get("tStartMs", 0)
        for seg in segs:
            text = (seg.get("utf8") or "").strip()
            if not text or text == "\n":
                continue
            t = (base_ms + seg.get("tOffsetMs", 0)) / 1000.0
            words.append(Word(t=t, w=text))

    words.sort(key=lambda w: w.t)
    return words


def transcribe_whisper(video_id: str, work_dir: Path, model: str = "medium") -> Transcript:
    """Fallback for streams published without auto-captions.

    Downloads audio only (not video) and runs faster-whisper locally. Rare
    enough on this channel that it is not on the hot path.
    """
    try:
        from faster_whisper import WhisperModel  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(
            "No captions available and faster-whisper is not installed. "
            "Install with: pip install faster-whisper"
        ) from exc

    work_dir.mkdir(parents=True, exist_ok=True)
    audio = work_dir / f"{video_id}.m4a"

    if not audio.exists():
        subprocess.run(
            [
                "yt-dlp", "--no-warnings", "--ignore-config",
                "-f", "bestaudio[ext=m4a]/bestaudio",
                "-o", str(audio),
                f"https://www.youtube.com/watch?v={video_id}",
            ],
            check=True,
            timeout=3600,
        )

    whisper = WhisperModel(model, device="auto", compute_type="auto")
    segments, _ = whisper.transcribe(str(audio), word_timestamps=True, language="en")

    words: list[Word] = []
    for seg in segments:
        for w in (seg.words or []):
            token = w.word.strip()
            if token:
                words.append(Word(t=float(w.start), w=token))

    return Transcript(video_id=video_id, words=words, source=f"whisper:{model}")


# Phrases the auto-captions reliably get wrong, applied to every transcript.
#
# "Bexar" is pronounced "bear", and YouTube transcribes it phonetically EVERY
# time: 176 occurrences of "Bear County" across 29 cached transcripts, zero
# correct. This is not a per-clip typo — it is the county's name, it reaches
# burned-in captions, titles, descriptions AND the text the scoring model reads,
# and local viewers notice it immediately.
#
# Keys are matched case-insensitively across word boundaries; the replacement
# preserves the original token count so word timings stay aligned.
PHRASE_FIXES: dict[str, str] = {
    "bear county": "Bexar County",
    "bear kounty": "Bexar County",
}

# Nathan heard and locked this one Perry line against the source audio.  It is
# case-specific: the same auto-caption text elsewhere must remain untouched.
CASE_PHRASE_FIXES: dict[str, dict[str, str]] = {
    "oL6lV6gCyOc": {
        "when i made them choices back then it ain't nothing like that one":
            "when I made them choices back then it ain't nothin' like now",
        "y'all stipulated to you": "y'all stipulated to.",
    },
}

# Local large-v3 and medium.en independently recover the negation in this
# exact phone-dispute answer. Evidence: posting-recovery-implementation-2026-09-19
# media-qc/short-asr*.json. Match source time and original token so another
# speaker or case saying "would" never inherits this correction.
CASE_WORD_FIXES: dict[str, tuple[tuple[float, str, str], ...]] = {
    "IDGfe1rPUQo": ((6536.239, "would", "wouldn't"),),
}


def apply_phrase_fixes(words: list[Word]) -> tuple[list[Word], int]:
    """Correct known mistranscriptions in place, preserving timing.

    Only equal-length replacements are supported on purpose. Substituting a
    different number of tokens would require inventing timestamps, and a
    caption whose timing has drifted is worse than one with a wrong word.
    """
    if not words:
        return words, 0
    lowered = [w.w.lower().strip(".,?!:;") for w in words]
    fixed = 0
    for wrong, right in PHRASE_FIXES.items():
        wt, rt = wrong.split(), right.split()
        if len(wt) != len(rt):
            continue
        n = len(wt)
        for i in range(len(words) - n + 1):
            if lowered[i:i + n] == wt:
                for k in range(n):
                    # keep any trailing punctuation the original token carried
                    tail = ""
                    orig = words[i + k].w
                    while orig and orig[-1] in ".,?!:;":
                        tail = orig[-1] + tail
                        orig = orig[:-1]
                    words[i + k] = Word(t=words[i + k].t, w=rt[k] + tail)
                fixed += 1
    return words, fixed


def apply_case_phrase_fixes(video_id: str, words: list[Word]) -> tuple[list[Word], int]:
    """Apply source-verified fixes for one video while retaining word starts.

    A shorter correction leaves the final spurious ASR token empty.  The word
    list and every retained token timestamp therefore keep their original
    indices; caption consumers already ignore empty tokens.
    """
    fixes = CASE_PHRASE_FIXES.get(video_id, {})
    if not words:
        return words, 0
    lowered = [w.w.lower().strip(".,?!:;\"") for w in words]
    fixed = 0
    for wrong, right in fixes.items():
        wt, rt = wrong.lower().split(), right.split()
        n = len(wt)
        for i in range(len(words) - n + 1):
            if lowered[i:i + n] != wt:
                continue
            replacement = rt + [""] * (n - len(rt))
            for k, token in enumerate(replacement):
                words[i + k] = Word(t=words[i + k].t, w=token)
            fixed += 1
    for source_t, wrong, right in CASE_WORD_FIXES.get(video_id, ()):
        for i, word in enumerate(words):
            if abs(word.t - source_t) < 0.001 and word.w == wrong:
                words[i] = Word(t=word.t, w=right)
                fixed += 1
    return words, fixed


def get_transcript(
    video_id: str,
    work_dir: Path,
    *,
    source: str = "auto_captions",
    language: str = "en",
    whisper_fallback: bool = True,
    whisper_model: str = "medium",
) -> Transcript:
    """Cached transcript resolution. Transcripts are small and worth keeping —
    they make backfilling and re-scoring free."""
    cache = work_dir / f"{video_id}.transcript.json"
    if cache.exists():
        t = Transcript.from_json(cache.read_text(encoding="utf-8"))
        # Applied on read as well as on write, so transcripts cached before the
        # fix map existed are corrected without re-downloading anything.
        t.words, n = apply_phrase_fixes(t.words)
        t.words, case_n = apply_case_phrase_fixes(video_id, t.words)
        n += case_n
        if n:
            cache.write_text(t.to_json(), encoding="utf-8")
        return t

    transcript: Transcript | None = None

    if source in ("auto_captions", "auto_captions_then_whisper"):
        transcript = fetch_captions(video_id, work_dir, language)

    if transcript is None and (source == "whisper" or whisper_fallback):
        transcript = transcribe_whisper(video_id, work_dir, whisper_model)

    if transcript is None:
        raise RuntimeError(f"no transcript available for {video_id}")

    transcript.words, _ = apply_phrase_fixes(transcript.words)
    transcript.words, _ = apply_case_phrase_fixes(video_id, transcript.words)
    cache.write_text(transcript.to_json(), encoding="utf-8")
    return transcript
