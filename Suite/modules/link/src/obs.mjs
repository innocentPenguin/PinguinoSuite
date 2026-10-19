// Minimal obs-websocket v5 client (OBS 28+ has it built in). Uses Node's global WebSocket.
import crypto from 'node:crypto';
import net from 'node:net';

const sha = s => crypto.createHash('sha256').update(s).digest('base64');

export function runRequests({ host, port, password }, requests, timeoutMs = 5000) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(`ws://${host}:${port}`);
    const results = [];
    let next = 0;
    const timer = setTimeout(() => { ws.close(); reject(new Error('OBS timed out (is OBS running with WebSocket enabled?)')); }, timeoutMs);
    const fail = e => { clearTimeout(timer); reject(e); };
    const sendNext = () => {
      if (next >= requests.length) { clearTimeout(timer); ws.close(); return resolve(results); }
      const r = requests[next];
      ws.send(JSON.stringify({ op: 6, d: { requestType: r.type, requestId: String(next), requestData: r.data } }));
    };
    ws.onerror = () => fail(new Error(`cannot reach OBS at ${host}:${port}`));
    ws.onmessage = ev => {
      const m = JSON.parse(ev.data);
      if (m.op === 0) {                                    // Hello
        const id = { rpcVersion: 1 };
        if (m.d.authentication) {
          const { challenge, salt } = m.d.authentication;
          id.authentication = sha(sha(password + salt) + challenge);
        }
        ws.send(JSON.stringify({ op: 1, d: id }));
      } else if (m.op === 2) sendNext();                   // Identified
      else if (m.op === 7) {                               // RequestResponse
        results.push(m.d.requestStatus);
        if (!m.d.requestStatus.result) return fail(new Error(`${m.d.requestType}: ${m.d.requestStatus.comment}`));
        next++; sendNext();
      }
    };
    ws.onclose = e => { if (e.code === 4009) fail(new Error('OBS WebSocket password is wrong')); };
  });
}

// Small helper: one connection, returns each request's responseData.
export function getData({ host, port, password }, types, timeoutMs = 4000) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(`ws://${host}:${port}`);
    const res = [];
    const timer = setTimeout(() => { ws.close(); reject(new Error('OBS timed out')); }, timeoutMs);
    const fail = e => { clearTimeout(timer); try { ws.close(); } catch {} reject(e); };
    ws.onerror = () => fail(new Error(`cannot reach OBS at ${host}:${port}`));
    ws.onclose = e => { if (e.code === 4009) fail(new Error('OBS WebSocket password is wrong')); };
    ws.onmessage = ev => {
      const m = JSON.parse(ev.data);
      if (m.op === 0) {
        const id = { rpcVersion: 1 };
        if (m.d.authentication) id.authentication = sha(sha(password + m.d.authentication.salt) + m.d.authentication.challenge);
        ws.send(JSON.stringify({ op: 1, d: id }));
      } else if (m.op === 2) types.forEach((t, i) => ws.send(JSON.stringify({ op: 6, d: { requestType: t, requestId: String(i) } })));
      else if (m.op === 7) {
        res[Number(m.d.requestId)] = m.d.responseData || {};
        if (res.filter(Boolean).length === types.length) { clearTimeout(timer); ws.close(); resolve(res); }
      }
    };
  });
}

let cache = { at: 0, key: '', v: null };
/** Read-only OBS state for the dashboard and safety checks. Cached 2 s. Never throws. */
export async function obsState(conn, { fresh = false } = {}) {
  const key = `${conn.host}:${conn.port}`;
  if (!fresh && cache.v && cache.key === key && Date.now() - cache.at < 2000) return cache.v;
  let v;
  try {
    const [sc, st, rc, inp] = await getData(conn, ['GetSceneList', 'GetStreamStatus', 'GetRecordStatus', 'GetInputList'], 2500);
    v = { connected: true, scene: sc.currentProgramSceneName || '', scenes: (sc.scenes || []).map(s => s.sceneName), inputs: (inp.inputs || []).map(i => i.inputName), streaming: !!st.outputActive, recording: !!rc.outputActive };
  } catch (e) { v = { connected: false, error: e.message }; }
  cache = { at: Date.now(), key, v };
  return v;
}

/** Forget the cached state (call after anything that changes OBS). */
export const forgetState = () => { cache = { at: 0, key: '', v: null }; };

/** One true sentence about OBS: not running / no password stored / wrong password / fine. Used by pre-stream and the key's Test button. */
export async function diagnoseObs(conn) {
  const addr = `${conn.host}:${conn.port}`;
  const open = await new Promise(res => {
    const sock = net.connect({ host: conn.host, port: conn.port });
    const done = v => { sock.destroy(); res(v); };
    sock.setTimeout(1500, () => done(false)); sock.once('connect', () => done(true)); sock.once('error', () => done(false));
  });
  if (!open) return { ok: false, code: 'not-running', detail: `OBS is not running, or its WebSocket server is off (nothing is listening on ${addr}). Start OBS, then turn on Tools > WebSocket Server Settings > Enable WebSocket server.` };
  try {
    const [v] = await getData(conn, ['GetVersion'], 4000);
    return { ok: true, code: 'ok', detail: `OBS ${v.obsVersion || ''} is running at ${addr} and accepted the password`.replace('OBS  ', 'OBS ') };
  } catch (e) {
    if (/password is wrong/.test(e.message)) {
      return conn.src === 'none'
        ? { ok: false, code: 'no-password', detail: 'OBS is running and asks for a password, but none is stored. Enter it in Integrations > Key vault > OBS_WS_PASSWORD (OBS: Tools > WebSocket Server Settings > Show Connect Info).' }
        : { ok: false, code: 'bad-password', detail: `OBS is running but rejected the password stored in ${conn.src}. Re-enter it in Integrations > Key vault > OBS_WS_PASSWORD (OBS: Tools > WebSocket Server Settings > Show Connect Info).` };
    }
    return { ok: false, code: 'error', detail: e.message };
  }
}
