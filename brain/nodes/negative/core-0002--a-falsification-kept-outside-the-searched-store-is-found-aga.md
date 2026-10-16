---
id: "core-0002"
class: "negative"
title: "A falsification kept outside the searched store is found again by the next session"
status: "parked"
touches: ["falsification", "negative", "map:tool:tools/map/find.py"]
links: ["core-0001"]
trigger: "a new attempt at a falsified idea is not stopped by near (n >= 1 miss) · cmd: `python3 tools/brain.py near <idea words> --class negative` · recheck: 2027-01-16"
created: "2026-10-16"
source: "_design/LEAN_LESSONS.md"
hypothesis: "recording a falsification anywhere in the repo (a commit message, another register) is enough for the next attempt to find it"
test: "lettuce history read as data: LEDGER L4 and the N-register preamble (LEAN LL-D3)"
statistic: "lettuce LEDGER L4: 1 falsification preserved in the wrong file was undiscoverable; the N-register preamble: falsifications in commit messages were invisible to anyone proposing the same idea again"
verdict: "refuted: a falsification must live in the store that is searched before building (here: a negative node, searched first by brain.py near and tools/map/find.py)"
retest: "a planted negative must be the top hit and print FALSIFIED-BEFORE · cmd: `python3 tools/brain.py selftest`"
searched: "1 (pre-stated)"
confidence: "INFERRED"
mechanism: "EXPLAINED"
quote: "LEDGER L4 (a falsification preserved in the wrong file was undiscoverable)"
---
Example node for the class `negative` (LL-D3 "never lose a falsification"). Negative results are a node class, not a
second register, so the same `near` query that looks for prior art also returns what was already refuted,
labelled FALSIFIED-BEFORE. The `retest` field is the load-bearing one: it names the condition and command under
which the question may be reopened.
