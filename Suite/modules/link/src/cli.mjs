#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import * as cfgm from './config.mjs';
import * as ts from './tailscale.mjs';
import { serve, runMacro } from './server.mjs';
import { doctor } from './doctor.mjs';

const cfg = cfgm.load();
const [cmd, ...args] = process.argv.slice(2);

const HELP = `PinguinoLink
  setup [hub|client] [hub-name]   install/connect Tailscale and write config
  status                          show devices and connection quality
  serve                           run dashboard + macro API (Stream Deck: pinguinolink macro <name>)
  macro <name>                    run an OBS macro (forwarded to the hub if this is a client)
  send <file> <device>            send a file (Taildrop, encrypted, works on any network)
  receive                         pull incoming files into ${cfg.inbox}
  doctor [--no-ai]                run checks; on failure ask Claude and offer fixes`;

/** Tailscale must be running for send/receive; says what to do instead of a raw error. */
async function needTailscale() {
  const s = await ts.status();
  if (s.error) { console.log(s.error); return null; }
  if (s.state !== 'Running') { console.log(`Tailscale is ${s.state}. Open the Tailscale app, turn it on, then try again.`); return null; }
  return s;
}

switch (cmd) {
  case 'setup': {
    const [role = cfg.role, hub = cfg.hub] = args;
    if (!(await ts.installed())) {
      console.log('Installing Tailscale…'); const r = await ts.install();
      if (!r.ok) { console.log('Install failed:', r.stderr, '\nRun: pinguinolink doctor'); break; }
    }
    cfgm.save({ ...cfg, role, hub });
    console.log('Connecting (complete the sign-in in your browser if prompted)…');
    const r = await ts.up(role === 'hub' ? hub : undefined);
    console.log(r.ok ? 'Connected.' : r.stderr + r.stdout);
    console.log(`Role: ${role}. ${role === 'hub' ? `Enable OBS: Tools > WebSocket Server Settings, then put the password in ${cfgm.DIR}` : `Hub: ${hub}`}`);
    console.log(`Token for other devices is in ${path.join(cfgm.DIR, 'config.json')} (copy "token" to each device).`);
    break;
  }
  case 'status': {
    const s = await ts.status();
    if (s.error) { console.log(s.error); break; }
    console.log(`${s.self.name} (${s.self.ip}) — ${s.state}`);
    for (const p of s.peers) console.log(`  ${p.online ? (p.direct ? '🟢 direct ' : '🟡 relayed') : '⚫ offline '} ${p.name} ${p.ip}`);
    break;
  }
  case 'serve': await serve(cfg); break;
  case 'macro':
    if (!args[0]) { console.log(`macros: ${Object.keys(cfg.macros).join(', ')}
usage: pinguinolink macro <name>`); break; }
    try { await runMacro(cfg, args[0]); console.log('ok'); } catch (e) { console.error(e.message); process.exit(1); }
    break;
  case 'send': {
    const [file, dev] = args;
    if (!file || !dev || !fs.existsSync(file)) { console.log('usage: pinguinolink send <file> <device>'); break; }
    const st = await needTailscale(); if (!st) break;
    const peer = st.peers.find(p => p.name.toLowerCase() === dev.toLowerCase());
    if (!peer) { console.log(`No device "${dev}" on your tailnet. Devices: ${st.peers.map(p => p.name).join(', ') || 'none'}`); break; }
    if (!peer.online) { console.log(`${peer.name} is offline. Turn it on (with Tailscale running) and try again.`); break; }
    const r = await ts.sendFile(file, peer.name); console.log(r.ok ? `sent to ${peer.name}` : r.stderr);
    break;
  }
  case 'receive': {
    if (!(await needTailscale())) break;
    fs.mkdirSync(cfg.inbox, { recursive: true });
    const r = await ts.receiveFiles(cfg.inbox); console.log(r.ok ? `saved to ${cfg.inbox}` : r.stderr);
    break;
  }
  case 'doctor': await doctor(cfg, { ask: !args.includes('--no-ai') }); break;
  default: console.log(HELP);
}
