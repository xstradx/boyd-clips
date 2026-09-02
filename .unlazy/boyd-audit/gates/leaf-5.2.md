# Gates: leaf-5.2 — The human-input surface - how many decisions one finished video costs today

OWNS: .unlazy/boyd-audit/findings/leaf-5.2.md

Scope: The human-input surface - how many decisions one finished video costs today. Read-only; no pipeline file modified.

- [ ] G1: findings file exists and every finding carries real evidence and a costed proposal
  CHECK: node .unlazy/boyd-audit/verify_findings.mjs --min 6 .unlazy/boyd-audit/findings/leaf-5.2.md
  EXPECT: findings verification passed
  EVIDENCE: pending

- [ ] G2: no pipeline file was modified by this leaf
  CHECK: node .unlazy/boyd-audit/snapshot.mjs --diff
  EXPECT: read-only verification passed
  EVIDENCE: pending

- [ ] G3: driver reviewed the findings and attempted to refute at least one, re-running its evidence independently
  EVIDENCE: pending
