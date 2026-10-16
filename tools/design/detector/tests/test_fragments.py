"""Component fragments (no doctype/html/body), as a handoff's components/ folder holds them: the stylesheet beside
the fragment applies, html/body rules reach it, and the rendered pass does not run on a page that does not exist.
Found by the landing-sample run (2026-10-16): a bare components/ scan exited 1 on black default text."""
import tempfile
import unittest
from pathlib import Path

from detector import detect, engine, registry as R


class Fragments(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        d = Path(self.t.name)
        (d / "components.css").write_text("body { color: #1c1917; background: #fafaf9; font-size: 17px; line-height: 1.6 }", encoding="utf-8")
        (d / "hero.html").write_text("<section><h2>Plain numbers</h2><p>Monthly reporting for small finance teams.</p></section>", encoding="utf-8")
        self.d = d

    def tearDown(self):
        self.t.cleanup()

    def test_sibling_stylesheet_and_body_rules_apply(self):
        ctx = engine.Context(self.d / "hero.html", (self.d / "hero.html").read_text(encoding="utf-8"), "html")
        p = [n for n in ctx.doc.iter() if n.tag == "p"][0]
        self.assertEqual(p.style.get("color"), "#1c1917")
        self.assertFalse(ctx.full_page)

    def test_design_system_color_clean_with_context(self):
        design = {"colors": {"ink": "#1c1917", "surface": "#fafaf9"}}
        findings, _, _ = engine.scan_file(self.d / "hero.html", R.RULES, design)
        self.assertEqual([f for f in findings if f["rule"] == "design-system-color"], [])

    def test_off_palette_fragment_still_flagged(self):
        (self.d / "components.css").write_text("body { color: #6d28d9 }", encoding="utf-8")
        design = {"colors": {"ink": "#1c1917", "surface": "#fafaf9"}}
        findings, _, _ = engine.scan_file(self.d / "hero.html", R.RULES, design)
        self.assertTrue([f for f in findings if f["rule"] == "design-system-color"])

    def test_rendered_pass_skips_fragments(self):
        _, _, not_run, info = detect.run([str(self.d)], rendered_mode="auto")
        self.assertIn("fragments", not_run["text-overflow"] + info["rendered"])


if __name__ == "__main__":
    unittest.main()
