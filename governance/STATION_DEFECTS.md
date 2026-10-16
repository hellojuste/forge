# STATION_DEFECTS — the forge station's defects register (station `forge`)
owner: governance/rules.json R-defects · status: CURRENT · date: 2026-10-16 · supersedes: none · audit: python3 tools/station_audit.py -k defects -k defects_due

<!--
Grammar: the commons governance/DEFECTS.md header (one owner); rows here carry DEF-forge-nnnn ids with status,
where, owner, found_by, trigger (cmd:|event:|date:) and, while OPEN, why_not_fixed_now (never scope for an own defect).
Allocate ids with `python3 tools/gov/new_row.py def "<subject>"`.
-->

## DEF-forge-0001 · 2026-10-16 · setup_tool.py Windows branches (kit-bin wrapper under Git Bash, .cmd/.exe bin paths, venv Scripts/) are untested on a real Windows host
status: OPEN
where: tools/station/setup_tool.py § bin_path / write_wrapper / is_windows
owner: this-station
found_by: forge-setup child session (claude/stable-kit-forge), 2026-10-16: every real run was on Linux; the Windows branches are covered only by the instruction-line selftest cases
trigger: cmd: python3 tools/station/setup_tool.py --all && python3 tools/station/setup_tool.py --all   (on the operator's Windows 11 + Git Bash; the second run prints ready x4)
why_not_fixed_now: no Windows host is reachable from the cloud container this session runs in; the fix, if any, is in this station's file and lands on the operator's first run
