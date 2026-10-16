"""color.py — CSS colour parsing, compositing, WCAG contrast and hue classification (stdlib).

Our own reimplementation of the colour helpers impeccable's detector relies on (upstream
crates/foundation/src/color.rs, Apache-2.0; see tools/design/detector/PORT_MAP.md). Colours are RGBA tuples of
floats: r, g, b in 0..255, a in 0..1.
"""
import colorsys
import math
import re

NAMED = {
    "aliceblue": "f0f8ff", "antiquewhite": "faebd7", "aqua": "00ffff", "aquamarine": "7fffd4", "azure": "f0ffff",
    "beige": "f5f5dc", "bisque": "ffe4c4", "black": "000000", "blanchedalmond": "ffebcd", "blue": "0000ff",
    "blueviolet": "8a2be2", "brown": "a52a2a", "burlywood": "deb887", "cadetblue": "5f9ea0", "chartreuse": "7fff00",
    "chocolate": "d2691e", "coral": "ff7f50", "cornflowerblue": "6495ed", "cornsilk": "fff8dc", "crimson": "dc143c",
    "cyan": "00ffff", "darkblue": "00008b", "darkcyan": "008b8b", "darkgoldenrod": "b8860b", "darkgray": "a9a9a9",
    "darkgreen": "006400", "darkgrey": "a9a9a9", "darkkhaki": "bdb76b", "darkmagenta": "8b008b",
    "darkolivegreen": "556b2f", "darkorange": "ff8c00", "darkorchid": "9932cc", "darkred": "8b0000",
    "darksalmon": "e9967a", "darkseagreen": "8fbc8f", "darkslateblue": "483d8b", "darkslategray": "2f4f4f",
    "darkslategrey": "2f4f4f", "darkturquoise": "00ced1", "darkviolet": "9400d3", "deeppink": "ff1493",
    "deepskyblue": "00bfff", "dimgray": "696969", "dimgrey": "696969", "dodgerblue": "1e90ff", "firebrick": "b22222",
    "floralwhite": "fffaf0", "forestgreen": "228b22", "fuchsia": "ff00ff", "gainsboro": "dcdcdc",
    "ghostwhite": "f8f8ff", "gold": "ffd700", "goldenrod": "daa520", "gray": "808080", "green": "008000",
    "greenyellow": "adff2f", "grey": "808080", "honeydew": "f0fff0", "hotpink": "ff69b4", "indianred": "cd5c5c",
    "indigo": "4b0082", "ivory": "fffff0", "khaki": "f0e68c", "lavender": "e6e6fa", "lavenderblush": "fff0f5",
    "lawngreen": "7cfc00", "lemonchiffon": "fffacd", "lightblue": "add8e6", "lightcoral": "f08080",
    "lightcyan": "e0ffff", "lightgoldenrodyellow": "fafad2", "lightgray": "d3d3d3", "lightgreen": "90ee90",
    "lightgrey": "d3d3d3", "lightpink": "ffb6c1", "lightsalmon": "ffa07a", "lightseagreen": "20b2aa",
    "lightskyblue": "87cefa", "lightslategray": "778899", "lightslategrey": "778899", "lightsteelblue": "b0c4de",
    "lightyellow": "ffffe0", "lime": "00ff00", "limegreen": "32cd32", "linen": "faf0e6", "magenta": "ff00ff",
    "maroon": "800000", "mediumaquamarine": "66cdaa", "mediumblue": "0000cd", "mediumorchid": "ba55d3",
    "mediumpurple": "9370db", "mediumseagreen": "3cb371", "mediumslateblue": "7b68ee", "mediumspringgreen": "00fa9a",
    "mediumturquoise": "48d1cc", "mediumvioletred": "c71585", "midnightblue": "191970", "mintcream": "f5fffa",
    "mistyrose": "ffe4e1", "moccasin": "ffe4b5", "navajowhite": "ffdead", "navy": "000080", "oldlace": "fdf5e6",
    "olive": "808000", "olivedrab": "6b8e23", "orange": "ffa500", "orangered": "ff4500", "orchid": "da70d6",
    "palegoldenrod": "eee8aa", "palegreen": "98fb98", "paleturquoise": "afeeee", "palevioletred": "db7093",
    "papayawhip": "ffefd5", "peachpuff": "ffdab9", "peru": "cd853f", "pink": "ffc0cb", "plum": "dda0dd",
    "powderblue": "b0e0e6", "purple": "800080", "rebeccapurple": "663399", "red": "ff0000", "rosybrown": "bc8f8f",
    "royalblue": "4169e1", "saddlebrown": "8b4513", "salmon": "fa8072", "sandybrown": "f4a460", "seagreen": "2e8b57",
    "seashell": "fff5ee", "sienna": "a0522d", "silver": "c0c0c0", "skyblue": "87ceeb", "slateblue": "6a5acd",
    "slategray": "708090", "slategrey": "708090", "snow": "fffafa", "springgreen": "00ff7f", "steelblue": "4682b4",
    "tan": "d2b48c", "teal": "008080", "thistle": "d8bfd8", "tomato": "ff6347", "turquoise": "40e0d0",
    "violet": "ee82ee", "wheat": "f5deb3", "white": "ffffff", "whitesmoke": "f5f5f5", "yellow": "ffff00",
    "yellowgreen": "9acd32",
}

_NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?"
COLOR_TOKEN = re.compile(
    r"#[0-9a-fA-F]{3,8}\b|\bcolor-mix\((?:[^()]|\([^()]*\))*\)|\b(?:rgba?|hsla?|oklch|oklab|lab|lch|hwb|color)\([^()]*\)|\b(?:%s|transparent)\b"
    % "|".join(sorted(NAMED, key=len, reverse=True)), re.I)


def _clamp(v, lo=0.0, hi=255.0):
    return max(lo, min(hi, v))


def _num(tok, scale=1.0, pct_scale=None):
    tok = tok.strip()
    if tok.lower() == "none":
        return 0.0
    if tok.endswith("%"):
        return float(tok[:-1]) * (pct_scale if pct_scale is not None else scale) / 100.0
    return float(tok)


def _hue(tok):
    t = tok.strip().lower()
    m = re.match(r"(%s)(deg|rad|grad|turn)?$" % _NUM, t)
    if not m:
        return 0.0
    v = float(m.group(1))
    unit = m.group(2) or "deg"
    return {"deg": v, "rad": math.degrees(v), "grad": v * 0.9, "turn": v * 360.0}[unit] % 360.0


def _args(inner):
    inner = inner.replace(",", " ")
    alpha = None
    if "/" in inner:
        inner, alpha = inner.split("/", 1)
    parts = inner.split()
    return parts, alpha


def _alpha(tok):
    if tok is None:
        return 1.0
    tok = tok.strip()
    if not tok:
        return 1.0
    return _clamp(_num(tok, 1.0, 1.0), 0.0, 1.0)


def _oklab_to_rgb(L, a, b):
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    bb = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s

    def enc(c):
        c = max(0.0, min(1.0, c))
        return 255.0 * (12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055)
    return enc(r), enc(g), enc(bb)


def parse_color(value):
    """A CSS colour string -> (r, g, b, a) or None (keywords like currentColor/inherit/var() -> None)."""
    if value is None:
        return None
    v = value.strip().lower()
    if not v:
        return None
    if v == "transparent":
        return (0.0, 0.0, 0.0, 0.0)
    if v in NAMED:
        h = NAMED[v]
        return (float(int(h[0:2], 16)), float(int(h[2:4], 16)), float(int(h[4:6], 16)), 1.0)
    if v.startswith("#"):
        h = v[1:]
        if not re.fullmatch(r"[0-9a-f]+", h) or len(h) not in (3, 4, 6, 8):
            return None
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h)
        a = int(h[6:8], 16) / 255.0 if len(h) == 8 else 1.0
        return (float(int(h[0:2], 16)), float(int(h[2:4], 16)), float(int(h[4:6], 16)), a)
    m = re.match(r"^([a-z-]+)\((.*)\)$", v, re.S)
    if not m:
        return None
    fn, inner = m.group(1), m.group(2)
    if fn == "color-mix":
        return _color_mix(inner)
    if fn == "color":
        parts, alpha = _args(inner)
        if len(parts) < 4 or parts[0] not in ("srgb", "srgb-linear", "display-p3"):
            return None          # rec2020, xyz, a98-rgb ...: not modelled -> abstain
        try:
            ch = [max(0.0, min(1.0, _num(x, 1.0, 1.0))) for x in parts[1:4]]
        except ValueError:
            return None
        if parts[0] == "srgb-linear":
            ch = [12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055 for c in ch]
        # display-p3 is treated as sRGB (same transfer curve; gamut difference < 1 contrast decimal for UI colours)
        return (ch[0] * 255, ch[1] * 255, ch[2] * 255, _alpha(alpha))
    try:
        parts, alpha = _args(inner)
        if fn in ("rgb", "rgba"):
            if len(parts) == 4 and alpha is None:
                parts, alpha = parts[:3], parts[3]
            r, g, b = (_clamp(_num(p, 1.0, 255.0)) for p in parts[:3])
            return (r, g, b, _alpha(alpha))
        if fn in ("hsl", "hsla"):
            if len(parts) == 4 and alpha is None:
                parts, alpha = parts[:3], parts[3]
            h = _hue(parts[0]) / 360.0
            s = _clamp(float(parts[1].rstrip("%")) / 100.0, 0, 1)
            light = _clamp(float(parts[2].rstrip("%")) / 100.0, 0, 1)
            r, g, b = colorsys.hls_to_rgb(h, light, s)
            return (r * 255, g * 255, b * 255, _alpha(alpha))
        if fn == "hwb":
            h = _hue(parts[0]) / 360.0
            w = float(parts[1].rstrip("%")) / 100.0
            bl = float(parts[2].rstrip("%")) / 100.0
            r, g, b = colorsys.hls_to_rgb(h, 0.5, 1.0)
            if w + bl >= 1:
                gray = w / (w + bl)
                return (gray * 255,) * 3 + (_alpha(alpha),)
            f = lambda c: (c * (1 - w - bl) + w) * 255
            return (f(r), f(g), f(b), _alpha(alpha))
        if fn == "oklch":
            L = _num(parts[0], 1.0, 1.0)
            C = _num(parts[1], 1.0, 0.4)
            H = math.radians(_hue(parts[2]))
            r, g, b = _oklab_to_rgb(L, C * math.cos(H), C * math.sin(H))
            return (r, g, b, _alpha(alpha))
        if fn == "oklab":
            L = _num(parts[0], 1.0, 1.0)
            r, g, b = _oklab_to_rgb(L, _num(parts[1], 1.0, 0.4), _num(parts[2], 1.0, 0.4))
            return (r, g, b, _alpha(alpha))
        if fn in ("lab", "lch"):
            # CIE Lab/LCh (D50) approximated through D65 sRGB; good to ~1 contrast decimal
            L = _num(parts[0], 1.0, 1.0)
            if fn == "lch":
                C, H = _num(parts[1], 1.0, 1.5), math.radians(_hue(parts[2]))
                A, B = C * math.cos(H), C * math.sin(H)
            else:
                A, B = _num(parts[1], 1.0, 1.25), _num(parts[2], 1.0, 1.25)
            fy = (L + 16) / 116
            fx, fz = fy + A / 500, fy - B / 200
            inv = lambda t: t ** 3 if t ** 3 > 0.008856 else (t - 16 / 116) / 7.787
            X, Y, Z = 0.96422 * inv(fx), 1.0 * inv(fy), 0.82521 * inv(fz)
            rl = 3.1338561 * X - 1.6168667 * Y - 0.4906146 * Z
            gl = -0.9787684 * X + 1.9161415 * Y + 0.0334540 * Z
            bl = 0.0719453 * X - 0.2289914 * Y + 1.4052427 * Z
            enc = lambda c: 255.0 * (12.92 * c if c <= 0.0031308 else 1.055 * max(c, 0) ** (1 / 2.4) - 0.055)
            return (_clamp(enc(rl)), _clamp(enc(gl)), _clamp(enc(bl)), _alpha(alpha))
    except (ValueError, IndexError):
        return None
    return None


def _split_commas(text):
    out, depth, buf = [], 0, []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    out.append("".join(buf).strip())
    return out


def _color_mix(inner):
    """color-mix(in <space>, A [p%], B [q%]) mixed in sRGB (oklab/oklch mixes approximated in sRGB)."""
    parts = _split_commas(inner)
    if len(parts) != 3 or not parts[0].startswith("in "):
        return None
    cols = []
    for part in parts[1:]:
        m = re.match(r"^(.*?)(?:\s+([\d.]+)%)?$", part.strip(), re.S)
        c = parse_color(m.group(1))
        if c is None:
            return None
        cols.append((c, float(m.group(2)) / 100 if m.group(2) else None))
    (a, pa), (b, pb) = cols
    if pa is None and pb is None:
        pa, pb = 0.5, 0.5
    elif pa is None:
        pa = 1 - pb
    elif pb is None:
        pb = 1 - pa
    tot = pa + pb
    if tot <= 0:
        return None
    pa, pb = pa / tot, pb / tot
    alpha = a[3] * pa + b[3] * pb
    if alpha <= 0:
        return (0.0, 0.0, 0.0, 0.0)
    mix = tuple((a[i] * a[3] * pa + b[i] * b[3] * pb) / alpha for i in range(3))
    return mix + (alpha * min(1.0, tot if tot < 1 else 1.0),)


def find_colors(text):
    """Every parseable colour literal in a CSS value, in order: [(token, rgba)]."""
    out = []
    for m in COLOR_TOKEN.finditer(text or ""):
        c = parse_color(m.group(0))
        if c is not None:
            out.append((m.group(0), c))
    return out


def over(fg, bg):
    """Composite fg (rgba) over an opaque-ish bg (rgba) -> rgba."""
    a = fg[3] + bg[3] * (1 - fg[3])
    if a <= 0:
        return (0.0, 0.0, 0.0, 0.0)
    ch = lambda i: (fg[i] * fg[3] + bg[i] * bg[3] * (1 - fg[3])) / a
    return (ch(0), ch(1), ch(2), a)


def luminance(c):
    def lin(v):
        v = v / 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2])


def contrast(fg, bg):
    """WCAG 2.x contrast ratio of fg composited over bg (bg assumed opaque after compositing on white)."""
    if bg[3] < 1:
        bg = over(bg, (255.0, 255.0, 255.0, 1.0))
    if fg[3] < 1:
        fg = over(fg, bg)
    l1, l2 = luminance(fg), luminance(bg)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def hsl(c):
    """(hue deg, saturation 0..1, lightness 0..1)."""
    h, l, s = colorsys.rgb_to_hls(c[0] / 255.0, c[1] / 255.0, c[2] / 255.0)
    return h * 360.0, s, l


def chroma(c):
    return (max(c[:3]) - min(c[:3])) / 255.0


def is_gray(c, tol=0.1):
    """Neutral: channel spread at most `tol` of full scale."""
    return chroma(c) <= tol


def hexs(c):
    return "#%02x%02x%02x" % tuple(int(round(_clamp(v))) for v in c[:3])
