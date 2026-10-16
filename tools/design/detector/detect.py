#!/usr/bin/env python3
"""detect.py — the kit's design detector (commons; built on studio): impeccable's 59 anti-pattern rules, reimplemented in stdlib Python.

owner: governance/rules.d/design.json R-design-detector (check `design_detector`; moved from studio, reconcile-01) · callers: skill design-review
(every station), studio's design-pass workflow (Detector stage + Verify) and design-review-loop (detector lens), the studio station's site_scaffold.py, studio_lint
(prototype README `detector:` reports). Port map: tools/design/detector/PORT_MAP.md. License: NOTICE.md (Apache-2.0
upstream, our own code).

Earned by: the operator's question (2026-10-16) whether studio can rate designs "with a py recreation of its rust
engine" instead of impeccable's Rust engine, whose roll request calls impeccable.style (R-studio-engine-off). Before
this the detector lens was an agent reading craft-floor.md by eye; now it is a measured, repeatable verdict.
Retires: the design-review-loop detector lens's "craft-floor Refuse list by reading" (kept as the fallback text only).

What runs: static HTML/CSS analysis for .html (parse + cascade + 50 element/page rules), upstream's line-regex
engine for .css/.scss/.sass/.jsx/.tsx/.vue/.svelte/.astro, and — only when node + Playwright are ALREADY installed —
a rendered pass (desktop 1280x800 + phone 390x844, every non-file request aborted) for the layout rules a static
read cannot see. Without a browser those rules are NOT RUN (listed, never counted clean). No telemetry, no network.

CLI:
  detect.py PATH... [--json FILE|-] [--report FILE] [--fail-on error|warning|advisory|none] [--min-score N]
                    [--design DESIGN.md] [--rendered auto|on|off] [--shot PNG] [--scope type,layout]
                    [--no-advisory] [--quiet]
  detect.py --list-rules
  detect.py --check        audit row design_detector: PORT_MAP fresh, every rule implemented + tested, parity floor
  detect.py --selftest
Exit: 0 pass (no finding at/above --fail-on, default warning; score >= --min-score) · 1 fail · 2 usage/unreadable.
"""
import argparse
import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from detector import engine, rendered, score  # noqa: E402
from detector import registry as R  # noqa: E402

VERSION = "studio-detector 1.0 (port of pbakaus/impeccable@5bf0a069dc85 rules)"
ROOT = HERE.parents[2]


def relpath(p):
    p = Path(p).resolve()
    try:
        return p.relative_to(ROOT).as_posix()
    except ValueError:
        return p.as_posix()


def run(paths, design_path=None, rendered_mode="auto", shot=None, scopes=None, no_advisory=False):
    files = engine.collect(paths)
    if not files:
        raise FileNotFoundError("nothing scannable under %s" % ", ".join(map(str, paths)))
    design = engine.load_design(paths[0], design_path)
    findings, ran, not_run = [], set(), {}
    br_ok, br_why = (False, "--rendered off") if rendered_mode == "off" else rendered.available()
    if rendered_mode == "on" and not br_ok:
        raise RuntimeError("--rendered on but no browser: %s" % br_why)
    html_files = [f for f in files if engine.kind_of(f) == "html"]
    approx = set()
    for f in files:
        fs, r, ctx = engine.scan_file(f, R.RULES, design)
        for x in fs:
            x["file"] = relpath(f)
        findings += fs
        ran |= r
        if not br_ok and ctx.kind == "html":
            # labelled static approximations of three rendered rules: advisory, engine static-approx, rule stays NOT RUN
            for h in rendered.static_approx(ctx):
                row = R.RULES[h["rule"]]
                h.update({"name": row["name"], "category": row["category"], "file": relpath(f), "line": 0})
                findings.append(h)
                approx.add(h["rule"])
            approx |= set(rendered.APPROX_RULES)
    from detector import dom as _dom
    pages = [f for f in html_files if _dom.is_full_page(f.read_text(encoding="utf-8", errors="replace"))]
    if html_files and not pages and rendered_mode != "off":
        br_ok, br_why = False, "target holds only HTML fragments (no doctype/html/body): nothing to render"
    if pages and br_ok:
        for f in pages:
            data, why = rendered.probe(f, shot=shot if f == pages[0] else None)
            if data is None:
                br_ok, br_why = False, why
                break
            for h in rendered.rules(data):
                d = engine.norm_hit(h, None)
                row = R.RULES[d["rule"]]
                d.setdefault("severity", row["severity"])
                d.update({"name": row["name"], "category": row["category"], "file": relpath(f), "engine": "rendered"})
                findings.append(d)
        if br_ok:
            ran |= set(rendered.RENDERED_RULES)
    for rid in R.RULES:
        if rid in ran:
            continue
        if rid in rendered.RENDERED_RULES:
            not_run[rid] = ("rendered rule; browser unavailable: %s%s" % (br_why, "; static approximation ran (advisory, labelled static-approx)" if rid in approx else "")) if html_files else "rendered rule; no HTML in target"
        elif rid.startswith("design-system-"):
            not_run[rid] = "no DESIGN.md with frontmatter found (pass --design)"
        elif not html_files:
            not_run[rid] = "HTML-engine rule; target has no HTML"
        else:
            not_run[rid] = "not implemented for this file kind"
    if scopes:
        findings = [f for f in findings if set(R.RULES[f["rule"]].get("scopes") or []) & set(scopes)]
    if no_advisory:
        findings = [f for f in findings if f["severity"] != "advisory"]
    info = {"version": VERSION, "files": {relpath(f): engine.file_digest(f) for f in files},
            "rendered": ("on (%s)" % br_why) if br_ok and html_files else "off (%s)" % br_why, "design_md": bool(design),
            "static_approx": sorted(approx)}
    return findings, ran, not_run, info


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):   # Windows consoles (cp1252) must not crash on a snippet's glyph
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--json")
    ap.add_argument("--report")
    ap.add_argument("--fail-on", default="warning", choices=["error", "warning", "advisory", "none"])
    ap.add_argument("--min-score", type=int)
    ap.add_argument("--design")
    ap.add_argument("--rendered", default="auto", choices=["auto", "on", "off"])
    ap.add_argument("--shot")
    ap.add_argument("--scope")
    ap.add_argument("--no-advisory", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--list-rules", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.check:
        return check()
    if a.list_rules:
        for rid, row in R.RULES.items():
            kind = "rendered" if rid in rendered.RENDERED_RULES else "static"
            print("%-32s %-8s %-9s %-8s %s" % (rid, row["category"], row["severity"], kind, row["name"]))
        return 0
    if not a.paths:
        ap.print_usage(sys.stderr)
        return 2
    try:
        findings, ran, not_run, info = run(a.paths, a.design, a.rendered, a.shot,
                                           a.scope.split(",") if a.scope else None, a.no_advisory)
    except (FileNotFoundError, RuntimeError, OSError) as e:
        print("detect: %s" % e, file=sys.stderr)
        return 2
    summary = score.summarise(findings, R.RULES, ran, not_run)
    code, reasons = score.verdict(summary, a.fail_on, a.min_score)
    target = ", ".join(relpath(p) for p in a.paths)
    if a.json:
        out = score.dump_json(target, summary, findings, code, reasons, info)
        if a.json == "-":
            print(out)
        else:
            Path(a.json).parent.mkdir(parents=True, exist_ok=True)
            Path(a.json).write_text(out + "\n", encoding="utf-8")
    text = score.text_report(target, summary, findings, R.RULES, code, reasons)
    if a.report:
        Path(a.report).parent.mkdir(parents=True, exist_ok=True)
        Path(a.report).write_text(text + "\n", encoding="utf-8")
    if not a.quiet and a.json != "-":
        print(text)
    elif a.quiet:
        print("detect: score %d · %d finding(s) · exit %d" % (summary["score"], len(findings), code))
    return code


GOOD_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Ledger</title><style>
body { margin: 0; font-family: "Source Serif 4", Georgia, serif; font-size: 18px; line-height: 1.6; color: #1c1917; background: #ffffff; }
main { max-width: 40rem; margin: 0 auto; padding: 32px 24px; }
h1 { font-family: "Archivo", sans-serif; font-size: 44px; line-height: 1.1; font-weight: 700; margin: 0 0 24px; }
h2 { font-size: 28px; line-height: 1.2; margin: 48px 0 12px; }
p { margin: 0 0 16px; }
a { color: #0f5132; }
</style></head><body><main>
<h1>Month-end, closed by the fifth</h1>
<p>Monthly reporting for small finance teams: one ledger, reconciled weekly, with a plain summary the owner can read in five minutes.</p>
<h2>How it works</h2>
<p>We connect to your bookkeeping export, check every account against the bank, and send a short report each Monday.</p>
<p><a href="#contact">Book a call</a></p>
</main></body></html>
"""

BAD_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>AI</title><style>
body { margin: 0; font-family: Inter, sans-serif; background: #0b0b12; color: #e5e7eb; }
.hero h1 { background: linear-gradient(90deg, #8b5cf6, #06b6d4); -webkit-background-clip: text; background-clip: text; color: transparent; font-size: 16px; }
.card { border-left: 4px solid #8b5cf6; border-radius: 16px; padding: 16px; background: #151521; box-shadow: 0 0 40px rgba(139, 92, 246, 0.6); }
.muted { color: #3f3f46; }
.btn { transition: transform 600ms cubic-bezier(0.68, -0.55, 0.265, 1.55); }
</style></head><body>
<section class="hero"><h1>Supercharge your workflow with next-generation AI</h1></section>
<div class="card"><h3>Seamless</h3><p class="muted">Empower your team to streamline everything with cutting-edge, world-class tooling.</p></div>
<img src="">
</body></html>
"""


def selftest():
    import unittest
    cases = 0
    with tempfile.TemporaryDirectory() as t:
        good, bad = Path(t) / "good.html", Path(t) / "bad.html"
        good.write_text(GOOD_PAGE, encoding="utf-8")
        bad.write_text(BAD_PAGE, encoding="utf-8")
        os.environ["STUDIO_DETECTOR_BROWSER"] = "off"   # selftest stays offline-deterministic
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                rc_good = main([str(good), "--json", str(Path(t) / "g.json")])
                rc_bad = main([str(bad), "--json", str(Path(t) / "b.json")])
                rc_usage = main([str(Path(t) / "missing.html")])
        finally:
            os.environ.pop("STUDIO_DETECTOR_BROWSER", None)
        g = json.loads((Path(t) / "g.json").read_text(encoding="utf-8"))
        b = json.loads((Path(t) / "b.json").read_text(encoding="utf-8"))
        assert rc_good == 0, ("a designed page passes", g["summary"]["rules"])
        cases += 1
        assert rc_bad == 1, "a planted slop page fails"
        cases += 1
        hit = set(b["summary"]["rules"])
        for rid in ("overused-font", "gradient-text", "side-tab", "dark-glow", "marketing-buzzword", "broken-image"):
            assert rid in hit, ("planted %s not found" % rid, sorted(hit))
            cases += 1
        assert b["summary"]["score"] < g["summary"]["score"], "the slop page scores lower"
        cases += 1
        assert rc_usage == 2, "a missing target is a usage error"
        cases += 1
        assert "text-overflow" in g["summary"]["not_run"] and "browser unavailable" in g["summary"]["not_run"]["text-overflow"], \
            "rendered rules are NOT RUN (never clean) without a browser"
        cases += 1
        assert set(g["engine"]["files"]) and all(len(v) == 64 for v in g["engine"]["files"].values())
        cases += 1
    # rule-level planted good/bad cases + upstream fixture parity floor
    suite = unittest.defaultTestLoader.discover(str(HERE / "tests"), pattern="test_*.py", top_level_dir=str(HERE.parent))
    res = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    assert res.wasSuccessful(), "unit tests failed: %s" % [str(x[0]) for x in res.failures + res.errors][:5]
    cases += res.testsRun
    from detector.tests import parity
    with contextlib.redirect_stdout(io.StringIO()) as buf:
        prc = parity.main(["--min-agree", str(PARITY_FLOOR)])
    assert prc == 0, buf.getvalue().splitlines()[0]
    from detector import port_map
    with contextlib.redirect_stdout(io.StringIO()) as pbuf:
        assert port_map.main(["--check"]) == 0, pbuf.getvalue()
    cases += 1
    print("selftest OK (%d cases: CLI plants + %d rule tests + PORT_MAP fresh + %s)" % (cases, res.testsRun, buf.getvalue().splitlines()[0]))
    return 0


PARITY_FLOOR = 0.95


def check():
    """The audit row: PORT_MAP.md fresh and complete (59 rules, each implemented and tested) and upstream-fixture
    parity at or above PARITY_FLOOR. Violations name what drifted."""
    from detector import port_map
    from detector.tests import parity
    viol = []
    with contextlib.redirect_stdout(io.StringIO()) as buf:
        if port_map.main(["--check"]) != 0:
            viol += [l for l in buf.getvalue().splitlines() if not l.startswith("port_map: 0") and "issue(s)" not in l]
    with contextlib.redirect_stdout(io.StringIO()) as buf:
        if parity.main(["--min-agree", str(PARITY_FLOOR)]) != 0:
            viol.append("parity under %.2f: %s" % (PARITY_FLOOR, buf.getvalue().splitlines()[0]))
    agree = buf.getvalue().splitlines()[0]
    print("design_detector: %d violation(s) · 0 worklist · denominator %d" % (len(viol), len(R.RULES)))
    print("  " + agree)
    for v in viol:
        print("  VIOLATION " + v)
    return 1 if viol else 0


if __name__ == "__main__":
    sys.exit(main())
