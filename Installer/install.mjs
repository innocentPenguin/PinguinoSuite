// INDEX install.mjs: PinguinoSuite Installer (CLI). Tries git first, then a network release, then a local folder/zip/USB.
// node install.mjs --target <empty folder> [--repo <git url> --tag vX.Y.Z] [--url <https manifest url>] [--local <folder|zip>] [--channel stable|beta] [--shortcuts]
// Installs app + core + Host + modules from the release (no Data\, no secrets). Never runs over an existing install. First run asks nothing sensitive.
import fs from 'node:fs';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { installRelease, makeShortcuts } from '../Suite/updater/lib/install.mjs';

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

async function main() {
  const tried = [];
  const attempts = [];
  if (opt('repo')) attempts.push(['git', () => viaGit(opt('repo'), opt('tag'))]);
  if (opt('url')) attempts.push(['network', () => installRelease({ target, channel, source: { type: 'https', url: opt('url') }, pubkey: opt('pubkey') || null })]);
  if (opt('local')) attempts.push(['local', () => installRelease({ target, channel, source: { type: 'local', path: opt('local') }, pubkey: opt('pubkey') || null })]);
  if (!attempts.length) return out({ ok: false, message: 'give at least one source: --repo, --url or --local' });
  for (const [name, run] of attempts) {
    try {
      const r = await run();
      if (r.ok) {
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
