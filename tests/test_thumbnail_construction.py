"""The thumbnail's hero slot and its refusal behaviour, measured 2026-09-16.

A run on dAKO7myCd-g:8929 died in `thumb_Q3_detail.py` with "cannot identify the
defendant - pick another frame" AFTER its long-form had rendered. Two separate
causes, both at this layer:

  * `packaging.thumbnail.subject_side` is an assumption ("measured on
    JgvW7oCQxuI only ... if the court's Zoom layout ever flips, this puts the
    wrong person in the hero slot, and nothing downstream would notice"). On this
    docket the judge's tile is the LEFT one, so the builder was handed Judge
    Boyd's tile and asked to isolate a defendant in it.
  * That defendant is not in custody, so he wears no jail scrubs - the signal
    the Q3 builder isolates him by. The refusal is correct; ending the run over
    it is not, because the single-plate construction already exists for exactly
    this "no usable cut-out" case.
"""
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from boydclips import pipeline, render, thumbnail  # noqa: E402
from boydclips.config import Config  # noqa: E402


TILES = ("crop=612:338:18:190", "crop=620:338:644:190")


def _fake_identity(row, score, threshold=0.363):
    module = SimpleNamespace(
        COSINE_SAME=threshold,
        find_judge=lambda bgr: (row, score),
    )
    return module


def _fake_cv2():
    return SimpleNamespace(imread=lambda path: "bgr")


@pytest.fixture
def frame(tmp_path):
    path = tmp_path / "frame.png"
    Image.new("RGB", (1280, 720), "grey").save(path)
    return path


def test_identity_decides_the_judge_tile_and_says_so(monkeypatch, frame):
    """Boyd's face at x=300 is in the LEFT tile, whatever the config assumes."""
    monkeypatch.setitem(sys.modules, "cv2", _fake_cv2())
    monkeypatch.setitem(sys.modules, "identity", _fake_identity([300.0, 251.0, 109.0, 141.0], 0.57))

    side, source = thumbnail._judge_tile_side(frame, TILES, {"subject_side": "right"})

    assert side == "left"
    assert "identity" in source and "0.57" in source


def test_unrecognised_frame_falls_back_to_the_config_and_is_marked_unverified(monkeypatch, frame):
    monkeypatch.setitem(sys.modules, "cv2", _fake_cv2())
    monkeypatch.setitem(sys.modules, "identity", _fake_identity([300.0, 251.0, 109.0, 141.0], 0.11))

    side, source = thumbnail._judge_tile_side(frame, TILES, {"subject_side": "right"})

    assert side == "right"
    assert "unverified" in source


def test_missing_identity_stack_is_not_a_gate(monkeypatch, frame):
    """No cv2/identity installed must leave the old behaviour, not crash."""
    monkeypatch.setitem(sys.modules, "cv2", None)

    side, source = thumbnail._judge_tile_side(frame, TILES, {"subject_side": "left"})

    assert side == "left"
    assert "unverified" in source


def _q3_cmd(out: Path) -> list[str]:
    return [sys.executable, str(thumbnail.Q3_BUILDER), "--video", "v.mp4",
            "--judge-t", "1.00", "--judge-crop", "612:338:18:190",
            "--plate-t", "1.00", "--plate-crop", "620:338:644:190",
            "--white", "WHITE", "--yellow", "YELLOW", "--out", str(out)]


def test_q3_refusal_ships_the_single_plate_construction(monkeypatch, frame, tmp_path):
    """A correct refusal to isolate the defendant must not kill a rendered run."""
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if str(command[1]).endswith("thumb_Q3_detail.py"):
            return subprocess.CompletedProcess(
                command, 1, stdout="  defendant: no scrubs found\n",
                stderr="cannot identify the defendant - pick another frame\n",
            )
        # make_thumbnail.py takes the output path positionally: frame, out.
        out = Path(command[3])
        Image.new("RGB", (1280, 720), "blue").save(out)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(thumbnail, "subprocess", SimpleNamespace(run=run))
    monkeypatch.setattr(thumbnail.render, "detect_tile_crops", lambda source: TILES)
    monkeypatch.setattr(thumbnail, "_sharpest_frame", lambda *a, **kw: frame)
    monkeypatch.setattr(thumbnail, "_judge_tile_side", lambda *a, **kw: ("left", "identity, cosine 0.57"))

    out = tmp_path / "thumbnail_quote.jpg"
    assert thumbnail.build(Path("source.mp4"), 1.0, "WHITE", "YELLOW", out, {}) == out

    assert len(calls) == 2
    assert str(calls[0][1]).endswith("thumb_Q3_detail.py")
    assert str(calls[1][1]).endswith("make_thumbnail.py")
    # The Q3 call got the JUDGE on the left crop this time.
    assert calls[0][calls[0].index("--judge-crop") + 1] == "612:338:18:190"
    assert calls[0][calls[0].index("--plate-crop") + 1] == "620:338:644:190"

    record = json.loads((tmp_path / "thumbnail_quote.jpg.construction.json").read_text(encoding="utf-8"))
    assert record["construction"] == "single_plate"
    assert record["subject_side"] == "left"
    assert "cannot identify the defendant" in record["fallback_reason"]


def test_q3_failures_that_are_not_a_refusal_still_raise(monkeypatch, frame, tmp_path):
    def run(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="ffmpeg: no such filter\n")

    monkeypatch.setattr(thumbnail, "subprocess", SimpleNamespace(run=run))
    monkeypatch.setattr(thumbnail.render, "detect_tile_crops", lambda source: TILES)
    monkeypatch.setattr(thumbnail, "_sharpest_frame", lambda *a, **kw: frame)
    monkeypatch.setattr(thumbnail, "_judge_tile_side", lambda *a, **kw: ("right", "config subject_side=right (unverified)"))

    with pytest.raises(RuntimeError, match="no such filter"):
        thumbnail.build(Path("source.mp4"), 1.0, "WHITE", "YELLOW", tmp_path / "out.jpg", {})


def test_a_failed_builder_reports_both_streams(monkeypatch, tmp_path):
    """The 2026-09-16 diagnosis cost an hour because stdout was dropped."""
    def run(command, **kwargs):
        return subprocess.CompletedProcess(
            command, 1,
            stdout="  judge tile (620, 338) @ src 271.0\n  defendant: no scrubs found\n",
            stderr="cannot identify the defendant - pick another frame\n",
        )

    monkeypatch.setattr(thumbnail, "subprocess", SimpleNamespace(run=run))

    with pytest.raises(RuntimeError) as raised:
        thumbnail._run_builder(["python", str(thumbnail.Q3_BUILDER)], tmp_path / "out.jpg")

    message = str(raised.value)
    assert "defendant: no scrubs found" in message
    assert "cannot identify the defendant" in message


def test_legacy_thumbnail_carries_the_construction_into_the_result(tmp_path, monkeypatch):
    target = tmp_path / "thumbnail_quote.jpg"

    def build(source, at, white, yellow, out, cfg):
        Image.new("RGB", (1280, 720), "blue").save(out)
        out.with_name(out.name + ".construction.json").write_text(
            json.dumps({"construction": "q3", "subject_side": "left",
                        "side_source": "identity, cosine 0.57"}),
            encoding="utf-8",
        )

    monkeypatch.setattr(pipeline.thumbnail, "build", build)
    pipe = pipeline.Pipeline.__new__(pipeline.Pipeline)
    pipe.cfg = Config({})
    result = pipe._produce_thumbnail(
        tmp_path / "source.mp4", 0, {"hook_start_s": 2},
        {"thumbnail_quote": "REAL WORDS", "thumbnail_quote_yellow": "WORDS"}, tmp_path,
    )

    assert result["status"] == "candidate"
    assert result["construction"] == "q3"
    assert result["subject_side"] == "left"
    assert (tmp_path / "thumbnail_quote.jpg.construction.json").is_file()


sys.path.insert(0, str(ROOT / "scripts"))
import thumb_Q3_detail as q3  # noqa: E402


def test_q3_cache_key_cannot_be_shared_by_two_different_frames():
    """The cache was keyed by preset tag and whole second only, and every
    unattended call uses the same tag - so two cases whose hook landed on the
    same second shared each other's tiles and cut-outs."""
    this_case = q3._cache_key("carthief", Path("dAKO7myCd-g_8929_8905-9492.mp4"),
                              "620:338:644:190", 271.0)
    other_case = q3._cache_key("carthief", Path("oL6lV6gCyOc_736_100-900.mp4"),
                               "620:338:644:190", 271.0)
    other_crop = q3._cache_key("carthief", Path("dAKO7myCd-g_8929_8905-9492.mp4"),
                               "612:338:18:190", 271.0)
    later_frame = q3._cache_key("carthief", Path("dAKO7myCd-g_8929_8905-9492.mp4"),
                                "620:338:644:190", 271.4)

    assert len({this_case, other_case, other_crop, later_frame}) == 4
    assert this_case == q3._cache_key("carthief", Path("dAKO7myCd-g_8929_8905-9492.mp4"),
                                      "620:338:644:190", 271.0)


def test_deep_scan_does_not_offer_a_second_row_for_a_rendered_hearing(tmp_path, monkeypatch, capsys):
    """The candidate list is what handed dAKO7myCd-g:8929 to the renderer."""
    sys.path.insert(0, str(ROOT / "tools"))
    import deep_scan
    from boydclips.state import Store

    db = tmp_path / "state" / "pipeline.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    store = Store(db)
    store.add_docket("dAKO7myCd-g", "docket", "2024-03-07", 10800)
    rendered = store.save_case(
        "dAKO7myCd-g",
        {"eligible": True, "start_s": 8340.0, "end_s": 9465.0, "shortable": True,
         "cause_number": "2023 CR 10327", "total_score": 94.0,
         "safety": {"safety_pass": True}, "proceeding_type": "sentencing",
         "defendant_name": "Andrew Garcia"},
        1,
    )
    store.save_clip(rendered, "longform", tmp_path / "l.mp4", 1164, "t", "", "v")
    store.save_case(
        "dAKO7myCd-g",
        {"eligible": True, "start_s": 8929.0, "end_s": 9469.0, "shortable": True,
         "cause_number": "unknown", "total_score": 91.0,
         "safety": {"safety_pass": True}, "proceeding_type": "sentencing",
         "defendant_name": "unknown"},
        2,
    )
    store.save_case(
        "dAKO7myCd-g",
        {"eligible": True, "start_s": 2000.0, "end_s": 2400.0, "shortable": True,
         "cause_number": "2024 CR 9", "total_score": 85.0,
         "safety": {"safety_pass": True}, "proceeding_type": "plea",
         "defendant_name": "Someone Else"},
        3,
    )
    store.close()

    monkeypatch.setattr(deep_scan, "DB", db)
    assert deep_scan.candidates() == 0

    out = capsys.readouterr().out
    assert "dAKO7myCd-g:2000" in out           # a genuinely unused case is still offered
    assert "dAKO7myCd-g:8929" not in out       # the duplicate row is not
