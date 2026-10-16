# work/ — the forge station's own outputs

One folder per job; every file here is station-authored (never upstream text).

| folder | written by | record checked by `forge_gates` |
|---|---|---|
| `trials/<tool>.md` (+ `trials/<tool>/tasks.json`) | skill/workflow `tool-trial` | `verdict:`, `n_tasks:` >= 5; the TRIAL row in `governance/STATION_LEDGER.md` |
| `optimize/<slug>.md` (+ `optimize/<slug>/holdout/`) | skill `evo-guard`, workflow `optimize-loop` | `holdout_sha256:`, `holdout_frozen_at:`, `gain_status:` |
| `wiki/<repo>/` | workflow `wiki-gen` (non-client repos only) | — |
| `re/legal_gate.json`, `re/<slug>.md` | skill `re-legal-gate`, workflow `reverse` | every report names a `gate: RE-GATE-nnnn` that decided proceed |
| `arch/<slug>.md` | workflow `arch-review` | — |
| `repin/<owner~repo>-<sha7>.md` | skill `kit-maintain`, workflow `kit-repin` | `licence_diff: changed` => `status: STOPPED`, `applied: no` |
| `CHECKPOINTS.md` | the commons `checkpoint` skill | — |
