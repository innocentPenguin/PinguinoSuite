// Copies Shared\PinguinoBots.cs.txt into every Streamer.bot action that uses it, between
//     // <<PINGUINO-SHARED-BEGIN>>   and   // <<PINGUINO-SHARED-END>>
// (each Streamer.bot action is compiled on its own, so the shared code has to be pasted into each one; this keeps the copies identical).
//   node Shared\sync-shared.mjs            writes the copies
//   node Shared\sync-shared.mjs --check    only checks (exit code 1 when a copy is out of date)
// If a file has no markers yet, the block is inserted right after the opening brace of "public class CPHInline".
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.dirname(here);
const targets = [
  'PinguinoChat\\PinguinoChat.cs',
  'HelperPinguino\\PinguinoHelper.cs',
  'PinguinoB0t\\PinguinoBotCore.cs',
  'Shared\\PinguinoRouter.cs',
];
const BEGIN = '// <<PINGUINO-SHARED-BEGIN>>', END = '// <<PINGUINO-SHARED-END>>';
const check = process.argv.includes('--check');
const block = fs.readFileSync(path.join(here, 'PinguinoBots.cs.txt'), 'utf8').replace(/\r\n/g, '\n').replace(/\s+$/, '');

let stale = 0;
for (const rel of targets) {
  const file = path.join(root, rel);
  if (!fs.existsSync(file)) { console.log('skip (missing): ' + rel); continue; }
  const raw = fs.readFileSync(file, 'utf8');
  const crlf = raw.includes('\r\n');
  let s = raw.replace(/\r\n/g, '\n');
  const bi = s.indexOf(BEGIN), ei = s.indexOf(END);
  let out;
  if (bi >= 0 && ei > bi) {
    // the block starts at the beginning of the BEGIN line and ends at the end of the END line
    const start = s.lastIndexOf('\n', bi) + 1, endLine = s.indexOf('\n', ei);
    const end = endLine < 0 ? s.length : endLine;
    // the snippet file itself carries the header comment ABOVE the markers? no: the BEGIN marker is its first line
    out = s.slice(0, start) + block.replace(/^\s*\/\/ <<PINGUINO-SHARED-BEGIN>>/, '    ' + BEGIN) + s.slice(end);
  } else {
    const m = /^public class CPHInline[^\n]*\n\s*\{\n/m.exec(s);
    if (!m) { console.log('no class found in ' + rel); stale++; continue; }
    const at = m.index + m[0].length;
    out = s.slice(0, at) + '\n' + block.replace(/^\s*\/\/ <<PINGUINO-SHARED-BEGIN>>/, '    ' + BEGIN) + '\n\n' + s.slice(at);
  }
  if (out === s) { console.log('up to date: ' + rel); continue; }
  if (check) { console.log('OUT OF DATE: ' + rel); stale++; continue; }
  fs.writeFileSync(file, crlf ? out.replace(/\n/g, '\r\n') : out, 'utf8');
  console.log('updated: ' + rel);
}
process.exit(check && stale ? 1 : 0);
