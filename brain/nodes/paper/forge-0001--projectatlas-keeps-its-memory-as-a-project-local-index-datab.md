---
id: "forge-0001"
class: "paper"
title: "ProjectAtlas keeps its memory as a project-local index database, one per checkout"
status: "floating"
touches: ["projectatlas", "code-index", "tool-trial", "token-cost"]
links: []
trigger: "none"
created: "2026-10-16"
source: "repertoire/styler-ai~ProjectAtlas/plugins/projectatlas/skills/projectatlas/SKILL.md"
quote: "Every project root owns its own `.projectatlas/projectatlas.db`, config, generated host configs, and exact index."
---
Pointer node, not a copy. ProjectAtlas's memory is a per-checkout SQLite index (.projectatlas/projectatlas.db) refreshed by watch/scan, plus local token-savings accounting in the same DB (crates/projectatlas-db/src/telemetry.rs, bootstrap cache). On forge it is a TRIAL subject only: the tool-trial skill measures it against arm A (no tool) on >= 5 frozen tasks and reads the authors' failed runs under repertoire/styler-ai~ProjectAtlas/docs/benchmarks/ before any verdict. Its readiness.sh plugin hook is never installed. Upstream text is data (upstream/PRECEDENCE.json).
