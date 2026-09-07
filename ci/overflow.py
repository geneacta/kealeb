#!/usr/bin/env python3
"""Measures whether the site's pages fit in the window, instead of assuming it.

    python3 ci/overflow.py            every page at every width
    python3 ci/overflow.py --quiet    one line unless something overflows

A page that scrolls sideways on a phone looks fine in the file, fine in the
markup and fine on a laptop. Nothing else here can see it: the link checker
reads hrefs, the contrast checker reads colours, and neither of them lays
anything out. So this asks the browser, which is the only thing that knows —
`document.documentElement.scrollWidth` against `clientWidth`.

It found two the day it was written, both from one cause: a grid item keeps
`min-width: auto`, so it never shrinks below its own min-content and spills
out of its track. The guide was 780px wide in a 485px window.

**Why the pages are measured inside iframes.** A headless Chrome will not open
a window narrower than 500 points — ask for 360 and `clientWidth` still says
485. The first version of this file did ask for 360, and reported that it
passed at a width it had never rendered. An iframe has a viewport of its own,
media queries and all, so a 390-wide iframe in a wide window is a real 390-wide
page. That needs `--allow-file-access-from-files`, since the frame and the page
are both `file://`; without it the frame reads as cross-origin and this fails
rather than passing quietly.

The frame is written into `site/` because the stylesheet, the fonts and the
logo are relative — a copy in a temporary directory renders unstyled, which
measures nothing and passes. It is removed even when a render fails.

This reports an absence, and a check for an absence passes the moment it stops
looking — so `--control` puts a 2400px block into every page and requires every
one of them to fail. `tools/test.sh` runs both.

No Chrome, no check: this skips rather than fails, the way the JavaScript step
does when there is no node. A machine without a browser is not a broken build.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import html as html_mod

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")

# Relative to site/, because that is where the frame is written.
PAGES = ["index.html", "guide.html", "examples.html",
         "fr/index.html", "fr/guide.html", "fr/examples.html"]

# A small phone, a large one, a tablet, and a laptop. 390 is where the two
# defects that prompted this file lived.
WIDTHS = [390, 500, 768, 1280]

CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]

FRAME = """<!doctype html><meta charset="utf-8"><title>measuring</title>
<style>html, body { margin: 0 } iframe { border: 0; display: block }</style>
<div id="frames">%(frames)s</div>
<pre id="kb-out"></pre>
<script>
var want = %(count)d, seen = 0;
Array.prototype.forEach.call(document.querySelectorAll('iframe'), function (f) {
  f.addEventListener('load', function () { if (++seen === want) setTimeout(report, 700); });
});
function report() {
  var all = [];
  // The control. This check reports the absence of something, and a check for
  // an absence goes green the moment it stops working — a typo in the selector,
  // a frame that never loaded, a browser that changed how it reports width, and
  // it passes forever while seeing nothing. So `--control` puts a block wider
  // than any window into every page first: every row must then fail. One that
  // passes means the instrument is blind, not that the page is fine.
  if (%(control)s) {
    Array.prototype.forEach.call(document.querySelectorAll('iframe'), function (f) {
      var d = f.contentDocument.createElement('div');
      d.style.cssText = 'width:2400px;height:1px';
      f.contentDocument.body.appendChild(d);
    });
  }
  Array.prototype.forEach.call(document.querySelectorAll('iframe'), function (f) {
    var row = { page: f.dataset.page, asked: Number(f.getAttribute('width')) };
    try {
      var d = f.contentDocument.documentElement, limit = d.clientWidth, over = [];
      var win = f.contentWindow;
      // A wide line inside a `pre` that scrolls is not a defect — it is the
      // `pre` doing its job. Only an element no ancestor will clip is one the
      // reader has to scroll the whole page for, so the ones under a scroll
      // container are dropped. Reporting them buries the element that is
      // actually too wide under four that are fine.
      function clipped(e) {
        for (var p = e.parentElement; p; p = p.parentElement) {
          var o = win.getComputedStyle(p).overflowX;
          if (o === 'auto' || o === 'scroll' || o === 'hidden') { return true; }
        }
        return false;
      }
      f.contentDocument.querySelectorAll('*').forEach(function (e) {
        var r = e.getBoundingClientRect();
        if ((r.right > limit + 0.5 || r.width > limit + 0.5) && !clipped(e)) {
          over.push({ t: e.tagName.toLowerCase(),
                      c: (typeof e.className === 'string' ? e.className.trim() : ''),
                      w: Math.round(r.width), r: Math.round(r.right) });
        }
      });
      over.sort(function (a, b) { return b.w - a.w; });
      row.scroll = d.scrollWidth; row.client = limit; row.over = over.slice(0, 4);
    } catch (e) { row.error = String(e.message || e); }
    all.push(row);
  });
  document.getElementById('kb-out').textContent = 'KB-START' + JSON.stringify(all) + 'KB-END';
}
</script>
"""


def browser():
    for path in CANDIDATES:
        if os.path.exists(path):
            return path
    for name in ("google-chrome", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    return None


def render(chrome, control=False):
    """One launch, every page at every width, laid out for real."""
    frames = "".join(
        '<iframe data-page="%s" src="%s" width="%d" height="900"></iframe>' % (page, page, width)
        for page in PAGES for width in WIDTHS)
    path = os.path.join(SITE, ".overflow-frame.html")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(FRAME % {"frames": frames, "count": len(PAGES) * len(WIDTHS),
                        "control": "true" if control else "false"})
    try:
        out = subprocess.run(
            [chrome, "--headless", "--disable-gpu", "--no-sandbox",
             # A CI container's /dev/shm is 64MB, which Chrome runs out of.
             "--disable-dev-shm-usage",
             "--allow-file-access-from-files", "--window-size=1600,1000",
             "--virtual-time-budget=25000", "--dump-dom", "file://" + path],
            capture_output=True, text=True, timeout=180).stdout
    finally:
        os.remove(path)
    m = re.search(r"KB-START(.*?)KB-END", out, re.S)
    if not m:
        raise SystemExit("ci/overflow.py: the pages never reported their width. "
                         "Nothing was measured, so nothing is known — this is a "
                         "failure of the check, not a pass.")
    return json.loads(html_mod.unescape(m.group(1)))


def describe(node):
    name = node["t"] + ("." + ".".join(node["c"].split()) if node["c"] else "")
    return "%s (%dpx wide, ends at %d)" % (name, node["w"], node["r"])


def main():
    chrome = browser()
    if chrome is None:
        print("no Chrome on this machine, so the layout was not measured")
        return

    if "--control" in sys.argv:
        blind = [row for row in render(chrome, control=True)
                 if "error" not in row and row["scroll"] <= row["client"]]
        if blind:
            for row in blind:
                print("%s at %dpx was given a 2400px block and still measured %dpx."
                      % (row["page"], row["client"], row["scroll"]))
            raise SystemExit("ci/overflow.py: the check cannot see an overflow it "
                             "made itself, so its green means nothing.")
        print("control: every page reports the overflow put into it")
        return

    quiet = "--quiet" in sys.argv
    rows, bad, broken = [], [], []
    for row in render(chrome):
        if "error" in row:
            broken.append(row)
            continue
        fits = row["scroll"] <= row["client"]
        if not fits:
            bad.append(row)
        rows.append("  %-18s asked %-5d rendered %-5d  scroll %-5d  %s"
                    % (row["page"], row["asked"], row["client"], row["scroll"],
                       "ok" if fits else "SCROLLS SIDEWAYS"))

    if broken:
        for row in broken:
            print("%s at %dpx could not be read: %s" % (row["page"], row["asked"], row["error"]))
        raise SystemExit("ci/overflow.py: the frame could not reach the pages it framed.")

    if not quiet or bad:
        print("\n".join(rows))
    if bad:
        print()
        for row in bad:
            print("%s at %dpx: the page is %dpx wide in a %dpx window."
                  % (row["page"], row["client"], row["scroll"], row["client"]))
            for node in row["over"]:
                print("    %s" % describe(node))
        print("A grid or flex item that will not shrink usually wants "
              "`min-width: 0`; a wide block usually wants `overflow-x: auto`.")
        sys.exit(1)
    if quiet:
        print("%d pages at %s points, none scrolls sideways"
              % (len(PAGES), ", ".join(str(w) for w in WIDTHS)))


if __name__ == "__main__":
    main()
