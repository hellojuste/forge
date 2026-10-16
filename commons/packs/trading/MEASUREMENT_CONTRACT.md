<!-- kit-authored · pack: trading · owner: commons/packs/trading/MEASUREMENT_CONTRACT.md · copy into a station as work/MEASUREMENT_CONTRACT.md only by reference; edit here on main -->
# Measurement contract (trading pack)

A number about a market is a claim about the future the moment anyone acts on it. This contract says what a claim
must carry before it may be stated, weighted or acted on. It binds every edge report, backtest summary, journal
statistic and upstream performance figure a station repeats.

## 1 · Every numerator carries its denominator
A rate, average, total or verdict is written with:
- **n** — the number of independent observations behind it (trades, signals, days), not the number of rows read;
- **population** — what was eligible (instrument, timeframe, session filter, date range) and what was dropped, with
  the count dropped and why;
- **command** — the exact command (or notebook cell, with its file and commit) that produced the number.

A green on zero rows prints `0`. "Win rate 64%" is not a statement; "64% (41/64 closed trades, EURUSD H1,
2023-01-02..2024-06-28, 3 rejected for missing fills) — `python3 tools/station/edge.py report --id E12`" is.

## 2 · Forward claims (expected return, edge, Sharpe, win rate used to size or arm)
A forward claim states all four, or it is restated as in-sample description and nothing acts on it:
1. **n** (section 1).
2. **An interval** — a confidence or credible interval for the quantity (bootstrap over trades, or a stated
   parametric model WITH its assumption written down). An empirical band is called empirical; never call it Gaussian.
3. **An out-of-sample walk-forward** — the parameters are fitted on window k and scored on window k+1, rolled across
   the history; the reported figure is the concatenated OOS result, with the number of folds and each fold's n.
4. **The window it was measured on**, so a reader can check rule 3.

## 3 · The LEAK rule
No weight, threshold or selection may use an estimate measured on the same window it is applied to. Concretely:
- a signal's weight in a composite comes from its OOS performance on PRIOR folds only;
- a filter chosen because it improved the backtest is part of the fit, so it is inside the walk, not outside it;
- a parameter sweep reports how many variants were tried; the best of N is deflated (or reported with N beside it).

## 4 · Shrink by n
An estimate from few observations is pulled toward its prior (zero edge, unless a preregistered prior says
otherwise) in proportion to its uncertainty. A simple portable form: `w = n / (n + k)` with k preregistered (for
example k = 30 trades); the shrunk estimate is `w * estimate + (1 - w) * prior`. Report both the raw and the shrunk value.

## 5 · Honest bands and independent evidence
- A **state** band (where the quantity is now, ± z·sqrt(state variance)) and a **predictive** band (where the next
  observation may land, ± z·sqrt(predictive variance)) are different things; label which one is drawn.
- Agreement between two views computed from the SAME data is not confirmation. Confluence needs different inputs.
- Each evidence family (structure, volume, positioning/dominance, macro) gets at most ONE weighted vote.
- The forming (incomplete) bar is provisional; a claim computed on it says so.

## 6 · Advisory output never arms
Backtest, lifecycle or journal output that is in-sample or lacks its denominator is ADVISORY: it may be shown, never
used to place, size or arm an order. An OOS walk-forward expected return WITH its denominator may arm, under the
station's own act gate.

## 7 · Upstream performance claims
A figure quoted from an upstream README, paper or vendor page is an UNDENOMINATED claim until this contract's fields
are recovered from its own data. Record it in `PREREGISTRATIONS.md` as a claim to test, never as a fact.

## 8 · Where the pieces live
- Preregister before you look: `PREREGISTRATIONS.md`.
- Refuted ideas: `NEGATIVE_RESULTS.md` (checked FIRST by every new edge attempt).
- Review lens: `FIT_LENS.md` (the reviewer's checklist; a claim failing any line is REFUTED, not "noted").
