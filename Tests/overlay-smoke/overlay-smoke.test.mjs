// node --test Tests/overlay-smoke/   (offline: a tiny local server stands in for the app; GET only)
import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { scanText, scanJson, assetsOf, apiPathsOf, run } from './overlay-smoke.mjs';

test('scanText ignores scripts/styles/comments, flags visible undefined/NaN/[object Object]/raw keys', () => {
  assert.deepEqual(scanText('<script>if(x===undefined)</script><style>.a{}</style><!-- NaN --><p>Hello</p>'), []);
  assert.equal(scanText('<p>Welcome undefined</p>').length, 1);
  assert.equal(scanText('<div>Score: NaN</div>').length, 1);
  assert.equal(scanText('<div>[object Object]</div>').length, 1);
  assert.equal(scanText('<b>@yt:ucfa15yqt-uwrayt_ctui0sa won</b>').length, 1);
  assert.deepEqual(scanText('<p>nothing: weird</p>'), []);
});

test('scanJson checks display fields only; ids may hold yt: keys', () => {
  assert.deepEqual(scanJson({ Username: 'yt:ucabc123', name: 'Tank' }), []);
  assert.equal(scanJson({ players: [{ name: 'yt:ucabc123' }] }).length, 1);
  assert.equal(scanJson({ label: 'undefined' }).length, 1);
  assert.equal(scanJson({ n: { text: '[object Object]' } }).length, 1);
  assert.equal(scanJson({ n: NaN }).length, 1);
});

test('assetsOf: tags and css url(), not inline script strings or external links', () => {
  const html = '<link href="a.css"><img src="images/x.png"><script src="o.js"></script><script>el.src=u; x.href=y</script><a href="#top">t</a><a href="https://e.com/">e</a><div style="background:url(\'img/b.png\')"></div>';
  assert.deepEqual(assetsOf(html).sort(), ['a.css', 'images/x.png', 'img/b.png', 'o.js']);
});

test('apiPathsOf: GET fetches only', () => {
  const html = "fetch('/api/state').then(); fetch(\"api/x\"); fetch('/api/do',{method:'POST'}); fetch('/api/q?a=1')";
  assert.deepEqual(apiPathsOf(html).sort(), ['/api/q', '/api/state', '/api/x']);
});

function server(routes) {
  const seen = [];
  const s = http.createServer((req, res) => { seen.push(req.method + ' ' + req.url); const r = routes[req.url.split('?')[0]]; if (!r) { res.statusCode = 404; return res.end(); } res.setHeader('content-type', r[0]); res.end(r[1]); });
  return new Promise(ok => s.listen(0, '127.0.0.1', () => ok({ s, seen, host: '127.0.0.1:' + s.address().port })));
}

test('run: a bad page, a missing asset and bad state JSON all fail; only GET is sent', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ovsmoke-'));
  fs.writeFileSync(path.join(dir, 'ok.html'), '<p>fine</p>');
  fs.writeFileSync(path.join(dir, 'chat.html'), '<p>Hi undefined</p><img src="gone.png"><script>fetch("/api/s")</script>');
  fs.writeFileSync(path.join(dir, 'state.html'), '<p>x</p><script>fetch("/api/s")</script>');
  const app = await server({
    '/ok.html': ['text/html', '<p>fine</p>'],
    '/chat.html': ['text/html', fs.readFileSync(path.join(dir, 'chat.html'), 'utf8')],
    '/state.html': ['text/html', fs.readFileSync(path.join(dir, 'state.html'), 'utf8')],
    '/api/s': ['application/json', '{"name":"yt:ucabc123"}'],
  });
  const res = await run({ host: app.host, multi: app.host, modules: [], overlayDir: dir, multiPaths: ['/ok.html'] });
  app.s.close(); fs.rmSync(dir, { recursive: true, force: true });
  assert.ok(app.seen.every(l => l.startsWith('GET ')), app.seen.join(','));
  const by = n => res.filter(r => r.page === n);
  assert.ok(by('host ok.html').every(r => r.ok));
  assert.ok(by('host chat.html').some(r => /visible text/.test(r.msg)) && by('host chat.html').some(r => /asset gone\.png/.test(r.msg)) && by('host chat.html').some(r => /state \/api\/s/.test(r.msg)), JSON.stringify(by('host chat.html')));
  assert.ok(by('host chat.html').some(r => /yt:ucabc123/.test(r.msg)));   // a state API shared by two pages is fetched and reported once
  assert.ok(by('host state.html').every(r => r.ok));
  assert.ok(by('multi /ok.html').every(r => r.ok));
});

test('run: unreachable port is a failure, not a pass', async () => {
  const res = await run({ host: '127.0.0.1:9', multi: '127.0.0.1:9', modules: ['127.0.0.1:9/'] });
  assert.ok(res.length > 0 && res.every(r => !r.ok));
});
