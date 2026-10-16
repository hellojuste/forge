"""Planted BAD / GOOD cases for rules_motion_copy (impeccable's motion + copy rules) and ignores.py.

Run from tools/design: python3 -m unittest discover -s detector/tests -p 'test_r*.py'
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from detector import engine, ignores  # noqa: E402
from detector import rules_motion_copy as MC  # noqa: E402


def page(body, css="", full=True):
    head = "<!DOCTYPE html><html><head><title>t</title><style>%s</style></head><body>" % css if full else \
        "<style>%s</style><div>" % css
    return head + body + ("</body></html>" if full else "</div>")


def hits(rule, html):
    ctx = engine.Context("t.html", html, "html")
    out = []
    for h in MC.RULES[rule](ctx):
        out.append(engine.norm_hit(h, ctx))
    return out


def snippets(rule, html):
    return [h["snippet"] for h in hits(rule, html)]


class BounceEasing(unittest.TestCase):
    CSS = ".ball{animation:bounce-y 1s infinite}@keyframes bounce-y{0%,100%{transform:translateY(-25%)}50%{transform:none}}"

    def test_bad_named_bounce_on_div(self):
        self.assertEqual(snippets("bounce-easing", page('<div class="ball"></div>', self.CSS)), ["animation: bounce-y"])

    def test_bad_overshooting_bezier(self):
        css = ".e{transition:transform .5s cubic-bezier(0.68, -0.55, 0.265, 1.55)}"
        self.assertEqual(snippets("bounce-easing", page('<div class="e"></div>', css)),
                         ["cubic-bezier(0.68, -0.55, 0.265, 1.55)"])

    def test_good_safe_tag_and_smooth_curve(self):
        self.assertEqual(snippets("bounce-easing", page('<span class="ball"></span>', self.CSS)), [])
        css = ".e{transition:transform .5s cubic-bezier(0.16, 1, 0.3, 1)}"
        self.assertEqual(snippets("bounce-easing", page('<div class="e"></div>', css)), [])

    def test_good_bounce_named_pulse(self):
        css = ".dot{animation:sk-bounceDelay 1s infinite}@keyframes sk-bounceDelay{0%,100%{transform:scale(0)}50%{transform:scale(1)}}"
        self.assertEqual(snippets("bounce-easing", page('<div class="dot"></div>', css)), [])

    def test_scoped_waiver(self):
        html = page('<section data-impeccable-ignore="bounce-easing"><div class="ball"></div></section>', self.CSS)
        self.assertEqual(snippets("bounce-easing", html), [])


class PulsingDot(unittest.TestCase):
    CSS = ".live{width:8px;height:8px;border-radius:50%;animation:pulse 2s infinite}@keyframes pulse{50%{opacity:.3}}"

    def test_bad_dot(self):
        self.assertEqual(snippets("pulsing-dot", page('<span class="live"></span>', self.CSS)),
                         ['.live — 8x8px dot with infinite "pulse" animation'])

    def test_bad_in_header_is_error(self):
        h = hits("pulsing-dot", page('<header><span class="live"></span></header>', self.CSS))
        self.assertEqual(h[0]["severity"], "error")
        self.assertTrue(h[0]["snippet"].endswith("in header/nav"))

    def test_bad_tailwind(self):
        html = page('<span class="animate-ping w-2 h-2 rounded-full"></span>')
        self.assertEqual(snippets("pulsing-dot", html), ["animate-ping on tiny rounded-full element"])

    def test_good_large_finite_or_rotating(self):
        css = (".card{width:240px;height:120px;border-radius:50%;animation:pulse 2s infinite}"
               ".nudge{width:8px;height:8px;border-radius:50%;animation:pulse 1s 3}"
               ".spin{width:8px;height:8px;border-radius:50%;animation:pulse-ring 1s infinite}"
               "@keyframes pulse{50%{opacity:.3}}@keyframes pulse-ring{to{transform:rotate(180deg)}}")
        self.assertEqual(snippets("pulsing-dot", page('<div class="card"></div>', css)), [])

    def test_good_partial_page(self):
        self.assertEqual(snippets("pulsing-dot", page('<span class="live"></span>', self.CSS, full=False)), [])

    def test_scoped_waiver(self):
        html = page('<div data-impeccable-ignore="pulsing-dot"><span class="live"></span></div>', self.CSS)
        self.assertEqual(snippets("pulsing-dot", html), [])


class Marquee(unittest.TestCase):
    def test_bad_loop(self):
        css = ".track{animation:crawl 20s linear infinite}@keyframes crawl{to{transform:translateX(-50%)}}"
        self.assertEqual(snippets("marquee", page('<div class="track">x</div>', css)),
                         ['.track — infinite horizontal loop animation "crawl"'])

    def test_bad_marquee_element(self):
        self.assertEqual(snippets("marquee", page("<marquee>news</marquee>")), ["<marquee> element"])

    def test_good_short_travel_or_finite(self):
        css = (".a{animation:nudge 2s infinite}@keyframes nudge{to{transform:translateX(10%)}}"
               ".b{animation:crawl 2s}@keyframes crawl{to{transform:translateX(-50%)}}")
        self.assertEqual(snippets("marquee", page('<div class="a"></div><div class="b"></div>', css)), [])


class Theater(unittest.TestCase):
    def test_bad(self):
        self.assertEqual(snippets("theater-slop-phrase", page("<p>We cut the compliance theater.</p>")),
                         ['"compliance theater"'])

    def test_good(self):
        self.assertEqual(snippets("theater-slop-phrase", page("<p>The company returns to its official theater.</p>")), [])


class EmDash(unittest.TestCase):
    def test_bad_saturated(self):
        body = "<p>" + " ".join("a — b" for _ in range(8)) + "</p>"
        self.assertEqual(snippets("em-dash-overuse", page(body)), ["8 em-dashes in body text"])

    def test_bad_entities_and_double_hyphen(self):
        body = "<p>" + " ".join("x &mdash; y --z" for _ in range(4)) + "</p>"
        self.assertEqual(snippets("em-dash-overuse", page(body)), ["8 em-dashes in body text"])

    def test_good_sparse_or_rules(self):
        self.assertEqual(snippets("em-dash-overuse", page("<p>a — b</p><pre>----- ----- -----</pre>")), [])
        long_text = "<p>" + "word " * 1000 + " — ".join("x" * 9) + "</p>"
        self.assertEqual(snippets("em-dash-overuse", page(long_text)), [])

    def test_count(self):
        self.assertEqual(MC.count_em_dashes("a — b -- c ---d"), 1)
        self.assertEqual(MC.count_em_dashes("a — b --c"), 2)
        self.assertEqual(MC.count_em_dashes("word---word"), 1)


class Buzzword(unittest.TestCase):
    def test_bad(self):
        self.assertEqual(snippets("marketing-buzzword", page("<p>Secure Storage Enterprise-grade security for all.</p>")),
                         ['1 buzzword phrase: "ure Storage Enterprise-grade security fo"'])

    def test_good(self):
        self.assertEqual(snippets("marketing-buzzword", page("<p>Backups every hour, restored in a click.</p>")), [])


class Aphoristic(unittest.TestCase):
    def test_bad_three(self):
        body = "<p>Not a feature. A platform.</p><p>Not a tool. A partner.</p><p>Ship it fast. No meetings needed.</p>"
        s = snippets("aphoristic-cadence", page(body))
        self.assertEqual(s, ['3 aphoristic constructions: "Not a feature. A platform."'])

    def test_good_two(self):
        body = "<p>Not a feature. A platform.</p><p>Not a tool. A partner.</p>"
        self.assertEqual(snippets("aphoristic-cadence", page(body)), [])


class RepeatedContainerText(unittest.TestCase):
    CSS = ".card{border:1px solid #ddd;border-radius:10px;background:#fff}"

    def test_bad(self):
        body = ('<div class="card"><div class="h"><span class="big">Suspended</span></div>'
                '<div class="m"><span class="tag">Suspended</span></div><p>Now <b>Suspended</b> here.</p></div>')
        self.assertEqual(snippets("repeated-container-text", page(body, self.CSS)),
                         ['"Suspended" rendered 3× in distinct spots inside div.card'])

    def test_good_parallel_rows_and_two_spots(self):
        body = ('<div class="card"><div class="r"><span>On schedule</span></div><div class="r"><span>On schedule</span></div>'
                '<div class="r"><span>On schedule</span></div></div>'
                '<div class="card"><i class="a">Rescheduled</i><b class="b">Rescheduled</b></div>')
        self.assertEqual(snippets("repeated-container-text", page(body, self.CSS)), [])

    def test_good_not_a_card(self):
        body = '<div><span class="a">Suspended</span><em>Suspended</em><b>Suspended</b></div>'
        self.assertEqual(snippets("repeated-container-text", page(body)), [])


class RuleSet(unittest.TestCase):
    def test_blinking_cursor_left_out(self):
        self.assertNotIn("blinking-cursor", MC.RULES)
        self.assertEqual(len(MC.RULES), 8)


class Ignores(unittest.TestCase):
    F = [{"rule": "bounce-easing", "line": 3}, {"rule": "overused-font", "line": 4}, {"rule": "em-dash-overuse", "line": 0}]

    def rules(self, text):
        return [f["rule"] for f in ignores.apply(list(self.F), text)]

    def test_file_wide(self):
        self.assertEqual(self.rules("<!-- impeccable-disable em-dash-overuse -- exported -->"),
                         ["bounce-easing", "overused-font"])
        self.assertEqual(self.rules("/* impeccable-disable */"), [])
        self.assertEqual(self.rules("// impeccable-disable *"), [])

    def test_disable_line(self):
        text = "a\nb\nx /* impeccable-disable-line bounce-easing */\nd"
        self.assertEqual(self.rules(text), ["overused-font", "em-dash-overuse"])

    def test_disable_next_line_with_reason(self):
        text = "a\nb\nc\n// impeccable-disable-next-line overused-font: brand font\n"
        self.assertEqual(self.rules(text), ["bounce-easing", "overused-font", "em-dash-overuse"])
        text = "a\nb\n{/* impeccable-disable-next-line overused-font, bounce-easing */}\n"
        self.assertEqual(self.rules(text), ["bounce-easing", "em-dash-overuse"])

    def test_line_zero_only_file_wide(self):
        text = "<!-- impeccable-disable-line em-dash-overuse -->"
        self.assertIn("em-dash-overuse", self.rules(text))

    def test_not_a_directive(self):
        self.assertEqual(len(self.rules("/* impeccable: ignore overused-font */")), 3)

    def test_element_helper(self):
        doc = engine.Context("t.html", '<div data-impeccable-ignore="pulsing-dot, side-tab"><p id="x">a</p></div>'
                             '<div data-impeccable-ignore><i id="y">b</i></div><b id="z">c</b>', "html").doc
        p, i, b = (next(n for n in doc.iter() if n.id == k) for k in ("x", "y", "z"))
        self.assertTrue(ignores.ignored(p, "side-tab"))
        self.assertFalse(ignores.ignored(p, "marquee"))
        self.assertTrue(ignores.ignored(i, "anything"))
        self.assertFalse(ignores.ignored(b, "side-tab"))


if __name__ == "__main__":
    unittest.main()
