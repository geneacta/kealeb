#!/bin/sh
# tools/build.sh — compile a kealeb program to a native executable.
#
#   tools/build.sh examples/hello.keal
#   build/hello
#
# Anything after the source file is passed to `keal build`. A program that
# imports `src/sql.keal` needs the one library kealeb does not vendor:
#
#   tools/build.sh examples/notes.keal -lsqlite3
#
# There is no platform object to compile first: kealeb's whole C surface is
# `static inline` in runtime/kb.h, which `keal build` pastes into the program
# it is already compiling. So this script picks a compiler, points it at the
# header, and gets out of the way.
set -e

ROOT=$(cd "$(dirname "$0")/.." && pwd)
SRC=${1:?usage: tools/build.sh path/to/app.keal [extra keal build args...]}
[ -f "$SRC" ] || { echo "no such file: $SRC" >&2; exit 1; }
shift
SRC=$(cd "$(dirname "$SRC")" && pwd)/$(basename "$SRC")
NAME=$(basename "$SRC" .keal)
OUT=$ROOT/build
mkdir -p "$OUT"

# The compiler: $KEAL wins, then a checked-out sibling, then the path.
if [ -n "$KEAL" ]; then :
elif [ -x "$ROOT/../keal/target/release/keal" ]; then KEAL=$ROOT/../keal/target/release/keal
elif command -v keal >/dev/null 2>&1; then KEAL=keal
else echo "no keal compiler found — set KEAL, or build ../keal" >&2; exit 1
fi

case $(uname -s) in
  Darwin|Linux|*BSD) : ;;
  *) echo "kealeb has no socket layer for $(uname -s) yet — POSIX only" >&2; exit 1 ;;
esac

# `keal build` writes the executable, and the C it generated, into the working
# directory under the source file's stem — so it runs in the output directory.
# Anything after the source file goes to `keal build` as it was written, which
# is how a program that imports `src/sql.keal` says `-lsqlite3`. The script
# does not guess: linking a library nobody asked for is worse than a missing
# flag, which at least says which symbol it wanted.
echo "keal $(basename "$SRC")"
cd "$OUT"
"$KEAL" build "$SRC" -I"$ROOT/runtime" "$@"
echo "→ build/$NAME"
