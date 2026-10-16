#!/usr/bin/env python3
"""port_map.py — generate PORT_MAP.md: every upstream impeccable rule -> our implementation -> its tests -> parity.

The upstream column names where impeccable implements the rule at pin 5bf0a069dc85 (crate file : line, function), as
read for the port; everything else is read live from our modules, tests and the parity run, so the table cannot drift
from the code: `port_map.py --check` fails when PORT_MAP.md differs from a fresh render (detect.py --selftest runs it).

  port_map.py           write PORT_MAP.md
  port_map.py --check   exit 1 when PORT_MAP.md is stale or a rule lacks an implementation or a test
"""
import contextlib
import glob
import io
import json
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from detector import registry as R, rendered, regex_engine  # noqa: E402
from detector import rules_color, rules_layout, rules_type, rules_motion_copy  # noqa: E402

C, H, F, D, B = "core/src/checks/", "html/src/", "foundation/src/", "detect/src/", "core/src/browser/"
UPSTREAM = {
    "side-tab": C + "rules.rs:301 check_borders; css_scan.rs:684/865 pseudo + inset stripe scans",
    "border-accent-on-rounded": C + "rules.rs:301 check_borders (rounded branch)",
    "overused-font": H + "page.rs:41 check_static_page_typography",
    "flat-type-hierarchy": C + "rules.rs:2274 check_flat_type_hierarchy_samples; " + H + "page.rs:109",
    "gradient-text": C + "rules.rs:818 check_colors (clip-to-text); html_patterns.rs:503 page form",
    "ai-color-palette": C + "rules.rs:818 check_colors (purple/cyan); html_patterns.rs:503 page accent",
    "cream-palette": H + "page.rs:627 check_cream_palette; " + C + "measures.rs:392 is_cream_color",
    "nested-cards": H + "page.rs:435 check_page_layout, :211 is_card_like",
    "monotonous-spacing": D + "design_system.rs + " + H + "static_engine.rs spacing collector",
    "bounce-easing": C + "rules.rs:1865 check_motion; css_scan.rs:2790 bounce_names_only_pulse",
    "pulsing-dot": C + "css_scan.rs:2890 scan_css_text_for_pulsing_dot",
    "blinking-cursor": B + "page_checks.rs blinking-cursor probe (browser only)",
    "shape-assembled-illustration": C + "html_patterns.rs:103 scan_html_for_shape_assembled_illustration",
    "organic-clip-path": C + "css_scan.rs:2360 scan_css_text_for_organic_clip_path",
    "buried-raster": C + "css_scan.rs:2561 scan_css_text_for_buried_raster + element adapter",
    "dark-glow": C + "rules.rs:2076 check_glow; css_scan.rs:160 scan_css_text_for_glow_with",
    "radial-halo": C + "css_scan.rs:345 scan_css_text_for_radial_halo_with",
    "radial-spotlight-glow": H + "adapters.rs:538 check_element_radial_spotlight; " + C + "measures.rs:373",
    "marquee": C + "css_scan.rs:2808 scan_css_text_for_marquee",
    "icon-tile-stack": C + "rules.rs:1493 check_icon_tile; " + H + "adapters.rs:1269",
    "italic-serif-display": C + "rules.rs:1616 check_italic_serif, :1576 resolve_serif",
    "hero-eyebrow-chip": C + "rules.rs:1747 check_hero_eyebrow",
    "kicker-above-heading": C + "rules.rs:1827 check_kicker_above_heading; text_rules.rs:151",
    "numbered-section-labels": C + "text_rules.rs:277 check_numbered_section_labels",
    "em-dash-overuse": C + "text_rules.rs:517 check_em_dash_overuse",
    "marketing-buzzword": D + "detect_text.rs run_text_content_analyzers (buzzword list)",
    "aphoristic-cadence": D + "detect_text.rs run_text_content_analyzers (aphorism patterns)",
    "oversized-h1": C + "measures.rs:442 check_oversized_h1",
    "extreme-negative-tracking": C + "text_rules.rs:324 tracking_is_crushed; " + H + "quality.rs:437",
    "broken-image": H + "adapters.rs check_element_broken_image",
    "script-error": "core/src/script_errors.rs + " + B + "driver.rs pageerror capture (browser only)",
    "content-hidden-at-rest": C + "measures.rs:1055 check_content_hidden_at_rest (browser only)",
    "edge-flush-cards": B + "page_checks.rs edge-flush cards (browser only)",
    "text-occlusion": B + "visual.rs / text_layers.rs occlusion (browser only)",
    "first-viewport-column-overflow": B + "page_checks.rs first-viewport columns (browser only)",
    "gray-on-color": C + "rules.rs:1293 contrast_findings, :457 find_gray_on_color_bg",
    "low-contrast": C + "rules.rs:1293 contrast_findings, :969 check_colors_deduped_shaped; " + H + "adapters.rs:970",
    "line-length": B + "quality.rs measured line boxes (browser only)",
    "cramped-padding": H + "quality.rs:437 check_quality (flush form); " + B + "quality.rs (inset form)",
    "body-text-viewport-edge": B + "page_checks.rs viewport-edge (browser only)",
    "tight-leading": H + "quality.rs:437 check_quality; " + F + "rules/text.rs:132",
    "skipped-heading": H + "quality.rs:895 check_page_quality_from_doc",
    "heading-rhythm": B + "page_checks.rs heading rhythm (browser only)",
    "justified-text": H + "quality.rs:437 check_quality; " + F + "rules/text.rs:272",
    "tiny-text": H + "quality.rs:437 check_quality",
    "undersized-ui-text": H + "quality.rs:437 check_quality; " + F + "rules/text.rs:155",
    "all-caps-body": H + "quality.rs:437 check_quality; " + C + "measures.rs:1114",
    "wide-tracking": H + "quality.rs:437 check_quality",
    "text-overflow": B + "element_checks.rs overflow (browser only)",
    "repeated-container-text": H + "page.rs:509 check_repeated_container_text_from_doc",
    "clipped-overflow-container": H + "adapters.rs:1801 check_element_clipped_overflow",
    "design-system-font": D + "design_system.rs check_source_design_system / is_allowed_font",
    "design-system-color": D + "design_system.rs is_allowed_color_raw",
    "design-system-radius": D + "design_system.rs is_allowed_radius_raw",
    "design-system-font-size": D + "design_system.rs (font-size ramp, source scan)",
    "gpt-thin-border-wide-shadow": C + "measures.rs:970 check_gpt_thin_border_wide_shadow",
    "repeating-stripes-gradient": C + "html_patterns.rs:358 repeating_gradient_repeats",
    "codex-grid-background": C + "css_scan.rs:264 scan_css_text_for_grid_background",
    "theater-slop-phrase": D + "detect_text.rs run_text_content_analyzers (theater head words)",
}
COUNT_REASONS = {
    ("linked-url-patterns.html", "low-contrast"): "deliberate: upstream applies every @media/@container block; ours reads the page at rest on a desktop viewport, so `@container (width > 2000px)` and `@media (max-width: 1px)` stripes do not paint (one ground differs)",
    ("low-contrast-decorative.html", "low-contrast"): "upstream reports the same ink on the same ground twice (`.author-signature` and `.fine-print`, both #b0b0b0 on #ffffff); our per-document dedupe keeps one",
}
MODULES = {"rules_color": rules_color, "rules_layout": rules_layout, "rules_type": rules_type,
           "rules_motion_copy": rules_motion_copy}


def parity_stats():
    from detector.tests import parity
    with tempfile.TemporaryDirectory() as t:
        with contextlib.redirect_stdout(io.StringIO()):
            parity.main(["--json", str(Path(t) / "p.json")])
        return json.loads((Path(t) / "p.json").read_text(encoding="utf-8"))


def render():
    tests = {Path(f).stem: Path(f).read_text(encoding="utf-8") for f in sorted(glob.glob(str(HERE / "tests" / "test_*.py")))}
    par = parity_stats()
    lines, gaps = [], []
    for rid, row in R.RULES.items():
        ours = None
        for name, m in MODULES.items():
            if rid in m.RULES:
                ours = "`%s.%s`" % (name, m.RULES[rid].__name__)
        if rid in rendered.RENDERED_RULES:
            ours = "`rendered.rules` (Playwright, optional)"
        engines = ["rendered" if rid in rendered.RENDERED_RULES else "static"]
        if rid in regex_engine.RULE_IDS:
            engines.append("regex")
        tnames = []
        for stem, src in tests.items():
            for m in re.finditer(r"    def (test_\w+)\(self[^)]*\):\n((?:(?!    def ).*\n?)*)", src):
                if rid in m.group(0):
                    tnames.append("%s.%s" % (stem, m.group(1)))
        key = rid.replace("-", "_")
        tnames.sort(key=lambda t: (key not in t, t))
        p = par["per_rule"].get(rid)
        pc = "%d / %d / %d" % (p["tp"], len(p["fn"]), len(p["fp"])) if p else "no gold hits"
        if not ours:
            gaps.append("%s: no implementation" % rid)
        if not tnames:
            gaps.append("%s: no test" % rid)
        shown = ", ".join("`%s`" % t for t in tnames[:2]) + (" +%d" % (len(tnames) - 2) if len(tnames) > 2 else "")
        lines.append("| `%s` | %s · %s | %s | %s | %s | %s | %s |" % (
            rid, row["category"], row["severity"], UPSTREAM.get(rid, "?"), ours or "MISSING", " + ".join(engines), pc, shown or "MISSING"))
    static = sum(1 for r in R.RULES if r not in rendered.RENDERED_RULES)
    head = """# PORT_MAP — impeccable detector rules -> studio detector (Python)

<!-- generated by tools/design/detector/port_map.py; do not edit by hand (detect.py --selftest fails when stale) · rule R-design-detector -->
Upstream: `pbakaus/impeccable` at `5bf0a069dc857e1b5f4b090e004d9d5b231416ca` (Apache-2.0), Rust crates under
`crates/` (`core/src/checks/`, `html/src/`, `foundation/src/`, `detect/src/`, `core/src/browser/`). Rule ids, names,
descriptions, categories and severities are upstream's (`registry.json`); every check is our own Python. Credit and
license: repo `NOTICE.md`. The engine was read from a bare clone at the pin, never run.

Rules: **%d** of %d ported · %d static (HTML engine; %d also in the line-regex engine for css/jsx/tsx/vue/svelte/astro)
· %d rendered (need an already-installed Playwright; otherwise NOT RUN, never counted clean).

Parity oracle: upstream's own fixtures (`tests/upstream/fixtures/`, %d) against upstream's own goldens
(`tests/upstream/expected.json`, `detect --no-config --json`, static engine). **Rule sets identical on %d / %d
fixtures.** Column "tp / fn / fp" counts fixtures where both fire / only upstream fires / only we fire. Rendered rules
have no static goldens (upstream's static engine never emits them); their tests run the probe on the upstream browser
fixtures and on hand-built measures.

| upstream rule | category · severity | upstream implementation | ours | engines | parity tp / fn / fp | tests |
|---|---|---|---|---|---|---|
""" % (len(R.RULES) - len([g for g in gaps if "implementation" in g]), len(R.RULES), static,
       len(regex_engine.RULE_IDS), len(rendered.RENDERED_RULES), par["total"], par["agree"], par["total"])
    tail = """
## Deliberate differences from upstream
- `@media` blocks: upstream's static cascade applies every block whatever its query; ours reads the page at rest on a
  desktop viewport (print, `prefers-color-scheme: dark`, `prefers-reduced-motion: reduce` and `max-width` < 1024px
  blocks are skipped). The phone viewport is covered by the rendered pass (390x844) when a browser exists.
- Named colours: the full CSS table (upstream resolves 39 names).
- No telemetry, no network, no roll request: the rendered probe aborts every request that is not `file:` or `data:`.
- Output: findings plus our own scores (0-100 per category, `score.py`) and a verdict exit code (0 pass, 1 fail at
  `--fail-on`, 2 usage). Upstream's CLI exits 2 on findings and 1 on scan errors.
- Root-absolute stylesheet hrefs (`/css/x.css`) resolve against ancestor folders (no server root offline).
- Modern sizing: `env(safe-area-inset-*)` reads as 0 (or its fallback) and `clamp()/min()/max()` arguments may be
  expressions (`1.5rem + 2vw`), so fluid type and notch-safe padding are measured instead of read as 0px
  (regression tests `tests/test_css_lengths.py`, found by the landing-sample run).
- Rendered pass: Python Playwright when installed, else node's; bundled Chromium, else an installed Chrome or Edge
  (`channel`). Without either, three rendered rules (line-length, body-text-viewport-edge, content-hidden-at-rest)
  get a static approximation: advisory only, `engine: static-approx`, snippet prefixed "static approximation", and
  the rule still reads NOT RUN in the summary, so a static pass is never presented as rendered parity.
"""
    exact, cells, mism = 0, 0, []
    for name, r in sorted(par["fixtures"].items()):
        w, g = r["want"], r["got"]
        exact += w == g
        for k in sorted(set(w) | set(g)):
            if w.get(k, 0) != g.get(k, 0):
                why = COUNT_REASONS.get((name, k))
                if not why:
                    gaps.append("count mismatch %s %s without a recorded reason" % (name, k))
                mism.append("| `%s` | `%s` | %d | %d | %s |" % (name, k, w.get(k, 0), g.get(k, 0), why or "UNEXPLAINED"))
    gw = sum(sum(r["want"].values()) for r in par["fixtures"].values())
    go = sum(sum(r["got"].values()) for r in par["fixtures"].values())
    counts = """
## Count-level parity (every mismatch, with its reason)
Finding counts identical on **%d / %d** fixtures; total findings upstream %d, ours %d.

| fixture | rule | upstream | ours | reason |
|---|---|---|---|---|
%s
""" % (exact, par["total"], gw, go, "\n".join(mism) or "| - | - | - | - | none |")
    return head + "\n".join(lines) + "\n" + counts + tail, gaps


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    text, gaps = render()
    path = HERE / "PORT_MAP.md"
    if argv == ["--check"]:
        bad = list(gaps)
        if not path.is_file() or path.read_text(encoding="utf-8") != text:
            bad.append("PORT_MAP.md is stale: run python3 tools/design/detector/port_map.py")
        for b in bad:
            print("port_map: " + b)
        print("port_map: %d issue(s) · %d rules" % (len(bad), len(R.RULES)))
        return 1 if bad else 0
    path.write_text(text, encoding="utf-8")
    print("port_map: wrote %s (%d rules, %d gap(s))" % (path, len(R.RULES), len(gaps)))
    return 1 if gaps else 0


if __name__ == "__main__":
    sys.exit(main())
