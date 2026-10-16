# Brain loops — the resurfacing register

owner: tools/brain.py (commons-mapbrain) · status: CURRENT · date: 2026-10-16 · supersedes: none · audit: python3 tools/brain.py audit --check

Every loop has a **verifier** (a command that can fail), **state** (files, never a conversation) and a **stop** (a goal
AND a limit). The ladder shows the least recently considered loops at session start; record a verdict with
`python3 tools/brain.py consider <id> do|defer|decline "why"` (appends to `brain/considered.jsonl`, merge=union).
Seeded on main; a station appends its own rows below (a station-only row is still one table row).

| id | what | verifier | state | stop | trigger |
|---|---|---|---|---|---|
| brain-floating | floating nodes resolved to promoted, parked (with a cmd trigger) or refuted (with a negative link) | `python3 tools/brain.py audit --check` | brain/nodes/ | goal: 0 floating without trigger · limit: stall 2 sessions | leisure |
| brain-stale-cards | stale cards re-confirmed with card refresh (digest re-read by a human, never rewritten by a script) | `python3 tools/brain.py audit --check` | brain/nodes/ | goal: 0 stale · limit: 14 days | event: a card source edited |
| brain-due | due rechecks run and dispositioned (each trigger names its number, command and date) | `python3 tools/brain.py audit` | brain/nodes/ | goal: 0 due · limit: 3 sessions | cadence: session start |
