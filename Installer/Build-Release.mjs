// INDEX Build-Release.mjs: packs the CURRENT built Suite into a release folder (suite-<ver>.zip + manifest.json [+ manifest.sig]) for the Installer / Updater / GitHub release.
// node Installer/Build-Release.mjs [--version 1.2.3] [--out Installer/dist/release] [--sign-key <ed25519 private key b64 file>]
// Read-only on the tree: never launches, stops or builds anything. Whitelist only; a deny-scan aborts if anything secret-looking would ship.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { writeZip } from '../Suite/updater/lib/zip.mjs';
import { sha256 } from '../Suite/updater/lib/apply.mjs';
import { hashComponents, SKIP_DIR, SKIP_FILE } from '../Suite/updater/lib/components.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2), opt = n => { const i = args.indexOf('--' + n); return i >= 0 ? args[i + 1] : undefined; };
const d = new Date(), p2 = n => String(n).padStart(2, '0');
const version = opt('version') || `1.${d.getFullYear()}${p2(d.getMonth() + 1)}${p2(d.getDate())}.${p2(d.getHours())}${p2(d.getMinutes())}`;
const outDir = path.resolve(opt('out') || path.join(ROOT, 'Installer', 'dist', 'release'));

// what ships: [relative root, filter]. Everything else (Data, vault, Archive, .venv, node_modules, listen models, logs, tests, other repos) never does.
const PLAN = [
  ['Suite/suite', null], ['Suite/modules', null], ['Suite/updater', null], ['Suite/modules.json', null], ['Suite/requirements.txt', null], ['Suite/README.md', null],
  ['PinguinoHost/bin/Release/net8.0', null],
  ['App/src-tauri/target/release/binaries/pinguino-core.exe', null], ['App/src-tauri/target/release/pinguino-suite.exe', null],
  ['PinguinoLite/src-tauri/target/release/pinguino-lite.exe', null], ['PinguinoLite/Start-Lite.bat', null],
  ['App/Setup-Suite.ps1', null], ['App/Update-Module.ps1', null], ['PinguinoApp/PinguinoApp.bat', null],
  ['Installer/install.mjs', null], ['Installer/prereqs.mjs', null],
  ['Docs/INSTALL.md', null], ['README.md', null],
];
const DENY = /(vault\.bin|module_secret|\.env($|\.)|secrets?[._-][^/]*\.json$|\.pgb$|\.dpapi$|install\.key|ghp_|github_pat_)/i;

const files = [];
(function walk() {
  for (const [rel] of PLAN) {
    const abs = path.join(ROOT, rel);
    if (!fs.existsSync(abs)) { if (/pinguino-suite\.exe|pinguino-core\.exe|PinguinoHost\.dll/.test(rel)) { console.error(`missing ${rel}: build it first (App\Build-All.bat --no-launch)`); process.exit(1); } continue; }
    const add = (a, r) => {
      const st = fs.statSync(a);
      if (st.isDirectory()) { if (SKIP_DIR.test(r + '/')) return; for (const n of fs.readdirSync(a)) add(path.join(a, n), `${r}/${n}`); return; }
      if (SKIP_FILE.test(r)) return;
      files.push({ name: r, abs: a });
    };
    add(abs, rel);
  }
})();
const hits = files.filter(f => DENY.test(f.name));
if (hits.length) { console.error('refusing to build: secret-looking files in the release:\n' + hits.map(h => '  ' + h.name).join('\n')); process.exit(1); }
if (!files.some(f => f.name.endsWith('PinguinoHost.dll')) || !files.some(f => f.name.endsWith('suite.py'))) { console.error('the release is missing PinguinoHost.dll or suite.py; build first'); process.exit(1); }

const entries = files.map(f => ({ name: f.name, data: fs.readFileSync(f.abs) }));
const zip = writeZip(entries);
const components = hashComponents(entries.map(e => ({ rel: e.name, data: e.data })));   // per-part hashes: the in-app updater shows and applies one part at a time
fs.mkdirSync(outDir, { recursive: true });
const zname = `suite-${version}.zip`;
fs.writeFileSync(path.join(outDir, zname), zip);
const manifestObj = { schema: 1, channel: 'stable', version, released: d.toISOString(), notes: `${files.length} files`, components, files: [{ name: zname, size: zip.length, sha256: sha256(zip), url: zname }] };
const manifest = JSON.stringify(manifestObj, null, 2);
fs.writeFileSync(path.join(outDir, 'manifest.json'), manifest);
if (opt('sign-key')) {
  const { signManifest } = await import('../Suite/updater/lib/sign.mjs');
  fs.writeFileSync(path.join(outDir, 'manifest.sig'), signManifest(Buffer.from(manifest), fs.readFileSync(opt('sign-key'), 'utf8').trim()));
}
console.log(JSON.stringify({ ok: true, version, out: outDir, files: files.length, zipBytes: zip.length }));
