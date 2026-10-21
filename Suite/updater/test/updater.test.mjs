// Updater tests: everything runs in temp dirs, never against a real install.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { writeZip, readZip } from '../lib/zip.mjs';
import { applyUpdate, sha256, dirs, rollbackLatest } from '../lib/apply.mjs';
import { safeRel } from '../lib/paths.mjs';
import { cmpVersion, parseManifest } from '../lib/manifest.mjs';
import { gitStatus, gitUpdate } from '../lib/sources.mjs';

const tmp = p => fs.mkdtempSync(path.join(os.tmpdir(), p));
const B = s => Buffer.from(s);
const notLive = async () => ({ live: false });

function makeInstall(version = '1.0.0', files = { 'App/app.txt': 'old app', 'Suite/core.txt': 'old core' }) {
  const d = tmp('inst-');
  for (const [k, v] of Object.entries(files)) { fs.mkdirSync(path.dirname(path.join(d, k)), { recursive: true }); fs.writeFileSync(path.join(d, k), v); }
  fs.mkdirSync(path.join(d, 'Data'), { recursive: true }); fs.writeFileSync(path.join(d, 'Data', 'keep.txt'), 'my data');
  fs.writeFileSync(path.join(d, 'install.json'), JSON.stringify({ schema: 1, version, channel: 'stable' }));
  return d;
}
function makeRelease(version, entries, { badHash = false, channel = 'stable' } = {}) {
  const d = tmp('rel-'), zip = writeZip(entries.map(([name, data]) => ({ name, data: B(data) })));
  const name = `suite-${version}.zip`; fs.writeFileSync(path.join(d, name), zip);
  fs.writeFileSync(path.join(d, 'manifest.json'), JSON.stringify({ schema: 1, channel, version, files: [{ name, size: zip.length, sha256: badHash ? 'a'.repeat(64) : sha256(zip), url: name }] }));
  return d;
}
const read = (d, rel) => fs.readFileSync(path.join(d, rel), 'utf8');

test('versions compare numerically', () => { assert.equal(cmpVersion('0.10.0', '0.9.2'), 1); assert.equal(cmpVersion('1.0', '1.0.0'), 0); assert.equal(cmpVersion('1.2.3', '1.10'), -1); });

test('zip round trip', () => { const z = writeZip([{ name: 'a/b.txt', data: B('hello'.repeat(50)) }, { name: 'c.bin', data: Buffer.from([1, 2, 3]) }]); const e = readZip(z); assert.equal(e[0].data().toString(), 'hello'.repeat(50)); assert.deepEqual([...e[1].data()], [1, 2, 3]); });

test('safeRel refuses escapes, drives, Data, secrets but allows vault.py', () => {
  for (const bad of ['../x', 'a/../../x', '/abs', 'C:/x', 'a\\b', 'Data/x.json', 'data/x', '.venv/x', 'Suite/.env', 'x/tokens.json', 'k.pem', 'a/./b', 'a/b ']) assert.throws(() => safeRel(bad), undefined, bad);
  assert.equal(safeRel('Suite/suite/vault.py'), 'Suite/suite/vault.py');
  assert.equal(safeRel('App/src/index.html'), 'App/src/index.html');
});

test('manifest needs sha256, sane names, a known schema', () => {
  assert.throws(() => parseManifest('{"schema":2}'));
  assert.throws(() => parseManifest(JSON.stringify({ schema: 1, version: '1.0', files: [{ name: '../x.zip', size: 1, sha256: 'a'.repeat(64) }] })));
  assert.throws(() => parseManifest(JSON.stringify({ schema: 1, version: '1.0', files: [{ name: 'x.zip', size: 1 }] })));
  assert.throws(() => parseManifest(JSON.stringify({ schema: 1, version: '1.0', min_updater: 9, files: [{ name: 'x.zip', size: 1, sha256: 'a'.repeat(64) }] })));
});

test('applies a newer release, keeps Data, writes backup + result', async () => {
  const inst = makeInstall(), rel = makeRelease('1.1.0', [['App/app.txt', 'new app'], ['App/extra.txt', 'extra']]);
  const r = await applyUpdate({ installDir: inst, source: { type: 'local', path: rel }, current: '1.0.0', liveCheck: notLive });
  assert.equal(r.ok, true, r.message); assert.match(r.message, /1\.0\.0 -> 1\.1\.0/);
  assert.equal(read(inst, 'App/app.txt'), 'new app'); assert.equal(read(inst, 'App/extra.txt'), 'extra'); assert.equal(read(inst, 'Suite/core.txt'), 'old core');
  assert.equal(read(inst, 'Data/keep.txt'), 'my data');
  assert.equal(JSON.parse(read(inst, 'install.json')).version, '1.1.0');
  assert.ok(fs.existsSync(dirs(inst).result));
  // a second run sees it is current
  const again = await applyUpdate({ installDir: inst, source: { type: 'local', path: rel }, current: '1.1.0', liveCheck: notLive });
  assert.equal(again.upToDate, true);
});

test('works from a zip that contains the manifest (USB style)', async () => {
  const inst = makeInstall(), rel = makeRelease('1.1.0', [['App/app.txt', 'new app']]);
  const bundle = path.join(tmp('usb-'), 'release.zip');
  fs.writeFileSync(bundle, writeZip(fs.readdirSync(rel).map(n => ({ name: n, data: fs.readFileSync(path.join(rel, n)) }))));
  const r = await applyUpdate({ installDir: inst, source: { type: 'local', path: bundle }, current: '1.0.0', liveCheck: notLive });
  assert.equal(r.ok, true, r.message); assert.equal(read(inst, 'App/app.txt'), 'new app');
});

test('bad sha256 changes nothing', async () => {
  const inst = makeInstall(), rel = makeRelease('1.1.0', [['App/app.txt', 'new app']], { badHash: true });
  const r = await applyUpdate({ installDir: inst, source: { type: 'local', path: rel }, current: '1.0.0', liveCheck: notLive });
  assert.equal(r.ok, false); assert.match(r.message, /sha256/); assert.equal(read(inst, 'App/app.txt'), 'old app');
});

test('live (or unclear) defers, writes the notice, changes nothing', async () => {
  for (const lv of [{ live: true }, { live: null, why: 'Host did not answer' }]) {
    const inst = makeInstall(), rel = makeRelease('1.1.0', [['App/app.txt', 'new app']]);
    const r = await applyUpdate({ installDir: inst, source: { type: 'local', path: rel }, current: '1.0.0', liveCheck: async () => lv });
    assert.equal(r.deferred, true); assert.equal(read(inst, 'App/app.txt'), 'old app'); assert.ok(fs.existsSync(dirs(inst).deferred));
  }
});

test('path traversal in a release is refused before any file is written', async () => {
  const inst = makeInstall(), rel = makeRelease('1.1.0', [['App/app.txt', 'new app'], ['../evil.txt', 'x']]);
  const r = await applyUpdate({ installDir: inst, source: { type: 'local', path: rel }, current: '1.0.0', liveCheck: notLive });
  assert.equal(r.ok, false); assert.equal(read(inst, 'App/app.txt'), 'old app'); assert.ok(!fs.existsSync(path.join(inst, '..', 'evil.txt')));
});

test('a release may not write into Data', async () => {
  const inst = makeInstall(), rel = makeRelease('1.1.0', [['Data/keep.txt', 'overwritten']]);
  const r = await applyUpdate({ installDir: inst, source: { type: 'local', path: rel }, current: '1.0.0', liveCheck: notLive });
  assert.equal(r.ok, false); assert.equal(read(inst, 'Data/keep.txt'), 'my data');
});

test('a failed post-check restores the exact old bytes and removes new files', async () => {
  const inst = makeInstall(), rel = makeRelease('1.1.0', [['App/app.txt', 'new app'], ['App/extra.txt', 'extra']]);
  const before = sha256(fs.readFileSync(path.join(inst, 'App/app.txt')));
  const r = await applyUpdate({ installDir: inst, source: { type: 'local', path: rel }, current: '1.0.0', liveCheck: notLive, postCheck: async () => false });
  assert.equal(r.ok, false); assert.match(r.message, /put back/);
  assert.equal(sha256(fs.readFileSync(path.join(inst, 'App/app.txt'))), before); assert.ok(!fs.existsSync(path.join(inst, 'App/extra.txt')));
  assert.equal(JSON.parse(read(inst, 'install.json')).version, '1.0.0'); assert.equal(read(inst, 'Data/keep.txt'), 'my data');
});

test('a locked file mid-swap triggers rollback', async () => {
  const inst = makeInstall(), rel = makeRelease('1.1.0', [['App/app.txt', 'new app'], ['Suite/core.txt', 'new core']]);
  fs.mkdirSync(path.join(inst, 'Suite', 'core.txt.pinguino-new')); // a directory where the temp file must go: the write fails on every OS
  const r = await applyUpdate({ installDir: inst, source: { type: 'local', path: rel }, current: '1.0.0', liveCheck: notLive });
  assert.equal(r.ok, false); assert.equal(read(inst, 'App/app.txt'), 'old app'); assert.equal(read(inst, 'Suite/core.txt'), 'old core');
});

test('manual rollback restores the newest backup', async () => {
  const inst = makeInstall(), rel = makeRelease('1.1.0', [['App/app.txt', 'new app']]);
  await applyUpdate({ installDir: inst, source: { type: 'local', path: rel }, current: '1.0.0', liveCheck: notLive });
  assert.equal(read(inst, 'App/app.txt'), 'new app');
  assert.equal(rollbackLatest(inst).ok, true); assert.equal(read(inst, 'App/app.txt'), 'old app'); assert.equal(JSON.parse(read(inst, 'install.json')).version, '1.0.0');
});

test('a held lock stops a second run quietly', async () => {
  const inst = makeInstall(), rel = makeRelease('1.1.0', [['App/app.txt', 'new app']]);
  fs.mkdirSync(dirs(inst).u, { recursive: true }); fs.writeFileSync(dirs(inst).lock, '1');
  const r = await applyUpdate({ installDir: inst, source: { type: 'local', path: rel }, current: '1.0.0', liveCheck: notLive });
  assert.equal(r.skipped, true); assert.equal(read(inst, 'App/app.txt'), 'old app');
});

test('wrong channel is not offered', async () => {
  const inst = makeInstall(), rel = makeRelease('1.1.0', [['App/app.txt', 'new app']], { channel: 'beta' });
  const r = await applyUpdate({ installDir: inst, source: { type: 'local', path: rel }, current: '1.0.0', liveCheck: notLive });
  assert.equal(r.upToDate, true); assert.equal(read(inst, 'App/app.txt'), 'old app');
});

test('git source fast-forwards a clean clone to the newest tag, refuses nothing silently', async (t) => {
  try { execFileSync('git', ['--version'], { stdio: 'ignore' }); } catch { return t.skip('git not installed'); }
  const g = (cwd, ...a) => execFileSync('git', ['-c', 'user.email=t@t', '-c', 'user.name=t', '-c', 'commit.gpgsign=false', ...a], { cwd, stdio: 'pipe' }).toString().trim();
  const origin = tmp('origin-'); g(origin, 'init', '-q'); fs.writeFileSync(path.join(origin, 'f.txt'), 'one'); g(origin, 'add', '.'); g(origin, 'commit', '-qm', 'one'); g(origin, 'tag', 'v1.0.0');
  const clone = tmp('clone-'); fs.rmSync(clone, { recursive: true }); g(os.tmpdir(), 'clone', '-q', origin, clone);
  fs.writeFileSync(path.join(origin, 'f.txt'), 'two'); g(origin, 'commit', '-qam', 'two'); g(origin, 'tag', 'v1.1.0');
  const st = await gitStatus(clone);
  assert.equal(st.isClone, true); assert.equal(st.newest, 'v1.1.0'); assert.equal(st.upToDate, false); assert.equal(st.dirty, false);
  await gitUpdate(clone, st.newest); assert.equal(read(clone, 'f.txt'), 'two');
  assert.equal((await gitStatus(clone)).upToDate, true);
  assert.rejects(() => gitUpdate(clone, 'v1.1.0; rm -rf'), /bad release tag/);
});

// ---- Installer (library + CLI) ----
import { installRelease } from '../lib/install.mjs';
const CLI = path.join(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')), '..', '..', '..', 'Installer', 'install.mjs');

test('installer lays down a release, creates empty Data, writes install.json, never over an install', async () => {
  const rel = makeRelease('2.0.0', [['App/app.txt', 'app'], ['Suite/suite/vault.py', 'code']]), target = path.join(tmp('tgt-'), 'PinguinoSuite');
  const r = await installRelease({ target, source: { type: 'local', path: rel } });
  assert.equal(r.ok, true, r.message); assert.equal(read(target, 'App/app.txt'), 'app'); assert.equal(fs.readdirSync(path.join(target, 'Data', 'runtime')).length, 0);
  const inst = JSON.parse(read(target, 'install.json')); assert.equal(inst.version, '2.0.0'); assert.equal(inst.source.type, 'local');
  assert.equal((await installRelease({ target, source: { type: 'local', path: rel } })).ok, false);
});

test('installer refuses a non-empty folder, a bad hash, and removes a half install', async () => {
  const rel = makeRelease('2.0.0', [['App/app.txt', 'app']]), full = tmp('full-'); fs.writeFileSync(path.join(full, 'mine.txt'), 'x');
  assert.match((await installRelease({ target: full, source: { type: 'local', path: rel } })).message, /not empty/);
  const bad = makeRelease('2.0.0', [['App/app.txt', 'app']], { badHash: true }), t2 = path.join(tmp('t2-'), 'S');
  assert.match((await installRelease({ target: t2, source: { type: 'local', path: bad } })).message, /sha256/); assert.ok(!fs.existsSync(path.join(t2, 'App')));
  const evil = makeRelease('2.0.0', [['App/app.txt', 'app'], ['Data/x.json', '{}']]), t3 = path.join(tmp('t3-'), 'S');
  await assert.rejects(() => installRelease({ target: t3, source: { type: 'local', path: evil } }), /may not write into Data/); assert.ok(!fs.existsSync(path.join(t3, 'App')));
});

test('installer CLI falls back from a dead network source to the local one', () => {
  const rel = makeRelease('2.0.0', [['App/app.txt', 'app']]), target = path.join(tmp('cli-'), 'S');
  const o = JSON.parse(execFileSync('node', [CLI, '--target', target, '--url', 'http://127.0.0.1:1/manifest.json', '--local', rel], { stdio: 'pipe' }).toString());
  assert.equal(o.ok, true, JSON.stringify(o)); assert.equal(o.via, 'local'); assert.match(o.tried[0], /^network:/); assert.equal(read(target, 'App/app.txt'), 'app');
});

// ---- Optional Ed25519 signing ----
import { generateKeyPair, signManifest } from '../lib/sign.mjs';
const sign = (rel, seed) => fs.writeFileSync(path.join(rel, 'manifest.sig'), signManifest(fs.readFileSync(path.join(rel, 'manifest.json')), seed));

test('signing: no key configured means unsigned releases still work', async () => {
  const inst = makeInstall(), rel = makeRelease('1.1.0', [['App/app.txt', 'new']]);
  assert.equal((await applyUpdate({ installDir: inst, source: { type: 'local', path: rel }, current: '1.0.0', liveCheck: notLive })).ok, true);
});

test('signing: a valid signature applies; unsigned, tampered and wrong-key are refused with nothing changed', async () => {
  const k = generateKeyPair(), other = generateKeyPair();
  const src = r => ({ type: 'local', path: r });
  const run = async (rel, pub) => { const inst = makeInstall(); const r = await applyUpdate({ installDir: inst, source: src(rel), current: '1.0.0', pubkey: pub, liveCheck: notLive }); return [inst, r]; };
  const ok = makeRelease('1.1.0', [['App/app.txt', 'new']]); sign(ok, k.seed);
  let [inst, r] = await run(ok, k.pubkey); assert.equal(r.ok, true, r.message); assert.equal(read(inst, 'App/app.txt'), 'new');
  const unsigned = makeRelease('1.1.0', [['App/app.txt', 'new']]);
  [inst, r] = await run(unsigned, k.pubkey); assert.equal(r.ok, false); assert.match(r.message, /not signed/); assert.equal(read(inst, 'App/app.txt'), 'old app');
  const tampered = makeRelease('1.1.0', [['App/app.txt', 'new']]); sign(tampered, k.seed);
  fs.writeFileSync(path.join(tampered, 'manifest.json'), fs.readFileSync(path.join(tampered, 'manifest.json'), 'utf8').replace('1.1.0', '9.9.9'));
  [inst, r] = await run(tampered, k.pubkey); assert.equal(r.ok, false); assert.match(r.message, /signature/); assert.equal(read(inst, 'App/app.txt'), 'old app');
  const wrong = makeRelease('1.1.0', [['App/app.txt', 'new']]); sign(wrong, other.seed);
  [inst, r] = await run(wrong, k.pubkey); assert.equal(r.ok, false); assert.match(r.message, /signature/);
});

test('signing: a zip bundle carries manifest.sig and installer honours the key', async () => {
  const k = generateKeyPair(), rel = makeRelease('2.0.0', [['App/app.txt', 'app']]); sign(rel, k.seed);
  const z = path.join(tmp('bun-'), 'bundle.zip');
  fs.writeFileSync(z, writeZip(fs.readdirSync(rel).map(n => ({ name: n, data: fs.readFileSync(path.join(rel, n)) }))));
  const t = path.join(tmp('sg-'), 'S'), r = await installRelease({ target: t, source: { type: 'local', path: z }, pubkey: k.pubkey });
  assert.equal(r.ok, true, r.message); assert.equal(JSON.parse(read(t, 'install.json')).pubkey, k.pubkey);
  const t2 = path.join(tmp('sg2-'), 'S'); await assert.rejects(() => installRelease({ target: t2, source: { type: 'local', path: z }, pubkey: generateKeyPair().pubkey }), /signature/);
  assert.ok(!fs.existsSync(path.join(t2, 'App')));
});

// ---- Launch hook (updater launch) ----
import net from 'node:net';
const UPD = path.join(path.dirname(CLI), '..', 'Suite', 'updater', 'updater.mjs');
const launch = (inst, extra = []) => JSON.parse(execFileSync('node', [UPD, 'launch', '--install', inst, '--core-port', '1', ...extra], { stdio: 'pipe' }).toString());
function withSource(inst, rel, more = {}) { const j = JSON.parse(read(inst, 'install.json')); fs.writeFileSync(path.join(inst, 'install.json'), JSON.stringify({ ...j, source: { type: 'local', path: rel }, ...more })); }

test('launch hook: applies from the configured source when the app is not running and the setting allows it', () => {
  const inst = makeInstall(), rel = makeRelease('1.2.0', [['App/app.txt', 'launched']]); withSource(inst, rel);
  const o = launch(inst); assert.equal(o.ok, true, JSON.stringify(o)); assert.equal(read(inst, 'App/app.txt'), 'launched'); assert.equal(read(inst, 'Data/keep.txt'), 'my data');
});

test('launch hook: setting off, no source, or app already running changes nothing', async () => {
  const rel = makeRelease('1.2.0', [['App/app.txt', 'launched']]);
  let inst = makeInstall(); withSource(inst, rel, { auto_update: false }); assert.match(launch(inst).message, /off/); assert.equal(read(inst, 'App/app.txt'), 'old app');
  inst = makeInstall(); assert.match(launch(inst).message, /no update source/);
  inst = makeInstall(); withSource(inst, rel);
  const srv = net.createServer().listen(0, '127.0.0.1'); await new Promise(r => srv.on('listening', r));
  const o = JSON.parse(execFileSync('node', [UPD, 'launch', '--install', inst, '--core-port', String(srv.address().port)], { stdio: 'pipe' }).toString()); srv.close();
  assert.match(o.message, /already running/); assert.equal(read(inst, 'App/app.txt'), 'old app');
});

test('launch hook: a corrupt release leaves the old version and reports it', () => {
  const inst = makeInstall(), rel = makeRelease('1.2.0', [['App/app.txt', 'x']], { badHash: true }); withSource(inst, rel);
  const o = launch(inst); assert.equal(o.ok, false); assert.equal(read(inst, 'App/app.txt'), 'old app');
});
