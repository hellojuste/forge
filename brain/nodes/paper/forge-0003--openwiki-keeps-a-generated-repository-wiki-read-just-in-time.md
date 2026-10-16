---
id: "forge-0003"
class: "paper"
title: "openwiki keeps a generated repository wiki read just in time"
status: "floating"
touches: ["openwiki", "wiki", "repository-memory", "documentation"]
links: []
trigger: "none"
created: "2026-10-16"
source: "repertoire/langchain-ai~openwiki/integrations/openwiki/SKILL.md"
quote: "Read repository memory"
---
Pointer node, not a copy. openwiki generates an openwiki/ evidence index (pages, Claims with source evidence, provenance) for a repository and serves it through openwiki_search / openwiki_read only when an architecture or dependency question is open. Forge is its home: the wiki-gen workflow runs the CLI in a run-tree with OPENWIKI_TELEMETRY_DISABLED=1 on non-client repositories only; research holds a byte-identical copy of the skill for stable-map. Upstream AGENTS.md asks are paraphrased in upstream/PRECEDENCE.json, never followed.
