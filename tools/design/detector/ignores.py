"""ignores.py — upstream waivers: in-file comment directives and the element-scoped data-impeccable-ignore attribute.

Ports impeccable crates/foundation/src/inline_ignores.rs (parse_inline_ignores, is_inline_ignored,
apply_inline_ignores) and crates/html/src/adapters.rs#scoped_ignore_active. Apache-2.0 upstream; stdlib only.

Directives (any comment syntax; only the directive text is read):
  impeccable-disable [rules]            whole file
  impeccable-disable-line [rules]       the directive's own line
  impeccable-disable-next-line [rules]  the line after it
Rules are comma/space separated; none or `*` means every rule; text after ` -- ` or `:` is a reason.
A finding with line 0 (every static HTML finding, every page-level analyzer) honours only the file-wide form.
"""
import re

WS = "\t\n\x0b\x0c\r \xa0  -     　﻿"
_DIRECTIVE = re.compile(r"(?i:impeccable)-((?i:disable-next-line)|(?i:disable-line)|(?i:disable))\b[ \t]*([^\n\r]*)",
                        re.A)
_TRAILING_CLOSER = re.compile(r"[%s]*(?:\*/\}?|--+>|\*\}|#\}|%%>|\}\})[%s]*$" % (WS, WS))
_REASON_SEP = re.compile(r"[%s]*(?:--+|:)[%s]*" % (WS, WS))
_TOKEN_SPLIT = re.compile(r"[%s,]+" % WS)
_HAS_DIRECTIVE = re.compile(r"(?i:impeccable-disable)", re.A)


WS_CHARS = "\t\n\x0b\x0c\r \xa0     　﻿" + "".join(chr(c) for c in range(0x2000, 0x200b))


def _norm(token):
    # inline_ignores.rs#normalize_rule: JS trim + toLowerCase
    return token.strip(WS_CHARS).lower()


def _rule_list(remainder):
    # inline_ignores.rs#parse_rule_list
    text = _TRAILING_CLOSER.sub("", remainder, count=1).strip(WS_CHARS)
    m = _REASON_SEP.search(text)
    if m:
        text = text[:m.start()]
    tokens = [t for t in (_norm(x) for x in _TOKEN_SPLIT.split(text)) if t]
    if not tokens or "*" in tokens:
        return {"*"}
    return set(tokens)


def parse(text):
    """-> (file_rules, {line: rules}, {line: rules}) — inline_ignores.rs#parse_inline_ignores."""
    file_rules, line_rules, next_rules = set(), {}, {}
    text = text or ""
    if not _HAS_DIRECTIVE.search(text):
        return file_rules, line_rules, next_rules
    for i, line in enumerate(text.split("\n")):
        for m in _DIRECTIVE.finditer(line):
            variant = m.group(1).lower()
            rules = _rule_list(m.group(2) or "")
            if variant == "disable":
                file_rules |= rules
            elif variant == "disable-line":
                line_rules.setdefault(i + 1, set()).update(rules)
            else:
                next_rules.setdefault(i + 2, set()).update(rules)
    return file_rules, line_rules, next_rules


def _hit(rules, rule):
    return bool(rules) and ("*" in rules or rule in rules)


def is_ignored(rule_id, line, directives):
    """inline_ignores.rs#is_inline_ignored."""
    file_rules, line_rules, next_rules = directives
    rule = _norm(rule_id or "")
    if not rule:
        return False
    if _hit(file_rules, rule):
        return True
    try:
        line = float(line or 0)
    except (TypeError, ValueError):
        line = 0.0
    if line > 0 and line == int(line):
        k = int(line)
        return _hit(line_rules.get(k), rule) or _hit(next_rules.get(k), rule)
    return False


def apply(findings, text):
    """Drop findings waived by a directive in the same file (inline_ignores.rs#apply_inline_ignores).
    Findings are dicts with `rule` (or `antipattern`) and optional `line`."""
    if not findings:
        return findings
    d = parse(text)
    if not (d[0] or d[1] or d[2]):
        return findings
    return [f for f in findings if not is_ignored(f.get("rule") or f.get("antipattern"), f.get("line", 0), d)]


_ATTR_SPLIT = re.compile(r"[%s,]+" % WS)


def ignored(node, rule_id):
    """True when node or an ancestor carries data-impeccable-ignore covering rule_id (empty value or `*` = all).
    Port of adapters.rs#scoped_ignore_active."""
    rule = (rule_id or "").lower()
    n = node
    while n is not None and getattr(n, "tag", "#document") != "#document":
        attrs = getattr(n, "attrs", {}) or {}
        if "data-impeccable-ignore" in attrs:
            rules = [r for r in _ATTR_SPLIT.split(_norm(attrs.get("data-impeccable-ignore") or "")) if r]
            if not rules or "*" in rules or rule in rules:
                return True
        n = getattr(n, "parent", None)
    return False
