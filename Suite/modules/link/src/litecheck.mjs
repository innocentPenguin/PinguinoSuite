// PinguinoLite contract checks in a temp folder. Run: node src/litecheck.mjs
process.env.PINGUINO_NEVER_REAL_OBS = '1';   // tests must never reach the real OBS
import fs from 'node:fs'; import os from 'node:os'; import path from 'node:path';
import { createLite, cmpVersion } from './lite.mjs';
const results = []; const check = (n, ok, x = '') => { results.push(ok); console.log(`${ok ? 'PASS' : 'FAIL'}  ${n}${ok ? '' : '  ' + x}`); };
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'plink-lite-')), mods = path.join(tmp, 'modules'), dir = path.join(tmp, 'lite');
fs.mkdirSync(path.join(mods, 'aaa'), { recursive: true }); fs.writeFileSync(path.join(mods, 'aaa', 'module.json'), JSON.stringify({ id: 'aaa', name: 'Aaa', desc: 'test', version: '1.9.0' }));
fs.mkdirSync(path.join(mods, 'Bad Id'), { recursive: true }); fs.writeFileSync(path.join(mods, 'Bad Id', 'module.json'), JSON.stringify({ id: '../x' }));
const rd = f => JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8'));
try {
  check('1.10.0 > 1.9.0', cmpVersion('1.10.0', '1.9.0') === 1 && cmpVersion('1.0', '1.0.0') === 0);
  const lite = createLite({ dir, modulesRoot: mods, getHealth: async () => true });
  await lite.start();
  check('installed.json lists only valid modules', Object.keys(rd('installed.json').modules).join() === 'aaa' && rd('installed.json').schema === 1);
  check('catalog lists it with latest_version', rd('modules_catalog.json').modules[0].latest_version === '1.9.0');
  check('status.json heartbeat + connector', rd('status.json').writer.name === 'PinguinoLink' && rd('status.json').connector.state === 'connected');
  check('no updates at first', rd('update_status.json').updates_available === 0);
  fs.mkdirSync(path.join(dir, 'packages'), { recursive: true }); fs.writeFileSync(path.join(dir, 'packages', 'aaa-1.10.0.zip'), 'x');
  fs.writeFileSync(path.join(dir, 'requests', '1-check.json'), JSON.stringify({ schema: 1, action: 'check', id: null }));
  fs.writeFileSync(path.join(dir, 'requests', '2-check.json.tmp'), '{}');
  await lite.poll();
  check('check request is consumed and finds the newer package', !fs.existsSync(path.join(dir, 'requests', '1-check.json')) && rd('update_status.json').updates_available === 1);
  check('*.tmp requests are ignored', fs.existsSync(path.join(dir, 'requests', '2-check.json.tmp')));
  fs.writeFileSync(path.join(dir, 'requests', '3-start-aaa.json'), JSON.stringify({ schema: 1, action: 'start', id: 'aaa' }));
  await lite.poll();
  check('start is consumed and reported as not available (not silent)', rd('update_status.json').result === 'error' && /not available/.test(rd('update_status.json').error) && fs.readdirSync(path.join(dir, 'requests')).every(f => f.endsWith('.tmp')));
  process.env.PINGUINO_LITE_VERSION = '0.1.0';
  fs.mkdirSync(path.join(dir, 'staging'), { recursive: true });
  const exe = path.join(dir, 'staging', 'PinguinoLite-0.2.0-setup.exe'); fs.writeFileSync(exe, 'fake installer');
  await lite.refresh();
  check('staged Lite without .sha256 is not offered', !fs.existsSync(path.join(dir, 'update_manifest.json')) && rd('update_status.json').lite_update_available === false);
  const { createHash } = await import('node:crypto');
  fs.writeFileSync(exe + '.sha256', createHash('sha256').update('fake installer').digest('hex'));
  await lite.refresh();
  check('verified staged Lite is offered in update_manifest.json', rd('update_manifest.json').latest_version === '0.2.0' && /^staging.PinguinoLite-0\.2\.0-setup\.exe$/.test(rd('update_manifest.json').staged_file) && rd('update_status.json').lite_update_available === true);
  process.env.PINGUINO_LITE_VERSION = '0.2.0'; await lite.refresh();
  check('no offer when Lite is already current', !fs.existsSync(path.join(dir, 'update_manifest.json')));
  const { sharedPath, listShared } = await import('./lite.mjs');
  check('sharedPath refuses traversal and odd names', ['../config.json', '..\\x.zip', 'a/b-1.0.zip', 'C:\\x-1.zip', 'demo-1.0.0.zip/../../x', 'config.json'].every(n => sharedPath(dir, n) === null));
  check('listShared offers only hash-sidecar files', listShared(dir).every(f => /^[0-9a-f]{64}$/.test(f.sha256)));
  lite.stop();
} finally { fs.rmSync(tmp, { recursive: true, force: true }); }
const failed = results.filter(r => !r).length; console.log(failed ? `\n${failed} FAILED` : '\nAll lite checks passed'); process.exit(failed ? 1 : 0);
