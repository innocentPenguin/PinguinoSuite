// Cross-platform integration self-check. Run: node src/selfcheck.mjs
// Starts the server on a spare port and verifies health, token, Origin and Host handling.
import { spawn } from 'node:child_process';
import os from 'node:os';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import * as cfgm from './config.mjs';
import * as ts from './tailscale.mjs';

const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'plink-'));   // proves PINGUINO_DATA_DIR is honoured
const port = 7800 + Math.floor(Math.random() * 100);
const base = `http://127.0.0.1:${port}`;
const child = spawn(process.execPath, [new URL('./cli.mjs', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'), 'serve'],
  { env: { ...process.env, PINGUINO_LINK_PORT: String(port), PINGUINO_API_TOKEN: 'selfcheck-core', PINGUINO_DATA_DIR: dataDir }, stdio: 'ignore', windowsHide: true });

const results = [];
const check = (name, ok) => { results.push(ok); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}`); };
const code = async (path, opts = {}) => { try { return (await fetch(base + path, { signal: AbortSignal.timeout(3000), ...opts })).status; } catch { return 0; } };

console.log(`platform ${os.platform()} ${os.arch()} · node ${process.versions.node}`);
check('node >= 22', Number(process.versions.node.split('.')[0]) >= 22);
const bin = await ts.resolveBin();
console.log(`info  tailscale cli: ${bin} (${(await ts.installed()) ? 'found' : 'not installed/reachable; optional'})`);

for (let i = 0; i < 20 && await code('/api/health') !== 200; i++) await new Promise(r => setTimeout(r, 500));
let tok = ''; try { tok = JSON.parse(fs.readFileSync(path.join(dataDir, 'link', 'config.json'), 'utf8')).token; } catch {}
check('config written to PINGUINO_DATA_DIR', !!tok);
check('GET /api/health = 200', await code('/api/health') === 200);
check('status without token = 401', await code('/api/status') === 401);
check('status with wrong token = 401', await code('/api/status', { headers: { 'x-link-token': 'nope' } }) === 401);
check('status with module token = 200', await code('/api/status', { headers: { 'x-link-token': tok } }) === 200);
check('status with Suite core token = 200', await code('/api/status', { headers: { 'x-link-token': 'selfcheck-core' } }) === 200);
check('status with Authorization: Bearer core token = 200', await code('/api/status', { headers: { authorization: 'Bearer selfcheck-core' } }) === 200);
check('loopback POST without token = 401', await code('/api/macro/stop', { method: 'POST' }) === 401);
check('foreign Origin = 403', await code('/api/macro/x', { method: 'POST', headers: { origin: 'http://evil.example', 'x-link-token': tok } }) === 403);
const tauri = async o => await code('/api/status', { headers: { origin: o, 'x-link-token': tok } });
check('Tauri origins allowed (3)', (await Promise.all(['tauri://localhost', 'http://tauri.localhost', 'https://tauri.localhost'].map(tauri))).every(c => c === 200));
check('Tauri origin still needs token', await code('/api/status', { headers: { origin: 'tauri://localhost' } }) === 401);
const ps = await fetch(base + '/api/prestream', { headers: { authorization: 'Bearer selfcheck-core' } }).then(r => r.ok ? r.json() : null).then(j => j?.items).catch(() => null);
check('prestream: no token needed, valid items', Array.isArray(ps) && ps.length > 0 && ps.every(i => i.id && i.label && ['pass', 'warn', 'fail'].includes(i.status) && typeof i.detail === 'string'));
check('prestream: no secrets in output', !JSON.stringify(ps).includes(tok) && !JSON.stringify(ps).includes('selfcheck-core'));
let lines = []; try { lines = fs.readFileSync(path.join(dataDir, 'console', 'link.jsonl'), 'utf8').trim().split(/\r?\n/).map(JSON.parse); } catch {}
check('console log: JSONL with ts/module/level/source/msg, no token', lines.length > 0 && lines.every(l => l.ts && l.module === 'link' && l.level && l.source && l.msg) && !JSON.stringify(lines).includes(tok));
console.log('info  prestream: ' + (ps || []).map(i => i.id + '=' + i.status).join(' '));
const page = await fetch(base + '/').catch(() => null);
const csp = page?.headers.get('content-security-policy') || '';
check('page embeddable (no X-Frame-Options, frame-ancestors lists Tauri)', !!page && !page.headers.get('x-frame-options') && csp.includes('tauri.localhost'));

child.kill();
try { fs.rmSync(dataDir, { recursive: true, force: true }); } catch {}
const bad = results.filter(r => !r).length;
console.log(bad ? `\n${bad} check(s) FAILED` : '\nAll checks passed');
process.exit(bad ? 1 : 0);
