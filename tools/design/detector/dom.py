"""dom.py — a small, forgiving HTML DOM built on html.parser (stdlib).

Enough of the HTML tree-construction rules to analyse real pages statically: void elements, implied end tags for
p/li/dt/dd/tr/td/th/option, raw-text <script>/<style>, source line per element. Text is kept as child strings.
"""
from html.parser import HTMLParser

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
BLOCK_CLOSES_P = {"address", "article", "aside", "blockquote", "details", "div", "dl", "fieldset", "figcaption",
                  "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hgroup", "hr", "main",
                  "menu", "nav", "ol", "p", "pre", "section", "table", "ul"}
IMPLIED = {"li": {"li"}, "dt": {"dt", "dd"}, "dd": {"dt", "dd"}, "tr": {"tr"}, "td": {"td", "th"},
           "th": {"td", "th"}, "option": {"option"}, "thead": {"tbody", "tfoot"}, "tbody": {"tbody", "tfoot"}}
NON_RENDERED = {"script", "style", "template", "noscript", "head", "title", "meta", "link", "base"}


class Node:
    __slots__ = ("tag", "attrs", "children", "parent", "line", "style", "idx", "pseudo")

    def __init__(self, tag, attrs=None, parent=None, line=0):
        self.tag = tag
        self.attrs = attrs or {}
        self.children = []
        self.parent = parent
        self.line = line
        self.style = None   # computed style dict, filled by css.cascade
        self.idx = 0
        self.pseudo = {}    # {"before": {...}, "after": {...}}

    # --- tree helpers -------------------------------------------------------------------------------------------
    def elements(self):
        return [c for c in self.children if isinstance(c, Node)]

    def iter(self):
        for c in self.children:
            if isinstance(c, Node):
                yield c
                yield from c.iter()

    def ancestors(self):
        p = self.parent
        while p is not None and p.tag != "#document":
            yield p
            p = p.parent

    def get(self, name, default=None):
        return self.attrs.get(name, default)

    @property
    def classes(self):
        return (self.attrs.get("class") or "").split()

    @property
    def id(self):
        return self.attrs.get("id")

    def own_text(self):
        return " ".join(c for c in self.children if isinstance(c, str)).strip()

    def text(self):
        if self.tag in NON_RENDERED:
            return ""
        out = []
        for c in self.children:
            out.append(c if isinstance(c, str) else c.text())
        return "".join(out)

    def norm_text(self):
        return " ".join(self.text().split())

    def prev_element(self):
        if self.parent is None:
            return None
        sib = self.parent.elements()
        i = sib.index(self)
        return sib[i - 1] if i > 0 else None

    def next_element(self):
        if self.parent is None:
            return None
        sib = self.parent.elements()
        i = sib.index(self)
        return sib[i + 1] if i + 1 < len(sib) else None

    def selector(self):
        s = self.tag
        if self.id:
            s += "#" + self.id
        if self.classes:
            s += "." + ".".join(self.classes[:3])
        return s

    def path(self):
        parts = [self.selector()]
        for a in list(self.ancestors())[:2]:
            parts.append(a.selector())
        return " > ".join(reversed(parts))

    def __repr__(self):
        return "<%s line %d>" % (self.selector(), self.line)


class _Builder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.doc = Node("#document")
        self.cur = self.doc
        self.n = 0

    def _close_to(self, tags):
        node = self.cur
        while node is not None and node.tag != "#document":
            if node.tag in tags:
                self.cur = node.parent
                return True
            node = node.parent
        return False

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "p" or tag in BLOCK_CLOSES_P:
            if self.cur.tag == "p":
                self.cur = self.cur.parent
        if tag in IMPLIED and self.cur.tag in IMPLIED[tag]:
            self.cur = self.cur.parent
        if tag in ("td", "th") and self.cur.tag in ("td", "th"):
            self.cur = self.cur.parent
        node = Node(tag, {k.lower(): (v if v is not None else "") for k, v in attrs}, self.cur, self.getpos()[0])
        self.n += 1
        node.idx = self.n
        self.cur.children.append(node)
        if tag not in VOID:
            self.cur = node

    def handle_startendtag(self, tag, attrs):
        tag = tag.lower()
        node = Node(tag, {k.lower(): (v if v is not None else "") for k, v in attrs}, self.cur, self.getpos()[0])
        self.n += 1
        node.idx = self.n
        self.cur.children.append(node)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in VOID:
            return
        self._close_to({tag})

    def handle_data(self, data):
        if data:
            self.cur.children.append(data)


def parse(html):
    b = _Builder()
    b.feed(html)
    b.close()
    return b.doc


def is_full_page(html):
    low = html[:4000].lower()
    return "<html" in low or "<body" in low or "<!doctype" in low
