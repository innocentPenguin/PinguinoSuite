// Remote macros through pairing: a CLIENT presses a macro, the paired HUB runs it in a FAKE OBS. Run: node src/remotecheck.mjs
process.env.PINGUINO_NEVER_REAL_OBS = '1';   // tests must never reach the real OBS
import { spawn } from 'node:child_process';
import os from 'node:os';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { startFakeObs } from './fakeobs.mjs';

const cli = fileURLToPath(new URL('./cli.mjs', import.meta.url));
const results = [];
const check = (name, ok, extra = '') => { results.push(ok); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${ok ? '' : '  ' + extra}`); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const until = async (fn, ms = 15000) => { const t = Date.now(); while (Date.now() - t < ms) { try { const v = await fn(); if (v) return v; } catch {} await sleep(300); } return null; };

const { obs, obsPort, close } = await startFakeObs('pw-secret-1');
const macros = { brb: [{ type: 'SetCurrentProgramScene', data: { sceneName: 'BRB' } }], live: [{ type: 'SetCurrentProgramScene', data: { sceneName: 'Main' } }], start: [{ type: 'StartStream' }], stop: [{ type: 'StopStream' }] };

async function node(name, port, role, extra = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), `plink-rc-${name}-`));
  fs.mkdirSync(path.join(dir, 'link'), { recursive: true });
  const cfg = { role, hub: 'hubpc', port, token: `module-token-${name}-module-token-0003`, inbox: dir, obs: { host: '127.0.0.1', port: obsPort, password: 'pw-secret-1' }, macros, claude: { enabled: false, cli: 'claude' }, cooldown: { macroMs: 0, riskyMs: 0 }, ...extra };
  fs.writeFileSync(path.join(dir, 'link', 'config.json'), JSON.stringify(cfg));
  const child = spawn(process.execPath, [cli, 'serve'], { stdio: 'ignore', windowsHide: true,
    env: { ...process.env, PINGUINO_LINK_PORT: String(port), PINGUINO_API_TOKEN: `core-${name}`, PINGUINO_DATA_DIR: dir, PINGUINO_MESH_TEST: '1', PINGUINO_CORE_URL: 'http://127.0.0.1:1' } });
  const base = `http://127.0.0.1:${port}`;
  const call = async (method, p, body, headers = {}) => {
    const r = await fetch(base + p, { method, signal: AbortSignal.timeout(100000), headers: { 'x-link-token': `core-${name}`, ...(body !== undefined ? { 'content-type': 'application/json' } : {}), ...headers }, body: body === undefined ? undefined : JSON.stringify(body) });
    return { status: r.status, json: await r.json().catch(() => ({})) };
  };
  await until(async () => (await fetch(base + '/api/health')).ok);
  return { dir, child, call, base };
}

const pa = 8000 + Math.floor(Math.random() * 40), pb = pa + 50;
const A = await node('A', pa, 'hub', { safety: { allowStartStream: true } }), B = await node('B', pb, 'client');
try {
  await A.call('POST', '/api/settings', { changes: { 'device.name': 'hubpc' } });
  await B.call('POST', '/api/settings', { changes: { 'device.name': 'clientpc' } });
  const { json: code } = await A.call('POST', '/api/mesh/pair/start', {});
  const joining = B.call('POST', '/api/mesh/pair/join', { addr: `127.0.0.1:${pa}`, code: code.code });
  const pend = await until(async () => (await A.call('GET', '/api/mesh/status')).json.pending?.[0]);
  if (!pend) { console.log('join result', JSON.stringify(await Promise.race([joining, sleep(100).then(() => 'pending')]))); }
  await A.call('POST', '/api/mesh/pair/approve', { id: pend.id, allow: true });
  check('pairing completes', (await joining).status === 200);
  await until(async () => (await B.call('GET', '/api/mesh/status')).json.peers.every(p => p.online) && (await B.call('GET', '/api/mesh/status')).json.peers.length === 1);

  const brb = await B.call('POST', '/api/macro/brb');
  check('client presses brb, hub switches OBS scene', brb.status === 200 && obs.scene === 'BRB', JSON.stringify(brb));
  const act = (await A.call('GET', '/api/activity')).json.items;
  check('hub activity shows who pressed it', act.some(a => a.name === 'brb' && a.detail === 'from clientpc'));

  const start = await B.call('POST', '/api/macro/start');
  check('remote start-stream is refused by default (403)', start.status === 403 && obs.streaming === false && /turned off/.test(start.json.error || ''), JSON.stringify(start));
  await A.call('POST', '/api/settings', { changes: { 'mesh.remoteRisky': true } });
  check('after the hub allows it, remote start works', (await B.call('POST', '/api/macro/start')).status === 200 && obs.streaming === true);
  check('remote stop works', (await B.call('POST', '/api/macro/stop')).status === 200 && obs.streaming === false);
  check('hub guard still applies through the client (stop while idle = 409)', (await B.call('POST', '/api/macro/stop')).status === 409);

  await A.call('POST', '/api/settings', { changes: { 'mesh.allowRemoteMacros': false } });
  const off = await B.call('POST', '/api/macro/live');
  check('hub can turn remote macros off (403 with explanation)', off.status === 403 && /remote macros are turned off/.test(off.json.error || '') && obs.scene === 'BRB', JSON.stringify(off));
  await A.call('POST', '/api/settings', { changes: { 'mesh.allowRemoteMacros': null } });
  check('and back on', (await B.call('POST', '/api/macro/live')).status === 200 && obs.scene === 'Main');
  check('unknown macro on the client is a clear error', /unknown macro/.test((await B.call('POST', '/api/macro/nope')).json.error || ''));

  const bad = await fetch(A.base + '/api/mesh/macro', { method: 'POST', headers: { 'content-type': 'application/json', 'x-link-peer': 'someone-else-id', 'x-link-token': 'z'.repeat(40) }, body: '{"name":"brb"}' });
  check('unpaired caller cannot use /api/mesh/macro (401)', bad.status === 401);
  const bad2 = await A.call('POST', '/api/mesh/macro', { name: 'brb' });
  check('module token alone is not a peer credential (401)', bad2.status === 401);

  const items = (await B.call('GET', '/api/prestream')).json.items;
  check('client prestream asks the hub about OBS', items.some(i => i.id === 'hub-obs' && i.status === 'pass') && items.some(i => i.id === 'hub-macros' && i.status === 'pass') && !items.some(i => i.id === 'obs'), JSON.stringify(items.map(i => i.id + '=' + i.status)));
  obs.scenes = ['Main'];
  await sleep(2200);
  const items2 = (await B.call('GET', '/api/prestream')).json.items;
  check('hub macro problems show on the client report', items2.find(i => i.id === 'hub-macros')?.status === 'fail');
} finally {
  for (const n of [A, B]) { n.child.kill(); try { fs.rmSync(n.dir, { recursive: true, force: true }); } catch {} }
  close();
}
const failed = results.filter(r => !r).length;
console.log(failed ? `\n${failed} check(s) FAILED` : '\nAll remote macro checks passed');
process.exit(failed ? 1 : 0);
