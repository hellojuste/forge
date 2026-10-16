#!/usr/bin/env python3
"""check_paths.py — every path a live document claims resolves (and, L tier, every grounded claim still matches its code).

Earned by: lettuce L205 (a tree move rewrote code constants but never scanned prose: CLAUDE.md had 11 of 56 path claims
unresolved, and `readme --check` passed because it faithfully rendered a dead path), L276 (workflow stage prompts named
13 dead paths because the check never read .claude/workflows: a worker is sent to a file that is not there), L285
(78 code lines built paths from retired dirs) and R131-R133 (`ground.py`: a prose claim cannot silently outlive the
code body it describes). Retires: lettuce audit_paths code_roots (root computed once in _common.ROOT).
A claim: a backticked token (workflow files: also bare slash-tokens) after stripping :line/#anchor/§, containing '/',
no whitespace or glob/meta chars, not a URL/absolute/~/.., not a git ref, whose FIRST SEGMENT is a current root entry
or a `moved_from` root. A line carrying was/formerly/moved/retired/superseded is negation-scoped. Docs under held lanes
are never scanned (their claims are their own). On main, a claim matching map/dirs.json "station_only" globs is not
gated (those paths exist only on station branches); on a station it must resolve.
Gate (exit 1): an unresolved live claim (`doc:line claim [proposal]`). `--fix` rewrites only a unique moved_from
candidate. `--code` (L): string literals rooted at a moved_from dir or holding the checkout's absolute path.
`--ground` (L, off by default): FRESH / CHANGED (worklist) / GONE + UNVERIFIED (gates); `--mint <key>` prints a record.
CLI: --check | --fix | --code | --ground | --mint <key> | --selftest  [--root DIR]. Exit 0/1/2.
"""
import ast
import hashlib
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402

NEG = re.compile(r"\b(was|formerly|moved|retired|superseded)\b", re.I)
BAD = set(" \t*?<>{}[]$=(),|'\"")
REFS = ("origin/", "refs/", "feature/", "heads/", "remotes/", "station/")


def roots(root, reg):
    cur = {e for e in os.listdir(root) if e != ".git"}
    moved = {}
    for d, e in (reg.get("dirs") or {}).items():
        for old in e.get("moved_from") or []:
            moved.setdefault(old.rstrip("/"), []).append(d.rstrip("/"))
    return cur, moved


def claims(text, workflow):
    for i, line in enumerate(text.splitlines(), 1):
        toks = re.findall(r"`([^`\n]+)`", line)
        if workflow:
            toks += re.findall(r"(?<![\w/.`-])((?:[\w.-]+/)+[\w.-]+)", line)
        for tk in toks:
            yield i, line, re.split(r"[#§]|:(?=\d)", tk.strip())[0]


def is_claim(tok, cur, moved):
    if "/" not in tok or any(c in BAD for c in tok) or "://" in tok or tok.startswith(("/", "~")) or ".." in tok.split("/"):
        return False
    if tok.startswith(REFS):
        return False
    first = tok.split("/")[0]
    return first in cur or first in moved


def resolves(root, tok, doc, tracked):
    t = tok.rstrip("/")
    if t in tracked or any(f.startswith(t + "/") for f in tracked):
        return True
    rel = os.path.normpath(os.path.join(os.path.dirname(doc), t)).replace(os.sep, "/")
    if rel in tracked or (Path(root) / rel).exists():
        return True
    if (Path(root) / t).exists():
        return True
    return C.is_git(root) and C.git(root, "check-ignore", "-q", t).returncode == 0


def station_only_match(tok, globs):
    """fix2-commons 3: a directory claim `<dir>/` (or `<dir>`) matches its tree glob `<dir>/**`.
    glob_match("upstream", "upstream/**") is False (the glob names the dir's CONTENTS), so a trailing-slash claim of a
    station-only dir was gated on main. Both spellings of the claim are tried against the glob and its dir stem."""
    t = tok.rstrip("/")
    for g in globs:
        if C.glob_match(t, g) or C.glob_match(tok, g):
            return True
        if g.endswith("/**") and (C.glob_match(t, g[:-3]) or C.glob_match(t + "/", g[:-2])):
            return True
    return False


def scan(root):
    reg = C.load_map(root, "dirs")
    cur, moved = roots(root, reg)
    domain, _, _ = C.domain_files(root)
    tracked = set(domain)
    docs = [f for f in domain if C.any_glob(f, reg.get("live_docs") or [])]
    out = []
    for doc in docs:
        text = C.read_text(root, doc) or ""
        for ln, line, tok in claims(text, doc.startswith(".claude/workflows/")):
            if not is_claim(tok, cur, moved) or NEG.search(line) or resolves(root, tok, doc, tracked):
                continue
            if not (Path(root) / "station.json").exists() and station_only_match(tok, reg.get("station_only") or []):
                continue  # station-only path named by a commons doc: absent on main by design (KIT_PLAN 3.3)
            first, rest = tok.split("/", 1)
            cands = [c for c in (new + "/" + rest for new in moved.get(first, [])) if resolves(root, c, doc, tracked)]
            out.append((doc, ln, tok, cands))
    return out, len(docs)


def fix(root, found):
    n = 0
    for doc, ln, tok, cands in found:
        if len(cands) == 1:
            p = Path(root) / doc
            lines = p.read_text(encoding="utf-8").split("\n")
            lines[ln - 1] = lines[ln - 1].replace(tok, cands[0])
            p.write_text("\n".join(lines), encoding="utf-8")
            n += 1
    return n


def code_scan(root):
    reg = C.load_map(root, "dirs")
    _, moved = roots(root, reg)
    domain, _, _ = C.domain_files(root)
    out, absroot = [], str(Path(root).resolve())
    for f in [x for x in domain if C.glob_match(x, "tools/**/*.py")]:
        src = C.read_text(root, f) or ""
        lines = src.splitlines()
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                line = lines[node.lineno - 1] if node.lineno <= len(lines) else ""
                if "# retired-dir: deliberate" in line:
                    continue
                if node.value.split("/")[0] in moved and "/" in node.value:
                    out.append("code_dead %s:%d %r" % (f, node.lineno, node.value))
                if absroot in node.value:
                    out.append("machine_path %s:%d" % (f, node.lineno))
    return out


def body_hash(root, key):
    m = re.fullmatch(r"(py:def|md:h):([^:]+)::([^#]+)", key)
    if not m:
        return None, "UNVERIFIED"
    kind, path, name = m.groups()
    text = C.read_text(root, path)
    if text is None:
        return None, "GONE"
    if kind == "py:def":
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return None, "UNVERIFIED"
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name.split(".")[-1]:
                if node.body and isinstance(node.body[0], ast.Expr) and isinstance(getattr(node.body[0], "value", None), ast.Constant):
                    node.body = node.body[1:] or [ast.Pass()]
                node.name = "§"
                return hashlib.sha256(ast.unparse(node).encode()).hexdigest()[:12], "OK"
        return None, "GONE"
    lines, sec, lvl = text.splitlines(), None, 0
    for l in lines:
        h = re.match(r"^(#+)\s+(.*)$", l)
        if sec is not None and h and len(h.group(1)) <= lvl:
            break
        if sec is None and h and re.sub(r"[^a-z0-9]+", "-", h.group(2).lower()).strip("-") == name:
            sec, lvl = [], len(h.group(1))
        elif sec is not None:
            sec.append(l)
    return (hashlib.sha256("\n".join(sec).encode()).hexdigest()[:12], "OK") if sec is not None else (None, "GONE")


def ground(root):
    reg = C.load_map(root, "dirs")
    domain, _, _ = C.domain_files(root)
    res = []
    for doc in [f for f in domain if C.any_glob(f, reg.get("live_docs") or [])]:
        for i, l in enumerate((C.read_text(root, doc) or "").splitlines(), 1):
            for rec in re.findall(r"grounds:\s*(\S+)", l):
                key, _, h = rec.rpartition("#")
                got, st = body_hash(root, key)
                res.append(("%s:%d" % (doc, i), rec, "FRESH" if got == h else ("CHANGED" if got else st)))
    return res


def selftest():
    import json
    import tempfile
    ok = True
    with tempfile.TemporaryDirectory() as t:
        reg = {"live_docs": ["CLAUDE.md", "docs/*.md"], "dirs": {"tools": {"moved_from": ["old"]}, "docs": {}, "upstream": {}, "a": {}, "b": {}}}
        files = {"map/dirs.json": json.dumps(reg), "tools/real.py": "def f():\n    '''doc'''\n    return 1\n", "a/x.md": "", "b/x.md": "",
                 "upstream/x~y/README.md": "`tools/nope.py`\n"}
        for f, x in files.items():
            Path(t, f).parent.mkdir(parents=True, exist_ok=True)
            Path(t, f).write_text(x)

        def run(doc):
            Path(t, "CLAUDE.md").write_text(doc)
            return scan(t)[0]
        cases = [("dead claim", "see `tools/dead.py`\n", 1), ("was-moved line", "this was moved from `tools/dead.py`\n", 0),
                 ("open/high/low is not a claim", "bands `open/high/low`\n", 0), ("clean", "`tools/real.py` and `tools/`\n", 0)]
        for name, doc, want in cases:
            if len(run(doc)) != want:
                ok = False
                print("FAIL", name, run(doc))
        found = run("run `old/real.py`\n")
        if not (fix(t, found) == 1 and "`tools/real.py`" in Path(t, "CLAUDE.md").read_text()):
            ok = False
            print("FAIL --fix rewrites a unique moved_from candidate")
        reg["dirs"]["a"]["moved_from"] = ["c"]
        reg["dirs"]["b"]["moved_from"] = ["c"]
        Path(t, "map", "dirs.json").write_text(json.dumps(reg))
        found = run("see `c/x.md`\n")
        if fix(t, found) != 0:
            ok = False
            print("FAIL --fix must refuse two candidates")
        # fix2-commons 3: on main a station-only DIRECTORY claim (trailing slash or bare) matches its `<dir>/**` glob
        reg["station_only"] = ["repertoire/**", "upstream/*.json", "station.json", "tools/station/**"]
        Path(t, "map", "dirs.json").write_text(json.dumps(reg))
        Path(t, "repertoire").mkdir(exist_ok=True)  # an (empty) root entry, so `repertoire/...` tokens are claims
        so = [("`repertoire/` dir claim", "held in `repertoire/`\n", 0), ("`repertoire/o~r/x.md` file claim", "see `repertoire/o~r/x.md`\n", 0),
              ("`tools/station/` dir claim", "see `tools/station/`\n", 0), ("`upstream/LOCK.json`", "see `upstream/LOCK.json`\n", 0),
              ("`tools/stationx/` is not tools/station/**", "see `tools/stationx/`\n", 1), ("`upstream/x~y/` is not upstream/*.json", "see `upstream/x~y/a.py`\n", 1)]
        for name, doc, want in so:
            if len(run(doc)) != want:
                ok = False
                print("FAIL station_only", name, run(doc))
        if not (station_only_match("repertoire/", ["repertoire/**"]) and station_only_match("repertoire", ["repertoire/**"])
                and not station_only_match("repertoirex/", ["repertoire/**"])):
            ok = False
            print("FAIL station_only_match dir stem")
        Path(t, "station.json").write_text("{}")
        if len(run("see `tools/station/`\n")) != 1:  # on a station the claim must resolve
            ok = False
            print("FAIL station_only must gate on a station")
        Path(t, "station.json").unlink()
        h, _ = body_hash(t, "py:def:tools/real.py::f")
        Path(t, "CLAUDE.md").write_text("grounds: py:def:tools/real.py::f#%s\n" % h)
        s1 = ground(t)[0][2]
        Path(t, "tools", "real.py").write_text("def f():\n    return 2\n")
        if not (s1 == "FRESH" and ground(t)[0][2] == "CHANGED"):
            ok = False
            print("FAIL grounding FRESH -> CHANGED")
    print("selftest OK" if ok else "selftest FAILED")
    return 0 if ok else 1


def main(argv):
    root, argv = C.root_arg(argv)
    if "--selftest" in argv:
        return selftest()
    try:
        if "--mint" in argv:
            key = argv[argv.index("--mint") + 1]
            h, st = body_hash(root, key)
            print("grounds: %s#%s" % (key, h) if h else "cannot mint %s: %s" % (key, st))
            return 0 if h else 1
        if "--ground" in argv:
            if not C.map_at_least(root, "L"):
                print(C.skipped("grounding", "knob map=%s" % C.knob(root, "map")))
                return 0
            res = ground(root)
            gates = [r for r in res if r[2] in ("GONE", "UNVERIFIED")]
            print(C.headline("grounding", len(gates), sum(r[2] == "CHANGED" for r in res), len(res)))
            print("\n".join("%s %s %s" % (r[2], r[0], r[1]) for r in res if r[2] != "FRESH"))
            return 1 if gates else 0
        found, ndocs = scan(root)
        extra = code_scan(root) if "--code" in argv and C.map_at_least(root, "L") else []
        if "--fix" in argv:
            print("paths: fixed %d of %d unresolved claim(s)" % (fix(root, found), len(found)))
            return 0
    except C.Unreadable as e:
        print("paths: UNREADABLE %s" % e)
        return 2
    print(C.headline("paths", len(found) + len(extra), 0, ndocs))
    for doc, ln, tok, cands in found:
        print("%s:%d  %s%s" % (doc, ln, tok, ("  [proposal: %s]" % " | ".join(cands)) if cands else ""))
    print("\n".join(extra))
    return 1 if found or extra else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
