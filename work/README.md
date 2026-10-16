# work/ — the forge station's own outputs

One folder per job; every file here is station-authored (never upstream text).

| folder | written by | record checked by `forge_gates` |
|---|---|---|
| `trials/<tool>.md` (+ `trials/<tool>/tasks.json`) | skill `tool-trial`, workflow `trial-run` | `verdict:`, `n_tasks:` >= 5, `noise_floor: K=`, `spread:`; the TRIAL row in `governance/STATION_LEDGER.md` |
| `optimize/<slug>.md` (+ `optimize/<slug>/holdout/`) | skill `evo-guard`, workflow `optimize-loop` | `holdout_sha256:`, `holdout_frozen_at:`, `gain_status:` |
| `wiki/<repo>/` | workflow `wiki-gen` (non-client repos only) | `REVIEW.md`: `target:`, `target_class:`, `status: generated|refused-*`; generated needs the openwiki telemetry row verified |
| `re/legal_gate.json`, `re/<slug>.md` | skill `re-legal-gate`, workflow `reverse` | every report names a `gate: RE-GATE-nnnn` that decided proceed |
| `arch/<slug>.md` | skill `design-it-twice`, workflow `arch-review` | >= 2 `## Design` sections, a depth table, `pick:` |
| `intake/<slug>.md` | workflow `intake-run` | `repo:`, 40-hex `sha:`, `licence:`, `agent_files:`, `decision:`; ingest needs its LOCK row |
| `repin/<owner~repo>-<sha7>.md` | skill `kit-maintain`, workflow `kit-repin` | `licence_diff: changed` => `status: STOPPED`, `applied: no` |

Every workflow's certain test is `python3 tools/station/forge_check.py output <kind> <path>`.
| `CHECKPOINTS.md` | the commons `checkpoint` skill | — |
