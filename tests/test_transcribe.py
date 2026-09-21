from boydclips.transcribe import Word, apply_case_phrase_fixes


def _words(text: str):
    return [Word(float(i), token) for i, token in enumerate(text.split())]


def test_perry_phrase_fix_is_exact_and_preserves_timing():
    original = _words("when i made them choices back then it ain't nothing like that one")
    before = [w.t for w in original]
    fixed, count = apply_case_phrase_fixes("oL6lV6gCyOc", original)
    assert count == 1
    assert [w.t for w in fixed] == before
    assert " ".join(w.w for w in fixed if w.w) == "when I made them choices back then it ain't nothin' like now"


def test_perry_phrase_fix_does_not_apply_to_other_video():
    text = "when i made them choices back then it ain't nothing like that one"
    fixed, count = apply_case_phrase_fixes("someOtherVideo", _words(text))
    assert count == 0
    assert " ".join(w.w for w in fixed) == text


def test_perry_spurious_you_is_removed_only_for_this_case():
    fixed, count = apply_case_phrase_fixes("oL6lV6gCyOc", _words("y'all stipulated to you"))
    assert count == 1 and " ".join(w.w for w in fixed if w.w) == "y'all stipulated to."
    other, count = apply_case_phrase_fixes("other", _words("y'all stipulated to you"))
    assert count == 0 and " ".join(w.w for w in other) == "y'all stipulated to you"


def test_phone_negation_fix_requires_video_time_and_original_token():
    fixed, count = apply_case_phrase_fixes("IDGfe1rPUQo", [Word(6536.239, "would")])
    assert count == 1 and fixed == [Word(6536.239, "wouldn't")]
    fixed, count = apply_case_phrase_fixes("IDGfe1rPUQo", fixed)
    assert count == 0 and fixed == [Word(6536.239, "wouldn't")]
    for video, word in [("other", Word(6536.239, "would")),
                        ("IDGfe1rPUQo", Word(100.0, "would")),
                        ("IDGfe1rPUQo", Word(6536.239, "could"))]:
        fixed, count = apply_case_phrase_fixes(video, [word])
        assert count == 0 and fixed == [word]
