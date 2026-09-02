#!/bin/sh
# tools/test.sh — build and run kealeb's checks.
#
#   tools/test.sh
#
# `units` needs no network: it holds the buffers, the encodings, the parser,
# the router, the renderer and the asset rules to their answers. `wire` starts
# a real server on a port the machine chooses and talks to it over a socket,
# which is the only way to check the framing.
set -e

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

# The same three places tools/build.sh looks, because the two must agree.
if [ -n "$KEAL" ]; then KEALC=$KEAL
elif [ -x "$ROOT/../keal/target/release/keal" ]; then KEALC=$ROOT/../keal/target/release/keal
elif command -v keal >/dev/null 2>&1; then KEALC=keal
else echo "no keal compiler found — set KEAL, or build ../keal" >&2; exit 1
fi

for t in tests/*.keal; do
  name=$(basename "$t" .keal)
  # lifetime is built with --audit below, and building it twice would say the
  # same thing twice while meaning less the second time.
  [ "$name" = "lifetime" ] && continue
  sh tools/build.sh "$t" >/dev/null
  printf '%-8s ' "$name"
  "build/$name"
done

# What an application leaves behind.
#
# The reason this step exists rather than an `assert` inside the program: the
# audit speaks *after* the program's last statement, so there is no moment at
# which the program could read its own verdict. An output is only attested
# when something outside consumes it, and this is that something. Copying this
# test without copying that reason gives a program that asserts nothing and
# passes.
printf '%-8s ' "lifetime"
mkdir -p build
( cd build && "$KEALC" build --audit "$ROOT/tests/lifetime.keal" -I"$ROOT/runtime" >/dev/null )
left=$(cd build && ./lifetime 2>&1)
echo "$left" | grep -q "nothing outlived the program" || {
  echo "FAILED — something outlived it:"
  echo "$left" | sed 's/^/  /'
  exit 1
}
echo "an application was built, used and dropped, and left nothing"

# The C the backend emits, read strictly.
#
# The miscompilation this framework found — a named function passed as a value,
# emitted as a bare pointer where a closure was expected — announced itself as
# one `cc` warning on every single build, for as long as it had existed, and
# nobody read it. So the warnings are read here, on purpose, and the one that
# means "the backend emitted code its own C compiler thinks is wrong" is an
# error. `keal build` does not do this and should not: a user's `native` block
# may legitimately warn. This checks what the *backend* wrote.
printf '%-8s ' "cc"
mkdir -p build
emitted=0
for t in tests/units.keal examples/todo.keal examples/counter.keal; do
  out="build/$(basename "$t" .keal).c"
  "$KEALC" emit-c "$t" -Iruntime > "$out"
  # The same five names keal's own corpus is held to. Three of them —
  # incompatible-pointer-types, implicit-function-declaration, int-conversion
  # — mean the backend contradicted itself. The other two are what keal-view's
  # bootstrap turned up.
  cc -fsyntax-only -std=c11 -Iruntime \
     -Werror=incompatible-pointer-types \
     -Werror=implicit-function-declaration \
     -Werror=int-conversion \
     -Werror=comment \
     -Werror=parentheses "$out"
  emitted=$((emitted + 1))
done
echo "$emitted translation units, no warning worth the name"

# The client is the one file that does not run under `keal`, so it is checked
# against a real server in the one runtime that can run it. No node, no check —
# and the suite says so rather than passing quietly.
if command -v node >/dev/null 2>&1; then
  sh tools/build.sh examples/counter.keal >/dev/null
  printf '%-8s ' "client"
  node tests/client.mjs
else
  echo "client   skipped — node not found, so the browser client is unchecked"
fi
