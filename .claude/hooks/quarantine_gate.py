#!/usr/bin/env python3
"""quarantine_gate.py — station hook MODULE (run in-process by station_dispatch.py): install/run inside a quarantined tree ASKS.

Earned by: ORDER 4 (b) (verbatim: "quarantine, it exists, its public, its on github, just pack them together") and
ORDER 4 (a) (AutoHedge "study it intently"): camofox-browser, Maxun and AIHawk/invisible_dots ship stealth/evasion
code, Maxun and camofox phone home (posthog, sentry, lib/reporter.js), and AutoHedge can sign live swaps. They are held
WHOLE and READABLE; what must be a deliberate act is installing their dependencies or executing them. LEAN LL-09/LL-08
(run as a tool, never vendored into the station's own graph) and LL-14 (an ask releases on the operator's answer).

API: check(event, payload, station) -> None | {"decision": "ask", "reason": str}
  ASK when a Bash segment is an install/run form —
    npm|pnpm|yarn|bun (i|install|ci|add|run|exec|x|start|dev), npx, pnpx, bunx,
    pip|pip3|uv|poetry|pipenv (install|run|sync|add), python|python3 <path>, node|deno|ts-node|tsx <path>,
    docker (compose)? (up|run|build|start), docker-compose (up|run|build), make, cargo (build|run|install),
    bash|sh|zsh <script>, ./<script>, playwright install
  — AND the segment's working directory (tracking `cd` / `pushd` / `make -C` / `npm --prefix` / `--cwd` inside the
  command), one of its arguments, the value of a leading `VAR=value` prefix (split on `:`, so
  `PYTHONPATH=study/x python3 -m pkg` counts), or a `-c`/`-e` code string that names the path as a substring
  (`python3 -c "runpy.run_path('study/x/main.py')"`) resolves inside a station.json `quarantined` path. A bare `yarn`
  or `bun` (which installs) is an install form (SAFETY 2).
  Reads (cat, less, grep, rg, git show, ls, find, head, wc) never ask.
Release: the operator answers the ask; a governance/RELEASES.json row with scope `quarantine_gate:<path>` (verbatim
`words` + `locator`) turns installs/runs in that path into allow.
Never denies. Run as a script: `--selftest`, or a PreToolUse payload on stdin -> hookSpecificOutput JSON.
"""
import json
import os
import re
import shlex
import sys
from pathlib import Path

SEG_SPLIT = re.compile(r"\|\||&&|;|\||\n|&(?!>)")
PKG = {"npm", "pnpm", "yarn", "bun"}
PKG_VERBS = {"i", "install", "ci", "add", "run", "exec", "x", "start", "dev", "run-script", "test"}
PY_PKG = {"pip", "pip3", "uv", "poetry", "pipenv", "pdm"}
PY_VERBS = {"install", "run", "sync", "add"}
INTERP = {"python", "python3", "node", "deno", "ts-node", "tsx", "bash", "sh", "zsh"}
DIRECT = {"npx", "pnpx", "bunx", "make", "gmake"}


def _segments(cmd):
    """Quote-aware statements (_cmdscan.segments: `python3 -c "a; b"` stays one segment); regex split as a fallback."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import _cmdscan
        return _cmdscan.segments(cmd or "")
    except Exception:
        return SEG_SPLIT.split(cmd or "")


def root_of(payload, station):
    return Path(station.get("_root") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve()


def released(root, scope, text):
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import _release
        return bool(_release.covers(scope, text, root=root))
    except Exception:
        pass
    try:
        rows = json.loads((Path(root) / "governance" / "RELEASES.json").read_text(encoding="utf-8")).get("releases", [])
    except (OSError, ValueError):
        return False
    return any(r.get("scope") == scope and r.get("words") and r.get("locator") for r in rows)


def _tokens(seg):
    try:
        return shlex.split(seg, posix=True)
    except ValueError:
        return seg.split()


def run_form(toks):
    """The install/run label of a token list, or None."""
    while toks and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", toks[0]):
        toks = toks[1:]
    if toks and toks[0] in ("sudo", "env", "nohup", "time", "exec"):
        toks = toks[1:]
    if not toks:
        return None
    c = os.path.basename(toks[0])
    args = [a for a in toks[1:] if not a.startswith("-")]
    skip = {"--prefix", "-C", "--cwd", "--dir", "--directory", "--project", "-w", "--workspace", "--filter", "-f", "--file", "-p", "--project-name", "--env-file"}
    args = [a for i, a in enumerate(toks[1:]) if not a.startswith("-") and toks[i] not in skip]
    if c in ("yarn", "bun") and not args:
        return "%s (install)" % c
    if c in PKG and args and args[0] in PKG_VERBS:
        return "%s %s" % (c, args[0])
    if c in PY_PKG and args and args[0] in PY_VERBS:
        return "%s %s" % (c, args[0])
    if c in ("python", "python3") or re.fullmatch(r"python3\.\d+", c):
        if "-m" in toks and toks.index("-m") + 1 < len(toks) and toks[toks.index("-m") + 1] in ("pip", "venv", "playwright"):
            return "%s -m %s" % (c, toks[toks.index("-m") + 1])
        return "%s <script>" % c if args or "-c" in toks else None
    if c in INTERP:
        return "%s <script>" % c if args or "-c" in toks else None
    if c in DIRECT:
        return c
    if c in ("docker", "podman"):
        sub = args[1:] if args[:1] == ["compose"] else args
        if sub[:1] and sub[0] in ("up", "run", "build", "start", "exec"):
            return "%s %s" % (c, " ".join(args[:2]))
        return None
    if c == "docker-compose" and args[:1] and args[0] in ("up", "run", "build", "start"):
        return "docker-compose " + args[0]
    if c == "cargo" and args[:1] and args[0] in ("build", "run", "install"):
        return "cargo " + args[0]
    if c == "playwright" and args[:1] == ["install"]:
        return "playwright install"
    if toks[0].startswith("./") or toks[0].startswith("/") and os.path.basename(toks[0]) not in ("ls", "cat"):
        return "execute %s" % toks[0]
    return None


def _inside(path, base):
    try:
        return os.path.commonpath([str(path), str(base)]) == str(base)
    except ValueError:
        return False


def evaluate(cmd, cwd, root, qpaths):
    """[(label, quarantined path)] for each install/run segment that touches a quarantined path."""
    hits = []
    cur = Path(cwd).resolve()
    for seg in _segments(cmd):
        seg = seg.strip()
        if not seg:
            continue
        toks = _tokens(seg)
        if toks[:1] and toks[0] in ("cd", "pushd") and len(toks) > 1:
            cur = (cur / toks[1]).resolve() if not os.path.isabs(toks[1]) else Path(toks[1]).resolve()
            continue
        label = run_form(toks)
        if not label:
            continue
        dirs = [cur]
        while toks and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", toks[0]):
            for part in toks[0].split("=", 1)[1].split(":"):
                if part.strip():
                    dirs.append((cur / part).resolve())
            toks = toks[1:]
        codes = [toks[i + 1] for i, a in enumerate(toks[:-1]) if a in ("-c", "-e", "--eval", "-p", "--print")]
        for flag in ("-C", "--prefix", "--cwd", "--dir", "--directory", "--project", "-f", "--file"):
            if flag in toks and toks.index(flag) + 1 < len(toks):
                dirs.append((cur / toks[toks.index(flag) + 1]).resolve())
        for a in toks[1:]:
            if a.startswith("-") and "=" in a:
                a = a.split("=", 1)[1]
            if "/" in a or a.startswith("."):
                dirs.append((cur / a).resolve())
        if toks and ("/" in toks[0]):
            dirs.append((cur / toks[0]).resolve())
        for q in qpaths:
            qa = (root / q).resolve()
            qs = q.rstrip("/")
            if any(_inside(d, qa) for d in dirs) or any(qs in code for code in codes):
                hits.append((label, q))
                break
    return hits


def check(event, payload, station):
    if event != "PreToolUse" or payload.get("tool_name") != "Bash":
        return None
    station = station or {}
    qpaths = [q for q in station.get("quarantined") or [] if q]
    if not qpaths:
        return None
    root = root_of(payload, station)
    cmd = (payload.get("tool_input") or {}).get("command", "")
    hits = evaluate(cmd, payload.get("cwd") or root, root, qpaths)
    hits = [(l, q) for l, q in hits if not released(root, "quarantine_gate:" + q, cmd)]
    if not hits:
        return None
    label, q = hits[0]
    return {"decision": "ask",
            "reason": "QUARANTINE-GATE: `%s` would install or run code from quarantined %s (held for study; may phone home, "
                      "evade, or sign) — confirm to proceed; release: a RELEASES.json row scope quarantine_gate:%s quoting the operator"
                      % (label, q, q)}


def _commit_releases(root, rows):
    """Selftest helper: commit governance/RELEASES.json on a `main` branch, as _release.covers reads it from there."""
    import subprocess
    (Path(root) / "governance").mkdir(exist_ok=True)
    (Path(root) / "governance/RELEASES.json").write_text(json.dumps({"releases": rows}))
    g = ["git", "-C", str(root), "-c", "user.name=kit", "-c", "user.email=kit@localhost"]
    subprocess.run(["git", "-C", str(root), "init", "-q", "-b", "main"], check=True)
    subprocess.run(g + ["add", "--", "governance/RELEASES.json"], check=True)
    subprocess.run(g + ["commit", "-qm", "releases"], check=True)


def selftest():
    import tempfile
    cases = 0
    with tempfile.TemporaryDirectory() as t:
        root = Path(t).resolve()
        for q in ("upstream/jo-inc~camofox-browser", "study/T~A", "upstream/getmaxun~maxun/server"):
            (root / q).mkdir(parents=True)
        st = {"name": "quarantine", "_root": str(root),
              "quarantined": ["upstream/jo-inc~camofox-browser/", "study/T~A/", "upstream/getmaxun~maxun/"]}

        def c(cmd, cwd=None):
            return check("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(cwd or root)}, st)

        asks = [
            "cd upstream/jo-inc~camofox-browser && npm install",
            "npm --prefix upstream/jo-inc~camofox-browser ci",
            "npx playwright install",  # cwd inside (below)
            "python3 study/T~A/main.py",
            "cd study/T~A; uv sync",
            "docker compose -f upstream/getmaxun~maxun/docker-compose.yml up -d",
            "make -C upstream/getmaxun~maxun/server",
            "bash upstream/jo-inc~camofox-browser/scripts/install.sh",
            "node upstream/getmaxun~maxun/server/src/index.js",
            "cd upstream/getmaxun~maxun && pip install -r requirements.txt",
            "PYTHONPATH=study/T~A python3 -m autohedge.main",
            "PYTHONPATH=/opt/lib:study/T~A python3 -m autohedge.main",
            "python3 -c \"import runpy; runpy.run_path('study/T~A/example.py')\"",
            "node -e \"require('./upstream/getmaxun~maxun/server/src/index.js')\"",
            "cd upstream && cd jo-inc~camofox-browser && yarn",
            "cd upstream/jo-inc~camofox-browser && bun",
        ]
        for cmd in asks:
            cwd = root / "upstream/jo-inc~camofox-browser" if cmd.startswith("npx") else None
            r = c(cmd, cwd)
            assert r and r["decision"] == "ask", (cmd, r)
            cases += 1
        allows = [
            "cat upstream/jo-inc~camofox-browser/lib/reporter.js",
            "grep -rn posthog upstream/getmaxun~maxun/server/src",
            "ls study/T~A && wc -l study/T~A/main.py",
            "npm install",  # outside any quarantined path
            "python3 tools/station_audit.py",
            "git log --oneline -3",
            "node --version",
            "yarn",  # bare yarn outside any quarantined path
            "PYTHONPATH=tools python3 -m pytest",
            "python3 -c 'print(1)'",
        ]
        for cmd in allows:
            assert c(cmd) is None, (cmd, c(cmd))
            cases += 1
        assert check("PreToolUse", {"tool_name": "Read", "tool_input": {"file_path": "study/T~A/main.py"}}, st) is None
        assert check("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": "npm i"}}, {"_root": str(root)}) is None, "no quarantined[] -> nothing"
        cases += 2
        _commit_releases(root, [{"id": "REL-0003", "scope": "quarantine_gate:study/T~A/", "words": "you may run autohedge paper mode",
                                 "locator": "fixture", "utc": "2026-10-16T00:00Z", "expires": "2999-01-01T00:00Z"}])
        assert c("python3 study/T~A/main.py") is None, "release row allows"
        assert c("cd upstream/jo-inc~camofox-browser && npm install")["decision"] == "ask", "release is per path"
        cases += 2
    print("quarantine_gate selftest OK (%d cases)" % cases)
    return 0


def main():
    if "--selftest" in sys.argv[1:]:
        return selftest()
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd())
        station = json.loads((root / "station.json").read_text()) if (root / "station.json").exists() else {}
        station["_root"] = str(root)
        r = check(payload.get("hook_event_name", "PreToolUse"), payload, station)
    except Exception:
        return 0
    if r:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": r["decision"],
                                                 "permissionDecisionReason": r["reason"]}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
