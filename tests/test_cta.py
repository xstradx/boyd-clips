# -*- coding: utf-8 -*-
"""The "FULL VIDEO OUT NOW" call to action (src/boydclips/cta.py): placement,
timing, geometry, motion envelope and the ffmpeg fragments. No ffmpeg run."""
from __future__ import annotations

from boydclips import cta, layout

CAP = layout.Box(60.0, 894.2, 960.0, 131.5, "caption", True)
WM = layout.Box(923.0, 38.0, 119.0, 47.1, "watermark", True)


def _comp(fx: float = 0.39, fy: float = 0.128, face_w: float | None = 0.089, face_h: float | None = 0.205,
          zoom: float = 1.0) -> dict:
    """A Garcia-shaped composition: the defendant small at the lectern in the
    bottom slot. `fx`/`fy` move the face; None face_w/face_h = no detector."""
    return {
        "divider_y": 960, "punch_zoom": 1.08,
        "anchors": {"top": {"fx": 0.57, "fy": 0.41, "face_w": 0.18, "face_h": 0.43, "source": "yunet"},
                    "bottom": {"fx": fx, "fy": fy, "face_w": face_w, "face_h": face_h,
                               "source": "yunet faces" if face_w else "geometric fallback (no face detected)"}},
        "base": {"top": {"crop": "crop=380:338:180:190", "zoom": 1.0, "subject_x": 539.4, "subject_y": 394.0},
                 "bottom": {"crop": "crop=380:338:698:190", "zoom": zoom, "subject_x": fx * 1080, "subject_y": fy * 960}},
        "segments": [],
    }


def test_defaults_merge_deep_and_keep_unknown_keys():
    c = cta.cfg_with_defaults({"arrow": {"stroke_px": 9}, "sound": {"enabled": False}, "extra": 1})
    assert c["arrow"]["stroke_px"] == 9
    assert c["arrow"]["head_len_px"] == cta.DEFAULTS["arrow"]["head_len_px"]   # untouched sibling
    assert c["sound"]["enabled"] is False and c["sound"]["relative_db"] == -20.0
    assert c["extra"] == 1
    assert cta.enabled({"enabled": False}) is False and cta.enabled(None) is True


def test_easings_hit_the_ends_and_are_not_linear():
    for f in (cta.EASE_OUT, cta.EASE_DRAW, cta.EASE_SMOOTH):
        ys = [f(i / 50) for i in range(51)]
        assert ys[0] == 0.0 and ys[-1] == 1.0
        assert all(b >= a - 1e-9 for a, b in zip(ys, ys[1:]))
    assert cta.EASE_OUT(0.25) > 0.6 and cta.EASE_DRAW(0.25) < 0.25
    # the head's ease overshoots past 1 and settles back to exactly 1
    back = [cta.EASE_BACK(i / 50) for i in range(51)]
    assert max(back) > 1.03 and back[-1] == 1.0 and back[0] == 0.0


def test_wrap_is_balanced():
    assert cta.wrap_lines("FULL VIDEO OUT NOW", 2) == ["FULL VIDEO", "OUT NOW"]
    assert cta.wrap_lines("FULL VIDEO OUT NOW", 1) == ["FULL VIDEO OUT NOW"]
    assert cta.wrap_lines("WATCH", 2) == ["WATCH"]


def test_block_is_phone_readable_and_targets_related_row():
    c = cta.cfg_with_defaults({})
    blk = cta.measure_block(c, ["FULL VIDEO", "OUT NOW"], 44, 0.08 * 44)
    assert 190 < blk["w"] < 310 and 65 < blk["h"] < 110
    p = cta.plan_cta({}, 54.915, _comp(), CAP, WM, None, 30)
    assert " ".join(p.lines) == "FULL VIDEO OUT NOW"
    assert p.arrow_target == (0.36 * 1080, 0.855 * 1920)


def test_auto_timing_is_end_anchored_and_holds_into_the_last_frame():
    p = cta.plan_cta({}, 54.915, _comp(), CAP, WM, None, 30)
    assert p.fade is False and abs(p.end_s - 54.915) < 1e-6
    c = cta.cfg_with_defaults({})
    assert abs((p.end_s - p.start_s) - cta.core_duration(c)) < 1.0 / 30 + 1e-6
    assert abs(p.start_s * 30 - round(p.start_s * 30)) < 1e-6         # frame-snapped
    tl = p.timeline
    assert (tl["text_in"] < tl["arrow_draw_start"] < tl["arrow_drawn"] < tl["head_settled"]
            < tl["nudge_start"] < tl["nudge_end"] <= tl["hold_until"] == tl["end"])


def test_explicit_early_start_fades_out_while_the_video_continues():
    p = cta.plan_cta({"start_s": 40.0}, 54.915, _comp(), CAP, WM, None, 30)
    assert p.fade is True and p.start_s == 40.0
    assert p.timeline["hold_until"] < p.end_s < 54.915
    c = cta.cfg_with_defaults({"start_s": 40.0})
    assert cta._envelope(p.timeline["hold_until"] - 0.01, p, c)["alpha"] == 1.0
    assert cta._envelope(p.end_s, p, c)["alpha"] == 0.0


def test_envelope_text_then_stroke_then_head_overshoot_then_one_nudge():
    p = cta.plan_cta({}, 50.0, _comp(), CAP, WM, None, 30)
    c = cta.cfg_with_defaults({})
    tl = p.timeline
    e0 = cta._envelope(tl["text_in"] + 0.05, p, c)
    assert 0.0 < e0["text"] < 1.0 and e0["draw"] == 0.0 and e0["head"] == 0.0
    mid = cta._envelope((tl["arrow_draw_start"] + tl["arrow_drawn"]) / 2, p, c)
    assert 0.2 < mid["draw"] < 0.8 and mid["head"] == 0.0               # no head until the stroke is nearly there
    heads = [cta._envelope(tl["arrow_drawn"] + k * 0.01, p, c)["head"] for k in range(0, 40)]
    assert max(heads) > 1.02 and abs(heads[-1] - 1.0) < 1e-9             # overshoots, then settles at 1
    nudges = [cta._envelope(tl["nudge_start"] + k * 0.02, p, c)["nudge"] for k in range(0, 30)]
    peaks = sum(1 for a, b, d in zip(nudges, nudges[1:], nudges[2:]) if b > a and b >= d and b > 0.5)
    assert peaks == 1                                                    # exactly one push, then still
    assert cta._envelope(tl["nudge_end"] + 0.3, p, c)["nudge"] == 0.0
    assert cta._envelope(tl["head_settled"] - 0.001, p, c)["nudge"] == 0.0   # nudge waits for the head


def test_side_left_by_default_on_the_lectern_composition():
    p = cta.plan_cta({}, 54.9, _comp(), CAP, WM, None, 30)
    assert p.side == "left" and p.text_box.x == 56.0
    assert p.box.y > CAP.y2                                              # never in the caption rail
    assert not p.scores["left"]["veto"]
    assert p.lines == ["FULL VIDEO", "OUT NOW"]


def test_face_in_the_lower_left_vetoes_left_and_moves_the_cta_right():
    comp = _comp(fx=0.14, fy=0.62, face_w=0.20, face_h=0.55)
    p = cta.plan_cta({}, 54.9, comp, CAP, WM, None, 30)
    assert p.scores["left"]["veto"] and "face" in p.scores["left"]["veto"][0]
    assert p.side == "right"
    assert p.box.x2 <= 0.815 * 1080 + 1e-6                               # clear of YouTube's action column


def test_forced_side_is_honoured_and_noted():
    comp = _comp(fx=0.14, fy=0.62, face_w=0.20, face_h=0.55)
    p = cta.plan_cta({"side": "left"}, 54.9, comp, CAP, WM, None, 30)
    assert p.side == "left" and any("forced side" in n for n in p.notes)


def test_no_measured_face_falls_back_to_busyness_and_says_so():
    import numpy as np
    comp = _comp(face_w=None, face_h=None)
    busy_left = np.zeros((1920, 1080, 3), dtype=np.uint8)
    busy_left[1300:1700, 0:540] = (np.indices((400, 540))[1] % 2 * 255)[..., None]   # stripes = busy
    p = cta.plan_cta({}, 54.9, comp, CAP, WM, [busy_left], 30)
    assert any("no measured face" in n for n in p.notes)
    assert p.scores["left"]["busyness"] > p.scores["right"]["busyness"]
    assert p.side == "right"


def test_cta_box_enters_the_overlay_layout_collision_check():
    p = cta.plan_cta({}, 54.9, _comp(), CAP, WM, None, 30)
    style = {"font_size": 96, "max_lines": 1, "rail_y": 960}
    ok = layout.overlay_layout(style, {"watermark_margin_frac": 0.035}, (119.0, 47.1), extra=[p.box])
    assert ok["overlay_collision"] == "PASS"
    high = layout.Box(p.box.x, 900.0, p.box.w, p.box.h, "cta", True)
    bad = layout.overlay_layout(style, {"watermark_margin_frac": 0.035}, (119.0, 47.1), extra=[high])
    assert bad["overlay_collision"] == "FAIL" and ("caption", "cta") in bad["collisions"]


def test_stroke_leaves_the_side_of_the_block_and_points_down():
    c = cta.cfg_with_defaults({})
    c["arrow"]["target"] = None
    tbox = layout.Box(56.0, 1517.0, 160.0, 56.0, "cta_text", True)
    pts = cta.arrow_path(tbox, "left", c, n=100)
    sx, sy = pts[0]
    ex, ey = pts[-1]
    assert abs(sx - (tbox.x2 + 18.0)) < 1e-6 and abs(sy - (tbox.y + 28.0)) < 1e-6   # beside the block, mid-height
    assert ex > sx and ey > sy + 60                                     # a little sideways, then well below
    assert ex - sx < 0.5 * (ey - sy)                                    # compact: mostly a drop
    # leaves horizontally, arrives vertically
    dx0, dy0 = pts[3][0] - pts[0][0], pts[3][1] - pts[0][1]
    dx1, dy1 = pts[-1][0] - pts[-3][0], pts[-1][1] - pts[-3][1]
    assert dx0 > 3 * abs(dy0) and dy1 > 6 * abs(dx1)
    # the right side is the mirror, on the block's left
    m = cta.arrow_path(tbox, "right", c, n=100)
    assert m[0][0] < tbox.x and m[-1][0] < m[0][0]
    # an absolute target wins when configured
    t = cta.arrow_path(tbox, "left", cta.cfg_with_defaults({"arrow": {"target": [0.2, 0.85]}}), n=10)
    assert abs(t[-1][0] - 216.0) < 1e-6 and abs(t[-1][1] - 1632.0) < 1e-6


def test_ffmpeg_chain_labels_and_inputs():
    rec = {"frames": {"pattern": "C:/x/cta_%04d.png", "fps": 30}, "start_s": 52.7667, "end_s": 54.915,
           "sound": {"file": "C:/x/cta_sfx.wav", "gain_db": -27.5}}
    inputs, vf, af = cta.ffmpeg_chain(rec, 2, "vwm", "vcta", "ac", "acta")
    assert inputs[:5] == ["-framerate", "30", "-start_number", "0", "-i"] and inputs[5].endswith("cta_%04d.png")
    assert inputs[-2:] == ["-i", "C:/x/cta_sfx.wav"]
    assert vf.startswith("[2:v]format=rgba,setpts=PTS+52.7667/TB[ctaov];[vwm][ctaov]overlay=")
    assert "format=yuv444" in vf and vf.endswith("[vcta]")
    assert af.startswith("[3:a]adelay=52767:all=1,volume=-27.50dB[ctasfx];[ac][ctasfx]amix=") and af.endswith("[acta]")
    inputs2, _vf2, af2 = cta.ffmpeg_chain({**rec, "sound": None}, 1, "a", "b", "c", "d")
    assert af2 is None and len(inputs2) == 6


def test_review_frames_cover_before_enter_middraw_hold():
    p = cta.plan_cta({}, 54.915, _comp(), CAP, WM, None, 30)
    labels = [l for l, _ in cta.review_frame_times(p)]
    assert labels == ["before_cta", "cta_enter", "cta_arrow_mid_draw", "cta_hold"]
    ts = [t for _, t in cta.review_frame_times(p)]
    assert ts[0] < p.start_s < ts[1] < ts[2] < ts[3] < p.end_s


def _close_up(fx: float, face_h: float = 0.4152) -> dict:
    """The 2026-09-13 shape that broke the stroke: the judge's webcam fills
    the bottom slot, so her face box covers the lower-left where the CTA and
    its stroke live."""
    comp = _comp(fx=fx, fy=0.617, face_w=0.1779, face_h=face_h)
    comp["segments"] = [{"index": 0, "punch": "bottom", "punch_scale": 1.08}]
    return comp


def test_stroke_never_drawn_over_a_close_up_subject():
    """IDGfe1rPUQo:6130, 2026-09-13. The fixed target (0.36, 0.855) sat on the
    judge's cheek: her face box starts at x 386 (0.1779 * 1080 * 1.6 grown,
    punched 1.08) and the stroke ended at 388.8. A stub of a stroke is not a
    fix either, so an 8.6 px lane drops it entirely — the text is what has to
    stay readable, and it is still clear of her face."""
    p = cta.plan_cta({}, 38.9, _close_up(0.50), CAP, WM, None, 30)
    assert p.side == "left"
    assert p.arrow_target is None and p.arrow_start is None
    assert any("stroke omitted" in n for n in p.notes)
    assert not p.text_box.intersects(p.scores["face_box"] and _box(p.scores["face_box"]))
    assert p.box.as_dict() == p.text_box.as_dict()          # nothing invisible in the overlay box
    # bad control: the same stroke is still drawn when the subject is small and
    # high in the slot (the lectern composition above)
    wide = cta.plan_cta({}, 38.9, _comp(), CAP, WM, None, 30)
    assert wide.arrow_target == (0.36 * 1080, 0.855 * 1920)
    assert not any("stroke omitted" in n for n in wide.notes)


def test_stroke_is_clamped_into_a_lane_that_is_wide_enough():
    p = cta.plan_cta({}, 38.9, _close_up(0.52), CAP, WM, None, 30)
    fence = p.scores["face_box"]["x"] - float(cta.DEFAULTS["arrow"]["clearance_px"])
    assert p.arrow_target is not None
    assert abs(p.arrow_target[0] - fence) < 0.6                # pulled back to the clear lane
    assert p.arrow_target[1] == 0.855 * 1920                   # the drop is untouched
    assert any("clamped" in n for n in p.notes)
    assert p.arrow_override == {"target": [p.arrow_override["target"][0], 0.855]}
    # and the recorded path really ends there, not at the configured target
    c = cta.cfg_with_defaults({})
    c["arrow"] = {**c["arrow"], **p.arrow_override}
    assert abs(cta.arrow_path(p.text_box, "left", c, n=64)[-1][0] - fence) < 1.0


def test_punch_grows_the_face_box_the_stroke_has_to_avoid():
    plain = cta.plan_cta({}, 38.9, _comp(fx=0.50, fy=0.617, face_w=0.1779, face_h=0.4152), CAP, WM, None, 30)
    punched = cta.plan_cta({}, 38.9, _close_up(0.50), CAP, WM, None, 30)
    assert punched.scores["face_punch"] == 1.08 and plain.scores["face_punch"] == 1.0
    assert punched.scores["face_box"]["w"] > plain.scores["face_box"]["w"] * 1.07


def _box(d: dict) -> layout.Box:
    return layout.Box(d["x"], d["y"], d["w"], d["h"], d.get("name", ""), d.get("critical", True))
