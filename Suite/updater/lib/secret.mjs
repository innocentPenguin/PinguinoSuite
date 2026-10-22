// INDEX secret.mjs: the read-only repo token. seal/unseal = passphrase-encrypted file shipped inside the installer (scrypt + AES-256-GCM);
// storeToken/loadToken = Windows DPAPI file on the installed PC (tied to that Windows user, never plaintext on disk). Tokens are never logged.
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

const MAGIC = Buffer.from('PGK1');

export function seal(plain, passphrase) {
  if (String(passphrase).length < 8) throw new Error('the install passphrase must be at least 8 characters');
  const salt = crypto.randomBytes(16), iv = crypto.randomBytes(12);
  const key = crypto.scryptSync(passphrase, salt, 32, { N: 2 ** 15, r: 8, p: 1, maxmem: 128 * 1024 * 1024 });
  const c = crypto.createCipheriv('aes-256-gcm', key, iv), ct = Buffer.concat([c.update(String(plain), 'utf8'), c.final()]);
  return Buffer.concat([MAGIC, salt, iv, c.getAuthTag(), ct]);
}

export function unseal(buf, passphrase) {
  if (buf.length < 48 || !buf.subarray(0, 4).equals(MAGIC)) throw new Error('that is not an install key file');
  const salt = buf.subarray(4, 20), iv = buf.subarray(20, 32), tag = buf.subarray(32, 48), ct = buf.subarray(48);
  const key = crypto.scryptSync(passphrase, salt, 32, { N: 2 ** 15, r: 8, p: 1, maxmem: 128 * 1024 * 1024 });
  try {
    const d = crypto.createDecipheriv('aes-256-gcm', key, iv); d.setAuthTag(tag);
    return Buffer.concat([d.update(ct), d.final()]).toString('utf8');
  } catch { throw new Error('wrong install passphrase, or the key file is damaged'); }
}

const tokFile = installDir => path.join(installDir, 'Data', 'runtime', 'update_token.dpapi');
const ps = (script, env) => execFileSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', script], { env: { ...process.env, ...env }, windowsHide: true, encoding: 'utf8' }).trim();

/** Encrypt with DPAPI (current Windows user) and write Data/runtime/update_token.dpapi. The token travels in an env var, not on a command line. */
export function storeToken(installDir, token) {
  fs.mkdirSync(path.dirname(tokFile(installDir)), { recursive: true });
  const enc = ps('ConvertTo-SecureString $env:PG_TOK -AsPlainText -Force | ConvertFrom-SecureString', { PG_TOK: token });
  fs.writeFileSync(tokFile(installDir), enc);
}

export function loadToken(installDir) {
  try {
    const enc = fs.readFileSync(tokFile(installDir), 'utf8').trim();
    if (!enc) return null;
    return ps('$s=ConvertTo-SecureString $env:PG_ENC;[Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s))', { PG_ENC: enc }) || null;
  } catch { return null; }
}
