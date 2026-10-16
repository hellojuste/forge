#!/usr/bin/env python3
"""upstream_check.py — every held upstream has a usage row, a full pin, live paths and visible instruction files.

Earned by: lettuce `vendor/USAGE.yml` ("without that, 47,000 vendored files are indistinguishable from no vendored
files"; "a tree with no entry point is a tree nobody opens") and two gaps lettuce never closed (PROGRAMME_MAPPING
2 M6): vendor trees were not pinned to a commit, and 4 vendored trees carried their own CLAUDE.md/AGENTS.md that
nothing listed (the leak risk). Retires: nothing in the kit (first upstream usage check); precedence itself is
owned by governance (`upstream/PRECEDENCE.json`), this file only points to it.

Inputs: `upstream/LOCK.json` (commons-upstream schema; the station's held trees) + `map/upstream.json` (commons:
empty of trees) overlaid by `map/station_upstream.json` (`upstreams.<owner~repo>`: what/when/entry/solves/
instructions/note, optional pinned.tree) + `map/tags.json`.
Gates (exit 1): NO-USAGE (a LOCK row with no usage row) · ORPHAN-DIR (a `<lane>/<owner~repo>/` dir with no LOCK row)
· ORPHAN-ENTRY (a usage row with no LOCK row, unless mode=reference) · DEAD (entry/licence/instructions path absent)
· TAG (solves tag undeclared) · PIN (LOCK sha not 40-hex, or a usage pinned.sha that differs) · EDITED (pinned.tree
!= git tree of the held path) · INSTRUCTIONS (agent files on disk != instructions[]).
Unreadable (exit 2): UNREADABLE (pinned.tree set but `git rev-parse HEAD:<lane>/<name>` failed - its rc is checked,
its echoed argument is never taken for a tree id).
Worklist (exit 0): WARN short sha, missing when/entry, no tree pin.
Re-pin (the EDITED remedy after a deliberate re-ingest): --pin-trees prints each held tree's git tree id computed
from the files on disk (pure stdlib: the git tree-object hash, no repo needed, so it works in a build dir before
any commit); --pin-trees --write records it as map/station_upstream.json upstreams.<name>.pinned {sha: LOCK sha, tree}.
CLI: --check | --list | --pin-trees [--write] | --selftest  [--root DIR]. Exit 0/1/2.
"""
import hashlib
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402

LANES = ("repertoire", "upstream", "study", "nc-lane")
AGENT = re.compile(r"(^|/)(_upstream_)?(CLAUDE\.md|CLAUDE\.local\.md|AGENTS\.md|GEMINI\.md|\.cursorrules|_?\.?mcp\.json)$|"
                   r"(^|/)(\.claude|_upstream_claude|\.cursor/rules|_upstream_claude-plugin)/|(^|/)\.github/copilot-instructions\.md$")


TREE_SKIP_DIRS = {".git", "__pycache__"}  # what commons .gitignore keeps out of every commit
TREE_SKIP_SUFFIX = (".pyc",)


def _obj(kind, data):
    return hashlib.sha1(b"%s %d\0" % (kind, len(data)) + data).hexdigest()


def tree_id(path):
    """git's tree id for the directory at <path> as `git add` would record it (None for a tree with no files)."""
    ents = []
    with os.scandir(path) as it:
        for e in it:
            if e.name in TREE_SKIP_DIRS or e.name.endswith(TREE_SKIP_SUFFIX):
                continue
            if e.is_symlink():
                ents.append((e.name, b"120000", _obj(b"blob", os.readlink(e.path).encode("utf-8", "surrogateescape"))))
            elif e.is_dir():
                sub = tree_id(e.path)
                if sub:
                    ents.append((e.name, b"40000", sub))
            elif e.is_file():
                with open(e.path, "rb") as fh:
                    blob = _obj(b"blob", fh.read())
                ents.append((e.name, b"100755" if os.stat(e.path).st_mode & 0o111 else b"100644", blob))
    if not ents:
        return None
    ents.sort(key=lambda x: x[0].encode("utf-8", "surrogateescape") + (b"/" if x[1] == b"40000" else b""))
    data = b"".join(m + b" " + n.encode("utf-8", "surrogateescape") + b"\0" + bytes.fromhex(s) for n, m, s in ents)
    return _obj(b"tree", data)


def pin_trees(root, write=False):
    """[(name, '<lane>/<name>', LOCK sha, tree id)] for every LOCK row whose held tree is on disk; --write records them."""
    rows, _, _ = load(root)
    out = []
    for r in rows:
        nm = str(r.get("repo", "")).replace("/", "~")
        d = Path(root) / str(r.get("lane") or "") / nm
        if r.get("lane") and d.is_dir():
            out.append((nm, "%s/%s" % (r["lane"], nm), r.get("sha"), tree_id(d)))
    if write and out:
        p = C.map_dir(root) / "station_upstream.json"
        obj = C.load_json(p, {"upstreams": {}})
        for nm, _, sha, tree in out:
            e = obj.setdefault("upstreams", {}).setdefault(nm, {})
            e["pinned"] = dict(e.get("pinned") or {}, sha=sha, tree=tree)
        C.write_if_changed(p, C.dump_json(obj))
    return out


def load(root):
    lock = C.load_json(Path(root) / "upstream" / "LOCK.json", {"rows": []})
    rows = lock.get("rows", lock if isinstance(lock, list) else [])
    ups = C.load_map(root, "upstream", required=False).get("upstreams") or {}
    tags = set((C.load_map(root, "tags", required=False).get("problems") or {}).keys())
    return rows, ups, tags


def check(root):
    rows, ups, tags = load(root)
    V, W = [], []
    names = {}
    for r in rows:
        nm = str(r.get("repo", "")).replace("/", "~")
        names.setdefault(nm, []).append(r)
        sha = str(r.get("sha", ""))
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            (W if re.fullmatch(r"[0-9a-f]{7,39}", sha) else V).append("%s %s: sha %r is not 40-hex" % (
                "WARN" if re.fullmatch(r"[0-9a-f]{7,39}", sha) else "PIN", nm, sha))
        if nm not in ups:
            V.append("NO-USAGE %s: LOCK row (%s, lane %s) has no map/station_upstream.json upstreams.%s row" % (nm, r.get("how"), r.get("lane"), nm))
    files = C.tracked_files(root)
    held_dirs = sorted({"/".join(f.split("/")[:2]) for f in files if f.split("/")[0] in LANES and len(f.split("/")) >= 3 and "~" in f.split("/")[1]})
    for d in held_dirs:
        if d.split("/")[1] not in names:
            V.append("ORPHAN-DIR %s/: no upstream/LOCK.json row" % d)
    for nm, e in sorted(ups.items()):
        if nm not in names and e.get("mode") != "reference":
            V.append("ORPHAN-ENTRY %s: usage row with no LOCK row (set mode: reference for a not-held upstream)" % nm)
        for k in ("entry", "license_file"):
            if e.get(k) and not (Path(root) / e[k]).exists():
                V.append("DEAD %s: %s %s does not resolve" % (nm, k, e[k]))
        for t in e.get("solves") or []:
            if t not in tags:
                V.append("TAG %s: solves %r is not in map/tags.json" % (nm, t))
        for k in ("when", "entry"):
            if not e.get(k) and e.get("mode") != "reference":
                W.append("WARN %s: no %s" % (nm, k))
        ps = (e.get("pinned") or {}).get("sha")
        if ps and names.get(nm) and ps not in {r.get("sha") for r in names[nm]}:
            V.append("PIN %s: pinned.sha %s differs from upstream/LOCK.json" % (nm, ps[:12]))
        trees = sorted({"%s/%s" % (r.get("lane"), nm) for r in names.get(nm, []) if r.get("lane")})
        tree_pin = (e.get("pinned") or {}).get("tree")
        for t in trees:
            if tree_pin and C.is_git(root):
                # fix2-commons 2: a failed rev-parse echoes its ARGUMENT on stdout ("HEAD:<lane>/<name>") with rc 128;
                # that echo is not a tree id. Check rc: a failed read is UNREADABLE (exit 2), never EDITED, never clean.
                r = C.git(root, "rev-parse", "--verify", "-q", "HEAD:%s" % t)
                got = r.stdout.strip()
                if r.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40,64}", got):
                    V.append("UNREADABLE %s: git rev-parse HEAD:%s failed (rc=%d%s) - commit the held tree, then re-check" % (
                        nm, t, r.returncode, (": " + r.stderr.strip()[:120]) if r.stderr.strip() else ""))
                elif got != tree_pin:
                    V.append("EDITED %s: git tree of %s is %s, pinned %s (a station edit inside a held tree; after a deliberate "
                             "re-ingest re-pin with python3 tools/map/upstream_check.py --pin-trees --write)" % (nm, t, got[:12], tree_pin[:12]))
            elif tree_pin:
                W.append("WARN %s: pinned.tree for %s not verifiable (not a git repo)" % (nm, t))
            elif not tree_pin and any(f.startswith(t + "/") for f in files):
                W.append("WARN %s: no pinned.tree for %s (station edits inside it would go unseen)" % (nm, t))
            found = sorted(f for f in files if f.startswith(t + "/") and AGENT.search(f[len(t) + 1:]))
            listed = sorted(e.get("instructions") or [])
            if found and found != listed:
                V.append("INSTRUCTIONS %s: on disk %s, listed %s" % (nm, found, listed))
        for p in e.get("instructions") or []:
            if not (Path(root) / p).exists():
                V.append("DEAD %s: instructions %s does not resolve" % (nm, p))
    return V, W, len(rows) + len(ups) + len(held_dirs)


def table(root):
    rows, ups, _ = load(root)
    out = ["| name | lanes | sha | licence | entry | instruction files |", "|---|---|---|---|---|---|"]
    for nm in sorted({str(r.get("repo", "")).replace("/", "~") for r in rows} | set(ups)):
        rs = [r for r in rows if str(r.get("repo", "")).replace("/", "~") == nm]
        e = ups.get(nm, {})
        out.append("| %s | %s | %s | %s | %s | %s |" % (nm, ",".join(sorted({str(r.get("lane") or r.get("held")) for r in rs})) or e.get("mode", "-"),
                   (rs[0].get("sha", "") if rs else (e.get("pinned") or {}).get("sha", ""))[:12], (rs[0].get("licence") if rs else e.get("license")) or "-",
                   e.get("entry") or "-", ", ".join(e.get("instructions") or []) or "-"))
    return "\n".join(out)


def selftest():
    import json
    import tempfile
    ok = True
    sha = "a" * 40

    def station(t, lock_rows, ups, extra=()):
        for d in ("upstream", "map"):
            Path(t, d).mkdir(parents=True, exist_ok=True)
        Path(t, "upstream", "LOCK.json").write_text(json.dumps({"rows": lock_rows}))
        Path(t, "map", "tags.json").write_text(json.dumps({"problems": {"docs-generation": "x"}}))
        Path(t, "map", "upstream.json").write_text(json.dumps({"upstreams": {}}))
        Path(t, "map", "station_upstream.json").write_text(json.dumps({"upstreams": ups}))
        for f in ("repertoire/o~r/README.md", "repertoire/o~r/_upstream_AGENTS.md") + tuple(extra):
            Path(t, f).parent.mkdir(parents=True, exist_ok=True)
            Path(t, f).write_text("x")
        C.git_init_fixture(t)
        C.commit_fixture(t, "one")
        C.commit_fixture(t, "two")
    good = {"o~r": {"what": "w", "when": "w", "entry": "repertoire/o~r/README.md", "solves": ["docs-generation"],
                    "instructions": ["repertoire/o~r/_upstream_AGENTS.md"]}}
    row = {"repo": "o/r", "sha": sha, "how": "repertoire", "lane": "repertoire", "held": "committed", "licence": "MIT"}
    cases = [("clean", [row], good, (), 0), ("orphan dir", [row], good, ("upstream/x~y/a.md",), 1),
             ("no usage row", [row, dict(row, repo="p/q", lane=None, held="bootstrap")], good, (), 1),
             ("dead entry", [row], {"o~r": dict(good["o~r"], entry="repertoire/o~r/NOPE.md")}, (), 1),
             ("undeclared tag", [row], {"o~r": dict(good["o~r"], solves=["nope"])}, (), 1),
             ("new nested CLAUDE.md", [row], good, ("repertoire/o~r/sub/_upstream_CLAUDE.md",), 1),
             ("short pin", [dict(row, sha="abcdef0")], good, (), 0)]
    for name, rows, ups, extra, want in cases:
        with tempfile.TemporaryDirectory() as t:
            station(t, rows, ups, extra)
            V, W, _ = check(t)
            if (1 if V else 0) != want:
                ok = False
                print("FAIL", name, V)
    with tempfile.TemporaryDirectory() as t:
        station(t, [row], good)
        tree = C.git(t, "rev-parse", "HEAD:repertoire/o~r").stdout.strip()
        ups = {"o~r": dict(good["o~r"], pinned={"tree": tree})}
        Path(t, "map", "station_upstream.json").write_text(json.dumps({"upstreams": ups}))
        clean = not check(t)[0]
        Path(t, "repertoire", "o~r", "README.md").write_text("edited")
        C.commit_fixture(t, "edit")
        edited = any(v.startswith("EDITED") for v in check(t)[0])
        if not (clean and edited):
            ok = False
            print("FAIL edited vendored file must move the tree hash", clean, edited)
    with tempfile.TemporaryDirectory() as t:  # --pin-trees: the stdlib tree hash equals git's, exec bit/symlink/nesting included
        station(t, [row], good, ("repertoire/o~r/a/b/deep.py", "repertoire/o~r/z.sh"))
        os.chmod(Path(t, "repertoire", "o~r", "z.sh"), 0o755)
        os.symlink("README.md", Path(t, "repertoire", "o~r", "link.md"))
        Path(t, "repertoire", "o~r", "a", "__pycache__").mkdir()
        Path(t, "repertoire", "o~r", "a", "__pycache__", "x.pyc").write_bytes(b"\0")
        Path(t, ".gitignore").write_text("__pycache__/\n*.pyc\n")
        C.commit_fixture(t, "exec + symlink")
        want = C.git(t, "rev-parse", "HEAD:repertoire/o~r").stdout.strip()
        got = pin_trees(t, write=True)
        pinned = C.load_json(Path(t, "map", "station_upstream.json"))["upstreams"]["o~r"]["pinned"]
        if not (got and got[0][3] == want and pinned == {"sha": sha, "tree": want} and not check(t)[0]):
            ok = False
            print("FAIL --pin-trees must equal git's tree id and record it", got, want, pinned)
    with tempfile.TemporaryDirectory() as t:  # fix2-commons 2: lane on disk but not in HEAD -> UNREADABLE, exit 2
        station(t, [row], good)
        tree = C.git(t, "rev-parse", "HEAD:repertoire/o~r").stdout.strip()
        ups = {"o~r": dict(good["o~r"], pinned={"tree": tree})}
        Path(t, "map", "station_upstream.json").write_text(json.dumps({"upstreams": ups}))
        C.git(t, "rm", "-q", "-r", "--cached", "repertoire/o~r")
        C.git(t, "-c", "user.name=kit", "-c", "user.email=kit@localhost", "commit", "-q", "-m", "untrack lane")
        V = check(t)[0]
        unread = any(v.startswith("UNREADABLE o~r") for v in V) and not any(v.startswith("EDITED") for v in V)
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            rc = main(["--root", t])
        if not (unread and rc == 2):
            ok = False
            print("FAIL failed rev-parse must be UNREADABLE (exit 2), not EDITED", V, rc)
    print("selftest OK" if ok else "selftest FAILED")
    return 0 if ok else 1


def main(argv):
    root, argv = C.root_arg(argv)
    if "--selftest" in argv:
        return selftest()
    try:
        if "--list" in argv:
            print(table(root))
            return 0
        if "--pin-trees" in argv:
            for nm, held, sha, tree in pin_trees(root, "--write" in argv):
                print("%s %s sha=%s tree=%s" % (nm, held, sha, tree))
            print("pin-trees: %s" % ("written to map/station_upstream.json" if "--write" in argv else "dry (add --write to record)"))
            return 0
        V, W, d = check(root)
    except C.Unreadable as e:
        print("upstream: UNREADABLE %s" % e)
        return 2
    print(C.headline("upstream", len(V), len(W), d))
    for x in V + W:
        print(x)
    if any(v.startswith("UNREADABLE") for v in V):
        return 2
    return 1 if V else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
