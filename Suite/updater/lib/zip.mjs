// INDEX zip.mjs: tiny zip reader/writer (stored + deflate) so the Updater and Installer need no dependencies.
// readZip never extracts anything: it only lists entries and hands back their bytes. Callers validate the names (see paths.mjs).
import zlib from 'node:zlib';

const TABLE = (() => { const t = new Uint32Array(256); for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; } return t; })();
export function crc32(buf) { let c = 0xffffffff; for (let i = 0; i < buf.length; i++) c = TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8); return (c ^ 0xffffffff) >>> 0; }

export const MAX_ENTRIES = 20000, MAX_ENTRY_BYTES = 1024 * 1024 * 1024;

/** @returns {{name:string, dir:boolean, size:number, data:()=>Buffer}[]} */
export function readZip(buf) {
  let eocd = -1;
  for (let i = buf.length - 22; i >= Math.max(0, buf.length - 22 - 65535); i--) if (buf.readUInt32LE(i) === 0x06054b50) { eocd = i; break; }
  if (eocd < 0) throw new Error('not a zip file');
  const count = buf.readUInt16LE(eocd + 10), cdOff = buf.readUInt32LE(eocd + 16);
  if (count > MAX_ENTRIES) throw new Error('zip has too many entries');
  const out = [];
  let p = cdOff;
  for (let n = 0; n < count; n++) {
    if (buf.readUInt32LE(p) !== 0x02014b50) throw new Error('zip directory is damaged');
    const flags = buf.readUInt16LE(p + 8), method = buf.readUInt16LE(p + 10), crc = buf.readUInt32LE(p + 16), csize = buf.readUInt32LE(p + 20), usize = buf.readUInt32LE(p + 24);
    const nlen = buf.readUInt16LE(p + 28), xlen = buf.readUInt16LE(p + 30), clen = buf.readUInt16LE(p + 32), lho = buf.readUInt32LE(p + 42);
    const attrs = buf.readUInt32LE(p + 38), madeBy = buf.readUInt16LE(p + 4) >> 8;
    const name = buf.toString('utf8', p + 46, p + 46 + nlen);
    p += 46 + nlen + xlen + clen;
    if (flags & 1) throw new Error('encrypted zip entries are not supported');
    if (usize > MAX_ENTRY_BYTES) throw new Error(`zip entry too large: ${name}`);
    const unixMode = madeBy === 3 ? (attrs >>> 16) : 0;
    const isLink = (unixMode & 0o170000) === 0o120000;
    out.push({
      name, dir: name.endsWith('/'), size: usize, link: isLink,
      data() {
        if (buf.readUInt32LE(lho) !== 0x04034b50) throw new Error('zip entry header is damaged');
        const start = lho + 30 + buf.readUInt16LE(lho + 26) + buf.readUInt16LE(lho + 28);
        const raw = buf.subarray(start, start + csize);
        const d = method === 0 ? Buffer.from(raw) : method === 8 ? zlib.inflateRawSync(raw, { maxOutputLength: MAX_ENTRY_BYTES }) : null;
        if (!d) throw new Error(`unsupported zip method ${method}`);
        if (d.length !== usize || crc32(d) !== crc) throw new Error(`zip entry failed its checksum: ${name}`);
        return d;
      },
    });
  }
  return out;
}

/** entries: [{name, data: Buffer}] -> zip Buffer (deflate). Used by the release builder and the tests. */
export function writeZip(entries) {
  const parts = [], cd = []; let off = 0;
  for (const e of entries) {
    const name = Buffer.from(e.name, 'utf8'), raw = e.data || Buffer.alloc(0), def = zlib.deflateRawSync(raw), useDef = def.length < raw.length;
    const body = useDef ? def : raw, method = useDef ? 8 : 0, crc = crc32(raw);
    const lh = Buffer.alloc(30); lh.writeUInt32LE(0x04034b50, 0); lh.writeUInt16LE(20, 4); lh.writeUInt16LE(0x0800, 6); lh.writeUInt16LE(method, 8);
    lh.writeUInt32LE(crc, 14); lh.writeUInt32LE(body.length, 18); lh.writeUInt32LE(raw.length, 22); lh.writeUInt16LE(name.length, 26);
    parts.push(lh, name, body);
    const ch = Buffer.alloc(46); ch.writeUInt32LE(0x02014b50, 0); ch.writeUInt16LE(20, 4); ch.writeUInt16LE(20, 6); ch.writeUInt16LE(0x0800, 8); ch.writeUInt16LE(method, 10);
    ch.writeUInt32LE(crc, 16); ch.writeUInt32LE(body.length, 20); ch.writeUInt32LE(raw.length, 24); ch.writeUInt16LE(name.length, 28); ch.writeUInt32LE(off, 42);
    cd.push(ch, name);
    off += 30 + name.length + body.length;
  }
  const cdBuf = Buffer.concat(cd), end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0); end.writeUInt16LE(entries.length, 8); end.writeUInt16LE(entries.length, 10); end.writeUInt32LE(cdBuf.length, 12); end.writeUInt32LE(off, 16);
  return Buffer.concat([...parts, cdBuf, end]);
}
