// Regression tests for the 53 security review, batch 2: pairing hardening, unique peer names, redirects, capped bodies.
// Run: node src/auditcheck4.mjs   (loopback only, temp dirs, no OBS)
import './testenv.mjs';
import http from 'node:http';
import { spawn } from 'node:child_process';
import os from 'node:os';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { readCapped, jsonCapped } from './httpcap.mjs';

const cli = fileURLToPath(new URL('./cli.mjs', import.meta.url));
let bad = 0;
const check = (n, c, x = '') => { console.log(`${c ? 'PASS' : 'FAIL'}  ${n}${c ? '' : '  ' + x}`); if (!c) bad++; };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const until = async (fn, ms = 20000) => { const t = Date.now(); while (Date.now() - t < ms) { try { const v = await fn(); if (v) return v; } catch {} await sleep(300); } return null; };

// 1. capped body reads (a peer cannot make us buffer unlimited data, with or without Content-Length)
const srv = http.createServer((req, res) => {
  if (req.url === '/big') { res.writeHead(200); const t = setInterval(() => res.write(Buffer.alloc(65536, 65)), 1); res.on('close', () => clearInterval(t)); }
  else if (req.url === '/small') { res.writeHead(200, { 'content-type': 'application/json' }); res.end('{"a":1}'); }
  else if (req.url === '/lie') { res.writeHead(200, { 'content-length': '999999999' }); res.end('x'); }
  else if (req.url === '/redir') { hits.redir++; res.writeHead(307, { location: `http://127.0.0.1:${srv.address().port}/target` }); res.end(); }
  else if (req.url === '/target') { hits.target++; res.writeHead(200); res.end('{}'); }
  else { res.writeHead(404); res.end(); }
});
const hits = { redir: 0, target: 0 };
await new Promise(r => srv.listen(0, '127.0.0.1', r));
const sp = srv.address().port;
const f = p => fetch(`http://127.0.0.1:${sp}${p}`);
let e1 = ''; try { await readCapped(await f('/big'), 1_000_000); } catch (e) { e1 = e.message; }
check('endless chunked body is cut off at the cap', /larger than/.test(e1), e1);
check('small JSON is read', (await jsonCapped(await f('/small'))).a === 1);
let e2 = ''; try { await jsonCapped(await f('/lie'), 1000); } catch (e) { e2 = e.message; }
check('announced size over the cap is refused before reading', /larger than/.test(e2), e2);
let e3 = ''; try { await fetch(`http://127.0.0.1:${sp}/redir`, { redirect: 'error' }); } catch (e) { e3 = e.name || 'err'; }
check('redirect: error refuses to follow (target never hit)', hits.target === 0 && hits.redir === 1 && e3 !== '');

// 2. pairing on a real spawned hub
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'plink-a4-')); fs.mkdirSync(path.join(dir, 'link'), { recursive: true });
const port = 9100 + Math.floor(Math.random() * 90);
fs.writeFileSync(path.join(dir, 'link', 'config.json'), JSON.stringify({ role: 'hub', hub: 'x', port, token: 'module-token-4-module-token-0004', inbox: dir, obs: { host: '127.0.0.1', port: 1, password: 'x' }, macros: {}, claude: { enabled: false, cli: 'claude' } }));
const child = spawn(process.execPath, [cli, 'serve'], { stdio: 'ignore', windowsHide: true, env: { ...process.env, PINGUINO_LINK_PORT: String(port), PINGUINO_API_TOKEN: 'core-4', PINGUINO_DATA_DIR: dir, PINGUINO_MESH_TEST: '1', PINGUINO_CORE_URL: 'http://127.0.0.1:1', PINGUINO_LITE_DIR: path.join(dir, 'lite') } });
const base = `http://127.0.0.1:${port}`;
const call = async (method, p, body) => { const r = await fetch(base + p, { method, headers: { 'x-link-token': 'core-4', 'content-type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) }); return { status: r.status, json: await r.json().catch(() => ({})) }; };
const pair = (code, over = {}) => fetch(base + '/api/mesh/pair/request', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ code, port: 1234, token: 'a'.repeat(48), device: { id: 'device-' + Math.random().toString(16).slice(2, 12), name: 'other', os: 'win32' }, ...over }) }).then(async r => ({ status: r.status, json: await r.json().catch(() => ({})) }));
try {
  await until(async () => (await fetch(base + '/api/health')).ok);
  await call('POST', '/api/settings', { changes: { 'device.name': 'hubpc' } });

  // junk while nothing is open is refused and costs nothing against the limiter
  let junk = []; for (let i = 0; i < 14; i++) junk.push((await pair('000000')).status);
  check('requests while no code is open get 403 (not counted)', junk.every(s => s === 403), junk.join(','));
  const c1 = (await call('POST', '/api/mesh/pair/start', {})).json.code;
  const ok0 = await pair(c1 === '123456' ? '654321' : '123456');
  check('after junk, a code opened now still works normally (wrong code -> 403, not 429)', ok0.status === 403, JSON.stringify(ok0));
  // bad token format
  const badTok = await pair(c1, { token: 'z'.repeat(40) });
  check('non-hex pairing token is refused (400)', badTok.status === 400, JSON.stringify(badTok));
  // three wrong tries from one address block that address but leave the code alive
  const wrongs = []; for (let i = 0; i < 3; i++) wrongs.push((await pair(c1 === '111111' ? '222222' : '111111')).status);
  const after = await pair(c1);
  check('3 wrong codes block that address (429), even with the right code', after.status === 429, wrongs.join(',') + ' ' + JSON.stringify(after));

  // a fresh code: single use, one requester at a time, unique names, "replaces" flag
  const c2 = (await call('POST', '/api/mesh/pair/start', {})).json.code;
  // (the blocked address list belongs to the old code; a new code starts clean)
  const devId = 'device-same-id-1';
  const first = pair(c2, { device: { id: devId, name: 'hubpc', os: 'win32' } });
  const pend = await until(async () => (await call('GET', '/api/mesh/status')).json.pending?.[0]);
  check('a pending request is listed', !!pend && pend.replaces === false, JSON.stringify(pend));
  const second = await pair(c2);
  check('a second requester with the same code is refused while one is pending (409)', second.status === 409, JSON.stringify(second));
  await call('POST', '/api/mesh/pair/approve', { id: pend.id, allow: true });
  const r1 = await first;
  check('first requester is paired', r1.status === 200 && /^[0-9a-f]{32,}$/.test(r1.json.token || ''), JSON.stringify(r1));
  const third = await pair(c2);
  check('the code is single use (403 afterwards)', third.status === 403, JSON.stringify(third));
  const st = (await call('GET', '/api/mesh/status')).json;
  check('a peer cannot take this device\'s own name', st.peers.length === 1 && st.peers[0].name.toLowerCase() !== 'hubpc', JSON.stringify(st.peers.map(p => p.name)));

  // denied pairing also burns the code; re-pairing an existing id shows "replaces"
  const c3 = (await call('POST', '/api/mesh/pair/start', {})).json.code;
  const again = pair(c3, { device: { id: devId, name: 'impostor', os: 'win32' } });
  const pend2 = await until(async () => (await call('GET', '/api/mesh/status')).json.pending?.[0]);
  check('pending request flags that it would replace an existing peer', pend2?.replaces === true, JSON.stringify(pend2));
  await call('POST', '/api/mesh/pair/approve', { id: pend2.id, allow: false });
  check('denied request is refused', (await again).status === 403);
  check('and the code is gone after the denial', (await pair(c3)).status === 403);
} finally { child.kill(); srv.close(); await sleep(300); try { fs.rmSync(dir, { recursive: true, force: true }); } catch {} }
console.log(bad ? `\n${bad} check(s) FAILED` : '\nAll audit-4 batch-2 checks passed');
process.exit(bad ? 1 : 0);
