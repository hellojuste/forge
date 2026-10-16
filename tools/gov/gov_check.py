#!/usr/bin/env python3
"""gov_check.py -- governance's own checks, one subcommand each (PROGRAMME_GOVERNANCE 3.10). stdlib only.

owner: governance/rules.json R-gov-checks
    python3 tools/gov/gov_check.py <check> [--root DIR] [--base REV] [--triggers] [--selftest]
    python3 tools/gov/gov_check.py --selftest          every subcommand's planted fixtures
Checks (hyphen or underscore spelling): claudemd station rules canon decisions history ledger ledger_owed(W)
defects defects_due(W) releases hooks_wired hooks_selftest hook_channels headers(W) admission router_targets
commons_drift main_purity.  (W) = WORKLIST: counts, exit 0.
First stdout line, always: "<check>: <n> violation(s) · <m> worklist · denominator <d>".
Exit 0 clean . 1 violation . 2 unreadable input (a failed read is never an empty read).
Earned by: lettuce's audit scripts each parsed registers their own way and three disagreed on the header grammar;
one script over one kernel (_gov.py) keeps every governance claim re-derived from source.
"""
import argparse
import concurrent.futures as cf
import datetime as dt
import json
import os
import re
import shlex
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _gov  # noqa: E402

V, W = "violation", "worklist"
HOOK_EVENTS_SILENT = {"PreToolUse", "PostToolUse", "Stop", "SubagentStop", "PostToolUseFailure"}
REPORT_KEYS = {"hookSpecificOutput", "systemMessage", "decision", "continue", "suppressOutput", "reason", "stopReason"}
REQUIRED_EXCLUDES = ["**/upstream/**/CLAUDE.md", "**/upstream/**/CLAUDE.local.md", "**/upstream/**/AGENTS.md",
                     "**/upstream/**/.claude/**"]
BANNED_AMENDMENT = re.compile(r"be (more )?careful|remember to|try harder|pay attention", re.I)
SCOPE_EXCUSE = re.compile(r"out of scope|not a one-line fix|not in scope|outside (my|this) scope", re.I)


class R:
    """One check's result: violations, worklist items, denominator."""

    def __init__(self):
        self.v, self.w, self.d = [], [], 0

    def bad(self, msg):
        self.v.append(msg)

    def todo(self, msg):
        self.w.append(msg)


# ---------------------------------------------------------------- shared readers
def rules_rows(root):
    return _gov.load_rows(root, "governance/rules.json", "governance/rules.d", "rules")


def check_rows(root):
    return _gov.load_rows(root, "governance/checks.json", "governance/checks.d", "checks")


def settings(root):
    return _gov.load_json(Path(root) / ".claude" / "settings.json")


def canon_decls(root):
    decl = {}
    for p in [Path(root) / "governance" / "rules.json"] + _gov.fragments(root, "governance/rules.d"):
        if p.exists():
            decl.update(_gov.load_json(p).get("canon") or {})
    return decl


def wired(root):
    """{script_rel: [(event, matcher, hookdict, argv)]} from settings.json."""
    out = {}
    for ev, mt, g, h, script in _gov.wired_commands(settings(root)):
        cmd = h.get("command", "")
        tail = cmd.split("exit 0;", 1)[-1]
        try:
            argv = shlex.split(tail)
        except ValueError:
            argv = tail.split()
        if script:
            out.setdefault(script, []).append((ev, mt, h, argv))
    return out


def dispatcher_modules(root):
    """{module name: path rel} named by the effective hooks.PreToolUse list."""
    mods = {}
    for m in _gov.config(root).get("hooks", {}).get("PreToolUse", []):
        rel = (".claude/hooks/station/%s.py" % m.split("/", 1)[1]) if m.startswith("station/") else ".claude/hooks/%s.py" % m
        mods[m] = rel
    return mods


def register_files(root, kind):
    base = {"dec": "DECISIONS.md", "ledger": "LEDGER.md", "def": "DEFECTS.md"}[kind]
    out = [("governance/" + base, "core")]
    sta = "governance/STATION_" + base
    if (Path(root) / sta).exists():
        out.append((sta, _gov.station_name(root)))
    return out


def read(root, rel):
    try:
        return (Path(root) / rel).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise _gov.GovError("missing: %s" % rel)
    except OSError as e:
        raise _gov.GovError("unreadable %s: %s" % (rel, e))


def head_rows(root, rel):
    if not (_gov.is_git(root) and _gov.has_head(root)):
        return None
    t = _gov.show(root, "HEAD", rel)
    return _gov.parse_rows(t) if t is not None else None


def check_ids(r, rows, rel, prefix, station):
    last, seen = 0, set()
    for row in rows:
        p = _gov.id_parts(row["id"])
        if not p or p[0] != prefix:
            r.bad("%s: unparseable id %s" % (rel, row["id"]))
            continue
        if (p[1] or "core") != station:
            r.bad("%s: %s carries station '%s', this file holds '%s' rows" % (rel, row["id"], p[1] or "core", station))
        if row["id"] in seen:
            r.bad("%s: duplicate id %s" % (rel, row["id"]))
        elif p[2] <= last:
            r.bad("%s: %s is not increasing in file order" % (rel, row["id"]))
        seen.add(row["id"])
        last = max(last, p[2])


# ---------------------------------------------------------------- checks
def c_claudemd(root, a):
    r = R()
    cfg = _gov.config(root)
    g = cfg["gov"]
    text = read(root, "CLAUDE.md")
    size = len(text.encode("utf-8"))
    budgets = cfg.get("claude_md_budget") if isinstance(cfg.get("claude_md_budget"), dict) else {}
    cap = int(budgets.get("core", 4096))
    r.d += 1
    if size > cap:
        r.bad("CLAUDE.md is %d B > %d B commons cap (claude_md_budget.core)" % (size, cap))
    hot = size + sum(len(p.read_bytes()) for p in sorted((Path(root) / ".claude" / "rules").glob("*.md")))
    budget = int(g.get("claude_md_budget", 6144))
    r.d += 1
    if hot > budget:
        r.bad("hot path CLAUDE.md + .claude/rules/*.md is %d B > %d B (gov.claude_md_budget, knob %s)"
              % (hot, budget, (cfg.get("knobs") or {}).get("gov", "standard")))
    allowed = g.get("claude_md_sections") or []
    for line in text.splitlines():
        m = re.match(r"^##\s+(.*)$", line)
        if m:
            r.d += 1
            if not any(m.group(1).strip().startswith(s) for s in allowed):
                r.bad("CLAUDE.md section '%s' is not in gov.claude_md_sections %s" % (m.group(1).strip(), allowed))
    owners = set()
    for row in rules_rows(root):
        o = (row.get("owner") or "").partition("#")[0]
        if o and o != "CLAUDE.md" and (Path(root) / o).is_file():
            owners.add(o)
    owner_text = {o: _collapse((Path(root) / o).read_text(encoding="utf-8", errors="replace")) for o in owners}
    for line in text.splitlines():
        s = line.strip()
        if len(s) >= 60:
            r.d += 1
            for o, t in owner_text.items():
                if _collapse(s) in t:
                    r.bad("CLAUDE.md line duplicated verbatim in owner %s: %r (the hot path is a pointer)" % (o, s[:80]))
    return r


def _collapse(s):
    return re.sub(r"\s+", " ", s).strip()


GOV_INTS = ["ctx_warn", "ctx_handoff", "ctx_repeat", "beat_s", "ceiling_s", "margin_s", "stale_beats",
            "block_max_agents", "block_window_s", "claude_md_budget", "state_budget"]
GOV_REQUIRED = GOV_INTS + ["claude_md_sections", "hot_path", "model_roster", "efforts", "defect_watch",
                           "hedge_regex", "protected_branches", "upstream_dirs", "patch_dir_name", "release_scopes"]


def c_station(root, a):
    r = R()
    schema = _gov.load_json(Path(root) / "commons" / "schema" / "station.schema.json")
    st = _gov.station_json(root)
    if st is not None:
        r.d += 1
        for e in _gov.validate(st, schema):
            r.bad("station.json: %s" % e)
    cfg = _gov.config(root)
    g = cfg.get("gov")
    if not isinstance(g, dict) or not g:
        r.bad("effective config has no gov block (commons/defaults.json + station.json)")
        return r
    for k in GOV_REQUIRED:
        r.d += 1
        if k not in g:
            r.bad("gov.%s missing" % k)
    for k in GOV_INTS:
        if k in g and (not isinstance(g[k], int) or isinstance(g[k], bool)):
            r.bad("gov.%s is not an integer: %r" % (k, g[k]))
    try:
        if int(g["ctx_warn"]) >= int(g["ctx_handoff"]):
            r.bad("gov.ctx_warn %s >= ctx_handoff %s" % (g["ctx_warn"], g["ctx_handoff"]))
        if (int(g["ceiling_s"]) - int(g["margin_s"])) % int(g["beat_s"]) != 0:
            r.bad("cadence ceiling_s - margin_s = %d is not a whole number of beats (beat_s %d)"
                  % (int(g["ceiling_s"]) - int(g["margin_s"]), int(g["beat_s"])))
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as e:
        r.bad("gov thresholds unusable: %s" % e)
    try:
        re.compile(g.get("hedge_regex", ""))
    except re.error as e:
        r.bad("gov.hedge_regex does not compile: %s" % e)
    if not isinstance(g.get("model_roster"), dict):
        r.bad("gov.model_roster is not an object")
    for k in ("listing_budget_bytes", "listed_max", "sessionstart_budget_bytes"):
        r.d += 1
        if not isinstance(cfg.get(k), int):
            r.bad("%s missing or not an integer" % k)
    return r


def _hook_verdict_doc(root, rel):
    first = _gov.docstring(Path(root) / rel).strip().splitlines()[:1]
    return "deny" if first and "DENY" in first[0] else None


def _implied_verdict(root, ref, why):
    """A row without enforcement.verdict: DENY / ASK as an upper-case word in its why or the hook's first docstring line."""
    first = (_gov.docstring(Path(root) / ref).strip().splitlines() or [""])[0]
    text = "%s %s" % (why or "", first)
    if re.search(r"\bDENY\b", text):
        return "deny"
    if re.search(r"\bASKS?\b", text):
        return "ask"
    return "report"


def c_rules(root, a):
    r = R()
    rows = rules_rows(root)
    wmap = wired(root)
    mods = dispatcher_modules(root)
    checks = {c.get("name"): c for c in check_rows(root)}
    named_hooks, named_checks, seen = set(), set(), set()
    for row in rows:
        r.d += 1
        rid = row.get("id", "?")
        where = "%s %s" % (row.get("_src"), rid)
        if rid in seen:
            r.bad("duplicate rule id %s (%s)" % (rid, row.get("_src")))
        seen.add(rid)
        for k in ("headline", "owner", "enforcement", "earned_by", "rung", "upstream"):
            if not row.get(k):
                r.bad("%s: missing %s" % (where, k))
        opath = (row.get("owner") or "").partition("#")[0]
        on_main = _gov.station_json(root) is None
        if not (opath and on_main and _gov.station_only(opath)):  # a station-only owner resolves on stations only
            ok, why = _gov.resolve_anchor(root, row.get("owner") or "")
            if row.get("owner") and not ok:
                r.bad("%s: %s" % (where, why))
        if row.get("upstream") and row["upstream"] not in ("NEVER", "SUBTREE", "N/A"):
            r.bad("%s: upstream %r not in NEVER|SUBTREE|N/A" % (where, row["upstream"]))
        e = _gov.norm_enforcement(row.get("enforcement") or {})
        derived = "soft"
        if e["kind"] == "hook":
            ref = e["ref"].partition("#")[0]
            named_hooks.add(ref)
            via_dispatch = ref in mods.values()
            if ref not in wmap and not via_dispatch:
                r.bad("%s: hook %s is not wired in .claude/settings.json nor named in hooks.PreToolUse" % (where, ref))
            elif not (Path(root) / ref).exists():
                r.bad("%s: hook %s does not exist" % (where, ref))
            explicit = (row.get("enforcement") or {}).get("verdict")
            verdict = explicit or _implied_verdict(root, ref, e["why"])
            if verdict not in ("deny", "ask", "report"):
                r.bad("%s: enforcement.verdict %r not in deny|ask|report" % (where, verdict))
            if explicit and _hook_verdict_doc(root, ref) == "deny" and verdict != "deny":
                r.bad("%s: %s's docstring says DENY but the row says %s" % (where, ref, verdict))
            derived = "hard" if verdict == "deny" else "soft"
        elif e["kind"] == "check":
            named_checks.add(e["ref"])
            if e["ref"] not in checks:
                r.bad("%s: check %s is not registered in checks.json/checks.d" % (where, e["ref"]))
            elif checks[e["ref"]].get("class") == "MUST_BE_CLEAN":
                derived = "hard"
        elif e["kind"] == "owed":
            if not e["trigger"] or not e["shape"]:
                r.bad("%s: OWED enforcement needs shape and trigger" % where)
        elif e["kind"] == "not-hookable":
            if not e["why"]:
                r.bad("%s: NOT HOOKABLE enforcement needs why" % where)
        else:
            r.bad("%s: enforcement.kind %r not in hook|check|owed|not-hookable" % (where, e["kind"]))
        if row.get("rung") and row["rung"] != derived:
            r.bad("%s: rung %s disagrees with its derivation %s" % (where, row["rung"], derived))
        for p in row.get("pointers") or []:
            if on_main and _gov.station_only(p):
                continue
            fp = Path(root) / p
            if not fp.exists():
                r.bad("%s: pointer file %s missing" % (where, p))
                continue
            t = fp.read_text(encoding="utf-8", errors="replace")
            if rid not in t and ("see " + (row.get("owner") or "")) not in t:
                r.bad("%s: pointer %s names neither %s nor 'see %s'" % (where, p, rid, row.get("owner")))
    for script in sorted(wmap):
        r.d += 1
        if script not in named_hooks:
            r.bad("orphan mechanism: wired hook %s is named by no rule" % script)
    for m, rel in sorted(mods.items()):
        r.d += 1
        if rel not in named_hooks and (Path(root) / rel).exists():
            r.bad("orphan mechanism: dispatcher module %s is named by no rule" % m)
    for name in sorted(checks):
        r.d += 1
        if name not in named_checks:
            r.bad("orphan mechanism: check %s is named by no rule" % name)
    s = settings(root)
    ex = s.get("claudeMdExcludes") or []
    for want in REQUIRED_EXCLUDES:
        r.d += 1
        if want not in ex:
            r.bad(".claude/settings.json claudeMdExcludes lacks %s (upstream agent files would load)" % want)
    return r


CANON_RE = re.compile(r"^\s*(?:#|//|<!--|/\*|\*|;|--)\s*CANON:([A-Za-z0-9_-]+)(?:\s+(BEGIN|END))?")


def _canon_blocks(lines):
    """[(group, body lines)]: `CANON:g BEGIN` .. `CANON:g END`, or `CANON:g` .. `/CANON:g`, or a bare
    `CANON:g` marker covering the next 2 lines."""
    out, i = [], 0
    while i < len(lines):
        m = CANON_RE.search(lines[i])
        if not m or "CANON:<" in lines[i] or m.group(2) == "END":
            i += 1
            continue
        g = m.group(1)
        end_rx = re.compile(r"CANON:%s\s+END|/CANON:%s\b" % (re.escape(g), re.escape(g)))
        j = next((k for k in range(i + 1, min(len(lines), i + 200)) if end_rx.search(lines[k])), None)
        if m.group(2) == "BEGIN" or j is not None:
            j = j if j is not None else len(lines)
            out.append((g, lines[i + 1:j]))
            i = j + 1
        else:
            out.append((g, lines[i + 1:i + 3]))
            i += 3
    return out


def c_canon(root, a):
    """Groups are declared in rules.json (or rules.d) `canon`: {group: "strict"} = every marked copy equal and
    at least two; {group: {"mode": "owner", "owner": <path>, "lines": <regex>}} = in every marked copy, each line
    matching <regex> appears verbatim in the owner file (the owner need not carry a marker)."""
    r = R()
    decl = canon_decls(root)
    lanes = tuple(_gov.config(root)["gov"].get("upstream_dirs") or [])
    groups = {}
    for rel in _gov.tracked_files(root):
        if rel.startswith(lanes) or rel.startswith(".upstream/"):
            continue
        p = Path(root) / rel
        try:
            if p.stat().st_size > 2_000_000:
                continue
            lines = p.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for g, body in _canon_blocks(lines):
            groups.setdefault(g, []).append((rel, body))
    for g, copies in sorted(groups.items()):
        r.d += 1
        mode = decl.get(g)
        if mode is None:
            r.bad("CANON:%s is not declared in rules.json canon (copies: %s)" % (g, ", ".join(c[0] for c in copies)))
            continue
        if isinstance(mode, dict) and mode.get("mode") == "owner":
            op = Path(root) / mode.get("owner", "")
            if not op.is_file():
                r.bad("CANON:%s owner %s missing" % (g, mode.get("owner")))
                continue
            otext = {_collapse(l) for l in op.read_text(encoding="utf-8", errors="replace").splitlines()}
            rx = re.compile(mode.get("lines") or ".")
            for rel, body in copies:
                for l in body:
                    if rx.search(l) and _collapse(l) not in otext:
                        r.bad("CANON:%s copy in %s differs from its owner %s: %r" % (g, rel, mode["owner"], l.strip()[:80]))
            continue
        if mode == "strict" and len(copies) < 2:
            r.bad("CANON:%s LONE COPY in %s" % (g, copies[0][0]))
        if mode == "strict" and len({_collapse("\n".join(c[1])) for c in copies}) > 1:
            r.bad("CANON:%s copies differ: %s" % (g, ", ".join(c[0] for c in copies)))
    return r


STATUS_RE = re.compile(r"^(CURRENT|SUPERSEDED \d{4}-\d{2}-\d{2} by (DEC-[a-z0-9-]*\d{4})|PARTIAL by (DEC-[a-z0-9-]*\d{4}).*)$")


def c_decisions(root, a):
    r = R()
    all_ids = {}
    files = register_files(root, "dec")
    parsed = []
    for rel, station in files:
        rows = _gov.parse_rows(read(root, rel))
        parsed.append((rel, station, rows))
        check_ids(r, rows, rel, "DEC", station)
        for i, row in enumerate(rows):
            all_ids.setdefault(row["id"], (rel, i))
    for rel, station, rows in parsed:
        for i, row in enumerate(rows):
            r.d += 1
            f = row["fields"]
            for k in ("words", "locator", "kind"):
                if not f.get(k):
                    r.bad("%s %s: missing %s" % (rel, row["id"], k))
            if f.get("kind") and f["kind"].split()[0] not in ("rule", "exception", "amendment", "correction", "grant"):
                r.bad("%s %s: kind %r" % (rel, row["id"], f["kind"]))
            st = f.get("status", "CURRENT")
            m = STATUS_RE.match(st)
            if not m:
                r.bad("%s %s: status %r not CURRENT|SUPERSEDED <date> by DEC-x|PARTIAL by DEC-x" % (rel, row["id"], st))
            else:
                ref = m.group(2) or m.group(3)
                if ref:
                    if ref not in all_ids:
                        r.bad("%s %s: superseded by %s, which does not exist" % (rel, row["id"], ref))
                    elif all_ids[ref][0] == rel and all_ids[ref][1] <= i:
                        r.bad("%s %s: superseded by %s, which is not later" % (rel, row["id"], ref))
            am = f.get("amends")
            if am and am.split()[0] not in all_ids:
                r.bad("%s %s: amends %s, which does not exist" % (rel, row["id"], am))
        hr = head_rows(root, rel)
        if hr is not None:
            now = {row["id"]: row for row in rows}
            for old in hr:
                if old["id"] not in now:
                    r.bad("%s: %s exists at HEAD and was deleted (amend, never delete)" % (rel, old["id"]))
                elif old["fields"].get("words", "") != now[old["id"]]["fields"].get("words", ""):
                    r.bad("%s: %s words: changed from HEAD (verbatim lock; a correction is a new row)" % (rel, old["id"]))
    return r


def _diff(root, base):
    if not _gov.is_git(root):
        raise _gov.GovError("history needs a git repo")
    args = ["diff", "-U0", "--no-color"] + (["%s..HEAD" % base] if base else ["--cached"])
    d = _gov.git(root, *args)
    if d.returncode != 0:
        raise _gov.GovError("git diff failed: %s" % d.stderr.strip()[:160])
    removed, added, cur = [], set(), None
    for line in d.stdout.splitlines():
        if line.startswith("--- ") or line.startswith("+++ "):
            if line.startswith("+++ "):
                pass
            if line.startswith("--- "):
                cur = line[6:] if line.startswith("--- a/") else None
            continue
        if line.startswith("-") and cur:
            removed.append((cur, line[1:]))
        elif line.startswith("+"):
            added.add(_collapse(line[1:]))
    return removed, added


def c_history(root, a):
    r = R()
    g = _gov.config(root)["gov"]
    hot = g.get("hot_path") or ["CLAUDE.md"]
    removed, added = _diff(root, getattr(a, "base", None))
    hist = ""
    for rel in ("governance/HISTORY.md", "governance/STATION_HISTORY.md"):
        p = Path(root) / rel
        if p.exists():
            hist += _collapse(p.read_text(encoding="utf-8", errors="replace")) + " "
    for f, line in removed:
        s = line.strip()
        if not _gov.any_match(f, hot) or len(s) < 40 or re.match(r"^#+\s", s):
            continue
        r.d += 1
        c = _collapse(s)
        if c in added or c in hist:
            continue
        r.bad("%s: removed hot-path line not moved verbatim to governance/HISTORY.md: %r" % (f, s[:90]))
    return r


HOOK_FORM = re.compile(r"^(HOOKED\s+(\S+)|OWED\s+.+trigger:\s*\S.*|NOT HOOKABLE\s+\S.*)$")


def c_ledger(root, a, owed_only=False):
    r = R()
    effort = judgement = 0
    for rel, station in register_files(root, "ledger"):
        rows = _gov.parse_rows(read(root, rel))
        if not owed_only:
            check_ids(r, rows, rel, "L", station)
        for row in rows:
            r.d += 1
            f = row["fields"]
            hk = f.get("hook", "")
            if hk.startswith("OWED"):
                r.todo("%s %s OWED: %s" % (rel, row["id"], hk[4:].strip()[:120]))
            ax = f.get("axis", "")
            effort += ax == "effort"
            judgement += ax == "judgement"
            if owed_only:
                continue
            for k in ("hook", "axis", "amendment"):
                if not f.get(k):
                    r.bad("%s %s: missing %s" % (rel, row["id"], k))
            if hk:
                m = HOOK_FORM.match(hk)
                if not m:
                    r.bad("%s %s: hook %r not HOOKED <path> | OWED <shape> — trigger: <c> | NOT HOOKABLE <why>" % (rel, row["id"], hk[:60]))
                elif m.group(2) and not (Path(root) / m.group(2)).exists():
                    r.bad("%s %s: HOOKED %s does not exist" % (rel, row["id"], m.group(2)))
            if ax and ax not in ("effort", "judgement"):
                r.bad("%s %s: axis %r" % (rel, row["id"], ax))
            am = f.get("amendment", "")
            if am:
                if BANNED_AMENDMENT.search(am):
                    r.bad("%s %s: amendment %r amends conduct, not a mechanism" % (rel, row["id"], am[:60]))
                else:
                    target = re.split(r"\s+[—-]\s+|\s+", am.strip(), maxsplit=1)[0]
                    ok, why = _gov.resolve_anchor(root, target)
                    if not ok:
                        r.bad("%s %s: amendment %s" % (rel, row["id"], why))
            if f.get("kind", "procedural") == "delegation" and not re.match(r"^P[1-8]\b", f.get("pathology", "")):
                r.bad("%s %s: delegation row without a pathology P1-P8" % (rel, row["id"]))
        if not owed_only:
            hr = head_rows(root, rel)
            if hr is not None:
                now = {row["id"] for row in rows}
                for old in hr:
                    if old["id"] not in now:
                        r.bad("%s: %s exists at HEAD and was deleted (supersede with a later row)" % (rel, old["id"]))
    if owed_only:
        print_extra.append("axis split: effort %d · judgement %d · denominator %d rows" % (effort, judgement, r.d))
    return r


def c_ledger_owed(root, a):
    return c_ledger(root, a, owed_only=True)


DEF_STATUS = re.compile(r"^(OPEN|FIXED \S+|WONTFIX DEC-[a-z0-9-]*\d{4}|MOVED \S+)$")


def c_defects(root, a, due_only=False):
    r = R()
    today = dt.date.today()
    for rel, station in register_files(root, "def"):
        rows = _gov.parse_rows(read(root, rel))
        if not due_only:
            check_ids(r, rows, rel, "DEF", station)
        for row in rows:
            r.d += 1
            f = row["fields"]
            st = f.get("status", "")
            trig = f.get("trigger", "")
            if due_only:
                if st == "OPEN":
                    m = re.search(r"date:\s*(\d{4}-\d{2}-\d{2})", trig)
                    if m and dt.date.fromisoformat(m.group(1)) <= today:
                        r.todo("%s %s DUE since %s" % (rel, row["id"], m.group(1)))
                    if getattr(a, "triggers", False) and trig.startswith("cmd:"):
                        rc, _, _ = _gov.run(shlex.split(trig[4:].strip()), root, timeout=60)
                        print_extra.append("%s %s: %s" % (row["id"], "FIXED-NOW" if rc == 0 else "STILL-OPEN", trig[4:].strip()))
                continue
            if not DEF_STATUS.match(st):
                r.bad("%s %s: status %r" % (rel, row["id"], st))
            for k in ("where", "owner"):
                if not f.get(k):
                    r.bad("%s %s: missing %s" % (rel, row["id"], k))
            if st == "OPEN":
                if not trig:
                    r.bad("%s %s: OPEN without trigger" % (rel, row["id"]))
                elif not re.match(r"^(cmd|event|date):\s*\S", trig):
                    r.bad("%s %s: trigger %r not cmd:|event:|date:" % (rel, row["id"], trig[:40]))
                why = f.get("why_not_fixed_now", "")
                if not why:
                    r.bad("%s %s: OPEN without why_not_fixed_now" % (rel, row["id"]))
                elif f.get("owner") == "this-station" and SCOPE_EXCUSE.search(why):
                    r.bad("%s %s: own defect excused by scope (%r) — it is your owed result" % (rel, row["id"], why[:50]))
            if st.startswith("FIXED "):
                sha = st.split()[1]
                if not _gov.is_git(root) or _gov.git(root, "cat-file", "-e", sha + "^{commit}").returncode != 0:
                    r.bad("%s %s: FIXED %s does not resolve to a commit" % (rel, row["id"], sha))
    return r


def c_defects_due(root, a):
    return c_defects(root, a, due_only=True)


def _iso(s):
    s = str(s).replace("Z", "+00:00")
    if len(s) == 16:
        s += ":00"
    v = dt.datetime.fromisoformat(s)
    return v if v.tzinfo else v.replace(tzinfo=dt.timezone.utc)


def c_releases(root, a):
    r = R()
    data = _gov.load_json(Path(root) / "governance" / "RELEASES.json")
    scopes = set(_gov.config(root)["gov"].get("release_scopes") or [])
    now = dt.datetime.now(dt.timezone.utc)
    ids = set()
    for row in data.get("releases", []):
        r.d += 1
        rid = row.get("id", "?")
        if rid in ids or not re.match(r"^REL-\d{4}$", rid):
            r.bad("%s: id missing, malformed or duplicated" % rid)
        ids.add(rid)
        for k in ("scope", "words", "locator", "utc", "expires"):
            if not row.get(k):
                r.bad("%s: missing %s" % (rid, k))
        if row.get("scope") and row["scope"].split(":", 1)[0] not in scopes:
            r.bad("%s: unknown scope %r (gov.release_scopes)" % (rid, row["scope"]))
        try:
            u, e = _iso(row["utc"]), _iso(row["expires"])
            if (e - u).total_seconds() > 7 * 86400:
                r.bad("%s: expires more than 7 days after utc" % rid)
            if e <= now:
                r.todo("%s expired %s (history; never delete)" % (rid, row["expires"]))
        except (KeyError, ValueError):
            r.bad("%s: utc/expires not ISO timestamps" % rid)
    return r


def c_hooks_wired(root, a):
    r = R()
    s = settings(root)
    wmap = wired(root)
    for ev, groups in (s.get("hooks") or {}).items():
        for gr in groups or []:
            for h in gr.get("hooks") or []:
                r.d += 1
                if "if" in h or "if" in gr:
                    r.bad("%s hook %r carries an `if:` filter (a filter on a hook path is a bypass)" % (ev, h.get("command", "")[:80]))
                cmd = h.get("command", "")
                if not cmd.startswith('cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0;'):
                    r.bad("%s hook %r is not guarded with cd \"${CLAUDE_PROJECT_DIR:-.}\" || exit 0" % (ev, cmd[:80]))
    for script in sorted(wmap):
        r.d += 1
        if not (Path(root) / script).exists():
            r.bad("wired script %s is missing" % script)
    mods = dispatcher_modules(root)
    if mods and ".claude/hooks/station_dispatch.py" not in wmap:
        r.bad("hooks.PreToolUse names modules but station_dispatch.py is not wired")
    for m, rel in sorted(mods.items()):
        r.d += 1
        if not (Path(root) / rel).exists():
            r.bad("dispatcher module %s (%s) is missing" % (m, rel))
    known = set(wmap) | set(mods.values())
    for p in sorted((Path(root) / ".claude" / "hooks").glob("**/*.py")):
        rel = str(p.relative_to(root))
        if p.name.startswith("_") or "__pycache__" in rel:
            continue
        r.d += 1
        if rel not in known:
            r.bad("orphan hook %s is wired nowhere (settings.json or hooks.PreToolUse)" % rel)
    return r


def _selftest_argv(root, argv):
    """argv of a wired command -> the argv that runs its selftest."""
    script = next((x for x in argv if x.endswith(".py")), None)
    if not script:
        return None
    try:
        text = (Path(root) / script).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if "--selftest" in text or "selftest" not in text:
        return [sys.executable, script, "--selftest"]
    return [sys.executable, script, "selftest"]


def c_hooks_selftest(root, a):
    r = R()
    runs = {}
    for script, entries in wired(root).items():
        st = _selftest_argv(root, entries[0][3])
        if st:
            runs[tuple(st)] = script
    for m, rel in dispatcher_modules(root).items():
        if (Path(root) / rel).exists():
            runs[(sys.executable, rel, "--selftest")] = rel
    with cf.ThreadPoolExecutor(max_workers=min(4, os.cpu_count() or 1)) as ex:
        futs = {ex.submit(_gov.run, list(st), root, 600): st for st in runs}
        for f in cf.as_completed(futs):
            st = futs[f]
            r.d += 1
            rc, out, err = f.result()
            if rc != 0:
                r.bad("%s selftest rc=%s: %s" % (" ".join(st[1:]), rc, (out + err).strip().splitlines()[-1:] or ""))
    return r


def c_hook_channels(root, a):
    r = R()
    probes = {"PreToolUse": {"tool_name": "Bash", "tool_input": {"command": "true"}},
              "PostToolUse": {"tool_name": "Bash", "tool_input": {"command": "true"}, "tool_response": {}},
              "Stop": {"stop_hook_active": False}, "SubagentStop": {"stop_hook_active": False}}
    with tempfile.TemporaryDirectory() as td:
        for script, entries in sorted(wired(root).items()):
            for ev, mt, h, argv in entries:
                if ev not in HOOK_EVENTS_SILENT:
                    continue
                r.d += 1
                payload = dict(probes.get(ev, {}), hook_event_name=ev, session_id="hook-channels-probe",
                               transcript_path=str(Path(td) / "none.jsonl"), cwd=str(root))
                cmd = [sys.executable if x == "python3" else x for x in argv]
                rc, out, err = _gov.run(cmd, root, timeout=60, input_=json.dumps(payload),
                                        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root)))
                for line in (out or "").splitlines():
                    if not line.strip():
                        continue
                    try:
                        j = json.loads(line)
                    except ValueError:
                        j = None
                    if not isinstance(j, dict) or not (set(j) & REPORT_KEYS):
                        r.bad("%s on %s prints plain stdout (lost to the debug log): %r" % (script, ev, line[:80]))
                        break
    return r


def c_headers(root, a):
    r = R()
    pats = ["governance/*.md", "docs/**/*.md", "HANDOFF*.md"]
    for rel in _gov.tracked_files(root):
        if not _gov.any_match(rel, pats):
            continue
        r.d += 1
        t = (Path(root) / rel).read_text(encoding="utf-8", errors="replace")
        h = _gov.five_field_header(t)
        if not h["ok"]:
            r.todo("%s: no five-field header (owner · status · date · supersedes · audit)" % rel)
        elif re.match(r"^\d+\s*(/|of)\s*\d+|^\d+\b|.*\bgreen\b", h["audit"]):
            r.todo("%s: audit: holds a number, not a command (%r)" % (rel, h["audit"][:40]))
    return r


def c_admission(root, a):
    r = R()
    for c in check_rows(root):
        r.d += 1
        for k in ("earned_by", "selftest", "retires"):
            if not c.get(k):
                r.bad("check %s (%s): empty %s (admission rule)" % (c.get("name"), c.get("_src"), k))
        for k in ("name", "cmd", "class", "programme", "inputs", "timeout_s"):
            if k not in c:
                r.bad("check %s: missing %s" % (c.get("name"), k))
        if c.get("class") not in ("MUST_BE_CLEAN", "WORKLIST"):
            r.bad("check %s: class %r" % (c.get("name"), c.get("class")))
    scripts = set(wired(root)) | set(dispatcher_modules(root).values())
    for rel in sorted(scripts):
        p = Path(root) / rel
        if not p.exists() or not rel.endswith(".py"):
            continue
        if not (rel.startswith(".claude/hooks/") or "/hooks/" in rel):
            continue
        r.d += 1
        doc = _gov.docstring(p)
        if "Earned by:" not in doc:
            r.bad("hook %s: docstring has no 'Earned by:' line" % rel)
        if doc.strip().splitlines()[:1] and "DENY" in doc.strip().splitlines()[0] and "Release:" not in doc:
            r.bad("DENY hook %s: docstring has no 'Release:' line" % rel)
    for name in sorted(_gov.COMMONS_SKILLS):
        p = Path(root) / ".claude" / "skills" / name / "SKILL.md"
        if not p.exists():
            continue
        r.d += 1
        t = p.read_text(encoding="utf-8", errors="replace")
        m = re.match(r"^---\n(.*?)\n---", t, re.S)
        if not m:
            r.bad("skill %s: frontmatter does not parse" % name)
            continue
        desc = re.search(r"^description:\s*(.*)$", m.group(1), re.M)
        if not desc or not desc.group(1).strip():
            r.bad("skill %s: no description" % name)
        elif len(desc.group(1).strip().strip('"').encode("utf-8")) > 200:
            r.bad("skill %s: description %d B > 200 B" % (name, len(desc.group(1).strip().encode("utf-8"))))
    return r


def router_rows(root):
    rows = []
    t = _gov.load_json(Path(root) / "router" / "intents.json")
    rows += [dict(x, _src="router/intents.json") for x in t.get("intents", [])]
    for p in _gov.fragments(root, "router/intents.d"):
        rows += [dict(x, _src=str(p.relative_to(root))) for x in _gov.load_json(p).get("intents", [])]
    kt = Path(root) / "router" / "kit_tree.json"
    if kt.exists():
        k = _gov.load_json(kt)
        rows += [dict(x, _src="router/kit_tree.json") for x in (k.get("intents") or k.get("leaves") or k.get("rows") or [])]
    return t, rows


def c_router_targets(root, a):
    r = R()
    t, rows = router_rows(root)
    schema = _gov.load_json(Path(root) / "commons" / "schema" / "intents.schema.json")
    for e in _gov.validate({k: v for k, v in t.items() if k != "intents"}, schema):
        r.bad("router/intents.json: %s" % e)
    pend = False
    sp = Path(root) / "governance" / "checks.d" / "station.json"
    if sp.exists():
        pend = bool(_gov.load_json(sp).get("equip_pending"))
    order = (t.get("router_tie_rule") or {}).get("order") or []
    dup = sorted({o for o in order if order.count(o) > 1})
    if dup:
        r.bad("router_tie_rule.order lists %s more than once" % ", ".join(dup))
    names = {}
    for row in rows:
        r.d += 1
        n = row.get("name", "?")
        for e in _gov.validate({"intents": [{k: v for k, v in row.items() if k != "_src"}]}, schema):
            r.bad("%s %s: %s" % (row["_src"], n, e))
        if n in names:
            r.bad("intent %s defined twice (%s, %s)" % (n, names[n], row["_src"]))
        names[n] = row["_src"]
        cls_station = row.get("contributed_by") == "station" or n.startswith("station:")
        if not cls_station and n not in order:
            r.bad("intent %s (%s) is not in router_tie_rule.order" % (n, row["_src"]))
        if cls_station and "station:*" not in order:
            r.bad("router_tie_rule.order has no station:* class for %s" % n)
        fm = (row.get("router") or {}).get("first_move") or {}
        if fm.get("skill") and not (Path(root) / ".claude" / "skills" / fm["skill"] / "SKILL.md").exists():
            r.bad("%s %s: first_move skill %s absent (.claude/skills/%s/SKILL.md)" % (row["_src"], n, fm["skill"], fm["skill"]))
        if fm.get("workflow") and not (Path(root) / ".claude" / "workflows" / (fm["workflow"] + ".js")).exists():
            msg = "%s %s: first_move workflow %s absent (.claude/workflows/%s.js)" % (row["_src"], n, fm["workflow"], fm["workflow"])
            (r.todo if pend else r.bad)(msg + (" [equip_pending]" if pend else ""))
        if not (fm.get("skill") or fm.get("workflow") or fm.get("inline_gather")):
            r.bad("%s %s: first_move names nothing" % (row["_src"], n))
    sk = Path(root) / "router" / "skills.json"
    if sk.exists():
        for s in _gov.load_json(sk).get("skills", []):
            r.d += 1
            if s.get("path") and not (Path(root) / s["path"]).exists() and not s.get("route_to"):
                r.bad("router/skills.json %s: path %s absent" % (s.get("id"), s["path"]))
    return r


def c_commons_drift(root, a):
    r = R()
    mp = Path(root) / "commons" / "MANIFEST.json"
    if not mp.exists():
        r.bad("commons/MANIFEST.json missing — regenerate: python3 tools/gov/gen_manifest.py --write (on main)")
        return r
    man = _gov.load_json(mp)
    files = man.get("files") or {}
    for rel, meta in sorted(files.items()):
        r.d += 1
        p = Path(root) / rel
        if not p.exists():
            r.bad("commons path %s is missing" % rel)
        elif not meta.get("generated") and _gov.sha256_file(p) != meta.get("sha256"):
            r.bad("commons path %s differs from commons/MANIFEST.json (commons files are edited on main only%s)"
                  % (rel, "; regenerate the manifest if this IS main" if _gov.station_json(root) is None else ""))
    if _gov.is_git(root):
        for ref in _gov.config(root)["gov"].get("protected_branches") or ["main"]:
            t = _gov.show(root, ref, "commons/MANIFEST.json")
            if t is None:
                continue
            try:
                theirs = json.loads(t).get("files") or {}
            except ValueError:
                r.bad("%s:commons/MANIFEST.json unreadable" % ref)
                break
            if {k: v.get("sha256") for k, v in theirs.items()} != {k: v.get("sha256") for k, v in files.items()}:
                r.todo("behind %s: commons/MANIFEST.json differs from %s's — run python3 tools/kit/sync.py" % (ref, ref))
            break
    return r


def c_main_purity(root, a):
    r = R()
    if _gov.station_json(root) is not None:
        print_extra.append("main_purity: station.json present — a station branch; nothing to assert")
        return r
    for rel in _gov.tracked_files(root):
        r.d += 1
        if _gov.station_only(rel):
            r.bad("station-only path on main: %s" % rel)
    return r


CHECKS = {
    "claudemd": c_claudemd, "station": c_station, "rules": c_rules, "canon": c_canon, "decisions": c_decisions,
    "history": c_history, "ledger": c_ledger, "ledger_owed": c_ledger_owed, "defects": c_defects,
    "defects_due": c_defects_due, "releases": c_releases, "hooks_wired": c_hooks_wired,
    "hooks_selftest": c_hooks_selftest, "hook_channels": c_hook_channels, "headers": c_headers,
    "admission": c_admission, "router_targets": c_router_targets, "commons_drift": c_commons_drift,
    "main_purity": c_main_purity,
}
WORKLIST_CHECKS = {"ledger_owed", "defects_due", "headers"}
print_extra = []


def run_check(name, root, a, quiet=False):
    del print_extra[:]
    try:
        res = CHECKS[name](root, a)
    except _gov.GovError as e:
        if not quiet:
            print("%s: UNREADABLE (%s)" % (name, e))
        return 2, None
    except (ValueError, KeyError, TypeError) as e:
        if not quiet:
            print("%s: UNREADABLE (%s: %s)" % (name, type(e).__name__, e))
        return 2, None
    if name in WORKLIST_CHECKS:
        res.w = res.w + res.v
        res.v = []
    if not quiet:
        print(_gov.headline(name, len(res.v), len(res.w), res.d))
        for v in res.v:
            print("  VIOLATION: " + v)
        for w in res.w:
            print("  WORKLIST: " + w)
        for x in print_extra:
            print("  " + x)
    return (1 if res.v else 0), res


# ---------------------------------------------------------------- selftest
def _edit_json(root, rel, fn):
    p = Path(root) / rel
    d = json.loads(p.read_text(encoding="utf-8"))
    fn(d)
    p.write_text(_gov.dump_json(d), encoding="utf-8")


def _append(root, rel, text):
    p = Path(root) / rel
    p.write_text((p.read_text(encoding="utf-8") if p.exists() else "") + text, encoding="utf-8")


def _replace(root, rel, old, new):
    p = Path(root) / rel
    t = p.read_text(encoding="utf-8")
    assert old in t, (rel, old)
    p.write_text(t.replace(old, new, 1), encoding="utf-8")


def _first_row_words(root, rel, new):
    p = Path(root) / rel
    t = p.read_text(encoding="utf-8")
    i = t.index("\nwords:", re.search(r"\n## DEC-[a-z0-9-]*\d{4} ", t).start())
    j = t.index("\n", i + 1)
    p.write_text(t[:i] + "\nwords: > " + new + t[j:], encoding="utf-8")


def _del_first_row(root, rel, prefix):
    p = Path(root) / rel
    t = p.read_text(encoding="utf-8")
    i = re.search(r"\n## %s[a-z0-9-]*\d{4} " % re.escape(prefix), t).start()
    j = t.index("\n## ", i + 1)
    p.write_text(t[:i] + t[j:], encoding="utf-8")


def _gm(root):
    gm = Path(root) / "tools" / "gov" / "gen_manifest.py"
    _gov.run([sys.executable, str(gm), "--root", str(root), "--write"], root)


def _stage_claude_line_removal(root, to_history=False, to_rules=False):
    p = Path(root) / "CLAUDE.md"
    lines = p.read_text(encoding="utf-8").splitlines(True)
    k = next(i for i, l in enumerate(lines) if len(l.strip()) >= 60 and not l.startswith("#") and "owner:" not in l)
    gone = lines.pop(k)
    p.write_text("".join(lines), encoding="utf-8")
    paths = ["CLAUDE.md"]
    if to_history:
        _append(root, "governance/HISTORY.md", "\n## 2026-10-16 · moved from CLAUDE.md § x · test\n" + gone)
        paths.append("governance/HISTORY.md")
    if to_rules:
        _gov.write(root, ".claude/rules/x.md", gone)
        paths.append(".claude/rules/x.md")
    _gov.git(root, "add", "--", *paths)


PLANTS = {
    "claudemd": [
        ("over budget", lambda r: _append(r, "CLAUDE.md", "\n" + ("y" * 100 + "\n") * 45)),
        ("disallowed section", lambda r: _append(r, "CLAUDE.md", "\n## Random notes\n")),
        ("line duplicated in an owner", lambda r: _append(r, "governance/DECISIONS.md",
         "\n" + next(l for l in (Path(r) / "CLAUDE.md").read_text().splitlines() if len(l) >= 60 and "owner:" not in l) + "\n")),
    ],
    "station": [
        ("missing gov key", lambda r: _edit_json(r, "commons/defaults.json", lambda d: d["gov"].pop("beat_s"))),
        ("non-integer threshold", lambda r: _edit_json(r, "commons/defaults.json", lambda d: d["gov"].__setitem__("ctx_warn", "150k"))),
        ("warn >= handoff", lambda r: _edit_json(r, "commons/defaults.json", lambda d: d["gov"].__setitem__("ctx_warn", 999999))),
        ("cadence not whole beats", lambda r: _edit_json(r, "commons/defaults.json", lambda d: d["gov"].__setitem__("margin_s", 61))),
        ("invalid station.json", lambda r: _gov.write(r, "station.json", json.dumps({"name": "Bad Name", "knobs": {"gov": "huge"}}))),
    ],
    "rules": [
        ("duplicate id", lambda r: _edit_json(r, "governance/rules.json", lambda d: d["rules"].append(dict(d["rules"][0])))),
        ("owner heading missing", lambda r: _edit_json(r, "governance/rules.json", lambda d: d["rules"][0].__setitem__("owner", "CLAUDE.md#No such heading"))),
        ("hook not wired", lambda r: _edit_json(r, "governance/rules.json", lambda d: d["rules"].append(dict(d["rules"][0], id="R-x", enforcement={"kind": "hook", "ref": ".claude/hooks/nope.py", "verdict": "report"}, rung="soft")))),
        ("check not registered", lambda r: _edit_json(r, "governance/rules.json", lambda d: d["rules"].append(dict(d["rules"][0], id="R-y", enforcement={"kind": "check", "ref": "no_such_check"}, rung="soft")))),
        ("owed without trigger", lambda r: _edit_json(r, "governance/rules.json", lambda d: d["rules"].append(dict(d["rules"][0], id="R-z", enforcement={"kind": "owed", "shape": "a hook"}, rung="soft")))),
        ("pointer without the id", lambda r: _edit_json(r, "governance/rules.json", lambda d: d["rules"][0].__setitem__("pointers", [".gitignore"]))),
        ("orphan wired hook", lambda r: _edit_json(r, "governance/rules.json", lambda d: d.__setitem__("rules", [x for x in d["rules"] if "stop.py" not in json.dumps(x.get("enforcement"))]))),
        ("rung disagrees", lambda r: _edit_json(r, "governance/rules.json", lambda d: [x.__setitem__("rung", "soft") for x in d["rules"] if x["id"] == "R-destructive"])),
        ("station-only owner absent on a station", lambda r: (_gov.write(r, "station.json", json.dumps({"name": "markets"})),
            _edit_json(r, "governance/rules.json", lambda d: d["rules"].append(dict(d["rules"][0], id="R-st", owner="upstream/PRECEDENCE.json#x", pointers=[]))))),
        ("excludes lack upstream CLAUDE.md", lambda r: _edit_json(r, ".claude/settings.json", lambda d: d["claudeMdExcludes"].remove("**/upstream/**/CLAUDE.md"))),
    ],
    "canon": [
        ("undeclared group", lambda r: _gov.write(r, "docs/a.md", "<!-- CANON:zz BEGIN -->\nx\n<!-- CANON:zz END -->\n")),
        ("strict copies differ", lambda r: (_edit_json(r, "governance/rules.json", lambda d: d.__setitem__("canon", {"g1": "strict"})),
                                            _gov.write(r, "docs/a.md", "<!-- CANON:g1 BEGIN -->\nalpha\n<!-- CANON:g1 END -->\n"),
                                            _gov.write(r, "docs/b.md", "<!-- CANON:g1 BEGIN -->\nbeta\n<!-- CANON:g1 END -->\n"))),
        ("lone copy", lambda r: (_edit_json(r, "governance/rules.json", lambda d: d.__setitem__("canon", {"g1": "strict"})),
                                 _gov.write(r, "docs/a.md", "# CANON:g1\nline one\nline two\n"))),
        ("copy differs from its owner", lambda r: (_gov.write(r, "tools/map/_common.py", "GEN_DECL = re.compile(r'A')\n"),
                                                   _gov.write(r, "tools/x.py", "# CANON:gen_decl\nGEN_DECL = re.compile(r'B')\n# /CANON:gen_decl\n"))),
    ],
    "decisions": [
        ("deleted row", lambda r: _del_first_row(r, "governance/DECISIONS.md", "DEC-")),
        ("edited words", lambda r: _first_row_words(r, "governance/DECISIONS.md", '"paraphrased"')),
        ("dangling superseded", lambda r: _replace(r, "governance/DECISIONS.md", "\nstatus: CURRENT\n", "\nstatus: SUPERSEDED 2026-10-17 by DEC-core-0999\n")),
        ("duplicate id", lambda r: _append(r, "governance/DECISIONS.md", "\n## DEC-core-0001 · 2026-10-16 · dup\nkind: rule\nwords: > \"x\"\nlocator: l\n")),
        ("row without locator", lambda r: _append(r, "governance/DECISIONS.md", "\n## DEC-core-0998 · 2026-10-16 · x\nkind: rule\nstatus: CURRENT\nwords: > \"x\"\n")),
    ],
    "history": [
        ("hot-path line deleted, not moved", lambda r: _stage_claude_line_removal(r)),
    ],
    "ledger": [
        ("be more careful", lambda r: _append(r, "governance/LEDGER.md", "\n## L-core-0990 — X\nkind: procedural\npathology: -\naxis: effort\nhook: NOT HOOKABLE x\namendment: be more careful\n")),
        ("missing hook", lambda r: _append(r, "governance/LEDGER.md", "\n## L-core-0991 — X\nkind: procedural\npathology: -\naxis: effort\namendment: CLAUDE.md\n")),
        ("HOOKED path missing", lambda r: _append(r, "governance/LEDGER.md", "\n## L-core-0992 — X\nkind: procedural\npathology: -\naxis: effort\nhook: HOOKED nope.py\namendment: CLAUDE.md\n")),
        ("delegation without pathology", lambda r: _append(r, "governance/LEDGER.md", "\n## L-core-0993 — X\nkind: delegation\npathology: -\naxis: judgement\nhook: NOT HOOKABLE x\namendment: CLAUDE.md\n")),
        ("deleted row", lambda r: _del_first_row(r, "governance/LEDGER.md", "L-")),
    ],
    "defects": [
        ("OPEN without trigger", lambda r: _append(r, "governance/DEFECTS.md", "\n## DEF-core-0001 · 2026-10-16 · x\nstatus: OPEN\nwhere: x\nowner: elsewhere\nwhy_not_fixed_now: other lane\n")),
        ("own defect excused by scope", lambda r: _append(r, "governance/DEFECTS.md", "\n## DEF-core-0001 · 2026-10-16 · x\nstatus: OPEN\nwhere: x\nowner: this-station\ntrigger: date: 2099-01-01\nwhy_not_fixed_now: out of scope\n")),
        ("FIXED commit unresolved", lambda r: _append(r, "governance/DEFECTS.md", "\n## DEF-core-0001 · 2026-10-16 · x\nstatus: FIXED deadbeef\nwhere: x\nowner: this-station\n")),
    ],
    "releases": [
        ("missing words", lambda r: _edit_json(r, "governance/RELEASES.json", lambda d: d["releases"].append({"id": "REL-0001", "scope": "deny_destructive", "match": "x", "locator": "l", "utc": "2026-10-16T09:00Z", "expires": "2026-10-17T09:00Z"}))),
        ("expires > 7 days", lambda r: _edit_json(r, "governance/RELEASES.json", lambda d: d["releases"].append({"id": "REL-0001", "scope": "deny_destructive", "match": "x", "words": "w", "locator": "l", "utc": "2026-10-01T09:00Z", "expires": "2026-10-30T09:00Z"}))),
        ("unknown scope", lambda r: _edit_json(r, "governance/RELEASES.json", lambda d: d["releases"].append({"id": "REL-0001", "scope": "nope", "match": "x", "words": "w", "locator": "l", "utc": "2026-10-16T09:00Z", "expires": "2026-10-17T09:00Z"}))),
    ],
    "hooks_wired": [
        ("wired script missing", lambda r: (Path(r) / ".claude/hooks/stop.py").unlink()),
        ("orphan hook", lambda r: _gov.write(r, ".claude/hooks/orphan.py", '"""orphan\nEarned by: x\n"""\n')),
        ("deny under if: filter", lambda r: _edit_json(r, ".claude/settings.json", lambda d: d["hooks"]["PreToolUse"][0]["hooks"][0].__setitem__("if", "Bash(git *)"))),
        ("dispatcher module missing", lambda r: (Path(r) / ".claude/hooks/act_gate.py").unlink()),
    ],
    "hooks_selftest": [
        ("a red hook selftest", lambda r: _gov.write(r, ".claude/hooks/stop.py", '"""stop\nEarned by: x\n"""\nimport sys\nsys.exit(1 if "--selftest" in sys.argv else 0)\n')),
    ],
    "hook_channels": [
        ("plain stdout on PostToolUse", lambda r: _gov.write(r, ".claude/hooks/context_threshold.py", '"""c\nEarned by: x\n"""\nprint("plain")\n')),
    ],
    "headers": [
        ("no header", lambda r: _gov.write(r, "docs/n.md", "# no header\n")),
        ("audit holds a number", lambda r: _gov.write(r, "docs/m.md", "# m\nowner: x · status: x · date: x · supersedes: x · audit: 12/12 green\n")),
    ],
    "admission": [
        ("empty earned_by", lambda r: _edit_json(r, "governance/checks.json", lambda d: d["checks"][0].__setitem__("earned_by", ""))),
        ("hook without Earned by", lambda r: _gov.write(r, ".claude/hooks/stop.py", '"""stop"""\nimport sys\nsys.exit(0)\n')),
        ("DENY hook without Release", lambda r: _gov.write(r, ".claude/hooks/deny_destructive.py", '"""DENY x\nEarned by: x\n"""\nimport sys\nsys.exit(0)\n')),
        ("skill description > 200 B", lambda r: _gov.write(r, ".claude/skills/closeout/SKILL.md", "---\nname: closeout\ndescription: %s\n---\n" % ("d" * 210))),
    ],
    "router_targets": [
        ("first_move skill absent", lambda r: _edit_json(r, "router/intents.json", lambda d: d["intents"][0]["router"].__setitem__("first_move", {"skill": "no-such-skill"}))),
        ("intent not in tie order", lambda r: _edit_json(r, "router/intents.json", lambda d: d["router_tie_rule"]["order"].remove("build"))),
        ("workflow absent (no equip_pending)", lambda r: _gov.write(r, "router/intents.d/station.json", json.dumps({"intents": [{"name": "edge", "description": "x", "contributed_by": "station", "router": {"keywords": ["edge"], "first_move": {"workflow": "edge-research"}}}]}))),
        ("schema: unknown contributor", lambda r: _edit_json(r, "router/intents.json", lambda d: d["intents"][0].__setitem__("contributed_by", "me"))),
    ],
    "commons_drift": [
        ("commons file edited", lambda r: _append(r, ".gitattributes", "# drift\n")),
        ("commons file missing", lambda r: (Path(r) / ".gitignore").unlink()),
    ],
    "main_purity": [
        ("station-only path on main", lambda r: _gov.write(r, "STATION.md", "# x\n")),
        ("gap skill on main", lambda r: _gov.write(r, ".claude/skills/pine-cockpit/SKILL.md", "---\nname: p\ndescription: p\n---\n")),
    ],
}
# worklist checks: the planted case must RAISE the worklist count (exit stays 0)
CLEAN_EXTRA = {
    "canon": ("a copy equal to its owner", lambda r: (_gov.write(r, "tools/map/_common.py", "GEN_DECL = re.compile(r'A')\n"),
                                                      _gov.write(r, "tools/x.py", "# CANON:gen_decl\nGEN_DECL = re.compile(r'A')\ndef f(): pass\n# /CANON:gen_decl\n"))),
    "router_targets": ("workflow absent WITH equip_pending is worklist", lambda r: (
        _gov.write(r, "router/intents.d/station.json", json.dumps({"intents": [{"name": "edge", "description": "x", "contributed_by": "station", "router": {"keywords": ["edge"], "first_move": {"workflow": "edge-research"}}}]})),
        _gov.write(r, "governance/checks.d/station.json", json.dumps({"checks": [], "equip_pending": True})))),
    "history": ("hot-path line moved to HISTORY.md", lambda r: _stage_claude_line_removal(r, to_history=True)),
    "commons_drift": ("an extra (station) file is not drift", lambda r: _gov.write(r, "notes/x.md", "x\n")),
}
CLEAN_EXTRA2 = {
    "rules": ("a station-only owner on main is not resolved", lambda r: _edit_json(r, "governance/rules.json",
              lambda d: d["rules"].append(dict(d["rules"][0], id="R-st", owner="upstream/PRECEDENCE.json#x", pointers=[])))),
    "history": ("hot-path line moved into .claude/rules/x.md in the same diff", lambda r: _stage_claude_line_removal(r, to_rules=True)),
    "defects_due": None,
}
WORKLIST_PLANTS = {
    "ledger_owed": ("an OWED row", lambda r: _append(r, "governance/LEDGER.md", "\n## L-core-0995 — X\nkind: procedural\npathology: -\naxis: effort\nhook: OWED a hook — trigger: the next miss\namendment: CLAUDE.md\n")),
    "defects_due": ("an OPEN row past its date", lambda r: _append(r, "governance/DEFECTS.md", "\n## DEF-core-0001 · 2026-10-16 · x\nstatus: OPEN\nwhere: x\nowner: elsewhere\ntrigger: date: 2001-01-01\nwhy_not_fixed_now: other lane\n")),
    "headers": PLANTS["headers"][0],
}


def build_base(td):
    base = Path(td) / "base"
    _gov.make_station(base, real_scripts=True, stub_hooks=True)
    _gm(base)
    _gov.commit_all(base, "manifest")
    return base


def selftest(names, base=None):
    fails, cases = [], 0

    class A:
        base = None
        triggers = False

    def ok(c, m):
        nonlocal cases
        cases += 1
        if not c:
            fails.append(m)

    with tempfile.TemporaryDirectory() as td:
        base = build_base(td)
        k = 0
        for name in names:
            ok(name in PLANTS or name in WORKLIST_PLANTS, "%s has no planted case (a subcommand without one is a failure)" % name)
            rc, res = run_check(name, base, A(), quiet=True)
            ok(rc == 0, "%s: clean fixture rc=%s %s" % (name, rc, res and res.v[:3]))
            clean_w = len(res.w) if res else 0
            for label, plant in PLANTS.get(name, []) if name not in WORKLIST_CHECKS else []:
                k += 1
                d = Path(td) / ("p%d" % k)
                shutil.copytree(base, d, symlinks=True)
                plant(d)
                rc, res = run_check(name, d, A(), quiet=True)
                ok(rc == 1, "%s: plant '%s' not caught (rc=%s)" % (name, label, rc))
                shutil.rmtree(d, ignore_errors=True)
            if name in WORKLIST_PLANTS:
                label, plant = WORKLIST_PLANTS[name]
                k += 1
                d = Path(td) / ("p%d" % k)
                shutil.copytree(base, d, symlinks=True)
                plant(d)
                rc, res = run_check(name, d, A(), quiet=True)
                ok(rc == 0 and res and len(res.w) > clean_w, "%s: worklist plant '%s' did not count (rc=%s)" % (name, label, rc))
                shutil.rmtree(d, ignore_errors=True)
            for extra in (CLEAN_EXTRA.get(name), CLEAN_EXTRA2.get(name)):
                if not extra:
                    continue
                label, plant = extra
                k += 1
                d = Path(td) / ("p%d" % k)
                shutil.copytree(base, d, symlinks=True)
                plant(d)
                rc, res = run_check(name, d, A(), quiet=True)
                ok(rc == 0, "%s: '%s' must stay clean (rc=%s %s)" % (name, label, rc, res and res.v[:2]))
                shutil.rmtree(d, ignore_errors=True)
        # unreadable input is exit 2, never an empty read
        d = Path(td) / "unreadable"
        shutil.copytree(base, d, symlinks=True)
        (d / "governance" / "RELEASES.json").write_text("{broken")
        if "releases" in names:
            rc, _ = run_check("releases", d, A(), quiet=True)
            ok(rc == 2, "releases on a broken file must exit 2, got %s" % rc)
    if fails:
        print("selftest FAILED (%d of %d cases)" % (len(fails), cases))
        for f in fails:
            print(" - " + f)
        return 1
    print("selftest OK (%d cases)" % cases)
    return 0


def main(argv=None):
    _gov.setup_io()
    ap = argparse.ArgumentParser(description="governance checks")
    ap.add_argument("check", nargs="?")
    ap.add_argument("--root")
    ap.add_argument("--base")
    ap.add_argument("--triggers", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    name = (a.check or "").replace("-", "_")
    if name and name not in CHECKS:
        print("gov_check: unknown check %r (one of: %s)" % (a.check, " ".join(CHECKS)))
        return 2
    if a.selftest:
        return selftest([name] if name else list(CHECKS))
    if not name:
        ap.print_usage()
        return 2
    rc, _ = run_check(name, _gov.find_root(a.root), a)
    return rc


if __name__ == "__main__":
    sys.exit(main())
