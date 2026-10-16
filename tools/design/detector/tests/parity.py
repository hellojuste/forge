#!/usr/bin/env python3
"""parity.py — run our detector over impeccable's own fixtures and compare rule sets with upstream's goldens.

tests/upstream/fixtures/ are impeccable's tests/fixtures/antipatterns (Apache-2.0, pin in expected.json);
expected.json holds the rule counts upstream's static engine reports for each (`detect --no-config --json`).
Per fixture we compare the SET of rule ids (counts are reported, not judged). Per rule: true positives (fixtures
where both fire), false negatives (upstream fires, we do not), false positives (we fire, upstream does not).

  parity.py [--rule ID] [--fixture NAME] [--show]     report
  parity.py --min-agree 0.85                          exit 1 when fixture-level set agreement drops under the floor
"""
import argparse
import collections
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from detector import engine  # noqa: E402
from detector import registry as R  # noqa: E402


def run_fixture(path):
    counts = collections.Counter()
    for f in engine.collect([path]):
        findings, _, _ = engine.scan_file(f, R.RULES)
        counts.update(x["rule"] for x in findings)
    return dict(counts)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--rule")
    ap.add_argument("--fixture")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--min-agree", type=float)
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    exp = json.loads((HERE / "upstream" / "expected.json").read_text(encoding="utf-8"))["fixtures"]
    per_rule = collections.defaultdict(lambda: {"tp": 0, "fn": [], "fp": []})
    agree, total, rows = 0, 0, {}
    for name, want in sorted(exp.items()):
        if a.fixture and a.fixture not in name:
            continue
        got = run_fixture(HERE / "upstream" / "fixtures" / name)
        ws, gs = set(want["rules"]), set(got)
        if a.rule:
            ws, gs = ws & {a.rule}, gs & {a.rule}
        total += 1
        agree += ws == gs
        rows[name] = {"want": want["rules"], "got": got, "match": ws == gs}
        for r in ws & gs:
            per_rule[r]["tp"] += 1
        for r in ws - gs:
            per_rule[r]["fn"].append(name)
        for r in gs - ws:
            per_rule[r]["fp"].append(name)
        if a.show and ws != gs:
            print("%-48s missing %s  extra %s" % (name, sorted(ws - gs), sorted(gs - ws)))
    print("fixtures with identical rule sets: %d / %d" % (agree, total))
    for r in sorted(per_rule):
        p = per_rule[r]
        print("  %-32s tp %3d  fn %3d  fp %3d%s" % (r, p["tp"], len(p["fn"]), len(p["fp"]),
              ("   fn: " + ", ".join(p["fn"][:4]) if p["fn"] and a.show else "")))
    if a.json:
        Path(a.json).write_text(json.dumps({"agree": agree, "total": total, "per_rule": per_rule, "fixtures": rows}, indent=1), encoding="utf-8")
    if a.min_agree is not None and total and agree / total < a.min_agree:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
