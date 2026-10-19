import { obsConn } from './vault.mjs';
import os from 'node:os';
import readline from 'node:readline/promises';
import { spawn } from 'node:child_process';
import * as ts from './tailscale.mjs';
import { runRequests } from './obs.mjs';

// Fixes Claude may *suggest*. It can only pick from this list; nothing else is ever executed.
const FIXES = {
  'tailscale-up':      { desc: 'Bring Tailscale up (may open a sign-in page)', run: cfg => ts.up() },
  'tailscale-restart': { desc: 'Restart the Tailscale service', run: () => os.platform() === 'win32'
      ? ts.run('powershell', ['-NoProfile', '-Command', 'Restart-Service Tailscale'])
      : ts.run('sh', ['-c', 'sudo tailscale down && sudo tailscale up']) },
  'tailscale-install': { desc: 'Install Tailscale', run: () => ts.install() },
};

export async function check(cfg) {
  const out = [];
  const add = (name, ok, detail = '') => out.push({ name, ok, detail });

  if (!(await ts.installed())) { add('tailscale installed', false, 'tailscale CLI not found'); return out; }
  add('tailscale installed', true);

  const st = await ts.status();
  if (st.error) { add('tailscale reachable', false, st.error); return out; }
  add('tailscale running', st.state === 'Running', `state=${st.state}`);
  for (const h of st.health) add('tailscale health', false, h);
  if (st.state !== 'Running') return out;

  if (cfg.role === 'client') {
    const hub = st.peers.find(p => p.name === cfg.hub);
    add(`hub "${cfg.hub}" on tailnet`, !!hub, hub ? '' : `peers: ${st.peers.map(p => p.name).join(', ') || 'none'}`);
    if (hub) {
      add('hub online', hub.online);
      if (hub.online) {
        const p = await ts.ping(cfg.hub);
        add('hub ping', p.ok, (p.stdout + p.stderr).trim().split('\n').pop());
        add('path to hub is direct (not relayed)', hub.direct, hub.direct ? '' : `relayed via ${hub.relay}; fine for macros, may hurt streaming`);
        try { const r = await fetch(`http://${hub.ip}:${cfg.port}/api/status`, { headers: { 'x-link-token': cfg.token }, signal: AbortSignal.timeout(4000) }); add('hub PinguinoLink service', r.ok, `HTTP ${r.status}`); }
        catch (e) { add('hub PinguinoLink service', false, e.message); }
      }
    }
  } else {
    try { await runRequests(await obsConn(cfg), [{ type: 'GetVersion' }]); add('OBS WebSocket', true); }
    catch (e) { add('OBS WebSocket', false, e.message); }
  }
  return out;
}

const HINTS = {
  'tailscale installed': 'Install Tailscale from https://tailscale.com/download and sign in.',
  'tailscale running': 'Open the Tailscale app and turn it on (tray icon).',
  'hub ': 'Start the streaming PC, make sure Tailscale and PinguinoLink are running there, and check the hub name in the Link config.',
  'OBS WebSocket': 'Start OBS, enable Tools > WebSocket Server Settings (port 4455), and put its password in the key vault as OBS_WS_PASSWORD.',
};

function redact(s, cfg) {
  return s.replaceAll(cfg.token, '<token>').replaceAll(cfg.obs.password || '\0', '<obs-password>')
          .replace(/https:\/\/login\.tailscale\.com\/\S+/g, '<login-url>');
}

function askClaude(cfg, prompt) {
  return new Promise((resolve, reject) => {
    const p = spawn(cfg.claude.cli, ['-p'], { shell: os.platform() === 'win32', windowsHide: true });
    let out = '', err = '';
    p.stdout.on('data', d => out += d); p.stderr.on('data', d => err += d);
    p.on('error', reject);
    p.on('close', c => c === 0 ? resolve(out) : reject(new Error(err || `claude exited ${c}`)));
    p.stdin.end(prompt);
  });
}

export async function doctor(cfg, { ask = true } = {}) {
  const results = await check(cfg);
  for (const r of results) {
    console.log(`${r.ok ? '✓' : '✗'} ${r.name}${r.detail ? ' — ' + r.detail : ''}`);
    const hint = !r.ok && Object.entries(HINTS).find(([k]) => r.name.startsWith(k))?.[1];
    if (hint) console.log(`    → ${hint}`);
  }
  const bad = results.filter(r => !r.ok);
  if (!bad.length) return console.log('\nAll good.');
  if (!ask || !cfg.claude.enabled) return;

  const net = await ts.netcheck();
  const bundle = redact(JSON.stringify({ os: os.platform(), role: cfg.role, failing: bad, all: results, netcheck: net.stdout.slice(0, 2000) }, null, 2), cfg);
  const prompt = `You are the troubleshooting brain of PinguinoLink, a Tailscale-based app linking a user's PCs (a Mac that streams to a Windows streaming PC running OBS; a Stream Deck sends OBS macros through it). Below is a redacted diagnostics bundle. Explain the most likely cause in 2-4 sentences, then on the LAST line output ONLY a JSON array of fix ids to try, chosen from: ${Object.keys(FIXES).join(', ')} (use [] if none apply or a manual step is needed).\n\n${bundle}`;
  console.log('\nAsking Claude (redacted diagnostics only)…\n');
  let reply;
  try { reply = await askClaude(cfg, prompt); } catch (e) { return console.log(`Claude unavailable: ${e.message}`); }
  console.log(reply.trim());

  const m = reply.trim().split('\n').pop().match(/\[.*\]/);
  const ids = (() => { try { return JSON.parse(m?.[0] || '[]').filter(i => FIXES[i]); } catch { return []; } })();
  if (!ids.length) return;
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  for (const id of ids) {
    if ((await rl.question(`\nApply fix "${id}": ${FIXES[id].desc}? [y/N] `)).trim().toLowerCase() === 'y') {
      const r = await FIXES[id].run(cfg); console.log(r.ok ? 'done' : `failed: ${r.stderr}`);
    }
  }
  rl.close();
}
