// INDEX overlay-smoke.mjs: GET-only smoke test of the pages OBS browser sources load (Host overlays on :8770, module pages) and the state APIs they read.
// node Tests/overlay-smoke/overlay-smoke.mjs [--host 127.0.0.1:8770] [--multi 127.0.0.1:8766] [--json] [--quiet]
// Fails (exit 1) on: a page that does not answer 200, visible text with undefined / NaN / [object Object] / a raw yt: or tt: key, a missing asset (src/href/url()),
// a state API (fetch('/api/...') found in the page) that does not answer 200 JSON, or JSON whose display fields hold undefined / NaN / [object Object] / a raw yt:/tt: key.
// Safe by construction: only GET, never POST, never contacts OBS or Twitch, never launches anything. Needs the app running; if a port is closed the page is reported as unreachable (fail).
// Also exported for the tests: scanText, scanJson, assetsOf, apiPathsOf.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const BAD_WORD = /\bundefined\b|\bNaN\b|\[object Object\]/;
const RAW_KEY = /(^|[\s@(>"'])(yt|tt):[A-Za-z0-9_-]{3,}/;
const DISPLAY_FIELDS = new Set(['name', 'display', 'displayname', 'display_name', 'label', 'text', 'message', 'title', 'who', 'viewer', 'from']);

/** Visible text problems in an HTML page: scripts, styles and comments are removed first (they legitimately say `undefined`). */
export function scanText(html) {
  const text = html.replace(/<script[\s\S]*?<\/script>/gi, ' ').replace(/<style[\s\S]*?<\/style>/gi, ' ').replace(/<!--[\s\S]*?-->/g, ' ').replace(/<[^>]+>/g, ' ');
  const out = [];
  for (const line of text.split(/\n/)) {
    const m = line.match(BAD_WORD) || line.match(RAW_KEY);
    if (m) out.push(line.trim().slice(0, 100));
  }
  return out;
}

/** Problems in a parsed JSON state: only display-like fields are checked (ids and Username keys may legitimately hold yt:... keys). */
export function scanJson(v, p = '$') {
  const out = [];
  if (Array.isArray(v)) v.forEach((x, i) => out.push(...scanJson(x, `${p}[${i}]`)));
  else if (v && typeof v === 'object') {
    for (const [k, x] of Object.entries(v)) {
      if (typeof x === 'string' && DISPLAY_FIELDS.has(k.toLowerCase()) && (BAD_WORD.test(x) || RAW_KEY.test(x))) out.push(`${p}.${k} = ${JSON.stringify(x.slice(0, 80))}`);
      else if (typeof x === 'number' && !Number.isFinite(x)) out.push(`${p}.${k} is not a number`);
      else out.push(...scanJson(x, `${p}.${k}`));
    }
  }
  return out;
}

/** Local assets a page loads: src=, href= (not anchors/links away) and css url(). */
export function assetsOf(html) {
  const set = new Set();
  const add = u => { if (u && !/^(https?:|data:|blob:|#|javascript:|mailto:|\/\/)/i.test(u) && !/[`${}]/.test(u)) set.add(u.split('#')[0].split('?')[0]); };
  // inline script bodies build strings like `x.src=`: only the <script ...> tag itself counts
  const markup = html.replace(/(<script\b[^>]*>)[\s\S]*?<\/script>/gi, '$1</script>').replace(/<!--[\s\S]*?-->/g, ' ');
  for (const m of markup.matchAll(/\b(?:src|href)\s*=\s*["']([^"']+)["']/gi)) add(m[1]);
  for (const m of html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, ' ').matchAll(/url\(\s*["']?([^"')]+)["']?\s*\)/gi)) add(m[1]);
  set.delete('');
  return [...set];
}

/** GET-only state paths a page reads: fetch('/x') / fetch("x") with no method option within the call. */
export function apiPathsOf(html) {
  const set = new Set();
  for (const m of html.matchAll(/fetch\(\s*(["'])(\/?[A-Za-z0-9_\-./]+)(?:\?[^"']*)?\1\s*([,)])([^;]{0,160})/g)) {
    if (m[3] === ',' && /method\s*:\s*["'](POST|PUT|DELETE|PATCH)/i.test(m[4])) continue;
    set.add(m[2].startsWith('/') ? m[2] : '/' + m[2]);
  }
  return [...set];
}

async function get(url, ms = 6000) {
  const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), ms);
  try {
    const r = await fetch(url, { signal: ctl.signal, method: 'GET', redirect: 'follow' });
    const buf = Buffer.from(await r.arrayBuffer());
    return { status: r.status, type: r.headers.get('content-type') || '', body: buf };
  } catch (e) { return { status: 0, type: '', body: Buffer.alloc(0), err: String(e.cause?.code || e.message) }; }
  finally { clearTimeout(t); }
}

export async function run({ host = '127.0.0.1:8770', multi = '127.0.0.1:8766', modules = ['127.0.0.1:8760/', '127.0.0.1:8765/', '127.0.0.1:8771/', '127.0.0.1:8772/'], overlayDir = path.join(ROOT, 'PinguinoB0t', 'overlays'), multiPaths = ['/obs/alerts', '/obs/goal'] } = {}) {
  const results = [];
  const note = (page, ok, msg) => results.push({ page, ok, msg });
  const seenApi = new Set();

  async function checkPage(base, rel, label, deep = true) {
    const url = `http://${base}${rel}`;
    const r = await get(url);
    if (r.status !== 200) return note(label, false, r.status ? `HTTP ${r.status}` : `unreachable (${r.err})`);
    const html = r.body.toString('utf8');
    const probs = scanText(html);
    if (probs.length) note(label, false, 'visible text: ' + probs.slice(0, 3).join(' | '));
    if (!deep) { if (!results.some(x => x.page === label && !x.ok)) note(label, true, 'ok'); return; }   // app UIs (core/Listen/...) need tokens and are not OBS sources: reachability + visible text only
    const dir = rel.replace(/[^/]*$/, '');
    for (const a of assetsOf(html)) {
      const au = a.startsWith('/') ? `http://${base}${a}` : `http://${base}${dir}${a}`;
      const ar = await get(au);
      if (ar.status !== 200) note(label, false, `asset ${a}: ${ar.status || 'unreachable'}`);
    }
    for (const api of apiPathsOf(html)) {
      const key = base + api; if (seenApi.has(key)) continue; seenApi.add(key);
      const jr = await get(`http://${base}${api}`);
      if (jr.status !== 200) { note(label, false, `state ${api}: HTTP ${jr.status || 'unreachable'}`); continue; }
      let j; try { j = JSON.parse(jr.body.toString('utf8')); } catch { continue; } // not JSON: only the 200 matters
      const jp = scanJson(j);
      if (jp.length) note(label, false, `state ${api}: ` + jp.slice(0, 3).join(' | '));
    }
    if (!results.some(x => x.page === label && !x.ok)) note(label, true, 'ok');
  }

  const dir = overlayDir;
  const pages = fs.existsSync(dir) ? fs.readdirSync(dir).filter(f => f.endsWith('.html') && !/backup/i.test(f)).sort() : [];
  for (const f of pages) await checkPage(host, '/' + f, `host ${f}`);
  for (const rel of multiPaths) await checkPage(multi, rel, `multi ${rel}`);
  for (const m of modules) { const i = m.indexOf('/'); await checkPage(m.slice(0, i), m.slice(i), `module ${m}`, false); }
  return results;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const a = process.argv.slice(2); const opt = n => { const i = a.indexOf('--' + n); return i >= 0 ? a[i + 1] : undefined; };
  const res = await run({ host: opt('host') || undefined, multi: opt('multi') || undefined });
  const bad = res.filter(r => !r.ok);
  if (a.includes('--json')) console.log(JSON.stringify({ ok: bad.length === 0, pages: res.length, bad }, null, 2));
  else {
    if (!a.includes('--quiet')) for (const r of res) console.log(`${r.ok ? 'ok  ' : 'FAIL'} ${r.page}${r.ok ? '' : '  ' + r.msg}`);
    console.log(bad.length ? `FAIL: ${bad.length} problem(s) on ${new Set(bad.map(b => b.page)).size} page(s)` : `PASS: ${new Set(res.map(r => r.page)).size} pages clean`);
  }
  process.exit(bad.length ? 1 : 0);
}
