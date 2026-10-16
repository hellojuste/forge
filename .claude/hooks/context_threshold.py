#!/usr/bin/env python3
"""context_threshold.py -- the handoff reminder (GOV 3.15). REPORT only: never denies, never seals.

owner: governance/rules.json R-context
Measures the last assistant `usage` row in the transcript tail (last 2 MB): input_tokens +
cache_read_input_tokens + cache_creation_input_tokens. Thresholds come from the effective gov config
(commons/defaults.json, overridden by station.json): ctx_warn, ctx_handoff, ctx_repeat.
  >= ctx_warn                     CONTEXT <n>k >= <warn>k: reach a durable point; ...
  >= ctx_handoff, every ctx_repeat HANDOFF <n>k >= <handoff>k: commit by path, write the handoff ...
Each crossing is said ONCE per session (state .cache/hooks/ctx_<session>.json).
Subagent guard: silent when the transcript's file stem is not the payload's session_id, or when the
payload carries agent_id / agent_type.
Channels: in-process `line(payload)` for the router (UserPromptSubmit, plain stdout); as a script on
PostToolUse it emits additionalContext through _report.
Earned by: lettuce sealed every session at the line and reverted it the same week (three human-driven
sessions locked mid-task); a subagent was told "HANDOFF 467k" on its first tool call.
"""
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
TAIL = 2 * 1024 * 1024


def _gov(root):
    g = {"ctx_warn": 150000, "ctx_handoff": 200000, "ctx_repeat": 50000}
    for rel in ("commons/defaults.json", "station.json"):
        try:
            g.update({k: v for k, v in (json.loads((Path(root) / rel).read_text(encoding="utf-8")).get("gov") or {}).items()
                      if k in g})
        except (OSError, ValueError):
            pass
    return g


def measure(transcript_path):
    """Context tokens of the last assistant usage row, or None."""
    try:
        with open(transcript_path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - TAIL))
            tail = f.read().decode("utf-8", "replace")
    except OSError:
        return None
    for line in reversed(tail.splitlines()):
        if '"usage"' not in line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        msg = row.get("message") if isinstance(row.get("message"), dict) else row
        u = (msg or {}).get("usage")
        if isinstance(u, dict):
            return int(u.get("input_tokens", 0) or 0) + int(u.get("cache_read_input_tokens", 0) or 0) \
                + int(u.get("cache_creation_input_tokens", 0) or 0)
    return None


def line(payload, root=None):
    """The one reminder line due now, or "" (already said, below threshold, subagent, no transcript)."""
    try:
        root = Path(root or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
        if payload.get("agent_id") or payload.get("agent_type"):
            return ""
        tp, sid = payload.get("transcript_path") or "", payload.get("session_id") or ""
        if not tp or not sid or Path(tp).stem != sid:
            return ""
        n = measure(tp)
        if n is None:
            return ""
        g = _gov(root)
        warn, hand, rep = int(g["ctx_warn"]), int(g["ctx_handoff"]), max(1, int(g["ctx_repeat"]))
        if n >= hand:
            key = "handoff:%d" % ((n - hand) // rep)
            text = ("HANDOFF %dk ≥ %dk: commit by path, write the handoff (header + NEXT quoting every human order "
                    "since your last checkpoint verbatim), start the successor on the SAME branch, then end." % (n // 1000, hand // 1000))
        elif n >= warn:
            key = "warn"
            text = "CONTEXT %dk ≥ %dk: reach a durable point; write a checkpoint at the next boundary." % (n // 1000, warn // 1000)
        else:
            return ""
        sp = root / ".cache" / "hooks" / ("ctx_%s.json" % re.sub(r"[^A-Za-z0-9_.-]", "_", sid)[:80])
        try:
            said = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else []
        except (OSError, ValueError):
            said = []
        if key in said:
            return ""
        try:
            sp.parent.mkdir(parents=True, exist_ok=True)
            sp.write_text(json.dumps(said + [key]), encoding="utf-8")
        except OSError:
            pass
        return text
    except Exception:
        return ""


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    t = line(payload, root)
    if t:
        import _report
        _report.report(payload.get("hook_event_name") or "PostToolUse", t, payload=payload, root=root, dedup=False)
    return 0


def selftest():
    import subprocess
    import tempfile
    fails, n = [], 0

    def ok(c, m):
        nonlocal n
        n += 1
        if not c:
            fails.append(m)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "commons").mkdir()
        (root / "commons" / "defaults.json").write_text(json.dumps({"gov": {"ctx_warn": 1000, "ctx_handoff": 2000, "ctx_repeat": 500}}))
        tp = root / "sess1.jsonl"

        def at(tokens):
            tp.write_text("\n".join([json.dumps({"type": "user", "message": {"content": "x"}}),
                                     json.dumps({"type": "assistant", "message": {"usage": {
                                         "input_tokens": tokens - 300, "cache_read_input_tokens": 200,
                                         "cache_creation_input_tokens": 100}}})]) + "\n")

        pl = {"session_id": "sess1", "transcript_path": str(tp)}
        at(999)
        ok(line(pl, root) == "", "warn-1 silent")
        at(1000)
        ok(line(pl, root).startswith("CONTEXT 1k"), "warn fires")
        ok(line(pl, root) == "", "second call at the same level silent")
        at(2100)
        ok(line(pl, root).startswith("HANDOFF 2k"), "handoff fires")
        at(2400)
        ok(line(pl, root) == "", "handoff + < repeat silent")
        at(2500)
        ok(line(pl, root).startswith("HANDOFF 2k"), "handoff + repeat fires again")
        ok(line(dict(pl, session_id="other"), root) == "", "stem != session_id silent (subagent guard)")
        ok(line(dict(pl, agent_id="a1"), root) == "", "agent_id silent")
        ok(line({"session_id": "x", "transcript_path": str(root / "x.jsonl")}, root) == "", "missing transcript silent")
        # script on PostToolUse: additionalContext JSON, exit 0
        tp2 = root / "sess2.jsonl"
        tp2.write_text(json.dumps({"message": {"usage": {"input_tokens": 1500}}}) + "\n")
        p = subprocess.run([sys.executable, str(Path(__file__).resolve())], cwd=td, capture_output=True, text=True,
                           input=json.dumps({"session_id": "sess2", "transcript_path": str(tp2), "hook_event_name": "PostToolUse"}),
                           env=dict(os.environ, CLAUDE_PROJECT_DIR=td))
        j = json.loads(p.stdout) if p.stdout.strip() else {}
        ok(p.returncode == 0 and "CONTEXT" in j.get("hookSpecificOutput", {}).get("additionalContext", ""),
           "PostToolUse emits additionalContext: %r" % p.stdout)
        p = subprocess.run([sys.executable, str(Path(__file__).resolve())], cwd=td, capture_output=True, text=True,
                           input="{}", env=dict(os.environ, CLAUDE_PROJECT_DIR=td))
        ok(p.returncode == 0 and p.stdout == "", "empty payload: nothing, exit 0")
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
