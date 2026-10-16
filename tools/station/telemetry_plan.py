#!/usr/bin/env python3
"""telemetry_plan.py -- for every registry/telemetry.json row, the exact offline commands that make it verifiable.

owner: .claude/skills/telemetry-audit/SKILL.md . station forge (station-only; stdlib only)

The kit rule is "never start a tool whose registry/telemetry.json row is verified:false". A row can only flip with
the operator's own offline status run (J2 GA6), and until now no file said WHICH run: CRITIC F11 found the
self-hosted stacks (Plane, trigger.dev, Lago) and the forge CLIs dead-ended on a rule nobody could satisfy.
This tool prints, per row: the opt-out env it would run under, the bootstrap + run-tree commands (the tool never
runs inside a station), the offline status command (station table below, or `unread` with the file to read
first), and the flip: the exact registry fields to write ON MAIN (registry/ is commons; a station never edits it).

  show <tool|owner/repo>  one row (exit 0 known · 1 no such row)
  all                     every row, then `telemetry_plan: <n> rows · <v> verified · <s> with a status command`
  gate <tool|owner/repo>  exit 0 only if the row is verified:true WITH verified_by_run (a workflow's start gate)
  --selftest
Earned by: CRITIC F11 (telemetry verify path missing; venture services can never start) and SAFETY 8 (registry
lags the opt-out evidence forge already cites).
Release: none needed; it reads only. A wrong status command is fixed in STATUS below with its evidence.
"""
import argparse
import json
import sys
import tempfile
from pathlib import Path

# Offline status runs whose command is evidenced at the pin. Each value: (status command, evidence, flag/env notes).
# A tool missing here prints `unread` and the evidence file to read first (skill telemetry-audit step 2).
STATUS = {
    "evo-hq/evo": ("EVO_TELEMETRY=0 evo telemetry status",
                   "plugins/evo/src/evo/telemetry.py:102-112 (EVO_TELEMETRY in 0/false/off/no, or DO_NOT_TRACK in "
                   "1/true/yes; gate at 120-121); never `evo telemetry off` (cli.py:615-623 sends a final event)"),
    "langchain-ai/openwiki": ("openwiki init --telemetry-file ow-telemetry.json   (expect {\"disabled\": true, \"sent\": false} in the file; "
                              "without a model key: node -e the installed dist/telemetry/senders.js recordRun, see work/telemetry/setup-findings.md)",
                              "src/telemetry/gates.ts:28-32 (truthy OPENWIKI_TELEMETRY_DISABLED or DO_NOT_TRACK skips "
                              "the send, senders.ts:136); record that no request leaves the run (offline: no network)"),
    "styler-ai/ProjectAtlas": ("PROJECTATLAS_NO_TELEMETRY=1 projectatlas runtime-info   (setup_tool.py's kit-bin/projectatlas sets it)",
                               "crates/projectatlas-db/src/telemetry.rs:1 + core/src/telemetry.rs:1 (local token accounting in "
                               "the project DB; no HTTP crate in the default build: `cargo tree -p projectatlas-cli -e normal` "
                               "-> 0 of ureq/reqwest/hyper); PROJECTATLAS_NO_TELEMETRY 1/true/yes/on skips the local writes "
                               "(crates/projectatlas-cli/src/runtime.rs:3608-3610, main.rs:4034-4040)"),
    "triggerdotdev/trigger.dev": ("npx trigger.dev@<pinned> --skip-telemetry whoami",
                                  "packages/cli-v3/src/mcp/telemetry.ts:18 (enabled only when the variable is "
                                  "undefined) -- the pinned version comes from the bootstrap tree's package.json"),
    "getmaxun/maxun": ("node -e \"process.exit(process.env.MAXUN_TELEMETRY==='true')\"",
                       "server/src/utils/analytics.ts:37 (sends only when MAXUN_TELEMETRY === 'true'); quarantined: "
                       "the gate row stays false, never started by a workflow"),
}


def load_rows(root):
    p = Path(root) / "registry" / "telemetry.json"
    if not p.exists():
        return []
    doc = json.loads(p.read_text(encoding="utf-8"))
    rows = doc if isinstance(doc, list) else (doc.get("telemetry") or doc.get("rows") or [])
    return [r for r in rows if isinstance(r, dict)]


def find(rows, key):
    k = key.lower()
    for r in rows:
        if k in (str(r.get("tool", "")).lower(), str(r.get("repo", "")).lower(),
                 str(r.get("repo", "")).lower().split("/")[-1], str(r.get("repo", "")).lower().replace("/", "~")):
            return r
    return None


def plan(r):
    repo = str(r.get("repo", ""))
    key = repo.replace("/", "~")
    env = " ".join("%s=%s" % kv for kv in sorted((r.get("opt_out_candidate_env") or {}).items()))
    st = STATUS.get(repo)
    lines = [
        "%s (%s) · station %s · verified: %s" % (r.get("tool"), repo, r.get("station"), str(bool(r.get("verified"))).lower()),
        "  opt-out env : %s" % (env or "none known (opt_out: %s)" % r.get("opt_out", "unread")),
        "  bootstrap   : python3 tools/kit/bootstrap.py %s" % key,
        "  run-tree    : python3 tools/kit/runtree.py %s --station %s   (cd into the printed tree; never run it in the station)"
        % (key, r.get("station")),
    ]
    if st:
        lines.append("  status run  : %s%s" % (env + " " if env else "", st[0]))
        lines.append("  evidence    : %s" % st[1])
    else:
        lines.append("  status run  : unread -- read %s at the pin first (skill telemetry-audit step 2), then add it to "
                     "tools/station/telemetry_plan.py STATUS with its file:line" % (r.get("evidence") or "the sender"))
    lines.append("  flip (main) : registry/telemetry.json row %s -> \"verified\": true, \"verified_by_run\": \"<status run> "
                 "-> <its output, quoted>\" (forge_gates refuses verified:true without verified_by_run)" % repo)
    return lines, bool(st)


def cmd_show(root, key):
    r = find(load_rows(root), key)
    if not r:
        print("telemetry_plan: no registry/telemetry.json row for %r" % key)
        return 1
    print("\n".join(plan(r)[0]))
    return 0


def cmd_all(root):
    rows = load_rows(root)
    with_cmd = 0
    for r in rows:
        lines, has = plan(r)
        with_cmd += has
        print("\n".join(lines))
    v = sum(1 for r in rows if r.get("verified") is True)
    print("telemetry_plan: %d rows · %d verified · %d with a status command (python3 tools/station/telemetry_plan.py all)"
          % (len(rows), v, with_cmd))
    return 0


def cmd_gate(root, key):
    r = find(load_rows(root), key)
    if not r:
        print("telemetry gate %s: NO ROW -- refused" % key)
        return 1
    if r.get("verified") is True and str(r.get("verified_by_run") or "").strip():
        print("telemetry gate %s: verified by run -- may start (inside a run-tree)" % key)
        return 0
    print("telemetry gate %s: verified:false -- refused; make it verifiable with: python3 tools/station/telemetry_plan.py show %s"
          % (key, key))
    return 1


def selftest():
    import contextlib
    import io
    rows = {"telemetry": [
        {"tool": "evo", "repo": "evo-hq/evo", "station": "forge", "verified": False, "evidence": "telemetry.py",
         "opt_out_candidate_env": {"DO_NOT_TRACK": "1"}},
        {"tool": "lago", "repo": "getlago/lago", "station": "venture", "verified": False, "evidence": "README.md"},
        {"tool": "ok", "repo": "a/ok", "station": "forge", "verified": True, "verified_by_run": "ok status -> off"},
        {"tool": "half", "repo": "a/half", "station": "forge", "verified": True},
    ]}
    fails = 0
    with tempfile.TemporaryDirectory() as t:
        (Path(t) / "registry").mkdir()
        (Path(t) / "registry" / "telemetry.json").write_text(json.dumps(rows))
        cases = [
            ("show evo has a status run", lambda: cmd_show(t, "evo"), 0, "evo telemetry status"),
            ("show by owner~repo", lambda: cmd_show(t, "evo-hq~evo"), 0, "runtree.py evo-hq~evo"),
            ("show lago says unread", lambda: cmd_show(t, "lago"), 0, "status run  : unread"),
            ("show unknown", lambda: cmd_show(t, "nope"), 1, "no registry"),
            ("gate unverified refused", lambda: cmd_gate(t, "evo"), 1, "refused"),
            ("gate verified by run passes", lambda: cmd_gate(t, "ok"), 0, "may start"),
            ("gate verified without run refused", lambda: cmd_gate(t, "half"), 1, "refused"),
            ("all counts", lambda: cmd_all(t), 0, "4 rows · 2 verified · 1 with a status command"),
        ]
        for name, fn, want_rc, want_txt in cases:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = fn()
            if rc == want_rc and want_txt in buf.getvalue():
                print("selftest ok: %s" % name)
            else:
                print("selftest FAIL: %s (rc %s, out %r)" % (name, rc, buf.getvalue()[:200]))
                fails += 1
    print("telemetry_plan selftest %s (%d cases)" % ("OK" if not fails else "FAILED", len(cases)))
    return 1 if fails else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", nargs="?", choices=["show", "all", "gate"])
    ap.add_argument("key", nargs="?")
    ap.add_argument("--root", default=".")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    try:
        if a.cmd == "all":
            return cmd_all(a.root)
        if a.cmd in ("show", "gate") and a.key:
            return (cmd_show if a.cmd == "show" else cmd_gate)(a.root, a.key)
    except ValueError as e:
        print("telemetry_plan: UNREADABLE registry/telemetry.json (%s)" % e)
        return 2
    ap.print_usage()
    return 2


if __name__ == "__main__":
    sys.exit(main())
