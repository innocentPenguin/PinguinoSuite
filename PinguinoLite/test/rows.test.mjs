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
const ctx = {}; vm.createContext(ctx); vm.runInContext(`${cmpLine}\n${block}\nthis.mergeRows = mergeRows;`, ctx);
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
