#!/usr/bin/env python3
"""skills_index.py - every upstream SKILL.md in the census -> its station -> its route.

Earned by: ORDER 4 (d), operator verbatim: "intent study under a per section while
maintaining our skills where there is plausbile gaps and ensuring all 359 are
inclusive in these as well with the relevant intent routing where each would live".
A census row that is homed nowhere, homed twice, or routed to a file that is not
on its home branch is a skill the operator was promised and does not have.
Retires: nothing (no earlier check covered the cross-branch view; per-branch
`skill_routes.py check` stays the station-local half).

Modes
  --write-assignment --plan <kit_plan.yml> --census <SKILL_CENSUS.yml>
        registry/skill_assignment.json = transcription of kit_plan.yml ->
        skills_assignment.rows (the ONE source of truth), plus a byte-for-byte
        copy of the census at registry/SKILL_CENSUS.yml, except rule
        COPYLEFT_PROSE_WITHHELD (fix2-root 1): a row whose repo_licence is GPL-family
        ships description '' plus description_withheld (licence + sha256 of the
        upstream text), so no >= 60-char line of a held copyleft file rides on every
        branch and licence_filter stays clean; ids, paths, shas, licences kept, row
        count unchanged, idempotent. One normalisation
        (fix-kitroot-1 D2, rule NONROUTED_INHERIT): a mirror/symlink whose
        route_to chain ends at a row that is not routed (kind not canonical/
        variant, e.g. a fixture) INHERITS that kind, with route_to null, the
        target's held_path (byte-identical content held once) and copy
        "none (same bytes as <target>, held there)".
        A mirror can only route to something that is itself routed; the
        changed ids are listed in the file's "inherited" field.
  --write   [--from-build <build dir> | --from-git <repo>]
        SKILLS_INDEX.md + registry/skills_index.json (GENERATED). Without a
        source: the pre-routing state (every row PENDING).
  --check   [--from-build ... | --from-git ...]
        exit 1 if ANY census row is unrouted, doubly homed, mis-homed or its
        path is missing on its home branch, or if a copyleft census row still
        carries description prose (COPYLEFT_PROSE_WITHHELD). Headline: VIOLATION
        rows + prose rows are violations; PENDING rows (no station source) are
        the worklist (and still exit 1 under --check).
  --verify  --census <yml> --clones <dir> [--plan <kit_plan.yml>]
        recompute the classification (symlink by git mode 120000, mirror by
        content sha, variant by same (repo,name) other bytes, fixture by path
        marker) and DIFF against the assignment; never writes.
  --selftest

ROUTED means: the home station's router/skills.json (or router/skills.d/*.json)
has a row for the id whose home is that station, and
  canonical/variant: >= 3 keywords and its held path exists on the branch;
  fixture: its held path exists on the branch;
  mirror/symlink: its route_to resolves to a ROUTED row.
"""
import argparse
import collections
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _kit  # noqa: E402

TOOL = "tools/kit/skills_index.py"
FIELDS = ["census_id", "home", "kind", "route_to", "held_path", "copy"]
FIXTURE_MARKERS = ("tests/oracle/", "e2e/fixtures/", "scripts/rlm_eval/", "/fixtures/", "/__fixtures__/")
MIN_KEYWORDS = 3


# ------------------------------------------------------------------ census redaction (fix2-root 1)
# The census ships on main and on every station branch. A station that holds a copyleft upstream
# (venture holds relaticle, AGPL-3.0) runs licence_filter, which refuses any station-authored file
# carrying a >= 60-char line of a held copyleft file; the census' folded description of
# 17:.claude/skills/filament-development/SKILL.md was such a line. Rule COPYLEFT_PROSE_WITHHELD:
# a census row whose repo_licence is GPL-family keeps id, path, name, sha, licence, desc_chars and
# every other key, but its description becomes '' and a description_withheld key records the
# licence and the sha256 of the withheld text (so the upstream copy can still be matched).
COPYLEFT_LICENCE_RE = re.compile(r"^\s*(?:A|L)?GPL", re.I)
WITHHELD_KEY = "description_withheld"
CENSUS_NOTE = ("# COPYLEFT_PROSE_WITHHELD (tools/kit/skills_index.py): rows whose repo_licence is GPL-family carry "
               "description '' and description_withheld (licence + sha256 of the upstream text); "
               "read the held SKILL.md on the home station for the prose.\n")


def is_copyleft_licence(lic):
    return bool(lic) and bool(COPYLEFT_LICENCE_RE.match(str(lic)))


def _yaml_scalar_text(parts):
    """The value of a census scalar from its first-line text and folded continuation lines."""
    v = " ".join(x.strip() for x in parts).strip()
    if len(v) >= 2 and v[0] == v[-1] == "'":
        return v[1:-1].replace("''", "'")
    if len(v) >= 2 and v[0] == v[-1] == '"':
        try:
            return json.loads(v)
        except ValueError:
            return v[1:-1]
    return "" if v in ("null", "~") else v


def redact_census_text(text):
    """Apply COPYLEFT_PROSE_WITHHELD to census text in its fixed shape (`- id:` blocks, two-space keys,
    four-space folded continuations); every other byte is kept. Idempotent.
    Returns (new_text, redacted ids, already-withheld ids)."""
    lines = text.splitlines(keepends=True)
    out, redacted, already = [], [], []
    i, n = 0, len(lines)
    while i < n:
        if not lines[i].startswith("- id:"):
            out.append(lines[i])
            i += 1
            continue
        j = i + 1
        while j < n and lines[j].startswith(" "):
            j += 1
        block = lines[i:j]
        rid = block[0][5:].strip()
        lic = next((l.split(":", 1)[1].strip() for l in block if l.startswith("  repo_licence:")), "")
        has_withheld = any(l.startswith("  %s:" % WITHHELD_KEY) for l in block)
        di = next((k for k, l in enumerate(block) if l.startswith("  description:")), None)
        if di is None or not is_copyleft_licence(lic):
            out.extend(block)
        else:
            dj = di + 1
            while dj < len(block) and block[dj].startswith("    "):
                dj += 1
            desc = _yaml_scalar_text([block[di][len("  description:"):]] + block[di + 1:dj])
            if desc == "" and has_withheld:
                already.append(rid)
                out.extend(block)
            else:
                sha = hashlib.sha256(desc.encode("utf-8")).hexdigest()
                rep = ["  description: ''\n"]
                if not has_withheld:
                    rep.append("  %s: copyleft %s upstream prose not shipped (licence_filter); sha256 %s\n"
                               % (WITHHELD_KEY, lic, sha))
                out.extend(block[:di] + rep + block[dj:])
                redacted.append(rid)
        i = j
    new = "".join(out)
    if (redacted or already) and CENSUS_NOTE not in new:
        # after the leading comment lines, before `meta:`
        k = 0
        body = new.splitlines(keepends=True)
        while k < len(body) and body[k].startswith("#"):
            k += 1
        new = "".join(body[:k]) + CENSUS_NOTE + "".join(body[k:])
    return new, redacted, already


def census_prose_violations(rows):
    """Census rows of a GPL-family repo that still carry description prose."""
    return [r["id"] for r in rows if is_copyleft_licence(r.get("repo_licence")) and (r.get("description") or "").strip()]


# ------------------------------------------------------------------ assignment
ROUTED_KINDS = ("canonical", "variant")
ROUTING_KINDS = ("mirror", "symlink")


def terminal_of(rid, by_id):
    """Follow route_to through mirror/symlink hops; return the terminal id (or None)."""
    tgt, seen = by_id[rid].get("route_to"), {rid}
    while tgt in by_id and by_id[tgt]["kind"] in ROUTING_KINDS and tgt not in seen:
        seen.add(tgt)
        tgt = by_id[tgt].get("route_to")
    return tgt


def normalise_rows(rows):
    """NONROUTED_INHERIT: a mirror/symlink whose terminal target exists but is not routed
    (fixture, or any kind outside canonical/variant) takes the target's kind, no route,
    the target's held_path and copy "none (same bytes as <target>, held there)". Returns (rows, inherited ids). Row count unchanged."""
    by_id = {r["id"]: r for r in rows}
    inherited, out = [], []
    for r in rows:
        r = dict(r)
        if r["kind"] in ROUTING_KINDS:
            t = terminal_of(r["id"], by_id)
            if t in by_id and by_id[t]["kind"] not in ROUTED_KINDS + ROUTING_KINDS:
                r.update(kind=by_id[t]["kind"], route_to=None, held_path=by_id[t].get("held_path"),
                         copy="none (same bytes as %s, held there)" % t)
                inherited.append(r["id"])
        out.append(r)
    return out, inherited


def rows_from_plan(plan, with_inherited=False):
    sa = plan["skills_assignment"]
    fmt = sa.get("rows_format", FIELDS)
    out = []
    for r in sa["rows"]:
        if isinstance(r, dict):
            d = dict(r)
            if "census_id" in d:
                d["id"] = d.pop("census_id")
        else:
            d = dict(zip(fmt, r))
            d["id"] = d.pop("census_id")
        out.append({k: d.get(k) for k in ("id", "home", "kind", "route_to", "held_path", "copy")})
    out, inherited = normalise_rows(out)
    return (out, inherited) if with_inherited else out


def write_assignment(root, plan_path, census_path):
    plan = _kit.read_json(plan_path)
    rows, inherited = rows_from_plan(plan, with_inherited=True)
    census, reader = _kit.load_census(census_path, root)
    cids = [c["id"] for c in census]
    ids = [r["id"] for r in rows]
    problems = []
    dup = [k for k, v in collections.Counter(ids).items() if v > 1]
    if dup:
        problems.append("duplicate assignment ids: %s" % dup[:5])
    missing = sorted(set(cids) - set(ids))
    extra = sorted(set(ids) - set(cids))
    if missing:
        problems.append("%d census ids have no assignment row, e.g. %s" % (len(missing), missing[:3]))
    if extra:
        problems.append("%d assignment ids are not in the census, e.g. %s" % (len(extra), extra[:3]))
    with open(census_path, "rb") as f:
        raw = f.read()
    red_text, redacted, already = redact_census_text(raw.decode("utf-8"))
    cbytes = red_text.encode("utf-8")
    doc = {
        "_generated_by": TOOL,
        "_source": "kit_plan.yml -> skills_assignment.rows (the ONE source of truth), normalised by NONROUTED_INHERIT "
                   "(a mirror/symlink of a non-routed row inherits its kind, no route); regenerate with "
                   "python3 tools/kit/skills_index.py --write-assignment --plan <kit_plan.yml> --census <SKILL_CENSUS.yml>",
        "inherited": inherited,
        "census_file": "registry/SKILL_CENSUS.yml",
        "census_sha256": hashlib.sha256(cbytes).hexdigest(),
        "census_reader": reader,
        "census_copyleft_prose_withheld": {
            "rule": "COPYLEFT_PROSE_WITHHELD: a GPL-family row ships description '' + description_withheld "
                    "(licence, sha256 of the upstream text); every other key kept",
            "count": len(redacted) + len(already),
            "ids": sorted(redacted + already)},
        "denominator": len(rows),
        "by_kind": dict(collections.Counter(r["kind"] for r in rows)),
        "by_home": dict(collections.Counter(r["home"] for r in rows)),
        "rows": rows,
    }
    _kit.write_json(os.path.join(root, "registry", "skill_assignment.json"), doc)
    dst = os.path.join(root, "registry", "SKILL_CENSUS.yml")
    if os.path.abspath(dst) != os.path.abspath(census_path) or cbytes != raw:
        with open(dst, "wb") as f:
            f.write(cbytes)
    shipped, _ = _kit.load_census(dst, root)
    if len(shipped) != len(cids):
        problems.append("redacted census has %d rows, source has %d" % (len(shipped), len(cids)))
    left = census_prose_violations(shipped)
    if left:
        problems.append("%d copyleft row(s) still carry description prose, e.g. %s" % (len(left), left[:3]))
    print("skill_assignment: %d rows / %d census files (reader %s) -> registry/skill_assignment.json; "
          "%d mirror/symlink row(s) inherited a non-routed kind; census: %d copyleft description(s) withheld "
          "(%d newly)" % (len(rows), len(cids), reader, len(inherited), len(redacted) + len(already), len(redacted)))
    for p in problems:
        print("  VIOLATION " + p)
    return 1 if problems else 0


def load_assignment(root):
    d = _kit.read_json(os.path.join(root, "registry", "skill_assignment.json"))
    return d["rows"]


# ------------------------------------------------------------------ station sources
class BuildSource:
    def __init__(self, build):
        self.build = build
        self.desc = "build dir " + build

    def stations(self):
        sd = os.path.join(self.build, "stations")
        return sorted(os.listdir(sd)) if os.path.isdir(sd) else []

    def route_docs(self, st):
        base = os.path.join(self.build, "stations", st, "router")
        out = []
        p = os.path.join(base, "skills.json")
        if os.path.isfile(p):
            out.append(("router/skills.json", _kit.read_json(p)))
        dd = os.path.join(base, "skills.d")
        if os.path.isdir(dd):
            for fn in sorted(os.listdir(dd)):
                if fn.endswith(".json") and not fn.endswith(".selftest.json"):
                    out.append(("router/skills.d/" + fn, _kit.read_json(os.path.join(dd, fn))))
        return out

    def exists(self, st, path):
        return os.path.isfile(os.path.join(self.build, "stations", st, path))


class GitSource:
    def __init__(self, repo):
        self.repo = repo
        self.desc = "git repo " + repo
        self._ls = {}

    def stations(self):
        out = _kit.git_out(self.repo, "for-each-ref", "--format=%(refname:short)", "refs/heads/station/")
        return sorted(x.split("/", 1)[1] for x in out.splitlines() if x.strip() and "--" not in x)

    def _files(self, st):
        if st not in self._ls:
            out = _kit.git(self.repo, "ls-tree", "-r", "--name-only", "-z", "station/" + st).out
            self._ls[st] = set(x for x in out.split("\0") if x)
        return self._ls[st]

    def route_docs(self, st):
        files = self._files(st)
        out = []
        names = (["router/skills.json"] if "router/skills.json" in files else []) + sorted(
            f for f in files if f.startswith("router/skills.d/") and f.endswith(".json")
            and not f.endswith(".selftest.json"))
        for n in names:
            txt = _kit.git(self.repo, "show", "station/%s:%s" % (st, n)).out
            out.append((n, json.loads(txt)))
        return out

    def exists(self, st, path):
        return path in self._files(st)


def route_rows(doc):
    if isinstance(doc, dict):
        return doc.get("skills") or doc.get("rows") or []
    return doc if isinstance(doc, list) else []


# ------------------------------------------------------------------ compute
def compute(assign, census, source):
    names = {c["id"]: c for c in census}
    by_id = {r["id"]: r for r in assign}
    claims = collections.defaultdict(list)   # id -> [(station, row)]
    copies = collections.defaultdict(list)
    station_list = source.stations() if source else []
    for st in station_list:
        for fname, doc in source.route_docs(st):
            for row in route_rows(doc):
                rid = row.get("id")
                if rid not in by_id:
                    continue
                home = row.get("home") or st
                if home == st:
                    claims[rid].append((st, row))
                else:
                    copies[rid].append(st)
    status = {}
    detail = {}
    # first pass: non-routing kinds
    for r in assign:
        rid, home, kind = r["id"], r["home"], r["kind"]
        probs = []
        if source is None:
            status[rid], detail[rid] = "PENDING", ["no station source (pre-routing state on main)"]
            continue
        cl = claims.get(rid, [])
        if len(cl) > 1:
            probs.append("DOUBLY_HOMED on %s" % ",".join(sorted(s for s, _ in cl)))
        homes = [s for s, _ in cl]
        if not cl:
            probs.append("UNROUTED: no row in %s router/skills.json" % home)
        elif home not in homes:
            probs.append("MISHOMED: claimed by %s, assignment says %s" % (",".join(homes), home))
        row = dict(cl[0][1]) if cl else {}
        for s, rw in cl:
            if s == home:
                row = rw
        if kind in ("canonical", "variant", "fixture"):
            path = row.get("path") or r.get("held_path")
            if not path:
                probs.append("PATH_MISSING: no held path")
            elif home not in station_list:
                probs.append("PATH_MISSING: branch station/%s absent" % home)
            elif not source.exists(home, path):
                probs.append("PATH_MISSING: %s not on station/%s" % (path, home))
            if kind != "fixture" and cl:
                kw = row.get("keywords") or []
                if len(kw) < MIN_KEYWORDS:
                    probs.append("UNROUTED: %d keyword(s) < %d" % (len(kw), MIN_KEYWORDS))
        status[rid] = "VIOLATION" if probs else "ROUTED"
        detail[rid] = probs
    # second pass: mirror / symlink resolve through route_to (one hop, then the target's status)
    if source is not None:
        for r in assign:
            if r["kind"] not in ("mirror", "symlink"):
                continue
            rid = r["id"]
            probs = [p for p in detail[rid] if not p.startswith("PATH_MISSING")]
            tgt = r.get("route_to")
            seen = set()
            while tgt in by_id and by_id[tgt]["kind"] in ("mirror", "symlink") and tgt not in seen:
                seen.add(tgt)
                tgt = by_id[tgt].get("route_to")
            if not tgt or tgt not in by_id:
                probs.append("UNROUTED: route_to %r is not a census row" % r.get("route_to"))
            elif status.get(tgt) != "ROUTED":
                probs.append("UNROUTED: route_to %s is not ROUTED" % tgt)
            status[rid] = "VIOLATION" if probs else "ROUTED"
            detail[rid] = probs
    out = []
    for r in assign:
        c = names.get(r["id"], {})
        route = r.get("held_path") if r["kind"] in ("canonical", "variant", "fixture") else "-> " + str(r.get("route_to"))
        out.append({"id": r["id"], "name": c.get("name"), "repo": c.get("repo"), "home": r["home"],
                    "kind": r["kind"], "route": route, "status": status[r["id"]],
                    "problems": detail[r["id"]], "copies_on": sorted(set(copies.get(r["id"], [])))})
    return out, station_list


def render(rows, source_desc, stations):
    cnt = collections.Counter(r["status"] for r in rows)
    n = len(rows)
    doc = {"_generated_by": TOOL, "source": source_desc, "denominator": n,
           "counts": dict(cnt), "stations_seen": stations, "rows": rows}
    md = ["<!-- GENERATED by tools/kit/skills_index.py — edit registry/skill_assignment.json (from kit_plan) or a station's router/skills.json, then run python3 tools/kit/skills_index.py --write --from-git . -->",
          "# SKILLS_INDEX — every census SKILL.md, its station, its route",
          "",
          "Source: %s. Denominator: %d census files (ORDER 4 d: every one is homed and routed)." % (source_desc, n),
          "",
          "| status | rows |", "|---|---|"]
    for k in ("ROUTED", "VIOLATION", "PENDING"):
        md.append("| %s | %d / %d |" % (k, cnt.get(k, 0), n))
    md += ["", "ROUTED = a row on the home branch's `router/skills.json` with >= 3 keywords and its held path present "
           "(fixture: path present; mirror/symlink: `route_to` resolves to a ROUTED row). "
           "`python3 tools/kit/skills_index.py --check --from-git .` exits 1 on any other state.", ""]
    by_home = collections.OrderedDict()
    for r in rows:
        by_home.setdefault(r["home"], []).append(r)
    for home, rs in by_home.items():
        kinds = collections.Counter(r["kind"] for r in rs)
        md.append("## station/%s — %d rows (%s)" % (home, len(rs), ", ".join("%s %d" % kv for kv in sorted(kinds.items()))))
        md.append("")
        md.append("| census id | name | kind | route | status |")
        md.append("|---|---|---|---|---|")
        for r in rs:
            st = r["status"] + ("" if not r["problems"] else ": " + "; ".join(r["problems"]))
            md.append("| `%s` | %s | %s | `%s` | %s |" % (r["id"], r["name"] or "", r["kind"], r["route"], st.replace("|", "/")))
        md.append("")
    return doc, "\n".join(md) + "\n"


def make_source(a):
    if a.from_build:
        return BuildSource(a.from_build)
    if a.from_git:
        return GitSource(a.from_git)
    return None


def cmd_write_or_check(a, root, write):
    try:
        assign = load_assignment(root)
        census, _ = _kit.load_census(os.path.join(root, "registry", "SKILL_CENSUS.yml"), root)
        src = make_source(a)
        rows, stations = compute(assign, census, src)
    except (OSError, ValueError, KeyError, _kit.KitError) as e:
        print("skills_index: unreadable input: %s" % e)
        return 2
    doc, md = render(rows, src.desc if src else "pre-routing (no station source)", stations)
    bad = [r for r in rows if r["status"] != "ROUTED"]
    prose = census_prose_violations(census)
    viol = [r for r in bad if r["status"] == "VIOLATION"]
    pend = [r for r in bad if r["status"] == "PENDING"]
    # PENDING (no station source yet: main before step 5) is a worklist, not a violation; --check still exits 1 on it
    print(_kit.headline("skills_index", len(viol) + len(prose), len(pend), len(rows)))
    for cid in prose[:10]:
        print("  CENSUS %s: copyleft row carries description prose (COPYLEFT_PROSE_WITHHELD; rerun --write-assignment)" % cid)
    if write:
        _kit.write_json(os.path.join(root, "registry", "skills_index.json"), doc)
        with open(os.path.join(root, "SKILLS_INDEX.md"), "w", encoding="utf-8") as f:
            f.write(md)
        print("wrote SKILLS_INDEX.md + registry/skills_index.json (%d ROUTED / %d)" % (len(rows) - len(bad), len(rows)))
        return 0
    for r in bad[:40]:
        print("  %s [%s -> station/%s] %s" % (r["id"], r["kind"], r["home"], "; ".join(r["problems"]) or r["status"]))
    if len(bad) > 40:
        print("  ... %d more" % (len(bad) - 40))
    return 1 if (bad or prose) else 0


# ------------------------------------------------------------------ verify
def classify(census, modes):
    """modes: id -> git mode string ('120000' for symlink). Returns id -> (kind, route_to)."""
    out = {}
    canon_by_sha = {}
    # group mirrors: census mirror_of names the first copy; a group = same (repo_id, sha)
    groups = collections.defaultdict(list)
    for c in census:
        groups[(c.get("repo_id"), c.get("sha"))].append(c)
    for c in census:
        cid = c["id"]
        if modes.get(cid) == "120000":
            out[cid] = ("symlink", None)
            continue
        if c.get("mirror_of"):
            out[cid] = ("mirror", c["mirror_of"])
            continue
        p = c.get("path", "")
        if any(m in "/" + p for m in FIXTURE_MARKERS):
            out[cid] = ("fixture", None)
            continue
        out[cid] = ("canonical", None)
    # NONROUTED_INHERIT (same rule as normalise_rows): a mirror whose terminal copy is not routed takes its kind
    for cid, (k, rt) in list(out.items()):
        if k != "mirror":
            continue
        t, seen = rt, {cid}
        while t in out and out[t][0] == "mirror" and t not in seen:
            seen.add(t)
            t = out[t][1]
        if t in out and out[t][0] not in ROUTED_KINDS + ROUTING_KINDS:
            out[cid] = (out[t][0], None)
    return out


def cmd_verify(a, root):
    try:
        census, reader = _kit.load_census(a.census, root)
        if a.plan:
            assign, inherited = rows_from_plan(_kit.read_json(a.plan), with_inherited=True)
        else:
            assign = load_assignment(root)
            inherited = list(_kit.read_json(os.path.join(root, "registry", "skill_assignment.json")).get("inherited") or [])
    except (OSError, ValueError, KeyError) as e:
        print("skills_index verify: unreadable input: %s" % e)
        return 2
    modes = {}
    by_repo = collections.defaultdict(list)
    for c in census:
        by_repo[c["repo"]].append(c)
    for repo, cs in by_repo.items():
        clone = os.path.join(a.clones, repo.replace("/", "~"))
        if not os.path.isdir(clone):
            print("skills_index verify: clone missing: %s" % clone)
            return 2
        p = _kit.git(clone, "ls-tree", "-r", "-z", "HEAD", "--", *[c["path"] for c in cs], check=False)
        if p.returncode != 0:
            print("skills_index verify: ls-tree failed in %s" % clone)
            return 2
        for ent in p.out.split("\0"):
            if not ent:
                continue
            meta, _, path = ent.partition("\t")
            modes["%s:%s" % (cs[0]["repo_id"], path)] = meta.split()[0]
    base = classify(census, modes)
    plan_by = {r["id"]: r for r in assign}
    diffs = []
    # the planner's rule refinements: a symlink/mirror routes to a canonical; a variant is a
    # non-mirror that shares (repo,name) with the canonical; a canonical choice may flip which
    # copy of a byte-identical pair is the mirror.
    names = collections.defaultdict(list)
    for c in census:
        names[(c["repo_id"], c.get("name"))].append(c["id"])
    for c in census:
        cid = c["id"]
        k, rt = base[cid]
        pr = plan_by.get(cid)
        if pr is None:
            diffs.append("%s: no assignment row" % cid)
            continue
        pk = pr["kind"]
        ok = False
        if k == pk:
            ok = True
            if k == "mirror" and pr.get("route_to") != rt:
                # flipped canonical choice: accept when the plan routes to a byte-identical copy
                tgt = pr.get("route_to")
                same = [x["id"] for x in census if x.get("sha") == c.get("sha") and x.get("repo_id") == c.get("repo_id")]
                ok = tgt in same
        elif k == "canonical" and pk == "variant":
            # same (repo,name) with another census row of different bytes
            ok = len(names[(c["repo_id"], c.get("name"))]) > 1
        elif k == "canonical" and pk == "mirror":
            # canonical choice flipped: the census' "first copy" is the plan's mirror
            tgt = pr.get("route_to")
            ok = any(x["id"] == tgt and x.get("sha") == c.get("sha") for x in census)
        elif k == "mirror" and pk in ("canonical", "fixture", "variant"):
            # flipped the other way: plan keeps this copy, routes the census' original to it
            ok = any(plan_by.get(x["id"], {}).get("route_to") == cid for x in census
                     if x.get("sha") == c.get("sha") and x["id"] != cid)
        elif k == "symlink" and pk == "symlink":
            ok = True
        elif k == "symlink" and cid in inherited:
            # NONROUTED_INHERIT on a symlink: classify() cannot read link targets, normalise_rows did
            ok = pk not in ROUTED_KINDS + ROUTING_KINDS
        if not ok:
            diffs.append("%s: recomputed %s%s, assignment says %s%s" % (
                cid, k, (" -> " + rt) if rt else "", pk, (" -> " + str(pr.get("route_to"))) if pr.get("route_to") else ""))
    extra = sorted(set(plan_by) - set(base))
    for e in extra:
        diffs.append("%s: assignment row not in census" % e)
    print(_kit.headline("skills_index_verify", len(diffs), 0, len(census)))
    print("  census reader: %s; symlinks by git mode: %d" % (reader, sum(1 for v in modes.values() if v == "120000")))
    for d in diffs[:40]:
        print("  " + d)
    return 1 if diffs else 0


# ------------------------------------------------------------------ selftest
def _selftest():
    tmp = tempfile.mkdtemp(prefix="kit-skidx-")
    try:
        root = os.path.join(tmp, "root")
        os.makedirs(os.path.join(root, "registry"))
        census_txt = """meta:
  total_skill_files: 5
skills:
- id: 1:skills/a/SKILL.md
  repo: o/r
  repo_id: 1
  path: skills/a/SKILL.md
  name: a
  description: 'Skill a, which is
    folded'
  sha: aaaa
  mirror_of: null
- id: 1:.agents/skills/a/SKILL.md
  repo: o/r
  repo_id: 1
  path: .agents/skills/a/SKILL.md
  name: a
  description: mirror of a
  sha: aaaa
  mirror_of: 1:skills/a/SKILL.md
- id: 1:skills/b/SKILL.md
  repo: o/r
  repo_id: 1
  path: skills/b/SKILL.md
  name: b
  description: b
  sha: bbbb
  mirror_of: null
- id: 1:tests/oracle/x/SKILL.md
  repo: o/r
  repo_id: 1
  path: tests/oracle/x/SKILL.md
  name: x
  description: fixture
  sha: cccc
  mirror_of: null
- id: 2:s/c/SKILL.md
  repo: p/q
  repo_id: 2
  path: s/c/SKILL.md
  name: c
  description: c
  sha: dddd
  mirror_of: null
- id: 1:tests/oracle/x/.claude/SKILL.md
  repo: o/r
  repo_id: 1
  path: tests/oracle/x/.claude/SKILL.md
  name: x
  description: fixture
  sha: cccc
  mirror_of: 1:tests/oracle/x/SKILL.md
"""
        cpath = os.path.join(tmp, "SKILL_CENSUS.yml")
        open(cpath, "w").write(census_txt)
        plan = {"skills_assignment": {"rows_format": FIELDS, "rows": [
            ["1:skills/a/SKILL.md", "alpha", "canonical", None, "repertoire/o~r/skills/a/SKILL.md", "dir"],
            ["1:.agents/skills/a/SKILL.md", "alpha", "mirror", "1:skills/a/SKILL.md", None, "none"],
            ["1:skills/b/SKILL.md", "alpha", "canonical", None, "repertoire/o~r/skills/b/SKILL.md", "dir"],
            ["1:tests/oracle/x/SKILL.md", "alpha", "fixture", None, "repertoire/o~r/tests/oracle/x/SKILL.md", "file"],
            ["2:s/c/SKILL.md", "beta", "canonical", None, "repertoire/p~q/s/c/SKILL.md", "dir"],
            ["1:tests/oracle/x/.claude/SKILL.md", "alpha", "mirror", "1:tests/oracle/x/SKILL.md", None, "none"],
        ]}}
        ppath = os.path.join(tmp, "plan.yml")
        open(ppath, "w").write(json.dumps(plan))
        assert write_assignment(root, ppath, cpath) == 0
        d = _kit.read_json(os.path.join(root, "registry", "skill_assignment.json"))
        assert len(d["rows"]) == 6 and d["rows"][1]["route_to"] == "1:skills/a/SKILL.md", d
        assert d["rows"][1]["kind"] == "mirror", "a mirror of a routed canonical stays a mirror"
        fx = d["rows"][5]  # D2: a mirror of a fixture inherits class fixture, no route, the fixture's held path
        assert fx == {"id": "1:tests/oracle/x/.claude/SKILL.md", "home": "alpha", "kind": "fixture", "route_to": None,
                      "held_path": "repertoire/o~r/tests/oracle/x/SKILL.md",
                      "copy": "none (same bytes as 1:tests/oracle/x/SKILL.md, held there)"}, fx
        assert d["inherited"] == ["1:tests/oracle/x/.claude/SKILL.md"] and d["denominator"] == 6, d["inherited"]
        assert d["by_kind"] == {"canonical": 3, "mirror": 1, "fixture": 2}, d["by_kind"]
        assert open(os.path.join(root, "registry", "SKILL_CENSUS.yml")).read() == census_txt
        census, _ = _kit.load_census(cpath)
        assert census[0]["description"] == "Skill a, which is folded", census[0]["description"]
        # planted: plan row missing -> violation
        bad = json.loads(json.dumps(plan))
        bad["skills_assignment"]["rows"].pop()
        open(ppath + ".bad", "w").write(json.dumps(bad))
        r2 = os.path.join(tmp, "root2")
        os.makedirs(os.path.join(r2, "registry"))
        assert write_assignment(r2, ppath + ".bad", cpath) == 1

        # build dir with two stations
        build = os.path.join(tmp, "build")

        def put(st, rel, txt="x"):
            p = os.path.join(build, "stations", st, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "w").write(txt)
        for rel in ("repertoire/o~r/skills/a/SKILL.md", "repertoire/o~r/skills/b/SKILL.md",
                    "repertoire/o~r/tests/oracle/x/SKILL.md"):
            put("alpha", rel)
        put("beta", "repertoire/p~q/s/c/SKILL.md")
        kw = ["k1", "k2", "k3"]
        alpha = {"skills": [
            {"id": "1:skills/a/SKILL.md", "home": "alpha", "kind": "canonical", "path": "repertoire/o~r/skills/a/SKILL.md", "keywords": kw},
            {"id": "1:.agents/skills/a/SKILL.md", "home": "alpha", "kind": "mirror", "route_to": "1:skills/a/SKILL.md", "keywords": []},
            {"id": "1:skills/b/SKILL.md", "home": "alpha", "kind": "canonical", "path": "repertoire/o~r/skills/b/SKILL.md", "keywords": kw},
            {"id": "1:tests/oracle/x/SKILL.md", "home": "alpha", "kind": "fixture", "path": "repertoire/o~r/tests/oracle/x/SKILL.md", "keywords": []},
            {"id": "2:s/c/SKILL.md", "home": "beta", "kind": "canonical", "path": "repertoire/p~q/s/c/SKILL.md", "keywords": kw},
            {"id": "1:tests/oracle/x/.claude/SKILL.md", "home": "alpha", "kind": "fixture", "path": "repertoire/o~r/tests/oracle/x/SKILL.md", "keywords": []},
        ]}
        beta = {"skills": [{"id": "2:s/c/SKILL.md", "home": "beta", "kind": "canonical", "path": "repertoire/p~q/s/c/SKILL.md", "keywords": kw}]}
        put("alpha", "router/skills.json", json.dumps(alpha))
        put("beta", "router/skills.json", json.dumps(beta))

        class A:
            from_build = build
            from_git = None
        assert cmd_write_or_check(A, root, write=False) == 0, "clean build must pass"
        assert cmd_write_or_check(A, root, write=True) == 0
        idx = _kit.read_json(os.path.join(root, "registry", "skills_index.json"))
        assert idx["counts"] == {"ROUTED": 6}, idx["counts"]
        assert _kit.declares_generated(open(os.path.join(root, "SKILLS_INDEX.md")).read())
        assert next(r for r in idx["rows"] if r["id"] == "2:s/c/SKILL.md")["copies_on"] == ["alpha"]

        def expect_fail(mutate, why):
            a2 = json.loads(json.dumps(alpha))
            b2 = json.loads(json.dumps(beta))
            mutate(a2, b2)
            put("alpha", "router/skills.json", json.dumps(a2))
            put("beta", "router/skills.json", json.dumps(b2))
            rc = cmd_write_or_check(A, root, write=False)
            assert rc == 1, "planted %s not caught" % why
        # planted 1: unrouted (row removed)
        expect_fail(lambda a2, b2: a2["skills"].pop(2), "unrouted")
        # planted 2: < 3 keywords
        expect_fail(lambda a2, b2: a2["skills"][0].update(keywords=["one"]), "few keywords (and the mirror behind it)")
        # planted 3: doubly homed
        expect_fail(lambda a2, b2: b2["skills"].append(dict(alpha["skills"][2], home="beta")), "doubly homed")
        # planted 4: path missing
        expect_fail(lambda a2, b2: a2["skills"][2].update(path="repertoire/o~r/skills/nope/SKILL.md"), "path missing")
        # planted 5: mirror routes to a non-routed target
        def m5(a2, b2):
            a2["skills"][0]["keywords"] = []
        expect_fail(m5, "mirror to unrouted canonical")
        put("alpha", "router/skills.json", json.dumps(alpha))
        put("beta", "router/skills.json", json.dumps(beta))
        assert cmd_write_or_check(A, root, write=False) == 0

        # git source: same layout as branches of a fixture repo
        repo = os.path.join(tmp, "repo")
        _kit.run(["git", "init", "-q", "-b", "main", repo])
        _kit.fixture_git_config(repo)
        open(os.path.join(repo, "README.md"), "w").write("main\n")
        _kit.stage_paths(repo)
        _kit.commit(repo, "main")
        for st in ("alpha", "beta"):
            _kit.git(repo, "switch", "-q", "-c", "station/" + st, "main")
            _kit.copy_tree(os.path.join(build, "stations", st), repo)
            _kit.stage_paths(repo)
            _kit.commit(repo, st)
            _kit.git(repo, "switch", "-q", "main")

        class G:
            from_build = None
            from_git = repo
        assert cmd_write_or_check(G, root, write=False) == 0, "git source must pass"
        _kit.git(repo, "switch", "-q", "station/alpha")
        os.remove(os.path.join(repo, "repertoire/o~r/skills/b/SKILL.md"))
        _kit.stage_paths(repo)
        _kit.commit(repo, "drop b")
        _kit.git(repo, "switch", "-q", "main")
        assert cmd_write_or_check(G, root, write=False) == 1, "git path-missing not caught"

        # pre-routing: no source -> PENDING, --check fails
        class N:
            from_build = None
            from_git = None
        assert cmd_write_or_check(N, root, write=False) == 1

        # verify: census-only classification vs plan (fixture + mirror + canonical)
        clones = os.path.join(tmp, "clones")
        for repo_name, files in (("o~r", ["skills/a/SKILL.md", ".agents/skills/a/SKILL.md", "skills/b/SKILL.md", "tests/oracle/x/SKILL.md",
                                          "tests/oracle/x/.claude/SKILL.md"]),
                                 ("p~q", ["s/c/SKILL.md"])):
            cr = os.path.join(clones, repo_name)
            _kit.run(["git", "init", "-q", "-b", "main", cr])
            _kit.fixture_git_config(cr)
            for f in files:
                p = os.path.join(cr, f)
                os.makedirs(os.path.dirname(p), exist_ok=True)
                open(p, "w").write(f)
            _kit.stage_paths(cr)
            _kit.commit(cr, "c")

        class V:
            census = cpath
            plan = ppath
        V.clones = clones
        assert cmd_verify(V, root) == 0, "verify clean fixture"
        bad2 = json.loads(json.dumps(plan))
        bad2["skills_assignment"]["rows"][2][2] = "fixture"
        open(ppath + ".bad2", "w").write(json.dumps(bad2))
        V.plan = ppath + ".bad2"
        assert cmd_verify(V, root) == 1, "verify planted kind flip"
        _selftest_redaction(tmp)
        print("selftest OK")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _selftest_redaction(tmp):
    """COPYLEFT_PROSE_WITHHELD: planted AGPL row with a folded >= 60-char description line."""
    long1 = "Builds panel interfaces. Use when creating, modifying, testing or debugging panels, resources,"
    long2 = "pages, schemas, forms, tables, actions, infolists, widgets, imports, or exports."
    txt = ("# SKILL_CENSUS: fixture\nmeta:\n  total_skill_files: 3\nskills:\n"
           "- id: 7:.claude/skills/f/SKILL.md\n  repo: o/agpl\n  repo_id: 7\n  path: .claude/skills/f/SKILL.md\n"
           "  name: f\n  description: %s\n    %s\n  desc_chars: 170\n  fm_ok: true\n  fm_keys:\n  - description\n"
           "  - name\n  sha: 1111\n  repo_licence: AGPL-3.0\n  mirror_of: null\n"
           "- id: 8:skills/m/SKILL.md\n  repo: o/mit\n  repo_id: 8\n  path: skills/m/SKILL.md\n  name: m\n"
           "  description: 'An MIT skill with a long folded description that keeps going and going,\n"
           "    it''s quoted.'\n  sha: 2222\n  repo_licence: MIT\n  mirror_of: null\n"
           "- id: 9:skills/g/SKILL.md\n  repo: o/gpl\n  repo_id: 9\n  path: skills/g/SKILL.md\n  name: g\n"
           "  description: short gpl text\n  sha: 3333\n  repo_licence: GPL-3.0\n  mirror_of: null\n") % (long1, long2)
    red, ids, already = redact_census_text(txt)
    assert ids == ["7:.claude/skills/f/SKILL.md", "9:skills/g/SKILL.md"] and already == [], (ids, already)
    assert long1 not in red and long2 not in red and "short gpl text" not in red, red
    assert "An MIT skill with a long folded description" in red, "a permissive row keeps its prose"
    assert CENSUS_NOTE in red and red.index(CENSUS_NOTE) < red.index("meta:")
    want = hashlib.sha256((long1 + " " + long2).encode()).hexdigest()
    assert "sha256 " + want in red, "withheld text is hashed exactly as the census reader joins it"
    red2, ids2, already2 = redact_census_text(red)
    assert red2 == red and ids2 == [] and len(already2) == 2, "idempotent"
    cp = os.path.join(tmp, "red_census.yml")
    open(cp, "w").write(red)
    for reader in ("stdlib", "kit"):
        rows = _kit.read_census_stdlib(cp) if reader == "stdlib" else _kit.load_census(cp)[0]
        assert len(rows) == 3, (reader, len(rows))
        byid = {r["id"]: r for r in rows}
        assert (byid["7:.claude/skills/f/SKILL.md"].get("description") or "") == "", (reader, byid)
        assert byid["7:.claude/skills/f/SKILL.md"]["sha"] in ("1111", 1111) and byid["7:.claude/skills/f/SKILL.md"]["name"] == "f"
        assert byid["7:.claude/skills/f/SKILL.md"][WITHHELD_KEY].startswith("copyleft AGPL-3.0 "), byid
        assert byid["8:skills/m/SKILL.md"]["description"].endswith("it's quoted."), (reader, byid["8:skills/m/SKILL.md"])
        assert census_prose_violations(rows) == [], reader
    cp0 = os.path.join(tmp, "raw_census.yml")
    open(cp0, "w").write(txt)
    assert census_prose_violations(_kit.read_census_stdlib(cp0)) == ["7:.claude/skills/f/SKILL.md", "9:skills/g/SKILL.md"]
    # write_assignment ships the redacted bytes (also when --census IS the shipped path) and hashes them
    root = os.path.join(tmp, "root_red")
    os.makedirs(os.path.join(root, "registry"))
    plan = {"skills_assignment": {"rows_format": FIELDS, "rows": [
        ["7:.claude/skills/f/SKILL.md", "alpha", "canonical", None, "upstream/o~agpl/f/SKILL.md", "dir"],
        ["8:skills/m/SKILL.md", "alpha", "canonical", None, "repertoire/o~mit/skills/m/SKILL.md", "dir"],
        ["9:skills/g/SKILL.md", "alpha", "canonical", None, "upstream/o~gpl/skills/g/SKILL.md", "dir"]]}}
    pp = os.path.join(tmp, "plan_red.json")
    open(pp, "w").write(json.dumps(plan))
    shipped = os.path.join(root, "registry", "SKILL_CENSUS.yml")
    open(shipped, "w").write(txt)
    assert write_assignment(root, pp, shipped) == 0
    got = open(shipped).read()
    assert got == red, "in-place --census registry/SKILL_CENSUS.yml must still redact"
    d = _kit.read_json(os.path.join(root, "registry", "skill_assignment.json"))
    assert d["census_sha256"] == hashlib.sha256(red.encode()).hexdigest() and d["census_copyleft_prose_withheld"]["count"] == 2
    assert write_assignment(root, pp, shipped) == 0 and open(shipped).read() == red, "second run is a no-op"

    # --check catches a planted unredacted census even when every route is clean
    class N:
        from_build = None
        from_git = None
    open(shipped, "w").write(txt)
    buf = __import__("io").StringIO()
    with __import__("contextlib").redirect_stdout(buf):
        rc = cmd_write_or_check(N, root, write=False)
    assert rc == 1 and "CENSUS 7:.claude/skills/f/SKILL.md" in buf.getvalue(), buf.getvalue()
    assert "skills_index: 2 violation(s) · 3 worklist · denominator 3" in buf.getvalue(), buf.getvalue()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=None, help="kit repo root (default: this file's repo)")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--write-assignment", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--from-build")
    ap.add_argument("--from-git")
    ap.add_argument("--plan")
    ap.add_argument("--census")
    ap.add_argument("--clones")
    a = ap.parse_args(argv)
    root = os.path.abspath(a.root or _kit.REPO_ROOT_GUESS)
    if a.selftest:
        return _selftest()
    if a.write_assignment:
        if not (a.plan and a.census):
            print("--write-assignment needs --plan and --census")
            return 2
        return write_assignment(root, a.plan, a.census)
    if a.verify:
        if not (a.census and a.clones):
            print("--verify needs --census and --clones")
            return 2
        return cmd_verify(a, root)
    if a.write or a.check:
        rc = cmd_write_or_check(a, root, write=a.write)
        if a.write and a.check:
            rc = cmd_write_or_check(a, root, write=False)
        return rc
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
