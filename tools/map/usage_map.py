#!/usr/bin/env python3
"""usage_map.py — every tool, hook, skill, workflow and upstream has a HOME and (ideally) a TRIGGER; plus observed use.

Earned by: lettuce L290 (151 of 251 entries had no trigger because the seeder read four trigger sources and missed
the three that actually ran tools; a generic path-literal scan then "minted 50 false triggers" -> every auto trigger
is a VERIFIABLE textual reference, never a guess, and under-deriving is safe), L368 (a function-body import counted
as a trigger edge -> module-level imports only), L294 (a hand flag nothing compared to source) and L265 (count unique
calls, not transcript rows). Retires: lettuce gen_usage_map.py's --apply door and INSTRUMENTS.yml FLAG gate.
Declared half -> map/usage.json (GENERATED, reproducible from tracked text). Observed half -> `--observed` reads the
gitignored .usage/log.jsonl (tools/map/hooks/usage_log.py), dedups by call id, and is NEVER written into usage.json.
Trigger sources: hook (settings.json command) · check (governance/checks*.json argv, map_check lists) · workflow
(code, comments stripped) · skill (SKILL.md names the path) · router (router/intents*.json first moves) · import
(module-level, in-repo, one hop from a triggered entry) · reference (upstream: a literal <lane>/<owner~repo>/ path).
Gates (exit 1): MISSING · STALE · INVALID · NO-HOME. Worklist: NO-TRIGGER · COLD. Knob: map M+.
CLI: --write | --check | --cold | --observed [--since ISO] | --list-outputs | --selftest  [--root DIR]. Exit 0/1/2.
"""
import ast
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402

TOOL = "tools/map/usage_map.py"
OUT = "map/usage.json"
SCOPE = ["tools/**/*.py", ".claude/hooks/**/*.py", ".claude/skills/*/SKILL.md", ".claude/workflows/*"]
LANES = ("repertoire", "upstream", "study", "nc-lane")
PATH_RX = re.compile(r"(?<![\w./-])((?:tools|\.claude)/[\w./-]+\.(?:py|sh|js|md))")


def kind_home(p):
    if p.endswith("/SKILL.md"):
        return "skill", "/" + p.split("/")[-2]
    if p.startswith(".claude/workflows/"):
        return "workflow", "workflow " + Path(p).stem
    if p.startswith(".claude/hooks/") or "/hooks/" in p:
        return "hook", "python3 " + p
    return "tool", ("python3 " + p) if p.endswith(".py") else p


def scope_files(root):
    domain, held, _ = C.domain_files(root)
    return [f for f in domain if C.any_glob(f, SCOPE)], domain + held


def _lines(root, rel, strip=True):
    text = C.read_text(root, rel) or ""
    return (C.strip_comments(text, Path(rel).suffix) if strip else text).splitlines()


def module_imports(root, rel):
    """Module-level imports that resolve in-repo: same dir, tools/, or a tools/ subpackage path."""
    try:
        tree = ast.parse(C.read_text(root, rel) or "")
    except SyntaxError:
        return []
    out = []
    for node in tree.body:
        names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module] if isinstance(node, ast.ImportFrom) and node.module else []
        for n in names:
            for cand in (str(Path(rel).parent / (n.replace(".", "/") + ".py")), "tools/%s.py" % n.replace(".", "/")):
                if (Path(root) / cand).is_file():
                    out.append((cand.replace("\\", "/"), node.lineno))
                    break
    return out


def derive(root):
    """[(target, source, ref, evidence)] from verifiable textual references only."""
    scope, files = scope_files(root)
    S = set(scope)
    out = []

    def scan(rel, source, strip=True):
        for i, l in enumerate(_lines(root, rel, strip), 1):
            for m in PATH_RX.findall(l):
                if m in S and m != rel:
                    out.append((m, source, rel, "%s:%d" % (rel, i)))
    for rel in [".claude/settings.json"] if (Path(root) / ".claude/settings.json").exists() else []:
        scan(rel, "hook", strip=False)
    for rel in sorted(f for f in files if re.fullmatch(r"governance/checks(\.d/[^/]+)?\.json", f)) + ["tools/map/map_check.py"]:
        if (Path(root) / rel).exists():
            scan(rel, "check", strip=rel.endswith(".py"))
    for rel in sorted(f for f in scope if f.startswith(".claude/workflows/")):
        scan(rel, "workflow")
    for rel in sorted(f for f in scope if f.endswith("/SKILL.md")):
        scan(rel, "skill", strip=False)
    for rel in sorted(f for f in files if re.fullmatch(r"router/(intents\.json|intents\.d/[^/]+\.json)", f)):
        scan(rel, "router", strip=False)
        for i, l in enumerate(_lines(root, rel, False), 1):
            for sk in re.findall(r'"skill"\s*:\s*"([\w-]+)"', l):
                p = ".claude/skills/%s/SKILL.md" % sk
                if p in S:
                    out.append((p, "router", rel, "%s:%d" % (rel, i)))
            for wf in re.findall(r'"workflow"\s*:\s*"([\w-]+)"', l):
                p = ".claude/workflows/%s.js" % wf
                if p in S:
                    out.append((p, "router", rel, "%s:%d" % (rel, i)))
    triggered = {t for t, _, _, _ in out}
    for rel in sorted(triggered):
        if rel.endswith(".py"):
            for tgt, ln in module_imports(root, rel):
                if tgt in S and tgt not in triggered:
                    out.append((tgt, "import", rel, "%s:%d" % (rel, ln)))
    return sorted(set(out))


def upstream_refs(root, names):
    scope, _ = scope_files(root)
    out = []
    for rel in scope:
        for i, l in enumerate(_lines(root, rel), 1):
            for lane, nm in re.findall(r"(?<![\w-])(%s)/([\w.-]+~[\w.-]+)/" % "|".join(LANES), l):
                if nm in names:
                    out.append(("upstream:" + nm, "reference", rel, "%s:%d" % (rel, i)))
    return out


def seed(root):
    scope, _ = scope_files(root)
    ups = C.load_map(root, "upstream", required=False).get("upstreams") or {}
    lock = C.load_json(Path(root) / "upstream" / "LOCK.json", {"rows": []}).get("rows", [])
    names = set(ups) | {str(r.get("repo", "")).replace("/", "~") for r in lock}
    hand = (C.load_map(root, "usage_hand", required=False).get("entries") or {})
    trig = derive(root) + upstream_refs(root, names)
    E = {}
    for p in scope:
        k, h = kind_home(p)
        E[p] = {"kind": k, "home": h}
    for nm in sorted(names):
        e = ups.get(nm, {})
        E["upstream:" + nm] = {"kind": "upstream", "home": e.get("entry") or e.get("url") or "upstream/LOCK.json row %s" % nm}
    for p, e in E.items():
        e["triggers"] = [{"source": s, "ref": r, "evidence": ev} for t, s, r, ev in trig if t == p]
        hd = hand.get(p) or {}
        e["hand"] = hd.get("hand") or []
        e["cold"] = hd.get("cold")
    return {"_generated_by": TOOL, "_note": "declared triggers only; observed use lives in .usage/log.jsonl (--observed)", "entries": E}, hand


def check(root):
    fresh, hand = seed(root)
    have = C.load_json(Path(root) / OUT, {"entries": {}}) if (Path(root) / OUT).exists() else {"entries": {}}
    V, W = [], []
    for p in sorted(set(fresh["entries"]) - set(have.get("entries") or {})):
        V.append("MISSING %s: in scope, no entry in %s" % (p, OUT))
    if not V and have != fresh:
        V.append("STALE %s differs from a fresh seed (python3 %s --write)" % (OUT, TOOL))
    for p, h in sorted(hand.items()):
        if p not in fresh["entries"]:
            V.append("INVALID %s: hand row for an unknown entry" % p)
        for row in h.get("hand") or []:
            ev = str(row.get("evidence", ""))
            f, _, ln = ev.rpartition(":")
            if not (row.get("source") and row.get("ref") and f and ln.isdigit() and (Path(root) / f).is_file()
                    and int(ln) <= len((C.read_text(root, f) or "").splitlines())):
                V.append("INVALID %s: hand trigger needs source, ref and resolving path:line evidence (%r)" % (p, ev))
        if h.get("cold") is not None:
            if not (isinstance(h["cold"], dict) and h["cold"].get("reason") and h["cold"].get("evidence")):
                V.append("INVALID %s: cold needs reason and evidence" % p)
            if h.get("hand") or (fresh["entries"].get(p) or {}).get("triggers"):
                V.append("INVALID %s: cold beside a trigger" % p)
    for rel in sorted(Path(root).glob("router/intents*.json")) + sorted(Path(root).glob("router/intents.d/*.json")):
        for i, l in enumerate(rel.read_text(encoding="utf-8").splitlines(), 1):
            for m in PATH_RX.findall(l):
                if not (Path(root) / m).exists():
                    V.append("INVALID %s:%d names %s, which does not exist" % (rel.relative_to(root).as_posix(), i, m))
    for p, e in sorted(fresh["entries"].items()):
        if not e.get("home"):
            V.append("NO-HOME %s" % p)
        if not e["triggers"] and not e["hand"] and not e["cold"]:
            W.append("NO-TRIGGER %s" % p)
        if e["cold"]:
            W.append("COLD %s: %s" % (p, e["cold"].get("reason")))
    return V, W, len(fresh["entries"])


def observed(root, since=None):
    fresh, _ = seed(root)
    E = fresh["entries"]
    seen, used = set(), {}
    log = Path(root) / ".usage" / "log.jsonl"
    for l in log.read_text(encoding="utf-8").splitlines() if log.exists() else []:
        try:
            r = json.loads(l)
        except ValueError:
            continue
        if since and r.get("ts", "") < since:
            continue
        key = r.get("call") or (r.get("session"), r.get("ts"), r.get("tool"), r.get("target"))
        if key in seen:
            continue
        seen.add(key)
        t = str(r.get("target") or "")
        if r.get("kind") == "skill" and "/" not in t:
            t = ".claude/skills/%s/SKILL.md" % t
        elif r.get("kind") == "upstream":
            parts = t.split("/")
            t = "upstream:" + parts[1] if len(parts) > 1 else t
        used[t] = max(used.get(t, ""), r.get("ts", ""))
    q = {"declared & used": [], "declared & unused": [], "undeclared & used": [], "neither": []}
    for p, e in sorted(E.items()):
        d = bool(e["triggers"] or e["hand"])
        q[("declared & " if d else ("undeclared & " if p in used else "")) + ("used" if p in used else ("unused" if d else "neither"))].append(p)
    q["undeclared & used"] += sorted(t for t in used if t not in E)
    lines = ["usage observed: %d unique call(s) · %d entries" % (len(seen), len(E))]
    for k, v in q.items():
        lines.append("%s: %d / %d%s" % (k, len(v), len(E), "".join("\n  %s%s" % (x, (" last_seen " + used[x]) if x in used else "") for x in v[:20])))
    return "\n".join(lines), q, len(seen)


def selftest():
    import tempfile
    ok = True
    with tempfile.TemporaryDirectory() as t:
        files = {".claude/settings.json": '{"hooks": {"PreToolUse": [{"hooks": [{"command": "python3 tools/wired.py"}]}]}}',
                 "tools/wired.py": "import os\nimport helper_mod\n\ndef f():\n    import lazy_mod\n",
                 "tools/helper_mod.py": "x = 1\n", "tools/lazy_mod.py": "x = 1\n", "tools/commented.py": "x = 1\n",
                 "tools/other.py": "# runs tools/commented.py\nprint(1)\n", "map/upstream.json": '{"upstreams": {}}'}
        for f, x in files.items():
            Path(t, f).parent.mkdir(parents=True, exist_ok=True)
            Path(t, f).write_text(x)
        Path(t, "station.json").write_text('{"name": "x", "knobs": {"map": "M"}}')
        E = seed(t)[0]["entries"]
        got = {p: sorted(x["source"] for x in e["triggers"]) for p, e in E.items()}
        want = {"tools/wired.py": ["hook"], "tools/helper_mod.py": ["import"], "tools/lazy_mod.py": [], "tools/commented.py": []}
        for p, w in want.items():
            if got.get(p) != w:
                ok = False
                print("FAIL trigger derivation", p, got.get(p), "want", w)
        Path(t, OUT).write_text(C.dump_json(seed(t)[0]))
        for name, hand in (("hand row without evidence", {"tools/other.py": {"hand": [{"source": "manual", "ref": "x"}]}}),
                           ("cold beside a trigger", {"tools/wired.py": {"cold": {"reason": "r", "evidence": "tools/wired.py:1"}}})):
            Path(t, "map", "usage_hand.json").write_text(json.dumps({"entries": hand}))
            Path(t, OUT).write_text(C.dump_json(seed(t)[0]))
            if not any(v.startswith("INVALID") for v in check(t)[0]):
                ok = False
                print("FAIL", name)
        Path(t, "map", "usage_hand.json").write_text(json.dumps({"entries": {}}))
        Path(t, OUT).write_text(C.dump_json(seed(t)[0]))
        if check(t)[0]:
            ok = False
            print("FAIL clean", check(t)[0])
        Path(t, "tools", "new.py").write_text("x\n")
        if not any(v.startswith("MISSING tools/new.py") for v in check(t)[0]):
            ok = False
            print("FAIL MISSING new tool")
        Path(t, ".usage").mkdir()
        ev = {"ts": "2026-10-16T00:00:00Z", "session": "s", "call": "c1", "tool": "Bash", "kind": "script", "target": "tools/wired.py"}
        Path(t, ".usage", "log.jsonl").write_text(json.dumps(ev) + "\n" + json.dumps(ev) + "\n")
        _, q, n = observed(t)
        if n != 1 or q["declared & used"] != ["tools/wired.py"] or sum(len(v) for v in q.values()) != len(seed(t)[0]["entries"]):
            ok = False
            print("FAIL observed dedup/quadrants", n, q)
    print("selftest OK" if ok else "selftest FAILED")
    return 0 if ok else 1


def main(argv):
    root, argv = C.root_arg(argv)
    if "--selftest" in argv:
        return selftest()
    name = "cold" if "--cold" in argv else "usage"
    if not C.map_at_least(root, "M"):
        if "--list-outputs" in argv:
            return 0
        print(C.skipped(name, "knob map=%s" % C.knob(root, "map")))
        return 0
    try:
        if "--list-outputs" in argv:
            print(OUT)
            return 0
        if "--write" in argv:
            print("usage: %s" % ("wrote " + OUT if C.write_if_changed(Path(root) / OUT, C.dump_json(seed(root)[0])) else "unchanged"))
            return 0
        if "--observed" in argv:
            since = argv[argv.index("--since") + 1] if "--since" in argv else None
            print(observed(root, since)[0])
            return 0
        V, W, d = check(root)
    except C.Unreadable as e:
        print("%s: UNREADABLE %s" % (name, e))
        return 2
    if name == "cold":
        print(C.headline("cold", 0, len(W), d))
        print("\n".join(W))
        return 0
    print(C.headline("usage", len(V), len(W), d))
    for x in V + W:
        print(x)
    return 1 if V else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
