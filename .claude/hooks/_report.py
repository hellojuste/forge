#!/usr/bin/env python3
"""_report.py -- the one report channel for every hook (LEAN CA-05, LL-13). stdlib only.

owner: governance/rules.json R-hook-libs
Plain stdout with exit 0 reaches the model only on SessionStart and UserPromptSubmit. On PreToolUse,
PostToolUse, Stop and SubagentStop it goes to the debug log -- "nothing is silent" was false for every
WARN in lettuce (L335). So a hook never prints a report itself; it calls

    report(event, text, audience="model"|"human", payload=None, key=None, root=None) -> str

which prints ONE line in the shape that event delivers and returns it ("" when deduplicated):
  SessionStart / UserPromptSubmit      plain text (delivered to the model as context)
  PreToolUse / PostToolUse, model      {"hookSpecificOutput": {"hookEventName", "additionalContext"}}
  Stop / SubagentStop, model           {"decision": "block", "reason": text}   (the only Stop shape the
                                       harness feeds back to the model; callers guard stop_hook_active)
  any event, human                     {"systemMessage": text}
Each (event, key or text) is said once per session: state in .cache/hooks/report_<session>.json.
render() builds the same string without printing or deduplicating (for hooks that combine lines).
Earned by: lettuce LEDGER L335 -- 11 reporters repeated one text on more than half their runs while
their WARNs went to the debug log.
"""
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

PLAIN_EVENTS = {"SessionStart", "UserPromptSubmit"}
CONTEXT_EVENTS = {"PreToolUse", "PostToolUse", "PostToolUseFailure", "Notification", "SubagentStart"}
STOP_EVENTS = {"Stop", "SubagentStop"}


def render(event, text, audience="model"):
    text = str(text).strip()
    if audience == "human":
        return json.dumps({"systemMessage": text}, ensure_ascii=False)
    if event in PLAIN_EVENTS:
        return text
    if event in STOP_EVENTS:
        return json.dumps({"decision": "block", "reason": text}, ensure_ascii=False)
    return json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}},
                      ensure_ascii=False)


def _root(root):
    if root:
        return Path(root)
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())


def _seen_path(root, session):
    s = re.sub(r"[^A-Za-z0-9_.-]", "_", session or "nosession")[:80]
    return _root(root) / ".cache" / "hooks" / ("report_%s.json" % s)


def once(event, key, payload=None, root=None):
    """True the first time (event, key) is seen in this session; records it."""
    session = (payload or {}).get("session_id") or "nosession"
    p = _seen_path(root, session)
    h = hashlib.sha256(("%s\0%s" % (event, key)).encode("utf-8")).hexdigest()[:16]
    try:
        seen = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
    except (OSError, ValueError):
        seen = []
    if h in seen:
        return False
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(seen + [h]), encoding="utf-8")
    except OSError:
        pass  # cannot record: say it (fail open toward speaking)
    return True


def report(event, text, audience="model", payload=None, key=None, root=None, dedup=True):
    if not str(text).strip():
        return ""
    if dedup and not once(event, key or text, payload, root):
        return ""
    out = render(event, text, audience)
    try:
        sys.stdout.write(out + "\n")
        sys.stdout.flush()
    except Exception:
        pass
    return out


def selftest():
    import contextlib
    import io
    fails, n = [], 0

    def ok(c, m):
        nonlocal n
        n += 1
        if not c:
            fails.append(m)

    ok(render("UserPromptSubmit", "x") == "x", "plain on UserPromptSubmit")
    j = json.loads(render("PostToolUse", "ctx"))
    ok(j["hookSpecificOutput"]["additionalContext"] == "ctx" and j["hookSpecificOutput"]["hookEventName"] == "PostToolUse",
       "PostToolUse additionalContext")
    ok(json.loads(render("Stop", "s"))["decision"] == "block", "Stop model -> decision block")
    ok(json.loads(render("PreToolUse", "h", "human")) == {"systemMessage": "h"}, "human -> systemMessage")
    with tempfile.TemporaryDirectory() as td:
        pl = {"session_id": "s1"}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            a = report("PostToolUse", "same", payload=pl, root=td)
            b = report("PostToolUse", "same", payload=pl, root=td)
            c = report("PostToolUse", "same", payload={"session_id": "s2"}, root=td)
            d = report("PostToolUse", "", payload=pl, root=td)
        ok(a and not b and c and not d, "once per session per finding: %r %r %r %r" % (a, b, c, d))
        ok(buf.getvalue().count("\n") == 2, "exactly two lines printed: %r" % buf.getvalue())
        for line in buf.getvalue().splitlines():
            ok("hookSpecificOutput" in json.loads(line), "report line is JSON")
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
    if len(sys.argv) >= 3:
        report(sys.argv[1], " ".join(sys.argv[2:]), dedup=False)
