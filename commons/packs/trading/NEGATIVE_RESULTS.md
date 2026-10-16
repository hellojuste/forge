<!-- kit-authored · pack: trading · owner: commons/packs/trading/NEGATIVE_RESULTS.md · a station keeps its rows in work/NEGATIVE_RESULTS.md -->
# Negative results (trading pack)

Never lose a falsification. A refuted idea is written here, with the condition under which it is worth testing again,
in the SAME commit that establishes the refutation. Every new edge attempt reads this file first (the router's edge
intent gathers it), so nobody spends a week re-discovering a dead end.

## Row grammar
```
## N-<station>-<nnnn> · <YYYY-MM-DD> · <the idea, one line>
prereg: <P-... id, or "none (exploratory: weaker evidence)">
result: <the OOS metric with n and interval, e.g. mean R -0.02 (n=212, 90% CI -0.09..0.05)>
why it failed: <the mechanism you believe, marked as belief; or "unknown">
evidence: <command + commit that produced the result>
retest: <a concrete condition: an event, a date, a data change, a new instrument — never "later">
related: <other N- / P- ids>
```

## Rules
- "Did not work" is not a row. The row carries the number, its n and its interval, so a later reader can tell a
  refutation from an underpowered test.
- An inconclusive result (n below the preregistered minimum) is recorded too, as `result: inconclusive (n=...)`, so
  the next attempt knows the data was thin rather than the idea dead.
- Rows are append-only. A successful retest adds a new row that cites this one; it does not delete it.
- A falsification found in someone else's claim (an upstream README, a vendor figure) is recorded here as well, with
  the claim quoted by locator and the test that contradicted it.
