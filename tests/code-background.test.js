const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { createCodeBackground } = require('../web/code-background');
function fixture(reduced = false) {
  const pending = new Map(), events = {}, changes = {}, canvases = [];
  let id = 0, texts = 0;
  const media = { matches: reduced, addEventListener: (n, f) => changes[n] = f, removeEventListener: n => delete changes[n] };
  const doc = { hidden: false, body: { prepend(c) { this.canvas = c; } },
    getElementById: () => doc.body.canvas || null,
    addEventListener: (n, f) => events[n] = f, removeEventListener: n => delete events[n],
    createElement() {
      const calls = [];
      const ctx = { setTransform() {}, fillText() { texts++; }, clearRect() { calls.length = 0; }, drawImage(...args) { calls.push(args); } };
      const c = { style: {}, attrs: {}, calls, getContext: () => ctx, setAttribute(n, v) { this.attrs[n] = v; }, remove() { doc.body.canvas = null; } };
      canvases.push(c); return c;
    }
  };
  const win = { innerWidth: 800, innerHeight: 280, devicePixelRatio: 3, matchMedia: () => media,
    addEventListener: (n, f) => events[n] = f, removeEventListener: n => delete events[n],
    requestAnimationFrame: f => { pending.set(++id, f); return id; }, cancelAnimationFrame: n => pending.delete(n) };
  const api = createCodeBackground(win, doc);
  return { win, doc, media, events, changes, pending, canvases, api, texts: () => texts,
    step(t) { const callbacks = [...pending.values()]; pending.clear(); callbacks.forEach(f => f(t)); } };
}
test('cached horizontal rows move left to right, retain y; rendering throttled', () => {
  const f = fixture(); const c = f.doc.body.canvas;
  const before = c.calls.map(x => [...x]), texts = f.texts();
  f.step(0); f.step(20);
  assert.deepEqual(c.calls, before);
  f.step(50);
  assert.ok(c.calls[0][1] > before[0][1]);
  assert.equal(c.calls[0][2], before[0][2]);
  assert.equal(f.texts(), texts);
  assert.equal(c.width, 1200); // DPR is capped at 1.5.
});
test('reduced motion renders static texture and reacts to preference changes', () => {
  const f = fixture(true);
  assert.equal(f.pending.size, 0);
  assert.ok(f.doc.body.canvas.calls.length);
  f.media.matches = false; f.changes.change();
  assert.equal(f.pending.size, 1);
  f.media.matches = true; f.changes.change();
  assert.equal(f.pending.size, 0);
});
test('hidden tab pauses, resume has no time jump, resize rebuilds cache', () => {
  const f = fixture(); f.step(0); f.step(50);
  const before = f.doc.body.canvas.calls[0][1];
  f.doc.hidden = true; f.events.visibilitychange();
  assert.equal(f.pending.size, 0);
  f.doc.hidden = false; f.events.visibilitychange(); f.step(9000);
  assert.equal(f.doc.body.canvas.calls[0][1], before);
  f.win.innerWidth = 1000; f.events.resize();
  assert.equal(f.doc.body.canvas.width, 1500);
});
test('decoration is inaccessible, cannot intercept input, initializes once and cleans up', () => {
  const f = fixture(), c = f.doc.body.canvas;
  assert.equal(c.attrs['aria-hidden'], 'true');
  assert.equal(c.style.pointerEvents, 'none');
  assert.equal(c.attrs.tabindex, undefined);
  assert.equal(createCodeBackground(f.win, f.doc), null);
  assert.deepEqual(Object.keys(f.events).sort(), ['resize', 'visibilitychange']);
  f.api.destroy();
  assert.equal(f.pending.size, 0); assert.equal(f.doc.body.canvas, null);
  assert.equal(Object.keys(f.events).length, 0);
});
test('both pages include background; CSS preserves black opaque panels and background stacking', () => {
  for (const [html, css] of [['index.html', 'style.css'], ['research.html', 'research.css']]) {
    const read = name => fs.readFileSync(path.join(__dirname, '../web', name), 'utf8');
    assert.match(read(html), /src="\/code-background.js" defer/);
    assert.match(read(css), /body\{isolation:isolate\}/);
    assert.match(read(css), /z-index:-1;pointer-events:none/);
    assert.match(read(css), /--panel:#000000/);
  }
});
