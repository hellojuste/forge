---
name: design-review
description: Measure a page, dashboard, MVP or CV/portfolio build in any station with the kit's design detector, contrast arithmetic and handoff lint: a scored verdict with evidence.
---
# design-review — measured design verdict, any station (commons; owner governance/rules.d/design.json R-design-detector)

Use it before you ship anything people look at: a venture MVP, a client-bi dashboard export, a career CV/portfolio
page, a studio variant. Studio still owns design WORK (briefs, variants, the four-lens review, polish); this skill is
the shared measuring floor every station runs.

## Steps (each prints its own evidence)
1. **Detector** — `python3 tools/design/detector/detect.py <file|dir> [--design DESIGN.md] --report <out>.txt`
   Score 0-100, 59 rules, exit 0 pass / 1 fail. No network. The rendered pass runs only if Playwright is already
   installed; otherwise those rules are listed NOT RUN (never counted clean). Quote the score and every finding id.
2. **Contrast** — `python3 tools/design/contrast.py FG BG --use body|large|ui` per text/UI pair (AA body 4.5,
   large 3.0, ui 3.0). For chart palettes prefer the account `dataviz` skill when listed; this stays the text floor.
3. **Tokens** — `python3 tools/design/handoff.py tokens tokens.json --css`: validates against
   `commons/schema/design_tokens.schema.json` and prints the `:root` block. Import `token_leaves` from
   `tools/design/handoff.py`; never keep a station copy.
4. **Handoff** (when a design moves between stations) — `python3 tools/design/handoff.py check <dir>`; format in
   `commons/packs/design/HANDOFF.md`.

## Verdict shape
`design-review: <target> · detector <score>/100 exit <0|1> (<n> findings of 59 rules run, <k> NOT RUN) · contrast <p>/<q> pairs pass · tokens OK|<errors>`
A detector exit 1 or a failing pair is a FAIL with the finding named; fix it or say why it stays.

## Directions (optional)
`python3 tools/design/design_catalog.py deal --n 3 --seed <slug>` deals local directions; the impeccable.style roll
is asked opted out (R-design-roll) and falls back to local with one notice line when offline.
