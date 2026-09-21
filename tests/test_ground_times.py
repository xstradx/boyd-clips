"""The scorer's quotes are verbatim; its timestamps are not. Ground them."""
from boydclips import analyze
from boydclips.transcribe import Word


def _words():
    text = ("court is calling the case. the only reason you're before me is because you had a vape pen "
            "so you got arrested and that's how you ended up before me. don't put jesus on me. here's the thing.")
    return [Word(t=round(6900 + i * 0.5, 3), w=w) for i, w in enumerate(text.split())]


def test_quote_time_is_found_inside_the_span():
    ws = _words()
    t = analyze.find_quote_time(ws, "The only reason you're before me is because you had a vape pen", 6800, 7600)
    assert t == 6900 + 5 * 0.5
    assert analyze.find_quote_time(ws, "words that never occur anywhere at all", 6800, 7600) is None


def test_ground_case_times_moves_late_timestamps_to_their_quotes():
    ws = _words()
    case = {"start_s": 6650.0, "end_s": 7529.0,
            "hook_quote": "The only reason you're before me is because you had a vape pen, so you got arrested",
            "hook_start_s": 7566.0,
            "editorial": {"money_moment_s": 7561.0,
                          "money_moment": "Boyd cuts through: \"Don't put Jesus on me. Here's the thing\" and more"},
            "short_segments": [{"beat": "hook", "start_s": 7566.0, "end_s": 7582.0,
                                "quote": "the only reason you're before me is because you had a vape pen"}]}
    notes = analyze.ground_case_times(case, ws)
    assert case["hook_start_s"] == 6902.5
    assert case["editorial"]["money_moment_s"] == 6900 + 30 * 0.5   # "don't" is token 30
    seg = case["short_segments"][0]
    assert seg["start_s"] == 6902.5 and abs((seg["end_s"] - seg["start_s"]) - 16.0) < 1e-6
    assert len(notes) == 3


def test_ground_case_times_leaves_close_timestamps_alone():
    ws = _words()
    case = {"start_s": 6650.0, "end_s": 7529.0, "hook_quote": "don't put jesus on me", "hook_start_s": 6911.0}
    assert analyze.ground_case_times(case, ws) == []
    assert case["hook_start_s"] == 6911.0
