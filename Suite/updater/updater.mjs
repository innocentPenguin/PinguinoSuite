// INDEX updater.mjs: PinguinoUpdater CLI. node updater.mjs check|apply|rollback|status [--install <dir>] [--source <folder|zip|https-url>] [--channel stable|beta] [--apply-if-safe]
// Run by the Suite launcher before the window opens (`apply --apply-if-safe` = apply only if you are off stream, else leave a notice). Prints one JSON line.
// Reads <install>\install.json {version, channel, source:{type,path|url}}; Data\ is never touched except Data\updates. Never contacts OBS.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { applyUpdate, checkUpdate, rollbackLatest, dirs } from './lib/apply.mjs';
import { gitStatus, gitUpdate } from './lib/sources.mjs';

const args = process.argv.slice(2), cmd = args[0] || 'status';
const opt = n => { const i = args.indexOf('--' + n); return i >= 0 ? args[i + 1] : undefined; };
const installDir = path.resolve(opt('install') || path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '..'));
const D = dirs(installDir);
const inst = (() => { try { return JSON.parse(fs.readFileSync(D.install, 'utf8')); } catch { return {}; } })();
const current = inst.version || '0.0.0', channel = opt('channel') || inst.channel || 'stable';
const srcArg = opt('source');
const source = srcArg ? (/^https?:/i.test(srcArg) ? { type: 'https', url: srcArg } : { type: 'local', path: srcArg }) : inst.source;
const out = o => { console.log(JSON.stringify(o)); };

async function main() {
  if (cmd === 'status') {
    const rd = f => { try { return JSON.parse(fs.readFileSync(f, 'utf8')); } catch { return null; } };
    return out({ version: current, channel, result: rd(D.result), deferred: rd(D.deferred) });
  }
  if (cmd === 'rollback') return out(rollbackLatest(installDir));
  // git source: the install folder is a clone
  if (!source || source.type === 'git') {
    const g = await gitStatus(installDir, channel).catch(() => ({ isClone: false }));
    if (g.isClone) {
      if (cmd === 'check') return out({ ok: true, source: 'git', current: g.current, newest: g.newest, available: !g.upToDate, dirty: g.dirty });
      if (g.upToDate) return out({ ok: true, source: 'git', message: 'already up to date' });
      if (g.dirty) return out({ ok: false, source: 'git', message: 'local edits in the install folder; not updating' });
      const { hostLiveCheck } = await import('./lib/apply.mjs'); const lv = await hostLiveCheck();
      if (lv.live !== false) return out({ ok: true, source: 'git', deferred: true, message: 'update is waiting until you are off stream' });
      return out({ ok: true, source: 'git', ...(await gitUpdate(installDir, g.newest)), to: g.newest });
    }
    if (!source) return out({ ok: true, message: 'no update source is set (install.json has none), nothing to do' });
  }
  if (cmd === 'check') { const c = await checkUpdate({ source, current, channel }); return out({ ok: true, current, available: c.available, version: c.manifest.version, notes: c.manifest.notes }); }
  if (cmd === 'apply') return out(await applyUpdate({ installDir, source, current, channel }));
  out({ ok: false, message: `unknown command ${cmd}` });
}
main().catch(e => { out({ ok: false, message: String(e.message || e).slice(0, 200) }); process.exitCode = 1; });
