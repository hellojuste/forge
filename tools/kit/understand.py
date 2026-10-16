#!/usr/bin/env python3
"""understand.py -- one command to decipher and remember any target: a ProjectAtlas index plus a grounded openwiki wiki,
kept in ONE shared memory location outside every station tree, with a manifest of what was indexed, when, at which
commit and with which tool versions.

owner: governance/rules.d/kit.json R-kit-understand (commons since reconcile-01 wave 2, DEC-core-0012; built on station
forge; imports tools/kit only; config: station.json "memory" over commons/defaults.json "memory" over the default below).
The TOOLS stay forge's: ProjectAtlas and openwiki are installed by station forge's setup_tool.py (its tool table); this
commons core finds them in the shared run root from any station and refuses, naming that command, when they are absent.

  understand.py <path | owner~repo | kit> [--atlas] [--wiki] [--refresh] [--dry-run]
      no --atlas/--wiki = both. A path is any directory (git repo or a folder of sources); owner~repo is a registry
      pin (bootstrapped, then checked out in a run tree at the pin); `kit` = the main ref plus every git worktree
      of this checkout (the kit and its stations), each its own memory.
      Memory: <root>/<slug>/ with manifest.json, atlas.db (projectatlas --db), wiki/ (openwiki pages) and src/
      (the copy openwiki writes into; the target itself is never written).
      --refresh  re-index only what changed since the manifest (commit or content hash); unchanged = skipped.
  understand.py --list                 every memory: slug, commit, indexed_at, atlas files/symbols, wiki pages
  understand.py --mcp <target>         the mcpServers JSON that serves this memory's atlas over MCP (stdio)
  understand.py --card                 one line per station.json "memory.targets" entry (for the SessionStart card)
  understand.py --check-wiki <target>  ownership + grounding: openwiki writes prose pages only; the kit's generators
                                       (map/*, SOLUTIONS, brain) stay the source of truth for indexes. Red when a page
                                       cites no source, cites a path absent at the indexed commit, or (kit targets)
                                       names a kit tool/skill/workflow path the kit's own map/atlas.json does not know.
  understand.py --check                the `understand` audit row (R-kit-understand): memory config well-formed, both tool
                                       keys pinned in registry/sources.json, and every mcp_optin.enabled tool known and
                                       telemetry-verified (an MCP server is never opted into unverified)
  understand.py --selftest
Tools are found where station forge's tools/station/setup_tool.py installs them (<run root>/*/<repo>@<sha7>/.kit-tool/setup.json at
the registry pin); a missing tool is a refusal naming `python3 tools/station/setup_tool.py <tool>`.
openwiki needs a model provider key from the station .env (names only are read here); without one the wiki part is
recorded as `blocked` in the manifest, never faked.
Earned by: operator 2026-10-16 "they also whole cloth are useful tools for deciphering and understanding anything and
keeping memory and context no?" (PRIME relay). Retires: per-workflow ad-hoc indexing of a target.
Exit: 0 done · 1 refused or a check red · 2 usage.
"""
import argparse
import datetime
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT_GUESS = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT_GUESS, "tools", "kit"))
import _kit  # noqa: E402
import bootstrap  # noqa: E402
import runtree  # noqa: E402

DEFAULTS = {"root": "~/.stable-kit/memory", "targets": []}
ATLAS_KEY = "styler-ai~ProjectAtlas"
WIKI_KEY = "langchain-ai~openwiki"
WIKI_KEYS = ["ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "BOB_API_KEY",
             "OPENAI_COMPATIBLE_API_KEY", "COPILOT_API_KEY"]  # openwiki src/config/constants.ts (provider keys)
# A wiki page cites evidence as a repository path in backticks or a markdown link to one (openwiki pages do both).
CITE = re.compile(r"`([A-Za-z0-9_.\-/]+\.[A-Za-z0-9]{1,8})(?::\d+(?:-\d+)?)?`|\]\((?!https?:)([^)#\s]+\.[A-Za-z0-9]{1,8})")
KIT_OWNED = re.compile(r"^(tools/.+\.py|\.claude/skills/[^/]+/SKILL\.md|\.claude/workflows/[^/]+\.js)$")
GENERATED = ("map/", "SKILLS_INDEX.md", "governance/OWNERSHIP.md")


def now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def config(root):
    cfg = dict(DEFAULTS)
    for p in (os.path.join(root, "commons", "defaults.json"), os.path.join(root, "station.json")):
        try:
            cfg.update(_kit.read_json(p).get("memory") or {})
        except (OSError, ValueError):
            pass
    cfg["root"] = os.path.abspath(os.path.expanduser(os.environ.get("STABLE_KIT_MEMORY") or cfg["root"]))
    return cfg


class Ctx:
    def __init__(self, root=ROOT_GUESS, mem_root=None, run_root=None, log=print, env_file=None):
        self.root = os.path.abspath(root)
        self.cfg = config(self.root)
        self.mem = os.path.abspath(mem_root) if mem_root else self.cfg["root"]
        self.rr = runtree.run_root(run_root)
        self.log = log
        self.env_file = env_file or os.path.join(self.root, ".env")

    def run(self, argv, cwd=None, env=None):
        e = dict(os.environ)
        e.update(env or {})
        try:
            p = subprocess.run(argv, cwd=cwd, env=e, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        except OSError as ex:
            return 127, str(ex)
        return p.returncode, p.stdout.decode("utf-8", "replace")


# ---------------------------------------------------------------- tools (as setup_tool.py installs them)
def pin(ctx, key):
    for s in _kit.read_json(os.path.join(ctx.root, "registry", "sources.json"))["sources"]:
        if s["key"] == key:
            return s
    raise KeyError("not a registry key: %s" % key)


def tool(ctx, key):
    """(wrapper, version) of the tool installed at the registry pin, or (None, reason)."""
    sha = pin(ctx, key)["sha"]
    for st in sorted(glob.glob(os.path.join(ctx.rr, "*", "*@" + sha[:7], ".kit-tool", "setup.json"))):
        try:
            s = _kit.read_json(st)
        except (OSError, ValueError):
            continue
        w = os.path.join(os.path.dirname(st), "kit-bin", os.path.basename(s.get("bin", "")).replace(".exe", "").replace(".cmd", ""))
        if s.get("key") == key and s.get("sha") == sha and os.path.isfile(w):
            return w, s.get("version")
    name = {ATLAS_KEY: "projectatlas", WIKI_KEY: "openwiki"}.get(key, key)
    return None, "%s is not set up at its pin; one command on station forge: python3 tools/station/setup_tool.py %s" % (name, name)


def bash():
    return shutil.which("bash") or "bash"


# ---------------------------------------------------------------- targets
def tree_hash(path):
    """Content identity of a non-git folder (paths + sizes + mtimes; cheap, changes when files change)."""
    h = hashlib.sha256()
    for dp, dns, fns in os.walk(path):
        dns[:] = sorted(d for d in dns if d not in (".git", "node_modules", ".projectatlas", "openwiki"))
        for f in sorted(fns):
            p = os.path.join(dp, f)
            try:
                st = os.stat(p)
            except OSError:
                continue
            h.update(("%s\0%d\0%d\n" % (os.path.relpath(p, path), st.st_size, int(st.st_mtime))).encode())
    return h.hexdigest()


def git_state(path):
    p = _kit.run(["git", "-C", path, "rev-parse", "HEAD"], check=False)
    if p.returncode != 0:
        return None, False
    dirty = bool(_kit.run(["git", "-C", path, "status", "--porcelain"], check=False).out.strip())
    return p.out.strip(), dirty


def resolve(ctx, target):
    """[(slug, kind, src, commit, identity)] -- `kit` expands to main + every worktree."""
    if target == "kit":
        out = []
        main = _kit.run(["git", "-C", ctx.root, "rev-parse", "main"], check=False).out.strip() \
            or _kit.run(["git", "-C", ctx.root, "rev-parse", "origin/claude/stable-kit-main"], check=False).out.strip()
        if main:
            out.append(("kit~main", "kit-ref", "main", main, main))
        wl = _kit.run(["git", "-C", ctx.root, "worktree", "list", "--porcelain"], check=False).out
        for blk in wl.strip().split("\n\n"):
            d = dict(l.split(" ", 1) for l in blk.splitlines() if " " in l)
            if "worktree" in d and "bare" not in blk.splitlines():
                br = d.get("branch", "detached").rsplit("/", 1)[-1]
                commit, dirty = git_state(d["worktree"])
                out.append(("kit~" + re.sub(r"[^A-Za-z0-9._-]", "-", br), "worktree", d["worktree"], commit,
                            commit + ("+dirty:" + tree_hash(d["worktree"])[:12] if dirty else "")))
        return out
    if "~" in target and not os.path.exists(target):
        row = pin(ctx, target)
        return [("%s@%s" % (target, row["sha"][:7]), "pin", target, row["sha"], row["sha"])]
    path = os.path.abspath(os.path.expanduser(target))
    if not os.path.isdir(path):
        raise KeyError("not a directory, registry key or `kit`: %s" % target)
    slug = "%s-%s" % (re.sub(r"[^A-Za-z0-9._-]", "-", os.path.basename(path.rstrip("/")) or "root"),
                      hashlib.sha256(path.encode()).hexdigest()[:8])
    commit, dirty = git_state(path)
    ident = (commit + ("+dirty:" + tree_hash(path)[:12] if dirty else "")) if commit else "tree:" + tree_hash(path)[:16]
    return [(slug, "path", path, commit, ident)]


def materialise(ctx, kind, src, commit, mdir, dry):
    """A readable source directory for the target (the target itself is only ever read)."""
    if kind == "path" or kind == "worktree":
        return src
    if kind == "pin":
        if dry:
            return "<run tree of %s>" % src
        row = pin(ctx, src)
        if bootstrap.run(ctx.root, [row], log=lambda *a: None) != 0:
            raise RuntimeError("bootstrap of %s failed: python3 tools/kit/bootstrap.py %s" % (src, src))
        msgs = []
        if runtree.add(ctx.root, src, rr=ctx.rr, log=msgs.append) != 0:
            raise RuntimeError("run tree: " + " | ".join(msgs))
        return runtree.tree_path(ctx.rr, runtree.station_for(ctx.root, src), src, row["sha"])
    # kit-ref: export the ref (no worktree metadata is added to the kit repo)
    dest = os.path.join(mdir, "ref-src")
    if dry:
        return dest
    stamp = os.path.join(dest, ".kit-ref")
    if not (os.path.isfile(stamp) and open(stamp).read().strip() == commit):
        shutil.rmtree(dest, ignore_errors=True)
        os.makedirs(dest)
        arc = subprocess.run(["git", "-C", ctx.root, "archive", "--format=tar", commit], stdout=subprocess.PIPE)
        subprocess.run(["tar", "-x", "-C", dest], input=arc.stdout, check=True)
        open(stamp, "w").write(commit + "\n")
    return dest


# ---------------------------------------------------------------- the two parts
def atlas(ctx, src, mdir, dry):
    w, ver = tool(ctx, ATLAS_KEY)
    if not w:
        return {"status": "refused", "reason": ver}
    db = os.path.join(mdir, "atlas.db")
    if dry:
        return {"status": "planned", "cmd": "bash %s --db %s scan %s" % (w, db, src)}
    rc, out = ctx.run([bash(), w, "--db", db, "--format", "json", "scan", src])
    if rc != 0:
        return {"status": "failed", "rc": rc, "tail": out.strip()[-400:]}
    stats = {}
    try:
        doc = json.loads(out[out.index("{"):])
        def walk(o, path=""):
            if isinstance(o, dict):
                for k, v in o.items():
                    walk(v, path + "." + k if path else k)
            elif isinstance(o, (int, float)) and not isinstance(o, bool):
                stats[path] = o
        walk(doc)
    except ValueError:
        pass
    keep = {k: v for k, v in stats.items() if re.search(r"(files|symbols|relations|summaries)$", k) and "symbols.symbols" in k
            or k.endswith(("files.indexed", "files.total", "symbols.parsed", "symbols.relations", "files.scanned"))}
    return {"status": "indexed", "db": db, "tool_version": ver, "stats": keep or dict(list(stats.items())[:12])}


def provider_keys(ctx):
    have = []
    try:
        for line in open(ctx.env_file, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if k.strip() in WIKI_KEYS and v.strip():
                    have.append(k.strip())
    except OSError:
        pass
    return have


def copy_source(src, dest):
    if os.path.isdir(os.path.join(src, ".git")) or os.path.isfile(os.path.join(src, ".git")):
        if not os.path.isdir(os.path.join(dest, ".git")):
            shutil.rmtree(dest, ignore_errors=True)
            subprocess.run(["git", "clone", "-q", "--local", "--no-hardlinks", src, dest], check=True)
        else:
            subprocess.run(["git", "-C", dest, "pull", "-q", "--ff-only"], check=False)
    else:
        keep = os.path.join(dest, "openwiki")
        saved = None
        if os.path.isdir(keep):
            saved = tempfile.mkdtemp()
            shutil.move(keep, os.path.join(saved, "openwiki"))
        shutil.rmtree(dest, ignore_errors=True)
        shutil.copytree(src, dest, ignore=shutil.ignore_patterns(".git", "node_modules", ".projectatlas"))
        if saved:
            shutil.move(os.path.join(saved, "openwiki"), keep)


def wiki(ctx, src, mdir, dry, refresh):
    w, ver = tool(ctx, WIKI_KEY)
    if not w:
        return {"status": "refused", "reason": ver}
    keys = provider_keys(ctx)
    if not keys:
        return {"status": "blocked", "reason": "no model provider key is set in %s (openwiki reads one of %s); fill one, then "
                "re-run with --wiki" % (os.path.relpath(ctx.env_file, ctx.root) if ctx.env_file.startswith(ctx.root) else ctx.env_file,
                                        ", ".join(WIKI_KEYS[:4]))}
    work = os.path.join(mdir, "src")
    pages_dir = os.path.join(work, "openwiki")
    mode = "--update" if os.path.isdir(pages_dir) and refresh else "--init"
    if dry:
        return {"status": "planned", "cmd": "cd %s && bash %s code %s --print" % (work, w, mode)}
    copy_source(src, work)
    rc, out = ctx.run([bash(), w, "code", mode, "--print",
                       "Every page cites the repository files it describes (path in backticks); use mermaid for flows."], cwd=work)
    if rc != 0:
        return {"status": "failed", "rc": rc, "tail": out.strip()[-400:], "keys": keys}
    pages = sorted(os.path.relpath(p, pages_dir) for p in glob.glob(os.path.join(pages_dir, "**", "*.md"), recursive=True))
    link = os.path.join(mdir, "wiki")
    if not os.path.exists(link):
        try:
            os.symlink(pages_dir, link)
        except OSError:
            pass
    return {"status": "generated", "mode": mode, "pages": len(pages), "dir": pages_dir, "tool_version": ver, "keys": keys}


# ---------------------------------------------------------------- one target
def understand(ctx, target, do_atlas=True, do_wiki=True, refresh=False, dry=False):
    rc = 0
    for slug, kind, src, commit, ident in resolve(ctx, target):
        mdir = os.path.join(ctx.mem, slug)
        mp = os.path.join(mdir, "manifest.json")
        old = {}
        if os.path.isfile(mp):
            try:
                old = _kit.read_json(mp)
            except (OSError, ValueError):
                old = {}
        wanted = [p for p, w in (("atlas", do_atlas), ("wiki", do_wiki)) if w]
        done = [p for p in wanted if (old.get(p) or {}).get("status") in ("indexed", "generated")]
        if old and not refresh and not dry and done == wanted:
            ctx.log("%s: memory exists (indexed %s at %s); --refresh re-indexes what changed" % (slug, old.get("indexed_at"), str(old.get("commit"))[:12]))
            continue
        man = dict(old) or {"_generated_by": "tools/kit/understand.py", "slug": slug, "target": target if target != "kit" else slug,
                            "kind": kind, "created_at": now()}
        man.update({"source": src, "commit": commit, "identity": ident, "memory": mdir})
        if not dry:
            os.makedirs(mdir, exist_ok=True)
        try:
            real = materialise(ctx, kind, src, commit, mdir, dry)
        except (RuntimeError, OSError, subprocess.CalledProcessError, KeyError) as e:
            ctx.log("%s: refused -- %s" % (slug, e))
            rc = 1
            continue
        man["read_from"] = real
        unchanged = bool(old) and old.get("identity") == ident  # a part not done yet (refused/blocked) is always retried
        for part, want, fn in (("atlas", do_atlas, lambda: atlas(ctx, real, mdir, dry)),
                               ("wiki", do_wiki, lambda: wiki(ctx, real, mdir, dry, refresh))):
            if not want:
                continue
            prev = old.get(part) or {}
            if unchanged and prev.get("status") in ("indexed", "generated"):
                ctx.log("%s: %s unchanged since %s (%s) -- skipped" % (slug, part, prev.get("at"), str(commit)[:12]))
                continue
            res = fn()
            res["at"] = now()
            res["commit"] = commit
            man[part] = res
            ctx.log("%s: %s %s%s" % (slug, part, res["status"], (" -- " + res["reason"]) if res.get("reason") else
                                     (" · " + json.dumps(res.get("stats") or res.get("pages") or res.get("cmd") or "")[:160])))
            if res["status"] in ("refused", "failed"):
                rc = 1
        if dry:
            continue
        man["indexed_at"] = now()
        _kit.write_json(mp, man)
        ctx.log("%s: memory %s" % (slug, mdir))
    return rc


# ---------------------------------------------------------------- ownership + grounding check
def kit_known_paths(root):
    p = os.path.join(root, "map", "atlas.json")
    try:
        doc = _kit.read_json(p)
    except (OSError, ValueError):
        return None
    text = json.dumps(doc)
    return set(re.findall(r'"((?:tools/[^"]+\.py)|(?:\.claude/skills/[^"/]+/SKILL\.md)|(?:\.claude/workflows/[^"/]+\.js))"', text))


def check_wiki(ctx, pages_dir, src, kit_root=None, log=print):
    """Violations: a page with no citation; a cited path absent from the source; (kit) a kit-owned path the kit's atlas
    does not know; any page written over a generated index path."""
    viol, n = [], 0
    known = kit_known_paths(kit_root) if kit_root else None
    for p in sorted(glob.glob(os.path.join(pages_dir, "**", "*.md"), recursive=True)):
        rel = os.path.relpath(p, pages_dir)
        n += 1
        if rel.startswith(GENERATED) or rel in GENERATED:
            viol.append("%s: openwiki wrote over a generated index path (the kit's generator owns it)" % rel)
        text = open(p, encoding="utf-8", errors="replace").read()
        cites = [a or b for a, b in CITE.findall(text)]
        cites = [c.lstrip("./") for c in cites if not c.startswith(("http", "#"))]
        if not cites:
            viol.append("%s: no source evidence cited (grounding)" % rel)
            continue
        for c in sorted(set(cites)):
            if not os.path.exists(os.path.join(src, c)) and not os.path.exists(os.path.join(pages_dir, c)):
                viol.append("%s: cites %s, absent at the indexed commit" % (rel, c))
            elif known is not None and KIT_OWNED.match(c) and c not in known:
                viol.append("%s: names %s, which the kit's map/atlas.json does not know (generators are the index owner)" % (rel, c))
    log(_kit.headline("wiki_ownership", len(viol), 0, n))
    for v in viol:
        log("  " + v)
    return 1 if viol else 0


# ---------------------------------------------------------------- list / mcp / card
def memories(ctx):
    out = []
    for mp in sorted(glob.glob(os.path.join(ctx.mem, "*", "manifest.json"))):
        try:
            out.append(_kit.read_json(mp))
        except (OSError, ValueError):
            pass
    return out


def mcp_snippet(ctx, target):
    w, ver = tool(ctx, ATLAS_KEY)
    if not w:
        return None, ver
    servers = {}
    for slug, *_ in resolve(ctx, target):
        db = os.path.join(ctx.mem, slug, "atlas.db")
        servers["atlas-" + slug.replace("~", "-").replace("@", "-")] = {
            "command": "bash", "args": [w, "--db", db, "mcp"],
            "env": {"PROJECTATLAS_NO_TELEMETRY": "1"},
            "_source": "understand.py --mcp %s (projectatlas %s; stdio; `projectatlas mcp`, README.md:51)" % (target, ver)}
    return {"mcpServers": servers}, None


def card(ctx):
    lines = []
    by = {m.get("slug"): m for m in memories(ctx)}
    for t in ctx.cfg.get("targets") or []:
        try:
            slugs = [s for s, *_ in resolve(ctx, t)]
        except (KeyError, OSError, ValueError):
            slugs = []
        for s in slugs:
            m = by.get(s)
            if m:
                a, wk = m.get("atlas") or {}, m.get("wiki") or {}
                lines.append("MEMORY %s · atlas %s · wiki %s · %s" % (s, a.get("status", "-"), wk.get("status", "-"), os.path.join(ctx.mem, s)))
            else:
                lines.append("MEMORY %s · none yet: python3 tools/kit/understand.py %s" % (s, t))
    return lines


# ---------------------------------------------------------------- selftest
STUB_ATLAS = """#!/bin/sh
# stub projectatlas: --db DB [--format json] scan SRC
db=""; while [ $# -gt 0 ]; do case "$1" in --db) db="$2"; shift 2;; --format) shift 2;; scan) src="$2"; shift 2;; mcp) echo mcp; exit 0;; *) shift;; esac; done
n=$(find "$src" -type f -not -path '*/.git/*' | wc -l | tr -d ' ')
echo "scanned $src" >> "$db"
echo "{\\"files\\": {\\"indexed\\": $n}, \\"symbols\\": {\\"parsed\\": $n, \\"symbols\\": 7, \\"relations\\": 3}}"
"""
STUB_WIKI = """#!/bin/sh
# stub openwiki: code --init|--update --print MSG (cwd = the copy)
mkdir -p openwiki
printf '# Overview\\n\\nThe entry point is `main.py` (see [it](main.py)).\\n' > openwiki/index.md
echo "$2" > openwiki/.mode
"""


def _install_stub(rr, key, sha, cli, body):
    pre = os.path.join(rr, "forge", "%s@%s" % (key.split("~")[1], sha[:7]), ".kit-tool")
    os.makedirs(os.path.join(pre, "kit-bin"), exist_ok=True)
    w = os.path.join(pre, "kit-bin", cli)
    open(w, "w").write(body)
    os.chmod(w, 0o755)
    _kit.write_json(os.path.join(pre, "setup.json"), {"key": key, "sha": sha, "version": "stub-1", "bin": os.path.join(pre, "bin", cli)})


def _selftest_check():
    import contextlib
    import io
    tmp = tempfile.mkdtemp()
    try:
        r = os.path.join(tmp, "k")
        os.makedirs(os.path.join(r, "registry"))
        os.makedirs(os.path.join(r, "commons"))
        _kit.write_json(os.path.join(r, "registry", "sources.json"), {"sources": [{"key": ATLAS_KEY}, {"key": WIKI_KEY}]})
        _kit.write_json(os.path.join(r, "registry", "telemetry.json"), {"telemetry": [{"repo": "styler-ai/ProjectAtlas", "verified": False}]})
        _kit.write_json(os.path.join(r, "commons", "defaults.json"), {"memory": {"targets": []}, "mcp_optin": {"enabled": []}})
        q = lambda: contextlib.redirect_stdout(io.StringIO())
        with q():
            assert kit_check(r) == 0, "clean config is green"
        _kit.write_json(os.path.join(r, "station.json"), {"mcp_optin": {"enabled": ["projectatlas"]}})
        with q():
            assert kit_check(r) == 1, "an MCP opt-in for an unverified telemetry row is red"
        _kit.write_json(os.path.join(r, "station.json"), {"memory": {"targets": [""]}})
        with q():
            assert kit_check(r) == 1, "an empty target is red"
        _kit.write_json(os.path.join(r, "registry", "sources.json"), {"sources": [{"key": ATLAS_KEY}]})
        os.remove(os.path.join(r, "station.json"))
        with q():
            assert kit_check(r) == 1, "a missing wiki pin is red"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 4


def _selftest():
    tmp = tempfile.mkdtemp(prefix="kit-understand-")
    try:
        root = os.path.join(tmp, "kit")
        os.makedirs(os.path.join(root, "registry"))
        sha_a, sha_w = "a" * 40, "b" * 40
        _kit.write_json(os.path.join(root, "registry", "sources.json"), {"sources": [
            {"key": ATLAS_KEY, "sha": sha_a, "url": "x"}, {"key": WIKI_KEY, "sha": sha_w, "url": "x"}]})
        _kit.write_json(os.path.join(root, "registry", "homes.json"), {"homes": []})
        _kit.write_json(os.path.join(root, "station.json"), {"memory": {"targets": []}})
        open(os.path.join(root, ".env"), "w").write("ANTHROPIC_API_KEY=\n")
        rr, mem = os.path.join(tmp, "run"), os.path.join(tmp, "mem")
        lines = []
        c = Ctx(root, mem_root=mem, run_root=rr, log=lines.append)
        tgt = os.path.join(tmp, "target")
        os.makedirs(tgt)
        open(os.path.join(tgt, "main.py"), "w").write("print(1)\n")
        _kit.run(["git", "init", "-q", "-b", "main", tgt])
        _kit.fixture_git_config(tgt)
        _kit.stage_paths(tgt)
        _kit.commit(tgt, "one")
        cases = 0
        # 1. no tools set up -> refused, naming the one setup command each
        assert understand(c, tgt) == 1
        assert any("python3 tools/station/setup_tool.py projectatlas" in l for l in lines), lines
        cases += 1
        _install_stub(rr, ATLAS_KEY, sha_a, "projectatlas", STUB_ATLAS)
        _install_stub(rr, WIKI_KEY, sha_w, "openwiki", STUB_WIKI)
        # 2. atlas indexed, wiki blocked (no provider key) -> manifest says so, target untouched
        lines.clear()
        assert understand(c, tgt) == 0, lines
        slug = resolve(c, tgt)[0][0]
        man = _kit.read_json(os.path.join(mem, slug, "manifest.json"))
        assert man["atlas"]["status"] == "indexed" and man["atlas"]["tool_version"] == "stub-1", man
        assert man["wiki"]["status"] == "blocked" and "ANTHROPIC_API_KEY" in man["wiki"]["reason"], man
        assert man["commit"] == _kit.git_out(tgt, "rev-parse", "HEAD")
        assert sorted(os.listdir(tgt)) == [".git", "main.py"], "the target is only read"
        assert not _kit.run(["git", "-C", tgt, "status", "--porcelain"]).out.strip()
        cases += 1
        # 3. second run -> exists; --refresh with nothing changed -> skipped
        lines.clear()
        assert understand(c, tgt) == 0 and any("atlas unchanged" in l for l in lines), "done part skipped: %s" % lines
        assert any("wiki blocked" in l for l in lines), "a blocked part is retried on every run: %s" % lines
        lines.clear()
        assert understand(c, tgt, do_wiki=False) == 0 and any("memory exists" in l for l in lines), lines
        lines.clear()
        assert understand(c, tgt, refresh=True) == 0 and any("atlas unchanged" in l for l in lines), lines
        cases += 1
        # 4. a new commit -> --refresh re-indexes; a provider key -> wiki generated on the COPY
        open(os.path.join(tgt, "lib.py"), "w").write("x = 2\n")
        _kit.stage_paths(tgt)
        _kit.commit(tgt, "two")
        open(os.path.join(root, ".env"), "w").write("ANTHROPIC_API_KEY=sk-test-never-printed\n")
        lines.clear()
        assert understand(c, tgt, refresh=True) == 0, lines
        man = _kit.read_json(os.path.join(mem, slug, "manifest.json"))
        assert man["atlas"]["commit"] == _kit.git_out(tgt, "rev-parse", "HEAD") and man["wiki"]["status"] == "generated", man
        assert man["wiki"]["pages"] == 1 and not os.path.exists(os.path.join(tgt, "openwiki")), "pages live in memory, not the target"
        assert not any("sk-test" in l for l in lines) and "sk-test" not in json.dumps(man)
        cases += 1
        # 5. ownership + grounding check: the generated page is grounded; planted defects go red
        pages = man["wiki"]["dir"]
        assert check_wiki(c, pages, tgt, log=lines.append) == 0
        open(os.path.join(pages, "ungrounded.md"), "w").write("# Thoughts\n\nThis module is elegant.\n")
        assert check_wiki(c, pages, tgt, log=lambda *a: None) == 1
        os.remove(os.path.join(pages, "ungrounded.md"))
        open(os.path.join(pages, "ghost.md"), "w").write("See `src/ghost.py` for details.\n")
        assert check_wiki(c, pages, tgt, log=lambda *a: None) == 1
        os.remove(os.path.join(pages, "ghost.md"))
        kit = os.path.join(tmp, "kitsrc")
        os.makedirs(os.path.join(kit, "tools", "x"))
        os.makedirs(os.path.join(kit, "map"))
        open(os.path.join(kit, "tools", "x", "known.py"), "w").write("")
        open(os.path.join(kit, "tools", "x", "stray.py"), "w").write("")
        _kit.write_json(os.path.join(kit, "map", "atlas.json"), {"nodes": [{"path": "tools/x/known.py"}]})
        kp = os.path.join(tmp, "kitpages")
        os.makedirs(os.path.join(kp, "map"))
        open(os.path.join(kp, "tools.md"), "w").write("Uses `tools/x/known.py`.\n")
        assert check_wiki(c, kp, kit, kit_root=kit, log=lambda *a: None) == 0
        open(os.path.join(kp, "tools.md"), "a").write("Also `tools/x/stray.py`.\n")
        assert check_wiki(c, kp, kit, kit_root=kit, log=lambda *a: None) == 1, "a kit path the generators do not know"
        open(os.path.join(kp, "tools.md"), "w").write("Uses `tools/x/known.py`.\n")
        open(os.path.join(kp, "map", "SOLUTIONS.md"), "w").write("`tools/x/known.py`\n")
        assert check_wiki(c, kp, kit, kit_root=kit, log=lambda *a: None) == 1, "a page over a generated index path"
        cases += 1
        # 6. a folder of sources (no git) is a target too; mcp snippet points at its atlas; card lists configured targets
        folder = os.path.join(tmp, "notes")
        os.makedirs(folder)
        open(os.path.join(folder, "a.md"), "w").write("# a\n")
        lines.clear()
        assert understand(c, folder, do_wiki=False) == 0, lines
        fslug = resolve(c, folder)[0][0]
        assert _kit.read_json(os.path.join(mem, fslug, "manifest.json"))["identity"].startswith("tree:")
        snip, why = mcp_snippet(c, folder)
        srv = list(snip["mcpServers"].values())[0]
        assert srv["args"][-1] == "mcp" and srv["args"][2].endswith(os.path.join(fslug, "atlas.db")), snip
        _kit.write_json(os.path.join(root, "station.json"), {"memory": {"targets": [folder, os.path.join(tmp, "nope-dir-absent")]}})
        c2 = Ctx(root, mem_root=mem, run_root=rr, log=lambda *a: None)
        cl = card(c2)
        assert len(cl) == 1 and cl[0].startswith("MEMORY " + fslug), cl
        cases += 1
        # 7. config: station.json memory.root over the default; STABLE_KIT_MEMORY over both
        _kit.write_json(os.path.join(root, "station.json"), {"memory": {"root": os.path.join(tmp, "m2")}})
        assert Ctx(root).mem == os.path.join(tmp, "m2")
        os.environ["STABLE_KIT_MEMORY"] = os.path.join(tmp, "m3")
        try:
            assert Ctx(root).mem == os.path.join(tmp, "m3")
        finally:
            os.environ.pop("STABLE_KIT_MEMORY")
        cases += 1
        cases += _selftest_check()
        print("understand selftest OK (%d cases: tools missing, atlas + blocked wiki, exists/refresh skip, new commit + "
              "wiki on the copy, ownership/grounding check, folder target + mcp + card, config precedence, "
              "--check clean / unverified MCP opt-in / empty target / missing pin)" % cases)
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


MCP_TOOLS = {"projectatlas": ATLAS_KEY}


def kit_check(root):
    """Headline check; never touches the memory dir or the network."""
    viol = []
    cfg = config(root)
    if not isinstance(cfg.get("targets"), list) or not all(isinstance(x, str) and x.strip() for x in cfg["targets"]):
        viol.append("memory.targets must be a list of non-empty strings (path | owner~repo | kit)")
    keys = {s.get("key") for s in _kit.read_json(os.path.join(root, "registry", "sources.json"))["sources"]}
    for k in (ATLAS_KEY, WIKI_KEY):
        if k not in keys:
            viol.append("registry/sources.json has no pin for %s" % k)
    opt = {}
    for p in (os.path.join(root, "commons", "defaults.json"), os.path.join(root, "station.json")):
        try:
            opt.update(_kit.read_json(p).get("mcp_optin") or {})
        except (OSError, ValueError):
            pass
    enabled = opt.get("enabled") or []
    tel = {}
    try:
        tel = {r.get("repo"): r for r in _kit.read_json(os.path.join(root, "registry", "telemetry.json")).get("telemetry", [])}
    except (OSError, ValueError):
        pass
    for name in enabled:
        if name not in MCP_TOOLS:
            viol.append("mcp_optin.enabled names %r, not one of %s" % (name, sorted(MCP_TOOLS)))
            continue
        repo = MCP_TOOLS[name].replace("~", "/")
        if (tel.get(repo) or {}).get("verified") is not True:
            viol.append("mcp_optin.enabled names %s but its registry/telemetry.json row (%s) is not verified" % (name, repo))
    print("understand: %d violation(s) · 0 worklist · denominator %d" % (len(viol), 3 + len(enabled)))
    for v in viol:
        print("  VIOLATION " + v)
    return 1 if viol else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", nargs="?")
    ap.add_argument("--atlas", action="store_true")
    ap.add_argument("--wiki", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--mcp", metavar="TARGET")
    ap.add_argument("--card", action="store_true")
    ap.add_argument("--check-wiki", metavar="TARGET")
    ap.add_argument("--root", default=ROOT_GUESS)
    ap.add_argument("--memory-root")
    ap.add_argument("--run-root")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return _selftest()
    if a.check:
        return kit_check(os.path.abspath(a.root))
    ctx = Ctx(a.root, mem_root=a.memory_root, run_root=a.run_root)
    try:
        if a.list:
            ms = memories(ctx)
            for m in ms:
                at, wk = m.get("atlas") or {}, m.get("wiki") or {}
                print("  %-40s %-12s %s · atlas %s %s · wiki %s %s" % (m.get("slug"), str(m.get("commit"))[:12], m.get("indexed_at"),
                      at.get("status", "-"), json.dumps(at.get("stats", ""))[:80], wk.get("status", "-"), wk.get("pages", "")))
            print("understand: %d memor%s in %s" % (len(ms), "y" if len(ms) == 1 else "ies", ctx.mem))
            return 0
        if a.card:
            for l in card(ctx):
                print(l)
            return 0
        if a.mcp:
            snip, why = mcp_snippet(ctx, a.mcp)
            if not snip:
                print("understand: refused -- " + why)
                return 1
            print(json.dumps(snip, indent=1))
            return 0
        if a.check_wiki:
            rc = 0
            for slug, kind, src, commit, ident in resolve(ctx, a.check_wiki):
                m = os.path.join(ctx.mem, slug, "manifest.json")
                man = _kit.read_json(m) if os.path.isfile(m) else {}
                wk = man.get("wiki") or {}
                if wk.get("status") != "generated":
                    print("%s: no generated wiki to check (wiki status %s)" % (slug, wk.get("status", "absent")))
                    continue
                rc = max(rc, check_wiki(ctx, wk["dir"], man.get("read_from", src),
                                        kit_root=man.get("read_from") if slug.startswith("kit~") else None))
            return rc
        if not a.target:
            ap.print_help()
            return 2
        both = not (a.atlas or a.wiki)
        return understand(ctx, a.target, do_atlas=a.atlas or both, do_wiki=a.wiki or both, refresh=a.refresh, dry=a.dry_run)
    except KeyError as e:
        print("understand: %s" % e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
