// INDEX manifest.mjs: release manifest schema 1 (parse, validate, resolve urls) and numeric version compare.
export const UPDATER_VERSION = 1;

export function cmpVersion(a, b) {
  const pa = String(a).split('.').map(n => parseInt(n, 10) || 0), pb = String(b).split('.').map(n => parseInt(n, 10) || 0);
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) { const d = (pa[i] || 0) - (pb[i] || 0); if (d) return d < 0 ? -1 : 1; }
  return 0;
}

export function parseManifest(text, base = '') {
  let m; try { m = JSON.parse(text.replace(/^﻿/, '')); } catch { throw new Error('update manifest is not valid JSON'); }
  if (!m || m.schema !== 1) throw new Error('update manifest has an unknown schema');
  if (!/^\d+(\.\d+){0,3}$/.test(String(m.version))) throw new Error('update manifest has a bad version');
  if (!['stable', 'beta'].includes(m.channel || 'stable')) throw new Error('update manifest has an unknown channel');
  if ((m.min_updater || 1) > UPDATER_VERSION) throw new Error('this release needs a newer PinguinoUpdater; update the updater first');
  if (!Array.isArray(m.files) || !m.files.length || m.files.length > 20) throw new Error('update manifest lists no files');
  const files = m.files.map(f => {
    if (!f || !/^[A-Za-z0-9._-]{1,100}$/.test(f.name || '')) throw new Error('update manifest has a bad file name');
    if (!/^[0-9a-f]{64}$/i.test(f.sha256 || '')) throw new Error(`update manifest has no sha256 for ${f.name}`);
    if (!Number.isInteger(f.size) || f.size < 0) throw new Error(`update manifest has no size for ${f.name}`);
    return { name: f.name, size: f.size, sha256: f.sha256.toLowerCase(), url: f.url ? String(f.url) : f.name };
  });
  let components = null;   // optional per-part hashes so one part can be updated alone: {id: {hash, files, bytes}}
  if (m.components != null) {
    if (typeof m.components !== 'object' || Array.isArray(m.components)) throw new Error('update manifest has a bad components list');
    components = {};
    for (const [id, c] of Object.entries(m.components)) {
      if (!/^[a-z0-9_-]{1,30}$/.test(id) || !c || !/^[0-9a-f]{64}$/i.test(c.hash || '')) throw new Error('update manifest has a bad component');
      components[id] = { hash: c.hash.toLowerCase(), files: Number(c.files) || 0, bytes: Number(c.bytes) || 0 };
    }
  }
  return { schema: 1, channel: m.channel || 'stable', version: String(m.version), released: m.released || '', notes: String(m.notes || '').slice(0, 2000), files, components, base };
}
