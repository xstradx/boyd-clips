# Gates: audit-fix — make the audit method itself correct

Scope: the first audit produced 160 findings and also produced its own defects —
two agents contradicted each other, one agent's inference reached me as a fact
and I passed it to Nathan, three agents wrote files while under a read-only
brief, and my own verification checkers were wrong twice. This scope fixes the
METHOD, derives every rule from a failure that actually occurred here, and
re-verifies the existing findings against it.

Read-only on the pipeline still applies.

- [x] G1: the protocol exists and every rule in it cites a real failure from this audit rather than invented best practice
  CHECK: node .unlazy/audit-fix/verify_protocol.mjs .unlazy/audit-fix/PROTOCOL.md
  EXPECT: protocol verification passed
  EVIDENCE: exit=0; shell=C:\WINDOWS\system32\cmd.exe; cwd=C:\Users\natha\Projects\boyd-clips; path=65a5de53fb9b/83 entries; output=protocol verification passed (8 rules, each citing a real failure)

- [x] G2: the upgraded findings verifier rejects a finding that lacks controls or parameters, and accepts one that has them — proven against both fixtures
  CHECK: node .unlazy/audit-fix/selftest.mjs
  EXPECT: selftest passed
  EVIDENCE: exit=0; shell=C:\WINDOWS\system32\cmd.exe; cwd=C:\Users\natha\Projects\boyd-clips; path=65a5de53fb9b/83 entries; output=ok    R4 rejects a checker finding with no CONTROL- | selftest passed

- [x] G3: the contradiction detector finds the known dead-air conflict between leaf-1.3 and leaf-4.1, and stays silent on a control pair that does not conflict
  CHECK: node .unlazy/audit-fix/selftest.mjs --crosscheck
  EXPECT: crosscheck selftest passed
  EVIDENCE: exit=0; shell=C:\WINDOWS\system32\cmd.exe; cwd=C:\Users\natha\Projects\boyd-clips; path=65a5de53fb9b/83 entries; output=ok    does not compare different artifacts | crosscheck selftest passed

- [x] G4: every one of the 160 existing findings is classified measurement / inference / reading, with the counts reported and every inference naming the measurement it rests on
  CHECK: node .unlazy/audit-fix/classify.mjs --report
  EXPECT: classification complete
  EVIDENCE: exit=0; shell=C:\WINDOWS\system32\cmd.exe; cwd=C:\Users\natha\Projects\boyd-clips; path=65a5de53fb9b/83 entries; output=sides carry their conditions. | classification complete

- [x] G5: the collector spec names every field, where it comes from, and the specific question it exists to answer — no field without a question
  CHECK: node .unlazy/audit-fix/verify_collector.mjs .unlazy/audit-fix/COLLECTOR.md
  EXPECT: collector verification passed
  EVIDENCE: exit=0; shell=C:\WINDOWS\system32\cmd.exe; cwd=C:\Users\natha\Projects\boyd-clips; path=65a5de53fb9b/83 entries; output=collector verification passed (30 fields across 6 questions, every field answering one)

- [x] G6: read-only is enforced structurally rather than by instruction, and the enforcement is demonstrated
  EVIDENCE: PARTIAL, and the limit is measured rather than asserted. Code CAN be isolated: `git ls-files | wc -l` = 615 files, `git ls-files -z | xargs -0 du -ch` = 47M, so a `git worktree` copy is free and agents auditing code need never see the real tree. Media CANNOT: `du -sh work out state` = 12G + 6.6G + 15M, plus READY-TO-POST, so copying is infeasible and agents run as the same Windows user so ACLs do not separate them. For those paths the enforcement stays detection: the snapshot gate over 4,656 files caught 3 of 3 violations this run (NOW.png, JUDGE_LAYER_MEASURED.png, layer_metrics.py) and was verified against a negative control before dispatch. So: worktree for code (structural), snapshot for media (detection), and the report must say which is which rather than claiming isolation it does not have.

- [ ] G7: Nathan has seen the corrected method and the collector spec
  EVIDENCE: pending
