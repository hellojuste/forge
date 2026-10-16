#!/usr/bin/env python3
"""act_gate.py — station hook MODULE (run in-process by station_dispatch.py): irreversible acts ASK, never deny.

Earned by: LEAN LL-18 (anything that touches real money or a live process is a deliberate act; lettuce's bridge rule
"costs a POSITION") and ORDER 4 (a) (verbatim: "copy it with a startup note to study it intently and understand how it
works, not discard it"): AutoHedge's `tools/ultra_tools.py` signs Jupiter swaps with SOLANA_PRIVATE_KEY, so the study
lane is disarmed by default and an armed run is asked, not silently allowed. Sending mail, finalising an invoice and
submitting a job application are the same class: they leave the machine and cannot be taken back.

API: check(event, payload, station) -> None | {"decision": "ask", "reason": str}
  * Bash command text or an MCP tool name matching a station.json `irreversible_acts` regex (strings or
    {"pattern", "why"} rows) or a built-in: execute_trade, ultra_tools, mcp__.*gmail.*send, mcp__.*__send_.*,
    SendEmailTool, lago .*finali[sz]e, career-ops .*apply.
  * AutoHedge patterns (execute_trade, ultra_tools, `-m autohedge` / `import autohedge`) ask ONLY when the command
    RUNS something (a runner — python, uv, node, bash ... — at command position of a segment, after `VAR=` prefixes,
    `sudo`/`env`) AND a live key is armed. Live keys = station.json `live_keys` (default commons/defaults.json:
    SOLANA_PRIVATE_KEY). Armed = NON-EMPTY in the station `.env` or a study-lane `study/*/.env` (the file is read),
    in this process's environment (an exported key: autohedge/env_loader.py loads with override=False, so the shell
    wins), or set inline in the command (`KEY=... python3 ...`, `export KEY=...`). The value is never printed.
    Reading or grepping the signing code is study, not a run, and never asks (REPRODUCE F5, SAFETY 3 and 4).
Release: the operator answers the ask; a governance/RELEASES.json row with scope `act_gate:<pattern>` (verbatim
`words` + `locator`) turns that pattern into allow.
Never denies (ORDER 5: the operator places things himself); an exception inside a module is reported by the dispatcher.
Run as a script: `--selftest`, or a PreToolUse payload on stdin -> hookSpecificOutput JSON.
"""
import json
import os
import re
import sys
from pathlib import Path

BUILTIN = [
    (r"\bexecute_trade\b", "AutoHedge execute_trade signs and sends a Jupiter swap (real funds)", "solana"),
    (r"\bultra_tools\b", "AutoHedge tools/ultra_tools.py reads SOLANA_PRIVATE_KEY and signs swaps", "solana"),
    (r"(?:-m\s+|\bimport\s+|\bfrom\s+)autohedge\b", "runs the AutoHedge package, whose trade path signs with the live key", "solana"),
    (r"mcp__.*gmail.*send", "sends an email from the operator's account", None),
    (r"mcp__.*__send_.*", "an MCP send_* act leaves the machine", None),
    (r"\bSendEmailTool\b", "sends an email", None),
    (r"\blago\b.*\bfinali[sz]e", "finalising a Lago invoice is irreversible", None),
    (r"\bcareer-ops\b.*\bapply", "submits a job application in the operator's name", None),
]
KEY = "SOLANA_PRIVATE_KEY"
RUNNER = re.compile(r"(python3?|python3\.\d+|uv|uvx|poetry|pipenv|pdm|node|deno|bun|bash|sh|zsh|swarms|autohedge|pytest|ipython|jupyter)")
SEG_SPLIT = re.compile(r"\|\||&&|;|\||\n|\$\(|`|&(?!>)")
WRAPPERS = ("sudo", "env", "nohup", "time", "exec", "command", "xargs")


def _segments(cmd):
    """Quote-aware statements (_cmdscan.segments: `python3 -c "a; b"` stays one segment); regex split as a fallback."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import _cmdscan
        return _cmdscan.segments(cmd or "")
    except Exception:
        return SEG_SPLIT.split(cmd or "")


def live_keys(station):
    return [k for k in (station.get("live_keys") or [KEY]) if k]


def runs_code(cmd):
    """True when some segment's command word is a runner (python, uv, node, bash, ...), after VAR= prefixes and wrappers."""
    for seg in _segments(cmd):
        toks = seg.strip().split()
        while toks and (re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=\S*", toks[0]) or toks[0] in WRAPPERS or toks[0] == "export"):
            if toks[0] == "export":
                toks = []
                break
            toks = toks[1:]
        if toks and RUNNER.fullmatch(os.path.basename(toks[0].strip("'\"("))):
            return True
    return False


def inline_armed(cmd, keys):
    """Keys set to a non-empty value inside the command text itself (`KEY=v cmd`, `export KEY=v`)."""
    return [k for k in keys if re.search(r"(?<![\w])%s=(?!['\"]?(?:\s|$|['\"]))\S" % re.escape(k), cmd or "")]


def root_of(payload, station):
    return Path(station.get("_root") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())


def _env_value_nonempty(path, name):
    try:
        for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"^\s*(?:export\s+)?%s\s*=\s*(.*)$" % re.escape(name), line)
            if m:
                v = m.group(1).split(" #", 1)[0].strip().strip("'\"")
                if v:
                    return True
    except OSError:
        pass
    return False


def armed(root, keys=(KEY,), environ=None):
    """Where a live key is non-empty: .env paths and "process environment (<KEY>)" — names only, never values."""
    root = Path(root)
    environ = os.environ if environ is None else environ
    cands = [root / ".env"] + sorted((root / "study").glob("*/.env")) if (root / "study").is_dir() else [root / ".env"]
    out = [str(p.relative_to(root)) for p in cands if p.is_file() and any(_env_value_nonempty(p, k) for k in keys)]
    out += ["process environment (%s)" % k for k in keys if (environ.get(k) or "").strip()]
    return out


def patterns(station):
    out = []
    for p in station.get("irreversible_acts") or []:
        if isinstance(p, dict):
            out.append((p.get("pattern", ""), p.get("why", "station.json irreversible_acts"), p.get("needs")))
        else:
            out.append((str(p), "station.json irreversible_acts", None))
    return out + BUILTIN


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


def subject(payload):
    tool = payload.get("tool_name", "")
    ti = payload.get("tool_input") or {}
    if tool == "Bash":
        return ti.get("command", "")
    if tool.startswith("mcp__") or tool in ("SendEmailTool",):
        return tool + " " + json.dumps(ti, sort_keys=True)[:400]
    return ""


def check(event, payload, station):
    if event != "PreToolUse":
        return None
    station = station or {}
    text = subject(payload)
    if not text:
        return None
    root = root_of(payload, station)
    for pat, why, needs in patterns(station):
        if not pat:
            continue
        try:
            hit = re.search(pat, text)
        except re.error:
            continue
        if not hit:
            continue
        if needs in ("solana", "live_key"):
            if payload.get("tool_name") == "Bash" and not runs_code(text):
                continue  # reading or grepping the signing code is study, not a run
            keys = live_keys(station)
            where = armed(root, keys, station.get("_environ"))
            where += ["inline in the command (%s)" % k for k in inline_armed(text, keys)]
            if not where:
                continue
            why = "%s; a live key is NON-EMPTY in %s" % (why, ", ".join(where))
        if released(root, "act_gate:" + pat, text):
            return None
        return {"decision": "ask",
                "reason": "ACT-GATE: irreversible act (%s) matched /%s/ — confirm to proceed; release: a RELEASES.json row "
                          "scope act_gate:%s quoting the operator" % (why, pat, pat)}
    return None


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
        root = Path(t)
        (root / "study/T~A").mkdir(parents=True)
        (root / "study/T~A/.env").write_text("JUPITER_API_KEY=\nSOLANA_PRIVATE_KEY=\n")
        st = {"name": "markets", "_root": str(root), "irreversible_acts": [r"\bbroker\.place_order\b"]}

        def c(tool, **ti):
            return check("PreToolUse", {"tool_name": tool, "tool_input": ti, "cwd": t}, st)

        st["_environ"] = {}
        assert c("Bash", command="cd study/T~A && python -c 'from tools.ultra_tools import execute_trade'") is None, "disarmed: no ask"
        cases += 1
        # REPRODUCE F5 / SAFETY 4: a key in the process environment or inline in the command arms the gate
        st["_environ"] = {"SOLANA_PRIVATE_KEY": "abc"}
        r = c("Bash", command="python3 -c 'from autohedge.tools.ultra_tools import execute_trade; execute_trade(1,2)'")
        assert r and r["decision"] == "ask" and "process environment" in r["reason"] and "abc" not in r["reason"], r
        assert c("Bash", command="python3 -m autohedge.main")["decision"] == "ask", "package run with an exported key"
        st["_environ"] = {}
        r = c("Bash", command="SOLANA_PRIVATE_KEY=5abc python3 -c \"from autohedge.tools.ultra_tools import execute_trade; execute_trade(1,2)\"")
        assert r and r["decision"] == "ask" and "inline" in r["reason"] and "5abc" not in r["reason"], r
        assert c("Bash", command="export SOLANA_PRIVATE_KEY=5abc; python3 study/T~A/autohedge/main.py --ultra_tools")["decision"] == "ask"
        assert c("Bash", command="SOLANA_PRIVATE_KEY= python3 -c 'import ultra_tools'") is None, "empty inline value is disarmed"
        st2 = dict(st, live_keys=["WALLET_PRIVATE_KEY"], _environ={"WALLET_PRIVATE_KEY": "x"})
        assert check("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": "uv run python -c 'import ultra_tools'"}}, st2)["decision"] == "ask", "configured live key"
        # SAFETY 3: reads of the real held path never ask, even armed
        st["_environ"] = {"SOLANA_PRIVATE_KEY": "abc"}
        for rd in ("grep -n execute_trade study/The-Swarm-Corporation~AutoHedge/autohedge/tools/ultra_tools.py",
                   "cat study/The-Swarm-Corporation~AutoHedge/autohedge/tools/ultra_tools.py | head -40",
                   "rg -n 'import autohedge' study/", "sed -n 1,80p study/The-Swarm-Corporation~AutoHedge/autohedge/main.py"):
            assert c("Bash", command=rd) is None, rd
        st["_environ"] = {}
        cases += 10
        (root / "study/T~A/.env").write_text("SOLANA_PRIVATE_KEY=  5abcSECRETvalue  # funded\n")
        r = c("Bash", command="python3 -c 'import ultra_tools; ultra_tools.execute_trade()'")
        assert r and r["decision"] == "ask" and "5abcSECRETvalue" not in r["reason"] and "study/T~A/.env" in r["reason"], r
        cases += 1
        assert c("Bash", command="grep -n execute_trade study/T~A/tools/ultra_tools.py") is None, "armed: reading the code is study, no ask"
        assert c("Bash", command="cd study/T~A && uv run main.py --ultra_tools")["decision"] == "ask", "armed run asks"
        cases += 1
        assert c("mcp__claude_ai_Gmail__send_email", to="x")["decision"] == "ask"
        assert c("mcp__lago__send_invoice")["decision"] == "ask"
        assert c("Bash", command="lago invoices finalize inv_1")["decision"] == "ask"
        assert c("Bash", command="node career-ops.mjs apply --id 3")["decision"] == "ask"
        assert c("Bash", command="python3 bot.py broker.place_order(1)")["decision"] == "ask", "station pattern"
        assert c("Bash", command="ls -la") is None
        assert c("Read", file_path="study/T~A/tools/ultra_tools.py") is None, "reads never ask"
        assert c("mcp__github__get_file_contents", path="x") is None
        cases += 9
        assert all(r.get("decision") != "deny" for r in [c("Bash", command="execute_trade")] if r), "never deny"
        _commit_releases(root, [{"id": "REL-0002", "scope": r"act_gate:\blago\b.*\bfinali[sz]e", "words": "finalize is fine",
                                 "locator": "fixture", "utc": "2026-10-16T00:00Z", "expires": "2999-01-01T00:00Z"}])
        assert c("Bash", command="lago invoices finalize inv_1") is None, "release row turns the ask into allow"
        assert c("Bash", command="node career-ops.mjs apply --id 3")["decision"] == "ask", "release is per pattern"
        cases += 2
    print("act_gate selftest OK (%d cases)" % cases)
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
