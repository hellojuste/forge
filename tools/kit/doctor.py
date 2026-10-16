#!/usr/bin/env python3
"""doctor.py - what this machine and this kit checkout need, as a REPORT.

Earned by: the first thing after unzip is "does it work here?", and the answer
spans the machine (git, python, node), the repo (branches, worktrees) and the
bootstrap cache (.upstream/ coverage per LOCK row). A multi-station working
root loads the hooks of ONE branch only (RF-15 / J1 graft 21) and nothing else
says so. Report only: it never changes anything and always exits 0.
Retires: nothing (new with the kit).

  doctor.py [--root R]
  doctor.py --selftest
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _kit  # noqa: E402
import bootstrap  # noqa: E402


def _ver(cmd):
    try:
        p = _kit.run(cmd, check=False)
        return (p.out or p.err).strip().splitlines()[0] if p.returncode == 0 else None
    except OSError:
        return None


def report(root, log=print):
    root = os.path.abspath(root)
    log("stable-kit doctor — %s" % root)
    gv = _ver(["git", "--version"])
    log("  git     : %s%s" % (gv or "MISSING (required)",
                              "" if not gv else "  (merge-tree --write-tree needs >= 2.38 for sync --check)"))
    log("  python3 : %s" % sys.version.split()[0])
    log("  node    : %s" % (_ver(["node", "--version"]) or "absent (needed only to syntax-check workflows)"))
    log("  merge.renormalize: not needed (no line-ending filters in the kit)")
    isrepo = _kit.run(["git", "-C", root, "rev-parse", "--git-dir"], check=False).returncode == 0
    if not isrepo:
        log("  repo    : NOT a git repo (unzip dropped .git?) -> git clone stable-kit.bundle stable-kit (UNZIP.md)")
        return 0
    br = _kit.run(["git", "-C", root, "for-each-ref", "--format=%(refname:short)", "refs/heads/"], check=False).out.split()
    st_br = [b for b in br if b.startswith("station/")]
    cur = _kit.run(["git", "-C", root, "symbolic-ref", "--short", "-q", "HEAD"], check=False).out.strip() or "(detached)"
    log("  branches: %d (main + %d station) · current %s" % (len(br), len(st_br), cur))
    wt = _kit.run(["git", "-C", root, "worktree", "list", "--porcelain"], check=False).out
    trees = []
    for blk in wt.split("\n\n"):
        d = {}
        for l in blk.splitlines():
            k, _, v = l.partition(" ")
            d[k] = v
        if "worktree" in d:
            trees.append((d["worktree"], d.get("branch", "(detached)").replace("refs/heads/", "")))
    log("  worktrees (%d):" % len(trees))
    for path, b in trees:
        log("    %-14s %s" % (b, path))
    missing = [b for b in st_br if b not in {t[1] for t in trees}]
    if missing:
        log("  stations without a worktree: %s  -> git worktree add ~/stations/<x> station/<x>" % ", ".join(m.split("/", 1)[1] for m in missing))
    # multi-station working root: station worktrees nested under one directory you open Claude in
    nested = [p for p, b in trees if b.startswith("station/") and os.path.abspath(p).startswith(root + os.sep)]
    if nested or os.path.basename(root) == "stations":
        log("  NOTE multi-station working root: Claude loads the hooks/CLAUDE.md of ONE branch only — open Claude inside one station worktree")
    # bootstrap coverage per LOCK row (this branch) or per registry bootstrap row (main)
    try:
        src = {s["key"]: s for s in _kit.read_json(os.path.join(root, "registry", "sources.json"))["sources"]}
        homes = _kit.read_json(os.path.join(root, "registry", "homes.json"))["homes"]
    except (OSError, ValueError, KeyError) as e:
        log("  registry: unreadable (%s)" % e)
        return 0
    rows = []
    lp = os.path.join(root, "upstream", "LOCK.json")
    if os.path.isfile(os.path.join(root, "station.json")) and os.path.isfile(lp):
        doc = _kit.read_json(lp)
        lr = doc if isinstance(doc, list) else (doc.get("rows") or doc.get("lock") or [])
        keys = sorted({(r.get("key") or str(r.get("repo", "")).replace("/", "~")) for r in lr
                       if str(r.get("held") or r.get("how") or "").startswith("bootstrap")})
        scope = "this station's LOCK bootstrap rows"
    else:
        keys = sorted({h["key"] for h in homes if any(l.get("how") == "bootstrap" for l in h.get("lands", []))})
        scope = "registry bootstrap rows"
    need = []
    for k in keys:
        s = src.get(k)
        ok = bool(s) and bootstrap.has_pin(bootstrap.bare_path(root, k), s["sha"])
        rows.append(ok)
        if not ok:
            need.append(k)
    log("  .upstream/ coverage: %d / %d %s have their pin" % (sum(rows), len(rows), scope))
    if need:
        log("  bootstrap needed (%d): %s" % (len(need), " ".join(need)))
        log("    -> python3 tools/kit/bootstrap.py %s   (or --all; offline: --from-bundle <dir>)" % (
            "--station " + _kit.read_json(os.path.join(root, "station.json")).get("name", "<x>")
            if os.path.isfile(os.path.join(root, "station.json")) else "--all"))
    log("  next: README.md (decision tree) · KIT.md · python3 tools/station_audit.py --state")
    return 0


def _selftest():
    tmp = tempfile.mkdtemp(prefix="kit-doctor-")
    try:
        lines = []
        assert report(os.path.join(tmp, "nope"), log=lines.append) == 0
        assert any("NOT a git repo" in l for l in lines)
        remote, v1, _ = bootstrap.make_remote(tmp)
        root = bootstrap.make_kit_root(tmp, [{"key": "o~r", "repo": "o/r", "url": "file://" + remote, "sha": v1}],
                                       [{"key": "o~r", "lands": [{"station": "alpha", "how": "bootstrap"}]}])
        _kit.run(["git", "init", "-q", "-b", "main", root])
        _kit.fixture_git_config(root)
        _kit.stage_paths(root)
        _kit.commit(root, "m")
        _kit.git(root, "branch", "station/alpha")
        lines = []
        assert report(root, log=lines.append) == 0
        assert any("0 / 1" in l for l in lines) and any("bootstrap needed (1): o~r" in l for l in lines), lines
        assert any("stations without a worktree: alpha" in l for l in lines), lines
        bootstrap.run(root, [{"key": "o~r", "url": "file://" + remote, "sha": v1}], log=lambda *a: None)
        lines = []
        report(root, log=lines.append)
        assert any("1 / 1" in l for l in lines), lines
        print("selftest OK")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in argv:
        return _selftest()
    root = argv[argv.index("--root") + 1] if "--root" in argv else _kit.REPO_ROOT_GUESS
    p = _kit.run(["git", "-C", root, "rev-parse", "--show-toplevel"], check=False)
    if p.returncode == 0:
        root = p.out.strip()
    try:
        report(root)
    except Exception as e:  # report only: never fail the operator's first command
        print("doctor: could not finish the report: %s" % e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
