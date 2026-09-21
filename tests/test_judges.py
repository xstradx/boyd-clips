"""The multi-judge source registry: config/judges.yaml + src/boydclips/judges.py.

These tests read one YAML file and validate it. No network access, no
downloading, no generation, and nothing in the existing pipeline is touched.
The negative controls below are the point of the module: none of them may ever
let a search hit or a third-party clip channel reach production.
"""
from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from boydclips import judges

BOYD_URL = "https://www.youtube.com/@judgestephanieboyd4233/streams"
WEST_URL = "https://www.youtube.com/channel/UCi6scjUsERAUv8P74BPM4_g/streams"

EXPECTED_IDS = ["stephanie_boyd", "cedric_simpson", "david_fleischer", "raquel_west"]
EXPECTED_NAMES = {
    "stephanie_boyd": "Judge Stephanie Boyd",
    "cedric_simpson": "Judge J. Cedric Simpson",
    "david_fleischer": "Judge David Fleischer",
    "raquel_west": "Judge Raquel West",
}
DISCOVERY_ONLY_IDS = ["cedric_simpson", "david_fleischer"]

RAW = yaml.safe_load(judges.DEFAULT_PATH.read_text(encoding="utf-8"))


def _data() -> dict:
    """A mutable copy of the shipped registry, so a test never edits the file."""
    return copy.deepcopy(RAW)


def _row(data: dict, judge_id: str) -> dict:
    for row in data["judges"]:
        if row["id"] == judge_id:
            return row
    raise AssertionError(f"{judge_id!r} is not in the registry under test")


def _write(tmp_path: Path, data) -> Path:
    path = tmp_path / "judges.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


# ------------------------------------------------------------------ the profiles


def test_all_four_profiles_load():
    profiles = judges.load_profiles()
    assert [p.id for p in profiles] == EXPECTED_IDS
    assert len(profiles) == 4
    assert all(p.discovery for p in profiles)


def test_display_names_are_exact():
    profiles = {p.id: p for p in judges.load_profiles()}
    assert set(profiles) == set(EXPECTED_NAMES)
    for judge_id, name in EXPECTED_NAMES.items():
        assert profiles[judge_id].display_name == name
        assert name.startswith("Judge ")


def test_boyd_stays_primary_and_production_enabled():
    boyd = judges.get_profile("stephanie_boyd")
    assert boyd.primary is True
    assert boyd.production_enabled is True
    assert boyd.source_review_required is False
    assert boyd.court == "187th District Court, Bexar County, Texas"
    assert boyd.jurisdiction == "Bexar County, Texas"
    assert boyd.court_source_urls == (BOYD_URL,)
    assert boyd.production_ready is True
    assert judges.primary_judge().id == "stephanie_boyd"
    assert "stephanie_boyd" in [p.id for p in judges.production_profiles()]


def test_boyd_url_is_the_one_the_pipeline_already_uses():
    from boydclips.config import load_config

    cfg = load_config()
    assert cfg.get("source.channel_url") == BOYD_URL
    assert cfg.get("source.court") == judges.get_profile("stephanie_boyd").court


def test_west_is_court_owned_but_pipeline_held():
    west = judges.get_profile("raquel_west")
    assert west.production_enabled is False
    assert west.source_review_required is False
    assert west.production_ready is False
    assert west.court == "252nd District Court, Jefferson County, Texas"
    assert "Jefferson" in west.jurisdiction
    assert [e.url for e in west.direct_urls] == [WEST_URL]
    assert [e.source_owner for e in west.direct_urls] == ["court"]


def test_simpson_and_fleischer_are_discovery_only():
    profiles = {p.id: p for p in judges.load_profiles()}
    for judge_id in DISCOVERY_ONLY_IDS:
        profile = profiles[judge_id]
        assert profile.production_enabled is False, judge_id
        assert profile.source_review_required is True, judge_id
        assert profile.production_ready is False, judge_id
        assert profile.court_source_urls == (), judge_id
        assert profile.direct_urls == (), judge_id
        assert profile.queries, judge_id
        for entry in profile.queries:
            assert entry.source_owner == "unverified"
            assert entry.query.strip()
            assert 1 <= entry.max_results <= 50


def test_fleischer_identity_is_exact_but_source_remains_held():
    fleischer = judges.get_profile("david_fleischer")
    assert fleischer.display_name == "Judge David Fleischer"
    assert fleischer.court == "Harris County Criminal Court at Law No. 5, Harris County, Texas"
    assert fleischer.jurisdiction == "Harris County, Texas"
    assert fleischer.production_enabled is False
    assert fleischer.source_review_required is True


def test_only_boyd_is_production_enabled_until_pipeline_is_profile_aware():
    enabled = {p.id for p in judges.load_profiles() if p.production_enabled}
    assert enabled == {"stephanie_boyd"}
    assert [p.id for p in judges.production_profiles()] == ["stephanie_boyd"]


# ---------------------------------------------------------------- discovery views


def test_discovery_targets_cover_direct_urls_and_bounded_queries():
    targets = judges.discovery_targets()
    urls = {t.url for t in targets if t.kind == "direct_url"}
    assert urls == {BOYD_URL, WEST_URL}

    for target in targets:
        if target.kind == "query":
            assert target.url is None
            assert target.query and target.query.strip()
            assert isinstance(target.max_results, int)
            assert 1 <= target.max_results <= 50
            assert target.production_ready is False, target.judge_id
        else:
            assert target.url and target.url.startswith("https://")
            assert target.query is None

    ready = {(t.judge_id, t.url) for t in targets if t.production_ready}
    assert ready == {("stephanie_boyd", BOYD_URL)}


def test_a_third_party_entry_is_listed_but_never_production_ready():
    data = _data()
    _row(data, "stephanie_boyd")["discovery"].append(
        {
            "kind": "direct_url",
            "url": "https://www.youtube.com/@CourtroomFleischerTV/videos",
            "source_owner": "third_party",
            "note": "competitor edit channel, evidence only",
        }
    )
    profiles = judges.parse_profiles(data)
    third_party = [e for p in profiles for e in p.direct_urls
                   if e.source_owner == "third_party"]
    assert third_party, "the third-party entry should still be recorded"
    assert all(e.production_ready is False for e in third_party)


def test_discovery_only_profiles_contribute_no_production_target():
    targets = [t for t in judges.discovery_targets() if t.judge_id in DISCOVERY_ONLY_IDS]
    assert targets
    assert all(t.production_ready is False for t in targets)
    assert all(t.source_review_required is True for t in targets)
    assert all(t.kind == "query" for t in targets)


# --------------------------------------------------------------- negative controls


def test_pipeline_discovers_west_and_stamps_her_on_every_docket(monkeypatch):
    """West is production-DISABLED but court-sourced, so explicit local
    discovery must work for her and every row must name her. Nothing is
    downloaded here: the listing call is replaced with a fixture."""
    from boydclips import discover, pipeline
    from boydclips.config import load_config

    calls: dict[str, object] = {}

    def fake_list_recent(channel_url, depth, judge_id=discover.DEFAULT_JUDGE_ID,
                         judge_name=discover.DEFAULT_JUDGE_NAME):
        calls.update(channel_url=channel_url, depth=depth,
                     judge_id=judge_id, judge_name=judge_name)
        return [
            discover.Docket("west-docket-1", "THURS., SEPT 17, 2026/JUDGE RAQUEL WEST/"
                           "252ND DISTRICT COURT/AFTERNOON DOCKET", 3600.0,
                           "2026-09-17", "afternoon",
                           judge_id=judge_id, judge_name=judge_name),
            discover.Docket("west-docket-2", "live", 1800.0, "", "unknown",
                            judge_id=judge_id, judge_name=judge_name),
        ]

    monkeypatch.setattr(discover, "list_recent", fake_list_recent)
    pipe = pipeline.Pipeline.__new__(pipeline.Pipeline)
    pipe.cfg = load_config()

    dockets = pipe.discover_judge("raquel_west")

    assert judges.get_profile("raquel_west").production_enabled is False
    assert calls["channel_url"] == WEST_URL
    assert calls["judge_id"] == "raquel_west"
    assert calls["judge_name"] == "Judge Raquel West"
    assert [d.video_id for d in dockets] == ["west-docket-1", "west-docket-2"]
    assert {d.judge_id for d in dockets} == {"raquel_west"}
    assert {d.judge_name for d in dockets} == {"Judge Raquel West"}


def test_pipeline_refuses_query_only_profiles_without_scanning(monkeypatch):
    """A search is a lead, not a source: Simpson and Fleischer must be refused
    before any listing happens, and an unknown id must not silently default to
    Boyd."""
    from boydclips import discover, pipeline
    from boydclips.config import load_config

    scanned: list[tuple] = []
    monkeypatch.setattr(discover, "list_recent",
                        lambda *args, **kwargs: scanned.append(args) or [])
    pipe = pipeline.Pipeline.__new__(pipeline.Pipeline)
    pipe.cfg = load_config()

    assert issubclass(pipeline.JudgeSourceNotVerified, judges.RegistryError)
    for judge_id in DISCOVERY_ONLY_IDS:
        with pytest.raises(pipeline.JudgeSourceNotVerified, match="court-owned direct source"):
            pipe.discover_judge(judge_id)
    with pytest.raises(judges.JudgeNotFound):
        pipe.discover_judge("judge_does_not_exist")
    assert scanned == [], "a refused profile must not be listed at all"

    # production_enabled semantics are untouched by this layer
    assert {p.id for p in judges.load_profiles() if p.production_enabled} == {"stephanie_boyd"}


def test_duplicate_ids_are_rejected(tmp_path):
    data = _data()
    duplicate = copy.deepcopy(_row(data, "stephanie_boyd"))
    duplicate["display_name"] = "Judge Stephanie Boyd (copy)"
    data["judges"].append(duplicate)
    with pytest.raises(judges.RegistryError, match="duplicate judge id"):
        judges.parse_profiles(data)
    with pytest.raises(judges.RegistryError, match="duplicate judge id"):
        judges.load_profiles(_write(tmp_path, data))


def test_missing_required_fields_are_rejected():
    for field_name in ("id", "display_name", "court", "jurisdiction",
                       "production_enabled", "source_review_required", "discovery"):
        data = _data()
        del _row(data, "raquel_west")[field_name]
        with pytest.raises(judges.RegistryError, match=field_name):
            judges.parse_profiles(data)


def test_production_enabled_without_direct_source_url_is_rejected():
    data = _data()
    row = _row(data, "raquel_west")
    row["production_enabled"] = True
    row["discovery"] = [
        {
            "kind": "query",
            "query": "Judge Raquel West 252nd District Court full hearing",
            "max_results": 25,
            "source_owner": "unverified",
        }
    ]
    assert row["production_enabled"] is True
    with pytest.raises(judges.RegistryError, match="no court-owned direct source"):
        judges.parse_profiles(data)


def test_production_enabled_with_only_a_third_party_url_is_rejected():
    data = _data()
    row = _row(data, "raquel_west")
    row["production_enabled"] = True
    row["discovery"][0]["source_owner"] = "third_party"
    with pytest.raises(judges.RegistryError, match="no court-owned direct source"):
        judges.parse_profiles(data)


def test_source_review_required_cannot_be_production_enabled():
    data = _data()
    _row(data, "david_fleischer")["production_enabled"] = True
    with pytest.raises(judges.RegistryError, match="source_review_required"):
        judges.parse_profiles(data)


def test_query_entries_must_be_bounded():
    for bad in (None, 0, 51, 25.0, "25", True):
        data = _data()
        _row(data, "cedric_simpson")["discovery"][0]["max_results"] = bad
        with pytest.raises(judges.RegistryError, match="max_results"):
            judges.parse_profiles(data)


def test_query_cannot_claim_a_court_owner_before_review():
    data = _data()
    _row(data, "cedric_simpson")["discovery"][0]["source_owner"] = "court"
    with pytest.raises(judges.RegistryError, match="a search is not a source"):
        judges.parse_profiles(data)


def test_direct_url_must_be_an_http_url():
    for bad in ("ytsearch:judge", "www.youtube.com/@judge", "", "  "):
        data = _data()
        _row(data, "raquel_west")["discovery"][0]["url"] = bad
        with pytest.raises(judges.RegistryError):
            judges.parse_profiles(data)


def test_direct_url_owner_must_be_known():
    data = _data()
    _row(data, "raquel_west")["discovery"][0]["source_owner"] = "unverified"
    with pytest.raises(judges.RegistryError, match="source_owner"):
        judges.parse_profiles(data)


def test_unknown_entry_kind_is_rejected():
    data = _data()
    _row(data, "raquel_west")["discovery"][0]["kind"] = "channel"
    with pytest.raises(judges.RegistryError, match="kind must be"):
        judges.parse_profiles(data)


def test_primary_must_be_unique_and_boyd():
    no_primary = _data()
    del _row(no_primary, "stephanie_boyd")["primary"]
    with pytest.raises(judges.RegistryError, match="exactly one profile"):
        judges.parse_profiles(no_primary)

    two_primaries = _data()
    _row(two_primaries, "raquel_west")["primary"] = True
    with pytest.raises(judges.RegistryError, match="exactly one profile"):
        judges.parse_profiles(two_primaries)

    other_primary = _data()
    del _row(other_primary, "stephanie_boyd")["primary"]
    _row(other_primary, "raquel_west")["primary"] = True
    with pytest.raises(judges.RegistryError, match="primary production judge"):
        judges.parse_profiles(other_primary)


def test_primary_judge_must_stay_production_enabled():
    data = _data()
    row = _row(data, "stephanie_boyd")
    row["production_enabled"] = False
    row["source_review_required"] = True
    with pytest.raises(judges.RegistryError, match="production-enabled"):
        judges.parse_profiles(data)


def test_registry_shape_controls():
    with pytest.raises(judges.RegistryError, match="non-empty list"):
        judges.parse_profiles({"judges": []})
    with pytest.raises(judges.RegistryError, match="missing required top-level key"):
        judges.parse_profiles({})
    with pytest.raises(judges.RegistryError, match="top level must be a mapping"):
        judges.parse_profiles(["stephanie_boyd"])


def test_missing_registry_file_is_a_registry_error(tmp_path):
    with pytest.raises(judges.RegistryError, match="not found"):
        judges.load_profiles(tmp_path / "absent.yaml")


def test_malformed_yaml_is_a_registry_error(tmp_path):
    path = tmp_path / "judges.yaml"
    path.write_text("judges: [ {id: 'x',\n", encoding="utf-8")
    with pytest.raises(judges.RegistryError, match="not valid YAML"):
        judges.load_profiles(path)


def test_explicit_path_loads_the_same_registry(tmp_path):
    path = _write(tmp_path, _data())
    assert [p.id for p in judges.load_profiles(path)] == EXPECTED_IDS
    assert judges.get_profile("raquel_west", path).court_source_urls == (WEST_URL,)


def test_unknown_id_raises_judge_not_found():
    with pytest.raises(judges.JudgeNotFound) as excinfo:
        judges.get_profile("judge_does_not_exist")
    assert isinstance(excinfo.value, KeyError)
    assert "judge_does_not_exist" in str(excinfo.value)


def test_default_path_points_at_the_repo_registry():
    assert judges.DEFAULT_PATH == Path(judges.ROOT) / "config" / "judges.yaml"
    assert judges.DEFAULT_PATH.exists()
