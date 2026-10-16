---
name: kit-maintain
description: Maintain the kit: repin report (path diff, LICENSE diff, new agent/hooks/.mcp.json files, telemetry grep, repurposed check), sync --check and listing budgets across branches.
---
# kit-maintain — repin and keep the branches in step (station forge; gap skill, invocable only)

The kit is pinned upstream text plus branches that share a commons. Both drift. This skill is the maintenance
pass, run from the forge worktree (workflow `kit-repin` for one repo).

## Do
1. **Repin report** (never a hand edit of a pin): `python3 tools/kit/repin.py --report <owner~repo> <new-sha>`
   (needs `python3 tools/kit/bootstrap.py <owner~repo>` first). It prints 1 the path-scoped diff of the held paths,
   2 the LICENSE/NOTICE blob diff, 3 new agent/hooks/MCP files, 4 a telemetry grep over changed files, 5 the README
   first-paragraph diff (repurposed repo: AIHawk became invisible_dots), 6 the certain tests to run.
2. Copy the report to `work/repin/<owner~repo>-<sha7>.md` with header lines `repo:`, `from_sha:`, `to_sha:`,
   `licence_diff: same|changed`, `stop_items: <n>`, `status: green|STOPPED`, `applied: yes|no`.
3. **Any STOP item stops.** A changed licence blob means the licence is decided again before ingest
   (`upstream-intake`), not after; new agent files are listed in `upstream/PRECEDENCE.json`; new telemetry goes
   through `telemetry-audit`.
4. Only when green: `python3 tools/kit/repin.py --apply <owner~repo> <new-sha>` (act_gate asks), then re-ingest the
   held paths with `tools/upstream/ingest.py` and regenerate `NOTICE.md`.
5. Across branches: `python3 tools/kit/sync.py --check` (commons drift) and, per station worktree,
   `python3 tools/station_audit.py -k listing_budget -k upstream_lock` and `python3 tools/kit/repin.py --check`.

## Test (what fails)
`python3 tools/station/forge_check.py check` (`forge_gates`): a repin report with `licence_diff: changed` (or
`stop_items` > 0) whose status is not STOPPED or that was applied. `repin.py --apply` itself refuses while the
report has a STOP item (`python3 tools/kit/repin.py --selftest`).
