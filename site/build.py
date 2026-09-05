#!/usr/bin/env python3
"""Builds the kealeb site, in English and in French.

    python3 site/build.py
    python3 site/build.py --external    the same, plus following the links out

Three pages in each language — the landing page, the guide, and the
examples — generated from the documents in this repository, so the site
cannot say something the repository does not. English lands in `site/`,
French in `site/fr/`.

The dress is Keal's, deliberately: the same tokens, the same shape of nav
and footer, so the two read as one family and a person who has seen one
knows where things are in the other. The markdown converter below is Keal's
too, adapted — `site/build.py` in that repository is where it was written,
and this is a copy rather than a dependency because a site should build with
nothing checked out beside it.

No dependencies and no build step beyond this file: the output is plain
HTML that GitHub Pages serves as it stands.
"""

import html
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
GITHUB = "https://github.com/geneacta/kealeb/blob/main/"
BASE_URL = "https://geneacta.github.io/kealeb/"
# Keal's site, per language. A French reader sent to an English page is a seam
# nobody sees while writing it and everybody feels while reading — Keal found
# it on its side first, pointing both of its cards at our English half, and
# this was the same mistake facing the other way.
KEAL_SITE = {"en": "https://geneacta.github.io/keal/",
             "fr": "https://geneacta.github.io/keal/fr/"}


INLINE_CODE = re.compile(r"`([^`]+)`")
BOLD = re.compile(r"\*\*([^*]+)\*\*")
ITALIC = re.compile(r"(?<![*\w])\*([^*\n]+)\*(?!\*)")
LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def slug(text):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "section"


def fix_href(href, lang="en"):
    """Repoint a repository-relative link at the page the site generates."""
    if href.startswith(("http://", "https://", "#", "mailto:")):
        return href
    anchor = ""
    if "#" in href:
        href, anchor = href.split("#", 1)
        anchor = "#" + anchor
    base = os.path.basename(href)
    if base.endswith(".md"):
        name = base[:-3]
        # A document under `docs/` is meant to have a page here. One that is
        # not in this table has no page, and the old fallback — send it to the
        # index — is worse than a broken link: it resolves, so nothing catches
        # it, and it points somewhere the text did not say. Keal's site had
        # three of those in production, found by exactly this check. So the
        # missing case stops the build instead.
        pages = {"guide": "guide.html", "guide.fr": "guide.html", "README": "index.html"}
        if name in pages:
            return pages[name] + anchor
        if href.replace("../", "").startswith("docs/"):
            raise SystemExit(
                "site/build.py: %s is under docs/ and has no page here.\n"
                "  Either give it one, or take the link out. Sending it to the index\n"
                "  would resolve and be wrong, which nothing would catch." % href)
        return GITHUB + href.lstrip("./") + anchor
    if base.endswith(".keal"):
        return "examples.html#" + slug(base[:-5]) if "examples/" in href else GITHUB + href.lstrip("./")
    # Anything else still lives in the repository.
    return GITHUB + href.lstrip("./") + anchor


def inline(text):
    out = html.escape(text, quote=False)
    # Code spans first, so nothing inside them is re-read as markup.
    holes = []

    def stash(m):
        holes.append(m.group(1))
        return "\x00%d\x00" % (len(holes) - 1)

    out = INLINE_CODE.sub(stash, out)
    out = BOLD.sub(r"<strong>\1</strong>", out)
    out = ITALIC.sub(r"<em>\1</em>", out)
    out = LINK.sub(lambda m: '<a href="%s">%s</a>' % (fix_href(m.group(2)), m.group(1)), out)
    for i, code in enumerate(holes):
        out = out.replace("\x00%d\x00" % i, "<code>%s</code>" % code)
    return out


def markdown(text):
    """Markdown to HTML, plus the table of contents entries it passes."""
    lines = text.split("\n")
    out, toc = [], []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            lang = line[3:].strip()
            body = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                body.append(lines[i])
                i += 1
            i += 1
            cls = " class=\"lang-%s\"" % lang if lang else ""
            out.append('<pre%s><code>%s</code></pre>' % (cls, html.escape("\n".join(body))))
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            level, title = len(m.group(1)), m.group(2).strip()
            anchor = slug(re.sub(r"`", "", title))
            out.append("<h%d id=\"%s\">%s</h%d>" % (level, anchor, inline(title), level))
            if level == 2:
                toc.append((anchor, re.sub(r"`", "", title)))
            i += 1
            continue
        if re.match(r"^---+\s*$", line):
            out.append("<hr>")
            i += 1
            continue
        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|?\s*$", lines[i + 1]):
            head = [c.strip() for c in line.strip().strip("|").split("|")]
            i += 2
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            t = ["<div class=\"tablewrap\"><table><thead><tr>"]
            t += ["<th>%s</th>" % inline(c) for c in head]
            t.append("</tr></thead><tbody>")
            for r in rows:
                t.append("<tr>" + "".join("<td>%s</td>" % inline(c) for c in r) + "</tr>")
            t.append("</tbody></table></div>")
            out.append("".join(t))
            continue
        if re.match(r"^\s*[-*]\s+", line):
            items, indent_stack = [], None
            while i < len(lines) and (re.match(r"^\s*[-*]\s+", lines[i]) or (lines[i].startswith("  ") and lines[i].strip() and items)):
                if re.match(r"^\s*[-*]\s+", lines[i]):
                    items.append(re.sub(r"^\s*[-*]\s+", "", lines[i]))
                else:
                    items[-1] += " " + lines[i].strip()
                i += 1
            _ = indent_stack
            out.append("<ul>" + "".join("<li>%s</li>" % inline(x) for x in items) + "</ul>")
            continue
        if re.match(r"^\s*\d+\.\s+", line):
            items = []
            while i < len(lines) and (re.match(r"^\s*\d+\.\s+", lines[i]) or (lines[i].startswith("   ") and lines[i].strip() and items)):
                if re.match(r"^\s*\d+\.\s+", lines[i]):
                    items.append(re.sub(r"^\s*\d+\.\s+", "", lines[i]))
                else:
                    items[-1] += " " + lines[i].strip()
                i += 1
            out.append("<ol>" + "".join("<li>%s</li>" % inline(x) for x in items) + "</ol>")
            continue
        if line.startswith(">"):
            body = []
            while i < len(lines) and lines[i].startswith(">"):
                body.append(lines[i].lstrip(">").strip())
                i += 1
            out.append("<blockquote>%s</blockquote>" % inline(" ".join(body)))
            continue
        if not line.strip():
            i += 1
            continue
        para = []
        while i < len(lines) and lines[i].strip() and not lines[i].startswith(("#", "```", "|", ">")) \
                and not re.match(r"^\s*[-*]\s+", lines[i]) and not re.match(r"^\s*\d+\.\s+", lines[i]) \
                and not re.match(r"^---+\s*$", lines[i]):
            para.append(lines[i])
            i += 1
        if not para:
            # A line that opens no block and cannot start a paragraph — a
            # stray table row, a `#` without its space — would otherwise be
            # read forever. Take it as text and move on.
            para.append(lines[i])
            i += 1
        out.append("<p>%s</p>" % inline(" ".join(para)))
    return "\n".join(out), toc


# ---- page chrome ---------------------------------------------------------

NAV = {
    "en": [("index.html", "Home"), ("guide.html", "Guide"), ("examples.html", "Examples")],
    "fr": [("index.html", "Accueil"), ("guide.html", "Le guide"), ("examples.html", "Exemples")],
}

FOOTER = {
    "en": ("A web framework for Keal: routes, pages, and state that stays on the server. Built by Geneacta.",
           "Source on GitHub", "The Keal language", "Issues"),
    "fr": ("Un cadriciel web pour Keal : des routes, des pages, et l'état qui reste sur le serveur. Construit par Geneacta.",
           "Les sources sur GitHub", "Le langage Keal", "Signalements"),
}

SWITCH = {"en": ("Français",), "fr": ("English",)}


def page(lang, filename, title, description, body, active=None, toc=None):
    """One complete HTML page, in the site's dress."""
    prefix = "" if lang == "en" else "../"
    links = "".join(
        '<a href="%s"%s>%s</a>' % (href, ' class="tab-active"' if href == active else "", label)
        for href, label in NAV[lang]
    )
    other = ("fr/" + filename) if lang == "en" else ("../" + filename)
    other_label = SWITCH[lang][0]
    foot = FOOTER[lang]
    locale = "en_GB" if lang == "en" else "fr_FR"
    canonical = BASE_URL + ("" if lang == "en" else "fr/") + filename
    alt_en = BASE_URL + filename
    alt_fr = BASE_URL + "fr/" + filename

    tocbox = ""
    layout = body
    if toc:
        entries = "".join('<a href="#%s">%s</a>' % (a, html.escape(t)) for a, t in toc)
        heading = "ON THIS PAGE" if lang == "en" else "SUR CETTE PAGE"
        tocbox = ('<div class="dtoc"><div class="h">%s</div>'
                  '<div class="dtoc-items">%s</div></div>' % (heading, entries))
        layout = '<div class="dgrid"><div></div><div class="dmain prose">%s</div>%s</div>' % (body, tocbox)

    return """<!doctype html>
<html lang="%(lang)s">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%(title)s</title>
<meta name="description" content="%(desc)s">
<link rel="canonical" href="%(canonical)s">
<link rel="alternate" hreflang="en" href="%(alt_en)s">
<link rel="alternate" hreflang="fr" href="%(alt_fr)s">
<link rel="alternate" hreflang="x-default" href="%(alt_en)s">
<meta property="og:type" content="website">
<meta property="og:site_name" content="kealeb">
<meta property="og:locale" content="%(locale)s">
<meta property="og:title" content="%(title)s">
<meta property="og:description" content="%(desc)s">
<meta property="og:url" content="%(canonical)s">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="%(title)s">
<meta name="twitter:description" content="%(desc)s">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Sora:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="%(prefix)sstyle.css">
</head>
<body>
<div class="wrap">
<nav class="nav">
  <div class="nav-left">
    <a class="wordmark" href="%(home)s">kealeb</a>
    <div class="nav-links">%(links)s</div>
  </div>
  <div class="nav-right">
    <span class="badge">v%(version)s</span>
    <a class="btn-keal" href="%(keal)s">Keal ↗</a>
    <a class="btn-lang" href="%(other)s">%(other_label)s</a>
    <a class="btn-gh" href="https://github.com/geneacta/kealeb">GitHub</a>
  </div>
</nav>
%(body)s
<footer class="foot">
  <div class="foot-l">%(foot0)s</div>
  <div class="foot-r">
    <a href="https://github.com/geneacta/kealeb">%(foot1)s</a>
    <a href="%(keal)s">%(foot2)s</a>
    <a href="https://github.com/geneacta/kealeb/issues">%(foot3)s</a>
  </div>
</footer>
</div>
</body>
</html>
""" % {
        "lang": lang, "title": html.escape(title), "desc": html.escape(description),
        "canonical": canonical, "alt_en": alt_en, "alt_fr": alt_fr, "locale": locale,
        "prefix": prefix, "home": "index.html", "links": links,
        "other": other, "other_label": other_label, "keal": KEAL_SITE[lang],
        "version": version(),
        "body": layout,
        "foot0": foot[0], "foot1": foot[1], "foot2": foot[2], "foot3": foot[3],
    }


def write(lang, filename, text):
    out = SITE if lang == "en" else os.path.join(SITE, "fr")
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, filename)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return path


def read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


def version():
    """The number in `keal.toml`, which is what `keal add` pins — the same
    source `ci/band.py` reads for the README's badge, so the site and the
    README cannot say different things."""
    for line in read("keal.toml").splitlines():
        m = re.match(r'\s*version\s*=\s*"([^"]+)"', line)
        if m:
            return m.group(1)
    raise SystemExit("site/build.py: keal.toml has no version")


def counts():
    """The line counts the landing page quotes, read rather than remembered."""
    keal = 0
    for name in sorted(os.listdir(os.path.join(ROOT, "src"))):
        if name.endswith(".keal"):
            keal += len(read("src/" + name).splitlines())
    keal += len(read("kealeb.keal").splitlines())
    c = sum(len(read("runtime/" + n).splitlines())
            for n in sorted(os.listdir(os.path.join(ROOT, "runtime"))) if n.endswith(".h"))
    live = read("src/live.keal")
    a = live.index('clientScript: String = """')
    a = live.index("\n", a) + 1
    js = len(live[a:live.index('\n"""', a)].splitlines())
    return keal, c, js


# ---- the landing page ----------------------------------------------------

HELLO = """import "kealeb/kealeb.keal"

val site = app("Hello")

site.page("/", { req -> column([
    h1("Hello"),
    p("from Keal")
])})

site.run(8080)"""

LIVE = """site.livePage("/", { req ->
    var count = 0
    view({ -> column([
        h1("Clicked ${count} times"),
        button("Click me", { e -> count = count + 1 })
    ]) })
})"""

PATCH = '{"p":[["t","0.0.0","Clicked 1 times"]]}'


def code(text, cls="mono"):
    return '<pre class="%s">%s</pre>' % (cls, html.escape(text))


HERO = {
    "en": {
        "title": "Web pages that stay on the server",
        "sub": ("Routes and handlers like Spring Boot, pages built out of components like "
                "Vaadin — and the whole of both is <code>.keal</code> files. The C underneath "
                "opens sockets and moves bytes. It does not decide anything."),
        "a": "Read the guide", "b": "On GitHub",
    },
    "fr": {
        "title": "Des pages web qui restent sur le serveur",
        "sub": ("Des routes et des gestionnaires comme Spring Boot, des pages faites de "
                "composants comme Vaadin — et tout cela est du <code>.keal</code>. Le C en "
                "dessous ouvre des sockets et déplace des octets. Il ne décide rien."),
        "a": "Lire le guide", "b": "Sur GitHub",
    },
}

CARDS = {
    "en": [
        ("One thread, no locks",
         "Every socket is non-blocking, one <code>poll</code> drives everything, and a handler runs "
         "with nothing else running. Session state is an ordinary Keal object and a data race is not "
         "a thing that can be written here. The cost is stated rather than hidden: a handler that "
         "blocks blocks the server."),
        ("Only the difference travels",
         "A live page keeps its tree on the server. An event runs a handler, the tree is built again, "
         "the two are compared, and what crosses the socket is the list of changes — seven kinds of "
         "patch, each one call in a browser."),
        ("Nothing is linked unless you ask",
         "No dependencies. SQLite arrives with a second import and one flag; a program that never "
         "opens a database never links against one. The hashing, the compression and the WebSocket "
         "framing are Keal."),
        ("Checked by things that did not write it",
         "SHA-256, HMAC and PBKDF2 against the vectors their specifications published. The gzip "
         "output handed to the system <code>gzip</code> and to Python, both required to give the "
         "bytes back. The browser client run against a real server on every build."),
    ],
    "fr": [
        ("Un fil, aucun verrou",
         "Chaque socket est non bloquante, un seul <code>poll</code> mène tout, et un gestionnaire "
         "s'exécute sans que rien d'autre ne tourne. L'état de session est un objet Keal ordinaire "
         "et une course n'est pas une chose qu'on puisse écrire ici. Le prix est énoncé et non "
         "caché : un gestionnaire qui bloque bloque le serveur."),
        ("Seule la différence traverse",
         "Une page vivante garde son arbre sur le serveur. Un événement exécute un gestionnaire, "
         "l'arbre est reconstruit, les deux sont comparés, et ce qui traverse la socket est la "
         "liste des changements — sept sortes de patch, chacune un appel dans le navigateur."),
        ("Rien n'est lié tant qu'on ne le demande pas",
         "Aucune dépendance. SQLite arrive avec un second import et un drapeau ; un programme qui "
         "n'ouvre pas de base ne s'y lie jamais. Le hachage, la compression et le tramage WebSocket "
         "sont du Keal."),
        ("Vérifié par ce qui ne l'a pas écrit",
         "SHA-256, HMAC et PBKDF2 contre les vecteurs publiés par leurs spécifications. La sortie "
         "gzip donnée au <code>gzip</code> du système et à Python, les deux devant rendre les "
         "octets. Le client du navigateur exécuté contre un vrai serveur à chaque construction."),
    ],
}

WORDS = {
    "en": ("the whole framework: HTTP, routing, the component tree, the renderer, stylesheets, "
           "JSON, WebSocket framing, gzip, the scheduler, the session hub, the diff, the SQLite "
           "layer and the hashing security rests on",
           "sockets, poll, byte blobs, files in pieces — two headers, no .c file",
           "the browser client: open a socket, report an event, apply a patch",
           "lines", "what it is",
           "A live page, and the whole of what a click costs",
           "One patch. The browser sets one text node. There is no JSON schema to write, no "
           "endpoint, no client state, and nothing to keep in sync — <code>count</code> is an "
           "ordinary Keal variable and the page is a function of it."),
    "fr": ("tout le cadriciel : HTTP, routage, arbre de composants, rendu, feuilles de style, "
           "JSON, tramage WebSocket, gzip, ordonnanceur, sessions, diff, couche SQLite, et le "
           "hachage sur lequel repose la sécurité",
           "sockets, poll, blobs d'octets, fichiers par morceaux — deux en-têtes, pas de .c",
           "le client du navigateur : ouvrir une socket, signaler un événement, appliquer un patch",
           "lignes", "ce que c'est",
           "Une page vivante, et tout ce que coûte un clic",
           "Un patch. Le navigateur pose un nœud texte. Il n'y a pas de schéma JSON à écrire, pas "
           "de point d'entrée, pas d'état client, et rien à tenir synchronisé — <code>count</code> "
           "est une variable Keal ordinaire et la page est une fonction d'elle."),
}


def landing(lang):
    keal, c, js = counts()
    w = WORDS[lang]
    hero = HERO[lang]
    table = (
        '<table class="counts"><thead><tr><th></th><th>%s</th><th>%s</th></tr></thead><tbody>'
        '<tr><td class="lang">Keal</td><td class="n">%s</td><td>%s</td></tr>'
        '<tr><td class="lang">C</td><td class="n">%d</td><td>%s</td></tr>'
        '<tr><td class="lang">JavaScript</td><td class="n">%d</td><td>%s</td></tr>'
        '</tbody></table>' % (w[3], w[4], format(keal, ",").replace(",", "&thinsp;"),
                              w[0], c, w[1], js, w[2])
    )
    cards = "".join('<div class="card"><h3>%s</h3><p>%s</p></div>' % (t, p) for t, p in CARDS[lang])
    body = """
<section class="hero">
  <div>
    <h1>%(title)s</h1>
    <p class="sub">%(sub)s</p>
    <div class="hero-cta"><a class="cta" href="guide.html">%(a)s</a>
      <a class="cta2" href="https://github.com/geneacta/kealeb">%(b)s</a></div>
  </div>
  <div class="hero-code">%(hello)s</div>
</section>
<section class="counts-wrap">%(table)s</section>
<section class="live">
  <h2>%(livehead)s</h2>
  <div class="live-grid">%(live)s<div class="patch">%(patch)s<p>%(note)s</p></div></div>
</section>
<section class="cards4">%(cards)s</section>
""" % {
        "title": hero["title"], "sub": hero["sub"], "a": hero["a"], "b": hero["b"],
        "hello": code(HELLO), "table": table, "livehead": w[5],
        "live": code(LIVE), "patch": code(PATCH), "note": w[6], "cards": cards,
    }
    title = ("kealeb — web pages that stay on the server" if lang == "en"
             else "kealeb — des pages web qui restent sur le serveur")
    desc = ("A web framework for Keal: Spring Boot's routes, Vaadin's pages, and the whole of both "
            "in .keal files." if lang == "en" else
            "Un cadriciel web pour Keal : les routes de Spring Boot, les pages de Vaadin, et tout "
            "cela en .keal.")
    return page(lang, "index.html", title, desc, body, active="index.html")


# ---- the guide -----------------------------------------------------------

def guide(lang):
    text = read("docs/guide.md" if lang == "en" else "docs/guide.fr.md")
    lines = [l for l in text.splitlines()
             if not l.startswith("*Le même parcours") and not l.startswith("*The same walkthrough")]
    body, toc = markdown("\n".join(lines[1:]))
    title = "The kealeb guide" if lang == "en" else "Le guide de kealeb"
    desc = ("Routes, pages, live pages, the widgets, a database, security, and what the framework "
            "will not do." if lang == "en" else
            "Les routes, les pages, les pages vivantes, les composants, une base de données, la "
            "sécurité, et ce que le cadriciel ne fera pas.")
    return page(lang, "guide.html", title, desc,
                '<div class="doc-head"><h1>%s</h1></div>%s' % (title, body),
                active="guide.html", toc=toc)


# ---- the examples --------------------------------------------------------

EXAMPLES = ["hello", "counter", "todo", "notes", "signin", "files"]

EX_TITLE = {
    "en": ("Examples", "Every one of these is a whole program in this repository, built and run by "
           "the test suite. The prose above each is the comment at the top of the file."),
    "fr": ("Exemples", "Chacun est un programme entier de ce dépôt, construit et exécuté par la "
           "suite de tests. Le texte au-dessus de chacun est le commentaire en tête du fichier."),
}


def examples(lang):
    out = []
    for name in EXAMPLES:
        text = read("examples/%s.keal" % name)
        doc, rest = [], []
        for line in text.splitlines():
            if line.startswith("///") and not rest:
                doc.append(line[4:] if len(line) > 3 else "")
                continue
            if line.startswith("import ") and not rest:
                continue
            if not line.strip() and not rest:
                continue
            rest.append(line)
        prose, _ = markdown("\n".join(doc))
        out.append('<section class="ex" id="%s"><h2>%s.keal</h2>%s%s</section>'
                   % (slug(name), name, prose, code("\n".join(rest).strip("\n"))))
    head, sub = EX_TITLE[lang]
    body = ('<div class="doc-head"><h1>%s</h1><p class="sub">%s</p></div>'
            '<div class="dgrid"><div></div><div class="dmain prose">%s</div><div></div></div>'
            % (head, sub, "".join(out)))
    return page(lang, "examples.html", "kealeb — " + head, sub, body, active="examples.html")


# ---- everything ----------------------------------------------------------

def main():
    written = []
    for lang in ("en", "fr"):
        written.append(write(lang, "index.html", landing(lang)))
        written.append(write(lang, "guide.html", guide(lang)))
        written.append(write(lang, "examples.html", examples(lang)))
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for where in ("", "fr/"):
        for name in ("index.html", "guide.html", "examples.html"):
            lines.append("  <url><loc>%s%s%s</loc></url>" % (BASE_URL, where, name))
    lines.append("</urlset>")
    written.append(write("en", "sitemap.xml", "\n".join(lines) + "\n"))
    written.append(write("en", "robots.txt",
                         "User-agent: *\nAllow: /\nSitemap: %ssitemap.xml\n" % BASE_URL))
    broken = check_links(written)
    if "--external" in sys.argv:
        broken += check_outward(written)
    for path in written:
        print(os.path.relpath(path, ROOT))
    if broken:
        print()
        for where, href, why in broken:
            print("%s -> %s (%s)" % (where, href, why))
        sys.exit(1)


def check_outward(written):
    """Follow the links that leave this site. Opt-in, and deliberately so.

    A build must not need the network: one that does fails on a train, and a
    suite that cannot run offline is a suite people stop running. But a link
    that leaves does rot — the site it points at moves, or the anchor on it is
    renamed — and nothing here would ever notice, because the ordinary check
    skips anything absolute on purpose.

    So: `python3 site/build.py --external`, by hand or on a schedule, and never
    as part of `tools/test.sh`.
    """
    import urllib.error
    import urllib.request

    seen = {}
    broken = []
    for path in written:
        if not path.endswith(".html"):
            continue
        text = open(path, encoding="utf-8").read()
        # Tag by tag rather than href by href, because `rel="preconnect"` names
        # an **origin** to warm up and not a document: fetching one answers 404
        # by design. The first run of this reported twelve broken links and all
        # twelve were those — the checker was wrong, not the site.
        outward = set()
        for tag in re.findall(r'<[^>]+>', text):
            if 'rel="preconnect"' in tag or 'rel="dns-prefetch"' in tag:
                continue
            outward.update(re.findall(r'(?:href|src)="(https?://[^"]+)"', tag))
        for href in sorted(outward):
            url = href.split("#", 1)[0]
            if url not in seen:
                request = urllib.request.Request(url, method="HEAD",
                                                 headers={"User-Agent": "kealeb-site-check"})
                try:
                    seen[url] = urllib.request.urlopen(request, timeout=15).getcode()
                except urllib.error.HTTPError as e:
                    # A HEAD is refused by some servers that answer a GET.
                    seen[url] = e.code if e.code != 405 else _get(url)
                except Exception as e:                       # network, DNS, TLS
                    seen[url] = str(e)
            if seen[url] != 200:
                broken.append((os.path.relpath(path, ROOT), href, "answered %s" % seen[url]))
    return broken


def _get(url):
    import urllib.request
    request = urllib.request.Request(url, headers={"User-Agent": "kealeb-site-check"})
    try:
        return urllib.request.urlopen(request, timeout=15).getcode()
    except Exception as e:
        return str(e)


def check_links(written):
    """Every relative link must point at a file that is there.

    A site is a set of pages that promise each other exist, and nothing
    checks that promise unless something does. This runs on every build and
    fails it, because a build that produces a broken link and says nothing is
    a build that produces a broken link.
    """
    broken = []
    ids = {}
    for path in written:
        if path.endswith(".html"):
            ids[os.path.normpath(path)] = set(
                re.findall(r'id="([^"]+)"', open(path, encoding="utf-8").read()))
    for path in written:
        if not path.endswith(".html"):
            continue
        here = os.path.dirname(path)
        text = open(path, encoding="utf-8").read()
        for href in re.findall(r'(?:href|src)="([^"]+)"', text):
            if href.startswith(("http://", "https://", "mailto:", "data:")):
                continue
            target, _, anchor = href.partition("#")
            where = os.path.normpath(os.path.join(here, target)) if target else os.path.normpath(path)
            if target and not os.path.exists(where):
                broken.append((os.path.relpath(path, ROOT), href, "no such page"))
                continue
            # An anchor that is not there is a link that resolves and lands in
            # the wrong place — the same failure as a wrong page, and the one a
            # checker that only looks at filenames cannot see.
            if anchor and where in ids and anchor not in ids[where]:
                broken.append((os.path.relpath(path, ROOT), href, "no such anchor on that page"))
    broken += check_language(written)
    return broken


# The sites that have a French half. A link from a French page to one of these
# should land in it.
BILINGUAL = ("https://geneacta.github.io/keal/", "https://geneacta.github.io/kealeb/")


def check_language(written):
    """A French page must not send a French reader to an English one.

    This is a seam nobody sees while writing it and everybody feels while
    reading: the nav link, the footer link and the sentence in the guide were
    all pointing at English homes from the French pages. Keal had the same
    thing facing the other way — both of its cards sent our French readers to
    our English half — and neither of us noticed until one of us looked.

    Only reader-facing links count. `rel="alternate"` and `rel="canonical"`
    name the other language on purpose, and flagging them would be flagging the
    thing that makes the site bilingual.
    """
    wrong = []
    for path in written:
        if not path.endswith(".html") or os.sep + "fr" + os.sep not in path:
            continue
        for tag in re.findall(r"<[^>]+>", open(path, encoding="utf-8").read()):
            if 'rel="alternate"' in tag or 'rel="canonical"' in tag or "og:url" in tag:
                continue
            for href in re.findall(r'href="(https://[^"]+)"', tag):
                for site in BILINGUAL:
                    if href.startswith(site) and not href.startswith(site + "fr/"):
                        wrong.append((os.path.relpath(path, ROOT), href,
                                      "a French page linking to an English one; "
                                      "that site has %sfr/" % site))
    return wrong


if __name__ == "__main__":
    main()
