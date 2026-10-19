// Key vault client (MODULE_CONTRACT "Key vault"): secrets are read from the core on demand and held in memory only.
// Standalone runs (no core token) and any vault failure fall back to the plaintext config value.
import { log } from './log.mjs';

const CORE = () => process.env.PINGUINO_CORE_URL || 'http://127.0.0.1:8760';
const warned = new Set();

export async function secret(name) {
  const t = process.env.PINGUINO_API_TOKEN;
  if (!t) return null;
  try {
    const r = await fetch(`${CORE()}/api/vault/${encodeURIComponent(name)}`, { headers: { authorization: `Bearer ${t}` }, signal: AbortSignal.timeout(1500) });
    if (r.ok) return (await r.json()).value || null;
    const k = `${name}:${r.status}`;
    if (r.status !== 404 && !warned.has(k)) { warned.add(k); log('warn', 'vault', `cannot read ${name} (${r.status}); using the config file value`); }
  } catch (e) {
    const k = `${name}:net`;
    if (!warned.has(k)) { warned.add(k); log('warn', 'vault', `vault unreachable (${e.cause?.code || e.message}); using the config file value`); }
  }
  return null;
}

/** OBS connection settings with the password from the vault when it is set there, else from the config file. */
export async function obsConn(cfg) {
  const v = await secret('OBS_WS_PASSWORD');
  return v ? { ...cfg.obs, password: v } : cfg.obs;
}
