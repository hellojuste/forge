"""_gov.py -- the governance kernel shared by every tools/gov script and tools/station_audit.py.

owner: governance/rules.json (R-gov-kernel) . stdlib only . Python 3.9+

What lives here (one copy, imported by path by every governance script):
  * root resolution (--root, else git toplevel, else cwd) and GOV_DIR = ROOT / "governance"
  * the overlay loader: <commons file> + <fragment dir>/*.json (+ station.json); a missing
    station.json means "I am on main, station core" (DEC-core-0007, branch discipline)
  * the effective config: commons/defaults.json overridden key-by-key by station.json
  * the Markdown register parser (## <ID> . <date> . <subject> + key: value lines)
  * heading resolution BY TEXT (never by line number, LEAN LL-30)
  * the headline every check prints first: "<check>: <n> violation(s) . <m> worklist . denominator <d>"
  * a minimal JSON-schema validator (type, required, enum, pattern, items, properties)
  * the GENERATED declaration test (owner: tools/map/_common.py GEN_DECL, imported by path when
    present; the fallback below is the same two lines, used only in fixtures without the map tools)
  * the tracked-file walk and a ** glob matcher
  * ONE fixture builder, make_station(), used by every governance selftest

Earned by: lettuce kept parsers per audit script and three of them disagreed on the header grammar
(PROGRAMME_GOVERNANCE 1.2); one kernel means one grammar.
"""
import fnmatch
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SEP = "·"  # the middle dot used in headlines and register headings
KIT_SRC = Path(__file__).resolve().parents[2]  # the tree this copy of _gov.py was installed in

HEADLINE_RE = re.compile(r"^(\S+): (\d+) violation\(s\) · (\d+) worklist · denominator (\d+)\s*$")
ROW_HEAD_RE = re.compile(r"^## ((?:DEC|L|DEF)-(?:[a-z][a-z0-9-]*-)?\d{4})\s*(?:·|--|—)\s*(.*)$")
REGISTER_ID_RE = re.compile(r"\b(?:DEC|L|DEF)-(?:[a-z][a-z0-9-]*-)?\d{4}\b|#\d+")
IGNORED_DIRS = {".git", ".upstream", ".cache", ".station", ".usage", "__pycache__", "node_modules"}


class GovError(Exception):
    """Unreadable input: callers exit 2, never report an empty read as clean."""


def setup_io():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


# ---------------------------------------------------------------- root, git
def git(root, *args, check=False, text=True, input_=None):
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, input=input_,
                       encoding="utf-8" if text else None, errors="replace" if text else None)
    if check and r.returncode != 0:
        raise GovError("git %s failed: %s" % (" ".join(args), (r.stderr or "").strip()[:200]))
    return r


def find_root(arg=None):
    if arg:
        return Path(arg).resolve()
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        return Path(r.stdout.strip()).resolve()
    return Path.cwd().resolve()


def is_git(root):
    return git(root, "rev-parse", "--is-inside-work-tree").returncode == 0


def has_head(root):
    return git(root, "rev-parse", "--verify", "-q", "HEAD").returncode == 0


def show(root, rev, rel):
    """Text of <rev>:<rel>, or None when absent."""
    r = git(root, "show", "%s:%s" % (rev, rel))
    return r.stdout if r.returncode == 0 else None


# ---------------------------------------------------------------- json + overlay
def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise GovError("missing: %s" % path)
    except (OSError, ValueError) as e:
        raise GovError("unreadable %s: %s" % (path, e))


def dump_json(obj):
    return json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def fragments(root, frag_dir):
    d = Path(root) / frag_dir
    if not d.is_dir():
        return []
    return sorted(p for p in d.glob("*.json") if not p.name.endswith(".selftest.json"))


def load_rows(root, base_rel, frag_dir, key, optional_base=False):
    """Rows under `key` from the commons file plus every fragment, each tagged with its source."""
    rows = []
    base = Path(root) / base_rel
    if base.exists() or not optional_base:
        data = load_json(base)
        for r in data.get(key, []):
            r = dict(r)
            r["_src"] = base_rel
            rows.append(r)
    for p in fragments(root, frag_dir):
        data = load_json(p)
        for r in data.get(key, []):
            r = dict(r)
            r["_src"] = str(p.relative_to(root))
            rows.append(r)
    return rows


def deep_merge(a, b):
    out = dict(a)
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def station_json(root):
    p = Path(root) / "station.json"
    return load_json(p) if p.exists() else None


def station_name(root):
    s = station_json(root)
    return (s or {}).get("name", "core") if s else "core"


def config(root):
    """commons/defaults.json overridden key-by-key by station.json (absent -> main, station core)."""
    d = Path(root) / "commons" / "defaults.json"
    base = load_json(d) if d.exists() else {}
    s = station_json(root)
    cfg = deep_merge(base, s or {})
    cfg["name"] = (s or {}).get("name", "core")
    mods = []
    for src in (base, s or {}):  # hooks.<Event> lists are a UNION (commons modules + station modules)
        for m in ((src.get("hooks") or {}).get("PreToolUse") or []):
            if m not in mods:
                mods.append(m)
    cfg["hooks"] = dict(cfg.get("hooks") or {}, PreToolUse=mods)
    g = dict(cfg.get("gov", {}))
    knob = (cfg.get("knobs") or {}).get("gov", "standard")
    budgets = cfg.get("claude_md_budget") or {}
    if "claude_md_budget" not in g and isinstance(budgets, dict) and knob in budgets:
        g["claude_md_budget"] = budgets[knob]
    cfg["gov"] = g
    return cfg


# ---------------------------------------------------------------- branch discipline (KIT_PLAN 3.3)
COMMONS_SKILLS = {"closeout", "handoff", "checkpoint", "summon", "tier", "upstream-intake"}
COMMONS_WORKFLOWS = {"_template", "orient"}
STATION_ONLY = [
    "station.json", "STATION.md", ".claude/rules/station.md", ".env", ".env.example", ".mcp.json",
    ".mcp.local.example.json", "NOTICE.md", "QUARANTINE.md", "upstream/**", "repertoire/**", "study/**",
    "nc-lane/**", "router/intents.d/station*.json", "router/skills*.json", "router/REASSIGN.md",
    "governance/checks.d/station.json", "governance/rules.d/station.json", "governance/STATION_*.md",
    ".claude/hooks/station/**", "tools/station/**", "map/station_*.json", "brain/brain.json",
    "work/**", "engagements/**", "notes/**",
]
APPEND_ONLY = ["brain/considered.jsonl", "brain/surface.jsonl"]


def station_only(path):
    """True when <path> is a station-only path (never on main, never in commons/MANIFEST.json)."""
    if any_match(path, STATION_ONLY):
        return True
    parts = path.split("/")
    if path.startswith(".claude/skills/") and len(parts) >= 3 and parts[2] not in COMMONS_SKILLS:
        return True
    if path.startswith(".claude/workflows/") and len(parts) == 3 and parts[2].endswith(".js") \
            and parts[2][:-3] not in COMMONS_WORKFLOWS:
        return True
    if path.startswith("brain/nodes/") and len(parts) >= 4 and not parts[-1].startswith("core-"):
        return True
    return False


# ---------------------------------------------------------------- headline
def headline(name, n, m, d):
    return "%s: %d violation(s) %s %d worklist %s denominator %d" % (name, n, SEP, m, SEP, d)


def parse_headline(text):
    first = (text or "").splitlines()[0] if (text or "").strip() else ""
    m = HEADLINE_RE.match(first)
    if not m:
        return None
    return {"name": m.group(1), "violations": int(m.group(2)), "worklist": int(m.group(3)),
            "denominator": int(m.group(4))}


# ---------------------------------------------------------------- markdown registers
def parse_rows(text):
    """Register rows: {'id','head','fields':{k:v},'body':[lines]} in file order."""
    rows, cur = [], None
    for line in text.splitlines():
        m = ROW_HEAD_RE.match(line)
        if m:
            cur = {"id": m.group(1), "head": m.group(2).strip(), "fields": {}, "body": []}
            rows.append(cur)
            continue
        if line.startswith("## ") or line.startswith("# "):
            cur = None
            continue
        if cur is None:
            continue
        cur["body"].append(line)
        fm = re.match(r"^([a-z_]+):\s?(.*)$", line)
        if fm and fm.group(1) not in cur["fields"]:
            cur["fields"][fm.group(1)] = fm.group(2).strip()
    return rows


def id_parts(rid):
    m = re.match(r"^(DEC|L|DEF)-(?:([a-z][a-z0-9-]*)-)?(\d{4})$", rid)
    if not m:
        return None
    return m.group(1), m.group(2) or "", int(m.group(3))


def headings(text):
    out, fence = [], False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            fence = not fence
            continue
        if fence:
            continue
        m = re.match(r"^#{1,6}\s+(.*?)\s*#*\s*$", line)
        if m:
            out.append(m.group(1).strip())
    return out


def resolve_anchor(root, owner):
    """'path#heading text' -> (ok, reason). Matches a heading equal to the text, or starting with it
    followed by a space or punctuation (so 'DEC-core-0002' resolves its row heading). Never line numbers."""
    path, _, anchor = owner.partition("#")
    p = Path(root) / path
    if not p.exists():
        return False, "owner path missing: %s" % path
    if not anchor:
        return True, ""
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return False, "owner unreadable: %s (%s)" % (path, e)
    a = anchor.strip().lower()
    for h in headings(text):
        hl = h.lower().strip("`*_ ")
        if hl == a or (hl.startswith(a) and (len(hl) == len(a) or not hl[len(a)].isalnum())):
            return True, ""
    if p.suffix == ".py" and re.search(r"^\s*def %s\b|^%s\s*=" % (re.escape(anchor), re.escape(anchor)), text, re.M):
        return True, ""
    return False, "heading not found: %s#%s" % (path, anchor)


def five_field_header(text):
    """The five-field header owner . status . date . supersedes . audit within the first 6 lines."""
    for line in text.splitlines()[:6]:
        low = line.lower()
        if all(k in low for k in ("owner:", "status:", "date:", "supersedes:", "audit:")):
            audit = line.split("audit:", 1)[1].strip()
            return {"ok": True, "audit": audit}
    return {"ok": False, "audit": ""}


# ---------------------------------------------------------------- schema validator
def validate(obj, schema, path="$"):
    """Minimal JSON-schema subset: type, required, enum, pattern, items, properties, minimum."""
    errs = []
    t = schema.get("type")
    types = {"object": dict, "array": list, "string": str, "integer": int, "number": (int, float),
             "boolean": bool, "null": type(None)}
    if t:
        tl = t if isinstance(t, list) else [t]
        ok = False
        for one in tl:
            py = types.get(one)
            if py is None:
                continue
            if one in ("integer", "number") and isinstance(obj, bool):
                continue
            if isinstance(obj, py):
                ok = True
        if not ok:
            return ["%s: expected %s, got %s" % (path, t, type(obj).__name__)]
    if "enum" in schema and obj not in schema["enum"]:
        errs.append("%s: %r not in %s" % (path, obj, schema["enum"]))
    if "pattern" in schema and isinstance(obj, str) and not re.search(schema["pattern"], obj):
        errs.append("%s: %r does not match %s" % (path, obj, schema["pattern"]))
    if "minimum" in schema and isinstance(obj, (int, float)) and obj < schema["minimum"]:
        errs.append("%s: %r < minimum %s" % (path, obj, schema["minimum"]))
    if isinstance(obj, dict):
        for k in schema.get("required", []):
            if k not in obj:
                errs.append("%s: missing required key %r" % (path, k))
        for k, sub in (schema.get("properties") or {}).items():
            if k in obj:
                errs.extend(validate(obj[k], sub, "%s.%s" % (path, k)))
    if isinstance(obj, list) and "items" in schema:
        for i, it in enumerate(obj):
            errs.extend(validate(it, schema["items"], "%s[%d]" % (path, i)))
    return errs


# ---------------------------------------------------------------- generated declaration
# The owner of GEN_DECL is tools/map/_common.py (commons-mapbrain). Imported by path when present;
# this fallback is the same two lines (PROGRAMME_MAPPING 3.0) for fixtures without the map tools.
_GEN_DECL_FALLBACK = re.compile(r'GENERATED by \S+|GENERATED\W+(?:do not edit|never hand-edit|regenerat)|"_generated_by"\s*:', re.I)


def _gen_decl(root=None):
    for base in [Path(root)] if root else []:
        p = base / "tools" / "map" / "_common.py"
        if p.exists():
            try:
                spec = importlib.util.spec_from_file_location("_map_common_for_gov", str(p))
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                if hasattr(mod, "GEN_DECL"):
                    return mod.GEN_DECL
            except Exception:
                pass
    return _GEN_DECL_FALLBACK


def declares_generated(text, root=None):
    rx = _gen_decl(root)
    return any(rx.search(l) for l in text.splitlines()[:3])


# ---------------------------------------------------------------- files + globs
def tracked_files(root):
    """Tracked (and untracked-not-ignored) files when a git repo, else a filesystem walk."""
    root = Path(root)
    if is_git(root):
        r = git(root, "ls-files", "-co", "--exclude-standard", "-z")
        if r.returncode == 0:
            return sorted(p for p in r.stdout.split("\0") if p and (root / p).is_file())
    out = []
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in IGNORED_DIRS]
        for fn in fns:
            rel = os.path.relpath(os.path.join(dp, fn), root).replace(os.sep, "/")
            out.append(rel)
    return sorted(out)


_GLOB_CACHE = {}


def glob_re(pattern):
    if pattern in _GLOB_CACHE:
        return _GLOB_CACHE[pattern]
    i, out = 0, ""
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
            continue
        if pattern.startswith("**", i):
            out += ".*"
            i += 2
            continue
        if c == "*":
            out += "[^/]*"
        elif c == "?":
            out += "[^/]"
        elif c == "{":
            j = pattern.index("}", i)
            out += "(?:" + "|".join(re.escape(x) for x in pattern[i + 1:j].split(",")) + ")"
            i = j
        else:
            out += re.escape(c)
        i += 1
    if pattern.endswith("/"):
        out += ".*"
    rx = re.compile("^" + out + "$")
    _GLOB_CACHE[pattern] = rx
    return rx


def globmatch(path, pattern):
    return bool(glob_re(pattern).match(path))


def any_match(path, patterns):
    return any(globmatch(path, p) for p in patterns)


def sha256_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


# DEC-core-0010: the ONLY per-station content of the commons .claude/settings.json; written by
# tools/upstream/skill_surface.py --write and proven current by its --check, so commons_drift hashes the file without them.
GENERATED_SETTINGS_KEYS = ("skillOverrides", "skillListingBudgetFraction")


def commons_sha256(p, rel):
    """sha256 of a commons path as commons_drift compares it: .claude/settings.json minus GENERATED_SETTINGS_KEYS."""
    if rel.replace("\\", "/") == ".claude/settings.json":
        try:
            d = json.loads(Path(p).read_text(encoding="utf-8"))
        except ValueError:
            return sha256_file(p)
        for k in GENERATED_SETTINGS_KEYS:
            d.pop(k, None)
        return hashlib.sha256(json.dumps(d, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return sha256_file(p)


# ---------------------------------------------------------------- hooks wiring
def wired_commands(settings):
    """[(event, matcher, entry_dict, hook_dict, script_rel)] from a settings.json object."""
    out = []
    for ev, groups in (settings.get("hooks") or {}).items():
        for g in groups or []:
            for h in g.get("hooks") or []:
                cmd = h.get("command", "")
                m = re.search(r"python3\s+(\S+\.py)", cmd)
                out.append((ev, g.get("matcher", ""), g, h, m.group(1) if m else None))
    return out


def docstring(path):
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    m = re.search(r'^(?:#![^\n]*\n)?(?:#[^\n]*\n)*\s*[rRuU]?("""|\'\'\')(.*?)\1', text, re.S)
    return m.group(2) if m else ""


# ---------------------------------------------------------------- fixtures
MY_DATA = [
    "CLAUDE.md", "commons/defaults.json", "commons/schema/station.schema.json",
    "commons/schema/intents.schema.json", "governance/rules.json", "governance/checks.json",
    "governance/RELEASES.json", "governance/DECISIONS.md", "governance/HISTORY.md",
    "governance/LEDGER.md", "governance/DEFECTS.md", "governance/OWNERSHIP.md",
    "router/intents.json", ".claude/settings.json", ".gitignore", ".gitattributes",
]
MY_SCRIPTS = [
    "tools/station_audit.py", "tools/gov/_gov.py", "tools/gov/gov_check.py", "tools/gov/gen_ownership.py",
    "tools/gov/new_row.py", "tools/gov/gen_manifest.py",
    ".claude/hooks/_cmdscan.py", ".claude/hooks/_report.py", ".claude/hooks/_release.py",
    ".claude/hooks/intent_router.py", ".claude/hooks/deny_destructive.py",
    ".claude/hooks/deny_noted_defect.py", ".claude/hooks/context_threshold.py",
    ".claude/hooks/stop.py", ".claude/hooks/station_dispatch.py",
]
STUB = '''"""%s -- fixture stub (present-by-contract; the real file is written by another slice).

Earned by: fixture
Release: fixture
"""
import sys
if "--selftest" in sys.argv or "selftest" in sys.argv:
    print("selftest OK (0 cases, stub)")
sys.exit(0)
'''


def write(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def referenced_scripts(root):
    """Every script path the wiring, the rules and the checks name."""
    refs = set()
    sp = Path(root) / ".claude" / "settings.json"
    if sp.exists():
        for _, _, _, _, s in wired_commands(load_json(sp)):
            if s:
                refs.add(s)
    for base, frag, key in (("governance/rules.json", "governance/rules.d", "rules"),
                            ("governance/checks.json", "governance/checks.d", "checks")):
        if not (Path(root) / base).exists():
            continue
        for r in load_rows(root, base, frag, key):
            if key == "rules":
                e = norm_enforcement(r.get("enforcement") or {})
                if e["kind"] == "hook" and e["ref"]:
                    refs.add(e["ref"])
                o = (r.get("owner") or "").partition("#")[0]
                if o.endswith(".py"):
                    refs.add(o)
            else:
                for a in (r.get("cmd") or []) + (r.get("selftest") or []):
                    if isinstance(a, str) and a.endswith(".py"):
                        refs.add(a)
    return sorted(refs)


def make_station(tmp, real_scripts=True, git_init=True, stub_hooks=False, extra=None):
    """A clean fixture station built from THIS install's governance slice; sibling files are stubbed.
    real_scripts: copy tools/gov + station_audit + hooks; stub_hooks: replace hook scripts with stubs."""
    tmp = Path(tmp)
    for rel in MY_DATA + (MY_SCRIPTS if real_scripts else []):
        src = KIT_SRC / rel
        if src.exists():
            dst = tmp / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
    for rel in referenced_scripts(tmp):
        p = tmp / rel
        if stub_hooks and rel.startswith(".claude/hooks/") and not Path(rel).name.startswith("_"):
            write(tmp, rel, STUB % rel)
        elif not p.exists():
            write(tmp, rel, STUB % rel)
    # skills / workflows named by first moves (siblings own them): stub with frontmatter
    ip = tmp / "router" / "intents.json"
    if ip.exists():
        for row in load_json(ip).get("intents", []):
            fm = (row.get("router") or {}).get("first_move") or {}
            if fm.get("skill"):
                sk = tmp / ".claude" / "skills" / fm["skill"] / "SKILL.md"
                if not sk.exists():
                    write(tmp, str(sk.relative_to(tmp)),
                          "---\nname: %s\ndescription: fixture stub\n---\n# %s\n" % (fm["skill"], fm["skill"]))
            if fm.get("workflow"):
                wf = tmp / ".claude" / "workflows" / (fm["workflow"] + ".js")
                if not wf.exists():
                    write(tmp, str(wf.relative_to(tmp)), "export const meta = {name: 'x'};\n")
    for rel, text in (extra or {}).items():
        write(tmp, rel, text)
    if git_init:
        git(tmp, "init", "-q", "-b", "main")
        commit_all(tmp, "fixture")
    return tmp


def commit_all(root, msg):
    r = git(root, "ls-files", "-o", "-m", "-d", "-z", "--exclude-standard")
    paths = [p for p in r.stdout.split("\0") if p]
    if paths:
        git(root, "add", "--", *paths)  # explicit path list (deletions stage too)
    return git(root, "-c", "user.name=kit", "-c", "user.email=kit@localhost", "commit", "-q",
               "--allow-empty", "-m", msg)


# ---------------------------------------------------------------- rule rows
_KIND_ALIASES = {"hooked": "hook", "hook": "hook", "check": "check", "owed": "owed",
                 "not_hookable": "not-hookable", "not-hookable": "not-hookable", "not hookable": "not-hookable"}


def norm_enforcement(e):
    """Accept both vocabularies: {kind: hook|check|owed|not-hookable, ref} and GOV 3.4 {HOOKED|CHECK|..., by}."""
    kind = _KIND_ALIASES.get(str(e.get("kind", "")).strip().lower(), str(e.get("kind", "")).strip().lower())
    ref = e.get("ref") or e.get("by") or ""
    return {"kind": kind, "ref": ref, "why": e.get("why", ""), "trigger": e.get("trigger", ""),
            "shape": e.get("shape", "")}


def run(cmd, cwd, timeout=120, input_=None, env=None):
    try:
        r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, timeout=timeout, input=input_,
                           encoding="utf-8", errors="replace", env=env)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return None, "", "TIMEOUT"
    except OSError as e:
        return 2, "", str(e)
