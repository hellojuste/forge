# STATION_LEDGER — the forge station's procedural lessons and tool-trial verdicts (station `forge`)
owner: governance/rules.json R-ledger · status: CURRENT · date: 2026-10-16 · supersedes: none · audit: python3 tools/station_audit.py -k ledger -k ledger_owed -k forge_gates

<!--
Grammar: the commons governance/LEDGER.md header (one owner); rows here carry L-forge-nnnn ids, each amending a
mechanism (never conduct) with its hook classified HOOKED | OWED — trigger | NOT HOOKABLE.
Allocate ids with `python3 tools/gov/new_row.py ledger "<HEADLINE>" --kind procedural`.
TRIAL rows (skill tool-trial, workflow tool-trial) go in the `## TRIALS` table at the end, never as L rows:
| TRIAL-forge-nnnn | date | tool | N (>= 5) | promote|park | tasks_sha256 (64 hex) | failed runs read | report path |
checked by `python3 tools/station/forge_check.py check` (forge_gates).
-->

(no station lessons yet)

## TRIALS

| id | date | tool | n | verdict | tasks_sha256 | failed_read | report |
|---|---|---|---|---|---|---|---|
