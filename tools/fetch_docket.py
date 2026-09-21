"""Fetch a complete docket stream at line speed for local section cutting.

    python tools/fetch_docket.py <video_id> [<video_id> ...]

Writes work/<vid>/<vid>.full.mp4 (avc1 <= 1080p + mp4a, the same selector
render.download_section uses). render.download_section then cuts sections
from it with a frame-accurate re-encode instead of yt-dlp's ffmpeg ranged
fetch, which googlevideo throttled to ~110 KB/s on 2026-09-06.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boydclips.render import full_docket_path  # noqa: E402

FORMAT = ("bv*[vcodec^=avc1][height<=1080]+ba[acodec^=mp4a]/"
          "bv*[height<=1080]+ba/best[ext=mp4]/best")
CLIENTS = ("web_embedded", "mweb", "tv_simply", "android", "default")


def fetch(video_id: str, work_root: Path = ROOT / "work") -> Path:
    out = full_docket_path(video_id, work_root / video_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        print(f"{video_id}: already fetched ({out.stat().st_size / 1e6:.0f} MB)")
        return out
    last = None
    for client in CLIENTS:
        t0 = time.time()
        cmd = ["yt-dlp", "--no-warnings", "--ignore-config", "--retries", "10", "--fragment-retries", "10",
               "--extractor-retries", "5", "--retry-sleep", "exp=2:60", "--js-runtimes", "node",
               "-N", "8", "-f", FORMAT, "--merge-output-format", "mp4", "-o", str(out),
               *(() if client == "default" else ("--extractor-args", f"youtube:player_client={client}")),
               f"https://www.youtube.com/watch?v={video_id}"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0 and out.exists():
            print(f"{video_id}: fetched via {client} in {time.time() - t0:.0f}s ({out.stat().st_size / 1e6:.0f} MB)")
            return out
        last = "\n".join(r.stderr.strip().splitlines()[-5:])
        for stale in out.parent.glob(f"{out.stem}*.part"):
            stale.unlink(missing_ok=True)
        print(f"{video_id}: {client} failed: {last}")
    raise RuntimeError(f"{video_id}: no client produced a file; last error:\n{last}")


if __name__ == "__main__":
    for vid in sys.argv[1:]:
        fetch(vid)
