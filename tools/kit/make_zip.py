#!/usr/bin/env python3
"""make_zip.py - package the assembled repo as stable-kit.zip (ORDER 2).

Earned by: ORDER 2, operator verbatim: "if you can do the 'main holds the shared
core and decision tree and each station gets its own self-contained branch' in
a zip then great". A zip of a git repo can silently drop .git files or
permissions on some unzip tools, so the zip carries a verified `git bundle --all`
as the fallback, and is unzip-verified before it is called done.
Retires: nothing (new with the kit).

  make_zip.py --repo <dir> --out <stable-kit.zip> [--branches N]
    (a) git bundle create <tmp>/stable-kit.bundle --all  + git bundle verify
    (b) zip <repo-name>/ INCLUDING .git, EXCLUDING .upstream/ .cache/ .station/
        .usage/ (gitignored caches), plus stable-kit.bundle and UNZIP.md at the
        zip root; POSIX permissions stored; REFUSES if the tree has a symlink
        (ingest dereferenced them all) and prints each one
    (c) verify: unzip to a temp dir, git fsck, branch count == N (default 9),
        git clone of the bundle works
    prints the zip size and the file count with denominators.
  make_zip.py --selftest   (fixture repo with two branches)
Exit 0 written and verified · 1 refused / verify failed · 2 usage.
"""
import argparse
import os
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


def zip_repo(repo, out, branches=9, log=print):
    repo = os.path.abspath(repo.rstrip("/"))
    name = os.path.basename(repo)
    if _kit.run(["git", "-C", repo, "rev-parse", "--git-dir"], check=False).returncode != 0:
        log("make_zip: not a git repo: %s" % repo)
        return 2
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


def verify(out, name, branches, log=print):
    tmp = tempfile.mkdtemp(prefix="kit-unzip-")
    try:
        with zipfile.ZipFile(out) as z:
            for zi in z.infolist():
                z.extract(zi, tmp)
                mode = (zi.external_attr >> 16) & 0o777
                if mode:
                    os.chmod(os.path.join(tmp, zi.filename), mode)
        r = os.path.join(tmp, name)
        f = _kit.run(["git", "-C", r, "fsck", "--no-progress"], check=False)
        if f.returncode != 0:
            log("make_zip verify: git fsck failed: %s" % f.err[:500])
            return 1
        br = [x for x in _kit.run(["git", "-C", r, "for-each-ref", "--format=%(refname:short)", "refs/heads/"]).out.split() if x]
        if len(br) != branches:
            log("make_zip verify: %d branches in the unzipped repo, expected %d: %s" % (len(br), branches, br))
            return 1
        c = os.path.join(tmp, "from-bundle")
        p = _kit.run(["git", "clone", "-q", os.path.join(tmp, "stable-kit.bundle"), c], check=False)
        if p.returncode != 0:
            log("make_zip verify: git clone of the bundle failed: %s" % p.err[:300])
            return 1
        rb = [x for x in _kit.run(["git", "-C", c, "for-each-ref", "--format=%(refname:short)", "refs/remotes/origin/"]).out.split()
              if not x.endswith("/HEAD") and x != "origin"]
        if len(rb) != branches:
            log("make_zip verify: bundle carries %d branches, expected %d" % (len(rb), branches))
            return 1
        if not os.path.isfile(os.path.join(tmp, "UNZIP.md")):
            log("make_zip verify: UNZIP.md missing at the zip root")
            return 1
        log("make_zip verify: unzip OK · git fsck clean · %d / %d branches · bundle clones with %d / %d branches"
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
        open(os.path.join(repo, "UNZIP.md"), "w").write("unzip\n")
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
        os.symlink("UNZIP.md", os.path.join(repo, "link.md"))
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
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return _selftest()
    if not (a.repo and a.out):
        ap.print_help()
        return 2
    try:
        return zip_repo(a.repo, a.out, a.branches)
    except (OSError, _kit.KitError) as e:
        print("make_zip: %s" % e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
