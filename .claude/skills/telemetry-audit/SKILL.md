---
name: telemetry-audit
description: Audit one tool's telemetry at its pin: sender paths, the opt-out switch with file:line, an offline status run when one exists; then update its registry/telemetry.json row.
---
# telemetry-audit — a telemetry row is a claim with evidence (station forge; gap skill, invocable only)

`registry/telemetry.json` decides whether a workflow may start a tool (`verified: false` = never started). This
skill is how a row earns `verified: true`.

## Do
0. **Print the plan** for the row: `python3 tools/station/telemetry_plan.py show <tool>` gives its opt-out env, the
   bootstrap and run-tree commands, the offline status run (or `unread` + the file to read first) and the exact
   fields to flip on main; `... all` does it for every row of every station (Plane, trigger.dev, Lago included), so a
   self-hosted stack is never stuck behind a rule nobody can satisfy. `... gate <tool>` is the start gate the forge
   workflows run (exit 0 only when verified by a recorded run). When steps 1-3 establish a new status command,
   add it to that tool's `STATUS` table with its file:line.
1. **Find the senders at the pin** (read-only, no run): in the bootstrap cache or with
   `git -C <clone> grep -n -i -E "telemetry|posthog|sentry|segment|amplitude|DO_NOT_TRACK" <sha> -- <src>`; name
   the endpoint constant and the function that sends.
2. **Find the switch** and cite `file:line` for the code that reads it and for the gate that skips the send.
   Known at the kit pins: evo `plugins/evo/src/evo/telemetry.py:102-112` (EVO_TELEMETRY=0/false/off/no or
   DO_NOT_TRACK=1), gate `telemetry_enabled()` :120-121; openwiki `src/telemetry/gates.ts:28-32`
   (OPENWIKI_TELEMETRY_DISABLED or DO_NOT_TRACK truthy), gate `src/telemetry/senders.ts:136`; ProjectAtlas
   `crates/projectatlas-db/src/telemetry.rs:1` (local token accounting in the project DB, no sender found).
3. **Run the tool's own status command offline** (in a run-tree, network off, opt-out env set) when one exists:
   evo `EVO_TELEMETRY=0 evo telemetry status` must print `telemetry: off (env)`; openwiki has no status verb, so
   run one init with `--telemetry-file <f>` and expect `{"disabled": true, "sent": false}` in `<f>`.
4. Update the row: `evidence`, `evidence_line`, `opt_out`, `verified_by_run` = the exact command and what it printed,
   `verified: true`. On main, the row lives in `registry/telemetry.json` (kit-root owns it); on a station, propose
   the row in `work/telemetry/<tool>.md` and land it on main.
5. Never use a tool's "telemetry off" command as the opt-out: evo's sends a final opt-out event (cli.py:615-623).

## Test (what fails)
`python3 tools/station/forge_check.py check` (`forge_gates`): a row with `verified: true` and no `verified_by_run`.
The commons `telemetry` check additionally refuses `verified: true` with no file+line evidence.
