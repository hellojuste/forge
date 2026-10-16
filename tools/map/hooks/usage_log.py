#!/usr/bin/env python3
"""usage_log.py — PostToolUse(Bash|Skill|Read|Task): append one observed-usage event to .usage/log.jsonl.

Earned by: lettuce never closed observed usage (PROGRAMME_MAPPING 2 M4): its usage map was fed only by declared
textual references, and none of its PostToolUse hooks appended a per-call event, so "is it actually used?" had no
answer from data. The dedup lesson rides along: lettuce L265 (pricers summed transcript rows, not API calls, and
overstated dollars 2.3x) -> every row carries the call id, and `tools/map/usage_map.py --observed` dedups on it.
Knob: map M+ (below M it exits 0 silently). The log is gitignored and NEVER written into map/usage.json.
Prints nothing; exit 0 always; fail open.
"""
import datetime
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _common as C  # noqa: E402

SCRIPT = re.compile(r"(?:python3?|bash|sh|node)\s+(\S+\.(?:py|sh|js))")


def event(payload, root):
    tool = payload.get("tool_name") or ""
    ti = payload.get("tool_input") or {}
    kind, target = None, None
    if tool == "Bash":
        cmd = ti.get("command") or ""
        m = SCRIPT.search(cmd) or re.search(r"(?:^|\s)(tools/\S+)", cmd)
        kind, target = "script", m.group(1) if m else None
    elif tool == "Skill":
        kind, target = "skill", ti.get("skill") or ti.get("command")
    elif tool == "Read":
        fp = ti.get("file_path") or ""
        try:
            rel = (Path(fp).resolve().relative_to(Path(root).resolve()).as_posix() if Path(fp).is_absolute() else fp)
        except ValueError:
            rel = ""
        if C.classify(rel, C.domain_cfg(root)) == "held" or rel.startswith(".claude/skills/"):
            kind, target = ("upstream" if C.classify(rel, C.domain_cfg(root)) == "held" else "skill-file"), rel
    elif tool == "Task":
        kind, target = "agent", ti.get("subagent_type")
    if not target:
        return None
    return {"ts": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "session": payload.get("session_id"), "call": payload.get("tool_use_id"), "tool": tool, "kind": kind,
            "target": target}


def log(payload, root):
    if not C.map_at_least(root, "M"):
        return False
    ev = event(payload, root)
    if not ev:
        return False
    d = Path(root) / ".usage"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "log.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(ev, sort_keys=True) + "\n")
    return True


def run_stdin(raw, root):
    try:
        log(json.loads(raw or "{}"), root)
    except Exception:  # noqa: BLE001 -- fail open
        pass
    return 0


def selftest():
    import tempfile
    ok = True
    with tempfile.TemporaryDirectory() as t:
        Path(t, "station.json").write_text('{"name": "x", "knobs": {"map": "M"}}')
        rc1 = run_stdin(json.dumps({"tool_name": "Bash", "session_id": "s", "tool_use_id": "c1",
                                    "tool_input": {"command": "python3 tools/map/find.py prior art"}}), t)
        rc2 = run_stdin("{not json", t)
        rc3 = run_stdin(json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}), t)
        lines = Path(t, ".usage", "log.jsonl").read_text().splitlines()
        if not (rc1 == rc2 == rc3 == 0 and len(lines) == 1 and json.loads(lines[0])["target"] == "tools/map/find.py"):
            ok = False
            print("FAIL bash + malformed: exit 0 and exactly one line", lines)
        Path(t, "station.json").write_text('{"name": "x", "knobs": {"map": "S"}}')
        run_stdin(json.dumps({"tool_name": "Skill", "tool_input": {"skill": "closeout"}}), t)
        if len(Path(t, ".usage", "log.jsonl").read_text().splitlines()) != 1:
            ok = False
            print("FAIL knob S logs nothing")
    print("selftest OK" if ok else "selftest FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    sys.exit(run_stdin(sys.stdin.read(), C.ROOT))
