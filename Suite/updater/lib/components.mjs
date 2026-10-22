// INDEX components.mjs: which part of the Suite a release file belongs to (shell, core, Host, each module, scripts/docs), so one part can be updated alone.
// restart: 'none' = swap and done, 'module' = the core restarts just that module around the swap, 'app' = files of the running app: staged now, swapped at the next launch.
import crypto from 'node:crypto';

export const COMPONENTS = [
  { id: 'shell', name: 'App shell', restart: 'app', match: ['App/src-tauri/target/release/pinguino-suite.exe'] },
  { id: 'core', name: 'Core', restart: 'app', match: ['App/src-tauri/target/release/binaries/', 'Suite/suite/', 'Suite/modules.json', 'Suite/requirements.txt'] },
  { id: 'host', name: 'Host', restart: 'app', match: ['PinguinoHost/'] },
  { id: 'listen', name: 'Listen', restart: 'module', module: 'listen', match: ['Suite/modules/listen/'] },
  { id: 'multi', name: 'Multi', restart: 'module', module: 'multi', match: ['Suite/modules/multi/'] },
  { id: 'link', name: 'Link', restart: 'module', module: 'link', match: ['Suite/modules/link/'] },
  { id: 'spotify', name: 'Spotify', restart: 'module', module: 'spotify', match: ['Suite/modules/spotify/'] },
  { id: 'voice', name: 'Voice', restart: 'module', module: 'voice', match: ['Suite/modules/voice/'] },
  { id: 'tools', name: 'Scripts and docs', restart: 'none', match: [] },   // everything else (updater, installer scripts, docs)
];
export const COMPONENT_IDS = new Set(COMPONENTS.map(c => c.id));

/** Component id for a clean forward-slash relative path. Unknown paths fall into 'tools'. */
export function componentOf(rel) {
  const r = String(rel).toLowerCase();
  for (const c of COMPONENTS) for (const m of c.match) if (r === m.toLowerCase() || (m.endsWith('/') && r.startsWith(m.toLowerCase()))) return c.id;
  return 'tools';
}

/** {id: {hash, files, bytes}} for entries [{rel, data}]. The hash covers names and contents, so it changes exactly when the component's files change. */
export function hashComponents(entries) {
  const per = {};
  for (const e of entries) {
    const id = componentOf(e.rel), p = per[id] || (per[id] = { lines: [], files: 0, bytes: 0 });
    p.lines.push(`${e.rel}\0${crypto.createHash('sha256').update(e.data).digest('hex')}`); p.files++; p.bytes += e.data.length;
  }
  const out = {};
  for (const [id, p] of Object.entries(per)) out[id] = { hash: crypto.createHash('sha256').update(p.lines.sort().join('\n')).digest('hex'), files: p.files, bytes: p.bytes };
  return out;
}
