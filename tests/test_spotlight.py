# -*- coding: utf-8 -*-
"""The spotlight treatment (src/boydclips/spotlight.py): the drawn ring, the
incoming arrow, cue levelling and the overlay/mix graph. No ffmpeg run for the
geometry tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from boydclips import spotlight


def test_ring_and_arrow_validate_their_own_geometry():
    clock = spotlight.RingCue(box=(382, 142, 701, 550), start_s=0.40, draw_s=0.55, hold_until_s=5.20)
    arrow = spotlight.ArrowCue(tail=(56, 1705), tip=(330, 1455), start_s=5.61, rise_s=0.32, hold_until_s=9.31)
    spec = spotlight.SpotlightSpec(ring=clock, arrow=arrow)
    spec.validate()
    assert spec.span() == (0.40, 9.31 + 0.25)

    with pytest.raises(ValueError):
        spotlight.RingCue(box=(0, 0, 5000, 500), start_s=0.0).validate()
    with pytest.raises(ValueError):
        spotlight.RingCue(box=(10, 10, 500, 500), start_s=0.0, draw_s=1.0, hold_until_s=0.5).validate()
    with pytest.raises(ValueError):                     # head longer than the arrow
        spotlight.ArrowCue(tail=(100, 100), tip=(120, 110), start_s=0.0, head_len_px=400).validate()
    with pytest.raises(ValueError):                     # nothing to draw
        spotlight.SpotlightSpec().validate()


def test_spec_round_trips_through_json():
    spec = spotlight.SpotlightSpec(
        ring=spotlight.RingCue(box=(382, 142, 701, 550), start_s=0.4, hold_until_s=5.2),
        arrow=spotlight.ArrowCue(tail=(56, 1705), tip=(330, 1455), start_s=5.61, hold_until_s=9.31),
        sounds=[spotlight.CueSound(Path(__file__), 0.4, -9.0)],
    )
    again = spotlight.SpotlightSpec.from_json(spec.to_json())
    assert again.ring.box == spec.ring.box and again.arrow.tip == spec.arrow.tip
    assert again.sounds[0].at_s == 0.4 and again.sounds[0].peak_dbfs == -9.0


def test_frames_cover_the_whole_span_and_stay_inside_the_canvas(tmp_path):
    spec = spotlight.SpotlightSpec(
        ring=spotlight.RingCue(box=(382, 142, 701, 550), start_s=0.4, draw_s=0.3, hold_until_s=1.4),
        arrow=spotlight.ArrowCue(tail=(56, 1705), tip=(330, 1455), start_s=1.5, rise_s=0.2, hold_until_s=2.5),
    )
    rec = spotlight.render_overlay_frames(spec, tmp_path, fps=10, ss=1)
    span = spec.span()
    assert rec["frames"] == int(round((span[1] - span[0]) * 10)) + 1
    x, y, w, h = rec["region"]
    assert x >= 0 and y >= 0 and x + w <= spotlight.CANVAS_W and y + h <= spotlight.CANVAS_H
    assert w > 200 and h > 500                                 # both cues are inside the region
    assert len(list(tmp_path.glob("spot_*.png"))) == rec["frames"]


def test_audio_mix_keeps_the_dialogue_first():
    """Regression: keying the mix to a 0.37 s cue truncated the audio."""
    graph = spotlight.audio_mix_filter(2)
    assert graph.startswith("[0:a][s0][s1]amix=")
    assert "duration=first" in graph and graph.endswith("[aout]")
