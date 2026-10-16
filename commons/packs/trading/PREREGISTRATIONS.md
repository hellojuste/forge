<!-- kit-authored · pack: trading · owner: commons/packs/trading/PREREGISTRATIONS.md · a station keeps its rows in work/PREREGISTRATIONS.md -->
# Preregistrations (trading pack)

Write the test down BEFORE looking at the result. A preregistration fixes what will count as success so the result
cannot move the goalposts. One row per hypothesis; rows are append-only (a change is a new row that supersedes, never
an edit).

## Row grammar
```
## P-<station>-<nnnn> · <YYYY-MM-DD> · <one-line hypothesis>
hypothesis: <the effect, stated so it can be false>
instrument/universe: <symbols, timeframe, session filter>
data: <source, date range; what is excluded and why>
in-sample window: <dates>            oos scheme: <walk-forward: fit k, score k+1; folds; fold length>
metric: <the ONE primary metric, e.g. mean R per trade>     secondary: <at most two>
success: <threshold on the OOS metric WITH its interval, e.g. lower 90% bound of mean R > 0.05>
n minimum: <below this the result is reported as inconclusive, not as a pass or a fail>
variants allowed: <how many parameter sets may be tried; the best is deflated by this N>
prior / shrink k: <prior value and the k in w = n/(n+k)>
kill: <the result that refutes it; it then goes to NEGATIVE_RESULTS.md with a retest condition>
command: <the command that will produce the verdict>
status: open | passed | refuted | inconclusive | superseded by P-...
```

## Rules
- A row is written and committed before the command in `command:` is run on OOS data. The commit hash precedes the
  result's commit hash; a reviewer checks the order with `git log --follow`.
- Changing the metric, threshold or window after seeing data creates a NEW row and marks the old one `superseded`.
- An upstream performance claim enters here as a hypothesis with `data:` = what the claim was based on, and is
  tested like any other.
- `inconclusive` is an honest outcome (n below minimum, interval spans zero). It is not a pass.

## Example
```
## P-markets-0001 · 2026-10-16 · London-open breakout continuation on EURUSD M15
hypothesis: the first 30-minute London range breakout continues >= 1R more often than it reverses
instrument/universe: EURUSD M15, 07:00-07:30 UTC range, trade 07:30-11:00
data: broker CSV 2019-01-01..2025-12-31; days with missing bars excluded (count reported)
in-sample window: 2019-2021        oos scheme: walk-forward, fit 12 months, score next 3, 16 folds
metric: mean R per trade           secondary: hit rate; max drawdown in R
success: lower 90% bootstrap bound of OOS mean R > 0.05
n minimum: 150 OOS trades
variants allowed: 12 (range length x stop rule); best deflated by N=12
prior / shrink k: prior 0R, k = 50
kill: OOS mean R <= 0 or lower bound < -0.05 -> NEGATIVE_RESULTS.md, retest if spread regime changes
command: python3 tools/station/edge.py walk --prereg P-markets-0001
status: open
```
