# UNZIP — restore stable-kit
1. `unzip stable-kit.zip` (keeps `stable-kit/` with its `.git`, plus `stable-kit.bundle` and this file).
2. `git -C stable-kit fsck` — must report no errors.
3. `git -C stable-kit branch` — must list `main` and 8 `station/*` branches (9 in all; the zip carries no remotes).
4. `cd stable-kit && python3 tools/kit/doctor.py` — report only: tools, worktrees, bootstrap coverage.
5. Start a station: `git worktree add ~/stations/<x> station/<x>`, then open Claude in `~/stations/<x>`.
6. Big upstreams, when online: `python3 tools/kit/bootstrap.py --station <x> --dry-run` (preview), then without `--dry-run` (or `--all`). One cache serves the kit root and every station worktree.
7. If step 2 or 3 fails (an unzip tool dropped `.git` files): `git clone stable-kit.bundle stable-kit-restored`
8. then `git -C stable-kit-restored fetch --update-head-ok origin 'refs/heads/*:refs/heads/*'` to get all 9 branches locally (`--update-head-ok`: the clone has `main` checked out, which a plain fetch refuses to update).
9. Secrets: fill the empty values in each station's `.env`; they are yours to commit on your private copy.
10. Where to go next: `README.md` (decision tree) and `KIT.md` (how sync, repin, split and zip work).
