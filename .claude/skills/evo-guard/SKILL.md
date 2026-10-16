---
name: evo-guard
description: Freeze a holdout BEFORE any evo optimise run and re-measure the winner on it; every 'found' gain is in-sample until then. Writes work/optimize/<slug>.md.
---
# evo-guard — no optimiser gain without a frozen holdout (station forge; gap skill)

evo searches many variants against one benchmark and keeps the best. The best of many on the data it was chosen on
is selection bias, not improvement. This skill puts a holdout in front of the loop and a re-measure behind it.

## When
Every `optimize-loop` workflow run, and any manual use of the held evo skills
(`repertoire/evo-hq~evo/plugins/evo/skills/{discover,optimize,report,ship}/`). Runs after `evo discover` and
BEFORE the first `evo optimize` experiment.

## Do
1. **Split.** From the benchmark inputs evo discover built, set aside >= 20% (or >= 5 cases, whichever is larger)
   as the holdout. Write the holdout to `work/optimize/<slug>/holdout/` and never give that path to evo.
2. **Freeze.** `find work/optimize/<slug>/holdout -type f | sort | xargs sha256sum | sha256sum` -> `holdout_sha256`.
   Record `holdout_frozen_at:` (UTC) before the first experiment starts.
3. **Telemetry.** Run evo only in a run-tree with `EVO_TELEMETRY=0` (or `DO_NOT_TRACK=1`) in the env; never
   `evo telemetry off` (it sends a final event).
4. **Optimise** with the held evo method. Every score evo reports is labelled in-sample.
5. **Re-measure** the chosen candidate AND the baseline on the holdout (same harness, same seed policy). Re-hash
   the holdout first: a changed hash voids the run.
6. Write `work/optimize/<slug>.md`: `target:`, `metric:`, `holdout_sha256:`, `holdout_frozen_at:`, `n_holdout:`,
   `baseline_score:`, `candidate_score_in_sample:`, `holdout_score:` (baseline vs candidate),
   `gain_status: in-sample | out-of-sample`. Only `evo ship` a candidate whose holdout gain is positive.

## Test (what fails)
`python3 tools/station/forge_check.py check` (`forge_gates`): a report without a 64-hex `holdout_sha256`, without
`holdout_frozen_at`, or claiming `gain_status: out-of-sample` with no `holdout_score`. Planted in the selftest.

## Never
Never tune on the holdout, never re-split after seeing holdout numbers (that is a new run with a new hash).
