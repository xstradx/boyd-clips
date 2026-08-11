"""Bexar County public-records clients.

Endpoint map and observed behaviour: spec/RECORDS-API.md. Everything here runs
unauthenticated and headless — no browser, no login. Endpoints that are gated
(Smart Search, behind reCAPTCHA) are deliberately absent rather than worked
around.

Design note: none of these sources agree on how to identify a person. The case
DB already holds both "Charlie McKinnus" and "Charlie Edward McKinnus" for one
defendant, so name matching alone will silently merge or split people. SONumber
is the reliable key and is carried through everywhere it is available.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Any

log = logging.getLogger("boydclips.records")

PORTAL = "https://portal-txbexar.tylertech.cloud"
EDOCS = "https://edocs.bexar.org/jailactivity"
MAGISTRATE = "https://centralmagistrate.bexar.org"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0 Safari/537.36")

# Fields that must never survive ingest. Address1 is a defendant's home
# address; publishing it is a hard SAFETY_RULES R3 violation and a YouTube
# doxxing strike. Dropped here, at the boundary, so no downstream code has to
# remember to avoid it.
PII_FIELDS = {"Address1", "DefendantAddress", "DefendantAddressString",
              "DefendantDL", "DefendantDLState"}


class RecordsError(RuntimeError):
    pass


# Minimum gap between requests to the same host.
#
# Observed 2026-08-10: a burst of jail_search calls made the portal start
# closing connections outright (WinError 10054). That is the server shedding
# load, not a network fault, and retrying harder makes it worse. Pacing at the
# client is the fix — an unattended daily run must never look like a scraper.
_MIN_INTERVAL = {"portal-txbexar.tylertech.cloud": 1.2,
                 "centralmagistrate.bexar.org": 1.0,
                 "edocs.bexar.org": 0.5}
_DEFAULT_INTERVAL = 0.8
_last_call: dict[str, float] = {}


def _throttle(url: str) -> None:
    host = urllib.parse.urlparse(url).netloc
    gap = _MIN_INTERVAL.get(host, _DEFAULT_INTERVAL)
    prev = _last_call.get(host)
    if prev is not None:
        wait = gap - (time.monotonic() - prev)
        if wait > 0:
            time.sleep(wait)
    _last_call[host] = time.monotonic()


def _cool_off(host: str, seconds: float) -> None:
    """Push the next allowed call into the future after a refusal."""
    _last_call[host] = time.monotonic() + seconds


def _request(url: str, *, data: bytes | None = None, headers: dict | None = None,
             timeout: int = 40, retries: int = 4) -> bytes:
    """One HTTP call, paced and backed off.

    County servers behind a CDN: transient 403/503 happens and a single failure
    must not abort a daily run. But a *connection reset* means something
    different from a 5xx — the host is refusing us — so it gets a long cool-off
    rather than the standard ramp.
    """
    hdrs = {"User-Agent": UA, "Accept": "application/json, text/plain, */*"}
    hdrs.update(headers or {})
    host = urllib.parse.urlparse(url).netloc
    last: Exception | None = None

    for attempt in range(1, retries + 1):
        _throttle(url)
        req = urllib.request.Request(url, data=data, headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            last = exc
            # 400/404 are answers, not failures — the id is bad, stop asking.
            if exc.code in (400, 404):
                raise RecordsError(f"{url} -> HTTP {exc.code}") from exc
            if exc.code in (429, 503):
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                pause = float(retry_after) if (retry_after or "").isdigit() else 30.0
                log.warning("  %s rate-limited (%s); cooling off %.0fs",
                            host, exc.code, pause)
                _cool_off(host, pause)
                time.sleep(pause)
                continue
        except (ConnectionResetError, ConnectionAbortedError) as exc:
            # WinError 10054 and friends. The host hung up on us.
            last = exc
            pause = 20.0 * attempt
            log.warning("  %s closed the connection; cooling off %.0fs",
                        host, pause)
            _cool_off(host, pause)
            time.sleep(pause)
            continue
        except Exception as exc:  # noqa: BLE001 - urllib raises a zoo of these
            last = exc
            if isinstance(getattr(exc, "reason", None),
                          (ConnectionResetError, ConnectionAbortedError)):
                pause = 20.0 * attempt
                log.warning("  %s closed the connection; cooling off %.0fs",
                            host, pause)
                _cool_off(host, pause)
                time.sleep(pause)
                continue
        if attempt < retries:
            time.sleep(min(2 ** attempt, 15))
    raise RecordsError(f"{url} failed after {retries} attempts: {last}")


def _strip_pii(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_pii(v) for k, v in obj.items() if k not in PII_FIELDS}
    if isinstance(obj, list):
        return [_strip_pii(v) for v in obj]
    return obj


# --------------------------------------------------------------- jail search

def jail_search(query: str, *, size: int = 25, offset: int = 0) -> dict[str, Any]:
    """Search Bexar jail history. Records go back to 1989.

    Returns {'total': int, 'hits': [...]}. A hit with releaseDate None is
    someone still in custody — that is the "is he out?" answer.
    """
    body = json.dumps({
        "Id": "0", "size": size, "from": offset, "searchTimeMilliseconds": 0,
        "queryString": query, "parameters": {}, "searchResult": {},
        "sorts": [], "facets": [],
    }).encode()
    raw = _request(
        f"{PORTAL}/app/JailSearchService/search",
        data=body,
        headers={"Content-Type": "application/json",
                 "Referer": f"{PORTAL}/app/JailSearch/"},
    )
    d = json.loads(raw)
    result = d.get("searchResult") or {}
    hits = _strip_pii(result.get("hits") or [])
    return {"total": result.get("totalHits", 0), "hits": hits}


def jailing_detail(jail_id: int | str) -> dict[str, Any]:
    """Full booking record: physical description, aliases, and per-charge
    disposition, bond type and warrant number.

    The doubled slash in the path is not a typo — it is what the portal's own
    client sends, and the service is picky about it.
    """
    raw = _request(
        f"{PORTAL}/app/ViewJailingService//Jailings({jail_id})",
        headers={"Referer": f"{PORTAL}/app/ViewJailing/"},
    )
    return _strip_pii(json.loads(raw))


def custody_status(name: str) -> dict[str, Any]:
    """Best-effort answer to 'where is this person now, and what is their record'.

    Groups every booking found for a name. Callers must treat this as a
    candidate set, not an identity: two people can share a name, and one person
    can appear under several spellings. Confirm with SONumber before asserting
    anything on camera.
    """
    res = jail_search(name, size=50)
    by_so: dict[str, list[dict]] = {}
    for h in res["hits"]:
        by_so.setdefault(str(h.get("defendantSONum")), []).append(h)

    people = []
    for so, bookings in by_so.items():
        bookings.sort(key=lambda b: str(b.get("bookingDate") or ""), reverse=True)
        latest = bookings[0]
        people.append({
            "so_number": so,
            "name": latest.get("defendantName"),
            "dob": (latest.get("defendantDOB") or "")[:10],
            "booking_count": len(bookings),
            "in_custody": latest.get("releaseDate") is None,
            "latest_booking": (latest.get("bookingDate") or "")[:10],
            "latest_charges": [c.get("chargeDescription", "").strip()
                               for c in (latest.get("charges") or [])],
            "first_booking": (bookings[-1].get("bookingDate") or "")[:10],
            "jail_ids": [b.get("jailID") for b in bookings],
        })
    people.sort(key=lambda p: p["booking_count"], reverse=True)
    return {"query": name, "total_hits": res["total"], "people": people}


# ------------------------------------------------------------ jail activity

_CSV_KINDS = {"bookings": "JABookings_", "releases": "JAReleases_"}


def fetch_jail_activity(day: date, kind: str = "bookings") -> list[dict[str, str]]:
    """One day of countywide jail activity.

    The county keeps only a rolling seven days, so anything older than that is
    unrecoverable — see archive_jail_activity().
    """
    if kind not in _CSV_KINDS:
        raise ValueError(f"kind must be one of {sorted(_CSV_KINDS)}")
    url = f"{EDOCS}/{_CSV_KINDS[kind]}{day:%Y%m%d}.csv"
    raw = _request(url).decode("utf-8-sig", errors="replace")
    rows = list(csv.DictReader(io.StringIO(raw)))
    return [{k: v for k, v in r.items() if k not in PII_FIELDS} for r in rows]


def archive_jail_activity(out_dir: Path, days_back: int = 7) -> dict[str, int]:
    """Snapshot the rolling window to disk.

    Run daily. Bexar deletes these after seven days and publishes no archive,
    so every day this does not run is a day of county-wide booking, bond,
    defence-attorney and bondsman data that no longer exists anywhere.
    Already-captured days are never refetched.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = skipped = missing = 0

    for delta in range(days_back + 1):
        day = date.today() - timedelta(days=delta)
        for kind in _CSV_KINDS:
            dest = out_dir / f"{day:%Y-%m-%d}_{kind}.json"
            if dest.exists():
                skipped += 1
                continue
            try:
                rows = fetch_jail_activity(day, kind)
            except RecordsError:
                missing += 1
                continue
            dest.write_text(json.dumps(rows, indent=1), encoding="utf-8")
            saved += 1
            log.info("  archived %s (%d rows)", dest.name, len(rows))

    return {"saved": saved, "skipped": skipped, "missing": missing}


# ----------------------------------------------------------------- hearings

# The judicial-officer dropdown posts a numeric id, not a name. Boyd's is
# stable but belongs to the portal's own party table, so re-scrape
# SearchCriteria.SelectedJudicialOfficer from Dashboard/26 if hearings ever
# come back empty for a date range that obviously has hearings.
JUDGE_BOYD_ID = "29818"


def hearings(date_from: date, date_to: date, judge_id: str = JUDGE_BOYD_ID) -> list[dict]:
    """Upcoming docket for a judicial officer — who is scheduled, before it airs.

    Two calls sharing one session: the form POST stores the criteria server
    side, then the grid read returns them. There is no way to pass criteria
    directly to the read endpoint; it only accepts a portlet id.
    """
    cookies: dict[str, str] = {}

    def _cookie_header() -> str:
        return "; ".join(f"{k}={v}" for k, v in cookies.items())

    def _capture(url: str, data: bytes | None = None, extra: dict | None = None) -> bytes:
        hdrs = {"User-Agent": UA, "Referer": f"{PORTAL}/Portal/Home/Dashboard/26"}
        if cookies:
            hdrs["Cookie"] = _cookie_header()
        hdrs.update(extra or {})
        req = urllib.request.Request(url, data=data, headers=hdrs)
        with urllib.request.urlopen(req, timeout=60) as resp:
            for header in resp.headers.get_all("Set-Cookie") or []:
                name, _, rest = header.partition("=")
                cookies[name.strip()] = rest.split(";")[0]
            return resp.read()

    _capture(f"{PORTAL}/Portal/Home/Dashboard/26")

    form = urllib.parse.urlencode({
        "SearchCriteria.SelectedCourt": "District Clerk",
        "SearchCriteria.SelectedHearingType": "District Clerk Criminal",
        "SearchCriteria.SearchByType": "JudicialOfficer",
        "SearchCriteria.SelectedJudicialOfficer": judge_id,
        "SearchCriteria.SelectedCourtRoom": "",
        "SearchCriteria.SearchValue": "",
        "SearchCriteria.Soundex": "false",
        "SearchCriteria.DateFrom": f"{date_from:%m/%d/%Y}",
        "SearchCriteria.DateTo": f"{date_to:%m/%d/%Y}",
        "PortletName": "HearingSearch", "IsRedirectFromCaseInfo": "false",
    }).encode()
    _capture(f"{PORTAL}/Portal/Hearing/SearchHearings/HearingSearch", form,
             {"Content-Type": "application/x-www-form-urlencoded",
              "X-Requested-With": "XMLHttpRequest"})

    raw = _capture(f"{PORTAL}/Portal/Hearing/HearingResults/Read",
                   b"sort=&group=&filter=&portletId=27",
                   {"Content-Type": "application/x-www-form-urlencoded",
                    "X-Requested-With": "XMLHttpRequest"})
    payload = json.loads(raw)

    out = []
    for row in payload.get("Data") or []:
        out.append({
            "defendant": row.get("DefendantName"),
            "case_number": row.get("CaseNumber"),
            "case_type": (row.get("CaseTypeId") or {}).get("Description"),
            "hearing_date": row.get("HearingDate"),
            "hearing_time": row.get("HearingTime"),
            "hearing_type": (row.get("HearingTypeId") or {}).get("Description"),
            "courtroom": row.get("CourtRoom"),
            "judge": row.get("JudgeParsed"),
            "encrypted_case_id": row.get("EncryptedCaseId"),
            "roa_url": row.get("CaseLoadUrl"),
        })
    return out


# --------------------------------------------------------------- magistrate

def magistrate_detail(booking_number: str) -> dict[str, Any]:
    """Intake record for someone processed in the last 24 hours.

    Scraped rather than an API — the page has no JSON endpoint. Outside that
    24-hour window this returns nothing useful, by design of the source.
    """
    html = _request(f"{MAGISTRATE}/Details/{booking_number}").decode(
        "utf-8", errors="replace")
    text = re.sub(r"<[^>]+>", "\n", re.sub(r"(?s)<(script|style).*?</\1>", "", html))
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    charges, current = [], {}
    for i, line in enumerate(lines):
        label = line.rstrip(":")
        if label in ("Offense Description", "Offense Type", "Bond Amount",
                     "Disposition", "Arrest Time", "Magistration Time"):
            if i + 1 < len(lines):
                current[label] = lines[i + 1]
        elif line.startswith("Case Number:"):
            if current:
                charges.append(current)
            current = {"Case Number": line.split(":", 1)[1].strip()}
    if current:
        charges.append(current)

    return {"booking_number": booking_number, "charges": charges}
