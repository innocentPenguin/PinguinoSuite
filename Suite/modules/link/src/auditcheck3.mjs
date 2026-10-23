// Regression tests for the 53 security review (batch 1: tailnet IP parsing, update sharing off by default, going-live confirmation, import allow-list).
// Run: node src/auditcheck3.mjs
import './testenv.mjs';
import { spawn } from 'node:child_process';
import os from 'node:os';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { isTailnetIp } from './mesh.mjs';
import { DEFAULTS } from './config.mjs';
import * as settings from './settings.mjs';

const cli = fileURLToPath(new URL('./cli.mjs', import.meta.url));
let bad = 0;
const check = (n, c, x = '') => { console.log(`${c ? 'PASS' : 'FAIL'}  ${n}${c ? '' : '  ' + x}`); if (!c) bad++; };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const until = async (fn, ms = 20000) => { const t = Date.now(); while (Date.now() - t < ms) { try { const v = await fn(); if (v) return v; } catch {} await sleep(300); } return null; };

// 1. isTailnetIp is a parse, not a prefix match
const yes = ['100.64.0.1', '100.127.255.254', '100.74.117.87', 'fd7a:115c:a1e0::1', 'FD7A:115C:A1E0:ab12::7', '::ffff:100.100.1.1'];
const no = ['100.64.0.1.evil.example.com', '100.64.0.1.evil.test', '100.63.0.1', '100.128.0.1', '100.64.0.1:80', '100.64.0.1 ', '100.64.0', '100.64.0.256', '8.8.8.8', 'fd7a:115c:a1e0:evil.com', 'fd7a:115c:a1e0:xyz', '', 'localhost', '100.64.0.1/x', '1.100.64.0.1'];
check('real tailnet addresses are accepted', yes.every(x => isTailnetIp(x)), yes.filter(x => !isTailnetIp(x)).join(' '));
check('lookalike names and bad addresses are refused', no.every(x => !isTailnetIp(x)), no.filter(x => isTailnetIp(x)).join(' '));
let refused = false; try { settings.apply({}, {}, { 'obs.host': '100.64.0.1.evil.example.com' }); } catch (e) { refused = e.status === 400; }
check('OBS host setting refuses a lookalike name', refused);

// 2. update sharing is opt-in
check('sharing and fetching updates default to OFF', DEFAULTS.mesh === undefined || (DEFAULTS.mesh.shareUpdates !== true && DEFAULTS.mesh.fetchUpdates !== true));
const fields = settings.view({}, { getName: () => 'x', setName() {} }).flatMap(g => g.fields);
check('settings page defaults for both are off', fields.find(f => f.key === 'mesh.shareUpdates')?.def === false && fields.find(f => f.key === 'mesh.fetchUpdates')?.def === false);

// 3. going live needs confirmation, imports cannot carry protected keys (on a real spawned Link)
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'plink-a3-')); fs.mkdirSync(path.join(dir, 'link'), { recursive: true });
const port = 9000 + Math.floor(Math.random() * 90);
fs.writeFileSync(path.join(dir, 'link', 'config.json'), JSON.stringify({ role: 'hub', hub: 'x', port, token: 'module-token-3-module-token-0003', inbox: dir, obs: { host: '127.0.0.1', port: 1, password: 'x' }, macros: {}, claude: { enabled: false, cli: 'claude' } }));
const child = spawn(process.execPath, [cli, 'serve'], { stdio: 'ignore', windowsHide: true, env: { ...process.env, PINGUINO_LINK_PORT: String(port), PINGUINO_API_TOKEN: 'core-3', PINGUINO_DATA_DIR: dir, PINGUINO_MESH_TEST: '1', PINGUINO_CORE_URL: 'http://127.0.0.1:1' } });
const base = `http://127.0.0.1:${port}`;
const call = async (method, p, body) => { const r = await fetch(base + p, { method, headers: { 'x-link-token': 'core-3', 'content-type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) }); return { status: r.status, json: await r.json().catch(() => ({})) }; };
const cfgNow = () => JSON.parse(fs.readFileSync(path.join(dir, 'link', 'config.json'), 'utf8'));
try {
  await until(async () => (await fetch(base + '/api/health')).ok);
  const a = await call('POST', '/api/settings', { changes: { 'safety.allowStartStream': true } });
  check('turning on Allow Start Stream without confirmation is refused (409)', a.status === 409 && a.json.needs === 'confirm_live' && cfgNow().safety?.allowStartStream !== true, JSON.stringify(a));
  const b = await call('POST', '/api/settings', { changes: { 'mesh.remoteRisky': true } });
  check('remote start/stop needs confirmation too', b.status === 409 && cfgNow().mesh?.remoteRisky !== true, JSON.stringify(b));
  const c = await call('POST', '/api/settings', { changes: { 'safety.allowStartStream': true }, confirm_live: true });
  check('with confirm_live it is applied', c.status === 200 && cfgNow().safety?.allowStartStream === true, JSON.stringify(c));
  const off = await call('POST', '/api/settings', { changes: { 'safety.allowStartStream': false } });
  check('turning it OFF never needs confirmation', off.status === 200);

  const evil = { format: 'pinguinolink-settings', version: 1, settings: { 'safety.allowStartStream': true, 'mesh.remoteRisky': true, 'mesh.shareUpdates': true, 'mesh.fetchUpdates': true, 'mesh.allowRemoteMacros': true, 'obs.host': '100.64.0.1', inbox: 'C:/Users/x/Startup', hub: 'evil', role: 'client', 'cooldown.macroMs': 0, 'ui.accent': '#112233' }, macros: [] };
  const imp = await call('POST', '/api/import', { data: evil });
  const cfg = cfgNow();
  check('import applies looks only; protected keys are ignored and listed', imp.status === 200 && cfg.safety?.allowStartStream !== true && cfg.mesh?.remoteRisky !== true && cfg.mesh?.shareUpdates !== true && cfg.mesh?.fetchUpdates !== true && cfg.obs.host === '127.0.0.1' && cfg.hub === 'x' && cfg.inbox === dir && imp.json.ignored?.includes('safety.allowStartStream') && imp.json.ignored.includes('obs.host') && imp.json.ignored.includes('inbox'), JSON.stringify({ imp: imp.json, cfg }));
  check('import still applies harmless settings', cfg.ui?.accent === '#112233' && cfg.cooldown?.macroMs === 0, JSON.stringify(cfg.ui));
  const weird = await call('POST', '/api/import', { data: { format: 'pinguinolink-settings', settings: 'nope', macros: [] } });
  check('import with a non-object settings value does not crash', weird.status === 200 || weird.status === 400, JSON.stringify(weird));
  const sh = await fetch(base + '/api/mesh/updates/list', { method: 'POST', headers: { 'content-type': 'application/json', 'x-link-peer': 'nobody', 'x-link-token': 'z'.repeat(40) }, body: '{}' });
  check('update list stays closed to strangers', sh.status === 401);
} finally { child.kill(); await sleep(300); try { fs.rmSync(dir, { recursive: true, force: true }); } catch {} }
console.log(bad ? `\n${bad} check(s) FAILED` : '\nAll audit-3 batch-1 checks passed');
process.exit(bad ? 1 : 0);
