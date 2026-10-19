// OBS control self-check against a FAKE obs-websocket v5 server (never touches the real OBS or stream).
// Run: node src/macrocheck.mjs
import { spawn } from 'node:child_process';
import http from 'node:http';
import crypto from 'node:crypto';
import os from 'node:os';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const cli = fileURLToPath(new URL('./cli.mjs', import.meta.url));
const results = [];
const check = (name, ok, extra = '') => { results.push(ok); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${ok ? '' : '  ' + extra}`); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const sha = s => crypto.createHash('sha256').update(s).digest('base64');

// ---- fake OBS ----
const obs = { scene: 'Main', scenes: ['Main', 'BRB'], inputs: ['Mic/Aux'], streaming: false, recording: false, muted: false, password: 'pw-secret-1', log: [] };
function frame(op, payload) {
  const len = payload.length;
  const head = len < 126 ? Buffer.from([0x80 | op, len]) : Buffer.from([0x80 | op, 126, len >> 8, len & 255]);
  return Buffer.concat([head, payload]);
}
const fakeObs = http.createServer();
fakeObs.on('upgrade', (req, sock) => {
  const accept = crypto.createHash('sha1').update(req.headers['sec-websocket-key'] + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest('base64');
  sock.write(`HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: ${accept}\r\n\r\n`);
  const send = o => sock.write(frame(1, Buffer.from(JSON.stringify(o))));
  const challenge = crypto.randomBytes(8).toString('hex'), salt = crypto.randomBytes(8).toString('hex');
  send({ op: 0, d: { obsWebSocketVersion: '5.5.0', rpcVersion: 1, authentication: { challenge, salt } } });
  let buf = Buffer.alloc(0);
  sock.on('error', () => {});
  sock.on('data', d => {
    buf = Buffer.concat([buf, d]);
    for (;;) {
      if (buf.length < 2) return;
      let len = buf[1] & 127, off = 2;
      if (len === 126) { if (buf.length < 4) return; len = buf.readUInt16BE(2); off = 4; }
      if (buf.length < off + 4 + len) return;
      const mask = buf.subarray(off, off + 4), data = Buffer.from(buf.subarray(off + 4, off + 4 + len));
      for (let i = 0; i < data.length; i++) data[i] ^= mask[i % 4];
      const opcode = buf[0] & 15;
      buf = buf.subarray(off + 4 + len);
      if (opcode === 8) return sock.end();
      if (opcode !== 1) continue;
      const m = JSON.parse(data.toString());
      if (m.op === 1) {
        if (m.d.authentication !== sha(sha(obs.password + salt) + challenge)) { sock.write(frame(8, Buffer.from([4009 >> 8, 4009 & 255]))); return sock.end(); }
        send({ op: 2, d: { negotiatedRpcVersion: 1 } });
      } else if (m.op === 6) {
        const { requestType: t, requestId: id, requestData: rd = {} } = m.d;
        obs.log.push(t);
        let ok = true, comment, data = {};
        if (t === 'GetVersion') data = { obsVersion: '31.0.0' };
        else if (t === 'GetSceneList') data = { currentProgramSceneName: obs.scene, scenes: obs.scenes.map(sceneName => ({ sceneName })) };
        else if (t === 'GetInputList') data = { inputs: obs.inputs.map(inputName => ({ inputName })) };
        else if (t === 'GetStreamStatus') data = { outputActive: obs.streaming };
        else if (t === 'GetRecordStatus') data = { outputActive: obs.recording };
        else if (t === 'SetCurrentProgramScene') { if (obs.scenes.includes(rd.sceneName)) obs.scene = rd.sceneName; else { ok = false; comment = 'No scene was found by that name.'; } }
        else if (t === 'StartStream') obs.streaming = true;
        else if (t === 'StopStream') obs.streaming = false;
        else if (t === 'ToggleInputMute') { if (obs.inputs.includes(rd.inputName)) obs.muted = !obs.muted; else { ok = false; comment = 'No input was found by that name.'; } }
        else { ok = false; comment = 'unknown request'; }
        send({ op: 7, d: { requestType: t, requestId: id, requestStatus: { result: ok, code: ok ? 100 : 600, comment }, responseData: data } });
      }
    }
  });
});
await new Promise(r => fakeObs.listen(0, '127.0.0.1', r));
const obsPort = fakeObs.address().port;

// ---- Link instance (hub role) pointed at the fake OBS ----
async function link(password) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'plink-mc-'));
  fs.mkdirSync(path.join(dir, 'link'), { recursive: true });
  const cfg = { role: 'hub', hub: 'x', port: 7777, token: 'module-token-module-token-0001', inbox: dir, obs: { host: '127.0.0.1', port: obsPort, password },
    macros: { brb: [{ type: 'SetCurrentProgramScene', data: { sceneName: 'BRB' } }], live: [{ type: 'SetCurrentProgramScene', data: { sceneName: 'Main' } }],
      start: [{ type: 'StartStream' }], stop: [{ type: 'StopStream' }], mute: [{ type: 'ToggleInputMute', data: { inputName: 'Mic/Aux' } }] }, claude: { enabled: false, cli: 'claude' } };
  fs.writeFileSync(path.join(dir, 'link', 'config.json'), JSON.stringify(cfg));
  const port = 7950 + Math.floor(Math.random() * 40);
  const child = spawn(process.execPath, [cli, 'serve'], { stdio: 'ignore', windowsHide: true,
    env: { ...process.env, PINGUINO_LINK_PORT: String(port), PINGUINO_API_TOKEN: 'core-mc', PINGUINO_DATA_DIR: dir, PINGUINO_CORE_URL: 'http://127.0.0.1:1' } });
  const base = `http://127.0.0.1:${port}`;
  const call = async (method, p) => {
    const r = await fetch(base + p, { method, headers: { 'x-link-token': cfg.token } });
    return { status: r.status, json: await r.json().catch(() => ({})) };
  };
  for (let i = 0; i < 30; i++) { try { if ((await fetch(base + '/api/health')).ok) break; } catch {} await sleep(300); }
  return { dir, child, call };
}

const good = await link('pw-secret-1'), bad = await link('bad-secret-2');
try {
  const st = await good.call('GET', '/api/obs');
  check('OBS state: connected, scene Main, not live', st.json.connected && st.json.scene === 'Main' && st.json.streaming === false, JSON.stringify(st.json));
  const ps = (await good.call('GET', '/api/prestream')).json.items;
  check('prestream: OBS pass', ps.find(i => i.id === 'obs')?.status === 'pass');
  check('prestream: macro targets pass', ps.find(i => i.id === 'macros')?.status === 'pass', JSON.stringify(ps.find(i => i.id === 'macros')));

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

  obs.scenes = ['Main'];                              // BRB scene disappears
  await sleep(2200);
  const ps2 = (await good.call('GET', '/api/prestream')).json.items;
  const mac = ps2.find(i => i.id === 'macros');
  check('prestream: missing scene is reported by name', mac?.status === 'fail' && mac.detail.includes('BRB'), JSON.stringify(mac));
  const miss = await good.call('POST', '/api/macro/brb');
  check('macro with a missing scene fails with OBS comment', miss.status === 500 && /scene/i.test(miss.json.error || ''), JSON.stringify(miss));

  const b = await bad.call('GET', '/api/obs');
  check('wrong OBS password is reported clearly', b.json.connected === false && /password is wrong/.test(b.json.error || ''), JSON.stringify(b.json));
  const bp = (await bad.call('GET', '/api/prestream')).json.items.find(i => i.id === 'obs');
  check('prestream: wrong password = fail', bp?.status === 'fail');
  check('no password text in any output', !JSON.stringify([ps, ps2, b, bp]).match(/pw-secret-1|bad-secret-2/));
} finally {
  for (const n of [good, bad]) { n.child.kill(); try { fs.rmSync(n.dir, { recursive: true, force: true }); } catch {} }
  fakeObs.close();
}
const failed = results.filter(r => !r).length;
console.log(failed ? `\n${failed} check(s) FAILED` : '\nAll OBS control checks passed');
process.exit(failed ? 1 : 0);
