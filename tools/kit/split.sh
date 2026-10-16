#!/usr/bin/env bash
# split.sh - turn one station branch into its own one-branch repo (a convenience).
#
# Earned by: the operator may want a station in its own private repo later
# (ORDER 4: "i will end up for private use putting it on a different repo";
# ORDER 5: "a branch is not a security boundary" - "i dont care about this
# because im going local then placing things myself later"). This keeps the way
# back: the split repo keeps a `kit` remote, so `git fetch kit && git merge kit/main`
# still syncs the commons. Retires: nothing.
#
#   split.sh station/<x> <dest-dir> [remote-url]
#     git clone --single-branch -b station/<x> <kit-repo> <dest>
#     git -C <dest> branch -m main ; remote `origin` renamed to `kit` (-> the kit repo path)
#     optionally: git -C <dest> remote add origin <remote-url> && git push -u origin main
#   split.sh --selftest
# Exit 0 ok · 1 refused (dest not empty, branch missing) · 2 usage.
set -u

usage() { sed -n '2,17p' "$0"; exit 2; }

split() {
  local br="$1" dest="$2" remote="${3:-}" kit
  kit="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "split: run inside the kit repo" >&2; return 2; }
  case "$br" in station/*) ;; *) echo "split: branch must be station/<x>, got $br" >&2; return 2;; esac
  git -C "$kit" rev-parse --verify -q "refs/heads/$br" >/dev/null || { echo "split: no branch $br" >&2; return 1; }
  if [ -e "$dest" ] && [ -n "$(ls -A "$dest" 2>/dev/null)" ]; then echo "split: $dest exists and is not empty" >&2; return 1; fi
  git clone -q --single-branch -b "$br" "$kit" "$dest" || return 1
  git -C "$dest" branch -m main || return 1
  git -C "$dest" remote rename origin kit || return 1
  git -C "$dest" config remote.kit.fetch '+refs/heads/main:refs/remotes/kit/main'
  git -C "$dest" config --unset branch.main.remote >/dev/null 2>&1 || true
  git -C "$dest" config --unset branch.main.merge >/dev/null 2>&1 || true
  if [ -n "$remote" ]; then
    git -C "$dest" remote add origin "$remote" && git -C "$dest" push -q -u origin main || return 1
  fi
  cat <<EOF
split: $br -> $dest (branch main; remote kit -> $kit)
  commons drift in the split repo is checked against commons/MANIFEST.json (tools/station_audit.py -k commons_drift)
  sync the commons later:  git -C $dest fetch kit && git -C $dest merge kit/main   (then python3 tools/kit/sync.py --main kit/main for GENERATED conflicts)
  this is a convenience, not a boundary (ORDER 5).
EOF
}

selftest() {
  local t; t="$(mktemp -d)" || exit 2
  trap 'rm -rf "$t"' EXIT
  local k="$t/kit"
  git init -q -b main "$k" && git -C "$k" config user.name kit && git -C "$k" config user.email kit@localhost && git -C "$k" config commit.gpgsign false
  echo main > "$k/README.md"; git -C "$k" add -- README.md; git -C "$k" commit -q -m main
  git -C "$k" switch -q -c station/alpha
  echo '{"name":"alpha"}' > "$k/station.json"; git -C "$k" add -- station.json; git -C "$k" commit -q -m alpha
  git -C "$k" switch -q main
  echo v2 > "$k/README.md"; git -C "$k" add -- README.md; git -C "$k" commit -q -m "main v2"
  git init -q --bare "$t/remote.git"
  ( cd "$k" && split station/alpha "$t/alpha" "$t/remote.git" ) >/dev/null 2>&1 || { echo "selftest FAIL: split"; exit 1; }
  [ "$(git -C "$t/alpha" symbolic-ref --short HEAD)" = main ] || { echo "selftest FAIL: branch not main"; exit 1; }
  [ "$(git -C "$t/alpha" branch --format='%(refname:short)' | wc -l)" -eq 1 ] || { echo "selftest FAIL: more than one branch"; exit 1; }
  [ -f "$t/alpha/station.json" ] || { echo "selftest FAIL: station file missing"; exit 1; }
  git -C "$t/alpha" remote get-url kit | grep -q "$k" || { echo "selftest FAIL: kit remote"; exit 1; }
  git -C "$t/remote.git" rev-parse -q --verify refs/heads/main >/dev/null || { echo "selftest FAIL: push to remote"; exit 1; }
  git -C "$t/alpha" fetch -q kit && git -C "$t/alpha" -c user.name=kit -c user.email=kit@localhost merge -q --no-edit kit/main \
    || { echo "selftest FAIL: fetch kit && merge kit/main"; exit 1; }
  grep -q v2 "$t/alpha/README.md" || { echo "selftest FAIL: commons update not merged"; exit 1; }
  if ( cd "$k" && split station/alpha "$t/alpha" ) >/dev/null 2>&1; then echo "selftest FAIL: non-empty dest accepted"; exit 1; fi
  if ( cd "$k" && split station/nope "$t/nope" ) >/dev/null 2>&1; then echo "selftest FAIL: missing branch accepted"; exit 1; fi
  echo "selftest OK"
  exit 0
}

case "${1:-}" in
  --selftest) selftest ;;
  ""|-h|--help) usage ;;
  *) [ $# -ge 2 ] || usage; split "$@"; exit $? ;;
esac
