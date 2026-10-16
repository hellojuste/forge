# RETURN — slice main-commons (branch claude/stable-kit-main)

owner: child main-commons · status: CURRENT · date: 2026-10-16 · supersedes: none · audit: `python3 tools/station_audit.py` + the selftests listed below

**Status: DONE.** Every finding this slice owned is fixed. One is partly declined: the `router_targets` red-under-equip_pending
half of CRITIC F1 (d), with the reason given below. Two follow-ups belong to the station children; they are listed under
"Stations must act". All work is commons, edited on main and stage-by-path. Generated files (MANIFEST, OWNERSHIP, map/*,
brain/INDEX) were regenerated with their tools after every change, and each merge of the sibling main-kittools was
resolved by regenerating.

## What changed

| commit | what |
|---|---|
| `1956346` | Router (DEC-core-0009). `multi_intent_cap` now refuses a prompt only when it looks like a document (≥ 3 newlines, or ≥ 4 clauses and > 300 chars); below that threshold the matched intents are ranked. Keywords also match their plurals (`s`, `es`, `y→ies`). A row-level `exclude` blanks phrases before matching: governance-admin `ledger` became the phrases `the ledger`/`ledger row`/…, and `general ledger`/`grootboek` are excluded. Row-level `claims` rank a row first within its tie slot and let a kit_tree leaf raise the WRONG STATION hint on one hit. The hint now counts phrases (margin ≥ 2, or ≥ 2 total / 1 claim when nothing local matched). An ABSENT first move always prints a fall back. New commons intents: `handoff` and `checkpoint`. In kit_tree, the bare `client`/`erp`/`dashboard`/`market`/`markets` became phrases; client-bi gained Power BI (`power bi`, `pbix`, `dax`, `power query`, `general ledger`); research gained market research/sizing/competitor work; career, venture and quarantine gained `claims`. |
| `6caf1d0` | `act_gate` arms on a live key that is non-empty in a `.env`, in **the process environment**, or **inline in the command** (`KEY=v cmd`, `export KEY=v`). It asks only when a runner sits at command position, so reads of the real held AutoHedge path never ask. It adds a `-m autohedge` / `import autohedge` pattern. `live_keys` is configurable (defaults.json + station schema). In `quarantine_gate`, a `VAR=value` prefix is resolved (split on `:`), `-c`/`-e` code strings are scanned for quarantined paths, a bare `yarn`/`bun` counts as an install, and segmentation is quote-aware via `_cmdscan`. The `station_audit` headline counts a skipped MUST as `NOT RUN (names)`, never as clean. |
| `1af6877` | **Skill-visibility ruling (DEC-core-0010).** New `tools/upstream/skill_surface.py`. `--write` symlinks every canonical `router/skills.json` row that sits inside a lane to `.claude/skills/<name>`; name collisions get `--<repo>`, then `-n`. Mirrors, symlinks, variants and fixtures are not surfaced. It also **generates** `.claude/settings.json` `skillOverrides` from station.json `skill_hide`, which accepts duplicates only (`why: mirror\|variant\|fixture\|harness`; a cap-style hide is a violation), and `skillListingBudgetFraction` from station.json `skill_listing_budget_fraction`. `--check` (new MUST check `skill_surface`, rule `R-skill-surface`) proves the links and both keys. `commons_drift` hashes settings.json without those two keys (`_gov.GENERATED_SETTINGS_KEYS` / `commons_sha256`), so the file stays commons-owned. `listing_budget` is now hygiene for kit-authored skills plus a **report** against Claude Code's real budget (fraction × `context_window_tokens` × 4 chars, default 1 % of 200k). Over budget is one worklist row naming the fraction that would fit; nothing is hidden. Only settings.json counts as hidden (LEAN F2 planted case). `listed_max` and `listing_budget_bytes` are retired from defaults, the template and gov_check; R-skill-overrides and R-listing-budget keep their old wording under `superseded_text`. `deny_upstream_write` resolves symlinks, so a write through a surfaced link into a lane is still denied. claudeMdExcludes also covers CLAUDE.md/AGENTS.md reached through a surfaced link. CLAUDE.md gained one Governance bullet (no new section). |
| `d35a033` | The router names a surfaced skill natively: `SKILL: read <path> (<name>) · /<surface>`. |
| `4771051` | SessionStart card: an ABSENT skill/workflow first move prints `[ABSENT] — instead: <inline_gather or find>`, so it never sends a session to a missing target. The purpose is printed once (the ladder drops its `purpose:` line under the card). LOOP lines are cut at a word boundary. New brain audit gate `CARD-BUDGET` measures the **untruncated** card against `sessionstart_budget_bytes`. Summon S3 gained the LL-41 clause "NEVER LAUNDER A DENIAL" and a return shape with `denials[]`. |
| `10a9d51`, `1173e3e` | `docs/design/{LEAN_LESSONS,PROGRAMME_MAPPING,PROGRAMME_BRAIN,PROGRAMME_GOVERNANCE}.md`, carried verbatim by the new `tools/gov/carry_design.py`, which adds a GENERATED header naming the source ref. New check `design_docs` (map programme, rule `R-lessons-resolve`): the byte comparison with the design branch runs when the ref is reachable and is skipped (worklist) in a private copy without it. The check also confirms that every `LL-nn` cited outside the lanes resolves to a `### LL-nn` heading. Today 28 cited ids resolve. Brain nodes core-0001/0002 and the LEDGER intro now cite `docs/design/LEAN_LESSONS.md`. `docs/` is registered in map/dirs.json. |
| `7f36248` | The router selftest reader accepts the `{"positive": [...], "negative": [...]}` shape that `skill_routes.py` documents (ASSEMBLY_NOTES C2 / CRITIC F14). |
| `2abe2c0` | `offline_complete` reads the kit's shared bootstrap cache via `tools/kit/_kit.upstream_cache` (main-kittools handover 2). |

## Findings owned → disposition

| id | disposition | evidence |
|---|---|---|
| Operator ruling 2026-10-16 (retire listed_max 6; native visibility; duplicates only via settings.json; budget = report) | **fixed** | DEC-core-0010; skill_surface selftest 20; workflows_check selftest 25 (a station.json-only override is NOT counted hidden; over budget is worklist, never red). Dry run on a venture worktree merged with this main: `skill_surface --write` gave `131 surfaced`, then `skill_surface` PASS. Listing report: `139 skill(s) listed, 3 hidden · 50826 chars of an 8000-char budget … OVER`. The worklist row names `skill_listing_budget_fraction >= 0.064` (the operator's call: it costs about 13k tokens per turn). |
| LEAN F2 (listing diet never reached the harness; false green) | **fixed** | As above: only `.claude/settings.json` counts, and its contents are generated and checked. |
| CRITIC F2 (multi_intent_cap rejects one-sentence prompts) | **fixed** | The cap applies only to document-shaped prompts. The selftest covers a one-line 4-intent prompt (routed), a multi-line paste and a long multi-clause paste (refused). |
| CRITIC F3 (bare client/erp/market/dashboard; career override) | **fixed** | `REAL_MAIN_CASES`: 19/19 realistic tasks reach the right station on the real main table. These include the CRITIC §1 table (6 of whose rows were wrong) and REPRODUCE F6's CV prompt. |
| CRITIC F4 (commons `ledger` captures "general ledger") | **fixed** | The selftest routes "reconcile the revenue kpi against the general ledger" to nothing and "add a row to the ledger" to governance-admin. |
| CRITIC F5 (Power BI) — kit_tree part | **fixed** | "Build a Power BI report for Wilvo…" goes to `STATION: client-bi`. The station `kpi`/`qa` intents are station files (client-bi child). |
| CRITIC F9 (wrong-station hint ignores phrases) | **fixed** | Fixture-station selftests: "Review the Qlik load script for Kanon" gives the client-bi hint; "Tailor my CV for a BI role" gives the career hint. |
| CRITIC F12 / LEAN F7 (plurals) | **fixed** | "find papers on …" and "who owns these decisions" both route. This applies to skills.json keywords too. |
| LEAN F6 (handoff/checkpoint routes) | **fixed** | Commons intents `handoff` and `checkpoint` are in the tie order, with selftest rows. |
| CRITIC F1 / LEAN F1 — card part | **fixed** | Brain selftest: an ABSENT workflow is flagged with its gather; one with no gather falls back to find; a PRESENT one is sent directly. The router prints `— do not invoke it; fall back to: python3 tools/map/find.py <words>` when no gather exists. |
| CRITIC F1 (d) / LEAN F1.2 — `router_targets` red under equip_pending | **declined (as a commons change now)** | `router_targets` already turns MUST-red for an ABSENT workflow once a station drops `equip_pending` (gov_check plant "workflow absent (no equip_pending)"). Making it red earlier would turn every station red while the equip children are building those workflows. The card and router no longer dead-end, which was the operator-facing harm. |
| REPRODUCE F5 / SAFETY 4 (key in process env / inline) | **fixed** | act_gate selftest 24 covers process env, inline `KEY=v`, `export KEY=v`, an empty inline value (disarmed) and a configured `live_keys` name. The value never appears in the reason. |
| SAFETY 3 (act_gate over-asks on reads) | **fixed** | Four reads of the real path `study/The-Swarm-Corporation~AutoHedge/autohedge/...` run armed and do not ask. |
| SAFETY 2 (quarantine_gate bypasses) | **fixed** | quarantine_gate selftest 30 covers `PYTHONPATH=study/… python3 -m`, PATH-list values, `python3 -c "runpy.run_path('study/…')"`, `node -e require(…)`, bare `yarn`/`bun` inside a quarantined tree, and their allowed counterparts outside it. |
| LEAN F5 (headline counts SKIP as clean) | **fixed** | The station_audit selftest asserts `0/1 clean · 1 NOT RUN (g)`. |
| LEAN F8 (purpose twice; budget overrun not caught) | **fixed** | Brain selftest "purpose printed once". Audit gate `CARD-BUDGET` measures the full card (planted 2,000-char purpose fires only it). |
| LEAN F9 (LL-41 clause) | **fixed** | Summon S3 has the clause and `denials[]` in the return shape. |
| LEAN F3 (LL citations dangle; brain/LEDGER cite an unshipped file) | **fixed** | The `design_docs` check (28 LL ids resolve, 4 of 4 files byte-equal to the design branch) and the repointed citations. |
| REPRODUCE F10 c (LOOP lines cut mid-word; purpose twice), handed over by main-kittools | **fixed** | `_word_cut` selftest; purpose as above. |
| CRITIC F14 / ASSEMBLY_NOTES C2 (two selftest shapes, one reader) | **fixed** | Router selftest "positive/negative shape". |
| main-kittools handover 2 (offline_complete cache) | **fixed** | upstream_checks offline_complete selftest 6 (a shared cache is read). |
| main-kittools handover 3 (`mode_at_pin` per PROVENANCE row, NOTICE line) | **deferred** | The kittools return calls it optional: `registry/held_modes.json` and its check already record all 41 changes. Re-test trigger: the next `ingest.py` run. |

## Stations must act (after merging this main)

1. **Every station:** run `python3 tools/upstream/skill_surface.py --write`, then commit `.claude/skills/<links>` and `.claude/settings.json` by path. Until that runs, the MUST check `skill_surface` is red, naming each missing link. That red is intended: the skills are not yet visible. Delete the station.json `skill_overrides` rows; they are reported as retired worklist rows because Claude Code never read them. A true duplicate goes to `skill_hide` with its `why`. Optional: `skill_listing_budget_fraction` (the report prints the value that fits).
2. **venture child:** row 17 (`custom-fields-development`) must become a mirror (main-kittools handover 1). On the merged venture dry run this is the only red: `skill_routes: kind variant, assignment says mirror`.
3. Station router fragments: the station halves of CRITIC F5/F12 and REPRODUCE F6 (`engagement`, `palette`, an `offer` intent, `launch plan`, and so on) are station files. The commons router changes keep every station's own router selftest green: all 8 were run with this router and tables (venture 295, markets 255, client-bi 162, career 192, research 172, studio 166, forge 186, quarantine 141 cases, all OK).

## Final tails (2026-10-16, claude/stable-kit-main @ 2abe2c0)

```
.claude/hooks/intent_router.py --selftest: selftest OK (145 cases, 56 fixture prompts)
.claude/hooks/act_gate.py --selftest: act_gate selftest OK (24 cases)
.claude/hooks/quarantine_gate.py --selftest: quarantine_gate selftest OK (30 cases)
.claude/hooks/deny_upstream_write.py --selftest: deny_upstream_write selftest OK (33 cases)
.claude/hooks/station_dispatch.py --selftest: selftest OK (7 cases)
tools/upstream/skill_surface.py --selftest: skill_surface selftest OK (20 cases)
tools/upstream/workflows_check.py --selftest: workflows_check selftest OK (25 cases)
tools/upstream/upstream_checks.py all --selftest: offline_complete selftest OK (6 cases) (all checks OK)
tools/gov/carry_design.py --selftest: carry_design selftest OK (6 cases)
tools/gov/gov_check.py --selftest: selftest OK (107 cases)
tools/brain.py selftest: selftest OK · 60/60 pass
tools/station_audit.py --selftest: selftest OK (87 cases)
python3 tools/station_audit.py: station_audit: 0 red · 37/37 clean · worklists 29
```
