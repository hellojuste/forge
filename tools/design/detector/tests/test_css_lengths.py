"""Regression tests for css.length_px on modern CSS sizing (found by the landing-sample run, 2026-10-16: two
prototype agents had to rewrite good CSS because env() inside max() read as 0px -> false cramped-padding, and
clamp(a, b + c vw, d) font sizes were unreadable -> false flat-type-hierarchy)."""
import unittest

from detector import css, engine
from detector import rules_layout, rules_type


def ctx(html):
    return engine.Context("/tmp/fake/page.html", html, "html", None)


class Lengths(unittest.TestCase):
    def test_env_resolves_to_zero_or_fallback(self):
        self.assertEqual(css.length_px("max(16px, env(safe-area-inset-left))"), 16.0)
        self.assertEqual(css.length_px("env(safe-area-inset-left, 12px)"), 12.0)
        self.assertEqual(css.length_px("calc(16px + env(safe-area-inset-left))"), 16.0)

    def test_clamp_with_expression_argument(self):
        self.assertAlmostEqual(css.length_px("clamp(2rem, 1.5rem + 2vw, 3.25rem)"), 49.6)

    def test_unknown_stays_unknown(self):
        self.assertIsNone(css.length_px("max(16px, attr(data-x))"))

    def test_safe_area_padding_is_not_cramped(self):
        page = """<!doctype html><html><head><style>
        section { background: #0f172a; color: #fff; padding: 48px max(24px, env(safe-area-inset-left)); }
        </style></head><body><section><p>Closing call to action with enough words to be text.</p></section></body></html>"""
        self.assertEqual(list(rules_layout.RULES["cramped-padding"](ctx(page))), [])

    def test_bad_flush_padding_still_fires(self):
        page = """<!doctype html><html><head><style>
        section { background: #0f172a; color: #fff; padding: 0; } p { margin: 0; }
        </style></head><body><section><p>Closing call to action flush against the coloured edge.</p></section></body></html>"""
        self.assertTrue(list(rules_layout.RULES["cramped-padding"](ctx(page))))

    def test_clamp_type_scale_is_not_flat(self):
        page = """<!doctype html><html><head><style>
        body { font-size: 17px; } h1 { font-size: clamp(2rem, 1.5rem + 2vw, 3.25rem); } h2 { font-size: clamp(1.5rem, 1.2rem + 1vw, 2rem); }
        </style></head><body><h1>Month-end, closed by the fifth</h1><p>Body copy for the page that is long enough.</p>
        <h2>How it works</h2><p>More body copy for the second section of the page.</p></body></html>"""
        self.assertEqual([h for h in rules_type.RULES["flat-type-hierarchy"](ctx(page))], [])


if __name__ == "__main__":
    unittest.main()
