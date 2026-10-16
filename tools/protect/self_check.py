#!/usr/bin/env python3
"""self_check.py — static exposure report for a site THE OPERATOR OWNS, against the known evasion signatures.

owner: governance/rules.d/protect.json R-protect-own-targets (commons since reconcile-01, DEC-core-0011; carries
R-quarantine-own-targets / DEC-quarantine-0006; study owner: station quarantine) · pack commons/packs/protection/PACK.md

Earned by: design/QUEUE.md Q4 (operator, 2026-10-16: "i genuinely just dont want anyone - especially myself - to be
exposed to unsafe behavior"). The study notes (notes/camofox-fingerprint-surfaces.md, notes/maxun-robot-signals.md,
notes/invisible_dots-automation-signatures.md) say which defenses the held tools defeat; this tool reports, for the
operator's OWN site, which of the checkable rows of commons/packs/protection/HARDENING_CHECKLIST.md are exposed. A checklist the
operator must remember to read is not run; a command that names each FAIL is.
Retires: nothing (no kit tool inspects a shipped site).

What it does (passive, honest, bounded): GET the page, GET /robots.txt and /sitemap.xml, and a burst of at most
BURST GETs to see whether a rate limit answers. Its User-Agent names itself. It never spoofs a fingerprint, never
submits a form, never follows a redirect to a host that is not owned, never imports or runs a quarantined tree.

Rails (DEC-quarantine-0006):
  * OWN TARGETS ONLY. A URL target is accepted only if its host is loopback (localhost, 127.0.0.0/8, ::1,
    *.localhost, *.test) or listed in the station's work/protection/OWNED.txt (one host per line, written by the
    operator; each station keeps its own, absent = empty). Anything
    else is REFUSED before any request (exit 3). There is no override flag: owning a host is recorded in a file.
  * A local directory target (a static build) is always the operator's own and makes no request at all.
  * NO BROKER/EXCHANGE. A host matching BROKER_RE is refused even if listed as owned (exit 3).
  * Evasion tooling never leaves quarantine: this file imports only the stdlib.

CLI:
  self_check.py <url-or-dir> [--owned-file F]   report; exit 0 no FAIL · 1 FAIL · 3 refused · 2 usage
  self_check.py check [--root DIR]              audit row: OWNED.txt (if present) well-formed, no broker host, pack present
  self_check.py --selftest                      planted-defect fixture site on 127.0.0.1 + refusal cases
Headline: "self_check: <n> violation(s) · <m> worklist · denominator <d>" (violations = FAIL rows, worklist = WARN).
Release: none; this never blocks a tool call. Fix the site or the OWNED.txt entry.
"""
import argparse
import ipaddress
import os
import re
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

NAME = "self_check"
SEP = "·"
UA = "stable-kit-self_check/1.0 (owner self-test; passive; no evasion)"
BURST = 5
TIMEOUT_S = 10
MAX_HOPS = 3
OWNED_FILE = Path("work") / "protection" / "OWNED.txt"
PACK_DIR = Path("commons") / "packs" / "protection"
PACK_FILES = ("PACK.md", "FAIR_DISTINCTION.md", "RATE_LIMITING.md", "HARDENING_CHECKLIST.md", "PRIVACY_CHECKLIST.md")
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "self_check"

BROKER_RE = re.compile(
    r"(broker|exchange|trading|forex|binance|coinbase|kraken|bitvavo|bitstamp|bitfinex|bybit|okx|kucoin|gemini\.com"
    r"|interactivebrokers|ibkr|etoro|degiro|robinhood|schwab|fidelity|vanguard|trading212|saxo|plus500|ig\.com"
    r"|tdameritrade|webull|revolut|tastytrade|oanda|bitmex|deribit|huobi|htx|crypto\.com)", re.I)
SENSITIVE_PATH_RE = re.compile(
    r"/(admin|wp-admin|account|accounts|user|users|profile|private|internal|draft|drafts|staging|backup|export"
    r"|invoice|invoices|dashboard|api/private)\b|[?&](token|key|session|email)=", re.I)
TOKEN_FIELD_RE = re.compile(r"(csrf|xsrf|authenticity_token|_token|nonce|__requestverificationtoken)", re.I)
HONEYPOT_RE = re.compile(r"(honeypot|hp_|website_url|leave.?empty|bot.?field|fax_only)", re.I)
VERSION_RE = re.compile(r"\d+\.\d+")
VENDOR_HEADERS = ("cf-ray", "cf-mitigated", "x-datadome", "x-px", "x-sucuri-id", "x-distil-cs")


class Refused(Exception):
    pass


# ---------------------------------------------------------------- ownership
def read_owned(path):
    """Hosts the operator declared as theirs: one per line; '#' comments; lowercase; no scheme or path."""
    hosts, bad = [], []
    p = Path(path)
    if not p.is_file():
        return hosts, bad
    for n, raw in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#", 1)[0].strip().lower()
        if not line:
            continue
        if not re.fullmatch(r"(\*\.)?[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*", line):
            bad.append("%s:%d not a bare host name: %r" % (p, n, raw.strip()))
            continue
        hosts.append(line)
    return hosts, bad


def is_loopback(host):
    host = (host or "").strip("[]").lower()
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".test"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def owned_reason(host, owned_hosts):
    """Why this host is the operator's, or raise Refused. Broker/exchange is refused first, always."""
    host = (host or "").strip("[]").lower()
    if not host:
        raise Refused("no host in target")
    if BROKER_RE.search(host):
        raise Refused("%s looks like a broker/exchange/trading host: out of scope for this station, even if owned" % host)
    if is_loopback(host):
        return "loopback"
    for h in owned_hosts:
        if host == h or (h.startswith("*.") and host.endswith(h[1:])):
            return "listed in %s" % OWNED_FILE
    raise Refused("%s is not shown to be the operator's own: it is not loopback and not listed in %s. "
                  "self_check runs only on sites you own; add the host to that file yourself if it is yours."
                  % (host, OWNED_FILE))


# ---------------------------------------------------------------- fetching (no redirects followed blindly)
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def default_fetch(url, method="GET"):
    """Return (status, {lowercase header: value}, set_cookie_list, body_text). Never follows a redirect itself."""
    host = urllib.parse.urlsplit(url).hostname or ""
    handlers = [_NoRedirect()]
    if is_loopback(host):
        handlers.append(urllib.request.ProxyHandler({}))
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(url, method=method, headers={"User-Agent": UA, "Accept": "text/html,*/*"})
    try:
        resp = opener.open(req, timeout=TIMEOUT_S)
    except urllib.error.HTTPError as e:
        resp = e
    status = resp.getcode() if hasattr(resp, "getcode") else resp.code
    headers = {k.lower(): v for k, v in resp.headers.items()}
    cookies = resp.headers.get_all("Set-Cookie") or []
    body = b""
    if method != "HEAD":
        try:
            body = resp.read(2_000_000)
        except Exception:
            body = b""
    return status, headers, cookies, body.decode("utf-8", "replace")


class Site:
    """The target, behind the ownership rail. Every request passes owned_reason() for its own host first."""

    def __init__(self, target, owned_hosts, fetch=default_fetch):
        self.owned_hosts = owned_hosts
        self.fetch_impl = fetch
        self.dir = None
        p = Path(target)
        if "://" not in target and p.is_dir():
            self.dir = p
            self.base = None
            self.reason = "local directory"
            return
        parts = urllib.parse.urlsplit(target)
        if parts.scheme not in ("http", "https"):
            raise Refused("target must be an http(s) URL or a local directory: %r" % target)
        self.reason = owned_reason(parts.hostname, owned_hosts)  # raises before any request
        self.base = target if parts.path else target + "/"
        self.scheme = parts.scheme
        self.requests = 0

    def get(self, path_or_url, method="GET"):
        """Fetch from the dir or the site. Redirects are followed only to owned hosts, at most MAX_HOPS."""
        if self.dir is not None:
            rel = path_or_url.lstrip("/") or "index.html"
            f = self.dir / rel
            if f.is_dir():
                f = f / "index.html"
            if not f.is_file():
                return 404, self.dir_headers(), [], ""
            return 200, self.dir_headers(), self.dir_cookies(), f.read_text(encoding="utf-8", errors="replace")
        url = urllib.parse.urljoin(self.base, path_or_url)
        for _ in range(MAX_HOPS + 1):
            owned_reason(urllib.parse.urlsplit(url).hostname, self.owned_hosts)
            self.requests += 1
            status, headers, cookies, body = self.fetch_impl(url, method)
            if status in (301, 302, 303, 307, 308) and headers.get("location"):
                url = urllib.parse.urljoin(url, headers["location"])
                continue
            return status, headers, cookies, body
        return status, headers, cookies, body

    def _headers_file(self):
        """Netlify/Cloudflare-Pages style `_headers` for a static build: lines under the `/*` block."""
        f = self.dir / "_headers"
        out, cookies, on = {}, [], False
        if f.is_file():
            for line in f.read_text(encoding="utf-8").splitlines():
                if line and not line[0].isspace():
                    on = line.strip() in ("/*", "/")
                    continue
                if on and ":" in line:
                    k, v = line.strip().split(":", 1)
                    if k.strip().lower() == "set-cookie":
                        cookies.append(v.strip())
                    else:
                        out[k.strip().lower()] = v.strip()
        return out, cookies

    def dir_headers(self):
        return self._headers_file()[0]

    def dir_cookies(self):
        return self._headers_file()[1]


# ---------------------------------------------------------------- HTML scan
class _FormScan(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = []  # dicts: method, action, hidden names, honeypots [(attrs)]
        self.cur = None
        self.scripts = []
        self.in_script = False

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "form":
            self.cur = {"method": a.get("method", "get").lower(), "action": a.get("action", ""), "tokens": 0,
                        "honeypots": []}
            self.forms.append(self.cur)
        elif tag == "input" and self.cur is not None:
            name = a.get("name", "") + " " + a.get("id", "")
            if a.get("type", "").lower() == "hidden" and TOKEN_FIELD_RE.search(name):
                self.cur["tokens"] += 1
            if HONEYPOT_RE.search(name) or HONEYPOT_RE.search(a.get("class", "")):
                self.cur["honeypots"].append(a)
        elif tag == "meta" and TOKEN_FIELD_RE.search(a.get("name", "")):
            for f in self.forms or []:
                f["tokens"] += 1
            self.meta_token = True
        elif tag == "script":
            self.in_script = True
            self.scripts.append(a.get("src", ""))

    def handle_endtag(self, tag):
        if tag == "form":
            self.cur = None
        elif tag == "script":
            self.in_script = False

    def handle_data(self, data):
        if self.in_script:
            self.scripts.append(data)


# ---------------------------------------------------------------- the checks (ids map to HARDENING_CHECKLIST rows)
def run_checks(site):
    rows = []  # (level, id, message)

    def add(level, cid, msg):
        rows.append((level, cid, msg))

    status, h, cookies, body = site.get("/")
    if status >= 400:
        add("FAIL", "H0", "front page answered %d; nothing else is meaningful until it loads" % status)
        return rows
    https = site.dir is not None or site.scheme == "https"

    # H13 security headers
    if site.dir is None and site.scheme == "https":
        add("PASS" if "strict-transport-security" in h else "FAIL", "H13.hsts",
            "Strict-Transport-Security %s" % ("set" if "strict-transport-security" in h else "missing"))
    elif site.dir is None:
        add("WARN", "H13.https", "plain http target (fine for local dev; production must be https + HSTS)")
    csp = h.get("content-security-policy", "")
    add("PASS" if csp else "FAIL", "H13.csp", "Content-Security-Policy %s" % ("set" if csp else "missing"))
    if csp and ("'unsafe-inline'" in csp and "script-src" in csp):
        add("WARN", "H13.csp-inline", "CSP allows 'unsafe-inline' scripts")
    add("PASS" if h.get("x-content-type-options", "").lower() == "nosniff" else "FAIL", "H13.nosniff",
        "X-Content-Type-Options nosniff %s" % ("set" if h.get("x-content-type-options") else "missing"))
    framing = "frame-ancestors" in csp or "x-frame-options" in h
    add("PASS" if framing else "FAIL", "H13.framing", "clickjacking guard (frame-ancestors / X-Frame-Options) %s"
        % ("set" if framing else "missing"))
    add("PASS" if "referrer-policy" in h else "WARN", "H13.referrer",
        "Referrer-Policy %s" % ("set" if "referrer-policy" in h else "missing"))
    add("PASS" if "permissions-policy" in h else "WARN", "H13.permissions",
        "Permissions-Policy %s" % ("set" if "permissions-policy" in h else "missing"))

    # H15 banners
    server = h.get("server", "")
    if VERSION_RE.search(server):
        add("FAIL", "H15.server", "Server header leaks a version: %r" % server)
    if "x-powered-by" in h:
        add("FAIL", "H15.powered-by", "X-Powered-By leaks the stack: %r" % h["x-powered-by"])
    if not VERSION_RE.search(server) and "x-powered-by" not in h:
        add("PASS", "H15", "no version banner")

    # H14 cookies
    for c in cookies:
        name = c.split("=", 1)[0].strip()
        low = c.lower()
        missing = [f for f, ok in (("Secure", "secure" in low or not https),
                                   ("HttpOnly", "httponly" in low),
                                   ("SameSite", "samesite" in low)) if not ok]
        add("FAIL" if missing else "PASS", "H14.cookie",
            "cookie %s %s" % (name, ("missing " + ", ".join(missing)) if missing else "flags ok"))

    # H11 vendor header present: noted, never credited
    vend = [v for v in VENDOR_HEADERS if v in h]
    if vend:
        add("WARN", "H11", "bot-manager header(s) %s present: camofox detects vendors by header; verify they "
            "actually challenge abusive rates on YOUR routes (not credited as a defense)" % ", ".join(vend))

    # H16 forms / honeypots / H1 fingerprint gates
    scan = _FormScan()
    try:
        scan.feed(body)
    except Exception:
        pass
    posts = [f for f in scan.forms if f["method"] == "post"]
    for f in posts:
        add("PASS" if f["tokens"] else "FAIL", "H16.csrf", "POST form action=%r %s" % (
            f["action"] or "(self)", "has a token-like field" if f["tokens"] else "has no CSRF token-like field"))
    for f in scan.forms:
        for hp in f["honeypots"]:
            ok = hp.get("aria-hidden", "") == "true" and hp.get("tabindex", "") == "-1"
            add("PASS" if ok else "FAIL", "FAIR.honeypot",
                "honeypot field %r %s" % (hp.get("name", "?"), "is hidden from screen readers and keyboards" if ok
                                          else "is reachable by screen readers/keyboards (needs aria-hidden=\"true\" "
                                               "and tabindex=\"-1\"); it would trap assistive-tech users"))
    js = "\n".join(scan.scripts)
    if "navigator.webdriver" in js:
        add("WARN", "H1", "page script reads navigator.webdriver: all three held tools hide it; do not gate on it")
    if re.search(r"fingerprintjs|fpjs|canvas\.toDataURL|getParameter\(\s*37445", js, re.I):
        add("WARN", "H2", "page script fingerprints the browser: camofox/invisible_dots spoof these at engine "
            "level; use as one weak score input, never a gate")

    # H7/H8 robots and sitemap
    rs, _, _, robots = site.get("/robots.txt")
    if rs >= 400 or not robots.strip():
        add("WARN", "H7.robots", "no robots.txt: Maxun proceeds 'without restrictions' when none is found; publish "
            "one with Crawl-delay (courtesy only, never access control)")
    else:
        add("PASS" if re.search(r"(?im)^\s*crawl-delay\s*:", robots) else "WARN", "H7.crawl-delay",
            "robots.txt %s Crawl-delay (Maxun honours it when present)" % (
                "has" if re.search(r"(?im)^\s*crawl-delay\s*:", robots) else "has no"))
        leaked = [m.group(0) for line in robots.splitlines() if line.lower().startswith("disallow")
                  for m in [SENSITIVE_PATH_RE.search(line)] if m]
        if leaked:
            add("WARN", "H7.advertises", "robots.txt Disallow lines name sensitive paths (%s): robots.txt is public; "
                "protect them with auth, and consider not listing them" % ", ".join(sorted(set(leaked))[:5]))
    ss, _, _, sitemap = site.get("/sitemap.xml")
    if ss < 400 and sitemap.strip():
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", sitemap)
        bad = [u for u in locs if SENSITIVE_PATH_RE.search(urllib.parse.urlsplit(u).path + "?" +
                                                           urllib.parse.urlsplit(u).query)]
        add("FAIL" if bad else "PASS", "H8.sitemap", "sitemap.xml %s" % (
            "lists private-looking URLs Maxun's crawler would harvest: " + ", ".join(bad[:5]) if bad
            else "lists %d URL(s), none private-looking" % len(locs)))

    # H3 rate limiting (URL targets only; a bounded honest burst)
    if site.dir is None:
        limited, advertised, retry_ok = False, False, True
        for _ in range(BURST):
            st, hh, _, _ = site.get("/")
            if any(k in hh for k in ("ratelimit-limit", "x-ratelimit-limit", "ratelimit-policy", "ratelimit")):
                advertised = True
            if st == 429:
                limited = True
                retry_ok = "retry-after" in hh
                break
        if limited and not retry_ok:
            add("FAIL", "H3.retry-after", "answered 429 without Retry-After: honest clients cannot back off")
        elif limited:
            add("PASS", "H3", "rate limit answered 429 with Retry-After inside a %d-request burst" % BURST)
        elif advertised:
            add("PASS", "H3", "rate-limit headers advertised (RateLimit-*)")
        else:
            add("WARN", "H3", "no rate-limit signal in a %d-request burst on /: per-IP limits alone are defeated by "
                "camofox residential rotation; confirm login/sign-up/reset limits per account and email domain "
                "server-side (RATE_LIMITING.md)" % BURST)
    return rows


def report(site, rows):
    fails = [r for r in rows if r[0] == "FAIL"]
    warns = [r for r in rows if r[0] == "WARN"]
    print("%s: %d violation(s) %s %d worklist %s denominator %d" % (NAME, len(fails), SEP, len(warns), SEP, len(rows)))
    print("  target owned: %s" % site.reason + ("" if site.dir is not None else
                                                 " %s %d request(s) made" % (SEP, site.requests)))
    for level, cid, msg in rows:
        print("  %-4s %-16s %s" % (level, cid, msg))
    return 1 if fails else 0


def scan_target(target, owned_file, fetch=default_fetch):
    hosts, bad = read_owned(owned_file)
    for b in bad:
        print("  WARN owned-file " + b)
    site = Site(target, hosts, fetch)
    return site, run_checks(site)


# ---------------------------------------------------------------- audit row
def check(root):
    root = Path(root)
    viol, work = [], []
    hosts, bad = read_owned(root / OWNED_FILE)
    viol += bad
    for h in hosts:
        if BROKER_RE.search(h):
            viol.append("%s lists %s, a broker/exchange-looking host: out of scope (DEC-quarantine-0006)" % (OWNED_FILE, h))
    # absent OWNED.txt = empty list: loopback and local builds only (main and a fresh station have none)
    for f in PACK_FILES:
        if not (root / PACK_DIR / f).is_file():
            viol.append("%s/%s missing" % (PACK_DIR.as_posix(), f))
    pack = root / PACK_DIR / "PACK.md"
    if pack.is_file():
        t = pack.read_text(encoding="utf-8")
        for needle in ("Evasion tooling never leaves quarantine", "Own targets only", "No broker/exchange"):
            if needle not in t:
                viol.append("%s/PACK.md lost the rail %r" % (PACK_DIR.as_posix(), needle))
    src = Path(__file__).read_text(encoding="utf-8")
    if re.search(r"^\s*(import|from)\s+(playwright|camoufox|selenium|puppeteer|undetected)", src, re.M) or \
            re.search(r"upstream/(jo-inc|getmaxun|feder-cr)", src.split("# ---------------------------------------------------------------- selftest")[0]):
        viol.append("self_check.py imports or references a held tree: evasion tooling never leaves quarantine")
    denom = len(PACK_FILES) + 2 + len(hosts)
    print("%s: %d violation(s) %s %d worklist %s denominator %d" % (NAME, len(viol), SEP, len(work), SEP, denom))
    for v in viol:
        print("  VIOLATION " + v)
    return 1 if viol else 0


# ---------------------------------------------------------------- selftest
def _serve(directory, rate_limit_after=None, retry_after=True):
    """A synthetic fixture site on 127.0.0.1: serves `directory`, headers from its `_headers` file."""
    import http.server
    import functools

    hits = {"n": 0}

    class H(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def end_headers(self):
            site = Site(str(directory), [])
            for k, v in site.dir_headers().items():
                self.send_header(k, v)
            for c in site.dir_cookies():
                self.send_header("Set-Cookie", c)
            super().end_headers()

        def version_string(self):
            hdrs = Site(str(directory), []).dir_headers()
            return hdrs.get("x-fixture-server", "fixture")

        def do_GET(self):
            if self.path == "/" and rate_limit_after is not None:
                hits["n"] += 1
                if hits["n"] > rate_limit_after:
                    self.send_response(429)
                    if retry_after:
                        self.send_header("Retry-After", "30")
                    self.send_header("Content-Length", "0")
                    super(H, self).end_headers()
                    return
            return super().do_GET()

    handler = functools.partial(H, directory=str(directory))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, "http://127.0.0.1:%d/" % srv.server_address[1]


def selftest():
    import contextlib
    import io

    cases = []

    def case(name, ok):
        cases.append((name, bool(ok)))

    def quiet(fn, *a, **k):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            r = fn(*a, **k)
        return r, buf.getvalue()

    def never_fetch(url, method="GET"):
        raise AssertionError("a request was made to %s" % url)

    with tempfile.TemporaryDirectory() as td:
        empty_owned = Path(td) / "OWNED.txt"
        empty_owned.write_text("# none\n")
        owned = Path(td) / "OWNED2.txt"
        owned.write_text("shop.example.org\n*.mine.example\ntrade.coinbase.com\nnot a host/path\n")

        # (1) REFUSAL BY DEFAULT: a non-owned host is refused before any request is made.
        for target in ("https://example.com/", "http://93.184.216.34/", "https://www.google.com/login",
                       "http://192.168.1.10/", "http://localhost.example.com/"):
            try:
                Site(target, read_owned(empty_owned)[0], never_fetch).get("/")
                case("refuse non-owned %s" % target, False)
            except Refused:
                case("refuse non-owned %s" % target, True)
            except AssertionError:
                case("refuse non-owned %s (request made!)" % target, False)
        # CLI exit code 3 on refusal, no request
        rc, out = quiet(main, ["https://example.com/", "--owned-file", str(empty_owned)])
        case("cli exit 3 on non-owned", rc == 3 and "REFUSED" in out)
        # (2) broker/exchange refused even when listed as owned
        hosts, bad = read_owned(owned)
        case("owned file parses 3 hosts, flags 1 bad line", len(hosts) == 3 and len(bad) == 1)
        try:
            Site("https://trade.coinbase.com/", hosts, never_fetch)
            case("refuse listed broker host", False)
        except Refused as e:
            case("refuse listed broker host", "broker" in str(e))
        # (3) owned-list hosts and wildcard accepted (no request made at construction)
        case("accept listed host", Site("https://shop.example.org/", hosts, never_fetch).reason.startswith("listed"))
        case("accept wildcard host", Site("https://a.mine.example/", hosts, never_fetch).reason.startswith("listed"))
        case("refuse wildcard apex mismatch", _refused(lambda: Site("https://evilmine.example/", hosts, never_fetch)))
        # (4) a redirect to a non-owned host is refused mid-flight
        def redirector(url, method="GET"):
            return 302, {"location": "https://example.com/"}, [], ""
        case("refuse redirect off-site", _refused(lambda: Site("https://shop.example.org/", hosts, redirector).get("/")))
        case("refuse non-http scheme", _refused(lambda: Site("file:///etc/passwd", hosts, never_fetch)))

        # (5) PLANTED-DEFECT fixture site on loopback
        defective = FIXTURES / "defective"
        clean = FIXTURES / "clean"
        srv, url = _serve(defective)
        try:
            site, rows = quiet(scan_target, url, empty_owned)[0]
        finally:
            srv.shutdown()
        ids = {(lvl, cid) for lvl, cid, _ in rows}
        for planted in ("H13.csp", "H13.nosniff", "H13.framing", "H15.powered-by", "H15.server", "H14.cookie",
                        "H16.csrf", "FAIR.honeypot", "H8.sitemap"):
            case("defective fixture FAILs %s" % planted, ("FAIL", planted) in ids)
        for planted in ("H1", "H2", "H7.crawl-delay", "H7.advertises", "H3", "H11"):
            case("defective fixture WARNs %s" % planted, ("WARN", planted) in ids)
        case("defective fixture made <= %d requests" % (BURST + 3), site.requests <= BURST + 3)
        rc, _ = quiet(report, site, rows)
        case("defective fixture exit 1", rc == 1)

        srv, url = _serve(clean, rate_limit_after=2)
        try:
            site, rows = quiet(scan_target, url, empty_owned)[0]
        finally:
            srv.shutdown()
        fails = [r for r in rows if r[0] == "FAIL"]
        case("clean fixture has no FAIL (%s)" % fails, not fails)
        case("clean fixture sees 429+Retry-After", ("PASS", "H3") in {(a, b) for a, b, _ in rows})
        rc, _ = quiet(report, site, rows)
        case("clean fixture exit 0", rc == 0)

        srv, url = _serve(clean, rate_limit_after=1, retry_after=False)
        try:
            site, rows = quiet(scan_target, url, empty_owned)[0]
        finally:
            srv.shutdown()
        case("429 without Retry-After FAILs", ("FAIL", "H3.retry-after") in {(a, b) for a, b, _ in rows})

        # (6) local-directory mode makes no request and still sees the planted defects
        site, rows = quiet(scan_target, str(defective), empty_owned)[0]
        dids = {(a, b) for a, b, _ in rows}
        case("dir mode FAILs H16.csrf and H8.sitemap", ("FAIL", "H16.csrf") in dids and ("FAIL", "H8.sitemap") in dids)
        case("dir mode is owned", site.reason == "local directory")

        # (7) audit row: planted broker host in OWNED.txt turns check red; a clean root is green
        root = Path(td) / "root"
        (root / "work" / "protection").mkdir(parents=True)
        (root / PACK_DIR).mkdir(parents=True)
        for f in PACK_FILES:
            src = Path(__file__).resolve().parents[2] / PACK_DIR / f
            (root / PACK_DIR / f).write_text(src.read_text(encoding="utf-8") if src.is_file() else
                                                 "Evasion tooling never leaves quarantine. Own targets only. "
                                                 "No broker/exchange.\n")
        (root / OWNED_FILE).write_text("# none\n")
        rc, _ = quiet(check, root)
        case("check green on clean root", rc == 0)
        (root / OWNED_FILE).write_text("app.binance.com\n")
        rc, out = quiet(check, root)
        case("check red on broker host in OWNED.txt", rc == 1 and "broker" in out)
        (root / OWNED_FILE).write_text("# none\n")
        (root / OWNED_FILE).unlink()
        rc, _ = quiet(check, root)
        case("check green when OWNED.txt is absent (empty list)", rc == 0)
        (root / PACK_DIR / "PACK.md").write_text("rails removed\n")
        rc, _ = quiet(check, root)
        case("check red when PACK.md loses its rails", rc == 1)

    bad = [n for n, ok in cases if not ok]
    for n in bad:
        print("  FAIL " + n)
    if bad:
        print("selftest FAILED (%d of %d cases)" % (len(bad), len(cases)))
        return 1
    print("selftest OK (%d cases)" % len(cases))
    return 0


def _refused(fn):
    try:
        fn()
        return False
    except Refused:
        return True


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "--selftest":
        return selftest()
    if argv and argv[0] == "check":
        ap = argparse.ArgumentParser(prog="self_check.py check")
        ap.add_argument("--root", default=".")
        a = ap.parse_args(argv[1:])
        return check(a.root)
    ap = argparse.ArgumentParser(prog="self_check.py", description="exposure report for a site YOU OWN")
    ap.add_argument("target", help="http(s) URL of a site you own, or a local directory (static build)")
    ap.add_argument("--owned-file", default=str(OWNED_FILE), help="hosts you own, one per line (default %(default)s)")
    try:
        a = ap.parse_args(argv)
    except SystemExit:
        return 2
    try:
        site, rows = scan_target(a.target, a.owned_file)
    except Refused as e:
        print("%s: REFUSED %s %s" % (NAME, SEP, e))
        return 3
    except (urllib.error.URLError, OSError) as e:
        print("%s: unreachable %s %s" % (NAME, SEP, e))
        return 2
    return report(site, rows)


if __name__ == "__main__":
    sys.exit(main())
