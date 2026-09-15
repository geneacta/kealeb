# Getting a project up

Every command on this page was run, in this order, on a machine that had
nothing but git and a C compiler on it. Where the guide explains, this page
only says what to type and what you should see. When something on it does not
happen the way it is written here, that is a bug in this page.

*La même marche à suivre en français : [`start.fr.md`](start.fr.md).*

---

## 1. What you need

| | for | check with |
|---|---|---|
| **git** | fetching Keal, kealeb, and your dependencies | `git --version` |
| **a C compiler** | `keal build` emits C and hands it to `cc`, or to `gcc` or `clang` when there is no `cc`. `CC=clang` chooses. | `cc --version` |
| **Rust, with cargo** | building the Keal compiler, once | `cargo --version` |
| **SQLite's library** | only if your program opens a database — `libsqlite3-dev` on Debian and Ubuntu, `sqlite-devel` on Fedora, `sqlite` from Homebrew | `pkg-config --libs sqlite3` |
| **node** | only to run kealeb's own browser test; a project never needs it | |

Linux, macOS and the BSDs. Windows is not there yet, and the build script says
so rather than trying.

## 2. Keal, the compiler

kealeb is written in Keal, and `keal build` is what turns a `.keal` file into
an executable. Build it once:

```sh
git clone https://github.com/geneacta/keal
cd keal
cargo build --release
```

That leaves the compiler at `target/release/keal`. Put it on your path:

```sh
cargo install --path .            # or: export PATH=$PWD/target/release:$PATH
keal --version                    # keal 1.3.0
```

kealeb declares the Keal it is built against in its own `keal.toml`, and the
badge at the top of the README shows it. Newer is fine; older may refuse
something this framework relies on, and says what.

The build script will also find a compiler that is **not** on your path: it
tries `$KEAL` first, then a `keal` checkout beside the project, then the path.
So `git clone` of both repositories side by side works with no path change at
all.

## 3. Two ways to start

The first shows you the framework in a minute. The second is the one you
keep.

### A. Inside kealeb's own repository

```sh
git clone https://github.com/geneacta/kealeb
cd kealeb
tools/build.sh examples/hello.keal
build/hello
```

Open `http://127.0.0.1:8080`. That is a page, styled, in dark mode if your
machine is, with no JavaScript on it. Ctrl-C stops it.

The other [examples](../examples) are whole programs too, each built and run
by the test suite:

| | | build with |
|---|---|---|
| `hello` | a page | `tools/build.sh examples/hello.keal` |
| `counter` | a live page: the state is on the server, only the difference travels | `tools/build.sh examples/counter.keal` |
| `todo` | a list to add to, tick off and filter — what a live page is for | `tools/build.sh examples/todo.keal` |
| `files` | serving a directory, including a file bigger than the machine | `tools/build.sh examples/files.keal` |
| `notes` | a live page whose state is a database | `tools/build.sh examples/notes.keal -lsqlite3` |
| `signin` | passwords, sessions, a guard and the CSRF token | `tools/build.sh examples/signin.keal -lsqlite3` |

The executable always lands in `build/`, named after the file.

### B. Your own project

A project that wants kealeb says so in a manifest, and stops caring where the
framework lives.

```sh
mkdir mysite && cd mysite
```

```toml
# keal.toml
[package]
name = "mysite"
version = "0.1.0"

[dependencies]
kealeb = { git = "https://github.com/geneacta/kealeb", tag = "v0.1.0" }
```

```sh
keal fetch
```

```
cloned kealeb (tag v0.1.0)
1 dependency in /home/you/mysite/.keal/deps
```

Two things appeared. `.keal/deps/kealeb/` is the framework, checked out at
the tag you named. `keal.lock` records the commit that tag resolved to, so a
tag moved upstream cannot quietly change what you build against — commit the
lockfile. `.keal/deps/` is yours to decide: commit it and the project builds
with no network and no git, or ignore it and run `keal fetch` after each
checkout. A `rev = "…"` naming a commit works in place of `tag`, and `keal
fetch` touches nothing else — no registry, no resolver, no newer version
picked on your behalf.

Now the program:

```keal
// app.keal
import "dep:kealeb/kealeb.keal"

val site = app("My site")

site.page("/", { req -> column([
    h1("Hello"),
    p("from Keal")
])})

site.run(8080)
```

The import says `dep:` and the dependency's name, and reads
`.keal/deps/kealeb/kealeb.keal` beside the nearest `keal.toml`. Build it with
the script that came with the dependency:

```sh
.keal/deps/kealeb/tools/build.sh app.keal
build/app
```

The output lands in **your** `build/`, not the dependency's. If you would
rather see the one flag the script adds — kealeb's C surface is a header, and
the compiler has to be told where it is:

```sh
mkdir -p build && cd build
keal build ../app.keal -I../.keal/deps/kealeb/runtime
```

`keal build` writes the executable, and the C it generated, into the directory
it runs in, which is why that runs from `build/`. Add `-lsqlite3` to either
command when the program imports `dep:kealeb/src/sql.keal`, and nothing
otherwise: kealeb links against no library at all unless you ask for the
database.

## 4. Check it without a browser

The program answers two questions on the command line and exits, instead of
binding a port:

```sh
build/app --routes
```

```
GET /
GET /kealeb/kealeb.css
GET /kealeb/kealeb.js
GET /kealeb/live
```

The last three are the framework's own — its stylesheet, its browser client,
and the socket a live page opens. And:

```sh
build/app --render /
```

prints the page's HTML on standard output, as this program builds it: filters
run, the 404 page answers a path with no route, `secure`'s headers are there.
It is what an editor or a build step should ask rather than guessing.

With the server running, from another terminal:

```sh
curl -i http://127.0.0.1:8080/
```

```
HTTP/1.1 200 OK
content-type: text/html; charset=utf-8
vary: accept-encoding
content-length: 320
connection: keep-alive
```

## 5. Stopping, and running it for real

Ctrl-C, and what a service manager sends, do not kill the process: they ask it
to stop, the listener closes, and connections in the middle of an answer get
five seconds to finish. Starting a second copy on the same port says so and
exits:

```
runtime error: kealeb could not start: port 8080 is already taken
```

`run(8080)` binds `127.0.0.1` and cannot surprise anybody. For a machine
other people reach:

```keal
site.run(8080, "")                    // every interface
site.log = false                      // no line per request
```

There is no TLS. Put it behind a reverse proxy, which is where a terminator
belongs; standard output is line-buffered from the moment the server starts,
so a log piped to a file or read by a supervisor arrives as it is written.
[§13 of the guide](guide.md#13-running-it) has the limits you can set — head
and body sizes, idle time, requests per connection — and
[the stopping order](guide.md#stopping).

## 6. What you can put in it

Everything below is one call on `site`, or one more import. Each row links to
the section of the guide that explains it.

| I want | write | guide |
|---|---|---|
| a page | `site.page("/about", { req -> column([h1("About")]) })` | [§6](guide.md#6-pages) |
| a route answering text | `site.get("/ping", { req -> text("pong") })` | [§3](guide.md#3-routes) |
| a path with a parameter | `site.get("/user/{id}", { req -> text(req.param("id")) })` | [§3](guide.md#what-a-pattern-can-say) |
| JSON in, JSON out | `parseJson(req.text())`, `jsonBody(jObj(fields).write())` | [§10](guide.md#10-json) |
| a form, no JavaScript | `site.formPage("/sign-up", build, onPost)` | [§7](guide.md#7-forms-without-javascript) |
| a file upload | `req.file("doc")`, then `.saveTo(path)` | [§7](guide.md#files) |
| a live page — state on the server, only the difference travels | `site.livePage("/", { req -> view({ -> … }) })` | [§8](guide.md#8-live-pages) |
| a stylesheet written in Keal | `site.css(sheet([rule(".hero").bg("…")]))` | [§6](guide.md#styles-written-in-keal) |
| my own JavaScript | `site.script("…")` | [§6](guide.md#javascript-and-when-you-need-it) |
| a directory of static files | `site.files("/static", "./public")` | [§9](guide.md#9-static-files) |
| my own 404 and error pages | `site.onNotFound(build)`, `site.onError(build)` | [§13](guide.md#when-there-is-nothing-there-and-when-something-broke) |
| something around every request — logging, a login wall | `site.use({ req, next -> next.on(req) })` | [§12](guide.md#12-filters) |
| work on a timer | `site.every(60000, job)`, `site.after(5000, job)` | [§14](guide.md#14-scheduled-work) |
| a database | `import "dep:kealeb/src/sql.keal"`, build with `-lsqlite3` | [§15](guide.md#15-a-database) |
| sign-in, sessions, CSRF, the security headers | `import "dep:kealeb/src/auth.keal"`, then `site.secure(auth(secret))` | [§16](guide.md#16-security) |
| tests with no socket | `dispatch(router, request("GET", "/x"))` | [§11](guide.md#11-testing) |
| to know what the framework will not do | | [§17](guide.md#17-what-the-framework-will-not-do) |

The paths in the import lines are the ones a project outside this repository
writes. Inside it, the examples say `../kealeb.keal` and `../src/sql.keal`
instead.

## 7. When it does not work

**`no keal compiler found — set KEAL, or build ../keal`.** The build script
looked in `$KEAL`, beside the project, and on the path. Either finish §2, or
tell it where the compiler is: `KEAL=/path/to/keal tools/build.sh app.keal`.

**`` `func main` must declare what it returns``.** An entry point that answers
nothing is a `proc main()`. And do not call it: Keal runs `main` by itself
once the top level has run, so a `main()` line at the bottom runs the whole
program twice.

**`the C backend cannot compile nested functions yet`.** A helper inside a
handler wants to be a top-level function instead. `examples/todo.keal` shows
the shape.

**`undefined reference to sqlite3_close`**, and a dozen linker lines like it.
The program imports `src/sql.keal` and the build did not say `-lsqlite3`. Add
it after the source file.

**`port 8080 is already taken`.** Another copy is running, or something else
is. Stop it, or pick another number in `run`.

**The page is there but a live page does nothing when clicked.** Look at the
browser's console: the client opens a WebSocket to `/kealeb/live`, and a
reverse proxy in front of the server has to pass upgrades through.
