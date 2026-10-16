#!/usr/bin/env python3
"""kit_check.py - the kit's claims about itself, re-derived.

Earned by: the decision tree is written in four places (README indented tree +
mermaid + station table, router/kit_tree.json, map/STATIONS.md, the git
branches) and the registry in seven files; a station renamed in one and not the
others sends the operator to a branch that does not exist (LL-07: one owner,
every copy checked). Retires: nothing (new with the kit).

  kit_check.py tree [--root R] [--plan kit_plan.yml] [--strict]
      README tree leaves == mermaid station nodes == README station table ==
      router/kit_tree.json leaves (same order) == map/STATIONS.md rows ==
      station/* branches (when the root is a git repo that has them) ==
      kit_plan.yml branches (when --plan). map/STATIONS.md must exist and
      declare GENERATED (build/root ships the pre-assembly seed written by
      assemble.py --seed-station-map; KIT.md and README.md name it, so every
      station audit checks it). --strict: a repo without station branches is a
      violation, not a skip.
  kit_check.py registry [--root R]
      28 sources rows, 40-hex pins, unique ids/keys, https://github.com/<repo>
      urls; every repo landed on a tree station or in the attic; every
      quarantine.json repo lands ONLY on station/quarantine (study lanes on their
      own station); licences cover every repo; telemetry rows carry a boolean
      `verified`; skill_assignment (if present) 360 unique rows homed on tree
      stations.
  kit_check.py tree registry          both
  kit_check.py --selftest
Exit 0 clean · 1 violation · 2 unreadable input.
"""
import json
import os
import re
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _kit  # noqa: E402

EXPECTED_SOURCES = 28
EXPECTED_SKILLS = 360
HEX40 = re.compile(r"^[0-9a-f]{40}$")


def _readme_parts(root):
    txt = open(os.path.join(root, "README.md"), encoding="utf-8").read()
    m = re.search(r"<!-- KIT_TREE:BEGIN.*?-->(.*?)<!-- KIT_TREE:END -->", txt, re.S)
    if not m:
        raise ValueError("README.md has no KIT_TREE:BEGIN/END block")
    block = m.group(1)
    qs = re.findall(r"\bQ(\d+)\b", block)
    leaves = re.findall(r"→\s*station/([\w-]+)", block)
    mm = re.search(r"```mermaid\n(.*?)```", txt, re.S)
    mer = []
    if mm:
        for s in re.findall(r"\[station/([\w-]+)", mm.group(1)):
            if s not in mer:
                mer.append(s)
    table = re.findall(r"^\|\s*([\w-]+)\s*\|\s*`station/([\w-]+)`\s*\|", txt, re.M)
    return [int(q) for q in qs], leaves, mer, table


def check_tree(root, plan=None, strict=False):
    v, notes = [], []
    try:
        qs, leaves, mer, table = _readme_parts(root)
        kt = _kit.read_json(os.path.join(root, "router", "kit_tree.json"))
    except (OSError, ValueError) as e:
        print("kit_check tree: unreadable input: %s" % e)
        return 2
    rows = kt["intents"] if isinstance(kt, dict) else kt
    kt_st = []
    for r in rows:
        n = r.get("name", "")
        if not n.startswith("station:"):
            v.append("kit_tree.json row %r is not station:<x>" % n)
            continue
        st = n.split(":", 1)[1]
        kt_st.append(st)
        if r.get("scope") != "main":
            v.append("kit_tree.json %s: scope must be 'main'" % n)
        if r.get("contributed_by") != "kit":
            v.append("kit_tree.json %s: contributed_by must be 'kit'" % n)
        rt = r.get("router") or {}
        fm = (rt.get("first_move") or {}).get("inline_gather", "")
        if fm != "git worktree add ~/stations/%s station/%s" % (st, st):
            v.append("kit_tree.json %s: first_move.inline_gather must be the worktree command, got %r" % (n, fm))
        if len(rt.get("keywords") or []) < 3:
            v.append("kit_tree.json %s: fewer than 3 keywords" % n)
    if qs != sorted(qs) or (qs and qs[0] != 0):
        v.append("README tree questions out of order: %s" % qs)
    if leaves != kt_st:
        v.append("README tree leaves %s != router/kit_tree.json order %s" % (leaves, kt_st))
    if mer != kt_st:
        v.append("README mermaid station nodes %s != kit_tree order %s" % (mer, kt_st))
    tab = [b for a, b in table]
    if [a for a, b in table] != tab:
        v.append("README station table name/branch mismatch: %s" % table)
    if tab != kt_st:
        v.append("README station table %s != kit_tree order %s" % (tab, kt_st))
    if len(set(kt_st)) != len(kt_st):
        v.append("kit_tree.json repeats a station")
    sm = os.path.join(root, "map", "STATIONS.md")
    if os.path.isfile(sm):
        smt = open(sm, encoding="utf-8").read()
        if not _kit.declares_generated(smt):
            v.append("map/STATIONS.md does not declare GENERATED in its first 3 lines (seed: python3 tools/kit/assemble.py "
                     "--seed-station-map; on an assembled main: python3 tools/map/gen_station_map.py --write)")
        got = set(re.findall(r"station/([\w-]+)", smt))
        got = {g for g in got if "--" not in g}
        if got != set(kt_st):
            v.append("map/STATIONS.md stations %s != kit_tree %s" % (sorted(got), sorted(kt_st)))
    elif strict:
        v.append("map/STATIONS.md missing (run python3 tools/map/gen_station_map.py --write)")
    else:
        # build/root ships a pre-assembly seed (assemble.py --seed-station-map) because KIT.md and README.md
        # name the file and every station audit checks those claims (fix-kitroot-1 D1)
        v.append("map/STATIONS.md absent (seed it: python3 tools/kit/assemble.py --seed-station-map --root <root>)")
    if os.path.isdir(os.path.join(root, ".git")) or os.path.isfile(os.path.join(root, ".git")):
        # REPRODUCE F2: local station/<x>, remote-tracking <remote>/station/<x> (a plain clone) and the
        # hosted claude/stable-kit-<x> naming all count (one resolver: tools/kit/_kit.station_refs)
        try:
            br = set(_kit.station_refs(root))
        except _kit.KitError as e:
            v.append("git refs unreadable: %s" % e)
            br = set()
        if br:
            if br != set(kt_st):
                v.append("station branches %s != kit_tree %s" % (sorted(br), sorted(kt_st)))
        elif strict:
            v.append("no station branches (station/<x>, <remote>/station/<x> or claude/stable-kit-<x>) in %s" % root)
        else:
            notes.append("no station/* branches yet: branch comparison skipped")
    if plan:
        pb = [b.split("/", 1)[1] for b in _kit.read_json(plan)["kit"]["branches"] if b.startswith("station/")]
        if set(pb) != set(kt_st):
            v.append("kit_plan.yml branches %s != kit_tree %s" % (sorted(pb), sorted(kt_st)))
    print(_kit.headline("kit_tree", len(v), len(notes), len(kt_st)))
    for x in v:
        print("  VIOLATION " + x)
    for x in notes:
        print("  note " + x)
    return 1 if v else 0


def check_registry(root):
    v = []
    R = os.path.join(root, "registry")
    try:
        src = _kit.read_json(os.path.join(R, "sources.json"))["sources"]
        homes = _kit.read_json(os.path.join(R, "homes.json"))["homes"]
        lics = _kit.read_json(os.path.join(R, "licences.json"))["licences"]
        tel = _kit.read_json(os.path.join(R, "telemetry.json"))["telemetry"]
        att = _kit.read_json(os.path.join(R, "attic.json"))["attic"]
        quar = _kit.read_json(os.path.join(R, "quarantine.json"))["quarantine"]
        tree_st = _kit.stations_from_tree(root)
    except (OSError, ValueError, KeyError) as e:
        print("kit_check registry: unreadable input: %s" % e)
        return 2
    if len(src) != EXPECTED_SOURCES:
        v.append("sources.json has %d rows, expected %d" % (len(src), EXPECTED_SOURCES))
    ids = [s.get("id") for s in src]
    keys = [s.get("key") for s in src]
    if len(set(ids)) != len(ids):
        v.append("sources.json repeats an id")
    if len(set(keys)) != len(keys):
        v.append("sources.json repeats a key")
    by_id = {}
    for s in src:
        by_id[s.get("id")] = s
        if not HEX40.match(str(s.get("sha", ""))):
            v.append("sources %s: sha %r is not 40-hex" % (s.get("key"), s.get("sha")))
        if s.get("url") != "https://github.com/%s" % s.get("repo"):
            v.append("sources %s: url %r != https://github.com/<repo>" % (s.get("key"), s.get("url")))
        if s.get("key") != str(s.get("repo", "")).replace("/", "~"):
            v.append("sources %s: key is not owner~repo" % s.get("key"))
        if not s.get("licence") or not s.get("licence_file"):
            v.append("sources %s: licence / licence_file missing" % s.get("key"))
    attic_ids = {a.get("id") for a in att}
    for a in att:
        if a.get("id") not in by_id:
            v.append("attic row %s is not a sources row" % a.get("id"))
        elif a.get("sha") != by_id[a["id"]].get("sha"):
            v.append("attic row %s sha != sources pin" % a.get("id"))
    hid = {}
    for h in homes:
        hid[h.get("id")] = h
        st_l = [x.get("station") for x in h.get("lands", []) if x.get("station")]
        if not st_l and h.get("id") not in attic_ids:
            v.append("homes %s: lands nowhere and not in the attic" % h.get("key"))
        for st in st_l:
            if st not in tree_st:
                v.append("homes %s: station %r is not a decision-tree station" % (h.get("key"), st))
        for x in h.get("lands", []):
            how = x.get("how", "")
            if not (how in ("repertoire", "tree", "bootstrap", "attic") or how.startswith("copy_from:")):
                v.append("homes %s: how %r unknown" % (h.get("key"), how))
            if how.startswith("copy_from:") and how.split(":", 1)[1] not in tree_st:
                v.append("homes %s: copy_from %r not a station" % (h.get("key"), how))
    if set(hid) != set(ids):
        v.append("homes.json ids %s != sources ids" % sorted(set(hid) ^ set(ids)))
    if {l.get("id") for l in lics} != set(ids):
        v.append("licences.json does not cover every sources id")
    for q in quar:
        h = hid.get(next((s.get("id") for s in src if s.get("key") == q.get("key")), None))
        if h is None:
            v.append("quarantine %s: repo not in sources/homes" % q.get("key"))
            continue
        if q.get("sha") != by_id[h["id"]].get("sha"):
            v.append("quarantine %s: sha != sources pin" % q.get("key"))
        lands = {x.get("station") for x in h.get("lands", []) if x.get("station")}
        if q.get("station") == "quarantine":
            if lands != {"quarantine"}:
                v.append("quarantine %s: must land ONLY on station/quarantine, lands on %s" % (q.get("key"), sorted(lands)))
            if not str(q.get("path", "")).startswith("upstream/"):
                v.append("quarantine %s: path must be under upstream/" % q.get("key"))
        elif q.get("station") not in lands:
            v.append("quarantine %s: listed on %s where it does not land" % (q.get("key"), q.get("station")))
    for h in homes:
        if "quarantine" in {x.get("station") for x in h.get("lands", [])} and \
                not any(q.get("key") == h.get("key") and q.get("station") == "quarantine" for q in quar):
            v.append("homes %s lands on quarantine but has no quarantine.json row" % h.get("key"))
    for t in tel:
        if not isinstance(t.get("verified"), bool):
            v.append("telemetry %s: verified must be a boolean" % t.get("tool"))
        if not t.get("evidence"):
            v.append("telemetry %s: evidence path missing" % t.get("tool"))
    sa = os.path.join(R, "skill_assignment.json")
    n_sk = 0
    if os.path.isfile(sa):
        rows = _kit.read_json(sa).get("rows", [])
        n_sk = len(rows)
        if n_sk != EXPECTED_SKILLS or len({r.get("id") for r in rows}) != n_sk:
            v.append("skill_assignment.json: %d rows (%d unique), expected %d" % (n_sk, len({r.get('id') for r in rows}), EXPECTED_SKILLS))
        bad = sorted({r.get("home") for r in rows} - set(tree_st))
        if bad:
            v.append("skill_assignment.json homes %s are not decision-tree stations" % bad)
    print(_kit.headline("kit_registry", len(v), 0, len(src)))
    print("  sources %d / %d · attic %d · quarantine rows %d · telemetry rows %d (verified %d) · skill rows %d / %d"
          % (len(src), EXPECTED_SOURCES, len(att), len(quar), len(tel), sum(1 for t in tel if t.get("verified") is True),
             n_sk, EXPECTED_SKILLS))
    for x in v:
        print("  VIOLATION " + x)
    return 1 if v else 0


def _selftest():
    here = _kit.REPO_ROOT_GUESS
    tmp = tempfile.mkdtemp(prefix="kit-check-")
    try:
        root = os.path.join(tmp, "r")
        os.makedirs(root)
        for rel in ("README.md", "router/kit_tree.json", "registry/sources.json", "registry/homes.json",
                    "registry/licences.json", "registry/telemetry.json", "registry/attic.json",
                    "registry/quarantine.json"):
            d = os.path.join(root, rel)
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copy2(os.path.join(here, rel), d)
        sts = _kit.stations_from_tree(root)
        assert check_registry(root) == 0, "clean registry"
        # STATIONS.md absent: a violation strict or not (KIT.md/README.md name it; D1)
        assert check_tree(root) == 1, "planted: STATIONS.md absent"
        # the shipped seed (assemble.py --seed-station-map): present, GENERATED, every tree station
        import assemble as kit_assemble
        assert kit_assemble.seed_station_map(root) == 0
        sm = os.path.join(root, "map", "STATIONS.md")
        seed = open(sm, encoding="utf-8").read()
        assert seed.startswith("<!-- GENERATED by tools/map/gen_station_map.py"), seed[:120]
        assert kit_assemble.seed_station_map(root, check=True) == 0, "seed --check current"
        assert check_tree(root) == 0, "clean tree with the seed"
        open(sm, "w").write("<!-- GENERATED by tools/map/gen_station_map.py -->\n" +
                            "".join("| station/%s | x |\n" % s for s in sts))
        assert check_tree(root, strict=True) == 0, "strict with STATIONS.md"
        open(sm, "w").write("".join("| station/%s | x |\n" % s for s in sts))
        assert check_tree(root) == 1, "planted: STATIONS.md without its GENERATED header"
        open(sm, "w").write("<!-- GENERATED by tools/map/gen_station_map.py -->\n" + "".join("| station/%s |\n" % s for s in sts[:-1]))
        assert check_tree(root) == 1, "planted: STATIONS.md missing a station"
        assert kit_assemble.seed_station_map(root, check=True) == 1, "planted: seed drift caught by --check"
        os.remove(sm)
        assert check_tree(root, strict=True) == 1, "strict: STATIONS.md absent"
        kit_assemble.seed_station_map(root)

        def plant(rel, fn, why, check):
            p = os.path.join(root, rel)
            orig = open(p, encoding="utf-8").read()
            open(p, "w", encoding="utf-8").write(fn(orig))
            try:
                assert check() == 1, "planted defect not caught: " + why
            finally:
                open(p, "w", encoding="utf-8").write(orig)
        plant("README.md", lambda t: t.replace("→ station/studio", "→ station/studi0"), "README leaf renamed", lambda: check_tree(root))
        plant("README.md", lambda t: t.replace("SD[station/studio]", "SD[studio]"), "mermaid node dropped", lambda: check_tree(root))
        plant("README.md", lambda t: t.replace("| studio | `station/studio` |", "| studio | `station/stud` |"), "table row", lambda: check_tree(root))

        def swap(t):
            d = json.loads(t)
            d["intents"][1], d["intents"][2] = d["intents"][2], d["intents"][1]
            return json.dumps(d)
        plant("router/kit_tree.json", swap, "kit_tree reordered", lambda: check_tree(root))

        def badsha(t):
            d = json.loads(t)
            d["sources"][0]["sha"] = d["sources"][0]["sha"][:12]
            return json.dumps(d)
        plant("registry/sources.json", badsha, "short sha", lambda: check_registry(root))

        def unland(t):
            d = json.loads(t)
            for h in d["homes"]:
                if not h["attic"]:
                    h["lands"] = []
                    break
            return json.dumps(d)
        plant("registry/homes.json", unland, "unlanded repo", lambda: check_registry(root))

        def leak(t):
            d = json.loads(t)
            for h in d["homes"]:
                if h["key"] == "getmaxun~maxun":
                    h["lands"].append({"station": "venture", "branch": "station/venture", "how": "tree"})
            return json.dumps(d)
        plant("registry/homes.json", leak, "quarantine repo landing outside quarantine", lambda: check_registry(root))

        def drop_src(t):
            d = json.loads(t)
            d["sources"].pop()
            return json.dumps(d)
        plant("registry/sources.json", drop_src, "27 rows", lambda: check_registry(root))

        def tel_str(t):
            d = json.loads(t)
            d["telemetry"][0]["verified"] = "no"
            return json.dumps(d)
        plant("registry/telemetry.json", tel_str, "verified not bool", lambda: check_registry(root))
        # git branches
        _kit.run(["git", "init", "-q", "-b", "main", root])
        _kit.fixture_git_config(root)
        _kit.stage_paths(root)
        _kit.commit(root, "fixture")
        for s in sts:
            _kit.git(root, "branch", "station/" + s)
        assert check_tree(root, strict=False) == 0, "branches match, seed present"
        open(sm, "w").write("<!-- GENERATED by tools/map/gen_station_map.py -->\n" + "".join("| station/%s |\n" % s for s in sts))
        assert check_tree(root, strict=True) == 0, "branches match"
        _kit.stage_paths(root)
        _kit.commit(root, "station map")
        for lay, lrepo in _kit.fixture_layouts(root, tmp).items():
            assert check_tree(lrepo, strict=True) == 0, "REPRODUCE F2: layout %s must pass --strict" % lay
        _kit.git(root, "branch", "-D", "station/" + sts[-1])
        assert check_tree(root) == 1, "planted: missing branch"
        print("selftest OK")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in argv:
        return _selftest()
    root = _kit.REPO_ROOT_GUESS
    plan = None
    strict = "--strict" in argv
    if "--root" in argv:
        root = argv[argv.index("--root") + 1]
    if "--plan" in argv:
        plan = argv[argv.index("--plan") + 1]
    subs = [a for a in argv if a in ("tree", "registry")]
    if not subs:
        print(__doc__)
        return 2
    rc = 0
    for s in subs:
        r = check_tree(root, plan, strict) if s == "tree" else check_registry(root)
        rc = max(rc, r)
    return rc


if __name__ == "__main__":
    sys.exit(main())
