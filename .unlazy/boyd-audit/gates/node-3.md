# Gates: node-3 — Reliability

Scope: integrate leaf-3.1, leaf-3.2, leaf-3.3 into one section of Nathan's breakdown, with contradictions between children resolved or left as a visible split.

- [ ] N1: every child findings file re-verifies
  CHECK: node .unlazy/boyd-audit/verify_findings.mjs --min 3 .unlazy/boyd-audit/findings/leaf-3.1.md .unlazy/boyd-audit/findings/leaf-3.2.md .unlazy/boyd-audit/findings/leaf-3.3.md
  EXPECT: findings verification passed
  EVIDENCE: pending

- [ ] N2: children's overlapping claims reconciled; every disagreement is either resolved by a measurement or reported as an open split
  EVIDENCE: pending
