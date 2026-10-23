// node --test Pipeline/lib-stubs.test.mjs  (temp folders only; never reads or writes the real Data)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { stubRoles } from './lib-stubs.mjs';

const master = { users: { newsub: { tenure: 7, streak: 3, founder: true }, plain: { tenure: 1, streak: 1, founder: false }, odd: { tenure: 'x' } } };

test('months, streak and founder come from the roster', () => {
  assert.deepEqual(stubRoles(master, 'NewSub'), { subMonths: 7, subStreak: 3, founder: true });
  assert.deepEqual(stubRoles(master, 'plain'), { subMonths: 1, subStreak: 1 });
  assert.deepEqual(stubRoles(master, 'odd'), { subMonths: 0, subStreak: 0 });
  assert.deepEqual(stubRoles(master, 'nobody'), {});
  assert.deepEqual(stubRoles(null, 'x'), {});
});

test('push-profiles --dry with a temp Data dir: creates the stub, leaves an existing profile alone', () => {
  const root = mkdtempSync(join(tmpdir(), 'pp-'));
  const data = join(root, 'Data'), app = join(root, 'app');
  for (const d of ['profiles', 'subs']) mkdirSync(join(data, d), { recursive: true });
  mkdirSync(app, { recursive: true });
  writeFileSync(join(app, 'settings.json'), '{}');
  const existing = { login: 'oldsub', name: 'OldSub', roles: { subMonths: 2 } };
  writeFileSync(join(data, 'profiles', 'oldsub.json'), JSON.stringify(existing));
  writeFileSync(join(data, 'subs', 'subscribers_master.json'), JSON.stringify({ users: { newsub: { tenure: 7, streak: 3, founder: true }, oldsub: { tenure: 99, streak: 99, founder: true } } }));
  writeFileSync(join(data, 'subs', 'live_subs.json'), JSON.stringify({ at: Date.now() / 1000, count: 2, users: { newsub: { name: 'NewSub', tier: 1 }, oldsub: { name: 'OldSub', tier: 1 } } }));
  const dump = join(root, 'dump.json');
  const r = spawnSync(process.execPath, [join(dirname(fileURLToPath(import.meta.url)), 'push-profiles.mjs'), '--dry'], { env: { ...process.env, PINGUINO_DATA_DIR: app, PINGUINO_PROFILE_DATA: data, PUSH_PROFILES_DUMP: dump }, encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr);
  const got = JSON.parse(readFileSync(dump, 'utf8'));
  assert.equal(got.newsub.roles.subMonths, 7);
  assert.equal(got.newsub.roles.subStreak, 3);
  assert.equal(got.newsub.roles.founder, true);
  assert.equal(got.oldsub.roles.subMonths, 2);          // existing profile: months untouched
  assert.equal(got.oldsub.roles.founder, undefined);
});
