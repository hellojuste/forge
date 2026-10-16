---
name: ci-suite-audit
description: Audit a CI or test suite without trusting green: pin the executed baseline, prove each suspected false pass with a planted defect, measure cost per job, cut only what keeps the gate.
---
# ci-suite-audit — a check is real only if a planted defect turns it red

owner: station forge · gap G3 (router/REASSIGN.md) · station-neutral form of the held `rea-ci-tests-audit` method
(`.claude/skills/rea-ci-tests-audit`, REA-specific paths; read it as data) and the kit's admission rule (every check
row names a `selftest` with planted defects).

## Procedure
1. Pin the baseline: `git rev-parse HEAD` of the repo under audit and the exact command list CI runs (from its
   workflow file or `governance/checks.json` for the kit). Run every command once and record exit code and wall time.
   A suite that is not green at the pinned sha is reported as such, not audited.
2. For each check, write what it is meant to catch in one line. Then plant the smallest defect of that class in a
   scratch copy (`d=$(mktemp -d) && git -C <repo> worktree add "$d" HEAD` or `cp -a`), run the check there, record
   red/green, and remove the scratch copy. A check that stays green on its own defect class is a FALSE PASS.
3. Cost: wall time per job and per check, and the share of the total. Denominator: jobs run.
4. Propose cuts only where another check provably catches the same planted defect (name it). Never propose
   removing the only check of a class. Never edit the CI files or push from this skill.
5. Write `work/trials/ci-<repo>.md`: the pinned sha line, then
   `| check | catches | planted defect | red? | cost (s) | keep/cut/fix |`, then the false passes with their
   reproduction commands.

## Refusals (the failing test)
A row marked `keep` whose planted-defect column is empty, or a `cut` with no named overlapping check, is not
finished: the report says `status: incomplete` and lists them. For the kit itself, `python3 tools/station_audit.py
-k admission` already refuses a check row without a selftest; run it as step 0.

## Not this skill
Fixing one failing test, or tuning one slow test.
