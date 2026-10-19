// Fake obs-websocket v5 server for tests (never touches the real OBS). Shared by macrocheck and remotecheck.
import http from 'node:http';
import crypto from 'node:crypto';
const sha = s => crypto.createHash('sha256').update(s).digest('base64');

export async function startFakeObs(password = 'pw-secret-1') {
  const obs = { scene: 'Main', scenes: ['Main', 'BRB'], inputs: ['Mic/Aux'], streaming: false, recording: false, muted: false, password, log: [] };
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
    return { obs, obsPort, close: () => fakeObs.close() };
}
