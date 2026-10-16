#!/usr/bin/env python3
"""sizing.py — the shared market-scan check: every market figure carries its source, n, unit, geography and arithmetic. Stdlib only.

owner: governance/rules.d/research.json R-research-market-scan (check `market_scan`; commons since reconcile-01,
DEC-core-0011) · callers: skill market-scan (every station), research's market-scan workflow + deliverables.py · kit-authored

Earned by: research pass 2 (PRIME 2026-10-16 item 5): career and venture will call the same market-scan capability as
research, so its rules live in one importable, directory-agnostic module instead of inside deliverables.py. It runs on
any record dir (`--dir`), needs only custody.py beside it (and _uplib for the finish line), and never assumes the
research station layout. deliverables.py `--kind market` delegates to `rules()` here.
Retires: the inline rules_market body of deliverables.py (moved here verbatim, then extended with grounds + denominator).

Record dir (any path): MARKET.md · sources.json · claims.json · sizing.json · captures/ (gateway.py writes them)
  sizing.json {"market", "geography", "as_of": "YYYY-MM", "figures": [{"id": "M<n>", "label": TAM|SAM|SOM|..., "figure": number,
               "unit", "geography", "as_of": "YYYY-MM", "approach": top-down|bottom-up, "sources": [S ids],
               "arithmetic": "how the figure follows from the quoted source numbers",
               "grounds": [{"source", "quote"}]   (each quote holds a number and occurs in that source's capture),
               "denominator": {"n", "population"} (what the figure counts over),
               "status": sourced|UNSOURCED, "total_of": [M ids]}]}
Rules: a sourced figure has unit, geography, as_of, arithmetic, >= 1 used source published within 24 months of as_of,
grounds whose quotes are found in the captures and carry a digit, and a denominator; both approaches appear among the
sourced figures; a total never folds in an UNSOURCED figure; every figure id appears in MARKET.md as [M<n>].
An UNSOURCED figure is shown but never summed: that is the sized-claim rule.
NC boundary (KIT_PLAN 4.3; research keeps the lane, nc_stamp and nc_export): a record whose MARKET.md carries the
NC-LANE stamp, or whose source row names the nc-lane path or a capture carrying the stamp, FAILS: NC-derived numbers
never reach a client-bi, venture or career deliverable through the shared market-scan.

CLI:
  sizing.py check --dir D [--md MARKET.md]     custody verify (hash, grounds, uncited lines) + the sizing rules
  sizing.py init --dir D --market M --geography G --as-of YYYY-MM   empty record + DRAFT (fails until filled)
  sizing.py scan [--root R]                    the `market_scan` audit row: check every work/**/sizing.json and
                                               engagements/**/sizing.json record dir (denominator = records)
  sizing.py --selftest
Exit: 0 clean · 1 violation · 2 unreadable/usage.
"""
import argparse
import contextlib
import hashlib
import io
import json
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "upstream"))
sys.path.insert(0, str(HERE))
import _uplib as U  # noqa: E402
import custody as C  # noqa: E402

NAME = "sizing"
APPROACHES = ("top-down", "bottom-up")
YM_RE = re.compile(r"^(\d{4})-(\d{2})(-\d{2})?$")
STALE_MONTHS = 24


def months(ym):
    m = YM_RE.match(str(ym or ""))
    return int(m.group(1)) * 12 + int(m.group(2)) - 1 if m else None


def rules(d, tag, srcs, md=None):
    """Sizing rules on one record dir -> violations. `srcs` are its sources.json rows."""
    d = Path(d)
    viol = []
    byid = {s.get("id"): s for s in srcs}
    rows = U.rows_of(C.load(d / "sizing.json"), "figures")
    if md is None:
        md = (d / "MARKET.md").read_text(encoding="utf-8") if (d / "MARKET.md").is_file() else ""
    if not rows:
        return ["%s/sizing.json: no figures" % tag]
    ids = {r.get("id"): r for r in rows}
    seen_app = set()
    for r in rows:
        rid = r.get("id", "?")
        t = "%s/sizing.json %s" % (tag, rid)
        if not re.match(r"^M\d+$", str(rid)):
            viol.append("%s: id must be M<n>" % t)
        if not isinstance(r.get("figure"), (int, float)):
            viol.append("%s: figure must be a number" % t)
        if r.get("status") not in ("sourced", "UNSOURCED"):
            viol.append("%s: status %r not sourced|UNSOURCED" % (t, r.get("status")))
            continue
        if not re.search(r"\[%s\]" % re.escape(str(rid)), md):
            viol.append("%s/MARKET.md: figure %s is not shown" % (tag, rid))
        for inner in r.get("total_of") or []:
            if (ids.get(inner) or {}).get("status") != "sourced":
                viol.append("%s: total folds in %s, which is not a sourced figure" % (t, inner))
        if r["status"] == "UNSOURCED":
            continue
        if r.get("approach") not in APPROACHES:
            viol.append("%s: approach %r not in %s" % (t, r.get("approach"), list(APPROACHES)))
        else:
            seen_app.add(r["approach"])
        for k in ("unit", "geography", "arithmetic"):
            if not str(r.get(k, "")).strip():
                viol.append("%s: sourced figure without %s" % (t, k))
        den = r.get("denominator")
        if not (isinstance(den, dict) and den.get("n") not in (None, "") and str(den.get("population") or "").strip()):
            viol.append("%s: sourced figure without denominator {n, population} (every number carries its n)" % t)
        asof = months(r.get("as_of"))
        if asof is None:
            viol.append("%s: as_of %r is not YYYY-MM" % (t, r.get("as_of")))
        if not r.get("sources"):
            viol.append("%s: sourced figure cites no source" % t)
        for sid in r.get("sources") or []:
            s = byid.get(sid)
            if s is None:
                viol.append("%s: unknown source %s" % (t, sid))
                continue
            if not s.get("used"):
                viol.append("%s: source %s not marked used" % (t, sid))
            pub = months(s.get("published"))
            if pub is None:
                viol.append("%s: source %s has no published YYYY-MM[-DD]; the figure must be UNSOURCED" % (t, sid))
            elif asof is not None and asof - pub > STALE_MONTHS:
                viol.append("%s: source %s is %d months older than as_of (> %d): mark the figure UNSOURCED" % (t, sid, asof - pub, STALE_MONTHS))
        if r.get("sources"):
            viol += C.check_grounds(t, r.get("grounds"), set(r.get("sources") or []), byid, d)
            for g in r.get("grounds") or []:
                if isinstance(g, dict) and not re.search(r"\d", str(g.get("quote") or "")):
                    viol.append("%s: ground quote from %s holds no number (quote the source figure itself)" % (t, g.get("source")))
    for a in APPROACHES:
        if a not in seen_app:
            viol.append("%s/sizing.json: no sourced %s figure (both approaches, with their spread)" % (tag, a))
    return viol


NC_CITE_RE = re.compile(r"(?<![\w-])%s/" % re.escape(U.LANES[3]))


def nc_violations(d, tag, srcs, md):
    """The NC boundary: nothing derived from the CC BY-NC lane feeds a shared market-scan."""
    viol = []
    if U.NC_STAMP_RE.search(md or ""):
        viol.append("%s/MARKET.md carries the NC-LANE stamp: an NC-derived scan never feeds a shared market-scan" % tag)
    for s in srcs:
        sid = s.get("id", "?")
        hit = any(NC_CITE_RE.search(str(s.get(k) or "")) for k in ("locator", "capture", "text_capture", "note"))
        for k in ("capture", "text_capture"):
            f = Path(d) / str(s.get(k) or "")
            if s.get(k) and f.is_file():
                try:
                    hit = hit or bool(U.NC_STAMP_RE.search(f.read_text(encoding="utf-8", errors="replace")[:4000]))
                except OSError:
                    pass
        if hit:
            viol.append("%s/sources.json %s is NC-derived (nc-lane path or NC-LANE stamp): the NC lane stays in research" % (tag, sid))
    return viol


def check(d, md_name="MARKET.md"):
    d = Path(d)
    missing = [f for f in (md_name, "sources.json", "claims.json", "sizing.json") if not (d / f).is_file()]
    if missing:
        return ["%s: missing %s" % (d.name, f) for f in missing]
    viol = C.verify_dir(d)
    srcs = U.rows_of(C.load(d / "sources.json"), "sources")
    md = (d / md_name).read_text(encoding="utf-8")
    viol += nc_violations(d, d.name, srcs, md)
    viol += rules(d, d.name, srcs, md)
    if (d / "DRAFT").exists():
        viol.append("%s: DRAFT marker present (unfinished)" % d.name)
    return viol


SKELETON = """# Market scan: {market} ({geography}, as of {as_of})

## Scope
Market: {market} · geography: {geography} · as of: {as_of} · public sources only (own-customer data is venture's).

## Method
Segments and competitors by the market-segments and competitor-analysis methods; sizing by market-sizing under the
sized-claim rules (both approaches, every figure with source, n, unit, geography, arithmetic; UNSOURCED never summed).

## Segments

## Competitors

## Sizing

| id | label | figure | unit | approach | arithmetic | n / population |
|---|---|---|---|---|---|---|

## Spread

## Gaps
"""


def cmd_init(a):
    d = Path(a.dir)
    if d.exists() and any(d.iterdir()):
        print("sizing init: %s exists and is not empty" % d)
        return 1
    d.mkdir(parents=True, exist_ok=True)
    (d / "MARKET.md").write_text(SKELETON.format(market=a.market, geography=a.geography, as_of=a.as_of), encoding="utf-8")
    for f, key in (("sources.json", "sources"), ("claims.json", "claims")):
        C._write(d / f, {"_schema": "research-%s/1" % key, key: []})
    C._write(d / "sizing.json", {"_schema": "research-figures/1", "market": a.market, "geography": a.geography,
                                 "as_of": a.as_of, "figures": []})
    (d / "DRAFT").write_text("remove this file when the scan is finished\n", encoding="utf-8")
    print("sizing init: wrote %s/ (MARKET.md, sources.json, claims.json, sizing.json, DRAFT)" % d)
    return 0


def selftest():
    txt1 = "Dealers sold 1,050,000 bicycles in 2024, of which 52% were electric.\n"
    txt2 = "The average price of a new e-bike was EUR 2,950 in 2024.\n"

    def h(t):
        return "sha256:" + hashlib.sha256(t.encode()).hexdigest()

    def src(i, txt, pub):
        return {"id": "S%d" % i, "locator": "https://example.org/%d" % i, "kind": "url", "fetched_utc": "2026-10-16T10:00:00Z",
                "read": True, "used": True, "hash": h(txt), "capture": "captures/S%d.txt" % i, "published": pub}

    good_fig = [
        {"id": "M1", "label": "units", "figure": 546000, "unit": "e-bikes/yr", "geography": "NL", "as_of": "2026-10",
         "approach": "top-down", "sources": ["S1"], "arithmetic": "1,050,000 x 52%", "status": "sourced",
         "grounds": [{"source": "S1", "quote": "sold 1,050,000 bicycles in 2024, of which 52% were electric"}],
         "denominator": {"n": 1050000, "population": "bicycles sold by NL dealers in 2024"}},
        {"id": "M2", "label": "value", "figure": 1.61e9, "unit": "EUR/yr", "geography": "NL", "as_of": "2026-10",
         "approach": "bottom-up", "sources": ["S1", "S2"], "arithmetic": "546,000 x EUR 2,950", "status": "sourced",
         "grounds": [{"source": "S2", "quote": "average price of a new e-bike was EUR 2,950"}],
         "denominator": {"n": 546000, "population": "e-bikes sold in NL in 2024"}},
        {"id": "M3", "label": "SOM", "figure": 1, "unit": "EUR/yr", "status": "UNSOURCED"}]
    base = {
        "MARKET.md": "# m\n## Sizing\n| [M1] | [M2] | [M3] |\n## Gaps\nnone\n",
        "sources.json": {"sources": [src(1, txt1, "2025-03"), src(2, txt2, "2025-06")]},
        "claims.json": {"claims": []},
        "sizing.json": {"figures": good_fig},
        "captures/S1.txt": txt1, "captures/S2.txt": txt2,
    }

    def run(files):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t) / "scan"
            for rel, obj in files.items():
                p = d / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(obj if isinstance(obj, str) else json.dumps(obj), encoding="utf-8")
            return check(d)

    def fig(i, **kw):
        f = json.loads(json.dumps(base))
        f["sizing.json"]["figures"][i].update(kw)
        for k, v in list(kw.items()):
            if v is None:
                f["sizing.json"]["figures"][i].pop(k)
        return f

    cases = [
        (base, None),
        (fig(0, grounds=[{"source": "S1", "quote": "sold 2,000,000 bicycles in 2024"}]), "QUOTE NOT FOUND"),
        (fig(0, grounds=[{"source": "S1", "quote": "of which were electric bicycles"}]), "QUOTE NOT FOUND"),
        (fig(1, grounds=[{"source": "S2", "quote": "average price of a new e-bike was"}]), "holds no number"),
        (fig(0, denominator=None), "without denominator"),
        (fig(0, grounds=None), "UNGROUNDED"),
        (fig(1, approach="top-down"), "no sourced bottom-up"),
        (fig(0, total_of=["M3"]), "folds in M3"),
        (fig(0, unit=""), "without unit"),
        (dict(base, **{"captures/S2.txt": txt2.replace("2,950", "3,950")}), "HASH DRIFT"),
        (dict(base, **{"sources.json": {"sources": [src(1, txt1, "2023-01"), src(2, txt2, "2025-06")]}}), "older than as_of"),
        (dict(base, **{"MARKET.md": "## Sizing\n| [M1] | [M2] |\nThe market is large.\n"}), "UNCITED"),
        (dict(base, **{"MARKET.md": "## Sizing\n| [M1] | [M2] |\n"}), "figure M3 is not shown"),
        (dict(base, **{"MARKET.md": U.NC_STAMP + "\n" + base["MARKET.md"]}), "NC-LANE stamp"),
        (dict(base, **{"sources.json": {"sources": [dict(src(1, txt1, "2025-03"), note="from nc-lane/out/x.md"),
                                                    src(2, txt2, "2025-06")]}}), "is NC-derived"),
        (dict(base, **{"captures/S2.txt": U.NC_STAMP + "\n" + txt2,
                       "sources.json": {"sources": [src(1, txt1, "2025-03"), src(2, U.NC_STAMP + "\n" + txt2, "2025-06")]}}),
         "is NC-derived"),
    ]
    fails = []
    for i, (files, needle) in enumerate(cases):
        v = run(files)
        if needle is None and v:
            fails.append("case %d must be clean: %s" % (i, v[:3]))
        if needle is not None and not any(needle in x for x in v):
            fails.append("case %d: %r not raised: %s" % (i, needle, v[:3]))
    with tempfile.TemporaryDirectory() as t:
        with contextlib.redirect_stdout(io.StringIO()):
            if scan(t) != 0:
                fails.append("scan of a root with no records must be clean (main)")
        rec = Path(t) / "work" / "markets" / "x"
        for rel, obj in base.items():
            pth = rec / rel
            pth.parent.mkdir(parents=True, exist_ok=True)
            pth.write_text(obj if isinstance(obj, str) else json.dumps(obj), encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = scan(t)
        if rc != 0 or "denominator 1" not in buf.getvalue():
            fails.append("scan of one clean record must be clean, denominator 1: %s" % buf.getvalue()[:200])
        (rec / "MARKET.md").write_text(U.NC_STAMP + "\n" + base["MARKET.md"], encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            if scan(t) != 1:
                fails.append("scan must fail an NC-stamped record")
    cases.append((None, "scan"))
    with tempfile.TemporaryDirectory() as t:
        with contextlib.redirect_stdout(io.StringIO()):
            rc = cmd_init(argparse.Namespace(dir=t + "/m", market="x", geography="NL", as_of="2026-10"))
        if rc != 0 or not check(t + "/m"):
            fails.append("an init skeleton must fail the check until filled")
    for f in fails:
        print("FAIL " + f)
    print("sizing selftest %s (%d cases)" % ("OK" if not fails else "FAILED", len(cases) + 1))
    return 0 if not fails else 1


def scan(root="."):
    """The market_scan audit row: every sizing.json record dir under work/ and engagements/ (never nc-lane/)."""
    root = Path(root)
    dirs = sorted({p.parent for base in ("work", "engagements") if (root / base).is_dir()
                   for p in (root / base).rglob("sizing.json") if "/%s/" % U.LANES[3] not in "/" + p.as_posix()})
    viol = []
    for d in dirs:
        try:
            viol += ["%s: %s" % (d.relative_to(root).as_posix(), v) for v in check(d)]
        except ValueError as e:
            viol.append("%s: UNREADABLE %s" % (d.relative_to(root).as_posix(), e))
    return U.finish("market_scan", viol, [], len(dirs))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="sizing.py", description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    c = sub.add_parser("check")
    c.add_argument("--dir", required=True)
    c.add_argument("--md", default="MARKET.md")
    s = sub.add_parser("scan")
    s.add_argument("--root", default=".")
    i = sub.add_parser("init")
    i.add_argument("--dir", required=True)
    i.add_argument("--market", required=True)
    i.add_argument("--geography", required=True)
    i.add_argument("--as-of", dest="as_of", required=True)
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    try:
        if a.cmd == "check":
            return U.finish(NAME, check(a.dir, a.md), [], 1)
        if a.cmd == "scan":
            return scan(a.root)
        if a.cmd == "init":
            if not re.match(r"^\d{4}-\d{2}$", a.as_of):
                print("sizing init: --as-of must be YYYY-MM")
                return 2
            return cmd_init(a)
    except ValueError as e:
        print("sizing: UNREADABLE %s" % e)
        return 2
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
