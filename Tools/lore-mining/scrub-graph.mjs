// Scrub verbatim chat out of the lore files. usage:
//   node scrub-graph.mjs <people_graph.json> <out.json>             drops edge.example -> out.json (the file the Host/bots should load)
//   node scrub-graph.mjs <people_graph.json> <out.json> <cards_dir> <cards_out_dir>   also writes person cards without treatsIvan.evidence
// Never modifies or deletes the input. Everything else in the graph/cards is kept byte-for-byte equivalent (parsed JSON, same keys).
import fs from 'fs'; import path from 'path';
const [inF, outF, cardsIn, cardsOut] = process.argv.slice(2);
if (!inF || !outF || path.resolve(inF) === path.resolve(outF)) { console.error('usage: scrub-graph.mjs <in> <out> [cardsIn cardsOut]  (out must differ from in)'); process.exit(2); }
const g = JSON.parse(fs.readFileSync(inF, 'utf8'));
let n = 0;
for (const e of g.edges || []) if ('example' in e) { if (e.example) n++; delete e.example; }
g.scrubbed = { at: new Date().toISOString(), dropped: 'edges[].example (verbatim chat excerpts)' };
fs.mkdirSync(path.dirname(path.resolve(outF)), { recursive: true });
fs.writeFileSync(outF, JSON.stringify(g, null, 1));
let c = 0;
if (cardsIn && cardsOut) {
  if (path.resolve(cardsIn) === path.resolve(cardsOut)) { console.error('cards out dir must differ from in'); process.exit(2); }
  fs.mkdirSync(cardsOut, { recursive: true });
  for (const f of fs.readdirSync(cardsIn).filter(f => f.endsWith('.json'))) {
    const card = JSON.parse(fs.readFileSync(path.join(cardsIn, f), 'utf8'));
    if (card.treatsIvan && 'evidence' in card.treatsIvan) { delete card.treatsIvan.evidence; c++; }
    fs.writeFileSync(path.join(cardsOut, f), JSON.stringify(card, null, 1));
  }
}
console.log(`scrubbed ${n} edge examples` + (cardsOut ? `, ${c} card evidence blocks` : '') + ` -> ${outF}`);
