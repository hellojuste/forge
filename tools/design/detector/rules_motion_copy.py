"""rules_motion_copy — motion and copy rules of impeccable's static HTML engine (Apache-2.0 upstream, ported).

bounce-easing (element rule), pulsing-dot, marquee, theater-slop-phrase (html-pattern pass), em-dash-overuse,
marketing-buzzword, aphoristic-cadence (regex-engine text analyzers), repeated-container-text (page check).
blinking-cursor is browser-only upstream and is not in RULES. Page-level rules need ctx.full_page.
Spec: specs/D_motion_copy.md (upstream file:line for every piece).
"""
import re

from . import css as CSS
from . import color as C
from .ignores import ignored

WS_CHARS = "\t\n\x0b\x0c\r \xa0  -     　﻿"
WS = "[%s]" % WS_CHARS
A = re.A
JS_WS = "\t\n\x0b\x0c\r \xa0     　﻿" + "".join(chr(c) for c in range(0x2000, 0x200b))


def jtrim(s):
    return (s or "").strip(JS_WS)


def utf16_len(s):
    return len(s.encode("utf-16-le")) // 2


def utf16_prefix(s, n):
    out, units = [], 0
    for ch in s:
        u = 2 if ord(ch) > 0xFFFF else 1
        if units + u > n:
            break
        units += u
        out.append(ch)
    return "".join(out)


def utf16_slice(s, start, end):
    """JS s.slice(start, end) in UTF-16 units (astral chars kept whole)."""
    out, units = [], 0
    for ch in s:
        u = 2 if ord(ch) > 0xFFFF else 1
        if units >= start and units + u <= end:
            out.append(ch)
        units += u
    return "".join(out)


def pf(s):
    """JS parseFloat."""
    m = re.match(r"[%s]*([+-]?(?:\d+\.?\d*(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?|Infinity))" % WS_CHARS, s or "")
    return float(m.group(1)) if m else float("nan")


def num_str(x):
    """JS String(number)."""
    if x != x:
        return "NaN"
    return str(int(x)) if x == int(x) else repr(x)


# ─── shared text helpers ─────────────────────────────────────────────────────────────────────────────────────────────
_SCRIPT = re.compile(r"<(?i:script)\b[^>]*>[\s\S]*?</(?i:script)>", A)
_STYLE = re.compile(r"<(?i:style)\b[^>]*>[\s\S]*?</(?i:style)>", A)
_HTML_COMMENT = re.compile(r"<!--[\s\S]*?-->")
_TAG = re.compile(r"<[^>]+>")
_WS_RUN = re.compile(WS + "+")


def strip_html_to_text(html):
    """regex_matchers.rs#strip_html_to_text."""
    s = _SCRIPT.sub(" ", html)
    s = _STYLE.sub(" ", s)
    s = _HTML_COMMENT.sub(" ", s)
    s = _TAG.sub(" ", s)
    return _WS_RUN.sub(" ", s)


# ─── em-dash-overuse ─────────────────────────────────────────────────────────────────────────────────────────────────
EM_DASH_FLOOR = 8                 # constants.rs EM_DASH_FLOOR
EM_DASH_CHARS_PER_DASH = 500      # constants.rs EM_DASH_CHARS_PER_DASH
_EM_ENTITY = re.compile(r"&(?i:mdash);|&#0*8212;|&#[xX]0*2014;", A)


def count_em_dashes(body):
    """text_rules.rs#count_em_dashes: each —, each `--` before a non-space, each `word---word`."""
    n, i, L = 0, 0, len(body)
    while i < L:
        c = body[i]
        if c == "—":
            n += 1
            i += 1
        elif c == "-":
            s = i
            while i < L and body[i] == "-":
                i += 1
            run = i - s
            nx = body[i] if i < L else None
            if run == 2 and nx is not None and nx not in JS_WS:
                n += 1
            elif run == 3 and s > 0 and body[s - 1].isalnum() and nx is not None and nx.isalnum():
                n += 1
        else:
            i += 1
    return n


def analyze_em_dash(raw):
    """regex_matchers.rs#analyze_em_dash_overuse -> snippet list."""
    text = _EM_ENTITY.sub("—", strip_html_to_text(raw))
    c = count_em_dashes(text)
    if c < EM_DASH_FLOOR or utf16_len(text) > c * EM_DASH_CHARS_PER_DASH:
        return []
    return ["%d em-dashes in body text" % c]


# ─── marketing-buzzword ──────────────────────────────────────────────────────────────────────────────────────────────
BUZZWORDS = [   # regex_matchers.rs BUZZWORDS (verbatim, upstream order)
    "streamline your", "empower your", "supercharge your", "unleash your", "unleash the power", "leverage the power",
    "built for the modern", "trusted by leading", "trusted by the world", "best-in-class", "industry-leading",
    "world-class", "enterprise-grade", "next-generation", "cutting-edge", "transform your business", "revolutionize",
    "game-changer", "game changing", "mission-critical", "best of breed", "future-proof", "future proof",
    "seamless experience", "seamlessly integrate", "drive engagement", "drive growth", "drive results",
    "harness the power",
]


def analyze_buzzwords(raw):
    """regex_matchers.rs#analyze_marketing_buzzword."""
    text = strip_html_to_text(raw)
    low = text.lower()
    count, sample = 0, ""
    for phrase in BUZZWORDS:
        frm = 0
        while True:
            i = low.find(phrase, frm)
            if i < 0:
                break
            count += 1
            if not sample:
                sample = jtrim(text[max(0, i - 12):min(i + len(phrase) + 12, len(text))])
            frm = i + len(phrase)
    if not count:
        return []
    return ['%d buzzword phrase%s: "%s"' % (count, "" if count == 1 else "s", sample)]


# ─── aphoristic-cadence ──────────────────────────────────────────────────────────────────────────────────────────────
NOT_A_RE = re.compile(r"\bNot an? [a-z][^.!?]{1,40}[.!]" + WS + r"+[A-Z][^.!?]{1,60}[.!]", A)
SHORT_REBUTTAL_RE = re.compile(r"\b[A-Z][^.!?]{4,80}[.!]" + WS + r"+(No|Just)" + WS + r"+[a-z][^.!?]{2,60}[.!]", A)
APHORISM_MIN = 3


def analyze_aphorisms(raw):
    """regex_matchers.rs#analyze_aphoristic_cadence."""
    text = strip_html_to_text(raw)
    count, sample = 0, ""
    for rx in (NOT_A_RE, SHORT_REBUTTAL_RE):
        for m in rx.finditer(text):
            count += 1
            if not sample:
                sample = utf16_prefix(jtrim(m.group(0)), 80)
    if count < APHORISM_MIN:
        return []
    return ['%d aphoristic constructions: "%s"' % (count, sample)]


# ─── theater-slop-phrase ─────────────────────────────────────────────────────────────────────────────────────────────
THEATER_RE = re.compile(r"\b([A-Za-z0-9_]+)" + WS + r"+(?i:theater)\b", A)
THEATER_DISMISSIVE_HEADS = {   # html_patterns.rs THEATER_DISMISSIVE_HEADS (closed list)
    "accessibility", "accountability", "agile", "alignment", "compliance", "diversity", "engagement", "governance",
    "growth", "hiring", "hygiene", "innovation", "inclusion", "kindness", "leadership", "metrics", "privacy", "process",
    "productivity", "quality", "safety", "security", "strategy", "sustainability", "transparency", "trust", "wellness",
}


def scan_theater(html):
    """html_patterns.rs#check_html_patterns_with, 'X theater' block: at most one hit per page."""
    body = _TAG.sub(" ", _STYLE.sub(" ", _SCRIPT.sub(" ", html)))
    for m in THEATER_RE.finditer(body):
        if m.group(1).lower() in THEATER_DISMISSIVE_HEADS:
            return ['"%s"' % jtrim(m.group(0))]
    return []


# ─── CSS-text helpers (foundation css_scan.rs) ───────────────────────────────────────────────────────────────────────
RULE_BLOCK = re.compile(r"([^{};]+)\{([^{}]*)\}")
KEYFRAMES_RE = re.compile(r"@(?:-webkit-)?keyframes" + WS + r"+([A-Za-z0-9_-]+)" + WS + r"*\{")
_IMPORTANT_TAIL = re.compile(WS + r"*!(?i:important)" + WS + r"*$", A)
ANIMATION_VALUE_KEYWORDS = {"ease", "ease-in", "ease-out", "ease-in-out", "linear", "infinite", "alternate",
                            "alternate-reverse", "normal", "reverse", "none", "forwards", "backwards", "both",
                            "running", "paused", "step-start", "step-end", "inherit", "initial", "unset"}
_INFINITE = re.compile(r"\b(?i:infinite)\b", A)
_IDENT = re.compile(r"^[a-zA-Z_-][A-Za-z0-9_-]*$")


def parse_decl_block(block):
    """css_scan.rs#parse_css_decl_block: last wins, prop lowercased, !important dropped."""
    d = {}
    for part in block.split(";"):
        i = part.find(":")
        if i <= 0:
            continue
        prop = jtrim(part[:i]).lower()
        val = jtrim(_IMPORTANT_TAIL.sub("", part[i + 1:], count=1))
        if prop and val:
            d[prop] = val
    return d


def brace_walk(text, frm):
    """-> (index after the matching close or text end, closed?)."""
    depth, i = 1, frm
    while i < len(text) and depth > 0:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    return i, depth == 0


def keyframe_bodies(text):
    """Yield (match, body) for every @keyframes block (unterminated: all but the last char)."""
    pos = 0
    while True:
        m = KEYFRAMES_RE.search(text, pos)
        if not m:
            return
        i, closed = brace_walk(text, m.end())
        yield m, text[m.end():max(m.end(), i - 1)], closed
        pos = i


def split_commas_outside_parens(s):
    """js_ext_a.rs#split_commas_outside_parens (JS /,(?![^(]*\\))/)."""
    parts, start = [], 0
    for i, ch in enumerate(s):
        if ch != ",":
            continue
        closes_first = False
        for c in s[i + 1:]:
            if c == "(":
                break
            if c == ")":
                closes_first = True
                break
        if closes_first:
            continue
        parts.append(s[start:i])
        start = i + 1
    parts.append(s[start:])
    return parts


def infinite_animation_names(d):
    """css_scan.rs#infinite_animation_names."""
    out = []
    if d.get("animation"):
        for layer in split_commas_outside_parens(d["animation"]):
            if not _INFINITE.search(layer):
                continue
            for t in re.split(WS + "+", layer):
                if _IDENT.match(t) and t.lower() not in ANIMATION_VALUE_KEYWORDS:
                    out.append(t)
                    break
    if d.get("animation-name") and _INFINITE.search(d.get("animation-iteration-count", "")):
        for raw in d["animation-name"].split(","):
            t = jtrim(raw)
            if t and t.lower() != "none":
                out.append(t)
    return out


_CUSTOM_PROP = re.compile(r"(--[A-Za-z0-9_-]+)" + WS + r"*:" + WS + r"*([^;{}]+)")
_VAR_REF = re.compile(r"var\(" + WS + r"*(--[a-zA-Z0-9_-]+)" + WS + r"*(?:," + WS + r"*([^)]+))?\)")
_CSS_LENGTH = re.compile(r"^(-?[0-9.]+)((?i:px)|(?i:rem)|(?i:em))$", A)


def custom_props(text):
    d = {}
    for m in _CUSTOM_PROP.finditer(text):
        d.setdefault(m.group(1), jtrim(m.group(2)))
    return d


def resolve_var_refs(raw, props, depth=0):
    """css_scan.rs#resolve_var_refs: unresolved refs stay as written."""
    if "var(" not in raw or depth > 8:
        return raw

    def rep(m):
        if m.group(1) in props:
            return resolve_var_refs(props[m.group(1)], props, depth + 1)
        if m.group(2):
            return resolve_var_refs(jtrim(m.group(2)), props, depth + 1)
        return m.group(0)
    return _VAR_REF.sub(rep, raw)


def css_length_to_px(v):
    """css_scan.rs#css_length_to_px: px, or rem/em × 16."""
    m = _CSS_LENGTH.match(jtrim(v or ""))
    if not m:
        return None
    n = pf(m.group(1))
    return n if m.group(2).lower() == "px" else n * 16


_LINK_TAG = re.compile(r"<link\b[^>]*>", re.I)
_HREF = re.compile(r"""\bhref\s*=\s*["']?([^"'\s>]+)""", re.I)


def style_corpus(ctx):
    """ctx.css_text plus root-absolute linked stylesheets the core loader leaves unread.

    Core wish (engine.py, not edited here): upstream resolves `href="/a/b.css"` against the file's directory tree
    (crates/html/src/cascade: a site-root path); engine.Context joins it as an absolute path and misses it. This
    helper retries such hrefs as suffixes of the file's ancestor directories, for this module's text scans only."""
    cached = getattr(ctx, "_motion_copy_corpus", None)
    if cached is not None:
        return cached
    text = ctx.css_text
    if getattr(ctx, "unread_stylesheet", False):
        loaded = {str(p) for p in getattr(ctx, "linked", [])}
        for tag in _LINK_TAG.findall(ctx.text):
            if "stylesheet" not in tag.lower():
                continue
            m = _HREF.search(tag)
            href = m.group(1).split("?")[0].split("#")[0] if m else ""
            if not href.startswith("/") or href.startswith("//"):
                continue
            parts = [p for p in href.split("/") if p]
            found = None
            for d in [ctx.path.parent] + list(ctx.path.parent.parents)[:4]:
                for k in range(len(parts)):
                    cand = d.joinpath(*parts[k:])
                    if cand.is_file():
                        found = cand.resolve()
                        break
                if found:
                    break
            if found and str(found) not in loaded:
                loaded.add(str(found))
                text += "\n" + CSS.strip_comments(found.read_text(encoding="utf-8", errors="replace"))
    try:
        ctx._motion_copy_corpus = text
    except AttributeError:
        pass
    return text


def selector_scoped_ignored(ctx, selector, rule_id):
    """engine.rs post-filter: drop a selector-bearing pattern hit when every element it matches is waived."""
    if not selector or ctx.doc is None:
        return False
    sel = jtrim(re.sub(r"::?[a-zA-Z-]+(\([^)]*\))?", "", selector))
    try:
        hosts = CSS.query(ctx.doc, sel) if sel and CSS.compiled(sel) else []
    except Exception:
        return False
    return bool(hosts) and all(ignored(n, rule_id) for n in hosts)


# ─── bounce-easing (element rule) ────────────────────────────────────────────────────────────────────────────────────
SAFE_TAGS = {"blockquote", "nav", "a", "input", "textarea", "select", "pre", "code", "span", "th", "td", "tr", "li",
             "label", "button", "hr", "html", "head", "body", "script", "style", "link", "meta", "title", "br", "img",
             "svg", "path", "circle", "rect", "line", "polyline", "polygon", "g", "defs", "use"}
BOUNCE_NAME = re.compile(r"(?i:bounce|elastic|wobble|jiggle|spring)", A)
BOUNCE_WORDS = ("bounce", "elastic", "wobble", "jiggle", "spring")
BEZIER_RE = re.compile(r"cubic-bezier\(" + WS + r"*([0-9.-]+)" + WS + r"*," + WS + r"*([0-9.-]+)" + WS + r"*," + WS
                       + r"*([0-9.-]+)" + WS + r"*," + WS + r"*([0-9.-]+)" + WS + r"*\)")
_TIMING_TOKEN = re.compile(r"(?i)^(?:ease|linear|step-|cubic-bezier\()")
_ANIM_NAME_TOKEN = re.compile(r"(?i)^[a-z_-][0-9A-Za-z_-]*$")
_ANIM_KEYWORD = re.compile(r"^(?:ease|linear|infinite|alternate|forwards|backwards|both|normal|none|running|paused)$")
_SCALE_FN = re.compile(r"^(?i:scale)(?:[xXyYzZ]|3[dD])?\(([^()]*)\)", A)
_STEP_BLOCK = re.compile(r"\{([^{}]*)\}")


def bezier_out_of_range(y1, y2):
    return y1 < -0.1 or y1 > 1.1 or y2 < -0.1 or y2 > 1.1


def parse_static_animation(value):
    """cascade_shorthand.rs#parse_static_animation -> (names, timings)."""
    names, timings = [], []
    for item in CSS.split_top(value, ","):
        toks = CSS.split_top(item)
        t = next((x for x in toks if _TIMING_TOKEN.match(x)), None)
        if t:
            timings.append(t)
        n = next((x for x in toks if _ANIM_NAME_TOKEN.match(x) and not _ANIM_KEYWORD.match(x)), None)
        if n:
            names.append(n)
    return ", ".join(names), ", ".join(timings)


def parse_static_transition_timing(value):
    """cascade_shorthand.rs#parse_static_transition (timing half)."""
    out = []
    for item in CSS.split_top(value, ","):
        t = next((x for x in CSS.split_top(item) if _TIMING_TOKEN.match(x)), None)
        if t:
            out.append(t)
    return ", ".join(out)


def _factors_in_unit(lst):
    parts = [p for p in re.split(r"[,%s]" % WS_CHARS, lst) if p]
    if not parts:
        return False
    for p in parts:
        try:
            v = float(p)
        except ValueError:
            return False
        if not 0.0 <= v <= 1.0:
            return False
    return True


def keyframe_decl_only_pulses(prop, value):
    """css_scan.rs#keyframe_decl_only_pulses."""
    prop = jtrim(prop).lower()
    if prop.startswith("-webkit-"):
        prop = prop[8:]
    value = jtrim(value)
    if value.endswith("!important"):
        value = jtrim(value[:-10])
    if prop == "opacity":
        return True
    if prop == "scale":
        return value.lower() == "none" or _factors_in_unit(value)
    if prop == "transform":
        if value.lower() == "none":
            return True
        rest, anyf = value, False
        while rest:
            m = _SCALE_FN.match(rest)
            if not m or not _factors_in_unit(m.group(1)):
                return False
            anyf = True
            rest = rest[m.end():].lstrip(JS_WS)
        return anyf
    if prop == "animation-timing-function":
        low = value.lower()
        if "linear(" in low or "var(" in low:
            return False
        return not any(not (0 <= pf(m.group(2)) <= 1) or not (0 <= pf(m.group(4)) <= 1)
                       for m in BEZIER_RE.finditer(low))
    return False


def css_keyframes_only_pulse(text, name):
    """css_scan.rs#css_keyframes_only_pulse -> True/False/None (None: no such keyframes)."""
    verdict = None
    for m, body, closed in keyframe_bodies(text):
        if m.group(1) != name:
            continue
        if not closed:
            return False
        decls = []
        for step in _STEP_BLOCK.finditer(body):
            for d in step.group(1).split(";"):
                if not jtrim(d):
                    continue
                p, _, v = d.partition(":")
                decls.append((p, v))
        if not decls or not all(keyframe_decl_only_pulses(p, v) for p, v in decls):
            return False
        verdict = True
    return verdict


def bounce_names_only_pulse(names, css_text):
    """css_scan.rs#bounce_names_only_pulse."""
    kept = [jtrim(n) for n in names.split(",") if any(w in jtrim(n).lower() for w in BOUNCE_WORDS)]
    return bool(kept) and all(css_keyframes_only_pulse(css_text, n) is True for n in kept)


def element_motion(node):
    """adapters.rs#check_element_motion -> rules.rs#check_motion (static engine: class list is empty)."""
    if node.tag in SAFE_TAGS:
        return []
    st = node.style or {}
    raw = st.get("__raw__", {})
    name, a_timing = "", ""
    if st.get("animation"):
        name, a_timing = parse_static_animation(st["animation"])
    if "animation-name" in raw:
        name = st.get("animation-name", "")
    if "animation-timing-function" in raw:
        a_timing = st.get("animation-timing-function", "")
    t_timing = parse_static_transition_timing(st["transition"]) if st.get("transition") else ""
    if "transition-timing-function" in raw:
        t_timing = st.get("transition-timing-function", "")
    hits = []
    if name and name != "none" and BOUNCE_NAME.search(name):
        hits.append("animation: %s" % name)
    timing = " ".join(t for t in (a_timing, t_timing) if t)
    for m in BEZIER_RE.finditer(timing):
        if bezier_out_of_range(pf(m.group(2)), pf(m.group(4))):
            hits.append("cubic-bezier(%s, %s, %s, %s)" % m.groups())
            break
    return hits


def rule_bounce_easing(ctx):
    if ctx.doc is None:
        return []
    css_text = ctx.sheet.text()
    out = []
    for node in ctx.elements():
        for snip in element_motion(node):
            if ignored(node, "bounce-easing"):
                continue
            if snip.startswith("animation: ") and bounce_names_only_pulse(snip[len("animation: "):], css_text):
                continue
            out.append(("bounce-easing", snip, node.line))
    return out


# ─── pulsing-dot ─────────────────────────────────────────────────────────────────────────────────────────────────────
_OPACITY_DECL = re.compile(r"\b(?i:opacity)" + WS + r"*:", A)
_BOX_SHADOW_DECL = re.compile(r"\b(?i:box-shadow)" + WS + r"*:", A)
_TRANSFORM_SCALE = re.compile(r"\b(?i:transform)" + WS + r"*:[^;{}]*\b(?i:scale)", A)
_REDUCED_MOTION = re.compile(r"@(?i:media)[^{]*(?i:prefers-reduced-motion)" + WS + r"*:" + WS + r"*(?i:reduce)[^{]*\{", A)
_CSS_COMMENT = re.compile(r"/\*[\s\S]*?\*/")
PULSE_NAME_RE = re.compile(r"(?i:pulse|blink|ping)", A)
_PCT_VALUE = re.compile(r"^([0-9.]+)%$")
_CLASS_ATTR = re.compile(r"(?i:class)" + WS + r"*=" + WS + r"*(?:\"([^\"]*)\"|'([^']*)')", A)
_TW_ANIMATE = re.compile(r"\banimate-(ping|pulse)\b", A)
_TW_ROUNDED_FULL = re.compile(r"\brounded-full\b", A)
_TW_TINY = re.compile(r"\b(?:w|h|size)-(?:1|1\.5|2|2\.5|3|3\.5|4)\b", A)
DOT_MIN_PX, DOT_MAX_PX = 2.0, 16.0


def collect_pulse_keyframes(text):
    """css_scan.rs#collect_pulse_keyframes: name -> pulses? (a pulsing definition upgrades, never downgrades)."""
    mp = {}
    for m, body, _ in keyframe_bodies(text):
        p = bool(_OPACITY_DECL.search(body) or _BOX_SHADOW_DECL.search(body) or _TRANSFORM_SCALE.search(body))
        if m.group(1) not in mp or p:
            mp[m.group(1)] = p
    return mp


def strip_reduced_motion_blocks(text):
    out, last, pos = [], 0, 0
    while True:
        m = _REDUCED_MOTION.search(text, pos)
        if not m:
            break
        i, _ = brace_walk(text, m.end())
        out.append(text[last:m.start()])
        last = pos = i
    out.append(text[last:])
    return "".join(out)


def landmark_ranges(markup):
    """css_scan.rs#landmark_source_ranges (<header>, <nav>)."""
    ranges = []
    for tag in ("header", "nav"):
        stack = []
        for m in re.finditer(r"<(?i:%s)\b|</(?i:%s)%s*>" % (tag, tag, WS), markup, A):
            if m.group(0)[1] == "/":
                if stack:
                    ranges.append((stack.pop(), m.start()))
            else:
                stack.append(m.start())
    return ranges


def _in_ranges(i, ranges):
    return any(a <= i < b for a, b in ranges)


def _value_has_token(value, needle):
    for m in re.finditer(re.escape(needle), value, re.I):
        a, b = m.start(), m.end()
        if (a == 0 or not re.match(r"[\w-]", value[a - 1], A)) and (b == len(value) or not re.match(r"[\w-]", value[b], A)):
            return True
    return False


def _attr_tag_starts(markup, attr, needle, exact):
    out = []
    for m in re.finditer(r"<[a-zA-Z][^>]*>?", markup):
        tag = m.group(0)
        for am in re.finditer(r"(?<![\w])%s%s*=%s*[\"']([^\"']*)[\"']" % (attr, WS, WS), tag, re.I | A):
            v = am.group(1)
            if (v.lower() == needle.lower()) if exact else _value_has_token(v, needle):
                out.append(m.start())
                break
    return out


def selector_hits_landmark(markup, selector, ranges):
    """css_scan.rs#selector_hits_landmark."""
    if not ranges:
        return False
    parts = [s for s in re.split("[%s>+~]+" % WS_CHARS, selector) if s]
    last = parts[-1] if parts else ""
    i = re.search(r"#([A-Za-z_][A-Za-z0-9_-]*)", last)
    c = re.search(r"\.([A-Za-z_][A-Za-z0-9_-]*)", last)
    if i:
        starts = _attr_tag_starts(markup, "id", i.group(1), True)
    elif c:
        starts = _attr_tag_starts(markup, "class", c.group(1), False)
    else:
        return False
    return any(_in_ranges(s, ranges) for s in starts)


def is_round_dot_radius(radius, w, h):
    """css_scan.rs#is_round_dot_radius."""
    if not radius:
        return False
    first = re.split(WS + "+", jtrim(radius))[0]
    pm = _PCT_VALUE.match(first)
    if pm:
        return pf(pm.group(1)) >= 40
    px = css_length_to_px(first)
    return px is not None and (px >= 999 or px >= 0.4 * min(w, h))


def scan_pulsing_dot(content, markup):
    """css_scan.rs#scan_css_text_for_pulsing_dot -> [(snippet, severity|None, selector|None)]."""
    props = custom_props(content)
    kf = collect_pulse_keyframes(content)
    ranges = landmark_ranges(markup)
    text = _CSS_COMMENT.sub(" ", strip_reduced_motion_blocks(content))
    merged = {}
    for g1, g2 in RULE_BLOCK.findall(text):
        d = parse_decl_block(g2)
        if not d:
            continue
        for raw in g1.split(","):
            s = jtrim(raw)
            if s and not s.startswith("@"):
                merged.setdefault(s, {}).update(d)
    out, seen = [], set()
    for s, d in merged.items():
        names = infinite_animation_names(d)
        pn = next((n for n in names if (kf[n] if n in kf else PULSE_NAME_RE.search(n))), None)
        if not pn:
            continue
        w = css_length_to_px(resolve_var_refs(d.get("width") or d.get("inline-size") or "", props))
        h = css_length_to_px(resolve_var_refs(d.get("height") or d.get("block-size") or "", props))
        if w is None or h is None or w < DOT_MIN_PX or h < DOT_MIN_PX or w > DOT_MAX_PX or h > DOT_MAX_PX:
            continue
        if not is_round_dot_radius(resolve_var_refs(d.get("border-radius", ""), props), w, h) or s in seen:
            continue
        seen.add(s)
        land = selector_hits_landmark(markup, s, ranges)
        out.append(('%s — %sx%spx dot with infinite "%s" animation%s'
                    % (s, num_str(w), num_str(h), pn, " in header/nav" if land else ""), "error" if land else None, s))
    for cm in _CLASS_ATTR.finditer(markup):
        cls = cm.group(1) or cm.group(2) or ""
        a = _TW_ANIMATE.search(cls)
        if not a or not _TW_ROUNDED_FULL.search(cls) or not _TW_TINY.search(cls):
            continue
        key = "tw:" + cls
        if key in seen:
            continue
        seen.add(key)
        land = _in_ranges(cm.start(), ranges)
        out.append(("animate-%s on tiny rounded-full element%s" % (a.group(1), " in header/nav" if land else ""),
                    "error" if land else None, None))
    return out


def rule_pulsing_dot(ctx):
    if not ctx.full_page:
        return []
    out = []
    for snip, sev, sel in scan_pulsing_dot(style_corpus(ctx), ctx.text):
        if selector_scoped_ignored(ctx, sel, "pulsing-dot"):
            continue
        hit = {"rule": "pulsing-dot", "snippet": snip}
        if sev:
            hit["severity"] = sev
        out.append(hit)
    return out


# ─── marquee ─────────────────────────────────────────────────────────────────────────────────────────────────────────
_MARQUEE_TAG = re.compile(r"<(?i:marquee)\b", A)
_TRANSLATE_X_PCT = re.compile(r"\b(?i:translate)(?:[xX]|3[dD])?\(" + WS + r"*(?:(?i:calc)\(" + WS + r"*)?(-?[0-9.]+)%", A)
_SCALE_OR_OPACITY = re.compile(r"\b(?i:scale)\(|\b(?i:opacity)" + WS + r"*:", A)
MARQUEE_MIN_TRAVEL_PCT = 20.0


def collect_marquee_keyframes(text):
    """css_scan.rs#collect_marquee_keyframes."""
    names = []
    for m, body, _ in keyframe_bodies(text):
        pct = [pf(x) for x in _TRANSLATE_X_PCT.findall(body)]
        if not pct or (len(pct) == 1 and _SCALE_OR_OPACITY.search(body)):
            continue
        travel = max(pct) - min(pct) if len(pct) > 1 else abs(pct[0])
        if travel >= MARQUEE_MIN_TRAVEL_PCT and m.group(1) not in names:
            names.append(m.group(1))
    return names


def scan_marquee(content, markup=None):
    """css_scan.rs#scan_css_text_for_marquee -> [(snippet, selector)]."""
    markup = content if markup is None else markup
    out = [("<marquee> element", "marquee")] if _MARQUEE_TAG.search(markup) else []
    kf = collect_marquee_keyframes(content)
    if not kf:
        return out
    seen = set()
    for g1, g2 in RULE_BLOCK.findall(content):
        sel = jtrim(g1)
        for n in infinite_animation_names(parse_decl_block(g2)):
            key = sel + " " + n
            if n in kf and key not in seen:
                seen.add(key)
                out.append(('%s — infinite horizontal loop animation "%s"' % (sel, n), sel))
    return out


def rule_marquee(ctx):
    if not ctx.full_page:
        return []
    return [("marquee", snip) for snip, sel in scan_marquee(style_corpus(ctx), ctx.text)
            if not selector_scoped_ignored(ctx, sel, "marquee")]


# ─── repeated-container-text ─────────────────────────────────────────────────────────────────────────────────────────
CONTAINER_TAGS = {"div", "section", "article", "aside", "main", "figure", "form", "fieldset", "details", "li"}
SKIP_TAGS = {"table", "select", "datalist", "nav", "menu"}
SKIP_ROLES = {"navigation", "menu", "menubar", "listbox", "grid", "tablist", "radiogroup"}
ICON_CLASS_RE = re.compile(r"(?i)icon|material-symbols|(?:^|%s)fa[srlbd]?(?:%s|-|$)" % (WS, WS))
MAX_DESCENDANTS = 250
TEXT_MIN, TEXT_MAX = 4, 48


def _in_skip(node):
    """closest(REPEATED_TEXT_SKIP_SELECTOR)."""
    n = node
    while n is not None and n.tag != "#document":
        if n.tag in SKIP_TAGS or (n.get("role") or "") in SKIP_ROLES or n.get("aria-hidden") == "true":
            return True
        n = n.parent
    return False


def _card_like(st):
    """text_rules.rs#is_repeated_text_container + is_card_like_from_props."""
    st = st or {}
    bs = st.get("box-shadow") or ""
    has_shadow = bool(bs) and bs != "none"
    sides = 0
    for sd in ("top", "right", "bottom", "left"):
        w = pf(st.get("border-%s-width" % sd) or "")
        if w == w and w >= 1:
            sides += 1
    has_border = sides >= 3
    r = pf(st.get("border-radius") or "")
    has_radius = r == r and r > 0
    bg = C.parse_color(st.get("background-color"))
    has_bg = bg is not None and bg[3] > 0.1
    return (has_shadow or has_border) and (has_radius or has_bg)


def _id_like(tok):
    """text_rules.rs#is_id_like_class."""
    return any(len(p) >= 4 and re.fullmatch(r"[0-9a-fA-F]+", p) and re.search(r"\d", p) for p in re.split(r"[-_]", tok))


def _sig(node):
    cls = sorted((c for c in node.classes if not _id_like(c)), key=lambda s: s.encode("utf-16-be"))
    return node.tag + ("." + ".".join(cls) if cls else "")


def _visible(node):
    return ((node.style or {}).get("display") or "").strip() != "none"


def rule_repeated_container_text(ctx):
    """page.rs#check_repeated_container_text_from_doc."""
    if not ctx.full_page or ctx.doc is None:
        return []
    conts = [n for n in ctx.doc.iter() if n.tag in CONTAINER_TAGS and not _in_skip(n) and _card_like(n.style)]
    cset = set(id(n) for n in conts)
    out = []
    for c in conts:
        if not _visible(c):
            continue
        desc = list(c.iter())
        if len(desc) > MAX_DESCENDANTS:
            continue
        groups = {}
        for d in desc:
            owned, a = False, d.parent
            while a is not None and a is not c:
                if id(a) in cset:
                    owned = True
                    break
                a = a.parent
            if owned or _in_skip(d) or ICON_CLASS_RE.search(d.get("class") or "") or not _visible(d):
                continue
            text = jtrim(_WS_RUN.sub(" ", " ".join(ch for ch in d.children if isinstance(ch, str))))
            if not (TEXT_MIN <= utf16_len(text) <= TEXT_MAX) or not re.search("[a-zA-Z]", text):
                continue
            chain, x = [], d
            while x is not None and x is not c:
                chain.append(_sig(x))
                x = x.parent
            groups.setdefault(text, []).append(">".join(chain))
        for text, sigs in groups.items():
            if len(sigs) >= 3 and len(set(sigs)) >= 3:
                sel = c.tag + ("." + ".".join(c.classes) if c.classes else "")
                out.append(("repeated-container-text", '"%s" rendered %d× in distinct spots inside %s'
                            % (utf16_prefix(text, 40), len(sigs), sel), c.line))
    return out


# ─── page-gated copy rules ───────────────────────────────────────────────────────────────────────────────────────────
def _page(rule_id, fn):
    def run(ctx):
        if not ctx.full_page:
            return []
        return [(rule_id, s) for s in fn(ctx.text)]
    run.__name__ = "rule_" + rule_id.replace("-", "_")
    return run


RULES = {
    "bounce-easing": rule_bounce_easing,
    "pulsing-dot": rule_pulsing_dot,
    "marquee": rule_marquee,
    "theater-slop-phrase": _page("theater-slop-phrase", scan_theater),
    "em-dash-overuse": _page("em-dash-overuse", analyze_em_dash),
    "marketing-buzzword": _page("marketing-buzzword", analyze_buzzwords),
    "aphoristic-cadence": _page("aphoristic-cadence", analyze_aphorisms),
    "repeated-container-text": rule_repeated_container_text,
}
