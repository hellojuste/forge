# DEFECTS — invariant 14 as a register (commons rows, station `core`)
owner: governance/rules.json R-defects · status: CURRENT · date: 2026-10-16 · supersedes: none · audit: python3 tools/station_audit.py -k defects -k defects_due

<!--
Grammar (checked by `gov_check.py defects`; DUE rows counted by `defects_due`):
## DEF-<station>-nnnn · YYYY-MM-DD · <what is wrong>
status: OPEN | FIXED <commit> | WONTFIX DEC-<station>-nnnn | MOVED <register id>
where: <path § heading or function — never a line number>
owner: this-station | <other lane / branch / upstream tree>
found_by: <session / locator>
trigger: cmd: <command whose exit 0 means fixed> | event: <the next change to X> | date: YYYY-MM-DD
why_not_fixed_now: <required while OPEN: why it is not this lane's file to fix now>

A defect in a file you own is your owed result: owner: this-station with an OPEN status may not give scope
("out of scope", "not a one-line fix") as why_not_fixed_now. Allocate ids with `python3 tools/gov/new_row.py def "<subject>"`.
Station rows go in governance/STATION_DEFECTS.md.
-->

(no open defects)
