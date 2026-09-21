"""Story-level memory: the regression set for "have we already made this video?".

Written after 2026-09-16, when `dAKO7myCd-g:8929` was selected and rendered
although the same hearing already had a long-form and a Short. Case keys cannot
see that: a re-scored hearing gets a new row. These tests pin the six situations
named in the request — same story / different hearing id, same cause / different
clip, existing long+Short, a rejected package that may be retried, a genuinely
new story, and an ambiguous possible match — plus the rule that a technically
valid Short is not an approved Short.
"""
from __future__ import annotations

import sqlite3
import sys
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from boydclips.pipeline import Pipeline, StoryReuseError  # noqa: E402
from boydclips.stories import StoryLedger  # noqa: E402


def ledger(tmp_path) -> StoryLedger:
    conn = sqlite3.connect(str(tmp_path / "ledger.db"))
    return StoryLedger(conn)


def add_story(led, *, video, start, end, cause=None, defendant="Someone",
              clip=None, editorial="UNREVIEWED", eligible=True, reason=None):
    story_id = led.story_id(video, start, cause)
    led.upsert_story(story_id, label=f"{defendant} — story", cause_number=cause,
                     defendant_label=defendant, selection_eligible=eligible,
                     ineligible_reason=reason, confidence="CONFIRMED")
    led.add_source(story_id, video, start, end, cause_number=cause,
                   evidence="test fixture")
    if clip:
        led.add_artifact(story_id, clip, Path(f"{video}_{int(start)}_{clip}.mp4"),
                         technical_status="VALID", editorial_status=editorial,
                         evidence="test fixture")
    return story_id


def test_same_story_different_hearing_id_is_a_match(tmp_path):
    """A re-scored hearing has a new case key and the same window."""
    led = ledger(tmp_path)
    add_story(led, video="dAKO7myCd-g", start=8340, end=9465,
              cause="2023 CR 10327", defendant="Andrew Garcia", clip="longform")

    kind, story_id, why = led.match("dAKO7myCd-g", 8929, 9469, "unknown")

    assert kind == "EXISTING" and story_id == "cause:2023cr10327"
    assert "inside an already-recorded window" in why


def test_same_cause_different_docket_is_a_match(tmp_path):
    """One cause heard across two sittings is one story."""
    led = ledger(tmp_path)
    add_story(led, video="docketA", start=100, end=400, cause="2022 CR0273",
              defendant="Louis Fletcher Thompson", clip="longform")

    kind, story_id, _why = led.match("docketB", 8000, 8400, "2022-CR-0273")

    assert kind == "EXISTING" and story_id == "cause:2022cr0273"


def test_existing_long_and_short_blocks_unattended_selection(tmp_path):
    led = ledger(tmp_path)
    add_story(led, video="v", start=10, end=610, cause="2026 CR 1",
              defendant="Jordan Rhodess", clip="longform", eligible=False,
              reason="package exists")
    add_story(led, video="v", start=10, end=610, cause="2026 CR 1") if False else None
    story = led.story_id("v", 10, "2026 CR 1")
    led.add_artifact(story, "short", Path("v_10_short.mp4"), technical_status="VALID",
                     editorial_status="UNREVIEWED", evidence="test fixture")

    blocked, why = led.selection_block("v", 10, 610, "2026 CR 1", "Jordan Rhodess")

    assert blocked and "already has a package" in why
    info = led.preflight("v", 10, 610, "2026 CR 1", "Jordan Rhodess")
    assert info["story_match"] == "EXISTING"
    assert info["prior_longform"] == "YES" and info["prior_short"] == "YES"
    assert info["selection_eligible"] is False


def test_rejected_package_may_be_retried_only_with_an_explicit_reason(tmp_path, monkeypatch):
    """A rejected package is a legitimate reason to revisit — but the reason has
    to be stated. Without it the render is refused before any work starts."""
    led = ledger(tmp_path)
    story_id = add_story(led, video="dAKO7myCd-g", start=8340, end=9465,
                         cause="2023 CR 10327", defendant="Andrew Garcia",
                         clip="longform", editorial="NEEDS_USER_REEDIT",
                         eligible=False, reason="Short rejected; needs the user's own edit")
    led.add_artifact(story_id, "short", Path("rejected_short.mp4"),
                     technical_status="VALID", editorial_status="NEEDS_USER_REEDIT",
                     evidence="user review")
    led.conn.commit()

    class FakeStore:
        conn = led.conn

        @staticmethod
        def case_key(video_id, start_s):
            return f"{video_id}:{int(start_s)}"

    class FakeDocket:
        video_id = "dAKO7myCd-g"
        title = "THUR, MARCH 7, 2024"

    pipe = Pipeline.__new__(Pipeline)
    pipe.store = FakeStore()
    case = {"start_s": 8929.0, "end_s": 9469.0, "cause_number": "unknown",
            "defendant_name": "unknown (detention officer defendant)"}

    pipe._revisit_reason = None
    with pytest.raises(StoryReuseError, match="already holds work"):
        pipe._story_memory(FakeDocket(), case)

    pipe._revisit_reason = "the user asked for a fresh Short cut on this hearing"
    memory = pipe._story_memory(FakeDocket(), case)
    assert memory["story_match"] == "EXISTING"
    decisions = [row["decision"] for row in led.conn.execute(
        "SELECT decision FROM story_decisions WHERE story_id = ?", (story_id,))]
    assert "REVISIT_AUTHORISED" in decisions


def test_genuinely_new_story_is_selectable(tmp_path):
    led = ledger(tmp_path)
    add_story(led, video="other", start=1, end=2, cause="2020 CR 9")

    blocked, why = led.selection_block("newvideo", 500, 900, "2026 CR 77777", "A Person")
    info = led.preflight("newvideo", 500, 900, "2026 CR 77777", "A Person")

    assert not blocked and why == ""
    assert info["story_match"] == "NEW"
    assert info["prior_longform"] == "NO" and info["prior_short"] == "NO"


def test_ambiguous_name_match_is_flagged_and_blocks(tmp_path):
    """Same first name AND surname is a lead a human must settle."""
    led = ledger(tmp_path)
    add_story(led, video="v", start=100, end=400, cause="2026 CR 5",
              defendant="Denise Marie Thomas", clip="longform")

    info = led.preflight("other", 900, 1200, "unknown", "Denise Thomas")
    blocked, why = led.selection_block("other", 900, 1200, "unknown", "Denise Thomas")

    assert info["story_match"] == "POSSIBLE_MATCH" and blocked
    assert "same surname is not identity" in why


def test_a_shared_surname_alone_is_not_identity(tmp_path):
    """Live example: Oscar Carvajal Jr. and Jose Carvajal share a surname and
    nothing else; Javier Garcia is not Andrew Garcia."""
    led = ledger(tmp_path)
    add_story(led, video="v", start=100, end=400, cause="2022 CR 5498",
              defendant="Jose Carvajal", clip="longform")

    info = led.preflight("other", 900, 1200, "unknown", "Oscar Carvajal Jr.")

    assert info["story_match"] == "NEW"


def test_technically_valid_is_not_editorially_approved(tmp_path):
    """The 2026-09-16 rule: short.mp4 existing and decoding is not approval."""
    led = ledger(tmp_path)
    path = tmp_path / "short.mp4"
    path.write_bytes(b"not really a video; the status fields are the point")
    story_id = add_story(led, video="v", start=1, end=2, cause="2024 CR0787",
                         defendant="Nashia Renee Harrison", clip="longform")
    led.add_artifact(story_id, "short", path, technical_status="VALID",
                     editorial_status="NEEDS_USER_REEDIT", evidence="user review")
    led.conn.commit()

    row = led.conn.execute(
        "SELECT technical_status, editorial_status FROM story_artifacts"
        " WHERE story_id = ? AND kind = 'short'", (story_id,)).fetchone()

    assert row["technical_status"] == "VALID"
    assert row["editorial_status"] == "NEEDS_USER_REEDIT"
    with pytest.raises(ValueError, match="unknown editorial status"):
        led.add_artifact(story_id, "short", path, editorial_status="APPROVED_BY_DECODE")


@pytest.mark.skipif(not (ROOT / "state" / "pipeline.db").is_file(),
                    reason="no pipeline store in this checkout")
def test_the_real_ledger_blocks_the_garcia_story():
    """Against the shipped store: the failure of 2026-09-16 cannot repeat."""
    conn = sqlite3.connect(f"file:{ROOT / 'state' / 'pipeline.db'}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    led = StoryLedger(conn)
    if not led.story("cause:2023cr10327"):
        pytest.skip("story ledger has not been built in this checkout")

    info = led.preflight("dAKO7myCd-g", 8929.0, 9469.0, "unknown")
    blocked, why = led.selection_block("dAKO7myCd-g", 8929.0, 9469.0, "unknown")

    assert info["story_match"] == "EXISTING"
    assert info["prior_longform"] == "YES" and info["prior_short"] == "YES"
    assert blocked and "already has a package" in why
    short = conn.execute(
        "SELECT editorial_status FROM story_artifacts WHERE story_id = ?"
        " AND kind = 'short' AND path LIKE ?",
        ("cause:2023cr10327", "%dAKO7myCd-g_8929%")).fetchone()
    assert short is not None and short["editorial_status"] == "NEEDS_USER_REEDIT"


def test_a_manifest_verdict_survives_a_rebuild(tmp_path, monkeypatch):
    """`boyd reject --short` writes the verdict into the manifest. The next
    `story_ledger.py build` must read it back, not reset it to UNREVIEWED."""
    sys.path.insert(0, str(ROOT / "tools"))
    import story_ledger

    review = tmp_path / "out" / "review" / "2026-09-10_CqAKrxLobT0_6499"
    review.mkdir(parents=True)
    (review / "manifest.json").write_text(json.dumps({
        "status": "candidate",
        "source": {"video_id": "CqAKrxLobT0", "docket_date": "2026-09-10"},
        "case": {"start_s": 6499.0, "end_s": 6683.0, "cause_number": "2024 CR0787",
                 "defendant_name": "Nashia Renee Harrison"},
        "outputs": {"short": {"file_path": str(review / "short.mp4"),
                              "editorial_status": "NEEDS_USER_REEDIT",
                              "editorial_note": "rejected cut"}},
    }), encoding="utf-8")
    monkeypatch.setattr(story_ledger, "ROOT", tmp_path)
    led = ledger(tmp_path)

    story_ledger.from_review(led, {})
    row = led.conn.execute(
        "SELECT editorial_status, note FROM story_artifacts WHERE kind = 'short'"
    ).fetchone()

    assert row["editorial_status"] == "NEEDS_USER_REEDIT"
    assert "rejected cut" in row["note"]


def test_operator_verdicts_derive_onto_the_story(tmp_path):
    """The store's own ledger table is the operator's record; the story ledger
    derives from it instead of keeping rows a rebuild would delete."""
    sys.path.insert(0, str(ROOT / "tools"))
    import story_ledger

    led = ledger(tmp_path)
    led.conn.executescript(
        "CREATE TABLE ledger (case_key TEXT, decision TEXT, reason TEXT,"
        " safety_related INTEGER, artifact_hash TEXT, decided_at TEXT);"
        "CREATE TABLE cases (case_key TEXT, video_id TEXT, start_s REAL, end_s REAL,"
        " cause_number TEXT, defendant TEXT);")
    led.conn.execute("INSERT INTO cases VALUES ('v:10','v',10,610,'2026 CR 1','A Person')")
    led.conn.execute("INSERT INTO ledger VALUES ('v:10','rejected','looked wrong',0,NULL,'now')")
    led.conn.commit()
    add_story(led, video="v", start=10, end=610, cause="2026 CR 1", defendant="A Person")

    assert story_ledger.from_operator_ledger(led) == 1

    story = led.story("cause:2026cr1")
    decisions = [row["decision"] for row in led.conn.execute(
        "SELECT decision FROM story_decisions WHERE story_id = 'cause:2026cr1'")]
    feedback = [row["preference"] for row in led.conn.execute(
        "SELECT preference FROM story_feedback WHERE story_id = 'cause:2026cr1'")]
    assert story["review_state"] == "REJECTED" and not story["selection_eligible"]
    assert "OPERATOR_REJECTED" in decisions and "looked wrong" in feedback


def test_publishing_refuses_a_rejected_short_cut():
    """A rejected cut may not move toward publishing even though it decodes."""
    from boydclips import readiness

    with pytest.raises(readiness.ReadinessError, match="not an approved edit"):
        readiness._require_editorial_clearance(
            {"file_path": "short.mp4", "editorial_status": "NEEDS_USER_REEDIT",
             "editorial_note": "the user rejected this cut"})
    readiness._require_editorial_clearance({"file_path": "short.mp4",
                                            "editorial_status": "UNREVIEWED"})
