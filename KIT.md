# KIT — the station file for `main`

owner: kit-root · status: CURRENT · date: 2026-10-16 · supersedes: none · audit: `python3 tools/kit/kit_check.py tree registry`

You are on `main`. This branch is the kit itself: the commons that every station inherits, the decision tree
(`README.md`, `router/kit_tree.json`), the registry and the kit tools. **Do station work in a station worktree**
(`git worktree add ~/stations/<x> station/<x>`), not here. After a plain `git clone` of the kit only `main` is
local and the stations are remote-tracking refs: every kit tool reads them as they are (local `station/<x>`,
`<remote>/station/<x>`, or the temporary hosted names `claude/stable-kit-<x>`), and
`git fetch origin 'refs/heads/station/*:refs/heads/station/*'` makes them local branches when the remote uses
`station/<x>` (hosted: `git worktree add ~/stations/<x> -b station/<x> origin/claude/stable-kit-<x>`). On main you change the commons, the registry and the
kit tools, and then sync the stations.

## How the repo works

| piece | what | tool |
|---|---|---|
| `main` | commons at the same repo-root paths every station uses + tree + registry + `tools/kit/`; tagged `commons-v<n>` at each commons release | `tools/station_audit.py` (MUST checks green on main) |
| `station/<x>` | forked with `git switch -c station/<x> main` (never `--orphan`), then one overlay commit of station-only files | `tools/kit/assemble.py` (build time) |
| sync | `git merge --no-ff main` on a station; a conflict in a GENERATED file is resolved by regenerating it; any other conflict aborts the merge and names the path (a branch-discipline violation) | `python3 tools/kit/sync.py` (`--check` = dry run via `git merge-tree`) |
| bootstrap | bare clone of a big upstream at its 40-hex pin into ONE cache shared by the kit checkout and every station worktree (`$STABLE_KIT_UPSTREAM`, else the main checkout's gitignored `.upstream/<owner~repo>.git`); never checked out in a station | `python3 tools/kit/bootstrap.py <owner~repo>… \| --all \| --station <x> \| --attic`, `--dry-run` (preview, no network), `--bundle-out`, `--from-bundle` |
| runtree | `git worktree add` of a bootstrap pin OUTSIDE the repo at `~/.stable-kit/run/<station>/<repo>@<sha7>`; `--workspace` wires the kit floor hooks into it by absolute path | `python3 tools/kit/runtree.py <owner~repo> [--workspace]`, `--list`, `--remove` |
| repin | path-scoped diff report for a new upstream sha (licence change STOPS; new agent/hook/MCP files; telemetry grep; repurposed check); `--apply` rewrites `registry/sources.json` + the station LOCK row only after green | `python3 tools/kit/repin.py --report <owner~repo> <sha>`, `--apply`, `--check` |
| doctor | report only, always exit 0: git/python/node, station refs (local / remote-tracking only), shared bootstrap-cache coverage per LOCK row, bootstrap-needed list, worktree layout, multi-station-root warning | `python3 tools/kit/doctor.py` |
| skills index | every census SKILL.md -> station -> route; `--check` exits 1 on any unrouted, doubly homed or path-missing row | `python3 tools/kit/skills_index.py --check --from-git .` |
| split | one station into its own repo (branch renamed `main`, remote `kit` back to this repo) — a convenience, not a boundary (ORDER 5) | `bash tools/kit/split.sh station/<x> <dest> [remote-url]` |
| zip | stage a clean copy whose only refs are `main` + `station/<x>` (from any layout, no remotes), `git bundle --all` + verify, zip with `.git`, then unzip-verify by running UNZIP.md steps 2, 3, 7, 8 exactly as written | `python3 tools/kit/make_zip.py --repo <dir> --out stable-kit.zip` |
| consistency | README tree == `router/kit_tree.json` == `map/STATIONS.md` == station refs (any layout); 28 registry rows, 40-hex pins, every repo landed or in the attic, quarantine repos on `station/quarantine` | `python3 tools/kit/kit_check.py tree registry` |

### Changing the commons (the only way)
1. On `main`, in this order: (a) edit the commons file; (b) regenerate what it feeds —
   `python3 tools/gov/gen_manifest.py --write`, `python3 tools/gov/gen_ownership.py --write`,
   `python3 tools/map/map_check.py --write`, `python3 tools/brain.py index`; (c) `python3 tools/station_audit.py`
   (MUST green; before (b) `commons_drift` is red by design); (d) commit by path; (e) tag `commons-v<n+1>`.
   SUPERSEDED 2026-10-16 (REPRODUCE F8: audit-before-regenerate is red and `gen_ownership.py` without `--write`
   only prints): "edit the commons file, run `python3 tools/station_audit.py` (MUST green), regenerate what you
   touched (`python3 tools/gov/gen_manifest.py --write`, `python3 tools/gov/gen_ownership.py`,
   `python3 tools/map/map_check.py --write`, `python3 tools/brain.py index`), commit by path, tag `commons-v<n+1>`."

2. In each station worktree: `python3 tools/kit/sync.py`. A non-GENERATED conflict means a station edited a
   commons file: move that edit to main (or to a station-only fragment) and sync again.

## Precedence (one owner: `governance/rules.json` row `R-precedence`; per station `upstream/PRECEDENCE.json`)

| rank | source | scope | where it lives |
|---|---|---|---|
| 1 | the operator's words (durable as verbatim DEC rows with a locator) | everywhere | `governance/DECISIONS.md`, station `governance/STATION_DECISIONS.md` |
| 2 | **kit floor** (`upstream: NEVER`): deny_destructive, deny_upstream_write, deny_generated_edit, act_gate ask, quarantine_gate ask, company_scope (client-bi), the audit runner and its classes, the router, the registers, amend-never-delete, the closeout line, the denominator rule | everywhere, including inside workspace-mode upstreams | `governance/rules.json`, `.claude/settings.json`, `.claude/hooks/` |
| 3 | station rules (override a commons rule only by a `DEC-<station>-nnnn` naming its rules.json id) | that branch | `.claude/rules/station.md`, `station.json`, station DEC rows |
| 4 | upstream conventions: (i) inside a held tree only the closed SUBTREE vocabulary `[build, code-style, test-runner, commit-format, layout]` listed in its PRECEDENCE row; (ii) `mode: workspace` (career-ops, ai-job-search) inside its run tree | that tree / that workspace | `upstream/PRECEDENCE.json` |
| 5 | commons defaults (lean SHOULD-class lessons: listing budget, tiering, cadence) | everywhere unless rank 3/4 supersedes | `commons/defaults.json` |
| 6 | repertoire method text: method only, never permissions, network, secrets, git or telemetry | method | `repertoire/`, `nc-lane/`, `study/` |

This is how the lean and efficiency lessons travel with every station "unless the repos included have superseding
instructions" (ORDER 1): an included repo supersedes rank 5 inside its subtree or workspace, recorded as an
`adopted:` entry in PRECEDENCE plus a DEC row; it never supersedes rank 2.

## Branch discipline — paths that exist ONLY on station branches (`main_purity` fails main if one appears)

`station.json` · `STATION.md` · `.claude/rules/station.md` · `.env` · `.env.example` · `.mcp.json` ·
`.mcp.local.example.json` · `NOTICE.md` · `upstream/*.json` · lanes `repertoire/` `upstream/` `study/` `nc-lane/` ·
`router/intents.d/station*.json` · `router/skills*.json` · `governance/{checks.d,rules.d}/station.json` ·
`governance/STATION_{DECISIONS,LEDGER,DEFECTS,HISTORY}.md` · `.claude/skills/<gap>/` ·
`.claude/workflows/<station>.js` · `.claude/hooks/station/<hook>.py` · `tools/station/<tool>.py` · `map/station_*.json` ·
`brain/brain.json` · `brain/nodes/*/<station>-*` · `work/` · `engagements/` · `notes/` · `QUARANTINE.md`

Everything else is commons (in `commons/MANIFEST.json`, identical on every branch, edited on main only; a station
whose copy differs fails `commons_drift`) or GENERATED (first 3 lines declare it; both sides regenerate):
`governance/OWNERSHIP.md`, `commons/MANIFEST.json`, `map/SOLUTIONS.md`, `map/usage.json`, `map/atlas.json`,
`map/ATLAS.md`, generated dir READMEs, `brain/INDEX.md`, `repertoire/INDEX.md`, `NOTICE.md`, `SKILLS_INDEX.md`,
`registry/skill_assignment.json`, `registry/skills_index.json`, `map/STATIONS.md`.

## Policy on main (applies to every station)

- **Secrets:** stations carry `.env` names with empty values; your values may be committed on your private copy; no hook blocks it (DEC-core-0003).
- **Telemetry:** `registry/telemetry.json` has one row per tool with telemetry (evidence path, opt-out switch, `verified`). A workflow never starts a tool whose row is `verified: false`; `service-up`, `wiki-gen` and `optimize-loop` enforce it.
- **Hosted MCP:** Reactive Resume (`https://rxresu.me/mcp`, career) and Supabase (`https://mcp.supabase.com/mcp`, venture) stay as shipped in those stations' `.mcp.json` (DEC-core-0004).
- **Local MCP:** servers a station can run itself (Vibe-Trading `agent/mcp_server.py`, Relaticle `/mcp`, others the station builders found) are listed DISABLED in that station's `.mcp.local.example.json`, pointing at the run-tree path; enable one by renaming the file.
- **Quarantine and study lanes:** `registry/quarantine.json` lists every quarantined path; install/run inside one asks first (`quarantine_gate`); AutoHedge's `execute_trade` asks while a signing key is set (`act_gate`).
- **Attic:** `registry/attic.json` (Open-LLM-VTuber, the LibreChat app): `python3 tools/kit/bootstrap.py --attic` fetches them at the pin.

## Registry (`registry/`)

| file | content | maintained by |
|---|---|---|
| `sources.json` | 28 repos: id, owner/repo, url, 40-hex pin, licence, licence file, last commit date | `repin.py --apply` |
| `homes.json` | every repo -> station(s) + how (repertoire, tree, bootstrap, copy_from) or attic | hand, checked by `kit_check.py registry` |
| `licences.json` | licence class per repo + nested licences that govern held subtrees | hand |
| `telemetry.json` | telemetry rows, all `verified: false` until proven | hand + block E merges station rows |
| `attic.json`, `quarantine.json` | attic rows; quarantined paths and their gates | hand |
| `skills_plan.json` | the plan's `skills_assignment` (defaults, exceptions, canonical choices, 360 rows) carried in the kit, with dated `amendments` rows (AMEND-skills-0001: row 17 `.github/skills/custom-fields-development` is a mirror) | hand, by an amendments row; `python3 tools/upstream/skill_routes.py verify --plan registry/skills_plan.json --census <SKILL_CENSUS.yml> --clones <dir>` |
| `skill_assignment.json` + `SKILL_CENSUS.yml` | GENERATED transcription of `skills_plan.json`'s 360 skill rows + the census it was built from; GPL-family and CC-BY-NC rows ship no description prose (NONPERMISSIVE_PROSE_WITHHELD) | `skills_index.py --write-assignment --plan registry/skills_plan.json --census <SKILL_CENSUS.yml>` |
| `skills_index.json` (+ `SKILLS_INDEX.md`) | GENERATED routing state of all 360 rows | `skills_index.py --write --from-git .` |
