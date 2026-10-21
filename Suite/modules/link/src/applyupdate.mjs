// INDEX applyupdate.mjs: detached helper that installs a staged PinguinoLite update. Started by lite.mjs on a "selfupdate-apply" request
// (which only exists after the user clicked "Update" in Lite). Lite exits right after that click and kills Link with it, so this
// helper runs on its own: wait for Lite to exit -> re-verify hash -> back up the install folder -> run the installer silently
// -> relaunch Lite; if anything fails, put the backup back and relaunch the old version.
// Usage: node applyupdate.mjs <job.json>. Writes <lite dir>\lite_apply_result.json. Never touches the network.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { spawn, execFile } from 'node:child_process';

const jobFile = process.argv[2];
const job = JSON.parse(fs.readFileSync(jobFile, 'utf8'));
const { liteDir, installer, sha256, exe, from, to, waitMs = 90000, installMs = 300000 } = job;
const TEST = process.env.PINGUINO_LITE_TEST === '1';          // tests may swap the process name and the installer command
const procName = TEST && job.procName ? job.procName : 'PinguinoLite.exe';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const iso = () => new Date().toISOString();
const logf = path.join(liteDir, 'lite_apply.log');
const say = m => { try { fs.appendFileSync(logf, `${iso()} ${m}\n`); } catch {} };
const result = (ok, msg, extra = {}) => {
  const f = path.join(liteDir, 'lite_apply_result.json');
  fs.writeFileSync(f + '.tmp', JSON.stringify({ schema: 1, at: iso(), ok, message: msg, from, to, ...extra }, null, 2));
  fs.renameSync(f + '.tmp', f);
  say(`${ok ? 'OK' : 'FAILED'}: ${msg}`);
};

const running = () => new Promise(res => execFile('tasklist.exe', ['/FI', `IMAGENAME eq ${procName}`, '/NH'], { windowsHide: true }, (e, out) => res(!e && out.toLowerCase().includes(procName.toLowerCase()))));
const launch = file => { try { const c = spawn(file, [], { detached: true, stdio: 'ignore', windowsHide: false }); c.on('error', e => say(`relaunch error: ${e.code || e.message}`)); c.unref(); say(`relaunched ${file}`); return true; } catch (e) { say(`could not relaunch: ${e.message}`); return false; } };
const hashOf = f => crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex');

async function main() {
  say(`apply ${from} -> ${to}: waiting for ${procName} to exit`);
  // 1. verify before anything else (the file could have changed since the click)
  const staging = path.resolve(liteDir, 'staging') + path.sep;
  const inst = path.resolve(installer);
  if (!inst.startsWith(staging) || !/^PinguinoLite-\d+(\.\d+)*-setup\.exe$/.test(path.basename(inst))) return result(false, 'installer is not a staged PinguinoLite setup file; nothing was changed');
  let want = ''; try { want = fs.readFileSync(inst + '.sha256', 'utf8').trim().split(/\s+/)[0].toLowerCase(); } catch {}
  if (!/^[0-9a-f]{64}$/.test(want) || want !== sha256 || hashOf(inst) !== want) return result(false, 'installer hash does not match; nothing was changed');
  // 2. wait for Lite to be closed (we never kill it)
  const t0 = Date.now();
  while (await running()) { if (Date.now() - t0 > waitMs) return result(false, 'PinguinoLite did not close in time; nothing was changed. Close it and click Update again'); await sleep(1000); }
  // 3. back up the install folder
  const dir = path.dirname(exe);
  const backup = path.join(liteDir, 'backup', `lite-${from}-${iso().replace(/[-:T]/g, '').slice(0, 14)}`);
  try { fs.mkdirSync(path.dirname(backup), { recursive: true }); fs.cpSync(dir, backup, { recursive: true }); }
  catch (e) { return result(false, `could not back up the current version (${e.code || e.message}); nothing was changed`); }
  say(`backup at ${backup}`);
  // 4. silent install
  const cmd = TEST && job.installCmd ? job.installCmd : [inst, '/S'];
  const code = await new Promise(res => {
    let done = false; const fin = c => { if (!done) { done = true; res(c); } };
    const c = spawn(cmd[0], cmd.slice(1), { stdio: 'ignore', windowsHide: true });
    c.on('error', () => fin(-1)); c.on('exit', fin);
    setTimeout(() => { try { c.kill(); } catch {} fin(-2); }, installMs);
  });
  // 5. relaunch, or roll back
  if (code === 0 && fs.existsSync(exe)) {
    launch(exe);
    return result(true, `PinguinoLite updated ${from} -> ${to}`, { backup });
  }
  say(`installer exit code ${code}; restoring the old version`);
  try { fs.cpSync(backup, dir, { recursive: true, force: true }); } catch (e) { say(`restore problem: ${e.message}`); }
  launch(exe);
  result(false, `installer failed (exit ${code}); the old version ${from} was put back`, { backup });
}
main().catch(e => { try { result(false, `update stopped: ${String(e.message).slice(0, 150)}`); } catch {} });
