#!/usr/bin/env python3
"""station_dispatch.py -- PreToolUse '.*': run the hook MODULES a station names, in one process.

owner: governance/rules.json R-station-dispatch (commons-gov contract decision 4; GOV 3.11 plug-in rule)
.claude/settings.json is a commons file, identical on every branch, so a station never adds a settings
entry. Instead the effective config (commons/defaults.json `hooks.PreToolUse` UNION station.json
`hooks.PreToolUse`; absent station.json = main, station `core`) names modules:
    bare name       -> .claude/hooks/<name>.py           (commons: act_gate, quarantine_gate, connector_scope)
    station/<name>  -> .claude/hooks/station/<name>.py   (station-only)
Each module exposes  check(event, payload, station) -> None | {"decision": "deny"|"ask"|"report", "reason": str}
where `station` is the effective config dict. Precedence: deny > ask > report. Output is ONE JSON line:
    {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny"|"ask",
                            "permissionDecisionReason": "<reasons>", "additionalContext": "<reports>"}}
or, with reports only, the _report channel (once per session). Exit 0 always.
A module that is missing or raises -> one report line naming it, NEVER a deny (fail open).
Earned by: KIT_PLAN 3.3 -- per-station settings.json entries would make the commons file differ on every
branch and conflict on every sync; modules + one dispatcher keep the commons byte-identical.
Release: a deny or ask names its own release in its reason (module-owned); the dispatcher itself never denies.
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
RANK = {"deny": 3, "ask": 2, "report": 1}


def _load(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _merge(a, b):
    out = dict(a)
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def effective(root):
    base = _load(Path(root) / "commons" / "defaults.json") or {}
    st = _load(Path(root) / "station.json")
    cfg = _merge(base, st or {})
    mods = []
    for src in (base, st or {}):
        for m in ((src.get("hooks") or {}).get("PreToolUse") or []):
            if m not in mods:
                mods.append(m)
    cfg.setdefault("hooks", {})
    cfg["hooks"] = dict(cfg["hooks"], PreToolUse=mods)
    cfg["name"] = (st or {}).get("name", "core")
    return cfg


def module_path(root, name):
    if name.startswith("station/"):
        return Path(root) / ".claude" / "hooks" / "station" / (name.split("/", 1)[1] + ".py")
    return Path(root) / ".claude" / "hooks" / (name + ".py")


def dispatch(event, payload, root):
    cfg = effective(root)
    decisions, reports = [], []
    for name in cfg["hooks"]["PreToolUse"]:
        p = module_path(root, name)
        if not p.exists():
            reports.append("station_dispatch: module %s missing (%s); skipped" % (name, p.relative_to(root)))
            continue
        try:
            spec = importlib.util.spec_from_file_location("stdispatch_" + name.replace("/", "_"), str(p))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            res = mod.check(event, payload, cfg)
        except Exception as e:  # one report line, never a deny
            reports.append("station_dispatch: module %s raised %s: %s; skipped" % (name, type(e).__name__, str(e)[:160]))
            continue
        if not res:
            continue
        d = str(res.get("decision", "")).lower()
        reason = "%s: %s" % (name, res.get("reason", ""))
        if d in ("deny", "ask"):
            decisions.append((RANK[d], d, reason))
        elif d == "report":
            reports.append(reason)
        else:
            reports.append("station_dispatch: module %s returned unknown decision %r; ignored" % (name, d))
    return decisions, reports


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    event = payload.get("hook_event_name") or "PreToolUse"
    try:
        decisions, reports = dispatch(event, payload, root)
    except Exception as e:
        decisions, reports = [], ["station_dispatch: internal error %s; allowed, fail-open" % e]
    if decisions:
        top = max(r for r, _, _ in decisions)
        d = [x for x in decisions if x[0] == top]
        hso = {"hookEventName": "PreToolUse", "permissionDecision": d[0][1],
               "permissionDecisionReason": " | ".join(x[2] for x in d)}
        if reports:
            hso["additionalContext"] = " | ".join(reports)
        print(json.dumps({"hookSpecificOutput": hso}, ensure_ascii=False))
        return 0
    if reports:
        import _report
        _report.report("PreToolUse", " | ".join(reports), payload=payload, root=root)
    return 0


def selftest():
    import shutil
    import subprocess
    import tempfile
    fails, n = [], 0

    def ok(c, m):
        nonlocal n
        n += 1
        if not c:
            fails.append(m)

    def mod(rel, body):
        p = Path(td) / ".claude" / "hooks" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('"""fixture module\nEarned by: selftest\n"""\n' + body, encoding="utf-8")

    def run(payload):
        p = subprocess.run([sys.executable, str(Path(td) / ".claude/hooks/station_dispatch.py")],
                           input=json.dumps(payload), capture_output=True, text=True, cwd=td,
                           env=dict(os.environ, CLAUDE_PROJECT_DIR=td))
        out = p.stdout.strip()
        return p.returncode, (json.loads(out) if out.startswith("{") else out), p.stderr

    with tempfile.TemporaryDirectory() as td:
        hooks = Path(td) / ".claude" / "hooks"
        hooks.mkdir(parents=True)
        for f in ("station_dispatch.py", "_report.py"):
            shutil.copyfile(HERE / f, hooks / f)
        (Path(td) / "commons").mkdir()
        (Path(td) / "commons" / "defaults.json").write_text(json.dumps({"hooks": {"PreToolUse": ["m_report", "m_ask"]}}))
        mod("m_report.py", "def check(e, p, s):\n    return {'decision': 'report', 'reason': 'seen ' + s['name']}\n")
        mod("m_ask.py", "def check(e, p, s):\n    return {'decision': 'ask', 'reason': 'irreversible'} if 'trade' in p.get('tool_input', {}).get('command', '') else None\n")
        mod("m_boom.py", "def check(e, p, s):\n    raise RuntimeError('kaboom')\n")
        mod("station/m_deny.py", "def check(e, p, s):\n    return {'decision': 'deny', 'reason': 'station says no'} if 'rm' in p.get('tool_input', {}).get('command', '') else None\n")
        base = {"tool_name": "Bash", "session_id": "s", "hook_event_name": "PreToolUse"}
        # main (no station.json): commons modules only, station name core
        rc, out, _ = run(dict(base, tool_input={"command": "ls"}))
        ok(rc == 0 and isinstance(out, dict) and "seen core" in out["hookSpecificOutput"]["additionalContext"],
           "main: report through _report with station core: %r" % (out,))
        rc, out, _ = run(dict(base, tool_input={"command": "execute trade"}))
        ok(isinstance(out, dict) and out["hookSpecificOutput"]["permissionDecision"] == "ask", "ask: %r" % (out,))
        # station: union with station modules, deny beats ask, exception = report
        (Path(td) / "station.json").write_text(json.dumps({"name": "markets", "hooks": {"PreToolUse": ["station/m_deny", "m_boom", "m_missing"]}}))
        rc, out, _ = run(dict(base, tool_input={"command": "rm trade"}))
        h = out["hookSpecificOutput"] if isinstance(out, dict) else {}
        ok(rc == 0 and h.get("permissionDecision") == "deny" and "station says no" in h.get("permissionDecisionReason", ""),
           "deny > ask: %r" % (out,))
        ok("kaboom" in h.get("additionalContext", "") and "m_missing missing" in h.get("additionalContext", ""),
           "exception and missing module are report lines: %r" % (h,))
        rc, out, _ = run(dict(base, session_id="s2", tool_input={"command": "ls"}))
        ok(rc == 0 and isinstance(out, dict) and "permissionDecision" not in out.get("hookSpecificOutput", {}),
           "an exception never denies: %r" % (out,))
        ok(effective(td)["hooks"]["PreToolUse"] == ["m_report", "m_ask", "station/m_deny", "m_boom", "m_missing"],
           "union order commons then station: %r" % effective(td)["hooks"]["PreToolUse"])
        rc, out, _ = run(dict(base, session_id="s2", tool_input={"command": "ls"}))
        ok(rc == 0 and out == "", "same reports again in one session: deduplicated: %r" % (out,))
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
