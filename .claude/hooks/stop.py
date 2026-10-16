#!/usr/bin/env python3
"""stop.py -- Stop: the close-out line (GOV 3.17), plus brain's asides check in-process.

owner: governance/rules.json R-closeout (CLAUDE.md invariant 7)
Fires when the turn since the last REAL user entry ran a `git commit` at a command position (Bash tool_use
blocks in the transcript, parsed by _cmdscan) AND the last assistant text has no line matching
^[ \\t>*_\\-`]*closeout\\s*:  (GOV's pattern, spaces allowed in the
markdown decoration). It says, once per session, through _report:
  CLOSEOUT: this turn committed <sha7> and has no "closeout:" line — run /closeout or write "closeout: none (<why>)"
Channel: the first time per session it is {"decision": "block", "reason": ...} (the one Stop shape the harness
feeds back to the model, so the turn continues once); when stop_hook_active is true, or on a repeat, it is a
{"systemMessage": ...} for the human only. It never loops.
Plug-in: tools/brain.py stop_check(payload) -> str|None, imported by path when present; its text joins the
same line ("closeout: L-0012; asides: none" satisfies both). A plug-in exception is one report line.
Earned by: lettuce passes that committed and ended without the close-out ritual left their lessons unfiled;
the asides-line rule (G12.5) became a Stop check after it was skipped in prose.
"""
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _cmdscan  # noqa: E402

CLOSEOUT_RE = re.compile(r"^[ \t>*_\-`]*closeout\s*:", re.I | re.M)
SHA_RE = re.compile(r"\[[^\]\n]*?\b([0-9a-f]{7,40})\]")


def _rows(tp):
    try:
        with open(tp, encoding="utf-8", errors="replace") as f:
            data = f.read()[-4 * 1024 * 1024:]
    except OSError:
        return []
    out = []
    for line in data.splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _content(row):
    m = row.get("message") if isinstance(row.get("message"), dict) else {}
    c = m.get("content", row.get("content"))
    if isinstance(c, str):
        return [{"type": "text", "text": c}]
    return c if isinstance(c, list) else []


def _is_real_user(row):
    if row.get("type") != "user" or row.get("isMeta") or row.get("isSynthetic"):
        return False
    blocks = _content(row)
    if not blocks or any(b.get("type") == "tool_result" for b in blocks if isinstance(b, dict)):
        return False
    text = " ".join(b.get("text", "") for b in blocks if isinstance(b, dict))
    return not text.lstrip().startswith(("<task-notification>", "<system-reminder>", "<command-"))


def analyse(tp):
    """(commit_sha7 or None, last assistant text)."""
    rows = _rows(tp)
    start = 0
    for i, r in enumerate(rows):
        if _is_real_user(r):
            start = i
    commit_ids, sha, last_text = set(), None, ""
    for r in rows[start:]:
        for b in _content(r):
            if not isinstance(b, dict):
                continue
            if r.get("type") == "assistant" and b.get("type") == "tool_use" and b.get("name") == "Bash":
                cmd = (b.get("input") or {}).get("command", "")
                if any(sub == "commit" for _, sub, _ in _cmdscan.git_calls(cmd)):
                    commit_ids.add(b.get("id"))
            elif b.get("type") == "tool_result" and b.get("tool_use_id") in commit_ids:
                c = b.get("content")
                text = c if isinstance(c, str) else " ".join(x.get("text", "") for x in (c or []) if isinstance(x, dict))
                m = SHA_RE.search(text or "")
                if m:
                    sha = m.group(1)[:7]
            elif r.get("type") == "assistant" and b.get("type") == "text" and b.get("text", "").strip():
                last_text = b["text"]
    if not commit_ids:
        return None, last_text
    return (sha or "a commit"), last_text


def _brain(payload, root):
    bp = Path(root) / "tools" / "brain.py"
    if not bp.exists():
        return None
    try:
        spec = importlib.util.spec_from_file_location("brain_for_stop", str(bp))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m.stop_check(payload) if hasattr(m, "stop_check") else None
    except Exception as e:
        return "stop: brain.stop_check plug-in failed (%s)" % type(e).__name__


def respond(payload, root):
    """The JSON line to print, or ""."""
    import _report
    tp = payload.get("transcript_path") or ""
    sha, last = analyse(tp) if tp else (None, "")
    parts = []
    if sha and not CLOSEOUT_RE.search(last or ""):
        parts.append('CLOSEOUT: this turn committed %s and has no "closeout:" line — run /closeout or write '
                     '"closeout: none (<why>)"' % sha)
    b = _brain(payload, root)
    if b:
        parts.append(str(b).strip())
    if not parts:
        return ""
    text = " · ".join(parts)
    first = _report.once("Stop", "closeout-block", payload, root) and not payload.get("stop_hook_active")
    return _report.render("Stop", text, "model" if first else "human")


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    try:
        out = respond(payload, root)
    except Exception as e:
        import _report
        out = _report.render("Stop", "stop: internal error (%s); skipped" % e, "human")
    if out:
        print(out)
    return 0


def selftest():
    import tempfile
    fails, n = [], 0

    def ok(c, m):
        nonlocal n
        n += 1
        if not c:
            fails.append(m)

    def transcript(path, closing_text, commit=True, quoted=False):
        cmd = "echo 'git commit -m x'" if quoted else "git add a.py && git commit -m 'work'"
        rows = [
            {"type": "user", "message": {"role": "user", "content": "earlier ask"}},
            {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t0", "name": "Bash",
                                                           "input": {"command": "git commit -m old"}}]}},
            {"type": "user", "message": {"role": "user", "content": "please fix the parser and commit"}},
        ]
        if commit:
            rows += [
                {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}]}},
                {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1",
                                                          "content": "[main 1a2b3c4d] work\n 1 file changed"}]}},
            ]
        rows.append({"type": "assistant", "message": {"content": [{"type": "text", "text": closing_text}]}})
        Path(path).write_text("\n".join(json.dumps(r) for r in rows) + "\n")

    template = "Done.\n\ncloseout: none (one-line fix) · next: ship the parser"
    with tempfile.TemporaryDirectory() as td:
        tp = str(Path(td) / "s1.jsonl")
        transcript(tp, "Fixed and committed.")
        out = respond({"session_id": "s1", "transcript_path": tp}, td)
        j = json.loads(out) if out else {}
        ok(j.get("decision") == "block" and "CLOSEOUT: this turn committed 1a2b3c4" in j.get("reason", ""),
           "commit without line -> one JSON block report: %r" % out)
        out = respond({"session_id": "s1", "transcript_path": tp}, td)
        ok(out and "systemMessage" in json.loads(out), "repeat in the same session -> systemMessage only: %r" % out)
        out = respond({"session_id": "s2", "transcript_path": tp, "stop_hook_active": True}, td)
        ok(out and set(json.loads(out)) == {"systemMessage"}, "stop_hook_active -> systemMessage only: %r" % out)
        transcript(tp, template)
        ok(respond({"session_id": "s3", "transcript_path": tp}, td) == "", "the /closeout step-9 template line satisfies it")
        transcript(tp, "All good.\n> **closeout:** L-core-0003")
        ok(respond({"session_id": "s4", "transcript_path": tp}, td) == "", "decorated closeout line accepted")
        transcript(tp, "Just answered a question.", commit=False)
        ok(respond({"session_id": "s5", "transcript_path": tp}, td) == "", "no commit in this turn (old commit before the user entry ignored)")
        transcript(tp, "Explained.", quoted=True)
        ok(respond({"session_id": "s6", "transcript_path": tp}, td) == "", "quoted 'git commit' is not a commit")
        ok(respond({"session_id": "s7", "transcript_path": str(Path(td) / "missing.jsonl")}, td) == "", "missing transcript: nothing")
        # brain plug-in joins the same line
        (Path(td) / "tools").mkdir()
        (Path(td) / "tools" / "brain.py").write_text("def stop_check(p):\n    return 'ASIDES: no asides: line'\n")
        transcript(tp, "Fixed.")
        out = respond({"session_id": "s8", "transcript_path": tp}, td)
        ok("CLOSEOUT" in out and "ASIDES" in out, "brain plug-in joins: %r" % out)
        (Path(td) / "tools" / "brain.py").write_text("def stop_check(p):\n    raise ValueError('x')\n")
        transcript(tp, template)
        out = respond({"session_id": "s9", "transcript_path": tp}, td)
        ok("plug-in failed" in out, "plug-in exception is one report line: %r" % out)
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
