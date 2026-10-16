# ASSEMBLY_NOTES — what the trial assemblies of fix round 2 hit, and who owns each stop

owner: kit-root · status: CURRENT · date: 2026-10-16 · supersedes: none · audit: `python3 tools/kit/assemble.py --build <build> --out <empty dir> --plan <kit_plan.yml>`

Fix round 2 (contract fix2-root) ran `tools/kit/assemble.py` for real against the build dir, more than once,
into fresh `mktemp -d` output dirs. It never wrote into the build dir except build/root (this slice). A stop
owned by root was fixed here. A stop owned by commons or by a station is recorded below with the file, the
check and the evidence, and was NOT fixed here. To see past those stops, a separate trial ran on a throwaway
COPY of the build dir with stand-ins. Each stand-in is labelled below. None of them ships.

The paths that exist only on a station branch are written here in plain text, not as backticked claims, so
the `paths` check on main and on every other station has nothing to resolve.

## Root-owned stops: fixed in build/root

| # | where it bit | check / evidence | fix (file) | regression test |
|---|---|---|---|---|
| R1 | venture, on an assembled copy of commons + root + venture | `licence_filter` (MUST): registry/SKILL_CENSUS.yml carried a line of copyleft upstream relaticle filament-development SKILL.md: "pages, schemas, forms, tables, actions, infolists, widgets, ..." | rule COPYLEFT_PROSE_WITHHELD in `tools/kit/skills_index.py`. `--write-assignment` ships the census with `description: ''` plus a `description_withheld` key (licence and the sha256 of the withheld text) for every GPL-family row. 37 rows are affected (36 AGPL-3.0, 1 GPL-3.0). Ids, paths, shas, licences, desc_chars and every other key are kept. The census still has 360 rows. It is idempotent, and it also applies when `--census` is the shipped file itself (assemble step 3) | the `skills_index.py --selftest` fixture plants an AGPL row with a folded description. `--check` now also fails on a copyleft row that carries prose |
| R2 | the build dir itself | build/root/map/STATIONS.md was found holding a 3-line fixture table ("\| branch \|") after the kit-root selftests ran from build/root. `kit_check.py tree` then said "map/STATIONS.md stations [] != kit_tree [...]" | `tools/kit/assemble.py`: the seed loader imports a station-map generator only if it defines `render(`, and the selftest's fixture generator now keeps its writes under `if __name__ == "__main__":`. Before this, importing the fixture for its render() ran its module body, which wrote map/STATIONS.md into the caller's cwd. The seed was re-written with `assemble.py --seed-station-map` | `assemble.py --selftest` now runs from an empty cwd and asserts that the cwd is still empty. With the guard removed, it fails with "selftest wrote into its cwd: ['map']" |
| R3 | station/markets, step 4 | `lane_tracked` (MUST, markets): 4 violations. The held AutoHedge tree's own .gitignore (`.env`, `experimental/`) dropped 4 overlay files from the commit: the study lane's .env slot and experimental/btc_agent.py, crypto_agent_wrapper.py, market_making.py. The career station's held hiring-agent .gitignore (`resume/*.pdf`) drops resume/sample.pdf the same way | `_kit.force_stage_nested_ignored()` plus `Assembler.force_nested()` in `tools/kit/assemble.py`. Every file copied from the build in steps 3 and 4 that a NESTED .gitignore drops is added with `git add -f`. A file that the kit's root .gitignore (runtime dirs), info/exclude or a global excludes file drops stays out. Negated `!pattern` matches are skipped. The assembly log prints each force-staged path. ORDER 5 allows the .env slot | the `assemble.py --selftest` fixture holds a nested .gitignore that drops .env and experimental/, plus a root-ignored .cache/ file. With the fix removed, it fails with "station/alpha lacks repertoire/o~r/.env" |
| R4 | main, step 3 (cosmetic) | in the pre-routing state, `skills_index.py --write` printed "360 violation(s)" with exit 0 | headline: VIOLATION rows and census prose rows are violations. PENDING rows (no station source yet) are the worklist. `--check` still exits 1 on PENDING | selftest asserts "2 violation(s) · 3 worklist" on the planted census |

## Stops owned by commons or a station: recorded, not fixed here

| # | owner | where | check | evidence | status when this file was written |
|---|---|---|---|---|---|
| C1 | commons (fix2-commons 1) | main, step 3 | `catalog` (MUST) | "UNCATALOGUED tools/kit/_kit.py: matched by scope, no map/catalog.json entry". Assembly stopped at step 3 | FIXED by commons during this round. The second trial passed step 3 and tagged commons-v1 |
| C2 | commons: `.claude/hooks/intent_router.py` `_load_cases` | station/quarantine, step 4 (the first station in tree order); it would hit every station | `hooks_selftest` (MUST) | all 8 station `router/skills.selftest.json` files use the `{"positive": [{prompt, expect}], "negative": [prompt]}` shape that commons' own `tools/upstream/skill_routes.py` accepts. The router's tolerant reader does not, so it reads the KEYS "positive" and "negative" as two prompts. Result: "skills 'negative': want [...10 prompts...] in top-2, got []" | CLEARED by 06:20Z on the STATION side: the station fixer rewrote the skills.selftest.json files into the `{"cases": [...]}` shape that the router reads. Quarantine then passed step 4 in the final real trial. The commons router's `_load_cases` still does not read the positive/negative shape that `skill_routes.py` documents (two readers in commons, two shapes), so a new station file in that shape would go red again: commons should accept both. Stand-in S1 was used for the throwaway trial |
| V1 | station venture | station/venture, step 4 | `router_targets` (MUST) | 7 first_move workflows named in the venture router intents.d/station.json are absent: idea-to-decision, prd, mvp-scaffold, launch-plan, service-up, billing-dryrun, weekly-ops (.claude/workflows/<name>.js) | CLEARED by 06:20Z: `--stations venture` on the real build passed station_audit. Stand-in S2 was used for the throwaway trial |
| V2 | station venture (with fix2-stations 3) | station/venture, step 4 | `hooks_selftest` (MUST) | venture skills.selftest positives "read the sdk-bundled full realtime guide" and "read the sdk-bundled full cost guide" expect the trigger-sdk variant, but the top 2 are the cli-v3 rows | CLEARED by 06:20Z (same venture run). Stand-in S3 was used for the throwaway trial |
| V3 | station venture / commons (fix2-commons 5: custom-fields variant hashing) | station/venture, step 4 | `hooks_selftest` (MUST) | "copilot skill for custom fields": wants 17:.github/skills/custom-fields-development/SKILL.md, gets the .claude copy | CLEARED by 06:20Z (same venture run). Stand-in S3 was used for the throwaway trial |
| B1 | station client-bi (fix2-stations 2: erpnext scripts/ ingest) | station/client-bi, step 4 (the second station in tree order) | `upstream` (MUST, `tools/map/upstream_check.py`) | "EDITED frappe~erpnext: git tree of upstream/frappe~erpnext is 5dcd428cc01c, pinned e3551cd38f18 (a station edit inside a held tree; after a deliberate re-ingest re-pin with python3 tools/map/upstream_check.py --pin-trees --write)". The ingest updated LOCK/PROVENANCE at 06:10Z, but the station's tree pin in map/station_upstream.json was not re-pinned | OPEN at 06:20Z. CLEARED by the final real trial (about 06:27Z): client-bi passed step 4 once the station fixer had re-pinned |

## Stand-ins used only in the throwaway trial (never shipped)

- S1: `_load_cases` in the copy's commons intent_router.py also accepts the positive/negative shape.
- Root tools checked for the R3 class: `repin.py` and `bootstrap.py` call `stage_paths` only inside their selftest fixtures (fake remotes). `sync.py` merges main and never copies lane files. So no real root path stages a held tree from a copy apart from `assemble.py`, which now force-stages.
- S2: 7 copies of commons `.claude/workflows/_template.js` (renamed) placed in the copy's venture overlay, plus 7 catalog entries in its map/station_catalog.json.
- S3: in the copy's venture skills.selftest.json, every positive whose prompt contains "sdk-bundled" was removed (the two named in V2 failed first), plus the custom-fields one from V3. The station fixer has since rewritten that file into the `{"cases": [...]}` shape, which still holds 5 sdk-bundled prompts and the custom-fields prompt. The final real trial shows whether they pass now.

With S1-S3 the trial ran all six steps and exited 0. Every station passed station_audit as MUST-clean at step 4.
Step 5 merged every station with sync.py. Step 6 ended with "skills_index: 0 violation(s) · 0 worklist ·
denominator 360", "branches: 9 (main + 8 stations), fsck clean, every station descends from main" and
"assemble: OK (9 branches)". Force-staged files: markets 4, career 1.

## Re-run

The final real trial (no stand-ins, the build dir as it stood after the commons and station fixers' changes)
ran all six steps and exited 0. Step 6 printed "skills_index: 0 violation(s) · 0 worklist · denominator 360",
then "branches: 9 (main + 8 stations), fsck clean, every station descends from main", then
"assemble: OK (9 branches)". Force-staged files: markets 4, career 1. Reproduce it with
`python3 tools/kit/assemble.py --build <build> --out $(mktemp -d)/stable-kit --plan <_design>/kit_plan.yml`.
It stops at the first station whose audit is red and leaves the repo in place for inspection.
