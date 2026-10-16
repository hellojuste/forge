"""rendered.py: rules(data) judged on hand-built measure dicts (no browser needed), plus browser runs over
impeccable's browser-only fixtures when Playwright is available (skipped cleanly otherwise)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from detector import rendered as RD  # noqa: E402

FIX = Path(__file__).resolve().parent / "upstream" / "fixtures"


def vp(**kw):
    base = {"width": 1280, "height": 800, "vw": 1280, "vh": 800, "errors": []}
    base.update(kw)
    return base


def ids(hits):
    return [h["rule"] if isinstance(h, dict) else h[0] for h in hits]


def snippets(hits, rule):
    return [(h["snippet"] if isinstance(h, dict) else h[1]) for h in hits if (h["rule"] if isinstance(h, dict) else h[0]) == rule]


class Judging(unittest.TestCase):
    def rules(self, desk, phone=None):
        return RD.rules({"viewports": [desk] + ([phone] if phone else [])})

    def test_script_error(self):
        bad = self.rules(vp(errors=[{"message": "TypeError: x is undefined", "stack": ""}]))
        self.assertEqual(snippets(bad, "script-error"), ["TypeError: x is undefined"])
        ad = self.rules(vp(errors=[{"message": "TypeError: y", "stack": "at https://js.nagich.co.il/core/a.js:1:2"}]))
        self.assertEqual(ad[0]["severity"], "advisory")
        self.assertIn("(third-party: Nagich)", ad[0]["snippet"])
        hyd = self.rules(vp(errors=[{"message": "Error: Minified React error #418; visit", "stack": ""}]))
        self.assertEqual(hyd[0]["severity"], "advisory")
        self.assertNotIn("script-error", ids(self.rules(vp(errors=[{"message": "load: timeout", "stack": ""}]))))

    def test_content_hidden(self):
        bad = self.rules(vp(hiddenText={"total": 1000, "hidden": 600, "samples": ["Lost section"]}))
        self.assertEqual(snippets(bad, "content-hidden-at-rest"),
                         ['60% of page text (600 of 1000 chars) stays at opacity 0 / visibility hidden after reveal handlers ran (e.g. "Lost section")'])
        self.assertNotIn("content-hidden-at-rest", ids(self.rules(vp(hiddenText={"total": 1000, "hidden": 140, "samples": []}))))

    def test_edge_flush_cards(self):
        sc = {"sel": "div.rail", "scrollW": 1600, "clientW": 800, "scrollLeft": 0, "w": 800, "h": 200, "pageTop": 100,
              "cards": [{"sel": "div.card", "left": 24, "right": 424, "lg": 24, "rg": 400},
                        {"sel": "div.card", "left": 424, "right": 824, "lg": 424, "rg": 0}]}
        self.assertEqual(snippets(self.rules(vp(scrollers=[sc])), "edge-flush-cards"),
                         ["1 card flush against the right edge of div.rail at rest (0px gap, e.g. div.card)"])
        lone = dict(sc, cards=sc["cards"][1:2])          # one card is not a row
        self.assertNotIn("edge-flush-cards", ids(self.rules(vp(scrollers=[lone]))))

    def test_body_text_edge(self):
        p = {"sel": "p", "tag": "p", "len": 120, "left": 4, "right": 1276, "moving": False, "cut": False}
        self.assertEqual(snippets(self.rules(vp(edgeText=[p])), "body-text-viewport-edge"),
                         ["<p> with 120-char body bleeds to viewport edge (left 4px / right 4px)"])
        ok = dict(p, left=24, right=1256)
        self.assertNotIn("body-text-viewport-edge", ids(self.rules(vp(edgeText=[ok]))))
        phone = vp(width=390, vw=390, edgeText=[dict(p, left=12, right=378)])   # 12px is the phone floor
        self.assertNotIn("body-text-viewport-edge", ids(self.rules(vp(), phone)))

    def test_text_overflow(self):
        bad = self.rules(vp(overflow=[{"sel": "div.box", "kind": "box", "delta": 120, "harm": True}]))
        self.assertEqual(snippets(bad, "text-overflow"), ["div.box overflows its box by 120px"])
        self.assertNotIn("text-overflow", ids(self.rules(vp(overflow=[{"sel": "div.box", "kind": "box", "delta": 120, "harm": False}]))))
        self.assertNotIn("text-overflow", ids(self.rules(vp(overflow=[{"sel": "div.box", "kind": "box", "delta": 10, "harm": True}]))))

    def test_text_occlusion(self):
        o = {"sel": "p.t", "text": "Root cause", "total": 10, "occluded": 8, "kind": "box", "occSel": "div.cover",
             "layered": True, "sameSvg": False}
        self.assertEqual(snippets(self.rules(vp(occlusion=[o])), "text-occlusion"),
                         ['p.t "Root cause" is 80% covered by an opaque element (div.cover)'])
        self.assertNotIn("text-occlusion", ids(self.rules(vp(occlusion=[dict(o, occluded=2)]))))
        self.assertNotIn("text-occlusion", ids(self.rules(vp(occlusion=[dict(o, kind="text", layered=False)]))))

    def test_column_overflow(self):
        row = {"sel": "section.hero", "cols": [{"top": 80, "left": 0, "right": 600, "contentH": 1800},
                                               {"top": 80, "left": 640, "right": 1240, "contentH": 300}]}
        self.assertEqual(len(snippets(self.rules(vp(columns=[row])), "first-viewport-column-overflow")), 1)
        even = {"sel": "section.hero", "cols": [dict(row["cols"][0], contentH=900), row["cols"][1]]}
        self.assertNotIn("first-viewport-column-overflow", ids(self.rules(vp(columns=[even]))))

    def test_heading_rhythm(self):
        h = {"sel": "h2", "tag": "h2", "text": "Pricing", "above": 8, "below": 40, "small": False, "prose": False, "separates": False}
        bad = self.rules(vp(heads=[h, dict(h, text="Teams")]))
        self.assertEqual(len(snippets(bad, "heading-rhythm")), 2)
        self.assertNotIn("heading-rhythm", ids(self.rules(vp(heads=[h]))))                       # one is not a page habit
        self.assertNotIn("heading-rhythm", ids(self.rules(vp(heads=[dict(h, above=64), dict(h, above=64)]))))

    def test_line_length(self):
        t = {"sel": "p", "widths": [1000, 1000, 400], "len": 290}
        self.assertEqual(snippets(self.rules(vp(lines=[t])), "line-length"), ["~121 chars on 2 of 3 rendered lines (aim for <80)"])
        self.assertNotIn("line-length", ids(self.rules(vp(lines=[dict(t, len=150)]))))

    def test_blinking_cursor(self):
        c = {"sel": "span.caret", "name": "blink", "w": 2, "h": 20, "pageTop": 100, "glyph": False, "empty": True,
             "filled": True, "radius": 0, "inHeader": False}
        bad = self.rules(vp(cursors=[c]))
        self.assertEqual(bad[0]["severity"], "warning")
        self.assertIn("2x20px blinking cursor", bad[0]["snippet"])
        self.assertNotIn("blinking-cursor", ids(self.rules(vp(cursors=[dict(c, w=12, h=12, radius=6)]))))   # round dot
        self.assertNotIn("blinking-cursor", ids(self.rules(vp(cursors=[dict(c, pageTop=2000)]))))

    def test_cramped_text_inset(self):
        c = {"sel": "div", "fs": 14, "pads": [2, 16, 2, 16], "insets": [2, 16, 2, 16], "borders": [True] * 4, "bg": False,
             "fullBleed": False}
        self.assertEqual(snippets(self.rules(vp(cramped=[c])), "cramped-padding"),
                         ["2px of space above and below the text (need ≥4.2px for 14px text)"])
        self.assertNotIn("cramped-padding", ids(self.rules(vp(cramped=[dict(c, pads=[12] * 4, insets=[12] * 4)]))))

    def test_rendered_rules_listed(self):
        for rid in ("edge-flush-cards", "text-occlusion", "first-viewport-column-overflow", "body-text-viewport-edge",
                    "text-overflow", "content-hidden-at-rest", "heading-rhythm", "script-error", "line-length",
                    "blinking-cursor"):
            self.assertIn(rid, RD.RENDERED_RULES)


class Browser(unittest.TestCase):
    """Upstream's browser fixtures: every flag-* case named in a finding, no pass-* case."""
    data = {}

    def setUp(self):
        ok, why = RD.available()
        if not ok:
            self.skipTest("no browser: %s" % why)

    def hits(self, name):
        if name not in self.data:
            d, why = RD.probe(FIX / name)
            if d is None:
                self.skipTest(why)
            self.data[name] = RD.rules(d)
        return self.data[name]

    def check(self, name, rule, n_min=1, flags=(), passes=()):
        got = snippets(self.hits(name), rule)
        self.assertGreaterEqual(len(got), n_min, got)
        for f in flags:
            self.assertTrue(any(f in s for s in got), (f, got))
        for p in passes:
            self.assertFalse(any(p in s for s in got), (p, got))
        self.assertFalse(any("pass-" in s or "Pass " in s for s in got), got)

    def test_edge_flush_cards(self):
        self.check("edge-flush-cards.html", "edge-flush-cards", flags=["flag-pager"])

    def test_text_overflow(self):
        self.check("text-overflow.html", "text-overflow", 10, flags=["flag-nowrap", "flag-under-positioned-box"])

    def test_text_occlusion(self):
        self.check("text-occlusion-buried.html", "text-occlusion", flags=["flag-under-headline"])
        self.check("text-occlusion.html", "text-occlusion", 3, flags=["flag-box-text", "flag-leak"])

    def test_first_viewport_column(self):
        self.check("first-viewport-column-overflow.html", "first-viewport-column-overflow", flags=["section.flag"])
        self.assertNotIn("first-viewport-column-overflow", ids(self.hits("first-viewport-column-overflow-tabs.html")))

    def test_body_text_edge(self):
        self.check("body-text-viewport-edge-display.html", "body-text-viewport-edge", 4)

    def test_heading_rhythm(self):
        self.check("heading-rhythm.html", "heading-rhythm", 18, flags=["Flag Crowded One"])

    def test_content_hidden(self):
        self.check("content-hidden-at-rest.html", "content-hidden-at-rest")
        self.assertNotIn("content-hidden-at-rest", ids(self.hits("content-hidden-closed-interface.html")))

    def test_script_error(self):
        got = [h for h in self.hits("script-error-ad-tech-hosts.html") if h["rule"] == "script-error"]
        self.assertEqual(sorted(h.get("severity", "error") for h in got), ["advisory", "advisory", "advisory", "error"])

    def test_blinking_cursor_and_line_length(self):
        self.check("blinking-cursor.html", "blinking-cursor", 3, flags=["flag-block-cursor"])
        self.check("line-length.html", "line-length", 5)


if __name__ == "__main__":
    unittest.main()
