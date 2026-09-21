"""Regression for the phone-dispute ledger seed's review and release provenance."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from boydclips.stories import StoryLedger  # noqa: E402
import story_ledger  # noqa: E402


def _curated_ledger(tmp_path, monkeypatch) -> StoryLedger:
    """Apply only the curated seed to an isolated in-memory ledger."""
    monkeypatch.setattr(story_ledger, "ROOT", tmp_path)
    ledger = StoryLedger(sqlite3.connect(":memory:"))
    story_ledger.apply_curated(ledger)
    return ledger


def test_phone_seed_does_not_infer_approval_or_publication_from_recut_feedback(
        tmp_path, monkeypatch):
    ledger = _curated_ledger(tmp_path, monkeypatch)
    story_id = "cause:2026cr00004664"

    phone = ledger.story(story_id)
    assert phone["selection_eligible"] == 0
    assert phone["review_state"] == "UNREVIEWED"
    assert phone["publication_status"] == "UNKNOWN"
    reason = phone["ineligible_reason"].lower()
    assert "avoid duplicates" in reason
    assert "no publication receipt was found" in reason
    assert "editorial review" in reason
    assert "live release confirmation" in reason

    feedback = {
        row["dimension"]: row
        for row in ledger.conn.execute(
            "SELECT dimension, preference, source, quote FROM story_feedback"
            " WHERE story_id = ?", (story_id,))
    }
    assert set(feedback) == {"short_keeps_conversation", "payoff_placement"}
    assert feedback["short_keeps_conversation"]["quote"] == (
        "i dont like the way the shorts edited i need more convo between them")
    assert feedback["payoff_placement"]["source"] == "STATE.md 2026-09-13 entry"

    perry = ledger.story("cause:2025cr005793")
    assert perry["review_state"] == "APPROVED"
    assert perry["publication_status"] == "PUBLISHED"
    assert ledger.conn.execute(
        "SELECT 1 FROM story_decisions WHERE story_id = ? AND decision = ?",
        ("cause:2025cr005793", "APPROVED_AND_POSTED")).fetchone()

    garcia = ledger.story("cause:2023cr10327")
    assert garcia["review_state"] == "REJECTED"
    assert garcia["publication_status"] == "NONE"
    assert ledger.conn.execute(
        "SELECT 1 FROM story_decisions WHERE story_id = ? AND decision = ?",
        ("cause:2023cr10327", "SHORT_REJECTED_BY_USER")).fetchone()
