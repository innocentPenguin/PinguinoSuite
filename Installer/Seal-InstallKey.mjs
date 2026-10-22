// INDEX Seal-InstallKey.mjs: run ONCE by Ivan. Encrypts the read-only GitHub token with an install passphrase into Installer/install.key.enc (gitignored).
// The token and passphrase are typed into this window (hidden); they are never written anywhere in plaintext, never put on a command line, never echoed.
// node Installer/Seal-InstallKey.mjs            (or Seal-InstallKey.bat)
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { seal, unseal } from '../Suite/updater/lib/secret.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
function ask(label) {
  return new Promise(res => {
    process.stdout.write(label);
    const stdin = process.stdin; let v = '';
    if (!stdin.isTTY) { stdin.setEncoding('utf8'); stdin.once('data', d => res(String(d).split(/\r?\n/)[0])); return; }
    stdin.setRawMode(true); stdin.resume(); stdin.setEncoding('utf8');
    const on = c => {
      for (const ch of c) {
        if (ch === '\r' || ch === '\n') { stdin.setRawMode(false); stdin.pause(); stdin.off('data', on); process.stdout.write('\n'); return res(v); }
        if (ch === '\u0003') process.exit(130);
        if (ch === '\u007f' || ch === '\b') v = v.slice(0, -1); else v += ch;
      }
    };
    stdin.on('data', on);
  });
}
const token = (await ask('Read-only GitHub token (input is hidden): ')).trim();
if (!/^(github_pat_|ghp_)[A-Za-z0-9_]{20,}$/.test(token)) { console.error('That does not look like a GitHub token (it should start with github_pat_ or ghp_). Nothing was written.'); process.exit(1); }
const p1 = await ask('Choose an install passphrase, 8+ characters (hidden): ');
const p2 = await ask('Type it again: ');
if (p1 !== p2) { console.error('The passphrases differ. Nothing was written.'); process.exit(1); }
const blob = seal(token, p1);
unseal(blob, p1);   // round-trip check before writing
fs.writeFileSync(path.join(here, 'install.key.enc'), blob);
console.log('Sealed. Installer\install.key.enc written (it is gitignored). You will type this passphrase once on the other PC.');
