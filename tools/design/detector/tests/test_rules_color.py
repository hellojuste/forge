"""Planted bad/good HTML for each colour rule (rules_color.py). Run: python3 -m unittest detector.tests.test_rules_color"""
import unittest

from detector import engine, rules_color

PAGE = "<!doctype html><html><head><style>%s</style></head><body%s>%s</body></html>"


def hits(rule, html, design=None):
    ctx = engine.Context("/tmp/fake/page.html", html, "html", design)
    return [engine.norm_hit(h, ctx) for h in rules_color.RULES[rule](ctx)]


def page(css="", body="", body_attrs=""):
    return PAGE % (css, body_attrs, body)


class ColorRules(unittest.TestCase):
    def fires(self, rule, html, design=None, contains=None):
        got = hits(rule, html, design)
        self.assertTrue(got, "%s should fire" % rule)
        if contains:
            self.assertTrue(any(contains in h["snippet"] for h in got), [h["snippet"] for h in got])
        return got

    def quiet(self, rule, html, design=None):
        self.assertEqual(hits(rule, html, design), [], "%s should stay quiet" % rule)

    def test_low_contrast(self):
        got = self.fires("low-contrast", page("p{color:#c8c8c8}", "<p>Washed out body copy</p>"),
                         contains="1.7:1 (need 4.5:1) — text #c8c8c8 on #ffffff")
        self.assertNotIn("severity", got[0])
        self.quiet("low-contrast", page("p{color:#333}", "<p>Readable body copy</p>"))

    def test_low_contrast_near_bar_is_advisory(self):
        got = self.fires("low-contrast", page("p{color:#777777}", "<p>Almost there</p>"), contains="4.48:1")
        self.assertEqual(got[0]["severity"], "advisory")

    def test_low_contrast_link_dedupe_and_disabled(self):
        got = hits("low-contrast", page("a{color:#bbbbbb}", "<a href=#>One</a> <a href=#>Two</a>"))
        self.assertEqual(len(got), 1)
        self.quiet("low-contrast", page(".b{background:#16a34a;color:#fff}", '<button class="b" disabled>Go</button>'))

    def test_gray_on_color(self):
        self.fires("gray-on-color", page(".c{background:#3b82f6;color:#969696}", '<div class="c">Gray on blue</div>'),
                   contains="text #969696 on bg #3b82f6")
        self.fires("gray-on-color", page("", '<div class="text-gray-400 bg-blue-500">x</div>'),
                   contains="text-gray-400 on bg-blue-500")
        self.quiet("gray-on-color", page(".c{background:#3b82f6;color:#fff}", '<div class="c">White on blue</div>'))
        self.quiet("gray-on-color", page("", '<div class="text-gray-800 hover:bg-blue-500 bg-blue-50">x</div>'))

    def test_gradient_text(self):
        css = ".g{background:linear-gradient(90deg,#ff0080,#7928ca);-webkit-background-clip:text;color:transparent}"
        self.fires("gradient-text", page(css, '<h1 class="g">Shiny</h1>'), contains="background-clip: text + gradient")
        one = ".g{background:linear-gradient(#0e0f12,#0e0f12);-webkit-background-clip:text}"
        self.quiet("gradient-text", page(one, '<h1 class="g">Solid</h1>'))

    def test_ai_color_palette(self):
        self.fires("ai-color-palette", page("h1{color:#a855f7}", "<h1>Purple heading</h1>"),
                   contains="Purple/violet text (#a855f7) on heading")
        self.fires("ai-color-palette", page("", '<div class="from-purple-500 to-blue-500">x</div>'))
        self.quiet("ai-color-palette", page("h1{color:#0f766e}", "<h1>Teal heading</h1>"))
        # a DESIGN.md that declares a purple switches the purple forms off
        self.quiet("ai-color-palette", page("h1{color:#a855f7}", "<h1>Brand</h1>"), design={"colors": {"brand": "#a855f7"}})

    def test_cream_palette(self):
        self.fires("cream-palette", page("body{background:#f5efe2}"), contains="rgb(245, 239, 226)")
        self.fires("cream-palette", page("", "", ' class="bg-amber-50"'), contains="Tailwind bg-amber-50")
        self.quiet("cream-palette", page("body{background:#ffffff}"))

    def test_dark_glow(self):
        self.fires("dark-glow", page(".x{box-shadow:0 0 24px #3b82f6}", '<div class="x">Glow</div>'),
                   contains="Zero-offset box-shadow glow (#3b82f6)")
        self.quiet("dark-glow", page(".x{box-shadow:0 4px 12px rgba(0,0,0,.2)}", '<div class="x">Card</div>'))

    def test_radial_halo(self):
        css = "body{background:#0b0b10}.h{background:radial-gradient(circle,#8526fe,transparent 70%)}"
        self.fires("radial-halo", page(css, '<div class="h">x</div>'), contains="(#8526fe → transparent) on dark page")
        self.quiet("radial-halo", page(css.replace("#0b0b10", "#ffffff"), '<div class="h">x</div>'))

    def test_radial_spotlight_glow(self):
        css = ".s{width:600px;height:400px;background:radial-gradient(circle,rgba(80,111,255,.3),transparent 70%)}"
        self.fires("radial-spotlight-glow", page(css, '<div class="s" data-name="Hero">Copy</div>'),
                   contains='"Hero" (#506fff a0.30 → transparent) on 600x400 surface')
        self.quiet("radial-spotlight-glow", page(css.replace("600px", "100px"), '<div class="s">Copy</div>'))

    def test_design_system_color(self):
        design = {"colors": {"ink": "#111111", "paper": "#ffffff"}}
        html = page("p{color:#ff00aa}", "<p>Off palette</p>")
        self.fires("design-system-color", html, design, contains="#ff00aa")
        self.quiet("design-system-color", page("p{color:#111111}", "<p>On palette</p>"), design)
        self.quiet("design-system-color", html, None)

    def test_buried_raster(self):
        self.fires("buried-raster", page("", '<img src="a.png" alt="Ghost" style="opacity:.05">'),
                   contains='<img> at opacity 0.05 "Ghost"')
        wash = ".p{background:linear-gradient(rgba(255,255,255,.95),rgba(255,255,255,.95)),url(paper.png)}"
        self.fires("buried-raster", page(wash, '<div class="p">x</div>'), contains="near-opaque gradient wash")
        self.quiet("buried-raster", page("", '<img src="a.png" alt="Shown"><img src="i.svg" alt="" style="opacity:0">'))

    def test_repeating_stripes(self):
        css = ".s{background:repeating-linear-gradient(45deg,#eee 0 10px,#fff 10px 20px)}"
        self.fires("repeating-stripes-gradient", page(css, '<div class="s">x</div>'))
        self.quiet("repeating-stripes-gradient",
                   page(".s{background:repeating-linear-gradient(90deg,#eee 0%,#fff 100%)}", '<div class="s">x</div>'))

    def test_codex_grid_background(self):
        css = (".g{background-image:linear-gradient(#ddd 1px,transparent 1px),linear-gradient(90deg,#ddd 1px,"
               "transparent 1px);background-size:24px 24px}")
        self.fires("codex-grid-background", page(css, '<div class="g">x</div>'))
        self.quiet("codex-grid-background",
                   page(".g{background-image:linear-gradient(#ddd 1px,transparent 1px);background-size:24px 24px}",
                        '<div class="g">x</div>'))

    def test_organic_clip_path(self):
        blob = ("polygon(3% 11%, 17% 2%, 38% 7%, 61% 1%, 83% 9%, 97% 27%, 93% 52%, 98% 79%, 81% 96%, 52% 91%, "
                "23% 98%, 6% 81%)")
        self.fires("organic-clip-path", page(".b{clip-path:%s}" % blob, '<div class="b">x</div>'),
                   contains="polygon() with 12 vertices")
        self.quiet("organic-clip-path", page(".b{clip-path:polygon(0 0,100% 0,100% 100%,0 100%)}", '<div class="b">x</div>'))

    def test_page_checks_need_full_page(self):
        self.quiet("cream-palette", "<div style='background:#f5efe2'>fragment</div>")


if __name__ == "__main__":
    unittest.main()
