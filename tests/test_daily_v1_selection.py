import logging
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from boydclips import cli, pipeline
from boydclips.discover import Docket
from boydclips.state import Store


class FakeConfig:
    def __init__(self, root: Path):
        self.root = root

    def get(self, key, default=None):
        return {
            "output.clips_per_day": 1,
            "output.bank_extras": True,
            "analysis.gates.recheck_selection": False,
            "autonomy.mode": "manual",
        }.get(key, default)

    def path(self, key):
        if key == "paths.state_db":
            return self.root / "state" / "pipeline.db"
        if key == "paths.logs":
            return self.root / "logs"
        raise AssertionError(key)


class FakeStore:
    def __init__(self, bank=(), rendered=()):
        self.bank = list(bank)
        self.rendered = set(rendered)
        self.marks = []
        # The pipeline consults the story ledger through the store's own
        # connection; a fake store without one would make the memory check
        # silently unavailable instead of exercised.
        self.conn = sqlite3.connect(":memory:")

    @staticmethod
    def case_key(video_id, start_s):
        return f"{video_id}:{int(start_s)}"

    @staticmethod
    def case_published(_key):
        return False

    def story_rendered(self, case_key, _video_id, _cause_number, _start_s=None, _end_s=None):
        return case_key in self.rendered

    def mark_docket(self, video_id, status, *args, **kwargs):
        self.marks.append((video_id, status))

    def banked_cases(self, limit=20):
        return self.bank[:limit]

    def get_docket_row(self, video_id):
        for row in self.bank:
            if row["video_id"] == video_id:
                return {
                    "video_id": video_id,
                    "title": f"stored {video_id}",
                    "duration_s": 3600,
                    "docket_date": "2026-09-10",
                }
        return None


def case(score, start=10.0, summary="candidate"):
    return {
        "eligible": True,
        "start_s": start,
        "end_s": start + 600,
        "total_score": score,
        "summary": summary,
    }


def make_pipeline(tmp_path, dockets, scored, bank=(), rendered=()):
    pipe = object.__new__(pipeline.Pipeline)
    pipe.cfg = FakeConfig(tmp_path)
    pipe.store = FakeStore(bank, rendered)
    pipe.work = tmp_path / "work"
    pipe.out = tmp_path / "out"
    pipe._analyzer = SimpleNamespace(calls_used=0, usage_events=[], reserved_calls=0)
    pipe.discover = lambda: dockets
    pipe.analyze_docket = lambda docket: list(scored[docket.video_id])
    pipe._repeat_tiebreak = lambda _video_id, rows: rows
    return pipe


def allow_ready(monkeypatch):
    monkeypatch.setattr(
        pipeline.readiness,
        "validate_candidate_bundle",
        lambda _path: {"ready": True, "case_key": "fixture"},
    )


def result(video_id):
    return {
        "longform": {"clip_id": f"{video_id}:10:longform"},
        "short": None,
        "package": {"hook_line": "hook"},
        "review_dir": f"review/{video_id}",
    }


def test_limit_is_global_and_best_case_wins(tmp_path, monkeypatch):
    allow_ready(monkeypatch)
    d1 = Docket("d1", "one", 3600, "2026-09-11", "morning")
    d2 = Docket("d2", "two", 3600, "2026-09-12", "morning")
    pipe = make_pipeline(tmp_path, [d1, d2], {"d1": [case(81)], "d2": [case(94)]})
    produced = []
    pipe.produce = lambda docket, picked: produced.append((docket.video_id, picked["total_score"])) or result(docket.video_id)
    monkeypatch.setattr(pipeline, "publish_pair", lambda *args, **kwargs: {"skipped": [], "short": {}, "longform": {}})

    outputs = pipe.run_daily(limit=1)

    assert produced == [("d2", 94)]
    assert len(outputs) == 1


def test_failed_best_candidate_falls_through_to_next(tmp_path, monkeypatch):
    allow_ready(monkeypatch)
    d1 = Docket("d1", "one", 3600, "2026-09-11", "morning")
    d2 = Docket("d2", "two", 3600, "2026-09-12", "morning")
    pipe = make_pipeline(tmp_path, [d1, d2], {"d1": [case(91)], "d2": [case(88)]})
    attempts = []

    def produce(docket, picked):
        attempts.append(docket.video_id)
        if docket.video_id == "d1":
            raise RuntimeError("fixture failure")
        return result(docket.video_id)

    pipe.produce = produce
    monkeypatch.setattr(pipeline, "publish_pair", lambda *args, **kwargs: {"skipped": [], "short": {}, "longform": {}})

    outputs = pipe.run_daily(limit=1)

    assert attempts == ["d1", "d2"]
    assert len(outputs) == 1


def test_new_discovery_excludes_an_already_rendered_local_case(tmp_path, monkeypatch):
    allow_ready(monkeypatch)
    d1 = Docket("d1", "one", 3600, "2026-09-11", "morning")
    d2 = Docket("d2", "two", 3600, "2026-09-12", "morning")
    pipe = make_pipeline(
        tmp_path,
        [d1, d2],
        {"d1": [case(96)], "d2": [case(88)]},
        rendered={"d1:10"},
    )
    produced = []
    pipe.produce = lambda docket, picked: produced.append(docket.video_id) or result(docket.video_id)
    monkeypatch.setattr(pipeline, "publish_pair", lambda *args, **kwargs: {"skipped": []})

    outputs = pipe.run_daily(limit=1)

    assert produced == ["d2"]
    assert len(outputs) == 1


def test_all_candidate_failures_raise_failed_run_signal(tmp_path, monkeypatch):
    d1 = Docket("d1", "one", 3600, "2026-09-11", "morning")
    pipe = make_pipeline(tmp_path, [d1], {"d1": [case(91)]})
    pipe.produce = lambda *_args: (_ for _ in ()).throw(RuntimeError("render broke"))

    with pytest.raises(pipeline.DailyRunError, match="no complete review bundle"):
        pipe.run_daily(limit=1)


def test_editorial_hold_is_a_clean_skip(tmp_path):
    d1 = Docket("d1", "one", 3600, "2026-09-11", "morning")
    pipe = make_pipeline(tmp_path, [d1], {"d1": [case(91)]})
    pipe.produce = lambda *_args: (_ for _ in ()).throw(
        pipeline.EditorialHoldError("Shorts Brain HOLD: no complete payoff")
    )

    assert pipe.run_daily(limit=1) == []


def test_exhausted_model_budget_is_a_failed_run_signal(tmp_path):
    d1 = Docket("d1", "one", 3600, "2026-09-11", "morning")
    pipe = make_pipeline(tmp_path, [d1], {"d1": [case(91)]})
    pipe._analyzer = SimpleNamespace(calls_used=20, usage_events=[])

    with pytest.raises(pipeline.DailyRunError, match="Sol call limit exhausted"):
        pipe.run_daily(limit=1)


def test_daily_run_reserves_enough_sol_calls_for_complete_bundle(tmp_path):
    d1 = Docket("d1", "one", 3600, "2026-09-11", "morning")
    pipe = make_pipeline(tmp_path, [d1], {"d1": [case(91)]})
    base = pipe.cfg

    class ProductionConfig:
        def get(self, key, default=None):
            return {
                "analysis.gates.recheck_selection": True,
                "analysis.producer_brain.enabled": True,
                "packaging.thumbnail.mode": "direct_gen",
            }.get(key, base.get(key, default))

        def path(self, key):
            return base.path(key)

    pipe.cfg = ProductionConfig()
    pipe._analyzer = SimpleNamespace(calls_used=18, usage_events=[])
    pipe.produce = lambda *_args: (_ for _ in ()).throw(AssertionError("must stop before partial work"))

    with pytest.raises(pipeline.DailyRunError, match="complete bundle needs at least 3"):
        pipe.run_daily(limit=1)


def test_cli_dry_run_never_runs_work_cleanup(monkeypatch):
    events = []

    class DryPipe:
        cfg = SimpleNamespace(get=lambda _self, _key, default=None: default)

        def run_daily(self, **_kwargs):
            events.append("run")
            return []

        def cleanup(self):
            events.append("cleanup")

        def close(self):
            events.append("close")

    monkeypatch.setattr(cli, "Pipeline", DryPipe)
    monkeypatch.setattr(cli, "setup_logging", lambda *_args: None)
    args = SimpleNamespace(moment=None, case=None, dry_run=True, limit=1, verbose=False)

    assert cli.cmd_run(args) == 0
    assert events == ["run", "close"]


def test_empty_discovery_uses_highest_unproduced_bank_case(tmp_path, monkeypatch):
    allow_ready(monkeypatch)
    bank = [{
        "case_key": "banked:20",
        "video_id": "banked",
        "start_s": 20.0,
        "end_s": 620.0,
        "total_score": 96.0,
        "payload": '{"eligible": true, "start_s": 20, "end_s": 620, "total_score": 96, "summary": "bank winner"}',
    }]
    pipe = make_pipeline(tmp_path, [], {}, bank=bank)
    produced = []
    pipe.produce = lambda docket, picked: produced.append((docket.video_id, picked["total_score"])) or result(docket.video_id)
    monkeypatch.setattr(pipeline, "publish_pair", lambda *args, **kwargs: {"skipped": [], "short": {}, "longform": {}})

    outputs = pipe.run_daily(limit=1)

    assert produced == [("banked", 96)]
    assert len(outputs) == 1


def test_same_story_bank_rows_are_attempted_once(tmp_path, monkeypatch):
    allow_ready(monkeypatch)
    bank = [
        {
            "case_key": f"banked:{start}", "video_id": "banked", "start_s": float(start),
            "end_s": float(end), "total_score": float(score),
            "payload": (
                '{"eligible": true, "start_s": %d, "end_s": %d, '
                '"story_windows": [[100, 900]], "total_score": %d, "summary": "same story"}'
            ) % (start, end, score),
        }
        for start, end, score in ((100, 500, 82), (500, 900, 94))
    ]
    pipe = make_pipeline(tmp_path, [], {}, bank=bank)
    attempts = []
    pipe.produce = lambda docket, picked: attempts.append(picked["total_score"]) or result(docket.video_id)
    monkeypatch.setattr(pipeline, "publish_pair", lambda *args, **kwargs: {"skipped": []})

    outputs = pipe.run_daily(limit=1)

    assert attempts == [94]
    assert len(outputs) == 1


def test_rendered_sibling_removes_entire_same_cause_story_from_bank(tmp_path):
    store = Store(tmp_path / "state.db")
    store.add_docket("video", "docket", "2026-09-12", 3600)
    first = store.save_case(
        "video", {**case(82, start=100), "cause_number": "2026 CR 1", "safety": {"safety_pass": True}}, 2,
    )
    store.save_case(
        "video", {**case(94, start=700), "cause_number": "2026 CR 1", "safety": {"safety_pass": True}}, 1,
    )
    store.save_clip(first, "longform", tmp_path / "first.mp4", 600, "title", "", "v")

    assert store.banked_cases() == []
    assert store.story_rendered("video:700", "video", "2026 CR 1") is True
    store.close()


def test_overlapping_rescored_row_of_a_rendered_hearing_counts_as_rendered(tmp_path):
    """dAKO7myCd-g, 2026-09-16. The hearing was scored twice: 8340 (8340-9465,
    cause 2023 CR 10327, rendered) and 8929 (8929-9469, cause "unknown"). The
    second row matched no clip by key and no sibling by cause, so it was handed
    to the renderer as "never rendered" and produced a second package for the
    same nine minutes. A candidate window that is mostly inside a window that
    already has media is the same story, whatever the row calls itself."""
    store = Store(tmp_path / "state.db")
    store.add_docket("dAKO7myCd-g", "docket", "2024-03-07", 10800)
    rendered = store.save_case(
        "dAKO7myCd-g",
        {**case(94, start=8340), "end_s": 9465.0, "cause_number": "2023 CR 10327",
         "safety": {"safety_pass": True}},
        1,
    )
    store.save_clip(rendered, "longform", tmp_path / "l.mp4", 1164, "title", "", "v")

    # Same hearing, re-scored row: unknown cause, window inside the rendered one.
    assert store.story_rendered("dAKO7myCd-g:8929", "dAKO7myCd-g", "unknown",
                                8929.0, 9469.0) is True
    # A genuinely different case in the same docket is untouched.
    assert store.story_rendered("dAKO7myCd-g:6000", "dAKO7myCd-g", "2024 CR 55",
                                6000.0, 6300.0) is False
    # And without a window to compare, the old behaviour is unchanged.
    assert store.story_rendered("dAKO7myCd-g:8929", "dAKO7myCd-g", "unknown") is False
    store.close()


def test_cli_limit_cannot_raise_hard_daily_ceiling(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="boydclips")
    bank = [
        {
            "case_key": f"d1:{start}", "video_id": "d1", "start_s": float(start),
            "end_s": float(start + 600), "total_score": float(score),
            "payload": (
                '{"eligible": true, "start_s": %d, "end_s": %d, '
                '"total_score": %d, "summary": "%s"}'
            ) % (start, start + 600, score, summary),
        }
        for start, score, summary in ((10, 93, "first"), (20, 90, "second"), (30, 88, "third"))
    ]
    pipe = make_pipeline(
        tmp_path,
        [],
        {},
        bank=bank,
    )
    pipe.discover = lambda: (_ for _ in ()).throw(AssertionError("dry-run must not discover"))
    pipe.analyze_docket = lambda docket: (_ for _ in ()).throw(AssertionError("dry-run must not analyze"))

    outputs = pipe.run_daily(limit=2, dry_run=True)

    assert outputs == []
    picks = [record for record in caplog.records if "[dry-run] global pick" in record.message]
    assert len(picks) == 1
