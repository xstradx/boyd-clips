# Driver's independent re-verification

Gate R4 requires the driver to re-run at least one evidence command per leaf and
try to REFUTE a finding rather than accept it. Recorded as it happens.

## leaf-1.2 — selection and scoring

**Claim tested:** `find_called_hearings.py` silently discards every over-long
hearing through an off-by-one.

**Refutation attempt:** read `scripts/find_called_hearings.py:85-94` myself
rather than trusting the replay. The loop is:

```python
if t1 - t0 > MAX_S:                     # cap an over-long run
    cut = a
    while cut < len(times) and times[cut] - t0 <= MAX_S:
        cut += 1
    b, t1 = cut, times[min(cut, len(times) - 1)]
span = t1 - t0
if not (MIN_S <= span <= MAX_S):
    continue
```

**VERDICT: CONFIRMED, and it is unambiguous from the code alone.** The `while`
exits on the first index whose time EXCEEDS `MAX_S`, then assigns that very index
to `t1`. So the "capped" span is by construction `> MAX_S`, and the next line
rejects it. The cap can never produce an accepted span. The comment says "cap an
over-long run"; the code deletes it instead. Fix is one line (`cut -= 1` before
the assignment) — but everything downstream must then be regenerated.

**Claim tested:** `judged_nathan.json` is a model impersonating Nathan.

**Refutation attempt:** `grep -n "MODEL" scripts/judge_nathan.py`
-> `34:MODEL = "claude-opus-5"`, and line 1 of the docstring reads
*"Ask the model the actual question: would Nathan post this hearing?"*

**VERDICT: CONFIRMED.** The filename says Nathan; the file is Opus 5 predicting
Nathan. A name is not evidence about the thing it names.

**Claim tested — this one I actively tried to break:** "no script in the repo
writes `final_shortlist.json`". `grep -rln final_shortlist src/ scripts/` returns
THREE files, which looked like a refutation.

**Refutation attempt:** checked what each of the three actually does with it.

```
scripts/batch_vertical.py:68  rows = json.loads((ROOT/"state"/"final_shortlist.json").read_text(...))
scripts/cut_shortlist.py:34   SHORTLIST = ROOT / "state" / "final_shortlist.json"
scripts/studio.py:68          for name in ("final_shortlist.json", "called_hearings.json"):
```

**VERDICT: CLAIM SURVIVES.** All three READ it. None writes it. So the single
file that decides which 48 clips get cut has no producer, was thresholded by
hand, and is untracked (`git ls-files state/` returns 0 — `state/` is in
`.gitignore`, so none of the ground truth has any version history at all).
That is a stronger finding than the one I set out to refute.

## Read-only gate fired mid-flight — a real violation, caught by the gate

`node .unlazy/boyd-audit/snapshot.mjs --diff` -> exit 1:

```
ADDED C:\Users\natha\OneDrive\Desktop\Boyd Clips\READY-TO-POST\NOW.png
1 file(s) outside the audit workspace changed
```

860x1228 RGB, 1.27 MB, written 05:02 — a contact sheet an audit agent produced
despite the brief forbidding writes. Benign in content, but it landed in
**READY-TO-POST**, the folder Nathan treats as finished deliverables. Left in
place deliberately: it is the evidence that the gate works, and deleting an
artifact mid-audit is worse than reporting it. Flag for cleanup at the end.

This is the gate earning its keep on the first run. Without it the file would
have sat in the deliverables folder indefinitely, indistinguishable from output.

## Credentials — checked myself, not read

The `youtube-channel` skill claims there are no YouTube API credentials on this
machine. Verified rather than accepted:

```
ls "C:/Users/natha/.claude/secrets/"          -> NO SECRETS DIR
find C:/Users/natha/Projects -iname "*client_secret*"  -> (nothing)
ls config/                                     -> .env.example, cases.json, pipeline.yaml
```

**CONFIRMED, and it explains something.** `.gitignore` reserves
`config/youtube_token.json` and `config/youtube_client_secret.json` — so
`src/boydclips/publish.py` was written against credentials that were never
created. That is why publishing is manual through a browser window, and why no
outcome has ever been pulled. Not a code defect: a one-time OAuth setup that
only Nathan can do, because it needs his Google account and his consent click.

## leaf-1.1 — ingest

**Claim:** no scheduled task exists; the corpus is 16 days stale.
`Get-ScheduledTask | Where TaskName -match 'boyd'` -> **count 0**.
`select max(docket_date) from dockets` -> **2026-08-13** (today is 2026-08-29).
`config/pipeline.yaml:21  max_age_days: 4`.
**CONFIRMED.** The daily run was never registered, and the 4-day window means the
missing fortnight cannot be recovered by the normal path even after it is.

**Claim:** 57% of transcripts say "bear county" for Bexar.
**CONFIRMED at 137/250 (55%)** — but only on my THIRD attempt, and the first two
failures are worth more than the finding:

1. `grep -rl "bear county" work/*/*.transcript.json` -> 0 hits. I concluded the
   claim was false. **My glob was fine; my assumption was not.**
2. Joined the raw JSON text and regexed words -> 0 hits for "bear county" AND
   0 for "bexar county". A Bexar County court transcript containing zero
   mentions of Bexar County is impossible — that implausible control is what
   told me the checker was broken, not the claim.
3. Actually opened one file: `{"video_id":..,"words":[{"t":143.599,"w":"Lock,"}]}`.
   Word-level storage. `json.dumps` interleaves keys between every word, so
   "bexar county" is never adjacent in the serialised text. Joining the `w`
   fields properly: **bear county 137, bexar county 120 of 250.**

**The lesson is the project's own:** a checker that has not been run against a
known answer proves nothing. Twice I would have reported "claim refuted" and
been wrong. This is the same defect class as the caption-side checker that
scored 0/5 wrong on a correct render by measuring Judge Boyd's collar.

## leaf-3.3 — provenance

**Claim:** two shipped thumbnails are byte-identical to variants Nathan rejected.
`md5sum` run myself:

```
cfc75fee40231c137fdedbd12feb46ef  CARTHIEF_thumbnail.jpg
cfc75fee40231c137fdedbd12feb46ef  AB-THUMBNAILS/CARTHIEF_thumb_A.jpg   <- identical
6468b079c0f9449b7feb1bc7fc47c4e5  AB-THUMBNAILS/CARTHIEF_thumb_C.jpg
32dd0a2aeef4468dfcf3ad6356be38d1  OFFERUP_thumbnail.jpg
32dd0a2aeef4468dfcf3ad6356be38d1  AB-THUMBNAILS/OFFERUP_thumb_A.jpg    <- identical
a41ddeec90dd547ef8759a7fbf748c99  AB-THUMBNAILS/OFFERUP_thumb_C.jpg
```

**CONFIRMED.** STATE.md records Nathan picking **C** for CARTHIEF and **C** for
OFFERUP, rejecting A on both for eyes-down. The shipped file is A in both cases.
Cannot be settled from disk which way the mistake runs — needs his eye.

## leaf-5.2 — the human-input surface

**Claim:** a detector implementing his eyes-level rule already exists, unwired.
`scripts/layout_L3_tight.py:169` — `"""pitch proxy, de-rolled. HIGHER = looking DOWN."""`
`:1497` — `chk("Judge Boyd eyes LEVEL not down (nv <= 0.50, |roll| <= 4)")`
`models/yunet.onnx` present, 229,738 bytes.
`grep -ln "layout_L3_tight\|yunet" run_case.py make_thumbnail_auto.py thumb_Q3_detail.py`
-> **no matches**.
**CONFIRMED.** STATE.md says this could not be automated and three metrics were
tried and failed. A fourth was built, encodes his rule as a hard assertion, and
the shipping path does not call it.
