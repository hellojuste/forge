<!-- kit-authored · pack: design · owner: governance/rules.d/design.json R-design-handoff · the handoff package every station builds from or consumes -->
# Design handoff package (design pack)

A handoff is the folder a design leaves in when it moves to the station that builds it. Studio writes most of them;
venture (product UI), client-bi (dashboards) and career (CV/portfolio) consume them, and any station may write one
for its own build. One format, one linter: `python3 tools/design/handoff.py check <dir>`.

## The README (`<dir>/README.md`)
```
target: venture            # site | venture | client-bi | career
first move: <what the target station runs first>
tokens: tokens.json        # commons/schema/design_tokens.schema.json
tokens-css: tokens.css     # every token as a --<group>-<name> custom property on :root
design-md: DESIGN.md       # YAML frontmatter (colors, typography, rounded) + prose
component: components/     # the built parts
motion-spec: motion.spec.md  # element | trigger | property | duration (ms) | curve | reduced-motion
a11y: a11y.md              # | fg | bg | use | ratio | rows, re-measured by tools/design/contrast.py; focus + reduced-motion notes
breakpoints: breakpoints.md  # >= 2 rows naming a px width
dataset: dataset.json      # the sample data the components were reviewed with
review: review.md          # verdict ship | fix-then-ship (never rework); every lens reports with evidence
site: site/                # optional: a built site whose detector-report.txt says `verdict: exit 0`
```

## Tokens
Four required groups (`color`, `font`, `space`, `radius`); a leaf is a string/number or `{"value": ...}`; `$`/`_` keys
are metadata. `python3 tools/design/handoff.py tokens tokens.json --css` validates and prints the `:root` block. A
station never keeps its own flattening rule: import `token_leaves` / `tokens_css` from `tools/design/handoff.py`.

## Measuring a build
`python3 tools/design/detector/detect.py <html|css|dir> [--design DESIGN.md]` scores the build 0-100 against the 59
detector rules (exit 0 pass, 1 fail). Skill `design-review` runs the detector, contrast and this lint in any station.
