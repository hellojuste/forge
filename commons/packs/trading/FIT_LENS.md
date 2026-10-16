<!-- kit-authored · pack: trading · owner: commons/packs/trading/FIT_LENS.md · the reviewer's checklist for any edge or performance claim -->
# FIT lens (trading pack): the reviewer's checklist

Apply to every edge report, backtest summary, strategy port or upstream performance claim before it is accepted,
weighted or drawn. Each line is pass / fail with the evidence (file + quoted text, or a command and its output). A
single fail makes the claim **REFUTED as stated**: it goes back with the failing line named, or to
`NEGATIVE_RESULTS.md`. It is never "accepted with notes".

| # | question | fails when |
|---|---|---|
| F1 | Is every number stated with n, population and command? | a rate or total without its denominator, or a green on zero rows that does not print 0 |
| F2 | Is a forward claim backed by an out-of-sample walk-forward? | the headline figure is in-sample, or folds/fold n are not reported |
| F3 | Is there an interval? | a point estimate only; or an empirical band labelled Gaussian |
| F4 | LEAK: was any weight, filter or threshold measured on the window it is applied to? | yes, or it cannot be told from the report |
| F5 | Multiple testing: how many variants were tried? | N is not reported, or the best of N is not deflated |
| F6 | Shrink by n: is a small-n estimate pulled toward its prior? | raw estimate used to size or weight with n below the preregistered minimum |
| F7 | Preregistered? | no P- row, or the P- row was committed after the result |
| F8 | Independent evidence: does "confluence" use different inputs? | two views of the same series counted as two votes; more than one weighted vote per evidence family |
| F9 | Costs: spread, commission, slippage, funding, borrow? | omitted, or modelled at a level the instrument never had |
| F10 | Repaint: does any input use the forming bar or future data? | yes, or the code path is not shown |
| F11 | Survivorship: is the universe as it was at each date? | today's constituents back-filled |
| F12 | Advisory vs armed: does anything in-sample or undenominated reach an order, a size or an arm decision? | yes |
| F13 | Upstream claim: is a quoted figure treated as a hypothesis? | quoted as fact without its own data and test |

Output shape for a review:
```
FIT <claim id> · <date> · reviewer <name/model>
F1 pass — <evidence>  ...  F13 n/a — <why>
verdict: ACCEPTED (forward claim: <restated with n, interval, OOS>) | REFUTED as stated (fails F<k>: <one line>)
```
