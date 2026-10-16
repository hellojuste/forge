# STATION_DECISIONS — the forge station's verbatim decisions (station `forge`)
owner: governance/rules.json R-decisions · status: CURRENT · date: 2026-10-16 · supersedes: none · audit: python3 tools/station_audit.py -k decisions

<!--
Grammar: the commons governance/DECISIONS.md header (one owner); rows here carry DEC-forge-nnnn ids.
Never delete, never renumber, never edit a `words:` line. A station row overrides a commons rule only by naming
its rules.json id. Allocate ids with `python3 tools/gov/new_row.py dec "<subject>"`.
-->

## DEC-forge-0001 · 2026-10-16 · Forge station adoptions: tools are trialled before use, upstream CLIs run disarmed in run-trees, nothing commons is overridden
kind: rule
status: CURRENT
words: > "make each of these packages workflow'd and fully equipped for their purpose, while ensuring that we bring our lean and efficiency lessons with us unless the repo's included have superceding instructions"
locator: operator ORDER 1, relayed verbatim in the stable-kit workflow task (_design/OPERATOR_ORDERS.md), 2026-10-16
covers: [station.json, governance/checks.d/station.json, governance/rules.d/station.json, .claude/rules/station.md, .env.example]
note: How the forge station is reconciled to its purpose (KIT_PLAN 4, forge). Adoptions, each naming the commons rule it uses, none overridden: (1) R-telemetry-claimed is tightened on this branch by R-forge-telemetry-run (a verified row also needs the recorded offline run, as registry/telemetry.json's own rule says); evo, openwiki and ProjectAtlas stay verified:false until the operator runs their status commands, so no workflow starts them; (2) R-no-secret-walls: .env carries the LLM key NAMES evo/openwiki/ProjectAtlas read, values empty, plus OPENWIKI_TELEMETRY_DISABLED=1, EVO_TELEMETRY=0 and DO_NOT_TRACK=1 (opt-out values, not secrets); no hook blocks committing a filled .env (ORDER 5); (3) R-irreversible / R-act-gate: evo telemetry on/off (off sends a final event), evo ship, openwiki integrations install/auth/ingest, the ProjectAtlas runtime installer, plugin installs, rea-agents setup / rea update / rea analyze-*, repin.py --apply and git push are added to station.json irreversible_acts so act_gate asks; (4) R-no-upstream-plugin-install: evo's '.*' hook-drain and ProjectAtlas readiness.sh stay in the bootstrap cache and are never wired; (5) R-connector-report stays report-only with connectors_expected empty; ProjectAtlas/openwiki MCP entries exist only as disabled examples in .mcp.local.example.json; (6) R-listing-budget: tool-trial and evo-guard are listed beside the commons closeout and handoff (4 of 6); telemetry-audit, kit-maintain and re-legal-gate are invocable only. Station rules R-forge-* are additions under rank 3 of R-precedence; every held upstream governs nothing (upstream/PRECEDENCE.json governs [] on every row).
