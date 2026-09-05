// tests/client.mjs — the client, against a real server, in a DOM small enough
// to read.
//
//     node tests/client.mjs        (tools/test.sh runs it when node is here)
//
// The client script is 130 lines of JavaScript and it is the only part of
// kealeb that does not run under `keal`. Leaving it unchecked would mean the
// framework's promise — you write no JavaScript — rests on the one file
// nothing tests. So: build the counter example, start it, load the page the
// server actually sends, run the script the server actually serves, and click
// a button. Everything below the fold is a DOM with the eleven methods that
// script uses and not a twelfth.
//
// What this catches is the whole round trip: the paths the server assigns, the
// six patch operations, the event delegation, the value extraction, and the
// framing at both ends. What it does not catch is anything about how a real
// browser lays the result out, which is what eyes are for.

import { spawn } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { setTimeout as sleep } from 'node:timers/promises';

let checks = 0;
const fail = [];
function ok(cond, what) {
  checks++;
  if (!cond) fail.push(what);
}
function same(got, want, what) {
  checks++;
  if (got !== want) fail.push(`${what}: expected \`${want}\`, got \`${got}\``);
}

// ------------------------------------------------------------------ the DOM

const VOID = new Set(['area', 'base', 'br', 'col', 'embed', 'hr', 'img',
                      'input', 'link', 'meta', 'source', 'track', 'wbr']);

class DomNode {
  constructor(type, name) {
    this.nodeType = type;              // 1 element, 3 text
    this.nodeName = name;
    this.childNodes = [];
    this.parentNode = null;
    this.attrs = new Map();
    this.nodeValue = '';
    this.listeners = new Map();
  }
  get type() { return this.attrs.get('type'); }
  get value() { return this._value !== undefined ? this._value : (this.attrs.get('value') ?? ''); }
  set value(v) { this._value = v; }
  get textContent() {
    if (this.nodeType === 3) return this.nodeValue;
    if (this.nodeType === 8) return '';
    return this.childNodes.map((c) => c.textContent).join('');
  }
  getAttribute(n) { return this.attrs.has(n) ? this.attrs.get(n) : null; }
  setAttribute(n, v) { this.attrs.set(n, String(v)); }
  removeAttribute(n) { this.attrs.delete(n); }
  insertBefore(child, ref) {
    const at = ref ? this.childNodes.indexOf(ref) : this.childNodes.length;
    this.childNodes.splice(at < 0 ? this.childNodes.length : at, 0, child);
    child.parentNode = this;
    return child;
  }
  appendChild(child) { return this.insertBefore(child, null); }
  removeChild(child) {
    const at = this.childNodes.indexOf(child);
    if (at >= 0) this.childNodes.splice(at, 1);
    child.parentNode = null;
    return child;
  }
  replaceChild(now, old) {
    const at = this.childNodes.indexOf(old);
    if (at < 0) return old;
    this.childNodes[at] = now;
    now.parentNode = this;
    old.parentNode = null;
    return old;
  }
  closest(selector) {
    const name = selector.slice(1, -1);          // only `[data-kb]` is used
    let n = this;
    while (n) {
      if (n.nodeType === 1 && n.attrs.has(name)) return n;
      n = n.parentNode;
    }
    return null;
  }
  addEventListener(name, fn) {
    if (!this.listeners.has(name)) this.listeners.set(name, []);
    this.listeners.get(name).push(fn);
  }
  // Only the capture phase matters here: the client listens on the root.
  dispatch(name, target) {
    const event = { target, key: undefined, preventDefault() {} };
    for (const fn of this.listeners.get(name) ?? []) fn(event);
  }
  html() {
    if (this.nodeType === 3) return escape(this.nodeValue);
    if (this.nodeType === 8) return `<!--${this.nodeValue}-->`;
    const attrs = [...this.attrs].map(([k, v]) => ` ${k}="${escapeAttr(v)}"`).join('');
    if (VOID.has(this.nodeName)) return `<${this.nodeName}${attrs}>`;
    return `<${this.nodeName}${attrs}>${this.childNodes.map((c) => c.html()).join('')}</${this.nodeName}>`;
  }
  find(pred, out = []) {
    if (pred(this)) out.push(this);
    for (const c of this.childNodes) c.find(pred, out);
    return out;
  }
}

const escape = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const escapeAttr = (s) => escape(s).replace(/"/g, '&quot;').replace(/'/g, '&#39;');
const unescape = (s) => s.replace(/&lt;/g, '<').replace(/&gt;/g, '>')
  .replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, '&');

// A parser for the markup kealeb emits, and nothing else: tags, double-quoted
// attributes, text, void elements. It is not an HTML parser and must never be
// asked to be one — if it ever disagrees with a browser, the fix is to render
// markup a browser and this both read the same way.
function parse(html) {
  const root = new DomNode(1, '#fragment');
  let at = root;
  let i = 0;
  while (i < html.length) {
    const lt = html.indexOf('<', i);
    if (lt < 0) { pushText(at, html.slice(i)); break; }
    if (lt > i) pushText(at, html.slice(i, lt));
    const gt = html.indexOf('>', lt);
    if (gt < 0) throw new Error('unterminated tag');
    const inner = html.slice(lt + 1, gt);
    if (inner.startsWith('!--')) {
      const c = new DomNode(8, '#comment');
      c.nodeValue = inner.slice(3, -2);
      at.appendChild(c);
    } else if (inner.startsWith('/')) {
      at = at.parentNode ?? root;
    } else {
      const space = inner.search(/\s/);
      const name = (space < 0 ? inner : inner.slice(0, space)).toLowerCase();
      const el = new DomNode(1, name);
      if (space >= 0) {
        for (const m of inner.slice(space).matchAll(/([a-zA-Z0-9:_-]+)="([^"]*)"/g)) {
          el.setAttribute(m[1], unescape(m[2]));
        }
      }
      at.appendChild(el);
      if (!VOID.has(name)) at = el;
    }
    i = gt + 1;
  }
  return root;
}

function pushText(at, text) {
  if (!text) return;
  const t = new DomNode(3, '#text');
  t.nodeValue = unescape(text);
  at.appendChild(t);
}

// --------------------------------------------------------------- the harness

// Port 0, and the server says which one it got. Asking for a fixed port makes
// this test fail — or worse, quietly talk to something else — whenever
// anything holds it, including a previous run of itself that outlived its
// kill. Reading the port out of the line the server prints is exact: there is
// no window between choosing it and binding it.
const running = [];
process.on('exit', () => running.forEach((p) => p.kill()));

// An error this file raised on purpose, whose message is the whole story.
function expected(message) {
  const e = new Error(message);
  e.expected = true;
  return e;
}

/// Start one of the examples on a port it chooses, and wait until it says so.
function start(name, within = 8000) {
  const server = spawn(`build/${name}`, ['0'], { stdio: ['ignore', 'pipe', 'pipe'] });
  server.stderr.on('data', (d) => process.stderr.write(d));
  running.push(server);
  return new Promise((resolve, reject) => {
    let seen = '';
    const giveUp = setTimeout(() => {
      reject(expected(
        `the ${name} example never said it was listening, within ${within}ms.\n` +
        `    What it printed instead: ${seen ? JSON.stringify(seen) : '(nothing at all)'}\n` +
        `    Run it by hand to see why: tools/build.sh examples/${name}.keal && build/${name} 0`));
    }, within);
    server.stdout.on('data', (d) => {
      seen += String(d);
      const at = /listening on http:\/\/[^:]+:(\d+)/.exec(seen);
      if (at) {
        clearTimeout(giveUp);
        resolve({ server, port: Number(at[1]) });
      }
    });
    server.on('error', (e) => {
      clearTimeout(giveUp);
      reject(expected(
        `build/${name} could not be started: ${e.code === 'ENOENT' ? 'it is not there' : e.message}.\n` +
        `    tools/test.sh builds the examples this file drives; build it by hand with\n` +
        `    tools/build.sh examples/${name}.keal${name === 'notes' ? ' -lsqlite3' : ''}`));
    });
    server.on('exit', (code) => {
      clearTimeout(giveUp);
      reject(expected(
        `the ${name} example exited with status ${code} before it said it was listening.\n` +
        `    Run it by hand to see why: tools/build.sh examples/${name}.keal && build/${name} 0`));
    });
  });
}

/// Load a live page and run the real client script against it, in a DOM small
/// enough to read. Answers the mount point and what the client sent.
async function live(name, port) {
  const page = await (await fetch(`http://127.0.0.1:${port}/`)).text();
  const session = /data-kb-session="([0-9a-f]+)"/.exec(page);
  if (!session) throw expected(`${name} served a page with no session id`);
  const mount = /<div id="kb-root" class="kb-page" data-kb-session="[0-9a-f]+">(.*)<\/div>\n<script/s.exec(page);
  if (!mount) throw expected(`${name} served a page with no mount point`);

  const root = new DomNode(1, 'div');
  root.setAttribute('id', 'kb-root');
  // The session id lives on the mount point rather than in an inline script,
  // so the harness must put it where the client will look for it.
  root.setAttribute('data-kb-session', session[1]);
  for (const c of parse(mount[1]).childNodes) root.appendChild(c);

  const document = {
    getElementById: (id) => (id === 'kb-root' ? root : null),
    createElement: (tag) => {
      const el = new DomNode(1, tag);
      if (tag === 'template') {
        el.content = { get firstChild() { return el._parsed?.childNodes[0] ?? null; } };
        Object.defineProperty(el, 'innerHTML', { set(html) { el._parsed = parse(html); } });
      }
      return el;
    },
    body: new DomNode(1, 'body'),
  };
  const window = { addEventListener() {} };
  const location = {
    protocol: 'http:', host: `127.0.0.1:${port}`,
    reload() { fail.push(`the client reloaded on ${name}`); },
  };
  const sent = [];
  class Socket {
    constructor(url) {
      this.readyState = 0;
      this.real = new globalThis.WebSocket(url);
      this.real.onopen = () => { this.readyState = 1; this.onopen?.(); };
      this.real.onmessage = (e) => this.onmessage?.({ data: e.data });
      this.real.onclose = () => { this.readyState = 3; this.onclose?.(); };
      this.real.onerror = () => this.onerror?.();
    }
    send(text) { sent.push(text); this.real.send(text); }
    close() { this.real.close(); }
  }
  const run = new Function('document', 'window', 'location', 'WebSocket', 'setTimeout',
                           'JSON', 'FormData', 'Math', clientSource());
  run(document, window, location, Socket, setTimeout, JSON, FormData, Math);
  await sleep(400);
  return { root, sent };
}

async function main() {
  await stopping();
  await counting();
  // The notes example is the one with a keyed list, and it keeps its notes in
  // SQLite — so on a machine with no library to link, that half is skipped and
  // says so rather than failing at a missing binary.
  if (process.env.KB_NO_SQLITE === '1') {
    console.log('(the keyed-list checks want the notes example, which wants sqlite3 — skipped)');
    return;
  }
  await moving();
}

// ------------------------------------------------------------- stopping

// A server told to stop must stop, and must say nothing twice on the way.
//
// The second half is not decoration. Keal calls a `proc main` by itself once
// the top level has run, so an example that both declares one and calls it
// runs the whole program twice — which is invisible while the first run blocks
// in the loop for ever, and becomes visible the moment the loop can end. That
// is exactly what graceful shutdown made possible, and exactly how it was
// found. Counting the "listening" lines is the check that keeps it found.
async function stopping() {
  const { server, port } = await start('counter');
  let printed = '';
  server.stdout.on('data', (d) => { printed += String(d); });
  await (await fetch(`http://127.0.0.1:${port}/`)).text();

  const ended = new Promise((resolve) => server.on('exit', (code, signal) => resolve({ code, signal })));
  server.kill('SIGTERM');
  const stopped = await Promise.race([ended, sleep(3000).then(() => null)]);

  ok(stopped !== null, 'a server told to stop stops, rather than having to be killed');
  if (stopped) same(String(stopped.code), '0', 'and exits saying nothing went wrong');
  same(String((printed.match(/listening on/g) ?? []).length), '0',
       'and started exactly once — a second "listening" means the program ran twice');
}

// ------------------------------------------------------- the counter page

async function counting() {
  const { port } = await start('counter');
  const { root, sent } = await live('counter', port);

  ok(sent.length === 0, 'the client says nothing until something happens');

  const heading = () => root.find((n) => n.nodeName === 'h1')[0].textContent;
  same(heading(), 'Clicked 0 times', 'the page arrives at zero');

  const buttons = root.find((n) => n.nodeName === 'button');
  same(buttons.length, 3, 'three buttons');
  const plus = buttons[1];
  same(plus.getAttribute('data-kb'), '0.2.0.1', 'and the middle one is where its path says');

  root.dispatch('click', plus);
  await sleep(250);
  same(heading(), 'Clicked 1 times', 'a click reaches the server and the answer reaches the page');

  root.dispatch('click', plus);
  root.dispatch('click', plus);
  await sleep(300);
  same(heading(), 'Clicked 3 times', 'and again, twice');

  root.dispatch('click', buttons[0]);
  await sleep(250);
  same(heading(), 'Clicked 2 times', 'the other button goes the other way');

  const chooser = root.find((n) => n.nodeName === 'select')[0];
  chooser.value = '5';
  root.dispatch('change', chooser);
  await sleep(250);
  same(buttons[1].textContent, '+5', 'the step is on the button');
  same(root.find((n) => n.nodeName === 'option' && n.getAttribute('selected'))[0].getAttribute('value'),
       '5', 'and the option that is chosen says so');

  const before = root.find((n) => n.nodeName === 'p').length;
  root.dispatch('click', buttons[1]);
  root.dispatch('click', buttons[1]);
  await sleep(300);
  same(heading(), 'Clicked 12 times', 'two steps of five');
  same(root.find((n) => n.nodeName === 'p').length, before + 1,
       'and the paragraph that only shows past nine appeared');

  same(sent.length, 7, 'seven events went out, one per thing done');
}

// --------------------------------------------- a keyed list, and the move

// What keys are for, checked the only way that means anything: the row that
// moved must be the *same DOM node* afterwards. A diff that rewrote it would
// pass every check about text and fail this one — and in a browser that
// difference is whether the caret, the focus and the scroll position stay with
// the thing they belonged to or are silently handed to another row.
async function moving() {
  const { port } = await start('notes');
  const { root } = await live('notes', port);

  const textField = () => root.find((n) => n.nodeName === 'input' &&
                                           n.getAttribute('type') === 'text')[0];
  const addButton = () => root.find((n) => n.nodeName === 'button' &&
                                           n.textContent === 'Add')[0];
  ok(!!textField() && !!addButton(), 'the notes page has a field and an Add button');
  if (!textField() || !addButton()) return;

  const noteRows = () => root
    .find((n) => n.nodeType === 1 && n.getAttribute('class') === 'kb-row')
    .filter((n) => n.find((c) => c.nodeName === 'input' &&
                                 c.getAttribute('type') === 'checkbox').length > 0);
  const labels = () => noteRows().map((r) => r.find((c) => c.nodeName === 'span')[0]?.textContent ?? '');

  const add = async (what) => {
    const f = textField();
    f.value = what;
    root.dispatch('input', f);
    await sleep(150);
    root.dispatch('click', addButton());
    await sleep(250);
  };

  const started = noteRows().length;
  await add('alpha');
  await add('beta');
  same(noteRows().length, started + 2, 'two notes were added');
  ok(labels().includes('alpha') && labels().includes('beta'), 'and both are on the page');

  // Ticking one sends it below the others, because the query orders by
  // `done` — so this is a reorder, which is what the move patch exists for.
  const alphaRow = noteRows()[labels().indexOf('alpha')];
  const betaRow = noteRows()[labels().indexOf('beta')];
  const box = alphaRow.find((n) => n.nodeName === 'input' &&
                                   n.getAttribute('type') === 'checkbox')[0];
  box.checked = true;
  root.dispatch('change', box);
  await sleep(400);

  const after = labels();
  ok(after.indexOf('alpha') > after.indexOf('beta'),
     `ticking a note moved it below the others (${after.join(', ')})`);
  ok(noteRows().includes(alphaRow), 'and the row that moved is the same node, not a new one');
  ok(noteRows().includes(betaRow), 'as is the one it moved past');

  // Removing it takes that node away and leaves the other untouched.
  root.dispatch('click', alphaRow.find((n) => n.nodeName === 'button')[0]);
  await sleep(350);
  ok(!labels().includes('alpha'), 'removing a note takes it off the page');
  ok(noteRows().includes(betaRow), 'and leaves the other as the node it always was');

  // This example keeps a file, so put it back as it was found.
  while (labels().includes('beta')) {
    const row = noteRows()[labels().indexOf('beta')];
    root.dispatch('click', row.find((n) => n.nodeName === 'button')[0]);
    await sleep(250);
  }
}

function clientSource() {
  const file = readFileSync(new URL('../src/live.keal', import.meta.url), 'utf8');
  const at = file.indexOf('public val clientScript: String = """');
  const from = file.indexOf('\n', at) + 1;
  const to = file.indexOf('\n"""', from);
  return file.slice(from, to);
}

// A failure in the harness is not a failed check, and reporting it as one
// ("1 of 0 checks failed") tells the reader nothing about what went wrong.
// The errors raised above carry the whole explanation in their message; a
// stack trace from `node:internal/child_process` carries none of it, so the
// stack is printed only for the ones nobody wrote on purpose.
let broke = null;
try {
  await main();
} catch (e) {
  broke = e;
}
running.forEach((p) => p.kill());

if (broke) {
  console.log('could not run');
  console.error(`  ✗ ${broke.expected ? broke.message : broke.stack}`);
  process.exit(1);
}
if (fail.length) {
  for (const f of fail) console.error(`  ✗ ${f}`);
  console.log(`${fail.length} of ${checks} checks failed`);
  process.exit(1);
}
console.log(`${checks} checks passed`);
