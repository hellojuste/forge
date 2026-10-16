# Proposal: registry/telemetry.json rows after forge-setup (land on main; registry/ is commons)

owner: station forge · skill telemetry-audit steps 2-4 · status: PROPOSAL · date: 2026-10-16 · order: "forge — one-step
setup for rea, evo, openwiki and ProjectAtlas" (1e)

`registry/telemetry.json` is a commons file. `commons_drift` compares it with main's copy, so the station does not
edit it. This file holds the proposed rows. Each row was read at the registry pin, and each status run was made
with the installed tool from `python3 tools/station/setup_tool.py <tool>`.

**Who ran it (read this before flipping).** The runs below were made by the forge child session in a Linux cloud
container (node 22.22.0, uv 0.11.32, cargo 1.97 via rustup), not by the operator on Windows. The registry `_doc`
says a row flips only with "the tool's own offline status run by the operator (J2 GA6)". Main decides one of two
things:
- (a) accept these runs as `verified_by_run`, or
- (b) keep `verified: false` until the operator repeats one line per tool on Windows. The line is the smoke step of
  `python3 tools/station/setup_tool.py <tool>`, which prints the same output.

## Findings per tool (pin, opt-out, evidence, status run)

| tool @ pin | sender | opt-out the wrapper sets | evidence (file:line at the pin) | offline status run → output |
|---|---|---|---|---|
| evo @ c70c04b (evo-hq-cli 0.8.0) | PostHog-style events to `https://telemetry.evo-hq.com/v1/events`, config from `/v1/config` (telemetry.py:31-32), ON by default. Every command except `telemetry` sends (cli.py:7430-7432). A PyPI version GET runs at most once every 24h (version_check.py:24,91). | `EVO_TELEMETRY=0`, `DO_NOT_TRACK=1`, `EVO_SKIP_VERSION_CHECK=1`, `EVO_HOME=<tree>/.kit-tool/home` with `telemetry.json` `{"enabled": false}` | `env_forces_off` telemetry.py:105-111; settings gate :123; version check skip version_check.py:104; `evo telemetry off` sends a final event (telemetry.py:445-455) | `kit-bin/evo telemetry status --json` → `"enabled": false, "source": "env", "install_id": null`. Env unset with only the config file: `"enabled": false, "source": "user"`. Both switches work on their own. |
| openwiki @ 7c469e5 (openwiki 0.7.2) | PostHog `https://us.i.posthog.com` (config.ts:13), event `openwiki_run`. Only non-dry `init`/`update` send (commands.ts:1157-1163). CI runs still send under a ci id (gates.ts:41-58). | `OPENWIKI_TELEMETRY_DISABLED=1`, `DO_NOT_TRACK=1`, `LANGCHAIN_TRACING_V2=false`, `OPENWIKI_CONFIG_DIR=<tree>/.kit-tool/home`, whose `.env` carries the same opt-out | gates.ts:28-32 and :84-90 (truthy = set and not ''/'0'/'false'); senders.ts:136-142 returns before the send. The installed package carries the same gate: `dist/telemetry/gates.js:24`, `dist/telemetry/senders.js:76`. | The installed `dist/telemetry/senders.js` `recordRun({command:'init', telemetryFile})` was called with `HTTPS_PROXY=http://127.0.0.1:9` (offline). The telemetry file reads `{"disabled": true, "sent": false}` and no `install-id` was created in the home. The CLI's own `openwiki init --telemetry-file` needs a model key, so it was not run. |
| ProjectAtlas @ bed8ba3 (0.5.0-rc3) | **Local only.** Token accounting goes into the project SQLite DB (core/src/telemetry.rs:1, db/src/telemetry.rs:1). The default build has no HTTP client: `cargo tree -p projectatlas-cli --locked -e normal` → 0 of ureq/reqwest/hyper. `ureq` is in Cargo.lock only through the optional `tree-sitter-language-pack` feature (Cargo.toml:133, cli Cargo.toml:91,125). | `PROJECTATLAS_NO_TELEMETRY=1` (it even skips the local writes), `DO_NOT_TRACK=1` | runtime.rs:3608-3610 `telemetry_disabled()`; truthy_env main.rs:4034-4040 (1/true/yes/on); writes are skipped at runtime.rs:3532,3590 and mcp.rs:4097-4098,4119 | `kit-bin/projectatlas runtime-info` → `version: "0.5.0-rc3"`, capabilities `... "token-telemetry"`. The output names no endpoint and no remote host other than the repository URL. |
| rea @ 1bd5c5c (rea-agents 6.5.0) | **No sender found.** I grepped src/, scripts/, bridge/ and native/ at the pin, and the 158 installed packages (incur 0.6.1 included), for telemetry, posthog, @sentry, mixpanel, segment.io, amplitude and update-notifier. The only hits are doc comments. The update check runs only inside the explicit `rea update` (UpdateRuntime.ts:198-207), and act_gate asks before it. | `DO_NOT_TRACK=1` (harmless; nothing reads it) | grep above; no `*_API_KEY` is read in src/ (REA calls no LLM) | `kit-bin/rea --version` → `6.5.0`; `kit-bin/rea --help` → rc 0 |

## Proposed rows (exact JSON for main; `verified` per choice (a), else keep false)

```json
{"tool": "evo", "repo": "evo-hq/evo", "station": "forge", "verified": true,
 "opt_out": "EVO_TELEMETRY in 0/false/off/no or DO_NOT_TRACK in 1/true/yes (telemetry.py:105-111); or $EVO_HOME/telemetry.json {\"enabled\": false} (telemetry.py:123); EVO_SKIP_VERSION_CHECK=1 skips the PyPI GET (version_check.py:104); never `evo telemetry off` (telemetry.py:445-455 sends a final event)",
 "opt_out_candidate_env": {"EVO_TELEMETRY": "0", "DO_NOT_TRACK": "1", "EVO_SKIP_VERSION_CHECK": "1"},
 "verified_by_run": "2026-10-16 forge-setup (cloud container, evo-hq-cli 0.8.0 from setup_tool.py): kit-bin/evo telemetry status --json -> {\"enabled\": false, \"source\": \"env\", \"install_id\": null}; with the env unset and only $EVO_HOME/telemetry.json -> {\"enabled\": false, \"source\": \"user\"}"}
{"tool": "openwiki", "repo": "langchain-ai/openwiki", "station": "forge", "verified": true,
 "opt_out": "OPENWIKI_TELEMETRY_DISABLED=1 or DO_NOT_TRACK=1 (truthy, gates.ts:28-32,84-90; checked before the send at senders.ts:136-142); CI is NOT an opt-out (gates.ts:41-58); LANGCHAIN_TRACING_V2=false for LangSmith (env.ts:178-180)",
 "opt_out_candidate_env": {"OPENWIKI_TELEMETRY_DISABLED": "1", "DO_NOT_TRACK": "1", "LANGCHAIN_TRACING_V2": "false"},
 "verified_by_run": "2026-10-16 forge-setup (cloud container, openwiki 0.7.2 from setup_tool.py, HTTPS_PROXY=http://127.0.0.1:9): installed dist/telemetry/senders.js recordRun({command:'init', telemetryFile}) -> {\"disabled\": true, \"sent\": false}; no install-id written"}
{"tool": "projectatlas", "repo": "styler-ai/ProjectAtlas", "station": "forge", "verified": true,
 "evidence": "crates/projectatlas-core/src/telemetry.rs:1, crates/projectatlas-db/src/telemetry.rs:1 (local token accounting in the project SQLite DB); default build has no HTTP client (cargo tree -p projectatlas-cli -e normal: 0 of ureq/reqwest/hyper; ureq only via the optional tree-sitter-language-pack feature)",
 "opt_out": "local only (no network sender); PROJECTATLAS_NO_TELEMETRY in 1/true/yes/on skips even the local writes (crates/projectatlas-cli/src/runtime.rs:3608-3610, main.rs:4034-4040)",
 "opt_out_candidate_env": {"PROJECTATLAS_NO_TELEMETRY": "1"},
 "verified_by_run": "2026-10-16 forge-setup (cloud container, projectatlas 0.5.0-rc3 built by cargo install --locked --path at the pin): kit-bin/projectatlas runtime-info -> version 0.5.0-rc3, capabilities incl. token-telemetry, no endpoint printed"}
{"tool": "rea", "repo": "morluto/rea", "station": "forge", "verified": true,
 "evidence": "no sender: grep telemetry|posthog|@sentry|mixpanel|segment.io|amplitude|update-notifier over src/ scripts/ bridge/ native/ at the pin and the 158 installed packages (incur 0.6.1 included): doc comments only; update check only in explicit `rea update` (src/application/UpdateRuntime.ts:198-207)",
 "opt_out": "none needed (no sender); `rea setup|update|analyze-*` are act_gate asks",
 "opt_out_candidate_env": {"DO_NOT_TRACK": "1"},
 "verified_by_run": "2026-10-16 forge-setup (cloud container, rea-agents 6.5.0 from setup_tool.py): kit-bin/rea --version -> 6.5.0; kit-bin/rea --help -> rc 0"}
```

`denominator` becomes 12 once the rea row is added.

## After main lands this

- `telemetry_plan.py gate <tool>` exits 0 for the flipped rows, so `optimize-loop` and `wiki-gen` get past their
  telemetry gates.
- `setup_tool.py --check <tool>` is the second gate, and it is already live on this branch.
- Re-test trigger: a repin of any of the four. `kit-repin` re-reads telemetry, and `setup_tool.py` reinstalls at the
  new pin's version.
