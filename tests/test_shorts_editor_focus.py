from boydclips.shorts_editor import Anchor, Beat, Candidate, TWord, assign_focus


def beat(start, text, *, role="turn", speaker="boyd", purpose="evidence"):
    toks = text.split()
    words = [TWord(i, start + i * 0.2, start + (i + 1) * 0.2, token) for i, token in enumerate(toks)]
    return Beat(role=role, turn=int(start), speaker=speaker, words=words, purpose=purpose)


def candidate(beats):
    return Candidate(Anchor(20.0, "model_beat", 0, "test"), 0, 0, [], [], beats=beats)


def cfg(max_punch_ins=None):
    return {"rapid_exchange_s": 0.1, "rapid_alternations": 3, "max_punch_ins": max_punch_ins,
            "punch_in_min_spacing_s": 3.0, "max_accents": 0}


def test_uncapped_focus_can_select_more_than_three_spaced_meaningful_beats():
    beats = [beat(0, "the record shows this", purpose="receipt"),
             beat(5, "this evidence contradicts that", purpose="contradiction"),
             beat(10, "why would you take it?", purpose="evidence"),
             beat(15, "the receipt confirms the amount", purpose="receipt")]
    out = assign_focus(candidate(beats), cfg())
    assert sum(b.punch_in for b in out.beats) == 4


def test_focus_rejects_filler_and_adjacent_jitter():
    beats = [beat(0, "the record shows this", purpose="receipt"),
             beat(1, "why did you do that?", purpose="evidence"),
             beat(6, "okay", purpose=""),
             beat(10, "have a seat", purpose="")]
    out = assign_focus(candidate(beats), cfg())
    assert [b.punch_in for b in out.beats] == [True, False, False, False]
