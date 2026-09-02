# Gates: leaf-1.2 — Clip selection and scoring

OWNS: .unlazy/boyd-audit/findings/leaf-1.2.md

Scope: Clip selection and scoring. Read-only audit. Deliverable is an evidence-bearing findings file; no pipeline file is modified.

- [ ] G1: findings file exists and every finding carries real evidence and a costed proposal
  CHECK: node .unlazy/boyd-audit/verify_findings.mjs --min 6 .unlazy/boyd-audit/findings/leaf-1.2.md
  EXPECT: findings verification passed
  EVIDENCE: pending

- [ ] G2: no pipeline file was modified by this leaf
  CHECK: node .unlazy/boyd-audit/verify_readonly.mjs leaf-1.2
  EXPECT: read-only verification passed
  EVIDENCE: pending

- [ ] G3: driver reviewed the findings and attempted to refute at least one, re-running its evidence command independently
  EVIDENCE: pending
