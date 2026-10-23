// Modules page: install.json parts decide "Not installed" (mergeRows in src/index.html). Run: node --test PinguinoLite/test
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const html = fs.readFileSync(path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'src', 'index.html'), 'utf8');
const cmpLine = html.split('\n').find(l => l.startsWith('const cmpVer'));
const block = html.slice(html.indexOf('// ROWS-BEGIN'), html.indexOf('// ROWS-END'));
assert.ok(cmpLine && block, 'markers present');
const ctx = {}; vm.createContext(ctx); vm.runInContext(`${cmpLine}\n${block}\nthis.mergeRows = mergeRows; this.normReplays = normReplays;`, ctx);
const merge = (...a) => JSON.parse(JSON.stringify(ctx.mergeRows(...a)));

const catalog = { data: { modules: [{ id: 'link', name: 'Link', version: '2.0' }, { id: 'spotify', name: 'Spotify', version: '1.2' }, { id: 'multi', name: 'Multi', version: '1.0' }, { id: 'voice', version: '1' }] } };
const installed = { data: { modules: { spotify: { version: '1.0' }, multi: { version: '1.0' } } } };
const status = { data: { modules: { spotify: { state: 'running' }, multi: { state: 'running' } }, busy: {} } };
const mods = { supported: true, link: true, modules: [{ id: 'listen', installed: false }, { id: 'multi', installed: false }, { id: 'spotify', installed: true }] };
const byId = r => Object.fromEntries(r.map(x => [x.id, x]));

test('without install.json the old behaviour stays (Link installed.json decides)', () => {
  const r = byId(merge(catalog, installed, status, null, ['voice']));
  assert.equal(r.spotify.installed, true); assert.equal(r.spotify.update, true); assert.equal(r.multi.installed, true); assert.equal(r.voice, undefined);
  assert.equal(byId(merge(catalog, installed, status, { supported: false, modules: mods.modules }, []))['multi'].installed, true);
});

test('install.json parts win: module Link still lists is shown Not installed, no update, no stale state', () => {
  const r = byId(merge(catalog, installed, status, mods, ['voice']));
  assert.equal(r.multi.installed, false); assert.equal(r.multi.update, false); assert.equal(r.multi.installed_version, null); assert.equal(r.multi.conn, undefined); assert.equal(r.multi.profile, true);
  assert.equal(r.spotify.installed, true); assert.equal(r.spotify.update, true); assert.equal(r.spotify.installed_version, '1.0'); assert.equal(r.spotify.conn.state, 'running');
});

test('installed by profile but unknown to Link: Installed without a version or update', () => {
  const r = byId(merge(catalog, { data: { modules: {} } }, status, mods, []));
  assert.equal(r.spotify.installed, true); assert.equal(r.spotify.installed_version, null); assert.equal(r.spotify.update, false);
});

test('link follows the profile too; an install without Link shows it Not installed', () => {
  assert.equal(byId(merge(catalog, installed, status, { ...mods, link: false }, []))['link'].installed, false);
  assert.equal(byId(merge(catalog, { data: { modules: { link: { version: '2.0' } } } }, status, mods, []))['link'].installed, true);
});

test('missing files never throw', () => {
  assert.deepEqual(merge(null, null, null, null, []), []);
  assert.deepEqual(merge({ exists: false }, { exists: false }, { exists: false }, { supported: true }, []), []);
});

test('installed.json entry without a version: installed, version unknown, no update badge', () => {
  const r = byId(merge(catalog, { data: { modules: { spotify: {} } } }, status, mods, []));
  assert.equal(r.spotify.installed, true); assert.equal(r.spotify.installed_version, null); assert.equal(r.spotify.update, false);
});

// Empty / first-run hints
const hintsBlock = html.slice(html.indexOf('// HINTS-BEGIN'), html.indexOf('// HINTS-END'));
const hctx = {}; vm.createContext(hctx); vm.runInContext(`${hintsBlock}\nthis.hints = hints;`, hctx);
const hints = x => JSON.parse(JSON.stringify(hctx.hints(x)));
test('first run: no install.json, no Link, no replay folder each say why', () => {
  const h = hints({ ports: {}, parts: { supported: false }, catalog: { exists: false }, status: { exists: false }, replays: { dirs: [{ name: 'Demos', exists: false }], items: [] } });
  assert.match(h.install, /no install\.json/); assert.match(h.link, /PinguinoLink is not running/); assert.match(h.catalog, /not running/); assert.match(h.replays, /No Rocket League replay folder/);
});
test('Link up but catalog missing; folder present but empty; all fine = no hints', () => {
  const h = hints({ ports: { 7777: true }, parts: { supported: true }, catalog: { exists: false }, status: { exists: true }, replays: { dirs: [{ exists: true }], items: [] } });
  assert.equal(h.link, ''); assert.equal(h.install, ''); assert.match(h.catalog, /has not written/); assert.match(h.replays, /no replays Lite could read/);
  const ok = hints({ ports: { 7777: true }, parts: { supported: true }, catalog: { exists: true }, status: { exists: true }, replays: { dirs: [{ exists: true }], items: [{}] } });
  assert.deepEqual(Object.values(ok), ['', '', '', '']);
  assert.match(hints({ ports: {}, status: { exists: true }, catalog: { exists: true }, replays: { dirs: [], items: [] } }).link, /not answering/);
});

test('normReplays: any reply shape gives items[] and dirs[], so a bad reply cannot blank the page', () => {
  const n = x => JSON.parse(JSON.stringify(ctx.normReplays(x)));
  for (const bad of [null, undefined, 'error: no folder', 42, [], { items: null }, { items: 'x', dirs: 5 }, { error: 'boom' }]) {
    const r = n(bad); assert.ok(Array.isArray(r.items) && Array.isArray(r.dirs), JSON.stringify(bad));
  }
  const good = n({ interval: 4, items: [{ status: 'complete' }, null, 7], dirs: [{ name: 'Demos', exists: true }, null] });
  assert.equal(good.interval, 4); assert.equal(good.items.length, 1); assert.equal(good.dirs.length, 1);
});
