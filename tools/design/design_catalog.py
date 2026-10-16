#!/usr/bin/env python3
"""design_catalog.py — deal design directions for design-pass variants: the local catalog, plus impeccable.style's roll.

owner: governance/rules.d/design.json R-design-roll (check `design_catalog`; moved from studio, reconcile-01) · callers: the design-pass workflow
(Brief stage records the hand in the brief; Prototype gives each variant its direction), the operator by hand.
stdlib only.

Earned by: the operator's decisions 2026-10-16 (relayed by PRIME): build a LOCAL direction catalog in place of the
engine's hosted roll; "why not as additional options also call upon their service to be fed options as well? wouldnt
hurt"; "on automatically". So the local catalog (design_catalog.json) is always dealt, and impeccable.style's
/api/roll is asked too unless station.json `design_catalog_sources` drops "impeccable".
Retires: design-pass's fixed DIRECTIONS list as the only source of variant directions.

The roll request mirrors impeccable's engine at pin 5bf0a069dc85 (crates/context/src/concept_seed.rs fetch_roll,
telemetry.rs): GET {IMPECCABLE_API_URL or https://impeccable.style/api}/roll?scope=direction&key=<k>&reroll=0
[&mode=<persuade|operate|read|experience>][&platform=<web|ios|android>], headers `X-Impeccable-Client:
impeccable/<v>` and — ALWAYS here — `X-Impeccable-Telemetry: off` (the engine's opted-out form: "the roll still
happens, and the server records nothing for it"). Budget IMPECCABLE_API_TIMEOUT ms (default 4000). The key is a
fresh random 32-hex per run: no project name, file, path or code is ever sent. The /api/chosen choice ping is
never sent unless station.json `impeccable_roll.telemetry` is true (default false); even then this tool only builds
it on an explicit `ping` command. Offline, timeout, non-2xx or a malformed body -> local-only with one notice line;
the run never fails because of the network.

CLI:
  design_catalog.py deal [--n 3] [--seed S] [--mode persuade] [--platform web] [--sources local,impeccable] [--json]
  design_catalog.py list
  design_catalog.py --check      audit row design_catalog (catalog valid, every ink/ground pair passes AA)
  design_catalog.py --selftest   planted: stub roll -> impeccable-tagged variants; stub timeout -> local-only + notice;
                                 no choice ping unless telemetry true; request carries the opt-out header, no project data
Exit: 0 ok · 1 check failed · 2 usage.
"""
import argparse
import hashlib
import json
import os
import random
import re
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CATALOG = HERE / "design_catalog.json"
CLIENT = "impeccable/0.0.0+studio"   # matches the engine's ^impeccable/[0-9A-Za-z.+-]{1,32}( [a-z]{1,16})?$
MODES = ("persuade", "operate", "read", "experience")
PLATFORMS = ("web", "ios", "android")
HEX12 = re.compile(r"^[0-9a-f]{12}$")
HEX32 = re.compile(r"^[0-9a-f]{32}$")


def settings(root=ROOT):
    """station.json design_catalog_sources (default ["local", "impeccable"]) and impeccable_roll."""
    try:
        sj = json.loads((Path(root) / "station.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        sj = {}
    sources = sj.get("design_catalog_sources") or ["local", "impeccable"]
    roll = {"telemetry": False}
    roll.update(sj.get("impeccable_roll") or {})
    return [s for s in sources if s in ("local", "impeccable")] or ["local"], roll


def load():
    return json.loads(CATALOG.read_text(encoding="utf-8"))["directions"]


def deal_local(n, seed, mode=None):
    """n distinct directions, seeded; directions whose modes include `mode` come first, and the hand mixes registers."""
    rng = random.Random(seed)
    dirs = load()
    pool = [d for d in dirs if not mode or mode in d["modes"]] or dirs
    rest = [d for d in dirs if d not in pool]
    rng.shuffle(pool)
    rng.shuffle(rest)
    order = pool + rest
    hand, regs = [], set()
    for d in order:                      # first pass: one per register so a hand is never all-safe or all-bold
        if d["register"] not in regs and len(hand) < n:
            hand.append(d)
            regs.add(d["register"])
    for d in order:
        if len(hand) >= n:
            break
        if d not in hand:
            hand.append(d)
    return [dict(d, source="local", source_ref="local:%s" % d["id"]) for d in hand[:n]]


def roll_request(mode=None, platform=None, base=None, key=None):
    """(url, headers) of the opted-out roll request; no project data in either."""
    base = (base or os.environ.get("IMPECCABLE_API_URL") or "https://impeccable.style/api").rstrip("/")
    params = [("scope", "direction"), ("key", key or secrets.token_hex(16)), ("reroll", "0")]
    if mode in MODES:
        params.append(("mode", mode))
    if platform in PLATFORMS:
        params.append(("platform", platform))
    url = "%s/roll?%s" % (base, urllib.parse.urlencode(params))
    return url, {"X-Impeccable-Client": CLIENT, "X-Impeccable-Telemetry": "off", "Accept": "application/json"}


def fetch_roll(mode=None, platform=None, base=None, timeout_ms=None):
    """-> (challengers, meta, notice). challengers=[] with a notice when anything goes wrong."""
    url, headers = roll_request(mode, platform, base)
    t = timeout_ms if timeout_ms is not None else float(os.environ.get("IMPECCABLE_API_TIMEOUT") or 4000)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=t / 1000.0) as r:
            if not 200 <= r.status < 300:
                return [], {}, "impeccable roll: HTTP %d; local catalog only" % r.status
            body = json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as e:
        return [], {}, "impeccable roll unavailable (%s); local catalog only" % (getattr(e, "reason", None) or e.__class__.__name__)
    ch = body.get("challengers") if isinstance(body, dict) else None
    if not isinstance(ch, list) or not ch:
        return [], {}, "impeccable roll returned no challengers; local catalog only"
    meta = {"poolRevision": body.get("poolRevision") if HEX12.match(str(body.get("poolRevision", ""))) else None,
            "handId": body.get("handId") if HEX32.match(str(body.get("handId", ""))) else None}
    out = []
    for c in ch:
        if not isinstance(c, dict) or not re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", str(c.get("id", ""))):
            continue
        out.append({"id": c["id"], "name": c.get("form") or c["id"], "idea": c.get("spark", ""),
                    "system": c.get("system", []), "web_leverage": c.get("webLeverage", ""), "source": "impeccable",
                    "source_ref": "impeccable:%s@%s" % (c["id"], meta["poolRevision"] or "unknown-revision")})
    return out, meta, None if out else "impeccable roll had no usable challengers; local catalog only"


def deal(n=3, seed=None, mode=None, platform=None, sources=None, base=None, timeout_ms=None, log=print):
    """The design-pass hand: local directions always; impeccable challengers interleaved when the roll answers."""
    seed = seed if seed is not None else secrets.token_hex(4)
    sources = sources or settings()[0]
    local = deal_local(n, seed, mode) if "local" in sources else []
    remote, meta, notice = ([], {}, None)
    if "impeccable" in sources:
        remote, meta, notice = fetch_roll(mode, platform, base, timeout_ms)
        if notice:
            log(notice)
    hand = []
    if remote:   # alternate local / impeccable, local first: the local catalog stays the default voice
        li, ri = iter(local), iter(remote)
        while len(hand) < n:
            nxt = next(li, None) if len(hand) % 2 == 0 else next(ri, None)
            nxt = nxt or next(li, None) or next(ri, None)
            if nxt is None:
                break
            hand.append(nxt)
    else:
        hand = local[:n]
    return {"seed": seed, "sources": sources, "mode": mode, "roll": meta or None, "notice": notice, "hand": hand}


def brief_section(d):
    """Markdown for the brief's `## Directions` section (the record of this run's hand)."""
    lines = ["## Directions", "seed: %s · sources: %s%s" % (d["seed"], ", ".join(d["sources"]),
                                                          (" · roll: poolRevision %s handId %s" % (d["roll"].get("poolRevision"), d["roll"].get("handId"))) if d.get("roll") else "")]
    if d.get("notice"):
        lines.append("note: " + d["notice"])
    for i, h in enumerate(d["hand"], 1):
        lines.append("- v%d: %s (`%s`) — %s" % (i, h["name"], h["source_ref"], h.get("idea", "")))
    return "\n".join(lines) + "\n"


def choice_ping(chosen_id, settings_roll, base=None, send=False):
    """The /api/chosen body the engine would POST — built ONLY when telemetry is explicitly true; sent only on send=True."""
    if settings_roll.get("telemetry") is not True:
        return None
    url = (base or os.environ.get("IMPECCABLE_API_URL") or "https://impeccable.style/api").rstrip("/") + "/chosen"
    body = json.dumps({"chosenId": chosen_id, "source": "agent"}).encode("utf-8")
    if send:
        req = urllib.request.Request(url, data=body, headers={"X-Impeccable-Client": CLIENT, "Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=4).close()
        except (urllib.error.URLError, OSError):
            return None
    return {"url": url, "body": body.decode("utf-8")}


def check():
    sys.path.insert(0, str(HERE))
    import contrast
    viol = []
    dirs = load()
    ids = [d["id"] for d in dirs]
    if len(set(ids)) != len(ids):
        viol.append("duplicate direction ids")
    for d in dirs:
        for k in ("id", "name", "register", "modes", "idea", "palette", "type", "space", "radius", "motion", "composition", "impeccable", "emil"):
            if k not in d:
                viol.append("%s: missing %s" % (d.get("id"), k))
        p = d.get("palette", {})
        for fg, bg, need in (("ink", "ground", 4.5), ("muted", "ground", 4.5), ("ink", "surface", 4.5), ("accent_ink", "accent", 4.5)):
            try:
                r = contrast.ratio(p[fg], p[bg])
            except Exception as e:
                viol.append("%s: %s/%s %s" % (d["id"], fg, bg, e))
                continue
            if r < need:
                viol.append("%s: %s %s on %s %s is %.2f:1 < %.1f" % (d["id"], fg, p[fg], bg, p[bg], r, need))
        if d.get("type", {}).get("body_size", 0) < 16 or d.get("type", {}).get("leading", 0) < 1.4:
            viol.append("%s: body under 16px or leading under 1.4" % d["id"])
        if any(re.search(r"https?://", json.dumps(d.get("type", {}))) for _ in [0]):
            viol.append("%s: a font loads from the network" % d["id"])
    print("design_catalog: %d violation(s) · 0 worklist · denominator %d" % (len(viol), len(dirs)))
    for v in viol:
        print("  VIOLATION " + v)
    return 1 if viol else 0


def selftest():
    import contextlib
    import io
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    seen = []

    class Stub(BaseHTTPRequestHandler):
        mode = "ok"

        def do_GET(self):
            seen.append(("GET", self.path, dict(self.headers)))
            if Stub.mode == "slow":
                import time
                time.sleep(1.0)
            body = json.dumps({"poolRevision": "0123456789ab", "handId": "00112233445566778899aabbccddeeff",
                               "challengers": [{"id": "teletext-service", "form": "Teletext", "spark": "s", "system": ["r"], "webLeverage": "w"},
                                               {"id": "microfiche-reader", "form": "Microfiche", "spark": "s", "system": ["r"], "webLeverage": "w"}]})
            try:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(body.encode())
            except OSError:
                pass

        def do_POST(self):
            seen.append(("POST", self.path, dict(self.headers)))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d/api" % srv.server_address[1]
    quiet = lambda *a: None
    cases = 0
    try:
        # 1 the stub deals a hand -> its variants appear tagged impeccable, alongside local ones
        d = deal(3, seed="t1", mode="persuade", sources=["local", "impeccable"], base=base, timeout_ms=3000, log=quiet)
        srcs = [h["source"] for h in d["hand"]]
        assert "impeccable" in srcs and "local" in srcs and len(d["hand"]) == 3, d
        assert any(h["source_ref"] == "impeccable:teletext-service@0123456789ab" for h in d["hand"]), d["hand"]
        assert d["roll"]["handId"] == "00112233445566778899aabbccddeeff"
        cases += 1
        # 2 the request is the opted-out form and carries no project data
        m, path, hdr = seen[-1]
        q = urllib.parse.parse_qs(urllib.parse.urlparse(path).query)
        assert m == "GET" and path.startswith("/api/roll?"), path
        assert hdr.get("X-Impeccable-Telemetry") == "off" and re.match(r"^impeccable/[0-9A-Za-z.+-]{1,32}$", hdr.get("X-Impeccable-Client", "")), hdr
        assert set(q) <= {"scope", "key", "reroll", "mode", "platform"} and re.match(r"^[0-9a-f]{32}$", q["key"][0]), q
        assert not re.search(r"lettuce|landing|work/|\.html|studio", path), path
        cases += 1
        # 3 the stub times out -> local only, one notice line, the run does not fail
        Stub.mode = "slow"
        notes = []
        d = deal(3, seed="t2", sources=["local", "impeccable"], base=base, timeout_ms=200, log=notes.append)
        assert [h["source"] for h in d["hand"]] == ["local"] * 3 and len(notes) == 1 and "local catalog only" in notes[0], (d, notes)
        cases += 1
        Stub.mode = "ok"
        # 4 offline (nothing listening) -> local only + notice
        notes = []
        d = deal(2, seed="t3", sources=["local", "impeccable"], base="http://127.0.0.1:9/api", timeout_ms=300, log=notes.append)
        assert len(d["hand"]) == 2 and all(h["source"] == "local" for h in d["hand"]) and notes, d
        cases += 1
        # 5 no choice ping unless telemetry is explicitly true; a deal never POSTs
        assert not any(s[0] == "POST" for s in seen), "a deal must never send the choice ping"
        assert choice_ping("teletext-service", {"telemetry": False}, base, send=True) is None
        assert not any(s[0] == "POST" for s in seen)
        assert choice_ping("teletext-service", {}, base, send=True) is None
        assert choice_ping("teletext-service", {"telemetry": True}, base, send=False)["url"].endswith("/api/chosen")
        cases += 1
        # 6 sources ["local"] never touches the network
        n0 = len(seen)
        d = deal(3, seed="t4", sources=["local"], base=base, log=quiet)
        assert len(seen) == n0 and all(h["source"] == "local" for h in d["hand"])
        cases += 1
        # 7 seeded deals are reproducible and mix registers
        a, b = deal_local(3, "same"), deal_local(3, "same")
        assert [x["id"] for x in a] == [x["id"] for x in b] and len({x["register"] for x in a}) == 2
        cases += 1
        # 8 the catalog check passes, and a planted low-contrast direction fails it
        with contextlib.redirect_stdout(io.StringIO()):
            assert check() == 0
            keep = CATALOG.read_text(encoding="utf-8")
            data = json.loads(keep)
            data["directions"][0]["palette"]["muted"] = "#b8b8b8"
            try:
                CATALOG.write_text(json.dumps(data), encoding="utf-8")
                assert check() == 1, "a planted low-contrast palette must fail"
            finally:
                CATALOG.write_text(keep, encoding="utf-8")
        cases += 1
    finally:
        srv.shutdown()
    print("selftest OK (%d cases: roll hand tagged impeccable · opted-out request, no project data · timeout + offline -> local with notice · no choice ping · local-only no network · seeded · contrast plant)" % cases)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", nargs="?", choices=["deal", "list"])
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--seed")
    ap.add_argument("--mode", choices=MODES)
    ap.add_argument("--platform", choices=PLATFORMS, default="web")
    ap.add_argument("--sources")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.check:
        return check()
    if a.cmd == "list":
        for d in load():
            print("%-16s %-7s %-28s %s" % (d["id"], d["register"], ",".join(d["modes"]), d["idea"][:70]))
        return 0
    if a.cmd != "deal" or not 1 <= a.n <= 5:
        ap.print_usage(sys.stderr)
        return 2
    srcs = a.sources.split(",") if a.sources else None
    d = deal(a.n, a.seed, a.mode, a.platform, srcs, log=lambda m: print(m, file=sys.stderr))
    print(json.dumps(d, indent=1, ensure_ascii=False) if a.json else brief_section(d), end="" if not a.json else "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
