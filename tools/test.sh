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

for t in tests/*.keal; do
  name=$(basename "$t" .keal)
  sh tools/build.sh "$t" >/dev/null
  printf '%-8s ' "$name"
  "build/$name"
done

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
