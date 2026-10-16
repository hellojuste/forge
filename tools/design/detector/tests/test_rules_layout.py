"""Planted bad / good inputs for every static rule in rules_layout.py (impeccable static-engine port)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from detector import engine  # noqa: E402
from detector import rules_layout as L  # noqa: E402

PAGE = "<!doctype html><html><head><style>%s</style></head><body>%s</body></html>"


def run(rule, css="", body="", design=None, full=True):
    text = (PAGE % (css, body)) if full else body
    ctx = engine.Context(Path("/tmp/planted.html"), text, "html", design)
    out = []
    for h in L.RULES[rule](ctx) or ():
        out.append(h if isinstance(h, dict) else {"rule": h[0], "snippet": h[1]})
    return [h for h in out if h["rule"] == rule]


class SideTab(unittest.TestCase):
    def test_rounded_card_left_border_fires(self):
        hits = run("side-tab", ".c{border-left:4px solid #6366f1;border-radius:8px}", '<div class="c">Card</div>')
        self.assertEqual([h["snippet"] for h in hits], ["border-left: 4px + border-radius: 8px"])

    def test_square_or_grey_border_passes(self):
        self.assertEqual(run("side-tab", ".c{border-left:4px solid #6366f1}", '<div class="c">Callout</div>'), [])
        self.assertEqual(run("side-tab", ".c{border-left:4px solid #9ca3af;border-radius:8px}", '<div class="c">x</div>'), [])

    def test_var_coloured_shorthand_keeps_its_width(self):
        css = ":root{--brand:#87a8ff}.c{border-left:5px solid var(--brand);border-radius:4px}"
        self.assertEqual(len(run("side-tab", css, '<div class="c">x</div>')), 1)

    def test_stripe_child_fires_on_rounded_flex_host(self):
        css = ".host{display:flex;border-radius:12px}.bar{width:4px;background:#e11d48}"
        hits = run("side-tab", css, '<div class="host"><div class="bar"></div><p>Body copy</p></div>')
        self.assertEqual([h["snippet"] for h in hits], ["div.bar — 4px stripe child (left)"])

    def test_stripe_child_on_square_host_passes(self):
        css = ".host{display:flex}.bar{width:4px;background:#e11d48}"
        self.assertEqual(run("side-tab", css, '<div class="host"><div class="bar"></div><p>Body copy</p></div>'), [])

    def test_pseudo_stripe_fires_and_square_host_passes(self):
        css = (".card{position:relative;border-radius:12px}.card::before{content:'';position:absolute;left:0;top:0;"
               "bottom:0;width:4px;background:#e11d48}")
        hits = run("side-tab", css, '<div class="card">Card</div>')
        self.assertEqual(hits[0]["snippet"], ".card::before — absolute 4px pseudo-element stripe (left: 0)")
        self.assertEqual(run("side-tab", css.replace("border-radius:12px", ""), '<div class="card">Card</div>'), [])

    def test_inset_shadow_stripe(self):
        css = ".note{box-shadow:inset 4px 0 0 #2563eb;border-radius:8px}"
        self.assertIn("inset box-shadow 4px stripe (left)", run("side-tab", css, '<div class="note">x</div>')[0]["snippet"])
        self.assertEqual(run("side-tab", ".note{box-shadow:inset 4px 0 0 #999;border-radius:8px}", '<div class="note">x</div>'), [])


class BorderAccent(unittest.TestCase):
    def test_top_band_on_rounded_card(self):
        hits = run("border-accent-on-rounded", ".c{border-top:4px solid #6366f1;border-radius:12px}", '<div class="c">x</div>')
        self.assertEqual([h["snippet"] for h in hits], ["border-top: 4px + border-radius: 12px"])

    def test_neutral_band_passes(self):
        self.assertEqual(run("border-accent-on-rounded", ".c{border-top:4px solid #ddd;border-radius:12px}", '<div class="c">x</div>'), [])


class NestedCards(unittest.TestCase):
    def test_card_in_card(self):
        body = ('<div class="border rounded-lg">Outer card text <div class="border rounded-md">Inner card text here</div></div>')
        self.assertEqual([h["snippet"] for h in run("nested-cards", body=body)], ["Card inside card (div)"])

    def test_plain_inner_box_passes(self):
        body = '<div class="border rounded-lg">Outer card text <div class="rounded-md">Inner text here ok</div></div>'
        self.assertEqual(run("nested-cards", body=body), [])

    def test_mockup_is_advisory(self):
        body = ('<div role="img" class="border rounded-lg">Outer card text <div class="border rounded-md">'
                'Inner card text here</div></div>')
        self.assertEqual(run("nested-cards", body=body)[0].get("severity"), "advisory")


class IconTile(unittest.TestCase):
    CSS = ".t{width:48px;height:48px;background:#eef2ff;border-radius:%s}"
    BODY = '<div><div class="t"><svg width="24" height="24"></svg></div><h3>Fast setup</h3></div>'

    def test_tile_above_heading(self):
        hits = run("icon-tile-stack", self.CSS % "10px", self.BODY)
        self.assertEqual([h["snippet"] for h in hits], ['48x48px icon tile above h3 "Fast setup"'])

    def test_round_avatar_passes(self):
        self.assertEqual(run("icon-tile-stack", self.CSS % "50%", self.BODY), [])


class GptBorderShadow(unittest.TestCase):
    CSS = ".card{border:1px solid #e5e7eb;box-shadow:0 20px 40px rgba(0,0,0,.2)}"

    def test_row_of_three(self):
        body = '<div>' + '<div class="card">A card</div>' * 3 + '</div>'
        hits = run("gpt-thin-border-wide-shadow", self.CSS, body)
        self.assertEqual(len(hits), 3)
        self.assertEqual(hits[0]["snippet"], "1px border + 40px shadow blur, repeated across the row")

    def test_two_cards_pass(self):
        self.assertEqual(run("gpt-thin-border-wide-shadow", self.CSS, '<div>' + '<div class="card">A card</div>' * 2 + '</div>'), [])


class CrampedPadding(unittest.TestCase):
    def test_children_flush_against_fill(self):
        hits = run("cramped-padding", ".chip{background:#1e293b}", '<div class="chip"><p>Seventeen dollars</p></div>')
        self.assertEqual([h["snippet"] for h in hits],
                         ['<div> "chip": children flush against bg on all sides (no inset)'])

    def test_padded_box_passes(self):
        self.assertEqual(run("cramped-padding", ".chip{background:#1e293b;padding:16px}", '<div class="chip"><p>Seventeen dollars</p></div>'), [])


class ClippedOverflow(unittest.TestCase):
    BODY = '<div class="box"><button>Open</button><ul class="pop" role="menu"><li>One item</li></ul></div>'

    def test_menu_clipped(self):
        css = ".box{overflow:hidden;position:relative}.pop{position:absolute;top:100%}"
        self.assertEqual([h["snippet"] for h in run("clipped-overflow-container", css, self.BODY)],
                         ["div.box clips positioned ul.pop"])

    def test_visible_overflow_passes(self):
        self.assertEqual(run("clipped-overflow-container", ".pop{position:absolute;top:100%}", self.BODY), [])


class ShapeIllustration(unittest.TestCase):
    def svg(self, n):
        fills = ["#f00", "#0f0", "#00f"]
        return '<svg width="400" height="300">%s</svg>' % "".join('<rect fill="%s"/>' % fills[i % 3] for i in range(n))

    def test_scene_fires(self):
        hits = run("shape-assembled-illustration", body=self.svg(8))
        self.assertEqual([h["snippet"] for h in hits], ["inline <svg> scene: 8 primitive shapes, ~400x300px, 3 fill colors"])

    def test_icon_passes(self):
        self.assertEqual(run("shape-assembled-illustration", body=self.svg(5)), [])


class BrokenImage(unittest.TestCase):
    def test_missing_and_empty_src(self):
        snips = [h["snippet"] for h in run("broken-image", body='<img alt="x"><img src="">')]
        self.assertEqual(snips, ["<img> with no src attribute", '<img src="">'])

    def test_real_src_passes(self):
        self.assertEqual(run("broken-image", body='<img src="a.png" alt="">'), [])


class MonotonousSpacing(unittest.TestCase):
    def test_one_value_everywhere(self):
        css = "".join(".a%d{padding:16px}" % i for i in range(10))
        self.assertEqual([h["snippet"] for h in run("monotonous-spacing", css, "<p>x</p>")], ["~16px used 10/10 times (100%)"])

    def test_varied_scale_passes(self):
        css = "".join(".a%d{padding:%dpx}" % (i, v) for i, v in enumerate([4, 8, 12, 16, 24, 32, 48, 64, 8, 16]))
        self.assertEqual(run("monotonous-spacing", css, "<p>x</p>"), [])


class DesignSystemRadius(unittest.TestCase):
    DESIGN = {"rounded": {"sm": "4px", "md": "8px"}}

    def test_off_scale_radius(self):
        hits = run("design-system-radius", ".c{border-radius:18px}", '<div class="c">Card</div>', self.DESIGN)
        self.assertTrue(hits)
        self.assertIn("18px", hits[0]["snippet"])

    def test_on_scale_and_no_design_pass(self):
        self.assertEqual(run("design-system-radius", ".c{border-radius:8px}", '<div class="c">x</div>', self.DESIGN), [])
        self.assertEqual(run("design-system-radius", ".c{border-radius:18px}", '<div class="c">x</div>', None), [])


if __name__ == "__main__":
    unittest.main()
