"""Does an audience for this case already exist, before we publish?

The rubric in `prompts/score_cases.md` reads the docket transcript and judges
the clip. It has no way to tell a status conference apart from a case the city
is already following, because that information is not in the transcript. This
module supplies that missing axis.

WHY IT EXISTS - measured off the channel on 2026-08-17, `yt-dlp
--flat-playlist` against @TexasTrialTracker/videos:

    72,000  Savanah Soto Capital Murder Trial - DNA Evidence, Bloody Money
    62,000  Christopher Preciado Found GUILTY - Reaction & Family Impact
    37,000  Deleted DMs Exposed a Killer's Plan | Day 6
     9,800  Drug Dealer BEGS Judge Boyd To Not Send Him To Prison
     4,300  Thug In Disbelief After Judge Boyd Sentences Him To Prison
     2,300  Judge Boyd EXPOSES Credit Card Fraud Scheme
     1,400  Judge Boyd SHUTS DOWN Gang Member's Early Probation Request

Every video over 10K is a named, press-covered capital murder trial. Routine
docket clips - which is what this pipeline produces - sit at 1.4K-4.6K. The
spread between the top trial video and a median docket clip is about 20x.

WHAT THIS IS NOT. It is a hypothesis off thirteen videos with a real confound:
the Soto series may have travelled because of the trial, or the timing, or
promotion, and those cannot be separated from this data. Nothing here is
validated against an outcome, because `publications` is empty and no view count
has ever been recorded against a clip this pipeline made. Treat the weights as
a starting position to be measured, not as findings.

WHERE IT SITS IN THE PIPELINE. Not a rubric weight - the rubric weights sum to
100 and are mirrored in the scoring prompt, so adding one silently dilutes the
rest. Notoriety is a property of the AUDIENCE, not of the clip, so it is
computed here in code, stored on the case, and used to rank cases that have
ALREADY passed the safety gate and the rubric. It never promotes a case past a
gate. SAFETY_RULES R7 stays in front of it, deliberately: this axis points
toward the most sensational cases about real, presumed-innocent people, and it
is the last thing that should be allowed to overrule the safety rules.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
from typing import Any

log = logging.getLogger("boydclips.notoriety")

# Charge severity tiers.
#
# Seeded from the channel's own spread above, not from a general theory of
# crime: homicide sits where the 72K/62K videos are, fraud and probation
# administration sit where the 1.4K-2.3K videos are, and drugs-with-a-plea sits
# between them because "Drug Dealer BEGS" reached 9.8K.
#
# This is keyword matching over the case summary, which is a PROXY. The county
# portal has the real charge codes - `records.case_detail()` returns them - and
# swapping this for those codes is the obvious upgrade once a case resolves to
# an encrypted_case_id. Keyword matching is what works today without a portal
# round-trip per candidate.
SEVERITY_TIERS: list[tuple[int, tuple[str, ...]]] = [
    (100, ("capital murder", "capital-murder")),
    (95, ("murder", "homicide", "manslaughter", "intoxication assault causing death")),
    # Charge PHRASES, not the bare word "child".
    #
    # MEASURED over-match, 2026-08-17: bare "child" fired on 7 of the top 10
    # banked cases - a shotgun fired at an adult son, a meth revocation, an
    # evading-arrest plea - because the word turns up incidentally in summaries
    # (child support, children present, a lecture about kids in cars). It put
    # every one of them at severity 85 and flattened the whole ranking to 72.
    # The offence has to be against a child, which takes a phrase to express.
    (85, ("child endangerment", "endangering a child", "abandoning a child",
          "abandoning/endangering", "injury to a child", "indecency with a child",
          "juvenile victim", "sexual assault", "trafficking", "child pornography")),
    (75, ("aggravated assault", "aggravated robbery", "kidnap", "deadly weapon",
          "shooting", "shot", "stabbing", "strangulation")),
    (65, ("assault", "family violence", "domestic", "robbery", "burglary of a habitation")),
    (55, ("felony dwi", "intoxication", "evading", "unlawful possession of a firearm")),
    (45, ("drug", "controlled substance", "possession", "delivery", "distribution")),
    (35, ("theft", "burglary", "fraud", "credit card", "forgery", "property")),
    (20, ("probation", "revocation", "status", "reset", "administrative", "bond")),
]

# LOCAL NEWS is the primary signal, and this was measured rather than assumed.
#
# Searching "Christopher Preciado court judge" returns KSAT 12 at 78,966 views,
# KENS 5 at 24,060, and six more from the same two newsrooms. Searching an
# ordinary docket defendant returns nothing from any of them. Local news
# deciding a case is worth a camera IS the audience existing in advance - it is
# a more direct measure of demand than a competitor's edit of the same footage.
LOCAL_NEWS_CHANNELS = (
    "KSAT", "KENS", "News 4", "WOAI", "FOX San Antonio", "KABB",
    "San Antonio Express-News", "Telemundo San Antonio", "Univision San Antonio",
)

# Court channels working the same courtrooms. Secondary, but when one exists
# its view count is a calibrated number from exactly this market.
COURT_CHANNELS = (
    "Audit the Court", "Courtroom", "Court Evidence", "AmericanJusticeFiles",
    "Law&Crime", "Law & Crime",
)


def _full_name_in(title: str, name: str) -> bool:
    """Require EVERY name token in the title, not just the surname.

    Measured trap: searching "Anthony Blackburn" surfaces Senator Marsha
    Blackburn at 55,837 views from Forbes Breaking News. Matching on surname
    alone would score a routine Bexar County docket case as nationally
    notorious and push it straight to the top of the day's ranking. Requiring
    the first name too drops every one of those rows and keeps the real hit -
    a 4-view Judge Boyd clip - which is the correct answer for that defendant.
    """
    low = title.lower()
    return all(tok in low for tok in name.lower().split() if len(tok) > 2)


def charge_severity(case: dict[str, Any]) -> tuple[int, str]:
    """Highest-matching severity tier for a case, with the phrase that matched.

    Reads the summary and charge-ish free text. Returns (score, why). Falls to
    the administrative floor rather than zero: an unmatched case is usually a
    routine setting, which is exactly what the bottom tier describes.
    """
    haystack = " ".join(str(case.get(k) or "") for k in (
        "summary", "charges", "charge", "proceeding_type", "hook_line",
        "shortable_reasoning",
    )).lower()

    for score, needles in SEVERITY_TIERS:
        for needle in needles:
            if needle in haystack:
                return score, f"matched {needle!r}"
    return 20, "no charge language matched - treated as a routine setting"


def _ytsearch(query: str, limit: int = 8, timeout: int = 90) -> list[dict[str, Any]]:
    """Search YouTube for a query, returning flat metadata rows.

    Uses the yt-dlp already required by the pipeline rather than the YouTube
    Data API, which this project cannot use for anything (see the audit note in
    config) and which would spend quota on a signal that does not need to be
    exact.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "yt_dlp", f"ytsearch{limit}:{query}",
         "--flat-playlist", "--no-warnings",
         "--print", '{"views":%(view_count)j,"channel":%(channel)j,"title":%(title)j}'],
        capture_output=True, text=True, timeout=timeout,
    )
    rows = []
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def existing_coverage(defendant_name: str | None, *, limit: int = 10) -> dict[str, Any]:
    """Has anyone already covered this defendant, and how big did it get?

    Separates local news from court channels because they mean different
    things: a newsroom sending a camera says the case matters to the city,
    while a court channel says the footage edits well. Both are evidence; the
    first is stronger.

    Asymmetric on purpose - a hit is strong evidence, a miss is weak. Neither
    newsrooms nor court channels cover every case, so an unfound defendant may
    still be notorious.
    """
    blank: dict[str, Any] = {
        "covered": False, "news_views": 0, "court_views": 0,
        "matches": [], "why": "",
    }
    name = (defendant_name or "").strip()
    # A bare first name matches half the county; require something specific.
    if len(name.split()) < 2:
        blank["why"] = "no usable defendant name"
        return blank

    try:
        rows = _ytsearch(f"{name} court judge", limit=limit)
    except Exception as exc:
        blank["why"] = f"search failed: {exc}"
        return blank

    matches = []
    for row in rows:
        chan = (row.get("channel") or "")
        title = (row.get("title") or "")
        if not _full_name_in(title, name):
            continue
        kind = None
        if any(c.lower() in chan.lower() for c in LOCAL_NEWS_CHANNELS):
            kind = "news"
        elif any(c.lower() in chan.lower() for c in COURT_CHANNELS):
            kind = "court"
        if kind:
            matches.append({"kind": kind, "channel": chan, "title": title,
                            "views": int(row.get("views") or 0)})

    if not matches:
        blank["why"] = f"no news or court coverage found for {name!r}"
        return blank

    news = max((m["views"] for m in matches if m["kind"] == "news"), default=0)
    court = max((m["views"] for m in matches if m["kind"] == "court"), default=0)
    bits = []
    if news:
        bits.append(f"local news best {news:,}")
    if court:
        bits.append(f"court channel best {court:,}")
    return {
        "covered": True, "news_views": news, "court_views": court,
        "matches": matches,
        "why": f"{len(matches)} match(es); " + ", ".join(bits),
    }


def score(
    case: dict[str, Any],
    *,
    check_competitors: bool = True,
) -> dict[str, Any]:
    """Combine the available signals into one 0-100 notoriety score.

    Weighting, stated plainly so it can be argued with:

      * severity 60 - the strongest signal the channel data supports, and the
        only one available for every case at zero cost.
      * competitor coverage 40 - the best evidence when it exists, but absent
        for most cases, so it cannot carry the majority.

    Competitor coverage is scored on a log-ish ladder rather than linearly:
    the difference between "covered at all" and "not covered" matters more
    than the difference between 40K and 60K views.
    """
    sev, sev_why = charge_severity(case)
    parts: dict[str, Any] = {"severity": sev, "severity_why": sev_why}

    cov: dict[str, Any] = {
        "covered": False, "news_views": 0, "court_views": 0,
        "matches": [], "why": "not checked",
    }
    if check_competitors:
        cov = existing_coverage(case.get("defendant_name"))
    parts["coverage"] = cov

    # Coverage is a capped BONUS, not 40% of the score.
    #
    # CORRECTION 2026-08-17, Nathan, and the channel data agrees with him. The
    # first version weighted coverage at 40% off the Soto/Preciado numbers.
    # Those videos were a live, press-covered capital murder trial posted the
    # day of - notoriety AND timeliness together, neither of which a routine
    # docket reproduces. Against Boyd-only rows the thesis fails outright:
    #
    #   9,800  Drug Dealer BEGS Judge Boyd To Not Send Him To Prison
    #   4,300  Thug In Disbelief After Judge Boyd Sentences Him To Prison
    #   3,000  Judge Boyd Sentences Famous San Antonio Rapper "IZZY93"
    #   2,300  Judge Boyd EXPOSES Credit Card Fraud Scheme
    #   1,400  Judge Boyd SHUTS DOWN Gang Member's Early Probation Request
    #
    # The one case with real local fame - a famous rapper, by name, in the
    # title - did 3.0K and LOST to an anonymous defendant begging, 3x. Within
    # Boyd-only content, fame is not the discriminator. What separates 9.8K
    # from 1.4K is liberty being decided on camera and a defendant reacting to
    # it, which is what the rubric's human_stakes and dramatic_turn already
    # score.
    #
    # So coverage is kept - it is still the right signal on the rare docket
    # case the city is genuinely following - but capped at 20 so it can nudge a
    # tie rather than overturn the rubric.
    news, court = cov["news_views"], cov["court_views"]
    if news >= 50_000:
        cov_score = 20
    elif news >= 10_000:
        cov_score = 15
    elif news > 0:
        cov_score = 10
    elif court >= 25_000:
        cov_score = 8
    elif court > 0:
        cov_score = 4
    else:
        cov_score = 0

    total = round(min(100.0, 0.85 * sev + cov_score), 1)
    parts["coverage_score"] = cov_score
    parts["total"] = total
    parts["summary"] = (
        f"notoriety {total:.0f}/100 - severity {sev} ({sev_why}); "
        f"coverage +{cov_score} ({cov['why']})"
    )
    return parts


def rank(cases: list[dict[str, Any]], *, check_competitors: bool = True,
         rubric_weight: float = 0.7) -> list[dict[str, Any]]:
    """Re-rank already-eligible cases by rubric score blended with notoriety.

    Blended rather than replaced, and weighted 0.7 TOWARD THE RUBRIC.

    That default was 0.5 and is now 0.7, because on Boyd-only content the
    rubric is closer to right than this module is. The channel's best docket
    clip is a defendant begging - no fame, no press - and its worst is a
    procedural probation request. That gap is human_stakes and dramatic_turn,
    both of which the rubric already scores directly. This module's job is to
    break ties and catch the occasional case the city is actually following,
    not to run the selection.

    Input cases must have ALREADY passed the safety gate. This function does no
    gating and must never be given a case that has not.
    """
    out = []
    for case in cases:
        n = score(case, check_competitors=check_competitors)
        rubric = float(case.get("total_score") or 0.0)
        blended = round(rubric_weight * rubric + (1 - rubric_weight) * n["total"], 1)
        enriched = dict(case)
        enriched["notoriety"] = n
        enriched["blended_score"] = blended
        out.append(enriched)

    out.sort(key=lambda c: c["blended_score"], reverse=True)
    for i, c in enumerate(out, 1):
        log.info("  rank %d: blended %.1f (rubric %.1f) - %s | %s",
                 i, c["blended_score"], float(c.get("total_score") or 0.0),
                 c.get("defendant_name") or "?", c["notoriety"]["summary"])
    return out
