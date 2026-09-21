"""Sittings of one cause are disjoint; overlapping rows are the same sitting twice."""
from boydclips.state import coalesce_windows


def test_overlapping_rows_become_one_sitting():
    assert coalesce_windows([(8320.0, 8999.0), (8340.0, 9465.0)]) == [(8320.0, 9465.0)]


def test_disjoint_sittings_are_kept_in_order():
    rows = [(6698.0, 6958.0), (8279.0, 8843.0)]
    assert coalesce_windows(list(reversed(rows))) == rows


def test_touching_rows_merge_and_nested_rows_collapse():
    assert coalesce_windows([(10.0, 20.0), (20.0, 30.0)]) == [(10.0, 30.0)]
    assert coalesce_windows([(10.0, 50.0), (20.0, 30.0)]) == [(10.0, 50.0)]


def test_empty():
    assert coalesce_windows([]) == []
