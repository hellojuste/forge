#!/usr/bin/env python3
"""ingest.py — copy pinned upstream files into a station lane, neutralised, with provenance.

Earned by: LEAN LL-03 (lettuce measured a nested upstream `.claude/skills` being LISTED on the first Read of
any file in its subtree; no directory-level exclude covers it), LL-08 (upstream kept verbatim, attributed,
off the dependency graph), LL-09 (licence decided before ingest) and JUDGE_2 F1 (career-ops / ARS ship
mode-120000 symlinks whose blob is the link text; hashing it as content miscounted the census).

What it does (the ONLY way upstream bytes enter a station lane):
  * reads blobs one by one from a blobless clone at a verified 40-hex pin (`git -C <clone> cat-file`);
  * refuses a symlink source (exit 1, names the path) unless --deref, which resolves the link text relative
    to the link's directory inside the repo and copies the target (recording `symlink_from`);
  * neutralises agent files (.claude/ -> _upstream_claude/, .claude-plugin/ -> _upstream_claude-plugin/,
    CLAUDE.md / CLAUDE.local.md / AGENTS.md / .mcp.json -> _upstream_<name>, hooks/hooks.json ->
    hooks/_upstream_hooks.json), one RENAMES.json row per rename;
  * copies the NEAREST LICENSE*/COPYING*/license.txt of every held file plus NOTICE*/THIRD_PARTY_NOTICES.md
    at the repo root and beside each governing licence;
  * appends idempotent rows to upstream/{LOCK,PROVENANCE,RENAMES,PRECEDENCE}.json (keys: LOCK by
    (repo, how, lane, copy_of); PROVENANCE/RENAMES by held path; PRECEDENCE by tree path).
  * --how bootstrap writes only the LOCK row (held: bootstrap) and a PRECEDENCE row: the bytes stay in the
    gitignored bare cache `.upstream/<owner~repo>.git` that tools/kit/bootstrap.py makes.

CLI (a contract with the station builders):
  ingest.py --clone <dir> --sha <40hex> --repo <owner/repo> --repo-id <n>
            --lane repertoire|upstream|study|nc-lane --dest <station root> --path <p> [--path <p>...]
            [--deref] [--copy-of <station>] [--held committed|sparse-committed]
            [--how repertoire|tree|copy_from:<st>|bootstrap] [--mode data|workspace] [--dry]
  ingest.py --selftest
Exit: 0 ok · 1 refused source (symlink without --deref, sha mismatch, path absent at the pin) · 2 usage.
Upstream text is DATA: nothing here executes or follows an upstream file.
"""
import argparse
import os
import posixpath
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _uplib as U  # noqa: E402

TOOL = "tools/upstream/ingest.py"


class Refused(Exception):
    pass


def _norm_path(p):
    p = p.strip().strip("/")
    return "" if p in (".", "") else p


def _resolve_link(src, text, tree):
    target = posixpath.normpath(posixpath.join(posixpath.dirname(src), text.strip()))
    if target.startswith("../") or target == ".." or target.startswith("/"):
        raise Refused("symlink %s -> %s escapes the repo" % (src, text.strip()))
    return target


def collect(clone, tree, paths, deref):
    """-> list of (dest_src_path, real_src_path, obj, symlink_from) ; raises Refused."""
    out, refusals = [], []

    def add_file(logical, real, depth=0, link_from=None):
        mode, obj = tree[real]
        if mode == "120000":
            if not deref:
                refusals.append(logical)
                return
            if depth > 8:
                raise Refused("symlink chain too deep at %s" % logical)
            text = U.blob(clone, obj).decode("utf-8", "replace")
            target = _resolve_link(real, text, tree)
            if target in tree:
                add_file(logical, target, depth + 1, link_from or logical)
            elif any(k.startswith(target + "/") for k in tree):
                for k in sorted(x for x in tree if x.startswith(target + "/")):
                    add_file(logical + k[len(target):], k, depth + 1, link_from or logical)
            else:
                raise Refused("symlink %s -> %s: target absent at the pin" % (logical, text.strip()))
            return
        out.append((logical, real, obj, link_from))

    for p in paths:
        p = _norm_path(p)
        if p and p in tree:
            add_file(p, p)
        else:
            pref = (p + "/") if p else ""
            hits = sorted(k for k in tree if k.startswith(pref))
            if not hits:
                raise Refused("path absent at the pin: %s" % (p or "."))
            for k in hits:
                add_file(k, k)
    if refusals:
        raise Refused("symlink source(s) refused (pass --deref to copy their targets): " + ", ".join(refusals))
    seen, uniq = set(), []
    for row in out:
        if row[0] not in seen:
            seen.add(row[0])
            uniq.append(row)
    return uniq


def run(a):
    if not re.fullmatch(r"[0-9a-f]{40}", a.sha or ""):
        print("ingest: --sha must be 40 hex", file=sys.stderr)
        return 2
    if not re.fullmatch(r"[^/\s]+/[^/\s]+", a.repo or ""):
        print("ingest: --repo must be owner/repo", file=sys.stderr)
        return 2
    lane = (a.lane or "").strip("/") or None
    how = a.how or ("copy_from:%s" % a.copy_of if a.copy_of else ("repertoire" if lane == "repertoire" else "tree"))
    if how != "bootstrap" and (lane not in U.LANES or not a.path):
        print("ingest: --lane (one of %s) and at least one --path are required unless --how bootstrap" % ", ".join(U.LANES), file=sys.stderr)
        return 2
    if not (how in U.HOW_VALUES or how.startswith("copy_from:")):
        print("ingest: bad --how %s" % how, file=sys.stderr)
        return 2
    clone, dest = Path(a.clone), Path(a.dest)
    try:
        head = U.git(clone, "rev-parse", "HEAD").strip()
    except RuntimeError as e:
        print("ingest: cannot read clone: %s" % e, file=sys.stderr)
        return 2
    if head != a.sha:
        print("ingest: REFUSED sha mismatch: --sha %s but %s HEAD is %s" % (a.sha, clone, head), file=sys.stderr)
        return 1
    tree = U.ls_tree(clone, a.sha)
    slug = a.repo.replace("/", "~")
    up = dest / "upstream"
    lock = U.load_json(up / "LOCK.json", None) or {"_why": "one row per held component: repo, 40-hex sha, how, lane, held; written by tools/upstream/ingest.py, checked by upstream_checks.py upstream_lock", "rows": []}
    prov = U.load_json(up / "PROVENANCE.json", None) or {"_why": "one row per held file: source repo, sha, source path, sha256, renamed_from, symlink_from, copy_of; written by tools/upstream/ingest.py, re-hashed by upstream_checks.py provenance", "rows": []}
    ren = U.load_json(up / "RENAMES.json", None) or {"_why": "one row per neutralisation rename (LL-03); written by tools/upstream/ingest.py, proven by upstream_checks.py vendor_leak", "rows": []}
    prec = U.load_json(up / "PRECEDENCE.json", None) or {"_why": "one row per held tree; precedence ladder KIT_PLAN 5; governs = closed SUBTREE vocabulary only; checked by upstream_checks.py precedence", "default": "station", "rows": []}

    agent_found = sorted(p for p in tree if U.is_agent_file(p))
    tree_path = ("%s/%s/" % (lane, slug)) if how != "bootstrap" else (".upstream/%s.git" % slug)

    held_files, renames = [], []
    if how != "bootstrap":
        try:
            sources = collect(clone, tree, a.path, a.deref)
        except Refused as e:
            print("ingest: REFUSED %s" % e, file=sys.stderr)
            return 1
        lic_paths, notice_paths = set(), set(U.notices_beside("", tree))
        per_file_lic = {}
        for logical, real, obj, link_from in sources:
            lp = U.nearest_licence(real, tree)
            per_file_lic[logical] = lp
            if lp:
                lic_paths.add(lp)
                notice_paths.update(U.notices_beside(lp.rpartition("/")[0], tree))
        have = {s[0] for s in sources}
        for extra, role in [(p, "licence") for p in sorted(lic_paths)] + [(p, "notice") for p in sorted(notice_paths)]:
            if extra not in have and tree[extra][0] != "120000":
                sources.append((extra, extra, tree[extra][1], None))
                have.add(extra)
                per_file_lic[extra] = U.nearest_licence(extra, tree)
        roles = {p: "licence" for p in lic_paths}
        roles.update({p: "notice" for p in notice_paths})
        for logical, real, obj, link_from in sources:
            data = U.blob(clone, obj)
            held = "%s/%s/%s" % (lane, slug, U.neutralise(logical))
            lp = per_file_lic.get(logical)
            row = {"path": held, "repo": a.repo, "repo_id": a.repo_id, "sha": a.sha, "source_path": real,
                   "sha256": U.sha256_bytes(data), "bytes": len(data),
                   "renamed_from": logical if U.neutralise(logical) != logical else None,
                   "symlink_from": link_from, "copy_of": a.copy_of, "lane": lane,
                   "role": roles.get(logical, "held"),
                   "licence_file": ("%s/%s/%s" % (lane, slug, U.neutralise(lp))) if lp else None}
            held_files.append((held, data, row))
            if row["renamed_from"]:
                renames.append({"path": held, "from": "%s/%s/%s" % (lane, slug, logical), "repo": a.repo,
                                "sha": a.sha, "rule": "LL-03 neutralisation"})
        lic_class = {}
        for lp in sorted(lic_paths):
            lic_class[lp] = U.classify_licence(U.blob(clone, tree[lp][1]).decode("utf-8", "replace"))
        root_lic = sorted(lic_paths, key=lambda x: (x.count("/"), x))
        licence = lic_class[root_lic[0]] if root_lic else "UNKNOWN"
        if len(set(lic_class.values())) > 1:
            licence = "; ".join("%s: %s" % (k, v) for k, v in sorted(lic_class.items()))
        lock_row = {"repo": a.repo, "repo_id": a.repo_id, "sha": a.sha, "how": how, "lane": lane,
                    "held_root": tree_path, "paths": sorted({_norm_path(p) or "." for p in a.path}),
                    "licence": licence, "licence_files": sorted(lic_paths),
                    "licence_file": root_lic[0] if root_lic else None,
                    "notice_files": sorted(notice_paths), "held": a.held or "committed",
                    "copy_of": a.copy_of, "mode": a.mode}
    else:
        lic_root = U.nearest_licence("x", tree)
        lic = U.classify_licence(U.blob(clone, tree[lic_root][1]).decode("utf-8", "replace")) if lic_root else "UNKNOWN"
        lock_row = {"repo": a.repo, "repo_id": a.repo_id, "sha": a.sha, "how": "bootstrap", "lane": None,
                    "held_root": tree_path, "paths": ["."], "licence": lic,
                    "licence_files": [lic_root] if lic_root else [], "licence_file": lic_root,
                    "notice_files": U.notices_beside("", tree), "held": "bootstrap", "copy_of": None,
                    "mode": a.mode, "files_at_pin": len(tree)}

    if a.dry:
        print("ingest --dry: %s %s -> %s (%d file(s), %d rename(s))" % (a.repo, how, tree_path, len(held_files), len(renames)))
        for h, _, r in held_files[:40]:
            print("  %s%s" % (h, "  (renamed from %s)" % r["renamed_from"] if r["renamed_from"] else ""))
        return 0

    for held, data, row in held_files:
        p = dest / held
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists() or p.read_bytes() != data:
            p.write_bytes(data)
    # merge rows (idempotent)
    key = lambda r: (r.get("repo"), r.get("how"), r.get("lane"), r.get("copy_of"))
    rows = [r for r in lock["rows"] if key(r) != key(lock_row)]
    old = [r for r in lock["rows"] if key(r) == key(lock_row)]
    if old and how != "bootstrap":
        lock_row["paths"] = sorted(set(old[0].get("paths", [])) | set(lock_row["paths"]))
        lock_row["licence_files"] = sorted(set(old[0].get("licence_files", [])) | set(lock_row["licence_files"]))
        lock_row["notice_files"] = sorted(set(old[0].get("notice_files", [])) | set(lock_row["notice_files"]))
    lock["rows"] = sorted(rows + [lock_row], key=lambda r: (r.get("repo_id") or 0, r["repo"], r["how"], r.get("lane") or ""))
    pmap = {r["path"]: r for r in prov["rows"]}
    for _, _, row in held_files:
        pmap[row["path"]] = row
    prov["rows"] = [pmap[k] for k in sorted(pmap)]
    rmap = {r["path"]: r for r in ren["rows"]}
    for r in renames:
        rmap[r["path"]] = r
    ren["rows"] = [rmap[k] for k in sorted(rmap)]
    pr = {r["path"]: r for r in prec["rows"]}
    renamed_to = sorted({r["path"] for r in renames})
    if tree_path in pr:
        cur = pr[tree_path]
        cur["agent_files_found"] = agent_found
        cur["agent_files_renamed_to"] = sorted(set(cur.get("agent_files_renamed_to", [])) | set(renamed_to))
    else:
        pr[tree_path] = {"path": tree_path, "repo": a.repo, "sha": a.sha, "licence": lock_row["licence"],
                         "agent_files_found": agent_found, "agent_files_renamed_to": renamed_to,
                         "loaded": "never-auto" if how != "bootstrap" else "never-auto (bare clone, no working tree)",
                         "governs": [], "summary_of_upstream_asks": U.TODO_PARAPHRASE, "adopted": [],
                         "mode": a.mode}
    prec["rows"] = [pr[k] for k in sorted(pr)]
    U.write_json(up / "LOCK.json", lock)
    U.write_json(up / "PRECEDENCE.json", prec)
    if how != "bootstrap":
        U.write_json(up / "PROVENANCE.json", prov)
        U.write_json(up / "RENAMES.json", ren)
    print("ingest: %s %s -> %s · %d file(s) held · %d rename(s) · licence %s" % (a.repo, how, tree_path, len(held_files), len(renames), lock_row["licence"]))
    return 0


def parser():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--clone"); ap.add_argument("--sha"); ap.add_argument("--repo")
    ap.add_argument("--repo-id", type=int, dest="repo_id"); ap.add_argument("--lane")
    ap.add_argument("--dest"); ap.add_argument("--path", action="append", default=[])
    ap.add_argument("--deref", action="store_true"); ap.add_argument("--copy-of", dest="copy_of")
    ap.add_argument("--held", choices=["committed", "sparse-committed"])
    ap.add_argument("--how"); ap.add_argument("--mode", choices=["data", "workspace"], default="data")
    ap.add_argument("--dry", action="store_true"); ap.add_argument("--selftest", action="store_true")
    return ap


# ---------------------------------------------------------------- selftest
GPL = "GNU GENERAL PUBLIC LICENSE\nVersion 3, 29 June 2007\n"
MIT = "MIT License\n\nPermission is hereby granted, free of charge, to any person obtaining a copy\n"


def make_fixture(d):
    """A git repo with CLAUDE.md, .claude/skills/x/SKILL.md, a symlink, a nested MIT LICENSE under a GPL root, a NOTICE."""
    files = {
        "LICENSE": GPL, "NOTICE": "Fixture NOTICE: keep me.\n", "CLAUDE.md": "Agent: run make deploy.\n",
        "AGENTS.md": "Agents file.\n", ".mcp.json": '{"mcpServers": {}}\n',
        ".claude/skills/x/SKILL.md": "---\nname: x\ndescription: fixture skill x\n---\nbody\n",
        ".claude-plugin/plugin.json": "{}\n",
        "pkg/LICENSE": MIT, "pkg/skills/y/SKILL.md": "---\nname: y\ndescription: fixture y\n---\nY body\n",
        "pkg/hooks/hooks.json": '{"hooks": {}}\n', "src/main.py": "print('upstream code, never run')\n",
    }
    for k, v in files.items():
        p = Path(d) / k
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(v)
    os.symlink("pkg/skills/y/SKILL.md", Path(d) / "link.md")
    os.makedirs(Path(d) / "agentdir", exist_ok=True)
    os.symlink("../pkg/skills/y", Path(d) / "agentdir" / "y")
    g = ["git", "-C", d, "-c", "user.name=kit", "-c", "user.email=kit@localhost"]
    subprocess.run(["git", "-C", d, "init", "-q"], check=True)
    subprocess.run(g + ["add", "--"] + sorted(files) + ["link.md", "agentdir/y"], check=True)
    subprocess.run(g + ["commit", "-qm", "fixture"], check=True)
    return subprocess.run(["git", "-C", d, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()


def selftest():
    import io
    import contextlib
    here = Path(__file__).resolve().parent
    sys.path.insert(0, str(here))
    import upstream_checks as UC
    cases = 0
    with tempfile.TemporaryDirectory() as t:
        src, st = os.path.join(t, "src"), os.path.join(t, "st")
        os.makedirs(src)
        sha = make_fixture(src)
        base = ["--clone", src, "--sha", sha, "--repo", "o/r", "--repo-id", "99", "--lane", "upstream", "--dest", st]

        def call(extra):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                rc = run(parser().parse_args(base + extra))
            return rc, buf.getvalue()

        rc, out = call(["--path", "."])
        assert rc == 1 and "link.md" in out, ("symlink must be refused", rc, out); cases += 1
        assert not Path(st, "upstream", "o~r").exists(), "refusal must write nothing"; cases += 1
        rc, out = call(["--path", ".", "--deref", "--dry"])
        assert rc == 0 and not Path(st, "upstream", "LOCK.json").exists(), ("dry writes nothing", out); cases += 1
        rc, out = call(["--path", ".", "--deref"])
        assert rc == 0, out
        T = Path(st, "upstream", "o~r")
        for must in ["_upstream_CLAUDE.md", "_upstream_AGENTS.md", "_upstream_mcp.json",
                     "_upstream_claude/skills/x/SKILL.md", "_upstream_claude-plugin/plugin.json",
                     "pkg/hooks/_upstream_hooks.json", "LICENSE", "NOTICE", "pkg/LICENSE"]:
            assert (T / must).is_file(), "missing renamed/held %s" % must
        for mustnot in ["CLAUDE.md", "AGENTS.md", ".mcp.json", ".claude", ".claude-plugin", "pkg/hooks/hooks.json"]:
            assert not (T / mustnot).exists(), "un-renamed %s" % mustnot
        cases += 2
        assert (T / "link.md").read_text() == "---\nname: y\ndescription: fixture y\n---\nY body\n"; cases += 1
        assert (T / "agentdir/y/SKILL.md").is_file(), "dir symlink deref"; cases += 1
        prov = U.load_json(Path(st, "upstream", "PROVENANCE.json"))
        pm = {r["path"]: r for r in prov["rows"]}
        assert pm["upstream/o~r/link.md"]["symlink_from"] == "link.md"; cases += 1
        assert pm["upstream/o~r/link.md"]["source_path"] == "pkg/skills/y/SKILL.md"; cases += 1
        assert pm["upstream/o~r/pkg/skills/y/SKILL.md"]["licence_file"] == "upstream/o~r/pkg/LICENSE", "nearest licence"; cases += 1
        assert pm["upstream/o~r/_upstream_CLAUDE.md"]["licence_file"] == "upstream/o~r/LICENSE"; cases += 1
        assert pm["upstream/o~r/_upstream_CLAUDE.md"]["renamed_from"] == "CLAUDE.md"; cases += 1
        lock = U.load_json(Path(st, "upstream", "LOCK.json"))
        assert len(lock["rows"]) == 1 and lock["rows"][0]["how"] == "tree" and "GPL" in lock["rows"][0]["licence"]; cases += 1
        ren = U.load_json(Path(st, "upstream", "RENAMES.json"))
        assert any(r["path"] == "upstream/o~r/_upstream_claude/skills/x/SKILL.md" for r in ren["rows"]); cases += 1
        prec = U.load_json(Path(st, "upstream", "PRECEDENCE.json"))
        assert prec["rows"][0]["summary_of_upstream_asks"] == U.TODO_PARAPHRASE and prec["rows"][0]["governs"] == []; cases += 1
        assert "CLAUDE.md" in prec["rows"][0]["agent_files_found"]; cases += 1
        snap = {p: Path(st, "upstream", p).read_bytes() for p in ("LOCK.json", "PROVENANCE.json", "RENAMES.json", "PRECEDENCE.json")}
        rc, out = call(["--path", ".", "--deref"])
        assert rc == 0 and all(Path(st, "upstream", p).read_bytes() == b for p, b in snap.items()), "idempotent"; cases += 1
        rc, out = call(["--path", "no/such/path"])
        assert rc == 1 and "absent" in out; cases += 1
        bad = list(base); bad[3] = "0" * 40
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            rc = run(parser().parse_args(bad + ["--path", "."]))
        assert rc == 1 and "mismatch" in buf.getvalue(); cases += 1
        with contextlib.redirect_stderr(io.StringIO()):
            rc = run(parser().parse_args(["--clone", src, "--sha", sha, "--repo", "o/r", "--dest", st]))
        assert rc == 2, "usage"; cases += 1
        # copy_of: second lane row, same bytes
        rc, out = call(["--path", "pkg/skills/y", "--copy-of", "home", "--how", "copy_from:home"])
        assert rc == 0 and len(U.load_json(Path(st, "upstream", "LOCK.json"))["rows"]) == 2; cases += 1
        # bootstrap row only
        rc, out = call(["--how", "bootstrap"])
        lock = U.load_json(Path(st, "upstream", "LOCK.json"))
        assert rc == 0 and any(r["held"] == "bootstrap" and r["lane"] is None for r in lock["rows"]); cases += 1
        # vendor_leak green after, red on a planted un-renamed .claude/
        with contextlib.redirect_stdout(io.StringIO()):
            assert UC.check_vendor_leak(Path(st)) == 0, "vendor_leak must be green after ingest"
        cases += 1
        planted = T / ".claude" / "skills" / "z" / "SKILL.md"
        planted.parent.mkdir(parents=True)
        planted.write_text("x")
        with contextlib.redirect_stdout(io.StringIO()):
            assert UC.check_vendor_leak(Path(st)) == 1, "vendor_leak must be red on planted .claude/"
        cases += 1
        # neutralise is a pure function over the whole rule table
        assert U.neutralise("a/.claude/x/CLAUDE.md") == "a/_upstream_claude/x/_upstream_CLAUDE.md"
        assert U.neutralise("hooks/hooks.json") == "hooks/_upstream_hooks.json"
        assert U.neutralise("x/CLAUDE.local.md") == "x/_upstream_CLAUDE.local.md"
        assert U.neutralise("p/.claude-plugin/m.json") == "p/_upstream_claude-plugin/m.json"
        cases += 1
    print("selftest OK (%d cases)" % cases)
    return 0


def main(argv=None):
    a = parser().parse_args(argv)
    if a.selftest:
        return selftest()
    if not (a.clone and a.sha and a.repo and a.dest):
        print("usage: ingest.py --clone <dir> --sha <40hex> --repo <owner/repo> --repo-id <n> --lane <lane> --dest <root> --path <p> [...]", file=sys.stderr)
        return 2
    return run(a)


if __name__ == "__main__":
    sys.exit(main())
