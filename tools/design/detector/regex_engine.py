"""regex_engine.py — impeccable's line-regex engine for every non-HTML file (Apache-2.0 upstream, ported).

Port of crates/detect/src/detect_text.rs (detect_text, run_regex_matchers, comment stripping, <style> block and
CSS-in-JS extraction, the inset-stripe scan, FileSheet) and crates/detect/src/regex_matchers.rs (REGEX_MATCHERS,
the side-accent corner gate, REGEX_ANALYZERS), with the core pieces they call (css_scan.rs CssHostIndex, pseudo-stripe,
grid-background, glow and halo scans; rules.rs DeclaredCorners / tailwind_declared_corners).

scan(ctx) -> [(rule_id, snippet, line)]; ctx.text is the source and ctx.path carries the extension. Inline ignores
are applied by the caller (engine.scan_file -> ignores.apply). Spec: specs/D_motion_copy.md §11.
"""
import re
import urllib.parse

from . import color as C
from . import rules_motion_copy as MC

A = re.A
WS_CHARS = MC.WS_CHARS
WS = MC.WS
JS_WS = MC.JS_WS
jtrim = MC.jtrim
pf = MC.pf
num_str = MC.num_str

PAGE_ANALYZER_EXTS = {".html", ".htm", ".astro", ".vue", ".svelte"}
JS_SOURCE_EXTS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
CSS_LIKE_EXTS = {".css", ".scss", ".sass", ".less"}
CSS_IN_JS_EXTS = {".js", ".ts", ".jsx", ".tsx"}
COMPONENT_EXTS = {".astro", ".vue", ".svelte"}

RULE_IDS = {
    "side-tab", "border-accent-on-rounded", "overused-font", "gradient-text", "gray-on-color", "ai-color-palette",
    "bounce-easing", "broken-image", "codex-grid-background", "monotonous-spacing", "em-dash-overuse",
    "marketing-buzzword", "aphoristic-cadence", "dark-glow", "radial-halo", "marquee",
}

SIDE_ACCENT_MIN_RADIUS_PX = 4.0      # rules.rs
NOMINAL_CARD_WIDTH_PX = 1000.0       # rules.rs


def ext_of(path):
    """detect_text.rs#ext_from_file_path: the last `.\\w+`, lowercased."""
    m = re.search(r"\.[A-Za-z0-9_]+$", str(path))
    return m.group(0).lower() if m else ""


def line_of_offset(text, index):
    return text.count("\n", 0, max(0, min(index, len(text)))) + 1


def _blank(s):
    """Every char but a newline becomes a space (lengths kept, so offsets survive)."""
    return "".join("\n" if c == "\n" else " " for c in s)


# ════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# Comment stripping (detect_text.rs)
# ════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
_CSS_COMMENT = re.compile(r"/\*[\s\S]*?\*/")
_HTML_COMMENT = re.compile(r"<!--[\s\S]*?-->")
_STYLE_TAG_INNER = re.compile(r"<(?i:style)\b[^>]*>([\s\S]*?)</(?i:style)>", A)
_SCRIPT_TAG = re.compile(r"<(?i:script)\b[^>]*>[\s\S]*?</(?i:script)>", A)
_STYLE_BLOCK = re.compile(r"<(?i:style)[^>]*>([\s\S]*?)</(?i:style)>", A)


def strip_css_comments(text):
    """detect_text.rs#strip_css_comments: blank /* */ bodies, newlines kept."""
    return _CSS_COMMENT.sub(lambda m: _blank(m.group(0)), text)


def blank_css_line_comments(text):
    """detect_text.rs#blank_css_line_comments: blank // comments outside strings and url(...)."""
    out, state, url_depth, i, n = [], "code", 0, 0, len(text)
    while i < n:
        ch = text[i]
        nx = text[i + 1] if i + 1 < n else None
        if state == "line":
            out.append("\n" if ch == "\n" else " ")
            if ch == "\n":
                state = "code"
            i += 1
            continue
        if state in ("single", "double"):
            out.append(ch)
            if ch == "\\":
                if nx is not None:
                    out.append(nx)
                    i += 1
            elif (state == "single" and ch == "'") or (state == "double" and ch == '"'):
                state = "code"
            i += 1
            continue
        prev = out[-1] if out else None
        if ch == "/" and nx == "/" and url_depth == 0 and prev not in (":", "(", "\\"):
            out.append("  ")
            i += 2
            state = "line"
            continue
        if ch == "'":
            state = "single"
        elif ch == '"':
            state = "double"
        if ch == "(":
            behind = "".join(out).rstrip(JS_WS)
            if url_depth > 0 or behind.lower().endswith("url"):
                url_depth += 1
        elif ch == ")" and url_depth > 0:
            url_depth -= 1
        out.append(ch)
        i += 1
    return "".join(out)


def _blank_css_line_comments_in_style_blocks(text):
    def rep(m):
        whole, inner = m.group(0), m.group(1)
        open_len = len(whole) - len(inner) - len("</style>")
        return whole[:open_len] + blank_css_line_comments(inner) + whole[open_len + len(inner):]
    return _STYLE_TAG_INNER.sub(rep, text)


def _blank_html_and_css_comments_outside_scripts(text):
    out, last = [], 0
    for m in _SCRIPT_TAG.finditer(text):
        seg = text[last:m.start()]
        out.append(_blank_css_line_comments_in_style_blocks(strip_css_comments(_HTML_COMMENT.sub(lambda c: _blank(c.group(0)), seg))))
        out.append(m.group(0))
        last = m.end()
    seg = text[last:]
    out.append(_blank_css_line_comments_in_style_blocks(strip_css_comments(_HTML_COMMENT.sub(lambda c: _blank(c.group(0)), seg))))
    return "".join(out)


_REGEX_PREFIX_KEYWORDS = {"await", "case", "default", "delete", "do", "else", "in", "instanceof", "new", "of",
                          "return", "throw", "typeof", "void", "yield"}


def strip_js_comments(text, jsx=False):
    """detect_text.rs#strip_js_comments, simplified: blanks // and /* */ outside strings, template literals (with
    ${} nesting) and regex literals; in JSX text `://` (a URL) is not a comment."""
    out = list(text)
    n, i = len(text), 0
    tmpl_stack = []          # brace depth at which each open template's ${ } expression closes
    brace = 0
    last_sig = ""            # last significant char outside comments/strings
    last_word = ""

    def regex_can_start():
        if not last_sig:
            return True
        if last_sig in "(,=:[!&|?{};+-*%<>~^":
            return True
        return last_word in _REGEX_PREFIX_KEYWORDS

    in_template = False
    while i < n:
        ch = text[i]
        nx = text[i + 1] if i + 1 < n else ""
        if in_template:
            if ch == "\\":
                i += 2
                continue
            if ch == "`":
                in_template = False
                last_sig, last_word = "`", ""
                i += 1
                continue
            if ch == "$" and nx == "{":
                brace += 1
                tmpl_stack.append(brace)
                in_template = False
                last_sig, last_word = "{", ""
                i += 2
                continue
            i += 1
            continue
        if ch in "\"'":
            j = i + 1
            while j < n and text[j] != ch and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            i = j + 1
            last_sig, last_word = ch, ""
            continue
        if ch == "`":
            in_template = True
            i += 1
            continue
        if ch == "/" and nx == "/":
            if jsx and i > 0 and text[i - 1] == ":":
                i += 2
                continue
            j = text.find("\n", i)
            j = n if j < 0 else j
            for k in range(i, j):
                out[k] = " "
            i = j
            continue
        if ch == "/" and nx == "*":
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            for k in range(i, j):
                if out[k] != "\n":
                    out[k] = " "
            i = j
            continue
        if ch == "/" and regex_can_start():
            j, in_class = i + 1, False
            while j < n and text[j] != "\n":
                c = text[j]
                if c == "\\":
                    j += 2
                    continue
                if c == "[":
                    in_class = True
                elif c == "]":
                    in_class = False
                elif c == "/" and not in_class:
                    break
                j += 1
            if j < n and text[j] == "/":
                i = j + 1
                last_sig, last_word = "/", ""
                continue
        if ch == "{":
            brace += 1
        elif ch == "}":
            if tmpl_stack and tmpl_stack[-1] == brace:
                tmpl_stack.pop()
                brace -= 1
                in_template = True
                i += 1
                continue
            brace -= 1
        if ch not in JS_WS:
            if ch.isalnum() or ch in "_$":
                j = i
                while j < n and (text[j].isalnum() or text[j] in "_$"):
                    j += 1
                last_word = text[i:j]
                last_sig = text[j - 1]
                i = j
                continue
            last_sig, last_word = ch, ""
        i += 1
    return "".join(out)


def _astro_frontmatter_strip(text):
    """detect_text.rs#blank_astro_frontmatter_comments (fence found by line, comments stripped as JS)."""
    if not text.startswith("---"):
        return text
    m = re.search(r"\n---[ \t]*(?:\r?\n|$)", text[3:])
    if not m:
        return text
    close = 3 + m.start()
    return strip_js_comments(text[:close]) + text[close:]


def blank_comments_for_matchers(text, ext):
    """detect_text.rs#blank_comments_for_matchers."""
    if ext in PAGE_ANALYZER_EXTS:
        if ext == ".astro":
            text = _astro_frontmatter_strip(text)
        return _blank_html_and_css_comments_outside_scripts(text)
    if ext in CSS_LIKE_EXTS:
        t = strip_css_comments(text)
        return t if ext == ".css" else blank_css_line_comments(t)
    return text


# ════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# Style blocks and CSS-in-JS (detect_text.rs)
# ════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
def extract_style_blocks(content, ext):
    """-> [(block_text, start_line)] for .astro/.vue/.svelte (start_line = line of `<style` + 1)."""
    if ext not in COMPONENT_EXTS:
        return []
    return [(m.group(1), line_of_offset(content, m.start()) + 1) for m in _STYLE_BLOCK.finditer(content)]


def _find_expr_end(text, start):
    """Index of the `}` closing a `${` whose `{` is at start (strings and templates kept whole)."""
    depth, i, n = 0, start, len(text)
    while i < n:
        c = text[i]
        if c in "\"'":
            j = i + 1
            while j < n and text[j] != c:
                j += 2 if text[j] == "\\" else 1
            i = j + 1
            continue
        if c == "`":
            e = find_template_literal_end(text, i)
            if e is None:
                return None
            i = e + 1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def find_template_literal_end(text, start):
    """detect_text.rs#find_template_literal_end: index of the closing backtick of the template opening at start."""
    i, n = start + 1, len(text)
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == "`":
            return i
        if c == "$" and i + 1 < n and text[i + 1] == "{":
            e = _find_expr_end(text, i + 1)
            if e is None:
                return None
            i = e + 1
            continue
        i += 1
    return None


_CSS_TAG = re.compile(r"\b(?:styled(?:\.[A-Za-z0-9_]+|\([^)]+\))|css)", A)


def find_css_in_js_templates(content):
    """detect_text.rs#find_css_in_js_templates -> [(tag_start, content_start, content_end)]."""
    out, pos, n = [], 0, len(content)
    while pos <= n:
        m = _CSS_TAG.search(content, pos)
        if not m:
            break
        cur = m.end()
        while cur < n and content[cur] in JS_WS:
            cur += 1
        skip = False
        if cur < n and content[cur] == "<":
            depth = 0
            while cur < n:
                ch = content[cur]
                if ch == "<":
                    depth += 1
                elif ch == ">" and content[cur - 1] != "=":
                    depth -= 1
                cur += 1
                if depth == 0:
                    break
            if depth != 0:
                skip = True
            else:
                while cur < n and content[cur] in JS_WS:
                    cur += 1
        if skip or cur >= n or content[cur] != "`":
            pos = m.end()
            continue
        end = find_template_literal_end(content, cur)
        if end is None:
            pos = m.end()
            continue
        out.append((m.start(), cur + 1, end))
        pos = end + 1
    return out


def extract_css_in_js(source, ext):
    """-> [(block_text, start_line)] (start_line = line of the tag)."""
    if ext not in CSS_IN_JS_EXTS:
        return []
    return [(source[cs:ce], source.count("\n", 0, ts) + 1) for ts, cs, ce in find_css_in_js_templates(source)]


_GLOBAL_STYLE_TEMPLATE = re.compile(r"\b(?:createGlobalStyle|injectGlobal)\s*`|<style\b[^>]*>\s*\{\s*`")


def global_style_templates(source, ext):
    if ext not in CSS_IN_JS_EXTS or not _GLOBAL_STYLE_TEMPLATE.search(source):
        return []
    out = []
    for m in _GLOBAL_STYLE_TEMPLATE.finditer(source):
        tick = m.end() - 1
        end = find_template_literal_end(source, tick)
        if end is not None:
            out.append(strip_css_comments(source[tick + 1:end]))
    return out


def strip_css_in_js_comments(content, ext):
    if ext not in CSS_IN_JS_EXTS:
        return content
    out, cur = [], 0
    for _, cs, ce in find_css_in_js_templates(content):
        out.append(content[cur:cs])
        out.append(strip_css_comments(content[cs:ce]))
        cur = ce
    out.append(content[cur:])
    return "".join(out)


# ════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# Corners (rules.rs DeclaredCorners, measures parse_radius_*)
# ════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
_IMPORTANT_TAIL_ANY = re.compile(r"(?i)" + WS + r"*!" + WS + r"*important" + WS + r"*$")
_BARE_NUMBER = re.compile(r"^-?(?:[0-9]+\.?[0-9]*|\.[0-9]+)$")


def _radius_token_px(token, width=NOMINAL_CARD_WIDTH_PX, em=16.0):
    token = jtrim(token)
    first = re.split(WS + "+", token)[0] if token else ""
    numv = pf(first)
    if numv != numv:
        return None
    if first.endswith("%"):
        numv = numv / 100.0 * width if width > 0 else numv
    unit = re.sub(r"^[^A-Za-z%]*", "", token).lower()
    if unit in ("px", "%"):
        return numv
    if unit == "em":
        return numv * em
    if unit == "rem":
        return numv * 16.0
    if unit == "" and numv == 0:
        return 0.0
    return None


def _radius_half(half):
    t = jtrim(half)
    if not t:
        return None
    parts = []
    for tok in re.split(WS + "+", t):
        if not tok:
            continue
        v = _radius_token_px(tok)
        if v is None:
            return None
        parts.append(v)
    if not parts:
        return None
    p = parts + [0.0] * 4
    return {1: [p[0]] * 4, 2: [p[0], p[1], p[0], p[1]], 3: [p[0], p[1], p[2], p[1]]}.get(len(parts), p[:4])


def parse_radius_corners(value):
    """css_measures.rs#parse_radius_corners -> [tl, tr, br, bl] or None."""
    if value is None:
        return None
    halves = value.split("/")
    h = _radius_half(halves[0])
    if h is None:
        return None
    if len(halves) > 1:
        v = _radius_half(halves[1])
        if v is None:
            return None
        h = [0.0 if v[i] <= 0 else h[i] for i in range(4)]
    return h


def parse_radius_corner_px(value):
    if value is None:
        return None
    toks = [t for t in re.split(WS + "+", jtrim(value)) if t]
    if not toks:
        return None
    hz = _radius_token_px(toks[0])
    if hz is None:
        return None
    if len(toks) > 1:
        v = _radius_token_px(toks[1])
        if v is None:
            return None
        if v <= 0:
            return 0.0
    return hz


_CORNER_KEYS = {"borderradius": None, "bordertopleftradius": 0, "borderstartstartradius": 0,
                "bordertoprightradius": 1, "borderstartendradius": 1, "borderbottomrightradius": 2,
                "borderendendradius": 2, "borderbottomleftradius": 3, "borderendstartradius": 3}


class Corners:
    """rules.rs#DeclaredCorners: [tl, tr, br, bl], None = unknown; default every corner 0, undeclared."""
    __slots__ = ("c", "declared")

    def __init__(self, c=None, declared=False):
        self.c = list(c) if c is not None else [0.0] * 4
        self.declared = declared

    @classmethod
    def unknown(cls):
        return cls([None] * 4, True)

    def copy(self):
        return Corners(self.c, self.declared)

    def set_all(self, corners):
        self.declared = True
        self.c = list(corners) if corners is not None else [None] * 4

    def set_unknown(self):
        self.set_all(None)

    def set_corner(self, i, px):
        self.declared = True
        self.c[i] = px

    def raise_corner(self, i, px):
        self.declared = True
        a = self.c[i]
        self.c[i] = max(a, px) if a is not None and px is not None else None

    def raise_to(self, other):
        if not other.declared:
            return
        for i in range(4):
            self.raise_corner(i, other.c[i])

    def known(self):
        return all(x is not None for x in self.c)

    def apply(self, prop, value):
        """DeclaredCorners::apply -> whether prop was a radius."""
        camel = "-" not in prop and any(ch.isupper() for ch in prop)
        key = prop.replace("-", "").lower()
        if key not in _CORNER_KEYS:
            return False
        v = jtrim(jtrim(value).strip("\"'`"))
        v = jtrim(_IMPORTANT_TAIL_ANY.sub("", v))
        if camel and _BARE_NUMBER.match(v):
            v += "px"
        corner = _CORNER_KEYS[key]
        if corner is None:
            self.set_all(parse_radius_corners(v))
        else:
            self.set_corner(corner, parse_radius_corner_px(v))
        return True

    def rounded_away(self, side):
        """is_rounded_away_from_side: side 0 top, 1 right, 2 bottom, 3 left."""
        if not self.declared:
            return False
        a, b = {0: (3, 2), 1: (0, 3), 2: (0, 1)}.get(side, (1, 2))
        a, b = self.c[a], self.c[b]
        if a is None or b is None:
            return True
        return a >= SIDE_ACCENT_MIN_RADIUS_PX and b >= SIDE_ACCENT_MIN_RADIUS_PX


_TW_ROUNDED_CLASS = re.compile(r"^rounded(?:-(tl|tr|br|bl|ss|se|ee|es|t|r|b|l|s|e))?(?:-([a-z0-9-]+|\[[^\]]*\]|\([^)]*\)))?$")
_TW_CLASS_SPLIT = re.compile(r"[\s\"'`{}]+")
_TW_SIZES = {None: 4.0, "sm": 4.0, "none": 0.0, "xs": 2.0, "md": 6.0, "lg": 8.0, "xl": 12.0, "2xl": 16.0,
             "3xl": 24.0, "4xl": 32.0, "full": 9999.0}


def tailwind_declared_corners(scope):
    """rules.rs#tailwind_declared_corners."""
    base, variants = [], []
    for raw in _TW_CLASS_SPLIT.split(scope):
        token = raw.strip("!")
        bracket = token.find("[")
        bracket = len(token) if bracket < 0 else bracket
        ci_ = token[:bracket].rfind(":")
        variant, cls = (True, token[ci_ + 1:].lstrip("!")) if ci_ >= 0 else (False, token)
        m = _TW_ROUNDED_CLASS.match(cls)
        if not m:
            continue
        side = m.group(1)
        group, corners = {None: (0, (0, 1, 2, 3)), "t": (1, (0, 1)), "r": (1, (1, 2)), "e": (1, (1, 2)),
                          "b": (1, (2, 3)), "l": (1, (0, 3)), "s": (1, (0, 3)), "tl": (2, (0,)), "ss": (2, (0,)),
                          "tr": (2, (1,)), "se": (2, (1,)), "br": (2, (2,)), "ee": (2, (2,))}.get(side, (2, (3,)))
        size = m.group(2)
        if size in _TW_SIZES:
            px = _TW_SIZES[size]
        elif size and size.startswith("["):
            px = parse_radius_corner_px(size[1:-1].replace("_", " "))
        else:
            px = None
        (variants if variant else base).append((group, corners, px))
    base.sort(key=lambda e: e[0])
    d = Corners()
    for _, corners, px in base:
        for i in corners:
            d.set_corner(i, px)
    for _, corners, px in variants:
        for i in corners:
            d.raise_corner(i, px)
    return d


# ════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# Statement / selector helpers (css_scan.rs, regex_matchers.rs)
# ════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
def has_interpolation(text):
    return "${" in text or "#{" in text or "@{" in text


_LESS_MIXIN_CALL = re.compile(r"^[.#][-_A-Za-z0-9]+(?:\s*>?\s*[.#][-_A-Za-z0-9]+)*\s*(?:\(.*\))?\s*(?:!important)?$")
_HEX_COLOR_START = re.compile(r"^#[0-9a-fA-F]{3,8}\b", A)


def is_unseen_declaration_source(statement):
    """css_scan.rs#is_unseen_declaration_source."""
    s = jtrim(statement)
    if not s:
        return False
    low = s.lower()
    if low.startswith(("@include", "@extend", "@apply", "composes")) or s.startswith("...") \
            or (s.startswith("+") and s[1:2].isalpha() and s[1:2].isascii()):
        return True
    if has_interpolation(s.split(":")[0]):
        return True
    return s[0] in ".#" and (":" not in s or "(" in s) and not _HEX_COLOR_START.match(s) and bool(_LESS_MIXIN_CALL.match(s))


def last_compound(selector):
    depth, p = 0, len(selector)
    while p > 0:
        c = selector[p - 1]
        if c in ")]":
            depth += 1
        elif c in "([":
            depth -= 1
        elif c in " \t\n\r>+~" and depth <= 0:
            break
        p -= 1
    return selector[p:]


def names_same_element(selector):
    """css_scan.rs#names_same_element."""
    s = jtrim(selector).strip("\"'`")
    parts = [jtrim(p) for p in MC.split_commas_outside_parens(s) if jtrim(p)]
    if not parts:
        return False
    for part in parts:
        lc = last_compound(part)
        if not lc.startswith("&"):
            return False
        rest = lc[1:]
        if not (rest == "" or rest[0] in ".#[:" or rest.startswith("--")):
            return False
    return True


_SIMPLE_SELECTOR = re.compile(r"::?[-A-Za-z]+(?:\([^)]*\))?|\[[^\]]*\]|[.#](?:\\.|[-_A-Za-z0-9])+|\*|[A-Za-z][-A-Za-z0-9]*")
_PSEUDO_ELEMENT_STRIP = re.compile(r"::?(?i:before|after)\b", A)
_ANY_PSEUDO_STRIP = re.compile(r"::?[a-zA-Z-]+(?:\([^)]*\))?")
_WS_RUN = re.compile(WS + "+")


def normalize_selector(s):
    return _WS_RUN.sub(" ", jtrim(s))


def compound_tokens(compound):
    return _SIMPLE_SELECTOR.findall(compound)


def resolve_nested_selectors(selector, parent):
    out = []
    for part in MC.split_commas_outside_parens(selector):
        part = normalize_selector(part)
        if not part:
            continue
        if not parent:
            out.append(part)
        else:
            for q in parent[:max(0, 64 - len(out))]:
                out.append(normalize_selector(part.replace("&", q)) if "&" in part else "%s %s" % (q, part))
        if len(out) >= 64:
            break
    return out


def split_statements(text, obj):
    """regex_matchers.rs#split_statements: statements at the block's own depth (nested blocks dropped)."""
    out, seg, depth, p, n = [], 0, 0, 0, len(text)

    def push(a, b):
        s = jtrim(text[a:b])
        if s:
            out.append(s)
    while p < n:
        c = text[p]
        if c in "\"'`":
            e = p + 1
            while e < n and text[e] != c:
                if text[e] == "\\":
                    e += 1
                e += 1
            p = min(e, n)
        elif c in "([":
            depth += 1
        elif c in ")]":
            depth -= 1
        elif c == "{":
            close = _matching_close(text, p)
            close = n - 1 if close is None else close
            if not (p > 0 and text[p - 1] in "$#@") and depth <= 0:
                seg = close + 1
            p = close
        elif (c == ";" or c == "\n") and depth <= 0:
            push(seg, p)
            seg = p + 1
        elif c == "," and obj and depth <= 0:
            push(seg, p)
            seg = p + 1
        p += 1
    if seg < n:
        push(seg, n)
    return out


def split_declaration(statement):
    s = jtrim(statement)
    if not s:
        return None
    if s[0] in "\"'`":
        close = s.find(s[0], 1)
        if close < 0:
            return None
        rest = jtrim(s[close + 1:])
        if not rest.startswith(":"):
            return None
        return s[1:close], jtrim(rest[1:])
    i = s.find(":")
    if i < 0:
        return None
    return jtrim(s[:i]), jtrim(s[i + 1:])


def apply_statements(corners, statements, theme_scale):
    for st in statements:
        if is_unseen_declaration_source(st):
            corners.set_unknown()
            continue
        d = split_declaration(st)
        if not d:
            continue
        prop, value = d
        if theme_scale and _BARE_NUMBER.match(value):
            key = prop.lower()
            if key.startswith("border") and key.endswith("radius"):
                if pf(value) == 0:
                    corners.apply(prop, "0")
                else:
                    corners.set_unknown()
                continue
        corners.apply(prop, value)


def _matching_close(text, open_):
    depth, quote, p, n = 0, None, open_, len(text)
    while p < n:
        c = text[p]
        if quote:
            if c == "\\":
                p += 2
                continue
            if c == quote:
                quote = None
            p += 1
            continue
        if c in "\"'`":
            quote = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth = max(0, depth - 1)
            if depth == 0:
                return p
        p += 1
    return None


def _matching_open(text, close):
    depth, p = 0, close + 1
    while p > 0:
        p -= 1
        if text[p] == "}":
            depth += 1
        elif text[p] == "{":
            depth -= 1
            if depth == 0:
                return p
    return None


def _balanced_braces(text, open_):
    c = _matching_close(text, open_)
    return None if c is None else text[open_ + 1:c]


def _block_bounds(text, offset):
    start, open_, depth = 0, None, 0
    p = min(offset, len(text))
    while p > 0:
        p -= 1
        c = text[p]
        if c == "}":
            depth += 1
        elif c == "{":
            if depth == 0:
                start, open_ = p + 1, p
                break
            depth -= 1
        elif c == "`" and depth == 0:
            start = p + 1
            break
    end, depth, p = len(text), 0, min(offset, len(text))
    while p < len(text):
        c = text[p]
        if c == "{":
            depth += 1
        elif c == "}":
            if depth == 0:
                end = p
                break
            depth -= 1
        elif c == "`" and depth == 0:
            end = p
            break
        p += 1
    return start, end, open_


def _opens_interpolation(text, open_):
    return open_ > 0 and text[open_ - 1] in "$#@"


def _is_object_open(text, open_):
    before = text[:open_].rstrip()
    return before.endswith(("{", "(", "=", ":", ",", "[", "?", "=>", "return"))


def _is_sx_object(text, open_):
    before = text[:open_].rstrip()
    if not before.endswith("{"):
        return False
    before = before[:-1].rstrip()
    if not before.endswith("="):
        return False
    return before[:-1].rstrip().endswith("sx")


def _object_key(text, open_):
    trimmed = text[:open_].rstrip()
    if not trimmed.endswith(":"):
        return "", open_
    before = trimmed[:-1].rstrip()
    if before.endswith("]"):
        return "${computed}", len(before)
    if before and before[-1] in "\"'`":
        q = before[-1]
        st = before[:-1].rfind(q)
        if st >= 0:
            return before[st + 1:-1], st
    k = len(before)
    while k > 0 and (before[k - 1].isascii() and (before[k - 1].isalnum() or before[k - 1] in "_$&-")):
        k -= 1
    return before[k:], k


def _selector_begin(text, open_):
    p = open_
    while p > 0:
        p -= 1
        c = text[p]
        if c == "}":
            o = _matching_open(text, p)
            if o is not None and _opens_interpolation(text, o):
                p = o
                continue
            return p + 1
        if c in ";{`":
            return p + 1
    return 0


def _inside_interpolation(text, tick):
    depth, p = 0, tick
    while p > 0:
        p -= 1
        c = text[p]
        if c == "}":
            depth += 1
        elif c == "{":
            if depth == 0:
                return p > 0 and text[p - 1] == "$"
            depth -= 1
        elif c == "`" and depth == 0:
            return False
    return False


class SourceText:
    """regex_matchers.rs#SourceText: the pass's lines joined, with line start offsets."""

    def __init__(self, lines):
        self.lines = lines
        self.text = "\n".join(lines)
        self.starts, pos = [], 0
        for ln in lines:
            self.starts.append(pos)
            pos += len(ln) + 1

    def offset(self, i, index):
        return self.starts[i] + index


def brace_scope_corners(src, i, index, base):
    """regex_matchers.rs#brace_scope_corners."""
    text = src.text
    start, end, open_ = _block_bounds(text, src.starts[i] + index)
    chunks, unknown, theme = [], False, False
    while True:
        obj = open_ is not None and _is_object_open(text, open_)
        chunks.append((start, end, obj))
        if open_ is None:
            if start > 0 and text[start - 1] == "`" and _inside_interpolation(text, start - 1):
                unknown = True
            break
        if _opens_interpolation(text, open_):
            unknown = True
            break
        if obj:
            theme = theme or _is_sx_object(text, open_)
            selector, sel_start = _object_key(text, open_)
        else:
            b = _selector_begin(text, open_)
            selector, sel_start = jtrim(text[b:open_]), b
        if has_interpolation(selector):
            unknown = True
            break
        if not (selector.startswith("@") or names_same_element(selector)):
            break
        start, end, open_ = _block_bounds(text, sel_start)
    corners = Corners.unknown() if unknown else base.copy()
    for s, e, obj in reversed(chunks):
        apply_statements(corners, split_statements(text[s:e], obj), obj and theme)
    return corners


def _indent(line):
    return len(line) - len(line.lstrip())


def sass_scope_corners(src, i, base):
    """regex_matchers.rs#sass_scope_corners."""
    lines = src.lines
    chunks, unknown, at = [], False, i
    while True:
        level = _indent(lines[at])
        first, parent = at, None
        for j in range(at - 1, -1, -1):
            if not lines[j].strip():
                continue
            if _indent(lines[j]) < level:
                parent = j
                break
            first = j
        last = at
        for j in range(at + 1, len(lines)):
            if not lines[j].strip():
                continue
            if _indent(lines[j]) < level:
                break
            last = j
        stmts = []
        for j in range(first, last + 1):
            ln = lines[j]
            if not ln.strip() or _indent(ln) != level:
                continue
            nxt = next((lines[k] for k in range(j + 1, last + 1) if lines[k].strip()), None)
            if not (nxt is not None and _indent(nxt) > level):
                stmts.append(jtrim(ln))
        chunks.append(stmts)
        if parent is None:
            break
        sel = jtrim(lines[parent])
        if has_interpolation(sel):
            unknown = True
            break
        if not (sel.startswith("@") or sel.startswith("+") or names_same_element(sel)):
            break
        at = parent
    corners = Corners.unknown() if unknown else base.copy()
    for stmts in reversed(chunks):
        apply_statements(corners, stmts, False)
    return corners


def sass_sheet_corners(text):
    lines = text.split("\n")
    sheet = Corners()
    for j, line in enumerate(lines):
        st = jtrim(line)
        if not st:
            continue
        nxt = next((l for l in lines[j + 1:] if l.strip()), None)
        if nxt is not None and _indent(nxt) > _indent(line):
            continue
        if is_unseen_declaration_source(st):
            sheet.set_unknown()
            continue
        low = st.lower()
        if has_interpolation(st) and ("radius" in low or "rounded" in low):
            sheet.set_unknown()
            continue
        d = split_declaration(st)
        if d:
            one = Corners()
            if one.apply(*d):
                sheet.raise_to(one)
    return sheet


# ════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# CssHostIndex (css_scan.rs) — a stylesheet's rule blocks with the selectors of the element each one styles
# ════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
class CssHostIndex:
    def __init__(self, css):
        content = strip_css_comments(css)
        self.content = content
        props = MC.custom_props(content)
        self.opens, self.closes, self.hosts, self.hosts_unknown = [], [], [], []
        self.rules = []                 # [(order, [("set", prop, value) | ("unseen",)])]
        self.interpolations = []
        self.exact, self.by_first = {}, {}
        stack = [dict(keys=["&"], parent=None, hosts=["&"], hunk=False, in_rule=False, order=0, direct=[],
                      chunk=0, seg=0, block=-1)]
        n, p = len(content), 0
        while p < n:
            c = content[p]
            if c in "\"'":
                e = p + 1
                while e < n and content[e] != c and content[e] != "\n":
                    if content[e] == "\\":
                        e += 1
                    e += 1
                p = e
            elif c in "#$@" and p + 1 < n and content[p + 1] == "{":
                depth, e = 0, p + 1
                while e < n:
                    if content[e] == "{":
                        depth += 1
                    elif content[e] == "}":
                        depth -= 1
                        if depth == 0:
                            break
                    e += 1
                self.interpolations.append((p, e))
                p = e
            elif c == ";":
                stack[-1]["seg"] = p + 1
            elif c == "{":
                top = stack[-1]
                selector = jtrim(content[top["seg"]:p])
                top["direct"].append(content[top["chunk"]:top["seg"]])
                block = len(self.opens)
                if selector.startswith("@"):
                    frame = dict(keys=list(top["keys"]), parent=top["parent"], hosts=list(top["hosts"]),
                                 hunk=top["hunk"], in_rule=top["in_rule"])
                else:
                    resolved = resolve_nested_selectors(selector, top["parent"])
                    hosts = list(resolved)
                    same = names_same_element(selector)
                    if same:
                        hosts.extend(top["hosts"])
                    frame = dict(keys=resolved, parent=resolved, hosts=hosts,
                                 hunk=has_interpolation(selector) or (same and top["hunk"]), in_rule=True)
                frame.update(order=p, direct=[], chunk=p + 1, seg=p + 1, block=block)
                self.opens.append(p)
                self.closes.append(n)
                self.hosts.append(frame["hosts"])
                self.hosts_unknown.append(frame["hunk"])
                stack.append(frame)
            elif c == "}":
                if len(stack) > 1:
                    fr = stack.pop()
                    self.closes[fr["block"]] = p
                    fr["direct"].append(content[fr["chunk"]:p])
                    self._add_rule(fr, props)
                else:
                    stack[0]["direct"].append(content[stack[0]["chunk"]:p])
                stack[-1]["chunk"] = stack[-1]["seg"] = p + 1
            p += 1
        while stack:
            fr = stack.pop()
            fr["direct"].append(content[min(fr["chunk"], n):])
            self._add_rule(fr, props)

    def _add_rule(self, fr, props):
        if not fr["keys"]:
            return
        decls = []
        for part in "".join(fr["direct"]).split(";"):
            if is_unseen_declaration_source(part):
                decls.append(("unseen",))
                continue
            i = part.find(":")
            if i <= 0:
                continue
            prop = jtrim(part[:i])
            if not prop.lower().endswith("radius"):
                continue
            decls.append(("set", prop, MC.resolve_var_refs(part[i + 1:], props)))
        if not decls:
            return
        rid = len(self.rules)
        for key in fr["keys"]:
            self.exact.setdefault(key, []).append(rid)
            if last_compound(key) == key:
                toks = compound_tokens(key)
                if toks:
                    self.by_first.setdefault(toks[0], []).append((rid, toks))
        self.rules.append((fr["order"], decls))

    def _apply(self, rid, corners):
        for d in self.rules[rid][1]:
            if d[0] == "set":
                corners.apply(d[1], d[2])
            else:
                corners.set_unknown()

    def tied_rules(self, hosts):
        ids = []
        for host in hosts:
            ids.extend(self.exact.get(host, []))
            toks = compound_tokens(last_compound(host))
            for t in toks:
                for rid, comp in self.by_first.get(t, []):
                    if all(x in toks for x in comp):
                        ids.append(rid)
        return sorted(set(ids), key=lambda r: (self.rules[r][0], r))

    def sheet_corners(self):
        sheet = Corners()
        for _, decls in self.rules:
            for d in decls:
                if d[0] == "set":
                    one = Corners()
                    one.apply(d[1], d[2])
                    sheet.raise_to(one)
                else:
                    sheet.set_unknown()
        for a, b in self.interpolations:
            t = self.content[a:b + 1]
            low = t.lower()
            if "`" in t or "radius" in low or "rounded" in low:
                sheet.set_unknown()
        return sheet

    def _host_forms(self, selectors):
        out = []
        for s in selectors:
            for h in (normalize_selector(jtrim(_PSEUDO_ELEMENT_STRIP.sub("", s))),
                      normalize_selector(_ANY_PSEUDO_STRIP.sub("", s))):
                if h and h not in out:
                    out.append(h)
        return out

    def _hosts_known_square(self, hosts, side, sheet):
        if hosts is None:
            return False
        ids = self.tied_rules(hosts)
        tied, declared = Corners(), Corners.unknown()
        for rid in ids:
            self._apply(rid, tied)
            self._apply(rid, declared)
        if tied.rounded_away(side):
            return False
        return not declared.rounded_away(side) or not sheet.rounded_away(side)

    def _in_interp(self, pos):
        return any(a <= pos <= b for a, b in self.interpolations)

    def is_declaration_known_square(self, pos, side, sheet):
        if self._in_interp(pos):
            return False
        before = sum(1 for o in self.opens if o < pos)
        block = next((b for b in range(before - 1, -1, -1) if self.closes[b] >= pos), None)
        if block is None:
            hosts = ["&"]
        elif self.hosts_unknown[block]:
            hosts = None
        else:
            hosts = self._host_forms(self.hosts[block])
        return self._hosts_known_square(hosts, side, sheet)

    def is_rule_known_square(self, pos, selector, side, sheet):
        if has_interpolation(selector) or self._in_interp(pos):
            return False
        block = sum(1 for o in self.opens if o < pos)
        if block < len(self.hosts_unknown) and self.hosts_unknown[block]:
            return False
        sels = self.hosts[block] if block < len(self.hosts) and self.hosts[block] else [selector]
        return self._hosts_known_square(self._host_forms(sels), side, sheet)

    def is_element_known_square(self, tag, styled_root, classes, side, sheet):
        if not sheet.declared:
            return True
        applicable = sorted({rid for sel, ids in self.exact.items()
                             if _selector_could_apply(sel, tag, styled_root, classes) for rid in ids})
        for rid in applicable:
            c = Corners()
            self._apply(rid, c)
            if c.rounded_away(side):
                return False
        host = (tag or "") + "".join("." + c for c in classes if _plain_class(c))
        tied_square = False
        if host:
            d = Corners.unknown()
            for rid in self.tied_rules([host]):
                self._apply(rid, d)
            tied_square = not d.rounded_away(side)
        return tied_square or sheet.known()


def _plain_class(c):
    return bool(c) and not c[0].isdigit() and all(ch.isascii() and (ch.isalnum() or ch in "-_") for ch in c)


def _selector_could_apply(selector, tag, styled_root, classes):
    if has_interpolation(selector):
        return True
    subject = last_compound(selector)
    if "&" in subject:
        return styled_root
    for tok in compound_tokens(subject):
        low = tok.lower()
        if low.startswith("::") or low in (":before", ":after", ":first-line", ":first-letter"):
            return False
        if tok.startswith("."):
            if tok[1:].replace("\\", "") not in classes:
                return False
        elif tok[:1].isalpha() and tok[:1].isascii():
            if tag is not None and tag.lower() != tok.lower():
                return False
    return True


# ════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# FileSheet (detect_text.rs)
# ════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
_STYLESHEET_IMPORT = re.compile(
    r"""(?i)\bimport\s*(?:[\w$*{}\s,]+?\s*from\s*)?\(?\s*['"][^'"\n]+\.(?:css|scss|sass|less|styl|stylus|pcss|postcss)(?:\?[^'"\n]*)?['"]"""
    r"""|\brequire\s*\(\s*['"][^'"\n]+\.(?:css|scss|sass|less|styl|stylus|pcss|postcss)(?:\?[^'"\n]*)?['"]\s*\)"""
    r"""|@import\b|<style\b[^>]*\bsrc\s*=|<link\b[^>]*\brel\s*=\s*['"]?stylesheet""")
_SASS_USE = re.compile(r"""@use\s+['"]([^'"\n]*)['"]""")


class FileSheet:
    def __init__(self, content, source, ext):
        self.content, self.source, self.ext = content, source, ext
        self._corners = self._style_text = self._sources = self._imports = None
        self._style_text_done = False

    def imports_stylesheet(self):
        if self._imports is None:
            self._imports = bool(_STYLESHEET_IMPORT.search(self.source)) or any(
                not u.startswith("sass:") for u in _SASS_USE.findall(self.source))
        return self._imports

    def style_sources(self):
        if self._sources is None:
            parts = [blank_css_line_comments(strip_css_comments(b)) + "\n" for b, _ in extract_style_blocks(self.content, self.ext)]
            parts += [strip_css_comments(b) + "\n" for b, _ in extract_css_in_js(self.source, self.ext)]
            parts += [g + "\n" for g in global_style_templates(self.source, self.ext)]
            self._sources = "".join(parts)
        return self._sources

    def style_text(self):
        """Component files: the source with everything outside <style> blocks blanked, and the block spans."""
        if not self._style_text_done:
            self._style_text_done = True
            if self.ext in COMPONENT_EXTS:
                spans = [(m.start(1), m.end(1)) for m in _STYLE_BLOCK.finditer(self.source)]
                if spans:
                    out, at = [], 0
                    for s, e in spans:
                        out.append(_blank(self.source[at:s]))
                        out.append(self.source[s:e])
                        at = e
                    out.append(_blank(self.source[at:]))
                    self._style_text = ("".join(out), spans)
        return self._style_text

    def corners(self):
        if self._corners is None:
            if self.ext == ".sass":
                self._corners = sass_sheet_corners(self.source)
            elif self.ext in CSS_LIKE_EXTS:
                self._corners = CssHostIndex(self.source).sheet_corners()
            else:
                sheet = Corners()
                for b, _ in extract_style_blocks(self.content, self.ext):
                    sheet.raise_to(CssHostIndex(blank_css_line_comments(strip_css_comments(b))).sheet_corners())
                for b, _ in extract_css_in_js(self.source, self.ext):
                    sheet.raise_to(CssHostIndex(strip_css_comments(b)).sheet_corners())
                for t in global_style_templates(self.source, self.ext):
                    sheet.raise_to(CssHostIndex(t).sheet_corners())
                self._corners = sheet
        return self._corners


# ════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# Markup helpers (regex_matchers.rs)
# ════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
def scan_js(text, start):
    """regex_matchers.rs#scan_js: yield (ch, i, prev, next, paren, brace) for chars outside strings/templates and
    other than ( ) { }."""
    k, n = start, len(text)
    quote, in_tmpl, paren, brace, interp = None, False, 0, 0, []
    while k < n:
        ch = text[k]
        prev = text[k - 1] if k > 0 else None
        nx = text[k + 1] if k + 1 < n else None
        if quote:
            if ch == "\\":
                k += 2
                continue
            if ch == quote:
                quote = None
            k += 1
            continue
        if in_tmpl and not interp:
            if ch == "\\":
                k += 2
                continue
            if ch == "$" and nx == "{":
                brace += 1
                interp.append(brace)
                k += 2
                continue
            if ch == "`":
                in_tmpl = False
            k += 1
            continue
        if ch in "'\"":
            quote = ch
        elif ch == "`":
            in_tmpl = True
        elif ch == "(":
            paren += 1
        elif ch == ")":
            paren -= 1
        elif ch == "{":
            brace += 1
        elif ch == "}":
            brace -= 1
            if interp and brace < interp[-1]:
                interp.pop()
        else:
            yield ch, k, prev, nx, paren, brace
        k += 1


def markup_tag_span(line, index):
    i = 0
    while i < len(line):
        ts = line.find("<", i)
        if ts < 0:
            return None
        if not (ts + 1 < len(line) and line[ts + 1].isascii() and line[ts + 1].isalpha()):
            i = ts + 1
            continue
        end = None
        for ch, j, _, _, _, brace in scan_js(line, ts + 1):
            if ch == ">" and brace == 0:
                end = j
                break
        if end is None:
            return None
        if ts <= index <= end:
            return ts, end
        i = end + 1
    return None


def containing_markup_tag(line, index):
    sp = markup_tag_span(line, index)
    return line[sp[0]:sp[1] + 1] if sp else line


def complete_markup_tag(line, index):
    sp = markup_tag_span(line, index)
    return line[sp[0]:sp[1] + 1] if sp else None


def _stripe_child_markup_empty(line, index):
    sp = markup_tag_span(line, index)
    if not sp:
        return True
    tag = line[sp[0]:sp[1] + 1]
    if tag.rstrip(">").rstrip().endswith("/"):
        return True
    return line[sp[1] + 1:].lstrip().startswith("</")


def _is_question(ch, prev, nx):
    return ch == "?" and prev not in (".", "?") and nx not in ("?", ".")


def find_ternary_split(text):
    q_pos = colon = None
    qp = qb = nested = 0
    for ch, i, prev, nx, paren, brace in scan_js(text, 0):
        if colon is None:
            if q_pos is None and _is_question(ch, prev, nx):
                q_pos, qp, qb = i, paren, brace
                continue
            same = paren == qp and brace == qb
            if q_pos is not None and _is_question(ch, prev, nx) and same:
                nested += 1
                continue
            if q_pos is not None and ch == ":" and same:
                if nested:
                    nested -= 1
                else:
                    colon = i
            continue
        if ch == "," and paren == qp and brace == qb:
            return text[:q_pos], text[q_pos + 1:colon], text[colon + 1:i], text[i:]
    if q_pos is not None and colon is not None:
        return text[:q_pos], text[q_pos + 1:colon], text[colon + 1:], ""
    return None


def exclusive_class_scopes(text):
    sp = find_ternary_split(text)
    if not sp:
        return [text]
    common, cons, alt, suffix = sp
    return [common + p + suffix for p in exclusive_class_scopes(cons)] + \
        [common + p + suffix for p in exclusive_class_scopes(alt)]


_TW_COLOR_BG = re.compile(r"\bbg-(?:red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|"
                          r"fuchsia|pink|rose)-[0-9]+\b", A)
_STATE_VARIANTS = {"hover", "focus", "focus-visible", "focus-within", "active", "visited", "disabled", "checked",
                   "open", "enabled", "invalid", "placeholder"}


def _in_state_variant(s, start):
    ts = max(s.rfind(c, 0, start) for c in " \t\n\r\x0c") + 1
    prefix = s[ts:start]
    if not prefix.endswith(":"):
        return False
    for v in prefix.rstrip(":").split(":"):
        v = v.lstrip("!")
        if v in _STATE_VARIANTS or v.startswith(("group-", "peer-", "aria-", "data-")):
            return True
    return False


def find_solid_chromatic_bg(s, skip_pale=False):
    """rules.rs#find_solid_chromatic_bg / find_gray_on_color_bg (skip_pale)."""
    for m in _TW_COLOR_BG.finditer(s):
        if s[m.end():m.end() + 1] == "/" or _in_state_variant(s, m.start()):
            continue
        if skip_pale and m.group(0).rsplit("-", 1)[-1] in ("50", "100"):
            continue
        return m.group(0)
    return None


def is_near_black_neutral_class(cls):
    shade = cls.strip().rsplit("-", 1)[-1]
    return shade.isdigit() and int(shade) >= 700


_STYLE_ATTR_VALUE = re.compile(r"(?i)\bstyle\s*=\s*(?:\"([^\"]*)\"|'([^']*)')")
_STYLE_OBJECT_ATTR = re.compile(r"\bstyle\s*=\s*\{\{")
_STYLE_EXPR_ATTR = re.compile(r"\bstyle\s*=\s*\{")
_JSX_SIDE_PROP = re.compile(r"^border(?:Left|Right)\s*=")
_CLASS_ATTR = re.compile(r"(?:^|[%s<])(className|class|tw|:class|v-bind:class|class:[-\w]+)%s*=%s*(\"[^\"]*\"|'[^']*'|\{)"
                         % (WS_CHARS, WS, WS))
_RADIUS_PROP_ATTR = re.compile(
    r"(?:^|\s)(borderRadius|border(?:Top|Bottom)(?:Left|Right)Radius|rounded(?:Top|Bottom|Left|Right|TopLeft|TopRight|"
    r"BottomLeft|BottomRight)?)\s*=\s*(\"[^\"]*\"|'[^']*'|\{[^}]*\})")
_CLASS_HELPER = re.compile(r"\b(?:cn|clsx|cx|classNames|classnames|twMerge|twJoin)\b")
_TW_SIDE_TAB_WHOLE = re.compile(r"^border-([lrse])-[0-9]+$")


def literal_class_text(expr):
    classes, rest, p, n = [], [], 0, len(expr)
    while p < n:
        c = expr[p]
        if c in "\"'`":
            e = p + 1
            while e < n and expr[e] != c:
                if expr[e] == "\\":
                    e += 1
                e += 1
            lit = expr[p + 1:min(e, n)]
            if has_interpolation(lit):
                return None
            classes.append(" " + lit)
            p = e + 1
            continue
        rest.append(c)
        p += 1
    rest = _CLASS_HELPER.sub("", "".join(rest))
    return "".join(classes) if all(ch.isspace() or ch in "(),+[]" for ch in rest) else None


def tag_own_corners(tag, corners):
    for m in _RADIUS_PROP_ATTR.finditer(tag):
        prop = m.group(1)
        value = m.group(2).strip("\"'{}").strip().strip("\"'")
        zero = value in ("0", "0px", "none")
        if prop.startswith("rounded"):
            if not zero:
                corners.set_unknown()
            elif prop == "rounded":
                corners.apply("border-radius", "0")
            continue
        if not zero and _BARE_NUMBER.match(value):
            corners.set_unknown()
            continue
        corners.apply(prop, value)
    m = _STYLE_ATTR_VALUE.search(tag)
    if m:
        apply_statements(corners, split_statements(m.group(1) if m.group(1) is not None else (m.group(2) or ""), False), False)
    else:
        m = _STYLE_OBJECT_ATTR.search(tag)
        if m:
            obj = _balanced_braces(tag, m.end() - 1)
            if obj is None:
                return Corners.unknown()
            apply_statements(corners, split_statements(obj, True), False)
        elif _STYLE_EXPR_ATTR.search(tag):
            return Corners.unknown()
    return corners


def markup_tag_corners(line, index):
    tag = complete_markup_tag(line, index)
    if tag is None or "{..." in tag or "{ ..." in tag:
        return Corners.unknown()
    corners = Corners()
    for m in _CLASS_ATTR.finditer(tag):
        name, val = m.group(1), m.group(2)
        if val == "{":
            inner = _balanced_braces(tag, m.start(2))
            text = literal_class_text(inner) if inner is not None else None
        elif name in ("class", "className", "tw"):
            inner = val[1:-1]
            text = None if "{" in inner else inner
        else:
            text = None
        if text is None:
            return Corners.unknown()
        cls = tailwind_declared_corners(text)
        if cls.declared:
            corners = cls
    return tag_own_corners(tag, corners)


def in_style_attribute(line, index):
    for m in _STYLE_ATTR_VALUE.finditer(line):
        g = 1 if m.group(1) is not None else 2
        if m.start(g) <= index <= m.end(g):
            return True
    for m in _STYLE_OBJECT_ATTR.finditer(line):
        if m.start() < index:
            obj = _balanced_braces(line, m.end() - 1)
            if obj is None or index <= m.end() + len(obj):
                return True
    return False


def _side_of(whole):
    m = _TW_SIDE_TAB_WHOLE.match(whole)
    if m:
        return 3 if m.group(1) in "ls" else 1
    low = whole.lower()
    return 3 if ("left" in low or "start" in low) else 1


def side_tab_rounded_in_scope(m, src, i, sass):
    """regex_matchers.rs#side_tab_rounded_in_scope."""
    whole, line = m.group(0), src.lines[i]
    if _TW_SIDE_TAB_WHOLE.match(whole):
        return markup_tag_corners(line, m.start()).rounded_away(_side_of(whole))
    side = _side_of(whole)
    if _JSX_SIDE_PROP.match(whole) or in_style_attribute(line, m.start()):
        corners = markup_tag_corners(line, m.start())
    elif sass:
        corners = sass_scope_corners(src, i, Corners())
    else:
        corners = brace_scope_corners(src, i, m.start(), Corners())
    return corners.rounded_away(side)


def side_tab_known_square_in_sheet(m, src, i, sass, index_text, sheet, cache):
    whole = m.group(0)
    if _TW_SIDE_TAB_WHOLE.match(whole):
        return False
    side = _side_of(whole)
    if sass:
        return not sass_scope_corners(src, i, Corners.unknown()).rounded_away(side) or not sheet.rounded_away(side)
    idx = cache.get(index_text)
    if idx is None:
        idx = cache[index_text] = CssHostIndex(index_text)
    return idx.is_declaration_known_square(src.offset(i, m.start()), side, sheet)


def _literal_tag_classes(tag):
    classes = []
    for m in _CLASS_ATTR.finditer(tag):
        name, val = m.group(1), m.group(2)
        if val == "{":
            inner = _balanced_braces(tag, m.start(2))
            text = literal_class_text(inner) if inner is not None else None
        elif name in ("class", "className", "tw"):
            inner = val[1:-1]
            text = None if "{" in inner else inner
        else:
            text = None
        if text is None:
            return None
        classes.extend(text.split())
    return classes


def _tag_squares_itself(m, src, i, tag, side):
    cls = _literal_tag_classes(tag)
    if cls is not None and any(c in ("rounded-none", "rounded-0") for c in cls):
        return True
    if not tag_own_corners(tag, Corners.unknown()).rounded_away(side):
        return True
    whole = m.group(0)
    in_obj = not _TW_SIDE_TAB_WHOLE.match(whole) and not _JSX_SIDE_PROP.match(whole) \
        and not in_style_attribute(src.lines[i], m.start())
    return in_obj and not brace_scope_corners(src, i, m.start(), Corners.unknown()).rounded_away(side)


def side_tab_markup_known_square(m, src, i, sources, sheet, imports, cache):
    if not sheet.declared and not imports:
        return True
    tag = complete_markup_tag(src.lines[i], m.start())
    if tag is None:
        return True
    side = _side_of(m.group(0))
    if imports and not _tag_squares_itself(m, src, i, tag, side):
        return False
    if not sheet.declared:
        return True
    if re.search(r"(?:^|\s)css\s*=", tag):
        return False
    classes = _literal_tag_classes(tag)
    if classes is None:
        return False
    nm = re.match(r"^<([A-Za-z][-\w.:]*)", tag)
    name = nm.group(1) if nm else ""
    component = name[:1].isupper() or "." in name
    tag_type = name.lower() if (not component and name) else None
    styled_root = component and bool(re.search(r"\b%s\s*=\s*styled\b" % re.escape(name), src.text))
    idx = cache.get(sources)
    if idx is None:
        idx = cache[sources] = CssHostIndex(sources)
    return idx.is_element_known_square(tag_type, styled_root, classes, side, sheet)


# ════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# Colour helpers (regex_matchers.rs#is_neutral_authored_color)
# ════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
NEUTRAL_COLOR_KEYWORDS = {"transparent", "currentcolor", "black", "white", "gray", "grey", "silver", "dimgray",
                          "dimgrey", "darkgray", "darkgrey", "lightgray", "lightgrey", "gainsboro", "whitesmoke"}


def _spread(c):
    return max(c[:3]) - min(c[:3])


def is_neutral_color(value):
    """color.rs#is_neutral_color, approximated through parse_color: channel spread under 30."""
    c = C.parse_color(value)
    return c is None or _spread(c) < 30


def is_neutral_authored_color(raw):
    c = jtrim(raw).lower()
    if not c:
        return False
    if c in NEUTRAL_COLOR_KEYWORDS:
        return True
    if re.match(r"^rgba?\(", c):
        m = re.match(r"^rgba?\(" + WS + r"*([0-9.]+)[%s,]+([0-9.]+)[%s,]+([0-9.]+)" % (WS_CHARS, WS_CHARS), c)
        if m:
            return max(map(pf, m.groups())) - min(map(pf, m.groups())) < 30
        return is_neutral_color(c)
    if re.match(r"^(?:hsla?|oklch|oklab|lab|lch|hwb)\(", c):
        return is_neutral_color(c)
    m = re.match(r"^#([0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})$", c)
    if m:
        h = m.group(1)
        if len(h) in (3, 4):
            ch = [int(x * 2, 16) for x in h[:3]]
        else:
            ch = [int(h[k:k + 2], 16) for k in (0, 2, 4)]
        return max(ch) - min(ch) < 30
    return False


_NEUTRAL_BORDER = re.compile(r"(?i:solid)" + WS + r"+((?:(?i:rgb)[aA]?|(?i:hsl)[aA]?|(?i:oklch)|(?i:oklab)|(?i:lab)|"
                             r"(?i:lch)|(?i:hwb)|(?i:color))\([^)]*\)|#[0-9a-fA-F]{3,8}\b|[a-zA-Z]+)", A)


def is_neutral_border_color(s):
    m = _NEUTRAL_BORDER.search(s)
    return bool(m) and is_neutral_authored_color(m.group(1))


# ════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# REGEX_MATCHERS (regex_matchers.rs, in order)
# ════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
def R(p):
    return re.compile(p, A)


SIDE_TAB_TW = R(r"\bborder-[lrse]-([0-9]+)\b")
SIDE_TAB_CSS = R(r"(?i:border-)(?i:left|right)" + WS + r"*:" + WS + r"*([0-9]+)(?i:px)" + WS + r"+(?i:solid)[^;]*")
TRAILING_SEMI = R(WS + r"*;?" + WS + r"*$")
SIDE_TAB_WIDTH = R(r"(?i:border-)(?i:left|right)(?i:-width)" + WS + r"*:" + WS + r"*([0-9]+)(?i:px)")
SIDE_TAB_INLINE = R(r"(?i:border-inline-)(?i:start|end)" + WS + r"*:" + WS + r"*([0-9]+)(?i:px)" + WS + r"+(?i:solid)")
SIDE_TAB_INLINE_WIDTH = R(r"(?i:border-inline-)(?i:start|end)(?i:-width)" + WS + r"*:" + WS + r"*([0-9]+)(?i:px)")
SIDE_TAB_JS = R(r"border(?:Left|Right)" + WS + r"*[:=]" + WS + r"*[\"'`]([0-9]+)px" + WS + r"+solid")
STRIPE_CHILD_TW = R(r"w-(?:0\.5|1(?:\.5)?|2(?:\.5)?|3|\[(?:[2-9]|1[0-2])px\])")
STRIPE_CHILD_HEIGHT = R(r"h-(?:px\b|[0-9]|\[)")
STRIPE_CHILD_ARIA = R(r"(?i)aria-(?:current|selected)")
STRIPE_CHILD_ROUNDED_FULL = R(r"\brounded-full\b")
STRIPE_CHILD_CUE = R(r"\b(?:shrink-0|rounded-[lres](?:-[A-Za-z0-9_]+)?|left-0|right-0|inset-0|inset-y-0)\b")
BORDER_ACCENT_TW = R(r"\bborder-[tb]-([0-9]+)\b")
ANIMATE_SPIN = R(r"\banimate-spin\b")
BORDER_ACCENT_CSS = R(r"(?i:border-)(?i:top|bottom)" + WS + r"*:" + WS + r"*([0-9]+)(?i:px)" + WS + r"+(?i:solid)")
OVERUSED_FONT_NAMES = ["Inter", "Roboto", "Open Sans", "Lato", "Montserrat", "Arial", "Helvetica", "Fraunces",
                       "Geist Sans", "Geist Mono", "Geist", "Mona Sans", "Plus Jakarta Sans", "Space Grotesk",
                       "Recoleta", "Instrument Sans", "Instrument Serif"]
OVERUSED_FONTS = {"inter", "roboto", "open sans", "lato", "montserrat", "arial", "helvetica", "fraunces",
                  "instrument sans", "instrument serif", "geist", "geist sans", "geist mono", "mona sans",
                  "plus jakarta sans", "space grotesk", "recoleta"}
OVERUSED_FONT = R(r"(?i:font-family)" + WS + r"*:" + WS + r"*['\"]?((?i:" + "|".join(re.escape(x) for x in OVERUSED_FONT_NAMES) + r"))\b")
GOOGLE_FONTS_URL = R(r"(?i:fonts)\.(?i:googleapis)\.(?i:com)/(?i:css)2?\?[^\"'%s)<>]*" % WS_CHARS)
GRADIENT_TEXT = R(r"(?i:background-clip)" + WS + r"*:" + WS + r"*(?i:text)|(?i:-webkit-background-clip)" + WS + r"*:" + WS + r"*(?i:text)")
GRADIENT_WORD = R(r"(?i:gradient)")
BG_CLIP_TEXT = R(r"\bbg-clip-text\b")
BG_GRADIENT_TO = R(r"\b(?i:bg-gradient-to-)")
GRAY_TEXT = R(r"\btext-(?:gray|slate|zinc|neutral|stone)-([0-9]+)\b")
PURPLE_TEXT = R(r"\btext-(?:purple|violet|indigo)-([0-9]+)\b")
HEADING_CTX = R(r"\b(?i:text-)(?:[2-9](?i:xl)|[3-9](?i:xl))\b|<(?i:h)[1-3]")
FROM_PURPLE = R(r"\bfrom-(?:purple|violet|indigo)-([0-9]+)\b")
TO_COLOR = R(r"\bto-(?:purple|violet|indigo|blue|cyan|pink|fuchsia)-[0-9]+\b")
ANIMATE_BOUNCE = R(r"\banimate-bounce\b")
ANIMATION_BOUNCE = R(r"(?i:animation)(?i:-name)?" + WS + r"*:" + WS + r"*([^;{}]*(?i:bounce|elastic|wobble|jiggle|spring)[^;{}]*)")
MOTION_TOKEN = R(r"(?i:bounce|elastic|wobble|jiggle|spring)")
COMMA_WS_SPLIT = R(r"[,%s]+" % WS_CHARS)
CUBIC_BEZIER = MC.BEZIER_RE
BROKEN_IMG_SRC = R(r"<(?i:img)\b[^>]*?\b(?i:src)" + WS + r"*=" + WS + r"*(?:\"\"|''|\"" + WS + r"+\"|'" + WS + r"+'|\"#\"|'#')")
IMG_OPEN = R(r"<(?i:img)\b")
SRC_ATTR = R(r"\b(?i:src)" + WS + r"*=")
_SAFE_ELEMENT = R(r"<(?:(?i:blockquote)|(?i:nav)[%s>]|(?i:pre)[%s>]|(?i:code)[%s>]|(?i:a)%s|(?i:input)[%s>]|(?i:span)[%s>])"
                  % (WS_CHARS, WS_CHARS, WS_CHARS, WS, WS_CHARS, WS_CHARS))
_ROUNDED_NONE = R(r"\brounded-none\b")
_ROUNDED = R(r"\brounded(?:-[A-Za-z0-9_]+)?\b")
_BORDER_RADIUS_WORD = R(r"(?i:border-radius)")


def has_rounded(s):
    return bool(_ROUNDED.search(_ROUNDED_NONE.sub("", s)))


def is_safe_element(s):
    return bool(_SAFE_ELEMENT.search(s))


def google_font_families(url_text):
    """fonts.rs#extract_google_font_families over one URL."""
    out = []
    for m in GOOGLE_FONTS_URL.finditer(url_text):
        url = m.group(0)
        q = url.find("?")
        if q < 0:
            continue
        for pair in url[q + 1:].replace("&amp;", "&").split("&"):
            if not pair:
                continue
            name, _, value = pair.partition("=")
            if urllib.parse.unquote_plus(name) == "family":
                for part in urllib.parse.unquote_plus(value).split("|"):
                    f = jtrim(part.split(":")[0]).lower()
                    if f:
                        out.append(f)
    return out


def _first_overused(text):
    return next((f for f in google_font_families(text) if f in OVERUSED_FONTS), "")


def _hyphen_safe_prefix(text, i):
    return i == 0 or not (text[i - 1].isascii() and (text[i - 1].isalnum() or text[i - 1] == "-"))


def _hyphen_safe_suffix(text, e):
    return e >= len(text) or not (text[e].isascii() and (text[e].isalnum() or text[e] in "-./"))


def _stripe_child_test(m, line):
    if not _hyphen_safe_prefix(line, m.start()) or not _hyphen_safe_suffix(line, m.end()):
        return False
    scope = containing_markup_tag(line, m.start())
    return (find_solid_chromatic_bg(scope) is not None and _stripe_child_markup_empty(line, m.start())
            and any(_hyphen_safe_prefix(scope, c.start()) and _hyphen_safe_suffix(scope, c.end())
                    for c in STRIPE_CHILD_CUE.finditer(scope))
            and not any(_hyphen_safe_prefix(scope, h.start()) for h in STRIPE_CHILD_HEIGHT.finditer(scope))
            and not STRIPE_CHILD_ROUNDED_FULL.search(scope) and not STRIPE_CHILD_ARIA.search(scope))


def _gray_pairs(line, gray, index):
    return [s for s in exclusive_class_scopes(containing_markup_tag(line, index)) if gray in s]


def _gray_test(m, line):
    return not is_near_black_neutral_class(m.group(0)) and any(
        find_solid_chromatic_bg(s, True) for s in _gray_pairs(line, m.group(0), m.start()))


def _gray_fmt(m, line):
    bg = next((b for b in (find_solid_chromatic_bg(s, True) for s in _gray_pairs(line, m.group(0), m.start())) if b), "?")
    return "%s on %s" % (m.group(0), bg)


def _bounce_fmt(m, _):
    tok = next((p for p in COMMA_WS_SPLIT.split(m.group(1)) if MOTION_TOKEN.search(p)), None)
    return "animation: %s" % (tok if tok is not None else jtrim(m.group(1)))


class _ImgMatch:
    """A synthetic match for the hand-written <img> scan."""

    def __init__(self, text, start):
        self._t, self._s = text, start

    def group(self, i=0):
        return self._t

    def start(self, i=0):
        return self._s

    def end(self, i=0):
        return self._s + len(self._t)


def find_img_without_src(line):
    """Port of /<img\\b(?:(?!\\bsrc\\s*=)[^>])*>/gi."""
    out, pos = [], 0
    while True:
        m = IMG_OPEN.search(line, pos)
        if not m:
            break
        gt = line.find(">", m.end())
        if gt < 0:
            pos = m.end()
            continue
        s = SRC_ATTR.search(line, m.end())
        if s and s.start() < gt:
            pos = m.end()
            continue
        out.append(_ImgMatch(line[m.start():gt + 1], m.start()))
        pos = gt + 1
    return out


def _all(rx):
    return lambda line: list(rx.finditer(line))


def _n(m):
    return int(m.group(1))


MATCHERS = [
    # (rule id, find_all(line), test(m, context), fmt(m, context))
    ("side-tab", _all(SIDE_TAB_TW), lambda m, c: _n(m) >= (2 if has_rounded(c) else 4), lambda m, c: m.group(0)),
    ("side-tab", _all(SIDE_TAB_CSS),
     lambda m, c: not is_safe_element(c) and not is_neutral_border_color(m.group(0))
     and _n(m) >= (2 if _BORDER_RADIUS_WORD.search(c) else 3),
     lambda m, c: TRAILING_SEMI.sub("", m.group(0), count=1)),
    ("side-tab", _all(SIDE_TAB_WIDTH), lambda m, c: not is_safe_element(c) and _n(m) >= 3, lambda m, c: m.group(0)),
    ("side-tab", _all(SIDE_TAB_INLINE), lambda m, c: not is_safe_element(c) and _n(m) >= 3, lambda m, c: m.group(0)),
    ("side-tab", _all(SIDE_TAB_INLINE_WIDTH), lambda m, c: not is_safe_element(c) and _n(m) >= 3, lambda m, c: m.group(0)),
    ("side-tab", _all(SIDE_TAB_JS), lambda m, c: _n(m) >= 3, lambda m, c: m.group(0)),
    ("side-tab", _all(STRIPE_CHILD_TW), _stripe_child_test,
     lambda m, c: "%s + %s stripe child" % (m.group(0), find_solid_chromatic_bg(containing_markup_tag(c, m.start())))),
    ("border-accent-on-rounded", _all(BORDER_ACCENT_TW),
     lambda m, c: has_rounded(containing_markup_tag(c, m.start())) and _n(m) >= 1
     and not ANIMATE_SPIN.search(containing_markup_tag(c, m.start())), lambda m, c: m.group(0)),
    ("border-accent-on-rounded", _all(BORDER_ACCENT_CSS),
     lambda m, c: _n(m) >= 3 and bool(_BORDER_RADIUS_WORD.search(c)), lambda m, c: m.group(0)),
    ("overused-font", _all(OVERUSED_FONT), lambda m, c: True, lambda m, c: m.group(0)),
    ("overused-font", _all(GOOGLE_FONTS_URL), lambda m, c: bool(_first_overused(m.group(0))),
     lambda m, c: "Google Fonts: %s" % _first_overused(m.group(0))),
    ("gradient-text", _all(GRADIENT_TEXT), lambda m, c: bool(GRADIENT_WORD.search(c)),
     lambda m, c: "background-clip: text + gradient"),
    ("gradient-text", _all(BG_CLIP_TEXT), lambda m, c: bool(BG_GRADIENT_TO.search(c)),
     lambda m, c: "bg-clip-text + bg-gradient"),
    ("gray-on-color", _all(GRAY_TEXT), _gray_test, _gray_fmt),
    ("ai-color-palette", _all(PURPLE_TEXT), lambda m, c: bool(HEADING_CTX.search(c)),
     lambda m, c: "%s on heading" % m.group(0)),
    ("ai-color-palette", _all(FROM_PURPLE), lambda m, c: bool(TO_COLOR.search(c)),
     lambda m, c: "%s gradient" % m.group(0)),
    ("bounce-easing", _all(ANIMATE_BOUNCE), lambda m, c: True, lambda m, c: "animate-bounce (Tailwind)"),
    ("bounce-easing", _all(ANIMATION_BOUNCE), lambda m, c: True, _bounce_fmt),
    ("bounce-easing", _all(CUBIC_BEZIER), lambda m, c: MC.bezier_out_of_range(pf(m.group(2)), pf(m.group(4))),
     lambda m, c: "cubic-bezier(%s, %s, %s, %s)" % m.groups()),
    ("broken-image", _all(BROKEN_IMG_SRC), lambda m, c: True, lambda m, c: MC.utf16_prefix(m.group(0), 100)),
    ("broken-image", find_img_without_src, lambda m, c: not SRC_ATTR.search(m.group(0)),
     lambda m, c: MC.utf16_prefix(m.group(0), 100)),
]


def run_regex_matchers(lines, path, line_offset, block_context, sheet, sass):
    """detect_text.rs#run_regex_matchers -> [(rule, snippet, line)] (matcher-major order)."""
    out = []
    src = SourceText(lines)
    cache = {}
    for rid, find_all, test, fmt in MATCHERS:
        for i, line in enumerate(lines):
            ms = find_all(line)
            if not ms:
                continue
            context = " ".join(lines[max(0, i - 3):min(i + 4, len(lines))]) if block_context else line
            for m in ms:
                if not test(m, context):
                    continue
                if rid == "side-tab" and not _side_tab_keeps(m, src, i, sass, block_context, sheet, cache):
                    continue
                out.append((rid, fmt(m, context), i + 1 + line_offset))
    return out


def _is_stripe_child_match(m):
    return bool(STRIPE_CHILD_TW.fullmatch(m.group(0)))


def _side_tab_keeps(m, src, i, sass, block_context, sheet, cache):
    """The rounded-card gate (detect_text.rs#run_regex_matchers): a side accent drops only on a box known square."""
    if _is_stripe_child_match(m) or side_tab_rounded_in_scope(m, src, i, sass):
        return True
    if sheet is None:
        return False
    if block_context:
        index_text = src.text
    else:
        pos = src.offset(i, m.start())
        st = sheet.style_text()
        index_text = st[0] if st and any(s <= pos <= e for s, e in st[1]) else None
    if index_text is not None:
        return not side_tab_known_square_in_sheet(m, src, i, sass, index_text, sheet.corners(), cache)
    return not side_tab_markup_known_square(m, src, i, sheet.style_sources(), sheet.corners(),
                                            sheet.imports_stylesheet(), cache)


# ════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# Stripe scans (detect_text.rs#scan_inset_stripe_css, css_scan.rs#scan_css_text_for_pseudo_stripe)
# ════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
_CHROMATIC_SHADOW_TOKEN = R(r"(?:^|-)(?i:" + "|".join(["accent", "kinpaku", "patina", "gold", "red", "orange", "amber",
                                                      "yellow", "lime", "green", "emerald", "teal", "cyan", "blue",
                                                      "indigo", "violet", "purple", "magenta", "pink", "rose", "coral",
                                                      "aqua", "mint", "burgundy", "crimson", "scarlet"]) + r")(?:-|$)")
_IMPORTANT_TAIL_STRICT = R(WS + r"*(?i:!important)" + WS + r"*$")
_IMPORTANT_TAIL_LOOSE = R(WS + r"*!" + WS + r"*(?i:important)" + WS + r"*$")
_NO_PAINT_KEYWORD = R(r"^(?i:currentcolor|transparent|inherit|unset)$")
_VAR_NAME = R(r"^(?i:var)\(" + WS + r"*(--[A-Za-z0-9_-]+)")
_COLOR_SHAPE = R(r"^(?:#|(?i:rgb)[aA]?\(|(?i:hsl)[aA]?\(|(?i:hwb)\(|(?i:oklch)\(|(?i:oklab)\(|(?i:lch)\(|(?i:lab)\(|(?i:color)\(|[a-zA-Z]+$)")
_SHADOW_LENGTH = R(r"^-?[0-9]*\.?[0-9]+(?i:px)?$")
_PX_TAIL = R(r"(?i:px)$")
_INSET_TOKEN = R(r"^(?i:inset)$")
_STATE_PSEUDO_T = R(r":(?i:hover|focus|focus-visible|focus-within|active|checked|target)\b")
_ARIA_SELECTED = R(r"\[(?i:aria-selected)" + WS + r"*[*^$|~]?=" + WS + r"*[\"']?(?i:true)")
_ARIA_CURRENT = R(r"\[(?i:aria-current)")
_ARIA_CURRENT_FALSE_TAIL = R(r"^" + WS + r"*[*^$|~]?=" + WS + r"*[\"']?(?i:false)")
_WIDTH_DECL = R(r"(?:^|;)" + WS + r"*(?i:width|inline-size)" + WS + r"*:" + WS + r"*([0-9]+(?:\.[0-9]+)?)(?i:px)")
_BOX_SHADOW_DECL = R(r"(?:^|;)" + WS + r"*(?i:box-shadow)" + WS + r"*:" + WS + r"*([^;]+)")
_INSET_WORD = R(r"\b(?i:inset)\b")


def _token_after_prefix(s, prefix_chars, pred, run_dash=True):
    """`(?:^|[prefix])(?:tok)(?![\\w-])` evaluated as maximal [\\w-] runs after each prefix."""
    def run_at(p):
        e = p
        while e < len(s) and s[e].isascii() and (s[e].isalnum() or s[e] == "_" or (run_dash and s[e] == "-")):
            e += 1
        return s[p:e]
    if pred(run_at(0)):
        return True
    return any(pred(run_at(i + 1)) for i, c in enumerate(s) if c in prefix_chars or c in JS_WS)


def _has_state_word(sel, prefixed=False):
    def pred(run):
        word = re.match(r"[A-Za-z0-9_]*", run).group(0)
        if word.lower() in ("active", "current", "selected"):
            return True
        return prefixed and run.lower().startswith(("btn", "button", "link"))
    return _token_after_prefix(sel, "._[-", pred)


def _has_tag(sel, tags):
    return _token_after_prefix(sel, ">+~,(", lambda run: run.lower() in tags)


def _aria_current_not_false(sel):
    return any(not _ARIA_CURRENT_FALSE_TAIL.match(sel[m.end():]) for m in _ARIA_CURRENT.finditer(sel))


def _split_layers(value):
    return MC.split_commas_outside_parens(value)


def _tokenize_shadow_layer(layer):
    toks, depth, cur = [], 0, []
    for ch in layer:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0 and ch in JS_WS:
            if cur:
                toks.append("".join(cur))
                cur = []
            continue
        cur.append(ch)
    if cur:
        toks.append("".join(cur))
    return toks


def _inset_color_chromatic(raw):
    color = _IMPORTANT_TAIL_STRICT.sub("", jtrim(raw), count=1)
    if _NO_PAINT_KEYWORD.match(color):
        return False
    m = _VAR_NAME.match(color)
    if m:
        return bool(_CHROMATIC_SHADOW_TOKEN.search(m.group(1)))
    if not _COLOR_SHAPE.match(color):
        return False
    return not is_neutral_authored_color(color)


def _js_number(s):
    s = jtrim(s)
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return float("nan")


def scan_inset_stripe_css(raw, line_offset, sheet):
    """detect_text.rs#scan_inset_stripe_css -> [(snippet, line)]."""
    content = strip_css_comments(raw)
    out, idx = [], None
    for m in MC.RULE_BLOCK.finditer(content):
        sel_raw = m.group(1)
        sel_start = m.start(1) + (len(sel_raw) - len(sel_raw.lstrip(JS_WS)))
        selector = _WS_RUN.sub(" ", jtrim(sel_raw))
        if not selector or _STATE_PSEUDO_T.search(selector) or _ARIA_SELECTED.search(selector) \
                or _aria_current_not_false(selector) or _has_state_word(selector, False) \
                or _has_tag(selector, {"button", "hr", "tr", "td", "th", "table", "blockquote", "pre", "code"}):
            continue
        body = m.group(2)
        widths = list(_WIDTH_DECL.finditer(body))
        if widths and _js_number(widths[-1].group(1)) <= 40:
            continue
        decls = list(_BOX_SHADOW_DECL.finditer(body))
        if not decls or not _INSET_WORD.search(decls[-1].group(1)):
            continue
        value = jtrim(_IMPORTANT_TAIL_LOOSE.sub("", decls[-1].group(1), count=1))
        for raw_layer in _split_layers(value):
            toks = _tokenize_shadow_layer(jtrim(raw_layer))
            if not any(_INSET_TOKEN.match(t) for t in toks):
                continue
            rest = [t for t in toks if not _INSET_TOKEN.match(t)]
            lengths = [t for t in rest if _SHADOW_LENGTH.match(t)]
            colors = [t for t in rest if not _SHADOW_LENGTH.match(t)]
            if len(lengths) < 2 or len(lengths) > 4 or len(colors) != 1:
                continue
            vals = [(_js_number(_PX_TAIL.sub("", t)), bool(_PX_TAIL.search(t))) for t in lengths]
            x, y = vals[0], vals[1]
            blur = vals[2][0] if len(vals) > 2 else 0.0
            spread = vals[3][0] if len(vals) > 3 else 0.0
            if (x[0] != 0 and not x[1]) or (y[0] != 0 and not y[1]) or blur != 0 or spread != 0:
                continue
            ax, ay = abs(x[0]), abs(y[0])
            if not ((3 <= ax <= 12 and ay == 0) or (3 <= ay <= 12 and ax == 0)):
                continue
            if not _inset_color_chromatic(colors[0]):
                continue
            edge = ("left" if x[0] > 0 else "right") if ay == 0 else ("top" if y[0] > 0 else "bottom")
            side = {"left": 3, "right": 1, "top": 0}.get(edge, 2)
            if idx is None:
                idx = CssHostIndex(content)
            if idx.is_rule_known_square(sel_start, selector, side, sheet.corners()):
                continue
            out.append(("%s — inset box-shadow %spx stripe (%s)" % (selector, num_str(ax if ay == 0 else ay), edge),
                        line_offset + line_of_offset(content, sel_start)))
            break
    return out


_PSEUDO_SEL = R(r"::?(?i:before|after)\b")
_PROSE_TAG = R(r"\b(?i:blockquote|pre|code|nav|hr)\b")
_FULL_PCT = R(r"^100(?:\.0*)?%$")
_NO_PAINT_BG = R(r"^(?i:none|transparent|inherit|initial|unset|currentcolor)$")
_STRIPE_COLOR_TOKEN = R(r"(?:(?i:rgb)[aA]?|(?i:hsl)[aA]?|(?i:oklch)|(?i:oklab)|(?i:lab)|(?i:lch)|(?i:hwb))\([^)]*\)|#[0-9a-fA-F]{3,8}\b")
_NEUTRAL_NAME = R(r"^(?i:white|black|gray|grey|silver)$")
_STATE_PSEUDO = R(r":(?i:hover|focus|focus-visible|focus-within|active|checked)\b")
_STRIPE_URL_FN = R(r"(?i:url)\((?:\"[^\"]*\"|'[^']*'|[^)]*)\)")
_ZERO_OFFSET = R(r"^-?0(?:px|%|rem|em)?$")


def _is_zero(v):
    return v is not None and bool(_ZERO_OFFSET.match(jtrim(v)))


def _image_no_colour(bg):
    if not _STRIPE_URL_FN.search(bg):
        return False
    rest = _STRIPE_URL_FN.sub(" ", bg)
    return not any(C.parse_color(t) is not None or "var(" in t
                   for t in re.split(r"[%s,/]" % WS_CHARS, rest) if t)


def _get_or(d, a, b):
    return d.get(a) or d.get(b) or ""


def scan_pseudo_stripe(raw):
    """css_scan.rs#scan_css_text_for_pseudo_stripe -> [(snippet, index, selector, side)]."""
    content = strip_css_comments(raw)
    props = MC.custom_props(content)
    out, seen = [], []
    for m in MC.RULE_BLOCK.finditer(content):
        selector = jtrim(m.group(1))
        if not _PSEUDO_SEL.search(selector) or _PROSE_TAG.search(selector):
            continue
        d = MC.parse_decl_block(m.group(2))
        if d.get("position") not in ("absolute", "fixed"):
            continue
        wv = jtrim(MC.resolve_var_refs(_get_or(d, "width", "inline-size"), props))
        hv = jtrim(MC.resolve_var_refs(_get_or(d, "height", "block-size"), props))
        wpx, hpx = MC.css_length_to_px(wv), MC.css_length_to_px(hv)
        vertical = wpx is not None and 3 <= wpx <= 12
        horizontal = (hpx is not None and 3 <= hpx <= 12
                      and not _has_tag(selector, {"a", "button", "summary", "tr", "td", "th", "table", "li"})
                      and not _ARIA_SELECTED.search(selector) and not _aria_current_not_false(selector)
                      and not _has_state_word(selector, True) and not _STATE_PSEUDO.search(selector))
        if not vertical and not horizontal:
            continue
        top, right, bottom, left = d.get("top"), d.get("right"), d.get("bottom"), d.get("left")
        if d.get("inset"):
            p = [x for x in re.split(WS + "+", d["inset"]) if x] or [""]
            t, r_, b, l_ = {1: (p[0],) * 4, 2: (p[0], p[1], p[0], p[1]), 3: (p[0], p[1], p[2], p[1])}.get(len(p), tuple(p[:4]))
            top = top if top is not None else t
            right = right if right is not None else r_
            bottom = bottom if bottom is not None else b
            left = left if left is not None else l_
        if left is None:
            left = d.get("inset-inline-start")
        if right is None:
            right = d.get("inset-inline-end")
        edge, thick = None, None
        if vertical:
            tp = MC.css_length_to_px(MC.resolve_var_refs(top or "", props))
            bp = MC.css_length_to_px(MC.resolve_var_refs(bottom or "", props))
            full = (_is_zero(top) and _is_zero(bottom)) or bool(_FULL_PCT.match(hv)) or (
                tp is not None and bp is not None and 0 <= tp <= 20 and 0 <= bp <= 20)
            if full:
                edge = "left" if _is_zero(left) else ("right" if _is_zero(right) else None)
                thick = wpx
        if edge is None and horizontal:
            if (_is_zero(left) and _is_zero(right)) or _FULL_PCT.match(wv):
                edge = "top" if _is_zero(top) else ("bottom" if _is_zero(bottom) else None)
                thick = hpx
        if edge is None:
            continue
        bg = jtrim(MC.resolve_var_refs(_get_or(d, "background-color", "background"), props))
        if not bg or _NO_PAINT_BG.match(bg):
            continue
        tok = _STRIPE_COLOR_TOKEN.search(bg)
        c = C.parse_color(tok.group(0) if tok else bg)
        if c is not None:
            if c[3] < 0.1 or _spread(c) < 30:
                continue
        elif _NEUTRAL_NAME.match(bg) or _image_no_colour(bg):
            continue
        if "&" not in selector:
            if selector in seen:
                continue
            seen.append(selector)
        start = m.start(1) + (len(m.group(1)) - len(m.group(1).lstrip(JS_WS)))
        out.append(("%s — absolute %spx pseudo-element stripe (%s: 0)"
                    % (selector, "null" if thick is None else num_str(thick), edge), start, selector,
                    {"top": 0, "right": 1, "bottom": 2}.get(edge, 3)))
    return out


def pseudo_stripe_findings(text, line_offset, sheet):
    out, idx = [], None
    for snip, index, selector, side in scan_pseudo_stripe(text):
        if idx is None:
            idx = CssHostIndex(text)
        if idx.is_rule_known_square(index, selector, side, sheet.corners()):
            continue
        out.append(("side-tab", snip, line_offset + line_of_offset(text, index)))
    return out


# ════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# Grid background, glow, halo (css_scan.rs)
# ════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
_HAIRLINE = R(r"\b[0-9]{1,3}px" + WS + r"*," + WS + r"*(?i:transparent)" + WS + r"+[0-9]{1,3}px")
_INVERTED_HAIRLINE = R(r"(?i:transparent)" + WS + r"+(?i:calc)\(100%" + WS + r"*-" + WS + r"*[0-9]{1,3}px\)")
_SIZE_DECL_PX = R(r"(?i:background-size)" + WS + r"*:[^;{}\"']*\b[0-9]{1,3}px\b")
_SHORTHAND_PX = R(r"/" + WS + r"*[0-9]{1,3}px\b")
_GRID_BG_DECL = R(r"\b(?i:background)(?:-(?i:image))?" + WS + r"*:" + WS + r"*([^;{}\"']*)")
_GRID_BLOCK = R(r"\{([^{}]*)\}|(?i:style)" + WS + r"*=" + WS + r"*\"([^\"]*)\"|(?i:style)" + WS + r"*=" + WS + r"*'([^']*)'")


def scan_grid_background(content):
    """css_scan.rs#scan_css_text_for_grid_background -> index or None."""
    for blk in _GRID_BLOCK.finditer(content):
        block = blk.group(1) or blk.group(2) or blk.group(3) or ""
        count, joined = 0, []
        for bm in _GRID_BG_DECL.finditer(block):
            v = bm.group(1)
            count += len(_HAIRLINE.findall(v)) + len(_INVERTED_HAIRLINE.findall(v))
            joined.append(v + ";")
        if not count:
            continue
        if count >= 2 and (_SIZE_DECL_PX.search(block) or _SHORTHAND_PX.search("".join(joined))):
            return blk.start()
    return None


_DARK_BG = R(r"(?i:background)(?:-(?i:color))?" + WS + r"*:" + WS + r"*(?:#(?:0[0-9a-fA-F]|1[0-9a-fA-F]|2[0-3])[0-9a-fA-F]{4}\b"
             r"|#(?:0|1)[0-9a-fA-F]{2}\b|(?i:rgb)\(" + WS + r"*([0-9]{1,2})" + WS + r"*," + WS + r"*([0-9]{1,2})" + WS
             + r"*," + WS + r"*([0-9]{1,2})" + WS + r"*\))")
_TW_DARK_BG = R(r"\bbg-(?:gray|slate|zinc|neutral|stone)-(?:9[0-9]{2}|800)\b")
_ROOT_BLOCK = R(r"(?:^|[}%s,;>])(?:(?i:body)|(?i:html)|:(?i:root))" % WS_CHARS + WS + r"*(?:,[^{]*)?\{([^}]*)\}")
_INLINE_BODY_STYLE = R(r"<(?i:body)[^>]*\b(?i:style)" + WS + r"*=" + WS + r"*\"([^\"]*)\"")
_BG_DECL = R(r"(?i:background)(?:-(?i:color))?" + WS + r"*:" + WS + r"*([^;{}]+)")


def _starts_property_token(text, start):
    def clean(at):
        return at == 0 or not (text[at - 1] == "-" or (text[at - 1].isascii() and (text[at - 1].isalnum() or text[at - 1] == "_"))
                               or ord(text[at - 1]) >= 0x80)
    if clean(start):
        return True
    return any(start >= len(p) and text[start - len(p):start].lower() == p and clean(start - len(p))
               for p in ("-webkit-", "-moz-", "-ms-", "-o-"))


def _luminance(c):
    def lin(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2])


def css_text_has_dark_root_bg(content, props):
    if any(_starts_property_token(content, m.start()) for m in _DARK_BG.finditer(content)) or _TW_DARK_BG.search(content):
        return True
    scopes = [m.group(1) for m in _ROOT_BLOCK.finditer(content)]
    m = _INLINE_BODY_STYLE.search(content)
    if m:
        scopes.append(m.group(1))
    for sc in scopes:
        for bm in _BG_DECL.finditer(sc):
            if not _starts_property_token(sc, bm.start()):
                continue
            c = C.parse_color(MC.resolve_var_refs(jtrim(bm.group(1)), props))
            if c is not None and c[3] > 0.5 and _luminance(c) < 0.1:
                return True
    return False


_SHADOW_DECL = R(r"\b((?i:box)-(?i:shadow)|(?i:text)-(?i:shadow))" + WS + r"*:" + WS + r"*([^;{}]+)")
_SHADOW_COLOR_FN = R(r"(?:(?i:rgb)[aA]?|(?i:hsl)[aA]?|(?i:hwb)|(?i:oklch)|(?i:oklab)|(?i:lch)|(?i:lab)|(?i:color))\([^)]*\)")
_SHADOW_HEX = R(r"#[0-9a-fA-F]{3,8}\b")
_SHADOW_WORD = R(r"[a-zA-Z][a-zA-Z]*")
_SHADOW_LEN = R(r"(-?[0-9]*\.?[0-9]+)(px|rem|em)?")


def find_shadow_color(layer):
    """rules_types.rs#find_shadow_color -> (rgba|None, start, end) or None."""
    for rx in (_SHADOW_COLOR_FN, _SHADOW_HEX):
        m = rx.search(layer)
        if m:
            return C.parse_color(m.group(0)), m.start(), m.end()
    for m in _SHADOW_WORD.finditer(layer):
        w = m.group(0).lower()
        if w in C.NAMED:
            return C.parse_color(w), m.start(), m.end()
    return None


def extract_shadow_lengths(layer, span=None):
    s = layer[:span[0]] + " " + layer[span[1]:] if span else layer
    out = []
    for m in _SHADOW_LEN.finditer(s):
        v = pf(m.group(1))
        out.append(v * 16 if m.group(2) in ("rem", "em") else v)
    return out


def _hex(c):
    return "#%02x%02x%02x" % tuple(int(round(max(0, min(255, x)))) for x in c[:3])


def scan_glow(content):
    """css_scan.rs#scan_css_text_for_glow -> [(index, snippet)] (file engines: dark page read from the text)."""
    props = MC.custom_props(content)
    dark = css_text_has_dark_root_bg(content, props)
    out = []
    for m in _SHADOW_DECL.finditer(content):
        if not _starts_property_token(content, m.start(1)):
            continue
        prop = m.group(1).lower()
        value = MC.resolve_var_refs(jtrim(m.group(2)), props)
        for layer in MC.split_commas_outside_parens(value):
            info = find_shadow_color(layer)
            if not info or info[0] is None:
                continue
            col = info[0]
            if _spread(col) < 30:
                continue
            vals = extract_shadow_lengths(layer, (info[1], info[2]))
            if len(vals) < 3 or vals[2] <= 4:
                continue
            blur, spread = vals[2], (vals[3] if len(vals) > 3 else 0.0)
            if blur / 2 + spread <= 0 or blur * col[3] < 3.0:     # rules.rs#glow_is_perceptible (no layout)
                continue
            zero = vals[0] == 0 and vals[1] == 0
            if not zero and not dark:
                continue
            out.append((m.start(), ("Zero-offset %s glow (%s)" if zero else "Colored %s glow (%s) on dark page")
                        % (prop, _hex(col))))
            break
    return out


_HALO_DECL = R(r"(?i:background)(?:-(?i:image))?" + WS + r"*:" + WS + r"*([^;{}]+)")
_URL_FN = R(r"(?i:url)" + WS + r"*\(")
_RADIAL_GRAD = R(r"((?i:repeating)-)?(?i:radial)-(?i:gradient)\(")
_HALO_COLOR_TOKEN = R(r"(?:(?i:rgb)[aA]?|(?i:hsl)[aA]?|(?i:oklch)|(?i:oklab)|(?i:lab)|(?i:lch)|(?i:hwb)|(?i:color-mix))"
                      r"\([^)]*(?:\([^)]*\))?[^)]*\)|#[0-9a-fA-F]{3,8}\b|\b(?i:transparent)\b")
_PX_STOP = R(r"(-?[0-9.]+)px\b")


def scan_radial_halo(content):
    """css_scan.rs#scan_css_text_for_radial_halo -> [(index, snippet)]."""
    props = MC.custom_props(content)
    if not css_text_has_dark_root_bg(content, props):
        return []
    out, seen = [], []
    for m in _HALO_DECL.finditer(content):
        if not _starts_property_token(content, m.start()):
            continue
        value = MC.resolve_var_refs(jtrim(m.group(1)), props)
        if _URL_FN.search(value):
            continue
        for g in _RADIAL_GRAD.finditer(value):
            if g.group(1):
                continue
            open_ = value.find("(", g.start())
            depth, end = 0, None
            for k in range(open_, len(value)):
                if value[k] == "(":
                    depth += 1
                elif value[k] == ")":
                    depth -= 1
                    if depth == 0:
                        end = k
                        break
            if end is None:
                break
            args = [jtrim(a) for a in MC.split_commas_outside_parens(value[open_ + 1:end])]
            if len(args) < 2:
                continue
            stops = [a for a in args if _HALO_COLOR_TOKEN.search(a)]
            if len(stops) < 2:
                continue
            if any(pm and abs(pf(pm.group(1))) <= 24 for pm in (_PX_STOP.search(s) for s in stops)):
                continue
            first = _HALO_COLOR_TOKEN.search(stops[0]).group(0)
            last = _HALO_COLOR_TOKEN.search(stops[-1]).group(0)
            lc = (0, 0, 0, 0.0) if last.lower() == "transparent" else C.parse_color(last)
            if lc is None or lc[3] > 0.05:
                continue
            fc = None if first.lower() == "transparent" else C.parse_color(first)
            if fc is None or fc[3] < 0.7 or _spread(fc) < 24:
                continue
            snip = "radial-gradient halo (%s → transparent) on dark page" % _hex(fc)
            if snip in seen:
                continue
            seen.append(snip)
            out.append((m.start(), snip))
    return out


# ════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# Page analyzers (regex_matchers.rs REGEX_ANALYZERS)
# ════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
_SPACING_PX = R(r"(?i:padding|margin)(?:-(?i:top|right|bottom|left))?" + WS + r"*:" + WS + r"*([0-9]+)(?i:px)")
_SPACING_REM = R(r"(?i:padding|margin)(?:-(?i:top|right|bottom|left))?" + WS + r"*:" + WS + r"*([0-9.]+)(?i:rem)")
_GAP_PX = R(r"(?i:gap)" + WS + r"*:" + WS + r"*([0-9]+)(?i:px)")
_TW_SPACING = R(r"\b(?:p|px|py|pt|pb|pl|pr|m|mx|my|mt|mb|ml|mr|gap)-([0-9]+)\b")


def _js_round(x):
    import math
    return math.floor(x + 0.5)


def analyze_monotonous_spacing(content):
    vals = []
    for m in _SPACING_PX.finditer(content):
        v = float(m.group(1))
        if 0 < v < 200:
            vals.append(v)
    for m in _SPACING_REM.finditer(content):
        v = _js_round(pf(m.group(1)) * 16)
        if 0 < v < 200:
            vals.append(v)
    vals += [float(m.group(1)) for m in _GAP_PX.finditer(content)]
    vals += [float(m.group(1)) * 4 for m in _TW_SPACING.finditer(content)]
    rounded = [_js_round(v / 4) * 4 for v in vals if v == v]
    if len(rounded) < 10:
        return []
    counts = {}
    for v in rounded:
        counts[v] = counts.get(v, 0) + 1
    mx = max(counts.values())
    pct = mx / len(rounded)
    if pct <= 0.6 or len({v for v in rounded if v > 0}) > 3:
        return []
    dom = next(k for k, c in counts.items() if c == mx)
    return ["~%spx used %d/%d times (%s%%)" % (num_str(dom), mx, len(rounded), num_str(_js_round(pct * 100)))]


def should_run_page_analyzers(content, ext):
    """detect_text.rs#should_run_page_analyzers (page.rs#is_full_page)."""
    stripped = _HTML_COMMENT.sub("", content)
    full = re.search(r"<!(?i:doctype)" + WS + r"|<(?i:html)[%s>]|<(?i:head)[%s>]" % (WS_CHARS, WS_CHARS), stripped, A)
    return bool(full) and (ext == "" or ext in PAGE_ANALYZER_EXTS)


def page_analyzers(content):
    out = [("monotonous-spacing", s, 0) for s in analyze_monotonous_spacing(content)]
    out += [("em-dash-overuse", s, 0) for s in MC.analyze_em_dash(content)]
    out += [("marketing-buzzword", s, 0) for s in MC.analyze_buzzwords(content)]
    out += [("aphoristic-cadence", s, 0) for s in MC.analyze_aphorisms(content)]
    g = scan_glow(content)
    if g:
        out.append(("dark-glow", g[0][1], line_of_offset(content, g[0][0])))
    h = scan_radial_halo(content)
    if h:
        out.append(("radial-halo", h[0][1], line_of_offset(content, h[0][0])))
    out += [("marquee", s, 0) for s, _ in MC.scan_marquee(content)]
    return out


# ════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# detect_text
# ════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
def detect_text(content, path):
    """detect_text.rs#detect_text (without design-system findings and inline ignores) -> [(rule, snippet, line)]."""
    ext = ext_of(path)
    if ext in JS_SOURCE_EXTS:
        stripped = strip_js_comments(content, ext in (".js", ".jsx", ".tsx"))
    else:
        stripped = blank_comments_for_matchers(content, ext)
    source = strip_css_in_js_comments(stripped, ext)
    lines = source.split("\n")
    css_like = ext in CSS_LIKE_EXTS
    sass = str(path).lower().endswith(".sass")
    sheet = FileSheet(content, source, ext)
    findings = run_regex_matchers(lines, path, 0, css_like, sheet, sass)
    if css_like:
        findings += [("side-tab", s, ln) for s, ln in scan_inset_stripe_css(content, 0, sheet)]
        findings += pseudo_stripe_findings(content, 0, sheet)
    gi = scan_grid_background(source)
    if gi is not None:
        findings.append(("codex-grid-background", "two-axis grid-line gradient background", line_of_offset(source, gi)))
    for block, start_line in extract_style_blocks(content, ext):
        bc = blank_css_line_comments(strip_css_comments(block))
        findings += run_regex_matchers(bc.split("\n"), path, start_line - 1, True, sheet, False)
        findings += [("side-tab", s, ln) for s, ln in scan_inset_stripe_css(bc, start_line - 2, sheet)]
        findings += pseudo_stripe_findings(bc, start_line - 2, sheet)
    for block, start_line in extract_css_in_js(source, ext):
        bc = strip_css_comments(block)
        findings += run_regex_matchers(bc.split("\n"), path, start_line - 1, True, sheet, False)
        findings += [("side-tab", s, ln) for s, ln in scan_inset_stripe_css(bc, start_line - 1, sheet)]
        findings += pseudo_stripe_findings(bc, start_line - 1, sheet)
    deduped = []
    for f in findings:     # same rule + snippet within 2 lines
        if not any(d[0] == f[0] and d[1] == f[1] and abs(d[2] - f[2]) <= 2 for d in deduped):
            deduped.append(f)
    if should_run_page_analyzers(content, ext):
        deduped += page_analyzers(content)
    return deduped


def scan(ctx):
    return detect_text(ctx.text, str(ctx.path))
