// Safe read-only check of the REAL OBS: GetVersion, GetSceneList, GetInputList only (no state change, never touches the stream).
// Password: OBS_WS_PASSWORD from the key vault (needs PINGUINO_API_TOKEN of a module, as the core gives to Link) or the Link config file.
// Prints scene and input names, never the password. Without a password or without OBS it prints one line saying why and exits 0.
//   node src/obsreadcheck.mjs            real check
//   node src/obsreadcheck.mjs --selftest against the fake OBS (also proves only read requests are sent)
import './testenv.mjs';
import { fileURLToPath } from 'node:url';
import * as cfgm from './config.mjs';
import { obsConn } from './vault.mjs';
import { getData } from './obs.mjs';

export const READ_ONLY = ['GetVersion', 'GetSceneList', 'GetInputList'];

/** Returns { ok, lines } and never throws; lines never contain the password. */
export async function readCheck(conn) {
  if (!conn.password) return { ok: false, lines: [`skipped: no OBS_WS_PASSWORD in the key vault or the Link config (source: ${conn.src})`] };
  try {
    const [ver, scenes, inputs] = await getData(conn, READ_ONLY);
    return { ok: true, lines: [
      `OBS ${ver.obsVersion || '?'} (websocket ${ver.obsWebSocketVersion || '?'}) reached at ${conn.host}:${conn.port}, password from ${conn.src}`,
      `scenes (${(scenes.scenes || []).length}), current "${scenes.currentProgramSceneName || '?'}": ${(scenes.scenes || []).map(s => s.sceneName).join(', ') || '-'}`,
      `inputs (${(inputs.inputs || []).length}): ${(inputs.inputs || []).map(i => i.inputName).join(', ') || '-'}`,
    ] };
  } catch (e) {
    return { ok: false, lines: [`OBS not usable: ${String(e.message || e).split(conn.password).join('***')}`] };
  }
}

async function selftest() {
  process.env.PINGUINO_NEVER_REAL_OBS = '1';
  const { startFakeObs } = await import('./fakeobs.mjs');
  const f = await startFakeObs('pw-secret-1');
  let bad = 0; const check = (n, c) => { console.log((c ? 'PASS  ' : 'FAIL  ') + n); if (!c) bad++; };
  const r = await readCheck({ host: '127.0.0.1', port: f.obsPort, password: 'pw-secret-1', src: 'test' });
  check('reads version, scenes, inputs', r.ok && /31\.0\.0/.test(r.lines[0]) && /Main, BRB/.test(r.lines[1]) && /Mic\/Aux/.test(r.lines[2]));
  check('only read-only requests were sent', f.obs.log.length === 3 && f.obs.log.every(t => READ_ONLY.includes(t)));
  check('password never printed', !r.lines.join('\n').includes('pw-secret-1'));
  const w = await readCheck({ host: '127.0.0.1', port: f.obsPort, password: 'wrong-pw', src: 'test' });
  check('wrong password gives a one-line reason without the password', !w.ok && w.lines.length === 1 && !w.lines[0].includes('wrong-pw'));
  const n = await readCheck({ host: '127.0.0.1', port: f.obsPort, password: '', src: 'none' });
  check('no password skips with a reason', !n.ok && /no OBS_WS_PASSWORD/.test(n.lines[0]));
  f.close();
  console.log(bad ? `${bad} check(s) FAILED` : 'All OBS read-only checks passed');
  process.exit(bad ? 1 : 0);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  if (process.argv.includes('--selftest')) await selftest();
  else {
    const conn = await obsConn(cfgm.load());
    const r = await readCheck(conn);
    console.log(r.lines.join('\n'));
    process.exit(0);
  }
}
