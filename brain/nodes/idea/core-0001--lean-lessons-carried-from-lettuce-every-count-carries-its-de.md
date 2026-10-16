---
id: "core-0001"
class: "idea"
title: "Lean lessons carried from lettuce: every count carries its denominator, every rule its owner and its mechanism"
status: "promoted"
touches: ["lean", "denominator", "governance", "map:tool:tools/brain.py"]
links: ["core-0002"]
trigger: "none"
created: "2026-10-16"
source: "_design/LEAN_LESSONS.md"
quote: "The lettuce lesson behind all of them is L99: *a rule in prose that a tool could enforce is a rule the next session will break*."
beats: "prose rules read hours before the act (lettuce measured them broken; LEAN LL-01, L99)"
---
The kit carries lettuce's lean and efficiency lessons (LEAN_LESSONS.md LL-01..LL-51, CA-01..CA-19) as mechanisms,
not prose: one audit runner with a denominator on every headline, one owner per rule, hooks at the moment of the act,
bounded context with named drops. An included upstream supersedes only the lean DEFAULTS, inside its own subtree or
workspace, never the kit floor (precedence: `upstream/PRECEDENCE.json`, owner governance).

The source is a design input of the kit build (not shipped in the repo); `brain.py audit` lists it under
external-source. Query: `python3 tools/brain.py near lean denominator`.
