// INDEX Release-Notes.mjs: plain-language changelog from git history between two tags/commits, grouped Lite / Master / Core / Suite.
// node Installer/Release-Notes.mjs --from <tag|commit> [--to HEAD] [--out notes.txt] [--json]
// Uses ONLY commit subjects and the names of changed files: no hashes, no authors, no e-mails, no bodies. Secret-looking text is replaced. Docs-only commits are left out.
// Build-Release.mjs takes the result with --notes-file <file> (it goes into the signed manifest `notes`, which the updater keeps to 2000 characters).
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

export const MAX_CHARS = 1900;   // manifest.mjs keeps 2000
export const GROUPS = ['Lite', 'Master', 'Core', 'Suite'];

const SECRET = /(oauth:[a-z0-9]{10,}|bearer\s+[a-z0-9._~+/=-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|(?:token|secret|password|api[_-]?key)\s*[:=]\s*\S{6,})/gi;
const EMAIL = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g;

/** Which group a commit belongs to, from the files it changed; null = leave it out (docs/notes only, or nothing). */
export function groupOf(files) {
  const f = files.map(x => x.replace(/\\/g, '/'));
  if (f.some(x => x.startsWith('PinguinoLite/'))) return 'Lite';
  if (f.some(x => /^App\/src\/master\//i.test(x))) return 'Master';
  if (f.some(x => /^(Suite\/suite\/|App\/src-tauri\/)/i.test(x))) return 'Core';
  if (f.some(x => !/^(Docs\/|README|\.remember\/|\.claude\/)/i.test(x))) return 'Suite';
  return null;
}

/** One commit subject -> one plain sentence (no prefix like "Lite:", no secrets or addresses, no trailing period, sentence case). */
export function plain(subject) {
  let s = String(subject || '').replace(SECRET, '[removed]').replace(EMAIL, '[removed]').trim();
  s = s.replace(/^(\w[\w /-]{0,24}):\s+/, '');   // "Updater: undo ..." -> "undo ..."
  s = s.replace(/\s*\(#?\d+\)\s*$/, '').replace(/[.\s]+$/, '');
  if (!s) return '';
  if (s.length > 110) s = s.slice(0, 107).replace(/\s+\S*$/, '') + '...';
  return s[0].toUpperCase() + s.slice(1);
}

/** commits: [{subject, files:[...]}] -> { text, groups:{Lite:[..]...}, count }. Duplicates collapse; the text stays under MAX_CHARS. */
export function buildNotes(commits, { max = MAX_CHARS } = {}) {
  const groups = Object.fromEntries(GROUPS.map(g => [g, []]));
  for (const c of commits) {
    const g = groupOf(c.files || []);
    if (!g || /^(wip|fixup|squash)\b/i.test(c.subject || '')) continue;
    const line = plain(c.subject);
    if (line && !groups[g].includes(line)) groups[g].push(line);
  }
  const count = GROUPS.reduce((n, g) => n + groups[g].length, 0);
  const lines = [];
  let used = 0, dropped = 0;
  for (const g of GROUPS) {
    if (!groups[g].length) continue;
    const head = `${g}:`;
    const items = [];
    for (const it of groups[g]) {
      const add = `- ${it}`;
      if (used + head.length + add.length + 40 > max) { dropped++; continue; }
      items.push(add); used += add.length + 1;
    }
    if (items.length) { lines.push(head, ...items); used += head.length + 1; }
  }
  if (dropped) lines.push(`...and ${dropped} more change${dropped > 1 ? 's' : ''}`);
  return { text: lines.join('\n'), groups, count };
}

/** Parse `git log --format=%x1e%s --name-only` output. */
export function parseLog(raw) {
  return String(raw).split('\x1e').map(r => r.replace(/\r/g, '').split('\n')).filter(l => l[0] && l[0].trim()).map(l => ({ subject: l[0].trim(), files: l.slice(1).map(x => x.trim()).filter(Boolean) }));
}

export function gitCommits(root, from, to = 'HEAD') {
  const range = from ? `${from}..${to}` : to;
  const raw = execFileSync('git', ['log', '--no-merges', '--format=%x1e%s', '--name-only', range], { cwd: root, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
  return parseLog(raw);
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  const args = process.argv.slice(2), opt = n => { const i = args.indexOf('--' + n); return i >= 0 ? args[i + 1] : undefined; };
  const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
  if (!opt('from')) { console.error('usage: node Installer/Release-Notes.mjs --from <tag|commit> [--to HEAD] [--out notes.txt] [--json]'); process.exit(2); }
  let r;
  try { r = buildNotes(gitCommits(root, opt('from'), opt('to') || 'HEAD')); } catch (e) { console.error(`git log failed: ${String(e.message).split('\n')[0]}`); process.exit(1); }
  if (opt('out')) fs.writeFileSync(path.resolve(opt('out')), r.text + '\n');
  if (args.includes('--json')) console.log(JSON.stringify({ ok: true, count: r.count, notes: r.text }));
  else console.log(r.text || '(no user-visible changes)');
}
