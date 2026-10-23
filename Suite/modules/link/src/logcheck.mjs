// Link log rotation: node src/logcheck.mjs  (temp folder only, touches no real log)
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import assert from 'node:assert/strict';
import { rotateIfBig } from './log.mjs';

const d = fs.mkdtempSync(path.join(os.tmpdir(), 'linklog-'));
const f = path.join(d, 'link.jsonl');
try {
  assert.equal(rotateIfBig(f, 100, 3), false, 'missing file is fine');
  fs.writeFileSync(f, 'x'.repeat(50));
  assert.equal(rotateIfBig(f, 100, 3), false, 'small file stays');
  for (let n = 1; n <= 6; n++) {
    fs.writeFileSync(f, String(n).repeat(200));
    assert.equal(rotateIfBig(f, 100, 3), true);
  }
  const names = fs.readdirSync(d).sort();
  assert.deepEqual(names, ['link.jsonl.1', 'link.jsonl.2', 'link.jsonl.3'], 'at most 3 old files, live file moved away');
  assert.equal(fs.readFileSync(f + '.1', 'utf8')[0], '6', 'newest rotated file is .1');
  assert.equal(fs.readFileSync(f + '.3', 'utf8')[0], '4', 'oldest kept is .3; 1..3 were dropped');
  console.log('log rotation: ok');
} finally { fs.rmSync(d, { recursive: true, force: true }); }
