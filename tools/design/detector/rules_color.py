"""rules_color — the colour rule group of impeccable's static HTML engine, ported to our cascade.

Upstream: impeccable crates (Apache-2.0) at pin 5bf0a069dc85; per-rule upstream fn in PORT_MAP.md.
Rules: low-contrast, gray-on-color, gradient-text, ai-color-palette, cream-palette, dark-glow, radial-halo,
radial-spotlight-glow, design-system-color, buried-raster, repeating-stripes-gradient, codex-grid-background,
organic-clip-path. RULES maps id -> fn(ctx) -> [hit dict].

Upstream reads a camelCase computed style; ours is node.style (kebab-case, var() resolved, raw strings). The
helpers below re-read what upstream's static cascade would have produced (own opacity, own shadows, raw weight).
"""
import math
import re

from . import color as C
from . import css as CSS

WS = r"[\t\n\x0B\x0C\r \xA0  -     　﻿]"
WHITE = (255.0, 255.0, 255.0, 1.0)
SAFE_TAGS = {"blockquote", "nav", "a", "input", "textarea", "select", "pre", "code", "span", "th", "td", "tr", "li",
             "label", "button", "hr", "html", "head", "body", "script", "style", "link", "meta", "title", "br", "img",
             "svg", "path", "circle", "rect", "line", "polyline", "polygon", "g", "defs", "use"}
NON_RENDERED_TAGS = {"script", "style", "title", "noscript", "template", "head", "meta", "link", "base", "param",
                     "source", "track", "datalist", "col", "colgroup", "area"}
NO_PAINT = {"", "transparent", "none", "initial", "inherit", "unset", "revert", "revert-layer"}
LARGE_PX, LARGE_BOLD_PX = 18 * 96 / 72, 14 * 96 / 72


# ─── small value helpers ─────────────────────────────────────────────────────────────────────────────────────────────
def sv(node, prop, default=""):
    return ((node.style or {}).get(prop) or default) if node is not None else default


def own_raw(node, prop):
    """The value this element declares itself (not inherited), var() resolved."""
    st = node.style or {}
    v = (st.get("__raw__") or {}).get(prop)
    return CSS._resolve_vars(v, st.get("__custom__") or {}) if v else ""


def pfloat(s):
    """JS parseFloat."""
    m = re.match(r"\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)", s or "")
    return float(m.group(1)) if m else float("nan")


def pf0(s):
    v = pfloat(s)
    return 0.0 if math.isnan(v) else v


def jsnum(v):
    """JS String(number)."""
    return str(int(v)) if float(v).is_integer() else repr(float(v))


def pc(value):
    """parse_any_color with upstream's rounded channels; None for currentcolor/inherit/var()."""
    if not value:
        return None
    v = value.strip()
    if v.lower() in ("currentcolor", "inherit") or "var(" in v.lower():
        return None
    c = C.parse_color(v)
    if c is None:
        return None
    return (float(round(c[0])), float(round(c[1])), float(round(c[2])), c[3])


def color_prop(node, prop):
    v = sv(node, prop)
    if v.strip().lower() == "currentcolor":
        return pc(sv(node, "color"))
    return pc(v)


def alpha(c):
    return c[3] if c is not None else 1.0


def hexs(c):
    return C.hexs(c) if c is not None else "?"


def spread(c):
    return max(c[:3]) - min(c[:3])


def lum(c):
    def lin(v):
        v = v / 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2])


def contrast(a, b):
    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def over(top, base):
    """compositeColorOver: rounded channels, opaque result."""
    a = alpha(top)
    return tuple(float(round(top[i] * a + base[i] * (1 - a))) for i in range(3)) + (1.0,)


def hue(c):
    r, g, b = (x / 255.0 for x in c[:3])
    mx, mn = max(r, g, b), min(r, g, b)
    if mx == mn:
        return 0.0
    d = mx - mn
    if mx == r:
        h = ((g - b) / d + (6 if g < b else 0)) / 6
    elif mx == g:
        h = ((b - r) / d + 2) / 6
    else:
        h = ((r - g) / d + 4) / 6
    return float(math.floor(h * 360 + 0.5))


def light_sat(c):
    mx, mn = max(c[:3]) / 255.0, min(c[:3]) / 255.0
    l = (mx + mn) / 2
    d = mx - mn
    s = 0.0 if d <= 0 or l <= 0 or l >= 1 else d / (1 - abs(2 * l - 1))
    return l, s


def is_gray_ink(c):
    l, s = light_sat(c)
    return s < 0.2 and 0.3 < l < 0.85


def oklch_lc(c):
    def dec(x):
        x = x / 255.0
        return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4
    r, g, b = dec(c[0]), dec(c[1]), dec(c[2])
    cb = lambda v: math.copysign(abs(v) ** (1 / 3), v)
    l = cb(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
    m = cb(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
    s = cb(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
    L = 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s
    A = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s
    B = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s
    return L, math.hypot(A, B)


def reads_as_colour(bg):
    """rules.rs background_reads_as_colour."""
    lm = lum(bg)
    scale = 1.0 if lm >= 0.01 else math.sqrt(0.01 / max(lm, 1e-4))
    if spread(bg) < 40 * scale:
        return False
    L, Ch = oklch_lc(bg)
    return L < 0.9 or Ch >= 0.09


def to_fixed(v, n):
    return "%.*f" % (n, v)


def ratio_label(r, thr):
    """color.rs ratio_label: a failing ratio never prints as its bar."""
    one = to_fixed(r, 1)
    if r < 0 or not r < thr or float(one) < thr:
        return one
    two = to_fixed(r, 2)
    if float(two) < thr:
        return two
    return str(math.floor(r * 100) / 100)


def contrast_severity(r, thr):
    if not r < thr:
        return None
    floor = 4.2 if thr == 4.5 else 2.8 if thr == 3 else None
    return "advisory" if floor is not None and float(ratio_label(r, thr)) >= floor else None


def split_top(s, sep=","):
    return CSS.split_top(s, sep)


def balanced(s, open_idx):
    """Index of the ')' closing the '(' at open_idx, else None."""
    depth = 0
    for i in range(open_idx, len(s)):
        if s[i] == "(":
            depth += 1
        elif s[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    return None


COLOR_FN = re.compile(r"\b(rgba?|hsla?|hwb|oklch|oklab|lch|lab|color|color-mix)\(", re.I)
HEX36 = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")


def gradient_colors(img):
    """color.rs parse_gradient_colors: colour functions, then 3/6-digit hex outside them (no named colours)."""
    if not img or "gradient" not in img:
        return []
    out, spans, pos = [], [], 0
    while True:
        m = COLOR_FN.search(img, pos)
        if not m:
            break
        end = balanced(img, m.end() - 1)
        if end is None:
            break
        spans.append((m.start(), end + 1))
        c = pc(img[m.start():end + 1])
        if c is not None:
            out.append(c)
        pos = end + 1
    for m in HEX36.finditer(img):
        if not any(a <= m.start() < b for a, b in spans):
            out.append(pc("#" + m.group(1)))
    return out


# ─── DOM gates ───────────────────────────────────────────────────────────────────────────────────────────────────────
def chain(node):
    return [node] + list(node.ancestors())


def scoped_ignored(node, rule):
    """adapters.rs scoped_ignore_active: data-impeccable-ignore on the element or an ancestor."""
    for n in chain(node):
        v = n.attrs.get("data-impeccable-ignore")
        if v is not None:
            parts = [p for p in re.split(r"[\s,]+", v.strip().lower()) if p]
            if not parts or "*" in parts or rule in parts:
                return True
    return False


def hidden_by_attr(n):
    v = n.attrs.get("hidden")
    if v is None:
        return False
    if v.strip().lower() == "until-found":
        return True
    return sv(n, "display").strip() in ("", "none")


def in_non_rendered(node):
    """quality.rs is_in_non_rendered_markup."""
    if node.tag in NON_RENDERED_TAGS or hidden_by_attr(node):
        return True
    if node.tag == "details" and "open" not in node.attrs:
        return True
    child = node
    for p in node.ancestors():
        if p.tag in NON_RENDERED_TAGS or hidden_by_attr(p):
            return True
        if p.tag == "details" and "open" not in p.attrs:
            summ = next((c for c in p.elements() if c.tag == "summary"), None)
            if summ is not child:
                return True
        child = p
    return False


SR_ONLY = ("sr-only", "visually-hidden", "visuallyhidden", "screen-reader", "screenreader")


def visually_hidden(node):
    for n in chain(node):
        cls = (n.attrs.get("class") or "").lower()
        if any(k in cls for k in SR_ONLY) or any(c in ("a11y-hidden", "hidden-visually") for c in cls.split()):
            return True
    if sv(node, "position") in ("absolute", "fixed"):
        if re.search(r"rect\(\s*0", sv(node, "clip")) or re.search(r"inset\(\s*(?:50%|99|100%)", sv(node, "clip-path")):
            return True
        if (pfloat(sv(node, "width")) == 1 or pfloat(sv(node, "height")) == 1) and sv(node, "overflow") in ("hidden", "clip"):
            return True
    return False


def direct_text(node):
    return "".join(c for c in node.children if isinstance(c, str))


EMOJI = re.compile("[\U0001F1E6-\U0001F1FF\U0001F300-\U0001F9FF\U0001FA00-\U0001FAFF☀-➿⌀-⏿"
                   "️‍\U0001F3FB-\U0001F3FF]")
ICON_FONTS = ("material icons", "material symbols", "materialicons", "materialsymbols", "material design icons",
              "font awesome", "fontawesome", "icomoon", "glyphicons", "bootstrap-icons", "remixicon", "ionicons",
              "tabler-icons")


def emoji_only(t):
    return bool(t) and bool(EMOJI.search(t)) and not EMOJI.sub("", t).strip()


def glyph_only(t):
    t = t.strip()
    return bool(t) and not any(ch.isalnum() for ch in t)


def is_icon_text(node, t):
    w = t.strip()
    fam = sv(node, "font-family").lower()
    if glyph_only(t) or (w and len(w) <= 48 and re.fullmatch(r"[a-z0-9_-]+", w) and re.search("[a-z]", w)
                         and any(f in fam for f in ICON_FONTS)):
        return True
    if w not in ("x", "X"):
        return False
    boxes = [node] + ([node.parent] if node.parent is not None else [])
    ctl = next((n for n in chain(node) if n.tag in ("button", "a") or n.attrs.get("role") == "button"), None)
    if ctl is not None:
        boxes.append(ctl)
    return any(("close" in v.lower() or "dismiss" in v.lower())
               for b in boxes for v in (b.attrs.get(k) or "" for k in ("class", "id", "aria-label", "title")))


def disabled(node):
    return any("disabled" in n.attrs or n.attrs.get("aria-disabled") == "true" for n in chain(node))


def font_weight_raw(node):
    """Upstream parseInt(fontWeight) || 400 — 'bold' reads as 400 there (quirk kept for parity)."""
    m = re.match(r"\s*(\d+)", sv(node, "font-weight"))
    w = float(m.group(1)) if m and int(m.group(1)) else 400.0
    first = (split_top(sv(node, "font-family"), ",") or [""])[0].strip().strip("'\"")
    words = [x.lower() for x in re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])", first)]
    if w < 700 and any(x in ("bold", "semibold", "demibold", "extrabold", "ultrabold", "heavy", "black") for x in words):
        return 700.0
    return w


def font_size(node):
    return float((node.style or {}).get("__font_px__") or 16.0)


def opacity_own(node):
    v = pfloat(sv(node, "opacity"))
    return 1.0 if math.isnan(v) else max(0.0, min(1.0, v))


def own_bg(node):
    """readOwnBackgroundColor."""
    return color_prop(node, "background-color")


def surface_label(n):
    i = (n.attrs.get("id") or "").strip()
    if i and not re.search(r"\s", i):
        return "%s#%s" % (n.tag, i)
    return "%s.%s" % (n.tag, n.classes[0]) if n.classes else n.tag


# ─── background walk (background.rs walk_surface / resolve_background) ───────────────────────────────────────────────
def _bg_image(n):
    img = sv(n, "background-image", "none")
    return img if img and img != "none" else ""


def _flatten(overlays, base):
    acc = base
    for _, o in reversed(overlays):
        acc = over(o, acc)
    return acc


def _repeat_axes(text):
    t = text.lower()
    if "no-repeat" in t:
        return False, False
    if "repeat-x" in t:
        return True, False
    if "repeat-y" in t:
        return False, True
    return True, True


def _tile_misses(n, img, font_px):
    """gradient_geometry.rs gradient_tile_misses_text: a gradient tile (size + repeat) that cannot cover a line."""
    if "gradient" not in img.lower() or "url(" in img.lower():
        return False
    size = sv(n, "background-size").strip()
    shorthand = (split_top(sv(n, "background"), ",") or [""])[0]
    if not size:
        m = re.search(r"/\s*([^\s/,]+)(?:\s+([^\s/,]+))?", re.sub(r"\([^()]*(?:\([^()]*\))*[^()]*\)", "()", shorthand))
        size = " ".join(g for g in (m.groups() if m else ()) if g)
    if not size or "," in size:
        return False
    rep = sv(n, "background-repeat") or shorthand
    rx, ry = _repeat_axes(rep)
    toks = size.lower().split()

    def ln(t):
        m = re.fullmatch(r"([-\d.]+)(px|%)", t) or re.fullmatch(r"(0)()", t)
        return (float(m.group(1)), m.group(2) or "px") if m else None
    w = ln(toks[0])
    h = ln(toks[1]) if len(toks) > 1 else None
    zero = lambda l: l is not None and l[0] <= 0
    short = lambda l: l is not None and l[1] == "px" and l[0] < font_px
    return (not rx and zero(w)) or (not ry and (zero(h) or short(h)))


class Surface:
    def __init__(self):
        self.color = None
        self.unresolved = False
        self.host = None
        self.base = None
        self.overlays = []
        self.ghost = None
        self.glabel = None
        self.skipped = []


def walk_surface(el, min_alpha=0.0, skip=(), font_px=None):
    out = Surface()
    cur = el
    while cur is not None and cur.tag != "#document":
        if sv(cur, "display").strip().lower() == "contents":
            cur = cur.parent
            continue
        img = "" if cur in skip else _bg_image(cur)
        has_img = bool(img) and re.search(r"gradient|url\(", img, re.I)
        raw = sv(cur, "background-color")
        bg = color_prop(cur, "background-color")
        if bg is not None and alpha(bg) > min_alpha:
            if alpha(bg) >= 0.99:
                out.color, out.host, out.base = _flatten(out.overlays, bg), cur, bg
                return out
            out.overlays.append((cur, bg))
        elif bg is None and raw.strip().lower() not in NO_PAINT:
            out.unresolved, out.host = True, cur
            return out
        if has_img:
            if font_px is not None and _tile_misses(cur, img, font_px):
                out.skipped.append(cur)
                cur = cur.parent
                continue
            out.host = cur
            layers = split_top(img, ",")
            top = next((l for l in layers if re.search(r"gradient\s*\(|url\s*\(", l, re.I)), None)
            if top is None or not re.search(r"gradient\s*\(", top, re.I) or re.match(r"\s*url\s*\(", top, re.I):
                out.unresolved = True
                return out
            if any(l is not top and re.search(r"url\s*\(", l, re.I) for l in layers):
                stops = gradient_colors(top)
                if not stops or any(alpha(s) < 0.99 for s in stops):
                    out.unresolved = True
                    return out
            out.ghost, out.glabel = cur, surface_label(cur)
            return out
        cur = cur.parent
    out.color, out.base = _flatten(out.overlays, WHITE), WHITE
    return out


def resolve_background(el):
    """The legacy walk (fills under alpha 0.1 ignored): glow and hover read it."""
    s = walk_surface(el, 0.1)
    return None if s.unresolved else s.color


def text_gradient_stops(el, surf):
    """background.rs resolve_text_gradient_stops."""
    overlays, cur = [], el
    while cur is not None and cur.tag != "#document":
        if sv(cur, "display").strip().lower() == "contents":
            cur = cur.parent
            continue
        img = "" if cur in surf.skipped else _bg_image(cur)
        if img and re.search(r"url\(", img, re.I):
            return None
        stops = gradient_colors(img) if img and "gradient" in img.lower() else []
        if stops:
            if any(alpha(s) < 0.99 for s in stops):
                base = walk_surface(cur.parent, 0.0).color if cur.parent is not None and cur.parent.tag != "#document" else WHITE
                stops = [s if alpha(s) >= 0.99 else over(s, base) for s in stops if alpha(s) >= 0.99 or base]
                if not stops:
                    return None
            return [_flatten(overlays, s) for s in stops] if overlays else stops
        bg = color_prop(cur, "background-color")
        if bg is not None and alpha(bg) > 0:
            if alpha(bg) >= 0.99:
                return None
            overlays.append((cur, bg))
        cur = cur.parent
    return None


def fold_opacity(el, ink, surf, eff):
    """adapters.rs fold_surface_opacity -> (visible ink, new effective bg) or (None, eff)."""
    layers, cur, reached = [], el, False
    for _ in range(64):
        if cur is None or cur.tag == "#document":
            reached = surf.host is None
            break
        if cur is surf.host:
            reached = True
            break
        fill = next((f for n, f in surf.overlays if n is cur), None)
        layers.append((fill, opacity_own(cur) if sv(cur, "opacity").strip() else 1.0))
        cur = cur.parent
    if not reached:
        return None, eff
    prod = 1.0
    for _, o in layers:
        prod *= o
    if not prod < 0.999:
        return None, eff
    outer = max(i for i, (_, o) in enumerate(layers) if o < 0.999)
    if not any(f is not None for f, _ in layers[:outer + 1]):
        return ink[:3] + (alpha(ink) * prod,), eff
    if eff is None or surf.base is None:
        return None, eff
    fg = [ink[i] * alpha(ink) for i in range(3)] + [alpha(ink)]
    bg = [0.0, 0.0, 0.0, 0.0]
    for fill, o in layers:
        if fill is not None:
            fa = alpha(fill)
            f = [fill[i] * fa for i in range(3)] + [fa]
            fg = [fg[i] + f[i] * (1 - fg[3]) for i in range(4)]
            bg = [bg[i] + f[i] * (1 - bg[3]) for i in range(4)]
        fg = [v * o for v in fg]
        bg = [v * o for v in bg]
    flat = lambda p: tuple(float(round(p[i] + surf.base[i] * (1 - p[3]))) for i in range(3)) + (1.0,)
    return flat(fg), flat(bg)


# ─── pseudo surfaces / pictures (cascade_build.rs mark_pseudo_rule) ──────────────────────────────────────────────────
def _covers(pd):
    zero = lambda v: (v or "").strip() in ("0", "0px")
    if all(zero(pd.get(s)) for s in ("top", "right", "bottom", "left")):
        return True
    return (pd.get("width") or "").strip() == "100%" and (pd.get("height") or "").strip() == "100%"


def pseudo_surface(node):
    for pe in ("before", "after"):
        pd = node.pseudo.get(pe) if node.pseudo else None
        if not pd or pd.get("position") not in ("absolute", "fixed") or "content" not in pd or not _covers(pd):
            continue
        raw = pd.get("background-color") or pd.get("background") or ""
        if "gradient" in raw.lower():
            continue
        cols = C.find_colors(raw)
        c = pc(cols[0][0]) if cols else None
        if c is not None and alpha(c) >= 0.9:
            return c
    return None


def has_pseudo_picture(node):
    for pe in ("before", "after"):
        pd = node.pseudo.get(pe) if node.pseudo else None
        if pd and pd.get("position") in ("absolute", "fixed") and "content" in pd and _covers(pd) and \
                "url(" in (pd.get("background-image") or pd.get("background") or "").lower():
            return True
    return False


def _stretched(n):
    if sv(n, "position").strip() not in ("absolute", "fixed"):
        return False
    zero = lambda v: v.strip() in ("0", "0px", "0%")
    return all(zero(sv(n, s)) for s in ("top", "right", "bottom", "left")) or \
        (sv(n, "width").strip() == "100%" and sv(n, "height").strip() == "100%")


def _stretched_picture_in(n, stretched, depth, budget):
    if budget[0] <= 0:
        return False
    budget[0] -= 1
    if sv(n, "visibility") == "hidden":
        return False
    if not stretched:
        if _stretched(n):
            stretched = True
        elif sv(n, "position").strip() not in ("", "static"):
            return False
    if stretched and (n.tag in ("img", "picture", "video", "canvas") or "url(" in sv(n, "background-image").lower()
                      or has_pseudo_picture(n)):
        return True
    return depth < 6 and any(_stretched_picture_in(c, stretched, depth + 1, budget) for c in n.elements()[:16])


def picture_under_text(el):
    """layer.rs picture_under_text."""
    budget, node = [512], el
    for _ in range(32):
        if has_pseudo_picture(node):
            return True
        b = own_bg(node)
        if b is not None and alpha(b) >= 0.95:
            return False
        p = node.parent
        if p is None or p.tag == "#document":
            return False
        sibs = p.elements()
        i = sibs.index(node)
        for s in list(reversed(sibs[:i]))[:32] + sibs[i + 1:i + 33]:
            if _stretched_picture_in(s, False, 0, budget):
                return True
        node = p
    return False


# ─── decorative text (decorative_text.rs, simplified: severity only) ─────────────────────────────────────────────────
MOCK_UI = {"app", "browser", "chrome", "dashboard", "desktop", "device", "editor", "frame", "laptop", "phone",
           "screen", "terminal", "ui", "window"}
MOCK_COPY = {"attribution", "caption", "captions", "copyright", "credit", "credits", "license", "licence"}
MOCK_SKIP = {"html", "body", "main", "section", "article", "header", "footer", "nav", "aside", "figcaption"}


def _parts(tok):
    return [p.lower() for p in re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])", tok)]


def is_mockup_marker(s):
    for tok in (s or "").split():
        parts = set(_parts(tok))
        if parts & MOCK_COPY:
            continue
        if parts & {"mockup", "mockups", "illustration", "illustrations"} or ("mock" in parts and parts & MOCK_UI):
            return True
    return False


def is_decorative(el):
    text = " ".join(el.text().split())
    in_svg = any(n.tag == "svg" for n in chain(el))
    for n in chain(el):
        if n.tag == "figcaption":
            break
        if not in_svg and n.attrs.get("role") == "img":
            return True
        if n.tag not in MOCK_SKIP and (is_mockup_marker(n.attrs.get("class")) or is_mockup_marker(n.attrs.get("id"))):
            words = len(text.split())
            return bool(text) and not (words >= 8 or (words >= 5 and text.rstrip()[-1:] in ".!?"))
    if not text:
        return False
    control = any(n.tag in ("a", "button", "label", "summary", "select", "option") for n in chain(el))
    heading = any(re.fullmatch(r"h[1-6]", n.tag) for n in chain(el))
    if re.fullmatch(r"[^\W\d_]{1,2}", text) and text not in ("i", "x", "v") and not control:
        for b in chain(el)[:3]:
            w, h = CSS.length_px(sv(b, "width")), CSS.length_px(sv(b, "height"))
            if w and h and 12 <= w <= 72 and 12 <= h <= 72 and 0.8 <= w / h <= 1.25 and \
                    (own_bg(b) is not None and alpha(own_bg(b)) > 0.1 or _bg_image(b)):
                return True
    if not heading and not control and len(text) <= 64 and \
            re.fullmatch(r"(?i)[\s·•|/,()\[\]–—-]*(?:v\d+(?:\.\d+)+\S*|(?:version|build|release|rev)\s*[:#]?\s*\S*\d\S*)"
                         r"[\s·•|/,()\[\]–—\-\w.:]*", text) and len(text.split()) <= 6:
        return True
    return False


# ─── check_colors (rules.rs) ─────────────────────────────────────────────────────────────────────────────────────────
B = r"(?<![A-Za-z0-9_])"
E = r"(?![A-Za-z0-9_])"
TW_GRAY_TEXT = re.compile(B + r"text-(?:gray|slate|zinc|neutral|stone)-\d+" + E)
TW_COLOR_BG = re.compile(B + r"bg-(?:red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|"
                         r"purple|fuchsia|pink|rose)-\d+" + E)
TW_BG_CLIP_TEXT = re.compile(B + r"bg-clip-text" + E)
TW_BG_GRADIENT_TO = re.compile(B + r"bg-gradient-to-")
TW_PURPLE_TEXT = re.compile(B + r"text-(?:purple|violet|indigo)-\d+" + E)
TW_TEXT_XL = re.compile(B + r"text-(?:[2-9]xl)" + E)
TW_FROM_PURPLE = re.compile(B + r"from-(?:purple|violet|indigo)-\d+" + E)
TW_TO_PURPLE = re.compile(B + r"to-(?:purple|violet|indigo|blue|cyan|pink|fuchsia)-\d+" + E)
STATE_VARIANTS = {"hover", "focus", "focus-visible", "focus-within", "active", "visited", "disabled", "checked",
                  "open", "enabled", "invalid", "placeholder"}


def in_state_variant(s, start):
    """rules.rs in_state_variant: hover:/group-*:/data-*: utilities paint only in that state."""
    tok_start = max(s.rfind(" ", 0, start), s.rfind("\n", 0, start), s.rfind("\t", 0, start)) + 1
    prefix = s[tok_start:start]
    if not prefix.endswith(":"):
        return False
    for v in prefix.rstrip(":").split(":"):
        v = v.lstrip("!")
        if v in STATE_VARIANTS or v.startswith(("group-", "peer-", "aria-", "data-")):
            return True
    return False


def find_gray_on_color_bg(s):
    for m in TW_COLOR_BG.finditer(s):
        if s[m.end():m.end() + 1] != "/" and not in_state_variant(s, m.start()) \
                and m.group(0).rsplit("-", 1)[1] not in ("50", "100"):
            return m.group(0)
    return None


def find_resting_gray_text(s):
    for m in TW_GRAY_TEXT.finditer(s):
        if not in_state_variant(s, m.start()) and int(m.group(0).rsplit("-", 1)[1]) < 700:
            return m.group(0)
    return None


def _readable_arg(arg, first):
    if arg.startswith("#"):
        return pc(arg.split()[0]) is not None
    m = re.match(r"(rgba?|hsla?|hwb|oklch|oklab|lch|lab|color|color-mix)\(", arg)
    if m:
        end = balanced(arg, m.end() - 1)
        return end is not None and pc(arg[:end + 1]) is not None
    if arg and " " not in arg and re.match(r"[\d.\-]", arg):
        return True
    if first and (re.match(r"(to|from|at|in) ", arg) or " at " in arg or " in " in arg
                  or any(w in arg for w in ("circle", "ellipse", "closest-", "farthest-"))
                  or re.fullmatch(r"-?[\d.]+(deg|rad|grad|turn)", arg)):
        return True
    return False


def gradient_one_colour(img):
    """rules.rs gradient_stops_are_one_colour."""
    low = img.lower()
    pos = 0
    while True:
        at = low.find("gradient(", pos)
        if at < 0:
            break
        o = at + len("gradient")
        end = balanced(low, o)
        end = len(low) if end is None else end
        args = [a.strip() for a in split_top(low[o + 1:end], ",")]
        for i, a in enumerate(args):
            if not _readable_arg(a, i == 0):
                return False
        pos = end
    stops = gradient_colors(img)
    if len(stops) < 2:
        return False
    f = stops[0]
    return all(abs(c[0] - f[0]) < 12 and abs(c[1] - f[1]) < 12 and abs(c[2] - f[2]) < 12
               and abs(alpha(c) - alpha(f)) * 255 < 12 for c in stops)


def contrast_findings(o, text):
    """rules.rs contrast_findings: gray-on-color then WCAG AA against the worst background."""
    vis = o["visible"]
    if vis is not None and alpha(vis) <= 0.02:
        return []
    bgs = [o["eff"]] if o["eff"] is not None else (o["stops"] or [])
    if not bgs:
        return []
    out = []
    if is_gray_ink(text) and all(reads_as_colour(b) for b in bgs):
        lab = hexs(o["eff"]) if o["eff"] is not None else "gradient(%s)" % ", ".join(hexs(b) for b in bgs)
        out.append({"rule": "gray-on-color", "snippet": "text %s on bg %s" % (hexs(text), lab)})
    inks = [(over(vis, b) if alpha(vis) < 1 else vis) if vis is not None else text for b in bgs]
    ratios = [contrast(i, b) for i, b in zip(inks, bgs)]
    w = ratios.index(min(ratios))
    r = ratios[w]
    large = o["fs"] >= LARGE_PX or (o["fs"] >= LARGE_BOLD_PX and o["fw"] >= 700)
    thr = 3.0 if large else 4.5
    if r < thr and not (o["eff"] is None and alpha(text) < 1):
        src = " (%s)" % o["src"] if o["src"] else ""
        hit = {"rule": "low-contrast", "snippet": "%s:1 (need %s:1) — text %s on %s%s" % (
            ratio_label(r, thr), jsnum(thr), hexs(inks[w]), hexs(bgs[w]), src)}
        sev = contrast_severity(r, thr)
        if sev:
            hit["severity"] = sev
        out.append(hit)
    return out


def bg_matches_text(o, text):
    if o["eff"] is not None:
        return hexs(o["eff"]) == hexs(text)
    return any(hexs(s) == hexs(text) for s in (o["stops"] or []))


def check_colors(o):
    tag, img, clip, text = o["tag"], o["img"], o["clip"], o["text"]
    if tag in SAFE_TAGS and not o["styled"]:
        # safe_tag_text_contrast: bare link / span text — WCAG verdict only
        if not o["paints_own"] or not o["has_direct"] or o["emoji"] or o["fs"] < 9 or tag in NON_RENDERED_TAGS \
                or clip == "text" or text is None or bg_matches_text(o, text):
            return []
        return [h for h in contrast_findings(o, text) if h["rule"] == "low-contrast"]
    out = []
    if o["has_direct"] and text is not None and not o["emoji"]:
        if clip != "text" and not o["glyph"] and not bg_matches_text(o, text):
            out += contrast_findings(o, text)
        if spread(text) >= 50 and 260 <= hue(text) <= 310 and (tag in ("h1", "h2", "h3") or o["fs"] >= 20):
            out.append({"rule": "ai-color-palette", "snippet": "Purple/violet text (%s) on heading" % hexs(text)})
    if clip == "text" and img and "gradient" in img and not gradient_one_colour(img):
        out.append({"rule": "gradient-text", "snippet": "background-clip: text + gradient"})
    cls = o["cls"]
    if cls:
        g, c = find_resting_gray_text(cls), find_gray_on_color_bg(cls)
        if g and c:
            out.append({"rule": "gray-on-color", "snippet": "%s on %s" % (g, c)})
        if TW_BG_CLIP_TEXT.search(cls) and TW_BG_GRADIENT_TO.search(cls):
            out.append({"rule": "gradient-text", "snippet": "bg-clip-text + bg-gradient (Tailwind)"})
        p = TW_PURPLE_TEXT.search(cls)
        if p and (tag in ("h1", "h2", "h3") or TW_TEXT_XL.search(cls)):
            out.append({"rule": "ai-color-palette", "snippet": "%s on heading" % p.group(0)})
        if TW_FROM_PURPLE.search(cls) and TW_TO_PURPLE.search(cls):
            out.append({"rule": "ai-color-palette", "snippet": "Purple/violet gradient (Tailwind)"})
    return out


def _clip_of(n):
    return (sv(n, "-webkit-background-clip") or sv(n, "background-clip")).strip()


def clips_to_text(v):
    layers = [x.strip() for x in v.split(",")]
    return bool(v.strip()) and all(x == "text" for x in layers)


def clipped_by_ancestor(el):
    for c in list(el.ancestors())[:12]:
        if clips_to_text(_clip_of(c)):
            return True
        b = own_bg(c)
        if b is not None and alpha(b) >= 0.95:
            return False
    return False


def inherits_scored_color(el, text):
    """adapters.rs inherits_scored_text_color: an ancestor wearing the same colour already reports it."""
    for c in list(el.ancestors())[:12]:
        if color_prop(c, "color") != text:
            return False
        d = direct_text(c)
        if d.strip():
            if emoji_only(d) or glyph_only(d):
                return False
            return c.tag not in SAFE_TAGS or not visually_hidden(c)
        b = own_bg(c)
        if b is not None and alpha(b) > 0:
            return False
    return False


def _data_svg_size(img):
    m = re.search(r"url\(\s*['\"]?(data:image/svg\+xml[^,]*),(.*?)['\"]?\s*\)\s*$", img.strip(), re.I | re.S)
    if not m or ";base64" in m.group(1).lower():
        return None
    from urllib.parse import unquote
    svg = unquote(m.group(2))
    tag = re.search(r"<svg\b[^>]*>", svg, re.I)
    if not tag:
        return None
    w = re.search(r"\bwidth\s*=\s*['\"]?([\d.]+)", tag.group(0))
    h = re.search(r"\bheight\s*=\s*['\"]?([\d.]+)", tag.group(0))
    if w and h and float(w.group(1)) > 0 and float(h.group(1)) > 0:
        return float(w.group(1)), float(h.group(1))
    vb = re.search(r"viewBox\s*=\s*['\"]\s*[-\d.]+[\s,]+[-\d.]+[\s,]+([\d.]+)[\s,]+([\d.]+)", tag.group(0))
    return (float(vb.group(1)), float(vb.group(2))) if vb else None


def _bg_is_icon(n):
    img = _bg_image(n)
    if not img or "gradient" in img.lower():
        return False
    sz = _data_svg_size(img)
    return sz is not None and sz[0] <= 32 and sz[1] <= 32


def icon_hosts(el):
    hosts = [el] if _bg_is_icon(el) else []
    for c in list(el.ancestors())[:12]:
        if c.tag == "li":
            if _bg_is_icon(c):
                hosts.append(c)
            break
    return hosts


class Seen:
    """rules.rs SafeTagTextSeen: one report per colour pair per page on the SAFE_TAGS text path."""
    def __init__(self):
        self.reported = set()

    def keep_first(self, hits, keys_of, keep):
        out = []
        for h in hits:
            keys = [(h["rule"], k) for k in keys_of(h)]
            if any(k in self.reported for k in keys) or not keep(h):
                continue
            self.reported.update(keys)
            out.append(h)
        return out


def ink_key(t):
    a = alpha(t)
    return hexs(t) if a >= 1 else "%s@%s" % (hexs(t), jsnum(round(a * 1000) / 1000))


def element_color_hits(el, seen):
    """adapters.rs check_element_colors."""
    tag = el.tag
    if sv(el, "visibility") == "hidden" or in_non_rendered(el):
        return []
    eff_op = 1.0
    for c in chain(el):
        if not eff_op > 0.02:
            break
        v = pfloat(sv(c, "opacity") or "1")
        eff_op *= 1.0 if math.isnan(v) else v
    if eff_op <= 0.02:
        return []
    d = direct_text(el)
    has_direct = bool(d.strip())
    text = color_prop(el, "color")
    icon = has_direct and is_icon_text(el, d)
    paints_own = (has_direct and tag in SAFE_TAGS and not emoji_only(d) and not icon and not visually_hidden(el)
                  and not clipped_by_ancestor(el) and not disabled(el) and not inherits_scored_color(el, text))
    icons = icon_hosts(el) if paints_own else []
    fs = font_size(el)
    raw_fs = sv(el, "font-size").strip()
    cov_px = fs if (raw_fs.endswith("px") or not raw_fs) else 9.0
    surf = walk_surface(el, 0.0, icons, cov_px)
    eff = None if surf.unresolved else surf.color
    obg = own_bg(el)
    pseudo = False
    if obg is None or alpha(obg) <= 0.5:
        ps = pseudo_surface(el)
        if ps is not None:
            obg = eff = ps
            surf.unresolved, pseudo = False, True
    stops = src = None
    if not surf.unresolved and eff is None:
        stops = text_gradient_stops(el, surf)
        if stops and surf.glabel:
            src = "gradient on " + surf.glabel
    visible = None
    if text is not None and not pseudo and not surf.unresolved:
        visible, eff = fold_opacity(el, text, surf, eff)
    if visible is None and text is not None and alpha(text) < 1:
        visible = text
    img = "none" if el in surf.skipped else (sv(el, "background-image") or "none")
    clip = _clip_of(el)
    styled = has_direct and ((obg is not None and alpha(obg) > 0.5) or "gradient" in img.lower()) and fs >= 9
    o = {"tag": tag, "text": text, "eff": eff, "stops": stops, "src": src, "visible": visible, "fs": fs,
         "fw": font_weight_raw(el), "has_direct": has_direct, "emoji": emoji_only(d), "glyph": icon,
         "paints_own": paints_own, "clip": clip, "img": img, "cls": el.attrs.get("class") or "", "styled": styled}
    hits = check_colors(o)
    lc = [h for h in hits if h["rule"] == "low-contrast"]
    decorative = bool(lc) and is_decorative(el)
    if decorative:
        for h in lc:
            h["severity"] = "advisory"
    if tag in SAFE_TAGS and not styled:
        skey = "text %s over %s [%d]" % (ink_key(text), src, surf.ghost.idx) if (src and text) else None
        pre = "decorative " if decorative else ""
        hits = seen.keep_first(hits, lambda h: [pre + h["snippet"]] + ([pre + skey] if skey else []),
                               lambda h: not scoped_ignored(el, h["rule"]) and not picture_under_text(el))
    hits += placeholder_hits(el, o)
    if disabled(el):
        hits = [h for h in hits if h["rule"] != "low-contrast"]
    return hits


# placeholder / hover rules are kept apart by our cascade: read them from the sheet here
PH_RULES = {}   # id(input node) -> [(host selector, Rule)] for the scan in progress (Node has __slots__)


def _state_rules(ctx, pattern):
    out = []
    for r in ctx.sheet.rules:
        for s in r.selectors:
            if re.search(pattern, s, re.I):
                out.append((s, r))
    return out


def placeholder_hits(el, o):
    """adapters.rs placeholder branch + rules.rs check_placeholder_colors."""
    if el.tag not in ("input", "textarea"):
        return []
    ph = (el.attrs.get("placeholder") or "").strip()
    if not ph:
        return []
    if el.tag == "input":
        t = (el.attrs.get("type") or "text").lower()
        if t in ("hidden", "checkbox", "radio", "file", "submit", "button", "image", "reset", "range", "color") \
                or (el.attrs.get("value") or "").strip():
            return []
    elif direct_text(el).strip():
        return []
    raw = None
    for sel, r in PH_RULES.get(id(el), []):
        for p, v, _ in r.decls:
            if p == "color":
                raw = v
    if raw is None:
        return []
    col = pc(CSS._resolve_vars(raw, (el.style or {}).get("__custom__") or {}))
    if col is None or alpha(col) <= 0.02:
        return []
    q = dict(o, visible=None)
    if alpha(col) < 1:
        if q["eff"] is not None:
            col = over(col, q["eff"])
        elif q["stops"]:
            best = min(q["stops"], key=lambda s: contrast(over(col, s), s))
            col = over(col, best)
            q["eff"], q["stops"] = best, None
    hits = contrast_findings(q, col)
    for h in hits:
        h["snippet"] = 'placeholder "%s" %s' % (ph, h["snippet"])
        if h["rule"] == "low-contrast" and (is_decorative(el) or field_has_label(el)):
            h["severity"] = "advisory"
    return hits


def field_has_label(f):
    def shows(e):
        return not CSS.is_hidden(e) and e.text().strip()
    fid = f.attrs.get("id")
    root = f
    while root.parent is not None:
        root = root.parent
    if fid:
        for e in root.iter():
            if e.tag == "label" and e.attrs.get("for") == fid and shows(e):
                return True
    for ref in (f.attrs.get("aria-labelledby") or "").split():
        for e in root.iter():
            if e.attrs.get("id") == ref and shows(e):
                return True
    if any(a.tag == "label" and shows(a) for a in f.ancestors()):
        return True
    cur = f
    for _ in range(3):
        prev = cur.prev_element()
        if prev is not None:
            return prev.tag == "label" and not prev.attrs.get("for") and 0 < len(prev.norm_text()) <= 80
        cur = cur.parent
        if cur is None or cur.tag in ("form", "fieldset", "body", "html", "td", "th", "li", "tr", "#document"):
            return False
    return False


def hover_hits(ctx, el, hover_rules):
    """adapters.rs check_element_hover_contrast."""
    d = direct_text(el)
    if not d.strip() or not hover_rules:
        return []
    custom = (el.style or {}).get("__custom__") or {}
    hc = hb = None
    for sel, r in hover_rules:
        base = re.sub(r":hover\b", "", sel, flags=re.I).strip()
        if not base or re.search(r"[>+~]\s*$", base) or not CSS.matches(el, base):
            continue
        for p, v, _ in r.decls:
            for lp, lv in CSS.expand(p, v):
                if lp == "color":
                    hc = CSS._resolve_vars(lv, custom)
                elif lp == "background-color":
                    hb = CSS._resolve_vars(lv, custom)
    if hc is None and hb is None:
        return []
    text = pc(hc) if hc is not None else color_prop(el, "color")
    if hc is not None and text == color_prop(el, "color") and hb is None:
        return []
    if text is None or alpha(text) < 1:
        return []
    ob = pc(hb) if hb is not None else own_bg(el)
    if ob is not None and alpha(ob) >= 0.99:
        bg = ob
    else:
        under = resolve_background(el.parent if el.parent is not None and el.parent.tag != "#document" else el)
        if under is None:
            return []
        bg = over(ob, under) if ob is not None and alpha(ob) > 0.1 else under
    if el.tag in SAFE_TAGS and not (ob is not None and alpha(ob) > 0.5):
        return []
    if emoji_only(d):
        return []
    fs, fw = font_size(el), font_weight_raw(el)
    large = fs >= LARGE_PX or (fs >= LARGE_BOLD_PX and fw >= 700)
    thr = 3.0 if large else 4.5
    r = contrast(text, bg)
    if r >= thr:
        return []
    h = {"rule": "low-contrast", "snippet": ":hover state %s:1 (need %s:1) — text %s on %s" % (
        ratio_label(r, thr), jsnum(thr), hexs(text), hexs(bg))}
    sev = contrast_severity(r, thr)
    if sev:
        h["severity"] = sev
    return [h]


def _all_elements(ctx):
    return [n for n in ctx.doc.iter() if n.style is not None] if ctx.doc is not None else []


def color_rules(ctx):
    """One pass of check_element_colors + hover over every element; cached per ctx (four rules share it)."""
    cache = getattr(ctx, "_color_hits", None)
    if cache is not None:
        return cache
    hits = []
    if ctx.doc is not None:
        ph_rules = []
        for sel, r in _state_rules(ctx, r"::?(?:-webkit-input-|-moz-)?placeholder\s*$"):
            host = re.sub(r"::?(?:-webkit-input-|-moz-)?placeholder\s*$", "", sel).rstrip()
            host = host + "*" if host.endswith((">", "+", "~")) else (host or "*")
            ph_rules.append((host, r))
        hover_rules = [(s, r) for s, r in _state_rules(ctx, r":hover\b")
                       if any(p in ("color", "background-color", "background") for p, _, _ in r.decls)]
        seen = Seen()
        PH_RULES.clear()
        for el in _all_elements(ctx):
            if el.tag in ("input", "textarea"):
                PH_RULES[id(el)] = [(h, r) for h, r in ph_rules if CSS.matches(el, h)]
            for h in element_color_hits(el, seen):
                if not scoped_ignored(el, h["rule"]):
                    h.setdefault("line", el.line)
                    hits.append(h)
        for el in _all_elements(ctx):
            for h in hover_hits(ctx, el, hover_rules):
                if not scoped_ignored(el, h["rule"]):
                    h["line"] = el.line
                    hits.append(h)
    try:
        ctx._color_hits = hits
    except AttributeError:
        pass
    return hits


def _pick(ctx, rule):
    return [h for h in color_rules(ctx) if h["rule"] == rule]


# ─── page patterns (html_patterns.rs check_html_patterns) ────────────────────────────────────────────────────────────
def enclosing_selector(text, index):
    """css scan enclosing_css_selector (None inside a style="" fragment)."""
    open_ = text.rfind("{", 0, index)
    if open_ < 0:
        return None
    if text.rfind("}", 0, index) > open_:
        return None
    before = re.sub(r"/\*.*?\*/", lambda m: " " * len(m.group(0)), text[:open_], flags=re.S)
    start = max(before.rfind("}"), before.rfind(";")) + 1
    sel = " ".join(re.sub(r"/\*.*?\*/", "", text[start:open_], flags=re.S).split())
    return sel or None


def page_hit(ctx, rule, snippet, index=None, selector=None, severity=None):
    """Drop a pattern hit whose rule selector matches only scoped-ignored elements (engine.rs:377-393)."""
    sel = selector if selector is not None else (enclosing_selector(ctx.css_text, index) if index is not None else None)
    if sel and ctx.doc is not None and not sel.startswith("@"):
        stripped = re.sub(r"::?[a-zA-Z-]+(\([^)]*\))?", "", sel).strip()
        try:
            m = [n for n in ctx.doc.iter() if any(CSS.matches(n, s) for s in CSS.split_selectors(stripped))] if stripped else []
        except Exception:
            m = []
        if m and all(scoped_ignored(n, rule) for n in m):
            return []
    h = {"rule": rule, "snippet": snippet}
    if index is not None:
        h["line"] = ctx.line_of(ctx.css_text[index:index + 40].split("\n")[0].strip()) or 0
    if severity:
        h["severity"] = severity
    return [h]


def starts_prop_token(text, start):
    def clean(at):
        return at == 0 or not (text[at - 1] == "-" or text[at - 1].isalnum() or text[at - 1] == "_" or ord(text[at - 1]) >= 0x80)
    if clean(start):
        return True
    for pre in ("-webkit-", "-moz-", "-ms-", "-o-"):
        if start >= len(pre) and text[start - len(pre):start].lower() == pre and clean(start - len(pre)):
            return True
    return False


def custom_props(text):
    out = {}
    for m in re.finditer(r"(--[A-Za-z0-9_-]+)\s*:\s*([^;{}]+)", text):
        out.setdefault(m.group(1), m.group(2).strip())
    return out


def resolve_vars(v, props, depth=0):
    if "var(" not in v or depth > 8:
        return v

    def rep(m):
        if m.group(1) in props:
            return resolve_vars(props[m.group(1)], props, depth + 1)
        if m.group(2):
            return resolve_vars(m.group(2).strip(), props, depth + 1)
        return m.group(0)
    return re.sub(r"var\(\s*(--[a-zA-Z0-9_-]+)\s*(?:,\s*([^)]+))?\)", rep, v)


DARK_BG = re.compile(r"background(?:-color)?\s*:\s*(?:#(?:0[0-9a-f]|1[0-9a-f]|2[0-3])[0-9a-f]{4}\b|#[01][0-9a-f]{2}\b|"
                     r"rgb\(\s*\d{1,2}\s*,\s*\d{1,2}\s*,\s*\d{1,2}\s*\))", re.I)
TW_DARK_BG = re.compile(B + r"bg-(?:gray|slate|zinc|neutral|stone)-(?:9\d{2}|800)" + E)
ROOT_BLOCK = re.compile(r"(?:^|[}\s,;>])(?:body|html|:root)\s*(?:,[^{]*)?\{([^}]*)\}", re.I)


def dark_root(text, props):
    """css_scan.rs css_text_has_dark_root_bg."""
    if any(starts_prop_token(text, m.start()) for m in DARK_BG.finditer(text)) or TW_DARK_BG.search(text):
        return True
    for m in ROOT_BLOCK.finditer(text):
        scope = m.group(1)
        for b in re.finditer(r"background(?:-color)?\s*:\s*([^;{}]+)", scope, re.I):
            if not starts_prop_token(scope, b.start()):
                continue
            c = pc(resolve_vars(b.group(1).strip(), props))
            if c is not None and alpha(c) > 0.5 and lum(c) < 0.1:
                return True
    return False


# ─── glow (rules.rs check_glow / css_scan.rs scan_css_text_for_glow) ─────────────────────────────────────────────────
SHADOW_FN = re.compile(r"(?:rgba?|hsla?|hwb|oklch|oklab|lch|lab|color)\([^)]*\)", re.I)
SHADOW_HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")


def find_shadow_color(layer):
    m = SHADOW_FN.search(layer) or SHADOW_HEX.search(layer)
    if m:
        return pc(m.group(0)), m.span()
    for m in re.finditer(r"[a-zA-Z]+", layer):
        if m.group(0).lower() in C.NAMED and m.group(0).lower() != "transparent":
            return pc(m.group(0)), m.span()
    return None


def shadow_lengths(layer, span):
    s = layer[:span[0]] + " " + layer[span[1]:]
    out = []
    for m in re.finditer(r"(-?\d*\.?\d+)(px|rem|em)?", s):
        v = float(m.group(1))
        out.append(v * 16 if m.group(2) in ("rem", "em") else v)
    return out


def glow_layer(value, on_dark, opacity=None):
    for layer in split_top(value, ","):
        info = find_shadow_color(layer)
        if not info or info[0] is None or spread(info[0]) < 30:
            continue
        v = shadow_lengths(layer, info[1])
        if len(v) < 3 or v[2] <= 4:
            continue
        blur, spr = v[2], v[3] if len(v) > 3 else 0.0
        if blur / 2 + spr <= 0 or blur * alpha(info[0]) * (1.0 if opacity is None else opacity) < 3.0:
            continue
        if v[0] == 0 and v[1] == 0:
            return "zero", info[0]
        if on_dark:
            return "dark", info[0]
    return None


def rule_dark_glow(ctx):
    out = []
    for el in _all_elements(ctx):
        bs, ts = own_raw(el, "box-shadow"), own_raw(el, "text-shadow")
        bs = "" if bs.strip() in ("", "none") else bs
        ts = "" if ts.strip() in ("", "none") else ts
        if not bs and not ts:
            continue
        parent = el.parent if el.parent is not None and el.parent.tag != "#document" else el
        bg = resolve_background(parent)
        on_dark = bg is not None and lum(bg) < 0.1
        op = pfloat(sv(el, "opacity")) if sv(el, "opacity") else float("nan")
        op = None if math.isnan(op) else max(0.0, min(1.0, op))
        for prop, val in (("box-shadow", bs), ("text-shadow", ts)):
            r = glow_layer(val, on_dark, op) if val else None
            if r:
                snip = ("Zero-offset %s glow (%s)" if r[0] == "zero" else "Colored %s glow (%s) on dark background") % (prop, hexs(r[1]))
                if not scoped_ignored(el, "dark-glow"):
                    out.append({"rule": "dark-glow", "snippet": snip, "line": el.line})
                break
    if ctx.full_page:
        text = ctx.css_text
        props = custom_props(text)
        dark = dark_root(text, props)
        for m in re.finditer(r"(?<![A-Za-z0-9_])(box-shadow|text-shadow)\s*:\s*([^;{}]+)", text, re.I):
            if not starts_prop_token(text, m.start(1)):
                continue
            r = glow_layer(resolve_vars(m.group(2).strip(), props), dark)
            if r:
                prop = m.group(1).lower()
                snip = ("Zero-offset %s glow (%s)" if r[0] == "zero" else "Colored %s glow (%s) on dark page") % (prop, hexs(r[1]))
                out += page_hit(ctx, "dark-glow", snip, m.start())
                break
    return out


# ─── radial-halo (css_scan.rs scan_css_text_for_radial_halo_with) ────────────────────────────────────────────────────
HALO_TOK = re.compile(r"(?:rgba?|hsla?|oklch|oklab|lab|lch|hwb|color-mix)\([^)]*(?:\([^)]*\))?[^)]*\)|"
                      r"#[0-9a-fA-F]{3,8}\b|\btransparent\b", re.I)


def _tok_color(tok):
    return (0.0, 0.0, 0.0, 0.0) if tok.lower() == "transparent" else pc(tok)


def rule_radial_halo(ctx):
    if not ctx.full_page:
        return []
    text = ctx.css_text
    props = custom_props(text)
    if not dark_root(text, props):
        return []
    for m in re.finditer(r"background(?:-image)?\s*:\s*([^;{}]+)", text, re.I):
        if not starts_prop_token(text, m.start()):
            continue
        v = resolve_vars(m.group(1).strip(), props)
        if re.search(r"url\s*\(", v, re.I):
            continue
        for g in re.finditer(r"(repeating-)?radial-gradient\(", v, re.I):
            if g.group(1):
                continue
            end = balanced(v, g.end() - 1)
            if end is None:
                break
            args = split_top(v[g.end():end], ",")
            stops = [a for a in args if HALO_TOK.search(a)]
            if len(args) < 2 or len(stops) < 2:
                continue
            if any((p := re.search(r"(-?[0-9.]+)px\b", s)) and abs(pf0(p.group(1))) <= 24 for s in stops):
                continue
            last = _tok_color(HALO_TOK.search(stops[-1]).group(0))
            if last is None or alpha(last) > 0.05:
                continue
            ft = HALO_TOK.search(stops[0]).group(0)
            first = None if ft.lower() == "transparent" else pc(ft)
            if first is None or alpha(first) < 0.7 or spread(first) < 24:
                continue
            return page_hit(ctx, "radial-halo", "radial-gradient halo (%s → transparent) on dark page" % hexs(first),
                            m.start())
    return []


# ─── radial-spotlight-glow (adapters.rs check_element_radial_spotlight + measures.rs) ────────────────────────────────
def _stop_from_arg(arg):
    m = HALO_TOK.search(arg)
    if not m:
        return None, False
    if m.group(0).lower() == "transparent":
        return None, True
    c = pc(m.group(0))
    return c, c is not None and alpha(c) <= 0.05


def spotlight_stops(value):
    for g in re.finditer(r"(repeating-)?radial-gradient\(", value, re.I):
        if g.group(1):
            continue
        end = balanced(value, g.end() - 1)
        if end is None:
            return []
        args = [a for a in split_top(value[g.end():end], ",") if HALO_TOK.search(a)]
        if len(args) < 2:
            return []
        stops = [_stop_from_arg(a) for a in args]
        lc, lt = stops[-1]
        if (0.0 if lt else alpha(lc) if lc else 1.0) > 0.05:
            return []
        colored = [c for c, t in stops if not t and c is not None and alpha(c) > 0.05]
        if not colored or len(colored) > 2 or any(alpha(c) >= 0.45 for c in colored):
            return []
        return [c for c in colored if spread(c) >= 24]
    return []


def _layer_mean(layer):
    o = layer.find("(", layer.lower().find("gradient("))
    end = balanced(layer, o)
    if end is None:
        return None
    stops = []
    for arg in split_top(layer[o + 1:end], ","):
        if HALO_TOK.search(arg):
            c, t = _stop_from_arg(arg)
            if c is not None:
                stops.append(c)
            elif t:
                stops.append((0.0, 0.0, 0.0, 0.0))
        else:
            c = pc(arg.split()[0]) if arg.split() else None
            if c is not None:
                stops.append(c)
    if not stops:
        return None
    a = sum(alpha(s) for s in stops)
    if a <= 0:
        return (0.0, 0.0, 0.0, 0.0)
    return tuple(sum(s[i] * alpha(s) for s in stops) / a for i in range(3)) + (a / len(stops),)


def backdrop(el, beneath):
    """measures.rs BackdropStack painted from the glow element up; None when an image or unread colour is in the way."""
    overlays, image, cur = [], beneath, el

    def push(p):
        a = alpha(p)
        if a <= 0.01:
            return None
        if a >= 0.99:
            acc = p[:3] + (1.0,)
            for o in reversed(overlays):
                acc = over(o, acc)
            return acc
        overlays.append(p)
        return None
    while cur is not None and cur.tag != "#document":
        img = image if image is not None else _bg_image(cur)
        image = None
        if img.strip():
            layers, clear, means = split_top(img, ","), 1.0, []
            for layer in layers:
                if clear <= 0.01:
                    break
                low = layer.lower()
                if "gradient(" in low:
                    mean = _layer_mean(layer)
                    if mean is None:
                        return None
                    clear *= 1 - alpha(mean)
                    means.append(mean)
                elif re.search(r"url\(|image\(|image-set\(|element\(|cross-fade\(", low):
                    return None
            r = g = b = a = 0.0
            for l in reversed(means):
                la = alpha(l)
                r, g, b, a = l[0] * la + r * (1 - la), l[1] * la + g * (1 - la), l[2] * la + b * (1 - la), la + a * (1 - la)
            if a > 0.01:
                res = push((r / a, g / a, b / a, a))
                if res:
                    return res
        col = color_prop(cur, "background-color")
        raw = sv(cur, "background-color").strip().lower()
        if col is not None:
            res = push(col)
            if res:
                return res
        elif raw not in NO_PAINT:
            return None
        cur = cur.parent
    acc = WHITE
    for o in reversed(overlays):
        acc = over(o, acc)
    return acc


def rule_radial_spotlight(ctx):
    out = []
    for el in _all_elements(ctx):
        img = sv(el, "background-image")
        val = img if re.search("radial-gradient", img, re.I) else ""
        if not val and re.search("radial-gradient", sv(el, "background"), re.I):
            val = sv(el, "background")
        if not val:
            continue
        stops = spotlight_stops(val)
        w, h = pf0(sv(el, "width")), pf0(sv(el, "height"))
        if not stops or not (w >= 240 and h >= 160):
            continue
        op = 1.0
        for c in chain(el):
            v = pfloat(sv(c, "opacity"))
            if not math.isnan(v):
                op *= max(0.0, min(1.0, v))
            if op <= 0.02:
                op = 0.0
                break
        layers = split_top(val, ",")
        gi = next((i for i, l in enumerate(layers) if "radial-gradient(" in l.lower()
                   and "repeating-radial-gradient(" not in l.lower()), None)
        bd = backdrop(el, ", ".join(layers[gi + 1:]) if gi is not None else "")
        best = None
        for s in stops:
            e = alpha(s) * op
            if e < 0.14:
                continue
            if bd is not None:
                r = contrast(over(s[:3] + (e,), bd), bd)
                if r < 1.30:
                    continue
                sc = r
            else:
                sc = e
            if best is None or sc > best[1]:
                best = (s, sc)
        if best is None or not behind_text(el):
            continue
        label = el.attrs.get("data-name") or el.attrs.get("id") or (el.classes[0] if el.classes else el.tag)
        s = best[0]
        snip = 'radial-gradient spotlight glow "%s" (%s a%s → transparent) on %sx%s surface' % (
            label, hexs(s), to_fixed(alpha(s), 2), jsnum(math.floor(w + 0.5)), jsnum(math.floor(h + 0.5)))
        if not scoped_ignored(el, "radial-spotlight-glow"):
            out.append({"rule": "radial-spotlight-glow", "snippet": snip, "line": el.line})
    return out


def behind_text(el):
    if el.norm_text():
        return True
    if sv(el, "position") not in ("absolute", "fixed"):
        return False
    return any(a.norm_text() for a in list(el.ancestors())[:8])


# ─── cream-palette (page.rs check_cream_palette) ─────────────────────────────────────────────────────────────────────
TAILWIND_BG_HEX = [("bg-amber-50", "#fffbeb"), ("bg-amber-100", "#fef3c7"), ("bg-orange-50", "#fff7ed"),
                   ("bg-orange-100", "#ffedd5"), ("bg-yellow-50", "#fefce8"), ("bg-stone-50", "#fafaf9"),
                   ("bg-stone-100", "#f5f5f4"), ("bg-stone-200", "#e7e5e4")]


def is_cream(c):
    return c is not None and min(c[:3]) >= 209 and c[0] >= c[1] >= c[2] and 6 <= c[0] - c[2] <= 48


def cream_from_class(cls):
    m = re.search(B + r"bg-\[([^\]]+)\]", cls or "")
    if m and is_cream(pc(m.group(1).replace("_", " "))):
        return "bg-[%s]" % m.group(1)
    toks = (cls or "").split()
    for tok, hx in TAILWIND_BG_HEX:
        if tok in toks and is_cream(pc(hx)):
            return tok
    return None


def rule_cream(ctx):
    if not ctx.full_page or ctx.doc is None:
        return []
    body = next((n for n in ctx.doc.iter() if n.tag == "body"), None)
    html = next((n for n in ctx.doc.iter() if n.tag == "html"), None)
    if body is None:
        return []
    bg = own_bg(body)
    if (bg is None or alpha(bg) == 0) and html is not None:
        bg = own_bg(html)
    if is_cream(bg):
        return [{"rule": "cream-palette", "snippet": "cream/beige page background rgb(%s, %s, %s)" % tuple(
            jsnum(v) for v in bg[:3]), "line": body.line}]
    for el in (body, html):
        tok = cream_from_class(el.attrs.get("class") if el is not None else "")
        if tok:
            return [{"rule": "cream-palette", "snippet": "cream/beige page background (Tailwind %s)" % tok}]
    return []


# ─── buried-raster (quality.rs check_quality + css_scan.rs scan_css_text_for_buried_raster) ──────────────────────────
def url_is_svg(u):
    u = u.strip().strip("'\"").lower()
    if u.startswith("data:"):
        return u.startswith("data:image/svg+xml")
    return re.split(r"[?#]", u)[0].endswith(".svg")


def raster_is_svg(is_img, src, bg):
    if is_img:
        return bool(src) and url_is_svg(src)
    urls = re.findall(r"url\(([^)]*)\)", bg, re.I)
    return bool(urls) and all(url_is_svg(u) for u in urls)


BURIED_GRAD = re.compile(r"(?:linear|radial|conic)-gradient\([^()]*(?:\([^()]*\)[^()]*)*\)", re.I)
BURIED_ALPHA = re.compile(r"rgba?\(\s*[0-9.]+%?\s*,?\s*[0-9.]+%?\s*,?\s*[0-9.]+%?\s*(?:[,/]\s*([0-9.]+%?))?\s*\)|"
                          r"hsla?\([^)]*?(?:[,/]\s*([0-9.]+%?))?\s*\)", re.I)


def _blend_not_normal(rule, prop):
    for m in re.finditer(prop + r"\s*:", rule, re.I):
        after = rule[m.end():]
        ws = len(after) - len(after.lstrip())
        if ws or not after.lower().startswith("normal"):
            return True
    return False


def rule_buried_raster(ctx):
    out = []
    for el in _all_elements(ctx):
        if (el.attrs.get("id") or "").startswith(("claude-", "cic-")):
            continue
        raw = sv(el, "opacity")
        op = pfloat(raw)
        if not raw.strip() or math.isnan(op) or not 0 <= op < 0.15:
            continue
        bg = sv(el, "background-image")
        is_img = el.tag == "img"
        if not (is_img or re.search(r"url\(", bg, re.I)) or raster_is_svg(is_img, el.attrs.get("src"), bg):
            continue
        lab = (el.attrs.get("alt") or "") if is_img else el.text().strip()[:40]
        snip = "%s at opacity %s%s" % ("<img>" if is_img else "raster background", jsnum(op), ' "%s"' % lab if lab else "")
        if not scoped_ignored(el, "buried-raster"):
            out.append({"rule": "buried-raster", "snippet": snip, "line": el.line})
    if not ctx.full_page:
        return out
    text = ctx.css_text
    for m in re.finditer(r"background(?:-image)?\s*:\s*([^;}]+)", text, re.I):
        val = m.group(1)
        if not re.search(r"url\(", val, re.I) or not re.search(r"gradient\(", val, re.I):
            continue
        rs = text.rfind("{", 0, m.start())
        re_ = text.find("}", m.start())
        rule = text[max(rs, 0):re_ if re_ >= 0 else len(text)]
        if _blend_not_normal(rule, r"background-blend-mode") or _blend_not_normal(rule, r"mix-blend-mode"):
            continue
        first_url = re.search(r"url\(", val, re.I).start()
        washed = False
        for g in BURIED_GRAD.finditer(val):
            if g.start() >= first_url:
                continue
            gs = g.group(0)
            alphas = []
            for a in BURIED_ALPHA.finditer(gs):
                t = a.group(1) or a.group(2)
                alphas.append(1.0 if t is None else (pf0(t) / 100 if t.endswith("%") else pf0(t)))
            stripped = re.sub(r"(?:rgba?|hsla?)\([^)]*\)", "", gs, flags=re.I)
            for h in re.finditer(r"#([0-9a-fA-F]{3,8})\b", stripped):
                hx = h.group(1)
                alphas.append(int(hx[3] * 2, 16) / 255 if len(hx) == 4 else int(hx[6:], 16) / 255 if len(hx) == 8 else 1.0)
            if re.search(r"\b(?:white|black|ivory|beige|linen|snow|cream)\b", stripped, re.I):
                alphas.append(1.0)
            if alphas and all(a >= 0.9 for a in alphas):
                washed = True
                break
        if washed:
            out += page_hit(ctx, "buried-raster", "raster under a near-opaque gradient wash: %s" % val.strip()[:90],
                            m.start())
    return out


# ─── repeating-stripes-gradient (html_patterns.rs repeating_gradient_repeats) ────────────────────────────────────────
def _split_top_stop(s, ws):
    """css_scan split_top_level: stop at the ')' closing the enclosing function."""
    parts, depth, start = [], 0, 0
    for i, ch in enumerate(s):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                parts.append(s[start:i])
                return [p.strip() for p in parts if p.strip()]
        elif depth == 0 and ((ws and ch.isspace()) or (not ws and ch == ",")):
            parts.append(s[start:i])
            start = i + 1
    parts.append(s[start:])
    return [p.strip() for p in parts if p.strip()]


def _grad_pos(tok):
    t = "".join(tok.split())
    while t.startswith("calc(") and t.endswith(")"):
        t = t[5:-1]
    m = re.match(r"([-+\d.]+)(.*)$", t)
    if not m:
        return None
    try:
        n = float(m.group(1))
    except ValueError:
        return None
    if n == 0:
        return 0.0
    full = {"%": 100.0, "deg": 360.0, "grad": 400.0, "turn": 1.0}.get(m.group(2))
    return n / full if full else None


def repeats(args, radial):
    stops = _split_top_stop(args, False)
    toks = lambda s: [t.lower() for t in _split_top_stop(s, True)]
    first_toks = toks(stops[0]) if stops else []
    if first_toks and (pc(first_toks[0]) is not None or first_toks[0] in ("transparent", "currentcolor")):
        fi = 0
    elif first_toks and "var(" in first_toks[0]:
        return True
    else:
        fi = 1
    if len(stops) < fi + 2:
        return True
    if radial and fi == 1:
        pre, i = toks(stops[0]), 0
        while i < len(pre):
            if pre[i] == "at":
                i += 1
                while i < len(pre) and pre[i] != "in":
                    i += 1
            elif pre[i] == "in":
                i += 2
                if i + 1 < len(pre) and pre[i + 1] == "hue":
                    i += 2
            elif pre[i] in ("circle", "ellipse", "farthest-corner"):
                i += 1
            else:
                return True
    first, last = toks(stops[fi]), toks(stops[-1])
    if len(last) == 1 and "var(" in last[0]:
        return True
    starts = len(first) < 2 or _grad_pos(first[1]) == 0.0
    ends = len(last) == 1 or _grad_pos(last[-1]) == 1.0
    return not (starts and ends)


def rule_stripes(ctx):
    if not ctx.full_page:
        return []
    text = ctx.css_text
    for m in re.finditer(r"repeating-(?:linear|radial|conic)-gradient\s*\(", text, re.I):
        if repeats(text[m.end():], "radial" in m.group(0).lower()):
            return page_hit(ctx, "repeating-stripes-gradient", "repeating-gradient decorative stripes", m.start())
    return []


# ─── codex-grid-background (css_scan.rs scan_css_text_for_grid_background) ───────────────────────────────────────────
HAIR = re.compile(r"\b\d{1,3}px\s*,\s*transparent\s+\d{1,3}px", re.I)
INV_HAIR = re.compile(r"transparent\s+calc\(100%\s*-\s*\d{1,3}px\)", re.I)
SIZE_PX = re.compile(r"background-size\s*:[^;{}\"']*\b\d{1,3}px\b", re.I)


def rule_grid(ctx):
    if not ctx.full_page:
        return []
    text = ctx.css_text
    for b in re.finditer(r"\{([^{}]*)\}|style\s*=\s*\"([^\"]*)\"|style\s*=\s*'([^']*)'", text, re.I):
        blk = b.group(1) or b.group(2) or b.group(3) or ""
        n, joined = 0, ""
        for d in re.finditer(r"\bbackground(?:-image)?\s*:\s*([^;{}\"']*)", blk, re.I):
            n += len(HAIR.findall(d.group(1))) + len(INV_HAIR.findall(d.group(1)))
            joined += d.group(1) + ";"
        if n >= 2 and (SIZE_PX.search(blk) or re.search(r"/\s*\d{1,3}px\b", joined)):
            return page_hit(ctx, "codex-grid-background", "two-axis grid-line gradient background", b.start())
    return []


# ─── organic-clip-path (css_scan.rs scan_css_text_for_organic_clip_path) ─────────────────────────────────────────────
def _coord_key(t):
    k = "".join(t.split()).lower()
    m = re.match(r"[-+\d.]*", k)
    try:
        if m.group(0) and float(m.group(0)) == 0:
            return "0"
    except ValueError:
        pass
    return k


def _vertices(body):
    out = []
    for i, point in enumerate(_split_top_stop(body, False)):
        c = _split_top_stop(point, True)
        if i == 0 and len(c) == 1 and c[0].lower() in ("nonzero", "evenodd"):
            continue
        if len(c) != 2:
            return None
        out.append(c)
    return out


def polygon_rectilinear(body):
    v = _vertices(body)
    if not v or len(v) < 3:
        return False
    k = [(_coord_key(x), _coord_key(y)) for x, y in v]
    return all(k[i][0] == k[(i + 1) % len(k)][0] or k[i][1] == k[(i + 1) % len(k)][1] for i in range(len(k)))


def _num_unit(t):
    m = re.fullmatch(r"([-+\d.]+)([a-z%]*)", t.strip().lower())
    if not m:
        return None
    try:
        v = float(m.group(1))
    except ValueError:
        return None
    return v, ("" if v == 0 else m.group(2))


def _teeth(along, step, across):
    n, swings, last = len(along), 0, None
    for i in range(n):
        j = (i + 1) % n
        if abs(abs(along[j] - along[i]) - step) > 0.5:
            last = None
            continue
        sw = across[j] - across[i]
        if abs(sw) < 0.01:
            continue
        if last is not None and (math.copysign(1, last) == math.copysign(1, sw) or abs(abs(last) - abs(sw)) > 0.5):
            return False
        last = sw
        swings += 1
    return swings >= 3


def polygon_zigzag(body):
    v = _vertices(body)
    if not v:
        return False
    xs, ys = [], []
    for x, y in v:
        a, b = _num_unit(x), _num_unit(y)
        if a is None or b is None:
            return False
        xs.append(a)
        ys.append(b)
    one = lambda arr: len({u for _, u in arr if u}) <= 1
    if len(xs) < 3 or not one(xs) or not one(ys):
        return False

    def distinct(arr):
        d = []
        for n, _ in arr:
            if not any(abs(x - n) < 0.01 for x in d):
                d.append(n)
        return sorted(d)
    even = lambda d: len(d) >= 3 and (d[1] - d[0]) > 0 and all(abs((d[i + 1] - d[i]) - (d[1] - d[0])) <= 0.5 for i in range(len(d) - 1))
    dx, dy = distinct(xs), distinct(ys)
    xv, yv = [n for n, _ in xs], [n for n, _ in ys]
    return (2 <= len(dx) <= 4 and even(dy) and _teeth(yv, dy[1] - dy[0], xv)) or \
        (2 <= len(dy) <= 4 and even(dx) and _teeth(xv, dx[1] - dx[0], yv))


def _cubic(p0, p1, p2, p3):
    out = []
    for k in range(1, 16):
        t = k / 16
        u = 1 - t
        a, b, c, d = u ** 3, 3 * u * u * t, 3 * u * t * t, t ** 3
        out.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return out


def _arc(frm, rx, ry, rot, large, sweep, to):
    rx, ry = abs(rx), abs(ry)
    if frm == to or rx == 0 or ry == 0:
        return []
    phi = math.radians(rot)
    sn, cs = math.sin(phi), math.cos(phi)
    dx, dy = (frm[0] - to[0]) / 2, (frm[1] - to[1]) / 2
    x1, y1 = cs * dx + sn * dy, -sn * dx + cs * dy
    lam = x1 * x1 / (rx * rx) + y1 * y1 / (ry * ry)
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx * rx * ry * ry - rx * rx * y1 * y1 - ry * ry * x1 * x1
    den = rx * rx * y1 * y1 + ry * ry * x1 * x1
    coef = 0 if den == 0 else math.sqrt(max(num / den, 0))
    if large == sweep:
        coef = -coef
    cx1, cy1 = coef * rx * y1 / ry, -coef * ry * x1 / rx
    cx, cy = cs * cx1 - sn * cy1 + (frm[0] + to[0]) / 2, sn * cx1 + cs * cy1 + (frm[1] + to[1]) / 2
    th1 = math.atan2((y1 - cy1) / ry, (x1 - cx1) / rx)
    delta = math.atan2((-y1 - cy1) / ry, (-x1 - cx1) / rx) - th1
    if sweep and delta < 0:
        delta += 2 * math.pi
    elif not sweep and delta > 0:
        delta -= 2 * math.pi
    out = []
    for k in range(1, 16):
        t = th1 + delta * k / 16
        ex, ey = rx * math.cos(t), ry * math.sin(t)
        out.append((cs * ex - sn * ey + cx, sn * ex + cs * ey + cy))
    return out


def path_rounded_rect(body):
    """css_scan.rs path_is_rounded_rectangle: straight sides on all four bbox edges, curves only turning corners."""
    data = body.split(")")[0].replace("&quot;", '"')
    i = data.find(",")
    if i >= 0 and data[:i].strip().lower() in ("nonzero", "evenodd"):
        data = data[i + 1:]
    data = data.strip("\"' \t\n")
    toks = re.findall(r"[A-Za-z]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", data)
    pts, segs = [], []
    cur = start = (0.0, 0.0)
    lc = lq = None
    k, cmd = 0, None
    ar = {"M": 2, "L": 2, "T": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "A": 7}
    while k < len(toks):
        t = toks[k]
        if t.isalpha():
            cmd = t
            k += 1
            if t in "Zz":
                lc = lq = None
                if cur != start:
                    segs.append((cur, start, True))
                cur = start
                pts.append(cur)
                cmd = None
            continue
        if cmd is None or cmd.upper() not in ar:
            return False
        n = ar[cmd.upper()]
        if k + n > len(toks):
            return False
        try:
            a = [float(x) for x in toks[k:k + n]]
        except ValueError:
            return False
        k += n
        rel = cmd.islower()
        base = cur if rel else (0.0, 0.0)
        U = cmd.upper()
        if U == "H":
            end = (cur[0] + a[0] if rel else a[0], cur[1])
        elif U == "V":
            end = (cur[0], cur[1] + a[0] if rel else a[0])
        else:
            end = (base[0] + a[n - 2], base[1] + a[n - 1])
        at = lambda j: (base[0] + a[j], base[1] + a[j + 1])
        refl = lambda c: cur if c is None else (2 * cur[0] - c[0], 2 * cur[1] - c[1])
        nc = nq = None
        lerp = lambda p, q, f: (p[0] + (q[0] - p[0]) * f, p[1] + (q[1] - p[1]) * f)
        if U == "C":
            pts += _cubic(cur, at(0), at(2), end)
            nc = at(2)
        elif U == "S":
            pts += _cubic(cur, refl(lc), at(0), end)
            nc = at(0)
        elif U in ("Q", "T"):
            c = at(0) if U == "Q" else refl(lq)
            pts += _cubic(cur, lerp(cur, c, 2 / 3), lerp(end, c, 2 / 3), end)
            nq = c
        elif U == "A":
            pts += _arc(cur, a[0], a[1], a[2], a[3] != 0, a[4] != 0, end)
        lc, lq = nc, nq
        if U == "M":
            start = end
            cmd = "l" if rel else "L"
        elif U in ("L", "H", "V"):
            segs.append((cur, end, True))
        else:
            segs.append((cur, end, False))
        cur = end
        pts.append(cur)
    lines = [(s[0], s[1]) for s in segs if s[2]]
    if len(lines) < 4 or not pts:
        return False
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    mnx, mxx, mny, mxy = min(xs), max(xs), min(ys), max(ys)
    tol = 0.01 * max(mxx - mnx, mxy - mny, 1.0)
    near = lambda p, q: abs(p - q) <= tol
    edges = [False] * 4
    for p, q in lines:
        if near(p[1], mny) and near(q[1], mny):
            edges[0] = True
        elif near(p[0], mxx) and near(q[0], mxx):
            edges[1] = True
        elif near(p[1], mxy) and near(q[1], mxy):
            edges[2] = True
        elif near(p[0], mnx) and near(q[0], mnx):
            edges[3] = True
        else:
            return False
    if not all(edges):
        return False

    def on(p):
        return [e for e, ok in enumerate((near(p[1], mny), near(p[0], mxx), near(p[1], mxy), near(p[0], mnx))) if ok]
    fl = next(i for i, s in enumerate(segs) if s[2])
    run = None
    for j in range(1, len(segs) + 1):
        s = segs[(fl + j) % len(segs)]
        if s[2]:
            if run:
                ea, eb = on(run[0]), on(run[1])
                if not any(x % 2 != y % 2 for x in ea for y in eb):
                    return False
                run = None
        else:
            run = (run[0], s[1]) if run else (s[0], s[1])
    return True


CLIP_RE = re.compile(r"clip-path\s*:\s*(polygon|path)\s*\(([^)]*(?:\)[^;}]*)?)", re.I)


def rule_organic(ctx):
    if not ctx.full_page:
        return []
    text, out, seen = ctx.css_text, [], set()
    for m in CLIP_RE.finditer(text):
        kind, body = m.group(1).lower(), m.group(2)
        sel = enclosing_selector(text, m.start())
        if kind == "path":
            n = len(re.findall("[CSQTAcsqta]", body))
            if n < 3 or path_rounded_rect(body):
                continue
            snip = "clip-path: path() with %d curve segments" % n
        else:
            pts = [p.strip() for p in body.split(",") if p.strip()]
            if len(pts) < 10:
                continue
            off = 0
            for p in pts:
                for nm in re.findall(r"-?[0-9.]+", p):
                    v = pf0(nm)
                    if abs(v - math.floor(v / 25 + 0.5) * 25) > 0.5:
                        off += 1
            if off < len(pts) or polygon_rectilinear(body) or polygon_zigzag(body):
                continue
            snip = "clip-path: polygon() with %d vertices approximating an organic contour" % len(pts)
        if (snip, sel) in seen:
            continue
        seen.add((snip, sel))
        out += page_hit(ctx, "organic-clip-path", snip, m.start(), selector=sel)
    return out


# ─── gradient-text / ai-color-palette page forms ─────────────────────────────────────────────────────────────────────
PURPLE_HEX = re.compile(r"#(?:7c3aed|8b5cf6|a855f7|9333ea|7e22ce|6d28d9|6366f1|764ba2|667eea)\b", re.I)
PURPLE_TEXT = re.compile(r"(?:\A|;)" + WS + r"*color" + WS + r"*:" + WS + r"*(?:.*?)#(?:7c3aed|8b5cf6|a855f7|9333ea|"
                         r"7e22ce|6d28d9)|gradient.*?#(?:7c3aed|8b5cf6|a855f7|764ba2|667eea)", re.I)


def ctx_one_colour(ctx_text):
    depth = 0
    for ch in ctx_text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return False
    low, found, pos = ctx_text.lower(), 0, 0
    while True:
        i = low.find("gradient(", pos)
        if i < 0:
            break
        o = i + len("gradient")
        close = balanced(ctx_text, o)
        if close is None:
            return False
        if not gradient_one_colour("linear-gradient" + ctx_text[o:close + 1]):
            return False
        found += 1
        pos = close + 1
    return found > 0


def rule_gradient_text(ctx):
    out = _pick(ctx, "gradient-text")
    if ctx.full_page:
        text = ctx.css_text
        for m in re.finditer(r"(?:-webkit-)?background-clip\s*:\s*text", text, re.I):
            win = text[max(0, m.start() - 200):m.end() + 200]
            if re.search("gradient", win, re.I) and not ctx_one_colour(win):
                out += page_hit(ctx, "gradient-text", "background-clip: text + gradient", m.start())
                break
        if TW_BG_CLIP_TEXT.search(ctx.class_text) and TW_BG_GRADIENT_TO.search(ctx.class_text):
            out.append({"rule": "gradient-text", "snippet": "bg-clip-text + bg-gradient (Tailwind)"})
    return out


def rule_ai_palette(ctx):
    out = _pick(ctx, "ai-color-palette")
    if ctx.full_page and PURPLE_HEX.search(ctx.css_text):
        m = PURPLE_TEXT.search(ctx.css_text)
        if m:
            out += page_hit(ctx, "ai-color-palette", "Purple/violet accent colors detected", m.start() + 1)
    return _drop_declared_purple(ctx, out)


def _drop_declared_purple(ctx, hits):
    """design_system.rs drop_declared_purple_findings: a DESIGN.md purple switches the purple forms off."""
    cols = (ctx.design or {}).get("colors") if isinstance(ctx.design, dict) else None
    if not isinstance(cols, dict):
        return hits
    for v in cols.values():
        c = pc(str(v))
        if c is not None and spread(c) >= 30 and 250 <= hue(c) <= 320:
            return [h for h in hits if not re.search("purple|violet|indigo", h["snippet"], re.I)]
    return hits


# ─── design-system-color (static_engine.rs collect_static_design_system_findings + ds.rs source scan) ────────────────
DS_COLOR_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]+\)|oklch\([^)]+\)|hsla?\([^)]+\)", re.I)
DS_STYLE_CTX = re.compile(r"(?:^|[{\s;\"'`(,])(?:color|background(?:-color|-image)?|border(?:-(?:top|right|bottom|left))?"
                          r"(?:-color)?|outline(?:-color)?|box-shadow|text-shadow|fill|stroke)\s*:\s*[^;{}\"'`]*$", re.I)
DS_FN_CTX = re.compile(r"(?:linear-gradient|radial-gradient|conic-gradient|color-mix)\([^)]*$", re.I)


def _ds_allowed(ctx):
    cols = (ctx.design or {}).get("colors") if isinstance(ctx.design, dict) else None
    if not isinstance(cols, dict):
        return None
    allowed = [c for c in (pc(str(v)) for v in cols.values()) if c is not None]
    return allowed or None


def _ds_ok(raw, allowed):
    t = raw.strip().lower()
    if t in ("", "transparent", "currentcolor", "inherit", "initial") or "var(" in t:
        return True
    c = pc(t)
    if c is None or alpha(c) <= 0.05:
        return True
    return any(max(abs(c[i] - a[i]) for i in range(3)) <= 6 for a in allowed)


def rule_design_color(ctx):
    allowed = _ds_allowed(ctx)
    if allowed is None:
        return []
    out, keys = [], set()

    def add(snip, value, line):
        c = pc(value)
        key = "%d,%d,%d" % tuple(c[:3]) if c else value.lower()
        if key not in keys:
            keys.add(key)
            out.append({"rule": "design-system-color", "snippet": snip, "line": line})
    for el in _all_elements(ctx):
        if el.tag in ("head", "title", "meta", "link", "style", "script", "noscript", "template", "source") or CSS.is_hidden(el):
            continue
        if any(n.attrs.get("aria-hidden") == "true" for n in chain(el)):
            continue
        checks = []
        if direct_text(el).strip():
            checks.append(("text color", sv(el, "color")))
        b = sv(el, "background-color")
        bc = pc(b)
        if b.strip() and not (bc is not None and alpha(bc) <= 0.05) and b.strip().lower() != "transparent":
            checks.append(("background", b))
        for side in ("top", "right", "bottom", "left"):
            w = CSS.length_px(sv(el, "border-%s-width" % side))
            if w and w > 0 and sv(el, "border-%s-style" % side) not in ("", "none", "hidden"):
                checks.append(("border-" + side, sv(el, "border-%s-color" % side)))
        for kind, raw in checks:
            label = " ".join(raw.split())
            if not label or _ds_ok(label, allowed):
                continue
            txt = " ".join(el.text().split())
            sample = ' "%s"' % txt[:40] if txt else ""
            add("%s %s on %s%s is outside DESIGN.md colors" % (kind, label, el.tag, sample), label, el.line)
    for i, line in enumerate(ctx.text.split("\n"), 1):
        if line.strip().startswith(("//", "/*", "*", "<!--")):
            continue
        for m in DS_COLOR_RE.finditer(line):
            before = line[:m.start()]
            if m.group(0).startswith("#") and (before.endswith("&") or (before.rstrip()[-1:] == ">" and line[m.end():].lstrip()[:1] == "<")):
                continue
            if not (DS_STYLE_CTX.search(before) or DS_FN_CTX.search(before)):
                continue
            raw = " ".join(m.group(0).split())
            if not _ds_ok(raw, allowed):
                add("Undocumented color %s is outside DESIGN.md colors" % raw, raw, i)
    return out


RULES = {
    "low-contrast": lambda ctx: _pick(ctx, "low-contrast"),
    "gray-on-color": lambda ctx: _pick(ctx, "gray-on-color"),
    "gradient-text": rule_gradient_text,
    "ai-color-palette": rule_ai_palette,
    "cream-palette": rule_cream,
    "dark-glow": rule_dark_glow,
    "radial-halo": rule_radial_halo,
    "radial-spotlight-glow": rule_radial_spotlight,
    "design-system-color": rule_design_color,
    "buried-raster": rule_buried_raster,
    "repeating-stripes-gradient": rule_stripes,
    "codex-grid-background": rule_grid,
    "organic-clip-path": rule_organic,
}
