"""design_md.py — DESIGN.md frontmatter -> dict (stdlib YAML subset).

Ports impeccable crates/detect/src/design_system.rs `parse_frontmatter` / `parse_yaml_subset` / `parse_scalar`:
the first line must trim to `---` and a later line trimming to `---` closes the block (else None). Inside it only
indentation-nested maps and scalars are understood: no lists, no flow maps, no multi-line scalars. Blank lines and
`#` comment lines are skipped; ` #` after whitespace (outside quotes) starts an inline comment. A key with no value
opens a child map. Scalars: "double" (YAML escapes), 'single' ('' -> '), true/false, null/~, integers/floats, and
anything else as a raw string.
"""
import re

_INT = re.compile(r"^-?[0-9]+$")
_FLOAT = re.compile(r"^-?[0-9]*\.[0-9]+$")
_ESC = {"0": "\0", "a": "\x07", "b": "\x08", "t": "\t", "n": "\n", "v": "\x0b", "f": "\x0c", "r": "\r",
        "e": "\x1b", " ": " ", '"': '"', "/": "/", "\\": "\\", "N": "\x85", "_": "\xa0", "L": " ",
        "P": " "}


def _top_colon(s):
    quote, prev = None, None
    for i, ch in enumerate(s):
        if quote:
            if ch == quote and prev != "\\":
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == ":":
            return i
        prev = ch
    return -1


def _strip_comment(s):
    quote, prev = None, None
    for i, ch in enumerate(s):
        if quote:
            if ch == quote and prev != "\\":
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and i > 0 and prev is not None and prev.isspace():
            return s[:i].rstrip()
        prev = ch
    return s


def _unquote_key(k):
    if len(k) >= 2 and k[0] == k[-1] and k[0] in "\"'":
        return k[1:-1]
    if k in ('"', "'"):
        return ""
    return k


def _unescape(body):
    out, i = [], 0
    while i < len(body):
        ch = body[i]
        if ch != "\\" or i == len(body) - 1:
            out.append(ch)
            i += 1
            continue
        nx = body[i + 1]
        if nx in _ESC:
            out.append(_ESC[nx])
            i += 2
            continue
        n = {"x": 2, "u": 4, "U": 8}.get(nx)
        if n:
            hexs = body[i + 2:i + 2 + n]
            if len(hexs) == n and re.fullmatch(r"[0-9a-fA-F]+", hexs) and int(hexs, 16) <= 0x10FFFF:
                cp = int(hexs, 16)
                out.append(chr(cp) if not 0xD800 <= cp <= 0xDFFF else "�")
                i += 2 + n
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def _scalar(raw):
    s = raw.strip()
    if len(s) >= 2 and s[0] == s[-1] == '"':
        return _unescape(s[1:-1])
    if len(s) >= 2 and s[0] == s[-1] == "'":
        return s[1:-1].replace("''", "'")
    if s == "true":
        return True
    if s == "false":
        return False
    if s in ("null", "~"):
        return None
    if _INT.match(s) or _FLOAT.match(s):
        v = float(s)
        return int(v) if v.is_integer() and "." not in s else v
    return s


def parse_yaml_subset(yaml):
    root = {}
    stack = [(-1, root)]
    for raw in re.split(r"\r?\n", yaml):
        if not raw.strip() or re.match(r"^\s*#", raw):
            continue
        indent = len(raw) - len(raw.lstrip())
        content = raw[indent:]
        ci = _top_colon(content)
        if ci < 0:
            continue
        while len(stack) > 1 and stack[-1][0] >= indent:
            stack.pop()
        key = _unquote_key(content[:ci].strip())
        rest = _strip_comment(content[ci + 1:].strip())
        parent = stack[-1][1]
        if not rest:
            child = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _scalar(rest)
    return root


def parse(text):
    """DESIGN.md text -> frontmatter dict ({'typography': {...}, 'colors': {...}, 'rounded': {...}}), or None."""
    if text is None:
        return None
    lines = re.split(r"\r?\n", text)
    if not lines or lines[0].strip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return parse_yaml_subset("\n".join(lines[1:i]))
    return None
