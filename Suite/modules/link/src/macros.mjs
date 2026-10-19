// Macro editor model. Macros are lists of OBS requests; the editor only offers an allow-list of safe, named actions
// (least privilege: no arbitrary OBS request, no shell). Hand-written steps in config.json stay valid and show as "custom".
import { fail } from './mesh.mjs';
import { log } from './log.mjs';
import * as cfgm from './config.mjs';

export const KINDS = {
  scene:          { label: 'Switch scene',            param: 'scene', build: p => ({ type: 'SetCurrentProgramScene', data: { sceneName: p } }) },
  'stream-start': { label: 'Start stream',            risky: true,  build: () => ({ type: 'StartStream' }) },
  'stream-stop':  { label: 'Stop stream',             risky: true,  build: () => ({ type: 'StopStream' }) },
  'record-start': { label: 'Start recording',         build: () => ({ type: 'StartRecord' }) },
  'record-stop':  { label: 'Stop recording',          risky: true,  build: () => ({ type: 'StopRecord' }) },
  'record-toggle':{ label: 'Toggle recording',        build: () => ({ type: 'ToggleRecord' }) },
  'replay-save':  { label: 'Save replay buffer',      build: () => ({ type: 'SaveReplayBuffer' }) },
  'mute-toggle':  { label: 'Toggle mute on input',    param: 'input', build: p => ({ type: 'ToggleInputMute', data: { inputName: p } }) },
  mute:           { label: 'Mute input',              param: 'input', build: p => ({ type: 'SetInputMute', data: { inputName: p, inputMuted: true } }) },
  unmute:         { label: 'Unmute input',            param: 'input', build: p => ({ type: 'SetInputMute', data: { inputName: p, inputMuted: false } }) },
};
const RISKY_TYPES = new Set(['StartStream', 'StopStream', 'StopRecord']);

/** OBS request -> editor step (or a read-only custom step). */
function toStep(r) {
  for (const [kind, k] of Object.entries(KINDS)) {
    const b = k.build(k.param ? '\u0000' : undefined);
    if (b.type !== r.type) continue;
    if (b.type === 'SetInputMute' && b.data.inputMuted !== r.data?.inputMuted) continue;
    return k.param ? { kind, value: r.data?.sceneName ?? r.data?.inputName ?? '' } : { kind };
  }
  return { kind: 'custom', raw: r.type };
}
const targets = r => [r.data?.sceneName, r.data?.inputName].filter(Boolean);

export const isRisky = (cfg, name) => (cfg.macros[name] || []).some(r => RISKY_TYPES.has(r.type)) || (cfg.ui?.confirmMacros || []).includes(name);

export function list(cfg) {
  const meta = cfg.macroMeta || {};
  return Object.entries(cfg.macros).map(([name, steps]) => ({ name, steps: steps.map(toStep), risky: isRisky(cfg, name), meta: meta[name] || {} }));
}
/** Buttons for the dashboard: label/icon/hidden personalisation applied. */
export function buttons(cfg) {
  return list(cfg).map(m => ({ name: m.name, label: m.meta.label || m.name, icon: m.meta.icon || '', risky: m.risky, hidden: !!m.meta.hidden }));
}

const s = (v, n) => String(v ?? '').replace(/[\u0000-\u001f]/g, '').trim().slice(0, n);

export function set(cfg, body) {
  const name = s(body.name, 24);
  if (!/^[\w-]{1,24}$/.test(name)) throw fail(400, 'Macro name: letters, digits, - and _ only (max 24)');
  if (!Array.isArray(body.steps) || !body.steps.length || body.steps.length > 8) throw fail(400, 'A macro needs 1 to 8 steps');
  if (!cfg.macros[name] && Object.keys(cfg.macros).length >= 30) throw fail(400, 'At most 30 macros');
  const prev = cfg.macros[name] || [];
  const steps = body.steps.map((st, i) => {
    if (st.kind === 'custom') {                                // keep a hand-written step exactly as it was
      const old = prev[i];
      if (!old) throw fail(400, 'cannot add a custom step here; edit config.json');
      return old;
    }
    const k = KINDS[st.kind];
    if (!k) throw fail(400, `unknown action "${st.kind}"`);
    const v = s(st.value, 80);
    if (k.param && !v) throw fail(400, `${k.label}: pick a ${k.param}`);
    return k.build(k.param ? v : undefined);
  });
  cfg.macros[name] = steps;
  cfg.macroMeta ||= {};
  const meta = { label: s(body.label, 24), icon: s(body.icon, 4), hidden: !!body.hidden };
  if (meta.label || meta.icon || meta.hidden) cfg.macroMeta[name] = Object.fromEntries(Object.entries(meta).filter(([, v]) => v)); else delete cfg.macroMeta[name];
  cfgm.save(cfg);
  log('info', 'macros', `macro "${name}" saved (${steps.length} step${steps.length > 1 ? 's' : ''})`);
  return { ok: true };
}
export function remove(cfg, name) {
  if (!cfg.macros[name]) throw fail(404, 'no such macro');
  delete cfg.macros[name]; if (cfg.macroMeta) delete cfg.macroMeta[name];
  cfgm.save(cfg);
  log('info', 'macros', `macro "${name}" deleted`);
  return { ok: true };
}
export function move(cfg, name, dir) {
  const keys = Object.keys(cfg.macros), i = keys.indexOf(name), j = i + (dir < 0 ? -1 : 1);
  if (i < 0) throw fail(404, 'no such macro');
  if (j < 0 || j >= keys.length) return { ok: true };
  [keys[i], keys[j]] = [keys[j], keys[i]];
  cfg.macros = Object.fromEntries(keys.map(k => [k, cfg.macros[k]]));
  cfgm.save(cfg);
  return { ok: true };
}
/** Which scenes/inputs a macro uses that OBS does not have. */
export function missing(cfg, name, obs) {
  if (!cfg.macros[name]) throw fail(404, 'no such macro');
  const have = new Set([...(obs.scenes || []), ...(obs.inputs || [])]);
  return cfg.macros[name].flatMap(targets).filter(t => !have.has(t));
}

/** Portable copy of the macros the editor understands (hand-written steps are skipped and counted). */
export function exportAll(cfg) {
  let skipped = 0;
  const out = list(cfg).map(m => { const steps = m.steps.filter(s => s.kind !== 'custom'); skipped += m.steps.length - steps.length; return { name: m.name, steps, label: m.meta.label || '', icon: m.meta.icon || '', hidden: !!m.meta.hidden }; }).filter(m => m.steps.length);
  return { macros: out, skipped };
}
export function importAll(cfg, items) {
  if (!Array.isArray(items) || items.length > 30) throw fail(400, 'macros must be a list of at most 30');
  const before = JSON.stringify([cfg.macros, cfg.macroMeta]);
  try { for (const m of items) set(cfg, m); }
  catch (e) { cfg.macros = JSON.parse(before)[0]; cfg.macroMeta = JSON.parse(before)[1] || {}; cfgm.save(cfg); throw e; }
  return items.length;
}
