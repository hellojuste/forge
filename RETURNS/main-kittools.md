# RETURN — slice main-kittools (branch claude/stable-kit-main)

owner: child main-kittools · status: CURRENT · date: 2026-10-16 · supersedes: none · audit: `python3 tools/station_audit.py` + the selftests listed below

**Status: DONE.** Every finding this slice owned is fixed, except two halves that sit in files another slice owns.
Those are listed under "Handed over" with the call each owner needs to make. Owned paths only: `tools/kit/*`,
`registry/*`, `README.md`, `KIT.md`, `UNZIP.md`, `SKILLS_INDEX.md`. I also regenerated `commons/MANIFEST.json`
and `map/*`, and added one catalog row for the new tool.

## What changed

| commit | what |
|---|---|
| `7d09d2d` | One ref resolver, `_kit.station_refs` / `main_ref`, covering local `station/<x>`, remote-tracking `<remote>/station/<x>` (a plain clone) and hosted `claude/stable-kit-<x>`. It is used by skills_index, kit_check, split.sh, repin, doctor, sync and make_zip. A selftest helper, `_kit.fixture_layouts`, builds all three layouts. Also: a shared bootstrap cache (`_kit.upstream_cache`: `$STABLE_KIT_UPSTREAM`, else the main checkout's `.upstream/` via `--git-common-dir`); `bootstrap --dry-run`; make_zip stages a clean `main` + `station/*` copy with no remotes and verifies by running UNZIP.md steps 2, 3, 7 and 8 exactly as written; UNZIP step 8 now uses `--update-head-ok`; the KIT.md commons order is fixed; the doctor hints are fixed. |
| `c707ede` | `registry/skills_plan.json`: the plan's `skills_assignment`, carried in the kit with an `amendments` row (AMEND-skills-0001, row 17 is a mirror). The census now withholds CC-BY-NC prose as well as GPL-family prose (rule NONPERMISSIVE_PROSE_WITHHELD; the licence comes from `registry/sources.json`). SKILLS_INDEX.md and skills_index.json were regenerated with a repo-relative source. |
| `79ec056` | New `tools/kit/held_modes.py` and `registry/held_modes.json`: modes at the pin vs on the branch, with the policy; `kit_check registry` runs `--check`. The camofox, maxun, evo and openwiki telemetry rows were re-read at their pins, and an AutoHedge (swarms) row was added. |
| last | README/KIT text follows the 2026-10-16 ruling (every canonical skill visible; the router adds precision and is never a gate; the 6-skill cap is retired). This file. |

## Findings owned → disposition

| id | disposition | evidence |
|---|---|---|
| REPRODUCE F2 (plain clone: skills_index 360/360, kit_check --strict, split.sh) | **fixed** | This session's checkout is exactly the hosted plain-clone case: before the fix, `skills_index --check --from-git .` reported 360 violations; after it, 0 / 360. `kit_check tree --strict` passes with 0 violations. `split.sh station/markets` works from `origin/claude/stable-kit-markets`. Selftests cover all three layouts in skills_index, kit_check, split.sh, doctor, sync, make_zip and held_modes. KIT.md has the post-clone line. |
| REPRODUCE F3 (UNZIP step 8 refused) | **fixed** | Step 8 now passes `--update-head-ok`. make_zip verify runs steps 2, 3, 7 and 8 as written. The selftest plants the old step 8 and verify fails. End to end on this repo: the first run, against the old UNZIP.md committed on main, was **caught** by verify ("refusing to fetch into branch main"). After the commit: `unzip OK · step 2 fsck clean · step 3 9 / 9 branches · steps 7-8 restore 9 / 9 local branches` (121,021,087 B). |
| REPRODUCE F4 (per-worktree cache) | **fixed in tools/kit; handed over for upstream_checks** | bootstrap, runtree, doctor and repin use `_kit.upstream_cache`. The selftest bootstraps from the kit root and sees the pin from a linked worktree, then does the reverse; `$STABLE_KIT_UPSTREAM` overrides. `tools/upstream/upstream_checks.py offline_complete` (lines 433-439) still reads `root/.upstream`, and that file belongs to main-commons (see "Handed over"). |
| REPRODUCE F7 (bootstrap --dry-run) | **fixed** | `--dry-run` prints key · url (or bundle) · sha · files_at_pin (from the LOCK rows on the station refs) · cache path · present/absent. It uses no network and writes nothing; the selftest asserts no `.upstream/` is created. |
| REPRODUCE F8 (KIT.md commons order) | **fixed** | The order is now edit → regenerate (`gen_ownership.py --write` included) → audit → commit → tag. The old text is kept under a dated SUPERSEDED line. |
| REPRODUCE F10 a, b (zip remotes, doctor hint) | **fixed** | (a) The zip is built from a staged copy whose only refs are `main` + `station/*` and which has no `[remote]`; the selftest checks this for all layouts. (b) The doctor hint says `--all --dry-run … or --station <x>`. |
| REPRODUCE F10 c (brain card prints purpose twice, LOOP lines cut mid-word) | **deferred → main-commons** | `tools/brain.py` is a commons file I do not own. |
| LEAN F4 (absolute /tmp paths in generated files) | **fixed** | `Source: this repo (git, every station ref: local, remote-tracking or claude/stable-kit-*)`; the BuildSource uses its basename only. The selftest asserts that no tmp path appears in either generated file. Regenerated with the tool. |
| SAFETY 5 (41 lost exec bits) | **fixed as record + documented policy (not restored)** | `held_modes.py --write` against tree-only fetches of all 28 pins gives 41 / 4,508 (client-bi 2, quarantine 20, studio 1, venture 18). That matches the review exactly, and every change is 100755 → 100644. Policy: NOT RESTORED, because nothing in a lane is directly executable and run trees keep upstream modes. `--check` (in `kit_check registry`) fails on any unrecorded 100755 in a lane or any drift. Not done: a per-row `mode_at_pin` in PROVENANCE and a NOTICE line, since `tools/upstream/ingest.py` / `notice.py` and the station files belong to other slices (see "Handed over"). |
| SAFETY 6 (CC BY-NC census excerpts) | **fixed** | NONPERMISSIVE_PROSE_WITHHELD: 42 rows withheld (37 GPL-family + 5 CC-BY-NC). The census `repo_licence` for ARS was unparsed ("check (Copyright …)"), so the licence is taken from `registry/sources.json`. The selftest covers an unparsed licence, the registry licence, and a superseded note that is not doubled. |
| SAFETY 7 (camofox / maxun rows) | **fixed (registry)** | Lines re-read at the pins: camofox `lib/config.js:232`, `reporter.js:478,640,642`; maxun `analytics.ts:37`, `ENVEXAMPLE:45`, `docs/generate-env.sh:80`. The old values are kept under `superseded`. The quarantine `.env`/`.env.example` NAME `CAMOFOX_CRASH_REPORT_ENABLED` and the QUARANTINE.md sentences are station files (see "Handed over"). |
| SAFETY 8 (evo / openwiki rows) | **fixed** | evo `telemetry.py:102-112`, candidate env `{EVO_TELEMETRY:0, DO_NOT_TRACK:1}`; openwiki `gates.ts:28-32,84-90`, `senders.ts:136`. Both re-read at the pins; `verified` stays false. |
| SAFETY 9 (AutoHedge unpinned swarms) | **fixed (registry)** | New row `autohedge (via swarms)`, verified false, PLAUSIBLE. `requirements.txt:1` and `pyproject.toml:30` were re-read at the pin. The startup-note §7 line belongs to the markets station. |
| Row 17 `.github/skills/custom-fields-development` | **fixed** | The pinned blobs differ only by the final newline (8,747 B vs 8,746 B; `diff` shows `\ No newline at end of file`). `skill_routes.py verify` restricted to repo 17 at the pin: design plan **1 violation** (kind plan=variant, recomputed=mirror); `registry/skills_plan.json` **0 / 31**. `registry/skill_assignment.json` now has kind mirror, route_to the `.claude/` canonical, no held_path. |

## Handed over (owner must act; re-test trigger in brackets)

1. **venture station child:** in `router/skills.json`, the row for `17:.github/skills/custom-fields-development/SKILL.md` must become `kind: mirror`, `route_to: 17:.claude/skills/custom-fields-development/SKILL.md`, with no keywords of its own, to match the registry. [`python3 tools/upstream/skill_routes.py check` on venture after its next sync]
2. **main-commons:** `tools/upstream/upstream_checks.py offline_complete` should resolve the cache with `tools/kit/_kit.upstream_cache(root)` (or the same `--git-common-dir` rule) rather than `root/.upstream`. Otherwise it will report a pin bootstrapped from the kit root as absent in a station worktree. [`offline_complete` in a `git worktree add` station after `bootstrap.py --station <x>` from the kit root]
3. **main-commons:** `tools/upstream/ingest.py` could record `mode_at_pin` per PROVENANCE row, and `notice.py` could add the line "N file modes normalised 100755→100644 (registry/held_modes.json)". This is optional, since the registry record and its check already exist. Also REPRODUCE F10 c in `tools/brain.py`. [next ingest]
4. **quarantine / markets station children:** add the NAME `CAMOFOX_CRASH_REPORT_ENABLED` to the quarantine `.env`/`.env.example`, with one QUARANTINE.md sentence each for camofox and maxun (SAFETY 7). Add the swarms line to `study/AUTOHEDGE_STARTUP_NOTE.md` §7 (SAFETY 9). [next station pass]
5. **all station children:** `sync.py` brings in the new `registry/SKILL_CENSUS.yml` (more rows withheld) and `registry/skills_plan.json`. Stations running `licence_filter` gain from the withheld rows; no conflict is expected (main-owned generated files take main's side).

## Final tails (re-run 2026-10-16 on `claude/stable-kit-main`, this checkout = hosted plain clone)

```
tools/kit/skills_index.py --selftest: selftest OK
tools/kit/kit_check.py --selftest: selftest OK
tools/kit/bootstrap.py --selftest: selftest OK
tools/kit/doctor.py --selftest: selftest OK
tools/kit/runtree.py --selftest: selftest OK
tools/kit/repin.py --selftest: selftest OK
tools/kit/sync.py --selftest: selftest OK
tools/kit/make_zip.py --selftest: selftest OK
tools/kit/held_modes.py --selftest: selftest OK
tools/kit/assemble.py --selftest: selftest OK (fixture: 3 branches, station map seeded before every audit, generated-conflict regenerated, commons-conflict aborted, 5 refusals, cwd untouched)
tools/kit/split.sh --selftest: selftest OK
skills_index: 0 violation(s) · 0 worklist · denominator 360
kit_tree: 0 violation(s) · 0 worklist · denominator 8
kit_registry: 0 violation(s) · 0 worklist · denominator 28
  sources 28 / 28 · attic 2 · quarantine rows 4 · telemetry rows 11 (verified 0) · skill rows 360 / 360
  held modes 41 / 4508 changed, recorded
held_modes: 0 violation(s) · 0 worklist · denominator 4508
station_audit: 0 red · 35/35 clean · worklists 27 · 4.2s
make_zip verify: unzip OK · UNZIP step 2 fsck clean · step 3 9 / 9 branches · steps 7-8 restore 9 / 9 local branches
```

closeout: main-kittools · 14 finding rows owned (REPRODUCE F2, F3, F4, F7, F8, F10 a/b, F10 c; LEAN F4; SAFETY 5-9; row 17) → 13 fixed, 1 deferred (F10 c, commons-owned) · 4 handovers named with re-test triggers · audit 35/35 MUST clean · 11 / 11 kit selftests OK
