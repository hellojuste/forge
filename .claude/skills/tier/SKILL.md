---
name: tier
description: Score an unstarted work item on six dimensions and return the model and effort to run it at, in a fixed shape, with the escalation boundary named as a STOP.
---
# tier — model and effort from the work, not from ambition (commons; owner governance/rules.json R-tier)

Roster: `station.json gov.model_roster` (`small` / `medium` / `large`; placeholders until the operator sets them).

## Score each 1–5, anchored on THIS station's surfaces
| dim | 1 | 3 | 5 |
|---|---|---|---|
| **REV** what being wrong costs here | a scratch note | a committed file others read | money moved, a message sent, a client deliverable, a lane or live surface touched |
| **MEAS** how much is measurement | none | counts with denominators | a forward claim (n, interval, OOS walk) |
| **AMB** ambiguity of the ask | literal | some judgement | the plan itself is unclear |
| **BREADTH** files / sources touched | 1 | ~10 | the whole station or many repos |
| **NOV** novelty | done here before | adapted pattern | first of its kind |
| **AUTO** autonomy (time without a human) | minutes, watched | an hour | a long unattended run |

## Rules
- **Model** = max(AMB, NOV, MEAS): 1–3 -> `small` or `medium` (3 -> medium); 4–5 -> `large`.
- **Effort** = max(BREADTH, AUTO): 1–2 low · 3 medium · 4 high · 5 xhigh.
- **Overrides:** REV >= 4 floors effort at medium; MEAS = 5 floors the model at large.
- **Mid-flight:** a wrong ANSWER bumps the model; a skipped file or an unrun check bumps the EFFORT.

## Output (fixed shape; the closeout fixture rejects a block missing the escalation line)
```
**Recommendation:** <model> at <effort> effort
**Scores:** REV n · MEAS n · AMB n · BREADTH n · NOV n · AUTO n
**Why:** 2–4 sentences
**Escalation boundary:** <the named item inside this pass that must STOP and rise> | none, the pass is uniform
**Before the irreversible act:** <what must be green> | nothing irreversible
**Review disposition:** next | parked, trigger "<...>" | closed
```
