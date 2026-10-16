"""Static approximations of rendered rules (used only without a browser): advisory, labelled static-approx."""
import unittest

from detector import engine, rendered

LONG = "Monthly reporting for small finance teams, reconciled weekly against the bank, with a plain summary " * 3


def ctx(html):
    return engine.Context("/tmp/fake/page.html", html, "html", None)


class StaticApprox(unittest.TestCase):
    def test_unbounded_paragraph_flags_line_length_and_edge(self):
        hits = rendered.static_approx(ctx("<!doctype html><html><body style='margin:0'><p>%s</p></body></html>" % LONG))
        rules = {h["rule"] for h in hits}
        self.assertIn("line-length", rules)
        self.assertIn("body-text-viewport-edge", rules)
        self.assertTrue(all(h["severity"] == "advisory" and h["engine"] == "static-approx" for h in hits))
        self.assertTrue(all(h["snippet"].startswith("static approximation") for h in hits))

    def test_measured_column_is_clean(self):
        page = "<!doctype html><html><body><main style='max-width:38rem;margin:0 auto;padding:0 24px'><p>%s</p></main></body></html>" % LONG
        self.assertEqual(rendered.static_approx(ctx(page)), [])

    def test_hidden_at_rest(self):
        page = "<!doctype html><html><body><section style='opacity:0'><p>%s</p></section><p>short</p></body></html>" % LONG
        self.assertIn("content-hidden-at-rest", {h["rule"] for h in rendered.static_approx(ctx(page))})


if __name__ == "__main__":
    unittest.main()
