// Update files shared between two paired PCs (local-only update source). Run: node src/updcheck.mjs
process.env.PINGUINO_NEVER_REAL_OBS = '1';   // tests must never reach the real OBS
import { spawn } from 'node:child_process';
import os from 'node:os';
import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const cli = fileURLToPath(new URL('./cli.mjs', import.meta.url));
const results = [];
const check = (name, ok, extra = '') => { results.push(ok); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${ok ? '' : '  ' + extra}`); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const until = async (fn, ms = 20000) => { const t = Date.now(); while (Date.now() - t < ms) { try { const v = await fn(); if (v) return v; } catch {} await sleep(300); } return null; };

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
const sha = b => crypto.createHash('sha256').update(b).digest('hex');

async function node(name, port, role) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), `plink-up-${name}-`));
  fs.mkdirSync(path.join(dir, 'link'), { recursive: true });
  const lite = path.join(dir, 'lite');
  const cfg = { role, hub: 'x', port, token: `module-token-${name}-module-token-0003`, inbox: dir, obs: { host: '127.0.0.1', port: 1, password: 'x' }, macros: {}, claude: { enabled: false, cli: 'claude' } };
  fs.writeFileSync(path.join(dir, 'link', 'config.json'), JSON.stringify(cfg));
  const child = spawn(process.execPath, [cli, 'serve'], { stdio: 'ignore', windowsHide: true,
    env: { ...process.env, PINGUINO_LINK_PORT: String(port), PINGUINO_API_TOKEN: `core-${name}`, PINGUINO_DATA_DIR: dir, PINGUINO_MESH_TEST: '1', PINGUINO_CORE_URL: 'http://127.0.0.1:1', PINGUINO_LITE_DIR: lite, PINGUINO_LITE_VERSION: '0.1.0' } });
  const base = `http://127.0.0.1:${port}`;
  const call = async (method, p, body, headers = {}) => {
    const r = await fetch(base + p, { method, signal: AbortSignal.timeout(60000), headers: { 'x-link-token': `core-${name}`, ...(body !== undefined ? { 'content-type': 'application/json' } : {}), ...headers }, body: body === undefined ? undefined : JSON.stringify(body) });
    return { status: r.status, json: await r.json().catch(() => ({})) };
  };
  await until(async () => (await fetch(base + '/api/health')).ok);
  return { dir, lite, child, call, base };
}
const pa = 8100 + Math.floor(Math.random() * 40), pb = pa + 50;
const A = await node('A', pa, 'hub'), B = await node('B', pb, 'client');
try {
  await A.call('POST', '/api/settings', { changes: { 'device.name': 'hubpc' } });
  await B.call('POST', '/api/settings', { changes: { 'device.name': 'clientpc' } });

  // A has: a good package, a tampered package (sidecar says something else), an old Lite installer, a newer one
  const pk = path.join(A.lite, 'packages'), st = path.join(A.lite, 'staging');
  fs.mkdirSync(pk, { recursive: true }); fs.mkdirSync(st, { recursive: true });
  const good = makeZip({ 'module.json': JSON.stringify({ id: 'demo', version: '1.0.0', name: 'Demo' }) });
  fs.writeFileSync(path.join(pk, 'demo-1.0.0.zip'), good); fs.writeFileSync(path.join(pk, 'demo-1.0.0.zip.sha256'), sha(good));
  fs.writeFileSync(path.join(pk, 'bad-1.0.0.zip'), 'tampered'); fs.writeFileSync(path.join(pk, 'bad-1.0.0.zip.sha256'), sha('original'));
  fs.writeFileSync(path.join(st, 'PinguinoLite-0.2.0-setup.exe'), 'installer'); fs.writeFileSync(path.join(st, 'PinguinoLite-0.2.0-setup.exe.sha256'), sha('installer'));
  fs.writeFileSync(path.join(st, 'PinguinoLite-0.0.5-setup.exe'), 'old'); fs.writeFileSync(path.join(st, 'PinguinoLite-0.0.5-setup.exe.sha256'), sha('old'));
  fs.writeFileSync(path.join(pk, 'nohash-1.0.0.zip'), 'x');                       // no sidecar: must not be offered

  const { json: code } = await A.call('POST', '/api/mesh/pair/start', {});
  const joining = B.call('POST', '/api/mesh/pair/join', { addr: `127.0.0.1:${pa}`, code: code.code });
  const pend = await until(async () => (await A.call('GET', '/api/mesh/status')).json.pending?.[0]);
  await A.call('POST', '/api/mesh/pair/approve', { id: pend.id, allow: true });
  check('pairing completes', (await joining).status === 200);
  await until(async () => (await B.call('GET', '/api/mesh/status')).json.peers.length === 1);

  const nobody = await fetch(A.base + '/api/mesh/updates/list', { method: 'POST', headers: { 'content-type': 'application/json', 'x-link-peer': 'nope', 'x-link-token': 'z'.repeat(40) }, body: '{}' });
  check('unpaired caller cannot list updates (401)', nobody.status === 401);
  check('module token alone is not enough (401)', (await A.call('POST', '/api/mesh/updates/list', {})).status === 401);

  // B asks for a check: it pulls from A
  fs.mkdirSync(path.join(B.lite, 'requests'), { recursive: true });
  fs.writeFileSync(path.join(B.lite, 'requests', '1-check.json'), JSON.stringify({ schema: 1, action: 'check', id: null }));
  const got = await until(() => fs.existsSync(path.join(B.lite, 'packages', 'demo-1.0.0.zip.sha256')));
  check('B fetched the good package from A with its hash file', !!got && sha(fs.readFileSync(path.join(B.lite, 'packages', 'demo-1.0.0.zip'))) === sha(good));
  await until(() => fs.existsSync(path.join(B.lite, 'update_manifest.json')));
  check('B fetched the newer Lite installer and offers it', fs.existsSync(path.join(B.lite, 'staging', 'PinguinoLite-0.2.0-setup.exe')) && JSON.parse(fs.readFileSync(path.join(B.lite, 'update_manifest.json'), 'utf8')).latest_version === '0.2.0');
  check('tampered package was discarded', !fs.existsSync(path.join(B.lite, 'packages', 'bad-1.0.0.zip')));
  check('older Lite installer and hashless package were not fetched', !fs.existsSync(path.join(B.lite, 'staging', 'PinguinoLite-0.0.5-setup.exe')) && !fs.existsSync(path.join(B.lite, 'packages', 'nohash-1.0.0.zip')));
  check('nothing was installed automatically', !fs.existsSync(path.join(B.dir, 'modules')));

  // path traversal through the peer route
  const sid = JSON.parse(fs.readFileSync(path.join(B.dir, 'link', 'mesh.json'), 'utf8'));
  const peer = Object.values(sid.peers)[0];
  const trav = await fetch(A.base + '/api/mesh/updates/get', { method: 'POST', headers: { 'content-type': 'application/json', 'x-link-peer': sid.self?.id || sid.id || peer.id, 'x-link-token': peer.outToken || peer.token || peer.out || '' }, body: JSON.stringify({ name: '../config.json' }) });
  check('path traversal name is refused (401/404, never the file)', [401, 404].includes(trav.status));

  await A.call('POST', '/api/settings', { changes: { 'mesh.shareUpdates': false } });
  fs.rmSync(path.join(B.lite, 'packages'), { recursive: true, force: true });
  fs.writeFileSync(path.join(B.lite, 'requests', '2-check.json'), JSON.stringify({ schema: 1, action: 'check', id: null }));
  await sleep(4000);
  check('A can switch sharing off (B gets nothing)', !fs.existsSync(path.join(B.lite, 'packages', 'demo-1.0.0.zip')));
} finally {
  for (const n of [A, B]) { n.child.kill(); try { fs.rmSync(n.dir, { recursive: true, force: true }); } catch {} }
}
const failed = results.filter(r => !r).length;
console.log(failed ? `\n${failed} check(s) FAILED` : '\nAll update sharing checks passed');
process.exit(failed ? 1 : 0);
