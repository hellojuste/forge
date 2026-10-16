#!/usr/bin/env python3
"""workflows_check.py — saved workflows parse and carry a real certain test; the skill listing stays inside its budget.

Earned by: lettuce `tools/audit_intents.py` (measured on node v22: `node --check file.js` on an ESM file returns 0 for
EVERY syntax error tried, so a bare check proves nothing; the harness-wrapped body is the only form that both accepts
a real workflow and rejects a broken one), LEAN LL-25 / CA-17 (a certain test must be able to fail: lettuce's admin
workflow once named `prime_record.py --cost-report`, which exits 2 on every run; a hard-coded `verdict: 'pass'` is no
test) and LL-02 (the per-turn cost of a skill is its listing line; a name shared by a workflow and a skill is hidden
by the override meant for one of them).

Checks (headline `<check>: <n> violation(s) · <m> worklist · denominator <d>`):
  workflows_parse  MUST  every `.claude/workflows/*.js`: (1) `node --check` on the body with `export ` dropped before
                         `const meta` and wrapped in `async function __wfcheck__(){...}` piped on stdin; (2) the first
                         statement is `export const meta = {...}`, a PURE literal (no call, arrow, template or bare
                         identifier value) with non-empty `name` (== file stem), `description`, `phases` [{title}];
                         (3) a `const CERTAIN_TEST = '<cmd>'`; (4) no `Date.now`, `Math.random`, escaped backtick;
                         (5) no workflow shares a name with a `.claude/skills/<name>/` (LL-02).
  certain_tests    MUST  each CERTAIN_TEST names a tool (python3/node/bash/git/a tools/ path), is not existence-only
                         (`test -f`, `ls`, `cat`, `stat`, `true`, `echo`), does not mutate (`rm`, `>` other than
                         `2>&1`, `git commit`, `git push`, `--write`, `sed -i`, `mv`), and the workflow does not
                         hard-code a passing verdict.
  listing_budget   MUST  skills listed per turn (every `.claude/skills/*/SKILL.md` not overridden to
                         `user-invocable-only`/`off` by `.claude/settings.json` skillOverrides, `commons/defaults.json`
                         skill_overrides or `station.json` skill_overrides) <= listed_max (6) and their name+description
                         bytes <= listing_budget_bytes (2400); every description <= 200 chars; frontmatter parses;
                         an override naming no skill or naming a workflow is a violation.
CLI: workflows_check.py [workflows_parse|certain_tests|listing_budget] --root <dir> [--check] [--selftest]
     (no check name = all three; --check is the default mode and is accepted for symmetry with the other tools)
Exit: 0 clean · 1 violation · 2 node absent (the parse gate cannot do its job; never a silent pass).
"""
import argparse
import contextlib
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _uplib as U  # noqa: E402

DESC_MAX = 200
EXISTENCE_ONLY = re.compile(r"^\s*(test\s+-[efds]|\[\s+-[efds]|ls\b|cat\b|stat\b|true\b|echo\b|:\s*$|exit\s+0)")
MUTATES = [(re.compile(r"(^|[\s;&|])rm\s"), "rm"), (re.compile(r"(?<![0-9&])>(?!&)"), "> redirect"),
           (re.compile(r"\bgit\s+commit\b"), "git commit"), (re.compile(r"\bgit\s+push\b"), "git push"),
           (re.compile(r"--write\b"), "--write"), (re.compile(r"\bsed\s+-i\b"), "sed -i"), (re.compile(r"(^|[\s;&|])mv\s"), "mv")]
NAMES_TOOL = re.compile(r"\b(python3?|node|bash|sh|git|make|npm|pytest)\b|tools/|\.py\b|\.js\b")
HARDCODED_PASS = re.compile(r"verdict\s*[:=]\s*['\"](pass|PASS|ok|OK|green)['\"]")


# ---------------------------------------------------------------- parsing helpers
def wrap_for_node(src):
    body = re.sub(r"(?m)^\s*export\s+(const\s+meta\b)", r"\1", src)
    return "async function __wfcheck__(){\n" + body + "\n}\n"


def node_check(src):
    node = shutil.which("node")
    if not node:
        return None, "node not on PATH — the parse gate cannot run"
    p = subprocess.run([node, "--check"], input=wrap_for_node(src), text=True, capture_output=True)
    if p.returncode == 0:
        return True, "ok"
    err = (p.stderr or p.stdout or "").strip().splitlines()
    head = err[0] if err else "node --check failed"
    return False, re.sub(r"\[stdin\]:(\d+)", lambda m: "line %d" % max(1, int(m.group(1)) - 1), head)


def strip_comments(src):
    return re.sub(r"(?s)/\*.*?\*/", "", re.sub(r"(?m)^\s*//.*$", "", src))


def meta_literal(src):
    """Text of the `export const meta = {...}` object, or None. Must be the first statement."""
    s = strip_comments(src).lstrip()
    m = re.match(r"export\s+const\s+meta\s*=\s*\{", s)
    if not m:
        return None
    i, depth, q = m.end() - 1, 0, None
    j = i
    while j < len(s):
        ch = s[j]
        if q:
            if ch == "\\":
                j += 2
                continue
            if ch == q:
                q = None
        elif ch in "'\"`":
            q = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[i:j + 1]
        j += 1
    return None


def literal_impurities(text):
    """Calls, arrows, templates and bare identifiers used as VALUES inside the meta literal."""
    no_str = re.sub(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"", "''", text)
    bad = []
    if "`" in no_str:
        bad.append("template literal")
    if "=>" in no_str or re.search(r"\bfunction\b", no_str):
        bad.append("function")
    if "(" in no_str:
        bad.append("call/expression")
    for m in re.finditer(r"[:\[,]\s*([A-Za-z_$][\w$.]*)\s*(?=[,}\]])", no_str):
        if m.group(1) not in ("true", "false", "null"):
            bad.append("identifier value %s" % m.group(1))
    return bad


def meta_value(text):
    node = shutil.which("node")
    if not node:
        return None
    p = subprocess.run([node, "-e", "const m = (%s);process.stdout.write(JSON.stringify(m))" % text], capture_output=True, text=True)
    if p.returncode != 0:
        return None
    try:
        return json.loads(p.stdout)
    except ValueError:
        return None


def certain_test_of(src):
    m = re.search(r"(?m)^\s*const\s+CERTAIN_TEST\s*=\s*(['\"])((?:\\.|(?!\1).)*)\1", src)
    return m.group(2).replace("\\'", "'").replace('\\"', '"') if m else None


def workflows(root):
    d = Path(root) / ".claude" / "workflows"
    return sorted(d.glob("*.js")) if d.is_dir() else []


def skill_dirs(root):
    d = Path(root) / ".claude" / "skills"
    return sorted(p for p in d.iterdir() if p.is_dir()) if d.is_dir() else []


# ---------------------------------------------------------------- checks
def check_workflows_parse(root):
    root = Path(root)
    viol, work = [], []
    skills = {p.name for p in skill_dirs(root)}
    wfs = workflows(root)
    for f in wfs:
        rel = f.relative_to(root).as_posix()
        src = f.read_text(encoding="utf-8")
        ok, detail = node_check(src)
        if ok is None:
            print("workflows_parse: UNREADABLE %s" % detail)
            return 2
        if not ok:
            viol.append("%s: node --check (harness-wrapped): %s" % (rel, detail))
        lit = meta_literal(src)
        if lit is None:
            viol.append("%s: first statement is not `export const meta = {...}`" % rel)
        else:
            imp = literal_impurities(lit)
            if imp:
                viol.append("%s: meta is not a pure literal (%s)" % (rel, ", ".join(sorted(set(imp)))))
            else:
                meta = meta_value(lit)
                if meta is None:
                    viol.append("%s: meta literal does not evaluate" % rel)
                else:
                    if meta.get("name") != f.stem:
                        viol.append("%s: meta.name %r != file stem %r" % (rel, meta.get("name"), f.stem))
                    if not str(meta.get("description", "")).strip():
                        viol.append("%s: meta.description empty" % rel)
                    ph = meta.get("phases")
                    if not isinstance(ph, list) or not ph or not all(isinstance(x, dict) and x.get("title") for x in ph):
                        viol.append("%s: meta.phases must be a non-empty list of {title}" % rel)
        if certain_test_of(src) is None:
            viol.append("%s: no `const CERTAIN_TEST = '<command>'`" % rel)
        for pat, what in ((r"\bDate\.now\b", "Date.now"), (r"\bMath\.random\b", "Math.random"), (r"\\`", "escaped backtick")):
            if re.search(pat, strip_comments(src)):
                viol.append("%s: uses %s (workflows are deterministic; the harness loader rejects escaped backticks)" % (rel, what))
        if f.stem in skills:
            viol.append("%s: shares its name with .claude/skills/%s/ (LL-02: one override would hide both)" % (rel, f.stem))
    return U.finish("workflows_parse", viol, work, len(wfs))


def check_certain_tests(root):
    root = Path(root)
    viol = []
    wfs = workflows(root)
    for f in wfs:
        rel = f.relative_to(root).as_posix()
        src = f.read_text(encoding="utf-8")
        ct = certain_test_of(src)
        if ct is None:
            viol.append("%s: no CERTAIN_TEST" % rel)
            continue
        if not NAMES_TOOL.search(ct):
            viol.append("%s: CERTAIN_TEST %r names no tool" % (rel, ct))
        if EXISTENCE_ONLY.search(ct) and not re.search(r"&&|\|\|", ct):
            viol.append("%s: CERTAIN_TEST %r is existence-only (it cannot fail on a wrong result)" % (rel, ct))
        for pat, what in MUTATES:
            if pat.search(ct.replace("2>&1", "").replace(">&2", "")):
                viol.append("%s: CERTAIN_TEST %r mutates (%s)" % (rel, ct, what))
                break
        if HARDCODED_PASS.search(strip_comments(src)):
            viol.append("%s: hard-codes a passing verdict (the verdict must be the certain test's exit code)" % rel)
    return U.finish("certain_tests", viol, [], len(wfs))


def overrides(root):
    root = Path(root)
    out = {}
    s = U.load_json(root / ".claude" / "settings.json", {}) or {}
    out.update(s.get("skillOverrides") or {})
    d = U.load_json(root / "commons" / "defaults.json", {}) or {}
    out.update(d.get("skill_overrides") or {})
    st = U.station_json(root) or {}
    out.update(st.get("skill_overrides") or {})
    return out, d, st


def check_listing_budget(root):
    root = Path(root)
    viol, work = [], []
    ov, defaults, st = overrides(root)
    max_n = st.get("listed_max", defaults.get("listed_max", 6))
    max_b = st.get("listing_budget_bytes", defaults.get("listing_budget_bytes", 2400))
    names, listed, total = set(), [], 0
    for d in skill_dirs(root):
        f = d / "SKILL.md"
        if not f.is_file():
            viol.append("%s: no SKILL.md" % d.relative_to(root).as_posix())
            continue
        fm = U.frontmatter(f.read_text(encoding="utf-8"))
        name, desc = fm.get("name"), fm.get("description", "")
        rel = f.relative_to(root).as_posix()
        if not name or not desc:
            viol.append("%s: frontmatter lacks name or description" % rel)
            continue
        if name != d.name:
            viol.append("%s: frontmatter name %r != directory %r" % (rel, name, d.name))
        names.add(d.name)
        if len(desc) > DESC_MAX:
            viol.append("%s: description %d chars > %d" % (rel, len(desc), DESC_MAX))
        if ov.get(d.name) in ("user-invocable-only", "off"):
            continue
        listed.append(d.name)
        total += len(name.encode()) + len(desc.encode())
    wf = {p.stem for p in workflows(root)}
    for k, v in sorted(ov.items()):
        if k not in names:
            (work if k in wf else viol).append("override %s=%s names no skill here%s" % (k, v, " (it is a workflow: a workflow is not listed; drop the row)" if k in wf else ""))
        if v not in ("user-invocable-only", "off", "on", "listed"):
            viol.append("override %s has unknown value %r" % (k, v))
    if len(listed) > max_n:
        viol.append("%d skills listed (%s) > listed_max %d" % (len(listed), ", ".join(listed), max_n))
    if total > max_b:
        viol.append("listed name+description %d B > listing_budget_bytes %d" % (total, max_b))
    rc = U.finish("listing_budget", viol, work, len(names))
    print("  listed: %s · %d B of %d · %d of max %d" % (", ".join(listed) or "none", total, max_b, len(listed), max_n))
    return rc


CHECKS = {"workflows_parse": check_workflows_parse, "certain_tests": check_certain_tests, "listing_budget": check_listing_budget}


# ---------------------------------------------------------------- selftest
GOOD = """export const meta = {
  name: 'good',
  description: 'a fixture workflow',
  phases: [{ title: 'Gather', detail: 'run the commands' }, { title: 'Verify' }],
}
const CERTAIN_TEST = 'python3 tools/station_audit.py -k workflows_parse'
phase('Gather')
const g = await agent('STATION_WORKFLOW=good. run it', { phase: 'Gather' })
if (args && args.dry) { return { plan: 1 } }
return { gather: g, certainTest: CERTAIN_TEST }
"""


def _skill(root, name, desc):
    p = Path(root) / ".claude/skills" / name / "SKILL.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("---\nname: %s\ndescription: %s\n---\nbody\n" % (name, desc))


def _q(fn, root):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = fn(root)
    return rc, buf.getvalue()


def selftest():
    if not shutil.which("node"):
        print("workflows_check selftest: node absent — cannot prove the parse gate (exit 2)")
        return 2
    cases = 0
    bad_wfs = {
        "workflows_parse": [
            ("good", GOOD.replace("return { gather", "return { gather: (")),                        # syntax error
            ("good", GOOD.replace("export const meta", "const x = 1\nexport const meta")),            # meta not first
            ("good", GOOD.replace("'a fixture workflow'", "describe()")),                             # impure meta
            ("good", GOOD.replace("name: 'good'", "name: 'other'")),                                  # name != stem
            ("good", GOOD.replace("const CERTAIN_TEST = 'python3 tools/station_audit.py -k workflows_parse'\n", "")),
            ("good", GOOD.replace("phase('Gather')", "const t = Date.now()\nphase('Gather')")),
            ("good", GOOD.replace("phases: [{ title: 'Gather', detail: 'run the commands' }, { title: 'Verify' }]", "phases: []")),
            ("closeout", GOOD.replace("name: 'good'", "name: 'closeout'")),                           # shares a skill name
        ],
        "certain_tests": [
            ("good", GOOD.replace("python3 tools/station_audit.py -k workflows_parse", "test -f out.md")),
            ("good", GOOD.replace("python3 tools/station_audit.py -k workflows_parse", "python3 tools/gen.py --write")),
            ("good", GOOD.replace("python3 tools/station_audit.py -k workflows_parse", "python3 tools/x.py > out.txt")),
            ("good", GOOD.replace("python3 tools/station_audit.py -k workflows_parse", "git commit -am done && python3 t.py")),
            ("good", GOOD.replace("python3 tools/station_audit.py -k workflows_parse", "the reviewer agrees")),
            ("good", GOOD.replace("return { gather: g,", "return { verdict: 'pass', gather: g,")),
        ],
    }
    for name, fn in CHECKS.items():
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / ".claude/workflows").mkdir(parents=True)
            (Path(t) / ".claude/workflows/good.js").write_text(GOOD)
            _skill(t, "closeout", "Close a work pass.")
            rc, out = _q(fn, t)
            assert rc == 0, "%s green on the good fixture:\n%s" % (name, out)
            cases += 1
        for stem, src in bad_wfs.get(name, []):
            with tempfile.TemporaryDirectory() as t:
                (Path(t) / ".claude/workflows").mkdir(parents=True)
                (Path(t) / (".claude/workflows/%s.js" % stem)).write_text(src)
                _skill(t, "closeout", "Close a work pass.")
                rc, out = _q(fn, t)
                assert rc == 1, "%s must be red on planted defect #%d:\n%s" % (name, cases, out)
                cases += 1
    # node gate really is needed: a bare `node --check` on the broken ESM file passes (lettuce measurement)
    with tempfile.TemporaryDirectory() as t:
        f = Path(t) / "broken.mjs"
        f.write_text("export const meta = {}\nconst x = (\n")
        ok, _ = node_check(f.read_text())
        assert ok is False, "wrapped gate rejects a syntax error"
        cases += 1
    # listing budget
    with tempfile.TemporaryDirectory() as t:
        for i in range(6):
            _skill(t, "s%d" % i, "x" * 150)
        rc, out = _q(check_listing_budget, t)
        assert rc == 0, out
        _skill(t, "s6", "seventh")
        rc, out = _q(check_listing_budget, t)
        assert rc == 1 and "> listed_max 6" in out, out
        U.write_json(Path(t) / "station.json", {"name": "x", "skill_overrides": {"s6": "user-invocable-only"}})
        rc, out = _q(check_listing_budget, t)
        assert rc == 0, out
        U.write_json(Path(t) / "station.json", {"name": "x", "listing_budget_bytes": 500})
        rc, out = _q(check_listing_budget, t)
        assert rc == 1 and "listing_budget_bytes" in out, out
        U.write_json(Path(t) / "station.json", {"name": "x", "skill_overrides": {"s6": "user-invocable-only", "ghost": "off"}})
        rc, out = _q(check_listing_budget, t)
        assert rc == 1 and "names no skill" in out, out
        _skill(t, "long", "y" * 201)
        U.write_json(Path(t) / "station.json", {"name": "x", "skill_overrides": {"s6": "off", "long": "off"}})
        rc, out = _q(check_listing_budget, t)
        assert rc == 1 and "description 201 chars" in out, out
        cases += 6
    print("workflows_check selftest OK (%d cases)" % cases)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("check", nargs="?", choices=sorted(CHECKS))
    ap.add_argument("--root")
    ap.add_argument("--check", dest="check_mode", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        try:
            return selftest()
        except AssertionError as e:
            print("workflows_check selftest FAILED: %s" % e)
            return 1
    root = U.find_root(a.root)
    worst = 0
    for n in ([a.check] if a.check else list(CHECKS)):
        worst = max(worst, CHECKS[n](root))
    return worst


if __name__ == "__main__":
    sys.exit(main())
