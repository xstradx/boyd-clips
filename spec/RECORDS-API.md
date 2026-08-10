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

## 4. Register of Actions — full docket sheet, SESSION-BOUND

```
GET /app/RegisterOfActionsService/CaseSummariesSlim?key={EncryptedCaseId}&mode=
```

Templates the page loads show the payload covers Case Info, Causes, **Charges**,
Related Cases, Lower Court Cases, **Dispositions**, **Warrants**, **Bonds** —
i.e. the conviction/felony data the jail search cannot give.

**Unsolved:** replaying the key in a fresh session returns
`No case found for id`, and the app's own call 404s with `mode=undefined`. The
`EncryptedCaseId` appears bound to the session that produced it. Fix is almost
certainly to carry the hearing-search cookie jar straight into this call rather
than starting fresh. Not yet verified.

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

## 7. Smart Search — reCAPTCHA'd

`/Portal/Home/Dashboard/29`. The only source of general case-record search.
Anonymous access is permitted but gated by reCAPTCHA, so it cannot be driven
unattended. Do not build a solver. If case-record search is needed, drive it
with a human solving the challenge, or reach the same data through Hearings →
Register of Actions, which is not gated.

---

## Joining it together

`defendantSONum` links jail search ↔ jailing detail ↔ magistrate ↔ jail CSVs.
`CaseNumber` links hearings ↔ CSVs ↔ magistrate.
Name matching alone is unsafe — the case DB already holds both
`Charlie McKinnus` and `Charlie Edward McKinnus` for one person.
