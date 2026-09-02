# -*- coding: utf-8 -*-
"""Case selection outranks packaging - who else has posted this case?

Nathan, 2026-08-30: *"I've told you 10 times soto case was high profile and no
one was posting it there are no trials like that"*. Project CLAUDE.md: "Before
packaging, search YouTube for the defendant / case and record who has posted
it in `config/cases.json`." Until 2026-09-01 nothing on disk did that search
or recorded it (grep: no posted_by / competitor field in any case), so the
step was manual and therefore skipped.

    python tools/case_search.py OFFERUP                 # search, print, record posted_by
    python tools/case_search.py --all                   # every case in config/cases.json
    python tools/case_search.py CARTHIEF --name "Jesus Lopez" --cause "2023 CR8930"
    python tools/case_search.py OFFERUP --dry-run       # search + print, write nothing
    python tools/case_search.py --check OFFERUP         # build-path gate (below)
    python tools/case_search.py --selftest              # offline

NAME / CAUSE. Parsed from the case's `note` ("Joseph Grant, 2024 CR011920. ..."),
else taken from the case's `defendant` / `cause` keys (written back after the
first parse or override so they are typed once), else the tool REFUSES with
CASE_SEARCH_NONAME and prints the hearing call it found in
state/called_hearings.json as the suggestion. It never writes a transcript
spelling into cases.json on its own: the CARTHIEF call is transcribed "Hay
Jesus Lopez", which is an ASR artefact, not a name.

SEARCH. yt-dlp 2026.07.04 (on PATH, measured), no API key, `ytsearch20:` with
--flat-playlist, five queries per case, 1.5 s apart:
    "<full name>" judge boyd  /  "<full name>" 187th  /  <cause number>  /
    <surname> boyd court  /  <white> <yellow> judge boyd (the case's own title)
Flat search entries carry no upload date; `youtubetab:approximate_date` gives
one derived from YouTube's "N months ago" text (measured 2026-09-01: 8 days
off on x7qaWLfn8kw), so the exact date is fetched per video for the matches
that count, capped at EXACT_DATE_CAP per case.

GRADING (measured 2026-09-01 on `Garcia boyd court`: 20 results, 15 of them
OTHER Garcias before Judge Boyd - Pete, Victor, Amethyst, Diamond, Greg,
Sylvia, John Robert. Surname + Boyd is NOT evidence anyone posted this case):
    name     full name in title or description                -> counts
    cause    the cause number in title or description         -> counts
    hook     surname + court context + the case's own title
             words (HOOK_NEED of them) in title/description   -> counts
    surname  surname + Boyd/187th/Bexar, no first name        -> listed, unconfirmed
    boyd     Boyd/187th/Bexar, no surname                     -> niche channel, not this case
    own      Texas Trial Tracker (UCT5Fde6OzBSFRmxw5mPn2CA)   -> dropped, counted as own_hits
    source   @judgestephanieboyd4233, the livestream itself   -> dropped
    -        anything else                                    -> dropped
The `hook` grade exists because a competitor need not type the name: measured
2026-09-01, courtcatch TXzrtgkpvVc "Courtroom Chaos: Judge Boyd, a Felony
Plea, and the Spider Monkey Surprise" IS the Joseph Grant hearing (its
description says only "Mr. Grant") and was graded surname, so MONKEY's verdict
read 1 channel when it was 2 - the direction that prints 'nobody' for a case
someone already posted. The hook words are the case's own white + yellow
title with function words removed ("Where's the spider monkey?" -> spider,
monkey). HOOK_NEED = 2 (or every word when the title has fewer) because one
generic word is not evidence: `lopez boyd court` returned "Church Theft Lies:
Jeremy Lopez", which shares "theft" with CARTHIEF's "Playing Grand Theft
Auto?" and is a different Lopez.

RECORD. cases.json[CASE].posted_by = {searched, queries, results,
competitor_count, competitors, verdict, ...}; other keys untouched and in
order, indent=1, ensure_ascii=False, CRLF and no trailing newline exactly as
the file has (round-trip measured byte-identical 2026-09-01).

--check CASE (wired 2026-09-01: tools/thumb_pipeline.py build() runs it as a
build gate, so a case with no search or a stale one fails the thumbnail build):
    CASE_SEARCH_MISSING <CASE>            exit 1   no posted_by
    CASE_SEARCH_STALE <CASE> ...          exit 1   searched > STALE_DAYS ago
    CASE_SEARCH_OK <CASE> <verdict>       exit 0
--check --all              every case in cases.json, worst exit code wins
--check --all --recorded   presence only: a stale search prints
                           CASE_SEARCH_RECORDED and exits 0. This is what
                           tools/selftest_all.py runs - the age limit belongs
                           on the build path (packaging), not in a suite whose
                           health would otherwise decay with the calendar.
"""
import datetime as _dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
CASES = os.path.join(ROOT, "config", "cases.json")
HEARINGS = os.path.join(ROOT, "state", "called_hearings.json")

# memory/nathan-channels-and-accounts.md, CORRECTED 2026-08-29: verified with
# `yt-dlp -J --flat-playlist https://www.youtube.com/@texastrialtracker`
OWN_CHANNEL = {"name": "texas trial tracker", "id": "UCT5Fde6OzBSFRmxw5mPn2CA", "handle": "@texastrialtracker"}
# the source livestream (same memory file) - it "posted" every case, it is not a competitor
SOURCE_CHANNEL = {"name": "judge stephanie boyd", "id": "UCiBt-ijBAoKLiWNwOYogbAQ", "handle": "@judgestephanieboyd4233"}

STALE_DAYS = 14          # brief 2026-09-01: a search older than this is not current
SEARCH_N = 20            # ytsearch20 - measured: the quoted queries return 1-3 anyway
MAX_QUERIES = 6          # polite ceiling per case; the set below is 5
SLEEP_S = 1.5            # between searches
EXACT_DATE_CAP = 8       # per-video date fetches per case (1.4 s each, measured)
RESULTS_CAP = 15         # entries stored per case
HOOK_NEED = 2            # title words that must appear for a surname hit to count (see GRADING)
NAME_SUFFIXES = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv"}
# function words dropped from a case title before it becomes hook words, plus
# the court words the _COURT check already requires (they carry no case identity)
_STOP = set("""a an the and or but of to in on for at by from with as is are was were be been do does did
you your youre he she it its his her they them their this that these those what where wheres who why how when
i me my we us our not no so then than if just get got had has have can will would could should says said
want wants wanted going make made like see saw say tell told know think come came go went take took give gave
let keep put look need try ask asked really very still
judge boyd court texas""".split())
# court context, on normalised text (punctuation -> space): "judge boyd",
# "judge stephanie boyd", "honorable boyd", "boyd s bench", "#judgeboyd",
# "187th district court", bexar. A bare "boyd" is not enough - measured
# 2026-09-01 on `thompson boyd court`: "Rhett Boyd and Deon Thompson" (sports)
# and "Cody Thompson Colorado Vs Aiden Boyd" (wrestling) came through as court
# hits. Nor is a bare "187th": `"Joseph Grant" 187th` returned "187th pick in
# the 2020 NFL draft", "187th day", "187th NATO Military Committee".
_COURT = re.compile(r"\b(?:judge|honorable|hon)\b(?:\s+\w+){0,3}\s+boyd\b|\bboyd\s+s\b|judgeboyd"
                    r"|\b187th\b(?:\s+\w+){0,2}\s+(?:district|court|judicial)\b|\bbexar\b")
YTDLP_TIMEOUT = 90

# "Joseph Grant, 2024 CR011920." / "Isidro Garcia, 2025 CR-002343." / "Louis
# Thompson, the 'family..." - two to four capitalised words, a comma, then an
# optional cause number. Each word needs a lowercase second letter so "SOURCE
# CORRECTED" and "Gate A" cannot parse as a person.
_NOTE = re.compile(r"^\s*(?P<name>[A-Z][a-z][A-Za-z'.-]*(?:\s+[A-Z][a-z][A-Za-z'.-]*){1,3})\s*,\s*"
                   r"(?P<cause>(?:19|20)\d{2}\s*-?\s*CR\s*-?\s*\d{3,})?")
_CAUSE = re.compile(r"((?:19|20)\d{2})\s*-?\s*CR\s*-?\s*0*(\d+)", re.I)
# "Court is calling 2023 CR8930 State of Texas versus Hay Jesus Lopez. Can I..."
_CALL = re.compile(r"calling\s+(?P<cause>(?:19|20)\d{2}\s*CR\s*[\d ]{3,})\s*,?\s*state\s+(?:of\s+texas\s+)?(?:versus|vs\.?|v\.)\s+"
                   r"(?P<name>[A-Z][\w'-]*(?:\s+[A-Z][\w'-]*){1,4})", re.I)


class NoName(Exception):
    pass


# ---------------------------------------------------------------- parsing
def parse_note(note):
    """-> (name, cause_or_None). Raises NoName when the note has no leading name."""
    if not note:
        raise NoName("no note")
    m = _NOTE.match(note)
    if not m:
        raise NoName("note does not start with '<First Last>, ...': " + note[:60].replace("\n", " "))
    cause = m.group("cause")
    return m.group("name").strip(), (re.sub(r"\s+", " ", cause).strip() if cause else None)


def norm_cause(cause):
    """'2025 CR-002343' / '2025CR002343' / '2025 CR 002343' -> ('2025', 2343)."""
    if not cause:
        return None
    m = _CAUSE.search(cause)
    return (m.group(1), int(m.group(2))) if m else None


def name_parts(name):
    """'Ruben Sanchez Jr.' -> (['ruben', 'sanchez', 'jr'], first='ruben', surname='sanchez')"""
    words = [w for w in re.sub(r"[^A-Za-z' -]", " ", name).lower().split() if w]
    core = [w for w in words if w.strip(".") not in NAME_SUFFIXES] or words
    return words, core[0], core[-1]


def hearing_call(case):
    """The 'Court is calling ...' line for this case from state/called_hearings.json,
    matched on the video id in the case's `video` path and case_from. A suggestion
    for --name/--cause, never written on its own (ASR spelling)."""
    vid = None
    m = re.search(r"work/([A-Za-z0-9_-]{11})/", case.get("video", ""))
    if m:
        vid = m.group(1)
    t0 = case.get("case_from")
    if not vid or not os.path.exists(HEARINGS):
        return None
    try:
        rows = json.load(open(HEARINGS, encoding="utf-8"))
    except Exception:
        return None
    best = None
    for r in rows:
        if r.get("video_id") != vid:
            continue
        d = abs(float(r.get("t", 0)) - float(t0)) if t0 is not None else 0
        if best is None or d < best[0]:
            best = (d, r.get("open", ""))
    if best is None or best[0] > 30:
        return None
    m = _CALL.search(best[1])
    if not m:
        return best[1][:120]
    return f"{re.sub(r' +', ' ', m.group('cause')).strip()} State versus {m.group('name')}  (ASR text: '{best[1][:90]}...')"


def resolve_identity(key, case, name=None, cause=None):
    """CLI override > stored defendant/cause > note. Returns (name, cause, source)."""
    src = []
    if name:
        src.append("--name")
    else:
        name = case.get("defendant")
        if name:
            src.append("cases.json defendant")
    if cause:
        src.append("--cause")
    else:
        cause = case.get("cause")
        if cause:
            src.append("cases.json cause")
    if not name or not cause:
        try:
            n2, c2 = parse_note(case.get("note"))
            if not name:
                name, src = n2, src + ["note"]
            if not cause and c2:
                cause, src = c2, src + ["note"]
        except NoName as e:
            if not name:
                hint = hearing_call(case)
                raise NoName(f"CASE_SEARCH_NONAME {key}: {e}. "
                             + (f"state/called_hearings.json reads: {hint}. " if hint else "")
                             + "Pass --name \"First Last\" [--cause \"YYYY CRnnnn\"]")
    return name, cause, "+".join(src)


# ---------------------------------------------------------------- search
def queries_for(name, cause, case):
    words, first, surname = name_parts(name)
    q = [f'"{name}" judge boyd', f'"{name}" 187th']
    if cause:
        q.append(cause)
    q.append(f"{surname} boyd court")
    title = " ".join(x for x in (case.get("white"), case.get("yellow")) if x).strip()
    if title:
        q.append(f"{title} judge boyd")
    return q[:MAX_QUERIES]


def hooks_for(case):
    """The case's own title words that identify it: "Where's the spider monkey?"
    -> ['spider', 'monkey']; "Do you want a jury trial?" -> ['jury', 'trial'].
    Contraction fragments ("where s", "you re" -> s, re: anything of two
    letters or fewer) and _STOP words are dropped; order kept."""
    title = " ".join(x for x in (case.get("white"), case.get("yellow")) if x)
    out = []
    for w in _norm_text(title).split():
        if len(w) > 2 and w not in _STOP and w not in out:
            out.append(w)
    return out


def ytdlp_search(query, n=SEARCH_N):
    """-> (entries, stderr). Flat search, approximate dates, no download."""
    cmd = ["yt-dlp", f"ytsearch{n}:{query}", "--flat-playlist", "--dump-single-json",
           "--no-download", "--no-warnings", "-q", "--extractor-args", "youtubetab:approximate_date"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=YTDLP_TIMEOUT)
    except FileNotFoundError:
        return None, "yt-dlp not on PATH"
    except subprocess.TimeoutExpired:
        return None, f"yt-dlp timed out after {YTDLP_TIMEOUT}s"
    if r.returncode != 0 or not r.stdout.strip():
        return None, (r.stderr or "").strip()[-400:] or f"exit {r.returncode}, empty output"
    try:
        return json.loads(r.stdout).get("entries") or [], ""
    except ValueError as e:
        return None, f"bad JSON from yt-dlp: {e}"


def ytdlp_exact_date(url):
    """'YYYY-MM-DD' or None - one per-video metadata fetch."""
    cmd = ["yt-dlp", "-j", "--no-download", "--skip-download", "--no-warnings", "-q", url]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=YTDLP_TIMEOUT)
        d = json.loads(r.stdout).get("upload_date") if r.returncode == 0 else None
    except Exception:
        return None
    return f"{d[:4]}-{d[4:6]}-{d[6:]}" if d and len(d) == 8 else None


# ---------------------------------------------------------------- grading
def _norm_text(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _is_channel(e, ch):
    return ((e.get("channel_id") or "") == ch["id"]
            or (e.get("uploader_id") or "").lower() == ch["handle"]
            or _norm_text(e.get("channel")) == _norm_text(ch["name"]))


def grade(e, name, cause, hooks=()):
    """'own' | 'source' | 'name' | 'cause' | 'hook' | 'surname' | 'boyd' | None
    `hooks` are the case's title words from hooks_for(); with none given the
    hook grade cannot fire and a surname+court hit stays 'surname'."""
    if _is_channel(e, OWN_CHANNEL):
        return "own"
    if _is_channel(e, SOURCE_CHANNEL):
        return "source"
    words, first, surname = name_parts(name)
    text = _norm_text((e.get("title") or "") + " " + (e.get("description") or ""))
    chan = _norm_text(e.get("channel"))
    # first name, up to two words (middle name / initial), surname
    if re.search(rf"\b{re.escape(first)}(?:\s+\w+){{0,2}}\s+{re.escape(surname)}\b", text):
        return "name"
    nc = norm_cause(cause)
    if nc and any(norm_cause(m.group(0)) == nc for m in _CAUSE.finditer(text)):
        return "cause"
    court = bool(_COURT.search(text + " " + chan))
    if re.search(rf"\b{re.escape(surname)}\b", text):
        if not court:
            return None
        # whole words, optional plural: "monkey" matches "monkeys", not "monkeying"
        hit = [h for h in hooks if re.search(rf"\b{re.escape(h)}s?\b", text)]
        if hooks and len(hit) >= min(HOOK_NEED, len(hooks)):
            return "hook"
        return "surname"
    return "boyd" if court else None


def _date_of(e):
    ts = e.get("timestamp")
    if e.get("upload_date"):
        d = str(e["upload_date"])
        return (f"{d[:4]}-{d[4:6]}-{d[6:]}" if len(d) == 8 else d), "exact"
    if ts:
        return _dt.datetime.fromtimestamp(int(ts), _dt.UTC).strftime("%Y-%m-%d"), "approx"
    return None, None


COUNTS = ("name", "cause", "hook")   # the grades that make a channel a competitor


def collect(entries_by_query, name, cause, hooks=()):
    """entries_by_query: [(query, [entry, ...])] -> posted_by dict (no date fetches)."""
    seen, own_hits, source_hits, niche = {}, 0, 0, {}
    raw = 0
    for qi, (q, entries) in enumerate(entries_by_query):
        for e in entries or []:
            raw += 1
            g = grade(e, name, cause, hooks)
            if g == "own":
                own_hits += 1
                continue
            if g == "source":
                source_hits += 1
                continue
            if g is None:
                continue
            if g == "boyd":
                ch = (e.get("channel") or "").strip()
                niche[ch] = max(niche.get(ch, 0), int(e.get("view_count") or 0))
                continue
            vid = e.get("id")
            if vid in seen:
                seen[vid]["hits"].append(qi)
                continue
            date, dsrc = _date_of(e)
            seen[vid] = {
                "match": g,
                "channel": (e.get("channel") or "").strip(),
                "channel_id": e.get("channel_id"),
                "channel_url": e.get("channel_url"),
                "handle": e.get("uploader_id"),
                "title": e.get("title"),
                "id": vid,
                "url": e.get("url") or f"https://www.youtube.com/watch?v={vid}",
                "view_count": e.get("view_count"),
                "duration_s": e.get("duration"),
                "upload_date": date,
                "date_source": dsrc,
                "hits": [qi],
            }
    rank = {"name": 0, "cause": 0, "hook": 0, "surname": 1}
    results = sorted(seen.values(), key=lambda r: (rank[r["match"]], -(r["view_count"] or 0)))
    competitors = []
    for r in results:
        if r["match"] in COUNTS and r["channel"] not in competitors:
            competitors.append(r["channel"])
    unconfirmed = []
    for r in results:
        if r["match"] == "surname" and r["channel"] not in competitors and r["channel"] not in unconfirmed:
            unconfirmed.append(r["channel"])
    n = len(competitors)
    verdict = "nobody" if n == 0 else f"{n} channel(s): " + ", ".join(competitors)
    return {
        "searched": _dt.date.today().isoformat(),
        "tool": "tools/case_search.py + yt-dlp " + ytdlp_version(),
        "defendant": name,
        "cause": cause,
        "hooks": list(hooks),
        "queries": [q for q, _ in entries_by_query],
        "raw_entries": raw,
        "own_hits": own_hits,
        "source_hits": source_hits,
        "results": results[:RESULTS_CAP],
        "competitor_count": n,
        "competitors": competitors,
        "unconfirmed_surname_only": unconfirmed,
        "niche_channels": dict(sorted(niche.items(), key=lambda kv: -kv[1])[:12]),
        "verdict": verdict,
    }


_YTV = None


def ytdlp_version():
    global _YTV
    if _YTV is None:
        try:
            _YTV = subprocess.run(["yt-dlp", "--version"], capture_output=True, text=True,
                                  timeout=30).stdout.strip() or "?"
        except Exception:
            _YTV = "?"
    return _YTV


# ---------------------------------------------------------------- cases.json io
def load_cases(path=CASES):
    raw = open(path, "rb").read()
    return json.loads(raw.decode("utf-8")), raw


def save_cases(data, raw, path=CASES):
    """Same indent, escaping, line endings and trailing-newline state as the file
    had - the diff must be only what changed. Measured 2026-09-01: indent=1 +
    ensure_ascii=False + CRLF reproduces config/cases.json byte-for-byte."""
    crlf = b"\r\n" in raw
    text = json.dumps(data, indent=1, ensure_ascii=False)
    if raw.endswith(b"\n"):
        text += "\n"
    out = text.encode("utf-8")
    if crlf:
        out = out.replace(b"\n", b"\r\n")
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(out)
    os.replace(tmp, path)


# ---------------------------------------------------------------- reporting
def print_table(pb):
    print(f"  defendant: {pb['defendant']}   cause: {pb['cause'] or '-'}   hooks: {' '.join(pb.get('hooks') or []) or '-'}   searched: {pb['searched']}")
    for i, q in enumerate(pb["queries"]):
        print(f"  q{i}: {q}")
    print(f"  raw entries {pb['raw_entries']}, own channel {pb['own_hits']}, source stream {pb['source_hits']}")
    if pb["results"]:
        print(f"  {'match':8} {'views':>8} {'date':10} {'channel':34} title")
        for r in pb["results"]:
            v = r["view_count"] if r["view_count"] is not None else "?"
            d = (r["upload_date"] or "?") + ("~" if r["date_source"] == "approx" else " ")
            print(f"  {r['match']:8} {str(v):>8} {d:11}{r['channel'][:33]:34} {(r['title'] or '')[:60]}")
            print(f"  {'':8} {'':>8} {'':11}{'':34} {r['url']}  q{','.join(map(str, r['hits']))}")
    if pb["niche_channels"]:
        print("  niche (Boyd court, not this case): " + ", ".join(pb["niche_channels"]))
    if pb["unconfirmed_surname_only"]:
        print("  surname-only, unconfirmed: " + ", ".join(pb["unconfirmed_surname_only"]))


def search_case(key, cases, raw, name=None, cause=None, write=True, path=CASES):
    case = cases[key]
    name, cause, src = resolve_identity(key, case, name, cause)
    qs = queries_for(name, cause, case)
    got, errors = [], []
    for i, q in enumerate(qs):
        if i:
            time.sleep(SLEEP_S)
        entries, err = ytdlp_search(q)
        if entries is None:
            errors.append(f"q{i} '{q}': {err}")
            entries = []
        got.append((q, entries))
        print(f"  q{i} [{len(entries):2d}] {q}" + (f"   ERROR {err}" if err else ""))
    if len(errors) == len(qs):
        print(f"CASE_SEARCH_ERROR {key}: every query failed - nothing recorded")
        for e in errors:
            print("    " + e)
        return None
    pb = collect(got, name, cause, hooks_for(case))
    if pb["raw_entries"] == 0:
        # even '<surname> boyd court' returns 20 when the search works; zero
        # across all queries is a block or an outage, not 'nobody'
        print(f"CASE_SEARCH_ERROR {key}: {len(qs)} queries returned 0 entries in total - not recorded as 'nobody'")
        return None
    if errors:
        pb["errors"] = errors
    # exact dates for the results that count
    fetched = 0
    for r in pb["results"]:
        if r["match"] in COUNTS and fetched < EXACT_DATE_CAP:
            time.sleep(0.7)
            d = ytdlp_exact_date(r["url"])
            fetched += 1
            if d:
                r["upload_date"], r["date_source"] = d, "exact"
    print_table(pb)
    print(f"CASE_SEARCH_VERDICT {key}: {pb['verdict']}")
    if write:
        if case.get("defendant") != name:
            case["defendant"] = name
        if cause and case.get("cause") != cause:
            case["cause"] = cause
        case["posted_by"] = pb
        save_cases(cases, raw, path)
        print(f"  recorded posted_by in {os.path.relpath(path, ROOT)} (identity from {src})")
    return pb


# ---------------------------------------------------------------- --check
def check(key, path=CASES, today=None):
    """-> (exit_code, line). The build-path gate."""
    try:
        cases, _ = load_cases(path)
    except Exception as e:
        return 2, f"CASE_SEARCH_UNKNOWN {key}: cannot read {path}: {e}"
    if key not in cases:
        return 2, f"CASE_SEARCH_UNKNOWN {key}: not in {os.path.basename(path)}"
    pb = cases[key].get("posted_by")
    if not isinstance(pb, dict) or not pb.get("searched"):
        return 1, f"CASE_SEARCH_MISSING {key}: no posted_by - run python tools/case_search.py {key}"
    today = today or _dt.date.today()
    try:
        d = _dt.date.fromisoformat(str(pb["searched"])[:10])
    except ValueError:
        return 1, f"CASE_SEARCH_STALE {key}: searched='{pb['searched']}' is not a date"
    age = (today - d).days
    if age > STALE_DAYS:
        return 1, f"CASE_SEARCH_STALE {key}: searched {d} is {age} days old (limit {STALE_DAYS})"
    return 0, f"CASE_SEARCH_OK {key} {pb.get('verdict', '?')}"


# ---------------------------------------------------------------- selftest
# Real yt-dlp entries, run 2026-09-01, trimmed to the fields the grader reads.
# `_from_query` names the live query each came from. Nothing here is invented.
FIXTURE = [
    {"id": "VQ9DYFA9AVw", "title": "The Moment Judge Boyd Asked If 18 Months Was Worth What He Stole",
     "channel": "Trial Tales", "channel_id": "UCupr8osK5xx6WbpFaQMEf3Q",
     "channel_url": "https://www.youtube.com/channel/UCupr8osK5xx6WbpFaQMEf3Q", "uploader_id": "@officialtrialtales",
     "url": "https://www.youtube.com/watch?v=VQ9DYFA9AVw", "view_count": 585, "duration": 3419, "timestamp": None,
     "description": "Three felony cases collide as Isidro Garcia stands before the court, facing a plea deal while his pattern of risky choices comes ...",
     "_from_query": "\"Isidro Garcia\" judge boyd"},
    {"id": "x7qaWLfn8kw", "title": "Judge Boyd sentences Isidro Garcia and Eric Adam Talamantas shares his opinions on Judge Franco",
     "channel": "Just Scrapping Purrfect Justice @just_scrapping", "channel_id": "UCy1tuOmPvzJXoNckfnmUCvg",
     "channel_url": "https://www.youtube.com/channel/UCy1tuOmPvzJXoNckfnmUCvg", "uploader_id": "@BexarCountyJudge",
     "url": "https://www.youtube.com/watch?v=x7qaWLfn8kw", "view_count": 2, "duration": 477, "timestamp": None,
     "description": "", "_from_query": "\"Isidro Garcia\" judge boyd"},
    {"id": "ESSF8lSkNN4", "title": "Judge Boyd: \"Then Why Are You Stealing Cars?\"",
     "channel": "Texas Trial Tracker", "channel_id": "UCT5Fde6OzBSFRmxw5mPn2CA",
     "channel_url": "https://www.youtube.com/channel/UCT5Fde6OzBSFRmxw5mPn2CA", "uploader_id": "@TexasTrialTracker",
     "url": "https://www.youtube.com/watch?v=ESSF8lSkNN4", "view_count": 49, "duration": 551, "timestamp": None,
     "description": "Judge Boyd asked about the damaged steering column. He said he did that himself, because he lost the key fob. Her answer: ...",
     "_from_query": "\"Isidro Garcia\" judge boyd"},
    {"id": "vLCkL_X1tWE", "title": "He told the judge it was funny. Judge Boyd doubled it.",
     "channel": "Texas Trial Tracker", "channel_id": "UCT5Fde6OzBSFRmxw5mPn2CA",
     "channel_url": "https://www.youtube.com/channel/UCT5Fde6OzBSFRmxw5mPn2CA", "uploader_id": "@TexasTrialTracker",
     "url": "https://www.youtube.com/watch?v=vLCkL_X1tWE", "view_count": 54, "duration": 1003, "timestamp": 1788220800,
     "description": "Causes 2023 CR8930 and 2023 CR8931. This is public court record, published for transparency. No commentary has been ...",
     "_from_query": "2023 CR8930"},
    {"id": "ylAXDvbIOBQ", "title": "MÁY HÚT MÙI KÍNH VÁT GẮN TƯỜNG | CAPRI CR-678H | Thiết kế sang trọng, Hút nhanh khói mùi",
     "channel": "Capri Việt Nam | Thiết Bị Nhà Bếp Cao Cấp", "channel_id": "UCQpvZ9UYTAclJDHGQ6Qa42Q",
     "channel_url": "https://www.youtube.com/channel/UCQpvZ9UYTAclJDHGQ6Qa42Q", "uploader_id": "@thietbinhabep.caprivietnam",
     "url": "https://www.youtube.com/watch?v=ylAXDvbIOBQ", "view_count": 431, "duration": 208, "timestamp": 1662076800,
     "description": "Máy hút mùi Capri CR-678H thiết kế sang trọng ...", "_from_query": "2023 CR8930"},
    {"id": "VKQFJWm-9B4", "title": "MON., NOV 17, 2025/JUDGE STEPHANIE BOYD/187TH DISTRICT COURT/MORNING DOCKET",
     "channel": "Judge Stephanie Boyd", "channel_id": "UCiBt-ijBAoKLiWNwOYogbAQ",
     "channel_url": "https://www.youtube.com/channel/UCiBt-ijBAoKLiWNwOYogbAQ", "uploader_id": "@judgestephanieboyd4233",
     "url": "https://www.youtube.com/watch?v=VKQFJWm-9B4", "view_count": 10624, "duration": 12156, "timestamp": 1764633600,
     "description": "Monday, November 17, 2025 Judge Stephanie Boyd 187th District Court Bexar County, Texas Morning Docket.",
     "_from_query": "Garcia boyd court"},
    {"id": "XSuRjujcFjs", "title": "Judge Boyd Showed No Mercy- Pete Garcia Gets 8 Years Jail for Child Crime| #courtstories",
     "channel": "Court Stories", "channel_id": "UCGdySRfu7TDuG--kHG10GDw",
     "channel_url": "https://www.youtube.com/channel/UCGdySRfu7TDuG--kHG10GDw", "uploader_id": "@CourtStories-s9u",
     "url": "https://www.youtube.com/watch?v=XSuRjujcFjs", "view_count": 182, "duration": 1066, "timestamp": 1764633600,
     "description": "This video breaks down the sentencing of Pete Garcia. Who lost his stable life over a dark secret. Watch as Judge Boyd delivers ...",
     "_from_query": "Garcia boyd court"},
    {"id": "Ek3Ah3NZYVo", "title": "Judge Boyd LOSES IT After Finding Out What This Cop Did",
     "channel": "Audit the Court", "channel_id": "UCmc4biDadYIwhBctWd1ESuA",
     "channel_url": "https://www.youtube.com/channel/UCmc4biDadYIwhBctWd1ESuA", "uploader_id": "@AudittheCourt",
     "url": "https://www.youtube.com/watch?v=Ek3Ah3NZYVo", "view_count": 492075, "duration": 1237, "timestamp": 1785628800,
     "description": "WATCH THE BEST JUDGE BOYD CASES: ...", "_from_query": "Garcia boyd court"},
    # MONKEY rows, fetched 2026-09-01 (repair): the courtcatch video that the
    # first build graded 'surname' and left out of the verdict, the Judge Boyd's
    # Bench video that names him, and two controls for the hook grade
    {"id": "TXzrtgkpvVc", "title": "Courtroom Chaos: Judge Boyd, a Felony Plea, and the Spider Monkey Surprise",
     "channel": "courtcatch", "channel_id": "UCwhCc-TRBD1HR1ny0sK-yIQ",
     "channel_url": "https://www.youtube.com/channel/UCwhCc-TRBD1HR1ny0sK-yIQ", "uploader_id": "@courtcatch-c6q",
     "url": "https://www.youtube.com/watch?v=TXzrtgkpvVc", "view_count": 4, "duration": 855, "timestamp": 1759363200,
     "description": "Watch this real courtroom drama unfold as Mr. Grant faces charges for unauthorized use of a vehicle, a state jail felony that carries ...",
     "_from_query": "Where's the spider monkey? judge boyd"},
    {"id": "GazDwmJElTE", "title": "Judge Boyd Schools Joseph Grant Over Monkey, Money & Mistakes",
     "channel": "Judge Boyd’s Bench", "channel_id": "UCt_FDKEqEc7TVYa4EpV5-0A",
     "channel_url": "https://www.youtube.com/channel/UCt_FDKEqEc7TVYa4EpV5-0A", "uploader_id": "@Judgeboydbench",
     "url": "https://www.youtube.com/watch?v=GazDwmJElTE", "view_count": 214, "duration": 721, "timestamp": 1759363200,
     "description": "What started as a routine plea for unauthorized use of a vehicle turned into one of the most memorable hearings in Judge Boyd's ...",
     "_from_query": "grant boyd court"},
    {"id": "s17QA7qiLOw", "title": "Coach Pleads for Star Athlete — Will Judge Boyd Grant Probation or Prison?",
     "channel": "The 19th Verdict", "channel_id": "UCRpT7hAW7y7yvDAa512f7uw",
     "channel_url": "https://www.youtube.com/channel/UCRpT7hAW7y7yvDAa512f7uw", "uploader_id": "@The19thVerdict",
     "url": "https://www.youtube.com/watch?v=s17QA7qiLOw", "view_count": 8, "duration": 1167, "timestamp": 1775088000,
     "description": "Coach Pleads for Star Athlete — Will Judge Boyd Grant Probation or Prison? The 19th Verdict: No Easy Way Out in Judge ...",
     "_from_query": "grant boyd court"},
    {"id": "YhtLF-brAXM", "title": "Judge Boyd Exposes Church Theft Lies: Jeremy Lopez Caught in Court!  #judgeboyd",
     "channel": "Trial & Truth", "channel_id": "UC0uRHwA4HR-zqE-HE-dUY6w",
     "channel_url": "https://www.youtube.com/channel/UC0uRHwA4HR-zqE-HE-dUY6w", "uploader_id": "@TrialandTruthYT",
     "url": "https://www.youtube.com/watch?v=YhtLF-brAXM", "view_count": 2, "duration": 655, "timestamp": 1756771200,
     "description": "Jeremy Tyler Lopez appeared in court facing burglary charges for entering a church and allegedly stealing $619.50. During the ...",
     "_from_query": "lopez boyd court"},
]

# the five cases' real note openings as of 2026-09-01 (CARTHIEF, SANCHEZ have none)
REAL_NOTES = {
    "CARTHIEF": None,
    "SANCHEZ": None,
    "OFFERUP": "Isidro Garcia, 2025 CR-002343. Hearing runs 10582-11209 (next call is State v. Anthony Wayne).",
    "MONKEY": "Joseph Grant, 2024 CR011920. SOURCE CORRECTED 2026-08-30: was MONKEY_LONGFORM.mp4, which is OUR OWN render",
    "THOMPSON": "Louis Thompson, the 'family was murdered' hearing (gMdQwkaFGMw, 657.7s). Nathan calls this one 'Thomas'.",
}
WANT_NOTES = {
    "CARTHIEF": NoName, "SANCHEZ": NoName,
    "OFFERUP": ("Isidro Garcia", "2025 CR-002343"),
    "MONKEY": ("Joseph Grant", "2024 CR011920"),
    "THOMPSON": ("Louis Thompson", None),
}


def selftest():
    ok = True

    def t(cond, what):
        nonlocal ok
        ok = ok and bool(cond)
        print(f"  {'ok  ' if cond else 'FAIL'} {what}")

    print("note parser, the five real notes + negative controls")
    for k, note in REAL_NOTES.items():
        want = WANT_NOTES[k]
        try:
            got = parse_note(note)
        except NoName as e:
            got = NoName
        t(got == want or (want is NoName and got is NoName), f"{k}: {note[:34] if note else None!r} -> {got if got is not NoName else 'NoName (loud)'}")
    for bad in ("SOURCE CORRECTED 2026-08-30: was MONKEY_LONGFORM.mp4", "Gate A failed, 2024 CR011920.",
                "Hearing runs 10582-11209, then", ""):
        try:
            parse_note(bad)
            t(False, f"negative control parsed as a name: {bad!r}")
        except NoName:
            t(True, f"refused: {bad[:40]!r}")
    t(parse_note("Ruben Sanchez Jr., 2026 CR00005277 State") == ("Ruben Sanchez Jr.", "2026 CR00005277"), "suffix Jr. kept in the name")
    t(name_parts("Ruben Sanchez Jr.")[2] == "sanchez", "surname skips the suffix")
    t(norm_cause("2025 CR-002343") == norm_cause("2025CR002343") == norm_cause("2025 CR 002343") == ("2025", 2343), "cause normalisation")
    # the live file (disk read, no network): only what stays true whatever gets
    # typed into a note. A note that parses must agree with the stored
    # defendant/cause (typed once, not twice), and a case that has been
    # searched must still resolve to the defendant it was searched under.
    # It never asserts that a note is unparsable - typing "Jesus Lopez, 2023
    # CR8930." into CARTHIEF's note is exactly what the brief wants, and the
    # first build's frozen NoName expectation turned the suite red on that
    # legitimate edit (verifier, 2026-09-01).
    if os.path.exists(CASES):
        live, _ = load_cases()
        for k, c in live.items():
            try:
                n, cz = parse_note(c.get("note"))
            except NoName:
                n = cz = None
            if n:
                t(not c.get("defendant") or c["defendant"] == n,
                  f"live {k}: note name {n!r} agrees with defendant {c.get('defendant')!r}")
            if cz and c.get("cause"):
                t(norm_cause(c["cause"]) == norm_cause(cz), f"live {k}: note cause {cz!r} agrees with cause {c['cause']!r}")
            if isinstance(c.get("posted_by"), dict):
                try:
                    rn, rc, src = resolve_identity(k, c)
                    t(rn == c["posted_by"].get("defendant"),
                      f"live {k}: resolves to {rn!r} ({src}), searched as {c['posted_by'].get('defendant')!r}")
                except NoName as e:
                    t(False, f"live {k}: has posted_by but no longer resolves - {e}")

    print("grading, real fixture entries")
    name, cause = "Isidro Garcia", "2025 CR-002343"
    by = {e["id"]: e for e in FIXTURE}
    t(grade(by["ESSF8lSkNN4"], name, cause) == "own", "own channel (Texas Trial Tracker) -> own, dropped")
    t(grade(by["vLCkL_X1tWE"], name, cause) == "own", "own channel by id even when cause is in the description -> own")
    t(grade(by["VKQFJWm-9B4"], name, cause) == "source", "the livestream channel -> source, dropped")
    t(grade(by["ylAXDvbIOBQ"], name, cause) is None, "unrelated title (CAPRI CR-678H range hood) -> dropped")
    t(grade(by["x7qaWLfn8kw"], name, cause) == "name", "full name in title -> name")
    t(grade(by["VQ9DYFA9AVw"], name, cause) == "name", "full name in description only -> name")
    t(grade(by["XSuRjujcFjs"], name, cause) == "surname", "Pete Garcia + Boyd -> surname only, NOT counted")
    t(grade(by["Ek3Ah3NZYVo"], name, cause) == "boyd", "Boyd, no Garcia -> niche channel, not this case")
    # negative control for the own-channel filter: rename the channel and drop the id -> it leaks
    leak = dict(by["ESSF8lSkNN4"], channel="Someone Else", channel_id="UCxxxxxxxxxxxxxxxxxxxxxx", uploader_id="@someoneelse")
    t(grade(leak, name, cause) == "boyd", "control: a non-own copy of our own video IS graded (filter is doing the work)")
    t(grade(dict(by["vLCkL_X1tWE"], channel="Someone Else", channel_id="UCx", uploader_id="@x"), "Jesus Lopez", "2023 CR8930") == "cause",
      "cause number in description -> cause (when not our channel)")
    t(grade({"title": "Isidro J. Garcia sentenced", "channel": "x"}, name, None) == "name", "middle initial between first and surname still matches")
    t(grade({"title": "Garcia sentenced", "channel": "x"}, name, None) is None, "surname without any court word -> dropped")
    # real titles from `thompson boyd court`, 2026-09-01: a bare "boyd" is a surname too
    t(grade({"title": "FULL SEGMENT: Rhett Boyd and Deon Thompson Debate the Best Teams", "channel": "BCSN"}, "Louis Thompson", None) is None,
      "control: sports 'Rhett Boyd and Deon Thompson' -> dropped, not court context")
    t(grade({"title": "Mat 11 106 Cody Thompson Colorado Vs Aiden Boyd Oklahoma", "channel": "USA Wrestling"}, "Louis Thompson", None) is None,
      "control: wrestling 'Cody Thompson ... Aiden Boyd' -> dropped")
    t(grade({"title": "Judge Boyd chats w/Laura Thompson about her Bout for Re-Election", "channel": "TAAN TV"}, "Louis Thompson", None) == "surname",
      "'Judge Boyd ... Laura Thompson' -> surname, unconfirmed")
    t(grade({"title": "Arrogant Mom Begs For 5th Chance", "channel": "Boyd's Bench", "description": ""}, "Louis Thompson", None) == "boyd",
      "channel \"Boyd's Bench\" alone -> boyd (niche)")
    t(grade({"title": "Judge Boyd sentences Ruth Lopez #judgeboyd", "channel": "x"}, "Jesus Lopez", None) == "surname",
      "'#judgeboyd' hashtag counts as court context")
    # real titles from `"Joseph Grant" 187th`, 2026-09-01
    t(grade({"title": "Donovan Peoples-Jones Press Conference", "channel": "Cleveland Browns",
             "description": "after being announced as 187th pick in the 2020 NFL draft"}, "Joseph Grant", None) is None,
      "control: '187th pick in the NFL draft' -> dropped")
    t(grade({"title": "187th NATO Military Committee in Chiefs of Defence", "channel": "NATO"}, "Joseph Grant", None) is None,
      "control: '187th NATO Military Committee' -> dropped")
    t(grade({"title": "MON., NOV 17, 2025/JUDGE STEPHANIE BOYD/187TH DISTRICT COURT/MORNING DOCKET", "channel": "x"}, "Joseph Grant", None) == "boyd",
      "'187TH DISTRICT COURT' -> court context")

    print("hook grade: the case's own title words (the MONKEY undercount, verifier 2026-09-01)")
    monkey = {"white": "Where's the", "yellow": "spider monkey?"}
    hooks = hooks_for(monkey)
    t(hooks == ["spider", "monkey"], f"hooks_for(Where's the spider monkey?) -> {hooks}")
    t(hooks_for({"white": "Do you want", "yellow": "a jury trial?"}) == ["jury", "trial"], "hooks_for(Do you want a jury trial?) -> jury, trial")
    t(hooks_for({"white": "Playing Grand", "yellow": "Theft Auto?"}) == ["playing", "grand", "theft", "auto"], "hooks_for(Playing Grand Theft Auto?)")
    t(hooks_for({"white": "You're why your son", "yellow": "is struggling"}) == ["son", "struggling"], "hooks_for(You're why your son is struggling) drops the 're' fragment")
    t(hooks_for({"white": "Your children", "yellow": "were killed?"}) == ["children", "killed"], "hooks_for(Your children were killed?)")
    t(hooks_for({"white": "Judge Boyd", "yellow": "in court"}) == [], "control: a title made of court words has no hooks")
    jg, jc = "Joseph Grant", "2024 CR011920"
    t(grade(by["TXzrtgkpvVc"], jg, jc, hooks) == "hook", "courtcatch 'Mr. Grant ... Spider Monkey' -> hook, COUNTS")
    t(grade(by["TXzrtgkpvVc"], jg, jc) == "surname", "control: the same entry without hooks is only 'surname' (the hook words do the work)")
    t(grade(by["TXzrtgkpvVc"], jg, jc, ["spider"]) == "hook", "a one-word title needs only that word")
    t(grade(by["TXzrtgkpvVc"], jg, jc, ["spider", "monkey", "banana"]) == "hook", f"{HOOK_NEED} of 3 title words is enough")
    t(grade(by["TXzrtgkpvVc"], jg, jc, ["banana", "monkey"]) == "surname", "one of two title words is not")
    t(grade(by["GazDwmJElTE"], jg, jc, hooks) == "name", "'Joseph Grant Over Monkey' -> name (name outranks hook)")
    t(grade(by["s17QA7qiLOw"], jg, jc, hooks) == "surname", "control: 'Will Judge Boyd Grant Probation' -> surname (grant the verb, no hook word), NOT counted")
    t(grade(by["YhtLF-brAXM"], "Jesus Lopez", "2023 CR8930", ["playing", "grand", "theft", "auto"]) == "surname",
      "control: 'Church Theft Lies: Jeremy Lopez' shares one generic word with CARTHIEF -> surname, NOT counted")
    t(grade(dict(by["TXzrtgkpvVc"], title="Chaos: a Felony Plea and the Spider Monkey Surprise", channel="x"), jg, jc, hooks) is None,
      "control: hook words + surname but no court context -> dropped")
    t(grade({"title": "Judge Boyd and the spider monkeys", "description": "Mr Grant", "channel": "x"}, jg, jc, hooks) == "hook", "plural 'monkeys' still matches")

    print("collect -> posted_by")
    pb = collect([('"Isidro Garcia" judge boyd', FIXTURE[:3]), ("2023 CR8930", FIXTURE[3:5]), ("Garcia boyd court", FIXTURE[5:8])], name, cause)
    ids = [r["id"] for r in pb["results"]]
    t("ESSF8lSkNN4" not in ids and "vLCkL_X1tWE" not in ids and pb["own_hits"] == 2, f"own videos dropped, own_hits={pb['own_hits']}")
    t("ylAXDvbIOBQ" not in ids, "unrelated dropped from results")
    t(ids[:2] == ["VQ9DYFA9AVw", "x7qaWLfn8kw"], f"name matches first, by views: {ids}")
    t(pb["competitor_count"] == 2 and pb["verdict"] == "2 channel(s): Trial Tales, Just Scrapping Purrfect Justice @just_scrapping", f"verdict: {pb['verdict']}")
    t(pb["unconfirmed_surname_only"] == ["Court Stories"], f"surname-only listed unconfirmed: {pb['unconfirmed_surname_only']}")
    t(list(pb["niche_channels"]) == ["Audit the Court"] and pb["source_hits"] == 1, f"niche: {list(pb['niche_channels'])}, source_hits={pb['source_hits']}")
    t(pb["results"][2]["upload_date"] == "2025-12-02" and pb["results"][2]["date_source"] == "approx", "approximate timestamp -> date~")
    t(collect([("q", [])], name, cause)["verdict"] == "nobody", "no matches -> 'nobody'")
    # the MONKEY undercount, as recorded by the first build vs. repaired
    mq = [("grant boyd court", FIXTURE[9:12]), ("Where's the spider monkey? judge boyd", FIXTURE[8:9])]
    pm = collect(mq, jg, jc, hooks)
    t(pm["verdict"] == "2 channel(s): Judge Boyd’s Bench, courtcatch" and pm["competitor_count"] == 2,
      f"MONKEY with hooks -> {pm['verdict']}")
    t(pm["unconfirmed_surname_only"] == ["The 19th Verdict"] and list(pm["niche_channels"]) == ["Trial & Truth"] and pm["hooks"] == hooks,
      f"'Grant Probation' stays unconfirmed, Jeremy Lopez is niche: {pm['unconfirmed_surname_only']} / {list(pm['niche_channels'])}")
    pm0 = collect(mq, jg, jc)
    t(pm0["verdict"] == "1 channel(s): Judge Boyd’s Bench" and "courtcatch" in pm0["unconfirmed_surname_only"],
      f"control: without hooks the first build's undercount comes back: {pm0['verdict']}")

    print("--check on temp cases.json (negative controls: the gate can fail)")
    tmp = tempfile.mkdtemp(prefix="case_search_")
    try:
        src = CASES if os.path.exists(CASES) else None
        p = os.path.join(tmp, "cases.json")
        if src:
            shutil.copy(src, p)
            data, raw = load_cases(p)
        else:
            data, raw = {"OFFERUP": {"white": "Do you want", "yellow": "a jury trial?"}}, b"{}"
            save_cases(data, raw, p)
        key = "OFFERUP" if "OFFERUP" in data else next(iter(data))
        # baseline for the write-fidelity check: the copy's own key order, minus
        # the block this test rewrites (the live file may already carry one)
        base = {k: [x for x in data[k] if x != "posted_by"] for k in data}
        base_vals = {k: {x: data[k][x] for x in base[k]} for k in data}
        data[key].pop("posted_by", None)
        save_cases(data, raw, p)
        code, line = check(key, p)
        t(code == 1 and line.startswith(f"CASE_SEARCH_MISSING {key}"), line)
        old = (_dt.date.today() - _dt.timedelta(days=30)).isoformat()
        data[key]["posted_by"] = dict(pb, searched=old)
        save_cases(data, raw, p)
        code, line = check(key, p)
        t(code == 1 and line.startswith(f"CASE_SEARCH_STALE {key}") and "30 days" in line, line)
        data[key]["posted_by"] = dict(pb, searched=(_dt.date.today() - _dt.timedelta(days=STALE_DAYS)).isoformat())
        save_cases(data, raw, p)
        code, line = check(key, p)
        t(code == 0 and line.startswith(f"CASE_SEARCH_OK {key} 2 channel(s)"), f"{STALE_DAYS} days old is still OK: {line}")
        code, line = check("NOPE", p)
        t(code == 2 and line.startswith("CASE_SEARCH_UNKNOWN"), line)
        # the real CLI exit code, in-process module but a real subprocess
        r = subprocess.run([sys.executable, os.path.abspath(__file__), "--check", key, "--cases", p],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
        t(r.returncode == 0 and "CASE_SEARCH_OK" in r.stdout, f"CLI --check exit {r.returncode}")
        data[key].pop("posted_by")
        save_cases(data, raw, p)
        r = subprocess.run([sys.executable, os.path.abspath(__file__), "--check", key, "--cases", p],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
        t(r.returncode == 1 and "CASE_SEARCH_MISSING" in r.stdout, f"CLI --check exit {r.returncode} on missing")
        # --check --all: one missing case fails the whole run; --recorded lets a
        # stale search through (selftest_all's row) but never a missing one
        r = subprocess.run([sys.executable, os.path.abspath(__file__), "--check", "--all", "--recorded", "--cases", p],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
        t(r.returncode == 1 and f"CASE_SEARCH_MISSING {key}" in r.stdout
          and r.stdout.count("CASE_SEARCH_") == len(data),
          f"--check --all --recorded: exit {r.returncode}, {r.stdout.count('CASE_SEARCH_')} lines for {len(data)} cases, missing still fails")
        data[key]["posted_by"] = dict(pb, searched=old)
        save_cases(data, raw, p)
        r = subprocess.run([sys.executable, os.path.abspath(__file__), "--check", "--all", "--recorded", "--cases", p],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
        others_ok = all(data[k].get("posted_by", {}).get("searched") for k in data if k != key)
        t(r.returncode == (0 if others_ok else 1) and f"CASE_SEARCH_RECORDED {key}" in r.stdout and "30 days" in r.stdout,
          f"--check --all --recorded: a 30-day-old search is RECORDED, exit {r.returncode}")
        r = subprocess.run([sys.executable, os.path.abspath(__file__), "--check", "--all", "--cases", p],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
        t(r.returncode == 1 and f"CASE_SEARCH_STALE {key}" in r.stdout,
          f"--check --all without --recorded: the same search is STALE, exit {r.returncode}")
        data[key].pop("posted_by")
        save_cases(data, raw, p)
        # write fidelity: keys, order, line endings preserved; only the additions differ
        data2, raw2 = load_cases(p)
        # compare with posted_by removed on BOTH sides: it may sit mid-entry in
        # the live file (TORRES 2026-09-02 - keys were appended after it)
        t(list(data2) == list(base)
          and all([x for x in data2[k] if x != "posted_by"] == base[k] for k in base)
          and all(data2[k][x] == base_vals[k][x] for k in base for x in base[k]),
          "case order, every original key order and every original value preserved after a write")
        t((b"\r\n" in raw2) == (b"\r\n" in raw) and raw2.endswith(b"\n") == raw.endswith(b"\n"),
          "line endings and trailing-newline state preserved")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("SELFTEST_PASS case_search" if ok else "SELFTEST_FAIL case_search")
    return ok


# ---------------------------------------------------------------- cli
def main(argv):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    a = list(argv)
    if not a or a[0] in ("-h", "--help"):
        print(__doc__)
        return 2
    if a[0] == "--selftest":
        return 0 if selftest() else 1

    def opt(flag):
        if flag in a:
            i = a.index(flag)
            v = a[i + 1]
            del a[i:i + 2]
            return v
        return None

    path = opt("--cases") or CASES
    name, cause = opt("--name"), opt("--cause")
    dry = "--dry-run" in a
    if dry:
        a.remove("--dry-run")
    if a and a[0] == "--check":
        recorded = "--recorded" in a
        targets = [x for x in a[1:] if not x.startswith("--")]
        if "--all" in a:
            cases, _ = load_cases(path)
            targets = list(cases)
        if not targets:
            print("usage: --check CASE | --check --all [--recorded]")
            return 2
        worst = 0
        for k in targets:
            code, line = check(k, path)
            if recorded and code == 1 and line.startswith("CASE_SEARCH_STALE") and " days old " in line:
                code, line = 0, line.replace("CASE_SEARCH_STALE", "CASE_SEARCH_RECORDED", 1)
            print(line)
            worst = max(worst, code)
        return worst
    cases, raw = load_cases(path)
    if a and a[0] == "--all":
        if name or cause:
            print("--name/--cause apply to one CASE, not --all")
            return 2
        keys = list(cases)
    else:
        keys = [k for k in a if not k.startswith("--")]
        if len(keys) != 1:
            print(__doc__)
            return 2
        if keys[0] not in cases:
            print(f"CASE_SEARCH_UNKNOWN {keys[0]}: not in {os.path.relpath(path, ROOT)} ({', '.join(cases)})")
            return 2
    bad = 0
    verdicts = []
    for i, k in enumerate(keys):
        if i:
            time.sleep(SLEEP_S)
        print(f"== {k}")
        try:
            cases, raw = load_cases(path)   # re-read: an earlier case's write is on disk
            pb = search_case(k, cases, raw, name, cause, write=not dry, path=path)
        except NoName as e:
            print(str(e))
            bad += 1
            continue
        if pb is None:
            bad += 1
        else:
            verdicts.append((k, pb["verdict"]))
    if len(keys) > 1:
        print("== verdicts")
        for k, v in verdicts:
            print(f"  {k:10} {v}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
