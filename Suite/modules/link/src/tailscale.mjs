import { execFile } from 'node:child_process';
import os from 'node:os';

export function run(cmd, args = [], { timeout = 30000 } = {}) {
  return new Promise(resolve => {
    execFile(cmd, args, { timeout, windowsHide: true }, (err, stdout, stderr) => {
      resolve({ ok: !err, code: err?.code ?? 0, stdout: String(stdout || ''), stderr: String(stderr || err?.message || '') });
    });
  });
}

const ts = (...a) => run('tailscale', a);

export async function installed() {
  return (await ts('version')).ok;
}

/** Install Tailscale with the platform package manager. */
export async function install() {
  if (os.platform() === 'win32') return run('winget', ['install', '--id', 'Tailscale.Tailscale', '-e', '--accept-source-agreements', '--accept-package-agreements'], { timeout: 600000 });
  if (os.platform() === 'darwin') return run('brew', ['install', '--cask', 'tailscale'], { timeout: 600000 });
  return run('sh', ['-c', 'curl -fsSL https://tailscale.com/install.sh | sh'], { timeout: 600000 });
}

/** Bring the node up. Prints a login URL on first run; Tailscale waits for the browser sign-in. */
export async function up(hostname) {
  const args = ['up', '--accept-routes=false', '--shields-up=false'];
  if (hostname) args.push(`--hostname=${hostname}`);
  return run('tailscale', args, { timeout: 180000 });
}

export async function status() {
  const r = await ts('status', '--json');
  if (!r.ok && !r.stdout) return { error: r.stderr.trim() || 'tailscale not reachable' };
  try {
    const j = JSON.parse(r.stdout);
    const peers = Object.values(j.Peer || {}).map(p => ({
      name: (p.DNSName || p.HostName || '').split('.')[0],
      ip: p.TailscaleIPs?.[0],
      os: p.OS,
      online: p.Online,
      direct: !!p.CurAddr,              // true = peer-to-peer, false = relayed (DERP)
      relay: p.Relay || null,
    }));
    return {
      state: j.BackendState,            // Running | NeedsLogin | Stopped ...
      self: { name: (j.Self?.DNSName || '').split('.')[0], ip: j.Self?.TailscaleIPs?.[0] },
      peers,
      health: j.Health || [],
      authUrl: j.AuthURL || null,
    };
  } catch { return { error: 'could not parse tailscale status' }; }
}

export const ping = name => ts('ping', '-c', '3', '--timeout=3s', name);
export const sendFile = (file, device) => ts('file', 'cp', file, `${device}:`);
export const receiveFiles = dir => run('tailscale', ['file', 'get', dir]);
export const netcheck = () => ts('netcheck');
