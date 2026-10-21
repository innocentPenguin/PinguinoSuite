// INDEX sign.mjs: optional Ed25519 signature over manifest.json (file manifest.sig, base64). Verified only when a public key is configured
// (install.json "pubkey", or --pubkey); with a key set an unsigned or badly signed manifest is refused. Key = base64 of the raw 32 byte public key.
import crypto from 'node:crypto';

const SPKI_PREFIX = Buffer.from('302a300506032b6570032100', 'hex');
const PKCS8_PREFIX = Buffer.from('302e020100300506032b657004220420', 'hex');

export function publicKeyFromB64(b64) {
  const raw = Buffer.from(String(b64 || '').trim(), 'base64');
  if (raw.length !== 32) throw new Error('the update public key must be 32 bytes (base64)');
  return crypto.createPublicKey({ key: Buffer.concat([SPKI_PREFIX, raw]), format: 'der', type: 'spki' });
}

/** Throws unless sigB64 is a valid Ed25519 signature of rawManifest under pubkeyB64. */
export function verifyManifestSignature(rawManifest, sigB64, pubkeyB64) {
  if (!sigB64) throw new Error('this release is not signed but a signing key is configured; refusing it');
  const ok = crypto.verify(null, rawManifest, publicKeyFromB64(pubkeyB64), Buffer.from(String(sigB64).trim(), 'base64'));
  if (!ok) throw new Error('the release signature does not match the configured key; refusing it');
}

/** Release-builder helpers (used by the tests and by whoever signs a release; the private key never lives in the repo). */
export function generateKeyPair() {
  const { publicKey, privateKey } = crypto.generateKeyPairSync('ed25519');
  return { pubkey: publicKey.export({ format: 'der', type: 'spki' }).subarray(-32).toString('base64'), seed: privateKey.export({ format: 'der', type: 'pkcs8' }).subarray(-32).toString('base64') };
}
export function signManifest(rawManifest, seedB64) {
  const key = crypto.createPrivateKey({ key: Buffer.concat([PKCS8_PREFIX, Buffer.from(seedB64, 'base64')]), format: 'der', type: 'pkcs8' });
  return crypto.sign(null, rawManifest, key).toString('base64');
}
