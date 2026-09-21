from boydclips import render
from boydclips.transcribe import Word


def test_body_enters_on_court_is_calling():
    words = [
        Word(100.0, "waiting"), Word(141.0, "Court"),
        Word(141.3, "is"), Word(141.6, "calling."), Word(142.0, "cause"),
    ]
    pieces, start = render.align_body_to_court_call(
        words, [render.Segment(96.0, 200.0)], max_wait_s=90, lead_s=0.08,
    )
    assert start == 140.92
    assert pieces == [render.Segment(140.92, 200.0)]


def test_missing_or_late_court_call_preserves_original_cut():
    original = [render.Segment(96.0, 120.0), render.Segment(130.0, 200.0)]
    for words in (
        [Word(101.0, "court"), Word(101.2, "called")],
        [Word(190.0, "court"), Word(190.2, "is"), Word(190.4, "calling")],
    ):
        pieces, start = render.align_body_to_court_call(
            words, original, max_wait_s=60, lead_s=0.08,
        )
        assert start is None
        assert pieces == original


def test_court_call_must_be_inside_a_kept_piece():
    original = [render.Segment(96.0, 120.0), render.Segment(150.0, 200.0)]
    words = [Word(140.0, "court"), Word(140.2, "is"), Word(140.4, "calling")]
    pieces, start = render.align_body_to_court_call(words, original)
    assert start is None
    assert pieces == original
