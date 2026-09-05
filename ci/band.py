#!/usr/bin/env python3
"""Keeps the badge band at the top of README.md current.

    python3 ci/band.py            rewrite it
    python3 ci/band.py --check    fail if it would change

Two numbers, and both are counted here rather than remembered: the version,
which is the one in `keal.toml` because that is what `keal add` pins, and the
share of this framework that is Keal, which is the README's own claim and the
one a reader is entitled to check.

Keal's own band is deliberately **not** gated in its test suite, and the reason
is worth repeating so that the difference here is a decision rather than an
oversight: its second number counts `.keal` files across every repository the
owner has, so it goes stale on its own and a gate would turn an unrelated push
red. Everything this band counts is in this repository, so it can only go stale
when somebody here changes something — which is exactly when a gate should
speak. `tools/test.sh` runs `--check`.
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
START = "<!-- kealeb-band:start -->"
END = "<!-- kealeb-band:end -->"
SHIELD = ("https://img.shields.io/badge/%s-%s-blue"
          "?style=flat-square&labelColor=2b2b2b")


def read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


def version():
    for line in read("keal.toml").splitlines():
        m = re.match(r'\s*version\s*=\s*"([^"]+)"', line)
        if m:
            return m.group(1)
    raise SystemExit("ci/band.py: keal.toml has no version")


def lines():
    """Keal, C and JavaScript, counted the same way the README's table is."""
    keal = sum(len(read("src/" + n).splitlines())
               for n in sorted(os.listdir(os.path.join(ROOT, "src"))) if n.endswith(".keal"))
    keal += len(read("kealeb.keal").splitlines())
    c = sum(len(read("runtime/" + n).splitlines())
            for n in sorted(os.listdir(os.path.join(ROOT, "runtime"))) if n.endswith(".h"))
    live = read("src/live.keal")
    at = live.index('clientScript: String = """')
    at = live.index("\n", at) + 1
    js = len(live[at:live.index('\n"""', at)].splitlines())
    return keal, c, js


def band():
    keal, c, js = lines()
    share = round((keal * 100) / (keal + c + js))
    releases = "https://github.com/geneacta/kealeb/releases"
    files = "https://github.com/geneacta/kealeb/tree/main/src"
    return "\n".join([
        START,
        '<p align="center">',
        '  <a href="%s"><img alt="version" src="%s"></a>'
        % (releases, SHIELD % ("version", version())),
        '  <a href="%s"><img alt="written in Keal" src="%s"></a>'
        % (files, SHIELD % ("written%20in%20Keal", "%d%%25" % share)),
        "</p>",
        END,
    ])


def main():
    path = os.path.join(ROOT, "README.md")
    text = read("README.md")
    if START not in text or END not in text:
        raise SystemExit("ci/band.py: README.md has no %s … %s markers" % (START, END))
    before = text[:text.index(START)]
    after = text[text.index(END) + len(END):]
    now = before + band() + after

    if "--check" in sys.argv:
        if now != text:
            print("ci/band.py: the badge band in README.md is out of date.")
            print("  Run python3 ci/band.py and commit what changes.")
            sys.exit(1)
        print("the badge band says what the repository says")
        return

    if now == text:
        print("the badge band was already current")
        return
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(now)
    print("rewrote the badge band in README.md")


if __name__ == "__main__":
    main()
