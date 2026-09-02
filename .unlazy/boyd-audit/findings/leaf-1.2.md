# leaf-1.2 — clip selection and scoring

## F1: The "cap an over-long run" block in find_called_hearings.py is dead code — it drops 100% of over-long hearings instead of capping them, discarding 1,135 content-eligible candidates
SEVERITY: blocker
EVIDENCE: `scripts/find_called_hearings.py:89-99` reads:
```
            if t1 - t0 > MAX_S:                     # cap an over-long run
                cut = a
                while cut < len(times) and times[cut] - t0 <= MAX_S:
                    cut += 1
                b, t1 = cut, times[min(cut, len(times) - 1)]
            span = t1 - t0
            if not (MIN_S <= span <= MAX_S):
                continue
```
The `while` exits on the FIRST word past `MAX_S`, so the "capped" span is always
just over 1200 s and the very next range check rejects it. Replicating that exact
block over the first 400 transcripts (print-only):
```
$ python -c "<lines 89-97 replayed over work/*/*.transcript.json>"
raw run 2073s -> after cap block span=1204.0s  (MAX_S=1200) -> REJECTED
raw run 2692s -> after cap block span=1200.1s  (MAX_S=1200) -> REJECTED
raw run 2059s -> after cap block span=1200.2s  (MAX_S=1200) -> REJECTED

over-long runs in first 400 transcripts: 653
  survive the cap  : 0
  silently dropped : 653
```
Zero of 653 survive. Scaled over the whole corpus, replaying the same segmentation
on all 1,702 transcripts:
```
total call-to-call runs: 6997
run span sec: p10 277 p25 559 med 980 p75 1801 p90 3198 p99 9846 max 25408
runs >1200s (MAX_S): 2863 = 40.9%
  of those, content-eligible (MTR, not trial, 3+ deferential): 1135
runs in [360,1200]: 3176
```
The 1,135 figure applies the three content gates I replicated exactly (`MTR`
present, `TRIAL` absent, 3+ `DEFER` sentences); I did not apply the
`their_words < 80` filter at `find_called_hearings.py:105`, so treat 1,135 as an
upper bound on what the bug discards. `state/called_hearings.json` holds 244 rows
and is not itself truncated (244 < the `out[:400]` cap), so the discarded pool is
up to 4.6x the entire surviving candidate list. Note also the median
call-to-call run is 980 s (16.3 min): the "court is calling" boundary is missed
often enough that half of all runs are longer than a single hearing, which is the
same defect STATE.md:217-219 records ("the court never says 'the court is calling'
there, which is why `find_called_hearings.py` merged them").
WHY-IT-MATTERS: The pool the whole channel picks from is missing up to 1,135
content-eligible hearings against the 244 it kept, and the missing ones are biased
by construction toward exactly the long,
multi-exchange hearings Nathan wants for 8+ min long-form RPM. Every "best clip we
have" claim is really "best of the 18% that survived an off-by-one".
PROPOSAL: Change the cap loop to step back one word (`cut -= 1` after the loop, or
`times[cut] - t0 < MAX_S` with a final decrement) so the capped span lands inside
`[MIN_S, MAX_S]`; better, emit successive `MAX_S` windows across a long run instead
of one, so the tail of a 40-minute run is also a candidate. Re-run and diff the new
`called_hearings.json` against the current 244 before trusting it.
COST: Two-line fix, then a full re-scan of 1,702 transcripts (minutes, CPU only).
Risk: `ranked_hearings.json`, `judged_*.json` and `final_shortlist.json` are all
keyed off the current 244 and become a stale subset — they must be regenerated,
which means re-spending LLM calls on the judging stage.

## F2: state/judged_nathan.json contains no judgement by Nathan — it is Opus 5 impersonating him, and it is the sole gate on the shortlist
SEVERITY: blocker
EVIDENCE: `scripts/judge_nathan.py:1` and `:56` — the docstring is *"Ask the model
the actual question: would Nathan post this hearing?"*, `MODEL = "claude-opus-5"`,
`OUT = ROOT / "state" / "judged_nathan.json"`, and the system prompt begins *"You
are picking hearings for a YouTube channel..."*. Every row's `post` field is a
model's guess at Nathan's taste, not his rating. The join proves the two never
touch:
```
$ python -c "lab=json.load(...labels.json); na={d['key'] ...judged_nathan.json}"
labels keys overlapping judged_nathan: 0
labels keys overlapping judged_opus:   0
```
And the shortlist is that model output with a threshold applied:
```
judged_nathan post>=4: 48   final_shortlist: 48   identical: True
post dist all: {1: 39, 2: 66, 3: 44, 4: 33, 5: 15}
```
`grep -rn "final_shortlist" scripts/ src/` shows three readers
(`batch_vertical.py:68`, `cut_shortlist.py:34`, `studio.py:68`) and **no writer** —
the `post>=4` filter that produced the 48 rows exists nowhere in the repo.
WHY-IT-MATTERS: The audit question "do the machine's judgements and Nathan's
agree?" cannot be answered, because there is no file of Nathan's judgements at the
hearing unit. The 48 clips queued for cutting were chosen entirely by a model
grading itself against a paraphrase of Nathan, with a hand-run threshold that is
not in version control. Nobody can reproduce the shortlist or tell whether the
model's taste tracks his.
PROPOSAL: Rename `judged_nathan.json` to `judged_as_nathan.json` so the file stops
claiming to be ground truth. Add a `scripts/build_final_shortlist.py` that applies
the documented threshold. Then have Nathan rate 40 of the 197 judged hearings on
`post` 1-5 into a real `state/nathan_hearings.json` and report the correlation —
that number is the go/no-go for running selection unattended.
COST: Rename plus one 30-line script is trivial; the label pass costs Nathan roughly
an hour of watching. Renaming breaks `judge_nathan.py`'s resume path until its
`OUT` constant is updated.

## F3: Two verdict sets over the identical 180 hearings disagree at kappa 0.649 and differ 2.7x on the consequential outcome label — the outcome classifier is not stable across runs
SEVERITY: high
EVIDENCE: `state/judged_hearings.json` and `state/judged_opus.json` hold the same
180 keys under the same schema (`date, drama, key, outcome, span_s, t, video_id,
why`), both written 2026-08-21 three minutes apart. `scripts/judge_hearings.py:44`
sets `MODEL = "claude-haiku-4-5-20251001"` and exposes `--model` / `--out`, so the
obvious reading is one Haiku run and one Opus run of that script over identical
inputs — **that model attribution is inferred from the filename and the flags, not
measured**; nothing in STATE.md or `judge.log` records the run (`grep -n -i
"judged_opus" STATE.md` returns nothing). Either way the disagreement below is
between two verdict sets over byte-identical inputs, and if the models were NOT
different the result is worse, not better. Measured:
```
common opus/haiku keys 180
outcome exact agree 135/180 = 75.0%
outcome Cohen kappa = 0.649 (po=0.750 pe=0.288)
drama identical 70.6%  within1 98.3%  mean|diff| 0.31
hard-consequence (jail|revoked): opus 7, haiku 19, BOTH 6
drama>=4: opus 10, haiku 4, both 3
opus outcome  Counter({'reset':79,'punished':35,'chance':31,'unclear':28,'jail':4,'revoked':3})
haiku outcome Counter({'reset':87,'punished':38,'unclear':19,'chance':17,'revoked':11,'jail':8})
```
On the only two categories that decide whether a clip is worth cutting, the models
barely overlap: 6 shared out of 20 distinct hard-consequence calls, 3 shared out of
11 distinct `drama>=4` calls.
WHY-IT-MATTERS: `judge_hearings.py`'s docstring justifies Haiku with "This is
classification, not judgement." The measurement says otherwise — the classifier
that feeds the ranking picks a nearly disjoint top set depending on which model
ran. A model deprecation or a `--model` typo silently reshuffles the pick list, and
nobody would see it because nothing compares runs.
PROPOSAL: Pin the model id in `config/` rather than as a script constant, record the
model id inside every verdict row, and keep the Opus-vs-Haiku disagreement set (the
45 outcome disagreements) as a standing regression fixture — a future run that moves
that number is a signal, not noise.
COST: Small code change. Risk: adding a `model` field invalidates the resume `done`
dict shape unless the loader tolerates missing keys.

## F4: Selection is not reproducible — no temperature, no seed, no cache, and resume-dependent batching changes the prompt each run
SEVERITY: high
EVIDENCE: `src/boydclips/llm.py` — `ClaudeCliBackend._invoke` builds the argv
`["claude","-p","--output-format","json","--model",self.model,
"--system-prompt-file",...,"--exclude-dynamic-system-prompt-sections",
"--disallowed-tools",*DISALLOWED_TOOLS]`. There is no `temperature`, `top_p` or
seed anywhere; `SdkBackend.complete` likewise passes only `model`, `max_tokens`,
`system`, `messages`, `output_config`. A grep for
`random|shuffle|seed|temperature|top_p` over `moments.py analyze.py arcs.py llm.py
hearingtype.py find_*.py rank_hearings.py judge_*.py index_moments.py
collect_bangers.py cut_shortlist.py` returns only two `time.time()` calls used for
progress printing (`judge_moments.py:80`, `cut_shortlist.py:87`) — nothing sets
sampling determinism at all.
There is also no response cache: `complete()` shells out every call, and the only
persistence is the output JSON. Worse, batch composition is resume-dependent —
`judge_nathan.py:150` skips keys already in `done` and then batches the remainder 4
at a time (`judge_hearings.py`, 20 at a time), so a run resumed after a failure
groups different hearings into the same prompt than a clean run would, and each
hearing is judged in a different context. `judge_hearings.py:167` catches a failed
batch with `print(f"  batch {i} failed: ...")` and continues, so a partial run
leaves a silently smaller `judged_*.json` with no marker.
WHY-IT-MATTERS: Re-running the scorer today does not reproduce today's shortlist,
and the difference cannot be distinguished from a real improvement. Every claim of
the form "the refit made it better" is unfalsifiable while this holds. It also means
one failed batch quietly removes hearings from consideration, since a resume treats
those keys as un-judged only if the run is repeated.
PROPOSAL: Cache on `sha256(model + system + user + schema)` to `state/llm_cache/`,
so a re-run is a replay unless the prompt changed. Make batch composition
deterministic (batch over the full sorted `rows`, then drop finished keys from the
results rather than from the input). Write a `runs.jsonl` line per invocation with
model id, input hash, and failed-batch count.
COST: ~60 lines in `llm.py` plus a call-site change per judge script. Risk: a stale
cache hiding a genuine prompt change — mitigated by hashing the prompt text itself.

## F5: The only human ground truth is 60 moment labels; the scorer fitted to them scores AUC 0.726 in-sample and 4/8 precision at the top, and 20% of the labels no longer point at anything
SEVERITY: high
EVIDENCE: `state/labels.json` has 60 unique keys (`raw key count 60 unique 60`, no
duplicates), split `Counter({'no': 37, 'yes': 18, 'maybe': 5})`. Commit
`7de4742 "Refit the scorer to Nathan's labels; drop the excuse anchor"` refitted
`scripts/find_wentthere.py:168-195` on 28 of these. Joining the labels to the
current `state/wentthere.json`:
```
labels matched to a wentthere row: 48 of 60
n yes 13 no 30 maybe 5
mean yes 64.9  mean no 54.4  diff 10.4
AUC yes-vs-no = 0.726  (390 comparisons)
top10   labelled=8   yes=4 no=4 maybe=0
top20   labelled=16  yes=6 no=8 maybe=2
top50   labelled=28  yes=12 no=13 maybe=3
```
AUC 0.726 is measured *on the data the weights were fitted to*, so it is an upper
bound, and precision at the top of the ranking is a coin flip (4 yes / 4 no in the
top 10). The commit message itself promised the holdout test — *"the old list drew
14 posts from 30. If the refit is genuine the new one should beat 47% clearly"* —
and there is no record it was ever run. It cannot be reconstructed either:
`.gitignore` line `state/` means `labels.json`, `judged_*.json` and `wentthere.json`
have zero version history (`git log -- state/labels.json` returns nothing,
`git ls-files state/` is empty), so the 28 fit labels cannot be separated from the
32 later ones. Separately, 12 of 60 labels (20%) join to nothing, because
`find_wentthere.py:228` writes only `rows[:500]` and the file was regenerated after
labelling — labelled candidates that fell out of the top 500 are orphaned.
WHY-IT-MATTERS: This is the only place the pipeline touches Nathan's actual taste,
and it is 60 labels on a unit (`wentthere` moments) that shares zero keys with the
unit the shortlist is built from (hearings, F2). One in five of his ratings has
already been lost to a re-run, and none of it is backed up. Publishing on the
strength of "the scorer is fitted to Nathan" is publishing on 28 in-sample points.
PROPOSAL: Commit the ground truth — either drop `state/*labels*.json` and
`judged_*.json` from `.gitignore` or mirror them to a tracked `truth/` directory on
write. Key labels by `video_id + rounded t` against the transcript, not against a
rank-truncated candidate file, so a re-scan cannot orphan them. Then run the holdout
the commit promised and record the number.
COST: Un-ignoring two globs is minutes. Re-keying labels is an afternoon and risks
mis-joining the 12 already-orphaned entries — those may need re-rating.

## F6: "The defendant talks a lot" — Nathan's first criterion — is measured with a rule the project's own prompt declares invalid, and 30 of 244 candidates are majority attorney speech
SEVERITY: high
EVIDENCE: `scripts/find_called_hearings.py:38` and `scripts/rank_hearings.py:53`
both split speakers with the same lexical rule:
`DEFER = re.compile(r"\byour honou?r\b|\b(yes|no),?\s+(ma'?am|sir)\b", re.I)` — any
sentence matching it is credited to the defendant (`their_share`, `their_words`,
`their_nums`, `detail_rate`), everything else to the judge. `judge_nathan.py:81-83`
states in its own system prompt that this is wrong: *"Attorney and defendant both
say 'your honor' and 'yes ma'am', so use context, not wording, to tell them apart."*
Measured over all 244 rows of `called_hearings.json`, counting only sentences
carrying an explicit lawyer marker
(`my client|may it please|we would ask|counsel|i represent|on behalf of`):
```
sentences credited to the defendant: 5760
of those, provably ATTORNEY speech: 71 = 1.2%
hearings with >=1 attorney sentence miscredited: 53 = 22% of the pool
mean attorney-word share inside their_share: 11.1%   max 98.9%
hearings where >50% of the defendant words are attorney speech: 30
   j1qve23gjOs:7789 99% | qk56IPbqnwg:1118 98% | 5dKFFblI_9I:3655 94%
   qn-Eji0kXAE:2952 90% | 07Os_qVWVUo:8716 87% | CGouAi4siV8:7539 84% ...
```
That 1.2% / 11.1% is a floor — it only counts sentences with an explicit lawyer
phrase; ordinary attorney speech ("yes ma'am", "your honor, he has") is
indistinguishable to this regex and is uncounted. Speaker-ID code exists and is not
used: a grep for `diarize|oncamera|who_speaks` over `find_called_hearings.py
rank_hearings.py judge_nathan.py judge_defendant_voice.py find_wentthere.py
index_moments.py` returns nothing, while `src/boydclips/diarize.py`,
`src/boydclips/oncamera.py` and `scripts/who_speaks.py` all exist.
WHY-IT-MATTERS: Nathan's rejection rule is explicit — *"If the lawyer does all the
talking, SKIP it. On one hearing he rejected: 'his lawyer asked he didn't talk'"*
(`judge_nathan.py:79-81`). At least 12% of the candidate pool is exactly the hearing
he rejects, ranked as if it were the hearing he wants. The LLM stage happens to have
caught these 30 (none reach `final_shortlist.json`), so today the damage is wasted
judging spend — but the lexical rank decides what the LLM ever sees, so genuinely
defendant-heavy hearings are being outranked by lawyer-heavy ones and dropped before
any model reads them.
PROPOSAL: Run `diarize.py` / `who_speaks.py` over each candidate span and compute
`their_share` from speaker turns, keeping DEFER only as a tiebreak. Cheaper interim:
subtract any sentence carrying a lawyer marker from `their_words` and re-rank — that
alone reprioritises 53 of 244 rows.
COST: Diarization over 244 spans is hours of GPU/CPU. The interim regex subtraction
is 5 lines and reorders `ranked_hearings.json`, which invalidates the existing
`judged_*.json` keys.

## F7: The selection stage has never run over the corpus — the deepest stage covers 40 of 1,701 videos (2.4%), and every selection state file is 8 days stale
SEVERITY: medium
EVIDENCE: 1,702 transcripts on disk (`glob('work/*/*.transcript.json')` = 1702),
1,701 distinct video ids, `select count(*) from dockets` = 1701. Coverage of each
selection artifact, measured as distinct `video_id` against that set:
```
called_hearings    rows=244    videos=177   coverage=10.4%
ranked_hearings    rows=197    videos=135   coverage= 7.9%
judged_nathan      rows=197    videos=135   coverage= 7.9%
judged_hearings    rows=180    videos=129   coverage= 7.6%
final_shortlist    rows=48     videos=40    coverage= 2.4%
wentthere          rows=500    videos=209   coverage=12.3%
funny              rows=462    videos=146   coverage= 8.6%
questions          rows=13924  videos=494   coverage=29.0%
moments            rows=389    videos=185   coverage=10.9%
```
The funnel is a strict chain (`ranked ⊂ called`, `judged_nathan ⊂ ranked`,
`final ⊂ judged_nathan` — all verified `True`), so the 10.4% at the top caps
everything below it. Every one of these files is dated 2026-08-20/21
(`ls --time-style=+%Y-%m-%d state/*.json`), i.e. 8 days old as of 2026-08-29, and
the top-of-funnel narrowness is not sampling — it is `out[:400]` in
`find_called_hearings.py:127` plus the F1 bug plus `out[:200]` in
`rank_hearings.py:141`.
WHY-IT-MATTERS: "The best clip in the archive" currently means "the best of 40
videos out of 1,701". Any footage pulled since 2026-08-21 has never been seen by
the selection stage at all, so the pipeline cannot be said to be running — it was
run once, by hand, over a week ago.
PROPOSAL: Add a `state/selection_manifest.json` recording, per video id, which
selection passes have run and at what code version, and make each `find_*` /
`rank_*` script process only the unseen ids. Then coverage is a query rather than a
forensic exercise.
COST: A day of plumbing across six scripts. Risk: introducing incremental state
means a code change no longer invalidates old rows — the manifest must key on a
scorer version or it will hide exactly the drift it is meant to expose.

## F8: Six selection state files totalling 4.3 MB are written and never read by any code, including three produced by no script at all
SEVERITY: medium
EVIDENCE: A `grep -rl` for each state filename across `src/ scripts/ tools/`,
cross-checked against the exact reference lines from
`grep -n "questions.json|funny.json|goingoff.json|dialogue_metrics|harsh_hearings|judged_opus" src/boydclips/*.py scripts/*.py`:
```
judged_opus.json      -> ORPHAN   (54 KB; no writer, no reader)
harsh_hearings.json   -> ORPHAN   (29 KB; no writer, no reader)
goingoff.json         -> ORPHAN   (1.8 MB; no writer, no reader)
dialogue_metrics.json -> only a prose mention at src/boydclips/diarize.py:43 (242 KB)
questions.json        -> only scripts/find_questions.py:28 OUT=...  (write-only, 2.0 MB)
funny.json            -> only scripts/find_funny.py:68 json.dump(...) (write-only, 74 KB)
```
`questions.json` is the largest at 13,924 rows over 494 videos — the broadest corpus
pass in the project (29% coverage, more than double anything in the live funnel) —
and nothing consumes it. `moments.json` (730 KB) is read only by its own consumer
`judge_moments.py:67`, which produces `moments_judged.json`, the one that
`momentrun.py` and `pipeline.py` actually use.
WHY-IT-MATTERS: Two problems in opposite directions. Someone re-orienting from disk
sees nine ranked candidate files and cannot tell which three drive the shortlist,
which is how a superseded ranking gets used to pick a video. And the widest, most
expensive pass in the repo (`questions.json`) sits unused while the live funnel runs
on 10% coverage.
PROPOSAL: Move the six to `state/superseded/` with a one-line `WHY.md` naming the
approach each replaced, quoting the original reason rather than re-wording it. Before
retiring `questions.json`, check whether its 494-video coverage should be feeding the
funnel instead of being deleted — that is Nathan's call, not a cleanup.
COST: Minutes, and it touches nothing executable. Risk: `studio.py:68` reads
`final_shortlist.json` then `called_hearings.json` by name, so only move files that
grep confirms unreferenced — the six above do.

## F9: Two of Nathan's stated criteria are absent from the code and one is explicitly inverted — repeat appearances are told to be ignored, and no 8-minute floor exists
SEVERITY: medium
EVIDENCE: Each stated criterion checked against the code.
*Defendant talks a lot* — implemented (`their_share`, `find_called_hearings.py:110`),
but by an invalid rule (F6).
*Drama / Boyd being stern* — implemented (`rank_hearings.py:52` `HARSH_END`,
`judge_hearings.py` `drama` 1-5).
*Boyd being funny* — `scripts/find_funny.py` exists but its output is read by nothing
(F8), so it is absent from the live path.
*Multiple appearances / repeat defendant* — **inverted.** `judge_nathan.py:96-99`
lists it under "NOT DISCRIMINATORS - ignore them": *"whether he is a repeat
offender"*. `src/boydclips/repeats.py` exists but a grep for `import repeats` /
`repeats.` finds it used only by `diag_camacho.py:7`, `probe_missing_oncamera.py:23`
and `repeat_shortlist.py` — three diagnostics, none in the selection funnel.
*Recent prison sentence* — not a signal anywhere. `grep -rn "prison"` across
`find_*.py rank_hearings.py judge_*.py moments.py arcs.py priors.py` returns only
`rank_hearings.py:53` (`going to prison` inside `HARSH_END`, an ending detector, not
a prior) and three docstrings warning that the word is her register, not an outcome.
*8+ minutes for RPM* — no floor. `find_called_hearings.py:33` sets
`MIN_S, MAX_S = 360.0, 1200.0` (6 min), and `judge_nathan.py:101` tells the model
*"length, as long as it is roughly 6 minutes or more"*. Measured on the output:
```
called_hearings n=244  min=364s  med=848s  8min+ (RPM): 233 (95%)  under 6min: 0
final_shortlist n=48   min 8.7min  med 14.5  max 19.6   under 8 min: 0
```
So today nothing under 8 min reaches the shortlist, but that is luck, not a gate —
11 of 244 candidates sit between 6 and 8 minutes with nothing to stop them.
WHY-IT-MATTERS: The repeat-offender inversion is a live contradiction between the
project memory and the prompt that actually picks clips, and only Nathan can say
which is current. The missing 8-minute gate is a one-line risk to long-form RPM the
day the pool changes.
PROPOSAL: Raise `MIN_S` to 480 for the long-form path and state the 8-minute RPM
reason in the comment. For the repeat criterion, put the conflict to Nathan as two
readings — (a) repeat appearances are a positive prior and `repeats.py` should feed
the rank, or (b) the "not a discriminator" line in the prompt is current and the
memory is stale — and do not resolve it in code either way.
COST: `MIN_S` is one line and shrinks the candidate pool by 11. Wiring `repeats.py`
into the rank is a day and would reorder everything downstream, so it should wait on
the answer.
