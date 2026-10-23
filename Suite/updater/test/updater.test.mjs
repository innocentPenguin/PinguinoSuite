// Updater tests: everything runs in temp dirs, never against a real install.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { writeZip, readZip } from '../lib/zip.mjs';
import { applyUpdate, sha256, dirs, rollbackLatest, recoverInterrupted } from '../lib/apply.mjs';
import { safeRel } from '../lib/paths.mjs';
import { ejectPart, verifyParts } from '../lib/parts.mjs';
import { cmpVersion, parseManifest } from '../lib/manifest.mjs';
import { gitStatus, gitUpdate, openSource, setToken } from '../lib/sources.mjs';
import { seal, unseal, storeToken, loadToken } from '../lib/secret.mjs';

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
  fs.mkdirSync(dirs(inst).u, { recursive: true }); fs.writeFileSync(dirs(inst).lock, String(process.pid));
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
  const inst = makeInstall(), rel = makeRelease('1.2.0', [['App/app.txt', 'launched']]); withSource(inst, rel, { auto_update: true });
  const o = launch(inst); assert.equal(o.ok, true, JSON.stringify(o)); assert.equal(read(inst, 'App/app.txt'), 'launched'); assert.equal(read(inst, 'Data/keep.txt'), 'my data');
});

test('launch hook: setting off, no source, or app already running changes nothing', async () => {
  const rel = makeRelease('1.2.0', [['App/app.txt', 'launched']]);
  let inst = makeInstall(); withSource(inst, rel, { auto_update: false }); assert.match(launch(inst).message, /off/); assert.equal(read(inst, 'App/app.txt'), 'old app');
  inst = makeInstall(); assert.match(launch(inst).message, /no update source/);
  inst = makeInstall(); withSource(inst, rel, { auto_update: true });
  const srv = net.createServer().listen(0, '127.0.0.1'); await new Promise(r => srv.on('listening', r));
  const o = JSON.parse(execFileSync('node', [UPD, 'launch', '--install', inst, '--core-port', String(srv.address().port)], { stdio: 'pipe' }).toString()); srv.close();
  assert.match(o.message, /already running/); assert.equal(read(inst, 'App/app.txt'), 'old app');
});

test('launch hook: a corrupt release leaves the old version and reports it', () => {
  const inst = makeInstall(), rel = makeRelease('1.2.0', [['App/app.txt', 'x']], { badHash: true }); withSource(inst, rel, { auto_update: true });
  const o = launch(inst); assert.equal(o.ok, false); assert.equal(read(inst, 'App/app.txt'), 'old app');
});


// ---- private repo key + github source
test('sealed key: right passphrase opens it, wrong or short one does not, token is not visible in the blob', () => {
  const blob = seal('github_pat_ABCDEFGHIJKLMNOP1234', 'correct horse');
  assert.equal(unseal(blob, 'correct horse'), 'github_pat_ABCDEFGHIJKLMNOP1234');
  assert.ok(!blob.toString('latin1').includes('ABCDEFGHIJKLMNOP'));
  assert.throws(() => unseal(blob, 'wrong passphrase'), /wrong install passphrase/);
  assert.throws(() => seal('x', 'short'), /at least 8/);
  const bad = Buffer.from(blob); bad[bad.length - 1] ^= 1;
  assert.throws(() => unseal(bad, 'correct horse'), /damaged/);
});

test('token on the installed PC is DPAPI-encrypted, not plaintext, and reads back', { skip: process.platform !== 'win32' }, () => {
  const d = tmp('tok-'); storeToken(d, 'github_pat_ROUNDTRIP1234567890');
  const raw = fs.readFileSync(path.join(d, 'Data', 'runtime', 'update_token.dpapi'), 'utf8');
  assert.ok(!raw.includes('ROUNDTRIP'));
  assert.equal(loadToken(d), 'github_pat_ROUNDTRIP1234567890');
  assert.equal(loadToken(tmp('none-')), null);
});

test('github source: token only goes to api.github.com, assets are fetched by id, sha256 still checked at install', async () => {
  const zip = writeZip([{ name: 'App/app.txt', data: B('hello') }]);
  const manifest = JSON.stringify({ schema: 1, channel: 'stable', version: '2.0.0', files: [{ name: 'suite-2.0.0.zip', size: zip.length, sha256: sha256(zip), url: 'suite-2.0.0.zip' }] });
  const calls = [];
  const realFetch = globalThis.fetch;
  globalThis.fetch = async (url, init = {}) => {
    calls.push({ url: String(url), auth: (init.headers || {}).Authorization, accept: (init.headers || {}).Accept });
    const u = String(url), mk = b => new Response(b, { status: 200 });
    if (u.endsWith('/releases/latest')) return mk(JSON.stringify({ assets: [{ name: 'manifest.json', id: 11 }, { name: 'suite-2.0.0.zip', id: 22 }] }));
    if (u.endsWith('/assets/11')) return mk(manifest);
    if (u.endsWith('/assets/22')) return mk(zip);
    return new Response('nope', { status: 404 });
  };
  try {
    await assert.rejects(openSource({ type: 'github', repo: 'o/r' }), /read-only key/);
    setToken('github_pat_TESTTOKEN123456789');
    const target = path.join(tmp('gh-'), 'inst');
    const r = await installRelease({ target, source: { type: 'github', repo: 'o/r' }, recordSource: { type: 'github', repo: 'o/r' } });
    assert.equal(r.ok, true, r.message);
    assert.equal(fs.readFileSync(path.join(target, 'App', 'app.txt'), 'utf8'), 'hello');
    assert.deepEqual(JSON.parse(fs.readFileSync(path.join(target, 'install.json'), 'utf8')).source, { type: 'github', repo: 'o/r' });
    assert.ok(calls.every(c => c.url.startsWith('https://api.github.com/repos/o/r/')));
    assert.ok(calls.every(c => c.auth === 'Bearer github_pat_TESTTOKEN123456789'));
    assert.ok(calls.some(c => c.accept === 'application/octet-stream'));
    await assert.rejects(openSource({ type: 'github', repo: '../evil' }), /owner\/name/);
  } finally { globalThis.fetch = realFetch; setToken(null); }
});

test('a --local install records no update source when asked', async () => {
  const rel = makeRelease('1.0.0', [['App/a.txt', 'x']]), target = path.join(tmp('nosrc-'), 'i');
  const r = await installRelease({ target, source: { type: 'local', path: rel }, recordSource: false });
  assert.equal(r.ok, true);
  assert.equal(JSON.parse(fs.readFileSync(path.join(target, 'install.json'), 'utf8')).source, undefined);
});

// ---- per-part updates (components) ----
import { hashComponents, componentOf } from '../lib/components.mjs';
import { checkUpdate } from '../lib/apply.mjs';
function makeCompRelease(version, entries) {
  const d = tmp('rel-'), zip = writeZip(entries.map(([name, data]) => ({ name, data: B(data) }))), name = `suite-${version}.zip`;
  fs.writeFileSync(path.join(d, name), zip);
  const components = hashComponents(entries.map(([rel, data]) => ({ rel, data: B(data) })));
  fs.writeFileSync(path.join(d, 'manifest.json'), JSON.stringify({ schema: 1, channel: 'stable', version, components, files: [{ name, size: zip.length, sha256: sha256(zip), url: name }] }));
  return d;
}
const FILES1 = [['Suite/modules/listen/a.py', 'listen 1'], ['Suite/modules/multi/b.py', 'multi 1'], ['Suite/suite/suite.py', 'core 1'], ['Docs/x.md', 'doc 1']];
const FILES2 = [['Suite/modules/listen/a.py', 'listen 2'], ['Suite/modules/multi/b.py', 'multi 2'], ['Suite/suite/suite.py', 'core 2'], ['Docs/x.md', 'doc 1']];

test('componentOf groups files; unknown paths are scripts and docs', () => {
  assert.equal(componentOf('Suite/modules/listen/server.py'), 'listen'); assert.equal(componentOf('Suite/suite/suite.py'), 'core');
  assert.equal(componentOf('PinguinoHost/bin/Release/net8.0/PinguinoHost.dll'), 'host'); assert.equal(componentOf('Docs/INSTALL.md'), 'tools');
  assert.equal(componentOf('App/src-tauri/target/release/pinguino-suite.exe'), 'shell');
});

test('a part updates alone: other parts stay, record kept, check lists only what differs, rollback restores', async () => {
  const inst = makeInstall('1.0.0', {}), r1 = makeCompRelease('1.0.1', FILES1), r2 = makeCompRelease('1.0.2', FILES2);
  let r = await applyUpdate({ installDir: inst, source: { type: 'local', path: r1 }, current: '1.0.0', liveCheck: notLive }); assert.equal(r.ok, true, r.message);
  r = await applyUpdate({ installDir: inst, source: { type: 'local', path: r2 }, current: '1.0.1', liveCheck: notLive, only: ['listen'] }); assert.equal(r.ok, true, r.message);
  assert.equal(read(inst, 'Suite/modules/listen/a.py'), 'listen 2'); assert.equal(read(inst, 'Suite/modules/multi/b.py'), 'multi 1'); assert.equal(read(inst, 'Suite/suite/suite.py'), 'core 1');
  const j = JSON.parse(read(inst, 'install.json')); assert.equal(j.version, '1.0.1');   // not everything is current, so the version does not move
  const c = await checkUpdate({ source: { type: 'local', path: r2 }, current: '1.0.1', installDir: inst });
  assert.deepEqual(c.components.filter(x => x.changed).map(x => x.id).sort(), ['core', 'multi']); assert.equal(c.available, true);
  rollbackLatest(inst); assert.equal(read(inst, 'Suite/modules/listen/a.py'), 'listen 1');
  r = await applyUpdate({ installDir: inst, source: { type: 'local', path: r2 }, current: '1.0.1', liveCheck: notLive, only: ['listen', 'multi', 'core'] });
  assert.equal(JSON.parse(read(inst, 'install.json')).version, '1.0.2');
  assert.equal((await checkUpdate({ source: { type: 'local', path: r2 }, current: '1.0.2', installDir: inst })).available, false);
});

test('a part update waits while live and refuses unknown parts or releases without part info', async () => {
  const inst = makeInstall('1.0.0', {}), r2 = makeCompRelease('1.0.2', FILES2);
  let r = await applyUpdate({ installDir: inst, source: { type: 'local', path: r2 }, current: '1.0.0', liveCheck: async () => ({ live: true }), only: ['listen'] });
  assert.equal(r.deferred, true); assert.ok(!fs.existsSync(path.join(inst, 'Suite/modules/listen/a.py')));
  r = await applyUpdate({ installDir: inst, source: { type: 'local', path: r2 }, current: '1.0.0', liveCheck: notLive, only: ['nope'] }); assert.equal(r.ok, false);
  r = await applyUpdate({ installDir: inst, source: { type: 'local', path: makeRelease('1.0.3', [['a.txt', 'x']]) }, current: '1.0.0', liveCheck: notLive, only: ['listen'] }); assert.equal(r.ok, false);
});

test('app parts are staged, then swapped by the launch hook', async () => {
  const inst = makeInstall('1.0.0', {}), r2 = makeCompRelease('1.0.2', FILES2);
  const r = await applyUpdate({ installDir: inst, source: { type: 'local', path: r2 }, current: '1.0.0', liveCheck: async () => ({ live: true }), only: ['core'], stageOnly: true });
  assert.equal(r.staged, true, r.message); assert.ok(!fs.existsSync(path.join(inst, 'Suite/suite/suite.py')));
  const pend = JSON.parse(fs.readFileSync(dirs(inst).pending, 'utf8')); assert.deepEqual(pend.only, ['core']);
  const o = launch(inst); assert.equal(o.ok, true, JSON.stringify(o));
  assert.equal(read(inst, 'Suite/suite/suite.py'), 'core 2'); assert.ok(!fs.existsSync(path.join(inst, 'Suite/modules/listen/a.py')));   // only the staged part moved
});

test('an update keeps the source recorded in install.json (the next check needs it)', async () => {
  const inst = makeInstall('1.0.0', {}), r2 = makeCompRelease('1.0.2', FILES2);
  withSource(inst, r2);
  await applyUpdate({ installDir: inst, source: { type: 'local', path: r2 }, current: '1.0.0', liveCheck: notLive, only: ['listen'] });
  assert.deepEqual(JSON.parse(read(inst, 'install.json')).source, { type: 'local', path: r2 });
});

// ---- install profiles: the PinguinoLite PC keeps only lite + link + scripts; other modules are added, taken out and verified on demand
const LITE = [['PinguinoLite/Start-Lite.bat', 'lite 1'], ['PinguinoLite/src-tauri/target/release/pinguino-lite.exe', 'litebin 1'], ['Suite/modules/link/l.mjs', 'link 1'], ['Suite/modules/spotify/s.py', 'spotify 1'],
  ['Suite/modules/listen/a.py', 'listen 1'], ['Suite/suite/suite.py', 'core 1'], ['Suite/updater/updater.mjs', 'upd 1'], ['Docs/x.md', 'doc 1']];
const LITE2 = LITE.map(([k, v]) => [k, v.replace(/ 1$/, ' 2')]);
async function minimalInstall() {
  const rel = makeCompRelease('1.0.1', LITE), dst = path.join(tmp('lite-'), 'inst');
  const r = await installRelease({ target: dst, source: { type: 'local', path: rel }, profile: 'lite-minimal' });
  assert.equal(r.ok, true, r.message); return { dst, rel };
}

test('lite-minimal installs only Lite, Link and the scripts; install.json records the profile and per-part hashes', async () => {
  const { dst } = await minimalInstall();
  for (const f of ['PinguinoLite/Start-Lite.bat', 'Suite/modules/link/l.mjs', 'Suite/updater/updater.mjs', 'Docs/x.md']) assert.ok(fs.existsSync(path.join(dst, f)), f);
  for (const f of ['Suite/modules/spotify/s.py', 'Suite/modules/listen/a.py', 'Suite/suite/suite.py']) assert.ok(!fs.existsSync(path.join(dst, f)), f);
  const j = JSON.parse(read(dst, 'install.json')); assert.equal(j.profile, 'lite-minimal'); assert.deepEqual(j.parts, ['lite', 'link', 'tools']);
  assert.deepEqual(Object.keys(j.components).sort(), ['link', 'lite', 'tools']);
  assert.equal((await installRelease({ target: path.join(tmp('x-'), 'i'), source: { type: 'local', path: makeCompRelease('1.0.1', LITE) }, profile: 'nope' })).ok, false);
  assert.equal((await installRelease({ target: path.join(tmp('x-'), 'i'), source: { type: 'local', path: makeRelease('1.0.1', [['a.txt', 'x']]) }, profile: 'lite-minimal' })).ok, false);   // no part info -> refuse
});

test('a minimal install is not offered, and does not take, the parts it does not keep; they show as optional', async () => {
  const { dst } = await minimalInstall(), r2 = makeCompRelease('1.0.2', LITE2);
  const c = await checkUpdate({ source: { type: 'local', path: r2 }, current: '1.0.1', installDir: dst });
  assert.deepEqual(c.components.map(x => x.id).sort(), ['link', 'lite', 'tools']); assert.deepEqual(c.optional.map(x => x.id).sort(), ['core', 'listen', 'spotify']);
  const r = await applyUpdate({ installDir: dst, source: { type: 'local', path: r2 }, current: '1.0.1', liveCheck: notLive });   // a full update of a minimal install
  assert.equal(r.ok, true, r.message); assert.equal(read(dst, 'Suite/modules/link/l.mjs'), 'link 2'); assert.ok(!fs.existsSync(path.join(dst, 'Suite/modules/spotify/s.py')));
  assert.equal(JSON.parse(read(dst, 'install.json')).version, '1.0.2');   // current as far as it is concerned
  assert.equal((await checkUpdate({ source: { type: 'local', path: r2 }, current: '1.0.2', installDir: dst })).available, false);
});

test('install on demand, verify, repair, eject (files are moved, not deleted), and the minimal profile stays valid', async () => {
  const { dst, rel } = await minimalInstall(), src = { type: 'local', path: rel };
  let r = await applyUpdate({ installDir: dst, source: src, current: '1.0.1', liveCheck: notLive, only: ['spotify'] });
  assert.equal(r.ok, true, r.message); assert.equal(read(dst, 'Suite/modules/spotify/s.py'), 'spotify 1');
  let j = JSON.parse(read(dst, 'install.json')); assert.deepEqual([...j.parts].sort(), ['link', 'lite', 'spotify', 'tools']); assert.ok(j.components.spotify);
  assert.ok(!fs.existsSync(path.join(dst, 'Suite/modules/listen/a.py')));
  let v = await verifyParts({ installDir: dst, source: src }); assert.equal(v.ok, true); assert.equal(v.all_ok, true); assert.deepEqual(v.parts.map(p => p.id).sort(), ['link', 'lite', 'spotify']);
  fs.writeFileSync(path.join(dst, 'Suite/modules/spotify/s.py'), 'hacked'); fs.rmSync(path.join(dst, 'Suite/modules/link/l.mjs'));
  v = await verifyParts({ installDir: dst, source: src, only: ['spotify', 'link'] });
  assert.equal(v.all_ok, false); assert.equal(v.parts.find(p => p.id === 'spotify').state, 'damaged'); assert.equal(v.parts.find(p => p.id === 'link').state, 'missing');
  assert.equal((await verifyParts({ installDir: dst, source: src, only: ['listen'] })).parts.length, 0);   // not installed -> not checked
  r = await applyUpdate({ installDir: dst, source: src, current: '1.0.1', liveCheck: notLive, only: ['spotify', 'link'] }); assert.match(r.message, /up to date/);   // hashes match, so a plain apply does nothing
  r = await applyUpdate({ installDir: dst, source: src, current: '1.0.1', liveCheck: notLive, only: ['spotify', 'link'], repair: true });
  assert.equal(r.ok, true, r.message); assert.equal(read(dst, 'Suite/modules/spotify/s.py'), 'spotify 1'); assert.equal(read(dst, 'Suite/modules/link/l.mjs'), 'link 1');
  fs.mkdirSync(path.join(dst, 'Suite/modules/spotify/data'), { recursive: true }); fs.writeFileSync(path.join(dst, 'Suite/modules/spotify/data/tokens.json'), 'mine');
  const e = ejectPart(dst, 'spotify'); assert.equal(e.ok, true, e.message); assert.equal(e.moved, 1);
  assert.ok(!fs.existsSync(path.join(dst, 'Suite/modules/spotify/s.py'))); assert.equal(read(dst, 'Suite/modules/spotify/data/tokens.json'), 'mine');   // module data stays
  assert.equal(fs.readFileSync(path.join(e.kept_in, 'files/Suite/modules/spotify/s.py'), 'utf8'), 'spotify 1');
  j = JSON.parse(read(dst, 'install.json')); assert.deepEqual([...j.parts].sort(), ['link', 'lite', 'tools']); assert.ok(!j.components.spotify);
  assert.equal(ejectPart(dst, 'link').ok, true); assert.ok(!fs.existsSync(path.join(dst, 'Suite/modules/link')));   // emptied folder removed; spotify's stays because its data is still there   // link is a module part too: allowed
  assert.equal(ejectPart(dst, 'lite').ok, false); assert.equal(ejectPart(dst, 'tools').ok, false); assert.equal(ejectPart(dst, 'zzz').ok, false);
});

test('a full install records its profile and keeps every part', async () => {
  const dst = path.join(tmp('full-'), 'inst'), rel = makeCompRelease('1.0.1', LITE);
  assert.equal((await installRelease({ target: dst, source: { type: 'local', path: rel } })).ok, true);
  const j = JSON.parse(read(dst, 'install.json')); assert.equal(j.profile, 'full'); assert.equal(j.parts, undefined); assert.ok(fs.existsSync(path.join(dst, 'Suite/modules/spotify/s.py')));
});
test('runtime files (spotify spike config + lockfile) never ship in a release', async () => {
  const { SKIP_DIR, SKIP_FILE } = await import('../lib/components.mjs');
  assert.ok(SKIP_DIR.test('Suite/modules/spotify/bin/spike-cfg/'));
  assert.ok(SKIP_FILE.test('Suite/modules/spotify/bin/spike-cfg/lockfile') && SKIP_FILE.test('lockfile'));
  assert.ok(!SKIP_FILE.test('Suite/modules/spotify/bin/librespot.exe'));
});

// ---- Lite Parts card: the exact command lines PinguinoLite issues (PinguinoLite/src-tauri/src/parts.rs apply_args) ----
test('Lite command lines: lite is staged then swapped by launch; link applies; repair restores; rollback --plan answers', () => {
  const run = (...a) => JSON.parse(execFileSync('node', [UPD, ...a, '--core-port', '1'], { stdio: 'pipe' }).toString());
  const inst = makeInstall('1.0.0', { 'PinguinoLite/lite.txt': 'old lite', 'Suite/modules/link/link.txt': 'old link' });
  const rel = makeCompRelease('1.1.0', [['PinguinoLite/lite.txt', 'new lite'], ['Suite/modules/link/link.txt', 'new link']]);
  withSource(inst, rel, { profile: 'lite-minimal', parts: ['lite', 'link', 'tools'] });
  // apply --only lite --stage --install <dir>: verified and parked, nothing swapped under the running exe
  let o = run('apply', '--only', 'lite', '--stage', '--install', inst);
  assert.equal(o.ok, true, JSON.stringify(o)); assert.equal(o.staged, true); assert.equal(read(inst, 'PinguinoLite/lite.txt'), 'old lite');
  // Start-Lite.bat: updater.mjs launch --install <dir> swaps the staged part
  o = run('launch', '--install', inst); assert.equal(o.ok, true, JSON.stringify(o)); assert.equal(read(inst, 'PinguinoLite/lite.txt'), 'new lite');
  // apply --only link --install <dir>
  o = run('apply', '--only', 'link', '--install', inst); assert.equal(o.ok, true, JSON.stringify(o)); assert.equal(read(inst, 'Suite/modules/link/link.txt'), 'new link');
  // apply --only link --repair: a damaged file is restored
  fs.writeFileSync(path.join(inst, 'Suite/modules/link/link.txt'), 'broken');
  o = run('apply', '--only', 'link', '--repair', '--install', inst); assert.equal(o.ok, true, JSON.stringify(o)); assert.equal(read(inst, 'Suite/modules/link/link.txt'), 'new link');
  // rollback --plan --install <dir>
  o = run('rollback', '--plan', '--install', inst); assert.equal(o.ok, true, JSON.stringify(o)); assert.ok(Array.isArray(o.components));
  // a part Lite never offers is refused by the updater too when unknown
  o = run('apply', '--only', 'nonsense', '--install', inst); assert.equal(o.ok, false);
});

// ---- fresh-PC failure modes (Installer review) ----
import { onlyEmptyDirs, pruneEmptyDirs, writeFailure, shortcutSpec, makeShortcuts, neededBytes, freeBytes } from '../lib/install.mjs';
import { defaultTimeoutMs } from '../lib/sources.mjs';

test('install: leftover empty folders do not block a retry, files do', async () => {
  const d = tmp('empty-'); fs.mkdirSync(path.join(d, 'Data', 'runtime'), { recursive: true });
  assert.equal(onlyEmptyDirs(d), true);
  fs.writeFileSync(path.join(d, 'Data', 'runtime', 'x.txt'), '1'); assert.equal(onlyEmptyDirs(d), false);
  fs.unlinkSync(path.join(d, 'Data', 'runtime', 'x.txt')); pruneEmptyDirs(d, true); assert.deepEqual(fs.readdirSync(d), []);
  // a retry into a folder that only holds empty folders works
  fs.mkdirSync(path.join(d, 'Data', 'runtime'), { recursive: true });
  const rel = makeRelease('1.0.0', [['App/app.txt', 'a']]);
  const r = await installRelease({ target: d, source: { type: 'local', path: rel } }); assert.equal(r.ok, true, JSON.stringify(r));
});

test('install: failure messages name the cause; shortcuts differ for a lite-minimal install; big downloads get a long time limit', () => {
  assert.match(writeFailure({ code: 'ENOSPC', message: 'x' }), /disk is full/);
  assert.match(writeFailure({ code: 'EBUSY', message: 'x' }), /antivirus/);
  assert.match(writeFailure({ code: 'ENAMETOOLONG', message: 'x' }), /too long/);
  assert.equal(shortcutSpec('lite-minimal').exeRel, 'PinguinoLite/Start-Lite.bat'); assert.match(shortcutSpec('full').exeRel, /pinguino-suite\.exe$/);
  assert.equal(defaultTimeoutMs(256 * 1024), 10000); assert.ok(defaultTimeoutMs(2 * 1024 ** 3) >= 15 * 60 * 1000);
});

test('install: refuses with a clear message when the drive is too small (mocked free space), installs when it fits', async () => {
  const rel = makeRelease('1.0.0', [['App/app.txt', 'a']]), size = fs.statSync(path.join(rel, 'suite-1.0.0.zip')).size;
  const d = tmp('space-'); const small = await installRelease({ target: d, source: { type: 'local', path: rel }, free: () => neededBytes(size) - 1 });
  assert.equal(small.ok, false); assert.match(small.message, /not enough free space.*MB are free/); assert.deepEqual(fs.readdirSync(d), []);
  const fits = await installRelease({ target: d, source: { type: 'local', path: rel }, free: () => neededBytes(size) }); assert.equal(fits.ok, true, JSON.stringify(fits));
  assert.equal(neededBytes(0), 500 * 1024 * 1024); assert.ok(freeBytes(path.join(d, 'not', 'there', 'yet')) > 0);   // walks up to an existing parent
  const unknown = await installRelease({ target: tmp('space2-'), source: { type: 'local', path: rel }, free: () => null }); assert.equal(unknown.ok, true);   // cannot tell = do not block
});

test('shortcuts: full and lite-minimal targets, written to a scratch folder (PINGUINO_SHORTCUT_DIR), never the real Desktop', { skip: process.platform !== 'win32' }, () => {
  const inst = tmp('lnk-inst-'), out = tmp('lnk-out-');
  for (const f of ['PinguinoLite/Start-Lite.bat', 'App/src-tauri/target/release/pinguino-suite.exe']) { fs.mkdirSync(path.dirname(path.join(inst, f)), { recursive: true }); fs.writeFileSync(path.join(inst, f), 'x'); }
  const old = process.env.PINGUINO_SHORTCUT_DIR; process.env.PINGUINO_SHORTCUT_DIR = out;
  try {
    const target = lnk => execFileSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', "(New-Object -ComObject WScript.Shell).CreateShortcut($env:L).TargetPath"], { env: { ...process.env, L: lnk } }).toString().trim();
    const lite = makeShortcuts({ target: inst, ...shortcutSpec('lite-minimal') });
    assert.deepEqual(lite.map(p => path.relative(out, p)).sort(), [path.join('Desktop', 'PinguinoLite.lnk'), path.join('Programs', 'PinguinoLite.lnk')]);
    assert.equal(target(lite[0]).toLowerCase(), path.join(inst, 'PinguinoLite', 'Start-Lite.bat').toLowerCase());
    const full = makeShortcuts({ target: inst, ...shortcutSpec('full') });
    assert.equal(target(full[0]).toLowerCase(), path.join(inst, 'App', 'src-tauri', 'target', 'release', 'pinguino-suite.exe').toLowerCase());
    // a target that is not in the install makes no shortcut
    assert.throws(() => makeShortcuts({ target: tmp('lnk-empty-'), ...shortcutSpec('lite-minimal') }), /not in this install/);
  } finally { if (old === undefined) delete process.env.PINGUINO_SHORTCUT_DIR; else process.env.PINGUINO_SHORTCUT_DIR = old; }
});

// ---- repair / uninstall (Installer/install.mjs --repair, --uninstall) ----
import { repairInstall, uninstallInstall, damagedParts } from '../lib/maintain.mjs';
const INSTALLER = path.join(path.dirname(UPD), '..', '..', 'Installer', 'install.mjs');
const runInstaller = (...a) => JSON.parse(execFileSync('node', [INSTALLER, ...a], { stdio: 'pipe' }).toString());

test('repair: only damaged parts are re-applied (backup kept), intact installs are left alone; CLI works', async () => {
  const files = [['PinguinoLite/lite.txt', 'lite v1'], ['Suite/modules/link/link.txt', 'link v1'], ['README.txt', 'docs']];
  const rel = makeCompRelease('1.0.0', files), inst = tmp('rep-');
  assert.equal((await installRelease({ target: inst, source: { type: 'local', path: rel }, recordSource: { type: 'local', path: rel }, profile: 'lite-minimal' })).ok, true);
  assert.deepEqual(damagedParts({ parts: [{ id: 'a', state: 'ok' }, { id: 'b', state: 'damaged' }] }), ['b']);
  let r = await repairInstall({ installDir: inst, source: { type: 'local', path: rel } }); assert.equal(r.ok, true, JSON.stringify(r)); assert.deepEqual(r.repaired, []);
  fs.writeFileSync(path.join(inst, 'Suite/modules/link/link.txt'), 'broken'); fs.unlinkSync(path.join(inst, 'PinguinoLite/lite.txt'));
  const o = runInstaller('--target', inst, '--repair', '--source', rel); assert.equal(o.ok, true, JSON.stringify(o));
  assert.deepEqual(o.repaired.sort(), ['link', 'lite']); assert.equal(read(inst, 'Suite/modules/link/link.txt'), 'link v1'); assert.equal(read(inst, 'PinguinoLite/lite.txt'), 'lite v1');
  assert.equal((await repairInstall({ installDir: tmp('norep-'), source: { type: 'local', path: rel } })).ok, false);   // not an install
});

test('uninstall: dry run moves nothing; --yes MOVES everything but Data into Data/updates/ejected; --purge-data also moves Data; nothing is deleted', async () => {
  const rel = makeCompRelease('1.0.0', [['PinguinoLite/lite.txt', 'lite'], ['Suite/modules/link/link.txt', 'link']]), inst = tmp('un-');
  await installRelease({ target: inst, source: { type: 'local', path: rel }, profile: 'lite-minimal' });
  fs.mkdirSync(path.join(inst, 'Data', 'runtime'), { recursive: true }); fs.writeFileSync(path.join(inst, 'Data', 'runtime', 'token.dpapi'), 'secret'); fs.writeFileSync(path.join(inst, 'Data', 'keep.txt'), 'mine');
  let o = runInstaller('--target', inst, '--uninstall'); assert.equal(o.dryRun, true); assert.ok(o.items.includes('PinguinoLite')); assert.equal(read(inst, 'PinguinoLite/lite.txt'), 'lite');
  o = runInstaller('--target', inst, '--uninstall', '--yes'); assert.equal(o.ok, true, JSON.stringify(o));
  assert.equal(fs.existsSync(path.join(inst, 'install.json')), false); assert.equal(fs.existsSync(path.join(inst, 'PinguinoLite')), false);
  assert.equal(read(inst, 'Data/keep.txt'), 'mine'); assert.equal(read(inst, 'Data/runtime/token.dpapi'), 'secret');   // Data stays
  assert.equal(fs.readFileSync(path.join(o.dest, 'PinguinoLite', 'lite.txt'), 'utf8'), 'lite');   // moved, not deleted
  assert.ok(fs.existsSync(path.join(o.dest, 'uninstalled.json'))); assert.equal(fs.existsSync(path.join(o.dest, 'install.json')), true);
  // purge-data: Data is moved too (into the same dated folder), still not deleted
  const inst2 = tmp('un2-'); await installRelease({ target: inst2, source: { type: 'local', path: rel }, profile: 'lite-minimal' });
  fs.mkdirSync(path.join(inst2, 'Data', 'runtime'), { recursive: true }); fs.writeFileSync(path.join(inst2, 'Data', 'runtime', 'token.dpapi'), 'secret');
  const p = uninstallInstall({ installDir: inst2, purgeData: true, apply: true, now: () => 'T1' });
  assert.equal(p.ok, true, JSON.stringify(p)); assert.equal(fs.existsSync(path.join(inst2, 'Data', 'runtime')), false);
  assert.equal(fs.readFileSync(path.join(inst2, 'Data', 'updates', 'ejected', 'uninstall-T1', 'Data', 'runtime', 'token.dpapi'), 'utf8'), 'secret');
  assert.equal(uninstallInstall({ installDir: tmp('nope-'), apply: true }).ok, false);   // not an install: refuses
});

// ---- failure halfway through an update (2026-10-23): every way it can die ends on the old version, verified ----
const bigRelease = (v, n = 6) => makeRelease(v, Array.from({ length: n }, (_, i) => [`App/f${i}.txt`, `new ${i}`]).concat([['App/extra.txt', 'extra']]));
const bigInstall = (n = 6) => makeInstall('1.0.0', Object.fromEntries(Array.from({ length: n }, (_, i) => [`App/f${i}.txt`, `old ${i}`])));
const allOld = (inst, n = 6) => { for (let i = 0; i < n; i++) assert.equal(read(inst, `App/f${i}.txt`), `old ${i}`); assert.ok(!fs.existsSync(path.join(inst, 'App/extra.txt'))); assert.equal(JSON.parse(read(inst, 'install.json')).version, '1.0.0'); assert.equal(read(inst, 'Data/keep.txt'), 'my data'); };
const leftovers = inst => { const out = []; (function w(d) { for (const e of fs.readdirSync(d, { withFileTypes: true })) { const f = path.join(d, e.name); if (e.isDirectory()) { if (e.name !== 'Data') w(f); } else if (f.endsWith('.pinguino-new')) out.push(f); } })(inst); return out; };

test('file locked after several files were already swapped: all old again, no temp files, journal gone', async () => {
  const inst = bigInstall(), rel = bigRelease('1.1.0');
  fs.mkdirSync(path.join(inst, 'App', 'f4.txt.pinguino-new'), { recursive: true });   // the 5th file cannot be written
  const r = await applyUpdate({ installDir: inst, source: { type: 'local', path: rel }, current: '1.0.0', liveCheck: notLive });
  assert.equal(r.ok, false); assert.match(r.message, /old version was put back/);
  fs.rmSync(path.join(inst, 'App', 'f4.txt.pinguino-new'), { recursive: true });
  allOld(inst); assert.deepEqual(leftovers(inst), []); assert.ok(!fs.existsSync(dirs(inst).swapping));
});

test('disk full while backing up: nothing changed, no half backup left, rollback does not trip on it', async () => {
  const inst = bigInstall(), rel = bigRelease('1.1.0');
  fs.rmSync(path.join(inst, 'App', 'f3.txt')); fs.mkdirSync(path.join(inst, 'App', 'f3.txt'));   // cannot be copied to the backup
  const r = await applyUpdate({ installDir: inst, source: { type: 'local', path: rel }, current: '1.0.0', liveCheck: notLive });
  assert.equal(r.ok, false); assert.match(r.message, /nothing was changed/); assert.equal(read(inst, 'App/f0.txt'), 'old 0');
  const bk = dirs(inst).backup; assert.deepEqual(fs.existsSync(bk) ? fs.readdirSync(bk) : [], []);
  assert.equal(rollbackLatest(inst).ok, false);   // "no backup", not an exception
});

test('process killed halfway through the swap: next updater run undoes it (old version, verify-style byte check)', async () => {
  const inst = bigInstall(), rel = bigRelease('1.1.0');
  const script = path.join(tmp('kill-'), 'run.mjs');
  const applyUrl = new URL('../lib/apply.mjs', import.meta.url).href;
  fs.writeFileSync(script, `import fs from 'node:fs'; import { applyUpdate } from '${applyUrl}';
let n = 0; const real = fs.renameSync; fs.renameSync = (a, b) => { if (String(a).endsWith('.pinguino-new') && ++n === 3) process.exit(137); return real(a, b); };
await applyUpdate({ installDir: ${JSON.stringify(inst)}, source: { type: 'local', path: ${JSON.stringify(rel)} }, current: '1.0.0', liveCheck: async () => ({ live: false }) });`);
  let code = 0; try { execFileSync(process.execPath, [script], { stdio: 'pipe' }); } catch (e) { code = e.status; }
  assert.equal(code, 137);
  assert.equal(read(inst, 'App/f0.txt'), 'new 0');   // really half-swapped
  assert.ok(fs.existsSync(dirs(inst).swapping) && fs.existsSync(dirs(inst).lock));
  const rec = recoverInterrupted(inst);   // dead owner's lock is taken over at once
  assert.ok(rec && rec.recovered); allOld(inst); assert.deepEqual(leftovers(inst), []);
  assert.ok(!fs.existsSync(dirs(inst).swapping) && !fs.existsSync(dirs(inst).lock));
  assert.equal(recoverInterrupted(inst), null);
  const again = await applyUpdate({ installDir: inst, source: { type: 'local', path: rel }, current: '1.0.0', liveCheck: notLive });   // and the update itself works afterwards
  assert.equal(again.ok, true); assert.equal(read(inst, 'App/f5.txt'), 'new 5');
});

test('killed update: simply running apply again recovers first, then updates', async () => {
  const inst = bigInstall(), rel = bigRelease('1.1.0');
  const script = path.join(tmp('kill-'), 'run.mjs');
  fs.writeFileSync(script, `import fs from 'node:fs'; import { applyUpdate } from '${new URL('../lib/apply.mjs', import.meta.url).href}';
let n = 0; const real = fs.renameSync; fs.renameSync = (a, b) => { if (String(a).endsWith('.pinguino-new') && ++n === 2) process.exit(9); return real(a, b); };
await applyUpdate({ installDir: ${JSON.stringify(inst)}, source: { type: 'local', path: ${JSON.stringify(rel)} }, current: '1.0.0', liveCheck: async () => ({ live: false }) });`);
  try { execFileSync(process.execPath, [script], { stdio: 'pipe' }); } catch {}
  const r = await applyUpdate({ installDir: inst, source: { type: 'local', path: rel }, current: '1.0.0', liveCheck: notLive });
  assert.equal(r.ok, true); assert.equal(read(inst, 'App/f0.txt'), 'new 0'); assert.equal(JSON.parse(read(inst, 'install.json')).version, '1.1.0'); assert.deepEqual(leftovers(inst), []);
});

test('a lock left by a dead updater does not block for 30 minutes; a live one still does', async () => {
  const inst = bigInstall(2), rel = bigRelease('1.1.0', 2);
  const dead = require_dead_pid(); fs.mkdirSync(dirs(inst).u, { recursive: true }); fs.writeFileSync(dirs(inst).lock, String(dead));
  const r = await applyUpdate({ installDir: inst, source: { type: 'local', path: rel }, current: '1.0.0', liveCheck: notLive });
  assert.equal(r.ok, true);
  function require_dead_pid() { const c = execFileSync(process.execPath, ['-e', 'console.log(process.pid)']); return parseInt(String(c).trim(), 10); }
});

// ---- release notes (Installer/Release-Notes.mjs) ----
import { buildNotes, groupOf, plain, parseLog } from '../../../Installer/Release-Notes.mjs';
test('release notes: grouped, plain, no secrets or addresses, docs-only left out, capped', () => {
  assert.equal(groupOf(['PinguinoLite/src/index.html', 'Docs/x.md']), 'Lite'); assert.equal(groupOf(['App/src/master/master.js']), 'Master');
  assert.equal(groupOf(['Suite/suite/core.py']), 'Core'); assert.equal(groupOf(['Installer/install.mjs']), 'Suite'); assert.equal(groupOf(['Docs/a.md', 'README.md']), null);
  assert.equal(plain('Updater: undo an update (#12).'), 'Undo an update');
  assert.equal(plain('fix login token=abcdef123456 for ivan@example.com'), 'Fix login [removed] for [removed]');
  const raw = '\x1eLite: show hints\n\nPinguinoLite/src/index.html\n\x1eDocs: words\n\nDocs/a.md\n\x1eWIP thing\n\nSuite/x.py\n\x1eShow hints\n\nPinguinoLite/a\n';
  const r = buildNotes(parseLog(raw));
  assert.equal(r.text, 'Lite:\n- Show hints'); assert.equal(r.count, 1);
  const many = buildNotes(Array.from({ length: 200 }, (_, i) => ({ subject: `Change number ${i} with a fairly long description here`, files: ['Suite/x.py'] })));
  assert.ok(many.text.length < 2000 && /and \d+ more change/.test(many.text));
  assert.doesNotMatch(buildNotes([{ subject: 'x ghp_abcdefghijklmnopqrstuvwxyz0123', files: ['Suite/a'] }]).text, /ghp_/);
});

// ---- backups and the swap journal: review fixes (22's scratch experiments) ----
import { spawn } from 'node:child_process';
import { listBackups, rollbackPlan } from '../lib/apply.mjs';
const apply1 = (inst, rel, current, extra = {}) => applyUpdate({ installDir: inst, source: { type: 'local', path: rel }, current, liveCheck: notLive, ...extra });
const sleeper = () => spawn(process.execPath, ['-e', 'setTimeout(()=>{}, 60000)'], { stdio: 'ignore' });
const oldLock = (inst, pid, ageMs) => { const f = dirs(inst).lock; fs.mkdirSync(dirs(inst).u, { recursive: true }); fs.writeFileSync(f, pid === null ? '' : String(pid)); const t = new Date(Date.now() - ageMs); fs.utimesSync(f, t, t); };

test('backups are ordered by time, not by folder name: 1.9.0 -> 1.10.0 -> 1.11.0 rolls back to 1.10.0 and prune keeps the newest', async () => {
  const inst = makeInstall('1.9.0', { 'App/a.txt': 'v1.9' });
  assert.equal((await apply1(inst, makeRelease('1.10.0', [['App/a.txt', 'v1.10']]), '1.9.0', { keepBackups: 1 })).ok, true);
  await new Promise(r => setTimeout(r, 1100));   // the stamp has second resolution
  assert.equal((await apply1(inst, makeRelease('1.11.0', [['App/a.txt', 'v1.11']]), '1.10.0', { keepBackups: 1 })).ok, true);
  const { valid } = listBackups(dirs(inst).backup);
  assert.equal(valid.length, 1); assert.equal(valid[0].b.from, '1.10.0'); assert.match(valid[0].name, /^\d{14}-1\.10\.0$/);
  assert.equal(rollbackPlan(inst).to, '1.10.0');
  assert.equal(rollbackLatest(inst).ok, true); assert.equal(read(inst, 'App/a.txt'), 'v1.10');
  // old-style names ("<version>-<stamp>") are still read, and the `at` inside decides
  const bk = dirs(inst).backup, mk = (name, from, at, txt) => { const d = path.join(bk, name); fs.mkdirSync(path.join(d, 'files', 'App'), { recursive: true }); fs.writeFileSync(path.join(d, 'files', 'App', 'a.txt'), txt); fs.writeFileSync(path.join(d, 'backup.json'), JSON.stringify({ from, to: 'x', at, files: ['App/a.txt'], created: [], install: { schema: 1, version: from } })); };
  fs.rmSync(bk, { recursive: true, force: true });
  mk('1.9.0-20261001000000', '1.9.0', '2026-10-01T00:00:00.000Z', 'nine'); mk('1.10.0-20261002000000', '1.10.0', '2026-10-02T00:00:00.000Z', 'ten');
  assert.equal(listBackups(bk).valid.map(v => v.b.from).join(), '1.9.0,1.10.0'); assert.equal(rollbackLatest(inst).ok, true); assert.equal(read(inst, 'App/a.txt'), 'ten');
});

test('killed mid-backup: half-built (.partial) and list-less folders are not backups; rollback skips them and the next update clears them', async () => {
  const inst = bigInstall(), bk = dirs(inst).backup;
  fs.mkdirSync(path.join(bk, '20261001000000-1.0.0.partial', 'files'), { recursive: true }); fs.mkdirSync(path.join(bk, '20261002000000-1.0.0', 'files'), { recursive: true });
  assert.equal(rollbackPlan(inst), null); assert.deepEqual(rollbackLatest(inst), { ok: false, message: 'there is no backup to restore' });
  const r = await apply1(inst, bigRelease('1.1.0'), '1.0.0'); assert.equal(r.ok, true);
  assert.deepEqual(fs.readdirSync(bk).filter(n => n.endsWith('.partial')), []); assert.equal(fs.readdirSync(bk).length, 1);
  assert.ok(fs.existsSync(path.join(r.backup, 'backup.json')));
  assert.equal(rollbackLatest(inst).ok, true); allOld(inst);
});

function journalFor(inst, backup, extra = {}) { fs.mkdirSync(dirs(inst).u, { recursive: true }); fs.writeFileSync(dirs(inst).swapping, JSON.stringify({ schema: 1, at: new Date().toISOString(), from: '1.0.0', to: '1.1.0', backup, ...extra })); }
const newState = inst => { for (let i = 0; i < 6; i++) assert.equal(read(inst, `App/f${i}.txt`), `new ${i}`); };

test('a stale journal never downgrades a newer install (version must be the journal from or to; not older than the install)', async () => {
  const inst = bigInstall(), r = await apply1(inst, bigRelease('1.1.0'), '1.0.0'); assert.equal(r.ok, true);
  // later the install moved on to 2.0.0 (files kept as they are) but an old journal was left behind
  fs.writeFileSync(dirs(inst).install, JSON.stringify({ schema: 1, version: '2.0.0', channel: 'stable' }));
  journalFor(inst, r.backup);
  const rec = recoverInterrupted(inst); assert.ok(rec && rec.discarded && !rec.recovered && /2\.0\.0/.test(rec.message), JSON.stringify(rec));
  newState(inst); assert.equal(JSON.parse(read(inst, 'install.json')).version, '2.0.0'); assert.ok(!fs.existsSync(dirs(inst).swapping));
  // right version, but the install was written long after the journal: also a later install
  fs.writeFileSync(dirs(inst).install, JSON.stringify({ schema: 1, version: '1.1.0', channel: 'stable', updated_at: new Date().toISOString() }));
  journalFor(inst, r.backup, { at: new Date(Date.now() - 3600e3).toISOString() });
  const rec2 = recoverInterrupted(inst); assert.ok(rec2 && rec2.discarded && /older than the current install/.test(rec2.message)); newState(inst);
  // the real thing still recovers (version = to, journal just written)
  fs.writeFileSync(dirs(inst).install, JSON.stringify({ schema: 1, version: '1.1.0', channel: 'stable', updated_at: new Date().toISOString() }));
  journalFor(inst, r.backup);
  const rec3 = recoverInterrupted(inst); assert.ok(rec3 && rec3.recovered); allOld(inst);
});

test('journal path check: a sibling folder named like the backup folder, the backup folder itself, and escapes are refused', async () => {
  const inst = bigInstall(), r = await apply1(inst, bigRelease('1.1.0'), '1.0.0'), D = dirs(inst);
  const evil = path.join(D.u, 'backup-evil'); fs.cpSync(r.backup, evil, { recursive: true });
  for (const b of [evil, D.backup, path.join(D.backup, '..'), path.join(r.backup, 'files'), '', 42, null]) {
    journalFor(inst, b); const rec = recoverInterrupted(inst);
    assert.ok(rec && rec.discarded && /outside the backup folder/.test(rec.message), String(b) + ' -> ' + JSON.stringify(rec)); newState(inst); assert.ok(!fs.existsSync(D.swapping));
  }
});

test('journal whose backup is gone is dropped (with "run Repair") and does not wedge the next update; a corrupt journal says so', async () => {
  const inst = bigInstall(), D = dirs(inst);
  journalFor(inst, path.join(D.backup, '20261001000000-1.0.0'));
  const rec = recoverInterrupted(inst); assert.ok(rec && rec.discarded && /Repair/.test(rec.message)); assert.ok(!fs.existsSync(D.swapping));
  fs.writeFileSync(D.swapping, '{not json');
  const bad = recoverInterrupted(inst); assert.ok(bad && /journal was unreadable/.test(bad.message) && bad.ok === false); assert.ok(!fs.existsSync(D.swapping));
  assert.equal(recoverInterrupted(inst), null);
  assert.equal((await apply1(inst, bigRelease('1.1.0'), '1.0.0')).ok, true);
});

test('lock: an empty lock file blocks for 5 s then counts as stale; an old lock of a LIVE owner is never stolen; a dead owner is taken over', async () => {
  const inst = bigInstall(2), rel = bigRelease('1.1.0', 2);
  oldLock(inst, null, 0); const fresh = await apply1(inst, rel, '1.0.0'); assert.equal(fresh.skipped, true);
  oldLock(inst, null, 10_000); assert.equal((await apply1(inst, rel, '1.0.0')).ok, true);
  const child = sleeper();
  try {
    const inst2 = bigInstall(2); oldLock(inst2, child.pid, 3 * 3600e3);   // 3 hours old, owner alive
    assert.equal((await apply1(inst2, rel, '1.0.0')).skipped, true); assert.equal(fs.readFileSync(dirs(inst2).lock, 'utf8'), String(child.pid));
    const rb = rollbackLatest(inst2); assert.equal(rb.ok, false); assert.match(rb.message, /update is running/);
  } finally { child.kill(); }
  await new Promise(r => child.once('exit', r));
  const inst3 = bigInstall(2); oldLock(inst3, child.pid, 0);   // its pid is gone now
  assert.equal((await apply1(inst3, rel, '1.0.0')).ok, true);
});

test('lock: two updaters that both find a dead updater lock cannot both run; the lock file is gone afterwards', async () => {
  const inst = bigInstall(2), rel = bigRelease('1.1.0', 2), child = sleeper(); child.kill(); await new Promise(r => child.once('exit', r));
  oldLock(inst, child.pid, 0);
  const [a, b] = await Promise.all([apply1(inst, rel, '1.0.0'), apply1(inst, rel, '1.0.0')]);
  assert.equal([a, b].filter(x => x.ok && !x.skipped).length, 1); assert.equal([a, b].filter(x => x.skipped).length, 1);
  assert.ok(!fs.existsSync(dirs(inst).lock)); assert.deepEqual(fs.readdirSync(dirs(inst).u).filter(n => n.includes('.stale-')), []);
});

test('rollback takes the update lock: it cannot run while an update swaps, and leaves no lock behind', async () => {
  const inst = bigInstall(), r = await apply1(inst, bigRelease('1.1.0'), '1.0.0'); assert.equal(r.ok, true);
  fs.writeFileSync(dirs(inst).lock, String(process.pid));   // an updater of this very process is "running"
  assert.equal(rollbackLatest(inst).ok, false); newState(inst);
  fs.unlinkSync(dirs(inst).lock);
  assert.equal(rollbackLatest(inst).ok, true); allOld(inst); assert.ok(!fs.existsSync(dirs(inst).lock));
});
