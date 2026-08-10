# SAFETY RULES — Boyd Clips

Texas district court proceedings are public record and the court publishes this
livestream itself. Clipping it is lawful.

**The court redacts at the source.** Judge Boyd mutes audio and cuts the camera
when material may not be shown. Sealed records, juvenile detail and protected
victim identifiers are therefore filtered upstream by the court, which has far
better information than any scoring model. This file does not re-litigate those
decisions. If it aired on the public stream, it is usable.

What remains is a short list protecting the one thing the court's redaction
cannot protect: **the channel's monetization**, and the accuracy of cuts the
court did not make.

Rules are enforced as a hard gate in scoring. Everything else is editorial
judgement and belongs in `CONTENT_SPEC.md`, not here.

---

## R1 — Presumption of innocence is a wording rule

Not a rejection rule. It never drops a case; it constrains phrasing.

- Use "charged with", "accused of", "faces a charge of".
- Never assert the underlying conduct as fact ("the man who stole").
- A guilty plea or conviction on the record **is** a fact and may be stated.

**Why:** asserting a crime someone has not been convicted of is defamation per
se in Texas and is not cured by a disclaimer. Phrasing costs nothing to get
right.

---

## R2 — No identifiable minors on camera

Rejected only if a person visibly under 18 appears on camera or is named. If the
court aired it, this rarely fires.

**Why:** not ethics — YouTube demonetizes and strikes for minors in criminal
proceedings regardless of legality. This protects revenue.

---

## R3 — No unredacted third-party contact details

Rejected only if the clip contains an address, phone number, or employer of a
victim or witness that the court did **not** mute. Names alone are fine — they
are on the public record.

**Why:** YouTube's harassment policy treats broadcast contact details as
doxxing. Strike risk, not squeamishness.

---

## R4 — The cut may not invert the outcome

Rejected only if a viewer seeing the clip would believe the *opposite* of what
happened — an acquittal shown as a conviction, a granted motion shown as denied,
a judge's warning shown as a ruling.

This is deliberately narrow. A clip does not need to contain the full ruling, be
self-explanatory, or represent the whole proceeding. Courtroom exchanges are
supposed to be dramatic out of context; that is the format. Only outcome
inversion is disqualifying.

**Why:** the court chose what to broadcast. It did not choose our edit, and a
cut that reverses a legal outcome is the one editing decision with real
defamation exposure.

---

## R5 — Never reorder speech

Cuts may remove material. They may never reorder it. Splicing two statements out
of sequence manufactures an exchange that never occurred.

Costs nothing, blocks nothing, prevents the one unrecoverable mistake.

---

## R6 — Titles must be supported by the clip's own audio

A title is a factual assertion. It must be audible in the clip. See
`CONTENT_SPEC.md` §6.

---

## R7 — Takedown path

Every published clip's manifest records its exact source timestamps. On a
removal request from a subject, attorney, or the court: **remove first,
evaluate second.** Logged in the state ledger with the reason.

---

## Enforcement

The scoring model returns, per case:

```json
{
  "safety_pass": true | false,
  "safety_rule_violations": ["R2"],
  "safety_reasoning": "..."
}
```

**Uncertainty resolves to ACCEPT.** Reject only on a specific, articulable
violation of a rule above, citing which rule and what triggered it. A vague
discomfort is not a violation. If you cannot name the rule and the trigger, the
case passes.

Rationale: the court already filtered this footage. A false reject costs a day's
clip on a channel that needs daily output; the remaining rules exist to catch
narrow, nameable failures, not to express caution.
