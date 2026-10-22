// INDEX updater.mjs: PinguinoUpdater CLI. node updater.mjs check|apply|rollback|status [--install <dir>] [--source <folder|zip|https-url>] [--channel stable|beta] [--apply-if-safe] [--only listen,multi] [--stage]
// Run by the Suite launcher before the window opens (`apply --apply-if-safe` = apply only if you are off stream, else leave a notice). Prints one JSON line.
// Reads <install>\install.json {version, channel, source:{type,path|url}}; Data\ is never touched except Data\updates. Never contacts OBS.
import fs from 'node:fs';
import net from 'node:net';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { ejectPart, verifyParts } from './lib/parts.mjs';
import { applyUpdate, checkUpdate, rollbackLatest, rollbackPlan, dirs, hostLiveCheck } from './lib/apply.mjs';
import { COMPONENTS, COMPONENT_IDS } from './lib/components.mjs';
import { gitStatus, gitUpdate, setToken } from './lib/sources.mjs';
import { loadToken } from './lib/secret.mjs';

const args = process.argv.slice(2), cmd = args[0] || 'status';
const opt = n => { const i = args.indexOf('--' + n); return i >= 0 ? args[i + 1] : undefined; };
const installDir = path.resolve(opt('install') || path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '..'));
const D = dirs(installDir);
const inst = (() => { try { return JSON.parse(fs.readFileSync(D.install, 'utf8')); } catch { return {}; } })();
const current = inst.version || '0.0.0', channel = opt('channel') || inst.channel || 'stable';
const srcArg = opt('source'), pubkey = opt('pubkey') || inst.pubkey || null;
const source = srcArg ? (/^https?:/i.test(srcArg) ? { type: 'https', url: srcArg } : { type: 'local', path: srcArg }) : inst.source;
const out = o => { console.log(JSON.stringify(o)); };
const rd = f => { try { return JSON.parse(fs.readFileSync(f, 'utf8')); } catch { return null; } };
const only = opt('only') ? opt('only').split(',').map(s => s.trim()).filter(Boolean) : null;
if (source && source.type === 'github') setToken(loadToken(installDir));   // DPAPI file written by the installer; null = the update says it needs the key

const appRunning = port => new Promise(res => { const s = net.connect({ port, host: '127.0.0.1' }); const done = v => { s.destroy(); res(v); }; s.setTimeout(800, () => done(true)); s.on('connect', () => done(true)); s.on('error', e => done(e.code !== 'ECONNREFUSED')); });

async function main() {
  // launch hook: `launch` (or --apply-if-safe) = apply only when the setting allows it AND the Suite is not already running (never swap files under a running app)
  if (cmd === 'launch' || args.includes('--apply-if-safe')) {
    if (await appRunning(Number(opt('core-port')) || 8760)) return out({ ok: true, skipped: true, message: 'the Suite is already running; not updating under it' });
    // a part staged from the Updates card (shell/core/Host files of the app) is swapped here, while nothing is running
    if (rd(D.rollbackPending)) { try { fs.unlinkSync(D.rollbackPending); } catch {} return out(rollbackLatest(installDir)); }   // a rollback that touched app files, parked until nothing is running
    const pend = rd(D.pending);
    if (pend && pend.source) {
      if (pend.source.type === 'github') setToken(loadToken(installDir));
      return out(await applyUpdate({ installDir, source: pend.source, current, channel: pend.channel || channel, pubkey, only: pend.only }));
    }
    if (!source) return out({ ok: true, skipped: true, message: 'no update source is set' });
    if (inst.auto_update !== true) return out({ ok: true, skipped: true, message: 'automatic updates are off; use Settings > Updates' });
  }
  const cmd2 = (cmd === 'launch' || (cmd === 'check' && args.includes('--apply-if-safe'))) ? 'apply' : cmd;
  if (cmd === 'status') {
    return out({ version: current, channel, profile: inst.profile || 'full', parts: inst.parts || null, result: rd(D.result), deferred: rd(D.deferred), pending: rd(D.pending), components: inst.components || null });
  }
  if (cmd === 'eject') {   // eject --part <id>: move an on-demand part (a module) out of the install; the caller stops it first, Data\ is never touched
    const part = opt('part'); if (!part) return out({ ok: false, message: 'give --part <id>' });
    if (await hostLiveCheck().then(l => l.live !== false)) return out({ ok: false, message: 'not while live (or when it cannot be told)' });
    return out(ejectPart(installDir, part));
  }
  if (cmd === 'verify') {   // verify [--only a,b]: read-only comparison of installed parts with the release
    if (!source) return out({ ok: false, message: 'no update source is set; cannot compare' });
    return out(await verifyParts({ installDir, source, channel, pubkey, only }));
  }
  if (cmd === 'rollback') {
    const plan = rollbackPlan(installDir);
    if (args.includes('--plan')) return out(plan ? { ok: true, ...plan } : { ok: false, message: 'there is no backup to restore' });
    if (plan && plan.components.some(id => COMPONENTS.find(c => c.id === id).restart === 'app') && await appRunning(Number(opt('core-port')) || 8760)) {
      fs.mkdirSync(path.dirname(D.rollbackPending), { recursive: true }); fs.writeFileSync(D.rollbackPending, JSON.stringify({ at: new Date().toISOString(), to: plan.to }));
      return out({ ok: true, staged: true, message: `the previous version (${plan.to}) is put back the next time the Suite starts` });
    }
    return out(rollbackLatest(installDir));
  }
  // git source: the install folder is a clone
  if (!source || source.type === 'git') {
    const g = await gitStatus(installDir, channel).catch(() => ({ isClone: false }));
    if (g.isClone) {
      if (cmd2 === 'check') return out({ ok: true, source: 'git', current: g.current, newest: g.newest, available: !g.upToDate, dirty: g.dirty });
      if (g.upToDate) return out({ ok: true, source: 'git', message: 'already up to date' });
      if (g.dirty) return out({ ok: false, source: 'git', message: 'local edits in the install folder; not updating' });
      const { hostLiveCheck } = await import('./lib/apply.mjs'); const lv = await hostLiveCheck();
      if (lv.live !== false) return out({ ok: true, source: 'git', deferred: true, message: 'update is waiting until you are off stream' });
      return out({ ok: true, source: 'git', ...(await gitUpdate(installDir, g.newest)), to: g.newest });
    }
    if (!source) return out({ ok: true, message: 'no update source is set (install.json has none), nothing to do' });
  }
  if (cmd2 === 'check') {
    const c = await checkUpdate({ source, current, channel, pubkey, installDir }), lv = await hostLiveCheck();
    return out({ ok: true, current, available: c.available, version: c.manifest.version, notes: c.manifest.notes, released: c.manifest.released, why: c.why || null, components: c.components, optional: c.optional, profile: inst.profile || 'full', live: lv.live, pending: rd(D.pending) });
  }
  if (cmd2 === 'apply') {
    if (only) {
      const bad = only.filter(id => !COMPONENT_IDS.has(id));
      if (bad.length) return out({ ok: false, message: `unknown part: ${bad.join(', ')}` });
      // files of the running app are never swapped under it: those parts are only staged for the next launch
      const appPart = only.some(id => COMPONENTS.find(c => c.id === id).restart === 'app');
      if (appPart && !args.includes('--stage') && await appRunning(Number(opt('core-port')) || 8760)) return out({ ok: false, message: 'shell, core and Host files belong to the running app; they are staged and applied at the next start' });
    }
    return out(await applyUpdate({ installDir, source, current, channel, pubkey, only, stageOnly: args.includes('--stage'), repair: args.includes('--repair') }));
  }
  out({ ok: false, message: `unknown command ${cmd}` });
}
main().catch(e => { out({ ok: false, message: String(e.message || e).slice(0, 200) }); process.exitCode = 1; });
