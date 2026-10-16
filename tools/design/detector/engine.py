"""engine.py — load a target (file or folder), build the static context, run every rule module, collect findings.

Context API (what a rule module sees; rule modules live in rules_*.py and expose RULES = {rule_id: fn} where
fn(ctx) -> iterable of Hit):
  ctx.path        Path of the file
  ctx.kind        'html' | 'css' | 'source' (jsx/tsx/vue/svelte/astro/scss/sass: regex engine only)
  ctx.text        raw source text
  ctx.doc         dom.Node root (html only; None otherwise) — cascade already applied: node.style, node.pseudo
  ctx.sheet       css.Sheet of every <style> block + linked local stylesheets (+ the file itself for .css)
  ctx.css_text    the sheet's raw text + every style="" attribute (as `style="..."` lines)   [upstream style corpus]
  ctx.class_text  every class="" attribute value, one per line                              [upstream class corpus]
  ctx.full_page   True when the HTML has <!doctype>, <html> or <body> (page-level rules run only then)
  ctx.design      parsed DESIGN.md frontmatter dict (or None) — design-system-* rules run only with one
  ctx.elements()  every element in document order outside head/script/style/template
  ctx.line_of(text_or_index) -> 1-based line in ctx.text
Non-HTML files never reach rule modules: regex_engine.scan(ctx) handles them (RULE_IDS lists what it can emit).
A Hit is (rule_id, snippet) or (rule_id, snippet, line) or a dict {rule, snippet, line?, severity?, selector?}.
"""
import hashlib
import re
from pathlib import Path

from . import css as CSS
from . import dom as DOM

HTML_EXT = {".html", ".htm"}
CSS_EXT = {".css"}
SOURCE_EXT = {".jsx", ".tsx", ".js", ".ts", ".vue", ".svelte", ".astro", ".scss", ".sass", ".less", ".mdx"}
SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", ".astro", "__pycache__", ".upstream", "vendor"}


class Context:
    def __init__(self, path, text, kind, design=None):
        self.path = Path(path)
        self.text = text
        self.kind = kind
        self.design = design
        self.doc = None
        self.sheet = CSS.Sheet()
        self.full_page = False
        self.css_text = ""
        self.class_text = ""
        self.linked = []
        self.unread_stylesheet = False
        self._lines = None
        if kind == "html":
            self._build_html()
        elif kind == "css":
            self.sheet.add(text)
            self.css_text = CSS.strip_comments(text)

    def _build_html(self):
        self.full_page = DOM.is_full_page(self.text)
        # a fragment is parsed inside a virtual <body> so html/body/:root rules of its stylesheet reach it (same lines)
        self.doc = DOM.parse(self.text if self.full_page else "<body>" + self.text + "</body>")
        for node in self.doc.iter():
            if node.tag == "style":
                media = node.get("media", "")
                if not media or CSS.media_applies(media):
                    self.sheet.add(node.text_raw() if hasattr(node, "text_raw") else "".join(
                        c for c in node.children if isinstance(c, str)))
            elif node.tag == "link" and "stylesheet" in (node.get("rel") or "").lower():
                href = (node.get("href") or "").split("?")[0].split("#")[0]
                if href and not re.match(r"^(https?:)?//|^data:", href):
                    f = resolve_href(self.path, href)
                    if f.is_file():
                        self.sheet.add(f.read_text(encoding="utf-8", errors="replace"))
                        self.linked.append(f)
                    else:
                        self.unread_stylesheet = True
                elif href:
                    self.unread_stylesheet = True
        if not self.full_page and not self.linked:
            # a component fragment carries no <link>: read the stylesheets that sit beside it (components/*.css)
            for f in sorted(self.path.parent.glob("*.css")):
                self.sheet.add(f.read_text(encoding="utf-8", errors="replace"))
                self.linked.append(f)
        from . import tailwind
        CSS.cascade(self.doc, self.sheet, tailwind.class_decls)
        styles, classes = [], []
        for node in self.doc.iter():
            if node.get("style"):
                styles.append('style="%s"' % node.get("style"))
            if node.get("class"):
                classes.append(node.get("class"))
        self.css_text = "\n".join([self.sheet.text()] + styles)
        self.class_text = "\n".join(classes)

    def elements(self):
        out = []

        def walk(n, hidden_ctx):
            for c in n.elements():
                if c.tag in DOM.NON_RENDERED:
                    continue
                out.append(c)
                walk(c, hidden_ctx)
        if self.doc is not None:
            walk(self.doc, False)
        return out

    def line_of(self, needle):
        if isinstance(needle, int):
            return self.text.count("\n", 0, needle) + 1
        i = self.text.find(needle) if needle else -1
        return self.text.count("\n", 0, i) + 1 if i >= 0 else 0


def resolve_href(page, href):
    """A local stylesheet href -> Path. Relative hrefs resolve against the page's folder. A root-absolute href
    (/css/site.css) has no known site root offline, so try each ancestor folder as the root, then the href's
    trailing segments under the page's folder (the way a dev server mounted one level up would serve it)."""
    page = Path(page).resolve()
    if not href.startswith("/"):
        return (page.parent / href).resolve()
    parts = [p for p in href.split("/") if p]
    for root in [page.parent] + list(page.parents):
        cand = root.joinpath(*parts)
        if cand.is_file():
            return cand
    for i in range(1, len(parts)):
        cand = page.parent.joinpath(*parts[i:])
        if cand.is_file():
            return cand
    return page.parent.joinpath(*parts)


def kind_of(path):
    ext = Path(path).suffix.lower()
    if ext in HTML_EXT:
        return "html"
    if ext in CSS_EXT:
        return "css"
    if ext in SOURCE_EXT:
        return "source"
    return None


def collect(paths):
    """Expand files/folders into scannable files (sorted, deduped)."""
    out = []
    for p in paths:
        p = Path(p)
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and kind_of(f) and not (set(f.relative_to(p).parts[:-1]) & SKIP_DIRS):
                    out.append(f)
        elif p.is_file() and kind_of(p):
            out.append(p)
    seen, uniq = set(), []
    for f in out:
        r = f.resolve()
        if r not in seen:
            seen.add(r)
            uniq.append(f)
    return uniq


def load_design(start, explicit=None):
    """DESIGN.md frontmatter as a dict: the explicit path, else the nearest DESIGN.md walking up from start."""
    from . import design_md
    if explicit:
        f = Path(explicit)
        return design_md.parse(f.read_text(encoding="utf-8")) if f.is_file() else None
    d = Path(start).resolve()
    d = d if d.is_dir() else d.parent
    for cand in [d] + list(d.parents)[:4]:
        f = cand / "DESIGN.md"
        if f.is_file():
            return design_md.parse(f.read_text(encoding="utf-8"))
    return None


def rule_modules():
    from . import rules_color, rules_layout, rules_type, rules_motion_copy
    return [rules_color, rules_layout, rules_type, rules_motion_copy]


def norm_hit(h, ctx):
    if isinstance(h, dict):
        d = dict(h)
    elif len(h) == 2:
        d = {"rule": h[0], "snippet": h[1]}
    else:
        d = {"rule": h[0], "snippet": h[1], "line": h[2]}
    d.setdefault("line", 0)
    d["snippet"] = " ".join(str(d.get("snippet", "")).split())[:240]
    return d


def scan_file(path, registry, design=None):
    """-> (findings, ran rule ids). Runs static rules; the caller adds rendered rules."""
    from . import ignores
    kind = kind_of(path)
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    ctx = Context(path, text, kind, design)
    findings, ran = [], set()
    hits = []
    if kind == "html":
        for mod in rule_modules():
            for rid, fn in mod.RULES.items():
                if rid.startswith("design-system-") and design is None:
                    continue
                ran.add(rid)
                hits.extend(fn(ctx) or ())
    else:
        # upstream routes every non-HTML file (css, jsx, tsx, vue, svelte, astro, scss, sass) to its line-regex engine
        from . import regex_engine
        ran.update(regex_engine.RULE_IDS)
        hits.extend(regex_engine.scan(ctx))
    for h in hits:
        d = norm_hit(h, ctx)
        row = registry[d["rule"]]
        d.setdefault("severity", row["severity"])
        d.update({"name": row["name"], "category": row["category"], "file": str(path)})
        findings.append(d)
    findings = ignores.apply(findings, text)
    return findings, ran, ctx


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

