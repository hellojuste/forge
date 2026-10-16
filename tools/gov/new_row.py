#!/usr/bin/env python3
"""new_row.py -- allocate the next DEC / L / DEF id and append a templated row (GOV 3.5, 3.7, 3.8).

owner: governance/rules.json R-registers
    python3 tools/gov/new_row.py dec|ledger|def "<subject>" [--kind <kind>] [--root DIR] [--no-branch-scan] [--dry]
                                 [--selftest]
The file and prefix come from station.json: absent -> main, station `core`, the commons register
(governance/DECISIONS.md, DEC-core-nnnn); present -> governance/STATION_<REG>.md with DEC-<station>-nnnn.
Next id = 1 + the max number of that prefix found in the working tree AND in every local branch's copy
(git for-each-ref refs/heads + git show <ref>:<file>), the small form of lettuce's ID_LEASES: two branches
collide only if both allocate before either is visible. --no-branch-scan is the single-writer knob.
The appended row is a TEMPLATE with <fill> slots; the register's check stays red until they are filled
(words/locator for DEC, trigger/why_not_fixed_now for DEF, hook/amendment for L) -- by design.
Earned by: lettuce RATIFICATIONS.md header: two ordinal series collided at "sixth"; ids were hand-allocated.
"""
import argparse
import datetime as dt
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _gov  # noqa: E402

REG = {"dec": ("DEC", "DECISIONS.md"), "ledger": ("L", "LEDGER.md"), "def": ("DEF", "DEFECTS.md")}


def target(root, kind):
    prefix, base = REG[kind]
    st = _gov.station_json(root)
    if st is None:
        return prefix, "core", "governance/" + base
    return prefix, st.get("name", "station"), "governance/STATION_" + base


def max_id(text, prefix, station):
    rx = re.compile(r"^## %s-%s-(\d{4})\b" % (prefix, re.escape(station)), re.M)
    return max([int(m) for m in rx.findall(text or "")] or [0])


def next_id(root, kind, branch_scan=True):
    prefix, station, rel = target(root, kind)
    p = Path(root) / rel
    n = max_id(p.read_text(encoding="utf-8") if p.exists() else "", prefix, station)
    if branch_scan and _gov.is_git(root):
        refs = _gov.git(root, "for-each-ref", "--format=%(refname:short)", "refs/heads").stdout.split()
        for ref in refs:
            n = max(n, max_id(_gov.show(root, ref, rel), prefix, station))
    return "%s-%s-%04d" % (prefix, station, n + 1), rel


def template(kind, rid, subject, row_kind):
    today = dt.date.today().isoformat()
    if kind == "dec":
        return ("\n## %s · %s · %s\nkind: %s\nstatus: CURRENT\nwords: > \"<fill: the human's words, verbatim>\"\n"
                "locator: <fill: session + event + UTC, or file@commit>\n" % (rid, today, subject, row_kind or "rule"))
    if kind == "ledger":
        return ("\n## %s — %s\nkind: %s\npathology: -\naxis: <fill: effort|judgement>\nhook: <fill: HOOKED <path> | "
                "OWED <shape> — trigger: <c> | NOT HOOKABLE <why>>\namendment: <fill: path#heading of the mechanism that changed>\n"
                "**What happened.** <fill>\n**The general rule.** <fill>\n> **Re-test trigger:** <fill>\n**Record:** <fill>, %s\n"
                % (rid, subject.upper(), row_kind or "procedural", today))
    return ("\n## %s · %s · %s\nstatus: OPEN\nwhere: <fill: path § heading>\nowner: this-station\nfound_by: <fill>\n"
            "trigger: <fill: cmd: <command> | event: <event> | date: YYYY-MM-DD>\nwhy_not_fixed_now: <fill>\n" % (rid, today, subject))


def main(argv=None):
    _gov.setup_io()
    ap = argparse.ArgumentParser()
    ap.add_argument("register", nargs="?", choices=sorted(REG))
    ap.add_argument("subject", nargs="?")
    ap.add_argument("--kind")
    ap.add_argument("--root")
    ap.add_argument("--no-branch-scan", action="store_true")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.register or not a.subject:
        ap.print_usage()
        return 2
    root = _gov.find_root(a.root)
    rid, rel = next_id(root, a.register, not a.no_branch_scan)
    row = template(a.register, rid, a.subject, a.kind)
    if a.dry:
        sys.stdout.write(row)
        return 0
    p = Path(root) / rel
    if not p.exists():
        title = {"dec": "DECISIONS", "ledger": "LEDGER", "def": "DEFECTS"}[a.register]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# STATION_%s — station rows (%s)\nowner: governance/rules.json · status: CURRENT · date: %s · "
                     "supersedes: none · audit: python3 tools/station_audit.py\n" % (title, _gov.station_name(root), dt.date.today()),
                     encoding="utf-8")
    with open(p, "a", encoding="utf-8") as f:
        f.write(row)
    print("%s appended to %s — fill the <fill> slots" % (rid, rel))
    return 0


def selftest():
    fails, n = [], 0

    def ok(c, m):
        nonlocal n
        n += 1
        if not c:
            fails.append(m)

    with tempfile.TemporaryDirectory() as td:
        r = Path(td)
        _gov.write(r, "governance/DECISIONS.md", "# D\n\n## DEC-core-0001 · 2026-10-16 · a\nkind: rule\n")
        _gov.git(r, "init", "-q", "-b", "main")
        _gov.commit_all(r, "base")
        _gov.git(r, "switch", "-q", "-c", "other")
        _gov.write(r, "governance/DECISIONS.md", "# D\n\n## DEC-core-0001 · x\n\n## DEC-core-0007 · 2026-10-16 · b\n")
        _gov.commit_all(r, "other allocates 0007")
        _gov.git(r, "switch", "-q", "main")
        ok(next_id(r, "dec")[0] == "DEC-core-0008", "branch scan sees other branch's 0007: %s" % next_id(r, "dec")[0])
        ok(next_id(r, "dec", branch_scan=False)[0] == "DEC-core-0002", "no-branch-scan knob")
        ok(main(["dec", "test subject", "--root", td]) == 0, "append")
        t = (r / "governance/DECISIONS.md").read_text()
        ok("## DEC-core-0008 · " in t and "words: > " in t, "templated row appended")
        _gov.write(r, "station.json", '{"name": "markets"}')
        rid, rel = next_id(r, "ledger")
        ok(rid == "L-markets-0001" and rel == "governance/STATION_LEDGER.md", "station picks STATION_ file + prefix: %s %s" % (rid, rel))
        ok(main(["ledger", "a lesson", "--root", td]) == 0 and "## L-markets-0001 — A LESSON" in (r / rel).read_text(), "station ledger row")
        ok(main(["def", "a defect", "--root", td]) == 0 and "## DEF-markets-0001 · " in (r / "governance/STATION_DEFECTS.md").read_text(), "station defect row")
    if fails:
        print("selftest FAILED (%d of %d cases)" % (len(fails), n))
        for f in fails:
            print(" - " + f)
        return 1
    print("selftest OK (%d cases)" % n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
