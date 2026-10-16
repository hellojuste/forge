#!/usr/bin/env python3
"""repin.py - move one upstream to a new sha, with the evidence first.

Earned by: an upstream can change under a pin bump in the ways that matter most
and show least: a licence swap (copyleft arriving in a held tree), new agent
files (CLAUDE.md / AGENTS.md / .claude/ / hooks.json / .mcp.json) that would
lazy-load, new telemetry, or a repo repurposed to something else (AIHawk became
invisible_dots). A pin moved without a report ships those silently.
Retires: hand edits of registry/sources.json.

  repin.py --report <owner~repo> <new-sha> [--root R] [--no-fetch] [--paths p ...]
      needs the bare clone <cache>/<owner~repo>.git (tools/kit/bootstrap.py; shared cache);
      fetches the new sha (unless --no-fetch), then reports:
        1 path-scoped diff --stat for the held paths (station LOCK rows, or --paths)
        2 LICENSE blob diff (any licence file change STOPS)
        3 new agent / hooks / MCP files
        4 telemetry grep over changed files
        5 repurposed check: README first paragraph diff
        6 the station certain tests to run before --apply
      exit 0 green · 1 a STOP item · 2 usage/missing clone
  repin.py --apply <owner~repo> <new-sha> [--root R]
      re-runs the report; only when green: on main rewrites registry/sources.json
      (sha, last_commit); on a station worktree (station.json present) rewrites
      that repo's upstream/LOCK.json rows. Prints the re-ingest command.
  repin.py --check [--root R]   every LOCK row (this station, or every station
      branch when run on main) equals its registry pin; exit 1 on a mismatch.
  repin.py --selftest
"""
import argparse
import json
import os
import re
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _kit  # noqa: E402
import bootstrap  # noqa: E402

AGENT_FILE = re.compile(r"(^|/)(CLAUDE\.md|CLAUDE\.local\.md|AGENTS\.md|\.mcp\.json|hooks/hooks\.json)$|(^|/)\.claude(-plugin)?/")
LICENCE_FILE = re.compile(r"(^|/)(LICEN[CS]E[^/]*|COPYING[^/]*|license\.txt|NOTICE[^/]*|THIRD_PARTY_NOTICES[^/]*)$", re.I)
TELEMETRY = r"telemetry|posthog|sentry|mixpanel|segment\.io|amplitude|analytics|DO_NOT_TRACK"


def lock_rows(doc):
    if isinstance(doc, list):
        return doc
    for k in ("rows", "lock", "LOCK", "entries"):
        if isinstance(doc.get(k), list):
            return doc[k]
    return []


def row_key(r):
    return r.get("key") or str(r.get("repo", "")).replace("/", "~")


def station_locks(root):
    """[(station, rows)] from this worktree's upstream/LOCK.json, or every station branch."""
    out = []
    lp = os.path.join(root, "upstream", "LOCK.json")
    if os.path.isfile(os.path.join(root, "station.json")):
        st = _kit.read_json(os.path.join(root, "station.json")).get("name", "station")
        out.append((st, lock_rows(_kit.read_json(lp)) if os.path.isfile(lp) else []))
        return out
    # REPRODUCE F2: local, remote-tracking and hosted claude/stable-kit-* station refs
    try:
        refs = _kit.station_refs(root, _kit.known_stations(root))
    except _kit.KitError:
        refs = {}
    for st, ref in refs.items():
        t = _kit.git(root, "show", "%s:upstream/LOCK.json" % ref, check=False)
        rows = lock_rows(json.loads(t.out)) if t.returncode == 0 else []
        out.append((st, rows))
    return out


def readme_first_paragraph(bare, sha):
    for name in ("README.md", "README.rst", "README", "readme.md"):
        p = _kit.run(["git", "-C", bare, "show", "%s:%s" % (sha, name)], check=False)
        if p.returncode == 0:
            paras = [x.strip() for x in re.split(r"\n\s*\n", p.out)]
            for para in paras:
                if para and not para.startswith(("#", "<", "[!", "![", "[![", "---", "|")):
                    return para
            return ""
    return ""


def report(root, key, new, fetch=True, paths=None, log=print):
    src = {s["key"]: s for s in _kit.read_json(os.path.join(root, "registry", "sources.json"))["sources"]}
    if key not in src:
        log("repin: %s is not a registry key" % key)
        return 2, {}
    old = src[key]["sha"]
    bare = bootstrap.bare_path(root, key)
    if not bootstrap.has_pin(bare, old):
        log("repin: no bare clone with the old pin; run python3 tools/kit/bootstrap.py %s" % key)
        return 2, {}
    if fetch and not bootstrap.has_pin(bare, new):
        _kit.run(["git", "-C", bare, "fetch", "-q", "--no-tags", "origin", new], check=False)
    if not bootstrap.has_pin(bare, new):
        log("repin: new sha %s not in %s" % (new, bare))
        return 2, {}
    g = lambda *a: _kit.run(["git", "-C", bare] + list(a), check=False).out
    stops, notes = [], []
    held = list(paths or [])
    if not held:
        for st, rows in station_locks(root):
            for r in rows:
                if row_key(r) == key:
                    for p in (r.get("paths") or ([r["path"]] if r.get("path") else [])):
                        held.append(p)
    held = sorted(set(held))
    log("repin report %s %s -> %s" % (key, old[:12], new[:12]))
    stat = g("diff", "--stat=120", old, new, "--", *held) if held else g("diff", "--shortstat", old, new)
    log("1 held-path diff (%s):\n%s" % ("%d held path(s)" % len(held) if held else "no LOCK rows: whole repo", stat.rstrip() or "  (no change)"))
    ns = [l.split("\t") for l in g("diff", "--name-status", "--no-renames", old, new).splitlines() if l]
    lic = [(s, p) for s, p in ns if LICENCE_FILE.search(p)]
    for s, p in lic:
        stops.append("licence/notice file %s: %s" % ({"A": "added", "D": "deleted", "M": "changed"}.get(s, s), p))
    log("2 licence blobs: %s" % ("; ".join("%s %s" % x for x in lic) if lic else "unchanged"))
    agents = [p for s, p in ns if s == "A" and AGENT_FILE.search(p)]
    for p in agents:
        notes.append("new agent/hook/MCP file: %s (ingest renames it; never wire it)" % p)
    log("3 new agent/hooks/MCP files: %s" % (", ".join(agents) or "none"))
    changed = [p for s, p in ns if s in ("A", "M")]
    tel = []
    if changed:
        tel = [l for l in g("grep", "-l", "-i", "-E", TELEMETRY, new, "--", *changed[:2000]).splitlines() if l]
    if tel:
        notes.append("telemetry terms in %d changed file(s): re-check registry/telemetry.json rows" % len(tel))
    log("4 telemetry grep over %d changed file(s): %s" % (len(changed), ", ".join(t.split(":", 1)[-1] for t in tel[:10]) or "none"))
    a, b = readme_first_paragraph(bare, old), readme_first_paragraph(bare, new)
    if a != b:
        stops.append("README first paragraph changed (repurposed?) - read it before applying")
        log("5 README first paragraph CHANGED:\n  old: %s\n  new: %s" % (a[:300], b[:300]))
    else:
        log("5 README first paragraph unchanged")
    sts = sorted({st for st, rows in station_locks(root) for r in rows if row_key(r) == key})
    log("6 then run, in each station worktree (%s): python3 tools/station_audit.py -k upstream_lock -k provenance "
        "-k licence_filter -k vendor_leak -k notice, and the station's certain tests" % (", ".join(sts) or "none found"))
    for n in notes:
        log("  NOTE " + n)
    for s in stops:
        log("  STOP " + s)
    log(_kit.headline("repin_report", len(stops), len(notes), len(ns)))
    return (1 if stops else 0), {"old": old, "new": new, "stops": stops, "notes": notes}


def apply(root, key, new, fetch=True, log=print):
    rc, info = report(root, key, new, fetch, log=log)
    if rc != 0:
        log("repin --apply: refused (report not green)")
        return rc
    bare = bootstrap.bare_path(root, key)
    if os.path.isfile(os.path.join(root, "station.json")):
        lp = os.path.join(root, "upstream", "LOCK.json")
        doc = _kit.read_json(lp)
        n = 0
        for r in lock_rows(doc):
            if row_key(r) == key:
                r["sha"] = new
                n += 1
        _kit.write_json(lp, doc)
        log("repin --apply: %d LOCK row(s) -> %s; now re-ingest the held paths: python3 tools/upstream/ingest.py "
            "--clone %s --sha %s ... (see upstream/LOCK.json paths)" % (n, new[:12], bare, new))
        return 0
    sp = os.path.join(root, "registry", "sources.json")
    doc = _kit.read_json(sp)
    for s in doc["sources"]:
        if s["key"] == key:
            s["sha"] = new
            s["last_commit"] = _kit.run(["git", "-C", bare, "log", "-1", "--format=%cs", new]).out.strip() or None
    _kit.write_json(sp, doc)
    log("repin --apply: registry/sources.json %s -> %s; bootstrap.py %s refreshes refs/heads/pin; then run "
        "repin.py --apply in each station worktree that LOCKs it" % (key, new[:12], key))
    return 0


def check(root, log=print):
    src = {s["key"]: s["sha"] for s in _kit.read_json(os.path.join(root, "registry", "sources.json"))["sources"]}
    bad, n = [], 0
    for st, rows in station_locks(root):
        for r in rows:
            n += 1
            k = row_key(r)
            if k not in src:
                bad.append("%s: LOCK row %s not in registry" % (st, k))
            elif r.get("sha") != src[k]:
                bad.append("%s: LOCK %s sha %s != registry %s" % (st, k, str(r.get("sha"))[:12], src[k][:12]))
    log(_kit.headline("repin_check", len(bad), 0, n))
    for b in bad:
        log("  " + b)
    return 1 if bad else 0


def _selftest():
    os.environ.pop(_kit.CACHE_ENV, None)  # fixtures must never touch the operator's configured cache
    tmp = tempfile.mkdtemp(prefix="kit-repin-")
    quiet = lambda *a: None
    try:
        remote, v1, v2 = bootstrap.make_remote(tmp, "o~r")
        w = lambda rel, txt: (os.makedirs(os.path.dirname(os.path.join(remote, rel)) or remote, exist_ok=True),
                              open(os.path.join(remote, rel), "w").write(txt))
        # v3: held path changes, new AGENTS.md, telemetry term; README paragraph stays "v2"
        w("skills/x/SKILL.md", "x\n")
        _kit.stage_paths(remote)
        _kit.commit(remote, "x")
        w("skills/x/SKILL.md", "x2 posthog.capture()\n")
        w("AGENTS.md", "do things\n")
        _kit.stage_paths(remote)
        _kit.commit(remote, "v3")
        v3 = _kit.git_out(remote, "rev-parse", "HEAD")
        w("LICENSE", "AGPL-3.0\n")
        _kit.stage_paths(remote)
        _kit.commit(remote, "relicense")
        v4 = _kit.git_out(remote, "rev-parse", "HEAD")
        x_base = _kit.git_out(remote, "rev-parse", "HEAD~2")
        rows = [{"key": "o~r", "repo": "o/r", "url": "file://" + remote, "sha": x_base}]
        root = bootstrap.make_kit_root(tmp, rows)
        assert bootstrap.run(root, rows, log=quiet) == 0
        _kit.run(["git", "-C", bootstrap.bare_path(root, "o~r"), "fetch", "-q", "origin", "+refs/heads/*:refs/remotes/origin/*"])
        out = []
        rc, info = report(root, "o~r", v3, fetch=False, paths=["skills/x/"], log=out.append)
        assert rc == 0, "\n".join(out)
        assert any("AGENTS.md" in n for n in info["notes"]) and any("telemetry" in n for n in info["notes"]), info
        assert any("skills/x/SKILL.md" in l for l in out), "held-path stat"
        rc, info = report(root, "o~r", v4, fetch=False, log=quiet)
        assert rc == 1 and any("LICENSE" in s for s in info["stops"]), "licence change must STOP"
        rc, info = report(root, "o~r", v1, fetch=False, log=quiet)
        assert rc == 1 and any("README" in s for s in info["stops"]), "README paragraph change must STOP"
        assert apply(root, "o~r", v4, fetch=False, log=quiet) == 1, "apply refused on red"
        assert _kit.read_json(os.path.join(root, "registry", "sources.json"))["sources"][0]["sha"] == x_base
        assert apply(root, "o~r", v3, fetch=False, log=quiet) == 0
        assert _kit.read_json(os.path.join(root, "registry", "sources.json"))["sources"][0]["sha"] == v3
        # --check on a station worktree
        st = os.path.join(tmp, "st")
        os.makedirs(os.path.join(st, "upstream"))
        os.makedirs(os.path.join(st, "registry"))
        shutil.copy2(os.path.join(root, "registry", "sources.json"), os.path.join(st, "registry", "sources.json"))
        _kit.write_json(os.path.join(st, "station.json"), {"name": "alpha"})
        _kit.write_json(os.path.join(st, "upstream", "LOCK.json"), {"rows": [{"repo": "o/r", "sha": v3, "paths": ["skills/x/"]}]})
        assert check(st, log=quiet) == 0
        _kit.write_json(os.path.join(st, "upstream", "LOCK.json"), {"rows": [{"repo": "o/r", "sha": x_base}]})
        assert check(st, log=quiet) == 1, "stale LOCK row must fail"
        print("selftest OK")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", nargs=2, metavar=("KEY", "SHA"))
    ap.add_argument("--apply", nargs=2, metavar=("KEY", "SHA"))
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--paths", nargs="*")
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--root", default=None)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return _selftest()
    root = a.root or os.getcwd()
    try:
        if a.report:
            return report(root, a.report[0], a.report[1], not a.no_fetch, a.paths)[0]
        if a.apply:
            return apply(root, a.apply[0], a.apply[1], not a.no_fetch)
        if a.check:
            return check(root)
    except (OSError, ValueError, KeyError, _kit.KitError) as e:
        print("repin: %s" % e)
        return 2
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
