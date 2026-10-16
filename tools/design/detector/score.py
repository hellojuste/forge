"""score.py — turn findings into per-rule / per-category scores, a readable report and a verdict exit code.

Scoring is ours (impeccable reports findings, not scores). Each rule that fires costs points by severity
(error 12, warning 5, advisory 1); repeats of one rule cost less each time (1 + log2(count)), so one systemic
mistake does not drown every other signal. A category score is 100 minus its rules' costs, floored at 0.
The overall score is the mean of the slop and quality scores. Rules that could not run (rendered rules without a
browser, design-system rules without a DESIGN.md) are listed as NOT RUN and never counted as clean.
"""
import json
import math

WEIGHT = {"error": 12.0, "warning": 5.0, "advisory": 1.0}
FAIL_ORDER = {"none": 99, "error": 3, "warning": 2, "advisory": 1}
SEV_RANK = {"error": 3, "warning": 2, "advisory": 1}


def rule_cost(severity, count):
    return WEIGHT.get(severity, 5.0) * (1 + math.log2(count)) if count else 0.0


def summarise(findings, registry, ran, not_run):
    """findings: list of dicts; registry: {id: row}; ran: set of rule ids that ran; not_run: {id: reason}."""
    per_rule = {}
    for f in findings:
        r = per_rule.setdefault(f["rule"], {"count": 0, "severity": f["severity"], "examples": []})
        r["count"] += 1
        if SEV_RANK[f["severity"]] > SEV_RANK[r["severity"]]:
            r["severity"] = f["severity"]
        if len(r["examples"]) < 3:
            r["examples"].append({"file": f.get("file", ""), "line": f.get("line", 0), "snippet": f.get("snippet", "")})
    cats = {}
    for rid, row in registry.items():
        cat = row["category"]
        c = cats.setdefault(cat, {"cost": 0.0, "rules_run": 0, "rules_hit": 0, "rules_not_run": 0, "rules_total": 0})
        c["rules_total"] += 1
        if rid in not_run:
            c["rules_not_run"] += 1
        elif rid in ran:
            c["rules_run"] += 1
        if rid in per_rule:   # a NOT RUN rule can still carry labelled static-approx (advisory) findings
            c["rules_hit"] += 1
            pr = per_rule[rid]
            pr["cost"] = round(rule_cost(pr["severity"], pr["count"]), 2)
            c["cost"] += pr["cost"]
    scopes = {}
    for rid, pr in per_rule.items():
        for s in registry[rid].get("scopes") or []:
            scopes[s] = scopes.get(s, 0.0) + pr["cost"]
    for c in cats.values():
        c["score"] = max(0, int(round(100 - c["cost"])))
        c["cost"] = round(c["cost"], 2)
    overall = int(round(sum(c["score"] for c in cats.values()) / len(cats))) if cats else 100
    return {
        "score": overall,
        "categories": cats,
        "scopes": {s: max(0, int(round(100 - v))) for s, v in sorted(scopes.items())},
        "rules": {rid: per_rule[rid] for rid in sorted(per_rule)},
        "counts": {
            "findings": len(findings),
            "error": sum(1 for f in findings if f["severity"] == "error"),
            "warning": sum(1 for f in findings if f["severity"] == "warning"),
            "advisory": sum(1 for f in findings if f["severity"] == "advisory"),
            "rules_total": len(registry),
            "rules_run": len([r for r in registry if r in ran and r not in not_run]),
            "rules_hit": len(per_rule),
            "rules_not_run": len(not_run),
        },
        "not_run": dict(sorted(not_run.items())),
    }


def verdict(summary, fail_on="warning", min_score=None):
    """0 pass · 1 fail. Fails when a finding at/above fail_on exists, or the score is under min_score."""
    limit = FAIL_ORDER.get(fail_on, 2)
    worst = 0
    for pr in summary["rules"].values():
        worst = max(worst, SEV_RANK[pr["severity"]])
    reasons = []
    if worst >= limit:
        reasons.append("findings at or above %s" % fail_on)
    if min_score is not None and summary["score"] < min_score:
        reasons.append("score %d < %d" % (summary["score"], min_score))
    return (1 if reasons else 0), reasons


def text_report(target, summary, findings, registry, code, reasons):
    c = summary["counts"]
    lines = ["detector report — %s" % target,
             "score %d/100 · slop %s · quality %s · %d finding(s) (%d error, %d warning, %d advisory)" % (
                 summary["score"], summary["categories"].get("slop", {}).get("score", "-"),
                 summary["categories"].get("quality", {}).get("score", "-"), c["findings"], c["error"], c["warning"],
                 c["advisory"]),
             "rules: %d run, %d hit, %d not run, of %d" % (c["rules_run"], c["rules_hit"], c["rules_not_run"], c["rules_total"])]
    if summary["scopes"]:
        lines.append("scopes: " + ", ".join("%s %d" % kv for kv in summary["scopes"].items()))
    lines.append("")
    order = sorted(summary["rules"].items(), key=lambda kv: (-SEV_RANK[kv[1]["severity"]], -kv[1]["cost"], kv[0]))
    for rid, pr in order:
        row = registry[rid]
        lines.append("[%s] %s (%s, %s) x%d  -%.1f" % (pr["severity"].upper(), rid, row["name"], row["category"], pr["count"], pr["cost"]))
        lines.append("    why: " + row["description"])
        for ex in pr["examples"]:
            lines.append("    at %s:%s  %s" % (ex.get("file", target), ex["line"], ex["snippet"][:160]))
    if summary["not_run"]:
        lines.append("")
        lines.append("NOT RUN (never counted clean):")
        for rid, why in summary["not_run"].items():
            lines.append("  %s — %s" % (rid, why))
    lines.append("")
    lines.append("verdict: exit %d%s" % (code, (" — " + "; ".join(reasons)) if reasons else " — clean at this threshold"))
    return "\n".join(lines)


def dump_json(target, summary, findings, code, reasons, engine_info):
    return json.dumps({"target": target, "exit": code, "reasons": reasons, "engine": engine_info,
                       "summary": summary, "findings": findings}, indent=1, ensure_ascii=False)
