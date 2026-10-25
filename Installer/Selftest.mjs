// INDEX Selftest.mjs: one-command release self-test. In a fresh temp folder it builds two SIGNED releases (1.0.0, 1.0.1) from a tiny fake tree,
// installs lite-minimal, checks/applies/verifies/rolls back, tries tampered releases, a failed swap, repair and the moving uninstall, and prints PASS/FAIL per step.
// node Installer/Selftest.mjs [--work <folder for the temp files>] [--keep] [--quiet]
// Safe by construction: everything lives in the temp folder (removed at the end unless --keep); the real tree is read only for the updater/installer code;
// the Host "live" probe is pointed at a closed port; port 8760 and the real install are never contacted. No network, no launching, no pushes.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { generateKeyPair } from '../Suite/updater/lib/sign.mjs';
import { plan as rebuildPlan, steps as rebuildSteps } from './Rebuild-Plan.mjs';
import { install as safeOut } from '../Suite/tools/safe_print.mjs'; safeOut();

const HERE = path.dirname(fileURLToPath(import.meta.url)), ROOT = path.resolve(HERE, '..');
const args = process.argv.slice(2), opt = n => { const i = args.indexOf('--' + n); return i >= 0 ? args[i + 1] : undefined; }, has = n => args.includes('--' + n);
const base = path.resolve(opt('work') || os.tmpdir());
if (path.resolve(base).toLowerCase().startsWith(ROOT.toLowerCase() + path.sep)) { console.error('Refusing: --work must be outside the repo.'); process.exit(2); }
fs.mkdirSync(base, { recursive: true });
const W = fs.mkdtempSync(path.join(base, 'pinguino-selftest-'));
const ENV = { ...process.env, PINGUINO_LIVE_URL: 'http://127.0.0.1:59998/api/live' };   // refused connection = "not live"; the real Host (8770) is never asked
const CORE_PORT = '59999';   // updater `--core-port`: a port nothing listens on, so a real Suite on 8760 can never be mistaken for the test

const results = [];
let failed = 0;
function step(name, fn) {
  let ok = false, note = '';
  try { const r = fn(); ok = r === true || r === undefined; note = typeof r === 'string' ? r : ''; if (typeof r === 'string') ok = false; }
  catch (e) { note = String(e && e.message || e).split('\n')[0]; }
  results.push({ name, ok, note }); if (!ok) failed++;
  if (!has('quiet')) console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${ok ? '' : '  -> ' + note}`);
}
const must = (cond, msg) => { if (!cond) throw new Error(msg); };
const node = (script, a) => {
  const r = spawnSync(process.execPath, [script, ...a], { env: ENV, encoding: 'utf8', timeout: 120000, cwd: W });
  const lines = String(r.stdout).trim().split('\n').filter(Boolean);
  let json = null; try { json = JSON.parse(lines[lines.length - 1]); } catch {}
  return { code: r.status, json, out: r.stdout, err: r.stderr };
};
const cp = (src, dst) => fs.cpSync(src, dst, { recursive: true });
const wr = (root, rel, txt) => { const f = path.join(root, rel); fs.mkdirSync(path.dirname(f), { recursive: true }); fs.writeFileSync(f, txt); };
const rd = f => JSON.parse(fs.readFileSync(f, 'utf8'));
const count = d => { let n = 0; (function w(x) { for (const e of fs.readdirSync(x, { withFileTypes: true })) e.isDirectory() ? w(path.join(x, e.name)) : n++; })(d); return n; };

// ---- fake tree: real updater + installer code, fake everything else ----
const tree = path.join(W, 'tree');
for (const rel of ['Suite/updater', 'Installer/install.mjs', 'Installer/prereqs.mjs']) cp(path.join(ROOT, rel), path.join(tree, rel));
fs.rmSync(path.join(tree, 'Suite/updater/test'), { recursive: true, force: true });
const fake = {
  'Suite/suite/suite.py': 'print("suite")', 'Suite/modules.json': '{}', 'Suite/requirements.txt': '', 'Suite/README.md': 'readme',
  'Suite/modules/link/link.py': 'LINK = "one"', 'Suite/modules/link/util.py': 'util',
  'Suite/modules/listen/listen.py': 'LISTEN = "one"', 'Suite/modules/multi/multi.py': 'MULTI = "one"',
  'PinguinoHost/bin/Release/net8.0/PinguinoHost.dll': 'host-dll',
  'App/src-tauri/target/release/binaries/pinguino-core.exe': 'core-exe', 'App/src-tauri/target/release/pinguino-suite.exe': 'shell-exe',
  'PinguinoLite/src-tauri/target/release/pinguino-lite.exe': 'lite-exe', 'PinguinoLite/Start-Lite.bat': '@echo lite',
  'App/Setup-Suite.ps1': '#', 'App/Update-Module.ps1': '#', 'PinguinoApp/PinguinoApp.bat': '@echo app', 'Docs/INSTALL.md': 'docs', 'README.md': 'readme',
};
for (const [k, v] of Object.entries(fake)) wr(tree, k, v);

const seedFile = path.join(W, 'signing-seed.txt'), rel100 = path.join(W, 'rel-1.0.0'), rel101 = path.join(W, 'rel-1.0.1'), inst = path.join(W, 'install');
const BR = path.join(HERE, 'Build-Release.mjs'), IN = path.join(HERE, 'install.mjs');
const UP = (dir = inst) => path.join(dir, 'Suite', 'updater', 'updater.mjs');
const upd = (cmd, a = []) => node(UP(), [cmd, '--install', inst, '--core-port', CORE_PORT, ...a]);
let key;

try {
  step('make a throwaway signing key (not saved anywhere but the temp folder)', () => { key = generateKeyPair(); fs.writeFileSync(seedFile, key.seed + '\n'); must(key.pubkey && key.seed, 'no key'); });
  step('build release 1.0.0, signed', () => {
    const r = node(BR, ['--root', tree, '--version', '1.0.0', '--out', rel100, '--sign-key', seedFile]);
    must(r.json && r.json.ok, 'Build-Release failed: ' + (r.err || r.out).slice(0, 200)); must(fs.existsSync(path.join(rel100, 'manifest.sig')) && fs.existsSync(path.join(rel100, 'suite-1.0.0.zip')), 'release files missing');
  });
  step('build release 1.0.1, signed, with release notes', () => {
    wr(tree, 'Suite/modules/link/link.py', 'LINK = "two"'); wr(tree, 'Suite/modules/link/extra.py', 'new file in 1.0.1');
    wr(W, 'notes.txt', 'Suite:\n- Link got a second version\n');
    const r = node(BR, ['--root', tree, '--version', '1.0.1', '--out', rel101, '--sign-key', seedFile, '--notes-file', path.join(W, 'notes.txt')]);
    must(r.json && r.json.ok, 'Build-Release failed: ' + (r.err || r.out).slice(0, 200));
    const m = rd(path.join(rel101, 'manifest.json')); must(/second version/.test(m.notes), 'notes not in manifest'); must(m.components && m.components.link, 'no per-part hashes');
  });
  step('install lite-minimal from 1.0.0 (signed, key recorded)', () => {
    const r = node(IN, ['--target', inst, '--local', rel100, '--pubkey', key.pubkey, '--profile', 'lite-minimal']);
    must(r.json && r.json.ok, 'install failed: ' + (r.json ? r.json.message : r.err).slice(0, 200));
    const j = rd(path.join(inst, 'install.json'));
    must(j.profile === 'lite-minimal' && j.version === '1.0.0' && j.pubkey === key.pubkey, 'install.json wrong: ' + JSON.stringify(j).slice(0, 200));
    must(JSON.stringify(j.parts) === JSON.stringify(['lite', 'link', 'tools']), 'parts wrong');
    must(fs.existsSync(path.join(inst, 'PinguinoLite/Start-Lite.bat')) && fs.existsSync(path.join(inst, 'Suite/modules/link/link.py')), 'lite/link files missing');
    must(!fs.existsSync(path.join(inst, 'Suite/modules/listen')) && !fs.existsSync(path.join(inst, 'PinguinoHost')), 'a part that is not in the profile was installed');
  });
  const src = s => ['--source', s];
  step('check against 1.0.1: update available, only link changed', () => {
    const r = upd('check', src(rel101)); must(r.json && r.json.ok && r.json.available && r.json.version === '1.0.1', 'no update offered: ' + r.out.slice(0, 200));
    const ch = r.json.components.filter(c => c.changed).map(c => c.id); must(JSON.stringify(ch) === '["link"]', 'changed parts: ' + ch);
  });
  step('verify the fresh 1.0.0 install against 1.0.0', () => { const r = upd('verify', src(rel100)); must(r.json && r.json.ok, 'verify not ok: ' + r.out.slice(0, 200)); });
  step('apply 1.0.1 (backup made, link updated, Data kept)', () => {
    wr(inst, 'Data/keep.txt', 'my data');
    const r = upd('apply', src(rel101)); must(r.json && r.json.ok && !r.json.deferred, 'apply failed: ' + r.out.slice(0, 250));
    must(rd(path.join(inst, 'install.json')).version === '1.0.1', 'version not 1.0.1'); must(fs.readFileSync(path.join(inst, 'Suite/modules/link/link.py'), 'utf8') === 'LINK = "two"', 'link.py not updated');
    must(fs.readFileSync(path.join(inst, 'Data/keep.txt'), 'utf8') === 'my data', 'Data changed'); must(fs.readdirSync(path.join(inst, 'Data/updates/backup')).length >= 1, 'no backup');
  });
  step('verify against 1.0.1 after the update', () => { const r = upd('verify', src(rel101)); must(r.json && r.json.ok, 'verify not ok: ' + r.out.slice(0, 200)); });
  step('roll back to 1.0.0 and verify it', () => {
    const r = upd('rollback'); must(r.json && r.json.ok, 'rollback failed: ' + r.out.slice(0, 200));
    must(rd(path.join(inst, 'install.json')).version === '1.0.0', 'version not 1.0.0'); must(!fs.existsSync(path.join(inst, 'Suite/modules/link/extra.py')), 'file created by 1.0.1 still there');
    const v = upd('verify', src(rel100)); must(v.json && v.json.ok, 'verify after rollback not ok: ' + v.out.slice(0, 200));
  });

  const clearStaging = () => fs.rmSync(path.join(inst, 'Data/updates/staging'), { recursive: true, force: true });
  const refused = (r, re) => { must(r.json && r.json.ok === false, 'was NOT refused: ' + r.out.slice(0, 200)); must(re.test(r.json.message || ''), 'wrong reason: ' + r.json.message); must(rd(path.join(inst, 'install.json')).version === '1.0.0', 'install changed'); must(fs.readFileSync(path.join(inst, 'Suite/modules/link/link.py'), 'utf8') === 'LINK = "one"', 'file changed'); };
  step('tamper: flipped bytes inside the zip are refused', () => {
    clearStaging(); const bad = path.join(W, 'bad-zip'); cp(rel101, bad); const z = path.join(bad, 'suite-1.0.1.zip'), b = fs.readFileSync(z);
    for (let i = 0; i < 8; i++) b[Math.floor(b.length / 2) + i] ^= 0xff; fs.writeFileSync(z, b);
    refused(upd('apply', src(bad)), /sha256|check|corrupt|size/i);
  });
  step('tamper: manifest edited after signing is refused', () => {
    clearStaging(); const bad = path.join(W, 'bad-manifest'); cp(rel101, bad); const m = rd(path.join(bad, 'manifest.json')); m.notes = 'edited'; fs.writeFileSync(path.join(bad, 'manifest.json'), JSON.stringify(m, null, 2));
    refused(upd('apply', src(bad)), /signature/i);
  });
  step('tamper: manifest.sig removed is refused (a key is configured)', () => {
    clearStaging(); const bad = path.join(W, 'bad-nosig'); cp(rel101, bad); fs.rmSync(path.join(bad, 'manifest.sig'));
    refused(upd('apply', src(bad)), /not signed|signature/i);
  });
  step('tamper: a release signed with a different key is refused', () => {
    clearStaging(); const other = generateKeyPair(), seed2 = path.join(W, 'other-seed.txt'); fs.writeFileSync(seed2, other.seed + '\n');
    const bad = path.join(W, 'bad-key'); const r0 = node(BR, ['--root', tree, '--version', '1.0.1', '--out', bad, '--sign-key', seed2]); must(r0.json && r0.json.ok, 'could not build the wrong-key release');
    refused(upd('apply', src(bad)), /signature/i);
  });
  step('failed swap (file cannot be written) puts 1.0.0 back and verify is ok', () => {
    clearStaging(); fs.mkdirSync(path.join(inst, 'Suite/modules/link/util.py.pinguino-new'), { recursive: true });   // a folder where the temp file must go
    const r = upd('apply', src(rel101)); must(r.json && r.json.ok === false && /put back/.test(r.json.message), 'expected a restored failure: ' + r.out.slice(0, 250));
    fs.rmSync(path.join(inst, 'Suite/modules/link/util.py.pinguino-new'), { recursive: true });
    must(rd(path.join(inst, 'install.json')).version === '1.0.0' && !fs.existsSync(path.join(inst, 'Suite/modules/link/extra.py')), 'not back on 1.0.0');
    const v = upd('verify', src(rel100)); must(v.json && v.json.ok, 'verify after failed swap not ok: ' + v.out.slice(0, 200));
  });
  step('the good release applies right after all that', () => {
    clearStaging(); const r = upd('apply', src(rel101)); must(r.json && r.json.ok, 'apply failed: ' + r.out.slice(0, 250)); must(rd(path.join(inst, 'install.json')).version === '1.0.1', 'version not 1.0.1');
    const c = upd('check', src(rel101)); must(c.json && c.json.available === false, 'still offering an update');
  });
  step('repair: a deleted file is detected by verify and restored by --repair', () => {
    fs.rmSync(path.join(inst, 'Suite/modules/link/util.py'));
    const v = upd('verify', src(rel101)); must(v.json && v.json.ok === false || (v.json && JSON.stringify(v.json).includes('missing')), 'verify did not notice the missing file: ' + v.out.slice(0, 200));
    const r = node(IN, ['--target', inst, '--repair', '--source', rel101]); must(r.json && r.json.ok, 'repair failed: ' + (r.json ? r.json.message : r.err));
    must(fs.readFileSync(path.join(inst, 'Suite/modules/link/util.py'), 'utf8') === 'util', 'file not restored');
    const v2 = upd('verify', src(rel101)); must(v2.json && v2.json.ok, 'verify after repair not ok: ' + v2.out.slice(0, 200));
  });
  step('uninstall: plain run only lists, --yes MOVES everything but Data (nothing deleted)', () => {
    const before = count(inst) - count(path.join(inst, 'Data'));
    const dry = node(IN, ['--target', inst, '--uninstall']); must(dry.json && dry.json.ok && fs.existsSync(path.join(inst, 'install.json')), 'dry run changed something or failed: ' + dry.out.slice(0, 200));
    const r = node(IN, ['--target', inst, '--uninstall', '--yes']); must(r.json && r.json.ok, 'uninstall failed: ' + (r.json ? r.json.message : r.err));
    must(!fs.existsSync(path.join(inst, 'install.json')) && !fs.existsSync(path.join(inst, 'PinguinoLite')), 'install not moved away');
    must(fs.readFileSync(path.join(inst, 'Data/keep.txt'), 'utf8') === 'my data', 'Data was touched');
    const ej = path.join(inst, 'Data/updates/ejected'), dirs = fs.existsSync(ej) ? fs.readdirSync(ej).filter(n => n.startsWith('uninstall-')) : [];
    must(dirs.length === 1, 'no dated ejected folder'); const moved = count(path.join(ej, dirs[0]));
    must(moved >= before, `only ${moved} of ${before} files were moved`);
  });
  step('Rebuild-Plan: path rules put each commit in the right group, builds newer than a commit drop it', () => {
    const c = (hash, time, ...files) => ({ hash, time, subject: hash, files });
    const g = rebuildPlan([c('a', 200, 'App/src/index.html'), c('b', 200, 'Suite/suite/suite.py', 'Docs/x.md'), c('c', 200, 'Suite/modules.json'), c('d', 200, 'Suite/modules/listen/listen.py'),
      c('e', 200, 'PinguinoLite/src/index.html'), c('f', 200, 'PinguinoLite/test/rows.test.mjs', 'Suite/tests/test_x.py'), c('g', 50, 'App/src-tauri/src/main.rs'), c('h', 200, 'PinguinoHost/Foo.cs')], { shell: 100, core: 100, host: 100, modules: 100, lite: 100 }, 100);
    const ids = k => g[k].map(x => x.hash).join('');
    must(ids('shell') === 'a' && ids('core') === 'bc' && ids('modules') === 'd' && ids('lite') === 'e' && ids('host') === 'h' && ids('none') === 'f', JSON.stringify(Object.fromEntries(Object.keys(g).map(k => [k, ids(k)]))));
    must(rebuildSteps({ groups: Object.fromEntries(Object.keys(g).map(k => [k, []])) })[0] === 'Nothing to rebuild or restart.', 'empty plan not recognised');
    must(rebuildSteps({ groups: { ...Object.fromEntries(Object.keys(g).map(k => [k, []])), core: g.core } }).some(x => /--force/.test(x)), 'core step lacks --force');
  });
  // ---- a FULL profile install (this PC's kind) in its own folder, from the same fake tree: every part, no `parts` list ----
  const inst2 = path.join(W, 'install-full'), upd2 = (cmd, a = []) => node(UP(inst2), [cmd, '--install', inst2, '--core-port', CORE_PORT, ...a]);
  step('install the full profile from 1.0.0: every part present, no parts list, key recorded', () => {
    const r = node(IN, ['--target', inst2, '--local', rel100, '--pubkey', key.pubkey, '--profile', 'full']);
    must(r.json && r.json.ok, 'install failed: ' + (r.json ? r.json.message : r.err).slice(0, 200));
    const j = rd(path.join(inst2, 'install.json'));
    must(j.profile === 'full' && j.version === '1.0.0' && j.pubkey === key.pubkey && !('parts' in j), 'install.json wrong: ' + JSON.stringify(j).slice(0, 200));
    for (const f of ['Suite/suite/suite.py', 'Suite/modules.json', 'Suite/modules/link/link.py', 'Suite/modules/listen/listen.py', 'Suite/modules/multi/multi.py', 'PinguinoHost/bin/Release/net8.0/PinguinoHost.dll',
      'App/src-tauri/target/release/pinguino-suite.exe', 'PinguinoLite/Start-Lite.bat', 'App/Setup-Suite.ps1', 'Docs/INSTALL.md']) must(fs.existsSync(path.join(inst2, f)), 'missing in a full install: ' + f);
    const ids = Object.keys(j.components || {}); for (const id of ['lite', 'link', 'listen', 'multi']) must(ids.includes(id), 'part not recorded: ' + id + ' (have ' + ids + ')');
    const v = upd2('verify', src(rel100)); must(v.json && v.json.ok, 'verify not ok: ' + v.out.slice(0, 200));
  });
  step('full install: check shows the release notes, only link changed, nothing optional', () => {
    const r = upd2('check', src(rel101)); must(r.json && r.json.ok && r.json.available && r.json.version === '1.0.1' && r.json.profile === 'full', 'no update offered: ' + r.out.slice(0, 200));
    must(/second version/.test(r.json.notes), 'notes missing from check: ' + JSON.stringify(r.json.notes));
    const ch = r.json.components.filter(c => c.changed).map(c => c.id); must(JSON.stringify(ch) === '["link"]', 'changed parts: ' + ch);
    must(!r.json.optional || r.json.optional.length === 0, 'full install lists optional parts: ' + JSON.stringify(r.json.optional));
  });
  step('full install: apply 1.0.1 touches only link, other modules and Data stay byte-identical', () => {
    wr(inst2, 'Data/mine.txt', 'full data'); const before = fs.readFileSync(path.join(inst2, 'Suite/modules/listen/listen.py'), 'utf8');
    const r = upd2('apply', src(rel101)); must(r.json && r.json.ok && !r.json.deferred, 'apply failed: ' + r.out.slice(0, 250));
    must(rd(path.join(inst2, 'install.json')).version === '1.0.1', 'version not 1.0.1');
    must(fs.readFileSync(path.join(inst2, 'Suite/modules/link/link.py'), 'utf8') === 'LINK = "two"', 'link.py not updated');
    must(fs.readFileSync(path.join(inst2, 'Suite/modules/listen/listen.py'), 'utf8') === before, 'listen changed');
    must(fs.readFileSync(path.join(inst2, 'Data/mine.txt'), 'utf8') === 'full data', 'Data changed');
    const v = upd2('verify', src(rel101)); must(v.json && v.json.ok, 'verify after apply not ok: ' + v.out.slice(0, 200));
  });
  step('manifest notes: long notes are cut to 2000 characters, signature still valid; no --notes-file = short default text', () => {
    wr(W, 'long-notes.txt', 'Suite:\n' + '- a very long line of notes that goes on and on\n'.repeat(120));
    const out = path.join(W, 'rel-notes'), r = node(BR, ['--root', tree, '--version', '1.0.2', '--out', out, '--sign-key', seedFile, '--notes-file', path.join(W, 'long-notes.txt')]);
    must(r.json && r.json.ok, 'Build-Release refused long notes: ' + (r.err || r.out).slice(0, 200));
    const m = rd(path.join(out, 'manifest.json')); must(String(m.notes || '').length <= 2000, 'notes not capped: ' + String(m.notes || '').length);
    const c = upd2('check', src(out)); must(c.json && c.json.ok && c.json.version === '1.0.2' && String(c.json.notes).length <= 2000 && c.json.notes.length > 100, 'check of the long-notes release: ' + c.out.slice(0, 200));
    const out2 = path.join(W, 'rel-nonotes'), r2 = node(BR, ['--root', tree, '--version', '1.0.3', '--out', out2, '--sign-key', seedFile]); must(r2.json && r2.json.ok, 'build without notes failed');
    const c2 = upd2('check', src(out2)); must(c2.json && c2.json.ok && String(c2.json.notes || '').length < 100, 'default notes too long: ' + JSON.stringify(c2.json && c2.json.notes));
  });
} finally {
  const keep = has('keep');
  if (!keep) { try { fs.rmSync(W, { recursive: true, force: true }); } catch {} }
  const pass = results.filter(r => r.ok).length;
  console.log(`\n${failed ? 'FAIL' : 'PASS'}: ${pass}/${results.length} steps passed${keep ? `; files kept in ${W}` : '; temp folder removed'}`);
  process.exitCode = failed ? 1 : 0;
}
