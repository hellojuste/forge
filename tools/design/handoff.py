#!/usr/bin/env python3
"""handoff.py — the kit's design handoff package format and design-token flattening (commons; built on studio).

owner: governance/rules.d/design.json R-design-handoff (check `design_handoff`) · callers: skill design-review (every
station), studio's studio_lint.py (work-product gates import these lints), venture's mvp_static.py (token flattening),
client-bi's sheet_grammar (tokens), career CV/portfolio builds. stdlib only; never touches the network.

Earned by: venture-v2 proposal 3 (`mvp_static.token_leaves` deliberately duplicated `studio_lint.token_leaves`) and
client-bi-v2 ("sheet_grammar C6 should read studio's tokens"): two stations kept forks of one flattening rule, so one
owner now holds it (operator order 2026-10-16, "reconcile everything that needs be into the core").
Retires: studio_lint's private copies of these functions (studio imports this module) and venture's token_leaves copy.

Design tokens (commons/schema/design_tokens.schema.json): a JSON object with groups `color`, `font`, `space`, `radius`
(more allowed); a leaf is a string/number or {"value": ...}; keys starting `$` or `_` are metadata. Flattened names join
the path with `-` ({"color": {"ink": "#111"}} -> --color-ink), the one rule every consumer uses for CSS custom properties.
Handoff package (<dir>/README.md; format: commons/packs/design/HANDOFF.md): `target:` (site|venture|client-bi|career),
`first move:`, and the nine parts tokens, tokens-css, design-md, component, motion-spec, a11y, breakpoints, dataset,
review, each naming an existing path under <dir>; optional `site:` (a built site whose detector report says exit 0).

CLI:
  handoff.py check DIR...                  lint each handoff package (DIR/README.md) · exit 0 / 1
  handoff.py tokens FILE [--css]           validate tokens against the schema; --css prints the :root block · exit 0 / 1
  handoff.py --check                       audit row design_handoff: schema parses and names TOKEN_GROUPS, the fixture
                                           tokens validate, commons/packs/design/HANDOFF.md names every part
  handoff.py --selftest
Exit: 0 clean · 1 violations · 2 usage.
"""
import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCHEMA = ROOT / "commons" / "schema" / "design_tokens.schema.json"
TOKEN_GROUPS = ("color", "font", "space", "radius")

LENSES = ("layout-typography", "motion", "accessibility", "detector")
VERDICTS = ("ship", "fix-then-ship", "rework")
PLACEHOLDER = re.compile(r"^\s*(tbd|todo|tbc|\?+|-+|n/?a|none|unknown|<[^>]*>|\.\.\.|…)?\s*$", re.I)
FINDING = re.compile(r"^\s*[-*]\s*\[([a-z-]+)\]\s*(.*)$")
SEV = re.compile(r"^\((P[0-2])\)\s*")
EVIDENCE = re.compile(r"\s[—-]{1,2}\s*evidence:\s*(\S.*)$", re.I)
SKIPPED = re.compile(r"^skipped\s*[—-]{1,2}\s*reason:\s*(\S.*)$", re.I)
SEP = "·"
MOTION_SOURCES = ("review-animations", "animation-performance")
SPEC_COLS = ("element", "trigger", "property", "duration", "curve", "reduced-motion")
CURVE = re.compile(r"^(cubic-bezier\(\s*-?[\d.]+\s*,\s*-?[\d.]+\s*,\s*-?[\d.]+\s*,\s*-?[\d.]+\s*\)|"
                   r"spring\([^)]*\d[^)]*\)|steps\(\s*\d+[^)]*\)|linear|ease|ease-in|ease-out|ease-in-out)$", re.I)
DURATION = re.compile(r"\b\d+(\.\d+)?\s*ms\b", re.I)
TARGETS = ("site", "venture", "client-bi", "career")
HANDOFF_PARTS = ("tokens", "tokens-css", "design-md", "component", "motion-spec", "a11y", "breakpoints", "dataset", "review")
CONTRAST_MIN = {"body": 4.5, "large": 3.0, "ui": 3.0}


def sections(text):
    """{heading: [non-empty content lines]} for `## ` headings (HTML comments dropped)."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    out, cur = {}, None
    for ln in text.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", ln)
        if m:
            cur = m.group(1).strip()
            out.setdefault(cur, [])
            continue
        if cur is not None and ln.strip():
            out[cur].append(ln.strip())
    return out


def lint_review(text):
    errs = []
    m = re.search(r"^verdict:\s*(\S+)", text, re.M | re.I)
    verdict = m.group(1).lower() if m else None
    if verdict is None:
        errs.append("no `verdict:` line (one merged verdict: %s)" % "|".join(VERDICTS))
    elif verdict not in VERDICTS:
        errs.append("verdict %r not in %s" % (verdict, "|".join(VERDICTS)))
    sec = sections(text)
    if "Findings" not in sec:
        errs.append("no `## Findings` section")
        return errs
    seen, p0 = set(), 0
    for ln in sec["Findings"]:
        fm = FINDING.match(ln)
        if not fm:
            if ln.startswith(("-", "*")):
                errs.append("finding without a [lens] tag: %.70s" % ln)
            continue
        lens, rest = fm.group(1), fm.group(2).strip()
        if lens not in LENSES:
            errs.append("unknown lens [%s] (lenses: %s)" % (lens, ", ".join(LENSES)))
            continue
        seen.add(lens)
        if SKIPPED.match(rest):
            continue
        sm = SEV.match(rest)
        if sm:
            p0 += sm.group(1) == "P0"
        if not EVIDENCE.search(" " + rest):
            errs.append("[%s] finding names no evidence (add ` — evidence: <file:line|selector|region|measured value>`): %.60s" % (lens, rest))
    for lens in LENSES:
        if lens not in seen:
            errs.append("lens [%s] did not report (findings, `no findings — evidence:`, or `skipped — reason:`)" % lens)
    if p0 and verdict == "ship":
        errs.append("verdict ship with %d P0 finding(s)" % p0)
    return errs


def _line(text, key):
    m = re.search(r"^%s:\s*(\S.*?)\s*$" % re.escape(key), text, re.M | re.I)
    return m.group(1).strip().strip("`") if m else None


def _table(text):
    """(header cells lower-cased, [row cells]) of the first markdown table whose header names every SPEC_COLS column."""
    lines = [l.strip() for l in re.sub(r"<!--.*?-->", "", text, flags=re.S).splitlines()]
    for i, l in enumerate(lines):
        if not (l.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[i + 1])):
            continue
        head = [c.strip().lower() for c in l.strip("|").split("|")]
        if not all(any(col in h for h in head) for col in SPEC_COLS):
            continue
        rows = []
        for r in lines[i + 2:]:
            if not r.startswith("|"):
                break
            rows.append([c.strip() for c in r.strip("|").split("|")])
        return head, rows
    return None, []


def lint_spec_table(text, where="spec"):
    errs = []
    head, rows = _table(text)
    if head is None:
        return ["%s: no table whose header names %s" % (where, ", ".join(SPEC_COLS))]
    if not rows:
        return ["%s: the spec table has no rows" % where]
    idx = {col: next(j for j, h in enumerate(head) if col in h) for col in SPEC_COLS}
    for n, r in enumerate(rows, 1):
        cell = lambda col: r[idx[col]].strip("` ") if idx[col] < len(r) else ""
        label = cell("element") or "row %d" % n
        for col in ("element", "trigger", "property"):
            if PLACEHOLDER.match(cell(col)):
                errs.append("%s row %d: `%s` is empty or a placeholder" % (where, n, col))
        if not DURATION.search(cell("duration")):
            errs.append("%s %s: duration %r names no value in ms" % (where, label, cell("duration")))
        if not CURVE.match(cell("curve")):
            errs.append("%s %s: curve %r is not cubic-bezier(...)/spring(...)/steps(...)/linear/ease*" % (where, label, cell("curve")))
        if PLACEHOLDER.match(cell("reduced-motion")):
            errs.append("%s %s: no reduced-motion fallback" % (where, label))
    return errs


def lint_motion(text, spec_only=False):
    if spec_only:
        errs = lint_spec_table(text)
        if not _line(text, "target"):
            errs.append("no `target:` line (the station or surface the spec is for)")
        return errs
    errs = []
    m = re.search(r"^animated elements:\s*(\d+)\b", text, re.M | re.I)
    if not m:
        errs.append("no `animated elements: N` inventory line (the denominator of the review)")
    sec = sections(text)
    if "Findings" not in sec:
        errs.append("no `## Findings` section")
    else:
        seen = set()
        for ln in sec["Findings"]:
            fm = FINDING.match(ln)
            if not fm:
                if ln.startswith(("-", "*")):
                    errs.append("finding without a [source] tag: %.70s" % ln)
                continue
            src, rest = fm.group(1), fm.group(2).strip()
            if src not in MOTION_SOURCES:
                errs.append("unknown source [%s] (sources: %s)" % (src, ", ".join(MOTION_SOURCES)))
                continue
            seen.add(src)
            if SKIPPED.match(rest):
                continue
            if not EVIDENCE.search(" " + rest):
                errs.append("[%s] finding names no evidence: %.60s" % (src, rest))
        for src in MOTION_SOURCES:
            if src not in seen:
                errs.append("source [%s] did not report" % src)
    if "Spec" not in sec:
        errs.append("no `## Spec` section (the plan as a spec table: %s)" % ", ".join(SPEC_COLS))
    elif not (m and m.group(1) == "0" and any(re.search(r"no change", l, re.I) for l in sec["Spec"])):
        errs += lint_spec_table("\n".join(sec["Spec"]), "Spec")
    return errs


def lint_handoff(path, root):
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    errs = []
    tgt = (_line(text, "target") or "").lower()
    if tgt not in TARGETS:
        errs.append("target %r is not one of %s" % (tgt, "|".join(TARGETS)))
    if not _line(text, "first move"):
        errs.append("no `first move:` line (what the target station runs first)")
    parts = {}
    for part in HANDOFF_PARTS:
        ref = _line(text, part)
        if not ref:
            errs.append("part `%s:` missing" % part)
            continue
        f = path.parent / ref
        if not f.exists():
            errs.append("part %s: %s does not exist under %s" % (part, ref, path.parent.relative_to(root).as_posix()))
            continue
        parts[part] = f
        body = f.read_text(encoding="utf-8", errors="replace") if f.is_file() else ""
        if part == "review" and f.is_file():
            if lint_review(body):
                errs.append("part review: %s fails the review lint" % ref)
            elif re.search(r"^verdict:\s*rework", body, re.M | re.I):
                errs.append("part review: verdict rework is not handed off")
        if part == "motion-spec" and f.is_file() and lint_motion(body, True):
            errs.append("part motion-spec: %s fails the spec lint" % ref)
        if part == "a11y" and f.is_file():
            errs += ["part a11y: " + e for e in lint_a11y(body)]
        if part == "breakpoints" and f.is_file():
            errs += ["part breakpoints: " + e for e in lint_breakpoints(body)]
        if part == "design-md" and f.is_file():
            errs += ["part design-md: " + e for e in lint_design_md(body)]
    site = _line(text, "site")   # R-studio-site: a built site's detector verdict must be clean
    if site:
        sd = (path.parent / site).resolve()
        rep = sd / "detector-report.txt"
        if not (sd / "index.html").is_file():
            errs.append("site: %s has no index.html (build it on station studio: python3 tools/station/site_scaffold.py)" % site)
        elif not rep.is_file() or not re.search(r"^verdict: exit 0\b", rep.read_text(encoding="utf-8", errors="replace"), re.M):
            errs.append("site: %s detector-report.txt does not say `verdict: exit 0`" % site)
    if "tokens" in parts and "tokens-css" in parts and parts["tokens"].is_file():
        errs += ["part tokens: " + e for e in lint_tokens(parts["tokens"], parts["tokens-css"])]
    return errs


def token_leaves(obj, prefix=""):
    """{"color": {"ink": "#111"}} -> {"color-ink": "#111"} (a leaf is a str/number, or a {"value": ...} object)."""
    out = {}
    for k, v in (obj or {}).items():
        if k.startswith(("$", "_")):
            continue
        name = (prefix + "-" + k) if prefix else k
        if isinstance(v, dict) and "value" in v and not isinstance(v["value"], dict):
            out[name] = str(v["value"])
        elif isinstance(v, dict):
            out.update(token_leaves(v, name))
        else:
            out[name] = str(v)
    return out


def tokens_css(tokens):
    leaves = token_leaves(tokens)
    return ":root {\n" + "".join("  --%s: %s;\n" % (k, v) for k, v in leaves.items()) + "}\n"


def lint_tokens(tok_path, css_path):
    import json
    errs = []
    try:
        tokens = json.loads(tok_path.read_text(encoding="utf-8"))
    except ValueError as e:
        return ["%s is not JSON (%s)" % (tok_path.name, e)]
    leaves = token_leaves(tokens)
    for group in ("color", "font", "space", "radius"):
        if not any(k == group or k.startswith(group + "-") for k in leaves):
            errs.append("no `%s` tokens" % group)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from detector import color as DC
    for k, v in leaves.items():
        if k.startswith("color-") and DC.parse_color(v) is None:
            errs.append("token %s = %r is not a colour" % (k, v))
    css = css_path.read_text(encoding="utf-8", errors="replace") if css_path.is_file() else ""
    missing = [k for k in leaves if not re.search(r"--%s\s*:" % re.escape(k), css)]
    if missing:
        errs.append("tokens-css lacks %d of %d token(s) as custom properties: %s" % (len(missing), len(leaves), ", ".join(missing[:5])))
    return errs


def lint_a11y(text):
    """A contrast table (fg | bg | use | ratio) re-measured with contrast.py: each claimed ratio must match the
    arithmetic (±0.05) and pass its use (body 4.5, large 3.0, ui 3.0); plus focus and reduced-motion notes."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import contrast
    errs, rows = [], 0
    for ln in text.splitlines():
        cells = [c.strip().strip("`") for c in ln.strip().strip("|").split("|")] if ln.strip().startswith("|") else []
        if len(cells) < 4 or not re.match(r"^#?[0-9a-fA-F]{3,6}$", cells[0] or ""):
            continue
        rows += 1
        fg, bg, use, claimed = cells[0], cells[1], cells[2].lower(), cells[3]
        try:
            ratio = contrast.ratio(fg, bg)
        except Exception as e:  # contrast.Bad
            errs.append("row %s on %s: %s" % (fg, bg, e))
            continue
        m = re.search(r"([\d.]+)", claimed)
        if not m or abs(float(m.group(1)) - ratio) > 0.05:
            errs.append("row %s on %s claims %s, contrast.py measures %.2f:1" % (fg, bg, claimed, ratio))
        if use not in CONTRAST_MIN:
            errs.append("row %s on %s: use %r not body|large|ui" % (fg, bg, use))
        elif ratio < CONTRAST_MIN[use]:
            errs.append("row %s on %s fails %s (%.2f < %.1f)" % (fg, bg, use, ratio, CONTRAST_MIN[use]))
    if rows == 0:
        errs.append("no contrast rows (| fg | bg | use | ratio |), measured with tools/design/contrast.py")
    low = text.lower()
    for need in ("focus", "reduced-motion"):
        if need not in low:
            errs.append("no `%s` note" % need)
    return errs


def lint_breakpoints(text):
    rows = [l for l in text.splitlines() if l.strip().startswith("|") and re.search(r"\b\d{3,4}\s*px\b", l)]
    return [] if len(rows) >= 2 else ["fewer than 2 breakpoint rows naming a px width (| name | min-width px | layout |)"]


def lint_design_md(text):
    errs = []
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return ["no YAML frontmatter (impeccable DESIGN.md shape: colors, typography, rounded)"]
    front = m.group(1)
    for key in ("colors", "typography"):
        if not re.search(r"^%s:" % key, front, re.M):
            errs.append("frontmatter has no `%s:`" % key)
    if not re.search(r"^#\s+\S", text[m.end():], re.M):
        errs.append("no prose heading after the frontmatter")
    return errs


GOOD_REVIEW = """# Review: invoice approval screen v2
verdict: fix-then-ship
## Findings
- [layout-typography] (P1) amount column is left-aligned, digits do not line up — evidence: .amount td, screenshot region 640x210
- [motion] no findings — evidence: no transitions in the build (grep transition: 0 hits)
- [accessibility] (P1) #777 on #fff for secondary labels is 4.48:1 — evidence: python3 tools/design/contrast.py '#777' '#fff'
- [detector] skipped — reason: impeccable engine not bootstrapped (telemetry row verified:false)
"""

GOOD_SPEC = """# Motion spec: modal open
target: venture
| element | trigger | property | duration | curve | reduced-motion |
|---|---|---|---|---|---|
| .modal | open | opacity, transform: scale(0.96 -> 1) | 200ms | cubic-bezier(0.23, 1, 0.32, 1) | opacity only, 150ms |
| .modal | close | opacity | 150ms | ease-out | instant (0ms) |
"""

GOOD_TOKENS = {"color": {"ink": "#1c1917", "muted": "#57534e", "surface": "#fafaf9", "accent": "#0f5132"},
               "font": {"body": "'Source Serif 4', Georgia, serif", "display": "'Archivo', 'Helvetica Neue', sans-serif"},
               "space": {"1": "4px", "2": "8px", "3": "16px", "4": "32px", "5": "64px"},
               "radius": {"sm": "4px", "md": "8px"}}

GOOD_DESIGN_MD = """---
colors:
  ink: "#1c1917"
  muted: "#57534e"
  surface: "#fafaf9"
  accent: "#0f5132"
typography:
  body: "Source Serif 4"
  display: "Archivo"
rounded:
  sm: 4px
  md: 8px
---
# Demo design system

Ink on warm stone; one green accent for actions only.
"""

GOOD_A11Y = """# Accessibility notes
| fg | bg | use | ratio |
|---|---|---|---|
| #1c1917 | #fafaf9 | body | 16.74:1 |
| #57534e | #fafaf9 | body | 7.30:1 |
| #fafaf9 | #0f5132 | ui | 8.96:1 |

- focus: 2px solid accent outline, 2px offset, on every link and button
- reduced-motion: reveal and hover lifts are removed under prefers-reduced-motion: reduce
"""

GOOD_BREAKPOINTS = """# Breakpoints
| name | min-width px | layout |
|---|---|---|
| base | 0px | single column, 16px gutters |
| wide | 768px | two columns for services |
| desk | 1120px | content capped at 68ch, 32px gutters |
"""

GOOD_HANDOFF_README = """target: venture
first move: skill design-handoff consumer: copy tokens.css and components/ into the product
tokens: tokens.json
tokens-css: tokens.css
design-md: DESIGN.md
component: components/
motion-spec: motion.spec.md
a11y: a11y.md
breakpoints: breakpoints.md
dataset: dataset.json
review: review.md
"""


def schema_errors(tokens):
    """Validate a token object against commons/schema/design_tokens.schema.json (kit validator subset)."""
    sys.path.insert(0, str(ROOT / "tools" / "gov"))
    import _gov
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    errs = _gov.validate(tokens, schema)
    leaves = token_leaves(tokens) if isinstance(tokens, dict) else {}
    for group in TOKEN_GROUPS:
        if isinstance(tokens, dict) and group in tokens and not any(k.startswith(group + "-") or k == group for k in leaves):
            errs.append("$.%s: group has no leaf" % group)
    return errs


def kit_check():
    viol = []
    try:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        if tuple(schema.get("required") or ()) != TOKEN_GROUPS:
            viol.append("%s required %s != TOKEN_GROUPS %s" % (SCHEMA.name, schema.get("required"), TOKEN_GROUPS))
    except (OSError, ValueError) as e:
        viol.append("%s unreadable (%s)" % (SCHEMA.name, e))
    fx = HERE / "fixtures" / "tokens.json"
    try:
        viol += ["fixtures/tokens.json: " + e for e in schema_errors(json.loads(fx.read_text(encoding="utf-8")))]
    except (OSError, ValueError) as e:
        viol.append("fixtures/tokens.json unreadable (%s)" % e)
    doc = ROOT / "commons" / "packs" / "design" / "HANDOFF.md"
    text = doc.read_text(encoding="utf-8") if doc.is_file() else ""
    for part in ("target",) + HANDOFF_PARTS:
        if not re.search(r"^%s:" % re.escape(part), text, re.M):
            viol.append("commons/packs/design/HANDOFF.md does not document part `%s:`" % part)
    print("design_handoff: %d violation(s) %s 0 worklist %s denominator %d" % (len(viol), SEP, SEP, 2 + 1 + len(HANDOFF_PARTS)))
    for v in viol:
        print("  VIOLATION " + v)
    return 1 if viol else 0


def selftest():
    import contextlib
    import io
    cases = 0
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert tuple(schema["required"]) == TOKEN_GROUPS, ("schema and TOKEN_GROUPS agree", schema["required"]); cases += 1
    assert schema_errors(GOOD_TOKENS) == [], schema_errors(GOOD_TOKENS); cases += 1
    bad = dict(GOOD_TOKENS); bad.pop("radius")
    assert any("radius" in e for e in schema_errors(bad)); cases += 1
    assert any("radius" in e for e in schema_errors(dict(GOOD_TOKENS, radius={}))); cases += 1
    assert token_leaves({"color": {"ink": {"value": "#111"}, "$type": "color"}, "_note": "x"}) == {"color-ink": "#111"}; cases += 1
    assert "--color-ink: #1c1917;" in tokens_css(GOOD_TOKENS); cases += 1
    assert lint_review(GOOD_REVIEW) == [], lint_review(GOOD_REVIEW); cases += 1
    assert lint_motion(GOOD_SPEC, True) == [], lint_motion(GOOD_SPEC, True); cases += 1
    assert lint_a11y(GOOD_A11Y) == [], lint_a11y(GOOD_A11Y); cases += 1
    assert any("claims" in e for e in lint_a11y(GOOD_A11Y.replace("16.74:1", "12.00:1"))); cases += 1
    assert any("fails body" in e for e in lint_a11y(GOOD_A11Y.replace("| #57534e | #fafaf9 | body | 7.30:1 |", "| #777777 | #ffffff | body | 4.48:1 |"))); cases += 1
    assert lint_breakpoints(GOOD_BREAKPOINTS) == [] and lint_breakpoints("# none\n"); cases += 1
    assert lint_design_md(GOOD_DESIGN_MD) == [] and lint_design_md("# no front\n"); cases += 1
    with tempfile.TemporaryDirectory() as t:
        h = Path(t) / "hand"
        (h / "components").mkdir(parents=True)
        (h / "components" / "Card.html").write_text("<div></div>\n", encoding="utf-8")
        (h / "tokens.json").write_text(json.dumps(GOOD_TOKENS), encoding="utf-8")
        (h / "tokens.css").write_text(tokens_css(GOOD_TOKENS), encoding="utf-8")
        (h / "DESIGN.md").write_text(GOOD_DESIGN_MD, encoding="utf-8")
        (h / "motion.spec.md").write_text(GOOD_SPEC, encoding="utf-8")
        (h / "a11y.md").write_text(GOOD_A11Y, encoding="utf-8")
        (h / "breakpoints.md").write_text(GOOD_BREAKPOINTS, encoding="utf-8")
        (h / "dataset.json").write_text("[]\n", encoding="utf-8")
        (h / "review.md").write_text(GOOD_REVIEW, encoding="utf-8")
        (h / "README.md").write_text(GOOD_HANDOFF_README, encoding="utf-8")
        assert lint_handoff(h / "README.md", t) == [], lint_handoff(h / "README.md", t); cases += 1
        (h / "README.md").write_text(GOOD_HANDOFF_README.replace("target: venture", "target: career"), encoding="utf-8")
        assert lint_handoff(h / "README.md", t) == []; cases += 1
        (h / "README.md").write_text(GOOD_HANDOFF_README.replace("a11y: a11y.md\n", ""), encoding="utf-8")
        assert any("a11y" in e for e in lint_handoff(h / "README.md", t)); cases += 1
        (h / "README.md").write_text(GOOD_HANDOFF_README.replace("target: venture", "target: nobody"), encoding="utf-8")
        assert any("target" in e for e in lint_handoff(h / "README.md", t)); cases += 1
        (h / "README.md").write_text(GOOD_HANDOFF_README, encoding="utf-8")
        (h / "tokens.css").write_text(":root {}\n", encoding="utf-8")
        assert any("custom properties" in e for e in lint_handoff(h / "README.md", t)); cases += 1
        (h / "tokens.css").write_text(tokens_css(GOOD_TOKENS), encoding="utf-8")
        (h / "review.md").write_text(GOOD_REVIEW.replace("verdict: fix-then-ship", "verdict: rework"), encoding="utf-8")
        assert any("rework" in e for e in lint_handoff(h / "README.md", t)); cases += 1
        (h / "review.md").write_text(GOOD_REVIEW, encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            assert main(["check", str(h)]) == 0; cases += 1
            assert main(["tokens", str(h / "tokens.json")]) == 0; cases += 1
        (h / "bad.json").write_text(json.dumps({"color": {"ink": "#111"}}), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            assert main(["tokens", str(h / "bad.json")]) == 1; cases += 1
    with contextlib.redirect_stdout(io.StringIO()):
        assert kit_check() == 0; cases += 1
    print("selftest OK (%d cases)" % cases)
    return 0


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("cmd", nargs="?", choices=("check", "tokens"))
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--css", action="store_true")
    ap.add_argument("--root", default=".")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.check:
        return kit_check()
    if not a.cmd or not a.paths:
        ap.print_usage()
        return 2
    bad = 0
    for p in a.paths:
        p = Path(p)
        if a.cmd == "check":
            readme = p / "README.md" if p.is_dir() else p
            if not readme.is_file():
                print("%s: no handoff README.md" % p)
                bad += 1
                continue
            root = Path(a.root).resolve()
            if root not in readme.resolve().parents:
                root = readme.resolve().parent.parent
            errs = lint_handoff(readme.resolve(), root)
        else:
            try:
                tokens = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                print("%s: unreadable (%s)" % (p, e))
                return 2
            errs = schema_errors(tokens)
            if a.css and not errs:
                sys.stdout.write(tokens_css(tokens))
        for e in errs:
            print("%s: %s" % (p, e))
        bad += bool(errs)
        if not errs and a.cmd == "check":
            print("%s: handoff OK" % p)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
