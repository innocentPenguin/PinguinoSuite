// Local install/update/uninstall/rollback with real zips in a temp folder. Run: node src/pkgcheck.mjs
process.env.PINGUINO_NEVER_REAL_OBS = '1';   // tests must never reach the real OBS
import fs from 'node:fs'; import os from 'node:os'; import path from 'node:path'; import zlib from 'node:zlib'; import crypto from 'node:crypto';
import { createLite } from './lite.mjs';
const results = []; const check = (n, ok, x = '') => { results.push(ok); console.log(`${ok ? 'PASS' : 'FAIL'}  ${n}${ok ? '' : '  ' + x}`); };

/** Minimal zip writer (deflate) for tests. entries: {name: string} */
function makeZip(entries) {
  const parts = [], cd = []; let off = 0, n = 0;
  for (const [name, content] of Object.entries(entries)) {
    const data = Buffer.from(content), comp = zlib.deflateRawSync(data), nm = Buffer.from(name), crc = zlib.crc32(data);
    const lh = Buffer.alloc(30); lh.writeUInt32LE(0x04034b50, 0); lh.writeUInt16LE(20, 4); lh.writeUInt16LE(8, 8); lh.writeUInt32LE(crc, 14); lh.writeUInt32LE(comp.length, 18); lh.writeUInt32LE(data.length, 22); lh.writeUInt16LE(nm.length, 26);
    parts.push(lh, nm, comp);
    const ch = Buffer.alloc(46); ch.writeUInt32LE(0x02014b50, 0); ch.writeUInt16LE(20, 4); ch.writeUInt16LE(20, 6); ch.writeUInt16LE(8, 10); ch.writeUInt32LE(crc, 16); ch.writeUInt32LE(comp.length, 20); ch.writeUInt32LE(data.length, 24); ch.writeUInt16LE(nm.length, 28); ch.writeUInt32LE(off, 42);
    cd.push(ch, nm); off += 30 + nm.length + comp.length; n++;
  }
  const cdb = Buffer.concat(cd), end = Buffer.alloc(22); end.writeUInt32LE(0x06054b50, 0); end.writeUInt16LE(n, 8); end.writeUInt16LE(n, 10); end.writeUInt32LE(cdb.length, 12); end.writeUInt32LE(off, 16);
  return Buffer.concat([...parts, cdb, end]);
}
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'plink-pkg-')), mods = path.join(tmp, 'modules'), dir = path.join(tmp, 'lite'), pk = path.join(dir, 'packages');
fs.mkdirSync(mods, { recursive: true }); fs.mkdirSync(pk, { recursive: true });
const put = (id, ver, entries, hash = true) => { const z = makeZip(entries), f = path.join(pk, `${id}-${ver}.zip`); fs.writeFileSync(f, z); if (hash) fs.writeFileSync(f + '.sha256', crypto.createHash('sha256').update(z).digest('hex') + `  ${id}-${ver}.zip\n`); };
const mj = (id, v) => JSON.stringify({ id, name: id, desc: 'test', version: v, port: 59999 });
const rd = f => JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8'));
const rf = (...p) => fs.readFileSync(path.join(mods, ...p), 'utf8');
const req = async (n, action, id) => { fs.mkdirSync(path.join(dir, 'requests'), { recursive: true }); fs.writeFileSync(path.join(dir, 'requests', `${n}-${action}-${id.replace(/\W/g, '_')}.json`), JSON.stringify({ schema: 1, action, id })); await lite.poll(); };
let running = false;
const lite = createLite({ dir, modulesRoot: mods, getHealth: async () => running });
try {
  await lite.start();
  put('demo', '1.0.0', { 'module.json': mj('demo', '1.0.0'), 'src/a.js': 'a1' });
  await lite.refresh();
  check('catalog shows the package with sha256 + package path', rd('modules_catalog.json').modules.find(m => m.id === 'demo')?.sha256?.length === 64);
  await req(1, 'install', 'demo');
  check('install unpacks into modules/demo', rf('demo', 'src', 'a.js') === 'a1' && rd('installed.json').modules.demo.version === '1.0.0' && rd('update_status.json').result === 'ok');
  await req(2, 'install', 'demo');
  check('installing again is refused', /already installed/.test(rd('installed.json').modules.demo.error || ''));
  fs.mkdirSync(path.join(mods, 'demo', 'data'), { recursive: true }); fs.writeFileSync(path.join(mods, 'demo', 'data', 'keep.db'), 'user data');
  put('demo', '1.1.0', { 'module.json': mj('demo', '1.1.0'), 'src/a.js': 'a2' });
  running = true; await req(3, 'update', 'demo');
  check('update of a RUNNING module is refused', /stop it first/.test(rd('installed.json').modules.demo.error || '') && rf('demo', 'src', 'a.js') === 'a1');
  running = false; await req(4, 'update', 'demo');
  check('update swaps files, keeps data/, error cleared', rf('demo', 'src', 'a.js') === 'a2' && rf('demo', 'data', 'keep.db') === 'user data' && !rd('installed.json').modules.demo.error && rd('installed.json').modules.demo.version === '1.1.0');
  check('old version is kept in backup (not deleted)', fs.readdirSync(path.join(dir, 'backup')).some(n => n.startsWith('demo-')));
  await req(5, 'rollback', 'demo');
  check('rollback restores 1.0.0', rf('demo', 'src', 'a.js') === 'a1' && rd('installed.json').modules.demo.version === '1.0.0');
  await req(6, 'uninstall', 'demo');
  check('uninstall moves the folder to backup', !fs.existsSync(path.join(mods, 'demo')) && !rd('installed.json').modules.demo);
  put('evil', '1.0.0', { 'module.json': mj('evil', '1.0.0'), '../outside.txt': 'x' });
  await req(7, 'install', 'evil');
  check('zip path escape is refused and nothing is written outside', /unsafe path/.test(rd('update_status.json').error || '') && !fs.existsSync(path.join(mods, 'outside.txt')) && !fs.existsSync(path.join(mods, 'evil')));
  put('nohash', '1.0.0', { 'module.json': mj('nohash', '1.0.0') }, false);
  await req(8, 'install', 'nohash');
  check('package without .sha256 is refused', /no \.sha256/.test(rd('update_status.json').error || '') && !fs.existsSync(path.join(mods, 'nohash')));
  put('tamper', '1.0.0', { 'module.json': mj('tamper', '1.0.0') });
  fs.appendFileSync(path.join(pk, 'tamper-1.0.0.zip'), 'junk');
  await req(9, 'install', 'tamper');
  check('changed package (hash mismatch) is refused', /hash does not match/.test(rd('update_status.json').error || '') && !fs.existsSync(path.join(mods, 'tamper')));
  put('wrongid', '1.0.0', { 'module.json': mj('other', '1.0.0') });
  await req(10, 'install', 'wrongid');
  check('package whose module.json id differs is refused', /id does not match/.test(rd('update_status.json').error || '') && !fs.existsSync(path.join(mods, 'wrongid')) && !fs.existsSync(path.join(mods, '.staging')));
  await req(11, 'install', 'link');
  check('install of link is refused', /Link/.test(rd('update_status.json').error || ''));
  await req(12, 'uninstall', '..');
  check('bad id is refused', /bad module id/.test(rd('update_status.json').error || ''));
  const { packModule } = await import('./pkg.mjs');
  fs.mkdirSync(path.join(mods, 'mine', 'data'), { recursive: true });
  fs.writeFileSync(path.join(mods, 'mine', 'module.json'), mj('mine', '2.0.0')); fs.writeFileSync(path.join(mods, 'mine', 'run.js'), 'ok'); fs.writeFileSync(path.join(mods, 'mine', 'data', 'secret.db'), 'private');
  const packed = packModule({ liteDir: dir, modulesRoot: mods, id: 'mine' });
  check('pack makes zip + sha256 and leaves out data/', packed.files === 2 && fs.existsSync(packed.file + '.sha256'));
  fs.renameSync(path.join(mods, 'mine'), path.join(tmp, 'mine-moved'));
  await req(13, 'install', 'mine');
  check('a packed module installs back (round trip) without data/', rf('mine', 'run.js') === 'ok' && !fs.existsSync(path.join(mods, 'mine', 'data')));
  let noVer = ''; try { fs.mkdirSync(path.join(mods, 'nover')); fs.writeFileSync(path.join(mods, 'nover', 'module.json'), JSON.stringify({ id: 'nover' })); packModule({ liteDir: dir, modulesRoot: mods, id: 'nover' }); } catch (e) { noVer = e.message; }
  check('pack refuses a module without a version', /version/.test(noVer));
  check('busy is clear when done', Object.keys(rd('status.json').busy).length === 0);
  lite.stop();
} finally { fs.rmSync(tmp, { recursive: true, force: true }); }
const failed = results.filter(r => !r).length; console.log(failed ? `\n${failed} FAILED` : '\nAll package checks passed'); process.exit(failed ? 1 : 0);
