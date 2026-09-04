/* kb_sql.h — the C face of kealeb's SQLite binding, and nothing else.
 *
 * Separate from `kb.h` on purpose. A program that never opens a database must
 * not link against one, so this header is pasted into the translation unit
 * only when `src/sql.keal` is imported, and only then does the build need
 * `-lsqlite3`. Importing `kealeb/kealeb.keal` does not reach this file.
 *
 * The rule `kb.h` is held to is the rule here: **the C decides nothing.** It
 * opens a connection, prepares a statement, binds a value, steps a row and
 * reads a column. It does not build SQL, does not decide when a transaction
 * ends, does not know what a row means. Everything that is a decision is in
 * `src/sql.keal`, where it can be read.
 *
 * SQLite's own handles are pointers; they cross as `Int`, which is what
 * `docs/memory.md` allows and what `kb.h` already does for a blob. Zero is
 * always the absent handle and every accessor tolerates it.
 *
 * One thing this file does that is not a system call: text out of the
 * database goes through `kb_text_from`, the same UTF-8 validator every byte
 * from a socket goes through. A column is UTF-8 if whatever wrote it was
 * honest, and "if whatever wrote it was honest" is not a promise a boundary
 * gets to make.
 */
#ifndef KEALEB_KB_SQL_H
#define KEALEB_KB_SQL_H

#include "kb.h"
#include <sqlite3.h>

/* What `kbs_step` answers, spelt so that `sql.keal` need not know SQLite's
 * numbers. */
#define KBS_ROW   1
#define KBS_DONE  2
#define KBS_ERROR 3

/* The five types a column can have, in the order `sql.keal` names them. */
#define KBS_NULL   0
#define KBS_INT    1
#define KBS_FLOAT  2
#define KBS_TEXT   3
#define KBS_BLOB   4

/* ----------------------------------------------------------- connections */

/* Open, creating the file if it is not there. `:memory:` is a database that
 * lives as long as the connection. Answers the handle, or 0.
 *
 * Foreign keys are switched on, because SQLite's default is off for
 * compatibility with 2005 and a program that declares a foreign key means it.
 * A busy timeout is set for the same reason a server sets one: the alternative
 * to waiting 5 seconds is failing immediately, and failing immediately is not
 * what anybody wants from a second connection. */
static inline int64_t kbs_open(const char *path) {
    sqlite3 *db = NULL;
    if (sqlite3_open(path, &db) != SQLITE_OK) {
        if (db) sqlite3_close(db);
        return 0;
    }
    sqlite3_busy_timeout(db, 5000);
    sqlite3_exec(db, "PRAGMA foreign_keys = ON", NULL, NULL, NULL);
    return (int64_t)(intptr_t)db;
}

static inline void kbs_close(int64_t h) {
    if (h) sqlite3_close((sqlite3 *)(intptr_t)h);
}

/* What went wrong, in whatever words SQLite has for it. */
static inline char *kbs_errmsg(int64_t h) {
    const char *m = h ? sqlite3_errmsg((sqlite3 *)(intptr_t)h) : "no connection";
    if (!m) m = "";
    return kb_text_from((const unsigned char *)m, (int64_t)strlen(m));
}

/* Rows added, changed or deleted by the most recent statement. */
static inline int64_t kbs_changes(int64_t h) {
    return h ? (int64_t)sqlite3_changes((sqlite3 *)(intptr_t)h) : 0;
}

/* The rowid the most recent insert gave out. */
static inline int64_t kbs_last_id(int64_t h) {
    return h ? (int64_t)sqlite3_last_insert_rowid((sqlite3 *)(intptr_t)h) : 0;
}

/* Run one or more statements with no parameters at all.
 *
 * The parameterless-ness is the point rather than a limitation: this is for a
 * schema, which the program wrote and which no request touches. Everything a
 * request can reach goes through `kbs_prepare` and a bound value, and the two
 * being different functions with different shapes is what makes that a rule a
 * reader can check rather than a habit. Answers 1, or 0 with the reason in
 * `kbs_errmsg`. */
static inline int64_t kbs_exec(int64_t h, const char *sql) {
    if (!h || !sql) return 0;
    return sqlite3_exec((sqlite3 *)(intptr_t)h, sql, NULL, NULL, NULL) == SQLITE_OK;
}

/* ------------------------------------------------------------ statements */

/* Compile one statement. Answers the handle, or one of two refusals — and the
 * two are different because the words for them are different.
 *
 * 0 means SQLite would not compile it, and `kbs_errmsg` then says why. -1
 * means it compiled something and there was **more after it**: a second
 * statement, which `sql.keal` runs one of per call, and which is either a
 * mistake or an injection. SQLite has nothing to say about that case — the
 * prepare succeeded — so asking it produces the phrase `not an error`, which
 * is true and is the least helpful thing a caller could be told. */
#define KBS_TRAILING (-1)

static inline int64_t kbs_prepare(int64_t h, const char *sql) {
    if (!h || !sql) return 0;
    sqlite3_stmt *st = NULL;
    const char *tail = NULL;
    if (sqlite3_prepare_v2((sqlite3 *)(intptr_t)h, sql, -1, &st, &tail) != SQLITE_OK) {
        if (st) sqlite3_finalize(st);
        return 0;
    }
    if (!st) return 0;                       /* whitespace or a comment */
    if (tail) {
        while (*tail == ' ' || *tail == '\t' || *tail == '\n' || *tail == '\r' || *tail == ';') tail++;
        if (*tail) { sqlite3_finalize(st); return KBS_TRAILING; }
    }
    return (int64_t)(intptr_t)st;
}

static inline void kbs_finalize(int64_t s) {
    if (s) sqlite3_finalize((sqlite3_stmt *)(intptr_t)s);
}

/* How many `?` the statement has. */
static inline int64_t kbs_bind_count(int64_t s) {
    return s ? (int64_t)sqlite3_bind_parameter_count((sqlite3_stmt *)(intptr_t)s) : 0;
}

/* Bind, one-based as SQLite counts. Each answers 1 or 0. */
static inline int64_t kbs_bind_int(int64_t s, int64_t i, int64_t v) {
    if (!s) return 0;
    return sqlite3_bind_int64((sqlite3_stmt *)(intptr_t)s, (int)i, v) == SQLITE_OK;
}

static inline int64_t kbs_bind_float(int64_t s, int64_t i, double v) {
    if (!s) return 0;
    return sqlite3_bind_double((sqlite3_stmt *)(intptr_t)s, (int)i, v) == SQLITE_OK;
}

/* SQLITE_TRANSIENT: SQLite copies the bytes, because the Keal string they came
 * from is borrowed and is gone when this returns. */
static inline int64_t kbs_bind_text(int64_t s, int64_t i, const char *v) {
    if (!s || !v) return 0;
    return sqlite3_bind_text((sqlite3_stmt *)(intptr_t)s, (int)i, v, -1,
                             SQLITE_TRANSIENT) == SQLITE_OK;
}

static inline int64_t kbs_bind_null(int64_t s, int64_t i) {
    if (!s) return 0;
    return sqlite3_bind_null((sqlite3_stmt *)(intptr_t)s, (int)i) == SQLITE_OK;
}

/* Advance. KBS_ROW when a row is there to read, KBS_DONE at the end,
 * KBS_ERROR otherwise. */
static inline int64_t kbs_step(int64_t s) {
    if (!s) return KBS_ERROR;
    int rc = sqlite3_step((sqlite3_stmt *)(intptr_t)s);
    if (rc == SQLITE_ROW) return KBS_ROW;
    if (rc == SQLITE_DONE) return KBS_DONE;
    return KBS_ERROR;
}

/* ---------------------------------------------------------------- columns */

static inline int64_t kbs_columns(int64_t s) {
    return s ? (int64_t)sqlite3_column_count((sqlite3_stmt *)(intptr_t)s) : 0;
}

static inline char *kbs_column_name(int64_t s, int64_t i) {
    const char *n = s ? sqlite3_column_name((sqlite3_stmt *)(intptr_t)s, (int)i) : NULL;
    if (!n) n = "";
    return kb_text_from((const unsigned char *)n, (int64_t)strlen(n));
}

static inline int64_t kbs_column_type(int64_t s, int64_t i) {
    if (!s) return KBS_NULL;
    switch (sqlite3_column_type((sqlite3_stmt *)(intptr_t)s, (int)i)) {
        case SQLITE_INTEGER: return KBS_INT;
        case SQLITE_FLOAT:   return KBS_FLOAT;
        case SQLITE_TEXT:    return KBS_TEXT;
        case SQLITE_BLOB:    return KBS_BLOB;
        default:             return KBS_NULL;
    }
}

static inline int64_t kbs_column_int(int64_t s, int64_t i) {
    return s ? (int64_t)sqlite3_column_int64((sqlite3_stmt *)(intptr_t)s, (int)i) : 0;
}

static inline double kbs_column_float(int64_t s, int64_t i) {
    return s ? sqlite3_column_double((sqlite3_stmt *)(intptr_t)s, (int)i) : 0.0;
}

/* The text of a column, validated as UTF-8 on the way across. A BLOB read
 * this way is its bytes, with anything that is not well-formed UTF-8 becoming
 * U+FFFD — which is why `sql.keal` answers the type as well as the value, and
 * why a program storing binary should read the type first. */
static inline char *kbs_column_text(int64_t s, int64_t i) {
    if (!s) return kb_text_from((const unsigned char *)"", 0);
    sqlite3_stmt *st = (sqlite3_stmt *)(intptr_t)s;
    const unsigned char *p = sqlite3_column_text(st, (int)i);
    int n = sqlite3_column_bytes(st, (int)i);
    if (!p || n < 0) return kb_text_from((const unsigned char *)"", 0);
    return kb_text_from(p, (int64_t)n);
}

/* The library's own version, for `keal doctor`-shaped questions. */
static inline char *kbs_version(void) {
    const char *v = sqlite3_libversion();
    return kb_text_from((const unsigned char *)v, (int64_t)strlen(v));
}

#endif /* KEALEB_KB_SQL_H */
