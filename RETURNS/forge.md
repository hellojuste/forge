# RETURNS — station forge (equip-forge + review fixes)

owner: child session for claude/stable-kit-forge (parent PRIME session_01GbdVhRTvKX1mxo9qitPKER) · status: DONE ·
date: 2026-10-16 · branch: claude/stable-kit-forge · main merged at 74b7eca

**Status.** Equip done. The station has its seven saved workflows. Each one's certain test checks the deliverable the workflow writes. The five REASSIGN/CRITIC gap skills are built and routed, `equip_pending` is off, the 21 canonical held skills are surfaced natively (DEC-core-0010), and the full audit is 0 red in a fresh clone of the branch. No workflow has run end to end yet (see Gaps).

## What changed (commits on this branch since ad66887)

| commit | what |
|---|---|
| `e4f2e50` | Merge of `origin/claude/stable-kit-main` (main-commons slice). The conflicts were in generated map files only, and they were resolved by regenerating them (`usage_map`, `gen_atlas`, `gen_solutions --write`). |
| `91eb938` | `skill_surface.py --write`: 21 canonical held skills are linked into `.claude/skills/`. station.json drops `skill_overrides`, `listed_max` and `listing_budget_bytes`, and `gov.model_roster` = haiku / sonnet / opus. |
| `4380df5` | 7 workflows. 5 gap skills. `tools/station/telemetry_plan.py`. `forge_check.py` gains the gates noise, wiki, arch, intake and roster plus `output <kind> <path>`. Router first moves are renamed and each gets an `inline_gather`. 5 new skill intents. `equip_pending` is removed. DEC-forge-0002. Map catalogue and tags. `.claude/settings.json` regenerated (`skill_listing_budget_fraction` 0.013). |
| `2d3930f` | STATION.md workflow and skill tables. work/README. REASSIGN `EQUIP DECISIONS`. Rules R-forge-noise-floor, R-forge-design-twice, R-forge-workflow-output. Registry telemetry proposal. |
| (this commit) | The proposal is marked as partly landed on main. RETURNS/forge.md. |

## Workflows built (`.claude/workflows/`, `workflows_check` 9/9 parse + certain_tests, 7 station + 2 commons)

| workflow | phases (tier) | deliverable | certain test (can fail) |
|---|---|---|---|
| `trial-run` | Gather (small), Freeze (small), Noise (medium), Run 2N arms (medium), Grade (large), Verdict (large), Verify (small) | `work/trials/<tool>.md` + TRIAL row | `forge_check.py output trial {path}`: red on N<5, missing noise floor, a promote inside the spread, or a verdict with no TRIAL row |
| `optimize-loop` | Gather, telemetry gate (code-enforced), Discover, Freeze (holdout hash + K=5), Optimize, Remeasure (large), Verify | `work/optimize/<slug>.md` | `output optimize`: red with no holdout hash or frozen_at, or out-of-sample with no score or inside the spread |
| `wiki-gen` | Gather, Target (refuses client), telemetry gate, Generate, Review (large), Verify | `work/wiki/<name>/REVIEW.md` or a `refused-*` record | `output wiki`: red when generated for a client target or with the openwiki row unverified |
| `reverse` | Gather, Gate (large; anything but proceed returns), Analyse, Findings (large), Verify | `work/re/<slug>.md` | `output re`: red when the report has no gate row, a missing gate, or a third-party proprietary target without a right |
| `intake-run` | Gather (census), Place (large), Ingest, Route (skill-route-intake), Verify | `work/intake/<slug>.md` + held files + routes | `output intake` && `skill_routes.py check` && `skill_surface.py --check`: red on a short sha, or an ingest with no LOCK row |
| `arch-review` | Gather, Design ×2 blind (large), Judge (large), Verify | `work/arch/<slug>.md` | `output arch`: red with fewer than 2 designs, no depth table, or no pick |
| `kit-repin` | Gather, Report, Tests (only if no STOP), Record (`applied: no`), Verify | `work/repin/<key>-<sha7>.md` | `output repin` && `repin.py --check`: red on a licence change not STOPPED or on applied: yes |

Every workflow has: meta as a pure literal, `--dry` (returns the plan and spawns no agent), required-args refusal, a schema on every agent, a beat, a refusal clause and the FORBIDDEN list, and `DEFAULT_MODELS` equal to station.json (forge gate `roster`). `tool-trial` and `upstream-intake` are named `trial-run` and `intake-run` because `workflows_parse` refuses a workflow that shares a skill's name (DEC-forge-0002).

## Gap skills and tools

- `noise-floor` (G2), `design-it-twice` (G1), `ci-suite-audit` (G3), `skill-route-intake` (G4), and `skill-author` (CRITIC purpose gap: skill-building).
- `telemetry-audit` gains step 0. `tools/station/telemetry_plan.py` (`all | show | gate`, selftest 8) prints, for each of the 11 registry rows: opt-out env, bootstrap, run-tree, offline status run (5 known, otherwise `unread` + the file to read first) and the exact flip on main.
- Router: intents telemetry, noise, ci-audit, skill-build, maintain. Keywords were frozen before the prompts. Two ties were resolved with `claims`. The router selftest has 209 cases, all OK.

## Findings → disposition

| finding | disposition | evidence |
|---|---|---|
| LEAN F1 / REPRODUCE F1 / CRITIC F1 (7/7 forge workflows ABSENT, no fallback, path-only certain tests, STATION.md claims) | **fixed** | 7 workflows PRESENT. Router: "repin supabase to a new sha" → `workflow kit-repin [PRESENT] · gather: python3 tools/kit/repin.py --check`. `equip_pending` is removed, so `router_targets` is MUST and 0 red. Certain tests check the output. STATION.md is reworded. |
| CRITIC §1 #13 ("Trial the evo optimizer … denominator") | **fixed** | → `FIRST MOVE (trial): workflow trial-run [PRESENT]` (station selftest row added) |
| LEAN F2 + operator ruling (6-skill cap) | **fixed** (station side of DEC-core-0010) | `skill_surface: 0 violation(s) · denominator 21`. Listing: 36 listed, 9,670 of 10,400 chars, fits. station.json overrides retired. |
| LEAN F8 / REPRODUCE F10c (forge card 1,449–1,503 B, purpose twice) | **fixed** (commons fix by main + forge) | card now 1,313 B (`brain.py hook session-start | wc -c`), purpose printed once |
| CRITIC F11 (forge part: telemetry verify path missing) | **fixed** | `telemetry_plan.py all`: "11 rows · 0 verified · 5 with a status command". Workflows gate on `telemetry_plan.py gate <tool>`. |
| CRITIC F13 (gap skills not routed) | **fixed for forge** | 5 skill intents, plus tool-trial / evo-guard / re-legal-gate / design-it-twice named by their workflows. Station skills.json rows stay census-only, because `skill_routes` checks them against the assignment. |
| SAFETY 8 (registry evo/openwiki rows stale vs forge evidence) | **fixed on main** (79ec056) for evo/openwiki. **ProjectAtlas deferred** to main. | `work/telemetry/registry-proposal.md` (SUPERSEDED-in-part line). The ProjectAtlas `opt_out: unread` row still needs reading at the pin. |
| REASSIGN G1–G4 | **built** | see EQUIP DECISIONS |
| REASSIGN R1 / R3 (copies to venture / research) | **deferred** (cross-station; another owner) | REASSIGN EQUIP DECISIONS |
| CRITIC F20 (forge worklists 39 at birth) | **deferred** | now 35. `--ratchet` baselining is a commons/assembly call; not run here. |
| LEAN F3, F5, F6, F9; CRITIC F2, F9, F12, F14 (commons causes touching forge) | **fixed on main**, verified here after the merge | router selftest 209 OK; audit headline counts NOT RUN |
| LEAN F4, F10; CRITIC F16 (commons/kit files) | **not forge's** | owned by main / kit-root |

**Proposal for main:** add `skip` to the router's `NEGATORS_DEFAULT`. "skip the ci audit" routed to `ci-audit`. The selftest prompt was reworded and the original was kept in the case's `_note`.

## Gaps (each with its settling test)

- No workflow has been executed end to end. None of the tools they start is telemetry-verified yet, and no upstream bootstrap cache exists in this container. Settle with `Workflow({name: "kit-repin", args: {dry: true}})` per workflow (plan returned, 0 agents), then a real `trial-run` on projectatlas after `telemetry_plan.py show projectatlas` has been run and recorded on main.
- evo, openwiki and ProjectAtlas stay `verified: false`, so `optimize-loop` and `wiki-gen` refuse at the gate by design. Settle: the operator's offline status runs, recorded as `verified_by_run` on main; then `telemetry_plan.py gate evo` exits 0.
- The status commands for trigger.dev / maxun in `telemetry_plan.py` STATUS come from registry file:line evidence, not from a run at the pin. Settle: the telemetry-audit step 3 run in a run-tree.

## Final tails (fresh `git clone` of this branch @ 2d3930f + this commit)

```
python3 tools/station_audit.py            -> station_audit: 0 red · 38/38 clean · worklists 35 · 4.7s   (rc=0)
python3 tools/upstream/workflows_check.py --root . --check
  workflows_parse: 0 violation(s) · 0 worklist · denominator 9
  certain_tests: 0 violation(s) · 0 worklist · denominator 9
  listing_budget: 0 violation(s) · 0 worklist · denominator 37
  listing: 36 skill(s) listed, 1 hidden · 9670 chars of a 10400-char budget (0.013 x 200000 tokens x 4) · fits
python3 tools/upstream/skill_routes.py check --root .            -> skill_routes: 0 violation(s) · 0 worklist · denominator 29
python3 tools/upstream/skill_routes.py selftest-routes --root .  -> skill_routes_selftest: 0 violation(s) · 0 worklist · denominator 34
python3 tools/upstream/skill_surface.py --check                  -> skill_surface: 0 violation(s) · 0 worklist · denominator 21
python3 .claude/hooks/intent_router.py --selftest                -> selftest OK (209 cases, 56 fixture prompts)
python3 tools/station/forge_check.py --selftest                  -> selftest: PASS (20 planted defect(s) + clean + unreadable)
python3 tools/station/telemetry_plan.py --selftest               -> telemetry_plan selftest OK (8 cases)
every tools/**, .claude/hooks/*.py carrying --selftest           -> selftests pass=48 fail=0
planted defect: one-design work/arch/once.md -> forge_check.py output arch -> 1 violation, rc=1 (removed after)
```
