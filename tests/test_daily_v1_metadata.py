from boydclips.metadata import case_tags, has_case_specific_tag


def test_tags_keep_channel_terms_and_add_only_case_topics():
    tags = case_tags(
        ["judge boyd", "courtroom", "viral", "judge boyd"],
        {"proceeding_type": "probation_revocation"},
        {"longform_title": "Judge Boyd Weighs Another Chance",
         "summary": "A sentencing decision after a probation violation."},
    )

    assert tags[:2] == ["judge boyd", "courtroom"]
    assert "probation revocation hearing" in tags
    assert "probation violation" in tags
    assert "sentencing hearing" in tags
    assert "viral" not in tags
    assert len(",".join(tags)) <= 500


def test_tags_add_specific_story_topic_when_proceeding_is_generic():
    tags = case_tags(
        ["judge boyd", "courtroom"],
        {"proceeding_type": "other", "defendant_name": "Jane Sample"},
        {"longform_title": "Judge Boyd Presses Her About the Missing Cell Phone",
         "summary": "A dispute over the phone changes the hearing."},
    )

    assert "cell phone dispute" in tags
    assert has_case_specific_tag(tags)
