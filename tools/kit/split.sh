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
#   split.sh station/<x> <dest-dir> [remote-url]     (<x>, station/<x> or claude/stable-kit-<x>)
#     the station ref resolves like every kit tool (tools/kit/_kit.py station-ref): local station/<x>,
#     local claude/stable-kit-<x>, then remote-tracking <remote>/station/<x> or <remote>/claude/stable-kit-<x>
#     (a plain `git clone` of the kit has its stations only as remote-tracking refs - REPRODUCE F2)
#     git init <dest> ; fetch that ref into branch main ; remote `kit` -> the kit repo, fetching the
#     kit's resolved main ref into kit/main
#     optionally: git -C <dest> remote add origin <remote-url> && git push -u origin main
#   split.sh --selftest
# Exit 0 ok · 1 refused (dest not empty, branch missing) · 2 usage.
set -u
KIT_TOOLS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() { sed -n '2,17p' "$0"; exit 2; }

split() {
  local br="$1" dest="$2" remote="${3:-}" kit ref mref here="$KIT_TOOLS"
  kit="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "split: run inside the kit repo" >&2; return 2; }
  case "$br" in station/*|claude/stable-kit-*) ;; */*|"") echo "split: branch must be station/<x>, claude/stable-kit-<x> or <x>, got $br" >&2; return 2;; esac
  ref="$(python3 "$here/_kit.py" station-ref "$br" "$kit")" || { echo "split: no branch $br (looked for station/<x>, claude/stable-kit-<x>, local and remote-tracking)" >&2; return 1; }
  mref="$(python3 "$here/_kit.py" main-ref "$kit")" || { echo "split: the kit has no main (main or claude/stable-kit-main, local or remote-tracking)" >&2; return 1; }
  if [ -e "$dest" ] && [ -n "$(ls -A "$dest" 2>/dev/null)" ]; then echo "split: $dest exists and is not empty" >&2; return 1; fi
  git init -q -b main "$dest" || return 1
  git -C "$dest" fetch -q --no-tags "$kit" "$ref" || return 1
  git -C "$dest" checkout -q -B main FETCH_HEAD || return 1
  git -C "$dest" remote add kit "$kit" || return 1
  git -C "$dest" config remote.kit.fetch "+$mref:refs/remotes/kit/main"
  git -C "$dest" config remote.kit.tagOpt --no-tags
  if [ -n "$remote" ]; then
    git -C "$dest" remote add origin "$remote" && git -C "$dest" push -q -u origin main || return 1
  fi
  cat <<EOF
split: $br ($ref) -> $dest (branch main; remote kit -> $kit, kit/main <- $mref)
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
  ( cd "$k" && split station/alpha "$t/alpha" "$t/remote.git" ) >"$t/log" 2>&1 || { echo "selftest FAIL: split"; cat "$t/log"; exit 1; }
  [ "$(git -C "$t/alpha" symbolic-ref --short HEAD)" = main ] || { echo "selftest FAIL: branch not main"; exit 1; }
  [ "$(git -C "$t/alpha" branch --format='%(refname:short)' | wc -l)" -eq 1 ] || { echo "selftest FAIL: more than one branch"; exit 1; }
  [ -f "$t/alpha/station.json" ] || { echo "selftest FAIL: station file missing"; exit 1; }
  git -C "$t/alpha" remote get-url kit | grep -q "$k" || { echo "selftest FAIL: kit remote"; exit 1; }
  git -C "$t/remote.git" rev-parse -q --verify refs/heads/main >/dev/null || { echo "selftest FAIL: push to remote"; exit 1; }
  git -C "$t/alpha" fetch -q kit && git -C "$t/alpha" -c user.name=kit -c user.email=kit@localhost merge -q --no-edit kit/main \
    || { echo "selftest FAIL: fetch kit && merge kit/main"; exit 1; }
  grep -q v2 "$t/alpha/README.md" || { echo "selftest FAIL: commons update not merged"; exit 1; }
  # REPRODUCE F2: a plain clone (stations remote-tracking) and the hosted claude/stable-kit-* naming
  git clone -q "$k" "$t/plain" || exit 1
  git init -q --bare "$t/hosted.git"
  git -C "$k" -c push.negotiate=false push -q "$t/hosted.git" main:refs/heads/claude/stable-kit-main station/alpha:refs/heads/claude/stable-kit-alpha || exit 1
  git -C "$t/hosted.git" symbolic-ref HEAD refs/heads/claude/stable-kit-main
  git clone -q "$t/hosted.git" "$t/hosted" || exit 1
  local lay arg
  for lay in plain:station/alpha hosted:alpha hosted:claude/stable-kit-alpha; do
    arg="${lay#*:}"; lay="${lay%%:*}"
    rm -rf "$t/out"
    ( cd "$t/$lay" && split "$arg" "$t/out" ) >/dev/null 2>&1 || { echo "selftest FAIL: split $arg from layout $lay"; exit 1; }
    [ -f "$t/out/station.json" ] && [ "$(git -C "$t/out" symbolic-ref --short HEAD)" = main ] || { echo "selftest FAIL: layout $lay content"; exit 1; }
    git -C "$t/out" fetch -q kit && git -C "$t/out" -c user.name=kit -c user.email=kit@localhost merge -q --no-edit kit/main \
      || { echo "selftest FAIL: layout $lay fetch kit && merge kit/main"; exit 1; }
    grep -q v2 "$t/out/README.md" || { echo "selftest FAIL: layout $lay commons update not merged"; exit 1; }
  done
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
