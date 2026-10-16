#!/usr/bin/env python3
"""runtree.py - check out a bootstrapped upstream at its pin, OUTSIDE the station.

Earned by: upstream code must only ever run outside the repo: a checked-out
upstream inside a station lazy-loads its CLAUDE.md and skills (LL-03), and its
install scripts write into the working tree. A run tree under
~/.stable-kit/run/<station>/<repo>@<sha7> keeps both away. It neutralises
nothing (it is a run tree, outside the repo). Retires: hand worktrees.

  runtree.py <owner~repo> [--station X] [--workspace] [--root R] [--run-root DIR]
      git -C .upstream/<owner~repo>.git worktree add --detach <run-root>/<station>/<repo>@<sha7> <sha>
      --workspace (career-ops, ai-job-search: agent workspaces that assume they
      ARE the repo) also writes <tree>/.claude/settings.local.json wiring the kit
      floor hooks (deny_destructive; station_dispatch with act_gate /
      quarantine_gate) by absolute path into the station worktree, and prints
      the PRECEDENCE case-ii notice.
  runtree.py --list | --remove <owner~repo> [--station X] [--force] | --selftest
Default run root: $STABLE_KIT_RUN or ~/.stable-kit/run.
Exit 0 ok · 1 refused (no bootstrap pin, dirty tree on remove) · 2 usage.
"""
import argparse
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _kit  # noqa: E402
import bootstrap  # noqa: E402

PRECEDENCE_II = (
    "PRECEDENCE case ii (KIT.md rank 4): in this workspace the upstream's own CLAUDE.md governs ITS workflow, "
    "above the commons defaults (rank 5) and below the kit floor (rank 2): deny_destructive, act_gate (ask on "
    "irreversible acts) and quarantine_gate stay wired by .claude/settings.local.json. Record any adoption as an "
    "`adopted:` entry in upstream/PRECEDENCE.json plus a DEC row.")


def run_root(arg=None):
    return os.path.abspath(os.path.expanduser(arg or os.environ.get("STABLE_KIT_RUN") or "~/.stable-kit/run"))


def station_for(root, key, station=None):
    if station:
        return station
    p = os.path.join(root, "registry", "homes.json")
    if os.path.isfile(p):
        for h in _kit.read_json(p)["homes"]:
            if h["key"] == key:
                boot = [l["station"] for l in h.get("lands", []) if l.get("how") == "bootstrap" and l.get("station")]
                anyst = [l["station"] for l in h.get("lands", []) if l.get("station")]
                if boot or anyst:
                    return (boot or anyst)[0]
                return "attic"
    return "attic"


def tree_path(rr, station, key, sha):
    return os.path.join(rr, station, "%s@%s" % (key.split("~", 1)[1], sha[:7]))


def workspace_settings(station_root):
    q = lambda s: '"%s"' % s.replace('"', '\\"')
    hook = lambda script: {"type": "command",
                           "command": "cd %s || exit 0; python3 %s" % (q(station_root), q(os.path.join(station_root, script)))}
    return {
        "_doc": "Written by tools/kit/runtree.py --workspace: the kit floor (rank 2) wired into an upstream workspace "
                "by absolute path. Hooks run from the station worktree so its station.json drives act_gate/quarantine_gate.",
        "hooks": {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [hook(".claude/hooks/deny_destructive.py")]},
                {"matcher": ".*", "hooks": [hook(".claude/hooks/station_dispatch.py")]},
            ]
        },
    }


def add(root, key, station=None, workspace=False, rr=None, log=print, station_root=None):
    src = {s["key"]: s for s in _kit.read_json(os.path.join(root, "registry", "sources.json"))["sources"]}
    if key not in src:
        log("runtree: %s is not a registry key" % key)
        return 2
    sha = src[key]["sha"]
    bare = bootstrap.bare_path(root, key)
    if not bootstrap.has_pin(bare, sha):
        log("runtree: no bootstrap pin for %s; run python3 tools/kit/bootstrap.py %s" % (key, key))
        return 1
    st = station_for(root, key, station)
    path = tree_path(run_root(rr), st, key, sha)
    if os.path.isdir(path):
        log("runtree: exists %s" % path)
    else:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _kit.run(["git", "-C", bare, "worktree", "add", "-q", "--detach", path, sha])
        log("runtree: %s @ %s -> %s" % (key, sha[:12], path))
    head = _kit.run(["git", "-C", path, "rev-parse", "HEAD"]).out.strip()
    if head != sha:
        log("runtree: HEAD %s != pin %s" % (head, sha))
        return 1
    if workspace:
        sroot = os.path.abspath(station_root or root)
        sp = os.path.join(path, ".claude", "settings.local.json")
        os.makedirs(os.path.dirname(sp), exist_ok=True)
        with open(sp, "w") as f:
            f.write(json.dumps(workspace_settings(sroot), indent=1) + "\n")
        log("runtree: workspace mode: wrote %s" % sp)
        log(PRECEDENCE_II)
    return 0


def list_trees(root, log=print):
    up = os.path.join(root, ".upstream")
    n = 0
    if os.path.isdir(up):
        for d in sorted(os.listdir(up)):
            if not d.endswith(".git"):
                continue
            out = _kit.run(["git", "-C", os.path.join(up, d), "worktree", "list", "--porcelain"], check=False).out
            for blk in out.split("\n\n"):
                lines = dict(l.split(" ", 1) for l in blk.splitlines() if " " in l)
                if "worktree" in lines and not blk.strip().endswith("bare") and "bare" not in blk.splitlines():
                    n += 1
                    log("  %-45s %s %s" % (d[:-4], lines.get("HEAD", "")[:12], lines["worktree"]))
    log("runtree: %d run tree(s)" % n)
    return 0


def remove(root, key, station=None, rr=None, force=False, log=print):
    src = {s["key"]: s for s in _kit.read_json(os.path.join(root, "registry", "sources.json"))["sources"]}
    if key not in src:
        log("runtree: %s is not a registry key" % key)
        return 2
    sha = src[key]["sha"]
    path = tree_path(run_root(rr), station_for(root, key, station), key, sha)
    bare = bootstrap.bare_path(root, key)
    args = ["git", "-C", bare, "worktree", "remove"] + (["--force"] if force else []) + [path]
    p = _kit.run(args, check=False)
    if p.returncode != 0:
        log("runtree: not removed (%s); dirty trees need --force" % p.err.strip()[:200])
        return 1
    log("runtree: removed %s" % path)
    return 0


def _selftest():
    tmp = tempfile.mkdtemp(prefix="kit-runtree-")
    quiet = lambda *a: None
    try:
        remote, v1, _ = bootstrap.make_remote(tmp, "o~ws")
        open(os.path.join(remote, "CLAUDE.md"), "w").write("upstream rules\n")
        rows = [{"key": "o~ws", "repo": "o/ws", "url": "file://" + remote, "sha": v1}]
        homes = [{"key": "o~ws", "lands": [{"station": "career", "how": "bootstrap"}]}]
        root = bootstrap.make_kit_root(tmp, rows, homes)
        rr = os.path.join(tmp, "run")
        assert add(root, "o~ws", rr=rr, log=quiet) == 1, "no pin yet -> refuse"
        assert bootstrap.run(root, rows, log=quiet) == 0
        msgs = []
        assert add(root, "o~ws", workspace=True, rr=rr, log=msgs.append) == 0
        path = tree_path(rr, "career", "o~ws", v1)
        assert os.path.isfile(os.path.join(path, "README.md")), "checked out at the pin"
        assert open(os.path.join(path, "README.md")).read() == "v1\n"
        assert not path.startswith(root), "run tree is outside the kit"
        s = json.load(open(os.path.join(path, ".claude", "settings.local.json")))
        cmds = [h["command"] for m in s["hooks"]["PreToolUse"] for h in m["hooks"]]
        assert any("deny_destructive.py" in c and os.path.abspath(root) in c for c in cmds), cmds
        assert any("station_dispatch.py" in c for c in cmds)
        assert any("PRECEDENCE case ii" in m for m in msgs)
        listed = []
        list_trees(root, log=listed.append)
        assert any(path in l for l in listed), listed
        assert add(root, "o~ws", rr=rr, log=quiet) == 0, "idempotent"
        open(os.path.join(path, "dirty.txt"), "w").write("x")
        assert remove(root, "o~ws", rr=rr, log=quiet) == 1, "dirty tree needs --force"
        assert remove(root, "o~ws", rr=rr, force=True, log=quiet) == 0
        assert not os.path.exists(path)
        print("selftest OK")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("key", nargs="?")
    ap.add_argument("--station")
    ap.add_argument("--workspace", action="store_true")
    ap.add_argument("--root", default=_kit.REPO_ROOT_GUESS)
    ap.add_argument("--run-root")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--remove", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return _selftest()
    try:
        if a.list:
            return list_trees(a.root)
        if not a.key:
            ap.print_help()
            return 2
        if a.remove:
            return remove(a.root, a.key, a.station, a.run_root, a.force)
        return add(a.root, a.key, a.station, a.workspace, a.run_root)
    except (OSError, ValueError, KeyError, _kit.KitError) as e:
        print("runtree: %s" % e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
