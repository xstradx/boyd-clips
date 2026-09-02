# GATES — fix the banger filter and finish the slate

CONTRACT: The mining filter is provably unreliable — it flagged a hearing that was
reset with no sentence as `sentence_pronounced=True`, and charge severity alone
kept surfacing plea paperwork. Fix the classifier against known controls, re-score
every hearing that has footage on disk, and produce a de-duplicated slate that
excludes anything already published or scheduled.

OWNS:
  C:/Users/natha/Projects/boyd-clips/tools/mine_slate.py
  D:/Boyd Clips/BANGERS/slate30.json
  D:/Boyd Clips/BANGERS/SLATE.md

CONTROLS (measured 2026-08-30, before any fix):
  FALSE POSITIVE: SPSHGzlOe8c window 4516-5133 (Robert Christopher Perez) —
    old flag said sentence_pronounced=True. Truth: reset to November 16, the
    judge pronounced NO sentence. Any classifier that calls this "sentenced" is
    broken.
  TRUE POSITIVE: 4zkUTUavW4I window 92-2169 (Anthony Blackburn) —
    "The court will sentence you to 3 years in the prison." Real sentence.
  A classifier that cannot separate these two is worthless, so both are asserted.

- [ ] G1 the classifier REJECTS the known false positive
    CHECK: python -W ignore tools/mine_slate.py --selftest
    EXPECT: G1_OK control_false_positive_rejected

- [ ] G2 the classifier ACCEPTS the known true positive
    CHECK: python -W ignore tools/mine_slate.py --selftest
    EXPECT: G2_OK control_true_positive_accepted

- [ ] G3 every hearing with footage is scored without crashing, and defendant
      speech share is measured rather than assumed
    CHECK: python -W ignore tools/mine_slate.py --score
    EXPECT: G3_OK scored=

- [ ] G4 nothing already published or scheduled reaches the slate
      (JgvW7oCQxuI = Thompson, 2XkPnvstmRQ = spider monkey, EwwnbiAQtFk = CARTHIEF)
    CHECK: python -W ignore tools/mine_slate.py --build
    EXPECT: G4_OK excluded_published=3

- [ ] G5 no two slate entries are the same case (same source video with
      overlapping windows collapses to one entry)
    CHECK: python -W ignore tools/mine_slate.py --build
    EXPECT: G5_OK no_duplicate_cases

- [ ] G6 the slate is written to disk and reports its true size honestly
    CHECK: python -W ignore tools/mine_slate.py --build
    EXPECT: G6_OK slate_written=

- [ ] G7 the Robert Castillo trial files are quarantined, not slated — eight
      files, one trial, no verdict in any of them
    CHECK: python -W ignore tools/mine_slate.py --build
    EXPECT: G7_OK castillo_quarantined=
