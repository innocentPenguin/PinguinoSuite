// PinguinoLite's own Link child must reuse a Link that already runs on the port. Run: node src/reusecheck.mjs
process.env.PINGUINO_NEVER_REAL_OBS = '1';
import { spawn } from 'node:child_process'; import os from 'node:os'; import fs from 'node:fs'; import path from 'node:path'; import { fileURLToPath } from 'node:url';
const cli = fileURLToPath(new URL('./cli.mjs', import.meta.url));
const results = []; const check = (n, ok, x = '') => { results.push(ok); console.log(`${ok ? 'PASS' : 'FAIL'}  ${n}${ok ? '' : '  ' + x}`); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const port = 8200 + Math.floor(Math.random() * 90), dir = fs.mkdtempSync(path.join(os.tmpdir(), 'plink-reuse-')), lite = path.join(dir, 'lite');
fs.mkdirSync(path.join(dir, 'link'), { recursive: true });
fs.writeFileSync(path.join(dir, 'link', 'config.json'), JSON.stringify({ role: 'client', hub: 'x', port, token: 'module-token-module-token-0009', inbox: dir, obs: { host: '127.0.0.1', port: 1, password: 'x' }, macros: {}, claude: { enabled: false, cli: 'claude' } }));
const base = { ...process.env, PINGUINO_LINK_PORT: String(port), PINGUINO_DATA_DIR: dir, PINGUINO_CORE_URL: 'http://127.0.0.1:1', PINGUINO_MESH_TEST: '1' };
const a = spawn(process.execPath, [cli, 'serve'], { stdio: 'ignore', windowsHide: true, env: { ...base, PINGUINO_API_TOKEN: 'core-a', PINGUINO_LITE_DIR: lite } });
try {
  for (let i = 0; i < 40; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) break; } catch {} await sleep(250); }
  const run = env => new Promise(res => { const c = spawn(process.execPath, [cli, 'serve'], { stdio: 'ignore', windowsHide: true, env }); const t = setTimeout(() => { c.kill(); res('timeout'); }, 15000); c.on('exit', code => { clearTimeout(t); res(code); }); });
  const { PINGUINO_API_TOKEN, ...noTok } = base;
  check('Lite-started Link exits 0 when a Link already runs', (await run({ ...noTok, PINGUINO_LITE_DIR: lite })) === 0);
  check('a Suite-started duplicate (has core token) still fails loudly (exit 1)', (await run({ ...base, PINGUINO_API_TOKEN: 'core-b' })) === 1);
  check('the first Link is still healthy', (await fetch(`http://127.0.0.1:${port}/api/health`)).ok);
} finally { a.kill(); try { fs.rmSync(dir, { recursive: true, force: true }); } catch {} }
const failed = results.filter(r => !r).length; console.log(failed ? `\n${failed} FAILED` : '\nAll reuse checks passed'); process.exit(failed ? 1 : 0);
