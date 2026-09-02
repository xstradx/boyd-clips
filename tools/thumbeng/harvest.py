# -*- coding: utf-8 -*-
"""Find current videos in a niche, pull their thumbnails, and score how hard
each one beat its OWN channel.

Public data only. There is no YouTube Data API key on this machine, and nothing
here needs one.

WHAT THE OUTLIER SCORE IS, AND WHAT IT IS NOT
---------------------------------------------
    outlier_score = video.views_per_day / channel.median_views_per_day
                    (median over that channel's SETTLED videos, EXCLUDING the
                     video being scored - see LEAVE-ONE-OUT below)

Views-per-day rather than raw views, because raw views conflate "good
thumbnail" with "published three years ago". Ratio to the video's own channel
rather than absolute views, because 200k views on a 5M-subscriber channel is a
flop and 200k on a 2,880-subscriber channel is a phenomenon; dividing by the
channel's own norm removes subscriber count, which is the dominant confound.
Median rather than mean, because one viral video in a small back catalogue drags
a mean up until every other video on the channel looks like a failure - which
would invert nothing less than the entire winner/loser split.

LEAVE-ONE-OUT, added when the self-inclusion bias was measured
--------------------------------------------------------------
The divisor excludes the video being scored. Measured on a synthetic 5-video
channel with paces 100/200/300/400/5000: including the video in its own
baseline scored the 5000 at 16.67x, excluding it scores 20.00x - a 20% error
introduced by the outlier dragging up the very median it is measured against.
The effect shrinks as the catalogue grows (a median moves by half a step when
one point leaves) but MIN_BASELINE is 5, so small channels are exactly where it
bites. A row is also required to leave MIN_BASELINE videos BEHIND it, so a
5-video channel scores visiting videos but not its own.

The `outlier_basis` string is deliberately NOT renamed for this: styles.py pins
the literal "vpd_ratio_vs_channel_median_settled7d" and this module is not
allowed to break it. channels.json carries baseline_method instead.

HONESTY LIMITS, and these are hard:
  * This measures PACE AGAINST THE CHANNEL'S OWN NORM. It cannot separate the
    thumbnail's effect from the title, the topic, the upload timing, or the
    algorithm's mood that week. It is a ranking signal, NOT an attribution.
  * We cannot see CTR or impressions for any channel we do not own. YouTube
    exposes those only in a channel's own Studio analytics. Every number here is
    downstream of views, so a thumbnail that earned a great CTR on a topic
    nobody searched for looks identical to a bad thumbnail.
  * Dates from the flat listing are APPROXIMATE (see below), so age_days and
    therefore views_per_day carry roughly a day of slop. Fine for ranking,
    wrong for anything that needs an exact publish date.
  * Search results are ranked by YouTube's own relevance, which is itself a
    popularity signal. A harvest built only from search is biased toward
    winners and will have almost no losers in it. That bias is recorded in the
    run manifest rather than hidden, and deepen_channels exists to fix it.
    A channel whose every settled row came from a search is therefore marked
    usable=False with search_only=True: the median of six search hits is the
    median of six winners, not the channel's norm, and dividing one winner by
    another returns a number near 1.0 that looks like a measurement and is not.
    (Before this was enforced, --no-deepen printed finite outlier scores while
    its own --help promised they would all be NaN.)
  * baseline_limit caps a channel listing at its N NEWEST videos, so on a
    high-frequency channel that window can be shorter than SETTLE_DAYS and
    contribute no settled videos at all. MEASURED 2026-08-30: A&E's newest 40
    uploads span 2026-08-24..2026-08-30, seven days, none of them settled - so
    its only settled rows were the nine search hits and the search_only gate
    correctly refused to score it. Raise baseline_limit for channels that post
    several times a day.

ACCESS PATHS, ALL PROBED LIVE ON THIS MACHINE
---------------------------------------------
1. SEARCH   yt-dlp --flat-playlist --dump-json "ytsearch5:<query>"  -> one call,
   rows carrying id, title, view_count, duration, channel, channel_id,
   channel_url, timestamp.
2. CHANNEL  the same flags against /channel/<ID>/videos.
3. DATES    WITHOUT --extractor-args youtubetab:approximate_date the flat
   listing returns timestamp=None for every row, which makes an age-normalised
   score impossible. WITH it, dates arrive but are approximate: measured, the
   flat listing gave 20260828 for a video whose full metadata dump gave
   20260827 (1787875200 vs 1787811126, about 18h out). Recorded as
   date_is_approximate=True and never presented as an exact publish date.
4. THUMBS   plain HTTPS GET, no key. Measured per variant on a real id:
       maxresdefault.jpg  1280x720  native 16:9, no bars
       hq720.jpg          1280x720  native 16:9, no bars
       mqdefault.jpg       320x180  native 16:9, no bars
       sddefault.jpg       640x480  60 black rows top and bottom
       hqdefault.jpg       480x360  45 black rows top and bottom
   A bogus id returns HTTP 404 and a real one 200, so a 404 is a genuine signal
   to step down the ladder. THUMB_QUALITIES is therefore the three native-16:9
   variants, with the two letterboxed ones only as last resorts that
   measure.deletterbox has to repair.

FLAT LISTING vs PER-VIDEO DUMP - the tradeoff, measured
-------------------------------------------------------
--flat-playlist is one HTTP conversation for the whole listing (about 2-4s for
60 videos) and returns view_count, duration and an approximate timestamp. A
per-video dump (yt-dlp --dump-json <url>, no --flat-playlist) returns the exact
upload timestamp, like/comment counts and the full description, but costs one
request per video - roughly 1-3s each, so 60 videos is minutes, not seconds.
Since the only field the flat path gets wrong is the date, and it is wrong by
under a day while our unit is days, THE FLAT PATH IS THE DEFAULT. hydrate_rows()
implements the slow exact path for the cases where a real date matters, and it
is never called by the normal harvest.

A full single-video dump also emits a "No supported JavaScript runtime" warning
and still returns complete metadata. That warning is not a failure.

FIELD-NAME ASYMMETRY - the bug this module exists to not have
-------------------------------------------------------------
MEASURED: a ytsearch row carries top-level channel / channel_id / channel_url.
A /channel/<id>/videos row carries channel_id = None and puts the identity in
playlist_channel / playlist_channel_id / playlist_id instead. Reading only
channel_id would give every channel-harvested row a null channel, collapsing
every baseline to one bucket and making every outlier score meaningless.
normalise_row reads both, in that order.

CACHING: a thumbnail already on disk is never re-downloaded, and harvest.jsonl
is rewritten from scratch each run (metadata is cheap; view counts move).

    python -m tools.thumbeng.harvest --niche court --query "courtroom judge sentencing"
    python -m tools.thumbeng.harvest --niche ttt --channel UCT5Fde6OzBSFRmxw5mPn2CA
    python -m tools.thumbeng.harvest --selftest
"""
import os
import sys
import json
import math
import time
import shutil
import argparse
import subprocess

# --- package-relative import, with a fallback for direct-script execution ----
# Running "python tools/thumbeng/harvest.py" leaves the package unimportable, so
# put the REPO ROOT (not the tools dir) on sys.path and import the package
# properly. Never put the tools dir first: tools/harvest.py already exists and
# is an unrelated courtroom-frame harvester that would shadow this file.
try:
    from tools.thumbeng import (
        SCHEMA_VERSION, WORK_ROOT, niche_dir, utc_now,
        write_json, read_json, write_jsonl, read_jsonl, write_csv, run_manifest,
    )
except ImportError:  # pragma: no cover - only hit on direct-script runs
    _ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if _ROOT not in sys.path:
        sys.path.insert(0, _ROOT)
    from tools.thumbeng import (
        SCHEMA_VERSION, WORK_ROOT, niche_dir, utc_now,
        write_json, read_json, write_jsonl, read_jsonl, write_csv, run_manifest,
    )

# requests is present on this interpreter (2.33.1, verified) but the module must
# not hard-depend on it: urllib from the stdlib is always there. requests is
# preferred when available only because its streaming download is tidier.
try:
    import requests as _requests
except ImportError:  # pragma: no cover
    _requests = None
import urllib.request
import urllib.error

try:
    import numpy as _np
    import cv2 as _cv2
except ImportError:  # pragma: no cover
    _np = None
    _cv2 = None


# ---------------------------------------------------------------- constants

def _find_ytdlp():
    """Resolve the yt-dlp executable.

    The known-good absolute path first (verified working), then PATH, so this
    still runs on a machine where miniconda moved.
    """
    for cand in ("C:/Users/natha/miniconda3/Scripts/yt-dlp.exe",
                 "C:/Users/natha/miniconda3/Scripts/yt-dlp"):
        if os.path.exists(cand):
            return cand
    found = shutil.which("yt-dlp")
    return found or "yt-dlp"


YTDLP = _find_ytdlp()

# All three are native 16:9 with zero black bars (measured). Order is
# descending resolution: a 1280x720 frame measures detail honestly, a 320x180
# one does not, and grammar.py can see which it got from thumb_quality.
THUMB_QUALITIES = ("maxresdefault", "hq720", "mqdefault")

# Letterboxed. Accepted only when nothing above exists, and measure.deletterbox
# must crop the bars before any measurement or lum_mean, edge_density and every
# palette key are poisoned.
FALLBACK_QUALITIES = ("sddefault", "hqdefault")

# Measured on a real id (see the ACCESS PATHS block). Kept as data so the
# minimum acceptable frame size is DERIVED from the smallest variant this
# module is willing to ask for, instead of being an invented number.
THUMB_VARIANT_DIMS = {
    "maxresdefault": (1280, 720),
    "hq720": (1280, 720),
    "sddefault": (640, 480),
    "hqdefault": (480, 360),
    "mqdefault": (320, 180),
}

# Smallest variant in the ladder is mqdefault at 320x180. Anything smaller than
# that is not one of the five variants we requested, so it is a placeholder or
# an error page rendered as an image, and must be rejected.
MIN_THUMB_W = min(w for w, _ in THUMB_VARIANT_DIMS.values())
MIN_THUMB_H = min(h for _, h in THUMB_VARIANT_DIMS.values())

THUMB_URL = "https://i.ytimg.com/vi/{vid}/{quality}.jpg"

# A YouTube video id is base64url text. Anything outside this set cannot be a
# real id, and - since the id becomes a FILENAME - would either escape out_dir
# ("../x") or raise OSError on Windows (':' '?' '*' are illegal in NTFS names).
_ID_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz"
                      "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")

# youtube.com was registered 2005-02-14 (epoch 1108339200, computed not
# recalled). A timestamp at or below it is not a real upload date - the flat
# listing occasionally hands back 0 - and must be treated as MISSING rather
# than as a 20-year-old video with a near-zero views-per-day.
YOUTUBE_EPOCH = 1108339200

# A video younger than a week has not settled its views-per-day: it is still on
# its initial impression burst. Including one inflates its own outlier score AND
# deflates every sibling's by raising the channel median.
SETTLE_DAYS = 7

# Below five settled videos a channel median is noise. Those channels get
# outlier_score = NaN rather than a number anyone might believe.
MIN_BASELINE = 5

# outlier_confidence reaches 1.0 at this many settled videos in the baseline.
# Named rather than inlined because the selftest asserts against it and a magic
# 20 buried in an expression is how the two drift apart. The value is a
# judgement, not a measurement: 20 settled videos is where a median stops
# moving when one video is added, on the channels looked at here. It is not
# derived from anything, and it is documented as such.
CONFIDENCE_FULL_N = 20

# A quartile needs at least one observation per quartile to mean anything. With
# n=1, _percentile returns that single value for BOTH p25 and p75, which prints
# as a spread of zero and reads as certainty. Below this, both are NaN.
MIN_PERCENTILE_N = 4

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")

HARVEST_KEYS = (
    "video_id", "title", "url", "channel", "channel_id", "channel_url",
    "view_count", "duration_s", "is_short", "upload_date", "timestamp",
    "date_is_approximate", "age_days", "views_per_day",
    "channel_median_vpd", "channel_n_baseline",
    "outlier_score", "outlier_log2", "outlier_confidence", "outlier_basis",
    "settled", "thumb_path", "thumb_quality", "thumb_w", "thumb_h",
    "thumb_http_status", "source_query", "harvested_utc", "schema_version",
)

# Keys whose JSON null must come back as NaN, so the round-trip is lossless.
_NAN_KEYS = frozenset((
    "age_days", "views_per_day", "channel_median_vpd",
    "outlier_score", "outlier_log2",
))

OUTLIER_BASIS = "vpd_ratio_vs_channel_median_settled7d"

# Recorded in channels.json so the file says which arithmetic produced it.
BASELINE_METHOD = "leave_one_out_median_vpd_over_settled_listing_backed"


# ---------------------------------------------------------------- guards

def _finite(v):
    """Value as a float when it is a real finite number, else None.

    Every numeric that crosses a file boundary in this engine can come back as
    an int (JSON writes 1000.0 and 1000 identically once a value is whole), as
    None (write_json turns NaN into null), or as a numeric string. The original
    code tested `isinstance(v, float)`, which silently returned NaN for an int
    median and raised TypeError on a null one - both from the same channels.json
    it had just written. One coercion, used everywhere, instead.
    """
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _from_search_only(row):
    """True when EVERY provenance tag on the row is a search.

    harvest() accumulates provenance as "search:q|baseline:UCxx", so a row the
    search found and a channel listing later confirmed is not search-only. An
    empty source_query returns False: unknown provenance is not evidence, and a
    caller holding hand-built rows must not have its baselines silently voided.
    """
    parts = [p for p in str(row.get("source_query") or "").split("|") if p]
    return bool(parts) and all(p.startswith("search:") for p in parts)


def _is_video_id(vid):
    """True when vid can be a YouTube id AND is safe as a filename.

    Both questions have the same answer, which is why they are one function:
    the id is interpolated into a URL and into a path, so "../evil" or "a:b?c"
    is either a directory escape or an OSError on NTFS. Length is NOT checked -
    ids are 11 characters today and that is not this module's promise to keep.
    """
    s = str(vid or "")
    return bool(s) and all(ch in _ID_CHARS for ch in s)


# ---------------------------------------------------------------- yt-dlp

def run_ytdlp(target, limit=60, flat=True, approximate_date=True,
              timeout=300, extra_args=None):
    """Run yt-dlp once and return the parsed --dump-json rows.

    encoding='utf-8' is not optional: the Windows console default (cp1252)
    mangles the em-dashes and emoji that appear in real competitor titles, and a
    mangled title showed up in the very first probe of this pipeline.

    On a non-zero exit this returns whatever rows DID parse rather than raising,
    because yt-dlp routinely exits non-zero after skipping a single private or
    members-only video, and losing 59 good rows to one bad one is worse than the
    bad one.
    """
    cmd = [YTDLP, "--dump-json", "--ignore-errors", "--no-warnings",
           "--playlist-end", str(int(limit))]
    if flat:
        cmd.append("--flat-playlist")
    if approximate_date:
        cmd += ["--extractor-args", "youtubetab:approximate_date"]
    if extra_args:
        cmd += list(extra_args)
    cmd.append(target)

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        sys.stderr.write("  yt-dlp failed on %s: %s\n" % (target, exc))
        return []

    rows = []
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    if proc.returncode != 0 and not rows:
        sys.stderr.write("  yt-dlp exit %d, no rows: %s\n"
                         % (proc.returncode, (proc.stderr or "").strip()[:300]))
    return rows


def search_videos(query, limit=60, timeout=300):
    """Search YouTube for a niche and return raw yt-dlp rows.

    This is how "what is working in their niche RIGHT NOW" gets its population.
    Note the sampling bias recorded in the module docstring: search order is
    YouTube's relevance ranking, so this returns winners. Losers come from
    channel_videos.
    """
    return run_ytdlp("ytsearch%d:%s" % (int(limit), query), limit=limit,
                     flat=True, approximate_date=True, timeout=timeout)


def _channel_url(channel_id_or_url):
    """Normalise a bare UC id, an @handle or a full URL to a /videos listing."""
    s = str(channel_id_or_url or "").strip().rstrip("/")
    if not s:
        return ""
    if s.startswith("http://") or s.startswith("https://"):
        return s if s.endswith("/videos") else s + "/videos"
    if s.startswith("@"):
        return "https://www.youtube.com/%s/videos" % s
    if s.startswith("UC") and len(s) >= 20:
        return "https://www.youtube.com/channel/%s/videos" % s
    return "https://www.youtube.com/@%s/videos" % s.lstrip("@")


def channel_videos(channel_id_or_url, limit=60, timeout=300):
    """Return a channel's own back catalogue as raw yt-dlp rows.

    This is the ONLY way to get losers. A search never surfaces a channel's
    flops, so a grammar built on search results alone is comparing winners to
    winners and will find nothing.
    """
    url = _channel_url(channel_id_or_url)
    if not url:
        return []
    return run_ytdlp(url, limit=limit, flat=True, approximate_date=True,
                     timeout=timeout)


def hydrate_rows(rows, timeout=120, progress=True):
    """Replace approximate flat-listing dates with exact ones, per video.

    THE SLOW PATH, deliberately not wired into harvest(). One yt-dlp invocation
    per video (roughly 1-3s each), so 60 videos is minutes. Only worth it when
    an exact publish date actually matters; for age in DAYS the flat listing's
    sub-day error is irrelevant. Rows it fixes get date_is_approximate=False.
    """
    out = []
    total = len(rows)
    for i, row in enumerate(rows, 1):
        vid = row.get("video_id") or row.get("id")
        if not vid:
            out.append(row)
            continue
        if progress:
            sys.stderr.write("  hydrate %d/%d %s\n" % (i, total, vid))
        got = run_ytdlp("https://www.youtube.com/watch?v=%s" % vid, limit=1,
                        flat=False, approximate_date=False, timeout=timeout)
        if got and got[0].get("timestamp"):
            row = dict(row)
            row["timestamp"] = int(got[0]["timestamp"])
            row["upload_date"] = got[0].get("upload_date") or row.get("upload_date")
            row["date_is_approximate"] = False
            if got[0].get("view_count") is not None:
                row["view_count"] = int(got[0]["view_count"])
        out.append(row)
    return out


# ---------------------------------------------------------------- rows

def _first(raw, *keys):
    """First non-empty value among keys. Exists because of the field-name
    asymmetry between search rows and channel rows documented up top."""
    for k in keys:
        v = raw.get(k)
        if v not in (None, "", []):
            return v
    return None


def normalise_row(raw, source_query="", now_utc=None):
    """Map one raw yt-dlp row onto the frozen harvest schema.

    Outlier fields are left unset here; they need the whole population and are
    filled in by outlier_score() after channel_baseline() has run.
    """
    now = float(now_utc if now_utc is not None else time.time())

    vid = _first(raw, "id", "video_id") or ""
    ts = _first(raw, "timestamp", "release_timestamp")
    try:
        ts = int(ts) if ts is not None else None
    except (TypeError, ValueError):
        ts = None
    # A timestamp at or before YOUTUBE_EPOCH cannot be an upload date. The old
    # test was a bare `if ts:`, which read 0 as "missing" by accident and would
    # have read 86400 as a 1970 upload - a 56-year age and a views_per_day of
    # ~0, which is a settled, scoreable, and completely wrong number.
    if ts is not None and ts <= YOUTUBE_EPOCH:
        ts = None

    if ts is not None:
        age_days = max(0.0, (now - ts) / 86400.0)
        upload_date = time.strftime("%Y%m%d", time.gmtime(ts))
    else:
        age_days = float("nan")
        upload_date = _first(raw, "upload_date") or None

    views = _first(raw, "view_count")
    try:
        views = int(views) if views is not None else None
    except (TypeError, ValueError):
        views = None

    dur = _first(raw, "duration")
    try:
        dur = float(dur) if dur is not None else None
    except (TypeError, ValueError):
        dur = None

    # max(age_days, 1.0): a video hours old would otherwise divide by ~0.1 and
    # report a views-per-day ten times its actual pace.
    if views is None or not math.isfinite(age_days):
        vpd = float("nan")
    else:
        vpd = views / max(age_days, 1.0)

    # See FIELD-NAME ASYMMETRY in the module docstring: channel-listing rows
    # carry the identity only under the playlist_* names.
    ch_id = _first(raw, "channel_id", "playlist_channel_id", "playlist_id",
                   "uploader_id")
    ch_name = _first(raw, "channel", "playlist_channel", "uploader",
                     "playlist_uploader")
    ch_url = _first(raw, "channel_url", "uploader_url", "playlist_webpage_url")
    if not ch_url and ch_id and str(ch_id).startswith("UC"):
        ch_url = "https://www.youtube.com/channel/%s" % ch_id

    settled = bool(math.isfinite(age_days) and age_days >= SETTLE_DAYS)

    return {
        "video_id": vid,
        "title": _first(raw, "title", "fulltitle") or "",
        "url": _first(raw, "webpage_url", "url") or (
            "https://www.youtube.com/watch?v=%s" % vid if vid else ""),
        "channel": ch_name,
        "channel_id": ch_id,
        "channel_url": ch_url,
        "view_count": views,
        "duration_s": dur,
        # A Short is <= 60s. Duration is the only signal available in a flat
        # listing; there is no is_short field to read.
        "is_short": bool(dur is not None and dur <= 60.0),
        "upload_date": upload_date,
        "timestamp": ts,
        # Always True: every row this module produces comes from a flat listing.
        # hydrate_rows() is the only thing that sets it False.
        "date_is_approximate": True,
        "age_days": age_days,
        "views_per_day": vpd,
        "channel_median_vpd": float("nan"),
        "channel_n_baseline": 0,
        "outlier_score": float("nan"),
        "outlier_log2": float("nan"),
        "outlier_confidence": 0.0,
        "outlier_basis": OUTLIER_BASIS,
        "settled": settled,
        "thumb_path": None,
        "thumb_quality": None,
        "thumb_w": None,
        "thumb_h": None,
        "thumb_http_status": None,
        "source_query": source_query,
        "harvested_utc": utc_now(),
        "schema_version": SCHEMA_VERSION,
    }


# ---------------------------------------------------------------- thumbnails

def _http_get(url, timeout=20):
    """GET returning (status, content_type, bytes).

    Uses requests when importable and urllib otherwise, so the module works on
    an interpreter without requests. A 404 is returned as a status, not raised:
    stepping down the quality ladder is normal control flow here, not an error.
    """
    headers = {"User-Agent": USER_AGENT}
    if _requests is not None:
        try:
            r = _requests.get(url, headers=headers, timeout=timeout, stream=True)
            return r.status_code, r.headers.get("Content-Type", ""), r.content
        except Exception as exc:                      # noqa: BLE001
            return 0, "error:%s" % type(exc).__name__, b""
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.headers.get("Content-Type", ""), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, "", b""
    except Exception as exc:                          # noqa: BLE001
        return 0, "error:%s" % type(exc).__name__, b""


def _decode_check(data):
    """Return (w, h, ok) for image bytes, rejecting YouTube's grey placeholder.

    YouTube serves HTTP 200 with a small flat grey placeholder for some ids.
    Measured as a real thumbnail it would poison every luminance, colour and
    edge statistic in the grammar, so it must be rejected at fetch time. Two
    tests: the bytes must decode at all, and the frame must not be
    near-uniform. std < 2.0 on a real thumbnail is not achievable - even a
    black-background court frame has text on it.

    The size floor is MIN_THUMB_W/H, derived from THUMB_VARIANT_DIMS (the
    smallest variant the ladder asks for is mqdefault, 320x180). It used to be
    a hand-written 100x60, which passed a 200x120 placeholder as a real frame.
    """
    if _cv2 is None or _np is None or not data:
        # Without cv2 we cannot verify. Accept the bytes and say so rather than
        # silently pretending they were checked.
        return None, None, bool(data)
    arr = _np.frombuffer(data, dtype=_np.uint8)
    img = _cv2.imdecode(arr, _cv2.IMREAD_COLOR)
    if img is None:
        return None, None, False
    h, w = img.shape[:2]
    if w < MIN_THUMB_W or h < MIN_THUMB_H:
        return w, h, False
    if float(img.std()) < 2.0:
        return w, h, False
    return w, h, True


def fetch_thumbnail(video_id, out_dir, qualities=THUMB_QUALITIES,
                    fallbacks=FALLBACK_QUALITIES, overwrite=False, timeout=20):
    """Download one video's thumbnail, walking the quality ladder.

    Accepts only HTTP 200 with an image/* content type whose bytes actually
    decode (see _decode_check). Skips the network entirely when the file already
    exists and overwrite is False, which is what makes a re-harvest free.

    Records which quality won, because a mqdefault-only video is 320x180 and its
    detail measurements are not comparable with a maxresdefault one. grammar.py
    must be able to see that from the data rather than guess.

    Raises ValueError on an id that is not base64url text: the id is both a URL
    segment and a filename, so "../evil" wrote OUTSIDE out_dir and "a:b?c"
    raised a bare OSError from open(). A bad id is a caller bug and says so.

    http_status is None, never 200, for a cache hit. The old code reported 200
    for a file it had not requested, which put a fabricated HTTP status into
    every re-harvested row.
    """
    if not _is_video_id(video_id):
        raise ValueError("not a usable video id (URL segment and filename): %r"
                         % (video_id,))
    out_dir = str(out_dir).replace("\\", "/").rstrip("/")
    os.makedirs(out_dir, exist_ok=True)
    path = "%s/%s.jpg" % (out_dir, video_id)

    if not overwrite and os.path.isfile(path) and os.path.getsize(path) > 0:
        try:
            with open(path, "rb") as fh:
                w, h, ok = _decode_check(fh.read())
        except OSError:
            w, h, ok = None, None, False
        if ok:
            meta = read_json(path + ".meta.json", default={}) or {}
            return {"path": path, "quality": meta.get("quality") or "cached",
                    "width": w or meta.get("width"),
                    "height": h or meta.get("height"),
                    "http_status": None,
                    "bytes": os.path.getsize(path), "cached": True}

    last_status = None
    for quality in tuple(qualities) + tuple(fallbacks):
        url = THUMB_URL.format(vid=video_id, quality=quality)
        status, ctype, data = _http_get(url, timeout=timeout)
        last_status = status
        if status != 200 or not str(ctype).lower().startswith("image/"):
            continue
        w, h, ok = _decode_check(data)
        if not ok:
            continue
        # Write through a temp file and os.replace, the same discipline
        # write_json uses. A crash or a dropped connection part-way through a
        # direct write leaves a truncated JPEG that cv2 still decodes - so it
        # would pass the cache check forever and be measured as a real frame.
        tmp = path + ".part"
        try:
            with open(tmp, "wb") as fh:
                fh.write(data)
            os.replace(tmp, path)
        except OSError as exc:
            sys.stderr.write("  cannot write %s: %s\n" % (path, exc))
            try:
                os.remove(tmp)
            except OSError:
                pass
            continue
        write_json(path + ".meta.json",
                   {"video_id": video_id, "quality": quality, "url": url,
                    "width": w, "height": h, "bytes": len(data),
                    "http_status": status, "fetched_utc": utc_now()})
        return {"path": path, "quality": quality, "width": w, "height": h,
                "http_status": status, "bytes": len(data), "cached": False}

    return {"path": None, "quality": None, "width": None, "height": None,
            "http_status": last_status, "bytes": 0, "cached": False}


# ---------------------------------------------------------------- scoring

def _clean_floats(vals):
    """Finite floats only, sorted. Accepts ints, numeric strings and Nones.

    Centralised because both _median and _percentile were calling
    math.isfinite() straight on whatever the caller had, which raises TypeError
    on the None that a JSON round-trip produces from a NaN.
    """
    out = []
    for v in vals or ():
        f = _finite(v)
        if f is not None:
            out.append(f)
    out.sort()
    return out


def _median(vals):
    """Median of finite values, NaN when there are none."""
    xs = _clean_floats(vals)
    if not xs:
        return float("nan")
    n = len(xs)
    return xs[n // 2] if n % 2 else 0.5 * (xs[n // 2 - 1] + xs[n // 2])


def _percentile(vals, q, min_n=1):
    """Linear-interpolated percentile, NaN when the sample is too small.

    min_n exists because a percentile over one observation is not a percentile:
    with n=1 this returns that value for p25 AND p75, printing a spread of zero
    that reads as a tight, well-measured channel. Callers reporting quartiles
    pass MIN_PERCENTILE_N.
    """
    xs = _clean_floats(vals)
    if len(xs) < max(1, int(min_n)):
        return float("nan")
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * (q / 100.0)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(xs) - 1)
    frac = pos - lo
    return xs[lo] * (1.0 - frac) + xs[hi] * frac


def channel_baseline(rows, min_videos=MIN_BASELINE, settle_days=SETTLE_DAYS):
    """Per-channel views-per-day baseline over SETTLED videos only.

    Median, not mean, for the reason in the module docstring: one viral outlier
    in a small back catalogue drags a mean up until every sibling looks like a
    failure, which inverts the winner/loser split entirely.

    usable is False below min_videos settled videos, and every video on an
    unusable channel gets outlier_score = NaN. A ratio against a 3-video median
    is not a measurement, it is a rumour.

    usable is ALSO False when every settled row came from a search
    (source_query "search:..."). A search returns a channel's hits, so its
    median is the median of that channel's winners and every ratio against it
    lands near 1.0 - a confident-looking number with no losers in the
    denominator. Rows whose source_query is empty (a caller holding rows in
    memory) are NOT assumed to be search rows: this only fires on positive
    evidence that the whole population came from one.

    settled_vpd_by_video is carried so outlier_score can take the video being
    scored back OUT of the divisor; see LEAVE-ONE-OUT in the module docstring.
    """
    by_ch = {}
    for row in rows:
        ch = row.get("channel_id") or "unknown"
        by_ch.setdefault(ch, []).append(row)

    out = {}
    for ch, group in by_ch.items():
        settled = []
        for r in group:
            if not r.get("settled"):
                continue
            # _finite, not math.isfinite: a row read back from harvest.jsonl
            # without nan_keys carries views_per_day=None and the old
            # math.isfinite(None) raised TypeError mid-baseline.
            if _finite(r.get("views_per_day")) is None:
                continue
            settled.append(r)

        vpds = [_finite(r.get("views_per_day")) for r in settled]
        views = [_finite(r.get("view_count")) for r in settled]
        views = [v for v in views if v is not None]
        n_settled = len(settled)

        by_vid = {}
        for r in settled:
            vid = str(r.get("video_id") or "")
            if vid:
                by_vid[vid] = _finite(r.get("views_per_day"))

        n_search = sum(1 for r in settled if _from_search_only(r))
        search_only = bool(n_settled > 0 and n_search == n_settled)

        med = _median(vpds)
        out[ch] = {
            "channel": next((r.get("channel") for r in group if r.get("channel")), None),
            "channel_id": ch,
            "n_total": len(group),
            "n_settled": n_settled,
            "n_settled_from_search": n_search,
            "search_only": search_only,
            "median_vpd": med,
            "mean_vpd": (sum(vpds) / len(vpds)) if vpds else float("nan"),
            "median_views": _median(views),
            # Quartiles suppressed below MIN_PERCENTILE_N rather than printed
            # from one or two observations.
            "p25_vpd": _percentile(vpds, 25, min_n=MIN_PERCENTILE_N),
            "p75_vpd": _percentile(vpds, 75, min_n=MIN_PERCENTILE_N),
            "settled_vpd_by_video": by_vid,
            "usable": bool(n_settled >= min_videos and math.isfinite(med)
                           and med > 0 and not search_only),
            "unusable_reason": (
                "fewer than %d settled videos" % min_videos
                if n_settled < min_videos else
                "every settled video came from a search: this median is a "
                "median of winners" if search_only else
                "median views-per-day is not a positive number"
                if not (math.isfinite(med) and med > 0) else None),
            "baseline_method": BASELINE_METHOD,
            # Carried so outlier_score enforces the SAME floor the baseline was
            # built with, instead of re-reading the module default and
            # disagreeing with its own caller.
            "min_videos": int(min_videos),
            "settle_days": settle_days,
        }
    return out


def outlier_score(row, baselines, settle_days=SETTLE_DAYS):
    """Score one video against its own channel's normal pace.

    outlier_score = views_per_day / channel median views_per_day.
    outlier_log2 = log2 of that, so 2x up and 2x down have equal magnitude -
    grammar.py's statistics need a symmetric quantity, and a raw ratio is not.

    outlier_confidence = min(1, n_baseline / CONFIDENCE_FULL_N), and 0 for any
    row that was not scored at all. It degrades honestly rather than pretending
    a 6-video channel is the same evidence as a 60-video one. n_baseline is the
    count AFTER the row is removed from its own baseline, so it is the number
    of videos that actually formed the divisor.

    HONESTY NOTE, carried deliberately into the code: this measures pace against
    the channel's own norm and CANNOT separate the thumbnail's effect from
    title, topic, upload timing or the algorithm. It is a ranking signal, not an
    attribution. And CTR/impressions are invisible for any channel we do not
    own, so even a perfect ranking here is a ranking of outcomes, not of causes.
    """
    ch = row.get("channel_id") or "unknown"
    base = baselines.get(ch) or {}
    vid = str(row.get("video_id") or "")

    # LEAVE-ONE-OUT. The video being scored is taken out of its own divisor,
    # and what is left must STILL meet min_videos - otherwise a 5-video channel
    # would score its own members against four siblings while the module claims
    # a five-video floor. Falls back to the whole-channel median when a caller
    # passes a baseline dict from an older channels.json that has no per-video
    # map; the fallback is reported in the returned n_baseline, not hidden.
    by_vid = base.get("settled_vpd_by_video")
    if isinstance(by_vid, dict) and by_vid:
        kept = [v for k, v in by_vid.items() if k != vid]
        med = _median(kept) if vid in by_vid else _finite(base.get("median_vpd"))
        n_base = len(kept) if vid in by_vid else int(_finite(base.get("n_settled")) or 0)
        if med is None:
            med = float("nan")
    else:
        med = _finite(base.get("median_vpd"))
        med = float("nan") if med is None else med
        n_base = int(_finite(base.get("n_settled")) or 0)

    vpd = _finite(row.get("views_per_day"))
    min_videos = int(_finite(base.get("min_videos")) or MIN_BASELINE)

    result = {
        "channel_median_vpd": med,
        "channel_n_baseline": n_base,
        "outlier_score": float("nan"),
        "outlier_log2": float("nan"),
        "outlier_confidence": 0.0,
        "outlier_basis": OUTLIER_BASIS,
    }

    if not base.get("usable"):
        return result
    if not row.get("settled"):
        return result
    if n_base < min_videos:
        return result
    if not (math.isfinite(med) and med > 0):
        return result
    if vpd is None:
        return result

    score = vpd / med
    result["outlier_score"] = score
    result["outlier_log2"] = math.log2(score) if score > 0 else float("-inf")
    if not math.isfinite(result["outlier_log2"]):
        result["outlier_log2"] = float("nan")
    result["outlier_confidence"] = min(1.0, n_base / float(CONFIDENCE_FULL_N))
    return result


# ---------------------------------------------------------------- pipeline

def harvest(niche, query=None, channel_ids=None, limit=60, baseline_limit=60,
            deepen_channels=True, fetch_thumbs=True, out_root=None,
            max_thumbs=None, progress=True):
    """Run a full harvest pass and write thumbs/, harvest.jsonl, channels.json.

    When deepen_channels is True a SECOND pass calls channel_videos on every
    distinct channel that appeared. This is not optional for honest scoring: a
    search returns at most a handful of videos per channel, and an outlier score
    is impossible without that channel's own baseline. It is also the expensive
    part - one yt-dlp invocation per channel, roughly 5-20s each - so its
    progress is printed rather than sat on silently.

    Videos whose thumbnail could not be fetched are still written, with
    thumb_path None, so what was skipped is visible rather than silently missing.
    """
    started = utc_now()
    t0 = time.time()
    if out_root is None:
        d = niche_dir(niche, create=True)
    else:
        # normpath, not os.path.join(x, "") + rstrip("/"): the old form turned
        # a drive root "C:/" into "C:", which on Windows means "the current
        # directory on C:" and is not the same place at all.
        d = os.path.abspath(str(out_root)).replace("\\", "/")
        if d.endswith("/") and not d.endswith(":/"):
            d = d[:-1]
        for sub in ("", "/thumbs", "/critique"):
            os.makedirs(d + sub, exist_ok=True)
    thumbs_dir = d + "/thumbs"
    warnings = []

    now = time.time()
    rows_by_id = {}

    def _absorb(raw_rows, src):
        """Merge rows in, returning (n_raw, n_new).

        Both counts, because the old single count was 'new unique rows' and the
        caller printed it as 'videos' and warned "returned no rows" whenever it
        was 0 - which is also what happens when a listing returns 60 rows that
        were all already held. That warning was a false statement about the
        network.

        Provenance accumulates as "search:q|baseline:UCxx" rather than being
        frozen at first sight: channel_baseline refuses to build a baseline out
        of search hits alone, and it can only see that if a row that was later
        confirmed by a channel listing says so.
        """
        n_raw = 0
        n_new = 0
        for raw in raw_rows:
            n_raw += 1
            row = normalise_row(raw, source_query=src, now_utc=now)
            vid = row["video_id"]
            if not vid:
                continue
            prev = rows_by_id.get(vid)
            if prev is None:
                rows_by_id[vid] = row
                n_new += 1
                continue
            if not prev.get("channel_id") and row.get("channel_id"):
                # Keep the richer identity. A channel-listing row can supply the
                # channel a search row somehow lacked, and vice versa.
                row["source_query"] = prev.get("source_query") or src
                rows_by_id[vid] = row
                prev = row
            srcs = [s for s in str(prev.get("source_query") or "").split("|") if s]
            if src not in srcs:
                srcs.append(src)
                prev["source_query"] = "|".join(srcs)
        return n_raw, n_new

    # --- pass 1: the requested population -----------------------------------
    if query:
        if progress:
            sys.stderr.write("[harvest] search: %s (limit %d)\n" % (query, limit))
        n_raw, n_new = _absorb(search_videos(query, limit=limit),
                               "search:%s" % query)
        if progress:
            sys.stderr.write("[harvest]   %d rows, %d new\n" % (n_raw, n_new))
        if n_raw == 0:
            warnings.append("search returned no rows for %r" % query)
        else:
            warnings.append(
                "search results are ranked by YouTube relevance, which is itself a "
                "popularity signal: this population is biased toward winners")

    for cid in (channel_ids or []):
        if progress:
            sys.stderr.write("[harvest] channel: %s\n" % cid)
        n_raw, n_new = _absorb(channel_videos(cid, limit=limit),
                               "channel:%s" % cid)
        if progress:
            sys.stderr.write("[harvest]   %d rows, %d new\n" % (n_raw, n_new))
        if n_raw == 0:
            warnings.append("channel %s returned no rows" % cid)

    # --- pass 2: deepen every channel seen, for baselines --------------------
    if deepen_channels:
        seen = set()
        for cid in (channel_ids or []):
            seen.add(str(cid))
        todo = []
        for row in list(rows_by_id.values()):
            cid = row.get("channel_id")
            if cid and str(cid).startswith("UC") and cid not in seen:
                seen.add(cid)
                todo.append(cid)
        for i, cid in enumerate(todo, 1):
            if progress:
                sys.stderr.write("[harvest] baseline %d/%d %s\n" % (i, len(todo), cid))
            _absorb(channel_videos(cid, limit=baseline_limit), "baseline:%s" % cid)

    rows = list(rows_by_id.values())
    if not rows:
        warnings.append("no videos harvested at all")

    # --- scoring -------------------------------------------------------------
    baselines = channel_baseline(rows)
    for row in rows:
        row.update(outlier_score(row, baselines))

    n_usable = sum(1 for b in baselines.values() if b.get("usable"))
    if n_usable == 0 and rows:
        # Say WHICH gate closed. "no channel has 5 settled videos" was printed
        # even when the channels had twenty settled videos and were rejected
        # for being search-only, which sends anyone reading it to the wrong fix.
        reasons = {}
        for b in baselines.values():
            r = b.get("unusable_reason") or "unknown"
            reasons[r] = reasons.get(r, 0) + 1
        warnings.append(
            "no channel produced a usable baseline: every outlier_score is NaN "
            "(%s)" % "; ".join("%d %s" % (v, k) for k, v in sorted(reasons.items())))
    n_search_only = sum(1 for b in baselines.values() if b.get("search_only"))
    if n_search_only:
        warnings.append(
            "%d of %d channels were seen only through a search, so their "
            "medians would be medians of winners: scored NaN. Re-run with "
            "deepen_channels=True to give them a real baseline."
            % (n_search_only, len(baselines)))

    # --- thumbnails ----------------------------------------------------------
    n_thumb = 0
    bad_ids = [r["video_id"] for r in rows if not _is_video_id(r["video_id"])]
    if bad_ids:
        warnings.append("%d rows had an unusable video id and were left "
                        "without a thumbnail: %s" % (len(bad_ids), bad_ids[:5]))
    if fetch_thumbs:
        # Score-ordered so that a max_thumbs cap keeps the most informative
        # videos rather than an arbitrary slice.
        order = sorted(rows, key=lambda r: (
            0 if math.isfinite(r.get("outlier_score", float("nan"))) else 1,
            -(r.get("outlier_score") if math.isfinite(
                r.get("outlier_score", float("nan"))) else 0.0)))
        # `is not None`, not truthiness: max_thumbs=0 means "fetch none" and
        # the old `if max_thumbs:` read it as "no cap" and fetched all of them.
        if max_thumbs is not None:
            order = order[:max(0, int(max_thumbs))]
        total = len(order)
        os.makedirs(thumbs_dir, exist_ok=True)
        for i, row in enumerate(order, 1):
            if not _is_video_id(row["video_id"]):
                continue          # already recorded in warnings above
            got = fetch_thumbnail(row["video_id"], thumbs_dir)
            row["thumb_path"] = got["path"]
            row["thumb_quality"] = got["quality"]
            row["thumb_w"] = got["width"]
            row["thumb_h"] = got["height"]
            row["thumb_http_status"] = got["http_status"]
            if got["path"]:
                n_thumb += 1
            elif progress:
                sys.stderr.write("  no thumbnail for %s (last status %s)\n"
                                 % (row["video_id"], got["http_status"]))
            if progress and (i % 10 == 0 or i == total):
                sys.stderr.write("[harvest] thumbs %d/%d (%d ok)\n"
                                 % (i, total, n_thumb))
    else:
        # No network, but a previous run's files are still on disk. Writing
        # thumb_path=None over a thumbnail that exists is a false statement
        # about the row, and it is free to check.
        for row in rows:
            p = "%s/%s.jpg" % (thumbs_dir, row["video_id"])
            if _is_video_id(row["video_id"]) and os.path.isfile(p) \
                    and os.path.getsize(p) > 0:
                meta = read_json(p + ".meta.json", default={}) or {}
                row["thumb_path"] = p
                row["thumb_quality"] = meta.get("quality") or "cached"
                row["thumb_w"] = meta.get("width")
                row["thumb_h"] = meta.get("height")
                n_thumb += 1

    # --- persist -------------------------------------------------------------
    rows.sort(key=lambda r: (
        -(r["outlier_score"] if math.isfinite(
            r.get("outlier_score", float("nan"))) else -1.0),
        -(r["views_per_day"] if math.isfinite(
            r.get("views_per_day", float("nan"))) else -1.0)))

    harvest_jsonl = d + "/harvest.jsonl"
    channels_json = d + "/channels.json"
    write_jsonl(harvest_jsonl, [{k: r.get(k) for k in HARVEST_KEYS} for r in rows])
    write_csv(d + "/harvest.csv", rows, HARVEST_KEYS)
    write_json(channels_json, {
        "schema_version": SCHEMA_VERSION,
        "generated_utc": utc_now(),
        "settle_days": SETTLE_DAYS,
        "min_baseline": MIN_BASELINE,
        "min_percentile_n": MIN_PERCENTILE_N,
        "confidence_full_n": CONFIDENCE_FULL_N,
        "outlier_basis": OUTLIER_BASIS,
        "baseline_method": BASELINE_METHOD,
        "channels": baselines,
    })

    n_settled = sum(1 for r in rows if r.get("settled"))
    manifest = {
        "niche": niche,
        "dir": d,
        "n_found": len(rows),
        "n_with_thumb": n_thumb,
        "n_settled": n_settled,
        "n_scored": sum(1 for r in rows
                        if math.isfinite(r.get("outlier_score", float("nan")))),
        "n_channels": len(baselines),
        "n_usable_channels": n_usable,
        "n_search_only_channels": n_search_only,
        "harvest_jsonl": harvest_jsonl,
        "channels_json": channels_json,
        "elapsed_s": round(time.time() - t0, 1),
        "warnings": warnings,
    }
    run_manifest(niche, "harvest",
                 {"query": query, "channel_ids": list(channel_ids or []),
                  "limit": limit, "baseline_limit": baseline_limit,
                  "deepen_channels": deepen_channels,
                  "fetch_thumbs": fetch_thumbs, "max_thumbs": max_thumbs},
                 {k: manifest[k] for k in
                  ("n_found", "n_with_thumb", "n_settled", "n_scored",
                   "n_channels", "n_usable_channels")},
                 started_utc=started, ok=bool(rows))
    return manifest


def load_harvest(niche):
    """The only sanctioned reader of harvest.jsonl.

    Raises on a schema_version mismatch: scoring against rows written by a
    different vocabulary silently compares the wrong things.
    """
    path = niche if str(niche).endswith(".jsonl") else \
        niche_dir(niche, create=False) + "/harvest.jsonl"
    rows = read_jsonl(path, nan_keys=_NAN_KEYS)
    for i, row in enumerate(rows, 1):
        sv = row.get("schema_version")
        if sv is None:
            continue
        try:
            sv_i = int(sv)
        except (TypeError, ValueError):
            # A non-numeric schema_version is a corrupt or foreign file. Raise
            # with the value in hand; int(sv) alone raised a ValueError whose
            # message named neither the file nor the line.
            raise ValueError(
                "harvest.jsonl line %d has a non-numeric schema_version %r (%s)"
                % (i, sv, path))
        if sv_i != SCHEMA_VERSION:
            raise ValueError(
                "harvest.jsonl schema_version %s != %d (%s) - re-run the harvest"
                % (sv, SCHEMA_VERSION, path))
    return rows


def join_measurements(harvest_rows, measure_rows):
    """Inner-join harvest.video_id == measure.image_id.

    Lives here rather than in grammar.py because styles.py and critique.py need
    the identical join and must not each write their own subtly different one.
    Rows carrying measure_error are dropped: a row whose features are all NaN
    would otherwise be counted as a video that contributed evidence.

    Returns (merged_rows, counts). Measurement keys win on a key collision,
    except that harvest's identity keys are re-applied afterwards, so a merged
    row always carries the real channel and outlier score.
    """
    by_id = {}
    n_dup = 0
    for m in measure_rows:
        mid = m.get("image_id")
        if not mid:
            continue
        if str(mid) in by_id:
            # Last one wins, as before, but it is now COUNTED. Silently
            # collapsing two measurements of the same image is how a
            # measure.py bug becomes invisible in the join.
            n_dup += 1
        by_id[str(mid)] = m

    merged = []
    n_err = 0
    n_unmatched_h = 0
    for h in harvest_rows:
        vid = str(h.get("video_id") or "")
        m = by_id.get(vid)
        if m is None:
            n_unmatched_h += 1
            continue
        if m.get("measure_error"):
            n_err += 1
            continue
        row = dict(h)
        row.update(m)
        for k in HARVEST_KEYS:
            row[k] = h.get(k)
        merged.append(row)

    # Unmatched means "no harvest row has this id" - measured against the
    # harvest ids, NOT against the merged output. The old version compared with
    # the merged ids, so a measurement that DID match a harvest row but was
    # dropped for measure_error was counted twice: once as
    # n_dropped_measure_error and again as n_measure_unmatched. Two counts of
    # the same row, in a dict whose whole job is to say where rows went.
    harvest_ids = {str(h.get("video_id") or "") for h in harvest_rows}
    n_unmatched_m = sum(1 for m in measure_rows
                        if str(m.get("image_id") or "") not in harvest_ids)
    counts = {
        "n_harvest": len(harvest_rows),
        "n_measure": len(measure_rows),
        "n_joined": len(merged),
        "n_dropped_measure_error": n_err,
        "n_harvest_unmatched": n_unmatched_h,
        "n_measure_unmatched": n_unmatched_m,
        "n_measure_duplicate_ids": n_dup,
    }
    return merged, counts


# ---------------------------------------------------------------- rendering

def _fmt(v, spec="%.2f", dash="-"):
    if v is None:
        return dash
    if isinstance(v, float) and not math.isfinite(v):
        return dash
    try:
        return spec % v
    except (TypeError, ValueError):
        return str(v)


def safe_print(text):
    """print() that cannot die on a competitor's title.

    MEASURED on this interpreter: sys.stdout is cp1252 with errors
    'surrogateescape', so an em-dash prints as a replacement character and
    nothing raises - the harvested title itself is intact UTF-8 in
    harvest.jsonl (verified: U+2014 stored, no U+FFFD). Under a stdout opened
    with errors='strict' the same print is a UnicodeEncodeError, and losing a
    finished harvest to the last print in the run would be absurd. The data is
    never touched; only this one rendering is made lossy.
    """
    try:
        print(text)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(str(text).encode(enc, "replace").decode(enc, "replace"))


def render_table(rows, top_n=None, width=118):
    """Plain-text table of a harvest, ranked by outlier score.

    Printed by the CLI so the module shows its own state instead of leaving
    anyone to open a JSONL file to find out whether it worked.
    """
    rows = list(rows)
    if top_n:
        rows = rows[:int(top_n)]
    head = ("%-7s %-9s %8s %7s %6s %-4s %-13s %-11s %s"
            % ("OUTLIER", "conf", "views", "vpd", "age_d", "thmb", "video_id",
               "channel", "title"))
    lines = [head, "-" * min(width, len(head) + 40)]
    for r in rows:
        title = (r.get("title") or "")[:36]
        chan = (r.get("channel") or "?")[:11]
        q = (r.get("thumb_quality") or "-")
        qshort = {"maxresdefault": "max", "hq720": "hq72", "mqdefault": "mq",
                  "sddefault": "sd", "hqdefault": "hq", "cached": "cach"}.get(q, q[:4])
        lines.append("%-7s %-9s %8s %7s %6s %-4s %-13s %-11s %s" % (
            _fmt(r.get("outlier_score"), "%.2fx"),
            _fmt(r.get("outlier_confidence"), "%.2f"),
            _fmt(r.get("view_count"), "%d"),
            _fmt(r.get("views_per_day"), "%.1f"),
            _fmt(r.get("age_days"), "%.0f"),
            qshort,
            r.get("video_id") or "?",
            chan,
            title))
    return "\n".join(lines)


def render_channels(baselines):
    """One line per channel baseline, so an unusable baseline is visible.

    Prints the channel's OWN reason for being unusable. The old version printed
    "NO (< 5 settled)" for every rejection including the search-only ones,
    which named a cause that was often not the cause.
    """
    lines = ["%-26s %-7s %-7s %9s %9s  %s"
             % ("channel", "n_tot", "n_sett", "med_vpd", "med_views", "usable")]
    lines.append("-" * 78)
    for ch, b in sorted(baselines.items(),
                        key=lambda kv: -(_finite((kv[1] or {}).get("n_settled")) or 0)):
        b = b or {}
        lines.append("%-26s %-7d %-7d %9s %9s  %s" % (
            (b.get("channel") or ch or "?")[:26],
            # int(_finite(...) or 0): a baseline read back from channels.json
            # can carry null here, and "%d" % None is a TypeError that killed
            # the whole table.
            int(_finite(b.get("n_total")) or 0),
            int(_finite(b.get("n_settled")) or 0),
            _fmt(b.get("median_vpd"), "%.1f"),
            _fmt(b.get("median_views"), "%.0f"),
            "yes" if b.get("usable")
            else "NO (%s)" % (b.get("unusable_reason") or "unusable")))
    return "\n".join(lines)


# ---------------------------------------------------------------- cli

TTT_CHANNEL = "UCT5Fde6OzBSFRmxw5mPn2CA"     # Texas Trial Tracker
KNOWN_GOOD_ID = "OGj_eLUXjrk"                # verified 200, 1280x720, 140705 B
KNOWN_404_ID = "AAAAAAAAAAA"                 # verified 404 on every variant


def selftest():
    """Prove the module's claims rather than assert them.

    Offline-safe: the network checks print SELFTEST_SKIP instead of failing when
    there is no connection, because a failing selftest must mean broken code,
    not a dropped wifi link.
    """
    ok = True
    notes = []

    # --- pure logic, no network ---------------------------------------------
    now = time.time()
    fake = normalise_row({"id": "x" * 11, "title": "t", "view_count": 1000,
                          "duration": 30, "timestamp": now - 10 * 86400},
                         source_query="unit", now_utc=now)
    if not (abs(fake["age_days"] - 10.0) < 0.01 and abs(fake["views_per_day"] - 100.0) < 0.5):
        ok = False
        notes.append("normalise_row age/vpd wrong: %s / %s"
                     % (fake["age_days"], fake["views_per_day"]))
    if not fake["is_short"] or not fake["settled"]:
        ok = False
        notes.append("normalise_row is_short/settled wrong")

    # The field-name asymmetry that would silently null every channel harvest.
    chrow = normalise_row({"id": "y" * 11, "title": "t", "channel_id": None,
                           "playlist_channel_id": TTT_CHANNEL,
                           "playlist_channel": "Texas Trial Tracker",
                           "view_count": 10, "timestamp": now - 30 * 86400}, now_utc=now)
    if chrow["channel_id"] != TTT_CHANNEL:
        ok = False
        notes.append("normalise_row did not read playlist_channel_id")

    # A 3-video channel must be unusable, and its videos unscored.
    synth = [normalise_row({"id": "a%d" % i, "title": "t", "channel_id": "UCsynthetic",
                            "view_count": 100 * (i + 1),
                            "timestamp": now - (30 + i) * 86400}, now_utc=now)
             for i in range(3)]
    b3 = channel_baseline(synth)
    if b3["UCsynthetic"]["usable"]:
        ok = False
        notes.append("3-video channel reported usable")
    s3 = outlier_score(synth[0], b3)
    if math.isfinite(s3["outlier_score"]):
        ok = False
        notes.append("unusable channel produced a finite outlier_score")

    # 12 videos all running at EXACTLY 1000 views/day: views must scale with age,
    # or the population's vpd varies and "median pace" means nothing. (The first
    # version of this check held views constant instead and asserted a band it
    # had no right to expect - the test was wrong, not the code.)
    synth12 = [normalise_row({"id": "b%d" % i, "title": "t", "channel_id": "UCbig",
                              "view_count": 1000 * (30 + i),
                              "timestamp": now - (30 + i) * 86400},
                             now_utc=now) for i in range(12)]
    b12 = channel_baseline(synth12)
    if not b12["UCbig"]["usable"]:
        ok = False
        notes.append("12-video channel reported unusable")
    if abs(b12["UCbig"]["median_vpd"] - 1000.0) > 1.0:
        ok = False
        notes.append("baseline median_vpd wrong: %s" % b12["UCbig"]["median_vpd"])
    s12 = outlier_score(synth12[0], b12)
    if not (abs(s12["outlier_score"] - 1.0) < 0.01 and abs(s12["outlier_log2"]) < 0.02):
        ok = False
        notes.append("median-pace video did not score 1.0x: %s" % s12["outlier_score"])
    # 11, not 12: the row being scored is removed from its own baseline, so the
    # confidence is the size of the divisor that was ACTUALLY used.
    if abs(s12["outlier_confidence"] - 11 / float(CONFIDENCE_FULL_N)) > 1e-9:
        ok = False
        notes.append("outlier_confidence not n_baseline/%d: %s"
                     % (CONFIDENCE_FULL_N, s12["outlier_confidence"]))
    if s12["channel_n_baseline"] != 11:
        ok = False
        notes.append("leave-one-out did not remove the row from its own "
                     "baseline: n=%s" % s12["channel_n_baseline"])

    # A video at exactly twice the channel's pace must score 2.0x / log2 = +1.0,
    # and one at half must score 0.5x / log2 = -1.0. This is the check that the
    # score means what the docstring says it means.
    dbl = normalise_row({"id": "d1", "title": "t", "channel_id": "UCbig",
                         "view_count": 2000 * 30, "timestamp": now - 30 * 86400},
                        now_utc=now)
    half = normalise_row({"id": "d2", "title": "t", "channel_id": "UCbig",
                          "view_count": 500 * 30, "timestamp": now - 30 * 86400},
                         now_utc=now)
    sd, sh = outlier_score(dbl, b12), outlier_score(half, b12)
    if not (abs(sd["outlier_score"] - 2.0) < 0.01 and abs(sd["outlier_log2"] - 1.0) < 0.02):
        ok = False
        notes.append("2x-pace video scored %s" % sd["outlier_score"])
    if not (abs(sh["outlier_score"] - 0.5) < 0.01 and abs(sh["outlier_log2"] + 1.0) < 0.02):
        ok = False
        notes.append("0.5x-pace video scored %s" % sh["outlier_score"])

    # An unsettled video must never be scored, however well it is doing.
    fresh = normalise_row({"id": "c1", "title": "t", "channel_id": "UCbig",
                           "view_count": 999999, "timestamp": now - 2 * 86400},
                          now_utc=now)
    if math.isfinite(outlier_score(fresh, b12)["outlier_score"]):
        ok = False
        notes.append("unsettled video was scored")

    # --- the hardening checks, each one a bug this module actually had -------

    # 1. Self-inclusion. 100/200/300/400/5000 -> the 5000 must score 20.00x
    #    against the other four, not 16.67x against a median it is inside.
    pop = [normalise_row({"id": "p%d" % i, "title": "t", "channel_id": "UCp",
                          "view_count": v * 30, "timestamp": now - 30 * 86400},
                         now_utc=now)
           for i, v in enumerate([100, 200, 300, 400, 5000])]
    bp = channel_baseline(pop)
    loo = outlier_score(pop[4], bp)
    if math.isfinite(loo["outlier_score"]):
        ok = False
        notes.append("5-video channel scored its OWN member: only 4 videos "
                     "would be left in the baseline (got %s)" % loo["outlier_score"])
    pop6 = pop + [normalise_row({"id": "p9", "title": "t", "channel_id": "UCp",
                                 "view_count": 250 * 30,
                                 "timestamp": now - 30 * 86400}, now_utc=now)]
    b6 = channel_baseline(pop6)
    loo6 = outlier_score(pop6[4], b6)
    if not (abs(loo6["outlier_score"] - 20.0) < 0.01):
        ok = False
        notes.append("leave-one-out score wrong: %s (want 20.00x)"
                     % loo6["outlier_score"])

    # 2. A channel seen ONLY through a search must not get a baseline. Its
    #    median is a median of winners and every ratio lands near 1.0.
    srows = [normalise_row({"id": "q%d" % i, "title": "t", "channel_id": "UCsearch",
                            "view_count": 1000 * (30 + i),
                            "timestamp": now - (30 + i) * 86400},
                           source_query="search:foo", now_utc=now)
             for i in range(8)]
    bs = channel_baseline(srows)
    if bs["UCsearch"]["usable"] or not bs["UCsearch"]["search_only"]:
        ok = False
        notes.append("search-only channel was treated as a baseline")
    if math.isfinite(outlier_score(srows[0], bs)["outlier_score"]):
        ok = False
        notes.append("search-only channel produced a finite outlier_score")
    for r in srows:
        r["source_query"] = r["source_query"] + "|baseline:UCsearch"
    if not channel_baseline(srows)["UCsearch"]["usable"]:
        ok = False
        notes.append("channel confirmed by a listing was still treated as "
                     "search-only")

    # 3. Quartiles must not be reported from one observation.
    solo = [normalise_row({"id": "s1", "title": "t", "channel_id": "UCsolo",
                           "view_count": 100, "timestamp": now - 30 * 86400},
                          now_utc=now)]
    bsolo = channel_baseline(solo)["UCsolo"]
    if math.isfinite(bsolo["p25_vpd"]) or math.isfinite(bsolo["p75_vpd"]):
        ok = False
        notes.append("p25/p75 reported from %d settled video(s)"
                     % bsolo["n_settled"])

    # 4. Values that survived a JSON round trip: NaN comes back as null and a
    #    whole float comes back looking like an int. Neither may crash, and
    #    neither may silently produce NaN where a number is available.
    jbase = {"UCj": {"n_settled": 9, "median_vpd": 10, "usable": True,
                     "min_videos": 5}}
    jrow = normalise_row({"id": "j1", "channel_id": "UCj", "view_count": 20 * 30,
                          "timestamp": now - 30 * 86400}, now_utc=now)
    if abs(outlier_score(jrow, jbase)["outlier_score"] - 2.0) > 0.01:
        ok = False
        notes.append("an int median_vpd from JSON scored NaN")
    nbase = {"UCj": {"n_settled": 9, "median_vpd": None, "usable": True}}
    try:
        if math.isfinite(outlier_score(jrow, nbase)["outlier_score"]):
            ok = False
            notes.append("a null median_vpd produced a finite score")
    except Exception as exc:                                  # noqa: BLE001
        ok = False
        notes.append("null median_vpd raised %s" % type(exc).__name__)
    try:
        channel_baseline([{"channel_id": "UCn", "settled": True,
                           "views_per_day": None, "view_count": None,
                           "video_id": "n1"}])
        render_channels({"UCn": {"channel": None, "n_total": None,
                                 "n_settled": None, "median_vpd": None,
                                 "median_views": None, "usable": False}})
        render_table([{"video_id": "n1", "title": None, "channel": None,
                       "outlier_score": None, "view_count": None}])
    except Exception as exc:                                  # noqa: BLE001
        ok = False
        notes.append("None-bearing rows crashed rendering/baseline: %s: %s"
                     % (type(exc).__name__, exc))

    # 5. A timestamp of 0 is not a 1970 upload.
    if math.isfinite(normalise_row({"id": "z1", "view_count": 10,
                                    "timestamp": 0}, now_utc=now)["age_days"]):
        ok = False
        notes.append("timestamp=0 was treated as a real upload date")

    # 6. An id that is not base64url is a directory escape or an OSError, and
    #    must raise rather than write somewhere unexpected.
    for badid in ("../evil", "a:b?c", "", None):
        try:
            fetch_thumbnail(badid, WORK_ROOT + "/_selftest/thumbs")
            ok = False
            notes.append("fetch_thumbnail accepted the id %r" % (badid,))
        except ValueError:
            pass

    # 7. join_measurements must not count one row twice.
    jm_h = [{"video_id": "v1"}, {"video_id": "v2"}]
    jm_m = [{"image_id": "v1", "measure_error": "boom"}, {"image_id": "zz"},
            {"image_id": "v2"}, {"image_id": "v2"}]
    _, jc = join_measurements(jm_h, jm_m)
    if jc["n_measure_unmatched"] != 1 or jc["n_dropped_measure_error"] != 1 \
            or jc["n_measure_duplicate_ids"] != 1 or jc["n_joined"] != 1:
        ok = False
        notes.append("join_measurements counts double-count a row: %s" % jc)

    print("logic checks: %s" % ("PASS" if ok else "FAIL"))

    # --- image edge cases, offline ------------------------------------------
    # Every one of these is a file that can genuinely appear in thumbs/: a 1x1
    # placeholder, a truncated download, a flat grey placeholder served with
    # HTTP 200, a grayscale frame, and a name that is not a file at all.
    edge = WORK_ROOT + "/_selftest/edge"
    os.makedirs(edge, exist_ok=True)
    if _np is not None and _cv2 is not None:
        cases = {
            "onepx": _np.zeros((1, 1, 3), _np.uint8),
            "small": _np.random.randint(0, 255, (120, 200, 3), dtype=_np.uint8),
            "flatgrey": _np.full((720, 1280, 3), 127, _np.uint8),
            "real": _np.random.randint(0, 255, (720, 1280, 3), dtype=_np.uint8),
        }
        want = {"onepx": False, "small": False, "flatgrey": False, "real": True}
        for name, img in cases.items():
            _cv2.imwrite(edge + "/%s.jpg" % name, img)
            with open(edge + "/%s.jpg" % name, "rb") as fh:
                w, h, good = _decode_check(fh.read())
            if good != want[name]:
                ok = False
                notes.append("_decode_check(%s) = %s, wanted %s"
                             % (name, good, want[name]))
        gray = _cv2.cvtColor(cases["real"], _cv2.COLOR_BGR2GRAY)
        _cv2.imwrite(edge + "/gray.jpg", gray)
        with open(edge + "/gray.jpg", "rb") as fh:
            gw, gh, ggood = _decode_check(fh.read())
        if not ggood or gw != 1280 or gh != 720:
            ok = False
            notes.append("a grayscale thumbnail was rejected: %s %sx%s"
                         % (ggood, gw, gh))
        with open(edge + "/trunc.jpg", "wb") as fh:
            fh.write(b"\xff\xd8\xff\xe0 not actually a jpeg")
        with open(edge + "/trunc.jpg", "rb") as fh:
            if _decode_check(fh.read())[2]:
                ok = False
                notes.append("a truncated JPEG passed _decode_check")
        # A cached file that fails the check must be re-fetched, not returned.
        offline = fetch_thumbnail("onepx", edge, qualities=(), fallbacks=())
        if offline["path"] is not None:
            ok = False
            notes.append("a 1x1 cached file was served as a thumbnail")
        cached = fetch_thumbnail("real", edge, qualities=(), fallbacks=())
        if not cached["cached"] or cached["http_status"] is not None:
            ok = False
            notes.append("cache hit reported http_status=%r for a request it "
                         "never made" % cached["http_status"])
        print("edge images  : 1x1/small/flat-grey/truncated rejected, "
              "grayscale %dx%d accepted, cache hit reports status=%r"
              % (gw, gh, cached["http_status"]))
    else:
        print("SELFTEST_SKIP no cv2: image edge cases not checked")

    # A missing file and an empty folder must both be quiet non-events.
    empty = WORK_ROOT + "/_selftest/empty"
    os.makedirs(empty, exist_ok=True)
    for f in os.listdir(empty):
        try:
            os.remove(empty + "/" + f)
        except OSError:
            pass
    miss = fetch_thumbnail("MissingFile1", empty, qualities=(), fallbacks=())
    if miss["path"] is not None or miss["http_status"] is not None:
        ok = False
        notes.append("a missing file did not fall through cleanly: %s" % miss)
    man_empty = harvest("selftest-empty", channel_ids=[], query=None,
                        deepen_channels=False, fetch_thumbs=True,
                        progress=False)
    if man_empty["n_found"] != 0 or man_empty["n_scored"] != 0:
        ok = False
        notes.append("an empty harvest reported %s" % man_empty)
    if load_harvest("selftest-empty") != []:
        ok = False
        notes.append("an empty harvest.jsonl did not read back empty")
    print("empty run    : n_found=0, files written, warnings=%s"
          % man_empty["warnings"])

    # max_thumbs=0 must mean zero, not "no cap".
    man_zero = harvest("selftest-empty", channel_ids=[], query=None,
                       deepen_channels=False, fetch_thumbs=True, max_thumbs=0,
                       progress=False)
    if man_zero["n_with_thumb"] != 0:
        ok = False
        notes.append("max_thumbs=0 fetched %d thumbnails" % man_zero["n_with_thumb"])

    # --- network -------------------------------------------------------------
    tmp = WORK_ROOT + "/_selftest/thumbs"
    net_ok = True
    got = fetch_thumbnail(KNOWN_GOOD_ID, tmp, overwrite=True)
    if got["path"] is None:
        net_ok = False
        print("SELFTEST_SKIP no network (known-good thumbnail unreachable, status %s)"
              % got["http_status"])
    else:
        print("thumbnail %s -> %s %dx%d %d bytes"
              % (KNOWN_GOOD_ID, got["quality"], got["width"] or 0,
                 got["height"] or 0, got["bytes"]))
        if got["width"] != 1280 or got["height"] != 720:
            ok = False
            notes.append("known-good thumbnail not 1280x720")

        # The 404 must step down the whole ladder and write nothing.
        bad = fetch_thumbnail(KNOWN_404_ID, tmp, overwrite=True)
        bad_path = "%s/%s.jpg" % (tmp, KNOWN_404_ID)
        print("bogus id %s -> path=%s status=%s file_written=%s"
              % (KNOWN_404_ID, bad["path"], bad["http_status"],
                 os.path.exists(bad_path)))
        if bad["path"] is not None or os.path.exists(bad_path):
            ok = False
            notes.append("404 id produced a file")

        # Cache must not re-download.
        again = fetch_thumbnail(KNOWN_GOOD_ID, tmp)
        if not again.get("cached"):
            ok = False
            notes.append("second fetch was not served from cache")
        else:
            print("cache: second fetch of %s served from disk, no download"
                  % KNOWN_GOOD_ID)

    # --- integration: the real Texas Trial Tracker channel -------------------
    if net_ok:
        print("\n--- integration: harvesting Texas Trial Tracker (%s) ---" % TTT_CHANNEL)
        man = harvest("selftest-ttt", channel_ids=[TTT_CHANNEL], limit=60,
                      deepen_channels=False, fetch_thumbs=True, progress=True)
        rows = load_harvest("selftest-ttt")
        safe_print("\n" + render_table(rows))
        safe_print("\n" + render_channels(
            (read_json(man["channels_json"], default={}) or {}).get("channels", {})))
        # os.listdir on a directory that was never created is a crash in the
        # selftest itself, which would read as "the harvest is broken".
        tdir = man["dir"] + "/thumbs"
        thumbs = ([f for f in os.listdir(tdir) if f.endswith(".jpg")]
                  if os.path.isdir(tdir) else [])
        print("\nharvest.jsonl : %s (%d rows)" % (man["harvest_jsonl"], len(rows)))
        print("thumbs on disk: %d files in %s/thumbs" % (len(thumbs), man["dir"]))
        print("counts        : found=%d with_thumb=%d settled=%d scored=%d "
              "channels=%d usable=%d  (%.1fs)"
              % (man["n_found"], man["n_with_thumb"], man["n_settled"],
                 man["n_scored"], man["n_channels"], man["n_usable_channels"],
                 man["elapsed_s"]))
        for w in man["warnings"]:
            print("warning       : %s" % w)

        if man["n_found"] < 5:
            ok = False
            notes.append("TTT harvest found only %d videos" % man["n_found"])
        if man["n_with_thumb"] < man["n_found"]:
            notes.append("%d of %d videos have no thumbnail"
                         % (man["n_found"] - man["n_with_thumb"], man["n_found"]))
        if len(thumbs) < man["n_with_thumb"]:
            ok = False
            notes.append("thumbnail files missing from disk: %d on disk, %d claimed"
                         % (len(thumbs), man["n_with_thumb"]))
        # Every row must carry the full frozen schema.
        missing = [k for k in HARVEST_KEYS if rows and k not in rows[0]]
        if missing:
            ok = False
            notes.append("harvest row missing keys: %s" % missing)
        # join_measurements must survive a measure.py that has not run yet.
        merged, counts = join_measurements(rows, [])
        if merged or counts["n_joined"] != 0:
            ok = False
            notes.append("join_measurements wrong on empty measurements")
        fake_m = [{"image_id": rows[0]["video_id"], "lum_mean": 42.0},
                  {"image_id": "nope", "lum_mean": 1.0, "measure_error": "x"}]
        merged, counts = join_measurements(rows, fake_m)
        if len(merged) != 1 or merged[0].get("lum_mean") != 42.0 \
                or merged[0].get("outlier_basis") != OUTLIER_BASIS:
            ok = False
            notes.append("join_measurements did not merge correctly: %s" % counts)
        else:
            print("join          : %s" % counts)

    for n in notes:
        print("note          : %s" % n)
    print(("SELFTEST_PASS  " if ok else "SELFTEST_FAIL  ") + "tools/thumbeng/harvest.py")
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="thumbeng.harvest",
                                 description="Harvest niche thumbnails and score outliers.")
    ap.add_argument("--niche", help="niche name; becomes work/thumbeng/<slug>")
    ap.add_argument("--query", help="search query for the niche")
    ap.add_argument("--channel", action="append", default=[],
                    help="channel id, @handle or URL (repeatable)")
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--baseline-limit", type=int, default=60)
    ap.add_argument("--no-deepen", action="store_true",
                    help="skip the per-channel baseline pass (fast, but every "
                         "outlier_score will be NaN unless channels were named)")
    ap.add_argument("--no-thumbs", action="store_true")
    ap.add_argument("--max-thumbs", type=int, default=None)
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--show", action="store_true",
                    help="print an existing harvest without re-running it")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.niche:
        ap.error("--niche is required (or use --selftest)")

    if args.show:
        rows = load_harvest(args.niche)
        safe_print(render_table(rows, top_n=args.top))
        ch = read_json(niche_dir(args.niche, create=False) + "/channels.json",
                       default={}) or {}
        safe_print("\n" + render_channels(ch.get("channels", {})))
        return 0

    if not args.query and not args.channel:
        ap.error("give --query and/or --channel")

    man = harvest(args.niche, query=args.query, channel_ids=args.channel,
                  limit=args.limit, baseline_limit=args.baseline_limit,
                  deepen_channels=not args.no_deepen,
                  fetch_thumbs=not args.no_thumbs, max_thumbs=args.max_thumbs)
    rows = load_harvest(args.niche)
    safe_print(render_table(rows, top_n=args.top))
    ch = read_json(man["channels_json"], default={}) or {}
    safe_print("\n" + render_channels(ch.get("channels", {})))
    print("\nfound=%d with_thumb=%d settled=%d scored=%d channels=%d usable=%d (%.1fs)"
          % (man["n_found"], man["n_with_thumb"], man["n_settled"], man["n_scored"],
             man["n_channels"], man["n_usable_channels"], man["elapsed_s"]))
    for w in man["warnings"]:
        print("warning: %s" % w)
    print("wrote: %s" % man["harvest_jsonl"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
