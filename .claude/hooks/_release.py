#!/usr/bin/env python3
"""_release.py -- committed human exceptions that release a DENY or an ASK (GOV 3.8, LEAN CA-05/LL-16).

owner: governance/rules.json R-hook-libs
    covers(scope, command, root=None, now=None) -> row | None
A release is a row of governance/RELEASES.json read from the PROTECTED branch's copy
(`git show <gov.protected_branches[0..]>:governance/RELEASES.json`), never from the working tree, so a
session cannot grant itself. A row covers when:
  row.scope == scope, or scope starts with row.scope + ":" (act_gate covers act_gate:execute_trade),
  row.match is a substring of the command (or path),
  utc <= now < expires.
No protected ref, no file, or an unreadable file -> None (no release; the deny stands and says why).
Never an env var on the denied command line (LL-14: a release the denied act can itself supply is no gate).
Earned by: lettuce Rule 25 / SEAL_RELEASES -- operator exceptions given in chat were lost or re-asked;
"an operator exception is a committed row".
"""
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_PROTECTED = ["main"]


def _protected(root):
    try:
        d = json.loads((Path(root) / "commons" / "defaults.json").read_text(encoding="utf-8"))
        pb = (d.get("gov") or {}).get("protected_branches") or DEFAULT_PROTECTED
    except (OSError, ValueError):
        pb = DEFAULT_PROTECTED
    try:
        s = json.loads((Path(root) / "station.json").read_text(encoding="utf-8"))
        pb = (s.get("gov") or {}).get("protected_branches") or pb
    except (OSError, ValueError):
        pass
    return pb


def load(root=None, rev=None):
    """Rows from <rev>:governance/RELEASES.json (rev default: first protected branch that exists)."""
    root = Path(root or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    revs = [rev] if rev else _protected(root)
    for r in revs:
        p = subprocess.run(["git", "-C", str(root), "show", "%s:governance/RELEASES.json" % r],
                           capture_output=True, text=True)
        if p.returncode == 0:
            try:
                return json.loads(p.stdout).get("releases", [])
            except ValueError:
                return []
    return []


def _t(s):
    s = str(s).strip().replace("Z", "+00:00")
    if len(s) == 16:  # 2026-10-16T09:00
        s += ":00"
    try:
        v = dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    return v if v.tzinfo else v.replace(tzinfo=dt.timezone.utc)


def active(row, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    a, b = _t(row.get("utc", "")), _t(row.get("expires", ""))
    return bool(a and b and a <= now < b)


def covers(scope, command, root=None, now=None, rows=None):
    for row in (rows if rows is not None else load(root)):
        rs = row.get("scope", "")
        if not rs or not (scope == rs or scope.startswith(rs + ":")):
            continue
        if row.get("match") and row["match"] not in (command or ""):
            continue
        if not row.get("words") or not row.get("locator"):
            continue
        if active(row, now):
            return row
    return None


def selftest():
    fails, n = [], 0

    def ok(c, m):
        nonlocal n
        n += 1
        if not c:
            fails.append(m)

    now = dt.datetime(2026, 10, 16, 12, 0, tzinfo=dt.timezone.utc)
    row = {"id": "REL-0001", "scope": "deny_destructive", "match": "git reset --hard", "words": "yes do it",
           "locator": "chat", "utc": "2026-10-16T09:00Z", "expires": "2026-10-17T09:00Z"}
    ok(covers("deny_destructive", "git reset --hard HEAD~1", rows=[row], now=now), "active row covers")
    ok(not covers("deny_destructive", "git clean -fd", rows=[row], now=now), "match must be a substring")
    ok(not covers("deny_noted_defect", "git reset --hard", rows=[row], now=now), "other scope")
    ok(not covers("deny_destructive", "git reset --hard", rows=[row],
                  now=dt.datetime(2026, 10, 18, tzinfo=dt.timezone.utc)), "expired")
    ok(covers("act_gate:execute_trade", "x", rows=[dict(row, scope="act_gate", match="")], now=now), "stem covers sub-scope")
    ok(not covers("deny_destructive", "git reset --hard", rows=[dict(row, words="")], now=now), "no words, no release")
    with tempfile.TemporaryDirectory() as td:
        g = lambda *a: subprocess.run(["git", "-C", td, *a], capture_output=True, text=True)
        g("init", "-q", "-b", "main")
        Path(td, "governance").mkdir()
        Path(td, "governance", "RELEASES.json").write_text(json.dumps({"releases": []}))
        g("add", "--", "governance/RELEASES.json")
        g("-c", "user.name=k", "-c", "user.email=k@l", "commit", "-qm", "r")
        g("switch", "-q", "-c", "station/x")
        Path(td, "governance", "RELEASES.json").write_text(json.dumps({"releases": [row]}))
        g("add", "--", "governance/RELEASES.json")
        g("-c", "user.name=k", "-c", "user.email=k@l", "commit", "-qm", "self-grant")
        ok(load(td) == [], "a branch cannot grant itself (reads main's copy)")
        ok(load(td, rev="station/x") == [row], "explicit rev reads that copy")
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
    print(json.dumps(load(), indent=1))
