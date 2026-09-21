# -*- coding: utf-8 -*-
"""thumbnail.mode: direct_gen - the orchestration around the model call,
tested with a fake runner (no codex, no images generated)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))

import thumb_direct as TD  # noqa: E402

FONT = ROOT / "assets" / "fonts" / "Anton-Regular.ttf"


def _synthetic(path: Path, size=(1672, 941), text="MY PHONE GOT STOLEN.", text_y=0.78, margin_ok=True, seed=0):
    """A stand-in for a generated thumbnail: dark room, warm blob subject,
    one bold caps line. No real faces (face gates are tested separately)."""
    rng = np.random.default_rng(seed)
    w, h = size
    arr = rng.integers(30, 90, (h, w, 3), dtype=np.uint8)
    im = Image.fromarray(arr, "RGB")
    d = ImageDraw.Draw(im)
    d.ellipse((w * 0.1, h * 0.15, w * 0.45, h * 0.9), fill=(210, 160, 120))
    font = ImageFont.truetype(str(FONT), int(h * 0.14)) if FONT.exists() else ImageFont.load_default()
    if text:
        tw = d.textbbox((0, 0), text, font=font)[2]
        x = (w - tw) // 2 if margin_ok else -8
        d.text((x, int(h * text_y)), text, font=font, fill=(255, 255, 255), stroke_width=8, stroke_fill=(0, 0, 0))
    im.save(path)
    return path


def test_normalize_to_1280_handles_image_gen_size(tmp_path):
    src = _synthetic(tmp_path / "gen.png", (1672, 941))
    out = tmp_path / "final.jpg"
    info = TD.normalize_to_1280(src, out)
    assert Image.open(out).size == (1280, 720)
    assert out.stat().st_size <= 2_000_000 and info["source_size"].startswith("1672x941")
    src2 = _synthetic(tmp_path / "wide.png", (2000, 900))
    TD.normalize_to_1280(src2, tmp_path / "final2.jpg")
    assert Image.open(tmp_path / "final2.jpg").size == (1280, 720)


def test_text_geometry_flags_margin_and_size(tmp_path):
    import cv2
    ok = _synthetic(tmp_path / "ok.png")
    g = TD.text_geometry(cv2.imread(str(ok)), TD.DEFAULTS)
    assert g["found"] and not g["touches_margin"] and g["height_frac"] >= 0.09
    edge = _synthetic(tmp_path / "edge.png", margin_ok=False)
    g2 = TD.text_geometry(cv2.imread(str(edge)), TD.DEFAULTS)
    assert g2["found"] and g2["touches_margin"]


def test_text_face_collision_uses_clusters_without_filling_blank_space():
    face = [{"box": [20, 20, 100, 100]}]
    spaced = {"bbox": [0, 0, 200, 200], "boxes": [[0, 0, 20, 20], [130, 130, 200, 200]]}
    assert TD.text_face_overlap(spaced, face) == 0
    actual_collision = {**spaced, "boxes": spaced['boxes'] + [[20, 20, 120, 70]]}
    assert TD.text_face_overlap(actual_collision, face) == .5


def test_text_grounded_rules():
    brief = {"allowed_lines": ["My phone got stolen.", "Why didn't you go to the library?"],
             "facts": ["$55 toward his fees in two years", "$6,399.22 owed"], "forbidden_tokens": ["flores", "waris"]}
    trans = "in two years you've only paid $55 my phone got stolen why didn't you go to the library".split()
    ok, why = TD.text_grounded('"MY PHONE GOT STOLEN."', brief, trans, TD.DEFAULTS)
    assert ok and "verbatim" in why
    ok, why = TD.text_grounded("PAID $55 IN 2 YEARS", brief, trans, TD.DEFAULTS)
    assert ok
    ok, why = TD.text_grounded("PAID $5,000 IN 2 YEARS", brief, trans, TD.DEFAULTS)
    assert not ok and "$5,000" in why
    ok, why = TD.text_grounded("FLORES LIED TO THE JUDGE", brief, trans, TD.DEFAULTS)
    assert not ok and "name" in why
    ok, why = TD.text_grounded("HE STOLE A SPACESHIP FROM NASA", brief, trans, TD.DEFAULTS)
    assert not ok
    ok, why = TD.text_grounded("MY PHONE GOT STOLEN AND THEN THE DOG ATE MY HOMEWORK", brief, trans, TD.DEFAULTS)
    assert not ok and "words" in why


def test_generated_copy_cannot_drop_negation_even_if_remaining_words_are_grounded(tmp_path, monkeypatch):
    source = _synthetic(tmp_path / "changed.png", text="YOUR BUILDING")
    monkeypatch.setattr(TD, "ocr_words", lambda *a: [("YOUR", 1), ("BUILDING", 1)])
    monkeypatch.setattr(TD, "faces_and_identity", lambda *a, **k: {"faces": [], "refs": []})
    brief = {"allowed_lines": ["NOT YOUR BUILDING"], "facts": [], "forbidden_tokens": [],
             "concept_directions": {"B": {"thumbnail_text": "NOT YOUR BUILDING"}}}
    assert TD.text_grounded("YOUR BUILDING", brief, [], TD.DEFAULTS)[0]
    result = TD.qc_concept(source, "B", {"text": "YOUR BUILDING"}, brief, {}, [], TD.DEFAULTS, tmp_path / "out.jpg")
    checks = {g["gate"]: g["ok"] for g in result["gates"]}
    assert checks["reviewed_copy_unchanged"] is False
    claimed = TD.qc_concept(source, "B", {"text": "NOT YOUR BUILDING"}, brief, {}, [], TD.DEFAULTS, tmp_path / "claimed.jpg")
    checks = {g["gate"]: g["ok"] for g in claimed["gates"]}
    assert checks["reviewed_copy_unchanged"] is True
    assert checks["critical_copy_words_visible"] is False  # generator's self-report is not evidence of NOT


def test_ocr_joined_words_preserve_all_letters_and_negations():
    want=['it','still',"wasn't",'yours']
    assert TD.recovered_copy_words(want,["ITSTILLWASN'TYOURS"]) == {0,1,2,3}
    assert TD.recovered_copy_words(want,['IT','STILL','WAS','YOURS']) == {0,1,3}
    assert TD.recovered_copy_words(['not','your','building'],['YOURBUILDING']) == {1,2}
    assert TD.recovered_copy_words(['20','dollars'],['200DOLLARS']) == set()
    assert TD.recovered_copy_words(['he','stole'],['SHE','STOLE']) == {1}
    assert TD.recovered_copy_words(['20','dispute'],['S20 DISPUTE'],('20',)) == {0,1}
    assert TD.recovered_copy_words(['20','dispute'],['S200 DISPUTE'],('20',)) == {1}
    assert TD.recovered_copy_words(['20','dispute'],['S20 DISPUTE']) == {1}


def test_no_text_allowed_only_when_explicitly_planned(tmp_path, monkeypatch):
    source = _synthetic(tmp_path / "portrait.png", text="")
    monkeypatch.setattr(TD, "ocr_words", lambda *a: [])
    monkeypatch.setattr(TD, "faces_and_identity", lambda *a, **k: {"faces": [
        {"box": [150, 100, 300, 350], "height_frac": .49, "cut_by_frame": False,
         "match": "defendant", "cosine": .9}], "refs": ["defendant"]})
    direction = {"thumbnail_text": "", "direction": {"typography": "No text; title carries the conflict."}}
    brief = {"allowed_lines": [], "facts": [], "forbidden_tokens": [], "concept_directions": {"A": direction}}
    def check(b, reported_text=""):
        return TD.qc_concept(source, "A", {"text": reported_text}, b, {}, [], TD.DEFAULTS, tmp_path / "out.jpg")
    assert check(brief)["ok"]
    assert not check({**brief, "concept_directions": {}})["ok"]
    assert not check(brief, "UNPLANNED CLAIM")["ok"]


def test_brief_never_carries_the_defendant_name():
    c = {"_key": "X", "defendant": "John Q. Sample", "defendant_full": "John Quincy Sample", "white": "\"My phone", "yellow": "got stolen.\"",
         "kicker": "HIS EXCUSE...", "note": "MTR; paid $55 in 2 years", "hearing_date": "2026-05-21"}
    b = TD.build_brief(c)
    assert "sample" in b["forbidden_tokens"] and "john" in b["forbidden_tokens"]
    assert any("phone got stolen" in l.lower() for l in b["allowed_lines"])
    p = TD.build_prompt(b, [("defendant_1", Path("d.png")), ("boyd_1", Path("b.png")), ("room_1", Path("r.png"))], TD.DEFAULTS)
    for fam in ("A. COURT OF JUSTICE", "B. DEFENDANT + JUDGE BOYD", "C. STRONGEST CASE STORY"):
        assert fam in p
    assert "NEVER more than 9 generated images" in p and "at most 2 retries" in p
    assert "explicit BOYD / DEFENDANT attribution" in p
    assert "Do not make Boyd blue, pale, plastic" in p
    assert "Never import a person, uniform, object, quote, or allegation" in p
    assert "Sample" not in p and "John" not in p


def test_run_case_with_fake_runner_retries_and_writes_manifest(tmp_path, monkeypatch):
    """Session 1 returns A/B/C; B's text touches the frame edge -> our QC
    rejects it -> one follow-up session regenerates B -> three finals,
    sidecars, sheet, manifest with retry counts and budget accounting."""
    work, out = tmp_path / "work", tmp_path / "out"
    work.mkdir()
    calls = []

    def fake_runner(prompt, attachments, workdir, cfg, extra_args=None):
        calls.append(prompt[:40])
        if len(calls) == 1:
            _synthetic(workdir / "concept_A.png", text="MY PHONE GOT STOLEN.", seed=1)
            _synthetic(workdir / "concept_B.png", text="NO EXCUSES, JUDGE.", margin_ok=False, seed=2)
            _synthetic(workdir / "concept_C.png", text="GO TO THE LIBRARY?", seed=3, text_y=0.05)
            return {"concepts": [
                {"family": "A", "file": "concept_A.png", "text": "MY PHONE GOT STOLEN.", "prop": None, "description": "defendant alone", "attempts": 1, "self_score": 8, "rejected_files": []},
                {"family": "B", "file": "concept_B.png", "text": "NO EXCUSES, JUDGE.", "prop": None, "description": "two shot", "attempts": 2, "self_score": 7, "rejected_files": ["x.png"]},
                {"family": "C", "file": "concept_C.png", "text": "GO TO THE LIBRARY?", "prop": "library card", "description": "prop", "attempts": 1, "self_score": 9, "rejected_files": []},
            ], "images_generated_total": 4, "notes": "ok", "_log": "l1", "_exit": 0}
        assert "REGENERATE ONLY concept B" in prompt
        _synthetic(workdir / "concept_B.png", text="NO EXCUSES, JUDGE.", seed=4)
        return {"concepts": [{"family": "B", "file": "concept_B.png", "text": "NO EXCUSES, JUDGE.", "prop": None, "description": "two shot v2", "attempts": 1, "self_score": 8, "rejected_files": []}],
                "images_generated_total": 1, "notes": "fixed", "_log": "l2", "_exit": 0}

    # no real faces in the synthetic images: stand in for the face/identity gates per family
    def fake_faces(bgr, refs, cfg, family=None):
        faces = [{"box": [100, 100, 400, 400], "height_frac": 0.55, "cut_by_frame": False, "match": "defendant", "cosine": 0.9}]
        if family in ("B", "C"):
            faces.append({"box": [800, 100, 400, 400], "height_frac": 0.5, "cut_by_frame": False, "match": "boyd", "cosine": 0.85})
        return {"faces": faces, "refs": ["defendant", "boyd"]}
    monkeypatch.setattr(TD, "faces_and_identity", fake_faces)
    monkeypatch.setattr(TD, "ocr_words", lambda bgr, width=336: [("MY PHONE GOT STOLEN NO EXCUSES JUDGE WHY DIDN'T YOU GO TO THE LIBRARY", 0.9)])
    monkeypatch.setattr(TD, "load_case", lambda case: {"_key": case, "defendant": "X Y", "white": "\"My phone", "yellow": "got stolen.\"",
                                                       "kicker": "No excuses, Judge.", "note": "Why didn't you go to the library?"})
    monkeypatch.setattr(TD, "transcript_words", lambda c: "my phone got stolen no excuses judge why didn't you go to the library".split())
    monkeypatch.setattr(TD, "gather_assets", lambda c, w=None: TD.Assets(defendant=[tmp_path / "d.png"], boyd=[tmp_path / "b.png"], rooms=[tmp_path / "r.png"], refs={"defendant": tmp_path / "d.png"}))
    for n in ("d", "b", "r"):
        _synthetic(tmp_path / f"{n}.png", (400, 400), text="")
    # synthetic images differ only by seed; the feed-size variety floor is measured on real images elsewhere
    m = TD.run_case("TESTCASE", out, work, None, runner=fake_runner, cfg={"budget": 9, "retries": 2, "min_variant_diff": 1.0})
    assert len(calls) == 2
    assert m["model_calls_used"] == 2
    assert set(m["finals"]) == {"A", "B", "C"} and m["control_present"] and m["complete"]
    assert m["retries_used"] == {"A": 0, "B": 1, "C": 0} and m["images_generated_total"] == 5
    for fam in "ABC":
        assert Image.open(out / f"TESTCASE_{fam}.jpg").size == (1280, 720)
        side = json.loads((out / f"TESTCASE_{fam}.json").read_text(encoding="utf-8"))
        assert side["family"] == fam and side["qc"]["ok"] and "session" in side and side["text"]
    assert (out / "TESTCASE_contact_sheet.jpg").exists() and (out / "manifest.json").exists()
    assert (out / "rejected" / "TESTCASE_B_r0.jpg").exists()
    assert m["variants"]["ok"]


def test_budget_is_a_hard_cap(tmp_path, monkeypatch):
    work, out = tmp_path / "work", tmp_path / "out"
    work.mkdir()
    n = {"calls": 0}

    def runner(prompt, attachments, workdir, cfg, extra_args=None):
        n["calls"] += 1
        _synthetic(workdir / "concept_A.png", text="MY PHONE GOT STOLEN.", margin_ok=False, seed=n["calls"])   # always at the edge -> always rejected
        return {"concepts": [{"family": "A", "file": "concept_A.png", "text": "MY PHONE GOT STOLEN.", "prop": None, "description": "d", "attempts": 3, "self_score": 6, "rejected_files": []}],
                "images_generated_total": 3, "notes": "", "_log": "l", "_exit": 0}
    monkeypatch.setattr(TD, "faces_and_identity", lambda bgr, refs, cfg, family=None: {"faces": [{"box": [100, 100, 400, 400], "height_frac": 0.55, "cut_by_frame": False, "match": "defendant", "cosine": 0.9}], "refs": ["defendant"]})
    monkeypatch.setattr(TD, "ocr_words", lambda bgr, width=336: [("MY PHONE GOT STOLEN", 0.9)])
    monkeypatch.setattr(TD, "load_case", lambda case: {"_key": case, "white": "My phone", "yellow": "got stolen."})
    monkeypatch.setattr(TD, "transcript_words", lambda c: "my phone got stolen".split())
    _synthetic(tmp_path / "d.png", (400, 400), text="")
    monkeypatch.setattr(TD, "gather_assets", lambda c, w=None: TD.Assets(defendant=[tmp_path / "d.png"], refs={"defendant": tmp_path / "d.png"}))
    m = TD.run_case("CAP", out, work, None, runner=runner, cfg={"budget": 9, "retries": 2})
    # session 1 = 3 images; two retries for A possible (each 3) but the cap of 9 stops after the second retry
    assert n["calls"] == 3 and m["images_generated_total"] == 9
    assert not m["complete"] and "A" not in m["finals"] and not m["control_present"]


def test_resume_repairs_only_failed_concept_and_keeps_spend(tmp_path, monkeypatch):
    """A paused partial set must not launch another three-image initial call."""
    ref = tmp_path / "ref.png"
    Image.new("RGB", (32, 32)).save(ref)
    monkeypatch.setattr(TD, "gather_assets", lambda *a: TD.Assets(defendant=[ref]))
    monkeypatch.setattr(TD, "transcript_words", lambda *a: [])
    monkeypatch.setattr(TD, "variant_diffs", lambda *a: {"pairs": {}, "ok": True})
    calls = []

    def runner(prompt, attachments, work, cfg):
        calls.append(prompt)
        families = "ABC" if len(calls) == 1 else "B"
        for family in families:
            Image.new("RGB", (1280, 720), (len(calls), 20, 30)).save(work / f"concept_{family}.png")
        return {"concepts": [{"family": f, "file": f"concept_{f}.png", "text": "REAL QUOTE"}
                             for f in families], "images_generated_total": len(families)}

    def qc(png, family, reported, brief, refs, transcript, cfg, output):
        Image.open(png).save(output)
        ok = family != "B" or len(calls) > 1
        return {"source": str(png), "ok": ok,
                "gates": [{"gate": "hero_face_size", "ok": ok, "detail": "fixture"}]}

    monkeypatch.setattr(TD, "qc_concept", qc)
    case = {"_key": "RESUME", "white": "REAL", "yellow": "QUOTE"}
    out, work = tmp_path / "out", tmp_path / "work"
    first = TD.run_case("RESUME", out, work, runner=runner, case_dict=case,
                        cfg={"budget": 3, "model_call_budget": 1})
    assert not first["complete"] and len(calls) == 1
    a_before = (out / "RESUME_A.jpg").read_bytes()
    final = TD.run_case("RESUME", out, work, runner=runner, case_dict=case, resume=True,
                        cfg={"budget": 4, "model_call_budget": 2})
    assert final["complete"] and len(calls) == 2
    assert "REGENERATE ONLY concept B" in calls[1]
    assert final["images_generated_total"] == 4 and final["model_calls_used"] == 2
    assert (out / "RESUME_A.jpg").read_bytes() == a_before
    with pytest.raises(ValueError, match="brief changed"):
        TD.run_case("RESUME", out, work, runner=runner, resume=True,
                    case_dict={**case, "yellow": "OTHER"})
    assert len(calls) == 2


def test_interrupted_thumbnail_call_cannot_refund_spend(tmp_path, monkeypatch):
    ref = tmp_path / "ref.png"
    Image.new("RGB", (32, 32)).save(ref)
    monkeypatch.setattr(TD, "gather_assets", lambda *a: TD.Assets(defendant=[ref]))
    monkeypatch.setattr(TD, "transcript_words", lambda *a: [])
    def interrupted(*a):
        raise RuntimeError("interrupted after possible generation")
    kwargs = dict(out_dir=tmp_path / "out", work=tmp_path / "work", runner=interrupted,
                  case_dict={"_key": "INTERRUPTED", "white": "REAL", "yellow": "QUOTE"})
    with pytest.raises(RuntimeError, match="interrupted"):
        TD.run_case("INTERRUPTED", **kwargs)
    saved = json.loads((tmp_path / "out/manifest.json").read_text())
    assert saved["model_calls_used"] == 1 and saved["in_flight"]["images_reserved"] == 9
    with pytest.raises(TD.UsageLimit, match="uncertain spend"):
        TD.run_case("INTERRUPTED", resume=True, **kwargs)


def test_missing_initial_concept_retries_without_attaching_current_directory(tmp_path, monkeypatch):
    work, out = tmp_path / "work", tmp_path / "out"
    work.mkdir()
    calls = []

    def runner(prompt, attachments, workdir, cfg, extra_args=None):
        calls.append([path for _name, path in attachments])
        if len(calls) == 1:
            return {"concepts": [], "images_generated_total": 0, "notes": "", "_log": "l1", "_exit": 0}
        assert all(path.is_file() for path in calls[-1])
        return {"concepts": [], "images_generated_total": 1, "notes": "", "_log": "l2", "_exit": 0}

    monkeypatch.setattr(TD, "load_case", lambda case: {"_key": case, "white": "REAL", "yellow": "WORDS"})
    monkeypatch.setattr(TD, "transcript_words", lambda c: "real words".split())
    _synthetic(tmp_path / "d.png", (400, 400), text="")
    monkeypatch.setattr(
        TD,
        "gather_assets",
        lambda c, w=None: TD.Assets(defendant=[tmp_path / "d.png"], refs={"defendant": tmp_path / "d.png"}),
    )

    TD.run_case("MISSING", out, work, None, runner=runner, cfg={"budget": 3, "retries": 1})

    assert len(calls) == 4


@pytest.mark.skipif(not (ROOT / "models" / "sface.onnx").exists(), reason="SFace model not present")
def test_identity_gate_on_a_real_generated_thumbnail():
    """The probe from 2026-09-06: generated faces vs the Flores source
    crops. Real people, real floor."""
    import cv2
    probe = ROOT / "out" / "review" / "bridge_probe_2026-09-06" / "probe1.png"
    refs = {"defendant": Path(r"D:/Boyd Clips/thumbwork/FLORES/defendant_surgical.png"), "boyd": Path(r"D:/Boyd Clips/thumbwork/FLORES/judge_surgical.png")}
    if not probe.exists() or not all(p.exists() for p in refs.values()):
        pytest.skip("probe or Flores assets missing")
    fi = TD.faces_and_identity(cv2.imread(str(probe)), refs, TD.DEFAULTS)
    by = {f["match"]: f["cosine"] for f in fi["faces"] if f["match"]}
    assert by.get("defendant", 0) >= TD.DEFAULTS["identity_min"] and by.get("boyd", 0) >= TD.DEFAULTS["identity_min"]
    assert all(not f["cut_by_frame"] for f in fi["faces"])


def test_thumbnail_mode_dispatch(monkeypatch, tmp_path):
    from boydclips import thumbnail as T
    calls = []
    monkeypatch.setattr(T, "_direct_build", lambda *a, **k: calls.append("direct") or None)
    monkeypatch.setattr(T, "_legacy_build", lambda *a, **k: calls.append("legacy") or tmp_path / "x.jpg")
    T.build_for_mode({"mode": "legacy"}, lambda: None, lambda: None)
    T.build_for_mode({"mode": "direct_gen"}, lambda: None, lambda: None)
    assert calls == ["legacy", "direct", "legacy"]        # direct returned None -> legacy fallback


def test_usage_limit_is_reported_as_such(tmp_path, monkeypatch):
    """A refused session must surface the platform's reason and retry time,
    not a generic 'no output' error (the daily route falls back on it)."""
    import subprocess
    log_text = "prompt echoed..." + chr(10) + "ERROR: You've hit your usage limit. Upgrade to Pro, visit usage or try again at 7:48 PM." + chr(10)

    def fake_run(cmd, **kw):
        kw["stdout"].write(log_text)
        return subprocess.CompletedProcess(cmd, 1)
    monkeypatch.setattr(TD.subprocess, "run", fake_run)
    monkeypatch.setattr(TD.shutil, "which", lambda name: "codex.cmd")
    _synthetic(tmp_path / "d.png", (300, 300), text="")
    with pytest.raises(TD.UsageLimit) as ei:
        TD.run_codex("p", [("defendant_1", tmp_path / "d.png")], tmp_path / "w", TD.DEFAULTS)
    assert "7:48 PM" in str(ei.value)


def test_image_budget_below_complete_set_stops_before_runner(tmp_path):
    calls = []
    with pytest.raises(TD.UsageLimit, match="needs at least 3"):
        TD.run_case(
            "fixture",
            out_dir=tmp_path / "out",
            work=tmp_path / "work",
            runner=lambda *args, **kwargs: calls.append(1) or {},
            cfg={"budget": 2},
            case_dict={"_key": "fixture", "video": str(tmp_path / "missing.mp4")},
        )
    assert calls == []


def test_sol_session_budget_stops_thumbnail_retries(tmp_path, monkeypatch):
    work, out = tmp_path / "work", tmp_path / "out"
    work.mkdir()
    calls = []

    def runner(prompt, attachments, workdir, cfg, extra_args=None):
        calls.append(1)
        return {"concepts": [], "images_generated_total": 3, "notes": "fixture"}

    _synthetic(tmp_path / "d.png", (400, 400), text="")
    monkeypatch.setattr(TD, "gather_assets", lambda c, w=None: TD.Assets(defendant=[tmp_path / "d.png"]))
    m = TD.run_case(
        "SOLCAP", out, work, None, runner=runner,
        cfg={"budget": 9, "retries": 2, "model_call_budget": 1},
        case_dict={"_key": "SOLCAP", "white": "VERIFIED", "yellow": "QUOTE"},
    )

    assert calls == [1]
    assert m["model_calls_used"] == 1
    assert not m["complete"]


def test_legacy_failure_under_direct_gen_records_missing_thumbnail(monkeypatch):
    """2026-09-06: the Q3 fallback raised after the long-form had rendered and
    took the whole case down. Under direct_gen the case continues with the
    thumbnail recorded as missing; legacy mode still raises."""
    from boydclips import thumbnail as T

    def boom():
        raise RuntimeError("cannot identify the defendant - pick another frame")
    r = T.build_for_mode({"mode": "direct_gen"}, lambda: None, boom)
    assert r["file_path"] is None and r["status"] == "missing" and "defendant" in r["error"]
    with pytest.raises(RuntimeError):
        T.build_for_mode({"mode": "legacy"}, lambda: None, boom)


def test_build_direct_resolves_the_quote_splitter(monkeypatch, tmp_path):
    """build_direct referenced split_thumbnail_quote without importing it
    (NameError on the first real run). It must resolve and hand a case dict
    with the split quote to thumb_direct.run_case."""
    import sys
    import types
    from boydclips import thumbnail as T
    seen = {}

    def fake_run_case(case, out_dir, work, args, runner=None, cfg=None, case_dict=None):
        seen.update(case_dict)
        out_dir.mkdir(parents=True, exist_ok=True)
        finals = {}
        for label in "ABC":
            path = out_dir / f"{label}.jpg"
            path.write_bytes(b"x")
            finals[label] = str(path)
        return {"finals": finals, "contact_sheet": None, "complete": True,
                "images_generated_total": 3}
    monkeypatch.setitem(sys.modules, "thumb_direct", types.SimpleNamespace(run_case=fake_run_case))
    pkg = {"thumbnail_quote": "This cop was lying!", "thumbnail_quote_yellow": "was lying!", "description": "d"}
    case = {"case_key": "vid:10", "start_s": 10.0, "end_s": 100.0, "hook_start_s": 40.0, "defendant_name": "X Y"}
    res = T.build_direct(tmp_path / "src.mp4", 0.0, case, pkg, tmp_path, {"mode": "direct_gen", "direct": {}})
    assert res and res["mode"] == "direct_gen" and res["file_path"].endswith("A.jpg")
    assert res["complete"] and res["images_generated_total"] == 3
    assert seen["white"] and seen["yellow"] and seen["defendant"] == "X Y"


# ---- 2026-09-06: the extractor handed Boyd's tile over as the defendant ----

def test_build_direct_work_key_is_unique_per_case(monkeypatch, tmp_path):
    """Without a case_key every route case shared thumbwork/case and reused
    the first case's extracted defendant. The source file's stem is unique."""
    import sys
    import types
    from boydclips import thumbnail as T
    seen = {}

    def fake_run_case(case, out_dir, work, args, runner=None, cfg=None, case_dict=None):
        seen["key"] = case
        out_dir.mkdir(parents=True, exist_ok=True)
        finals = {}
        for label in "ABC":
            path = out_dir / f"{label}.jpg"
            path.write_bytes(b"x")
            finals[label] = str(path)
        return {"finals": finals, "contact_sheet": None, "complete": True,
                "images_generated_total": 3}
    monkeypatch.setitem(sys.modules, "thumb_direct", types.SimpleNamespace(run_case=fake_run_case))
    pkg = {"thumbnail_quote": "This cop was lying!", "thumbnail_quote_yellow": "was lying!", "description": "d"}
    case = {"start_s": 8340.0, "end_s": 9465.0, "hook_start_s": 8400.0, "defendant_name": "X Y"}
    T.build_direct(tmp_path / "dAKO7myCd-g_8340_8296-9488.mp4", 0.0, case, pkg, tmp_path, {"direct": {}})
    assert seen["key"] == "dAKO7myCd-g_8340_8296-9488"


def test_boyd_tile_is_the_one_that_matches_her_reference():
    import thumb_direct as TD
    assert TD.boyd_tile_index([0.61, 0.12]) == 0
    assert TD.boyd_tile_index([0.08, 0.55]) == 1
    assert TD.boyd_tile_index([-1.0, -1.0]) is None          # no faces at all
    assert TD.boyd_tile_index([0.40, 0.38]) is None          # a tie says nothing
    assert TD.parse_crop("crop=612:338:18:190") == (612, 338, 18, 190)
    assert TD.parse_crop("null") is None


def test_person_box_frames_one_person_inside_the_tile():
    import thumb_direct as TD
    x, y, w, h = TD.person_box((300.0, 60.0, 40.0, 50.0), 620, 338)
    assert x < 300 and x + w > 340 and y < 60 and y + h <= 338 and x >= 0
    assert w <= 620 and h <= 338
    # a face at the tile edge stays clipped to the tile
    x, y, w, h = TD.person_box((5.0, 2.0, 40.0, 50.0), 620, 338)
    assert x == 0 and y == 0 and w > 0


def test_extraction_takes_the_lectern_person_from_the_courtroom_tile(monkeypatch, tmp_path):
    """Two tiles: the judge on the left, two people at the lectern on the
    right. The defendant cutout must come from the right tile's LEFT person
    and Boyd's cutout from the left tile; the old code took tiles[0]."""
    import sys
    import types
    import numpy as np
    import cv2
    import thumb_direct as TD
    from boydclips import render as R
    W, H = 1280, 720
    left = (612, 338, 18, 190)
    right = (620, 338, 644, 190)
    # faces: the judge in the left tile; lectern (x=0.30) and counsel (x=0.72) in the right tile
    judge = (left[2] + 280, left[3] + 90, 60, 70)
    lectern = (right[2] + 186 - 20, right[3] + 110, 40, 48)
    counsel = (right[2] + 446 - 22, right[3] + 100, 44, 52)
    face_list = [judge, lectern, counsel]

    def faces_in(bgr, score=0.6):
        h, w = bgr.shape[:2]
        # pretend the detector finds the faces we drew (rects are flagged by colour)
        rows = []
        for (x, y, fw, fh), tag in zip(face_list, ("judge", "lectern", "counsel")):
            # find this face's tag colour inside the crop
            mask = np.all(bgr == TAGS[tag], axis=2)
            if mask.any():
                ys, xs = np.where(mask)
                rows.append([float(xs.min()), float(ys.min()), float(xs.max() - xs.min() + 1), float(ys.max() - ys.min() + 1), 0.9])
        return rows

    TAGS = {"judge": (10, 20, 200), "lectern": (200, 20, 10), "counsel": (20, 200, 10)}
    frame = np.full((H, W, 3), 90, np.uint8)
    for (x, y, fw, fh), tag in zip(face_list, ("judge", "lectern", "counsel")):
        frame[y:y + fh, x:x + fw] = TAGS[tag]
    fake_ident = types.SimpleNamespace(
        faces_in=faces_in,
        embed=lambda bgr, r: np.array([1.0 if tuple(bgr[int(r[1]) + 1, int(r[0]) + 1]) == TAGS["judge"] else 0.0]),
        score_against=lambda vec, ref: float(vec[0]),
        load_reference=lambda: np.ones((1, 1)),
        cosine=lambda a, b: float(np.dot(a, b)))
    fake_matting = types.SimpleNamespace(alpha=lambda bgr, refine=True: np.ones(bgr.shape[:2], np.float32))
    monkeypatch.setitem(sys.modules, "identity", fake_ident)
    monkeypatch.setitem(sys.modules, "matting", fake_matting)
    monkeypatch.setattr(R, "detect_tile_crops", lambda src: ("crop=612:338:18:190", "crop=620:338:644:190"))
    src = tmp_path / "case.mp4"
    src.write_bytes(b"x")

    def fake_run(cmd, **kw):
        out = Path(cmd[-1])
        cv2.imwrite(str(out), frame)
        return types.SimpleNamespace(returncode=0)
    monkeypatch.setattr(TD.subprocess, "run", fake_run)
    got = TD.extract_from_video({"video": str(src), "plate_t": 10.0, "offset": 0.0}, tmp_path / "wd", samples=2)
    info = json.loads((tmp_path / "wd" / "extraction.json").read_text())
    assert info["boyd_tile"] == 0 and info["tile"] == 1
    assert abs(info["face"][0] - 0.30) < 0.03                      # the lectern person, not counsel at 0.72
    cut = cv2.imread(str(got["defendant"][0]), cv2.IMREAD_UNCHANGED)
    assert cut is not None and cut.shape[2] == 4
    assert np.all(cut[..., :3] == TAGS["lectern"], axis=2).any()   # the defendant's pixels are in the cutout
    assert not np.all(cut[..., :3] == TAGS["judge"], axis=2).any()  # and the judge's are not
    assert got["boyd"] and np.all(cv2.imread(str(got["boyd"][0]), cv2.IMREAD_UNCHANGED)[..., :3] == TAGS["judge"], axis=2).any()
