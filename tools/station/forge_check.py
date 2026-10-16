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

  noise      every work/trials/*.md with a verdict and every work/optimize/*.md claiming a gain carries
             `noise_floor: K=<k>` with K >= 5 and `spread:`; a `gain:` not larger than `spread:` cannot be promoted
             or called out-of-sample.
                                     (skill noise-floor: "a gain smaller than the run-to-run spread is not a gain")
  wiki       every work/wiki/<repo>/REVIEW.md names target, target_class and status; status generated needs a
             non-client target_class and the openwiki telemetry row verified:true.   (workflow wiki-gen)
  arch       every work/arch/*.md holds >= 2 `## Design` sections, a comparison table and a `pick:` line.
                                                       (skill design-it-twice, workflow arch-review)
  intake     every work/intake/*.md names repo, a 40-hex sha, licence, agent_files and decision; decision ingest
             needs an upstream/LOCK.json row with that repo and sha.                 (workflow intake-run)
  roster     every station workflow's DEFAULT_MODELS literal equals station.json gov.model_roster (one owner).

  output <kind> <path>  the certain test of a station workflow: the whole check above, PLUS the named deliverable
             exists, lies under its kind's folder and carries its kind's required fields.

Headline (station_audit grammar): "forge_gates: <n> violation(s) · <m> worklist · denominator <d>".
CLI: forge_check.py check [--root DIR] | forge_check.py output <kind> <path> [--root DIR] | forge_check.py --selftest
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
HEX40 = re.compile(r"^[0-9a-f]{40}$")
NOISE = re.compile(r"K\s*=\s*(\d+)")
NUM = re.compile(r"[-+]?\d+(?:\.\d+)?")
CLIENTISH = {"client", "customer", "third-party", "third-party-proprietary", "proprietary"}
OK_WIKI_CLASS = {"own", "open-source", "kit"}
INTAKE_DECISIONS = {"ingest", "bootstrap", "attic", "refuse"}
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


# ------------------------------------------------------------------ noise
def _num(v):
    m = NUM.search(v or "")
    return float(m.group(0)) if m else None


def _noise(rel, f, viol, claims):
    nf = f.get("noise_floor", "")
    m = NOISE.search(nf)
    if not m or int(m.group(1)) < 5:
        viol.append("%s: no `noise_floor: K=<k>` with K >= 5 -- a claimed result without the baseline spread is refused" % rel)
        return
    spread = _num(f.get("spread"))
    if spread is None:
        viol.append("%s: noise_floor without a numeric `spread:`" % rel)
        return
    gain = _num(f.get("gain"))
    if claims and gain is not None and abs(gain) <= spread:
        viol.append("%s: gain %s is not larger than the run-to-run spread %s (not a gain)" % (rel, gain, spread))


def check_noise(root, viol, work):
    n = 0
    for rp in _reports(root, "work/trials"):
        f = _fields(rp.read_text(encoding="utf-8", errors="replace"))
        if f.get("verdict", "").lower() in ("promote", "park"):
            n += 1
            _noise(rp.relative_to(root), f, viol, f.get("verdict", "").lower() == "promote")
    for rp in _reports(root, "work/optimize"):
        f = _fields(rp.read_text(encoding="utf-8", errors="replace"))
        if f.get("gain") or f.get("gain_status", "").lower() == "out-of-sample":
            n += 1
            _noise(rp.relative_to(root), f, viol, f.get("gain_status", "").lower() == "out-of-sample")
    return n


# ------------------------------------------------------------------ wiki
def _telemetry_rows(root):
    p = Path(root) / "registry" / "telemetry.json"
    if not p.exists():
        return []
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as e:
        raise Unreadable("registry/telemetry.json: %s" % e)
    rows = doc if isinstance(doc, list) else (doc.get("rows") or doc.get("telemetry") or [])
    return [r for r in rows if isinstance(r, dict)]


def wiki_reviews(root):
    d = Path(root) / "work" / "wiki"
    return sorted(d.glob("*/REVIEW.md")) if d.is_dir() else []


def check_wiki(root, viol, work):
    revs = wiki_reviews(root)
    ow = [r for r in _telemetry_rows(root) if "openwiki" in str(r.get("repo", "")) + str(r.get("tool", ""))]
    verified = bool(ow) and all(r.get("verified") is True for r in ow)
    for rp in revs:
        rel = rp.relative_to(root)
        f = _fields(rp.read_text(encoding="utf-8", errors="replace"))
        for k in ("target", "target_class", "status"):
            if not f.get(k):
                viol.append("%s: missing %s" % (rel, k))
        cls, st = f.get("target_class", "").lower(), f.get("status", "").lower()
        if st == "generated":
            if cls not in OK_WIKI_CLASS:
                viol.append("%s: generated a wiki for target_class %r (only %s; client repos are client-bi's)"
                            % (rel, cls, "/".join(sorted(OK_WIKI_CLASS))))
            if not verified:
                viol.append("%s: generated while the openwiki telemetry row is not verified:true (never start an unverified tool)" % rel)
        elif st.startswith("refused"):
            work.append("%s: %s" % (rel, st))
        elif st:
            viol.append("%s: status %r is not generated|refused-*" % (rel, st))
    return len(revs)


# ------------------------------------------------------------------ arch
def check_arch(root, viol, work):
    reps = _reports(root, "work/arch")
    for rp in reps:
        rel = rp.relative_to(root)
        t = rp.read_text(encoding="utf-8", errors="replace")
        designs = re.findall(r"(?m)^##\s+Design\b", t)
        if len(designs) < 2:
            viol.append("%s: %d `## Design` section(s); design it twice needs >= 2 radically different designs" % (rel, len(designs)))
        if not re.search(r"(?mi)^\|.*\bdepth\b.*\|", t):
            viol.append("%s: no comparison table with a depth column" % rel)
        if not _fields(t).get("pick"):
            viol.append("%s: no `pick:` line (the chosen design and why)" % rel)
    return len(reps)


# ------------------------------------------------------------------ intake
def _lock_rows(root):
    p = Path(root) / "upstream" / "LOCK.json"
    if not p.exists():
        return []
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as e:
        raise Unreadable("upstream/LOCK.json: %s" % e)
    rows = doc if isinstance(doc, list) else (doc.get("rows") or doc.get("lock") or [])
    return [r for r in rows if isinstance(r, dict)]


def check_intake(root, viol, work):
    reps = _reports(root, "work/intake")
    lock = None
    for rp in reps:
        rel = rp.relative_to(root)
        f = _fields(rp.read_text(encoding="utf-8", errors="replace"))
        for k in ("repo", "sha", "licence", "agent_files", "decision"):
            if not f.get(k):
                viol.append("%s: missing %s" % (rel, k))
        sha = f.get("sha", "").strip("` ").lower()
        if sha and not HEX40.match(sha):
            viol.append("%s: sha %r is not 40 hex (re-derive with git rev-parse)" % (rel, sha[:16]))
        dec = f.get("decision", "").lower()
        if dec and dec not in INTAKE_DECISIONS:
            viol.append("%s: decision %r is not %s" % (rel, dec, "|".join(sorted(INTAKE_DECISIONS))))
        if dec == "ingest":
            lock = _lock_rows(root) if lock is None else lock
            repo = f.get("repo", "").strip("` ")
            if not any(str(r.get("repo")) == repo and str(r.get("sha", "")).lower() == sha for r in lock):
                viol.append("%s: decision ingest but upstream/LOCK.json has no row %s@%s (ingest.py writes it)" % (rel, repo, sha[:7]))
    return len(reps)


# ------------------------------------------------------------------ roster
DEFAULT_MODELS = re.compile(r"(?s)const\s+DEFAULT_MODELS\s*=\s*\{(.*?)\}")


def check_roster(root, viol, work):
    root = Path(root)
    sj = root / "station.json"
    if not sj.exists():
        return 0
    try:
        roster = (json.loads(sj.read_text(encoding="utf-8")).get("gov") or {}).get("model_roster") or {}
    except ValueError as e:
        raise Unreadable("station.json: %s" % e)
    n = 0
    for wf in sorted((root / ".claude" / "workflows").glob("*.js")):
        m = DEFAULT_MODELS.search(wf.read_text(encoding="utf-8"))
        if not m:
            continue
        n += 1
        got = dict(re.findall(r"(\w+)\s*:\s*'([^']*)'", m.group(1)))
        if got != {k: v for k, v in roster.items() if isinstance(v, str)}:
            viol.append("%s: DEFAULT_MODELS %s != station.json gov.model_roster %s" % (wf.relative_to(root), got, roster))
    return n


CHECKS = [check_trial, check_holdout, check_telemetry, check_re_gate, check_repin, check_noise, check_wiki, check_arch,
          check_intake, check_roster]

# kind -> (folder, required fields or None for a structural check, the deliverable's file inside a dir)
KINDS = {
    "trial": ("work/trials", ("verdict", "n_tasks", "noise_floor", "spread")),
    "optimize": ("work/optimize", ("holdout_sha256", "holdout_frozen_at", "gain_status")),
    "wiki": ("work/wiki", ("target", "target_class", "status")),
    "re": ("work/re", ("gate",)),
    "arch": ("work/arch", ("pick",)),
    "intake": ("work/intake", ("repo", "sha", "decision")),
    "repin": ("work/repin", ("status", "applied")),
}


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


def cmd_output(root, kind, rel):
    """Certain test of one workflow run: the whole gate is clean AND the deliverable is there and complete."""
    folder, required = KINDS[kind]
    p = (root / rel).resolve()
    viol = []
    try:
        p.relative_to((root / folder).resolve())
    except ValueError:
        viol.append("%s is not under %s/" % (rel, folder))
    if p.is_dir():
        p = p / "REVIEW.md"
    if not p.is_file():
        viol.append("deliverable %s does not exist (the workflow produced nothing)" % rel)
    else:
        f = _fields(p.read_text(encoding="utf-8", errors="replace"))
        miss = [k for k in required if not f.get(k)]
        if miss:
            viol.append("%s: missing %s" % (rel, ", ".join(miss)))
    if kind == "trial" and p.is_file():
        led = Path(root) / "governance" / "STATION_LEDGER.md"
        rows = trial_rows(led.read_text(encoding="utf-8", errors="replace")) if led.exists() else []
        if _fields(p.read_text(encoding="utf-8", errors="replace")).get("verdict", "").lower() in ("promote", "park") and \
                not any(len(c) >= 8 and c[7].strip("` ") == Path(rel).as_posix() for c in rows):
            viol.append("%s: has a verdict but no TRIAL row in governance/STATION_LEDGER.md names it" % rel)
    try:
        gv, gw, den = run(root)
    except Unreadable as e:
        print("forge_output: UNREADABLE (%s)" % e)
        return 2
    viol.extend(gv)
    print("forge_output %s: %d violation(s) · %d worklist · denominator %d" % (kind, len(viol), len(gw), den + 1))
    for v in viol:
        print("  VIOLATION " + v)
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
        "work/trials/projectatlas.md": "verdict: park\nn_tasks: 6\nnoise_floor: K=5 seed fixed\nspread: 0.04\ngain: 0.01 (inside the spread: park)\n",
        "work/wiki/dotfiles/REVIEW.md": "target: ~/src/dotfiles\ntarget_class: own\nstatus: refused-telemetry\n",
        "work/arch/router.md": "## Design A\nx\n## Design B\ny\n| design | depth | leverage | locality |\n|---|---|---|---|\npick: B -- deeper module\n",
        "work/intake/foo.md": "repo: foo/bar\nsha: %s\nlicence: MIT\nagent_files: CLAUDE.md\ndecision: ingest\n" % ("c" * 40),
        "upstream/LOCK.json": json.dumps({"rows": [{"repo": "foo/bar", "sha": "c" * 40}]}),
        "station.json": json.dumps({"name": "forge", "gov": {"model_roster": {"small": "haiku", "large": "opus"}}}),
        ".claude/workflows/w.js": "const DEFAULT_MODELS = { small: 'haiku', large: 'opus' }\n",
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
        ("trial verdict without noise floor", {"work/trials/projectatlas.md": "verdict: park\nn_tasks: 6\n"}),
        ("optimize gain inside the spread", {"work/optimize/latency.md": "holdout_sha256: %s\nholdout_frozen_at: x\ngain_status: out-of-sample\nholdout_score: 0.71\nnoise_floor: K=6\nspread: 0.05\ngain: 0.03\n" % ("b" * 64)}),
        ("trial promoted inside the spread", {"work/trials/projectatlas.md": "verdict: promote\nn_tasks: 6\nnoise_floor: K=5\nspread: 0.04\ngain: 0.02\n"}),
        ("noise floor K<5", {"work/trials/projectatlas.md": "verdict: park\nn_tasks: 6\nnoise_floor: K=3\nspread: 0.04\n"}),
        ("wiki generated with telemetry unverified", {"work/wiki/dotfiles/REVIEW.md": "target: x\ntarget_class: own\nstatus: generated\n"}),
        ("wiki generated for a client repo", {"work/wiki/dotfiles/REVIEW.md": "target: x\ntarget_class: client\nstatus: generated\n",
                                              "registry/telemetry.json": json.dumps({"telemetry": [{"tool": "openwiki", "repo": "langchain-ai/openwiki", "verified": True, "verified_by_run": "x"}]})}),
        ("arch designed once", {"work/arch/router.md": "## Design A\n| design | depth |\npick: A\n"}),
        ("intake ingest without LOCK row", {"upstream/LOCK.json": json.dumps({"rows": []})}),
        ("intake short sha", {"work/intake/foo.md": "repo: foo/bar\nsha: abc1234\nlicence: MIT\nagent_files: none\ndecision: bootstrap\n"}),
        ("workflow roster drift", {".claude/workflows/w.js": "const DEFAULT_MODELS = { small: 'opus', large: 'opus' }\n"}),
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
        # output: a present, complete deliverable passes; a missing one and a field-less one fail
        t4 = tempfile.mkdtemp(prefix="forge_check_o_")
        try:
            _plant(t4, good)
            r4 = Path(t4)
            import contextlib
            import io
            with contextlib.redirect_stdout(io.StringIO()):
                a = cmd_output(r4, "arch", "work/arch/router.md")
                b = cmd_output(r4, "arch", "work/arch/missing.md")
                c = cmd_output(r4, "wiki", "work/wiki/dotfiles")
                _plant(t4, {"work/re/bare.md": "gate: RE-GATE-0001\n"})
                d = cmd_output(r4, "trial", "work/re/bare.md")
                _plant(t4, {"work/trials/other.md": "verdict: promote\nn_tasks: 7\nnoise_floor: K=5\nspread: 0.01\ngain: 0.2\n"})
                e = cmd_output(r4, "trial", "work/trials/other.md")
            if (a, b, c, d, e) == (0, 1, 0, 1, 1):
                print("selftest ok: output gate (present 0, missing 1, wiki dir 0, wrong folder 1, verdict without TRIAL row 1)")
            else:
                print("selftest FAIL: output gate returned %s" % ((a, b, c, d, e),))
                fails += 1
        finally:
            shutil.rmtree(t4, ignore_errors=True)
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
    ap.add_argument("cmd", nargs="?", choices=["check", "output"])
    ap.add_argument("kind", nargs="?", choices=sorted(KINDS))
    ap.add_argument("path", nargs="?")
    ap.add_argument("--root", default=".")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.cmd == "check":
        return cmd_check(Path(a.root).resolve())
    if a.cmd == "output":
        if not (a.kind and a.path):
            ap.error("output needs <kind> <path>")
        return cmd_output(Path(a.root).resolve(), a.kind, a.path)
    ap.print_usage()
    return 2


if __name__ == "__main__":
    sys.exit(main())
