#!/usr/bin/env python3
"""_cmdscan.py -- the one shell-command scanner every Bash hook uses (LEAN CA-05). stdlib only.

owner: governance/rules.json R-hook-libs
A hook that greps the raw command string denies `echo "git add -A"` and misses `cd x && git add -A`.
This library parses instead:
  strip_heredocs(cmd)  heredoc BODIES removed (the `<<EOF` line stays, the body is data)
  blanked(cmd)         quoted strings emptied ('..' and ".." become '' and "")
  segments(cmd)        raw statements split at ; && || | & newline ( ) $( ` -- outside quotes
  statements(cmd)      argv per statement, env assignments and wrappers (sudo, env, nohup, time, command,
                       exec, builtin) dropped, `bash|sh|zsh -c "<cmd>"` and `eval "<cmd>"` scanned recursively
  git_calls(cmd)       [(dir_or_None, subcommand, args)] honouring `git -C <dir>` and `-c k=v`
  written_paths(cmd)   paths a command would WRITE: redirect targets, tee, sed -i, cp/mv/install dest,
                       rm/rmdir/truncate/touch args, git checkout|restore paths
Earned by: lettuce L86/L82 -- the first deny hooks were regexes over the raw string; a quoted mention was
denied and a chained statement slipped through (LEAN LL-12, CA-05).
"""
import re
import shlex
import sys

WRAPPERS = {"sudo", "env", "nohup", "time", "command", "exec", "builtin", "nice", "stdbuf", "timeout"}
SHELLS = {"bash", "sh", "zsh", "dash"}
_HEREDOC_RE = re.compile(r"<<(-?)\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")


def strip_heredocs(cmd):
    """Remove heredoc bodies; keep the line that opens them."""
    lines = cmd.split("\n")
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        delims = [(m.group(1) == "-", m.group(3)) for m in _HEREDOC_RE.finditer(blanked(line, keep_heredoc=True))]
        i += 1
        for dash, d in delims:
            while i < len(lines):
                body = lines[i].lstrip("\t") if dash else lines[i]
                i += 1
                if body.strip() == d:
                    break
    return "\n".join(out)


def blanked(cmd, keep_heredoc=False):
    """Quoted strings emptied; escapes kept as-is outside quotes."""
    out, i, q = [], 0, None
    while i < len(cmd):
        c = cmd[i]
        if q is None:
            if c == "\\" and i + 1 < len(cmd):
                out.append(cmd[i:i + 2])
                i += 2
                continue
            if c in ("'", '"'):
                if keep_heredoc and i > 1 and cmd[max(0, i - 3):i].replace(" ", "").endswith("<<"):
                    out.append(c)  # <<'EOF' keeps its delimiter visible
                    j = cmd.find(c, i + 1)
                    if j > 0:
                        out.append(cmd[i + 1:j + 1])
                        i = j + 1
                        continue
                q = c
                out.append(c)
            else:
                out.append(c)
        else:
            if q == '"' and c == "\\" and i + 1 < len(cmd):
                i += 2
                continue
            if c == q:
                out.append(c)
                q = None
        i += 1
    return "".join(out)


def segments(cmd):
    """Statements as raw strings (quotes intact), split outside quotes."""
    cmd = strip_heredocs(cmd)
    segs, cur, i, q = [], [], 0, None
    while i < len(cmd):
        c = cmd[i]
        if q:
            cur.append(c)
            if q == '"' and c == "\\" and i + 1 < len(cmd):
                cur.append(cmd[i + 1])
                i += 2
                continue
            if c == q:
                q = None
            i += 1
            continue
        if c == "\\" and i + 1 < len(cmd):
            if cmd[i + 1] == "\n":
                i += 2
                continue
            cur.append(cmd[i:i + 2])
            i += 2
            continue
        if c in ("'", '"'):
            q = c
            cur.append(c)
            i += 1
            continue
        two = cmd[i:i + 2]
        if two in ("&&", "||", "$("):
            segs.append("".join(cur))
            cur = []
            i += 2
            continue
        if c == "&" and (cmd[i - 1:i] in (">", "<") or cmd[i + 1:i + 2] == ">"):
            cur.append(c)  # 2>&1, &>file
            i += 1
            continue
        if c in ";|&\n()`{}":
            segs.append("".join(cur))
            cur = []
            i += 1
            continue
        cur.append(c)
        i += 1
    segs.append("".join(cur))
    return [s.strip() for s in segs if s.strip()]


def _split(seg):
    try:
        toks = shlex.split(seg, comments=True)
    except ValueError:
        toks = seg.split()
    return [t for t in toks if not t.startswith("<<")]


def _raw_tokens(seg):
    """Tokens with their quotes kept (a quoted '>x' is data, not a redirect)."""
    try:
        lx = shlex.shlex(seg, posix=False)
        lx.whitespace_split = True
        lx.commenters = ""
        return list(lx)
    except ValueError:
        return seg.split()


def _unq(t):
    return t[1:-1] if len(t) >= 2 and t[0] == t[-1] and t[0] in "'\"" else t


def _unwrap(argv):
    while argv:
        a = argv[0]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", a):
            argv = argv[1:]
            continue
        if a in WRAPPERS:
            argv = argv[1:]
            while argv and (argv[0].startswith("-") or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", argv[0])
                            or (a == "timeout" and re.match(r"^\d", argv[0]))):
                argv = argv[1:]
            continue
        break
    return argv


def statements(cmd, _depth=0):
    """argv lists, one per simple command, recursing into sh -c / eval strings."""
    out = []
    for seg in segments(cmd):
        argv = _unwrap(_split(seg))
        if not argv:
            continue
        base = argv[0].rsplit("/", 1)[-1]
        if _depth < 3 and base in SHELLS and "-c" in argv[1:]:
            k = argv.index("-c")
            if k + 1 < len(argv):
                out.extend(statements(argv[k + 1], _depth + 1))
                continue
        if _depth < 3 and base == "eval" and len(argv) > 1:
            out.extend(statements(" ".join(argv[1:]), _depth + 1))
            continue
        out.append(argv)
    return out


def git_calls(cmd):
    """[(dir, sub, args)] for every git statement. dir is the -C value (None = cwd)."""
    calls = []
    for argv in statements(cmd):
        if argv[0].rsplit("/", 1)[-1] != "git":
            continue
        i, d = 1, None
        while i < len(argv) and argv[i].startswith("-"):
            if argv[i] == "-C" and i + 1 < len(argv):
                d = argv[i + 1] if d is None else d.rstrip("/") + "/" + argv[i + 1]
                i += 2
                continue
            if argv[i] in ("-c", "--git-dir", "--work-tree", "--namespace") and i + 1 < len(argv):
                i += 2
                continue
            i += 1
        if i < len(argv):
            calls.append((d, argv[i], argv[i + 1:]))
    return calls


def written_paths(cmd):
    paths = []
    for seg in segments(cmd):
        argv = _unwrap(_split(seg))
        raw = _raw_tokens(seg)
        # redirections (quotes respected: `echo ">x"` is not a redirect)
        for k, a in enumerate(raw):
            m = re.match(r"^\d*(>>?|&>>?)(.*)$", a)
            if m and not a.startswith(">&") and "&" not in m.group(2)[:1]:
                tgt = _unq(m.group(2) or (raw[k + 1] if k + 1 < len(raw) else ""))
                if tgt and not tgt.startswith("&") and tgt != "/dev/null":
                    paths.append(tgt)
        if not argv:
            continue
        base = argv[0].rsplit("/", 1)[-1]
        args = [a for a in argv[1:] if not re.match(r"^\d*(>>?|&>>?)", a)]
        plain = [a for a in args if not a.startswith("-")]
        if base == "tee":
            paths.extend(plain)
        elif base == "sed" and any(a == "-i" or a.startswith("-i") or a == "--in-place" for a in args):
            paths.extend(plain[1:] if len(plain) > 1 else [])
        elif base in ("cp", "mv", "install", "ln", "rsync") and len(plain) >= 2:
            t = [a for a in args if a.startswith("--target-directory=")]
            paths.append(t[0].split("=", 1)[1] if t else plain[-1])
            if base == "mv":
                paths.extend(plain[:-1])  # the source disappears too
        elif base in ("rm", "rmdir", "truncate", "touch", "unlink", "shred", "chmod", "chown"):
            paths.extend(plain[1:] if base in ("chmod", "chown") else plain)
        elif base == "git" and len(argv) > 1:
            for d, sub, gargs in git_calls(seg):
                if sub in ("checkout", "restore"):
                    if "--" in gargs:
                        paths.extend(gargs[gargs.index("--") + 1:])
                    elif sub == "restore":
                        paths.extend(a for a in gargs if not a.startswith("-"))
                elif sub in ("rm", "mv"):
                    paths.extend(a for a in gargs if not a.startswith("-"))
    return paths


# ---------------------------------------------------------------- selftest
def selftest():
    cases = [
        ("statements", 'echo "git add -A"', [["echo", "git add -A"]]),
        ("statements", "cd x && git add -A", [["cd", "x"], ["git", "add", "-A"]]),
        ("statements", "FOO=1 sudo -E git push -f", [["git", "push", "-f"]]),
        ("statements", "bash -c 'git reset --hard'", [["git", "reset", "--hard"]]),
        ("statements", "cat <<'EOF'\ngit add -A\nEOF\necho ok", [["cat"], ["echo", "ok"]]),
        ("written_paths", 'echo hi > "upstream/q x"', ["upstream/q x"]),
        ("statements", "cat <<EOF > f\npkill node\nEOF", [["cat", ">", "f"]]),
        ("statements", "a; b | c || d & e", [["a"], ["b"], ["c"], ["d"], ["e"]]),
        ("statements", "x=$(git stash drop)", [["git", "stash", "drop"]]),
        ("statements", "ls 2>&1 | head", [["ls", "2>&1"], ["head"]]),
        ("git_calls", "git -C ../w -c user.name=x commit -a -m 'm'", [("../w", "commit", ["-a", "-m", "m"])]),
        ("git_calls", "echo git push --force", []),
        ("written_paths", "echo hi > upstream/a/x", ["upstream/a/x"]),
        ("written_paths", "echo '>upstream/a/x'", []),
        ("written_paths", "sed -i s/a/b/ upstream/a/x", ["upstream/a/x"]),
        ("written_paths", "cp a b/c && rm -rf d", ["b/c", "d"]),
        ("written_paths", "git checkout -- p1 p2", ["p1", "p2"]),
        ("written_paths", "cat upstream/a/x | tee out.txt", ["out.txt"]),
        ("written_paths", "ls 2>/dev/null >>log.txt", ["log.txt"]),
    ]
    fails = []
    for fn, arg, want in cases:
        got = globals()[fn](arg)
        if got != want:
            fails.append("%s(%r) = %r, want %r" % (fn, arg, got, want))
    if fails:
        print("selftest FAILED (%d of %d cases)" % (len(fails), len(cases)))
        for f in fails:
            print(" - " + f)
        return 1
    print("selftest OK (%d cases)" % len(cases))
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    print("\n".join(" ".join(a) for a in statements(sys.stdin.read())))
