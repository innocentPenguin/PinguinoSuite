// The plain-language morning check. Run: node src/morningcheck.mjs
import './testenv.mjs';
import { spawn } from 'node:child_process';
import os from 'node:os';
import fs from 'node:fs';
import net from 'node:net';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { startFakeObs } from './fakeobs.mjs';
import { morning, probeObsPort } from './morning.mjs';

const cli = fileURLToPath(new URL('./cli.mjs', import.meta.url));
let bad = 0;
const check = (n, c, x = '') => { console.log(`${c ? 'PASS' : 'FAIL'}  ${n}${c ? '' : '  ' + x}`); if (!c) bad++; };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const until = async (fn, ms = 20000) => { const t = Date.now(); while (Date.now() - t < ms) { try { const v = await fn(); if (v) return v; } catch {} await sleep(300); } return null; };
const line = (r, label) => r.lines.find(l => l.label === label);
const pass = id => ({ id, label: id, status: 'pass', detail: 'ok detail' });

// --- pure logic
const hub = { role: 'hub', hub: 'x' }, cli1 = { role: 'client', hub: 'streampc' };
let r = morning(hub, { items: [pass('obs'), pass('macros'), pass('tailscale')], mesh: { peers: [{ name: 'mac', online: true }] }, probe: { state: 'closed', addrs: [] } });
check('all good gives verdict good', r.verdict === 'good' && /All good/.test(r.headline), JSON.stringify(r));
check('hub role is explained in plain words', /HUB: it runs OBS/.test(line(r, 'This PC').text));
check('port 4455 closed is good', line(r, 'OBS port 4455').status === 'good');
r = morning(hub, { items: [pass('obs'), { id: 'macros', status: 'fail', detail: 'live: scene "Main" (set obsNames)' }, pass('tailscale')], mesh: { peers: [{ name: 'mac', online: false }, { name: 'pc2', online: true }] }, probe: { state: 'open', addrs: ['192.168.1.5'] } });
check('missing names and an offline PC make it a problem', r.verdict === 'problem' && /2 things need fixing/.test(r.headline) && /scene "Main"/.test(line(r, 'Scene and mic names').text) && /Offline: mac/.test(line(r, 'Other PCs').text), JSON.stringify(r.lines));
check('open port 4455 is a note naming the address', line(r, 'OBS port 4455').status === 'note' && /192\.168\.1\.5/.test(line(r, 'OBS port 4455').text));
r = morning(cli1, { items: [{ id: 'hub-obs', status: 'pass', detail: '' }, pass('hub-macros')], mesh: { peers: [] }, probe: null });
check('client reads the hub items and has no port line', /CLIENT/.test(line(r, 'This PC').text) && /hub reports OBS/.test(line(r, 'OBS').text) && !line(r, 'OBS port 4455') && line(r, 'Scene and mic names').status === 'good');
r = morning({ ...hub, safety: { allowStartStream: true }, mesh: { remoteRisky: true } }, { items: [], mesh: { peers: [] }, probe: { state: 'obs-off' } });
check('start-stream allowed and remote stop show as notes', line(r, 'Going live').status === 'note' && line(r, 'Remote stop') && r.verdict === 'attention');
check('safe default says buttons cannot start the stream', /cannot start the stream/.test(line(morning(hub, {}), 'Going live').text));
check('probe never touches the real port in tests', (await probeObsPort(4455)).state === 'skipped');
const srv = net.createServer(s => s.destroy()); await new Promise(x => srv.listen(0, '0.0.0.0', x));
const hasNet = Object.values(os.networkInterfaces()).flat().some(a => a && a.family === 'IPv4' && !a.internal);   // no network adapter = nothing to probe
const pr = await probeObsPort(srv.address().port);
check('probe sees a port that listens on all interfaces', hasNet ? pr.state === 'open' : pr.state === 'closed', JSON.stringify(pr));
srv.close();
const none = await probeObsPort(1);
check('probe says obs-off when nothing listens', none.state === 'obs-off', JSON.stringify(none));

// --- the endpoint on a real (spawned) hub with a fake OBS
const f = await startFakeObs('pw-secret-1');
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'plink-morning-')); fs.mkdirSync(path.join(dir, 'link'), { recursive: true });
const port = 8900 + Math.floor(Math.random() * 90);
fs.writeFileSync(path.join(dir, 'link', 'config.json'), JSON.stringify({ role: 'hub', hub: 'x', port, token: 'module-token-M-module-token-0003', inbox: dir, obs: { host: '127.0.0.1', port: f.obsPort, password: 'pw-secret-1' },
  macros: { live: [{ type: 'SetCurrentProgramScene', data: { sceneName: 'Main' } }], mute: [{ type: 'ToggleInputMute', data: { inputName: 'Mic/Aux' } }] }, claude: { enabled: false, cli: 'claude' } }));
const child = spawn(process.execPath, [cli, 'serve'], { stdio: 'ignore', windowsHide: true, env: { ...process.env, PINGUINO_LINK_PORT: String(port), PINGUINO_API_TOKEN: 'core-M', PINGUINO_DATA_DIR: dir, PINGUINO_MESH_TEST: '1', PINGUINO_CORE_URL: 'http://127.0.0.1:1' } });
const base = `http://127.0.0.1:${port}`;
try {
  await until(async () => (await fetch(base + '/api/health')).ok);
  const noTok = await fetch(base + '/api/morning');
  check('endpoint needs the token', noTok.status === 401);
  const res = await fetch(base + '/api/morning', { headers: { 'x-link-token': 'core-M' } });
  const j = await res.json();
  check('endpoint answers with a verdict and plain lines', res.status === 200 && ['good', 'attention', 'problem'].includes(j.verdict) && j.lines.length >= 6 && j.lines.every(l => l.label && l.text), JSON.stringify(j).slice(0, 300));
  check('OBS reachable and names resolved are reported', line(j, 'OBS')?.status === 'good' && line(j, 'Scene and mic names')?.status === 'good', JSON.stringify(j.lines));
  check('no secret in the output', !JSON.stringify(j).includes('pw-secret-1') && !JSON.stringify(j).includes('module-token'));
  check('check only read from OBS (nothing changed, nothing live)', f.obs.streaming === false && f.obs.log.every(t => /^Get/.test(t)), f.obs.log.join(','));
  const post = await fetch(base + '/api/morning', { method: 'POST', headers: { 'x-link-token': 'core-M' } });
  check('POST is not accepted (read-only)', post.status >= 400);
} finally { child.kill(); await sleep(300); try { fs.rmSync(dir, { recursive: true, force: true }); } catch {} f.close(); }
console.log(bad ? `\n${bad} check(s) FAILED` : '\nAll morning-check checks passed');
process.exit(bad ? 1 : 0);
