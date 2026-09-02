#!/bin/sh
# tools/test.sh — build and run kealeb's checks.
#
#   tools/test.sh
#
# Six steps, and two of them are controls.
#
#   guide     every snippet the guide promises, compiled
#   units     the buffers, encodings, parser, router, renderer and diff
#   lifetime  an application built, used, dropped — and leaving nothing
#   leaks     a cycle built on purpose, which the audit must still see
#   cc        the C the backend emitted, read under five -Werror names,
#             each of which is first handed a fault it must refuse
#   client    the real client script, against a real server, over a socket
#
# `lifetime` and `cc` both assert negatives, and a negative goes green the
# moment the instrument stops working. `leaks` and the fault files are what
# say the instruments still work. A suite that only ever checks for the
# absence of a thing needs something that checks it can still find one.
#
# One property this file must keep, stated because it is easy to lose by
# accident and impossible to notice when it goes: **every binary run here is
# one a build asserted immediately before**. `set -e` and a build step in front
# of each run are what give that, so a leftover executable from an earlier run
# cannot be the thing that passes. Checked by planting six of them and a
# failing build: all six were overwritten, and the failing build stopped the
# suite instead of running what was already there. Anything added below should
# keep that shape.
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
  # Both of these are built with --audit below; building them twice would say
  # the same thing twice while meaning less the second time.
  [ "$name" = "lifetime" ] && continue
  [ "$name" = "leaks" ] && continue
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

# The control for the step above.
#
# `lifetime` asserts a negative, and a negative goes green the moment the
# instrument stops working: if `--audit` ever stopped finding cycles, it would
# pass while every leak went unreported. So `leaks` builds the cycle on
# purpose and this requires the audit to still see it — and to see exactly
# one, since the pair in that file differ only in what their closure holds.
# `2 Table` would mean it stopped telling them apart, which is the other
# direction of the same failure.
printf '%-8s ' "leaks"
( cd build && "$KEALC" build --audit "$ROOT/tests/leaks.keal" -I"$ROOT/runtime" >/dev/null )
found=$(cd build && ./leaks 2>&1)
{ echo "$found" | grep -q "^  1 Table$" && echo "$found" | grep -q "a cycle"; } || {
  echo "FAILED — the audit no longer sees a cycle it is standing in front of:"
  echo "$found" | sed 's/^/  /'
  exit 1
}
echo "a cycle built on purpose is still reported as exactly one"

# The C the backend emits, read strictly.
#
# The miscompilation this framework found — a named function passed as a value,
# emitted as a bare pointer where a closure was expected — announced itself as
# one `cc` warning on every single build, for as long as it had existed, and
# nobody read it. So the warnings are read here, on purpose, and the one that
# means "the backend emitted code its own C compiler thinks is wrong" is an
# error. `keal build` does not do this and should not: a user's `native` block
# may legitimately warn. This checks what the *backend* wrote.
# The five names, written once.
#
# Everything below is built from this list: the flags the emitted C is
# compiled under, and the fault each name must refuse. Two lists would let one
# drift from the other — proving a flag nobody uses, or using one nobody
# proved — and the drift is invisible because both halves stay green.
STRICT="incompatible-pointer-types implicit-function-declaration int-conversion
        comment parentheses"

# The smallest C that commits exactly one of those errors. A name with no
# fault written for it is a name this step cannot prove, so it is refused
# rather than skipped.
fault() {
  case $1 in
    incompatible-pointer-types)
      printf 'int f(long x){return (int)x;}\nint g(void){int(*p)(void)=f;return p();}\n' ;;
    implicit-function-declaration)
      printf 'int g(void){return nosuchfn();}\n' ;;
    int-conversion)
      printf 'int *g(void){return 1;}\n' ;;
    comment)
      printf '/* /* */\nint g(void){return 0;}\n' ;;
    parentheses)
      printf 'int g(int a,int b){ if (a = b) return 1; return 0; }\n' ;;
    *)
      # On stderr: this function's standard output is the fault file itself,
      # and a diagnostic written there would be compiled instead of read.
      echo "FAILED — no fault is written for -Werror=$1, so nothing proves it" >&2
      echo "  bites. Either write one beside the others, or fix the spelling" >&2
      echo "  in STRICT — a misspelt name arrives here, because a name that" >&2
      echo "  is not one of the five has no fault of its own." >&2
      return 1 ;;
  esac
}

printf '%-8s ' "cc"
mkdir -p build/probe

# The control comes first: a flag that rejects nothing lets everything past,
# so there is no point compiling anything under a barrier that has not been
# shown to be one. `cc` accepts an unknown -Werror= name with a warning and
# exits 0, so a misspelling would otherwise be a barrier made of nothing.
proven=0
for name in $STRICT; do
  fault "$name" > "build/probe/$name.c" || { echo; exit 1; }
  if cc -fsyntax-only -std=c11 "-Werror=$name" "build/probe/$name.c" 2>/dev/null; then
    echo "FAILED — cc accepted this under -Werror=$name:"
    sed 's/^/    /' "build/probe/$name.c"
    echo "  Two things can cause that and this test cannot tell them apart:"
    echo "  the compiler has the name and ignores it, or what is printed above"
    echo "  stopped being a fault. Read it — if it still commits the error the"
    echo "  name describes, the flag is the problem. Either way the barrier"
    echo "  below is made of nothing until it is explained."
    exit 1
  fi
  proven=$((proven + 1))
done

flags=""
for name in $STRICT; do flags="$flags -Werror=$name"; done

emitted=0
for t in tests/units.keal examples/todo.keal examples/counter.keal; do
  out="build/$(basename "$t" .keal).c"
  "$KEALC" emit-c "$t" -Iruntime > "$out"
  # shellcheck disable=SC2086
  if ! cc -fsyntax-only -std=c11 -Iruntime $flags "$out" 2>build/probe/cc.err; then
    echo "FAILED — the backend emitted C that its own C compiler objects to,"
    echo "  compiling $t. This is the step that would have caught a named"
    echo "  function passed as a value being emitted as a bare pointer, which"
    echo "  is what it was written for. What cc said about $out:"
    if [ -s build/probe/cc.err ]; then
      sed 's/^/  /' build/probe/cc.err
    else
      echo "  nothing at all — cc refused without a diagnostic, which is a"
      echo "  second bug on top of the first and the more surprising of the two."
    fi
    exit 1
  fi
  emitted=$((emitted + 1))
done

echo "$proven flags each refuse their own fault, and $emitted translation units draw none of them"

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
