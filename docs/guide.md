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

## 2. Routes

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

## 3. The request

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

## 4. The response

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

## 5. Pages

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

## 6. Forms without JavaScript

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

## 7. Live pages

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

## 8. Static files

```keal
site.files("/static", "./public")      // /static/a/b.css -> ./public/a/b.css
site.file("/favicon.svg", "./public/favicon.svg")
```

Each answer carries an `ETag` built from the file's timestamp and size, and a
client that sends it back gets a 304 with no body.

Any path with a `..` segment, a leading `/`, a backslash, or a dotfile
component is a **403** — refused, not normalised. Normalising a hostile path
is how a directory gets escaped.

## 9. JSON

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

## 10. Testing

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

The one shape in kealeb that needs it: a route's handler is kept by the router
and the router by the application, so a handler that captured `this` to read
the application's title would close the ring. Read the field into a local
before the lambda and the closure holds the value instead of the object that
had it. `weak` is not the answer here — it would say the application is only
weakly held by its own routes, which is not what the program means.

## 11. Running it

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

## 12. What the framework will not do

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
| `src/app.keal` | the front door everything above is reachable from |
