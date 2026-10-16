---
name: design-it-twice
description: Before an architecture recommendation, draft two or three radically different interfaces for the same module with usage examples, compare depth, leverage, locality; pick. Writes work/arch/<slug>.md.
---
# design-it-twice — never recommend the first design you thought of

owner: station forge · gap G1 (router/REASSIGN.md) · used by workflow `arch-review` · check: `forge_gates` gate `arch`

The held LibreChat skills give the vocabulary (`.claude/skills/codebase-design` — deep modules, seams, leverage,
locality) and the hunt for shallow modules (`.claude/skills/improve-codebase-architecture`). Both are upstream text,
read as data. Neither holds the "design it twice" step; this skill does.

## Procedure
1. Name the module and its callers from the code: list the call sites (`grep -rn <symbol>`), quote the current
   interface, and count its entry points. That count goes in the report.
2. Draft Design A and Design B (C optional). They must differ in the interface itself, not in naming: for example one
   deep function versus a small object API, push versus pull, a single config struct versus capability arguments.
   Each design gets a `## Design <X>` section with its interface signature, one usage example rewritten at a REAL call
   site, what it hides, and what it costs to migrate (files touched, counted).
3. Compare them in one table whose columns include depth, leverage, locality and migration cost:
   `| design | depth | leverage | locality | migration (files) |`.
4. Write `pick: <A|B|C> -- <one-line reason drawn from the table>`, and what would make you switch.
5. Save as `work/arch/<slug>.md`. Do not edit the code in this skill: the change is a later, separate pass.

## Refusals (the failing test)
`python3 tools/station/forge_check.py output arch work/arch/<slug>.md` exits 1 when the report has fewer than two
`## Design` sections, no comparison table with a depth column, or no `pick:` line (planted: "arch designed once").

## Not this skill
Reviewing a diff for bugs (`/code-review`), or the full report on a codebase (`improve-codebase-architecture`).
