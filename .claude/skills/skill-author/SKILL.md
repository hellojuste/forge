---
name: skill-author
description: Write a new kit skill or station workflow that earns its place: prior-art search, frontmatter under 200 chars, a procedure with a failing test, a router row, selftest prompts, audit green.
---
# skill-author — forge is where the kit's own skills and workflows are built

owner: station forge (purpose: make agents cheaper and better) · checks: `listing_budget`, `workflows_parse`,
`certain_tests`, `paths`, `skill_routes` · see also the account-level `skill-creator` skill for description evals

## Procedure
1. Prior art first: `python3 tools/map/find.py <words>` and `map/SOLUTIONS.md`. If a skill, held upstream skill or
   workflow already does the job, extend or route to it instead (one owner per job).
2. Decide the shape. A skill is a procedure an agent follows inline. A workflow (`.claude/workflows/<name>.js`) is
   orchestration across agents with a GATHER stage and a certain test. A workflow never takes a skill's name
   (`workflows_parse` refuses it); suffix the verb (`trial-run` next to skill `tool-trial`).
3. Skill file `.claude/skills/<name>/SKILL.md`: frontmatter `name` (= directory) and `description` (<= 200 chars:
   what it does + when; it is the per-turn listing cost). Body: owner line, When, numbered Procedure with concrete
   commands and paths, Refusals naming the check that fails and how to plant the defect, Not this skill.
4. If the procedure has a rule, make a check fail on it: add the gate to `tools/station/<tool>.py` with a planted
   case in its `--selftest`, and register the check in `governance/checks.d/station.json` (earned_by, selftest,
   retires, class). A rule written only in prose is never run.
5. Workflow file: copy `.claude/workflows/_template.js`; `export const meta` as a pure literal first; `const
   CERTAIN_TEST` that checks the DELIVERABLE (station form: `python3 tools/station/forge_check.py output <kind>
   {path}`), never an existence check; `const DEFAULT_MODELS` equal to station.json `gov.model_roster`; one
   deliverable and a schema per agent; `args.dry` returns the plan.
6. Route it: a station intent `first_move` in `router/intents.d/station.json` or a `kind: gap` row in
   `router/skills.json`, with selftest prompts written after the keywords are frozen (skill-route-intake step 3-4).
7. Catalogue it in `map/station_catalog.json`, then run `python3 tools/upstream/workflows_check.py --root .`,
   `python3 tools/station_audit.py` (0 red) and `python3 .claude/hooks/intent_router.py --selftest`.

## Refusals (the failing test)
`listing_budget` is red on a description over 200 chars or frontmatter name != directory; `workflows_parse` on an
impure meta, a missing CERTAIN_TEST or a skill-name clash; `certain_tests` on an existence-only or mutating test;
`paths` on a cited path that does not exist; forge gate `roster` on DEFAULT_MODELS drift.
