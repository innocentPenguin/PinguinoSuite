// Settings and macro-editor API check (no OBS needed). Run: node src/settingscheck.mjs
import { spawn } from 'node:child_process';
import os from 'node:os';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const cli = fileURLToPath(new URL('./cli.mjs', import.meta.url));
const results = [];
const check = (name, ok, extra = '') => { results.push(ok); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${ok ? '' : '  ' + extra}`); };
const sleep = ms => new Promise(r => setTimeout(r, ms));

const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'plink-sc-'));
fs.mkdirSync(path.join(dir, 'link'), { recursive: true });
const hand = { type: 'SetSourceFilterEnabled', data: { sourceName: 'x', filterName: 'y', filterEnabled: true } };
fs.writeFileSync(path.join(dir, 'link', 'config.json'), JSON.stringify({ role: 'client', hub: 'h', port: 7777, token: 'module-token-module-token-0002', inbox: dir, obs: { host: '127.0.0.1', port: 4455, password: '' }, macros: { hand: [hand] } }));
const port = 7990 + Math.floor(Math.random() * 9);
const child = spawn(process.execPath, [cli, 'serve'], { stdio: 'ignore', windowsHide: true,
  env: { ...process.env, PINGUINO_LINK_PORT: String(port), PINGUINO_API_TOKEN: 'core-sc', PINGUINO_DATA_DIR: dir, PINGUINO_CORE_URL: 'http://127.0.0.1:1' } });
const base = `http://127.0.0.1:${port}`;
const call = async (method, p, body) => {
  const r = await fetch(base + p, { method, headers: { 'x-link-token': 'core-sc', ...(body !== undefined ? { 'content-type': 'application/json' } : {}) }, body: body === undefined ? undefined : JSON.stringify(body) });
  return { status: r.status, json: await r.json().catch(() => ({})) };
};
const cfgFile = () => JSON.parse(fs.readFileSync(path.join(dir, 'link', 'config.json'), 'utf8'));
try {
  for (let i = 0; i < 30; i++) { try { if ((await fetch(base + '/api/health')).ok) break; } catch {} await sleep(300); }
  const get = await call('GET', '/api/settings');
  const fields = get.json.groups.flatMap(g => g.fields);
  check('settings: every field has a one-line help and a default', fields.length > 15 && fields.every(f => f.help && f.def !== undefined));
  check('settings: no secret fields exposed', !fields.some(f => /password|token|secret/i.test(f.key)));

  const set = async (k, v, extra) => call('POST', '/api/settings', { changes: { [k]: v }, ...extra });
  check('set a number within range', (await set('ui.refreshSec', 10)).json.changed?.[0] === 'ui.refreshSec' && cfgFile().ui.refreshSec === 10);
  check('number out of range rejected', (await set('ui.refreshSec', 1)).status === 400);
  check('bad colour rejected, good accepted', (await set('ui.accent', 'orange')).status === 400 && (await set('ui.accent', '#ff9900')).status === 200);
  check('OBS address must be local or tailnet', (await set('obs.host', '8.8.8.8')).status === 400 && (await set('obs.host', '100.64.1.2')).status === 200);
  check('relative inbox path rejected', (await set('inbox', 'Downloads')).status === 400);
  check('unknown setting rejected', (await set('token', 'x')).status === 400);
  const roleTry = await set('role', 'hub');
  check('role change without confirmation = 409 and unchanged', roleTry.status === 409 && roleTry.json.needs === 'confirm_role' && cfgFile().role === 'client');
  check('role change with confirmation applies', (await set('role', 'hub', { confirm_role: true })).status === 200 && cfgFile().role === 'hub');
  check('reset to default removes the stored override', (await set('ui.refreshSec', null)).status === 200 && cfgFile().ui?.refreshSec === undefined);
  check('batch is all-or-nothing', (await call('POST', '/api/settings', { changes: { 'ui.compact': true, 'ui.refreshSec': 999 } })).status === 400 && !cfgFile().ui?.compact);
  check('device name can be changed', (await set('device.name', 'Studio PC')).status === 200 && (await call('GET', '/api/mesh/status')).json.self.name === 'Studio PC');
  const st = await call('GET', '/api/status');
  check('status carries ui personalisation', st.json.ui?.accent === '#ff9900' && Array.isArray(st.json.macro_buttons));

  const m = (await call('GET', '/api/macros')).json;
  check('macro list shows a hand-written step as custom', m.macros.find(x => x.name === 'hand')?.steps[0].kind === 'custom');
  const add = await call('POST', '/api/macros/set', { name: 'go-live', label: 'Go live', icon: '🔴', steps: [{ kind: 'scene', value: 'Main' }, { kind: 'stream-start' }] });
  check('add a macro with 2 steps', add.status === 200 && cfgFile().macros['go-live'].length === 2 && cfgFile().macros['go-live'][1].type === 'StartStream');
  const btn = (await call('GET', '/api/status')).json.macro_buttons.find(b => b.name === 'go-live');
  check('macro with StartStream is flagged risky, label/icon applied', btn?.risky === true && btn.label === 'Go live' && btn.icon === '🔴');
  check('bad macro name rejected', (await call('POST', '/api/macros/set', { name: 'bad name!', steps: [{ kind: 'stream-stop' }] })).status === 400);
  check('unknown action rejected (allow-list)', (await call('POST', '/api/macros/set', { name: 'x', steps: [{ kind: 'RemoveScene' }] })).status === 400);
  check('scene step without a scene rejected', (await call('POST', '/api/macros/set', { name: 'x', steps: [{ kind: 'scene', value: '' }] })).status === 400);
  const keep = await call('POST', '/api/macros/set', { name: 'hand', steps: [{ kind: 'custom' }] });
  check('editing keeps a custom step untouched', keep.status === 200 && JSON.stringify(cfgFile().macros.hand[0]) === JSON.stringify(hand));
  await call('POST', '/api/macros/move', { name: 'go-live', dir: -1 });
  check('macro can be moved up', Object.keys(cfgFile().macros)[0] === 'go-live');
  check('macro check explains itself when OBS is not reachable', !!(await call('POST', '/api/macros/check', { name: 'go-live' })).json.note);
  check('macro can be deleted', (await call('POST', '/api/macros/delete', { name: 'go-live' })).status === 200 && !cfgFile().macros['go-live'] && !cfgFile().macroMeta?.['go-live']);
  check('reload keeps all settings', cfgFile().ui.accent === '#ff9900' && cfgFile().obs.host === '100.64.1.2');

  const ex = (await call('GET', '/api/export')).json;
  check('export has settings and macros, no secrets', ex.format === 'pinguinolink-settings' && ex.settings['ui.accent'] === '#ff9900' && !JSON.stringify(ex).match(/token|password|module-token/i));
  await call('POST', '/api/macros/set', { name: 'tmp', steps: [{ kind: 'record-toggle' }] });
  const exm = (await call('GET', '/api/export')).json;
  check('export lists editor macros and counts skipped custom steps', exm.macros.some(m => m.name === 'tmp') && exm.skipped_custom_steps === 1);
  await call('POST', '/api/settings', { changes: { 'ui.accent': null, 'obs.host': null } });
  await call('POST', '/api/macros/delete', { name: 'tmp' });
  const imp = await call('POST', '/api/import', { data: exm });
  check('import restores settings and macros', imp.status === 200 && cfgFile().ui.accent === '#ff9900' && !!cfgFile().macros.tmp);
  check('import rejects foreign files', (await call('POST', '/api/import', { data: { format: 'other' } })).status === 400);
  const badImp = await call('POST', '/api/import', { data: { format: 'pinguinolink-settings', settings: {}, macros: [{ name: 'ok1', steps: [{ kind: 'stream-stop' }] }, { name: 'bad name', steps: [{ kind: 'x' }] }] } });
  check('bad import is all-or-nothing', badImp.status === 400 && !cfgFile().macros.ok1);
  check('import never changes the role', (await call('POST', '/api/import', { data: { format: 'pinguinolink-settings', settings: { role: 'client' }, macros: [] } })).status === 200 && cfgFile().role === 'hub');
  await call('POST', '/api/settings', { changes: { 'log.level': 'error' } });
  const before = fs.readFileSync(path.join(dir, 'console', 'link.jsonl'), 'utf8').split('\n').length;
  await call('POST', '/api/settings', { changes: { 'ui.compact': true } });       // would log info
  await sleep(300);
  check('log level filters lower levels', fs.readFileSync(path.join(dir, 'console', 'link.jsonl'), 'utf8').split('\n').length === before);
  const page = await fetch(base + '/').then(r => r.text());
  check('page loads with settings and macro editor', page.includes('id=sdet') && page.includes('id=mdet') && page.includes('/theme.css'));
} finally { child.kill(); try { fs.rmSync(dir, { recursive: true, force: true }); } catch {} }
const failed = results.filter(r => !r).length;
console.log(failed ? `\n${failed} check(s) FAILED` : '\nAll settings checks passed');
process.exit(failed ? 1 : 0);
