// Audit round 2 regression checks (Docs: Docs/sessions/52-link.md). Run: node src/auditcheck2.mjs
// Fake OBS / fake peers only; PINGUINO_NEVER_REAL_OBS blocks port 4455.
process.env.PINGUINO_NEVER_REAL_OBS = '1';
process.env.PINGUINO_MESH_TEST = '1';
import './testenv.mjs';
import { spawn } from 'node:child_process';
import http from 'node:http';
import crypto from 'node:crypto';
import os from 'node:os';
import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';
import { fileURLToPath } from 'node:url';

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'plink-audit2-'));
process.env.PINGUINO_DATA_DIR = tmp;
const { extractZip, writeZip } = await import('./pkg.mjs');
const { getData } = await import('./obs.mjs');
const { startFakeObs } = await import('./fakeobs.mjs');
const { createMesh } = await import('./mesh.mjs');
const cli = fileURLToPath(new URL('./cli.mjs', import.meta.url));
let bad = 0;
const check = (n, c, extra = '') => { console.log(`${c ? 'PASS' : 'FAIL'}  ${n}${c ? '' : '  ' + extra}`); if (!c) bad++; };
const sleep = ms => new Promise(r => setTimeout(r, ms));

// ---- server routes ----
const port = 17900 + Math.floor(Math.random() * 90), tok = 'core-audit2-token';
const child = spawn(process.execPath, [cli, 'serve'], { stdio: 'ignore', windowsHide: true, env: { ...process.env, PINGUINO_LINK_PORT: String(port), PINGUINO_API_TOKEN: tok, PINGUINO_DATA_DIR: path.join(tmp, 'srv') } });
const base = `http://127.0.0.1:${port}`;
for (let i = 0; i < 60; i++) { try { if ((await fetch(base + '/api/health')).ok) break; } catch {} await sleep(250); }
const call = async (method, p, body, headers = {}, raw) => {
  const r = await fetch(base + p, { method, headers: { ...(body !== undefined ? { 'content-type': 'application/json' } : {}), ...headers }, body: raw ?? (body === undefined ? undefined : JSON.stringify(body)) });
  return { status: r.status, json: await r.json().catch(() => ({})) };
};
for (const k of ['constructor', '__proto__', 'toString', 'hasOwnProperty']) {
  const r = await call('POST', '/api/mesh/heartbeat', {}, { 'x-link-peer': k });
  check(`peer id "${k}" with no token is refused`, r.status === 401, `status ${r.status}`);
}
check('peer macro route refuses prototype peer id', (await call('POST', '/api/mesh/macro', { name: 'brb' }, { 'x-link-peer': 'constructor' })).status === 401);
for (const body of ['null', '[]', '5', '"x"']) {
  const r = await call('POST', '/api/mesh/forget', undefined, { 'x-link-token': tok, 'content-type': 'application/json' }, body);
  const r2 = await call('POST', '/api/macros/set', undefined, { 'x-link-token': tok, 'content-type': 'application/json' }, body);
  check(`JSON body ${body} gives 4xx, not 500`, r.status < 500 && r2.status < 500, `${r.status}/${r2.status}`);
}
const nullMsg = await call('POST', '/api/mesh/msg', undefined, { 'x-link-peer': 'nobody', 'content-type': 'application/json' }, 'null');
check('null body on a peer route is a 4xx', nullMsg.status >= 400 && nullMsg.status < 500, String(nullMsg.status));
for (const n of ['constructor', '__proto__', 'toString']) {
  const r = await call('POST', `/api/macro/${n}`, undefined, { 'x-link-token': tok });
  check(`macro named ${n} is "unknown macro" (4xx), not a crash`, r.status >= 400 && r.status < 500, String(r.status));
}
const hostStatus = h => new Promise(res => { const q = http.request({ host: '127.0.0.1', port, path: '/api/health', headers: { host: h } }, r => { r.resume(); res(r.statusCode); }); q.on('error', () => res(0)); q.end(); });
check('Host "evil.example:abc" is refused', await hostStatus('evil.example:abc') === 421);
check('Host "evil.example" is refused', await hostStatus('evil.example') === 421);
check('Host "127.0.0.1:port" is allowed', await hostStatus(`127.0.0.1:${port}`) === 200);
check('server still alive', child.exitCode === null);
child.kill();

// ---- obs.mjs against a rogue server ----
function rogue(payload) {
  const s = http.createServer();
  s.on('upgrade', (req, sock) => {
    const accept = crypto.createHash('sha1').update(req.headers['sec-websocket-key'] + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest('base64');
    sock.write(`HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: ${accept}\r\n\r\n`);
    const b = Buffer.from(payload); sock.write(Buffer.concat([Buffer.from([0x81, b.length]), b])); sock.on('error', () => {});
  });
  return new Promise(r => s.listen(0, '127.0.0.1', () => r(s)));
}
for (const payload of ['not json at all', '{"op":0}', '{"op":7}']) {
  const s = await rogue(payload), p = s.address().port;
  const code = `import('${new URL('./obs.mjs', import.meta.url).href}').then(m => m.getData({host:'127.0.0.1',port:${p},password:'x'},['GetVersion'],1500)).then(()=>console.log('resolved'),e=>console.log('rejected')).then(()=>process.exit(0))`;
  const out = await new Promise(res => { const c = spawn(process.execPath, ['-e', code], { env: { ...process.env, PINGUINO_NEVER_REAL_OBS: '1' } }); let o = ''; c.stdout.on('data', d => o += d); c.on('exit', x => res(`${x}:${o.trim()}`)); });
  check(`obs client survives rogue server message ${JSON.stringify(payload)}`, out === '0:rejected', out);
  s.close();
}
const f = await startFakeObs('pw');
let rej = false; try { await getData({ host: '127.0.0.1', port: f.obsPort, password: 'pw' }, ['GetSceneList', 'NoSuchRequest'], 2000); } catch { rej = true; }
check('a failed OBS request rejects instead of returning empty data', rej);
f.close();

// ---- zip handling ----
const d1 = path.join(tmp, 'z1'); fs.mkdirSync(d1);
const zf = path.join(tmp, 'a.zip');
for (const name of ['a:b.txt', 'x/../../y.txt', '/abs.txt', 'C:\w.txt']) {
  fs.writeFileSync(zf, writeZip([{ name, data: Buffer.from('hi') }]));
  let threw = false; try { extractZip(zf, d1); } catch { threw = true; }
  check(`zip entry "${name}" rejected`, threw);
}
{ // zip bomb: 300 MB of zeros declared as 10 bytes
  const z = writeZip([{ name: 'bomb.bin', data: Buffer.alloc(300 * 1024 * 1024) }]);
  for (let i = 0; i + 4 <= z.length; i++) {
    if (z.readUInt32LE(i) === 0x04034b50) z.writeUInt32LE(10, i + 22);
    if (z.readUInt32LE(i) === 0x02014b50) z.writeUInt32LE(10, i + 24);
  }
  fs.writeFileSync(zf, z);
  const before = process.memoryUsage().rss; let threw = false;
  try { extractZip(zf, path.join(tmp, 'z2')); } catch { threw = true; }
  check('zip bomb (declared 10 bytes) rejected without inflating it', threw && !fs.existsSync(path.join(tmp, 'z2', 'bomb.bin')) && process.memoryUsage().rss - before < 150 * 1024 * 1024);
}


// ---- pairing with a hostile peer that returns a short token ----
const hostile = http.createServer((req, res) => { req.resume(); req.on('end', () => { res.writeHead(200, { 'content-type': 'application/json' }); res.end(JSON.stringify({ device: { id: 'hostile-device-1', name: 'x', os: 'w' }, token: '' })); }); });
await new Promise(r => hostile.listen(0, '127.0.0.1', r));
const mesh = createMesh({ port: 1, mesh: {} }, { port: 1 });
let refused = false; try { await mesh.join(`127.0.0.1:${hostile.address().port}`, '123456'); } catch { refused = true; }
check('pairing refuses a peer that hands back no/short token', refused && mesh.status().peers.length === 0);
hostile.close();

console.log(bad ? `${bad} check(s) FAILED` : 'All audit-2 checks passed');
try { fs.rmSync(tmp, { recursive: true, force: true }); } catch {}
process.exit(bad ? 1 : 0);
