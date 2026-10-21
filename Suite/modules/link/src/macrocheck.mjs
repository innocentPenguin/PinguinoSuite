// OBS control self-check against a FAKE obs-websocket v5 server (never touches the real OBS or stream).
// Run: node src/macrocheck.mjs
process.env.PINGUINO_NEVER_REAL_OBS = '1';   // tests must never reach the real OBS
import { spawn } from 'node:child_process';
import http from 'node:http';
import os from 'node:os';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { startFakeObs } from './fakeobs.mjs';
import { diagnoseObs } from './obs.mjs';

const cli = fileURLToPath(new URL('./cli.mjs', import.meta.url));
const results = [];
const check = (name, ok, extra = '') => { results.push(ok); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${ok ? '' : '  ' + extra}`); };
const sleep = ms => new Promise(r => setTimeout(r, ms));

const { obs, obsPort, close: closeObs } = await startFakeObs('pw-secret-1');

// ---- Link instance (hub role) pointed at the fake OBS ----
async function link(password, allowStart = true) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'plink-mc-'));
  fs.mkdirSync(path.join(dir, 'link'), { recursive: true });
  const cfg = { role: 'hub', hub: 'x', port: 7777, token: 'module-token-module-token-0001', inbox: dir, obs: { host: '127.0.0.1', port: obsPort, password },
    macros: { brb: [{ type: 'SetCurrentProgramScene', data: { sceneName: 'BRB' } }], live: [{ type: 'SetCurrentProgramScene', data: { sceneName: 'Main' } }],
      start: [{ type: 'StartStream' }], stop: [{ type: 'StopStream' }], mute: [{ type: 'ToggleInputMute', data: { inputName: 'Mic/Aux' } }] }, claude: { enabled: false, cli: 'claude' }, cooldown: { macroMs: 0, riskyMs: 0 }, ui: { sceneButtons: true }, ...(allowStart ? { safety: { allowStartStream: true } } : {}) };
  fs.writeFileSync(path.join(dir, 'link', 'config.json'), JSON.stringify(cfg));
  const port = 7950 + Math.floor(Math.random() * 40);
  const child = spawn(process.execPath, [cli, 'serve'], { stdio: 'ignore', windowsHide: true,
    env: { ...process.env, PINGUINO_LINK_PORT: String(port), PINGUINO_API_TOKEN: 'core-mc', PINGUINO_DATA_DIR: dir, PINGUINO_CORE_URL: 'http://127.0.0.1:1' } });
  const base = `http://127.0.0.1:${port}`;
  const call = async (method, p, body) => {
    const r = await fetch(base + p, { method, headers: { 'x-link-token': cfg.token, ...(body ? { 'content-type': 'application/json' } : {}) }, body: body ? JSON.stringify(body) : undefined });
    return { status: r.status, json: await r.json().catch(() => ({})) };
  };
  for (let i = 0; i < 30; i++) { try { if ((await fetch(base + '/api/health')).ok) break; } catch {} await sleep(300); }
  return { dir, child, call, port };
}

const good = await link('pw-secret-1'), bad = await link('bad-secret-2'), off = await link('pw-secret-1', false);
try {
  const st = await good.call('GET', '/api/obs');
  check('OBS state: connected, scene Main, not live', st.json.connected && st.json.scene === 'Main' && st.json.streaming === false, JSON.stringify(st.json));
  const ps = (await good.call('GET', '/api/prestream')).json.items;
  check('prestream: OBS pass', ps.find(i => i.id === 'obs')?.status === 'pass');
  check('prestream: macro targets pass', ps.find(i => i.id === 'macros')?.status === 'pass', JSON.stringify(ps.find(i => i.id === 'macros')));

  check('DEFAULT: start macro is refused (403) and nothing goes live', (await off.call('POST', '/api/macro/start')).status === 403 && obs.streaming === false);
  check('DEFAULT: scene macros still work', (await off.call('POST', '/api/macro/brb')).status === 200 && obs.scene === 'BRB');
  await off.call('POST', '/api/macro/live');
  check('macro brb switches scene', (await good.call('POST', '/api/macro/brb')).status === 200 && obs.scene === 'BRB');
  check('macro live switches back', (await good.call('POST', '/api/macro/live')).status === 200 && obs.scene === 'Main');
  check('macro mute toggles input', (await good.call('POST', '/api/macro/mute')).status === 200 && obs.muted === true);
  await good.call('POST', '/api/macro/mute');
  check('macro stop while not streaming is refused (409)', (await good.call('POST', '/api/macro/stop')).status === 409 && obs.streaming === false);
  check('macro start goes live', (await good.call('POST', '/api/macro/start')).status === 200 && obs.streaming === true);
  await sleep(2200);                                  // state cache is 2 s
  const live = await good.call('GET', '/api/obs');
  check('OBS state shows LIVE', live.json.streaming === true);
  check('second start is refused while live (409)', (await good.call('POST', '/api/macro/start')).status === 409);
  check('macro stop ends the stream', (await good.call('POST', '/api/macro/stop')).status === 200 && obs.streaming === false);
  check('unknown macro = 500 with a clear message', (await good.call('POST', '/api/macro/nope')).json.error?.includes('unknown macro'));

  // Stream Deck path: the CLI talks to the running module (guards + activity), reading the same config dir
  const runCli = (...a) => new Promise(res => { const p = spawn(process.execPath, [cli, ...a], { env: { ...process.env, PINGUINO_DATA_DIR: good.dir, PINGUINO_LINK_PORT: String(good.port) }, windowsHide: true }); let out = ''; p.stdout.on('data', d => out += d); p.stderr.on('data', d => out += d); p.on('close', c => res({ code: c, out: out.trim() })); });
  const cl = await runCli('macro', 'brb');
  check('CLI macro goes through the running module', cl.code === 0 && cl.out === 'ok' && obs.scene === 'BRB', JSON.stringify(cl));
  check('CLI press shows in the activity list', (await good.call('GET', '/api/activity')).json.items.some(a => a.name === 'brb'));
  await good.call('POST', '/api/macro/live');
  const cl2 = await runCli('macro', 'stop');
  check('CLI shows the guard message and exits 1', cl2.code === 1 && /not streaming/.test(cl2.out), JSON.stringify(cl2));
  const mcli = (await good.call('GET', '/api/macros')).json.cli;
  check('macro list exposes the Stream Deck command parts', !!mcli?.node && /cli.mjs$/.test(mcli.script));
  const o2 = (await good.call('GET', '/api/obs')).json;
  check('scene buttons: /api/obs lists scenes when enabled', Array.isArray(o2.scenes) && o2.scenes.includes('BRB'));
  check('scene button switches OBS scene', (await good.call('POST', '/api/scene', { name: 'BRB' })).status === 200 && obs.scene === 'BRB');
  await good.call('POST', '/api/scene', { name: 'Main' });
  check('unknown scene refused (404)', (await good.call('POST', '/api/scene', { name: 'Nope' })).status === 404 && obs.scene === 'Main');
  const act = (await good.call('GET', '/api/activity')).json.items;
  check('activity lists recent actions', act.length > 3 && act.some(a => a.name === 'start' && a.ok) && act.some(a => a.kind === 'scene'));
  await good.call('POST', '/api/settings', { changes: { 'cooldown.macroMs': 800 } });
  await sleep(900);
  const c1 = await good.call('POST', '/api/macro/live'), c2 = await good.call('POST', '/api/macro/live');
  check('repeat press inside the guard is ignored (429)', c1.status === 200 && c2.status === 429, JSON.stringify([c1.status, c2.status]));
  await sleep(900);
  check('press after the guard window works again', (await good.call('POST', '/api/macro/live')).status === 200);
  await good.call('POST', '/api/settings', { changes: { 'cooldown.macroMs': 0 } });

  obs.scenes = ['Main'];                              // BRB scene disappears
  await sleep(2200);
  const ps2 = (await good.call('GET', '/api/prestream')).json.items;
  const mac = ps2.find(i => i.id === 'macros');
  check('prestream: missing scene is reported by name', mac?.status === 'fail' && mac.detail.includes('BRB'), JSON.stringify(mac));
  const miss = await good.call('POST', '/api/macro/brb');
  check('macro with a missing scene fails with OBS comment', miss.status === 500 && /scene/i.test(miss.json.error || ''), JSON.stringify(miss));

  const dn = await diagnoseObs({ host: '127.0.0.1', port: 1, password: '', src: 'none' });
  check('diagnose: OBS not running says so and what to do', !dn.ok && dn.code === 'not-running' && /Start OBS/.test(dn.detail), dn.detail);
  const dnp = await diagnoseObs({ host: '127.0.0.1', port: obsPort, password: '', src: 'none' });
  check('diagnose: OBS up but no password stored', dnp.code === 'no-password' && /OBS_WS_PASSWORD/.test(dnp.detail), dnp.detail);
  const dbp = await diagnoseObs({ host: '127.0.0.1', port: obsPort, password: 'nope', src: 'the key vault' });
  check('diagnose: OBS up but wrong password names where it came from', dbp.code === 'bad-password' && /the key vault/.test(dbp.detail), dbp.detail);
  check('Test button endpoint: pass when good', (await good.call('POST', '/api/test-obs')).status === 200);
  const tb = await bad.call('POST', '/api/test-obs');
  check('Test button endpoint: fail with the one-step fix', tb.status === 424 && /OBS_WS_PASSWORD/.test(tb.json.error || ''), JSON.stringify(tb));
  const b = await bad.call('GET', '/api/obs');
  check('wrong OBS password is reported clearly', b.json.connected === false && /password is wrong/.test(b.json.error || ''), JSON.stringify(b.json));
  const bp = (await bad.call('GET', '/api/prestream')).json.items.find(i => i.id === 'obs');
  check('prestream: wrong password = fail', bp?.status === 'fail');
  check('no password text in any output', !JSON.stringify([ps, ps2, b, bp]).match(/pw-secret-1|bad-secret-2/));
} finally {
  for (const n of [good, bad, off]) { n.child.kill(); try { fs.rmSync(n.dir, { recursive: true, force: true }); } catch {} }
  closeObs();
}
const failed = results.filter(r => !r).length;
console.log(failed ? `\n${failed} check(s) FAILED` : '\nAll OBS control checks passed');
process.exit(failed ? 1 : 0);
