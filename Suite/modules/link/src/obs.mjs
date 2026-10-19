// Minimal obs-websocket v5 client (OBS 28+ has it built in). Uses Node's global WebSocket.
import crypto from 'node:crypto';

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
