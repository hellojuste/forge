#!/usr/bin/env python3
"""upstream_checks.py — the upstream programme's audit checks, one subcommand each. Stdlib only.

Earned by: LEAN LL-03 (lettuce measured a nested upstream `.claude/skills` LISTED on the first Read of a file in its
subtree: `vendor_leak`), LL-08 (upstream kept verbatim and attributed: `provenance`, `upstream_lock`), LL-09
(licence decided before ingest: `licence_filter`), § PRECEDENCE + GOV §5 (an upstream cannot switch off a station
rail: `precedence`), KIT_PLAN §6 (telemetry rows are claims: `telemetry`) and §4.1 (offline completeness has an
honest denominator: `offline_complete`), JUDGE_2 F9 (copyleft only held unmodified beside its licence) and the
research station's CC BY-NC lane (`nc_export`).

Checks (headline `<check>: <n> violation(s) · <m> worklist · denominator <d>`; exit 0 clean, 1 violation, 2 unreadable):
  vendor_leak      MUST  every file under a lane held tree is neutralised (no `.claude/`, `.claude-plugin/`,
                         CLAUDE.md, CLAUDE.local.md, AGENTS.md, .mcp.json, hooks/hooks.json left live), and no station
                         instruction file (CLAUDE.md, .claude/rules, .claude/skills outside lanes) quotes a >= 60-char
                         line of a held upstream agent file.
  precedence       MUST  every held tree (LOCK row / tree dir on disk) has a PRECEDENCE row; `governs` and `adopted`
                         only from the closed SUBTREE vocabulary [build, code-style, test-runner, commit-format, layout];
                         `adopted` within `governs`. WORKLIST: rows whose summary_of_upstream_asks is still the stub.
  upstream_lock    MUST  40-hex sha; how in {bootstrap, repertoire, tree, copy_from:<station>}; lane consistent with how;
                         committed held root exists; LOCK sha == registry/sources.json pin when that registry exists.
  provenance       MUST  every PROVENANCE row re-hashes to its sha256; every file under a held tree has exactly one row
                         (missing or extra = violation; `_PATCHES/` and a tree-root `.env` slot are exempt).
  licence_filter   MUST  a GPL/AGPL-governed held file sits only under `upstream/<owner~repo>/` with its licence file
                         present and byte-identical to the pin; no station-authored file carries a >= 60-char line of a
                         copyleft held file.
  nc_export        MUST when station.json `nc_lane: true` (else skipped, said so): every file under nc-lane/out/
                         carries the NC-LANE stamp line; no work/ or engagements/ deliverable cites an nc-lane/ path.
  telemetry        WORKLIST rows of registry/telemetry.json with verified:false; VIOLATION a row claiming verified:true
                         with neither an evidence file+line nor a recorded offline status run.
  offline_complete WORKLIST LOCK rows `held: bootstrap` whose `.upstream/<owner~repo>.git` lacks the pinned commit.

CLI: upstream_checks.py <check> [--root <dir>] [--selftest]      (--root default: git toplevel or cwd)
     upstream_checks.py all [--root <dir>]                       (runs every check, exit = worst)
Release: none needed; a check never blocks a tool call. Fix the file, or re-run ingest.py (which writes the rows).
"""
import argparse
import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _uplib as U  # noqa: E402

LONG_LINE = 60
TEXT_EXT = {".md", ".txt", ".py", ".js", ".ts", ".json", ".yml", ".yaml", ".toml", ".sh", ".html", ".css", ".tmpl",
            ".mjs", ".cjs", ".tsx", ".jsx", ".php", ".rb", ".go", ".rs", ".java", ".sql", ".cfg", ".ini", ".env", ""}


# ---------------------------------------------------------------- shared readers
def _up(root, name):
    return U.load_json(Path(root) / "upstream" / name, None)


def lock_rows(root):
    return U.rows_of(_up(root, "LOCK.json"))


def prov_rows(root):
    return U.rows_of(_up(root, "PROVENANCE.json"))


def prec_rows(root):
    return U.rows_of(_up(root, "PRECEDENCE.json"), "trees")


def lane_files(root):
    """Every file under a lane directory (relative posix paths)."""
    root = Path(root)
    out = []
    for lane in U.LANES:
        if (root / lane).is_dir():
            out += [lane + "/" + p for p in U.walk_files(root / lane)]
    return sorted(out)


def held_tree_files(root):
    return [p for p in lane_files(root) if U.tree_of(p) and not U.exempt_in_tree(p)]


def _read_text(p, limit=2_000_000):
    try:
        b = Path(p).read_bytes()
    except OSError:
        return None
    if len(b) > limit or b"\0" in b[:4096]:
        return None
    return b.decode("utf-8", "replace")


def _long_lines(text):
    """Lines that can carry copyleft expression: >= LONG_LINE chars AND >= LONG_LINE // 2 letters/digits.
    A comment ruler (`# ------...`) or box-drawing line is long but carries no expression; counting it made every
    station file with a ruler "carry a line of copyleft" (fix2-commons trial assembly: tools/gov/_gov.py vs
    upstream/frappe~erpnext/.agents/skills/accounts-code-review/scripts/pr_ledger.py)."""
    return {l.strip() for l in text.splitlines()
            if len(l.strip()) >= LONG_LINE and sum(c.isalnum() for c in l) >= LONG_LINE // 2}


def station_authored_files(root):
    """Files outside lanes, registries and generated notices: what the station itself wrote."""
    out = []
    for p in U.walk_files(root):
        top = p.split("/", 1)[0]
        if top in U.LANES or p.startswith("upstream/") or p in ("NOTICE.md",):
            continue
        if Path(p).suffix.lower() not in TEXT_EXT:
            continue
        out.append(p)
    return out


def instruction_files(root):
    out = []
    for p in U.walk_files(root):
        if p.split("/", 1)[0] in U.LANES:
            continue
        if p == "CLAUDE.md" or p.startswith(".claude/rules/") or (p.startswith(".claude/skills/") and p.endswith(".md")):
            out.append(p)
    return out


# ---------------------------------------------------------------- vendor_leak
def check_vendor_leak(root):
    root = Path(root)
    files = lane_files(root)
    viol, work = [], []
    agent_lines = {}
    for p in files:
        rel_in_lane = p.split("/", 1)[1] if "/" in p else p
        r = U.leak_reason(rel_in_lane)
        if r and not U.exempt_in_tree(p):
            viol.append("%s: %s (re-ingest with tools/upstream/ingest.py; it renames)" % (p, r))
        parts = p.split("/")
        if any(x in ("_upstream_claude", "_upstream_claude-plugin") for x in parts) or parts[-1] in (
                "_upstream_CLAUDE.md", "_upstream_AGENTS.md", "_upstream_CLAUDE.local.md"):
            t = _read_text(root / p)
            if t:
                for l in _long_lines(t):
                    agent_lines.setdefault(l, p)
    if agent_lines:
        for f in instruction_files(root):
            t = _read_text(root / f) or ""
            for l in _long_lines(t):
                if l in agent_lines:
                    viol.append("%s quotes upstream agent text from %s: %.70s..." % (f, agent_lines[l], l))
                    break
    st = U.station_json(root) or {}
    settings = U.load_json(root / ".claude" / "settings.json", {}) or {}
    ex = settings.get("claudeMdExcludes", [])
    if (root / ".claude" / "settings.json").exists():
        for need in ("**/_upstream_claude/**",):
            if need not in ex:
                work.append(".claude/settings.json claudeMdExcludes lacks %s (second layer; owner commons-gov)" % need)
    return U.finish("vendor_leak", viol, work, len([p for p in files if U.tree_of(p)]))


# ---------------------------------------------------------------- precedence
def held_trees_on_disk(root):
    out = set()
    for p in lane_files(root):
        t = U.tree_of(p)
        if t:
            out.add(t)
    return out


def check_precedence(root):
    root = Path(root)
    obj = _up(root, "PRECEDENCE.json")
    rows = prec_rows(root)
    viol, work = [], []
    if obj is not None and obj.get("default", "station") != "station":
        viol.append("PRECEDENCE.json default is %r; only 'station' is allowed (kit floor, GOV 5)" % obj.get("default"))
    byp = {}
    for r in rows:
        p = r.get("path")
        if not p:
            viol.append("PRECEDENCE row without path: %s" % json.dumps(r)[:80])
            continue
        if p in byp:
            viol.append("PRECEDENCE path doubled: %s" % p)
        byp[p] = r
        gov = r.get("governs", [])
        if not isinstance(gov, list):
            viol.append("%s: governs must be a list" % p)
            gov = []
        for g in gov:
            if g not in U.GOVERNS_VOCAB:
                viol.append("%s: governs %r is outside the SUBTREE vocabulary %s (an upstream never governs a kit-floor concern)"
                            % (p, g, list(U.GOVERNS_VOCAB)))
        for a in r.get("adopted", []) or []:
            if a not in gov:
                viol.append("%s: adopted %r not in governs" % (p, a))
        if (r.get("summary_of_upstream_asks") or "").strip() in ("", U.TODO_PARAPHRASE):
            work.append("%s: summary_of_upstream_asks still '%s' (paraphrase the upstream agent files)" % (p, U.TODO_PARAPHRASE))
        if r.get("loaded", "never-auto").split(" ")[0] != "never-auto":
            viol.append("%s: loaded must be never-auto (LL-03)" % p)
    need = set(held_trees_on_disk(root))
    for l in lock_rows(root):
        if l.get("held") == "bootstrap":
            need.add(l.get("held_root") or ".upstream/%s.git" % l.get("repo", "").replace("/", "~"))
        elif l.get("held_root"):
            need.add(l["held_root"])
    for t in sorted(need):
        if t not in byp:
            viol.append("held tree %s has no PRECEDENCE row (ingest.py writes the stub)" % t)
    return U.finish("precedence", viol, work, len(need | set(byp)))


# ---------------------------------------------------------------- upstream_lock
def load_sources(root):
    obj = U.load_json(Path(root) / "registry" / "sources.json", None)
    if obj is None:
        return None
    rows = U.rows_of(obj, "sources", "repos")
    pins = {}
    for r in rows:
        repo = r.get("repo") or r.get("owner_repo") or r.get("full_name") or r.get("name")
        if not repo and r.get("owner") and r.get("repo_name"):
            repo = r["owner"] + "/" + r["repo_name"]
        sha = r.get("sha") or r.get("pin") or r.get("sha40")
        if repo and sha:
            pins[repo.replace("~", "/")] = sha
    return pins


def check_upstream_lock(root):
    root = Path(root)
    rows = lock_rows(root)
    pins = load_sources(root)
    viol, work = [], []
    st = U.station_json(root) or {}
    seen = set()
    for r in rows:
        tag = "%s %s/%s" % (r.get("repo"), r.get("how"), r.get("lane"))
        k = (r.get("repo"), r.get("how"), r.get("lane"), r.get("copy_of"))
        if k in seen:
            viol.append("%s: duplicate LOCK row" % tag)
        seen.add(k)
        if not re.fullmatch(r"[0-9a-f]{40}", str(r.get("sha", ""))):
            viol.append("%s: sha %r is not 40-hex" % (tag, r.get("sha")))
        how = str(r.get("how", ""))
        lane = r.get("lane")
        if not (how in U.HOW_VALUES or re.fullmatch(r"copy_from:[a-z][a-z0-9-]*", how)):
            viol.append("%s: how %r not in bootstrap|repertoire|tree|copy_from:<station>" % (tag, how))
        if how == "bootstrap":
            if lane not in (None, "", "null"):
                viol.append("%s: a bootstrap row holds no lane" % tag)
            if r.get("held") != "bootstrap":
                viol.append("%s: how bootstrap must be held: bootstrap" % tag)
        else:
            if lane not in U.LANES:
                viol.append("%s: lane %r not one of %s" % (tag, lane, list(U.LANES)))
            if how == "repertoire" and lane not in ("repertoire", "nc-lane"):
                viol.append("%s: how repertoire holds only in repertoire/ or nc-lane/" % tag)
            if how == "tree" and lane == "repertoire":
                viol.append("%s: a whole tree goes to upstream/ or study/, not repertoire/" % tag)
            if how.startswith("copy_from:"):
                if not r.get("copy_of"):
                    viol.append("%s: copy_from row without copy_of" % tag)
                elif how.split(":", 1)[1] != r.get("copy_of"):
                    viol.append("%s: copy_of %r differs from how %r" % (tag, r.get("copy_of"), how))
                elif st.get("name") and r.get("copy_of") == st.get("name"):
                    viol.append("%s: a station cannot copy from itself" % tag)
            if r.get("held") not in ("committed", "sparse-committed"):
                viol.append("%s: held %r (committed|sparse-committed for a lane row)" % (tag, r.get("held")))
            slug = str(r.get("repo", "")).replace("/", "~")
            want = "%s/%s/" % (lane, slug)
            if r.get("held_root") and r["held_root"] != want:
                viol.append("%s: held_root %s, expected %s" % (tag, r["held_root"], want))
            if not (root / want).is_dir():
                viol.append("%s: held root %s missing on disk" % (tag, want))
        if pins is not None:
            pin = pins.get(str(r.get("repo")))
            if pin is None:
                work.append("%s: repo not in registry/sources.json" % tag)
            elif pin != r.get("sha"):
                viol.append("%s: LOCK sha %s != registry/sources.json pin %s (repin with tools/kit/repin.py)" % (tag, r.get("sha"), pin))
    lanes_on_disk = held_trees_on_disk(root)
    roots = {r.get("held_root") for r in rows}
    for t in sorted(lanes_on_disk - roots):
        viol.append("tree %s on disk has no LOCK row" % t)
    return U.finish("upstream_lock", viol, work, len(rows))


# ---------------------------------------------------------------- provenance
def check_provenance(root):
    root = Path(root)
    rows = prov_rows(root)
    viol, work = [], []
    seen = {}
    for r in rows:
        p = r.get("path", "")
        if p in seen:
            viol.append("%s: doubled PROVENANCE row" % p)
        seen[p] = r
        f = root / p
        if not f.is_file():
            viol.append("%s: PROVENANCE row but file missing" % p)
            continue
        if U.sha256_file(f) != r.get("sha256"):
            viol.append("%s: sha256 differs from PROVENANCE (an upstream file was edited in place; patches go to _PATCHES/)" % p)
        if not re.fullmatch(r"[0-9a-f]{40}", str(r.get("sha", ""))):
            viol.append("%s: sha %r not 40-hex" % (p, r.get("sha")))
    for p in held_tree_files(root):
        if p not in seen:
            viol.append("%s: file under a held tree with no PROVENANCE row (extra)" % p)
    return U.finish("provenance", viol, work, len(set(seen) | set(held_tree_files(root))))


# ---------------------------------------------------------------- licence_filter
def check_licence_filter(root):
    root = Path(root)
    rows = prov_rows(root)
    viol, work = [], []
    cls_cache = {}

    def lic_of(lp):
        if lp not in cls_cache:
            t = _read_text(root / lp) if lp else None
            cls_cache[lp] = U.classify_licence(t) if t is not None else None
        return cls_cache[lp]

    prov = {r["path"]: r for r in rows if r.get("path")}
    copyleft_lines = {}
    n = 0
    for r in rows:
        p, lp = r.get("path", ""), r.get("licence_file")
        if r.get("role") in ("licence", "notice"):
            continue
        n += 1
        if not lp:
            work.append("%s: no governing licence file recorded" % p)
            continue
        cls = lic_of(lp)
        if cls is None:
            viol.append("%s: governing licence file %s is missing" % (p, lp))
            continue
        if not U.is_copyleft(cls):
            continue
        parts = p.split("/")
        if parts[0] != "upstream" or len(parts) < 3 or "~" not in parts[1]:
            viol.append("%s: %s-governed file outside upstream/<owner~repo>/ (copyleft is held only unmodified beside its licence)" % (p, cls))
        lrow = prov.get(lp)
        if not lrow:
            viol.append("%s: licence file %s has no PROVENANCE row (cannot prove it is the pinned text)" % (p, lp))
        elif (root / lp).is_file() and U.sha256_file(root / lp) != lrow.get("sha256"):
            viol.append("%s: licence file %s differs from the pin" % (p, lp))
        t = _read_text(root / p)
        if t:
            for l in _long_lines(t):
                copyleft_lines.setdefault(l, p)
    if copyleft_lines:
        for f in station_authored_files(root):
            t = _read_text(root / f)
            if not t:
                continue
            for l in _long_lines(t):
                if l in copyleft_lines:
                    viol.append("%s carries a line of copyleft %s: %.60s..." % (f, copyleft_lines[l], l))
                    break
    return U.finish("licence_filter", viol, work, n)


# ---------------------------------------------------------------- nc_export
def check_nc_export(root):
    root = Path(root)
    st = U.station_json(root) or {}
    if st.get("nc_lane") is not True:
        print("nc_export: 0 violation(s) · 0 worklist · denominator 0")
        print("  skipped: station.json nc_lane is not true (check applies to the research station's CC BY-NC lane)")
        return 0
    viol, work = [], []
    outs = []
    out_dir = root / "nc-lane" / "out"
    if out_dir.is_dir():
        outs = ["nc-lane/out/" + p for p in U.walk_files(out_dir)]
    for p in outs:
        t = _read_text(root / p) or ""
        if not U.NC_STAMP_RE.search(t):
            viol.append("%s: missing stamp line '%s'" % (p, U.NC_STAMP))
    deliv = []
    for top in ("work", "engagements"):
        if (root / top).is_dir():
            deliv += [top + "/" + p for p in U.walk_files(root / top)]
    for p in deliv:
        t = _read_text(root / p) or ""
        if re.search(r"(?<![\w-])nc-lane/", t):
            viol.append("%s cites an nc-lane/ path (non-commercial material never feeds a deliverable)" % p)
    return U.finish("nc_export", viol, work, len(outs) + len(deliv))


# ---------------------------------------------------------------- telemetry
def telemetry_rows(root):
    root = Path(root)
    rows = []
    for rel in ("registry/telemetry.json", "upstream/TELEMETRY.json"):
        obj = U.load_json(root / rel, None)
        rows += [dict(r, _src=rel) for r in U.rows_of(obj, "telemetry", "tools")]
    return rows


def check_telemetry(root):
    rows = telemetry_rows(root)
    viol, work = [], []
    for r in rows:
        tool = r.get("tool") or r.get("repo") or r.get("name") or "?"
        if r.get("verified") is True:
            ev = r.get("evidence") or r.get("evidence_path")
            line = r.get("evidence_line") or (re.search(r":\d+", str(ev or "")) is not None)
            run = r.get("verified_by_run") or r.get("status_command_run")
            if not ((ev and line) or run):
                viol.append("%s (%s): verified:true with no evidence file+line and no recorded offline status run" % (tool, r["_src"]))
        else:
            work.append("%s: verified:false — opt-out switch %s unproven (evidence: %s)"
                        % (tool, r.get("opt_out") or r.get("switch") or "unknown", r.get("evidence") or r.get("evidence_path") or "none"))
    return U.finish("telemetry", viol, work, len(rows))


# ---------------------------------------------------------------- offline_complete
def upstream_cache(root):
    """The shared bootstrap cache (tools/kit/_kit.upstream_cache: $STABLE_KIT_UPSTREAM, else the main checkout's
    .upstream/ seen from every linked station worktree); <root>/.upstream when tools/kit is not present."""
    kp = Path(root) / "tools" / "kit" / "_kit.py"
    if kp.exists():
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("_kit_for_upstream_checks", str(kp))
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            return Path(m.upstream_cache(str(root)))
        except Exception:  # noqa: BLE001 -- fall back to the per-root cache, named in the headline row
            pass
    return Path(root) / ".upstream"


def check_offline_complete(root):
    root = Path(root)
    rows = [r for r in lock_rows(root) if r.get("held") == "bootstrap"]
    viol, work = [], []
    cache = upstream_cache(root) if rows else root / ".upstream"
    for r in rows:
        slug = str(r.get("repo", "")).replace("/", "~")
        bare = cache / ("%s.git" % slug)
        if not bare.is_dir():
            work.append("%s: %s/%s.git absent (run python3 tools/kit/bootstrap.py %s)" % (r.get("repo"), cache, slug, slug))
            continue
        p = subprocess.run(["git", "-C", str(bare), "cat-file", "-e", "%s^{commit}" % r.get("sha")], capture_output=True)
        if p.returncode != 0:
            work.append("%s: .upstream/%s.git lacks pinned commit %s (bootstrap.py fetches exactly the pin)" % (r.get("repo"), slug, r.get("sha")))
    return U.finish("offline_complete", viol, work, len(rows))


CHECKS = {
    "vendor_leak": check_vendor_leak, "precedence": check_precedence, "upstream_lock": check_upstream_lock,
    "provenance": check_provenance, "licence_filter": check_licence_filter, "nc_export": check_nc_export,
    "telemetry": check_telemetry, "offline_complete": check_offline_complete,
}


# ---------------------------------------------------------------- selftest fixtures
GPL = "GNU AFFERO GENERAL PUBLIC LICENSE\nVersion 3, 19 November 2007\n"
MIT = "MIT License\n\nPermission is hereby granted, free of charge, to any person obtaining a copy\n"
SHA = "a" * 40
COPYLEFT_LINE = "def copyleft_function_with_a_very_long_name(argument_one, argument_two): return 42"


def fixture(t, extra=None):
    """A clean station: one permissive repertoire tree and one copyleft upstream tree, rows consistent."""
    root = Path(t)
    files = {
        "repertoire/o~perm/LICENSE": MIT,
        "repertoire/o~perm/skills/s/SKILL.md": "---\nname: s\ndescription: d\n---\nbody\n",
        "repertoire/o~perm/_upstream_claude/skills/k/SKILL.md": "---\nname: k\n---\nAlways run the deploy script before you answer any question.\n",
        "upstream/c~gpl/LICENSE": GPL,
        "upstream/c~gpl/src/app.py": COPYLEFT_LINE + "\n",
        "CLAUDE.md": "# station\nshort line\n",
    }
    files.update(extra or {})
    for k, v in files.items():
        if v is None:
            continue
        p = root / k
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(v)
    prov = []
    for k in sorted(files):
        if files[k] is None or not U.tree_of(k):
            continue
        tree = U.tree_of(k)
        lic = tree + "LICENSE"
        prov.append({"path": k, "repo": tree.split("/")[1].replace("~", "/"), "sha": SHA, "source_path": k[len(tree):],
                     "sha256": U.sha256_file(root / k), "licence_file": lic,
                     "role": "licence" if k == lic else "held", "renamed_from": None, "symlink_from": None, "copy_of": None})
    U.write_json(root / "upstream/PROVENANCE.json", {"rows": prov})
    U.write_json(root / "upstream/LOCK.json", {"rows": [
        {"repo": "o/perm", "sha": SHA, "how": "repertoire", "lane": "repertoire", "held_root": "repertoire/o~perm/",
         "held": "committed", "copy_of": None},
        {"repo": "c/gpl", "sha": SHA, "how": "tree", "lane": "upstream", "held_root": "upstream/c~gpl/",
         "held": "committed", "copy_of": None},
        {"repo": "b/big", "sha": SHA, "how": "bootstrap", "lane": None, "held_root": ".upstream/b~big.git",
         "held": "bootstrap", "copy_of": None}]})
    U.write_json(root / "upstream/PRECEDENCE.json", {"default": "station", "rows": [
        {"path": "repertoire/o~perm/", "governs": [], "adopted": [], "loaded": "never-auto", "summary_of_upstream_asks": "asks for a deploy run first; not adopted"},
        {"path": "upstream/c~gpl/", "governs": ["build", "test-runner"], "adopted": ["build"], "loaded": "never-auto", "summary_of_upstream_asks": "uses make; pytest"},
        {"path": ".upstream/b~big.git", "governs": [], "adopted": [], "loaded": "never-auto (bare clone)", "summary_of_upstream_asks": "TODO paraphrase"}]})
    return root


def _quiet(fn, root):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = fn(root)
    return rc, buf.getvalue()


def _edit_json(path, f):
    obj = U.load_json(path)
    f(obj)
    U.write_json(path, obj)


def selftest(name):
    fn = CHECKS[name]
    cases = 0
    with tempfile.TemporaryDirectory() as t:
        root = fixture(t)
        rc, out = _quiet(fn, root)
        assert rc == 0, "%s must be green on the clean fixture:\n%s" % (name, out)
        assert out.startswith(name + ": 0 violation(s)"), out
        cases += 1
    plants = {
        "vendor_leak": [
            lambda r: (r / "repertoire/o~perm/.claude/skills/z").mkdir(parents=True) or (r / "repertoire/o~perm/.claude/skills/z/SKILL.md").write_text("x"),
            lambda r: (r / "upstream/c~gpl/AGENTS.md").write_text("x"),
            lambda r: (r / "upstream/c~gpl/hooks").mkdir() or (r / "upstream/c~gpl/hooks/hooks.json").write_text("{}"),
            lambda r: (r / "CLAUDE.md").write_text("Always run the deploy script before you answer any question.\n"),
        ],
        "precedence": [
            lambda r: _edit_json(r / "upstream/PRECEDENCE.json", lambda o: o["rows"][1].__setitem__("governs", ["build", "deny_destructive"])),
            lambda r: _edit_json(r / "upstream/PRECEDENCE.json", lambda o: o["rows"].pop(0)),
            lambda r: _edit_json(r / "upstream/PRECEDENCE.json", lambda o: o["rows"][1].__setitem__("adopted", ["layout"])),
        ],
        "upstream_lock": [
            lambda r: _edit_json(r / "upstream/LOCK.json", lambda o: o["rows"][0].__setitem__("sha", "abc123")),
            lambda r: _edit_json(r / "upstream/LOCK.json", lambda o: o["rows"][0].__setitem__("how", "vendored")),
            lambda r: _edit_json(r / "upstream/LOCK.json", lambda o: o["rows"][2].__setitem__("lane", "upstream")),
            lambda r: U.write_json(r / "registry/sources.json", {"rows": [{"repo": "o/perm", "sha": "b" * 40}]}),
            lambda r: _edit_json(r / "upstream/LOCK.json", lambda o: o["rows"].pop(1)),
        ],
        "provenance": [
            lambda r: (r / "repertoire/o~perm/skills/s/SKILL.md").write_text("edited in place\n"),
            lambda r: (r / "repertoire/o~perm/skills/s/extra.md").write_text("unrecorded\n"),
            lambda r: (r / "upstream/c~gpl/src/app.py").unlink(),
        ],
        "licence_filter": [
            lambda r: (r / "tools").mkdir() or (r / "tools/mine.py").write_text("# mine\n" + COPYLEFT_LINE + "\n"),
            lambda r: (r / "upstream/c~gpl/LICENSE").write_text(GPL + "amended\n"),
            lambda r: _edit_json(r / "upstream/PROVENANCE.json", lambda o: o["rows"].append(
                {"path": "study/c~gpl/x.py", "sha": SHA, "sha256": "0", "licence_file": "upstream/c~gpl/LICENSE", "role": "held"})),
        ],
        "telemetry": [
            lambda r: U.write_json(r / "registry/telemetry.json", {"rows": [{"tool": "evo", "verified": True}]}),
        ],
        "nc_export": [
            lambda r: (r / "nc-lane/out").mkdir(parents=True) or (r / "nc-lane/out/review.md").write_text("no stamp\n"),
            lambda r: (r / "work").mkdir() or (r / "work/deliverable.md").write_text("see nc-lane/out/review.md\n"),
        ],
        "offline_complete": [],
    }
    for plant in plants[name]:
        with tempfile.TemporaryDirectory() as t:
            root = fixture(t)
            if name == "nc_export":
                U.write_json(root / "station.json", {"name": "research", "nc_lane": True})
            plant(root)
            rc, out = _quiet(fn, root)
            assert rc == 1, "%s must be red on planted defect #%d:\n%s" % (name, cases, out)
            cases += 1
    # worklist-class behaviour
    with tempfile.TemporaryDirectory() as t:
        root = fixture(t)
        if name == "precedence":
            rc, out = _quiet(fn, root)
            assert rc == 0 and "1 worklist" in out.splitlines()[0], out
            cases += 1
        if name == "licence_filter":  # a shared comment ruler is not copyleft expression
            ruler = "# " + "-" * 76
            with tempfile.TemporaryDirectory() as t2:
                r2 = fixture(t2, {"upstream/c~gpl/src/app.py": COPYLEFT_LINE + "\n" + ruler + "\n", "tools/mine.py": "# mine\n" + ruler + "\n"})
                rc, out = _quiet(fn, r2)
                assert rc == 0, ("a shared ruler line must not count as copyleft", out)
            cases += 1
        if name == "telemetry":
            U.write_json(root / "registry/telemetry.json", {"rows": [
                {"tool": "evo", "verified": False, "opt_out": "unknown"},
                {"tool": "openwiki", "verified": True, "evidence": "src/telemetry.ts:12", "opt_out": "OPENWIKI_TELEMETRY_DISABLED=1"}]})
            rc, out = _quiet(fn, root)
            assert rc == 0 and "1 worklist" in out.splitlines()[0], out
            cases += 1
        if name == "nc_export":
            rc, out = _quiet(fn, root)
            assert rc == 0 and "skipped" in out, out
            U.write_json(root / "station.json", {"name": "research", "nc_lane": True})
            (root / "nc-lane/out").mkdir(parents=True)
            (root / "nc-lane/out/r.md").write_text("# r\n" + U.NC_STAMP + "\n")
            rc, out = _quiet(fn, root)
            assert rc == 0, out
            cases += 2
        if name == "offline_complete":
            rc, out = _quiet(fn, root)
            assert rc == 0 and "1 worklist" in out.splitlines()[0], ("absent bare clone is WORKLIST", out)
            src = root.parent / (root.name + "_src")
            src.mkdir()
            subprocess.run(["git", "-C", str(src), "init", "-q"], check=True)
            (src / "f").write_text("x")
            subprocess.run(["git", "-C", str(src), "add", "f"], check=True)
            subprocess.run(["git", "-C", str(src), "-c", "user.name=kit", "-c", "user.email=kit@localhost", "commit", "-qm", "f"], check=True)
            sha = subprocess.run(["git", "-C", str(src), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
            subprocess.run(["git", "clone", "-q", "--bare", str(src), str(root / ".upstream/b~big.git")], check=True)
            _edit_json(root / "upstream/LOCK.json", lambda o: o["rows"][2].__setitem__("sha", sha))
            rc, out = _quiet(fn, root)
            assert rc == 0 and "0 worklist" in out.splitlines()[0], ("pinned commit present", out)
            _edit_json(root / "upstream/LOCK.json", lambda o: o["rows"][2].__setitem__("sha", "c" * 40))
            rc, out = _quiet(fn, root)
            assert rc == 0 and "1 worklist" in out.splitlines()[0], ("missing pinned commit is WORKLIST", out)
            # REPRODUCE F4 (main-kittools handover): the cache is the kit's shared one, not <root>/.upstream
            _edit_json(root / "upstream/LOCK.json", lambda o: o["rows"][2].__setitem__("sha", sha))
            shared = root.parent / (root.name + "_shared")
            shutil_mv = __import__("shutil").move
            shared.mkdir()
            shutil_mv(str(root / ".upstream/b~big.git"), str(shared / "b~big.git"))
            (root / "tools/kit").mkdir(parents=True, exist_ok=True)
            (root / "tools/kit/_kit.py").write_text("def upstream_cache(root):\n    return %r\n" % str(shared))
            rc, out = _quiet(fn, root)
            assert rc == 0 and "0 worklist" in out.splitlines()[0], ("the shared cache is read", out)
            __import__("shutil").rmtree(str(root / "tools/kit"))
            __import__("shutil").rmtree(str(shared))
            cases += 4
            import shutil
            shutil.rmtree(src)
    # an empty tree (main, no lanes) is green with denominator 0
    with tempfile.TemporaryDirectory() as t:
        rc, out = _quiet(fn, Path(t))
        assert rc == 0, out
        cases += 1
    print("%s selftest OK (%d cases)" % (name, cases))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("check", choices=sorted(CHECKS) + ["all"])
    ap.add_argument("--root")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    names = sorted(CHECKS) if a.check == "all" else [a.check]
    worst = 0
    for n in names:
        try:
            rc = selftest(n) if a.selftest else CHECKS[n](U.find_root(a.root))
        except AssertionError as e:
            print("%s selftest FAILED: %s" % (n, e))
            rc = 1
        except (OSError, ValueError) as e:
            print("%s: UNREADABLE %s" % (n, e))
            rc = 2
        worst = max(worst, rc)
    return worst


if __name__ == "__main__":
    sys.exit(main())
