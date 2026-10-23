// Two-instance pairing check: a hub and a client Link on loopback, temp data dirs, a FAKE OBS.
// Pair, change role, forward a macro, fetch an update, and confirm the x-link-peer fix holds.
// Run: node src/pairingcheck.mjs   (touches no real data, never reaches the real OBS)
import './testenv.mjs';
import { spawn } from 'node:child_process';
import os from 'node:os';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { startFakeObs } from './fakeobs.mjs';

const cli = fileURLToPath(new URL('./cli.mjs', import.meta.url));
const results = [];
const check = (name, ok, extra = '') => { results.push(ok); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${ok ? '' : '  ' + extra}`); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const until = async (fn, ms = 20000) => { const t = Date.now(); while (Date.now() - t < ms) { try { const v = await fn(); if (v) return v; } catch {} await sleep(300); } return null; };
const sha = b => crypto.createHash('sha256').update(b).digest('hex');

const { obs, obsPort, close } = await startFakeObs('pw-secret-1');
const macros = { brb: [{ type: 'SetCurrentProgramScene', data: { sceneName: 'BRB' } }], live: [{ type: 'SetCurrentProgramScene', data: { sceneName: 'Main' } }] };
const dirs = [];

async function node(name, port, role) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), `plink-pair-${name}-`));
  dirs.push(dir);
  fs.mkdirSync(path.join(dir, 'link'), { recursive: true });
  const lite = path.join(dir, 'lite');
  const cfg = { role, hub: 'hubpc', port, mesh: { shareUpdates: true, fetchUpdates: true }, token: `module-token-${name}-module-token-0003`, inbox: dir, obs: { host: '127.0.0.1', port: obsPort, password: 'pw-secret-1' }, macros, claude: { enabled: false, cli: 'claude' }, cooldown: { macroMs: 0, riskyMs: 0 } };
  fs.writeFileSync(path.join(dir, 'link', 'config.json'), JSON.stringify(cfg));
  const child = spawn(process.execPath, [cli, 'serve'], { stdio: 'ignore', windowsHide: true,
    env: { ...process.env, PINGUINO_LINK_PORT: String(port), PINGUINO_API_TOKEN: `core-${name}`, PINGUINO_DATA_DIR: dir, PINGUINO_MESH_TEST: '1', PINGUINO_CORE_URL: 'http://127.0.0.1:1', PINGUINO_LITE_DIR: lite, PINGUINO_LITE_VERSION: '0.1.0' } });
  const base = `http://127.0.0.1:${port}`;
  const call = async (method, p, body, headers = {}) => {
    const r = await fetch(base + p, { method, signal: AbortSignal.timeout(60000), headers: { 'x-link-token': `core-${name}`, ...(body !== undefined ? { 'content-type': 'application/json' } : {}), ...headers }, body: body === undefined ? undefined : JSON.stringify(body) });
    return { status: r.status, json: await r.json().catch(() => ({})) };
  };
  await until(async () => (await fetch(base + '/api/health')).ok);
  return { dir, lite, child, call, base };
}

const pa = 8800 + Math.floor(Math.random() * 40), pb = pa + 50;
const A = await node('A', pa, 'hub'), B = await node('B', pb, 'client');
try {
  await A.call('POST', '/api/settings', { changes: { 'device.name': 'hubpc' } });
  await B.call('POST', '/api/settings', { changes: { 'device.name': 'clientpc' } });

  // 1. pairing: wrong code first, then the right one
  const { json: code } = await A.call('POST', '/api/mesh/pair/start', {});
  const wrong = await B.call('POST', '/api/mesh/pair/join', { addr: `127.0.0.1:${pa}`, code: code.code === '000000' ? '111111' : '000000' });
  check('wrong pairing code is refused', wrong.status !== 200, JSON.stringify(wrong));
  const { json: code2 } = await A.call('POST', '/api/mesh/pair/start', {});
  const joining = B.call('POST', '/api/mesh/pair/join', { addr: `127.0.0.1:${pa}`, code: code2.code });
  const pend = await until(async () => (await A.call('GET', '/api/mesh/status')).json.pending?.[0]);
  check('hub sees a pending request that needs a click', !!pend);
  await A.call('POST', '/api/mesh/pair/approve', { id: pend?.id, allow: true });
  check('pairing completes after Allow', (await joining).status === 200);
  const online = await until(async () => { const s = (await B.call('GET', '/api/mesh/status')).json; return s.peers.length === 1 && s.peers[0].online; });
  check('client lists the hub as online', !!online);
  check('hub lists the client as a peer', (await A.call('GET', '/api/mesh/status')).json.peers.length === 1);

  // 2. macro forwarded from the client to the hub
  const brb = await B.call('POST', '/api/macro/brb');
  check('client presses brb, hub switches the fake OBS scene', brb.status === 200 && obs.scene === 'BRB', JSON.stringify(brb));

  // 3. role change on the client (needs the confirm flag) and back
  const noConfirm = await B.call('POST', '/api/settings', { changes: { role: 'hub' } });
  check('role change without confirmation is refused', noConfirm.status >= 400, JSON.stringify(noConfirm));
  const roleOk = await B.call('POST', '/api/settings', { changes: { role: 'hub' }, confirm_role: true });
  const st = (await B.call('GET', '/api/settings')).json;
  check('role change with confirmation is applied', roleOk.status === 200 && JSON.stringify(st).includes('"hub"'), JSON.stringify(roleOk));
  await B.call('POST', '/api/settings', { changes: { role: 'client' }, confirm_role: true });
  await until(async () => (await B.call('GET', '/api/mesh/status')).json.peers[0]?.online);
  check('client still presses a macro after switching back', (await B.call('POST', '/api/macro/live')).status === 200 && obs.scene === 'Main');

  // 4. update fetch: hub shares a hashed package, client pulls it on request
  const pk = path.join(A.lite, 'packages');
  fs.mkdirSync(pk, { recursive: true });
  const pkg = Buffer.from('PK-fake-package-bytes');
  fs.writeFileSync(path.join(pk, 'demo-1.0.0.zip'), pkg); fs.writeFileSync(path.join(pk, 'demo-1.0.0.zip.sha256'), sha(pkg));
  fs.mkdirSync(path.join(B.lite, 'requests'), { recursive: true });
  fs.writeFileSync(path.join(B.lite, 'requests', '1-check.json'), JSON.stringify({ schema: 1, action: 'check', id: null }));
  const fetched = path.join(B.lite, 'packages', 'demo-1.0.0.zip');
  const got = await until(() => fs.existsSync(fetched + '.sha256'), 20000);
  check('client fetched the hub package with a matching hash', !!got && sha(fs.readFileSync(fetched)) === sha(pkg));

  // 5. the x-link-peer fix: prototype names and empty tokens never authenticate
  const routes = ['/api/mesh/macro', '/api/mesh/updates/list', '/api/mesh/msg', '/api/mesh/forget'];
  let allBlocked = true, note = '';
  for (const id of ['constructor', '__proto__', 'toString', 'hasOwnProperty', '']) {
    for (const r of routes) for (const tok of [undefined, '', 'z'.repeat(40)]) {
      const h = { 'content-type': 'application/json', 'x-link-peer': id }; if (tok !== undefined) h['x-link-token'] = tok;
      const res = await fetch(A.base + r, { method: 'POST', headers: h, body: '{"name":"brb"}' });
      if (res.status !== 401) { allBlocked = false; note = `${id || '(empty)'} ${r} tok=${tok === undefined ? 'none' : tok.length} -> ${res.status}`; }
    }
  }
  check('prototype-name peers get 401 on every peer route', allBlocked, note);
  const scene = obs.scene;
  check('and the hub OBS was not touched by them', scene === 'Main');
  const noToken = await fetch(A.base + '/api/mesh/macro', { method: 'POST', headers: { 'content-type': 'application/json', 'x-link-peer': 'nobody' }, body: '{"name":"brb"}' });
  check('unknown peer id without a token gets 401', noToken.status === 401);
} finally {
  for (const n of [A, B]) { n.child.kill(); }
  await sleep(300);
  for (const d of dirs) { try { fs.rmSync(d, { recursive: true, force: true }); } catch {} }
  close();
}
const failed = results.filter(r => !r).length;
console.log(failed ? `\n${failed} check(s) FAILED` : '\nAll pairing checks passed');
process.exit(failed ? 1 : 0);
