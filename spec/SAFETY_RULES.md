# SAFETY RULES — Boyd Clips

Texas district court proceedings are public record, and the court publishes
this livestream itself. Clipping it is lawful. That is not the same as it being
harmless.

The people in these clips did not choose to be filmed, are mostly not public
figures, and many are in the worst week of their lives. This file exists so
that a system running unattended cannot quietly turn that into a liability —
legal, platform, or moral.

Rules below are **enforced as a hard gate** in the scoring stage. A case that
fails any of them is dropped before rendering, regardless of how good it is.

---

## R1 — Presumption of innocence is not optional

Most people appearing on a docket have been **accused**, not convicted.

- Use "charged with", "accused of", "faces a charge of".
- Never "the man who stole", "the woman who assaulted", or any construction
  asserting the underlying conduct as fact.
- Never imply guilt through framing, title, or caption emphasis.
- A guilty plea entered on camera **is** a fact and may be described as one.
- A conviction is a fact and may be described as one.

**Why:** stating that someone committed a crime they have not been convicted of
is defamation per se in Texas, and unlike most content risk it is not cured by
a disclaimer.

---

## R2 — No juveniles

Any case involving a person under 18, in any role — defendant, victim, witness,
or family member being discussed — is rejected outright. No exceptions, no
blurring, no "their name wasn't said."

---

## R3 — No sexual-offense victims

Any case involving a sexual offense is rejected. Even where the court has not
sealed identifying detail, the possibility of exposing a victim is not worth
any amount of engagement.

---

## R4 — No third-party identifiers

Reject if the clip contains a victim's, witness's, or juror's name, address,
phone number, employer, or any detail that would let a viewer locate them.

The defendant's name is generally on the public record and may appear. Everyone
else's presence in that courtroom is not a choice they made.

---

## R5 — No jury material

Reject anything touching juror identity, juror questioning, or deliberations.
This can create actual legal exposure for the proceeding itself.

---

## R6 — Vulnerability is not content

Reject when the thing that makes the moment compelling is a person's:

- visible mental-health crisis,
- intoxication or withdrawal,
- disability or cognitive impairment,
- inability to afford counsel, fines, transport, or housing.

**The test:** is the drama coming from a *decision or exchange*, or from
watching someone suffer? Only the first is publishable.

A defendant arguing with the judge is a decision.
A defendant sobbing while unable to answer is suffering.

---

## R7 — The clip must be honest on its own

Reject if a viewer who sees only the clip would form a materially false
impression of what happened.

This is the rule that catches the most cases in practice. Courtroom exchanges
routinely look outrageous when the surrounding twenty minutes are removed —
a judge appearing harsh is often enforcing a condition the defendant already
agreed to, on a record the clip doesn't show.

**Selective editing that changes the meaning of a proceeding is the single
highest-risk thing this system could do.** It is also the easiest to do by
accident, because the most misleading cut is often the most engaging one.

---

## R8 — Never reorder speech

Cuts may remove material. They may never reorder it. Two statements spliced
out of sequence can manufacture an exchange that never occurred.

---

## R9 — Titles are claims

A title is a factual assertion. It must be supported by the clip's own audio.
See `CONTENT_SPEC.md` §6.

---

## R10 — Takedown path

Every published clip's manifest records its exact source timestamps. If a
subject, attorney, or the court requests removal, the standing policy is:
**remove first, evaluate second.** The engagement value of any single clip is
not worth contesting a removal request from someone whose worst day it depicts.

Removals are logged in the state ledger with the reason, so that patterns in
requests can inform the rules above.

---

## Enforcement

The scoring model returns, per case:

```json
{
  "safety_pass": true | false,
  "safety_rule_violations": ["R2", "R7"],
  "safety_reasoning": "..."
}
```

`safety_pass: false` drops the case before any video is downloaded. The model is
instructed that **uncertainty resolves to rejection** — a false reject costs one
day's clip; a false accept can cost considerably more.
