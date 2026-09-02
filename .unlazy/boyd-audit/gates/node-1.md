# Gates: node-1 — Pipeline

Scope: integrate leaf-1.1, leaf-1.2, leaf-1.3 into one section of Nathan's breakdown, with contradictions between children resolved or left as a visible split.

- [ ] N1: every child findings file re-verifies
  CHECK: node .unlazy/boyd-audit/verify_findings.mjs --min 3 .unlazy/boyd-audit/findings/leaf-1.1.md .unlazy/boyd-audit/findings/leaf-1.2.md .unlazy/boyd-audit/findings/leaf-1.3.md
  EXPECT: findings verification passed
  EVIDENCE: pending

- [ ] N2: children's overlapping claims reconciled; every disagreement is either resolved by a measurement or reported as an open split
  EVIDENCE: pending
