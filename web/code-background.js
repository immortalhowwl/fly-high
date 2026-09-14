/* Decorative source texture only — not a feed or simulation output. */
(function (root) {
  'use strict';
  function createCodeBackground(win, doc) {
    if (doc.getElementById('code-background')) return null;
    const canvas = doc.createElement('canvas');
    const ctx = canvas.getContext('2d');
    if (!ctx) return null;
    canvas.id = 'code-background';
    canvas.setAttribute('aria-hidden', 'true');
    canvas.setAttribute('role', 'presentation');
    canvas.style.pointerEvents = 'none';
    doc.body.prepend(canvas);
    const media = win.matchMedia('(prefers-reduced-motion: reduce)');
    const snippets = [
      'const path = nodes.map(node => node.position);  // source texture',
      'function trace(branch) { return branch.children.map(trace); }',
      'export const shape = { edges, vertices, origin };',
      'const next = points.filter(point => point.visible);',
      'for (const layer of layers) { draw(layer.geometry); }',
      'import { vector, normalize } from "geometry";',
      'return segments.map(segment => transform(segment, basis));',
      'const mesh = connect(vertices);  /* decorative source */'
    ];
    const tileWidth = 960, lineHeight = 14, frameInterval = 1000 / 24;
    let width, height, rows = [], raf = null, last = null, elapsed = 0, destroyed = false;
    function render() {
      ctx.clearRect(0, 0, width, height);
      rows.forEach((row, i) => {
        const x = (row.phase + elapsed * row.speed) % tileWidth;
        for (let left = x - tileWidth; left < width; left += tileWidth) {
          ctx.drawImage(row.tile, left, i * lineHeight, tileWidth, lineHeight);
        }
      });
    }
    function resize() {
      width = win.innerWidth; height = win.innerHeight;
      const dpr = Math.min(win.devicePixelRatio || 1, 1.5);
      canvas.width = Math.ceil(width * dpr); canvas.height = Math.ceil(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      rows = Array.from({ length: Math.ceil(height / lineHeight) }, (_, i) => {
        const tile = doc.createElement('canvas');
        tile.width = tileWidth * dpr; tile.height = Math.ceil(lineHeight * dpr);
        const ink = tile.getContext('2d');
        ink.setTransform(dpr, 0, 0, dpr, 0, 0);
        ink.font = '10px "Courier New", monospace';
        ink.fillStyle = i % 3 === 0 ? '#b9bd68' : '#858b4f';
        ink.textBaseline = 'top';
        const text = snippets[i % snippets.length] + '    ' + snippets[(i + 3) % snippets.length] + '    ';
        ink.fillText(text.repeat(2), 0, 2);
        return { tile, phase: (i * 137) % tileWidth, speed: 9 + (i % 5) * 2 };
      });
      render();
    }
    function frame(now) {
      raf = null;
      if (destroyed || doc.hidden || media.matches) return;
      if (last === null) last = now;
      const delta = now - last;
      if (delta >= frameInterval) {
        elapsed += Math.min(delta, 150) / 1000;
        last = now;
        render();
      }
      raf = win.requestAnimationFrame(frame);
    }
    function sync() {
      if (raf !== null) win.cancelAnimationFrame(raf);
      raf = null; last = null;
      if (!destroyed && !doc.hidden && !media.matches) raf = win.requestAnimationFrame(frame);
      else if (!doc.hidden) render();
    }
    win.addEventListener('resize', resize);
    doc.addEventListener('visibilitychange', sync);
    if (media.addEventListener) media.addEventListener('change', sync);
    else media.addListener(sync);
    resize(); sync();
    return { destroy() {
      destroyed = true;
      if (raf !== null) win.cancelAnimationFrame(raf);
      win.removeEventListener('resize', resize);
      doc.removeEventListener('visibilitychange', sync);
      if (media.removeEventListener) media.removeEventListener('change', sync);
      else media.removeListener(sync);
      canvas.remove();
    } };
  }
  if (typeof module === 'object' && module.exports) module.exports = { createCodeBackground };
  else if (root.document) createCodeBackground(root, root.document);
})(typeof window !== 'undefined' ? window : globalThis);
