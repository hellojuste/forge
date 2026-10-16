#!/usr/bin/env python3
"""setup_tool.py -- one command per forge tool: prerequisites, pin, run tree, install AT the pin, telemetry off, keys, smoke.

owner: STATION.md#Set up a tool . station forge (station-only; stdlib only)

  setup_tool.py <rea|evo|openwiki|projectatlas|--all> [--dry-run] [--remove]
  setup_tool.py --check <tool>     exit 0 only when the tool is ready at its pin (a workflow's start check);
                                   otherwise prints the one setup command and exits 1
  setup_tool.py --list             one status line per tool
  setup_tool.py --selftest         stub installers on a fake PATH, a fixture kit and remote; no network

One run, per tool:
  (a) prerequisites: each missing one prints the exact Windows / Git Bash install line (and the Linux/macOS one
      when not on Windows); nothing is installed on the host by this tool;
  (b) the pin: tools/kit/bootstrap.py <owner~repo> (bare clone at the registry sha);
  (c) the run tree OUTSIDE the station: tools/kit/runtree.py <owner~repo> --workspace (kit floor hooks wired);
  (d) the install INSIDE the run tree, under <tree>/.kit-tool/, at the version the pin's own manifest names
      (package.json / pyproject.toml / Cargo.toml read from the run tree), by the tool's documented route;
  (e) telemetry: the opt-out env + config file each tool's source reads (file:line in TOOLS below), written into
      <tree>/.kit-tool/kit-bin/<cli> (a wrapper named after the CLI, so act_gate matches it) and the tool's home dir (kept inside the run tree);
  (f) LLM keys: the wrapper exports the NAMES the tool reads from the station .env at run time; values are never
      printed and never copied out of .env;
  (g) smoke: the version probe (must equal the pin's version, else refused) plus one harmless offline command.
Idempotent: a tool already installed at its pin prints `ready`. --remove deletes <tree>/.kit-tool and the run tree.
Never runs: `rea setup|update|analyze-*`, `evo install|telemetry on|off|ship`, `openwiki integrations|auth|ingest`,
`projectatlas init` (they write host agent configs or send; act_gate asks for them, station.json irreversible_acts).

Earned by: operator order 2026-10-16 "forge -- one-step setup for rea, evo, openwiki and ProjectAtlas" (the manual
bootstrap -> runtree -> install sequence was three tools and a README per CLI). Retires: hand installs per README.
Exit: 0 ready · 1 refused (missing prerequisite, wrong version, failed step) · 2 usage.
"""
import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT_GUESS = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT_GUESS, "tools", "kit"))
import _kit  # noqa: E402
import bootstrap  # noqa: E402
import runtree  # noqa: E402

STATION = "forge"
PREFIX = ".kit-tool"
STATE = "setup.json"
SELF = "python3 tools/station/setup_tool.py"

# ---------------------------------------------------------------- prerequisites (exact install lines)
# win: Windows 11 + Git Bash (winget ships with Windows 11); posix: printed in addition off Windows.
PREREQS = {
    "git": {"exe": ["git"], "win": "winget install --id Git.Git -e", "posix": "sudo apt-get install -y git"},
    "node": {"exe": ["node"], "win": "winget install --id OpenJS.NodeJS -e   (then reopen Git Bash; node >= 22.22 covers rea and openwiki)",
             "posix": "curl -fsSL https://fnm.vercel.app/install | bash && fnm install 22"},
    "npm": {"exe": ["npm"], "win": "winget install --id OpenJS.NodeJS -e   (npm ships with node)",
            "posix": "npm ships with node (see node)"},
    "python": {"exe": ["python3", "python", "py"], "win": "winget install --id Python.Python.3.12 -e",
               "posix": "sudo apt-get install -y python3 python3-venv"},
    "uv": {"exe": ["uv"], "win": "powershell -ExecutionPolicy ByPass -c \"irm https://astral.sh/uv/install.ps1 | iex\"   (or: winget install --id astral-sh.uv -e)",
           "posix": "curl -LsSf https://astral.sh/uv/install.sh | sh"},
    "pip": {"exe": ["pip3", "pip"], "win": "py -3.12 -m ensurepip --upgrade",
            "posix": "python3 -m ensurepip --upgrade"},
    "cargo": {"exe": ["cargo"], "win": "winget install --id Rustlang.Rustup -e && rustup default stable   "
                                       "(the MSVC linker: winget install --id Microsoft.VisualStudio.2022.BuildTools -e "
                                       "--override \"--add Microsoft.VisualStudio.Workload.VCTools --includeRecommended --passive\")",
              "posix": "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y"},
}

# ---------------------------------------------------------------- the four tools (evidence at the registry pin)
TOOLS = {
    "rea": {
        "key": "morluto~rea",
        "cli": "rea",
        "manifest": ("package.json", "json:version"),          # package.json:4 "6.5.0" at 1bd5c5c
        "package": "rea-agents",                               # package.json:2; bins rea + rea-agents :40-43
        "node_range": [((22, 19, 0), (23, 0, 0)), ((24, 11, 0), (25, 0, 0)), ((26, 0, 0), None)],  # engines :45
        "routes": ["npm"],
        "version_args": ["--version"],                         # src/cli.ts:88-89 (incur Cli.create version)
        "smoke_args": ["--help"],                              # README.md:117 `rea --help`
        "telemetry_env": {"DO_NOT_TRACK": "1"},
        "telemetry_note": "no sender in src/, scripts/, bridge/, native/ at the pin (grep telemetry|posthog|sentry|analytics|"
                          "mixpanel|update-notifier); update check only in the explicit `rea update` "
                          "(src/application/UpdateRuntime.ts:198-207), which act_gate asks for",
        "key_names": [],                                       # REA drives no LLM itself (no *_API_KEY read in src/)
        "home_env": {},
        "home_files": {},
        "run_hint": "rea --help · rea doctor --json (read-only, docs/installation.md:353) · analyses go through workflow reverse (legal gate)",
    },
    "evo": {
        "key": "evo-hq~evo",
        "cli": "evo",
        "manifest": ("plugins/evo/pyproject.toml", "toml:version"),  # pyproject.toml:3 "0.8.0" at c70c04b
        "package": "evo-hq-cli",                               # pyproject.toml:2; console script evo :58-61
        "routes": ["uv", "pip"],                               # README.md:73 `uv tool install evo-hq-cli`
        "version_args": ["--version"],                         # cli.py:6118-6120 -> "evo-hq-cli 0.8.0"
        "smoke_args": ["telemetry", "status", "--json"],       # cli.py:598-604 + telemetry.py:130-150 (local read)
        "telemetry_env": {"EVO_TELEMETRY": "0", "DO_NOT_TRACK": "1", "EVO_SKIP_VERSION_CHECK": "1"},
        "telemetry_note": "telemetry.py:105-111 env_forces_off (EVO_TELEMETRY 0/false/off/no or DO_NOT_TRACK 1/true/yes); "
                          "telemetry.py:123 settings enabled:false in $EVO_HOME/telemetry.json; version_check.py:104 "
                          "EVO_SKIP_VERSION_CHECK skips the PyPI GET; never `evo telemetry off` (telemetry.py:445-455 sends a final event)",
        "key_names": [],                                       # no *_API_KEY read in plugins/evo/src (host agent's model)
        "key_names_optional": ["E2B_API_KEY", "DAYTONA_API_KEY", "EVO_SANDBOX_BEARER_TOKEN"],  # dashboard.py:219-231, manual.py:51
        "home_env": {"EVO_HOME": "{home}"},                    # user_defaults.py:38-60
        "home_files": {"telemetry.json": "{\"enabled\": false}\n"},
        "run_hint": "evo --help · evo telemetry status · runs go through workflow optimize-loop (holdout first)",
    },
    "openwiki": {
        "key": "langchain-ai~openwiki",
        "cli": "openwiki",
        "manifest": ("package.json", "json:version"),          # package.json:3 "0.7.2" at 7c469e5
        "package": "openwiki",                                 # package.json:2; bin openwiki :10-11; README.md:43
        "node_range": [((22, 22, 0), None)],                   # engines :7-8
        "routes": ["npm"],
        "version_args": None,                                  # no --version flag (src/cli/commands.ts:233); read the installed package.json
        "smoke_args": ["--help"],                              # src/cli/commands.ts:233-234
        "telemetry_env": {"OPENWIKI_TELEMETRY_DISABLED": "1", "DO_NOT_TRACK": "1", "LANGCHAIN_TRACING_V2": "false"},
        "telemetry_note": "src/telemetry/gates.ts:28-32,84-90 (truthy OPENWIKI_TELEMETRY_DISABLED or DO_NOT_TRACK); "
                          "senders.ts:136-142 returns before the PostHog send (config.ts:13 us.i.posthog.com); CI runs still "
                          "send (gates.ts:41-58) so the opt-out is always set; LangSmith tracing off (env.ts:178-180)",
        "key_names": ["ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "TAVILY_API_KEY"],  # constants.ts:16,44,46,133; env.ts:109-181
        "home_env": {"OPENWIKI_CONFIG_DIR": "{home}"},         # src/config/openwiki-home.ts:6-14
        "home_files": {".env": "# GENERATED by tools/station/setup_tool.py -- telemetry only; keys come from the station .env via kit-bin/openwiki\n"
                               "OPENWIKI_TELEMETRY_DISABLED=1\nLANGCHAIN_TRACING_V2=false\n"},  # env.ts:88-89 <home>/.env
        "run_hint": "openwiki --help · wikis go through workflow wiki-gen (target check + review)",
    },
    "projectatlas": {
        "key": "styler-ai~ProjectAtlas",
        "cli": "projectatlas",                                 # crates/projectatlas-cli/Cargo.toml:10-13 [[bin]] projectatlas
        "manifest": ("Cargo.toml", "toml:workspace.package.version"),  # Cargo.toml:13-14 "0.5.0-rc3" at bed8ba3
        "package": "projectatlas-cli",
        "routes": ["cargo", "release"],                        # README.md:50 cargo install ... projectatlas-cli --locked
        "version_args": ["--version"],
        "smoke_args": ["runtime-info"],                        # main.rs:1365-1366, 3118-3120 (no DB use)
        "telemetry_env": {"PROJECTATLAS_NO_TELEMETRY": "1", "DO_NOT_TRACK": "1"},
        "telemetry_note": "local only: core/src/telemetry.rs + db/src/telemetry.rs are token accounting in the project SQLite DB "
                          "(no std::net, no HTTP crate in Cargo.toml); PROJECTATLAS_NO_TELEMETRY 1/true/yes/on skips even the "
                          "local writes (crates/projectatlas-cli/src/runtime.rs:3608-3610, main.rs:4034-4040)",
        "release": {"url": "https://github.com/styler-ai/ProjectAtlas/releases/download/{tag}/{asset}",
                    "sums": "https://github.com/styler-ai/ProjectAtlas/releases/download/{tag}/SHA256SUMS",
                    "asset": {"windows": "projectatlas-{tag}-x86_64-pc-windows-msvc.zip",        # release.yml:473
                              "linux": "projectatlas-{tag}-x86_64-unknown-linux-gnu.tar.gz",     # release.yml:238,309
                              "darwin": "projectatlas-{tag}-x86_64-apple-darwin.tar.gz"},
                    "member": "projectatlas/projectatlas"},                                     # release.yml:310-311,474-475
        "key_names": [],                                       # local index; no API key named at the pin
        "home_env": {},
        "home_files": {},
        "run_hint": "projectatlas --help · trials go through workflow trial-run; arch-review / intake-run use it read-only",
    },
}
ORDER = ["rea", "evo", "openwiki", "projectatlas"]
NEEDS = {"npm": ["node", "npm"], "uv": ["python", "uv"], "pip": ["python", "pip"], "cargo": ["cargo"], "release": []}


def is_windows():
    return os.name == "nt" or bool(os.environ.get("MSYSTEM"))


# ---------------------------------------------------------------- small readers
def read_version(tree, spec):
    path, how = spec
    p = os.path.join(tree, path)
    with open(p, encoding="utf-8") as f:
        text = f.read()
    kind, dotted = how.split(":", 1)
    if kind == "json":
        return str(json.loads(text)[dotted])
    want = dotted.split(".")
    section, key = ".".join(want[:-1]), want[-1]
    cur = ""
    for line in text.splitlines():
        s = line.strip()
        m = re.match(r"^\[([^\]]+)\]$", s)
        if m:
            cur = m.group(1).strip()
            continue
        m = re.match(r'^%s\s*=\s*"([^"]+)"' % re.escape(key), s)
        if m and (cur == section if section else cur in ("project", "package")):
            return m.group(1)
    raise ValueError("no %s in %s" % (dotted, path))


def parse_node_version(text):
    m = re.search(r"v?(\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(x) for x in m.groups()) if m else None


def node_ok(v, ranges):
    return any(v >= lo and (hi is None or v < hi) for lo, hi in ranges)


def fmt_range(ranges):
    return " || ".join(">=%s%s" % (".".join(map(str, lo)), (" <%s" % ".".join(map(str, hi))) if hi else "") for lo, hi in ranges)


class Ctx:
    """Where things are and how commands run; the selftest swaps PATH, the run root and the kit root."""

    def __init__(self, root, run_root=None, path=None, log=print, station_root=None, windows=None):
        self.root = os.path.abspath(root)
        self.station_root = os.path.abspath(station_root or root)
        self.rr = runtree.run_root(run_root)
        self.path = path if path is not None else os.environ.get("PATH", "")
        self.log = log
        self.windows = is_windows() if windows is None else windows
        self.fetcher = None  # None = urllib; the selftest plants a fixture release

    def which(self, names):
        for n in names:
            w = shutil.which(n, path=self.path)
            if w:
                return w
        return None

    def env(self, extra=None):
        e = dict(os.environ)
        e["PATH"] = self.path
        e.update(extra or {})
        return e

    def run(self, argv, cwd=None, extra_env=None):
        try:
            p = subprocess.run(argv, cwd=cwd, env=self.env(extra_env), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        except OSError as e:
            return 127, str(e)
        return p.returncode, p.stdout.decode("utf-8", "replace")


def pin_of(ctx, key):
    src = {s["key"]: s for s in _kit.read_json(os.path.join(ctx.root, "registry", "sources.json"))["sources"]}
    if key not in src:
        raise KeyError("not a registry key: %s" % key)
    return src[key]


def tree_of(ctx, key, sha):
    return runtree.tree_path(ctx.rr, runtree.station_for(ctx.root, key, STATION), key, sha)


def layout(ctx, name, sha):
    t = TOOLS[name]
    tree = tree_of(ctx, t["key"], sha)
    pre = os.path.join(tree, PREFIX)
    return tree, pre, os.path.join(pre, "home")


def bin_path(ctx, pre, cli, route):
    exe = ".exe" if ctx.windows else ""
    if route == "npm":
        return os.path.join(pre, "node_modules", ".bin", cli + (".cmd" if ctx.windows else ""))
    if route == "pip":
        return os.path.join(pre, "venv", "Scripts" if ctx.windows else "bin", cli + exe)
    return os.path.join(pre, "bin", cli + exe)  # uv (UV_TOOL_BIN_DIR), cargo (--root), release


def read_state(pre):
    p = os.path.join(pre, STATE)
    try:
        return _kit.read_json(p)
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------- (a) prerequisites
def missing_prereqs(ctx, name, route):
    out = []
    for need in ["git"] + NEEDS[route]:
        if not ctx.which(PREREQS[need]["exe"]):
            out.append(need)
    t = TOOLS[name]
    if route == "npm" and "node" not in out and t.get("node_range"):
        rc, txt = ctx.run([ctx.which(["node"]), "--version"])
        v = parse_node_version(txt)
        if rc != 0 or v is None or not node_ok(v, t["node_range"]):
            out.append("node-version:%s:%s" % (".".join(map(str, v)) if v else "?", fmt_range(t["node_range"])))
    return out


def instruction(ctx, need):
    if need.startswith("node-version:"):
        _, have, want = need.split(":", 2)
        return "node %s found, %s needs %s -> %s" % (have, "this tool", want, PREREQS["node"]["win"])
    p = PREREQS[need]
    line = "missing %s -> Windows/Git Bash: %s" % (need, p["win"])
    if not ctx.windows:
        line += "  ·  Linux/macOS: %s" % p["posix"]
    return line


def pick_route(ctx, name, release_asset=None):
    """First route whose prerequisites are present; the release route only when the pin publishes an asset."""
    misses = {}
    for r in TOOLS[name]["routes"]:
        if r == "release":
            if release_asset:
                return r, {}
            misses[r] = ["release:none"]
            continue
        m = missing_prereqs(ctx, name, r)
        if not m:
            return r, {}
        misses[r] = m
    return None, misses


# ---------------------------------------------------------------- (d) install routes
def install_cmds(ctx, name, route, tree, pre, version):
    t = TOOLS[name]
    if route == "npm":
        return [([ctx.which(["npm"]), "install", "--prefix", pre, "--no-audit", "--no-fund", "--loglevel=error",
                  "%s@%s" % (t["package"], version)], tree, {})]
    if route == "uv":
        env = {"UV_TOOL_DIR": os.path.join(pre, "uv-tools"), "UV_TOOL_BIN_DIR": os.path.join(pre, "bin"),
               "UV_PYTHON_PREFERENCE": "system"}
        return [([ctx.which(["uv"]), "tool", "install", "--force", "%s==%s" % (t["package"], version)], tree, env)]
    if route == "pip":
        py = ctx.which(PREREQS["python"]["exe"])
        venv_py = os.path.join(pre, "venv", "Scripts" if ctx.windows else "bin", "python" + (".exe" if ctx.windows else ""))
        return [([py, "-m", "venv", os.path.join(pre, "venv")], tree, {}),
                ([venv_py, "-m", "pip", "install", "--disable-pip-version-check", "-q", "%s==%s" % (t["package"], version)], tree, {})]
    if route == "cargo":
        # the run tree IS the pin: build its own crate with its lockfile (README.md:50 uses --git --tag; --path is the same crate at the exact sha)
        return [([ctx.which(["cargo"]), "install", "--locked", "--path", os.path.join(tree, "crates", t["package"]),
                  "--root", pre], tree, {"CARGO_TARGET_DIR": os.path.join(pre, "target")})]
    return []


def release_asset_for(ctx, name, sha):
    """A prebuilt binary only when a release tag points exactly at the pin (ProjectAtlas release.yml publishes per tag)."""
    t = TOOLS[name]
    bare = bootstrap.bare_path(ctx.root, t["key"])
    # bootstrap fetches --no-tags; the release tags are fetched here (small refs; offline -> no tag, a clear refusal)
    _kit.run(["git", "-C", bare, "fetch", "-q", "origin", "+refs/tags/*:refs/tags/*"], check=False)
    p = _kit.run(["git", "-C", bare, "tag", "--points-at", sha], check=False)
    tags = [x for x in p.out.split() if x.startswith("v")]
    return tags[0] if tags else None


def fetch(url):
    """Bytes at url (stdlib; HTTPS_PROXY honoured). The selftest swaps this for a fixture reader."""
    import urllib.request
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.read()


def install_release(ctx, name, tag, pre, fetcher=None):
    """Download the pin's own release archive, check it against the release SHA256SUMS, unpack the binary to <pre>/bin."""
    import hashlib
    import io
    import tarfile
    import zipfile
    rel = TOOLS[name]["release"]
    plat = "windows" if ctx.windows else ("darwin" if sys.platform == "darwin" else "linux")
    asset = rel["asset"][plat].format(tag=tag)
    get = fetcher or fetch
    try:
        blob = get(rel["url"].format(tag=tag, asset=asset))
        sums = get(rel["sums"].format(tag=tag)).decode("utf-8", "replace")
    except Exception as e:  # network, 404, proxy: all are a refusal with the reason
        return False, "download of %s failed (%s)" % (asset, e)
    want = [l.split()[0] for l in sums.splitlines() if l.strip().endswith(asset)]
    have = hashlib.sha256(blob).hexdigest()
    if not want or want[0].lower() != have:
        return False, "sha256 of %s is %s, SHA256SUMS says %s" % (asset, have, want[0] if want else "nothing")
    member = rel["member"] + (".exe" if ctx.windows else "")
    dest = os.path.join(pre, "bin", os.path.basename(member))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    try:
        if asset.endswith(".zip"):
            data = zipfile.ZipFile(io.BytesIO(blob)).read(member)
        else:
            data = tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz").extractfile(member).read()
    except (KeyError, OSError, zipfile.BadZipFile, tarfile.TarError, AttributeError) as e:
        return False, "%s has no %s (%s)" % (asset, member, e)
    with open(dest, "wb") as f:
        f.write(data)
    os.chmod(dest, 0o755)
    return True, "%s sha256 %s" % (asset, have[:12])


def nearest_tag(ctx, name, sha):
    bare = bootstrap.bare_path(ctx.root, TOOLS[name]["key"])
    p = _kit.run(["git", "-C", bare, "describe", "--tags", "--contains", sha], check=False)
    tag = p.out.strip().split("~")[0].split("^")[0] if p.returncode == 0 else ""
    return (" (nearest later release: %s; a repin to it via workflow kit-repin would enable the binary)" % tag) if tag else ""


def write_wrapper(ctx, name, pre, binp):
    t = TOOLS[name]
    home = os.path.join(pre, "home")
    # Git Bash reads C:/x/y; npm writes an extensionless sh shim beside each .cmd, and bash execs that one
    gb = (lambda s: s.replace("\\", "/")) if ctx.windows else (lambda s: s)
    q = lambda s: "'" + gb(s).replace("'", "'\\''") + "'"
    target = binp[:-4] if ctx.windows and binp.endswith(".cmd") else binp
    names = t["key_names"] + t.get("key_names_optional", [])
    lines = ["#!/usr/bin/env bash",
             "# GENERATED by tools/station/setup_tool.py -- do not edit; regenerate: %s %s" % (SELF, name),
             "# %s at the pin, telemetry off, LLM keys by NAME from the station .env (values never copied here)." % name,
             "STATION_ENV=%s" % q(os.path.join(ctx.station_root, ".env"))]
    if names:
        lines += ['if [ -f "$STATION_ENV" ]; then',
                  '  while IFS= read -r line || [ -n "$line" ]; do',
                  '    line="${line%$\'\\r\'}"; case "$line" in \'#\'*|\'\') continue;; esac',
                  '    k="${line%%=*}"; v="${line#*=}"',
                  '    case "$k" in %s) [ -n "$v" ] && export "$k=$v";; esac' % "|".join(names),
                  '  done < "$STATION_ENV"',
                  'fi']
    for k, v in sorted(t["home_env"].items()):
        lines.append("export %s=%s" % (k, q(v.format(home=home))))
    # the opt-outs are exported AFTER the .env read, so nothing in .env can switch telemetry back on
    for k, v in sorted(t["telemetry_env"].items()):
        lines.append("export %s=%s" % (k, q(v)))
    lines.append("exec %s \"$@\"" % q(target))
    # named after the CLI, so act_gate's irreversible_acts patterns (`rea analyze-*`, `evo ship`, `openwiki auth`, ...)
    # match a call through the wrapper exactly as they match the bare CLI
    p = wrapper_path(pre, name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(p, os.stat(p).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return p


def wrapper_path(pre, name):
    return os.path.join(pre, "kit-bin", TOOLS[name]["cli"])


def write_home(name, home):
    os.makedirs(home, exist_ok=True)
    for fn, body in TOOLS[name]["home_files"].items():
        with open(os.path.join(home, fn), "w", encoding="utf-8", newline="\n") as f:
            f.write(body)


def tool_env(name, home):
    t = TOOLS[name]
    e = {k: v.format(home=home) for k, v in t["home_env"].items()}
    e.update(t["telemetry_env"])
    return e


def probe_version(ctx, name, pre, binp):
    t = TOOLS[name]
    if t["version_args"] is None:
        pj = os.path.join(pre, "node_modules", t["package"], "package.json")
        try:
            return 0, str(_kit.read_json(pj)["version"])
        except (OSError, ValueError, KeyError) as e:
            return 1, "unreadable %s (%s)" % (pj, e)
    return ctx.run([binp] + t["version_args"], extra_env=tool_env(name, os.path.join(pre, "home")))


def version_matches(out, version):
    return bool(re.search(r"(^|[^0-9A-Za-z.])v?%s([^0-9A-Za-z.-]|$)" % re.escape(version), out.strip()))


def keys_report(ctx, name):
    t = TOOLS[name]
    names = t["key_names"] + t.get("key_names_optional", [])
    if not names:
        return "keys: none read by %s at the pin" % name
    have = {}
    p = os.path.join(ctx.station_root, ".env")
    if os.path.isfile(p):
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                have[k.strip()] = bool(v.strip())
    return "keys (names only, from %s): %s" % (os.path.relpath(p, ctx.station_root) if os.path.isfile(p) else ".env (absent)",
                                               ", ".join("%s=%s" % (n, "set" if have.get(n) else "empty") for n in names))


# ---------------------------------------------------------------- the one command
def status(ctx, name):
    """(state, detail): ready | absent | wrong-version | broken."""
    t = TOOLS[name]
    try:
        sha = pin_of(ctx, t["key"])["sha"]
    except (OSError, ValueError, KeyError) as e:
        return "broken", str(e)
    tree, pre, _ = layout(ctx, name, sha)
    st = read_state(pre)
    if not st:
        return "absent", tree
    if st.get("sha") != sha:
        return "wrong-version", "installed for pin %s, registry pin is %s" % (str(st.get("sha"))[:12], sha[:12])
    binp = st.get("bin", "")
    if not os.path.exists(binp):
        return "broken", "bin missing: %s" % binp
    if not os.path.isfile(wrapper_path(pre, name)):
        return "broken", "wrapper missing: %s" % wrapper_path(pre, name)
    rc, out = probe_version(ctx, name, pre, binp)
    if rc != 0 or not version_matches(out, st.get("version", "?")):
        return "wrong-version", "probe says %r, pin wants %s" % (out.strip()[-120:], st.get("version"))
    return "ready", "%s %s · run: bash %s" % (name, st["version"], wrapper_path(pre, name))


def setup(ctx, name, dry=False):
    t = TOOLS[name]
    L = ctx.log
    try:
        row = pin_of(ctx, t["key"])
    except (OSError, ValueError, KeyError) as e:
        L("%s: refused -- %s" % (name, e))
        return 1
    sha = row["sha"]
    tree, pre, home = layout(ctx, name, sha)
    s, detail = status(ctx, name)
    if s == "ready":
        L("%s: ready -- %s" % (name, detail))
        return 0
    if s == "wrong-version":
        L("%s: refused -- wrong version (%s); remove it first: %s %s --remove" % (name, detail, SELF, name))
        return 1
    # (a) prerequisites
    route, misses = pick_route(ctx, name)
    if route is None and "release" in t["routes"] and not dry:
        # the release route needs the pin to be fetched first to know its tags
        pass
    if route is None:
        asset = None
        if "release" in t["routes"] and not dry and bootstrap.run(ctx.root, [row], log=lambda *a: None) == 0:
            asset = release_asset_for(ctx, name, sha)
        elif "release" in t["routes"] and bootstrap.has_pin(bootstrap.bare_path(ctx.root, t["key"]), sha):
            asset = release_asset_for(ctx, name, sha)
        if asset:
            route = "release"
        else:
            L("%s: refused -- prerequisites missing for every route (%s)" % (name, " / ".join(t["routes"])))
            for r, m in misses.items():
                for need in m:
                    if need == "release:none":
                        near = nearest_tag(ctx, name, sha)
                        L("  route release: the pin %s is not a tagged release, so no prebuilt binary matches it%s; "
                          "install Rust instead -> %s" % (sha[:12], near, PREREQS["cargo"]["win"]))
                    else:
                        L("  route %s: %s" % (r, instruction(ctx, need)))
            return 1
    if dry:
        L("%s --dry-run · pin %s · route %s · nothing written" % (name, sha[:12], route))
        L("  (b) python3 tools/kit/bootstrap.py %s" % t["key"])
        L("  (c) python3 tools/kit/runtree.py %s --workspace   -> %s" % (t["key"], tree))
        L("  (d) install at the version in %s (read from the run tree) via %s into %s" % (t["manifest"][0], route, pre))
        L("  (e) telemetry: %s" % " ".join("%s=%s" % kv for kv in sorted(t["telemetry_env"].items())))
        L("  (f) %s" % keys_report(ctx, name))
        L("  (g) smoke: %s %s ; %s %s" % (t["cli"], " ".join(t["version_args"] or ["(package.json version)"]), t["cli"], " ".join(t["smoke_args"])))
        return 0
    # (b) pin
    if bootstrap.run(ctx.root, [row], log=lambda *a: None) != 0:
        L("%s: refused -- bootstrap of %s at %s failed; run python3 tools/kit/bootstrap.py %s" % (name, t["key"], sha[:12], t["key"]))
        return 1
    L("%s: (b) pin %s present" % (name, sha[:12]))
    # (c) run tree outside the station, kit floor wired
    msgs = []
    if runtree.add(ctx.root, t["key"], station=STATION, workspace=True, rr=ctx.rr, log=msgs.append,
                   station_root=ctx.station_root) != 0:
        L("%s: refused -- run tree: %s" % (name, " | ".join(msgs)))
        return 1
    if os.path.realpath(tree).startswith(os.path.realpath(ctx.station_root) + os.sep):
        L("%s: refused -- run tree %s is inside the station; set STABLE_KIT_RUN outside it" % (name, tree))
        return 1
    L("%s: (c) run tree %s" % (name, tree))
    # (d) install at the pin's own version
    try:
        version = read_version(tree, t["manifest"])
    except (OSError, ValueError, KeyError) as e:
        L("%s: refused -- cannot read the pin's version: %s" % (name, e))
        return 1
    os.makedirs(pre, exist_ok=True)
    if route == "release":
        ok, why = install_release(ctx, name, release_asset_for(ctx, name, sha), pre, ctx.fetcher)
        if not ok:
            L("%s: refused -- release binary: %s; or install Rust -> %s" % (name, why, PREREQS["cargo"]["win"]))
            return 1
    for argv, cwd, extra in install_cmds(ctx, name, route, tree, pre, version):
        rc, out = ctx.run(argv, cwd=cwd, extra_env=extra)
        if rc != 0:
            L("%s: refused -- install step failed (rc %d): %s\n  %s" % (name, rc, " ".join(os.path.basename(a) if i == 0 else a for i, a in enumerate(argv)),
                                                                     "\n  ".join(out.strip().splitlines()[-12:])))
            return 1
    binp = bin_path(ctx, pre, t["cli"], route)
    if not os.path.exists(binp):
        L("%s: refused -- install ran but %s is missing" % (name, binp))
        return 1
    L("%s: (d) installed %s %s via %s" % (name, t["package"], version, route))
    # (e) telemetry + (f) keys
    write_home(name, home)
    run_sh = write_wrapper(ctx, name, pre, binp)
    L("%s: (e) telemetry off: %s" % (name, " ".join("%s=%s" % kv for kv in sorted(t["telemetry_env"].items()))
                                     + ("; %s written" % ", ".join("home/" + f for f in t["home_files"]) if t["home_files"] else "")))
    L("%s: (f) %s" % (name, keys_report(ctx, name)))
    # (g) smoke: the version must be the pin's, then one harmless command
    rc, out = probe_version(ctx, name, pre, binp)
    if rc != 0 or not version_matches(out, version):
        L("%s: refused -- wrong version: probe says %r, the pin wants %s; nothing recorded (%s %s --remove cleans up)"
          % (name, out.strip()[-160:], version, SELF, name))
        return 1
    rc2, out2 = ctx.run([binp] + t["smoke_args"], extra_env=tool_env(name, home))
    if rc2 != 0:
        L("%s: refused -- smoke `%s %s` failed (rc %d): %s" % (name, t["cli"], " ".join(t["smoke_args"]), rc2, out2.strip()[-300:]))
        return 1
    _kit.write_json(os.path.join(pre, STATE), {"_generated_by": "tools/station/setup_tool.py", "tool": name, "key": t["key"],
                                               "sha": sha, "version": version, "route": route, "bin": binp, "run": run_sh,
                                               "telemetry_env": t["telemetry_env"], "smoke": {"cmd": [t["cli"]] + t["smoke_args"],
                                                                                          "tail": out2.strip()[-400:]}})
    L("%s: (g) smoke ok: %s -> %s ; %s %s -> rc 0" % (name, " ".join([t["cli"]] + (t["version_args"] or ["(package.json)"])),
                                                     out.strip().splitlines()[-1][:80], t["cli"], " ".join(t["smoke_args"])))
    L("%s: ready -- lives in %s" % (name, pre))
    L("  run: bash %s %s     (%s)" % (run_sh, " ".join(t["smoke_args"]), t["run_hint"]))
    L("  or put it on PATH (Git Bash): export PATH=\"%s:$PATH\"" % os.path.dirname(run_sh))
    return 0


def remove(ctx, name, dry=False):
    t = TOOLS[name]
    try:
        sha = pin_of(ctx, t["key"])["sha"]
    except (OSError, ValueError, KeyError) as e:
        ctx.log("%s: refused -- %s" % (name, e))
        return 1
    tree, pre, _ = layout(ctx, name, sha)
    if dry:
        ctx.log("%s --remove --dry-run: would delete %s and the run tree %s" % (name, pre, tree))
        return 0
    if not os.path.isdir(tree):
        ctx.log("%s: nothing to remove (no run tree at %s)" % (name, tree))
        return 0
    shutil.rmtree(pre, ignore_errors=True)
    msgs = []
    rc = runtree.remove(ctx.root, t["key"], station=STATION, rr=ctx.rr, force=True, log=msgs.append)
    if rc != 0 or os.path.exists(tree):
        ctx.log("%s: refused -- run tree not removed: %s" % (name, " | ".join(msgs)))
        return 1
    ctx.log("%s: removed (install and run tree %s; the bare pin stays in the bootstrap cache)" % (name, tree))
    return 0


def check(ctx, name):
    s, detail = status(ctx, name)
    if s == "ready":
        ctx.log("%s: ready -- %s" % (name, detail))
        return 0
    ctx.log("%s: not ready (%s: %s) -> one command: %s %s" % (name, s, detail, SELF, name))
    return 1


# ---------------------------------------------------------------- selftest
STUB_NPM = r'''#!/usr/bin/env python3
import json, os, sys
a = sys.argv[1:]
pre = a[a.index("--prefix") + 1]
pkg, ver = a[-1].rsplit("@", 1)
ver = os.environ.get("STUB_WRONG_VERSION") or ver
os.makedirs(os.path.join(pre, "node_modules", pkg), exist_ok=True)
json.dump({"name": pkg, "version": ver}, open(os.path.join(pre, "node_modules", pkg, "package.json"), "w"))
b = os.path.join(pre, "node_modules", ".bin"); os.makedirs(b, exist_ok=True)
for cli in ("rea", "openwiki"):
    p = os.path.join(b, cli)
    open(p, "w").write("#!/bin/sh\nif [ \"$1\" = --version ]; then echo %s; else echo help ok; fi\n" % ver)
    os.chmod(p, 0o755)
'''
STUB_NODE = "#!/bin/sh\necho ${STUB_NODE_VERSION:-v26.1.0}\n"
STUB_UV = r'''#!/usr/bin/env python3
import os, sys
spec = sys.argv[-1]; ver = os.environ.get("STUB_WRONG_VERSION") or spec.split("==")[1]
b = os.environ["UV_TOOL_BIN_DIR"]; os.makedirs(b, exist_ok=True)
p = os.path.join(b, "evo")
open(p, "w").write("#!/bin/sh\nif [ \"$1\" = --version ]; then echo evo-hq-cli %s; else echo \"{\\\"enabled\\\": false, \\\"source\\\": \\\"env\\\", \\\"evo_telemetry\\\": \\\"$EVO_TELEMETRY\\\"}\"; fi\n" % ver)
os.chmod(p, 0o755)
'''


def _stub_bin(tmp, which):
    d = os.path.join(tmp, "fakebin-" + "-".join(which))
    os.makedirs(d, exist_ok=True)
    bodies = {"npm": STUB_NPM, "node": STUB_NODE, "uv": STUB_UV, "python3": "#!/bin/sh\nexec %s \"$@\"\n" % sys.executable,
              "git": "#!/bin/sh\nexec %s \"$@\"\n" % shutil.which("git")}
    for n in which:
        p = os.path.join(d, n)
        with open(p, "w") as f:
            f.write(bodies[n])
        os.chmod(p, 0o755)
    return d


def _fixture(tmp):
    """A kit root whose registry holds four fixture remotes shaped like the real pins (manifest + version)."""
    rows, homes = [], []
    shapes = {"morluto~rea": {"package.json": '{"name": "rea-agents", "version": "6.5.0"}\n'},
              "evo-hq~evo": {"plugins/evo/pyproject.toml": '[project]\nname = "evo-hq-cli"\nversion = "0.8.0"\n'},
              "langchain-ai~openwiki": {"package.json": '{"name": "openwiki", "version": "0.7.2"}\n'},
              "styler-ai~ProjectAtlas": {"Cargo.toml": '[workspace]\nmembers = []\n\n[workspace.package]\nversion = "0.5.0-rc3"\n'}}
    for key, files in shapes.items():
        remote = os.path.join(tmp, "remote-" + key)
        _kit.run(["git", "init", "-q", "-b", "main", remote])
        _kit.fixture_git_config(remote)
        for rel, body in files.items():
            os.makedirs(os.path.dirname(os.path.join(remote, rel)) or remote, exist_ok=True)
            open(os.path.join(remote, rel), "w").write(body)
        _kit.stage_paths(remote)
        _kit.commit(remote, "pin")
        sha = _kit.git_out(remote, "rev-parse", "HEAD")
        rows.append({"key": key, "repo": key.replace("~", "/"), "url": "file://" + remote, "sha": sha})
        homes.append({"key": key, "lands": [{"station": STATION, "how": "bootstrap"}]})
    root = bootstrap.make_kit_root(tmp, rows, homes)
    open(os.path.join(root, ".env"), "w").write("ANTHROPIC_API_KEY=sk-SECRET-never-printed\nOPENROUTER_API_KEY=\n")
    return root


def _selftest():
    os.environ.pop(_kit.CACHE_ENV, None)
    for k in ("STUB_WRONG_VERSION", "STUB_NODE_VERSION"):
        os.environ.pop(k, None)
    tmp = tempfile.mkdtemp(prefix="kit-setup-")
    cases = 0
    try:
        root = _fixture(tmp)
        rr = os.path.join(tmp, "run")
        lines = []
        mk = lambda path, win=False: Ctx(root, run_root=rr, path=path, log=lines.append, windows=win)

        # 1. missing prerequisite -> exact Windows/Git Bash instruction, nothing written
        lines.clear()
        c = mk(_stub_bin(tmp, ["git"]))
        assert setup(c, "rea") == 1
        assert any("missing node -> Windows/Git Bash: winget install --id OpenJS.NodeJS -e" in l for l in lines), lines
        assert not os.path.exists(rr), "a refused prerequisite must not create a run tree"
        lines.clear()
        assert setup(c, "evo") == 1
        assert any("route uv: missing python" in l for l in lines) and any("route pip:" in l for l in lines), lines
        lines.clear()
        assert setup(c, "projectatlas") == 1
        assert any("winget install --id Rustlang.Rustup -e" in l for l in lines), lines
        assert any("not a tagged release" in l for l in lines), "cargo absent + untagged pin -> rustup instruction: %s" % lines
        lines.clear()
        assert setup(mk(_stub_bin(tmp, ["git"]), win=False), "rea") == 1
        assert any("Linux/macOS: " in l for l in lines), lines
        cases += 1

        # 1b. node too old for the pin's engines range -> refused with the node line
        os.environ["STUB_NODE_VERSION"] = "v20.11.0"
        lines.clear()
        assert setup(mk(_stub_bin(tmp, ["git", "node", "npm"])), "openwiki") == 1
        assert any("node 20.11.0 found" in l and ">=22.22.0" in l for l in lines), lines
        os.environ.pop("STUB_NODE_VERSION")
        cases += 1

        # 2. a full setup through the stubs: ready, run.sh carries the opt-outs, keys by name, no secret value printed
        full = _stub_bin(tmp, ["git", "node", "npm", "uv", "python3"])
        lines.clear()
        c = mk(full)
        assert setup(c, "rea") == 0, lines
        assert setup(c, "evo") == 0, lines
        assert setup(c, "openwiki") == 0, lines
        _, pre_ow, home_ow = layout(c, "openwiki", pin_of(c, "langchain-ai~openwiki")["sha"])
        tree_ev, pre_ev, home_ev = layout(c, "evo", pin_of(c, "evo-hq~evo")["sha"])
        assert not os.path.realpath(pre_ev).startswith(os.path.realpath(root)), "install must live outside the station"
        sh = open(wrapper_path(pre_ow, "openwiki")).read()
        assert "export OPENWIKI_TELEMETRY_DISABLED='1'" in sh and "ANTHROPIC_API_KEY|OPENROUTER_API_KEY" in sh, sh
        assert sh.index("while IFS=") < sh.index("export OPENWIKI_TELEMETRY_DISABLED"), "opt-outs must follow the .env read"
        assert "sk-SECRET" not in sh and not any("sk-SECRET" in l for l in lines), "a key value leaked"
        assert any("ANTHROPIC_API_KEY=set" in l and "OPENROUTER_API_KEY=empty" in l for l in lines), lines
        assert json.load(open(os.path.join(home_ev, "telemetry.json"))) == {"enabled": False}
        assert os.path.isfile(os.path.join(tree_ev, ".claude", "settings.local.json")), "kit floor hooks wired (--workspace)"
        assert read_state(pre_ev)["version"] == "0.8.0" and "\"source\": \"env\"" in read_state(pre_ev)["smoke"]["tail"]
        assert any(l.startswith("evo: ready -- lives in") for l in lines), lines
        if shutil.which("bash"):
            rc, out = c.run([shutil.which("bash"), wrapper_path(pre_ev, "evo"), "telemetry"])
            assert rc == 0 and "\"evo_telemetry\": \"0\"" in out, out
        cases += 1

        # 3. second run -> ready, nothing re-installed (the stub npm is gone from PATH and it still says ready)
        lines.clear()
        c2 = mk(_stub_bin(tmp, ["git"]))
        assert setup(c2, "rea") == 0 and any(l.startswith("rea: ready") for l in lines), lines
        assert check(c2, "evo") == 0
        cases += 1

        # 4. --dry-run writes nothing
        lines.clear()
        before = sorted(os.listdir(os.path.join(rr, STATION)))
        assert setup(mk(full), "projectatlas", dry=True) == 1, "cargo absent: dry-run still reports the refusal"
        assert sorted(os.listdir(os.path.join(rr, STATION))) == before
        cases += 1

        # 5. --remove -> gone; --check then names the one setup command
        lines.clear()
        tree_rea = layout(c, "rea", pin_of(c, "morluto~rea")["sha"])[0]
        assert remove(c, "rea") == 0 and not os.path.exists(tree_rea), lines
        lines.clear()
        assert check(c, "rea") == 1 and any("one command: python3 tools/station/setup_tool.py rea" in l for l in lines), lines
        assert remove(c, "rea") == 0, "remove is idempotent"
        cases += 1

        # 6. wrong version -> refused: an installer that delivers another version, and a state file for another pin
        os.environ["STUB_WRONG_VERSION"] = "6.4.0"
        lines.clear()
        assert setup(mk(full), "rea") == 1
        assert any("refused -- wrong version" in l and "6.5.0" in l for l in lines), lines
        assert read_state(layout(c, "rea", pin_of(c, "morluto~rea")["sha"])[1]) is None, "a wrong version is never recorded"
        os.environ.pop("STUB_WRONG_VERSION")
        st = read_state(pre_ow)
        st["sha"] = "0" * 40
        _kit.write_json(os.path.join(pre_ow, STATE), st)
        lines.clear()
        assert setup(mk(full), "openwiki") == 1 and any("wrong version" in l and "--remove" in l for l in lines), lines
        assert check(mk(full), "openwiki") == 1
        cases += 1

        # 6b. cargo absent + a release tag AT the pin -> the prebuilt binary, checked against SHA256SUMS; a bad sum is refused
        import hashlib, io, zipfile, tarfile as _tf
        pa_key = "styler-ai~ProjectAtlas"
        pa_sha = pin_of(c, pa_key)["sha"]
        remote = os.path.join(tmp, "remote-" + pa_key)
        _kit.git(remote, "tag", "v0.5.0-rc3", pa_sha)
        payload = io.BytesIO()
        with _tf.open(fileobj=payload, mode="w:gz") as tf:
            body = b"#!/bin/sh\nif [ \"$1\" = --version ]; then echo projectatlas 0.5.0-rc3; else echo runtime ok; fi\n"
            ti = _tf.TarInfo("projectatlas/projectatlas")
            ti.size, ti.mode = len(body), 0o755
            tf.addfile(ti, io.BytesIO(body))
        blob = payload.getvalue()
        asset = "projectatlas-v0.5.0-rc3-x86_64-unknown-linux-gnu.tar.gz"
        good = {"SHA256SUMS": ("%s  %s\n" % (hashlib.sha256(blob).hexdigest(), asset)).encode(), asset: blob}
        bad = dict(good, SHA256SUMS=("%s  %s\n" % ("0" * 64, asset)).encode())
        c3 = mk(_stub_bin(tmp, ["git"]))
        c3.fetcher = lambda url: bad[url.rsplit("/", 1)[1]]
        lines.clear()
        assert setup(c3, "projectatlas") == 1 and any("SHA256SUMS says" in l for l in lines), lines
        c3.fetcher = lambda url: good[url.rsplit("/", 1)[1]]
        lines.clear()
        assert setup(c3, "projectatlas") == 0 and any("ready" in l for l in lines), lines
        assert read_state(layout(c3, "projectatlas", pa_sha)[1])["route"] == "release"
        assert remove(c3, "projectatlas") == 0
        cases += 1

        # 6c. Windows: the wrapper execs npm's sh shim (not .cmd) by a forward-slash path
        cw = mk(full, win=True)
        pw = os.path.join(tmp, "winpre")
        os.makedirs(pw)
        body = open(write_wrapper(cw, "rea", pw, "C:\\Users\\op\\.kit-tool\\node_modules\\.bin\\rea.cmd")).read()
        assert "exec 'C:/Users/op/.kit-tool/node_modules/.bin/rea' " in body, body
        cases += 1

        # 7. the wrapper is named after the CLI: act_gate's station patterns still ask through it (gates stay)
        pats = _kit.read_json(os.path.join(ROOT_GUESS, "station.json"))["irreversible_acts"]
        asks = lambda cmd: any(re.search(p, cmd) for p in pats)
        w = lambda n: "bash " + wrapper_path(os.path.join(rr, STATION, "x@1", PREFIX), n)
        for cmd in (w("rea") + " analyze-javascript-application /t", w("rea") + " setup", w("evo") + " ship",
                    w("evo") + " telemetry off", w("openwiki") + " auth", w("projectatlas") + " init"):
            assert asks(cmd), "act_gate would not ask for: " + cmd
        assert not asks(w("rea") + " --help") and not asks(w("evo") + " telemetry status")
        cases += 1

        # 8. readers: the pin's version from its own manifests
        assert read_version(layout(c, "evo", pin_of(c, "evo-hq~evo")["sha"])[0], TOOLS["evo"]["manifest"]) == "0.8.0"
        pa_tree = os.path.join(tmp, "pa")
        os.makedirs(pa_tree)
        open(os.path.join(pa_tree, "Cargo.toml"), "w").write('[workspace.package]\nversion = "0.5.0-rc3"\n[package]\nversion = "9"\n')
        assert read_version(pa_tree, TOOLS["projectatlas"]["manifest"]) == "0.5.0-rc3"
        assert version_matches("evo-hq-cli 0.8.0\n", "0.8.0") and not version_matches("evo-hq-cli 0.8.01", "0.8.0")
        assert not version_matches("6.5.0-rc1", "6.5.0") and version_matches("projectatlas 0.5.0-rc3", "0.5.0-rc3")
        assert node_ok((26, 1, 0), TOOLS["rea"]["node_range"]) and not node_ok((23, 1, 0), TOOLS["rea"]["node_range"])
        cases += 1
        print("setup_tool selftest OK (%d cases: missing prerequisite, old node, full setup, second run ready, dry-run, "
              "remove, wrong version, release binary + bad checksum, Windows wrapper, act_gate through the wrapper, readers)" % cases)
        return 0
    finally:
        for k in ("STUB_WRONG_VERSION", "STUB_NODE_VERSION"):
            os.environ.pop(k, None)
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tool", nargs="?", choices=ORDER)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--remove", action="store_true")
    ap.add_argument("--check", metavar="TOOL", choices=ORDER)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--root", default=ROOT_GUESS)
    ap.add_argument("--run-root")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return _selftest()
    ctx = Ctx(a.root, run_root=a.run_root)
    if a.check:
        return check(ctx, a.check)
    if a.list:
        for n in ORDER:
            s, d = status(ctx, n)
            print("  %-13s %-14s %s" % (n, s, d))
        return 0
    names = ORDER if a.all else ([a.tool] if a.tool else [])
    if not names:
        ap.print_help()
        return 2
    rc = 0
    for n in names:
        r = remove(ctx, n, a.dry_run) if a.remove else setup(ctx, n, a.dry_run)
        rc = max(rc, r)
    if len(names) > 1:
        print("setup_tool: %d tool(s) · %s" % (len(names), "all ok" if rc == 0 else "at least one refused (see above)"))
    return rc


if __name__ == "__main__":
    sys.exit(main())
