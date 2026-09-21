"""The bench's machine-readable half.

`python tools/bench.py check` used to report every expectation as "needs a
watch". On 2026-09-16 three of the six specimens got counterparts that read the
bundle and the cached transcript and can FAIL: the Short stays out of a refused
window, the last kept word stops before the sentence's first word, and the Short
opens on the approved source hook. These tests hold both directions — a
satisfied check is not a pass if it cannot find its own evidence, and a broken
bundle must trip the gate.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))
import bench  # noqa: E402
from boydclips.transcribe import Transcript, Word  # noqa: E402


def _workspace(tmp_path, *, last_word_s: float, opening: str = "hello there"):
    """A bench with one specimen, one manifest and one cached transcript."""
    transcript = Transcript("v", [Word(100.0, "All"), Word(100.2, "right."),
                                  Word(100.4, "This"), Word(100.6, "is"),
                                  Word(100.8, "what"), Word(101.0, "the"),
                                  Word(101.2, "court"), Word(101.4, "is"),
                                  Word(101.6, "going"), Word(101.8, "to"),
                                  Word(102.0, "do.")])
    (tmp_path / "work" / "v").mkdir(parents=True)
    (tmp_path / "work" / "v" / "v.transcript.json").write_text(transcript.to_json(), encoding="utf-8")
    (tmp_path / "out" / "review" / "case").mkdir(parents=True)
    plan = {
        "ok": True,
        "segments": [[90.0, last_word_s]],
        "word_stream": [{"src_t": 90.0, "w": opening.split()[0]},
                        {"src_t": last_word_s, "w": opening.split()[-1]}],
    }
    (tmp_path / "out" / "review" / "case" / "manifest.json").write_text(
        json.dumps({"outputs": {"short": {"edit_plan": plan}}}), encoding="utf-8")
    (tmp_path / "bench.json").write_text(json.dumps({"cases": [{
        "dir": "case",
        "manifest": "out/review/case/manifest.json",
        "case_key": "v:90.0",
        "expected": "SHORT_KEEPS_CONVERSATION_STOPS_BEFORE_SENTENCE",
        "checks": [{
            "kind": "ends_before_source_word",
            "transcript": "work/v/v.transcript.json",
            "sentence": "All right. This is what the court is going to do.",
            "first_word": "All",
            "first_word_s": 100.0,
        }],
    }]}), encoding="utf-8")
    return tmp_path


def test_bench_check_supports_the_expectation_when_the_short_stops_early(tmp_path, monkeypatch, capsys):
    root = _workspace(tmp_path, last_word_s=99.4)
    monkeypatch.setattr(bench, "ROOT", root)
    monkeypatch.setattr(bench, "BENCH", root / "bench.json")

    assert bench.check() == 0
    out = capsys.readouterr().out
    assert "supported" in out and "99.40s < sentence start 100.00s" in out


def test_bench_check_fails_when_the_short_runs_into_the_sentence(tmp_path, monkeypatch, capsys):
    root = _workspace(tmp_path, last_word_s=100.6)
    monkeypatch.setattr(bench, "ROOT", root)
    monkeypatch.setattr(bench, "BENCH", root / "bench.json")

    assert bench.check() == 1
    out = capsys.readouterr().out
    assert "VIOLATED" in out and "runs into the sentence" in out


def test_bench_check_refuses_to_pass_a_boundary_the_transcript_does_not_support(
        tmp_path, monkeypatch, capsys):
    """The recorded boundary is evidence too: if the transcript does not say
    "All right." at that time, the check cannot claim support."""
    root = _workspace(tmp_path, last_word_s=99.4)
    payload = json.loads((root / "bench.json").read_text(encoding="utf-8"))
    payload["cases"][0]["checks"][0]["first_word_s"] = 500.0
    (root / "bench.json").write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(bench, "ROOT", root)
    monkeypatch.setattr(bench, "BENCH", root / "bench.json")

    assert bench.check() == 1
    assert "recorded boundary is wrong" in capsys.readouterr().out


def test_bench_check_holds_the_real_specimens_that_carry_checks():
    """Against the shipped bench: every machine-readable check must hold, and
    the three unclassified specimens stay visibly unproven."""
    payload = json.loads((ROOT / "bench" / "bench.json").read_text(encoding="utf-8"))
    checked = [entry for entry in payload["cases"] if entry.get("checks")]
    assert len(checked) == 3
    for entry in checked:
        data = json.loads((ROOT / entry["manifest"]).read_text(encoding="utf-8"))
        for check in entry["checks"]:
            ok, detail = bench._run_check(check, data)
            assert ok, f"{entry['case_key']} {check['kind']}: {detail}"
