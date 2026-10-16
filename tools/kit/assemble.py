#!/usr/bin/env python3
"""assemble.py - build the stable-kit repo from the build dir (block E runs it).

Earned by: ORDER 2 (operator verbatim): "main holds the shared core and decision
tree and each station gets its own self-contained branch". Branches made by hand
drift: an orphan branch cannot merge main, a station that overwrites a commons
file conflicts on every sync. This tool makes the shape structural.
Retires: nothing (new with the kit).

  assemble.py --build <build dir> --out <repo dir> [--stations a,b,...]
              [--plan <kit_plan.yml>] [--no-strict]
  assemble.py --fixture --out <repo dir>    build a 2-station toy build dir and assemble it
  assemble.py --selftest                    fixture + forced conflicts + refusals
  assemble.py --seed-station-map [--root R] [--plan kit_plan.yml] [--build <build dir>] [--check]
        write (or, with --check, compare) the pre-assembly map/STATIONS.md: one row per
        decision-tree station, rendered by tools/map/gen_station_map.py's render() with
        values true before any branch exists (0 behind, LOCK rows of the build overlay).
        build/root ships this file; step 3 re-seeds it on main; step 5 replaces it with
        the render of the real branches.

Steps (KIT_PLAN 3, contract kit-root section 2):
 1 refuse a non-empty --out
 2 git init -b main; repo-local user.name=stable-kit, user.email=kit@localhost
 3 copy build/commons/. then build/root/. (refuse a root file that collides with a
   commons file); SEED map/STATIONS.md from the plan's branch list (seed_station_map,
   through the commons generator's own render(): every audit from here on sees the
   file KIT.md and README.md name - fix-kitroot-1 D1); regenerate: registry/skill_assignment.json (with --plan),
   SKILLS_INDEX.md (pre-routing), every declared GENERATED file (map, brain,
   ownership, ...), commons/MANIFEST.json last; stage by path list, commit
   "kit: commons + decision tree (main)"; tools/station_audit.py must exit 0
   (every MUST_BE_CLEAN green) or STOP (the commit stays, untagged); tag commons-v1
 4 per station in decision-tree order: git switch -c station/<x> main; refuse an
   overlay path that already exists on main (unless main's copy is GENERATED);
   copy build/stations/<x>/.; regenerate the station's GENERATED files;
   commit "station/<x>: overlay"; station_audit MUST-clean or STOP (audits run
   on the committed tree: checks read HEAD:<lane>); back to main
 5 on main: tools/map/gen_station_map.py --write, skills_index.py --from-git
   --write, MANIFEST regenerated, kit_check.py tree registry --strict, commit
   "kit: station map + skills index"; then tools/kit/sync.py on every station
   (proves the merge path; a conflict = STOP)
 6 skills_index.py --from-git --check, git fsck, branch list == main + stations,
   git merge-base --is-ancestor main station/<x> for all
Exit 0 built and verified · 1 a STOP (the repo is left for inspection) · 2 usage.
"""
import argparse
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _kit  # noqa: E402
import sync as kit_sync  # noqa: E402

KIT_DIR = os.path.dirname(os.path.abspath(__file__))
# Regenerators run unconditionally when their script exists (first-time generation:
# regen_all() alone only refreshes files that already declare GENERATED).
ALWAYS_MAIN = [["tools/gov/gen_ownership.py", "--write"], ["tools/map/map_check.py", "--write"], ["tools/brain.py", "index"]]
ALWAYS_STATION = ALWAYS_MAIN + [["tools/upstream/notice.py", "--root", ".", "--write"],
                                ["tools/upstream/skill_routes.py", "index", "--station-root", "."]]
REQUIRED_STRICT = ["tools/station_audit.py", "tools/gov/gen_manifest.py", "tools/kit/skills_index.py",
                   "tools/kit/kit_check.py", "tools/kit/sync.py", "tools/map/gen_station_map.py"]


class Stop(Exception):
    pass


# ------------------------------------------------------------------ pre-assembly station map (D1)
STATION_MAP = "map/STATIONS.md"
STATION_MAP_TOOL = "tools/map/gen_station_map.py"
SEED_NOTE = ("%d station branch(es) SEEDED from the plan's branch list before any branch exists "
             "(tools/kit/assemble.py --seed-station-map); assemble.py step 5 re-renders this file from the real "
             "branches with `python3 tools/map/gen_station_map.py --write`. Open one: "
             "`git worktree add ~/stations/<x> station/<x>`.")


def _load_station_map_render(root, build=None):
    """render() of the commons generator: <root>/tools/map/ (assembled repo), else
    <build>/commons/tools/map/ or <root>/../commons/tools/map/ (build layout). None if absent."""
    cands = [os.path.join(root, STATION_MAP_TOOL)]
    if build:
        cands.append(os.path.join(build, "commons", STATION_MAP_TOOL))
    cands.append(os.path.join(os.path.dirname(os.path.abspath(root)), "commons", STATION_MAP_TOOL))
    for p in cands:
        if not os.path.isfile(p):
            continue
        try:
            # import only a generator that defines render(): executing a script-style generator's module
            # body would write map/STATIONS.md into the CALLER's cwd (fix2-root: the selftest clobbered
            # build/root/map/STATIONS.md this way)
            with open(p, encoding="utf-8") as fh:
                if "def render(" not in fh.read():
                    continue
            import importlib.util
            spec = importlib.util.spec_from_file_location("_kit_gen_station_map", p)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        except Exception:  # a fixture generator without render(): fall back, said so in the file
            continue
        if callable(getattr(mod, "render", None)):
            return mod.render, p
    return None, None


def seed_rows(root, plan=None, build=None):
    """One row per decision-tree station (router/kit_tree.json order; the plan's branch list
    must name the same set). Purpose: overlay station.json > plan station > kit_tree note."""
    order = _kit.stations_from_tree(root)
    pl = _kit.read_json(plan) if plan else {}
    pb = [b.split("/", 1)[1] for b in (pl.get("kit") or {}).get("branches", []) if b.startswith("station/")]
    if pb:  # a plan that lists branches must list exactly the decision-tree stations
        if set(pb) != set(order):
            raise Stop("plan branches %s != router/kit_tree.json stations %s" % (sorted(pb), sorted(order)))
    p_purpose = {s.get("name"): s.get("purpose") for s in (pl.get("stations") or []) if isinstance(s, dict)}
    kt = _kit.read_json(os.path.join(root, "router", "kit_tree.json"))
    kt_desc = {r["name"].split(":", 1)[1]: r.get("description") for r in kt["intents"] if r.get("name", "").startswith("station:")}
    rows = []
    for st in sorted(order):
        ov = os.path.join(build, "stations", st) if build else None
        purpose, lock, have = None, 0, bool(ov and os.path.isdir(ov))
        if have:
            try:
                purpose = (_kit.read_json(os.path.join(ov, "station.json")) or {}).get("purpose")
            except (OSError, ValueError):
                purpose = None
            try:
                lock = len((_kit.read_json(os.path.join(ov, "upstream", "LOCK.json")) or {}).get("rows", []))
            except (OSError, ValueError, AttributeError):
                lock = 0
        purpose = purpose or p_purpose.get(st) or kt_desc.get(st) or "-"
        rows.append({"branch": "station/" + st, "purpose": purpose, "behind": 0,
                     "base": "pending (seed: assemble step 4 branches it from main)",
                     "lock": lock,
                     "subject": "(seed) station/%s: overlay%s" % (st, "" if have or not build else " - overlay not in this build")})
    return rows


def render_seed(root, plan=None, build=None):
    rows = seed_rows(root, plan, build)
    render, src = _load_station_map_render(root, build)
    if render is not None:
        lines = render(rows).split("\n")
        lines[0] = lines[0].replace(" from the station/* branches", " (pre-assembly seed by tools/kit/assemble.py)")
        lines = [SEED_NOTE % len(rows) if " rendered against `main`" in l else l
                 for l in lines]
        return "\n".join(lines)
    # fallback (fixture generators without render()): same GENERATED first line, same table
    esc = lambda s: str(s).replace("|", "\\|")
    L = ["<!-- GENERATED by %s (pre-assembly seed by tools/kit/assemble.py) — run python3 %s --write -->" % (STATION_MAP_TOOL, STATION_MAP_TOOL),
         "owner: %s · status: GENERATED · date: see git log · supersedes: none · audit: python3 %s --check" % (STATION_MAP_TOOL, STATION_MAP_TOOL),
         "", "# Stations", "", SEED_NOTE % len(rows), "",
         "| branch | purpose | behind main | merge-base == commons tag | LOCK rows | last commit |", "|---|---|---|---|---|---|"]
    L += ["| `%s` | %s | %d | %s | %d | %s |" % (r["branch"], esc(r["purpose"]), r["behind"], r["base"], r["lock"], esc(r["subject"])) for r in rows]
    return "\n".join(L) + "\n"


def seed_station_map(root, plan=None, build=None, check=False):
    """Write (or compare) <root>/map/STATIONS.md as the pre-assembly seed. Returns 0 written/current, 1 drift."""
    want = render_seed(root, plan, build)
    path = os.path.join(root, STATION_MAP)
    have = open(path, encoding="utf-8").read() if os.path.isfile(path) else None
    if check:
        return 0 if have == want else 1
    if have != want:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(want)
    return 0


class Assembler:
    def __init__(self, build, out, stations=None, plan=None, strict=True, fixture=False, log=print):
        self.build, self.out = os.path.abspath(build), os.path.abspath(out)
        self.only = stations
        self.plan = plan
        self.strict = strict
        self.fixture = fixture
        self.log = log
        self.notes = []

    # -- helpers
    def py(self, *argv, must=True, what=None):
        script = os.path.join(self.out, argv[0])
        if not os.path.isfile(script):
            if must and self.strict:
                raise Stop("required tool absent: %s" % argv[0])
            self.notes.append("skipped (absent): %s" % " ".join(argv))
            return None
        p = _kit.run([sys.executable] + list(argv), cwd=self.out, check=False)
        head = (p.out.strip().splitlines() or [p.err.strip()[:200]])[0] if (p.out or p.err) else ""
        self.log("  $ python3 %s -> %d %s" % (" ".join(argv), p.returncode, head))
        if p.returncode != 0 and must:
            raise Stop("%s failed (exit %d):\n%s%s" % (what or " ".join(argv), p.returncode, p.out[-3000:], p.err[-2000:]))
        return p

    def git(self, *a, **k):
        return _kit.git(self.out, *a, **k)

    def regen(self, on_station):
        for argv in (ALWAYS_STATION if on_station else ALWAYS_MAIN):
            self.py(*argv, must=False)
        _kit.stage_paths(self.out)
        done, failed = kit_sync.regen_all(self.out, on_station)
        for d in done:
            self.log("  regen %s" % d)
        hard = [f for f in failed if "absent" not in f]
        if hard:
            raise Stop("regeneration failed: %s" % hard)
        for f in failed:
            self.notes.append("regen skipped: %s" % f)

    def audit(self, where):
        p = self.py("tools/station_audit.py", must=False)
        if p is None:
            if self.strict:
                raise Stop("tools/station_audit.py absent")
            return
        if p.returncode != 0:
            raise Stop("station_audit not MUST-clean on %s (exit %d):\n%s" % (where, p.returncode, p.out[-4000:]))

    def force_nested(self, copied):
        """Every copied build file lands in the commit, even one a held tree's own .gitignore drops
        (fix2-root: AutoHedge's .env and experimental/ were left untracked and markets lane_tracked went red)."""
        forced = _kit.force_stage_nested_ignored(self.out, copied)
        if forced:
            self.log("  force-staged %d file(s) a nested .gitignore drops: %s%s" % (
                len(forced), ", ".join(forced[:4]), " ..." if len(forced) > 4 else ""))

    def commit(self, msg):
        _kit.stage_paths(self.out)
        if _kit.has_staged(self.out):
            _kit.commit(self.out, msg)
            self.log("  commit: %s" % msg)
        else:
            self.log("  (nothing to commit for: %s)" % msg)

    # -- steps
    def step1_2(self):
        if os.path.exists(self.out) and os.listdir(self.out):
            raise Stop("refusing: --out %s exists and is not empty" % self.out)
        for d in ("commons", "root"):
            if not os.path.isdir(os.path.join(self.build, d)):
                raise Stop("build dir lacks %s/" % d)
        os.makedirs(self.out, exist_ok=True)
        _kit.run(["git", "init", "-q", "-b", "main", self.out])
        _kit.fixture_git_config(self.out)
        self.log("1-2 init %s (main)" % self.out)

    def step3(self):
        self.log("3 main: commons + root")
        commons = set(_kit.list_files(os.path.join(self.build, "commons")))
        root = set(_kit.list_files(os.path.join(self.build, "root")))
        root = {r for r in root if "__pycache__" not in r}
        clash = sorted(commons & root)
        if clash:
            raise Stop("root files collide with commons files: %s" % clash[:20])
        copied = _kit.copy_tree(os.path.join(self.build, "commons"), self.out, skip_names=(".git", "__pycache__"))
        copied += _kit.copy_tree(os.path.join(self.build, "root"), self.out, skip_names=(".git", "__pycache__"))
        self.force_nested(copied)
        # D1: KIT.md / README.md name map/STATIONS.md; every audit from here on (main step 3, each station in
        # step 4) must find it. Seed it now from the plan's branch list; step 5 re-renders it from real branches.
        seed_station_map(self.out, plan=os.path.abspath(self.plan) if self.plan else None, build=self.build)
        self.log("  seed %s (%d stations, pre-assembly)" % (STATION_MAP, len(_kit.stations_from_tree(self.out))))
        _kit.stage_paths(self.out)  # sibling tools walk `git ls-files`: the copied tree must be in the index
        if self.strict:
            missing = [t for t in REQUIRED_STRICT if not os.path.isfile(os.path.join(self.out, t))]
            if missing:
                raise Stop("required tools absent on main: %s" % missing)
        if self.plan:
            self.py("tools/kit/skills_index.py", "--write-assignment", "--plan", os.path.abspath(self.plan),
                    "--census", "registry/SKILL_CENSUS.yml")
        self.py("tools/kit/skills_index.py", "--write", must=True)  # pre-routing state
        self.regen(on_station=False)
        _kit.stage_paths(self.out)
        self.py("tools/gov/gen_manifest.py", "--write")
        _kit.stage_paths(self.out)
        # commit BEFORE the audit: checks that read `HEAD:<path>` (upstream_check's pinned trees) must see the
        # tree being audited, not its parent. A red audit STOPs with this commit left for inspection, untagged.
        self.commit("kit: commons + decision tree (main)")
        self.audit("main")
        self.git("tag", "commons-v1")

    def stations(self):
        order = _kit.stations_from_tree(self.out)
        have = set(os.listdir(os.path.join(self.build, "stations"))) if os.path.isdir(os.path.join(self.build, "stations")) else set()
        want = [s for s in order if (self.only is None or s in self.only)]
        missing = [s for s in want if s not in have]
        if missing:
            if self.strict:
                raise Stop("build/stations lacks %s" % missing)
            self.notes.append("stations absent from build, skipped: %s" % missing)
        extra = sorted(have - set(order))
        if extra:
            raise Stop("build/stations has stations not in the decision tree: %s" % extra)
        return [s for s in want if s in have]

    def step4(self, st):
        self.log("4 station/%s" % st)
        src = os.path.join(self.build, "stations", st)
        files = [f for f in _kit.list_files(src) if "__pycache__" not in f]
        main_files = set(x for x in self.git("ls-tree", "-r", "--name-only", "-z", "main").out.split("\0") if x)
        bad = []
        for f in files:
            if f in main_files:
                txt = _kit.git(self.out, "show", "main:" + f, check=False).out
                if not _kit.declares_generated(txt):
                    bad.append(f)
        if bad:
            raise Stop("station/%s overlay writes commons/main paths (branch discipline): %s" % (st, bad[:20]))
        self.git("switch", "-q", "-c", "station/" + st, "main")
        copied = _kit.copy_tree(src, self.out, skip_names=(".git", "__pycache__"))
        self.force_nested(copied)
        _kit.stage_paths(self.out)
        self.regen(on_station=True)
        _kit.stage_paths(self.out)
        # commit first (see step3): on a station the lanes exist only in this commit, and upstream_check
        # compares `git rev-parse HEAD:<lane>/<repo>` with the LOCK pin - before the commit HEAD is main.
        self.commit("station/%s: overlay" % st)
        self.audit("station/" + st)
        self.git("switch", "-q", "main")

    def step5(self, sts):
        self.log("5 main: station map + skills index; sync every station")
        self.py("tools/map/gen_station_map.py", "--write", must=self.strict)
        self.py("tools/kit/skills_index.py", "--write", "--from-git", self.out)
        _kit.stage_paths(self.out)
        self.py("tools/gov/gen_manifest.py", "--write", must=self.strict)
        _kit.stage_paths(self.out)
        self.py("tools/kit/kit_check.py", "tree", "--strict")
        if not self.fixture:
            self.py("tools/kit/kit_check.py", "registry")
        self.commit("kit: station map + skills index")
        for st in sts:
            self.git("switch", "-q", "station/" + st)
            p = _kit.run([sys.executable, "tools/kit/sync.py"], cwd=self.out, check=False)
            self.log("  sync station/%s -> %d %s" % (st, p.returncode, (p.out.strip().splitlines() or [""])[0]))
            if p.returncode != 0:
                raise Stop("sync failed on station/%s:\n%s" % (st, p.out[-3000:]))
        self.git("switch", "-q", "main")

    def step6(self, sts):
        self.log("6 verify")
        p = self.py("tools/kit/skills_index.py", "--check", "--from-git", self.out, must=False)
        if p is not None and p.returncode != 0:
            raise Stop("skills_index --check: unrouted census rows:\n%s" % p.out[-4000:])
        f = _kit.run(["git", "-C", self.out, "fsck", "--no-progress"], check=False)
        if f.returncode != 0:
            raise Stop("git fsck failed: %s" % f.err)
        br = sorted(x for x in self.git("for-each-ref", "--format=%(refname:short)", "refs/heads/").out.split())
        want = sorted(["main"] + ["station/" + s for s in sts])
        if br != want:
            raise Stop("branches %s != expected %s" % (br, want))
        for s in sts:
            if self.git("merge-base", "--is-ancestor", "main", "station/" + s, check=False).returncode != 0:
                raise Stop("main is not an ancestor of station/%s" % s)
        self.log("  branches: %d (main + %d stations), fsck clean, every station descends from main" % (len(br), len(sts)))

    def run(self):
        self.step1_2()
        self.step3()
        sts = self.stations()
        for st in sts:
            self.step4(st)
        self.step5(sts)
        self.step6(sts)
        for n in self.notes:
            self.log("  note: " + n)
        self.log("assemble: OK -> %s (%d branches)" % (self.out, len(sts) + 1))
        return 0


# ------------------------------------------------------------------ fixture
FIX_GEN = r'''"""fixture generator: gen/OUT.md lists src/*.txt"""
import os, sys
srcs = sorted(f for f in os.listdir("src") if f.endswith(".txt"))
out = "<!-- GENERATED by tools/gen.py — edit src/*.txt, then run python3 tools/gen.py --write -->\n" + "".join("- %s\n" % s for s in srcs)
if "--check" in sys.argv:
    sys.exit(0 if os.path.isfile("gen/OUT.md") and open("gen/OUT.md").read() == out else 1)
os.makedirs("gen", exist_ok=True)
open("gen/OUT.md", "w").write(out)
'''
FIX_AUDIT = r'''"""fixture station_audit: one MUST check (gen current) + main_purity."""
import os, subprocess, sys
bad = []
if subprocess.call([sys.executable, "tools/gen.py", "--check"]) != 0:
    bad.append("gen/OUT.md stale")
if not os.path.exists("station.json"):
    for p in ("router/skills.json", "repertoire"):
        if os.path.exists(p):
            bad.append("main_purity: station-only path on main: " + p)
print("station_audit: %d violation(s) · 0 worklist · denominator 2" % len(bad))
for b in bad: print("  " + b)
sys.exit(1 if bad else 0)
'''
FIX_MANIFEST = r'''"""fixture gen_manifest: sha256 of every commons file."""
import hashlib, json, os, subprocess, sys
STATION_ONLY = ("station.json", "router/skills.json", "repertoire/")
files = [f for f in subprocess.run(["git", "ls-files", "-z"], capture_output=True, text=True).stdout.split("\0") if f]
rows = {}
for f in sorted(set(files)):
    if f.startswith(STATION_ONLY) or f == "commons/MANIFEST.json" or not os.path.isfile(f):
        continue
    rows[f] = hashlib.sha256(open(f, "rb").read()).hexdigest()
doc = {"_generated_by": "tools/gov/gen_manifest.py", "paths": rows}
os.makedirs("commons", exist_ok=True)
open("commons/MANIFEST.json", "w").write(json.dumps(doc, indent=1, sort_keys=True) + "\n")
'''
FIX_STATION_MAP = r'''"""fixture gen_station_map: map/STATIONS.md from station/* branches."""
import os, subprocess
if __name__ == "__main__":  # importable without side effects (fix2-root: the seed loader imports generators)
    br = subprocess.run(["git", "for-each-ref", "--format=%(refname:short)", "refs/heads/station/"], capture_output=True, text=True).stdout.split()
    os.makedirs("map", exist_ok=True)
    open("map/STATIONS.md", "w").write("<!-- GENERATED by tools/map/gen_station_map.py — run python3 tools/map/gen_station_map.py --write -->\n| branch |\n|---|\n" + "".join("| %s |\n" % b for b in br))
'''
FIX_CENSUS = """meta:
  total_skill_files: 3
skills:
- id: 1:skills/a/SKILL.md
  repo: o/r
  repo_id: 1
  path: skills/a/SKILL.md
  name: a
  sha: aaaa
  mirror_of: null
- id: 1:.agents/skills/a/SKILL.md
  repo: o/r
  repo_id: 1
  path: .agents/skills/a/SKILL.md
  name: a
  sha: aaaa
  mirror_of: 1:skills/a/SKILL.md
- id: 2:s/c/SKILL.md
  repo: p/q
  repo_id: 2
  path: s/c/SKILL.md
  name: c
  sha: cccc
  mirror_of: null
"""


def make_fixture_build(build):
    def w(rel, txt):
        p = os.path.join(build, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(txt)
    # commons: one GENERATED file (gen/OUT.md) + one check (station_audit)
    w("commons/tools/gen.py", FIX_GEN)
    w("commons/tools/station_audit.py", FIX_AUDIT)
    w("commons/tools/gov/gen_manifest.py", FIX_MANIFEST)
    w("commons/tools/map/gen_station_map.py", FIX_STATION_MAP)
    w("commons/src/a.txt", "a\n")
    w("commons/gen/OUT.md", "<!-- GENERATED by tools/gen.py — stale on purpose; assemble regenerates -->\n")
    w("commons/router/intents.json", '{"intents": ["build"]}\n')
    w("commons/.gitignore", ".upstream/\n.cache/\n.station/\n.usage/\n__pycache__/\n")
    # root: the real kit tools + a 2-station tree
    for fn in sorted(os.listdir(KIT_DIR)):
        if fn.endswith((".py", ".sh")):
            dst = os.path.join(build, "root", "tools", "kit", fn)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(KIT_DIR, fn), dst)
    sts = ["alpha", "beta"]
    tree = "\n".join(["What am I about to do?"] + [
        "├─ Q%d about %s?\n│     └─ yes → station/%s" % (i, s, s) for i, s in enumerate(sts)])
    mer = "\n".join("  Q%d -- yes --> N%d[station/%s]" % (i, i, s) for i, s in enumerate(sts))
    table = "\n".join("| %s | `station/%s` | toy |" % (s, s) for s in sts)
    w("root/README.md", "# toy kit\n\n<!-- KIT_TREE:BEGIN -->\n```\n%s\n```\n<!-- KIT_TREE:END -->\n\n```mermaid\nflowchart TD\n%s\n```\n\n| station | branch | purpose |\n|---|---|---|\n%s\n" % (tree, mer, table))
    rows = [{"name": "station:" + s, "q": "Q%d" % i, "scope": "main", "contributed_by": "kit",
             "router": {"keywords": [s, s + "1", s + "2"], "phrases": [],
                        "first_move": {"inline_gather": "git worktree add ~/stations/%s station/%s" % (s, s)}}}
            for i, s in enumerate(sts)]
    w("root/router/kit_tree.json", json.dumps({"intents": rows}, indent=1) + "\n")
    w("root/registry/SKILL_CENSUS.yml", FIX_CENSUS)
    plan = {"skills_assignment": {"rows_format": ["census_id", "home", "kind", "route_to", "held_path", "copy"], "rows": [
        ["1:skills/a/SKILL.md", "alpha", "canonical", None, "repertoire/o~r/skills/a/SKILL.md", "dir"],
        ["1:.agents/skills/a/SKILL.md", "alpha", "mirror", "1:skills/a/SKILL.md", None, "none"],
        ["2:s/c/SKILL.md", "beta", "canonical", None, "repertoire/p~q/s/c/SKILL.md", "dir"]]}}
    w("plan.json", json.dumps(plan))
    # stations
    kw = ["k1", "k2", "k3"]
    w("stations/alpha/station.json", '{"name": "alpha"}\n')
    w("stations/alpha/src/alpha.txt", "alpha\n")
    w("stations/alpha/repertoire/o~r/skills/a/SKILL.md", "---\nname: a\n---\n")
    # a held tree's own .gitignore drops a held file (and the kit's root .gitignore drops a runtime dir)
    w("stations/alpha/repertoire/o~r/.gitignore", ".env\nexperimental/\n!keep.env\n")
    w("stations/alpha/repertoire/o~r/.env", "SLOT=\n")
    w("stations/alpha/repertoire/o~r/experimental/x.py", "print(1)\n")
    w("stations/alpha/.cache/runtime.txt", "runtime\n")
    w("stations/alpha/router/skills.json", json.dumps({"skills": [
        {"id": "1:skills/a/SKILL.md", "home": "alpha", "kind": "canonical", "path": "repertoire/o~r/skills/a/SKILL.md", "keywords": kw},
        {"id": "1:.agents/skills/a/SKILL.md", "home": "alpha", "kind": "mirror", "route_to": "1:skills/a/SKILL.md", "keywords": []}]}))
    w("stations/beta/station.json", '{"name": "beta"}\n')
    w("stations/beta/repertoire/p~q/s/c/SKILL.md", "---\nname: c\n---\n")
    w("stations/beta/router/skills.json", json.dumps({"skills": [
        {"id": "2:s/c/SKILL.md", "home": "beta", "kind": "canonical", "path": "repertoire/p~q/s/c/SKILL.md", "keywords": kw}]}))
    return os.path.join(build, "plan.json")


def fixture_assemble(out, log=print):
    tmp = tempfile.mkdtemp(prefix="kit-fixture-build-")
    build = os.path.join(tmp, "build")
    plan = make_fixture_build(build)
    try:
        return Assembler(build, out, plan=plan, strict=False, fixture=True, log=log).run()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _selftest():
    tmp = tempfile.mkdtemp(prefix="kit-assemble-")
    lines = []
    log = lines.append
    cwd0 = os.getcwd()
    try:
        # planted: run from an empty cwd; nothing the selftest does may write there (fix2-root: importing a
        # script-style generator for its render() wrote map/STATIONS.md into the caller's cwd = build/root)
        os.makedirs(os.path.join(tmp, "cwd"))
        os.chdir(os.path.join(tmp, "cwd"))
        out = os.path.join(tmp, "out")
        assert fixture_assemble(out, log=log) == 0, "\n".join(lines)
        g = lambda *a, **k: _kit.git(out, *a, **k)
        br = sorted(g("for-each-ref", "--format=%(refname:short)", "refs/heads/").out.split())
        assert br == ["main", "station/alpha", "station/beta"], br
        assert g("tag", "--list", "commons-v1").out.strip() == "commons-v1"
        # main is pure, stations carry their overlay, generated file regenerated on the station
        assert g("cat-file", "-e", "main:router/skills.json", check=False).returncode != 0, "main_purity"
        assert "- alpha.txt" in g("show", "station/alpha:gen/OUT.md").out, "station regenerated gen/OUT.md"
        assert "- alpha.txt" not in g("show", "main:gen/OUT.md").out
        idx = json.loads(g("show", "main:registry/skills_index.json").out)
        assert idx["counts"] == {"ROUTED": 3}, idx["counts"]
        assert "station/beta" in g("show", "main:map/STATIONS.md").out
        # D1: the station map exists at EVERY audit point: seeded in the step-3 commit (commons-v1, before any
        # branch), inherited by each station branch, re-rendered from real branches on main in step 5
        seed = g("show", "commons-v1:map/STATIONS.md").out
        assert "SEEDED from the plan's branch list" in seed and "station/alpha" in seed and "station/beta" in seed, seed
        assert _kit.declares_generated(seed), "seed declares GENERATED"
        assert "map/STATIONS.md" in json.loads(g("show", "commons-v1:commons/MANIFEST.json").out)["paths"], \
            "the seed is staged before the step-3 manifest"
        for b in ("station/alpha", "station/beta"):
            assert g("cat-file", "-e", b + ":map/STATIONS.md", check=False).returncode == 0, b + " lacks map/STATIONS.md"
        assert "SEEDED" not in g("show", "main:map/STATIONS.md").out, "step 5 replaces the seed with the real render"
        for ref in ("commons-v1", "main"):  # commons-v1 = the step-3 manifest, made before any commit
            man = json.loads(g("show", ref + ":commons/MANIFEST.json").out)["paths"]
            assert "tools/gen.py" in man and "README.md" in man and "SKILLS_INDEX.md" in man, \
                "%s MANIFEST must see the copied tree (tools walk git ls-files): %s" % (ref, sorted(man)[:10])
        # every overlay file a NESTED .gitignore drops is committed; the root .gitignore's runtime dirs are not
        for f in ("repertoire/o~r/.env", "repertoire/o~r/experimental/x.py", "repertoire/o~r/.gitignore"):
            assert g("cat-file", "-e", "station/alpha:" + f, check=False).returncode == 0, "station/alpha lacks " + f
        assert g("cat-file", "-e", "station/alpha:.cache/runtime.txt", check=False).returncode != 0, ".cache/ is the kit's runtime dir"
        msgs = g("log", "--format=%s", "main").out.splitlines()
        assert msgs[:2] == ["kit: station map + skills index", "kit: commons + decision tree (main)"], msgs

        # forced conflict in a GENERATED file -> resolved by regeneration
        def w(rel, txt):
            p = os.path.join(out, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "w").write(txt)
        w("src/main2.txt", "m\n")
        _kit.run([sys.executable, "tools/gen.py", "--write"], cwd=out)
        w("router/intents.json", '{"intents": ["build", "main-edit"]}\n')
        _kit.stage_paths(out)
        _kit.commit(out, "main: commons release 2")
        g("switch", "-q", "station/alpha")
        p = _kit.run([sys.executable, "tools/kit/sync.py"], cwd=out, check=False)
        assert p.returncode == 0, p.out + p.err
        assert "resolved by regeneration" in p.out, p.out
        o = open(os.path.join(out, "gen/OUT.md")).read()
        assert "- main2.txt" in o and "- alpha.txt" in o, o
        # forced conflict in a commons file -> abort
        g("switch", "-q", "station/beta")
        w("router/intents.json", '{"intents": ["build", "beta-edit"]}\n')
        _kit.stage_paths(out)
        _kit.commit(out, "beta edits a commons file (violation)")
        before = g("rev-parse", "HEAD").out.strip()
        p = _kit.run([sys.executable, "tools/kit/sync.py"], cwd=out, check=False)
        assert p.returncode == 1 and "ABORTED" in p.out, p.out
        assert g("rev-parse", "HEAD").out.strip() == before
        g("switch", "-q", "main")

        # refusal 1: non-empty out
        assert Assembler(tmp, out, strict=False, log=log).run_safe() == 1
        # refusal 2: a station overlay that writes a commons path
        build2 = os.path.join(tmp, "build2")
        plan2 = make_fixture_build(build2)
        with open(os.path.join(build2, "stations", "beta", "router", "intents.json"), "w") as f:
            f.write('{"intents": ["hijack"]}\n')
        rc = Assembler(build2, os.path.join(tmp, "out2"), plan=plan2, strict=False, fixture=True, log=log).run_safe()
        assert rc == 1 and any("branch discipline" in l for l in lines), "overlay onto a commons path must STOP"
        # refusal 3: root collides with commons
        build3 = os.path.join(tmp, "build3")
        plan3 = make_fixture_build(build3)
        shutil.copy2(os.path.join(build3, "commons", "router", "intents.json"), os.path.join(build3, "root", "router", "intents.json"))
        rc = Assembler(build3, os.path.join(tmp, "out3"), plan=plan3, strict=False, fixture=True, log=log).run_safe()
        assert rc == 1 and any("collide" in l for l in lines)
        # refusal 4: an unrouted census row fails step 6
        build4 = os.path.join(tmp, "build4")
        plan4 = make_fixture_build(build4)
        os.remove(os.path.join(build4, "stations", "beta", "router", "skills.json"))
        rc = Assembler(build4, os.path.join(tmp, "out4"), plan=plan4, strict=False, fixture=True, log=log).run_safe()
        assert rc == 1 and any("unrouted" in l for l in lines)
        # refusal 5: a plan whose branch list disagrees with the decision tree cannot seed the station map
        build5 = os.path.join(tmp, "build5")
        make_fixture_build(build5)
        bad_plan = os.path.join(tmp, "plan5.json")
        with open(bad_plan, "w") as f:
            json.dump({"kit": {"branches": ["main", "station/alpha", "station/gamma"]}}, f)
        try:
            seed_rows(os.path.join(build5, "root"), plan=bad_plan, build=build5)
            raise AssertionError("plan/tree branch mismatch must refuse the seed")
        except Stop:
            pass
        assert os.listdir(os.path.join(tmp, "cwd")) == [], "selftest wrote into its cwd: %s" % os.listdir(os.path.join(tmp, "cwd"))
        print("selftest OK (fixture: 3 branches, station map seeded before every audit, generated-conflict regenerated, "
              "commons-conflict aborted, 5 refusals, cwd untouched)")
        return 0
    except AssertionError:
        print("\n".join(lines[-60:]))
        raise
    finally:
        os.chdir(cwd0)
        shutil.rmtree(tmp, ignore_errors=True)


def _run_safe(self):
    try:
        return self.run()
    except Stop as e:
        self.log("assemble: STOP - %s" % e)
        return 1
    except _kit.KitError as e:
        self.log("assemble: git/tool failure - %s" % e)
        return 2


Assembler.run_safe = _run_safe


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build")
    ap.add_argument("--out")
    ap.add_argument("--stations")
    ap.add_argument("--plan")
    ap.add_argument("--no-strict", action="store_true")
    ap.add_argument("--fixture", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--seed-station-map", action="store_true")
    ap.add_argument("--root", default=_kit.REPO_ROOT_GUESS)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return _selftest()
    if a.seed_station_map:
        try:
            rc = seed_station_map(a.root, plan=a.plan, build=a.build, check=a.check)
        except (Stop, OSError, ValueError, KeyError) as e:
            print("seed_station_map: unreadable input / refused: %s" % e)
            return 2
        n = len(_kit.stations_from_tree(a.root))
        if a.check:
            print("seed_station_map: %s %s (%d stations)" % ("current" if rc == 0 else "DRIFT", STATION_MAP, n))
        else:
            print("seed_station_map: wrote %s (%d stations, pre-assembly seed)" % (STATION_MAP, n))
        return rc
    if a.fixture:
        if not a.out:
            print("--fixture needs --out")
            return 2
        tmp = tempfile.mkdtemp(prefix="kit-fixture-build-")
        try:
            build = os.path.join(tmp, "build")
            plan = make_fixture_build(build)
            return Assembler(build, a.out, plan=plan, strict=False, fixture=True).run_safe()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    if not (a.build and a.out):
        ap.print_help()
        return 2
    only = [s.strip() for s in a.stations.split(",")] if a.stations else None
    return Assembler(a.build, a.out, stations=only, plan=a.plan, strict=not a.no_strict).run_safe()


if __name__ == "__main__":
    sys.exit(main())
