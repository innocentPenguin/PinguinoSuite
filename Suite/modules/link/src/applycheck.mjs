// Lite self-update apply: hash re-check, wait for exit, backup, silent install (fake installer), relaunch, auto-restore. Run: node src/applycheck.mjs
process.env.PINGUINO_NEVER_REAL_OBS = '1';   // tests must never reach the real OBS
process.env.PINGUINO_LITE_TEST = '1';
import './testenv.mjs';
import fs from 'node:fs'; import os from 'node:os'; import path from 'node:path'; import crypto from 'node:crypto';
import { createLite } from './lite.mjs';
const results = []; const check = (n, ok, x = '') => { results.push(ok); console.log(`${ok ? 'PASS' : 'FAIL'}  ${n}${ok ? '' : '  ' + x}`); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const until = async (fn, ms = 20000) => { const t = Date.now(); while (Date.now() - t < ms) { if (await fn()) return true; await sleep(200); } return false; };
const sha = b => crypto.createHash('sha256').update(b).digest('hex');
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'plink-apply-')), mods = path.join(tmp, 'modules');
fs.mkdirSync(mods, { recursive: true });
const fakeInst = path.join(tmp, 'fakeinstaller.mjs');
fs.writeFileSync(fakeInst, `import fs from 'node:fs'; import path from 'node:path';
const [dir, mode] = process.argv.slice(2);
fs.writeFileSync(path.join(dir, 'version.txt'), mode === 'bad' ? 'half-written' : 'new');
process.exit(mode === 'bad' ? 1 : 0);`);
const rig = name => {                                       // a fake installed Lite + lite dir with a verified staged installer
  const root = path.join(tmp, name), dir = path.join(root, 'lite'), inst = path.join(root, 'install'), st = path.join(dir, 'staging');
  fs.mkdirSync(st, { recursive: true }); fs.mkdirSync(inst, { recursive: true });
  const exe = path.join(inst, 'PinguinoLite.exe'); fs.copyFileSync(process.execPath, exe);
  fs.writeFileSync(path.join(inst, 'version.txt'), 'old');
  const f = path.join(st, 'PinguinoLite-0.2.0-setup.exe'); fs.writeFileSync(f, 'installer bytes'); fs.writeFileSync(f + '.sha256', sha('installer bytes'));
  return { root, dir, inst, exe, f };
};
const rd = (d, f) => JSON.parse(fs.readFileSync(path.join(d, f), 'utf8'));
async function run(r, mode, procName = 'NoSuchLiteApp.exe') {
  process.env.PINGUINO_LITE_EXE = r.exe; process.env.PINGUINO_LITE_VERSION = '0.1.0';
  process.env.PINGUINO_LITE_TEST_JOB = JSON.stringify({ procName, installCmd: [process.execPath, fakeInst, r.inst, mode], waitMs: 3000 });
  const lite = createLite({ dir: r.dir, modulesRoot: mods, getHealth: async () => true });
  await lite.start();
  fs.writeFileSync(path.join(r.dir, 'requests', '1-selfupdate-apply.json'), JSON.stringify({ schema: 1, action: 'selfupdate-apply', id: null }));
  await lite.poll();
  const rf = () => ['lite_apply_result.json', 'lite_apply_result.seen.json'].find(n => fs.existsSync(path.join(r.dir, n)));   // Link renames it to .seen when the helper ends
  const done = await until(() => rf());
  lite.stop();
  return done ? rd(r.dir, rf()) : null;
}
try {
  // 1. happy path
  let r = rig('ok'); let res = await run(r, 'good');
  check('apply installs the staged update and reports ok', res?.ok === true && fs.readFileSync(path.join(r.inst, 'version.txt'), 'utf8') === 'new', JSON.stringify(res));
  check('old version was backed up first', fs.readdirSync(path.join(r.dir, 'backup')).some(n => n.startsWith('lite-0.1.0-')) && fs.readFileSync(path.join(r.dir, 'backup', fs.readdirSync(path.join(r.dir, 'backup'))[0], 'version.txt'), 'utf8') === 'old');
  // 2. failing installer -> automatic restore
  r = rig('bad'); res = await run(r, 'bad');
  check('failed installer: old version is put back automatically', res?.ok === false && /put back/.test(res.message) && fs.readFileSync(path.join(r.inst, 'version.txt'), 'utf8') === 'old', JSON.stringify(res));
  // 3. installer changed after the click -> refused, nothing touched
  r = rig('tamper');
  process.env.PINGUINO_LITE_EXE = r.exe; process.env.PINGUINO_LITE_VERSION = '0.1.0';
  process.env.PINGUINO_LITE_TEST_JOB = JSON.stringify({ procName: 'NoSuchLiteApp.exe', installCmd: [process.execPath, fakeInst, r.inst, 'good'] });
  const lite = createLite({ dir: r.dir, modulesRoot: mods, getHealth: async () => true }); await lite.start();
  fs.writeFileSync(r.f, 'tampered'); await lite.refresh();
  fs.writeFileSync(path.join(r.dir, 'requests', '1-selfupdate-apply.json'), JSON.stringify({ schema: 1, action: 'selfupdate-apply', id: null })); await lite.poll(); lite.stop();
  await sleep(1500);
  check('tampered installer is refused, nothing changed', !fs.existsSync(path.join(r.dir, 'lite_apply_result.json')) && fs.readFileSync(path.join(r.inst, 'version.txt'), 'utf8') === 'old' && /no verified installer/.test(rd(r.dir, 'update_status.json').error || ''));
  // 4. Lite still running -> waits, then gives up without changing anything
  r = rig('running'); res = await run(r, 'good', path.basename(process.execPath));
  await sleep(800);
  check('Lite still open: gives up after the wait, nothing changed', res?.ok === false && /did not close/.test(res.message) && fs.readFileSync(path.join(r.inst, 'version.txt'), 'utf8') === 'old', JSON.stringify(res));
  check('busy.lite is cleared again after a refused update (can retry)', Object.keys(rd(r.dir, 'status.json').busy).length === 0);
  // 5. no update staged
  r = rig('none'); fs.rmSync(path.join(r.dir, 'staging'), { recursive: true });
  process.env.PINGUINO_LITE_EXE = r.exe;
  const l2 = createLite({ dir: r.dir, modulesRoot: mods, getHealth: async () => true }); await l2.start();
  fs.writeFileSync(path.join(r.dir, 'requests', '1-selfupdate-apply.json'), JSON.stringify({ schema: 1, action: 'selfupdate-apply', id: null })); await l2.poll(); l2.stop();
  check('apply with nothing staged is refused with a clear message', /no verified installer/.test(rd(r.dir, 'update_status.json').error || '') && !fs.existsSync(path.join(r.dir, 'lite_apply_job.json')));
  // ---- macOS/Linux branch (fake platform, fake process lister, fake installer runner; nothing platform-specific is executed)
  process.env.PINGUINO_LITE_PLATFORM = 'linux';
  const fakePs = path.join(tmp, 'fakeps.mjs');
  fs.writeFileSync(fakePs, "console.log(process.env.FAKE_PS || '');");
  const unixRig = name => {
    const root = path.join(tmp, name), dir = path.join(root, 'lite'), inst = path.join(root, 'install'), st = path.join(dir, 'staging');
    fs.mkdirSync(st, { recursive: true }); fs.mkdirSync(inst, { recursive: true });
    const exe = path.join(inst, 'PinguinoLite'); fs.copyFileSync(process.execPath, exe);
    fs.writeFileSync(path.join(inst, 'version.txt'), 'old');
    const f = path.join(st, 'PinguinoLite-0.2.0-setup.sh'); fs.writeFileSync(f, 'installer bytes'); fs.writeFileSync(f + '.sha256', sha('installer bytes'));
    const w = path.join(st, 'PinguinoLite-0.3.0-setup.exe'); fs.writeFileSync(w, 'windows only'); fs.writeFileSync(w + '.sha256', sha('windows only'));
    return { root, dir, inst, exe, f };
  };
  const runUnix = async (r, mode, ps = '') => {
    process.env.PINGUINO_LITE_EXE = r.exe; process.env.PINGUINO_LITE_VERSION = '0.1.0'; process.env.FAKE_PS = ps;
    process.env.PINGUINO_LITE_TEST_JOB = JSON.stringify({ listCmd: [process.execPath, fakePs], installCmd: [process.execPath, fakeInst, r.inst, mode], waitMs: 2500 });
    const lite = createLite({ dir: r.dir, modulesRoot: mods, getHealth: async () => true });
    await lite.start();
    fs.writeFileSync(path.join(r.dir, 'requests', '1-selfupdate-apply.json'), JSON.stringify({ schema: 1, action: 'selfupdate-apply', id: null }));
    await lite.poll();
    const rf = () => ['lite_apply_result.json', 'lite_apply_result.seen.json'].find(n => fs.existsSync(path.join(r.dir, n)));
    const done = await until(() => rf()); lite.stop();
    return { res: done ? rd(r.dir, rf()) : null, job: fs.existsSync(path.join(r.dir, 'lite_apply_job.json')) ? rd(r.dir, 'lite_apply_job.json') : null, man: fs.existsSync(path.join(r.dir, 'update_manifest.json')) ? rd(r.dir, 'update_manifest.json') : null };
  };
  let u = unixRig('lx-ok'); let ur = await runUnix(u, 'good', '/usr/bin/other\n/sbin/init');
  check('linux: offers the .sh installer, not the Windows .exe', ur.man?.latest_version === '0.2.0' && /setup\.sh$/.test(ur.man?.staged_file || ''), JSON.stringify(ur.man));
  check('linux: job carries the platform and the Lite binary without .exe', ur.job?.platform === 'linux' && path.basename(ur.job?.exe || '') === 'PinguinoLite', JSON.stringify(ur.job));
  check('linux: apply installs, backs up first and reports ok', ur.res?.ok === true && fs.readFileSync(path.join(u.inst, 'version.txt'), 'utf8') === 'new' && fs.readdirSync(path.join(u.dir, 'backup')).length === 1, JSON.stringify(ur.res));
  u = unixRig('lx-run'); ur = await runUnix(u, 'good', '/usr/bin/other\n/opt/PinguinoLite/PinguinoLite');
  await sleep(500);
  check('linux: process list shows Lite still open -> waits, gives up, nothing changed', ur.res?.ok === false && /did not close/.test(ur.res.message) && fs.readFileSync(path.join(u.inst, 'version.txt'), 'utf8') === 'old', JSON.stringify(ur.res));
  u = unixRig('lx-bad'); ur = await runUnix(u, 'bad');
  check('linux: failing installer -> old version put back', ur.res?.ok === false && /put back/.test(ur.res.message) && fs.readFileSync(path.join(u.inst, 'version.txt'), 'utf8') === 'old', JSON.stringify(ur.res));
  u = unixRig('lx-name'); fs.renameSync(u.f, path.join(u.dir, 'staging', 'PinguinoLite-0.2.0-setup.exe.x')); fs.rmSync(u.f + '.sha256');
  ur = await runUnix(u, 'good'); await sleep(300);
  check('linux: with only a Windows .exe staged the apply is refused', ur.res === null && !fs.existsSync(path.join(u.dir, 'lite_apply_job.json')));
  process.env.PINGUINO_LITE_PLATFORM = 'win32';
  u = unixRig('win-sh'); fs.rmSync(path.join(u.dir, 'staging', 'PinguinoLite-0.3.0-setup.exe')); fs.rmSync(path.join(u.dir, 'staging', 'PinguinoLite-0.3.0-setup.exe.sha256'));
  const lw = createLite({ dir: u.dir, modulesRoot: mods, getHealth: async () => true }); await lw.start(); lw.stop();
  check('windows: a .sh installer is never offered', !fs.existsSync(path.join(u.dir, 'update_manifest.json')));
  delete process.env.PINGUINO_LITE_PLATFORM;
} finally { await sleep(500); try { fs.rmSync(tmp, { recursive: true, force: true }); } catch {} }
const failed = results.filter(x => !x).length; console.log(failed ? `\n${failed} FAILED` : '\nAll Lite apply checks passed'); process.exit(failed ? 1 : 0);
