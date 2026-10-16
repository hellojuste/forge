# LEDGER — procedural and delegation lessons that changed a mechanism (commons rows, station `core`)
owner: governance/rules.json R-ledger · status: CURRENT · date: 2026-10-16 · supersedes: none · audit: python3 tools/station_audit.py -k ledger -k ledger_owed

<!--
Grammar (checked by `gov_check.py ledger`; OWED hooks counted by `ledger_owed`):
## L-<station>-nnnn — <THE GENERAL RULE IN CAPITALS>
kind: procedural | delegation
pathology: - | P1 SILENT | P2 STUCK | P3 DRIFT | P4 CONFABULATION | P5 OVERSPEND | P6 SHARED-ERROR | P7 NULL | P8 COLLISION
axis: effort | judgement
hook: HOOKED <hook path> | OWED <shape> — trigger: <condition> | NOT HOOKABLE <the fact no harness event carries>
amendment: <path or path#heading of the mechanism that changed> (never "be more careful")
**What happened.** <date, what, measured cost>
**The general rule.** <one sentence>
> **Re-test trigger:** <event | date | command>
**Record:** <locator>, <date>

Never delete a row; a later row whose amendment names it supersedes it. Allocate ids with
`python3 tools/gov/new_row.py ledger "<HEADLINE>" --kind procedural`. Station rows go in governance/STATION_LEDGER.md.
The seed rows below are the lettuce lessons that earned each commons hook (source: docs/design/LEAN_LESSONS.md, carried as data).
-->

## L-core-0001 — A WHOLE-TREE STAGE SWEEPS ANOTHER WRITER'S FILES; A PATTERN KILL KILLS A SIBLING'S RUN
kind: procedural
pathology: -
axis: effort
hook: HOOKED .claude/hooks/deny_destructive.py
amendment: .claude/hooks/deny_destructive.py
**What happened.** lettuce LEDGER L86: `git add -A` swept two workers' in-flight files into an unrelated commit and `pkill -f` killed a sibling's baseline run; L82 and S15/S79 repeated the shapes; L415 widened the force-push deny from main to every ref.
**The general rule.** Destructive shell shapes are denied mechanically, each with its allowed form named as the release.
> **Re-test trigger:** python3 .claude/hooks/deny_destructive.py --selftest
**Record:** lettuce LEDGER L86, L82, L415 via LEAN_LESSONS LL-17, 2026-10-16

## L-core-0002 — "NOTED" IS NOT AN OUTCOME: A DEFECT ONLY WRITTEN DOWN IS A DEFECT SHIPPED
kind: procedural
pathology: -
axis: effort
hook: HOOKED .claude/hooks/deny_noted_defect.py
amendment: .claude/hooks/deny_noted_defect.py
**What happened.** lettuce Invariant 14, AMENDED 2026-10-09: a child lane left its own TRI_ASC/TRI_DSC defect as "out of scope"; hedge words in reports carried no register id.
**The general rule.** A staged hedge line in a watched register needs a DEF/L/DEC id on the same line, or the commit is denied.
> **Re-test trigger:** python3 .claude/hooks/deny_noted_defect.py --selftest
**Record:** lettuce OPERATOR_RULES Invariant 14 via LEAN_LESSONS LL-31, 2026-10-16

## L-core-0003 — A CONTEXT LINE IS A REMINDER, NEVER A SEAL, AND IT IS NEVER SAID TO A SUBAGENT
kind: procedural
pathology: -
axis: effort
hook: HOOKED .claude/hooks/context_threshold.py
amendment: .claude/hooks/context_threshold.py
**What happened.** lettuce sealed every session at the handoff line and reverted it the same week (three human-driven sessions locked mid-task); a subagent was told "HANDOFF 467k" on its first tool call.
**The general rule.** The handoff reminder fires once per crossing per session, never denies, and stays silent in subagent transcripts.
> **Re-test trigger:** python3 .claude/hooks/context_threshold.py --selftest
**Record:** PROGRAMME_GOVERNANCE 3.15 and its gap row, 2026-10-16

## L-core-0004 — A TURN THAT COMMITS WORK ENDS WITH A CLOSE-OUT LINE OR IT WAS NOT CLOSED
kind: procedural
pathology: -
axis: effort
hook: HOOKED .claude/hooks/stop.py
amendment: .claude/hooks/stop.py
**What happened.** lettuce passes that committed and ended without the close-out ritual left their lessons unfiled; the asides line rule (G12.5) became a Stop check after it was skipped in prose.
**The general rule.** The Stop hook reports once when a committing turn has no `closeout:` line, and never loops.
> **Re-test trigger:** python3 .claude/hooks/stop.py --selftest
**Record:** lettuce CLAUDE.md asides rule via PROGRAMME_GOVERNANCE 3.17, 2026-10-16

## L-core-0005 — THE FIRST MOVE IS A GATHER, NOT A GUESS; A HARNESS TURN OR A PROHIBITION IS NOT A REQUEST
kind: procedural
pathology: -
axis: effort
hook: HOOKED .claude/hooks/intent_router.py
amendment: .claude/hooks/intent_router.py
**What happened.** lettuce R105 ("THE FIRST SHOULD ALWAYS GATHER"); about 15 harness turns were misrouted in one session; four words cancelled "no idea why the bridge fails"; 11 of 13 multi-intent prompts were pasted documents.
**The general rule.** Every human prompt is routed to one first move from data, with harness prefixes, negators and a multi-intent cap.
> **Re-test trigger:** python3 .claude/hooks/intent_router.py --selftest
**Record:** lettuce intent_router docstring via LEAN_LESSONS LL-19, 2026-10-16

## L-core-0006 — A SHARED SETTINGS FILE EDITED ON EVERY BRANCH CONFLICTS ON EVERY MERGE
kind: procedural
pathology: -
axis: effort
hook: HOOKED .claude/hooks/station_dispatch.py
amendment: .claude/hooks/station_dispatch.py
**What happened.** The kit design review (KIT_PLAN 3.3) found that per-station hook entries in settings.json would make the commons file differ per branch and conflict on every sync.
**The general rule.** Station hooks are modules named in station.json and run by one commons dispatcher; settings.json stays identical on every branch.
> **Re-test trigger:** python3 .claude/hooks/station_dispatch.py --selftest
**Record:** KIT_PLAN 3.3, contract commons-gov decision 4, 2026-10-16

## L-core-0007 — NESTED UPSTREAM AGENT FILES LOAD AS INSTRUCTIONS UNLESS THEY ARE NEUTRALISED AND WRITE-GUARDED
kind: procedural
pathology: -
axis: effort
hook: HOOKED .claude/hooks/deny_upstream_write.py
amendment: .claude/hooks/deny_upstream_write.py
**What happened.** lettuce measured nested upstream .claude/skills being listed on first Read and kept vendor_nested as an open register with no write guard.
**The general rule.** Lanes are read-only to agents except _PATCHES files whose first line is NOT APPLIED.
> **Re-test trigger:** python3 .claude/hooks/deny_upstream_write.py --selftest
**Record:** LEAN_LESSONS LL-03, LL-08 via PROGRAMME_GOVERNANCE 3.14, 2026-10-16

## L-core-0008 — AN IRREVERSIBLE ACT (A TRADE, A SEND, AN APPLICATION) WAITS FOR THE HUMAN
kind: procedural
pathology: -
axis: effort
hook: HOOKED .claude/hooks/act_gate.py
amendment: .claude/hooks/act_gate.py
**What happened.** lettuce LL-18: anything that touches a live process or real money is written as a patch; AutoHedge's execute_trade signs Jupiter swaps when a key is present (ORDER 4).
**The general rule.** Irreversible acts ASK; a RELEASES row turns a named pattern into allow.
> **Re-test trigger:** python3 .claude/hooks/act_gate.py --selftest
**Record:** LEAN_LESSONS LL-18, KIT_PLAN 6, 2026-10-16

## L-core-0009 — A QUARANTINED TREE IS READ FREELY AND RUN ONLY WITH THE HUMAN'S YES
kind: procedural
pathology: -
axis: effort
hook: HOOKED .claude/hooks/quarantine_gate.py
amendment: .claude/hooks/quarantine_gate.py
**What happened.** ORDER 4 packed camofox, Maxun and AIHawk/invisible_dots together; their install and run paths (telemetry, stealth tooling) are the act worth a question.
**The general rule.** Install/run inside a quarantined path asks; reads never do.
> **Re-test trigger:** python3 .claude/hooks/quarantine_gate.py --selftest
**Record:** KIT_PLAN 6 quarantine paragraph, 2026-10-16

## L-core-0010 — A CONNECTOR OUTSIDE THE STATION'S NOUN IS REPORTED, NOT SILENTLY USED
kind: procedural
pathology: -
axis: effort
hook: HOOKED .claude/hooks/connector_scope.py
amendment: .claude/hooks/connector_scope.py
**What happened.** lettuce CA-10 deny_connector enforced the noun boundary; ORDER 5 removed confidentiality walls, so the portable form is a report with a deny knob.
**The general rule.** An unexpected mcp server is named once per session; a station may opt into deny by a DEC row.
> **Re-test trigger:** python3 .claude/hooks/connector_scope.py --selftest
**Record:** LEAN_LESSONS CA-10, KIT_PLAN 6, 2026-10-16

## L-core-0011 — A GENERATED FILE IS A CLAIM: REGENERATE IT, NEVER HAND-EDIT IT
kind: procedural
pathology: -
axis: effort
hook: HOOKED tools/map/hooks/deny_generated_edit.py
amendment: tools/map/hooks/deny_generated_edit.py
**What happened.** lettuce L409: three clean branch tips merged into a red main because generated files were hand-merged; L196: 13 of 37 red CI runs came from a lane forbidden to run the generators.
**The general rule.** Hand edits of files declaring GENERATED in their first 3 lines are denied; merges regenerate.
> **Re-test trigger:** python3 tools/map/hooks/deny_generated_edit.py --selftest
**Record:** LEAN_LESSONS LL-24, 2026-10-16

## L-core-0012 — CHECK WHETHER IT EXISTS BEFORE BUILDING IT
kind: procedural
pathology: -
axis: effort
hook: HOOKED tools/map/hooks/prior_art.py
amendment: tools/map/hooks/prior_art.py
**What happened.** lettuce built near-duplicate tools twice before the SOLUTIONS catalog and the prior-art reminder existed (LL-06).
**The general rule.** A Write that creates a new tool or skill is answered with the nearest existing ones.
> **Re-test trigger:** python3 tools/map/hooks/prior_art.py --selftest
**Record:** LEAN_LESSONS LL-06, CA-13, 2026-10-16

## L-core-0013 — A MAP NOBODY MEASURES ROTS: RECORD WHAT IS ACTUALLY USED
kind: procedural
pathology: -
axis: effort
hook: HOOKED tools/map/hooks/usage_log.py
amendment: tools/map/hooks/usage_log.py
**What happened.** The cairn rule (LL-49) separates what a session HELD from what it USED; without a usage log the atlas cannot tell cold tools from hot ones.
**The general rule.** Tool, skill and read use is logged (map knob M and above) so the atlas ranks by measured use.
> **Re-test trigger:** python3 tools/map/hooks/usage_log.py --selftest
**Record:** LEAN_LESSONS LL-49, PROGRAMME_MAPPING usage, 2026-10-16

## L-core-0014 — THE NEXT SESSION STARTS FROM THE PLAN, NOT FROM THE DIFF
kind: procedural
pathology: -
axis: effort
hook: HOOKED tools/brain.py
amendment: tools/brain.py
**What happened.** lettuce /clear opened blind (Table A row 34) and compaction lost the NEXT block until the context ladder printed it first within a byte budget.
**The general rule.** SessionStart prints the orientation card, NEXT and the audit state within 1,500 B; writes are surfaced to the brain.
> **Re-test trigger:** python3 tools/brain.py selftest
**Record:** LEAN_LESSONS LL-44, CA-11, 2026-10-16
