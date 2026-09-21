"""R49 cold open in the daily route: render.coldopen_span picks a 3-9 s
sentence at the money moment, inside the piece, later than 30 s into the body."""
from boydclips import render
from boydclips.render import Segment
from boydclips.transcribe import Word


def _words(start: float, text: str, step: float = 0.4):
    return [Word(t=round(start + i * step, 3), w=w) for i, w in enumerate(text.split())]


def test_span_ends_at_first_sentence_end_past_the_floor():
    ws = _words(100.0, "you deserve a conviction and I am going to give you a conviction. next case please now.")
    span, note = render.coldopen_span(ws, 100.0, [Segment(0.0, 200.0)])
    assert note == "ok" and span is not None
    c0, c1 = span
    assert abs(c0 - (100.0 - render.COLDOPEN_LEAD_S)) < 1e-6
    # "conviction." is word index 12 -> starts 104.8; its end is the next word's start 105.2
    assert abs(c1 - 105.2) < 1e-6
    assert render.COLDOPEN_MIN_S <= c1 - c0 <= render.COLDOPEN_MAX_S


def test_refuses_a_moment_inside_the_first_30s():
    ws = _words(10.0, "short line here. and more words follow this.")
    span, note = render.coldopen_span(ws, 10.0, [Segment(0.0, 200.0)])
    assert span is None and "into the body" in note


def test_refuses_a_moment_outside_the_pieces():
    ws = _words(300.0, "words. words words.")
    span, note = render.coldopen_span(ws, 300.0, [Segment(0.0, 200.0), Segment(400.0, 500.0)])
    assert span is None and "not inside" in note


def test_caps_at_max_when_no_sentence_end_arrives():
    ws = _words(100.0, " ".join(["word"] * 60))          # 24 s of speech, no punctuation
    span, note = render.coldopen_span(ws, 100.0, [Segment(0.0, 200.0)])
    assert span is not None
    c0, c1 = span
    assert c1 - c0 <= render.COLDOPEN_MAX_S + 1e-6
    assert c1 - c0 >= render.COLDOPEN_MIN_S


def test_never_runs_past_the_piece_end():
    ws = _words(100.0, " ".join(["word"] * 60))
    span, note = render.coldopen_span(ws, 100.0, [Segment(0.0, 103.5)])
    assert span is None or span[1] <= 103.5


def test_render_longform_accepts_the_span():
    """The span satisfies every check render_longform applies before encoding."""
    ws = _words(100.0, "no I did not do it. that is the whole point of this hearing today.")
    pieces = [Segment(40.0, 300.0)]
    span, note = render.coldopen_span(ws, 100.0, pieces)
    assert span is not None
    c0, c1 = span
    body0 = min(p.start_s for p in pieces)
    body1 = max(p.end_s for p in pieces)
    assert render.COLDOPEN_MIN_S <= c1 - c0 <= render.COLDOPEN_MAX_S
    assert body0 <= c0 and c1 <= body1
    assert c0 - body0 >= render.COLDOPEN_MIN_AHEAD_S
