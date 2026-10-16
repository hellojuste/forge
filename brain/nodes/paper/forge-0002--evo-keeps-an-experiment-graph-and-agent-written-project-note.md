---
id: "forge-0002"
class: "paper"
title: "evo keeps an experiment graph and agent-written project notes under .evo/"
status: "floating"
touches: ["evo", "autoresearch", "optimize", "holdout"]
links: []
trigger: "none"
created: "2026-10-16"
source: "repertoire/evo-hq~evo/plugins/evo/skills/references/cli-quick-reference.md"
quote: "Agent's persistent project notes (you write it, you read it)."
---
Pointer node, not a copy. evo's memory is the run directory .evo/run_<id>/ (graph.json of experiments, per-attempt outcome.json, traces and diff.patch, immutable once written) plus .evo/project.md, the notes the optimising agent writes for itself; annotations and notes go through the evo CLI, never hand edits. On forge the graph is evidence of in-sample search only: the evo-guard skill freezes a holdout before the first experiment and re-measures the chosen candidate on it. evo runs only in a run-tree with EVO_TELEMETRY=0; its hooks.json hook-drain is never installed.
