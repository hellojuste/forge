"""rules_type.py — typography rules (impeccable static engine, Apache-2.0 port; per-rule upstream fn in PORT_MAP.md).

Element rules (any fragment): italic-serif-display, hero-eyebrow-chip, oversized-h1 and the check_quality group
(tight-leading, justified-text, tiny-text, undersized-ui-text, all-caps-body, wide-tracking,
extreme-negative-tracking). Page rules (ctx.full_page): overused-font, flat-type-hierarchy, kicker-above-heading,
numbered-section-labels, skipped-heading. design-system-font / design-system-font-size read ctx.design.
line-length is browser-only upstream (rect-gated) and lives in rendered.py.

Upstream quirks kept on purpose: no UA heading sizes (core), line-height / letter-spacing resolve to px at the
element that declares them and inherit as px (helper _declared_px below, since core keeps CSS inheritance), and
`has_direct_text` means ONE direct text node longer than 10 chars.
"""
import math
import re

from . import color as C
from . import css as CSS

# --- small JS-compatible helpers -------------------------------------------------------------------------------------


def len16(s):
    return sum(2 if ord(c) > 0xFFFF else 1 for c in s)


def prefix16(s, n):
    out, k = [], 0
    for c in s:
        w = 2 if ord(c) > 0xFFFF else 1
        if k + w > n:
            break
        out.append(c)
        k += w
    return "".join(out)


def collapse(s):
    return re.sub(r"\s+", " ", s or "").strip()


def jsround(x):
    return math.floor(x + 0.5)


def num(x):
    """JS Number#toString for the values snippets print."""
    if x == int(x) and abs(x) < 1e21:
        return str(int(x))
    return repr(float(x))


def fixed2(x):
    return "%.2f" % x


def parse_float(v):
    m = re.match(r"^\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?)", v or "", re.I)
    return float(m.group(1)) if m else float("nan")


def resolve_length_px(v, fs):
    """checks.mjs#resolveLengthPx: px / rem*16 / em*fs / %*fs / unitless*fs; None for normal/auto/inherit/NaN."""
    if v is None:
        return None
    v = v.strip()
    if not v or v in ("normal", "auto", "inherit"):
        return None
    n = parse_float(v)
    if math.isnan(n):
        return None
    if v.endswith("px"):
        return n
    if v.endswith("rem"):
        return n * 16
    if v.endswith("em"):
        return n * fs
    if v.endswith("%"):
        return n / 100 * fs
    return n * fs


# --- DOM helpers -----------------------------------------------------------------------------------------------------
NON_RENDERED_TAGS = {"script", "style", "title", "noscript", "template", "head", "meta", "link", "base", "param",
                     "source", "track", "datalist", "col", "colgroup", "area"}
HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")


def st(n):
    return n.style or {}


def sv(n, prop, default=""):
    v = st(n).get(prop)
    return default if v is None else str(v).strip()


def text_nodes(n):
    return [c for c in n.children if isinstance(c, str)]


def direct_text(n):
    return "".join(text_nodes(n))


def has_direct_gt(n, k):
    return any(len16(t.strip()) > k for t in text_nodes(n))


def text_content(n):
    """domutils textContent: every descendant text node (script/style included), no separator."""
    out = []
    for c in n.children:
        out.append(c if isinstance(c, str) else text_content(c))
    return "".join(out)


def clean_inline_text(n):
    return collapse(" ".join(text_nodes(n)))


def font_px(n):
    return float(st(n).get("__font_px__", CSS.DEFAULT_FONT_PX))


_SEL_LISTS = {}


def _sels(sel):
    if sel not in _SEL_LISTS:
        _SEL_LISTS[sel] = CSS.split_selectors(sel)
    return _SEL_LISTS[sel]


def is_match(n, sel):
    return n is not None and not n.tag.startswith("#") and any(CSS.matches(n, s) for s in _sels(sel))


def closest(n, sel):
    for x in [n] + list(n.ancestors()):
        if is_match(x, sel):
            return x
    return None


def contains(a, b):
    return b is a or any(x is a for x in b.ancestors())


def elements(doc, tags):
    return [n for n in doc.iter() if n.tag in tags]


def _declared_px(n, prop):
    """Upstream normalises line-height / letter-spacing to px at the declaring element (base = its font size) and
    children inherit that px. Find the nearest declaring element and resolve there. None for normal/undeclared."""
    for x in [n] + list(n.ancestors()):
        raw = st(x).get("__raw__") or {}
        if prop in raw:
            v = sv(x, prop)
            if v.lower() in ("normal", ""):
                return None
            return resolve_length_px(v, font_px(x))
    return None


def full_page(ctx):
    """page.mjs#isFullPage: doctype / <html> / <head> in the text with HTML comments stripped (ctx.full_page also
    accepts <body> and does not strip comments, so a commented `<html>` would wrongly count)."""
    t = re.sub(r"<!--[\s\S]*?-->", "", ctx.text)
    return re.search(r"(?i)<!doctype\s|<html[\s>]|<head[\s>]", t) is not None


def is_accent_color(s):
    """checks.mjs#isAccentColor: rgb/hex spread >= 40, oklch chroma >= 0.05, hsl saturation >= 20%."""
    s = (s or "").strip().lower()
    if not s:
        return False
    if s.startswith("oklch("):
        nums = re.findall(r"\d*\.\d+|\d+", s)
        return len(nums) >= 2 and float(nums[1]) >= 0.05
    m = re.match(r"hsla?\(\s*[0-9.]+\s*,\s*([0-9.]+)%", s)
    if m:
        return float(m.group(1)) >= 20
    if s.startswith("hsl"):
        return False
    c = C.parse_color(s)
    return c is not None and max(c[:3]) - min(c[:3]) >= 40


# --- shared constants ------------------------------------------------------------------------------------------------
OVERUSED_FONTS = ["inter", "roboto", "open sans", "lato", "montserrat", "arial", "helvetica", "fraunces",
                  "instrument sans", "instrument serif", "geist", "geist sans", "geist mono", "mona sans",
                  "plus jakarta sans", "space grotesk", "recoleta"]
CSS_GENERIC_FONTS = {"serif", "sans-serif", "monospace", "cursive", "fantasy", "inherit", "initial", "unset", "revert"}
GENERIC_FONTS = CSS_GENERIC_FONTS | {"system-ui", "ui-serif", "ui-sans-serif", "ui-monospace", "ui-rounded",
                                     "-apple-system", "blinkmacsystemfont", "segoe ui"}
KNOWN_SERIF_FONTS = {"fraunces", "recoleta", "newsreader", "playfair display", "playfair", "cormorant",
                     "cormorant garamond", "garamond", "eb garamond", "tiempos", "tiempos headline", "tiempos text",
                     "lora", "vollkorn", "spectral", "source serif pro", "source serif 4", "source serif",
                     "ibm plex serif", "merriweather", "libre caslon", "libre baskerville", "baskerville", "georgia",
                     "times new roman", "times", "dm serif display", "dm serif text", "instrument serif",
                     "gt sectra", "ogg", "canela", "freight display", "freight text"}
SR_ONLY = ('.sr-only, .visually-hidden, .visuallyhidden, .screen-reader, .screen-reader-only, .screenreader, '
           '.a11y-hidden, .hidden-visually, [class*="sr-only" i], [class*="visually-hidden" i], '
           '[class*="visuallyhidden" i], [class*="screen-reader" i], [class*="screenreader" i]')
QUALITY_TEXT_TAGS = {"p", "li", "td", "th", "dd", "blockquote", "figcaption"}


def _cls(*names):
    return ", ".join('[class*="%s" i]' % c for c in names)


TINY_TEXT_UI_CONTEXT = ('button, a, label, summary, pre, [role="button"], [role="link"], [role="tab"], '
                        '[role="menuitem"], [role="option"], nav, footer, [aria-hidden="true"], ' +
                        _cls("badge", "caption", "chip", "code", "console", "diff", "label", "meta", "mock", "pill",
                             "preview", "tag", "terminal", "writes"))
EXEMPT_CONTEXT = ('pre, code, kbd, samp, var, svg, [aria-hidden="true"], ' +
                  _cls("terminal", "console", "code", "mock", "editor", "syntax", "diff"))
INTERACTIVE = ('a[href], button, summary, label, select, textarea, [role="button"], [role="link"], [role="tab"], '
               '[role="menuitem"], [role="menuitemcheckbox"], [role="menuitemradio"], [role="option"], '
               '[role="checkbox"], [role="radio"], [role="switch"], [role="treeitem"]')
FURNITURE_ELEMENTS = ('nav, [role="navigation"], td, th, [role="gridcell"], [role="cell"], caption, figcaption, dt, '
                      'dd, footer')
FURNITURE_CLASSES = _cls("meta", "label", "badge", "chip", "pill", "tag", "kicker", "eyebrow", "breadcrumb",
                         "timestamp", "category", "caption", "nav")
SMALLPRINT = "small, footer, " + _cls("legal", "copyright", "fineprint", "fine-print", "smallprint", "small-print",
                                      "disclaimer", "disclosure", "footnote")
KICKER_SKIP = ('nav,form,table,thead,tbody,tfoot,figure,figcaption,ol,ul,li,[role="navigation"],'
               '[aria-label*="breadcrumb" i],[class*="breadcrumb" i],[aria-hidden="true"],'
               '[data-impeccable-allow-kickers]')
KICKER_CARD = 'article,button,a,li,[role="listitem"],[role="option"]'
APP_CONTEXT = '[role="tabpanel"],[role="dialog"],[role="application"],dialog'
FOOTER_SELECTOR = 'footer, [role="contentinfo"], #footer'


def is_heading_el(n):
    return n.tag in HEADINGS or (n.get("role") or "").strip().lower() == "heading"


def is_non_rendered_text(n):
    """checks.mjs#isNonRenderedText."""
    if n.tag in NON_RENDERED_TAGS or any(a.tag == "head" for a in n.ancestors()):
        return True
    return sv(n, "display").lower() == "none" or sv(n, "visibility").lower() in ("hidden", "collapse")


def is_visually_hidden(n):
    """checks.mjs#isVisuallyHidden (clip/clip-path branches are dead in upstream's static cascade)."""
    if closest(n, SR_ONLY):
        return True
    if sv(n, "position") in ("absolute", "fixed"):
        w, h = parse_float(sv(n, "width")), parse_float(sv(n, "height"))
        if (w == 1 or h == 1) and sv(n, "overflow") in ("hidden", "clip"):
            return True
    return False


def is_heading_text(n):
    """quality.rs is_heading_text: inside a heading with no reading block (QUALITY_TEXT_TAGS) in between."""
    hd = closest(n, 'h1, h2, h3, h4, h5, h6, [role="heading"]')
    if hd is None:
        return False
    x = n
    while x is not None and x is not hd:
        if x.tag in QUALITY_TEXT_TAGS:
            return False
        x = x.parent
    return True


def is_in_control(n):
    if closest(n, INTERACTIVE):
        return True
    for x in [n] + list(n.ancestors()):
        ti = x.get("tabindex")
        if ti is not None:
            idx = parse_float(ti.strip())
            if not (math.isfinite(idx) and idx < 0) and len16(collapse(text_content(x))) <= 80:
                return True
    return False


# --- advisory demoters (text_context.rs) ------------------------------------------------------------------------------
FINE_MARKERS = ["legal", "copyright", "fineprint", "fine-print", "smallprint", "small-print", "disclaimer",
                "disclosure", "footnote", "terms"]


def _words(token):
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", token)
    return [w for w in re.split(r"[-_\s]+", s.lower()) if w]


def _has_fine_marker(text):
    for tok in (text or "").split():
        words = _words(tok)
        for m in FINE_MARKERS:
            parts = m.split("-")
            k = len(parts)
            for i in range(len(words) - k + 1):
                w = words[i:i + k]
                if w[:-1] == parts[:-1] and (w[-1] == parts[-1] or w[-1] == parts[-1] + "s"):
                    return True
    return False


def is_fine_print(n):
    """text_context.rs#is_fine_print."""
    if is_heading_el(n):
        return False
    if not 0 < font_px(n) < 15:
        return False
    for x in [n] + list(n.ancestors()):
        if x.tag == "label" or is_heading_el(x):
            return False
        if x.tag in ("html", "body", "main"):
            break
    if any(c.tag in ("input", "select", "textarea", "button") for c in n.elements()):
        return False

    def check(k):
        return k.tag == "input" and (k.get("type") or "").strip().lower() in ("checkbox", "radio")

    def wraps(k, d):
        return check(k) or (d > 0 and any(wraps(c, d - 1) for c in k.elements()))

    if n.parent is not None:
        sib = n.parent.elements()
        i = sib.index(n)
        for k in ([sib[i - 1]] if i > 0 else []) + ([sib[i + 1]] if i + 1 < len(sib) else []):
            if check(k) or (not collapse(text_content(k)) and wraps(k, 3)):
                return False
    x = n
    for _ in range(4):
        if x is None or x.tag in ("html", "body", "main", "article", "form", "#document"):
            break
        if x.tag == "small" or _has_fine_marker(x.get("class")) or _has_fine_marker(x.get("id")):
            return True
        x = x.parent
    text = collapse(text_content(n))
    if len(text) < 60:
        return False
    if text[:1] in "*†‡§¹²³⁴⁵⁶⁷⁸⁹":
        return True
    kids = n.elements()
    if kids and kids[0].tag == "sup":
        mark = collapse(text_content(kids[0]))
        return 0 < len(mark) <= 3 and text.startswith(mark) and len(collapse(direct_text(n))) >= 30
    return False


MOCK_UI_PARTS = {"app", "browser", "chrome", "dashboard", "desktop", "device", "editor", "frame", "laptop", "phone",
                 "screen", "terminal", "ui", "window"}
MOCK_COPY_PARTS = {"attribution", "caption", "captions", "copyright", "credit", "credits", "license", "licence"}
MOCK_SKIP = {"html", "body", "main", "section", "article", "header", "footer", "nav", "aside", "figcaption"}


def _token_parts(tok):
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", tok)
    return [p for p in re.split(r"[-_:/.\s]+", s.lower()) if p]


def _mock_marker(text):
    for tok in (text or "").split():
        p = set(_token_parts(tok))
        if p & MOCK_COPY_PARTS:
            continue
        if p & {"mockup", "mockups", "illustration", "illustrations"} or ("mock" in p and p & MOCK_UI_PARTS):
            return True
    return False


def _sentence_copy(t):
    w = len(t.split())
    return w >= 8 or (w >= 5 and t.rstrip().endswith((".", "!", "?", "。", "！", "？")))


def in_mock_context(n):
    """decorative_text classify == Mockup (role=img picture, or a mockup class marker; framed-demo walk omitted)."""
    chain = [n] + list(n.ancestors())
    in_svg = any(x.tag == "svg" for x in chain)
    marked = False
    for x in chain:
        if x.tag == "figcaption":
            return False
        if not in_svg and (x.get("role") or "").strip().lower() == "img":
            return True
        if x.tag == "svg":
            in_svg = False
        if x.tag not in MOCK_SKIP and (_mock_marker(x.get("class")) or _mock_marker(x.get("id"))):
            marked = True
            break
    text = collapse(text_content(n))
    return marked and bool(text) and not _sentence_copy(text)


MICRO_STOP_TAGS = {"a", "button", "label", "summary", "select", "option", "textarea", "nav", "form", "td", "th",
                   "dt", "dd", "legend", "figcaption", "caption", "time"}
MICRO_STOP_ROLES = {"button", "link", "tab", "menuitem", "option", "checkbox", "radio", "switch", "navigation",
                    "cell", "gridcell", "tooltip", "alert", "status"}
UNITS = {"%", "d", "day", "days", "h", "hr", "hrs", "hour", "hours", "m", "min", "mins", "minute", "minutes", "s",
         "sec", "secs", "second", "seconds", "ms", "wk", "wks", "week", "weeks", "mo", "mos", "month", "months", "yr",
         "yrs", "year", "years", "kb", "mb", "gb", "tb", "px", "pt", "hz", "khz", "mhz", "ghz", "fps", "bpm", "rpm",
         "km", "cm", "mm", "mi", "ft", "kg", "g", "mg", "lb", "lbs", "oz", "ml", "l", "kwh", "kw", "w", "v", "mph",
         "kph", "°c", "°f", "°", "x", "pts"}
MONEY = set("$€£¥₩₹₽₺₫฿")


def _few_words(t, mw, mc):
    return bool(t) and len(t.split()) <= mw and len(t) <= mc and not (set(t) & MONEY) \
        and not t.endswith((".", "!", "?", "。", "！", "？"))


def _holds_heading(n, leading, depth):
    if is_heading_el(n):
        return True
    if depth == 0:
        return False
    kids = n.elements()
    if not kids:
        return False
    return _holds_heading(kids[0] if leading else kids[-1], leading, depth - 1)


def _display_title(n, label_px):
    t = collapse(text_content(n))
    return bool(t) and collapse(direct_text(n)) == t and len(t.split()) <= 8 and not _sentence_copy(t) \
        and not (set(t) & MONEY) and not any(c.isdigit() for c in t) and sum(c.isalpha() for c in t) >= 2 \
        and font_px(n) >= 18 and font_px(n) >= label_px * 1.5


def _is_pill(n):
    rad = CSS.length_px(sv(n, "border-radius").split()[0] if sv(n, "border-radius") else "") or 0
    bg = C.parse_color(sv(n, "background-color"))
    img = sv(n, "background-image")
    border = any((CSS.length_px(sv(n, "border-%s-width" % s)) or 0) > 0 for s in CSS.SIDES)
    return rad > 0 and ((bg is not None and bg[3] > 0.1) or (img and img != "none") or border)


def _beside_heading(el):
    label_px = font_px(el)
    pill = _is_pill(el)

    def beside(n):
        if n.parent is None:
            return False
        sib = n.parent.elements()
        i = sib.index(n)
        prev = sib[i - 1] if i > 0 else None
        nxt = sib[i + 1] if i + 1 < len(sib) else None
        opens = all(not collapse(text_content(s)) for s in sib[:i])
        return (opens and nxt is not None and (_holds_heading(nxt, True, 2) or _display_title(nxt, label_px))) or \
            ((pill or _is_pill(n)) and prev is not None and
             (_holds_heading(prev, False, 2) or _display_title(prev, label_px)))
    if beside(el):
        return True
    p = el.parent
    return p is not None and not p.tag.startswith("#") and len(p.elements()) == 1 \
        and not collapse(direct_text(p)) and beside(p)


def is_micro_label(n):
    """text_context.rs#is_micro_label (chart-label branch reduced to a class/id marker walk)."""
    t = collapse(text_content(n))
    if not t or collapse(direct_text(n)) != t or is_heading_el(n):
        return False
    for x in [n] + list(n.ancestors()):
        if x.tag in MICRO_STOP_TAGS or (x.get("role") or "").strip().lower() in MICRO_STOP_ROLES or is_heading_el(x):
            return False
        if x.tag in ("html", "body", "main"):
            break
    if set(t) & MONEY:
        return False
    sib = n.parent.elements() if n.parent is not None else [n]
    i = sib.index(n)
    near = [s for s in (sib[i - 1] if i > 0 else None, sib[i + 1] if i + 1 < len(sib) else None) if s is not None]
    lp = font_px(n)
    if t.rstrip(".").lower() in UNITS and any(
            re.match(r"^[+\-−~≈<>]?\d[\d.,:]*[kKmMbB+]?$", collapse(text_content(s))) and font_px(s) >= lp * 1.3
            for s in near):
        return True
    if re.match(r"(?i)^(?:0\d|\d{1,2}[.)]|(?:step|no\.?|#)\s?\d{1,2})$", t) and any(
            s is not n and font_px(s) > lp and sum(c.isalpha() for c in collapse(text_content(s))) >= 2 for s in sib):
        return True
    if _few_words(t, 3, 16):
        x = n
        for _ in range(5):
            if x is None or x.tag.startswith("#"):
                break
            parts = set(_token_parts(x.get("class") or "")) | set(_token_parts(x.get("id") or ""))
            if parts & {"axis", "chart", "charts", "gauge", "graph", "histogram", "plot", "sparkline", "tick",
                        "ticks", "xaxis", "yaxis"}:
                return True
            x = x.parent
    return _few_words(t, 4, 32) and "%" not in t and not any(c.isdigit() for c in t) and _beside_heading(n)


# =====================================================================================================================
# Page rules
# =====================================================================================================================
OVERUSED_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "td", "th", "dd", "blockquote", "figcaption", "a",
                 "button", "label", "span", "div"}


def _font_token(f):
    t = f.strip()
    t = t[1:] if t[:1] in "'\"" else t
    t = t[:-1] if t[-1:] in "'\"" else t
    return t.lower()


def overused_font(ctx):
    """detect-html.mjs#checkStaticPageTypography (overused half)."""
    if not full_page(ctx):
        return
    seen = []
    for n in ctx.doc.iter():
        if n.tag not in OVERUSED_TAGS or not any(t.strip() for t in text_nodes(n)):
            continue
        toks = [_font_token(f) for f in sv(n, "font-family").split(",")]
        p = next((t for t in toks if t and t not in CSS_GENERIC_FONTS), None)
        if p in OVERUSED_FONTS and p not in seen:
            seen.append(p)
    for p in seen:
        yield ("overused-font", "Primary font: %s" % p)


TYPE_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "td", "th", "dd", "blockquote", "figcaption"}


def _rendered_type(n):
    for x in [n] + list(n.ancestors()):
        if "hidden" in x.attrs:
            return False
        if sv(x, "display").lower() == "none" or sv(x, "visibility").lower() in ("hidden", "collapse"):
            return False
        op = parse_float(sv(x, "opacity"))
        if math.isfinite(op) and op <= 0.01:
            return False
    return True


def _parse_weight(v):
    v = (v or "400").strip().lower()
    if v == "normal":
        return 400.0
    if v == "bold":
        return 700.0
    n = parse_float(v)
    return n if math.isfinite(n) and 1 <= n <= 1000 else float("nan")


def _type_samples(doc):
    out = []
    for n in doc.iter():
        if n.tag not in TYPE_TAGS or not text_content(n).strip() or not _rendered_type(n):
            continue
        size = font_px(n)
        if not math.isfinite(size) or size < 8 or size >= 200:
            continue
        out.append((n.tag if n.tag in HEADINGS else "body", size, _parse_weight(st(n).get("font-weight"))))
    return out


def _dominant(role, sizes):
    counts = {}
    for s in sizes:
        counts[s] = counts.get(s, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        if role != "h1":
            return None
        return max(s for s, c in ranked if c == ranked[0][1])
    if role not in ("h1", "body") and len(ranked) > 1 and ranked[1][1] >= ranked[0][1] * 0.75 \
            and ranked[1][0] >= ranked[0][0] * 1.25:
        return None
    return ranked[0][0]


def _weight_separates(samples):
    body, heads = {}, []
    for role, size, w in samples:
        size = jsround(size * 10) / 10
        if not (8 <= size < 200) or not math.isfinite(w):
            continue
        if role == "body":
            body[w] = body.get(w, 0) + 1
        else:
            heads.append(w)
    if not body or not heads:
        return False
    bw = sorted(body.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    return sum(1 for w in heads if w >= bw + 200) >= 0.8 * len(heads)


def _step(sizes):
    step = 1.0
    for i in range(1, len(sizes)):
        step = max(step, sizes[i] / sizes[i - 1])
    return step


def flat_type_hierarchy(ctx):
    """checks.mjs#checkFlatTypeHierarchySamples + flat_type_hierarchy_severity."""
    if not full_page(ctx):
        return
    samples = _type_samples(ctx.doc)
    by_role = {}
    for role, size, _ in samples:
        size = jsround(size * 10) / 10
        if 8 <= size < 200:
            by_role.setdefault(role, []).append(size)
    settled = dropped = 0
    dropped_sizes, roles = [], []
    for role, sizes in by_role.items():
        d = _dominant(role, sizes)
        if d is not None:
            settled += len(sizes) if role != "body" else 0
            roles.append((role, d))
        elif role != "body":
            dropped += len(sizes)
            dropped_sizes += sizes
    if len(roles) < 3:
        return
    rd = dict(roles)
    if "h1" in rd and "body" in rd and rd["h1"] < rd["body"]:
        return
    roles.sort(key=lambda r: (r[1], r[0]))
    ladder = [s for _, s in roles]
    step = _step(ladder)
    if step >= 1.25:
        return
    if dropped > settled and any(_step(sorted(ladder + [x])) >= 1.25 for x in dropped_sizes):
        return
    sep = _weight_separates(samples)
    snip = "Role sizes: %s (largest adjacent step %s:1; target 1.25:1%s)" % (
        ", ".join("%s %spx" % (r, num(s)) for r, s in roles), fixed2(step),
        "; weight separates headings from body text" if sep else "")
    hit = {"rule": "flat-type-hierarchy", "snippet": snip}
    if sep:
        hit["severity"] = "advisory"
    yield hit


META_RE = re.compile(r"[·•|]|\s[/›»>]\s|\b(19|20)\d{2}\b")
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
DOC_NUM_RE = re.compile(r"(?i)^(§|\d+(\.\d+)+\b|(section|article|clause|appendix|exhibit|schedule|chapter|part|rule|"
                        r"title)\s+([0-9ivxlcIVXLC]+\b|one|two|three|four|five|six|seven|eight|nine|ten|eleven|"
                        r"twelve)\b)")


def _strip_edge_quotes(t):
    if t.startswith('"'):
        t = t[1:]
    if t.endswith('"'):
        t = t[:-1]
    return t


def _label_ceiling(hfs, base):
    rel = hfs * 0.45 if math.isfinite(hfs) and hfs > 0 else 0.0
    return max(base, min(rel, 16.0))


def _heading_level(h):
    m = re.match(r"^h([1-6])$", h.tag)
    if m:
        return int(m.group(1))
    if (h.get("role") or "").lower() != "heading":
        return 0
    lv = parse_float(h.get("aria-level") or "")
    return int(lv) if math.isfinite(lv) and lv >= 1 else 2


def _tracked(ls, fs):
    """rules_types.rs#hero_eyebrow_tracked with the 0.08em floor."""
    return ls >= 1.6 or (fs > 0 and ls > 0 and ls >= fs * 0.08 - 1e-9)


def kicker_above_heading(ctx):
    """checks.mjs#collectKickerCandidates + isKickerCandidate."""
    if not full_page(ctx):
        return
    for h in ctx.doc.iter():
        if not (h.tag in ("h1", "h2", "h3", "h4") or (h.get("role") or "").lower() == "heading"):
            continue
        lvl = _heading_level(h)
        if not lvl or lvl > 4 or closest(h, KICKER_SKIP) or closest(h, APP_CONTEXT):
            continue
        k = h.prev_element()
        if k is None or closest(k, KICKER_SKIP):
            continue
        item = closest(h, KICKER_CARD)
        if item is not None and contains(item, k):
            continue
        htext = collapse(text_content(h))
        ktext = clean_inline_text(k) or collapse(text_content(k))
        hfs, kfs = font_px(h), font_px(k)
        kls = _declared_px(k, "letter-spacing") or 0.0
        if len16(htext) < 3 or re.match(r"^/[0-9A-Za-z_-]+", _strip_edge_quotes(htext).strip()) or hfs < 20:
            continue
        if k.tag not in ("p", "span", "div", "small") or not 2 <= len16(ktext) <= 34:
            continue
        if re.match(r"(?i)^step\s*\d+", ktext) or re.match(r"^\d{1,2}$", ktext) or META_RE.search(ktext) \
                or DOC_NUM_RE.match(ktext):
            continue
        variant = sv(k, "font-variant") + " " + sv(k, "font-variant-caps")
        upper = sv(k, "text-transform") == "uppercase" or (re.search(r"[A-Z]", ktext) and not re.search(r"[a-z]", ktext)) \
            or "small-caps" in variant
        if not upper or not 0 < kfs <= _label_ceiling(hfs, 14.0) or not kls >= kfs * 0.06:
            continue
        if h.tag == "h1" and hfs >= 48 and (kls >= 1.6 or (kfs <= 14 and _tracked(kls, kfs) and _hero_hits(h))):
            continue
        yield ("kicker-above-heading", 'kicker "%s" above %s "%s"' % (
            prefix16(ktext, 40), h.tag, prefix16(_strip_edge_quotes(htext), 60)))


def _parse_numbered(raw):
    t = collapse(raw)
    if not t or len16(t) > 40:
        return None
    m = re.match(r"^(\d{2})$", t) or re.match(r"^(\d{1,2})\s*[^0-9A-Za-z_\s]\s*\S", t)
    if not m or int(m.group(1)) > 40:
        return None
    return int(m.group(1)), t


def numbered_section_labels(ctx):
    """checks.mjs#collectNumberedSectionLabelCandidates + checkNumberedSectionLabels (min 2, >= 2 distinct)."""
    if not full_page(ctx):
        return
    cands, used = [], set()
    for h in ctx.doc.iter():
        if h.tag not in ("h2", "h3", "h4") or closest(h, KICKER_SKIP):
            continue
        label = h.prev_element()
        if label is None and h.parent is not None and h.parent.elements()[:1] == [h]:
            label = h.parent.prev_element() if not h.parent.tag.startswith("#") else None
        if label is None or id(label) in used or closest(label, KICKER_SKIP) or label.tag in HEADINGS:
            continue
        item = closest(h, KICKER_CARD)
        if item is not None and contains(item, label):
            continue
        if any(d.tag in ("img", "picture", "video", "canvas") for d in label.iter()):
            continue
        if any(d.tag == "svg" and d.parent is not None and _parse_numbered(direct_text(d.parent))
               for d in label.iter()):
            continue
        parsed = _parse_numbered(clean_inline_text(label) or collapse(text_content(label)))
        if not parsed:
            continue
        htext = collapse(text_content(h))
        hfs, lfs = font_px(h), font_px(label)
        if len16(htext) < 3 or label.tag not in ("span", "p", "div", "small", "em", "strong", "b"):
            continue
        if not 0 < lfs <= _label_ceiling(hfs, 13.0) or (hfs > 0 and hfs < lfs * 1.3):
            continue
        w = parse_float(sv(label, "font-weight") or "400")
        w = w if math.isfinite(w) and w else 400
        ls = _declared_px(label, "letter-spacing") or 0.0
        if not (re.search(r"(?i)mono", sv(label, "font-family")) or w >= 600 or ls >= 0.5
                or sv(label, "text-transform") == "uppercase" or is_accent_color(sv(label, "color"))):
            continue
        used.add(id(label))
        cands.append((parsed[0], prefix16(parsed[1], 24), h.tag, prefix16(_strip_edge_quotes(htext), 60)))
    if len(cands) < 2 or len({c[0] for c in cands}) < 2:
        return
    for idx, lt, tag, ht in cands:
        yield ("numbered-section-labels", 'tiny numbered label "%s" beside %s "%s" (%d on page)' % (lt, tag, ht, len(cands)))


def skipped_heading(ctx):
    """checks.mjs#checkPageQualityFromDoc (a skip into the footer is excused)."""
    if not full_page(ctx):
        return
    prev_level, prev_text, prev_footer, prev_opens = 0, "", None, False
    for h in ctx.doc.iter():
        if h.tag not in HEADINGS:
            continue
        level = int(h.tag[1])
        text = prefix16(collapse(text_content(h)), 60)
        footer = closest(h, FOOTER_SELECTOR)
        opens = footer is not None and footer is not prev_footer
        into = footer is not None and (opens or prev_opens)
        cont = prev_level > 0
        skips = cont and level > prev_level + 1
        if skips and not into:
            yield ("skipped-heading", '<h%d> "%s" followed by <h%d> "%s" (missing h%d)' % (
                prev_level, prev_text, level, text, prev_level + 1))
        prev_level, prev_text, prev_footer = level, text, footer
        prev_opens = opens and cont and not skips


# =====================================================================================================================
# Element rules
# =====================================================================================================================
def hero_px(raw):
    """checks.mjs#resolveHeroHeadingSizePx: px / (r)em*16 / %*0.16 / clamp() max endpoint."""
    v = (raw or "").strip().lower()

    def simple(t):
        m = re.match(r"^(-?\d*\.?\d+)\s*(px|rem|em|%)?$", t.strip())
        if not m:
            return None
        n = float(m.group(1))
        return n * 16 if m.group(2) in ("rem", "em") else (n * 0.16 if m.group(2) == "%" else n)
    if not v:
        return 0.0
    d = simple(v)
    if d is not None:
        return d
    m = re.match(r"^clamp\((.*)\)$", v)
    if m:
        parts = m.group(1).split(",")
        if len(parts) == 3:
            b = [x for x in (simple(parts[0]), simple(parts[2])) if x is not None]
            if b:
                return max(b)
    return 0.0


def _hero_size(n):
    """Upstream reads the cascaded px string; core keeps raw values, so a px font size resolves through core."""
    raw = sv(n, "font-size")
    if re.match(r"^[\d.]+(em|%)$", raw.lower()):
        return font_px(n)
    return hero_px(raw) if raw else font_px(n)


def _resolve_serif(ff):
    toks = [_font_token(f) for f in (ff or "").split(",")]
    prim = next((t for t in toks if t and t not in GENERIC_FONTS), None)
    if prim is None:
        return None, False
    return prim, prim in KNOWN_SERIF_FONTS or "serif" in toks


def _hidden_node(x):
    s = st(x)
    op = parse_float(s.get("opacity") or "")
    return (s.get("display") or "").strip() == "none" or (s.get("visibility") or "").strip() in ("hidden", "collapse") \
        or (s.get("content-visibility") or "").strip() == "hidden" or (math.isfinite(op) and op <= 0.01) \
        or x.get("aria-hidden") == "true" or "hidden" in x.attrs


def italic_serif_display(ctx):
    """checks.mjs#checkElementItalicSerif / checkItalicSerif."""
    for h in elements(ctx.doc, ("h1", "h2")):
        pending = [h]
        while pending:
            node = pending.pop()
            if any(_hidden_node(x) for x in [node] + list(node.ancestors())):
                continue
            if direct_text(node).strip():
                s = st(node)
                if (s.get("font-style") or "").strip() == "italic":
                    fs = _hero_size(node)
                    prim, serif = _resolve_serif(s.get("font-family"))
                    if fs >= 48 and serif:
                        yield ("italic-serif-display", 'italic serif %s (%s) at %spx "%s"' % (
                            h.tag, prim or "serif", num(jsround(fs)), prefix16(text_content(h).strip(), 60)))
                        break
            pending.extend(reversed(node.elements()))


def _accent_dash(n):
    for pd in (n.pseudo or {}).values():
        w = CSS.length_px(pd.get("width") or pd.get("inline-size"))
        h = CSS.length_px(pd.get("height") or pd.get("block-size"))
        if w is None or h is None or not (8 <= w <= 80 and 1 <= h <= 6):
            continue
        cols = C.find_colors(pd.get("background-color") or pd.get("background") or "")
        if cols:
            c = cols[0][1]
            if c[3] >= 0.1 and max(c[:3]) - min(c[:3]) >= 30:
                return True
    return False


def _hero_hit(h):
    sib = h.prev_element()
    if sib is None or _hero_size(h) < 48 or closest(h, APP_CONTEXT) or sib.tag in HEADINGS:
        return None
    text = text_content(sib).strip()
    if not 2 <= len16(text) <= 60:
        return None
    sfs = font_px(sib)
    if not 0 < sfs <= 14:
        return None
    ls = _declared_px(sib, "letter-spacing") or 0.0
    upper = sv(sib, "text-transform") == "uppercase" or (re.search(r"[A-Z]", text) and not re.search(r"[a-z]", text))
    dated = ls < 1.6 and (sib.tag == "time" or any(d.tag == "time" for d in sib.iter()) or YEAR_RE.search(text))
    tracked_caps = bool(upper) and not dated and _tracked(ls, sfs)
    w = parse_float(st(sib).get("font-weight") or "")
    w = w if math.isfinite(w) and w else 400
    accent_bold = w >= 700 and is_accent_color(sv(sib, "color"))
    dash = _accent_dash(sib)
    if not (tracked_caps or accent_bold or dash):
        return None
    style = "tracked-caps" if tracked_caps else ("accent-bold" if accent_bold else "dash-prefix")
    return 'eyebrow chip (%s) "%s" above h1 "%s"' % (style, prefix16(text, 40), prefix16(text_content(h).strip(), 60))


def _hero_hits(h):
    return _hero_hit(h) is not None


def hero_eyebrow_chip(ctx):
    """checks.mjs#checkElementHeroEyebrow / checkHeroEyebrow."""
    for h in elements(ctx.doc, ("h1",)):
        s = _hero_hit(h)
        if s:
            yield ("hero-eyebrow-chip", s)


def oversized_h1(ctx):
    """checks.mjs#checkOversizedH1 (static: no viewport gate)."""
    for h in elements(ctx.doc, ("h1",)):
        fs = font_px(h)
        text = collapse(text_content(h))
        if fs >= 72 and len16(text) >= 40:
            yield ("oversized-h1", '%spx h1, %d chars "%s"' % (num(jsround(fs)), len16(text), prefix16(text, 60)))


# --- check_quality (quality.rs) -------------------------------------------------------------------------------------
def _is_cjk_char(c):
    o = ord(c)
    return (0x1100 <= o <= 0x11FF or 0x3040 <= o <= 0x30FF or 0x3130 <= o <= 0x318F or 0x31F0 <= o <= 0x31FF
            or 0x3400 <= o <= 0x4DBF or 0x4E00 <= o <= 0x9FFF or 0xA960 <= o <= 0xA97F or 0xAC00 <= o <= 0xD7FF
            or 0xF900 <= o <= 0xFAFF or 0xFF66 <= o <= 0xFF9F or 0x20000 <= o <= 0x3FFFF)


def is_cjk_text(t):
    cjk = letters = 0
    for c in t[:256]:
        if _is_cjk_char(c):
            cjk += 1
            letters += 1
        elif c.isalpha():
            letters += 1
    return cjk > 0 and cjk * 2 >= letters


def _no_word_space_script(t):
    ex = other = 0
    for c in t[:400]:
        if not c.isalpha():
            continue
        o = ord(c)
        if (0x0600 <= o <= 0x06FF or 0x0750 <= o <= 0x077F or 0x08A0 <= o <= 0x08FF or 0x0E00 <= o <= 0x0E7F
                or 0x1100 <= o <= 0x11FF or 0x2E80 <= o <= 0x9FFF or 0xA960 <= o <= 0xA97F or 0xAC00 <= o <= 0xD7FF
                or 0xF900 <= o <= 0xFAFF or 0xFB50 <= o <= 0xFDFF or 0xFE70 <= o <= 0xFEFF or 0xFF66 <= o <= 0xFF9F
                or 0x20000 <= o <= 0x3134F):
            ex += 1
        else:
            other += 1
    return ex > other


def _capitalized_run(t):
    up = False
    for c in t:
        if c.islower():
            return False
        if c.isupper():
            up = True
    return up


def _font_weight_number(v):
    v = (v or "").strip().lower()
    if v in ("bold", "bolder"):
        return 700.0
    if v == "lighter":
        return 100.0
    n = parse_float(v)
    return n if math.isfinite(n) else 400.0


def _line_clamp(display, clamp):
    display = display.strip()
    if display in ("-webkit-box", "-webkit-inline-box"):
        return True
    return clamp.strip() not in ("", "none") and display in ("flow-root", "inline-block")


def _measure_px(n, fs):
    x = n
    for _ in range(12):
        if x is None or x.tag.startswith("#"):
            return None
        w = sv(x, "width")
        if not w.endswith("%"):
            px = resolve_length_px(w, fs)
            if px is not None and px > 0:
                return px
        x = x.parent
    return None


def _quality(ctx):
    """checks.mjs#checkQuality static branches, memoised per context (all seven rules come from one pass)."""
    memo = getattr(ctx, "_type_quality", None)
    if memo is not None:
        return memo
    out = []
    for n in ctx.elements():
        tag = n.tag
        if (n.id or "").startswith(("claude-", "cic-")):
            continue
        hdt = has_direct_gt(n, 10)
        tl = len16(text_content(n).strip())
        fs = font_px(n)
        is_h = tag in HEADINGS
        tt = sv(n, "text-transform")
        lh = _declared_px(n, "line-height")
        ls = _declared_px(n, "letter-spacing")
        # tight-leading
        if hdt and tl > 50 and not is_h and lh is not None and 0 < fs < 24:
            ratio = lh / fs
            if ratio > 0 and jsround(ratio * 100) / 100 < 1.3 and not is_non_rendered_text(n) \
                    and not is_visually_hidden(n) and not is_heading_text(n) \
                    and not (_font_weight_number(sv(n, "font-weight")) >= 600
                             and _line_clamp(sv(n, "display"), sv(n, "-webkit-line-clamp"))):
                out.append({"rule": "tight-leading", "snippet": "line-height %sx (need >=1.3)" % fixed2(ratio),
                            "severity": "advisory" if is_fine_print(n) else None})
        # justified-text
        if hdt and sv(n, "text-align") == "justify" and fs > 0:
            hy = sv(n, "hyphens") or sv(n, "-webkit-hyphens")
            m = _measure_px(n, fs)
            if hy != "auto" and m is not None and m / (fs * 0.5) <= 45 and not _no_word_space_script(direct_text(n)):
                out.append(("justified-text", "text-align: justify without hyphens: auto"))
        # tiny-text
        if hdt and tl > 20 and fs < 12 and tag not in ("sub", "sup", "code", "kbd", "samp", "var", "caption",
                                                      "figcaption") \
                and not closest(n, TINY_TEXT_UI_CONTEXT) and tt != "uppercase" and not is_non_rendered_text(n):
            out.append({"rule": "tiny-text", "snippet": "%spx body text" % num(fs),
                        "severity": "advisory" if (is_fine_print(n) or in_mock_context(n)) else None})
        # undersized-ui-text
        dt = collapse(direct_text(n))
        if 0 < fs < 11 and len16(dt) >= 2 and tag not in ("sub", "sup", "option") \
                and not any(a.tag in ("sub", "sup") for a in n.ancestors()) and not is_non_rendered_text(n) \
                and not closest(n, EXEMPT_CONTEXT) and not is_visually_hidden(n):
            inter = is_in_control(n)
            fc = closest(n, FURNITURE_CLASSES)
            furn = closest(n, FURNITURE_ELEMENTS) is not None or (fc is not None and fc.tag != "html")
            floor = 10.0 if (closest(n, SMALLPRINT) and not inter) else 11.0
            if jsround((floor - fs) * 1000) >= 100 and (inter or furn or len16(dt) <= 20):
                adv = not inter and (is_micro_label(n) or in_mock_context(n))
                out.append({"rule": "undersized-ui-text", "snippet": '%spx functional text "%s" (below %spx floor)' % (
                    num(fs), prefix16(dt, 40), num(floor)), "severity": "advisory" if adv else None})
        # all-caps-body
        if hdt and tt == "uppercase" and not is_h:
            own = len16(collapse(direct_text(n)))
            if own >= 80:
                out.append(("all-caps-body", "text-transform: uppercase on %d chars of body text" % own))
        own_t = collapse(text_content(n))
        # wide-tracking
        if hdt and tl > 20 and ls is not None and ls > 0 and fs > 0 and ls / fs > 0.05:
            every = len16(own_t) < 80 and _capitalized_run(own_t) and all(c.isupper() for c in own_t if c.isalpha())
            caps = tt == "uppercase" or (tt != "lowercase" and (every or (tl <= 40 and _capitalized_run(own_t))))
            d = collapse(direct_text(n))
            cjk = is_cjk_text(d if any(c.isalpha() for c in d) else own_t)
            if not caps and not cjk:
                out.append(("wide-tracking", "letter-spacing: %sem on body text" % fixed2(ls / fs)))
        # extreme-negative-tracking
        if hdt and tl > 20 and ls is not None and ls < 0 and fs > 0:
            em = ls / fs
            if em < (-0.09 if fs >= 40 else -0.07) and not is_cjk_text(own_t):
                out.append(("extreme-negative-tracking", 'letter-spacing: %sem at %spx — "%s"' % (
                    fixed2(em), num(fs), prefix16(own_t, 40))))
    for h in out:
        if isinstance(h, dict) and h.get("severity") is None:
            h.pop("severity")
    ctx._type_quality = out
    return out


def _quality_rule(rid):
    def fn(ctx):
        return [h for h in _quality(ctx) if (h["rule"] if isinstance(h, dict) else h[0]) == rid]
    fn.__name__ = rid.replace("-", "_")
    fn.__doc__ = "quality.rs check_quality: %s" % rid
    return fn


# =====================================================================================================================
# Design-system rules (design_system.rs; ctx.design = design_md.parse frontmatter)
# =====================================================================================================================
def _norm_font(v):
    t = re.sub(r"(?i)\s*!important\s*$", "", (v or "").strip()).strip()
    t = re.sub(r"^[\"']|[\"']$", "", t).replace("+", " ")
    return re.sub(r"\s+", " ", t).lower()


def _split_args(s):
    out, depth, cur, quote = [], 0, [], None
    for ch in s:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
            continue
        cur.append(ch)
    if "".join(cur).strip():
        out.append("".join(cur).strip())
    return out


def _declared_stack(stack):
    fonts = []
    for part in _split_args(re.sub(r"(?i)\s*!important\s*$", "", stack)):
        if part[:4].lower() == "var(" and part.endswith(")"):
            args = _split_args(part[4:-1])
            if len(args) > 1:
                fonts += _declared_stack(",".join(args[1:]))
            continue
        f = _norm_font(part)
        if f:
            fonts.append(f)
    return fonts


def primary_font(stack):
    """design-system.mjs#primaryFont."""
    if not stack or re.search(r"(?i)var\(", stack) or re.search(r"[$`{}]|\s\+\s|\|\|", stack):
        return ""
    for f in _split_args(re.sub(r"(?i)\s*!important\s*$", "", stack)):
        f = _norm_font(f)
        if f and f not in GENERIC_FONTS:
            return f
    return ""


def design_system(design):
    """normalizeDesignSystem: allowed fonts + font-size ramp from the frontmatter typography map."""
    typo = design.get("typography") if isinstance(design, dict) else None
    fonts, sizes = [], []

    def step(raw, fluid):
        t = str(raw).strip().lower()
        if re.match(r"^-?[0-9.]+(?:px|rem)$", t):
            px = resolve_length_px(t, 16)
            if px is not None and math.isfinite(px) and px > 0:
                sizes.append((px, fluid))
    if isinstance(typo, dict):
        for role in typo.values():
            if isinstance(role, dict) and isinstance(role.get("fontFamily"), str):
                for f in _declared_stack(role["fontFamily"]):
                    if f not in GENERIC_FONTS and f not in fonts:
                        fonts.append(f)
        scale = typo.get("scale")
        if isinstance(scale, dict):
            for v in scale.values():
                if isinstance(v, (str, int, float)) and not isinstance(v, bool):
                    step(_js_string(v), False)
        for name, role in typo.items():
            if name == "scale" or not isinstance(role, dict):
                continue
            raw = role.get("fontSize")
            raw = "" if raw is None else _js_string(raw).strip().lower()
            args = _clamp_args(raw)
            if args:
                step(args[0], True)
                step(args[2], True)
            else:
                step(raw, False)
    return {"fonts": fonts, "sizes": sizes, "has_fonts": bool(fonts), "has_sizes": any(not f for _, f in sizes)}


def _js_string(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _clamp_args(raw):
    m = re.match(r"(?is)^clamp\(\s*(.+)\s*\)$", (raw or "").strip())
    if not m:
        return None
    a = _split_args(m.group(1))
    return a if len(a) == 3 else None


def _font_allowed(f, ds):
    return not f or f in GENERIC_FONTS or not ds["has_fonts"] or f in ds["fonts"]


def _title(s):
    return re.sub(r"(?<![A-Za-z0-9_])[A-Za-z0-9_]", lambda m: m.group(0).upper(), s)


def _source_lines(text):
    for i, line in enumerate(text.split("\n")):
        t = line.strip()
        if t.startswith(("//", "/*", "*", "<!--")):
            continue
        yield i + 1, line


DS_SKIP_TAGS = {"head", "title", "meta", "link", "style", "script", "noscript", "template", "source"}


def design_system_font(ctx):
    """collectStaticDesignSystemFindings (font half) merged with checkSourceDesignSystem font-family scan."""
    if not ctx.design:
        return
    ds = design_system(ctx.design)
    if not ds["has_fonts"]:
        return
    out, keys = [], {}
    if ctx.doc is not None:
        for n in ctx.doc.iter():
            if n.tag in DS_SKIP_TAGS or any(x.tag in DS_SKIP_TAGS for x in n.ancestors()) or any(
                    "hidden" in x.attrs or x.get("aria-hidden") == "true" or sv(x, "display").lower() == "none"
                    or sv(x, "visibility").lower() in ("hidden", "collapse") for x in [n] + list(n.ancestors())):
                continue
            if not any(t.strip() for t in text_nodes(n)):
                continue
            f = primary_font(sv(n, "font-family"))
            key = "font:" + f
            if f and key not in keys and not _font_allowed(f, ds):
                t = collapse(text_content(n))
                keys[key] = len(out)
                out.append({"rule": "design-system-font", "line": 0, "snippet": "%s%s uses %s; not declared in "
                            "DESIGN.md typography" % (n.tag, ' "%s"' % prefix16(t, 40) if t else "", f)})
    for ln, line in _source_lines(ctx.text):
        found = [("font-family", m.group(1)) for m in re.finditer(r"(?i)font-family\s*:\s*([^;}\n]+)", line)]
        found += [("fontFamily", m.group(1)) for m in re.finditer(r"fontFamily\s*[:=]\s*[\"'`]([^\"'`]+)[\"'`]", line)]
        for ctxname, stack in found:
            p = primary_font(stack)
            if not p or _font_allowed(p, ds):
                continue
            _merge(out, keys, "font:" + p, ln, "%s: %s is not declared in DESIGN.md typography" % (ctxname, _title(p)))
        for m in re.finditer(r"(?i)fonts\.googleapis\.com/css2?\?[^\"'\s)<>]*", line):
            for fm in re.finditer(r"[?&]family=([^&]+)", m.group(0)):
                from urllib.parse import unquote
                disp = unquote(fm.group(1).split(":")[0].replace("+", " "))
                f = _norm_font(disp)
                if f and not _font_allowed(f, ds):
                    _merge(out, keys, "google-font:" + f, ln,
                           "Google Fonts: %s is not declared in DESIGN.md typography" % disp)
    yield from out


def _merge(out, keys, key, line, snippet):
    if key in keys:
        f = out[keys[key]]
        if not f.get("line"):
            f["line"] = line
        return
    keys[key] = len(out)
    out.append({"rule": "design-system-font", "line": line, "snippet": snippet})


def _size_status(raw, ds):
    t = raw.strip().lower()
    if not re.match(r"^-?[0-9.]+(?:px|rem)$", t):
        return "unjudgeable"
    px = resolve_length_px(t, 16)
    if px is None or not math.isfinite(px) or px <= 0:
        return "unjudgeable"
    return "on" if any(abs(p - px) <= 0.5 for p, _ in ds["sizes"]) else "off"


def design_system_font_size(ctx):
    """checkSourceDesignSystem font-size scan (source-only upstream: font-size:, fontSize:, text-[Npx|rem])."""
    if not ctx.design:
        return
    ds = design_system(ctx.design)
    if not ds["has_sizes"]:
        return
    seen = set()
    for ln, line in _source_lines(ctx.text):
        found = [("font-size", m.group(1)) for m in re.finditer(r"(?i)font-size\s*:\s*([^;}\n]+)", line)]
        found += [("fontSize", m.group(1)) for m in re.finditer(r"fontSize\s*[:=]\s*[\"'`]([^\"'`]+)[\"'`]", line)]
        found += [("text-[…] class", m.group(1))
                  for m in re.finditer(r"\btext-\[(-?[0-9.]+(?:px|rem))\]", line)]
        for cname, value in found:
            token = value.strip()
            t = re.sub(r"\s*!important\s*$", "", token.lower())
            args = _clamp_args(t)
            if args:
                off = [a for a in (args[0], args[2]) if _size_status(a, ds) == "off"]
                if not off:
                    continue
                snip = "%s: %s has fluid endpoint%s %s off the DESIGN.md type ramp" % (
                    cname, token, "s" if len(off) > 1 else "", " and ".join(off))
                val = off[0]
            else:
                if _size_status(t, ds) != "off":
                    continue
                snip = "%s: %s is off the DESIGN.md type ramp" % (cname, token)
                val = re.sub(r"(?i)\s*!important\s*$", "", token).strip()
            px = resolve_length_px(val.strip(), 16)
            key = "%s" % num(jsround(px * 100) / 100) if px is not None else val.lower()
            if key in seen:
                continue
            seen.add(key)
            yield {"rule": "design-system-font-size", "line": ln, "snippet": snip}


RULES = {
    "overused-font": overused_font,
    "flat-type-hierarchy": flat_type_hierarchy,
    "italic-serif-display": italic_serif_display,
    "hero-eyebrow-chip": hero_eyebrow_chip,
    "kicker-above-heading": kicker_above_heading,
    "numbered-section-labels": numbered_section_labels,
    "oversized-h1": oversized_h1,
    "skipped-heading": skipped_heading,
    "design-system-font": design_system_font,
    "design-system-font-size": design_system_font_size,
}
for _rid in ("tight-leading", "justified-text", "tiny-text", "undersized-ui-text", "all-caps-body", "wide-tracking",
             "extreme-negative-tracking"):
    RULES[_rid] = _quality_rule(_rid)
