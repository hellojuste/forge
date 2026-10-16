# REASSIGN — station forge (proposals only)

owner: intent-forge (block C, INTENT-STUDY) · status: PROPOSAL · date: 2026-10-16 · supersedes: none · audit: `python3 tools/upstream/skill_routes.py check --station forge --root .` and `selftest-routes --root .`

Nothing here has moved a file. Block E's integrator decides; until then `kit_plan.yml -> skills_assignment` (transcribed in
`registry/skill_assignment.json`) stays the one source of truth for every home below.

Denominator for this pass: 29 census rows homed in forge (canonical 21, fixture 2, mirror 6), 0 held copies.
All 29 read at depth `headings` (name + description + every `#`/`##` heading + first 15 body lines).
Selftest: 21/21 positive prompts route to their row at rank 1 (top-2 required), 10/10 negatives route to nothing,
through the commons matcher (`commons/.claude/hooks/intent_router.py` `match_skills`).

## 1 · Reassignment proposals

| # | census id | current home | proposed | reason (one line) | prompt that showed it |
|---|---|---|---|---|---|
| R1 | `3:pm-ai-shipping/skills/shipping-artifacts/SKILL.md` | forge | forge (keep) **+ held copy in venture** (`copy_of: forge`) | The recorded exception reason is "review agent-built code"; this skill is not a review, it is the doc set written while BUILDING a product, which is venture's noun (build and run the side-business). A venture session asking for launch docs never reaches forge's router. | `write the shipping documentation for this vibe-coded app before launch` |
| R2 | `3:pm-ai-shipping/skills/intended-vs-implemented/SKILL.md` | forge | forge (keep); **no move** | Its method needs the shipping-artifacts docs to exist first (its Purpose section points to shipping-artifacts for that). If R1 is adopted as a copy, both stay homed here and the audit stays a forge job; if R1 were adopted as a MOVE instead, this row must follow it to venture so the pair is never split. | `compare what the permissions doc intended with what is implemented` |
| R3 | `20:skills/mermaid-diagrams/SKILL.md` | forge | forge (keep) **+ held copy in research** | Research owns "repo-stable mapping"; a mapping deliverable with sequence / ER / state diagrams needs the same syntax-safety rules, and research's router cannot see a forge row. Generic diagram method, no openwiki runtime needed. | `add a mermaid flowchart for the login sequence` (asked on a research branch would fall through to nothing) |

Rows judged correctly placed, with a note instead of a move (no other station would use them):

| census id | note |
|---|---|
| `18:skills/codex-coding-plugin/SKILL.md` | Repo-internal to ProjectAtlas (keeps its own plugin manifests and caches on one release). Useful only when patching ProjectAtlas itself; keep routed, low priority. |
| `20:skills/write-connector/SKILL.md` | Repo-internal to openwiki (adds a built-in TypeScript connector to its source tree). Keep. |
| `21:.agents/skills/rea-changelog-update/SKILL.md` | Repo-internal to REA, but the method (inventory pinned history before prose, credit contributors, release-please sync) transfers to any release-please repo. Keep. |
| `21:.agents/skills/rea-tool-design/SKILL.md` | A 956-byte pointer into REA's own docs; meaningless without the REA tree. Keep. |
| `21:.agents/skills/rea-ci-tests-audit/SKILL.md` | REA-flavoured, method is generic (executed baseline, prove the false pass, cost without losing the gate). See gap G3. |
| `19:scripts/rlm_eval/baseline_SKILL.md`, `25:e2e/fixtures/deployment-skills/e2e-deployment-skill/SKILL.md` | Fixtures: keywords are `fixture-*` tokens only, so no ordinary prompt can reach them. |

## 2 · Observed routing noise (recorded, keywords NOT changed)

Probe prompts outside the selftest showed generic keywords pulling non-evo prompts into evo rows. The keyword lists were
frozen before the prompts were written and are left as they are; this is the evidence for a later narrowing decision.

| probe prompt | routed to | cause |
|---|---|---|
| `write a report on the quarter` | evo `report` | bare `report` keyword |
| `ship it` | evo `ship` | bare `ship` keyword |
| `set up the backend` | evo `infra-setup` | bare `backend` keyword |
| `review the architecture of this service` | improve-codebase-architecture, code-review | expected and wanted |

Mitigation already in place: the skill tier is a FALL-THROUGH, it prints only when no station or commons intent fires,
and forge's station intents own `evo`, `optimize`, `architecture`, `projectatlas`, `openwiki`, `rea`. Proposal N1:
if the integrator sees these misfires in live sessions, narrow `report`, `ship`, `backend` out of the evo rows (the rows
keep `overnight`/`scatter`, `winner`/`mergeable`, `modal`/`e2b`/`daytona` plus the `evo:report`/`evo:ship` phrases) and
re-run `selftest-routes`.

## 3 · Gap skills this station still needs

Baseline already shipped in `.claude/skills/`: `evo-guard`, `kit-maintain`, `re-legal-gate`, `telemetry-audit`,
`tool-trial`. The gaps below are not covered by any of those five nor by a held upstream skill.

### G1 · `design-it-twice`
- Job: before any architecture recommendation, draft two (or three) radically different interfaces for the same module, each with its usage example, and compare them on depth, leverage and locality.
- Why a gap: STATION.md names "architecture review (design it twice)" and the `arch-review` workflow cites it, but the held LibreChat set carries only `codebase-design` and `improve-codebase-architecture`; nothing in `repertoire/` holds the design-twice step.
- Output: `work/arch/<slug>.md` with both designs, the comparison table and the pick with its reason; keywords `twice`, `alternatives`, `interface`.

### G2 · `noise-floor`
- Job: run the frozen benchmark K >= 5 times on the unchanged baseline and record the spread (min, max, sd) before an evo loop or a tool trial claims any gain.
- Why a gap: `evo-guard` freezes a holdout and `tool-trial` fixes N >= 5 tasks, but neither measures run-to-run variance of the score itself; a gain smaller than the noise floor is not a gain (every numerator carries its denominator).
- Output: a `noise_floor` line (K, spread, seed policy) prepended to `work/optimize/<slug>.md` or `work/trials/<tool>.md`; evo-guard and tool-trial refuse a verdict without it.

### G3 · `ci-suite-audit` (station-neutral)
- Job: the REA CI audit method without REA's paths: pin the executed baseline SHA, prove each suspected false pass with a planted defect, measure cost per job, and cut only what keeps the gate.
- Why a gap: the held method is written against REA's own docs and commands; the kit's own `tools/` checks (and any upstream under trial) need the same audit, and lettuce's planted-defect selftest discipline (admission rule) is the matching house rule to bring along.
- Output: `work/trials/ci-<repo>.md` with a table of check -> catches what -> planted defect -> cost; never pushes or edits workflows on its own.

### G4 · `skill-route-intake`
- Job: when `upstream-intake` lands a new repo, write its `router/skills.json` rows the way this pass did: dump name/description/headings, freeze 3–8 keywords per canonical row, THEN write one positive and the negatives, run `selftest-routes`; mirrors route to canonicals, fixtures get `fixture-*` tokens only.
- Why a gap: the `upstream-intake` workflow lists router rows as an output but no skill carries the freeze-before-prompts discipline (LL-19) or the fixture/mirror rules; without it a later intake will fit keywords to prompts.
- Output: the station's `router/skills.json` + `router/skills.selftest.json` rows for the new upstream, `repertoire/INDEX.md` regenerated, check exit 0.

## Fix round 2 — APPLIED (2026-10-16, contract fix2-stations)

Station-local routing changes made by the fix-round-2 station fixer. Every keyword change is also written into the row's `notes`; for those rows the block-C claim "keywords frozen before the prompts were written" (LL-19) no longer holds, because the change was made after a probe prompt showed the miss. Proof: `python3 tools/upstream/skill_routes.py check` and `selftest-routes` (0 violations) and `python3 .claude/hooks/intent_router.py --selftest` (OK) in an assembled copy.

- `router/skills.selftest.json` reshaped from `{positive, negative}` to one `cases` list (`expect: null` = negative). The commons hook's `_load_cases` read the old shape as a `{prompt: expect}` map, so `.claude/hooks/intent_router.py --selftest` failed two pseudo-cases ('positive', 'negative') and `hooks_selftest` was red on every assembled branch; `skill_routes.py selftest-routes` reads both shapes. No prompt or expectation changed in the reshape.
- Section 2 / N1 (generic words pull non-evo prompts into evo rows): bare `report` dropped from evo `report`, bare `ship` from evo `ship`, bare `backend` from evo `infra-setup` (each keeps >= 5 keywords and its `evo:` phrase). New negatives: "write a report on the quarter", "ship it", "set up the backend" route to no skill row; the three evo positives still land.

## DEFERRED TO EQUIP

Not applied here: each needs a cross-station copy or move, a gap skill, or a commons/root change. The equip block decides.

- R1 (held copy of `shipping-artifacts` in venture), R3 (held copy of `mermaid-diagrams` in research): cross-station copies.
- R2: follows R1 only if R1 becomes a move.
- Gap skills G1 `design-it-twice`, G2 `noise-floor`, G3 `ci-suite-audit`, G4 `skill-route-intake`.

## EQUIP DECISIONS (equip-forge, 2026-10-16)

| item | decision | where / why |
|---|---|---|
| G1 `design-it-twice` | **built** | `.claude/skills/design-it-twice/SKILL.md`; enforced by forge gate `arch`; used by workflow `arch-review`; routed by the `arch` intent |
| G2 `noise-floor` | **built** | `.claude/skills/noise-floor/SKILL.md`; forge gate `noise` (K >= 5, spread, gain inside spread never promoted); stage `Noise` of `trial-run`, `Freeze` of `optimize-loop`; intent `noise` |
| G3 `ci-suite-audit` | **built** | `.claude/skills/ci-suite-audit/SKILL.md`; intent `ci-audit` (gather `station_audit.py -k admission`) |
| G4 `skill-route-intake` | **built** | `.claude/skills/skill-route-intake/SKILL.md`; stage `Route` of `intake-run` |
| CRITIC purpose gap: skill-building | **built** | `.claude/skills/skill-author/SKILL.md`; intent `skill-build` |
| CRITIC F11 (telemetry verify path) | **built** | `tools/station/telemetry_plan.py` (`all`, `show`, `gate`, selftest 8); telemetry-audit step 0 |
| R1 copy `shipping-artifacts` to venture | **proposal, not done** | cross-station copy; the venture owner ingests it from the phuryn/pm-skills clone at the forge pin with `--copy-of forge` |
| R2 | **no change** | follows R1 only if R1 became a move; it stays a copy proposal |
| R3 copy `mermaid-diagrams` to research | **proposal, not done** | cross-station copy; the research owner decides |
| N1 (narrow `report`/`ship`/`backend`) | **already applied** in fix round 2 (above) | — |
| Router misses seen while writing equip selftests | **recorded** | `skip the ci audit` routed to ci-audit: `skip` is not a commons negator (`NEGATORS_DEFAULT`), proposed to main; `measure the noise floor of the benchmark` and `draft a new workflow for the repin job` tied with `trial`/`repin`, resolved with row `claims` (`noise floor`; `new skill`/`new workflow`/`write a skill`/`author a skill`), keywords unchanged |
