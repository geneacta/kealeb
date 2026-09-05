/* kb.h — the C face of kealeb, and the only C in the framework.
 *
 * Everything here is `static inline`, and `native """#include "kb.h""""`
 * pastes it into the *same translation unit* as the compiled Keal program.
 * So a call from Keal to one of these is not a call: it is the system call
 * it contains, or the load it contains. That is what lets the HTTP parser,
 * the router, the renderer, the WebSocket framing and the component diff
 * above be written in Keal without paying for the choice.
 *
 * The rule this file is held to, borrowed from keal-view: **the C does not
 * decide anything.** It opens sockets, moves bytes, and says which
 * descriptors are ready. It does not parse a request, does not know what a
 * header is, and does not build a response. Everything that is a decision
 * lives in a `.keal` file where it can be read.
 *
 * The one exception is `kb_blob_text`, and the exception is deliberate:
 * turning arbitrary bytes from the network into a Keal `String` is a
 * property of the boundary itself, so the boundary is where it is checked.
 * Invalid UTF-8 becomes U+FFFD rather than reaching Keal as a String that
 * is not one.
 *
 * POSIX only for now — macOS and Linux. Windows wants Winsock and a
 * different poll; the surface below is drawn so that it can arrive as one
 * more `#if` rather than as a second design.
 */
#ifndef KEALEB_KB_H
#define KEALEB_KB_H

#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <time.h>
#include <unistd.h>
#include <poll.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <arpa/inet.h>

/* Answers of the byte-moving calls. A negative number is never a count. */
#define KB_CLOSED   0   /* the peer went away, cleanly                    */
#define KB_AGAIN   -1   /* nothing to move right now; wait for poll       */
#define KB_ERROR   -2   /* the descriptor is finished                     */

/* Bits of `kb_watch`'s interest set and of `kb_ready_events`. */
#define KB_READ     1
#define KB_WRITE    2
#define KB_GONE     4   /* hang-up or error; only ever reported, never asked for */

/* ------------------------------------------------------------------ blobs */

/* A byte array outside Keal's heap. Keal has no byte type and its `String`
 * is text, so everything that is not text — a request body, a frame being
 * assembled, a file being served — lives in one of these and is read a byte
 * at a time, which after inlining is one bounds-checked load. The length
 * sits in the eight bytes before the data, so a read checks its own bounds
 * without a second call. A handle is that data pointer as an `Int`; 0 is
 * the absent blob and every accessor tolerates it. */
static inline int64_t kb_blob_new(int64_t size) {
    if (size < 0) return 0;
    unsigned char *m = (unsigned char *)malloc((size_t)size + 8);
    if (!m) return 0;
    memcpy(m, &size, 8);
    memset(m + 8, 0, (size_t)size);
    return (int64_t)(m + 8);
}

static inline int64_t kb_blob_size(int64_t h) {
    if (!h) return 0;
    int64_t n; memcpy(&n, (unsigned char *)h - 8, 8); return n;
}

static inline int64_t kb_blob_get(int64_t h, int64_t i) {
    if (!h) return -1;
    if ((uint64_t)i >= (uint64_t)kb_blob_size(h)) return -1;
    return (int64_t)((unsigned char *)h)[i];
}

static inline void kb_blob_set(int64_t h, int64_t i, int64_t v) {
    if (h && (uint64_t)i < (uint64_t)kb_blob_size(h))
        ((unsigned char *)h)[i] = (unsigned char)v;
}

static inline void kb_blob_free(int64_t h) {
    if (h) free((unsigned char *)h - 8);
}

/* A bigger blob holding what this one holds. The old handle stays valid and
 * is the caller's to free — growing is a copy, not a realloc, because a
 * realloc may move and a handle that moved under a caller is a bug nobody
 * finds twice. */
static inline int64_t kb_blob_grow(int64_t h, int64_t size) {
    int64_t n = kb_blob_new(size);
    if (!n) return 0;
    int64_t old = kb_blob_size(h);
    if (old > size) old = size;
    if (old > 0) memcpy((void *)n, (const void *)h, (size_t)old);
    return n;
}

/* Move `len` bytes from one blob to another. Answers what it moved. */
static inline int64_t kb_blob_copy(int64_t dst, int64_t dof,
                                   int64_t src, int64_t sof, int64_t len) {
    if (!dst || !src || len <= 0) return 0;
    int64_t dn = kb_blob_size(dst), sn = kb_blob_size(src);
    if (dof < 0 || sof < 0 || dof > dn || sof > sn) return 0;
    if (len > dn - dof) len = dn - dof;
    if (len > sn - sof) len = sn - sof;
    if (len <= 0) return 0;
    memmove((unsigned char *)dst + dof, (unsigned char *)src + sof, (size_t)len);
    return len;
}

/* The bytes of a Keal `String`, appended into a blob at `off`. Answers how
 * many it wrote, or -1 if they do not fit. This is how a header line built
 * in Keal becomes bytes on the way out. */
static inline int64_t kb_blob_write(int64_t h, int64_t off, const char *s) {
    if (!h || !s || off < 0) return -1;
    size_t len = strlen(s);
    if (off + (int64_t)len > kb_blob_size(h)) return -1;
    memcpy((unsigned char *)h + off, s, len);
    return (int64_t)len;
}

/* How many bytes a `String` occupies. `String.length` counts characters;
 * a Content-Length counts bytes, and the two differ the moment anybody
 * types an accent. */
static inline int64_t kb_text_bytes(const char *s) {
    return s ? (int64_t)strlen(s) : 0;
}

/* --------------------------------------------------------- bytes to text */

/* `len` bytes of `h` as a Keal `String`.
 *
 * The boundary's one decision, and it is a safety property rather than a
 * policy: what arrives from a socket is bytes, what Keal calls a `String`
 * is UTF-8, and the two are not the same claim. Every byte sequence that is
 * not well-formed UTF-8 — a stray continuation, an over-long encoding, a
 * surrogate, a truncated tail — becomes U+FFFD, one per offending byte, and
 * an embedded NUL becomes U+FFFD too, because a Keal string ends at one.
 * Text that is already valid is copied unchanged, which is every request a
 * conforming client sends. */
static inline int64_t kb_utf8_len(unsigned char c) {
    if (c < 0x80) return 1;
    if ((c & 0xE0) == 0xC0) return 2;
    if ((c & 0xF0) == 0xE0) return 3;
    if ((c & 0xF8) == 0xF0) return 4;
    return 0;
}

/* The validator itself, over any bytes. `kb_blob_text` was its only caller
 * until a database needed one too: text out of SQLite is UTF-8 if whatever
 * wrote it was honest, and "if whatever wrote it was honest" is not a promise
 * a boundary gets to make. One validator, every caller. */
static inline char *kb_text_from(const unsigned char *p, int64_t len) {
    if (!p || len < 0) { char *e = (char *)malloc(1); if (e) e[0] = 0; return e; }
    /* Worst case every byte becomes three. */
    char *out = (char *)malloc((size_t)len * 3 + 1);
    if (!out) return NULL;
    int64_t i = 0, o = 0;
    while (i < len) {
        unsigned char c = p[i];
        int64_t want = c ? kb_utf8_len(c) : 0;
        int ok = want > 0 && i + want <= len;
        if (ok) {
            for (int64_t k = 1; k < want; k++)
                if ((p[i + k] & 0xC0) != 0x80) { ok = 0; break; }
        }
        if (ok && want == 2 && c < 0xC2) ok = 0;                       /* over-long */
        if (ok && want == 3 && c == 0xE0 && p[i + 1] < 0xA0) ok = 0;   /* over-long */
        if (ok && want == 3 && c == 0xED && p[i + 1] >= 0xA0) ok = 0;  /* surrogate */
        if (ok && want == 4 && c == 0xF0 && p[i + 1] < 0x90) ok = 0;   /* over-long */
        if (ok && want == 4 && (c > 0xF4 || (c == 0xF4 && p[i + 1] >= 0x90))) ok = 0;
        if (ok) {
            for (int64_t k = 0; k < want; k++) out[o++] = (char)p[i + k];
            i += want;
        } else {
            out[o++] = (char)0xEF; out[o++] = (char)0xBF; out[o++] = (char)0xBD;
            i += 1;
        }
    }
    out[o] = 0;
    return out;
}

static inline char *kb_blob_text(int64_t h, int64_t off, int64_t len) {
    if (!h || off < 0 || len < 0) { char *e = (char *)malloc(1); if (e) e[0] = 0; return e; }
    int64_t n = kb_blob_size(h);
    if (off > n) off = n;
    if (len > n - off) len = n - off;
    return kb_text_from((const unsigned char *)h + off, len);
}

/* ---------------------------------------------------------------- sockets */

/* Never die because a browser closed a tab mid-response. Called once, from
 * the server's own start-up, and it is the whole of kealeb's signal policy. */
static inline void kb_ignore_sigpipe(void) { signal(SIGPIPE, SIG_IGN); }

/* Line-buffer standard output.
 *
 * C buffers a stream by blocks when it is not a terminal, so a server whose
 * output is piped to a file or a supervisor prints its log in four-kilobyte
 * bursts — or, if it is killed, not at all. A log that arrives after the
 * question it would have answered is not a log. Called once, next to the
 * signal above, and for the same reason: it is a property of being a server
 * rather than a decision any handler makes. */
static inline void kb_stdout_lines(void) { setvbuf(stdout, NULL, _IOLBF, 0); }

static inline int kb_nonblocking(int fd) {
    int fl = fcntl(fd, F_GETFL, 0);
    if (fl < 0) return -1;
    return fcntl(fd, F_SETFL, fl | O_NONBLOCK);
}

/* Bind and listen. `host` is an IPv4 address in dotted form, or "" for every
 * interface — 127.0.0.1 while developing is not paranoia, it is the default
 * that cannot surprise anybody. Answers the descriptor, or a negative number
 * naming which step failed: -1 socket, -2 address, -3 bind, -4 listen. */
static inline int64_t kb_listen(const char *host, int64_t port, int64_t backlog) {
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) return -1;
    int one = 1;
    setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
    struct sockaddr_in a;
    memset(&a, 0, sizeof a);
    a.sin_family = AF_INET;
    a.sin_port = htons((unsigned short)port);
    if (!host || !*host) {
        a.sin_addr.s_addr = htonl(INADDR_ANY);
    } else if (inet_pton(AF_INET, host, &a.sin_addr) != 1) {
        close(fd); return -2;
    }
    if (bind(fd, (struct sockaddr *)&a, sizeof a) < 0) { close(fd); return -3; }
    if (listen(fd, (int)(backlog > 0 ? backlog : 128)) < 0) { close(fd); return -4; }
    kb_nonblocking(fd);
    return (int64_t)fd;
}

/* The port a listener actually got, which is the question worth asking when
 * it was asked to listen on 0. */
static inline int64_t kb_local_port(int64_t fd) {
    struct sockaddr_in a;
    socklen_t n = sizeof a;
    if (getsockname((int)fd, (struct sockaddr *)&a, &n) < 0) return -1;
    return (int64_t)ntohs(a.sin_port);
}

/* The next waiting connection, or KB_AGAIN when there is none. Accepted
 * descriptors are non-blocking and Nagle is off: a framework that batches
 * its own writes has nothing to gain from the kernel batching them again,
 * and everything to lose in latency. */
static inline int64_t kb_accept(int64_t fd) {
    int c = accept((int)fd, NULL, NULL);
    if (c < 0) return (errno == EAGAIN || errno == EWOULDBLOCK) ? KB_AGAIN : KB_ERROR;
    kb_nonblocking(c);
    int one = 1;
    setsockopt(c, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
    return (int64_t)c;
}

/* The peer's address, as text. Empty when it cannot be had. */
static inline char *kb_peer(int64_t fd) {
    struct sockaddr_in a;
    socklen_t n = sizeof a;
    char buf[INET_ADDRSTRLEN + 8];
    buf[0] = 0;
    if (getpeername((int)fd, (struct sockaddr *)&a, &n) == 0)
        inet_ntop(AF_INET, &a.sin_addr, buf, sizeof buf);
    size_t len = strlen(buf);
    char *out = (char *)malloc(len + 1);
    if (out) memcpy(out, buf, len + 1);
    return out;
}

/* Read into `h` at `off`, at most `max` bytes. Answers the count, or
 * KB_CLOSED, KB_AGAIN, KB_ERROR. */
static inline int64_t kb_recv(int64_t fd, int64_t h, int64_t off, int64_t max) {
    if (!h) return KB_ERROR;
    int64_t n = kb_blob_size(h);
    if (off < 0 || off >= n) return KB_ERROR;
    if (max > n - off) max = n - off;
    if (max <= 0) return KB_ERROR;
    ssize_t got = recv((int)fd, (unsigned char *)h + off, (size_t)max, 0);
    if (got > 0) return (int64_t)got;
    if (got == 0) return KB_CLOSED;
    if (errno == EAGAIN || errno == EWOULDBLOCK) return KB_AGAIN;
    if (errno == EINTR) return KB_AGAIN;
    return KB_ERROR;
}

/* Write `len` bytes of `h` from `off`. Answers what it managed — a short
 * write is ordinary and is the caller's to resume — or KB_AGAIN / KB_ERROR. */
static inline int64_t kb_send(int64_t fd, int64_t h, int64_t off, int64_t len) {
    if (!h) return KB_ERROR;
    int64_t n = kb_blob_size(h);
    if (off < 0 || off > n) return KB_ERROR;
    if (len > n - off) len = n - off;
    if (len <= 0) return 0;
    ssize_t put = send((int)fd, (const unsigned char *)h + off, (size_t)len,
#ifdef MSG_NOSIGNAL
                       MSG_NOSIGNAL
#else
                       0
#endif
    );
    if (put >= 0) return (int64_t)put;
    if (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR) return KB_AGAIN;
    return KB_ERROR;
}

static inline void kb_close(int64_t fd) { if (fd >= 0) close((int)fd); }

/* ------------------------------------------------------------- the wait */

/* The descriptors the loop is interested in, and what came back ready.
 * Keal owns the decision of what to watch; this is the array and the one
 * `poll` call. 4096 is not a connection limit anybody will meet by accident
 * and a growable set would be a second allocation policy for no gain. */
#define KB_MAX_WATCH 4096
static struct pollfd kb_set[KB_MAX_WATCH];
static int64_t        kb_set_n = 0;
static struct pollfd kb_hot[KB_MAX_WATCH];
static int64_t        kb_hot_n = 0;

static inline int64_t kb_find(int64_t fd) {
    for (int64_t i = 0; i < kb_set_n; i++) if (kb_set[i].fd == (int)fd) return i;
    return -1;
}

/* Watch `fd` for `events` (KB_READ | KB_WRITE), replacing any earlier
 * interest in it. Answers 1, or 0 when the set is full. */
static inline int64_t kb_watch(int64_t fd, int64_t events) {
    short e = 0;
    if (events & KB_READ)  e |= POLLIN;
    if (events & KB_WRITE) e |= POLLOUT;
    int64_t at = kb_find(fd);
    if (at < 0) {
        if (kb_set_n >= KB_MAX_WATCH) return 0;
        at = kb_set_n++;
        kb_set[at].fd = (int)fd;
    }
    kb_set[at].events = e;
    kb_set[at].revents = 0;
    return 1;
}

static inline void kb_unwatch(int64_t fd) {
    int64_t at = kb_find(fd);
    if (at < 0) return;
    kb_set[at] = kb_set[--kb_set_n];
}

static inline int64_t kb_watching(void) { return kb_set_n; }

/* Wait until something is ready or `ms` have passed; a negative `ms` waits
 * for ever. Answers how many descriptors are ready, and freezes them so
 * that Keal can close one while walking the list without the ground moving.
 * That copy is the reason this is not just a thin `poll`. */
static inline int64_t kb_poll(int64_t ms) {
    int n = poll(kb_set, (nfds_t)kb_set_n, (int)ms);
    kb_hot_n = 0;
    if (n <= 0) return n < 0 && errno != EINTR ? KB_ERROR : 0;
    for (int64_t i = 0; i < kb_set_n && kb_hot_n < KB_MAX_WATCH; i++)
        if (kb_set[i].revents) kb_hot[kb_hot_n++] = kb_set[i];
    return kb_hot_n;
}

static inline int64_t kb_ready_fd(int64_t i) {
    if (i < 0 || i >= kb_hot_n) return -1;
    return (int64_t)kb_hot[i].fd;
}

static inline int64_t kb_ready_events(int64_t i) {
    if (i < 0 || i >= kb_hot_n) return 0;
    short r = kb_hot[i].revents;
    int64_t e = 0;
    if (r & POLLIN)  e |= KB_READ;
    if (r & POLLOUT) e |= KB_WRITE;
    if (r & (POLLHUP | POLLERR | POLLNVAL)) e |= KB_GONE;
    return e;
}

/* ------------------------------------------------------- clock and chance */

/* Milliseconds since an arbitrary fixed point. Timeouts are differences, and
 * a difference must not jump because somebody corrected the wall clock. */
static inline int64_t kb_mono_ms(void) {
    struct timespec t;
#ifdef CLOCK_MONOTONIC
    clock_gettime(CLOCK_MONOTONIC, &t);
#else
    clock_gettime(CLOCK_REALTIME, &t);
#endif
    return (int64_t)t.tv_sec * 1000 + t.tv_nsec / 1000000;
}

/* Seconds since the epoch — what a `Date:` header and a cookie expiry mean. */
static inline int64_t kb_epoch_s(void) { return (int64_t)time(NULL); }

/* Eight bytes nobody can guess, which is what a session identifier has to
 * be. `random()` is a different promise and must not be used for this. */
static inline int64_t kb_secure_random(void) {
    int64_t v = 0;
    FILE *f = fopen("/dev/urandom", "rb");
    if (f) {
        size_t got = fread(&v, 1, sizeof v, f);
        fclose(f);
        if (got == sizeof v) return v < 0 ? -v : v;
    }
    /* Nothing here should ever run. If it does, say so rather than hand
     * back a token that only looks random. */
    return -1;
}

/* ------------------------------------------------------------ the files */

/* A file's bytes, or 0. Serving a stylesheet, an image or a font wants
 * bytes, and `readFile` answers text. */
static inline int64_t kb_file_read(const char *path) {
    FILE *f = fopen(path, "rb");
    if (!f) return 0;
    if (fseek(f, 0, SEEK_END) != 0) { fclose(f); return 0; }
    long n = ftell(f);
    if (n < 0) { fclose(f); return 0; }
    rewind(f);
    int64_t h = kb_blob_new((int64_t)n);
    if (!h) { fclose(f); return 0; }
    size_t got = n > 0 ? fread((void *)h, 1, (size_t)n, f) : 0;
    fclose(f);
    if (got != (size_t)n) { kb_blob_free(h); return 0; }
    return h;
}

/* Write bytes to a file, replacing whatever was there. Answers 1, or 0.
 *
 * `writeFile` in the prelude takes a `String`, and an upload is not text. This
 * is the other half of `kb_file_read`, and it exists for exactly one caller:
 * a `Part` being saved. */
static inline int64_t kb_file_write(const char *path, int64_t h, int64_t off, int64_t len) {
    if (!path || !h || off < 0 || len < 0) return 0;
    int64_t n = kb_blob_size(h);
    if (off > n) return 0;
    if (len > n - off) len = n - off;
    FILE *f = fopen(path, "wb");
    if (!f) return 0;
    size_t put = len > 0 ? fwrite((const unsigned char *)h + off, 1, (size_t)len, f) : 0;
    int bad = fclose(f) != 0;
    return (!bad && put == (size_t)len) ? 1 : 0;
}

/* When a file last changed, in seconds since the epoch, or -1. An ETag is
 * cheaper than re-reading a file that has not moved. */
static inline int64_t kb_file_mtime(const char *path) {
    struct stat st;
    if (stat(path, &st) != 0) return -1;
    return (int64_t)st.st_mtime;
}

#endif /* KEALEB_KB_H */
