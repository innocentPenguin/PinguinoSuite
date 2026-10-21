// Mesh self-check: two Link instances on this PC pair, exchange messages, unpair. Run: node src/meshcheck.mjs
// Uses PINGUINO_MESH_TEST=1 (allows loopback peers) and fake cores; touches no real config, port 7777 or Suite process.
process.env.PINGUINO_NEVER_REAL_OBS = '1';   // tests must never reach the real OBS
import { spawn } from 'node:child_process';
import http from 'node:http';
import os from 'node:os';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const cli = fileURLToPath(new URL('./cli.mjs', import.meta.url));
const results = [];
const check = (name, ok) => { results.push(ok); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}`); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const until = async (fn, ms = 15000) => { const t = Date.now(); while (Date.now() - t < ms) { try { const v = await fn(); if (v) return v; } catch {} await sleep(300); } return null; };

function fakeCore() {
  const got = [];
  const srv = http.createServer((req, res) => {
    let b = ''; req.on('data', c => b += c);
    req.on('end', () => { got.push({ url: req.url, auth: req.headers.authorization, tok: req.headers['x-link-token'], body: JSON.parse(b || '{}') }); res.end('{"ok":true}'); });
  });
  return new Promise(r => srv.listen(0, '127.0.0.1', () => r({ srv, got, url: `http://127.0.0.1:${srv.address().port}` })));
}

async function node(name, port, coreUrl) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), `plink-${name}-`));
  const tok = `core-${name}`;
  const child = spawn(process.execPath, [cli, 'serve'], { stdio: 'ignore', windowsHide: true,
    env: { ...process.env, PINGUINO_LINK_PORT: String(port), PINGUINO_API_TOKEN: tok, PINGUINO_DATA_DIR: dir, PINGUINO_MESH_TEST: '1', PINGUINO_CORE_URL: coreUrl } });
  const base = `http://127.0.0.1:${port}`;
  const call = async (method, p, body, headers = {}) => {
    const r = await fetch(base + p, { method, signal: AbortSignal.timeout(100000), headers: { 'x-link-token': tok, ...(body !== undefined ? { 'content-type': 'application/json' } : {}), ...headers }, body: body === undefined ? undefined : JSON.stringify(body) });
    return { status: r.status, json: await r.json().catch(() => ({})) };
  };
  await until(async () => (await fetch(base + '/api/health')).ok);
  return { name, port, dir, tok, base, child, call };
}

const ca = await fakeCore(), cb = await fakeCore();
const pa = 7900 + Math.floor(Math.random() * 40), pb = pa + 50;
const A = await node('A', pa, ca.url), B = await node('B', pb, cb.url);
try {
  const noPair = await fetch(A.base + '/api/mesh/pair/request', { method: 'POST', headers: { 'content-type': 'application/json' }, body: '{}' });
  check('pair request without a pairing in progress = 403', noPair.status === 403);
  check('mesh status needs the token', (await fetch(A.base + '/api/mesh/status')).status === 401);

  const { json: code } = await A.call('POST', '/api/mesh/pair/start', {});
  check('pairing code is 6 digits', /^\d{6}$/.test(code.code));
  const wrong = await B.call('POST', '/api/mesh/pair/join', { addr: `127.0.0.1:${pa}`, code: '000000' === code.code ? '111111' : '000000' });
  check('wrong code rejected (403)', wrong.status === 403);

  const joining = B.call('POST', '/api/mesh/pair/join', { addr: `127.0.0.1:${pa}`, code: code.code });
  const pend = await until(async () => { const s = await A.call('GET', '/api/mesh/status'); return s.json.pending?.[0]; });
  check('request waits for approval on the other device', !!pend);
  check('pending request exposes no tokens', !JSON.stringify(pend).match(/[0-9a-f]{32}/));
  await A.call('POST', '/api/mesh/pair/approve', { id: pend.id, allow: true });
  const joined = await joining;
  check('join completes after approval', joined.status === 200 && joined.json.ok);

  const aOnline = await until(async () => (await A.call('GET', '/api/mesh/status')).json.peers.every(p => p.online) && (await A.call('GET', '/api/mesh/status')).json.peers.length === 1);
  const bOnline = await until(async () => (await B.call('GET', '/api/mesh/status')).json.peers.every(p => p.online) && (await B.call('GET', '/api/mesh/status')).json.peers.length === 1);
  check('both sides list the other as an online peer', !!aOnline && !!bOnline);
  check('pairing code is single use', (await A.call('GET', '/api/mesh/status')).json.pairing === null);
  check('/api/status lists paired peers', (await A.call('GET', '/api/status')).json.peers?.length === 1);
  const ps = (await A.call('GET', '/api/prestream')).json.items || [];
  check('prestream has one item per peer', ps.some(i => i.id.startsWith('peer-') && i.status === 'pass'));

  const hb = { type: 'device-hb', payload: { id: 'dev-a', name: 'A', priority: 100 } };
  const sent = await A.call('POST', '/api/peer/broadcast', hb, { authorization: `Bearer ${A.tok}` });
  check('broadcast reports 1 sent', sent.status === 200 && sent.json.sent === 1);
  const arrived = await until(() => cb.got.find(g => g.url === '/api/device/peer'));
  check('peer message reaches the other core, payload unchanged', arrived?.body.type === 'device-hb' && arrived.body.payload.priority === 100 && arrived.body.from);
  check('core call uses the Link module token', arrived?.auth === `Bearer ${B.tok}` && arrived?.tok === B.tok);

  const bad = await fetch(B.base + '/api/mesh/msg', { method: 'POST', headers: { 'content-type': 'application/json', 'x-link-peer': 'nobody-nobody', 'x-link-token': 'x'.repeat(48) }, body: JSON.stringify(hb) });
  check('message from unknown peer = 401', bad.status === 401);
  const peerId = (await B.call('GET', '/api/mesh/status')).json.peers[0].id;
  const bad2 = await fetch(B.base + '/api/mesh/msg', { method: 'POST', headers: { 'content-type': 'application/json', 'x-link-peer': (await A.call('GET', '/api/mesh/status')).json.self.id, 'x-link-token': 'wrong-token-wrong-token-wrong-token' }, body: JSON.stringify(hb) });
  check('message with wrong peer token = 401', bad2.status === 401);
  check('non-JSON body = 415', (await A.call('POST', '/api/peer/broadcast', undefined)).status === 415);

  await A.call('POST', '/api/mesh/unpair', { id: (await A.call('GET', '/api/mesh/status')).json.peers[0].id });
  const gone = await until(async () => (await B.call('GET', '/api/mesh/status')).json.peers.length === 0);
  check('unpair on one side removes it on the other', !!gone);
  check('broadcast with no peers sends 0', (await A.call('POST', '/api/peer/broadcast', hb)).json.sent === 0);
  void peerId;

  const logs = fs.readFileSync(path.join(A.dir, 'console', 'link.jsonl'), 'utf8');
  check('pairing events logged, no tokens in the log', logs.includes('"source":"pairing"') && !logs.includes(A.tok) && !/[0-9a-f]{48}/.test(logs));
} finally {
  for (const n of [A, B]) { n.child.kill(); try { fs.rmSync(n.dir, { recursive: true, force: true }); } catch {} }
  ca.srv.close(); cb.srv.close();
}
const bad = results.filter(r => !r).length;
console.log(bad ? `\n${bad} check(s) FAILED` : '\nAll mesh checks passed');
process.exit(bad ? 1 : 0);
