// User-editable settings: one schema drives validation, defaults, one-line help and the Settings card on the page.
// Values live in config.json (device name lives in mesh.json). Secrets (OBS password) are NOT here: they live in the key vault.
import os from 'node:os';
import path from 'node:path';
import * as cfgm from './config.mjs';
import { isTailnetIp, fail } from './mesh.mjs';
import { log, setLevel } from './log.mjs';

const D = cfgm.DEFAULTS;
export const SCHEMA = [
  { group: 'This device', fields: [
    { key: 'device.name', label: 'Device name', type: 'text', def: os.hostname(), help: 'The name other devices see for this PC.', special: true },
    { key: 'role', label: 'Role', type: 'select', options: ['client', 'hub'], def: D.role, danger: true, help: 'hub = this PC runs OBS and executes macros; client = forwards macros to the hub. Changing it asks you to confirm.' },
    { key: 'hub', label: 'Hub device', type: 'text', def: D.hub, list: 'peers', help: 'Tailscale name of the PC that runs OBS (used by clients).' },
    { key: 'inbox', label: 'Received files folder', type: 'path', def: D.inbox, help: 'Where "receive" saves incoming files (full path).' },
  ] },
  { group: 'OBS', fields: [
    { key: 'obs.host', label: 'OBS address', type: 'host', def: D.obs.host, help: 'Where OBS runs. Only this PC (127.0.0.1) or a Tailscale address is allowed.' },
    { key: 'obs.port', label: 'OBS WebSocket port', type: 'number', min: 1, max: 65535, def: D.obs.port, help: 'Matches OBS > Tools > WebSocket Server Settings (default 4455). The password is in the key vault.' },
  ] },
  { group: 'This page', fields: [
    { key: 'ui.refreshSec', label: 'Refresh every (seconds)', type: 'number', min: 2, max: 60, def: 4, help: 'How often this page updates itself.' },
    { key: 'ui.showReadiness', label: 'Show the readiness list', type: 'bool', def: true, help: 'A checklist at the top of the page: OBS, macros, Tailscale and devices, each with a plain-language status.' },
    { key: 'ui.confirmMacros', label: 'Extra macros needing a second click', type: 'list', def: [], help: 'Comma-separated macro names. Anything that starts or stops the stream always needs it.' },
    { key: 'ui.compact', label: 'Compact layout', type: 'bool', def: false, help: 'Tighter spacing so more fits on screen.' },
    { key: 'ui.accent', label: 'Accent colour', type: 'color', def: '', help: 'Hex like #ff9900 for headings and highlights. Blank = the Suite theme.' },
  ] },
  { group: 'Buttons and safety', fields: [
    { key: 'cooldown.macroMs', label: 'Repeat-press guard (ms)', type: 'number', min: 0, max: 10000, def: 600, help: 'A macro pressed again within this time is ignored (stops double taps and Stream Deck bounce). 0 = off.' },
    { key: 'cooldown.riskyMs', label: 'Repeat-press guard for start/stop (ms)', type: 'number', min: 0, max: 30000, def: 3000, help: 'Same, for macros that start or stop the stream or stop recording.' },
    { key: 'ui.sceneButtons', label: 'Show a button for every OBS scene', type: 'bool', def: false, help: 'Adds quick scene buttons under OBS (this PC must be the hub and OBS connected).' },
    { key: 'ui.activityCount', label: 'Recent activity lines', type: 'number', min: 0, max: 50, def: 15, help: 'How many recent macro/scene actions to list on this page. 0 hides the list.' },
  ] },
  { group: 'Pre-stream report', fields: [
    { key: 'prestream.obs', label: 'Check OBS', type: 'bool', def: true, help: 'Include "OBS reachable" in the pre-stream report.' },
    { key: 'prestream.macros', label: 'Check macro targets', type: 'bool', def: true, help: 'Verify every scene and input your macros name exists in OBS.' },
    { key: 'prestream.tailscale', label: 'Check Tailscale', type: 'bool', def: true, help: 'Include the Tailscale status.' },
    { key: 'prestream.tailscaleRequired', label: 'Tailscale is required', type: 'bool', def: false, help: 'Report Tailscale being off as a failure instead of a warning.' },
    { key: 'prestream.devices', label: 'Check paired devices', type: 'bool', def: true, help: 'Include one line per paired device.' },
  ] },
  { group: 'Devices', fields: [
    { key: 'mesh.offlineSec', label: 'Offline after (seconds)', type: 'number', min: 5, max: 120, def: 12, help: 'Silence longer than this shows a paired device as offline.' },
    { key: 'mesh.allowRemoteMacros', label: 'Let paired devices run my OBS macros', type: 'bool', def: true, help: 'A paired client can press the macros on this PC (scene, mute...). Turn off to make this PC ignore remote presses.' },
    { key: 'mesh.remoteRisky', label: 'Let paired devices start/stop my stream', type: 'bool', def: false, help: 'Allows remote start/stop-stream macros. Off by default: only press those on this PC.' },
    { key: 'mesh.codeMinutes', label: 'Pairing code lifetime (minutes)', type: 'number', min: 1, max: 15, def: 5, help: 'How long a pairing code stays valid. It always works only once.' },
  ] },
  { group: 'Logging', fields: [
    { key: 'log.level', label: 'Console log level', type: 'select', options: ['debug', 'info', 'warn', 'error'], def: 'info', help: 'Lowest level written to the Suite console (warn = only problems).' },
  ] },
];
const FIELDS = Object.fromEntries(SCHEMA.flatMap(g => g.fields).map(f => [f.key, f]));
const RESTART = new Set(['port']);

const getPath = (o, k) => k.split('.').reduce((a, p) => a?.[p], o);
function setPath(o, k, v) { const ps = k.split('.'); let a = o; for (const p of ps.slice(0, -1)) a = (a[p] ??= {}); a[ps.at(-1)] = v; }
function delPath(o, k) { const ps = k.split('.'); let a = o; for (const p of ps.slice(0, -1)) { a = a?.[p]; if (!a) return; } delete a[ps.at(-1)]; }

export function value(cfg, ctx, key) {
  const f = FIELDS[key];
  if (f.special) return ctx.getName();
  const v = getPath(cfg, key);
  return v === undefined ? f.def : v;
}

export function view(cfg, ctx) {
  return SCHEMA.map(g => ({ group: g.group, fields: g.fields.map(f => ({ key: f.key, label: f.label, type: f.type, options: f.options, min: f.min, max: f.max, list: f.list, danger: !!f.danger,
    help: f.help, def: f.def, value: value(cfg, ctx, f.key), changed: JSON.stringify(value(cfg, ctx, f.key)) !== JSON.stringify(f.def) })) }));
}

const str = (v, n = 200) => String(v ?? '').replace(/[^\x20-\x7e\u00a0-\uffff]/g, '').trim().slice(0, n);
function clean(f, v) {
  switch (f.type) {
    case 'text': { const s = str(v, 80); if (!s) throw fail(400, `${f.label} cannot be empty`); return s; }
    case 'path': { const s = str(v, 260); if (!path.isAbsolute(s)) throw fail(400, `${f.label} must be a full path like C:\\Users\\you\\Downloads`); return s; }
    case 'number': { const n = Number(v); if (!Number.isInteger(n) || n < f.min || n > f.max) throw fail(400, `${f.label} must be a whole number from ${f.min} to ${f.max}`); return n; }
    case 'bool': if (typeof v !== 'boolean') throw fail(400, `${f.label} must be on or off`); return v;
    case 'select': if (!f.options.includes(v)) throw fail(400, `${f.label} must be one of ${f.options.join(', ')}`); return v;
    case 'color': { const s = str(v, 7); if (s && !/^#[0-9a-fA-F]{6}$/.test(s)) throw fail(400, `${f.label} must look like #ff9900 or be empty`); return s; }
    case 'host': { const s = str(v, 64); if (s === 'localhost' || s === '127.0.0.1' || isTailnetIp(s)) return s; throw fail(400, 'OBS address must be this PC (127.0.0.1) or a Tailscale address (100.x). OBS is never reached over other networks.'); }
    case 'list': {
      const a = (Array.isArray(v) ? v : String(v ?? '').split(',')).map(x => str(x, 24)).filter(Boolean);
      if (a.some(x => !/^[\w-]+$/.test(x)) || a.length > 30) throw fail(400, `${f.label}: use macro names separated by commas`);
      return a;
    }
  }
  throw fail(400, 'unsupported setting');
}

/** Apply {key: value|null}. null = reset to default. Validates everything first; nothing is applied if any value is bad. */
export function apply(cfg, ctx, changes, { confirmRole = false } = {}) {
  const todo = [];
  for (const [key, raw] of Object.entries(changes || {})) {
    const f = FIELDS[key];
    if (!f) throw fail(400, `unknown setting ${key}`);
    todo.push([f, raw === null ? f.def : clean(f, raw)]);
  }
  const roleChange = todo.find(([f, v]) => f.key === 'role' && v !== cfg.role);
  if (roleChange && !confirmRole) throw fail(409, `Switching to ${roleChange[1]} needs confirmation`, { needs: 'confirm_role', to: roleChange[1] });
  const changed = [];
  for (const [f, v] of todo) {
    if (JSON.stringify(value(cfg, ctx, f.key)) === JSON.stringify(v)) continue;
    if (f.special) ctx.setName(v);
    else if (f.def !== undefined && ['role', 'hub', 'port', 'inbox', 'obs.host', 'obs.port'].includes(f.key)) setPath(cfg, f.key, v);
    else if (JSON.stringify(v) === JSON.stringify(f.def)) delPath(cfg, f.key);
    else setPath(cfg, f.key, v);
    changed.push(f.key);
    log(f.danger ? 'warn' : 'info', 'settings', `${f.key} changed${f.danger ? ` to ${v}` : ''}`);
    if (f.key === 'log.level') setLevel(v);
  }
  if (changed.length) cfgm.save(cfg);
  return { ok: true, changed, restart: changed.some(k => RESTART.has(k)) };
}
