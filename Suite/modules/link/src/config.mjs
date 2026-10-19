import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';

export const DIR = path.join(os.homedir(), '.pinguinolink');
const FILE = path.join(DIR, 'config.json');

const DEFAULTS = {
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
