# Gates: boyd-audit root — reliability audit of the Boyd Clips pipeline

Scope: a complete, evidence-bearing breakdown of the Boyd Clips pipeline and a
costed list of proposed changes for Nathan to approve. Read-only: no pipeline
file is modified this pass.

- [ ] R1: all thirteen leaf findings files exist and every finding carries real evidence and a costed proposal
  CHECK: node .unlazy/boyd-audit/verify_findings.mjs --min 3 .unlazy/boyd-audit/findings/leaf-1.1.md .unlazy/boyd-audit/findings/leaf-1.2.md .unlazy/boyd-audit/findings/leaf-1.3.md .unlazy/boyd-audit/findings/leaf-2.1.md .unlazy/boyd-audit/findings/leaf-2.2.md .unlazy/boyd-audit/findings/leaf-3.1.md .unlazy/boyd-audit/findings/leaf-3.2.md .unlazy/boyd-audit/findings/leaf-3.3.md .unlazy/boyd-audit/findings/leaf-4.1.md .unlazy/boyd-audit/findings/leaf-4.2.md .unlazy/boyd-audit/findings/leaf-5.1.md .unlazy/boyd-audit/findings/leaf-5.2.md .unlazy/boyd-audit/findings/leaf-5.3.md
  EXPECT: findings verification passed
  EVIDENCE: pending

- [x] R2: the audit modified nothing outside its own workspace
  CHECK: node .unlazy/boyd-audit/snapshot.mjs --diff
  EXPECT: read-only verification passed
  EVIDENCE: exit=0; shell=C:\WINDOWS\system32\cmd.exe; cwd=C:\Users\natha\Projects\boyd-clips; path=65a5de53fb9b/83 entries; output=read-only verification passed (4656 files unchanged since baseline)

- [ ] R3: the consolidated breakdown exists and every proposal in it carries a reason and a cost
  CHECK: node .unlazy/boyd-audit/verify_findings.mjs --min 8 .unlazy/boyd-audit/BREAKDOWN.md
  EXPECT: findings verification passed
  EVIDENCE: pending

- [ ] R4: driver independently re-ran at least one evidence command per leaf and recorded the result
  EVIDENCE: pending

- [ ] R5: Nathan has seen the breakdown and decided which proposals to act on
  EVIDENCE: pending

- [ ] R6: the breakdown states the OUTCOME Nathan is actually chasing in my own words, and says plainly what his sketched approach does not cover — rather than building his examples
  EVIDENCE: pending
