// INDEX Build-Installer.mjs: builds Installer/dist/PinguinoSuiteSetup.exe, ONE file for the other PC: stub exe + payload (node.exe, installer scripts, the release, the sealed key if present).
// node Installer/Build-Installer.mjs [--version 1.2.3] [--release <dir already built by Build-Release.mjs>] [--no-key]
// Read-only on the tree. Never launches/stops anything, never touches OBS. The sealed key (Installer/install.key.enc) is included only if it exists; it is useless without the passphrase.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { writeZip } from '../Suite/updater/lib/zip.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url)), ROOT = path.resolve(HERE, '..');
const args = process.argv.slice(2), opt = n => { const i = args.indexOf('--' + n); return i >= 0 ? args[i + 1] : undefined; }, has = n => args.includes('--' + n);
const dist = path.join(HERE, 'dist'), relDir = path.resolve(opt('release') || path.join(dist, 'release'));
const log = s => console.log(s);

// 1. release
if (!opt('release')) {
  log('building the release...');
  const o = execFileSync(process.execPath, [path.join(HERE, 'Build-Release.mjs'), '--out', relDir, ...(opt('version') ? ['--version', opt('version')] : [])], { encoding: 'utf8' });
  log(o.trim());
}
if (!fs.existsSync(path.join(relDir, 'manifest.json'))) { console.error('no release at ' + relDir); process.exit(1); }

// 2. stub exe (std-only rustc; no downloads)
const stub = path.join(dist, 'stub.exe');
fs.mkdirSync(dist, { recursive: true });
const env = { ...process.env, PATH: `${process.env.PATH};${path.join(os.homedir(), '.cargo', 'bin')}` };
log('building the stub...');
execFileSync('rustc', ['-O', '--edition', '2021', path.join(HERE, 'pinguino_installer.rs'), '-o', stub], { env, stdio: 'inherit' });
for (const f of fs.readdirSync(dist)) if (f.endsWith('.pdb')) fs.unlinkSync(path.join(dist, f));

// 3. payload
const add = (list, name, abs) => list.push({ name, data: fs.readFileSync(abs) });
const entries = [];
add(entries, 'node.exe', process.execPath);
for (const f of ['install.mjs', 'prereqs.mjs', 'Installer.hta']) add(entries, `Installer/${f}`, path.join(HERE, f));
const key = path.join(HERE, 'install.key.enc');
if (!has('no-key') && fs.existsSync(key)) add(entries, 'Installer/install.key.enc', key);
for (const f of fs.readdirSync(path.join(ROOT, 'Suite', 'updater', 'lib'))) if (f.endsWith('.mjs')) add(entries, `Suite/updater/lib/${f}`, path.join(ROOT, 'Suite', 'updater', 'lib', f));
for (const f of fs.readdirSync(relDir)) if (/^(manifest\.json|manifest\.sig|suite-[0-9.]+\.zip)$/.test(f)) add(entries, `release/${f}`, path.join(relDir, f));
log(`packing ${entries.length} files...`);
const payload = writeZip(entries);

// 4. stub + payload + trailer
const out = path.join(dist, 'PinguinoSuiteSetup.exe'), tr = Buffer.alloc(16);
tr.writeBigUInt64LE(BigInt(payload.length), 0); tr.write('PGSETUP1', 8, 'latin1');
fs.writeFileSync(out, Buffer.concat([fs.readFileSync(stub), payload, tr]));
fs.unlinkSync(stub);
log(JSON.stringify({ ok: true, installer: out, bytes: fs.statSync(out).size, hasKey: entries.some(e => e.name.endsWith('install.key.enc')), release: JSON.parse(fs.readFileSync(path.join(relDir, 'manifest.json'), 'utf8')).version }));
