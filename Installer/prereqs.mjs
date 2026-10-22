// INDEX prereqs.mjs: makes a fresh Windows PC ready to run an installed Suite: .NET 8 runtime (Host), Python (core modules), Node 22+ (Link), the Suite venv + its packages.
// node prereqs.mjs --target <install folder> [--no-gpu] [--check]   (--check = report only, installs nothing)
// Uses winget (built into Windows 10/11) for anything missing; each install may show a Windows permission prompt. Prints one JSON line per step. Never touches OBS, Data\ or secrets.
import fs from 'node:fs';
import path from 'node:path';
import { spawn, execFile } from 'node:child_process';

const args = process.argv.slice(2), opt = n => { const i = args.indexOf('--' + n); return i >= 0 ? args[i + 1] : undefined; }, has = n => args.includes('--' + n);
const target = opt('target') && path.resolve(opt('target'));
const say = o => console.log(JSON.stringify(o));
const run = (cmd, a, o = {}) => new Promise(res => execFile(cmd, a, { windowsHide: true, timeout: o.timeout || 20000, cwd: o.cwd, maxBuffer: 8 << 20 }, (e, out, err) => res({ ok: !e, out: String(out || '') + String(err || ''), code: e && e.code })));
const stream = (cmd, a, o = {}) => new Promise(res => {
  const p = spawn(cmd, a, { cwd: o.cwd, windowsHide: true }); let tail = '';
  const eat = d => { tail = (tail + d).slice(-600); };
  p.stdout.on('data', eat); p.stderr.on('data', eat);
  p.on('error', e => res({ ok: false, out: e.message })); p.on('close', c => res({ ok: c === 0, out: tail.trim(), code: c }));
});

async function findPython() {
  const cands = [['py', ['-3.13']], ['py', ['-3.12']], ['py', ['-3.11']], ['py', ['-3.10']], ['python', []], ['python3', []]];
  const local = process.env.LOCALAPPDATA || '';
  for (const v of ['313', '312', '311']) cands.push([path.join(local, 'Programs', 'Python', `Python${v}`, 'python.exe'), []]);
  for (const [c, pre] of cands) {
    const r = await run(c, [...pre, '-c', 'import sys;print(sys.executable);print("%d.%d"%sys.version_info[:2])']);
    if (!r.ok) continue;
    const [exe, ver] = r.out.trim().split(/\r?\n/);
    const [maj, min] = (ver || '').split('.').map(Number);
    if (maj === 3 && min >= 10 && min <= 14 && !/WindowsApps/i.test(exe)) return { exe, ver };
  }
  return null;
}
const dotnetOk = async () => { const r = await run('dotnet', ['--list-runtimes']); return r.ok && /Microsoft\.NETCore\.App 8\./.test(r.out); };
const nodeOk = async () => { const r = await run('node', ['--version']); return r.ok && Number((/v(\d+)/.exec(r.out) || [])[1]) >= 22; };
const hasWinget = async () => (await run('winget', ['--version'])).ok;
const webview2Ok = async () => {   // the runtime lives under EdgeWebView\Application\<version>\msedgewebview2.exe (per-machine or per-user)
  const roots = [process.env['ProgramFiles(x86)'], process.env.ProgramFiles, path.join(process.env.LOCALAPPDATA || '', 'Microsoft')].filter(Boolean);
  for (const r of roots) { try { const app = path.join(r, r.endsWith('Microsoft') ? '' : 'Microsoft', 'EdgeWebView', 'Application'); if (fs.readdirSync(app).some(v => /^\d/.test(v))) return true; } catch {} }
  return false;
};

async function need(name, ok, wingetId, why, manual) {
  if (await ok()) { say({ step: name, ok: true, message: 'already installed' }); return true; }
  if (has('check')) { say({ step: name, ok: false, message: `missing (${why})`, manual }); return false; }
  if (!(await hasWinget())) { say({ step: name, ok: false, message: `missing, and winget is not available. ${manual}` }); return false; }
  say({ progress: `installing ${name} (Windows may ask permission)...` });
  const r = await stream('winget', ['install', '--id', wingetId, '-e', '--silent', '--accept-package-agreements', '--accept-source-agreements', '--disable-interactivity'], { timeout: 900000 });
  const good = r.ok || /already installed|No newer package/i.test(r.out);
  say({ step: name, ok: good && await ok(), message: good ? 'installed' : `winget failed: ${r.out.slice(-200)}`, manual: good ? undefined : manual });
  return good;
}

const results = {};
results.webview2 = await need('WebView2 (app window)', webview2Ok, 'Microsoft.EdgeWebView2Runtime', 'the app window needs it', 'Install "Microsoft Edge WebView2 Runtime" from microsoft.com.');
results.dotnet = await need('.NET 8 runtime (bot Host)', dotnetOk, 'Microsoft.DotNet.Runtime.8', 'the bot Host needs it', 'Install ".NET Runtime 8" from dotnet.microsoft.com/download/dotnet/8.0.');
results.node = await need('Node.js 22+ (PinguinoLink)', nodeOk, 'OpenJS.NodeJS.LTS', 'PinguinoLink needs it', 'Install Node.js LTS (22 or newer) from nodejs.org.');
let py = await findPython();
if (!py) {
  await need('Python 3.12 (core modules)', async () => !!(await findPython()), 'Python.Python.3.12', 'Listen, Multi, Spotify and Voice need it', 'Install Python 3.12 from python.org (tick "Add python.exe to PATH").');
  py = await findPython();
} else say({ step: 'Python (core modules)', ok: true, message: `Python ${py.ver}` });
results.python = !!py;

if (target && py && !has('check')) {
  const venvPy = path.join(target, 'Suite', '.venv', 'Scripts', 'python.exe');
  if (!fs.existsSync(venvPy)) {
    say({ progress: 'creating the Python environment...' });
    const r = await stream(py.exe, ['-m', 'venv', path.join(target, 'Suite', '.venv')]);
    if (!r.ok) say({ step: 'Python environment', ok: false, message: r.out.slice(-200) });
  }
  if (fs.existsSync(venvPy)) {
    let req = path.join(target, 'Suite', 'requirements.txt');
    const gpu = !has('no-gpu') && (await run('nvidia-smi', [])).ok;
    if (!gpu && fs.existsSync(req)) {   // no NVIDIA card: skip the multi-GB CUDA libraries (Listen then uses the CPU)
      const lite = path.join(target, 'Data', 'runtime', 'requirements.cpu.txt');
      fs.mkdirSync(path.dirname(lite), { recursive: true });
      fs.writeFileSync(lite, fs.readFileSync(req, 'utf8').split(/\r?\n/).filter(l => !/^nvidia-/.test(l.trim())).join('\n'));
      req = lite;
    }
    say({ progress: `installing Python packages (${gpu ? 'with' : 'without'} NVIDIA libraries; the first run downloads a lot)...` });
    await stream(venvPy, ['-m', 'pip', 'install', '-q', '--upgrade', 'pip'], { cwd: target });
    const r = await stream(venvPy, ['-m', 'pip', 'install', '-q', '-r', req], { cwd: target });
    say({ step: 'Python packages', ok: r.ok, message: r.ok ? 'installed' : `pip failed: ${r.out.slice(-250)}` });
    results.packages = r.ok;
  }
}
const allOk = Object.values(results).every(Boolean);
say({ ok: allOk, done: true, message: allOk ? 'everything the Suite needs is ready' : 'some prerequisites are missing (see above); the installer can be run again to retry' });
process.exitCode = allOk ? 0 : 1;
