"""Resolve a docket defendant to a Bexar SO number, then pull their real history.

THE POINT, and why the earlier "not safely reachable" verdict was wrong:
`defendantSONum` is an exact person key. Searching a bare SO number returns every
booking for that person and nothing else — verified 15/15, 14/14, 12/12 on three
separate numbers. So once you have the right SO number, priors are CERTAIN, not
probabilistic. There is no confidence problem at all on that side.

The only real question is which SO number belongs to the person in front of Judge
Boyd, and that is an ordinary disambiguation problem, not a wall:

  * ~20% of docket names return exactly one person. Done, no work needed.
  * The rest are resolved by BOOKING DATE. A 2025 cause number means the arrest
    happened in a narrow window, which eliminates the fourteen other Tony
    Rodriguezes who were booked in 1989, 2003, 2011...
  * Charge overlap against the case summary breaks the remaining ties.

Two routes that look obvious and are NOT available, both tested rather than
assumed:
  * The jail index does not contain court cause numbers. `2025CR001529` returns
    0 hits in any form — quoted, canonical, or field-scoped. The jail keys on its
    own booking numbers.
  * Cause numbers in our own DB are LLM-extracted from video and inconsistently
    formatted ("2025 CR0133", "2025 CR 013333"), so they cannot be trusted as an
    exact key even where one would work.

NEVER state priors from an UNRESOLVED match. On a monetised channel, attaching
the wrong person's record to a named defendant is the one mistake with real
consequences — and 314+ people in Bexar County share the name "Jose Garcia".
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from . import records

SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def strip_accents(s: str) -> str:
    """PEÑA -> PENA.

    The jail index stores names without diacritics, so a search for "peña"
    returns 1,894 unrelated rows and never the person, while "pena" returns
    PENA, ARNOLD as the first hit. On a Bexar County docket this is not an edge
    case — it silently loses a large share of Hispanic surnames.
    """
    return "".join(c for c in unicodedata.normalize("NFKD", s or "")
                   if not unicodedata.combining(c))

# Words that carry no discriminating power when comparing a charge description
# against a case summary.
_STOP = {"of", "the", "a", "an", "with", "and", "or", "to", "in", "on", "by",
         "for", "at", "from", "under", "over", "degree", "class", "state",
         "county", "felony", "misdemeanor", "offense", "charge", "count"}


def normalise_name(name: str) -> tuple[str, str] | None:
    """First and last token, suffixes and middle names dropped.

    Middle names and suffixes break the search: querying "Anthony Blackburn Sr."
    returns nothing while "Anthony Blackburn" returns eight bookings for one
    person. Measured, not assumed.
    """
    # The analyser writes its own annotations into the name field —
    # "J. Angel Flores (also rendered as ...)", "Jesus Vigil (transcribed as ...)".
    # Left in, they turn a findable person into "no jail record".
    name = strip_accents(name)
    name = re.sub(r"\(.*?\)|\[.*?\]", " ", name)
    name = re.split(r"\b(?:also|aka|a\.k\.a|transcribed|rendered|or)\b", name, flags=re.I)[0]

    toks = [t.strip(".,") for t in re.split(r"[\s,]+", name.lower()) if t.strip(".,")]
    toks = [t for t in toks if t not in SUFFIXES]
    # drop bare initials — "J. David Taylor" searches better as "david taylor"
    toks = [t for t in toks if len(t) > 1] or toks
    if len(toks) < 2:
        return None
    return toks[0], toks[-1]


def _hits(payload: dict[str, Any]) -> list[dict]:
    return payload.get("hits") or []


def _parse_dt(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).date()
    except Exception:
        return None


@dataclass
class Person:
    so: str
    name: str = ""
    dob: date | None = None
    bookings: list[dict] = field(default_factory=list)

    @property
    def booking_dates(self) -> list[date]:
        return sorted(d for d in (_parse_dt(b.get("bookingDate")) for b in self.bookings) if d)

    def charge_terms(self) -> set[str]:
        out: set[str] = set()
        for b in self.bookings:
            for ch in b.get("charges") or []:
                for w in re.split(r"[^a-z]+", str(ch.get("chargeDescription", "")).lower()):
                    if len(w) > 3 and w not in _STOP:
                        out.add(w)
        return out


def candidates(name: str, *, size: int = 50) -> dict[str, Person]:
    """Every distinct person in the jail system matching first+last name."""
    nm = normalise_name(name)
    if not nm:
        return {}
    first, last = nm
    try:
        res = records.jail_search(f"{first} {last}", size=size)
    except records.RecordsError:
        return {}

    people: dict[str, Person] = {}
    for h in _hits(res):
        so = str(h.get("defendantSONum") or "").strip()
        if not so:
            continue
        dn = str(h.get("defendantName", "")).lower()
        # the search is full-text OR, so it returns partial matches too
        if first not in dn or last not in dn:
            continue
        p = people.setdefault(so, Person(so=so, name=h.get("defendantName", ""),
                                         dob=_parse_dt(h.get("defendantDOB"))))
        p.bookings.append(h)
    return people


@dataclass
class Match:
    person: Person | None
    confidence: str            # "certain" | "high" | "none"
    reason: str
    n_candidates: int


def _split_court_name(court_name: str) -> tuple[str, str, list[str]] | None:
    """'SALAZAR, JOSE ISMAEL, JR' -> ('jose', 'salazar', ['ismael']).

    Also accepts plain 'First Middle Last'. The fallback path hands this function
    our own database's spoken-name string, which has no comma — rejecting it
    reported "unparseable court name" for people who simply were not on a roster
    we could pull, so they were never actually looked up.
    """
    # strip analyser annotations before anything else
    court_name = strip_accents(court_name or "")
    court_name = re.sub(r"\(.*?\)|\[.*?\]", " ", court_name)
    court_name = re.split(r"\b(?:also|aka|a\.k\.a|transcribed|rendered)\b",
                          court_name, flags=re.I)[0]

    parts = [p.strip() for p in court_name.split(",") if p.strip()]
    if not parts:
        return None

    if len(parts) > 1:                      # clerk format: LAST, FIRST MIDDLE
        last = parts[0].lower()
        given = [t.lower().strip(".") for p in parts[1:] for t in p.split()]
    else:                                   # plain format: First Middle Last
        toks = [t.lower().strip(".") for t in parts[0].split() if t.strip(".")]
        toks = [t for t in toks if t not in SUFFIXES]
        if len(toks) < 2:
            return None
        last, given = toks[-1], toks[:-1]

    given = [g for g in given if g and g not in SUFFIXES]
    if not given or not last:
        return None
    return given[0], last, given[1:]


def resolve_from_court(court_name: str, *, hearing_date: date | None = None) -> Match:
    """Resolve using the COURT's canonical name. This is the primary path.

    Why this beats matching the analyser's transcription: the hearings API returns
    the defendant exactly as the clerk has them — 'SALAZAR, JOSE ISMAEL, JR',
    'ANTHONY, ROGER WAYNE' — including the MIDDLE NAME. The middle name is the
    whole ballgame. Measured on one real Boyd docket:

        SALAZAR, JOSE ISMAEL   21 candidates -> 1
        ANTHONY, ROGER WAYNE   21 candidates -> 1
        WILLIAMS, KEVIN ARTHUR 12 candidates -> 1

    72% of a docket resolves this way against 20% matching first+last off the
    transcript. The transcript gives "Jose Salazar"; the clerk gives the person.
    Always start here, and only fall back to the transcript name if the case is
    not on a docket we can pull.
    """
    sp = _split_court_name(court_name)
    if not sp:
        return Match(None, "none", "unparseable court name", 0)
    first, last, middles = sp

    try:
        res = records.jail_search(f"{first} {last}", size=50)
    except records.RecordsError:
        return Match(None, "none", "jail search failed", 0)

    people: dict[str, Person] = {}
    for h in _hits(res):
        so = str(h.get("defendantSONum") or "").strip()
        dn = str(h.get("defendantName", "")).lower()
        if not so or first not in dn or last not in dn:
            continue
        p = people.setdefault(so, Person(so=so, name=h.get("defendantName", ""),
                                         dob=_parse_dt(h.get("defendantDOB"))))
        p.bookings.append(h)

    n0 = len(people)
    if n0 == 0:
        return Match(None, "none", "no jail record for this name", 0)
    if n0 == 1:
        return Match(next(iter(people.values())), "certain", "unique name", 1)

    # 1. the middle name from the clerk's record
    if middles:
        narrowed = {so: p for so, p in people.items()
                    if all(m in p.name.lower() for m in middles)}
        if len(narrowed) == 1:
            return Match(next(iter(narrowed.values())), "certain",
                         f"middle name narrowed {n0} candidates to 1", n0)
        if narrowed:
            people = narrowed

    # 2. in custody on the day of the hearing — deterministic when it applies,
    #    but most felony defendants appear on bond, so it only catches some
    if hearing_date and len(people) > 1:
        inside = []
        for p in people.values():
            for b in p.bookings:
                bd = _parse_dt(b.get("bookingDate"))
                rd = _parse_dt(b.get("releaseDate"))
                if bd and bd <= hearing_date and (rd is None or rd >= hearing_date):
                    inside.append(p)
                    break
        if len(inside) == 1:
            return Match(inside[0], "certain",
                         "only candidate in custody on the hearing date", n0)

    return Match(None, "none",
                 f"{len(people)} candidates remain after middle name and custody", n0)


def resolve(name: str, *, hearing_date: date | None = None,
            summary: str = "", window_years: int = 4) -> Match:
    """Pick the one person in front of the judge, or refuse."""
    people = candidates(name)
    n = len(people)
    if n == 0:
        return Match(None, "none", "no jail record for this name", 0)
    if n == 1:
        p = next(iter(people.values()))
        return Match(p, "certain", "name is unique in Bexar County", 1)

    pool = list(people.values())

    # 1. booking-date window — the strongest filter. Someone sentenced in 2026
    #    was not arrested for it in 1989.
    if hearing_date:
        lo = hearing_date - timedelta(days=365 * window_years)
        near = [p for p in pool if any(lo <= d <= hearing_date for d in p.booking_dates)]
        if len(near) == 1:
            return Match(near[0], "high",
                         f"only 1 of {n} same-name people was booked within "
                         f"{window_years}y before the hearing", n)
        if near:
            pool = near

    # 2. charge overlap against the case summary
    if summary and len(pool) > 1:
        want = {w for w in re.split(r"[^a-z]+", summary.lower())
                if len(w) > 3 and w not in _STOP}
        scored = sorted(((len(p.charge_terms() & want), p) for p in pool),
                        key=lambda t: t[0], reverse=True)
        if scored[0][0] >= 2 and scored[0][0] > scored[1][0]:
            return Match(scored[0][1], "high",
                         f"charge overlap ({scored[0][0]} terms) beat "
                         f"{len(pool)-1} other same-name candidate(s)", n)

    return Match(None, "none",
                 f"{len(pool)} same-name people could not be separated", n)


def history(so: str, *, size: int = 100) -> list[dict]:
    """Every booking for one SO number. This part is exact — same key, same system."""
    try:
        res = records.jail_search(str(so), size=size)
    except records.RecordsError:
        return []
    return [h for h in _hits(res) if str(h.get("defendantSONum") or "") == str(so)]


def summarise(so: str, *, before: date | None = None) -> dict[str, Any]:
    """Broadcast-safe summary of one person's prior bookings.

    `before` excludes the current case's own booking so "priors" means priors.
    """
    bk = history(so)
    rows = []
    for b in bk:
        d = _parse_dt(b.get("bookingDate"))
        if before and d and d >= before:
            continue
        rows.append({
            "date": d.isoformat() if d else None,
            "agency": ((b.get("arrests") or [{}])[0]).get("arrestingAgency"),
            "charges": [c.get("chargeDescription") for c in (b.get("charges") or [])],
        })
    rows.sort(key=lambda r: r["date"] or "")
    charges = [c for r in rows for c in r["charges"] if c]
    return {
        "so": so,
        "prior_bookings": len(rows),
        "first": rows[0]["date"] if rows else None,
        "last": rows[-1]["date"] if rows else None,
        "distinct_charges": sorted({c for c in charges}),
        "bookings": rows,
    }


# --------------------------------------------------------------- the real path
def _d(s: Any) -> date | None:
    if not s:
        return None
    t = str(s)
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(t[:10], fmt).date()
        except Exception:
            pass
    return _parse_dt(t)


def resolve_from_case(court_name: str, encrypted_case_id: str,
                      case_load_url: str | None = None) -> Match:
    """Resolve a defendant to their SID (= SO number) using the court's own dates.

    THIS IS THE DETERMINISTIC PATH and it should be tried before anything else.

    The Register of Actions carries, inside the bond block, the defendant's
    `ArrestDate` and `InmateReleaseDate` for this case. The jail system stores the
    same two dates against a booking. A release date pins one person:

        court : ArrestDate 07/21/2025   InmateReleaseDate 11/03/2025
        jail  : SID 874064  WILLIAMS, KEVIN ARTHUR  booked 07/22  released 11/03

    Note the one-day offset on arrest vs booking — they are separate events, so
    arrest is matched with a tolerance and release is matched exactly. That
    distinction matters: a decoy (KEVIN RAY WILLIAMS, booked 07/18, released
    07/22) sits inside the arrest tolerance and is excluded only by the release
    date.

    Falls back to resolve_from_court() when a case has no bond record — cases
    where the defendant was never released have no InmateReleaseDate.
    """
    try:
        detail = records.case_detail(encrypted_case_id, case_load_url)
    except Exception:
        return resolve_from_court(court_name)

    windows = records.case_arrest_windows(detail)
    sp = _split_court_name(court_name)
    if not sp or not windows:
        return resolve_from_court(court_name)
    first, last, _ = sp

    try:
        res = records.jail_search(f"{first} {last}", size=50)
    except records.RecordsError:
        return Match(None, "none", "jail search failed", 0)

    people: dict[str, Person] = {}
    for h in _hits(res):
        so = str(h.get("defendantSONum") or "").strip()
        dn = str(h.get("defendantName", "")).lower()
        if not so or first not in dn or last not in dn:
            continue
        p = people.setdefault(so, Person(so=so, name=h.get("defendantName", ""),
                                         dob=_parse_dt(h.get("defendantDOB"))))
        p.bookings.append(h)
    if not people:
        return Match(None, "none", "no jail record for this name", 0)

    for w in windows:
        wa, wr = _d(w.get("arrest")), _d(w.get("release"))
        for p in people.values():
            for b in p.bookings:
                bd, rd = _d(b.get("bookingDate")), _d(b.get("releaseDate"))
                # release date is exact; arrest tolerates the arrest->booking gap
                if wr and rd and wr == rd:
                    return Match(p, "certain",
                                 f"court release date {wr} matches booking exactly", len(people))
                if wa and bd and abs((bd - wa).days) <= 2 and not wr:
                    return Match(p, "certain",
                                 f"court arrest date {wa} matches booking {bd}", len(people))

    return resolve_from_court(court_name)
