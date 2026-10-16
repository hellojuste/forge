# .claude/hooks/station/ — forge station hook modules

None. The only hook module this station names in `station.json` `hooks.PreToolUse` is the commons
`connector_scope` (report-only; the list is a union with the commons modules `act_gate`, `quarantine_gate`,
`connector_scope`), so no station-only module lives here. The forge-specific asks (evo telemetry on/off, evo ship,
openwiki integrations install/auth/ingest, ProjectAtlas runtime installer, plugin installs, REA setup/update/analyze,
repin.py --apply, git push) are DATA in `station.json` `irreversible_acts`, read by the commons `act_gate`.
A future module goes here as `<name>.py` with `--selftest`, `Earned by:` and (for a DENY) `Release:` lines, is listed
as `station/<name>` in `station.json`, and is named by a rule in `governance/rules.d/station.json`; an unlisted `.py`
here is an orphan and fails `hooks_wired`.
