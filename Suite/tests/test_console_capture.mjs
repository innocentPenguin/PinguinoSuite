// node --test: console-capture.js dedupe, rate limit, redaction, originals still called
import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { create, redact } = require('../../App/src/console-capture.js');

function fakeWin() {
  const calls = [], listeners = {};
  return {
    calls, listeners,
    console: { error: (...a) => calls.push(['error', ...a]), warn: (...a) => calls.push(['warn', ...a]) },
    addEventListener: (n, f) => { listeners[n] = f; },
  };
}
function setup() {
  let t = 0; const sent = [];
  const c = create({ send: (b) => { sent.push(b); return Promise.resolve(); }, now: () => t });
  return { c, sent, tick: (ms) => { t += ms; } };
}

test('originals are still called and the entry is queued', () => {
  const { c, sent } = setup(); const w = fakeWin();
  c.attach(w, 'shell');
  w.console.error('boom', 5);
  assert.deepEqual(w.calls[0], ['error', 'boom', 5]);
  c.flush();
  assert.equal(sent[0][0].msg, 'boom 5');
  assert.equal(sent[0][0].level, 'error');
});

test('same message once per 10 s with a count', () => {
  const { c, sent, tick } = setup();
  for (let i = 0; i < 5; i++) c.record('error', 'same');
  tick(11000); c.record('error', 'same');
  c.flush();
  assert.equal(sent[0].length, 2);
  assert.equal(sent[0][0].n, 5);
  assert.equal(sent[0][1].n, 1);
});

test('200 entries per session', () => {
  const { c } = setup();
  for (let i = 0; i < 500; i++) c.record('error', 'unique ' + i);
  assert.equal(c.stats().total, 200);
});

test('redaction: tokens, query strings, long text', () => {
  assert.ok(!/abcdef/.test(redact('GET http://127.0.0.1:8765/api/x?token=abcdef123456 failed')));
  assert.ok(!/zzzzzzzzzz/.test(redact('Authorization: Bearer zzzzzzzzzzzz')));
  assert.ok(!/ABCDEFGHIJ/.test(redact('k ' + 'ABCDEFGHIJ'.repeat(5))));
  assert.ok(redact('x '.repeat(500)).length <= 201);
  assert.ok(redact('http://h/api/x?a=1').includes('/api/x'));
});

test('error event and unhandled rejection are recorded', () => {
  const { c, sent } = setup(); const w = fakeWin();
  c.attach(w, 'shell');
  w.listeners.error({ message: 'ReferenceError: x', filename: 'http://h/app.js?v=3', lineno: 7, colno: 2 });
  w.listeners.unhandledrejection({ reason: new Error('nope') });
  c.flush();
  assert.equal(sent[0][0].src, 'app.js:7:2');
  assert.match(sent[0][1].msg, /Unhandled rejection: Error: nope/);
});

test('a failing send never throws', () => {
  const c = create({ send: () => { throw new Error('down'); }, now: () => 0 });
  c.record('error', 'x');
  assert.doesNotThrow(() => c.flush());
});

test('suppressed repeats after a flush are counted in the next entry', () => {
  const { c, sent, tick } = setup();
  c.record('error', 'again'); c.flush();
  c.record('error', 'again'); c.record('error', 'again');
  tick(11000); c.record('error', 'again'); c.flush();
  assert.equal(sent[1][0].n, 3);
});
