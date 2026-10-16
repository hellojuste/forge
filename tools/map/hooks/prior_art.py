#!/usr/bin/env python3
"""prior_art.py — PreToolUse(Write): at the moment a NEW tool/skill/workflow is born, point at what already exists.

Earned by: lettuce `docs/catalog/LIB_OVERLAP.md` (2026-07-31: the "check whether it exists" rule was run before one
build and not before the next, and a parallel Rung/Ladder type was built beside the existing Tranche) and
`tools/hooks/remind_prior_art.py` (E46: "the rule sits in a file the session read hours before" — so the reminder
moves to the Write that creates the file). The brain plugs in: when the brain knob is medium+, `tools/brain.py`
`prior_art()` RUNS the retrieval and its top hits ride in the same message (one process, one message).
Fires when tool_input.file_path does not exist, matches map/dirs.json "prior_art_globs", and is not under a held
lane (that upstream's own conventions govern its files). Once per session per kind (state in .usage/, gitignored).
Knob: map S+ (XS prints nothing). Channel: PreToolUse JSON hookSpecificOutput.additionalContext. Never blocks;
exit 0 always; any exception fails open silently.
"""
import importlib.util
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _common as C  # noqa: E402

DEFAULT_GLOBS = ["tools/**/*.py", ".claude/skills/*/SKILL.md", ".claude/workflows/*"]


def kind_of(rel):
    if rel.endswith("/SKILL.md"):
        return "skill"
    if rel.startswith(".claude/workflows/"):
        return "workflow"
    return "tool"


def brain_hits(payload, root):
    p = Path(root) / "tools" / "brain.py"
    if not p.exists():
        return None
    spec = importlib.util.spec_from_file_location("_brain_for_prior_art", str(p))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.prior_art(payload, mod.Ctx(root))


def message(payload, root):
    if not C.map_at_least(root, "S"):
        return None
    fp = (payload.get("tool_input") or {}).get("file_path") or ""
    if not fp:
        return None
    ap = Path(fp) if Path(fp).is_absolute() else Path(root) / fp
    try:
        rel = ap.resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return None
    try:
        globs = C.load_map(root, "dirs", required=False).get("prior_art_globs") or DEFAULT_GLOBS
    except C.Unreadable:
        globs = DEFAULT_GLOBS
    if ap.exists() or C.classify(rel, C.domain_cfg(root)) != "domain" or not C.any_glob(rel, globs):
        return None
    kind = kind_of(rel)
    sid = re.sub(r"[^\w-]", "_", str(payload.get("session_id") or "nosession"))
    state = Path(root) / ".usage" / ("prior_art.%s" % sid)
    seen = set(state.read_text().split()) if state.exists() else set()
    parts = []
    if kind not in seen:
        words = " ".join(w for w in re.split(r"[_\-./]", Path(rel).stem if kind == "tool" else Path(rel).parent.name) if len(w) >= 3) or rel
        parts.append("PRIOR ART: new %s %s. Run python3 tools/map/find.py %s and read map/SOLUTIONS.md first." % (kind, rel, words))
        try:
            state.parent.mkdir(parents=True, exist_ok=True)
            state.write_text(" ".join(sorted(seen | {kind})))
        except OSError:
            pass
    try:
        b = brain_hits(payload, root)
    except Exception:  # noqa: BLE001 -- the brain half fails open
        b = None
    if b:
        parts.append(b)
    return " ".join(parts) or None


def emit(text):
    return json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": text}})


def selftest():
    import tempfile
    ok = True
    with tempfile.TemporaryDirectory() as t:
        Path(t, "tools").mkdir()
        Path(t, "tools", "old.py").write_text("x")
        Path(t, "upstream", "a~b").mkdir(parents=True)
        p = lambda f, s="S1": {"session_id": s, "tool_input": {"file_path": f, "content": ""}}
        m1 = message(p("tools/sync_cal.py"), t)
        m2 = message(p("tools/other_new.py"), t)
        m3 = message(p("tools/old.py", "S2"), t)
        m4 = message(p("upstream/a~b/tools/new.py", "S3"), t)
        m5 = message(p(".claude/skills/newskill/SKILL.md"), t)
        for cond, name in ((m1 and "PRIOR ART: new tool tools/sync_cal.py" in m1 and "find.py sync cal" in m1, "new tool prints once"),
                           (m2 is None, "same kind again in the same session prints nothing"),
                           (m3 is None, "existing file prints nothing"), (m4 is None, "held lane prints nothing"),
                           (m5 and "new skill" in m5, "a different kind prints"),
                           (json.loads(emit("x"))["hookSpecificOutput"]["hookEventName"] == "PreToolUse", "channel shape")):
            if not cond:
                ok = False
                print("FAIL", name)
        Path(t, "station.json").write_text('{"name": "x", "knobs": {"map": "XS"}}')
        if message(p("tools/z_new.py", "S9"), t) is not None:
            ok = False
            print("FAIL knob XS prints nothing")
    print("selftest OK" if ok else "selftest FAILED")
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        return selftest()
    try:
        text = message(json.loads(sys.stdin.read() or "{}"), C.ROOT)
        if text:
            print(emit(text))
    except Exception:  # noqa: BLE001 -- fail open, silently
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
