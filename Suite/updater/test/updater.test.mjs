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
  assert.equal(ejectPart(dst, 'link').ok, true);   // link is a module part too: allowed
  assert.equal(ejectPart(dst, 'lite').ok, false); assert.equal(ejectPart(dst, 'tools').ok, false); assert.equal(ejectPart(dst, 'zzz').ok, false);
});

test('a full install records its profile and keeps every part', async () => {
  const dst = path.join(tmp('full-'), 'inst'), rel = makeCompRelease('1.0.1', LITE);
  assert.equal((await installRelease({ target: dst, source: { type: 'local', path: rel } })).ok, true);
  const j = JSON.parse(read(dst, 'install.json')); assert.equal(j.profile, 'full'); assert.equal(j.parts, undefined); assert.ok(fs.existsSync(path.join(dst, 'Suite/modules/spotify/s.py')));
});
