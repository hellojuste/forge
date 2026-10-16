#!/usr/bin/env python3
"""forge_check.py -- the forge station's five refusals, as one check (station-only; stdlib only).

owner: governance/rules.d/station.json (R-forge-*) . registered: governance/checks.d/station.json (forge_gates)

Each gap skill on this station names a failing test; a test written only in prose is never run, so this file runs
all five against the records the skills and workflows write:

  trial      governance/STATION_LEDGER.md `## TRIALS` table: every TRIAL-forge-nnnn row has N >= 5 frozen tasks,
             verdict promote|park, a 64-hex tasks_sha256, a non-empty failed-benchmark read, and an existing
             work/trials/<tool>.md report.                         (skill tool-trial: "a verdict with N < 5 is refused")
  holdout    every work/optimize/*.md report carries `holdout_sha256: <64 hex>` and `holdout_frozen_at:`; a report that
             claims `gain_status: out-of-sample` also carries `holdout_score:`.
                                                    (skill evo-guard: "a run report without a holdout hash is refused")
  telemetry  every registry/telemetry.json row with verified:true carries `verified_by_run` (the offline status
             command that was run and what it printed).    (skill telemetry-audit: "verified without a command")
  re_gate    every work/re/*.md report names `gate: RE-GATE-nnnn` that exists in work/re/legal_gate.json with
             decision proceed; a proceed row whose target is third-party proprietary needs a stated right.
                                                         (skill re-legal-gate: "a run without a gate row is refused")
  repin      every work/repin/*.md report with `licence_diff: changed` (or any STOP item) says `status: STOPPED` and
             `applied: no`.                      (skill kit-maintain: "a repin with a changed LICENSE blob stops")

Headline (station_audit grammar): "forge_gates: <n> violation(s) · <m> worklist · denominator <d>".
CLI: forge_check.py check [--root DIR] | forge_check.py --selftest
Exit: 0 clean . 1 violation . 2 unreadable input.
Earned by: KIT_PLAN 4 forge jobs (tool trial N >= 5, evo optimise with a frozen holdout, RE behind a legal gate,
repin with a report) and LEAN 'every numerator carries its denominator': lettuce shipped trial verdicts and
'found' optimiser gains with no denominator and no out-of-sample re-measure.
Release: none needed; a check never blocks a tool call. Fix the record (or the report), then re-run.
"""
import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

HEX64 = re.compile(r"^[0-9a-f]{64}$")
TRIAL_ID = re.compile(r"^TRIAL-forge-\d{4}$")
GATE_ID = re.compile(r"^RE-GATE-\d{4}$")
RIGHTS = {"own", "authorized", "open-source-licence", "interoperability-statute", "public-domain"}
PROPRIETARY = {"proprietary", "unknown", "closed", "eula"}


class Unreadable(Exception):
    pass


def _fields(text):
    out = {}
    for line in text.splitlines():
        m = re.match(r"^\s*(?:[-*]\s*)?([a-z_][a-z0-9_]*):\s*(.*?)\s*$", line)
        if m and m.group(1) not in out:
            out[m.group(1)] = m.group(2)
    return out


def _reports(root, sub):
    d = Path(root) / sub
    if not d.is_dir():
        return []
    return sorted(p for p in d.glob("*.md") if p.name.upper() != "README.MD")


# ------------------------------------------------------------------ trial
def trial_rows(text):
    """Rows of the `## TRIALS` markdown table: | id | date | tool | n | verdict | tasks_sha256 | failed_read | report |"""
    rows, on = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            on = line.strip().upper().startswith("## TRIALS")
            continue
        if not on or not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not cells or not TRIAL_ID.match(cells[0].strip("` ")):
            continue
        rows.append(cells)
    return rows


def check_trial(root, viol, work):
    p = Path(root) / "governance" / "STATION_LEDGER.md"
    if not p.exists():
        return 0
    rows = trial_rows(p.read_text(encoding="utf-8", errors="replace"))
    for c in rows:
        rid = c[0].strip("` ")
        if len(c) < 8:
            viol.append("trial %s: %d cell(s), need 8 (id|date|tool|n|verdict|tasks_sha256|failed_read|report)" % (rid, len(c)))
            continue
        _, _, tool, n, verdict, tsha, failed, report = [x.strip("` ") for x in c[:8]]
        try:
            nv = int(n)
        except ValueError:
            nv = -1
        if nv < 5:
            viol.append("trial %s (%s): N=%s < 5 -- a verdict on fewer than 5 frozen tasks is refused" % (rid, tool, n))
        if verdict.lower() not in ("promote", "park"):
            viol.append("trial %s (%s): verdict %r is not promote|park" % (rid, tool, verdict))
        if not HEX64.match(tsha.lower()):
            viol.append("trial %s (%s): tasks_sha256 %r is not 64 hex (tasks were not frozen before the runs)" % (rid, tool, tsha[:20]))
        if not failed or failed in ("-", "none"):
            viol.append("trial %s (%s): failed-benchmark read is empty (write the path read, or 'none published: <where looked>')" % (rid, tool))
        if not report or not (Path(root) / report).is_file():
            viol.append("trial %s (%s): report %r does not exist" % (rid, tool, report))
    for rp in _reports(root, "work/trials"):
        f = _fields(rp.read_text(encoding="utf-8", errors="replace"))
        if f.get("verdict") and f.get("verdict", "").lower() not in ("pending", ""):
            try:
                nt = int(f.get("n_tasks", "-1"))
            except ValueError:
                nt = -1
            if nt < 5:
                viol.append("%s: verdict %r with n_tasks=%s < 5 is refused" % (rp.relative_to(root), f["verdict"], f.get("n_tasks")))
        elif not f.get("verdict"):
            work.append("%s: no verdict yet" % rp.relative_to(root))
    return len(rows) + len(_reports(root, "work/trials"))


# ------------------------------------------------------------------ holdout
def check_holdout(root, viol, work):
    reps = _reports(root, "work/optimize")
    for rp in reps:
        rel = rp.relative_to(root)
        f = _fields(rp.read_text(encoding="utf-8", errors="replace"))
        h = f.get("holdout_sha256", "").strip("` ").lower()
        if not HEX64.match(h):
            viol.append("%s: no 64-hex holdout_sha256 -- an optimise report without a frozen holdout is refused" % rel)
        if not f.get("holdout_frozen_at"):
            viol.append("%s: no holdout_frozen_at (the holdout must be frozen BEFORE the first evo run)" % rel)
        gs = f.get("gain_status", "in-sample").lower()
        if gs == "out-of-sample" and not f.get("holdout_score"):
            viol.append("%s: gain_status out-of-sample without holdout_score (the gain is in-sample until re-measured)" % rel)
        elif gs != "out-of-sample":
            work.append("%s: gain still in-sample (no holdout re-measure yet)" % rel)
    return len(reps)


# ------------------------------------------------------------------ telemetry
def check_telemetry(root, viol, work):
    p = Path(root) / "registry" / "telemetry.json"
    if not p.exists():
        return 0
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as e:
        raise Unreadable("registry/telemetry.json: %s" % e)
    rows = doc if isinstance(doc, list) else (doc.get("rows") or doc.get("telemetry") or [])
    for r in rows:
        if not isinstance(r, dict):
            continue
        if r.get("verified") is True and not (r.get("verified_by_run") or "").strip():
            viol.append("telemetry %s: verified:true without verified_by_run (the offline status command and its output)"
                        % (r.get("tool") or r.get("repo")))
    return len(rows)


# ------------------------------------------------------------------ re_gate
def load_gates(root):
    p = Path(root) / "work" / "re" / "legal_gate.json"
    if not p.exists():
        return {}
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as e:
        raise Unreadable("work/re/legal_gate.json: %s" % e)
    return {r.get("id"): r for r in (doc.get("rows") or []) if isinstance(r, dict)}


def check_re_gate(root, viol, work):
    gates = load_gates(root)
    for gid, g in gates.items():
        if not GATE_ID.match(str(gid)):
            viol.append("legal_gate: id %r is not RE-GATE-nnnn" % gid)
        for k in ("target", "owner", "licence", "jurisdiction_note", "decision"):
            if not str(g.get(k) or "").strip():
                viol.append("legal_gate %s: missing %s" % (gid, k))
        third = str(g.get("owner", "")).lower() not in ("self", "operator", "own")
        prop = str(g.get("licence", "")).lower() in PROPRIETARY
        if g.get("decision") == "proceed" and third and prop and str(g.get("right", "")).lower() not in RIGHTS:
            viol.append("legal_gate %s: proceed on a third-party proprietary target without a stated right (%s)"
                        % (gid, "/".join(sorted(RIGHTS))))
    reps = _reports(root, "work/re")
    for rp in reps:
        rel = rp.relative_to(root)
        f = _fields(rp.read_text(encoding="utf-8", errors="replace"))
        gid = f.get("gate", "").strip("` ")
        if not gid:
            viol.append("%s: no `gate: RE-GATE-nnnn` line -- a reverse-engineering run without a gate row is refused" % rel)
        elif gid not in gates:
            viol.append("%s: gate %s is not in work/re/legal_gate.json" % (rel, gid))
        elif gates[gid].get("decision") != "proceed":
            viol.append("%s: gate %s decision is %r, not proceed" % (rel, gid, gates[gid].get("decision")))
    return len(reps) + len(gates)


# ------------------------------------------------------------------ repin
def check_repin(root, viol, work):
    reps = _reports(root, "work/repin")
    for rp in reps:
        rel = rp.relative_to(root)
        f = _fields(rp.read_text(encoding="utf-8", errors="replace"))
        stop = f.get("licence_diff", "").lower() == "changed" or f.get("stop_items", "0").strip() not in ("0", "", "none")
        if stop:
            if f.get("status", "").upper() != "STOPPED":
                viol.append("%s: a STOP item (licence_diff=%s, stop_items=%s) but status is %r, not STOPPED"
                            % (rel, f.get("licence_diff"), f.get("stop_items"), f.get("status")))
            if f.get("applied", "no").lower() != "no":
                viol.append("%s: a repin with a STOP item was applied" % rel)
        elif not f.get("status"):
            work.append("%s: no status line" % rel)
    return len(reps)


CHECKS = [check_trial, check_holdout, check_telemetry, check_re_gate, check_repin]


def run(root):
    viol, work, den = [], [], 0
    for fn in CHECKS:
        den += fn(root, viol, work)
    return viol, work, den


def cmd_check(root):
    try:
        viol, work, den = run(root)
    except Unreadable as e:
        print("forge_gates: UNREADABLE (%s)" % e)
        return 2
    print("forge_gates: %d violation(s) · %d worklist · denominator %d" % (len(viol), len(work), den))
    for v in viol:
        print("  VIOLATION " + v)
    for w in work:
        print("  WORKLIST " + w)
    return 1 if viol else 0


# ------------------------------------------------------------------ selftest
LEDGER_OK = """# STATION_LEDGER
## TRIALS
| id | date | tool | n | verdict | tasks_sha256 | failed_read | report |
|---|---|---|---|---|---|---|---|
| TRIAL-forge-0001 | 2026-10-16 | projectatlas | 6 | park | %s | docs/benchmarks/v0.4-agent-navigation-failed-mcp-approval-9ec0331.jsonl | work/trials/projectatlas.md |
""" % ("a" * 64)


def _plant(tmp, files):
    for rel, text in files.items():
        p = Path(tmp) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")


def selftest():
    good = {
        "governance/STATION_LEDGER.md": LEDGER_OK,
        "work/trials/projectatlas.md": "verdict: park\nn_tasks: 6\n",
        "work/optimize/latency.md": "holdout_sha256: %s\nholdout_frozen_at: 2026-10-16T10:00Z\ngain_status: in-sample\n" % ("b" * 64),
        "registry/telemetry.json": json.dumps({"telemetry": [{"tool": "evo", "verified": True,
                                                              "verified_by_run": "EVO_TELEMETRY=0 evo telemetry status -> telemetry: off (env)"}]}),
        "work/re/legal_gate.json": json.dumps({"rows": [{"id": "RE-GATE-0001", "target": "own CLI build", "owner": "self",
                                                        "licence": "MIT", "jurisdiction_note": "DISCLAIMER.md read", "decision": "proceed"}]}),
        "work/re/own-cli.md": "gate: RE-GATE-0001\n",
        "work/repin/evo.md": "licence_diff: changed\nstatus: STOPPED\napplied: no\n",
    }
    planted = [
        ("trial N<5", {"governance/STATION_LEDGER.md": LEDGER_OK.replace("| projectatlas | 6 |", "| projectatlas | 4 |")}),
        ("trial unfrozen tasks", {"governance/STATION_LEDGER.md": LEDGER_OK.replace("a" * 64, "TBD")}),
        ("trial report N<5", {"work/trials/projectatlas.md": "verdict: promote\nn_tasks: 3\n"}),
        ("optimize without holdout hash", {"work/optimize/latency.md": "holdout_frozen_at: 2026-10-16\ngain_status: in-sample\n"}),
        ("out-of-sample without score", {"work/optimize/latency.md": "holdout_sha256: %s\nholdout_frozen_at: x\ngain_status: out-of-sample\n" % ("b" * 64)}),
        ("telemetry verified without command", {"registry/telemetry.json": json.dumps({"telemetry": [{"tool": "evo", "verified": True}]})}),
        ("re run without gate row", {"work/re/own-cli.md": "findings only\n"}),
        ("re gate missing", {"work/re/own-cli.md": "gate: RE-GATE-0009\n"}),
        ("re third-party proprietary without right", {"work/re/legal_gate.json": json.dumps({"rows": [{"id": "RE-GATE-0001", "target": "vendor app", "owner": "Vendor Inc", "licence": "proprietary", "jurisdiction_note": "EU", "decision": "proceed"}]})}),
        ("repin licence changed but applied", {"work/repin/evo.md": "licence_diff: changed\nstatus: green\napplied: yes\n"}),
    ]
    fails = 0
    tmp = tempfile.mkdtemp(prefix="forge_check_")
    try:
        _plant(tmp, good)
        v, w, d = run(tmp)
        if v:
            print("selftest FAIL: clean fixture has violations: %s" % v)
            fails += 1
        else:
            print("selftest ok: clean fixture (denominator %d)" % d)
        for name, files in planted:
            t2 = tempfile.mkdtemp(prefix="forge_check_p_")
            try:
                _plant(t2, good)
                _plant(t2, files)
                v, w, d = run(t2)
                if v:
                    print("selftest ok: planted %-42s -> %d violation(s)" % (name, len(v)))
                else:
                    print("selftest FAIL: planted %s not caught" % name)
                    fails += 1
            finally:
                shutil.rmtree(t2, ignore_errors=True)
        t3 = tempfile.mkdtemp(prefix="forge_check_u_")
        try:
            _plant(t3, {"registry/telemetry.json": "{not json"})
            try:
                run(t3)
                print("selftest FAIL: unreadable telemetry.json not reported")
                fails += 1
            except Unreadable:
                print("selftest ok: unreadable input -> UNREADABLE (exit 2)")
        finally:
            shutil.rmtree(t3, ignore_errors=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("selftest: %s (%d planted defect(s) + clean + unreadable)" % ("PASS" if not fails else "FAIL", len(planted)))
    return 1 if fails else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="forge station refusals (tool-trial, evo-guard, telemetry-audit, re-legal-gate, kit-maintain)")
    ap.add_argument("cmd", nargs="?", choices=["check"])
    ap.add_argument("--root", default=".")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.cmd == "check":
        return cmd_check(Path(a.root).resolve())
    ap.print_usage()
    return 2


if __name__ == "__main__":
    sys.exit(main())
