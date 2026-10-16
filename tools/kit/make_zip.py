#!/usr/bin/env python3
"""make_zip.py - package the assembled repo as stable-kit.zip (ORDER 2).

Earned by: ORDER 2, operator verbatim: "if you can do the 'main holds the shared
core and decision tree and each station gets its own self-contained branch' in
a zip then great". A zip of a git repo can silently drop .git files or
permissions on some unzip tools, so the zip carries a verified `git bundle --all`
as the fallback, and is unzip-verified before it is called done.
Retires: nothing (new with the kit).

  make_zip.py --repo <dir> --out <stable-kit.zip> [--branches N] [--name stable-kit]
    (0) stage: a fresh repo <name>/ whose ONLY refs are `main` + `station/<x>`, fetched from the
        resolved refs of <dir> (tools/kit/_kit.main_ref / station_refs: local, remote-tracking or
        hosted claude/stable-kit-* - REPRODUCE F2), checked out on main; no remotes, no
        remote-tracking refs, no untracked or gitignored files (REPRODUCE F10 a)
    (a) git bundle create <tmp>/stable-kit.bundle --all  + git bundle verify
    (b) zip <name>/ INCLUDING .git, EXCLUDING .upstream/ .cache/ .station/
        .usage/ (gitignored caches), plus stable-kit.bundle and UNZIP.md at the
        zip root; POSIX permissions stored; REFUSES if the tree has a symlink
        (ingest dereferenced them all) and prints each one
    (c) verify: unzip to a temp dir, then run UNZIP.md's own commands exactly as written
        (step 2 fsck, step 3 branch list == N (default 9), steps 7-8 the bundle fallback,
        whose restored clone must hold N local branches - REPRODUCE F3)
    prints the zip size and the file count with denominators.
  make_zip.py --selftest   (fixture repo with two branches, the kit's real UNZIP.md, all three layouts)
Exit 0 written and verified · 1 refused / verify failed · 2 usage.
"""
import argparse
import os
import re
import shlex
import shutil
import stat
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _kit  # noqa: E402

EXCLUDE_TOP = (".upstream", ".cache", ".station", ".usage")


def walk(repo):
    files, links = [], []
    for base, dirs, fs in os.walk(repo):
        rel_base = os.path.relpath(base, repo)
        if rel_base == ".":
            dirs[:] = [d for d in dirs if d not in EXCLUDE_TOP]
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for d in list(dirs):
            if os.path.islink(os.path.join(base, d)):
                links.append(os.path.normpath(os.path.join(rel_base, d)))
                dirs.remove(d)
        for fn in fs:
            p = os.path.join(base, fn)
            rel = os.path.normpath(os.path.join(rel_base, fn))
            (links if os.path.islink(p) else files).append(rel)
    return sorted(files), sorted(links)


def stage(src, dest, log=print):
    """(0) a normalised copy of the kit: refs main + station/<x> only, checked out on main.
    Returns the station names, or None when src has no main."""
    mref = _kit.main_ref(src)
    if not mref:
        log("make_zip: no main ref in %s (main or claude/stable-kit-main, local or remote-tracking)" % src)
        return None
    srefs = _kit.station_refs(src, _kit.known_stations(src))
    env = _kit.clean_git_env()
    _kit.run(["git", "init", "-q", "-b", "main", dest], env=env)
    specs = ["+%s:refs/heads/main" % mref] + ["+%s:refs/heads/station/%s" % (r, st) for st, r in srefs.items()]
    _kit.run(["git", "-C", dest, "fetch", "-q", "--no-tags", "--update-head-ok", os.path.abspath(src)] + specs, env=env)
    _kit.run(["git", "-C", dest, "checkout", "-q", "-f", "main"], env=env)
    _kit.run(["git", "-C", dest, "reflog", "expire", "--expire=now", "--all"], env=env)
    log("make_zip: staged main <- %s and %d station(s) <- %s" % (
        mref, len(srefs), ", ".join("%s" % r for r in srefs.values()) or "none"))
    return sorted(srefs)


def zip_repo(repo, out, branches=9, log=print, name="stable-kit"):
    src = os.path.abspath(repo.rstrip("/"))
    if _kit.run(["git", "-C", src, "rev-parse", "--git-dir"], check=False).returncode != 0:
        log("make_zip: not a git repo: %s" % src)
        return 2
    stmp = tempfile.mkdtemp(prefix="kit-zipstage-")
    try:
        repo = os.path.join(stmp, name)
        if stage(src, repo, log) is None:
            return 1
        return _zip_staged(repo, name, out, branches, log)
    finally:
        shutil.rmtree(stmp, ignore_errors=True)


def _zip_staged(repo, name, out, branches, log):
    files, links = walk(repo)
    if links:
        log("make_zip: REFUSED - %d symlink(s) in the tree (ingest dereferences them; fix the build):" % len(links))
        for l in links[:50]:
            log("  " + l)
        return 1
    tmp = tempfile.mkdtemp(prefix="kit-zip-")
    try:
        bundle = os.path.join(tmp, "stable-kit.bundle")
        _kit.run(["git", "-C", repo, "bundle", "create", "-q", bundle, "--all"])
        if _kit.run(["git", "-C", repo, "bundle", "verify", "-q", bundle], check=False).returncode != 0:
            log("make_zip: bundle verify failed")
            return 1
        unzip_md = os.path.join(repo, "UNZIP.md")
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        n = 0
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
            for rel in files:
                p = os.path.join(repo, rel)
                st = os.stat(p)
                zi = zipfile.ZipInfo.from_file(p, arcname="%s/%s" % (name, rel.replace(os.sep, "/")))
                zi.external_attr = (stat.S_IFREG | stat.S_IMODE(st.st_mode)) << 16
                zi.compress_type = zipfile.ZIP_DEFLATED
                with open(p, "rb") as f:
                    z.writestr(zi, f.read())
                n += 1
            for src, arc in ((bundle, "stable-kit.bundle"), (unzip_md, "UNZIP.md")):
                if os.path.isfile(src):
                    zi = zipfile.ZipInfo.from_file(src, arcname=arc)
                    zi.external_attr = (stat.S_IFREG | 0o644) << 16
                    zi.compress_type = zipfile.ZIP_DEFLATED
                    with open(src, "rb") as f:
                        z.writestr(zi, f.read())
                    n += 1
        log("make_zip: %s · %d bytes · %d files (%d repo files incl. .git / %d walked; excluded top dirs %s)"
            % (out, os.path.getsize(out), n, len(files), len(files), ",".join(EXCLUDE_TOP)))
        return verify(out, name, branches, log)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


UNZIP_STEPS = (2, 3, 7, 8)


def unzip_commands(md):
    """{step: [argv, ...]} for the backticked `git ...` commands of UNZIP.md steps 2, 3, 7 and 8."""
    out = {}
    for line in md.splitlines():
        m = re.match(r"^\s*(\d+)\.\s", line)
        if not m or int(m.group(1)) not in UNZIP_STEPS:
            continue
        cmds = [shlex.split(c) for c in re.findall(r"`([^`]+)`", line) if c.startswith("git ")]
        if cmds:
            out[int(m.group(1))] = cmds
    return out


def verify(out, name, branches, log=print):
    tmp = tempfile.mkdtemp(prefix="kit-unzip-")
    try:
        with zipfile.ZipFile(out) as z:
            for zi in z.infolist():
                z.extract(zi, tmp)
                mode = (zi.external_attr >> 16) & 0o777
                if mode:
                    os.chmod(os.path.join(tmp, zi.filename), mode)
        if not os.path.isfile(os.path.join(tmp, "UNZIP.md")):
            log("make_zip verify: UNZIP.md missing at the zip root")
            return 1
        steps = unzip_commands(open(os.path.join(tmp, "UNZIP.md"), encoding="utf-8").read())
        missing = [n for n in UNZIP_STEPS if n not in steps]
        if missing:
            log("make_zip verify: UNZIP.md steps %s carry no `git ...` command to run" % missing)
            return 1
        env = _kit.clean_git_env()

        def run_step(n):
            outs = []
            for argv in steps[n]:
                p = _kit.run(argv, cwd=tmp, check=False, env=env)
                if p.returncode != 0:
                    log("make_zip verify: UNZIP step %d `%s` failed (%d): %s" % (n, " ".join(argv), p.returncode, (p.err or p.out)[:300]))
                    return None
                outs.append(p.out)
            return "".join(outs)
        if run_step(2) is None:
            return 1
        listing = run_step(3)
        if listing is None:
            return 1
        br = [l.strip(" *+") for l in listing.splitlines() if l.strip()]
        if len(br) != branches or "main" not in br:
            log("make_zip verify: UNZIP step 3 lists %d branches, expected %d (main + station/*): %s" % (len(br), branches, br))
            return 1
        if run_step(7) is None or run_step(8) is None:
            return 1
        restored = [a for a in steps[7][0] if not a.startswith("-")][-1]
        rb = _kit.run(["git", "-C", os.path.join(tmp, restored), "for-each-ref", "--format=%(refname:short)", "refs/heads/"],
                      env=env).out.split()
        if len(rb) != branches:
            log("make_zip verify: UNZIP steps 7-8 restored %d local branches, expected %d: %s" % (len(rb), branches, rb))
            return 1
        log("make_zip verify: unzip OK · UNZIP step 2 fsck clean · step 3 %d / %d branches · steps 7-8 restore %d / %d local branches"
            % (len(br), branches, len(rb), branches))
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _selftest():
    tmp = tempfile.mkdtemp(prefix="kit-zipst-")
    quiet = lambda *a: None
    try:
        repo = os.path.join(tmp, "stable-kit")
        _kit.run(["git", "init", "-q", "-b", "main", repo])
        _kit.fixture_git_config(repo)
        # the kit's REAL UNZIP.md: verify runs its steps 2, 3, 7, 8 exactly as written (REPRODUCE F3)
        real = os.path.join(os.path.dirname(os.path.dirname(_kit.KIT_DIR)), "UNZIP.md")
        shutil.copy(real, os.path.join(repo, "UNZIP.md"))
        os.makedirs(os.path.join(repo, "tools"))
        sp = os.path.join(repo, "tools", "x.sh")
        open(sp, "w").write("#!/bin/sh\necho x\n")
        os.chmod(sp, 0o755)
        open(os.path.join(repo, ".gitignore"), "w").write(".upstream/\n")
        _kit.stage_paths(repo)
        _kit.commit(repo, "main")
        _kit.git(repo, "switch", "-q", "-c", "station/alpha")
        open(os.path.join(repo, "station.json"), "w").write("{}\n")
        _kit.stage_paths(repo)
        _kit.commit(repo, "alpha")
        _kit.git(repo, "switch", "-q", "main")
        os.makedirs(os.path.join(repo, ".upstream", "big.git"))
        open(os.path.join(repo, ".upstream", "big.git", "HEAD"), "w").write("cache\n")
        out = os.path.join(tmp, "out", "stable-kit.zip")
        assert zip_repo(repo, out, branches=2, log=quiet) == 0
        names = zipfile.ZipFile(out).namelist()
        assert "stable-kit.bundle" in names and "UNZIP.md" in names
        assert "stable-kit/.git/HEAD" in names, "includes .git"
        assert not any(n.startswith("stable-kit/.upstream/") for n in names), "excludes .upstream/"
        zi = zipfile.ZipFile(out).getinfo("stable-kit/tools/x.sh")
        assert (zi.external_attr >> 16) & 0o111, "exec bit stored"
        assert zip_repo(repo, out, branches=9, log=quiet) == 1, "wrong branch count must fail verify"
        # REPRODUCE F2 / F10 a: a plain clone and the hosted naming zip to the same 2 local branches, no remotes
        for lay, lrepo in _kit.fixture_layouts(repo, tmp).items():
            o = os.path.join(tmp, "out", "%s.zip" % lay)
            assert zip_repo(lrepo, o, branches=2, log=quiet) == 0, "layout %s" % lay
            names = zipfile.ZipFile(o).namelist()
            assert not any("/refs/remotes/" in n for n in names) and "stable-kit/station.json" not in names, lay
            cfg = zipfile.ZipFile(o).read("stable-kit/.git/config").decode()
            assert "[remote" not in cfg, (lay, cfg)
        # UNZIP.md as the reviewers found it (step 8 without --update-head-ok) must FAIL verify
        bad = open(real, encoding="utf-8").read().replace("fetch --update-head-ok origin", "fetch origin")
        assert bad != open(real, encoding="utf-8").read(), "UNZIP.md step 8 must carry --update-head-ok"
        open(os.path.join(repo, "UNZIP.md"), "w").write(bad)
        _kit.stage_paths(repo)
        _kit.commit(repo, "planted: the refused fetch")
        assert zip_repo(repo, out + "3", branches=2, log=quiet) == 1, "planted step 8 must fail verify"
        _kit.git(repo, "reset", "-q", "--hard", "HEAD~1")
        os.symlink("UNZIP.md", os.path.join(repo, "link.md"))
        _kit.git(repo, "add", "--", "link.md")
        _kit.commit(repo, "planted symlink")
        assert zip_repo(repo, out + "2", branches=2, log=quiet) == 1, "symlink must be refused"
        assert not os.path.exists(out + "2")
        print("selftest OK")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo")
    ap.add_argument("--out")
    ap.add_argument("--branches", type=int, default=9)
    ap.add_argument("--name", default="stable-kit", help="top directory in the zip (UNZIP.md names stable-kit/)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return _selftest()
    if not (a.repo and a.out):
        ap.print_help()
        return 2
    try:
        return zip_repo(a.repo, a.out, a.branches, name=a.name)
    except (OSError, _kit.KitError) as e:
        print("make_zip: %s" % e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
