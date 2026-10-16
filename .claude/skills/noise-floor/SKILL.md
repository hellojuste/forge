---
name: noise-floor
description: Before a tool trial or evo loop claims a gain, run the frozen baseline K >= 5 times and record the spread; a gain not larger than the spread is no gain. Writes noise_floor/spread lines.
---
# noise-floor — measure the run-to-run spread before believing a delta

owner: station forge · gap G2 (router/REASSIGN.md) · check: `python3 tools/station/forge_check.py check` (gate `noise`)

## When
Before `trial-run` gives a verdict, before `optimize-loop` (or `evo-guard`) calls a gain out-of-sample, and any time
someone quotes "X% fewer tokens" or "+0.03 score" from one run of each arm.

## Procedure
1. Pick the unchanged baseline: the A arm (no tool) of the first frozen task, or evo's baseline commit on the frozen
   benchmark. Do not change prompt, model, effort or seed policy between repeats.
2. Run it K >= 5 times, each in a fresh context (a new agent or a new process). Record each score as a number:
   tokens for a trial, the benchmark metric for evo.
3. spread = (max - min) / mean for token counts; for a bounded metric use max - min in the metric's own unit.
   Write the seed policy you held fixed (temperature, seed, model, effort).
4. Put these lines at the top of the report (`work/trials/<tool>.md` or `work/optimize/<slug>.md`):
   ```
   noise_floor: K=<k> <seed policy>
   spread: <number>
   gain: <the claimed delta, same unit; negative tokens = cheaper>
   ```
5. Decide: |gain| <= spread means park (trial) or in-sample/noise (evo). Only |gain| > spread can be promoted, and the
   report states both numbers with their denominators (K repeats, N tasks).

## Refusals (the failing test)
`forge_gates` is red when a trial report with a verdict, or an optimise report claiming a gain, lacks
`noise_floor: K=<k>` with K >= 5 or a numeric `spread:`, and when a `promote` / `out-of-sample` claim has
|gain| <= spread. Planted cases: `python3 tools/station/forge_check.py --selftest` (noise floor K<5, trial promoted
inside the spread, optimize gain inside the spread).

## Not this skill
Choosing the tasks (tool-trial), freezing the holdout (evo-guard). This skill only measures the floor under them.
