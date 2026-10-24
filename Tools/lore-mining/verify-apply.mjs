// node Tools/lore-mining/verify-apply.mjs [loreDir]   (default Data/lore) - post-apply checks for the people-graph rebuild; exit 1 on any FAIL.
import fs from 'fs'; import path from 'path';
const L = process.argv[2] || 'D:/PinguinoSuite/Data/lore';
const suite = 'D:/PinguinoSuite';
const rj = f => JSON.parse(fs.readFileSync(path.join(L, f), 'utf8'));
const G = rj('people_graph.json'), P = rj('people_graph.public.json');
const al = JSON.parse(fs.readFileSync(path.join(suite, 'Data/boards/aliases.json'), 'utf8')).aliases;
Object.assign(al, JSON.parse(fs.readFileSync(new URL('./lore-aliases.json', import.meta.url), 'utf8')).aliases); // lore-only aliases
const ids = new Set(G.nodes.map(n => n.login));
const names = d => new Set(fs.readdirSync(path.join(L, d)).filter(f => f.endsWith('.json')).map(f => f.slice(0, -5)));
const cards = names('person_cards'), pc = names('person_cards_public');
let bad = 0; const ok = (c, m) => { console.log((c ? 'OK   ' : 'FAIL ') + m); if (!c) bad++; };
ok(!Object.keys(al).some(a => ids.has(a)), 'no alias account is still a node');
ok(G.edges.every(e => ids.has(e.a) && ids.has(e.b)), 'no dangling edges');
ok(cards.size === ids.size && [...ids].every(i => cards.has(i)), 'cards == nodes (' + cards.size + ')');
ok(pc.size === ids.size && [...ids].every(i => pc.has(i)), 'public cards == nodes (' + pc.size + ')');
ok(!P.edges.some(e => 'example' in e), 'public graph has no excerpts');
ok(![...pc].some(c => fs.readFileSync(path.join(L, 'person_cards_public', c + '.json'), 'utf8').includes('"evidence"')), 'public cards have no evidence');
ok(P.nodes.length === G.nodes.length && P.edges.length === G.edges.length, 'public graph matches the private one');
ok(ids.has('kskycs2'), 'kskycs2 is a node');
console.log('nodes', G.nodes.length, 'edges', G.edges.length, 'groups', G.groups.length);
process.exit(bad ? 1 : 0);
