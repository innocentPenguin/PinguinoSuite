// INDEX Rebuild-Plan.mjs: which commits need which rebuild/restart since the last build, from git log + path rules. Read-only: runs git and stats files, builds nothing.
// node Installer/Rebuild-Plan.mjs [--since <date|commit>] [--md] [--json] [--files]
//   default: each part uses the time of its own newest built file (shell exe, core exe, Host dll, Lite exe). A part with no built file falls back to --since or 2026-10-22 00:00.
//   --since X   use X for every part (a date such as 2026-10-22, or a commit-ish: commits after it)
//   --md        markdown (for Docs\REBUILD_CHECKLIST.md)   --json  machine-readable   --files  also list the changed files per commit
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
export const ROOT = path.resolve(here, '..');
export const FALLBACK = '2026-10-22T00:00:00';

/** One entry per thing that can need work. `test` decides per changed file (forward slashes). `built` = files whose newest mtime is "the last build". */
export const PARTS = [
  { id: 'shell', title: 'Shell rebuild (Tauri app)', how: 'App\\Build-All.bat --only shell (Build-Shell skips when nothing is newer)',
    test: f => /^App\/src\//.test(f) || /^App\/src-tauri\/(src|capabilities|tauri\.conf\.json|Cargo\.(toml|lock)|build\.rs|icons)/.test(f),
    built: ['App/src-tauri/target/release/pinguino-suite.exe'] },
  { id: 'core', title: 'Core rebuild (frozen Python)', how: 'App\\Build-All.bat --only core --force   (Build-All may say "up to date" and skip: Stale.ps1 only compares times, so force it)',
    test: f => (/^Suite\/suite\/.+\.py$/.test(f) || f === 'Suite/modules.json'),
    built: ['App/src-tauri/binaries/pinguino-core.exe'] },
  { id: 'host', title: 'Host rebuild (dotnet)', how: 'App\\Build-All.bat --only host',
    test: f => /^PinguinoHost\//.test(f) && !/\/(bin|obj)\//.test(f) && !/\.(md|txt)$/i.test(f),
    built: ['PinguinoHost/bin/Release/net8.0/PinguinoHost.dll'] },
  { id: 'modules', title: 'Module restart (Listen, Multi, Link, Spotify, Voice)', how: 'App\\Update-Module.bat <id>  (listen first; or restart the whole app)',
    test: f => /^Suite\/modules\/(listen|multi|link|spotify|voice)\/(?!.*(test|tests)\/).+/.test(f) && !/\.(md|txt)$/i.test(f),
    // a module runs from the tree, so its "last build" is its last restart; the app restart (shell/core exe time) is the best proxy we can read
    built: ['App/src-tauri/target/release/pinguino-suite.exe', 'App/src-tauri/binaries/pinguino-core.exe'] },
  { id: 'lite', title: 'Lite rebuild (PinguinoLite, Tauri)', how: 'D: target recipe, see Docs\\sessions\\012-pinguinolite.md section 8: $env:CARGO_TARGET_DIR=\'D:\\cargo-target\\lite\'; $env:CARGO_BUILD_JOBS=\'1\'; cargo build --release --manifest-path D:\\PinguinoSuite\\PinguinoLite\\src-tauri\\Cargo.toml',
    test: f => /^PinguinoLite\/(src|src-tauri\/(src|capabilities|tauri\.conf\.json|Cargo\.(toml|lock)|build\.rs|icons))/.test(f),
    built: ['PinguinoLite/src-tauri/target/release/pinguino-lite.exe', 'D:/cargo-target/lite/release/pinguino-lite.exe'] },
];
export const NONE = { id: 'none', title: 'No rebuild (Node, site, docs, tests, installer tools)' };

const git = (...a) => execFileSync('git', a, { cwd: ROOT, encoding: 'utf8', maxBuffer: 256 * 1024 * 1024 });

/** Newest mtime (ms) of the first existing file among part.built, or null. */
export function lastBuilt(part) {
  let best = null, which = null;
  for (const rel of part.built) {
    const p = path.isAbsolute(rel) || /^[A-Za-z]:/.test(rel) ? rel : path.join(ROOT, rel);
    try { const t = fs.statSync(p).mtimeMs; if (best === null || t > best) { best = t; which = rel; } } catch {}
  }
  return best === null ? null : { ms: best, file: which };
}

/** All commits (newest first) with their changed files, from the oldest reference on. `since` may be a date or a commit-ish. */
export function readCommits(sinceArg) {
  const isRev = sinceArg && /^[0-9a-f]{6,40}$/i.test(sinceArg) || sinceArg && /^(HEAD|refs\/)/.test(sinceArg);
  const args = ['log', '--no-merges', '--name-only', '--format=%x01%h%x09%ct%x09%s'];
  if (isRev) args.push(`${sinceArg}..HEAD`); else args.push(`--since=${sinceArg || FALLBACK}`);
  return git(...args).split('\x01').filter(Boolean).map(chunk => {
    const [head, ...rest] = chunk.split('\n');
    const [hash, ct, ...s] = head.split('\t');
    return { hash, time: Number(ct) * 1000, subject: s.join('\t'), files: rest.map(x => x.trim()).filter(Boolean).map(x => x.replace(/\\/g, '/')) };
  });
}

/** Pure grouping: commits [{time, subject, files}], refs {partId: ms|null}. A commit is listed under every part it touches, otherwise under "none". */
export function plan(commits, refs, fallbackMs = 0) {
  const out = Object.fromEntries([...PARTS, NONE].map(p => [p.id, []]));
  for (const c of commits) {
    let hit = false;
    for (const p of PARTS) {
      const since = refs[p.id] ?? fallbackMs;
      const files = c.files.filter(p.test);
      if (c.time > since && files.length) { out[p.id].push({ ...c, matched: files }); hit = true; }
    }
    if (!hit && c.time > Math.min(fallbackMs, ...Object.values(refs).map(v => v ?? fallbackMs))) out.none.push({ ...c, matched: [] });
  }
  return out;
}

export function build(sinceArg) {
  const fb = sinceArg && !/^[0-9a-f]{6,40}$/i.test(sinceArg) && !/^(HEAD|refs\/)/.test(sinceArg) ? Date.parse(sinceArg) : Date.parse(FALLBACK);
  const refs = {}, info = {};
  for (const p of PARTS) {
    const lb = sinceArg ? null : lastBuilt(p);
    refs[p.id] = lb ? lb.ms : null;
    info[p.id] = lb ? { since: new Date(lb.ms).toISOString(), from: lb.file } : { since: sinceArg || FALLBACK, from: sinceArg ? '--since' : 'fallback (no built file found)' };
  }
  // read from the oldest reference so no part misses a commit; a commit-ish --since is applied by git itself
  const oldest = sinceArg || new Date(Math.min(fb, ...Object.values(refs).map(v => v ?? fb))).toISOString();
  const commits = readCommits(oldest);
  const isRev = !!sinceArg && /^([0-9a-f]{6,40}|HEAD.*|refs\/.*)$/i.test(sinceArg);
  return { info, groups: plan(commits, isRev ? Object.fromEntries(PARTS.map(p => [p.id, 0])) : refs, fb), total: commits.length };
}

const when = ms => new Date(ms).toISOString().slice(0, 16).replace('T', ' ');
export function render(r, { md = false, files = false, all = false } = {}) {
  const L = [], h = t => L.push(md ? `### ${t}` : `== ${t} ==`);
  for (const p of PARTS) {
    const g = r.groups[p.id];
    h(`${p.title}: ${g.length} commit${g.length === 1 ? '' : 's'}`);
    L.push(`${md ? '- ' : ''}since ${r.info[p.id].since} (${r.info[p.id].from})`);
    if (g.length) L.push(`${md ? '- ' : ''}do: ${p.how}`);
    for (const c of g) {
      L.push(`${md ? '- `' + c.hash + '`' : '  ' + c.hash} ${c.subject}`);
      if (files) for (const f of c.matched.slice(0, 12)) L.push(`${md ? '  - ' : '      '}${f}`);
    }
    L.push('');
  }
  h(`${NONE.title}: ${r.groups.none.length}`);
  if (all) for (const c of r.groups.none) L.push(`${md ? '- `' + c.hash + '`' : '  ' + c.hash} ${c.subject}`);
  else {   // hundreds of lines nobody needs: count by area (--all lists them)
    const by = {};
    for (const c of r.groups.none) { const k = c.files.length ? c.files[0].split('/')[0] : '(empty)'; by[k] = (by[k] || 0) + 1; }
    L.push(Object.entries(by).sort((a, b) => b[1] - a[1]).map(([k, v]) => `${k} ${v}`).join(', ') + '   (--all lists them)');
  }
  return L.join('\n');
}

/** Order to run things in, only the steps that have commits (an empty plan prints "nothing to rebuild"). */
export function steps(r) {
  const n = id => r.groups[id].length, s = [];
  s.push('Tell Ivan, and check that the stream is OFFLINE (GET /api/live on 8770 must say false). Never rebuild while live.');
  if (n('shell') || n('core') || n('host')) s.push('Quit the app from the tray (Quit), so the exe, the core and the Host DLL are not locked.');
  if (n('host')) s.push('Host: App\\Build-All.bat --only host');
  if (n('core')) s.push('Core: App\\Build-All.bat --only core --force');
  if (n('shell')) s.push('Shell: App\\Build-All.bat --only shell');
  if (n('shell') || n('core') || n('host')) s.push('Launch with PinguinoApp.bat (or Build-All.bat with no flags builds the stale pieces and launches).');
  else if (n('modules')) s.push('No app restart needed: App\\Update-Module.bat listen (then multi, link, spotify, voice as listed), one at a time.');
  if (n('lite')) s.push('Lite (can run beside the above, only the coordinator): the D: target recipe from the Lite line.');
  return s.length > 1 ? s : ['Nothing to rebuild or restart.'];
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const a = process.argv.slice(2), opt = n => { const i = a.indexOf(n); return i >= 0 ? a[i + 1] : undefined; };
  const r = build(opt('--since'));
  if (a.includes('--json')) console.log(JSON.stringify({ info: r.info, steps: steps(r), groups: Object.fromEntries(Object.entries(r.groups).map(([k, v]) => [k, v.map(c => ({ hash: c.hash, subject: c.subject }))])) }, null, 2));
  else {
    console.log(render(r, { md: a.includes('--md'), files: a.includes('--files'), all: a.includes('--all') }));
    console.log((a.includes('--md') ? '### Order\n' : '== Order ==\n') + steps(r).map((x, i) => `${i + 1}. ${x}`).join('\n'));
  }
}
