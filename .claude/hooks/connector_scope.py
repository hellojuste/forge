#!/usr/bin/env python3
"""connector_scope.py — station hook MODULE (run in-process by station_dispatch.py): an MCP server outside the station's
expected set is REPORTED once per session (default) or denied (operator's opt-in).

Earned by: LEAN CA-10 / LL-04 (noun decides the station: client ERP data belongs to client-bi, the operator's identity
documents to career; a connector reached from the wrong station is how one noun leaks into another) and lettuce
`deny_connector.sh` (GitHub + Claude_Code_Remote only). ORDER 5 (verbatim: "i dont care about this because im going
local then placing things myself later") turns the lettuce DENY into a REPORT by default: the operator sees the
crossing; nothing blocks him. A station that wants the wall sets station.json `connector_scope: "deny"` and records
that choice as a DEC row.

API: check(event, payload, station) -> None | {"decision": "report"|"deny", "reason": str}
  * tool_name `mcp__<server>__<tool>`; <server> compared case-insensitively (and with `claude_ai_` stripped) against
    station.json `connectors_expected` (absent key = nothing expected is declared -> no report).
  * report: one line per (session_id, server) — remembered in `.station/connector_scope/<session>.json` (gitignored
    runtime dir) so the same crossing is not repeated every call.
  * deny: only when station.json `connector_scope` == "deny".
Release: add the server to `connectors_expected` (station-only file), or set `connector_scope` back to "report".
Run as a script: `--selftest`, or a PreToolUse payload on stdin -> hookSpecificOutput JSON (report -> stderr line).
"""
import json
import os
import re
import sys
from pathlib import Path


def root_of(payload, station):
    return Path(station.get("_root") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())


def server_of(tool):
    m = re.match(r"^mcp__(.+?)__", tool or "")
    return m.group(1) if m else None


def _norm(s):
    s = s.lower()
    return s[len("claude_ai_"):] if s.startswith("claude_ai_") else s


def _seen(root, session, server):
    d = Path(root) / ".station" / "connector_scope"
    f = d / ("%s.json" % re.sub(r"[^A-Za-z0-9_.-]", "_", session or "nosession"))
    try:
        seen = set(json.loads(f.read_text()))
    except (OSError, ValueError):
        seen = set()
    if server in seen:
        return True
    try:
        d.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(sorted(seen | {server})))
    except OSError:
        pass
    return False


def check(event, payload, station):
    if event != "PreToolUse":
        return None
    station = station or {}
    server = server_of(payload.get("tool_name", ""))
    if not server or "connectors_expected" not in station:
        return None
    expected = {_norm(s) for s in station.get("connectors_expected") or []}
    if _norm(server) in expected:
        return None
    mode = station.get("connector_scope", "report")
    name = station.get("name", "this station")
    if mode == "deny":
        return {"decision": "deny",
                "reason": "CONNECTOR-SCOPE: MCP server %s is not in %s's connectors_expected %s (station.json connector_scope: deny) "
                          "— release: add it to connectors_expected or set connector_scope to report" % (server, name, sorted(expected))}
    if _seen(root_of(payload, station), payload.get("session_id"), server):
        return None
    return {"decision": "report",
            "reason": "CONNECTOR-SCOPE: MCP server %s is outside %s's connectors_expected %s — data from another noun may be "
                      "crossing stations (report only; once per session)" % (server, name, sorted(expected))}


def selftest():
    import tempfile
    cases = 0
    with tempfile.TemporaryDirectory() as t:
        st = {"name": "client-bi", "_root": t, "connectors_expected": ["Bisharp_MCP", "github"]}

        def c(tool, session="s1", station=st):
            return check("PreToolUse", {"tool_name": tool, "tool_input": {}, "session_id": session, "cwd": t}, station)

        assert c("mcp__Bisharp_MCP__Trimergo_Projecten_Bisharp") is None
        assert c("mcp__github__get_me") is None
        assert c("mcp__claude_ai_GitHub__get_me") is None, "claude_ai_ prefix and case folded"
        cases += 3
        r = c("mcp__Supabase__execute_sql")
        assert r and r["decision"] == "report" and "Supabase" in r["reason"], r
        assert c("mcp__Supabase__list_tables") is None, "once per session per server"
        assert c("mcp__Supabase__list_tables", session="s2")["decision"] == "report", "new session reports again"
        cases += 3
        deny = dict(st, connector_scope="deny")
        assert c("mcp__Supabase__execute_sql", station=deny)["decision"] == "deny"
        assert c("mcp__Bisharp_MCP__x", station=deny) is None
        cases += 2
        assert c("Bash") is None and c("mcp__x__y", station={"name": "main", "_root": t}) is None, "no key -> silent"
        assert check("PostToolUse", {"tool_name": "mcp__x__y"}, st) is None
        cases += 2
        q = {"name": "quarantine", "_root": t, "connectors_expected": []}
        assert c("mcp__github__get_me", station=q)["decision"] == "report", "empty expected set reports everything"
        cases += 1
    print("connector_scope selftest OK (%d cases)" % cases)
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
    if r and r["decision"] == "deny":
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                 "permissionDecisionReason": r["reason"]}}))
    elif r:
        print(r["reason"], file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
