#!/usr/bin/env python3
"""custody.py — chain of custody (commons; built on research): sources, claims, intake and ToS records. Stdlib only.

owner: governance/rules.d/research.json R-research-market-scan (commons since reconcile-01, DEC-core-0011; the
research station's gap skills source-custody, claim-ledger, intake-capture, tos-gate call it) · kit-authored

Earned by: the research station's purpose ("investigate from public sources with chain of custody", KIT_PLAN 4.3) and
lettuce's measurement contract (every number carries its denominator; a claim with no source row is a claim nobody can
re-derive). Each gap skill names a failing test; this tool is where those tests live so they are code, not prose:
  source-custody   a source marked used without a sha256 capture hash (or a 40-hex git sha for a repo) FAILS
  claim-ledger     a claim with no source row, or citing an unknown source id, is listed UNSUPPORTED and FAILS
  intake-capture   a repo item with status checked and no `ls_remote` record FAILS
  tos-gate         a source gathered by scrape/automation/gateway whose host has no ToS row (or a refuse decision) FAILS
Custody v2 (2026-10-16, research pass 2 — the chain is re-derivable, not just recorded):
  re-hash          a source row naming a `capture` (and `text_capture`) file is re-hashed on every check; a capture that is
                   missing or whose sha256 no longer equals the recorded `hash` / `text_hash` FAILS (hash drift); a used
                   url/file/capture/post/image source must name its capture, so its hash can be re-derived
  grounded         every claim carries `grounds: [{source, quote}]`; each quote must occur (whitespace/case/quote-mark
                   normalised) in that source's text capture, and the source must be one the claim cites — else FAILS
  inferred         an inferred claim also states its `reasoning` (the step from the grounded premises to the claim)
  denominator      a claim whose text carries a percentage or an n=/k= count needs `denominator: {n, population}`
  uncited          `uncited_lines(md)`: every paragraph, list item and table row outside an exempt section (Question,
                   Scope, Method, Gaps, Boundary, Sources, ...) carries a [C<n>]/[S<n>]/[M<n>] tag; deliverables.py
                   applies it to each deliverable's markdown
Retires: nothing in the kit (first custody check; commons nc_export covers the licence side, not custody).

Record shapes (all JSON, beside the deliverable in `work/<job>/<slug>/`):
  sources.json  {"sources": [{"id", "locator", "kind": url|file|repo|capture|post|image, "fetched_utc",
                 "hash": "sha256:<64hex>" | "sha": "<40hex>" (repo), "read": bool, "used": bool,
                 "capture": "captures/S<n>.<ext>" (relative to the record dir), "text_capture", "text_hash",
                 "status": checked|inferred (intake items), "method": manual|api|scrape|automation|gateway,
                 "ls_remote": {"url", "ref", "sha", "utc"} (repo items), "note"}]}
  claims.json   {"claims": [{"id", "text", "sources": [ids], "status": checked|inferred,
                 "grounds": [{"source": id, "quote": "verbatim text from the source's capture"}],
                 "reasoning" (inferred), "denominator": {"n", "population"} (quantitative)}]}
  tos.json      {"sites": [{"host", "tos_url", "robots": allowed|disallowed|partial|unknown, "checked_utc",
                 "decision": proceed|manual-only|refuse, "reason"}]}

CLI:
  custody.py check [--root DIR]                      every work/**/{sources,claims,tos}.json (audit check `custody`)
  custody.py hash <file>                             print sha256:<hex> of a captured file
  custody.py verify --dir D                          one record dir, every rule above (the per-deliverable chain check)
  custody.py plant --dir D                           copy a CLEAN record dir to a temp dir, plant 6 defects one at a time
                                                     (tamper a capture, drop a capture, break a quote, drop grounds,
                                                     uncite a line, unknown source) and prove each turns the check red
  custody.py add-source --dir D --locator L [--file F] [--kind K] [--method M] [--used] [--status S] [--note N]
                                                     append a row (hash from --file); ids S1, S2, ...
  custody.py ls-remote --dir D --id S<n> --sha <40hex> [--ref HEAD] [--url U]
                                                     record a `git ls-remote <url> <ref>` result the operator ran
  custody.py tos-gate --dir D --url U               exit 0 when the host has a proceed/manual-only ToS row, else 1
  custody.py --selftest
Exit: 0 clean · 1 violation/refused · 2 unreadable/usage.
Release: none needed; a check never blocks a tool call. Fix the record (add the hash, the source, the ToS row).
"""
import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "upstream"))
import _uplib as U  # noqa: E402

NAME = "custody"
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?Z$")
KINDS = ("url", "file", "repo", "capture", "post", "image")
METHODS = ("manual", "api", "scrape", "automation", "gateway")
GATHERED = ("scrape", "automation", "gateway")
CAPTURED_KINDS = ("url", "file", "capture", "post", "image")
TAG_ANY_RE = re.compile(r"\[(?:[CSM]\d+)\]")
QUANT_RE = re.compile(r"\d\s*%|\b[nk]\s*=\s*\d", re.I)
MIN_QUOTE = 12
EXEMPT_SECTIONS = re.compile(r"^(question|scope|method|methods|search plan|inclusion rule|screening|gaps|boundary|sources|custody|"
                             r"how to re-?verify|limitations|notes|grade scheme|reproduce)\b", re.I)
STATUS = ("checked", "inferred")
DECISIONS = ("proceed", "manual-only", "refuse")
ROBOTS = ("allowed", "disallowed", "partial", "unknown")
SCAN_TOPS = ("work", "engagements")


def now_utc():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def host_of(locator):
    u = urlparse(locator if "://" in locator else "https://" + locator)
    return (u.hostname or "").lower().lstrip(".")


def host_matches(host, site):
    site = (site or "").lower().lstrip(".")
    if site.startswith("www."):
        site = site[4:]
    h = host[4:] if host.startswith("www.") else host
    return bool(site) and (h == site or h.endswith("." + site))


def load(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        raise ValueError("%s unreadable: %s" % (path, e))


# ---------------------------------------------------------------- per-directory checks
def norm_text(t):
    """Normalise for quote matching: unify quote marks and dashes, drop soft hyphens, collapse whitespace, casefold."""
    t = str(t or "")
    for a, b in (("‘", "'"), ("’", "'"), ("“", '"'), ("”", '"'), ("–", "-"), ("—", "-"),
                 (" ", " "), ("­", "")):
        t = t.replace(a, b)
    return re.sub(r"\s+", " ", t).strip().casefold()


def rehash(d, rel, r):
    """Re-derive a source row's capture hashes from the bytes on disk; [] when they still match."""
    viol = []
    if d is None:
        return viol
    for fkey, hkey in (("capture", "hash"), ("text_capture", "text_hash")):
        cap = r.get(fkey)
        if not cap:
            continue
        p = (Path(d) / cap).resolve()
        try:
            p.relative_to(Path(d).resolve())
        except ValueError:
            viol.append("%s: %s %r lies outside the record dir" % (rel, fkey, cap))
            continue
        if not p.is_file():
            viol.append("%s: %s %s is missing (the hash can no longer be re-derived)" % (rel, fkey, cap))
        elif file_hash(p) != r.get(hkey):
            viol.append("%s: HASH DRIFT %s %s no longer matches its recorded %s" % (rel, fkey, cap, hkey))
    return viol


def text_of(d, r):
    """The text a quote is matched against: the text capture, else a text-like raw capture; None when absent."""
    for fkey in ("text_capture", "capture"):
        cap = r.get(fkey)
        if cap and d is not None and (Path(d) / cap).is_file():
            b = (Path(d) / cap).read_bytes()
            if fkey == "capture" and b[:4096].count(b"\x00"):
                continue
            return b.decode("utf-8", "replace")
    return None


def check_sources(rel, obj, tos_rows, d=None):
    viol, ids = [], {}
    rows = U.rows_of(obj, "sources")
    for i, r in enumerate(rows):
        sid = r.get("id") or "#%d" % i
        tag = "%s %s" % (rel, sid)
        if not r.get("id"):
            viol.append("%s: source row without id" % tag)
        elif sid in ids:
            viol.append("%s: duplicate source id" % tag)
        ids[sid] = r
        if not r.get("locator"):
            viol.append("%s: no locator (url or path)" % tag)
        if r.get("kind") not in KINDS:
            viol.append("%s: kind %r not in %s" % (tag, r.get("kind"), list(KINDS)))
        if not UTC_RE.match(str(r.get("fetched_utc", ""))):
            viol.append("%s: fetched_utc %r is not an ISO UTC time (YYYY-MM-DDTHH:MM[:SS]Z)" % (tag, r.get("fetched_utc")))
        if r.get("used") is True:
            ok = HASH_RE.match(str(r.get("hash", ""))) or (r.get("kind") == "repo" and SHA_RE.match(str(r.get("sha", ""))))
            if not ok:
                viol.append("%s: used source without a capture hash (sha256:<hex>, or a 40-hex sha for a repo)" % tag)
            if r.get("read") is False:
                viol.append("%s: used but marked read: false" % tag)
            if r.get("kind") in CAPTURED_KINDS and not r.get("capture"):
                viol.append("%s: used %s source names no `capture` file (its hash cannot be re-derived)" % (tag, r.get("kind")))
        elif r.get("hash") and not HASH_RE.match(str(r["hash"])):
            viol.append("%s: hash %r is not sha256:<64 hex>" % (tag, r["hash"]))
        viol += rehash(d, tag, r)
        if "status" in r and r["status"] not in STATUS:
            viol.append("%s: status %r not in %s" % (tag, r["status"], list(STATUS)))
        if r.get("kind") == "repo" and r.get("status") == "checked":
            lr = r.get("ls_remote") or {}
            if not (SHA_RE.match(str(lr.get("sha", ""))) and lr.get("ref") and UTC_RE.match(str(lr.get("utc", "")))):
                viol.append("%s: checked repo item without an ls_remote record {url, ref, sha (40-hex), utc}" % tag)
        m = r.get("method", "manual")
        if m not in METHODS:
            viol.append("%s: method %r not in %s" % (tag, m, list(METHODS)))
        elif m in GATHERED:
            h = host_of(str(r.get("locator", "")))
            row = next((t for t in tos_rows if host_matches(h, t.get("host"))), None)
            if row is None:
                viol.append("%s: gathered by %s from %s with no ToS row in tos.json (tos-gate)" % (tag, m, h or "?"))
            elif row.get("decision") != "proceed":
                viol.append("%s: gathered by %s from %s but its ToS decision is %r" % (tag, m, h, row.get("decision")))
    return viol, ids, len(rows)


def check_grounds(tag, grounds, cited, ids, d):
    """Each ground {source, quote} names a cited source and its quote occurs in that source's capture text."""
    viol = []
    if not isinstance(grounds, list) or not grounds:
        return ["%s: UNGROUNDED (no grounds: [{source, quote}] — a quote line from the captured source)" % tag]
    for j, g in enumerate(grounds):
        g = g if isinstance(g, dict) else {}
        sid, quote = g.get("source"), str(g.get("quote") or "")
        gt = "%s ground %d" % (tag, j + 1)
        if sid not in cited:
            viol.append("%s: source %r is not among the claim's sources" % (gt, sid))
            continue
        if sid not in ids:
            continue  # reported as UNSUPPORTED already
        if len(norm_text(quote)) < MIN_QUOTE:
            viol.append("%s: quote shorter than %d characters (quote the source, not a keyword)" % (gt, MIN_QUOTE))
            continue
        if d is None:
            continue
        txt = text_of(d, ids[sid])
        if txt is None:
            viol.append("%s: source %s has no text capture to ground the quote in" % (gt, sid))
        elif norm_text(quote) not in norm_text(txt):
            viol.append("%s: QUOTE NOT FOUND in %s's capture: %.60s" % (gt, sid, quote))
    return viol


def check_claims(rel, obj, ids, d=None):
    viol = []
    rows = U.rows_of(obj, "claims")
    seen = set()
    for i, c in enumerate(rows):
        cid = c.get("id") or "#%d" % i
        tag = "%s %s" % (rel, cid)
        if cid in seen:
            viol.append("%s: duplicate claim id" % tag)
        seen.add(cid)
        src = c.get("sources") or []
        unknown = [s for s in src if s not in ids]
        if not src:
            viol.append("%s: UNSUPPORTED (no source row): %.70s" % (tag, c.get("text", "")))
        elif unknown:
            viol.append("%s: UNSUPPORTED (unknown source id %s)" % (tag, ", ".join(map(str, unknown))))
        if c.get("status") not in STATUS:
            viol.append("%s: status %r not in %s" % (tag, c.get("status"), list(STATUS)))
        elif c["status"] == "checked" and src and not unknown and not any(ids[s].get("used") for s in src):
            viol.append("%s: checked claim cites no source marked used" % tag)
        elif c["status"] == "inferred" and not str(c.get("reasoning") or "").strip():
            viol.append("%s: inferred claim without `reasoning` (the step from its grounded premises)" % tag)
        if src:
            viol += check_grounds(tag, c.get("grounds"), set(src), ids, d)
        if c.get("quantitative") is True or QUANT_RE.search(str(c.get("text", ""))):
            den = c.get("denominator")
            if not (isinstance(den, dict) and den.get("n") not in (None, "") and str(den.get("population") or "").strip()):
                viol.append("%s: quantitative claim without denominator {n, population} (R-denominator)" % tag)
    return viol, len(rows)


def uncited_lines(md, tag_re=TAG_ANY_RE, exempt=EXEMPT_SECTIONS):
    """(line number, text) of every claim unit with no tag: a paragraph, list item or table data row outside an exempt
    `##` section and outside the preamble before the first `##`. A unit may opt out with `<!-- no-claim -->`."""
    out, sec, in_code, unit = [], None, False, []
    lines = (md or "").splitlines()

    def flush():
        if unit and sec is not None and not exempt.match(sec):
            text = " ".join(t for _, t in unit)
            if not tag_re.search(text) and "<!-- no-claim -->" not in text:
                out.append((unit[0][0], text[:90]))
        unit.clear()

    for i, raw in enumerate(lines, 1):
        line = raw.strip()
        if line.startswith("```"):
            flush()
            in_code = not in_code
            continue
        if in_code:
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            flush()
            if len(m.group(1)) == 2:
                sec = m.group(2).strip()
            continue
        if not line or (line.startswith("<!--") and line.endswith("-->") and "no-claim" not in line):
            flush()
            continue
        if line.startswith("|"):
            flush()
            if re.match(r"^\|[\s:|-]+\|?$", line):
                continue
            nxt = lines[i].strip() if i < len(lines) else ""
            if re.match(r"^\|[\s:|-]+\|?$", nxt):
                continue  # header row
            unit.append((i, line))
            flush()
            continue
        if re.match(r"^([-*+]|\d+[.)])\s", line):
            flush()
        unit.append((i, line))
    flush()
    return out


def check_tos(rel, obj):
    viol = []
    rows = U.rows_of(obj, "sites")
    for i, t in enumerate(rows):
        tag = "%s %s" % (rel, t.get("host") or "#%d" % i)
        if not t.get("host"):
            viol.append("%s: ToS row without host" % tag)
        if t.get("decision") not in DECISIONS:
            viol.append("%s: decision %r not in %s" % (tag, t.get("decision"), list(DECISIONS)))
        if t.get("robots") not in ROBOTS:
            viol.append("%s: robots %r not in %s" % (tag, t.get("robots"), list(ROBOTS)))
        if not UTC_RE.match(str(t.get("checked_utc", ""))):
            viol.append("%s: checked_utc missing or not ISO UTC" % tag)
        if not (t.get("reason") or "").strip():
            viol.append("%s: no reason recorded for the decision" % tag)
    return viol, rows, len(rows)


def check_dir(root, d):
    rel = d.relative_to(root).as_posix()
    tos = load(d / "tos.json")
    sv, tos_rows, tn = check_tos(rel + "/tos.json", tos) if tos is not None else ([], [], 0)
    src = load(d / "sources.json")
    v1, ids, n1 = check_sources(rel + "/sources.json", src, tos_rows, d) if src is not None else ([], {}, 0)
    cl = load(d / "claims.json")
    v2, n2 = check_claims(rel + "/claims.json", cl, ids, d) if cl is not None else ([], 0)
    if cl is not None and src is None:
        v2.append("%s/claims.json: no sources.json beside it (every claim maps to source rows)" % rel)
    return sv + v1 + v2, tn + n1 + n2


def record_dirs(root):
    out = set()
    for top in SCAN_TOPS:
        base = Path(root) / top
        if base.is_dir():
            for name in ("sources.json", "claims.json", "tos.json"):
                out.update(p.parent for p in base.rglob(name))
    return sorted(out)


def cmd_check(root):
    root = Path(root)
    viol, denom = [], 0
    try:
        for d in record_dirs(root):
            v, n = check_dir(root, d)
            viol += v
            denom += n
    except ValueError as e:
        print("%s: UNREADABLE %s" % (NAME, e))
        return 2
    return U.finish(NAME, viol, [], denom)


# ---------------------------------------------------------------- writers
def file_hash(p):
    return "sha256:" + hashlib.sha256(Path(p).read_bytes()).hexdigest()


SKIP_MD = ("FALSIFICATION.md", "README.md")


def verify_dir(d):
    """Every custody rule on one record dir plus the uncited-line rule on its top-level markdown -> violations."""
    d = Path(d).resolve()
    viol, _ = check_dir(d.parent, d)
    for md in sorted(d.glob("*.md")):
        if md.name in SKIP_MD:
            continue
        for ln, text in uncited_lines(md.read_text(encoding="utf-8")):
            viol.append("%s/%s:%d: UNCITED claim line (no [C/S/M] tag): %s" % (d.name, md.name, ln, text))
    return viol


def cmd_verify(a):
    d = Path(a.dir)
    if not (d / "sources.json").is_file():
        print("custody verify: no sources.json in %s" % d)
        return 2
    try:
        viol = verify_dir(d)
    except ValueError as e:
        print("custody verify: UNREADABLE %s" % e)
        return 2
    return U.finish("custody-verify", viol, [], 1)


def _plant(t):
    """The 6 planted defects: name -> (mutation on a copied record dir, needle the check must print)."""
    t = Path(t)
    src = json.loads((t / "sources.json").read_text(encoding="utf-8"))
    cl = json.loads((t / "claims.json").read_text(encoding="utf-8")) if (t / "claims.json").is_file() else {"claims": []}
    cap = next((r for r in src["sources"] if r.get("used") and r.get("capture")), None)
    gc = next((c for c in cl["claims"] if c.get("grounds")), None)

    def tamper():
        p = t / cap["capture"]
        p.write_bytes(p.read_bytes() + b" ")

    def drop():
        (t / cap["capture"]).unlink()

    def mutate_claim(fn):
        def f():
            fn(gc)
            (t / "claims.json").write_text(json.dumps(cl), encoding="utf-8")
        return f

    def uncite():
        for md in sorted(t.glob("*.md")):
            if md.name in SKIP_MD:
                continue
            lines = md.read_text(encoding="utf-8").splitlines()
            sec = None
            for i, l in enumerate(lines):
                if l.startswith("## "):
                    sec = l[3:].strip()
                elif sec and not EXEMPT_SECTIONS.match(sec) and TAG_ANY_RE.search(l):
                    # a whole new paragraph: stripping tags from one line of a multi-line unit can leave it cited
                    lines[i:i] = ["", "This planted sentence states a fact and cites nothing.", ""]
                    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
                    return
        raise RuntimeError("no tagged prose line to uncite")

    out = []
    if cap:
        out += [("tampered capture", tamper, "HASH DRIFT"), ("capture deleted", drop, "is missing")]
    if gc:
        out += [("quote altered", mutate_claim(lambda c: c["grounds"][0].update(quote=c["grounds"][0]["quote"] + " (not in source)")),
                 "QUOTE NOT FOUND"),
                ("grounds dropped", mutate_claim(lambda c: c.pop("grounds")), "UNGROUNDED"),
                ("unknown source cited", mutate_claim(lambda c: c.update(sources=["S999"])), "UNSUPPORTED")]
    out.append(("claim line uncited", uncite, "UNCITED"))
    return out


def cmd_plant(a):
    import shutil
    d = Path(a.dir)
    base = verify_dir(d)
    if base:
        print("custody plant: %s is not clean before planting (%d violations); fix it first" % (d, len(base)))
        return 2
    n_red, rows = 0, []
    with tempfile.TemporaryDirectory() as t0:
        probe = Path(t0) / d.name
        shutil.copytree(d, probe)
        names = [(n, needle) for n, _, needle in _plant(probe)]
    for name, needle in names:
        with tempfile.TemporaryDirectory() as t1:
            c = Path(t1) / d.name
            shutil.copytree(d, c)
            fn = dict((n, f) for n, f, _ in _plant(c))[name]
            fn()
            v = verify_dir(c)
            hit = any(needle in x for x in v)
            n_red += hit
            rows.append("  %-22s -> %s (%d violation(s); needle %r %s)" % (name, "RED" if hit else "MISSED", len(v), needle,
                                                                          "found" if hit else "absent"))
    print("custody plant: %s clean before planting; %d of %d planted defects turned the check red" % (d, n_red, len(names)))
    print("\n".join(rows))
    return 0 if n_red == len(names) else 1


def _load_or(path, key):
    obj = load(path)
    if obj is None:
        obj = {"_schema": "research-%s/1" % key, key: []}
    obj.setdefault(key, [])
    return obj


def _write(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def cmd_add_source(a):
    p = Path(a.dir) / "sources.json"
    obj = _load_or(p, "sources")
    n = 1 + max([int(r["id"][1:]) for r in obj["sources"] if re.fullmatch(r"S\d+", str(r.get("id", "")))] or [0])
    row = {"id": "S%d" % n, "locator": a.locator, "kind": a.kind, "fetched_utc": now_utc(), "read": True,
           "used": bool(a.used), "method": a.method}
    if a.file:
        import shutil
        dst = Path(a.dir) / "captures" / (row["id"] + Path(a.file).suffix)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(a.file, dst)
        row["hash"] = file_hash(dst)
        row["capture"] = dst.relative_to(Path(a.dir)).as_posix()
    if a.status:
        row["status"] = a.status
    if a.note:
        row["note"] = a.note
    obj["sources"].append(row)
    _write(p, obj)
    print("custody: added %s -> %s" % (row["id"], p))
    return 0


def cmd_ls_remote(a):
    p = Path(a.dir) / "sources.json"
    obj = _load_or(p, "sources")
    if not SHA_RE.match(a.sha):
        print("custody: --sha must be 40 hex (paste the first column of `git ls-remote <url> %s`)" % a.ref)
        return 2
    for r in obj["sources"]:
        if r.get("id") == a.id:
            r["ls_remote"] = {"url": a.url or r.get("locator"), "ref": a.ref, "sha": a.sha, "utc": now_utc()}
            if r.get("kind") == "repo":
                r.setdefault("sha", a.sha)
            _write(p, obj)
            print("custody: ls_remote recorded on %s" % a.id)
            return 0
    print("custody: no source %s in %s" % (a.id, p))
    return 1


def cmd_tos_gate(a):
    obj = load(Path(a.dir) / "tos.json")
    h = host_of(a.url)
    row = next((t for t in U.rows_of(obj, "sites") if host_matches(h, t.get("host"))), None) if obj else None
    if row is None:
        print("tos-gate: REFUSED %s — no ToS/robots row for %s in %s/tos.json (record the stance first)" % (a.url, h, a.dir))
        return 1
    if row.get("decision") == "refuse":
        print("tos-gate: REFUSED %s — recorded decision refuse: %s" % (a.url, row.get("reason", "")))
        return 1
    print("tos-gate: %s %s (robots %s; %s)" % (row.get("decision"), h, row.get("robots"), row.get("reason", "")))
    return 0


# ---------------------------------------------------------------- selftest
def selftest():
    import contextlib
    import io
    fails = []
    good_hash = "sha256:" + "a" * 64
    sha = "b" * 40

    def run(t, files):
        for rel, obj in files.items():
            if isinstance(obj, str):
                Path(t, rel).parent.mkdir(parents=True, exist_ok=True)
                Path(t, rel).write_text(obj, encoding="utf-8")
            else:
                _write(Path(t) / rel, obj)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cmd_check(t)
        return rc, buf.getvalue()

    cap_txt = "The station keeps a custody row for every source it touches.\n"
    cap_hash = "sha256:" + hashlib.sha256(cap_txt.encode()).hexdigest()
    CAP = {"work/inv/x/captures/S1.txt": cap_txt}
    base_src = {"id": "S1", "locator": "https://example.org/a", "kind": "url", "fetched_utc": "2026-10-16T10:00:00Z",
                "read": True, "used": True, "hash": cap_hash, "capture": "captures/S1.txt"}
    G = [{"source": "S1", "quote": "keeps a custody row for every source"}]
    claim = {"id": "C1", "text": "t", "sources": ["S1"], "status": "checked", "grounds": G}

    def inv(src=None, claims=None, extra=None):
        f = dict(CAP)
        f["work/inv/x/sources.json"] = {"sources": src or [base_src]}
        if claims is not None:
            f["work/inv/x/claims.json"] = {"claims": claims}
        f.update(extra or {})
        return f

    cases = [
        ("clean empty", {}, 0),
        ("clean pair", inv(claims=[claim]), 0),
        ("used without hash", inv(src=[dict(base_src, hash=None)]), 1),
        ("unmapped claim", inv(claims=[dict(claim, sources=[], status="inferred")]), 1),
        ("unknown source id", inv(claims=[dict(claim, sources=["S9"], grounds=[{"source": "S9", "quote": "x" * 20}])]), 1),
        ("claims without sources.json", {"work/inv/x/claims.json": {"claims": [claim]}}, 1),
        # custody v2 planted defects: each one alone turns the check red
        ("hash drift", inv(claims=[claim], extra={"work/inv/x/captures/S1.txt": cap_txt + "edited later\n"}), 1),
        ("capture missing", {"work/inv/x/sources.json": {"sources": [base_src]}}, 1),
        ("used url without capture", inv(src=[{k: v for k, v in base_src.items() if k != "capture"}]), 1),
        ("ungrounded claim", inv(claims=[{k: v for k, v in claim.items() if k != "grounds"}]), 1),
        ("quote not in capture", inv(claims=[dict(claim, grounds=[{"source": "S1", "quote": "keeps no records at all, ever"}])]), 1),
        ("quote too short", inv(claims=[dict(claim, grounds=[{"source": "S1", "quote": "custody"}])]), 1),
        ("ground on uncited source", inv(claims=[dict(claim, grounds=[{"source": "S2", "quote": "keeps a custody row for"}])]), 1),
        ("inferred without reasoning", inv(claims=[dict(claim, status="inferred")]), 1),
        ("inferred with reasoning", inv(claims=[dict(claim, status="inferred", reasoning="premise S1 implies it")]), 0),
        ("quantitative without denominator", inv(claims=[dict(claim, text="62% of rows carry a hash")]), 1),
        ("quantitative with denominator", inv(claims=[dict(claim, text="62% of rows carry a hash",
                                                           denominator={"n": 50, "population": "rows in sources.json"})]), 0),
        ("quote normalised (case, quotes, spaces)", inv(claims=[dict(claim, grounds=[{"source": "S1", "quote": "KEEPS a  custody\nrow"}])]), 0),
        ("checked repo without ls_remote", {"work/intake/d/sources.json": {"sources": [
            {"id": "S1", "locator": "https://github.com/o/r", "kind": "repo", "fetched_utc": "2026-10-16T10:00Z",
             "read": True, "used": True, "sha": sha, "status": "checked"}]}}, 1),
        ("checked repo with ls_remote", {"work/intake/d/sources.json": {"sources": [
            {"id": "S1", "locator": "https://github.com/o/r", "kind": "repo", "fetched_utc": "2026-10-16T10:00Z",
             "read": True, "used": True, "sha": sha, "status": "checked",
             "ls_remote": {"url": "https://github.com/o/r", "ref": "HEAD", "sha": sha, "utc": "2026-10-16T10:01Z"}}]}}, 0),
        ("scrape without ToS row", inv(src=[dict(base_src, method="scrape")]), 1),
        ("gateway without ToS row", inv(src=[dict(base_src, method="gateway")]), 1),
        ("scrape with ToS proceed", inv(src=[dict(base_src, method="scrape", locator="https://www.example.org/b")],
                                        extra={"work/inv/x/tos.json": {"sites": [{"host": "example.org", "tos_url": "https://example.org/terms",
                                                                                  "robots": "allowed", "checked_utc": "2026-10-16T09:00Z",
                                                                                  "decision": "proceed", "reason": "public pages, robots allow"}]}}), 0),
        ("scrape with ToS refuse", inv(src=[dict(base_src, method="automation")],
                                       extra={"work/inv/x/tos.json": {"sites": [{"host": "example.org", "robots": "disallowed",
                                                                                 "checked_utc": "2026-10-16T09:00Z", "decision": "refuse",
                                                                                 "reason": "ToS forbids automated access"}]}}), 1),
    ]
    for name, files, want in cases:
        with tempfile.TemporaryDirectory() as t:
            rc, out = run(t, files)
            if rc != want or not out.startswith("custody: "):
                fails.append("%s: rc %s want %s · %s" % (name, rc, want, out.strip()[:200]))
    with tempfile.TemporaryDirectory() as t:
        Path(t, "work/x").mkdir(parents=True)
        Path(t, "work/x/sources.json").write_text("{broken")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cmd_check(t)
        if rc != 2 or "UNREADABLE" not in buf.getvalue():
            fails.append("unreadable sources.json must exit 2: %s" % buf.getvalue())
        Path(t, "work/x/sources.json").unlink()
        # writers + gate round trip
        cap = Path(t, "cap.png")
        cap.write_bytes(b"pixels")
        d = Path(t, "work/intake/2026-10-16")
        ns = argparse.Namespace
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_add_source(ns(dir=str(d), locator="https://github.com/o/r", file=str(cap), kind="repo", method="manual",
                              used=True, status="checked", note=None))
            r1 = cmd_check(Path(t))
        if r1 != 1:
            fails.append("checked repo item without ls_remote must fail after add-source")
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_ls_remote(ns(dir=str(d), id="S1", sha=sha, ref="HEAD", url=None))
            r2 = cmd_check(Path(t))
        if r2 != 0:
            fails.append("after ls-remote the record must be clean")
        with contextlib.redirect_stdout(io.StringIO()):
            g1 = cmd_tos_gate(ns(dir=str(d), url="https://example.org/x"))
        _write(d / "tos.json", {"sites": [{"host": "example.org", "robots": "allowed", "checked_utc": "2026-10-16T09:00Z",
                                           "decision": "manual-only", "reason": "read by hand only"}]})
        with contextlib.redirect_stdout(io.StringIO()):
            g2 = cmd_tos_gate(ns(dir=str(d), url="https://sub.example.org/x"))
        if (g1, g2) != (1, 0):
            fails.append("tos-gate: no row must refuse (got %s), manual-only row must pass (got %s)" % (g1, g2))
    md_cases = [
        ("# T\nQuestion: x\n\n## Findings\n- a claim [C1]\n- an uncited claim\n", 1),
        ("# T\n## Gaps\nanything goes here\n## Conclusion\nRests on [C1] and\ncontinues here.\n", 0),
        ("## Matrix\n| id | what |\n|---|---|\n| [S1] | x |\n| S2 | y |\n", 1),
        ("## Findings\n```\ncode line\n```\nA transition. <!-- no-claim -->\n", 0),
        ("## Findings\nA figure [M1] and a paragraph\n\nwith no tag at all.\n", 1),
    ]
    for i, (md, want) in enumerate(md_cases):
        got = len(uncited_lines(md))
        if got != want:
            fails.append("uncited_lines case %d: %d uncited, want %d" % (i, got, want))
    for f in fails:
        print("FAIL " + f)
    print("selftest %s (%d cases)" % ("OK" if not fails else "FAILED", len(cases) + len(md_cases) + 4))
    return 0 if not fails else 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="custody.py", description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    c = sub.add_parser("check")
    c.add_argument("--root")
    h = sub.add_parser("hash")
    h.add_argument("file")
    s = sub.add_parser("add-source")
    s.add_argument("--dir", required=True)
    s.add_argument("--locator", required=True)
    s.add_argument("--file")
    s.add_argument("--kind", default="url", choices=KINDS)
    s.add_argument("--method", default="manual", choices=METHODS)
    s.add_argument("--used", action="store_true")
    s.add_argument("--status", choices=STATUS)
    s.add_argument("--note")
    lr = sub.add_parser("ls-remote")
    lr.add_argument("--dir", required=True)
    lr.add_argument("--id", required=True)
    lr.add_argument("--sha", required=True)
    lr.add_argument("--ref", default="HEAD")
    lr.add_argument("--url")
    v = sub.add_parser("verify")
    v.add_argument("--dir", required=True)
    pl = sub.add_parser("plant")
    pl.add_argument("--dir", required=True)
    tg = sub.add_parser("tos-gate")
    tg.add_argument("--dir", required=True)
    tg.add_argument("--url", required=True)
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    try:
        if a.cmd == "check":
            return cmd_check(U.find_root(a.root))
        if a.cmd == "hash":
            print(file_hash(a.file))
            return 0
        if a.cmd == "add-source":
            return cmd_add_source(a)
        if a.cmd == "ls-remote":
            return cmd_ls_remote(a)
        if a.cmd == "tos-gate":
            return cmd_tos_gate(a)
        if a.cmd == "verify":
            return cmd_verify(a)
        if a.cmd == "plant":
            return cmd_plant(a)
    except (ValueError, OSError) as e:
        print("custody: UNREADABLE %s" % e)
        return 2
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
