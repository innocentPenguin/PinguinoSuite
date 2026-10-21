// INDEX sources.mjs: where a release comes from. openSource({type:'local'|'https', ...}) -> {manifest, fetchFile(entry)}; every source yields the same shape.
// gitStatus/gitUpdate handle the git source (an install folder that is a clone). Nothing here verifies hashes: apply.mjs does that.
import fs from 'node:fs';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { parseManifest, cmpVersion } from './manifest.mjs';
import { readZip } from './zip.mjs';
import { verifyManifestSignature } from './sign.mjs';

const MAX_MANIFEST = 256 * 1024, MAX_FILE = 2 * 1024 * 1024 * 1024;

async function httpGet(url, { timeoutMs = 10000, maxBytes = MAX_FILE, allowHttpLocal = false } = {}) {
  const u = new URL(url);
  const local = ['127.0.0.1', 'localhost', '[::1]'].includes(u.hostname);
  if (u.protocol !== 'https:' && !(allowHttpLocal && local && u.protocol === 'http:')) throw new Error('updates must come from an https address');
  const r = await fetch(url, { redirect: 'follow', signal: AbortSignal.timeout(timeoutMs) });
  if (r.url && new URL(r.url).protocol !== u.protocol) throw new Error('refusing a redirect to another protocol');
  if (!r.ok) throw new Error(`update server answered ${r.status}`);
  const len = Number(r.headers.get('content-length') || 0);
  if (len > maxBytes) throw new Error('update file is larger than allowed');
  const buf = Buffer.from(await r.arrayBuffer());
  if (buf.length > maxBytes) throw new Error('update file is larger than allowed');
  return buf;
}

/** opts.pubkey (base64 raw Ed25519 key): when set the manifest must carry a valid manifest.sig. */
export async function openSource(spec, opts = {}) {
  const guard = (raw, sig) => { if (opts.pubkey) verifyManifestSignature(raw, sig, opts.pubkey); };
  if (spec.type === 'local') {
    const p = path.resolve(spec.path);
    const st = fs.statSync(p);
    if (st.isDirectory()) {
      const mp = path.join(p, 'manifest.json');
      if (fs.statSync(mp).size > MAX_MANIFEST) throw new Error('update manifest is too large');
      const raw = fs.readFileSync(mp), sp = path.join(p, 'manifest.sig');
      guard(raw, fs.existsSync(sp) ? fs.readFileSync(sp, 'utf8') : '');
      return { type: 'local', manifest: parseManifest(raw.toString('utf8'), p), fetchFile: async f => {
        const fp = path.resolve(p, f.url); if (!fp.startsWith(p + path.sep)) throw new Error('release file is outside the release folder');
        return fs.readFileSync(fp); } };
    }
    const entries = readZip(fs.readFileSync(p)), byName = Object.fromEntries(entries.map(e => [e.name, e]));
    if (!byName['manifest.json']) throw new Error('that zip has no manifest.json');
    const rawZ = byName['manifest.json'].data();
    guard(rawZ, byName['manifest.sig'] ? byName['manifest.sig'].data().toString('utf8') : '');
    return { type: 'local', manifest: parseManifest(rawZ.toString('utf8'), p), fetchFile: async f => {
      const e = byName[f.url]; if (!e) throw new Error(`the zip does not contain ${f.url}`); return e.data(); } };
  }
  if (spec.type === 'https') {
    const body = await httpGet(spec.url, { maxBytes: MAX_MANIFEST, ...opts });
    if (opts.pubkey) { let sig = ''; try { sig = (await httpGet(new URL('manifest.sig', spec.url).toString(), { maxBytes: 4096, ...opts })).toString('utf8'); } catch {} guard(body, sig); }
    const manifest = parseManifest(body.toString('utf8'), spec.url);
    return { type: 'https', manifest, fetchFile: f => httpGet(new URL(f.url, spec.url).toString(), opts) };
  }
  throw new Error(`unknown update source: ${spec.type}`);
}

const git = (cwd, args) => new Promise((res, rej) => execFile('git', args, { cwd, windowsHide: true, timeout: 120000 }, (e, out, err) => e ? rej(new Error((err || e.message).trim().slice(0, 300))) : res(out.trim())));

/** {isClone, dirty, current, newest} for an install folder that is a git clone. Tags look like v1.2.3. */
export async function gitStatus(dir, channel = 'stable') {
  try { await git(dir, ['rev-parse', '--is-inside-work-tree']); } catch { return { isClone: false }; }
  const dirty = (await git(dir, ['status', '--porcelain', '--untracked-files=no'])).length > 0;
  await git(dir, ['fetch', '--tags', '--quiet']);
  const tags = (await git(dir, ['tag', '--list', 'v*'])).split(/\r?\n/).filter(t => /^v\d+(\.\d+){0,3}$/.test(t) || (channel === 'beta' && /^v\d+(\.\d+){0,3}-beta\d*$/.test(t)));
  const ver = t => t.replace(/^v/, '').replace(/-beta\d*$/, '');
  tags.sort((a, b) => cmpVersion(ver(a), ver(b)));
  const current = await git(dir, ['describe', '--tags', '--abbrev=0']).catch(() => '');
  return { isClone: true, dirty, current, newest: tags[tags.length - 1] || '', upToDate: !tags.length || (current && cmpVersion(ver(current), ver(tags[tags.length - 1])) >= 0) };
}

/** Fast-forward the clone to a tag. Never discards local edits; the caller must have checked dirty === false. */
export async function gitUpdate(dir, tag) {
  if (!/^v\d+(\.\d+){0,3}(-beta\d*)?$/.test(tag)) throw new Error('bad release tag');
  const before = await git(dir, ['rev-parse', 'HEAD']);
  try { await git(dir, ['merge', '--ff-only', tag]); } catch (e) { throw new Error(`could not fast-forward to ${tag}: ${e.message}`); }
  return { before, after: await git(dir, ['rev-parse', 'HEAD']) };
}
export const gitRollback = (dir, sha) => git(dir, ['reset', '--hard', sha]);
