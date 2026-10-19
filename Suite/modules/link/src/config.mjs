import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const LEGACY = path.join(os.homedir(), '.pinguinolink');
// The Suite core sets PINGUINO_DATA_DIR; standalone runs keep using ~/.pinguinolink.
// PINGUINO_DATA_DIR is shared by every module, so Link keeps its own subfolder (the root already holds other modules' config.json).
// A command run by hand (Stream Deck, terminal) has no PINGUINO_DATA_DIR; inside the Suite tree it must still read the same
// config as the running module, so it falls back to <Suite>/Data/runtime/link when that folder exists.
const SUITE_LINK = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', '..', '..', 'Data', 'runtime', 'link');
export const DIR = process.env.PINGUINO_DATA_DIR ? path.join(path.resolve(process.env.PINGUINO_DATA_DIR), 'link')
  : fs.existsSync(path.join(SUITE_LINK, 'config.json')) ? SUITE_LINK : LEGACY;
const FILE = path.join(DIR, 'config.json');

export const DEFAULTS = {
  role: 'client',            // 'hub' = the streaming PC that runs OBS; 'client' = everything else
  hub: 'streaming-pc',       // Tailscale device name of the hub (clients forward macros to it)
  port: 7777,
  token: null,               // shared secret for the macro API; generated on first run
  inbox: path.join(os.homedir(), 'Downloads', 'PinguinoLink'),
  obs: { host: '127.0.0.1', port: 4455, password: '' },
  macros: {
    brb:  [{ type: 'SetCurrentProgramScene', data: { sceneName: 'BRB' } }],
    live: [{ type: 'SetCurrentProgramScene', data: { sceneName: 'Main' } }],
    start: [{ type: 'StartStream' }],
    stop:  [{ type: 'StopStream' }],
    mute:  [{ type: 'ToggleInputMute', data: { inputName: 'Mic/Aux' } }],
  },
  claude: { enabled: true, cli: 'claude' },   // doctor escalation; uses the local Claude Code CLI
};

export function load() {
  fs.mkdirSync(DIR, { recursive: true });
  // One-time migration of an existing standalone config into the Suite data dir.
  if (DIR !== LEGACY && !fs.existsSync(FILE) && fs.existsSync(path.join(LEGACY, 'config.json'))) {
    try { fs.copyFileSync(path.join(LEGACY, 'config.json'), FILE); } catch {}
  }
  let cfg = {};
  try { cfg = JSON.parse(fs.readFileSync(FILE, 'utf8')); } catch {}
  const merged = { ...DEFAULTS, ...cfg, obs: { ...DEFAULTS.obs, ...cfg.obs }, claude: { ...DEFAULTS.claude, ...cfg.claude } };
  if (!merged.token) { merged.token = crypto.randomBytes(24).toString('hex'); save(merged); }
  return merged;
}

export function save(cfg) {
  fs.mkdirSync(DIR, { recursive: true });
  fs.writeFileSync(FILE, JSON.stringify(cfg, null, 2), { mode: 0o600 });
}
