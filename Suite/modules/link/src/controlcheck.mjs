// Lite start/stop/restart checks with a fake Suite core (consumes control files) and a fake health. Run: node src/controlcheck.mjs
process.env.PINGUINO_NEVER_REAL_OBS = '1';
import fs from 'node:fs'; import os from 'node:os'; import path from 'node:path';
import { createLite } from './lite.mjs';
const results = []; const check = (n, ok, x = '') => { results.push(ok); console.log(`${ok ? 'PASS' : 'FAIL'}  ${n}${ok ? '' : '  ' + x}`); };
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'plink-ctl-')), mods = path.join(tmp, 'modules'), dir = path.join(tmp, 'lite'), control = path.join(tmp, 'control');
const mk = (id, port) => { fs.mkdirSync(path.join(mods, id), { recursive: true }); fs.writeFileSync(path.join(mods, id, 'module.json'), JSON.stringify({ id, name: id, version: '1.0.0', ...(port ? { port } : {}) })); };
mk('aaa', 7101); mk('noport'); mk('link', 7777);
let up = false, core = true, seen = [];
const fakeCore = setInterval(() => { if (!core || !fs.existsSync(control)) return; for (const f of fs.readdirSync(control)) { seen.push(f); fs.unlinkSync(path.join(control, f)); if (f.startsWith('start-aaa')) up = true; if (f.startsWith('stop-aaa')) up = false; } }, 100);
const rd = f => JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8'));
const req = async (o) => { fs.mkdirSync(path.join(dir, 'requests'), { recursive: true }); fs.writeFileSync(path.join(dir, 'requests', `${Date.now()}-${o.action}.json`), JSON.stringify({ schema: 1, ...o })); await lite.poll(); };
const lite = createLite({ dir, modulesRoot: mods, control, settleMs: 3000, getHealth: async m => m.port === 7101 ? up : true });
try {
  await lite.start();
  await req({ action: 'start', id: 'aaa' });
  check('start drops start-aaa and module becomes running', seen.includes('start-aaa') && rd('installed.json').modules.aaa.state === 'running' && rd('update_status.json').result === 'ok');
  seen = []; await req({ action: 'start', id: 'aaa' });
  check('start on a running module does nothing', seen.length === 0);
  await req({ action: 'restart', id: 'aaa' });
  check('restart drops restart-aaa and ends running', seen.includes('restart-aaa') && rd('installed.json').modules.aaa.state === 'running');
  await req({ action: 'stop', id: 'aaa' });
  check('stop drops stop-aaa and ends stopped', seen.includes('stop-aaa') && rd('installed.json').modules.aaa.state === 'stopped');
  seen = []; await req({ action: 'stop', id: 'link' });
  check('link cannot stop itself', seen.length === 0 && /cannot stop or restart itself/.test(rd('update_status.json').error));
  await req({ action: 'start', id: 'nope' });
  check('unknown module refused', /not installed/.test(rd('update_status.json').error));
  await req({ action: 'start', id: '../x' });
  check('bad id refused, nothing written outside control', /bad module id/.test(rd('update_status.json').error) && !fs.existsSync(path.join(tmp, 'x')));
  await req({ action: 'start', id: 'noport' });
  check('module without a port refused', /no port/.test(rd('update_status.json').error));
  up = false; core = false;
  await req({ action: 'start', id: 'aaa' });
  check('core not running: error and control file cleaned up', /did not pick up/.test(rd('update_status.json').error) && fs.readdirSync(control).length === 0, JSON.stringify(rd('update_status.json')));
  check('busy flag cleared', Object.keys(rd('status.json').busy).length === 0);
} finally { clearInterval(fakeCore); lite.stop?.(); fs.rmSync(tmp, { recursive: true, force: true }); }
const bad = results.filter(r => !r).length; console.log(bad ? `${bad} FAILED` : `all ${results.length} passed`); process.exit(bad ? 1 : 0);
