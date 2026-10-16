# RETURNS — station forge · forge-setup

owner: child session for claude/stable-kit-forge (parent PRIME session_01GbdVhRTvKX1mxo9qitPKER) · status: DONE (two items need main, one needs the operator's Windows run) ·
date: 2026-10-16 · branch: claude/stable-kit-forge · main merged (`tools/kit/sync.py`: already up to date at 097c376)

**Order (verbatim):** "forge — one-step setup for rea, evo, openwiki and ProjectAtlas"

**Status.**
- One command now sets up each tool: `python3 tools/station/setup_tool.py <rea|evo|openwiki|projectatlas|--all> [--dry-run] [--remove]`.
- Each tool was installed for real at its pin in this container, passed its smoke test, and printed `ready` on a second run.
- Six workflows now refuse with that one command when their tool is not ready.
- The registry flips are not done here: `registry/telemetry.json` and `README.md` are commons (`commons_drift` hashes them against main), so both land as proposals for main.

## What changed (commits since 3caddd3)

| commit | what |
|---|---|
| `a105d9b` | `tools/station/setup_tool.py` (selftest: 11 cases); `.claude/workflows/setup.js`; router intent `setup` (15 frozen tool-qualified keywords plus claims) with 6 selftest prompts; six workflows wired to their tools; `station.json` irreversible_acts: `rea setup` (before, only `rea-agents setup` matched) and `projectatlas init`; map catalog, tag `tool-setup`, regenerated maps |
| `a67f3ba` | `work/telemetry/setup-findings.md` (findings plus exact registry JSON for main); `telemetry_plan.py` status commands; STATION.md "Set up a tool"; the old proposal keeps its words under a SUPERSEDED line |
| (this commit) | Windows wrapper shim fix (6c), `DEF-forge-0001`, this file |

## What each tool needs on Windows 11 + Git Bash

`setup_tool.py` prints these lines itself when something is missing (the selftest checks the exact text).

| tool @ pin | route `setup_tool.py` takes | needs | if missing, it prints |
|---|---|---|---|
| rea @ 1bd5c5c (rea-agents 6.5.0) | `npm install --prefix <tree>/.kit-tool rea-agents@6.5.0` (README.md:116, the npm package at the pin's package.json version) | node in `^22.19 \|\| ^24.11 \|\| >=26` (engines, package.json:45); node 26 is fine | `winget install --id OpenJS.NodeJS -e` |
| evo @ c70c04b (evo-hq-cli 0.8.0) | `uv tool install evo-hq-cli==0.8.0` with `UV_TOOL_DIR`/`UV_TOOL_BIN_DIR` inside the run tree; when uv is absent, `python -m venv` + `pip install evo-hq-cli==0.8.0` | python >= 3.10; uv OR pip | `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 \| iex"` (or `winget install --id astral-sh.uv -e`); `py -3.12 -m ensurepip --upgrade` |
| openwiki @ 7c469e5 (openwiki 0.7.2) | `npm install --prefix <tree>/.kit-tool openwiki@0.7.2` (README.md:43,99). There is no Python package at the pin: `openwiki/` holds wiki pages | node >= 22.22.0 (package.json:7-8) | the node line above (an older node gets `node X found, ... needs >=22.22.0`) |
| ProjectAtlas @ bed8ba3 (0.5.0-rc3) | `cargo install --locked --path crates/projectatlas-cli --root <tree>/.kit-tool` from the run tree, i.e. the exact pin (README.md:50 uses `--git --tag`; `project-atlas` is not a crates.io crate). Otherwise the pin's own release zip, checked against `SHA256SUMS` | cargo (rustup reads rust-toolchain.toml and fetches 1.98.0 itself) plus the MSVC linker | `winget install --id Rustlang.Rustup -e && rustup default stable` + `winget install --id Microsoft.VisualStudio.2022.BuildTools -e --override "--add Microsoft.VisualStudio.Workload.VCTools --includeRecommended --passive"` |

ProjectAtlas has no prebuilt binary for the pin. bed8ba3 is not tagged: tag `v0.5.0-rc3` is 7 commits later (`git rev-list --count bed8ba3..5c955b1`). The release route therefore refuses and prints the rustup line, naming v0.5.0-rc3 as the repin that would enable a binary. The route itself is real and tested: when a tag points at the pin it downloads `projectatlas-<tag>-x86_64-pc-windows-msvc.zip` (release.yml:473), checks it against `SHA256SUMS`, and unpacks the binary.

**Where it lives.** `~/.stable-kit/run/forge/<repo>@<sha7>/.kit-tool/` (or `$STABLE_KIT_RUN`).
- The wrapper is `kit-bin/<cli>`: run it as `bash .../kit-bin/evo --help`, or add `kit-bin` to PATH. It is named after the CLI so act_gate's patterns still match through it (selftest case 7).
- It exports the telemetry opt-outs AFTER reading the key names from the station `.env`, so `.env` cannot switch telemetry back on.
- Key values are never printed and never copied out of `.env`.

**Never run by setup:**
- `rea setup|update|analyze-*`
- `evo install|ship|telemetry on|off`
- `openwiki integrations|auth|ingest`
- `projectatlas init` (it writes MCP configs; arch-review and intake-run use `scan` on a throwaway clone)

## Telemetry findings per tool (full table and JSON rows: `work/telemetry/setup-findings.md`)

| tool | sends? | opt-out the wrapper sets | status run here → output |
|---|---|---|---|
| evo | yes: telemetry.evo-hq.com, on by default, plus a daily PyPI GET | `EVO_TELEMETRY=0`, `DO_NOT_TRACK=1`, `EVO_SKIP_VERSION_CHECK=1`, `EVO_HOME` in the tree with `telemetry.json {"enabled": false}` | `evo telemetry status --json` → `"enabled": false, "source": "env", "install_id": null`. With the env unset → `"source": "user"`. Both switches hold on their own. |
| openwiki | yes: PostHog us.i.posthog.com, on non-dry init/update; CI is NOT an opt-out | `OPENWIKI_TELEMETRY_DISABLED=1`, `DO_NOT_TRACK=1`, `LANGCHAIN_TRACING_V2=false`, `OPENWIKI_CONFIG_DIR` in the tree | installed `dist/telemetry/senders.js` `recordRun` run offline → `{"disabled": true, "sent": false}`, no install-id |
| ProjectAtlas | no network: local token accounting in SQLite; 0 HTTP crates in the default build | `PROJECTATLAS_NO_TELEMETRY=1` (runtime.rs:3608-3610) | `projectatlas runtime-info` → version 0.5.0-rc3, no endpoint printed |
| rea | no sender found (src/ + 158 installed packages) | `DO_NOT_TRACK=1` (harmless) | `rea --version` → 6.5.0 |

Proposed for main:
- flip evo, openwiki and ProjectAtlas to `verified: true` with the `verified_by_run` above;
- add a rea row;
- set `denominator` to 12.

The runs were made by this session in a Linux container, not by the operator. The registry `_doc` asks for the operator's run, so main chooses (a) accept these runs or (b) have the operator re-run one line per tool. Until main lands the rows, `optimize-loop` and `wiki-gen` still stop at `telemetry_plan.py gate` by design.

## README tools table (commons: proposal for main, not edited here)

Under "Upstream clones (bootstrap)", after the `runtree.py` line, add:
```
python3 tools/station/setup_tool.py --all                     # on forge: rea, evo, openwiki, ProjectAtlas installed at the pin in run trees, telemetry off
```
In the KIT_TREE forge row (owned by router/kit_tree.json), add `setup` to the workflow list. `kit_check.py tree` keeps the two equal.

## Findings → disposition

| finding | disposition |
|---|---|
| A wrapper named `run.sh` would have let `rea analyze-*` / `evo ship` through the wrapper unasked | **fixed**: the wrapper is `kit-bin/<cli>`; selftest case 7 runs station.json's patterns against wrapper commands |
| `rea setup` (bin `rea`) was not asked; only `rea-agents setup` was | **fixed** in station.json (`\brea(-agents)?(@\S+)?\s+(setup\|update)\b`); act_gate selftest 24 OK |
| `projectatlas init` writes MCP configs into the repo it runs in, and no gate asked | **fixed**: added to irreversible_acts; arch-review and intake-run index a `git clone --local` copy with `scan` |
| The order said `cargo install project-atlas`; no such crates.io crate, and the README route is `--git --tag v0.4.5`, not the pin | build the pin's own crate with `--path --locked` |
| The order said openwiki installs "via its Python/npm" | npm only: no Python package at the pin |
| Registry and README are commons | proposals above; `commons_drift` stays green |
| Windows branches untested on a real host | **filed** as `DEF-forge-0001` (trigger: `setup_tool.py --all` twice on the operator's Windows) |
| SessionStart/PostToolUse HANDOFF hook (context ≥ 200k) | not acted on: the order ends this session after RETURNS; every milestone was committed and pushed by path, so a successor would start from the pushed branch |

## Test tails (fresh `git clone` of the branch at a67f3ba; setup_tool re-run after this commit's fix)

```
python3 tools/station_audit.py                       -> station_audit: 0 red · 38/38 clean · worklists 35 · 4.2s
python3 tools/upstream/workflows_check.py --root . --check
  workflows_parse: 0 violation(s) · 0 worklist · denominator 10
  certain_tests: 0 violation(s) · 0 worklist · denominator 10
  listing_budget: 0 violation(s) · 0 worklist · denominator 37
python3 tools/station/setup_tool.py --selftest      -> setup_tool selftest OK (11 cases: missing prerequisite, old node, full setup, second run ready, dry-run, remove, wrong version, release binary + bad checksum, Windows wrapper, act_gate through the wrapper, readers)
  planted: version_matches -> always True  => selftest FAILS (caught); node install line changed => FAILS (caught)
python3 tools/station/forge_check.py --selftest     -> selftest: PASS (20 planted defect(s) + clean + unreadable)
python3 tools/station/forge_check.py check          -> forge_gates: 0 violation(s) · 0 worklist · denominator 19
python3 tools/station/telemetry_plan.py --selftest  -> telemetry_plan selftest OK (8 cases)
python3 .claude/hooks/intent_router.py --selftest   -> selftest OK (215 cases, 56 fixture prompts)
python3 .claude/hooks/act_gate.py --selftest        -> act_gate selftest OK (24 cases)
python3 tools/upstream/skill_routes.py check --root .   -> skill_routes: 0 violation(s) · 0 worklist · denominator 29
python3 tools/upstream/skill_surface.py --check     -> skill_surface: 0 violation(s) · 0 worklist · denominator 21
every tools/**, .claude/hooks/*.py carrying --selftest -> pass=49 fail=0 (upstream_checks.py needs its `all` positional)
workflow mock (tool not ready, gather rows exit 1): trial-run, optimize-loop, reverse, arch-review, intake-run -> refused naming
  `python3 tools/station/setup_tool.py <tool>` after 1 agent; wiki-gen -> status refused-not-ready record (4 agents)
real runs, Linux container (node 22.22.0, uv 0.11.32, cargo 1.97 via rustup), STABLE_KIT_RUN=<scratchpad>:
  rea 14s · evo 3s (uv) / 6s (pip fallback, uv hidden) · openwiki 25s · projectatlas: cargo build (background) -> all `ready`
  second `--all` -> rea/evo/openwiki/projectatlas: ready ×4 · setup_tool: 4 tool(s) · all ok
  cargo hidden -> projectatlas refused: rustup + MSVC lines, "pin bed8ba3c9b5e is not a tagged release ... nearest later release: v0.5.0-rc3"
  evo --remove -> removed; --check evo -> "not ready (absent) -> one command: python3 tools/station/setup_tool.py evo", rc=1
```
