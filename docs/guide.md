# The kealeb guide

Everything the framework does, in the order you will meet it. Half an hour end
to end. Every snippet here is code that compiles; the examples in
[`examples/`](../examples) are the longer versions.

*Le même parcours en français : [`guide.fr.md`](guide.fr.md).*

---

## 1. A program

```keal
import "kealeb/kealeb.keal"

val site = app("My site")

site.page("/", { req -> column([
    h1("Hello"),
    p("from Keal")
])})

site.run(8080)
```

```sh
tools/build.sh hello.keal
build/hello
```

`app(title)` makes an application. `run(port)` serves until the process stops.
Between those two lines you register what the site answers.

The import is the umbrella: everything in this guide is visible after it. A
program that wants less can import one module — `import "kealeb/src/http.keal"`
brings the request and the response and nothing else.

## 2. Using kealeb from your own project

The guide so far assumes you are inside this repository. You do not have to be.
kealeb is a Keal package, and a project that wants it says so:

```toml
# keal.toml
[package]
name = "myproject"
version = "0.1.0"

[dependencies]
kealeb = { git = "https://github.com/geneacta/kealeb", tag = "v0.1.0" }
```

```sh
keal fetch                                  # puts it in .keal/deps/kealeb
.keal/deps/kealeb/tools/build.sh app.keal   # output lands in *your* build/
```

```keal
import "dep:kealeb/kealeb.keal"
```

The build script is the one part that is not just `keal build`, and only
because of one flag: kealeb's C surface is a header, and the compiler has to be
told where it is. Running it from the dependency does that, and puts the
executable in your directory rather than in kealeb's. If you would rather see
the whole command:

```sh
keal build app.keal -I.keal/deps/kealeb/runtime
```

That is all of it. Add `-lsqlite3` when the program imports `src/sql.keal`, and
nothing otherwise: kealeb links against no library at all unless you ask for
the database.

### One thing about `main`

Keal calls a `main` by itself once the top level has run. So an entry point
named `main` must **not** also be called:

```keal
proc main() {
    site.run(8080)
}
                        // no `main()` here — Keal does that
```

Writing both runs the whole program twice. It is invisible while the server
blocks in its loop for ever, and it appears the moment the loop can end — which
is what graceful shutdown made possible, and how this was found here.

## 3. Routes

Five verbs and a catch-all, each taking a path and a handler:

```keal
site.get("/health", { req -> text("ok") })
site.post("/orders", { req -> jsonBody("{\"id\":7}").status(201) })
site.put("/orders/{id}", { req -> text("replaced ${req.param("id")}") })
site.patch("/orders/{id}", { req -> text("changed") })
site.delete("/orders/{id}", { req -> noContent() })
site.any("/ping", { req -> text("pong") })
```

A handler is `(Request) -> Response`. That is a plain function type, so a
handler can be a named function, a lambda, or a value passed around:

```keal
func health(req: Request): Response { return text("ok") }

site.get("/health", health)
site.get("/healthz", health)
```

A named function used as a value needs Keal at `4b21fc5` or later. Before
that, the native backend emitted the bare function pointer where a closure was
expected and the program died — found here, fixed upstream the same day.

### What a pattern can say

| pattern | matches | `req.param(...)` |
|---|---|---|
| `/user/new` | exactly that | — |
| `/user/{id}` | `/user/42` | `id` is `42` |
| `/files/{rest...}` | `/files/a/b.css` | `rest` is `a/b.css` |

A trailing `{name...}` catches everything left, slashes included, and may only
be last. Segments arrive percent-decoded: `/user/le%20monde` gives
`req.param("id") == "le monde"`.

**When two patterns match, the one with more literal segments wins.**
`/user/new` beats `/user/{id}` whichever was declared first. That is the only
precedence rule, and it does not depend on the order you wrote them in.

A path that matches nothing is a 404. A path that matches under a different
verb is a **405** carrying `Allow:` — the difference matters to every client
and a framework that cannot tell them apart makes them all guess.

## 4. The request

```keal
site.post("/search", { req ->
    val q = req.queryOr("q", "")                 // ?q=…
    val page = req.queryOr("page", "1").toInt() ?: 1
    val who = req.headerOr("user-agent", "?")    // case does not matter
    val sid = req.cookie("session")              // String?
    val form = req.form()                        // a posted form, decoded
    val body = req.text()                        // the body as text
    text("${q} ${page} ${who}")
})
```

| | |
|---|---|
| `method` `path` `target` `version` `peer` | as they arrived; `path` is decoded, `target` is not |
| `param(name)` | what the route captured — `""` if the route has no such hole |
| `query` · `queryOr(name, fallback)` | the query string, parsed |
| `header(name): String?` · `headerOr` · `hasHeader` | names fold case; a header sent twice is joined with `, ` |
| `cookies(): Map` · `cookie(name): String?` | |
| `text()` · `form()` · `formAll()` · `body` | the body as text, as a form, keeping repeats, as bytes |
| `contentType()` | the media type, without its parameters |
| `keepAlive()` · `isUpgrade()` | what the connection is for |

A `Request` cannot be changed. Keal says the contents of a parameter belong to
the caller unless the signature says `var`, and a function type cannot say
`var` — so a handler is given the answer rather than the chance to change the
question. Where the framework needs to add something, it builds a new one:
that is what `withParams` does, and it shares the body rather than copying it.

## 5. The response

```keal
html("<p>hi</p>")                        // text/html; charset=utf-8
text("plain")                            // text/plain; charset=utf-8
jsonBody("{\"ok\":true}")                // application/json
bytes("image/png", someBuf)              // anything, from a byte buffer
noContent()                              // 204
redirect("/next")                        // 302; redirect("/x", 301) for a move
notFound("no such order")                // 404
badRequest("id must be a number")        // 400
serverError()                            // 500
```

Each answers a `Response`, and each adjustment answers the response again, so
a line reads as one thing:

```keal
html(page).status(201).type("text/html").with("x-made-by", "kealeb").cookie("sid", token, 3600)
```

Keep a chain on **one line**. Keal ends a statement at a newline when the
previous token could end one, so a `.` at the start of the next line is a new
statement, not a continuation.

`cookie(name, value, maxAge, path, httpOnly, sameSite)` defaults to
`HttpOnly`, `SameSite=Lax`, path `/`, and no `Max-Age` at all — which means
*this browser session*. `maxAge = 0` deletes.

`Content-Length` is always written from the body's byte count and cannot be
overridden. A length that disagrees with its body breaks the *next* request
rather than this one, which is a bug worth refusing the chance to write.

## 6. Pages

A page is a function from a request to a tree of components. The framework
wraps it in a document and sends it.

```keal
site.page("/about", { req -> column([
    h1("About"),
    p("Two paragraphs and a link."),
    link("/", "home")
])}, "About us")
```

The last argument is the `<title>`; without it the application's own title is
used.

### The tree

Every builder answers a `Node`, and every adjustment answers it again.

```keal
el("section").cls("hero").id("top").attr("role", "banner").add(h1("Title"))
```

| | |
|---|---|
| `el(tag)` · `elt(tag, kids)` | any element |
| `txt(s)` | text — **always escaped** |
| `raw(s)` | markup that is already markup, and must be exactly one element |
| `nothing()` | a node that takes up a place and shows nothing |
| `div` `span` `p` `h1` `h2` `h3` `strong` `em` `code` `pre` `br` `hr` | |
| `link(href, s)` · `img(src, alt)` | |
| `ul` `ol` `li` · `table` `thead` `tbody` `tr` `th` `td` `tdt` | |
| `section` `header` `footer` `nav` `main` | |
| `form` `label` `option` | |
| `.cls(names)` `.id(v)` `.style(v)` `.title(v)` `.attr(n, v)` `.flag(n, yes)` | |
| `.add(child)` `.addAll(children)` `.on(event, handler)` `.keyed(k)` | |

`.flag(name, yes)` is for the boolean attributes: it writes `disabled` when
`yes` and leaves it out otherwise, because `disabled="false"` is still
disabled.

### The widgets

`row`, `column` and `card` are layout; the rest take handlers and only mean
something on a live page.

```keal
row([button("Save", { e -> save() }), button("Cancel", { e -> back() })])
column([field(name, { e -> name = e.value }), checkbox(on, { e -> on = e.checked() })])
select(chosen, [("a", "Alpha"), ("b", "Beta")], { e -> chosen = e.value })
textarea(body, { e -> body = e.value })
shownWhen(count > 0, p("${count} waiting"))
```

`submit(text)` is the other kind: a button that submits its form the ordinary
way, for a page that works with no JavaScript at all.

### Styles written in Keal

`.style("color: red")` takes a string and always will — for one declaration on
one node that is the shortest honest thing. For a stylesheet, `css.keal`
builds one out of values:

```keal
val href = site.css(sheet([
    vars(":root", [("--accent", "#2f6feb")]),
    rule(".hero").bg("var(--accent)").fg("white").pad("3rem 2rem").radius("12px"),
    rule(".hero h1").size("2.4rem").weight("700"),
    media("(max-width: 600px)", [rule(".hero").pad("1.5rem")])
]))
```

| | |
|---|---|
| `rule(selector)` | a rule; every setter answers it, so chain or don't |
| `.set(property, value)` | the one that always works |
| `.fg` `.bg` `.pad` `.margin` `.border` `.radius` `.font` `.size` `.weight` `.width` `.height` `.gap` `.display` `.flex` `.grid` `.shadow` `.opacity` `.cursor` `.position` `.overflow` `.transition` | the ones worth a name |
| `media(query, rules)` · `supports(query, rules)` | at-rules; the query is the selector |
| `vars(selector, pairs)` | custom properties, as one rule |
| `sheet(rules)` | all of it, as text |

It is not a CSS parser and does not validate: what you write goes out. What it
buys is that **a rule is a value** — held in a list, returned from a function,
built from a loop — and that the selectors and the numbers come from the same
place as the rest of the program.

`site.css(text)` serves it and links it from every page. The URL names the
content — `/kealeb/asset-2b7c19f4e1.css` — so it is sent with a one-year
`immutable` cache and still changes the instant the stylesheet does. It answers
that URL, for a page that wants to reference it itself.

### JavaScript, and when you need it

```keal
site.script("/* a map widget, a chart, an analytics tag */")
site.linkStyle("https://fonts.example/thing.css")
site.inHead("<link rel=\"icon\" href=\"/favicon.svg\">")
```

`script` is served and cached the same way, with `defer`. The framework's whole
point is that you do not need it — the events and the rendering are Keal, on
the server. It is here for the things that are genuinely the browser's. If you
find yourself writing application logic in there, the framework has failed at
something and it is worth saying which.

**Order does not matter.** The title, the stylesheet and the assets are fixed
when the server is built, which is after every registration, so a page
registered before `site.css(...)` still gets the stylesheet. That was a real
bug and this is the sentence that says it is not one any more.

### Escaping

`txt` escapes. There is no flag to turn that off — `raw` is a different
function with a different name, and that is the whole safety story. Attribute
values are escaped for quotes as well.

### The stylesheet

Every page links `/kealeb/kealeb.css`: about a hundred lines, every rule
prefixed `kb-`, following the operating system's dark mode. To bring your own:

```keal
site.style = "/static/app.css"     // yours instead
site.style = ""                    // none at all
site.head = "<link rel=\"icon\" href=\"/favicon.svg\">"
```

## 7. Forms without JavaScript

```keal
site.page("/greet", { req -> column([
    h1("Greet"),
    el("form").attr("method", "post").add(row([
        el("input").cls("kb-input").attr("name", "name"),
        submit("Say hello")
    ]))
])})

site.post("/greet", { req ->
    val name = req.form().get("name") ?: ""
    html(doc("Greet", h1("Hello, ${name}")))
})
```

Nothing here needs a socket, a session or a script. It is the whole of
[`examples/hello.keal`](../examples/hello.keal)'s third route.

### Files

A form that carries a file posts `multipart/form-data`, which is bytes and not
text — a PNG through a UTF-8 validator is a corrupted PNG. So it is parsed on
the bytes, and a `Part` hands you either.

```keal
site.post("/upload", { req ->
    val doc = req.file("doc")
    if (doc == null) {
        badRequest("choose a file")
    } else {
        doc.saveTo("uploads/${epochS()}-${doc.safeName()}")
        redirect("/", 303)
    }
})
```

| | |
|---|---|
| `req.isMultipart()` | is this that kind of body? |
| `req.parts()` | every part, in order |
| `req.part(name)` | one part, or null |
| `req.file(name)` | one part, but **only** when a file was actually chosen |
| `p.name` `p.filename` `p.kind` | the field name, the client's file name, the claimed media type |
| `p.text()` `p.bytes()` `p.size()` `p.isFile()` | |
| `p.saveTo(path)` · `p.safeName(fallback)` | |

Three things worth knowing before writing the handler:

* **`file` and `part` are different questions.** A browser sends a part for a
  file input even when nobody chose a file — empty name, no content. `part`
  gives you that; `file` gives you `null`, which is the check every upload
  handler would otherwise forget.
* **`kind` is a claim.** The client says what it likes. A server that trusts it
  is a server that serves a script as an image.
* **`filename` is never a path.** It is what a stranger typed, `../../etc/`
  included. `saveTo` takes a path *you* chose, and there is deliberately no
  `save(intoDirectory)` — that function would have to decide what to do with
  the client's name, and every wrong answer is a directory somebody escaped.
  `safeName()` strips it down to letters, digits and `. - _`, and it is still
  a name a stranger chose: use it to show somebody what they uploaded, and
  generate the name you store.

The whole body is in memory, bounded by the server's `maxBody` (8 MB by
default). There is no streaming to disk, no `multipart/mixed`, and no
`Content-Transfer-Encoding` but the identity one — a browser posting a form
sends none of those.

## 8. Live pages

```keal
site.livePage("/", { req ->
    var count = 0
    view({ -> column([
        h1("Clicked ${count} times"),
        button("Click me", { e -> count = count + 1 })
    ]) })
})
```

Two functions, and the difference between them is the whole model:

* **The outer one runs once per visitor.** Whatever it closes over is that
  visitor's own state. There is no session map to key correctly — the closure
  *is* the session.
* **The inner one runs after every event.** It must be a function of the state
  and nothing else: anything it reads that can change without an event will
  not be noticed until the next one.

### What happens

1. The browser asks for the page. The server builds the tree, numbers the
   nodes that listen, sends the HTML, and keeps the tree.
2. A small script opens a WebSocket back to `/kealeb/live`.
3. You click. The script sends `{"i":"0.2.1","e":"click","v":"","f":{}}` —
   which node, which event, what it held.
4. The server runs the handler, builds the tree again, compares it with the
   one it kept, and sends the difference.
5. The script applies it. Six operations exist and no seventh: set a text
   node's text, set an attribute, remove an attribute, replace a node, insert
   a child, remove a child.

A handler is `(Ev) -> Unit`:

| | |
|---|---|
| `e.name` | `click`, `input`, `change`, `submit`, `keydown` |
| `e.value` | what the element held — the field's text, `"true"`/`"false"` for a checkbox, the chosen option |
| `e.number(fallback)` · `e.checked()` | the value, read |
| `e.field(name)` | a form's field on `submit`, the key on `keydown` |

### The one rule

**One `Node`, one node in the browser.** A node's identity is its position —
`0.2.1`, counted from the mount point — so anything that renders to no bytes
would shift everything after it. That is why `nothing()` exists and renders an
empty comment, and why `raw` must contain exactly one element.

### Identity, and when to say what a node is

Without a key, **identity is position**. The node at `0.2.1` is compared with
whatever was at `0.2.1` last time, and if the tags match the browser's node is
kept and its attributes adjusted. That is right when it is the same thing
rendered again — which is the ordinary case, sixty times out of sixty.

It is wrong when two *different* things land in the same place: a list shifted
up by one, a tab that changed, a row that was deleted. The node is kept, and
so is everything the server does not know about it — the caret, the focus, the
scroll position, a keystroke that has not been reported yet. They now belong
to something else.

`.keyed(id)` is how a page says *this is a different thing*:

```keal
for (task in tasks) {
    rows.add(row([...]).keyed("task-${task.id}"))
}
```

A node whose key changed is rebuilt rather than patched, so that state is
thrown away with it. Keys are compared on the server and never reach the
browser.

What keys do **not** do yet is make a move cheap: inserting at the front of a
list still rewrites everything after it, because the diff walks children by
index and does not look for one that moved. Correct, and more work than it
needs to be. That is the next thing to fix.

### Sessions

A session lives as long as its socket, plus `ttlMs` (a minute by default) for
a tab that went to sleep. A page whose session the server has forgotten
reloads itself and gets a new one.

```keal
site.live.ttlMs = 300000        // five minutes
site.live.size()                // how many pages are open
site.live.refreshAll()          // rebuild every open page
```

`refreshAll` is what to call when the world changed under all of them at once
— a row was inserted by something else, a job finished.

### What it costs

The server holds a session per open page. A page that is open is memory that
is used. That is Vaadin's bargain and it is the one kealeb makes; if a page
must scale to a hundred thousand idle tabs, it should be a `page`, not a
`livePage`.

## 9. Static files

```keal
site.files("/static", "./public")      // /static/a/b.css -> ./public/a/b.css
site.file("/favicon.svg", "./public/favicon.svg")
```

Each answer carries an `ETag` built from the file's timestamp and size, and a
client that sends it back gets a 304 with no body.

Any path with a `..` segment, a leading `/`, a backslash, or a dotfile
component is a **403** — refused, not normalised. Normalising a hostile path
is how a directory gets escaped.

### Bodies bigger than memory

A request body over a megabyte is written to a file as it arrives rather than
held:

```keal
s.spoolFrom = 4 * 1024 * 1024      // where the line is
s.spoolDir = "/var/tmp"            // where the files go
s.maxBody = 512 * 1024 * 1024      // now costs disk, not memory
```

A handler is told which it got:

```keal
site.post("/upload", { req ->
    if (req.spooled()) {
        req.saveBodyTo("uploads/${epochS()}.bin")
        redirect("/", 303)
    } else {
        store(req.body)
        redirect("/", 303)
    }
})
```

`text()`, `form()` and `parts()` read the body in memory, so a spooled body has
nothing for them: it is at `bodyPath`, and it is the handler's to move, copy or
read in pieces. **The file is deleted when the request is done**, so a handler
that wants to keep it must say so before it returns — `saveBodyTo` is that.

Measured, posting sixty megabytes: **2.5 MB resident**. It was 133 MB when the
draining happened after the read loop rather than inside it — the kernel hands
over as much as it has, so a body arrives faster than one turn of the loop and
the read buffer grew to hold all of it. That is a bug this framework had for
about ten minutes, and the number is here because "streaming" is a word and 130
MB is not.

What this does not do: a **multipart** body over the threshold is spooled
whole, and `parts()` cannot read it. A form with a large file in it therefore
wants `spoolFrom` above the largest form you accept, or a handler that parses
the file itself. Parsing multipart out of a file is the missing piece, and it
is named here rather than discovered.

### Files bigger than the machine

A file under a megabyte is read into memory; above that the server opens it and
sends it as the socket takes it, a quarter of a megabyte at a time.

```keal
streamFrom = 4 * 1024 * 1024        // where the line is
```

The line is where two things swap places. A small file wants to be in memory:
it can be compressed, which is worth four or five times its size on a
stylesheet, and holding it costs nothing. A large one wants the opposite —
compressing a film is pointless because a film is already compressed, and
holding it is the difference between serving it and refusing to.

Measured, serving the same hundred-megabyte file both ways:

| | resident memory |
|---|---|
| streamed | **3 MB** |
| read whole | **235 MB** |

The socket's appetite is what paces the read, so a slow client is a slow read
and not a queue: the server never holds more of the file than the piece it is
writing. A streamed body is never compressed, and both paths answer `Range`.

### Ranges

A static file is served with `Accept-Ranges: bytes`, and a client that asks for
part of one gets it:

```
Range: bytes=0-499        the first five hundred
Range: bytes=500-         everything from there
Range: bytes=-500         the **last** five hundred
```

The answer is a 206 with `Content-Range`. A range naming bytes the file does
not have is a **416** carrying `Content-Range: bytes */size` — the resource is
there, the slice is not, and that is a different thing from a 404.

Anything this cannot honour — a unit that is not bytes, more than one range,
anything malformed — means *send the whole thing*, which is always a correct
answer to a range request and is what the specification allows a server to do
rather than working harder.

A 206 is never compressed: a range names bytes of the resource as it is, so a
compressed slice would be a slice of something the client did not ask for.

The honest limit: the file is read whole before the slice is cut. That is fine
for the sizes a page is made of and wrong for a film, and it is the same
limitation as everywhere else here — nothing streams yet.

## 10. JSON

```keal
val fields: Map<String, Json> = {}
fields.set("id", jInt(7))
fields.set("name", jStr("Ada"))
fields.set("tags", jStrs(["a", "b"]))
jsonBody(jObj(fields).write())
```

Reading:

```keal
site.post("/orders", { req ->
    val body = parseJson(req.text())
    if (body == null) { badRequest("not JSON") } else {
        text("id ${body.intAt("id")} for ${body.str("name")}")
    }
})
```

`parseJson` answers `Json?`. Trailing text is a refusal, not something to
ignore. `field(name)` answers `Json?`, which is a different thing from a field
whose value is JSON `null` — and the difference is why it is nullable.

## 11. Testing

A handler is a function, so most of a site can be tested with no socket at
all:

```keal
val r = Router()
r.get("/user/{id}", { req -> text("user ${req.param("id")}") })

assert(dispatch(r, request("GET", "/user/42")).text() == "user 42", "the parameter")
assert(dispatch(r, request("GET", "/nope")).code == 404, "and nothing else")
```

`request(method, target)` builds one by hand. `dispatch(router, req)` runs it
through the table.

When you do want the socket, ask for port 0 and the machine picks one:

```keal
val s = site.serverOn(0)
val port = s.open()          // the port it actually got
s.tick(50)                   // one turn of the loop
```

`tools/test.sh` runs [`tests/units.keal`](../tests/units.keal) and, when
`node` is present, [`tests/client.mjs`](../tests/client.mjs) — which runs the
real client script against a real server.

### Testing what a program leaves behind

Keal frees an object when its last reference goes, so a leak here is a
**cycle** and nothing else. `keal build --audit` reports what outlived a
program and says which of it was unreachable:

```sh
keal build --audit tests/lifetime.keal && ./lifetime
```

The trap is that the verdict arrives *after* the last statement, so the
program cannot assert on it — by the time there is an answer there is no
program left to act on it. Something outside has to read the output;
`tools/test.sh` does, and fails with the whole report when the answer is not
`nothing outlived the program`. A version of that test ending in
`assert(true, "no leaks")` looks like a test, runs green for ever, and checks
nothing.

That test asserts a negative, so it has a control:
[`tests/leaks.keal`](../tests/leaks.keal) builds the cycle on purpose and the
runner requires the audit to still report it, and to report exactly one. A
suite that only ever checks for the absence of a thing goes green the day it
stops being able to find it.

The rule is one line and it is not about handlers, or about kealeb: **a
closure stored in an object must not hold that object.** Reference counting
frees what nothing points at, and a ring points at itself.

In this framework the ring goes through the router — it keeps the handler, and
the application keeps it — so the shape to avoid is a handler that reaches
back to the application:

```keal
val site = app("mine")

site.get("/a", { req -> text(site.title) })       // holds the application
val name = site.title
site.get("/b", { req -> text(name) })             // holds a string
```

Inside a method of your own class it is the same thing spelt `this`. Either
way the fix is the same: read what the closure needs into a local *before* the
lambda, and the closure holds the value instead of the object that had it.

In an ordinary program this costs nothing, and it is worth saying so plainly
rather than raising an alarm: `val site = app(...)` at the top level lives
until the process ends, so a ring inside it is never collected because nothing
was ever going to collect it. It matters when an application is built and
dropped — a test, or a program that serves more than one. That is exactly what
`tests/lifetime.keal` does, and why its handlers never mention `site`.

`weak` is not the answer here. It would say the application is only weakly
held by its own routes, which is not what the program means.

## 12. Filters

A filter wraps every request. It is an ordinary function, and there is no
registry, no ordering annotation and no chain configuration — the order is the
order you wrote them in.

```keal
site.use({ req, next ->
    val started = monoMs()
    val res = next.on(req)
    println("${req.method} ${req.path} ${res.code} ${monoMs() - started}ms")
    res
})
```

They run **outermost first** and unwind in the other direction, so the first
one added is the last one to see the answer. A filter that never calls
`next.on(req)` has answered by itself, which is what refusing looks like:

```keal
site.use({ req, next ->
    if (req.path.startsWith("/admin") and (not a.signedIn(req))) {
        redirect("/sign-in", 303)
    } else {
        next.on(req)
    }
})
```

Filters sit **inside** what `secure` installs and **outside** the router: a
filter never sees a request that failed its CSRF check, and everything a filter
answers still gets the response headers.

A filter is held by the application, so the rule that holds everywhere else
holds here — a filter must not capture the application. Read what it needs into
a local first.

When one function is enough, `Server.handle` is still there and replacing it
replaces everything, routing included.

## 13. Running it

```keal
site.run(8080)                        // 127.0.0.1 — cannot surprise anybody
site.run(8080, "")                    // every interface
site.log = false                      // no line per request
```

The server it builds can be adjusted before it starts:

```keal
val s = site.serverOn(8080)
s.maxHead = 16 * 1024                 // bigger heads are 431
s.maxBody = 2 * 1024 * 1024           // bigger bodies are 413
s.idleMs = 15000                      // a quiet connection is closed
s.maxRequests = 500                   // per connection, then close
s.handle = { req -> myOwnDispatch(req) }
s.run()
```

There is no TLS. Put it behind a reverse proxy, which is where a terminator
belongs; `X-Forwarded-For` arrives as an ordinary header and `req.peer` is the
proxy.

Standard output is line-buffered from the moment the server starts, so a log
piped to a file or a supervisor arrives as it is written.

### Compression

Every response a browser can read gzipped, is:

```keal
s.compress = false        // if you would rather it were not
s.compressFrom = 2048     // the size below which it is not worth the header
```

It is on by default and there is not much to it: if the client said
`Accept-Encoding: gzip`, the media type is text or something that is text
underneath, the body is at least `compressFrom` bytes, and compressing actually
made it smaller — then it goes out compressed. Any of those failing, it goes
out as it was.

`Vary: Accept-Encoding` is set **whether or not** it compressed, and that is
the part everybody forgets: a cache that stored the compressed answer without
it would hand it to the next client along, who may not be able to read it.

Measured on this machine: a 9 KB page becomes 717 bytes in about a
millisecond; 180 KB takes four. Something already compressed — a PNG, a font —
is never touched, because its media type is not on the short list of things
worth compressing and DEFLATE would spend those milliseconds making it very
slightly bigger.

The compressor is `src/gzip.keal`, written in Keal. Each block goes out with
whichever code table is smaller — the fixed one the specification writes down,
or one built from what that block actually contains and written into the output
ahead of it. Choosing costs one loop over the frequencies and is worth about a
fifth on HTML; a block whose alphabet is nearly uniform, a fragment of an image
or a base64 blob, comes out smaller with the fixed table, which is why it is
asked rather than assumed.

Measured against the reference implementation on the eight files the suite
compresses, `gzip -6` and this one produce **the same size on six of them,
one byte less on two, and eight bytes more on one** — a 13 KB file, which is
three parts in a thousand. There is no reason to reach for anything else.

There is no decompressor. kealeb compresses and never inflates, which is also
why nothing in Keal can check the output: `tools/test.sh` hands every file it
produces to the system `gzip` **and** to Python, and requires both to give the
bytes back. A test that only checked the output was smaller would go green the
day the compressor started emitting plausible nonsense.

### Stopping

`SIGINT` and `SIGTERM` — Ctrl-C, and what a service manager sends — do not kill
the process any more. They ask it to stop, and it does so in this order:

1. `onStop` runs, if you set one.
2. The listener closes, so a client that connects now is refused by the kernel
   and can go somewhere else.
3. Connections in the middle of an answer are given up to `drainMs` (five
   seconds) to finish. Connections that owe nothing are closed at once —
   waiting for an idle keep-alive would mean waiting the whole timeout every
   time.
4. Anything still open after that is closed anyway, with a line saying so. A
   shutdown that waits for ever is a process somebody has to kill, and being
   killed is what this exists to avoid.

```keal
val s = site.serverOn(8080)
s.onStop = { -> println("goodbye") }
s.drainMs = 15000
s.run()
```

A handler cannot be interrupted, so a request already running always finishes:
the signal sets a flag and the loop notices, which is also the only thing that
is safe to do inside a signal handler.

### When there is nothing there, and when something broke

```keal
site.onNotFound({ req -> column([h1("Nothing at ${req.path}"), link("/", "home")]) })
site.onError({ req -> column([h1("Something went wrong"), p("It has been written down.")]) })
```

Both build a page like any other page — the document, the stylesheet, the
site's own shape — and both replace the answer **only when the client asked for
HTML**. An API's 404 stays the short sentence a program can read, because
error handling that has to parse HTML is error handling nobody writes.

`onError` is not told what was thrown, on purpose. Whatever a handler threw may
hold a query, a path or a password — anything it was holding when it gave up —
so it goes to standard output, where somebody who can read the log can read it,
and a log is not a thing a stranger can read.

The catch that turns a throw into a 500 sits **inside** the filters, around the
router. That is not a detail: a handler that throws unwinds every filter around
it on the way out, so a catch further out would produce a 500 that no filter
ever sees — `onError` could not replace it, and a logging filter would miss the
one request most worth recording.

## 14. Scheduled work

```keal
site.every(60000, { -> sweepExpiredCarts() })      // every minute
site.after(5000, { -> warmTheCache() })            // once, five seconds in
```

A job runs on the loop's own thread, **between requests and never during
one**, so it reads and writes whatever a handler reads and writes with nothing
to synchronise — no lock, no queue, no copy. That is the same bargain the rest
of the framework makes, and it has the same price: a job that blocks blocks
the server.

A job that takes longer than its interval simply runs less often than it
asked. It is never started twice, and there is no queue of missed runs waiting
to stampede when it finishes.

A job that throws is reported on standard output and **keeps its schedule** —
a batch that fails once an hour should still be tried next hour, and a server
that dies because a scheduled job did is worse than the job failing.

From a server you already hold, `every` and `after` answer the `Timer`, which
can be `cancel()`led or told to run `soon()`:

```keal
val s = site.serverOn(8080)
val beat = s.every(30000, { -> ping() })
beat.soon()                                        // run it on the next turn
beat.cancel()                                      // and never again
```

The cost is a comparison per turn of the loop and nothing else: the loop was
already sleeping in `poll` with a deadline, and a timer is that deadline being
chosen rather than assumed. A server with no jobs sleeps exactly as it did
before.

The rule about what a job may capture is the handler's rule: **a job must not
hold the application.** `site.every(1000, { -> println(site.title) })` closes
the ring that `tests/lifetime.keal` exists to keep open.

There is no cron expression and no calendar. `every` counts milliseconds. A
job that must run at 03:00 should check the clock itself — `utcNow()` is in
the prelude — because a scheduler that understands time zones and daylight
saving is a different program from this one, and pretending otherwise is how
a batch runs twice in October.

## 15. A database

SQLite, and it is a **second import and a second link flag** — a program that
never opens a database must not link against one:

```keal
import "kealeb/kealeb.keal"
import "kealeb/src/sql.keal"
```

```sh
tools/build.sh app.keal -lsqlite3
```

```keal
val db = openDb("notes.db")          // ":memory:" for a test
if (db == null) { println("could not open it"); exit(1) }

db.migrate([
    "create table note(id integer primary key, body text not null, done integer not null default 0)",
    "alter table note add column made integer not null default 0"
])

db.run("insert into note(body) values (?)", [vText(what)])
for (r in db.query("select id, body, done from note order by id", [])) {
    println("${r.int("id")} ${r.text("body")} ${r.bool("done")}")
}
```

### The one rule

**Everything a request can reach goes in as a bound value** — `?` in the SQL,
a `Val` in the list. There is no function here that builds SQL out of a string
somebody sent you, because there is no safe version of that to offer.

`script()` is the only function that takes SQL with no parameters. It is for
the schema you wrote, it runs several statements at once, and it is spelt
differently from `run` on purpose. Never hand it anything a request touched.

Two more refusals fall out of that, and both are the shape a half-finished
edit takes:

* `run` and `query` take **one** statement. `"select 1; drop table note"` is
  refused with those words, not run and not silently truncated.
* The number of values must match the number of `?`. A mismatch is refused
  naming both counts, rather than becoming a null in a column three weeks
  later.

### Reading

| | |
|---|---|
| `db.run(sql, params)` | rows changed, or -1 |
| `db.query(sql, params)` | every row, as a list |
| `db.one(sql, params)` | the first `Row?`, or null |
| `db.value(sql, params)` | the first column of the first row, as a `Val` |
| `db.script(sql)` | statements with no parameters — your schema |
| `db.changed()` · `db.lastId()` · `db.error()` | |

A `Row` is read by name — `r.int("id")`, `r.text("body")`, `r.float("score")`,
`r.bool("done")`, `r.isNull("x")` — and a name no column has answers null
rather than failing, because a query and its reader drift apart in the same
commit often enough that a crash there helps nobody.

The values convert the way SQLite itself converts: asking a number for its
text gives you the digits. `isNull` is separate from every fallback, because
*absent* and *zero* are not the same answer.

Building: `vInt` `vFloat` `vText` `vBool` `vNull`. SQLite has no boolean, so
`vBool` is an integer that says which.

### Transactions

```keal
db.transaction({ ->
    db.run("update account set balance = balance - ? where id = ?", [vInt(n), vInt(from)])
    db.run("update account set balance = balance + ? where id = ?", [vInt(n), vInt(to)])
    true                                  // false rolls back
})
```

It commits when the block answers true, rolls back when it answers false, and
rolls back **and re-throws** when it throws — because a transaction left open
by an exception is what locks a database for everybody else.

### Migrations

`migrate(steps)` is every migration the program has ever had, in order and
never reordered. Step 1 is `steps[0]`; a database at version 2 runs from
`steps[2]` onward. SQLite keeps the number in the file, so there is no table
to create and nothing to keep in sync.

Each step runs **in a transaction with its own version bump**, so a step that
fails leaves the database exactly where it was. It answers the version it
reached, or -1 with the reason in `error()`.

### What it is not

There is no object-relational mapper, and there is not going to be one by
accident. A `Row` is a `Row` rather than your record because turning one into
the other is three lines you can read, and a mapper that does it for you is a
second language to learn before the first query.

The honest limits, each of which is a real one:

* **One connection.** The server is one thread; a second connection would
  spend its life waiting on the first. `Db` closes itself when its last
  reference goes, so there is no pool to configure and nothing to remember.
* **`query` reads every row into memory**, in one go. A query that could
  answer a million rows should say `limit`. That is stated rather than hidden
  behind a cursor that looks lazy and is not.
* **No blobs.** A `BLOB` column read through `text()` comes back with anything
  that is not well-formed UTF-8 turned into U+FFFD, which is the same
  treatment bytes off a socket get. Read `kind` first if the column might not
  be text.
* **SQLite only.** Postgres would be `libpq` through the same C door, or its
  wire protocol written in Keal — a project of its own either way.

[`examples/notes.keal`](../examples/notes.keal) is a live page whose state is
a database: stop it, start it again, the notes are there. It also shows the
one thing a live page cannot work out for itself — `site.live.refreshAll()` in
a timer, so a page learns about a change it did not cause.

## 16. Security

Four ideas, and there is no fifth. A **password** you can store, a **session**
that is a signed cookie and nothing on the server, a **guard** that is an
ordinary function wrapping a handler, and a **token** that makes a form only
work when it came from your own page.

There is no role hierarchy, no expression language, no filter chain and no
annotations. A role is a string. A rule is a function.

```keal
import "kealeb/src/auth.keal"

val a = auth(secretFromFile("app.secret"))
site.secure(a)
```

Those two lines switch on four things nobody should have to write:

* every form on every page gets a hidden CSRF token, put there by the
  framework walking the tree;
* every `POST`, `PUT`, `PATCH` and `DELETE` is refused without it;
* every response carries `nosniff`, `Referrer-Policy`, `X-Frame-Options` and a
  content policy of `default-src 'self'` with no room for inline script;
* a WebSocket upgrade whose `Origin` is another site is refused.

There is nothing to configure because there is nothing there anybody should
want to turn off. What is left to decide is what an application really has to:
who may sign in, and what they may then do.

### The secret

Everything is a signature under one key, so a program that hard-codes it in a
public repository has no security at all, and one that generates a new key at
every start signs everybody out on every deploy.

```keal
val a = auth(secretFromFile("app.secret"))
```

Thirty-two random bytes, made on the first run, read on every one after.
**Keep that file out of version control and back it up**: it signs every
session and peppers every password, so losing it signs everybody out *and*
makes every stored hash unverifiable.

### Passwords

```keal
val stored = a.hashPassword(what)                 // pbkdf2-sha256$25000$…$…
if (a.checkPassword(what, stored)) { … }
if (a.needsRehash(stored)) { store(a.hashPassword(what)) }
```

PBKDF2-HMAC-SHA256, written in Keal in `src/hash.keal` and checked against the
published vectors on every build. A fresh sixteen-byte salt per password, and
the round count stored alongside — so raising it later does not invalidate
anything, and `needsRehash` says when to write one again at the new count.

**Why 25 000 rounds and not the 600 000 OWASP asks for**, since the difference
matters and hiding it would be worse than having it: this server is one
thread, so hashing blocks every other request for as long as it takes. 25 000
costs about 95 ms here — measured, not guessed. At OWASP's number a login
would hold the loop for two and a half seconds and ten of them would be a
denial of service anybody could mount.

Three things carry the weight that the round count does not:

* **A pepper.** Every password is hashed with a secret that is not in the
  database. A stolen database is not something you can guess against, whatever
  the round count, unless the secret leaked too.
* **A rate limit.** `a.mayTry(key)` allows ten attempts a minute per key. Call
  it with the account name *and* the peer, so one account cannot be locked out
  from elsewhere and one machine cannot work through a list of names.
* **Saying so.** If your server has time to spare, `a.rounds = 100000` is one
  line, and it costs what `tools/build.sh` will tell you it costs.

### Sessions

```keal
a.signIn(redirect("/", 303), name)      // sets the cookie
a.signOut(redirect("/", 303))           // deletes it
a.userOf(req)                           // String?, or null
a.signedIn(req)                         // Bool
```

The whole session is the cookie: a name and the second it was issued, signed.
`HttpOnly`, `SameSite=Lax`, and `Secure` unless you turn it off for localhost.

There is no table, so nothing expires on the server and nothing grows — and
signing out deletes a cookie, which means a stolen cookie stays good until it
expires. That is the trade a stateless session makes, stated rather than
buried, and `a.ttl` is the dial on it (a week by default; 0 means until the
browser closes).

### Guards

```keal
site.get("/private", requireUser(a, { req -> … }))
site.get("/admin", requireWhen(a, { who -> isAdmin(db, who) }, { req -> … }))
```

`requireUser` sends a stranger to `a.signInPath` with `?next=` naming where
they were going, or answers 401 when `signInPath` is empty — which is what an
API wants and a browser does not. `requireWhen` is given the user's name and
answers whether they may; somebody signed in but not allowed gets **403**, not
404.

Reading `?next=` back is `nextAfter(req)`, and the checking is the point: a
redirect that follows a value a stranger controls is how a phishing link
borrows your domain. Anything that is not a single-slash-rooted path is
refused, `//evil.example` included — that is the one people forget.

### The token

`site.secure(a)` puts a hidden field into every form built by `page` or
`livePage` whose method changes something, and refuses every unsafe request
without it. An API may send it as `X-CSRF-Token` instead.

The token is derived from the session rather than stored, so it needs no state
and cannot get out of step, and a visitor with no session still gets one —
which the sign-in form needs, since it has to work before anybody is signed
in.

One gap to know about: a handler that builds its own document with `doc(...)`
rather than through `page` is not walked, so add `a.csrfInput(req)` yourself.
The pattern that avoids the question is POST-then-redirect, which you want
anyway.

### What this does not do

* No OAuth, no SAML, no LDAP, no OpenID. A password and a cookie.
* No permission model. `requireWhen` hands you a name and takes a `Bool`;
  where roles live and what they mean is your program's business.
* No TLS. Put it behind a reverse proxy — and until you do, `a.secure = false`
  or the cookie will not be sent at all.
* No account recovery, no email confirmation, no second factor.
* **The cryptography is hand-written.** `src/hash.keal` says so at the top and
  says why: the alternative was linking OpenSSL, which is one more thing to
  install and a second answer to *what does this depend on*. Every function in
  it is held to the vectors whoever specified it published — NIST's for
  SHA-256, RFC 4231's for HMAC, RFC 7914's for PBKDF2 — on every build. That is
  enough to say the algorithms are the algorithms. It is not an audit, and this
  guide will not pretend it is one.

## 17. What the framework will not do

* It will not talk to any database but SQLite, and only when you ask for it
  with a second import and `-lsqlite3`.
* It will not map rows onto your records for you. See §12.
* It will not compress. It will not speak HTTP/2, or TLS.
* It will not read a chunked request body — it answers **501** and says so.
* It will not read `multipart/form-data`, so there are no file uploads yet.
* It will not run your handler on another thread, so a handler that blocks
  blocks the server. Answer, and return.
* It will not escape what you put in `raw`. That is what the name is for.

---

## Where things are

| file | what is in it |
|---|---|
| `runtime/kb.h` | the whole C surface: sockets, `poll`, blobs |
| `src/ffi.keal` | the only file that mentions C |
| `src/bytes.keal` | byte buffers, hex, Base64, SHA-1 |
| `src/text.keal` | percent-encoding, forms, cookies, HTTP dates |
| `src/http.keal` | `Request`, `Response`, the wire format |
| `src/router.keal` | patterns, matching, dispatch |
| `src/server.keal` | the event loop and the connection state machine |
| `src/ui.keal` | the component tree and the renderer |
| `src/theme.keal` | the stylesheet and the document |
| `src/json.keal` | JSON both ways |
| `src/ws.keal` | WebSocket framing |
| `src/live.keal` | sessions, the diff, and the browser client |
| `src/css.keal` | stylesheets, written in Keal |
| `src/sql.keal` | SQLite: bound values, rows, transactions, migrations |
| `runtime/kb_sql.h` | the C for that, and the only thing that needs a library |
| `src/gzip.keal` | DEFLATE and the gzip container, fixed codes only |
| `src/upload.keal` | `multipart/form-data`, parsed on the bytes |
| `src/hash.keal` | SHA-256, HMAC, PBKDF2 — with the warning that goes with them |
| `src/auth.keal` | passwords, sessions, guards, the CSRF token |
| `src/app.keal` | the front door everything above is reachable from |
