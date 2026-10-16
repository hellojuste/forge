#!/usr/bin/env python3
"""find.py — prior-art search: has this already been built, tried, or held upstream?

Earned by: lettuce `tools/find_solution.py` — falsifications print FIRST ("a dossier hit informs a build decision
while a falsification CHANGES it"); matched terms and fields print instead of a score ("a bare 0.87 is hand-typed
confidence wearing arithmetic"); an unreadable source is reported as unreadable, never as zero hits.
Sources, in order: (1) the falsification register (map/dirs.json "registers": {"negative": <dir or file>}; the
commons points it at brain/nodes/negative/), (2) map/catalog.json, (3) map/upstream.json (+ station overlay),
(4) map/atlas.json node labels. Not installed -> `not installed: <source>` (exit 0). Configured but unreadable ->
`UNREADABLE <path>` (exit 2). Zero hits -> `no hits · <records> records in <k> sources` (exit 0).
CLI: find.py <words...> [--json] [--root DIR] | --selftest
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402

STOP = {"the", "and", "for", "with", "that", "this", "from", "have", "has", "was", "are", "does", "any", "exist", "tool", "there"}


def words(s):
    return {w for w in re.findall(r"[a-z0-9]+", str(s).lower()) if len(w) >= 3 and w not in STOP}


def records(root):
    """Yields (source, records|None, note). records: list of (label, {field: text})."""
    reg = C.load_map(root, "dirs", required=False).get("registers") or {}
    neg = reg.get("negative")
    if not neg:
        yield "register", None, "not installed: falsification register"
    else:
        p = Path(root) / neg
        if not p.exists():
            yield "register", None, "not installed: %s" % neg
        else:
            rows = []
            for f in sorted(p.rglob("*.md")) if p.is_dir() else [p]:
                try:
                    text = f.read_text(encoding="utf-8")
                except OSError as e:
                    raise C.Unreadable("%s: %s" % (f, e))
                fm = dict(re.findall(r"^(title|hypothesis|verdict|retest|id): (.+)$", text, re.M))
                rows.append((fm.get("id", f.name).strip('"'), {k: v.strip('"') for k, v in fm.items()}))
            yield "register", rows, ""
    cat = C.load_map(root, "catalog", required=False).get("entries") or {}
    yield "catalog", [(k, {"title": e.get("title", ""), "purpose": e.get("purpose", ""), "solves": " ".join(e.get("solves") or []), "path": k})
                      for k, e in sorted(cat.items())], ""
    ups = C.load_map(root, "upstream", required=False).get("upstreams") or {}
    yield "upstream", [("upstream:" + k, {"what": e.get("what", ""), "when": e.get("when", ""), "solves": " ".join(e.get("solves") or []),
                                          "name": k}) for k, e in sorted(ups.items())], ""
    ap = C.map_dir(root) / "atlas.json"
    if not ap.exists():
        yield "atlas", None, "not installed: map/atlas.json"
    else:
        yield "atlas", [(n["id"], {"label": n.get("label", ""), "id": n["id"]}) for n in C.load_json(ap).get("nodes", [])], ""


def search(root, query):
    q = words(query)
    out, notes, n_rec, n_src = [], [], 0, 0
    for src, rows, note in records(root):
        if rows is None:
            notes.append(note)
            continue
        n_src += 1
        n_rec += len(rows)
        for label, fields in rows:
            matched = {f: sorted(q & words(v)) for f, v in fields.items() if q & words(v)}
            if matched:
                out.append({"source": src, "label": label, "matched": matched,
                            "kind": "REFUTATION" if src == "register" else src})
    return out, notes, n_rec, n_src


def selftest():
    import tempfile
    ok = True
    with tempfile.TemporaryDirectory() as t:
        Path(t, "map").mkdir()
        Path(t, "brain", "nodes", "negative").mkdir(parents=True)
        Path(t, "brain", "nodes", "negative", "core-0001--x.md").write_text('---\nid: "core-0001"\ntitle: "caching index speeds startup"\n---\n')
        Path(t, "map", "catalog.json").write_text(json.dumps({"entries": {"tools/cache.py": {"title": "index caching", "solves": []}}}))
        Path(t, "map", "dirs.json").write_text(json.dumps({"registers": {"negative": "brain/nodes/negative"}}))
        out, notes, n, k = search(t, "caching")
        if not (len(out) == 2 and out[0]["kind"] == "REFUTATION" and out[1]["label"] == "tools/cache.py"):
            ok = False
            print("FAIL register hit first", out)
        Path(t, "map", "dirs.json").write_text(json.dumps({}))
        _, notes, _, _ = search(t, "caching")
        if "not installed: falsification register" not in notes:
            ok = False
            print("FAIL unconfigured register prints not installed")
        Path(t, "map", "catalog.json").write_text("{corrupt")
        if main(["--root", t, "caching"]) != 2:
            ok = False
            print("FAIL corrupt configured source exits 2")
    print("selftest OK" if ok else "selftest FAILED")
    return 0 if ok else 1


def main(argv):
    root, argv = C.root_arg(argv)
    if "--selftest" in argv:
        return selftest()
    as_json = "--json" in argv
    query = " ".join(a for a in argv if a != "--json")
    if not query.strip():
        print("usage: find.py <words...> [--json]")
        return 2
    try:
        out, notes, n, k = search(root, query)
    except C.Unreadable as e:
        print("UNREADABLE %s" % e)
        return 2
    if as_json:
        print(json.dumps({"hits": out, "notes": notes, "records": n, "sources": k}, indent=1, sort_keys=True))
        return 0
    for h in out:
        print("%s %s  matched %s" % (h["kind"].upper(), h["label"], " · ".join("%s=%s" % (f, ",".join(w)) for f, w in sorted(h["matched"].items()))))
    for x in notes:
        print(x)
    print("%d hit(s) · %d records in %d sources" % (len(out), n, k) if out else "no hits · %d records in %d sources" % (n, k))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
