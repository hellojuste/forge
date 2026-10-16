# Proposal: registry/telemetry.json rows for the forge tools (land on main; registry/ is commons)

owner: station forge · skill telemetry-audit step 4 · status: PROPOSAL · date: 2026-10-16 · answers SAFETY review finding 8
("evo and openwiki registry rows are stale against the evidence forge's `.env` already cites")

The station never edits `registry/telemetry.json`. These are the field changes for the main owner. Each keeps
`verified: false`: only the operator's offline status run (`python3 tools/station/telemetry_plan.py show <tool>`)
flips it, with `verified_by_run`.

| repo | field | current on main | proposed | evidence at the pin |
|---|---|---|---|---|
| evo-hq/evo | `opt_out` | "EVO_TELEMETRY (read at telemetry.py:103) and DO_NOT_TRACK (telemetry.py:111); exact off-value unconfirmed" | "EVO_TELEMETRY in 0/false/off/no, or DO_NOT_TRACK in 1/true/yes (telemetry.py:102-112); gate telemetry_enabled() at :120-121; never `evo telemetry off` (cli.py:615-623 sends a final event)" | `plugins/evo/src/evo/telemetry.py:102-112`, `:120-121`; `plugins/evo/src/evo/cli.py:615-623` (station.json `telemetry` and `irreversible_acts_why`) |
| evo-hq/evo | `opt_out_candidate_env` | `{"DO_NOT_TRACK": "1"}` | `{"EVO_TELEMETRY": "0", "DO_NOT_TRACK": "1"}` | same |
| langchain-ai/openwiki | `evidence` | "src/telemetry/config.ts:39 (FIRST_RUN_NOTICE_OPT_OUT text)" | "src/telemetry/gates.ts:28-32 (reads OPENWIKI_TELEMETRY_DISABLED / DO_NOT_TRACK); send gated at src/telemetry/senders.ts:136; notice text config.ts:39" | station.json `telemetry` row for openwiki |
| langchain-ai/openwiki | `opt_out` | "...the reading branch of the code is not yet cited" | "truthy OPENWIKI_TELEMETRY_DISABLED or DO_NOT_TRACK skips the send (gates.ts:28-32, senders.ts:136)" | same |
| styler-ai/ProjectAtlas | `evidence` | (see main) | "crates/projectatlas-db/src/telemetry.rs:1: local token accounting in the project DB; no network sender recorded" | station.json `telemetry` row for ProjectAtlas |

SUPERSEDED in part 2026-10-16 (the words above stay): after merging main at 74b7eca, `registry/telemetry.json` already
carries the evo and openwiki opt-out evidence (main commit 79ec056, "telemetry rows re-read at the pins (SAFETY 7-9)"),
so those four rows are LANDED. Still open for main: the ProjectAtlas row (`opt_out: unread`) — proposed text above.

The offline status runs that would then flip each row are printed by `python3 tools/station/telemetry_plan.py all`.
