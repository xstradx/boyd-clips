"""Unstructured auto-captions (no '>>', no punctuation) get their speaker
turns from the diarisation; structured transcripts are split as before."""
from boydclips import shorts_editor as SE
from boydclips.transcribe import Word


def _words(text: str, start: float = 100.0, step: float = 0.4):
    return [Word(t=round(start + i * step, 3), w=w) for i, w in enumerate(text.split())]


UNPUNCT = ("what have you done in the last year on probation nothing your honor i was pregnant "
           "and i did not want to have my baby in jail so what have you done since then nothing "
           "the court is going to deny the motion and amend your conditions to felony drug court")


def test_has_speaker_structure():
    assert not SE.has_speaker_structure(_words(UNPUNCT))
    assert SE.has_speaker_structure(_words("All right. Court is calling the case. >> Yes, ma'am."))
    assert SE.has_speaker_structure(_words("That's as immediate as I can do. All right, court is calling. Yes ma'am I did. No."))
    assert not SE.has_speaker_structure([])


def test_diarisation_splits_an_unstructured_transcript():
    ws = _words(UNPUNCT)                      # 55 words, 100.0 .. 121.6
    tw = SE.timed_words(ws, 90.0, 130.0, 0.9)
    assert len(SE.split_turns(tw, 0.6)) == 1  # the failure mode: one turn
    # Boyd 100-104.5, defendant 104.5-112.9, Boyd 112.9-116.5, defendant 116.5-118.5, Boyd after
    diar = [(100.0, "boyd"), (104.5, "defendant"), (112.9, "boyd"), (116.5, "defendant"), (118.5, "boyd")]
    turns = SE.label_speakers(SE.split_turns(tw, 0.6, diar=diar), diar)
    assert len(turns) >= 4
    assert all(len(t.words) >= 2 for t in turns)
    spk = [t.speaker for t in turns]
    assert spk[0] == "boyd" and "defendant" in spk
    # every word kept, in order, exactly once
    flat = [w.w for t in turns for w in t.words]
    assert flat == [w.w for w in tw]


def test_structured_transcript_is_split_the_same_with_diar():
    txt = "Court is calling the case. >> Yes, ma'am. >> Did you report? >> No, I did not. >> Why not?"
    ws = _words(txt)
    tw = SE.timed_words(ws, 90.0, 130.0, 0.9)
    base = SE.split_turns(tw, 0.6)
    diar = [(100.0, "boyd"), (101.0, "defendant"), (102.5, "boyd"), (104.0, "defendant"), (106.0, "boyd")]
    with_diar = SE.split_turns(tw, 0.6, diar=diar)
    assert [len(t.words) for t in with_diar] == [len(t.words) for t in base]


def test_jitter_and_short_sides_do_not_split():
    ws = _words(UNPUNCT)
    tw = SE.timed_words(ws, 90.0, 130.0, 0.9)
    # changes 0.3 s apart and one 0.2 s before the end: at most one real cut survives
    diar = [(100.0, "boyd"), (108.0, "defendant"), (108.3, "boyd"), (121.5, "defendant")]
    turns = SE.split_turns(tw, 0.6, diar=diar)
    assert 1 <= len(turns) <= 2
    assert all(len(t.words) >= 2 for t in turns)


def test_confident_defendant_text_survives_boyd_diarisation():
    """The ECAPA pass attributed 86-100 % of the 2024 hearings to Boyd and
    relabelled the defendant's own first-person answer as the judge."""
    ws = _words("Because I was supposed to be in custody and y'all let me out. All right. So we let her out of custody and then you go use drugs.")
    tw = SE.timed_words(ws, 90.0, 130.0, 0.9)
    turns = SE.split_turns(tw, 0.6)
    assert len(turns) >= 2
    diar = [(90.0, "boyd")]                      # the diariser says Boyd for everything
    labelled = SE.label_speakers(turns, diar)
    first = labelled[0]
    assert first.speaker == "defendant" and "diarize" not in first.speaker_evidence
    # a turn the text does not read as the defendant still takes the diarisation
    other = next(t for t in labelled if t.text.strip().startswith("So we let her"))
    assert other.speaker == "boyd" and "diarize" in other.speaker_evidence
