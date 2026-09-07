#!/usr/bin/env python3
"""Measures the contrast of the site's colours, instead of looking at them.

    python3 ci/contrast.py

The identity states its contrast as a constraint rather than a suggestion —
`--dim` and `--prose` on `--bg` at 4.5:1, `--accent` on `--bg` at 7:1, `--bg`
on `--accent` at 7:1 — and a constraint nothing measures is a preference.
The link checker will catch a broken `assets/`; it will never catch a
paragraph nobody can read.

The arithmetic is WCAG 2.1's, which is eight lines: undo the sRGB transfer
curve, weight the channels, and compare the two luminances with the +0.05
that keeps the ratio finite at black.

The thresholds are the identity's, not this file's. If one fails, the answer
is a colour, not a smaller number here.
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Each pair is (foreground, background, least it may be, why it exists).
DEMANDS = [
    ("--ink", "--bg", 7.0, "body text"),
    ("--prose", "--bg", 4.5, "prose in the documents"),
    ("--dim", "--bg", 4.5, "the smaller text under a card"),
    ("--accent", "--bg", 7.0, "a link, and the wordmark's suffix"),
    ("--bg", "--accent", 7.0, "the text of a filled button"),
    ("--mint", "--bg", 4.5, "the pill, and the answer under a code block"),
    ("--code", "--panel", 4.5, "code, which is most of what this site shows"),
    ("--kw", "--panel", 4.5, "a keyword inside that code"),
    ("--ink", "--panel", 7.0, "a card's heading"),
    ("--dim", "--panel", 4.5, "a card's paragraph"),
]


def tokens(path):
    text = open(path, encoding="utf-8").read()
    block = text[text.index(":root {"):text.index("}", text.index(":root {"))]
    found = {}
    for name, value in re.findall(r"(--[a-z0-9-]+)\s*:\s*(#[0-9A-Fa-f]{6})", block):
        found[name] = value
    return found


def channel(v):
    v = v / 255
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def luminance(hex_colour):
    r, g, b = (int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def ratio(a, b):
    la, lb = luminance(a), luminance(b)
    if la < lb:
        la, lb = lb, la
    return (la + 0.05) / (lb + 0.05)


def main():
    found = tokens(os.path.join(ROOT, "site", "style.css"))
    missing = sorted({n for pair in DEMANDS for n in pair[:2]} - set(found))
    if missing:
        print("ci/contrast.py: site/style.css has no %s" % ", ".join(missing))
        sys.exit(1)

    failed = []
    rows = []
    for fg, bg, least, why in DEMANDS:
        got = ratio(found[fg], found[bg])
        ok = got >= least
        if not ok:
            failed.append((fg, bg, got, least, why))
        rows.append("  %-9s on %-8s %5.2f:1  needs %.1f  %s  %s"
                    % (fg, bg, got, least, "ok " if ok else "NO ", why))

    if "--quiet" not in sys.argv or failed:
        print("\n".join(rows))
    if failed:
        print()
        for fg, bg, got, least, why in failed:
            print("%s on %s is %.2f:1 and must be %.1f — %s." % (fg, bg, got, least, why))
        print("The answer is a colour, not a smaller number in ci/contrast.py.")
        sys.exit(1)
    if "--quiet" in sys.argv:
        print("%d pairs, every one above what the identity asks" % len(DEMANDS))


if __name__ == "__main__":
    main()
