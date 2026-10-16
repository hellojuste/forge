"""Planted BAD / GOOD cases for regex_engine (impeccable's line-regex engine for non-HTML files).

One pair per REGEX_MATCHERS entry (in upstream order), then the passes around them: comment stripping, <style> blocks,
CSS-in-JS, the rounded-card gate, the stripe scans, grid background, page analyzers, dedupe.
Run from tools/design: python3 -m unittest discover -s detector/tests -p 'test_r*.py'
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from detector import regex_engine as RE  # noqa: E402


def found(text, path="x.jsx"):
    return RE.detect_text(text, path)


def rules(text, path="x.jsx"):
    return [f[0] for f in found(text, path)]


def snips(rule, text, path="x.jsx"):
    return [f[1] for f in found(text, path) if f[0] == rule]


# (name, rule, path, BAD text, expected snippet or None, GOOD text) — one row per upstream matcher, in order.
MATCHER_CASES = [
    ("side-tab tailwind", "side-tab", "x.jsx", '<div className="border-l-4 border-indigo-500 rounded-lg p-4">x</div>',
     "border-l-4", '<div className="border-l-1 border-indigo-500 rounded-lg p-4">x</div>'),
    ("side-tab css", "side-tab", "x.css", ".c { border-left: 4px solid #6366f1; border-radius: 12px; }",
     "border-left: 4px solid #6366f1", ".c { border-left: 4px solid #000; border-radius: 12px; }"),
    ("side-tab width", "side-tab", "x.css", ".c { border-left-width: 4px; border-radius: 12px; }",
     "border-left-width: 4px", ".c { border-left-width: 2px; border-radius: 12px; }"),
    ("side-tab inline", "side-tab", "x.css", ".c { border-inline-start: 4px solid #6366f1; border-radius: 12px; }",
     "border-inline-start: 4px solid", ".c { border-inline-start: 2px solid #6366f1; border-radius: 12px; }"),
    ("side-tab inline width", "side-tab", "x.css", ".c { border-inline-end-width: 5px; border-radius: 12px; }",
     "border-inline-end-width: 5px", ".c { border-inline-end-width: 1px; border-radius: 12px; }"),
    ("side-tab js", "side-tab", "x.jsx", "<div style={{ borderLeft: '4px solid #6366f1', borderRadius: 12 }} />",
     "borderLeft: '4px solid", "<div style={{ borderLeft: '1px solid #6366f1', borderRadius: 12 }} />"),
    ("side-tab stripe child", "side-tab", "x.jsx", '<div className="w-1 shrink-0 rounded-l-lg bg-amber-500" />',
     "w-1 + bg-amber-500 stripe child", '<div className="w-1 bg-amber-500" />'),
    ("border-accent tailwind", "border-accent-on-rounded", "x.jsx",
     '<div className="rounded-lg border-t-4 border-blue-500" />', "border-t-4",
     '<div className="animate-spin rounded-full h-12 w-12 border-b-2" />'),
    ("border-accent css", "border-accent-on-rounded", "x.css", ".c { border-top: 4px solid #6366f1; border-radius: 12px; }",
     "border-top: 4px solid", ".c { border-top: 4px solid #6366f1; }"),
    ("overused-font family", "overused-font", "x.css", ".c { font-family: Inter, sans-serif; }",
     "font-family: Inter", ".c { font-family: Literata, serif; }"),
    ("overused-font google", "overused-font", "x.css",
     '@import url("https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400&display=swap");',
     "Google Fonts: space grotesk", '@import url("https://fonts.googleapis.com/css2?family=Literata&display=swap");'),
    ("gradient-text css", "gradient-text", "x.css",
     ".t { background: linear-gradient(90deg, #f0f, #0ff); -webkit-background-clip: text; }",
     "background-clip: text + gradient", ".t { background: #f0f; -webkit-background-clip: text; }"),
    ("gradient-text tailwind", "gradient-text", "x.jsx",
     '<h1 className="bg-clip-text bg-gradient-to-r from-pink-500 to-orange-500">Hi</h1>',
     "bg-clip-text + bg-gradient", '<h1 className="bg-clip-text text-transparent">Hi</h1>'),
    ("gray-on-color", "gray-on-color", "x.jsx", '<button className="text-slate-300 bg-red-500">Log out</button>',
     "text-slate-300 on bg-red-500", '<button className="text-gray-800 bg-yellow-400">Log out</button>'),
    ("ai-color-palette heading", "ai-color-palette", "x.jsx", '<h1 className="text-purple-600 text-4xl">Hi</h1>',
     "text-purple-600 on heading", '<p className="text-purple-600 text-sm">Hi</p>'),
    ("ai-color-palette gradient", "ai-color-palette", "x.jsx", '<div className="from-purple-500 to-pink-500" />',
     "from-purple-500 gradient", '<div className="from-purple-500 to-gray-500" />'),
    ("bounce tailwind", "bounce-easing", "x.jsx", '<span className="animate-bounce">v</span>',
     "animate-bounce (Tailwind)", '<span className="animate-pulse">v</span>'),
    ("bounce animation", "bounce-easing", "x.css", ".b { animation: bounce 1s infinite; }",
     "animation: bounce", ".b { animation: fade-in 1s ease-out; }"),
    ("bounce bezier", "bounce-easing", "x.css", ".e { transition: transform .3s cubic-bezier(0.68, -0.55, 0.265, 1.55); }",
     "cubic-bezier(0.68, -0.55, 0.265, 1.55)", ".e { transition: transform .3s cubic-bezier(0.16, 1, 0.3, 1); }"),
    ("broken-image empty src", "broken-image", "x.jsx", '<img src="" alt="x" />', '<img src=""',
     '<img src="a.png" alt="x" />'),
    ("broken-image no src", "broken-image", "x.vue", '<template><img alt="x"></template>', '<img alt="x">',
     '<template><img src="a.png" alt="x"></template>'),
]


class Matchers(unittest.TestCase):
    def test_one_case_per_upstream_matcher(self):
        self.assertEqual(len(MATCHER_CASES), len(RE.MATCHERS))
        self.assertEqual([c[1] for c in MATCHER_CASES], [m[0] for m in RE.MATCHERS])

    def test_bad_fires(self):
        for name, rule, path, bad, want, _ in MATCHER_CASES:
            with self.subTest(name):
                got = snips(rule, bad, path)
                self.assertTrue(got, "%s: nothing for %r" % (name, bad))
                self.assertTrue(any(want in s for s in got), "%s: %r" % (name, got))

    def test_good_is_quiet(self):
        for name, rule, path, _, _, good in MATCHER_CASES:
            with self.subTest(name):
                self.assertEqual(snips(rule, good, path), [], name)

    def test_rule_ids_cover_matchers(self):
        self.assertTrue({m[0] for m in RE.MATCHERS} <= RE.RULE_IDS)


class SideTabGate(unittest.TestCase):
    def test_square_card_drops(self):
        self.assertEqual(snips("side-tab", ".c {\n  border-left: 4px solid #6366f1;\n}", "x.css"), [])
        self.assertEqual(snips("side-tab", '<div className="border-l-4 border-indigo-500 p-4">x</div>'), [])

    def test_rounded_or_unknown_keeps(self):
        self.assertTrue(snips("side-tab", ".c {\n  border-radius: $r;\n  border-left: 4px solid #6366f1;\n}", "x.scss"))
        self.assertTrue(snips("side-tab", "<div className={cn('border-l-4 border-indigo-500', className)} />"))

    def scope_rounded(self, text, needle="border-left: 4px solid #6366f1", sass=False):
        lines = text.split("\n")
        i = next(k for k, ln in enumerate(lines) if needle in ln)
        m = RE.SIDE_TAB_CSS.search(lines[i])
        return RE.side_tab_rounded_in_scope(m, RE.SourceText(lines), i, sass)

    def test_same_element_nesting(self):
        css = ".c {\n  border-radius: 12px;\n  &.on { border-left: 4px solid #6366f1; }\n}"
        self.assertTrue(self.scope_rounded(css))
        self.assertTrue(snips("side-tab", css, "x.scss"))
        css = ".c {\n  border-radius: 12px;\n  .child { border-left: 4px solid #6366f1; }\n}"
        self.assertFalse(self.scope_rounded(css))
        # the file still declares a radius the child may carry, so the sheet gate keeps the finding (fails safe)
        self.assertTrue(snips("side-tab", css, "x.scss"))
        self.assertFalse(self.scope_rounded(".c {\n  border-radius: 12px;\n  &__part { border-left: 4px solid #6366f1; }\n}"))
        self.assertTrue(self.scope_rounded(".c {\n  border-radius: 12px;\n  @media (min-width: 600px) {\n    border-left: 4px solid #6366f1;\n  }\n}"))
        self.assertTrue(self.scope_rounded(".c {\n  @include card-shape;\n  border-left: 4px solid #6366f1;\n}"))

    def test_sass_indentation(self):
        self.assertTrue(snips("side-tab", ".card\n  border-left: 4px solid #6366f1\n  border-radius: 12px\n", "x.sass"))
        self.assertEqual(snips("side-tab", ".card\n  border-left: 4px solid #6366f1\n  padding: 8px\n", "x.sass"), [])

    def test_tailwind_corners(self):
        self.assertTrue(RE.tailwind_declared_corners("border-l-4 rounded-r-lg").rounded_away(3))
        self.assertFalse(RE.tailwind_declared_corners("border-l-4 rounded-l-lg").rounded_away(3))
        self.assertTrue(RE.tailwind_declared_corners("border-l-4 md:rounded-xl").rounded_away(3))
        self.assertFalse(RE.tailwind_declared_corners("rounded-r-none border-l-4 rounded-lg").rounded_away(3))


class Passes(unittest.TestCase):
    def test_css_comments_are_blank(self):
        self.assertEqual(rules("/* .b { animation: bounce 1s } */\n.a { color: red }", "x.css"), [])

    def test_js_comments_are_blank(self):
        self.assertEqual(rules('// <span className="animate-bounce" />\nconst a = 1;\n/* animate-bounce */'), [])
        self.assertTrue(rules('const s = "// not a comment"; <span className="animate-bounce" />'))

    def test_style_block_line_and_dedupe(self):
        vue = "<template><div/></template>\n<style>\n.b {\n  animation: bounce 1s infinite;\n}\n</style>\n"
        f = [x for x in found(vue, "x.vue") if x[0] == "bounce-easing"]
        self.assertEqual(f, [("bounce-easing", "animation: bounce", 4)])

    def test_css_in_js_template(self):
        tsx = "import styled from 'x';\nconst B = styled.div`\n  /* animation: bounce */\n  animation: wobble 1s;\n`;\n"
        self.assertEqual([x for x in found(tsx, "x.tsx") if x[0] == "bounce-easing"],
                         [("bounce-easing", "animation: wobble", 4)])

    def test_dedupe_within_two_lines_only(self):
        css = ".a { animation: bounce 1s }\n.b { animation: bounce 2s }\n\n\n\n.c { animation: bounce 3s }"
        self.assertEqual([x[2] for x in found(css, "x.css") if x[0] == "bounce-easing"], [1, 6])

    def test_inset_stripe(self):
        css = ".card { width: 320px; border-radius: 12px; box-shadow: inset 4px 0 0 #6366f1; }"
        self.assertEqual(snips("side-tab", css, "x.css"), [".card — inset box-shadow 4px stripe (left)"])
        self.assertEqual(snips("side-tab", ".card { box-shadow: inset 4px 0 0 #6366f1; }", "x.css"), [])

    def test_pseudo_stripe(self):
        css = (".card { position: relative; border-radius: 12px; }\n"
               ".card::before { content: ''; position: absolute; top: 0; bottom: 0; left: 0; width: 4px; background: #6366f1; }")
        self.assertEqual(snips("side-tab", css, "x.css"),
                         [".card::before — absolute 4px pseudo-element stripe (left: 0)"])
        self.assertEqual(snips("side-tab", css.replace("#6366f1", "#999"), "x.css"), [])

    def test_grid_background(self):
        css = (".g { background-image: linear-gradient(#ddd 1px, transparent 1px), "
               "linear-gradient(90deg, #ddd 1px, transparent 1px); background-size: 24px 24px; }")
        self.assertEqual(snips("codex-grid-background", css, "x.css"), ["two-axis grid-line gradient background"])
        self.assertEqual(snips("codex-grid-background", ".g { background-image: linear-gradient(#ddd 1px, transparent 1px); }",
                               "x.css"), [])

    def test_page_analyzers_full_page_component_only(self):
        body = " ".join("a — b" for _ in range(8))
        vue = "<!DOCTYPE html><html><head></head><body><p>%s Streamline your work.</p></body></html>" % body
        got = rules(vue, "x.vue")
        self.assertIn("em-dash-overuse", got)
        self.assertIn("marketing-buzzword", got)
        self.assertEqual([r for r in rules(vue, "x.tsx") if r in ("em-dash-overuse", "marketing-buzzword")], [])
        partial = "<template><p>%s</p></template>" % body
        self.assertNotIn("em-dash-overuse", rules(partial, "x.vue"))

    def test_page_marquee_and_glow(self):
        page = ("<!DOCTYPE html><html><head><style>body{background:#0a0a0a}.t{animation:c 9s linear infinite}"
                "@keyframes c{to{transform:translateX(-50%)}}.g{box-shadow:0 0 24px #a855f7}</style></head><body></body></html>")
        got = rules(page, "x.svelte")
        self.assertIn("marquee", got)
        self.assertIn("dark-glow", got)

    def test_scan_ctx_entrypoint(self):
        class Ctx:
            text = ".b { animation: bounce 1s }"
            path = Path("a.css")
        self.assertEqual(RE.scan(Ctx()), [("bounce-easing", "animation: bounce", 1)])


if __name__ == "__main__":
    unittest.main()
