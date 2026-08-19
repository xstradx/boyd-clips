"""Build a full research dossier for a case: everything reachable, in one file.

Nathan, 2026-08-12: "a summery of anything and EVERYTHING you can find relavant
to the case" — and the criminal history is MATERIAL FOR THE VIDEO, not a way of
choosing which cases to make.

Sources, in the order they are joined:
  1. our own analysis      state/pipeline.db  (score, hook quote, summary, clips)
  2. the court's docket    hearings API       (canonical name, real cause number)
  3. the Register of Actions                  (charges, disposition, bond, arrest
                                               and release dates, case flags)
  4. the jail record       jailing detail     (DOB, description, aliases, per-charge
                                               disposition and warrant numbers)
  5. the full arrest history  SID query       (every booking, exact)

The bridge between 3 and 5 is the court's own InmateReleaseDate matching a jail
booking to the day — see priors.resolve_from_case.

NOT AVAILABLE, measured rather than assumed: mugshots. The Tyler portal carries
HasMugshotFront/Left/Right on every booking and all three are False on all 43
bookings tested, including a person currently in custody. Bexar has the feature
switched off. The magistrate site carries no photos either. Use a frame from the
courtroom footage instead — it is the actual person, it shows a real reaction,
and its rights status is the same as the rest of the video.

Usage:  python scripts/case_dossier.py [n_cases]
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from boydclips import priors, records  # noqa: E402

DB = Path("state/pipeline.db")
OUT = Path("out/dossiers")


def _f(v, dash="—"):
    return dash if v in (None, "", 0) else v


def roster_for(d: date) -> list[dict]:
    try:
        return records.hearings(d, d)
    except Exception:
        return []


def pick_row(roster: list[dict], defendant: str) -> dict | None:
    """Match our analyser's spoken-name guess to the clerk's canonical row."""
    nm = priors.normalise_name(defendant or "")
    if not nm:
        return None
    first, last = nm
    for r in roster:
        dn = (r.get("defendant") or "").lower()
        if last in dn and first in dn:
            return r
    for r in roster:                       # surname only, last resort
        if last in (r.get("defendant") or "").lower():
            return r
    return None


def dossier(case: dict) -> str:
    L: list[str] = []
    add = L.append
    name = case["defendant"]
    add(f"# {name}")
    add("")
    add(f"*Score {case['total_score']} · {case['proceeding_type']} · "
        f"video `{case['video_id']}` @ {int(case['start_s'])}s–{int(case['end_s'])}s*")
    add("")

    p = case["payload"]
    if p.get("hook_quote"):
        add(f"> **“{p['hook_quote']}”**")
        add("")
    if p.get("summary"):
        add("## What happens")
        add("")
        add(p["summary"])
        add("")

    row = case.get("court_row")
    add("## Court record")
    add("")
    if not row:
        add("_Not matched to a docket row — the analyser's name did not resolve "
            "against the clerk's roster for this date._")
        add("")
    else:
        add(f"- **Defendant (as the clerk has it):** {row['defendant']}")
        add(f"- **Cause number:** `{row['case_number']}`  "
            f"(analyser read it as `{_f(case['cause_number'])}`)")
        add(f"- **Hearing:** {_f(row.get('hearing_type'))} on {_f(row.get('hearing_date'))}"
            f" at {_f(row.get('hearing_time'))}")
        add(f"- **Court:** {_f(row.get('courtroom'))} — {_f(row.get('judge'))}")
        add("")

    det = case.get("roa")
    if det:
        ci = det.get("CaseInformation") or {}
        add(f"- **Case type:** {_f((ci.get('CaseType') or {}).get('Description'))}"
            f" / {_f((ci.get('CaseSubType') or {}).get('Description'))}")
        flags = [ (f.get('CaseFlagCode') or {}).get('Description')
                  for f in (ci.get("CaseFlags") or []) ]
        flags = [f for f in flags if f]
        if flags:
            add(f"- **Case flags:** {', '.join(flags)}")
        for st in (ci.get("CaseStatuses") or [])[:3]:
            d = (st.get("CaseStatusCodeId") or {}).get("Description") or st.get("Description")
            if d:
                add(f"- **Status:** {d}")
        disp = (det.get("DispositionInformation") or {}).get("Dispositions") or []
        for d in disp[:6]:
            desc = (d.get("DispositionTypeId") or {}).get("Description")
            if desc:
                add(f"- **Disposition:** {desc} ({_f(str(d.get('DispositionDate'))[:10])})")
        add("")
        wins = records.case_arrest_windows(det)
        if wins:
            add("### Bond")
            add("")
            for w in wins:
                amt = w.get("amount")
                money = f"${amt:,.0f}" if isinstance(amt, (int, float)) and amt else "—"
                add(f"- {money} {_f(w.get('type'))}, bond #{_f(w.get('bond_number'))} — "
                    f"arrested {_f(w.get('arrest'))}, released {_f(w.get('release'))}")
            add("")

    m = case.get("match")
    add("## Identity")
    add("")
    if not (m and m.person):
        add(f"_Not resolved to a person — {m.reason if m else 'no attempt'}._ "
            "**Do not state priors on screen for this case.**")
        add("")
    else:
        per = m.person
        add(f"- **SID / SO number:** `{per.so}`  ({m.confidence}: {m.reason})")
        jd = case.get("jail_detail") or {}
        add(f"- **Name on file:** {_f(jd.get('DefendantCurrentName') or per.name)}")
        add(f"- **DOB:** {_f(jd.get('DefendantDOBString'))}")
        add(f"- **Description:** {_f(jd.get('DefendantDescription'))}"
            f" · hair {_f(jd.get('DefendantHair'))} · eyes {_f(jd.get('DefendantEyes'))}")
        al = [a.get("aliasName") for a in (jd.get("Aliases") or []) if a.get("aliasName")]
        if al:
            add(f"- **Aliases:** {', '.join(al)}")
        add(f"- **Mugshot published:** no (Bexar has the field disabled — use a video frame)")
        add("")

        pr = case.get("priors") or {}
        add("## Criminal history")
        add("")
        add(f"**{pr.get('prior_bookings', 0)} prior bookings** in Bexar County, "
            f"{_f(pr.get('first'))} to {_f(pr.get('last'))}.")
        add("")
        if pr.get("bookings"):
            add("| booked | charges | agency |")
            add("|---|---|---|")
            for b in pr["bookings"]:
                ch = ", ".join(c.strip() for c in (b.get("charges") or []) if c)[:78]
                add(f"| {_f(b.get('date'))} | {ch or '—'} | {_f(b.get('agency'))} |")
            add("")

    if case.get("jail_detail", {}).get("Charges"):
        add("## Charges on this arrest")
        add("")
        for c in case["jail_detail"]["Charges"]:
            add(f"- **{_f(c.get('ChargeDescription'))}** — {_f(c.get('Disposition'))}"
                f" · offence {_f(c.get('OffenseDateString'))}"
                f" · warrant {_f(c.get('WarrantNumber'))}"
                f" · {_f(c.get('ArrestingAgency'))}")
        add("")

    add("---")
    add("")
    add("*Every fact above is from a public record. Identity is asserted only where "
        "the court's own release date matched a jail booking to the day, or the name "
        "is unique in the county.*")
    return "\n".join(L)


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute("""
        select c.*, d.docket_date from cases c join dockets d on d.video_id = c.video_id
        where c.safety_pass=1 and c.shortable=1 and c.defendant is not null and c.defendant!=''
        order by c.total_score desc limit ?""", (n * 3,)).fetchall()

    OUT.mkdir(parents=True, exist_ok=True)
    done = 0
    roster_cache: dict[str, list[dict]] = {}

    for r in rows:
        if done >= n:
            break
        case = dict(r)
        try:
            case["payload"] = json.loads(r["payload"])
        except Exception:
            case["payload"] = {}

        dd = r["docket_date"]
        if dd not in roster_cache:
            roster_cache[dd] = roster_for(date.fromisoformat(dd))
        row = pick_row(roster_cache[dd], r["defendant"])
        case["court_row"] = row

        if row:
            try:
                case["roa"] = records.case_detail(row["encrypted_case_id"], row.get("roa_url"))
            except Exception:
                case["roa"] = None
            m = priors.resolve_from_case(row["defendant"], row["encrypted_case_id"],
                                         row.get("roa_url"))
        else:
            m = priors.resolve_from_court(r["defendant"])
        case["match"] = m

        if m.person:
            case["priors"] = priors.summarise(m.person.so, before=date.fromisoformat(dd))
            newest = sorted(m.person.bookings,
                            key=lambda b: str(b.get("bookingDate")), reverse=True)
            if newest:
                try:
                    case["jail_detail"] = records.jailing_detail(newest[0].get("jailID"))
                except Exception:
                    case["jail_detail"] = {}

        slug = "".join(ch if ch.isalnum() else "_" for ch in r["defendant"])[:40]
        path = OUT / f"{r['total_score']:.0f}_{slug}.md"
        path.write_text(dossier(case), encoding="utf-8")
        sid = case["match"].person.so if case["match"].person else "unresolved"
        npr = (case.get("priors") or {}).get("prior_bookings", 0)
        print(f"  {r['defendant'][:26]:28s} score {r['total_score']:<6} SID {str(sid):>11}  "
              f"{npr:2d} priors  -> {path.name}")
        done += 1

    print(f"\n-> {OUT.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
