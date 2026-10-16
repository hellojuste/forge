---
name: handoff
description: Write the durable handoff a fresh session picks the work up from: five header fields, five sections, waves a fresh worker can take alone, every negative claim re-derived now.
---
# handoff — the durable handoff document (commons; owner governance/rules.json R-handoff)

For a session that is ending while the work continues: context running out, a different model tier next, or the
operator says "hand off". For a session that is awake right now, message it instead; a handoff is the artifact.

## Live context (injected, never transcribed)
!`python3 tools/station_audit.py --state`
!`git log --oneline -8`

## 1 · Header — in the first 40 lines, all five
```
branch: <branch>            date: <YYYY-MM-DD>
covers: <the scope this handoff speaks for — more than one current handoff is safe only with this>
supersedes: <path of the handoff it replaces | none>
audit: <the command a reader runs first, e.g. python3 tools/station_audit.py>
```

## 2 · Five sections
1. **Where things stand** — what is true now, each fact with the command that shows it.
2. **What changed and what it means** — the commits (hash + subject) and why they matter for the next worker.
3. **What is next, as waves** — each wave: deliverable (one file or one return shape) · files · tier (from /tier) ·
   done-test (a command that can fail) · refusal (what the worker returns instead of guessing).
4. **What is blocked and on whom** — the blocker, its owner, and the act that releases it.
5. **Open questions** — each with what would settle it (a test, a file to read, a person to ask).

## 3 · Rules that make it trustworthy
- **Re-derive every negative claim** in THIS session ("X is broken", "Y is not implemented", "Z has no tests"): run the
  command or read the file now and cite it. Inherited negatives are the most expensive kind of wrong.
- **No transcribed counters.** Name the command that prints a number; do not paste the number as a fact that will rot.
- **Anchors are text, never line numbers**: `path` + a quoted phrase the reader can grep.
- **Corrections go where the reader acts** (edit the wave row), not into a changelog paragraph above it.
- Operator orders since the session started are quoted verbatim with their locator.

## 4 · Where it goes
`work/HANDOFF_<topic>.md` on a station (`HANDOFF.md` at the root on main), committed by path, then run /closeout.
