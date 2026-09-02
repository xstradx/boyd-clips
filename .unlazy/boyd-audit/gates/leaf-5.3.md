# Gates: leaf-5.3 — How unattended content pipelines are actually built in 2026 - external, fetched evidence only

OWNS: .unlazy/boyd-audit/findings/leaf-5.3.md

Scope: How unattended content pipelines are actually built in 2026 - external, fetched evidence only. Read-only; no pipeline file modified.

- [ ] G1: findings file exists and every finding carries real evidence and a costed proposal
  CHECK: node .unlazy/boyd-audit/verify_findings.mjs --min 8 .unlazy/boyd-audit/findings/leaf-5.3.md
  EXPECT: findings verification passed
  EVIDENCE: pending

- [ ] G2: no pipeline file was modified by this leaf
  CHECK: node .unlazy/boyd-audit/snapshot.mjs --diff
  EXPECT: read-only verification passed
  EVIDENCE: pending

- [ ] G3: driver reviewed the findings and attempted to refute at least one, re-running its evidence independently
  EVIDENCE: pending
