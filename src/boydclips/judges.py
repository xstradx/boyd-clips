"""The multi-judge source registry.

WHY THIS EXISTS
The daily pipeline clips exactly one docket: Judge Stephanie Boyd's 187th
District Court feed, hardcoded in ``config/pipeline.yaml``. Courtroom channels
now circulate three other judges heavily (J. Cedric Simpson, David Fleischer,
Raquel West) and the repo already holds a pile of evidence that most of that
material is third-party editing: ``data/channel_catalog.json`` carries
``#judgefleischer`` edits and ``config/cases.json`` records the clip channel
"Courtroom Justice TV" / ``@CourtroomFleischerTV``. A judge name in a video
title is not a source.

This module keeps that distinction in data instead of in prose. Every judge is
one profile in ``config/judges.yaml`` with a stable id, the court that owns the
docket, and discovery entries that say whether they are a direct source or a
bounded search. The loader is strict on purpose: it refuses to return a
registry in which unverified material could be treated as production-ready.

THE RULES, AND WHY EACH ONE IS A REFUSAL RATHER THAN A WARNING
  * Duplicate ids silently collapse to one profile, so ``get_profile`` would
    return whichever row happened to be last.
  * A ``production_enabled`` profile with no court-owned ``direct_url`` is a
    profile whose only "source" is a search. Search hits for these judges are
    edited competitor clips, and ``source_owner: third_party`` entries are
    never production-ready - the flag would be a lie.
  * ``source_review_required`` plus ``production_enabled`` contradict each
    other; one of the two is wrong and only a human can say which.
  * A search is not a source, so a ``query`` entry may not claim a court owner
    before review has happened.

WHAT THIS MODULE DOES NOT DO
No network access, no downloading, no generation. It reads the YAML file and
validates it. Nothing in the existing pipeline is wired to it yet.

  python -c "from boydclips import judges; print(judges.discovery_targets())"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml

from .config import ROOT

DEFAULT_PATH = ROOT / "config" / "judges.yaml"

# Judge Boyd stays the primary production judge until Nathan says otherwise.
PRIMARY_JUDGE_ID = "stephanie_boyd"

DIRECT_URL = "direct_url"
QUERY = "query"
ENTRY_KINDS = (DIRECT_URL, QUERY)

COURT_OWNED = "court"
THIRD_PARTY = "third_party"
UNVERIFIED = "unverified"
DIRECT_URL_OWNERS = (COURT_OWNED, THIRD_PARTY)

# A discovery search has to be bounded, or "find more judges" becomes an
# unbounded scrape of YouTube's whole catalogue.
MIN_QUERY_RESULTS = 1
MAX_QUERY_RESULTS = 50

REQUIRED_TEXT_FIELDS = ("id", "display_name", "court", "jurisdiction")
REQUIRED_BOOL_FIELDS = ("production_enabled", "source_review_required")


class RegistryError(ValueError):
    """The registry is missing, malformed, or breaks a production rule."""


class JudgeNotFound(KeyError):
    """No profile with that id is registered."""


@dataclass(frozen=True)
class DiscoveryEntry:
    """One place we may look for a judge's material, direct or by search."""

    kind: str
    source_owner: str
    note: str = ""
    url: str | None = None
    query: str | None = None
    max_results: int | None = None

    @property
    def production_ready(self) -> bool:
        """Only a court-owned direct URL is production material.

        A search hit is a lead: for these judges the hits are overwhelmingly
        edited competitor clips, so a query never carries production authority.
        """
        return self.kind == DIRECT_URL and self.source_owner == COURT_OWNED

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "source_owner": self.source_owner,
            "url": self.url,
            "query": self.query,
            "max_results": self.max_results,
            "production_ready": self.production_ready,
            "note": self.note,
        }


@dataclass(frozen=True)
class JudgeProfile:
    """One judge, one court, and every source we are allowed to look at."""

    id: str
    display_name: str
    court: str
    jurisdiction: str
    production_enabled: bool
    source_review_required: bool
    discovery: tuple[DiscoveryEntry, ...]
    primary: bool = False
    identity_reference: Mapping[str, Any] | str | None = field(default=None, compare=False)
    notes: str = field(default="", compare=False)

    @property
    def direct_urls(self) -> tuple[DiscoveryEntry, ...]:
        return tuple(e for e in self.discovery if e.kind == DIRECT_URL)

    @property
    def queries(self) -> tuple[DiscoveryEntry, ...]:
        return tuple(e for e in self.discovery if e.kind == QUERY)

    @property
    def court_source_urls(self) -> tuple[str, ...]:
        return tuple(e.url for e in self.direct_urls if e.source_owner == COURT_OWNED)

    @property
    def production_ready(self) -> bool:
        """Enabled, reviewed, and backed by at least one court-owned URL."""
        return (
            self.production_enabled
            and not self.source_review_required
            and bool(self.court_source_urls)
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "court": self.court,
            "jurisdiction": self.jurisdiction,
            "primary": self.primary,
            "production_enabled": self.production_enabled,
            "source_review_required": self.source_review_required,
            "production_ready": self.production_ready,
            "court_source_urls": list(self.court_source_urls),
            "identity_reference": self.identity_reference,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class DiscoveryTarget:
    """A profile's discovery entry, flattened for the caller that scans it."""

    judge_id: str
    display_name: str
    kind: str
    source_owner: str
    production_ready: bool
    source_review_required: bool
    url: str | None = None
    query: str | None = None
    max_results: int | None = None
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "judge_id": self.judge_id,
            "display_name": self.display_name,
            "kind": self.kind,
            "source_owner": self.source_owner,
            "url": self.url,
            "query": self.query,
            "max_results": self.max_results,
            "production_ready": self.production_ready,
            "source_review_required": self.source_review_required,
            "note": self.note,
        }


# --------------------------------------------------------------------- parsing


def _text(raw: Mapping[str, Any], key: str, where: str) -> str:
    value = raw.get(key)
    if value is None:
        raise RegistryError(f"{where}: missing required field {key!r}")
    if not isinstance(value, str) or not value.strip():
        raise RegistryError(f"{where}: {key} must be a non-empty string")
    return value.strip()


def _optional_text(raw: Mapping[str, Any], key: str, where: str) -> str:
    value = raw.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise RegistryError(f"{where}: {key} must be a string when present")
    return value.strip()


def _flag(raw: Mapping[str, Any], key: str, where: str) -> bool:
    value = raw.get(key)
    if value is None:
        raise RegistryError(f"{where}: missing required field {key!r}")
    if not isinstance(value, bool):
        raise RegistryError(f"{where}: {key} must be true or false, got {value!r}")
    return value


def _parse_entry(raw: Any, where: str) -> DiscoveryEntry:
    if not isinstance(raw, Mapping):
        raise RegistryError(f"{where}: each discovery entry must be a mapping")

    kind = _text(raw, "kind", where)
    if kind not in ENTRY_KINDS:
        raise RegistryError(
            f"{where}: kind must be one of {ENTRY_KINDS}, got {kind!r}"
        )
    owner = _text(raw, "source_owner", where)
    note = _optional_text(raw, "note", where)

    if kind == DIRECT_URL:
        url = _text(raw, "url", where)
        if not url.startswith(("http://", "https://")):
            raise RegistryError(f"{where}: url must be an http(s) URL, got {url!r}")
        if owner not in DIRECT_URL_OWNERS:
            raise RegistryError(
                f"{where}: a direct_url source_owner must be one of "
                f"{DIRECT_URL_OWNERS}, got {owner!r}. Use a query entry until the "
                "source owner is established."
            )
        return DiscoveryEntry(kind=kind, source_owner=owner, note=note, url=url)

    query = _text(raw, "query", where)
    max_results = raw.get("max_results")
    if isinstance(max_results, bool) or not isinstance(max_results, int):
        raise RegistryError(
            f"{where}: a query entry needs an integer max_results bound "
            f"({MIN_QUERY_RESULTS}..{MAX_QUERY_RESULTS}), got {max_results!r}"
        )
    if not MIN_QUERY_RESULTS <= max_results <= MAX_QUERY_RESULTS:
        raise RegistryError(
            f"{where}: max_results must be between {MIN_QUERY_RESULTS} and "
            f"{MAX_QUERY_RESULTS}, got {max_results}"
        )
    if owner != UNVERIFIED:
        raise RegistryError(
            f"{where}: a search is not a source - query entries must use "
            f"source_owner {UNVERIFIED!r}, got {owner!r}"
        )
    return DiscoveryEntry(
        kind=kind,
        source_owner=owner,
        note=note,
        query=query,
        max_results=max_results,
    )


def _parse_profile(raw: Any, where: str) -> JudgeProfile:
    if not isinstance(raw, Mapping):
        raise RegistryError(f"{where}: each profile must be a mapping")

    for key in REQUIRED_TEXT_FIELDS:
        _text(raw, key, where)
    for key in REQUIRED_BOOL_FIELDS:
        _flag(raw, key, where)

    judge_id = _text(raw, "id", where)
    if not judge_id.replace("_", "").isalnum() or judge_id.lower() != judge_id:
        raise RegistryError(
            f"{where}: id {judge_id!r} must be a stable lowercase slug "
            "(letters, digits and underscores)"
        )

    discovery_raw = raw.get("discovery")
    if discovery_raw is None:
        raise RegistryError(f"{where}: missing required field 'discovery'")
    if not isinstance(discovery_raw, list) or not discovery_raw:
        raise RegistryError(f"{where}: discovery must be a non-empty list")
    discovery = tuple(
        _parse_entry(entry, f"{where}.discovery[{i}]")
        for i, entry in enumerate(discovery_raw)
    )

    primary = raw.get("primary", False)
    if not isinstance(primary, bool):
        raise RegistryError(f"{where}: primary must be true or false when present")

    identity_reference = raw.get("identity_reference")
    if identity_reference is not None and not isinstance(
        identity_reference, (str, Mapping)
    ):
        raise RegistryError(
            f"{where}: identity_reference must be a string or a mapping when present"
        )

    profile = JudgeProfile(
        id=judge_id,
        display_name=_text(raw, "display_name", where),
        court=_text(raw, "court", where),
        jurisdiction=_text(raw, "jurisdiction", where),
        production_enabled=_flag(raw, "production_enabled", where),
        source_review_required=_flag(raw, "source_review_required", where),
        discovery=discovery,
        primary=primary,
        identity_reference=identity_reference,
        notes=_optional_text(raw, "notes", where),
    )
    return _validate_profile(profile, where)


def _validate_profile(profile: JudgeProfile, where: str) -> JudgeProfile:
    if profile.production_enabled and profile.source_review_required:
        raise RegistryError(
            f"{where}: profile {profile.id!r} is production_enabled and "
            "source_review_required at once; one of the two is wrong"
        )
    if profile.production_enabled and not profile.court_source_urls:
        raise RegistryError(
            f"{where}: production-enabled profile {profile.id!r} has no "
            "court-owned direct source URL. A query is not a source, and "
            "third-party clip channels are never production-ready."
        )
    return profile


def parse_profiles(data: Any, *, source: str = "judges.yaml") -> list[JudgeProfile]:
    """Validate already-parsed registry data. Strict, and total: raises or returns."""
    if not isinstance(data, Mapping):
        raise RegistryError(f"{source}: top level must be a mapping with a 'judges' list")

    raw_judges = data.get("judges")
    if raw_judges is None:
        raise RegistryError(f"{source}: missing required top-level key 'judges'")
    if not isinstance(raw_judges, list) or not raw_judges:
        raise RegistryError(f"{source}: 'judges' must be a non-empty list")

    profiles: list[JudgeProfile] = []
    for index, raw in enumerate(raw_judges):
        profiles.append(_parse_profile(raw, f"{source}:judges[{index}]"))

    seen: dict[str, JudgeProfile] = {}
    for profile in profiles:
        if profile.id in seen:
            raise RegistryError(
                f"{source}: duplicate judge id {profile.id!r}; ids must be unique "
                "because lookups and story records key off them"
            )
        seen[profile.id] = profile

    primaries = [p for p in profiles if p.primary]
    if len(primaries) != 1:
        raise RegistryError(
            f"{source}: exactly one profile must be marked primary: true, "
            f"found {len(primaries)} ({[p.id for p in primaries]})"
        )
    primary = primaries[0]
    if primary.id != PRIMARY_JUDGE_ID:
        raise RegistryError(
            f"{source}: the primary production judge must be {PRIMARY_JUDGE_ID!r}, "
            f"got {primary.id!r}"
        )
    if not primary.production_enabled:
        raise RegistryError(
            f"{source}: the primary judge {primary.id!r} must stay production-enabled"
        )

    return profiles


# --------------------------------------------------------------- public loading


def load_profiles(path: Path | str | None = None) -> list[JudgeProfile]:
    """Load every profile from config/judges.yaml (or an explicit path)."""
    config_path = Path(path) if path is not None else DEFAULT_PATH
    if not config_path.exists():
        raise RegistryError(f"judge registry not found: {config_path}")
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RegistryError(f"{config_path}: not valid YAML: {exc}") from exc
    return parse_profiles(data, source=str(config_path))


def get_profile(judge_id: str, path: Path | str | None = None) -> JudgeProfile:
    """Return one profile by id. Raises JudgeNotFound if it is not registered."""
    for profile in load_profiles(path):
        if profile.id == judge_id:
            return profile
    registered = ", ".join(p.id for p in load_profiles(path))
    raise JudgeNotFound(f"no judge profile with id {judge_id!r}; registered: {registered}")


def production_profiles(path: Path | str | None = None) -> list[JudgeProfile]:
    """Every profile currently cleared to produce clips."""
    return [p for p in load_profiles(path) if p.production_enabled]


def discovery_targets(path: Path | str | None = None) -> list[DiscoveryTarget]:
    """Every discovery entry, flattened, with its effective production status.

    The effective flag is the profile's clearance AND the entry's own owner: a
    query entry, or any third-party clip channel, comes back
    ``production_ready=False`` no matter which profile it hangs off.
    """
    targets: list[DiscoveryTarget] = []
    for profile in load_profiles(path):
        cleared = profile.production_ready
        for entry in profile.discovery:
            targets.append(
                DiscoveryTarget(
                    judge_id=profile.id,
                    display_name=profile.display_name,
                    kind=entry.kind,
                    source_owner=entry.source_owner,
                    production_ready=cleared and entry.production_ready,
                    source_review_required=profile.source_review_required,
                    url=entry.url,
                    query=entry.query,
                    max_results=entry.max_results,
                    note=entry.note,
                )
            )
    return targets


def primary_judge(path: Path | str | None = None) -> JudgeProfile:
    """The primary production judge (Judge Stephanie Boyd)."""
    return get_profile(PRIMARY_JUDGE_ID, path)
