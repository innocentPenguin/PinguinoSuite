// Regression tests for the 53 security review, batch 3: crash-safe secrets files, OBS allow-list, token page behind proxies,
// unauthenticated prestream, zip names, test hooks. Run: node src/auditcheck5.mjs   (loopback only, temp dirs, no OBS)
import './testenv.mjs';
import { spawn } from 'node:child_process';
import os from 'node:os';
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import { fileURLToPath } from 'node:url';
import { writeJsonAtomic, readJsonSafe } from './safefile.mjs';
import { customSteps, goesLive, runRequests } from './obs.mjs';
import * as macros from './macros.mjs';
import { extractZip, writeZip } from './pkg.mjs';
import { testHook } from './testhook.mjs';

const cli = fileURLToPath(new URL('./cli.mjs', import.meta.url));
let bad = 0;
const check = (n, c, x = '') => { console.log(`${c ? 'PASS' : 'FAIL'}  ${n}${c ? '' : '  ' + x}`); if (!c) bad++; };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const until = async (fn, ms = 20000) => { const t = Date.now(); while (Date.now() - t < ms) { try { const v = await fn(); if (v) return v; } catch {} await sleep(300); } return null; };
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'plink-a5-'));

// 1. secrets files: atomic write, .bak, never a silent reset
const f = path.join(tmp, 'x.json');
check('missing file gives the fallback', readJsonSafe(f, { a: 1 }).a === 1);
writeJsonAtomic(f, { v: 1 }); writeJsonAtomic(f, { v: 2 });
check('atomic write leaves the new file, the old one as .bak, no .tmp', readJsonSafe(f).v === 2 && JSON.parse(fs.readFileSync(f + '.bak', 'utf8')).v === 1 && !fs.existsSync(f + '.tmp'));
fs.writeFileSync(f, '{"v":3,'); // half-written
let warned = ''; const got = readJsonSafe(f, {}, m => { warned = m; });
check('half-written file is restored from .bak with a warning', got.v === 1 && /damaged/.test(warned));
fs.rmSync(f + '.bak'); fs.writeFileSync(f, '{"v":3,');
let thrown = ''; try { readJsonSafe(f); } catch (e) { thrown = e.message; }
check('damaged file with no .bak stops instead of resetting', /damaged/.test(thrown) && fs.readFileSync(f, 'utf8') === '{"v":3,');
fs.writeFileSync(f, ''); check('an empty file is treated as new', Object.keys(readJsonSafe(f)).length === 0);

// 2. OBS request allow-list and wider go-live list
check('custom request types are listed', customSteps([{ type: 'SetStreamServiceSettings' }, { type: 'GetVersion' }, { type: 'SetCurrentProgramScene' }]).join() === 'SetStreamServiceSettings');
check('output, hotkey, service and caption requests count as going live', ['StartOutput', 'ToggleOutput', 'TriggerHotkeyByName', 'TriggerHotkeyBySequence', 'SetStreamServiceSettings', 'SendStreamCaption', 'ToggleStream'].every(t => goesLive([{ type: t }])));
let rej = null; try { await runRequests({ host: '127.0.0.1', port: 1, password: 'x' }, [{ type: 'CreateScene', data: { sceneName: 'x' } }]); } catch (e) { rej = e; }
check('an unknown request type is refused before any connection (403)', rej?.status === 403 && /allowCustomSteps/.test(rej.message), String(rej?.message));
check('ToggleStream marks a macro risky', macros.isRisky({ macros: { m: [{ type: 'ToggleStream' }] } }, 'm'));

// 3. zip names
const zipOf = n => { const z = path.join(tmp, 'z-' + Math.random().toString(16).slice(2) + '.zip'); fs.writeFileSync(z, writeZip([{ name: n, data: Buffer.from('x') }])); return z; };
const tries = n => { try { extractZip(zipOf(n), fs.mkdtempSync(path.join(tmp, 'e-'))); return 'ok'; } catch (e) { return e.message; } };
check('normal names extract', tries('data/a.txt') === 'ok');
check('trailing dot or space is refused', /unsafe/.test(tries('x./y')) && /unsafe/.test(tries('a/b ')));
check('Windows device names are refused', /unsafe/.test(tries('NUL')) && /unsafe/.test(tries('sub/aux.txt')) && /unsafe/.test(tries('COM1')));

// 4. test hooks are inert in a real run
process.env.PINGUINO_LITE_TEST = '1';
const keep = [process.env.PINGUINO_API_TOKEN, process.env.PINGUINO_DATA_DIR];
process.env.PINGUINO_API_TOKEN = 'real'; process.env.PINGUINO_DATA_DIR = 'D:\\PinguinoSuite\\Data';
check('test hook is off when a real Suite token and data dir are present', testHook('PINGUINO_LITE_TEST') === false);
process.env.PINGUINO_DATA_DIR = path.join(tmp, 'd');
check('test hook is on for a temp data dir', testHook('PINGUINO_LITE_TEST') === true);
process.env.PINGUINO_LITE_TEST = 'yes'; check('only the exact value 1 counts', testHook('PINGUINO_LITE_TEST') === false);
delete process.env.PINGUINO_LITE_TEST;
for (const [k, v] of [['PINGUINO_API_TOKEN', keep[0]], ['PINGUINO_DATA_DIR', keep[1]]]) { if (v === undefined) delete process.env[k]; else process.env[k] = v; }

// 4b. rejected-request log is rate-limited per caller and path
const { logDenied } = await import('./server.mjs');
const dreq = (ua, u = '/api/obs?x=1') => ({ method: 'GET', url: u, headers: ua ? { 'user-agent': ua } : {} });
const t0 = 1_000_000;
const first = logDenied(dreq('python-requests/2'), t0);
let more = 0; for (let i = 1; i < 300; i++) if (logDenied(dreq('python-requests/2'), t0 + i * 3000 % 59000)) more++;
check('300 rejected polls inside a minute write one log line', first === true && more === 0, `more=${more}`);
check('the next minute logs again, other callers and paths have their own line', logDenied(dreq('python-requests/2'), t0 + 61000) === true && logDenied(dreq('curl/8'), t0 + 100) === true && logDenied(dreq('python-requests/2', '/api/status'), t0 + 100) === true);

const { warnLimited } = await import('./server.mjs');
let wl = 0; for (let i = 0; i < 100; i++) if (warnLimited('http', 'POST /api/peer/broadcast: bad peer token (401)', t0 + i * 500)) wl++;
check('repeated client-error lines (mesh 401, bad Host, foreign Origin) are limited too', wl === 1, String(wl));

// 4c. a command that cannot even be started (spawn UNKNOWN on Windows throws synchronously) must resolve, not crash
const tsm = await import('./tailscale.mjs');
const bogus = await tsm.run('x'.repeat(40000), ['version'], { timeout: 2000 });   // absurdly long path: spawn fails at once
check('a command that cannot be started gives ok:false instead of throwing', bogus.ok === false && typeof bogus.stderr === 'string');
const nope = await tsm.run(path.join(tmp, 'no', 'such', 'tailscale.exe'), ['status'], { timeout: 2000 });
check('a missing binary gives ok:false', nope.ok === false);

// 5. spawned Link: token page behind a proxy, prestream, headers
const dir = path.join(tmp, 'run'); fs.mkdirSync(path.join(dir, 'link'), { recursive: true });
const port = 9200 + Math.floor(Math.random() * 90), TOKEN = 'module-token-5-module-token-0005';
fs.writeFileSync(path.join(dir, 'link', 'config.json'), JSON.stringify({ role: 'hub', hub: 'x', port, token: TOKEN, inbox: dir, obs: { host: '127.0.0.1', port: 1, password: 'x' }, macros: {}, claude: { enabled: false, cli: 'claude' } }));
const child = spawn(process.execPath, [cli, 'serve'], { stdio: 'ignore', windowsHide: true, env: { ...process.env, PINGUINO_LINK_PORT: String(port), PINGUINO_API_TOKEN: 'core-5', PINGUINO_DATA_DIR: dir, PINGUINO_MESH_TEST: '1', PINGUINO_CORE_URL: 'http://127.0.0.1:8760', PINGUINO_LITE_DIR: path.join(dir, 'lite') } });
// node's fetch cannot set Host/Via freely; use http.request
const req = (p, headers = {}) => new Promise((resolve, reject) => { const r = http.request({ host: '127.0.0.1', port, path: p, headers }, res => { let b = ''; res.on('data', c => b += c); res.on('end', () => resolve({ status: res.statusCode, headers: res.headers, body: b })); }); r.on('error', reject); r.end(); });
try {
  await until(async () => (await req('/api/health')).status === 200);
  const page = await req('/');
  check('plain loopback visit gets the page with the token', page.status === 200 && page.body.includes(TOKEN));
  check('page carries nosniff, no-referrer and a narrow frame-ancestors', page.headers['x-content-type-options'] === 'nosniff' && page.headers['referrer-policy'] === 'no-referrer' && /frame-ancestors/.test(page.headers['content-security-policy']) && !/127\.0\.0\.1:\*/.test(page.headers['content-security-policy']), JSON.stringify(page.headers));
  const script = /<script>([\s\S]*)<\/script>/.exec(page.body)?.[1] || '';
  let syntaxOk = true; try { new Function(script); } catch { syntaxOk = false; }
  check('page has the Morning check button and its script parses', page.body.includes('id=morningbtn') && syntaxOk);
  const mo = await req('/api/morning', { 'x-link-token': TOKEN });
  const mj = JSON.parse(mo.body || '{}');
  check('/api/morning returns plain lines for the button', mo.status === 200 && typeof mj.headline === 'string' && Array.isArray(mj.lines) && mj.lines.length > 0 && mj.lines.every(l => l.label && l.text && ['good', 'note', 'bad'].includes(l.status)));
  check('/api/morning needs the token', (await req('/api/morning')).status === 401);
  const viaProxy = await req('/', { 'x-forwarded-for': '203.0.113.9' });
  check('same request through a proxy (X-Forwarded-For) does NOT get the token', !viaProxy.body.includes(TOKEN) && viaProxy.status !== 200 || (viaProxy.status === 200 && !viaProxy.body.includes(TOKEN)), String(viaProxy.status));
  const viaTs = await req('/', { host: 'ivansserver.tail1234.ts.net' });
  check('a tailnet Host name does not get the token either', !viaTs.body.includes(TOKEN));
  check('health answers with nosniff', (await req('/api/health')).headers['x-content-type-options'] === 'nosniff');
  const pre = await req('/api/prestream');
  check('prestream works for the local Suite', pre.status === 200);
  const preProxy = await req('/api/prestream', { 'x-forwarded-for': '203.0.113.9' });
  check('prestream through a proxy without a token is 401', preProxy.status === 401, String(preProxy.status));
  const preTok = await req('/api/prestream', { 'x-forwarded-for': '203.0.113.9', 'x-link-token': TOKEN });
  check('prestream with the token works', preTok.status === 200);
} finally { child.kill(); await sleep(300); try { fs.rmSync(tmp, { recursive: true, force: true }); } catch {} }
console.log(bad ? `\n${bad} check(s) FAILED` : '\nAll audit-5 batch-3 checks passed');
process.exit(bad ? 1 : 0);
