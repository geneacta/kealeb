# kealeb — web pages that stay on the server, written in Keal

A web framework for [Keal](https://github.com/geneacta/keal): routes and
handlers like Spring Boot, pages built out of components like Vaadin, and
**the whole thing is `.keal` files**. The C underneath opens sockets, moves
bytes, and says which descriptors are ready. It does not parse a request, does
not know what a header is, and does not decide anything.

```
              lines    what it is
  Keal         3 580   the whole framework: HTTP, routing, the component
                       tree, the renderer, stylesheets, JSON, WebSocket
                       framing, the scheduler, the session hub and the diff
  C              442   sockets, poll, byte blobs — one header, no .c file
  JavaScript     132   the browser client: open a socket, report an event,
                       apply six kinds of patch
```

A live page keeps its state on the server and sends the browser only what
changed. You write no HTML, no JavaScript, and no template.

## Hello

```keal
import "kealeb/kealeb.keal"

val site = app("Hello")

site.page("/", { req -> column([
    h1("Hello"),
    p("from Keal")
])})

site.run(8080)
```

```sh
tools/build.sh hello.keal && build/hello
```

That is a whole page, styled, in dark mode if the machine is, at
`http://127.0.0.1:8080`.

## A live page

The same tree, except the state lives on the server and only the difference
travels:

```keal
site.livePage("/", { req ->
    var count = 0
    view({ -> column([
        h1("Clicked ${count} times"),
        button("Click me", { e -> count = count + 1 })
    ]) })
})
```

Click the button and this crosses the socket:

```json
{"p":[["t","0.0.0","Clicked 1 times"]]}
```

One patch. The browser sets one text node. There is no JSON schema to write,
no endpoint, no client state, and nothing to keep in sync — `count` is an
ordinary Keal variable and the page is a function of it.

**`livePage`'s outer function runs once per visitor.** Whatever it closes over
is that visitor's own state, so there is no session map to key correctly: the
closure *is* the session. What it answers is called again after every event.

[`examples/todo.keal`](examples/todo.keal) is the whole of a to-do list — add,
tick off, remove, filter — in about seventy lines, and
[`examples/counter.keal`](examples/counter.keal) is the counter above with a
step you can change.

## Why this is possible

One fact about the compiler decides the design, and keal-view found it first:
`native """..."""` pastes its C into **the same translation unit** as the
compiled program, so a `static inline` function declared there is inlined into
Keal's own code by the C compiler. A call across the boundary is not a call —
it is the system call it contains.

```keal
public extern func recvInto(fd: Int, h: Int, off: Int, max: Int): Int = "kb_recv"
```

That is `recv(2)`. So there was no reason to write the HTTP parser in C, and
every reason not to. The whole C surface is
[`runtime/kb.h`](runtime/kb.h): sockets, `poll`, byte blobs, the clock, and
`/dev/urandom`. The file that binds it is [`src/ffi.keal`](src/ffi.keal), and
it is **the only file in the repository that mentions C**.

The one decision the C does make is deliberate and is a property of the
boundary rather than a policy: bytes off a socket are not a Keal `String`
until somebody has checked they are UTF-8, so `kb_blob_text` checks, and what
is not well-formed arrives as U+FFFD rather than as a string that is not one.

## One thread, and why

Every socket is non-blocking, one `poll` drives everything, and a handler runs
to completion with nothing else running. So session state is an ordinary Keal
object, **there is no lock anywhere in kealeb**, and a data race is not a thing
that can be written here.

The cost is stated rather than hidden: a handler that blocks blocks the
server. Handlers answer and return. Several loops on several cores can be
added later without any of this changing shape, because nothing in
`server.keal` assumes it is the only one.

Deterministic destruction does the rest of the bookkeeping. A `Buf` owns one
blob and gives it back in `deinit`, so a connection that dies frees its
buffers at the statement its last reference goes — no pool, no collector, and
nothing to remember.

It also decides one shape in `src/app.keal` that would otherwise look
arbitrary. A route's handler is kept by the router and the router by the
application, so a handler reads the application's own configuration into a
local *before* the lambda rather than capturing `this`. Capturing `this` would
close that ring, and reference counting cannot open one: changing a single
line to do it leaks the `App`, the `Router`, every `Route` and the session hub
— measured, and the reason `tests/lifetime.keal` exists.

## What is in it

**HTTP/1.1.** Keep-alive, pipelining, `HEAD`, `Expect: 100-continue`, chunked
*responses* not yet and chunked *requests* refused by name with 501. Request
and response are one class each; a header sent twice arrives joined with a
comma, because that is what the protocol says it means. `Content-Length` is
written from the body's byte count and cannot be overridden.

**Routing.** `/user/{id}` captures, `/files/{rest...}` captures the tail. When
two patterns match, the one with more literal segments wins — `/user/new`
beats `/user/{id}` whichever was declared first, and that is the only
precedence rule there is. A path that exists under another verb is a 405 that
says which verbs it takes, not a 404.

**Pages.** A tree of components, rendered and sent. Text is escaped, always;
`raw` is spelt differently on purpose. A stylesheet is included — small,
prefixed `kb-`, and following the operating system's dark mode — and
`style = ""` turns it off entirely.

**Live pages.** The tree stays on the server; an event runs a handler,
rebuilds the tree, compares it with the last one, and sends the difference as
at most six kinds of patch. Reconnects on its own. Sessions expire.

**Stylesheets, written in Keal.** `rule(".hero").bg(accent).pad("3rem")` is a
value, so it can be held in a list, returned from a function and built from a
loop. `site.css(sheet([...]))` serves it at a URL naming its own contents,
which is a one-year `immutable` cache that still changes the instant the
stylesheet does. `site.script(...)` does the same for the JavaScript you should
not need — a map widget, a chart — and says so.

**Scheduled work.** `site.every(60000, { -> sweep() })` runs on the loop's own
thread, between requests and never during one, so a job reads and writes what a
handler reads and writes with nothing to synchronise. A job that throws is
reported and keeps its schedule. The whole cost is one comparison per turn: the
loop was already sleeping with a deadline.

**The rest.** Static files with ETags and a 403 for any path that tries to
climb. JSON both ways, surrogate pairs included. WebSocket framing, RFC 6455,
no extensions. Cookies. Forms, including repeated fields.

## Getting started

```sh
git clone https://github.com/geneacta/keal
git clone https://github.com/geneacta/kealeb
cd keal && cargo build --release && cd ../kealeb
tools/build.sh examples/todo.keal
build/todo
```

Then open `http://127.0.0.1:8080`.

`tools/build.sh` is fifteen lines and there is no object file to compile
first: the whole C surface is `static inline` in one header, so `keal build`
compiles it as part of the program.

* **[The guide](docs/guide.md)** — routes, pages, live pages, the widgets,
  static files, sessions, testing, deployment. Read this one.
* **[Le guide, en français](docs/guide.fr.md)** — the same walkthrough.

## The tests

```sh
tools/test.sh
```

`units` holds the buffers, the encodings, the request parser, the router, the
renderer, the diff, the stylesheet builder, the scheduler and the asset rules
to their answers — 162 checks, no network. `lifetime` builds an application, uses it, drops it, and reads what
`keal build --audit` says outlived it, which must be nothing. `cc` emits the
backend's own C and compiles it under five `-Werror` names — one of which had
been announcing a real miscompilation on every build until somebody read it.

Those last two assert **negatives**, and a negative goes green the moment the
instrument stops working. So each has a control. `leaks` builds a reference
cycle on purpose — a closure that captures `this` and is stored in the object
it captured — and requires the audit to still see it, and to see exactly one,
since the two objects in that file differ only in what their closure holds.
The `cc` step hands each of its five flags a fault of its own and requires
each to refuse it. Five flags that reject nothing pass everything. `client` is the one that matters: it builds the counter example,
starts it, loads the page the server actually sends, runs the JavaScript the
server actually serves against a DOM small enough to read, and clicks the
button. The client is the only part of kealeb that does not run under `keal`,
so leaving it unchecked would put the framework's whole promise on the one
file nothing tests.

It needs `node` for that, and says so rather than passing quietly when there
is none.

## What is not here yet

The honest list.

* **Moving a node cheaply.** `.keyed(id)` already decides *identity* — a node
  whose key changed is rebuilt rather than patched, so a list that shifted up
  by one does not hand the browser's caret and focus to a different row. What
  it does not yet do is make the move cheap: the diff walks children by index
  and does not look for one that moved, so inserting at the front still
  rewrites everything after it. Correct, and more work than it needs to be.
* **A database.** Nothing at all — no driver, no SQL, no pool. This is the
  largest thing missing, and it is missing on purpose until somebody decides
  which database and accepts what that adds to the build: Keal reaches C, so
  SQLite is four commands away and Postgres is a protocol nobody has written
  here yet.
* **TLS.** None. Put it behind a reverse proxy, which is where a terminator
  belongs anyway.
* **Windows.** `runtime/kb.h` is POSIX. Winsock wants a different `poll` and a
  different `close`; the surface is drawn so that it arrives as one more
  `#if`, not as a second design.
* **Chunked request bodies**, `multipart/form-data` (so no file uploads yet),
  and compression. Each is refused by name rather than half-read.
* **Several event loops.** One core today.
* **A filter chain.** `Server.handle` is one function and can be replaced
  wholesale, which covers logging and authentication awkwardly. A proper
  `before`/`after` belongs here.

Three things kealeb wants from the language, and does not have. `keal build`
does not compile **nested functions**, which is the natural shape for a page's
helpers — it refuses them by name, and
[`examples/todo.keal`](examples/todo.keal) says what to write instead. A
lambda cannot capture a **top-level binding from another module**, so
`src/app.keal` copies two into locals first. And a **lambda's parameter cannot
be `var`**, so nothing a handler is given can be changed — which is why
`dispatch` builds a new `Request` rather than writing the captured parameters
into the old one, and it turned out to be the better design.

## License

Apache License 2.0 — see [LICENSE](LICENSE), the same as Keal's, and for the
same reason: what goes through Keal comes out as C, and everyone involved
should know where they stand.
