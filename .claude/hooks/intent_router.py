#!/usr/bin/env python3
"""intent_router.py -- UserPromptSubmit: route every human prompt to ONE first move (GOV 3.12, LEAN CA-06/LL-19).

owner: governance/rules.json R-router . table: router/intents.json (+ router/intents.d/*.json, router/kit_tree.json,
router/skills.json). Never blocks; plain stdout (UserPromptSubmit delivers it); any failure prints
"intent_router: could not classify (<reason>)" and exits 0.

Behaviour:
 1. harness turns (router_tie_rule's harness_prefixes) print nothing.
 2. the prompt is lowercased and split into clauses at , ; : ! ? newline and ". "; keywords match whole words,
    phrases and path_patterns as substrings, file_types as token suffixes, patterns as regexes; a hit is cancelled
    by a negator within neg_window words before it in the same clause ("never touch upstream/x" is not a request).
 3. >= multi_intent_cap intents matched -> "ROUTER: n intents matched (...) — not routed; likely a pasted document".
 4. otherwise the earliest matched intent in router_tie_rule.order wins (`station:*` stands for every
    contributed_by station row and every kit_tree leaf); conversational or nothing -> no FIRST MOVE line.
 5. FIRST MOVE line with PRESENT/ABSENT read live from disk (.claude/skills/<n>/SKILL.md, .claude/workflows/<n>.js).
 6. on main (no station.json) kit_tree leaves route: "STATION: <x> — git worktree add ~/stations/<x> station/<x>".
    On a station, scope:main rows only hint: a leaf for ANOTHER station beating every local intent by >= 2 keyword
    hits prints "WRONG STATION? this looks like <x> (git worktree add ../<x> station/<x>)".
 7. no intent fired -> skill fall-through from router/skills.json: <= 2 "SKILL: read <path> (<name>)" lines
    (match_skills: whole-word keyword hits, then phrases, canonical before variant; mirror/symlink rows resolve
    through route_to). An intent's FIRST MOVE won -> the TOP skill match is ALSO printed as one "SKILL: read" line
    when its score (keyword + phrase hits) clears skill_also_min_hits (router/intents.json, default 2), it is not the
    first move's own skill, and the lines so far plus it fit max_out_bytes (fix2-commons 6, ROUTER SHADOWING:
    station intents captured skill prompts before the skill tier - markets 15/93, career 20/41 skill positives).
    The tie order and the cost rules are unchanged: the FIRST MOVE line stays first and is still the one route.
 8. plug-ins in-process: context_threshold.line(payload), tools/brain.py surface(prompt). Total output is cut at
    max_out_bytes (1,200) with a "…TRUNCATED <k> B" marker.
Importable: match_skills(prompt, rows, k=2), route(prompt, root) -- no side effects at import.
Earned by: lettuce R105 ("THE FIRST SHOULD ALWAYS GATHER"); ~15 harness turns misrouted in one session; four words
cancelled "no idea why the bridge fails"; 11 of 13 multi-intent prompts were pasted documents.
"""
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIND_RANK = {"canonical": 0, "variant": 1, "gap": 0, "kit": 0, "copy": 1, "fixture": 3, "symlink_text": 2}
CLAUSE_RE = re.compile(r"[,;:!?\n]|\.(?=\s|$)")
WORD_RE = re.compile(r"[a-z0-9'][a-z0-9'_\-]*")


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _frag_files(root, rel):
    d = Path(root) / rel
    return sorted(p for p in d.glob("*.json") if not p.name.endswith(".selftest.json")) if d.is_dir() else []


def load_table(root):
    """(table dict, local intents, hint rows, station name or None)."""
    root = Path(root)
    table = _load(root / "router" / "intents.json")
    rows = [dict(r) for r in table.get("intents", [])]
    for p in _frag_files(root, "router/intents.d"):
        rows.extend(dict(r) for r in _load(p).get("intents", []))
    kt = root / "router" / "kit_tree.json"
    if kt.exists():
        k = _load(kt)
        for r in (k.get("intents") or k.get("leaves") or k.get("rows") or []):
            r = dict(r)
            r.setdefault("scope", "main")
            r.setdefault("contributed_by", "kit")
            rows.append(r)
    station = None
    sp = root / "station.json"
    if sp.exists():
        try:
            station = _load(sp).get("name") or "station"
        except ValueError:
            station = "station"
    if station:
        local = [r for r in rows if r.get("scope") != "main"]
        hints = [r for r in rows if r.get("scope") == "main"]
    else:
        local, hints = rows, []
    return table, local, hints, station


# ---------------------------------------------------------------- matching
def clauses(prompt):
    return [c for c in CLAUSE_RE.split(prompt.lower()) if c.strip()]


def _negated(clause, start, negators, window):
    before = WORD_RE.findall(clause[:start])
    if not before:
        return False
    tail = before[-window:] if window else []
    singles = {n for n in negators if " " not in n}
    if any(w in singles for w in tail):
        return True
    joined = " ".join(before[-(window + 2):])
    return any(" " in n and n in joined for n in negators)


def _kw_re(kw):
    return re.compile(r"(?<![a-z0-9])" + re.escape(kw.lower()) + r"(?![a-z0-9])")


def hits(row_router, prompt, negators, window, cls=None):
    """{'kw': n, 'phrase': n, 'other': n} distinct non-negated items that match."""
    cls = cls if cls is not None else clauses(prompt)
    out = {"kw": 0, "phrase": 0, "other": 0}

    def any_hit(finder):
        for c in cls:
            for m in finder(c):
                if not _negated(c, m, negators, window):
                    return True
        return False

    for kw in row_router.get("keywords") or []:
        rx = _kw_re(kw)
        if kw.strip() and any_hit(lambda c: [m.start() for m in rx.finditer(c)]):
            out["kw"] += 1
    for ph in row_router.get("phrases") or []:
        p = ph.lower()
        if p.strip() and any_hit(lambda c: [m.start() for m in re.finditer(re.escape(p), c)]):
            out["phrase"] += 1
    for pp in row_router.get("path_patterns") or []:
        p = pp.lower()
        if p.strip() and any_hit(lambda c: [m.start() for m in re.finditer(re.escape(p), c)]):
            out["other"] += 1
    for ft in row_router.get("file_types") or []:
        rx = re.compile(r"\S" + re.escape(ft.lower()) + r"(?![a-z0-9])")
        if ft.strip() and any_hit(lambda c: [m.start() for m in rx.finditer(c)]):
            out["other"] += 1
    for pat in row_router.get("patterns") or []:
        try:
            rx = re.compile(pat)
        except re.error:
            continue
        if any_hit(lambda c: [m.start() for m in rx.finditer(c)]):
            out["other"] += 1
    return out


def _total(h):
    return h["kw"] + h["phrase"] + h["other"]


def _order_index(row, order):
    name = row.get("name", "")
    if name in order:
        return order.index(name)
    if (row.get("contributed_by") == "station" or name.startswith("station:")) and "station:*" in order:
        return order.index("station:*")
    if "conversational" in order:
        return order.index("conversational") - 0.5
    return len(order)


NEGATORS_DEFAULT = ("no", "never", "don't", "dont", "do not", "not", "without", "stop")
SKILL_ALSO_MIN_HITS = 2


def match_skills(prompt, rows, k=2, negators=NEGATORS_DEFAULT, window=3):
    """Top-k skill rows for a prompt (resolved through route_to); [] when nothing matches.
    Rank: whole-word keyword hits desc, then phrase hits desc, then canonical before variant, then file order."""
    return [t for _, t in scored_skills(prompt, rows, k, negators, window)]


def scored_skills(prompt, rows, k=2, negators=NEGATORS_DEFAULT, window=3):
    """match_skills with each result's score (keyword hits + phrase hits of the row that matched): [(score, row)]."""
    by_id = {r.get("id"): r for r in rows if r.get("id")}
    cls = clauses(prompt)
    scored = []
    for i, r in enumerate(rows):
        h = hits({"keywords": r.get("keywords") or [], "phrases": r.get("phrases") or []}, prompt, list(negators), window, cls)
        if not (h["kw"] or h["phrase"]):
            continue
        target, seen = r, set()
        while target.get("route_to") and target.get("route_to") in by_id and target["route_to"] not in seen:
            seen.add(target["route_to"])
            target = by_id[target["route_to"]]
        rank = KIND_RANK.get(str(r.get("kind", "canonical")), 1)
        scored.append((-h["kw"], -h["phrase"], rank, i, target))
    scored.sort(key=lambda x: x[:4])
    out, paths = [], set()
    for kh, ph, _, _, t in scored:
        key = t.get("path") or t.get("id")
        if key in paths:
            continue
        paths.add(key)
        out.append((-kh - ph, t))
        if len(out) >= k:
            break
    return out


def skill_line(r):
    return "SKILL: read %s (%s)" % (r.get("path") or r.get("id"), r.get("name") or r.get("id"))


def first_move_line(root, row):
    fm = (row.get("router") or {}).get("first_move") or {}
    name = row.get("name", "?")
    args = (" " + fm["args"]) if fm.get("args") else ""
    gather = fm.get("inline_gather", "")
    if fm.get("skill"):
        present = (Path(root) / ".claude" / "skills" / fm["skill"] / "SKILL.md").exists()
        line = "FIRST MOVE (%s): skill /%s%s [%s]" % (name, fm["skill"], args, "PRESENT" if present else "ABSENT")
    elif fm.get("workflow"):
        present = (Path(root) / ".claude" / "workflows" / (fm["workflow"] + ".js")).exists()
        line = "FIRST MOVE (%s): workflow %s%s [%s]" % (name, fm["workflow"], args, "PRESENT" if present else "ABSENT")
    else:
        return "FIRST MOVE (%s): run `%s`%s" % (name, gather or "(no gather named)", args)
    if gather:
        line += (" — fall back to: `%s`" if not present else " · gather: `%s`") % gather
    return line


def _station_of(row):
    n = row.get("name", "")
    return n.split(":", 1)[1] if n.startswith("station:") else (row.get("station") or n)


def route(prompt, root, payload=None):
    """The router's output lines (before plug-ins and truncation)."""
    table, local, hints, station = load_table(root)
    tie = table.get("router_tie_rule") or {}
    order = tie.get("order") or []
    cap = int(tie.get("multi_intent_cap", 3))
    negators = table.get("negators") or []
    window = int(table.get("neg_window", 3))
    low = prompt.lstrip().lower()
    if any(low.startswith(p.lower()) for p in table.get("harness_prefixes") or []):
        return None
    cls = clauses(prompt)
    matched = []
    for i, r in enumerate(local):
        h = hits(r.get("router") or {}, prompt, negators, window, cls)
        if _total(h):
            matched.append((r, h, i))
    lines = []
    if hints:
        best_local = max([h["kw"] for _, h, _ in matched] or [0])
        cand = []
        for r in hints:
            if _station_of(r) == station:
                continue
            h = hits(r.get("router") or {}, prompt, negators, window, cls)
            if h["kw"] >= best_local + 2:
                cand.append((h["kw"], r))
        if cand:
            cand.sort(key=lambda x: -x[0])
            x = _station_of(cand[0][1])
            lines.append("WRONG STATION? this looks like %s (git worktree add ../%s station/%s)" % (x, x, x))
    if len(matched) >= cap:
        names = ",".join(r.get("name", "?") for r, _, _ in matched)
        lines.append("ROUTER: %d intents matched (%s) — not routed; likely a pasted document" % (len(matched), names))
        return lines
    if matched:
        matched.sort(key=lambda m: (_order_index(m[0], order), -_total(m[1]), m[2]))
        win = matched[0][0]
        if win.get("name") == "conversational":
            return lines
        if win.get("scope") == "main" and not station:
            x = _station_of(win)
            fm = (win.get("router") or {}).get("first_move") or {}
            lines.append("STATION: %s — %s" % (x, fm.get("inline_gather") or "git worktree add ~/stations/%s station/%s" % (x, x)))
        else:
            lines.append(first_move_line(root, win))
            also = skill_also(prompt, root, table, win, lines, negators, window)
            if also:
                lines.append(also)
        return lines
    sk = Path(root) / "router" / "skills.json"
    if sk.exists():
        rows = _load(sk).get("skills", [])
        for r in match_skills(prompt, rows, 2, negators, window):
            lines.append(skill_line(r))
    return lines


def skill_also(prompt, root, table, win, lines, negators, window):
    """fix2-commons 6: the top skill match printed BESIDE a winning FIRST MOVE, or None.
    Printed only when its score clears skill_also_min_hits, it is not the first move's own skill, and the lines so far
    plus it fit max_out_bytes (the plug-ins after it keep the existing truncation rule)."""
    sk = Path(root) / "router" / "skills.json"
    if not sk.exists():
        return None
    top = scored_skills(prompt, _load(sk).get("skills", []), 1, negators, window)
    if not top:
        return None
    score, r = top[0]
    if score < int(table.get("skill_also_min_hits", SKILL_ALSO_MIN_HITS)):
        return None
    own = ((win.get("router") or {}).get("first_move") or {}).get("skill")
    if own and (r.get("path") or "").rstrip("/") in (".claude/skills/%s/SKILL.md" % own, ".claude/skills/%s" % own):
        return None
    line = skill_line(r)
    if len("\n".join(lines + [line]).encode("utf-8")) > int(table.get("max_out_bytes", 1200)):
        return None
    return line


def _plugins(prompt, payload, root):
    out = []
    try:
        spec = importlib.util.spec_from_file_location("ctx_threshold_for_router", str(HERE / "context_threshold.py"))
        if spec and (HERE / "context_threshold.py").exists():
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            t = m.line(payload, root)
            if t:
                out.append(t)
    except Exception as e:
        out.append("intent_router: context_threshold plug-in failed (%s)" % type(e).__name__)
    bp = Path(root) / "tools" / "brain.py"
    if bp.exists():
        try:
            spec = importlib.util.spec_from_file_location("brain_for_router", str(bp))
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            if hasattr(m, "surface"):
                t = m.surface(prompt)
                if t:
                    out.append(str(t).strip())
        except Exception as e:
            out.append("intent_router: brain.surface plug-in failed (%s)" % type(e).__name__)
    return out


def truncate(text, limit):
    b = text.encode("utf-8")
    if len(b) <= limit:
        return text
    marker_len = len(" …TRUNCATED 99999 B".encode("utf-8"))
    keep = b[: max(0, limit - marker_len)].decode("utf-8", "ignore")
    return keep + " …TRUNCATED %d B" % (len(b) - len(keep.encode("utf-8")))


def respond(payload, root):
    prompt = payload.get("prompt") or ""
    try:
        table = _load(Path(root) / "router" / "intents.json")
        limit = int(table.get("max_out_bytes", 1200))
    except Exception:
        limit = 1200
    try:
        lines = route(prompt, root, payload)
    except Exception as e:
        return "intent_router: could not classify (%s: %s)" % (type(e).__name__, str(e)[:120])
    if lines is None:
        return ""
    lines = lines + _plugins(prompt, payload, root)
    return truncate("\n".join(l for l in lines if l), limit)


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError as e:
        print("intent_router: could not classify (payload unreadable: %s)" % e)
        return 0
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    out = respond(payload, root)
    if out:
        print(out)
    return 0


# ---------------------------------------------------------------- selftest
FIXTURE_STATION_INTENTS = {"intents": [
    {"name": "edge", "description": "fixture", "contributed_by": "station",
     "router": {"keywords": ["backtest", "edge", "expectancy"], "phrases": ["walk forward"], "first_move": {"workflow": "edge-research"}}},
    {"name": "journal", "description": "fixture", "contributed_by": "station",
     "router": {"keywords": ["journal", "fills"], "phrases": ["trade log"], "first_move": {"workflow": "journal-review"}}},
]}
FIXTURE_KIT_TREE = {"intents": [
    {"name": "station:quarantine", "description": "fixture", "scope": "main", "contributed_by": "kit",
     "router": {"keywords": ["camofox", "maxun", "stealth", "fingerprinting"], "phrases": ["anti-bot"],
                "first_move": {"inline_gather": "git worktree add ~/stations/quarantine station/quarantine"}}},
    {"name": "station:markets", "description": "fixture", "scope": "main", "contributed_by": "kit",
     "router": {"keywords": ["backtest", "trade", "edge", "pine", "tradingview", "autohedge"], "phrases": [],
                "first_move": {"inline_gather": "git worktree add ~/stations/markets station/markets"}}},
    {"name": "station:client-bi", "description": "fixture", "scope": "main", "contributed_by": "kit",
     "router": {"keywords": ["qlik", "erp", "dashboard", "kpi", "client"], "phrases": ["load script"],
                "first_move": {"inline_gather": "git worktree add ~/stations/client-bi station/client-bi"}}},
]}
FIXTURE_SKILLS = {"skills": [
    {"id": "s1", "name": "market-sizing", "kind": "canonical", "path": "repertoire/a/market-sizing/SKILL.md",
     "keywords": ["tam", "sam", "market"], "phrases": ["market size"], "route_to": None, "home": "research", "depth": "frontmatter"},
    {"id": "s2", "name": "market-sizing", "kind": "variant", "path": "repertoire/b/market-sizing/SKILL.md",
     "keywords": ["tam", "sam", "market"], "phrases": [], "route_to": None, "home": "research", "depth": "frontmatter"},
    {"id": "s3", "name": "market-sizing", "kind": "mirror", "path": None,
     "keywords": ["sizing"], "phrases": [], "route_to": "s1", "home": "research", "depth": "frontmatter"},
    {"id": "s4", "name": "mermaid", "kind": "canonical", "path": "repertoire/c/mermaid/SKILL.md",
     "keywords": ["mermaid", "diagram", "flowchart"], "phrases": [], "route_to": None, "home": "research", "depth": "body"},
]}

# (prompt, expected first-line prefix or None for no output, label) -- keywords above and in router/intents.json
# were frozen before these prompts were written.
COMMONS_CASES = [
    ("<task-notification>build a new tool now</task-notification>", None, "harness turn"),
    ("Another Claude session sent a message: please build the thing", None, "harness turn (peer)"),
    ("<wake reason=\"external-event\"> CI failed", None, "harness turn (wake)"),
    ("[Workflow harness — user request] build x", None, "harness turn (workflow)"),
    ("no idea why the build fails", "FIRST MOVE (build)", "negator outside window 3"),
    ("don't build anything yet", None, "negated build"),
    ("please do not create a new tool", None, "negated phrase and keyword"),
    ("build a parser for the csv exports", "FIRST MOVE (build)", "build keyword"),
    ("can you scaffold a new skill for invoices", "FIRST MOVE (build)", "build phrase"),
    ("who owns the denominator rule?", "FIRST MOVE (governance-admin)", "owner question"),
    ("supersede DEC-core-0004 with a new decision", "FIRST MOVE (governance-admin)", "supersede"),
    ("open governance/LEDGER.md and add a row", "FIRST MOVE (governance-admin)", "path pattern"),
    ("let's wrap up for today", "FIRST MOVE (closeout)", "closeout phrase"),
    ("what next?", "FIRST MOVE (closeout)", "what next"),
    ("fan out three subagents over the stations", "FIRST MOVE (delegate)", "delegate"),
    ("run these in parallel please", "FIRST MOVE (delegate)", "parallel"),
    ("build it in parallel with subagents", "FIRST MOVE (build)", "tie build vs delegate resolved by order"),
    ("change the rule and build a check for it", "FIRST MOVE (governance-admin)", "tie governance-admin vs build"),
    ("thanks, that looks good", None, "conversational"),
    ("hello", None, "greeting"),
    ("Never touch governance/x.", None, "prohibition is not a request (path)"),
    ("never build on main", None, "prohibition is not a request (keyword)"),
    ("rule, build, closeout, delegate: a pasted spec", "ROUTER: 4 intents matched", "pasted document"),
    ("fix the ledger rule; build the tool; fan out workers", "ROUTER: 3 intents matched", "3-intent paste"),
    ("write a workflow file .claude/workflows/x.js", "FIRST MOVE (delegate)", "path + file type"),
    ("x " * 900 + "build", "FIRST MOVE (build)", "long prompt still <= 1200 B"),
]
MAIN_CASES = [
    ("I want to backtest a new edge on ES", "STATION: markets", "kit leaf on main"),
    ("study camofox fingerprinting", "STATION: quarantine", "Q0 first"),
    ("fix the qlik load script for the client", "STATION: client-bi", "client leaf"),
    ("never open camofox", None, "negated leaf"),
]
STATION_CASES = [
    ("run a backtest on the edge", "FIRST MOVE (edge)", "station intent beats commons"),
    ("build a backtest harness", "FIRST MOVE (edge)", "station:* heads the tie order"),
    ("update the trade log journal", "FIRST MOVE (journal)", "second station intent"),
    ("study camofox stealth fingerprinting for anti-bot", "WRONG STATION? this looks like quarantine", "wrong-station hint"),
    ("the client erp kpi dashboard in qlik", "WRONG STATION? this looks like client-bi", "wrong-station hint 2"),
    ("estimate the tam for this market", "SKILL: read repertoire/a/market-sizing/SKILL.md", "skill fall-through, canonical first"),
    ("draw a mermaid flowchart", "SKILL: read repertoire/c/mermaid/SKILL.md", "skill fall-through"),
    ("sizing please", "SKILL: read repertoire/a/market-sizing/SKILL.md", "mirror resolves via route_to"),
    ("no mermaid please", None, "negated skill"),
    ("edge", "FIRST MOVE (edge): workflow edge-research [ABSENT]", "ABSENT target"),
]
# fix2-commons 6 (ROUTER SHADOWING): (prompt, exact expected output lines, label) on the fixture station
SHADOW_CASES = [
    ("backtest the tam market sizing edge", ["FIRST MOVE (edge): workflow edge-research [ABSENT]",
                                            "SKILL: read repertoire/a/market-sizing/SKILL.md (market-sizing)"],
     "intent wins AND the top skill clears the threshold: both lines, FIRST MOVE first"),
    ("backtest a mermaid edge", ["FIRST MOVE (edge): workflow edge-research [ABSENT]"],
     "intent wins, top skill scores 1 (< skill_also_min_hits 2): no SKILL line"),
    ("run a backtest on the edge", ["FIRST MOVE (edge): workflow edge-research [ABSENT]"],
     "intent wins, no skill hit: no SKILL line"),
    ("backtest the edge, no tam no market", ["FIRST MOVE (edge): workflow edge-research [ABSENT]"],
     "negated skill keywords never co-route"),
    ("update the journal fills for the mermaid flowchart diagram", ["FIRST MOVE (journal): workflow journal-review [ABSENT]",
                                                                    "SKILL: read repertoire/c/mermaid/SKILL.md (mermaid)"],
     "second intent + a 3-hit skill"),
]


def _load_cases(p):
    """Tolerant reader for station selftest files: list | {cases|prompts: [...]} | {prompt: expect}."""
    d = _load(p)
    if isinstance(d, dict) and not any(k in d for k in ("cases", "prompts", "tests")):
        items = [{"prompt": k, "expect": v} for k, v in d.items() if not k.startswith("_")]
    else:
        items = d if isinstance(d, list) else (d.get("cases") or d.get("prompts") or d.get("tests") or [])
    out = []
    for it in items:
        if isinstance(it, list) and len(it) >= 2:
            it = {"prompt": it[0], "expect": it[1]}
        if not isinstance(it, dict) or "prompt" not in it:
            raise ValueError("%s: a case without 'prompt'" % p)
        exp = None
        for key in ("expect", "intent", "expected", "route", "skill", "id", "path", "name", "routes_to"):
            if key in it:
                exp = it[key]
                break
        if it.get("must_route") is False or it.get("negative") is True:
            exp = None
        if isinstance(exp, str) and exp.lower() in ("", "none", "null", "nothing"):
            exp = None
        out.append((it["prompt"], exp))
    return out


def skills_case_failures(rows, cases):
    """router/skills.selftest.json cases through match_skills -> failure messages. A variant/mirror expectation is met
    by its canonical (match_skills resolves route_to): the SAME equivalence tools/upstream/skill_routes.py
    selftest-routes applies, so the two validators of one file agree (fix2-commons 6)."""
    by = {r.get("id"): r for r in rows if r.get("id") and not r.get("copy_of")}

    def canon(i):
        seen = set()
        while by.get(i, {}).get("route_to") and i not in seen:
            seen.add(i)
            i = by[i]["route_to"]
        return i
    fails = []
    for prompt, exp in cases:
        got = match_skills(prompt, rows, 2)
        if exp is None:
            if got:
                fails.append("skills %r: want nothing, got %r" % (prompt, [g.get("id") for g in got]))
            continue
        exps = exp if isinstance(exp, list) else [exp]
        keys = {str(v) for g in got for v in (g.get("id"), g.get("name"), g.get("path")) if v}
        gc = {canon(g.get("id")) for g in got if g.get("id")}
        if not any(str(e) in keys or canon(e) in gc for e in exps):
            fails.append("skills %r: want %r in top-2, got %r" % (prompt, exp, sorted(keys)))
    return fails


def selftest(root=None):
    import shutil
    import tempfile
    fails, n = [], 0

    def ok(c, m):
        nonlocal n
        n += 1
        if not c:
            fails.append(m)

    def check(rt, cases):
        for prompt, want, label in cases:
            out = respond({"prompt": prompt, "session_id": "selftest"}, rt)
            ok(len(out.encode("utf-8")) <= 1200, "%s: output %d B > 1200" % (label, len(out.encode())))
            if want is None:
                ok(out == "", "%s: want nothing, got %r" % (label, out[:200]))
            else:
                ok(out.startswith(want), "%s: want %r, got %r" % (label, want, out[:200]))

    src = HERE.parent.parent
    with tempfile.TemporaryDirectory() as td:
        rt = Path(td)
        (rt / ".claude" / "hooks").mkdir(parents=True)
        (rt / "router").mkdir()
        shutil.copyfile(src / "router" / "intents.json", rt / "router" / "intents.json")
        for s in ("summon", "closeout"):
            (rt / ".claude" / "skills" / s).mkdir(parents=True)
            (rt / ".claude" / "skills" / s / "SKILL.md").write_text("---\nname: %s\n---\n" % s)
        # 1. commons table on main, no kit tree
        check(rt, COMMONS_CASES)
        # truncation marker
        big = respond({"prompt": "build"}, rt)
        ok(big.startswith("FIRST MOVE (build): skill /summon") and "[PRESENT]" in big, "PRESENT target: %r" % big)
        ok(truncate("y" * 2000, 1200).endswith("B") and "TRUNCATED" in truncate("y" * 2000, 1200)
           and len(truncate("y" * 2000, 1200).encode()) <= 1200, "TRUNCATED marker within the cap")
        # 2. main with the kit tree
        (rt / "router" / "kit_tree.json").write_text(json.dumps(FIXTURE_KIT_TREE))
        check(rt, MAIN_CASES)
        # 3. a station: fragments, scope:main hints, skills fall-through
        (rt / "station.json").write_text(json.dumps({"name": "markets"}))
        (rt / "router" / "intents.d").mkdir()
        (rt / "router" / "intents.d" / "station.json").write_text(json.dumps(FIXTURE_STATION_INTENTS))
        (rt / "router" / "skills.json").write_text(json.dumps(FIXTURE_SKILLS))
        check(rt, STATION_CASES)
        ok(respond({"prompt": "backtest the trade edge on tradingview pine"}, rt).startswith("FIRST MOVE (edge)"),
           "own station's kit leaf never hints WRONG STATION")
        # fix2-commons 6: FIRST MOVE + co-routed SKILL line (exact lines; plug-ins print nothing in this fixture)
        for prompt, want, label in SHADOW_CASES:
            got = (route(prompt, rt) or [])
            ok(got == want, "%s: want %r, got %r" % (label, want, got))
            ok(len(respond({"prompt": prompt}, rt).encode("utf-8")) <= 1200, "%s: over budget" % label)
        tbl = json.loads((rt / "router" / "intents.json").read_text())
        (rt / "router" / "intents.json").write_text(json.dumps(dict(tbl, skill_also_min_hits=1)))
        ok(route("backtest a mermaid edge", rt) == ["FIRST MOVE (edge): workflow edge-research [ABSENT]",
                                                    "SKILL: read repertoire/c/mermaid/SKILL.md (mermaid)"],
           "skill_also_min_hits is read from router/intents.json")
        (rt / "router" / "intents.json").write_text(json.dumps(dict(tbl, max_out_bytes=200)))
        tight = route("backtest the tam market sizing edge", rt)
        ok(tight == ["FIRST MOVE (edge): workflow edge-research [ABSENT]"] or
           len("\n".join(tight).encode("utf-8")) <= 200, "co-routed SKILL line respects max_out_bytes: %r" % tight)
        own = dict(FIXTURE_SKILLS, skills=FIXTURE_SKILLS["skills"] + [
            {"id": "s5", "name": "edge-research", "kind": "canonical", "path": ".claude/skills/edge-research/SKILL.md",
             "keywords": ["backtest", "edge", "sharpe"], "phrases": [], "route_to": None}])
        (rt / "router" / "intents.json").write_text(json.dumps(tbl))
        (rt / "router" / "skills.json").write_text(json.dumps(own))
        st_own = json.loads((rt / "router" / "intents.d" / "station.json").read_text())
        st_own["intents"][0]["router"]["first_move"] = {"skill": "edge-research"}
        (rt / "router" / "intents.d" / "station.json").write_text(json.dumps(st_own))
        ok(route("backtest the edge sharpe", rt) == ["FIRST MOVE (edge): skill /edge-research [ABSENT]"],
           "the first move's own skill is never repeated as a SKILL line: %r" % route("backtest the edge sharpe", rt))
        (rt / "router" / "intents.d" / "station.json").write_text(json.dumps(FIXTURE_STATION_INTENTS))
        (rt / "router" / "skills.json").write_text(json.dumps(FIXTURE_SKILLS))
        ok(skills_case_failures(FIXTURE_SKILLS["skills"], [("sizing please", "s3"), ("estimate the tam", "s1"), ("hello", None)]) == [],
           "a mirror expectation is met by its canonical: %r" % skills_case_failures(FIXTURE_SKILLS["skills"], [("sizing please", "s3")]))
        ok(len(skills_case_failures(FIXTURE_SKILLS["skills"], [("draw a mermaid", "s1"), ("draw a mermaid", None)])) == 2,
           "a wrong expectation and a routed negative both fail")
        ok([s for s, _ in scored_skills("the market size and tam", FIXTURE_SKILLS["skills"], k=2)] == [3, 2],
           "scored_skills scores = keyword + phrase hits: %r" % scored_skills("the market size and tam", FIXTURE_SKILLS["skills"], k=2))
        # match_skills contract (commons-upstream imports it)
        r = match_skills("market sizing for tam", FIXTURE_SKILLS["skills"], k=2)
        ok([x["id"] for x in r] == ["s1", "s2"], "match_skills top-2 canonical then variant: %r" % [x["id"] for x in r])
        ok(match_skills("nothing relevant", FIXTURE_SKILLS["skills"]) == [], "match_skills empty")
        # broken table -> one 'could not classify' line, exit 0
        (rt / "router" / "intents.json").write_text("{broken")
        out = respond({"prompt": "build"}, rt)
        ok(out.startswith("intent_router: could not classify"), "unreadable table: %r" % out)
    # 4. the real station's own selftest files, if present
    root = Path(root) if root else src
    files = sorted((root / "router" / "intents.d").glob("*.selftest.json")) if (root / "router" / "intents.d").is_dir() else []
    for f in files:
        try:
            cases = _load_cases(f)
        except Exception as e:
            ok(False, "%s unreadable: %s" % (f.name, e))
            continue
        for prompt, exp in cases:
            out = respond({"prompt": prompt, "session_id": "selftest"}, root)
            first = out.splitlines()[0] if out else ""
            if exp is None:
                ok(not first.startswith("FIRST MOVE") and not first.startswith("STATION:"), "%s %r: want no route, got %r" % (f.name, prompt, first))
            else:
                ok(("(%s)" % exp) in first or (": %s " % exp) in first or first.startswith(str(exp)),
                   "%s %r: want %r, got %r" % (f.name, prompt, exp, first))
    sk_t = root / "router" / "skills.selftest.json"
    if sk_t.exists() and (root / "router" / "skills.json").exists():
        rows = _load(root / "router" / "skills.json").get("skills", [])
        try:
            cases = _load_cases(sk_t)
        except Exception as e:
            cases = []
            ok(False, "skills.selftest.json unreadable: %s" % e)
        sfails = skills_case_failures(rows, cases)
        for m in sfails:
            ok(False, m)
        n += len(cases) - len(sfails)  # passing cases count too (ok() counted the failures)
    total = len(COMMONS_CASES) + len(MAIN_CASES) + len(STATION_CASES) + len(SHADOW_CASES)
    if total < 30:
        ok(False, "fewer than 30 fixture prompts (%d)" % total)
    if fails:
        print("selftest FAILED (%d of %d cases)" % (len(fails), n))
        for f in fails:
            print(" - " + f)
        return 1
    print("selftest OK (%d cases, %d fixture prompts)" % (n, total))
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        r = None
        if "--root" in sys.argv:
            r = sys.argv[sys.argv.index("--root") + 1]
        sys.exit(selftest(r))
    sys.exit(main())
