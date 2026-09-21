"""download_section cuts from a local full docket when one exists, with the
file's t=0 at section_start (frame-accurate), and never touches yt-dlp."""
import shutil
import subprocess

import pytest

from boydclips import render

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
                                reason="ffmpeg not on PATH")


def _synthetic(path, seconds=6.0):
    # a timecode-like signal: frame number encoded as luma ramp per second via testsrc's clock
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                    "-i", f"testsrc2=size=320x180:rate=30:duration={seconds}",
                    "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
                    "-c:v", "libx264", "-g", "60", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)], check=True)


def _duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def test_cut_from_full_docket(tmp_path, monkeypatch):
    vid = "testvid0001"
    work = tmp_path / vid
    work.mkdir()
    full = render.full_docket_path(vid, work)
    _synthetic(full)
    called = []
    monkeypatch.setattr(render, "SECTION_PLAYER_CLIENTS", ())  # yt-dlp must not be reached
    monkeypatch.setattr(render, "_run", lambda cmd, **kw: called.append(cmd) or subprocess.run(cmd, check=True))
    # section_start = max(0, start - margin); pick start so the cut begins mid-GOP
    start_s = render.SECTION_MARGIN_S + 1.5
    path, offset = render.download_section(vid, start_s, start_s + 2.0, work / "case.mp4")
    assert path.exists() and offset == pytest.approx(1.5)
    assert path.name == f"case_{int(offset)}-{int(start_s + 2.0 + render.SECTION_MARGIN_S)}.mp4"
    assert called and called[0][0] == "ffmpeg"
    # the cut runs from 1.5 s to min(end, 6.0) = 6.0 -> 4.5 s
    assert _duration(path) == pytest.approx(4.5, abs=0.15)


def test_cached_cut_is_reused(tmp_path, monkeypatch):
    vid = "testvid0002"
    work = tmp_path / vid
    work.mkdir()
    _synthetic(render.full_docket_path(vid, work), seconds=3.0)
    monkeypatch.setattr(render, "SECTION_PLAYER_CLIENTS", ())
    p1, o1 = render.download_section(vid, 0.5, 1.5, work / "c.mp4")
    m1 = p1.stat().st_mtime_ns
    p2, o2 = render.download_section(vid, 0.5, 1.5, work / "c.mp4")
    assert p1 == p2 and o1 == o2 and p2.stat().st_mtime_ns == m1
