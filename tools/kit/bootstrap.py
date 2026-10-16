#!/usr/bin/env python3
"""bootstrap.py - fetch big upstreams as BARE clones at their exact 40-hex pin.

Earned by: committing the large apps (supabase 17,979 files, trigger.dev 6,832,
LibreChat 6,418, ...) would bloat every branch, and a checked-out upstream
CLAUDE.md or .claude/skills/ lazy-loads into the session that reads it (LL-03).
A bare clone has no working tree, so nothing in it can load; run trees live
outside the repo (tools/kit/runtree.py). Retires: ad-hoc `git clone` of upstreams.

  bootstrap.py <owner~repo>... | --all | --station <x> | --attic
               [--root R] [--registry sources.json] [--from-bundle DIR] [--bundle-out DIR] [--list]
    -> <cache>/<owner~repo>.git (bare), `git fetch` of exactly the pinned sha from
       registry/sources.json, ref refs/heads/pin -> the sha, verified with rev-parse;
       never checked out. <cache> is ONE directory shared by the kit checkout and every
       linked station worktree (REPRODUCE F4; tools/kit/_kit.upstream_cache):
       $STABLE_KIT_UPSTREAM, else the main checkout's gitignored `.upstream/`
       (`git rev-parse --git-common-dir`/..), so a bootstrap run from the kit root is
       seen from ~/stations/<x> and the reverse.
    --from-bundle DIR   use DIR/<owner~repo>.bundle instead of the network
    --bundle-out DIR    write DIR/<owner~repo>.bundle (ref pin) for offline transport
    --list              coverage: which rows have their pin locally
    --dry-run           no network, no writes: per selected row key · url · sha ·
                        files_at_pin (from the LOCK rows) · cache path · present/absent
  bootstrap.py --selftest   (a local fixture "remote"; no network)
Exit 0 all requested pins present · 1 a pin missing or mismatched · 2 usage.
"""
import argparse
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _kit  # noqa: E402


def load_registry(root, registry=None):
    src = _kit.read_json(registry or os.path.join(root, "registry", "sources.json"))["sources"]
    homes_p = os.path.join(root, "registry", "homes.json")
    attic_p = os.path.join(root, "registry", "attic.json")
    homes = _kit.read_json(homes_p)["homes"] if os.path.isfile(homes_p) else []
    attic = _kit.read_json(attic_p)["attic"] if os.path.isfile(attic_p) else []
    return src, homes, attic


def select(src, homes, attic, keys=(), all_=False, station=None, attic_flag=False):
    by_key = {s["key"]: s for s in src}
    out = []
    if all_:
        bkeys = {h["key"] for h in homes if any(l.get("how") == "bootstrap" for l in h.get("lands", []))}
        bkeys |= {a["key"] for a in attic}
        out += [by_key[k] for k in sorted(bkeys) if k in by_key]
    if station:
        for h in homes:
            if any(l.get("station") == station and l.get("how") == "bootstrap" for l in h.get("lands", [])):
                out.append(by_key[h["key"]])
    if attic_flag:
        out += [by_key[a["key"]] for a in attic if a["key"] in by_key]
    for k in keys:
        if k not in by_key:
            raise KeyError("not a registry key: %s (use owner~repo)" % k)
        out.append(by_key[k])
    seen, uniq = set(), []
    for s in out:
        if s["key"] not in seen:
            seen.add(s["key"])
            uniq.append(s)
    return uniq


def bare_path(root, key):
    return os.path.join(_kit.upstream_cache(root), key + ".git")


def lock_sizes(root):
    """{key: files_at_pin} from this checkout's upstream/LOCK.json and from every station ref's LOCK
    (on main the LOCKs live on the station branches). Unreadable LOCKs are skipped: a preview, not a check."""
    docs = []
    lp = os.path.join(root, "upstream", "LOCK.json")
    if os.path.isfile(lp):
        try:
            docs.append(_kit.read_json(lp))
        except (OSError, ValueError):
            pass
    try:
        refs = _kit.station_refs(root, _kit.known_stations(root)).values()
    except _kit.KitError:
        refs = []
    for ref in refs:
        p = _kit.git(root, "show", "%s:upstream/LOCK.json" % ref, check=False)
        if p.returncode == 0:
            try:
                docs.append(json.loads(p.out))
            except ValueError:
                pass
    out = {}
    for d in docs:
        for r in (d if isinstance(d, list) else (d.get("rows") or d.get("lock") or [])):
            k = r.get("key") or str(r.get("repo", "")).replace("/", "~")
            if r.get("files_at_pin") is not None:
                out.setdefault(k, r["files_at_pin"])
    return out


def dry_run(root, rows, from_bundle=None, log=print):
    """REPRODUCE F7: what a bootstrap would fetch, without the network and without writing."""
    sizes = lock_sizes(root)
    cache = _kit.upstream_cache(root)
    log("bootstrap --dry-run · cache %s · %d row(s) selected · no network, nothing written" % (cache, len(rows)))
    have = 0
    for r in rows:
        bare = bare_path(root, r["key"])
        pres = has_pin(bare, r["sha"])
        have += pres
        srcs = os.path.join(from_bundle, r["key"] + ".bundle") if from_bundle else r.get("url", "?")
        log("  %-45s %s · %s · files_at_pin %s · %s · %s" % (
            r["key"], srcs, r["sha"], sizes.get(r["key"], "?"), bare, "present" if pres else "absent (would fetch)"))
    log("bootstrap --dry-run: %d / %d pins already present; %d would be fetched" % (have, len(rows), len(rows) - have))
    return 0


def has_pin(bare, sha):
    if not os.path.isdir(bare):
        return False
    p = _kit.run(["git", "-C", bare, "cat-file", "-e", sha + "^{commit}"], check=False)
    return p.returncode == 0


def _ensure_bare(bare, url=None):
    if not os.path.isdir(bare):
        os.makedirs(os.path.dirname(bare), exist_ok=True)
        _kit.run(["git", "init", "-q", "--bare", bare])
    if url:
        have = _kit.run(["git", "-C", bare, "remote", "get-url", "origin"], check=False)
        if have.returncode != 0:
            _kit.run(["git", "-C", bare, "remote", "add", "origin", url])
        elif have.out.strip() != url:
            _kit.run(["git", "-C", bare, "remote", "set-url", "origin", url])


def _pin_ref(bare, sha):
    _kit.run(["git", "-C", bare, "update-ref", "refs/heads/pin", sha])
    _kit.run(["git", "-C", bare, "symbolic-ref", "HEAD", "refs/heads/pin"])
    got = _kit.run(["git", "-C", bare, "rev-parse", "pin^{commit}"]).out.strip()
    return got == sha


def fetch_one(root, row, from_bundle=None, log=print):
    key, sha = row["key"], row["sha"]
    bare = bare_path(root, key)
    if has_pin(bare, sha):
        ok = _pin_ref(bare, sha)
        log("  %-45s present  %s" % (key, sha[:12]))
        return ok
    if from_bundle:
        b = os.path.join(from_bundle, key + ".bundle")
        if not os.path.isfile(b):
            log("  %-45s MISSING bundle %s" % (key, b))
            return False
        _ensure_bare(bare)
        p = _kit.run(["git", "-C", bare, "fetch", "-q", "--no-tags", b, "+refs/heads/*:refs/bundle/*"], check=False)
        if p.returncode != 0:
            log("  %-45s bundle fetch failed: %s" % (key, p.err.strip()[:200]))
            return False
    else:
        _ensure_bare(bare, row["url"])
        p = _kit.run(["git", "-C", bare, "fetch", "-q", "--no-tags", "origin", sha], check=False)
        if p.returncode != 0 or not has_pin(bare, sha):
            # server refused a by-sha want: fetch branches, then the pin must be among them
            _kit.run(["git", "-C", bare, "fetch", "-q", "--no-tags", "origin", "+refs/heads/*:refs/remotes/origin/*"], check=False)
    if not has_pin(bare, sha):
        log("  %-45s FAIL pin %s not obtainable" % (key, sha[:12]))
        return False
    ok = _pin_ref(bare, sha)
    log("  %-45s %s %s" % (key, "fetched " if ok else "MISMATCH", sha[:12]))
    return ok


def bundle_out(root, row, outdir, log=print):
    bare = bare_path(root, row["key"])
    if not has_pin(bare, row["sha"]):
        log("  %-45s no local pin; bootstrap it first" % row["key"])
        return False
    os.makedirs(outdir, exist_ok=True)
    _pin_ref(bare, row["sha"])
    b = os.path.join(outdir, row["key"] + ".bundle")
    _kit.run(["git", "-C", bare, "bundle", "create", "-q", b, "refs/heads/pin"])
    v = _kit.run(["git", "-C", bare, "bundle", "verify", "-q", b], check=False)
    log("  %-45s bundle %s (%d bytes)%s" % (row["key"], b, os.path.getsize(b), "" if v.returncode == 0 else " VERIFY FAILED"))
    return v.returncode == 0


def run(root, rows, from_bundle=None, bundle_dir=None, log=print):
    ok = 0
    for r in rows:
        good = fetch_one(root, r, from_bundle, log)
        if good and bundle_dir:
            good = bundle_out(root, r, bundle_dir, log)
        ok += 1 if good else 0
    log("bootstrap: %d / %d pins present" % (ok, len(rows)))
    return 0 if ok == len(rows) else 1


def coverage(root, src, log=print):
    n = 0
    for s in src:
        h = has_pin(bare_path(root, s["key"]), s["sha"])
        n += h
        log("  %-45s %s" % (s["key"], "pin present" if h else "-"))
    log("bootstrap coverage: %d / %d registry rows have their pin in %s" % (n, len(src), _kit.upstream_cache(root)))
    return 0


# ------------------------------------------------------------------ selftest
def make_remote(tmp, name="o~r"):
    remote = os.path.join(tmp, "remote-" + name)
    _kit.run(["git", "init", "-q", "-b", "main", remote])
    _kit.fixture_git_config(remote)
    open(os.path.join(remote, "README.md"), "w").write("v1\n")
    open(os.path.join(remote, "LICENSE"), "w").write("MIT\n")
    _kit.stage_paths(remote)
    _kit.commit(remote, "v1")
    v1 = _kit.git_out(remote, "rev-parse", "HEAD")
    open(os.path.join(remote, "README.md"), "w").write("v2\n")
    _kit.stage_paths(remote)
    _kit.commit(remote, "v2")
    v2 = _kit.git_out(remote, "rev-parse", "HEAD")
    return remote, v1, v2


def make_kit_root(tmp, rows, homes=None, attic=None):
    root = os.path.join(tmp, "kit")
    os.makedirs(os.path.join(root, "registry"), exist_ok=True)
    _kit.write_json(os.path.join(root, "registry", "sources.json"), {"sources": rows})
    _kit.write_json(os.path.join(root, "registry", "homes.json"), {"homes": homes or []})
    _kit.write_json(os.path.join(root, "registry", "attic.json"), {"attic": attic or []})
    return root


def _selftest():
    os.environ.pop(_kit.CACHE_ENV, None)  # fixtures must never write to the operator's configured cache
    tmp = tempfile.mkdtemp(prefix="kit-boot-")
    quiet = lambda *a: None
    try:
        remote, v1, v2 = make_remote(tmp)
        url = "file://" + remote
        rows = [{"key": "o~r", "repo": "o/r", "url": url, "sha": v1},
                {"key": "o~bad", "repo": "o/bad", "url": url, "sha": "0" * 40}]
        homes = [{"key": "o~r", "lands": [{"station": "alpha", "how": "bootstrap"}]},
                 {"key": "o~bad", "lands": [{"station": "beta", "how": "repertoire"}]}]
        root = make_kit_root(tmp, rows, homes)
        src, h, a = load_registry(root)
        sel = select(src, h, a, station="alpha")
        assert [s["key"] for s in sel] == ["o~r"], sel
        assert run(root, sel, log=quiet) == 0, "pin v1 (not the tip) must be fetched"
        bare = bare_path(root, "o~r")
        assert _kit.run(["git", "-C", bare, "rev-parse", "--is-bare-repository"]).out.strip() == "true"
        assert _kit.run(["git", "-C", bare, "rev-parse", "pin"]).out.strip() == v1
        assert not os.path.exists(os.path.join(bare, "README.md")), "never checked out"
        assert run(root, sel, log=quiet) == 0, "idempotent"
        assert run(root, select(src, h, a, keys=["o~bad"]), log=quiet) == 1, "unobtainable pin must fail"
        try:
            select(src, h, a, keys=["nope"])
            raise AssertionError("unknown key accepted")
        except KeyError:
            pass
        bdir = os.path.join(tmp, "bundles")
        assert run(root, sel, bundle_dir=bdir, log=quiet) == 0
        assert os.path.isfile(os.path.join(bdir, "o~r.bundle"))
        root2 = make_kit_root(os.path.join(tmp, "second"), [dict(rows[0], url="https://invalid.example/none")], homes[:1])
        assert run(root2, select(*load_registry(root2), keys=["o~r"]), from_bundle=bdir, log=quiet) == 0, "offline bundle restore"
        assert _kit.run(["git", "-C", bare_path(root2, "o~r"), "rev-parse", "pin"]).out.strip() == v1
        assert run(root2, [dict(rows[0], key="o~r", sha=v2)], from_bundle=bdir, log=quiet) == 1, "bundle lacks v2"
        # --dry-run: no network, no writes, says present/absent
        lines = []
        root3 = make_kit_root(os.path.join(tmp, "third"), [dict(rows[0], url="https://invalid.example/none")], homes[:1])
        assert dry_run(root3, select(*load_registry(root3), station="alpha"), log=lines.append) == 0
        assert not os.path.exists(os.path.join(root3, ".upstream")), "dry-run wrote"
        assert any("absent (would fetch)" in l for l in lines) and "0 / 1" in lines[-1], lines
        lines = []
        dry_run(root, sel, log=lines.append)
        assert "1 / 1" in lines[-1], lines
        _selftest_shared_cache(tmp, url, v1)
        print("selftest OK")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _selftest_shared_cache(tmp, url, v1):
    """REPRODUCE F4: a bootstrap from the main checkout is seen from a linked worktree, and the reverse."""
    quiet = lambda *a: None
    rows = [{"key": "o~r", "repo": "o/r", "url": url, "sha": v1}]
    homes = [{"key": "o~r", "lands": [{"station": "alpha", "how": "bootstrap"}]}]
    kit = make_kit_root(os.path.join(tmp, "wt"), rows, homes)
    _kit.run(["git", "init", "-q", "-b", "main", kit])
    _kit.fixture_git_config(kit)
    open(os.path.join(kit, ".gitignore"), "w").write(".upstream/\n")
    _kit.stage_paths(kit)
    _kit.commit(kit, "m")
    _kit.git(kit, "branch", "station/alpha")
    wt = os.path.join(tmp, "wt-stations", "alpha")
    _kit.git(kit, "worktree", "add", "-q", wt, "station/alpha")
    assert os.path.realpath(_kit.upstream_cache(wt)) == os.path.realpath(os.path.join(kit, ".upstream")), _kit.upstream_cache(wt)
    assert run(kit, select(*load_registry(kit), keys=["o~r"]), log=quiet) == 0
    assert has_pin(bare_path(wt, "o~r"), v1), "pin fetched from the kit root must be visible in the worktree"
    lines = []
    coverage(wt, load_registry(wt)[0], log=lines.append)
    assert "1 / 1" in lines[-1], lines
    shutil.rmtree(os.path.join(kit, ".upstream"))
    assert run(wt, select(*load_registry(wt), keys=["o~r"]), log=quiet) == 0
    assert has_pin(bare_path(kit, "o~r"), v1) and not os.path.exists(os.path.join(wt, ".upstream")), "worktree bootstrap lands in the shared cache"
    alt = os.path.join(tmp, "alt-cache")
    os.environ[_kit.CACHE_ENV] = alt
    try:
        assert bare_path(wt, "o~r") == os.path.join(alt, "o~r.git"), "$STABLE_KIT_UPSTREAM overrides"
    finally:
        os.environ.pop(_kit.CACHE_ENV, None)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("keys", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--station")
    ap.add_argument("--attic", action="store_true")
    ap.add_argument("--root", default=_kit.REPO_ROOT_GUESS)
    ap.add_argument("--registry")
    ap.add_argument("--from-bundle")
    ap.add_argument("--bundle-out")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return _selftest()
    try:
        src, homes, attic = load_registry(a.root, a.registry)
        if a.list:
            return coverage(a.root, src)
        rows = select(src, homes, attic, a.keys, a.all, a.station, a.attic)
    except (OSError, ValueError, KeyError) as e:
        print("bootstrap: %s" % e)
        return 2
    if not rows:
        ap.print_help()
        return 2
    if a.dry_run:
        return dry_run(a.root, rows, a.from_bundle)
    try:
        return run(a.root, rows, a.from_bundle, a.bundle_out)
    except _kit.KitError as e:
        print("bootstrap: git failure: %s" % e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
