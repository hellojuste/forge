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

## DEC-core-0009 · 2026-10-16 · Router ranks one-sentence prompts instead of refusing them; bare high-collision keywords become phrases; handoff and checkpoint are routed
kind: rule
status: CURRENT
words: > "how would someone resolve these into a rational decision tree set of subfolders"
locator: operator ORDER 1 (design/OPERATOR_ORDERS.md on claude/stable-kit-design), applied after the independent reviews design/review/CRITIC.md F2-F4, F9, F12 and LEAN.md F6, F7, 2026-10-16
covers: [.claude/hooks/intent_router.py, router/intents.json, router/kit_tree.json]
note: multi_intent_cap now refuses only prompts that look like documents (>= 3 newlines, or >= 4 clauses and > 300 chars); keywords match plurals; governance-admin `ledger` became phrases with an `exclude` for "general ledger"/"grootboek"; kit_tree drops bare client/erp/dashboard/market/markets and gains `claims` (career, venture, quarantine); the WRONG STATION hint counts phrases; an ABSENT first move always prints a fall back. Re-test: python3 .claude/hooks/intent_router.py --selftest (REAL_MAIN_CASES = the 18-task table, 19/19 to the right station).

## DEC-core-0010 · 2026-10-16 · The 6-skill listing cap is retired: every canonical skill homed in a station is natively visible; only true duplicates are hidden, in the settings file Claude Code reads
kind: rule
status: CURRENT
words: > "its nuts to think there would only use 6 anyway what is the point of doing all this ... ? weird built out"
locator: operator ruling relayed verbatim by PRIME session_01GbdVhRTvKX1mxo9qitPKER to child slice main-commons, 2026-10-16, reacting to the reviews' "listed_max 6" design (design/review/LEAN.md F2)
covers: [tools/upstream/skill_surface.py, tools/upstream/workflows_check.py, .claude/settings.json, commons/defaults.json, templates/station.json.tmpl, tools/gov/_gov.py]
note: tools/upstream/skill_surface.py --write symlinks every canonical router/skills.json row inside a lane to .claude/skills/<name> (Claude Code follows skill-dir symlinks; the directory name invokes the skill) and GENERATES .claude/settings.json skillOverrides from station.json skill_hide (duplicates only: mirror|variant|fixture|harness) plus skillListingBudgetFraction from station.json skill_listing_budget_fraction. commons_drift hashes settings.json without those two keys (tools/gov/_gov.py GENERATED_SETTINGS_KEYS); skill_surface --check (MUST) proves them and the links current. listing_budget is hygiene plus a REPORT against the real budget (1% of the context window), never a cap. Supersedes the R-skill-overrides and R-listing-budget wording settled under DEC-core-0001 (listed_max 6, listing_budget_bytes 2400; station.json skill_overrides, which Claude Code never read). The router stays an extra precision layer, never a gate. Upstream instruction files still never auto-load: the _upstream_claude renames and claudeMdExcludes stand, and claudeMdExcludes now also covers CLAUDE.md/AGENTS.md reached through a surfaced skill link.

## DEC-core-0011 · 2026-10-16 · Proven cross-station pieces move to the commons: the design engine, the protection pack and self-check, the shared market-scan
kind: rule
status: CURRENT
words: > "reconcile everything that needs be into the core, then i will pull."
locator: OPERATOR ORDER 2026-10-16, relayed verbatim by PRIME session_01GbdVhRTvKX1mxo9qitPKER to child slice reconcile-01 (claude/stable-kit-main)
covers: [tools/design/, tools/protect/, tools/research/, commons/packs/protection/, commons/packs/design/HANDOFF.md, commons/schema/design_tokens.schema.json, governance/rules.d/design.json, governance/rules.d/protect.json, governance/rules.d/research.json, governance/checks.d/design.json, governance/checks.d/protect.json, governance/checks.d/research.json, .claude/skills/design-review/, .claude/skills/site-protection/, .claude/skills/shared-market-scan/, tools/gov/_gov.py]
note: From DONE stations only (studio-v2, quarantine defensive, research-v2, client-bi-v2, venture-v2). Studio's detector, contrast, direction catalog (roll client, opted out) and the handoff/token lints -> tools/design/ (R-design-detector, R-design-roll, R-design-handoff); quarantine's protection pack -> commons/packs/protection/ and self_check -> tools/protect/ with every rail (loopback + the station's own work/protection/OWNED.txt only, broker/exchange refused, no override, stdlib only; R-protect-own-targets carries R-quarantine-own-targets); research's custody + sizing -> tools/research/ (R-research-market-scan), refusing NC-lane sources so NC-derived numbers never reach client-bi/venture deliverables (research keeps nc_stamp/nc_export and the NC lane). Studio, quarantine and research keep the study/work and import the commons copy; their station rows name the commons owner. Forge (understand/Atlas/openwiki/evo/rea) and career (CLI) are PENDING: still live. Re-test: python3 tools/station_audit.py on main and on each synced station. Amended 2026-10-16 (same pass): the skill first landed as .claude/skills/market-scan/ and was renamed shared-market-scan, because research's .claude/workflows/market-scan.js shares the name (LL-02, workflows_parse red on research).
