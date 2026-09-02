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

const port = 8891;
const server = spawn('build/counter', [], { stdio: ['ignore', 'pipe', 'pipe'], env: { ...process.env } });
server.stdout.on('data', () => {});
server.stderr.on('data', (d) => process.stderr.write(d));
process.on('exit', () => server.kill());

async function main() {
  await sleep(700);
  const page = await (await fetch(`http://127.0.0.1:8080/`)).text();

  const session = /window\.KB_SESSION="([0-9a-f]+)"/.exec(page);
  ok(session !== null, 'the page names a session');
  if (!session) return;

  const mount = /<div id="kb-root" class="kb-page">(.*)<\/div>\n<script>/s.exec(page);
  ok(mount !== null, 'the page has a mount point');
  if (!mount) return;

  const root = new DomNode(1, 'div');
  root.setAttribute('id', 'kb-root');
  for (const c of parse(mount[1]).childNodes) root.appendChild(c);

  // The document and window the client script expects, and nothing more.
  const document = {
    getElementById: (id) => (id === 'kb-root' ? root : null),
    createElement: (name) => {
      const el = new DomNode(1, name);
      if (name === 'template') {
        el.content = { get firstChild() { return el._parsed?.childNodes[0] ?? null; } };
        Object.defineProperty(el, 'innerHTML', {
          set(html) { el._parsed = parse(html); },
        });
      }
      return el;
    },
    body: new DomNode(1, 'body'),
  };
  const window = { KB_SESSION: session[1], addEventListener() {} };
  const location = { protocol: 'http:', host: `127.0.0.1:8080`, reload() { fail.push('the client reloaded'); } };

  const source = clientSource();
  ok(source.length > 500, 'the client script is served from the framework');
  const run = new Function('document', 'window', 'location', 'WebSocket', 'setTimeout',
                           'JSON', 'FormData', 'Math', source);
  const sent = [];
  class Socket {
    constructor(url) {
      this.url = url;
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
  run(document, window, location, Socket, setTimeout, JSON, FormData, Math);

  await sleep(400);
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

  // Changing the step rewrites two labels and moves a `selected` attribute —
  // four patches, of three different kinds, in one round trip.
  const chooser = root.find((n) => n.nodeName === 'select')[0];
  chooser.value = '5';
  root.dispatch('change', chooser);
  await sleep(250);
  same(buttons[1].textContent, '+5', 'the step is on the button');
  same(root.find((n) => n.nodeName === 'option' && n.getAttribute('selected'))[0].getAttribute('value'),
       '5', 'and the option that is chosen says so');

  // Crossing nine grows a paragraph that was not in the tree at all: an empty
  // placeholder replaced by a real node, which is the `r` patch.
  const before = root.find((n) => n.nodeName === 'p').length;
  root.dispatch('click', buttons[1]);
  root.dispatch('click', buttons[1]);
  await sleep(300);
  same(heading(), 'Clicked 12 times', 'two steps of five');
  same(root.find((n) => n.nodeName === 'p').length, before + 1,
       'and the paragraph that only shows past nine appeared');

  same(sent.length, 7, 'seven events went out, one per thing done');
}

function clientSource() {
  const file = readFileSync(new URL('../src/live.keal', import.meta.url), 'utf8');
  const at = file.indexOf('public val clientScript: String = """');
  const from = file.indexOf('\n', at) + 1;
  const to = file.indexOf('\n"""', from);
  return file.slice(from, to);
}

try {
  await main();
} catch (e) {
  fail.push(`threw: ${e.stack}`);
}
server.kill();

if (fail.length) {
  for (const f of fail) console.error(`  ✗ ${f}`);
  console.log(`${fail.length} of ${checks} checks failed`);
  process.exit(1);
}
console.log(`${checks} checks passed`);
