"""rules_layout.py — static layout / border / box rules, ported from impeccable's static HTML engine (Apache-2.0).

Upstream: impeccable crates (Apache-2.0) at pin 5bf0a069dc85; upstream function per rule in PORT_MAP.md and the comments.
Rules: side-tab, border-accent-on-rounded, nested-cards, icon-tile-stack, gpt-thin-border-wide-shadow,
cramped-padding (static flush form), clipped-overflow-container, shape-assembled-illustration, broken-image,
monotonous-spacing, design-system-radius.

Deviations kept deliberately small: lengths go through css.length_px (upstream parseFloat()s border widths);
`currentcolor` borders read as neutral (upstream's static default border colour is black).
"""
import re

from . import color as C
from . import css as CSS

SIDES = ("top", "right", "bottom", "left")
SIDE_NAMES = ("Top", "Right", "Bottom", "Left")
SIDE_ACCENT_MIN_RADIUS_PX = 4.0          # rules.rs SIDE_ACCENT_MIN_RADIUS_PX
NOMINAL_CARD_WIDTH_PX = 1000.0
CORNER_PROPS = ("border-top-left-radius", "border-top-right-radius", "border-bottom-right-radius",
                "border-bottom-left-radius")
BORDER_SAFE_TAGS = {"blockquote", "nav", "a", "input", "textarea", "select", "pre", "code", "span", "th", "td", "tr",
                    "li", "button", "hr", "html", "head", "body", "script", "style", "link", "meta", "title", "br",
                    "img", "svg", "path", "circle", "rect", "line", "polyline", "polygon", "g", "defs", "use"}
SAFE_TAGS = BORDER_SAFE_TAGS | {"label"}
HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


# ---------------------------------------------------------------------------------------------------------------------
# shared helpers
def _ignored(node, rule_id):
    """ignores.ignored(node, rule) when that module provides it (data-impeccable-ignore); else never."""
    try:
        from . import ignores
    except ImportError:
        return False
    fn = getattr(ignores, "ignored", None)
    return bool(fn(node, rule_id)) if fn else False


def _st(node):
    return node.style or {}


def _font(node):
    return _st(node).get("__font_px__", CSS.DEFAULT_FONT_PX)


def js_num(v):
    """JS Number -> string: 4 not 4.0."""
    if v is None:
        return "null"
    if float(v).is_integer():
        return str(int(v))
    return ("%.6f" % v).rstrip("0").rstrip(".")


def js_round(v):
    import math
    return math.floor(v + 0.5)


def parse_float(v):
    """JS parseFloat."""
    m = re.match(r"^\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?)", str(v or ""), re.I)
    return float(m.group(1)) if m else float("nan")


def pf0(v):
    f = parse_float(v)
    return 0.0 if f != f or f == 0 else f


def _len(node, prop, pct_base=None):
    """A declared length in px (0 when unset or unknown). css.length_px with an em base of the element's font."""
    v = _st(node).get(prop)
    if v is None or v == "":
        return 0.0
    if v.strip().lower() in ("thin", "medium", "thick"):
        return 0.0          # upstream's static cascade only keeps numeric border widths
    px = CSS.length_px(v, _font(node), CSS.DEFAULT_FONT_PX, pct_base)
    return px if px is not None else pf0(v)


def _decl_px(node, prop):
    """Declared px length or None (width/height of a box; `auto`, % -> None)."""
    v = (_st(node).get(prop) or "").strip()
    if not v:
        return None
    return CSS.length_px(v, _font(node))


def own_text_longer_than(node, n):
    return any(isinstance(c, str) and len(c.strip()) > n for c in node.children)


def class_selector(node):
    """adapters.rs class_selector: tag or tag.cls1.cls2."""
    return node.tag + ("." + ".".join(node.classes) if node.classes else "")


def closest(node, pred):
    for n in [node] + list(node.ancestors()):
        if pred(n):
            return n
    return None


def ident_words(s):
    """measures.rs ident_words: alnum runs lowercased + camelCase pieces."""
    out = []
    for run in re.split(r"[^A-Za-z0-9]+", s or ""):
        if not run:
            continue
        out.append(run.lower())
        start = 0
        for i in range(1, len(run)):
            if run[i].isupper() and run[i - 1].islower():
                out.append(run[start:i].lower())
                start = i
        if start > 0:
            out.append(run[start:].lower())
    return out


def ident_names_any(s, words, pairs=()):
    w = ident_words(s)
    return any(t in words for t in w) or any((w[i], w[i + 1]) in pairs for i in range(len(w) - 1))


def color_alpha(v):
    """css_measures.rs css_color_alpha (transparent -> 0, unparseable -> 1)."""
    if is_transparent(v):
        return 0.0
    c = C.parse_color(v)
    return c[3] if c else 1.0


def is_transparent(v):
    """css_measures.rs css_color_is_transparent."""
    if v is None:
        return True
    s = v.strip().lower()
    if not s or s in ("transparent", "rgba(0, 0, 0, 0)"):
        return True
    c = C.parse_color(s)
    return c is not None and c[3] <= 0.05


def nearly_match(a, b):
    ca, cb = C.parse_color(a or ""), C.parse_color(b or "")
    if not ca or not cb:
        return False
    return abs(ca[3] - cb[3]) <= 0.03 and max(abs(ca[i] - cb[i]) for i in range(3)) <= 3


def _channel(tok, full):
    m = re.match(r"^\s*([-+]?[\d.]+)(%?)", tok)
    if not m:
        return None
    v = float(m.group(1))
    return v / 100.0 * full if m.group(2) else v


def is_neutral_color(v):
    """color.rs is_neutral_color: grey borders do not count as accents."""
    if v is None:
        return True
    s = v.strip().lower()
    if not s or s in ("transparent", "currentcolor"):
        return True
    m = re.match(r"^(oklch|lch|oklab|lab|hsla?|hwb)\((.*)\)$", s)
    if m:
        parts = [p for p in re.split(r"[\s,/]+", m.group(2).strip()) if p]
        try:
            fn = m.group(1)
            if fn == "oklch":
                return _channel(parts[1], 0.4) < 0.02
            if fn == "lch":
                return _channel(parts[1], 150.0) < 3
            if fn == "oklab":
                return (_channel(parts[1], 0.4) ** 2 + _channel(parts[2], 0.4) ** 2) ** 0.5 < 0.02
            if fn == "lab":
                return (_channel(parts[1], 125.0) ** 2 + _channel(parts[2], 125.0) ** 2) ** 0.5 < 3
            if fn.startswith("hsl"):
                return float(parts[1].rstrip("%")) < 10
            if fn == "hwb":
                w, b = float(parts[1].rstrip("%")), float(parts[2].rstrip("%"))
                return 1 - min(100.0, w + b) / 100.0 < 0.1
        except (IndexError, TypeError, ValueError):
            return False
    c = C.parse_color(s)
    if c is None:
        return False            # an unresolved var() counts as coloured upstream
    return max(c[:3]) - min(c[:3]) < 30


# --- shadows: css_measures.rs parse_shadow_layers -------------------------------------------------------------------
def shadow_layers(value):
    out = []
    v = (value or "").strip()
    if not v or v == "none":
        return out
    for layer in CSS.split_top(v, ","):
        m = C.COLOR_TOKEN.search(layer)
        col = C.parse_color(m.group(0)) if m else None
        alpha = 1.0
        if m:
            alpha = 0.0 if m.group(0).lower() == "transparent" else (col[3] if col else 1.0)
        rest = (layer[:m.start()] + " " + layer[m.end():]) if m else layer
        inset = bool(re.search(r"\binset\b", rest, re.I))
        rest = re.sub(r"\b[a-zA-Z]+\b", " ", rest)
        nums = [float(x) for x in re.findall(r"-?\d*\.?\d+", rest)]
        if len(nums) < 2:
            continue
        out.append({"x": nums[0], "y": nums[1], "blur": nums[2] if len(nums) > 2 else 0.0,
                    "spread": nums[3] if len(nums) > 3 else 0.0, "inset": inset, "alpha": alpha, "color": col})
    return out


# --- radius / corners: background.rs + rules.rs ----------------------------------------------------------------------
def _radius_token(tok, width, em):
    t = tok.strip().lower()
    m = re.match(r"^([-+]?(?:\d+\.?\d*|\.\d+))(px|%|em|rem)?$", t)
    if not m:
        return None
    n = float(m.group(1))
    u = m.group(2) or ""
    if u == "px":
        return n
    if u == "%":
        return n / 100.0 * width if width > 0 else n
    if u == "em":
        return n * em
    if u == "rem":
        return n * 16.0
    return 0.0 if n == 0 else None


def corner_px(value, width, em):
    """One corner longhand: horizontal radius, square when the vertical radius is 0."""
    toks = (value or "").split()
    if not toks:
        return None
    h = _radius_token(toks[0], width, em)
    if h is None:
        return None
    if len(toks) > 1:
        v = _radius_token(toks[1], width, em)
        if v is None:
            return None
        if v <= 0:
            return 0.0
    return h


def radius_scalar_px(node):
    """resolve_border_radius_scalar_px: first horizontal token of border-radius, em/rem aware."""
    st = _st(node)
    v = st.get("border-radius")
    width = _decl_px(node, "width") or 0.0
    if v:
        first = v.split("/")[0].split()
        if first:
            px = _radius_token(first[0], width, _font(node))
            if px is not None:
                return px
        return pf0(v)
    tl = st.get("border-top-left-radius")
    if tl:
        px = corner_px(tl, width, _font(node))
        return px or 0.0
    return 0.0


def radius_px_loose(node, width=None):
    """resolve_border_radius_px: parseFloat of border-radius (% of width)."""
    v = _st(node).get("border-radius") or _st(node).get("border-top-left-radius") or ""
    n = parse_float(v)
    if n != n:
        return 0.0
    w = width if width is not None else (_decl_px(node, "width") or 0.0)
    if re.match(r"^\s*[-+]?[\d.]+%", v) and w > 0:
        return n / 100.0 * w
    return n


TW_ROUNDED = re.compile(r"^rounded(?:-(tl|tr|br|bl|ss|se|ee|es|t|r|b|l|s|e))?(?:-([a-z0-9-]+|\[[^\]]*\]|\([^)]*\)))?$")
TW_SIZES = {None: 4.0, "sm": 4.0, "none": 0.0, "xs": 2.0, "md": 6.0, "lg": 8.0, "xl": 12.0, "2xl": 16.0, "3xl": 24.0,
            "4xl": 32.0, "full": 9999.0}


def tailwind_corners(class_attr):
    """rules.rs tailwind_declared_corners -> (declared, [TL,TR,BR,BL] with None = unknown)."""
    base, variants = [], []
    for raw in re.split(r"[\s\"'`{}]+", class_attr or ""):
        tok = raw.strip("!")
        if not tok:
            continue
        br = tok.find("[")
        head = tok if br < 0 else tok[:br]
        i = head.rfind(":")
        variant = i >= 0
        cls = tok[i + 1:].lstrip("!") if variant else tok
        m = TW_ROUNDED.match(cls)
        if not m:
            continue
        side = m.group(1)
        if side is None:
            group, corners = 0, (0, 1, 2, 3)
        elif side == "t":
            group, corners = 1, (0, 1)
        elif side in ("r", "e"):
            group, corners = 1, (1, 2)
        elif side == "b":
            group, corners = 1, (2, 3)
        elif side in ("l", "s"):
            group, corners = 1, (0, 3)
        elif side in ("tl", "ss"):
            group, corners = 2, (0,)
        elif side in ("tr", "se"):
            group, corners = 2, (1,)
        elif side in ("br", "ee"):
            group, corners = 2, (2,)
        else:
            group, corners = 2, (3,)
        size = m.group(2)
        if size in TW_SIZES:
            px = TW_SIZES[size]
        elif size and size.startswith("["):
            px = corner_px(size[1:-1].replace("_", " "), NOMINAL_CARD_WIDTH_PX, 16.0)
        else:
            px = None
        (variants if variant else base).append((group, corners, px))
    if not base and not variants:
        return False, [0.0] * 4
    cur = [0.0] * 4
    for _, corners, px in sorted(base, key=lambda e: e[0]):
        for i in corners:
            cur[i] = px
    for _, corners, px in variants:
        for i in corners:
            cur[i] = None if cur[i] is None or px is None else max(cur[i], px)
    return True, cur


def _box4(v):
    if len(v) == 1:
        return v * 4
    if len(v) == 2:
        return [v[0], v[1], v[0], v[1]]
    if len(v) == 3:
        return [v[0], v[1], v[2], v[1]]
    return v[:4]


def _shorthand_corners(value, width, em):
    """border-radius shorthand -> [TL,TR,BR,BL] (None if a token is unknown); `h / v` squares a corner whose v is 0."""
    halves = value.split("/")

    def half(h):
        toks = h.split()
        if not toks:
            return None
        vals = [_radius_token(t, width, em) for t in toks]
        if any(v is None for v in vals):
            return None
        return _box4(vals)
    hz = half(halves[0])
    if hz is None or len(halves) < 2:
        return hz
    vt = half(halves[1])
    if vt is None:
        return None
    return [0.0 if vt[i] <= 0 else hz[i] for i in range(4)]


def _corners_from_style(node):
    """background.rs resolve_border_radius_corners: longhands; a longhand still holding the whole (var-built)
    shorthand reads its own position of it; a trailing `/ v` part squares corners whose vertical radius is 0."""
    st = _st(node)
    width = _decl_px(node, "width") or 0.0
    short = st.get("border-radius")
    whole = _shorthand_corners(short, width, _font(node)) if short else None
    out = []
    for i, p in enumerate(CORNER_PROPS):
        v = st.get(p)
        if v is None or v == "":
            out.append(0.0)
            continue
        if short and (v == short or (whole is not None and "/" in short)) and whole is not None:
            out.append(whole[i])
            continue
        px = corner_px(v, width, _font(node))
        if px is None:
            return None
        out.append(px)
    return out


def side_accent_corners(ctx, node):
    """background.rs resolve_side_accent_corners -> [TL,TR,BR,BL] or None (unknown keeps the finding)."""
    raw = _st(node).get("__raw__") or {}
    if not any(k in raw for k in CORNER_PROPS + ("border-radius",)):
        declared, tw = tailwind_corners(node.get("class"))
        if declared:
            return None if any(c is None for c in tw) else tw
        if getattr(ctx, "unread_stylesheet", False):
            return None
    return _corners_from_style(node)


AWAY = {0: (3, 2), 1: (0, 3), 2: (0, 1), 3: (1, 2)}   # side -> the two corners it does not touch


def rounded_away(corners, i):
    """rules.rs is_rounded_away_from_side."""
    if corners is None:
        return True
    a, b = (corners[k] for k in AWAY[i])
    if a is None or b is None:
        return True
    return a >= SIDE_ACCENT_MIN_RADIUS_PX and b >= SIDE_ACCENT_MIN_RADIUS_PX


ACTIVE_CLASS = re.compile(r"(?:^|[\s_-])(?:active|current|selected)(?:$|[\s_-])", re.I)


def tab_context(node):
    """adapters.rs is_tab_context_element."""
    for n in [node] + list(node.ancestors()):
        if n.get("aria-selected") == "true" or (n.get("aria-current") is not None and n.get("aria-current") != "false"):
            return True
    for depth, n in enumerate([node] + list(node.ancestors())):
        if depth >= 6:
            break
        if ACTIVE_CLASS.search(n.get("class") or ""):
            return True
    return False


def status_context(node):
    """adapters.rs is_status_context_element."""
    return closest(node, lambda n: (n.get("role") or "") in ("status", "alert", "alertdialog", "log")
                   or (n.get("aria-live") or "") in ("polite", "assertive")) is not None


# --- border sides: core css._border_parts reads a var() token as the width (`border-left: 5px solid var(--c)`
# loses 5px); when a side's resolved width is not a length we re-read the winning shorthand ourselves.
def _winning_border_decl(ctx, node, side):
    best = None
    props = ("border", "border-" + side)
    for r in ctx.sheet.rules:
        for d_prop, d_val, imp in r.decls:
            if d_prop not in props:
                continue
            for sel in r.selectors:
                if CSS.PSEUDO_EL.search(sel) or CSS.STATE_PSEUDO.search(sel):
                    continue
                try:
                    if not CSS.matches(node, sel):
                        continue
                    spec = CSS.specificity(CSS.compiled(sel))
                except Exception:
                    continue
                key = (1 if imp else 0, spec, r.order)
                if best is None or key >= best[0]:
                    best = (key, d_val)
    for d_prop, d_val, imp in CSS.parse_decls(node.get("style") or ""):
        if d_prop in props:
            key = (1 if imp else 0, (1, 0, 0, 0), 10 ** 7)
            if best is None or key >= best[0]:
                best = (key, d_val)
    return best[1] if best else None


def border_side(ctx, node, i):
    """(width px, colour string, style) of one side, repairing var()-coloured shorthands."""
    st = _st(node)
    s = SIDES[i]
    wv = st.get("border-%s-width" % s)
    col = st.get("border-%s-color" % s)
    style = (st.get("border-%s-style" % s) or "").strip().lower()
    if wv and CSS.length_px(wv, _font(node)) is None and wv.strip().lower() not in ("thin", "medium", "thick") \
            and ctx is not None:
        decl = _winning_border_decl(ctx, node, s)
        if decl:
            w2, c2 = None, None
            for tok in CSS.split_top(CSS._resolve_vars(decl, st.get("__custom__") or {})):
                if tok.lower() in CSS.BORDER_STYLES:
                    style = tok.lower()
                elif CSS.length_px(tok, _font(node)) is not None and w2 is None:
                    w2 = tok
                elif C.parse_color(tok) is not None:
                    c2 = tok
            wv, col = w2 or "0", c2 or col
    w = 0.0
    if wv and wv.strip().lower() not in ("thin", "medium", "thick"):
        px = CSS.length_px(wv, _font(node))
        w = px if px is not None else pf0(wv)
    return w, col, style


# ---------------------------------------------------------------------------------------------------------------------
# side-tab / border-accent-on-rounded: rules.rs check_borders via adapters.rs check_element_borders
def check_borders(ctx, node):
    tag = node.tag
    st = _st(node)
    bg = C.parse_color(st.get("background-color") or "")
    span_badge = tag == "span" and bg is not None and bg[3] > 0.1
    if tag in BORDER_SAFE_TAGS and not span_badge:
        return []
    if not any((st.get("border-%s-width" % s) or "0").strip() not in ("0", "0px", "") for s in SIDES):
        return []
    sides = [border_side(ctx, node, i) for i in range(4)]
    widths = [x[0] for x in sides]
    if not any(w > 0 for w in widths):
        return []
    if status_context(node):
        return []
    colors = [x[1] for x in sides]
    radius = radius_scalar_px(node)
    corners = side_accent_corners(ctx, node)
    tab = None
    out = []
    for i in range(4):
        w = widths[i]
        if w < 1 or is_neutral_color(colors[i]):
            continue
        if sides[i][2] in ("none", "hidden"):
            continue
        max_other = max(widths[j] for j in range(4) if j != i)
        if not (w >= 2 and (max_other <= 1 or w >= max_other * 2)):
            continue
        sn = SIDES[i]
        if i in (1, 3):
            if span_badge or not rounded_away(corners, i):
                continue
            if radius > 0:
                out.append(("side-tab", "border-%s: %spx + border-radius: %spx" % (sn, js_num(w), js_num(radius))))
            elif w >= 3:
                out.append(("side-tab", "border-%s: %spx" % (sn, js_num(w))))
            elif corners is not None:
                far = min(corners[k] for k in AWAY[i])
                if far > 0:
                    out.append(("side-tab", "border-%s: %spx + border-radius: %spx" % (sn, js_num(w), js_num(far))))
        elif radius > 0 and w >= 2:
            out.append(("border-accent-on-rounded", "border-%s: %spx + border-radius: %spx"
                        % (sn, js_num(w), js_num(radius))))
        else:
            if tab is None:
                tab = tab_context(node)
            if not tab and 3 <= w <= 12 and rounded_away(corners, i):
                out.append(("side-tab", "border-%s: %spx" % (sn, js_num(w))))
    return out


def _border_hits(ctx):
    cache = getattr(ctx, "_layout_border_hits", None)
    if cache is None:
        cache = []
        for node in ctx.elements():
            for rid, snip in check_borders(ctx, node):
                if not _ignored(node, rid):
                    cache.append((rid, snip))
        ctx._layout_border_hits = cache
    return cache


# --- stripe child: adapters.rs check_element_stripe_child + rules.rs check_stripe_child -----------------------------
STRIPE_SKIP_TAGS = {"nav", "blockquote", "pre", "table", "button", "a", "select", "progress", "meter"}
STRIPE_SKIP_ROLES = {"progressbar", "slider", "scrollbar", "separator", "tablist"}
UNIT_PX = {"pt": 96 / 72, "pc": 16.0, "in": 96.0, "cm": 96 / 2.54, "mm": 96 / 25.4, "q": 96 / 101.6}


def _stripe_width(v):
    v = (v or "").strip().lower()
    m = re.match(r"^(-?[\d.]+)(px|rem|em|pt|pc|in|cm|mm|q)$", v)
    if not m:
        return None
    n = float(m.group(1))
    u = m.group(2)
    return n if u == "px" else n * 16.0 if u in ("rem", "em") else n * UNIT_PX[u]


def _hug(v):
    f = parse_float(v)
    return f == f and abs(f) <= 2


def _first_kw(v, allowed=None):
    for t in (v or "").lower().split():
        if not allowed or t in allowed:
            return t
    return None


def check_stripe_child(ctx, el):
    if el.tag not in ("div", "span"):
        return []
    host = el.parent
    if host is None or host.tag in ("body", "html", "#document") or host.tag in HEADINGS:
        return []
    if el.elements() or el.norm_text():
        return []
    if closest(el, lambda n: n.tag in STRIPE_SKIP_TAGS or (n.get("role") or "").strip() in STRIPE_SKIP_ROLES):
        return []
    if tab_context(el) or status_context(el):
        return []
    st, hs = _st(el), _st(host)
    width = _stripe_width(st.get("width")) or 0.0
    pos = (st.get("position") or "").lower()
    h = (st.get("height") or "").lower()
    auto_h = h in ("", "auto", "initial", "unset")
    if pos in ("absolute", "fixed"):
        if not (h == "100%" or (auto_h and _hug(st.get("top")) and _hug(st.get("bottom")))):
            return []
        edge = "left" if _hug(st.get("left")) else "right" if _hug(st.get("right")) else None
    else:
        if "flex" not in (hs.get("display") or ""):
            return []
        d = _first_kw(hs.get("flex-direction") or (hs.get("flex-flow") or ""),
                      ("row", "row-reverse", "column", "column-reverse")) or "row"
        if d.startswith("column"):
            return []
        a = _first_kw(st.get("align-self"))
        if not a or a == "auto":
            a = _first_kw(hs.get("align-items")) or ""
        if not (h == "100%" or (auto_h and a in ("", "stretch", "normal"))):
            return []
        sibs = host.elements()
        if len(sibs) < 2:
            return []
        rev = "reverse" in d
        edge = ("right" if rev else "left") if sibs[0] is el else ("left" if rev else "right") if sibs[-1] is el else None
    if edge is None:
        return []
    if not rounded_away(side_accent_corners(ctx, host), 3 if edge == "left" else 1):
        return []
    if not (2 <= width <= 12):
        return []
    bg = C.parse_color(st.get("background-color") or "")
    if bg is None or bg[3] <= 0.1 or max(bg[:3]) - min(bg[:3]) < 30:
        return []
    return [("side-tab", "%s — %spx stripe child (%s)" % (class_selector(el), js_num(js_round(width)), edge))]


# --- CSS-text stripe scans: css_scan.rs scan_css_text_for_pseudo_stripe / scan_css_text_for_inset_stripe -------------
RULE_BLOCK = re.compile(r"([^{};]+)\{([^{}]*)\}")
PSEUDO_SEL = re.compile(r"::?(?:before|after)\b", re.I)
PROSE_TAG = re.compile(r"\b(?:blockquote|pre|code|nav|hr)\b", re.I)
STATE_PSEUDO = re.compile(r":(?:hover|focus|focus-visible|focus-within|active|checked)\b", re.I)
STATE_PSEUDO_T = re.compile(r":(?:hover|focus|focus-visible|focus-within|active|checked|target)\b", re.I)
ARIA_SEL_TRUE = re.compile(r"""\[aria-selected\s*[*^$|~]?=\s*["']?true""", re.I)
ZERO = re.compile(r"^-?0(?:px|%|rem|em)?$")
FULL_PCT = re.compile(r"^100(?:\.0*)?%$")
NO_PAINT = re.compile(r"^(?:none|transparent|inherit|initial|unset|currentcolor)$", re.I)
STRIPE_COLOR = re.compile(r"(?:rgba?|hsla?|oklch|oklab|lab|lch|hwb)\([^)]*\)|#[0-9a-fA-F]{3,8}\b", re.I)


def _decl_block(body):
    d = {}
    for part in body.split(";"):
        i = part.find(":")
        if i <= 0:
            continue
        k = part[:i].strip().lower()
        v = re.sub(r"\s*!\s*important\s*$", "", part[i + 1:], flags=re.I).strip()
        if k and v:
            d[k] = v
    return d


def _custom_props(text):
    out = {}
    for m in re.finditer(r"(--[A-Za-z0-9_-]+)\s*:\s*([^;}]+)", text):
        out.setdefault(m.group(1), m.group(2).strip())
    return out


def _resolve(v, props, depth=0):
    if "var(" not in (v or "") or depth > 8:
        return v or ""

    def rep(m):
        name, _, fb = m.group(1).partition(",")
        name = name.strip()
        if name in props:
            return _resolve(props[name], props, depth + 1)
        return fb.strip() if fb else m.group(0)
    return re.sub(r"var\(((?:[^()]|\([^()]*\))*)\)", rep, v)


def _css_len(v):
    m = re.match(r"^(-?[0-9.]+)(px|rem|em)$", (v or "").strip(), re.I)
    if not m:
        return None
    n = float(m.group(1))
    return n if m.group(2).lower() == "px" else n * 16.0


def _has_tag(sel, tags):
    for m in re.finditer(r"(?:^|[\s>+~,(])([\w-]+)", sel):
        if m.group(1).lower() in tags:
            return True
    return False


def _state_word(sel, prefixed):
    for m in re.finditer(r"(?:^|[\s._\[-])([\w-]+)", sel):
        run = m.group(1)
        word = re.match(r"\w*", run).group(0).lower()
        if word in ("active", "current", "selected"):
            return True
        if prefixed and run.lower().startswith(("btn", "button", "link")):
            return True
    return False


def _aria_current(sel):
    for m in re.finditer(r"\[aria-current", sel, re.I):
        if not re.match(r"""\s*[*^$|~]?=\s*["']?false""", sel[m.end():], re.I):
            return True
    return False


def scan_pseudo_stripe(text):
    content = re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=re.S)
    props = _custom_props(content)
    out, seen = [], set()
    for m in RULE_BLOCK.finditer(content):
        sel = m.group(1).strip()
        if not PSEUDO_SEL.search(sel) or PROSE_TAG.search(sel):
            continue
        d = _decl_block(m.group(2))
        if d.get("position") not in ("absolute", "fixed"):
            continue
        wv = _resolve(d.get("width") or d.get("inline-size") or "", props).strip()
        hv = _resolve(d.get("height") or d.get("block-size") or "", props).strip()
        W, H = _css_len(wv), _css_len(hv)
        vert = W is not None and 3 <= W <= 12
        horiz = (H is not None and 3 <= H <= 12 and not _has_tag(sel, {"a", "button", "summary", "tr", "td", "th", "table", "li"})
                 and not ARIA_SEL_TRUE.search(sel) and not _aria_current(sel) and not _state_word(sel, True)
                 and not STATE_PSEUDO.search(sel))
        if not vert and not horiz:
            continue
        top, right, bottom, left = (d.get(k) for k in SIDES)
        if d.get("inset"):
            box = _box4(d["inset"].split())
            top = top if top is not None else box[0]
            right = right if right is not None else box[1]
            bottom = bottom if bottom is not None else box[2]
            left = left if left is not None else box[3]
        left = left if left is not None else d.get("inset-inline-start")
        right = right if right is not None else d.get("inset-inline-end")
        z = lambda v: v is not None and bool(ZERO.match(v.strip()))
        edge = thick = None
        if vert:
            tp, bp = _css_len(_resolve(top or "", props)), _css_len(_resolve(bottom or "", props))
            full = (z(top) and z(bottom)) or FULL_PCT.match(hv) or (tp is not None and bp is not None and 0 <= tp <= 20 and 0 <= bp <= 20)
            if full:
                edge = "left" if z(left) else "right" if z(right) else None
                thick = W
        if edge is None and horiz:
            if (z(left) and z(right)) or FULL_PCT.match(wv):
                edge = "top" if z(top) else "bottom" if z(bottom) else None
                thick = H
        if edge is None:
            continue
        bg = _resolve(d.get("background-color") or d.get("background") or "", props).strip()
        if not bg or NO_PAINT.match(bg):
            continue
        tok = STRIPE_COLOR.search(bg)
        c = C.parse_color(tok.group(0) if tok else bg)
        if c is not None:
            if c[3] < 0.1 or max(c[:3]) - min(c[:3]) < 30:
                continue
        elif bg.lower() in ("white", "black", "gray", "grey", "silver"):
            continue
        elif re.search(r"url\(", bg, re.I) and not any(C.parse_color(t) or "var(" in t for t in
                                                       re.split(r"[\s,/]+", re.sub(r"url\([^)]*\)", " ", bg)) if t):
            continue
        if "&" not in sel:
            if sel in seen:
                continue
            seen.add(sel)
        out.append({"rule": "side-tab", "selector": sel, "side": SIDES.index(edge),
                    "snippet": "%s — absolute %spx pseudo-element stripe (%s: 0)" % (sel, js_num(thick), edge)})
    return out


def scan_inset_stripe(text):
    props = _custom_props(text)
    out, seen = [], set()
    for m in RULE_BLOCK.finditer(text):
        sel = m.group(1).strip()
        if STATE_PSEUDO_T.search(sel) or ARIA_SEL_TRUE.search(sel) or _aria_current(sel) or _state_word(sel, False):
            continue
        if _has_tag(sel, {"button", "hr", "tr", "td", "th", "table", "blockquote", "pre", "code"}):
            continue
        d = _decl_block(m.group(2))
        shadow = d.get("box-shadow")
        if not shadow or not re.search(r"\binset\b", shadow, re.I):
            continue
        w = _css_len(_resolve(d.get("width") or d.get("inline-size") or "", props))
        if w is not None and w <= 40:
            continue
        for L in shadow_layers(_resolve(shadow, props)):
            if not L["inset"] or L["color"] is None:
                continue
            c = L["color"]
            if c[3] < 0.1 or max(c[:3]) - min(c[:3]) < 30 or L["blur"] or L["spread"]:
                continue
            ax, ay = abs(L["x"]), abs(L["y"])
            if not ((3 <= ax <= 12 and ay == 0) or (3 <= ay <= 12 and ax == 0)):
                continue
            if sel in seen:
                break
            seen.add(sel)
            edge = ("left" if L["x"] > 0 else "right") if ay == 0 else ("top" if L["y"] > 0 else "bottom")
            out.append({"rule": "side-tab", "selector": sel, "side": SIDES.index(edge),
                        "snippet": "%s — inset box-shadow %spx stripe (%s)" % (sel, js_num(ax if ay == 0 else ay), edge)})
            break
    return out


PSEUDO_STRIP = re.compile(r"::?[a-zA-Z-]+(\([^)]*\))?")


def _host_rule_corners(ctx, host_sel):
    """CssHostIndex.side_stripe_on_rounded_host (approx.): radius declarations of rules naming the host selector."""
    norm = " ".join(host_sel.split())
    corners, declared = [0.0] * 4, False
    for r in ctx.sheet.rules:
        if not any(" ".join(s.split()) == norm for s in r.selectors):
            continue
        for prop, val, _ in r.decls:
            for lp, lv in CSS.expand(prop, val):
                if lp in CORNER_PROPS:
                    corners[CORNER_PROPS.index(lp)] = corner_px(lv, NOMINAL_CARD_WIDTH_PX, 16.0)
                    declared = True
    return corners if declared else [0.0] * 4


def stripe_scan_hits(ctx):
    """engine.rs html-pattern gate: a CSS-text stripe reports only on a host rounded away from it."""
    hits = []
    for f in scan_pseudo_stripe(ctx.css_text) + scan_inset_stripe(ctx.css_text):
        host_sel = PSEUDO_STRIP.sub("", f["selector"]).strip()
        hosts = []
        if host_sel and ctx.doc is not None:
            try:
                hosts = [n for n in ctx.doc.iter() if CSS.matches(n, host_sel)]
            except Exception:
                hosts = []
        if hosts and all(_ignored(n, "side-tab") for n in hosts):
            continue
        if hosts:
            ok = any(rounded_away(side_accent_corners(ctx, n), f["side"]) for n in hosts)
        else:
            corners = _host_rule_corners(ctx, host_sel)
            ok = rounded_away(None if any(c is None for c in corners) else corners, f["side"])
        if ok:
            hits.append(("side-tab", f["snippet"]))
    return hits


def rule_side_tab(ctx):
    hits = [h for h in _border_hits(ctx) if h[0] == "side-tab"]
    for el in ctx.elements():
        for h in check_stripe_child(ctx, el):
            if not _ignored(el, "side-tab"):
                hits.append(h)
    if ctx.full_page:
        hits.extend(stripe_scan_hits(ctx))
    return hits


def rule_border_accent(ctx):
    return [h for h in _border_hits(ctx) if h[0] == "border-accent-on-rounded"]


# ---------------------------------------------------------------------------------------------------------------------
# nested-cards: page.rs check_page_layout / is_card_like
SHADOW_CLASS = re.compile(r"\bshadow(?:-sm|-md|-lg|-xl|-2xl)?\b")
BORDER_CLASS_TOKEN = re.compile(r"^border(?:-[0-9]+|-px|-\[[0-9.]+(?:px|rem|em)\])?$")
ROUNDED_CLASS = re.compile(r"\brounded(?:-sm|-md|-lg|-xl|-2xl|-full)?\b")
BG_CLASS = re.compile(r"\bbg-(?:white|gray-[0-9]+|slate-[0-9]+)\b")
POSITIONED_CLASS = re.compile(r"\b(?:absolute|fixed)\b")
POSITIONED_STYLE = re.compile(r"position\s*:\s*(?:absolute|fixed)", re.I)
OVERLAY_CLASS = re.compile(r"\b(?:dropdown|popover|tooltip|menu|modal|dialog)\b", re.I)
CAPTION_MAX_CHARS = 140
MEDIA_WORDS = {"play", "pause", "stop", "mute", "unmute", "volume", "sound", "skip", "forward", "fast", "rewind",
               "replay", "back", "previous", "prev", "next", "seek", "speed", "playback", "fullscreen", "full", "exit",
               "captions", "subtitles"}
MONO_TAGS = {"pre", "code", "samp", "kbd", "output"}
INLINE_TAGS = {"a", "abbr", "b", "br", "code", "em", "i", "kbd", "mark", "s", "samp", "small", "span", "strong",
               "sub", "sup"}


def _bg_decl_not_transparent(style_attr):
    for m in re.finditer(r"background(?:-color)?\s*:(\s*)", style_attr, re.I):
        if m.group(1) or not style_attr[m.end():m.end() + 11].lower() == "transparent":
            return True
    return False


def is_card_like(node):
    """page.rs is_card_like (static: Tailwind border class, computed/declared shadow, radius, bg)."""
    if node.tag in SAFE_TAGS or node.tag in ("input", "select", "textarea", "img", "video", "canvas", "picture"):
        return False
    st = _st(node)
    sa = node.get("style") or ""
    cls = node.get("class") or ""
    bs = (st.get("box-shadow") or "").strip()
    has_shadow = (bs and bs != "none") or bool(SHADOW_CLASS.search(cls)) or bool(re.search("box-shadow", sa, re.I))
    has_border = any(BORDER_CLASS_TOKEN.match(t.rsplit(":", 1)[-1].lstrip("!")) for t in cls.split())
    if not has_shadow and not has_border:
        return False
    has_radius = radius_px_loose(node) > 0 or bool(ROUNDED_CLASS.search(cls)) or bool(re.search("border-radius", sa, re.I))
    has_bg = bool(BG_CLASS.search(cls)) or _bg_decl_not_transparent(sa)
    return has_radius or has_bg


def _control_of(n):
    for tok in (n.get("role") or "").lower().split():
        if tok == "slider":
            return "seek"
        if tok == "button":
            return "button"
        if tok in ("switch", "checkbox", "radio", "combobox", "tab", "textbox", "searchbox", "spinbutton"):
            return "field"
    if n.tag == "button":
        return "button"
    if n.tag in ("select", "textarea"):
        return "field"
    if n.tag == "input":
        t = (n.get("type") or "").strip().lower()
        return None if t == "hidden" else "seek" if t == "range" else "button" if t in ("button", "submit", "reset", "image") else "field"
    return None


def _first_word(name):
    w = [x for x in re.split(r"\W+", (name or "").strip().lower()) if x]
    return w[0] if w else ""


def _vis(text):
    return len("".join((text or "").split()))


def _rendered(n):
    return not CSS.is_hidden(n)


def frames_embedded_content(el, outer):
    """page.rs frames_embedded_content (r4-p17): a media player, a captioned figure, or an output block."""
    nodes = [el] + list(el.iter())
    controls = []
    for n in nodes:
        k = _control_of(n)
        if k:
            controls.append((n, k, n.get("aria-label") or n.get("title") or n.text()))
    media = any(n.tag in ("audio", "video") and "controls" in n.attrs and _rendered(n) for n in nodes)
    custom = any(k == "button" and _first_word(nm) in ("play", "pause") for _, k, nm in controls) and (
        any(k == "seek" for _, k, _ in controls) or any(n.tag == "progress" for n in nodes))
    if (media or custom) and all(k == "seek" or (k == "button" and (not _first_word(nm) or _first_word(nm) in MEDIA_WORDS))
                                 for _, k, nm in controls):
        outer_ctrls = [c for c, _, _ in controls if not any(o is not c and c in list(o.iter()) for o, _, _ in controls)]
        if _vis(el.text()) - sum(_vis(c.text()) for c in outer_ctrls) <= CAPTION_MAX_CHARS:
            return True
    if el.tag == "figure" or any(n.tag == "figcaption" for n in nodes[1:]):
        total = _vis(el.text())
        for fig in (n for n in nodes if n.tag in ("svg", "canvas")):
            cap = total - _vis(fig.text())
            inside = set(map(id, fig.iter()))
            if 0 < cap <= CAPTION_MAX_CHARS and all(id(c) in inside for c, _, _ in controls):
                return True
    chrome = all(k == "button" and (_first_word(nm) in ("copy", "copied") or _vis(c.text()) == 0) for c, k, nm in controls)
    return chrome and is_output_block(el, outer)


def _mono(n):
    return "mono" in (_st(n).get("font-family") or "").lower()


def _mono_at(n, el):
    for a in [n] + list(n.ancestors()):
        if a.tag in MONO_TAGS or _mono(a):
            return True
        if a is el:
            break
    return False


def is_output_block(el, outer):
    if _mono(outer):
        return False
    nodes = [el] + list(el.iter())
    if len(nodes) > 2000:
        return False
    text, mono, run = {}, {}, {}
    for n in nodes:
        own = _vis("".join(c for c in n.children if isinstance(c, str)))
        is_mono = bool(own) and _mono_at(n, el)
        text[id(n)], run[id(n)], mono[id(n)] = own, own, (own if is_mono else 0)
    for n in reversed(nodes[1:]):
        p = id(n.parent)
        if p not in text:
            continue
        text[p] += text[id(n)]
        mono[p] += mono[id(n)]
        d = _st(n).get("display") or ""
        if (n.tag in INLINE_TAGS) if not d else d in ("inline", "contents"):
            run[p] += run[id(n)]
    total = text[id(el)]
    if total <= 0:
        return False
    for n in nodes:
        t = text[id(n)]
        if t < total * 0.6 or mono[id(n)] < t * 0.9:
            continue
        ws = _st(n).get("white-space") or ""
        if n.tag in MONO_TAGS or ws.startswith("pre") or ws == "break-spaces" or run[id(n)] >= t * 0.8:
            return True
    return False


def _is_dialog(n):
    roles = (n.get("role") or "").lower().split()
    return n.tag == "dialog" or "dialog" in roles or "alertdialog" in roles or (n.get("aria-modal") or "").strip().lower() == "true"


def is_dialog_card(outer):
    if _is_dialog(outer):
        return True
    for a in outer.ancestors():
        if _is_dialog(a):
            return True
        if is_card_like(a):
            return False
    return False


def box_in_mockup(el):
    """decorative_text.rs box_in_mockup (approx.): role=img outside svg, or a window with three title-bar dots."""
    in_svg = any(a.tag == "svg" for a in [el] + list(el.ancestors()))
    for c in [el] + list(el.ancestors()):
        if c.tag == "figcaption":
            break
        if not in_svg and "img" in (c.get("role") or "").lower().split():
            return True
        if c.tag == "svg":
            in_svg = False
    for c in [el] + list(el.ancestors())[:4]:
        for bar in c.elements()[:2]:
            dots = [d for d in bar.elements() if not d.elements() and not d.norm_text()]
            if len(dots) >= 3 and len(bar.elements()) <= 6:
                return True
    return False


def rule_nested_cards(ctx):
    if not ctx.full_page or ctx.doc is None:
        return []
    flagged = []
    card = {}

    def cl(n):
        k = id(n)
        if k not in card:
            card[k] = is_card_like(n)
        return card[k]
    for el in ctx.doc.iter():
        if el.tag in ("pre", "code") or not cl(el):
            continue
        cls, sa = el.get("class") or "", el.get("style") or ""
        if POSITIONED_CLASS.search(cls) or POSITIONED_STYLE.search(sa):
            continue
        if len(el.text().strip()) < 10 or OVERLAY_CLASS.search(cls):
            continue
        for p in el.ancestors():
            if cl(p):
                if not is_dialog_card(p) and not frames_embedded_content(el, p):
                    flagged.append(el)
                break
    hits = []
    for el in flagged:
        if any(o is not el and o in set(el.iter()) for o in flagged):
            continue
        if _ignored(el, "nested-cards"):
            continue
        h = {"rule": "nested-cards", "snippet": "Card inside card (%s)" % el.tag}
        if box_in_mockup(el):
            h["severity"] = "advisory"
        hits.append(h)
    return hits


# ---------------------------------------------------------------------------------------------------------------------
# icon-tile-stack: adapters.rs check_element_icon_tile + rules.rs check_icon_tile
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍\U0001F1E6-\U0001F1FF]")
ICON_SEL = re.compile(r"fa-|icon")


def _is_icon(n):
    return n.tag == "svg" or (n.tag == "i" and ("data-lucide" in n.attrs or bool(ICON_SEL.search(n.get("class") or ""))))


def rule_icon_tile(ctx):
    hits = []
    for h in ctx.elements():
        if h.tag not in HEADINGS:
            continue
        sib = h.prev_element()
        if sib is None or sib.tag in HEADINGS:
            continue
        ss = _st(sib)
        w, ht = _decl_px(sib, "width") or 0.0, _decl_px(sib, "height") or 0.0
        if not (32 <= w <= 128 and 32 <= ht <= 128) or not (0.7 <= w / ht <= 1.4):
            continue
        icon = next((n for n in sib.iter() if _is_icon(n)), None)
        icon_w = 0.0
        if icon is not None:
            icon_w = _decl_px(icon, "width") or pf0(icon.get("width"))
        own = "".join(c for c in sib.children if isinstance(c, str)).strip()
        emoji = not sib.elements() and bool(own) and not EMOJI.sub("", own).strip()
        bg = C.parse_color(ss.get("background-color") or "")
        img = ss.get("background-image") or "none"
        bg_visible = (bg is not None and bg[3] >= 0.05) or (img and img != "none")
        ring = max([L["spread"] for L in shadow_layers(ss.get("box-shadow")) if L["alpha"] >= 0.05 and L["x"] == 0
                    and L["y"] == 0 and L["blur"] == 0 and L["spread"] >= 0.5] or [0.0])
        border = max(_len(sib, "border-top-width"), ring)
        if not bg_visible and not border > 0:
            continue
        if radius_px_loose(sib, w) >= w / 2:
            continue
        if icon is None and not emoji:
            continue
        if icon_w and icon_w >= w * 0.95:
            continue
        if _ignored(h, "icon-tile-stack"):
            continue
        hits.append(("icon-tile-stack", '%sx%spx icon tile above %s "%s"'
                     % (js_num(js_round(w)), js_num(js_round(ht)), h.tag, h.text().strip()[:60])))
    return hits


# ---------------------------------------------------------------------------------------------------------------------
# gpt-thin-border-wide-shadow: adapters.rs check_element_gpt_border_shadow + measures.rs row walk
GPT_MIN_ROW, GPT_MIN_BLUR, GPT_TOL, GPT_DEPTH, GPT_SIBS, GPT_CELL = 3, 32.0, 0.25, 2, 24, 32


def gpt_pair(node):
    st = _st(node)
    blur = None
    for L in shadow_layers(st.get("box-shadow")):
        if L["inset"] or L["alpha"] < 0.12 or L["blur"] + min(L["spread"], 0) < GPT_MIN_BLUR:
            continue
        blur = L["blur"] if blur is None else max(blur, L["blur"])
    if blur is None:
        return None
    thin = []
    for s in SIDES:
        w = _len(node, "border-%s-width" % s)
        if (st.get("border-%s-style" % s) or "").lower() in ("none", "hidden"):
            continue
        col = st.get("border-%s-color" % s)
        a = 1.0 if (col or "").lower() == "currentcolor" else color_alpha(col) if col else 1.0
        if 0 < w <= 1.5 and a >= 0.28:
            thin.append(w)
    return (max(thin), blur) if len(thin) >= 2 else None


def gpt_paints_at_rest(node):
    op, hidden, oof = 1.0, False, False
    for depth, n in enumerate([node] + list(n2 for n2 in node.ancestors())):
        st = _st(n)
        if "hidden" in n.attrs or (st.get("display") or "").lower() == "none":
            return False
        if depth <= GPT_DEPTH and (st.get("position") or "").lower() in ("absolute", "fixed"):
            oof = True
        hidden |= (st.get("visibility") or "").lower() in ("hidden", "collapse")
        o = parse_float(st.get("opacity"))
        if o == o:
            op *= o
    return not (oof and (hidden or op <= 0.02))


def _close(a, b):
    m = max(a, b)
    return m > 0 and abs(a - b) / m <= GPT_TOL


def _same_card(a, b):
    if a.tag != b.tag:
        return False
    for p in ("width", "height"):
        va, vb = (_st(a).get(p) or "").strip(), (_st(b).get(p) or "").strip()
        if va.endswith("px") and vb.endswith("px"):
            x, y = parse_float(va), parse_float(vb)
            if x == x and y == y and not _close(x, y):
                return False
    return True


def gpt_row_size(el):
    """measures.rs gpt_border_shadow_row_size."""
    if not gpt_paints_at_rest(el):
        return 0

    def mate(n):
        return _same_card(el, n) and gpt_pair(n) is not None and gpt_paints_at_rest(n)

    def cell_mates(cell, sib, depth):
        if depth == 0:
            return 1 if mate(sib) else 0
        if cell.tag != sib.tag:
            return 0
        level, budget = [sib], GPT_CELL
        for _ in range(depth):
            nxt = []
            for n in level:
                for ch in n.elements():
                    if budget == 0:
                        break
                    budget -= 1
                    nxt.append(ch)
            if not nxt:
                return 0
            level = nxt
        found = 0
        for n in level:
            if found + 1 >= GPT_MIN_ROW:
                break
            if mate(n):
                found += 1
        return found
    best, cell = 1, el
    for depth in range(GPT_DEPTH + 1):
        if depth:
            if cell.parent is None or cell.parent.tag == "#document":
                break
            cell = cell.parent
        row = 1
        before, after = cell.prev_element(), cell.next_element()
        for _ in range(GPT_SIBS):
            if before is None and after is None:
                break
            if before is not None:
                row += cell_mates(cell, before, depth)
                if row >= GPT_MIN_ROW:
                    return row
                before = before.prev_element()
            if after is not None:
                row += cell_mates(cell, after, depth)
                if row >= GPT_MIN_ROW:
                    return row
                after = after.next_element()
        best = max(best, row)
        if best >= GPT_MIN_ROW:
            break
    return best


def rule_gpt(ctx):
    hits = []
    for el in ctx.elements():
        p = gpt_pair(el)
        if p and gpt_row_size(el) >= GPT_MIN_ROW and not _ignored(el, "gpt-thin-border-wide-shadow"):
            hits.append(("gpt-thin-border-wide-shadow", "%spx border + %spx shadow blur, repeated across the row"
                         % (js_num(p[0]), js_num(js_round(p[1])))))
    return hits


# ---------------------------------------------------------------------------------------------------------------------
# cramped-padding (static flush form): quality.rs check_quality
FLUSH_SKIP = {"html", "body", "main", "header", "footer", "nav", "article", "aside", "button", "a", "label", "summary",
              "code", "pre", "input", "textarea", "select", "form", "figure", "table", "tbody", "thead", "tr", "td", "th"}
VISIBLE_BORDER_STYLES = {"", "solid", "dashed", "dotted", "double", "groove", "ridge", "inset", "outset"}


def _side_len(node, prop):
    v = _st(node).get(prop)
    if v is None or v == "":
        return 0.0
    if "var(" in v.lower():
        return None
    px = CSS.length_px(v, _font(node), CSS.DEFAULT_FONT_PX, None)
    return px if px is not None else (None if "%" in v else 0.0)


def _insulates(node, s, depth=4):
    for key in ("padding-" + SIDES[s], "margin-" + SIDES[s]):
        v = _side_len(node, key)
        if v is None or v >= 4:
            return True
    if depth == 0 or own_text_longer_than(node, 4):
        return False
    kids = node.elements()
    return len(kids) == 1 and _insulates(kids[0], s, depth - 1)


def bg_boundary(node):
    """quality.rs has_visible_background_boundary."""
    bg = _st(node).get("background-color")
    if not bg or "var(" in bg or is_transparent(bg):
        return False
    for p in node.ancestors():
        pb = _st(p).get("background-color")
        if pb and "var(" in pb:
            return False
        if pb and not is_transparent(pb):
            return not nearly_match(bg, pb)
    scheme = " ".join((_st(n).get("color-scheme") or "") for n in [node] + list(node.ancestors()))
    if "dark" in scheme.lower():
        return True
    return not nearly_match(bg, "rgb(255, 255, 255)")


def _outline(node):
    """(width px, colour, style): longhands, else the `outline` shorthand core leaves unexpanded."""
    st = _st(node)
    w, col, style = _len(node, "outline-width"), st.get("outline-color"), (st.get("outline-style") or "").strip().lower()
    short = st.get("outline")
    if short:
        toks = CSS.split_top(short)
        if short.strip() in ("0", "none"):
            return 0.0, col, "none"
        for t in toks:
            tl = t.lower()
            if tl in CSS.BORDER_STYLES:
                style = style or tl
            elif CSS.length_px(t, _font(node)) is not None:
                w = w or CSS.length_px(t, _font(node))
            elif C.parse_color(t) is not None:
                col = col or t
    return w, col or "currentcolor", style


def cramped_flush(node):
    if node.tag in FLUSH_SKIP or (node.id or "").startswith(("claude-", "cic-")):
        return None
    st = _st(node)
    kids = node.elements()
    if own_text_longer_than(node, 10) or (st.get("position") or "") in ("fixed", "absolute") or not kids:
        return None
    bvis = []
    for s in SIDES:
        col = st.get("border-%s-color" % s) or "currentcolor"
        style = (st.get("border-%s-style" % s) or "").strip().lower()
        bvis.append(_len(node, "border-%s-width" % s) > 0 and "var(" not in col and not is_transparent(col)
                    and style in VISIBLE_BORDER_STYLES)
    ow, ocol, ostyle = _outline(node)
    outline = ow > 0 and not is_transparent(ocol) and "var(" not in ocol and ostyle not in ("", "none")
    bgv = bg_boundary(node)
    if not (any(bvis) or outline or bgv):
        return None
    flush = []
    for s in range(4):
        pad = _side_len(node, "padding-" + SIDES[s])
        if (bvis[s] or outline or bgv) and pad is not None and pad <= 2 and not any(_insulates(k, s) for k in kids):
            flush.append(SIDES[s])
    if not flush or not any(len(k.text().strip()) > 4 for k in kids):
        return None
    vis_sides = [SIDES[i] for i in range(4) if bvis[i]]
    parts = (["border"] if len(vis_sides) == 4 else ["border-" + "/".join(vis_sides)] if vis_sides else [])
    parts += (["outline"] if outline else []) + (["bg"] if bgv else [])
    sides = "all sides" if len(flush) == 4 else "/".join(flush)
    cls = node.classes[0] if node.classes else ""
    ident = '<%s> "%s"' % (node.tag, cls) if cls else "<%s>" % node.tag
    return "%s: children flush against %s on %s (no inset)" % (ident, "+".join(parts), sides)


def rule_cramped(ctx):
    hits = []
    for el in ctx.elements():
        s = cramped_flush(el)
        if s and not _ignored(el, "cramped-padding"):
            hits.append(("cramped-padding", s))
    return hits


# ---------------------------------------------------------------------------------------------------------------------
# clipped-overflow-container: adapters.rs check_element_clipped_overflow
VIEWPORT_WORDS = {"carousel", "comparison", "compare", "fisheye", "flickity", "marquee", "owl", "preview", "reel",
                  "rolling", "scroller", "slick", "slider", "slideshow", "splide", "split", "swiper", "tempwrap",
                  "ticker", "viewport"}
VIEWPORT_PAIRS = {("demo", "area"), ("demo", "stage"), ("demo", "viewport")}
DECOR_WORDS = {"art", "bg", "background", "badge", "blob", "crop", "decor", "dot", "glow", "grain", "image", "mask",
               "ornament", "overlay", "photo", "scrim", "shadow", "shine", "texture"}
POPOVER_ROLES = {"dialog", "listbox", "menu", "menubar", "tooltip"}
INTERACTIVE_ROLES = {"button", "dialog", "link", "listbox", "menu", "menuitem", "option", "tooltip"}


def _ident(n):
    return "%s %s" % (n.get("class") or "", n.get("id") or "")


def clipped_axes(node):
    st = _st(node)
    clips = lambda v: v in ("hidden", "clip")
    scrolls = lambda v: v in ("auto", "scroll")
    ox, oy, ov = [(st.get(k) or "visible").strip() for k in ("overflow-x", "overflow-y", "overflow")]
    ov1 = ov.split()[0] if ov.split() else ov
    cx, cy = clips(ox) or clips(ov1), clips(oy) or clips(ov1)
    if not (cx or cy) or scrolls(ox) or scrolls(oy) or scrolls(ov1):
        return None
    if (st.get("display") or "") in ("contents", "none"):
        return None
    return cx, cy


def _viewport_named(n):
    return ident_names_any(_ident(n), VIEWPORT_WORDS, VIEWPORT_PAIRS)


def _can_own(n):
    if n.tag in ("html", "body"):
        return False
    if re.search(r"\b(carousel|slider)\b", (n.get("aria-roledescription") or "").lower()):
        return False
    return not (_viewport_named(n) or any(_viewport_named(c) for c in n.elements()))


def _is_popover(n):
    return "popover" in n.attrs or (n.tag == "dialog" and "open" in n.attrs) or \
        (n.get("role") or "").strip().lower() in POPOVER_ROLES


def _is_interactive(n):
    if n.tag == "a" and "href" in n.attrs:
        return True
    if n.tag in ("button", "input", "select", "summary", "textarea"):
        return True
    if "tabindex" in n.attrs and n.get("tabindex").strip() != "-1":
        return True
    return (n.get("role") or "").strip().lower() in INTERACTIVE_ROLES


def _decorative(n):
    if closest(n, lambda a: a.get("aria-hidden") == "true"):
        return True
    if (n.get("role") or "").lower() in ("none", "presentation") or n.tag in ("img", "svg", "canvas", "video"):
        return True
    if ident_names_any(_ident(n), DECOR_WORDS) and not (n.norm_text() or any(_is_interactive(d) for d in n.iter())):
        return True
    return False


ESC_PROPS = (("top", 0, 1), ("right", 1, 0), ("bottom", 0, 1), ("left", 1, 0), ("inset", 1, 1), ("inset-block", 1, 1),
             ("inset-inline", 1, 1), ("inset-block-start", 1, 1), ("inset-block-end", 1, 1),
             ("inset-inline-start", 1, 1), ("inset-inline-end", 1, 1))


def escapes(node, cx, cy):
    """measures.rs positioned_style_implies_escape_axis."""
    st = _st(node)
    for prop, on_x, on_y in ESC_PROPS:
        if not ((on_x and cx) or (on_y and cy)):
            continue
        v = (st.get(prop) or "").strip().lower()
        if v and (re.search(r"(?:^|[\s(])-+(?:\d|\.)", v) or re.search(r"(?:^|[\s(])100(?:\.0+)?%", v)):
            return True
    return False


def check_clipped(el):
    ax = clipped_axes(el)
    if not ax or not _can_own(el):
        return None
    for ch in el.iter():
        if (_st(ch).get("position") or "") not in ("absolute", "fixed"):
            continue
        if not (_is_popover(ch) or any(_is_popover(d) for d in ch.iter())):
            continue
        if _decorative(ch) or _viewport_named(ch):
            continue
        if not escapes(ch, *ax):
            continue
        nearer = False
        for inner in ch.ancestors():
            if inner is el:
                break
            ia = clipped_axes(inner)
            if ia and _can_own(inner) and escapes(ch, *ia):
                nearer = True
                break
        if nearer:
            continue
        return "%s clips positioned %s" % (class_selector(el), class_selector(ch))
    return None


def rule_clipped(ctx):
    hits = []
    for el in ctx.elements():
        s = check_clipped(el)
        if s and not _ignored(el, "clipped-overflow-container"):
            hits.append(("clipped-overflow-container", s))
    return hits


# ---------------------------------------------------------------------------------------------------------------------
# shape-assembled-illustration: html_patterns.rs scan_html_for_shape_assembled_illustration
SVG_BLOCK = re.compile(r"<svg\b[^>]*>.*?</svg>", re.I | re.S)
SVG_OPEN = re.compile(r"^<svg\b[^>]*>", re.I)
VIEWBOX = re.compile(r"""\bviewBox\s*=\s*["']\s*[-0-9.]+[\s,]+[-0-9.]+[\s,]+([0-9.]+)[\s,]+([0-9.]+)\s*["']""", re.I)
FILL = re.compile(r"""\bfill\s*[:=]\s*["']?\s*([^"';>}\s]+)""", re.I)


def _attr_dim(open_tag, name):
    for m in re.finditer(r"""%s\s*=\s*["']\s*([0-9.]+)(?:px)?\s*["']""" % name, open_tag, re.I):
        if m.start() > 0 and (open_tag[m.start() - 1].isalnum() or open_tag[m.start() - 1] in "-_"):
            continue
        return parse_float(m.group(1))
    return None


def scan_shapes(html):
    out = []
    for m in SVG_BLOCK.finditer(html):
        block = m.group(0)
        om = SVG_OPEN.match(block)
        open_tag = om.group(0) if om else ""
        if len(re.findall(r"<(?:text|tspan)\b", block, re.I)) > 2 or re.search(r"<pattern\b", block, re.I):
            continue
        prims = len(re.findall(r"<(?:rect|circle|ellipse|polygon)\b", block, re.I))
        if prims < 8:
            continue
        vb = VIEWBOX.search(open_tag)
        w = _attr_dim(open_tag, "width")
        h = _attr_dim(open_tag, "height")
        w = w if w is not None else (parse_float(vb.group(1)) if vb else None)
        h = h if h is not None else (parse_float(vb.group(2)) if vb else None)
        if w is None or h is None or not (w >= 200 and h >= 200):
            continue
        fills = []
        for fm in FILL.finditer(block):
            p = fm.group(1).strip().lower()
            if p and p not in ("none", "transparent", "currentcolor", "inherit") and p not in fills:
                fills.append(p)
        if len(fills) < 3:
            continue
        out.append(("shape-assembled-illustration", "inline <svg> scene: %d primitive shapes, ~%sx%spx, %d fill colors"
                    % (prims, js_num(js_round(w)), js_num(js_round(h)), len(fills))))
    return out


def rule_shapes(ctx):
    return scan_shapes(ctx.text) if ctx.full_page else []


# ---------------------------------------------------------------------------------------------------------------------
# broken-image: adapters.rs check_element_broken_image
def rule_broken_image(ctx):
    hits = []
    if ctx.doc is None:
        return hits
    for el in ctx.doc.iter():
        if el.tag != "img" or _ignored(el, "broken-image"):
            continue
        src = el.get("src")
        if src is None:
            hits.append(("broken-image", "<img> with no src attribute"))
        elif src.strip() in ("", "#"):
            hits.append(("broken-image", '<img src="%s">' % src))
    return hits


# ---------------------------------------------------------------------------------------------------------------------
# monotonous-spacing: html_patterns.rs check_html_patterns_with (layout block)
SPACING_PX = re.compile(r"(?:padding|margin)(?:-(?:top|right|bottom|left))?\s*:\s*(\d+)px", re.I)
GAP_PX = re.compile(r"gap\s*:\s*(\d+)px", re.I)
TW_SPACE = re.compile(r"\b(?:p|px|py|pt|pb|pl|pr|m|mx|my|mt|mb|ml|mr|gap)-(\d+)\b")
SPACING_REM = re.compile(r"(?:padding|margin)(?:-(?:top|right|bottom|left))?\s*:\s*([0-9.]+)rem", re.I)


def monotonous(style_text, class_text):
    vals = [int(n) for n in SPACING_PX.findall(style_text) if 0 < int(n) < 200]
    vals += [int(n) for n in GAP_PX.findall(style_text)]
    vals += [int(n) * 4 for n in TW_SPACE.findall(class_text)]
    for n in SPACING_REM.findall(style_text):
        f = parse_float(n)
        if f == f:
            v = js_round(f * 16)
            if 0 < v < 200:
                vals.append(v)
    r = [js_round(v / 4.0) * 4 for v in vals]
    if len(r) < 10:
        return None
    counts = {}
    for v in r:
        counts[v] = counts.get(v, 0) + 1
    top = max(counts.values())
    pct = top / len(r)
    if pct > 0.6 and len({v for v in r if v > 0}) <= 3:
        dom = next(k for k, c in counts.items() if c == top)
        return "~%spx used %d/%d times (%s%%)" % (js_num(dom), top, len(r), js_num(js_round(pct * 100)))
    return None


def rule_monotonous(ctx):
    if not ctx.full_page:
        return []
    s = monotonous(ctx.css_text, ctx.class_text)
    return [("monotonous-spacing", s)] if s else []


# ---------------------------------------------------------------------------------------------------------------------
# design-system-radius: design_system.rs is_allowed_radius_raw / static_engine.rs collect_static_design_system_findings
PILL_NAME = re.compile(r"(^|\.)(full|pill|round|rounded-full)$")


def design_radii(design):
    rounded = (design or {}).get("rounded") if isinstance(design, dict) else None
    radii, pill = [], False
    if not isinstance(rounded, dict):
        return radii, pill
    for name, raw in rounded.items():
        if not isinstance(raw, (str, int, float)) or isinstance(raw, bool):
            continue
        v = str(raw).strip()
        if not v or "var(" in v or "%" in v:
            continue
        px = _plain_len(v)
        if px is None:
            continue
        radii.append(px)
        if PILL_NAME.search(str(name).lower()):
            pill = True
    return radii, pill


def _plain_len(v):
    """foundation resolve_length_px at 16px: px, rem, em, %, unitless."""
    v = v.strip().lower()
    if not v or v in ("normal", "auto", "inherit"):
        return None
    n = parse_float(v)
    if n != n:
        return None
    if v.endswith("px"):
        return n
    if v.endswith("rem") or v.endswith("em"):
        return n * 16
    if v.endswith("%"):
        return n / 100 * 16
    return n * 16


def radius_allowed(raw, radii, pill):
    if not radii:
        return True
    t = raw.strip().lower()
    if t in ("", "0", "none", "initial", "inherit") or "var(" in t or "%" in t:
        return True
    px = _plain_len(t)
    if px is None or px <= 0.5:
        return True
    if pill and px >= 99:
        return True
    return any(abs(r - px) <= 0.5 for r in radii)


def radius_tokens(value):
    return [t.strip().rstrip(")") for t in re.split(r"\s+", re.sub(r"\s*/\s*", " ", value)) if t.strip().rstrip(")")]


def _key(tok):
    px = _plain_len(tok)
    return round(px * 100) / 100 if px is not None else tok.lower()


def rule_design_radius(ctx):
    radii, pill = design_radii(ctx.design)
    if not radii:
        return []
    hits, keys = [], {}
    for el in ctx.elements():
        if CSS.is_hidden(el) or el.get("aria-hidden") == "true" or closest(el, lambda a: a.get("aria-hidden") == "true"):
            continue
        raw = ((_st(el).get("__raw__") or {}).get("border-radius") or _st(el).get("border-radius") or "").strip()
        if not raw:
            continue
        for tok in radius_tokens(raw):
            if radius_allowed(tok, radii, pill) or _key(tok) in keys:
                continue
            sample = el.norm_text()[:40]
            keys[_key(tok)] = len(hits)
            hits.append({"rule": "design-system-radius", "line": 0, "snippet": "border-radius %s on %s%s is outside the "
                         "DESIGN.md rounded scale" % (tok, el.tag, ' "%s"' % sample if sample else "")})
    for i, line in enumerate(ctx.text.split("\n")):
        if line.lstrip().startswith(("//", "/*", "*")):
            continue
        for rx, label in ((r"border-radius\s*:\s*([^;}\n]+)", "border-radius"),
                          (r"""borderRadius\s*[:=]\s*["'`]([^"'`]+)["'`]""", "borderRadius")):
            for m in re.finditer(rx, line, re.I if label == "border-radius" else 0):
                for tok in radius_tokens(m.group(1)):
                    if radius_allowed(tok, radii, pill):
                        continue
                    k = _key(tok)
                    if k in keys:
                        h = hits[keys[k]]
                        if not h.get("line"):
                            h["line"] = i + 1
                        continue
                    keys[k] = len(hits)
                    hits.append({"rule": "design-system-radius", "line": i + 1,
                                 "snippet": "%s: %s is outside the DESIGN.md rounded scale" % (label, tok)})
    return hits


RULES = {
    "side-tab": rule_side_tab,
    "border-accent-on-rounded": rule_border_accent,
    "nested-cards": rule_nested_cards,
    "icon-tile-stack": rule_icon_tile,
    "gpt-thin-border-wide-shadow": rule_gpt,
    "cramped-padding": rule_cramped,
    "clipped-overflow-container": rule_clipped,
    "shape-assembled-illustration": rule_shapes,
    "broken-image": rule_broken_image,
    "monotonous-spacing": rule_monotonous,
    "design-system-radius": rule_design_radius,
}
