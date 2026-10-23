// node Tools/test-scrub-graph.mjs  -> PASS scrub-graph. Uses a temp dir; checks no verbatim text survives and everything else is kept.
import fs from 'fs'; import os from 'os'; import path from 'path'; import { execFileSync } from 'child_process';
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'pgscrub_')); const bad = [];
try {
  const SECRET = 'verbatim secret chat line 12345';
  const g = { built: 'x', nodes: [{ login: 'a', msgs: 5 }, { login: 'b', msgs: 6 }], edges: [{ a: 'a', b: 'b', mutual: 40, tags: ['chat friends'], example: SECRET }, { a: 'a', b: 'c', mutual: 3, tags: [], example: null }], groups: [{ group: 1, members: ['a', 'b'] }] };
  fs.writeFileSync(path.join(tmp, 'g.json'), JSON.stringify(g)); fs.mkdirSync(path.join(tmp, 'cards'));
  fs.writeFileSync(path.join(tmp, 'cards', 'a.json'), JSON.stringify({ login: 'a', treatsIvan: { read: 'friendly', evidence: [['t', SECRET]] }, likes: ['x'] }));
  const before = fs.readFileSync(path.join(tmp, 'g.json'), 'utf8');
  const out = execFileSync('node', [path.join(path.dirname(new URL(import.meta.url).pathname.replace(/^\/(\w:)/, '$1')), 'lore-mining', 'scrub-graph.mjs'), path.join(tmp, 'g.json'), path.join(tmp, 'pub.json'), path.join(tmp, 'cards'), path.join(tmp, 'cards_pub')], { encoding: 'utf8' });
  const pub = fs.readFileSync(path.join(tmp, 'pub.json'), 'utf8'); const card = fs.readFileSync(path.join(tmp, 'cards_pub', 'a.json'), 'utf8');
  if (pub.includes(SECRET) || pub.includes('"example"')) bad.push('example survived in graph');
  if (card.includes(SECRET) || card.includes('evidence')) bad.push('evidence survived in card');
  const p = JSON.parse(pub); if (p.nodes.length !== 2 || p.edges.length !== 2 || p.edges[0].mutual !== 40 || p.groups[0].members.length !== 2 || card.indexOf('likes') < 0) bad.push('other data lost');
  if (fs.readFileSync(path.join(tmp, 'g.json'), 'utf8') !== before || !fs.readFileSync(path.join(tmp, 'cards', 'a.json'), 'utf8').includes(SECRET)) bad.push('input was modified');
  if (!/scrubbed 1 edge/.test(out)) bad.push('count: ' + out);
  try { execFileSync('node', [path.join(path.dirname(new URL(import.meta.url).pathname.replace(/^\/(\w:)/, '$1')), 'lore-mining', 'scrub-graph.mjs'), path.join(tmp, 'g.json'), path.join(tmp, 'g.json')], { stdio: 'pipe' }); bad.push('in==out was allowed'); } catch { }
} finally { fs.rmSync(tmp, { recursive: true, force: true }); }
console.log(bad.length ? 'FAIL\n - ' + bad.join('\n - ') : 'PASS scrub-graph'); process.exit(bad.length ? 1 : 0);
