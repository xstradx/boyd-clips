# Gates: leaf-4.2 — What is actually live on Texas Trial Tracker

OWNS: .unlazy/boyd-audit/findings/leaf-4.2.md

Scope: What is actually live on Texas Trial Tracker. Read-only audit. Deliverable is an evidence-bearing findings file; no pipeline file is modified.

- [ ] G1: findings file exists and every finding carries real evidence and a costed proposal
  CHECK: node .unlazy/boyd-audit/verify_findings.mjs --min 3 .unlazy/boyd-audit/findings/leaf-4.2.md
  EXPECT: findings verification passed
  EVIDENCE: pending

- [ ] G2: no pipeline file was modified by this leaf
  CHECK: node .unlazy/boyd-audit/verify_readonly.mjs leaf-4.2
  EXPECT: read-only verification passed
  EVIDENCE: pending

- [ ] G3: driver reviewed the findings and attempted to refute at least one, re-running its evidence command independently
  EVIDENCE: pending
