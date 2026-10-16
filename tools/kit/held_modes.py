#!/usr/bin/env python3
"""held_modes.py - the git file mode of every held upstream file at its pin vs on its station branch.

Earned by: SAFETY 5 (2026-10-16): 41 held files lost their executable bit at ingest (bytes identical,
100755 at the pin -> 100644 on the branch), and nothing recorded it: PROVENANCE hashes content only.
Decision recorded here (MODE_POLICY): the strip is KEPT as policy, not restored, because a lane holds
upstream code as data (deny_upstream_write, quarantine_gate) and a directly executable file in a lane is
one `./script` away from running outside the run tree; run trees (tools/kit/runtree.py) check out the
pin with its own modes, so nothing that is meant to run loses its bit. What was missing was the record:
this tool writes it and checks it. Retires: nothing (no earlier check compared modes).

  held_modes.py --write [--clones DIR]
      for every station ref (local, remote-tracking or claude/stable-kit-*), every upstream/PROVENANCE.json
      row (symlink-dereferenced rows skipped): mode at the pin (`git ls-tree` of the pinned tree from
      DIR/<owner~repo>, else the shared bootstrap cache <cache>/<owner~repo>.git; trees suffice, no blobs)
      vs mode on the branch. Writes registry/held_modes.json (GENERATED): every row whose modes differ.
      Exit 1 when a pin's tree is unreachable (a partial record is never written).
  held_modes.py --check
      no clones needed: every recorded row still exists on its branch with the recorded held mode, every
      station's held 100755 files are recorded, and no recorded change is other than 100755 -> 100644
      (MODE_POLICY). Exit 1 on drift.
  held_modes.py --selftest
Exit 0 clean · 1 drift / unreachable pin · 2 usage.
"""
import argparse
import collections
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _kit  # noqa: E402

TOOL = "tools/kit/held_modes.py"
OUT = os.path.join("registry", "held_modes.json")
MODE_POLICY = ("NOT RESTORED (SAFETY 5, 2026-10-16): held upstream files are data in a read-only lane; an upstream "
               "100755 is stored 100644 so nothing in a lane is directly executable. Bytes are unchanged (PROVENANCE "
               "sha256). To run upstream code use a run tree (tools/kit/runtree.py), which checks out the pin with "
               "its own modes. This file is the record of every mode the strip changed.")
ALLOWED = ("100755", "100644")


def ls_modes(repo, treeish, paths=None):
    """{path: mode} for blobs under treeish (all, or only `paths`)."""
    args = ["ls-tree", "-r", "-z", treeish]
    out = {}
    plist = sorted(set(paths)) if paths is not None else [None]
    for i in range(0, len(plist), 300):
        chunk = plist[i:i + 300]
        p = _kit.git(repo, *(args + (["--"] + chunk if chunk != [None] else [])), check=False)
        if p.returncode != 0:
            raise _kit.KitError("ls-tree %s failed in %s: %s" % (treeish, repo, p.err.strip()[:200]))
        for ent in p.out.split("\0"):
            if not ent:
                continue
            meta, _, path = ent.partition("\t")
            mode, typ, _obj = meta.split()
            if typ == "blob":
                out[path] = mode
    return out


def provenance(repo, ref):
    p = _kit.git(repo, "show", "%s:upstream/PROVENANCE.json" % ref, check=False)
    if p.returncode != 0:
        return []
    d = json.loads(p.out)
    return d.get("rows") or [] if isinstance(d, dict) else d


def pin_source(root, key, clones):
    for cand in ([os.path.join(clones, key), os.path.join(clones, key + ".git")] if clones else []) + \
            [os.path.join(_kit.upstream_cache(root), key + ".git")]:
        if os.path.isdir(cand):
            return cand
    return None


def compute(root, clones=None):
    refs = _kit.station_refs(root, _kit.known_stations(root))
    rows, unreachable, denom = [], [], 0
    per = collections.Counter()
    for st, ref in refs.items():
        prov = [r for r in provenance(root, ref) if not r.get("symlink_from")]
        held = ls_modes(root, ref, [r["path"] for r in prov]) if prov else {}
        by_pin = collections.defaultdict(list)
        for r in prov:
            by_pin[(r["repo"], r["sha"])].append(r)
        for (repo, sha), rs in sorted(by_pin.items()):
            key = repo.replace("/", "~")
            src = pin_source(root, key, clones)
            if not src or _kit.git(src, "cat-file", "-e", sha + "^{tree}", check=False).returncode != 0:
                unreachable.append("%s @ %s (station %s, %d rows)" % (repo, sha[:12], st, len(rs)))
                continue
            pin = ls_modes(src, sha, [r["source_path"] for r in rs])
            for r in rs:
                denom += 1
                a, b = pin.get(r["source_path"]), held.get(r["path"])
                if a and b and a != b:
                    rows.append({"station": st, "path": r["path"], "repo": repo, "source_path": r["source_path"],
                                 "pin": sha, "mode_at_pin": a, "mode_held": b})
                    per[(st, repo, a, b)] += 1
    return rows, unreachable, denom, per


def render(rows, denom, per):
    return {"_generated_by": TOOL,
            "_regenerate": "python3 tools/kit/held_modes.py --write [--clones <dir of owner~repo pinned clones>]",
            "policy": MODE_POLICY,
            "denominator": denom,
            "changed": len(rows),
            "by_station_repo": ["%s · %s · %s -> %s · %d" % (k + (v,)) for k, v in sorted(per.items())],
            "rows": sorted(rows, key=lambda r: (r["station"], r["path"]))}


def cmd_write(root, clones, log=print):
    try:
        rows, unreachable, denom, per = compute(root, clones)
    except (_kit.KitError, ValueError) as e:
        log("held_modes: unreadable input: %s" % e)
        return 2
    if unreachable:
        log(_kit.headline("held_modes", len(unreachable), 0, denom))
        for u in unreachable:
            log("  UNREACHABLE pin tree: %s (pass --clones or bootstrap it)" % u)
        return 1
    _kit.write_json(os.path.join(root, OUT), render(rows, denom, per))
    log("held_modes: wrote %s · %d / %d held files changed mode at ingest" % (OUT, len(rows), denom))
    for line in render(rows, denom, per)["by_station_repo"]:
        log("  " + line)
    return 0


def cmd_check(root, log=print):
    p = os.path.join(root, OUT)
    if not os.path.isfile(p):
        log("held_modes: %s missing (run --write)" % OUT)
        return 1
    doc = _kit.read_json(p)
    refs = _kit.station_refs(root, _kit.known_stations(root))
    viol = []
    rec = collections.defaultdict(dict)
    for r in doc.get("rows", []):
        rec[r["station"]][r["path"]] = r
        if (r.get("mode_at_pin"), r.get("mode_held")) != ALLOWED:
            viol.append("%s:%s recorded %s -> %s (MODE_POLICY allows only 100755 -> 100644)"
                        % (r["station"], r["path"], r.get("mode_at_pin"), r.get("mode_held")))
    for st, ref in refs.items():
        prov = [r["path"] for r in provenance(root, ref) if not r.get("symlink_from")]
        held = ls_modes(root, ref, prov) if prov else {}
        for path, r in rec.get(st, {}).items():
            if held.get(path) != r["mode_held"]:
                viol.append("%s:%s is %s on the branch, recorded %s" % (st, path, held.get(path, "absent"), r["mode_held"]))
        for path, mode in held.items():
            if mode == "100755" and path not in rec.get(st, {}):
                viol.append("%s:%s is 100755 in a lane and not recorded (MODE_POLICY strips it; rerun --write)" % (st, path))
    for st in sorted(set(rec) - set(refs)):
        viol.append("station %s recorded but no ref found" % st)
    log(_kit.headline("held_modes", len(viol), 0, int(doc.get("denominator") or 0)))
    for v in viol[:40]:
        log("  VIOLATION " + v)
    return 1 if viol else 0


# ------------------------------------------------------------------ selftest
def _selftest():
    os.environ.pop(_kit.CACHE_ENV, None)
    tmp = tempfile.mkdtemp(prefix="kit-modes-")
    quiet = lambda *a: None
    try:
        up = os.path.join(tmp, "clones", "o~r")
        _kit.run(["git", "init", "-q", "-b", "main", up])
        _kit.fixture_git_config(up)
        for rel, mode in (("bin/run.sh", 0o755), ("README.md", 0o644), ("lib/a.py", 0o644)):
            p = os.path.join(up, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "w").write(rel + "\n")
            os.chmod(p, mode)
        _kit.stage_paths(up)
        _kit.commit(up, "pin")
        sha = _kit.git_out(up, "rev-parse", "HEAD")
        kit = os.path.join(tmp, "kit")
        _kit.run(["git", "init", "-q", "-b", "main", kit])
        _kit.fixture_git_config(kit)
        os.makedirs(os.path.join(kit, "registry"))
        open(os.path.join(kit, "README.md"), "w").write("kit\n")
        _kit.stage_paths(kit)
        _kit.commit(kit, "main")
        _kit.git(kit, "switch", "-q", "-c", "station/alpha")
        prov = []
        for rel in ("bin/run.sh", "README.md", "lib/a.py"):
            dst = os.path.join(kit, "upstream", "o~r", rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            open(dst, "w").write(rel + "\n")
            os.chmod(dst, 0o644)  # ingest strips the bit
            prov.append({"repo": "o/r", "sha": sha, "source_path": rel, "path": "upstream/o~r/" + rel, "symlink_from": None})
        _kit.write_json(os.path.join(kit, "upstream", "PROVENANCE.json"), {"rows": prov})
        _kit.stage_paths(kit)
        _kit.commit(kit, "alpha")
        _kit.git(kit, "switch", "-q", "main")
        clones = os.path.join(tmp, "clones")
        assert cmd_write(kit, None, log=quiet) == 1, "no pin source: refuse a partial record"
        assert cmd_write(kit, clones, log=quiet) == 0
        d = _kit.read_json(os.path.join(kit, OUT))
        assert d["denominator"] == 3 and d["changed"] == 1 and d["rows"][0]["path"] == "upstream/o~r/bin/run.sh", d
        assert d["rows"][0]["mode_at_pin"] == "100755" and d["rows"][0]["mode_held"] == "100644"
        assert _kit.declares_generated(open(os.path.join(kit, OUT)).read())
        assert cmd_check(kit, log=quiet) == 0, "clean record"
        for lay, lrepo in _kit.fixture_layouts(kit, tmp).items():  # REPRODUCE F2 layouts
            if lay != "local":
                os.makedirs(os.path.join(lrepo, "registry"), exist_ok=True)
                shutil.copy(os.path.join(kit, OUT), os.path.join(lrepo, OUT))
            assert cmd_check(lrepo, log=quiet) == 0, lay
        # planted: a held file regains its exec bit on the branch -> drift
        _kit.git(kit, "switch", "-q", "station/alpha")
        os.chmod(os.path.join(kit, "upstream/o~r/lib/a.py"), 0o755)
        _kit.git(kit, "add", "--", "upstream/o~r/lib/a.py")
        _kit.commit(kit, "planted +x")
        _kit.git(kit, "switch", "-q", "main")
        lines = []
        assert cmd_check(kit, log=lines.append) == 1 and any("lib/a.py is 100755" in l for l in lines), lines
        print("selftest OK")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=_kit.REPO_ROOT_GUESS)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--clones")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return _selftest()
    if a.write:
        return cmd_write(a.root, a.clones)
    if a.check:
        return cmd_check(a.root)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
