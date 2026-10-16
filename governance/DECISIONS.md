# DECISIONS — the verbatim decisions log (commons rows, station `core`)
owner: governance/rules.json R-decisions · status: CURRENT · date: 2026-10-16 · supersedes: none · audit: python3 tools/station_audit.py -k decisions

<!--
Grammar (parsed by tools/gov/_gov.py parse_rows; checked by `gov_check.py decisions`):
## DEC-<station>-nnnn · YYYY-MM-DD · <subject>
kind: rule | exception | amendment | correction | grant
status: CURRENT | SUPERSEDED <date> by DEC-<station>-nnnn | PARTIAL by DEC-<station>-nnnn (§ <what>)
words: > "<the human's words, VERBATIM, typos kept; abridged only to the operative clause>"
locator: <where the words were said: session + event + UTC, file@commit, or "typed in chat <UTC>">
covers: [<path#anchor>, ...]      (optional)
amends: DEC-<station>-nnnn        (kind amendment only)
note: <the session's own words, clearly not the human's>

Rules: never delete, never renumber, never edit a `words:` line (a correction is a new kind: correction row).
Superseding edits ONLY the old row's status: line. Allocate ids with `python3 tools/gov/new_row.py dec "<subject>"`.
Commons rows live here (DEC-core-nnnn, edited on main only); a station writes governance/STATION_DECISIONS.md.
-->

## DEC-core-0001 · 2026-10-16 · JSON and the Python stdlib for every registry; station.json is the name-equivalent of LEAN's station.yml
kind: rule
status: CURRENT
words: > "pls dont ignore my instruction to backfill the efficiency programmes we have unless there are superceding instructions as well, inclusive of the mapping and brains and governance (unless there are superceding)"
locator: operator ORDER 2, relayed verbatim in the stable-kit-b2b workflow task, 2026-10-16
covers: [commons/defaults.json, commons/schema/station.schema.json, tools/gov/_gov.py]
note: The planner's settlement (KIT_PLAN 8.1, J1 RF-12, J2 F11) of HOW the three programmes are backfilled: every registry is JSON read by the stdlib, so audit, router and brain run on every branch with no install. No PyYAML anywhere.

## DEC-core-0002 · 2026-10-16 · The precedence ladder has one owner (KIT_PLAN section 5)
kind: rule
status: CURRENT
words: > "while ensuring that we bring our lean and efficiency lessons with us unless the repo's included have superceding instructions"
locator: operator ORDER 1, relayed verbatim in the stable-kit-b2b workflow task, 2026-10-16
covers: [governance/rules.json#R-precedence, upstream/PRECEDENCE.json]
note: Ladder, highest first: 1 the operator's words (DEC rows) · 2 kit floor (upstream: NEVER — deny_destructive, deny_upstream_write, deny_generated_edit, act_gate ask, quarantine_gate ask, company_scope, the audit runner, the router, the registers, amend-never-delete, the closeout line, the denominator rule) · 3 station rules (a station overrides a commons rule only by a DEC-<station> row naming its rules.json id) · 4 upstream conventions (only the closed SUBTREE vocabulary build, code-style, test-runner, commit-format, layout inside a held tree; or mode: workspace) · 5 commons defaults (lean SHOULD lessons) · 6 repertoire method text. An included repo supersedes rank 5 in its subtree, never rank 2.

## DEC-core-0003 · 2026-10-16 · No secret walls: every station ships .env slots and no hook blocks committing secrets
kind: rule
status: CURRENT
words: > "so feel free to put whatever secrets its fine" and "i dont care about this because im going local then placing things myself later"
locator: operator ORDER 5, relayed verbatim in the stable-kit-b2b workflow task, 2026-10-16
covers: [CLAUDE.md#Invariants, .claude/settings.json]
note: Builders never invent a secret value; the built repo carries names with empty values. Branches are not treated as security boundaries.

## DEC-core-0004 · 2026-10-16 · Hosted MCP defaults (Reactive Resume, Supabase) are left as shipped
kind: rule
status: CURRENT
words: > "just leave these for the hosted ill worry about that myself"
locator: operator ORDER 4, relayed verbatim in the stable-kit-b2b workflow task, 2026-10-16
note: station/career and station/venture .mcp.json carry the upstream server entries byte-for-byte; no repointing.

## DEC-core-0005 · 2026-10-16 · camofox-browser, Maxun and AIHawk/invisible_dots are packed together in station/quarantine; install/run asks
kind: rule
status: CURRENT
words: > "quarantine, it exists, its public, its on github, just pack them together"
locator: operator ORDER 4, relayed verbatim in the stable-kit-b2b workflow task, 2026-10-16
covers: [.claude/hooks/quarantine_gate.py]

## DEC-core-0006 · 2026-10-16 · AutoHedge is held whole in the markets study lane with a startup note, disarmed by default
kind: rule
status: CURRENT
words: > "this sounds like we should copy it with a startup note to study it intently and understand how it works, not discard it"
locator: operator ORDER 4, relayed verbatim in the stable-kit-b2b workflow task, 2026-10-16
covers: [.claude/hooks/act_gate.py]
note: Disarmed = the study lane's SOLANA_PRIVATE_KEY is empty; act_gate asks before execute_trade/ultra_tools while a key is present.

## DEC-core-0007 · 2026-10-16 · Holding modes, neutralisation at ingest, and branch discipline (commons / station-only / GENERATED / append-only)
kind: rule
status: CURRENT
words: > "if you can do the 'main holds the shared core and decision tree and each station gets its own self-contained branch' in a zip then great, if not then make a branch-that-is-a-repo-that-holds-the-shared-core-and-decision-tree-and-each-station-gets-its-own-self-contained-branch so its easy clean up"
locator: operator ORDER 2, relayed verbatim in the stable-kit-b2b workflow task, 2026-10-16
covers: [commons/MANIFEST.json, tools/gov/gen_manifest.py, .claude/hooks/station_dispatch.py]
note: KIT_PLAN 3.3 and 4.1. A commons file is identical on every branch (commons_drift); a station adds station-only files that never exist on main (main_purity); station hooks, checks, rules and router rows are overlay modules and fragments, never edits of commons files.

## DEC-core-0008 · 2026-10-16 · Every census SKILL.md is homed in exactly one station and routed there
kind: rule
status: CURRENT
words: > "intent study under a per section while maintaining our skills where there is plausbile gaps and ensuring all 359 are inclusive in these as well with the relevant intent routing where each would live"
locator: operator ORDER 4, relayed verbatim in the stable-kit-b2b workflow task, 2026-10-16
covers: [router/intents.json]
note: Mirrors and symlinks route to their canonical copy; the router's skill fall-through reads router/skills.json.
