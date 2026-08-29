# Bexar County public records — reverse-engineered API map

Established by live probing 2026-08-10. Every status below was observed, not
assumed. Re-probe before trusting any of it after a Tyler version bump
(portal currently reports `Version: 2017.1.65.0`).

**No login is required for any of this.** The portal states it outright:
"Registration is not required for public data. Registration is reserved for
authorized law enforcement and justice partners." An earlier assumption that
Smart Search needed an account was wrong — it needs a reCAPTCHA, which is a
different problem with a different answer.

---

## 1. Jail Search — WORKS HEADLESS, no auth, no CAPTCHA

Full custody history back to **1989**.

```
POST https://portal-txbexar.tylertech.cloud/app/JailSearchService/search
Content-Type: application/json

{"Id":"0","size":10,"from":0,"searchTimeMilliseconds":0,
 "queryString":"De Hoyos","parameters":{},"searchResult":{},
 "sorts":[],"facets":[]}
```

Returns HTTP **201** with `searchResult.totalHits` and `searchResult.hits[]`:

| field | note |
|---|---|
| `defendantName`, `defendantDOB` | |
| `defendantSONum` | **the join key** — same SID as magistrate + jail CSVs |
| `bookingNumber`, `bookingDate`, `bookingTime` | |
| `releaseDate`, `releaseTime` | **null release = still in custody** |
| `charges[].chargeDescription` | |
| `arrests[].arrestingAgency` | |
| `facility`, `nodeName`, `chargeCount` | |
| `jailID` | feeds the detail call below |

Paginate with `from`/`size`. `sorts[]` supports `bookingNumber.sort`.

## 2. Jailing detail — WORKS HEADLESS

```
GET https://portal-txbexar.tylertech.cloud/app/ViewJailingService//Jailings({jailID})
```
(the double slash is genuine — that is what the app sends)

Adds: race, gender, height, weight, hair, eyes, aliases, address, DL state,
and per-charge `WarrantNumber`, `Disposition`, `BondType`, `FineAmount`,
`CostsAmount`, `PaidAmount`, `OffenseDate`.

**Mugshots are not published.** `HasMugshotFront` / `HasMugshotLeft` /
`HasMugshotRight` exist in the schema and were `False` on every record checked
(6 records spanning 1989–2026). Tyler's software supports booking photos;
Bexar has them switched off. The magistrate detail page likewise serves zero
non-chrome images. Do not substitute a third-party mugshot aggregator: those
are commercial scrapers that assert copyright and go stale.

## 3. Hearings docket — WORKS, session-based, no CAPTCHA

**This is the advance docket** — who is scheduled in front of Boyd before it
happens. 165 hearings returned for 2026-08-10 → 2026-08-24.

Two steps, same cookie jar:

1. POST the search form (`/Portal/Home/Dashboard/26`) — sets criteria in
   session. Location `District Clerk`, Hearing Type `District Clerk Criminal`,
   Search Type `Judicial Officer`, officer `Boyd, Stephanie R`, date range.
2. `POST /Portal/Hearing/HearingResults/Read` with body
   `sort=&group=&filter=&portletId=27`

Each row carries `DefendantName`, `CaseNumber`, `CaseTypeId` (Felony/Misd),
`HearingDate`, `HearingTime`, `HearingTypeId` (e.g. Probation Hearing),
`CourtRoom`, `JudgeParsed`, and `CaseLoadUrl` / `EncryptedCaseId`.

## 4. Register of Actions — case summary, needs a carried session

```
GET /app/RegisterOfActionsService/CaseSummariesSlim?key={EncryptedCaseId}&mode=
```

Templates the page loads show the payload covers Case Info, Causes, **Charges**,
Related Cases, Lower Court Cases, **Dispositions**, **Warrants**, **Bonds** —
i.e. the conviction/felony data the jail search cannot give.

**Solved** (was "Unsolved" here until 2026-08-23). Carry the hearing-search
cookie jar in and GET the case's own ROA page first to scope the session, then
call with `mode=portalembed`. This is what `records.case_detail()` does and it
works. But note the payload does **not** include charges or causes — see §9.

## 5. Jail Activity CSVs — WORKS, but expires in 7 days

```
https://edocs.bexar.org/jailactivity/JABookings_YYYYMMDD.csv
https://edocs.bexar.org/jailactivity/JAReleases_YYYYMMDD.csv
```

Bookings: `SONumber, InmateFullName, Address1, CaseNumber, Court, AttorneyName,
ConfineDate, OffenseDate, ChargeOffenseDescription, BondType, BondAmount`

Releases: adds `ReleaseDate, ReleaseTime, ReleaseType, BondsmanName`

Adds **defence attorney, court, and bondsman**, which nothing else exposes.

> **The county deletes these after 7 days.** Archive daily or the history is
> gone permanently. This is the only source here that is time-critical.

> **`Address1` is a home address.** Strip it at ingest. It must never reach a
> clip, title, description or manifest — that is a hard R3 violation and a
> YouTube doxxing strike.

## 6. Central Magistrate — last 24 hours only

```
GET https://centralmagistrate.bexar.org/                    (list)
GET https://centralmagistrate.bexar.org/Details/{bookingNumber}
```

Magistration/arrest/release timestamps, per-charge case number, offense class,
bond amount, disposition, comments. No auth. Useless for Boyd's dockets on its
own (hearings happen months after booking) but precise on bond at intake.

## 7. Smart Search — reCAPTCHA'd, and NOT needed

`/Portal/Home/Dashboard/29`. Anonymous access is permitted but gated by
reCAPTCHA, so it cannot be driven unattended. Do not build a solver.

**It is not the only route to a case record — see §8.** The earlier claim that
it was "the only source of general case-record search" is wrong, measured
2026-08-23.

## 8. Case lookup by cause number — WORKS HEADLESS, no CAPTCHA

The hearing-search form (§3) accepts `SearchByType=CaseNumber`, verified from
its own `<option value="CaseNumber">Case Number</option>` on Dashboard/26. That
turns the ungated hearings portlet into a cause-number lookup:

```
SearchCriteria.SelectedCourt        = District Clerk
SearchCriteria.SelectedHearingType  = District Clerk Criminal
SearchCriteria.SearchByType         = CaseNumber
SearchCriteria.SearchValue          = 2024CR011920
SearchCriteria.DateFrom/DateTo      = wide range, e.g. 01/01/2024–12/31/2026
```
then `POST /Portal/Hearing/HearingResults/Read` as in §3. Returns the rows for
that cause with its `EncryptedCaseId` and `CaseLoadUrl`.

Gotchas, all observed:
- The exact zero-padded form matters. `2024CR011920` → Total=2;
  `2024CR11920` and `DC2024CR11920` → Total=0.
- `SelectedHearingType=All Hearings` with an empty `SelectedCourt` makes the
  Read endpoint return **HTTP 500**. Keep the District Clerk pair above.
- Searching by judicial officer + date is **not exhaustive**: Boyd's docket for
  07/14/2025 returned Total=30 and did not include a case that the ROA proves
  was disposed in her court that day. Anchor on the cause number, not the
  docket.

## 9. Charges are NOT in CaseSummariesSlim — separate OData endpoints

`CaseSummariesSlim` returns `CauseInformation: null` and no charge list. The
real endpoints, read out of the ROA bundle
(`/app/RegisterOfActions/bundles/RegisterOfActionsJs`, which builds them as
`serviceUri + "Charges('" + caseId + "')" + buildQueryString(...)`):

```
GET /app/RegisterOfActionsService/Charges('{longCaseId}')?mode=portalembed
GET /app/RegisterOfActionsService/PartyNames('{longCaseId}')?mode=portalembed
GET /app/RegisterOfActionsService/CombinedEvents('{longCaseId}')?mode=portalembed&$top=300
GET /app/RegisterOfActionsService/CaseEvents('{longCaseId}')?mode=portalembed&$top=300
GET /app/RegisterOfActionsService/DispositionEvents('{longCaseId}')?mode=portalembed&$top=300
```

**The key differs from the one `CaseSummariesSlim` takes.** These take the
*long* `id` from `CaseLoadUrl` (~300 hex chars), not the 32-char
`EncryptedCaseId`. Passing the short key returns nothing useful.

`Charges(...)` gives `ChargeOffenseDescription`, `Degree` / `DegreeDescription`,
`Statute`, `OffenseDate`, `FiledDate`, arrests and `ArrestControlNumber`.
`CombinedEvents(...)` is the full docket sheet — every filing and setting, past
and future — and is what actually answers "what is the status now".

Same session discipline as §4: GET Dashboard/26, then GET the case's own
`/app/RegisterOfActions/?id=...` page, carrying one cookie jar.

**Pace these.** Firing ~18 endpoint-name guesses back to back made the service
return 500s with zero-byte bodies until it was left alone. `records._request`
throttling is not optional here.

---

## Joining it together

`defendantSONum` links jail search ↔ jailing detail ↔ magistrate ↔ jail CSVs.
`CaseNumber` links hearings ↔ CSVs ↔ magistrate.
Name matching alone is unsafe — the case DB already holds both
`Charlie McKinnus` and `Charlie Edward McKinnus` for one person.
