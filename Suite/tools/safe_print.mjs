// safe_print: make control characters visible so a BEL (0x07) in chat text or test data can never ring the speaker.
// 0x00-0x08, 0x0b, 0x0c, 0x0e-0x1f, 0x7f become \xNN (BEL -> \x07); \t \r \n pass through.
//   import { clean, safePrint, install } from '../Suite/tools/safe_print.mjs';   install() sanitizes process.stdout/stderr and so console.log.
const CTRL = /[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g;
export const clean = s => String(s).replace(CTRL, c => '\\x' + c.charCodeAt(0).toString(16).padStart(2, '0'));
export const safePrint = (...a) => console.log(...a.map(x => typeof x === 'string' ? clean(x) : x));
export function install() {
  for (const s of [process.stdout, process.stderr]) {
    if (s._safe) continue;
    const w = s.write.bind(s);
    s.write = (chunk, ...r) => w(typeof chunk === 'string' ? clean(chunk) : (Buffer.isBuffer(chunk) && chunk.includes(7) ? clean(chunk.toString('utf8')) : chunk), ...r);
    s._safe = true;
  }
}
