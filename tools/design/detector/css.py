"""css.py — CSS parsing, selector matching and a static cascade with inheritance and var() resolution (stdlib).

Static means "the page at rest on a desktop viewport": rules under :hover/:focus/:active and similar state
pseudo-classes do not apply, @media blocks apply unless they are print-only or max-width below 768px, ::before/::after
rules are kept apart on Node.pseudo. Values are kept as strings; helpers below turn them into px / colours.
"""
import re

from . import color as C

INHERITED = {"color", "font-family", "font-size", "font-style", "font-weight", "line-height", "letter-spacing",
             "text-align", "text-transform", "visibility", "white-space", "word-spacing", "hyphens", "font-variant",
             "text-shadow", "cursor", "direction", "-webkit-text-fill-color", "font-variant-caps"}
STATE_PSEUDO = re.compile(r":(hover|focus|focus-visible|focus-within|active|visited|checked|disabled|invalid|valid|"
                          r"target|placeholder-shown|indeterminate|open|popover-open|modal|user-invalid)\b", re.I)
PSEUDO_EL = re.compile(r"::?(before|after)\b", re.I)
OTHER_PSEUDO_EL = re.compile(r"::?(placeholder|selection|marker|first-line|first-letter|backdrop|-webkit-[a-z-]+|-moz-[a-z-]+)\b", re.I)
DEFAULT_FONT_PX = 16.0
HEADING_SIZES = {"h1": 2.0, "h2": 1.5, "h3": 1.17, "h4": 1.0, "h5": 0.83, "h6": 0.67}
KEYWORD_SIZES = {"xx-small": 9, "x-small": 10, "small": 13, "medium": 16, "large": 18, "x-large": 24,
                 "xx-large": 32, "xxx-large": 48}
# impeccable's static engine applies no browser default stylesheet (an unstyled h1 is 16px, weight 400); the one UA
# rule it keeps is italic for em, i, cite, dfn, var and address (upstream crates/html/src/cascade/build.rs). We follow
# it so findings match upstream; a page that wants a heading scale must declare one (which a designed page does).
UA_DEFAULTS = {t: {"font-style": "italic"} for t in ("em", "i", "cite", "dfn", "var", "address")}


# --- parsing ---------------------------------------------------------------------------------------------------------
def strip_comments(css):
    return re.sub(r"/\*.*?\*/", "", css or "", flags=re.S)


def parse_decls(text):
    """'a: b; c: d !important' -> [(prop, value, important)] (handles ; inside url()/strings)."""
    out = []
    depth, buf, parts, quote = 0, [], [], None
    for ch in text:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch == ";" and depth == 0:
            parts.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    parts.append("".join(buf))
    for p in parts:
        if ":" not in p:
            continue
        k, v = p.split(":", 1)
        k = k.strip().lower()
        v = v.strip()
        if not k or not v or not re.match(r"^(--)?[-a-z0-9_]+$", k):
            continue
        imp = False
        if re.search(r"!\s*important\s*$", v, re.I):
            imp = True
            v = re.sub(r"!\s*important\s*$", "", v, flags=re.I).strip()
        out.append((k, v, imp))
    return out


class Rule:
    __slots__ = ("selectors", "decls", "order", "media")

    def __init__(self, selectors, decls, order, media=""):
        self.selectors = selectors
        self.decls = decls
        self.order = order
        self.media = media


def _blocks(css):
    """Yield (prelude, body) for each top-level block."""
    i, n = 0, len(css)
    while i < n:
        j = css.find("{", i)
        if j < 0:
            return
        # statement at-rules (@import ...;) before the block
        pre = css[i:j]
        while ";" in pre and pre.strip().startswith("@"):
            k = pre.find(";")
            pre = pre[k + 1:]
        depth, k = 1, j + 1
        while k < n and depth:
            if css[k] == "{":
                depth += 1
            elif css[k] == "}":
                depth -= 1
            k += 1
        yield pre.strip(), css[j + 1:k - 1]
        i = k


def media_applies(prelude):
    p = prelude.lower()
    if re.search(r"\bprint\b", p) and "screen" not in p:
        return False
    if "prefers-reduced-motion: reduce" in p.replace("  ", " ") or "prefers-reduced-motion:reduce" in p:
        return False
    if "prefers-color-scheme: dark" in p or "prefers-color-scheme:dark" in p:
        return False
    m = re.search(r"max-width\s*:\s*([\d.]+)(px|em|rem)", p)
    if m:
        px = float(m.group(1)) * (16 if m.group(2) != "px" else 1)
        if px < 1024:
            return False
    m = re.search(r"min-width\s*:\s*([\d.]+)(px|em|rem)", p)
    if m:
        px = float(m.group(1)) * (16 if m.group(2) != "px" else 1)
        if px > 1440:
            return False
    return True


class Sheet:
    def __init__(self):
        self.rules = []
        self.keyframes = {}   # name -> [(selector-ish offset, decls)]
        self.font_faces = []
        self.order = 0
        self.raw = []

    def add(self, css, media=""):
        css = strip_comments(css)
        self.raw.append(css)
        self._add(css, media, None)

    def _add(self, css, media, parent_sel):
        for pre, body in _blocks(css):
            low = pre.lower()
            if low.startswith("@media"):
                if media_applies(pre[6:]):
                    self._add(body, pre, parent_sel)
            elif low.startswith("@supports") or low.startswith("@layer") or low.startswith("@container") \
                    or low.startswith("@scope") or low.startswith("@document"):
                self._add(body, media, parent_sel)
            elif "keyframes" in low and low.startswith("@"):
                name = pre.split()[-1].strip() if len(pre.split()) > 1 else ""
                frames = [(p2, parse_decls(b2)) for p2, b2 in _blocks(body)]
                self.keyframes[name] = frames
            elif low.startswith("@font-face"):
                self.font_faces.append(parse_decls(body))
            elif low.startswith("@"):
                continue
            else:
                sels = split_selectors(pre)
                if parent_sel:
                    sels = [s.replace("&", p) if "&" in s else p + " " + s for p in parent_sel for s in sels]
                # nested rules inside the body (CSS nesting)
                own = body
                if "{" in body:
                    own = re.sub(r"[^;{}]*\{[^{}]*\}", "", body)
                    self._add(body[:0] + "".join(
                        "%s{%s}" % (p2, b2) for p2, b2 in _blocks(body)), media, sels)
                decls = parse_decls(own)
                if decls:
                    self.order += 1
                    self.rules.append(Rule(sels, decls, self.order, media))

    def text(self):
        return "\n".join(self.raw)


def split_selectors(pre):
    out, depth, buf = [], 0, []
    for ch in pre:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "," and depth == 0:
            out.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    out.append("".join(buf).strip())
    return [s for s in out if s]


# --- selectors -------------------------------------------------------------------------------------------------------
_TOKEN = re.compile(r"""
    (?P<comb>\s*[>+~]\s*|\s+)
  | (?P<tag>\*|[a-zA-Z][a-zA-Z0-9-]*)
  | (?P<id>\#[-\w\\:]+)
  | (?P<cls>\.[-\w\\:/\[\]%.]+?(?=[.#\[:\s>+~,)]|$))
  | (?P<attr>\[[^\]]*\])
  | (?P<pseudo>::?[-\w]+(?:\((?:[^()]|\([^()]*\))*\))?)
""", re.X)


def parse_selector(sel):
    """-> list of (combinator, compound) where compound = dict(tag, ids, classes, attrs, pseudos); None if unsupported."""
    sel = sel.strip()
    parts, comp, comb = [], None, " "
    pos = 0
    while pos < len(sel):
        m = _TOKEN.match(sel, pos)
        if not m or m.end() == pos:
            return None
        pos = m.end()
        if m.group("comb") is not None:
            c = m.group("comb").strip() or " "
            if comp is not None:
                parts.append((comb, comp))
                comp = None
            comb = c
            continue
        if comp is None:
            comp = {"tag": None, "ids": [], "classes": [], "attrs": [], "pseudos": []}
        if m.group("tag"):
            comp["tag"] = m.group("tag").lower()
        elif m.group("id"):
            comp["ids"].append(m.group("id")[1:].replace("\\", ""))
        elif m.group("cls"):
            comp["classes"].append(m.group("cls")[1:].replace("\\", ""))
        elif m.group("attr"):
            comp["attrs"].append(m.group("attr")[1:-1])
        elif m.group("pseudo"):
            comp["pseudos"].append(m.group("pseudo"))
    if comp is not None:
        parts.append((comb, comp))
    return parts or None


def specificity(parts):
    a = b = c = 0
    for _, comp in parts:
        a += len(comp["ids"])
        b += len(comp["classes"]) + len(comp["attrs"])
        for p in comp["pseudos"]:
            if p.startswith("::") or PSEUDO_EL.match(p):
                c += 1
            elif p.lower().startswith((":where",)):
                pass
            else:
                b += 1
        if comp["tag"] and comp["tag"] != "*":
            c += 1
    return (a, b, c)


def _attr_match(node, spec):
    m = re.match(r"\s*([-\w:]+)\s*(?:([~|^$*]?=)\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s\]]+))\s*(i)?)?\s*$", spec)
    if not m:
        return False
    name = m.group(1).lower()
    if name not in node.attrs:
        return False
    op = m.group(2)
    if not op:
        return True
    want = m.group(3) if m.group(3) is not None else (m.group(4) if m.group(4) is not None else m.group(5))
    have = node.attrs.get(name, "")
    if m.group(6):
        want, have = want.lower(), have.lower()
    if op == "=":
        return have == want
    if op == "~=":
        return want in have.split()
    if op == "|=":
        return have == want or have.startswith(want + "-")
    if op == "^=":
        return have.startswith(want)
    if op == "$=":
        return have.endswith(want)
    if op == "*=":
        return want in have
    return False


def _nth(expr, i):
    expr = expr.replace(" ", "").lower()
    if expr == "odd":
        return i % 2 == 1
    if expr == "even":
        return i % 2 == 0
    m = re.match(r"^([-+]?\d*)?n([-+]\d+)?$", expr)
    if m:
        a = m.group(1)
        a = 1 if a in ("", "+", None) else (-1 if a == "-" else int(a))
        b = int(m.group(2) or 0)
        if a == 0:
            return i == b
        return (i - b) % a == 0 and (i - b) / a >= 0
    try:
        return i == int(expr)
    except ValueError:
        return False


def _pseudo_ok(node, p):
    pl = p.lower()
    if pl.startswith("::") or PSEUDO_EL.match(pl) or OTHER_PSEUDO_EL.match(pl):
        return True     # pseudo-element: matched on the host, caller sorts it out
    if STATE_PSEUDO.match(pl):
        return False
    name = re.match(r":([-\w]+)", pl).group(1)
    arg = None
    if "(" in pl:
        arg = p[p.index("(") + 1:-1]
    sibs = node.parent.elements() if node.parent is not None else [node]
    if name == "root":
        return node.tag == "html"
    if name in ("first-child",):
        return sibs[0] is node
    if name == "last-child":
        return sibs[-1] is node
    if name == "only-child":
        return len(sibs) == 1
    if name == "first-of-type":
        return [s for s in sibs if s.tag == node.tag][0] is node
    if name == "last-of-type":
        return [s for s in sibs if s.tag == node.tag][-1] is node
    if name == "nth-child" and arg:
        return _nth(arg, sibs.index(node) + 1)
    if name == "nth-last-child" and arg:
        return _nth(arg, len(sibs) - sibs.index(node))
    if name == "nth-of-type" and arg:
        same = [s for s in sibs if s.tag == node.tag]
        return _nth(arg, same.index(node) + 1)
    if name == "empty":
        return not node.children or all(isinstance(c, str) and not c.strip() for c in node.children)
    if name in ("not",) and arg:
        return not any(matches(node, s) for s in split_selectors(arg))
    if name in ("is", "where", "matches", "-webkit-any") and arg:
        return any(matches(node, s) for s in split_selectors(arg))
    if name == "has" and arg:
        return any(matches(d, s.lstrip("> ").strip()) for d in node.iter() for s in split_selectors(arg))
    if name in ("link", "any-link"):
        return node.tag == "a" and "href" in node.attrs
    if name in ("lang", "dir", "defined", "scope", "enabled", "required", "optional", "read-only", "read-write"):
        return True
    return False


def _compound_ok(node, comp):
    if node is None or node.tag.startswith("#"):
        return False
    if comp["tag"] and comp["tag"] != "*" and comp["tag"] != node.tag:
        return False
    if comp["ids"] and any(i != node.id for i in comp["ids"]):
        return False
    if comp["classes"]:
        cl = set(node.classes)
        if any(c not in cl for c in comp["classes"]):
            return False
    for a in comp["attrs"]:
        if not _attr_match(node, a):
            return False
    for p in comp["pseudos"]:
        if not _pseudo_ok(node, p):
            return False
    return True


_SEL_CACHE = {}


def compiled(sel):
    if sel not in _SEL_CACHE:
        _SEL_CACHE[sel] = parse_selector(sel)
    return _SEL_CACHE[sel]


def _match_parts(node, parts, k):
    comb, comp = parts[k]
    if not _compound_ok(node, comp):
        return False
    if k == 0:
        return True
    if comb == ">":
        return _match_parts(node.parent, parts, k - 1) if node.parent is not None else False
    if comb == " ":
        p = node.parent
        while p is not None and not p.tag.startswith("#"):
            if _match_parts(p, parts, k - 1):
                return True
            p = p.parent
        return False
    if comb in ("+", "~"):
        prev = node.prev_element()
        while prev is not None:
            if _match_parts(prev, parts, k - 1):
                return True
            if comb == "+":
                return False
            prev = prev.prev_element()
        return False
    return False


def matches(node, sel):
    parts = compiled(sel)
    if not parts:
        return False
    return _match_parts(node, parts, len(parts) - 1)


def pseudo_element_of(sel):
    m = PSEUDO_EL.search(sel.split()[-1] if sel.split() else sel)
    return m.group(1).lower() if m else None


def query(doc, sel):
    return [n for n in doc.iter() if matches(n, sel)]


# --- shorthands ------------------------------------------------------------------------------------------------------
def split_top(value, sep=None):
    out, depth, buf = [], 0, []
    for ch in value:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if depth == 0 and ((sep is None and ch.isspace()) or ch == sep):
            if buf:
                out.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if "".join(buf).strip():
        out.append("".join(buf).strip())
    return out


SIDES = ("top", "right", "bottom", "left")
BORDER_STYLES = {"none", "hidden", "dotted", "dashed", "solid", "double", "groove", "ridge", "inset", "outset"}


def _box(v):
    p = split_top(v)
    if not p:
        return None
    if len(p) == 1:
        p = p * 4
    elif len(p) == 2:
        p = [p[0], p[1], p[0], p[1]]
    elif len(p) == 3:
        p = [p[0], p[1], p[2], p[1]]
    return p[:4]


def _border_parts(v):
    width, style, col = None, None, None
    for t in split_top(v):
        tl = t.lower()
        if tl in BORDER_STYLES:
            style = tl
        elif re.match(r"^[-\d.]+(px|em|rem|pt|%)?$", tl) or tl in ("thin", "medium", "thick") or tl.startswith("calc(") or tl.startswith("var("):
            width = t
        else:
            col = t
    return width, style, col


def expand(prop, value):
    """One declaration -> [(longhand, value)] for the shorthands the rules read."""
    v = value
    if prop in ("padding", "margin"):
        b = _box(v)
        return [(prop + "-" + s, b[i]) for i, s in enumerate(SIDES)] if b else []
    if prop in ("padding-inline", "margin-inline"):
        b = split_top(v)
        base = prop.split("-")[0]
        return [(base + "-left", b[0]), (base + "-right", b[-1])] if b else []
    if prop in ("padding-block", "margin-block"):
        b = split_top(v)
        base = prop.split("-")[0]
        return [(base + "-top", b[0]), (base + "-bottom", b[-1])] if b else []
    if prop == "inset":
        b = _box(v)
        return [(s, b[i]) for i, s in enumerate(SIDES)] if b else []
    if prop == "border-width":
        b = _box(v)
        return [("border-%s-width" % s, b[i]) for i, s in enumerate(SIDES)] if b else []
    if prop == "border-color":
        b = _box(v)
        return [("border-%s-color" % s, b[i]) for i, s in enumerate(SIDES)] if b else []
    if prop == "border-style":
        b = _box(v)
        return [("border-%s-style" % s, b[i]) for i, s in enumerate(SIDES)] if b else []
    if prop in ("border", "border-top", "border-right", "border-bottom", "border-left",
                "border-inline-start", "border-inline-end", "border-block-start", "border-block-end",
                "border-inline", "border-block"):
        w, s, c = _border_parts(v)
        if v.strip().lower() in ("none", "0"):
            w, s = "0", "none"
        side_map = {"border": SIDES, "border-inline-start": ("left",), "border-inline-end": ("right",),
                    "border-block-start": ("top",), "border-block-end": ("bottom",),
                    "border-inline": ("left", "right"), "border-block": ("top", "bottom")}
        sides = side_map[prop] if prop in side_map else (prop.split("-")[1],)
        out = []
        for sd in sides:
            out.append(("border-%s-width" % sd, w if w is not None else ("medium" if s and s not in ("none", "hidden") else "0")))
            out.append(("border-%s-style" % sd, s or "none"))
            out.append(("border-%s-color" % sd, c or "currentcolor"))
        return out
    if prop in ("border-inline-start-width", "border-inline-start-color", "border-inline-start-style"):
        return [(prop.replace("inline-start", "left"), v)]
    if prop in ("border-inline-end-width", "border-inline-end-color", "border-inline-end-style"):
        return [(prop.replace("inline-end", "right"), v)]
    if prop == "border-radius":
        main = v.split("/")[0]
        b = _box(main)
        if not b:
            return []
        names = ("border-top-left-radius", "border-top-right-radius", "border-bottom-right-radius", "border-bottom-left-radius")
        return [(names[i], b[i]) for i in range(4)] + [("border-radius", v)]
    if prop == "background":
        out = [("background", v)]
        layers = split_top(v, ",")
        last = layers[-1] if layers else v
        col = None
        for t in split_top(last):
            if C.parse_color(t) is not None or t.lower().startswith("var("):
                col = t
        imgs = [l for l in layers if re.search(r"(gradient|url|image-set|image)\(", l, re.I)]
        out.append(("background-color", col or "transparent"))
        out.append(("background-image", ", ".join(_image_part(l) for l in imgs) if imgs else "none"))
        if re.search(r"\btext\b", v):
            out.append(("background-clip", "text"))
        return out
    if prop == "font":
        out = []
        m = re.search(r"(?:^|\s)((?:[\d.]+)(?:px|em|rem|pt|%)|xx-small|x-small|small|medium|large|x-large|xx-large|smaller|larger)(?:\s*/\s*([^\s]+))?\s+(.+)$", v)
        if m:
            out.append(("font-size", m.group(1)))
            if m.group(2):
                out.append(("line-height", m.group(2)))
            out.append(("font-family", m.group(3)))
            pre = v[:m.start(1)]
            if "italic" in pre:
                out.append(("font-style", "italic"))
            w = re.search(r"\b(bold|bolder|lighter|[1-9]00)\b", pre)
            if w:
                out.append(("font-weight", w.group(1)))
        return out
    if prop == "text-decoration":
        return [("text-decoration", v)]
    if prop == "overflow":
        b = split_top(v)
        return [("overflow", v), ("overflow-x", b[0]), ("overflow-y", b[-1])] if b else []
    if prop == "animation":
        return [("animation", v)]
    if prop == "transition":
        return [("transition", v)]
    if prop == "-webkit-text-fill-color":
        return [(prop, v)]
    if prop == "-webkit-background-clip":
        return [("background-clip", v)]
    return [(prop, v)]


def _image_part(layer):
    m = re.search(r"((?:repeating-)?(?:linear|radial|conic)-gradient\((?:[^()]|\((?:[^()]|\([^()]*\))*\))*\)|url\([^)]*\))", layer, re.I)
    return m.group(1) if m else layer


# --- cascade ---------------------------------------------------------------------------------------------------------
def _resolve_vars(value, custom, depth=0):
    if "var(" not in value or depth > 12:
        return value

    def rep(m):
        inner = m.group(1)
        name, _, fallback = inner.partition(",")
        name = name.strip()
        if name in custom:
            return _resolve_vars(custom[name], custom, depth + 1)
        return _resolve_vars(fallback.strip(), custom, depth + 1) if fallback else ""
    prev = None
    while prev != value and "var(" in value:
        prev = value
        value = re.sub(r"var\(((?:[^()]|\([^()]*\))*)\)", rep, value)
    return value


def cascade(doc, sheet, class_decls=None):
    """Fill node.style for every element; node.pseudo for ::before/::after. class_decls(node) -> [(prop, value)]
    returns utility-class declarations (Tailwind), applied at class specificity before stylesheet order."""
    entries = []  # (selector parts, specificity, order, decls, pseudo)
    for r in sheet.rules:
        for s in r.selectors:
            pe = pseudo_element_of(s)
            host = PSEUDO_EL.sub("", s).strip() if pe else s
            if OTHER_PSEUDO_EL.search(host):
                continue
            host = host or "*"
            parts = compiled(host)
            if not parts:
                continue
            entries.append((host, parts, specificity(compiled(s) or parts), r.order, r.decls, pe))
    # index by last compound's key for speed
    by_key = {}
    for e in entries:
        comp = e[1][-1][1]
        if comp["ids"]:
            key = "#" + comp["ids"][0]
        elif comp["classes"]:
            key = "." + comp["classes"][0]
        elif comp["tag"] and comp["tag"] != "*":
            key = comp["tag"]
        else:
            key = "*"
        by_key.setdefault(key, []).append(e)

    def visit(node, parent_style, parent_custom):
        cands = list(by_key.get("*", [])) + list(by_key.get(node.tag, []))
        if node.id:
            cands += by_key.get("#" + node.id, [])
        for c in node.classes:
            cands += by_key.get("." + c, [])
        own = {"": [], "before": [], "after": []}
        seen = set()
        for e in cands:
            if id(e) in seen:
                continue
            seen.add(id(e))
            if _match_parts(node, e[1], len(e[1]) - 1):
                own[e[5] or ""].append(e)
        decl_list = []  # (important, spec, order, prop, value)
        for prop, val in UA_DEFAULTS.get(node.tag, {}).items():
            decl_list.append((0, (-1, 0, 0), 0, prop, val))
        if class_decls:
            for k, (prop, val) in enumerate(class_decls(node)):
                decl_list.append((0, (0, 1, 0), -1000 + k, prop, val))
        for e in own[""]:
            for prop, val, imp in e[4]:
                decl_list.append((1 if imp else 0, e[2], e[3], prop, val))
        style_attr = node.attrs.get("style")
        if style_attr:
            for prop, val, imp in parse_decls(style_attr):
                decl_list.append((1 if imp else 0, (1, 0, 0, 0), 10 ** 7, prop, val))
        decl_list.sort(key=lambda d: (d[0], d[1], d[2]))
        style = {k: v for k, v in parent_style.items() if k in INHERITED or k.startswith("--")}
        custom = dict(parent_custom)
        raw = {}
        for _, _, _, prop, val in decl_list:
            for lp, lv in expand(prop, val):
                raw[lp] = lv
        for k, v in raw.items():
            if k.startswith("--"):
                custom[k] = v
        for k, v in raw.items():
            if not k.startswith("--"):
                vv = _resolve_vars(v, custom)
                if vv.strip().lower() == "inherit":
                    vv = parent_style.get(k, "")
                style[k] = vv
        style["__raw__"] = raw
        style["__parent_font_px__"] = parent_style.get("__font_px__", DEFAULT_FONT_PX)
        style["__font_px__"] = font_px(style.get("font-size"), parent_style.get("__font_px__", DEFAULT_FONT_PX),
                                       raw_given="font-size" in raw)
        style["__custom__"] = custom
        node.style = style
        for pe in ("before", "after"):
            if own[pe]:
                pd = {}
                for e in sorted(own[pe], key=lambda e: (e[2], e[3])):
                    for prop, val, imp in e[4]:
                        for lp, lv in expand(prop, val):
                            pd[lp] = _resolve_vars(lv, custom)
                node.pseudo[pe] = pd
        for ch in node.elements():
            visit(ch, style, custom)

    root_style = {"__font_px__": DEFAULT_FONT_PX, "color": "#000000"}
    for ch in doc.elements():
        visit(ch, root_style, {})


# --- value helpers ---------------------------------------------------------------------------------------------------
def font_px(value, parent_px=DEFAULT_FONT_PX, raw_given=True, root_px=DEFAULT_FONT_PX):
    if not value or not raw_given:
        return parent_px
    v = value.strip().lower()
    if v in KEYWORD_SIZES:
        return float(KEYWORD_SIZES[v])
    if v == "smaller":
        return parent_px / 1.2
    if v == "larger":
        return parent_px * 1.2
    px = length_px(v, parent_px, root_px, parent_px)
    return px if px is not None else parent_px


def length_px(value, font=DEFAULT_FONT_PX, root=DEFAULT_FONT_PX, pct_base=None, vw=1280.0, vh=800.0):
    """CSS length -> px (None when unknown). Handles calc/clamp/min/max by evaluating their arguments."""
    if value is None:
        return None
    v = str(value).strip().lower()
    if not v:
        return None
    if v in ("0", "0px", "0.0"):
        return 0.0
    m = re.match(r"^env\(\s*[-\w]+\s*(?:,\s*(.*))?\)$", v)
    if m:   # env(safe-area-inset-*): 0 on a desktop at rest, else its fallback
        return length_px(m.group(1), font, root, pct_base, vw, vh) if m.group(1) else 0.0
    m = re.match(r"^(clamp|min|max)\((.*)\)$", v)
    if m:
        args = [length_px(a if not re.search(r"\s[-+*/]\s", a) else "calc(%s)" % a, font, root, pct_base, vw, vh)
                for a in split_top(m.group(2), ",")]
        if any(a is None for a in args):
            return None
        if m.group(1) == "min":
            return min(args)
        if m.group(1) == "max":
            return max(args)
        if len(args) == 3:
            return max(args[0], min(args[1], args[2]))
        return None
    m = re.match(r"^calc\((.*)\)$", v)
    if m:
        expr = m.group(1)
        expr = re.sub(r"(?:env|clamp|min|max|calc)\((?:[^()]|\([^()]*\))*\)",
                      lambda f: ("%rpx" % length_px(f.group(0), font, root, pct_base, vw, vh)) if length_px(f.group(0), font, root, pct_base, vw, vh) is not None else "NaN",
                      expr)
        if "NaN" in expr:
            return None
        toks = re.findall(r"[-+]?[\d.]+[a-z%]*|[-+*/()]", expr)
        out = []
        for t in toks:
            if re.match(r"^[-+]?[\d.]+[a-z%]+$", t):
                px = length_px(t, font, root, pct_base, vw, vh)
                if px is None:
                    return None
                out.append(repr(px))
            else:
                out.append(t)
        try:
            return float(eval("".join(out), {"__builtins__": {}}, {}))  # tokens are numbers/operators only
        except Exception:
            return None
    m = re.match(r"^([-+]?(?:\d+\.?\d*|\.\d+))(px|em|rem|%|pt|vw|vh|vmin|vmax|ch|ex|svh|dvh|lvh)?$", v)
    if not m:
        return None
    n = float(m.group(1))
    u = m.group(2) or ("px" if n == 0 else None)
    if u is None:
        return None
    return {"px": n, "em": n * font, "rem": n * root, "pt": n * 4 / 3, "vw": n * vw / 100, "vh": n * vh / 100,
            "svh": n * vh / 100, "dvh": n * vh / 100, "lvh": n * vh / 100, "vmin": n * min(vw, vh) / 100,
            "vmax": n * max(vw, vh) / 100, "ch": n * font * 0.5, "ex": n * font * 0.5,
            "%": (n * pct_base / 100 if pct_base is not None else None)}.get(u)


def line_height_px(style):
    fs = style.get("__font_px__", DEFAULT_FONT_PX)
    v = (style.get("line-height") or "normal").strip().lower()
    if v == "normal":
        return fs * 1.2
    if re.match(r"^[\d.]+$", v):
        return float(v) * fs
    px = length_px(v, fs, DEFAULT_FONT_PX, fs)
    return px if px is not None else fs * 1.2


def letter_spacing_em(style):
    fs = style.get("__font_px__", DEFAULT_FONT_PX)
    v = (style.get("letter-spacing") or "normal").strip().lower()
    if v == "normal":
        return 0.0
    m = re.match(r"^([-+]?[\d.]+)em$", v)
    if m:
        return float(m.group(1))
    px = length_px(v, fs)
    return px / fs if px is not None and fs else 0.0


def font_weight(style):
    v = (style.get("font-weight") or "400").strip().lower()
    return {"normal": 400, "bold": 700, "bolder": 700, "lighter": 300}.get(v) or (float(v) if re.match(r"^\d+$", v) else 400)


def first_family(style):
    fam = style.get("font-family") or ""
    first = split_top(fam, ",")
    return first[0].strip().strip("'\"").lower() if first else ""


def families(style):
    return [f.strip().strip("'\"").lower() for f in split_top(style.get("font-family") or "", ",")]


def color_of(style, prop="color"):
    v = style.get(prop)
    if not v:
        return None
    if v.strip().lower() == "currentcolor":
        return C.parse_color(style.get("color", "#000"))
    return C.parse_color(v)


def is_hidden(node):
    """display:none / visibility:hidden / [hidden] / aria-hidden on the node or an ancestor."""
    for n in [node] + list(node.ancestors()):
        st = n.style or {}
        if "hidden" in n.attrs and n.tag != "input":
            return True
        if (st.get("display") or "").strip().lower() == "none":
            return True
        if n.tag in ("template", "script", "style", "noscript", "head"):
            return True
    st = node.style or {}
    if (st.get("visibility") or "").strip().lower() in ("hidden", "collapse"):
        return True
    return False


def is_visually_hidden(node):
    st = node.style or {}
    if (st.get("position") or "") == "absolute" and (st.get("clip") or st.get("clip-path")):
        w = length_px(st.get("width"))
        if w is not None and w <= 1:
            return True
    if "sr-only" in node.classes or "visually-hidden" in node.classes:
        return True
    return False


def background_of(node, default=(255.0, 255.0, 255.0, 1.0)):
    """The effective background behind node: composite solid backgrounds down the ancestor chain; a gradient layer
    contributes the mean of its colour stops. Returns (rgba, source) where source is 'solid'|'gradient'|'image'|'default'."""
    layers = []
    for n in [node] + list(node.ancestors()):
        st = n.style or {}
        bg = color_of(st, "background-color")
        img = st.get("background-image") or "none"
        src = None
        if img and img != "none" and "gradient" in img:
            cols = [c for _, c in C.find_colors(img)]
            if cols:
                avg = tuple(sum(c[i] for c in cols) / len(cols) for i in range(4))
                bg = C.over(avg, bg) if bg else avg
                src = "gradient"
        elif img and img != "none" and "url(" in img:
            src = "image"
        if bg is not None and bg[3] > 0:
            layers.append((bg, src or "solid"))
            if bg[3] >= 0.999:
                break
    acc = default
    source = "default"
    for bg, src in reversed(layers):
        acc = C.over(bg, acc)
        source = src
    return acc, source
