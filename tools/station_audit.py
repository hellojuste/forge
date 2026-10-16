#!/usr/bin/env python3
"""station_audit.py -- THE one audit runner of a station: one command, two classes, one exit code.

owner: governance/rules.json (R-audit-runner) . spec: PROGRAMME_GOVERNANCE 3.9 . stdlib only

Checks are registered AS DATA: governance/checks.json + governance/checks.d/*.json (each programme and
each station owns its own fragment; the runner is never edited to add a check). A row:
  {"name","cmd":[argv],"class":"MUST_BE_CLEAN|WORKLIST","programme","earned_by","selftest":[argv],
   "retires","inputs":[globs],"timeout_s","gate_subcount"}
Every check prints a headline first: "<check>: <n> violation(s) . <m> worklist . denominator <d>"
(or "<check>: skipped (<why>)" when a knob or the branch turns it off -- a named skip, never a silent pass).
Anything else is UNREADABLE and red: a scraper fed garbage never reports a count.

  station_audit.py                 run every row (parallel, --jobs N), exit 0 iff every MUST_BE_CLEAN row is
                                   clean, no gate_subcount fired, nothing TIMEOUT/UNREADABLE (and with a floor
                                   file, no worklist above its floor)
  -k NAME (repeatable)             run only those; prints "ran k/N checks; the other N-k were NOT run"
  --changed                        reuse cached results whose key (cmd + sha256 of input files) is unchanged
  --state                          one cached line, <= gov.state_budget bytes; always exit 0 (SessionStart-safe)
  --list                           the registry table
  --ratchet                        write governance/worklist_floor.json from the current worklist counts
  --selftest                       every row's selftest, then the planted-runner tests (GOV 3.9 items 1-7)
  --root DIR                       station root (default: git toplevel, else cwd)

Exit: 0 clean . 1 red . 2 unreadable registry / usage.
Earned by: lettuce hard-coded 45 checks in Python and needed audit_canon to keep CLAUDE.md's printed lists
honest; registration by data removes the list (PROGRAMME_GOVERNANCE 3.9).
"""
import argparse
import concurrent.futures as cf
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "gov"))
import _gov  # noqa: E402

SKIP_RE = re.compile(r"^(\S+): skipped \((.+)\)\s*$")


def load_registry(root):
    rows = _gov.load_rows(root, "governance/checks.json", "governance/checks.d", "checks")
    seen, out = set(), []
    for r in rows:
        if r.get("name") in seen:
            raise _gov.GovError("duplicate check name %r (%s)" % (r.get("name"), r["_src"]))
        seen.add(r.get("name"))
        out.append(r)
    return out


def input_key(root, row, files):
    pats = row.get("inputs") or ["*"]
    if "*" in pats:
        return None  # whole tree: always re-run
    h = hashlib.sha256(json.dumps(row.get("cmd")).encode())
    for f in files:
        if _gov.any_match(f, pats):
            try:
                h.update(f.encode() + b"\0" + _gov.sha256_file(Path(root) / f).encode())
            except OSError:
                h.update(f.encode() + b"\0missing")
    return h.hexdigest()


def cache_dir(root):
    return Path(root) / ".cache" / "audit"


def run_row(root, row):
    t0 = time.time()
    rc, out, err = _gov.run(row["cmd"], root, timeout=row.get("timeout_s") or 120)
    res = {"name": row["name"], "class": row.get("class", "MUST_BE_CLEAN"), "rc": rc, "secs": round(time.time() - t0, 2)}
    if rc is None:
        res.update(status="TIMEOUT", headline="TIMEOUT %s after %ss" % (row["name"], row.get("timeout_s")), worklist=0)
        return res
    first = (out or "").splitlines()[0] if (out or "").strip() else ""
    hl = _gov.parse_headline(first)
    sk = SKIP_RE.match(first)
    if sk and rc == 0:
        res.update(status="SKIP", headline=first, worklist=0, violations=0)
        return res
    if hl is None or rc == 2 or rc not in (0, 1):
        res.update(status="UNREADABLE", headline="UNREADABLE %s (rc=%s: %s)" % (row["name"], rc, (first or err.strip()[:120])), worklist=0)
        return res
    res.update(headline=first, worklist=hl["worklist"], violations=hl["violations"])
    if res["class"] == "MUST_BE_CLEAN":
        res["status"] = "PASS" if rc == 0 and hl["violations"] == 0 else "FAIL"
    else:
        res["status"] = "PASS"
        gs = row.get("gate_subcount")
        if gs:
            m = re.search(gs, out or "")
            if m and int(m.group(1)) != 0:
                res["status"] = "FAIL"
                res["headline"] += "  [gate_subcount %s]" % m.group(1)
    return res


def is_red(res, floors=None):
    if res["status"] in ("FAIL", "TIMEOUT", "UNREADABLE"):
        return True
    if floors and res["class"] == "WORKLIST" and res["name"] in floors and res.get("worklist", 0) > floors[res["name"]]:
        return True
    return False


def head_sha(root):
    r = _gov.git(root, "rev-parse", "--short=7", "HEAD")
    return r.stdout.strip() if r.returncode == 0 else "nogit"


def audit(root, names=None, changed=False, jobs=None, quiet=False):
    rows = load_registry(root)
    allnames = [r["name"] for r in rows]
    if names:
        unknown = [n for n in names if n not in allnames]
        if unknown:
            raise _gov.GovError("unknown check(s): %s" % ", ".join(unknown))
        rows = [r for r in rows if r["name"] in names]
    files = _gov.tracked_files(root)
    cdir = cache_dir(root)
    results, todo, reused = [], [], 0
    for r in rows:
        key = input_key(root, r, files)
        cp = cdir / ("%s.json" % r["name"])
        if changed and key and cp.exists():
            try:
                c = json.loads(cp.read_text(encoding="utf-8"))
                if c.get("key") == key:
                    c["reused"] = True
                    results.append(c)
                    reused += 1
                    continue
            except ValueError:
                pass
        todo.append((r, key))
    jobs = jobs or min(4, os.cpu_count() or 1)
    with cf.ThreadPoolExecutor(max_workers=jobs) as ex:
        futs = {ex.submit(run_row, root, r): (r, key) for r, key in todo}
        for f in cf.as_completed(futs):
            r, key = futs[f]
            res = f.result()
            res["ran"] = True
            results.append(res)
            if res["status"] not in ("TIMEOUT", "UNREADABLE") and key:
                cdir.mkdir(parents=True, exist_ok=True)
                c = dict(res, key=key, utc=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%SZ"))
                (cdir / ("%s.json" % r["name"])).write_text(json.dumps(c), encoding="utf-8")
            else:
                try:
                    (cdir / ("%s.json" % r["name"])).unlink()
                except OSError:
                    pass
    order = {n: i for i, n in enumerate(allnames)}
    results.sort(key=lambda x: order.get(x["name"], 0))
    return results, len(allnames), reused


def floors(root):
    p = Path(root) / "governance" / "worklist_floor.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8")).get("floors", {})
        except ValueError:
            return {}
    return {}


def write_state(root, results, full):
    red = [r["name"] for r in results if is_red(r)]
    wl = {r["name"]: r.get("worklist", 0) for r in results if r["class"] == "WORKLIST"}
    st = {"sha": head_sha(root), "utc": dt.datetime.now(dt.timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%SZ"),
          "red": red, "worklists": wl, "full": full}
    cache_dir(root).mkdir(parents=True, exist_ok=True)
    (cache_dir(root) / "_state.json").write_text(json.dumps(st), encoding="utf-8")


def state_line(root):
    try:
        budget = int(_gov.config(root).get("gov", {}).get("state_budget", 600))
    except Exception:
        budget = 600
    p = cache_dir(root) / "_state.json"
    if not p.exists():
        return "AUDIT none cached — run python3 tools/station_audit.py --changed"
    try:
        st = json.loads(p.read_text(encoding="utf-8"))
        then = dt.datetime.strptime(st["utc"], "%Y-%m-%dT%H:%M:%SZ")
        age_s = int((dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - then).total_seconds())
        age = "%dm" % (age_s // 60) if age_s < 7200 else "%dh" % (age_s // 3600)
        wl = st.get("worklists", {})
        line = "AUDIT %s %s red=%s worklists=%s" % (
            st.get("sha", "?"), age, ",".join(st.get("red", [])) or "none",
            ",".join("%s:%d" % (k, v) for k, v in sorted(wl.items()) if v) or "none")
        extra = []
        if "defects_due" in wl:
            extra.append("defects due=%d" % wl["defects_due"])
        if "ledger_owed" in wl:
            extra.append("ledger OWED=%d" % wl["ledger_owed"])
        if extra:
            line += " · " + " · ".join(extra)
        if not st.get("full", True):
            line += " (partial run)"
    except Exception as e:
        line = "AUDIT state unreadable (%s) — run python3 tools/station_audit.py --changed" % e
    b = line.encode("utf-8")
    if len(b) > budget:
        line = b[: budget - 14].decode("utf-8", "ignore") + " …TRUNCATED"
    return line


def print_table(results, total, ran_names, reused, secs, fl, names):
    for r in results:
        tag = r["status"] + ("*" if r.get("reused") else "")
        print("%-10s %-13s %-18s %s" % (tag, r["class"], r["name"], r.get("headline", "")))
    if names:
        print("ran %d/%d checks; the other %d were NOT run" % (len(results), total, total - len(results)))
    if reused:
        print("reused %d/%d" % (reused, len(results)))
    print(headline(results, fl, secs))
    return 1 if any(is_red(r, fl) for r in results) else 0


def headline(results, fl, secs):
    """LEAN F5 / LL-22 (a green must never be misreadable): a SKIPped MUST is NOT RUN, never counted as clean."""
    must = [r for r in results if r["class"] == "MUST_BE_CLEAN"]
    red = [r for r in results if is_red(r, fl)]
    skipped = [r for r in must if r.get("status") == "SKIP"]
    clean = [r for r in must if not is_red(r, fl) and r.get("status") != "SKIP"]
    notrun = (" · %d NOT RUN (%s)" % (len(skipped), ", ".join(r["name"] for r in skipped))) if skipped else ""
    return "station_audit: %d red · %d/%d clean%s · worklists %d · %ss" % (
        len(red), len(clean), len(must), notrun,
        sum(r.get("worklist", 0) for r in results if r["class"] == "WORKLIST"), secs)


# ---------------------------------------------------------------- selftest
def _sa(root, *args, timeout=600):
    return _gov.run([sys.executable, str(Path(root) / "tools" / "station_audit.py"), "--root", str(root), *args],
                    root, timeout=timeout)


def _regen_manifest(root):
    gm = Path(root) / "tools" / "gov" / "gen_manifest.py"
    if gm.exists():
        _gov.run([sys.executable, str(gm), "--root", str(root), "--write"], root)


def _plants():
    """name -> function(root) planting ONE defect for that governance MUST_BE_CLEAN check."""
    def edit_json(root, rel, fn):
        p = Path(root) / rel
        d = json.loads(p.read_text(encoding="utf-8"))
        fn(d)
        p.write_text(_gov.dump_json(d), encoding="utf-8")

    def append(root, rel, text):
        p = Path(root) / rel
        p.write_text(p.read_text(encoding="utf-8") + text, encoding="utf-8")

    def p_claudemd(r):
        append(r, "CLAUDE.md", "\n<!-- padding -->\n" + ("x" * 120 + "\n") * 60)
        _regen_manifest(r)

    def p_station(r):
        edit_json(r, "commons/defaults.json", lambda d: d["gov"].__setitem__("ctx_warn", d["gov"]["ctx_handoff"] + 1))
        _regen_manifest(r)

    def p_rules(r):
        def f(d):
            d["rules"].append(dict(d["rules"][0]))
        edit_json(r, "governance/rules.json", f)
        _regen_manifest(r)

    def p_canon(r):
        _gov.write(r, "docs/x.md", "owner: x · status: x · date: x · supersedes: x · audit: python3 tools/station_audit.py\n"
                   "<!-- CANON:undeclared BEGIN -->\nsame\n<!-- CANON:undeclared END -->\n")

    def p_decisions(r):
        p = Path(r) / "governance" / "DECISIONS.md"
        t = p.read_text(encoding="utf-8")
        i = t.index("\nwords:", re.search(r"\n## DEC-[a-z0-9-]*\d{4} ", t).start())
        j = t.index("\n", i + 1)
        p.write_text(t[:i] + "\nwords: > \"an edited quote\"" + t[j:], encoding="utf-8")
        _regen_manifest(r)

    def p_history(r):
        p = Path(r) / "CLAUDE.md"
        lines = p.read_text(encoding="utf-8").splitlines(True)
        k = next(i for i, l in enumerate(lines) if len(l.strip()) >= 60 and not l.startswith("#") and "owner:" not in l)
        del lines[k]
        p.write_text("".join(lines), encoding="utf-8")
        _gov.git(r, "add", "--", "CLAUDE.md")
        _regen_manifest(r)

    def p_ledger(r):
        append(r, "governance/LEDGER.md", "\n## L-core-0999 — PLANTED\nkind: procedural\npathology: -\naxis: effort\n"
               "hook: NOT HOOKABLE planted\namendment: be more careful\n")
        _regen_manifest(r)

    def p_defects(r):
        append(r, "governance/DEFECTS.md", "\n## DEF-core-0999 · 2026-10-16 · planted\nstatus: OPEN\nwhere: x\nowner: this-station\n")
        _regen_manifest(r)

    def p_releases(r):
        edit_json(r, "governance/RELEASES.json", lambda d: d["releases"].append(
            {"id": "REL-0999", "scope": "no_such_hook", "match": "x", "words": "w", "locator": "l",
             "utc": "2026-10-16T09:00Z", "expires": "2026-10-17T09:00Z"}))
        _regen_manifest(r)

    def p_hooks_wired(r):
        def f(d):
            for g in d["hooks"]["PreToolUse"]:
                if any("deny_destructive" in h.get("command", "") for h in g["hooks"]):
                    g["hooks"][0]["if"] = "Bash(git *)"
        edit_json(r, ".claude/settings.json", f)
        _regen_manifest(r)

    def p_hooks_selftest(r):
        _gov.write(r, ".claude/hooks/stop.py", '"""stop (planted). Earned by: x\n"""\nimport sys\nsys.exit(1 if "--selftest" in sys.argv else 0)\n')
        _regen_manifest(r)

    def p_hook_channels(r):
        _gov.write(r, ".claude/hooks/context_threshold.py",
                   '"""ctx (planted)\nEarned by: x\n"""\nimport sys\nif "--selftest" in sys.argv:\n    print("selftest OK (1 cases)")\nelse:\n    print("plain text on stdout")\n')
        _regen_manifest(r)

    def p_admission(r):
        edit_json(r, "governance/checks.json", lambda d: d["checks"][0].__setitem__("earned_by", ""))
        _regen_manifest(r)

    def p_router_targets(r):
        def f(d):
            d["intents"][0]["router"]["first_move"] = {"skill": "no-such-skill", "args": ""}
        edit_json(r, "router/intents.json", f)
        _regen_manifest(r)

    def p_commons_drift(r):
        append(r, ".gitattributes", "# drift\n")

    def p_main_purity(r):
        _gov.write(r, "STATION.md", "# a station-only file on main\n")

    return {"claudemd": p_claudemd, "station": p_station, "rules": p_rules, "canon": p_canon,
            "decisions": p_decisions, "history": p_history, "ledger": p_ledger, "defects": p_defects,
            "releases": p_releases, "hooks_wired": p_hooks_wired, "hooks_selftest": p_hooks_selftest,
            "hook_channels": p_hook_channels, "admission": p_admission, "router_targets": p_router_targets,
            "commons_drift": p_commons_drift, "main_purity": p_main_purity}


def _reds(out):
    return sorted({l.split()[2] for l in out.splitlines()
                   if l.split() and l.split()[0].rstrip("*") in ("FAIL", "TIMEOUT", "UNREADABLE") and len(l.split()) > 2})


def selftest(root):
    fails, cases = [], 0

    def ok(cond, msg):
        nonlocal cases
        cases += 1
        if not cond:
            fails.append(msg)

    # (0) every registered row's own selftest
    try:
        rows = load_registry(root)
    except _gov.GovError as e:
        print("selftest: registry unreadable: %s" % e)
        return 2
    seen = set()
    with cf.ThreadPoolExecutor(max_workers=min(4, os.cpu_count() or 1)) as ex:
        futs = {}
        for r in rows:
            st = tuple(r.get("selftest") or [])
            if st and st not in seen:
                seen.add(st)
                futs[ex.submit(_gov.run, list(st), root, (r.get("timeout_s") or 120) * 3)] = (r["name"], st)
        for f in cf.as_completed(futs):
            name, st = futs[f]
            rc, out, err = f.result()
            ok(rc == 0, "row selftest red: %s (%s) rc=%s %s" % (name, " ".join(st), rc, (out + err).strip()[-300:]))

    # (1)+(2)+(7) governance fixture: clean all green; each planted defect red alone
    with tempfile.TemporaryDirectory() as td:
        base = Path(td) / "clean"
        _gov.make_station(base, real_scripts=True, stub_hooks=True)
        _regen_manifest(base)
        _gov.commit_all(base, "manifest")
        rc, out, err = _sa(base)
        ok(rc == 0, "(2) clean fixture not green: rc=%s\n%s%s" % (rc, out[-1500:], err[-500:]))
        gov_names = [r["name"] for r in load_registry(base) if r.get("class") == "MUST_BE_CLEAN"]
        plants = _plants()
        for name in gov_names:
            ok(name in plants, "(1) no planted defect for MUST check %s" % name)
        for name, plant in plants.items():
            d = Path(td) / ("p_" + name)
            shutil.copytree(base, d, symlinks=True)
            shutil.rmtree(d / ".cache", ignore_errors=True)
            plant(d)
            rc, out, err = _sa(d)
            reds = _reds(out)
            ok(rc == 1 and reds == [name], "(1) plant %s: rc=%s red=%s\n%s" % (name, rc, reds, out[-800:]))
        ok("admission" in plants, "(7) admission plant missing")

    # (3)-(6) + checks.d pickup: a synthetic registry
    with tempfile.TemporaryDirectory() as td:
        r = Path(td)
        here = Path(__file__).resolve().parent
        (r / "tools" / "gov").mkdir(parents=True)
        shutil.copyfile(here / "station_audit.py", r / "tools" / "station_audit.py")
        shutil.copyfile(here / "gov" / "_gov.py", r / "tools" / "gov" / "_gov.py")
        _gov.write(r, "a/in.txt", "a\n")
        _gov.write(r, "b/in.txt", "b\n")
        hl = "import sys; print('%s: 0 violation(s) · 0 worklist · denominator 1')"
        adm = {"programme": "selftest", "earned_by": "selftest", "selftest": ["true"], "retires": "nothing", "gate_subcount": None}
        checks = [
            dict(adm, name="a", cmd=[sys.executable, "-c", hl % "a"], **{"class": "MUST_BE_CLEAN"}, inputs=["a/**"], timeout_s=30),
            dict(adm, name="b", cmd=[sys.executable, "-c", hl % "b"], **{"class": "MUST_BE_CLEAN"}, inputs=["b/**"], timeout_s=30),
            dict(adm, name="w", cmd=[sys.executable, "-c", "print('w: 0 violation(s) · 3 worklist · denominator 9'); print('deploy: 0')"],
                 **{"class": "WORKLIST"}, inputs=["a/**"], timeout_s=30),
        ]
        _gov.write(r, "governance/checks.json", _gov.dump_json({"checks": checks}))
        rc, out, _ = _sa(r)
        ok(rc == 0, "(base) synthetic registry not green: %s" % out)
        # (5) -k
        rc, out, _ = _sa(r, "-k", "a")
        ok(rc == 0 and "ran 1/3 checks; the other 2 were NOT run" in out, "(5) -k line missing: %s" % out)
        # (6) --changed re-runs exactly the rows whose inputs match
        _sa(r, "--changed")
        _gov.write(r, "b/in.txt", "b changed\n")
        rc, out, _ = _sa(r, "--changed")
        reused = sorted(l.split()[2] for l in out.splitlines() if l.startswith("PASS*"))
        ran = sorted(l.split()[2] for l in out.splitlines() if l.startswith("PASS ") or l.startswith("FAIL "))
        ok(reused == ["a", "w"] and ran == ["b"] and "reused 2/3" in out, "(6) --changed reran %s reused %s\n%s" % (ran, reused, out))
        # --state after a run
        rc, out, _ = _sa(r, "--state")
        ok(rc == 0 and out.startswith("AUDIT ") and len(out.strip().encode()) <= 600, "--state: %r" % out)
        # gate_subcount
        checks[2]["gate_subcount"] = r"deploy: (\d+)"
        _gov.write(r, "governance/checks.json", _gov.dump_json({"checks": checks}))
        rc, out, _ = _sa(r)
        ok(rc == 0, "gate_subcount 0 must stay green: %s" % out)
        # planted checks.d/x.json row is picked up
        _gov.write(r, "governance/checks.d/x.json", _gov.dump_json({"checks": [
            dict(adm, name="x", cmd=[sys.executable, "-c", "print('x: 1 violation(s) · 0 worklist · denominator 1'); raise SystemExit(1)"],
                 **{"class": "MUST_BE_CLEAN"}, inputs=["*"], timeout_s=30)]}))
        rc, out, _ = _sa(r)
        ok(rc == 1 and "FAIL" in out and " x " in out, "checks.d/x.json row not picked up: %s" % out)
        (r / "governance" / "checks.d" / "x.json").unlink()
        # (3) timeout: red and never cached
        _gov.write(r, "governance/checks.d/t.json", _gov.dump_json({"checks": [
            dict(adm, name="t", cmd=["sleep", "999"], **{"class": "MUST_BE_CLEAN"}, inputs=["a/**"], timeout_s=1)]}))
        rc, out, _ = _sa(r, "-k", "t", "--changed")
        ok(rc == 1 and "TIMEOUT" in out and not (r / ".cache" / "audit" / "t.json").exists(), "(3) timeout: %s" % out)
        (r / "governance" / "checks.d" / "t.json").unlink()
        # (4) garbage -> UNREADABLE
        _gov.write(r, "governance/checks.d/g.json", _gov.dump_json({"checks": [
            dict(adm, name="g", cmd=[sys.executable, "-c", "print('garbage')"], **{"class": "WORKLIST"}, inputs=["*"], timeout_s=30)]}))
        rc, out, _ = _sa(r, "-k", "g")
        ok(rc == 1 and "UNREADABLE" in out, "(4) garbage not UNREADABLE: %s" % out)
        # named skip is green and printed
        _gov.write(r, "governance/checks.d/g.json", _gov.dump_json({"checks": [
            dict(adm, name="g", cmd=[sys.executable, "-c", "print('g: skipped (knob XS)')"], **{"class": "MUST_BE_CLEAN"}, inputs=["*"], timeout_s=30)]}))
        rc, out, _ = _sa(r, "-k", "g")
        ok(rc == 0 and "SKIP" in out, "named skip: %s" % out)
        ok("0/1 clean · 1 NOT RUN (g)" in out and "1/1 clean" not in out, "a skipped MUST is never counted clean (LEAN F5): %s" % out)
        # --state with nothing cached
        shutil.rmtree(r / ".cache")
        rc, out, _ = _sa(r, "--state")
        ok(rc == 0 and "AUDIT none cached" in out, "--state none: %s" % out)
        # --ratchet: a worklist above its floor turns red
        rc, out, _ = _sa(r, "--ratchet")
        ok(rc == 0 and (r / "governance" / "worklist_floor.json").exists(), "--ratchet: %s" % out)
        fl = json.loads((r / "governance" / "worklist_floor.json").read_text())
        fl["floors"]["w"] = 2
        (r / "governance" / "worklist_floor.json").write_text(json.dumps(fl))
        rc, out, _ = _sa(r, "-k", "w")
        ok(rc == 1, "worklist above floor must be red: %s" % out)
    if fails:
        print("selftest FAILED (%d of %d cases)" % (len(fails), cases))
        for f in fails:
            print(" - " + f)
        return 1
    print("selftest OK (%d cases)" % cases)
    return 0


def main(argv=None):
    _gov.setup_io()
    ap = argparse.ArgumentParser(description="the one station audit runner")
    ap.add_argument("-k", action="append", dest="names")
    ap.add_argument("--changed", action="store_true")
    ap.add_argument("--state", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--ratchet", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--jobs", type=int)
    ap.add_argument("--root")
    a = ap.parse_args(argv)
    root = _gov.find_root(a.root)
    if a.state:
        try:
            print(state_line(root))
        except Exception as e:
            print("AUDIT state unavailable (%s)" % e)
        return 0
    try:
        if a.selftest:
            return selftest(root)
        if a.list:
            for r in load_registry(root):
                print("%-18s %-13s %-12s %s" % (r["name"], r.get("class"), r.get("programme", ""), ",".join(r.get("inputs") or [])))
            return 0
        t0 = time.time()
        results, total, reused = audit(root, a.names, a.changed, a.jobs)
        fl = floors(root)
        write_state(root, results, full=not a.names)
        rc = print_table(results, total, a.names, reused, round(time.time() - t0, 1), fl, a.names)
        if a.ratchet:
            p = Path(root) / "governance" / "worklist_floor.json"
            p.write_text(_gov.dump_json(
                {"_generated_by": "tools/station_audit.py --ratchet",
                 "floors": {r["name"]: r.get("worklist", 0) for r in results if r["class"] == "WORKLIST"}}), encoding="utf-8")
            print("ratchet: wrote %s" % p.relative_to(root))
            return 0
        return rc
    except _gov.GovError as e:
        print("station_audit: UNREADABLE registry (%s)" % e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
