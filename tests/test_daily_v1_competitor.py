from boydclips import competitor
from boydclips.transcribe import Transcript, Word


def transcript(video_id, text):
    return Transcript(video_id, [Word(float(i), word) for i, word in enumerate(text.split())])


def test_competitor_scan_is_bounded_and_ranks_age_adjusted_views(monkeypatch):
    outputs = {
        "one": "v1\tFirst\t600\t10000\t20260911\nv2\tSecond\t600\t500\t20260901",
        "two": "v3\tThird\t600\t9000\t20260911",
    }
    calls = []

    def runner(args):
        calls.append(args)
        return outputs[args[-1]]

    leads = competitor.list_recent(
        [{"name": "A", "url": "one"}, {"name": "B", "url": "two"}],
        per_channel=2,
        max_leads=2,
        runner=runner,
    )

    assert [lead.video_id for lead in leads] == ["v1", "v3"]
    assert len(calls) == 2
    assert all(args[args.index("--playlist-end") + 1] == "2" for args in calls)


def test_exact_competitor_audio_resolves_to_original_case():
    shared = "the court needs to know why you came back after one more chance today"
    leads = [
        (competitor.Lead("lead", "A", "Interesting", 12000, "2026-09-11", 600),
         transcript("lead", "intro words " + shared + " outro words")),
    ]
    match = competitor.best_match(
        "setup from original stream " + shared + " complete ruling and aftermath",
        leads,
        min_overlap=0.1,
    )

    assert match and match["video_id"] == "lead"
    assert match["original_source_verified"] is True
    assert match["transcript_overlap"] >= 0.1


def test_generic_court_words_do_not_create_a_match():
    leads = [
        (competitor.Lead("lead", "A", "Generic", 1000, "2026-09-11", 60),
         transcript("lead", "judge court hearing today your honor")),
    ]
    assert competitor.best_match(
        "the judge opened another court hearing for a different person",
        leads,
        min_overlap=0.08,
    ) is None


def test_verified_competitor_lead_ranks_before_unmatched_candidate():
    matched = {
        "total_score": 82,
        "competitor_lead": {"original_source_verified": True, "lead_strength": 9.0},
    }
    unmatched = {"total_score": 99}

    ordered = sorted([(unmatched, 0), (matched, 1)], key=lambda row: competitor.candidate_priority(*row))

    assert ordered[0][0] is matched
