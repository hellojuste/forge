#!/usr/bin/env python3
"""gen_atlas.py — the addressable graph of the station: one id space, a census derived from owners, edges with evidence.

Earned by: lettuce docs/ARTIFACTS.md (2026-08-26: two registry pages were stale, most counts by about 2x, and nothing
regenerated them), docs/atlas/README.md ("the knowledge of how to rebuild it lives only in the transcript of the
session that made it") and G16.1/RAT-058 (the drawing and the hub shared NO id — "the intersection at 0" — so any
diffusion stayed in one half). Hence: numbers are never typed (census == sum of owner counts), every edge carries
`path:line` evidence that is re-read, and the mermaid ids ARE the atlas ids. Retires: lettuce graph.yml geometry,
render_atlas.py and CROSSWALK.yml (one id space by construction). The brain's `map:<id>` touches resolve here
(`--ids`, `--neighbours`).
Gates (exit 1): DRIFT · UNDECLARED · CENSUS · DANGLING · EVIDENCE. Worklist: ORPHANS · COMPONENTS. Knob: map M+
(edges in/wires/runs/ports-from); L adds imports/routes and --near.
CLI: --write | --check | --orphans | --show <id|word> | --ids | --neighbours | --near <id> | --list-outputs | --selftest
     [--root DIR]. Exit 0/1/2.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402
import usage_map as U  # noqa: E402

TOOL = "tools/map/gen_atlas.py"
OUTS = ["map/atlas.json", "map/ATLAS.md"]
LANES = U.LANES


def build(root):
    schema = C.load_map(root, "atlas_schema")
    L = C.map_at_least(root, "L")
    dirs = C.load_map(root, "dirs", required=False).get("dirs") or {}
    scope, files = U.scope_files(root)
    nodes, edges = {}, []

    def node(i, cls, label, source):
        nodes[i] = {"id": i, "class": cls, "label": label, "source": source}
    dirs_lines = (C.read_text(root, "map/dirs.json") or "").splitlines()
    for d in sorted(dirs):
        node("dir:" + d, "dir", d + "/", "map/dirs.json")
    for p in scope:
        k, _ = U.kind_home(p)
        if k == "skill":
            node("skill:" + p.split("/")[-2], "skill", p.split("/")[-2], p)
        elif k == "workflow":
            node("workflow:" + Path(p).stem, "workflow", Path(p).stem, p)
        else:
            node("tool:" + p, "tool", Path(p).name, p)
    by_path = {n["source"]: i for i, n in nodes.items() if n["class"] in ("skill", "workflow", "tool")}
    settings = C.load_json(Path(root) / ".claude/settings.json", {}) if (Path(root) / ".claude/settings.json").exists() else {}
    slines = (C.read_text(root, ".claude/settings.json") or "").splitlines()
    for ev, groups in sorted((settings.get("hooks") or {}).items()):
        for g in groups:
            for n, h in enumerate(g.get("hooks") or []):
                hid = "hook:%s:%s:%d" % (ev, g.get("matcher") or "*", n)
                node(hid, "hook", "%s %s" % (ev, g.get("matcher") or "*"), ".claude/settings.json")
                for m in U.PATH_RX.findall(h.get("command", "")):
                    ln = next((i for i, l in enumerate(slines, 1) if h.get("command", "") and json.dumps(h["command"])[1:-1] in l), 0)
                    if m in by_path:
                        edges.append({"from": hid, "to": by_path[m], "kind": "wires", "evidence": ".claude/settings.json:%d" % ln, "token": m})
    ups = C.load_map(root, "upstream", required=False).get("upstreams") or {}
    lock = C.load_json(Path(root) / "upstream" / "LOCK.json", {"rows": []}).get("rows", [])
    unames = sorted(set(ups) | {str(r.get("repo", "")).replace("/", "~") for r in lock})
    for nm in unames:
        node("upstream:" + nm, "upstream", nm, "map/station_upstream.json" if nm in ups else "upstream/LOCK.json")
    if L:
        for rel in sorted(f for f in files if re.fullmatch(r"router/(intents\.json|intents\.d/[^/]+\.json)", f)):
            for row in C.load_json(Path(root) / rel, {}).get("intents", []):
                node("intent:" + row["name"], "intent", row["name"], rel)
    for i, n in sorted(nodes.items()):
        if n["class"] in ("skill", "workflow", "tool"):
            best = max((d for d in dirs if n["source"].startswith(d.rstrip("/") + "/")), key=len, default=None)
            if best:
                ln = next((k for k, l in enumerate(dirs_lines, 1) if '"%s"' % best in l), 0)
                edges.append({"from": i, "to": "dir:" + best, "kind": "in", "evidence": "map/dirs.json:%d" % ln, "token": '"%s"' % best})
    for p in scope:
        src = by_path.get(p)
        for k, l in enumerate(U._lines(root, p, strip=not p.endswith(".md")), 1):
            for m in U.PATH_RX.findall(l):
                if m in by_path and m != p and nodes[by_path[m]]["class"] == "tool":
                    edges.append({"from": src, "to": by_path[m], "kind": "runs", "evidence": "%s:%d" % (p, k), "token": m})
            for lane, nm in re.findall(r"(?<![\w-])(%s)/([\w.-]+~[\w.-]+)/" % "|".join(LANES), l):
                if nm in unames:
                    edges.append({"from": src, "to": "upstream:" + nm, "kind": "ports-from", "evidence": "%s:%d" % (p, k), "token": "%s/%s/" % (lane, nm)})
        if L and p.endswith(".py"):
            for tgt, ln in U.module_imports(root, p):
                if tgt in by_path:
                    edges.append({"from": src, "to": by_path[tgt], "kind": "imports", "evidence": "%s:%d" % (p, ln), "token": Path(tgt).stem})
    cat = C.load_map(root, "catalog", required=False).get("entries") or {}
    clines = (C.read_text(root, "map/catalog.json") or "").splitlines()
    for p, e in sorted(cat.items()):
        for kin in e.get("kin") or []:
            if kin.startswith("upstream:") and kin in nodes and p in by_path:
                ln = next((k for k, l in enumerate(clines, 1) if kin in l), 0)
                edges.append({"from": by_path[p], "to": kin, "kind": "ports-from", "evidence": "map/catalog.json:%d" % ln, "token": kin})
    if L:
        for rel in sorted(f for f in files if re.fullmatch(r"router/(intents\.json|intents\.d/[^/]+\.json)", f)):
            rl = (C.read_text(root, rel) or "").splitlines()
            for row in C.load_json(Path(root) / rel, {}).get("intents", []):
                fm = (row.get("router") or {}).get("first_move") or {}
                tg = [("skill:" + fm["skill"], '"%s"' % fm["skill"])] if fm.get("skill") else []
                tg += [("workflow:" + fm["workflow"], '"%s"' % fm["workflow"])] if fm.get("workflow") else []
                tg += [(by_path[m], m) for m in U.PATH_RX.findall(json.dumps(fm)) if m in by_path]
                for t, tok in tg:
                    if t in nodes:
                        ln = next((k for k, l in enumerate(rl, 1) if tok in l), 0)
                        edges.append({"from": "intent:" + row["name"], "to": t, "kind": "routes", "evidence": "%s:%d" % (rel, ln), "token": tok})
    uniq = {(e["from"], e["to"], e["kind"]): e for e in edges}
    edges = [uniq[k] for k in sorted(uniq)]
    census = {c: sum(1 for n in nodes.values() if n["class"] == c) for c in sorted({n["class"] for n in nodes.values()})}
    census["total"] = len(nodes)
    return {"_generated_by": TOOL, "census": census, "nodes": [nodes[k] for k in sorted(nodes)], "edges": edges}, schema


def mermaid_id(i):
    return re.sub(r"[^A-Za-z0-9_]", "_", i)


def render_md(atlas, cap=60):
    L = ["<!-- GENERATED by %s from the station tree + map/*.json — run python3 %s --write -->" % (TOOL, TOOL),
         "owner: map/atlas_schema.json · status: GENERATED · date: see git log · supersedes: none · audit: python3 %s --check" % TOOL, "",
         "# Atlas", "", "census: " + " · ".join("%s %d" % (k, v) for k, v in sorted(atlas["census"].items())), "",
         "One id space: the mermaid ids below are the atlas ids (non-alphanumerics -> `_`). Where is X? `python3 %s --show <id|word>`." % TOOL, ""]
    labels = {n["id"]: n["label"] for n in atlas["nodes"]}
    views = [("Dirs and what is in them", ["in"]), ("Hooks and the tools they wire", ["wires"]),
             ("Intent -> workflow/skill -> tool -> upstream", ["routes", "runs", "ports-from"])]
    for title, kinds in views:
        es = [e for e in atlas["edges"] if e["kind"] in kinds]
        ids = sorted({e["from"] for e in es} | {e["to"] for e in es})
        L += ["## %s" % title, ""]
        if not es:
            L += ["(no edges of kind %s)" % ", ".join(kinds), ""]
        elif len(ids) > cap:
            L += ["%d nodes > cap %d: table instead of a hairball." % (len(ids), cap), "", "| from | kind | to | evidence |", "|---|---|---|---|"]
            L += ["| `%s` | %s | `%s` | %s |" % (e["from"], e["kind"], e["to"], e["evidence"]) for e in es] + [""]
        else:
            L += ["```mermaid", "flowchart LR"] + ['  %s["%s"]' % (mermaid_id(i), labels.get(i, i).replace('"', "'")) for i in ids]
            L += ["  %s -->|%s| %s" % (mermaid_id(e["from"]), e["kind"], mermaid_id(e["to"])) for e in es] + ["```", ""]
    return "\n".join(L)


def check(root):
    fresh, schema = build(root)
    V, W = [], []
    have = C.load_json(Path(root) / OUTS[0], {}) if (Path(root) / OUTS[0]).exists() else {}
    if C.read_text(root, OUTS[0]) != C.dump_json(fresh) or C.read_text(root, OUTS[1]) != render_md(fresh):
        V.append("DRIFT %s differ from their render (python3 %s --write)" % (" / ".join(OUTS), TOOL))
    nc, ek = schema.get("node_classes") or {}, schema.get("edge_kinds") or {}
    for c in sorted({n["class"] for n in have.get("nodes", [])} - set(nc)):
        V.append("UNDECLARED node class %s" % c)
    for k in sorted({e["kind"] for e in have.get("edges", [])}):
        if k not in ek or ek[k].get("status") != "derived":
            V.append("UNDECLARED edge kind %s (absent or not derived)" % k)
    hc = {}
    for n in have.get("nodes", []):
        hc[n["class"]] = hc.get(n["class"], 0) + 1
    for c in sorted(set(hc) | {k for k in fresh["census"] if k != "total"}):
        if hc.get(c, 0) != fresh["census"].get(c, 0):
            V.append("CENSUS %s: atlas %d, owners %d" % (c, hc.get(c, 0), fresh["census"].get(c, 0)))
    ids = {n["id"] for n in have.get("nodes", [])}
    for e in have.get("edges", []):
        if e["from"] not in ids or e["to"] not in ids:
            V.append("DANGLING %s -%s-> %s" % (e["from"], e["kind"], e["to"]))
        f, _, ln = e.get("evidence", "").rpartition(":")
        lines = (C.read_text(root, f) or "").splitlines()
        if not (ln.isdigit() and 0 < int(ln) <= len(lines) and e.get("token", "") in lines[int(ln) - 1].replace('\\"', '"')):
            V.append("EVIDENCE %s -%s-> %s: %s no longer holds %r" % (e["from"], e["kind"], e["to"], e.get("evidence"), e.get("token")))
    deg = {}
    for e in fresh["edges"]:
        deg[e["from"]] = deg.get(e["from"], 0) + 1
        deg[e["to"]] = deg.get(e["to"], 0) + 1
    W += ["ORPHAN %s" % n["id"] for n in fresh["nodes"] if n["class"] != "dir" and not deg.get(n["id"])]
    return V, W, fresh["census"]["total"], fresh


def components(atlas):
    adj = {n["id"]: set() for n in atlas["nodes"]}
    for e in atlas["edges"]:
        adj[e["from"]].add(e["to"])
        adj[e["to"]].add(e["from"])
    seen, sizes = set(), []
    for s in adj:
        if s in seen:
            continue
        stack, k = [s], 0
        seen.add(s)
        while stack:
            x = stack.pop()
            k += 1
            for y in adj[x] - seen:
                seen.add(y)
                stack.append(y)
        sizes.append(k)
    return sorted(sizes, reverse=True)


def neighbours(atlas):
    nb = {n["id"]: set() for n in atlas["nodes"]}
    for e in atlas["edges"]:
        nb[e["from"]].add(e["to"])
        nb[e["to"]].add(e["from"])
    return nb


def selftest():
    import tempfile
    ok = True
    with tempfile.TemporaryDirectory() as t:
        files = {"map/dirs.json": json.dumps({"dirs": {"tools": {"role": "r"}, ".claude": {"role": "r"}}}, indent=1),
                 "map/atlas_schema.json": json.dumps({"node_classes": {c: {} for c in ("dir", "skill", "workflow", "tool", "hook", "upstream", "intent")},
                                                      "edge_kinds": {k: {"status": "derived"} for k in ("in", "wires", "runs", "imports", "ports-from", "routes")}}),
                 "map/station_upstream.json": json.dumps({"upstreams": {"o~r": {"mode": "reference"}}}),
                 ".claude/settings.json": json.dumps({"hooks": {"Stop": [{"hooks": [{"command": "python3 tools/hook_t.py"}]}]}}),
                 ".claude/skills/sk/SKILL.md": "---\nname: sk\n---\n!`python3 tools/run_me.py`\n",
                 "tools/run_me.py": "import os\n", "tools/hook_t.py": "import lib_a\n\ndef f():\n    import lib_b\n",
                 "tools/lib_a.py": "x = 1\n", "tools/lib_b.py": "x = 1\n", "tools/port.py": "# see\nSRC = 'repertoire/o~r/x.md'\n"}
        for f, x in files.items():
            Path(t, f).parent.mkdir(parents=True, exist_ok=True)
            Path(t, f).write_text(x)
        a, _ = build(t)
        es = {(e["from"], e["kind"], e["to"]) for e in a["edges"]}
        for want, present in ((("skill:sk", "runs", "tool:tools/run_me.py"), True), (("hook:Stop:*:0", "wires", "tool:tools/hook_t.py"), True),
                              (("tool:tools/hook_t.py", "imports", "tool:tools/lib_a.py"), True), (("tool:tools/hook_t.py", "imports", "tool:tools/lib_b.py"), False),
                              (("tool:tools/port.py", "ports-from", "upstream:o~r"), True)):
            if (want in es) != present:
                ok = False
                print("FAIL edge", want, "expected" if present else "not expected")
        Path(t, "map", "atlas.json").write_text(C.dump_json(a))
        Path(t, "map", "ATLAS.md").write_text(render_md(a))
        if check(t)[0]:
            ok = False
            print("FAIL clean", check(t)[0])
        Path(t, ".claude", "skills", "sk", "SKILL.md").write_text("---\nname: sk\n---\nnothing runs here now\n")
        if not any(v.startswith("EVIDENCE") for v in check(t)[0]):
            ok = False
            print("FAIL evidence edit must fail EVIDENCE")
        Path(t, ".claude", "skills", "sk", "SKILL.md").unlink()
        if not any(v.startswith("CENSUS skill") for v in check(t)[0]):
            ok = False
            print("FAIL deleted skill must fail CENSUS")
    print("selftest OK" if ok else "selftest FAILED")
    return 0 if ok else 1


def main(argv):
    root, argv = C.root_arg(argv)
    if "--selftest" in argv:
        return selftest()
    name = "orphans" if "--orphans" in argv else "atlas"
    if not C.map_at_least(root, "M"):
        if "--list-outputs" in argv:
            return 0
        if "--ids" in argv or "--neighbours" in argv:
            return 2  # no atlas on this station: the brain treats the map join as unavailable, never as empty
        print(C.skipped(name, "knob map=%s" % C.knob(root, "map")))
        return 0
    try:
        if "--list-outputs" in argv:
            print("\n".join(OUTS))
            return 0
        if "--ids" in argv or "--neighbours" in argv or "--show" in argv or "--near" in argv:
            a = C.load_json(Path(root) / OUTS[0])
            nb = neighbours(a)
            if "--ids" in argv:
                print("\n".join(n["id"] for n in a["nodes"]))
            elif "--neighbours" in argv:
                print("\n".join("%s\t%s" % (i, ",".join(sorted(v))) for i, v in sorted(nb.items())))
            elif "--show" in argv:
                q = " ".join(argv[argv.index("--show") + 1:]).lower()
                hits = [n for n in a["nodes"] if q == n["id"].lower()] or [n for n in a["nodes"] if q in n["id"].lower() or q in n["label"].lower()]
                for n in hits[:10]:
                    print("%s (%s) source %s" % (n["id"], n["class"], n["source"]))
                    for e in a["edges"]:
                        if n["id"] in (e["from"], e["to"]):
                            print("  %s -%s-> %s  [%s]" % (e["from"], e["kind"], e["to"], e["evidence"]))
                print("%d node(s) matched of %d" % (len(hits), len(a["nodes"])))
            else:
                if not C.map_at_least(root, "L"):
                    print(C.skipped("near", "knob map=%s" % C.knob(root, "map")))
                    return 0
                q = argv[argv.index("--near") + 1]
                base = nb.get(q, set()) | {q}
                rank = sorted(((len(base & (v | {i})) / len(base | v | {i}), i, sorted(base & (v | {i}))) for i, v in nb.items() if i != q), key=lambda x: (-x[0], x[1]))
                for s, i, shared in [r for r in rank if r[0] > 0][:10]:
                    print("%s shares %s" % (i, ", ".join(shared)))
            return 0
        if "--write" in argv:
            a, _ = build(root)
            n = C.write_if_changed(Path(root) / OUTS[0], C.dump_json(a)) + C.write_if_changed(Path(root) / OUTS[1], render_md(a))
            print("atlas: wrote %d file(s) · census %d" % (n, a["census"]["total"]))
            return 0
        V, W, d, fresh = check(root)
    except C.Unreadable as e:
        print("%s: UNREADABLE %s" % (name, e))
        return 2
    sizes = components(fresh)
    comp = "COMPONENTS giant %d of %d nodes in %d component(s)" % (sizes[0] if sizes else 0, d, len(sizes))
    if name == "orphans":
        print(C.headline("orphans", 0, len(W), d))
        print("\n".join(W + [comp]))
        return 0
    print(C.headline("atlas", len(V), len(W), d))
    for x in V + W + [comp]:
        print(x)
    return 1 if V else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
