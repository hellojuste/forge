---
name: tool-trial
description: Trial a tool before adopting it: N >= 5 frozen tasks run without and with it, graded by the grade pack, plus the authors' own failed benchmarks; verdict promote/park with the denominator.
---
# tool-trial — adopt a tool only on a measured difference (station forge; gap skill)

A tool's own benchmark is the authors' numerator. The denominator is what YOU measured on YOUR tasks, with and
without it, and what the authors' failed runs say. This skill turns "this looks useful" into a TRIAL row.

## When
Before any tool (ProjectAtlas, openwiki, evo, an MCP server, a new CLI) is wired into a workflow, a hook or a
`.mcp.json` on any station. The router sends `projectatlas`, `trial`, `benchmark`, `tokens saved` here
(workflow `tool-trial`).

## Do
1. **Freeze the tasks first.** Write >= 5 real tasks from this kit (not from the tool's README) to
   `work/trials/<tool>/tasks.json`; record `sha256sum work/trials/<tool>/tasks.json` as `tasks_sha256`. No task is
   added, removed or reworded after the first run.
2. **Telemetry gate.** The tool's `registry/telemetry.json` row must be `verified: true`, or the run happens with the
   env opt-out set inside a run-tree (`python3 tools/kit/runtree.py`), never in the station. See `telemetry-audit`.
3. **Run arm A (without) and arm B (with)** on every task, same model and effort, fresh context per run. Record
   tokens, wall time, tool calls and the answer.
4. **Grade blind** with `commons/packs/grade/RUBRIC.md`: the grader sees answers without the arm label.
5. **Read the authors' failures.** For ProjectAtlas that is `repertoire/styler-ai~ProjectAtlas/docs/benchmarks/`
   (every `*-failed-*` file, including `v0.4-agent-navigation-failed-mcp-approval-9ec0331.jsonl`). Name what you
   read; "none published" is allowed only with where you looked.
6. **Verdict:** `promote` only if B beats A on the graded score without losing on tokens beyond the stated margin,
   on N >= 5; otherwise `park`. State both numbers with N.
7. Write `work/trials/<tool>.md` (`verdict:`, `n_tasks:`, `tasks_sha256:`, scores per arm, failed runs read) and
   append one row to the `## TRIALS` table in `governance/STATION_LEDGER.md`:
   `| TRIAL-forge-nnnn | <date> | <tool> | <N> | promote|park | <tasks_sha256> | <failed runs read> | work/trials/<tool>.md |`

## Test (what fails)
`python3 tools/station/forge_check.py check` (check `forge_gates`): a TRIAL row or report with N < 5, a verdict that
is not promote|park, a tasks hash that is not 64 hex, an empty failed-benchmark read, or a missing report.
Planted in `python3 tools/station/forge_check.py --selftest`.

## Never
Never quote the tool's own savings figure as the result. Never install the tool's plugin hooks to "try it"
(evo's PreToolUse `.*` hook-drain, ProjectAtlas readiness.sh): act_gate asks before any plugin install.
