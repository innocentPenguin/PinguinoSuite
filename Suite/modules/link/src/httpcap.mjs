// INDEX httpcap.mjs: read a fetch() response body with a hard byte limit (a peer may not make this PC buffer unlimited data).

/** Whole body as a Buffer; throws as soon as more than `max` bytes arrive (also when Content-Length is missing or lies). */
export async function readCapped(res, max) {
  const len = Number(res.headers?.get?.('content-length'));
  if (len > max) { try { await res.body?.cancel(); } catch {} throw new Error(`answer larger than ${max} bytes`); }
  if (!res.body) return Buffer.alloc(0);
  const chunks = []; let n = 0;
  const reader = res.body.getReader();
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    n += value.length;
    if (n > max) { try { await reader.cancel(); } catch {} throw new Error(`answer larger than ${max} bytes`); }
    chunks.push(Buffer.from(value));
  }
  return Buffer.concat(chunks);
}
/** JSON body, capped (default 256 KB); throws on oversize or bad JSON. */
export async function jsonCapped(res, max = 256 * 1024) {
  return JSON.parse((await readCapped(res, max)).toString('utf8'));
}
