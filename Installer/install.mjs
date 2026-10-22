// INDEX install.mjs: PinguinoSuite Installer (CLI). Tries git first, then a network release, then a local folder/zip/USB.
// Private repo: --github owner/name [--tag vX] [--key-file install.key.enc]; the install passphrase comes from the PG_KEY_PASS environment variable (never a command-line argument).
// The read-only token is unsealed in memory, used for the download, then stored DPAPI-encrypted in Data/runtime so the Updater can keep updating from the repo.
// --prereqs also installs/checks .NET, Python, Node and the Suite venv (winget). --update-from owner/name records the repo as the update source of a --local install.
// node install.mjs --target <empty folder> [--repo <git url> --tag vX.Y.Z] [--url <https manifest url>] [--local <folder|zip>] [--channel stable|beta] [--shortcuts]
// Installs app + core + Host + modules from the release (no Data\, no secrets). Never runs over an existing install. First run asks nothing sensitive.
import fs from 'node:fs';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { installRelease, makeShortcuts } from '../Suite/updater/lib/install.mjs';
import { unseal, storeToken } from '../Suite/updater/lib/secret.mjs';
import { setToken } from '../Suite/updater/lib/sources.mjs';

const args = process.argv.slice(2);
const opt = n => { const i = args.indexOf('--' + n); return i >= 0 ? args[i + 1] : undefined; };
const has = n => args.includes('--' + n);
const out = o => console.log(JSON.stringify(o));
const target = opt('target'), channel = opt('channel') || 'stable';
if (!target) { out({ ok: false, message: 'usage: install.mjs --target <folder> [--repo <git url>] [--url <https manifest>] [--local <folder|zip>] [--shortcuts]' }); process.exit(2); }

const sh = (cmd, a, cwd) => new Promise((res, rej) => execFile(cmd, a, { cwd, windowsHide: true, timeout: 600000 }, (e, o, er) => e ? rej(new Error((er || e.message).trim().slice(0, 300))) : res(o.trim())));

async function viaGit(repo, tag) {
  if (!/^https:\/\/|^git@|^[A-Za-z]:\\|^\//.test(repo)) throw new Error('repo must be an https address, ssh address or local path');
  await sh('git', ['--version']);
  const dst = path.resolve(target);
  if (fs.existsSync(dst) && fs.readdirSync(dst).length) throw new Error('that folder is not empty; pick an empty folder');
  await sh('git', ['clone', '--quiet', ...(tag ? ['--branch', tag] : []), repo, dst]);
  fs.mkdirSync(path.join(dst, 'Data', 'runtime'), { recursive: true });
  fs.writeFileSync(path.join(dst, 'install.json'), JSON.stringify({ schema: 1, version: (tag || 'git').replace(/^v/, ''), channel, installed_at: new Date().toISOString(), source: { type: 'git', url: repo } }, null, 2));
  return { ok: true, message: `PinguinoSuite cloned into ${dst}; build it with App\\Setup-Suite.ps1`, version: tag || 'git', via: 'git' };
}

function prereqs() {   // relays the prerequisite steps as progress lines; a failure here does not undo the install
  return new Promise(res => {
    const p = execFile(process.execPath, [path.join(path.dirname(fileURLToPath(import.meta.url)), 'prereqs.mjs'), '--target', path.resolve(target)], { windowsHide: true, maxBuffer: 16 << 20, timeout: 3 * 3600 * 1000 });
    let buf = '', ok = false;
    p.stdout.on('data', d => { buf += d; let i; while ((i = buf.indexOf(String.fromCharCode(10))) >= 0) { const ln = buf.slice(0, i).trim(); buf = buf.slice(i + 1); try { const o = JSON.parse(ln); if (o.done) ok = !!o.ok; out({ progress: o.progress || (o.step ? `${o.step}: ${o.message}` : o.message) }); } catch {} } });
    p.on('close', () => res(ok));
  });
}

async function main() {
  const tried = [];
  const attempts = [];
  let token = null, recordSource = null;
  const keyFile = opt('key-file') || (fs.existsSync(path.join(path.dirname(fileURLToPath(import.meta.url)), 'install.key.enc')) ? path.join(path.dirname(fileURLToPath(import.meta.url)), 'install.key.enc') : null);
  if ((opt('github') || opt('update-from')) && keyFile) {
    const pass = process.env.PG_KEY_PASS || '';
    try { token = unseal(fs.readFileSync(keyFile), pass); setToken(token); }
    catch (e) { return out({ ok: false, message: String(e.message), needsPassphrase: true }); }
  }
  if (opt('github') && !token) return out({ ok: false, message: 'the private repo needs its install key (install.key.enc) and passphrase' });
  const ghRepo = opt('github') || opt('update-from');
  if (ghRepo) recordSource = { type: 'github', repo: ghRepo };
  else if (opt('local')) recordSource = false;   // a bundled/USB release is not an update source: record none (the temp folder it came from is gone afterwards)
  if (opt('github')) attempts.push(['private repo', () => installRelease({ target, channel, source: { type: 'github', repo: opt('github'), tag: opt('tag') }, pubkey: opt('pubkey') || null, token })]);
  if (opt('repo')) attempts.push(['git', () => viaGit(opt('repo'), opt('tag'))]);
  if (opt('url')) attempts.push(['network', () => installRelease({ target, channel, source: { type: 'https', url: opt('url') }, pubkey: opt('pubkey') || null })]);
  if (opt('local')) attempts.push(['local', () => installRelease({ target, channel, source: { type: 'local', path: opt('local') }, pubkey: opt('pubkey') || null, recordSource })]);
  if (!attempts.length) return out({ ok: false, message: 'give at least one source: --repo, --url or --local' });
  for (const [name, run] of attempts) {
    if (has('progress')) out({ progress: `trying ${name}` });
    try {
      const r = await run();
      if (r.ok) {
        if (token) { try { storeToken(path.resolve(target), token); r.keyStored = true; } catch (e) { r.keyStored = false; r.keyError = String(e.message).slice(0, 120); } }
        if (has('prereqs')) r.prereqs = await prereqs();
        if (has('shortcuts')) { try { r.shortcuts = makeShortcuts({ target }); } catch (e) { r.shortcutsError = String(e.message).slice(0, 120); } }
        return out({ ...r, via: name, tried });
      }
      tried.push(`${name}: ${r.message}`);
    } catch (e) { tried.push(`${name}: ${String(e.message).slice(0, 160)}`); }
  }
  out({ ok: false, message: 'every source failed; nothing was installed', tried });
  process.exitCode = 1;
}
main();
