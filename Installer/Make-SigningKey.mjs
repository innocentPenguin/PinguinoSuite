// INDEX Make-SigningKey.mjs: run ONCE by Ivan. Creates the Ed25519 release-signing key pair.
// The private seed goes to a file OUTSIDE the repo (default %USERPROFILE%\.pinguino\signing-seed.txt) and is never printed;
// the public key (safe to share) is printed and saved next to it as signing-pubkey.txt. It never overwrites an existing seed.
// node Installer/Make-SigningKey.mjs [--out <folder>]
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { generateKeyPair } from '../Suite/updater/lib/sign.mjs';

const i = process.argv.indexOf('--out');
const dir = path.resolve(i >= 0 ? process.argv[i + 1] : path.join(os.homedir(), '.pinguino'));
const repo = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')), '..');
if (dir.toLowerCase().startsWith(repo.toLowerCase())) { console.error('Refusing: the private key must live outside the repo folder.'); process.exit(1); }
const seedFile = path.join(dir, 'signing-seed.txt');
if (fs.existsSync(seedFile)) { console.error(`A signing seed already exists at ${seedFile}. Nothing was changed (delete it by hand only if you really want a new key; every install then needs the new public key).`); process.exit(1); }
fs.mkdirSync(dir, { recursive: true });
const k = generateKeyPair();
fs.writeFileSync(seedFile, k.seed + '\n', { mode: 0o600 });
fs.writeFileSync(path.join(dir, 'signing-pubkey.txt'), k.pubkey + '\n');
console.log(`Private seed written to ${seedFile} (back it up somewhere safe; never commit or share it).`);
console.log('Public key (give this to installs: --pubkey, or "pubkey" in install.json):');
console.log(k.pubkey);
