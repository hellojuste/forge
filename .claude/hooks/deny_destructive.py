#!/usr/bin/env python3
"""deny_destructive.py -- PreToolUse Bash DENY: no erasure of work (GOV 3.13, LEAN CA-07/LL-17).

owner: governance/rules.json R-destructive
Matching goes through _cmdscan.statements(): heredoc bodies and quoted strings are data, statements are
split at ; && || | & ( ) $( so `echo "git add -A"` passes and `cd x && git add -A` is denied. Every
state-dependent shape is measured IN THE COMMAND'S REPO AT HOOK TIME (payload cwd + `git -C <dir>`).

Earned by: lettuce LEDGER L86 (`git add -A` swept two workers' in-flight files into an unrelated commit;
`pkill -f` killed a sibling's baseline run), L82, S15/S79, L415 (force-push deny widened to every ref).
Release: the allowed form printed on the deny line (e.g. `git add <paths>`, `--force-with-lease`,
commit or stash first, `kill <pid>`), or a governance/RELEASES.json row with scope deny_destructive read
from the protected branch.
Exit: 2 = DENY (one stderr line naming the release) . 0 = allow, or fail-open with one report line.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _cmdscan  # noqa: E402

SCOPE = "deny_destructive"


class StateUnreadable(Exception):
    pass


def _git(d, *args):
    r = subprocess.run(["git", "-C", str(d), *args], capture_output=True, text=True)
    return r


def _repo_dir(cwd, d):
    base = Path(cwd or os.getcwd())
    return (base / d) if d else base


def _dirty_tracked(d):
    r = _git(d, "status", "--porcelain", "--untracked-files=no")
    if r.returncode != 0:
        raise StateUnreadable("git status failed in %s" % d)
    return [l[3:] for l in r.stdout.splitlines() if l.strip()]


def _dirty_paths(d, paths):
    r = _git(d, "status", "--porcelain", "--untracked-files=no", "--", *paths)
    if r.returncode != 0:
        raise StateUnreadable("git status failed in %s" % d)
    return [l[3:] for l in r.stdout.splitlines() if l.strip() and l[1] != " "]


def _flags(args):
    """Short flags exploded: -fdx -> {-f,-d,-x}; long flags kept."""
    out = set()
    for a in args:
        if a.startswith("--"):
            out.add(a.split("=", 1)[0])
        elif a.startswith("-") and len(a) > 1:
            out.update("-" + c for c in a[1:])
    return out


# ---------------------------------------------------------------- the shape table
# Each shape: (name, test(dir, sub, args, cfg) -> erase-what | None, release). test raises StateUnreadable.
def t_add_all(d, sub, args, cfg):
    if sub == "add":
        f = _flags(args)
        plain = [a for a in args if not a.startswith("-")]
        if "-A" in f or "--all" in f or "." in plain or "*" in plain or (("-u" in f or "--update" in f) and not plain):
            return "stage every changed file in the tree, including other writers' in-flight work"
    if sub == "commit" and ({"-a", "--all"} & _flags(args)):
        return "commit every modified tracked file, including other writers' in-flight work"
    return None


def t_force_push(d, sub, args, cfg):
    if sub != "push":
        return None
    f = _flags([a for a in args if not a.startswith("--force-with-lease") and not a.startswith("--force-if-includes")])
    if "--force" in f or "-f" in f or any(a.startswith("+") for a in args if not a.startswith("-")):
        return "overwrite the remote ref and drop commits someone else pushed"
    return None


def t_hard_reset(d, sub, args, cfg):
    f = _flags(args)
    hit = (sub == "reset" and "--hard" in f) or (sub == "checkout" and ("-f" in f or "--force" in f)) \
        or (sub == "switch" and ("--discard-changes" in f or "-f" in f or "--force" in f))
    if not hit:
        return None
    dirty = _dirty_tracked(d)
    return ("discard uncommitted edits in %s" % ", ".join(dirty[:3])) if dirty else None


def t_checkout_paths(d, sub, args, cfg):
    if sub not in ("checkout", "restore"):
        return None
    f = _flags(args)
    if sub == "restore" and ("--staged" in f or "-S" in f) and not ("--worktree" in f or "-W" in f):
        return None  # index only: the worktree edits survive
    if "--" in args:
        paths = args[args.index("--") + 1:]
    elif sub == "restore":
        paths = [a for a in args if not a.startswith("-")]
    else:
        plain = [a for a in args if not a.startswith("-")]
        paths = [a for a in plain if (Path(d) / a).exists() and _git(d, "rev-parse", "-q", "--verify", a).returncode != 0]
    if not paths:
        return None
    dirty = _dirty_paths(d, paths)
    return ("overwrite uncommitted edits in %s" % ", ".join(dirty[:3])) if dirty else None


def t_clean(d, sub, args, cfg):
    if sub != "clean":
        return None
    f = _flags(args)
    if "-n" in f or "--dry-run" in f or not ("-f" in f or "--force" in f):
        return None
    dry = ["-n"] + [a for a in args if a.startswith("-") and a not in ("-f", "--force", "-i", "--interactive")]
    dry = [("-" + "".join(c for c in a[1:] if c != "f")) if (a.startswith("-") and not a.startswith("--") and "f" in a) else a
           for a in dry]
    dry = [a for a in dry if a != "-"]
    r = _git(d, "clean", *dry)
    if r.returncode != 0:
        raise StateUnreadable("git clean -n failed in %s" % d)
    files = [l.replace("Would remove ", "") for l in r.stdout.splitlines() if l.strip()]
    return ("delete untracked %s" % ", ".join(files[:3])) if files else None


def t_branch_delete(d, sub, args, cfg):
    if sub != "branch":
        return None
    f = _flags(args)
    if not ("-D" in f or (("--delete" in f or "-d" in f) and ("--force" in f or "-f" in f))):
        return None
    lost = []
    for b in [a for a in args if not a.startswith("-")]:
        r = _git(d, "merge-base", "--is-ancestor", b, "HEAD")
        if r.returncode == 1:
            lost.append(b)
        elif r.returncode != 0:
            raise StateUnreadable("cannot resolve branch %s" % b)
    return ("drop unmerged commits on %s" % ", ".join(lost)) if lost else None


def t_worktree_force(d, sub, args, cfg):
    if sub == "worktree" and args[:1] == ["remove"] and ({"--force", "-f"} & _flags(args[1:])):
        return "delete a worktree with its uncommitted and untracked work"
    return None


def t_stash_drop(d, sub, args, cfg):
    if sub == "stash" and args[:1] in (["drop"], ["clear"]) and cfg.get("protect_stash"):
        return "destroy stashed work"
    return None


GIT_SHAPES = [
    ("git add -A/./--all/-u, git commit -a", t_add_all, "stage by path: git add <paths>"),
    ("git push --force", t_force_push, "git push --force-with-lease"),
    ("git reset --hard / checkout -f / switch --discard-changes", t_hard_reset, "commit or stash first; on a clean tree it passes"),
    ("git checkout|restore <paths>", t_checkout_paths, "commit or stash those paths first (a dirty path stays denied for --ours/--theirs/--source too)"),
    ("git clean -f", t_clean, "git clean -n to see the list, then delete by path"),
    ("git branch -D", t_branch_delete, "merge it first, or git branch -d"),
    ("git worktree remove --force", t_worktree_force, "git worktree remove <path> without --force (git refuses a dirty tree)"),
    ("git stash drop|clear", t_stash_drop, "git stash pop"),
]


def kill_shape(argv):
    base = argv[0].rsplit("/", 1)[-1]
    if base in ("pkill", "killall"):
        return ("%s" % base, "kill every process matching a pattern, including a sibling's run", "kill <pid>")
    if base == "kill":
        rest = argv[1:]
        if "--" in rest:
            targets = rest[rest.index("--") + 1:]
        else:
            i = 0
            while i < len(rest) and rest[i].startswith("-"):
                a = rest[i]
                if a in ("-s", "-n"):
                    i += 2
                    continue
                if i == 0 and len(rest) > 1 and re.match(r"^-(\d+|[A-Z][A-Z0-9]*)$", a):
                    i += 1  # the signal
                    continue
                break
            targets = rest[i:]
        if any(re.match(r"^-\d+$", t) for t in targets):
            return ("kill -<pgid>|-1", "kill a whole process group or every process you own", "kill <pid>")
    return None


def decide(cmd, cwd=None, cfg=None):
    """(shape, erase, release) for the first destructive statement, else None. May raise StateUnreadable."""
    cfg = cfg or {}
    for argv in _cmdscan.statements(cmd):
        k = kill_shape(argv)
        if k:
            return k
    for d, sub, args in _cmdscan.git_calls(cmd):
        rd = _repo_dir(cwd, d)
        for name, test, release in GIT_SHAPES:
            erase = test(rd, sub, args, cfg)
            if erase:
                return (name, erase, release)
    return None


def _cfg(root):
    cfg = {}
    for rel in ("commons/defaults.json", "station.json"):
        try:
            cfg.update((json.loads((Path(root) / rel).read_text(encoding="utf-8")).get("gov") or {}))
        except (OSError, ValueError):
            pass
    return cfg


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    if payload.get("tool_name", "Bash") != "Bash":
        return 0
    cmd = (payload.get("tool_input") or {}).get("command") or ""
    if not cmd.strip():
        return 0
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    try:
        hit = decide(cmd, payload.get("cwd") or os.getcwd(), _cfg(root))
    except StateUnreadable as e:
        import _report
        _report.report("PreToolUse", "deny_destructive: cannot read the state it guards (%s); allowed, fail-open" % e,
                       payload=payload, root=root)
        return 0
    except Exception as e:  # never brick the session
        import _report
        _report.report("PreToolUse", "deny_destructive: internal error (%s); allowed, fail-open" % e, payload=payload, root=root)
        return 0
    if not hit:
        return 0
    try:
        import _release
        if _release.covers(SCOPE, cmd, root=root):
            return 0
    except Exception:
        pass
    shape, erase, release = hit
    sys.stderr.write("DENY-DESTRUCTIVE: %s would %s — release: %s (or a governance/RELEASES.json row, scope %s)\n"
                     % (shape, erase, release, SCOPE))
    return 2


# ---------------------------------------------------------------- selftest
def selftest():
    import tempfile
    fails, n = [], 0

    def run(cmd, cwd, env=None):
        p = subprocess.run([sys.executable, str(Path(__file__).resolve())], input=json.dumps(
            {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(cwd), "session_id": "st"}),
            capture_output=True, text=True, cwd=str(cwd), env=dict(os.environ, CLAUDE_PROJECT_DIR=str(cwd), **(env or {})))
        return p.returncode, p.stderr

    def expect(cmd, cwd, want, label=None):
        nonlocal n
        n += 1
        rc, err = run(cmd, cwd)
        lines = [l for l in err.splitlines() if l.strip()]
        if want == 2 and not (rc == 2 and len(lines) == 1 and "release:" in lines[0]):
            fails.append("%s: want DENY with one release line, got rc=%s %r" % (label or cmd, rc, err))
        elif want == 0 and rc != 0:
            fails.append("%s: want allow, got rc=%s %r" % (label or cmd, rc, err))

    with tempfile.TemporaryDirectory() as td:
        r = Path(td) / "repo"
        r.mkdir()
        g = lambda *a: subprocess.run(["git", "-C", str(r), *a], capture_output=True, text=True)
        g("init", "-q", "-b", "main")
        (r / "a.txt").write_text("a\n")
        (r / "b.txt").write_text("b\n")
        g("add", "--", "a.txt", "b.txt")
        g("-c", "user.name=k", "-c", "user.email=k@l", "commit", "-qm", "base")
        g("branch", "merged")
        g("switch", "-q", "-c", "feature")
        (r / "f.txt").write_text("f\n")
        g("add", "--", "f.txt")
        g("-c", "user.name=k", "-c", "user.email=k@l", "commit", "-qm", "feature")
        g("switch", "-q", "main")
        # always-denied shapes and their allowed siblings
        for c in ("git add -A", "git add .", "git add --all", "git add -u", "git commit -a -m x", "git commit -am x",
                  "cd x && git add -A", "git -C . add -A", "bash -c 'git add -A'"):
            expect(c, r, 2)
        for c in ("git add a.txt", "git add -u a.txt", 'echo "git add -A"', "cat <<'EOF'\ngit add -A\nEOF",
                  "git commit -m 'a -a b'"):
            expect(c, r, 0)
        expect("git push --force origin x", r, 2)
        expect("git push -f", r, 2)
        expect("git push origin +main", r, 2)
        expect("git push --force-with-lease origin x", r, 0)
        expect("git push origin main", r, 0)
        expect("pkill -f node", r, 2)
        expect("killall python3", r, 2)
        expect("kill -9 -1", r, 2)
        expect("kill -- -4242", r, 2)
        expect("kill 4242", r, 0)
        expect("kill -9 4242", r, 0)
        expect("git worktree remove --force ../w", r, 2)
        expect("git worktree remove ../w", r, 0)
        expect("git branch -D feature", r, 2)
        expect("git branch -D merged", r, 0)
        expect("git branch -d feature", r, 0)
        # clean tree: state-dependent shapes pass
        expect("git reset --hard", r, 0, "reset --hard on a clean tree")
        expect("git checkout -f main", r, 0, "checkout -f on a clean tree")
        expect("git checkout -- a.txt", r, 0, "checkout -- clean path")
        expect("git clean -fd", r, 0, "clean with nothing untracked")
        # dirty tree
        (r / "a.txt").write_text("edited\n")
        (r / "u.txt").write_text("untracked\n")
        expect("git reset --hard", r, 2, "reset --hard over an edit")
        expect("git checkout -f main", r, 2, "checkout -f over an edit")
        expect("git switch --discard-changes main", r, 2, "switch --discard-changes over an edit")
        expect("git checkout -- a.txt", r, 2, "checkout -- dirty path")
        expect("git checkout a.txt", r, 2, "checkout <dirty path>")
        expect("git restore a.txt", r, 2, "restore dirty path")
        expect("git checkout --ours -- a.txt", r, 2, "--ours on a dirty path stays denied")
        expect("git checkout --theirs -- b.txt", r, 0, "--theirs on a clean path is exempt")
        expect("git checkout HEAD -- b.txt", r, 0, "<rev> -- clean path")
        expect("git restore --staged a.txt", r, 0, "restore --staged keeps the worktree")
        expect("git clean -fd", r, 2, "clean -f with an untracked file")
        expect("git clean -n", r, 0, "clean -n")
        expect("echo 'git reset --hard'", r, 0, "quoted mention")
        expect("git -C %s reset --hard" % r, Path(td), 2, "git -C <dirty repo> measured there")
        expect("git stash drop", r, 0, "stash drop without protect_stash")
    if fails:
        print("selftest FAILED (%d of %d cases)" % (len(fails), n))
        for f in fails:
            print(" - " + f)
        return 1
    print("selftest OK (%d cases)" % n)
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    sys.exit(main())
