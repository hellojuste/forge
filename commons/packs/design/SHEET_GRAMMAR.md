<!-- kit-authored · pack: design · owner: commons/packs/design/SHEET_GRAMMAR.md · grammar for a dashboard sheet a person must read correctly at a glance -->
# Dashboard sheet grammar (design pack)

A dashboard sheet is read in seconds and acted on. These rules make the reading correct: every number shows what it
is out of, every active filter is visible, and empty or extreme data looks different from normal data. They apply to
any BI tool or hand-built page.

## 1 · KPI tile = value + denominator + period + comparison
```
Revenue invoiced            <- the measure, in the reader's words
EUR 412.6k                  <- value with unit and scale
of EUR 480k plan (86%)      <- the denominator it is read against (plan, total, population)
Sep 2026 · vs Aug +4.1%     <- period and ONE comparison with its sign
```
- A percentage always shows its numerator and denominator on the tile or in its tooltip: `86% (412.6k / 480k)`.
- A count shows its population: `37 late orders of 1,204 open`.
- An average shows its n: `avg lead time 11.2 d (n = 318 orders)`.
- Comparisons say against what (`vs Aug`, `vs plan`, `vs same month last year`); colour alone never encodes direction.

## 2 · Filter visibility
- Every filter that changes a number on the sheet is visible on the sheet (a filter bar or a "current selections"
  line), including filters inherited from another sheet or set by default/section access.
- A tile computed with a filter that differs from the sheet's (a fixed set-analysis selection, an "ignore filters"
  measure) says so in its subtitle: `all regions (ignores region filter)`.
- Company/entity scope is always shown when the data model holds more than one entity.

## 3 · Empty, partial and extreme states
- **Empty**: no rows -> the tile shows `no data for <selection>`, never `0` and never a blank. Zero is a value; empty
  is the absence of one.
- **Partial period**: the current, incomplete period is marked (`Oct 2026 · to date, 16 of 31 days`) and is not
  compared with a full period without that mark.
- **Extreme**: values beyond a sane range (negative stock, margin > 100%, a 10x jump) are flagged on the tile with a
  link to the rows behind them; they are data-quality signals first.
- **Late data**: the sheet shows the data's as-of time (last reload / source extract time), not the page's render time.

## 4 · Reconciliation
Every headline number on a sheet ties to a source-system report a controller trusts. The sheet (or its notes) names
that report and the last reconciliation: `ties to <ERP report> · checked <date> · diff 0.00`. A number that does not
tie is labelled `unreconciled` until it does.

## 5 · Layout order
Top-left: the question the sheet answers and its scope. Then KPI tiles (with denominators), then the trend that
explains them, then the detail table that lets the reader check them. Detail tables carry totals that equal the tiles.

## 6 · Review checklist (pass/fail, evidence per line)
1. Every KPI shows value, unit, denominator, period and one labelled comparison.
2. Every active filter (incl. defaults and section access) is visible.
3. Empty shows "no data", not 0; partial periods are marked; extremes are flagged.
4. As-of time of the data is visible.
5. Headline numbers name the source report they tie to and the last check.
6. Colour is never the only carrier of meaning; sign and label carry it too.
