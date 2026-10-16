#!/usr/bin/env python3
"""deny_upstream_write.py — PreToolUse (Bash|Edit|Write|MultiEdit|NotebookEdit) DENY: lanes and live surfaces are read-only.

Earned by: LEAN LL-08 (lettuce `vendor/README.md`: "Do not edit these files"; upstream kept verbatim so PROVENANCE
re-hashes and a repin diff is honest) and LL-18 (lettuce `deny_bridge_write.py`: "a bridge file edited under a running
process costs a POSITION ... the damage happens outside the repository"). CA-09 merged: one hook for both lists.

Denies (exit 2, one stderr line):
  * Edit/Write/MultiEdit/NotebookEdit, and Bash writes (redirect `>`/`>>`, `tee`, `sed -i`, `cp`/`mv`/`ln`/`install`
    destination, `mv`/`rm`/`truncate` operands, `git checkout -- <p>`, `git restore <p>`), into a held upstream tree
    `<lane>/<owner~repo>/` for lane in repertoire/ upstream/ study/ nc-lane/ (or station.json gov.upstream_dirs) —
    except files under that tree's `_PATCHES/` whose first line is `NOT APPLIED`;
  * a hand write of the GENERATED `repertoire/INDEX.md` (only `tools/upstream/skill_routes.py index` writes it) and of
    the ingest-owned registries `upstream/{LOCK,PROVENANCE,RENAMES}.json` (only `tools/upstream/ingest.py` writes them);
  * a write matching a station.json `live_surfaces` glob, except `<surface>/patches/` files whose first line is
    `NOT APPLIED`.
Allowed: every read; lane-root station-authored files (e.g. `study/AUTOHEDGE_STARTUP_NOTE.md`, `upstream/PRECEDENCE.json`
whose paraphrase is hand-filled, `<lane>/notes/`).
Release: write the change as `<lane>/<owner~repo>/_PATCHES/<name>` (or `<surface>/patches/<name>`) with first line
`NOT APPLIED`; or a governance/RELEASES.json row (scope `deny_upstream_write`, `match` = the path prefix, the
operator's verbatim `words` + `locator`) read from main by `_release.covers`.
Not hookable: a write made from inside an interpreter (`python3 -c "open(p,'w')"`) carries no path the harness shows;
the `provenance` check (re-hash) is the backstop.
Fails OPEN on unreadable input (a broken hook must not wedge the session).
"""
import fnmatch
import json
import os
import re
import shlex
import sys
from pathlib import Path

LANES_DEFAULT = ("repertoire", "upstream", "study", "nc-lane")
PATCH_DIR = "_PATCHES"
NOT_APPLIED = "NOT APPLIED"
INGEST_OWNED = {"upstream/LOCK.json", "upstream/PROVENANCE.json", "upstream/RENAMES.json"}
GENERATED = {"repertoire/INDEX.md"}
TOOL_PATH_KEYS = ("file_path", "notebook_path", "path")


# ---------------------------------------------------------------- station + release
def root_of(payload):
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve()


def load_station(root):
    try:
        return json.loads((root / "station.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def lanes(station):
    dirs = ((station.get("gov") or {}).get("upstream_dirs")) or station.get("upstream_dirs")
    if dirs:
        return tuple(d.strip("/") for d in dirs)
    return LANES_DEFAULT


def released(root, scope, text):
    """True when a committed RELEASES.json row covers (scope, text). Uses commons _release.covers when present."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import _release  # noqa: WPS433 (commons-gov's reader: reads main's copy so a session cannot grant itself)
        return bool(_release.covers(scope, text, root=root))
    except Exception:
        pass
    try:
        rows = json.loads((root / "governance" / "RELEASES.json").read_text(encoding="utf-8")).get("releases", [])
    except (OSError, ValueError):
        return False
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M")
    for r in rows:
        if not (r.get("words") and r.get("locator")):
            continue
        if r.get("expires") and str(r["expires"])[:16] < now:
            continue
        sc = r.get("scope", "")
        if sc == scope or (sc == scope.split(":", 1)[0] and r.get("match") and r["match"] in text):
            return True
    return False


# ---------------------------------------------------------------- bash write scanner
SEG_SPLIT = re.compile(r"\|\||&&|;|\||\n|&(?!>)")


def segments(cmd):
    out = []
    for seg in SEG_SPLIT.split(cmd or ""):
        seg = seg.strip()
        if not seg:
            continue
        try:
            toks = shlex.split(seg, posix=True)
        except ValueError:
            toks = seg.split()
        out.append(toks)
    return out


def written_paths(cmd):
    """[(path, op)] for every path a Bash command would write, move, delete or overwrite."""
    out = []
    for m in re.finditer(r"(?<![<&0-9])(\d?>>?|&>>?)\s*(?!&)([^\s;|&<>]+)", cmd or ""):
        out.append((m.group(2).strip("'\""), "append" if m.group(1).endswith(">>") else "redirect"))
    for toks in segments(cmd):
        toks = [t for t in toks if not re.fullmatch(r"\d?>>?.*|&>.*|<.*", t)]
        while toks and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", toks[0]):
            toks = toks[1:]
        if toks and toks[0] in ("sudo", "env", "command", "nohup", "time"):
            toks = toks[1:]
        if not toks:
            continue
        c, args = os.path.basename(toks[0]), toks[1:]
        ops = [a for a in args if not a.startswith("-")]
        if c == "tee":
            out += [(a, "tee") for a in ops]
        elif c in ("sed", "perl") and any(a == "-i" or a.startswith("-i") or a.startswith("--in-place") for a in args):
            out += [(a, "sed -i") for a in ops[1:]] if c == "sed" else [(a, "perl -i") for a in ops[1:]]
        elif c in ("cp", "ln", "install", "rsync") and len(ops) >= 2:
            out.append((ops[-1], c))
        elif c == "mv" and ops:
            out += [(a, "mv") for a in ops]
        elif c in ("rm", "rmdir", "truncate", "shred", "unlink", "touch", "chmod", "chown") and ops:
            out += [(a, c) for a in (ops[1:] if c in ("chmod", "chown") else ops)]
        elif c == "git" and args:
            sub = [a for a in args if not a.startswith("-")]
            if sub[:1] == ["checkout"] and "--" in args:
                out += [(a, "git checkout --") for a in args[args.index("--") + 1:]]
            elif sub[:1] == ["restore"]:
                out += [(a, "git restore") for a in sub[1:]]
            elif sub[:1] in (["rm"], ["mv"]):
                out += [(a, "git " + sub[0]) for a in sub[1:]]
    return out


# ---------------------------------------------------------------- decision
def rel(root, p, cwd=None):
    try:
        base = Path(cwd) if cwd else root
        q = Path(p) if os.path.isabs(p) else base / p
        r = os.path.relpath(os.path.normpath(str(q)), str(root)).replace("\\", "/")
        return None if r.startswith("../") or r == ".." else r
    except (ValueError, TypeError):
        return None


def first_line(text):
    return (text or "").lstrip("﻿").split("\n", 1)[0].strip()


def file_first_line(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return first_line(f.readline())
    except OSError:
        return ""


def held_tree(r, lane_names):
    parts = r.split("/")
    if len(parts) >= 3 and parts[0] in lane_names and "~" in parts[1]:
        return parts[0] + "/" + parts[1] + "/"
    return None


def verdict(root, station, r, op, content=None):
    """None (allow) or the stderr reason for a write to repo-relative path r."""
    lane_names = lanes(station)
    if r in GENERATED:
        return "DENY-UPSTREAM-WRITE: %s is GENERATED — release: python3 tools/upstream/skill_routes.py index --station-root ." % r
    if r in INGEST_OWNED:
        return ("DENY-UPSTREAM-WRITE: %s is written only by tools/upstream/ingest.py — release: re-run ingest.py at the pin "
                "(or a RELEASES.json row scope deny_upstream_write)" % r)
    destructive = op in ("rm", "mv", "rmdir", "shred", "unlink", "truncate", "git rm", "git mv")
    if destructive and (r.rstrip("/") in lane_names or held_tree(r.rstrip("/") + "/x", lane_names)):
        return ("DENY-UPSTREAM-WRITE: %s %s would remove a lane or a whole held tree — release: a RELEASES.json row scope "
                "deny_upstream_write quoting the operator (re-ingest is the normal path)" % (op, r))
    tree = held_tree(r, lane_names)
    if tree:
        if ("/%s/" % PATCH_DIR) in ("/" + r) and op not in ("rm", "mv", "rmdir", "shred", "unlink", "git rm", "git mv"):
            fl = first_line(content) if content is not None else file_first_line(root / r)
            if fl == NOT_APPLIED:
                return None
            return ("DENY-UPSTREAM-WRITE: %s is a patch whose first line is not '%s' — release: make line 1 exactly %s"
                    % (r, NOT_APPLIED, NOT_APPLIED))
        return ("DENY-UPSTREAM-WRITE: %s (%s) is inside held upstream tree %s (read-only, PROVENANCE re-hashes it) — release: "
                "write %s%s/<name> with first line %s, or a RELEASES.json row scope deny_upstream_write quoting the operator"
                % (r, op, tree, tree, PATCH_DIR, NOT_APPLIED))
    for g in station.get("live_surfaces") or []:
        g = g.rstrip("/")
        base = g.rstrip("*").rstrip("/")
        if fnmatch.fnmatch(r, g) or fnmatch.fnmatch(r, g + "/*") or r == base or r.startswith(base + "/"):
            if r.startswith(base + "/patches/") and op not in ("rm", "mv"):
                fl = first_line(content) if content is not None else file_first_line(root / r)
                if fl == NOT_APPLIED:
                    return None
                return "DENY-LIVE-WRITE: %s patch must start with '%s' — release: make line 1 exactly %s" % (r, NOT_APPLIED, NOT_APPLIED)
            return ("DENY-LIVE-WRITE: %s matches live surface %s (a running process reads it) — release: write %s/patches/<name> "
                    "with first line %s, applied in a later sweep under the operator's per-session authorisation" % (r, g, base, NOT_APPLIED))
    return None


def decide(payload, root=None, station=None):
    root = root or root_of(payload)
    station = load_station(root) if station is None else station
    tool = payload.get("tool_name", "")
    ti = payload.get("tool_input") or {}
    targets = []
    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        p = next((ti.get(k) for k in TOOL_PATH_KEYS if ti.get(k)), None)
        if p:
            content = ti.get("content") if tool == "Write" else None
            if tool in ("Edit", "MultiEdit"):
                edits = ti.get("edits") or [{"old_string": ti.get("old_string", ""), "new_string": ti.get("new_string", "")}]
                for e in edits:
                    if NOT_APPLIED in (e.get("old_string") or "") and NOT_APPLIED not in (e.get("new_string") or ""):
                        content = "edited first line"
            targets.append((p, tool.lower(), content))
    elif tool == "Bash":
        cmd = ti.get("command", "")
        if re.search(r"tools/upstream/(skill_routes\.py\s+index|ingest\.py)\b", cmd) and not written_paths(cmd):
            return None
        targets = [(p, op, None) for p, op in written_paths(cmd)]
    for p, op, content in targets:
        r = rel(root, p, payload.get("cwd"))
        if r is None:
            continue
        reason = verdict(root, station, r, op, content)
        if reason and not released(root, "deny_upstream_write:" + r, r):
            return reason
    return None


# ---------------------------------------------------------------- selftest
def _commit_releases(root, rows):
    """Selftest helper: commit governance/RELEASES.json on a `main` branch, as _release.covers reads it from there."""
    import subprocess
    (Path(root) / "governance").mkdir(exist_ok=True)
    (Path(root) / "governance/RELEASES.json").write_text(json.dumps({"releases": rows}))
    g = ["git", "-C", str(root), "-c", "user.name=kit", "-c", "user.email=kit@localhost"]
    subprocess.run(["git", "-C", str(root), "init", "-q", "-b", "main"], check=True)
    subprocess.run(g + ["add", "--", "governance/RELEASES.json"], check=True)
    subprocess.run(g + ["commit", "-qm", "releases"], check=True)


def selftest():
    import tempfile
    cases = 0
    with tempfile.TemporaryDirectory() as t:
        root = Path(t)
        (root / "upstream/a~b/_PATCHES").mkdir(parents=True)
        (root / "upstream/a~b/x.py").write_text("x\n")
        (root / "upstream/a~b/_PATCHES/old.md").write_text("NOT APPLIED\nold patch\n")
        (root / "upstream/a~b/_PATCHES/bad.md").write_text("applied?\n")
        (root / "bridge/patches").mkdir(parents=True)
        st = {"name": "fx", "live_surfaces": ["bridge/"]}
        (root / "station.json").write_text(json.dumps(st))

        def d(tool, **ti):
            return decide({"tool_name": tool, "tool_input": ti, "cwd": str(root)}, root=root)

        expect = [
            (d("Write", file_path=str(root / "upstream/a~b/x.py"), content="y"), True, "Write into a held tree"),
            (d("Write", file_path="upstream/a~b/_PATCHES/p.md", content="NOT APPLIED\nfix\n"), False, "patch with NOT APPLIED"),
            (d("Write", file_path="upstream/a~b/_PATCHES/p.md", content="fix\n"), True, "patch without NOT APPLIED"),
            (d("Bash", command="echo hi > upstream/a~b/x"), True, "redirect"),
            (d("Bash", command="cat upstream/a~b/x"), False, "read"),
            (d("Bash", command="sed -i s/a/b/ upstream/a~b/x"), True, "sed -i"),
            (d("Bash", command="grep -r foo upstream/ | head"), False, "read pipeline"),
            (d("Bash", command="cp /tmp/z repertoire/o~r/skills/s/SKILL.md"), True, "cp destination"),
            (d("Bash", command="rm -rf study/T~A"), True, "rm of a whole held tree"),
            (d("Bash", command="rm -rf upstream"), True, "rm of a lane"),
            (d("Bash", command="rm -rf study/notes/old.md"), False, "rm of a lane-root station note"),
            (d("Bash", command="rm -rf study/T~A/main.py"), True, "rm inside a held tree"),
            (d("Bash", command="cd x && git checkout -- upstream/a~b/x.py"), True, "git checkout --"),
            (d("Bash", command="echo more >> upstream/a~b/_PATCHES/old.md"), False, "append to a NOT APPLIED patch"),
            (d("Bash", command="echo more >> upstream/a~b/_PATCHES/bad.md"), True, "append to a patch lacking the line"),
            (d("Edit", file_path="upstream/a~b/_PATCHES/old.md", old_string="NOT APPLIED", new_string="APPLIED"), True, "edit removing NOT APPLIED"),
            (d("Write", file_path="repertoire/INDEX.md", content="x"), True, "generated INDEX.md"),
            (d("Bash", command="python3 tools/upstream/skill_routes.py index --station-root ."), False, "the INDEX writer"),
            (d("Write", file_path="upstream/PROVENANCE.json", content="{}"), True, "ingest-owned registry"),
            (d("Edit", file_path="upstream/PRECEDENCE.json", old_string="TODO paraphrase", new_string="uses pnpm"), False, "paraphrase fill"),
            (d("Write", file_path="study/AUTOHEDGE_STARTUP_NOTE.md", content="# note"), False, "lane-root station file"),
            (d("Write", file_path="bridge/live.mq5", content="x"), True, "live surface"),
            (d("Write", file_path="bridge/patches/p.md", content="NOT APPLIED\nx"), False, "live surface patch"),
            (d("Bash", command="tee -a upstream/a~b/log.txt < /dev/null"), True, "tee"),
            (d("Read", file_path="upstream/a~b/x.py"), False, "Read tool"),
            (d("Write", file_path="tools/mine.py", content="x"), False, "station file"),
        ]
        for got, want, label in expect:
            assert bool(got) == want, "%s: got %r" % (label, got)
            cases += 1
        # release row (fallback reader, working tree)
        _commit_releases(root, [
            {"id": "REL-0001", "scope": "deny_upstream_write", "match": "upstream/a~b/x.py", "words": "yes edit it",
             "locator": "fixture", "utc": "2026-10-16T00:00Z", "expires": "2999-01-01T00:00Z"}])
        assert d("Write", file_path="upstream/a~b/x.py", content="y") is None, "a committed release row on main allows"
        assert d("Write", file_path="upstream/a~b/y.py", content="y"), "the release covers only its match"
        cases += 2
        # hook protocol: exit 2 + stderr on deny, 0 otherwise
        import subprocess
        p = subprocess.run([sys.executable, __file__], input=json.dumps({"tool_name": "Write", "tool_input": {"file_path": "upstream/q~r/a", "content": "x"},
                                                                         "cwd": str(root)}), capture_output=True, text=True,
                           env=dict(os.environ, CLAUDE_PROJECT_DIR=str(root)))
        assert p.returncode == 2 and "DENY-UPSTREAM-WRITE" in p.stderr and "release" in p.stderr, (p.returncode, p.stderr)
        p = subprocess.run([sys.executable, __file__], input="not json", capture_output=True, text=True)
        assert p.returncode == 0, "fails open"
        cases += 2
    print("deny_upstream_write selftest OK (%d cases)" % cases)
    return 0


def main():
    if "--selftest" in sys.argv[1:]:
        return selftest()
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    try:
        reason = decide(payload)
    except Exception as e:  # fail open, but say so
        print("deny_upstream_write: internal error %s (failing open)" % e, file=sys.stderr)
        return 0
    if reason:
        print(reason, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
