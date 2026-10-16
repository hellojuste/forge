---
name: closeout
description: Close a work pass: audit letter/spirit/intention/sufficiency against the plan, rate it, tier the next item, set dispositions, file ledger/defect rows, end with the closeout: line.
---
# closeout — the close-out ritual (commons; owner governance/rules.json R-closeout)

Run at the end of every pass, and before handing work to a different model or session. Steps, in this order.

## 1 · Live state
!`python3 tools/station_audit.py --state`

## 2 · Audit the pass on four axes (answer each separately; one line is fine, silence is not)
- **Letter** — did it do what the plan literally said? Name the plan file and the item.
- **Spirit** — what was the plan FOR? Did the work serve that, or only the wording?
- **Intention** — re-read the ORIGINAL request or thesis and quote it with its locator (DEC row, message, file). Not
  the latest paraphrase of it.
- **Sufficiency** — docs that describe the changed thing changed with it; registers updated; GENERATED files
  regenerated (`python3 tools/upstream/notice.py --root . --write`, `python3 tools/upstream/skill_routes.py index
  --station-root .`, `python3 tools/gov/gen_manifest.py --write` on main); nothing merely "noted".

## 3 · Rate fulfilment
`fulfilment: <n>%` with the deduction named (what is missing, not how hard it was).

## 4 · One disposition per open item
`next` · `parked — trigger: <event | date | command>` · `closed`. A park without a trigger is refused: "later" is an
abandoned item wearing a nicer word.

## 5 · Defects
Each defect you found is FIXED in this pass (your own file) or filed as a `DEF-` row
(`python3 tools/gov/new_row.py defect ...`) with its re-test trigger (another owner's file). There is no third option:
a defect found and only written down is a defect shipped.

## 6 · Ledger
Any procedural or delegation failure, or near-miss, becomes an `L-` row with `hook:` answered — *could a hook or a
check have caught this?* (`HOOKED <script>` · `OWED <shape> — trigger: <condition>` · `NOT HOOKABLE <the fact no
harness event carries>`). A delegation row also names `pathology:` and `amendment:` (the section of /summon it changed).

## 7 · Commit order
Stage by path (never `git add -A` / `.` / `--all`), then `python3 tools/station_audit.py --changed` (or `-k` the
touched checks), then commit. Ledger and defect rows go in the SAME commit as the work they describe.

## 8 · Next
Tier the next item with /tier and end with exactly ONE recommended next step:
`NEXT — <one thing>` · why now · tier · first act (a literal command or file) · after it.
List parked items with their triggers and the distance to each live trigger.

## 9 · Last line (the Stop hook checks it)
`closeout: <ids filed or none> · next: <one line>`
