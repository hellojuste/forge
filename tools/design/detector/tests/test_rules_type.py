"""Planted BAD / GOOD pages for every rule in rules_type.RULES, plus design_md.parse.

Run from tools/design:  python3 -m unittest detector.tests.test_rules_type
"""
import unittest

from detector import design_md, engine, rules_type

PAGE = "<!doctype html><html><head><style>%s</style></head><body>%s</body></html>"
LONG = "Readers move through this paragraph at an even pace because the copy runs on for a while."
DESIGN = design_md.parse("""---
typography:
  body:
    fontFamily: "Karla, sans-serif"
    fontSize: 16px
  scale:
    sm: 14px
    lg: 1.5rem
---
# Design
""")


def hits(rule, css="", body="", design=None, raw=None):
    text = raw if raw is not None else PAGE % (css, body)
    ctx = engine.Context("/tmp/fake/page.html", text, "html", design)
    out = []
    for h in rules_type.RULES[rule](ctx) or ():
        d = engine.norm_hit(h, ctx)
        if d["rule"] == rule:
            out.append(d)
    return out


class TypeRules(unittest.TestCase):
    def fires(self, rule, bad, good, **kw):
        b = hits(rule, *bad, **kw)
        g = hits(rule, *good, **kw)
        self.assertTrue(b, "%s did not fire on BAD" % rule)
        self.assertFalse(g, "%s fired on GOOD: %r" % (rule, g))
        return b

    def test_overused_font(self):
        b = self.fires("overused-font", ("body{font-family:Inter,sans-serif}", "<p>Hello</p>"),
                       ("body{font-family:Karla,sans-serif}", "<p>Hello</p>"))
        self.assertEqual(b[0]["snippet"], "Primary font: inter")

    def test_overused_font_needs_full_page(self):
        self.assertFalse(hits("overused-font", raw="<!-- <html> --><p style='font-family:Inter'>Hi</p>"))

    def test_flat_type_hierarchy(self):
        flat = '<h1 style="font-size:18px">Title</h1><h2 style="font-size:16px">Sub</h2><p style="font-size:15px">Body</p>'
        ok = '<h1 style="font-size:48px">Title</h1><h2 style="font-size:30px">Sub</h2><p style="font-size:16px">Body</p>'
        b = self.fires("flat-type-hierarchy", ("", flat), ("", ok))
        self.assertIn("Role sizes: body 15px, h2 16px, h1 18px", b[0]["snippet"])

    def test_flat_type_hierarchy_weight_is_advisory(self):
        flat = ('<h1 style="font-size:18px;font-weight:700">T</h1><h2 style="font-size:16px;font-weight:700">S</h2>'
                '<p style="font-size:15px">Body</p>')
        self.assertEqual(hits("flat-type-hierarchy", "", flat)[0].get("severity"), "advisory")

    def test_italic_serif_display(self):
        b = self.fires("italic-serif-display",
                       ("h1{font-family:'Fraunces',serif;font-style:italic;font-size:72px}", "<h1>Big italic</h1>"),
                       ("h1{font-family:'Karla',sans-serif;font-style:italic;font-size:72px}", "<h1>Big italic</h1>"))
        self.assertEqual(b[0]["snippet"], 'italic serif h1 (fraunces) at 72px "Big italic"')

    def test_hero_eyebrow_chip(self):
        css = ("h1{font-size:64px} .eb{font-size:12px;text-transform:uppercase;letter-spacing:%s}")
        body = '<p class="eb">Now in beta</p><h1>Ship it</h1>'
        b = self.fires("hero-eyebrow-chip", (css % "0.2em", body), (css % "0", body))
        self.assertTrue(b[0]["snippet"].startswith("eyebrow chip (tracked-caps)"))

    def test_kicker_above_heading(self):
        css = "h2{font-size:32px} .k{font-size:12px;text-transform:%s;letter-spacing:0.12em}"
        body = '<p class="k">Our platform</p><h2>Everything you need</h2>'
        b = self.fires("kicker-above-heading", (css % "uppercase", body), (css % "none", body))
        self.assertEqual(b[0]["snippet"], 'kicker "Our platform" above h2 "Everything you need"')

    def test_numbered_section_labels(self):
        css = "h2{font-size:32px} .n{font-size:12px;font-family:%s}"
        body = ('<section><span class="n">01</span><h2>Alpha ships</h2></section>'
                '<section><span class="n">02</span><h2>Beta earns</h2></section>')
        b = self.fires("numbered-section-labels", (css % "monospace", body), (css % "Karla", body))
        self.assertEqual(len(b), 2)
        self.assertIn("(2 on page)", b[0]["snippet"])

    def test_oversized_h1(self):
        text = "A sweeping product headline that runs on far too long to sit"
        b = self.fires("oversized-h1", ("h1{font-size:96px}", "<h1>%s</h1>" % text),
                       ("h1{font-size:48px}", "<h1>%s</h1>" % text))
        self.assertTrue(b[0]["snippet"].startswith("96px h1, 60 chars"))

    def test_skipped_heading(self):
        b = self.fires("skipped-heading", ("", "<h1>Top</h1><h3>Deep</h3>"), ("", "<h1>Top</h1><h2>Next</h2>"))
        self.assertEqual(b[0]["snippet"], '<h1> "Top" followed by <h3> "Deep" (missing h2)')
        self.assertFalse(hits("skipped-heading", "", "<h2>End</h2><footer><h4>Company</h4></footer>"))

    def test_tight_leading(self):
        b = self.fires("tight-leading", ("p{font-size:16px;line-height:1.1}", "<p>%s</p>" % LONG),
                       ("p{font-size:16px;line-height:1.5}", "<p>%s</p>" % LONG))
        self.assertEqual(b[0]["snippet"], "line-height 1.10x (need >=1.3)")

    def test_tight_leading_inherits_px(self):
        # upstream: body 16px/1.2 -> 19.2px inherited by a 14px p -> 1.37, fine
        self.assertFalse(hits("tight-leading", "body{font-size:16px;line-height:1.2} p{font-size:14px}",
                              "<p>%s</p>" % LONG))

    def test_justified_text(self):
        self.fires("justified-text", ("p{text-align:justify;width:300px}", "<p>%s</p>" % LONG),
                   ("p{text-align:justify;width:760px}", "<p>%s</p>" % LONG))

    def test_tiny_text(self):
        b = self.fires("tiny-text", ("p{font-size:10px}", "<p>%s</p>" % LONG),
                       ("p{font-size:14px}", "<p>%s</p>" % LONG))
        self.assertEqual(b[0]["snippet"], "10px body text")

    def test_undersized_ui_text(self):
        b = self.fires("undersized-ui-text", ("a{font-size:9px}", '<nav><a href="/">Pricing</a></nav>'),
                       ("a{font-size:12px}", '<nav><a href="/">Pricing</a></nav>'))
        self.assertEqual(b[0]["snippet"], '9px functional text "Pricing" (below 11px floor)')

    def test_all_caps_body(self):
        self.fires("all-caps-body", ("p{text-transform:uppercase}", "<p>%s</p>" % LONG),
                   ("p{text-transform:uppercase}", "<p>Short caps label here</p>"))

    def test_wide_tracking(self):
        b = self.fires("wide-tracking", ("p{letter-spacing:0.15em}", "<p>%s</p>" % LONG),
                       ("p{letter-spacing:0.02em}", "<p>%s</p>" % LONG))
        self.assertEqual(b[0]["snippet"], "letter-spacing: 0.15em on body text")

    def test_extreme_negative_tracking(self):
        b = self.fires("extreme-negative-tracking", ("p{letter-spacing:-0.08em}", "<p>%s</p>" % LONG),
                       ("p{letter-spacing:-0.04em}", "<p>%s</p>" % LONG))
        self.assertTrue(b[0]["snippet"].startswith("letter-spacing: -0.08em at 16px —"))

    def test_design_system_font(self):
        b = self.fires("design-system-font", ("p{font-family:Lato,sans-serif}", "<p>Hello there</p>"),
                       ("p{font-family:Karla,sans-serif}", "<p>Hello there</p>"), design=DESIGN)
        self.assertEqual(b[0]["snippet"], 'p "Hello there" uses lato; not declared in DESIGN.md typography')
        self.assertGreater(b[0]["line"], 0)
        self.assertFalse(hits("design-system-font", "p{font-family:Lato}", "<p>Hi</p>", design=None))

    def test_design_system_font_size(self):
        b = self.fires("design-system-font-size", ("p{font-size:15px}", "<p>Hi</p>"),
                       ("p{font-size:24px}", "<p>Hi</p>"), design=DESIGN)
        self.assertEqual(b[0]["snippet"], "font-size: 15px is off the DESIGN.md type ramp")
        self.assertTrue(hits("design-system-font-size", "p{font-size:clamp(13px, 2vw, 24px)}", "<p>x</p>",
                             design=DESIGN))
        self.assertFalse(hits("design-system-font-size", "p{font-size:1.2em}", "<p>x</p>", design=DESIGN))

    def test_line_length_left_to_rendered(self):
        self.assertNotIn("line-length", rules_type.RULES)


class DesignMd(unittest.TestCase):
    def test_parse_shapes(self):
        d = design_md.parse('---\n# c\ncolors:\n  primary: "#1a1a1a"  # ink\n  accent: \'#f00\'\n'
                            'typography:\n  body:\n    fontFamily: Inter, sans-serif\n    fontSize: 16px\n'
                            '    weight: 400\nrounded:\n  md: 8px\n  pill: 9999\nflag: true\nnone: ~\n---\nbody\n')
        self.assertEqual(d["colors"], {"primary": "#1a1a1a", "accent": "#f00"})
        self.assertEqual(d["typography"]["body"], {"fontFamily": "Inter, sans-serif", "fontSize": "16px",
                                                   "weight": 400})
        self.assertEqual(d["rounded"], {"md": "8px", "pill": 9999})
        self.assertIs(d["flag"], True)
        self.assertIsNone(d["none"])

    def test_no_frontmatter(self):
        self.assertIsNone(design_md.parse("# DESIGN\nno frontmatter"))
        self.assertIsNone(design_md.parse("---\nunclosed: 1\n"))
        self.assertEqual(design_md.parse("---\n---\n"), {})

    def test_numeric_font_size_off_ramp_rules(self):
        ds = rules_type.design_system(design_md.parse("---\ntypography:\n  body:\n    fontSize: 16\n---"))
        self.assertFalse(ds["has_sizes"])


if __name__ == "__main__":
    unittest.main()
