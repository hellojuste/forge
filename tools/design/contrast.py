#!/usr/bin/env python3
"""contrast.py — WCAG 2.x contrast ratio for a colour pair or a whole palette (stdlib only).

owner: governance/rules.d/design.json R-design-detector (commons since reconcile-01) · callers: skill design-review, tools/design/handoff.py
(a11y re-measure), studio's palette-check gap skill
Earned by: the palette-check contract test (station-studio.md section 3): "#777 on #fff fails AA body text" — a grey that
looks readable on a monitor measures 4.48:1, under the 4.5:1 AA floor for body text. Eyes round it up; arithmetic does not.
Retires: nothing (first contrast check in the kit). When the session lists an account-level `dataviz` skill, its palette
validator is preferred for CHART palettes (it also checks categorical separation); this tool stays the floor for text/UI pairs.

Formula (WCAG 2.2, 1.4.3 / 1.4.6 / 1.4.11): relative luminance L = 0.2126 R + 0.7152 G + 0.0722 B with each sRGB channel
c = c8/255 linearised as c/12.92 if c <= 0.04045 else ((c + 0.055)/1.055)^2.4; ratio = (L1 + 0.05)/(L2 + 0.05), L1 >= L2.
Thresholds: AA body 4.5 · AA large text 3.0 · AAA body 7.0 · AAA large 4.5 · non-text UI (borders, icons, focus) 3.0.
Alpha is refused (a translucent colour has no contrast until it is composited onto a known background).

CLI:
  contrast.py FG BG [--level AA|AAA] [--use body|large|ui]     one pair; exit 0 pass, 1 fail
  contrast.py --palette FILE.json [--level AA|AAA]             FILE: {"pairs": [{"fg","bg","use"?,"name"?}, ...]}
                                                                or {"colors": {"name": "#hex"}, "background": "#hex"}
  contrast.py --selftest
Exit: 0 every pair passes · 1 a pair fails · 2 usage / unreadable input.
"""
import argparse
import json
import re
import sys

THRESHOLDS = {("AA", "body"): 4.5, ("AA", "large"): 3.0, ("AA", "ui"): 3.0,
              ("AAA", "body"): 7.0, ("AAA", "large"): 4.5, ("AAA", "ui"): 3.0}
HEX = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
RGB = re.compile(r"^rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)$")


class Bad(ValueError):
    pass


def parse(colour):
    s = str(colour).strip()
    m = HEX.match(s)
    if m:
        h = m.group(1)
        if len(h) == 3:
            h = "".join(ch * 2 for ch in h)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    m = RGB.match(s.lower())
    if m:
        vals = tuple(int(x) for x in m.groups())
        if all(0 <= v <= 255 for v in vals):
            return vals
    if s.lower().startswith(("rgba", "hsla")) or (s.startswith("#") and len(s) in (5, 9)):
        raise Bad("%r carries alpha: composite it onto its real background first" % s)
    raise Bad("%r is not #rgb, #rrggbb or rgb(r,g,b)" % s)


def _lin(c8):
    c = c8 / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(rgb):
    r, g, b = (_lin(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(fg, bg):
    l1, l2 = sorted((luminance(parse(fg)), luminance(parse(bg))), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def verdict(fg, bg, level="AA", use="body"):
    need = THRESHOLDS[(level, use)]
    r = ratio(fg, bg)
    # WCAG compares the unrounded ratio; 4.48 is a fail even though it prints near 4.5
    return {"fg": fg, "bg": bg, "ratio": round(r, 2), "exact": r, "need": need, "level": level, "use": use,
            "pass": r >= need}


def pairs_of(obj):
    if isinstance(obj, dict) and isinstance(obj.get("pairs"), list):
        return [(p["fg"], p["bg"], p.get("use", "body"), p.get("name") or "%s on %s" % (p["fg"], p["bg"])) for p in obj["pairs"]]
    if isinstance(obj, dict) and isinstance(obj.get("colors"), dict) and obj.get("background"):
        bg = obj["background"]
        use = obj.get("use", "body")
        return [(c, bg, use, n) for n, c in sorted(obj["colors"].items())]
    raise Bad("palette file needs {'pairs': [...]} or {'colors': {...}, 'background': '#hex'}")


def line(v, name=None):
    return "%s %-28s %5.2f:1  need %.1f (%s %s)" % ("PASS" if v["pass"] else "FAIL", name or "%s on %s" % (v["fg"], v["bg"]),
                                                  v["ratio"], v["need"], v["level"], v["use"])


def selftest():
    cases = 0
    v = verdict("#777", "#fff")
    assert not v["pass"] and 4.47 < v["exact"] < 4.49, v; cases += 1          # the contract test
    assert verdict("#767676", "#ffffff")["pass"], "#767676 is the lightest grey that passes AA body on white"; cases += 1
    assert abs(ratio("#000", "#fff") - 21.0) < 1e-9; cases += 1
    assert abs(ratio("#fff", "#fff") - 1.0) < 1e-9; cases += 1
    assert abs(ratio("#fff", "#000") - ratio("#000", "#fff")) < 1e-12, "order-free"; cases += 1
    assert verdict("#777", "#fff", use="large")["pass"], "4.48 passes AA large (3.0)"; cases += 1
    assert not verdict("#777", "#fff", level="AAA", use="large")["pass"], "4.48 fails AAA large (4.5)"; cases += 1
    assert verdict("rgb(0, 0, 0)", "#FFFFFF")["pass"]; cases += 1
    for bad in ("#12345", "rgba(0,0,0,.5)", "#00000080", "blue", "rgb(300,0,0)"):
        try:
            parse(bad)
        except Bad:
            cases += 1
            continue
        raise AssertionError("accepted bad colour %r" % bad)
    ps = pairs_of({"colors": {"muted": "#777777", "ink": "#111111"}, "background": "#ffffff"})
    got = {n: verdict(f, b, "AA", u)["pass"] for f, b, u, n in ps}
    assert got == {"ink": True, "muted": False}, got; cases += 1
    print("selftest OK (%d cases)" % cases)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("fg", nargs="?")
    ap.add_argument("bg", nargs="?")
    ap.add_argument("--level", choices=["AA", "AAA"], default="AA")
    ap.add_argument("--use", choices=["body", "large", "ui"], default="body")
    ap.add_argument("--palette")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    try:
        if a.palette:
            with open(a.palette, encoding="utf-8") as f:
                ps = pairs_of(json.load(f))
            vs = [(n, verdict(fg, bg, a.level, use)) for fg, bg, use, n in ps]
        elif a.fg and a.bg:
            vs = [(None, verdict(a.fg, a.bg, a.level, a.use))]
        else:
            ap.print_usage(sys.stderr)
            return 2
    except (Bad, KeyError, OSError, ValueError) as e:
        print("contrast: %s" % e, file=sys.stderr)
        return 2
    fails = 0
    for n, v in vs:
        print(line(v, n))
        fails += not v["pass"]
    print("contrast: %d of %d pair(s) fail %s" % (fails, len(vs), a.level))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
